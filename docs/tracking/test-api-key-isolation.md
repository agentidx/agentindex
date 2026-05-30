# Tracking: isolate test API key from production NERQ_DASHBOARD_KEY

**Opened:** 2026-05-30 (phase 4 PREP-2)
**Severity:** low (functional workaround in place)
**Owner:** unassigned
**Status:** tracking — defer until distinct-key infra has a clear use case

## Context

Phase 3 question F.5 asked how to test auth-gated paths. Anders' answer:
"out-of-scope för default suite. Skapa separat test_auth_endpoints.py som
skipps om ZARQ_TEST_API_KEY env-var saknas. Generera test-key + spara i
~/agentindex/secrets/.env.test (gitignored, riktiga read-only key med
begränsad scope)."

The intent: a distinct, read-only test key that the suite can use without
risking production access if it leaks.

What was actually shipped in PREP-2 (commit TBD): `~/agentindex/secrets/.env.test`
sets `ZARQ_TEST_API_KEY` to the existing `NERQ_DASHBOARD_KEY` *default*
value (`"nerq-reach-2026"`). The suite reads it; the server validates
against `NERQ_DASHBOARD_KEY`. Same string, different env-var name — they
happen to match because the production env doesn't override the default.

## Why not a separate key right now

Two changes would have to land together:

1. `reach_dashboard.py` (and any other `/internal/*` route validators)
   would need to accept a *list* of valid keys, not a single string —
   so that both the dashboard key and the test key are honored.
2. `com.nerq.api` LaunchAgent plist would need a new env var
   `NERQ_TEST_API_KEY=...` set to the same generated value the suite
   uses.

That's a code change in the auth path plus a production restart. Phase 4's
risk-budget didn't allow it without a clearer use case for parallel keys
(rotation? different scopes per key? different audit trails?). Using the
existing key in `.env.test` defers the question without blocking testing.

## What "graduate this" looks like

When we're ready to do this properly:

1. Generate a value: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. Add it to `com.nerq.api.plist` under `EnvironmentVariables` as
   `NERQ_TEST_API_KEY` and to `~/agentindex/secrets/.env.test` as
   `ZARQ_TEST_API_KEY` (same value).
3. Modify the single key check in `reach_dashboard.py`
   (`if key != DASHBOARD_KEY`) into a set-check that accepts either the
   dashboard key or the test key. Log which key was used (audit trail).
4. Restart `com.nerq.api`. Verify both keys work.
5. Update this tracking issue with the result and close.

## Risk of current setup

The "test" key in `.env.test` *is* the production `/internal/*` key. If
`.env.test` ever escapes git-ignore (a `git add -f` or someone copies it
to a shared location), an attacker gets read access to the same internal
dashboards a Nerq operator does. Acceptable risk for now because:

- `.env.test` is matched by `.env.*` in `.gitignore`, and `secrets/` is
  also gitignored as a safety net.
- The data behind `/internal/*` is operational metrics (reach, yield),
  not user PII or financial state.
- `NERQ_DASHBOARD_KEY` is rotatable — if the test key leaks, set
  `NERQ_DASHBOARD_KEY` in the production plist to a new value and the
  test suite stops working until graduated to proper isolation.

## Related

- `tests/zarq_surface/test_auth_endpoints.py` — the consumer.
- `agentindex/reach_dashboard.py` — the single-key check that needs to
  become a list-check when this issue graduates.
- `secrets/.env.test` — current placeholder credentials.
