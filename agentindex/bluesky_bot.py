"""
Bluesky Bot — Post Nerq Scout summaries to Bluesky (AT Protocol).

Auth: App password from ~/.config/nerq/bluesky_handle and ~/.config/nerq/bluesky_app_password
API: https://bsky.social/xrpc/

Usage:
    from agentindex.bluesky_bot import post_scout_summary
    post_scout_summary(findings)
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger("nerq.bluesky")

HANDLE_PATH = Path.home() / ".config" / "nerq" / "bluesky_handle"
PASSWORD_PATH = Path.home() / ".config" / "nerq" / "bluesky_app_password"
BSKY_API = "https://bsky.social/xrpc"
MAX_POST_LEN = 300

# ── Session cache ────────────────────────────────────────────

_session: dict | None = None


def _load_credentials() -> tuple[str, str] | None:
    """Load handle and app password from disk."""
    if not HANDLE_PATH.exists() or not PASSWORD_PATH.exists():
        logger.info("No Bluesky credentials — posting disabled")
        return None
    handle = HANDLE_PATH.read_text().strip()
    password = PASSWORD_PATH.read_text().strip()
    if not handle or not password:
        logger.info("No Bluesky credentials — posting disabled")
        return None
    return handle, password


def _create_session() -> dict | None:
    """Authenticate and return session (did, accessJwt, refreshJwt)."""
    global _session
    creds = _load_credentials()
    if not creds:
        return None

    handle, password = creds
    try:
        resp = requests.post(
            f"{BSKY_API}/com.atproto.server.createSession",
            json={"identifier": handle, "password": password},
            timeout=10,
        )
        resp.raise_for_status()
        _session = resp.json()
        logger.info(f"Bluesky session created for {handle}")
        return _session
    except Exception as e:
        logger.warning(f"Bluesky auth failed: {e}")
        return None


def _get_session() -> dict | None:
    """Get or create session."""
    global _session
    if _session and _session.get("accessJwt"):
        return _session
    return _create_session()


# ── Link facets ──────────────────────────────────────────────

def _extract_link_facets(text: str) -> list[dict]:
    """Find URLs in text and create Bluesky link facets."""
    facets = []
    for m in re.finditer(r"https?://[^\s\)]+", text):
        url = m.group(0)
        # Byte offsets (AT Protocol uses UTF-8 byte positions)
        start = len(text[:m.start()].encode("utf-8"))
        end = len(text[:m.end()].encode("utf-8"))
        facets.append({
            "index": {"byteStart": start, "byteEnd": end},
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}],
        })
    return facets


# ── Post function ────────────────────────────────────────────

def post_to_bluesky(text: str) -> dict | None:
    """Post text to Bluesky. Returns the created record or None.

    Max 300 chars. URLs in text become clickable via facets.
    """
    session = _get_session()
    if not session:
        return None

    if len(text) > MAX_POST_LEN:
        text = text[:MAX_POST_LEN - 1] + "\u2026"

    facets = _extract_link_facets(text)

    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    if facets:
        record["facets"] = facets

    try:
        resp = requests.post(
            f"{BSKY_API}/com.atproto.repo.createRecord",
            json={
                "repo": session["did"],
                "collection": "app.bsky.feed.post",
                "record": record,
            },
            headers={"Authorization": f"Bearer {session['accessJwt']}"},
            timeout=10,
        )
        if resp.status_code == 401:
            # Token expired — retry with fresh session
            logger.info("Bluesky token expired, re-authenticating")
            global _session
            _session = None
            session = _get_session()
            if not session:
                return None
            resp = requests.post(
                f"{BSKY_API}/com.atproto.repo.createRecord",
                json={
                    "repo": session["did"],
                    "collection": "app.bsky.feed.post",
                    "record": record,
                },
                headers={"Authorization": f"Bearer {session['accessJwt']}"},
                timeout=10,
            )

        resp.raise_for_status()
        result = resp.json()
        logger.info(f"Bluesky post created: {result.get('uri', '')}")
        return result

    except Exception as e:
        logger.warning(f"Bluesky post failed: {e}")
        return None


# ── Scout integration ────────────────────────────────────────

def post_scout_summary(findings: list[dict]) -> dict | None:
    """Post a summary of Scout findings to Bluesky.

    Args:
        findings: List of dicts with name, trust_score, grade, category keys.

    Returns:
        Bluesky record dict or None if posting disabled/failed.
    """
    if not findings:
        return None

    # Find top agent by trust score
    top = max(findings, key=lambda f: f.get("trust_score") or 0)
    top_name = top.get("name", "?")
    top_score = top.get("trust_score")
    top_grade = top.get("grade", "?")

    score_str = f"{top_score:.0f}" if top_score else "?"

    text = (
        f"Nerq Scout: {top_name} scored {score_str} ({top_grade}). "
        f"{len(findings)} agents evaluated today. "
        f"Report: https://nerq.ai/safe/{top_name}"
    )

    if len(text) > MAX_POST_LEN:
        text = (
            f"Scout: {top_name} scored {score_str} ({top_grade}). "
            f"{len(findings)} agents evaluated. "
            f"https://nerq.ai/safe/{top_name}"
        )

    result = post_to_bluesky(text)
    if result:
        print(f"Bluesky: Posted — {result.get('uri', '')}")
    return result


def post_benchmark_summary() -> dict | None:
    """Post benchmark highlight to Bluesky."""
    text = (
        "AI agents with trust-checking: 0% failure rate vs 36% without. "
        "N=100 iterations, p<0.00000001. "
        "https://nerq.ai/report/benchmark"
    )
    result = post_to_bluesky(text)
    if result:
        print(f"Bluesky: Benchmark posted — {result.get('uri', '')}")
    return result


# ── Dry run / test ───────────────────────────────────────────

def dry_run():
    """Test the bot without posting. Validates credentials and facet extraction."""
    print("Bluesky Bot — Dry Run")
    print("=" * 40)

    # Check credentials
    creds = _load_credentials()
    if creds:
        print(f"Handle: {creds[0]}")
        print("Password: ***")
        session = _create_session()
        if session:
            print(f"Auth: OK (did={session['did']})")
        else:
            print("Auth: FAILED")
    else:
        print("Credentials: NOT FOUND (posting disabled)")
        print(f"  Expected: {HANDLE_PATH}")
        print(f"           {PASSWORD_PATH}")

    # Test facet extraction
    test_text = "Check out https://nerq.ai/report/benchmark for results."
    facets = _extract_link_facets(test_text)
    print(f"\nFacet test: {len(facets)} link(s) found")
    for f in facets:
        print(f"  [{f['index']['byteStart']}:{f['index']['byteEnd']}] {f['features'][0]['uri']}")

    # Test scout summary formatting
    test_findings = [
        {"name": "SWE-agent", "trust_score": 92.5, "grade": "A+", "category": "Coding Agent"},
        {"name": "langchain", "trust_score": 88.0, "grade": "A", "category": "Framework"},
    ]
    text = (
        f"Nerq Scout: {test_findings[0]['name']} scored "
        f"{test_findings[0]['trust_score']:.0f} ({test_findings[0]['grade']}). "
        f"{len(test_findings)} agents evaluated today. "
        f"Full report: https://nerq.ai/blog"
    )
    print(f"\nSample post ({len(text)} chars):")
    print(f"  {text}")
    print(f"  Under 300 limit: {'YES' if len(text) <= 300 else 'NO'}")

    print("\nDry run complete.")


if __name__ == "__main__":
    dry_run()
