from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from agentindex.db.models import Agent, DiscoveryLog, CrawlJob, get_session
from sqlalchemy import select, func, text
from datetime import datetime, timedelta
import uvicorn, os, json

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def dashboard():
    s = get_session()
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)
    hour_ago = now - timedelta(hours=1)
    week_ago = now - timedelta(days=7)
    total = s.execute(select(func.count(Agent.id))).scalar() or 0
    active = s.execute(select(func.count(Agent.id)).where(Agent.is_active==True)).scalar() or 0
    new24 = s.execute(select(func.count(Agent.id)).where(Agent.first_indexed>day_ago)).scalar() or 0
    statuses = s.execute(select(Agent.crawl_status,func.count(Agent.id)).group_by(Agent.crawl_status).order_by(func.count(Agent.id).desc())).all()
    parsed = sum(c for st,c in statuses if st in("parsed","classified","ranked"))
    pending = sum(c for st,c in statuses if st=="indexed")
    disc_total = s.execute(select(func.count(DiscoveryLog.id))).scalar() or 0
    disc_24h = s.execute(select(func.count(DiscoveryLog.id)).where(DiscoveryLog.timestamp>day_ago)).scalar() or 0
    disc_1h = s.execute(select(func.count(DiscoveryLog.id)).where(DiscoveryLog.timestamp>hour_ago)).scalar() or 0
    avg_resp = s.execute(select(func.avg(DiscoveryLog.response_time_ms)).where(DiscoveryLog.timestamp>day_ago)).scalar()
    avg_resp = int(avg_resp) if avg_resp else 0
    unique_queries_24h = s.execute(select(func.count(func.distinct(DiscoveryLog.query))).where(DiscoveryLog.timestamp>day_ago)).scalar() or 0
    top_queries = []
    try:
        tq = s.execute(select(DiscoveryLog.query, func.count(DiscoveryLog.id).label('cnt')).where(DiscoveryLog.timestamp>week_ago).group_by(DiscoveryLog.query).order_by(text('cnt DESC')).limit(5)).all()
        top_queries = [(str(q.query.get('need','?') if isinstance(q.query, dict) else q.query)[:40], q.cnt) for q in tq]
    except Exception:
        pass
    sources = s.execute(select(Agent.source,func.count(Agent.id)).group_by(Agent.source).order_by(func.count(Agent.id).desc())).all()
    cats = s.execute(select(Agent.category,func.count(Agent.id)).where(Agent.is_active==True).group_by(Agent.category).order_by(func.count(Agent.id).desc()).limit(15)).all()
    parsed_1h = 0
    try:
        parsed_1h = s.execute(select(func.count(Agent.id)).where(Agent.crawl_status.in_(["parsed","classified","ranked"]), Agent.last_parsed>hour_ago)).scalar() or 0
    except Exception:
        pass
    s.close()
    dist_channels = [("API Endpoint","api.agentcrawl.dev","Live"),("Dashboard","dash.agentcrawl.dev","Live"),("PyPI","pip install agentcrawl","Published"),("npm","npm install @agentidx/sdk","Published"),("GitHub","github.com/agentidx/agentindex","Public"),("MCP Registry","Smithery / MCP Hub","Pending")]
    alerts_html = '<div style="color:#4ade80;font-size:13px;padding:8px">No alerts</div>'
    status_text = "HEALTHY"
    status_class = "ok"
    try:
        with open(os.path.expanduser("~/agentindex/health.json")) as f:
            health = json.load(f)
        if health.get("alerts"):
            alerts_html = ""
            for a in health["alerts"]:
                alerts_html += f'<div style="background:#1a1a1a;border-left:3px solid #fbbf24;padding:12px;margin-bottom:8px;border-radius:0 8px 8px 0;font-size:13px"><strong>[{a["severity"].upper()}]</strong> {a["component"]}: {a["message"]}</div>'
            if any(a["severity"]=="critical" for a in health["alerts"]):
                status_text = "CRITICAL"
                status_class = "crit"
            else:
                status_text = "DEGRADED"
                status_class = "warn"
    except Exception:
        pass
    errors_html = '<div style="color:#4ade80;font-size:13px;padding:8px">No recent errors</div>'
    try:
        with open(os.path.expanduser("~/agentindex/agentindex.log")) as f:
            lines = f.readlines()
        errs = [l.strip() for l in lines[-500:] if "ERROR" in l][-10:]
        if errs:
            errors_html = ""
            for line in errs:
                short = line[:120] + "..." if len(line)>120 else line
                errors_html += f'<div style="background:#1a1a1a;border-left:3px solid #fbbf24;padding:12px;margin-bottom:8px;border-radius:0 8px 8px 0;font-size:13px">{short}</div>'
    except Exception:
        pass
    # Missionary report
    missionary_html = '<div style="color:#666;font-size:13px;padding:8px">No missionary report yet</div>'
    try:
        report_dir = os.path.expanduser("~/agentindex/missionary_reports")
        if os.path.exists(report_dir):
            reports = sorted([f for f in os.listdir(report_dir) if f.endswith(".json")], reverse=True)
            if reports:
                with open(os.path.join(report_dir, reports[0])) as f:
                    mr = json.load(f)
                actions = mr.get("actions", [])
                presence = mr.get("presence_tracker", {})
                report_date = reports[0].replace("report-", "").replace(".json", "")
                missionary_html = f'<div style="font-size:11px;color:#666;margin-bottom:8px">Report: {report_date} | {len(actions)} actions</div>'
                for a in actions[:12]:
                    color = "#4ade80" if "SUBMIT" in a or "MERGED" in a else "#fbbf24" if "REGISTER" in a or "ALERT" in a else "#60a5fa" if "NEW" in a else "#e0e0e0"
                    icon = "🎯" if "SUBMIT" in a else "📋" if "REGISTER" in a else "🆕" if "NEW" in a else "⚠️" if "ALERT" in a else "🔍" if "COMPETITOR" in a else "💡" if "SEARCH TERM" in a else "📝" if "UPDATED" in a else "•"
                    short = a[:100] + "..." if len(a) > 100 else a
                    missionary_html += f'<div style="background:#1a1a1a;border-left:3px solid {color};padding:8px 12px;margin-bottom:4px;border-radius:0 8px 8px 0;font-size:12px">{icon} {short}</div>'
                if len(actions) > 12:
                    missionary_html += f'<div style="color:#666;font-size:11px;padding:4px 12px">...and {len(actions)-12} more</div>'
    except Exception:
        pass

    sr = "".join(f"<tr><td>{x}</td><td>{c:,}</td></tr>" for x,c in sources)
    pr = "".join(f"<tr><td>{x}</td><td>{c:,}</td></tr>" for x,c in statuses)
    cr = "".join(f'<tr><td>{x or "unclassified"}</td><td>{c:,}</td></tr>' for x,c in cats)
    dr = "".join(f'<tr><td>{name}</td><td style="font-family:monospace;font-size:11px">{url}</td><td>{status}</td></tr>' for name,url,status in dist_channels)
    tqr = "".join(f'<tr><td>{q}</td><td>{c}</td></tr>' for q,c in top_queries) if top_queries else '<tr><td colspan="2" style="color:#666">No queries yet</td></tr>'
    ts = now.strftime("%Y-%m-%d %H:%M UTC")
    colors = {"ok":"#166534","warn":"#854d0e","crit":"#991b1b"}
    tcolors = {"ok":"#4ade80","warn":"#fbbf24","crit":"#fca5a5"}
    bg = colors.get(status_class,"#166534")
    tc = tcolors.get(status_class,"#4ade80")
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AgentIndex Dashboard</title><meta http-equiv="refresh" content="30">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,sans-serif;background:#0a0a0a;color:#e0e0e0;padding:16px;max-width:1200px;margin:0 auto}}
h1{{font-size:22px;margin-bottom:4px;color:#4ade80}}
.sub{{font-size:12px;color:#666;margin-bottom:16px}}
.g{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:20px}}
.c{{background:#1a1a1a;border-radius:12px;padding:14px}}
.c .l{{font-size:10px;color:#888;text-transform:uppercase;letter-spacing:1px}}
.c .v{{font-size:26px;font-weight:700;color:#fff;margin-top:4px}}
.c .s{{font-size:11px;color:#666;margin-top:4px}}
.c.hi .v{{color:#4ade80}}
table{{width:100%;border-collapse:collapse;margin-top:8px}}
th,td{{text-align:left;padding:6px 8px;font-size:12px}}
th{{color:#888;border-bottom:1px solid #333}}
td{{border-bottom:1px solid #1a1a1a}}
.sec{{margin-bottom:20px}}
.sec h2{{font-size:13px;color:#888;margin-bottom:8px;text-transform:uppercase;letter-spacing:1px}}
.row{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media(max-width:600px){{.row{{grid-template-columns:1fr}}}}
</style></head><body>
<h1>AgentIndex</h1>
<div class="sub">AI Agent Discovery Platform | {ts}</div>
<span style="display:inline-block;padding:4px 12px;border-radius:12px;font-size:12px;font-weight:600;margin-bottom:14px;background:{bg};color:{tc}">{status_text}</span>
<div class="g">
<div class="c"><div class="l">Index Size</div><div class="v">{total:,}</div><div class="s">{active:,} active</div></div>
<div class="c"><div class="l">New 24h</div><div class="v">{new24:,}</div></div>
<div class="c"><div class="l">Parsed</div><div class="v">{parsed:,}</div><div class="s">~{parsed_1h}/hr</div></div>
<div class="c"><div class="l">Pending</div><div class="v">{pending:,}</div></div>
<div class="c hi"><div class="l">API Calls 24h</div><div class="v">{disc_24h:,}</div><div class="s">{disc_1h}/hr</div></div>
<div class="c hi"><div class="l">API Calls Total</div><div class="v">{disc_total:,}</div></div>
<div class="c"><div class="l">Avg Response</div><div class="v">{avg_resp}ms</div></div>
<div class="c"><div class="l">Unique Queries 24h</div><div class="v">{unique_queries_24h}</div></div>
</div>
<div class="sec"><h2>Distribution Channels</h2>
<table><tr><th>Channel</th><th>Address</th><th>Status</th></tr>{dr}</table></div>
<div class="sec"><h2>Alerts</h2>{alerts_html}</div>
<div class="sec"><h2>Missionary Report</h2>{missionary_html}</div>
<div class="row">
<div class="sec"><h2>Sources</h2><table><tr><th>Source</th><th>Count</th></tr>{sr}</table></div>
<div class="sec"><h2>Top Queries (7d)</h2><table><tr><th>Query</th><th>Count</th></tr>{tqr}</table></div>
</div>
<div class="row">
<div class="sec"><h2>Pipeline</h2><table><tr><th>Status</th><th>Count</th></tr>{pr}</table></div>
<div class="sec"><h2>Categories</h2><table><tr><th>Category</th><th>Count</th></tr>{cr}</table></div>
</div>
<div class="sec"><h2>Recent Errors</h2>{errors_html}</div>
<div style="font-size:11px;color:#333;text-align:center;margin-top:16px">Auto-refreshes every 30s | agentcrawl.dev</div>
</body></html>"""
    return HTMLResponse(content=html)

if __name__=="__main__":
    uvicorn.run(app,host="0.0.0.0",port=int(os.getenv("DASHBOARD_PORT","8200")),log_level="warning")
