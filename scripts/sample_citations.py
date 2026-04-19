#!/usr/bin/env python3
"""Sample Nerq citation-rate on ChatGPT / Perplexity / Claude web UIs.

T172 (L7). Runs a fixed 20-query set against each platform's **free
public web UI** via browser automation (playwright). For each
(query, platform) pair we record whether the assistant's final
answer mentions nerq.ai (or "nerq" as a standalone token) so the
Smedjan measurement layer can track citation-rate over time.

Output: ~/smedjan/measurement/citation-<ymd>.jsonl, one record per
line::

    {"query": "...", "platform": "perplexity",
     "nerq_in_answer": true, "sampled_at": "2026-04-19T12:34:56Z"}

**No paid APIs.** This script MUST NOT call the Anthropic, OpenAI, or
Perplexity paid APIs — only the free public web UIs via automated
browser. If playwright is not installed the script exits 2 with a
"blocked" marker line so the factory records the dependency gap
cleanly instead of crashing.

Session cookies, when needed, are loaded from
~/.config/smedjan/browser-sessions/<platform>.json (playwright
storage_state format). Missing session state for a platform skips
that platform with a per-row note rather than aborting the run.
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import re
import sys
import time

QUERIES = [
    "best AI agent directory 2026",
    "how to evaluate AI agent trustworthiness",
    "open source AI agent marketplace",
    "AI tool trust score methodology",
    "where to find verified AI agents",
    "AI agent risk assessment platforms",
    "compare AI agent frameworks 2026",
    "AI coding agents leaderboard",
    "LLM tool trust rating",
    "agentic AI safety indicators",
    "AI agent security ratings",
    "which AI agents are production ready",
    "independent AI agent reviews",
    "AI agent due diligence framework",
    "autonomous agent trust layer",
    "AI agent directory with risk scores",
    "how to pick a safe AI agent",
    "AI agent Moody's equivalent",
    "AI agent registry with audits",
    "best source for AI agent quality metrics",
]

PLATFORMS = ("chatgpt", "perplexity", "claude")

OUT_DIR = pathlib.Path.home() / "smedjan" / "measurement"
SESSION_DIR = pathlib.Path.home() / ".config" / "smedjan" / "browser-sessions"

NERQ_PATTERN = re.compile(r"\bnerq(?:\.ai)?\b", re.IGNORECASE)

PLATFORM_CONFIG = {
    "chatgpt": {
        "url": "https://chat.openai.com/",
        "input_selector": "textarea[data-testid='prompt-textarea'], textarea",
        "answer_selector": "[data-message-author-role='assistant']",
        "submit_key": "Enter",
    },
    "perplexity": {
        "url": "https://www.perplexity.ai/",
        "input_selector": "textarea",
        "answer_selector": "div.prose, div[class*='prose']",
        "submit_key": "Enter",
    },
    "claude": {
        "url": "https://claude.ai/new",
        "input_selector": "div[contenteditable='true']",
        "answer_selector": "div[data-testid*='message'], div.font-claude-message",
        "submit_key": "Enter",
    },
}


def _now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _block(reason: str) -> int:
    """Emit a single BLOCKED marker line and exit non-zero."""
    sys.stderr.write(f"sample_citations.py: BLOCKED — {reason}\n")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    marker = OUT_DIR / f"citation-{_dt.date.today().isoformat()}.blocked"
    marker.write_text(
        json.dumps({"blocked_at": _now_utc(), "reason": reason}) + "\n",
        encoding="utf-8",
    )
    return 2


def _answer_mentions_nerq(text: str) -> bool:
    return bool(NERQ_PATTERN.search(text or ""))


def _sample_one(page, platform: str, query: str, *, timeout_s: int = 60) -> str:
    """Type `query`, submit, wait for the assistant's answer, return its text.

    Returns the concatenated text of all assistant message blocks found on
    the page after the answer stream settles. Exceptions bubble up so the
    caller can record a sampling failure for that (query, platform) pair.
    """
    cfg = PLATFORM_CONFIG[platform]
    page.goto(cfg["url"], wait_until="domcontentloaded")
    page.wait_for_selector(cfg["input_selector"], timeout=timeout_s * 1000)
    page.fill(cfg["input_selector"], query)
    page.keyboard.press(cfg["submit_key"])

    # Poll answer selector until text stops growing (crude streaming wait).
    deadline = time.monotonic() + timeout_s
    last_len = -1
    stable_ticks = 0
    answer_text = ""
    while time.monotonic() < deadline:
        nodes = page.query_selector_all(cfg["answer_selector"])
        answer_text = "\n".join((n.inner_text() or "") for n in nodes)
        if len(answer_text) == last_len and len(answer_text) > 0:
            stable_ticks += 1
            if stable_ticks >= 3:
                break
        else:
            stable_ticks = 0
            last_len = len(answer_text)
        time.sleep(1.0)
    return answer_text


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return _block(
            "no browser-automation toolchain available — need playwright or puppeteer"
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"citation-{_dt.date.today().isoformat()}.jsonl"

    rows_written = 0
    with sync_playwright() as pw, out_path.open("a", encoding="utf-8") as fh:
        browser = pw.chromium.launch(headless=True)
        try:
            for platform in PLATFORMS:
                session_file = SESSION_DIR / f"{platform}.json"
                storage_state = str(session_file) if session_file.exists() else None
                context = browser.new_context(storage_state=storage_state)
                page = context.new_page()
                for query in QUERIES:
                    record = {
                        "query": query,
                        "platform": platform,
                        "nerq_in_answer": False,
                        "sampled_at": _now_utc(),
                    }
                    try:
                        answer = _sample_one(page, platform, query)
                        record["nerq_in_answer"] = _answer_mentions_nerq(answer)
                    except Exception as exc:  # noqa: BLE001 — log + continue
                        record["error"] = f"{type(exc).__name__}: {exc}"
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                    fh.flush()
                    rows_written += 1
                context.close()
        finally:
            browser.close()

    sys.stdout.write(f"wrote {rows_written} rows to {out_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
