from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from agentindex.db.models import Agent, DiscoveryLog, CrawlJob, get_session
from sqlalchemy import select, func
from datetime import datetime, timedelta
import uvicorn, os, json

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def dashboard():
    s = get_session()
    total = s.execute(select(func.count(Agent.id))).scalar() or 0
    active = s.execute(select(func.count(Agent.id)).where(Agent.is_active==True)).scalar() or 0
    day_ago = datetime.utcnow() - timedelta(hours=24)
    new24 = s.execute(select(func.count(Agent.id)).where(Agent.first_indexed>day_ago)).scalar() or 0
    disc24 = s.execute(select(func.count(DiscoveryLog.id)).where(DiscoveryLog.timestamp>day_ago)).scalar() or 0
    statuses = s.execute(select(Agent.crawl_status,func.count(Agent.id)).group_by(Agent.crawl_status).order_by(func.count(Agent.id).desc())).all()
    parsed = sum(c for st,c in statuses if st in("parsed","classified","ranked"))
    pending = sum(c for st,c in statuses if st=="indexed")
    sources = s.execute(select(Agent.source,func.count(Agent.id)).group_by(Agent.source).order_by(func.count(Agent.id).desc())).all()
    cats = s.execute(select(Agent.category,func.count(Agent.id)).where(Agent.is_active==True).group_by(Agent.category).order_by(func.count(Agent.id).desc()).limit(10)).all()
    s.close()
    alerts_html = "<div style=\"color:#4ade80;font-size:13px;padding:8px\">No alerts</div>"
    status_text = "HEALTHY"
    status_class = "ok"
    try:
        with open(os.path.expanduser("~/agentindex/health.json")) as f:
            health = json.load(f)
        if health.get("alerts"):
            alerts_html = ""
            for a in health["alerts"]:
                alerts_html += f"<div style=\"background:#1a1a1a;border-left:3px solid #fbbf24;padding:12px;margin-bottom:8px;border-radius:0 8px 8px 0;font-size:13px\"><strong>[{a['severity'].upper()}]</strong> {a['component']}: {a['message']}</div>"
            if any(a["severity"]=="critical" for a in health["alerts"]):
                status_text = "CRITICAL"
                status_class = "crit"
            else:
                status_text = "DEGRADED"
                status_class = "warn"
    except Exception:
        pass
    errors_html = "<div style=\"color:#4ade80;font-size:13px;padding:8px\">No recent errors</div>"
    try:
        with open(os.path.expanduser("~/agentindex/agentindex.log")) as f:
            lines = f.readlines()
        errs = [l.strip() for l in lines[-500:] if "ERROR" in l][-10:]
        if errs:
            errors_html = ""
            for line in errs:
                short = line[:120] + "..." if len(line)>120 else line
                errors_html += f"<div style=\"background:#1a1a1a;border-left:3px solid #fbbf24;padding:12px;margin-bottom:8px;border-radius:0 8px 8px 0;font-size:13px\">{short}</div>"
    except Exception:
        pass
    sr = "".join(f"<tr><td>{x}</td><td>{c}</td></tr>" for x,c in sources)
    pr = "".join(f"<tr><td>{x}</td><td>{c}</td></tr>" for x,c in statuses)
    cr = "".join(f"<tr><td>{x or chr(39)+'unclassified'+chr(39)}</td><td>{c}</td></tr>" for x,c in cats)
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    colors = {"ok":"#166534","warn":"#854d0e","crit":"#991b1b"}
    tcolors = {"ok":"#4ade80","warn":"#fbbf24","crit":"#fca5a5"}
    bg = colors.get(status_class,"#166534")
    tc = tcolors.get(status_class,"#4ade80")
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AgentIndex</title><meta http-equiv="refresh" content="30">
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:-apple-system,sans-serif;background:#0a0a0a;color:#e0e0e0;padding:16px}}h1{{font-size:20px;margin-bottom:12px;color:#4ade80}}.g{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:20px}}.c{{background:#1a1a1a;border-radius:12px;padding:16px}}.c .l{{font-size:11px;color:#888;text-transform:uppercase;letter-spacing:1px}}.c .v{{font-size:28px;font-weight:700;color:#fff;margin-top:4px}}.c .s{{font-size:12px;color:#666;margin-top:4px}}table{{width:100%;border-collapse:collapse;margin-top:8px}}th,td{{text-align:left;padding:8px;font-size:13px}}th{{color:#888;border-bottom:1px solid #333}}td{{border-bottom:1px solid #1a1a1a}}.sec{{margin-bottom:24px}}.sec h2{{font-size:14px;color:#888;margin-bottom:8px;text-transform:uppercase;letter-spacing:1px}}</style></head><body>
<h1>AgentIndex</h1>
<span style="display:inline-block;padding:4px 12px;border-radius:12px;font-size:13px;font-weight:600;margin-bottom:16px;background:{bg};color:{tc}">{status_text}</span>
<span style="font-size:12px;color:#666">{ts}</span>
<div class="g">
<div class="c"><div class="l">Total</div><div class="v">{total}</div><div class="s">{active} active</div></div>
<div class="c"><div class="l">New 24h</div><div class="v">{new24}</div></div>
<div class="c"><div class="l">Parsed</div><div class="v">{parsed}</div></div>
<div class="c"><div class="l">Pending</div><div class="v">{pending}</div></div>
<div class="c"><div class="l">Discovery 24h</div><div class="v">{disc24}</div></div>
</div>
<div class="sec"><h2>Alerts</h2>{alerts_html}</div>
<div class="sec"><h2>Sources</h2><table><tr><th>Source</th><th>Count</th></tr>{sr}</table></div>
<div class="sec"><h2>Pipeline</h2><table><tr><th>Status</th><th>Count</th></tr>{pr}</table></div>
<div class="sec"><h2>Categories</h2><table><tr><th>Category</th><th>Count</th></tr>{cr}</table></div>
<div class="sec"><h2>Recent Errors</h2>{errors_html}</div>
<div style="font-size:11px;color:#444;text-align:center;margin-top:16px">Auto-refreshes every 30s</div>
</body></html>"""
    return HTMLResponse(content=html)

if __name__=="__main__":
    uvicorn.run(app,host="0.0.0.0",port=int(os.getenv("DASHBOARD_PORT","8200")),log_level="warning")
