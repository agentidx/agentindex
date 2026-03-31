"""
RSS Feed — nerq.ai
Route: GET /feed.xml
Generates RSS 2.0 XML from docs/auto-reports/*.md
"""
import os
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import Response

router_rss = APIRouter(tags=["feed"])

REPORTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "auto-reports"


def _escape_xml(s: str) -> str:
    """Escape XML entities."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter (between --- markers) and remaining body.

    Returns (metadata_dict, body_text).
    If no frontmatter, returns empty dict and full content.
    """
    if not content.startswith("---"):
        return {}, content

    end = content.find("---", 3)
    if end == -1:
        return {}, content

    fm_block = content[3:end].strip()
    body = content[end + 3:].strip()

    meta = {}
    for line in fm_block.split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip().strip('"').strip("'")

    return meta, body


def _build_items() -> list[dict]:
    """Read all markdown files and build RSS items."""
    items = []
    if not REPORTS_DIR.exists():
        return items

    for f in REPORTS_DIR.glob("*.md"):
        content = f.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(content)

        slug = f.stem

        # Title: from frontmatter, or first H1, or filename
        title = meta.get("title")
        if not title:
            lines = content.strip().split("\n")
            if lines and lines[0].startswith("# "):
                title = lines[0].lstrip("# ").strip()
            else:
                title = slug.replace("-", " ").replace("_", " ").title()

        # Date: from frontmatter, or filename pattern, or file mtime
        date_str = meta.get("date")
        pub_date = None
        if date_str:
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%B %d, %Y"):
                try:
                    pub_date = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue

        if pub_date is None:
            # Try extracting date from filename (e.g. 2026-03-10-weekly)
            m = re.match(r"(\d{4}-\d{2}-\d{2})", slug)
            if m:
                try:
                    pub_date = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

        if pub_date is None:
            mtime = os.path.getmtime(f)
            pub_date = datetime.fromtimestamp(mtime, tz=timezone.utc)

        # Description: first 200 chars of body after frontmatter, skip headers
        description = ""
        for line in body.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("---"):
                description = line[:200]
                break

        link = f"https://nerq.ai/blog/{slug}"

        items.append({
            "title": title,
            "link": link,
            "description": description,
            "pub_date": pub_date,
            "guid": link,
        })

    # Sort by date descending, limit to 50
    items.sort(key=lambda x: x["pub_date"], reverse=True)
    return items[:50]


@router_rss.get("/feed.xml")
@router_rss.get("/rss.xml")
@router_rss.get("/blog/feed.xml")
@router_rss.get("/blog/rss.xml")
def rss_feed():
    """RSS 2.0 feed of blog articles."""
    now = format_datetime(datetime.now(timezone.utc))
    items = _build_items()

    items_xml = ""
    for item in items:
        pub = format_datetime(item["pub_date"])
        items_xml += f"""    <item>
      <title>{_escape_xml(item['title'])}</title>
      <link>{item['link']}</link>
      <description>{_escape_xml(item['description'])}</description>
      <pubDate>{pub}</pubDate>
      <guid>{item['guid']}</guid>
    </item>
"""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Nerq — AI Agent Trust Intelligence</title>
    <link>https://nerq.ai</link>
    <description>Trust scores, scout reports, and ecosystem analysis for 204K+ AI agents</description>
    <language>en</language>
    <lastBuildDate>{now}</lastBuildDate>
{items_xml}  </channel>
</rss>"""

    return Response(content=xml, media_type="application/rss+xml")
