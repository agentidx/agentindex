"""
Nerq Analytics Dashboard — /admin/analytics-dashboard
Dark theme, JetBrains Mono, daily breakdowns from analytics.db.
File-based cache, 10min TTL.
"""
import json
import logging
import os
import sqlite3
import time
from datetime import date, datetime

from fastapi import Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger("nerq.analytics_dashboard")

ANALYTICS_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "analytics.db")
_CACHE_FILE = "/tmp/nerq_analytics_dashboard.json"
_CACHE_TTL = 600  # 10 minutes


def _query_data():
    """Run all queries against analytics.db and return data dict."""
    conn = sqlite3.connect(ANALYTICS_DB, timeout=30)
    data = {}

    # 0. SUMMARY — per-day totals for each category
    rows = conn.execute("""
        SELECT date(ts) as day,
          SUM(CASE WHEN is_bot = 0 THEN 1 ELSE 0 END) as human,
          SUM(CASE WHEN is_ai_bot = 1 AND status = 200 AND path NOT LIKE '/v1/preflight%' AND user_agent NOT LIKE '%GPTBot%' THEN 1 ELSE 0 END) as ai_cite,
          SUM(CASE WHEN is_ai_bot = 1 AND status = 200 AND path NOT LIKE '/v1/preflight%' AND user_agent LIKE '%GPTBot%' THEN 1 ELSE 0 END) as ai_index,
          SUM(CASE WHEN is_ai_bot = 1 AND status != 200 THEN 1 ELSE 0 END) as ai_errors,
          SUM(CASE WHEN is_bot = 1 AND is_ai_bot = 0 AND bot_name IN ('Google','Bing','Yandex','DuckDuck','Apple') THEN 1 ELSE 0 END) as search,
          SUM(CASE WHEN bot_name = 'Meta' THEN 1 ELSE 0 END) as meta,
          SUM(CASE WHEN bot_name = 'Amazon' THEN 1 ELSE 0 END) as amazon,
          SUM(CASE WHEN is_bot = 1 AND is_ai_bot = 0 AND bot_name NOT IN ('Google','Bing','Yandex','DuckDuck','Apple','Meta','Amazon') THEN 1 ELSE 0 END) as other_bots,
          COUNT(*) as total
        FROM requests GROUP BY day ORDER BY day
    """).fetchall()
    summary = {}
    for k in ["human", "ai_cite", "ai_index", "ai_errors", "search", "meta", "amazon", "other_bots", "total"]:
        summary[k] = {}
    for r in rows:
        day = r[0]
        for i, k in enumerate(["human", "ai_cite", "ai_index", "ai_errors", "search", "meta", "amazon", "other_bots", "total"], 1):
            summary[k][day] = r[i] or 0
    data["summary"] = summary

    # 0b. AI Preflight per day (from preflight_analytics, AI bots only)
    pf_ai_rows = conn.execute("""
        SELECT date(ts) as day, COUNT(*) as cnt
        FROM preflight_analytics WHERE bot_name IN ('ChatGPT','Claude','Perplexity','ByteDance')
        GROUP BY day ORDER BY day
    """).fetchall()
    data["summary"]["ai_preflight"] = {day: cnt for day, cnt in pf_ai_rows}

    # 1. AI CITATIONS per bot per day (status=200, excludes GPTBot indexing + preflight)
    rows = conn.execute("""
        SELECT date(ts) as day, bot_name, COUNT(*) as cnt
        FROM requests WHERE is_ai_bot = 1
          AND status = 200
          AND path NOT LIKE '/v1/preflight%'
          AND user_agent NOT LIKE '%GPTBot%'
        GROUP BY day, bot_name ORDER BY day, bot_name
    """).fetchall()
    citations = {}
    for day, bot, cnt in rows:
        if bot not in citations:
            citations[bot] = {}
        citations[bot][day] = cnt
    data["aiCitations"] = citations

    # 2. AI INDEXING per day (GPTBot only, status=200)
    rows = conn.execute("""
        SELECT date(ts) as day, COUNT(*) as cnt
        FROM requests WHERE is_ai_bot = 1
          AND status = 200
          AND path NOT LIKE '/v1/preflight%'
          AND user_agent LIKE '%GPTBot%'
        GROUP BY day ORDER BY day
    """).fetchall()
    data["aiIndexing"] = {day: cnt for day, cnt in rows}

    # Search crawls per bot per day
    rows = conn.execute("""
        SELECT date(ts) as day, bot_name, COUNT(*) as cnt
        FROM requests WHERE is_bot = 1 AND is_ai_bot = 0
          AND bot_name IN ('Google','Bing','Yandex','DuckDuck','Apple')
        GROUP BY day, bot_name ORDER BY day, bot_name
    """).fetchall()
    search = {}
    for day, bot, cnt in rows:
        if bot not in search:
            search[bot] = {}
        search[bot][day] = cnt
    data["searchCrawls"] = search

    # Other crawlers per bot per day
    rows = conn.execute("""
        SELECT date(ts) as day, bot_name, COUNT(*) as cnt
        FROM requests WHERE is_bot = 1 AND is_ai_bot = 0
          AND bot_name IN ('Meta','Amazon')
        GROUP BY day, bot_name ORDER BY day, bot_name
    """).fetchall()
    other_crawlers = {}
    for day, bot, cnt in rows:
        if bot not in other_crawlers:
            other_crawlers[bot] = {}
        other_crawlers[bot][day] = cnt
    data["otherCrawlers"] = other_crawlers

    # AI Errors per STATUS CODE per day (non-200)
    rows = conn.execute("""
        SELECT date(ts) as day, CAST(status AS TEXT) as sc, COUNT(*) as cnt
        FROM requests WHERE is_ai_bot = 1 AND status != 200
        GROUP BY day, sc ORDER BY day, sc
    """).fetchall()
    ai_errors = {}
    for day, sc, cnt in rows:
        if sc not in ai_errors:
            ai_errors[sc] = {}
        ai_errors[sc][day] = cnt
    data["aiErrors"] = ai_errors

    # New AI platform crawls per bot per day (all status codes)
    rows = conn.execute("""
        SELECT date(ts) as day,
          CASE
            WHEN user_agent LIKE '%Grok%' THEN 'Grok'
            WHEN user_agent LIKE '%DeepSeek%' THEN 'DeepSeek'
            WHEN user_agent LIKE '%MistralAI%' THEN 'Mistral'
            WHEN user_agent LIKE '%Sogou%' THEN 'Sogou'
            WHEN user_agent LIKE '%Baiduspider%' THEN 'Baidu'
            WHEN user_agent LIKE '%Yeti%' THEN 'Naver'
            WHEN user_agent LIKE '%DuckDuckBot%' THEN 'DuckDuckBot'
            WHEN user_agent LIKE '%coccocbot%' THEN 'CocCoc'
            WHEN user_agent LIKE '%LinkedInBot%' THEN 'LinkedIn'
            WHEN user_agent LIKE '%NotebookLM%' THEN 'NotebookLM'
            WHEN user_agent LIKE '%BraveSearch%' THEN 'Brave'
            WHEN user_agent LIKE '%kagi%' THEN 'Kagi'
            ELSE NULL
          END as bot, COUNT(*) as cnt
        FROM requests
        WHERE ts > datetime('now', '-30 days')
          AND (user_agent LIKE '%Grok%' OR user_agent LIKE '%DeepSeek%'
            OR user_agent LIKE '%MistralAI%' OR user_agent LIKE '%Sogou%'
            OR user_agent LIKE '%Baiduspider%' OR user_agent LIKE '%Yeti%'
            OR user_agent LIKE '%DuckDuckBot%' OR user_agent LIKE '%coccocbot%'
            OR user_agent LIKE '%LinkedInBot%' OR user_agent LIKE '%NotebookLM%'
            OR user_agent LIKE '%BraveSearch%' OR user_agent LIKE '%kagi%')
        GROUP BY day, bot ORDER BY day, bot
    """).fetchall()
    new_ai = {}
    for day, bot, cnt in rows:
        if bot and bot != 'NULL':
            if bot not in new_ai:
                new_ai[bot] = {}
            new_ai[bot][day] = cnt
    data["newAiPlatforms"] = new_ai

    # SEO/Other crawlers breakdown by user_agent
    rows = conn.execute("""
        SELECT date(ts) as day,
          CASE WHEN user_agent LIKE '%SemrushBot%' THEN 'Semrush'
               WHEN user_agent LIKE '%MJ12bot%' THEN 'Majestic'
               WHEN user_agent LIKE '%PetalBot%' THEN 'PetalBot'
               WHEN user_agent LIKE '%DotBot%' THEN 'Moz'
               WHEN user_agent LIKE '%AhrefsBot%' THEN 'Ahrefs'
               WHEN user_agent LIKE '%TikTokSpider%' THEN 'TikTok'
               WHEN user_agent LIKE '%DataForSeo%' THEN 'DataForSeo'
               WHEN user_agent LIKE '%Barkrowler%' THEN 'Babbar'
               WHEN user_agent LIKE '%curl%' THEN 'curl'
               ELSE 'Unknown'
          END as crawler, COUNT(*) as cnt
        FROM requests WHERE is_bot = 1 AND is_ai_bot = 0
          AND bot_name IN ('Other Bot','High-Volume Bot')
        GROUP BY day, crawler ORDER BY day, crawler
    """).fetchall()
    seo_crawlers = {}
    for day, crawler, cnt in rows:
        if crawler not in seo_crawlers:
            seo_crawlers[crawler] = {}
        seo_crawlers[crawler][day] = cnt
    data["seoCrawlers"] = seo_crawlers

    # Social per day
    rows = conn.execute("""
        SELECT date(ts) as day, referrer_domain, COUNT(*) as cnt
        FROM requests WHERE referrer_domain IN (
            'reddit.com','twitter.com','x.com','facebook.com',
            'linkedin.com','t.co','news.ycombinator.com'
        )
        GROUP BY day, referrer_domain ORDER BY day
    """).fetchall()
    social = {}
    _social_map = {
        "news.ycombinator.com": "HackerNews",
        "twitter.com": "X/Twitter", "x.com": "X/Twitter", "t.co": "X/Twitter",
        "facebook.com": "Facebook",
        "reddit.com": "Reddit",
        "linkedin.com": "LinkedIn",
    }
    for day, domain, cnt in rows:
        label = _social_map.get(domain, domain)
        if label not in social:
            social[label] = {}
        social[label][day] = social[label].get(day, 0) + cnt
    data["social"] = social

    # Preflight AI per source per day (from preflight_analytics)
    rows = conn.execute("""
        SELECT date(ts) as day,
          CASE
            WHEN bot_name IN ('ChatGPT','Claude','Perplexity','ByteDance') THEN bot_name
            ELSE 'Other'
          END as source,
          COUNT(*) as cnt
        FROM preflight_analytics
        WHERE bot_name IN ('ChatGPT','Claude','Perplexity','ByteDance')
        GROUP BY day, source ORDER BY day, source
    """).fetchall()
    pf = {}
    for day, src, cnt in rows:
        if src not in pf:
            pf[src] = {}
        pf[src][day] = cnt
    data["preflight"] = pf

    # Preflight non-AI per source per day
    rows = conn.execute("""
        SELECT date(ts) as day,
          CASE
            WHEN bot_name = 'Meta' THEN 'Meta'
            WHEN bot_name = 'Amazon' THEN 'Amazon'
            WHEN bot_name = 'Google' THEN 'Google'
            WHEN bot_name IS NULL OR bot_name = '' THEN 'Human'
            ELSE 'Other'
          END as source,
          COUNT(*) as cnt
        FROM preflight_analytics
        WHERE bot_name NOT IN ('ChatGPT','Claude','Perplexity','ByteDance')
           OR bot_name IS NULL
        GROUP BY day, source ORDER BY day, source
    """).fetchall()
    pf_non_ai = {}
    for day, src, cnt in rows:
        if src not in pf_non_ai:
            pf_non_ai[src] = {}
        pf_non_ai[src][day] = cnt
    data["preflightNonAI"] = pf_non_ai

    # Human visits per day
    rows = conn.execute("""
        SELECT date(ts) as day, COUNT(*) as cnt
        FROM requests WHERE is_bot = 0
        GROUP BY day ORDER BY day
    """).fetchall()
    data["humanVisits"] = {day: cnt for day, cnt in rows}

    # Human by country per day (top 10)
    top_countries = conn.execute("""
        SELECT country, COUNT(*) as cnt FROM requests
        WHERE is_bot = 0 AND country IS NOT NULL AND country != ''
        GROUP BY country ORDER BY cnt DESC LIMIT 10
    """).fetchall()
    top_cc = [r[0] for r in top_countries]

    if top_cc:
        placeholders = ",".join(f"'{c}'" for c in top_cc)
        rows = conn.execute(f"""
            SELECT date(ts) as day, country, COUNT(*) as cnt
            FROM requests WHERE is_bot = 0 AND country IN ({placeholders})
            GROUP BY day, country ORDER BY day, country
        """).fetchall()
        hbc = {}
        for day, cc, cnt in rows:
            if cc not in hbc:
                hbc[cc] = {}
            hbc[cc][day] = cnt
        data["humanByCountry"] = hbc
        data["topCountries"] = top_cc
    else:
        data["humanByCountry"] = {}
        data["topCountries"] = []

    # Language CASE expression
    _lang_case = """
        CASE
            WHEN path LIKE '/es/%' THEN 'es' WHEN path LIKE '/de/%' THEN 'de'
            WHEN path LIKE '/fr/%' THEN 'fr' WHEN path LIKE '/ja/%' THEN 'ja'
            WHEN path LIKE '/pt/%' THEN 'pt' WHEN path LIKE '/id/%' THEN 'id'
            WHEN path LIKE '/cs/%' THEN 'cs' WHEN path LIKE '/th/%' THEN 'th'
            WHEN path LIKE '/ro/%' THEN 'ro' WHEN path LIKE '/tr/%' THEN 'tr'
            WHEN path LIKE '/hi/%' THEN 'hi' WHEN path LIKE '/ru/%' THEN 'ru'
            WHEN path LIKE '/pl/%' THEN 'pl' WHEN path LIKE '/it/%' THEN 'it'
            WHEN path LIKE '/ko/%' THEN 'ko' WHEN path LIKE '/vi/%' THEN 'vi'
            WHEN path LIKE '/nl/%' THEN 'nl' WHEN path LIKE '/sv/%' THEN 'sv'
            WHEN path LIKE '/zh/%' THEN 'zh' WHEN path LIKE '/da/%' THEN 'da'
            WHEN path LIKE '/ar/%' THEN 'ar' WHEN path LIKE '/no/%' THEN 'no'
            ELSE 'en'
        END
    """

    # AI CITATIONS by language per day (status=200, excludes GPTBot indexing + preflight)
    rows = conn.execute(f"""
        SELECT date(ts) as day, {_lang_case} as lang, COUNT(*) as cnt
        FROM requests WHERE is_ai_bot = 1
          AND status = 200
          AND path NOT LIKE '/v1/preflight%'
          AND user_agent NOT LIKE '%GPTBot%'
        GROUP BY day, lang ORDER BY day, lang
    """).fetchall()
    abl = {}
    for day, lang, cnt in rows:
        if lang not in abl:
            abl[lang] = {}
        abl[lang][day] = cnt
    data["aiByLang"] = abl

    # Human visits by language per day
    rows = conn.execute(f"""
        SELECT date(ts) as day, {_lang_case} as lang, COUNT(*) as cnt
        FROM requests WHERE is_bot = 0
        GROUP BY day, lang ORDER BY day, lang
    """).fetchall()
    hbl = {}
    for day, lang, cnt in rows:
        if lang not in hbl:
            hbl[lang] = {}
        hbl[lang][day] = cnt
    data["humanByLang"] = hbl

    conn.close()
    data["generated_at"] = datetime.now().isoformat()
    return data


def _get_cached_data():
    """File-based cache, 10min TTL."""
    try:
        if os.path.exists(_CACHE_FILE):
            age = time.time() - os.path.getmtime(_CACHE_FILE)
            if age < _CACHE_TTL:
                with open(_CACHE_FILE) as f:
                    return json.load(f)
    except Exception:
        pass

    data = _query_data()
    try:
        with open(_CACHE_FILE + ".tmp", "w") as f:
            json.dump(data, f)
        os.replace(_CACHE_FILE + ".tmp", _CACHE_FILE)
    except Exception:
        pass
    return data


def _render_html(data):
    """Render the dashboard HTML with data injected as JS objects."""
    from datetime import timedelta
    today = date.today().isoformat()
    _d0 = date(2026, 2, 23)
    _days_list = []
    _d = _d0
    while _d <= date.today():
        _days_list.append(_d.isoformat())
        _d += timedelta(days=1)

    # Country label map
    _cc_names = {
        "US": "United States", "VN": "Vietnam", "SE": "Sweden", "CN": "China",
        "CA": "Canada", "DE": "Germany", "FR": "France", "SG": "Singapore",
        "RU": "Russia", "FI": "Finland", "BR": "Brazil", "IN": "India",
        "GB": "United Kingdom", "HK": "Hong Kong", "MX": "Mexico",
        "BD": "Bangladesh", "PK": "Pakistan", "CO": "Colombia",
        "IQ": "Iraq", "JP": "Japan", "KR": "South Korea",
    }

    # Build country rows JS
    hbc = data.get("humanByCountry", {})
    top_cc = data.get("topCountries", [])
    country_rows_js = ",\n".join(
        f"  {{ key: '{cc.lower()}', label: '{_cc_names.get(cc, cc)}', data: {json.dumps(hbc.get(cc, {}))} }}"
        for cc in top_cc
    )

    # Build lang rows
    lang_order = ['en', 'id', 'cs', 'th', 'de', 'es', 'fr', 'ja', 'pt', 'ro', 'hi', 'ru', 'tr', 'pl', 'it', 'ko', 'vi', 'nl', 'sv', 'da', 'zh', 'ar', 'no']
    ai_lang = data.get("aiByLang", {})
    human_lang = data.get("humanByLang", {})
    ai_lang_rows = ",\n".join(
        f"  {{ key: '{l}', label: '{l.upper()}', data: {json.dumps(ai_lang.get(l, {}))} }}"
        for l in lang_order if l in ai_lang
    )
    human_lang_rows = ",\n".join(
        f"  {{ key: '{l}', label: '{l.upper()}', data: {json.dumps(human_lang.get(l, {}))} }}"
        for l in lang_order if l in human_lang
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>Nerq Analytics Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #0c0e13; --bg2: #141720; --bg3: #1a1e2a; --border: #252a3a;
  --text: #e4e6ed; --text2: #8b90a0; --text3: #555a6e;
  --accent: #6c8cff; --green: #4ade80; --amber: #f59e0b; --red: #ef4444;
  --teal: #2dd4bf; --purple: #a78bfa; --pink: #f472b6; --coral: #fb923c;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: var(--bg); color: var(--text); font-family: 'DM Sans', sans-serif; padding: 24px; }}
h1 {{ font-size: 22px; font-weight: 600; margin-bottom: 4px; }}
.subtitle {{ color: var(--text2); font-size: 13px; margin-bottom: 24px; }}
.section {{ margin-bottom: 32px; }}
.section-title {{ font-size: 14px; font-weight: 600; color: var(--text2); text-transform: uppercase; letter-spacing: 1.2px; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }}
.table-wrap {{ overflow-x: auto; border-radius: 8px; border: 1px solid var(--border); }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; font-family: 'JetBrains Mono', monospace; }}
th {{ background: var(--bg3); color: var(--text2); font-weight: 500; text-align: right; padding: 8px 10px; position: sticky; top: 0; white-space: nowrap; }}
th:first-child {{ text-align: left; position: sticky; left: 0; z-index: 2; background: var(--bg3); }}
td {{ padding: 6px 10px; text-align: right; border-top: 1px solid var(--border); white-space: nowrap; }}
td:first-child {{ text-align: left; position: sticky; left: 0; background: var(--bg2); z-index: 1; font-weight: 500; color: var(--text); }}
tr:hover td {{ background: var(--bg3); }}
tr:hover td:first-child {{ background: var(--bg3); }}
tr.total-row td {{ border-top: 2px solid var(--accent); font-weight: 600; color: var(--accent); background: rgba(108,140,255,0.05); }}
tr.total-row td:first-child {{ background: rgba(108,140,255,0.05); }}
tr.subtotal-row td {{ border-top: 1.5px solid var(--border); font-weight: 500; color: var(--teal); }}
.dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }}
.num {{ color: var(--text); }}
.zero {{ color: var(--text3); }}
.today {{ background: rgba(108,140,255,0.08); }}
</style>
</head>
<body>
<h1>Nerq — Daily Analytics Dashboard</h1>
<p class="subtitle">All traffic data from analytics.db · Cached {_CACHE_TTL // 60}min · Generated {data.get('generated_at', '')[:19]} · <a href="/admin/analytics-weekly" style="color:var(--accent)">Weekly view &rarr;</a></p>
<div id="app"></div>
<script>
const days = {json.dumps(_days_list)};
const today = '{today}';

const summary = {json.dumps(data.get('summary', {}))};
const aiCitations = {json.dumps(data.get('aiCitations', {}))};
const aiIndexing = {json.dumps(data.get('aiIndexing', {}))};
const searchCrawls = {json.dumps(data.get('searchCrawls', {}))};
const otherCrawlers = {json.dumps(data.get('otherCrawlers', {}))};
const aiErrors = {json.dumps(data.get('aiErrors', {}))};
const seoCrawlers = {json.dumps(data.get('seoCrawlers', {}))};
const social = {json.dumps(data.get('social', {}))};
const preflight = {json.dumps(data.get('preflight', {}))};
const preflightNonAI = {json.dumps(data.get('preflightNonAI', {}))};
const humanVisits = {json.dumps(data.get('humanVisits', {}))};
const humanByCountry = {json.dumps(data.get('humanByCountry', {}))};
const aiByLang = {json.dumps(data.get('aiByLang', {}))};
const humanByLang = {json.dumps(data.get('humanByLang', {}))};
const newAiPlatforms = {json.dumps(data.get('newAiPlatforms', {}))};

function fmt(n) {{
  if (n === 0) return '<span class="zero">–</span>';
  if (n >= 1000) return n.toLocaleString('en-US');
  return String(n);
}}

function buildTable(id, title, rowDefs, options = {{}}) {{
  const {{ showTotal = true, totalLabel = 'TOTAL', dotColors = {{}} }} = options;
  let firstDay = days.length;
  for (const row of rowDefs) {{
    if (row.type === 'total' || row.type === 'subtotal') continue;
    for (let i = 0; i < days.length; i++) {{
      if ((row.data[days[i]] || 0) > 0 && i < firstDay) firstDay = i;
    }}
  }}
  const startIdx = Math.max(firstDay, days.length - 34);
  const visibleDays = days.slice(startIdx);

  let html = `<div class="section"><div class="section-title">${{title}}</div><div class="table-wrap"><table><thead><tr><th></th>`;
  for (const d of visibleDays) {{
    const cls = d === today ? ' class="today"' : '';
    html += `<th${{cls}}>${{d.slice(5)}}</th>`;
  }}
  html += '</tr></thead><tbody>';

  for (const row of rowDefs) {{
    if (row.type === 'total') {{
      html += '<tr class="total-row"><td>' + row.label + '</td>';
      for (const d of visibleDays) {{
        let sum = 0;
        for (const r of rowDefs) {{
          if (r.type !== 'total' && r.type !== 'subtotal' && (!row.scope || row.scope.includes(r.key))) {{
            sum += (r.data[d] || 0);
          }}
        }}
        const cls = d === today ? ' class="today"' : '';
        html += `<td${{cls}}>${{fmt(sum)}}</td>`;
      }}
      html += '</tr>';
    }} else if (row.type === 'subtotal') {{
      html += '<tr class="subtotal-row"><td>' + row.label + '</td>';
      for (const d of visibleDays) {{
        let sum = 0;
        for (const r of rowDefs) {{
          if (row.scope.includes(r.key)) {{
            sum += (r.data[d] || 0);
          }}
        }}
        const cls = d === today ? ' class="today"' : '';
        html += `<td${{cls}}>${{fmt(sum)}}</td>`;
      }}
      html += '</tr>';
    }} else {{
      const dot = dotColors[row.key] ? `<span class="dot" style="background:${{dotColors[row.key]}}"></span>` : '';
      html += `<tr><td>${{dot}}${{row.label}}</td>`;
      for (const d of visibleDays) {{
        const v = row.data[d] || 0;
        const cls = d === today ? ' class="today"' : '';
        html += `<td${{cls}}>${{fmt(v)}}</td>`;
      }}
      html += '</tr>';
    }}
  }}
  html += '</tbody></table></div></div>';
  return html;
}}

let out = '';

// 1. SUMMARY — all categories per day
out += buildTable('summary', 'Summary &mdash; all traffic categories', [
  {{ key: 'human', label: 'Human visits', data: summary.human || {{}} }},
  {{ key: 'ai_cite', label: 'AI Citations (200, excl GPTBot)', data: summary.ai_cite || {{}} }},
  {{ key: 'ai_index', label: 'AI Indexing (GPTBot 200)', data: summary.ai_index || {{}} }},
  {{ key: 'ai_pf', label: 'AI Preflight (AI bots)', data: summary.ai_preflight || {{}} }},
  {{ type: 'subtotal', label: 'Valuable traffic', scope: ['human','ai_cite','ai_pf'] }},
  {{ key: 'ai_err', label: 'AI Errors (non-200)', data: summary.ai_errors || {{}} }},
  {{ key: 'search', label: 'Search Engines', data: summary.search || {{}} }},
  {{ key: 'meta', label: 'Meta', data: summary.meta || {{}} }},
  {{ key: 'amazon', label: 'Amazon', data: summary.amazon || {{}} }},
  {{ key: 'other_bots', label: 'SEO/Other Bots', data: summary.other_bots || {{}} }},
  {{ type: 'total', label: 'TOTAL ALL REQUESTS' }}
], {{ dotColors: {{ human: '#4ade80', ai_cite: '#8b5cf6', ai_index: '#10a37f', ai_pf: '#6c8cff', ai_err: '#ef4444', search: '#f59e0b', meta: '#1877f2', amazon: '#ff9900', other_bots: '#888' }}}});

// 2. AI CITATIONS
out += buildTable('citations', 'AI Citations (answering user queries)', [
  {{ key: 'chatgpt', label: 'ChatGPT (SearchBot+User)', data: aiCitations['ChatGPT'] || {{}} }},
  {{ key: 'claude', label: 'Claude', data: aiCitations['Claude'] || {{}} }},
  {{ key: 'perplexity', label: 'Perplexity', data: aiCitations['Perplexity'] || {{}} }},
  {{ key: 'bytedance', label: 'ByteDance', data: aiCitations['ByteDance'] || {{}} }},
  {{ type: 'total', label: 'TOTAL AI CITATIONS' }}
], {{ dotColors: {{ chatgpt: '#10a37f', claude: '#d97706', perplexity: '#6c8cff', bytedance: '#ff004f' }}}});

// 3. AI INDEXING
out += buildTable('indexing', 'AI Indexing (GPTBot)', [
  {{ key: 'gptbot', label: 'GPTBot', data: aiIndexing }},
], {{ dotColors: {{ gptbot: '#10a37f' }}}});

// 3b. NEW AI PLATFORMS
const newAi = newAiPlatforms || {{}};
out += buildTable('newai', 'AI Crawling &mdash; New Platforms (all status codes)', [
  {{ key: 'sogou', label: 'Sogou', data: newAi['Sogou'] || {{}} }},
  {{ key: 'duckduckbot', label: 'DuckDuckBot', data: newAi['DuckDuckBot'] || {{}} }},
  {{ key: 'baidu', label: 'Baidu', data: newAi['Baidu'] || {{}} }},
  {{ key: 'notebooklm', label: 'NotebookLM', data: newAi['NotebookLM'] || {{}} }},
  {{ key: 'coccoc', label: 'CocCoc', data: newAi['CocCoc'] || {{}} }},
  {{ key: 'naver', label: 'Naver', data: newAi['Naver'] || {{}} }},
  {{ key: 'linkedin', label: 'LinkedIn', data: newAi['LinkedIn'] || {{}} }},
  {{ key: 'grok', label: 'Grok', data: newAi['Grok'] || {{}} }},
  {{ key: 'deepseek', label: 'DeepSeek', data: newAi['DeepSeek'] || {{}} }},
  {{ key: 'mistral', label: 'Mistral', data: newAi['Mistral'] || {{}} }},
  {{ key: 'brave', label: 'Brave', data: newAi['Brave'] || {{}} }},
  {{ key: 'kagi', label: 'Kagi', data: newAi['Kagi'] || {{}} }},
  {{ type: 'total', label: 'TOTAL NEW AI PLATFORMS' }}
], {{ dotColors: {{ sogou: '#8B4513', duckduckbot: '#de5833', baidu: '#2319dc', notebooklm: '#4285f4', coccoc: '#00b14f', naver: '#03c75a', linkedin: '#0a66c2', grok: '#1da1f2', deepseek: '#0066ff', mistral: '#ff6b35', brave: '#fb542b', kagi: '#6b21a8' }}}});

// 4. AI ERRORS (by status code)
out += buildTable('aierrors', 'AI Errors (non-200 by status code)', [
  {{ key: 's404', label: '404 Not Found', data: aiErrors['404'] || {{}} }},
  {{ key: 's301', label: '301 Redirect', data: aiErrors['301'] || {{}} }},
  {{ key: 's429', label: '429 Rate Limited', data: aiErrors['429'] || {{}} }},
  {{ key: 's410', label: '410 Gone', data: aiErrors['410'] || {{}} }},
  {{ key: 's500', label: '500 Server Error', data: aiErrors['500'] || {{}} }},
  {{ key: 's302', label: '302 Redirect', data: aiErrors['302'] || {{}} }},
  {{ type: 'total', label: 'TOTAL AI ERRORS' }}
], {{ dotColors: {{ s404: '#ef4444', s301: '#f59e0b', s429: '#fb923c', s410: '#888', s500: '#dc2626', s302: '#f59e0b' }}}});

// 5. AI PREFLIGHT (AI bots only)
out += buildTable('preflight', 'AI Preflight (/v1/preflight &mdash; AI bots only)', [
  {{ key: 'chatgpt', label: 'ChatGPT', data: preflight['ChatGPT'] || {{}} }},
  {{ key: 'claude', label: 'Claude', data: preflight['Claude'] || {{}} }},
  {{ key: 'perplexity', label: 'Perplexity', data: preflight['Perplexity'] || {{}} }},
  {{ key: 'bytedance', label: 'ByteDance', data: preflight['ByteDance'] || {{}} }},
  {{ type: 'total', label: 'TOTAL AI PREFLIGHT' }}
], {{ dotColors: {{ chatgpt: '#10a37f', claude: '#d97706', perplexity: '#6c8cff', bytedance: '#ff004f' }}}});

// 6. NON-AI PREFLIGHT
out += buildTable('pfnonai', 'Non-AI Preflight callers', [
  {{ key: 'meta', label: 'Meta', data: preflightNonAI['Meta'] || {{}} }},
  {{ key: 'amazon', label: 'Amazon', data: preflightNonAI['Amazon'] || {{}} }},
  {{ key: 'google', label: 'Google', data: preflightNonAI['Google'] || {{}} }},
  {{ key: 'human', label: 'Human', data: preflightNonAI['Human'] || {{}} }},
  {{ key: 'other', label: 'Other', data: preflightNonAI['Other'] || {{}} }},
  {{ type: 'total', label: 'TOTAL NON-AI PREFLIGHT' }}
], {{ dotColors: {{ meta: '#1877f2', amazon: '#ff9900', google: '#4285f4', human: '#4ade80', other: '#888' }}}});

// 7. TOTAL AI ENGAGEMENT (citations + AI preflight)
const aiEngagementData = {{}};
for (const d of days) {{
  let sum = 0;
  for (const bot of Object.values(aiCitations)) sum += (bot[d] || 0);
  for (const p of ['ChatGPT','Claude','Perplexity','ByteDance']) sum += (preflight[p]?.[d] || 0);
  aiEngagementData[d] = sum;
}}
out += buildTable('engagement', 'Total AI Engagement (citations + AI preflight)', [
  {{ key: 'total', label: 'AI citations + AI preflight', data: aiEngagementData }},
], {{}});

// 8. SEARCH ENGINE CRAWLS
out += buildTable('search', 'Search Engine Crawls', [
  {{ key: 'google', label: 'Google', data: searchCrawls['Google'] || {{}} }},
  {{ key: 'bing', label: 'Bing', data: searchCrawls['Bing'] || {{}} }},
  {{ key: 'yandex', label: 'Yandex', data: searchCrawls['Yandex'] || {{}} }},
  {{ key: 'apple', label: 'Apple', data: searchCrawls['Apple'] || {{}} }},
  {{ key: 'duckduck', label: 'DuckDuckGo', data: searchCrawls['DuckDuck'] || {{}} }},
  {{ type: 'total', label: 'TOTAL SEARCH CRAWLS' }}
], {{ dotColors: {{ google: '#4285f4', bing: '#00809d', yandex: '#ff0000', apple: '#999', duckduck: '#de5833' }}}});

// 9. META CRAWLER
out += buildTable('meta', 'Meta (meta-externalagent)', [
  {{ key: 'meta', label: 'Meta', data: otherCrawlers['Meta'] || {{}} }},
], {{ dotColors: {{ meta: '#1877f2' }}}});

// 10. AMAZON CRAWLER
out += buildTable('amazon', 'Amazon (Amazonbot)', [
  {{ key: 'amazon', label: 'Amazon', data: otherCrawlers['Amazon'] || {{}} }},
], {{ dotColors: {{ amazon: '#ff9900' }}}});

// 11. SEO/OTHER CRAWLER BREAKDOWN
out += buildTable('seocrawlers', 'SEO &amp; Other Crawlers (breakdown)', [
  {{ key: 'semrush', label: 'Semrush', data: seoCrawlers['Semrush'] || {{}} }},
  {{ key: 'majestic', label: 'Majestic', data: seoCrawlers['Majestic'] || {{}} }},
  {{ key: 'petalbot', label: 'PetalBot (Huawei)', data: seoCrawlers['PetalBot'] || {{}} }},
  {{ key: 'moz', label: 'Moz (DotBot)', data: seoCrawlers['Moz'] || {{}} }},
  {{ key: 'ahrefs', label: 'Ahrefs', data: seoCrawlers['Ahrefs'] || {{}} }},
  {{ key: 'tiktok', label: 'TikTok', data: seoCrawlers['TikTok'] || {{}} }},
  {{ key: 'dataforseo', label: 'DataForSeo', data: seoCrawlers['DataForSeo'] || {{}} }},
  {{ key: 'babbar', label: 'Babbar', data: seoCrawlers['Babbar'] || {{}} }},
  {{ key: 'curl', label: 'curl', data: seoCrawlers['curl'] || {{}} }},
  {{ key: 'unknown', label: 'Unknown', data: seoCrawlers['Unknown'] || {{}} }},
  {{ type: 'total', label: 'TOTAL SEO/OTHER' }}
], {{ dotColors: {{ semrush: '#ff642d', majestic: '#e6194b', petalbot: '#e11d48', moz: '#118dff', ahrefs: '#ff8c00', tiktok: '#000', dataforseo: '#888', babbar: '#888', curl: '#888', unknown: '#555' }}}});

// 12. SOCIAL TRAFFIC
out += buildTable('social', 'Social Traffic', [
  {{ key: 'hn', label: 'Hacker News', data: social['HackerNews'] || {{}} }},
  {{ key: 'twitter', label: 'X / Twitter', data: social['X/Twitter'] || {{}} }},
  {{ key: 'fb', label: 'Facebook', data: social['Facebook'] || {{}} }},
  {{ key: 'reddit', label: 'Reddit', data: social['Reddit'] || {{}} }},
  {{ key: 'linkedin', label: 'LinkedIn', data: social['LinkedIn'] || {{}} }},
  {{ type: 'total', label: 'TOTAL SOCIAL' }}
], {{ dotColors: {{ hn: '#ff6600', twitter: '#1da1f2', fb: '#1877f2', reddit: '#ff4500', linkedin: '#0a66c2' }}}});

// 13. HUMAN VISITS
out += buildTable('human', 'Human Visits', [
  {{ key: 'human', label: 'Human visits', data: humanVisits }},
], {{}});

// 14. HUMAN BY COUNTRY
out += buildTable('humancountry', 'Human Visits by Country (top 10)', [
{country_rows_js},
  {{ type: 'total', label: 'TOTAL (top 10)' }}
], {{}});

// 15. AI CITATIONS BY LANGUAGE
out += buildTable('ailang', 'AI Citations by Language', [
{ai_lang_rows},
  {{ type: 'total', label: 'TOTAL' }}
], {{}});

// 16. HUMAN VISITS BY LANGUAGE
out += buildTable('humanlang', 'Human Visits by Language', [
{human_lang_rows},
  {{ type: 'total', label: 'TOTAL' }}
], {{}});

document.getElementById('app').innerHTML = out;
</script>
</body>
</html>"""


def mount_analytics_dashboard(app):
    @app.get("/admin/analytics-dashboard", response_class=HTMLResponse)
    async def analytics_dashboard_page():
        import asyncio
        data = await asyncio.to_thread(_get_cached_data)
        return HTMLResponse(content=_render_html(data))

    logger.info("Mounted /admin/analytics-dashboard")
