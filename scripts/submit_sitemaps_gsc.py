#!/usr/bin/env python3
"""Submit Smedjan / Nerq sitemaps to Google Search Console.

Designed for a systemd timer on smedjan (every 24h). Stdlib-only so
the smedjan host does not need google-api-python-client installed.

Credentials: ~/.config/smedjan/gsc-credentials.json with shape
    {
      "client_id": "...",
      "client_secret": "...",
      "refresh_token": "...",
      "site_url": "https://nerq.ai/",   # or sc-domain:nerq.ai
      "sitemaps": [                      # optional; if omitted we
        "https://nerq.ai/sitemap.xml"    #  derive from the local
      ]                                  #  sitemap-index / sitemap.
    }

If the credentials file is absent, we exit 0 after writing a blocker
line to the log — the systemd timer will keep firing harmlessly until
the operator drops the file in place (see runbooks/gsc-setup.md).
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

CREDENTIALS_PATH = pathlib.Path.home() / ".config" / "smedjan" / "gsc-credentials.json"
LOG_DIR = pathlib.Path.home() / "smedjan" / "measurement"
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOCAL_SITEMAP_INDEX = REPO_ROOT / "agentindex" / "static" / "sitemap-index.xml"
LOCAL_SITEMAP = REPO_ROOT / "static" / "sitemap.xml"

OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GSC_SITEMAP_URL_TMPL = (
    "https://www.googleapis.com/webmasters/v3/sites/{site}/sitemaps/{feedpath}"
)
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def _log_path() -> pathlib.Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ymd = _dt.date.today().strftime("%Y%m%d")
    return LOG_DIR / f"gsc-submission-{ymd}.log"


def _log(line: str) -> None:
    ts = _dt.datetime.now().isoformat(timespec="seconds")
    entry = f"{ts} {line}\n"
    with _log_path().open("a", encoding="utf-8") as fh:
        fh.write(entry)
    sys.stdout.write(entry)


def _discover_sitemaps(creds: dict) -> list[str]:
    explicit = creds.get("sitemaps")
    if explicit:
        return list(explicit)

    for candidate in (LOCAL_SITEMAP_INDEX, LOCAL_SITEMAP):
        if not candidate.exists():
            continue
        try:
            root = ET.parse(candidate).getroot()
        except ET.ParseError as exc:
            _log(f"WARN parse-failed path={candidate} err={exc}")
            continue
        locs = [el.text.strip() for el in root.findall(f".//{SITEMAP_NS}loc") if el.text]
        if root.tag.endswith("sitemapindex") and locs:
            return locs
        origin = creds.get("site_url", "").rstrip("/")
        if origin.startswith("sc-domain:"):
            return []
        if origin:
            return [f"{origin}/{candidate.name}"]
    return []


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


def _submit(site_url: str, sitemap_url: str, access_token: str) -> tuple[int, str]:
    url = GSC_SITEMAP_URL_TMPL.format(
        site=urllib.parse.quote(site_url, safe=""),
        feedpath=urllib.parse.quote(sitemap_url, safe=""),
    )
    req = urllib.request.Request(url, method="PUT")
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Content-Length", "0")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode() or "ok"
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")


def main() -> int:
    if not CREDENTIALS_PATH.exists():
        _log(
            "BLOCKED credentials-missing path="
            f"{CREDENTIALS_PATH} note='GSC credentials missing — "
            "see runbooks/gsc-setup.md'"
        )
        return 0

    creds = json.loads(CREDENTIALS_PATH.read_text())
    site_url = creds.get("site_url")
    if not site_url:
        _log("ERROR site_url missing in credentials")
        return 2

    sitemaps = _discover_sitemaps(creds)
    if not sitemaps:
        _log(f"ERROR no sitemaps discovered site={site_url}")
        return 2

    try:
        access_token = _refresh_access_token(creds)
    except (urllib.error.URLError, KeyError) as exc:
        _log(f"ERROR token-refresh-failed err={exc}")
        return 2

    ok = 0
    for sm in sitemaps:
        status, body = _submit(site_url, sm, access_token)
        tag = "OK" if 200 <= status < 300 else "FAIL"
        _log(f"{tag} status={status} site={site_url} sitemap={sm} body={body[:200]!r}")
        if 200 <= status < 300:
            ok += 1
    _log(f"SUMMARY submitted={ok} total={len(sitemaps)}")
    return 0 if ok == len(sitemaps) else 1


if __name__ == "__main__":
    sys.exit(main())
