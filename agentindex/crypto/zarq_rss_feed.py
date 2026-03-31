"""
ZARQ RSS/Atom Feed — zarq.ai/feed.xml
Publishes structural collapse alerts, vitality score changes, and paper trading performance.
"""
from fastapi import APIRouter, Request
from starlette.responses import Response
import httpx
import asyncio
from datetime import datetime
import html

router_zarq_rss = APIRouter()


def _esc(s):
    return html.escape(str(s)) if s else ""


async def _fetch(client, path):
    try:
        r = await client.get(f"http://127.0.0.1:8000{path}", timeout=5.0)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


@router_zarq_rss.get("/zarq/feed.xml")
async def zarq_rss_feed(request: Request):
    host = request.headers.get("host", "")
    domain = "zarq.ai" if "zarq" in host else host

    async with httpx.AsyncClient() as client:
        collapse, regime, nav_alpha = await asyncio.gather(
            _fetch(client, "/v1/agents/structural-collapse"),
            _fetch(client, "/v1/crypto/paper-trading/regime"),
            _fetch(client, "/v1/crypto/paper-trading/nav/ALPHA"),
        )

    now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
    items = []

    # Regime item
    rd = regime.get("data", {})
    current_regime = rd.get("alpha_regime", "UNKNOWN")
    btc_price = rd.get("btc_price", 0)
    btc_dd = rd.get("btc_dd_from_ath", 0)
    items.append(f"""<item>
      <title>Market Regime: {_esc(current_regime)} — BTC ${btc_price:,.0f}</title>
      <link>https://{domain}/briefing</link>
      <description>Current regime: {_esc(current_regime)}. BTC at ${btc_price:,.0f} ({btc_dd*100:.1f}% from ATH). Check the daily briefing for full details.</description>
      <pubDate>{now}</pubDate>
      <guid isPermaLink="false">zarq-regime-{datetime.utcnow().strftime('%Y%m%d')}</guid>
    </item>""")

    # Structural collapse alerts
    collapse_agents = collapse.get("agents", [])
    total = collapse.get("total_agents_in_structural_collapse", 0)
    if collapse_agents:
        names = ", ".join(a.get("token_symbol", a.get("agent_name", "?")) for a in collapse_agents[:5])
        mcap = collapse.get("total_mcap_exposed_usd", 0)
        items.append(f"""<item>
      <title>Structural Collapse Alert: {total} tokens ({names})</title>
      <link>https://{domain}/crash-watch</link>
      <description>{total} tokens in structural collapse with ${mcap:,.0f} market cap exposed. Tokens: {_esc(names)}. NDD values below 1.0 indicate imminent structural failure.</description>
      <pubDate>{now}</pubDate>
      <guid isPermaLink="false">zarq-collapse-{datetime.utcnow().strftime('%Y%m%d')}</guid>
    </item>""")

        # Individual collapse items
        for a in collapse_agents[:3]:
            name = a.get("agent_name", a.get("agent_id", "?"))
            symbol = a.get("token_symbol", name)
            ndd = a.get("ndd_current", 0)
            tp3 = a.get("trust_p3", 0)
            mc = a.get("market_cap_usd", 0)
            items.append(f"""<item>
      <title>COLLAPSE: {_esc(symbol)} — NDD {ndd:.2f}, Crash P {tp3:.1f}%</title>
      <link>https://{domain}/token/{_esc(name)}</link>
      <description>{_esc(symbol)} is in structural collapse. Distance-to-Default: {ndd:.2f}. Crash probability: {tp3:.1f}%. Market cap: ${mc:,.0f}.</description>
      <pubDate>{now}</pubDate>
      <guid isPermaLink="false">zarq-collapse-{_esc(name)}-{datetime.utcnow().strftime('%Y%m%d')}</guid>
    </item>""")

    # Paper trading performance
    history = nav_alpha.get("data", {}).get("history", [])
    if history:
        latest = history[-1]
        nav = latest.get("nav_value", 10000)
        cum_ret = latest.get("cumulative_return", 0)
        nav_date = latest.get("nav_date", "")
        items.append(f"""<item>
      <title>Paper Trading: ALPHA NAV ${nav:,.0f} ({cum_ret*100:+.2f}%)</title>
      <link>https://{domain}/paper-trading</link>
      <description>ALPHA portfolio NAV: ${nav:,.0f} (cumulative return: {cum_ret*100:+.2f}%) as of {_esc(nav_date)}. Hash-chained audit trail available.</description>
      <pubDate>{now}</pubDate>
      <guid isPermaLink="false">zarq-nav-alpha-{_esc(nav_date)}</guid>
    </item>""")

    items_xml = "\n".join(items)

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>ZARQ Risk Intelligence</title>
    <link>https://{domain}/briefing</link>
    <description>Live risk signals from ZARQ: structural collapse alerts, market regime changes, paper trading performance, and yield risk flags.</description>
    <language>en-us</language>
    <lastBuildDate>{now}</lastBuildDate>
    <atom:link href="https://{domain}/feed.xml" rel="self" type="application/rss+xml" />
    <ttl>60</ttl>
    {items_xml}
  </channel>
</rss>"""

    return Response(content=rss, media_type="application/rss+xml",
                    headers={"Cache-Control": "public, max-age=300"})


def mount_zarq_rss(app):
    app.include_router(router_zarq_rss)
