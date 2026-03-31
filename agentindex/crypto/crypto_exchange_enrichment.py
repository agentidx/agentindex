"""
Nerq Crypto Module — Exchange Enrichment
Punkt 28: Berika exchanges med proof-of-reserves, regulatorisk status, hack-historik.

Uses curated data for major exchanges + DeFiLlama hack data.

Usage:
    python3 crypto_exchange_enrichment.py          # Enrich all
    python3 crypto_exchange_enrichment.py --stats   # Show enrichment stats
"""

import argparse
import json
from datetime import datetime, timezone

from crypto_models import get_db, init_db


# ══════════════════════════════════════════════════════════════════
# CURATED EXCHANGE DATA
# Known proof-of-reserves, regulatory status, and hack history
# ══════════════════════════════════════════════════════════════════

EXCHANGE_DATA = {
    "binance": {
        "proof_of_reserves": 1,
        "regulatory_status": {
            "France": "Registered (AMF)",
            "Italy": "Registered (OAM)",
            "Spain": "Registered (Bank of Spain)",
            "Dubai": "Licensed (VARA)",
            "Japan": "Licensed (FSA, via subsidiary)",
            "US": "Partial (Binance.US separate entity, SEC settlement 2023)",
        },
        "hack_history": [
            {"date": "2019-05-07", "amount_usd": 40_000_000, "type": "Hot wallet breach", "recovered": "Covered by SAFU fund"}
        ],
    },
    "coinbase-exchange": {
        "proof_of_reserves": 1,
        "regulatory_status": {
            "US": "Licensed (MSB, state licenses, publicly traded NASDAQ:COIN)",
            "UK": "Registered (FCA)",
            "Germany": "Licensed (BaFin)",
            "Ireland": "Licensed (Central Bank of Ireland)",
            "Japan": "Licensed (FSA)",
            "Singapore": "Licensed (MAS)",
        },
        "hack_history": [],
    },
    "kraken": {
        "proof_of_reserves": 1,
        "regulatory_status": {
            "US": "Licensed (MSB, state licenses, SEC settlement 2023)",
            "UK": "Registered (FCA)",
            "Canada": "Registered (OSC)",
            "Australia": "Licensed (AUSTRAC)",
            "Japan": "Licensed (FSA)",
            "Abu Dhabi": "Licensed (FSRA)",
        },
        "hack_history": [],
    },
    "kucoin": {
        "proof_of_reserves": 1,
        "regulatory_status": {
            "Seychelles": "Registered",
            "US": "DOJ settlement 2024 ($297M)",
        },
        "hack_history": [
            {"date": "2020-09-25", "amount_usd": 281_000_000, "type": "Hot wallet breach", "recovered": "Most recovered via blockchain tracking"}
        ],
    },
    "okx": {
        "proof_of_reserves": 1,
        "regulatory_status": {
            "Dubai": "Licensed (VARA)",
            "Bahamas": "Registered",
            "Hong Kong": "License application pending",
        },
        "hack_history": [],
    },
    "bybit": {
        "proof_of_reserves": 1,
        "regulatory_status": {
            "Dubai": "Licensed (VARA)",
            "Cyprus": "Licensed",
        },
        "hack_history": [
            {"date": "2025-02-21", "amount_usd": 1_500_000_000, "type": "Cold wallet breach (Lazarus Group)", "recovered": "Under investigation"}
        ],
    },
    "bitget": {
        "proof_of_reserves": 1,
        "regulatory_status": {
            "Lithuania": "Registered",
            "Poland": "Registered",
        },
        "hack_history": [],
    },
    "gate-io": {
        "proof_of_reserves": 1,
        "regulatory_status": {
            "Cayman Islands": "Registered",
            "Malta": "License application",
        },
        "hack_history": [
            {"date": "2018-04-01", "amount_usd": 230_000_000, "type": "Suspected breach (unconfirmed)", "recovered": "Unknown"}
        ],
    },
    "mexc": {
        "proof_of_reserves": 0,
        "regulatory_status": {
            "Seychelles": "Registered",
        },
        "hack_history": [],
    },
    "crypto-com-exchange": {
        "proof_of_reserves": 1,
        "regulatory_status": {
            "Singapore": "Licensed (MAS MPI)",
            "US": "Licensed (MSB, state licenses)",
            "UK": "Registered (FCA)",
            "France": "Registered (AMF)",
            "Dubai": "Licensed (VARA)",
            "South Korea": "Licensed (VASP)",
        },
        "hack_history": [
            {"date": "2022-01-17", "amount_usd": 34_000_000, "type": "Unauthorized withdrawals", "recovered": "All users reimbursed"}
        ],
    },
    "bitfinex": {
        "proof_of_reserves": 1,
        "regulatory_status": {
            "BVI": "Registered",
            "El Salvador": "Licensed (Bitcoin Law)",
        },
        "hack_history": [
            {"date": "2016-08-02", "amount_usd": 72_000_000, "type": "Security breach (120K BTC)", "recovered": "Partially recovered by DOJ 2022"}
        ],
    },
    "gemini": {
        "proof_of_reserves": 1,
        "regulatory_status": {
            "US": "Licensed (NYDFS Trust Company, state MSB licenses)",
            "UK": "Registered (FCA)",
            "Singapore": "Licensed (MAS MPI)",
            "Ireland": "Licensed (Central Bank)",
        },
        "hack_history": [],
    },
    "bitstamp": {
        "proof_of_reserves": 1,
        "regulatory_status": {
            "Luxembourg": "Licensed (CSSF PFS)",
            "US": "Licensed (state MSB licenses)",
            "UK": "Registered (FCA)",
            "Singapore": "Licensed (MAS MPI)",
        },
        "hack_history": [
            {"date": "2015-01-04", "amount_usd": 5_000_000, "type": "Hot wallet breach", "recovered": "All users covered"}
        ],
    },
    "upbit": {
        "proof_of_reserves": 1,
        "regulatory_status": {
            "South Korea": "Licensed (VASP, operated by Dunamu Inc)",
        },
        "hack_history": [
            {"date": "2019-11-27", "amount_usd": 49_000_000, "type": "Hot wallet breach (342K ETH)", "recovered": "Covered by company funds"}
        ],
    },
    "htx": {
        "proof_of_reserves": 1,
        "regulatory_status": {
            "Seychelles": "Registered",
            "Dubai": "License pending",
        },
        "hack_history": [
            {"date": "2023-09-25", "amount_usd": 8_000_000, "type": "Hot wallet breach", "recovered": "Users covered"},
            {"date": "2023-11-22", "amount_usd": 97_000_000, "type": "Hot wallet breach", "recovered": "Users covered"}
        ],
    },
    "poloniex": {
        "proof_of_reserves": 0,
        "regulatory_status": {
            "Seychelles": "Registered",
        },
        "hack_history": [
            {"date": "2023-11-10", "amount_usd": 126_000_000, "type": "Hot wallet breach", "recovered": "Partial"}
        ],
    },
}


# ══════════════════════════════════════════════════════════════════
# ENRICHMENT ENGINE
# ══════════════════════════════════════════════════════════════════

def enrich_exchanges():
    """Apply curated data to exchanges in the database."""
    print("\n🏦 ENRICHING EXCHANGES")
    print(f"   Curated data for {len(EXCHANGE_DATA)} exchanges\n")

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    enriched = 0
    not_found = []

    for exchange_id, data in EXCHANGE_DATA.items():
        # Try exact match first
        row = conn.execute("SELECT id FROM crypto_exchanges WHERE id = ?", (exchange_id,)).fetchone()

        if not row:
            # Try fuzzy match
            row = conn.execute("SELECT id FROM crypto_exchanges WHERE id LIKE ?",
                             (f"%{exchange_id.split('-')[0]}%",)).fetchone()

        if row:
            actual_id = row["id"]
            conn.execute("""
                UPDATE crypto_exchanges SET
                    proof_of_reserves = ?,
                    regulatory_status = ?,
                    hack_history = ?
                WHERE id = ?
            """, (
                data.get("proof_of_reserves", 0),
                json.dumps(data.get("regulatory_status", {})),
                json.dumps(data.get("hack_history", [])),
                actual_id
            ))
            enriched += 1

            por = "✅ PoR" if data.get("proof_of_reserves") else "❌ No PoR"
            regs = len(data.get("regulatory_status", {}))
            hacks = len(data.get("hack_history", []))
            print(f"   {por} | {regs} jurisdictions | {hacks} hacks → {actual_id}")
        else:
            not_found.append(exchange_id)

    conn.commit()

    # Stats
    por_count = conn.execute("SELECT COUNT(*) as c FROM crypto_exchanges WHERE proof_of_reserves = 1").fetchone()["c"]
    reg_count = conn.execute("SELECT COUNT(*) as c FROM crypto_exchanges WHERE regulatory_status IS NOT NULL AND regulatory_status != ''").fetchone()["c"]
    hack_count = conn.execute("SELECT COUNT(*) as c FROM crypto_exchanges WHERE hack_history IS NOT NULL AND hack_history != '' AND hack_history != '[]'").fetchone()["c"]

    conn.close()

    print(f"\n✅ Enriched {enriched} exchanges")
    if not_found:
        print(f"   ⚠️ Not found in DB: {', '.join(not_found)}")
    print(f"\n   📊 Database totals:")
    print(f"      Proof of Reserves: {por_count} exchanges")
    print(f"      Regulatory data:   {reg_count} exchanges")
    print(f"      Hack history:      {hack_count} exchanges")

    return enriched


def print_stats():
    conn = get_db()

    total = conn.execute("SELECT COUNT(*) as c FROM crypto_exchanges").fetchone()["c"]
    por = conn.execute("SELECT COUNT(*) as c FROM crypto_exchanges WHERE proof_of_reserves = 1").fetchone()["c"]
    reg = conn.execute("SELECT COUNT(*) as c FROM crypto_exchanges WHERE regulatory_status IS NOT NULL AND regulatory_status != ''").fetchone()["c"]
    hacked = conn.execute("SELECT COUNT(*) as c FROM crypto_exchanges WHERE hack_history IS NOT NULL AND hack_history != '' AND hack_history != '[]'").fetchone()["c"]
    scored = conn.execute("SELECT COUNT(*) as c FROM crypto_exchanges WHERE trust_score IS NOT NULL").fetchone()["c"]

    print(f"\n📊 EXCHANGE ENRICHMENT STATS")
    print(f"   Total exchanges:     {total:,}")
    print(f"   With PoR:            {por} ({por/total*100:.1f}%)")
    print(f"   With regulatory:     {reg} ({reg/total*100:.1f}%)")
    print(f"   With hack history:   {hacked} ({hacked/total*100:.1f}%)")
    print(f"   Scored:              {scored}")

    # Top by trust score with enrichment
    top = conn.execute("""
        SELECT name, trust_score, trust_grade, proof_of_reserves, regulatory_status, hack_history
        FROM crypto_exchanges WHERE trust_score IS NOT NULL
        ORDER BY trust_score DESC LIMIT 10
    """).fetchall()

    print(f"\n   Top 10 exchanges (enriched):")
    for ex in top:
        por_str = "✅" if ex["proof_of_reserves"] else "❌"
        regs = 0
        if ex["regulatory_status"]:
            try:
                regs = len(json.loads(ex["regulatory_status"]))
            except:
                pass
        hacks = 0
        if ex["hack_history"]:
            try:
                h = json.loads(ex["hack_history"])
                hacks = len(h) if isinstance(h, list) else 0
            except:
                pass
        print(f"     {ex['trust_grade']} ({ex['trust_score']:5.1f}) {por_str} {regs}reg {hacks}hack — {ex['name']}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Nerq Crypto — Exchange Enrichment")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    init_db()

    if args.stats:
        print_stats()
        return

    print("=" * 60)
    print("  NERQ CRYPTO — Exchange Enrichment (Punkt 28)")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    enrich_exchanges()

    print("\n💡 TIP: Re-score exchanges to include enrichment data:")
    print("   python3 crypto_trust_score.py --exchanges-only")


if __name__ == "__main__":
    main()
