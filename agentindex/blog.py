"""
Blog — Auto-published reports from nerq.ai
Routes: /blog, /blog/{slug}
Serves markdown files from docs/auto-reports/
"""
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, PlainTextResponse

from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

router_blog = APIRouter(tags=["blog"])

REPORTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "auto-reports"


def _md_to_html(md: str) -> str:
    """Minimal markdown to HTML (no external deps)."""
    lines = md.split("\n")
    html_lines = []
    in_table = False
    in_list = False
    in_code = False

    for line in lines:
        stripped = line.strip()

        # Code blocks
        if stripped.startswith("```"):
            if in_code:
                html_lines.append("</pre>")
                in_code = False
            else:
                html_lines.append("<pre>")
                in_code = True
            continue
        if in_code:
            html_lines.append(_esc(line))
            continue

        # Close list if not a list item
        if in_list and not stripped.startswith("- ") and not stripped.startswith("* "):
            html_lines.append("</ul>")
            in_list = False

        # Close table
        if in_table and not stripped.startswith("|"):
            html_lines.append("</tbody></table>")
            in_table = False

        # Headers
        if stripped.startswith("# "):
            html_lines.append(f"<h1>{_inline(stripped[2:])}</h1>")
        elif stripped.startswith("## "):
            html_lines.append(f"<h2>{_inline(stripped[3:])}</h2>")
        elif stripped.startswith("### "):
            html_lines.append(f"<h3>{_inline(stripped[4:])}</h3>")
        # Horizontal rule
        elif stripped in ("---", "***", "___"):
            html_lines.append("<hr>")
        # Table
        elif stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.match(r'^[-:]+$', c) for c in cells):
                continue  # separator row
            if not in_table:
                html_lines.append("<table><thead><tr>")
                html_lines.append("".join(f"<th>{_inline(c)}</th>" for c in cells))
                html_lines.append("</tr></thead><tbody>")
                in_table = True
            else:
                html_lines.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
        # List items
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{_inline(stripped[2:])}</li>")
        # Empty line
        elif not stripped:
            html_lines.append("")
        # Paragraph
        else:
            html_lines.append(f"<p>{_inline(stripped)}</p>")

    if in_list:
        html_lines.append("</ul>")
    if in_table:
        html_lines.append("</tbody></table>")
    if in_code:
        html_lines.append("</pre>")

    return "\n".join(html_lines)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(s: str) -> str:
    """Process inline markdown: bold, italic, code, links."""
    s = _esc(s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'\*(.+?)\*', r'<em>\1</em>', s)
    s = re.sub(r'`(.+?)`', r'<code>\1</code>', s)
    s = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', s)
    return s


def _list_articles() -> list[dict]:
    """List all published articles, newest first."""
    articles = []
    if not REPORTS_DIR.exists():
        return articles

    for f in sorted(REPORTS_DIR.glob("*-weekly.md"), reverse=True):
        slug = f.stem
        content = f.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        title = lines[0].lstrip("# ").strip() if lines else slug

        # Extract summary: first non-empty, non-header line
        summary = ""
        for line in lines[1:]:
            line = line.strip()
            if line and not line.startswith("#"):
                summary = line[:200]
                break

        # Date from slug (YYYY-MM-DD-weekly)
        date_str = slug.replace("-weekly", "")
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
            date_display = date.strftime("%B %d, %Y")
        except ValueError:
            date_display = date_str

        articles.append({
            "slug": slug,
            "title": title,
            "summary": summary,
            "date": date_display,
            "date_raw": date_str,
        })

    return articles


@router_blog.get("/blog", response_class=HTMLResponse)
def blog_index():
    """Blog listing page."""
    articles = _list_articles()

    article_cards = ""
    for a in articles:
        article_cards += f"""<div class="card" style="margin-bottom:16px">
<h3 style="margin:0"><a href="/blog/{a['slug']}">{_esc(a['title'])}</a></h3>
<p class="desc" style="margin:4px 0 0">{_esc(a['summary'])}</p>
<p style="font-size:12px;color:#9ca3af;margin:4px 0 0">{a['date']}</p>
</div>"""

    if not article_cards:
        article_cards = '<p class="desc">No articles published yet.</p>'

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Blog — Nerq</title>
<meta name="description" content="Weekly data-driven reports on the AI agent ecosystem from Nerq.">
<link rel="canonical" href="https://nerq.ai/blog">
<meta name="robots" content="index, follow">
<style>{NERQ_CSS}</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:20px;padding-bottom:40px;max-width:720px">
<div class="breadcrumb"><a href="/">nerq</a> &rsaquo; blog</div>
<h1>blog</h1>
<p class="desc">Weekly data-driven reports on the AI agent ecosystem. Auto-generated from live index data.</p>
{article_cards}
</main>
{NERQ_FOOTER}
</body>
</html>""")


@router_blog.get("/blog/{slug}", response_class=HTMLResponse)
def blog_article(slug: str):
    """Serve a single blog article."""
    md_path = REPORTS_DIR / f"{slug}.md"
    if not md_path.exists():
        return HTMLResponse("<h1>Not found</h1>", status_code=404)

    content = md_path.read_text(encoding="utf-8")
    lines = content.strip().split("\n")
    title = lines[0].lstrip("# ").strip() if lines else slug
    body_html = _md_to_html(content)

    # Date from slug
    date_str = slug.replace("-weekly", "")
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        date_display = date.strftime("%B %d, %Y")
    except ValueError:
        date_display = date_str

    # Extract summary for meta
    summary = ""
    for line in lines[1:]:
        line = line.strip()
        if line and not line.startswith("#"):
            summary = line[:160]
            break

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)} — Nerq</title>
<meta name="description" content="{_esc(summary)}">
<link rel="canonical" href="https://nerq.ai/blog/{slug}">
<meta name="robots" content="index, follow">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Article","headline":"{_esc(title)}","datePublished":"{date_str}","author":{{"@type":"Organization","name":"Nerq","url":"https://nerq.ai"}},"publisher":{{"@type":"Organization","name":"Nerq","url":"https://nerq.ai"}}}}
</script>
<style>{NERQ_CSS}
article h1{{font-size:1.6rem;margin-bottom:4px}}
article h2{{margin-top:28px}}
article p{{margin:8px 0;line-height:1.7}}
article ul{{margin:8px 0 8px 20px}}
article li{{margin:4px 0;line-height:1.6}}
article table{{margin:12px 0}}
article hr{{border:none;border-top:1px solid #e5e7eb;margin:24px 0}}
article pre{{margin:12px 0}}
</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:20px;padding-bottom:40px;max-width:720px">
<div class="breadcrumb"><a href="/">nerq</a> &rsaquo; <a href="/blog">blog</a> &rsaquo; {date_display}</div>
<article>
<p style="font-size:13px;color:#9ca3af;margin-bottom:16px">{date_display}</p>
{body_html}
</article>
<p style="font-size:12px;color:#9ca3af;margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb">
Data from the <a href="/">Nerq</a> index &middot;
<a href="/blog">all articles</a> &middot;
<a href="/v1/agent/stats">live stats</a>
</p>
</main>
{NERQ_FOOTER}
</body>
</html>""")
