"""Linter test: detect hardcoded internal links in Python source files.

PURPOSE:
    Prevent regression of the internal-link bug that caused 32% prefix
    coverage on localized pages. Any new hardcoded href="/safe/..."
    or href="/best/..." in a Python file outside agentindex/i18n/ is
    a violation and must be rewritten to use localize_url().

HOW IT WORKS:
    The test scans every .py file in agentindex/agentindex/ for patterns
    like href="/safe/, href="/best/, href="/compare/, etc. Any match
    in a file that is NOT in the allowlist is a test failure.

THE ALLOWLIST:
    Files in the allowlist are "known debt" — they currently contain
    hardcoded links and we know it. The allowlist exists so that this
    test passes today (green CI from the start), while still catching
    NEW hardcoded links in files that are supposed to be clean.

    AS FILES ARE MIGRATED TO localize_url(), REMOVE THEM FROM THE
    ALLOWLIST. The end state (Dag 35) is an empty allowlist, at which
    point the test guarantees 100% of internal links go through
    localize_url().

HOW TO USE THIS TEST:
    - Run it locally: python -m pytest tests/test_no_hardcoded_links.py
    - The test reports violations per file with line numbers.
    - If you ADD a hardcoded link to an allowlisted file, the test
      still passes (that file is allowlisted).
    - If you ADD a hardcoded link to a NON-allowlisted file, the test
      fails and tells you to use localize_url() instead.
    - If you REMOVE hardcoded links from an allowlisted file, reduce
      the file's max_count in the allowlist accordingly. When max_count
      reaches 0, remove the file from the allowlist entirely.

MAX_COUNT LOGIC:
    Each allowlisted file has a max_count — the maximum number of
    violations we tolerate in that file. This is a ratchet: it can
    only decrease over time. If the actual count rises above max_count,
    the test fails (someone added more hardcoded links instead of
    migrating them). If the actual count falls below max_count, the
    test passes but prints a warning reminding you to lower the
    max_count.
"""
import re
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

# Repo root relative to this test file.
REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTINDEX_DIR = REPO_ROOT / "agentindex"

# Patterns that indicate hardcoded internal content links.
# These match href="/safe/X", href='/best/X', f'href="/compare/X"', etc.
# They do NOT match /v1/, /static/, /api/ etc — those are global paths.
HARDCODED_LINK_PATTERNS = [
    re.compile(r'href=["\']/safe/'),
    re.compile(r'href=["\']/best/'),
    re.compile(r'href=["\']/compare/'),
    re.compile(r'href=["\']/alternatives/'),
    re.compile(r'href=["\']/is-[a-z]'),
    re.compile(r'href=["\']/does-[a-z]'),
    re.compile(r'href=["\']/was-[a-z]'),
    re.compile(r'href=["\']/who-owns/'),
    re.compile(r'href=["\']/review/'),
    re.compile(r'href=["\']/pros-cons/'),
]

# Files that are EXEMPT from the linter — they define the URL helpers
# themselves, or they are tests that legitimately use hardcoded URLs as
# test inputs.
EXEMPT_PATHS = {
    "agentindex/i18n/urls.py",       # The definition of localize_url itself
    "agentindex/i18n/languages.py",  # The language definitions
    "agentindex/i18n/__init__.py",   # Public API
    "agentindex/i18n/html_rewrite.py",  # Helper that calls localize_url internally
    "tests/test_i18n_urls.py",       # Tests need hardcoded URLs as inputs
    "tests/test_i18n_languages.py",
    "tests/test_i18n_html_rewrite.py",  # Tests need hardcoded URLs as inputs
    "tests/test_no_hardcoded_links.py",  # This file itself
    "tests/conftest.py",
}

# Paths under agentindex/ that we skip entirely (not Python files, or
# not relevant — backups, third-party, vendored code).
SKIP_DIR_PATTERNS = [
    "backups/",
    "venv/",
    ".git/",
    "__pycache__/",
    "crypto/templates/",  # Jinja2 HTML templates, not Python
    "track-record/",      # Sub-repo
    "nerq-trust-protocol/",  # Sub-repo
    "integrations/",      # Vendored code
    "npm-langchain-agentindex/",  # Sub-repo
    "reddit_deployment/",
]

# Known debt: files that currently contain hardcoded links.
# Format: { relative_path: max_count }
# These max_counts should DECREASE over time as we migrate files.
# When max_count reaches 0, remove the entry entirely.
#
# Initial counts will be filled in automatically on the first run —
# the test will print the current counts and you paste them here.
ALLOWLIST_MAX_COUNTS: Dict[str, int] = {
    # Baseline from Dag 32 (2026-04-07): 30 files, 193 hardcoded internal links.
    # MÅL: this dict should be empty at end of Dag 33 (migration day).
    #
    # When you migrate a file to localize_url(), reduce its count. When the
    # count reaches 0, delete the entry. The test will fail if any file
    # exceeds its listed count (meaning: regression detected).
    "agentindex/agent_safety_pages.py": 52,
    "agentindex/ab_test.py": 32,
    "agentindex/guide_pages.py": 27,
    "agentindex/demand_pages.py": 16,
    "agentindex/seo_programmatic.py": 12,
    "agentindex/crypto/crypto_seo_pages.py": 8,
    "agentindex/pattern_routes.py": 6,
    "agentindex/localized_routes.py": 5,
    "agentindex/badge_api.py": 4,
    "agentindex/intelligence_api.py": 3,
    "agentindex/weekly_safety_digest.py": 3,
    "agentindex/agent_compare_pages.py": 2,
    "agentindex/compatibility_api.py": 2,
    "agentindex/reach_dashboard.py": 2,
    "agentindex/review_pages.py": 2,
    "agentindex/seo_answers_packages.py": 2,
    "agentindex/seo_asset_pages.py": 2,
    "agentindex/api/discovery.py": 1,
    "agentindex/compliance_pages.py": 1,
    "agentindex/crypto/zarq_token_pages.py": 1,
    "agentindex/dev_onboarding.py": 1,
    "agentindex/economics_api.py": 1,
    "agentindex/entity_pages.py": 1,
    "agentindex/federation_api.py": 1,
    "agentindex/intelligence/predictive/routes.py": 1,
    "agentindex/mcp_trust_pages.py": 1,
    "agentindex/seo_dynamic.py": 1,
    "agentindex/seo_improve.py": 1,
    "agentindex/seo_pages.py": 1,
    "agentindex/trust_score_page.py": 1,
}


def _relative_path(abs_path: Path) -> str:
    """Return the repo-relative path as a string with forward slashes."""
    return str(abs_path.relative_to(REPO_ROOT)).replace("\\", "/")


def _should_skip(rel_path: str) -> bool:
    """Return True if the file should be skipped entirely."""
    for pattern in SKIP_DIR_PATTERNS:
        if pattern in rel_path:
            return True
    return False


def _scan_file(abs_path: Path) -> List[Tuple[int, str]]:
    """Scan a single file and return list of (line_number, line_content)
    tuples for lines containing hardcoded internal links."""
    violations = []
    try:
        with abs_path.open("r", encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f, start=1):
                for pattern in HARDCODED_LINK_PATTERNS:
                    if pattern.search(line):
                        violations.append((lineno, line.rstrip()))
                        break  # One violation per line is enough
    except (OSError, UnicodeDecodeError):
        pass
    return violations


def _scan_all_python_files() -> Dict[str, int]:
    """Scan all Python files under agentindex/ and return a dict of
    {relative_path: violation_count}."""
    violations_by_file: Dict[str, int] = {}
    for abs_path in AGENTINDEX_DIR.rglob("*.py"):
        rel_path = _relative_path(abs_path)
        if _should_skip(rel_path):
            continue
        if rel_path in EXEMPT_PATHS:
            continue
        violations = _scan_file(abs_path)
        if violations:
            violations_by_file[rel_path] = len(violations)
    return violations_by_file


def test_no_new_hardcoded_internal_links():
    """Fail if any file has MORE hardcoded internal links than allowlisted.

    This is the main gate: it ensures no NEW hardcoded links are added.
    Existing hardcoded links in allowlisted files are tolerated until
    they are migrated to localize_url().
    """
    current_violations = _scan_all_python_files()

    errors: List[str] = []
    for rel_path, count in sorted(current_violations.items()):
        max_allowed = ALLOWLIST_MAX_COUNTS.get(rel_path, 0)
        if count > max_allowed:
            if max_allowed == 0:
                errors.append(
                    f"  {rel_path}: {count} hardcoded internal link(s) found. "
                    f"This file is NOT allowlisted. "
                    f"Use agentindex.i18n.urls.localize_url() instead."
                )
            else:
                errors.append(
                    f"  {rel_path}: {count} hardcoded links (allowlist max: {max_allowed}). "
                    f"Someone added {count - max_allowed} new hardcoded link(s). "
                    f"Use agentindex.i18n.urls.localize_url() instead."
                )

    if errors:
        message = (
            "\n\nHardcoded internal link violations found:\n"
            + "\n".join(errors)
            + "\n\nFix: replace hardcoded href='/safe/...' with "
            "href=localize_url('/safe/...', lang) using the helper from "
            "agentindex.i18n.urls.\n"
        )
        pytest.fail(message)


def test_allowlist_counts_are_not_stale():
    """Warn if a file has FEWER violations than its allowlist max_count.

    This is the ratchet: allowlist counts should only decrease over time.
    If a file has been cleaned up, its max_count should be lowered to
    the new actual count (or the entry removed if count is 0).

    This test only WARNS — it does not fail — because someone might be
    in the middle of migrating a file and wants their commit to pass
    even before they've updated the allowlist.
    """
    current_violations = _scan_all_python_files()
    stale_entries = []
    for rel_path, max_allowed in ALLOWLIST_MAX_COUNTS.items():
        actual = current_violations.get(rel_path, 0)
        if actual < max_allowed:
            stale_entries.append(
                f"  {rel_path}: allowlist says {max_allowed}, actual is {actual}. "
                f"Lower to {actual}."
            )

    if stale_entries:
        print(
            "\n\n⚠️  Stale allowlist entries (can be tightened):\n"
            + "\n".join(stale_entries)
            + "\n\nUpdate ALLOWLIST_MAX_COUNTS in tests/test_no_hardcoded_links.py\n"
        )


def test_allowlist_has_no_exempt_files():
    """An EXEMPT file should never appear in the allowlist — that would
    be a contradiction (exempt means 'never scanned', allowlisted means
    'scanned but tolerated')."""
    conflicts = set(ALLOWLIST_MAX_COUNTS.keys()) & EXEMPT_PATHS
    assert not conflicts, (
        f"Files in both ALLOWLIST_MAX_COUNTS and EXEMPT_PATHS: {conflicts}. "
        f"A file should be in at most one of these."
    )


def test_exempt_paths_exist():
    """Every path in EXEMPT_PATHS should actually exist in the repo."""
    for rel_path in EXEMPT_PATHS:
        abs_path = REPO_ROOT / rel_path
        assert abs_path.exists(), (
            f"EXEMPT_PATHS contains {rel_path!r} but that file does not exist. "
            f"Remove it from EXEMPT_PATHS or check the path."
        )
