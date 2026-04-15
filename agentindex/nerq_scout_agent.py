"""
Nerq Scout Agent — Autonomous discovery, evaluation, and reporting.
Run: python3 -m agentindex.nerq_scout_agent

Steps:
  1. DISCOVER: Find top uncontacted agents from PostgreSQL
  2. EVALUATE: Call /v1/agent/kya/{name} for each
  3. PUBLISH: Generate report via Ollama, save markdown, publish to Dev.to
"""

import json
import logging
import os
import random
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import urllib.request

try:
    import psycopg2
except ImportError:
    psycopg2 = None

try:
    import requests as _requests_lib
except ImportError:
    _requests_lib = None

# ── Paths for enhancements ───────────────────────────────────

SCORE_ANOMALIES_PATH = Path(__file__).resolve().parent / "score_anomalies.json"
CRYPTO_TRUST_DB_PATH = Path(__file__).resolve().parent / "crypto" / "crypto_trust.db"
BADGE_OUTREACH_LOG_PATH = Path(__file__).resolve().parent / "badge_outreach_log.json"

# ── Config ────────────────────────────────────────────────────

REPORTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "auto-reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b"
KYA_BASE = "http://localhost:8000/v1/agent/kya"
KYA_API_KEY = "nerq-internal-2026"

DEVTO_KEY_PATH = Path.home() / ".config" / "nerq" / "devto_api_key"

SYSTEM_PROMPT = (
    "You are the Nerq Scout, reporting on top AI agents discovered today. "
    "Write a concise, data-driven report. No hype."
)

# ── Logging ───────────────────────────────────────────────────

logger = logging.getLogger("nerq_scout_agent")
logger.setLevel(logging.INFO)

_fh = logging.FileHandler(LOGS_DIR / "scout.log")
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(_fh)

_sh = logging.StreamHandler()
_sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(_sh)


# ── Helpers: score anomalies ──────────────────────────────────

def _load_score_anomalies() -> list[dict]:
    """Load score_anomalies.json, returning empty list on any failure."""
    try:
        if SCORE_ANOMALIES_PATH.exists():
            data = json.loads(SCORE_ANOMALIES_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
    except Exception as e:
        logger.warning(f"Could not load score_anomalies.json: {e}")
    return []


def _vitality_anomaly_footer() -> str:
    """Return a report footer line about dramatic vitality movers, or empty string."""
    anomalies = _load_score_anomalies()
    if not anomalies:
        return ""

    big_movers = []
    for entry in anomalies:
        try:
            delta = abs(float(entry.get("vitality_delta", 0)))
            if delta > 15:
                big_movers.append(entry)
        except (TypeError, ValueError):
            continue

    if not big_movers:
        return ""

    big_movers.sort(key=lambda e: abs(float(e.get("vitality_delta", 0))), reverse=True)
    lines = []
    for m in big_movers[:3]:
        name = m.get("name") or m.get("token") or m.get("symbol") or "Unknown"
        delta = float(m.get("vitality_delta", 0))
        score = m.get("vitality_score", "?")
        direction = "up" if delta > 0 else "down"
        lines.append(f"  - {name}: vitality {direction} {abs(delta):.1f}pts to {score}")

    return "\n\n**Vitality Anomalies:**\n" + "\n".join(lines)


def _biggest_vitality_mover() -> dict | None:
    """Find the token with the largest absolute vitality delta from anomalies."""
    anomalies = _load_score_anomalies()
    if not anomalies:
        return None

    best = None
    best_delta = 0
    for entry in anomalies:
        try:
            delta = abs(float(entry.get("vitality_delta", 0)))
            if delta > best_delta:
                best_delta = delta
                best = entry
        except (TypeError, ValueError):
            continue

    return best if best_delta > 0 else None


def _weekly_numbers_footer() -> str:
    """Build a 'This Week at Nerq' footer with live counts."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    # 1. New agents from PostgreSQL via psycopg2
    new_agents = 0
    try:
        import psycopg2
        conn = psycopg2.connect(
            dbname=os.environ.get("PGDATABASE", "agentindex"),
            user=os.environ.get("PGUSER", "anstudio"),
            host=os.environ.get("PGHOST", "localhost"),
            port=os.environ.get("PGPORT", "5432"),
        )
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM agents WHERE created_at >= %s", (cutoff,))
        row = cur.fetchone()
        new_agents = row[0] if row else 0
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"Weekly numbers: Postgres agents count failed: {e}")

    # 2. Tokens scored from crypto_trust.db (vitality_scores table)
    tokens_scored = 0
    try:
        if CRYPTO_TRUST_DB_PATH.exists():
            conn = sqlite3.connect(str(CRYPTO_TRUST_DB_PATH))
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM vitality_scores")
            row = cur.fetchone()
            tokens_scored = row[0] if row else 0
            cur.close()
            conn.close()
    except Exception as e:
        logger.warning(f"Weekly numbers: vitality_scores count failed: {e}")

    # 3. Badge outreach from badge_outreach_log.json (contacted entries in last 7 days)
    badge_outreach = 0
    try:
        if BADGE_OUTREACH_LOG_PATH.exists():
            log_data = json.loads(BADGE_OUTREACH_LOG_PATH.read_text(encoding="utf-8"))
            contacted = log_data.get("contacted", {})
            cutoff_dt = datetime.now(timezone.utc) - timedelta(days=7)
            for key, val in contacted.items():
                try:
                    ts = val if isinstance(val, str) else val.get("timestamp", val.get("date", ""))
                    if isinstance(ts, str) and ts:
                        # Try parsing ISO format
                        entry_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if entry_dt >= cutoff_dt:
                            badge_outreach += 1
                    else:
                        # Count all entries if no parseable timestamp
                        badge_outreach += 1
                except (ValueError, TypeError, AttributeError):
                    badge_outreach += 1  # Count if we can't parse date
    except Exception as e:
        logger.warning(f"Weekly numbers: badge outreach count failed: {e}")

    return (
        f"\n\n---\n**This Week at Nerq:** {new_agents} new agents indexed "
        f"· {tokens_scored} tokens scored · {badge_outreach} badge outreach issues opened"
    )


# ── Step 1: DISCOVER ─────────────────────────────────────────

def _pg_connect():
    """Connect to PostgreSQL via psycopg2."""
    if not psycopg2:
        raise RuntimeError("psycopg2 not installed")
    from agentindex.db_config import get_read_conn
    return get_read_conn()


def discover() -> list[dict]:
    """Find top 10 uncontacted high-trust agents."""
    try:
        conn = _pg_connect()
        conn.set_session(readonly=True)
        cur = conn.cursor()

        # Check if nerq_scout_log table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'nerq_scout_log'
            )
        """)
        has_scout_log = cur.fetchone()[0]

        if has_scout_log:
            cur.execute("""
                SELECT a.name, a.source_url, a.trust_score_v2, a.stars, a.category, a.agent_type
                FROM agents a
                LEFT JOIN nerq_scout_log sl
                    ON sl.event_type = 'scout_evaluate'
                    AND sl.agent_name = a.name
                WHERE a.trust_score_v2 >= 85
                  AND a.stars >= 100
                  AND a.source = 'github'
                  AND a.is_active = true
                  AND a.agent_type IN ('agent', 'tool', 'mcp_server')
                  AND sl.id IS NULL
                ORDER BY a.trust_score_v2 DESC
                LIMIT 10
            """)
        else:
            cur.execute("""
                SELECT name, source_url, trust_score_v2, stars, category, agent_type
                FROM agents
                WHERE trust_score_v2 >= 85
                  AND stars >= 100
                  AND source = 'github'
                  AND is_active = true
                  AND agent_type IN ('agent', 'tool', 'mcp_server')
                ORDER BY trust_score_v2 DESC
                LIMIT 10
            """)

        agents = []
        for r in cur.fetchall():
            agents.append({
                "name": r[0],
                "source_url": r[1],
                "trust_score_v2": float(r[2]) if r[2] else None,
                "stars": r[3],
                "category": r[4],
                "agent_type": r[5],
            })

        cur.close()
        conn.close()

        logger.info(f"DISCOVER: Found {len(agents)} uncontacted agents")
        for a in agents:
            logger.info(f"  - {a['name']} (trust={a['trust_score_v2']}, stars={a['stars']})")

        return agents
    except Exception as e:
        logger.error(f"DISCOVER failed: {e}")
        return []


# ── Step 2: EVALUATE ─────────────────────────────────────────

def _http_get_json(url: str, headers: dict = None, timeout: int = 15) -> tuple[int, dict]:
    """HTTP GET returning (status_code, json_body). Uses requests if available, else urllib."""
    if _requests_lib:
        resp = _requests_lib.get(url, headers=headers, timeout=timeout)
        return resp.status_code, resp.json() if resp.status_code == 200 else {}
    req = urllib.request.Request(url)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}


def evaluate(agents: list[dict]) -> list[dict]:
    """Call KYA endpoint for each agent and log results."""
    results = []

    # Open Postgres connection for logging
    pg_conn = None
    pg_cur = None
    try:
        pg_conn = _pg_connect()
        pg_cur = pg_conn.cursor()
        # Ensure nerq_scout_log exists
        pg_cur.execute("""
            CREATE TABLE IF NOT EXISTS nerq_scout_log (
                id SERIAL PRIMARY KEY,
                event_type TEXT,
                agent_name TEXT,
                details TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        pg_conn.commit()
    except Exception as e:
        logger.warning(f"EVALUATE: Cannot open Postgres for logging: {e}")

    for agent in agents:
        name = agent["name"]
        try:
            status, data = _http_get_json(
                f"{KYA_BASE}/{name}",
                headers={"X-API-Key": KYA_API_KEY},
            )
            if status == 200:
                result = {
                    "name": name,
                    "trust_score": data.get("trust_score"),
                    "grade": data.get("trust_grade") or data.get("grade"),
                    "category": data.get("category"),
                    "source_url": agent.get("source_url"),
                    "stars": agent.get("stars"),
                    "agent_type": agent.get("agent_type"),
                }
            else:
                result = {
                    "name": name,
                    "trust_score": agent.get("trust_score_v2"),
                    "grade": None,
                    "category": agent.get("category"),
                    "source_url": agent.get("source_url"),
                    "stars": agent.get("stars"),
                    "agent_type": agent.get("agent_type"),
                    "error": f"KYA returned {status}",
                }

            logger.info(
                f"EVALUATE: {name} -> score={result.get('trust_score')}, "
                f"grade={result.get('grade')}"
            )

            # Log to nerq_scout_log
            if pg_cur:
                try:
                    pg_cur.execute("""
                        INSERT INTO nerq_scout_log (event_type, agent_name, details)
                        VALUES ('scout_evaluate', %s, %s)
                    """, (name, json.dumps({
                        "trust_score": result.get("trust_score"),
                        "grade": result.get("grade"),
                        "category": result.get("category"),
                        "source_url": result.get("source_url"),
                    })))
                    pg_conn.commit()
                except Exception as e:
                    logger.warning(f"EVALUATE: Failed to log {name}: {e}")
                    try:
                        pg_conn.rollback()
                    except Exception:
                        pass

            results.append(result)

        except Exception as e:
            logger.error(f"EVALUATE: Failed for {name}: {e}")
            results.append({
                "name": name,
                "error": str(e),
                "trust_score": agent.get("trust_score_v2"),
                "category": agent.get("category"),
                "source_url": agent.get("source_url"),
                "stars": agent.get("stars"),
                "agent_type": agent.get("agent_type"),
            })

    if pg_cur:
        try:
            pg_cur.close()
        except Exception:
            pass
    if pg_conn:
        try:
            pg_conn.close()
        except Exception:
            pass

    logger.info(f"EVALUATE: Completed {len(results)}/{len(agents)} agents")
    return results


# ── Step 3: PUBLISH ──────────────────────────────────────────

def publish(results: list[dict]) -> Path | None:
    """Generate scout report, save markdown, publish to Dev.to."""
    if not results:
        logger.info("PUBLISH: No results to publish")
        return None

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Build data summary for the LLM
    agents_summary = "\n".join(
        f"- {r['name']}: trust={r.get('trust_score', 'N/A')}, "
        f"grade={r.get('grade', 'N/A')}, category={r.get('category', 'N/A')}, "
        f"stars={r.get('stars', 'N/A')}, type={r.get('agent_type', 'N/A')}, "
        f"report: https://nerq.ai/safe/{r['name']}"
        for r in results
    )

    prompt = f"""Write a daily scout report for {date_str}.

Agents discovered and evaluated today:
{agents_summary}

Write a short report with:
1. A title line starting with #
2. One-paragraph summary
3. Table of agents (Name, Trust Score, Grade, Category, Stars)
4. Key observations (2-3 bullet points)
5. For each agent mentioned, include a link to its trust report at https://nerq.ai/safe/{{name}}
6. End with links to the Nerq ecosystem: https://nerq.ai/compare for comparisons, https://zarq.ai/crash-watch for crypto risk monitoring

Return ONLY the markdown. Start with # on the first line."""

    # Try Ollama
    body_md = None
    try:
        logger.info("PUBLISH: Generating report with Ollama...")
        payload = json.dumps({
            "model": MODEL,
            "prompt": prompt,
            "system": SYSTEM_PROMPT,
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": 1500},
        }).encode("utf-8")
        req = urllib.request.Request(OLLAMA_URL, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            body_md = json.loads(resp.read().decode()).get("response", "").strip()
        logger.info("PUBLISH: Ollama report generated")
    except Exception as e:
        logger.warning(f"PUBLISH: Ollama failed ({e}), using template fallback")

    # Fallback template
    if not body_md:
        body_md = _fallback_report(results, date_str)

    # Enhancement 1: Append vitality anomaly footer for high-scoring results
    high_trust = [r for r in results if (r.get("trust_score") or 0) >= 85]
    if high_trust:
        anomaly_footer = _vitality_anomaly_footer()
        if anomaly_footer:
            body_md += anomaly_footer

    # Add YAML frontmatter
    lines = body_md.split("\n")
    title = lines[0].lstrip("# ").strip() if lines else f"Scout Report — {date_str}"
    full_md = f"""---
title: "{title}"
date: {date_str}
type: scout
---

{body_md}"""

    # Save to disk
    report_path = REPORTS_DIR / f"{date_str}-scout.md"
    report_path.write_text(full_md, encoding="utf-8")
    logger.info(f"PUBLISH: Saved {report_path}")
    print(f"Saved: {report_path}")

    # Publish to Dev.to
    _publish_devto(title, body_md, date_str)

    # Print summary
    print(f"\n--- Scout Summary ({date_str}) ---")
    print(f"Agents evaluated: {len(results)}")
    for r in results:
        score = r.get("trust_score", "?")
        grade = r.get("grade", "?")
        print(f"  {r['name']}: {score} ({grade})")
    print(f"Report: {report_path}")

    return report_path


def _fallback_report(results: list[dict], date_str: str) -> str:
    """Template-based report when Ollama is unavailable."""
    table_rows = "\n".join(
        f"| [{r['name']}](https://nerq.ai/safe/{r['name']}) | {r.get('trust_score', 'N/A')} | "
        f"{r.get('grade', 'N/A')} | {r.get('category', 'N/A')} | "
        f"{r.get('stars', 'N/A')} |"
        for r in results
    )

    return f"""# Nerq Scout Report — {date_str}

Today the Nerq Scout evaluated {len(results)} high-trust AI agents from GitHub. These agents scored 85+ on the Nerq Trust Index and have 100+ stars.

## Agents Evaluated

| Name | Trust Score | Grade | Category | Stars |
|------|------------|-------|----------|-------|
{table_rows}

See all agent comparisons at [nerq.ai/compare](https://nerq.ai/compare).

## Observations

- {len(results)} agents met the scout criteria (trust >= 85, stars >= 100, GitHub source).
- All agents were evaluated via the Nerq KYA (Know Your Agent) endpoint.
- Reports are generated daily and published to the Nerq blog.

---
*Data from the [Nerq](https://nerq.ai) index. Browse agents at [nerq.ai/safe](https://nerq.ai/safe). Crypto risk: [zarq.ai/crash-watch](https://zarq.ai/crash-watch) | [zarq.ai/tokens](https://zarq.ai/tokens). Generated {date_str}.*
"""


def _publish_devto(title: str, body_md: str, date_str: str):
    """Publish report to Dev.to as published article."""
    if not DEVTO_KEY_PATH.exists():
        logger.info("PUBLISH: No Dev.to API key found, skipping")
        print("Dev.to: No API key found, skipping. Add key to ~/.config/nerq/devto_api_key")
        return None

    api_key = DEVTO_KEY_PATH.read_text().strip()
    if not api_key:
        logger.info("PUBLISH: Empty Dev.to API key, skipping")
        return None

    # Enhancement 3: Add weekly numbers footer
    weekly_footer = _weekly_numbers_footer()

    body_with_canonical = (
        body_md
        + weekly_footer
        + f"\n\n---\n*Originally published on [nerq.ai](https://nerq.ai/blog/{date_str}-scout). Explore agents: [nerq.ai/safe](https://nerq.ai/safe) | Compare: [nerq.ai/compare](https://nerq.ai/compare)*"
    )

    payload = {
        "article": {
            "title": title,
            "body_markdown": body_with_canonical,
            "published": True,
            "tags": ["ai", "agents", "trust", "opensource"],
            "canonical_url": f"https://nerq.ai/blog/{date_str}-scout",
            "description": f"Nerq Scout daily report: {date_str}",
        }
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://dev.to/api/articles",
            data=data,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            url = result.get("url", "")
            logger.info(f"PUBLISH: Dev.to published — {url}")
            print(f"Dev.to: Published — {url}")
            return url
    except Exception as e:
        logger.warning(f"PUBLISH: Dev.to failed — {e}")
        print(f"Dev.to: Failed — {e}")
        return None


# ── Main ─────────────────────────────────────────────────────

def main():
    t0 = time.time()
    logger.info("=" * 50)
    logger.info("Nerq Scout Agent starting")
    logger.info("=" * 50)

    print("=" * 50)
    print(f"Nerq Scout Agent — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 50)

    # Step 1
    print("\n1. DISCOVER: Finding uncontacted high-trust agents...")
    agents = discover()
    t1 = time.time()
    print(f"   Found {len(agents)} agents ({t1 - t0:.1f}s)")

    if not agents:
        print("   No new agents to evaluate. Done.")
        logger.info("No new agents found. Exiting.")
        return

    # Step 2
    print(f"\n2. EVALUATE: Calling KYA for {len(agents)} agents...")
    results = evaluate(agents)
    t2 = time.time()
    print(f"   Evaluated {len(results)} agents ({t2 - t1:.1f}s)")

    # Step 3
    print("\n3. PUBLISH: Generating and publishing report...")
    report_path = publish(results)
    t3 = time.time()
    print(f"   Published ({t3 - t2:.1f}s)")

    # Step 4: Post to Bluesky (Enhancement 2: 1-in-4 posts include Token Alert)
    print("\n4. BLUESKY: Posting summary...")
    try:
        from agentindex.bluesky_bot import post_scout_summary
        post_scout_summary(results)

        # 1 in 4 posts: append a Token Alert about biggest vitality mover
        if random.randint(1, 4) == 1:
            mover = _biggest_vitality_mover()
            if mover:
                name = mover.get("name") or mover.get("token") or mover.get("symbol") or "Unknown"
                delta = float(mover.get("vitality_delta", 0))
                score = mover.get("vitality_score", "?")
                direction = "up" if delta > 0 else "down"
                alert_line = f"\U0001f514 Token Alert: {name} vitality {direction} {abs(delta):.1f}pts to {score}"
                try:
                    from agentindex.bluesky_bot import post_text
                    post_text(alert_line)
                    logger.info(f"BLUESKY: Token Alert posted — {alert_line}")
                    print(f"   Bluesky: Token Alert posted")
                except Exception as e2:
                    logger.warning(f"Bluesky Token Alert failed: {e2}")
    except Exception as e:
        logger.warning(f"Bluesky posting failed: {e}")
        print(f"   Bluesky: Skipped ({e})")
    t4 = time.time()

    total = t4 - t0
    print(f"\nTotal time: {total:.1f}s")
    logger.info(f"Scout Agent completed in {total:.1f}s — {len(results)} agents evaluated")


if __name__ == "__main__":
    main()
