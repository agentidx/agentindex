#!/usr/bin/env python3
"""
Predictive Content Machine
============================
Auto-generates pages BEFORE traffic arrives based on demand signals.

Nerq cycle: every 6 hours (max 20 pages per cycle)
ZARQ cycle: every 1 hour (max 10 pages per cycle, crypto moves fast)

Usage:
    python -m agentindex.intelligence.predictive_content --nerq
    python -m agentindex.intelligence.predictive_content --zarq
    python -m agentindex.intelligence.predictive_content --calibrate
"""

import json
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler("/tmp/predictive-content.log")])
logger = logging.getLogger("nerq.predictive_content")

ANALYTICS_DB = str(Path(__file__).parent.parent.parent / "logs" / "analytics.db")
MISSING_TARGETS = str(Path(__file__).parent.parent.parent / "data" / "missing_targets.json")
CRYPTO_DB = str(Path(__file__).parent.parent / "crypto" / "crypto_trust.db")
TODAY = date.today()


# ════════════════════════════════════════════════════════
# NERQ SIGNALS
# ════════════════════════════════════════════════════════

def check_missing_targets():
    """Signal 1: AI systems asked for something we don't have."""
    opportunities = []
    if not os.path.exists(MISSING_TARGETS):
        return opportunities
    try:
        data = json.loads(open(MISSING_TARGETS).read())
        for target, info in data.items():
            count = info.get("count", 0)
            if count >= 2:
                opportunities.append({
                    "tool": target,
                    "score": min(100, count * 30),
                    "reason": f"AI systems requested '{target}' {count} times (404)",
                    "signal": "missing_target",
                })
    except Exception as e:
        logger.warning(f"Missing targets error: {e}")
    return opportunities


def check_ai_crawl_spikes():
    """Signal 2: AI bot crawl frequency increased >3x vs 7-day average."""
    opportunities = []
    if not os.path.exists(ANALYTICS_DB):
        return opportunities
    try:
        conn = sqlite3.connect(ANALYTICS_DB, timeout=3)
        rows = conn.execute("""
            SELECT path,
                SUM(CASE WHEN ts > strftime('%Y-%m-%dT%H:%M:%f', 'now', '-24 hours') THEN 1 ELSE 0 END) as last_24h,
                COUNT(*) / 7.0 as daily_avg
            FROM requests
            WHERE is_bot = 1
            AND (user_agent LIKE '%ChatGPT%' OR user_agent LIKE '%Perplexity%'
                 OR user_agent LIKE '%ClaudeBot%' OR user_agent LIKE '%GPTBot%')
            AND ts > strftime('%Y-%m-%dT%H:%M:%f', 'now', '-7 days')
            GROUP BY path
            HAVING last_24h > daily_avg * 3 AND last_24h > 5
            ORDER BY last_24h DESC
            LIMIT 20
        """).fetchall()
        conn.close()

        for path, last_24h, daily_avg in rows:
            # Extract tool name from path
            tool = path.split("/")[-1] if "/" in path else path
            tool = tool.replace("-safe", "").strip("-")
            if tool and len(tool) > 2:
                spike = last_24h / max(1, daily_avg)
                opportunities.append({
                    "tool": tool,
                    "score": min(100, spike * 20),
                    "reason": f"AI crawl spike: {last_24h:.0f} hits/24h vs {daily_avg:.0f} avg ({spike:.1f}x)",
                    "signal": "ai_crawl_spike",
                })
    except Exception as e:
        logger.warning(f"AI crawl spike check error: {e}")
    return opportunities


def check_star_acceleration():
    """Signal 3: Tools with accelerating star growth."""
    opportunities = []
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT o2.agent_name,
                   (o2.stars - o1.stars) as star_gain,
                   o2.stars as current_stars
            FROM prediction_observations o1
            JOIN prediction_observations o2 ON o1.agent_id = o2.agent_id
            WHERE o1.observed_at = :yesterday AND o2.observed_at = :today
            AND o2.stars > 100
            AND (o2.stars - o1.stars) > 10
            ORDER BY (o2.stars - o1.stars) DESC
            LIMIT 20
        """), {"yesterday": (TODAY - timedelta(days=1)).isoformat(),
               "today": TODAY.isoformat()}).fetchall()

        for name, gain, stars in rows:
            tool = name.split("/")[-1] if "/" in name else name
            opportunities.append({
                "tool": tool, "full_name": name,
                "score": min(100, gain * 0.5),
                "reason": f"Star acceleration: +{gain} stars in 24h (total: {stars:,})",
                "signal": "star_acceleration",
            })
    except Exception as e:
        logger.warning(f"Star acceleration check error: {e}")
    finally:
        session.close()
    return opportunities


def check_replacement_patterns():
    """Signal 5: Tool A declining while Tool B (same category) rising."""
    opportunities = []
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT s1.agent_name as declining, s2.agent_name as rising,
                   s1.star_velocity_7d as dec_vel, s2.star_velocity_7d as rise_vel
            FROM prediction_signals s1
            JOIN prediction_signals s2 ON s1.calculated_at = s2.calculated_at
            JOIN agents a1 ON s1.agent_id = a1.id
            JOIN agents a2 ON s2.agent_id = a2.id
            WHERE s1.calculated_at = :today
            AND a1.category = a2.category AND a1.category IS NOT NULL
            AND s1.star_velocity_7d < -5
            AND s2.star_velocity_7d > 5
            AND s1.agent_id != s2.agent_id
            ORDER BY (s2.star_velocity_7d - s1.star_velocity_7d) DESC
            LIMIT 10
        """), {"today": TODAY.isoformat()}).fetchall()

        for dec_name, rise_name, dec_vel, rise_vel in rows:
            dec_tool = dec_name.split("/")[-1] if "/" in dec_name else dec_name
            rise_tool = rise_name.split("/")[-1] if "/" in rise_name else rise_name
            diff = abs(rise_vel - dec_vel)
            opportunities.append({
                "tool": dec_tool, "alt_tool": rise_tool,
                "score": min(100, diff * 0.3),
                "reason": f"Replacement: {dec_tool} ({dec_vel:+d}) -> {rise_tool} ({rise_vel:+d})",
                "signal": "replacement_pattern",
            })
    except Exception as e:
        logger.warning(f"Replacement pattern check error: {e}")
    finally:
        session.close()
    return opportunities


NERQ_SIGNALS = {
    "missing_target": check_missing_targets,
    "ai_crawl_spike": check_ai_crawl_spikes,
    "star_acceleration": check_star_acceleration,
    "replacement_pattern": check_replacement_patterns,
}


# ════════════════════════════════════════════════════════
# ZARQ CRYPTO SIGNALS
# ════════════════════════════════════════════════════════

def check_crash_predictions():
    """Tokens where crash probability crossed 50%."""
    opportunities = []
    try:
        conn = sqlite3.connect(CRYPTO_DB, timeout=3)
        rows = conn.execute("""
            SELECT n.token_id, n.name, n.crash_probability, n.alert_level
            FROM crypto_ndd_daily n
            WHERE n.run_date = (SELECT MAX(run_date) FROM crypto_ndd_daily)
            AND n.crash_probability > 0.5
            ORDER BY n.crash_probability DESC
            LIMIT 20
        """).fetchall()
        conn.close()

        for token_id, name, prob, alert in rows:
            opportunities.append({
                "tool": token_id, "name": name or token_id,
                "score": min(100, prob * 100),
                "reason": f"Crash probability {prob*100:.0f}% -- alert: {alert}",
                "signal": "crash_prediction",
            })
    except Exception as e:
        logger.warning(f"Crash prediction check error: {e}")
    return opportunities


def check_vitality_changes():
    """Tokens with significant vitality drops."""
    opportunities = []
    try:
        conn = sqlite3.connect(CRYPTO_DB, timeout=3)
        rows = conn.execute("""
            SELECT v.token_id, v.vitality_score, v.vitality_grade
            FROM vitality_scores v
            WHERE v.vitality_score < 30
            ORDER BY v.vitality_score ASC
            LIMIT 20
        """).fetchall()
        conn.close()

        for token_id, score, grade in rows:
            opportunities.append({
                "tool": token_id,
                "score": min(100, (100 - (score or 0)) * 1.5),
                "reason": f"Low vitality: {score}/100 ({grade}) -- people searching 'is {token_id} dead'",
                "signal": "vitality_drop",
            })
    except Exception as e:
        logger.warning(f"Vitality check error: {e}")
    return opportunities


ZARQ_SIGNALS = {
    "crash_prediction": check_crash_predictions,
    "vitality_drop": check_vitality_changes,
}


# ════════════════════════════════════════════════════════
# PAGE GENERATION
# ════════════════════════════════════════════════════════

GENERATION_TIERS = {
    "strong": {"min_score": 80, "templates": [
        "/is-{tool}-safe", "/compare/{tool}-vs-{alt}", "/alternatives/{tool}", "/predict/{tool}",
    ]},
    "medium": {"min_score": 50, "templates": [
        "/is-{tool}-safe", "/alternatives/{tool}",
    ]},
    "weak": {"min_score": 0, "templates": [
        "/is-{tool}-safe",
    ]},
}

ZARQ_TEMPLATES = {
    "strong": ["/is-{tool}-dead", "/is-{tool}-a-scam", "/crash-prediction/{tool}"],
    "medium": ["/is-{tool}-dead", "/is-{tool}-a-scam"],
    "weak": ["/is-{tool}-dead"],
}


def get_tier(score):
    if score >= 80: return "strong"
    if score >= 50: return "medium"
    return "weak"


def page_exists(url):
    """Check if a page already returns 200."""
    try:
        import subprocess
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "3",
             f"http://localhost:8000{url}"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() == "200"
    except Exception:
        return False


def ensure_in_slug_file(tool_name):
    """Ensure the tool is in agent_safety_slugs.json so /is-X-safe works."""
    slugs_path = Path(__file__).parent.parent / "agent_safety_slugs.json"
    try:
        with open(slugs_path) as f:
            slugs = json.load(f)
        slug = tool_name.lower().replace("/", "-").replace(" ", "-").replace("_", "-")
        slug = re.sub(r"[^a-z0-9-]", "", slug).strip("-")
        existing_slugs = {s.get("slug", "").lower() for s in slugs}
        if slug not in existing_slugs:
            slugs.append({"slug": slug, "name": tool_name, "category": "", "source": "predictive",
                         "trust_score": 0, "trust_grade": "D", "stars": 0, "is_verified": False})
            with open(slugs_path, "w") as f:
                json.dump(slugs, f)
            logger.info(f"Added {slug} to safety slugs")
            return True
    except Exception as e:
        logger.warning(f"Slug file update error: {e}")
    return False


def submit_indexnow(urls, host="nerq.ai"):
    """Submit new URLs to IndexNow."""
    if not urls:
        return
    try:
        import requests as http_req
        key = "nerq2026indexnow" if "nerq" in host else "zarq2026indexnow"
        full_urls = [f"https://{host}{u}" if not u.startswith("http") else u for u in urls]

        for i in range(0, len(full_urls), 100):
            batch = full_urls[i:i+100]
            resp = http_req.post("https://api.indexnow.org/indexnow", json={
                "host": host, "key": key,
                "keyLocation": f"https://{host}/{key}.txt",
                "urlList": batch,
            }, timeout=10)
            if resp.status_code in (200, 202):
                logger.info(f"IndexNow: {len(batch)} URLs submitted to {host}")
            else:
                logger.warning(f"IndexNow error: HTTP {resp.status_code}")
            time.sleep(0.3)
    except Exception as e:
        logger.warning(f"IndexNow error: {e}")


def log_prediction(domain, opp, pages_created):
    """Log prediction for calibration."""
    session = get_session()
    try:
        session.execute(text("""
            INSERT INTO predictive_content_log (domain, signal_type, signal_score, tool_or_token, pages_created)
            VALUES (:domain, :signal, :score, :tool, CAST(:pages AS jsonb))
        """), {
            "domain": domain, "signal": opp["signal"], "score": opp["score"],
            "tool": opp.get("tool", ""), "pages": json.dumps(pages_created),
        })
        session.commit()
    except Exception as e:
        logger.warning(f"Log prediction error: {e}")
        session.rollback()
    finally:
        session.close()


# ════════════════════════════════════════════════════════
# ORCHESTRATORS
# ════════════════════════════════════════════════════════

def run_nerq_cycle():
    """Run Nerq predictive content cycle (every 6 hours)."""
    load = os.getloadavg()[0]
    if load > 5.0:
        logger.info(f"Skipping Nerq cycle -- load {load:.1f}")
        return

    logger.info("=== NERQ PREDICTIVE CYCLE ===")
    all_opps = []

    for signal_name, check_fn in NERQ_SIGNALS.items():
        try:
            opps = check_fn()
            logger.info(f"  {signal_name}: {len(opps)} opportunities")
            all_opps.extend(opps)
        except Exception as e:
            logger.error(f"  {signal_name} failed: {e}")

    # Deduplicate by tool name, keep highest score
    seen = {}
    for opp in all_opps:
        tool = opp.get("tool", "").lower()
        if tool not in seen or opp["score"] > seen[tool]["score"]:
            seen[tool] = opp
    all_opps = sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:20]

    logger.info(f"Top {len(all_opps)} opportunities (after dedup)")

    pages_created_total = 0
    for opp in all_opps:
        tier = get_tier(opp["score"])
        templates = GENERATION_TIERS[tier]["templates"]
        pages = []

        for tmpl in templates:
            url = tmpl.replace("{tool}", re.sub(r"[^a-z0-9-]", "-", opp["tool"].lower()).strip("-"))
            if "{alt}" in url:
                url = url.replace("{alt}", "alternative")  # placeholder
            if not page_exists(url):
                # Ensure slug exists for /is-X-safe routes
                if "/is-" in url and "-safe" in url:
                    ensure_in_slug_file(opp["tool"])
                pages.append(url)

        if pages:
            submit_indexnow(pages, host="nerq.ai")
            log_prediction("nerq.ai", opp, pages)
            pages_created_total += len(pages)
            logger.info(f"  {opp['tool']}: score={opp['score']:.0f} signal={opp['signal']} pages={len(pages)}")

    logger.info(f"Nerq cycle complete: {pages_created_total} pages from {len(all_opps)} signals")


def run_zarq_cycle():
    """Run ZARQ predictive content cycle (every hour)."""
    load = os.getloadavg()[0]
    if load > 5.0:
        logger.info(f"Skipping ZARQ cycle -- load {load:.1f}")
        return

    logger.info("=== ZARQ PREDICTIVE CYCLE ===")
    all_opps = []

    for signal_name, check_fn in ZARQ_SIGNALS.items():
        try:
            opps = check_fn()
            logger.info(f"  {signal_name}: {len(opps)} opportunities")
            all_opps.extend(opps)
        except Exception as e:
            logger.error(f"  {signal_name} failed: {e}")

    seen = {}
    for opp in all_opps:
        tool = opp.get("tool", "").lower()
        if tool not in seen or opp["score"] > seen[tool]["score"]:
            seen[tool] = opp
    all_opps = sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:10]

    logger.info(f"Top {len(all_opps)} opportunities")

    pages_created_total = 0
    for opp in all_opps:
        tier = get_tier(opp["score"])
        templates = ZARQ_TEMPLATES[tier]
        pages = []

        for tmpl in templates:
            url = tmpl.replace("{tool}", opp["tool"].lower())
            # ZARQ pages are dynamic -- they work if the token exists in slugs
            pages.append(url)

        if pages:
            submit_indexnow(pages, host="zarq.ai")
            log_prediction("zarq.ai", opp, pages)
            pages_created_total += len(pages)
            logger.info(f"  {opp['tool']}: score={opp['score']:.0f} signal={opp['signal']} pages={len(pages)}")

    logger.info(f"ZARQ cycle complete: {pages_created_total} pages from {len(all_opps)} signals")


def run_calibration():
    """Weekly calibration: compare predictions with actual traffic."""
    logger.info("=== CALIBRATION ===")
    session = get_session()
    try:
        # Get predictions from 7+ days ago that haven't been calibrated
        rows = session.execute(text("""
            SELECT id, domain, signal_type, tool_or_token, pages_created, predicted_at
            FROM predictive_content_log
            WHERE predicted_at < NOW() - INTERVAL '7 days'
            AND calibrated_at IS NULL
            LIMIT 100
        """)).fetchall()

        if not rows:
            logger.info("No predictions to calibrate yet")
            return

        conn = sqlite3.connect(ANALYTICS_DB, timeout=3) if os.path.exists(ANALYTICS_DB) else None

        for row in rows:
            pred_id = row[0]
            pages = json.loads(row[4]) if isinstance(row[4], str) else (row[4] or [])
            total_traffic = 0
            ai_citations = 0

            if conn and pages:
                for page in pages:
                    try:
                        r = conn.execute("""
                            SELECT COUNT(*) as hits,
                                   SUM(CASE WHEN user_agent LIKE '%ChatGPT%' OR user_agent LIKE '%Perplexity%' THEN 1 ELSE 0 END) as ai
                            FROM requests WHERE path = ? AND ts > strftime('%Y-%m-%dT%H:%M:%f', 'now', '-7 days')
                        """, (page,)).fetchone()
                        total_traffic += r[0] or 0
                        ai_citations += r[1] or 0
                    except Exception:
                        pass

            accurate = total_traffic > 0
            session.execute(text("""
                UPDATE predictive_content_log
                SET actual_traffic_7d = :traffic, actual_ai_citations = :ai,
                    calibrated_at = NOW(), accurate = :accurate
                WHERE id = :id
            """), {"traffic": total_traffic, "ai": ai_citations, "accurate": accurate, "id": pred_id})

        session.commit()
        if conn:
            conn.close()

        # Report accuracy by signal type
        results = session.execute(text("""
            SELECT signal_type, COUNT(*) as total,
                   SUM(CASE WHEN accurate THEN 1 ELSE 0 END) as correct
            FROM predictive_content_log
            WHERE calibrated_at IS NOT NULL
            GROUP BY signal_type
        """)).fetchall()

        for sig, total, correct in results:
            acc = (correct or 0) / max(1, total) * 100
            logger.info(f"  {sig}: {acc:.0f}% accuracy ({correct}/{total})")

    except Exception as e:
        logger.error(f"Calibration error: {e}")
        session.rollback()
    finally:
        session.close()


# ════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--nerq" in args:
        run_nerq_cycle()
    elif "--zarq" in args:
        run_zarq_cycle()
    elif "--calibrate" in args:
        run_calibration()
    elif "--all" in args:
        run_nerq_cycle()
        run_zarq_cycle()
    else:
        print("Usage: python -m agentindex.intelligence.predictive_content --nerq|--zarq|--calibrate|--all")
