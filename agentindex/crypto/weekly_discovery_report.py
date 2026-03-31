"""
Sprint 7: Weekly Agent Discovery Report
Genererar automatisk veckorapport som HTML + JSON.
Körs via LaunchAgent varje måndag 06:00 UTC.
"""
import sqlite3, json, os, logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"
REPORT_DIR = "/Users/anstudio/agentindex/agentindex/crypto/reports"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def gather_report_data(week_ago: str, now: str) -> dict:
    conn = get_conn()

    # Nya agenter den senaste veckan
    new_agents = conn.execute("""
        SELECT source, COUNT(*) as n
        FROM agent_crypto_profile
        WHERE first_seen_at >= ?
        GROUP BY source ORDER BY n DESC
    """, (week_ago,)).fetchall()

    # Totala agenter per källa
    total_by_source = conn.execute("""
        SELECT source, COUNT(*) as n
        FROM agent_crypto_profile
        GROUP BY source ORDER BY n DESC
    """).fetchall()

    # Nyidentifierade AI-agenter (wallet behavior)
    new_ai_wallets = conn.execute("""
        SELECT agent_type, COUNT(*) as n, AVG(confidence) as avg_conf
        FROM wallet_behavior
        WHERE is_ai_agent=1 AND analyzed_at >= ?
        GROUP BY agent_type ORDER BY n DESC
    """, (week_ago,)).fetchall()

    # Top 10 entities med högst AI-agent koncentration
    top_ai_entities = conn.execute("""
        SELECT entity_type, entity_id, entity_name, entity_symbol,
               total_agents, identified_ai_agents, ai_agent_ratio,
               ai_tvl_ratio, computed_at
        FROM agent_activity_index
        WHERE identified_ai_agents > 0
        ORDER BY ai_agent_ratio DESC
        LIMIT 10
    """).fetchall()

    # Top 5 chains
    top_chains = conn.execute("""
        SELECT entity_id as chain, total_agents, identified_ai_agents, ai_agent_ratio
        FROM agent_activity_index
        WHERE entity_type='chain'
        ORDER BY total_agents DESC
        LIMIT 5
    """).fetchall()

    # Totala stats
    total_agents = conn.execute("SELECT COUNT(*) FROM agent_crypto_profile").fetchone()[0]
    total_relations = conn.execute("SELECT COUNT(*) FROM agent_crypto_relations").fetchone()[0]
    total_ai = conn.execute("SELECT COUNT(*) FROM wallet_behavior WHERE is_ai_agent=1").fetchone()[0]
    total_analyzed = conn.execute("SELECT COUNT(*) FROM wallet_behavior").fetchone()[0]

    # Högst confidence AI-agenter
    top_ai_agents = conn.execute("""
        SELECT wb.wallet_address, wb.agent_type, wb.confidence,
               wb.avg_tx_per_day, wb.night_tx_ratio,
               acp.agent_name, acp.source, acp.chain
        FROM wallet_behavior wb
        LEFT JOIN agent_crypto_profile acp ON LOWER(acp.creator_address) = wb.wallet_address
        WHERE wb.is_ai_agent=1
        ORDER BY wb.confidence DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    return {
        "new_agents_by_source": [dict(r) for r in new_agents],
        "total_by_source": [dict(r) for r in total_by_source],
        "new_ai_wallets_by_type": [dict(r) for r in new_ai_wallets],
        "top_ai_entities": [dict(r) for r in top_ai_entities],
        "top_chains": [dict(r) for r in top_chains],
        "totals": {
            "agents": total_agents,
            "relations": total_relations,
            "identified_ai_agents": total_ai,
            "wallets_analyzed": total_analyzed,
            "ai_detection_rate": round(total_ai / total_analyzed, 3) if total_analyzed > 0 else 0,
        },
        "top_ai_agents": [dict(r) for r in top_ai_agents],
    }

def generate_html_report(data: dict, week_start: str, week_end: str) -> str:
    totals = data["totals"]
    new_total = sum(r["n"] for r in data["new_agents_by_source"])
    new_ai = sum(r["n"] for r in data["new_ai_wallets_by_type"])

    # Sources table rows
    source_rows = "".join(
        f"<tr><td>{r['source']}</td><td>{r['n']:,}</td></tr>"
        for r in data["total_by_source"]
    )

    # New agents rows
    new_rows = "".join(
        f"<tr><td>{r['source']}</td><td>+{r['n']:,}</td></tr>"
        for r in data["new_agents_by_source"]
    ) or "<tr><td colspan='2'>Inga nya agenter denna vecka</td></tr>"

    # AI type rows
    ai_type_rows = "".join(
        f"<tr><td>{r['agent_type'] or 'okänd'}</td><td>{r['n']}</td><td>{r['avg_conf']:.2f}</td></tr>"
        for r in data["new_ai_wallets_by_type"]
    ) or "<tr><td colspan='3'>Ingen ny wallet-analys denna vecka</td></tr>"

    # Top entities rows
    entity_rows = "".join(
        f"""<tr>
            <td>{r['entity_type']}</td>
            <td><strong>{r['entity_name'] or r['entity_id']}</strong>
                {f"({r['entity_symbol']})" if r.get('entity_symbol') else ''}</td>
            <td>{r['identified_ai_agents']}</td>
            <td>{r['ai_agent_ratio']*100:.1f}%</td>
            <td>{f"{r['ai_tvl_ratio']*100:.1f}%" if r.get('ai_tvl_ratio') else '—'}</td>
        </tr>"""
        for r in data["top_ai_entities"]
    )

    # Top AI agents rows
    agent_rows = "".join(
        f"""<tr>
            <td><code>{r['wallet_address'][:10]}...</code></td>
            <td>{r.get('agent_name') or '—'}</td>
            <td>{r.get('source') or '—'}</td>
            <td>{r['agent_type'] or '—'}</td>
            <td><strong>{r['confidence']:.2f}</strong></td>
            <td>{r['avg_tx_per_day']:.1f}/dag</td>
        </tr>"""
        for r in data["top_ai_agents"]
    )

    return f"""<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agent Discovery Report — {week_start}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #0a0a0a; color: #e0e0e0; max-width: 900px;
          margin: 0 auto; padding: 2rem; }}
  h1 {{ color: #00d4aa; font-size: 1.8rem; border-bottom: 1px solid #333; padding-bottom: 1rem; }}
  h2 {{ color: #888; font-size: 1rem; text-transform: uppercase; letter-spacing: 2px;
        margin-top: 2.5rem; }}
  .stats-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin: 1.5rem 0; }}
  .stat-card {{ background: #141414; border: 1px solid #222; border-radius: 8px;
                padding: 1.2rem; text-align: center; }}
  .stat-number {{ font-size: 2rem; font-weight: 700; color: #00d4aa; }}
  .stat-label {{ font-size: 0.8rem; color: #666; margin-top: 0.3rem; }}
  .stat-delta {{ font-size: 0.9rem; color: #4CAF50; margin-top: 0.2rem; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
  th {{ background: #141414; color: #666; font-size: 0.75rem;
        text-transform: uppercase; padding: 0.6rem 0.8rem; text-align: left; }}
  td {{ padding: 0.6rem 0.8rem; border-bottom: 1px solid #1a1a1a; font-size: 0.9rem; }}
  tr:hover td {{ background: #0f0f0f; }}
  code {{ background: #1a1a1a; padding: 2px 6px; border-radius: 3px;
          font-family: 'SF Mono', monospace; font-size: 0.85rem; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 3px;
            font-size: 0.75rem; font-weight: 600; }}
  .badge-ai {{ background: #00d4aa22; color: #00d4aa; border: 1px solid #00d4aa44; }}
  .footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #1a1a1a;
             color: #444; font-size: 0.8rem; }}
</style>
</head>
<body>

<h1>🤖 Agent Discovery Report</h1>
<p style="color:#555">Vecka {week_start} → {week_end} &nbsp;|&nbsp;
   Genererad: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>

<h2>Sammanfattning</h2>
<div class="stats-grid">
  <div class="stat-card">
    <div class="stat-number">{totals['agents']:,}</div>
    <div class="stat-label">Totala agenter indexerade</div>
    <div class="stat-delta">+{new_total:,} denna vecka</div>
  </div>
  <div class="stat-card">
    <div class="stat-number">{totals['identified_ai_agents']:,}</div>
    <div class="stat-label">Identifierade AI-agenter</div>
    <div class="stat-delta">+{new_ai} nya denna vecka</div>
  </div>
  <div class="stat-card">
    <div class="stat-number">{totals['ai_detection_rate']*100:.0f}%</div>
    <div class="stat-label">AI-detektionsgrad</div>
    <div class="stat-delta">{totals['wallets_analyzed']:,} wallets analyserade</div>
  </div>
</div>

<h2>Nya agenter denna vecka</h2>
<table>
  <tr><th>Källa</th><th>Nya agenter</th></tr>
  {new_rows}
</table>

<h2>Totalt per källa</h2>
<table>
  <tr><th>Källa</th><th>Totalt</th></tr>
  {source_rows}
</table>

<h2>Nyidentifierade AI-agenter (wallet behavior)</h2>
<table>
  <tr><th>Agenttyp</th><th>Antal</th><th>Snitt confidence</th></tr>
  {ai_type_rows}
</table>

<h2>Top entities — högst AI-koncentration</h2>
<table>
  <tr><th>Typ</th><th>Entity</th><th>AI-agenter</th><th>AI-ratio</th><th>AI-TVL</th></tr>
  {entity_rows}
</table>

<h2>Top 10 AI-agenter (confidence)</h2>
<table>
  <tr><th>Wallet</th><th>Namn</th><th>Källa</th><th>Typ</th><th>Confidence</th><th>Aktivitet</th></tr>
  {agent_rows}
</table>

<div class="footer">
  <p>ZARQ Agent Intelligence &nbsp;|&nbsp; zarq.ai &nbsp;|&nbsp;
     Data: crypto_trust.db &nbsp;|&nbsp; {totals['relations']:,} relationer indexerade</p>
  <p>Rapporten genereras automatiskt varje måndag 06:00 UTC</p>
</div>

</body>
</html>"""

def save_report(html: str, data: dict, date_str: str):
    Path(REPORT_DIR).mkdir(parents=True, exist_ok=True)

    # HTML
    html_path = f"{REPORT_DIR}/agent_discovery_{date_str}.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    # JSON
    json_path = f"{REPORT_DIR}/agent_discovery_{date_str}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

    # Spara också som "latest" för enkel åtkomst via API
    latest_html = f"{REPORT_DIR}/agent_discovery_latest.html"
    latest_json = f"{REPORT_DIR}/agent_discovery_latest.json"
    with open(latest_html, "w", encoding="utf-8") as f:
        f.write(html)
    with open(latest_json, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

    log.info(f"Rapport sparad: {html_path}")
    return html_path, json_path

def run():
    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()
    week_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    week_end = now.strftime("%Y-%m-%d")
    date_str = now.strftime("%Y%m%d")

    log.info(f"Genererar Agent Discovery Report för veckan {week_start} → {week_end}")

    data = gather_report_data(week_ago, now.isoformat())
    data["generated_at"] = now.isoformat()
    data["week_start"] = week_start
    data["week_end"] = week_end

    html = generate_html_report(data, week_start, week_end)
    html_path, json_path = save_report(html, data, date_str)

    log.info(f"✅ Rapport klar: {html_path}")
    return data

if __name__ == "__main__":
    run()
