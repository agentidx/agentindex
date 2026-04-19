"""health_dashboard.py — single-page HTML dashboard for the Smedjan factory.

Renders a self-contained ``index.html`` with:

    * workers         — heartbeat freshness, current task, tasks-done last 24h
    * queue depth     — row count per task status
    * recent tasks    — last 20 terminal rows (done/blocked/needs_approval)
                        with id, status, duration, output_paths
    * canary status   — newest L1 canary observation + 5xx / write-rate
                        headline metrics pulled from the JSONL log

The file is designed to be opened directly from disk — no server, no JS,
no network calls once rendered. Meant to be refreshed by a systemd timer
(``health-dashboard.timer``) every 15 minutes on the smedjan host; on
Mac Studio the same script runs fine and produces the same artefact at
``~/smedjan/measurement/health/index.html``.

Usage
-----
    python3 -m smedjan.scripts.health_dashboard
    python3 -m smedjan.scripts.health_dashboard --out /tmp/health.html

Exit codes: 0 success, 1 DB unreachable (partial HTML written with an
error banner so operators still see *something* in the browser).
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from smedjan import sources

log = logging.getLogger("smedjan.health_dashboard")

DEFAULT_OUT = Path.home() / "smedjan" / "measurement" / "health" / "index.html"
CANARY_JSONL = Path.home() / "smedjan" / "observations" / "L1-canary-observations.jsonl"

HEARTBEAT_FRESH_SEC = 120          # green dot if < 2 min
HEARTBEAT_WARN_SEC  = 600          # yellow dot if < 10 min; red otherwise
RECENT_TASK_LIMIT   = 20


# ── data gathering ───────────────────────────────────────────────────────

def _fetch_workers(cur) -> list[dict]:
    cur.execute(
        """
        SELECT h.worker_id,
               h.last_seen_at,
               h.current_task,
               h.note,
               EXTRACT(EPOCH FROM (now() - h.last_seen_at)) AS age_sec,
               (
                 SELECT count(*) FROM smedjan.tasks t
                 WHERE t.claimed_by = h.worker_id
                   AND t.done_at >= now() - interval '24 hours'
               ) AS done_24h
          FROM smedjan.worker_heartbeats h
         ORDER BY h.last_seen_at DESC
        """
    )
    return [dict(r) for r in cur.fetchall()]


def _fetch_queue_depth(cur) -> dict[str, int]:
    cur.execute(
        "SELECT status::text AS status, count(*) AS n "
        "FROM smedjan.tasks GROUP BY status"
    )
    return {r["status"]: int(r["n"]) for r in cur.fetchall()}


def _fetch_recent_tasks(cur) -> list[dict]:
    cur.execute(
        """
        SELECT id,
               title,
               status::text AS status,
               claimed_by,
               claimed_at,
               done_at,
               output_paths,
               CASE
                 WHEN claimed_at IS NOT NULL AND done_at IS NOT NULL
                   THEN EXTRACT(EPOCH FROM (done_at - claimed_at))
                 ELSE NULL
               END AS duration_sec,
               COALESCE(done_at, updated_at) AS ended_at
          FROM smedjan.tasks
         WHERE status IN ('done', 'blocked', 'needs_approval')
         ORDER BY COALESCE(done_at, updated_at) DESC NULLS LAST
         LIMIT %s
        """,
        (RECENT_TASK_LIMIT,),
    )
    return [dict(r) for r in cur.fetchall()]


def _read_last_canary_obs() -> dict | None:
    if not CANARY_JSONL.exists():
        return None
    try:
        last = None
        with CANARY_JSONL.open() as fh:
            for line in fh:
                line = line.strip()
                if line:
                    last = line
        if not last:
            return None
        return json.loads(last)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("could not parse canary jsonl: %s", exc)
        return None


# ── rendering ────────────────────────────────────────────────────────────

CSS = """
:root {
  --bg: #111418; --fg: #e8ecef; --mut: #8a94a0; --card: #1a1e24;
  --ok: #6cc24a; --warn: #e7b04a; --bad: #e05a5a; --acc: #c2956b;
  --border: #2a2f36;
}
* { box-sizing: border-box; }
body { font: 13px/1.5 -apple-system, BlinkMacSystemFont, "JetBrains Mono", monospace;
       margin: 0; background: var(--bg); color: var(--fg); padding: 24px; }
h1 { font: 600 22px/1.2 "DM Serif Display", serif; margin: 0 0 4px; color: var(--acc); }
h2 { font-size: 14px; text-transform: uppercase; letter-spacing: 0.08em;
     color: var(--mut); margin: 24px 0 8px; }
.meta { color: var(--mut); font-size: 12px; margin-bottom: 16px; }
.banner { background: #3a1f1f; color: #ffcccc; padding: 10px 14px;
          border-radius: 4px; margin-bottom: 16px; }
.grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 6px;
        padding: 12px 14px; }
.card .label { color: var(--mut); font-size: 11px; text-transform: uppercase;
               letter-spacing: 0.05em; }
.card .value { font-size: 22px; font-weight: 600; color: var(--fg); margin-top: 2px; }
.card .sub { color: var(--mut); font-size: 11px; margin-top: 2px; }
table { width: 100%; border-collapse: collapse; background: var(--card);
        border: 1px solid var(--border); border-radius: 6px; overflow: hidden;
        font-size: 12px; }
th, td { padding: 7px 10px; text-align: left; border-bottom: 1px solid var(--border);
         vertical-align: top; }
th { background: #1f242b; color: var(--mut); font-weight: 500;
     text-transform: uppercase; font-size: 10px; letter-spacing: 0.06em; }
tr:last-child td { border-bottom: none; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
       margin-right: 6px; vertical-align: middle; }
.dot-ok   { background: var(--ok); }
.dot-warn { background: var(--warn); }
.dot-bad  { background: var(--bad); }
.mono { font-family: "JetBrains Mono", ui-monospace, monospace; }
.badge { display: inline-block; padding: 1px 6px; border-radius: 3px;
         font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em;
         background: var(--border); color: var(--fg); }
.badge-done  { background: #1e3a22; color: #a8dca8; }
.badge-blocked { background: #3a1f1f; color: #f3b4b4; }
.badge-needs_approval { background: #3a311e; color: #eed28a; }
.badge-in_progress { background: #1e2a3a; color: #a8c5ec; }
.badge-queued { background: #2a2a3a; color: #c5c5e0; }
.badge-pending { background: #2f2f2f; color: #c0c0c0; }
.badge-approved { background: #1e3a34; color: #a8ecd6; }
.truncate { max-width: 320px; overflow: hidden; text-overflow: ellipsis;
            white-space: nowrap; display: inline-block; vertical-align: bottom; }
footer { color: var(--mut); font-size: 11px; margin-top: 28px; }
"""


def _dot_for_age(age_sec: float | None) -> str:
    if age_sec is None:
        return '<span class="dot dot-bad"></span>'
    if age_sec < HEARTBEAT_FRESH_SEC:
        return '<span class="dot dot-ok"></span>'
    if age_sec < HEARTBEAT_WARN_SEC:
        return '<span class="dot dot-warn"></span>'
    return '<span class="dot dot-bad"></span>'


def _fmt_age(age_sec: float | None) -> str:
    if age_sec is None:
        return "—"
    age_sec = float(age_sec)
    if age_sec < 60:
        return f"{int(age_sec)}s ago"
    if age_sec < 3600:
        return f"{int(age_sec / 60)}m ago"
    if age_sec < 86400:
        return f"{age_sec / 3600:.1f}h ago"
    return f"{age_sec / 86400:.1f}d ago"


def _fmt_duration(sec: float | None) -> str:
    if sec is None:
        return "—"
    sec = float(sec)
    if sec < 60:
        return f"{sec:.1f}s"
    if sec < 3600:
        return f"{int(sec // 60)}m{int(sec % 60):02d}s"
    return f"{sec / 3600:.1f}h"


def _fmt_ts(ts: datetime | None) -> str:
    if ts is None:
        return "—"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _canary_headlines(obs: dict | None) -> list[tuple[str, str, str]]:
    """Return [(label, value, sub)] tuples for the canary cards."""
    if not obs:
        return [("canary", "no data", f"missing {CANARY_JSONL.name}")]
    try:
        ts = obs.get("ts", "—")
        inner = obs.get("obs", {})
        w_total = inner.get("whole_12h_total")
        w_5xx = inner.get("whole_12h_5xx")
        write_rate = None
        if isinstance(w_total, (int, float)) and w_total:
            write_rate = w_total / 12.0  # per-hour proxy
        cards: list[tuple[str, str, str]] = []
        cards.append(("last observation", str(ts), "L1 canary JSONL tail"))
        cards.append((
            "12h 5xx (whole)",
            f"{w_5xx}" if w_5xx is not None else "—",
            f"of {w_total:,} total" if isinstance(w_total, int) else "",
        ))
        cards.append((
            "write rate proxy",
            f"{write_rate:,.0f}/h" if write_rate else "—",
            "requests / hour (12h avg)",
        ))
        ai_bot_24h = inner.get("ai_bot", {}).get("24h", {})
        if ai_bot_24h:
            parts = ", ".join(f"{k}={v}" for k, v in sorted(ai_bot_24h.items()))
            cards.append(("ai-bot hits (24h)", parts, "per canary slug"))
        return cards
    except Exception as exc:  # noqa: BLE001 — dashboard must not crash
        log.warning("canary parse failed: %s", exc)
        return [("canary", "parse error", str(exc))]


def _render_workers(workers: list[dict]) -> str:
    if not workers:
        return "<p class='meta'>No heartbeats recorded yet.</p>"
    rows = []
    for w in workers:
        rows.append(
            "<tr>"
            f"<td>{_dot_for_age(w['age_sec'])}<span class='mono'>{html.escape(w['worker_id'])}</span></td>"
            f"<td>{_fmt_age(w['age_sec'])}</td>"
            f"<td class='mono'>{html.escape(w['current_task'] or '—')}</td>"
            f"<td>{html.escape(w['note'] or '')}</td>"
            f"<td>{int(w['done_24h'] or 0)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>worker</th><th>heartbeat</th><th>current task</th>"
        "<th>note</th><th>done 24h</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _render_queue(depth: dict[str, int]) -> str:
    order = ["pending", "queued", "needs_approval", "approved",
             "in_progress", "done", "blocked"]
    cards = []
    for status in order:
        n = depth.get(status, 0)
        cards.append(
            "<div class='card'>"
            f"<div class='label'>{status}</div>"
            f"<div class='value'>{n}</div>"
            "</div>"
        )
    # Render any unknown statuses we haven't hardcoded.
    for status, n in depth.items():
        if status not in order:
            cards.append(
                "<div class='card'>"
                f"<div class='label'>{html.escape(status)}</div>"
                f"<div class='value'>{n}</div>"
                "</div>"
            )
    return "<div class='grid'>" + "".join(cards) + "</div>"


def _render_recent(recent: list[dict]) -> str:
    if not recent:
        return "<p class='meta'>No recent tasks.</p>"
    rows = []
    for t in recent:
        outs = t.get("output_paths") or []
        outs_str = ", ".join(outs) if outs else "—"
        outs_html = html.escape(outs_str)
        rows.append(
            "<tr>"
            f"<td class='mono'>{html.escape(t['id'])}</td>"
            f"<td><span class='badge badge-{html.escape(t['status'])}'>{html.escape(t['status'])}</span></td>"
            f"<td class='mono'>{_fmt_duration(t['duration_sec'])}</td>"
            f"<td>{_fmt_ts(t.get('ended_at'))}</td>"
            f"<td title='{outs_html}'><span class='truncate mono'>{outs_html}</span></td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>id</th><th>status</th><th>duration</th>"
        "<th>ended</th><th>output paths</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _render_canary(obs: dict | None) -> str:
    cards = _canary_headlines(obs)
    chunks = []
    for label, value, sub in cards:
        chunks.append(
            "<div class='card'>"
            f"<div class='label'>{html.escape(label)}</div>"
            f"<div class='value mono'>{html.escape(value)}</div>"
            f"<div class='sub'>{html.escape(sub)}</div>"
            "</div>"
        )
    return "<div class='grid'>" + "".join(chunks) + "</div>"


def render_html(
    workers: list[dict],
    queue: dict[str, int],
    recent: list[dict],
    canary: dict | None,
    error: str | None = None,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    banner = f"<div class='banner'>{html.escape(error)}</div>" if error else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="900">
<title>Smedjan factory health</title>
<style>{CSS}</style>
</head>
<body>
<h1>Smedjan factory health</h1>
<p class="meta">Generated {now} · auto-refresh 15 min</p>
{banner}
<h2>Workers</h2>
{_render_workers(workers)}
<h2>Queue depth</h2>
{_render_queue(queue)}
<h2>Recent tasks (last {RECENT_TASK_LIMIT})</h2>
{_render_recent(recent)}
<h2>Canary status</h2>
{_render_canary(canary)}
<footer>smedjan.scripts.health_dashboard · index at {html.escape(str(DEFAULT_OUT))}</footer>
</body>
</html>
"""


# ── main ─────────────────────────────────────────────────────────────────

def generate(out_path: Path) -> int:
    workers: list[dict] = []
    queue: dict[str, int] = {}
    recent: list[dict] = []
    error: str | None = None
    try:
        with sources.smedjan_db_cursor(dict_cursor=True) as (_, cur):
            workers = _fetch_workers(cur)
            queue = _fetch_queue_depth(cur)
            recent = _fetch_recent_tasks(cur)
    except Exception as exc:  # noqa: BLE001 — render partial, do not crash the timer
        error = f"Smedjan DB unreachable: {exc}"
        log.error(error)

    canary = _read_last_canary_obs()
    html_text = render_html(workers, queue, recent, canary, error=error)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(html_text, encoding="utf-8")
    os.replace(tmp, out_path)
    log.info("wrote %s (%d workers, %d statuses, %d recent tasks)",
             out_path, len(workers), len(queue), len(recent))
    return 1 if error else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Render Smedjan factory health dashboard")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT,
                   help=f"output HTML path (default {DEFAULT_OUT})")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return generate(args.out)


if __name__ == "__main__":
    sys.exit(main())
