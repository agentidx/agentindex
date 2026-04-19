#!/usr/bin/env python3
"""
Nerq-migration pre-check verifier (L8 / T187).

Reads assertions the runbook at ~/smedjan/runbooks/nerq-migration.md makes
about current config and checks each one. Emits a markdown report with
one PASS/FAIL/UNKNOWN verdict per assertion.

Usage:
    python3 -m smedjan.scripts.nerq_migration_precheck \
        [--out PATH] [--json]

Defaults:
    out = ~/smedjan/audits/L8-nerq-migration-readiness-<YMD>.md

No writes to Nerq-prod or any LaunchAgent. Read-only probes only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import shutil
import subprocess
import sys
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

HOME = Path.home()
SMEDJAN_HOME = HOME / "smedjan"
RUNBOOK_PATH = SMEDJAN_HOME / "runbooks" / "nerq-migration.md"
LINUX_AUTH_RUNBOOK = SMEDJAN_HOME / "runbooks" / "claude-code-linux-auth.md"
LAUNCHAGENT_DIR = HOME / "Library" / "LaunchAgents"
MAC_CONFIG_TOML = SMEDJAN_HOME / "config" / "config.toml"
SMEDJAN_HOST_CONFIG_PATH = "/home/smedjan/smedjan/config/config.toml"
SSH_HOST = "smedjan"
SSH_TIMEOUT = "5"


@dataclass
class Verdict:
    id: str
    statement: str
    category: str
    verdict: str  # PASS | FAIL | UNKNOWN
    detail: str = ""
    source_line: str = ""


def _run(cmd: list[str], *, timeout: int = 20) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError as e:
        return 127, "", f"not found: {e}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"


def _ssh(cmd: str, *, timeout: int = 15) -> tuple[int, str, str]:
    return _run(
        [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={SSH_TIMEOUT}",
            SSH_HOST,
            cmd,
        ],
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_file_exists(path: Path, detail_hint: str = "") -> tuple[str, str]:
    if path.exists():
        return "PASS", f"{path} exists"
    return "FAIL", f"{path} missing{(': ' + detail_hint) if detail_hint else ''}"


def check_runbook_present() -> tuple[str, str]:
    return check_file_exists(RUNBOOK_PATH)


def check_mac_config_present() -> tuple[str, str]:
    return check_file_exists(MAC_CONFIG_TOML)


def _load_smedjan_config():
    # Import lazily so this script can be imported as a module even when
    # config import would otherwise fail (e.g., missing tomllib on py3.10).
    from smedjan import config  # type: ignore
    return config


def check_config_loadable() -> tuple[str, str]:
    try:
        cfg = _load_smedjan_config()
    except Exception as e:
        return "FAIL", f"import smedjan.config failed: {e}"
    if cfg.SMEDJAN_DB_DSN is None:
        return "FAIL", "SMEDJAN_DB_DSN is None — config.toml not loaded"
    return "PASS", f"config loaded from {cfg.CONFIG_DIR}"


def _dsn_host(dsn: str) -> str:
    # postgresql://user:pw@host:port/db
    if "@" not in dsn:
        return ""
    rest = dsn.split("@", 1)[1]
    return rest.split(":", 1)[0].split("/", 1)[0]


def check_smedjan_db_host_is_hetzner() -> tuple[str, str]:
    cfg = _load_smedjan_config()
    host = _dsn_host(cfg.SMEDJAN_DB_DSN or "")
    if host == "smedjan":
        return "PASS", f"smedjan_db host = {host}"
    return "FAIL", f"smedjan_db host = {host!r}; runbook expects 'smedjan'"


def check_nerq_ro_host_is_localhost() -> tuple[str, str]:
    cfg = _load_smedjan_config()
    host = _dsn_host(cfg.NERQ_RO_DSN or "")
    if host in ("localhost", "127.0.0.1"):
        return "PASS", f"nerq_readonly_source host = {host}"
    return "FAIL", f"nerq_readonly_source host = {host!r}; runbook expects localhost"


def check_analytics_mirror_host_is_hetzner() -> tuple[str, str]:
    cfg = _load_smedjan_config()
    host = _dsn_host(cfg.ANALYTICS_MIRROR_DSN or "")
    if host == "smedjan":
        return "PASS", f"analytics_mirror host = {host}"
    return "FAIL", f"analytics_mirror host = {host!r}; runbook expects 'smedjan'"


def check_worker_location_mac_studio() -> tuple[str, str]:
    cfg = _load_smedjan_config()
    if cfg.WORKER_LOCATION == "mac_studio":
        return "PASS", "worker.location = mac_studio"
    return "FAIL", f"worker.location = {cfg.WORKER_LOCATION!r}"


def check_launchagent(name: str) -> tuple[str, str]:
    plist = LAUNCHAGENT_DIR / name
    if not plist.exists():
        return "FAIL", f"{plist} missing"
    # is it loaded?
    code, out, _err = _run(["launchctl", "list"], timeout=10)
    label = name.removesuffix(".plist")
    if code == 0 and label in out:
        return "PASS", f"{name} exists and is loaded"
    return "PASS", f"{name} exists (not currently loaded — load state is orthogonal)"


def check_script_exists(rel: str) -> tuple[str, str]:
    p = REPO_ROOT / rel
    return check_file_exists(p)


def check_nerq_readonly_connects_and_has_software_registry() -> tuple[str, str]:
    try:
        from smedjan import sources  # type: ignore
        with sources.nerq_readonly_cursor() as (_c, cur):
            cur.execute("SELECT to_regclass('public.software_registry')")
            row = cur.fetchone()
    except Exception as e:
        return "FAIL", f"nerq_readonly connect or query failed: {e}"
    if row and row[0]:
        return "PASS", "nerq_readonly connects; public.software_registry present"
    return "FAIL", "nerq_readonly connects but public.software_registry missing"


def check_smedjan_readonly_role_exists() -> tuple[str, str]:
    try:
        from smedjan import sources  # type: ignore
        with sources.nerq_readonly_cursor() as (_c, cur):
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", ("smedjan_readonly",))
            row = cur.fetchone()
    except Exception as e:
        return "FAIL", f"pg_roles probe failed: {e}"
    return ("PASS", "smedjan_readonly role present in Nerq cluster") if row else (
        "FAIL", "smedjan_readonly role missing"
    )


def check_smedjan_db_worker_heartbeats() -> tuple[str, str]:
    try:
        from smedjan import sources  # type: ignore
        with sources.smedjan_db_cursor() as (_c, cur):
            cur.execute("SELECT to_regclass('smedjan.worker_heartbeats')")
            row = cur.fetchone()
    except Exception as e:
        return "FAIL", f"smedjan_db probe failed: {e}"
    return ("PASS", "smedjan.worker_heartbeats present") if row and row[0] else (
        "FAIL", "smedjan.worker_heartbeats missing"
    )


def check_remote_smedjan_reachable() -> tuple[str, str]:
    code, out, err = _ssh("hostname && uname -s")
    if code != 0:
        return "UNKNOWN", f"ssh smedjan failed: {err or out}"
    return "PASS", f"ssh smedjan OK: {out.replace(chr(10), ' / ')}"


def check_remote_config_toml() -> tuple[str, str]:
    code, out, err = _ssh(f"test -f {shlex.quote(SMEDJAN_HOST_CONFIG_PATH)} && echo ok")
    if code == 0 and out == "ok":
        return "PASS", f"{SMEDJAN_HOST_CONFIG_PATH} exists on smedjan"
    return "FAIL", f"{SMEDJAN_HOST_CONFIG_PATH} missing on smedjan ({err or out})"


def check_remote_analytics_import_timer() -> tuple[str, str]:
    code, out, err = _ssh(
        "systemctl list-timers smedjan-analytics-import.timer "
        "--no-pager --all 2>&1 | head -20"
    )
    if code != 0:
        return "UNKNOWN", f"remote systemctl failed: {err or out}"
    if "smedjan-analytics-import.timer" in out:
        return "PASS", "smedjan-analytics-import.timer is known to systemd on smedjan"
    return "FAIL", f"timer not listed:\n{out}"


def check_linux_auth_runbook_present() -> tuple[str, str]:
    return check_file_exists(LINUX_AUTH_RUNBOOK)


def check_git_locked_helper() -> tuple[str, str]:
    return check_file_exists(REPO_ROOT / "scripts" / "git-locked.sh")


# ---------------------------------------------------------------------------
# Assertion catalogue — extracted from
# ~/smedjan/runbooks/nerq-migration.md
# ---------------------------------------------------------------------------

CHECKS: list[tuple[str, str, str, Callable[[], tuple[str, str]], str]] = [
    # (id, category, statement, fn, runbook line hint)

    # --- Runbook + helper presence ------------------------------------------
    ("A00", "runbook", "Runbook file present at ~/smedjan/runbooks/nerq-migration.md",
     check_runbook_present, "(precondition)"),
    ("A01", "runbook", "Helper scripts/git-locked.sh exists for locked git writes",
     check_git_locked_helper, "(precondition)"),

    # --- Component placement (from the 'Smedjan components today' table) ---
    ("A10", "components", "smedjan factory DB + schedulers on smedjan.nbg1.hetzner "
     "(SMEDJAN_DB_DSN host = smedjan)",
     check_smedjan_db_host_is_hetzner,
     "L12: factory DB | smedjan.nbg1.hetzner"),
    ("A11", "components", "Worker (factory_core) on Mac Studio "
     "(worker.location = mac_studio)",
     check_worker_location_mac_studio,
     "L13: Worker (factory_core loop) | Mac Studio"),
    ("A12", "components", "canary_monitor on Mac Studio "
     "(com.nerq.smedjan.canary_monitor.plist present)",
     lambda: check_launchagent("com.nerq.smedjan.canary_monitor.plist"),
     "L14: canary_monitor | Mac Studio"),
    ("A13", "components", "analytics-mirror exporter on Mac Studio "
     "(com.nerq.smedjan.analytics_export.plist present)",
     lambda: check_launchagent("com.nerq.smedjan.analytics_export.plist"),
     "L15: analytics-mirror exporter | Mac Studio"),
    ("A14", "components", "Nerq replica Postgres reachable locally on Mac Studio "
     "(nerq_readonly host = localhost, software_registry queryable)",
     check_nerq_readonly_connects_and_has_software_registry,
     "L16 + cutover step 6"),
    ("A15", "components", "analytics_mirror DSN points at the smedjan host",
     check_analytics_mirror_host_is_hetzner,
     "L14 of config.toml / runbook 'What does NOT change'"),

    # --- Mac-side config file -----------------------------------------------
    ("A20", "config", "Mac-side config ~/smedjan/config/config.toml present "
     "(runbook assumes this is where the Nerq DSN edit happens on worker host)",
     check_mac_config_present,
     "(inferred: step 5 edits config on 'smedjan' side)"),
    ("A21", "config", "smedjan.config imports cleanly (returns non-None DSNs)",
     check_config_loadable,
     "step 5 verify command"),
    ("A22", "config", "nerq_readonly_source DSN host = localhost "
     "(what the runbook says the single-line edit will flip)",
     check_nerq_ro_host_is_localhost,
     "L19 of config.toml / step 5"),

    # --- LaunchAgents invoked explicitly in the cutover checklist -----------
    ("A30", "launchagents",
     "LaunchAgent com.nerq.smedjan.ai_demand.plist present",
     lambda: check_launchagent("com.nerq.smedjan.ai_demand.plist"),
     "step 1 + step 10"),
    ("A31", "launchagents",
     "LaunchAgent com.nerq.smedjan.l1_observation.plist present",
     lambda: check_launchagent("com.nerq.smedjan.l1_observation.plist"),
     "step 1 + step 10"),

    # --- Scripts referenced by move-to-new-Nerq steps -----------------------
    ("A40", "scripts", "scripts/canary_monitor_l1.py exists (step 7)",
     lambda: check_script_exists("scripts/canary_monitor_l1.py"),
     "step 7"),
    ("A41", "scripts", "scripts/smedjan-analytics-export.sh exists (step 8)",
     lambda: check_script_exists("scripts/smedjan-analytics-export.sh"),
     "step 8"),

    # --- Postgres-side assertions -------------------------------------------
    ("A50", "postgres", "smedjan_readonly role exists on the Nerq cluster "
     "(pg_roles probe)",
     check_smedjan_readonly_role_exists,
     "L29 pg_roles verify"),
    ("A51", "postgres", "smedjan.worker_heartbeats exists in the smedjan DB "
     "(step 11 relies on it)",
     check_smedjan_db_worker_heartbeats,
     "step 11"),

    # --- Remote smedjan host ------------------------------------------------
    ("A60", "remote", "ssh smedjan works (prereq for the smedjan-side steps)",
     check_remote_smedjan_reachable,
     "steps 1, 5, 10"),
    ("A61", "remote", "Remote config /home/smedjan/smedjan/config/config.toml exists",
     check_remote_config_toml,
     "step 5"),
    ("A62", "remote", "systemd timer smedjan-analytics-import.timer installed on smedjan",
     check_remote_analytics_import_timer,
     "step 1 + step 10"),

    # --- Future-host assertions (explicitly unverifiable until cutover) -----
    ("A70", "future", "New Nerq host has pg_hba entry for "
     "'host agentindex smedjan_readonly 100.64.0.0/10 scram-sha-256'",
     lambda: ("UNKNOWN", "new Nerq host does not exist yet — verify on cutover day"),
     "L30"),
    ("A71", "future", "New Nerq host postgresql.conf listen_addresses includes Tailscale IP",
     lambda: ("UNKNOWN", "new Nerq host does not exist yet — verify on cutover day"),
     "L31"),
    ("A72", "future", "Claude Code headless Linux auth available for worker move",
     lambda: ("UNKNOWN",
              f"depends on upstream Anthropic work — see {LINUX_AUTH_RUNBOOK}"),
     "step 9 + future cleanups"),

    # --- Ancillary docs -----------------------------------------------------
    ("A80", "runbook", "Companion runbook claude-code-linux-auth.md present "
     "(referenced from step 9 and the 'future cleanups' section)",
     check_linux_auth_runbook_present,
     "step 9, future cleanups"),
]


def run_all() -> list[Verdict]:
    out: list[Verdict] = []
    for cid, cat, stmt, fn, src in CHECKS:
        try:
            verdict, detail = fn()
        except Exception as e:
            verdict = "UNKNOWN"
            detail = f"check raised: {e}\n{traceback.format_exc(limit=2)}"
        out.append(
            Verdict(
                id=cid,
                statement=stmt,
                category=cat,
                verdict=verdict,
                detail=detail,
                source_line=src,
            )
        )
    return out


def _counts(results: list[Verdict]) -> dict[str, int]:
    c = {"PASS": 0, "FAIL": 0, "UNKNOWN": 0}
    for r in results:
        c[r.verdict] = c.get(r.verdict, 0) + 1
    return c


def to_markdown(results: list[Verdict]) -> str:
    counts = _counts(results)
    today = dt.date.today().isoformat()
    lines: list[str] = []
    lines.append(f"# L8 — Nerq-migration readiness audit ({today})")
    lines.append("")
    lines.append(
        f"Runbook under audit: `{RUNBOOK_PATH}` · "
        f"Generated by `smedjan/scripts/nerq_migration_precheck.py`"
    )
    lines.append("")
    lines.append(
        "**Summary:** "
        + ", ".join(f"{k}={counts.get(k, 0)}" for k in ("PASS", "FAIL", "UNKNOWN"))
        + f" · total={len(results)}"
    )
    lines.append("")
    lines.append(
        "Scope: one verdict per assertion the runbook makes about the *current* "
        "configuration. Assertions about the *future* Nerq host (new pg_hba, "
        "new listen_addresses, Claude-Code headless auth) are recorded as UNKNOWN "
        "by design — they cannot be checked until cutover day."
    )
    lines.append("")

    cat_titles = {
        "runbook": "Runbook + helper presence",
        "components": "Component placement (current hybrid layout)",
        "config": "Mac-side config.toml assertions",
        "launchagents": "LaunchAgents referenced in the cutover checklist",
        "scripts": "Scripts referenced by move-to-new-Nerq steps",
        "postgres": "Postgres role / schema assertions",
        "remote": "Remote smedjan host (Hetzner / Tailscale)",
        "future": "Future-host assertions (unverifiable pre-cutover)",
    }
    by_cat: dict[str, list[Verdict]] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)

    for cat, title in cat_titles.items():
        rows = by_cat.get(cat, [])
        if not rows:
            continue
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| ID | Verdict | Assertion | Runbook ref | Detail |")
        lines.append("|---|---|---|---|---|")
        for r in rows:
            detail_cell = r.detail.replace("|", "\\|").replace("\n", " ⏎ ")
            stmt_cell = r.statement.replace("|", "\\|")
            src_cell = r.source_line.replace("|", "\\|")
            lines.append(
                f"| {r.id} | **{r.verdict}** | {stmt_cell} | {src_cell} | {detail_cell} |"
            )
        lines.append("")

    fails = [r for r in results if r.verdict == "FAIL"]
    if fails:
        lines.append("## Failures that block cutover")
        lines.append("")
        for r in fails:
            lines.append(f"- **{r.id}** — {r.statement}")
            lines.append(f"  - Detail: {r.detail}")
        lines.append("")

    unk = [r for r in results if r.verdict == "UNKNOWN"]
    if unk:
        lines.append("## Unverifiable on cutover-1 (expected or needs attention)")
        lines.append("")
        for r in unk:
            lines.append(f"- **{r.id}** — {r.statement}")
            lines.append(f"  - Detail: {r.detail}")
        lines.append("")

    lines.append("## How this was produced")
    lines.append("")
    lines.append(
        "Every assertion in the runbook body (tables + cutover steps + "
        "'what does NOT change' section) was translated into a Python check. "
        "No writes to Nerq-prod, no LaunchAgent load/unload, no remote mutations. "
        "Re-run:"
    )
    lines.append("")
    lines.append("```bash")
    lines.append("python3 -m smedjan.scripts.nerq_migration_precheck")
    lines.append("```")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out",
        default=str(SMEDJAN_HOME / "audits" /
                    f"L8-nerq-migration-readiness-{dt.date.today():%Y%m%d}.md"),
        help="destination markdown report",
    )
    ap.add_argument("--json", action="store_true", help="also print JSON to stdout")
    ap.add_argument("--no-write", action="store_true",
                    help="do not write the markdown file")
    args = ap.parse_args()

    results = run_all()
    md = to_markdown(results)

    if not args.no_write:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md)
        print(f"wrote {out}")

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2))

    counts = _counts(results)
    # Exit 0 even on FAILs — this is a reporting tool, not a gate.
    # Callers grep the report for "FAIL" if they want to block cutover.
    print("summary:", counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
