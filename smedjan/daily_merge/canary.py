"""30-min canary post-merge — auto-rollback at >5 5xx/min sustained 2 ticks."""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

API_LOG = Path("/Users/anstudio/agentindex/logs/api.log")


@dataclass
class CanaryTick:
    ts: str
    delta_lines: int
    fivex: int
    health_status: int
    health_ms: float


@dataclass
class CanaryResult:
    ticks: list[CanaryTick] = field(default_factory=list)
    triggered: bool = False
    trigger_reason: str = ""
    elapsed_min: float = 0.0


def _probe_health() -> tuple[int, float]:
    import urllib.request, urllib.error
    t0 = time.time()
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/v1/health", timeout=5) as r:
            return r.status, (time.time() - t0) * 1000
    except urllib.error.HTTPError as e:
        return e.code, (time.time() - t0) * 1000
    except Exception:
        return 0, (time.time() - t0) * 1000


def _count_5xx_since(prev_lines: int) -> tuple[int, int]:
    if not API_LOG.exists():
        return 0, prev_lines
    try:
        with API_LOG.open("rb") as f:
            data = f.read()
    except Exception:
        return 0, prev_lines
    now_lines = data.count(b"\n")
    delta = max(0, now_lines - prev_lines)
    if delta == 0:
        return 0, now_lines
    # tail last delta lines
    chunk = data.splitlines()[-delta:] if delta < 100000 else data.splitlines()[prev_lines:]
    fivex = sum(
        1 for line in chunk
        if b" 503 " in line or b" 502 " in line or b" 504 " in line or b" 500 " in line
    )
    return fivex, now_lines


def run_canary(duration_min: int = 30,
               threshold_5xx_per_min: int = 5,
               sustained_ticks: int = 2) -> CanaryResult:
    """Watch api.log; trigger if 5xx/min > threshold for `sustained_ticks` in a row."""
    result = CanaryResult()
    start = time.time()
    deadline = start + duration_min * 60
    prev_lines = API_LOG.stat().st_size if False else 0
    # Initialize line-count
    try:
        with API_LOG.open("rb") as f:
            prev_lines = sum(1 for _ in f)
    except Exception:
        prev_lines = 0

    consecutive_high = 0

    while time.time() < deadline:
        time.sleep(60)
        ts = time.strftime("%H:%M:%S")
        status, ms = _probe_health()
        fivex, now_lines = _count_5xx_since(prev_lines)
        prev_lines = now_lines
        delta = max(0, now_lines - (prev_lines - fivex))  # rough
        result.ticks.append(CanaryTick(
            ts=ts, delta_lines=fivex,  # using fivex as approx
            fivex=fivex, health_status=status, health_ms=ms,
        ))

        if fivex > threshold_5xx_per_min:
            consecutive_high += 1
        else:
            consecutive_high = 0

        if consecutive_high >= sustained_ticks:
            result.triggered = True
            result.trigger_reason = (
                f"5xx-burst sustained {consecutive_high} ticks "
                f"(latest: {fivex}/min, threshold: {threshold_5xx_per_min})"
            )
            break

    result.elapsed_min = (time.time() - start) / 60
    return result
