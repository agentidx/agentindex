#!/usr/bin/env python3
"""
CVE Enrichment via OSV.dev batch API.
Queries up to 1000 packages per request. ~20 min for all enriched packages.

Run: python3 -m agentindex.crawlers.cve_enrichment [limit]
"""

import json
import logging
import sys
import time
from pathlib import Path

import requests
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agentindex.db.models import get_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
log = logging.getLogger("cve_enrichment")

ECOSYSTEM_MAP = {
    "npm": "npm", "pypi": "PyPI", "crates": "crates.io",
    "nuget": "NuGet", "gems": "RubyGems", "go": "Go", "packagist": "Packagist",
}
OSV_BATCH = "https://api.osv.dev/v1/querybatch"
BATCH_SIZE = 1000


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 500000
    session = get_session()
    try:
        session.execute(text("SET statement_timeout = '10s'"))
        regs = ",".join(f"'{r}'" for r in ECOSYSTEM_MAP)
        rows = session.execute(text(f"""
            SELECT id, name, registry, latest_version
            FROM software_registry
            WHERE registry IN ({regs})
            AND enriched_at IS NOT NULL
            AND (cve_count IS NULL OR cve_count = 0)
            ORDER BY COALESCE(downloads, 0) DESC
            LIMIT :lim
        """), {"lim": limit}).fetchall()
        session.execute(text("SET statement_timeout = '10s'"))

        total = len(rows)
        log.info(f"CVE enrichment: {total} packages to check")
        updated = 0

        for i in range(0, total, BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            queries = []
            valid_idx = []
            for j, row in enumerate(batch):
                eco = ECOSYSTEM_MAP.get(row[2])
                if not eco:
                    continue
                q = {"package": {"name": row[1], "ecosystem": eco}}
                if row[3]:
                    q["version"] = row[3]
                queries.append(q)
                valid_idx.append(j)

            if not queries:
                continue

            try:
                resp = requests.post(OSV_BATCH, json={"queries": queries}, timeout=30)
                if resp.status_code != 200:
                    log.warning(f"OSV batch failed: {resp.status_code}")
                    time.sleep(5)
                    continue
                results = resp.json().get("results", [])
            except Exception as e:
                log.warning(f"OSV request error: {e}")
                time.sleep(5)
                continue

            for k, result in enumerate(results):
                if k >= len(valid_idx):
                    break
                idx = valid_idx[k]
                pkg = batch[idx]
                vulns = result.get("vulns", [])
                cve_count = len(vulns)
                cve_critical = 0
                for v in vulns:
                    for sev in v.get("severity", []):
                        if sev.get("type") == "CVSS_V3":
                            try:
                                score = float(sev.get("score", "0"))
                                if score >= 9.0:
                                    cve_critical += 1
                            except (ValueError, TypeError):
                                pass

                if cve_count > 0:
                    try:
                        session.execute(text("""
                            UPDATE software_registry
                            SET cve_count = :cnt, cve_critical = :crit
                            WHERE id = :id
                        """), {"id": str(pkg[0]), "cnt": cve_count, "crit": cve_critical})
                        updated += 1
                    except Exception:
                        session.rollback()

            session.commit()
            log.info(f"Batch {i // BATCH_SIZE + 1}: checked {len(queries)}, found CVEs in {updated} packages")
            time.sleep(0.5)

        session.commit()
        log.info(f"CVE enrichment complete: {updated}/{total} packages have CVEs")
    except Exception as e:
        log.error(f"Fatal: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
