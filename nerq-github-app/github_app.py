"""
Nerq Trust Bot — GitHub App webhook handler.

Listens for PR events, scans dependency changes, and posts trust reports as PR comments.
Mount on the existing FastAPI app via:
    from nerq_github_app.github_app import router
    app.include_router(router)
"""

import hashlib
import hmac
import json
import logging
import os
import re
from typing import Optional

import httpx
from fastapi import APIRouter, Request, Response

logger = logging.getLogger("nerq-github-app")

router = APIRouter(tags=["github-app"])

# Load from .env file (LaunchAgent doesn't source shell env)
def _load_env():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(env_path):
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    vals = {}
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip().strip("'\"")
    return vals

_env = _load_env()
GITHUB_APP_SECRET = _env.get("GITHUB_APP_WEBHOOK_SECRET", "") or os.environ.get("GITHUB_APP_WEBHOOK_SECRET", "")
GITHUB_APP_ID = _env.get("GITHUB_APP_ID", "") or os.environ.get("GITHUB_APP_ID", "")
_key_path = _env.get("GITHUB_APP_PRIVATE_KEY_PATH", "") or os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH", "")
if _key_path and os.path.exists(_key_path):
    with open(_key_path) as _f:
        GITHUB_APP_PRIVATE_KEY = _f.read()
else:
    GITHUB_APP_PRIVATE_KEY = os.environ.get("GITHUB_APP_PRIVATE_KEY", "")
NERQ_API_BASE = os.environ.get("NERQ_API_URL", "https://nerq.ai")
USER_AGENT = "NerqGitHubApp/1.0.0"

DEP_FILES = {
    "requirements.txt", "requirements-dev.txt", "requirements-test.txt",
    "package.json", "pyproject.toml", "Pipfile", "setup.py", "setup.cfg",
}


def verify_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook signature."""
    if not GITHUB_APP_SECRET:
        return True  # Skip verification in dev
    expected = "sha256=" + hmac.new(
        GITHUB_APP_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_requirements(content: str) -> list[str]:
    """Parse requirements.txt format."""
    deps = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        match = re.match(r"^([a-zA-Z0-9_.-]+)", line)
        if match:
            deps.append(match.group(1))
    return deps


def parse_package_json(content: str) -> list[str]:
    """Parse package.json dependencies."""
    try:
        pkg = json.loads(content)
        deps = []
        for section in ["dependencies", "devDependencies"]:
            if section in pkg:
                deps.extend(pkg[section].keys())
        return deps
    except json.JSONDecodeError:
        return []


def parse_pyproject_toml(content: str) -> list[str]:
    """Parse pyproject.toml dependencies."""
    deps = []
    dep_section = re.search(r"dependencies\s*=\s*\[([\s\S]*?)\]", content)
    if dep_section:
        for match in re.finditer(r'"([a-zA-Z0-9_.-]+)', dep_section.group(1)):
            deps.append(match.group(1))
    return deps


def parse_dep_file(filename: str, content: str) -> list[str]:
    """Parse dependencies from a file based on its name."""
    basename = os.path.basename(filename)
    if "requirements" in basename and basename.endswith(".txt"):
        return parse_requirements(content)
    elif basename == "package.json":
        return parse_package_json(content)
    elif basename == "pyproject.toml":
        return parse_pyproject_toml(content)
    return []


def grade_emoji(grade: str) -> str:
    if grade.startswith("A"):
        return ":white_check_mark:"
    if grade.startswith("B"):
        return ":large_blue_circle:"
    if grade.startswith("C"):
        return ":warning:"
    if grade.startswith("D"):
        return ":orange_circle:"
    return ":red_circle:"


async def get_installation_token(installation_id: int) -> Optional[str]:
    """Get an installation access token for the GitHub App."""
    if not GITHUB_APP_PRIVATE_KEY or not GITHUB_APP_ID:
        logger.warning("GitHub App credentials not configured")
        return None

    try:
        import jwt
        import time

        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + (10 * 60),
            "iss": GITHUB_APP_ID,
        }
        token = jwt.encode(payload, GITHUB_APP_PRIVATE_KEY, algorithm="RS256")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": USER_AGENT,
                },
            )
            if resp.status_code == 201:
                return resp.json()["token"]
    except ImportError:
        logger.warning("PyJWT not installed — cannot authenticate as GitHub App")
    except Exception as e:
        logger.error(f"Failed to get installation token: {e}")
    return None


async def scan_dependencies(deps: list[str]) -> list[dict]:
    """Check trust scores for a list of dependencies."""
    results = []
    async with httpx.AsyncClient(timeout=15) as client:
        for dep in deps[:30]:  # Limit to 30 deps per PR
            try:
                resp = await client.get(
                    f"{NERQ_API_BASE}/v1/preflight",
                    params={"target": dep},
                    headers={"User-Agent": USER_AGENT},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results.append({
                        "name": dep,
                        "score": data.get("trust_score") or data.get("target_trust"),
                        "grade": data.get("target_grade") or data.get("grade", "—"),
                        "cves": data.get("cves", {}),
                        "report_url": data.get("report_url", f"https://nerq.ai/is-{dep}-safe"),
                    })
                else:
                    results.append({"name": dep, "score": None, "grade": "—", "cves": {}, "report_url": f"https://nerq.ai/is-{dep}-safe"})
            except Exception:
                results.append({"name": dep, "score": None, "grade": "—", "cves": {}, "report_url": f"https://nerq.ai/is-{dep}-safe"})
    return results


def build_comment(results: list[dict], dep_file: str) -> str:
    """Build a PR comment with trust report."""
    scored = [r for r in results if r["score"] is not None]
    avg_score = round(sum(r["score"] for r in scored) / len(scored)) if scored else 0

    critical_count = sum(r.get("cves", {}).get("critical", 0) for r in results)
    high_count = sum(r.get("cves", {}).get("high", 0) for r in results)

    # Header
    if critical_count > 0:
        header = f":rotating_light: **Nerq Trust Gate** — {critical_count} critical CVE(s) found"
    elif high_count > 0:
        header = f":warning: **Nerq Trust Gate** — {high_count} high-severity CVE(s) found"
    elif avg_score >= 70:
        header = f":shield: **Nerq Trust Gate** — All clear (avg {avg_score}/100)"
    else:
        header = f":shield: **Nerq Trust Gate** — {len(results)} dependencies scanned (avg {avg_score}/100)"

    # Table
    rows = []
    for r in sorted(results, key=lambda x: x["score"] or 0):
        emoji = grade_emoji(r["grade"])
        score_str = str(r["score"]) if r["score"] is not None else "N/A"
        cve_str = ""
        if r.get("cves"):
            crit = r["cves"].get("critical", 0)
            high = r["cves"].get("high", 0)
            if crit:
                cve_str = f"{crit} CRITICAL"
            elif high:
                cve_str = f"{high} HIGH"
        rows.append(f"| {r['name']} | {score_str} | {emoji} {r['grade']} | {cve_str or '0'} | [Report]({r['report_url']}) |")

    table = "| Package | Trust | Grade | CVEs | Report |\n|---|---|---|---|---|\n" + "\n".join(rows)

    comment = f"""{header}

<details>
<summary>Dependency trust report for <code>{dep_file}</code></summary>

{table}

</details>

<sub>Powered by [Nerq](https://nerq.ai) — Is it safe?</sub>
"""
    return comment


@router.post("/webhooks/github")
async def github_webhook(request: Request):
    """Handle GitHub App webhook events."""
    payload = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")

    if not verify_signature(payload, signature):
        return Response(status_code=401, content="Invalid signature")

    event = request.headers.get("x-github-event", "")
    data = json.loads(payload)

    if event == "ping":
        return {"status": "pong"}

    if event == "pull_request" and data.get("action") in ("opened", "synchronize"):
        return await handle_pull_request(data)

    return {"status": "ignored", "event": event}


async def handle_pull_request(data: dict):
    """Handle pull_request events — scan dependency changes."""
    pr = data["pull_request"]
    repo = data["repository"]
    installation_id = data.get("installation", {}).get("id")

    owner = repo["owner"]["login"]
    repo_name = repo["name"]
    pr_number = pr["number"]

    logger.info(f"PR #{pr_number} on {owner}/{repo_name} — checking for dependency changes")

    # Get PR files
    token = await get_installation_token(installation_id) if installation_id else None
    if not token:
        logger.info("No token available — skipping")
        return {"status": "no_token"}

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        # Get changed files
        files_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo_name}/pulls/{pr_number}/files",
            headers=headers,
        )
        if files_resp.status_code != 200:
            return {"status": "error", "message": "Could not fetch PR files"}

        changed_files = files_resp.json()
        dep_files_changed = [
            f for f in changed_files
            if os.path.basename(f["filename"]) in DEP_FILES
        ]

        if not dep_files_changed:
            return {"status": "no_dep_changes"}

        # Process each changed dependency file
        all_results = []
        dep_file_names = []

        for file_info in dep_files_changed:
            filename = file_info["filename"]
            dep_file_names.append(filename)

            # Fetch file content from the PR branch
            content_resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo_name}/contents/{filename}?ref={pr['head']['ref']}",
                headers=headers,
            )
            if content_resp.status_code != 200:
                continue

            import base64
            content_data = content_resp.json()
            content = base64.b64decode(content_data.get("content", "")).decode("utf-8", errors="ignore")

            deps = parse_dep_file(filename, content)
            if deps:
                results = await scan_dependencies(deps)
                all_results.extend(results)

        if not all_results:
            return {"status": "no_deps_found"}

        # Deduplicate
        seen = set()
        unique_results = []
        for r in all_results:
            if r["name"] not in seen:
                seen.add(r["name"])
                unique_results.append(r)

        # Build and post comment
        comment_body = build_comment(unique_results, ", ".join(dep_file_names))

        await client.post(
            f"https://api.github.com/repos/{owner}/{repo_name}/issues/{pr_number}/comments",
            headers=headers,
            json={"body": comment_body},
        )

        # Set commit status if critical CVEs
        critical_count = sum(r.get("cves", {}).get("critical", 0) for r in unique_results)
        state = "failure" if critical_count > 0 else "success"
        scored = [r for r in unique_results if r["score"] is not None]
        avg = round(sum(r["score"] for r in scored) / len(scored)) if scored else 0

        await client.post(
            f"https://api.github.com/repos/{owner}/{repo_name}/statuses/{pr['head']['sha']}",
            headers=headers,
            json={
                "state": state,
                "target_url": "https://nerq.ai/github-app",
                "description": f"Trust: {avg}/100 · {len(unique_results)} deps · {critical_count} critical CVEs",
                "context": "nerq/trust-gate",
            },
        )

        logger.info(f"Posted trust report on PR #{pr_number}: {len(unique_results)} deps, avg {avg}")
        return {"status": "reported", "deps": len(unique_results), "avg_score": avg}
