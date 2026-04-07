#!/usr/bin/env python3
"""
Nerq Yield Tracker — Measures citation yield per entity, registry, pattern, and AI bot.
Stores snapshots in reach_history.db for trend analysis.

Run: python3 scripts/yield_tracker.py [hours]
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

ANALYTICS_DB = os.path.expanduser("~/agentindex/logs/analytics.db")
HISTORY_DB = os.path.expanduser("~/agentindex/data/reach_history.db")
PSQL = "/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql"

# Import slug extraction from reach_dashboard
sys.path.insert(0, os.path.expanduser("~/agentindex"))
from scripts.reach_dashboard import extract_slugs, classify_bot


def _classify_pattern(path):
    """Classify URL into pattern type."""
    if not path:
        return "other"
    p = path.split("?")[0]
    # Strip language prefix
    m = re.match(r"^/([a-z]{2})/(.+)$", p)
    if m and len(m.group(1)) == 2:
        p = "/" + m.group(2)
        lang_prefix = True
    else:
        lang_prefix = False

    if p.startswith("/safe/"): return "safe" + (" (l10n)" if lang_prefix else "")
    if p.startswith("/is-"): return "is-X-safe" + (" (l10n)" if lang_prefix else "")
    if p.startswith("/compare/"): return "compare"
    if p.startswith("/review/"): return "review"
    if p.startswith("/alternatives/"): return "alternatives"
    if p.startswith("/privacy/"): return "privacy"
    if p.startswith("/v1/preflight"): return "preflight"
    if p.startswith("/guide/"): return "guide"
    if p.startswith("/predict/"): return "predict"
    if p.startswith("/model/"): return "model"
    if p.startswith("/profile/"): return "profile"
    if p.startswith("/does-"): return "does-X"
    if p.startswith("/was-"): return "was-X"
    if p.startswith("/who-"): return "who-X"
    if p.startswith("/what-"): return "what-X"
    if p.startswith("/pros-"): return "pros-cons"
    if p.startswith("/token/"): return "token"
    if p.startswith("/dataset/"): return "dataset"
    return "other"


def _get_registry_map(slugs):
    """Batch lookup registries from PostgreSQL."""
    if not slugs:
        return {}
    reg_map = {}
    for i in range(0, len(slugs), 500):
        batch = list(slugs)[i:i+500]
        slug_list = ",".join(f"'{s.replace(chr(39), '')}'" for s in batch)
        try:
            result = subprocess.run(
                [PSQL, "-d", "agentindex", "-t", "-A", "-F", "|", "-c",
                 f"SELECT DISTINCT ON (slug) slug, registry, trust_score, is_king, downloads "
                 f"FROM software_registry WHERE slug IN ({slug_list}) "
                 f"ORDER BY slug, is_king DESC NULLS LAST, trust_score DESC NULLS LAST"],
                capture_output=True, text=True, timeout=15
            )
            for line in result.stdout.strip().split("\n"):
                if "|" not in line:
                    continue
                parts = line.split("|")
                if len(parts) >= 3:
                    reg_map[parts[0].strip()] = {
                        "registry": parts[1].strip(),
                        "trust_score": float(parts[2]) if parts[2].strip() else 0,
                        "is_king": parts[3].strip() == "t" if len(parts) > 3 else False,
                        "downloads": int(parts[4]) if len(parts) > 4 and parts[4].strip().isdigit() else 0,
                    }
        except Exception as e:
            print(f"  PG lookup batch failed: {e}")
    return reg_map


def _classify_tier(registry, is_king, downloads):
    """Classify entity into yield tier."""
    if registry in ("ai_tool", "saas"):
        return "Tier 1 (AI+SaaS)"
    if registry in ("vpn", "country", "city", "charity"):
        return "Tier 1 (High-value)"
    if registry in ("wordpress", "chrome", "ios", "android", "steam", "firefox", "vscode"):
        return "Tier 2 (Apps+Extensions)"
    if is_king:
        return "Tier 2 (Kings)"
    if registry in ("npm", "pypi", "crates", "nuget", "go", "packagist", "gems", "homebrew"):
        if downloads and downloads > 10000:
            return "Tier 3 (Popular packages)"
        return "Tier 4 (Long tail)"
    if registry == "website":
        return "Tier 3 (Websites)"
    return "Tier 4 (Long tail)"


def run_yield_analysis(hours=24):
    """Run full yield analysis and save snapshots."""
    print(f"=== Yield Tracker — {hours}h analysis ===")

    conn = sqlite3.connect(ANALYTICS_DB)
    conn.row_factory = sqlite3.Row

    # Get all AI bot requests (200 + 404)
    rows = conn.execute(f"""
        SELECT path, bot_name, status, query_string
        FROM requests
        WHERE is_ai_bot = 1 AND ts >= datetime('now', '-{int(hours)} hours')
    """).fetchall()
    conn.close()

    # Aggregate
    entity_citations = defaultdict(lambda: {"200": 0, "404": 0, "bots": defaultdict(int), "patterns": defaultdict(int)})
    pattern_stats = defaultdict(lambda: {"200": 0, "404": 0, "entities": set()})
    bot_stats = defaultdict(lambda: {"200": 0, "404": 0})
    total_200 = 0
    total_404 = 0

    for row in rows:
        path = row["path"] or ""
        bot = classify_bot(row["bot_name"])
        status = row["status"]
        qs = row["query_string"] or ""
        pattern = _classify_pattern(path)

        if status == 200:
            total_200 += 1
            bot_stats[bot]["200"] += 1
            pattern_stats[pattern]["200"] += 1
        elif status == 404:
            total_404 += 1
            bot_stats[bot]["404"] += 1
            pattern_stats[pattern]["404"] += 1

        slugs = extract_slugs(path, qs)
        for slug in (slugs or []):
            if not slug or len(slug) < 2:
                continue
            slug = slug.strip().lower()
            d = entity_citations[slug]
            if status == 200:
                d["200"] += 1
            elif status == 404:
                d["404"] += 1
            d["bots"][bot] += 1
            d["patterns"][pattern] += 1
            pattern_stats[pattern]["entities"].add(slug)

    print(f"  Total: {total_200:,} citations + {total_404:,} 404s = {total_200+total_404:,} AI requests")
    print(f"  Entities: {len(entity_citations):,} unique")

    # Enrich with registry data
    reg_map = _get_registry_map(set(entity_citations.keys()))
    print(f"  Registry matches: {len(reg_map):,}")

    # ── Yield per registry ──
    registry_yield = defaultdict(lambda: {"entities": 0, "citations": 0, "404s": 0, "kings": 0})
    tier_yield = defaultdict(lambda: {"entities": 0, "citations": 0, "404s": 0})

    for slug, data in entity_citations.items():
        info = reg_map.get(slug, {})
        reg = info.get("registry", "unknown")
        is_king = info.get("is_king", False)
        downloads = info.get("downloads", 0)
        tier = _classify_tier(reg, is_king, downloads)

        ry = registry_yield[reg]
        ry["entities"] += 1
        ry["citations"] += data["200"]
        ry["404s"] += data["404"]
        if is_king:
            ry["kings"] += 1

        ty = tier_yield[tier]
        ty["entities"] += 1
        ty["citations"] += data["200"]
        ty["404s"] += data["404"]

    # ── Save snapshots ──
    hist = sqlite3.connect(HISTORY_DB)
    hist.execute("""CREATE TABLE IF NOT EXISTS yield_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_ts TEXT NOT NULL,
        granularity TEXT NOT NULL,
        key TEXT NOT NULL,
        citations_count INTEGER,
        miss_count INTEGER,
        entity_count INTEGER,
        yield_per_entity REAL,
        metadata TEXT
    )""")
    hist.execute("CREATE INDEX IF NOT EXISTS idx_ys_ts ON yield_snapshots(snapshot_ts)")
    hist.execute("CREATE INDEX IF NOT EXISTS idx_ys_gran ON yield_snapshots(granularity, key)")

    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    # Registry snapshots
    for reg, data in sorted(registry_yield.items(), key=lambda x: -x[1]["citations"]):
        hist.execute("INSERT INTO yield_snapshots (snapshot_ts, granularity, key, citations_count, miss_count, entity_count, yield_per_entity, metadata) VALUES (?,?,?,?,?,?,?,?)",
                     (now, "registry", reg, data["citations"], data["404s"], data["entities"],
                      round(data["citations"] / max(data["entities"], 1), 2),
                      json.dumps({"kings": data["kings"]})))

    # Tier snapshots
    for tier, data in sorted(tier_yield.items(), key=lambda x: -x[1]["citations"]):
        hist.execute("INSERT INTO yield_snapshots (snapshot_ts, granularity, key, citations_count, miss_count, entity_count, yield_per_entity) VALUES (?,?,?,?,?,?,?)",
                     (now, "tier", tier, data["citations"], data["404s"], data["entities"],
                      round(data["citations"] / max(data["entities"], 1), 2)))

    # Pattern snapshots
    for pattern, data in sorted(pattern_stats.items(), key=lambda x: -x[1]["200"]):
        entity_count = len(data["entities"])
        hist.execute("INSERT INTO yield_snapshots (snapshot_ts, granularity, key, citations_count, miss_count, entity_count, yield_per_entity) VALUES (?,?,?,?,?,?,?)",
                     (now, "pattern", pattern, data["200"], data["404"], entity_count,
                      round(data["200"] / max(entity_count, 1), 2)))

    # Bot snapshots
    for bot, data in sorted(bot_stats.items(), key=lambda x: -x[1]["200"]):
        hist.execute("INSERT INTO yield_snapshots (snapshot_ts, granularity, key, citations_count, miss_count, entity_count) VALUES (?,?,?,?,?,?)",
                     (now, "bot", bot, data["200"], data["404"], 0))

    # Top 50 entity snapshots
    top_entities = sorted(entity_citations.items(), key=lambda x: -x[1]["200"])[:50]
    for slug, data in top_entities:
        info = reg_map.get(slug, {})
        hist.execute("INSERT INTO yield_snapshots (snapshot_ts, granularity, key, citations_count, miss_count, entity_count, metadata) VALUES (?,?,?,?,?,?,?)",
                     (now, "entity", slug, data["200"], data["404"], 1,
                      json.dumps({"registry": info.get("registry", "unknown"),
                                  "is_king": info.get("is_king", False),
                                  "top_bot": max(data["bots"].items(), key=lambda x: x[1])[0] if data["bots"] else ""})))

    hist.commit()
    hist.close()

    # ── Print report ──
    print(f"\n{'='*60}")
    print(f"YIELD PER TIER")
    print(f"{'='*60}")
    print(f"{'Tier':<30} {'Entities':>8} {'Citations':>10} {'404s':>8} {'Yield/Entity':>12}")
    for tier, data in sorted(tier_yield.items(), key=lambda x: -x[1]["citations"]):
        yld = data["citations"] / max(data["entities"], 1)
        print(f"  {tier:<28} {data['entities']:>8,} {data['citations']:>10,} {data['404s']:>8,} {yld:>12.1f}")

    print(f"\n{'='*60}")
    print(f"YIELD PER REGISTRY (top 15)")
    print(f"{'='*60}")
    print(f"{'Registry':<15} {'Entities':>8} {'Citations':>10} {'404s':>6} {'Yield':>8} {'Kings':>6}")
    for reg, data in sorted(registry_yield.items(), key=lambda x: -x[1]["citations"])[:15]:
        yld = data["citations"] / max(data["entities"], 1)
        print(f"  {reg:<13} {data['entities']:>8,} {data['citations']:>10,} {data['404s']:>6,} {yld:>8.1f} {data['kings']:>6,}")

    print(f"\n{'='*60}")
    print(f"YIELD PER PATTERN")
    print(f"{'='*60}")
    print(f"{'Pattern':<20} {'Citations':>10} {'404s':>8} {'Entities':>8} {'Yield/Entity':>12}")
    for pattern, data in sorted(pattern_stats.items(), key=lambda x: -x[1]["200"])[:15]:
        ec = len(data["entities"])
        yld = data["200"] / max(ec, 1)
        print(f"  {pattern:<18} {data['200']:>10,} {data['404']:>8,} {ec:>8,} {yld:>12.1f}")

    print(f"\n{'='*60}")
    print(f"YIELD PER BOT")
    print(f"{'='*60}")
    for bot, data in sorted(bot_stats.items(), key=lambda x: -x[1]["200"]):
        eff = data["200"] / max(data["200"] + data["404"], 1) * 100
        print(f"  {bot:<15} {data['200']:>8,} citations  {data['404']:>6,} 404s  ({eff:.0f}% efficiency)")

    # Kings vs non-kings
    kings_cit = sum(d["citations"] for r, d in registry_yield.items() if d["kings"] > 0)
    kings_ent = sum(d["kings"] for d in registry_yield.values())
    total_cit = sum(d["citations"] for d in registry_yield.values())
    total_ent = sum(d["entities"] for d in registry_yield.values())
    print(f"\n{'='*60}")
    print(f"KINGS vs NON-KINGS")
    print(f"{'='*60}")
    print(f"  Kings: {kings_ent:,} entities → hard to measure per-king citations from this data")
    print(f"  Total: {total_ent:,} entities → {total_cit:,} citations")
    print(f"  Global yield: {total_cit / max(total_ent, 1):.1f} citations/entity")

    print(f"\nSnapshots saved to {HISTORY_DB}")
    return entity_citations, registry_yield, tier_yield


if __name__ == "__main__":
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    run_yield_analysis(hours)
