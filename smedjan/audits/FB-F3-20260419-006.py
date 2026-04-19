import re, sys, json, time, subprocess, itertools
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, "/Users/anstudio/agentindex")
from smedjan import sources

# --- 1. already-audited pairs (001-005) ---
seen = set()
for i in range(1, 6):
    p = Path.home()/f"smedjan/audits/FB-F3-20260419-00{i}.md"
    for line in p.read_text().splitlines():
        m = re.match(r'^\|\s*([a-z0-9_]+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|', line)
        if m and m.group(1) != 'registry':
            a, b = sorted([m.group(2).strip(), m.group(3).strip()])
            seen.add((m.group(1), a, b))
print(f"excluding {len(seen)} previously-audited pairs", file=sys.stderr)

# --- 2. load demand scores ---
with sources.smedjan_db_cursor() as (_, cur):
    cur.execute("SELECT slug, score FROM smedjan.ai_demand_scores WHERE slug <> 'test' ORDER BY score DESC LIMIT 600")
    demand = dict(cur.fetchall())
print(f"loaded {len(demand)} demand rows", file=sys.stderr)

# --- 3. for each registry, find which of these top slugs exist and rank ---
top_slugs = list(demand.keys())
with sources.nerq_readonly_cursor() as (_, cur):
    cur.execute(
        "SELECT DISTINCT slug, source FROM entity_lookup WHERE slug = ANY(%s) AND source IS NOT NULL",
        (top_slugs,),
    )
    rows = cur.fetchall()
by_reg = defaultdict(list)
for slug, source in rows:
    by_reg[source].append(slug)
print(f"registries with demand-slugs: {len(by_reg)}", file=sys.stderr)

# --- 4. per-registry top-N, then all within-registry pairs scored ---
TOP_PER_REG = 40
scored_pairs = {}  # (reg, a, b) -> score
for reg, slugs in by_reg.items():
    # sort by demand score desc, take top-N
    slugs_sorted = sorted(slugs, key=lambda s: demand[s], reverse=True)[:TOP_PER_REG]
    for a, b in itertools.combinations(slugs_sorted, 2):
        a2, b2 = sorted([a, b])
        key = (reg, a2, b2)
        scored_pairs[key] = demand[a] + demand[b]

# --- 5. collapse cross-registry dups to highest-scored registry ---
by_pair = {}  # (a,b) -> (reg, score)
for (reg, a, b), score in scored_pairs.items():
    k = (a, b)
    if k not in by_pair or by_pair[k][1] < score:
        by_pair[k] = (reg, score)

# --- 6. rebuild as (reg, a, b, score) and exclude seen ---
candidates = []
for (a, b), (reg, score) in by_pair.items():
    if (reg, a, b) in seen:
        continue
    # also exclude if the pair was seen in ANY registry (avoid repeats)
    if any((r, a, b) in seen for r in by_reg):
        continue
    candidates.append((reg, a, b, score))
candidates.sort(key=lambda x: x[3], reverse=True)
print(f"candidate pairs: {len(candidates)}", file=sys.stderr)

picked = candidates[:50]

# --- 7. curl each ---
def check(a, b):
    url = f"https://nerq.ai/compare/{a}-vs-{b}"
    try:
        out = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "--max-time", "20",
             "-A", "smedjan-audit/1.0",
             url],
            capture_output=True, text=True, timeout=25,
        )
        code = out.stdout.strip() or "000"
    except Exception as e:
        code = "ERR"
    return code

results = []
for i, (reg, a, b, score) in enumerate(picked, 1):
    code = check(a, b)
    results.append((reg, a, b, code, score))
    if i % 10 == 0:
        print(f"  done {i}/50", file=sys.stderr)
    time.sleep(0.15)

# --- 8. write markdown ---
def rec_for(code):
    if code == "404":
        return "create"
    if code == "200":
        return "skip"
    return "investigate"

counts = {"200": 0, "404": 0, "other": 0}
for *_, code, _s in [(r[0], r[1], r[2], r[3], r[4]) for r in results]:
    if code == "200":
        counts["200"] += 1
    elif code == "404":
        counts["404"] += 1
    else:
        counts["other"] += 1

out_path = Path.home()/"smedjan/audits/FB-F3-20260419-006.md"
lines = [
    "# FB-F3-20260419-006 /compare/ coverage proposals (top 50 pairs)",
    "",
    "Fallback-generated. Top 40 demand-scored slugs per registry (joined to Nerq `entity_lookup.source`) are cross-paired within each registry; each pair is scored by combined demand; cross-registry duplicates collapse to the highest-scoring registry. Pairs already audited in sibling tasks FB-F3-20260419-001..005 are excluded so this run surfaces the next tier of proposals. Slug `test` is dropped (scraping artefact).",
    "",
    "For each pair the audit runs `curl https://nerq.ai/compare/<a>-vs-<b>` (User-Agent `smedjan-audit/1.0`, 20 s timeout, no redirect follow) and records the HTTP status. Recommendation: `create` if 404, `skip` if 200, `investigate` otherwise. No pages are created here — a follow-up task materialises any `create` rows.",
    "",
    "| registry | slug_a | slug_b | http_status | recommendation |",
    "|----------|--------|--------|-------------|----------------|",
]
for reg, a, b, code, _score in results:
    lines.append(f"| {reg} | {a} | {b} | {code} | {rec_for(code)} |")
lines.append("")
lines.append(f"**counts_by_status:** `{json.dumps(counts)}`")
lines.append("")
lines.append("## Notes")
lines.append("")
lines.append("Excluded 79 pairs previously curled by FB-F3-20260419-001..005 so this run covers the next-best proposals. As with prior audits, Nerq's `/compare/` route may serve a lightweight stub page, so a `200` here means 'route responds' not 'analysis materialised'. Body-inspection (detect `Not Yet Analyzed`) would split `skip` into `skip-real` vs `skip-stub` for a future refinement task.")
out_path.write_text("\n".join(lines) + "\n")
print(json.dumps({"counts": counts, "wrote": str(out_path), "rows": len(results)}))
