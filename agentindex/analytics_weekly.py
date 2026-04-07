"""
Nerq Analytics Weekly Dashboard — /admin/analytics-weekly
Same design as analytics-dashboard but with WEEKS as columns.
File-based cache, 30min TTL.
"""
import json
import logging
import os
import sqlite3
import time
from datetime import date, datetime

from fastapi import Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger("nerq.analytics_weekly")

ANALYTICS_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "analytics.db")
_CACHE_FILE = "/tmp/nerq_analytics_weekly.json"
_CACHE_TTL = 1800  # 30 minutes


def _query_data():
    """Run all queries grouped by ISO week."""
    conn = sqlite3.connect(ANALYTICS_DB, timeout=30)
    data = {}

    _week = "strftime('%Y-W%W', ts)"

    # 0. SUMMARY per week
    rows = conn.execute(f"""
        SELECT {_week} as wk,
          SUM(CASE WHEN is_bot = 0 THEN 1 ELSE 0 END) as human,
          SUM(CASE WHEN is_ai_bot = 1 AND status = 200 AND path NOT LIKE '/v1/preflight%' AND user_agent NOT LIKE '%GPTBot%' THEN 1 ELSE 0 END) as ai_cite,
          SUM(CASE WHEN is_ai_bot = 1 AND status = 200 AND path NOT LIKE '/v1/preflight%' AND user_agent LIKE '%GPTBot%' THEN 1 ELSE 0 END) as ai_index,
          SUM(CASE WHEN is_ai_bot = 1 AND status != 200 THEN 1 ELSE 0 END) as ai_errors,
          SUM(CASE WHEN is_bot = 1 AND is_ai_bot = 0 AND bot_name IN ('Google','Bing','Yandex','DuckDuck','Apple') THEN 1 ELSE 0 END) as search,
          SUM(CASE WHEN bot_name = 'Meta' THEN 1 ELSE 0 END) as meta,
          SUM(CASE WHEN bot_name = 'Amazon' THEN 1 ELSE 0 END) as amazon,
          SUM(CASE WHEN is_bot = 1 AND is_ai_bot = 0 AND bot_name NOT IN ('Google','Bing','Yandex','DuckDuck','Apple','Meta','Amazon') THEN 1 ELSE 0 END) as other_bots,
          COUNT(*) as total
        FROM requests GROUP BY wk ORDER BY wk
    """).fetchall()
    summary = {}
    for k in ["human", "ai_cite", "ai_index", "ai_errors", "search", "meta", "amazon", "other_bots", "total"]:
        summary[k] = {}
    for r in rows:
        wk = r[0]
        for i, k in enumerate(["human", "ai_cite", "ai_index", "ai_errors", "search", "meta", "amazon", "other_bots", "total"], 1):
            summary[k][wk] = r[i] or 0
    data["summary"] = summary

    # AI Preflight per week
    pf_rows = conn.execute(f"""
        SELECT {_week.replace('ts', 'ts')} as wk, COUNT(*) as cnt
        FROM preflight_analytics WHERE bot_name IN ('ChatGPT','Claude','Perplexity','ByteDance')
        GROUP BY wk ORDER BY wk
    """).fetchall()
    data["summary"]["ai_preflight"] = {wk: cnt for wk, cnt in pf_rows}

    # 1. AI CITATIONS per bot per week
    rows = conn.execute(f"""
        SELECT {_week} as wk, bot_name, COUNT(*) as cnt
        FROM requests WHERE is_ai_bot = 1 AND status = 200
          AND path NOT LIKE '/v1/preflight%' AND user_agent NOT LIKE '%GPTBot%'
        GROUP BY wk, bot_name ORDER BY wk, bot_name
    """).fetchall()
    citations = {}
    for wk, bot, cnt in rows:
        if bot not in citations:
            citations[bot] = {}
        citations[bot][wk] = cnt
    data["aiCitations"] = citations

    # 2. AI INDEXING per week
    rows = conn.execute(f"""
        SELECT {_week} as wk, COUNT(*) as cnt
        FROM requests WHERE is_ai_bot = 1 AND status = 200
          AND path NOT LIKE '/v1/preflight%' AND user_agent LIKE '%GPTBot%'
        GROUP BY wk ORDER BY wk
    """).fetchall()
    data["aiIndexing"] = {wk: cnt for wk, cnt in rows}

    # Search crawls per bot per week
    rows = conn.execute(f"""
        SELECT {_week} as wk, bot_name, COUNT(*) as cnt
        FROM requests WHERE is_bot = 1 AND is_ai_bot = 0
          AND bot_name IN ('Google','Bing','Yandex','DuckDuck','Apple')
        GROUP BY wk, bot_name ORDER BY wk, bot_name
    """).fetchall()
    search = {}
    for wk, bot, cnt in rows:
        if bot not in search:
            search[bot] = {}
        search[bot][wk] = cnt
    data["searchCrawls"] = search

    # Other crawlers per week
    rows = conn.execute(f"""
        SELECT {_week} as wk, bot_name, COUNT(*) as cnt
        FROM requests WHERE is_bot = 1 AND is_ai_bot = 0
          AND bot_name IN ('Meta','Amazon')
        GROUP BY wk, bot_name ORDER BY wk, bot_name
    """).fetchall()
    oc = {}
    for wk, bot, cnt in rows:
        if bot not in oc:
            oc[bot] = {}
        oc[bot][wk] = cnt
    data["otherCrawlers"] = oc

    # AI Errors per status code per week
    rows = conn.execute(f"""
        SELECT {_week} as wk, CAST(status AS TEXT) as sc, COUNT(*) as cnt
        FROM requests WHERE is_ai_bot = 1 AND status != 200
        GROUP BY wk, sc ORDER BY wk, sc
    """).fetchall()
    ae = {}
    for wk, sc, cnt in rows:
        if sc not in ae:
            ae[sc] = {}
        ae[sc][wk] = cnt
    data["aiErrors"] = ae

    # SEO/Other crawlers breakdown per week
    rows = conn.execute(f"""
        SELECT {_week} as wk,
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
        GROUP BY wk, crawler ORDER BY wk, crawler
    """).fetchall()
    sc = {}
    for wk, crawler, cnt in rows:
        if crawler not in sc:
            sc[crawler] = {}
        sc[crawler][wk] = cnt
    data["seoCrawlers"] = sc

    # Social per week
    rows = conn.execute(f"""
        SELECT {_week} as wk, referrer_domain, COUNT(*) as cnt
        FROM requests WHERE referrer_domain IN (
            'reddit.com','twitter.com','x.com','facebook.com',
            'linkedin.com','t.co','news.ycombinator.com')
        GROUP BY wk, referrer_domain ORDER BY wk
    """).fetchall()
    social = {}
    _sm = {"news.ycombinator.com": "HackerNews", "twitter.com": "X/Twitter",
           "x.com": "X/Twitter", "t.co": "X/Twitter", "facebook.com": "Facebook",
           "reddit.com": "Reddit", "linkedin.com": "LinkedIn"}
    for wk, domain, cnt in rows:
        label = _sm.get(domain, domain)
        if label not in social:
            social[label] = {}
        social[label][wk] = social[label].get(wk, 0) + cnt
    data["social"] = social

    # Preflight AI per week
    rows = conn.execute(f"""
        SELECT strftime('%Y-W%W', ts) as wk, bot_name, COUNT(*) as cnt
        FROM preflight_analytics
        WHERE bot_name IN ('ChatGPT','Claude','Perplexity','ByteDance')
        GROUP BY wk, bot_name ORDER BY wk, bot_name
    """).fetchall()
    pf = {}
    for wk, src, cnt in rows:
        if src not in pf:
            pf[src] = {}
        pf[src][wk] = cnt
    data["preflight"] = pf

    # Human visits per week
    rows = conn.execute(f"""
        SELECT {_week} as wk, COUNT(*) as cnt FROM requests WHERE is_bot = 0
        GROUP BY wk ORDER BY wk
    """).fetchall()
    data["humanVisits"] = {wk: cnt for wk, cnt in rows}

    # AI by language per week
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
            WHEN path LIKE '/ar/%' THEN 'ar'
            ELSE 'en'
        END
    """
    rows = conn.execute(f"""
        SELECT {_week} as wk, {_lang_case} as lang, COUNT(*) as cnt
        FROM requests WHERE is_ai_bot = 1 AND status = 200
          AND path NOT LIKE '/v1/preflight%' AND user_agent NOT LIKE '%GPTBot%'
        GROUP BY wk, lang ORDER BY wk, lang
    """).fetchall()
    abl = {}
    for wk, lang, cnt in rows:
        if lang not in abl:
            abl[lang] = {}
        abl[lang][wk] = cnt
    data["aiByLang"] = abl

    # Human by language per week
    rows = conn.execute(f"""
        SELECT {_week} as wk, {_lang_case} as lang, COUNT(*) as cnt
        FROM requests WHERE is_bot = 0
        GROUP BY wk, lang ORDER BY wk, lang
    """).fetchall()
    hbl = {}
    for wk, lang, cnt in rows:
        if lang not in hbl:
            hbl[lang] = {}
        hbl[lang][wk] = cnt
    data["humanByLang"] = hbl

    conn.close()
    data["generated_at"] = datetime.now().isoformat()
    return data


def _get_cached_data():
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
    # Build week list from summary keys
    all_weeks = sorted(set().union(*(set(v.keys()) for v in data.get("summary", {}).values() if isinstance(v, dict))))
    current_week = date.today().strftime("%Y-W%W")

    lang_order = ['en', 'id', 'cs', 'th', 'de', 'es', 'fr', 'ja', 'pt', 'ro', 'hi', 'ru', 'tr', 'pl', 'it', 'ko', 'vi', 'nl', 'sv', 'da', 'zh', 'ar', 'no']  # 23 langs incl Norwegian (added Dag 31)
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
<title>Nerq Analytics — Weekly</title>
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
.current {{ background: rgba(108,140,255,0.08); }}
</style>
</head>
<body>
<h1>Nerq — Weekly Analytics Dashboard</h1>
<p class="subtitle">Grouped by ISO week · Cached {_CACHE_TTL // 60}min · Generated {data.get('generated_at', '')[:19]} · <a href="/admin/analytics-dashboard" style="color:var(--accent)">&larr; Daily view</a></p>
<div id="app"></div>
<script>
const weeks = {json.dumps(all_weeks)};
const currentWeek = '{current_week}';

const summary = {json.dumps(data.get('summary', {}))};
const aiCitations = {json.dumps(data.get('aiCitations', {}))};
const aiIndexing = {json.dumps(data.get('aiIndexing', {}))};
const searchCrawls = {json.dumps(data.get('searchCrawls', {}))};
const otherCrawlers = {json.dumps(data.get('otherCrawlers', {}))};
const aiErrors = {json.dumps(data.get('aiErrors', {}))};
const seoCrawlers = {json.dumps(data.get('seoCrawlers', {}))};
const social = {json.dumps(data.get('social', {}))};
const preflight = {json.dumps(data.get('preflight', {}))};
const humanVisits = {json.dumps(data.get('humanVisits', {}))};
const aiByLang = {json.dumps(data.get('aiByLang', {}))};
const humanByLang = {json.dumps(data.get('humanByLang', {}))};

function fmt(n) {{
  if (n === 0) return '<span class="zero">&ndash;</span>';
  if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
  if (n >= 1000) return n.toLocaleString('en-US');
  return String(n);
}}

function buildTable(id, title, rowDefs, options = {{}}) {{
  const {{ dotColors = {{}} }} = options;
  const visibleWeeks = weeks.slice(-16);

  let html = `<div class="section"><div class="section-title">${{title}}</div><div class="table-wrap"><table><thead><tr><th></th>`;
  for (const w of visibleWeeks) {{
    const wn = w.split('-W')[1];
    const cls = w === currentWeek ? ' class="current"' : '';
    html += `<th${{cls}}>W${{wn}}</th>`;
  }}
  html += '</tr></thead><tbody>';

  for (const row of rowDefs) {{
    if (row.type === 'total') {{
      html += '<tr class="total-row"><td>' + row.label + '</td>';
      for (const w of visibleWeeks) {{
        let sum = 0;
        for (const r of rowDefs) {{
          if (r.type !== 'total' && r.type !== 'subtotal' && (!row.scope || row.scope.includes(r.key))) {{
            sum += (r.data[w] || 0);
          }}
        }}
        const cls = w === currentWeek ? ' class="current"' : '';
        html += `<td${{cls}}>${{fmt(sum)}}</td>`;
      }}
      html += '</tr>';
    }} else if (row.type === 'subtotal') {{
      html += '<tr class="subtotal-row"><td>' + row.label + '</td>';
      for (const w of visibleWeeks) {{
        let sum = 0;
        for (const r of rowDefs) {{
          if (row.scope.includes(r.key)) sum += (r.data[w] || 0);
        }}
        const cls = w === currentWeek ? ' class="current"' : '';
        html += `<td${{cls}}>${{fmt(sum)}}</td>`;
      }}
      html += '</tr>';
    }} else {{
      const dot = dotColors[row.key] ? `<span class="dot" style="background:${{dotColors[row.key]}}"></span>` : '';
      html += `<tr><td>${{dot}}${{row.label}}</td>`;
      for (const w of visibleWeeks) {{
        const v = row.data[w] || 0;
        const cls = w === currentWeek ? ' class="current"' : '';
        html += `<td${{cls}}>${{fmt(v)}}</td>`;
      }}
      html += '</tr>';
    }}
  }}
  html += '</tbody></table></div></div>';
  return html;
}}

let out = '';

out += buildTable('summary', 'Summary &mdash; all traffic categories (weekly)', [
  {{ key: 'human', label: 'Human visits', data: summary.human || {{}} }},
  {{ key: 'ai_cite', label: 'AI Citations', data: summary.ai_cite || {{}} }},
  {{ key: 'ai_index', label: 'AI Indexing (GPTBot)', data: summary.ai_index || {{}} }},
  {{ key: 'ai_pf', label: 'AI Preflight (AI bots)', data: summary.ai_preflight || {{}} }},
  {{ type: 'subtotal', label: 'Valuable traffic', scope: ['human','ai_cite','ai_pf'] }},
  {{ key: 'ai_err', label: 'AI Errors', data: summary.ai_errors || {{}} }},
  {{ key: 'search', label: 'Search Engines', data: summary.search || {{}} }},
  {{ key: 'meta', label: 'Meta', data: summary.meta || {{}} }},
  {{ key: 'amazon', label: 'Amazon', data: summary.amazon || {{}} }},
  {{ key: 'other_bots', label: 'SEO/Other Bots', data: summary.other_bots || {{}} }},
  {{ type: 'total', label: 'TOTAL' }}
], {{ dotColors: {{ human: '#4ade80', ai_cite: '#8b5cf6', ai_index: '#10a37f', ai_pf: '#6c8cff', ai_err: '#ef4444', search: '#f59e0b', meta: '#1877f2', amazon: '#ff9900', other_bots: '#888' }}}});

out += buildTable('citations', 'AI Citations', [
  {{ key: 'chatgpt', label: 'ChatGPT', data: aiCitations['ChatGPT'] || {{}} }},
  {{ key: 'claude', label: 'Claude', data: aiCitations['Claude'] || {{}} }},
  {{ key: 'perplexity', label: 'Perplexity', data: aiCitations['Perplexity'] || {{}} }},
  {{ key: 'bytedance', label: 'ByteDance', data: aiCitations['ByteDance'] || {{}} }},
  {{ type: 'total', label: 'TOTAL' }}
], {{ dotColors: {{ chatgpt: '#10a37f', claude: '#d97706', perplexity: '#6c8cff', bytedance: '#ff004f' }}}});

out += buildTable('indexing', 'AI Indexing (GPTBot)', [
  {{ key: 'gptbot', label: 'GPTBot', data: aiIndexing }},
], {{ dotColors: {{ gptbot: '#10a37f' }}}});

out += buildTable('aierrors', 'AI Errors (by status code)', [
  {{ key: 's404', label: '404 Not Found', data: aiErrors['404'] || {{}} }},
  {{ key: 's301', label: '301 Redirect', data: aiErrors['301'] || {{}} }},
  {{ key: 's429', label: '429 Rate Limited', data: aiErrors['429'] || {{}} }},
  {{ key: 's410', label: '410 Gone', data: aiErrors['410'] || {{}} }},
  {{ key: 's500', label: '500 Server Error', data: aiErrors['500'] || {{}} }},
  {{ type: 'total', label: 'TOTAL' }}
], {{ dotColors: {{ s404: '#ef4444', s301: '#f59e0b', s429: '#fb923c', s410: '#888', s500: '#dc2626' }}}});

out += buildTable('preflight', 'AI Preflight', [
  {{ key: 'chatgpt', label: 'ChatGPT', data: preflight['ChatGPT'] || {{}} }},
  {{ key: 'claude', label: 'Claude', data: preflight['Claude'] || {{}} }},
  {{ key: 'perplexity', label: 'Perplexity', data: preflight['Perplexity'] || {{}} }},
  {{ key: 'bytedance', label: 'ByteDance', data: preflight['ByteDance'] || {{}} }},
  {{ type: 'total', label: 'TOTAL' }}
], {{ dotColors: {{ chatgpt: '#10a37f', claude: '#d97706', perplexity: '#6c8cff', bytedance: '#ff004f' }}}});

out += buildTable('search', 'Search Engine Crawls', [
  {{ key: 'google', label: 'Google', data: searchCrawls['Google'] || {{}} }},
  {{ key: 'bing', label: 'Bing', data: searchCrawls['Bing'] || {{}} }},
  {{ key: 'yandex', label: 'Yandex', data: searchCrawls['Yandex'] || {{}} }},
  {{ key: 'apple', label: 'Apple', data: searchCrawls['Apple'] || {{}} }},
  {{ key: 'duckduck', label: 'DuckDuckGo', data: searchCrawls['DuckDuck'] || {{}} }},
  {{ type: 'total', label: 'TOTAL' }}
], {{ dotColors: {{ google: '#4285f4', bing: '#00809d', yandex: '#ff0000', apple: '#999', duckduck: '#de5833' }}}});

out += buildTable('meta', 'Meta (meta-externalagent)', [
  {{ key: 'meta', label: 'Meta', data: otherCrawlers['Meta'] || {{}} }},
], {{ dotColors: {{ meta: '#1877f2' }}}});

out += buildTable('amazon', 'Amazon (Amazonbot)', [
  {{ key: 'amazon', label: 'Amazon', data: otherCrawlers['Amazon'] || {{}} }},
], {{ dotColors: {{ amazon: '#ff9900' }}}});

out += buildTable('seocrawlers', 'SEO &amp; Other Crawlers', [
  {{ key: 'semrush', label: 'Semrush', data: seoCrawlers['Semrush'] || {{}} }},
  {{ key: 'majestic', label: 'Majestic', data: seoCrawlers['Majestic'] || {{}} }},
  {{ key: 'petalbot', label: 'PetalBot', data: seoCrawlers['PetalBot'] || {{}} }},
  {{ key: 'moz', label: 'Moz', data: seoCrawlers['Moz'] || {{}} }},
  {{ key: 'ahrefs', label: 'Ahrefs', data: seoCrawlers['Ahrefs'] || {{}} }},
  {{ key: 'tiktok', label: 'TikTok', data: seoCrawlers['TikTok'] || {{}} }},
  {{ key: 'curl', label: 'curl', data: seoCrawlers['curl'] || {{}} }},
  {{ key: 'unknown', label: 'Unknown', data: seoCrawlers['Unknown'] || {{}} }},
  {{ type: 'total', label: 'TOTAL' }}
], {{ dotColors: {{ semrush: '#ff642d', majestic: '#e6194b', petalbot: '#e11d48', moz: '#118dff', ahrefs: '#ff8c00', tiktok: '#000', curl: '#888', unknown: '#555' }}}});

out += buildTable('social', 'Social Traffic', [
  {{ key: 'hn', label: 'Hacker News', data: social['HackerNews'] || {{}} }},
  {{ key: 'twitter', label: 'X/Twitter', data: social['X/Twitter'] || {{}} }},
  {{ key: 'reddit', label: 'Reddit', data: social['Reddit'] || {{}} }},
  {{ key: 'linkedin', label: 'LinkedIn', data: social['LinkedIn'] || {{}} }},
  {{ type: 'total', label: 'TOTAL' }}
], {{ dotColors: {{ hn: '#ff6600', twitter: '#1da1f2', reddit: '#ff4500', linkedin: '#0a66c2' }}}});

out += buildTable('human', 'Human Visits', [
  {{ key: 'human', label: 'Human visits', data: humanVisits }},
], {{}});

out += buildTable('ailang', 'AI Citations by Language', [
{ai_lang_rows},
  {{ type: 'total', label: 'TOTAL' }}
], {{}});

out += buildTable('humanlang', 'Human Visits by Language', [
{human_lang_rows},
  {{ type: 'total', label: 'TOTAL' }}
], {{}});

document.getElementById('app').innerHTML = out;
</script>
</body>
</html>"""


def mount_analytics_weekly(app):
    @app.get("/admin/analytics-weekly", response_class=HTMLResponse)
    async def analytics_weekly_page():
        import asyncio
        data = await asyncio.to_thread(_get_cached_data)
        return HTMLResponse(content=_render_html(data))

    logger.info("Mounted /admin/analytics-weekly")
