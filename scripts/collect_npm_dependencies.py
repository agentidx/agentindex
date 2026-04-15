#!/usr/bin/env python3
"""
npm Dependency Graph Collector — Background batch job.

Fetches dependency data from npm registry for all npm packages in our DB.
Stores edges in dependency_edges table (Postgres).

Priority order: top packages by downloads first.
Rate limit: 1 request/second (polite, avoids npm rate limiting).

Usage:
    python3 scripts/collect_npm_dependencies.py              # run batch
    python3 scripts/collect_npm_dependencies.py --limit 100   # test with 100
    python3 scripts/collect_npm_dependencies.py --status      # show progress
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
from agentindex.db_config import get_write_dsn
PG_DSN = os.environ.get("DATABASE_URL") or get_write_dsn(fmt="psycopg2")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, "npm-dependency-collector.log")),
    ]
)
log = logging.getLogger("npm-deps")

RATE_LIMIT = 1.0  # seconds between requests
NPM_REGISTRY = "https://registry.npmjs.org"


def get_packages_to_process(conn, limit=None):
    """Get npm packages ordered by downloads, excluding already-processed."""
    cur = conn.cursor()
    cur.execute("""
        SELECT sr.name, sr.slug, sr.downloads
        FROM software_registry sr
        WHERE sr.registry = 'npm'
          AND sr.name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM dependency_edges de
              WHERE de.entity_from = sr.name AND de.registry = 'npm'
          )
        ORDER BY sr.downloads DESC NULLS LAST
        LIMIT %s
    """, (limit or 1000000,))
    rows = cur.fetchall()
    cur.close()
    return rows


def fetch_npm_metadata(package_name):
    """Fetch package metadata from npm registry."""
    # URL-encode scoped packages (@scope/name)
    encoded = package_name.replace("/", "%2f")
    url = f"{NPM_REGISTRY}/{encoded}"

    req = urllib.request.Request(url)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "NerqDependencyCollector/1.0 (+https://nerq.ai)")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return data
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        if e.code == 429:
            log.warning(f"Rate limited on {package_name}, sleeping 60s")
            time.sleep(60)
            return None
        log.warning(f"HTTP {e.code} for {package_name}")
        return None
    except Exception as e:
        log.warning(f"Error fetching {package_name}: {e}")
        return None


def extract_dependencies(data):
    """Extract all dependency types from npm package metadata."""
    if not data:
        return []

    latest_version = data.get("dist-tags", {}).get("latest")
    if not latest_version:
        return []

    version_data = data.get("versions", {}).get(latest_version, {})
    if not version_data:
        return []

    edges = []
    dep_types = {
        "dependencies": "direct",
        "devDependencies": "dev",
        "peerDependencies": "peer",
        "optionalDependencies": "optional",
    }

    for field, dep_type in dep_types.items():
        deps = version_data.get(field, {})
        if isinstance(deps, dict):
            for dep_name, version_range in deps.items():
                edges.append({
                    "entity_to": dep_name,
                    "dependency_type": dep_type,
                    "version_range": str(version_range)[:100],
                })

    return edges


def save_edges(conn, package_name, edges):
    """Save dependency edges to Postgres."""
    if not edges:
        # Save a marker so we don't re-process
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO dependency_edges (entity_from, entity_to, dependency_type, version_range, registry)
            VALUES (%s, %s, %s, %s, 'npm')
            ON CONFLICT (entity_from, entity_to, dependency_type, registry) DO NOTHING
        """, (package_name, "__NO_DEPS__", "marker", ""))
        conn.commit()
        cur.close()
        return 0

    cur = conn.cursor()
    saved = 0
    for edge in edges:
        try:
            cur.execute("""
                INSERT INTO dependency_edges (entity_from, entity_to, dependency_type, version_range, registry)
                VALUES (%s, %s, %s, %s, 'npm')
                ON CONFLICT (entity_from, entity_to, dependency_type, registry) DO UPDATE SET
                    version_range = EXCLUDED.version_range,
                    observed_at = NOW()
            """, (package_name, edge["entity_to"], edge["dependency_type"], edge["version_range"]))
            saved += 1
        except Exception as e:
            log.warning(f"Error saving edge {package_name} → {edge['entity_to']}: {e}")
            conn.rollback()

    conn.commit()
    cur.close()
    return saved


def show_status(conn):
    """Show collection progress."""
    cur = conn.cursor()

    cur.execute("SELECT COUNT(DISTINCT entity_from) FROM dependency_edges WHERE registry='npm'")
    processed = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM software_registry WHERE registry='npm'")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM dependency_edges WHERE registry='npm' AND entity_to != '__NO_DEPS__'")
    edges = cur.fetchone()[0]

    cur.execute("""
        SELECT entity_to, COUNT(*) as dependents
        FROM dependency_edges WHERE registry='npm' AND entity_to != '__NO_DEPS__'
        GROUP BY entity_to ORDER BY dependents DESC LIMIT 10
    """)
    top_deps = cur.fetchall()

    cur.close()

    print(f"\n{'='*60}")
    print(f"npm Dependency Graph Collection Status")
    print(f"{'='*60}")
    print(f"  Packages processed: {processed:,} / {total:,} ({processed/max(total,1)*100:.1f}%)")
    print(f"  Dependency edges: {edges:,}")
    print(f"  Avg edges/package: {edges/max(processed,1):.1f}")
    print(f"\n  Top 10 most-depended-on packages:")
    for name, count in top_deps:
        print(f"    {name:<40} {count:>6} dependents")
    print(f"{'='*60}")


def run(limit=None):
    import psycopg2

    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False

    packages = get_packages_to_process(conn, limit)
    log.info(f"Packages to process: {len(packages)}")

    if not packages:
        log.info("All packages already processed!")
        show_status(conn)
        conn.close()
        return

    processed = 0
    total_edges = 0
    errors = 0
    t0 = time.time()

    for name, slug, downloads in packages:
        try:
            data = fetch_npm_metadata(name)
            edges = extract_dependencies(data)
            saved = save_edges(conn, name, edges)
            total_edges += saved
            processed += 1

            if processed % 100 == 0:
                elapsed = time.time() - t0
                rate = processed / max(elapsed, 1)
                remaining = (len(packages) - processed) / max(rate, 0.01)
                log.info(f"  Progress: {processed}/{len(packages)} ({rate:.1f}/s, ~{remaining/3600:.1f}h remaining). Edges: {total_edges:,}")

        except Exception as e:
            log.warning(f"Error processing {name}: {e}")
            errors += 1
            try:
                conn.rollback()
            except:
                conn = psycopg2.connect(PG_DSN)
                conn.autocommit = False

        time.sleep(RATE_LIMIT)

    elapsed = time.time() - t0
    log.info(f"\nBatch complete: {processed} packages, {total_edges} edges, {errors} errors, {elapsed/60:.0f} min")
    show_status(conn)
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="npm Dependency Graph Collector")
    parser.add_argument("--limit", type=int, help="Max packages to process")
    parser.add_argument("--status", action="store_true", help="Show progress only")
    args = parser.parse_args()

    os.makedirs(LOG_DIR, exist_ok=True)

    if args.status:
        import psycopg2
        conn = psycopg2.connect(PG_DSN)
        show_status(conn)
        conn.close()
    else:
        run(limit=args.limit)
