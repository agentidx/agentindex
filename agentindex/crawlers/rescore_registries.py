"""
Registry Re-scorer — applies improved scoring formulas per registry.
Fixes: security default 90→50, popularity default 30→5, registry-specific buckets.

Usage:
    python -m agentindex.crawlers.rescore_registries --registry website [--batch 10000] [--dry-run]
    python -m agentindex.crawlers.rescore_registries --registry all --batch 50000
"""
import argparse
import logging
import os
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [rescore] %(message)s")
log = logging.getLogger("rescore")

from agentindex.db_config import get_write_dsn
DB_DSN = os.environ.get("DATABASE_URL") or get_write_dsn(fmt="psycopg2")


def score_security(cve_count, has_enrichment, license_str, openssf_score):
    """Security score: start at 50 (unknown), add/subtract based on evidence."""
    score = 50  # Unknown = middle, NOT 90

    if has_enrichment and cve_count == 0:
        score += 20  # Verified no CVEs — real signal
    elif cve_count == 0:
        score += 0   # Not verified — no bonus
    elif cve_count <= 2:
        score -= 10
    elif cve_count <= 5:
        score -= 25
    else:
        score -= 40

    # OpenSSF scorecard
    if openssf_score and openssf_score >= 7:
        score += 15
    elif openssf_score and openssf_score >= 5:
        score += 8
    elif openssf_score and openssf_score >= 3:
        score += 4

    # License (security signal)
    lic = (license_str or "").upper()
    if lic and any(k in lic for k in ["MIT", "BSD", "APACHE", "ISC"]):
        score += 10
    elif lic and any(k in lic for k in ["GPL", "LGPL", "MPL"]):
        score += 5
    elif not lic:
        score -= 5  # No license = slight risk

    return max(0, min(100, score))


def score_popularity(registry, downloads, stars, forks):
    """Registry-specific popularity. Unknown = LOW (5), not middle."""
    dl = downloads or 0
    st = stars or 0
    fk = forks or 0

    if registry == "website":
        # Tranco rank: lower = better. 0 = unknown.
        # 399K sites in 100K-500K range — use LOG scale for smooth spread
        import math
        rank = dl
        if rank <= 0:
            return 5
        # Log-scale: rank 1 → 99, rank 500K → ~15
        # Formula: 99 - 15 * log10(rank)  (clamped 5-99)
        score = 99 - 15 * math.log10(max(rank, 1))
        return max(5, min(99, int(score)))

    if registry == "npm":
        if dl > 10_000_000: return 95
        if dl > 1_000_000: return 82
        if dl > 100_000: return 68
        if dl > 10_000: return 52
        if dl > 1_000: return 38
        if dl > 100: return 24
        if dl > 0: return 12
        return 5  # Unknown = low

    if registry == "nuget":
        if dl > 100_000_000: return 95
        if dl > 10_000_000: return 82
        if dl > 1_000_000: return 68
        if dl > 100_000: return 52
        if dl > 10_000: return 38
        if dl > 100: return 24
        if dl > 0: return 12
        return 5

    if registry in ("chrome", "firefox"):
        users = dl  # user count stored in downloads
        if users > 1_000_000: return 95
        if users > 100_000: return 80
        if users > 10_000: return 62
        if users > 1_000: return 45
        if users > 100: return 30
        if users > 0: return 18
        return 5

    if registry == "go":
        if st > 50_000: return 95
        if st > 10_000: return 82
        if st > 1_000: return 65
        if st > 100: return 48
        if st > 10: return 32
        if st > 0: return 18
        return 5

    if registry == "pypi":
        if dl > 10_000_000: return 95
        if dl > 1_000_000: return 80
        if dl > 100_000: return 65
        if dl > 10_000: return 50
        if dl > 1_000: return 35
        if dl > 100: return 22
        if dl > 0: return 12
        return 5

    if registry in ("crates", "packagist", "gems"):
        if dl > 10_000_000: return 95
        if dl > 1_000_000: return 80
        if dl > 100_000: return 65
        if dl > 10_000: return 50
        if dl > 1_000: return 35
        if dl > 0: return 18
        return 5

    # Default (android, ios, steam, wordpress, vscode, etc.)
    if dl > 1_000_000: return 90
    if dl > 100_000: return 72
    if dl > 10_000: return 55
    if dl > 1_000: return 40
    if dl > 100: return 25
    if dl > 0: return 15
    return 5  # Unknown = low


def score_maintenance(release_count):
    """Maintenance based on release count."""
    rc = release_count or 0
    return min(100, 30 + min(rc, 70))  # 30 base + up to 70 from releases


def score_community(stars, forks, contributors):
    """Community based on GitHub signals."""
    st = stars or 0
    fk = forks or 0
    ct = contributors or 0

    score = 10  # Base low
    if st > 10000: score += 35
    elif st > 1000: score += 25
    elif st > 100: score += 15
    elif st > 10: score += 8

    if fk > 100: score += 15
    elif fk > 10: score += 8
    elif fk > 0: score += 3

    if ct > 50: score += 15
    elif ct > 10: score += 10
    elif ct > 3: score += 5

    return min(100, score)


def score_quality(license_str, description):
    """Quality based on license + documentation."""
    score = 15  # Base low
    lic = (license_str or "").upper()
    if lic and any(k in lic for k in ["MIT", "BSD", "APACHE", "ISC"]):
        score += 30
    elif lic and any(k in lic for k in ["GPL", "LGPL", "MPL"]):
        score += 20
    elif lic:
        score += 10

    desc = description or ""
    if len(desc) > 200: score += 20
    elif len(desc) > 50: score += 10
    elif len(desc) > 20: score += 5

    return min(100, score)


def compute_total(sec, maint, pop, comm, qual, registry=""):
    """Weighted total. Websites weight popularity higher (30%) since Tranco rank is the key differentiator."""
    if registry == "website":
        # Websites: Tranco rank is nearly the ONLY differentiator.
        # Other dimensions are identical for all websites (no CVEs, no releases, no stars).
        # Use 70% popularity to let rank dominate the score.
        total = round(sec * 0.05 + maint * 0.05 + pop * 0.70 + comm * 0.05 + qual * 0.15, 1)
    else:
        total = round(sec * 0.25 + maint * 0.20 + pop * 0.20 + comm * 0.15 + qual * 0.20, 1)
    return max(0, min(100, total))


def grade_from_score(score):
    if score >= 90: return "A+"
    if score >= 85: return "A"
    if score >= 80: return "A-"
    if score >= 75: return "B+"
    if score >= 70: return "B"
    if score >= 65: return "B-"
    if score >= 60: return "C+"
    if score >= 55: return "C"
    if score >= 50: return "C-"
    if score >= 40: return "D"
    return "F"


_SKIP_REGISTRIES = {"crypto", "vpn", "password_manager", "hosting", "antivirus", "saas", "website_builder",
                     "packagist", "gems", "homebrew", "vscode"}  # Manual vertical scoring

def rescore_batch(registry, batch_size=10000, dry_run=False):
    if registry in _SKIP_REGISTRIES:
        log.info(f"SKIP {registry} — uses external scoring engine")
        return
    conn = psycopg2.connect(DB_DSN, options="-c statement_timeout=60000 -c application_name=nerq_rescore")
    conn.autocommit = True
    cur = conn.cursor()

    # Get current stats
    cur.execute(f"SELECT ROUND(AVG(trust_score)::numeric,1), ROUND(STDDEV(trust_score)::numeric,1), MIN(trust_score), MAX(trust_score), COUNT(*) FROM software_registry WHERE registry=%s AND trust_score IS NOT NULL", (registry,))
    before = cur.fetchone()
    log.info(f"BEFORE {registry}: avg={before[0]}, stddev={before[1]}, min={before[2]}, max={before[3]}, n={before[4]}")

    if dry_run:
        cur.close(); conn.close(); return

    cur.execute("""
        SELECT id, downloads, stars, forks, contributors, release_count,
               license, description, cve_count, openssf_score, enriched_at IS NOT NULL as enriched
        FROM software_registry WHERE registry=%s AND trust_score IS NOT NULL
        LIMIT %s
    """, (registry, batch_size))
    rows = cur.fetchall()
    log.info(f"Re-scoring {len(rows)} {registry} entities...")

    for i, (pid, dl, st, fk, ct, rc, lic, desc, cve, ossf, enriched) in enumerate(rows):
        sec = score_security(cve or 0, enriched, lic, ossf)
        pop = score_popularity(registry, dl, st, fk)
        maint = score_maintenance(rc)
        comm = score_community(st, fk, ct)
        qual = score_quality(lic, desc)
        total = compute_total(sec, maint, pop, comm, qual, registry)
        g = grade_from_score(total)

        cur.execute("""
            UPDATE software_registry SET trust_score=%s, trust_grade=%s,
                security_score=%s, maintenance_score=%s, popularity_score=%s,
                community_score=%s, quality_score=%s
            WHERE id=%s
        """, (total, g, round(sec,1), round(maint,1), round(pop,1), round(comm,1), round(qual,1), pid))

        if (i+1) % 10000 == 0:
            log.info(f"  Progress: {i+1}/{len(rows)}")

    # After stats
    cur.execute(f"SELECT ROUND(AVG(trust_score)::numeric,1), ROUND(STDDEV(trust_score)::numeric,1), MIN(trust_score), MAX(trust_score) FROM software_registry WHERE registry=%s AND trust_score IS NOT NULL", (registry,))
    after = cur.fetchone()
    log.info(f"AFTER {registry}: avg={after[0]}, stddev={after[1]}, min={after[2]}, max={after[3]}")

    cur.close(); conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True, help="Registry to rescore (or 'all')")
    parser.add_argument("--batch", type=int, default=10000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.registry == "all":
        for reg in ["website", "npm", "nuget", "firefox", "chrome", "go", "pypi", "crates", "packagist", "gems",
                     "android", "ios", "steam", "wordpress", "vscode", "homebrew"]:
            rescore_batch(reg, args.batch, args.dry_run)
    else:
        rescore_batch(args.registry, args.batch, args.dry_run)
