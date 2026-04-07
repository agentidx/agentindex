"""Internal URL localization — single source of truth for href generation.

THE PROBLEM THIS SOLVES:
    Before this module existed, internal links in Nerq were generated
    via ~700 hardcoded f-strings spread across 20+ Python files. Four
    different helper variables (_lp, _ss_lp, _lang_prefix, lp) existed
    independently. Three different regex rewriters duplicated the same
    logic in localized_routes.py. The result was 32% prefix coverage on
    localized pages — Norwegian users clicking "See Also" links landed
    on English pages.

THE SOLUTION:
    One function: localize_url(path, lang). It is the only authorized
    way to generate an internal URL. A linter in
    tests/test_no_hardcoded_links.py enforces this.

DESIGN: WHITELIST, NOT BLACKLIST
    We chose whitelist because the safe default for an unknown path is
    "do not prefix" — that way, a new /admin or /internal path never
    accidentally becomes /no/admin or /de/internal.
"""

from typing import FrozenSet, Tuple

from agentindex.i18n.languages import SUPPORTED_LANGS


# Prefixes that ARE localized content pages.
LOCALIZED_PREFIXES: Tuple[str, ...] = (
    "/safe/",
    "/best/",
    "/compare/",
    "/alternatives/",
    "/is-",
    "/does-",
    "/was-",
    "/what-is-",
    "/what-is/",       # entity pages: /what-is/nordvpn
    "/who-owns/",
    "/review/",
    "/pros-cons/",
    "/privacy/",       # entity pages: /privacy/nordvpn (NOT /privacy global)
    "/categories",
)

# Paths that are NEVER prefixed.
GLOBAL_PATHS: Tuple[str, ...] = (
    "/v1/",
    "/api/",
    "/static/",
    "/feed",
    "/sitemap",
    "/robots.txt",
    "/llms.txt",
    "/llms-full.txt",
    "/nerq/",
    "/methodology",
    "/about",
    "/contact",
    "/pricing",
    "/privacy",
    "/terms",
    "/whitepaper",
    "/health-disclaimer",
    "/compliance",
    "/dashboard",
    "/discover",
    "/claim",
    "/check-website",
    "/badges",
    "/badge/",
    "/ab-results",
    "/insights",
    "/briefing",
    "/answers",
    "/crash-watch",
    "/paper-trading",
    "/risk-scanner",
    "/oracle",
    "/webhooks",
    "/start",
    "/profile",
    "/report",
    "/reports",
    "/research",
    "/stats",
    "/leaderboard",
    "/popular",
    "/trending",
    "/new",
    "/verified",
    "/vitality",
    "/improve",
    "/predict",
    "/predictions",
    "/flywheel",
    "/weekly",
    "/demo",
    "/extension",
    "/extensions",
    "/cli",
    "/github-app",
    "/github-action",
    "/integrate",
    "/gateway",
    "/federation",
    "/compatibility",
    "/apps",
    "/crates",
    "/gems",
    "/homebrew",
    "/datasets",
    "/dataset",
    "/games",
    "/game",
    "/containers",
    "/container",
    "/commerce",
    "/npm",
    "/pypi",
    "/packagist",
    "/vscode",
    "/wordpress-plugins",
    "/chrome",
    "/packages",
    "/package",
    "/mcp",
    "/mcp-servers",
    "/agent",
    "/models",
    "/model",
    "/prompts",
    "/templates",
    "/spaces",
    "/space",
    "/tokens",
    "/protocol",
    "/framework",
    "/frameworks",
    "/org",
    "/orgs",
    "/index",
    "/industry",
    "/internal",
    "/admin",
    "/data",
    "/crypto",
    "/vpn",
    "/vpns",
    "/zarq",
    "/trust",
    "/scan",
    "/kya",
    "/action",
    "/guide",
    "/guides",
    "/docs",
    "/blog",
    "/for",
)

_LANG_PREFIXES: FrozenSet[str] = frozenset(f"/{lang}/" for lang in SUPPORTED_LANGS)


def _is_external(path: str) -> bool:
    if not path:
        return False
    if path.startswith(("http://", "https://", "//", "mailto:", "tel:", "javascript:")):
        return True
    return False


def _is_fragment_only(path: str) -> bool:
    return path.startswith("#")


def _is_relative(path: str) -> bool:
    return bool(path) and not path.startswith("/")


def _is_already_localized(path: str) -> bool:
    for prefix in _LANG_PREFIXES:
        if path.startswith(prefix):
            return True
    for lang in SUPPORTED_LANGS:
        if path == f"/{lang}":
            return True
    return False


def _is_global_path(path: str) -> bool:
    for global_prefix in GLOBAL_PATHS:
        if global_prefix.endswith("/"):
            if path.startswith(global_prefix):
                return True
        else:
            if path == global_prefix:
                return True
            if path.startswith(global_prefix + "/"):
                return True
            if path.startswith(global_prefix + "?"):
                return True
            if path.startswith(global_prefix + "#"):
                return True
    return False


def _is_localized_content(path: str) -> bool:
    for prefix in LOCALIZED_PREFIXES:
        if path.startswith(prefix):
            return True
    if path == "/":
        return True
    return False


def localize_url(path: str, lang: str = "en") -> str:
    """Generate a localized internal URL.

    This is the single authorized function for generating internal
    hrefs in Nerq. Do not construct URLs via f-strings — use this.
    """
    if not isinstance(path, str) or not path:
        return path if isinstance(path, str) else ""

    if lang == "en":
        return path

    if lang not in SUPPORTED_LANGS:
        return path

    if _is_external(path):
        return path
    if _is_fragment_only(path):
        return path
    if _is_relative(path):
        return path
    if _is_already_localized(path):
        return path

    # IMPORTANT: Check localized content BEFORE global paths.
    # Otherwise /privacy/nordvpn matches global "/privacy" exact rule
    # before we recognize it as an entity page under /privacy/ prefix.
    if _is_localized_content(path):
        return f"/{lang}{path}"

    if _is_global_path(path):
        return path

    return path
