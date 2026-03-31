#!/usr/bin/env python3
"""
ZARQ — Bulk Data Export (CC BY 4.0)
====================================
Generates /data/crypto-ratings.jsonl.gz for public download.
Includes all 198 rated tokens with Trust Score, DtD, risk level, and structural alerts.

Usage:
    python3 bulk_data_export.py

Output:
    ~/agentindex/agentindex/exports/crypto-ratings.jsonl.gz

License: Creative Commons Attribution 4.0 International (CC BY 4.0)
"""

import sqlite3
import json
import gzip
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CRYPTO_DB = os.path.join(SCRIPT_DIR, "crypto_trust.db")
EXPORT_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "exports")
OUTPUT_FILE = os.path.join(EXPORT_DIR, "crypto-ratings.jsonl.gz")


def export_ratings():
    """Export all token ratings as JSONL.gz with CC BY 4.0 metadata."""
    
    conn = sqlite3.connect(CRYPTO_DB)
    conn.row_factory = sqlite3.Row
    
    # Get all rated tokens
    rows = conn.execute("""
        SELECT token_id, score, rating, 
               pillar_1, pillar_2, pillar_3, pillar_4, pillar_5,
               symbol, name, market_cap_rank
        FROM crypto_rating_daily
        WHERE run_date = (SELECT MAX(run_date) FROM crypto_rating_daily)
        ORDER BY score DESC
    """).fetchall()
    
    # Get latest NDD data if available
    ndd_data = {}
    try:
        ndd_rows = conn.execute("""
            SELECT token_id, ndd, alert_level, ndd_trend
            FROM crypto_ndd_daily
            WHERE run_date = (SELECT MAX(run_date) FROM crypto_ndd_daily)
        """).fetchall()
        for r in ndd_rows:
            ndd_data[r["token_id"]] = {
                "dtd": r["ndd"],
                "alert_level": r["alert_level"],
                "dtd_trend": r["ndd_trend"]
            }
    except:
        pass
    
    conn.close()
    
    os.makedirs(EXPORT_DIR, exist_ok=True)
    
    export_date = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    
    with gzip.open(OUTPUT_FILE, "wt", encoding="utf-8") as f:
        # First line: metadata
        meta = {
            "_meta": True,
            "source": "ZARQ Crypto Risk Intelligence",
            "url": "https://zarq.ai",
            "license": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "export_date": export_date,
            "total_tokens": len(rows),
            "methodology": "https://zarq.ai/methodology",
            "whitepaper": "https://zarq.ai/whitepaper",
            "citation": "ZARQ Crypto Risk Intelligence, zarq.ai"
        }
        f.write(json.dumps(meta) + "\n")
        
        # Token rows
        for row in rows:
            token_id = row["token_id"]
            record = {
                "token_id": token_id,
                "trust_score": round(row["score"], 2) if row["score"] else None,
                "rating": row["rating"],
                "symbol": row["symbol"],
                "name": row["name"],
                "market_cap_rank": row["market_cap_rank"],
                "pillars": {
                    "security": round(row["pillar_1"], 2) if row["pillar_1"] else None,
                    "compliance": round(row["pillar_2"], 2) if row["pillar_2"] else None,
                    "maintenance": round(row["pillar_3"], 2) if row["pillar_3"] else None,
                    "popularity": round(row["pillar_4"], 2) if row["pillar_4"] else None,
                    "ecosystem": round(row["pillar_5"], 2) if row["pillar_5"] else None,
                },
            }
            
            # Add DtD if available
            if token_id in ndd_data:
                record["dtd"] = ndd_data[token_id]["dtd"]
                record["alert_level"] = ndd_data[token_id]["alert_level"]
                record["dtd_trend"] = ndd_data[token_id]["dtd_trend"]
            
            f.write(json.dumps(record) + "\n")
    
    size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"Exported {len(rows)} tokens to {OUTPUT_FILE} ({size_kb:.0f} KB)")
    print(f"License: CC BY 4.0")
    print(f"Date: {export_date}")


if __name__ == "__main__":
    export_ratings()
