#!/usr/bin/env python3
"""
Nerq Trust Score Engine v2.0 — 5 Dimensions, 4.9M agents
"""

import json
import time
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import execute_values, DictCursor

DB_DSN = "dbname=agentindex"
BATCH_SIZE = 5000
NOW = datetime.now(timezone.utc).replace(tzinfo=None)

PERMISSIVE_LICENSES = {
    'MIT', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause', 'ISC',
    'Unlicense', 'CC0-1.0', 'MIT-0', 'MPL-2.0', 'CC-BY-4.0',
    'WTFPL', 'Zlib', 'BSL-1.0', '0BSD', 'CC-BY-SA-4.0'
}
COPYLEFT_LICENSES = {
    'GPL-2.0', 'GPL-3.0', 'AGPL-3.0', 'LGPL-2.1', 'LGPL-3.0',
    'EUPL-1.2', 'OSL-3.0'
}
VERIFIED_REGISTRIES = {'npm', 'npm_full', 'pypi', 'pypi_full', 'pypi_ai'}
MCP_REGISTRIES = {'mcp_registry', 'mcp', 'glama_mcp'}

RISKY_SHELL = ['shell', 'exec', 'subprocess', 'os.system', 'child_process',
               'eval(', 'execsync', 'spawn(', 'popen']
RISKY_FS_WRITE = ['write file', 'filesystem write', 'fs.write', 'os.remove',
                  'shutil.rmtree', 'unlink(', 'delete file']
RISKY_NETWORK = ['http request', 'outbound', 'requests.get', 'urllib',
                 'axios', 'fetch(', 'httpx']
RISKY_CREDS = ['password', 'credential', 'secret', 'api_key', 'api key',
               'token', 'oauth', 'private_key', 'ssh_key']
SECURITY_KEYWORDS = ['security', 'vulnerability', 'disclosure', 'report a bug',
                     'responsible disclosure', 'security.md', 'cve']
TESTING_KEYWORDS = ['pytest', 'jest', 'mocha', 'unittest', 'test suite',
                    'coverage', 'github actions', 'ci/cd', 'circleci', 'travis']


def score_security(agent, text_to_scan):
    points = 50
    license_val = agent['license'] or ''
    source = agent['source'] or ''
    is_verified = agent['is_verified'] or False
    rm = agent['raw_metadata']
    has_readme = False; readme_text = ''
    has_pkg = False
    if rm and isinstance(rm, dict):
        has_readme = bool(rm.get('readme'))
        has_pkg = bool(rm.get('package_json') or rm.get('pyproject'))
        readme_text = (rm.get('readme') or '')[:5000].lower()

    if license_val:
        if license_val in PERMISSIVE_LICENSES: points += 15
        elif license_val in COPYLEFT_LICENSES: points += 8
        elif license_val == 'NOASSERTION': points -= 8
        else: points += 4
    else:
        points -= 12

    if has_readme and len(readme_text) > 500: points += 8
    elif has_readme or len(text_to_scan) > 200: points += 3

    if any(kw in readme_text for kw in SECURITY_KEYWORDS): points += 10
    if any(kw in readme_text for kw in TESTING_KEYWORDS): points += 7
    if has_pkg: points += 5

    if any(kw in text_to_scan for kw in RISKY_SHELL): points -= 15
    if any(kw in text_to_scan for kw in RISKY_FS_WRITE): points -= 8
    if any(kw in text_to_scan for kw in RISKY_NETWORK): points -= 5
    if any(kw in text_to_scan for kw in RISKY_CREDS): points -= 8

    if source in VERIFIED_REGISTRIES: points += 8
    elif source in MCP_REGISTRIES: points += 5
    if is_verified: points += 12

    return max(0, min(100, points))


def score_compliance(agent):
    cs = agent['compliance_score']
    if cs is None: return 40
    if cs >= 80: return 90
    if cs >= 70: return 80
    if cs >= 60: return 70
    if cs >= 50: return 60
    if cs >= 40: return 50
    if cs >= 30: return 35
    if cs >= 20: return 25
    return 15


def score_maintenance(agent, contrib=None):
    """Maintenance score: recency (70%) + contributor activity (30%).

    Contributor data is descriptive, not predictive. A dormant project is not
    automatically bad — mature packages can be stable without recent activity.
    The contributor signal adjusts the maintenance score by up to ±15 points.
    """
    lu = agent['last_source_update']
    tc = agent['trust_components']

    # Base: recency score (same as before)
    if lu:
        d = (NOW - lu).days
        if d <= 14: base = 98
        elif d <= 30: base = 92
        elif d <= 60: base = 80
        elif d <= 90: base = 70
        elif d <= 180: base = 55
        elif d <= 365: base = 35
        else: base = 15
    elif tc and isinstance(tc, dict):
        s = tc.get('activity',0)*0.4 + tc.get('recency',0)*0.4 + tc.get('stability',0)*0.2
        base = max(0, min(100, s))
    else:
        base = 40

    # Contributor adjustment (±15 points max, conservative)
    if contrib:
        active = contrib.get('active_contributors_6mo', -1)
        tier = contrib.get('contributor_tier', 'unknown')
        if tier == 'active-community':      # 6+ active
            adj = +10
        elif tier == 'small-team':          # 2-5 active
            adj = +5
        elif tier == 'single-maintainer':   # 1 active
            adj = -5
        elif tier == 'dormant':             # 0 active in 6 months
            adj = -15
        else:
            adj = 0
        base = max(0, min(100, base + adj))

    return base


def score_popularity(agent):
    stars = agent['stars'] or 0
    downloads = agent['downloads'] or 0
    forks = agent['forks'] or 0

    if stars >= 10000: ss = 98
    elif stars >= 1000: ss = 90
    elif stars >= 500: ss = 82
    elif stars >= 100: ss = 72
    elif stars >= 50: ss = 62
    elif stars >= 10: ss = 50
    elif stars >= 1: ss = 35
    else: ss = 0

    if downloads >= 1000000: ds = 95
    elif downloads >= 100000: ds = 85
    elif downloads >= 10000: ds = 70
    elif downloads >= 1000: ds = 55
    elif downloads >= 100: ds = 40
    elif downloads >= 10: ds = 30
    else: ds = 0

    fb = 15 if forks >= 100 else 10 if forks >= 10 else 5 if forks >= 3 else 0
    base = max(ss, ds)
    if base == 0: return 30
    return max(0, min(100, base + fb))


def score_ecosystem(agent, author_count):
    points = 30
    caps = agent['capabilities']
    at = agent['agent_type'] or ''
    src = agent['source'] or ''
    rm = agent['raw_metadata']

    if caps and isinstance(caps, list) and len(caps) > 0: points += 20
    if at == 'mcp_server' or src in MCP_REGISTRIES: points += 20
    if at in ('agent', 'tool'): points += 10
    if agent.get('category'): points += 8
    inv = agent.get('invocation')
    if inv and isinstance(inv, dict) and len(inv) > 0: points += 10
    if rm and isinstance(rm, dict):
        if rm.get('package_json') or rm.get('pyproject'): points += 8
    if author_count >= 20: points += 12
    elif author_count >= 5: points += 8
    elif author_count >= 2: points += 4
    return max(0, min(100, points))


W = {'security': 0.30, 'compliance': 0.25, 'maintenance': 0.20,
     'popularity': 0.15, 'ecosystem': 0.10}

def compute(agent, ac, contrib=None):
    desc = (agent['description'] or '').lower()
    caps = ''
    if agent['capabilities'] and isinstance(agent['capabilities'], list):
        caps = ' '.join(str(c).lower() for c in agent['capabilities'])
    readme = ''
    if agent['raw_metadata'] and isinstance(agent['raw_metadata'], dict):
        readme = (agent['raw_metadata'].get('readme') or '')[:5000].lower()
    txt = f"{desc} {caps} {readme}"

    dims = {
        'security': score_security(agent, txt),
        'compliance': score_compliance(agent),
        'maintenance': score_maintenance(agent, contrib),
        'popularity': score_popularity(agent),
        'ecosystem': score_ecosystem(agent, ac),
    }
    score = round(max(0, min(100, sum(dims[k]*W[k] for k in W))), 1)

    if score >= 90: g = 'A+'
    elif score >= 80: g = 'A'
    elif score >= 70: g = 'B'
    elif score >= 60: g = 'C'
    elif score >= 45: g = 'D'
    elif score >= 30: g = 'E'
    else: g = 'F'

    r = 'low' if score >= 70 else 'medium' if score >= 50 else 'high' if score >= 30 else 'critical'
    return score, g, r, dims


def main():
    print("=" * 65)
    print("  NERQ TRUST SCORE ENGINE v2.0")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = False

    print("\n[1/4] Preparing columns...")
    with conn.cursor() as cur:
        for col, ct in [('trust_score_v2','REAL'),('trust_grade','VARCHAR(2)'),
                        ('trust_risk_level','VARCHAR(10)'),('trust_dimensions','JSONB'),
                        ('trust_scored_at','TIMESTAMP')]:
            cur.execute(f"DO $$ BEGIN ALTER TABLE agents ADD COLUMN {col} {ct}; EXCEPTION WHEN duplicate_column THEN NULL; END $$;")
    conn.commit()
    print("  Done")

    print("\n[2/4] Computing author counts + loading contributor metrics...")
    author_counts = {}
    with conn.cursor() as cur:
        cur.execute("SELECT author, COUNT(*) FROM agents WHERE author IS NOT NULL AND author != '' GROUP BY author")
        for row in cur:
            author_counts[row[0]] = row[1]
    print(f"  {len(author_counts):,} authors")

    # Load contributor metrics (from GitHub collector)
    contrib_map = {}
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT agent_id, active_contributors_6mo, total_contributors, top_contributor_pct, contributor_tier FROM contributor_metrics")
            for row in cur:
                contrib_map[str(row['agent_id'])] = dict(row)
        print(f"  {len(contrib_map):,} contributor metrics loaded")
    except Exception as e:
        print(f"  No contributor metrics table: {e}")

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM agents")
        total = cur.fetchone()[0]

    # Use OFFSET/LIMIT batching instead of named cursor to avoid cursor invalidation
    print(f"\n[3/4] Scoring {total:,} agents...")
    scored = 0
    grade_dist = {}
    risk_dist = {}
    dim_sums = {k: 0.0 for k in W}
    score_sum = 0.0
    start = time.time()

    offset = 0
    while offset < total:
        # Read a batch
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("""
                SELECT id, name, source, agent_type, stars, forks, downloads,
                       license, description, author, last_source_update,
                       capabilities, is_verified, compliance_score,
                       trust_components, raw_metadata, category, invocation
                FROM agents
                ORDER BY id
                LIMIT %s OFFSET %s
            """, (BATCH_SIZE, offset))
            rows = cur.fetchall()

        if not rows:
            break

        batch = []
        for agent in rows:
            ac = author_counts.get(agent['author'] or '', 0)
            contrib = contrib_map.get(str(agent['id']))
            score, grade, risk_level, dims = compute(agent, ac, contrib)
            batch.append((score, grade, risk_level, json.dumps(dims), NOW, agent['id']))

            grade_dist[grade] = grade_dist.get(grade, 0) + 1
            risk_dist[risk_level] = risk_dist.get(risk_level, 0) + 1
            score_sum += score
            for k in dims:
                dim_sums[k] += dims[k]
            scored += 1

        # Write batch
        with conn.cursor() as cur:
            execute_values(cur, """
                UPDATE agents SET
                    trust_score_v2 = data.score,
                    trust_grade = data.grade,
                    trust_risk_level = data.risk_level,
                    trust_dimensions = data.dims::jsonb,
                    trust_scored_at = data.scored_at
                FROM (VALUES %s) AS data(score, grade, risk_level, dims, scored_at, id)
                WHERE agents.id = data.id
            """, batch, template="(%s::real, %s, %s, %s, %s, %s::uuid)")
        conn.commit()

        offset += BATCH_SIZE
        elapsed = time.time() - start
        rate = scored / elapsed if elapsed > 0 else 0
        eta = (total - scored) / rate / 60 if rate > 0 else 0
        pct = scored * 100 / total
        print(f"\r  {scored:>10,} / {total:,} ({pct:.1f}%) | {rate:.0f}/sec | ETA {eta:.1f}min", end='', flush=True)

    elapsed = time.time() - start
    avg = score_sum / scored if scored > 0 else 0

    print(f"\n\n{'=' * 65}")
    print(f"  RESULTS — {scored:,} agents in {elapsed:.1f}s ({scored/elapsed:.0f}/sec)")
    print(f"  Average Trust Score: {avg:.1f}/100")
    print(f"{'=' * 65}")

    print(f"\n  -- Dimension Averages --")
    for k in ['security','compliance','maintenance','popularity','ecosystem']:
        a = dim_sums[k] / scored if scored > 0 else 0
        print(f"    {k:>12}: {a:5.1f}/100  (weight: {int(W[k]*100)}%)")

    print(f"\n  -- Grade Distribution --")
    for g in ['A+','A','B','C','D','E','F']:
        c = grade_dist.get(g, 0)
        p = c * 100 / scored if scored > 0 else 0
        print(f"    {g:>2}: {c:>10,} ({p:5.1f}%) {'#' * int(p/2)}")

    print(f"\n  -- Risk Distribution --")
    for r in ['low','medium','high','critical']:
        c = risk_dist.get(r, 0)
        p = c * 100 / scored if scored > 0 else 0
        print(f"    {r:>8}: {c:>10,} ({p:5.1f}%)")

    print(f"\n[4/4] Creating indexes...")
    with conn.cursor() as cur:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_trust_v2 ON agents (trust_score_v2 DESC NULLS LAST)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_trust_grade ON agents (trust_grade)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_trust_risk ON agents (trust_risk_level)")
    conn.commit()
    print("  Done")

    print(f"\n  -- Top 15 Trusted Agents --")
    with conn.cursor() as cur:
        cur.execute("""SELECT name, agent_type, trust_score_v2, trust_grade, trust_dimensions
            FROM agents WHERE trust_score_v2 IS NOT NULL ORDER BY trust_score_v2 DESC LIMIT 15""")
        for i, (name, at, sc, gr, dm) in enumerate(cur, 1):
            d = dm if isinstance(dm, dict) else json.loads(dm) if dm else {}
            print(f"    {i:>2}. {gr:>2} {sc:5.1f}  {name:<35} [{at}] S:{d.get('security',0)} C:{d.get('compliance',0)} M:{d.get('maintenance',0)} P:{d.get('popularity',0)} E:{d.get('ecosystem',0)}")

    print(f"\n  -- Bottom 10 --")
    with conn.cursor() as cur:
        cur.execute("""SELECT name, agent_type, trust_score_v2, trust_grade
            FROM agents WHERE trust_score_v2 IS NOT NULL ORDER BY trust_score_v2 ASC LIMIT 10""")
        for i, (n, at, sc, gr) in enumerate(cur, 1):
            print(f"    {i:>2}. {gr:>2} {sc:5.1f}  {n:<35} [{at}]")

    print(f"\n  -- MCP Server Stats --")
    with conn.cursor() as cur:
        cur.execute("""SELECT COUNT(*), ROUND(AVG(trust_score_v2)::numeric,1),
            COUNT(CASE WHEN trust_grade IN ('A+','A') THEN 1 END),
            COUNT(CASE WHEN trust_grade='B' THEN 1 END),
            COUNT(CASE WHEN trust_grade='C' THEN 1 END),
            COUNT(CASE WHEN trust_grade IN ('D','E','F') THEN 1 END)
            FROM agents WHERE agent_type='mcp_server'""")
        r = cur.fetchone()
        print(f"    Total: {r[0]:,}  Avg: {r[1]}  A+/A: {r[2]:,}  B: {r[3]:,}  C: {r[4]:,}  D/E/F: {r[5]:,}")

    print(f"\n{'=' * 65}")
    print(f"  DONE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 65}")
    conn.close()

if __name__ == '__main__':
    main()
