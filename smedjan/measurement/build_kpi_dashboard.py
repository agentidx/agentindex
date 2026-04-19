#!/usr/bin/env python3
"""Render the Stage-1 Trinity KPI dashboard (T173).

Joins three signals into a single static HTML page served from file://:

    Traffic (GSC impressions/clicks per page-type, T170)
        ×
    CTR (clicks ÷ impressions, derived in same CSV)
        ×
    RPC-proxy (avg_cpc_usd from smedjan.monetization_tiers, T003)

Output: ~/smedjan/measurement/kpi/index.html

A "vertical" is one row of smedjan.monetization_tiers — i.e. one
(path_pattern, tier, CPC) triple. There are 98 of them today so the
≥10-verticals acceptance is met by construction.

The script is deliberately resilient: if no GSC CSV has been produced
yet (T170 is blocked on credentials at time of writing), the dashboard
still renders with a banner explaining the gap and zero-traffic rows.
That way the daily timer can keep firing harmlessly.
"""

from __future__ import annotations

import csv
import datetime as _dt
import html
import logging
import pathlib
import sys

from smedjan import sources

log = logging.getLogger("smedjan.measurement.build_kpi_dashboard")

OUT_DIR = pathlib.Path.home() / "smedjan" / "measurement" / "kpi"
GSC_DIR = pathlib.Path.home() / "smedjan" / "measurement"

# Mirrors scripts/pull_gsc_daily.py — keep in sync if T170 grows new buckets.
PAGE_TYPES = (
    "/safe",
    "/compare",
    "/best",
    "/alternatives",
    "/crypto/token",
    "/review",
    "/privacy",
)


def _classify(path_pattern: str) -> str | None:
    """Map a monetization_tiers path_pattern to its T170 page_type bucket.

    Longest-prefix wins so '/crypto/token/{slug}' lands in '/crypto/token'
    rather than nowhere (there is no '/crypto' bucket in T170).
    """
    for prefix in sorted(PAGE_TYPES, key=len, reverse=True):
        if path_pattern == prefix or path_pattern.startswith(prefix + "/"):
            return prefix
    return None


def _latest_gsc_csv() -> pathlib.Path | None:
    if not GSC_DIR.exists():
        return None
    candidates = sorted(GSC_DIR.glob("gsc-*.csv"))
    return candidates[-1] if candidates else None


def _read_gsc(csv_path: pathlib.Path) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            out[row["page_type"]] = {
                "impressions_7d": int(row["impressions_7d"] or 0),
                "clicks_7d": int(row["clicks_7d"] or 0),
                "ctr_7d": float(row["ctr_7d"] or 0.0),
            }
    return out


def _fetch_tiers() -> list[dict]:
    with sources.smedjan_db_cursor(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT path_pattern, tier, avg_cpc_usd::float AS avg_cpc_usd, rationale
              FROM smedjan.monetization_tiers
            """
        )
        return [dict(r) for r in cur.fetchall()]


def _build_rows(
    tiers: list[dict], gsc: dict[str, dict[str, float]]
) -> list[dict]:
    rows: list[dict] = []
    empty = {"impressions_7d": 0, "clicks_7d": 0, "ctr_7d": 0.0}
    for t in tiers:
        page_type = _classify(t["path_pattern"]) or ""
        traffic = gsc.get(page_type, empty)
        cpc = t["avg_cpc_usd"] or 0.0
        clicks = traffic["clicks_7d"]
        rows.append(
            {
                "path_pattern": t["path_pattern"],
                "tier": t["tier"],
                "page_type": page_type or "—",
                "avg_cpc_usd": cpc,
                "impressions_7d": traffic["impressions_7d"],
                "clicks_7d": clicks,
                "ctr_7d": traffic["ctr_7d"],
                "est_weekly_rev_usd": clicks * cpc,
            }
        )
    rows.sort(
        key=lambda r: (r["est_weekly_rev_usd"], r["avg_cpc_usd"]), reverse=True
    )
    return rows


def _summary_by_page_type(rows: list[dict]) -> list[dict]:
    bucket: dict[str, dict] = {}
    for r in rows:
        pt = r["page_type"]
        b = bucket.setdefault(
            pt,
            {
                "page_type": pt,
                "patterns": 0,
                "impressions_7d": r["impressions_7d"],
                "clicks_7d": r["clicks_7d"],
                "ctr_7d": r["ctr_7d"],
                "max_cpc_usd": 0.0,
                "tiers": set(),
            },
        )
        b["patterns"] += 1
        b["max_cpc_usd"] = max(b["max_cpc_usd"], r["avg_cpc_usd"])
        b["tiers"].add(r["tier"])
    out = []
    for b in bucket.values():
        b["tiers"] = ",".join(sorted(b["tiers"]))
        b["est_weekly_rev_usd"] = b["clicks_7d"] * b["max_cpc_usd"]
        out.append(b)
    out.sort(key=lambda r: r["est_weekly_rev_usd"], reverse=True)
    return out


def _fmt_pct(v: float) -> str:
    return f"{v * 100:.2f}%"


def _fmt_money(v: float) -> str:
    return f"${v:,.2f}"


def _fmt_int(v: int) -> str:
    return f"{v:,}"


CSS = """
:root {
  --bg: #0f1115;
  --panel: #161a22;
  --border: #232a36;
  --text: #e6e6e6;
  --muted: #8a93a3;
  --warm: #c2956b;
  --t1: #d97757;
  --t2: #c2956b;
  --t3: #6b7d92;
  --good: #6ec47a;
  --warn: #d3a44b;
  --bad:  #cd5c5c;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif;
  font-size: 14px;
  line-height: 1.5;
}
header {
  padding: 24px 32px 12px;
  border-bottom: 1px solid var(--border);
}
h1 {
  margin: 0 0 4px;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.subtitle { color: var(--muted); font-size: 13px; }
.banner {
  margin: 16px 32px 0;
  padding: 12px 16px;
  background: rgba(211, 164, 75, 0.08);
  border: 1px solid rgba(211, 164, 75, 0.4);
  border-radius: 6px;
  color: var(--warn);
  font-size: 13px;
}
.banner.ok { background: rgba(110, 196, 122, 0.06); border-color: rgba(110, 196, 122, 0.4); color: var(--good); }
section { padding: 16px 32px 28px; }
h2 {
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
  font-weight: 600;
  margin: 0 0 12px;
}
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  font-variant-numeric: tabular-nums;
}
th, td {
  padding: 10px 14px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}
th { color: var(--muted); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; background: rgba(255,255,255,0.02); }
td.num, th.num { text-align: right; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: rgba(255,255,255,0.02); }
.tier {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}
.tier.T1 { background: rgba(217,119,87,0.15); color: var(--t1); border: 1px solid rgba(217,119,87,0.4); }
.tier.T2 { background: rgba(194,149,107,0.15); color: var(--t2); border: 1px solid rgba(194,149,107,0.4); }
.tier.T3 { background: rgba(107,125,146,0.15); color: var(--t3); border: 1px solid rgba(107,125,146,0.4); }
.muted { color: var(--muted); }
footer { padding: 16px 32px 32px; color: var(--muted); font-size: 12px; }
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin: 16px 32px;
}
.kpi-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
}
.kpi-card .label { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; }
.kpi-card .value { font-size: 22px; font-weight: 600; margin-top: 4px; }
.kpi-card .sub { color: var(--muted); font-size: 12px; margin-top: 2px; }
"""


def _render(
    rows: list[dict],
    summary: list[dict],
    gsc_path: pathlib.Path | None,
    generated_at: _dt.datetime,
) -> str:
    total_impr = sum(r["impressions_7d"] for r in summary)
    total_clk = sum(r["clicks_7d"] for r in summary)
    total_ctr = (total_clk / total_impr) if total_impr else 0.0
    total_rev = sum(r["est_weekly_rev_usd"] for r in summary)
    n_verticals = len(rows)

    if gsc_path is None:
        banner = (
            '<div class="banner">⚠ No GSC CSV found in '
            f"{html.escape(str(GSC_DIR))} yet — T170 is blocked on missing "
            "Search Console credentials. Traffic and CTR columns will read 0 "
            "until <code>~/.config/smedjan/gsc-credentials.json</code> "
            "is dropped in place.</div>"
        )
    else:
        banner = (
            '<div class="banner ok">✓ GSC source: '
            f"<code>{html.escape(gsc_path.name)}</code></div>"
        )

    head = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Smedjan KPI · Trinity Stage 1</title>
<meta name="generator" content="smedjan.measurement.build_kpi_dashboard">
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>Smedjan KPI · Stage-1 Trinity</h1>
  <div class="subtitle">Trafik × CTR × RPC-proxy · generated {generated_at:%Y-%m-%d %H:%M %Z}</div>
</header>
{banner}
<div class="kpi-grid">
  <div class="kpi-card">
    <div class="label">Verticals tracked</div>
    <div class="value">{_fmt_int(n_verticals)}</div>
    <div class="sub">path patterns × tier × CPC</div>
  </div>
  <div class="kpi-card">
    <div class="label">Impressions (7d)</div>
    <div class="value">{_fmt_int(total_impr)}</div>
    <div class="sub">aggregated across page-types</div>
  </div>
  <div class="kpi-card">
    <div class="label">Clicks (7d)</div>
    <div class="value">{_fmt_int(total_clk)}</div>
    <div class="sub">CTR {_fmt_pct(total_ctr)}</div>
  </div>
  <div class="kpi-card">
    <div class="label">Est. weekly revenue (proxy)</div>
    <div class="value">{_fmt_money(total_rev)}</div>
    <div class="sub">clicks × max CPC per page-type</div>
  </div>
</div>
"""

    summary_rows = "\n".join(
        f"<tr>"
        f"<td><code>{html.escape(r['page_type'])}</code></td>"
        f"<td>{html.escape(r['tiers'])}</td>"
        f"<td class='num'>{_fmt_int(r['patterns'])}</td>"
        f"<td class='num'>{_fmt_int(r['impressions_7d'])}</td>"
        f"<td class='num'>{_fmt_int(r['clicks_7d'])}</td>"
        f"<td class='num'>{_fmt_pct(r['ctr_7d'])}</td>"
        f"<td class='num'>{_fmt_money(r['max_cpc_usd'])}</td>"
        f"<td class='num'>{_fmt_money(r['est_weekly_rev_usd'])}</td>"
        f"</tr>"
        for r in summary
    )
    summary_block = f"""
<section>
  <h2>Page-type summary</h2>
  <table>
    <thead><tr>
      <th>Page-type</th><th>Tiers</th>
      <th class="num">Patterns</th>
      <th class="num">Impr 7d</th><th class="num">Clicks 7d</th>
      <th class="num">CTR 7d</th><th class="num">Top CPC</th>
      <th class="num">Est. wk rev</th>
    </tr></thead>
    <tbody>{summary_rows}</tbody>
  </table>
</section>
"""

    detail_rows = "\n".join(
        f"<tr>"
        f"<td><code>{html.escape(r['path_pattern'])}</code></td>"
        f"<td><span class='tier {r['tier']}'>{r['tier']}</span></td>"
        f"<td class='muted'>{html.escape(r['page_type'])}</td>"
        f"<td class='num'>{_fmt_money(r['avg_cpc_usd'])}</td>"
        f"<td class='num'>{_fmt_int(r['impressions_7d'])}</td>"
        f"<td class='num'>{_fmt_int(r['clicks_7d'])}</td>"
        f"<td class='num'>{_fmt_pct(r['ctr_7d'])}</td>"
        f"<td class='num'>{_fmt_money(r['est_weekly_rev_usd'])}</td>"
        f"</tr>"
        for r in rows
    )
    detail_block = f"""
<section>
  <h2>Verticals · {_fmt_int(len(rows))} rows</h2>
  <table>
    <thead><tr>
      <th>Path pattern</th><th>Tier</th><th>Page-type</th>
      <th class="num">CPC (RPC proxy)</th>
      <th class="num">Impr 7d</th><th class="num">Clicks 7d</th>
      <th class="num">CTR 7d</th>
      <th class="num">Est. wk rev</th>
    </tr></thead>
    <tbody>{detail_rows}</tbody>
  </table>
</section>
"""

    foot = (
        "<footer>Sources: smedjan.monetization_tiers (T003) · "
        "~/smedjan/measurement/gsc-&lt;ymd&gt;.csv (T170). "
        "Estimated weekly revenue is a proxy: page-type clicks × pattern CPC "
        "(or × top CPC for the page-type summary). It is NOT measured revenue."
        "</footer></body></html>"
    )
    return head + summary_block + detail_block + foot


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        tiers = _fetch_tiers()
    except sources.SourceUnavailable as exc:
        log.error("BLOCKED smedjan-db-unreachable err=%s", exc)
        return 2

    gsc_path = _latest_gsc_csv()
    gsc = _read_gsc(gsc_path) if gsc_path else {}

    rows = _build_rows(tiers, gsc)
    summary = _summary_by_page_type(rows)

    html_doc = _render(rows, summary, gsc_path, _dt.datetime.now())
    out = OUT_DIR / "index.html"
    out.write_text(html_doc, encoding="utf-8")
    log.info(
        "OK verticals=%d page_types=%d gsc=%s out=%s",
        len(rows),
        len(summary),
        gsc_path.name if gsc_path else "missing",
        out,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
