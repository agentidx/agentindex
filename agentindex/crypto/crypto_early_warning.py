"""
NERQ CRYPTO — Early Warning Feed — "The Nerq Signal"
HTML page + RSS + Atom feeds for active risk signals.
"""
import sqlite3, os, json, hashlib
from datetime import datetime, timedelta
from xml.sax.saxutils import escape as xml_escape
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse

DB_NAME = "crypto_trust.db"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)
SITE_URL = "https://nerq.ai"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def signal_hash(token_id, date, risk_level, ndd):
    raw = f"NERQ|{token_id}|{date}|{risk_level}|{float(ndd or 0):.4f}"
    return hashlib.sha256(raw.encode()).hexdigest()

def compute_scoreboard(conn):
    cutoff = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")
    signals = conn.execute("""
        SELECT DISTINCT s.token_id, s.signal_date, s.risk_level, s.ndd_current
        FROM nerq_risk_signals s
        WHERE s.risk_level IN ('WARNING','CRITICAL') AND s.signal_date < ?
        ORDER BY s.signal_date
    """, (cutoff,)).fetchall()
    total = correct = severe = 0
    for sig in signals:
        ref = conn.execute("SELECT close FROM crypto_price_history WHERE token_id=? AND date<=? ORDER BY date DESC LIMIT 1",
            (sig["token_id"], sig["signal_date"])).fetchone()
        out = conn.execute("SELECT MIN(close) as min_p FROM crypto_price_history WHERE token_id=? AND date BETWEEN ? AND date(?,'+90 days')",
            (sig["token_id"], sig["signal_date"], sig["signal_date"])).fetchone()
        if ref and out and ref["close"] and ref["close"] > 0 and out["min_p"] is not None:
            total += 1
            dd = (out["min_p"] - ref["close"]) / ref["close"]
            if dd < -0.30: correct += 1
            if dd < -0.50: severe += 1
    return {"total": total, "correct": correct, "severe": severe,
            "precision": round(correct/total*100, 1) if total > 0 else None,
            "updated": datetime.utcnow().strftime("%Y-%m-%d")}

CSS = """
:root{--bg:#0a0e17;--surface:#111827;--border:#1f2937;--text:#e5e7eb;--dim:#9ca3af;--accent:#3b82f6;--critical:#ef4444;--warning:#f59e0b;--safe:#10b981}
*{margin:0;padding:0;box-sizing:border-box}body{background:var(--bg);color:var(--text);font-family:Inter,-apple-system,sans-serif;line-height:1.6}
.container{max-width:1100px;margin:0 auto;padding:2rem 1.5rem}h1{font-size:2rem;font-weight:700;margin-bottom:.25rem}
h2{font-size:1.25rem;font-weight:600;margin:2rem 0 1rem}h3{font-size:1rem;font-weight:600;margin-bottom:.75rem}
.subtitle{color:var(--dim);font-size:.95rem;margin-bottom:1.5rem}a{color:var(--accent);text-decoration:none}
.header{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:1rem;margin-bottom:2rem}
.header-right{display:flex;gap:.75rem;align-items:center}
.feed-link{display:inline-flex;align-items:center;gap:.3rem;background:var(--surface);border:1px solid var(--border);padding:.4rem .75rem;border-radius:6px;font-size:.8rem;color:var(--dim)}
.dist-bar{display:flex;gap:.75rem;margin-bottom:2rem;flex-wrap:wrap}
.dist-item{background:var(--surface);border:1px solid var(--border);padding:.75rem 1.25rem;border-radius:8px;text-align:center;min-width:100px}
.dist-value{font-size:1.5rem;font-weight:700}.dist-label{font-size:.75rem;color:var(--dim);text-transform:uppercase;letter-spacing:.05em}
.dist-item.safe .dist-value{color:var(--safe)}.dist-item.watch .dist-value{color:var(--dim)}
.dist-item.warning .dist-value{color:var(--warning)}.dist-item.critical .dist-value{color:var(--critical)}
.scoreboard{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.5rem;margin-bottom:2rem}
.scoreboard-grid{display:flex;gap:2rem;flex-wrap:wrap;margin:1rem 0}
.stat{text-align:center}.stat-value{display:block;font-size:1.75rem;font-weight:700;color:var(--accent)}
.stat-label{font-size:.75rem;color:var(--dim);text-transform:uppercase}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:left;padding:.6rem .75rem;border-bottom:2px solid var(--border);color:var(--dim);font-size:.7rem;text-transform:uppercase;letter-spacing:.05em;font-weight:600}
td{padding:.6rem .75rem;border-bottom:1px solid var(--border)}tr:hover{background:rgba(255,255,255,.02)}
.badge{display:inline-block;padding:.15rem .5rem;border-radius:4px;font-size:.7rem;font-weight:700;letter-spacing:.03em}
.badge.critical{background:rgba(239,68,68,.08);color:var(--critical);border:1px solid rgba(239,68,68,.3)}
.badge.warning{background:rgba(245,158,11,.08);color:var(--warning);border:1px solid rgba(245,158,11,.3)}
.token-name{color:var(--dim);font-size:.8rem;margin-left:.3rem}.hash{font-family:monospace;font-size:.7rem;color:var(--dim)}
.tabs{display:flex;gap:0;margin-bottom:1.5rem;border-bottom:2px solid var(--border)}
.tab{padding:.6rem 1.25rem;cursor:pointer;color:var(--dim);font-size:.85rem;font-weight:500;border-bottom:2px solid transparent;margin-bottom:-2px}
.tab.active{color:var(--accent);border-bottom-color:var(--accent)}
.tab-content{display:none}.tab-content.active{display:block}
.retro-notice{background:rgba(245,158,11,.06);border:1px solid rgba(245,158,11,.2);border-radius:8px;padding:.75rem 1rem;margin-bottom:1rem;font-size:.8rem;color:var(--warning)}
.api-cta{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.5rem;margin-top:2rem;text-align:center}
.api-cta code{background:var(--bg);padding:.5rem 1rem;border-radius:6px;font-size:.8rem;display:inline-block;margin:.75rem 0;color:var(--accent)}
.footer{margin-top:3rem;padding-top:1.5rem;border-top:1px solid var(--border);font-size:.75rem;color:var(--dim);text-align:center}
@media(max-width:768px){.container{padding:1rem}h1{font-size:1.5rem}table{font-size:.75rem}th,td{padding:.4rem}}
"""

def build_signals_page(conn, run_date):
    active = conn.execute("""
        SELECT s.token_id, s.signal_date, s.risk_level, s.structural_weakness, s.ndd_current,
               s.trust_p3, s.trust_score, s.drawdown_90d, r.symbol, r.name, r.rating
        FROM nerq_risk_signals s
        LEFT JOIN crypto_rating_daily r ON s.token_id=r.token_id AND r.run_date=s.signal_date
        WHERE s.signal_date=? AND s.risk_level IN ('WARNING','CRITICAL')
        ORDER BY s.structural_weakness DESC, s.ndd_current ASC
    """, (run_date,)).fetchall()
    dist = {"SAFE":0,"WATCH":0,"WARNING":0,"CRITICAL":0}
    for row in conn.execute("SELECT risk_level, COUNT(*) as c FROM nerq_risk_signals WHERE signal_date=? GROUP BY risk_level", (run_date,)).fetchall():
        dist[row["risk_level"]] = row["c"]
    total_tokens = sum(dist.values())
    cutoff_90 = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")
    hist = conn.execute("""
        SELECT s.token_id, s.signal_date, s.risk_level, s.structural_weakness, s.ndd_current, r.symbol, r.name, r.rating
        FROM nerq_risk_signals s LEFT JOIN crypto_rating_daily r ON s.token_id=r.token_id AND r.run_date=s.signal_date
        WHERE s.risk_level IN ('WARNING','CRITICAL') AND s.signal_date>=? AND s.signal_date<?
        ORDER BY s.signal_date DESC, s.structural_weakness DESC LIMIT 200
    """, (cutoff_90, run_date)).fetchall()
    sb = compute_scoreboard(conn)
    active_tbody = ""
    for row in active:
        r = dict(row)
        h = signal_hash(r["token_id"], r["signal_date"], r["risk_level"], r.get("ndd_current") or 0)
        bc = "critical" if r["risk_level"]=="CRITICAL" else "warning"
        dd = (r.get("drawdown_90d") or 0) * 100
        sym = (r.get("symbol") or "").upper() or r["token_id"]
        active_tbody += f'<tr><td><span class="badge {bc}">{r["risk_level"]}</span></td><td><strong>{sym}</strong> <span class="token-name">{r.get("name","")}</span></td><td>{r.get("rating","N/A")}</td><td>{(r.get("ndd_current") or 0):.2f}</td><td>{r.get("structural_weakness",0)}/4</td><td>{(r.get("trust_p3") or 0):.0f}</td><td>{dd:.0f}%</td><td class="hash" title="SHA-256: {h}">{h[:12]}</td></tr>'
    hist_tbody = ""
    for row in hist:
        r = dict(row)
        h = signal_hash(r["token_id"], r["signal_date"], r["risk_level"], r.get("ndd_current") or 0)
        bc = "critical" if r["risk_level"]=="CRITICAL" else "warning"
        sym = (r.get("symbol") or "").upper() or r["token_id"]
        hist_tbody += f'<tr><td>{r["signal_date"]}</td><td><span class="badge {bc}">{r["risk_level"]}</span></td><td><strong>{sym}</strong> <span class="token-name">{r.get("name","")}</span></td><td>{r.get("rating","N/A")}</td><td>{(r.get("ndd_current") or 0):.2f}</td><td>{r.get("structural_weakness",0)}/4</td><td class="hash">{h[:12]}</td></tr>'
    prec = f'{sb["precision"]}%' if sb["precision"] is not None else "N/A"
    no_signals = '<p style="color:var(--dim);margin-top:1rem;font-size:.85rem">No active WARNING or CRITICAL signals.</p>' if not active_tbody else ""
    year = datetime.utcnow().year
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>The Nerq Signal -- Crypto Early Warning Feed</title>
<meta name="description" content="Real-time crypto risk signals. {len(active)} active warnings as of {run_date}. Track record: {prec} precision.">
<link rel="alternate" type="application/rss+xml" title="Nerq Signals RSS" href="/crypto/signals/rss">
<link rel="alternate" type="application/atom+xml" title="Nerq Signals Atom" href="/crypto/signals/atom">
<link rel="canonical" href="{SITE_URL}/crypto/signals">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"DataFeed","name":"The Nerq Signal","description":"Real-time crypto risk and crash warning signals","url":"{SITE_URL}/crypto/signals","provider":{{"@type":"Organization","name":"Nerq","url":"{SITE_URL}"}},"dateModified":"{run_date}"}}</script>
<style>{CSS}</style></head><body><div class="container">
<div class="header"><div><h1>The Nerq Signal</h1><p class="subtitle">Crypto Early Warning Feed -- {run_date} -- {total_tokens} tokens monitored</p></div>
<div class="header-right"><a href="/crypto/signals/rss" class="feed-link">RSS</a><a href="/crypto/signals/atom" class="feed-link">Atom</a><a href="/v1/crypto/signals" class="feed-link">API</a></div></div>
<div class="dist-bar"><div class="dist-item safe"><div class="dist-value">{dist["SAFE"]}</div><div class="dist-label">Safe</div></div>
<div class="dist-item watch"><div class="dist-value">{dist["WATCH"]}</div><div class="dist-label">Watch</div></div>
<div class="dist-item warning"><div class="dist-value">{dist["WARNING"]}</div><div class="dist-label">Warning</div></div>
<div class="dist-item critical"><div class="dist-value">{dist["CRITICAL"]}</div><div class="dist-label">Critical</div></div></div>
<div class="scoreboard"><h3>Running Scoreboard</h3><div class="scoreboard-grid">
<div class="stat"><span class="stat-value">{prec}</span><span class="stat-label">Precision</span></div>
<div class="stat"><span class="stat-value">{sb["correct"]}/{sb["total"]}</span><span class="stat-label">Correct / Evaluated</span></div>
<div class="stat"><span class="stat-value">{sb["severe"]}</span><span class="stat-label">Severe Crashes Caught</span></div></div>
<p style="font-size:.8rem;color:var(--dim);margin-top:.5rem">Only signals >90 days old are evaluated. Crash = >30% drawdown within 90 days. Updated {sb["updated"]}.</p></div>
<div class="tabs"><div class="tab active" onclick="switchTab('active')">Active Signals ({len(active)})</div><div class="tab" onclick="switchTab('history')">Historical (90d)</div></div>
<div id="tab-active" class="tab-content active"><table><thead><tr><th>Level</th><th>Token</th><th>Rating</th><th>NDD</th><th>Weakness</th><th>P3</th><th>DD 90d</th><th>Hash</th></tr></thead><tbody>{active_tbody}</tbody></table>{no_signals}</div>
<div id="tab-history" class="tab-content"><div class="retro-notice">Historical signals shown for track record verification. Signals older than feed launch are retroactive analysis, not real-time predictions.</div>
<table><thead><tr><th>Date</th><th>Level</th><th>Token</th><th>Rating</th><th>NDD</th><th>Weakness</th><th>Hash</th></tr></thead><tbody>{hist_tbody}</tbody></table></div>
<div class="api-cta"><h3>Get signals via API</h3><code>curl {SITE_URL}/v1/crypto/signals</code></div>
<div class="footer"><p>The Nerq Signal -- Systematic Crypto Risk Intelligence</p><p>Each signal is SHA-256 hashed at generation. Verify at /v1/crypto/signals/history.</p><p>{year} Nerq. Data updates daily at 06:00 CET.</p></div>
</div><script>function switchTab(n){{document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.getElementById('tab-'+n).classList.add('active');event.target.classList.add('active')}}</script></body></html>"""

def build_rss(conn, run_date):
    rows = conn.execute("""SELECT s.token_id, s.signal_date, s.risk_level, s.ndd_current, s.structural_weakness, r.symbol, r.name, r.rating
        FROM nerq_risk_signals s LEFT JOIN crypto_rating_daily r ON s.token_id=r.token_id AND r.run_date=s.signal_date
        WHERE s.risk_level IN ('WARNING','CRITICAL') ORDER BY s.signal_date DESC LIMIT 50""").fetchall()
    items = ""
    for row in rows:
        r = dict(row); sym = (r.get("symbol") or "").upper() or r["token_id"]
        h = signal_hash(r["token_id"], r["signal_date"], r["risk_level"], r.get("ndd_current") or 0)
        title = xml_escape(f'[{r["risk_level"]}] {sym} -- NDD {(r.get("ndd_current") or 0):.2f}')
        desc = xml_escape(f'{sym} rated {r.get("rating","N/A")}. Risk: {r["risk_level"]}. NDD: {(r.get("ndd_current") or 0):.2f}/5.0. Weakness: {r.get("structural_weakness",0)}/4. Hash: {h[:16]}')
        pub = datetime.strptime(r["signal_date"], "%Y-%m-%d").strftime("%a, %d %b %Y 06:00:00 +0100")
        items += f'<item><title>{title}</title><description>{desc}</description><link>{SITE_URL}/crypto/signals</link><guid isPermaLink="false">nerq-{r["token_id"]}-{r["signal_date"]}</guid><pubDate>{pub}</pubDate><category>{r["risk_level"]}</category></item>'
    now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
    return f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel><title>The Nerq Signal</title><link>{SITE_URL}/crypto/signals</link><description>Crypto risk signals from Nerq</description><language>en</language><lastBuildDate>{now}</lastBuildDate><atom:link href="{SITE_URL}/crypto/signals/rss" rel="self" type="application/rss+xml"/>{items}</channel></rss>'

def build_atom(conn, run_date):
    rows = conn.execute("""SELECT s.token_id, s.signal_date, s.risk_level, s.ndd_current, s.structural_weakness, r.symbol, r.name, r.rating
        FROM nerq_risk_signals s LEFT JOIN crypto_rating_daily r ON s.token_id=r.token_id AND r.run_date=s.signal_date
        WHERE s.risk_level IN ('WARNING','CRITICAL') ORDER BY s.signal_date DESC LIMIT 50""").fetchall()
    entries = ""
    for row in rows:
        r = dict(row); sym = (r.get("symbol") or "").upper() or r["token_id"]
        h = signal_hash(r["token_id"], r["signal_date"], r["risk_level"], r.get("ndd_current") or 0)
        title = xml_escape(f'[{r["risk_level"]}] {sym} -- NDD {(r.get("ndd_current") or 0):.2f}')
        summary = xml_escape(f'{sym} rated {r.get("rating","N/A")}. Risk: {r["risk_level"]}. NDD: {(r.get("ndd_current") or 0):.2f}/5.0. Hash: {h[:16]}')
        entries += f'<entry><title>{title}</title><id>urn:nerq:signal:{r["token_id"]}:{r["signal_date"]}</id><updated>{r["signal_date"]}T06:00:00Z</updated><summary>{summary}</summary><link href="{SITE_URL}/crypto/signals"/><category term="{r["risk_level"]}"/></entry>'
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    return f'<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>The Nerq Signal</title><link href="{SITE_URL}/crypto/signals" rel="alternate"/><link href="{SITE_URL}/crypto/signals/atom" rel="self"/><id>urn:nerq:signals:feed</id><updated>{now}</updated><author><name>Nerq</name></author>{entries}</feed>'

def mount_early_warning(app):
    @app.get("/crypto/signals", response_class=HTMLResponse, tags=["early-warning"])
    def signals_page():
        conn = get_db()
        rd = conn.execute("SELECT MAX(signal_date) as d FROM nerq_risk_signals").fetchone()
        run_date = rd["d"] if rd else datetime.utcnow().strftime("%Y-%m-%d")
        html = build_signals_page(conn, run_date)
        conn.close()
        return HTMLResponse(content=html)
    @app.get("/crypto/signals/rss", tags=["early-warning"])
    def signals_rss():
        conn = get_db()
        rd = conn.execute("SELECT MAX(signal_date) as d FROM nerq_risk_signals").fetchone()
        run_date = rd["d"] if rd else datetime.utcnow().strftime("%Y-%m-%d")
        xml = build_rss(conn, run_date)
        conn.close()
        return Response(content=xml, media_type="application/rss+xml")
    @app.get("/crypto/signals/atom", tags=["early-warning"])
    def signals_atom():
        conn = get_db()
        rd = conn.execute("SELECT MAX(signal_date) as d FROM nerq_risk_signals").fetchone()
        run_date = rd["d"] if rd else datetime.utcnow().strftime("%Y-%m-%d")
        xml = build_atom(conn, run_date)
        conn.close()
        return Response(content=xml, media_type="application/atom+xml")
