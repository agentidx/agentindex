"""
Add /best/{category} pages to seo_pages.py.
Shows top-rated agents per category with Trust Scores.
Critical for SEO long-tail queries like "best MCP servers" or "most trusted AI models".

Run: cd ~/agentindex && venv/bin/python add_best_pages.py
"""

FILE = "agentindex/seo_pages.py"

with open(FILE, "r") as f:
    content = f.read()

if "def best_in_class" in content:
    print("Best-in-class pages already exist. Skipping.")
    exit(0)

marker = "# ================================================================\n# HTML RENDERING"
pos = content.find(marker)
if pos == -1:
    print("ERROR: Could not find HTML RENDERING marker")
    exit(1)

BEST_PAGES = '''
    # ============================================================
    # /best/{category} - Best in Class Pages
    # ============================================================
    BEST_CATEGORIES = {
        "mcp-servers": ("mcp_server", "MCP Servers", "Model Context Protocol servers"),
        "ai-agents": ("agent", "AI Agents", "autonomous AI agents"),
        "ai-models": ("model", "AI Models", "machine learning models"),
        "ai-tools": ("tool", "AI Tools", "developer tools and utilities"),
        "datasets": ("dataset", "Datasets", "training and evaluation datasets"),
        "npm-packages": ("package", "npm Packages", "JavaScript/TypeScript AI packages"),
    }

    @app.get("/best", response_class=HTMLResponse)
    async def best_index():
        links = ""
        for slug, (_, label, desc) in BEST_CATEGORIES.items():
            links += '<div style="margin:12px 0"><a href="/best/' + slug + '" style="font-size:1.2em;color:#2563eb;font-weight:bold">' + label + '</a><br><span style="color:#6b7280">' + desc + '</span></div>'
        count = _agent_count_text()
        html = '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
        html += '<title>Best AI Agents by Trust Score | Nerq</title>'
        html += '<meta name="description" content="Top-rated AI agents, MCP servers, models, and tools ranked by Nerq Trust Score across ' + count + ' indexed agents.">'
        html += '<link rel="canonical" href="https://nerq.ai/best">'
        html += '<style>body{font-family:-apple-system,sans-serif;max-width:800px;margin:0 auto;padding:40px 20px;color:#1a1a2e;line-height:1.7}a{color:#2563eb}</style></head><body>'
        html += '<nav><a href="/">Nerq</a> &gt; Best in Class</nav>'
        html += '<h1>Best AI Agents by Trust Score</h1>'
        html += '<p>Top-rated agents across ' + count + ' indexed, scored by security, compliance, maintenance, popularity, and ecosystem.</p>'
        html += links
        html += '<footer style="margin-top:3em;border-top:1px solid #e5e7eb;padding-top:1em;color:#6b7280"><a href="/">Home</a> | <a href="/methodology">Methodology</a> | <a href="/discover">Search</a></footer>'
        html += '</body></html>'
        return HTMLResponse(content=html)

    @app.get("/best/{category}", response_class=HTMLResponse)
    async def best_in_class(category: str):
        if category not in BEST_CATEGORIES:
            return HTMLResponse(content="Category not found", status_code=404)

        agent_type, label, desc = BEST_CATEGORIES[category]
        session = get_session()
        result = session.execute(text(
            "SELECT id, name, trust_score_v2, trust_grade, author, source, stars, compliance_score, trust_dimensions "
            "FROM agents WHERE agent_type = :atype AND trust_score_v2 IS NOT NULL AND is_active = true "
            "ORDER BY trust_score_v2 DESC LIMIT 50"
        ), {"atype": agent_type})
        rows = result.fetchall()
        session.close()

        count = _agent_count_text()
        table_rows = ""
        for i, r in enumerate(rows):
            aid, name, score, grade, author, source, stars, comp, dims = r
            gc = _trust_grade_color(grade) if grade else "#888"
            table_rows += '<tr>'
            table_rows += '<td>' + str(i + 1) + '</td>'
            table_rows += '<td><a href="/agent/' + str(aid) + '">' + _esc(str(name)) + '</a></td>'
            table_rows += '<td><span style="background:' + gc + ';color:white;padding:2px 8px;border-radius:4px;font-weight:bold">' + str(grade or "?") + '</span></td>'
            table_rows += '<td>' + str(int(round(score))) if score else "?"
            table_rows += '</td>'
            table_rows += '<td>' + _esc(str(author or "")) + '</td>'
            table_rows += '<td>' + str(stars or 0) + '</td>'
            table_rows += '</tr>'

        html = '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
        html += '<title>Best ' + label + ' by Trust Score | Nerq</title>'
        html += '<meta name="description" content="Top 50 most trusted ' + desc + ' ranked by Nerq Trust Score. Security, compliance, maintenance, popularity, and ecosystem analysis across 52 jurisdictions.">'
        html += '<link rel="canonical" href="https://nerq.ai/best/' + category + '">'
        html += '<style>body{font-family:-apple-system,sans-serif;max-width:1000px;margin:0 auto;padding:40px 20px;color:#1a1a2e;line-height:1.7}a{color:#2563eb}table{width:100%;border-collapse:collapse;margin:1em 0}th,td{padding:8px 12px;border:1px solid #e5e7eb;text-align:left}th{background:#f9fafb}</style>'
        html += '<script type="application/ld+json">'
        html += '{"@context":"https://schema.org","@type":"ItemList","name":"Best ' + label + ' by Nerq Trust Score",'
        html += '"description":"Top 50 most trusted ' + desc + ' ranked by Nerq Trust Score",'
        html += '"numberOfItems":' + str(len(rows)) + ','
        html += '"itemListElement":['
        schema_items = []
        for i, r in enumerate(rows[:10]):
            schema_items.append('{"@type":"ListItem","position":' + str(i+1) + ',"url":"https://nerq.ai/agent/' + str(r[0]) + '","name":"' + str(r[1]).replace('"', '') + '"}')
        html += ','.join(schema_items)
        html += ']}</script>'
        html += '</head><body>'
        html += '<nav><a href="/">Nerq</a> &gt; <a href="/best">Best</a> &gt; ' + label + '</nav>'
        html += '<h1>Best ' + label + ' by Trust Score</h1>'
        html += '<p>Top 50 most trusted ' + desc + ' out of ' + count + ' total indexed agents. Ranked by <a href="/methodology">Nerq Trust Score</a> (security, compliance, maintenance, popularity, ecosystem).</p>'
        html += '<table><thead><tr><th>#</th><th>Name</th><th>Grade</th><th>Score</th><th>Author</th><th>Stars</th></tr></thead><tbody>'
        html += table_rows
        html += '</tbody></table>'
        html += '<p style="margin-top:2em"><a href="/data/trust-summary.json">Download full data</a> | <a href="/methodology">Methodology</a> | <a href="/best">All categories</a></p>'
        html += '<footer style="margin-top:2em;border-top:1px solid #e5e7eb;padding-top:1em;color:#6b7280">&copy; 2026 Nerq. ' + count + ' AI agents scored.</footer>'
        html += '</body></html>'
        return HTMLResponse(content=html)

'''

content = content[:pos] + BEST_PAGES + content[pos:]

with open(FILE, "w") as f:
    f.write(content)

total = len(content.splitlines())
print(f"Done! {FILE} now {total} lines")

import py_compile
try:
    py_compile.compile(FILE, doraise=True)
    print("Syntax check: OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
