#!/usr/bin/env python3
"""
Crypto Trust Score Sync — copy ZARQ trust scores to software_registry.
Reads from crypto_trust.db (nerq_risk_signals + crypto_rating_daily),
writes to PostgreSQL software_registry with registry='crypto'.

Run: python3 -m agentindex.crawlers.crypto_sync
"""

import logging
import sqlite3
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
log = logging.getLogger("crypto_sync")

ZARQ_DB = str(Path(__file__).parent.parent / "crypto" / "crypto_trust.db")


def main():
    log.info(f"Reading from {ZARQ_DB}")
    conn = sqlite3.connect(ZARQ_DB)

    # Get latest risk signals (trust scores)
    risk_rows = conn.execute("""
        SELECT token_id, trust_score, risk_level, ndd_current, structural_weakness
        FROM nerq_risk_signals
        WHERE signal_date = (SELECT MAX(signal_date) FROM nerq_risk_signals)
        ORDER BY trust_score DESC
    """).fetchall()
    log.info(f"Risk signals: {len(risk_rows)} tokens")

    # Get names from crypto_rating_daily
    name_map = {}
    rating_rows = conn.execute("""
        SELECT token_id, name, symbol, score, rating, market_cap, market_cap_rank
        FROM crypto_rating_daily
        WHERE run_date = (SELECT MAX(run_date) FROM crypto_rating_daily)
    """).fetchall()
    for r in rating_rows:
        name_map[r[0]] = {
            "name": r[1] or r[0].replace("-", " ").title(),
            "symbol": r[2] or "",
            "rating_score": r[3],
            "rating": r[4] or "",
            "market_cap": r[5] or 0,
            "rank": r[6] or 0,
        }

    # Get price data for tokens not in rating_daily
    price_tokens = conn.execute("""
        SELECT DISTINCT token_id FROM crypto_price_history
        WHERE token_id NOT IN (SELECT DISTINCT token_id FROM crypto_rating_daily)
    """).fetchall()
    for r in price_tokens:
        if r[0] not in name_map:
            name_map[r[0]] = {
                "name": r[0].replace("-", " ").title(),
                "symbol": "",
                "rating_score": None,
                "rating": "",
                "market_cap": 0,
                "rank": 0,
            }

    conn.close()

    # Merge: use risk_signals trust_score, fallback to rating_daily score
    tokens = {}
    for r in risk_rows:
        token_id = r[0]
        trust_score = r[1] or 50
        risk_level = r[2] or "UNKNOWN"
        info = name_map.get(token_id, {"name": token_id.replace("-", " ").title(), "symbol": "", "market_cap": 0, "rank": 0})

        # Map trust score to grade
        if trust_score >= 80: grade = "A"
        elif trust_score >= 70: grade = "B+"
        elif trust_score >= 60: grade = "B"
        elif trust_score >= 50: grade = "C+"
        elif trust_score >= 40: grade = "C"
        elif trust_score >= 30: grade = "D"
        else: grade = "F"

        # Description
        symbol = info.get("symbol", "").upper()
        risk_text = {"SAFE": "low risk", "WATCH": "moderate risk", "WARNING": "elevated risk", "DANGER": "high risk"}.get(risk_level, "")
        desc = f"{info['name']} ({symbol}) cryptocurrency. Nerq risk level: {risk_text}."
        if info.get("market_cap") and info["market_cap"] > 0:
            mcap = info["market_cap"]
            if mcap >= 1e9:
                desc += f" Market cap: ${mcap/1e9:.1f}B."
            elif mcap >= 1e6:
                desc += f" Market cap: ${mcap/1e6:.0f}M."

        tokens[token_id] = {
            "name": info["name"],
            "slug": token_id,
            "score": round(trust_score, 1),
            "grade": grade,
            "desc": desc[:500],
            "security_score": round(trust_score, 1),
            "popularity_score": min(100, max(10, (info.get("rank") or 999) * -0.1 + 100)) if info.get("rank") else 50,
        }

    # Also add tokens from rating_daily that aren't in risk_signals
    for token_id, info in name_map.items():
        if token_id not in tokens and info.get("rating_score"):
            score = info["rating_score"]
            if score >= 80: grade = "A"
            elif score >= 70: grade = "B+"
            elif score >= 60: grade = "B"
            elif score >= 50: grade = "C+"
            elif score >= 40: grade = "C"
            elif score >= 30: grade = "D"
            else: grade = "F"

            symbol = info.get("symbol", "").upper()
            desc = f"{info['name']} ({symbol}) cryptocurrency."
            if info.get("market_cap") and info["market_cap"] > 0:
                mcap = info["market_cap"]
                if mcap >= 1e9:
                    desc += f" Market cap: ${mcap/1e9:.1f}B."
                elif mcap >= 1e6:
                    desc += f" Market cap: ${mcap/1e6:.0f}M."

            tokens[token_id] = {
                "name": info["name"],
                "slug": token_id,
                "score": round(score, 1),
                "grade": grade,
                "desc": desc[:500],
                "security_score": round(score, 1),
                "popularity_score": 50,
            }

    log.info(f"Total tokens to sync: {len(tokens)}")

    # Upsert to PostgreSQL
    session = get_session()
    try:
        session.execute(text("SET statement_timeout = '10s'"))
        done = 0
        for token_id, t in tokens.items():
            session.execute(text("""
                INSERT INTO software_registry (id, name, slug, registry, description, trust_score, trust_grade,
                    security_score, popularity_score, enriched_at, created_at)
                VALUES (:id, :name, :slug, 'crypto', :desc, :score, :grade, :sec, :pop, NOW(), NOW())
                ON CONFLICT (registry, slug) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    trust_score = EXCLUDED.trust_score,
                    trust_grade = EXCLUDED.trust_grade,
                    security_score = EXCLUDED.security_score,
                    popularity_score = EXCLUDED.popularity_score,
                    enriched_at = NOW()
            """), {
                "id": str(uuid.uuid4()),
                "name": t["name"],
                "slug": t["slug"],
                "desc": t["desc"],
                "score": t["score"],
                "grade": t["grade"],
                "sec": t["security_score"],
                "pop": t["popularity_score"],
            })
            done += 1

        session.commit()
        log.info(f"Synced {done} crypto tokens to software_registry")
    finally:
        session.close()


if __name__ == "__main__":
    main()
