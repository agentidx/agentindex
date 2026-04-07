"""
Patch analytics.py to add System Health + Trust Score section to /admin/dashboard.
Adds a new KPI row and system health panel after existing KPIs.

Run: cd ~/agentindex && venv/bin/python patch_analytics.py
"""

FILE = "agentindex/analytics.py"

with open(FILE, "r") as f:
    content = f.read()

# Find the insertion point: after the closing </div> of the kpis section
# The KPIs section ends with: </div>\n\n<div class="grid">
old_marker = '</div>\n\n<div class="grid">'
if old_marker not in content:
    # Try alternate
    old_marker = '</div>\\n\\n<div class="grid">'
    if old_marker not in content:
        print("Trying to find marker in f-string...")
        # It's inside an f-string, look for the literal
        old_marker = """</div>

<div class="grid">"""
        if old_marker not in content:
            print("ERROR: Could not find insertion point")
            print("Looking for 'div class=\"grid\"'...")
            import re
            matches = [(m.start(), content[max(0,m.start()-30):m.start()+30]) for m in re.finditer(r'class="grid"', content)]
            for pos, ctx in matches:
                print(f"  Found at {pos}: ...{ctx}...")
            exit(1)

# Build the health section HTML
# We need to generate it dynamically, so we add Python code before the f-string return
# Find where render_dashboard builds the HTML

# Strategy: Add a function that generates the health HTML, call it in render_dashboard
# Find "def render_dashboard"
func_start = content.find("def render_dashboard")
if func_start == -1:
    print("ERROR: render_dashboard not found")
    exit(1)

# Add helper function before render_dashboard
HEALTH_FUNC = '''
def _get_system_health():
    """Generate system health + Trust Score KPIs for dashboard."""
    import subprocess
    from agentindex.db.models import get_session
    from sqlalchemy import text
    
    health = {}
    
    # Process count
    try:
        r = subprocess.run(["bash", "-c", 
            "ps aux | grep -E 'agentindex.run|uvicorn|mcp_sse|parser|dashboard' | grep -v grep | wc -l"],
            capture_output=True, text=True, timeout=5)
        health["processes"] = int(r.stdout.strip())
    except:
        health["processes"] = 0
    
    # Trust Score stats
    try:
        s = get_session()
        health["total_agents"] = s.execute(text("SELECT COUNT(*) FROM agents WHERE is_active = true")).scalar() or 0
        health["scored"] = s.execute(text("SELECT COUNT(*) FROM agents WHERE trust_score_v2 IS NOT NULL AND is_active = true")).scalar() or 0
        health["avg_score"] = float(s.execute(text("SELECT ROUND(AVG(trust_score_v2)::numeric, 1) FROM agents WHERE trust_score_v2 IS NOT NULL AND is_active = true")).scalar() or 0)
        
        # Grade distribution
        gc = s.execute(text("SELECT trust_grade, COUNT(*) FROM agents WHERE trust_score_v2 IS NOT NULL AND is_active = true GROUP BY trust_grade ORDER BY trust_grade")).fetchall()
        health["grades"] = {g: c for g, c in gc}
        
        # New agents last 24h
        health["new_24h"] = s.execute(text("SELECT COUNT(*) FROM agents WHERE first_indexed > NOW() - INTERVAL '24 hours'")).scalar() or 0
        
        # Snapshot date
        try:
            snap = s.execute(text("SELECT snapshot_date, COUNT(*) FROM trust_score_history GROUP BY snapshot_date ORDER BY snapshot_date DESC LIMIT 1")).fetchone()
            health["last_snapshot"] = str(snap[0]) if snap else "never"
            health["snapshot_count"] = snap[1] if snap else 0
        except:
            health["last_snapshot"] = "never"
            health["snapshot_count"] = 0
        
        s.close()
    except Exception as e:
        health["total_agents"] = 0
        health["scored"] = 0
        health["avg_score"] = 0
        health["grades"] = {}
        health["new_24h"] = 0
        health["last_snapshot"] = "error"
        health["snapshot_count"] = 0
    
    # API health
    try:
        import urllib.request
        r = urllib.request.urlopen("http://localhost:8000/v1/health", timeout=3)
        health["api_ok"] = r.status == 200
    except:
        health["api_ok"] = False
    
    # Build HTML
    proc_color = "#4ade80" if health["processes"] >= 4 else "#fbbf24" if health["processes"] >= 2 else "#f87171"
    api_color = "#4ade80" if health["api_ok"] else "#f87171"
    api_text = "OK" if health["api_ok"] else "DOWN"
    
    grade_colors = {"A+":"#059669","A":"#10b981","B":"#3b82f6","C":"#f59e0b","D":"#f97316","E":"#ef4444","F":"#991b1b"}
    grade_badges = ""
    for g in ["A+", "A", "B", "C", "D", "E", "F"]:
        c = health["grades"].get(g, 0)
        if c > 0:
            color = grade_colors.get(g, "#888")
            grade_badges += f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold;margin-right:4px">{g}: {c:,}</span>'
    
    html = f"""
<div style="margin-bottom:20px">
<h3 style="font-size:13px;color:#71717a;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">System Health + Trust Score</h3>
<div class="kpis">
<div class="kpi"><div class="label">Active Agents</div><div class="num">{health["total_agents"]:,}</div><div class="sub">{health["new_24h"]:,} new 24h</div></div>
<div class="kpi"><div class="label">Trust Scored</div><div class="num">{health["scored"]:,}</div><div class="sub">avg {health["avg_score"]}/100</div></div>
<div class="kpi"><div class="label">Processes</div><div class="num" style="color:{proc_color}">{health["processes"]}/5</div><div class="sub">run.py + API + MCP + parser + dash</div></div>
<div class="kpi"><div class="label">API Status</div><div class="num" style="color:{api_color}">{api_text}</div><div class="sub">nerq.ai/v1/health</div></div>
<div class="kpi"><div class="label">Last Snapshot</div><div class="num" style="font-size:16px">{health["last_snapshot"]}</div><div class="sub">{health["snapshot_count"]:,} agents</div></div>
</div>
<div style="margin-top:8px">{grade_badges}</div>
</div>
"""
    return html


'''

content = content[:func_start] + HEALTH_FUNC + content[func_start:]
print("[1] Added _get_system_health() function")

# Now inject the call into the HTML template
# Find the marker again (position shifted due to insertion)
old_section = """</div>

<div class="grid">"""
new_section = """</div>

{health_section}

<div class="grid">"""

content = content.replace(old_section, new_section, 1)
print("[2] Added health_section placeholder in HTML")

# Add health_section = _get_system_health() before the f-string
# Find "hourly_bars" generation which is just before the f-string
hourly_marker = "hourly_bars = "
pos = content.find(hourly_marker)
if pos > 0:
    # Find the line start
    line_start = content.rfind("\n", 0, pos) + 1
    indent = "    "
    content = content[:pos] + "health_section = _get_system_health()\n" + indent + content[pos:]
    print("[3] Added health_section = _get_system_health() call")
else:
    print("[3] WARNING: Could not find hourly_bars, trying alternate injection")
    # Try to find just before the return/f-string
    fstring_marker = '    return f"""'
    pos = content.find(fstring_marker)
    if pos > 0:
        content = content[:pos] + "    health_section = _get_system_health()\n" + content[pos:]
        print("[3] Added health_section call before f-string")

with open(FILE, "w") as f:
    f.write(content)

print(f"\nDone! {FILE} now {len(content.splitlines())} lines")

import py_compile
try:
    py_compile.compile(FILE, doraise=True)
    print("Syntax check: OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
