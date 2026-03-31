"""
Channel Dashboard — Track adoption across all 5 distribution channels.

Endpoints:
  /admin/channels — Channel analytics dashboard
  /vscode         — VS Code extension landing page
  /github-app     — GitHub App install page
  /extension      — Browser extension page
  /cli            — CLI tools page
  /github-action  — GitHub Action page
"""

import os
import sqlite3
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["channels"])

ANALYTICS_DB = os.path.join(os.path.dirname(__file__), "..", "logs", "analytics.db")


def get_channel_stats(days: int = 7) -> list[dict]:
    """Query channel usage from analytics DB."""
    try:
        conn = sqlite3.connect(ANALYTICS_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT
              CASE
                WHEN user_agent LIKE '%NerqVSCode%' THEN 'VS Code Extension'
                WHEN user_agent LIKE '%NerqGitHubApp%' THEN 'GitHub App'
                WHEN user_agent LIKE '%NerqBrowserExt%' THEN 'Browser Extension'
                WHEN user_agent LIKE '%NerqCLI%' THEN 'CLI (nerq)'
                WHEN user_agent LIKE '%NerqAction%' THEN 'GitHub Action'
                WHEN user_agent LIKE '%ChatGPT%' OR user_agent LIKE '%GPTBot%' THEN 'AI: ChatGPT'
                WHEN user_agent LIKE '%Claude%' THEN 'AI: Claude'
                WHEN user_agent LIKE '%Perplexity%' THEN 'AI: Perplexity'
                WHEN user_agent LIKE '%python-requests%' OR user_agent LIKE '%httpx%' THEN 'SDK/API'
                ELSE 'Web/Other'
              END as channel,
              COUNT(*) as api_calls,
              COUNT(DISTINCT ip) as unique_users
            FROM requests
            WHERE path LIKE '/v1/%'
            AND ts > datetime('now', ?)
            GROUP BY channel
            ORDER BY api_calls DESC
        """, (f"-{days} days",)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_daily_channel_trend(days: int = 14) -> list[dict]:
    """Get daily API calls per channel."""
    try:
        conn = sqlite3.connect(ANALYTICS_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT
              date(ts) as day,
              CASE
                WHEN user_agent LIKE '%NerqVSCode%' THEN 'vscode'
                WHEN user_agent LIKE '%NerqGitHubApp%' THEN 'github-app'
                WHEN user_agent LIKE '%NerqBrowserExt%' THEN 'browser-ext'
                WHEN user_agent LIKE '%NerqCLI%' THEN 'cli'
                WHEN user_agent LIKE '%NerqAction%' THEN 'action'
                ELSE 'other'
              END as channel,
              COUNT(*) as calls
            FROM requests
            WHERE path LIKE '/v1/%'
            AND ts > datetime('now', ?)
            GROUP BY day, channel
            ORDER BY day
        """, (f"-{days} days",)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


CHANNEL_META = {
    "vscode": {
        "name": "VS Code Extension",
        "tagline": "Trust scores right in your editor",
        "description": "Automatic trust verification for AI dependencies. See CVEs, trust scores, and safer alternatives — right where you code.",
        "install_cmd": "ext install nerq-ai.nerq-ai-guard",
        "install_label": "Install from VS Code Marketplace",
        "install_url": "https://marketplace.visualstudio.com/items?itemName=nerq-ai.nerq-ai-guard",
        "icon": "code",
        "color": "#007acc",
        "steps": [
            "Open VS Code and search for 'Nerq' in extensions",
            "Install and open any project with dependency files",
            "See trust scores, CVE warnings, and recommendations inline",
        ],
    },
    "github-app": {
        "name": "Nerq Trust Bot",
        "tagline": "Automatic trust reports on every PR",
        "description": "Install the Nerq Trust Bot on your GitHub repos. Every PR that changes dependencies gets an automatic trust report with CVE checks.",
        "install_label": "Install GitHub App",
        "install_url": "https://github.com/apps/nerq-trust-bot",
        "icon": "git-pull-request",
        "color": "#24292e",
        "steps": [
            "Click 'Install' and select your repos",
            "Open a PR that changes requirements.txt or package.json",
            "Get an automatic trust report comment with CVE alerts",
        ],
    },
    "extension": {
        "name": "Nerq: AI Tool Inspector",
        "tagline": "Trust scores on GitHub, npm, and PyPI",
        "description": "See trust scores for AI tools directly on GitHub repos, npm packages, and PyPI projects. One glance tells you if it's safe.",
        "install_label": "Add to Chrome",
        "install_url": "#",
        "icon": "globe",
        "color": "#4285f4",
        "steps": [
            "Install from Chrome Web Store",
            "Visit any GitHub repo, npm package, or PyPI project",
            "See the trust badge appear automatically — click for full report",
        ],
    },
    "cli": {
        "name": "Nerq CLI",
        "tagline": "Trust verification from your terminal",
        "description": "Scan dependencies, find cheaper LLM alternatives, and check trust scores — all from the command line.",
        "install_cmd": "pip install nerq",
        "install_label": "Install via pip",
        "install_url": "https://pypi.org/project/nerq/",
        "icon": "terminal",
        "color": "#0f172a",
        "steps": [
            "pip install nerq",
            "nerq scan — scan project dependencies",
            "nerq savings — find cheaper LLM alternatives",
        ],
    },
    "github-action": {
        "name": "Nerq Trust Gate",
        "tagline": "CI/CD trust verification in one line",
        "description": "Add automatic AI dependency trust verification to your GitHub Actions workflow. One line of YAML. That's it.",
        "install_label": "View on GitHub Marketplace",
        "install_url": "https://github.com/marketplace/actions/nerq-trust-gate",
        "icon": "play-circle",
        "color": "#2088ff",
        "yaml_snippet": """name: Trust Check
on: [push, pull_request]
jobs:
  trust:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: nerq-ai/trust-gate@v1""",
        "steps": [
            "Add the YAML snippet to .github/workflows/trust-check.yml",
            "Push to trigger the workflow",
            "See trust report in the Actions summary with warnings and grades",
        ],
    },
}


def _page_shell(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Nerq</title>
<meta name="description" content="{title} — Trust verification for AI tools and dependencies">
<link rel="canonical" href="https://nerq.ai">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1f2937; background: #fafafa; }}
  .hero {{ background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: white; padding: 60px 20px; text-align: center; }}
  .hero h1 {{ font-size: 36px; font-weight: 700; margin-bottom: 12px; }}
  .hero p {{ font-size: 18px; opacity: 0.85; max-width: 600px; margin: 0 auto 24px; }}
  .install-btn {{ display: inline-block; padding: 14px 32px; background: #3b82f6; color: white; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 16px; transition: background 0.2s; }}
  .install-btn:hover {{ background: #2563eb; }}
  .install-cmd {{ display: inline-block; background: rgba(255,255,255,0.1); padding: 10px 20px; border-radius: 6px; font-family: monospace; font-size: 14px; margin-bottom: 16px; }}
  .content {{ max-width: 800px; margin: 0 auto; padding: 40px 20px; }}
  .steps {{ list-style: none; counter-reset: step; }}
  .steps li {{ counter-increment: step; padding: 16px 0 16px 50px; position: relative; border-bottom: 1px solid #e5e7eb; }}
  .steps li::before {{ content: counter(step); position: absolute; left: 0; top: 16px; width: 32px; height: 32px; background: #0f172a; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px; }}
  .steps li:last-child {{ border-bottom: none; }}
  h2 {{ font-size: 24px; margin-bottom: 16px; }}
  .yaml-box {{ background: #0f172a; color: #e2e8f0; padding: 20px; border-radius: 8px; font-family: monospace; font-size: 13px; white-space: pre; overflow-x: auto; margin: 20px 0; }}
  .footer {{ text-align: center; padding: 30px 20px; color: #6b7280; font-size: 13px; border-top: 1px solid #e5e7eb; }}
  .footer a {{ color: #3b82f6; text-decoration: none; }}
  .nav {{ display: flex; gap: 16px; justify-content: center; padding: 16px; background: white; border-bottom: 1px solid #e5e7eb; flex-wrap: wrap; }}
  .nav a {{ color: #4b5563; text-decoration: none; font-size: 13px; font-weight: 500; }}
  .nav a:hover {{ color: #0f172a; }}
</style>
</head>
<body>
<nav class="nav">
  <a href="/">Nerq</a>
  <a href="/github-action">GitHub Action</a>
  <a href="/cli">CLI</a>
  <a href="/extension">Browser Extension</a>
  <a href="/vscode">VS Code</a>
  <a href="/github-app">GitHub App</a>
</nav>
{body}
<div class="footer">
  <a href="https://nerq.ai">nerq.ai</a> — Is it safe?
</div>
</body>
</html>"""


def _channel_landing(channel_key: str) -> str:
    ch = CHANNEL_META[channel_key]

    install_section = ""
    if ch.get("install_cmd"):
        install_section += f'<div class="install-cmd">{ch["install_cmd"]}</div><br>'
    install_section += f'<a href="{ch["install_url"]}" class="install-btn">{ch["install_label"]}</a>'

    yaml_section = ""
    if ch.get("yaml_snippet"):
        yaml_section = f'<div class="yaml-box">{ch["yaml_snippet"]}</div>'

    steps_html = "\n".join(f"<li>{s}</li>" for s in ch["steps"])

    body = f"""
<div class="hero">
  <h1>{ch["name"]}</h1>
  <p>{ch["tagline"]}</p>
  {install_section}
</div>
<div class="content">
  <p style="font-size:16px;line-height:1.6;margin-bottom:24px">{ch["description"]}</p>
  {yaml_section}
  <h2>How it works</h2>
  <ol class="steps">
    {steps_html}
  </ol>
</div>"""
    return _page_shell(ch["name"], body)


@router.get("/admin/channels", response_class=HTMLResponse)
async def channel_dashboard():
    """Channel adoption dashboard."""
    stats = get_channel_stats(7)
    trend = get_daily_channel_trend(14)

    rows = ""
    total_calls = 0
    total_users = 0
    for s in stats:
        total_calls += s["api_calls"]
        total_users += s["unique_users"]
        rows += f"""<tr>
          <td style="font-weight:600">{s['channel']}</td>
          <td style="text-align:right">{s['api_calls']:,}</td>
          <td style="text-align:right">{s['unique_users']:,}</td>
        </tr>"""

    body = f"""
<div class="hero" style="padding:30px 20px">
  <h1>Channel Dashboard</h1>
  <p>API calls by distribution channel (last 7 days)</p>
</div>
<div class="content">
  <div style="display:flex;gap:20px;margin-bottom:30px">
    <div style="flex:1;background:white;padding:20px;border-radius:8px;border:1px solid #e5e7eb;text-align:center">
      <div style="font-size:28px;font-weight:700">{total_calls:,}</div>
      <div style="font-size:13px;color:#6b7280">API Calls (7d)</div>
    </div>
    <div style="flex:1;background:white;padding:20px;border-radius:8px;border:1px solid #e5e7eb;text-align:center">
      <div style="font-size:28px;font-weight:700">{total_users:,}</div>
      <div style="font-size:13px;color:#6b7280">Unique Users (7d)</div>
    </div>
    <div style="flex:1;background:white;padding:20px;border-radius:8px;border:1px solid #e5e7eb;text-align:center">
      <div style="font-size:28px;font-weight:700">{len([s for s in stats if s['channel'] not in ('Web/Other','SDK/API')])}</div>
      <div style="font-size:13px;color:#6b7280">Active Channels</div>
    </div>
  </div>

  <h2>Channel Breakdown</h2>
  <table style="width:100%;border-collapse:collapse;background:white;border-radius:8px;overflow:hidden;border:1px solid #e5e7eb">
    <tr style="background:#f9fafb">
      <th style="padding:10px 16px;text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:0.5px">Channel</th>
      <th style="padding:10px 16px;text-align:right;font-size:12px;text-transform:uppercase;letter-spacing:0.5px">API Calls</th>
      <th style="padding:10px 16px;text-align:right;font-size:12px;text-transform:uppercase;letter-spacing:0.5px">Unique Users</th>
    </tr>
    {rows}
  </table>
</div>"""
    return _page_shell("Channel Dashboard", body)


# ── Landing pages ──

@router.get("/vscode", response_class=HTMLResponse)
async def vscode_landing():
    return _channel_landing("vscode")

@router.get("/github-app", response_class=HTMLResponse)
async def github_app_landing():
    return _channel_landing("github-app")

@router.get("/extension", response_class=HTMLResponse)
async def extension_landing():
    return _channel_landing("extension")

@router.get("/cli", response_class=HTMLResponse)
async def cli_landing():
    return _channel_landing("cli")

@router.get("/github-action", response_class=HTMLResponse)
async def github_action_landing():
    return _channel_landing("github-action")
