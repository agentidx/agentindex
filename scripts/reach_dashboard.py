#!/usr/bin/env python3
"""
Nerq Reach Dashboard — Aggregate AI reach per entity.

Reads analytics.db (SQLite) for AI bot requests,
extracts entity slugs from paths, cross-references with
software_registry (PostgreSQL), and outputs a JSON dashboard.

Run: python3 scripts/reach_dashboard.py [hours]
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

ANALYTICS_DB = os.path.expanduser("~/agentindex/logs/analytics.db")
PSQL_PATH = "/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql"
OUTPUT_JSON = os.path.expanduser("~/agentindex/data/reach_dashboard.json")
HISTORY_DB = os.path.expanduser("~/agentindex/data/reach_history.db")


def extract_slugs(path, query_string=None):
    """Extract entity slug(s) from a URL path. Returns list of slugs.
    Covers all 36+ URL patterns including localized routes.
    """
    if not path:
        return []

    path_clean = path.split("?")[0].rstrip("/")

    # ── Strip language prefix: /{lang}/... → /... ──
    # Matches /sv/, /es/, /fr/, /de/, /ja/, /ko/, /zh/, /ar/, etc.
    m = re.match(r"^/([a-z]{2})/(.+)$", path_clean)
    if m and m.group(1) in ("sv", "es", "fr", "de", "pt", "it", "ja", "ko",
                             "zh", "ar", "hi", "ru", "nl", "pl", "tr", "vi",
                             "th", "id", "da"):
        path_clean = "/" + m.group(2)

    # ── Simple prefix patterns: /{prefix}/{slug} ──
    _PREFIX_PATTERNS = [
        ("/safe/", 6), ("/review/", 8), ("/alternatives/", 14),
        ("/privacy/", 9), ("/pros-cons/", 11), ("/token/", 7),
        ("/model/", 7), ("/predict/", 9), ("/profile/", 9),
        ("/dataset/", 9),
    ]
    for prefix, length in _PREFIX_PATTERNS:
        if path_clean.startswith(prefix):
            s = path_clean[length:].split("/")[0]
            return [s] if s else []

    # ── /compare/{a}-vs-{b} ──
    m = re.match(r"^/compare/(.+)-vs-(.+)$", path_clean)
    if m:
        return [m.group(1), m.group(2)]

    # ── /is-{slug}-{suffix} (safe, legit, a-scam, dead, secure, ..., safe-for-kids) ──
    m = re.match(r"^/is-(.+?)-(safe|legit|a-scam|dead|secure|trustworthy|good|safe-for-kids)$", path_clean)
    if m:
        return [m.group(1)]

    # ── /does-{slug}-sell-your-data ──
    m = re.match(r"^/does-(.+?)-sell-your-data$", path_clean)
    if m:
        return [m.group(1)]

    # ── /was-{slug}-hacked ──
    m = re.match(r"^/was-(.+?)-hacked$", path_clean)
    if m:
        return [m.group(1)]

    # ── /who-owns/{slug} or /who-owns-{slug} or /who-makes-{slug} ──
    for p in ("/who-owns/", "/who-makes/"):
        if path_clean.startswith(p):
            s = path_clean[len(p):].split("/")[0]
            return [s] if s else []
    m = re.match(r"^/who-(?:owns|makes)-(.+)$", path_clean)
    if m:
        return [m.group(1)]

    # ── /what-is/{slug} or /what-is-{slug} ──
    if path_clean.startswith("/what-is/"):
        s = path_clean[9:].split("/")[0]
        return [s] if s else []
    m = re.match(r"^/what-is-(.+)$", path_clean)
    if m:
        return [m.group(1)]

    # ── /guide/use-{slug}-safely or /guide/{slug} ──
    if path_clean.startswith("/guide/"):
        g = path_clean[7:]
        m = re.match(r"^use-(.+?)-safely$", g)
        if m:
            return [m.group(1)]
        return [g.split("/")[0]] if g else []

    # ── /v1/preflight?target={slug} ──
    if path_clean == "/v1/preflight" or path.startswith("/v1/preflight?"):
        qs = query_string or ""
        if "?" in path:
            qs = path.split("?", 1)[1]
        params = parse_qs(qs)
        target = params.get("target", [None])[0]
        return [target] if target else []

    # ── /crash-prediction/{slug} ──
    if path_clean.startswith("/crash-prediction/"):
        s = path_clean[18:].split("/")[0]
        return [s] if s else []

    # ── /crypto/defi/{slug} ──
    if path_clean.startswith("/crypto/defi/"):
        s = path_clean[13:].split("/")[0]
        return [s] if s else []

    # ── Registry-specific: /npm/{slug}, /pypi/{slug}, etc. ──
    for prefix in ("/npm/", "/pypi/", "/crate/", "/crates/", "/gem/", "/gems/",
                   "/go/", "/nuget/", "/packagist/",
                   "/wordpress/", "/chrome/", "/firefox/", "/vscode/",
                   "/homebrew/", "/steam/", "/ios/", "/android/"):
        if path_clean.startswith(prefix):
            s = path_clean[len(prefix):].split("/")[0]
            return [s] if s else []

    # ── /agent/{uuid} — skip UUIDs, not entity slugs ──
    # These are agent detail pages with UUIDs, not useful for reach

    return []


def classify_bot(bot_name):
    """Classify AI system from bot_name."""
    if not bot_name:
        return "Other AI"
    bn = bot_name.lower()
    if "chatgpt" in bn or "gpt" in bn or "openai" in bn:
        return "ChatGPT"
    if "claude" in bn or "anthropic" in bn:
        return "Claude"
    if "perplexity" in bn:
        return "Perplexity"
    if "bytedance" in bn:
        return "ByteDance"
    if "bing" in bn or "copilot" in bn:
        return "Copilot/Bing"
    if "gemini" in bn or "google" in bn:
        return "Gemini/Google"
    if "meta" in bn or "facebook" in bn:
        return "Meta AI"
    if "duckduck" in bn:
        return "DuckDuckGo"
    return "Other AI"


def aggregate_reach(hours=24):
    """Aggregate AI reach per entity from analytics.db."""
    conn = sqlite3.connect(ANALYTICS_DB)
    conn.row_factory = sqlite3.Row

    # Use SQLite datetime() for proper comparison (handles both T and space separators)
    cursor = conn.execute(f"""
        SELECT path, bot_name, ts, query_string
        FROM requests
        WHERE is_ai_bot = 1 AND status = 200
          AND ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-{int(hours)} hours')
    """)

    entity_data = defaultdict(lambda: {
        "total_citations": 0,
        "preflight_calls": 0,
        "by_system": defaultdict(int),
        "route_types": defaultdict(int),
    })

    total_rows = 0
    for row in cursor:
        total_rows += 1
        path = row["path"] or ""
        bot = row["bot_name"] or ""
        qs = row["query_string"] or ""

        slugs = extract_slugs(path, qs)
        if not slugs:
            continue

        ai_system = classify_bot(bot)
        is_preflight = path.startswith("/v1/preflight")

        # Classify route type
        route = "other"
        if "/safe/" in path: route = "safe"
        elif "/is-" in path: route = "is-X-safe"
        elif "/compare/" in path: route = "compare"
        elif "/review/" in path: route = "review"
        elif "/alternatives/" in path: route = "alternatives"
        elif "/privacy/" in path: route = "privacy"
        elif path.startswith("/v1/preflight"): route = "preflight"
        elif "/does-" in path: route = "does-X"
        elif "/was-" in path: route = "was-X"
        elif "/who-" in path: route = "who-X"
        elif "/what-" in path: route = "what-X"
        elif "/pros-" in path: route = "pros-cons"
        elif "/guide/" in path: route = "guide"
        elif "/predict/" in path: route = "predict"
        elif "/model/" in path: route = "model"
        elif "/profile/" in path: route = "profile"
        elif "/token/" in path: route = "token"
        elif "/dataset/" in path: route = "dataset"
        elif "/crash-" in path: route = "crash"

        for slug in slugs:
            if not slug:
                continue
            slug = slug.strip().lower()
            if len(slug) < 2 or len(slug) > 100:
                continue
            d = entity_data[slug]
            d["total_citations"] += 1
            if is_preflight:
                d["preflight_calls"] += 1
            d["by_system"][ai_system] += 1
            d["route_types"][route] += 1

    conn.close()
    print(f"Processed {total_rows} AI bot requests → {len(entity_data)} unique entities")
    return dict(entity_data)


def enrich_with_registry(entity_data):
    """Cross-reference with software_registry in PostgreSQL."""
    slugs = list(entity_data.keys())
    if not slugs:
        return entity_data

    # Batch in groups of 500
    for i in range(0, len(slugs), 500):
        batch = slugs[i:i+500]
        slug_list = ",".join(f"'{s.replace(chr(39), '')}'" for s in batch)

        query = f"""
        SELECT DISTINCT ON (slug) slug, name, registry, trust_score, COALESCE(downloads, 0), is_king
        FROM software_registry
        WHERE slug IN ({slug_list})
        ORDER BY slug, is_king DESC NULLS LAST, trust_score DESC NULLS LAST;
        """

        try:
            result = subprocess.run(
                [PSQL_PATH, "-d", "agentindex", "-t", "-A", "-F", "|", "-c", query],
                capture_output=True, text=True, timeout=15
            )
            for line in result.stdout.strip().split("\n"):
                if not line or "|" not in line:
                    continue
                parts = line.split("|")
                if len(parts) >= 4:
                    slug = parts[0].strip()
                    if slug in entity_data:
                        entity_data[slug]["name"] = parts[1].strip()
                        entity_data[slug]["registry"] = parts[2].strip()
                        entity_data[slug]["trust_score"] = parts[3].strip()
                        entity_data[slug]["downloads"] = int(parts[4].strip()) if len(parts) > 4 and parts[4].strip().isdigit() else 0
                        entity_data[slug]["is_king"] = parts[5].strip() == "t" if len(parts) > 5 else False
        except Exception as e:
            print(f"PostgreSQL batch {i//500} failed: {e}")

    return entity_data


def save_daily_snapshot(dashboard):
    """Save daily snapshot for trend analysis."""
    conn = sqlite3.connect(HISTORY_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_reach (
            date TEXT PRIMARY KEY,
            total_citations INTEGER,
            total_preflight INTEGER,
            total_entities INTEGER,
            estimated_reach INTEGER,
            by_ai_system TEXT,
            by_registry TEXT,
            top_entities TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_daily_reach (
            date TEXT,
            slug TEXT,
            name TEXT,
            registry TEXT,
            citations INTEGER,
            preflight INTEGER,
            estimated_reach INTEGER,
            by_ai_system TEXT,
            PRIMARY KEY (date, slug)
        )
    """)

    today = datetime.utcnow().strftime("%Y-%m-%d")
    s = dashboard["summary"]

    conn.execute(
        "INSERT OR REPLACE INTO daily_reach VALUES (?,?,?,?,?,?,?,?)",
        (today, s["total_citations"], s["total_preflight"], s["total_entities_cited"],
         s["total_estimated_reach"], json.dumps(s.get("by_ai_system", {})),
         json.dumps(s.get("by_registry", {})),
         json.dumps([e["slug"] for e in dashboard["top_100_entities"][:20]]))
    )

    for e in dashboard["top_100_entities"]:
        conn.execute(
            "INSERT OR REPLACE INTO entity_daily_reach VALUES (?,?,?,?,?,?,?,?)",
            (today, e["slug"], e["name"], e["registry"], e["citations_24h"],
             e["preflight_calls_24h"], e["estimated_human_reach"],
             json.dumps(e.get("by_ai_system", {})))
        )

    conn.commit()
    conn.close()
    print(f"Daily snapshot saved for {today}")


def build_dashboard(hours=24):
    """Build complete dashboard data."""
    print(f"Aggregating reach data for last {hours} hours...")
    entity_data = aggregate_reach(hours)

    print("Enriching with registry data...")
    entity_data = enrich_with_registry(entity_data)

    HUMAN_REACH_MULTIPLIER = 1.0

    ranked = sorted(entity_data.items(), key=lambda x: x[1]["total_citations"], reverse=True)

    dashboard = {
        "generated_at": datetime.utcnow().isoformat(),
        "period_hours": hours,
        "summary": {
            "total_entities_cited": len(entity_data),
            "total_citations": sum(d["total_citations"] for _, d in ranked),
            "total_preflight": sum(d["preflight_calls"] for _, d in ranked),
            "total_estimated_reach": int(sum(d["total_citations"] * HUMAN_REACH_MULTIPLIER for _, d in ranked)),
            "by_ai_system": {},
            "by_registry": {},
            "by_route_type": {},
        },
        "top_100_entities": [],
    }

    system_totals = defaultdict(int)
    registry_totals = defaultdict(int)
    route_totals = defaultdict(int)

    for slug, data in ranked:
        for system, count in data["by_system"].items():
            system_totals[system] += count
        reg = data.get("registry", "unknown")
        registry_totals[reg] += data["total_citations"]
        for rt, count in data.get("route_types", {}).items():
            route_totals[rt] += count

    dashboard["summary"]["by_ai_system"] = dict(sorted(system_totals.items(), key=lambda x: -x[1]))
    dashboard["summary"]["by_registry"] = dict(sorted(registry_totals.items(), key=lambda x: -x[1]))
    dashboard["summary"]["by_route_type"] = dict(sorted(route_totals.items(), key=lambda x: -x[1]))

    for slug, data in ranked[:100]:
        entity = {
            "slug": slug,
            "name": data.get("name", slug.replace("-", " ").title()),
            "registry": data.get("registry", "unknown"),
            "trust_score": data.get("trust_score", "N/A"),
            "is_king": data.get("is_king", False),
            "citations_24h": data["total_citations"],
            "preflight_calls_24h": data["preflight_calls"],
            "estimated_human_reach": int(data["total_citations"] * HUMAN_REACH_MULTIPLIER),
            "by_ai_system": dict(sorted(data["by_system"].items(), key=lambda x: -x[1])),
            "top_routes": dict(sorted(data.get("route_types", {}).items(), key=lambda x: -x[1])[:5]),
        }
        dashboard["top_100_entities"].append(entity)

    # Save JSON
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(dashboard, f, indent=2)
    print(f"Dashboard saved to {OUTPUT_JSON}")

    # Save daily snapshot
    save_daily_snapshot(dashboard)

    # Print summary
    s = dashboard["summary"]
    print(f"\n{'='*60}")
    print(f"NERQ REACH DASHBOARD — Last {hours}h")
    print(f"{'='*60}")
    print(f"Entities cited:    {s['total_entities_cited']:,}")
    print(f"Total citations:   {s['total_citations']:,}")
    print(f"Preflight calls:   {s['total_preflight']:,}")
    print(f"Est. human reach:  {s['total_estimated_reach']:,}")
    print(f"\nBy AI system:")
    for system, count in sorted(system_totals.items(), key=lambda x: -x[1]):
        pct = round(100 * count / max(s["total_citations"], 1), 1)
        print(f"  {system:15s} {count:>8,}  ({pct}%)")
    print(f"\nBy registry (top 10):")
    for reg, count in sorted(registry_totals.items(), key=lambda x: -x[1])[:10]:
        print(f"  {reg:15s} {count:>8,}")
    print(f"\nTop 10 entities:")
    for e in dashboard["top_100_entities"][:10]:
        top_sys = next(iter(e["by_ai_system"]), "")
        print(f"  {e['name'][:35]:35s} ({e['registry']:8s}) {e['citations_24h']:>5,} citations  [{top_sys}]")

    return dashboard


if __name__ == "__main__":
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    build_dashboard(hours)
