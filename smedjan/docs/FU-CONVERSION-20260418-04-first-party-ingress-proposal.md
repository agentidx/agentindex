# FU-CONVERSION-20260418-04 — First-party AI ingress param + session cookie

> **Parent audit**: AUDIT-CONVERSION-20260418, Finding 4 (severity `high`).
> **Audit window**: 2026-03-20 → 2026-04-19 (30d), `analytics_mirror.requests` on smedjan.
> **Status**: design proposal only. No production deploy from this task.
> **Scope of future edits**: middleware in `agentindex/api/discovery.py` (in-repo, allowed), `agentindex/analytics.py` (classifier), and `analytics_mirror.requests` schema (forbidden file — requires explicit authority).
>
> **Coordination (do not duplicate)**:
>
> - `FU-CITATION-20260418-02` (`smedjan/observations/ai-mediated-attribution-20260418.md`) — established that **today's `ai_mediated` is agent fetches**, not human clicks. Its 0% `referrer_domain` is correct by construction (the ChatGPT-User / Claude-User / Perplexity-User UAs do not emit `Referer`). Proposed a Sec-Fetch-Site-based passive detector that captures stripped-referrer human clicks as `ai_human_click` / `ai_source='ai_likely'`.
> - `FU-CITATION-20260418-09` (`smedjan/observations/ai-source-classifier-parity-20260418.md`) — per-vendor parity analysis; confirmed CIDR rules have zero recall on humans.
>
> **This task's contribution on top of those** is the *active, deterministic per-vendor* signal (tagged inbound URL + first-party cookie). It is **complementary, not redundant**, to Patch B/C in the sibling note.

---

## 1. Executive summary

Three coupled problems to solve for the human-click cohort:

1. **No per-vendor ground truth for stripped-referrer clicks.** Sibling Patch B produces `ai_source='ai_likely'` for cross-site document nav with empty `Referer`. That is vendor-agnostic. To evaluate "optimize for Claude vs ChatGPT vs Perplexity" we need per-vendor ground truth on at least a subset of paths.
2. **Citation-body → click attribution is lost after first hit.** Even when the inbound URL carries `?s=<vendor>`, we need attribution to persist across subsequent same-session PVs without leaking it to Google (canonical pollution) or to third-party referrers (referrer leakage).
3. **Our own headers must not silently strip referrer.** Audited below; we are clean.

Proposed fix shape (spec only; no code):

- **(a) Ingress param taxonomy.** Accept `?s=chatgpt|claude|perplexity|gemini|ai_other` on any HTML endpoint. Also accept the conventional `?utm_source=chatgpt.com|claude.ai|perplexity.ai|gemini.google.com` as an alias — this is what vendor UIs already inject when they rewrite answer-body links through a referrer-preserving tracker.
- **(b) Stamp + strip on first hit.** First-time landing with `?s=…` sets an `HttpOnly`, `SameSite=Lax`, `Secure`, first-party session cookie `__ai_src`, then emits `302 → same-path-without-?s` so (i) the canonical URL Google indexes is clean, (ii) Cloudflare cache keys stay stable, (iii) the param never re-fires on reload.
- **(c) Classifier reads cookie.** `classify_ai_source` reads `__ai_src` from the cookie jar when referrer + UA signals are both blank, and emits `ai_source=<vendor>`, `visitor_type='ai_human_click'` (depends on sibling Patch B having added that enum value).
- **(d) Injection surface.** Tagged URLs are published via `llms.txt`, per-page `<link rel="canonical">` with `?s=<vendor>` on a small allowlist of high-value answer pages, and sitemap annotations. This is the bit the LLMs need to actually pick up — design has a §6 on why it's not a given.

Target populated-column rate after rollout: **5–15% of the human-click cohort** carries `ai_source != NULL` via the cookie, on top of the ~5–10% already captured by the sibling's `ai_likely` bucket. Expected **absolute volume 30–300 rows / 30d** for the per-vendor subset, gated on how many answer pages have the allowlisted canonical (§6).

---

## 2. Current-state audit: what we do, and do not, strip

### 2.1 Nerq does not set Referrer-Policy or CSP

Response headers from `https://nerq.ai/` (Cloudflare edge, 2026-04-19):

```
HTTP/2 200
content-type: text/html; charset=utf-8
access-control-allow-origin: *
access-control-allow-methods: GET, POST, OPTIONS
cache-control: public, max-age=14400, s-maxage=3600, stale-while-revalidate=86400
cdn-cache-control: public, max-age=3600, stale-while-revalidate=86400
server: cloudflare
x-cache: HIT
cf-cache-status: HIT
```

No `Referrer-Policy`, no `Content-Security-Policy`, no `Strict-Transport-Security`, no `X-Frame-Options`, no `Permissions-Policy`. The middleware in `agentindex/api/discovery.py:593` only touches `Access-Control-*` and `Cache-Control`.

**Audit finding**: **Nerq is not the entity stripping the inbound `Referer` header.** When a browser navigates *to* Nerq, what arrives is whatever the sender's document policy allowed through. Per the sibling note, the 0% rate on `ai_mediated` is explained by UA behavior (server-side bot fetches don't send Referer), and the ≤10-row/30d rate on human follow-through (Claude=1, Perplexity=8) is explained by the *sender's* policy — `rel="noopener noreferrer"` on outbound-citation anchors, or a document-level `Referrer-Policy: strict-origin-when-cross-origin` or stricter on claude.ai / perplexity.ai.

**No referrer-policy fix is available to us as the receiver.** The ingress-param approach is the only server-side remedy.

### 2.2 Cloudflare edge inserts `referrer-policy: same-origin` on its *error pages* (e.g., 502)

Observed on `?s=chatgpt` which currently misses cache → upstream returned 502:

```
HTTP/2 502
referrer-policy: same-origin
x-frame-options: SAMEORIGIN
```

These headers are from Cloudflare's default error template, not our origin. They do not affect ingress — by the time the browser sees them, the request has already been made. They only affect *outbound* nav from the error page itself, which is not a path our readers follow. No action required, but worth logging so we don't chase a phantom fix.

### 2.3 The `?s=chatgpt` test currently 502s

Query-string variation on a hot-cached home page causes Cloudflare to miss cache → origin-fetch → 502 (likely origin rate limit or `BotRateLimitMiddleware` at `agentindex/api/discovery.py:149`). This is **implementation concern #1** for rollout: the ingress-param path must be served cleanly from origin, not 502'd. See §7.

---

## 3. Cookie schema

One cookie, scoped narrowly. No PII, no cross-subdomain leakage, no fingerprinting surface.

| Property | Value | Why |
|---|---|---|
| Name | `__ai_src` | Leading `__` prevents client-side `document.cookie` writes from JS libraries clobbering it. Short name for header budget. |
| Value | `{vendor}:{ts_unix}:{hmac_trunc}` | e.g. `chatgpt:1744761600:8a3f12`. Three colon-separated fields. |
| &nbsp;&nbsp;`vendor` | enum: `chatgpt`, `claude`, `perplexity`, `gemini`, `ai_other` | Matches existing `ai_source` enum plus catch-all. |
| &nbsp;&nbsp;`ts_unix` | integer UNIX seconds at stamp time | Lets classifier age-check the cookie and degrade gracefully if the value is older than TTL. |
| &nbsp;&nbsp;`hmac_trunc` | first 6 hex chars of `HMAC-SHA256(secret, vendor + ':' + ts_unix)` | Rejects forged cookies sent by scrapers mimicking the flow. Secret lives in env (`NERQ_COOKIE_HMAC_KEY`), rotated at will — stale cookies just fail validation silently and classify as unknown, which is harmless. |
| Domain | `.nerq.ai` | Works across `www.nerq.ai`, `zarq.ai` is a separate apex — would need a second cookie if we want cross-property attribution. **Out of scope for F04** (flagged in §9 q2). |
| Path | `/` | All surfaces. |
| Max-Age | `1800` (30 min) | "Session" cookie; AI citations rarely drive a return visit hours later. Longer TTL inflates per-vendor numbers artificially and invites stale attribution. |
| HttpOnly | `true` | No JS needs to read this. Keeps it out of XSS reach. |
| Secure | `true` | HTTPS-only. Nerq is HTTPS-only. |
| SameSite | `Lax` | `Strict` would strip the cookie on the 302 self-redirect in some browsers; `Lax` preserves it on top-level nav which is what we do. `None` is too permissive. |
| Priority | (unset) | Default medium is fine. |

**Size budget**: ~50 bytes. Well under any header limit.

**Cookie header echoes back on every subsequent PV**, which is what we want — the classifier reads it per-request.

**No server-side session store.** The cookie is self-contained; no DB row is written for "the session exists." This matters because session-store infra is one of the few things that creates operational on-call burden; we dodge it entirely.

---

## 4. Param-rewrite rules

### 4.1 Accepted ingress keys

```
?s=chatgpt | ?s=claude | ?s=perplexity | ?s=gemini | ?s=ai_other
?utm_source=chatgpt.com | chatgpt | openai | openai.com
?utm_source=claude.ai | claude | anthropic | anthropic.com
?utm_source=perplexity.ai | perplexity
?utm_source=gemini.google.com | gemini | bard
```

Any unrecognised `?s=` value → drop silently, do not stamp. Any `?utm_source=` not in the map → leave intact for GA-style consumers, do not stamp.

**Case-insensitive matching** on the value. Whitespace trimmed. Max 32 chars; longer → reject.

### 4.2 Middleware flow (pseudocode, insertion point after `BotRateLimitMiddleware` at `agentindex/api/discovery.py:184`)

```python
class AISourceStampMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Only stamp on GET of text/html surfaces. Never on /api/*, /static/*,
        # /search_events, and never on HEAD/POST.
        if (request.method == "GET"
                and not request.url.path.startswith(("/api/", "/static/",
                                                    "/search_events"))
                and _looks_like_html_route(request.url.path)):
            vendor = _extract_ingress_vendor(request.query_params)
            if vendor and "__ai_src" not in request.cookies:
                # First hit. Stamp cookie, 302 to stripped URL.
                stripped_qs = _strip_ingress_keys(request.query_params)
                target = request.url.path + (f"?{stripped_qs}" if stripped_qs else "")
                resp = RedirectResponse(url=target, status_code=302)
                resp.set_cookie(
                    key="__ai_src",
                    value=_encode_cookie(vendor),
                    max_age=1800,
                    path="/",
                    domain=".nerq.ai",
                    secure=True,
                    httponly=True,
                    samesite="lax",
                )
                # Do NOT write request to analytics here; the classifier will
                # run on the subsequent GET (post-redirect) with the cookie
                # present, which is when we want the row stamped.
                return resp

        return await call_next(request)
```

### 4.3 What gets stripped

`s`, `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term` — the whole UTM family. If the user arrived from a hand-crafted ChatGPT answer with `?utm_source=chatgpt.com`, that tag is *our* tracker; it has no business being in the URL Google indexes. Strip it at the same moment we stamp the cookie.

### 4.4 What does NOT get stripped

Any other query param (`?tab=`, `?compare=`, `?sort=`) is the page's own state; leave it alone.

### 4.5 Idempotency & double-stamp avoidance

- If the cookie is already set, do **not** re-stamp or re-redirect. Just drop the ingress keys from the URL if present (cheap optimisation; `?s=` on a returning visitor is redundant).
- If the user arrives with `?s=chatgpt` and already has `__ai_src=claude:…`, **overwrite** — the newer signal wins. Log this as an `overwrite_count` metric; we expect it to be near-zero, and a spike would indicate a scraping pattern.

### 4.6 Cache-key implications (operational)

Cloudflare keys on full URL including query string. Consequences:

- Before rewrite: every inbound `?s=<vendor>` PV missed cache → origin load. At 1,100 ai_mediated/day this is ≈ 1/80 RPS of origin traffic, manageable, **but** combined with `BotRateLimitMiddleware` it's what produced the 502 in §2.3.
- After rewrite: the 302 response itself varies on `?s=` (cheap — just a Location header, minimal origin CPU); the subsequent stripped URL is a plain cache HIT.
- Configure Cloudflare to **not cache** any response carrying `Set-Cookie: __ai_src=…` — the 302 must always come fresh from origin to stamp each visitor. Standard CF behaviour already avoids caching `Set-Cookie` responses, but double-check the page rule on `nerq.ai/*`.

---

## 5. Classifier patch (design sketch only)

**Depends on sibling Patch B** (`ai_human_click` / `ai_agent_fetch` taxonomy split and `ai_likely` value). Without that, this patch has no `visitor_type` value to write.

Insertion point in `agentindex/analytics.py:279` — extend `classify_ai_source` signature to accept `cookies: dict[str, str]`:

```python
def classify_ai_source(referrer, referrer_domain, user_agent, sec_fetch_site=None,
                      sec_fetch_dest=None, sec_fetch_user=None, cookies=None):
    ua_lower = (user_agent or '').lower()

    # 1. Existing UA-fragment rule (unchanged).
    for fragment, source in _AI_MEDIATED_UA_FRAGMENTS.items():
        if fragment in ua_lower:
            return source, 'ai_agent_fetch'     # renamed per sibling Patch B

    # 2. NEW: first-party cookie wins over all referrer-based rules.
    if cookies:
        vendor, ok = _decode_ai_src_cookie(cookies.get('__ai_src'))
        if ok and vendor:
            return _vendor_to_ai_source(vendor), 'ai_human_click'

    # 3. Existing referrer-domain rule (unchanged).
    if referrer_domain:
        source = _AI_REFERRER_DOMAINS.get(referrer_domain.lower())
        if source is not None:
            return source, 'ai_human_click'      # renamed per sibling Patch B

    # 4. NEW (from sibling Patch B): Sec-Fetch-Site stripped-referrer detector.
    if (not referrer
        and (sec_fetch_site or '').lower() == 'cross-site'
        and (sec_fetch_dest or '').lower() == 'document'
        and (sec_fetch_user or '') == '?1'):
        return 'ai_likely', 'ai_human_click'

    return None, ''
```

Precedence: cookie > referrer-domain > Sec-Fetch-Site. Cookie is the *most specific* per-vendor signal and should not be overridden by a weaker passive signal on subsequent PVs.

---

## 6. Injection surface — how vendors pick up `?s=<vendor>`

This is where the design has the biggest open uncertainty. Three mechanisms, in descending order of reliability:

### 6.1 `llms.txt` canonical with `?s=<vendor>`

We already ship `llms.txt` per `docs/strategy/nerq-ai-citation-optimization-sprint.md` context. Rewrite the canonical URL block to include `?s=llms_txt_seen` — not a vendor directly, but a ground-truth marker that *any* LLM ingesting `llms.txt` and surfacing its canonical URL will tag.

Catch: `llms.txt` is a recommendation, not a standard; vendors may or may not round-trip the canonical param. ChatGPT's crawler tends to canonicalise; Claude less so. **Expected pickup rate: low (~5% of vendor-answer links).**

### 6.2 Per-page `<link rel="canonical">` with `?s=<vendor>`

The allowlist approach (sibling note §4.3 / §8 q3). For the top ~20 high-AI-landing pages (`/dataset/wildchat-*`, `/safe/<top-N-slugs>`, `/profile/<top-N>`), emit a canonical with vendor-specific query string depending on UA on render. This is SEO-risky — canonical mutation can nuke organic rank if done wrong. **Needs Anders sign-off** (sibling q3).

Alternative, safer: emit a single stable `<link rel="canonical">` (no query), but add a `<script type="application/ld+json">` JSON-LD `sameAs` hint pointing to `?s=<vendor>` URLs. JSON-LD consumption by LLMs is rising; organic rank impact is near zero.

**Expected pickup rate**: 10–25% of vendor-answer links that hit one of the allowlisted pages.

### 6.3 Hand-placed tagged URLs in answer-seed surfaces

`sitemap.xml` already exists and is forbidden under this task's rules (see §10). Outside that, any time we publish a URL for LLM consumption (press release, GitHub README, docs site, blog post), we use the `?s=ai_other` variant. This is a content-ops change, not a code change — the smedjan factory can coordinate a one-off pass over published anchor-link inventory.

**Expected pickup rate**: ~100% for the one-off-tagged links — but the volume of such links is small (tens, not thousands).

### 6.4 Net expected populated-column rate

Given:

- Sibling Patch B captures ~5,000–15,000 rows/30d as `ai_likely` (stripped-referrer passive detector) — per sibling §7.
- Of those, the fraction that traveled through an allowlisted page with a vendor-tagged canonical: ~5–15% → **250–2,250 rows/30d carry `ai_source != NULL` via cookie**.
- Plus the one-off tagged links: tens/30d.

**Conservative post-rollout target**: `ai_source != NULL` on ≥ 5% of the new `ai_human_click` cohort, i.e., 250–750 rows / 30d with per-vendor ground truth. If we exceed 1,000 rows / 30d with per-vendor attribution, the vendors are round-tripping canonicals more aggressively than expected and we should revisit the overwrite-count metric in §4.5 for fraud signal.

**What "populated-column rate" is NOT**: it is not "% of today's 36,423 `ai_mediated` rows will gain a referrer_domain after rollout." Those are agent fetches and *cannot gain a referrer* regardless of what we ship. The relevant denominator shifts to the sibling's new `ai_human_click` cohort.

---

## 7. Implementation & rollout concerns

1. **Cloudflare 502 on `?s=` today (§2.3).** Must be resolved before rollout. Options: exempt `?s=` from `BotRateLimitMiddleware`, or add a CF page rule to route `?s=<known-vendor>` to origin without rate limiting. Prefer the former — keeps policy in-app.
2. **Cache-key proliferation.** The 302 response *itself* varies on `?s=` but is small and uncachable; Cloudflare default already does not cache 302 with `Set-Cookie`. The stripped URL is what we want cached and that key is stable. No page-rule changes needed.
3. **GSC / Ahrefs impact.** Because we 302 to the stripped URL within the first hop, neither Googlebot nor the AI bot's crawler (when they follow tagged links) will index the tagged variant — the canonical is always clean. Confirmed safe.
4. **Cookie domain scope.** `.nerq.ai` covers `www.nerq.ai`. `zarq.ai` is a different eTLD and will **not** see this cookie. If we want Nerq→ZARQ cross-surface attribution (which F01 wants), the right answer is a redirect-preserved param on the ZARQ handoff link itself, not cross-domain cookies. Out of scope here.
5. **Consent / privacy.** No PII in the cookie, no third-party embedding, no fingerprinting. Under GDPR this is a "strictly necessary for functionality" cookie for analytics purposes — arguable but defensible; in any case a short TTL (30 min) and no cross-domain scope minimise exposure. Flag for legal review during deploy.
6. **Cookie forgery.** HMAC-truncation (§3 `hmac_trunc`) is 24 bits — brute-force is trivial. That is intentional: we are not defending against adversaries, only filtering obvious replay from low-effort scrapers. Stale cookies fail silently and the request classifies as no-signal; zero fallout for the user.

---

## 8. Validation plan (mirrors sibling §6)

### 8.1 Pre-deploy data self-check

Confirm no existing cookie named `__ai_src` collides with anything:

```sql
-- requests has no cookie column today; this check runs after the schema migration.
SELECT count(*) FROM analytics_mirror.requests WHERE cookie_header ILIKE '%__ai_src%';
-- Expect 0 (we haven't stamped anything yet). If nonzero, a prior experiment
-- left stale cookies in browsers — investigate before enabling the classifier.
```

### 8.2 Manual click-test (pre-deploy baseline + post-deploy gate)

Four terminals, one per vendor (`chatgpt`, `claude`, `perplexity`, `gemini`):

```bash
# Using real browser (because headless curl won't preserve SameSite=Lax correctly):
# 1. Open a fresh incognito window.
# 2. Visit https://nerq.ai/safe/<canary-slug>?s=claude
# 3. Expected: 302 → /safe/<canary-slug> with Set-Cookie: __ai_src=claude:…
# 4. Visit https://nerq.ai/safe/<other-slug>
# 5. Expected: 200, cookie still present, row stamped ai_source='Claude',
#             visitor_type='ai_human_click'.
```

Query after each step:

```sql
SELECT ts, path, ai_source, visitor_type, substr(user_agent,1,40) ua
  FROM analytics_mirror.requests
 WHERE ts >= now() - interval '5 minutes'
 ORDER BY ts DESC LIMIT 10;
```

Save raw results to `~/smedjan/observations/FU-CONVERSION-20260418-04-validation.json`.

### 8.3 Post-deploy aggregate check (T+7d)

```sql
SELECT date_trunc('day', ts) day,
       ai_source, visitor_type, count(*) n
  FROM analytics_mirror.requests
 WHERE ts >= now() - interval '7 days'
   AND visitor_type = 'ai_human_click'
 GROUP BY 1,2,3 ORDER BY 1 DESC, 4 DESC;
```

Pass criteria:

- Weekly `ai_human_click` volume ≥ 200 (gate shared with sibling §6.3; same rows, different lens).
- Cookie-sourced per-vendor rows ≥ 30 / wk across any combination of `ai_source ∈ {Claude, ChatGPT, Perplexity, Gemini}`. (Fail → likely an injection-surface problem §6; investigate llms.txt / canonical coverage, not the classifier.)
- `overwrite_count` (§4.5) ≤ 5 / wk. (Fail → scraping-pattern investigation.)

---

## 9. Open questions / decision points for Anders

1. **TTL.** 30-minute session cookie is the conservative default. If we want day-scope attribution (same user returns 4 hours later, is that still "Claude-attributed"?) bump to 24 h. Trade-off is slightly stale per-vendor counts vs. a more permissive model of what counts as a "session." My recommendation: stay at 30 min; a returning user four hours later is a different intent, not the same funnel.
2. **`zarq.ai` cross-domain.** If F01 (Nerq→ZARQ handoff) ships, it will redirect human readers from Nerq to ZARQ. Cookie won't travel. Should we preserve attribution across the hop via `?s=<vendor>` on the outbound ZARQ link? Small work, big clarity win. Recommend yes — but track as a separate follow-up under F01.
3. **Canonical mutation risk (sibling §8 q3).** Without canonical tagging the per-vendor signal is bounded by the one-off tagged-link inventory (small). Gaining real volume needs the allowlisted-canonical change, which carries SEO risk. Not this task's call — but flagging that without it, §6.4's conservative target hits the low end.
4. **HMAC secret rotation policy.** If we ever rotate `NERQ_COOKIE_HMAC_KEY`, all in-flight cookies fail validation silently. That is the designed behaviour (they classify as no-signal and the reader is unaffected). Policy decision: rotate quarterly? Annually? Never rotate unless compromise suspected? Recommend never-unless-compromise.

---

## 10. Forbidden-file callouts

Deploy-task implementation will need authority for:

- **`agentindex/api/main.py`** — if the middleware stack lives there (actually it's in `discovery.py` at lines 586–589; check before deploy whether `main.py` also needs touching for the middleware import).
- **`alembic/`** (or equivalent migration) — `analytics_mirror.requests` gets one new nullable text column `cookie_ai_src` (or the full raw `cookie_header` if sibling Patch A decides to capture it). Forbidden under this task.
- **`.env` files** — `NERQ_COOKIE_HMAC_KEY` added to server env. Forbidden under this task.

In-repo, no extra authority needed:

- `agentindex/api/discovery.py` — middleware insertion (already has 4 custom middlewares).
- `agentindex/analytics.py` — classifier signature extension.
- `agentindex/api/search_events.py:77,95` — existing `classify_ai_source` call sites; pass cookie jar through.

---

## 11. Proposed follow-up tasks

To be queued via `scripts/smedjan queue add` after this note is reviewed.

1. **FU-CONVERSION-2026xxxx-F04A** (risk=low) — cookie-schema + middleware implementation in `discovery.py`. No forbidden files. Blocks on HMAC-key env var (§10).
2. **FU-CONVERSION-2026xxxx-F04B** (risk=low) — classifier patch in `analytics.py` and `search_events.py`. Depends on sibling Patch B (taxonomy split).
3. **FU-CONVERSION-2026xxxx-F04C** (risk=medium) — injection-surface rollout: update `llms.txt` to include `?s=llms_txt_seen` marker. Touches a file adjacent to `robots.txt`/`sitemap.xml`; confirm whitelist before.
4. **FU-CONVERSION-2026xxxx-F04D** (risk=medium) — canonical-tagging allowlist for top-20 AI-landing pages. Depends on §9 q3 Anders sign-off.
5. **FU-CONVERSION-2026xxxx-F04E** (risk=low) — manual click-test (§8.2) pre-deploy baseline + post-deploy gate. Output JSON.
