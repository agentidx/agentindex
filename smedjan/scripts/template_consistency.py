"""template_consistency.py — L6 Kings-vs-non-Kings section-skeleton audit (T163).

Goal
----
For each of the Nerq verticals that still ship two template variants
(Kings with the fully-unlocked L1 scaffold vs. non-Kings which, outside
the L1_UNLOCK_REGISTRIES allowlist, render a reduced skeleton), sample
up to 20 Kings and 20 non-Kings, render them through the local Nerq
safety-page endpoint (``/safe/{slug}``), extract the per-page
``<h2 class="section-title">`` values, normalise them, and check:

    non_king_sections ⊆ king_sections

Any vertical where the non-King union carries a section the King union
does not is flagged as a genuine template regression. With the L1
Kings-unlock rolling out the two sets should be converging, so a
non-King-only section strongly implies that a renderer branch is
guarded by the wrong flag (e.g. gated on ``not is_king`` by mistake).

Output
------
``~/smedjan/audits/L6-template-consistency-<YYYYMMDD>.md`` — one
summary table plus per-vertical detail.

Invocation
----------
    /Users/anstudio/agentindex/venv/bin/python \
        -m smedjan.scripts.template_consistency [--sample N]

Renders pages in-process by importing
``agentindex.agent_safety_pages._render_agent_page`` rather than hitting
the local Nerq HTTP endpoint — the endpoint is frequently saturated by
production traffic and we want a deterministic read regardless. Only
writes are to the audit markdown file under ``~/smedjan/audits/``.

``L1_UNLOCK_REGISTRIES`` should match production (currently
``gems,homebrew``) to audit the live non-King branch behaviour.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import html as _html
import logging
import os
import pathlib
import re
import sys
from typing import Optional

from smedjan import sources

log = logging.getLogger("smedjan.template_consistency")

# Verticals worth auditing: the software/commercial registries that run
# the dual King/non-King scaffold in agent_safety_pages.py. Skipped on
# purpose: city / charity / ingredient / supplement / cosmetic_ingredient
# / country / vpn — they ship dedicated templates (_render_travel_page /
# _render_charity_page / _render_ingredient_page / vpn-specific branch)
# that do not participate in the L1 Kings-unlock.
VERTICALS = (
    "npm", "pypi", "crates", "nuget", "go", "gems", "packagist", "homebrew",
    "wordpress", "vscode", "chrome", "firefox",
    "ios", "android", "steam",
    "website", "saas", "crypto",
    "antivirus", "hosting", "password_manager", "website_builder",
)

SECTION_TITLE_RE = re.compile(
    r'<h2[^>]*class="section-title"[^>]*>(?P<title>.*?)</h2>',
    re.IGNORECASE | re.DOTALL,
)
H1_RE = re.compile(r"<h1[^>]*>(?P<content>.*?)</h1>", re.IGNORECASE | re.DOTALL)

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def _strip_tags(s: str) -> str:
    return TAG_RE.sub("", s)


def _decode(s: str) -> str:
    return _html.unescape(s)


def _fetch_slugs(registry: str, is_king: bool, limit: int) -> list[tuple[str, str]]:
    """Return up to ``limit`` (slug, name) tuples for the vertical, trust DESC."""
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            """
            SELECT slug, name FROM software_registry
            WHERE registry = %s AND is_king = %s
              AND slug IS NOT NULL AND slug <> ''
            ORDER BY COALESCE(trust_score, 0) DESC, stars DESC NULLS LAST
            LIMIT %s
            """,
            (registry, is_king, limit),
        )
        return [(r[0], r[1]) for r in cur.fetchall()]


def _derive_display_name(slug: str, name: str) -> str:
    # Mirrors the logic in agent_safety_pages._render_agent_page: strip
    # any "org/" prefix and title-case with hyphens / underscores turned
    # to spaces. Good enough for entity-name redaction in H2 titles.
    leaf = (name or slug).split("/")[-1]
    return leaf.replace("-", " ").replace("_", " ").title()


# Words that are too short or too common to be safely redacted as
# entity-name fragments (they collide with template prose: "Is {E} …?",
# "Does {E} …?", "What is {E}'s …?").
_REDACT_STOPWORDS = {
    "is", "it", "a", "an", "the", "and", "or", "of", "for", "to", "in", "on",
    "at", "by", "be", "as", "do", "does", "did", "has", "have", "had",
    "what", "how", "who", "why", "not", "yes", "no", "this", "that",
    "me", "my", "we", "you", "your",
    "ai", "api", "app", "go", "io", "js", "css", "sql",
    "score", "trust", "safe", "score?",
    "find", "findings", "secure", "security", "data", "platforms", "platform",
    "analysis", "detailed", "frequently", "asked", "questions", "calculated",
    "across", "maintains", "collect",
}


def _normalise_title(
    raw: str, slug: str, name: str, displayed: str = ""
) -> str:
    """Redact entity-specific tokens so titles are comparable across rows.

    Redaction is a two-pass process. First we strip the **full** displayed
    entity string (pulled from the rendered ``<h1>``), which handles
    exotic punctuation and suffixes like ``®`` / ``™`` / ``(Tafsir & By
    Word)`` that survive word-level splitting. Second pass redacts
    remaining derived tokens on word boundaries, skipping anything
    shorter than 4 chars or listed in ``_REDACT_STOPWORDS`` — those
    collide with template prose and would otherwise produce junk titles
    like ``Detailed S{E} Analysis``.
    """
    t = _decode(_strip_tags(raw))
    t = WS_RE.sub(" ", t).strip()

    # Pass 1: whole-string displayed entity (case-insensitive). No length
    # gate — the H1 is authoritative for what the template actually
    # renders. This catches brand suffixes, parentheticals, bracketed
    # platform notes, and hieroglyphs.
    if displayed:
        t = re.sub(re.escape(displayed), "{E}", t, flags=re.IGNORECASE)

    # Pass 2: word-level fallback tokens (handles variants the H1 does
    # not capture — e.g. "What is LangChain's …" vs "langchain").
    display_fallback = _derive_display_name(slug, name)
    raw_tokens: set[str] = set()
    for src in (displayed, display_fallback, name or "", slug,
                slug.replace("-", " ")):
        if not src:
            continue
        raw_tokens.add(src)
        for word in re.split(r"[\s/_\-\.@\(\)\[\]\{\}&]+", src):
            if word:
                raw_tokens.add(word)

    usable: list[str] = []
    for tok in raw_tokens:
        if len(tok) < 4:
            continue
        if tok.lower() in _REDACT_STOPWORDS:
            continue
        usable.append(tok)

    # Longest first so multi-word names redact before their parts.
    for tok in sorted(usable, key=len, reverse=True):
        t = re.sub(r"\b" + re.escape(tok) + r"\b", "{E}", t, flags=re.IGNORECASE)

    # Strip lingering brand decorations clinging to {E}.
    t = re.sub(r"\{E\}\s*(?:®|™|\(R\)|\(TM\))", "{E}", t, flags=re.IGNORECASE)
    # Possessives that survive case-insensitive replacement.
    t = re.sub(r"\{E\}\s*(?:'s|&#39;s|&rsquo;s)", "{E}", t)
    # Parentheticals / brackets that directly follow the entity.
    t = re.sub(r"\{E\}\s*[\(\[][^)\]]*[\)\]]", "{E}", t)
    # Dedup runs: "{E} {E} Across Platforms" → "{E} Across …"
    t = re.sub(r"(\{E\}\s+){2,}", "{E} ", t)
    t = WS_RE.sub(" ", t).strip()
    return t


_RENDER_FN = None  # lazily imported; see _render_page()


def _render_page(slug: str, name: str) -> Optional[str]:
    """Render a /safe/{slug} page in-process. Returns HTML or None."""
    global _RENDER_FN
    if _RENDER_FN is None:
        # Deferred import — agentindex.agent_safety_pages is heavy and
        # pulls in the full FastAPI app module. We only need the pure
        # page-renderer entry point, which has no route-layer deps.
        from agentindex.agent_safety_pages import _render_agent_page as fn
        _RENDER_FN = fn
    try:
        return _RENDER_FN(slug, {"name": name or slug})
    except Exception as exc:
        log.warning("render failed slug=%s: %s", slug, exc)
        return None


_H1_PREFIXES = (
    "Is ", "Are ", "How to ", "How Safe is ", "How Safe Is ",
)
_H1_SUFFIXES = (
    " Safe?", " Safe", " Trust Score", " Trust Score?", " Review",
)


def _displayed_entity(html_body: str) -> str:
    """Pull the live display name out of the rendered ``<h1>``.

    The agent_safety_pages renderer title-cases / re-maps names in ways
    our DB columns do not capture; the H1 is authoritative.
    """
    m = H1_RE.search(html_body)
    if not m:
        return ""
    text = WS_RE.sub(" ", _decode(_strip_tags(m.group("content")))).strip()
    for p in _H1_PREFIXES:
        if text.startswith(p):
            text = text[len(p):]
            break
    for s in _H1_SUFFIXES:
        if text.endswith(s):
            text = text[: -len(s)]
            break
    return text.strip().rstrip("?").strip()


def _extract_sections(html_body: str, slug: str, name: str) -> set[str]:
    displayed = _displayed_entity(html_body)
    effective_name = displayed or name
    out: set[str] = set()
    for m in SECTION_TITLE_RE.finditer(html_body):
        norm = _normalise_title(m.group("title"), slug, effective_name, displayed)
        if norm:
            out.add(norm)
    return out


def _render_batch(
    rows: list[tuple[str, str]],
) -> tuple[set[str], int, int]:
    """Return (union_of_sections, rendered_count, failed_count)."""
    if not rows:
        return set(), 0, 0
    union: set[str] = set()
    ok = 0
    fail = 0
    # Sequential: _render_agent_page hits the same Postgres pool as the
    # live Nerq app; keeping concurrency at 1 avoids stealing connections
    # from production while the audit runs.
    for slug, name in rows:
        body = _render_page(slug, name)
        if not body:
            fail += 1
            continue
        union |= _extract_sections(body, slug, name)
        ok += 1
    return union, ok, fail


def _vertical_report(
    registry: str, king_union: set[str], non_king_union: set[str],
    k_ok: int, k_fail: int, n_ok: int, n_fail: int,
) -> tuple[str, bool, str]:
    """Return (markdown_block, is_regression, status_label)."""
    # A vertical with zero Kings cannot be audited for regression — the
    # King set is empty by construction, so every non-King section would
    # trip the subset test. Mark those separately.
    if k_ok == 0 and n_ok == 0:
        status = "insufficient-sample"
        regression = False
    elif k_ok == 0:
        status = "kings-absent"
        regression = False
    else:
        regression = bool(non_king_union - king_union)
        status = "REGRESSION" if regression else "ok"

    lines: list[str] = []
    lines.append(f"### `{registry}` — {status}")
    lines.append("")
    lines.append(
        f"- Kings sampled: **{k_ok}** rendered (+{k_fail} failed). "
        f"Non-Kings sampled: **{n_ok}** rendered (+{n_fail} failed)."
    )
    lines.append(
        f"- King-section count: **{len(king_union)}**. "
        f"Non-King-section count: **{len(non_king_union)}**."
    )
    shared = king_union & non_king_union
    king_only = king_union - non_king_union
    non_king_only = non_king_union - king_union
    lines.append(
        f"- Shared: **{len(shared)}** · King-only: **{len(king_only)}** · "
        f"Non-King-only (regression if >0): **{len(non_king_only)}**."
    )
    lines.append("")

    def _bullets(header: str, items: set[str]) -> None:
        if not items:
            return
        lines.append(f"**{header}**")
        for t in sorted(items):
            lines.append(f"- `{t}`")
        lines.append("")

    if regression:
        _bullets("Non-King-only sections (flagged):", non_king_only)
    elif non_king_only and status == "kings-absent":
        _bullets("Non-King-only sections (no King baseline):", non_king_only)
    _bullets("King-only sections:", king_only)
    _bullets("Shared sections:", shared)

    return "\n".join(lines), regression, status


def build_report(
    sample: int, verticals: tuple[str, ...] = VERTICALS,
) -> tuple[str, dict]:
    """Run the audit and return (markdown_body, stats)."""
    today = _dt.date.today().isoformat()
    l1_unlock = os.environ.get("L1_UNLOCK_REGISTRIES", "")
    header: list[str] = []
    header.append(f"# L6 Template Consistency Audit — {today}")
    header.append("")
    header.append(
        "For each vertical, up to **%d Kings** and **%d non-Kings** were "
        "sampled from `software_registry` (Nerq RO replica, highest "
        "`trust_score` first) and rendered in-process via "
        "`agentindex.agent_safety_pages._render_agent_page`. The "
        "`<h2 class=\"section-title\">` values were extracted and "
        "compared after entity-name redaction." % (sample, sample)
    )
    header.append("")
    header.append(
        f"`L1_UNLOCK_REGISTRIES = \"{l1_unlock}\"` at audit time "
        "(empty ⇒ no non-King unlocks, `*`/`all` ⇒ every registry "
        "unlocked). Registries named in this variable should converge "
        "toward full King/non-King parity."
    )
    header.append("")
    header.append(
        "A vertical is **flagged** when the non-King union contains any "
        "section the King union does not (i.e. non-Kings render richer "
        "than Kings — a renderer-branch regression, typically guarded "
        "on the wrong flag)."
    )
    header.append("")

    summary_rows: list[tuple[str, int, int, int, int, int, int, bool, str]] = []
    vertical_blocks: list[str] = []
    regressions: list[str] = []
    kings_absent: list[str] = []

    for reg in verticals:
        king_rows = _fetch_slugs(reg, True, sample)
        non_king_rows = _fetch_slugs(reg, False, sample)
        log.info(
            "vertical=%s kings=%d non-kings=%d",
            reg, len(king_rows), len(non_king_rows),
        )
        king_union, k_ok, k_fail = _render_batch(king_rows)
        non_king_union, n_ok, n_fail = _render_batch(non_king_rows)
        block, is_reg, status = _vertical_report(
            reg, king_union, non_king_union, k_ok, k_fail, n_ok, n_fail,
        )
        vertical_blocks.append(block)
        summary_rows.append((
            reg, k_ok, n_ok, len(king_union), len(non_king_union),
            len(king_union & non_king_union),
            len(non_king_union - king_union), is_reg, status,
        ))
        if is_reg:
            regressions.append(reg)
        if status == "kings-absent":
            kings_absent.append(reg)

    # Summary table right after the intro.
    summary: list[str] = []
    summary.append("## Summary")
    summary.append("")
    summary.append(
        "| Vertical | K rendered | N rendered | K-only | Shared | N-only | Flag |"
    )
    summary.append(
        "|---|---:|---:|---:|---:|---:|---|"
    )
    for reg, k_ok, n_ok, k_n, n_n, shared, n_only, is_reg, status in summary_rows:
        if is_reg:
            flag = "🚩 REGRESSION"
        elif status == "kings-absent":
            flag = "◐ kings-absent"
        elif status == "insufficient-sample":
            flag = "∅ no data"
        else:
            flag = "—"
        summary.append(
            f"| `{reg}` | {k_ok} | {n_ok} | {k_n - shared} | {shared} | {n_only} | {flag} |"
        )
    summary.append("")
    summary.append(
        f"**Verticals covered:** {len(summary_rows)} · "
        f"**Regressions:** {len(regressions)}"
        + (f" → {', '.join('`' + r + '`' for r in regressions)}" if regressions else "")
    )
    if kings_absent:
        summary.append(
            f"**Kings-absent** (comparison not possible): "
            f"{', '.join('`' + r + '`' for r in kings_absent)}"
        )
    summary.append("")

    body = "\n".join(header) + "\n" + "\n".join(summary) + "\n"
    body += "## Per-vertical detail\n\n" + "\n".join(vertical_blocks) + "\n"

    stats = {
        "verticals": len(summary_rows),
        "regressions": regressions,
        "kings_absent": kings_absent,
        "sample": sample,
        "l1_unlock": l1_unlock,
    }
    return body, stats


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=20,
                        help="max Kings + max non-Kings per vertical (default 20)")
    parser.add_argument("--out-dir",
                        default=str(pathlib.Path.home() / "smedjan" / "audits"),
                        help="directory to write the audit report into")
    parser.add_argument("--verticals", default="",
                        help="optional comma-separated subset of verticals to run")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    verts = VERTICALS
    if args.verticals.strip():
        chosen = tuple(v.strip() for v in args.verticals.split(",") if v.strip())
        verts = chosen

    try:
        body, stats = build_report(args.sample, verticals=verts)
    except sources.SourceUnavailable as exc:
        log.error("nerq readonly replica unavailable: %s", exc)
        return 2

    out_dir = pathlib.Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"L6-template-consistency-{_dt.date.today().strftime('%Y%m%d')}.md"
    out_path.write_text(body)

    log.info(
        "wrote %s — verticals=%d regressions=%d",
        out_path, stats["verticals"], len(stats["regressions"]),
    )
    print(out_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
