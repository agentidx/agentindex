#!/usr/bin/env python3
"""
Nerq Perplexity Optimizer — Analyze Perplexity crawl patterns vs ChatGPT.
Identifies Perplexity-specific demand gaps and optimization opportunities.

Run: python3 scripts/yield_perplexity.py [hours]
"""

import os
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, os.path.expanduser("~/agentindex"))
from scripts.yield_tracker import _classify_pattern
from scripts.reach_dashboard import extract_slugs

ANALYTICS_DB = os.path.expanduser("~/agentindex/logs/analytics.db")


def analyze(hours=24):
    print(f"=== Perplexity Analysis — {hours}h ===")
    conn = sqlite3.connect(ANALYTICS_DB)

    # Bot comparison: Perplexity vs ChatGPT
    bots = {}
    for bot_name in ("Perplexity", "ChatGPT", "Claude", "ByteDance"):
        rows = conn.execute(f"""
            SELECT path, status, query_string, COUNT(*) as hits
            FROM requests
            WHERE bot_name = ? AND ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-{int(hours)} hours')
            GROUP BY path, status, query_string
        """, (bot_name,)).fetchall()

        pattern_stats = defaultdict(lambda: {"200": 0, "404": 0})
        entity_stats = defaultdict(int)
        total_200 = sum(h for _, s, _, h in rows if s == 200)
        total_404 = sum(h for _, s, _, h in rows if s == 404)

        for path, status, qs, hits in rows:
            pat = _classify_pattern(path)
            if status == 200:
                pattern_stats[pat]["200"] += hits
            else:
                pattern_stats[pat]["404"] += hits
            for slug in (extract_slugs(path, qs) or []):
                if slug and len(slug) >= 2:
                    entity_stats[slug.strip().lower()] += hits

        bots[bot_name] = {
            "total_200": total_200,
            "total_404": total_404,
            "efficiency": total_200 / max(total_200 + total_404, 1) * 100,
            "patterns": dict(pattern_stats),
            "top_entities": sorted(entity_stats.items(), key=lambda x: -x[1])[:20],
            "unique_entities": len(entity_stats),
        }

    conn.close()

    # Print comparison
    print(f"\n{'='*70}")
    print(f"BOT COMPARISON — {hours}h")
    print(f"{'='*70}")
    print(f"{'Bot':<15} {'Citations':>10} {'404s':>8} {'Efficiency':>10} {'Entities':>10}")
    for bot, data in sorted(bots.items(), key=lambda x: -x[1]["total_200"]):
        print(f"  {bot:<13} {data['total_200']:>10,} {data['total_404']:>8,} {data['efficiency']:>9.1f}% {data['unique_entities']:>10,}")

    # Pattern comparison
    print(f"\n{'='*70}")
    print(f"PATTERN COMPARISON: Perplexity vs ChatGPT")
    print(f"{'='*70}")
    all_patterns = set()
    for b in bots.values():
        all_patterns.update(b["patterns"].keys())

    print(f"{'Pattern':<22} {'Perplexity':>10} {'ChatGPT':>10} {'Ratio':>8}")
    for pat in sorted(all_patterns, key=lambda p: -(bots.get("Perplexity", {}).get("patterns", {}).get(p, {}).get("200", 0))):
        p_cit = bots.get("Perplexity", {}).get("patterns", {}).get(pat, {}).get("200", 0)
        c_cit = bots.get("ChatGPT", {}).get("patterns", {}).get(pat, {}).get("200", 0)
        ratio = p_cit / max(c_cit, 1)
        if p_cit > 50 or c_cit > 50:
            print(f"  {pat:<20} {p_cit:>10,} {c_cit:>10,} {ratio:>7.1f}x")

    # Perplexity unique demand (entities Perplexity cites but ChatGPT doesn't)
    p_entities = set(s for s, _ in bots.get("Perplexity", {}).get("top_entities", []))
    c_entities = set(s for s, _ in bots.get("ChatGPT", {}).get("top_entities", []))
    p_unique = p_entities - c_entities

    print(f"\n{'='*70}")
    print(f"PERPLEXITY-ONLY TOP ENTITIES (not in ChatGPT top 20)")
    print(f"{'='*70}")
    p_ent_dict = dict(bots.get("Perplexity", {}).get("top_entities", []))
    for slug in sorted(p_unique, key=lambda s: -p_ent_dict.get(s, 0))[:10]:
        print(f"  {slug:<50} {p_ent_dict[slug]:>5} citations")

    # Perplexity 404s (specific demand gaps)
    print(f"\n{'='*70}")
    print(f"PERPLEXITY 404s (demand gaps)")
    print(f"{'='*70}")
    p_patterns = bots.get("Perplexity", {}).get("patterns", {})
    for pat in sorted(p_patterns.keys(), key=lambda p: -p_patterns[p].get("404", 0)):
        f = p_patterns[pat].get("404", 0)
        if f > 0:
            print(f"  {pat:<20} {f:>6} 404s")


if __name__ == "__main__":
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    analyze(hours)
