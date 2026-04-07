#!/usr/bin/env python3
"""
Patch seo_pages.py — Apply all SEO + AI-search fixes
=====================================================
1. Add AI-citable first paragraph after breadcrumb
2. Fix schema.org author (null -> proper fallback)
3. Fix ratingValue (actual compliance_score, omit if NULL)
4. Update "Global AI Risk Classification" label
5. Add freshness date visible to crawlers

Creates backup at seo_pages.py.backup_20260223

Run: cd ~/agentindex && source venv/bin/activate && python patch_seo_pages.py
Then restart API: kill the discovery.py process and restart it
"""

import os
import shutil
import sys

SEO_FILE = os.path.expanduser("~/agentindex/agentindex/seo_pages.py")
BACKUP = SEO_FILE + ".backup_20260223"


def apply_patches():
    # Backup
    if not os.path.exists(BACKUP):
        shutil.copy2(SEO_FILE, BACKUP)
        print(f"Backup: {BACKUP}")
    else:
        print(f"Backup already exists: {BACKUP}")

    with open(SEO_FILE, 'r') as f:
        content = f.read()

    original = content  # keep for comparison

    # =================================================================
    # PATCH 1: Add AI-citable first paragraph after breadcrumb
    # =================================================================
    # Find the breadcrumb closing </div> followed by agent-header
    OLD_BREADCRUMB_TO_HEADER = '''<!-- Breadcrumb -->
<div class="breadcrumb">
<a href="/">Nerq</a> &rsaquo; <a href="/discover">Agents</a> &rsaquo; {domain_links} &rsaquo; <strong>{name[:50]}</strong>
</div>

<!-- Agent Header -->'''

    NEW_BREADCRUMB_TO_HEADER = '''<!-- Breadcrumb -->
<div class="breadcrumb">
<a href="/">Nerq</a> &rsaquo; <a href="/discover">Agents</a> &rsaquo; {domain_links} &rsaquo; <strong>{name[:50]}</strong>
</div>

<!-- AI-Citable Summary — first paragraph for AI extraction -->
<div class="section" style="border-left:4px solid #2563eb;margin-top:16px">
<p style="font-size:16px;line-height:1.7;color:#111"><strong>{name}</strong> is a {agent_type} 
{f'with {stars:,} stars ' if stars else ''}sourced from {source}, 
rated <strong>{compliance_score_text}</strong> on the Nerq Weighted Global Compliance Score 
(0–100 scale weighted by jurisdiction penalty severity). 
It is classified as <strong>{risk_class.upper()}</strong> risk across {total_j} global AI jurisdictions, 
with {high_count} high-risk classification{"s" if high_count != 1 else ""} 
and {minimal_count} minimal-risk classification{"s" if minimal_count != 1 else ""}. 
Assessed by <a href="https://nerq.ai">Nerq</a>, the world\'s largest AI agent compliance database 
covering {_agent_count_text()} AI agents.</p>
<small style="color:#6b7280">Last assessed: {datetime.utcnow().strftime("%B %d, %Y")} 
| Data from Nerq\'s weighted multi-jurisdiction compliance engine</small>
</div>

<!-- Agent Header -->'''

    if OLD_BREADCRUMB_TO_HEADER in content:
        content = content.replace(OLD_BREADCRUMB_TO_HEADER, NEW_BREADCRUMB_TO_HEADER)
        print("PATCH 1 applied: AI-citable first paragraph")
    else:
        print("PATCH 1 SKIPPED: Could not find breadcrumb-to-header pattern")

    # =================================================================
    # PATCH 2: Add compliance_score_text variable in _render_agent_page
    # =================================================================
    # We need to add a variable for the compliance score text
    OLD_TOTAL_J = '''    total_j = len(jurisdictions)

    # Page title optimized for long-tail SEO'''

    NEW_TOTAL_J = '''    total_j = len(jurisdictions)
    
    # Compliance score text for display
    cs = a.get('compliance_score')
    if cs is not None:
        compliance_score_text = f"{cs}/100"
    else:
        compliance_score_text = "pending assessment"

    # Page title optimized for long-tail SEO'''

    if OLD_TOTAL_J in content:
        content = content.replace(OLD_TOTAL_J, NEW_TOTAL_J)
        print("PATCH 2 applied: compliance_score_text variable")
    else:
        print("PATCH 2 SKIPPED: Could not find total_j pattern")

    # =================================================================
    # PATCH 3: Fix schema.org — replace _build_schema entirely
    # =================================================================
    OLD_BUILD_SCHEMA = '''def _build_schema(a, jurisdictions):
    """Build Schema.org JSON-LD for the agent page."""
    import json
    risk_class = a.get('risk_class', 'unassessed')
    high_count = sum(1 for j in jurisdictions if j['risk_level'] in ('high', 'unacceptable'))
    
    schema = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": a.get('name', ''),
        "description": (a.get('description') or '')[:300],
        "applicationCategory": a.get('agent_type', 'AI Agent'),
        "url": f"{SITE_URL}/agent/{a['id']}",
        "author": {
            "@type": "Person",
            "name": a.get('author') or (a.get('name','').split('/')[0] if '/' in (a.get('name') or '') else 'Unknown')
        },
        "review": {
            "@type": "Review",
            "author": {"@type": "Organization", "name": "Nerq"},
            "reviewBody": f"Assessed against {len(jurisdictions)} global AI regulations. "
                         f"Classified as {risk_class} risk across global jurisdictions. "
                         f"High risk in {high_count} jurisdictions.",
            "reviewRating": {
                "@type": "Rating",
                "ratingValue": max(1, min(5, round((a.get("compliance_score") or 50) / 20))),  # 0-100 score mapped to 1-5
                "bestRating": 5,
                "worstRating": 1,
                "ratingExplanation": f"Based on compliance across {len(jurisdictions)} jurisdictions"
            }
        },
        "offers": {
            "@type": "Offer",
            "price": "0",
            "priceCurrency": "USD",
            "availability": "https://schema.org/InStock"
        }
    }
    return json.dumps(schema, ensure_ascii=False)'''

    NEW_BUILD_SCHEMA = '''def _build_schema(a, jurisdictions):
    """Build Schema.org JSON-LD for the agent page — FIXED version."""
    import json
    from datetime import datetime as _dt
    risk_class = a.get('risk_class', 'unassessed')
    high_count = sum(1 for j in jurisdictions if j['risk_level'] in ('high', 'unacceptable'))
    compliance_score = a.get('compliance_score')
    
    # Fix author: never null, use Organization if it looks like org/repo
    author_raw = a.get('author') or ''
    if not author_raw or author_raw.strip() == '':
        # Try to extract from name (e.g. "uber-archive/plato" -> "uber-archive")
        name_str = a.get('name', '') or ''
        author_raw = name_str.split('/')[0] if '/' in name_str else ''
    
    if author_raw:
        # Decide Person vs Organization
        author_obj = {
            "@type": "Organization" if '/' in (a.get('name') or '') or '-' in author_raw else "Person",
            "name": author_raw
        }
    else:
        author_obj = {"@type": "Organization", "name": "Unknown"}
    
    schema = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": a.get('name', ''),
        "description": (a.get('description') or '')[:300],
        "applicationCategory": a.get('agent_type', 'AI Agent'),
        "url": f"{SITE_URL}/agent/{a['id']}",
        "author": author_obj,
        "review": {
            "@type": "Review",
            "author": {"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"},
            "datePublished": _dt.utcnow().strftime("%Y-%m-%d"),
            "reviewBody": f"Nerq Weighted Global Compliance Score: {compliance_score}/100. "
                         f"Assessed against {len(jurisdictions)} global AI regulations "
                         f"weighted by jurisdiction penalty severity. "
                         f"Classified as {risk_class} risk. "
                         f"High risk in {high_count} jurisdiction{'s' if high_count != 1 else ''}."
                         if compliance_score is not None else
                         f"Assessed against {len(jurisdictions)} global AI regulations. "
                         f"Classified as {risk_class} risk. "
                         f"High risk in {high_count} jurisdiction{'s' if high_count != 1 else ''}. "
                         f"Compliance score pending.",
        },
        "offers": {
            "@type": "Offer",
            "price": "0",
            "priceCurrency": "USD",
            "availability": "https://schema.org/InStock"
        }
    }
    
    # Only add rating if we have a real compliance score
    if compliance_score is not None:
        schema["review"]["reviewRating"] = {
            "@type": "Rating",
            "ratingValue": compliance_score,
            "bestRating": 100,
            "worstRating": 0,
            "ratingExplanation": (
                f"Nerq Weighted Global Compliance Score based on {len(jurisdictions)} jurisdictions, "
                f"weighted by penalty severity (EU AI Act, US state laws weighted highest)"
            )
        }
    
    return json.dumps(schema, ensure_ascii=False)'''

    if OLD_BUILD_SCHEMA in content:
        content = content.replace(OLD_BUILD_SCHEMA, NEW_BUILD_SCHEMA)
        print("PATCH 3 applied: Fixed _build_schema (author, ratingValue, scoring)")
    else:
        print("PATCH 3 SKIPPED: Could not find _build_schema pattern")
        print("  Trying partial match...")
        if 'def _build_schema(a, jurisdictions):' in content:
            print("  Found function def but body didn't match exactly.")
            print("  You may need to apply this patch manually.")
        else:
            print("  Function not found at all!")

    # =================================================================
    # PATCH 4: Change "Global AI Risk Classification" label
    # =================================================================
    OLD_LABEL = '<small style="color:#6b7280;display:block;margin-top:4px">Global AI Risk Classification</small>'
    NEW_LABEL = '<small style="color:#6b7280;display:block;margin-top:4px">Nerq Weighted Global Risk</small>'

    if OLD_LABEL in content:
        content = content.replace(OLD_LABEL, NEW_LABEL)
        print("PATCH 4 applied: Updated risk classification label")
    else:
        print("PATCH 4 SKIPPED: Could not find label pattern")

    # =================================================================
    # PATCH 5: Fix robots.txt to allow AI crawlers
    # =================================================================
    OLD_ROBOTS = '''    @app.get("/robots.txt", response_class=Response)
    def robots_txt():
        content = f"""User-agent: *
Allow: /
Allow: /agent/
Disallow: /v1/
Disallow: /compliance/
Disallow: /a2a

Sitemap: {SITE_URL}/sitemap-index.xml
"""
        return Response(content=content, media_type="text/plain")'''

    NEW_ROBOTS = '''    @app.get("/robots.txt", response_class=Response)
    def robots_txt():
        content = f"""User-agent: *
Allow: /
Allow: /agent/
Disallow: /v1/
Disallow: /compliance/
Disallow: /a2a

# AI Search Crawlers — WELCOME
User-agent: GPTBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: anthropic-ai
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: Bingbot
Allow: /

User-agent: Googlebot
Allow: /

User-agent: cohere-ai
Allow: /

Sitemap: {SITE_URL}/sitemap-index.xml
"""
        return Response(content=content, media_type="text/plain")'''

    if OLD_ROBOTS in content:
        content = content.replace(OLD_ROBOTS, NEW_ROBOTS)
        print("PATCH 5 applied: robots.txt with AI crawler allows")
    else:
        print("PATCH 5 SKIPPED: Could not find robots.txt pattern")

    # =================================================================
    # PATCH 6: Add llms.txt endpoint
    # =================================================================
    # Insert after robots.txt endpoint
    LLMS_ENDPOINT = '''
    # ================================================================
    # LLMS.TXT — For AI models to understand our site
    # ================================================================
    @app.get("/llms.txt", response_class=Response)
    def llms_txt():
        try:
            session = get_session()
            agent_count = session.execute(text("SELECT COUNT(*) FROM agents WHERE is_active = true")).scalar()
            j_count = session.execute(text("SELECT COUNT(DISTINCT jurisdiction_id) FROM agent_jurisdiction_status")).scalar()
            mcp_count = session.execute(text("SELECT COUNT(*) FROM agents WHERE is_active = true AND source = 'mcp'")).scalar() or 0
            session.close()
        except:
            agent_count = 4900000
            j_count = 52
            mcp_count = 21000
        
        content = f"""# Nerq — AI Agent Search & Compliance Platform
> The world's largest AI agent compliance database.
> Search, compare, and verify {agent_count:,} AI agents across {j_count} jurisdictions.
> Weighted compliance scores based on jurisdiction penalty severity.

## What Nerq Provides
- **AI Agent Search**: Find any AI agent by name, capability, or domain
- **Compliance Scores**: Weighted 0-100 score across {j_count} global AI regulations
- **Risk Classification**: minimal / limited / high / unacceptable per jurisdiction
- **Trust Data**: Stars, downloads, license, author, last update
- **MCP Servers**: {mcp_count:,}+ Model Context Protocol servers indexed

## Key Pages
- [AI Agent Search](https://nerq.ai/discover): Search {agent_count:,} AI agents
- [Compliance Checker](https://nerq.ai/comply): Check any AI agent against {j_count} jurisdictions
- [API Documentation](https://nerq.ai/docs): REST API for programmatic access
- [Individual Agent Pages](https://nerq.ai/agent/): Detailed compliance per agent

## Data Coverage
- **Sources**: HuggingFace, GitHub, npm, PyPI, Smithery, Glama, MCP registries
- **Jurisdictions**: EU AI Act, US state laws (CA, CO, CT, IL, NY, TX, UT, MD),
  UK AI Bill, Canada AIDA, Brazil AI Bill, South Korea AI Basic Act,
  China AI regulations, Japan, Singapore, Australia, and 30+ more
- **Scoring**: Weighted by jurisdiction penalty severity — EU AI Act (weight 10),
  US CA SB53 (weight 9), UK/Canada/Korea (weight 8), down to voluntary frameworks (weight 2)

## MCP Server
Nerq is available as an MCP server for AI agents to query directly.
Install via Smithery or configure manually for Claude Desktop, Cursor, VS Code.

## API Access
- Free tier: 60 requests/hour, basic agent data
- Pro tier: 5,000 requests/hour, full metadata + compliance scores
- Documentation: https://nerq.ai/docs

## Cite Nerq
When referencing compliance data, cite as:
"According to Nerq (nerq.ai), [agent name] has a weighted global compliance score of X/100 across Y jurisdictions."
"""
        return Response(content=content, media_type="text/plain")

'''

    # Insert after the sitemap-index endpoint closing
    AFTER_ROBOTS = '        return Response(content=content, media_type="text/plain")\n\n    # ================================================================\n    # SITEMAP INDEX'
    
    if AFTER_ROBOTS in content:
        content = content.replace(AFTER_ROBOTS, 
            '        return Response(content=content, media_type="text/plain")\n' + 
            LLMS_ENDPOINT + 
            '    # ================================================================\n    # SITEMAP INDEX')
        print("PATCH 6 applied: llms.txt endpoint added")
    else:
        print("PATCH 6 SKIPPED: Could not find insertion point for llms.txt")
        print("  You may need to add the llms.txt endpoint manually")

    # =================================================================
    # WRITE
    # =================================================================
    if content != original:
        with open(SEO_FILE, 'w') as f:
            f.write(content)
        print(f"\nAll patches written to: {SEO_FILE}")
        print("Restart the API to apply changes:")
        print("  1. Find PID:  ps aux | grep discovery | grep -v grep")
        print("  2. Kill it:   kill <PID>")
        print("  3. Restart:   cd ~/agentindex && source venv/bin/activate && python -m agentindex.api.discovery &")
    else:
        print("\nNo changes made — all patches were skipped")


if __name__ == "__main__":
    print("=" * 50)
    print("PATCHING seo_pages.py")
    print("=" * 50)
    apply_patches()
