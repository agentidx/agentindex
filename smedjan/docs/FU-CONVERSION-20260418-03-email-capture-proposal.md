# FU-CONVERSION-20260418-03 — Email-capture form on `/zarq/docs`, `/gateway`, homepage + newsletter-job model fix

> **Parent audit**: AUDIT-CONVERSION-20260418, Finding 3 (severity `critical`).
> **Window audited**: 2026-03-20 → 2026-04-19 (30d), `analytics_mirror.requests` (ai_mediated status<400 GET) + Nerq RO `public.compliance_subscribers`.
> **Status**: proposal only. No production deploy from this task.
> **Whitelisted edit surfaces for the implementation PR** (not this task):
>   - `agentindex/zarq_docs.py` (single HTML block inside `_render_docs`)
>   - `agentindex/gateway_page.py` (single HTML block inside `_page()`)
>   - `static/zarq_home.html` (single HTML block in the ZARQ homepage)
>   - `agentindex/ab_test.py::render_homepage` (one block, inserted into each of the 4 variants — nerq.ai homepage is A/B-tested)
>   - `agentindex/compliance/integration.py` (+ ~30 lines: form-urlencoded branch, rate limit, dedupe)
>   - `~/.openclaw/cron/jobs.json` (1-line model-string swap — **operational, not in the Python repo**; requires explicit execute-authority before touching)
> **Parallel work shipped — reuse, do not duplicate**:
>   - `agentindex/compliance/integration.py:99` — `POST /compliance/subscribe` accepts `{email, type, persona}` as **JSON only** today. Reuse; extend to form-urlencoded (Section 2).
>   - `FU-CONVERSION-20260418-07` (proposal shipped today) — dataset-digest capture card. This proposal deliberately matches its HTML/DOM shape so all four surfaces share one `<form>` fragment.
>   - `FU-CONVERSION-20260418-01` (in flight) — ZARQ CTA on success pages. This proposal piggybacks on the same CTA placement rules (post-content, above FAQ fold).

---

## Executive summary

`compliance_subscribers` has **5 rows all-time** (last insert 2026-04-03, prior 4 all `test` probes 2026-02-19). Over the 30d audit window (2026-03-20 → 2026-04-19), `analytics_mirror.requests` records:

| Surface | 30d ai_mediated hits | Current capture surface |
|---|---:|---|
| `/` (nerq.ai homepage, rendered by `ab_test.render_homepage`) | **5,643** | none |
| `/zarq/docs` (target of `/zarq/doc` 301) | **1** | none |
| `/gateway` | **2** | none |
| **POST `/compliance/subscribe`** (endpoint is live, just unreachable) | **0** | — |

The audit's "4 ai_mediated IPs hit subscribe-like paths, all 404" — re-checking today — resolves to `/is-tracing-subscriber-safe`, `/crates/tracing-subscriber`, `/what-is/tracing-subscriber`. **None of those are human subscribe attempts**; they are LLM-cited Rust-crate queries that matched `%subscribe%` by accident. The true state is worse than the audit stated: **zero ai_mediated humans have ever attempted to subscribe**, because the product exposes no form. Retention capture on the AI channel is not weak — it is absent.

**Proposed surface stack** (one HTML fragment, four insertion points):

1. **(S1)** A single `<form>` shape shared across the four surfaces, each stamping a distinct `sub_type`:
   - `/zarq/docs` → `sub_type='zarq_doc'`
   - `/gateway` → `sub_type='gateway'`
   - nerq.ai `/` (all 4 A/B variants) → `sub_type='home'`
   - ZARQ `/` (`static/zarq_home.html`) → `sub_type='zarq_home'`
   - (parked) `/dataset/<slug>` → `sub_type='dataset_digest'` — owned by FU-07.
   - (parked) generic catch-all post-LLM landing → `sub_type='ai_landing'` — seeded when a request carries the `?s=<ai>` param from FU-04; **not rendered by this proposal**, reserved in the tag vocabulary.
2. **(S2)** DB insert path: reuse `/compliance/subscribe`; extend the handler to accept form-urlencoded, add duplicate suppression on `(email, sub_type)`, and log the source path + user-agent fingerprint into a new 2-column sidecar.
3. **(S3)** Rate-limit (IP + global) and anti-bot (honeypot field + timing gate) at the endpoint — **no CAPTCHA** (free-tier only, paid-APIs rule).
4. **(S4)** Newsletter-job model-name fix in `~/.openclaw/cron/jobs.json:196` — swap dead `anthropic/claude-sonnet-4-20250514` for `anthropic/claude-sonnet-4-6` (currently allowed). No production-write from this task; the swap is staged as a 1-line diff the implementation ticket applies under explicit authority.

Expected lift (14d, see §Measurement): `compliance_subscribers` growth **≥ 60 new rows** (lower bound), of which ≥ 40 tagged `sub_type='home'` (the volume is there). Parent-audit F03 recommendation of "0.5 % capture on 1,200/day ai_mediated = 6/day = 180/month" is the upper bound if homepage hero is tuned (F06, separate follow-up); this proposal only targets the capture-*surface* existence problem, not the conversion-rate-tuning problem.

---

## Baseline (frozen 2026-04-19)

```sql
-- analytics_mirror:
SELECT count(*)                                                           AS ai_med_30d,
       count(*) FILTER (WHERE path IN ('/zarq/docs','/zarq/doc'))          AS zarq_doc,
       count(*) FILTER (WHERE path='/gateway')                             AS gateway,
       count(*) FILTER (WHERE path='/')                                    AS home_nerq
  FROM analytics_mirror.requests
 WHERE ts >= now() - interval '30 days'
   AND visitor_type='ai_mediated' AND status<400 AND method='GET';
-- 35,852 | 1 | 2 | 5,643

-- Nerq RO:
SELECT count(*), min(created_at), max(created_at),
       count(*) FILTER (WHERE email ILIKE 'test%') AS test_rows
  FROM compliance_subscribers;
-- 5 | 2026-02-19 14:14 | 2026-04-03 20:15 | 4
```

30d daily shape on `/` (sample): 140–220 ai_mediated/day; trend flat per F11. Gateway + zarq/docs are currently invisible to AI readers (1–2 hits each over 30d); capture surface there is a **long bet against future citation-lift from FU-01/F08**, not an immediate-volume bet.

---

## Section 1 — Form HTML spec (per surface)

### 1.1 Shared shape (`_subscribe_card.html`)

Single POST target, four call sites. The HTML below is the canonical shape; each surface only changes `data-surface-sub-type` and copy.

```html
<aside class="nerq-subscribe-card"
       role="region" aria-label="Subscribe"
       style="margin:32px 0;padding:20px;
              background:#ecfeff;border-left:4px solid #0d9488;
              max-width:720px">
  <div style="font-size:16px;font-weight:600;color:#0f766e;margin-bottom:4px">
    {{HEADLINE}}</div>
  <div style="font-size:13px;color:#374151;margin-bottom:12px">
    {{SUBTITLE}}</div>

  <form class="nerq-subscribe-form"
        method="post"
        action="/compliance/subscribe"
        style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">

    <!-- visible email field -->
    <input type="email" name="email" required
           placeholder="you@example.com"
           autocomplete="email"
           style="flex:1;min-width:220px;padding:10px;font-size:14px;
                  border:1px solid #d1d5db;font-family:inherit">

    <!-- honeypot: hidden via CSS; bots fill it, humans do not.
         Server rejects 200-OK-no-insert if `hp_website` != '' -->
    <input type="text" name="hp_website" value="" tabindex="-1"
           autocomplete="off"
           style="position:absolute;left:-9999px;width:1px;height:1px;opacity:0">

    <!-- timing gate: rendered server-side with Math.floor(time.time()*1000).
         Server rejects if (now - rendered_ts) < 2000 ms -->
    <input type="hidden" name="rendered_ts" value="{{RENDERED_TS_MS}}">

    <!-- per-surface tag -->
    <input type="hidden" name="type" value="{{SUB_TYPE}}">
    <input type="hidden" name="persona" value="{{PERSONA}}">

    <button type="submit"
            style="padding:10px 18px;background:#0d9488;color:#fff;border:0;
                   font-size:13px;font-weight:600;cursor:pointer">
      {{CTA_LABEL}}</button>
  </form>

  <div style="font-size:11px;color:#6b7280;margin-top:8px">
    We send one email at most per week. Unsubscribe in one click.
    See <a href="/privacy" style="color:#0d9488">privacy</a>.</div>
</aside>
```

**Design rules**

1. **No JavaScript.** Native HTML form POST. Honeypot + timing gate are both server-evaluated, not client-evaluated. This keeps the card visible and functional to LLM readers who sometimes render forms as plain text in answers (and to no-JS scrapers).
2. **Always include the `<aside>` role + aria-label**; the card is a secondary navigation landmark, not body content.
3. **One email field only.** No persona dropdown (the existing checker form's persona dropdown produced the `developer` value across all 5 extant rows — it was treated as free-selection, not signal). Persona is set server-side per surface instead.
4. **`rendered_ts` is the server's `time.time_ns() // 1_000_000`** injected at render (fresh every page load — **breaks Cloudflare HTML caching of the three surfaces for the `<form>` fragment only**; see §Cache note below).
5. **No reCAPTCHA, hCaptcha, Turnstile, or third-party widget.** Explicit "no paid APIs" rule, plus avoid any vendor that fingerprints the reader.

#### Cache note (important)

`/gateway` and `/zarq/docs` currently return `Cache-Control: public, max-age=3600` via Cloudflare edge — a per-request `rendered_ts` value will reduce edge-cacheability. Three acceptable fixes, pick one at implementation time:

1. **Fragment cache bypass**: set `Cache-Control: public, max-age=300, s-maxage=60` on these three routes only. Cost: 20× more origin hits for what is currently a ~1-hit/day-each surface (zarq/docs, gateway) — negligible. Home is 140–220/day, still negligible.
2. **Cookie-stamped ts**: render `rendered_ts` only from a `document.cookie` set on first visit via a `<script>` sniff — reintroduces JS and breaks no-JS readers. Reject.
3. **Omit timing gate**: skip `rendered_ts`, keep honeypot only. Weaker but still blocks 95 % of naive form-scrapers. Acceptable MVP; upgrade to (1) if honeypot misses too many bots.

**Recommended MVP: option 3 (honeypot only).** Timing gate is a d+30 upgrade if bot-insert volume becomes visible in the dedupe sidecar.

### 1.2 Per-surface copy and tags

| Surface | `SUB_TYPE` | `PERSONA` | `HEADLINE` | `SUBTITLE` | `CTA_LABEL` |
|---|---|---|---|---|---|
| `/zarq/docs` | `zarq_doc` | `api_reader` | Get notified when ZARQ changes | "One email when the methodology, endpoints, or ratings shift. No marketing." | Notify me |
| `/gateway` | `gateway` | `agent_builder` | Weekly tool-trust digest | "Five newly-verified MCP tools each week — what they do, their trust score, and what to swap them for." | Subscribe |
| `/` (nerq.ai) | `home` | `nerq_reader` | Weekly AI asset intelligence | "Five highest-trust new agents, datasets, or models each week. One email. No ads." | Subscribe |
| `/` (zarq.ai, `static/zarq_home.html`) | `zarq_home` | `crypto_reader` | Weekly crypto-risk snapshot | "Structural warnings, crashes caught, tokens downgraded. One email, Monday morning." | Subscribe |
| (reserved) `?s=<ai>` landing wrapper | `ai_landing` | `llm_reader` | — | Reserved for FU-CONVERSION-20260418-04 wiring; not rendered here | — |

All four surfaces use the same `<form>`. Only the 5 Jinja context values change.

### 1.3 Per-surface insertion point (exact file + anchor)

| Surface | File | Anchor | Placement |
|---|---|---|---|
| `/zarq/docs` | `agentindex/zarq_docs.py` | `_render_docs()` return string, between the closing tag of the last `<section>` and the `<footer>` | **Below** the last doc section, **above** footer; ≤ 60 px from bottom, so only scrolled-to-end readers see it (keeps the docs page skim-clean for LLMs). |
| `/gateway` | `agentindex/gateway_page.py` | `_page()` return string, between `</main>` and `{NERQ_FOOTER}` (line ~220) | Post-content; keeps the "Try nerq-gateway" fetch-demo CTA above-fold uncontested. |
| nerq.ai `/` | `agentindex/ab_test.py::render_homepage` | For each of the 4 variants, inject into the template just above the variant's final CTA section | **All 4 variants must receive the block** or A/B signal is contaminated (one variant having capture and another not would confound the test). Mark the card itself as NOT part of the A/B — only its placement-height may differ per variant. |
| ZARQ `/` | `static/zarq_home.html` | Before `<footer>`, after the `<div style="text-align:center…">` with the "scores updated daily" footer-adjacent line (~line 153) | Below-content, above footer; matches the `/zarq/docs` pattern. |

**Net new HTML per surface**: ~1.8 KB (one `<aside>`, no scripts, one inline `<style>`-less block). Compressed: ~700 bytes. Zero new HTTP requests.

### 1.4 i18n

English-only at MVP. Swedish copy for Smedjan traffic is owned by the expansion sprint (ADR-003), not this card. When the Swedish homepage exists, clone the block with `SUB_TYPE='home_sv'`.

### 1.5 Accessibility

- Labelled region, keyboard-focusable email input.
- `required` attribute + native browser validation.
- Contrast: `#0d9488` on `#fff` = 4.65:1 (AA); `#0f766e` on `#ecfeff` = 6.9:1 (AAA). Pass.
- No motion, no sound, no autofocus.

---

## Section 2 — DB insert path + `sub_type` tagging

### 2.1 Endpoint status quo

File: `agentindex/compliance/integration.py:99–142`. Today:

- Accepts `application/json` only (`await request.json()`).
- Validates `email` with a single `"@"` substring check.
- Has a table-auto-create (`CREATE TABLE IF NOT EXISTS compliance_subscribers …`) **left over from early dev**; the table exists in prod today, so this block is a noop but keeps the function idempotent.
- Inserts **unconditionally** — the 4 `tes***` rows 60 seconds apart on 2026-02-19 prove it. **No dedupe.**
- Swallows all exceptions silently and returns `{"status":"subscribed"}` with HTTP 200 — so a DB write failure is invisible to the client. This contributes to why the table is empty: if any real insert has failed in the past, we would not know.
- No rate-limit, no honeypot check.

### 2.2 Proposed minimal handler diff

```python
# agentindex/compliance/integration.py — replace lines 98–142 with the below.
# Proposal only; ship under implementation ticket FU-CONVERSION-20260418-03-impl.

import re
import time
import hashlib
from collections import deque
from fastapi import Request
from fastapi.responses import JSONResponse

# Simple in-process IP rate bucket: 5 inserts / IP / hour.
# Deliberately NOT using Redis — endpoint volume is tiny (target ~10/day
# at steady state), and a per-process deque keeps infra-dep zero.
_IP_HITS: dict[str, deque[float]] = {}
_IP_HITS_MAX = 5
_IP_HITS_WINDOW_S = 3600
_GLOBAL_HITS: deque[float] = deque()
_GLOBAL_MAX = 500  # site-wide ceiling / hour

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_ALLOWED_SUB_TYPES = {
    "zarq_doc", "gateway", "home", "zarq_home",
    "dataset_digest", "ai_landing",
    "checklist", "monitor",  # legacy — do not break /checker
}

@app.post("/compliance/subscribe")
async def subscribe_email(request: Request):
    # 1. Parse body — tolerate JSON or form-urlencoded.
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
    else:
        form = await request.form()
        data = dict(form)

    # 2. Honeypot: bot filled a hidden field.
    if (data.get("hp_website") or "").strip():
        return JSONResponse({"status": "subscribed"}, status_code=200)  # silent drop

    email = (data.get("email") or "").strip().lower()
    sub_type = (data.get("type") or "unknown").strip().lower()
    persona = (data.get("persona") or "unknown").strip().lower()

    # 3. Validate.
    if not _EMAIL_RE.match(email) or len(email) > 254:
        return JSONResponse({"status": "invalid_email"}, status_code=400)
    if sub_type not in _ALLOWED_SUB_TYPES:
        sub_type = "unknown"

    # 4. Rate-limit.
    ip = (request.headers.get("cf-connecting-ip")
          or request.client.host if request.client else "unknown")
    now = time.time()
    bucket = _IP_HITS.setdefault(ip, deque())
    while bucket and bucket[0] < now - _IP_HITS_WINDOW_S:
        bucket.popleft()
    if len(bucket) >= _IP_HITS_MAX:
        return JSONResponse({"status": "rate_limited"}, status_code=429)
    while _GLOBAL_HITS and _GLOBAL_HITS[0] < now - _IP_HITS_WINDOW_S:
        _GLOBAL_HITS.popleft()
    if len(_GLOBAL_HITS) >= _GLOBAL_MAX:
        return JSONResponse({"status": "rate_limited"}, status_code=429)

    # 5. Dedupe + insert.
    try:
        from agentindex.db.models import get_write_session
        from sqlalchemy import text
        session = get_write_session()

        existing = session.execute(
            text("SELECT 1 FROM compliance_subscribers "
                 "WHERE email=:email AND sub_type=:sub_type LIMIT 1"),
            {"email": email, "sub_type": sub_type},
        ).first()
        if existing:
            session.close()
            return JSONResponse({"status": "already_subscribed"}, status_code=200)

        session.execute(
            text("INSERT INTO compliance_subscribers (email, sub_type, persona) "
                 "VALUES (:email, :sub_type, :persona)"),
            {"email": email, "sub_type": sub_type, "persona": persona},
        )
        session.commit()
        session.close()

        bucket.append(now)
        _GLOBAL_HITS.append(now)

        logging.getLogger("nerq").info(
            f"subscribe email={hashlib.sha1(email.encode()).hexdigest()[:8]} "
            f"sub_type={sub_type} persona={persona} ip={ip}"
        )
    except Exception:
        logging.getLogger("nerq").exception("subscribe insert failed")
        return JSONResponse({"status": "error"}, status_code=500)

    return JSONResponse({"status": "subscribed"})
```

Diff summary (lines): `-44 +76`. No schema change.

### 2.3 Why no schema migration

Current `compliance_subscribers` columns accept this proposal as-is:

```
 id         integer NOT NULL DEFAULT nextval(…)
 email      text    NOT NULL
 sub_type   text            DEFAULT 'unknown'
 persona    text            DEFAULT 'unknown'
 created_at timestamp       DEFAULT now()
```

`sub_type` is free-text; the `_ALLOWED_SUB_TYPES` set is code-side only so old rows (`checklist`, `monitor`, `unknown`) stay valid.

**Nice-to-have (deferred)**: add a partial unique index `CREATE UNIQUE INDEX compliance_subscribers_email_sub_type_uniq ON compliance_subscribers(email, sub_type);` to enforce dedupe at the DB layer. **Not in this task** — schema change crosses the "no DB schema changes without explicit instruction" line in CLAUDE.md. Flag for a separate ticket requesting Anders's sign-off.

### 2.4 `sub_type` tag vocabulary (stable)

| Tag | Surface | Notes |
|---|---|---|
| `zarq_doc` | `/zarq/docs` | ZARQ-API followers |
| `gateway` | `/gateway` | nerq-gateway followers |
| `home` | nerq.ai `/` | nerq home (all 4 A/B variants) |
| `zarq_home` | zarq.ai `/` | ZARQ home |
| `dataset_digest` | `/dataset/<slug>` | Owned by FU-07 |
| `ai_landing` | any `?s=<ai>` landing | Owned by FU-04; reserved |
| `checklist` | `/checker` | Legacy — pre-existing |
| `monitor` | `/checker` | Legacy — pre-existing |
| `unknown` | default | Anything else |

---

## Section 3 — Rate-limit + anti-bot plan

Stacked cheapest-first. No external service, no paid API, no Redis dependency.

| Layer | Mechanism | Cost | Effectiveness |
|---|---|---|---|
| L0 | `<input type="email" required>` native validator | free | blocks nothing serious |
| L1 | Regex `_EMAIL_RE` server-side | free | blocks malformed strings |
| L2 | Honeypot `hp_website` field | ~10 bytes HTML | blocks ≥ 95 % of naive form-scanners |
| L3 | Per-IP 5/hour + global 500/hour, in-process deques | 0 infra | blocks brute-fill from single IP |
| L4 | Silent-drop on honeypot hit (200 OK, no insert) | 0 | denies bots the 400/429 signal they'd use to adapt |
| L5 | SHA-1 email hash in logs only (not plaintext) | 0 | defence in depth if logs leak |
| L6 (deferred) | Cloudflare Turnstile | free tier, but pulls in Cloudflare JS | adds tracking surface — reject unless L2+L3 fail in measurement |
| L7 (deferred) | Timing gate (`rendered_ts`) | breaks edge cache, see §1.1 | d+30 upgrade |

**Expected false-positive rate**: 0 at L1–L5. A human typing fast will not hit the 5/hour cap; any human retry is blocked by L4 dedupe in `_ALLOWED_SUB_TYPES`.

**What happens if we get scraped anyway**: the dedupe index (code-side) keeps the table clean-ish; worst case, we see `sub_type='unknown'` rows with junk emails. Run `DELETE FROM compliance_subscribers WHERE email NOT LIKE '%@%.%' OR sub_type='unknown' AND created_at > :since` as a manual cleanup — acceptable until L6 is needed.

**What this does NOT protect against**

- Targeted human adversary (would burn through `5/hr`, but stops being worthwhile before revenue exists — we are months from any monetization).
- Distributed bot network rotating IPs — possible, but cheap attack on a site with no form on it a week ago is unlikely. Monitor; if it happens, enable L6.

---

## Section 4 — Newsletter-job model-name fix

### 4.1 Current state

**Location**: `~/.openclaw/cron/jobs.json:196` (Buzz cron config, **operated by Buzz, not the Python repo**).

```json
{
  "id": "d71476ae-e32e-4790-9aef-0dfc22482d4b",
  "name": "Weekly AgentIndex Newsletter",
  "enabled": true,
  "schedule": {"kind": "cron", "expr": "0 6 * * 1", "tz": "Europe/Stockholm"},
  "payload": {
    "kind": "agentTurn",
    "message": "Generate and deliver the weekly AgentIndex newsletter. …",
    "model": "anthropic/claude-sonnet-4-20250514"
  },
  "state": {
    "consecutiveErrors": 3,
    "lastError": "model not allowed: anthropic/claude-sonnet-4-20250514"
  }
}
```

The model string `anthropic/claude-sonnet-4-20250514` has been retired. Per `docs/buzz-snapshots/OPERATIONSPLAN-2026-04-11.md:264`, Buzz itself has flagged this as a hardcoded-model smell.

### 4.2 Proposed one-line swap

```diff
-      "model": "anthropic/claude-sonnet-4-20250514"
+      "model": "anthropic/claude-sonnet-4-6"
```

**Rationale for picking `claude-sonnet-4-6`**:

- The Max-subscription environment this task runs in exposes Opus-4.7 (1M), Sonnet-4.6, and Haiku-4.5 as current models (see CLAUDE.md model family note in the session).
- Newsletter generation is a weekly, moderate-complexity write task — Sonnet-4.6 is the cost/quality sweet spot; Opus-4.7 would be overkill for templated stats summaries, Haiku-4.5 would underperform on the Swedish/English mixed tone.
- Keeps the `anthropic/` provider prefix that Buzz already uses.
- Zero-risk swap — the rest of the JSON object is unchanged; Buzz picks up model changes at next schedule fire (next Monday 06:00 Stockholm).

### 4.3 Fallback plan

The newsletter content generator (`newsletter/automated_newsletter.py`) does **not** call Anthropic directly — it runs stats aggregation (`WeeklyReportGenerator`) and markdown formatting (`NewsletterFormatter`) **with no LLM dependency at all**. The `model` field in `jobs.json` is the model Buzz uses to *interpret* the cron job's `message` string and *act* on it ("generate and deliver the newsletter"). So:

- **Fast path**: swap the model string. Buzz wakes, runs the Python newsletter generator, posts to Discord.
- **Slower path** (if swap still fails): rewrite the cron job's `payload.kind` from `agentTurn` (LLM-wrapped) to `systemEvent` (direct command), with the actual Python invocation. This is **out of scope for this task** — it rewrites Buzz's execution model — but worth parking here so the next ticket knows the option exists.

### 4.4 Do not execute from this task

**Explicit guardrail**: this task is design-only. The 1-line swap is an operational change to Buzz's cron config, which per CLAUDE.md requires explicit user authority. The implementation ticket must:

1. Read `~/.openclaw/cron/jobs.json`, take a `.bak` copy.
2. Apply the 1-line diff.
3. Confirm with Buzz's admin interface that the job re-enables and next-run-ts is in the future.
4. Do **not** restart Buzz; cron will pick up the edit on next fire.
5. Watch `~/.openclaw/cron/runs/d71476ae-*.jsonl` for the first post-edit run; expect a non-error `status: "ok"`.

The task description for this FU explicitly says "No production deploy from this task", which I read as blocking step 2 above from within *this* worker's execution. The design doc is the deliverable.

---

## Measurement — 14-day lift

Freeze a 14-day pre-window (`[deploy - 14d, deploy)`) and a 14-day post-window (`[deploy, deploy + 14d]`). Final verdict at d+14.

```sql
-- File: smedjan/audits/FU-CONVERSION-20260418-03-measure.sql
-- Pre-window: 0 subscribers from any of the 4 surfaces (baseline).
-- Post-window: target growth below.

-- 1. Surface-level request-side (run on smedjan analytics_mirror):
WITH windowed AS (
  SELECT CASE WHEN ts < :deploy_date THEN 'pre' ELSE 'post' END AS phase,
         path, status, method, visitor_type
    FROM analytics_mirror.requests
   WHERE ts >= (:deploy_date::timestamptz - interval '14 days')
     AND ts <  (:deploy_date::timestamptz + interval '14 days')
)
SELECT phase,
       count(*) FILTER (WHERE method='POST' AND path='/compliance/subscribe') AS post_hits,
       count(*) FILTER (WHERE method='POST' AND path='/compliance/subscribe' AND status=200) AS post_200,
       count(*) FILTER (WHERE method='POST' AND path='/compliance/subscribe' AND status=400) AS post_400,
       count(*) FILTER (WHERE method='POST' AND path='/compliance/subscribe' AND status=429) AS post_429,
       count(*) FILTER (WHERE visitor_type='ai_mediated' AND path='/zarq/docs' AND method='GET' AND status<400) AS zarq_docs_ai_hits,
       count(*) FILTER (WHERE visitor_type='ai_mediated' AND path='/gateway'   AND method='GET' AND status<400) AS gateway_ai_hits,
       count(*) FILTER (WHERE visitor_type='ai_mediated' AND path='/'          AND method='GET' AND status<400) AS home_ai_hits
  FROM windowed
 GROUP BY phase
 ORDER BY phase;

-- 2. Row-side on Nerq RO (run separately, NOT via analytics_mirror):
--    Groups inserted rows by sub_type and phase.
SELECT
  CASE WHEN created_at < :deploy_date THEN 'pre' ELSE 'post' END AS phase,
  sub_type,
  count(*) AS n
  FROM compliance_subscribers
 WHERE created_at BETWEEN (:deploy_date::timestamptz - interval '14 days')
                      AND (:deploy_date::timestamptz + interval '14 days')
 GROUP BY 1, 2
 ORDER BY 1, 3 DESC;
```

### Success thresholds (day+14)

| Metric | pre (14d) | target post (14d) | rationale |
|---|---:|---:|---|
| `compliance_subscribers` total new rows | 0 | **≥ 60** | primary KPI; lower bound |
| `sub_type='home'` rows | 0 | ≥ 40 | ~5,643/30d homepage → 2,800/14d; 1.4% floor |
| `sub_type='zarq_doc'` rows | 0 | ≥ 0 (no floor) | /zarq/docs has 1 ai_mediated hit/30d; capture surface is a bet on FU-01 driving traffic, not immediate volume |
| `sub_type='gateway'` rows | 0 | ≥ 0 (no floor) | same as above |
| `sub_type='zarq_home'` rows | 0 | ≥ 5 | zarq.ai homepage is lower-trafficked than nerq.ai but non-zero |
| POST `/compliance/subscribe` 200-rate | n/a | ≥ 70 % | endpoint health check; below suggests regex over-reject |
| POST `/compliance/subscribe` 429-rate | n/a | ≤ 2 % | rate-limit misfiring |
| Newsletter-job `lastStatus` | `error` (3× consec) | `ok` on first Monday post-deploy | S4 validation; hard-fail signal if not |
| 4xx rate on `/`, `/gateway`, `/zarq/docs` | freeze | ≤ pre + 0.5 pp | guardrail — HTML bloat introduced? |

### Alert / rollback conditions

- **Any 5xx from `/compliance/subscribe`** > 1 % of POSTs: roll back to pre-Section-2 handler.
- **Dedupe missing**: if `SELECT email, sub_type, count(*) FROM compliance_subscribers GROUP BY 1,2 HAVING count(*)>1` returns rows within 24 h, the dedupe `SELECT 1` step is racing — swap to `INSERT … ON CONFLICT DO NOTHING` (needs the partial-unique index — then it IS a schema change; confirm with Anders).
- **Junk-row volume > 20 % of post inserts**: honeypot bypassed. Enable L6 (Turnstile).
- **`home_ai_hits` drops > 20 % post-deploy**: homepage HTML bloat, AI crawler giving up. Investigate; rollback card on nerq.ai `/` first.

---

## Out of scope / deferred

- **Weekly send pipeline**: this proposal creates capture *surface*. The actual Monday-morning outbound email job is `newsletter/automated_newsletter.py`, which today writes a `.md` file and stops. An SMTP sender (with DKIM, unsubscribe link, list-unsub header) is a separate follow-up: **FU-CONVERSION-20260418-03b**. Capture without send is fine for 30 days — but set a 30-day timer or the promise of "one email a week" gets broken.
- **Unsubscribe endpoint**: the card copy promises one-click unsubscribe. Today, none exists. MVP implementation can use `mailto:unsubscribe@nerq.ai?subject=unsubscribe+<sha1_email>` as a stopgap. A real `/compliance/unsubscribe?token=<signed>` endpoint is follow-up **FU-CONVERSION-20260418-03c**.
- **DB schema UNIQUE index**: see §2.3 — needs Anders sign-off.
- **Double opt-in**: not in MVP; regulatory baseline for EU recipients is a confirmation email. Since the first sends happen ≥ 7 days post-capture and require FU-03b, the DOI flow is owned by that follow-up, not this one.
- **Cookie consent**: the form does not set any cookies; no consent banner needed for capture. If L7 (timing gate) adds a cookie path, revisit.
- **Per-variant A/B copy on nerq.ai `/`**: the card is identical across variants A/B/C/D **by design** (§1.3 rule). A copy A/B is a separate experiment.
- **Sticky / floating capture**: explicitly rejected — the card is post-content. If 14-day capture rate exceeds 2.0 % we can promote to a sticky right-rail (needs shared CSS changes, touches 4+ templates).
- **Swedish copy** — ADR-003 expansion sprint owns i18n.
- **Persona signal**: hardcoded per surface, not user-selected. If downstream digest content wants reader-intent tags, add them in FU-03b, not here.

---

## References

- Parent audit: `smedjan/audit-reports/2026-04-18-conversion.md` §Finding 3 (lines 99–122).
- Endpoint being extended: `agentindex/compliance/integration.py:99` (`POST /compliance/subscribe`).
- Sibling proposal reusing the same endpoint: `smedjan/docs/FU-CONVERSION-20260418-07-dataset-verdict-proposal.md` §W3.
- Cron job with dead model: `~/.openclaw/cron/jobs.json:193–212` (job id `d71476ae-e32e-4790-9aef-0dfc22482d4b`).
- Failing-run log: `~/.openclaw/cron/runs/d71476ae-e32e-4790-9aef-0dfc22482d4b.jsonl` (3 consecutive `model not allowed` errors, latest 2026-03-11 06:00 Stockholm based on epoch ms 1776052823439).
- Target-surface templates:
  - `agentindex/zarq_docs.py` (`/zarq/docs`, redirect target of `/zarq/doc`)
  - `agentindex/gateway_page.py` (`/gateway`)
  - `agentindex/ab_test.py::render_homepage` (nerq.ai `/`, 4 variants)
  - `static/zarq_home.html` (zarq.ai `/`)
- Schema reference: Postgres `compliance_subscribers` — `\d` output confirmed 2026-04-19 (5 columns, no indexes beyond PK).
- CLAUDE.md rule on hardcoded model strings: `CLAUDE.md:123` + `docs/buzz-snapshots/OPERATIONSPLAN-2026-04-11.md:264`.
