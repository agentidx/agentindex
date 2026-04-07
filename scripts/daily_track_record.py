#!/usr/bin/env python3
"""
ZARQ Daily Track Record — Sprint 1
====================================
Records a tamper-evident daily snapshot of all risk signals.
Each entry is hash-chained to the previous one (blockchain-style).

Output: ~/agentindex/track-record/daily-signals.jsonl
Run daily via cron or LaunchAgent.
"""

import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
CRYPTO_DB = os.path.join(PROJECT_ROOT, "agentindex", "crypto", "crypto_trust.db")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "track-record")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "daily-signals.jsonl")


def get_previous_hash():
    """Read the hash of the last entry in the chain."""
    if not os.path.exists(OUTPUT_FILE):
        return "genesis"
    last_line = None
    with open(OUTPUT_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                last_line = line
    if not last_line:
        return "genesis"
    try:
        return json.loads(last_line)["hash"]
    except (json.JSONDecodeError, KeyError):
        return "genesis"


def compute_hash(date_str, signals, previous_hash):
    """SHA-256 of date + sorted signal list + previous hash."""
    payload = json.dumps(
        {"date": date_str, "signals": signals, "previous_hash": previous_hash},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_latest_price(conn, token_id):
    """Get most recent price from crypto_price_history."""
    row = conn.execute(
        "SELECT close, date FROM crypto_price_history "
        "WHERE token_id = ? ORDER BY date DESC LIMIT 1",
        (token_id,),
    ).fetchone()
    if row:
        return {"price": row[0], "price_date": row[1]}
    return {"price": None, "price_date": None}


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Check if today's entry already exists
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("date") == today:
                        print(f"Entry for {today} already exists. Skipping.")
                        return 0
                except json.JSONDecodeError:
                    continue

    conn = sqlite3.connect(CRYPTO_DB)
    conn.row_factory = sqlite3.Row

    # Get latest signal date
    sd_row = conn.execute(
        "SELECT MAX(signal_date) as d FROM nerq_risk_signals"
    ).fetchone()
    signal_date = sd_row["d"] if sd_row else None
    if not signal_date:
        print("ERROR: No signal data found.")
        conn.close()
        return 1

    # Query all 205 tokens
    rows = conn.execute(
        """
        SELECT token_id, risk_level, trust_score, trust_p3,
               ndd_current, structural_weakness, structural_strength,
               first_collapse_date, price_at_collapse
        FROM nerq_risk_signals
        WHERE signal_date = ?
        ORDER BY token_id
        """,
        (signal_date,),
    ).fetchall()

    signals = []
    warning_count = 0
    for row in rows:
        sw = row["structural_weakness"] or 0
        p3 = row["trust_p3"] or 100
        is_warning = sw >= 2 or p3 < 40

        price_info = get_latest_price(conn, row["token_id"])

        signal = {
            "token_id": row["token_id"],
            "risk_level": row["risk_level"],
            "trust_score": round(float(row["trust_score"]), 2) if row["trust_score"] else None,
            "trust_p3": round(float(p3), 2),
            "ndd": round(float(row["ndd_current"]), 2) if row["ndd_current"] else None,
            "structural_weakness": sw,
            "zarq_warning": is_warning,
            "price_usd": price_info["price"],
            "price_date": price_info["price_date"],
        }

        if is_warning:
            warning_count += 1
            signal["first_collapse_date"] = row["first_collapse_date"]
            signal["price_at_collapse"] = row["price_at_collapse"]

        signals.append(signal)

    conn.close()

    # Build the hash-chained entry
    previous_hash = get_previous_hash()
    entry_hash = compute_hash(today, signals, previous_hash)

    entry = {
        "date": today,
        "signal_date": signal_date,
        "total_tokens": len(signals),
        "zarq_warnings": warning_count,
        "signals": signals,
        "hash": entry_hash,
        "previous_hash": previous_hash,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Append to JSONL
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "a") as f:
        f.write(json.dumps(entry, separators=(",", ":")) + "\n")

    print(f"Track record entry for {today}:")
    print(f"  Signal date: {signal_date}")
    print(f"  Total tokens: {len(signals)}")
    print(f"  ZARQ warnings: {warning_count}")
    print(f"  Hash: {entry_hash[:16]}...")
    print(f"  Previous: {previous_hash[:16]}{'...' if len(previous_hash) > 16 else ''}")
    print(f"  Written to: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
