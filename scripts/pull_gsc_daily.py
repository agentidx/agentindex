#!/usr/bin/env python3
"""Pull 7-day GSC impressions/clicks/CTR per page-type.

Daily job (T170). Hits the Search Console searchAnalytics/query endpoint
with a 7-day rolling window (endDate = today − 3d to respect the usual
GSC data-lag), aggregates page URLs into the seven Smedjan page-types,
and writes ~/smedjan/measurement/gsc-<ymd>.csv with columns:

    page_type, impressions_7d, clicks_7d, ctr_7d

Reuses the OAuth2 refresh-token credentials dropped in place for T150
(~/.config/smedjan/gsc-credentials.json). Stdlib-only so the smedjan
host does not need google-api-python-client.

If the credentials file is absent, exit 0 after writing a BLOCKED log
line — a systemd timer can keep firing harmlessly.
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

CREDENTIALS_PATH = pathlib.Path.home() / ".config" / "smedjan" / "gsc-credentials.json"
OUT_DIR = pathlib.Path.home() / "smedjan" / "measurement"

OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
SEARCH_ANALYTICS_URL = (
    "https://www.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"
)

PAGE_TYPES = (
    "/safe",
    "/compare",
    "/best",
    "/alternatives",
    "/crypto/token",
    "/review",
    "/privacy",
)

ROW_LIMIT = 25000
GSC_LAG_DAYS = 3
WINDOW_DAYS = 7


def _log_path(today: _dt.date) -> pathlib.Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUT_DIR / f"gsc-pull-{today:%Y%m%d}.log"


def _log(today: _dt.date, line: str) -> None:
    ts = _dt.datetime.now().isoformat(timespec="seconds")
    entry = f"{ts} {line}\n"
    with _log_path(today).open("a", encoding="utf-8") as fh:
        fh.write(entry)
    sys.stdout.write(entry)


def _refresh_access_token(creds: dict) -> str:
    body = urllib.parse.urlencode(
        {
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "refresh_token": creds["refresh_token"],
            "grant_type": "refresh_token",
        }
    ).encode()
    req = urllib.request.Request(OAUTH_TOKEN_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    return payload["access_token"]


def _query_page_bucket(
    site_url: str,
    access_token: str,
    start_date: _dt.date,
    end_date: _dt.date,
    start_row: int,
) -> dict:
    body = json.dumps(
        {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "dimensions": ["page"],
            "rowLimit": ROW_LIMIT,
            "startRow": start_row,
        }
    ).encode()
    url = SEARCH_ANALYTICS_URL.format(site=urllib.parse.quote(site_url, safe=""))
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def _classify(page_url: str) -> str | None:
    try:
        path = urllib.parse.urlparse(page_url).path
    except ValueError:
        return None
    # Longest-prefix wins ('/crypto/token' before '/crypto').
    for prefix in sorted(PAGE_TYPES, key=len, reverse=True):
        if path == prefix or path.startswith(prefix + "/"):
            return prefix
    return None


def _aggregate(rows: list[dict]) -> dict[str, dict[str, float]]:
    buckets: dict[str, dict[str, float]] = {
        p: {"impressions": 0, "clicks": 0} for p in PAGE_TYPES
    }
    for row in rows:
        keys = row.get("keys") or []
        if not keys:
            continue
        bucket = _classify(keys[0])
        if bucket is None:
            continue
        buckets[bucket]["impressions"] += int(row.get("impressions", 0) or 0)
        buckets[bucket]["clicks"] += int(row.get("clicks", 0) or 0)
    return buckets


def _write_csv(buckets: dict[str, dict[str, float]], out_path: pathlib.Path) -> None:
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
            f"{CREDENTIALS_PATH} note='GSC credentials missing — "
            "see runbooks/gsc-setup.md'",
        )
        return 0

    creds = json.loads(CREDENTIALS_PATH.read_text())
    site_url = creds.get("site_url")
    if not site_url:
        _log(today, "ERROR site_url missing in credentials")
        return 2

    end_date = today - _dt.timedelta(days=GSC_LAG_DAYS)
    start_date = end_date - _dt.timedelta(days=WINDOW_DAYS - 1)

    try:
        access_token = _refresh_access_token(creds)
    except (urllib.error.URLError, KeyError) as exc:
        _log(today, f"ERROR token-refresh-failed err={exc}")
        return 2

    all_rows: list[dict] = []
    start_row = 0
    while True:
        try:
            payload = _query_page_bucket(
                site_url, access_token, start_date, end_date, start_row
            )
        except urllib.error.HTTPError as exc:
            _log(
                today,
                f"ERROR searchanalytics-http status={exc.code} "
                f"body={exc.read().decode(errors='replace')[:200]!r}",
            )
            return 2
        except urllib.error.URLError as exc:
            _log(today, f"ERROR searchanalytics-net err={exc}")
            return 2

        rows = payload.get("rows") or []
        all_rows.extend(rows)
        if len(rows) < ROW_LIMIT:
            break
        start_row += ROW_LIMIT

    buckets = _aggregate(all_rows)
    out_path = OUT_DIR / f"gsc-{today:%Y%m%d}.csv"
    _write_csv(buckets, out_path)

    totals_imp = sum(int(b["impressions"]) for b in buckets.values())
    totals_clk = sum(int(b["clicks"]) for b in buckets.values())
    _log(
        today,
        f"OK rows={len(all_rows)} bucketed_impressions={totals_imp} "
        f"bucketed_clicks={totals_clk} window={start_date}..{end_date} "
        f"out={out_path}",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
