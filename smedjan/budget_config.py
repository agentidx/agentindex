"""Smedjan budget allocation config — loads/updates ~/smedjan/config/budget.toml.

Anders sets two knobs:
  1. `last_observed_weekly_used` — the Max dashboard number at sync time
  2. `smedjan_share_of_remaining` — how much of what's left Smedjan can burn

Everything else is derived:

    remaining_at_sync_pct = 100 - last_observed_weekly_used
    smedjan_allocated_pct = remaining_at_sync_pct * share / 100
    days_to_reset         = (weekly_reset_at - now).days_hours
    safe_daily_pct        = smedjan_allocated_pct / days_to_reset
    claims_since_sync     = count(session_budget stamps > last_observed_at)
    used_since_sync_pct   = claims_since_sync / calibration_factor
    remaining_share_pct   = smedjan_allocated_pct - used_since_sync_pct

Throttle tiers (against share, NOT raw claim count) live in
`session_budget.py`; this module just surfaces the numbers.
"""
from __future__ import annotations

import json
import logging
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CONFIG_PATH = Path.home() / "smedjan" / "config" / "budget.toml"

# Hardcoded defaults if budget.toml missing. Anders will sync on first run.
_DEFAULTS = {
    "smedjan_share_of_remaining": 100,
    "weekly_reset_at": "2026-04-23T21:00:00Z",
    "last_observed_weekly_used": 0,
    "last_observed_at": None,
    "calibration_factor": 15,
}

# Stale-warning: a sync older than this is "stale" and the dashboard
# should flag it (but not refuse to compute — stale data is better than
# none, provided it's labelled).
STALE_AFTER_HOURS = 6

log = logging.getLogger("smedjan.budget_config")


@dataclass
class BudgetConfig:
    smedjan_share_of_remaining: int      # 0-100
    weekly_reset_at: datetime
    last_observed_weekly_used: int       # 0-100
    last_observed_at: datetime | None
    calibration_factor: float


@dataclass
class Allocation:
    remaining_at_sync_pct: float         # 100 - last_observed_weekly_used
    smedjan_allocated_pct: float         # remaining * share/100
    days_to_reset: float
    safe_daily_pct: float
    used_since_sync_pct: float           # claims_since_sync / calibration_factor
    remaining_share_pct: float           # allocated - used_since_sync
    share_fraction_consumed: float       # used_since_sync / allocated (0-1+)
    status: str                          # green | yellow | red | over
    stale_sync: bool                     # last sync older than STALE_AFTER_HOURS


def _parse_ts(raw) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    s = str(raw).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        log.warning("budget: could not parse timestamp %r", raw)
        return None


def load() -> BudgetConfig:
    raw = dict(_DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("rb") as fh:
                data = tomllib.load(fh)
            raw.update(data.get("budget", {}))
        except Exception as e:  # noqa: BLE001
            log.warning("budget: failed to parse %s: %s — using defaults", CONFIG_PATH, e)
    reset = _parse_ts(raw["weekly_reset_at"]) or datetime.now(timezone.utc)
    return BudgetConfig(
        smedjan_share_of_remaining=int(raw["smedjan_share_of_remaining"]),
        weekly_reset_at=reset,
        last_observed_weekly_used=int(raw["last_observed_weekly_used"]),
        last_observed_at=_parse_ts(raw["last_observed_at"]),
        calibration_factor=float(raw["calibration_factor"]),
    )


def save(cfg: BudgetConfig) -> None:
    """Persist BudgetConfig back to TOML. Handwritten — no toml-writer
    dep — keeps format stable for humans to read/edit."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    last_obs = cfg.last_observed_at.astimezone(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    ) if cfg.last_observed_at else ""
    reset = cfg.weekly_reset_at.astimezone(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    content = (
        "# Smedjan budget allocation — Anders sets share of Max weekly.\n"
        "# Updated via `smedjan budget sync` / `smedjan budget share`.\n\n"
        "[budget]\n"
        f"smedjan_share_of_remaining = {cfg.smedjan_share_of_remaining}\n"
        f'weekly_reset_at = "{reset}"\n'
        f"last_observed_weekly_used = {cfg.last_observed_weekly_used}\n"
        f'last_observed_at = "{last_obs}"\n'
        f"calibration_factor = {cfg.calibration_factor:g}\n"
    )
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    import os
    os.replace(tmp, CONFIG_PATH)


def update_sync(weekly_used: int, at: datetime | None = None) -> BudgetConfig:
    """Record a new Max-dashboard observation. Anders calls this from
    the CLI. Resets the claims-since-sync counter implicitly via the
    `last_observed_at` timestamp."""
    at = at or datetime.now(timezone.utc)
    cfg = load()
    cfg.last_observed_weekly_used = max(0, min(100, int(weekly_used)))
    cfg.last_observed_at = at
    save(cfg)
    return cfg


def update_share(share_pct: int) -> BudgetConfig:
    cfg = load()
    cfg.smedjan_share_of_remaining = max(0, min(100, int(share_pct)))
    save(cfg)
    return cfg


def allocation(claims_since_sync: int, now: datetime | None = None) -> tuple[BudgetConfig, Allocation]:
    """Compute the derived allocation numbers. Caller supplies the
    claims-since-sync count from session_budget so we stay decoupled
    from the state file format there."""
    now = now or datetime.now(timezone.utc)
    cfg = load()

    remaining_at_sync = max(0.0, 100.0 - cfg.last_observed_weekly_used)
    allocated = remaining_at_sync * cfg.smedjan_share_of_remaining / 100.0

    days_to_reset = max(
        (cfg.weekly_reset_at - now).total_seconds() / 86400.0,
        1.0 / 24.0,  # floor at 1h to avoid division chaos near reset
    )
    safe_daily = allocated / days_to_reset if allocated > 0 else 0.0

    cf = max(cfg.calibration_factor, 0.001)
    used_since_sync = claims_since_sync / cf

    remaining_share = allocated - used_since_sync
    frac = used_since_sync / allocated if allocated > 0 else 0.0

    if frac < 0.70:
        status = "green"
    elif frac < 0.85:
        status = "yellow"
    elif frac < 1.0:
        status = "red"
    else:
        status = "over"

    stale = False
    if cfg.last_observed_at is not None:
        age_h = (now - cfg.last_observed_at).total_seconds() / 3600.0
        stale = age_h > STALE_AFTER_HOURS

    alloc = Allocation(
        remaining_at_sync_pct=remaining_at_sync,
        smedjan_allocated_pct=allocated,
        days_to_reset=days_to_reset,
        safe_daily_pct=safe_daily,
        used_since_sync_pct=used_since_sync,
        remaining_share_pct=remaining_share,
        share_fraction_consumed=frac,
        status=status,
        stale_sync=stale,
    )
    return cfg, alloc


def as_dict(cfg: BudgetConfig, alloc: Allocation) -> dict:
    """Flat view for dashboard + CLI output."""
    return {
        "share_pct": cfg.smedjan_share_of_remaining,
        "weekly_reset_at": cfg.weekly_reset_at.isoformat(timespec="minutes"),
        "last_observed_weekly_used": cfg.last_observed_weekly_used,
        "last_observed_at": cfg.last_observed_at.isoformat(timespec="minutes") if cfg.last_observed_at else None,
        "calibration_factor": cfg.calibration_factor,
        "remaining_at_sync_pct": round(alloc.remaining_at_sync_pct, 2),
        "smedjan_allocated_pct": round(alloc.smedjan_allocated_pct, 2),
        "days_to_reset": round(alloc.days_to_reset, 2),
        "safe_daily_pct": round(alloc.safe_daily_pct, 2),
        "used_since_sync_pct": round(alloc.used_since_sync_pct, 2),
        "remaining_share_pct": round(alloc.remaining_share_pct, 2),
        "share_fraction_consumed": round(alloc.share_fraction_consumed, 3),
        "status": alloc.status,
        "stale_sync": alloc.stale_sync,
    }
