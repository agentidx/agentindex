"""
Safety Improver
===============
Finds safety pages with high Google traffic but low word count,
and logs recommendations for content improvement.

Runs weekly (Sundays at 10:00) via LaunchAgent.

Usage:
    python -m agentindex.intelligence.safety_improver
"""

import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # agentindex repo root
ANALYTICS_DB = BASE_DIR / "logs" / "analytics.db"
AGENTS_DB = BASE_DIR / "agents.db"
TMP_ANALYTICS = Path("/tmp/safety_improver_analytics.db")
TMP_AGENTS = Path("/tmp/safety_improver_agents.db")
OUTPUT_PATH = BASE_DIR / "data" / "safety_improvement_recommendations.json"


def copy_dbs():
    """Copy DBs to /tmp to avoid holding locks."""
    for src, dst in [(ANALYTICS_DB, TMP_ANALYTICS), (AGENTS_DB, TMP_AGENTS)]:
        if not src.exists():
            print(f"[WARN] DB not found: {src} — skipping")
            continue
        shutil.copy2(src, dst)
        print(f"[OK] Copied {src} -> {dst} ({dst.stat().st_size / 1024:.0f} KB)")


def get_safety_traffic():
    """Get safety pages ranked by Google organic traffic."""
    if not TMP_ANALYTICS.exists():
        print("[WARN] No analytics DB copy available")
        return []

    conn = sqlite3.connect(str(TMP_ANALYTICS))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT path, COUNT(DISTINCT ip) as visitors
            FROM requests
            WHERE referrer LIKE '%google%' AND is_bot = 0
            AND (path LIKE '/is-%safe' OR path LIKE '/safe/%')
            AND ts > strftime('%Y-%m-%dT%H:%M:%f', 'now', '-30 days')
            GROUP BY path ORDER BY visitors DESC LIMIT 50
        """).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[ERROR] Traffic query failed: {e}")
        return []
    finally:
        conn.close()


def estimate_word_count(path):
    """Estimate word count for a safety page by checking templates/static content."""
    # Check if there's a matching template or static file
    slug = path.strip("/").split("/")[-1] if "/" in path else path.strip("/")

    # Check various template locations
    template_dirs = [
        BASE_DIR / "agentindex" / "templates",
        BASE_DIR / "agentindex" / "static",
        BASE_DIR / "static",
    ]

    for tdir in template_dirs:
        for ext in [".html", ".jinja2", ".j2"]:
            candidate = tdir / f"{slug}{ext}"
            if candidate.exists():
                text = candidate.read_text(errors="ignore")
                # Strip HTML tags roughly
                import re
                text = re.sub(r"<[^>]+>", " ", text)
                return len(text.split())

    # If we can't find the file, return -1 (unknown)
    return -1


def find_improvement_candidates(traffic_data):
    """Find pages with most traffic but lowest word count."""
    candidates = []
    for item in traffic_data:
        path = item["path"]
        visitors = item["visitors"]
        word_count = estimate_word_count(path)
        candidates.append({
            "path": path,
            "visitors_30d": visitors,
            "word_count": word_count,
        })

    # Sort: prioritize high traffic + low word count
    # Pages with unknown word count (-1) get medium priority
    def sort_key(c):
        wc = c["word_count"] if c["word_count"] > 0 else 500  # assume medium for unknowns
        return -c["visitors_30d"] / max(wc, 1)

    candidates.sort(key=sort_key)
    return candidates[:10]


def main():
    print(f"=== Safety Improver — {datetime.now().isoformat()} ===")

    copy_dbs()
    traffic = get_safety_traffic()

    if not traffic:
        print("[INFO] No safety page traffic data found. Nothing to recommend.")
        return

    print(f"[INFO] Found traffic data for {len(traffic)} safety pages")

    candidates = find_improvement_candidates(traffic)

    print(f"\n{'='*60}")
    print(f"TOP 10 PAGES TO IMPROVE (high traffic, low word count)")
    print(f"{'='*60}")
    for i, c in enumerate(candidates, 1):
        wc_str = str(c["word_count"]) if c["word_count"] >= 0 else "unknown"
        print(f"  {i:2d}. {c['path']}")
        print(f"      visitors (30d): {c['visitors_30d']}  |  word count: {wc_str}")

    # Save to JSON
    output = {
        "generated_at": datetime.now().isoformat(),
        "recommendations": candidates,
        "total_safety_pages_with_traffic": len(traffic),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\n[OK] Saved recommendations to {OUTPUT_PATH}")

    # Cleanup
    for tmp in [TMP_ANALYTICS, TMP_AGENTS]:
        if tmp.exists():
            tmp.unlink()


if __name__ == "__main__":
    main()
