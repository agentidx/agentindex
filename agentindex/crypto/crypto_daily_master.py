#!/usr/bin/env python3
"""
NERQ CRYPTO — Daily Master Pipeline
======================================
Runs the entire daily pipeline in order:
  1. Crawl tokens (update 18,291 tokens in data DB)
  2. Fetch prices (OHLCV from 4 exchanges + DeFiLlama)
  3. Compute credit ratings
  4. Compute NDD distress scores
  5. Generate alerts

This is the ONLY script that needs to be scheduled.
Everything else is called from here.

Usage:
  python3 crypto_daily_master.py              # Full pipeline
  python3 crypto_daily_master.py --skip-crawl # Skip token crawl (saves 35 min)
  python3 crypto_daily_master.py --skip-prices # Skip price fetch
  python3 crypto_daily_master.py --only ndd    # Only run NDD step
  python3 crypto_daily_master.py --status      # Show last run status

Schedule: Daily at 06:00 CET (05:00 UTC) via LaunchAgent

Author: NERQ
Version: 1.0
Date: 2026-02-27
"""

import subprocess
import sys
import os
import time
import json
import sqlite3
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable
LOG_DIR = os.path.expanduser("~/agentindex/logs")
CRYPTO_DB = os.path.join(SCRIPT_DIR, "crypto_trust.db")
DATA_DB = os.path.join(SCRIPT_DIR, "..", "data", "crypto_trust.db")

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"{ts} | {level:<5} | {msg}"
    print(line)
    # Also append to daily log file
    logfile = os.path.join(LOG_DIR, f"crypto_daily_{datetime.now().strftime('%Y-%m-%d')}.log")
    with open(logfile, "a") as f:
        f.write(line + "\n")


def run_step(name, script, args=None, timeout_min=60):
    """Run a pipeline step as subprocess."""
    cmd = [PYTHON, os.path.join(SCRIPT_DIR, script)]
    if args:
        cmd.extend(args)

    log(f"{'='*60}")
    log(f"STEP: {name}")
    log(f"  Script: {script}")
    log(f"  Args: {args or 'none'}")

    t0 = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
            timeout=timeout_min * 60,
        )

        elapsed = time.time() - t0

        # Log output (last 30 lines)
        if result.stdout:
            for line in result.stdout.strip().split("\n")[-30:]:
                log(f"  {line}")

        if result.returncode == 0:
            log(f"  ✅ {name} completed ({elapsed:.0f}s)")
            return True
        else:
            log(f"  ❌ {name} failed (exit code {result.returncode})", "ERROR")
            if result.stderr:
                for line in result.stderr.strip().split("\n")[-10:]:
                    log(f"  STDERR: {line}", "ERROR")
            return False

    except subprocess.TimeoutExpired:
        log(f"  ❌ {name} timed out after {timeout_min} min", "ERROR")
        return False
    except Exception as e:
        log(f"  ❌ {name} exception: {e}", "ERROR")
        return False


def save_run_status(steps_results):
    """Save run status to DB for monitoring."""
    try:
        conn = sqlite3.connect(CRYPTO_DB)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS crypto_pipeline_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                steps_json TEXT,
                status TEXT,
                total_seconds REAL
            )
        """)
        conn.execute("""
            INSERT INTO crypto_pipeline_runs
            (run_date, started_at, completed_at, steps_json, status, total_seconds)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%Y-%m-%d"),
            steps_results.get("started_at", ""),
            datetime.now(timezone.utc).isoformat(),
            json.dumps(steps_results.get("steps", {})),
            "OK" if all(steps_results.get("steps", {}).values()) else "PARTIAL",
            steps_results.get("total_seconds", 0),
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        log(f"  Could not save run status: {e}", "WARN")


def get_status():
    """Show last run status."""
    try:
        conn = sqlite3.connect(CRYPTO_DB)
        conn.row_factory = sqlite3.Row
        row = conn.execute("""
            SELECT * FROM crypto_pipeline_runs ORDER BY id DESC LIMIT 1
        """).fetchone()
        conn.close()

        if row:
            print(f"\n  Last pipeline run:")
            print(f"    Date:      {row['run_date']}")
            print(f"    Started:   {row['started_at']}")
            print(f"    Completed: {row['completed_at']}")
            print(f"    Status:    {row['status']}")
            print(f"    Duration:  {row['total_seconds']:.0f}s")
            steps = json.loads(row['steps_json']) if row['steps_json'] else {}
        for step, ok in steps.items():
                emoji = "✅" if ok else "❌"
                print(f"    {emoji} {step}")
        else:
            print("  No pipeline runs recorded yet.")

        # Data freshness
        conn = sqlite3.connect(CRYPTO_DB)
        row = conn.execute("SELECT MAX(date) FROM crypto_price_history").fetchone()
        print(f"\n  Price data latest: {row[0] if row else 'none'}")

        row = conn.execute("SELECT MAX(run_date), COUNT(*) FROM crypto_ndd_daily").fetchone()
        print(f"  NDD latest: {row[0] if row else 'none'} ({row[1]} tokens)")

        # Data DB freshness
        conn2 = sqlite3.connect(DATA_DB)
        row = conn2.execute("SELECT MAX(crawled_at) FROM crypto_tokens").fetchone()
        print(f"  Token crawl latest: {row[0][:19] if row and row[0] else 'none'}")
        conn2.close()
        conn.close()

    except Exception as e:
        print(f"  Error: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="NERQ Daily Master Pipeline")
    parser.add_argument("--skip-crawl", action="store_true")
    parser.add_argument("--skip-prices", action="store_true")
    parser.add_argument("--skip-rating", action="store_true")
    parser.add_argument("--skip-ndd", action="store_true")
    parser.add_argument("--only", type=str, choices=["crawl", "prices", "rating", "ndd"])
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.status:
        get_status()
        return

    t0 = time.time()
    started = datetime.now(timezone.utc).isoformat()

    log("=" * 60)
    log("NERQ CRYPTO — Daily Master Pipeline")
    log(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)

    steps = {}

    # Determine which steps to run
    run_crawl = not args.skip_crawl and args.only in (None, "crawl")
    run_prices = not args.skip_prices and args.only in (None, "prices")
    run_rating = not args.skip_rating and args.only in (None, "rating")
    run_ndd = not args.skip_ndd and args.only in (None, "ndd")

    # STEP 1: Crawl tokens
    if run_crawl:
        steps["1_crawl_tokens"] = run_step(
            "Crawl Tokens (18K)",
            "crypto_crawler.py",
            args=["--tokens-only"],
            timeout_min=60,
        )
    else:
        log("  SKIP: Token crawl")

    # STEP 2: Fetch prices
    if run_prices:
        steps["2_fetch_prices"] = run_step(
            "Fetch Prices (exchanges + DeFiLlama)",
            "crypto_price_pipeline.py",
            args=["--backfill", "2"],
            timeout_min=30,
        )
    else:
        log("  SKIP: Price fetch")

    # STEP 3: Credit ratings
    if run_rating:
        steps["3_credit_rating"] = run_step(
            "Credit Rating (daily)",
            "crypto_rating_daily.py",
            args=["--cached"],
            timeout_min=10,
        )
    else:
        log("  SKIP: Credit rating")

    # STEP 4: NDD
    if run_ndd:
        steps["4_ndd_distress"] = run_step(
            "NDD Distress Scoring (all tokens)",
            "crypto_ndd_daily_v3.py",
            timeout_min=10,
        )
    else:
        log("  SKIP: NDD")

    # STEP 4b: DeFiLlama price fallback (if exchange prices had gaps)
    if run_prices:
        steps["4b_defillama_fallback"] = run_step(
            "DeFiLlama Price Fallback (stale tokens)",
            "defillama_price_fallback.py",
            args=["--stale-only", "--days", "2"],
            timeout_min=10,
        )

    # STEP 5: Risk Signals (Beta + Structural Weakness/Strength + Alerts)
    run_risk = args.only in (None, "risk")
    if run_risk:
        steps["5_risk_signals"] = run_step(
            "Risk Signals",
            os.path.join(SCRIPT_DIR, "nerq_risk_signals.py"),
            timeout_min=10,
        )
    else:
        log("  SKIP: Risk signals")

    # SUMMARY
    total = time.time() - t0
    log("=" * 60)
    log("PIPELINE SUMMARY")
    log("=" * 60)

    for step, ok in steps.items():
        emoji = "✅" if ok else "❌"
        log(f"  {emoji} {step}")
    log(f"  Total time: {total:.0f}s ({total/60:.1f} min)")

    # Freshness check
    try:
        conn = sqlite3.connect(CRYPTO_DB)
        ohlcv = conn.execute("SELECT COUNT(DISTINCT token_id) FROM crypto_price_history WHERE date >= date('now', '-2 days')").fetchone()[0]
        ndd = conn.execute("SELECT COUNT(*) FROM crypto_ndd_daily WHERE run_date = date('now')").fetchone()[0]
        conn.close()
        log(f"\n  Tokens with fresh OHLCV: {ohlcv}")
        log(f"  Tokens with today's NDD: {ndd}")
    except:
        pass

    # Save run status
    save_run_status({
        "started_at": started,
        "steps": steps,
        "total_seconds": total,
    })

    # Exit code
    if all(steps.values()):
        log("\n  ✅ All steps completed successfully")
        sys.exit(0)
    else:
        log("\n  ⚠️ Some steps failed — check logs", "WARN")
        sys.exit(1)


if __name__ == "__main__":
    main()
