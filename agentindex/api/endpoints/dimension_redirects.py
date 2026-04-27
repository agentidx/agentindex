"""301 redirects from localised + verb-prefix `/<prefix>/<slug>.json`
variants to the canonical `/dimensions/<slug>.json`.

Background — AUDIT-QUERY-20260427 finding 7 (FU-QUERY-20260427-07):
AI bots (ChatGPT-led) probe a fictitious localised JSON-API surface,
generating ~250 404s/day across ~14 prefixes:

    /rating/<slug>.json         /prediction/<slug>.json
    /signals/<slug>.json        /dependencies/<slug>.json
    /dimensiones/<slug>.json    /Dimensionen/<slug>.json
    /boyut/<slug>.json          /dimensioner/<slug>.json
    /dimensjoner/<slug>.json    /dimensiuni/<slug>.json
    /dimensioni/<slug>.json     /dimensies/<slug>.json
    /dimensi/<slug>.json

100% of these are .json suffix — machine traffic constructing a JSON
API. The canonical surface is `/dimensions/<slug>.json` (served by
`agentindex.api.endpoints.dimensions`). This module gives bots a
citable redirect target.

Two layers:

  1. Localised prefixes (no existing handlers) → unconditional 301.
     Registered as explicit GET routes on `router`.

  2. Verb prefixes (rating/prediction/signals/dependencies — already
     served by their own routers) → 404-only 301.
     `attach_404_redirects(app)` installs an HTTP middleware that
     rewrites a 404 on `/<verb>/<slug>.json` into a 301 toward the
     canonical surface. URLs that the existing handlers serve as 200
     are untouched.

Mounted from `agentindex/api/discovery.py`.
"""
from __future__ import annotations

import logging
import re
from typing import Awaitable, Callable

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import RedirectResponse

logger = logging.getLogger("agentindex.api.endpoints.dimension_redirects")

router = APIRouter(tags=["redirects"], include_in_schema=False)

# Localised /<dimension-word>/<slug>.json variants observed in the 404
# logs. Both the bot-observed casing and a lowercase variant are
# registered for the German "Dimensionen" so case differences don't
# fall through to a 404.
LOCALISED_PREFIXES: tuple[str, ...] = (
    "dimensiones",     # es
    "Dimensionen",     # de (observed casing)
    "dimensionen",     # de (lowercase fallback)
    "boyut",           # tr
    "dimensioner",     # sv/da/no
    "dimensjoner",     # nb
    "dimensiuni",      # ro
    "dimensioni",      # it
    "dimensies",       # nl
    "dimensi",         # id
)

# Verb-prefix variants whose existing /{slug}.json handlers may 404
# when the slug is unknown. Their 200 responses are untouched.
VERB_PREFIXES: tuple[str, ...] = (
    "rating",
    "prediction",
    "signals",
    "dependencies",
)


def _make_redirect_handler(prefix: str) -> Callable[[str], Response]:
    """Build a handler that 301-redirects /<prefix>/<slug>.json
    to /dimensions/<slug>.json. The closure captures `prefix` for
    logging only — the redirect target is always the canonical path."""

    def handler(slug: str) -> Response:
        target = f"/dimensions/{slug}.json"
        logger.info(
            "dimension_redirect prefix=%s slug=%s target=%s",
            prefix, slug, target,
        )
        return RedirectResponse(target, status_code=301)

    safe = re.sub(r"[^A-Za-z0-9_]", "_", prefix)
    handler.__name__ = f"_redirect_{safe}"
    return handler


for _prefix in LOCALISED_PREFIXES:
    router.add_api_route(
        path=f"/{_prefix}/{{slug}}.json",
        endpoint=_make_redirect_handler(_prefix),
        methods=["GET", "HEAD"],
        include_in_schema=False,
        response_class=RedirectResponse,
        status_code=301,
    )


_VERB_404_PATH_RE = re.compile(
    r"^/(?:" + "|".join(re.escape(p) for p in VERB_PREFIXES) + r")/(?P<slug>[^/]+)\.json$"
)


def attach_404_redirects(app: FastAPI) -> None:
    """Attach middleware that turns 404s on `/<verb>/<slug>.json`
    into 301s toward the canonical `/dimensions/<slug>.json`.

    Only installs once per app (idempotent: subsequent calls are
    no-ops). Other 404 paths fall through unchanged.
    """
    if getattr(app.state, "_dim_404_redirects_installed", False):
        return

    @app.middleware("http")
    async def _verb_404_to_dimensions(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        if response.status_code != 404:
            return response
        match = _VERB_404_PATH_RE.match(request.url.path)
        if match is None:
            return response
        slug = match.group("slug")
        target = f"/dimensions/{slug}.json"
        logger.info(
            "dimension_redirect_404 path=%s slug=%s target=%s",
            request.url.path, slug, target,
        )
        return RedirectResponse(target, status_code=301)

    app.state._dim_404_redirects_installed = True
