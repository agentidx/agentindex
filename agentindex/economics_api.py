"""
Economics API & Pages — Sprint 3
=================================
Endpoints:
  GET  /v1/economics/{agent}       — Pricing, costs, rate limits, value score
  GET  /v1/compare/{a}/vs/{b}      — Head-to-head comparison
  GET  /pricing                    — Hub page
  GET  /pricing/{agent}            — Individual pricing page
  GET  /compare/{slug}/cost        — Cost comparison page

Usage in discovery.py:
    from agentindex.economics_api import mount_economics
    mount_economics(app)
"""

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Query, Request
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.sql import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER, nerq_page

logger = logging.getLogger("nerq.economics")

SQLITE_DB = Path(__file__).parent / "crypto" / "crypto_trust.db"


# ── Helpers ────────────────────────────────────────────────────

def _get_pricing(agent_name: str, conn) -> dict:
    """Get pricing data from SQLite."""
    rows = conn.execute(
        "SELECT plan_name, price_monthly, price_annual_monthly, free_tier_limits, "
        "key_features, pricing_url, pricing_model FROM agent_pricing "
        "WHERE agent_name = ? OR agent_name LIKE ? ORDER BY COALESCE(price_monthly, 999999)",
        (agent_name, f"%{agent_name}%")
    ).fetchall()
    if not rows:
        return {}

    plans = []
    model = rows[0][6]
    url = rows[0][5]

    for r in rows:
        plan = {"name": r[0]}
        if r[1] is not None:
            plan["price_monthly"] = r[1]
        if r[2] is not None:
            plan["price_annual_monthly"] = r[2]
        if r[3]:
            plan["limits"] = r[3]
        if r[4]:
            plan["features"] = r[4]
        plans.append(plan)

    return {
        "model": model,
        "plans": plans,
        "pricing_url": url,
        "has_free_tier": any((p.get("price_monthly") or 0) == 0 for p in plans),
    }


def _get_rate_limits(agent_name: str, conn) -> dict:
    """Get rate limit data from SQLite."""
    rows = conn.execute(
        "SELECT tier, requests_per_minute, requests_per_hour, requests_per_day, "
        "tokens_per_minute, concurrent_limit FROM agent_rate_limits "
        "WHERE agent_name = ? OR agent_name LIKE ?",
        (agent_name, f"%{agent_name}%")
    ).fetchall()
    if not rows:
        return {}

    result = {}
    for r in rows:
        tier = r[0] or "default"
        limits = {}
        if r[1]:
            limits["requests_per_minute"] = r[1]
        if r[2]:
            limits["requests_per_hour"] = r[2]
        if r[3]:
            limits["requests_per_day"] = r[3]
        if r[4]:
            limits["tokens_per_minute"] = r[4]
        if r[5]:
            limits["concurrent_limit"] = r[5]
        if limits:
            result[tier] = limits

    return result


def _get_cost_estimates(agent_name: str, conn) -> dict:
    """Get cost estimate data from SQLite."""
    rows = conn.execute(
        "SELECT model_used, task_type, estimated_cost_usd FROM agent_cost_estimates "
        "WHERE agent_name = ? OR agent_name LIKE ? "
        "ORDER BY task_type, estimated_cost_usd",
        (agent_name, f"%{agent_name}%")
    ).fetchall()
    if not rows:
        return {}

    models = list(set(r[0] for r in rows))
    per_task = {}
    for r in rows:
        task = r[1]
        cost = r[2]
        if task not in per_task:
            per_task[task] = {"min": cost, "max": cost}
        else:
            per_task[task]["min"] = min(per_task[task]["min"], cost)
            per_task[task]["max"] = max(per_task[task]["max"], cost)

    # Format as strings
    formatted = {}
    for task, costs in per_task.items():
        if costs["min"] == costs["max"]:
            formatted[task] = f"${costs['min']:.4f}"
        else:
            formatted[task] = f"${costs['min']:.4f}-${costs['max']:.4f}"

    return {
        "model_used": " / ".join(models) if len(models) <= 3 else f"{models[0]} + {len(models)-1} more",
        "per_task": formatted,
    }


def _get_enrichment_data(agent_name: str, conn) -> dict:
    """Get CVE, download, license data."""
    result = {"cve_count": 0, "license": None, "license_category": None, "npm_weekly": None, "pypi_weekly": None}
    try:
        dl = conn.execute(
            "SELECT npm_weekly, pypi_weekly FROM package_downloads WHERE agent_name = ? LIMIT 1",
            (agent_name,)
        ).fetchone()
        if dl:
            result["npm_weekly"] = dl[0]
            result["pypi_weekly"] = dl[1]
        cve = conn.execute(
            "SELECT COUNT(*) FROM agent_vulnerabilities WHERE agent_name = ?",
            (agent_name,)
        ).fetchone()
        if cve:
            result["cve_count"] = cve[0]
        lic = conn.execute(
            "SELECT spdx_id, license_category FROM agent_licenses WHERE agent_name = ? LIMIT 1",
            (agent_name,)
        ).fetchone()
        if lic:
            result["license"] = lic[0]
            result["license_category"] = lic[1]
    except Exception:
        pass
    return result


def _compute_value_score(trust_score: float, pricing: dict) -> int:
    """Compute value score: trust * affordability_factor (0-100)."""
    if trust_score is None:
        return 0

    # Get cheapest paid plan price
    min_price = None
    has_free = pricing.get("has_free_tier", False)

    for plan in pricing.get("plans", []):
        p = plan.get("price_monthly")
        if p is not None and p > 0:
            if min_price is None or p < min_price:
                min_price = p

    # Affordability factor (0-1): free=1.0, $10=0.9, $50=0.7, $200=0.3
    if has_free and pricing.get("model") == "open_source_free":
        affordability = 1.0
    elif has_free:
        affordability = 0.95
    elif min_price is not None:
        affordability = max(0.1, 1.0 - (min_price / 300.0))
    else:
        affordability = 0.5  # unknown pricing

    value = trust_score * affordability
    return min(100, int(round(value)))


def _lookup_agent(name: str, session) -> dict | None:
    """Find agent by name."""
    row = session.execute(text("""
        SELECT id::text, name, COALESCE(trust_score_v2, trust_score) as trust_score,
               trust_grade, category, source, stars, description, is_verified,
               source_url, last_source_update
        FROM (
            SELECT *, 1 AS _r FROM agents
            WHERE LOWER(name) = LOWER(:name) AND is_active = true
          UNION ALL
            SELECT *, 2 AS _r FROM agents
            WHERE lower(name::text) LIKE lower(:suffix) AND is_active = true
          UNION ALL
            SELECT *, 3 AS _r FROM agents
            WHERE lower(name::text) LIKE lower(:pattern) AND is_active = true
        ) sub
        ORDER BY _r ASC, COALESCE(trust_score_v2, trust_score) DESC NULLS LAST
        LIMIT 1
    """), {"name": name, "suffix": f"%/{name}", "pattern": f"%{name}%"}).fetchone()
    if not row:
        return None
    return dict(row._mapping)


def _get_cheaper_alternatives(agent_name: str, category: str, trust_score: float,
                              pricing_model: str, session, conn) -> list:
    """Find cheaper alternatives with comparable trust."""
    try:
        rows = session.execute(text("""
            SELECT name, COALESCE(trust_score_v2, trust_score) as ts, source
            FROM agents
            WHERE is_active = true
              AND LOWER(name) != LOWER(:name)
              AND category = :cat
              AND COALESCE(trust_score_v2, trust_score) >= :min_ts
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC
            LIMIT 20
        """), {"name": agent_name, "cat": category or "other",
               "min_ts": max(0, (trust_score or 0) - 20)}).fetchall()
    except Exception:
        return []

    alts = []
    for r in rows:
        d = dict(r._mapping)
        alt_name = d["name"]
        alt_pricing = _get_pricing(alt_name, conn)
        alt_costs = _get_cost_estimates(alt_name, conn)

        # Only include if cheaper
        alt_model = alt_pricing.get("model", "unknown")
        if alt_model == "open_source_free" or alt_pricing.get("has_free_tier"):
            from agentindex.agent_safety_pages import _make_slug
            slug = _make_slug(alt_name)
            alts.append({
                "name": alt_name,
                "trust_score": round(float(d["ts"]), 1) if d["ts"] else 0,
                "pricing_model": alt_model,
                "estimated_cost_per_task": alt_costs.get("per_task", {}).get("code_review", "N/A"),
                "preflight_url": f"https://nerq.ai/v1/preflight?target={alt_name}",
                "details_url": f"https://nerq.ai/safe/{slug}",
            })
            if len(alts) >= 3:
                break

    return alts


# ── Mount function ─────────────────────────────────────────────

def mount_economics(app):

    # ═══════════════════════════════════════════════════════════
    # GET /v1/economics/{agent}
    # ═══════════════════════════════════════════════════════════

    @app.get("/v1/economics/{agent_name}")
    def economics_endpoint(agent_name: str):
        t0 = time.time()
        session = get_session()
        try:
            agent = _lookup_agent(agent_name, session)
            if not agent:
                return JSONResponse(status_code=404, content={"error": f"Agent '{agent_name}' not found"})

            name = agent["name"]
            trust_score = float(agent.get("trust_score") or 0)
            category = agent.get("category") or "other"

            conn = sqlite3.connect(str(SQLITE_DB), timeout=5)
            try:
                pricing = _get_pricing(name, conn)
                costs = _get_cost_estimates(name, conn)
                rate_limits = _get_rate_limits(name, conn)
                enr = _get_enrichment_data(name, conn)
                value = _compute_value_score(trust_score, pricing)
                alternatives = _get_cheaper_alternatives(name, category, trust_score,
                                                         pricing.get("model", ""), session, conn)
            finally:
                conn.close()

            from agentindex.agent_safety_pages import _make_slug
            slug = _make_slug(name)

            result = {
                "agent": name,
                "trust_score": round(trust_score, 1),
                "grade": agent.get("trust_grade"),
                "category": category,
                "pricing": pricing or {"model": "unknown", "plans": [], "pricing_url": None},
                "estimated_costs": costs or {},
                "rate_limits": rate_limits or {},
                "cheaper_alternatives": alternatives,
                "value_score": value,
                "enrichment": {
                    "known_cves": enr.get("cve_count", 0),
                    "license": enr.get("license"),
                    "npm_weekly_downloads": enr.get("npm_weekly"),
                    "pypi_weekly_downloads": enr.get("pypi_weekly"),
                    "github_stars": agent.get("stars"),
                },
                "details_url": f"https://nerq.ai/safe/{slug}",
                "pricing_page_url": f"https://nerq.ai/pricing/{slug}",
                "response_time_ms": round((time.time() - t0) * 1000, 1),
            }

            return JSONResponse(content=result, headers={"Cache-Control": "public, max-age=3600"})
        finally:
            session.close()

    # ═══════════════════════════════════════════════════════════
    # GET /v1/compare/{a}/vs/{b}
    # ═══════════════════════════════════════════════════════════

    @app.get("/v1/compare/{agent_a}/vs/{agent_b}")
    def compare_endpoint(agent_a: str, agent_b: str):
        t0 = time.time()
        session = get_session()
        try:
            a = _lookup_agent(agent_a, session)
            b = _lookup_agent(agent_b, session)
            if not a:
                return JSONResponse(status_code=404, content={"error": f"Agent '{agent_a}' not found"})
            if not b:
                return JSONResponse(status_code=404, content={"error": f"Agent '{agent_b}' not found"})

            conn = sqlite3.connect(str(SQLITE_DB), timeout=5)
            try:
                a_pricing = _get_pricing(a["name"], conn)
                b_pricing = _get_pricing(b["name"], conn)
                a_costs = _get_cost_estimates(a["name"], conn)
                b_costs = _get_cost_estimates(b["name"], conn)
                a_rates = _get_rate_limits(a["name"], conn)
                b_rates = _get_rate_limits(b["name"], conn)
                a_enr = _get_enrichment_data(a["name"], conn)
                b_enr = _get_enrichment_data(b["name"], conn)
            finally:
                conn.close()

            a_trust = float(a.get("trust_score") or 0)
            b_trust = float(b.get("trust_score") or 0)

            # Build pricing summary string
            def _price_summary(pricing):
                if not pricing or not pricing.get("plans"):
                    return "Unknown"
                if pricing.get("model") == "open_source_free":
                    return "Free (open source)"
                cheapest_paid = None
                for p in pricing["plans"]:
                    m = p.get("price_monthly")
                    if m is not None and m > 0:
                        if cheapest_paid is None or m < cheapest_paid:
                            cheapest_paid = m
                if cheapest_paid:
                    has_free = any((p.get("price_monthly") or 0) == 0 for p in pricing["plans"])
                    return f"{'Free tier + ' if has_free else ''}${cheapest_paid:.0f}/mo"
                return "Free"

            # Generate verdict
            trust_diff = abs(a_trust - b_trust)
            a_free = a_pricing.get("model") == "open_source_free" or a_pricing.get("has_free_tier")
            b_free = b_pricing.get("model") == "open_source_free" or b_pricing.get("has_free_tier")

            if a_trust > b_trust and a_free:
                verdict = f"{a['name']} has higher trust ({a_trust:.0f} vs {b_trust:.0f}) and is more affordable. Recommended choice."
            elif b_trust > a_trust and b_free:
                verdict = f"{b['name']} has higher trust ({b_trust:.0f} vs {a_trust:.0f}) and is more affordable. Recommended choice."
            elif a_trust > b_trust:
                verdict = f"{a['name']} has higher trust ({a_trust:.0f} vs {b_trust:.0f}) but may cost more. Choose {a['name']} for reliability, {b['name']} for cost efficiency."
            elif b_trust > a_trust:
                verdict = f"{b['name']} has higher trust ({b_trust:.0f} vs {a_trust:.0f}) but may cost more. Choose {b['name']} for reliability, {a['name']} for cost efficiency."
            else:
                verdict = f"Both agents have similar trust scores ({a_trust:.0f}). Compare pricing and features to decide."

            result = {
                "comparison": {
                    "agents": [a["name"], b["name"]],
                    "trust": {a["name"]: round(a_trust, 1), b["name"]: round(b_trust, 1)},
                    "grade": {a["name"]: a.get("trust_grade"), b["name"]: b.get("trust_grade")},
                    "pricing": {a["name"]: _price_summary(a_pricing), b["name"]: _price_summary(b_pricing)},
                    "pricing_model": {a["name"]: a_pricing.get("model"), b["name"]: b_pricing.get("model")},
                    "estimated_cost_per_task": {
                        a["name"]: a_costs.get("per_task", {}).get("code_review", "N/A"),
                        b["name"]: b_costs.get("per_task", {}).get("code_review", "N/A"),
                    },
                    "known_cves": {a["name"]: a_enr.get("cve_count", 0), b["name"]: b_enr.get("cve_count", 0)},
                    "license": {a["name"]: a_enr.get("license"), b["name"]: b_enr.get("license")},
                    "github_stars": {a["name"]: a.get("stars"), b["name"]: b.get("stars")},
                    "npm_downloads": {a["name"]: a_enr.get("npm_weekly"), b["name"]: b_enr.get("npm_weekly")},
                    "value_score": {
                        a["name"]: _compute_value_score(a_trust, a_pricing),
                        b["name"]: _compute_value_score(b_trust, b_pricing),
                    },
                    "verdict": verdict,
                },
                "response_time_ms": round((time.time() - t0) * 1000, 1),
            }

            return JSONResponse(content=result, headers={"Cache-Control": "public, max-age=3600"})
        finally:
            session.close()

    # ═══════════════════════════════════════════════════════════
    # /pricing — Hub page
    # ═══════════════════════════════════════════════════════════

    @app.get("/pricing", response_class=HTMLResponse)
    def pricing_hub(request: Request):
        host = (request.headers.get("host") or "").lower()
        if "nerq" not in host:
            return HTMLResponse(status_code=404, content="Not found")

        session = get_session()
        conn = sqlite3.connect(str(SQLITE_DB), timeout=5)
        try:
            # Get agents with pricing sorted by value score
            priced_agents = conn.execute("""
                SELECT DISTINCT agent_name, pricing_model
                FROM agent_pricing
                ORDER BY agent_name
            """).fetchall()

            # Categorize
            free_agents = []
            under_20 = []
            under_50 = []
            enterprise = []

            for r in priced_agents:
                name = r[0]
                model = r[1]
                agent = _lookup_agent(name, session)
                trust = float(agent.get("trust_score") or 0) if agent else 0
                pricing = _get_pricing(name, conn)
                value = _compute_value_score(trust, pricing)

                entry = {"name": name, "trust": trust, "value": value, "model": model,
                         "grade": agent.get("trust_grade") if agent else "N/A"}

                if model == "open_source_free":
                    free_agents.append(entry)
                else:
                    min_price = 999999
                    for p in pricing.get("plans", []):
                        pm = p.get("price_monthly")
                        if pm is not None and pm > 0:
                            min_price = min(min_price, pm)
                    if min_price <= 20:
                        under_20.append(entry)
                    elif min_price <= 50:
                        under_50.append(entry)
                    else:
                        enterprise.append(entry)

            # Sort by value score
            free_agents.sort(key=lambda x: x["value"], reverse=True)
            under_20.sort(key=lambda x: x["value"], reverse=True)
            under_50.sort(key=lambda x: x["value"], reverse=True)

            # Top 10 best value overall
            all_agents = free_agents + under_20 + under_50 + enterprise
            all_agents.sort(key=lambda x: x["value"], reverse=True)
            top_value = all_agents[:10]

        finally:
            conn.close()
            session.close()

        def _agent_row(a):
            from agentindex.agent_safety_pages import _make_slug
            slug = _make_slug(a["name"])
            return f'<tr><td><a href="/pricing/{slug}">{a["name"]}</a></td><td>{a["trust"]:.0f}</td><td>{a["grade"]}</td><td>{a["model"]}</td><td><strong>{a["value"]}</strong></td></tr>'

        def _table(agents, limit=15):
            if not agents:
                return "<p style='color:#6b7280;font-size:13px'>No agents in this category yet.</p>"
            rows = "".join(_agent_row(a) for a in agents[:limit])
            return f"<table><thead><tr><th>Agent</th><th>Trust</th><th>Grade</th><th>Pricing Model</th><th>Value Score</th></tr></thead><tbody>{rows}</tbody></table>"

        faq_schema = json.dumps({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": "How much does Cursor cost?",
                 "acceptedAnswer": {"@type": "Answer", "text": "Cursor offers a free Hobby plan with 2000 completions/month, a Pro plan at $20/month with unlimited fast completions, and a Business plan at $40/month."}},
                {"@type": "Question", "name": "What are the cheapest AI coding agents?",
                 "acceptedAnswer": {"@type": "Answer", "text": "Many excellent AI coding agents are free and open-source, including Continue, Aider, Tabby, and Open Interpreter. For commercial options, Codeium offers a free tier with unlimited autocomplete."}},
                {"@type": "Question", "name": "Is there a free alternative to GitHub Copilot?",
                 "acceptedAnswer": {"@type": "Answer", "text": "Yes. Continue-dev, Codeium (free tier), Tabby (self-hosted), and Aider are popular free alternatives to GitHub Copilot with comparable functionality."}},
            ]
        })

        body = f"""<h1>AI Agent Pricing Comparison 2026</h1>
<p class="desc">Compare pricing across {len(all_agents)} AI agents and tools. Trust scores, cost estimates, and value rankings.</p>

<div class="search-box" style="max-width:500px">
<input type="text" id="agent-input" placeholder="Compare pricing for any AI agent..." autofocus>
<button onclick="window.location.href='/pricing/'+document.getElementById('agent-input').value.toLowerCase().replace(/\\s+/g,'-')">Compare</button>
</div>

<h2>Top 10 Best Value AI Agents</h2>
<p class="desc">Highest trust-to-cost ratio. Value = trust score &times; affordability.</p>
{_table(top_value)}

<h2>Free &amp; Open Source</h2>
<p class="desc">{len(free_agents)} agents with open-source licensing — unlimited, self-hosted.</p>
{_table(free_agents)}

<h2>Under $20/month</h2>
<p class="desc">{len(under_20)} agents with affordable paid plans.</p>
{_table(under_20)}

<h2>Under $50/month</h2>
<p class="desc">{len(under_50)} agents with mid-range pricing.</p>
{_table(under_50)}

<h2>Enterprise &amp; Usage-Based</h2>
<p class="desc">{len(enterprise)} agents with enterprise or custom pricing.</p>
{_table(enterprise)}

<script type="application/ld+json">{faq_schema}</script>
<script>
document.getElementById('agent-input').addEventListener('keydown', e => {{
    if (e.key === 'Enter') {{
        const v = document.getElementById('agent-input').value.trim().toLowerCase().replace(/\\s+/g, '-');
        if (v) window.location.href = '/pricing/' + v;
    }}
}});
</script>"""

        return HTMLResponse(nerq_page(
            "AI Agent Pricing Comparison 2026 — Find the Best Value | Nerq",
            body,
            "Compare AI agent pricing across 200K+ tools. Free tier, paid plans, cost per task estimates, and value rankings.",
            "https://nerq.ai/pricing"
        ))

    # ═══════════════════════════════════════════════════════════
    # /pricing/{agent} — Individual pricing page
    # ═══════════════════════════════════════════════════════════

    @app.get("/pricing/{agent_slug}", response_class=HTMLResponse)
    def pricing_page(agent_slug: str, request: Request):
        host = (request.headers.get("host") or "").lower()
        if "nerq" not in host:
            return HTMLResponse(status_code=404, content="Not found")

        # Resolve slug to agent name
        from agentindex.agent_safety_pages import _SLUG_OVERRIDES
        override = _SLUG_OVERRIDES.get(agent_slug.lower())
        lookup_name = override or agent_slug.replace("-", " ")

        session = get_session()
        conn = sqlite3.connect(str(SQLITE_DB), timeout=5)
        try:
            agent = _lookup_agent(lookup_name, session)
            if not agent:
                return HTMLResponse(status_code=404, content=nerq_page(
                    "Agent Not Found | Nerq",
                    f'<h1>Agent Not Found</h1><p>No agent matching "{agent_slug}". <a href="/pricing">Browse all pricing</a>.</p>'
                ))

            name = agent["name"]
            trust = float(agent.get("trust_score") or 0)
            grade = agent.get("trust_grade") or "N/A"
            pricing = _get_pricing(name, conn)
            costs = _get_cost_estimates(name, conn)
            rates = _get_rate_limits(name, conn)
            enr = _get_enrichment_data(name, conn)
            value = _compute_value_score(trust, pricing)
            alternatives = _get_cheaper_alternatives(name, agent.get("category"),
                                                      trust, pricing.get("model", ""), session, conn)
        finally:
            conn.close()
            session.close()

        from agentindex.agent_safety_pages import _make_slug
        slug = _make_slug(name)

        # Plans table
        plans_html = ""
        if pricing and pricing.get("plans"):
            rows = ""
            for p in pricing["plans"]:
                price = f"${p['price_monthly']:.0f}/mo" if p.get("price_monthly") else "Free" if p.get("price_monthly") == 0 else "Contact sales"
                annual = f"${p['price_annual_monthly']:.0f}/mo" if p.get("price_annual_monthly") else "—"
                rows += f"<tr><td><strong>{p['name']}</strong></td><td>{price}</td><td>{annual}</td><td>{p.get('limits', '—')}</td><td>{p.get('features', '—')}</td></tr>"
            plans_html = f"""<h2>Pricing Plans</h2>
<table><thead><tr><th>Plan</th><th>Monthly</th><th>Annual</th><th>Limits</th><th>Features</th></tr></thead>
<tbody>{rows}</tbody></table>"""
            if pricing.get("pricing_url"):
                plans_html += f'<p style="font-size:13px;margin-top:8px"><a href="{pricing["pricing_url"]}" target="_blank" rel="nofollow">Official pricing page &rarr;</a></p>'

        # Cost estimates
        costs_html = ""
        if costs and costs.get("per_task"):
            rows = ""
            for task, cost_str in costs["per_task"].items():
                rows += f"<tr><td>{task.replace('_', ' ').title()}</td><td>{cost_str}</td></tr>"
            costs_html = f"""<h2>Estimated Cost Per Task</h2>
<p class="desc">Based on detected model: {costs.get('model_used', 'Unknown')}</p>
<table><thead><tr><th>Task</th><th>Estimated Cost</th></tr></thead>
<tbody>{rows}</tbody></table>"""

        # Rate limits
        rates_html = ""
        if rates:
            rows = ""
            for tier, limits in rates.items():
                parts = []
                if limits.get("requests_per_minute"):
                    parts.append(f"{limits['requests_per_minute']} RPM")
                if limits.get("requests_per_day"):
                    parts.append(f"{limits['requests_per_day']} RPD")
                if limits.get("tokens_per_minute"):
                    parts.append(f"{limits['tokens_per_minute']:,} TPM")
                rows += f"<tr><td>{tier}</td><td>{', '.join(parts)}</td></tr>"
            rates_html = f"""<h2>Rate Limits</h2>
<table><thead><tr><th>Tier</th><th>Limits</th></tr></thead>
<tbody>{rows}</tbody></table>"""

        # Alternatives
        alts_html = ""
        if alternatives:
            rows = ""
            for alt in alternatives:
                rows += f'<tr><td><a href="/pricing/{_make_slug(alt["name"])}">{alt["name"]}</a></td><td>{alt["trust_score"]}</td><td>{alt["pricing_model"]}</td><td>{alt.get("estimated_cost_per_task", "N/A")}</td></tr>'
            alts_html = f"""<h2>More Affordable Alternatives</h2>
<table><thead><tr><th>Agent</th><th>Trust Score</th><th>Pricing</th><th>Est. Cost/Task</th></tr></thead>
<tbody>{rows}</tbody></table>"""

        verified_badge = ' <span class="pill pill-green">Nerq Verified</span>' if trust >= 70 else ""
        value_badge = f' <span class="pill pill-green">Value: {value}/100</span>' if value > 0 else ""

        body = f"""<div class="breadcrumb"><a href="/pricing">Pricing</a> / {name}</div>
<h1>{name} Pricing 2026{verified_badge}{value_badge}</h1>
<p class="desc">Trust score: {trust:.0f}/100 ({grade}) &middot; Category: {agent.get('category', 'N/A')} &middot; {agent.get('stars') or 0} stars</p>

<div class="stat-row">
<div class="stat-item"><div class="num">{trust:.0f}</div><div class="label">Trust Score</div></div>
<div class="stat-item"><div class="num">{value}</div><div class="label">Value Score</div></div>
<div class="stat-item"><div class="num">{pricing.get('model', 'N/A')}</div><div class="label">Pricing Model</div></div>
<div class="stat-item"><div class="num">{enr.get('cve_count', 0)}</div><div class="label">Known CVEs</div></div>
</div>

{plans_html}
{costs_html}
{rates_html}
{alts_html}

<p style="margin-top:24px;font-size:13px;color:#6b7280">
<a href="/safe/{slug}">Safety report</a> &middot;
<a href="/v1/economics/{name}">API (JSON)</a> &middot;
<a href="/v1/preflight?target={name}">Preflight check</a>
</p>"""

        return HTMLResponse(nerq_page(
            f"{name} Pricing 2026 — Plans, Costs & Alternatives | Nerq",
            body,
            f"Compare {name} pricing plans, cost per task estimates, rate limits, and cheaper alternatives. Trust score: {trust:.0f}/100.",
            f"https://nerq.ai/pricing/{slug}"
        ))

    # ═══════════════════════════════════════════════════════════
    # /compare/{slug}/cost — Cost comparison page
    # ═══════════════════════════════════════════════════════════

    @app.get("/cost-compare/{slug}", response_class=HTMLResponse)
    def cost_compare_page(slug: str, request: Request):
        host = (request.headers.get("host") or "").lower()
        if "nerq" not in host:
            return HTMLResponse(status_code=404, content="Not found")

        # Parse "agent1-vs-agent2" slug
        parts = slug.split("-vs-")
        if len(parts) != 2:
            return HTMLResponse(status_code=404, content=nerq_page(
                "Invalid Comparison | Nerq",
                '<h1>Invalid comparison URL</h1><p>Use format: /compare/agent1-vs-agent2/cost</p>'
            ))

        from agentindex.agent_safety_pages import _SLUG_OVERRIDES
        a_slug, b_slug = parts[0].strip(), parts[1].strip()
        a_name = _SLUG_OVERRIDES.get(a_slug.lower(), a_slug)
        b_name = _SLUG_OVERRIDES.get(b_slug.lower(), b_slug)

        session = get_session()
        conn = sqlite3.connect(str(SQLITE_DB), timeout=5)
        try:
            a = _lookup_agent(a_name, session)
            b = _lookup_agent(b_name, session)
            if not a or not b:
                missing = a_slug if not a else b_slug
                return HTMLResponse(status_code=404, content=nerq_page(
                    "Agent Not Found | Nerq",
                    f'<h1>Agent Not Found</h1><p>"{missing}" not found. <a href="/pricing">Browse all pricing</a>.</p>'
                ))

            a_pricing = _get_pricing(a["name"], conn)
            b_pricing = _get_pricing(b["name"], conn)
            a_costs = _get_cost_estimates(a["name"], conn)
            b_costs = _get_cost_estimates(b["name"], conn)
            a_enr = _get_enrichment_data(a["name"], conn)
            b_enr = _get_enrichment_data(b["name"], conn)

            a_trust = float(a.get("trust_score") or 0)
            b_trust = float(b.get("trust_score") or 0)
            a_value = _compute_value_score(a_trust, a_pricing)
            b_value = _compute_value_score(b_trust, b_pricing)
        finally:
            conn.close()
            session.close()

        def _price_str(pricing):
            if not pricing or not pricing.get("plans"):
                return "Unknown"
            if pricing.get("model") == "open_source_free":
                return "Free (open source)"
            for p in pricing["plans"]:
                if p.get("price_monthly") and p["price_monthly"] > 0:
                    return f"From ${p['price_monthly']:.0f}/mo"
            return "Free tier available"

        # Verdict
        if a_value > b_value:
            verdict = f"{a['name']} offers better overall value (score {a_value} vs {b_value}) with {'higher' if a_trust > b_trust else 'comparable'} trust."
        elif b_value > a_value:
            verdict = f"{b['name']} offers better overall value (score {b_value} vs {a_value}) with {'higher' if b_trust > a_trust else 'comparable'} trust."
        else:
            verdict = f"Both agents offer similar value. Choose based on specific features and ecosystem fit."

        from agentindex.agent_safety_pages import _make_slug

        a_cr_cost = (a_costs.get("per_task") or {}).get("code_review", "N/A")
        b_cr_cost = (b_costs.get("per_task") or {}).get("code_review", "N/A")

        body = f"""<div class="breadcrumb"><a href="/pricing">Pricing</a> / {a['name']} vs {b['name']}</div>
<h1>{a['name']} vs {b['name']}: Pricing &amp; Trust Comparison 2026</h1>
<p class="desc">Side-by-side comparison across pricing, trust, security, and value.</p>

<table>
<thead><tr><th>Metric</th><th>{a['name']}</th><th>{b['name']}</th></tr></thead>
<tbody>
<tr><td>Trust Score</td><td><strong>{a_trust:.0f}/100</strong></td><td><strong>{b_trust:.0f}/100</strong></td></tr>
<tr><td>Grade</td><td>{a.get('trust_grade', 'N/A')}</td><td>{b.get('trust_grade', 'N/A')}</td></tr>
<tr><td>Pricing</td><td>{_price_str(a_pricing)}</td><td>{_price_str(b_pricing)}</td></tr>
<tr><td>Pricing Model</td><td>{a_pricing.get('model', 'N/A')}</td><td>{b_pricing.get('model', 'N/A')}</td></tr>
<tr><td>Code Review Cost</td><td>{a_cr_cost}</td><td>{b_cr_cost}</td></tr>
<tr><td>Known CVEs</td><td>{a_enr.get('cve_count', 0)}</td><td>{b_enr.get('cve_count', 0)}</td></tr>
<tr><td>License</td><td>{a_enr.get('license', 'Unknown')}</td><td>{b_enr.get('license', 'Unknown')}</td></tr>
<tr><td>GitHub Stars</td><td>{(a.get('stars') or 0):,}</td><td>{(b.get('stars') or 0):,}</td></tr>
<tr><td>npm Downloads/wk</td><td>{(a_enr.get('npm_weekly') or 0):,}</td><td>{(b_enr.get('npm_weekly') or 0):,}</td></tr>
<tr><td>Value Score</td><td><strong>{a_value}</strong></td><td><strong>{b_value}</strong></td></tr>
</tbody>
</table>

<div class="card" style="margin-top:20px">
<h3 style="margin:0 0 8px">Verdict</h3>
<p style="margin:0;font-size:14px">{verdict}</p>
</div>

<p style="margin-top:20px;font-size:13px;color:#6b7280">
<a href="/pricing/{_make_slug(a['name'])}">{a['name']} pricing</a> &middot;
<a href="/pricing/{_make_slug(b['name'])}">{b['name']} pricing</a> &middot;
<a href="/v1/compare/{a['name']}/vs/{b['name']}">API (JSON)</a>
</p>"""

        return HTMLResponse(nerq_page(
            f"{a['name']} vs {b['name']}: Pricing, Trust & Safety Comparison 2026 | Nerq",
            body,
            f"Compare {a['name']} vs {b['name']} across pricing, trust scores, CVEs, licenses, and value. Which AI agent is better?",
            f"https://nerq.ai/cost-compare/{a_slug}-vs-{b_slug}"
        ))

    logger.info("Mounted economics: /v1/economics, /v1/compare, /pricing, /pricing/{agent}, /compare/{slug}/cost")
