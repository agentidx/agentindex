"""
Batch Dependency Scanner API

POST /v1/scan-project — accepts a list of dependencies or a GitHub repo URL,
looks up trust scores, and returns a project health report.
"""

import base64
import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.sql import text

from agentindex.db.models import get_engine

logger = logging.getLogger("agentindex.intelligence.scan_api")

# ── LLM-related package identifiers ────────────────────────────

LLM_PACKAGES = {
    "openai": {"provider": "OpenAI", "est_monthly_usd": 120},
    "anthropic": {"provider": "Anthropic", "est_monthly_usd": 100},
    "cohere": {"provider": "Cohere", "est_monthly_usd": 80},
    "google-generativeai": {"provider": "Google Gemini", "est_monthly_usd": 90},
    "mistralai": {"provider": "Mistral", "est_monthly_usd": 60},
    "groq": {"provider": "Groq", "est_monthly_usd": 40},
    "together": {"provider": "Together AI", "est_monthly_usd": 50},
    "replicate": {"provider": "Replicate", "est_monthly_usd": 70},
    "fireworks-ai": {"provider": "Fireworks", "est_monthly_usd": 45},
    "ai21": {"provider": "AI21", "est_monthly_usd": 60},
    "huggingface-hub": {"provider": "Hugging Face", "est_monthly_usd": 30},
    "langchain-openai": {"provider": "OpenAI (via LangChain)", "est_monthly_usd": 120},
    "langchain-anthropic": {"provider": "Anthropic (via LangChain)", "est_monthly_usd": 100},
}

# ── Helpers ─────────────────────────────────────────────────────


def _lookup_dependency(conn, dep_name: str) -> Optional[Dict[str, Any]]:
    """Look up a dependency in the agents table by name (exact match first, then fuzzy)."""
    # Fast exact match first
    row = conn.execute(
        text(
            "SELECT name, trust_score_v2, trust_grade, source_url, category "
            "FROM entity_lookup WHERE name_lower = :exact AND is_active=true "
            "AND trust_score_v2 IS NOT NULL ORDER BY stars DESC LIMIT 1"
        ),
        {"exact": dep_name.lower()},
    ).fetchone()
    if not row:
        # Fallback: match as suffix (e.g., "owner/langchain" matches "langchain")
        row = conn.execute(
            text(
                "SELECT name, trust_score_v2, trust_grade, source_url, category "
                "FROM entity_lookup WHERE name_lower LIKE :pattern AND is_active=true "
                "AND trust_score_v2 IS NOT NULL "
                "AND agent_type IN ('agent', 'mcp_server', 'tool') "
                "ORDER BY stars DESC LIMIT 1"
            ),
            {"pattern": f"%/{dep_name.lower()}"},
        ).fetchone()
    if row:
        return {
            "name": row[0],
            "trust_score": round(row[1], 1) if row[1] else None,
            "trust_grade": row[2],
            "source_url": row[3],
            "category": row[4],
        }
    return None


def _compute_grade(avg_score: float) -> str:
    """Grade thresholds aligned with mass_project_scanner calibration."""
    if avg_score >= 67:
        return "A"
    elif avg_score >= 61:
        return "B"
    elif avg_score >= 56:
        return "C"
    elif avg_score >= 52:
        return "D"
    else:
        return "F"


def _find_alternative(conn, category: str, min_trust: float = 75.0) -> Optional[Dict[str, Any]]:
    """Find a higher-trust alternative in the same category."""
    row = conn.execute(
        text(
            "SELECT name, trust_score_v2, trust_grade, source_url "
            "FROM entity_lookup WHERE category = :cat AND is_active=true "
            "AND trust_score_v2 >= :min_trust "
            "ORDER BY trust_score_v2 DESC, stars DESC LIMIT 1"
        ),
        {"cat": category, "min_trust": min_trust},
    ).fetchone()
    if row:
        return {
            "name": row[0],
            "trust_score": round(row[1], 1) if row[1] else None,
            "trust_grade": row[2],
            "source_url": row[3],
        }
    return None


def _scan_dependencies(dependencies: List[Dict[str, str]]) -> Dict[str, Any]:
    """Core scan logic: look up each dependency, compute project health."""
    engine = get_engine()
    results = []
    scores = []
    critical_findings = []
    llm_providers = []
    total_est_cost = 0

    with engine.connect() as conn:
        for dep in dependencies:
            dep_name = dep.get("name", "")
            dep_version = dep.get("version", "unknown")

            entry: Dict[str, Any] = {
                "name": dep_name,
                "version": dep_version,
                "found": False,
                "trust_score": None,
                "trust_grade": None,
                "source_url": None,
                "category": None,
            }

            match = _lookup_dependency(conn, dep_name)
            if match:
                entry.update(match)
                entry["found"] = True
                if match["trust_score"] is not None:
                    scores.append(match["trust_score"])

                # Flag low-trust dependencies
                if match["trust_score"] is not None and match["trust_score"] < 40:
                    finding = {
                        "severity": "critical",
                        "dependency": dep_name,
                        "trust_score": match["trust_score"],
                        "trust_grade": match["trust_grade"],
                        "message": f"{dep_name} has a critically low trust score ({match['trust_score']})",
                    }
                    # Try to find an alternative
                    if match.get("category"):
                        alt = _find_alternative(conn, match["category"])
                        if alt:
                            finding["suggested_alternative"] = alt
                    critical_findings.append(finding)
                elif match["trust_score"] is not None and match["trust_score"] < 55:
                    critical_findings.append({
                        "severity": "warning",
                        "dependency": dep_name,
                        "trust_score": match["trust_score"],
                        "trust_grade": match["trust_grade"],
                        "message": f"{dep_name} has a low trust score ({match['trust_score']})",
                    })

            # Detect LLM usage
            dep_lower = dep_name.lower().replace("_", "-")
            if dep_lower in LLM_PACKAGES:
                info = LLM_PACKAGES[dep_lower]
                llm_providers.append(info["provider"])
                total_est_cost += info["est_monthly_usd"]

            results.append(entry)

    # Compute project health
    avg_trust = round(sum(scores) / len(scores), 1) if scores else 0.0
    project_grade = _compute_grade(avg_trust) if scores else "N/A"
    low_trust_count = sum(1 for s in scores if s < 55)
    no_score_count = sum(1 for r in results if not r["found"])

    # Alternatives for low-trust deps
    alternatives = []
    for f in critical_findings:
        if "suggested_alternative" in f:
            alternatives.append({
                "replace": f["dependency"],
                "with": f["suggested_alternative"],
            })

    # Cost insight
    cost_insight = None
    if llm_providers:
        cost_insight = {
            "detected_llm_providers": llm_providers,
            "estimated_monthly_cost_usd": total_est_cost,
            "note": "Estimates based on moderate usage patterns. Actual costs depend on volume.",
        }

    badge_markdown = (
        f"[![Nerq Project Health](https://nerq.ai/badge/project/{project_grade})]"
        f"(https://nerq.ai/scan)"
    )

    return {
        "project_health_grade": project_grade,
        "project_health_score": avg_trust,
        "total_dependencies": len(dependencies),
        "issues": {
            "critical": sum(1 for f in critical_findings if f["severity"] == "critical"),
            "warnings": sum(1 for f in critical_findings if f["severity"] == "warning"),
            "low_trust_deps": low_trust_count,
            "unscored_deps": no_score_count,
        },
        "critical_findings": critical_findings,
        "cost_insight": cost_insight,
        "alternatives": alternatives if alternatives else None,
        "badge_markdown": badge_markdown,
        "report_url": "https://nerq.ai/scan/report",
        "dependencies": results,
        "scanned_at": datetime.utcnow().isoformat() + "Z",
    }


def _parse_requirements_txt(content: str) -> List[Dict[str, str]]:
    """Parse requirements.txt content into a list of {name, version} dicts."""
    deps = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Handle version specifiers: pkg==1.0, pkg>=1.0, pkg~=1.0, pkg!=1.0
        for sep in ["==", ">=", "<=", "~=", "!=", ">", "<"]:
            if sep in line:
                name, version = line.split(sep, 1)
                deps.append({"name": name.strip(), "version": version.strip()})
                break
        else:
            # No version specifier
            # Strip extras like pkg[extra]
            name = line.split("[")[0].strip()
            if name:
                deps.append({"name": name, "version": "latest"})
    return deps


def _fetch_github_requirements(owner: str, repo: str) -> Optional[str]:
    """Fetch requirements.txt from a GitHub repository via the API."""
    token = os.getenv("GITHUB_TOKEN", "")
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/requirements.txt"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "nerq-scan/1.0")
    if token:
        req.add_header("Authorization", f"token {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if data.get("encoding") == "base64" and data.get("content"):
                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            return None
    except urllib.error.HTTPError as e:
        logger.warning(f"GitHub API error for {owner}/{repo}: {e.code}")
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch requirements from {owner}/{repo}: {e}")
        return None


def _get_cached_scan(conn, repo_full_name: str) -> Optional[Dict[str, Any]]:
    """Check project_scans table for a recent cached result."""
    row = conn.execute(
        text(
            "SELECT repo_full_name, github_stars, total_deps, deps_with_cves, "
            "critical_cves, high_cves, deps_without_license, deps_low_trust, "
            "avg_trust_score, project_health_grade, estimated_monthly_cost, "
            "top_issues, dep_list, scanned_at "
            "FROM project_scans WHERE repo_full_name = :repo LIMIT 1"
        ),
        {"repo": repo_full_name},
    ).fetchone()
    if row:
        m = dict(row._mapping)
        scanned_at = m.get("scanned_at")
        if isinstance(scanned_at, str):
            scanned_at = datetime.fromisoformat(scanned_at)
        if scanned_at and datetime.utcnow() - scanned_at < timedelta(days=7):
            top_issues = m.get("top_issues") or []
            dep_list = m.get("dep_list") or []
            if isinstance(top_issues, str):
                top_issues = json.loads(top_issues)
            if isinstance(dep_list, str):
                dep_list = json.loads(dep_list)
            return {
                "project_health_grade": m["project_health_grade"],
                "project_health_score": m["avg_trust_score"],
                "total_dependencies": m["total_deps"],
                "github_repo": m["repo_full_name"],
                "github_stars": m["github_stars"],
                "issues": {
                    "critical": m["critical_cves"],
                    "high": m["high_cves"],
                    "low_trust_deps": m["deps_low_trust"],
                    "no_license": m["deps_without_license"],
                },
                "dependencies": dep_list,
                "critical_findings": [i for i in top_issues if i.get("severity") == "critical"],
                "cached": True,
                "cached_at": scanned_at.isoformat() if hasattr(scanned_at, "isoformat") else str(scanned_at),
            }
    return None


def _cache_scan_result(conn, repo_full_name: str, result: Dict[str, Any]):
    """Store scan result in project_scans table (upsert)."""
    try:
        deps = result.get("dependencies", [])
        issues = result.get("critical_findings", [])
        conn.execute(
            text(
                "INSERT INTO project_scans "
                "(repo_full_name, github_stars, total_deps, avg_trust_score, "
                "project_health_grade, deps_low_trust, deps_without_license, "
                "top_issues, dep_list, scanned_at) "
                "VALUES (:repo, 0, :total, :avg_trust, :grade, :low, :nolic, "
                ":issues, :deps, NOW()) "
                "ON CONFLICT (repo_full_name) DO UPDATE SET "
                "total_deps=EXCLUDED.total_deps, avg_trust_score=EXCLUDED.avg_trust_score, "
                "project_health_grade=EXCLUDED.project_health_grade, "
                "deps_low_trust=EXCLUDED.deps_low_trust, deps_without_license=EXCLUDED.deps_without_license, "
                "top_issues=EXCLUDED.top_issues, dep_list=EXCLUDED.dep_list, scanned_at=NOW()"
            ),
            {
                "repo": repo_full_name,
                "total": result.get("total_dependencies", 0),
                "avg_trust": result.get("project_health_score", 0),
                "grade": result.get("project_health_grade", "?"),
                "low": result.get("issues", {}).get("low_trust_deps", 0),
                "nolic": result.get("issues", {}).get("no_license", 0),
                "issues": json.dumps(issues),
                "deps": json.dumps(deps),
            },
        )
        conn.commit()
    except Exception as e:
        logger.warning(f"Failed to cache scan result for {repo_full_name}: {e}")


# ── API mount ───────────────────────────────────────────────────


def mount_scan_api(app):
    """Mount the /v1/scan-project endpoint on the FastAPI app."""

    @app.post("/v1/scan-project")
    async def scan_project(request: Request):
        """
        Batch dependency scanner.

        Accepts either:
          {"dependencies": [{"name": "langchain", "version": "0.2.0"}, ...]}
        or:
          {"github_repo": "langchain-ai/langchain"}
        """
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid JSON body"},
            )

        # ── GitHub repo mode ────────────────────────────────
        github_repo = body.get("github_repo")
        if github_repo:
            parts = github_repo.strip("/").split("/")
            if len(parts) < 2:
                return JSONResponse(
                    status_code=400,
                    content={"error": "github_repo must be in 'owner/repo' format"},
                )
            owner, repo = parts[0], parts[1]
            repo_full = f"{owner}/{repo}"

            # Check cache
            engine = get_engine()
            with engine.connect() as conn:
                cached = _get_cached_scan(conn, repo_full)
                if cached:
                    return JSONResponse(content=cached)

            # Fetch requirements.txt
            content = _fetch_github_requirements(owner, repo)
            if content is None:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": f"Could not find requirements.txt in {repo_full}",
                        "hint": "The repository may not have a requirements.txt at the root level.",
                    },
                )

            deps = _parse_requirements_txt(content)
            if not deps:
                return JSONResponse(
                    status_code=422,
                    content={"error": "requirements.txt was found but contained no parseable dependencies"},
                )

            result = _scan_dependencies(deps)
            result["github_repo"] = repo_full

            # Cache the result
            with engine.connect() as conn:
                _cache_scan_result(conn, repo_full, result)

            return JSONResponse(content=result)

        # ── Direct dependencies mode ───────────────────────
        dependencies = body.get("dependencies")
        if not dependencies or not isinstance(dependencies, list):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Request must include 'dependencies' (array) or 'github_repo' (string)",
                    "example_dependencies": [
                        {"name": "langchain", "version": "0.2.0"},
                        {"name": "openai", "version": "1.0.0"},
                    ],
                    "example_github_repo": "langchain-ai/langchain",
                },
            )

        result = _scan_dependencies(dependencies)
        return JSONResponse(content=result)
