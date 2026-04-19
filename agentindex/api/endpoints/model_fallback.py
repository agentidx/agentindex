"""/model/{slug} 200-with-noindex fallback + backfill enqueue.

Background
----------
`AUDIT-QUERY-20260418` finding #1 showed `/model/<slug>` returned 404 on
54.2% of requests (1,086 / 2,002 over the 7-day window ending
2026-04-18T14:24Z). Representative miss slugs — `zk-kit-poseidon-cipher`,
`rwkv-v7-7-2b-g0a-gguf`, `juit-librebarcode` — come straight from AI-bot
citations (ChatGPT, Perplexity) for real HuggingFace / npm / crates IDs
that simply aren't yet in `public.entity_lookup`. Every 404 served to a
crawler is citation damage because the outcome gets cached.

This module installs an HTTP middleware that post-processes responses on
paths matching `^/model/[^/]+(/[^/]+)?$`. When the upstream handler (the
main `/model/{slug}` renderer in `agentindex/seo_dynamic.py`) emits a 404,
the middleware rewrites the response to:

  1. HTTP 200 with an `X-Robots-Tag: noindex, follow` header + matching
     `<meta name="robots">` tag, so search engines do not index the
     placeholder.
  2. A human- and bot-readable stub page that names the slug, acknowledges
     the gap, links to `/discover` and `/safe/<slug>`, and states that
     the trust rating is pending.
  3. A side-effect: append the slug (+ bot UA, referer) to
     `~/smedjan/worker-logs/model-backfill-queue.tsv`, deduped in-process
     via a bounded LRU so a single rogue crawler cannot flood the log.

The module also registers `/v1/ops/model-miss-metrics` which returns a
small JSON document — hit / miss / fallback counts, miss rate, rolling
recent misses — so the next audit (`AUDIT-QUERY-2026-04-25`) can verify
the 404 rate has dropped below 10%.

Whitelisted scope: `agentindex/api/`, `agentindex/renderers/`. This file
sits in `agentindex/api/endpoints/` and is wired from
`agentindex/api/discovery.py`. Neither `agentindex/seo_dynamic.py` nor
`agentindex/api/main.py` is modified.
"""
from __future__ import annotations

import html as html_mod
import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict, deque
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger("agentindex.api.endpoints.model_fallback")

router = APIRouter(tags=["model_fallback"])

SITE = "https://nerq.ai"
TODAY = date.today().isoformat()
YEAR = date.today().year

# ── Path match ────────────────────────────────────────────────────────────
# Covers `/model/zk-kit-poseidon-cipher` and `/model/org/llama-3` (HF-style
# two-segment slugs). Excludes the hub (`/model`, `/models`) and any deeper
# paths like `/model/foo/bar/baz`.
_PATH_RE = re.compile(r"^/model/[^/]+(?:/[^/]+)?$")

# Slug sanity — mirrors the `/hacked/` endpoint's constraint. Prevents HTML
# injection through the URL and rejects obvious garbage (spaces, fragments,
# path traversal) before doing any work.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,199}$")

# ── Backfill queue ────────────────────────────────────────────────────────
BACKFILL_LOG_PATH = Path(
    os.environ.get(
        "NERQ_MODEL_BACKFILL_LOG",
        str(Path.home() / "smedjan" / "worker-logs" / "model-backfill-queue.tsv"),
    )
)

_LRU_MAX = 4096
_seen: "OrderedDict[str, float]" = OrderedDict()
_seen_lock = threading.Lock()


def _should_log(slug: str, ttl_s: int = 900) -> bool:
    """Deduplicated gate: log each slug at most once per 15 min per process."""
    now = time.time()
    with _seen_lock:
        ts = _seen.get(slug)
        if ts is not None and (now - ts) < ttl_s:
            _seen.move_to_end(slug)
            return False
        _seen[slug] = now
        _seen.move_to_end(slug)
        while len(_seen) > _LRU_MAX:
            _seen.popitem(last=False)
    return True


def _enqueue_backfill(slug: str, user_agent: str, referer: str, is_bot: bool) -> bool:
    """Append a TSV row to the backfill queue. Best-effort; never raises."""
    try:
        BACKFILL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = "\t".join([
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            slug,
            "bot" if is_bot else "human",
            (user_agent or "").replace("\t", " ").replace("\n", " ")[:240],
            (referer or "").replace("\t", " ").replace("\n", " ")[:240],
        ]) + "\n"
        # O_APPEND guarantees atomicity for single-line writes up to PIPE_BUF.
        with open(BACKFILL_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line)
        return True
    except Exception as exc:
        logger.warning("model backfill enqueue failed for %s: %s", slug, exc)
        return False


# ── Metrics ───────────────────────────────────────────────────────────────
_metrics_lock = threading.Lock()
_metrics: dict[str, int] = {
    "total_requests": 0,   # any /model/<slug>(/<sub>)? seen by middleware
    "upstream_200": 0,     # upstream handler served a 200 — indexed model
    "upstream_other": 0,   # upstream served non-200 non-404 — untouched
    "fallback_served": 0,  # middleware replaced a 404 with the fallback
    "backfill_enqueued": 0,  # distinct slug rows appended
    "invalid_slug": 0,     # slug failed _SLUG_RE; kept as 404
}

_RECENT_MAX = 100
_recent: "deque[dict[str, Any]]" = deque(maxlen=_RECENT_MAX)


def _bump(key: str, n: int = 1) -> None:
    with _metrics_lock:
        _metrics[key] = _metrics.get(key, 0) + n


def _record_recent(entry: dict[str, Any]) -> None:
    with _metrics_lock:
        _recent.append(entry)


# ── Renderer ──────────────────────────────────────────────────────────────
def _pretty_name(slug: str) -> str:
    tail = slug.rsplit("/", 1)[-1]
    tokens = re.split(r"[-_.]", tail)
    return " ".join(t.capitalize() for t in tokens if t) or tail or slug


def render_fallback(slug: str) -> str:
    name = _pretty_name(slug)
    safe_slug = html_mod.escape(slug)
    safe_name = html_mod.escape(name)
    canonical = f"{SITE}/discover?q={safe_slug}"

    faq_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f"Does Nerq have a trust score for {name}?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": (
                        f"Not yet. \"{name}\" has been queued for indexing but "
                        "Nerq has not finished computing a Trust Score. Check "
                        "back in 24–48 hours or browse the full Nerq index."
                    ),
                },
            },
            {
                "@type": "Question",
                "name": f"Why is {name} not indexed?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": (
                        "Nerq crawls 5M+ AI assets across HuggingFace, GitHub, "
                        "npm, PyPI, crates.io and other registries on a rolling "
                        "schedule. Newly released or low-traffic assets may lag "
                        "the public index by a few days."
                    ),
                },
            },
        ],
    }

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex, follow">
<title>{safe_name} — trust score pending | Nerq</title>
<meta name="description" content="Nerq has not yet indexed {safe_name}. Trust score, security analysis and alternatives will appear once ingestion completes.">
<link rel="canonical" href="{canonical}">
<meta name="nerq:type" content="model_fallback">
<meta name="nerq:slug" content="{safe_slug}">
<meta name="nerq:status" content="pending_backfill">
<meta name="nerq:audit" content="AUDIT-QUERY-20260418#1">
<meta name="nerq:followup" content="FU-QUERY-20260418-01">
<script type="application/ld+json">{json.dumps(faq_ld, ensure_ascii=False)}</script>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:780px;margin:0 auto;padding:24px;color:#1e293b;line-height:1.6}}
h1{{font-size:28px;margin:0 0 8px}}
h2{{font-size:20px;margin:28px 0 10px}}
.note{{font-size:16px;padding:16px;background:#f8fafc;border-left:4px solid #0d9488;border-radius:0 8px 8px 0;margin:8px 0 20px}}
a{{color:#0d9488;text-decoration:none}} a:hover{{text-decoration:underline}}
ul{{padding-left:22px}} li{{margin:4px 0}}
.meta{{font-size:12px;color:#64748b;margin-top:32px}}
</style>
</head><body>
<h1>{safe_name}</h1>
<p class="note"><strong>Trust score pending.</strong> Nerq has not yet indexed
<code>{safe_slug}</code>. This slug has been queued for backfill; a full trust
report will appear here once ingestion completes (usually within 24–48 hours).</p>

<h2>While you wait</h2>
<ul>
<li><a href="/discover?q={safe_slug}">Search Nerq</a> for similar models already indexed.</li>
<li><a href="/safe/{safe_slug}">Preview the safety-report URL</a> — it will populate once the trust score is computed.</li>
<li><a href="/models">Browse top-rated models &amp; datasets</a>.</li>
</ul>

<h2>What is Nerq?</h2>
<p>Nerq is an independent trust layer for the agentic economy: 5M+ AI assets
(agents, tools, models, datasets) with Trust Scores derived from security,
activity, documentation and popularity signals. No ads, no pay-to-rank.</p>

<p class="meta">Slug: <code>{safe_slug}</code> · Last checked: {TODAY} ·
Status: queued for backfill · Source audit: AUDIT-QUERY-20260418 finding #1.
This page is served by the model-fallback middleware and is intentionally
<em>noindex</em> — it does not ship a Trust Score and is not a valid
citation target.</p>
</body></html>"""


# ── Middleware ────────────────────────────────────────────────────────────
_AI_BOT_MARKERS = (
    "gptbot", "chatgpt", "oai-searchbot", "claude", "anthropic", "perplexity",
    "googleother", "bytespider", "ccbot", "mistral", "youbot", "amazonbot",
    "applebot-extended", "meta-externalagent", "cohere-ai",
)


def _is_ai_bot(ua: str) -> bool:
    lo = (ua or "").lower()
    return any(m in lo for m in _AI_BOT_MARKERS)


async def _consume(iterator: Iterable[bytes]) -> None:
    async for _ in iterator:  # type: ignore[attr-defined]
        pass


async def model_fallback_middleware(request: Request, call_next):
    path = request.url.path
    # Hot-path early exit for non-model requests. `/model` (hub) and
    # `/models` (plural hub) do not match the trailing-slash-plus-slug form
    # so they fall through untouched.
    if not path.startswith("/model/"):
        return await call_next(request)
    if not _PATH_RE.match(path):
        return await call_next(request)

    response = await call_next(request)

    _bump("total_requests")
    status = response.status_code

    if status == 200:
        _bump("upstream_200")
        return response
    if status != 404:
        _bump("upstream_other")
        return response

    # 404 from upstream — we own the response now. Drain the body so the
    # underlying connection state is clean before we return our replacement.
    if hasattr(response, "body_iterator"):
        try:
            await _consume(response.body_iterator)
        except Exception:
            logger.debug("failed to drain 404 body for %s", path, exc_info=True)

    slug = path[len("/model/"):]
    if not _SLUG_RE.match(slug.lower()):
        _bump("invalid_slug")
        return HTMLResponse(
            "<!DOCTYPE html><html><head><meta name=\"robots\" content=\"noindex\">"
            "<title>Invalid slug — Nerq</title></head><body><h1>Invalid slug</h1>"
            "<p><a href=\"/\">Search Nerq</a></p></body></html>",
            status_code=404,
            headers={"X-Robots-Tag": "noindex"},
        )

    ua = request.headers.get("user-agent", "")
    ref = request.headers.get("referer", "")
    is_bot = _is_ai_bot(ua)

    if _should_log(slug):
        if _enqueue_backfill(slug, ua, ref, is_bot):
            _bump("backfill_enqueued")
    _bump("fallback_served")
    _record_recent({
        "slug": slug,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ai_bot": is_bot,
    })

    body = render_fallback(slug)
    return HTMLResponse(
        content=body,
        status_code=200,
        headers={
            "X-Robots-Tag": "noindex, follow",
            "Cache-Control": "public, max-age=300",
            "X-Schema-Version": "nerq-model-fallback/v1",
        },
    )


# ── Metrics endpoint ──────────────────────────────────────────────────────
@router.get("/v1/ops/model-miss-metrics", summary="Miss-rate metrics for /model/{slug}")
def model_miss_metrics() -> JSONResponse:
    with _metrics_lock:
        snapshot = dict(_metrics)
        recent = list(_recent)

    total = snapshot.get("total_requests", 0)
    miss = snapshot.get("fallback_served", 0)
    miss_rate = (miss / total) if total else 0.0

    payload = {
        "source_audit": "AUDIT-QUERY-20260418#1",
        "followup": "FU-QUERY-20260418-01",
        "since_process_start": True,
        "counters": snapshot,
        "miss_rate": round(miss_rate, 4),
        "recent_misses": recent,
        "backfill_log": str(BACKFILL_LOG_PATH),
    }
    return JSONResponse(payload)


# ── Installer ─────────────────────────────────────────────────────────────
def install(app: FastAPI) -> None:
    """Wire the middleware + metrics router onto the given FastAPI app.

    The middleware is added with the HTTP hook (not the ASGI stack) because
    we need a FastAPI `Request` object and the ergonomic `call_next`
    semantics.  Including the router under `/v1/ops/` keeps it out of the
    public crawl surface without requiring auth (the data is non-sensitive).
    """
    app.middleware("http")(model_fallback_middleware)
    app.include_router(router)
