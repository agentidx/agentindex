# Fix: CF-IPCountry Header Replaces ip-api.com Rate-Limited Lookup

Date: 2026-04-12 (Sunday evening ~17:04 CEST)
Status: Applied and verified — missing country rate dropped from 57% to 0%

## Problem

Analytics dashboard showed growing discrepancy between 'Human Visits by Country (top 10)' and 'Human Visits by Language' and 'Summary human visits' because an exponentially growing fraction of requests had no country attribution.

Growth curve of missing country:
- 2026-04-05: 497 missing per day (4%)
- 2026-04-10: 13,024 (16%)
- 2026-04-11: 19,371 (21%)
- 2026-04-12 (pre-fix): 44,529 missing (49% of day traffic)

## Root cause

`agentindex/analytics.py::_ip_to_country()` was calling external API
`http://ip-api.com/json/{ip}?fields=countryCode` for every unique IP.

Free tier of ip-api.com has a hard limit of 45 requests per minute.

As Nerq grew, unique IPs exceeded that threshold, causing:
1. External API calls timing out or returning 429
2. Failed lookups cached as empty string in `_geo_cache`
3. Same IP would then permanently lack country attribution until
   process restart (every request restart would re-cache as empty
   on first failed lookup).

## Fix

Added `country` parameter to `log_request()` and read it from Cloudflare
request header `CF-IPCountry` in the middleware. This header is free,
has no rate limit, and Cloudflare sets it on every request it proxies
to origin.

Code changes:
1. `log_request()` signature adds `country=None` kwarg
2. Inside `log_request()`, if `country is None` then fall back to
   `_ip_to_country(ip)` (legacy path, kept for testcases that don't
   use CF)
3. Middleware extracts `cf_country = request.headers.get('cf-ipcountry', '')`
   and filters CF 'XX' (unknown) and 'T1' (Tor) codes
4. Middleware passes `country=cf_country` to `log_request()`

## Deployment

FastAPI restarted via launchctl at 2026-04-12 17:04 CEST.
Sacred bytes verified 2/2/1 before and after.

## Verification

Measured percentage of requests with missing country, per minute:

| Time | Missing% |
|---|---|
| 17:00 | 59.1% |
| 17:03 | 57% |
| **17:04 (restart)** | 12.8% |
| **17:05** | 0.3% |
| **17:06** | 0.4% |
| **17:07** | 0.0% |

Complete coverage restored within 3 minutes of restart.

## Impact

- Analytics dashboard now shows complete country attribution
- Request latency improved ~5-10ms (no external HTTP call per unique IP)
- ip-api.com rate limit eliminated as growth bottleneck
- Same geoIP data source as Cloudflare's own analytics (consistent)

## Backup

`agentindex/analytics.py.bak-pre-cf-country` preserved in repo directory.

## Legacy path

`_ip_to_country()` function retained. Now only invoked when `country` is
not passed (testcases or non-CF origins). Cache and external call still
works, just not invoked in normal production flow.
