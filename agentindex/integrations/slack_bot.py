"""
Nerq Slack Bot — Slash command handler
=======================================
Handles /nerq slash commands from Slack.

Routes:
  POST /integrations/slack    — Slack slash command endpoint
  GET  /integrations/slack    — Documentation page

Commands:
  /nerq check <agent>         — Trust score card
  /nerq compare <a> vs <b>    — Side-by-side comparison
  /nerq recommend <task>      — Top 3 recommendations
"""

import json
import logging
import urllib.parse
import urllib.request
from typing import Optional

from fastapi import Request, Form
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger("nerq.slack")

API_BASE = "https://nerq.ai"


def _api_get(path: str) -> dict:
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "nerq-slack-bot/1.0"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def _check_response(agent: str) -> dict:
    """Build Slack block response for trust check."""
    try:
        data = _api_get(f"/v1/preflight?target={urllib.parse.quote(agent)}")
        score = data.get("trust_score", 0)
        grade = data.get("grade", "?")
        rec = data.get("recommendation", "UNKNOWN")
        cves = data.get("security", {}).get("known_cves", 0)
        cat = data.get("category", "")

        color = "#22c55e" if rec == "PROCEED" else "#eab308" if rec == "CAUTION" else "#ef4444"
        slug = agent.lower().replace("/", "").replace(" ", "-")

        return {
            "response_type": "in_channel",
            "attachments": [{
                "color": color,
                "blocks": [
                    {"type": "header", "text": {"type": "plain_text", "text": f"🛡️ {agent}"}},
                    {"type": "section", "fields": [
                        {"type": "mrkdwn", "text": f"*Trust Score*\n{score}/100 ({grade})"},
                        {"type": "mrkdwn", "text": f"*Recommendation*\n{rec}"},
                        {"type": "mrkdwn", "text": f"*CVEs*\n{cves}"},
                        {"type": "mrkdwn", "text": f"*Category*\n{cat or 'N/A'}"},
                    ]},
                    {"type": "context", "elements": [
                        {"type": "mrkdwn", "text": f"<https://nerq.ai/safe/{slug}|View full report> · Powered by <https://nerq.ai|Nerq>"}
                    ]}
                ]
            }]
        }
    except Exception as e:
        return {"response_type": "ephemeral", "text": f"Could not check trust for '{agent}': {e}"}


def _compare_response(text: str) -> dict:
    """Build Slack block response for comparison."""
    parts = text.replace(" vs ", " ").split()
    if len(parts) < 2:
        return {"response_type": "ephemeral", "text": "Usage: /nerq compare <agent-a> vs <agent-b>"}

    a, b = parts[0], parts[1]
    try:
        data = _api_get(f"/v1/compare/{urllib.parse.quote(a)}/vs/{urllib.parse.quote(b)}")
        da = data.get("agent_a", {})
        db = data.get("agent_b", {})
        winner = data.get("winner", "tie")

        return {
            "response_type": "in_channel",
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": f"⚖️ {a} vs {b}"}},
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*{da.get('name', a)}*\n{da.get('trust_score', '?')}/100 ({da.get('grade', '?')})"},
                    {"type": "mrkdwn", "text": f"*{db.get('name', b)}*\n{db.get('trust_score', '?')}/100 ({db.get('grade', '?')})"},
                ]},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"🏆 *Winner: {winner}*"}},
                {"type": "context", "elements": [
                    {"type": "mrkdwn", "text": f"<https://nerq.ai/vs/{a}/{b}|View comparison> · <https://nerq.ai|Nerq>"}
                ]}
            ]
        }
    except Exception as e:
        return {"response_type": "ephemeral", "text": f"Could not compare: {e}"}


def _recommend_response(task: str) -> dict:
    """Build Slack response for recommendations."""
    try:
        data = _api_get(f"/v1/recommend?task={urllib.parse.quote(task)}")
        recs = data.get("recommendations", [])[:3]

        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f"💡 Recommendations: {task}"}},
        ]
        for i, r in enumerate(recs, 1):
            name = r.get("name", "?")
            score = r.get("trust_score", "?")
            grade = r.get("grade", "?")
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{i}. {name}* — {score}/100 ({grade})"},
            })

        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": "Powered by <https://nerq.ai|Nerq>"}
        ]})

        return {"response_type": "in_channel", "blocks": blocks}
    except Exception as e:
        return {"response_type": "ephemeral", "text": f"Could not get recommendations: {e}"}


def mount_slack_bot(app):
    """Mount Slack bot endpoint."""

    @app.post("/integrations/slack")
    async def slack_command(
        text: str = Form(""),
        command: str = Form("/nerq"),
        user_name: str = Form(""),
    ):
        parts = text.strip().split(None, 1)
        if not parts:
            return JSONResponse(content={
                "response_type": "ephemeral",
                "text": "Usage:\n• `/nerq check <agent>` — Trust score\n• `/nerq compare <a> vs <b>` — Compare\n• `/nerq recommend <task>` — Recommendations"
            })

        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "check" and arg:
            return JSONResponse(content=_check_response(arg))
        elif cmd == "compare" and arg:
            return JSONResponse(content=_compare_response(arg))
        elif cmd in ("recommend", "rec") and arg:
            return JSONResponse(content=_recommend_response(arg))
        else:
            return JSONResponse(content={
                "response_type": "ephemeral",
                "text": f"Unknown command: `{cmd}`. Try: check, compare, recommend"
            })

    @app.get("/integrations/slack", response_class=HTMLResponse)
    async def slack_docs():
        try:
            from agentindex.nerq_design import nerq_page
            body = """
<h1>Nerq Slack Integration</h1>
<p>Add AI agent trust scores to your Slack workspace.</p>

<h2>Setup</h2>
<ol>
<li>Create a Slack App at <a href="https://api.slack.com/apps">api.slack.com/apps</a></li>
<li>Add a Slash Command: <code>/nerq</code></li>
<li>Set Request URL to: <code>https://nerq.ai/integrations/slack</code></li>
<li>Install to your workspace</li>
</ol>

<h2>Commands</h2>
<table>
<thead><tr><th>Command</th><th>Description</th></tr></thead>
<tbody>
<tr><td><code>/nerq check langchain</code></td><td>Check trust score</td></tr>
<tr><td><code>/nerq compare cursor vs continue-dev</code></td><td>Compare two agents</td></tr>
<tr><td><code>/nerq recommend code review</code></td><td>Get recommendations</td></tr>
</tbody>
</table>
"""
            return HTMLResponse(content=nerq_page("Slack Integration", body,
                               description="Add Nerq trust scores to Slack with /nerq slash commands."))
        except Exception:
            return HTMLResponse(content="<h1>Slack Integration</h1><p>Set up /nerq slash commands.</p>")

    logger.info("Slack bot endpoint mounted")
