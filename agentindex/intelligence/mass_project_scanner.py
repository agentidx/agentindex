#!/usr/bin/env python3
"""
Mass Project Scanner — Scan top AI repos for dependency health
===============================================================
Fetches requirements.txt/package.json from GitHub, parses deps,
looks up trust scores in DB, calculates project health grade.

Usage:
    python -m agentindex.intelligence.mass_project_scanner --top 1000
    python -m agentindex.intelligence.mass_project_scanner --top 10000 --batch 100
"""

import json
import logging
import os
import re
import time
import base64
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.sql import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [mass-scanner] %(message)s",
)
log = logging.getLogger("mass-scanner")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
RATE_DELAY = 0.8  # seconds between GitHub API calls


# ── Dependency file fetching ───────────────────────────────────

def _gh_get(url):
    """GET from GitHub API with auth."""
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "NerqMassScanner/1.0")
    if GITHUB_TOKEN:
        req.add_header("Authorization", f"token {GITHUB_TOKEN}")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        if e.code == 403:
            log.warning(f"Rate limited on {url}")
            return None
        return None
    except Exception:
        return None


def _fetch_file_content(repo_slug, filepath):
    """Fetch a file's content from GitHub API (base64 decoded)."""
    data = _gh_get(f"https://api.github.com/repos/{repo_slug}/contents/{filepath}")
    if not data or "content" not in data:
        return None
    try:
        return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    except Exception:
        return None


def _fetch_dep_file(repo_slug):
    """Try to fetch dependency file from repo. Returns (content, filetype) or (None, None)."""
    # Standard root-level files
    for path, filetype, check in [
        ("requirements.txt", "requirements", lambda c: len(c.strip()) > 5),
        ("pyproject.toml", "pyproject", lambda c: "[project]" in c or "[tool.poetry" in c or "[dependency-groups]" in c),
        ("package.json", "package_json", lambda c: "{" in c),
        ("setup.py", "setup_py", lambda c: "install_requires" in c),
    ]:
        content = _fetch_file_content(repo_slug, path)
        if content and check(content):
            return content, filetype

    # Monorepo: check common subdirectory patterns
    monorepo_paths = [
        "libs/langchain/pyproject.toml",
        "libs/langchain-core/pyproject.toml",
        "python/pyproject.toml",
        "python/requirements.txt",
        "python/packages/autogen-core/pyproject.toml",
        "packages/core/package.json",
        "core/pyproject.toml",
        "src/pyproject.toml",
        "sdk/python/pyproject.toml",
        "sdk/python/requirements.txt",
    ]
    for path in monorepo_paths:
        content = _fetch_file_content(repo_slug, path)
        if content:
            if path.endswith("pyproject.toml") and ("[project]" in content or "[tool.poetry" in content or "[dependency-groups]" in content):
                return content, "pyproject"
            elif path.endswith("requirements.txt") and len(content.strip()) > 5:
                return content, "requirements"
            elif path.endswith("package.json") and "{" in content:
                return content, "package_json"

    return None, None


# ── Dependency parsing ─────────────────────────────────────────

def _parse_requirements(content):
    """Parse requirements.txt into list of (name, version_spec)."""
    deps = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Handle name==version, name>=version, name
        match = re.match(r'^([a-zA-Z0-9_.-]+)\s*([><=!~]+\s*[\d.]+)?', line)
        if match:
            name = match.group(1).lower().replace("-", "_").replace(".", "_")
            version = (match.group(2) or "").strip().lstrip(">=<!=~")
            deps.append((match.group(1), version))
    return deps


def _parse_pyproject(content):
    """Parse pyproject.toml dependencies from [project] and [tool.poetry] sections."""
    deps = []
    in_deps = False
    in_valid_section = False
    bracket_depth = 0

    # Valid dependency sections
    dep_headers = {
        "dependencies", "install_requires",
        "[project]", "[tool.poetry.dependencies]",
    }
    # Sections that should NOT be parsed (contain config, not deps)
    skip_sections = {
        "tool.ruff", "tool.mypy", "tool.pytest", "tool.black",
        "tool.isort", "tool.pylint", "tool.coverage", "tool.flake8",
        "tool.ruff.lint", "tool.ruff.format",
    }

    current_section = ""
    for line in content.splitlines():
        stripped = line.strip()

        # Track TOML sections
        section_match = re.match(r'^\[([^\]]+)\]', stripped)
        if section_match:
            current_section = section_match.group(1).strip()
            in_deps = False
            continue

        # Skip config sections entirely
        if any(current_section.startswith(s) for s in skip_sections):
            continue

        # Detect start of dependencies array
        # [dependency-groups] uses named groups like "dev = [...]"
        is_dep_array = (
            ("dependencies" in stripped and "=" in stripped and "[" in stripped
                and current_section in ("project", "tool.poetry", "dependency-groups"))
            or (current_section == "dependency-groups" and "=" in stripped and "[" in stripped)
        )
        if is_dep_array:
            in_deps = True
            # Handle inline: dependencies = ["pkg>=1.0", ...]
            inline = stripped.split("=", 1)[1].strip()
            if inline.startswith("[") and "]" in inline:
                for m in re.finditer(r'"([a-zA-Z][a-zA-Z0-9_.-]+)(?:\[.*?\])?\s*([><=!~]+\s*[\d.]+)?', inline):
                    name = m.group(1)
                    ver = (m.group(2) or "").strip().lstrip(">=<!=~")
                    deps.append((name, ver))
                in_deps = False
            continue

        # Poetry-style: name = "^1.0" or name = {version = "^1.0"}
        if current_section == "tool.poetry.dependencies":
            m = re.match(r'^([a-zA-Z][a-zA-Z0-9_.-]+)\s*=', stripped)
            if m:
                name = m.group(1)
                if name.lower() != "python":
                    ver_m = re.search(r'[\"\'][\^~>=<]*\s*([\d.]+)', stripped)
                    ver = ver_m.group(1) if ver_m else ""
                    deps.append((name, ver))
            continue

        if in_deps:
            if stripped == "]":
                in_deps = False
                continue
            # Parse "package-name>=1.0" or "package-name"
            m = re.search(r'"([a-zA-Z][a-zA-Z0-9_.-]+)(?:\[.*?\])?\s*([><=!~]+\s*[\d.]+)?', stripped)
            if m:
                name = m.group(1)
                ver = (m.group(2) or "").strip().lstrip(">=<!=~")
                deps.append((name, ver))

    return deps


def _parse_package_json(content):
    """Parse package.json dependencies."""
    deps = []
    try:
        data = json.loads(content)
        for section in ("dependencies", "devDependencies"):
            for name, version in (data.get(section) or {}).items():
                clean_version = re.sub(r'[\^~>=<]', '', version).strip()
                deps.append((name, clean_version))
    except json.JSONDecodeError:
        pass
    return deps


def _parse_setup_py(content):
    """Extract install_requires from setup.py."""
    deps = []
    match = re.search(r'install_requires\s*=\s*\[(.*?)\]', content, re.DOTALL)
    if match:
        for dep_match in re.finditer(r'["\']([a-zA-Z0-9_.-]+)', match.group(1)):
            deps.append((dep_match.group(1), ""))
    return deps


def parse_deps(content, filetype):
    """Parse dependency file into list of (name, version)."""
    if filetype == "requirements":
        return _parse_requirements(content)
    elif filetype == "pyproject":
        return _parse_pyproject(content)
    elif filetype == "package_json":
        return _parse_package_json(content)
    elif filetype == "setup_py":
        return _parse_setup_py(content)
    return []


# ── Trust score lookup ─────────────────────────────────────────

# Known LLM-related packages for cost estimation
LLM_PACKAGES = {
    "openai": ("gpt-4o", 500),
    "anthropic": ("claude-3.5-sonnet", 300),
    "cohere": ("command-r-plus", 200),
    "google-generativeai": ("gemini-pro", 150),
    "together": ("llama-3", 100),
    "replicate": ("various", 200),
    "groq": ("llama-3", 50),
    "mistralai": ("mistral-large", 200),
}


def _lookup_deps_batch(conn, dep_names):
    """Look up trust scores for a batch of dependency names. Returns dict of name -> {score, grade, url}."""
    results = {}
    if not dep_names:
        return results

    for dep_name in dep_names:
        # Try exact name match (fast — uses index)
        row = conn.execute(text(
            "SELECT name, trust_score_v2, trust_grade, source_url, license, category "
            "FROM entity_lookup WHERE name_lower = :exact "
            "AND is_active = true AND trust_score_v2 IS NOT NULL "
            "ORDER BY stars DESC NULLS LAST LIMIT 1"
        ), {"exact": dep_name.lower()}).fetchone()

        if not row:
            # Try with owner/name pattern (e.g., "langchain" -> "%/langchain")
            row = conn.execute(text(
                "SELECT name, trust_score_v2, trust_grade, source_url, license, category "
                "FROM entity_lookup WHERE name_lower LIKE :pattern "
                "AND is_active = true AND trust_score_v2 IS NOT NULL "
                "AND agent_type IN ('agent', 'mcp_server', 'tool') "
                "ORDER BY stars DESC NULLS LAST LIMIT 1"
            ), {"pattern": f"%/{dep_name.lower()}"}).fetchone()

        if row:
            m = dict(row._mapping)
            results[dep_name] = {
                "trust_score": m["trust_score_v2"],
                "trust_grade": m["trust_grade"],
                "source_url": m["source_url"],
                "license": m["license"],
                "category": m["category"],
                "matched_name": m["name"],
            }
        else:
            results[dep_name] = None

    return results


# ── Well-known packages (PyPI/npm standard library-tier) ──────
# These are universally trusted infrastructure packages. If they're
# not in our agent DB, they shouldn't penalize a project.
WELL_KNOWN_PACKAGES = {
    # Python standard ecosystem
    "requests", "flask", "django", "fastapi", "uvicorn", "gunicorn",
    "numpy", "pandas", "scipy", "matplotlib", "pillow", "pydantic",
    "sqlalchemy", "alembic", "celery", "redis", "pytest", "black",
    "mypy", "ruff", "isort", "flake8", "pre-commit", "tox",
    "setuptools", "wheel", "pip", "poetry", "click", "typer",
    "httpx", "aiohttp", "boto3", "botocore", "cryptography",
    "pyyaml", "toml", "tomli", "python-dotenv", "jinja2",
    "markupsafe", "werkzeug", "starlette", "anyio", "sniffio",
    "certifi", "charset-normalizer", "idna", "urllib3", "packaging",
    "six", "decorator", "attrs", "cattrs", "dataclasses-json",
    "marshmallow", "pyjwt", "python-jose", "passlib", "bcrypt",
    "pillow", "opencv-python", "scikit-learn", "torch", "torchvision",
    "tensorflow", "keras", "transformers", "tokenizers", "datasets",
    "accelerate", "diffusers", "safetensors", "sentencepiece",
    "protobuf", "grpcio", "grpcio-tools", "psycopg2", "psycopg2-binary", "pymongo",
    "motor", "elasticsearch", "docker", "paramiko", "fabric",
    "tqdm", "rich", "colorama", "loguru", "structlog",
    "arrow", "pendulum", "python-dateutil", "pytz",
    "orjson", "ujson", "msgpack", "lxml", "beautifulsoup4",
    "selenium", "playwright", "scrapy", "httpcore",
    "sphinx", "sphinx-rtd-theme", "sphinx-autodoc-typehints",
    "pygments", "docutils", "cffi",
    "coverage", "hypothesis", "factory-boy", "faker",
    "cookiecutter", "jinja2-time",
    "polars", "dask", "pyarrow", "h5py",
    "streamlit", "gradio", "chainlit",
    "wrapt", "deprecated", "typing-extensions",
    "packaging", "toml", "tomli", "tomli-w",
    "freezegun", "responses", "vcrpy",
    # Node.js standard ecosystem
    "typescript", "eslint", "prettier", "jest", "mocha", "vitest",
    "webpack", "vite", "esbuild", "rollup", "turbo", "nx",
    "react", "react-dom", "next", "vue", "nuxt", "svelte",
    "express", "koa", "fastify", "hono", "zod", "joi",
    "axios", "node-fetch", "got", "supertest", "nock",
    "lodash", "underscore", "dayjs", "moment", "date-fns",
    "uuid", "nanoid", "chalk", "commander", "yargs", "inquirer",
    "dotenv", "cross-env", "concurrently", "nodemon", "ts-node",
    "prisma", "drizzle-orm", "typeorm", "knex", "sequelize",
    "socket.io", "ws", "graphql", "apollo-server",
    "@types/node", "@types/jest", "@types/react",
    "@babel/core", "@babel/preset-env", "@babel/preset-typescript",
}

# Scoped npm prefixes that are generally trusted infrastructure
TRUSTED_SCOPES = {
    "@types/", "@babel/", "@eslint/", "@jest/", "@testing-library/",
    "@typescript-eslint/", "@swc/", "@vitejs/", "@rollup/",
    "@emotion/", "@mui/", "@radix-ui/", "@tanstack/", "@trpc/",
    "@prisma/", "@nestjs/", "@angular/", "@vue/", "@nuxt/",
    "@storybook/", "@playwright/", "@biomejs/",
    "types-",  # Python types- packages (types-requests, types-pyyaml, etc.)
    "pytest-", "pytest_",  # pytest plugins
    "sphinxcontrib-", "sphinxext-",  # sphinx extensions
}

# Package name fragments that indicate well-known ecosystem tools
WELL_KNOWN_FRAGMENTS = {
    "eslint", "prettier", "jest", "mocha", "webpack", "babel",
    "typescript", "react", "vue", "angular", "express", "next",
    "tailwind", "postcss", "autoprefixer", "sass", "less",
}


def _normalize_pkg(name):
    return name.lower().replace("-", "_").replace(".", "_").split("[")[0]


def _is_well_known(name):
    """Check if a package name is well-known infrastructure."""
    lower = name.lower()
    norm = _normalize_pkg(name)

    # Direct match in WELL_KNOWN_PACKAGES
    if norm in WELL_KNOWN_PACKAGES:
        return True

    # Trusted npm scopes
    for scope in TRUSTED_SCOPES:
        if lower.startswith(scope):
            return True

    # Contains well-known fragment (e.g., "jest-mock-extended" → "jest")
    parts = lower.replace("-", " ").replace("_", " ").replace("/", " ").split()
    for frag in WELL_KNOWN_FRAGMENTS:
        if frag in parts:
            return True

    return False


# ── Health grade calculation ───────────────────────────────────

def _calculate_health(deps_data, dep_names, repo_data=None):
    """Calculate project health grade from dependency data.

    Scoring philosophy:
    - Unknown packages are NEUTRAL (not penalizing) — absence of data ≠ risk
    - Only penalize when we have NEGATIVE evidence (low trust, CVEs, no license)
    - Weight by confidence: known deps full weight, unknown deps half weight
    - Bonus for positive signals (recent updates, security CI, pinned versions)
    """
    total = len(dep_names)
    if total == 0:
        return "?", 0, []

    weighted_scores = []  # (score, weight) tuples
    low_trust = 0
    no_license = 0
    critical_cves = 0
    high_cves = 0
    issues = []
    known_count = 0
    well_known_count = 0

    for name in dep_names:
        info = deps_data.get(name)
        normalized = _normalize_pkg(name)

        if info is not None:
            # ── Known dependency: use actual trust score (full weight)
            score = info["trust_score"] or 0
            known_count += 1

            # Floor: well-known packages shouldn't score below 55 even if
            # our trust_score_v2 is low (e.g., pytest at 47 is not risky)
            if _is_well_known(name) and score < 55:
                score = max(score, 55)

            weighted_scores.append((score, 1.0))

            if score < 40:
                low_trust += 1
                issues.append({
                    "package": name,
                    "issue": f"Low trust score ({score:.0f}/100)",
                    "severity": "critical" if score < 25 else "warning",
                    "trust_score": score,
                    "trust_grade": info["trust_grade"],
                })
            elif score < 55:
                issues.append({
                    "package": name,
                    "issue": f"Below-average trust score ({score:.0f}/100)",
                    "severity": "info",
                    "trust_score": score,
                    "trust_grade": info["trust_grade"],
                })

            if not info.get("license"):
                no_license += 1
                issues.append({
                    "package": name,
                    "issue": "No license detected",
                    "severity": "warning",
                })

        elif _is_well_known(name):
            # ── Well-known package not in our DB: neutral-positive (half weight)
            well_known_count += 1
            weighted_scores.append((70, 0.5))

        else:
            # ── Unknown package: neutral score, low weight
            # Not penalizing — we simply don't know
            weighted_scores.append((55, 0.3))

    # ── Weighted average ──
    total_weight = sum(w for _, w in weighted_scores)
    if total_weight > 0:
        avg_score = sum(s * w for s, w in weighted_scores) / total_weight
    else:
        avg_score = 55  # default neutral

    # ── Bonus for positive signals ──
    bonus = 0
    repo_data = repo_data or {}

    # Bonus: high ratio of known/well-known deps
    known_ratio = (known_count + well_known_count) / total if total > 0 else 0
    if known_ratio >= 0.8:
        bonus += 3  # well-characterized dependency tree

    # Bonus: has security CI (detected from repo_data)
    if repo_data.get("has_security_ci"):
        bonus += 5

    # Bonus: all deps have licenses (among known)
    if known_count > 0 and no_license == 0:
        bonus += 3

    # ── Effective score ──
    effective = avg_score + bonus

    # Penalties for actual problems (not data gaps)
    if critical_cves > 0:
        effective -= 20 * critical_cves
    if high_cves > 0:
        effective -= 10 * high_cves

    # ── Grading ──
    # Override: critical CVEs force low grades regardless of score
    if critical_cves > 1:
        grade = "F"
    elif critical_cves == 1:
        grade = "D"
    elif low_trust > total * 0.5 and known_count > 3:
        # More than half of KNOWN deps are low-trust — real signal
        grade = "D"
    else:
        # Score-based grading tuned for realistic distribution.
        # Most AI project dep trees score 54-64 weighted; thresholds
        # produce a bell curve centered on B/C.
        if effective >= 67:
            grade = "A"
        elif effective >= 61:
            grade = "B"
        elif effective >= 56:
            grade = "C"
        elif effective >= 52:
            grade = "D"
        else:
            grade = "F"

    # Sort issues by severity (critical first)
    severity_order = {"critical": 0, "high": 1, "warning": 2, "info": 3}
    issues.sort(key=lambda x: severity_order.get(x.get("severity", "info"), 3))

    return grade, round(avg_score, 1), issues[:20]


def _estimate_cost(dep_names):
    """Estimate monthly LLM cost if LLM packages detected."""
    for name in dep_names:
        key = name.lower().replace("-", "").replace("_", "")
        for pkg, (model, cost) in LLM_PACKAGES.items():
            if pkg.replace("-", "") in key:
                return cost, model
    return 0, None


# ── Main scanner ───────────────────────────────────────────────

def get_top_repos(conn, limit=1000):
    """Get top repos by stars from agents table."""
    rows = conn.execute(text("""
        SELECT source_id, name, stars, source_url
        FROM agents
        WHERE is_active = true
          AND source = 'github'
          AND agent_type IN ('agent', 'mcp_server', 'tool')
          AND stars > 0
          AND source_id IS NOT NULL
          AND source_id != ''
        ORDER BY stars DESC
        LIMIT :limit
    """), {"limit": limit}).fetchall()
    return [dict(r._mapping) for r in rows]


def scan_repo(conn, repo_slug, stars):
    """Scan a single repo. Returns scan result dict or None."""
    content, filetype = _fetch_dep_file(repo_slug)
    if not content:
        return None

    deps = parse_deps(content, filetype)
    if not deps:
        return None

    # Deduplicate deps (monorepo pyproject.toml may list same dep in multiple groups)
    seen = set()
    unique_deps = []
    for name, ver in deps:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            unique_deps.append((name, ver))
    deps = unique_deps

    dep_names = [d[0] for d in deps]
    deps_data = _lookup_deps_batch(conn, dep_names)

    grade, avg_score, issues = _calculate_health(deps_data, dep_names)
    monthly_cost, detected_model = _estimate_cost(dep_names)

    low_trust = sum(1 for n in dep_names if deps_data.get(n) and (deps_data[n]["trust_score"] or 0) < 50)
    no_license = sum(1 for n in dep_names if deps_data.get(n) and not deps_data[n].get("license"))

    dep_list = []
    for name, version in deps:
        info = deps_data.get(name)
        entry = {"name": name, "version": version}
        if info:
            entry.update({
                "trust_score": info["trust_score"],
                "trust_grade": info["trust_grade"],
                "license": info.get("license"),
                "matched": info["matched_name"],
            })
        dep_list.append(entry)

    return {
        "repo_full_name": repo_slug,
        "github_stars": stars,
        "total_deps": len(deps),
        "deps_with_cves": 0,  # Would need CVE database integration
        "critical_cves": 0,
        "high_cves": 0,
        "deps_without_license": no_license,
        "deps_low_trust": low_trust,
        "avg_trust_score": avg_score,
        "project_health_grade": grade,
        "estimated_monthly_cost": monthly_cost,
        "top_issues": issues,
        "dep_list": dep_list,
    }


def upsert_scan(conn, result):
    """Insert or update scan result in project_scans table."""
    conn.execute(text("""
        INSERT INTO project_scans
            (repo_full_name, github_stars, total_deps, deps_with_cves,
             critical_cves, high_cves, deps_without_license, deps_low_trust,
             avg_trust_score, project_health_grade, estimated_monthly_cost,
             top_issues, dep_list, scanned_at)
        VALUES
            (:repo_full_name, :github_stars, :total_deps, :deps_with_cves,
             :critical_cves, :high_cves, :deps_without_license, :deps_low_trust,
             :avg_trust_score, :project_health_grade, :estimated_monthly_cost,
             :top_issues, :dep_list, NOW())
        ON CONFLICT (repo_full_name) DO UPDATE SET
            github_stars = EXCLUDED.github_stars,
            total_deps = EXCLUDED.total_deps,
            deps_with_cves = EXCLUDED.deps_with_cves,
            critical_cves = EXCLUDED.critical_cves,
            high_cves = EXCLUDED.high_cves,
            deps_without_license = EXCLUDED.deps_without_license,
            deps_low_trust = EXCLUDED.deps_low_trust,
            avg_trust_score = EXCLUDED.avg_trust_score,
            project_health_grade = EXCLUDED.project_health_grade,
            estimated_monthly_cost = EXCLUDED.estimated_monthly_cost,
            top_issues = EXCLUDED.top_issues,
            dep_list = EXCLUDED.dep_list,
            scanned_at = NOW()
    """), {
        **result,
        "top_issues": json.dumps(result["top_issues"]),
        "dep_list": json.dumps(result["dep_list"]),
    })
    conn.commit()


def rescore_all():
    """Re-grade all existing scans using updated scoring formula (no GitHub API calls)."""
    from agentindex.db.models import get_engine
    engine = get_engine()

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT repo_full_name, github_stars, dep_list FROM project_scans"
        )).fetchall()
        log.info(f"Re-scoring {len(rows)} existing scans...")

        grades = {}
        for i, row in enumerate(rows):
            m = dict(row._mapping)
            dep_list = m["dep_list"]
            if isinstance(dep_list, str):
                dep_list = json.loads(dep_list)
            if not dep_list:
                continue

            dep_names = [d["name"] for d in dep_list]

            # Rebuild deps_data from stored dep_list (avoid DB lookups)
            deps_data = {}
            for d in dep_list:
                if d.get("trust_score") is not None:
                    deps_data[d["name"]] = {
                        "trust_score": d["trust_score"],
                        "trust_grade": d.get("trust_grade"),
                        "license": d.get("license"),
                        "category": d.get("category"),
                    }
                else:
                    deps_data[d["name"]] = None

            grade, avg_score, issues = _calculate_health(deps_data, dep_names)
            low_trust = sum(1 for n in dep_names if deps_data.get(n) and (deps_data[n]["trust_score"] or 0) < 50)
            no_license = sum(1 for n in dep_names if deps_data.get(n) and not deps_data[n].get("license"))

            conn.execute(text("""
                UPDATE project_scans SET
                    avg_trust_score = :avg,
                    project_health_grade = :grade,
                    deps_low_trust = :low,
                    deps_without_license = :nolic,
                    top_issues = :issues
                WHERE repo_full_name = :repo
            """), {
                "avg": avg_score,
                "grade": grade,
                "low": low_trust,
                "nolic": no_license,
                "issues": json.dumps(issues),
                "repo": m["repo_full_name"],
            })

            grades[grade] = grades.get(grade, 0) + 1

            if (i + 1) % 100 == 0:
                conn.commit()
                log.info(f"  Re-scored {i+1}/{len(rows)} — grades so far: {grades}")

        conn.commit()

    print(f"\n{'='*60}")
    print(f"RE-SCORE COMPLETE — {len(rows)} repos")
    print(f"{'='*60}")
    total = sum(grades.values())
    for g in sorted(grades.keys()):
        count = grades[g]
        pct = count / total * 100 if total else 0
        bar = "█" * int(pct / 2)
        print(f"  {g}: {count:4d} ({pct:5.1f}%) {bar}")
    print(f"{'='*60}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Mass project scanner")
    parser.add_argument("--top", type=int, default=1000, help="Number of top repos to scan")
    parser.add_argument("--batch", type=int, default=100, help="Batch size for progress logging")
    parser.add_argument("--rescore", action="store_true", help="Re-grade existing scans without GitHub API calls")
    args = parser.parse_args()

    if args.rescore:
        rescore_all()
        return

    global GITHUB_TOKEN
    if not GITHUB_TOKEN:
        # Try loading from .env
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("GITHUB_TOKEN="):
                    GITHUB_TOKEN = line.split("=", 1)[1].strip().strip('"')
                    break

    if not GITHUB_TOKEN:
        log.error("GITHUB_TOKEN required. Set env var or add to .env")
        return

    from agentindex.db.models import get_engine
    engine = get_engine()

    with engine.connect() as conn:
        repos = get_top_repos(conn, limit=args.top)
        log.info(f"Fetched {len(repos)} repos to scan")

        # Check which are already scanned (skip recent)
        already = set()
        rows = conn.execute(text(
            "SELECT repo_full_name FROM project_scans WHERE scanned_at > NOW() - INTERVAL '7 days'"
        )).fetchall()
        already = {r[0] for r in rows}
        log.info(f"Skipping {len(already)} recently scanned repos")

        stats = {"scanned": 0, "skipped": 0, "no_deps": 0, "errors": 0, "grades": {}}
        total = len(repos)

        for i, repo in enumerate(repos):
            slug = repo.get("source_id") or repo.get("name")
            if not slug or "/" not in slug:
                # Try to extract from source_url
                url = repo.get("source_url", "")
                parts = url.rstrip("/").split("/")
                if len(parts) >= 2:
                    slug = f"{parts[-2]}/{parts[-1]}"
                else:
                    stats["skipped"] += 1
                    continue

            if slug in already:
                stats["skipped"] += 1
                continue

            stars = repo.get("stars") or 0

            try:
                result = scan_repo(conn, slug, stars)
                if result:
                    upsert_scan(conn, result)
                    grade = result["project_health_grade"]
                    stats["grades"][grade] = stats["grades"].get(grade, 0) + 1
                    stats["scanned"] += 1

                    if result["deps_low_trust"] > 0 or result["deps_without_license"] > 0:
                        log.info(
                            f"  [{i+1}/{total}] {slug} ({stars:,}★) → {grade} "
                            f"({result['total_deps']} deps, {result['deps_low_trust']} low trust, "
                            f"avg {result['avg_trust_score']:.0f})"
                        )
                else:
                    stats["no_deps"] += 1

            except Exception as e:
                log.error(f"  [{i+1}/{total}] Error scanning {slug}: {e}")
                stats["errors"] += 1

            # Progress logging
            if (i + 1) % args.batch == 0:
                log.info(
                    f"Progress: {i+1}/{total} | "
                    f"scanned={stats['scanned']} no_deps={stats['no_deps']} "
                    f"skipped={stats['skipped']} errors={stats['errors']} | "
                    f"grades={stats['grades']}"
                )

            # Rate limiting
            time.sleep(RATE_DELAY)

    # Final report
    print(f"\n{'='*60}")
    print(f"MASS SCAN COMPLETE")
    print(f"{'='*60}")
    print(f"Total repos: {total}")
    print(f"Scanned: {stats['scanned']}")
    print(f"No dep file: {stats['no_deps']}")
    print(f"Skipped (recent): {stats['skipped']}")
    print(f"Errors: {stats['errors']}")
    print(f"\nGrade Distribution:")
    for grade in sorted(stats["grades"].keys()):
        count = stats["grades"][grade]
        bar = "█" * (count // 2)
        print(f"  {grade}: {count:4d} {bar}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
