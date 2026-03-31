"""
Auto Publisher — Weekly AI agent ecosystem report
Generates data-driven articles from live DB, publishes to nerq.ai/blog and Dev.to.
Run: python -m agentindex.crypto.auto_publisher
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

REPORTS_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "auto-reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b"

DEVTO_KEY_PATH = Path.home() / ".config" / "nerq" / "devto_api_key"

SYSTEM_PROMPT = (
    "You are a technical writer for Nerq, the AI Asset Search Engine indexing 5M+ AI assets. "
    "Write concise, data-driven weekly reports about the AI agent ecosystem. "
    "No hype, no fluff. Facts and numbers. Markdown format. "
    "Use ## for sections. Keep the tone professional and analytical, like a financial report. "
    "Do not use emojis. Do not invent data — only use what is provided."
)


# ── Data Collection ──────────────────────────────────────────

def _get_db_session():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from agentindex.db.models import get_session
    return get_session()


def collect_data() -> dict:
    """Query live DB for weekly report data."""
    from sqlalchemy import text
    session = _get_db_session()
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    try:
        # 1. Total counts
        totals = session.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE agent_type IN ('agent','tool','mcp_server')) AS agents_tools,
                COUNT(*) FILTER (WHERE agent_type IN ('model','dataset')) AS models_datasets,
                COUNT(*) AS total
            FROM agents WHERE is_active = true
        """)).fetchone()

        # 2. New agents this week (top 10 by trust)
        new_agents = session.execute(text("""
            SELECT name, source, category, trust_score_v2, stars, agent_type
            FROM agents
            WHERE is_active = true
              AND first_indexed >= :week_ago
              AND agent_type IN ('agent','tool','mcp_server')
              AND trust_score_v2 IS NOT NULL
            ORDER BY trust_score_v2 DESC
            LIMIT 10
        """), {"week_ago": week_ago.isoformat()}).fetchall()

        new_count = session.execute(text("""
            SELECT COUNT(*) FROM agents
            WHERE is_active = true
              AND first_indexed >= :week_ago
              AND agent_type IN ('agent','tool','mcp_server')
        """), {"week_ago": week_ago.isoformat()}).scalar() or 0

        # 3. Framework trends
        fw_trends = session.execute(text("""
            WITH fw AS (
                SELECT unnest(frameworks) AS framework,
                       CASE WHEN first_indexed >= :week_ago THEN 1 ELSE 0 END AS is_new
                FROM agents
                WHERE is_active = true
                  AND agent_type IN ('agent','tool','mcp_server')
                  AND frameworks IS NOT NULL
            )
            SELECT framework, COUNT(*) AS total, SUM(is_new) AS new_this_week
            FROM fw
            GROUP BY framework
            HAVING COUNT(*) >= 10
            ORDER BY SUM(is_new) DESC, COUNT(*) DESC
            LIMIT 12
        """), {"week_ago": week_ago.isoformat()}).fetchall()

        # 4. Category trends
        cat_trends = session.execute(text("""
            SELECT category,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE first_indexed >= :week_ago) AS new_this_week
            FROM agents
            WHERE is_active = true
              AND agent_type IN ('agent','tool','mcp_server')
              AND category IS NOT NULL AND category != ''
            GROUP BY category
            ORDER BY COUNT(*) FILTER (WHERE first_indexed >= :week_ago) DESC, COUNT(*) DESC
            LIMIT 10
        """), {"week_ago": week_ago.isoformat()}).fetchall()

        # 5. New MCP servers
        new_mcp = session.execute(text("""
            SELECT name, source, trust_score_v2, description
            FROM agents
            WHERE is_active = true
              AND agent_type = 'mcp_server'
              AND first_indexed >= :week_ago
              AND trust_score_v2 IS NOT NULL
            ORDER BY trust_score_v2 DESC
            LIMIT 5
        """), {"week_ago": week_ago.isoformat()}).fetchall()

        new_mcp_count = session.execute(text("""
            SELECT COUNT(*) FROM agents
            WHERE is_active = true AND agent_type = 'mcp_server'
              AND first_indexed >= :week_ago
        """), {"week_ago": week_ago.isoformat()}).scalar() or 0

        # 6. Agent of the week (highest trust newcomer)
        agent_of_week = session.execute(text("""
            SELECT name, source, category, trust_score_v2, stars, description, source_url
            FROM agents
            WHERE is_active = true
              AND first_indexed >= :week_ago
              AND agent_type IN ('agent','tool','mcp_server')
              AND trust_score_v2 IS NOT NULL
            ORDER BY trust_score_v2 DESC
            LIMIT 1
        """), {"week_ago": week_ago.isoformat()}).fetchone()

        # 7. Trust score distribution
        trust_dist = session.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE trust_score_v2 >= 70) AS high,
                COUNT(*) FILTER (WHERE trust_score_v2 >= 40 AND trust_score_v2 < 70) AS medium,
                COUNT(*) FILTER (WHERE trust_score_v2 < 40) AS low,
                ROUND(AVG(trust_score_v2)::numeric, 1) AS avg_trust
            FROM agents
            WHERE is_active = true
              AND agent_type IN ('agent','tool','mcp_server')
              AND trust_score_v2 IS NOT NULL
        """)).fetchone()

        # 8. Source platform breakdown
        sources = session.execute(text("""
            SELECT source, COUNT(*) AS cnt
            FROM agents
            WHERE is_active = true AND agent_type IN ('agent','tool','mcp_server')
            GROUP BY source ORDER BY cnt DESC LIMIT 8
        """)).fetchall()

        data = {
            "report_date": now.strftime("%Y-%m-%d"),
            "week_start": week_ago.strftime("%Y-%m-%d"),
            "total_agents_tools": totals[0],
            "total_models_datasets": totals[1],
            "total_assets": totals[2],
            "new_agents_this_week": new_count,
            "top_new_agents": [
                {"name": r[0], "source": r[1], "category": r[2],
                 "trust_score": float(r[3]) if r[3] else None, "stars": r[4], "type": r[5]}
                for r in new_agents
            ],
            "framework_trends": [
                {"framework": r[0], "total": r[1], "new_this_week": r[2]}
                for r in fw_trends
            ],
            "category_trends": [
                {"category": r[0], "total": r[1], "new_this_week": r[2]}
                for r in cat_trends
            ],
            "new_mcp_servers": {
                "count": new_mcp_count,
                "top": [
                    {"name": r[0], "source": r[1], "trust_score": float(r[2]) if r[2] else None,
                     "description": (r[3] or "")[:200]}
                    for r in new_mcp
                ],
            },
            "agent_of_the_week": {
                "name": agent_of_week[0],
                "source": agent_of_week[1],
                "category": agent_of_week[2],
                "trust_score": float(agent_of_week[3]) if agent_of_week[3] else None,
                "stars": agent_of_week[4],
                "description": (agent_of_week[5] or "")[:300],
                "url": agent_of_week[6],
            } if agent_of_week else None,
            "trust_distribution": {
                "high": trust_dist[0], "medium": trust_dist[1],
                "low": trust_dist[2], "avg": float(trust_dist[3]) if trust_dist[3] else None,
            },
            "source_platforms": [
                {"source": r[0], "count": r[1]} for r in sources
            ],
        }
        return data
    finally:
        session.close()


# ── Article Generation ───────────────────────────────────────

def generate_article(data: dict) -> dict:
    """Send data to Ollama qwen2.5:7b to generate article."""
    prompt = f"""Write a weekly report for Nerq's AI Agent Ecosystem Weekly for the week ending {data['report_date']}.

Here is the raw data to base the report on:

TOTALS:
- {data['total_agents_tools']:,} agents, tools & MCP servers indexed
- {data['total_models_datasets']:,} models & datasets indexed
- {data['total_assets']:,} total AI assets
- {data['new_agents_this_week']:,} new agents/tools added this week

TOP NEW AGENTS (by trust score):
{json.dumps(data['top_new_agents'], indent=2)}

FRAMEWORK TRENDS (total count + new this week):
{json.dumps(data['framework_trends'], indent=2)}

CATEGORY TRENDS:
{json.dumps(data['category_trends'], indent=2)}

NEW MCP SERVERS: {data['new_mcp_servers']['count']} new this week
Top new MCP servers:
{json.dumps(data['new_mcp_servers']['top'], indent=2)}

AGENT OF THE WEEK:
{json.dumps(data['agent_of_the_week'], indent=2)}

TRUST SCORE DISTRIBUTION:
{json.dumps(data['trust_distribution'], indent=2)}

SOURCE PLATFORMS:
{json.dumps(data['source_platforms'], indent=2)}

Write the report with these sections:
1. Title (one line, descriptive)
2. One-paragraph summary (3-4 sentences)
3. This Week in Numbers (key stats)
4. Agent of the Week (profile the top newcomer)
5. Framework Trends (which frameworks are growing)
6. MCP Server Growth (if any new ones)
7. Trust & Compliance (distribution analysis)
8. Outlook (1-2 sentences)

Return ONLY the markdown article. Start with a # title on the first line."""

    print(f"Generating article with {MODEL}...")
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "system": SYSTEM_PROMPT,
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": 2000},
        }, timeout=120)
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
    except Exception as e:
        print(f"Ollama error: {e}")
        text = _fallback_article(data)

    # Extract title from first line
    lines = text.split("\n")
    title = lines[0].lstrip("# ").strip() if lines else f"AI Agent Ecosystem Weekly — {data['report_date']}"

    # Extract summary (first paragraph after title)
    summary = ""
    for line in lines[1:]:
        line = line.strip()
        if line and not line.startswith("#"):
            summary = line
            break

    return {"title": title, "summary": summary, "body": text}


def _fallback_article(data: dict) -> str:
    """Generate a basic article without LLM if Ollama fails."""
    d = data
    aotw = d.get("agent_of_the_week") or {}
    top_agents = "\n".join(
        f"| {a['name']} | {a['source']} | {a['trust_score']:.0f} | {a.get('stars') or '—'} |"
        for a in d["top_new_agents"][:5]
    )
    fw_lines = "\n".join(
        f"| {f['framework']} | {f['total']:,} | +{f['new_this_week']} |"
        for f in d["framework_trends"][:8]
    )

    return f"""# AI Agent Ecosystem Weekly — {d['report_date']}

The Nerq index now tracks {d['total_agents_tools']:,} agents, tools, and MCP servers alongside {d['total_models_datasets']:,} models and datasets. This week, {d['new_agents_this_week']:,} new entries were added to the index.

## This Week in Numbers

- **{d['total_assets']:,}** total AI assets indexed
- **{d['new_agents_this_week']:,}** new agents and tools this week
- **{d['new_mcp_servers']['count']}** new MCP servers
- **{d['trust_distribution']['avg']}** average trust score

## Agent of the Week

**{aotw.get('name', 'N/A')}** ({aotw.get('source', '')}) — Trust Score: {aotw.get('trust_score', 'N/A')}

{aotw.get('description', '')}

## Top New Agents

| Name | Source | Trust | Stars |
|------|--------|-------|-------|
{top_agents}

## Framework Trends

| Framework | Total Agents | New This Week |
|-----------|-------------|---------------|
{fw_lines}

## Trust Distribution

- High trust (70+): {d['trust_distribution']['high']:,}
- Medium trust (40-69): {d['trust_distribution']['medium']:,}
- Low trust (<40): {d['trust_distribution']['low']:,}

## Outlook

The agent ecosystem continues to expand. MCP adoption remains strong with {d['new_mcp_servers']['count']} new servers this week.

---
*Data from the [Nerq](https://nerq.ai) index. Generated {d['report_date']}.*
"""


# ── Save & Publish ───────────────────────────────────────────

def save_report(article: dict, data: dict) -> Path:
    """Save markdown + raw data JSON."""
    date_str = data["report_date"]
    slug = f"{date_str}-weekly"
    md_path = REPORTS_DIR / f"{slug}.md"
    json_path = REPORTS_DIR / f"{slug}-data.json"

    md_path.write_text(article["body"], encoding="utf-8")
    json_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    print(f"Saved: {md_path}")
    print(f"Saved: {json_path}")
    return md_path


def publish_devto(article: dict, data: dict):
    """Publish to Dev.to as draft if API key exists."""
    if not DEVTO_KEY_PATH.exists():
        print("Dev.to: No API key found, skipping. Add key to ~/.config/nerq/devto_api_key")
        return None

    api_key = DEVTO_KEY_PATH.read_text().strip()
    if not api_key:
        print("Dev.to: Empty API key, skipping.")
        return None

    tags = ["ai", "agents", "mcp", "machinelearning"]
    body = article["body"]
    # Append canonical link
    date_str = data["report_date"]
    body += f"\n\n---\n*Originally published on [nerq.ai](https://nerq.ai/blog/{date_str}-weekly)*"

    payload = {
        "article": {
            "title": article["title"],
            "body_markdown": body,
            "published": True,  # Auto-publish — Scout + weekly reports go live
            "tags": tags,
            "canonical_url": f"https://nerq.ai/blog/{date_str}-weekly",
            "description": article["summary"][:150],
        }
    }

    try:
        resp = requests.post(
            "https://dev.to/api/articles",
            json=payload,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        url = resp.json().get("url", "")
        print(f"Dev.to: Draft created — {url}")
        return url
    except Exception as e:
        print(f"Dev.to: Failed — {e}")
        return None


# ── Main ─────────────────────────────────────────────────────

def run():
    """Generate and publish weekly report."""
    print("=" * 60)
    print(f"Auto Publisher — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    print("\n1. Collecting data from live DB...")
    data = collect_data()
    print(f"   {data['new_agents_this_week']:,} new agents this week")
    print(f"   {data['total_agents_tools']:,} total agents/tools")

    print("\n2. Generating article...")
    article = generate_article(data)
    print(f"   Title: {article['title']}")

    print("\n3. Saving report...")
    save_report(article, data)

    print("\n4. Publishing to Dev.to...")
    publish_devto(article, data)

    print(f"\n{'=' * 60}")
    print(f"Done. Article live at: https://nerq.ai/blog/{data['report_date']}-weekly")
    print("=" * 60)


if __name__ == "__main__":
    run()
