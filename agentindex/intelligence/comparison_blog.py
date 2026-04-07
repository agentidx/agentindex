"""
Comparison Blog Pages
=====================
Serves auto-generated comparison posts at /blog/<slug>.

Usage in discovery.py:
    from agentindex.intelligence.comparison_blog import mount_comparison_blog
    mount_comparison_blog(app)
"""

import json
import logging
import sqlite3

from fastapi.responses import HTMLResponse, Response

logger = logging.getLogger("nerq.comparison-blog")

SQLITE_DB = "/Users/anstudio/agentindex/data/crypto_trust.db"


def _esc(s):
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def mount_comparison_blog(app):
    """Mount comparison blog routes."""

    @app.get("/blog/{slug}", response_class=HTMLResponse)
    async def blog_post(slug: str):
        try:
            conn = sqlite3.connect(SQLITE_DB, timeout=10)
            row = conn.execute(
                "SELECT title, content, faq, category, agents, winner FROM auto_comparisons WHERE slug = ?",
                (slug,)
            ).fetchone()
            conn.close()
        except Exception:
            row = None

        if not row:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/insights", status_code=301)

        title, content, faq_str, category, agents_str, winner = row
        faq = json.loads(faq_str) if faq_str else []
        agents = json.loads(agents_str) if agents_str else []

        # Convert markdown-ish content to HTML (basic)
        html_content = content.replace("\n\n", "</p><p>").replace("\n", "<br>")
        # Handle headers
        for i in range(3, 0, -1):
            prefix = "#" * i + " "
            html_content = html_content.replace(f"<br>{prefix}", f"</p><h{i}>")
            html_content = html_content.replace(f"<p>{prefix}", f"<h{i}>")
            # Close headers at next paragraph
            import re
            html_content = re.sub(f"<h{i}>([^<]+)</p>", f"<h{i}>\\1</h{i}><p>", html_content)

        # Handle tables
        lines = content.split("\n")
        table_html = ""
        in_table = False
        for line in lines:
            if line.strip().startswith("|") and "|" in line[1:]:
                if not in_table:
                    table_html += "<table style='width:100%;border-collapse:collapse;margin:16px 0'>"
                    in_table = True
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if all(c.replace("-", "") == "" for c in cells):
                    continue
                tag = "th" if not table_html.count("<tr>") else "td"
                table_html += "<tr>" + "".join(f"<{tag} style='padding:8px;border:1px solid #e5e7eb'>{_esc(c)}</{tag}>" for c in cells) + "</tr>"
            elif in_table:
                table_html += "</table>"
                in_table = False
        if in_table:
            table_html += "</table>"

        # FAQ schema
        faq_jsonld = json.dumps({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q["q"],
                 "acceptedAnswer": {"@type": "Answer", "text": q["a"]}}
                for q in faq
            ]
        })

        try:
            from agentindex.nerq_design import nerq_page
            body = f"""
<article>
<h1>{_esc(title)}</h1>
<p style="color:#6b7280;font-size:14px">Category: {_esc(category)} · Winner: {_esc(winner)}</p>
{table_html}
<div style="line-height:1.8">{html_content}</div>
</article>

<div class="faq-section">
<h2>FAQ</h2>
"""
            for q in faq:
                body += f'<div class="faq-item"><div class="faq-q">{_esc(q["q"])}</div><div class="faq-a">{_esc(q["a"])}</div></div>'
            body += "</div>"

            page = nerq_page(title, body, description=f"Independent comparison: {title}")
            page = page.replace("</head>", f'<script type="application/ld+json">{faq_jsonld}</script></head>')
            return HTMLResponse(content=page)
        except Exception:
            return HTMLResponse(content=f"<h1>{_esc(title)}</h1>{html_content}")

    @app.get("/blog", response_class=HTMLResponse)
    async def blog_index():
        try:
            conn = sqlite3.connect(SQLITE_DB, timeout=10)
            rows = conn.execute(
                "SELECT slug, title, category, winner, generated_at FROM auto_comparisons ORDER BY generated_at DESC LIMIT 50"
            ).fetchall()
            conn.close()
        except Exception:
            rows = []

        try:
            from agentindex.nerq_design import nerq_page
            body = "<h1>Blog — AI Agent Comparisons</h1><p>Independent trust comparisons based on 204K+ AI assets.</p>"
            for r in rows:
                body += f'<div style="border-bottom:1px solid #e5e7eb;padding:16px 0"><a href="/blog/{_esc(r[0])}" style="font-size:18px;font-weight:600">{_esc(r[1])}</a><br><span style="font-size:13px;color:#6b7280">{_esc(r[2])} · Winner: {_esc(r[3])} · {r[4][:10] if r[4] else ""}</span></div>'
            if not rows:
                body += "<p>No comparison posts yet. Check back soon.</p>"
            return HTMLResponse(content=nerq_page("Blog — AI Agent Comparisons", body))
        except Exception:
            return HTMLResponse(content="<h1>Blog</h1><p>Comparisons coming soon.</p>")

    logger.info("Comparison blog mounted")
