"""Parse ZARQ-relevant FastAPI route declarations from the source tree.

We *don't* import the app to discover routes (that would couple the test
suite to the app's import graph and runtime DB connections). We grep the
source and extract the route path string from each decorator, then prepend
the APIRouter prefix that the file's router was declared with. Static,
fast, and works even when the app is down — which matters for regression
detection.

Prefix handling rationale (post-2026-05-30 phase 3 finding): a route
declared `@router.get("/rating/{token_id}")` inside
`crypto_api.py` where the file has `router = APIRouter(prefix="/crypto")`
serves traffic at `/crypto/rating/{token_id}` once included. The earlier
version of this module greppd the decorator string only and produced 100+
false 404s in the phase-2 run. We now parse the prefix per file and
prepend it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ZARQ_KEYWORDS = (
    "zarq", "paper", "trade", "crypto", "signal", "vitality", "risk",
    "distress", "ndd", "structural", "breakout", "yield", "defi", "token",
    "vital", "rating", "alert", "track", "dash", "kya", "cascade",
    "recovery", "methodology", "early.warning", "whitepaper", "backtest",
    "machine.discovery",
)

# Match `@router.get("/foo", ...)`, `@app.post("/bar")`, etc.
DECORATOR_RE = re.compile(
    r"""
    @(?P<obj>\w+)            # router / app / *_router / *_app
    \.(?P<method>get|post|put|delete|patch|head|options)
    \(\s*
    (?P<quote>['"])
    (?P<path>[^'"]+)
    (?P=quote)
    """,
    re.VERBOSE,
)

# Routes we explicitly skip even though the path matches a keyword:
#   - sitemap-style XML endpoints are auto-generated dumps; testing them
#     just checks the file builds, not the surface
#   - dashboard_old.py is legacy as the name implies
SKIP_FILE_SUBSTRINGS = ("dashboard_old.py",)
SKIP_PATH_PREFIXES = ("/sitemap-",)

# Match `<name> = APIRouter(prefix="/foo", ...)` or `prefix='/foo'`.
# Stops at the first non-greedy quoted string after `prefix=`.
ROUTER_PREFIX_RE = re.compile(
    r"""
    (?P<name>\w+)\s*=\s*APIRouter\(
    [^)]*?
    prefix\s*=\s*(?P<q>['"])(?P<prefix>[^'"]*)(?P=q)
    """,
    re.VERBOSE | re.DOTALL,
)


def _is_zarq_relevant(file_path: str, route_path: str) -> bool:
    needle = f"{file_path} {route_path}".lower()
    return any(kw in needle for kw in ZARQ_KEYWORDS)


def _file_prefix_map(file_path: str) -> dict[str, str]:
    """Return {router_var_name: prefix_string} for APIRouters in the file.

    Read once per file, cached at the call site by `discover_zarq_routes`.
    Files with no APIRouter declarations return {}.
    """
    out: dict[str, str] = {}
    try:
        with open(file_path) as fh:
            src = fh.read()
    except OSError:
        return out
    for m in ROUTER_PREFIX_RE.finditer(src):
        out[m.group("name")] = m.group("prefix").rstrip("/")
    return out


def discover_zarq_routes(source_root: Path) -> list[dict]:
    """Return every ZARQ-relevant route declaration under `source_root`.

    Each entry: {"file": str, "line": int, "method": str, "path": str,
    "decorator_object": str}. Skips backups, __pycache__, sitemap routes,
    and the legacy dashboard_old.
    """
    src = str(source_root)
    # Use a single grep to enumerate decorator lines. We re-parse each match
    # in Python for correctness — grep's -P regex isn't portable.
    cmd = [
        "grep", "-rn", "-E",
        r"@(\w+)\.(get|post|put|delete|patch|head|options)\(",
        src,
        "--include=*.py",
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=False)
    routes: list[dict] = []
    prefix_cache: dict[str, dict[str, str]] = {}
    for raw in out.stdout.splitlines():
        # raw: <path>:<line>:<text>
        try:
            file_part, line_part, code = raw.split(":", 2)
        except ValueError:
            continue
        if "__pycache__" in file_part or file_part.endswith(".bak"):
            continue
        if any(s in file_part for s in SKIP_FILE_SUBSTRINGS):
            continue
        m = DECORATOR_RE.search(code)
        if not m:
            continue
        raw_path = m.group("path")
        decorator_obj = m.group("obj")

        # Look up the router prefix for this file × object pair, if any.
        if file_part not in prefix_cache:
            prefix_cache[file_part] = _file_prefix_map(file_part)
        prefix = prefix_cache[file_part].get(decorator_obj, "")
        full_path = (prefix + raw_path) if prefix else raw_path

        if any(full_path.startswith(p) for p in SKIP_PATH_PREFIXES):
            continue
        if not _is_zarq_relevant(file_part, full_path):
            continue
        routes.append({
            "file": file_part,
            "line": int(line_part),
            "method": m.group("method").upper(),
            "path": full_path,
            "raw_path": raw_path,
            "router_prefix": prefix,
            "decorator_object": decorator_obj,
        })
    return routes


def substitute_path_params(path: str, inputs: dict) -> str | None:
    """Substitute synthetic values into path parameters. Returns the concrete
    URL or None if a parameter has no mapping (skip the test).

    Supports the parameter names we see in the codebase: token_id, token,
    slug, agent, agent_name, agent_slug, token_a, token_b, category.
    """
    # Prefer the explicit substitution map from the fixtures JSON if present;
    # fall back to the inputs[]-derived defaults otherwise.
    sub_map = dict(inputs.get("_param_substitutions", {}))
    sub_map.setdefault("token_id",   inputs["tokens"][0])
    sub_map.setdefault("token",      inputs["tokens"][0])
    sub_map.setdefault("slug",       inputs["tokens"][0])
    sub_map.setdefault("agent",      inputs["agents"][0])
    sub_map.setdefault("agent_name", inputs["agents"][0])
    sub_map.setdefault("agent_slug", inputs["agents"][0])
    sub_map.setdefault("token_a",    inputs["tokens"][0])
    sub_map.setdefault("token_b",    inputs["tokens"][1])
    sub_map.setdefault("category",   inputs["categories"][0])
    out = path
    for name, value in sub_map.items():
        out = out.replace("{" + name + "}", value)
    # Any unresolved {name} → cannot substitute → caller decides what to do.
    if "{" in out and "}" in out:
        return None
    return out


if __name__ == "__main__":
    # Manual invocation for debugging: `python -m tests.zarq_surface.route_discovery`
    routes = discover_zarq_routes(Path("/Users/anstudio/agentindex/agentindex"))
    print(f"Discovered {len(routes)} ZARQ-relevant routes.")
    for r in routes[:5]:
        print(r)
