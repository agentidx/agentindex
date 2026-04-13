# Phase 0 Day 4.5 — Crypto Read-Path on Hetzner Replicas

Date: 2026-04-13
Status: COMPLETE — all crypto endpoints working on all 3 nodes

## Problem

Hetzner nodes returned HTTP 500 on `/v1/crypto/rating/{token}` and
`/v1/crypto/ndd/{token}`. Root cause: crypto_api_v2.py read directly from
SQLite crypto_trust.db which was empty on Hetzner (by design — .db files
excluded from rsync).

## Solution

Created `agentindex/crypto/dual_read.py` — read-path counterpart to
`dual_write.py`. When `ZARQ_READ_POSTGRES=1`, returns a Postgres connection
wrapper that:
- Translates `?` → `%s` placeholders
- Adds `zarq.` prefix to Tier A table names
- Returns dict-like rows compatible with `sqlite3.Row`
- Uses `DATABASE_URL` env var for connection DSN

## Verification — all 3 nodes return identical data

```
=== /v1/crypto/rating/bitcoin ===
NBG: Baa2 56.46 2026-03-31
HEL: Baa2 56.46 2026-03-31
MAC: Baa2 56.46 2026-03-31

=== /v1/crypto/ndd/bitcoin ===
NBG: ndd=3.35 alert=WATCH run=2026-04-12
HEL: ndd=3.35 alert=WATCH run=2026-04-12
MAC: ndd=3.34 alert=WATCH run=2026-04-13   ← 1 day ahead (pre-dual-write gap)
```

## Files modified

| File | Change |
|---|---|
| `agentindex/crypto/dual_read.py` | NEW — Postgres read wrapper |
| `agentindex/crypto/crypto_api_v2.py` | `get_db()` uses `dual_read` when flag set |
| `agentindex/api/zarq_router.py` | Landing page data uses `dual_read` |

## Configuration

| Node | ZARQ_READ_POSTGRES | DATABASE_URL |
|---|---|---|
| Mac Studio | not set (reads SQLite) | not set (uses /tmp socket) |
| nerq-nbg-1 | 1 | postgresql://anstudio@127.0.0.1:5432/agentindex |
| nerq-hel-1 | 1 | postgresql://anstudio@127.0.0.1:5432/agentindex |

## Issues encountered

1. **Unix socket path**: Mac Studio uses `/tmp/.s.PGSQL.5432`, Hetzner uses
   `/var/run/postgresql/.s.PGSQL.5432`. Fixed by using `DATABASE_URL` env var.

## Known limitations

- Only `crypto_api_v2.py` and `zarq_router.py` use `dual_read`. Other crypto
  modules still read from SQLite directly. Those modules are not served via
  HTTP endpoints, so they don't affect Hetzner serving.
- NDD data on Hetzner is 1 day behind due to pre-dual-write gap (8K rows).
  Will converge once gap is backfilled.
