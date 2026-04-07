"""
Run all registry crawlers in sequence.
Usage: python3 agentindex/crypto/crawlers/run_all_crawlers.py
"""
import importlib
import time

CRAWLERS = [
    "agentindex.crypto.crawlers.crawl_pulsemcp",
    "agentindex.crypto.crawlers.crawl_mcp_registry",
    "agentindex.crypto.crawlers.crawl_openrouter",
    "agentindex.crypto.crawlers.crawl_lobehub",
    "agentindex.crypto.crawlers.crawl_agentverse",
    "agentindex.crypto.crawlers.crawl_erc8004",
]


def main():
    print("=" * 60)
    print("Running all registry crawlers")
    print("=" * 60)
    start = time.time()

    for crawler_path in CRAWLERS:
        print(f"\n--- {crawler_path} ---")
        try:
            mod = importlib.import_module(crawler_path)
            mod.run()
        except Exception as e:
            print(f"  FAILED: {e}")

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"All crawlers finished in {elapsed:.1f}s")

    # Print SQLite staging summary
    import sqlite3
    conn = sqlite3.connect("/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db")
    rows = conn.execute("SELECT source, COUNT(*) FROM agent_crypto_profile GROUP BY source ORDER BY COUNT(*) DESC").fetchall()
    total = sum(r[1] for r in rows)
    print(f"\n=== SQLite Staging Summary ===")
    for source, count in rows:
        print(f"  {source:20s} {count:>6,}")
    print(f"  {'TOTAL':20s} {total:>6,}")
    conn.close()

    # Sync to PostgreSQL
    print(f"\n{'=' * 60}")
    print("Syncing to PostgreSQL...")
    print("=" * 60)
    try:
        from agentindex.crypto.crawlers.sync_to_postgres import sync
        sync()
    except Exception as e:
        print(f"  SYNC FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
