# A2 Schema Design

**Audited:** 2026-04-10 by Claude Code (Leverage Sprint Day 2 M3)
**Status:** Read-only audit, deployment-ready design, no changes made
**Blocking production:** no — design only

---

## Current analytics.db state

| Property | Value |
|---|---|
| File path | `/Users/anstudio/agentindex/logs/analytics.db` |
| File size | 9,297,940,480 bytes (8.66 GB) |
| Total rows | 14,699,443 |
| Date range | 2026-03-11 to 2026-04-10 (30 days) |
| Avg rows/day (last 7d) | ~795,923 (range: 667K–1.07M) |
| Est. bytes/row | ~632 bytes |
| Rows last 30 days | 14,700,940 (essentially all data) |

## Current requests table schema

Source: `PRAGMA table_info(requests)`

| cid | name | type | notnull | default | pk |
|---|---|---|---|---|---|
| 0 | id | INTEGER | 0 | — | 1 (PK) |
| 1 | ts | TEXT | 1 | — | 0 |
| 2 | method | TEXT | 0 | — | 0 |
| 3 | path | TEXT | 0 | — | 0 |
| 4 | status | INTEGER | 0 | — | 0 |
| 5 | duration_ms | REAL | 0 | — | 0 |
| 6 | ip | TEXT | 0 | — | 0 |
| 7 | user_agent | TEXT | 0 | — | 0 |
| 8 | bot_name | TEXT | 0 | — | 0 |
| 9 | is_bot | INTEGER | 0 | 0 | 0 |
| 10 | is_ai_bot | INTEGER | 0 | 0 | 0 |
| 11 | referrer | TEXT | 0 | — | 0 |
| 12 | referrer_domain | TEXT | 0 | — | 0 |
| 13 | query_string | TEXT | 0 | — | 0 |
| 14 | search_query | TEXT | 0 | — | 0 |
| 15 | country | TEXT | 0 | — | 0 |

Schema defined at: `agentindex/analytics.py:78–95`

## Current indices

Source: `PRAGMA index_list(requests)` + `PRAGMA index_info` for each

| Index name | Columns |
|---|---|
| `idx_requests_bot` | (ts, is_ai_bot, bot_name) |
| `idx_requests_duration` | (ts, duration_ms) |
| `idx_requests_ts` | (ts) |
| `idx_ai_bot` | (is_ai_bot) |
| `idx_bot` | (is_bot) |
| `idx_path` | (path) |
| `idx_ts` | (ts) |

Note: `idx_requests_ts` and `idx_ts` are redundant (both on `ts` alone).

## Current write path

**File:** `agentindex/analytics.py`

1. **Middleware:** `AnalyticsMiddleware` class at line 249. `dispatch()` at line 250 captures every non-static request.
2. **Field extraction:** Lines 278–281 extract `ip` (from `cf-connecting-ip` / `x-forwarded-for`), `user_agent`, `referer`, and `query_string` from request headers.
3. **Bot detection:** `_detect_bot(ua, ip)` called at line 216 inside `log_request()`. Returns `(is_bot, is_ai_bot, bot_name)`.
4. **Referrer parsing:** `_extract_referrer_domain(ref)` at line 187 extracts domain from referrer URL, strips `www.` prefix.
5. **INSERT:** `log_request()` at lines 213–246. The INSERT is at lines 222–229:
   ```sql
   INSERT INTO requests (ts, method, path, status, duration_ms, ip, user_agent,
      bot_name, is_bot, is_ai_bot, referrer, referrer_domain, query_string, search_query, country)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
   ```
6. **Referrer IS stored:** in both `referrer` (full URL, line 11) and `referrer_domain` (extracted domain, line 12).

**Call chain:** HTTP request → `AnalyticsMiddleware.dispatch()` (line 250) → `log_request()` (line 291) → SQLite INSERT.

## Current bot detection

**File:** `agentindex/analytics.py:150–185`

Function `_detect_bot(ua, ip)` uses three layers:

1. **AI_BOTS dict** (lines 49–73): maps user-agent fragments to bot names. Includes GPTBot, ChatGPT-User, ClaudeBot, PerplexityBot, Google-Extended, Bingbot, etc. `is_ai_bot=True` for: ChatGPT, Claude, Perplexity, Google AI, Cohere, ByteDance (line 155).
2. **Google crawler patterns** (lines 159–162): additional Google UA strings.
3. **Generic bot patterns** (lines 165–169): "bot", "crawler", "spider", etc.
4. **IP-based detection** (lines 171–183): known bot IP prefixes + volume threshold (>50 pages/day).

**Key observation:** `ChatGPT-User` is currently classified as `is_ai_bot=1` AND `is_bot=1`. This is wrong for A2 purposes — `ChatGPT-User` is an AI-mediated human visit (a human using ChatGPT who clicks a link), not a crawler bot. Same for `Claude-User` and `Perplexity-User`. The current classification conflates AI crawlers with AI-mediated human traffic.

**There is no `visitor_type` column.** Bot/human is determined by `is_bot` (INTEGER 0/1). There is no `ai_source` column. Classification is done at write time, not query time.

**Also:** `ab_test.py:56–65` has a separate `_is_bot()` function with different logic (simple fragment matching). Used only for A/B test logging, not for analytics.db.

## Proposed ALTER TABLE statements

### Column additions

```sql
-- 1. AI source attribution (which AI platform referred this visit)
ALTER TABLE requests ADD COLUMN ai_source TEXT;

-- 2. Visitor classification (replaces binary is_bot for richer taxonomy)
ALTER TABLE requests ADD COLUMN visitor_type TEXT;
```

**Timing estimate:** SQLite `ALTER TABLE ADD COLUMN` is metadata-only — it modifies the table definition without rewriting rows. Expected execution: <100ms regardless of table size. No lock contention beyond the brief schema lock.

**Why not a CHECK constraint?** SQLite supports CHECK constraints on ALTER TABLE ADD COLUMN only in version 3.37.0+. macOS system SQLite may be older. Moreover, CHECK failures would crash the analytics logger (which deliberately swallows exceptions). Enforce valid values in application code instead.

### Index additions

```sql
-- 3. Composite index for AI source dashboard queries
CREATE INDEX IF NOT EXISTS idx_ai_source_ts ON requests(ai_source, ts);

-- 4. Index for visitor_type filtering
CREATE INDEX IF NOT EXISTS idx_visitor_type ON requests(visitor_type);
```

**Timing estimate for `idx_ai_source_ts`:** On an 8.66 GB table with ~14.7M rows, creating a B-tree index requires a full table scan. Based on typical SQLite performance on SSD (~50K–100K rows/sec for index creation on a table this wide):
- Optimistic: ~2.5 minutes
- Conservative: ~5 minutes
- During this time, SQLite holds a RESERVED lock → **all writes will block**.

**Mitigation:** Run index creation during low-traffic hours (early morning UTC). The `idx_visitor_type` index is smaller (single column) but has the same lock behavior — run both in sequence during the same maintenance window.

## Proposed pattern matching function

**Insert point:** `agentindex/analytics.py`, between `_extract_referrer_domain()` (line 187) and `_extract_search_query()` (line 196). Call it from `log_request()` at line 216, right after `_detect_bot()`.

```python
# AI referrer domains → source name
_AI_REFERRER_DOMAINS = {
    'claude.ai': 'Claude',
    'chat.openai.com': 'ChatGPT',
    'chatgpt.com': 'ChatGPT',
    'perplexity.ai': 'Perplexity',
    'copilot.microsoft.com': 'Copilot',
    'bing.com': None,  # only if path contains /chat — handled below
    'gemini.google.com': 'Gemini',
    'grok.x.ai': 'Grok',
    'x.com': None,  # only if path contains /i/grok — handled below
    'duckduckgo.com': None,  # only with AI params — handled below
    'kagi.com': 'Kagi',
    'doubao.com': 'Doubao',
    'search.brave.com': None,  # only with AI params — handled below
}

# User-Agent fragments that indicate AI-mediated human visits (not bots)
_AI_MEDIATED_UA_FRAGMENTS = {
    'chatgpt-user': 'ChatGPT',
    'claude-user': 'Claude',
    'perplexity-user': 'Perplexity',
}


def classify_ai_source(
    referrer: str | None,
    referrer_domain: str | None,
    user_agent: str | None,
) -> tuple[str | None, str]:
    """Classify AI attribution and visitor type.

    Returns:
        (ai_source, visitor_type) where:
        - ai_source: 'ChatGPT', 'Claude', 'Perplexity', etc. or None
        - visitor_type: 'bot' | 'human' | 'ai_mediated'
    """
    ua_lower = (user_agent or '').lower()

    # 1. Check for AI-mediated user agents (highest signal)
    for fragment, source in _AI_MEDIATED_UA_FRAGMENTS.items():
        if fragment in ua_lower:
            return source, 'ai_mediated'

    # 2. Check referrer domain
    if referrer_domain:
        domain = referrer_domain.lower()
        source = _AI_REFERRER_DOMAINS.get(domain)

        if source is not None:
            return source, 'human'  # human clicked a link from an AI chat

        # Special cases requiring path/query inspection
        ref_lower = (referrer or '').lower()
        if domain == 'bing.com' and '/chat' in ref_lower:
            return 'Copilot', 'human'
        if domain == 'x.com' and '/i/grok' in ref_lower:
            return 'Grok', 'human'
        if domain == 'duckduckgo.com' and ('ia=' in ref_lower or 'ai=' in ref_lower):
            return 'DuckDuckGo AI', 'human'
        if domain == 'search.brave.com' and 'summarizer' in ref_lower:
            return 'Brave AI', 'human'

    # 3. No AI attribution detected — fall through to existing bot detection
    return None, ''  # caller uses existing is_bot to determine 'bot' or 'human'
```

**Integration in `log_request()` (line 213):**

```python
def log_request(method, path, status, duration_ms, ip, user_agent, referrer, query_string='', search_query=None):
    try:
        is_bot, is_ai_bot, bot_name = _detect_bot(user_agent or '', ip or '')
        ref_domain = _extract_referrer_domain(referrer)

        # NEW: AI source attribution
        ai_source, visitor_type = classify_ai_source(referrer, ref_domain, user_agent)
        if not visitor_type:
            visitor_type = 'bot' if is_bot else 'human'

        # UPDATE: override is_bot for AI-mediated visits
        if visitor_type == 'ai_mediated':
            is_bot = False  # These are human visits via AI, not bots
            is_ai_bot = False

        # ... rest unchanged, but INSERT gains ai_source and visitor_type columns
```

**Important fix:** `ChatGPT-User`, `Claude-User`, `Perplexity-User` are currently misclassified as `is_bot=1, is_ai_bot=1`. After this change, they will be classified as `visitor_type='ai_mediated'` with `is_bot=0`. This is a behavior change that improves accuracy. Existing dashboard queries filtering on `is_bot=0` will now correctly include AI-mediated human visits.

## Proposed backfill strategy

### Backfill SQL (all rows — data is only 30 days old)

Since the entire table spans only 2026-03-11 to 2026-04-10, there is no need for a date filter — all rows are within 30 days.

```sql
-- Step 1: Backfill ai_source and visitor_type from referrer_domain
UPDATE requests SET
    ai_source = CASE
        WHEN referrer_domain = 'claude.ai' THEN 'Claude'
        WHEN referrer_domain IN ('chat.openai.com', 'chatgpt.com') THEN 'ChatGPT'
        WHEN referrer_domain = 'perplexity.ai' THEN 'Perplexity'
        WHEN referrer_domain = 'copilot.microsoft.com' THEN 'Copilot'
        WHEN referrer_domain = 'gemini.google.com' THEN 'Gemini'
        WHEN referrer_domain = 'grok.x.ai' THEN 'Grok'
        WHEN referrer_domain = 'kagi.com' THEN 'Kagi'
        WHEN referrer_domain = 'doubao.com' THEN 'Doubao'
        WHEN referrer_domain = 'bing.com' AND referrer LIKE '%/chat%' THEN 'Copilot'
        WHEN referrer_domain = 'duckduckgo.com' AND (referrer LIKE '%ia=%' OR referrer LIKE '%ai=%') THEN 'DuckDuckGo AI'
        ELSE NULL
    END,
    visitor_type = CASE
        WHEN user_agent LIKE '%ChatGPT-User%' THEN 'ai_mediated'
        WHEN user_agent LIKE '%Claude-User%' THEN 'ai_mediated'
        WHEN user_agent LIKE '%Perplexity-User%' THEN 'ai_mediated'
        WHEN referrer_domain IN ('claude.ai', 'chat.openai.com', 'chatgpt.com',
            'perplexity.ai', 'copilot.microsoft.com', 'gemini.google.com',
            'grok.x.ai', 'kagi.com', 'doubao.com') THEN 'human'
        WHEN referrer_domain = 'bing.com' AND referrer LIKE '%/chat%' THEN 'human'
        WHEN referrer_domain = 'duckduckgo.com' AND (referrer LIKE '%ia=%' OR referrer LIKE '%ai=%') THEN 'human'
        WHEN is_bot = 1 THEN 'bot'
        ELSE 'human'
    END
WHERE ai_source IS NULL;  -- only run on unclassified rows

-- Step 2: Fix ai_source for AI-mediated user agents (separate pass for clarity)
UPDATE requests SET
    ai_source = CASE
        WHEN user_agent LIKE '%ChatGPT-User%' THEN 'ChatGPT'
        WHEN user_agent LIKE '%Claude-User%' THEN 'Claude'
        WHEN user_agent LIKE '%Perplexity-User%' THEN 'Perplexity'
        ELSE ai_source
    END
WHERE user_agent LIKE '%ChatGPT-User%'
   OR user_agent LIKE '%Claude-User%'
   OR user_agent LIKE '%Perplexity-User%';

-- Step 3: Fix is_bot for AI-mediated visits (retroactive correction)
UPDATE requests SET is_bot = 0, is_ai_bot = 0
WHERE visitor_type = 'ai_mediated' AND is_bot = 1;
```

### Estimated impact

| Metric | Value |
|---|---|
| Rows affected by Step 1 (visitor_type for all) | ~14.7M |
| Rows with AI referrer (ai_source set) | ~68 (from referrer_domain data) |
| Rows with AI-mediated UA (Step 2) | ~28,860 (ChatGPT-User: 28,628; Perplexity-User: 190; Claude-User: ~42) |
| Rows reclassified bot→ai_mediated (Step 3) | ~28,860 |

### Lock risk and mitigation

**Risk:** The Step 1 UPDATE touches all ~14.7M rows to set `visitor_type`. SQLite uses a journal/WAL for writes. This will:
- Require writing ~14.7M row updates (setting 1–2 columns)
- Hold an EXCLUSIVE lock for the duration
- Block all incoming writes (analytics logging) during execution

**Estimated execution time:** 
- Step 1 (14.7M rows): 5–15 minutes depending on WAL mode and disk I/O
- Step 2 (~29K rows): <1 second
- Step 3 (~29K rows): <1 second

**Mitigation — batched approach:**

```sql
-- Process in batches of 100K rows to limit lock duration to ~5-10 seconds each
UPDATE requests SET visitor_type = CASE ... END
WHERE id IN (SELECT id FROM requests WHERE visitor_type IS NULL LIMIT 100000);
-- Repeat until no rows remain. Sleep 1-2 seconds between batches to let writes drain.
```

This limits each lock to ~5–10 seconds, allowing queued analytics writes to complete between batches. Total wall time: ~20–30 minutes but with no sustained lock.

**Alternative: backfill only non-NULL rows first, fill visitor_type lazily.**
Since only ~29K rows have AI-relevant data, we could:
1. Backfill only AI-attributed rows immediately (~29K, <1 second)
2. Leave `visitor_type = NULL` for the 14.7M non-AI rows
3. Treat `visitor_type IS NULL` as equivalent to the existing `is_bot` column logic in queries

This avoids the 14.7M-row UPDATE entirely. **Recommended approach.**

## Proposed dashboard queries

### Panel 1: Overall AI-to-human conversion rate

```sql
-- AI-attributed human visits vs. AI bot crawls on the same URLs
SELECT
    ROUND(100.0 * human_visits / NULLIF(bot_crawls, 0), 2) AS conversion_rate_pct,
    human_visits,
    bot_crawls
FROM (
    SELECT
        COUNT(*) FILTER (WHERE ai_source IS NOT NULL AND visitor_type IN ('human', 'ai_mediated')) AS human_visits,
        (SELECT COUNT(*) FROM requests WHERE is_ai_bot = 1 AND ts >= date('now', '-7 days')) AS bot_crawls
    FROM requests
    WHERE ai_source IS NOT NULL AND ts >= date('now', '-7 days')
);
```

Note: SQLite does not support `FILTER (WHERE ...)`. Use:
```sql
SELECT
    ROUND(100.0 * SUM(CASE WHEN ai_source IS NOT NULL AND visitor_type IN ('human', 'ai_mediated') THEN 1 ELSE 0 END)
        / NULLIF((SELECT COUNT(*) FROM requests WHERE is_ai_bot = 1 AND ts >= date('now', '-7 days')), 0), 2)
        AS conversion_rate_pct,
    SUM(CASE WHEN ai_source IS NOT NULL AND visitor_type IN ('human', 'ai_mediated') THEN 1 ELSE 0 END) AS human_visits,
    (SELECT COUNT(*) FROM requests WHERE is_ai_bot = 1 AND ts >= date('now', '-7 days')) AS bot_crawls
FROM requests
WHERE ts >= date('now', '-7 days');
```

### Panel 2: Per-AI-source breakdown

```sql
SELECT
    ai_source,
    COUNT(*) AS visits,
    COUNT(DISTINCT ip) AS unique_visitors,
    COUNT(DISTINCT path) AS unique_pages
FROM requests
WHERE ai_source IS NOT NULL
  AND ts >= date('now', '-7 days')
GROUP BY ai_source
ORDER BY visits DESC;
```

### Panel 3: Top URLs by AI-attributed human visits

```sql
SELECT
    path,
    ai_source,
    COUNT(*) AS visits,
    COUNT(DISTINCT ip) AS unique_visitors
FROM requests
WHERE ai_source IS NOT NULL
  AND visitor_type IN ('human', 'ai_mediated')
  AND ts >= date('now', '-7 days')
GROUP BY path, ai_source
ORDER BY visits DESC
LIMIT 50;
```

### Panel 4: Language/vertical breakdown

The `requests` table does not have a `language` or `vertical` column. However, language/vertical can be inferred from the URL path pattern:

```sql
-- Extract language from path prefix (e.g., /sv/, /de/, /zh/)
SELECT
    CASE
        WHEN path LIKE '/en/%' OR path NOT LIKE '/__%/%' THEN 'en'
        ELSE SUBSTR(path, 2, 2)
    END AS language,
    ai_source,
    COUNT(*) AS visits
FROM requests
WHERE ai_source IS NOT NULL
  AND visitor_type IN ('human', 'ai_mediated')
  AND ts >= date('now', '-7 days')
GROUP BY language, ai_source
ORDER BY visits DESC;
```

Note: This is approximate. Needs validation against actual URL patterns in the codebase.

### Panel 5: 7-day trend for AI-attributed visits

```sql
SELECT
    date(ts) AS day,
    ai_source,
    visitor_type,
    COUNT(*) AS visits
FROM requests
WHERE ai_source IS NOT NULL
  AND ts >= date('now', '-7 days')
GROUP BY day, ai_source, visitor_type
ORDER BY day, visits DESC;
```

## Open questions

1. **Lock duration for backfill:** The full 14.7M-row backfill of `visitor_type` will hold an exclusive lock for 5–15 minutes. **Recommended:** skip the full backfill, only backfill the ~29K AI-attributed rows, and treat `visitor_type IS NULL` as legacy (use `is_bot` for those rows). Does Anders agree?

2. **Index creation timing:** `CREATE INDEX idx_ai_source_ts` on an 8.66 GB table will take 2–5 minutes with an exclusive lock. Should this be done during a maintenance window, or is 2–5 minutes of blocked writes acceptable during normal traffic?

3. **ChatGPT-User reclassification:** Currently ~28,860 `ChatGPT-User` requests are logged as `is_bot=1, is_ai_bot=1`. The proposed change reclassifies them as `visitor_type='ai_mediated', is_bot=0`. This changes the meaning of existing `is_bot=0` queries across all dashboards. **Risk:** any dashboard counting "human visits" as `is_bot=0` will see a one-time bump of ~29K visits retroactively. Is this acceptable, or should we keep `is_bot` unchanged and only use `visitor_type` going forward?

4. **5-minute attribution window:** The sprint plan mentions attributing visits "within 5 minutes of a known AI bot crawl" to AI sources. This requires correlating bot crawl timestamps with subsequent human visits to the same URL from the same or similar IP. **Assessment:** This is feasible but complex — requires a JOIN between bot crawls and human visits on `(path, ts within window)`. The current volume of AI bot crawls (~4M rows) makes this JOIN expensive. **Recommendation:** defer this to a later sprint; direct referrer + user-agent attribution covers the high-confidence cases.

5. **WAL mode:** Is analytics.db running in WAL mode? WAL allows concurrent reads during writes and reduces lock contention during backfill. Check with `PRAGMA journal_mode;`. If not WAL, consider switching before backfill.

6. **Existing query breakage:** Adding nullable columns via `ALTER TABLE ADD COLUMN` will not break existing queries — new columns default to NULL and are not referenced by existing `INSERT` statements (which use explicit column lists at `analytics.py:223`). However, the `log_request()` function's INSERT must be updated to include the two new columns. **No existing SELECT queries will break.**

7. **Disk space:** The 8.66 GB database will grow by the two new columns + two new indices. Estimate: ~200–400 MB additional for indices. Is disk space a concern on this Mac Studio?

8. **DuckDuckGo and Brave:** These are only AI-attributed when specific query parameters are present, but the `referrer` field may not contain the full URL with query params (depending on browser referrer policy). Need to verify what referrer data actually looks like for these sources.

## Appendix: raw PRAGMA and grep output

### PRAGMA table_info(requests)

```
0|id|INTEGER|0||1
1|ts|TEXT|1||0
2|method|TEXT|0||0
3|path|TEXT|0||0
4|status|INTEGER|0||0
5|duration_ms|REAL|0||0
6|ip|TEXT|0||0
7|user_agent|TEXT|0||0
8|bot_name|TEXT|0||0
9|is_bot|INTEGER|0|0|0
10|is_ai_bot|INTEGER|0|0|0
11|referrer|TEXT|0||0
12|referrer_domain|TEXT|0||0
13|query_string|TEXT|0||0
14|search_query|TEXT|0||0
15|country|TEXT|0||0
```

### PRAGMA index_list(requests)

```
0|idx_requests_bot|0|c|0      → columns: (ts, is_ai_bot, bot_name)
1|idx_requests_duration|0|c|0 → columns: (ts, duration_ms)
2|idx_requests_ts|0|c|0       → columns: (ts)
3|idx_ai_bot|0|c|0            → columns: (is_ai_bot)
4|idx_bot|0|c|0               → columns: (is_bot)
5|idx_path|0|c|0              → columns: (path)
6|idx_ts|0|c|0                → columns: (ts)
```

### AI referrer domain counts (current data)

```
chatgpt.com|20
claude.ai|17
perplexity.ai|15
kagi.com|14
copilot.microsoft.com|1
chat.openai.com|1
```

### AI-mediated user agent counts

```
ChatGPT-User variants: ~28,628 rows
Perplexity-User variants: ~190 rows
Claude-User variants: ~42 rows
```

### AI bot counts (is_ai_bot=1)

```
Claude|2,132,366
ChatGPT|1,571,501
Perplexity|159,924
ByteDance|105,350
Total: 3,968,949
```

### Top referrer domains (all traffic)

```
nerq.ai|1,388,602
zarq.ai|280,736
localhost:8000|13,493
google.com|6,550
bing.com|1,069
github.com|727
duckduckgo.com|332
agentcrawl.dev|297
```

### Key source files referenced

| File | Lines | Purpose |
|---|---|---|
| `agentindex/analytics.py` | 49–73 | AI_BOTS dict |
| `agentindex/analytics.py` | 75–95 | `_init_db()` — schema definition |
| `agentindex/analytics.py` | 150–185 | `_detect_bot()` — bot classification |
| `agentindex/analytics.py` | 187–194 | `_extract_referrer_domain()` |
| `agentindex/analytics.py` | 213–246 | `log_request()` — INSERT path |
| `agentindex/analytics.py` | 249–303 | `AnalyticsMiddleware` — request capture |
| `agentindex/analytics.py` | 278–281 | Header extraction (ip, ua, referer) |
| `agentindex/ab_test.py` | 56–65 | Separate `_is_bot()` (A/B test only) |
