#!/usr/bin/env python3
"""Submit Smedjan / Nerq sitemaps to Bing Webmaster Tools.

Designed for a systemd timer on smedjan (every 24h). Stdlib-only so
the smedjan host does not need any extra packages.

Credentials: ~/.config/smedjan/bing-wmt-key containing JSON
    {
      "api_key": "...",
      "site_url": "https://nerq.ai/",
      "sitemaps": [                      # optional; if omitted we
        "https://nerq.ai/sitemap.xml"    #  derive from the local
      ]                                  #  sitemap-index / sitemap.
    }

For convenience the file may also contain just the raw API key as a
single line; in that case `site_url` defaults to https://nerq.ai/.

If the credentials file is absent we exit 0 after writing a blocker
line to the log — the systemd timer will keep firing harmlessly until
the operator drops the file in place (see runbooks/bing-setup.md).
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

CREDENTIALS_PATH = pathlib.Path.home() / ".config" / "smedjan" / "bing-wmt-key"
LOG_DIR = pathlib.Path.home() / "smedjan" / "measurement"
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOCAL_SITEMAP_INDEX = REPO_ROOT / "agentindex" / "static" / "sitemap-index.xml"
LOCAL_SITEMAP = REPO_ROOT / "static" / "sitemap.xml"

BING_SUBMIT_FEED_URL = (
    "https://ssl.bing.com/webmaster/api.svc/json/SubmitFeed?apikey={api_key}"
)
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def _log_path() -> pathlib.Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ymd = _dt.date.today().strftime("%Y%m%d")
    return LOG_DIR / f"bing-submission-{ymd}.log"


def _log(line: str) -> None:
    ts = _dt.datetime.now().isoformat(timespec="seconds")
    entry = f"{ts} {line}\n"
    with _log_path().open("a", encoding="utf-8") as fh:
        fh.write(entry)
    sys.stdout.write(entry)


def _load_credentials() -> dict:
    raw = CREDENTIALS_PATH.read_text().strip()
    try:
        creds = json.loads(raw)
        if not isinstance(creds, dict):
            raise ValueError("credentials JSON must be an object")
    except (json.JSONDecodeError, ValueError):
        creds = {"api_key": raw}
    creds.setdefault("site_url", "https://nerq.ai/")
    return creds


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
        if origin:
            return [f"{origin}/{candidate.name}"]
    return []


def _submit(site_url: str, sitemap_url: str, api_key: str) -> tuple[int, str]:
    url = BING_SUBMIT_FEED_URL.format(api_key=urllib.parse.quote(api_key, safe=""))
    body = json.dumps({"siteUrl": site_url, "feedUrl": sitemap_url}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode() or "ok"
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")


def main() -> int:
    if not CREDENTIALS_PATH.exists():
        _log(
            "BLOCKED credentials-missing path="
            f"{CREDENTIALS_PATH} note='Bing WMT key missing — "
            "see runbooks/bing-setup.md'"
        )
        return 0

    try:
        creds = _load_credentials()
    except OSError as exc:
        _log(f"ERROR credentials-read-failed err={exc}")
        return 2

    api_key = creds.get("api_key")
    site_url = creds.get("site_url")
    if not api_key:
        _log("ERROR api_key missing in credentials")
        return 2
    if not site_url:
        _log("ERROR site_url missing in credentials")
        return 2

    sitemaps = _discover_sitemaps(creds)
    if not sitemaps:
        _log(f"ERROR no sitemaps discovered site={site_url}")
        return 2

    ok = 0
    for sm in sitemaps:
        status, body = _submit(site_url, sm, api_key)
        tag = "OK" if 200 <= status < 300 else "FAIL"
        _log(f"{tag} status={status} site={site_url} sitemap={sm} body={body[:200]!r}")
        if 200 <= status < 300:
            ok += 1
    _log(f"SUMMARY submitted={ok} total={len(sitemaps)}")
    return 0 if ok == len(sitemaps) else 1


if __name__ == "__main__":
    sys.exit(main())
