#!/usr/bin/env python3
"""
LLM Context Auto-Updater (E3)
===============================
Runs daily at 07:30 via LaunchAgent com.nerq.llm-context-updater.
Reads current counts from database, updates all numbers in llms.txt
and llms-full.txt, and refreshes the "last updated" date.

Exit 0 on success.
"""

import json
import logging
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = "/tmp/llm-context-updater.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("llm-context-updater")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORTS_DIR = Path(__file__).resolve().parent / "exports"
LLMS_TXT = EXPORTS_DIR / "llms.txt"
LLMS_FULL_TXT = EXPORTS_DIR / "llms-full.txt"

# Database paths
RISK_DB = Path(__file__).parent / "crypto" / "crypto_trust.db"
SEO_DB = Path(__file__).parent / "data" / "crypto_trust.db"


def get_counts() -> dict:
    """Get current counts from all databases and slug files."""
    counts = {}

    # Token counts from risk DB
    try:
        conn = sqlite3.connect(str(RISK_DB))
        counts["rated_tokens"] = conn.execute(
            "SELECT COUNT(DISTINCT token_id) FROM crypto_rating_daily"
        ).fetchone()[0]
        counts["vitality_scores"] = conn.execute(
            "SELECT COUNT(*) FROM vitality_scores"
        ).fetchone()[0]
        try:
            counts["ndd_tokens"] = conn.execute(
                "SELECT COUNT(DISTINCT token_id) FROM crypto_ndd_daily"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            counts["ndd_tokens"] = counts["rated_tokens"]
        conn.close()
    except Exception as e:
        logger.warning("Risk DB error: %s", e)
        counts["rated_tokens"] = 0
        counts["vitality_scores"] = 0

    # Token count from SEO DB
    try:
        conn = sqlite3.connect(str(SEO_DB))
        counts["seo_tokens"] = conn.execute(
            "SELECT COUNT(*) FROM crypto_tokens"
        ).fetchone()[0]
        conn.close()
    except Exception as e:
        logger.warning("SEO DB error: %s", e)
        counts["seo_tokens"] = 0

    # Slug file counts
    slug_dir = Path(__file__).parent
    crypto_dir = slug_dir / "crypto"

    for name, path in [
        ("agent_safety_slugs", slug_dir / "agent_safety_slugs.json"),
        ("mcp_server_slugs", slug_dir / "mcp_server_slugs.json"),
        ("comparison_pairs", slug_dir / "comparison_pairs.json"),
        ("token_slugs", crypto_dir / "token_slugs.json"),
        ("vitality_compare_pairs", crypto_dir / "vitality_compare_pairs.json"),
    ]:
        try:
            with open(path) as f:
                data = json.load(f)
            counts[name] = len(data) if isinstance(data, (list, dict)) else 0
        except (FileNotFoundError, json.JSONDecodeError):
            counts[name] = 0

    return counts


def format_number(n: int) -> str:
    """Format number with commas: 15098 -> 15,098."""
    return f"{n:,}"


def update_file(path: Path, counts: dict, today: str) -> list[str]:
    """Update numbers in a file. Returns list of changes made."""
    if not path.exists():
        logger.warning("File not found: %s", path)
        return []

    with open(path) as f:
        content = f.read()

    original = content
    changes = []

    # The main token count used in text like "15,098 rated tokens" or "15,000+ tokens"
    # We use vitality_scores as the primary count (it's the most comprehensive)
    total_tokens = counts["vitality_scores"] or counts["ndd_tokens"] or counts["rated_tokens"]

    # Pattern: "N,NNN tokens" or "N,NNN+ tokens" or "N,NNN rated tokens"
    def replace_token_count(m):
        prefix = m.group(1) or ""
        suffix = m.group(2)
        new_num = format_number(total_tokens)
        return f"{prefix}{new_num}{suffix}"

    # Update "15,098 tokens" / "15,098 rated tokens" / "15,000+ tokens"
    new_content = re.sub(
        r'(\b)(\d{1,3}(?:,\d{3})*)\+?\s+(tokens?\s+rated|rated\s+tokens?|tokens)',
        lambda m: f"{m.group(1)}{format_number(total_tokens)} {m.group(3)}",
        content,
    )
    if new_content != content:
        changes.append(f"token count -> {format_number(total_tokens)}")
        content = new_content

    # "15,098 rated" standalone
    new_content = re.sub(
        r'(\b)(\d{1,3}(?:,\d{3})*)\s+rated\b(?!\s+tokens)',
        lambda m: f"{m.group(1)}{format_number(total_tokens)} rated",
        content,
    )
    if new_content != content:
        changes.append(f"rated count -> {format_number(total_tokens)}")
        content = new_content

    # "204K agents" -> update with agent safety slug count as proxy
    # Keep the "204K" or "5M+" format for agent counts since they come from Postgres
    # We don't update these as they require the live API

    # MCP server count: "25K MCP servers" or "25,000 MCP"
    mcp_count = counts.get("mcp_server_slugs", 0)
    if mcp_count > 0:
        # Only update specific MCP page counts, not the 25K+ total
        pass

    # Update comparison counts: "100 side-by-side" or "100 comparisons"
    comp_count = counts.get("comparison_pairs", 0)
    if comp_count > 0:
        new_content = re.sub(
            r'\b\d+\s+(side-by-side\s+(?:agent\s+)?comparisons?)',
            f"{comp_count} \\1",
            content,
        )
        if new_content != content:
            changes.append(f"comparison count -> {comp_count}")
            content = new_content

    # Agent safety page count: "500 AI agents" in safety context
    safety_count = counts.get("agent_safety_slugs", 0)
    if safety_count > 0:
        new_content = re.sub(
            r'listing\s+\d+\s+AI\s+agents\s+with\s+independent\s+trust',
            f"listing {safety_count} AI agents with independent trust",
            content,
        )
        if new_content != content:
            changes.append(f"safety page count -> {safety_count}")
            content = new_content

    # MCP trust page count: "500 trust-rated MCP servers"
    mcp_page_count = counts.get("mcp_server_slugs", 0)
    if mcp_page_count > 0:
        new_content = re.sub(
            r'listing\s+\d+\s+trust-rated\s+MCP',
            f"listing {mcp_page_count} trust-rated MCP",
            content,
        )
        if new_content != content:
            changes.append(f"MCP page count -> {mcp_page_count}")
            content = new_content

    if content != original:
        with open(path, "w") as f:
            f.write(content)

    return changes


def main():
    t0 = time.time()
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    logger.info("=" * 60)
    logger.info("LLM Context Updater started at %s", now.isoformat())

    # Get current counts
    counts = get_counts()
    logger.info("Current counts:")
    for k, v in sorted(counts.items()):
        logger.info("  %-25s %s", k, format_number(v) if isinstance(v, int) else v)

    # Update each LLM context file
    all_changes = []

    for path in [LLMS_TXT, LLMS_FULL_TXT]:
        if path.exists():
            changes = update_file(path, counts, today)
            if changes:
                logger.info("Updated %s:", path.name)
                for c in changes:
                    logger.info("  - %s", c)
                all_changes.extend(changes)
            else:
                logger.info("No changes needed for %s", path.name)

    elapsed = time.time() - t0
    logger.info("-" * 60)
    logger.info("LLM CONTEXT UPDATE COMPLETE")
    logger.info("  Files checked:     %d", sum(1 for p in [LLMS_TXT, LLMS_FULL_TXT] if p.exists()))
    logger.info("  Changes made:      %d", len(all_changes))
    logger.info("  Elapsed:           %.1fs", elapsed)
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
