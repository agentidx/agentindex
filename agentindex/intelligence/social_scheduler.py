"""
Social Scheduler — Daily 12:00
==============================
Auto-generates and posts daily social content to Bluesky.

Schedule:
  Monday:    "State of the Agent Economy" summary
  Tuesday:   "Top 10 Most Trusted AI Agents This Week"
  Wednesday: "Rising Agents" (biggest trust score gains)
  Thursday:  "Framework Spotlight"
  Friday:    "Security Roundup: N new CVEs"
  Saturday:  "Developer Tip"
  Sunday:    "Weekend Read" (link to latest blog post)

Usage:
    python -m agentindex.intelligence.social_scheduler
"""

import json
import logging
import sqlite3
from datetime import datetime

from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [social] %(message)s")
logger = logging.getLogger("social")

from agentindex.db.models import get_session

SQLITE_DB = "/Users/anstudio/agentindex/data/crypto_trust.db"


def _post_bluesky(content: str) -> bool:
    """Post to Bluesky via existing mechanism."""
    try:
        from agentindex.bluesky_bot import post_to_bluesky
        post_to_bluesky(content)
        return True
    except Exception as e:
        logger.warning(f"Could not post to Bluesky: {e}")
        # Save content for manual posting
        try:
            with open("/Users/anstudio/agentindex/logs/social_queue.txt", "a") as f:
                f.write(f"\n---\n{datetime.now().isoformat()}\n{content}\n")
        except:
            pass
        return False


def monday_post():
    """State of the Agent Economy."""
    s = get_session()
    try:
        total = s.execute(text("SELECT COUNT(*) FROM entity_lookup WHERE is_active = true")).scalar() or 0
        mcp = s.execute(text("SELECT COUNT(*) FROM entity_lookup WHERE agent_type = 'mcp_server'")).scalar() or 0
        avg_score = s.execute(text("SELECT AVG(COALESCE(trust_score_v2, trust_score)) FROM entity_lookup WHERE COALESCE(trust_score_v2, trust_score) IS NOT NULL")).scalar() or 0
        new_7d = s.execute(text("SELECT COUNT(*) FROM entity_lookup WHERE first_indexed > NOW() - INTERVAL '7 days'")).scalar() or 0
        s.close()
    except:
        s.close()
        return "🌐 State of the Agent Economy\n\nThe AI agent ecosystem continues to grow. Check nerq.ai for the latest data."

    return (
        f"🌐 State of the Agent Economy — Week of {datetime.now().strftime('%B %d')}\n\n"
        f"📊 {total:,} AI assets indexed\n"
        f"🔧 {mcp:,} MCP servers\n"
        f"📈 {new_7d:,} new assets this week\n"
        f"⭐ Average trust score: {avg_score:.0f}/100\n\n"
        f"Search and verify any AI agent: nerq.ai"
    )


def tuesday_post():
    """Top 10 Most Trusted."""
    s = get_session()
    try:
        rows = s.execute(text("""
            SELECT name, COALESCE(trust_score_v2, trust_score) as ts, trust_grade
            FROM entity_lookup WHERE is_active = true AND COALESCE(trust_score_v2, trust_score) IS NOT NULL AND stars > 100
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC LIMIT 10
        """)).fetchall()
        s.close()
    except:
        s.close()
        return "🏆 Top 10 Most Trusted AI Agents This Week\n\nCheck nerq.ai/verified for the full list."

    lines = [f"🏆 Top 10 Most Trusted AI Agents This Week\n"]
    for i, r in enumerate(rows, 1):
        d = dict(r._mapping)
        lines.append(f"{i}. {d['name']} — {d['ts']:.0f}/100 ({d['trust_grade']})")
    lines.append(f"\nFull rankings: nerq.ai/verified")
    return "\n".join(lines)


def wednesday_post():
    """Rising Agents."""
    s = get_session()
    try:
        rows = s.execute(text("""
            SELECT name, trust_score, trust_score_v2,
                   COALESCE(trust_score_v2, 0) - COALESCE(trust_score, 0) as delta
            FROM entity_lookup
            WHERE trust_score IS NOT NULL AND trust_score_v2 IS NOT NULL
              AND COALESCE(trust_score_v2, 0) > COALESCE(trust_score, 0)
            ORDER BY delta DESC LIMIT 5
        """)).fetchall()
        s.close()
    except:
        s.close()
        return "📈 Rising Agents\n\nSee which agents are improving: nerq.ai"

    lines = ["📈 Rising Agents — Biggest Trust Score Gains\n"]
    for r in rows:
        d = dict(r._mapping)
        lines.append(f"⬆️ {d['name']}: +{d['delta']:.0f} points ({d['trust_score']:.0f} → {d['trust_score_v2']:.0f})")
    lines.append("\nTrack trust trends: nerq.ai")
    return "\n".join(lines)


def thursday_post():
    """Framework Spotlight."""
    s = get_session()
    try:
        rows = s.execute(text("""
            SELECT category, COUNT(*) as cnt, AVG(COALESCE(trust_score_v2, trust_score)) as avg_ts
            FROM entity_lookup WHERE category IS NOT NULL AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
            GROUP BY category HAVING COUNT(*) >= 10
            ORDER BY avg_ts DESC LIMIT 5
        """)).fetchall()
        s.close()
    except:
        s.close()
        return "🔍 Framework Spotlight\n\nExplore AI frameworks: nerq.ai"

    lines = ["🔍 Framework Spotlight — Top Categories by Trust\n"]
    for r in rows:
        d = dict(r._mapping)
        lines.append(f"📂 {d['category']}: {d['cnt']} agents, avg trust {d['avg_ts']:.0f}/100")
    lines.append("\nExplore all categories: nerq.ai/discover")
    return "\n".join(lines)


def friday_post():
    """Security Roundup."""
    try:
        conn = sqlite3.connect(SQLITE_DB, timeout=10)
        count = conn.execute("SELECT COUNT(*) FROM agent_vulnerabilities").fetchone()[0]
        recent = conn.execute(
            "SELECT COUNT(*) FROM agent_vulnerabilities WHERE published_date > date('now', '-7 days')"
        ).fetchone()[0]
        critical = conn.execute(
            "SELECT COUNT(*) FROM agent_vulnerabilities WHERE severity = 'CRITICAL'"
        ).fetchone()[0]
        conn.close()
    except:
        count, recent, critical = 0, 0, 0

    return (
        f"🔒 Security Roundup — Week of {datetime.now().strftime('%B %d')}\n\n"
        f"🆕 {recent} new CVEs this week\n"
        f"⚠️ {critical} critical vulnerabilities tracked\n"
        f"📊 {count} total CVEs in database\n\n"
        f"Check your agents: nerq check <agent-name>\n"
        f"RSS feed: nerq.ai/feed/cve-alerts.xml"
    )


def saturday_post():
    """Developer Tip."""
    tips = [
        "💡 Developer Tip: Add trust verification to your CI/CD pipeline.\n\nUse our GitHub Action:\n  nerq-ai/trust-check-action@v1\n\nOr pre-commit hook:\n  pip install nerq && nerq scan requirements.txt\n\nBlock risky dependencies before they ship. nerq.ai",
        "💡 Developer Tip: Check agent trust before `pip install`.\n\n$ nerq check langchain\n╭──────────────────────╮\n│ Trust Score: 78/100  │\n│ Grade: B             │\n│ Recommendation: PROCEED │\n╰──────────────────────╯\n\nInstall: pip install nerq",
        "💡 Developer Tip: Add trust badges to your README.\n\n[![Nerq Trust](https://nerq.ai/badge/your-agent)](https://nerq.ai/safe/your-agent)\n\nShow users your agent is independently verified. nerq.ai/badges",
        "💡 Developer Tip: Use the MCP server for real-time trust checks.\n\nConnect to mcp.nerq.ai/sse from Claude, Cursor, or VS Code.\nNo API key needed. 22 tools available.\n\nnerq.ai",
    ]
    day_of_year = datetime.now().timetuple().tm_yday
    return tips[day_of_year % len(tips)]


def sunday_post():
    """Weekend Read."""
    try:
        conn = sqlite3.connect(SQLITE_DB, timeout=10)
        row = conn.execute(
            "SELECT slug, title FROM auto_comparisons ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            return f"📖 Weekend Read\n\n{row[1]}\n\nnerq.ai/blog/{row[0]}"
    except:
        pass
    return "📖 Weekend Read\n\nExplore the latest AI agent comparisons and trust data.\n\nnerq.ai/blog"


def run():
    """Generate and post today's content."""
    weekday = datetime.now().weekday()
    generators = {
        0: monday_post,
        1: tuesday_post,
        2: wednesday_post,
        3: thursday_post,
        4: friday_post,
        5: saturday_post,
        6: sunday_post,
    }

    content = generators[weekday]()
    logger.info(f"Generated post for {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][weekday]}:")
    logger.info(content)

    posted = _post_bluesky(content)
    return {"weekday": weekday, "content": content, "posted": posted}


def main():
    logger.info("=" * 60)
    logger.info("Social Scheduler — starting")
    logger.info("=" * 60)
    result = run()
    logger.info(f"Posted: {result['posted']}")


if __name__ == "__main__":
    main()
