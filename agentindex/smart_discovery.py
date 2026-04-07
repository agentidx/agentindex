"""
Smart Discovery, Recommendation, and Improvement APIs
======================================================
Sprint 1 endpoints:
  GET  /v1/discover    — Enhanced agent search with rich filters
  GET  /v1/recommend   — Task-based agent recommendation
  GET  /v1/improve/{agent} — Actionable improvement plan

Usage in discovery.py:
    from agentindex.smart_discovery import mount_smart_discovery
    mount_smart_discovery(app)
"""

import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Query, Request
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.sql import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.smart_discovery")

SQLITE_DB = Path(__file__).parent / "crypto" / "crypto_trust.db"

# Task → category mapping
TASK_CATEGORY_MAP = {
    "code-review": "coding",
    "code review": "coding",
    "coding": "coding",
    "programming": "coding",
    "code generation": "coding",
    "code completion": "coding",
    "security": "security",
    "security-audit": "security",
    "vulnerability": "security",
    "penetration testing": "security",
    "data": "data",
    "data-analysis": "data",
    "data analysis": "data",
    "analytics": "data",
    "etl": "data",
    "automation": "automation",
    "workflow": "automation",
    "devops": "automation",
    "ci-cd": "automation",
    "chatbot": "chatbot",
    "conversational": "chatbot",
    "customer support": "chatbot",
    "research": "research",
    "rag": "research",
    "retrieval": "research",
    "search": "research",
    "writing": "writing",
    "content": "writing",
    "copywriting": "writing",
    "image": "image",
    "image generation": "image",
    "design": "image",
    "audio": "audio",
    "speech": "audio",
    "voice": "audio",
    "translation": "translation",
    "testing": "testing",
    "qa": "testing",
}

FRAMEWORK_NAMES = {
    "langchain", "crewai", "autogen", "llamaindex", "haystack",
    "semantic-kernel", "langgraph", "flowise", "dify", "langflow",
    "chainlit", "streamlit", "gradio",
}

SORT_OPTIONS = {
    "trust_score": "COALESCE(trust_score_v2, trust_score) DESC NULLS LAST",
    "popularity": "stars DESC NULLS LAST",
    "recency": "last_source_update DESC NULLS LAST",
    "name": "name ASC",
}


def _get_enrichment(agent_name):
    """Get CVE, download, license data from SQLite."""
    if not SQLITE_DB.exists():
        return {"cve_count": 0, "npm_weekly": None, "pypi_weekly": None, "license": None, "license_category": None}
    conn = sqlite3.connect(str(SQLITE_DB))
    try:
        dl = conn.execute(
            "SELECT npm_weekly, pypi_weekly FROM package_downloads WHERE agent_name = ? LIMIT 1",
            (agent_name,)
        ).fetchone()
        cve = conn.execute(
            "SELECT COUNT(*) FROM agent_vulnerabilities WHERE agent_name = ?",
            (agent_name,)
        ).fetchone()
        lic = conn.execute(
            "SELECT spdx_id, license_category FROM agent_licenses WHERE agent_name = ? LIMIT 1",
            (agent_name,)
        ).fetchone()
        return {
            "cve_count": cve[0] if cve else 0,
            "npm_weekly": dl[0] if dl else None,
            "pypi_weekly": dl[1] if dl else None,
            "license": lic[0] if lic else None,
            "license_category": lic[1] if lic else None,
        }
    except Exception:
        return {"cve_count": 0, "npm_weekly": None, "pypi_weekly": None, "license": None, "license_category": None}
    finally:
        conn.close()


def _get_enrichment_batch(agent_names):
    """Batch enrichment lookup."""
    if not SQLITE_DB.exists() or not agent_names:
        return {}
    conn = sqlite3.connect(str(SQLITE_DB))
    result = {}
    try:
        for name in agent_names:
            result[name] = {"cve_count": 0, "npm_weekly": None, "pypi_weekly": None, "license": None, "license_category": None}
            dl = conn.execute("SELECT npm_weekly, pypi_weekly FROM package_downloads WHERE agent_name = ? LIMIT 1", (name,)).fetchone()
            if dl:
                result[name]["npm_weekly"] = dl[0]
                result[name]["pypi_weekly"] = dl[1]
            cve = conn.execute("SELECT COUNT(*) FROM agent_vulnerabilities WHERE agent_name = ?", (name,)).fetchone()
            if cve:
                result[name]["cve_count"] = cve[0]
            lic = conn.execute("SELECT spdx_id, license_category FROM agent_licenses WHERE agent_name = ? LIMIT 1", (name,)).fetchone()
            if lic:
                result[name]["license"] = lic[0]
                result[name]["license_category"] = lic[1]
    except Exception as e:
        logger.warning(f"Batch enrichment error: {e}")
    finally:
        conn.close()
    return result


def _format_agent_result(row, enrichment=None):
    """Format a DB row into a clean API result."""
    d = dict(row._mapping) if hasattr(row, "_mapping") else row
    name = d.get("name") or ""
    score = d.get("trust_score") or d.get("current_score") or 0
    grade = d.get("trust_grade") or "N/A"
    enr = enrichment or {}

    from agentindex.agent_safety_pages import _make_slug
    slug = _make_slug(name)

    return {
        "name": name,
        "trust_score": round(float(score), 1) if score else 0,
        "grade": grade,
        "category": d.get("category") or "uncategorized",
        "description": (d.get("description") or "")[:300],
        "npm_weekly_downloads": enr.get("npm_weekly"),
        "pypi_weekly_downloads": enr.get("pypi_weekly"),
        "github_stars": d.get("stars") or 0,
        "known_cves": enr.get("cve_count", 0),
        "license": enr.get("license"),
        "license_category": enr.get("license_category"),
        "source": d.get("source") or "unknown",
        "author": d.get("author") or "Unknown",
        "is_verified": d.get("is_verified") or (float(score or 0) >= 70),
        "preflight_url": f"https://nerq.ai/v1/preflight?target={name}",
        "details_url": f"https://nerq.ai/safe/{slug}",
    }


def mount_smart_discovery(app):

    # ═══════════════════════════════════════════════════════════
    # GET /v1/discover — Enhanced search with filters
    # ═══════════════════════════════════════════════════════════

    @app.get("/v1/discover")
    def discover_get(
        q: str = Query(..., description="Search query"),
        min_trust_score: Optional[int] = Query(None, ge=0, le=100),
        max_trust_score: Optional[int] = Query(None, ge=0, le=100),
        has_no_cves: Optional[bool] = Query(None),
        license_type: Optional[str] = Query(None, description="PERMISSIVE, COPYLEFT, VIRAL, UNKNOWN"),
        framework: Optional[str] = Query(None),
        category: Optional[str] = Query(None),
        sort: Optional[str] = Query("trust_score", description="trust_score, popularity, recency, name"),
        limit: int = Query(20, ge=1, le=100),
        request: Request = None,
    ):
        start = time.time()
        session = get_session()
        try:
            # Check if query matches a category
            q_lower = q.lower().strip()
            resolved_category = category
            if not resolved_category:
                resolved_category = TASK_CATEGORY_MAP.get(q_lower)

            # Check if query matches a framework
            resolved_framework = framework
            if not resolved_framework and q_lower in FRAMEWORK_NAMES:
                resolved_framework = q_lower

            # Build SQL
            conditions = ["is_active = true"]
            params = {}

            if resolved_category:
                conditions.append("category = :category")
                params["category"] = resolved_category

            if min_trust_score is not None:
                conditions.append("COALESCE(trust_score_v2, trust_score) >= :min_ts")
                params["min_ts"] = min_trust_score

            if max_trust_score is not None:
                conditions.append("COALESCE(trust_score_v2, trust_score) <= :max_ts")
                params["max_ts"] = max_trust_score

            if resolved_framework:
                conditions.append("frameworks::text ILIKE :fw_pattern")
                params["fw_pattern"] = f"%{resolved_framework}%"

            # Text search if not pure category/framework lookup
            if not resolved_category and not resolved_framework:
                conditions.append(
                    "(to_tsvector('english', coalesce(name, '') || ' ' || "
                    "coalesce(description, '') || ' ' || coalesce(category, '')) "
                    "@@ plainto_tsquery('english', :q) "
                    "OR name ILIKE :q_like)"
                )
                params["q"] = q
                params["q_like"] = f"%{q}%"

            where = " AND ".join(conditions)
            order = SORT_OPTIONS.get(sort, SORT_OPTIONS["trust_score"])

            sql = f"""
                SELECT name, COALESCE(trust_score_v2, trust_score) as trust_score,
                       trust_grade, category, description, stars, source, author,
                       is_verified, source_url
                FROM entity_lookup
                WHERE {where}
                ORDER BY {order}
                LIMIT :lim
            """
            params["lim"] = limit

            rows = session.execute(text(sql), params).fetchall()

            # Count total
            count_sql = f"SELECT COUNT(*) FROM entity_lookup WHERE {where}"
            count_params = {k: v for k, v in params.items() if k != "lim"}
            total = session.execute(text(count_sql), count_params).scalar() or 0

            # Enrich with CVE/download data
            names = [dict(r._mapping)["name"] for r in rows]
            enrichment = _get_enrichment_batch(names)

            # Format results
            results = []
            for r in rows:
                d = dict(r._mapping)
                enr = enrichment.get(d["name"], {})

                # Post-filter: has_no_cves
                if has_no_cves and enr.get("cve_count", 0) > 0:
                    continue
                # Post-filter: license_type
                if license_type and enr.get("license_category") != license_type.upper():
                    continue

                results.append(_format_agent_result(r, enr))

            filters_applied = {}
            if min_trust_score is not None:
                filters_applied["min_trust_score"] = min_trust_score
            if max_trust_score is not None:
                filters_applied["max_trust_score"] = max_trust_score
            if has_no_cves:
                filters_applied["has_no_cves"] = True
            if license_type:
                filters_applied["license_type"] = license_type
            if resolved_framework:
                filters_applied["framework"] = resolved_framework
            if resolved_category:
                filters_applied["category"] = resolved_category

            return JSONResponse(content={
                "query": q,
                "total_results": total,
                "results": results,
                "filters_applied": filters_applied,
                "sort": sort,
                "response_time_ms": round((time.time() - start) * 1000, 1),
            })
        finally:
            session.close()

    # ═══════════════════════════════════════════════════════════
    # GET /v1/recommend — Task-based recommendation
    # ═══════════════════════════════════════════════════════════

    @app.get("/v1/recommend")
    def recommend(
        task: str = Query(..., description="Task description (e.g., code-review, security-audit)"),
        framework: Optional[str] = Query(None),
        min_trust: int = Query(60, ge=0, le=100),
        max_cost_monthly: Optional[float] = Query(None, description="Max monthly cost (0=free only)"),
        pricing_model: Optional[str] = Query(None, description="open_source_free, per_seat, per_call, usage_based"),
        sort: Optional[str] = Query("composite", description="composite, trust_score, value"),
        limit: int = Query(5, ge=1, le=20),
    ):
        start = time.time()
        session = get_session()
        try:
            # Map task to category
            task_lower = task.lower().strip()
            category = TASK_CATEGORY_MAP.get(task_lower)

            # Build query
            conditions = [
                "is_active = true",
                "COALESCE(trust_score_v2, trust_score) >= :min_trust",
            ]
            params = {"min_trust": min_trust}

            if category:
                conditions.append("category = :category")
                params["category"] = category

            if framework:
                conditions.append("frameworks::text ILIKE :fw")
                params["fw"] = f"%{framework}%"

            # If no category match, do text search
            if not category:
                conditions.append(
                    "(to_tsvector('english', coalesce(name, '') || ' ' || "
                    "coalesce(description, '') || ' ' || coalesce(category, '')) "
                    "@@ plainto_tsquery('english', :task) "
                    "OR category ILIKE :task_like)"
                )
                params["task"] = task
                params["task_like"] = f"%{task}%"

            where = " AND ".join(conditions)

            # Fetch candidates (more than needed for ranking)
            # last_source_update not in entity_lookup; use agents with work_mem guard
            session.execute(text("SET LOCAL work_mem = '2MB'"))
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            sql = f"""
                SELECT name, COALESCE(trust_score_v2, trust_score) as trust_score,
                       trust_grade, category, description, stars, source, author,
                       is_verified, source_url, last_source_update
                FROM agents
                WHERE {where}
                ORDER BY COALESCE(trust_score_v2, trust_score) DESC NULLS LAST
                LIMIT :fetch_limit
            """
            params["fetch_limit"] = limit * 10

            rows = session.execute(text(sql), params).fetchall()

            # Enrich
            names = [dict(r._mapping)["name"] for r in rows]
            enrichment = _get_enrichment_batch(names)

            # Get pricing data for cost filtering
            pricing_data = {}
            if max_cost_monthly is not None or pricing_model or sort == "value":
                try:
                    import sqlite3 as _sqlite3
                    _conn = _sqlite3.connect(str(SQLITE_DB), timeout=3)
                    for name in names:
                        rows_p = _conn.execute(
                            "SELECT pricing_model, price_monthly FROM agent_pricing WHERE agent_name = ? OR agent_name LIKE ?",
                            (name, f"%{name}%")
                        ).fetchall()
                        if rows_p:
                            pricing_data[name] = {
                                "model": rows_p[0][0],
                                "min_price": min((r[1] or 0) for r in rows_p),
                                "has_free": any((r[1] or 0) == 0 for r in rows_p),
                            }
                    _conn.close()
                except Exception:
                    pass

            # Rank by composite: trust(40%) + popularity(30%) + recency(20%) + compatibility(10%)
            scored = []
            for r in rows:
                d = dict(r._mapping)
                enr = enrichment.get(d["name"], {})

                # Skip if has critical CVEs
                if enr.get("cve_count", 0) > 5:
                    continue

                agent_name = d["name"]

                # Apply cost filter
                if max_cost_monthly is not None:
                    pd = pricing_data.get(agent_name, {})
                    if pd:
                        if max_cost_monthly == 0:
                            if not pd.get("has_free") and pd.get("model") != "open_source_free":
                                continue
                        elif pd.get("min_price", 0) > max_cost_monthly:
                            continue

                # Apply pricing model filter
                if pricing_model:
                    pd = pricing_data.get(agent_name, {})
                    if pd and pd.get("model") != pricing_model:
                        continue

                trust = float(d.get("trust_score") or 0)
                stars = d.get("stars") or 0
                downloads = (enr.get("npm_weekly") or 0) + (enr.get("pypi_weekly") or 0)
                pop = min((stars + downloads) / 10000.0, 1.0) * 100

                # Recency score
                recency = 50  # default
                last_update = d.get("last_source_update")
                if last_update:
                    try:
                        dt = datetime.fromisoformat(str(last_update)[:19])
                        days_ago = (datetime.now() - dt).days
                        recency = max(100 - days_ago, 0)
                    except Exception:
                        pass

                # Compatibility score (framework match)
                compat = 100 if framework else 70

                # Value score for sorting
                pd = pricing_data.get(agent_name, {})
                affordability = 1.0
                if pd:
                    if pd.get("model") == "open_source_free":
                        affordability = 1.0
                    elif pd.get("has_free"):
                        affordability = 0.95
                    elif pd.get("min_price"):
                        affordability = max(0.1, 1.0 - (pd["min_price"] / 300.0))
                value = trust * affordability

                if sort == "value":
                    composite = value
                elif sort == "trust_score":
                    composite = trust
                else:
                    composite = trust * 0.4 + pop * 0.3 + recency * 0.2 + compat * 0.1

                scored.append((composite, d, enr, pricing_data.get(agent_name)))

            scored.sort(key=lambda x: x[0], reverse=True)
            top = scored[:limit]

            # Format recommendations
            recommendations = []
            for rank, (score, d, enr, pd) in enumerate(top, 1):
                name = d["name"]
                trust_score = d.get("trust_score") or 0
                grade = d.get("trust_grade") or "N/A"
                cves = enr.get("cve_count", 0)
                lic = enr.get("license") or "Unknown"

                from agentindex.agent_safety_pages import _make_slug
                slug = _make_slug(name)

                # Generate "why" explanation
                why_parts = []
                if float(trust_score) >= 80:
                    why_parts.append(f"High trust score ({trust_score:.0f}/100)")
                elif float(trust_score) >= 70:
                    why_parts.append(f"Verified trust score ({trust_score:.0f}/100)")
                if cves == 0:
                    why_parts.append("Zero known CVEs")
                if lic and lic != "Unknown":
                    why_parts.append(f"{lic} licensed")
                if framework:
                    why_parts.append(f"Compatible with {framework}")
                stars_val = d.get("stars") or 0
                if stars_val > 1000:
                    why_parts.append(f"{stars_val:,} GitHub stars")
                if pd and pd.get("model") == "open_source_free":
                    why_parts.append("Free & open source")
                elif pd and pd.get("has_free"):
                    why_parts.append("Free tier available")

                rec = {
                    "rank": rank,
                    "name": name,
                    "trust_score": round(float(trust_score), 1),
                    "grade": grade,
                    "category": d.get("category") or "uncategorized",
                    "why": ". ".join(why_parts) + "." if why_parts else "Matches your criteria.",
                    "known_cves": cves,
                    "license": lic,
                    "github_stars": stars_val,
                    "preflight_url": f"https://nerq.ai/v1/preflight?target={name}",
                    "details_url": f"https://nerq.ai/safe/{slug}",
                }
                if pd:
                    rec["pricing_model"] = pd.get("model")
                recommendations.append(rec)

            constraints = {
                "framework": framework,
                "min_trust": min_trust,
            }
            if max_cost_monthly is not None:
                constraints["max_cost_monthly"] = max_cost_monthly
            if pricing_model:
                constraints["pricing_model"] = pricing_model

            return JSONResponse(content={
                "task": task,
                "mapped_category": category,
                "constraints": constraints,
                "sort": sort,
                "total_candidates": len(scored),
                "recommendations": recommendations,
                "response_time_ms": round((time.time() - start) * 1000, 1),
            })
        finally:
            session.close()

    # ═══════════════════════════════════════════════════════════
    # GET /v1/improve/{agent} — Improvement plan
    # ═══════════════════════════════════════════════════════════

    @app.get("/v1/improve/{agent_name}")
    def improve(agent_name: str):
        start = time.time()
        session = get_session()
        try:
            # Look up agent
            row = session.execute(text("""
                SELECT name, COALESCE(trust_score_v2, trust_score) as trust_score,
                       trust_grade, category, source, stars, author, description,
                       compliance_score, documentation_score, activity_score,
                       security_score, popularity_score, is_verified,
                       eu_risk_class, source_url
                FROM entity_lookup
                WHERE (name_lower = :name_lower OR name_lower LIKE :pattern)
                  AND is_active = true
                ORDER BY CASE WHEN name_lower = :name_lower THEN 0 ELSE 1 END,
                         COALESCE(trust_score_v2, trust_score) DESC NULLS LAST
                LIMIT 1
            """), {"name_lower": agent_name.lower(), "pattern": f"%{agent_name.lower()}%"}).fetchone()

            if not row:
                return JSONResponse(status_code=404, content={"error": f"Agent '{agent_name}' not found"})

            d = dict(row._mapping)
            name = d["name"]
            current_score = float(d.get("trust_score") or 0)
            grade = d.get("trust_grade") or "N/A"

            # Get enrichment
            enr = _get_enrichment(name)

            # Analyze weaknesses and generate improvements
            improvements = []
            potential_gain = 0

            # Dimension scores
            security = d.get("security_score")
            compliance = d.get("compliance_score")
            documentation = d.get("documentation_score")
            activity = d.get("activity_score")
            popularity = d.get("popularity_score")

            # CVE improvements
            cve_count = enr.get("cve_count", 0)
            if cve_count > 0:
                impact = min(cve_count * 4, 15)
                improvements.append({
                    "priority": len(improvements) + 1,
                    "action": f"Fix {cve_count} known {'vulnerability' if cve_count == 1 else 'vulnerabilities'} in dependencies",
                    "estimated_impact": f"+{impact} points",
                    "dimension": "Security",
                    "current_value": f"{cve_count} CVEs",
                })
                potential_gain += impact

            # License improvements
            lic_cat = enr.get("license_category")
            if not lic_cat or lic_cat == "UNKNOWN":
                impact = 5
                improvements.append({
                    "priority": len(improvements) + 1,
                    "action": "Add a LICENSE file (MIT recommended for maximum compatibility)",
                    "estimated_impact": f"+{impact} points",
                    "dimension": "Compliance",
                    "current_value": "No license detected",
                })
                potential_gain += impact

            # Documentation improvements
            if documentation is not None and documentation < 50:
                impact = int((50 - documentation) * 0.3)
                improvements.append({
                    "priority": len(improvements) + 1,
                    "action": "Add comprehensive README with installation instructions, usage examples, and API documentation",
                    "estimated_impact": f"+{impact} points",
                    "dimension": "Documentation",
                    "current_value": f"{documentation:.0f}/100",
                })
                potential_gain += impact

            # Activity improvements
            if activity is not None and activity < 50:
                impact = int((50 - activity) * 0.2)
                improvements.append({
                    "priority": len(improvements) + 1,
                    "action": "Increase release cadence and respond to issues within 7 days",
                    "estimated_impact": f"+{impact} points",
                    "dimension": "Maintenance",
                    "current_value": f"{activity:.0f}/100",
                })
                potential_gain += impact

            # Popularity improvements
            npm = enr.get("npm_weekly") or 0
            pypi = enr.get("pypi_weekly") or 0
            stars_val = d.get("stars") or 0
            if npm == 0 and pypi == 0:
                impact = 5
                improvements.append({
                    "priority": len(improvements) + 1,
                    "action": "Publish to npm and/or PyPI for broader distribution and download tracking",
                    "estimated_impact": f"+{impact} points",
                    "dimension": "Popularity",
                    "current_value": "No package registry presence",
                })
                potential_gain += impact

            if stars_val < 10:
                impact = 3
                improvements.append({
                    "priority": len(improvements) + 1,
                    "action": "Add project to Awesome lists and promote in relevant communities to increase GitHub stars",
                    "estimated_impact": f"+{impact} points",
                    "dimension": "Popularity",
                    "current_value": f"{stars_val} stars",
                })
                potential_gain += impact

            # Security score improvements
            if security is not None and security < 60:
                impact = int((60 - security) * 0.2)
                improvements.append({
                    "priority": len(improvements) + 1,
                    "action": "Enable automated security scanning (Dependabot, Snyk) and add security policy (SECURITY.md)",
                    "estimated_impact": f"+{impact} points",
                    "dimension": "Security",
                    "current_value": f"{security:.0f}/100",
                })
                potential_gain += impact

            # Compliance improvements
            eu_risk = d.get("eu_risk_class") or ""
            if not eu_risk or eu_risk.lower() in ("high", "unacceptable"):
                impact = 4
                improvements.append({
                    "priority": len(improvements) + 1,
                    "action": "Add EU AI Act compliance documentation and risk classification to repository",
                    "estimated_impact": f"+{impact} points",
                    "dimension": "Compliance",
                    "current_value": f"EU risk class: {eu_risk or 'Not classified'}",
                })
                potential_gain += impact

            # Nerq badge
            if not d.get("is_verified"):
                improvements.append({
                    "priority": len(improvements) + 1,
                    "action": "Add Nerq Trust Badge to README to signal trust verification to users",
                    "estimated_impact": "+0 points (visibility only)",
                    "dimension": "Ecosystem",
                    "current_value": "No trust badge",
                })

            # Sort by estimated impact (descending)
            improvements.sort(key=lambda x: int(x["estimated_impact"].replace("+", "").split()[0]) if x["estimated_impact"][1:].split()[0].isdigit() else 0, reverse=True)
            for i, imp in enumerate(improvements):
                imp["priority"] = i + 1

            potential_score = min(current_score + potential_gain, 100)

            # Grade lookup
            def _grade(s):
                if s >= 90: return "A+"
                if s >= 85: return "A"
                if s >= 80: return "A-"
                if s >= 75: return "B+"
                if s >= 70: return "B"
                if s >= 65: return "B-"
                if s >= 60: return "C+"
                if s >= 55: return "C"
                if s >= 50: return "C-"
                if s >= 45: return "D+"
                if s >= 40: return "D"
                return "F"

            from agentindex.agent_safety_pages import _make_slug
            slug = _make_slug(name)

            return JSONResponse(content={
                "agent": name,
                "current_score": round(current_score, 1),
                "current_grade": grade,
                "potential_score": round(potential_score, 1),
                "potential_grade": _grade(potential_score),
                "improvements": improvements,
                "dimensions": {
                    "security": round(security, 1) if security else None,
                    "compliance": round(compliance, 1) if compliance else None,
                    "documentation": round(documentation, 1) if documentation else None,
                    "maintenance": round(activity, 1) if activity else None,
                    "popularity": round(popularity, 1) if popularity else None,
                },
                "enrichment": {
                    "known_cves": enr.get("cve_count", 0),
                    "license": enr.get("license"),
                    "npm_weekly_downloads": enr.get("npm_weekly"),
                    "pypi_weekly_downloads": enr.get("pypi_weekly"),
                    "github_stars": stars_val,
                },
                "details_url": f"https://nerq.ai/safe/{slug}",
                "response_time_ms": round((time.time() - start) * 1000, 1),
            })
        finally:
            session.close()

    # ═══════════════════════════════════════════════════════════
    # /recommend — Interactive UI page
    # ═══════════════════════════════════════════════════════════

    @app.get("/recommend", response_class=HTMLResponse)
    def recommend_page(request: Request):
        host = (request.headers.get("host") or "").lower()
        if "nerq" not in host:
            return HTMLResponse(status_code=404, content="Not found")

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Agent Recommender — Find the Best Agent for Your Task | Nerq</title>
<meta name="description" content="Get personalized AI agent recommendations based on your task. Nerq analyzes 204K+ agents across trust, security, and compatibility to find the best match.">
<link rel="canonical" href="https://nerq.ai/recommend">
<style>{NERQ_CSS}
.rec-form {{ max-width: 600px; margin: 24px auto; }}
.rec-form input, .rec-form select {{ padding: 10px 14px; border: 1px solid #e5e7eb; font-size: 14px; font-family: system-ui, sans-serif; width: 100%; margin-bottom: 12px; }}
.rec-form button {{ padding: 10px 24px; background: #0d9488; color: #fff; border: none; font-size: 14px; font-weight: 600; cursor: pointer; width: 100%; }}
.rec-results {{ max-width: 700px; margin: 20px auto; }}
.rec-card {{ border: 1px solid #e5e7eb; padding: 20px; margin-bottom: 12px; }}
.rec-card h3 {{ margin: 0 0 8px; font-size: 16px; }}
.rec-card .why {{ font-size: 13px; color: #374151; line-height: 1.6; }}
.rec-rank {{ font-family: ui-monospace, monospace; font-size: 12px; color: #0d9488; font-weight: 700; }}
.rec-score {{ font-family: ui-monospace, monospace; font-size: 14px; color: #1a1a1a; }}
</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:20px;padding-bottom:40px">
  <h1>AI Agent Recommender</h1>
  <p class="desc">Describe your task and get personalized agent recommendations ranked by trust, popularity, and compatibility.</p>

  <div class="rec-form">
    <input id="task" placeholder="What do you need? (e.g., code review, security audit, data analysis)" autofocus>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">
      <select id="framework">
        <option value="">Any framework</option>
        <option value="langchain">LangChain</option>
        <option value="crewai">CrewAI</option>
        <option value="autogen">AutoGen</option>
        <option value="llamaindex">LlamaIndex</option>
        <option value="haystack">Haystack</option>
      </select>
      <select id="min_trust">
        <option value="60">Min trust: 60</option>
        <option value="70" selected>Min trust: 70</option>
        <option value="80">Min trust: 80</option>
        <option value="50">Min trust: 50</option>
      </select>
      <select id="limit">
        <option value="5" selected>Top 5</option>
        <option value="10">Top 10</option>
        <option value="3">Top 3</option>
      </select>
    </div>
    <button onclick="doRecommend()">Find Best Agents</button>
  </div>

  <div id="results" class="rec-results"></div>
</main>
{NERQ_FOOTER}
<script>
async function doRecommend() {{
  const task = document.getElementById('task').value.trim();
  if (!task) return;
  const fw = document.getElementById('framework').value;
  const mt = document.getElementById('min_trust').value;
  const lim = document.getElementById('limit').value;
  const el = document.getElementById('results');
  el.innerHTML = '<p style="color:#6b7280">Searching 204K agents...</p>';
  let url = `/v1/recommend?task=${{encodeURIComponent(task)}}&min_trust=${{mt}}&limit=${{lim}}`;
  if (fw) url += `&framework=${{fw}}`;
  try {{
    const r = await fetch(url);
    const d = await r.json();
    if (!d.recommendations || d.recommendations.length === 0) {{
      el.innerHTML = '<p>No agents found matching your criteria. Try broadening your search.</p>';
      return;
    }}
    let html = `<p style="font-size:13px;color:#6b7280;margin-bottom:16px">${{d.total_candidates}} candidates evaluated in ${{d.response_time_ms}}ms</p>`;
    for (const rec of d.recommendations) {{
      html += `<div class="rec-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <h3><span class="rec-rank">#${{rec.rank}}</span> ${{rec.name}}</h3>
          <span class="rec-score">${{rec.trust_score}}/100 (${{rec.grade}})</span>
        </div>
        <p class="why">${{rec.why}}</p>
        <div style="margin-top:8px;font-size:12px;color:#6b7280">
          ${{rec.category}} &middot; ${{rec.github_stars?.toLocaleString() || 0}} stars &middot; ${{rec.known_cves}} CVEs &middot; ${{rec.license || 'Unknown'}}
        </div>
        <div style="margin-top:8px;display:flex;gap:8px">
          <a href="${{rec.details_url}}" style="font-size:12px;color:#0d9488">Safety report</a>
          <a href="${{rec.preflight_url}}" style="font-size:12px;color:#0d9488">Preflight check</a>
        </div>
      </div>`;
    }}
    el.innerHTML = html;
  }} catch(e) {{
    el.innerHTML = '<p style="color:red">Error: ' + e.message + '</p>';
  }}
}}
document.getElementById('task').addEventListener('keydown', e => {{ if(e.key === 'Enter') doRecommend(); }});
</script>
</body>
</html>"""
        return HTMLResponse(content=html)

    # ═══════════════════════════════════════════════════════════
    # /improve — Interactive UI page
    # ═══════════════════════════════════════════════════════════

    @app.get("/improve", response_class=HTMLResponse)
    def improve_page(request: Request):
        host = (request.headers.get("host") or "").lower()
        if "nerq" not in host:
            return HTMLResponse(status_code=404, content="Not found")

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Improve Your Agent's Trust Score | Nerq</title>
<meta name="description" content="Get specific, actionable steps to improve your AI agent's Nerq Trust Score. Fix vulnerabilities, add licenses, improve documentation, and more.">
<link rel="canonical" href="https://nerq.ai/improve">
<style>{NERQ_CSS}
.imp-form {{ max-width: 500px; margin: 24px auto; display: flex; gap: 8px; }}
.imp-form input {{ flex: 1; padding: 10px 14px; border: 1px solid #e5e7eb; font-size: 14px; font-family: system-ui, sans-serif; }}
.imp-form button {{ padding: 10px 24px; background: #0d9488; color: #fff; border: none; font-size: 14px; font-weight: 600; cursor: pointer; }}
.imp-results {{ max-width: 700px; margin: 20px auto; }}
.imp-card {{ border-left: 3px solid #0d9488; padding: 16px 20px; margin-bottom: 12px; background: #f9fafb; }}
.imp-card .dim {{ font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.03em; }}
.imp-card .action {{ font-size: 15px; font-weight: 600; color: #1a1a1a; margin: 4px 0; }}
.imp-card .impact {{ font-family: ui-monospace, monospace; color: #0d9488; font-size: 13px; }}
.score-arc {{ text-align: center; margin: 20px 0; }}
.score-arc .current {{ font-size: 3rem; font-weight: 700; color: #6b7280; font-family: ui-monospace, monospace; }}
.score-arc .arrow {{ font-size: 2rem; color: #0d9488; margin: 0 12px; }}
.score-arc .potential {{ font-size: 3rem; font-weight: 700; color: #0d9488; font-family: ui-monospace, monospace; }}
</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:20px;padding-bottom:40px">
  <h1>Improve Your Trust Score</h1>
  <p class="desc">Enter your agent or tool name to get specific, actionable steps to improve your Nerq Trust Score.</p>

  <div class="imp-form">
    <input id="agent" placeholder="Agent or tool name..." autofocus>
    <button onclick="doImprove()">Analyze</button>
  </div>

  <div id="results" class="imp-results"></div>
</main>
{NERQ_FOOTER}
<script>
async function doImprove() {{
  const name = document.getElementById('agent').value.trim();
  if (!name) return;
  const el = document.getElementById('results');
  el.innerHTML = '<p style="color:#6b7280">Analyzing...</p>';
  try {{
    const r = await fetch(`/v1/improve/${{encodeURIComponent(name)}}`);
    if (r.status === 404) {{ el.innerHTML = '<p>Agent not found. Try a different name.</p>'; return; }}
    const d = await r.json();
    let html = `<div class="score-arc">
      <span class="current">${{d.current_score}} <small style="font-size:14px;color:#6b7280">${{d.current_grade}}</small></span>
      <span class="arrow">&rarr;</span>
      <span class="potential">${{d.potential_score}} <small style="font-size:14px">${{d.potential_grade}}</small></span>
    </div>
    <p style="text-align:center;color:#6b7280;font-size:13px;margin-bottom:24px">
      ${{d.agent}} &mdash; ${{d.improvements.length}} improvement${{d.improvements.length !== 1 ? 's' : ''}} identified
    </p>`;
    for (const imp of d.improvements) {{
      html += `<div class="imp-card">
        <div class="dim">#${{imp.priority}} &middot; ${{imp.dimension}}</div>
        <div class="action">${{imp.action}}</div>
        <div class="impact">${{imp.estimated_impact}}</div>
        ${{imp.current_value ? `<div style="font-size:12px;color:#6b7280;margin-top:4px">Current: ${{imp.current_value}}</div>` : ''}}
      </div>`;
    }}
    el.innerHTML = html;
  }} catch(e) {{
    el.innerHTML = '<p style="color:red">Error: ' + e.message + '</p>';
  }}
}}
document.getElementById('agent').addEventListener('keydown', e => {{ if(e.key === 'Enter') doImprove(); }});
</script>
</body>
</html>"""
        return HTMLResponse(content=html)

    logger.info("Mounted smart discovery: /v1/discover (GET), /v1/recommend, /v1/improve, /recommend, /improve")
