from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse
from fastapi.responses import HTMLResponse
import os

class ZarqRouter(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        host = request.headers.get("host", "")
        if "zarq.ai" not in host:
            return await call_next(request)
        
        path = request.url.path
        
        # API calls pass through (already namespaced /v1/crypto/)
        if path.startswith("/v1/"):
            return await call_next(request)
        
        # Static assets pass through
        if path.startswith("/static/") or path.startswith("/favicon"):
            return await call_next(request)
        
        # Root → crypto landing (paper-trading for now, will be replaced)
        if path == "/" or path == "":
            # Serve paper trading dashboard as temporary landing
            template_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "crypto", "templates", "zarq_landing.html"
            )
            try:
                with open(template_path, "r") as f:
                    html = f.read()
                # Fill in live alert data
                try:
                    from agentindex.crypto.dual_read import get_crypto_db
                    conn = get_crypto_db()
                    row = conn.execute("SELECT MAX(signal_date) as d FROM nerq_risk_signals").fetchone()
                    if row and row["d"]:
                        sd = row["d"]
                        critical = conn.execute("SELECT COUNT(*) FROM nerq_risk_signals WHERE signal_date=? AND risk_level='CRITICAL'", [sd]).fetchone()[0]
                        warning = conn.execute("SELECT COUNT(*) FROM nerq_risk_signals WHERE signal_date=? AND risk_level='WARNING'", [sd]).fetchone()[0]
                        latest = conn.execute("""
                            SELECT s.token_id, s.first_collapse_date, s.price_at_collapse, s.weeks_in_collapse,
                                   r.name, n.price_usd
                            FROM nerq_risk_signals s
                            LEFT JOIN crypto_rating_daily r ON s.token_id = r.token_id
                            LEFT JOIN crypto_ndd_daily n ON s.token_id = n.token_id
                            WHERE s.signal_date=? AND s.risk_level='CRITICAL' AND s.first_collapse_date IS NOT NULL
                            ORDER BY s.first_collapse_date DESC LIMIT 1
                        """, [sd]).fetchone()
                        html = html.replace("{{COLLAPSE_COUNT}}", str(critical))
                        html = html.replace("{{STRESS_COUNT}}", str(warning))
                        if latest:
                            name = latest["name"] or latest["token_id"].replace("-", " ").title()
                            price_then = latest["price_at_collapse"] or 0
                            price_now = latest["price_usd"] or 0
                            change_pct = ((price_now - price_then) / price_then * 100) if price_then > 0 else 0
                            change_str = f"{change_pct:+.1f}%" 
                            html = html.replace("{{LATEST_NAME}}", name)
                            html = html.replace("{{LATEST_DATE}}", latest["first_collapse_date"] or "")
                            html = html.replace("{{LATEST_PRICE}}", f"{price_then:.4f}")
                            html = html.replace("{{LATEST_PRICE_NOW}}", f"{price_now:.4f}")
                            html = html.replace("{{LATEST_CHANGE}}", change_str)
                        # Worst performer (largest decline since collapse)
                        worst = conn.execute("""
                            SELECT s.token_id, s.first_collapse_date, s.price_at_collapse,
                                   r.name, n.price_usd
                            FROM nerq_risk_signals s
                            LEFT JOIN crypto_rating_daily r ON s.token_id = r.token_id
                            LEFT JOIN crypto_ndd_daily n ON s.token_id = n.token_id
                            WHERE s.signal_date=? AND s.risk_level='CRITICAL'
                              AND s.price_at_collapse > 0 AND n.price_usd > 0
                            ORDER BY (n.price_usd - s.price_at_collapse) / s.price_at_collapse ASC
                            LIMIT 1
                        """, [sd]).fetchone()
                        if worst:
                            wname = worst["name"] or worst["token_id"].replace("-", " ").title()
                            wp_then = worst["price_at_collapse"] or 0
                            wp_now = worst["price_usd"] or 0
                            wchange = ((wp_now - wp_then) / wp_then * 100) if wp_then > 0 else 0
                            html = html.replace("{{WORST_NAME}}", wname)
                            html = html.replace("{{WORST_DATE}}", worst["first_collapse_date"] or "")
                            html = html.replace("{{WORST_CHANGE}}", f"{wchange:+.1f}%")
                        html = html.replace("{{TOTAL_ALERTS}}", str(critical + warning))
                        
                        # Build alert proof box with target tracking
                        # Use crash_model_v3_predictions for first warning dates (nerq_risk_signals.first_collapse_date is unpopulated)
                        try:
                            all_alerts = conn.execute("""
                                SELECT s.token_id, s.risk_level,
                                       n.symbol
                                FROM nerq_risk_signals s
                                LEFT JOIN crypto_ndd_daily n ON s.token_id = n.token_id AND n.run_date = s.signal_date
                                WHERE s.signal_date=? AND s.risk_level IN ('WARNING','CRITICAL')
                            """, [sd]).fetchall()

                            mature_cutoff = "2026-01-25"  # ~6 weeks before today
                            mature_t1 = 0
                            mature_t2 = 0
                            mature_count = 0
                            latest_t1_date = ""
                            latest_t1_sym = ""
                            latest_t2_date = ""
                            latest_t2_sym = ""
                            latest_alert_sym = ""
                            latest_alert_date = ""
                            latest_alert_level = ""

                            for a in all_alerts:
                                tid = a["token_id"]
                                # Get first warning date from crash model
                                fw = conn.execute(
                                    "SELECT MIN(date) as d FROM crash_model_v3_predictions WHERE token_id=? AND crash_prob_v3 > 0.5",
                                    [tid]).fetchone()
                                fd = fw["d"] if fw else None
                                if not fd:
                                    continue

                                # Get price at first warning
                                pw = conn.execute(
                                    "SELECT close FROM crypto_price_history WHERE token_id=? AND date=?",
                                    [tid, fd]).fetchone()
                                pa = pw[0] if pw and pw[0] and pw[0] > 0 else None
                                if not pa:
                                    continue

                                sym = (a["symbol"] or tid.split("-")[0][:5]).upper()

                                # Latest alert issued
                                if not latest_alert_date or fd > latest_alert_date:
                                    latest_alert_date = fd
                                    latest_alert_sym = sym
                                    latest_alert_level = "Collapse" if a["risk_level"] == "CRITICAL" else "Stress"

                                if fd >= mature_cutoff:
                                    continue
                                mature_count += 1

                                mp = conn.execute("SELECT MIN(close) FROM crypto_price_history WHERE token_id=? AND date>=?", (tid, fd)).fetchone()
                                if not mp or mp[0] is None or mp[0] <= 0:
                                    continue
                                dd = (mp[0] - pa) / pa * 100

                                if dd <= -30:
                                    mature_t1 += 1
                                    cross = conn.execute("SELECT date FROM crypto_price_history WHERE token_id=? AND date>=? AND close<=? ORDER BY date ASC LIMIT 1", (tid, fd, pa*0.70)).fetchone()
                                    if cross and cross[0] > latest_t1_date:
                                        latest_t1_date = cross[0]
                                        latest_t1_sym = sym
                                if dd <= -50:
                                    mature_t2 += 1
                                    cross = conn.execute("SELECT date FROM crypto_price_history WHERE token_id=? AND date>=? AND close<=? ORDER BY date ASC LIMIT 1", (tid, fd, pa*0.50)).fetchone()
                                    if cross and cross[0] > latest_t2_date:
                                        latest_t2_date = cross[0]
                                        latest_t2_sym = sym

                            t1_rate = f"{mature_t1/mature_count*100:.0f}" if mature_count else "0"
                            t2_rate = f"{mature_t2/mature_count*100:.0f}" if mature_count else "0"
                            fresh = len(all_alerts) - mature_count
                            total_alerts = len(all_alerts)
                            
                            latest_target_date = max(latest_t1_date, latest_t2_date)
                            if latest_target_date == latest_t2_date and latest_t2_sym:
                                latest_target_sym = latest_t2_sym
                                latest_target_pct = "-50%"
                            else:
                                latest_target_sym = latest_t1_sym
                                latest_target_pct = "-30%"

                            proof_box = f"""<div style="text-align:left !important;background:var(--gray-100);border:1px solid var(--gray-200);padding:28px 32px">
  <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px">
    <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.15em;text-transform:uppercase;color:var(--red)">Live Structural Alerts</div>
    <a href="/crypto/alerts" style="font-family:var(--mono);font-size:11px;color:var(--warm);text-decoration:none">View all {total_alerts} alerts &rarr;</a>
  </div>
  <div style="font-family:var(--sans);font-size:13px;color:var(--gray-500);margin-bottom:20px">Out-of-sample: 176 collapse signals issued, 98% lost &gt;50%. Only 1 false positive (&lt;30% decline).</div>

  <div style="font-family:var(--serif);font-size:24px;color:var(--black);margin-bottom:12px">Live Signal Accuracy <span style="font-family:var(--mono);font-size:13px;color:var(--red);vertical-align:middle;margin-left:8px">{total_alerts} active alerts</span></div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:20px">
    <div style="text-align:left;padding:20px;background:var(--white);border:1px solid var(--gray-200)">
      <div style="display:flex;align-items:baseline;gap:8px">
        <div style="font-family:var(--serif);font-size:42px;color:var(--black)">{t1_rate}%</div>
        <div style="font-family:var(--mono);font-size:10px;color:var(--warm);text-transform:uppercase;letter-spacing:0.05em">1st Target Hit</div>
      </div>
      <div style="font-family:var(--sans);font-size:13px;color:var(--gray-600);margin-top:6px">{mature_t1} of {mature_count} mature alerts declined &ge;30% from alert price</div>
      <div style="font-family:var(--mono);font-size:11px;color:var(--gray-500);margin-top:8px">Latest: <span style="color:var(--warm);font-weight:500">{latest_t1_sym}</span> crossed -30% on {latest_t1_date}</div>
    </div>
    <div style="text-align:left;padding:20px;background:var(--white);border:1px solid var(--gray-200)">
      <div style="display:flex;align-items:baseline;gap:8px">
        <div style="font-family:var(--serif);font-size:42px;color:var(--black)">{t2_rate}%</div>
        <div style="font-family:var(--mono);font-size:10px;color:var(--red);text-transform:uppercase;letter-spacing:0.05em">2nd Target Hit</div>
      </div>
      <div style="font-family:var(--sans);font-size:13px;color:var(--gray-600);margin-top:6px">{mature_t2} of {mature_count} mature alerts declined &ge;50% from alert price</div>
      <div style="font-family:var(--mono);font-size:11px;color:var(--gray-500);margin-top:8px">Latest: <span style="color:var(--red);font-weight:500">{latest_t2_sym}</span> crossed -50% on {latest_t2_date}</div>
    </div>
  </div>

  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;padding-top:16px;border-top:1px solid var(--gray-200)">
    <div>
      <div style="font-family:var(--serif);font-size:28px;color:var(--black)">{total_alerts}</div>
      <div style="font-family:var(--mono);font-size:9px;color:var(--gray-500);text-transform:uppercase;letter-spacing:0.05em">Active Alerts</div>
      <div style="font-family:var(--sans);font-size:12px;color:var(--gray-500);margin-top:2px">{critical} Collapse &middot; {warning} Stress</div>
    </div>
    <div>
      <div style="font-family:var(--serif);font-size:28px;color:var(--black)">{fresh}</div>
      <div style="font-family:var(--mono);font-size:9px;color:var(--gray-500);text-transform:uppercase;letter-spacing:0.05em">Monitoring</div>
      <div style="font-family:var(--sans);font-size:12px;color:var(--gray-500);margin-top:2px">Recent alerts, tracking</div>
    </div>
    <div>
      <div style="font-family:var(--serif);font-size:28px;color:var(--red)">{latest_alert_sym}</div>
      <div style="font-family:var(--mono);font-size:9px;color:var(--gray-500);text-transform:uppercase;letter-spacing:0.05em">Latest Alert Issued</div>
      <div style="font-family:var(--sans);font-size:12px;color:var(--gray-500);margin-top:2px">{latest_alert_level} &middot; {latest_alert_date}</div>
    </div>
  </div>
  <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--gray-200);font-family:var(--mono);font-size:12px;color:var(--gray-600)">
    Latest to hit target: <span style="color:var(--red);font-weight:600">{latest_target_sym}</span> reached {latest_target_pct} on {latest_target_date}
  </div>
</div>"""
                            html = html.replace("{{ALERT_PROOF_BOX}}", proof_box)
                        except Exception as e2:
                            html = html.replace("{{ALERT_PROOF_BOX}}", "")
                    conn.close()
                except Exception as e:
                    html = html.replace("{{COLLAPSE_COUNT}}", "0")
                    html = html.replace("{{STRESS_COUNT}}", "0")
                    html = html.replace("{{LATEST_NAME}}", "—")
                    html = html.replace("{{LATEST_DATE}}", "—")
                    html = html.replace("{{LATEST_PRICE}}", "0")
                    html = html.replace("{{LATEST_PRICE_NOW}}", "0")
                    html = html.replace("{{LATEST_CHANGE}}", "—")
                    html = html.replace("{{WORST_NAME}}", "—")
                    html = html.replace("{{WORST_DATE}}", "—")
                    html = html.replace("{{WORST_CHANGE}}", "—")
                    html = html.replace("{{TOTAL_ALERTS}}", "0")
                return HTMLResponse(content=html)
            except:
                pass
        
        # /crypto paths → serve without prefix
        if path.startswith("/crypto"):
            return await call_next(request)
        
        # /token and /tokens pages pass through
        if path.startswith("/token"):
            return await call_next(request)

        # /paper-trading passes through
        if path.startswith("/paper-trading"):
            return await call_next(request)
        
        # /admin/dashboard passes through
        if path.startswith("/admin"):
            return await call_next(request)
        
        # Everything else on zarq.ai → redirect to crypto
        return await call_next(request)

