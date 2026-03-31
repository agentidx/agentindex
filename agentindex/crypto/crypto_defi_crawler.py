"""
Nerq Crypto Module — DeFiLlama Crawler
Punkt 26: Crawla alla 5K+ DeFi-protokoll med TVL, audit-status, hack-historik.

DeFiLlama API is free, no key needed, no strict rate limits.

Usage:
    python3 crypto_defi_crawler.py                # Full crawl: protocols + hacks
    python3 crypto_defi_crawler.py --stats         # Print DB stats
"""

import argparse
import json
import time
import sys
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("❌ requests not installed. Run: pip3 install requests --break-system-packages")
    sys.exit(1)

from crypto_models import get_db, init_db

DEFILLAMA_BASE_URL = "https://api.llama.fi"
DELAY = 1.0  # polite delay between calls


def _n(val):
    """Safely convert numeric values to float for SQLite."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError, OverflowError):
        return None


def api_get(url, retries=3):
    """GET request with retries."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=30, headers={
                "User-Agent": "Nerq/1.0 (https://nerq.ai) DeFiCrawler"
            })
            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"  ⚠️ HTTP {resp.status_code} for {url} (attempt {attempt+1})")
                time.sleep(3)
        except requests.exceptions.RequestException as e:
            print(f"  ⚠️ Request error: {e} (attempt {attempt+1})")
            time.sleep(3)
    print(f"  ❌ Failed after {retries} attempts: {url}")
    return None


# ── Protocol Crawler ──────────────────────────────────────────────

def crawl_protocols():
    """
    Crawl all DeFi protocols from /protocols endpoint.
    Returns everything in one call — TVL, category, chains, etc.
    """
    print("\n🏗️  CRAWLING DEFI PROTOCOLS via /protocols")

    data = api_get(f"{DEFILLAMA_BASE_URL}/protocols")
    if not data:
        print("❌ Failed to fetch protocols")
        return 0

    print(f"   Received {len(data)} protocols from DeFiLlama\n")

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for p in data:
        slug = p.get("slug") or p.get("name", "").lower().replace(" ", "-")
        if not slug:
            continue

        # Extract audit info from the protocol data
        audits = p.get("audits") or p.get("audit_links") or []
        audit_note = p.get("audit_note") or ""

        conn.execute("""
            INSERT INTO crypto_defi_protocols (
                id, name, tvl_usd, tvl_change_1d, tvl_change_7d, tvl_change_30d,
                category, chains, url, twitter, github,
                audit_status, crawled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                tvl_usd = excluded.tvl_usd,
                tvl_change_1d = excluded.tvl_change_1d,
                tvl_change_7d = excluded.tvl_change_7d,
                tvl_change_30d = excluded.tvl_change_30d,
                category = excluded.category,
                chains = excluded.chains,
                url = excluded.url,
                twitter = excluded.twitter,
                github = excluded.github,
                audit_status = excluded.audit_status,
                crawled_at = excluded.crawled_at
        """, (
            slug,
            p.get("name", ""),
            _n(p.get("tvl")),
            _n(p.get("change_1d")),
            _n(p.get("change_7d")),
            _n(p.get("change_1m")),
            p.get("category", ""),
            json.dumps(p.get("chains", [])),
            p.get("url", ""),
            p.get("twitter", ""),
            (p.get("github") or [""])[0] if isinstance(p.get("github"), list) else p.get("github", ""),
            json.dumps({"audits": audits, "audit_note": audit_note}),
            now
        ))
        count += 1

        if count % 1000 == 0:
            conn.commit()
            print(f"   💾 {count} protocols saved...")

    conn.commit()
    conn.close()
    print(f"\n✅ DeFi protocol crawl complete: {count} protocols saved")
    return count


# ── Hack History Crawler ──────────────────────────────────────────

def crawl_hacks():
    """
    Crawl known DeFi hacks from /hacks endpoint.
    Maps hacks back to protocols for trust scoring.
    """
    print("\n🔓 CRAWLING DEFI HACKS via /hacks")

    data = api_get(f"{DEFILLAMA_BASE_URL}/hacks")
    if not data:
        print("❌ Failed to fetch hacks")
        return 0

    print(f"   Received {len(data)} hack incidents\n")

    conn = get_db()

    # Build a dict: protocol_slug -> list of hacks
    hack_map = {}
    for h in data:
        name = (h.get("name") or "").strip()
        slug = name.lower().replace(" ", "-")
        if not slug:
            continue

        incident = {
            "date": h.get("date", ""),
            "amount_usd": _n(h.get("amount")),
            "classification": h.get("classification", ""),
            "technique": h.get("technique", ""),
            "chain": h.get("chain", ""),
            "target": h.get("target_type", ""),
        }

        if slug not in hack_map:
            hack_map[slug] = []
        hack_map[slug].append(incident)

    # Update protocols with hack history
    updated = 0
    for slug, hacks in hack_map.items():
        total_stolen = sum(h["amount_usd"] or 0 for h in hacks)
        result = conn.execute("""
            UPDATE crypto_defi_protocols
            SET hack_history = ?
            WHERE id = ?
        """, (json.dumps({"incidents": hacks, "total_stolen_usd": total_stolen}), slug))

        if result.rowcount > 0:
            updated += 1

    conn.commit()
    conn.close()
    print(f"✅ Hack data mapped: {len(hack_map)} protocols with hacks, {updated} matched in DB")
    print(f"   Total incidents: {len(data)}")
    return updated


# ── Stats ─────────────────────────────────────────────────────────

def print_stats():
    """Print DeFi database stats."""
    conn = get_db()

    total = conn.execute("SELECT COUNT(*) as c FROM crypto_defi_protocols").fetchone()["c"]
    with_tvl = conn.execute("SELECT COUNT(*) as c FROM crypto_defi_protocols WHERE tvl_usd > 0").fetchone()["c"]
    with_hacks = conn.execute("SELECT COUNT(*) as c FROM crypto_defi_protocols WHERE hack_history IS NOT NULL").fetchone()["c"]
    scored = conn.execute("SELECT COUNT(*) as c FROM crypto_defi_protocols WHERE trust_score IS NOT NULL").fetchone()["c"]

    top = conn.execute("SELECT name, tvl_usd FROM crypto_defi_protocols ORDER BY tvl_usd DESC LIMIT 5").fetchall()

    # Category breakdown
    cats = conn.execute("""
        SELECT category, COUNT(*) as c FROM crypto_defi_protocols
        WHERE category != '' GROUP BY category ORDER BY c DESC LIMIT 10
    """).fetchall()

    print("\n📊 DEFI DATABASE STATS")
    print(f"   Protocols:    {total:,} ({with_tvl:,} with TVL, {scored:,} scored)")
    print(f"   With hacks:   {with_hacks:,}")
    print(f"\n   Top 5 by TVL:")
    for t in top:
        tvl = t["tvl_usd"]
        if tvl and tvl > 1_000_000_000:
            print(f"     {t['name']}: ${tvl/1e9:.1f}B")
        elif tvl and tvl > 1_000_000:
            print(f"     {t['name']}: ${tvl/1e6:.0f}M")
        elif tvl:
            print(f"     {t['name']}: ${tvl:,.0f}")

    print(f"\n   Top categories:")
    for c in cats:
        print(f"     {c['category']}: {c['c']}")

    conn.close()


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Nerq Crypto — DeFiLlama Crawler")
    parser.add_argument("--stats", action="store_true", help="Print DB stats and exit")
    parser.add_argument("--protocols-only", action="store_true", help="Only crawl protocols")
    parser.add_argument("--hacks-only", action="store_true", help="Only crawl hacks")
    args = parser.parse_args()

    init_db()

    if args.stats:
        print_stats()
        return

    print("=" * 60)
    print("  NERQ CRYPTO — DeFiLlama Crawler")
    print(f"  Started: {datetime.now(timezone.utc).isoformat()}")
    print("  No API key needed ✅")
    print("=" * 60)

    start = time.time()

    if not args.hacks_only:
        crawl_protocols()
        time.sleep(DELAY)

    if not args.protocols_only:
        crawl_hacks()

    elapsed = time.time() - start
    print(f"\n⏱️  Total time: {elapsed:.1f} seconds")

    print_stats()


if __name__ == "__main__":
    main()
