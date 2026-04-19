#!/usr/bin/env python3
"""Pull Bing WMT page-level impressions/clicks/CTR per page-type.

Daily job (T171). Hits the Bing Webmaster Tools GetPageStats endpoint,
aggregates page URLs into the seven Smedjan page-types, and writes
~/smedjan/measurement/bing-<ymd>.csv with columns:

    page_type, impressions_7d, clicks_7d, ctr_7d

Column names mirror the T170 GSC pull for downstream-tool symmetry.
The Bing WMT API does not accept a custom date range for GetPageStats —
it returns a rolling aggregate (roughly the last six months). Treat the
values as "current Bing visibility", not strictly a 7-day window.

Credentials: ~/.config/smedjan/bing-wmt-key (shared with T156). The
file is either raw API-key text or JSON of the form::

    {"api_key": "...", "site_url": "https://nerq.ai/"}

If the credentials file is absent, exit 0 after logging a BLOCKED line
so a systemd timer keeps firing harmlessly.

Stdlib-only so the smedjan host needs no extra packages.
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

CREDENTIALS_PATH = pathlib.Path.home() / ".config" / "smedjan" / "bing-wmt-key"
OUT_DIR = pathlib.Path.home() / "smedjan" / "measurement"

BING_PAGE_STATS_URL = (
    "https://ssl.bing.com/webmaster/api.svc/json/GetPageStats"
    "?siteUrl={site}&apikey={api_key}"
)
DEFAULT_SITE_URL = "https://nerq.ai/"

PAGE_TYPES = (
    "/safe",
    "/compare",
    "/best",
    "/alternatives",
    "/crypto/token",
    "/review",
    "/privacy",
)


def _log_path(today: _dt.date) -> pathlib.Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUT_DIR / f"bing-pull-{today:%Y%m%d}.log"


def _log(today: _dt.date, line: str) -> None:
    ts = _dt.datetime.now().isoformat(timespec="seconds")
    entry = f"{ts} {line}\n"
    with _log_path(today).open("a", encoding="utf-8") as fh:
        fh.write(entry)
    sys.stdout.write(entry)


def _load_credentials() -> tuple[str, str]:
    raw = CREDENTIALS_PATH.read_text().strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw, DEFAULT_SITE_URL
    api_key = payload.get("api_key") or payload.get("apikey")
    if not api_key:
        raise KeyError("api_key missing in bing-wmt-key")
    site_url = payload.get("site_url") or DEFAULT_SITE_URL
    return api_key, site_url


def _fetch_page_stats(site_url: str, api_key: str) -> list[dict]:
    url = BING_PAGE_STATS_URL.format(
        site=urllib.parse.quote(site_url, safe=""),
        api_key=urllib.parse.quote(api_key, safe=""),
    )
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode())
    return payload.get("d") or []


def _classify(page_url: str) -> str | None:
    try:
        path = urllib.parse.urlparse(page_url).path
    except ValueError:
        return None
    for prefix in sorted(PAGE_TYPES, key=len, reverse=True):
        if path == prefix or path.startswith(prefix + "/"):
            return prefix
    return None


def _aggregate(rows: list[dict]) -> dict[str, dict[str, int]]:
    buckets: dict[str, dict[str, int]] = {
        p: {"impressions": 0, "clicks": 0} for p in PAGE_TYPES
    }
    for row in rows:
        page_url = row.get("Page") or row.get("page")
        if not page_url:
            continue
        bucket = _classify(page_url)
        if bucket is None:
            continue
        buckets[bucket]["impressions"] += int(row.get("Impressions", 0) or 0)
        buckets[bucket]["clicks"] += int(row.get("Clicks", 0) or 0)
    return buckets


def _write_csv(buckets: dict[str, dict[str, int]], out_path: pathlib.Path) -> None:
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["page_type", "impressions_7d", "clicks_7d", "ctr_7d"])
        for page_type in PAGE_TYPES:
            bkt = buckets[page_type]
            imp = int(bkt["impressions"])
            clk = int(bkt["clicks"])
            ctr = (clk / imp) if imp else 0.0
            w.writerow([page_type, imp, clk, f"{ctr:.6f}"])


def main() -> int:
    today = _dt.date.today()

    if not CREDENTIALS_PATH.exists():
        _log(
            today,
            "BLOCKED credentials-missing path="
            f"{CREDENTIALS_PATH} note='Bing WMT key missing — "
            "see runbooks/bing-setup.md'",
        )
        return 0

    try:
        api_key, site_url = _load_credentials()
    except (OSError, KeyError) as exc:
        _log(today, f"ERROR credentials-load-failed err={exc}")
        return 2

    try:
        rows = _fetch_page_stats(site_url, api_key)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:200]
        _log(today, f"ERROR pagestats-http status={exc.code} body={body!r}")
        return 2
    except urllib.error.URLError as exc:
        _log(today, f"ERROR pagestats-net err={exc}")
        return 2

    buckets = _aggregate(rows)
    out_path = OUT_DIR / f"bing-{today:%Y%m%d}.csv"
    _write_csv(buckets, out_path)

    totals_imp = sum(int(b["impressions"]) for b in buckets.values())
    totals_clk = sum(int(b["clicks"]) for b in buckets.values())
    _log(
        today,
        f"OK rows={len(rows)} bucketed_impressions={totals_imp} "
        f"bucketed_clicks={totals_clk} site={site_url} out={out_path}",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
