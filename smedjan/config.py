"""
Smedjan configuration — loads per-host config.toml + .env.

Principles: (1) no paid APIs, (2) writes go to the dedicated smedjan DB,
(3) reads against Nerq are read-only. DSNs come from config.toml with
${VAR} placeholders substituted from .env (mode 600) in the same dir.

Config resolution order:
    1. $SMEDJAN_CONFIG_DIR
    2. ~/smedjan/config                  (Mac Studio layout)
    3. /home/smedjan/smedjan/config      (smedjan.nbg1 layout)
    4. Legacy hard-coded fallback — warns so the silent fallback is loud.
"""
from __future__ import annotations

import logging
import os
import re
import tomllib
from pathlib import Path

SMEDJAN_SCHEMA = "smedjan"

_log = logging.getLogger("smedjan.config")


def _candidate_dirs() -> list[Path]:
    env = os.environ.get("SMEDJAN_CONFIG_DIR")
    cands: list[Path] = []
    if env:
        cands.append(Path(env))
    cands.append(Path.home() / "smedjan" / "config")
    cands.append(Path("/home/smedjan/smedjan/config"))
    return cands


def _read_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


_VAR_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _substitute(value: str, env: dict[str, str]) -> str:
    def _sub(m: "re.Match[str]") -> str:
        key = m.group(1)
        if key not in env:
            raise KeyError(f"config references unset secret ${{{key}}}; check .env")
        return env[key]
    return _VAR_RE.sub(_sub, value)


def _load_config() -> tuple[dict, Path | None]:
    for d in _candidate_dirs():
        toml_path = d / "config.toml"
        env_path = d / ".env"
        if not toml_path.exists():
            continue
        env = _read_dotenv(env_path)
        raw = tomllib.loads(toml_path.read_text())

        def walk(node):
            if isinstance(node, dict):
                return {k: walk(v) for k, v in node.items()}
            if isinstance(node, list):
                return [walk(v) for v in node]
            if isinstance(node, str):
                return _substitute(node, env)
            return node
        return walk(raw), d
    return {}, None


_CONFIG, CONFIG_DIR = _load_config()


def _dsn(section: str) -> str | None:
    sec = _CONFIG.get(section) if _CONFIG else None
    return (sec or {}).get("dsn")


SMEDJAN_DB_DSN           = _dsn("smedjan_db")
NERQ_RO_DSN              = _dsn("nerq_readonly_source")
ANALYTICS_MIRROR_DSN     = _dsn("analytics_mirror")
ANALYTICS_MIRROR_SCHEMA  = (
    ((_CONFIG.get("analytics_mirror") or {}).get("schema")) if _CONFIG else None
) or "analytics_mirror"
WORKER_LOCATION          = (
    ((_CONFIG.get("worker") or {}).get("location")) if _CONFIG else "mac_studio"
)

_LEGACY_DSN = "host=100.119.193.70 port=5432 dbname=agentindex user=anstudio"

# Back-compat for scripts imported before M6 rolled out.
PG_PRIMARY_DSN = SMEDJAN_DB_DSN or os.environ.get("SMEDJAN_PG_DSN") or _LEGACY_DSN
if SMEDJAN_DB_DSN is None:
    _log.warning("no config.toml found; falling back to legacy DSN %s", _LEGACY_DSN)

# ── Filesystem ────────────────────────────────────────────────────────────
REPO_ROOT     = Path("/Users/anstudio/agentindex")
SMEDJAN_ROOT  = Path("/Users/anstudio/smedjan")
WORKER_LOGDIR = SMEDJAN_ROOT / "worker-logs"
DOCS_DIR      = SMEDJAN_ROOT / "docs"
RUNBOOK_DIR   = SMEDJAN_ROOT / "runbooks"

# ── Task-execution policy ─────────────────────────────────────────────────
# Files on this list block any task whose whitelisted_files overlaps them.
# Mirrors CLAUDE.md + v2.2 addendum "what you must NOT do".
FORBIDDEN_PATHS: tuple[str, ...] = (
    "agentindex/api/main.py",
    "alembic/",
    "robots.txt",
    "sitemap.xml",
    "CLAUDE.md",
    "docs/buzz-context.md",
    ".env",
)

# Auto-yes fires when: risk=low AND every whitelisted_file is inside one
# of these prefixes AND no FORBIDDEN_PATHS overlap AND all deps are done.
AUTO_YES_WHITELIST_PREFIXES: tuple[str, ...] = (
    "agentindex/agent_safety_pages.py",
    "agentindex/nerq_design.py",
    "agentindex/translations.py",
    "agentindex/faq_schemas/",
    "agentindex/smedjan/",                 # factory's own tree
    "smedjan/",                            # user-home factory artefacts
    "scripts/smedjan",
    "scripts/baseline_l1_canary.py",
    "scripts/canary_monitor_l1.py",
    "scripts/observation_l1_canary.py",
    "scripts/compute_ai_demand_score.py",
    "scripts/dryrun_l1_kings_unlock.py",
    "scripts/purge_redis_canary.py",
)

# ── Notifications ─────────────────────────────────────────────────────────
NTFY_TOPIC = os.environ.get("SMEDJAN_NTFY_TOPIC", "nerq-alerts")
NTFY_URL   = f"https://ntfy.sh/{NTFY_TOPIC}"

# ── Worker ────────────────────────────────────────────────────────────────
# `claude` CLI is the ONLY supported invocation. Paid APIs are forbidden.
CLAUDE_CLI = os.environ.get("SMEDJAN_CLAUDE_CLI", "/usr/local/bin/claude")
CLAUDE_MODEL = os.environ.get("SMEDJAN_CLAUDE_MODEL", "")  # default = CLI default
WORKER_IDLE_SLEEP_SECONDS = int(os.environ.get("SMEDJAN_WORKER_IDLE", "60"))
WORKER_MAX_TASK_SECONDS   = int(os.environ.get("SMEDJAN_WORKER_MAX_TASK", "3600"))
WORKER_CLAIM_TTL_MINUTES  = int(os.environ.get("SMEDJAN_WORKER_CLAIM_TTL", "90"))
WORKER_DRY_RUN_DEFAULT    = os.environ.get("SMEDJAN_WORKER_DRY_RUN", "1") == "1"
