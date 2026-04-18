"""
Smedjan configuration — all environment-derived constants live here.

Anchored to two principles: (1) no paid APIs, (2) read-only against Nerq
tables; writes happen in the `smedjan` schema only.
"""
from __future__ import annotations

import os
from pathlib import Path

# ── Postgres ──────────────────────────────────────────────────────────────
# Smedjan writes to the `smedjan` schema inside the agentindex database
# on the Nbg primary. A dedicated DB (or dedicated Postgres on smedjan.nerq)
# is a future migration; for Phase A we share the cluster for operational
# simplicity. Reads against public.software_registry / entity_lookup stay
# read-only.
PG_PRIMARY_DSN = os.environ.get(
    "SMEDJAN_PG_DSN",
    "host=100.119.193.70 port=5432 dbname=agentindex user=anstudio",
)
SMEDJAN_SCHEMA = "smedjan"

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
