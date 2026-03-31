"""
Deep Analysis Pages
===================
Generates enriched /safe/ content for top agents with:
- Security deep dive (CVEs, dependency vulnerabilities)
- Maintenance health (commits, releases, issues)
- Ecosystem position (frameworks, co-dependencies, MCP compatibility)
- Cost analysis (pricing, alternatives)
- Trust score breakdown (6 dimensions)
- Improvement path
- Rich FAQ

Mounts as additional HTML sections injected into existing /safe/ pages.
"""

import logging
import os
import sqlite3
from datetime import datetime, timezone
from html import escape as _esc

from fastapi import Request
from fastapi.responses import HTMLResponse

from agentindex.db.models import get_session
from sqlalchemy import text

logger = logging.getLogger("deep-analysis")

_SQLITE_PATH = os.path.join(os.path.dirname(__file__), "crypto", "crypto_trust.db")

# Top agents that get deep analysis pages (by canonical name)
TOP_AGENTS = [
    "langchain-ai/langchain", "crewAIInc/crewAI", "microsoft/autogen",
    "run-llama/llama_index", "getcursor/cursor", "microsoft/semantic-kernel",
    "deepset-ai/haystack", "huggingface/smolagents", "stanfordnlp/dspy",
    "openai/openai-python", "anthropics/anthropic-sdk-python",
    "cognition-labs/devin", "princeton-nlp/SWE-agent", "continuedev/continue",
    "mastra-ai/mastra", "Significant-Gravitas/AutoGPT", "n8n-io/n8n",
    "ollama/ollama", "langflow-ai/langflow", "langgenius/dify",
    "open-webui/open-webui", "google-gemini/gemini-cli", "browser-use/browser-use",
    "infiniflow/ragflow", "lobehub/lobehub", "OpenHands/OpenHands",
    "anthropics/claude-code", "cline/cline", "openai/codex",
    "FoundationAgents/MetaGPT", "firecrawl/firecrawl", "FlowiseAI/Flowise",
    "Mintplex-Labs/anything-llm", "hiyouga/LlamaFactory",
    "unslothai/unsloth", "mudler/LocalAI", "janhq/jan",
    "CherryHQ/cherry-studio", "anomalyco/opencode",
    "AntonOsika/gpt-engineer", "pathwaycom/llm-app",
    "microsoft/markitdown", "upstash/context7",
    "oobabooga/text-generation-webui", "sansan0/TrendRadar",
    "binary-husky/gpt_academic", "lencx/ChatGPT",
    "affaan-m/everything-claude-code", "awesome-llm-apps",
    "punkpeye/awesome-mcp-servers",
    # Top "is X safe" search targets
    "ChatGPT", "Windsurf", "Bolt", "Comfy-Org/ComfyUI",
    "GitHub Copilot", "GitHub Copilot CLI", "Claude", "Gemini", "HuggingFace",
    "Stable Diffusion",
    # Additional high-star tools
    "pydantic/pydantic-ai", "ComposioHQ/composio", "agno-agi/agno",
    "promptfoo/promptfoo", "zcaceres/markdownify-mcp", "truera/trulens",
    "tanweai/pua", "SWE-agent/SWE-agent",
]


def _get_sqlite_conn():
    try:
        return sqlite3.connect(_SQLITE_PATH, timeout=5)
    except Exception:
        return None


def get_deep_sections(agent_name: str, agent_data: dict) -> str:
    """Generate deep analysis HTML sections for an agent.

    Args:
        agent_name: The agent name (as in DB)
        agent_data: Dict with agent fields from the agents table

    Returns:
        HTML string with deep analysis sections, or empty string if not a top agent.
    """
    # Only generate deep content for top agents
    name_lower = agent_name.lower()
    is_top = any(name_lower == t.lower() for t in TOP_AGENTS)
    if not is_top:
        return ""

    sections = []
    conn = _get_sqlite_conn()

    score = agent_data.get("trust_score") or agent_data.get("trust_score_v2") or 0
    grade = agent_data.get("trust_grade") or "N/A"
    category = agent_data.get("category") or "uncategorized"
    stars = agent_data.get("stars") or 0
    description = agent_data.get("description") or ""
    source = agent_data.get("source") or ""

    # ── Executive Summary ──
    exec_summary = _executive_summary(agent_name, score, grade, category, stars, description, conn)
    if exec_summary:
        sections.append(exec_summary)

    if conn:
        # ── Security Deep Dive ──
        security_html = _security_section(agent_name, conn)
        if security_html:
            sections.append(security_html)

        # ── Maintenance Health ──
        maintenance_html = _maintenance_section(agent_name, agent_data, conn)
        if maintenance_html:
            sections.append(maintenance_html)

        # ── Ecosystem Position ──
        ecosystem_html = _ecosystem_section(agent_name, conn)
        if ecosystem_html:
            sections.append(ecosystem_html)

        # ── Cost Analysis ──
        cost_html = _cost_section(agent_name, conn)
        if cost_html:
            sections.append(cost_html)

        conn.close()

    # ── Trust Score Breakdown ──
    breakdown_html = _trust_breakdown(agent_data)
    if breakdown_html:
        sections.append(breakdown_html)

    # ── Improvement Path ──
    improve_html = _improvement_section(agent_name, agent_data)
    if improve_html:
        sections.append(improve_html)

    # ── Deep FAQ ──
    faq_html = _deep_faq(agent_name, score, grade, category, stars, conn)
    if faq_html:
        sections.append(faq_html)

    if not sections:
        return ""

    return f"""
<div class="deep-analysis" style="margin-top:40px;border-top:2px solid #e5e7eb;padding-top:32px">
<h2 style="font-size:22px;font-weight:700;margin-bottom:24px">Deep Analysis: {_esc(agent_name)}</h2>
{''.join(sections)}
</div>
"""


def _executive_summary(name, score, grade, category, stars, description, conn):
    # CVE status
    cve_text = "No known vulnerabilities."
    if conn:
        try:
            cve_count = conn.execute(
                "SELECT COUNT(*) FROM agent_vulnerabilities WHERE agent_name = ? OR agent_name LIKE ?",
                (name, f"%{name.split('/')[-1]}%")
            ).fetchone()[0]
            if cve_count > 0:
                critical = conn.execute(
                    "SELECT COUNT(*) FROM agent_vulnerabilities WHERE (agent_name = ? OR agent_name LIKE ?) AND severity = 'CRITICAL'",
                    (name, f"%{name.split('/')[-1]}%")
                ).fetchone()[0]
                cve_text = f"{cve_count} known CVE{'s' if cve_count != 1 else ''}"
                if critical:
                    cve_text += f" ({critical} CRITICAL)"
                cve_text += "."
        except Exception:
            pass

    stars_text = f"{stars:,} GitHub stars" if stars else "Community data unavailable"

    return f"""
<div class="exec-summary" style="background:#f0fdf4;border:1px solid #bbf7d0;padding:20px;margin-bottom:24px">
<h3 style="margin:0 0 8px;font-size:16px;font-weight:600;color:#15803d">Executive Summary</h3>
<p style="margin:0;font-size:14px;line-height:1.7;color:#374151">
<strong>{_esc(name)}</strong> is a {_esc(category)} tool with a Nerq Trust Score of <strong>{score:.1f}/100 ({_esc(grade)})</strong>.
{_esc(cve_text)} {stars_text}.
{_esc(description[:200]) if description else ''}
</p>
</div>
"""


def _security_section(name, conn):
    try:
        rows = conn.execute(
            "SELECT cve_id, severity, description, fetched_at FROM agent_vulnerabilities WHERE agent_name = ? OR agent_name LIKE ? ORDER BY severity DESC",
            (name, f"%{name.split('/')[-1]}%")
        ).fetchall()
    except Exception:
        rows = []

    if not rows:
        return f"""
<div style="margin-bottom:24px">
<h3 style="font-size:16px;font-weight:600;margin-bottom:8px">Security</h3>
<p style="font-size:14px;color:#374151">No known CVEs. {_esc(name)} has a clean security record in the Nerq database.</p>
</div>
"""

    table_rows = ""
    for cve_id, severity, desc, fetched in rows:
        sev_color = {"CRITICAL": "#dc2626", "HIGH": "#ea580c", "MEDIUM": "#d97706", "LOW": "#65a30d"}.get(severity, "#6b7280")
        table_rows += f"""
<tr>
<td style="font-family:monospace;font-size:12px">{_esc(cve_id or '')}</td>
<td><span style="color:{sev_color};font-weight:600;font-size:12px">{_esc(severity or '')}</span></td>
<td style="font-size:12px">{_esc((desc or '')[:120])}</td>
<td style="font-size:12px;color:#6b7280">{_esc((fetched or '')[:10])}</td>
</tr>
"""

    return f"""
<div style="margin-bottom:24px">
<h3 style="font-size:16px;font-weight:600;margin-bottom:8px;color:#dc2626">Security: {len(rows)} Known CVE{'s' if len(rows) != 1 else ''}</h3>
<div style="overflow-x:auto">
<table style="width:100%;border-collapse:collapse;font-size:13px">
<thead><tr style="border-bottom:2px solid #e5e7eb;text-align:left">
<th style="padding:8px 12px">CVE ID</th><th style="padding:8px 12px">Severity</th><th style="padding:8px 12px">Description</th><th style="padding:8px 12px">Discovered</th>
</tr></thead>
<tbody>{table_rows}</tbody>
</table>
</div>
</div>
"""


def _maintenance_section(name, agent_data, conn):
    last_update = agent_data.get("last_source_update")
    last_crawled = agent_data.get("last_crawled")

    days_since_update = None
    if last_update:
        try:
            if hasattr(last_update, 'replace'):
                dt = last_update.replace(tzinfo=timezone.utc) if last_update.tzinfo is None else last_update
            else:
                dt = datetime.fromisoformat(str(last_update)).replace(tzinfo=timezone.utc)
            days_since_update = (datetime.now(timezone.utc) - dt).days
        except Exception:
            pass

    activity_score = agent_data.get("activity_score")
    stars = agent_data.get("stars") or 0
    forks = agent_data.get("forks") or 0

    # Get download data
    downloads_text = ""
    try:
        dl = conn.execute(
            "SELECT registry, weekly_downloads FROM package_downloads WHERE agent_name = ? OR agent_name LIKE ? ORDER BY weekly_downloads DESC LIMIT 3",
            (name, f"%{name.split('/')[-1]}%")
        ).fetchall()
        if dl:
            parts = []
            for reg, wk in dl:
                if wk and wk > 0:
                    parts.append(f"{wk:,}/week ({reg})")
            if parts:
                downloads_text = "Downloads: " + ", ".join(parts)
    except Exception:
        pass

    items = []
    if days_since_update is not None:
        freshness = "Active" if days_since_update < 30 else "Stale" if days_since_update < 90 else "Inactive"
        items.append(f"<li>Last update: <strong>{days_since_update} days ago</strong> ({freshness})</li>")
    if stars:
        items.append(f"<li>GitHub stars: <strong>{stars:,}</strong></li>")
    if forks:
        items.append(f"<li>Forks: <strong>{forks:,}</strong></li>")
    if activity_score is not None:
        items.append(f"<li>Activity score: <strong>{activity_score:.0f}/100</strong></li>")
    if downloads_text:
        items.append(f"<li>{_esc(downloads_text)}</li>")

    if not items:
        return ""

    return f"""
<div style="margin-bottom:24px">
<h3 style="font-size:16px;font-weight:600;margin-bottom:8px">Maintenance Health</h3>
<ul style="font-size:14px;color:#374151;line-height:1.8;padding-left:20px">
{''.join(items)}
</ul>
</div>
"""


def _ecosystem_section(name, conn):
    items = []

    # Frameworks
    try:
        fws = conn.execute(
            "SELECT DISTINCT framework FROM agent_frameworks WHERE agent_name = ? OR agent_name LIKE ?",
            (name, f"%{name.split('/')[-1]}%")
        ).fetchall()
        if fws:
            fw_list = ", ".join(r[0] for r in fws)
            items.append(f"<li>Compatible frameworks: <strong>{_esc(fw_list)}</strong></li>")
    except Exception:
        pass

    # MCP compatibility
    try:
        mcp = conn.execute(
            "SELECT DISTINCT client FROM mcp_compatibility WHERE server_name = ? OR server_name LIKE ?",
            (name, f"%{name.split('/')[-1]}%")
        ).fetchall()
        if mcp:
            mcp_list = ", ".join(r[0] for r in mcp)
            items.append(f"<li>MCP clients: <strong>{_esc(mcp_list)}</strong></li>")
    except Exception:
        pass

    # External trust signals
    try:
        signals = conn.execute(
            "SELECT signal_source, signal_value FROM external_trust_signals WHERE agent_name = ? OR agent_name LIKE ? LIMIT 5",
            (name, f"%{name.split('/')[-1]}%")
        ).fetchall()
        if signals:
            for src, val in signals:
                items.append(f"<li>External signal ({_esc(src)}): {_esc(str(val)[:80])}</li>")
    except Exception:
        pass

    if not items:
        return ""

    return f"""
<div style="margin-bottom:24px">
<h3 style="font-size:16px;font-weight:600;margin-bottom:8px">Ecosystem Position</h3>
<ul style="font-size:14px;color:#374151;line-height:1.8;padding-left:20px">
{''.join(items)}
</ul>
</div>
"""


def _cost_section(name, conn):
    items = []
    try:
        pricing = conn.execute(
            "SELECT pricing_model, price_monthly, free_tier_limits FROM agent_pricing WHERE agent_name = ? OR agent_name LIKE ? LIMIT 3",
            (name, f"%{name.split('/')[-1]}%")
        ).fetchall()
        for model, monthly, limits in pricing:
            if model:
                price_str = f"${monthly:.2f}/mo" if monthly and monthly > 0 else "Free"
                items.append(f"<li>Pricing: <strong>{_esc(model)}</strong> — {price_str}</li>")
                if limits:
                    items.append(f"<li>Free tier: {_esc(str(limits)[:100])}</li>")
    except Exception:
        pass

    try:
        costs = conn.execute(
            "SELECT task_type, estimated_cost_usd FROM agent_cost_estimates WHERE agent_name = ? OR agent_name LIKE ? LIMIT 5",
            (name, f"%{name.split('/')[-1]}%")
        ).fetchall()
        for task, cost in costs:
            if cost is not None:
                items.append(f"<li>Cost per {_esc(task)}: <strong>${cost:.4f}</strong></li>")
    except Exception:
        pass

    if not items:
        return ""

    return f"""
<div style="margin-bottom:24px">
<h3 style="font-size:16px;font-weight:600;margin-bottom:8px">Cost Analysis</h3>
<ul style="font-size:14px;color:#374151;line-height:1.8;padding-left:20px">
{''.join(items)}
</ul>
</div>
"""


def _trust_breakdown(agent_data):
    dimensions = []
    labels = [
        ("security_score", "Security", "#dc2626"),
        ("compliance_score", "Compliance", "#7c3aed"),
        ("activity_score", "Maintenance", "#2563eb"),
        ("documentation_score", "Documentation", "#0891b2"),
        ("popularity_score", "Community", "#059669"),
    ]

    for key, label, color in labels:
        val = agent_data.get(key)
        if val is not None:
            width = max(2, min(100, int(val)))
            dimensions.append(f"""
<div style="margin-bottom:8px">
<div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:2px">
<span>{label}</span><span style="font-weight:600">{val:.0f}/100</span>
</div>
<div style="background:#e5e7eb;height:8px;border-radius:4px;overflow:hidden">
<div style="background:{color};height:100%;width:{width}%;border-radius:4px"></div>
</div>
</div>
""")

    if not dimensions:
        return ""

    # Find strongest and weakest
    scored = [(agent_data.get(k), l) for k, l, _ in labels if agent_data.get(k) is not None]
    if scored:
        strongest = max(scored, key=lambda x: x[0])
        weakest = min(scored, key=lambda x: x[0])
        insight = f"<p style='font-size:13px;color:#6b7280;margin-top:8px'>Strongest: {strongest[1]} ({strongest[0]:.0f}/100). Weakest: {weakest[1]} ({weakest[0]:.0f}/100).</p>"
    else:
        insight = ""

    return f"""
<div style="margin-bottom:24px">
<h3 style="font-size:16px;font-weight:600;margin-bottom:12px">Trust Score Breakdown</h3>
<div style="max-width:500px">
{''.join(dimensions)}
</div>
{insight}
</div>
"""


def _improvement_section(name, agent_data):
    suggestions = []
    score = agent_data.get("trust_score") or agent_data.get("trust_score_v2") or 0

    security = agent_data.get("security_score")
    compliance = agent_data.get("compliance_score")
    activity = agent_data.get("activity_score")
    docs = agent_data.get("documentation_score")
    popularity = agent_data.get("popularity_score")

    if security is not None and security < 60:
        suggestions.append(("Improve security practices", "Add security policy, fix known vulnerabilities, enable dependency scanning.", "+5-15 points"))
    if compliance is not None and compliance < 50:
        suggestions.append(("Add compliance documentation", "Add LICENSE file, privacy policy, data handling documentation.", "+5-10 points"))
    if activity is not None and activity < 40:
        suggestions.append(("Increase maintenance activity", "Respond to issues, merge PRs, publish regular releases.", "+5-10 points"))
    if docs is not None and docs < 50:
        suggestions.append(("Improve documentation", "Add API docs, usage examples, contribution guidelines.", "+5-10 points"))
    if score < 70:
        suggestions.append(("Reach Nerq Verified status", "Achieve 70+ trust score to earn the Nerq Verified badge.", "Verified badge"))

    if not suggestions:
        return ""

    rows = ""
    for title, desc, impact in suggestions[:3]:
        rows += f"""
<div style="padding:12px;border:1px solid #e5e7eb;margin-bottom:8px">
<div style="font-weight:600;font-size:14px">{_esc(title)}</div>
<div style="font-size:13px;color:#6b7280;margin-top:4px">{_esc(desc)}</div>
<div style="font-size:12px;color:#059669;margin-top:4px">Estimated impact: {_esc(impact)}</div>
</div>
"""

    return f"""
<div style="margin-bottom:24px">
<h3 style="font-size:16px;font-weight:600;margin-bottom:8px">How to Improve This Score</h3>
{rows}
</div>
"""


def _deep_faq(name, score, grade, category, stars, conn):
    short_name = name.split("/")[-1] if "/" in name else name

    # CVE check
    cve_answer = f"As of {datetime.now().strftime('%B %Y')}, {_esc(short_name)} has no known CVEs in the Nerq database."
    if conn:
        try:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM agent_vulnerabilities WHERE agent_name = ? OR agent_name LIKE ?",
                (name, f"%{short_name}%")
            ).fetchone()[0]
            if cnt > 0:
                cve_answer = f"Yes, {_esc(short_name)} has {cnt} known CVE{'s' if cnt != 1 else ''}. Check the security section above for details."
        except Exception:
            pass

    # License
    license_answer = "License information is not yet available in the Nerq database."
    if conn:
        try:
            lic = conn.execute(
                "SELECT license_spdx, license_category FROM agent_licenses WHERE agent_name = ? OR agent_name LIKE ? OR agent_id LIKE ? LIMIT 1",
                (name, f"%{short_name}%", f"%{short_name}%")
            ).fetchone()
            if lic:
                license_answer = f"{_esc(short_name)} uses the {_esc(lic[0])} license ({_esc(lic[1])})."
        except Exception:
            pass

    safe_answer = f"{'Yes' if score >= 70 else 'Caution advised'}. {_esc(short_name)} has a Nerq Trust Score of {score:.1f}/100 ({_esc(grade)})."
    if score >= 80:
        safe_answer += " This is a high trust score, indicating strong security, maintenance, and community signals."
    elif score >= 70:
        safe_answer += " This meets the Nerq Verified threshold, but review the detailed analysis before production use."
    elif score >= 50:
        safe_answer += " This is below the Nerq Verified threshold of 70. Consider alternatives or perform additional due diligence."
    else:
        safe_answer += " This score indicates significant trust concerns. We recommend reviewing alternatives."

    faqs = [
        (f"Is {short_name} safe to use in production?", safe_answer),
        (f"Does {short_name} have any known vulnerabilities?", cve_answer),
        (f"What license does {short_name} use?", license_answer),
        (f"How does {short_name} compare to alternatives?",
         f"In the {_esc(category)} category, {_esc(short_name)} scores {score:.1f}/100. "
         f"Use the Nerq comparison API to compare directly: "
         f"<code>curl nerq.ai/v1/compare/{_esc(short_name.lower())}/vs/[alternative]</code>"),
        (f"How often is {short_name} updated?",
         f"Check the maintenance health section above for the latest activity data. "
         f"Nerq tracks commit frequency, release cadence, and issue response times."),
    ]

    faq_items = ""
    faq_schema = []
    for q, a in faqs:
        faq_items += f"""
<details style="border:1px solid #e5e7eb;padding:12px 16px;margin-bottom:8px">
<summary style="cursor:pointer;font-weight:600;font-size:14px">{_esc(q)}</summary>
<p style="font-size:14px;color:#374151;margin:8px 0 0;line-height:1.6">{a}</p>
</details>
"""
        faq_schema.append({"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a.replace("<code>", "").replace("</code>", "")}})

    import json
    schema_json = json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": faq_schema})

    # Note: FAQPage JSON-LD is already emitted by agent_safety_pages.py — do not duplicate
    return f"""
<div style="margin-bottom:24px">
<h3 style="font-size:16px;font-weight:600;margin-bottom:12px">Frequently Asked Questions</h3>
{faq_items}
</div>
"""


def mount_deep_analysis(app):
    """No routes to mount — deep analysis is injected into existing /safe/ pages."""
    pass
