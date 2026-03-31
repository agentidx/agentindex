"""
Nerq Crypto — Bulk Trust Score Export
Punkt 35: Generate /data/crypto-trust-scores.jsonl.gz

Exports all scored crypto entities as JSONL (one JSON object per line, gzipped).
Same pattern as existing /data/trust-scores.jsonl.gz for agents.

Usage:
    python3 crypto_export.py
"""

import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from crypto_models import get_db

EXPORT_DIR = Path(__file__).parent.parent / "exports"


def export_all():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = EXPORT_DIR / "crypto-trust-scores.jsonl.gz"

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    with gzip.open(output_path, "wt", encoding="utf-8") as f:
        # Tokens
        rows = conn.execute("""
            SELECT id, symbol, name, current_price_usd, market_cap_usd, market_cap_rank,
                   trust_score, trust_grade, security_score, compliance_score,
                   maintenance_score, popularity_score, ecosystem_score, scored_at
            FROM crypto_tokens WHERE trust_score IS NOT NULL
            ORDER BY trust_score DESC
        """).fetchall()

        for r in rows:
            obj = {
                "entity_type": "token",
                "id": r["id"],
                "symbol": r["symbol"],
                "name": r["name"],
                "price_usd": r["current_price_usd"],
                "market_cap_usd": r["market_cap_usd"],
                "market_cap_rank": r["market_cap_rank"],
                "trust_score": r["trust_score"],
                "trust_grade": r["trust_grade"],
                "security": r["security_score"],
                "compliance": r["compliance_score"],
                "maintenance": r["maintenance_score"],
                "popularity": r["popularity_score"],
                "ecosystem": r["ecosystem_score"],
                "scored_at": r["scored_at"],
            }
            f.write(json.dumps(obj) + "\n")
            count += 1

        # Exchanges
        rows = conn.execute("""
            SELECT id, name, country, trade_volume_24h_btc, trust_score_cg,
                   trust_score, trust_grade, security_score, compliance_score,
                   maintenance_score, popularity_score, ecosystem_score, scored_at
            FROM crypto_exchanges WHERE trust_score IS NOT NULL
            ORDER BY trust_score DESC
        """).fetchall()

        for r in rows:
            obj = {
                "entity_type": "exchange",
                "id": r["id"],
                "name": r["name"],
                "country": r["country"],
                "volume_24h_btc": r["trade_volume_24h_btc"],
                "coingecko_trust": r["trust_score_cg"],
                "trust_score": r["trust_score"],
                "trust_grade": r["trust_grade"],
                "security": r["security_score"],
                "compliance": r["compliance_score"],
                "maintenance": r["maintenance_score"],
                "popularity": r["popularity_score"],
                "ecosystem": r["ecosystem_score"],
                "scored_at": r["scored_at"],
            }
            f.write(json.dumps(obj) + "\n")
            count += 1

        # DeFi protocols
        rows = conn.execute("""
            SELECT id, name, category, tvl_usd,
                   trust_score, trust_grade, security_score, compliance_score,
                   maintenance_score, popularity_score, ecosystem_score, scored_at
            FROM crypto_defi_protocols WHERE trust_score IS NOT NULL
            ORDER BY trust_score DESC
        """).fetchall()

        for r in rows:
            obj = {
                "entity_type": "defi",
                "id": r["id"],
                "name": r["name"],
                "category": r["category"],
                "tvl_usd": r["tvl_usd"],
                "trust_score": r["trust_score"],
                "trust_grade": r["trust_grade"],
                "security": r["security_score"],
                "compliance": r["compliance_score"],
                "maintenance": r["maintenance_score"],
                "popularity": r["popularity_score"],
                "ecosystem": r["ecosystem_score"],
                "scored_at": r["scored_at"],
            }
            f.write(json.dumps(obj) + "\n")
            count += 1

    conn.close()

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"✅ Exported {count:,} crypto entities to {output_path}")
    print(f"   File size: {size_mb:.1f} MB")

    # Also generate summary JSON
    summary_path = EXPORT_DIR / "crypto-trust-summary.json"
    conn = get_db()

    summary = {
        "generated_at": now,
        "totals": {
            "tokens": conn.execute("SELECT COUNT(*) FROM crypto_tokens WHERE trust_score IS NOT NULL").fetchone()[0],
            "exchanges": conn.execute("SELECT COUNT(*) FROM crypto_exchanges WHERE trust_score IS NOT NULL").fetchone()[0],
            "defi_protocols": conn.execute("SELECT COUNT(*) FROM crypto_defi_protocols WHERE trust_score IS NOT NULL").fetchone()[0],
        },
        "averages": {
            "tokens": round(conn.execute("SELECT AVG(trust_score) FROM crypto_tokens WHERE trust_score IS NOT NULL").fetchone()[0] or 0, 1),
            "exchanges": round(conn.execute("SELECT AVG(trust_score) FROM crypto_exchanges WHERE trust_score IS NOT NULL").fetchone()[0] or 0, 1),
            "defi_protocols": round(conn.execute("SELECT AVG(trust_score) FROM crypto_defi_protocols WHERE trust_score IS NOT NULL").fetchone()[0] or 0, 1),
        },
        "top_tokens": [],
        "top_exchanges": [],
        "top_defi": [],
    }

    for table, key in [("crypto_tokens", "top_tokens"), ("crypto_exchanges", "top_exchanges"), ("crypto_defi_protocols", "top_defi")]:
        rows = conn.execute(f"SELECT id, name, trust_score, trust_grade FROM {table} WHERE trust_score IS NOT NULL ORDER BY trust_score DESC LIMIT 10").fetchall()
        summary[key] = [{"id": r["id"], "name": r["name"], "trust_score": r["trust_score"], "trust_grade": r["trust_grade"]} for r in rows]

    conn.close()

    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"✅ Summary written to {summary_path}")


if __name__ == "__main__":
    export_all()
