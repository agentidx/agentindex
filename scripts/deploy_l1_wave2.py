#!/usr/bin/env python3
"""
deploy_l1_wave2.py — L1 Wave 2 registry unlock runner (npm, pypi, crates).

Widens the com.nerq.api LaunchAgent env var
    L1_UNLOCK_REGISTRIES: gems,homebrew -> gems,homebrew,npm,pypi,crates
in seven monitored steps:

  1. Read current L1_UNLOCK_REGISTRIES via PlistBuddy. Abort with
     STATUS: blocked if the value is not already exactly 'gems,homebrew'.
  2. For each of npm, pypi, crates run
         scripts/dryrun_l1_kings_unlock.py --n-per-reg 50 --registries <reg>
     and parse the summary.json. Halt with STATUS: needs_approval if any
     registry has crashes or antipatterns > 0.
  3. PlistBuddy Set the env var to 'gems,homebrew,npm,pypi,crates'.
  4. launchctl unload + load (not just kickstart — the 2026-04-18 incident
     confirmed kickstart alone does not propagate new EnvironmentVariables).
  5. Sleep 30s, then curl http://localhost:8000/v1/health and require
     status == 'ok'.
  6. Invoke scripts/purge_redis_canary.py with SMEDJAN_CANARY_REGS
     ='npm,pypi,crates' to evict stale /safe/<slug> page-cache entries.
  7. Write an observation report skeleton to
     ~/smedjan/observations/L1-wave2-<UTC-ts>.md for canary_monitor_l1
     to fill as gradient data lands.

The runner DOES NOT reopen L1_UNLOCK_REGISTRIES to all-at-once — it
sets the single allowlist 'gems,homebrew,npm,pypi,crates' and yields
to canary_monitor_l1 for the 30-min-per-phase monitoring cadence.

Safety rails:
  * `--dry-run` (default) prints every phase but does not touch the
    LaunchAgent, launchctl, Redis, or production endpoints.
  * `--execute` is required to perform any production mutation.
  * Step 2 is executed in both dry-run and execute modes because it is
    read-only relative to production.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

PLIST_PATH = Path(os.path.expanduser("~/Library/LaunchAgents/com.nerq.api.plist"))
PLISTBUDDY = "/usr/libexec/PlistBuddy"
LAUNCHCTL  = "/bin/launchctl"
LABEL      = "com.nerq.api"

PRE_UNLOCK  = "gems,homebrew"
POST_UNLOCK = "gems,homebrew,npm,pypi,crates"
NEW_REGS    = ["npm", "pypi", "crates"]

DRYRUN_SCRIPT = REPO_ROOT / "scripts" / "dryrun_l1_kings_unlock.py"
PURGE_SCRIPT  = REPO_ROOT / "scripts" / "purge_redis_canary.py"
HEALTH_URL    = os.environ.get("SMEDJAN_HEALTH_URL", "http://localhost:8000/v1/health")

OBS_DIR = Path(os.path.expanduser(
    os.environ.get("SMEDJAN_OBS_DIR", "~/smedjan/observations")
))
DRYRUN_OUT_BASE = Path(os.path.expanduser(
    os.environ.get("SMEDJAN_WAVE2_DRYRUN_DIR", "~/smedjan/discovery/canary-wave2")
))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("smedjan.deploy_l1_wave2")


class Blocked(Exception):
    """Precondition failed; runner must abort STATUS: blocked."""


class NeedsApproval(Exception):
    """Dry-run gate failed; runner must abort STATUS: needs_approval."""


# ---------- step 1: plist precondition ------------------------------------

def _plistbuddy_print(key_path: str) -> str:
    cmd = [PLISTBUDDY, "-c", f"Print :{key_path}", str(PLIST_PATH)]
    log.info("read plist key :%s", key_path)
    out = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out.stdout.strip()


def verify_precondition() -> None:
    if not PLIST_PATH.exists():
        raise Blocked(f"plist not found at {PLIST_PATH}")
    current = _plistbuddy_print("EnvironmentVariables:L1_UNLOCK_REGISTRIES")
    log.info("current L1_UNLOCK_REGISTRIES = %r", current)
    if current != PRE_UNLOCK:
        raise Blocked(
            f"precondition failed: L1_UNLOCK_REGISTRIES={current!r} "
            f"(expected exactly {PRE_UNLOCK!r})"
        )


# ---------- step 2: per-registry dry-runs ---------------------------------

def _summary_verdict(summary_path: Path) -> dict[str, Any]:
    """Read summary.json and return the gate-relevant counts."""
    doc = json.loads(summary_path.read_text())
    s = doc.get("summary", {})
    return {
        "sample_size":       s.get("sample_size", 0),
        "new_render_failed": s.get("new_render_failed", -1),
        "new_any_antipattern": s.get("new_any_antipattern", -1),
        "crash_samples":     doc.get("crash_samples", []),
        "antipattern_samples": doc.get("antipattern_samples", []),
    }


def run_dryruns(n_per_reg: int = 50) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for reg in NEW_REGS:
        out_dir = DRYRUN_OUT_BASE / reg
        out_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable, str(DRYRUN_SCRIPT),
            "--n-per-reg", str(n_per_reg),
            "--registries", reg,
            "--out", str(out_dir),
        ]
        log.info("dryrun %s: %s", reg, shlex.join(cmd))
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT))
        summary_path = out_dir / "summary.json"
        if not summary_path.exists():
            raise NeedsApproval(
                f"dryrun for {reg} produced no summary.json (exit={proc.returncode})"
            )
        verdict = _summary_verdict(summary_path)
        verdict["exit_code"] = proc.returncode
        verdict["summary_path"] = str(summary_path)
        results[reg] = verdict
        log.info("dryrun %s verdict: %s", reg, {k: v for k, v in verdict.items()
                                                 if k not in ("crash_samples",
                                                              "antipattern_samples")})
    # Gate
    offenders = [
        reg for reg, v in results.items()
        if v["new_render_failed"] != 0 or v["new_any_antipattern"] != 0
    ]
    if offenders:
        raise NeedsApproval(
            "dryrun gate failed for: "
            + ", ".join(f"{r} (crashes={results[r]['new_render_failed']}, "
                        f"antipatterns={results[r]['new_any_antipattern']})"
                        for r in offenders)
        )
    return results


# ---------- step 3: plist mutation ----------------------------------------

def widen_plist(execute: bool) -> None:
    cmd = [
        PLISTBUDDY, "-c",
        f"Set :EnvironmentVariables:L1_UNLOCK_REGISTRIES {POST_UNLOCK}",
        str(PLIST_PATH),
    ]
    log.info("%s plist set: %s", "EXEC" if execute else "DRY", shlex.join(cmd))
    if execute:
        subprocess.run(cmd, check=True)
        # Verify the write
        readback = _plistbuddy_print("EnvironmentVariables:L1_UNLOCK_REGISTRIES")
        if readback != POST_UNLOCK:
            raise Blocked(
                f"plist set did not persist: readback={readback!r}"
            )
        log.info("plist readback confirmed: %s", readback)


# ---------- step 4: launchctl unload + load -------------------------------

def launchctl_reload(execute: bool) -> None:
    unload = [LAUNCHCTL, "unload", str(PLIST_PATH)]
    load   = [LAUNCHCTL, "load",   str(PLIST_PATH)]
    for cmd in (unload, load):
        log.info("%s launchctl: %s", "EXEC" if execute else "DRY", shlex.join(cmd))
        if execute:
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                log.warning("launchctl %s exit=%d stderr=%s",
                            cmd[1], proc.returncode, proc.stderr.strip())
                if cmd[1] == "load":
                    # load failure is fatal; unload failures can happen if
                    # the agent was already unloaded
                    raise Blocked(f"launchctl load failed: {proc.stderr.strip()}")


# ---------- step 5: health check ------------------------------------------

def wait_for_health(execute: bool, wait_s: int = 30) -> dict[str, Any] | None:
    log.info("%s sleep %ds before health check", "EXEC" if execute else "DRY", wait_s)
    if not execute:
        return None
    time.sleep(wait_s)
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body)
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        raise Blocked(f"health check failed: {type(e).__name__}: {e}")
    if data.get("status") != "ok":
        raise Blocked(f"health check not ok: {data}")
    log.info("health ok: %s", data)
    return data


# ---------- step 6: redis canary purge ------------------------------------

def purge_redis(execute: bool) -> dict[str, Any]:
    env = os.environ.copy()
    env["SMEDJAN_CANARY_REGS"] = ",".join(NEW_REGS)
    if not execute:
        env["SMEDJAN_DRY_RUN"] = "1"
    cmd = [sys.executable, str(PURGE_SCRIPT)]
    log.info("%s redis purge: SMEDJAN_CANARY_REGS=%s %s",
             "EXEC" if execute else "DRY", env["SMEDJAN_CANARY_REGS"], shlex.join(cmd))
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env,
                          capture_output=True, text=True)
    # purge script logs its own counts; return exit_code + tail for the report
    tail = "\n".join(proc.stderr.strip().splitlines()[-5:])
    return {"exit_code": proc.returncode, "stderr_tail": tail}


# ---------- step 7: observation report ------------------------------------

REPORT_SKELETON = """# L1 Wave 2 — Deploy Observation T+0

**Generated:** {ts}
**Deploy T0:** {t0}
**Pre-unlock:** `{pre}`
**Post-unlock:** `{post}`
**New registries this wave:** {new_regs}
**Rollback runbook:** `~/smedjan/runbooks/L1-rollback.md`
**Gradient cadence:** canary_monitor_l1 at 30-min phases (T+0.5h, T+1h, T+1.5h, T+2h, ...)

## Preflight dry-run gate (step 2)

| Registry | Samples | Crashes | Antipatterns | Exit | Summary |
|---|---:|---:|---:|---:|---|
{dryrun_rows}

## Plist mutation (step 3)

- PlistBuddy Set `:EnvironmentVariables:L1_UNLOCK_REGISTRIES` to `{post}`
- Readback verified: {readback_ok}
- Mode: {exec_mode}

## LaunchAgent reload (step 4)

- `launchctl unload {plist}`
- `launchctl load   {plist}`
- Reason for full unload+load: 2026-04-18 incident — kickstart alone does
  not propagate new EnvironmentVariables on macOS 15.

## Post-reload health (step 5)

- Waited {wait_s}s, then `GET {health_url}`
- Response: `{health_resp}`

## Redis canary purge (step 6)

- `SMEDJAN_CANARY_REGS={new_regs_csv}`
- `{purge_script}` exit={purge_exit}
- Tail:

```
{purge_tail}
```

## AI-bot crawls — wave-2 cohort (filled by canary_monitor_l1)

| Window | npm | pypi | crates | total |
|---|---:|---:|---:|---:|
| 12h | _ | _ | _ | _ |
| 24h | _ | _ | _ | _ |
| 7d  | _ | _ | _ | _ |

Baseline (PRE, 7d): npm=_ / pypi=_ / crates=_

## Citations (human visits with AI-platform referrer) — wave-2 cohort

| Window | npm | pypi | crates | total |
|---|---:|---:|---:|---:|
| 12h | _ | _ | _ | _ |
| 24h | _ | _ | _ | _ |
| 7d  | _ | _ | _ | _ |

Baseline (PRE, 7d): npm=_ / pypi=_ / crates=_

## 5xx observed — wave-2 cohort

| Window | npm total | npm 5xx | pypi total | pypi 5xx | crates total | crates 5xx |
|---|---:|---:|---:|---:|---:|---:|
| 12h | _ | _ | _ | _ | _ | _ |
| 24h | _ | _ | _ | _ | _ | _ |

## Whole-site 5xx (12h context)

- Total requests: _
- 5xx count: _
- 5xx rate: _
- PRE-baseline (24h): _

## Next check

- T+0.5h — first gradient phase, halt if npm 5xx > 0 or any registry crash>0
- Rollback: run `~/smedjan/runbooks/L1-rollback.md` (PlistBuddy Set back to `{pre}` + unload/load)
"""


def _dryrun_rows(results: dict[str, dict[str, Any]] | None) -> str:
    if not results:
        return "| npm | _ | _ | _ | _ | _ |\n| pypi | _ | _ | _ | _ | _ |\n| crates | _ | _ | _ | _ | _ |"
    rows = []
    for reg in NEW_REGS:
        r = results.get(reg, {})
        rows.append(
            f"| {reg} | {r.get('sample_size', '_')} | "
            f"{r.get('new_render_failed', '_')} | "
            f"{r.get('new_any_antipattern', '_')} | "
            f"{r.get('exit_code', '_')} | "
            f"`{r.get('summary_path', '_')}` |"
        )
    return "\n".join(rows)


def write_observation(
    t0: datetime,
    dryrun_results: dict[str, dict[str, Any]] | None,
    readback_ok: bool,
    exec_mode: str,
    health_resp: dict[str, Any] | None,
    purge: dict[str, Any] | None,
    wait_s: int,
) -> Path:
    OBS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc)
    path = OBS_DIR / f"L1-wave2-{ts.strftime('%Y%m%dT%H%M%SZ')}.md"
    body = REPORT_SKELETON.format(
        ts=ts.isoformat(),
        t0=t0.isoformat(),
        pre=PRE_UNLOCK,
        post=POST_UNLOCK,
        new_regs=", ".join(NEW_REGS),
        new_regs_csv=",".join(NEW_REGS),
        dryrun_rows=_dryrun_rows(dryrun_results),
        readback_ok="yes" if readback_ok else "no / dry-run",
        exec_mode=exec_mode,
        plist=str(PLIST_PATH),
        wait_s=wait_s,
        health_url=HEALTH_URL,
        health_resp=json.dumps(health_resp) if health_resp else "_ (dry-run)",
        purge_script=str(PURGE_SCRIPT),
        purge_exit=(purge or {}).get("exit_code", "_"),
        purge_tail=(purge or {}).get("stderr_tail", "_ (dry-run)"),
    )
    path.write_text(body)
    log.info("wrote observation report: %s", path)
    return path


# ---------- main ---------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="L1 Wave 2 (npm/pypi/crates) deployment runner. "
                    "Default is --dry-run; pass --execute for production."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                     help="print planned phases, do not mutate plist/launchctl/redis (default)")
    mode.add_argument("--execute", action="store_true", default=False,
                     help="perform the production mutation (plist + launchctl + redis)")
    parser.add_argument("--n-per-reg", type=int, default=50,
                        help="dry-run samples per registry (default 50)")
    parser.add_argument("--skip-preflight", action="store_true",
                        help="skip step 2 dry-runs (use only with prior verified gate)")
    parser.add_argument("--wait-s", type=int, default=30,
                        help="seconds to wait after launchctl reload before health check")
    parser.add_argument("--skeleton-only", action="store_true",
                        help="write an empty observation skeleton and exit "
                             "(for bootstrapping the report location)")
    args = parser.parse_args()

    execute = bool(args.execute)
    exec_mode = "EXECUTE" if execute else "DRY-RUN"
    t0 = datetime.now(timezone.utc)
    log.info("==== L1 Wave 2 deploy runner START (%s) ====", exec_mode)

    if args.skeleton_only:
        path = write_observation(
            t0=t0, dryrun_results=None, readback_ok=False,
            exec_mode=exec_mode, health_resp=None, purge=None,
            wait_s=args.wait_s,
        )
        print(f"skeleton: {path}")
        return 0

    dryrun_results: dict[str, dict[str, Any]] | None = None
    readback_ok = False
    health_resp: dict[str, Any] | None = None
    purge_result: dict[str, Any] | None = None

    try:
        # 1
        verify_precondition()
        # 2
        if args.skip_preflight:
            log.warning("--skip-preflight set: bypassing step 2 dryruns")
        else:
            dryrun_results = run_dryruns(args.n_per_reg)
        # 3
        widen_plist(execute=execute)
        readback_ok = execute
        # 4
        launchctl_reload(execute=execute)
        # 5
        health_resp = wait_for_health(execute=execute, wait_s=args.wait_s)
        # 6
        purge_result = purge_redis(execute=execute)
        # 7
        write_observation(
            t0=t0,
            dryrun_results=dryrun_results,
            readback_ok=readback_ok,
            exec_mode=exec_mode,
            health_resp=health_resp,
            purge=purge_result,
            wait_s=args.wait_s,
        )
    except Blocked as e:
        log.error("BLOCKED: %s", e)
        write_observation(
            t0=t0, dryrun_results=dryrun_results, readback_ok=readback_ok,
            exec_mode=f"{exec_mode} (BLOCKED: {e})",
            health_resp=health_resp, purge=purge_result, wait_s=args.wait_s,
        )
        return 3
    except NeedsApproval as e:
        log.error("NEEDS APPROVAL: %s", e)
        write_observation(
            t0=t0, dryrun_results=dryrun_results, readback_ok=readback_ok,
            exec_mode=f"{exec_mode} (NEEDS_APPROVAL: {e})",
            health_resp=health_resp, purge=purge_result, wait_s=args.wait_s,
        )
        return 4

    log.info("==== L1 Wave 2 deploy runner DONE (%s) ====", exec_mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
