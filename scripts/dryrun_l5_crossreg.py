#!/usr/bin/env python3
"""L5 cross-registry-link dryrun (T153).

Picks 50 slugs that have cross-registry duplicates and renders each safety
page twice — once with L5_CROSSREG_LINKS=off and once with =live — verifying:

  * Off  → page has NO 'cross-registry-links' block.
  * Live → page has the block, with at least one anchor.
  * HTML parses (html.parser doesn't raise) and contains <html>/<body>.

Exit 0 on success, 1 on first violation. Writes a one-line JSON summary
to stdout for the factory worker.

Usage:
    L5_CROSSREG_LINKS=live python3 scripts/dryrun_l5_crossreg.py
    python3 scripts/dryrun_l5_crossreg.py            # runs both modes
"""
from __future__ import annotations

import json
import os
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Ensure default mode before module import; we re-import inside _render_at_mode.
os.environ.setdefault("L5_CROSSREG_LINKS", "off")

import importlib

import agentindex.agent_safety_pages as asp  # noqa: E402
from sqlalchemy.sql import text  # noqa: E402

SAMPLE_SIZE = 50


def _pick_slugs(n: int) -> list[tuple[str, str]]:
    """Return [(slug, name), ...] for slugs that exist in >=2 registries."""
    session = asp.get_session()
    try:
        # Exclude registries served by alternate renderers (travel/charity/
        # ingredient) — those return early before king_sections is built and
        # would never carry the cross-registry section.
        skip_regs = ("country", "city", "charity",
                     "ingredient", "supplement", "cosmetic_ingredient")
        rows = session.execute(text("""
            WITH dups AS (
                SELECT slug
                FROM software_registry
                WHERE trust_score IS NOT NULL AND trust_score > 0
                  AND slug IS NOT NULL AND slug <> ''
                  AND registry NOT IN :skip
                GROUP BY slug
                HAVING COUNT(DISTINCT registry) >= 2
                LIMIT :n
            )
            SELECT DISTINCT ON (sr.slug) sr.slug, sr.name
            FROM software_registry sr
            JOIN dups d USING (slug)
            WHERE sr.registry NOT IN :skip
            ORDER BY sr.slug, sr.trust_score DESC
        """), {"n": n, "skip": skip_regs}).fetchall()
        return [(r[0], r[1]) for r in rows]
    finally:
        session.close()


class _HTMLSniffer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.has_html = False
        self.has_body = False
        self.has_crossreg = False
        self.crossreg_anchors = 0
        self._in_crossreg = False
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        if tag == "html":
            self.has_html = True
        elif tag == "body":
            self.has_body = True
        if tag == "section" and "cross-registry-links" in (attr_dict.get("class") or ""):
            self.has_crossreg = True
            self._in_crossreg = True
            self._depth = 1
            return
        if self._in_crossreg:
            self._depth += 1
            if tag == "a":
                self.crossreg_anchors += 1

    def handle_endtag(self, tag):
        if self._in_crossreg:
            self._depth -= 1
            if self._depth <= 0:
                self._in_crossreg = False


def _render_at_mode(mode: str, slug: str, name: str) -> str:
    os.environ["L5_CROSSREG_LINKS"] = mode
    importlib.reload(asp)
    out = asp._render_agent_page(slug, {"name": name})
    if isinstance(out, bytes):
        out = out.decode("utf-8", errors="replace")
    return out


def _check(html: str) -> _HTMLSniffer:
    sniffer = _HTMLSniffer()
    sniffer.feed(html)
    return sniffer


def main() -> int:
    samples = _pick_slugs(SAMPLE_SIZE)
    if len(samples) < SAMPLE_SIZE:
        print(json.dumps({"error": "not enough cross-registry slugs",
                          "got": len(samples), "wanted": SAMPLE_SIZE}))
        return 1

    failures: list[dict] = []
    off_with_block = 0
    live_with_block = 0
    live_anchors_total = 0
    pages_rendered = 0

    for slug, name in samples:
        try:
            html_off = _render_at_mode("off", slug, name)
            html_live = _render_at_mode("live", slug, name)
        except Exception as exc:
            failures.append({"slug": slug, "phase": "render", "error": repr(exc)})
            continue
        pages_rendered += 1

        s_off = _check(html_off)
        s_live = _check(html_live)

        if not (s_off.has_html and s_off.has_body):
            failures.append({"slug": slug, "phase": "off-html", "html_tag": s_off.has_html,
                             "body_tag": s_off.has_body})
        if not (s_live.has_html and s_live.has_body):
            failures.append({"slug": slug, "phase": "live-html", "html_tag": s_live.has_html,
                             "body_tag": s_live.has_body})
        if s_off.has_crossreg:
            off_with_block += 1
            failures.append({"slug": slug, "phase": "off-leak",
                             "msg": "cross-registry block rendered when env=off"})
        if s_live.has_crossreg:
            live_with_block += 1
            live_anchors_total += s_live.crossreg_anchors
        else:
            failures.append({"slug": slug, "phase": "live-missing",
                             "msg": "cross-registry block missing when env=live"})

    summary = {
        "samples": len(samples),
        "pages_rendered": pages_rendered,
        "off_with_block": off_with_block,
        "live_with_block": live_with_block,
        "live_anchors_total": live_anchors_total,
        "failure_count": len(failures),
        "failures_first_5": failures[:5],
        "ok": len(failures) == 0,
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
