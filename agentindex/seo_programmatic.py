"""
Nerq Programmatic SEO Module
==============================
High-value SEO page routes: comparisons, best-of, alternatives, guides, sitemaps.

Usage in discovery.py:
    from agentindex.seo_programmatic import mount_seo_programmatic
    mount_seo_programmatic(app)
"""

import html
import json
import logging
import os
import re
import time
from datetime import date

from fastapi import Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.sql import text

from agentindex.db.models import get_db_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER, render_hreflang

logger = logging.getLogger("nerq.seo_programmatic")

SITE = "https://nerq.ai"
TODAY = date.today().isoformat()
YEAR = date.today().year

# ── Simple cache ────────────────────────────────────────────
_cache: dict[str, tuple[float, object]] = {}
CACHE_TTL = 3600  # 1 hour


def _cached(key: str):
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < CACHE_TTL:
        return entry[1]
    return None


def _set_cache(key: str, val):
    _cache[key] = (time.time(), val)
    return val


# ── Grade color helper ──────────────────────────────────────
def _grade_color(grade: str | None) -> str:
    if not grade:
        return "#6b7280"
    g = grade.upper().rstrip("+- ")
    if g in ("A", "AA"):
        return "#065f46"
    if g == "B":
        return "#1e40af"
    if g == "C":
        return "#92400e"
    return "#991b1b"


def _grade_pill(grade: str | None) -> str:
    g = html.escape(grade or "N/A")
    color = _grade_color(grade)
    return f'<span style="color:{color};font-weight:700">{g}</span>'


# ── Slug helpers ────────────────────────────────────────────
def _to_slug(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _safe_slug(name: str) -> str:
    """Build /is-{slug}-safe path slug."""
    return _to_slug(name)


# ── HTML helpers ────────────────────────────────────────────
def _page(title: str, body: str, desc: str = "", canonical: str = "",
          jsonld: str = "", robots: str = "index, follow",
          og_title: str = "", og_desc: str = "",
          nerq_type: str = "", nerq_tools: str = "",
          nerq_verdict: str = "", extra_ld: str = "") -> str:
    og_t = html.escape(og_title or title)
    og_d = html.escape(og_desc or desc)
    canon = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    _path = canonical.replace("https://nerq.ai", "") if canonical else ""
    _hreflang = render_hreflang(_path) if _path else ""
    meta_desc = f'<meta name="description" content="{html.escape(desc)}">' if desc else ""
    ld = f'<script type="application/ld+json">{jsonld}</script>' if jsonld else ""
    extra_ld_tag = f'<script type="application/ld+json">{extra_ld}</script>' if extra_ld else ""
    nerq_meta = ""
    if nerq_type:
        nerq_meta += f'<meta name="nerq:type" content="{html.escape(nerq_type)}">\n'
    if nerq_tools:
        nerq_meta += f'<meta name="nerq:tools" content="{html.escape(nerq_tools)}">\n'
    if nerq_verdict:
        nerq_meta += f'<meta name="nerq:verdict" content="{html.escape(nerq_verdict)}">\n'
    nerq_meta += f'<meta name="nerq:updated" content="{TODAY}">\n'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
{meta_desc}
<meta name="robots" content="{robots}">
<meta property="og:title" content="{og_t}">
<meta property="og:description" content="{og_d}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Nerq">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{og_t}">
<meta name="twitter:description" content="{og_d}">
{nerq_meta}
{canon}
{_hreflang}
{ld}
{extra_ld_tag}
<style>{NERQ_CSS}</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:20px;padding-bottom:40px">
{body}
</main>
{NERQ_FOOTER}
</body>
</html>"""


def _breadcrumb(*parts: tuple[str, str]) -> str:
    items = ['<a href="/">nerq</a>']
    for href, label in parts:
        if href:
            items.append(f'<a href="{href}">{html.escape(label)}</a>')
        else:
            items.append(html.escape(label))
    return f'<div class="breadcrumb">{" &rsaquo; ".join(items)}</div>'


def _faq_section(items: list[tuple[str, str]]) -> str:
    rows = ""
    faq_ld_items = []
    for q, a in items:
        rows += f'<details style="margin:8px 0;border:1px solid #e5e7eb;padding:12px"><summary style="cursor:pointer;font-weight:600">{html.escape(q)}</summary><p style="margin-top:8px;color:#4b5563">{a}</p></details>'
        faq_ld_items.append({"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}})
    return f'<h2>FAQ</h2>{rows}'


def _trunc(s: str | None, n: int = 100) -> str:
    if not s:
        return ""
    s = s.strip()
    return (s[:n] + "...") if len(s) > n else s


def _score_fmt(v) -> str:
    if v is None:
        return "N/A"
    try:
        return f"{float(v):.0f}"
    except (TypeError, ValueError):
        return "N/A"


def _stars_fmt(v) -> str:
    if not v:
        return "-"
    try:
        n = int(v)
        if n >= 1000:
            return f"{n / 1000:.1f}k"
        return str(n)
    except (TypeError, ValueError):
        return "-"


# ── Agent lookup ────────────────────────────────────────────
_AGENT_COLS = "id, name, category, trust_score_v2, trust_grade, stars, language, description, security_score, activity_score, documentation_score, popularity_score, eu_risk_class, source, source_url, author, agent_type, downloads, license"


def _find_agent(session, slug: str) -> dict | None:
    cache_key = f"agent:{slug}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    # Check software_registry FIRST (consumer overrides + exact match)
    try:
        from agentindex.agent_safety_pages import _resolve_entity
        resolved = _resolve_entity(slug)
        if not resolved:
            norm = slug.lower().replace("-", "").replace("_", "")
            if norm != slug.lower():
                resolved = _resolve_entity(norm)
        if resolved and resolved.get("trust_score"):
            # Convert to agent-like dict
            return _set_cache(cache_key, {
                "name": resolved["name"],
                "trust_score_v2": resolved.get("trust_score"),
                "trust_grade": resolved.get("trust_grade"),
                "category": resolved.get("category"),
                "source": resolved.get("source"),
                "source_url": resolved.get("source_url", ""),
                "stars": resolved.get("stars", 0),
                "author": resolved.get("author", ""),
                "description": resolved.get("description", ""),
                "language": "",
                "license": resolved.get("license", ""),
                "security_score": resolved.get("security_score"),
                "activity_score": resolved.get("maintenance_score"),
                "documentation_score": None,
                "popularity_score": resolved.get("popularity_score"),
                "is_verified": resolved.get("is_verified", False),
                "compliance_score": None,
                "eu_risk_class": None,
            })
    except Exception:
        pass

    # Fallback: agents table exact name match (language column needed, not in entity_lookup)
    session.execute(text("SET LOCAL work_mem = '2MB'; SET LOCAL statement_timeout = '5s'"))
    row = session.execute(text(
        f"SELECT {_AGENT_COLS} FROM agents WHERE LOWER(name) = :s AND is_active = true LIMIT 1"
    ), {"s": slug.lower()}).fetchone()

    if not row:
        # Slug-style match: replace hyphens with patterns
        pattern = slug.replace("-", "%")
        row = session.execute(text(
            f"SELECT {_AGENT_COLS} FROM agents WHERE LOWER(name) LIKE :p AND is_active = true ORDER BY COALESCE(stars, 0) DESC LIMIT 1"
        ), {"p": f"%{pattern}%"}).fetchone()

    if not row:
        return None
    cols = [c.strip() for c in _AGENT_COLS.split(",")]
    agent = dict(zip(cols, row))
    return _set_cache(cache_key, agent)


# ── Categories for best-of pages ────────────────────────────
BEST_CATEGORIES = {
    "code-review-tools": ("Code Review Tools", ["code_review", "code_assistant"], ["code review", "linting"]),
    "mcp-servers": ("MCP Servers", ["mcp_server"], ["mcp"]),
    "langchain-alternatives": ("LangChain Alternatives", ["agent_framework", "llm_tool"], ["langchain", "agent framework"]),
    "ai-coding-assistants": ("AI Coding Assistants", ["code_assistant", "coding_agent"], ["code", "coding", "ide"]),
    "agent-frameworks": ("Agent Frameworks", ["agent_framework"], ["agent", "framework", "orchestrat"]),
    "llm-providers": ("LLM Providers", ["llm_provider", "llm_tool"], ["llm", "language model", "gpt"]),
    "vector-databases": ("Vector Databases", ["database", "vector_db"], ["vector", "embedding", "pinecone"]),
    "ai-image-generators": ("AI Image Generators", ["image_generation"], ["image", "diffusion", "stable"]),
    "open-source-llms": ("Open Source LLMs", ["llm", "model"], ["open source", "llama", "mistral"]),
    "ai-automation-tools": ("AI Automation Tools", ["automation"], ["automat", "workflow", "n8n"]),
    "data-analysis-tools": ("Data Analysis Tools", ["data_analysis"], ["data", "analytics", "pandas"]),
    "chatbot-frameworks": ("Chatbot Frameworks", ["chatbot"], ["chatbot", "conversational"]),
    "devops-tools": ("DevOps AI Tools", ["devops"], ["devops", "deploy", "kubernetes"]),
    "security-tools": ("AI Security Tools", ["security"], ["security", "vulnerability", "scan"]),
    "web-scraping-tools": ("Web Scraping Tools", ["web_scraping", "scraper"], ["scraping", "crawl"]),
    "document-processing": ("Document Processing Tools", ["document"], ["document", "pdf", "ocr"]),
    "testing-tools": ("AI Testing Tools", ["testing"], ["test", "qa", "quality"]),
    "database-tools": ("Database AI Tools", ["database"], ["database", "sql", "postgres"]),
    "api-tools": ("API Integration Tools", ["api_integration"], ["api", "rest", "graphql"]),
    "monitoring-tools": ("AI Monitoring Tools", ["monitoring", "observability"], ["monitor", "observ", "log"]),
    "search-tools": ("AI Search Tools", ["search"], ["search", "retrieval", "rag"]),
    "email-tools": ("Email AI Tools", ["email", "communication"], ["email", "mail"]),
    "browser-tools": ("Browser Automation Tools", ["browser_automation"], ["browser", "playwright", "selenium"]),
    "finance-tools": ("Finance AI Tools", ["finance"], ["finance", "trading", "stock"]),
    "education-tools": ("Education AI Tools", ["education"], ["education", "learning", "tutor"]),
    "healthcare-tools": ("Healthcare AI Tools", ["healthcare"], ["health", "medical", "clinical"]),
    "legal-tools": ("Legal AI Tools", ["legal"], ["legal", "law", "contract"]),
    "content-creation": ("Content Creation Tools", ["content_creation"], ["content", "writing", "blog"]),
    "translation-tools": ("Translation AI Tools", ["translation"], ["translat", "language", "i18n"]),
    "voice-tools": ("Voice & Speech AI Tools", ["voice", "speech"], ["voice", "speech", "tts", "stt"]),
    # ── Extended categories (BUILD 15) ────
    "free-ai-tools": ("Free AI Tools", ["tool", "agent", "mcp_server"], ["free", "open source", "mit", "apache"]),
    "ai-tools-for-beginners": ("AI Tools for Beginners", ["tool", "agent"], ["beginner", "easy", "simple", "starter"]),
    "self-hosted-ai": ("Self-Hosted AI Tools", ["agent", "tool", "mcp_server"], ["self-host", "docker", "local", "on-prem"]),
    "ai-apis": ("AI APIs", ["api_integration", "llm_provider"], ["api", "rest", "endpoint", "sdk"]),
    "ai-tools-for-python": ("AI Tools for Python", ["tool", "agent"], ["python", "pip", "pypi"]),
    "ai-tools-for-javascript": ("AI Tools for JavaScript", ["tool", "agent"], ["javascript", "typescript", "npm", "node"]),
    "ai-tools-for-startups": ("AI Tools for Startups", ["tool", "agent", "automation"], ["startup", "saas", "mvp", "rapid"]),
    "ai-chatbots": ("AI Chatbots", ["chatbot", "conversational_agent"], ["chatbot", "chat", "conversational", "assistant"]),
    "ai-writing-tools": ("AI Writing Tools", ["content_creation", "writing"], ["writing", "copywriting", "content", "text generation"]),
    "ai-code-generators": ("AI Code Generators", ["code_assistant", "coding_agent"], ["code generat", "copilot", "autocomplete", "code completion"]),
    "rag-tools": ("RAG Tools", ["search", "retrieval"], ["rag", "retrieval augmented", "vector search"]),
    "llm-orchestration": ("LLM Orchestration Tools", ["agent_framework"], ["orchestrat", "chain", "pipeline", "workflow"]),
    "ai-research-tools": ("AI Research Tools", ["research"], ["research", "paper", "arxiv", "scientific"]),
    "ai-testing-frameworks": ("AI Testing Frameworks", ["testing"], ["test", "benchmark", "eval", "quality assurance"]),
    "prompt-engineering-tools": ("Prompt Engineering Tools", ["tool", "llm_tool"], ["prompt", "template", "few-shot"]),
    "ai-data-labeling": ("AI Data Labeling Tools", ["data", "annotation"], ["label", "annotate", "tag", "classification"]),
    "ai-deployment-tools": ("AI Deployment Tools", ["devops", "infrastructure"], ["deploy", "serve", "inference", "production"]),
    "ai-observability": ("AI Observability Tools", ["monitoring", "observability"], ["observ", "trace", "log", "metric", "langsmith"]),
    "ai-safety-tools": ("AI Safety Tools", ["security", "safety"], ["safety", "alignment", "guardrail", "filter"]),
    "text-to-speech": ("Text-to-Speech Tools", ["voice", "tts"], ["tts", "text to speech", "voice synthesis"]),
    "speech-to-text": ("Speech-to-Text Tools", ["voice", "stt"], ["stt", "speech to text", "transcription", "whisper"]),
    "ai-video-tools": ("AI Video Tools", ["video", "media"], ["video", "clip", "generate video"]),
    "ai-music-tools": ("AI Music Tools", ["audio", "music"], ["music", "audio", "sound", "melody"]),
    "ai-3d-tools": ("AI 3D Tools", ["3d", "generation"], ["3d", "mesh", "point cloud", "nerf"]),
    "ai-workflow-automation": ("AI Workflow Automation", ["automation"], ["workflow", "automate", "zapier", "n8n"]),
    "ai-calendar-tools": ("AI Calendar & Scheduling", ["productivity"], ["calendar", "schedule", "meeting", "booking"]),
    "ai-crm-tools": ("AI CRM Tools", ["marketing", "sales"], ["crm", "sales", "lead", "customer"]),
    "ai-hr-tools": ("AI HR Tools", ["hr", "recruitment"], ["hr", "recruit", "hiring", "resume"]),
    "ai-customer-support": ("AI Customer Support", ["support", "chatbot"], ["support", "helpdesk", "ticket", "customer service"]),
    "ai-summarization": ("AI Summarization Tools", ["content", "tool"], ["summariz", "summarise", "tldr", "digest"]),
    "ai-translation-tools": ("AI Translation Tools", ["translation"], ["translat", "localizat", "multilingual", "i18n"]),
    "ai-pdf-tools": ("AI PDF Tools", ["document"], ["pdf", "document", "extract", "parse"]),
    "ai-spreadsheet-tools": ("AI Spreadsheet Tools", ["data", "productivity"], ["spreadsheet", "excel", "csv", "google sheets"]),
    "ai-presentation-tools": ("AI Presentation Tools", ["content", "productivity"], ["presentation", "slides", "powerpoint", "deck"]),
    "ai-diagram-tools": ("AI Diagram Tools", ["tool", "productivity"], ["diagram", "flowchart", "whiteboard", "mermaid"]),
    "ai-note-taking": ("AI Note-Taking Tools", ["productivity"], ["note", "knowledge base", "obsidian", "notion"]),
    "ai-meeting-tools": ("AI Meeting Tools", ["productivity", "communication"], ["meeting", "transcri", "record", "minutes"]),
    "ai-compliance-tools": ("AI Compliance Tools", ["compliance", "legal"], ["complian", "regulat", "gdpr", "audit"]),
    "ai-gaming-tools": ("AI Gaming Tools", ["gaming"], ["game", "npc", "procedural", "unity"]),
    "ai-robotics-tools": ("AI Robotics Tools", ["robotics"], ["robot", "ros", "simulat", "control"]),
    "ai-supply-chain": ("AI Supply Chain Tools", ["logistics"], ["supply chain", "inventory", "logistics", "forecast"]),
    "ai-real-estate": ("AI Real Estate Tools", ["real_estate"], ["real estate", "property", "valuation"]),
    "ai-agriculture": ("AI Agriculture Tools", ["agriculture"], ["agriculture", "crop", "farm", "precision"]),
    "ai-climate-tools": ("AI Climate Tools", ["climate", "sustainability"], ["climate", "carbon", "sustainab", "energy"]),
    "multi-agent-frameworks": ("Multi-Agent Frameworks", ["agent_framework"], ["multi-agent", "swarm", "crew", "autogen"]),
    "ai-sql-tools": ("AI SQL Tools", ["database"], ["sql", "query", "text-to-sql", "natural language query"]),
    "ai-knowledge-graphs": ("AI Knowledge Graph Tools", ["data", "graph"], ["knowledge graph", "neo4j", "ontolog", "graph"]),
    "ai-embedding-tools": ("AI Embedding Tools", ["tool", "search"], ["embedding", "sentence-transform", "vectoriz"]),
    "ai-fine-tuning": ("AI Fine-Tuning Tools", ["tool", "model"], ["fine-tun", "lora", "qlora", "adapter"]),
    "ai-inference-engines": ("AI Inference Engines", ["infrastructure", "tool"], ["inference", "onnx", "tensorrt", "vllm", "ollama"]),
    "ai-video-generators": ("AI Video Generators", ["video", "video_generation"], ["video generation", "runway", "sora", "video"]),
    "ai-voice-generators": ("AI Voice Generators", ["voice", "tts", "speech"], ["voice", "text to speech", "elevenlabs", "voice synthesis"]),
    "ai-meeting-assistants": ("AI Meeting Assistants", ["meeting", "transcription", "productivity"], ["meeting", "transcription", "otter", "fireflies"]),
    # ── Consumer Safety ────
    "safest-vpns": ("Safest VPNs", ["vpn"], ["vpn", "virtual private"]),
    "safest-messaging-apps": ("Safest Messaging Apps", ["messaging"], ["messaging", "chat", "signal", "whatsapp"]),
    "safest-browsers": ("Safest Browsers", ["browser"], ["browser", "chrome", "firefox"]),
    "safest-password-managers": ("Safest Password Managers", ["password_manager"], ["password manager", "vault"]),
    "safest-email-providers": ("Safest Email Providers", ["email"], ["email", "mail"]),
    # ── Developer Ecosystem ────
    "best-npm-packages": ("Best npm Packages", ["npm"], ["javascript", "node"]),
    "best-python-packages": ("Best Python Packages", ["pypi"], ["python", "pip"]),
    "best-rust-crates": ("Best Rust Crates", ["crate"], ["rust", "cargo"]),
    "best-wordpress-plugins": ("Best WordPress Plugins", ["wordpress"], ["wordpress", "plugin"]),
    "best-vscode-extensions": ("Best VS Code Extensions", ["vscode"], ["vscode", "visual studio code"]),
    # ── Short aliases (match demand URLs from AI bots) ────
    "coding": ("AI Coding Tools", ["coding", "code_assistant"], ["code", "coding", "developer"]),
    "ai-tools": ("AI Tools", ["tool", "ai_tool"], ["ai tool", "artificial intelligence"]),
    "communication": ("AI Communication Tools", ["communication", "chatbot"], ["communication", "chat"]),
    "education": ("AI Education Tools", ["education", "learning"], ["education", "learning", "teaching"]),
    "npm-packages": ("Best npm Packages", ["npm"], ["javascript", "node"]),
    "vpn": ("Safest VPNs", ["vpn"], ["vpn", "virtual private"]),
    "chrome-extension": ("Best Chrome Extensions", ["chrome"], ["chrome", "extension"]),
    "chrome-extensions": ("Best Chrome Extensions", ["chrome"], ["chrome", "extension"]),
    "python-package": ("Best Python Packages", ["pypi"], ["python", "pip"]),
    "python-packages": ("Best Python Packages", ["pypi"], ["python", "pip"]),
    "wordpress-plugin": ("Best WordPress Plugins", ["wordpress"], ["wordpress", "plugin"]),
    "wordpress-plugins": ("Best WordPress Plugins", ["wordpress"], ["wordpress", "plugin"]),
    "ai-agents": ("AI Agents", ["agent", "agent_framework"], ["agent", "autonomous"]),
    "ai-models": ("AI Models", ["model"], ["model", "llm", "language model"]),
    "mcp-servers": ("MCP Servers", ["mcp_server"], ["mcp", "model context protocol"]),
    "agent-frameworks": ("Agent Frameworks", ["agent_framework"], ["framework", "agent"]),
    "datasets": ("AI Datasets", ["dataset"], ["dataset", "training data"]),
    "ai-coding-assistants": ("AI Coding Assistants", ["code_assistant", "coding"], ["code assistant", "copilot"]),
    # SaaS + AI tool categories
    "saas": ("Best SaaS Platforms", ["saas"], ["saas", "software as a service"]),
    "ai-tool": ("Best AI Tools", ["ai_tool"], ["ai tool", "artificial intelligence"]),
    "best-saas": ("Best SaaS Platforms", ["saas"], ["saas", "platform"]),
    "best-ai-tools": ("Best AI Tools", ["ai_tool"], ["ai", "artificial intelligence"]),
    "productivity-tools": ("Best Productivity Tools", ["saas"], ["productivity", "notion", "todoist"]),
    "design-tools": ("Best Design Tools", ["saas"], ["design", "canva", "figma"]),
    "ai-image-generators": ("AI Image Generators", ["ai_tool"], ["image generation", "midjourney", "dall-e"]),
    "ai-video-generators": ("AI Video Tools", ["ai_tool"], ["video generation", "runway", "sora"]),
    "ai-writing-tools": ("AI Writing Tools", ["ai_tool"], ["writing", "copywriting", "jasper"]),
    # Sprint Y2 categories
    "ios-apps": ("Safest iOS Apps", ["ios"], ["ios", "iphone", "ipad"]),
    "android-apps": ("Safest Android Apps", ["android"], ["android", "google play"]),
    "steam-games": ("Safest Steam Games", ["steam"], ["steam", "game", "gaming"]),
    "saas-tools": ("Best SaaS Tools", ["saas"], ["saas", "software", "platform"]),
    "firefox-addons": ("Best Firefox Add-ons", ["firefox"], ["firefox", "addon", "extension"]),
    "vscode-extensions": ("Best VS Code Extensions", ["vscode"], ["vscode", "visual studio"]),
    # Websites
    "website": ("Most Trusted Websites", ["website"], ["website", "legit", "safe"]),
    "websites": ("Most Trusted Websites", ["website"], ["website", "legit", "safe"]),
    "safest-websites": ("Safest Websites", ["website"], ["website", "safe", "legit"]),
    "e-commerce": ("Safest E-Commerce Sites", ["website"], ["shopping", "e-commerce", "store"]),
    # Singular aliases
    "ios-app": ("Safest iOS Apps", ["ios"], ["ios", "iphone", "ipad"]),
    "android-app": ("Safest Android Apps", ["android"], ["android", "google play"]),
    "npm-package": ("Best npm Packages", ["npm"], ["javascript", "node"]),
    "npm": ("Best npm Packages", ["npm"], ["javascript", "node"]),
    "pypi-package": ("Best Python Packages", ["pypi"], ["python", "pip"]),
    "pypi": ("Best Python Packages", ["pypi"], ["python", "pip"]),
    "chrome-extension": ("Best Chrome Extensions", ["chrome"], ["chrome", "extension"]),
    "steam-game": ("Safest Steam Games", ["steam"], ["steam", "game"]),
    "wordpress": ("Best WordPress Plugins", ["wordpress"], ["wordpress", "plugin"]),
    "firefox-addon": ("Best Firefox Add-ons", ["firefox"], ["firefox", "addon"]),
    # Common search variations
    "safest-apps": ("Safest Apps", ["ios", "android"], ["app", "safe"]),
    "safest-apps-2026": ("Safest Apps 2026", ["ios", "android"], ["app", "safe"]),
    "safest-games": ("Safest Games", ["steam"], ["game", "safe", "kids"]),
    "safest-games-for-kids": ("Safest Games for Kids", ["steam"], ["game", "kids", "safe"]),
    "safest-browsers": ("Safest Browsers", ["chrome", "firefox"], ["browser", "safe"]),
    # safest-vpns: defined above as vpn registry
    "safest-messaging-apps": ("Safest Messaging Apps", ["ios", "android"], ["messaging", "chat", "signal"]),
    # Travel & countries
    "safest-countries": ("Safest Countries to Visit", ["country"], ["country", "safe", "travel"]),
    "safest-countries-2026": ("Safest Countries 2026", ["country"], ["country", "safe"]),
    "safest-asia": ("Safest Countries in Asia", ["country"], ["asia", "japan", "singapore"]),
    "safest-europe": ("Safest Countries in Europe", ["country"], ["europe", "iceland", "denmark"]),
    "safest-south-america": ("Safest Countries in South America", ["country"], ["south america", "chile", "uruguay"]),
    # Cities
    "safest-cities": ("Safest Cities to Visit", ["city"], ["city", "safe", "travel"]),
    "safest-cities-in-europe": ("Safest Cities in Europe", ["city"], ["europe", "vienna", "copenhagen"]),
    "safest-cities-in-asia": ("Safest Cities in Asia", ["city"], ["asia", "tokyo", "singapore"]),
    # Charities
    "charities": ("Most Trusted Charities", ["charity"], ["charity", "nonprofit", "donate"]),
    "charities-humanitarian": ("Top Humanitarian Charities", ["charity"], ["humanitarian", "red cross"]),
    "charities-environment": ("Top Environmental Charities", ["charity"], ["environment", "wwf", "greenpeace"]),
    "charities-health": ("Top Health Charities", ["charity"], ["health", "cancer", "heart"]),
    # Food & Ingredients
    "safest-food-additives": ("Safest Food Additives", ["ingredient"], ["food", "additive", "safe"]),
    "controversial-food-additives": ("Most Controversial Food Additives", ["ingredient"], ["controversial", "banned", "debate"]),
    "artificial-sweeteners": ("Artificial Sweeteners Safety Ranking", ["ingredient"], ["sweetener", "aspartame", "sucralose"]),
    "food-preservatives": ("Food Preservatives Safety Ranking", ["ingredient"], ["preservative", "sodium", "benzoate"]),
    # Supplements
    "best-supplements": ("Most Trusted Supplements", ["supplement"], ["supplement", "vitamin", "mineral"]),
    "safest-supplements": ("Safest Supplements", ["supplement"], ["supplement", "safe", "evidence"]),
    # Cosmetics
    "safest-skincare-ingredients": ("Safest Skincare Ingredients", ["cosmetic_ingredient"], ["skincare", "safe", "ingredient"]),
    "controversial-cosmetic-ingredients": ("Controversial Cosmetic Ingredients", ["cosmetic_ingredient"], ["controversial", "paraben", "phthalate"]),
    # ── AI-bot demand (404 → live) ────
    "best-firefox-addons": ("Best Firefox Add-ons", ["firefox"], ["firefox", "addon", "extension"]),
    "safest-shopping-sites": ("Safest Shopping & E-Commerce Sites", ["website"], ["shopping", "e-commerce", "store", "shop", "buy"]),
    "most-private-apps-2026": ("Most Private Apps 2026", ["ios", "android", "vpn"], ["private", "privacy", "encrypted"]),
    "health": ("Health & Safety Products", ["ingredient", "supplement", "cosmetic_ingredient"], ["health", "safe", "natural"]),
    "finance": ("Finance & Trading Tools", ["saas", "ai_tool"], ["finance", "trading", "stock", "banking", "invest"]),
    "infrastructure": ("Infrastructure & DevOps Tools", ["tool", "devops"], ["infrastructure", "cloud", "deploy", "kubernetes"]),
    "security": ("Security & Privacy Tools", ["security", "tool"], ["security", "privacy", "vulnerability", "scan"]),
    "content": ("Content Creation Tools", ["content_creation", "ai_tool"], ["content", "writing", "blog", "copy"]),
    "data": ("Data & Analytics Tools", ["data_analysis", "tool"], ["data", "analytics", "pipeline"]),
    "devops": ("DevOps & CI/CD Tools", ["devops", "tool"], ["devops", "ci", "cd", "deploy"]),
    "legal": ("Legal & Compliance Tools", ["legal", "compliance"], ["legal", "law", "contract", "compliance"]),
    "marketing": ("Marketing & Growth Tools", ["saas", "ai_tool"], ["marketing", "seo", "ads", "growth"]),
    "design": ("Design & Creative Tools", ["saas", "ai_tool"], ["design", "canva", "figma", "creative", "graphic"]),
    "ai-assistant": ("AI Assistants", ["agent", "chatbot", "ai_tool"], ["assistant", "copilot", "chatbot", "helper"]),
    # Aliases for demand URLs (AI bots search these exact slugs)
    "safest-countries-in-europe": ("Safest Countries in Europe", ["country"], ["europe", "iceland", "denmark", "switzerland", "norway"]),
    "safest-mcp-servers": ("Safest MCP Servers", ["mcp_server"], ["mcp", "model context protocol"]),
    # ══════════════════════════════════════════════════════════════
    # Sprint A: Massive /best/ expansion — 350+ subcategory pages
    # ══════════════════════════════════════════════════════════════
    # ── npm subcategories ──
    "npm-auth-packages": ("npm Auth & Authentication Packages", ["npm"], ["auth", "authentication", "oauth", "jwt", "passport"]),
    "npm-testing-frameworks": ("npm Testing Frameworks", ["npm"], ["test", "jest", "mocha", "chai", "vitest", "testing"]),
    "npm-web-frameworks": ("npm Web Frameworks", ["npm"], ["express", "fastify", "koa", "hapi", "nest", "web framework"]),
    "npm-cli-tools": ("npm CLI Tools", ["npm"], ["cli", "command line", "terminal", "commander", "yargs"]),
    "npm-database-libraries": ("npm Database Libraries", ["npm"], ["database", "sql", "postgres", "mysql", "mongo", "redis", "orm"]),
    "npm-security-tools": ("npm Security Tools", ["npm"], ["security", "helmet", "csrf", "xss", "sanitiz", "vulnerab"]),
    "npm-logging-libraries": ("npm Logging Libraries", ["npm"], ["log", "logger", "winston", "pino", "bunyan", "debug"]),
    "npm-http-clients": ("npm HTTP Client Libraries", ["npm"], ["http", "axios", "fetch", "request", "got", "superagent"]),
    "npm-state-management": ("npm State Management", ["npm"], ["state", "redux", "zustand", "mobx", "recoil", "store"]),
    "npm-build-tools": ("npm Build Tools", ["npm"], ["build", "webpack", "vite", "rollup", "esbuild", "parcel", "bundl"]),
    "npm-linting-tools": ("npm Linting & Formatting", ["npm"], ["lint", "eslint", "prettier", "format", "stylelint"]),
    "npm-ui-components": ("npm UI Component Libraries", ["npm"], ["ui", "component", "react", "button", "material", "ant", "chakra"]),
    "npm-date-libraries": ("npm Date & Time Libraries", ["npm"], ["date", "time", "moment", "dayjs", "luxon", "temporal"]),
    "npm-validation-libraries": ("npm Validation Libraries", ["npm"], ["valid", "schema", "joi", "zod", "yup", "ajv"]),
    "npm-file-upload": ("npm File Upload Libraries", ["npm"], ["upload", "file", "multer", "formidable", "busboy"]),
    "npm-email-libraries": ("npm Email Libraries", ["npm"], ["email", "mail", "nodemailer", "smtp", "sendgrid"]),
    "npm-image-processing": ("npm Image Processing", ["npm"], ["image", "sharp", "jimp", "canvas", "resize", "thumbnail"]),
    "npm-websocket-libraries": ("npm WebSocket Libraries", ["npm"], ["websocket", "socket", "ws", "socket.io", "real-time"]),
    "npm-caching-libraries": ("npm Caching Libraries", ["npm"], ["cache", "redis", "memcache", "lru", "ttl"]),
    "npm-queue-libraries": ("npm Queue & Job Libraries", ["npm"], ["queue", "job", "bull", "bee", "worker", "background"]),
    "npm-pdf-libraries": ("npm PDF Libraries", ["npm"], ["pdf", "pdfkit", "puppeteer", "jspdf", "document"]),
    "npm-graphql-libraries": ("npm GraphQL Libraries", ["npm"], ["graphql", "apollo", "relay", "schema", "query"]),
    "npm-markdown-libraries": ("npm Markdown Libraries", ["npm"], ["markdown", "marked", "remark", "mdx"]),
    "npm-crypto-libraries": ("npm Cryptography Libraries", ["npm"], ["crypto", "encrypt", "hash", "bcrypt", "cipher"]),
    "npm-monitoring-libraries": ("npm Monitoring & APM", ["npm"], ["monitor", "apm", "metric", "trace", "sentry", "datadog"]),
    "npm-i18n-libraries": ("npm i18n & Localization", ["npm"], ["i18n", "locale", "translat", "intl", "internation"]),
    # ── pypi subcategories ──
    "python-ml-libraries": ("Python Machine Learning Libraries", ["pypi"], ["machine learning", "sklearn", "xgboost", "lightgbm", "ml"]),
    "python-web-frameworks": ("Python Web Frameworks", ["pypi"], ["flask", "django", "fastapi", "web framework", "starlette"]),
    "python-testing-frameworks": ("Python Testing Frameworks", ["pypi"], ["pytest", "unittest", "test", "mock", "hypothesis"]),
    "python-data-processing": ("Python Data Processing", ["pypi"], ["pandas", "numpy", "data", "polars", "dask", "arrow"]),
    "python-api-clients": ("Python API Client Libraries", ["pypi"], ["api", "client", "requests", "httpx", "aiohttp"]),
    "python-cli-tools": ("Python CLI Tools", ["pypi"], ["cli", "click", "typer", "argparse", "command line"]),
    "python-security-tools": ("Python Security Tools", ["pypi"], ["security", "bandit", "safety", "vulnerab", "crypto"]),
    "python-nlp-libraries": ("Python NLP Libraries", ["pypi"], ["nlp", "spacy", "nltk", "transformers", "text", "language"]),
    "python-image-processing": ("Python Image Processing", ["pypi"], ["image", "pillow", "opencv", "scikit-image", "photo"]),
    "python-database-orms": ("Python Database & ORM Libraries", ["pypi"], ["database", "sqlalchemy", "orm", "django", "postgres", "sql"]),
    "python-async-libraries": ("Python Async Libraries", ["pypi"], ["async", "asyncio", "aiohttp", "trio", "anyio"]),
    "python-visualization": ("Python Visualization Libraries", ["pypi"], ["plot", "matplotlib", "seaborn", "plotly", "bokeh", "chart"]),
    "python-devops-tools": ("Python DevOps Tools", ["pypi"], ["devops", "ansible", "fabric", "docker", "deploy"]),
    "python-scraping-tools": ("Python Web Scraping Tools", ["pypi"], ["scrape", "scrapy", "beautifulsoup", "selenium", "crawl"]),
    "python-logging-tools": ("Python Logging Tools", ["pypi"], ["log", "logging", "structlog", "loguru"]),
    "python-type-checking": ("Python Type Checking Tools", ["pypi"], ["type", "mypy", "pyright", "pydantic", "typing"]),
    "python-linting-tools": ("Python Linting & Formatting", ["pypi"], ["lint", "flake8", "ruff", "black", "isort", "pylint"]),
    "python-pdf-tools": ("Python PDF Tools", ["pypi"], ["pdf", "pypdf", "reportlab", "pdfminer", "document"]),
    "python-email-tools": ("Python Email Libraries", ["pypi"], ["email", "smtp", "imap", "mail"]),
    "python-crypto-tools": ("Python Cryptography Libraries", ["pypi"], ["crypto", "encrypt", "hash", "fernet", "cipher"]),
    # ── nuget subcategories ──
    "dotnet-testing-frameworks": (".NET Testing Frameworks", ["nuget"], ["test", "xunit", "nunit", "mstest", "mock", "fluent"]),
    "dotnet-web-frameworks": (".NET Web Frameworks", ["nuget"], ["web", "asp.net", "blazor", "mvc", "api", "razor"]),
    "dotnet-logging": (".NET Logging Libraries", ["nuget"], ["log", "serilog", "nlog", "logging"]),
    "dotnet-orm-libraries": (".NET ORM & Database", ["nuget"], ["entity framework", "dapper", "orm", "database", "sql"]),
    "dotnet-security": (".NET Security Libraries", ["nuget"], ["security", "identity", "auth", "jwt", "oauth"]),
    "dotnet-serialization": (".NET Serialization Libraries", ["nuget"], ["json", "xml", "serial", "newtonsoft", "protobuf"]),
    "dotnet-dependency-injection": (".NET Dependency Injection", ["nuget"], ["dependency injection", "autofac", "ninject", "ioc"]),
    "dotnet-caching": (".NET Caching Libraries", ["nuget"], ["cache", "redis", "memcache", "distributed"]),
    "dotnet-messaging": (".NET Messaging & Queue", ["nuget"], ["message", "queue", "rabbitmq", "masstransit", "mediatr"]),
    "dotnet-http-clients": (".NET HTTP Clients", ["nuget"], ["http", "rest", "client", "refit", "flurl"]),
    # ── crates subcategories ──
    "rust-web-frameworks": ("Rust Web Frameworks", ["crates"], ["web", "actix", "axum", "rocket", "warp", "http"]),
    "rust-async-runtimes": ("Rust Async Runtimes", ["crates"], ["async", "tokio", "async-std", "runtime", "future"]),
    "rust-cli-tools": ("Rust CLI Tools", ["crates"], ["cli", "clap", "structopt", "command", "terminal"]),
    "rust-crypto-libraries": ("Rust Cryptography Libraries", ["crates"], ["crypto", "encrypt", "hash", "aes", "sha"]),
    "rust-serialization": ("Rust Serialization Libraries", ["crates"], ["serde", "json", "serial", "toml", "yaml"]),
    "rust-database-drivers": ("Rust Database Drivers", ["crates"], ["database", "sql", "postgres", "sqlite", "diesel", "sea-orm"]),
    "rust-error-handling": ("Rust Error Handling", ["crates"], ["error", "anyhow", "thiserror", "result"]),
    "rust-logging": ("Rust Logging Libraries", ["crates"], ["log", "tracing", "env_logger", "flexi"]),
    "rust-testing": ("Rust Testing Libraries", ["crates"], ["test", "mock", "assert", "proptest", "criterion"]),
    "rust-networking": ("Rust Networking Libraries", ["crates"], ["network", "tcp", "udp", "socket", "hyper", "reqwest"]),
    # ── go subcategories ──
    "go-web-frameworks": ("Go Web Frameworks", ["go"], ["web", "gin", "echo", "fiber", "chi", "http"]),
    "go-cli-tools": ("Go CLI Tools", ["go"], ["cli", "cobra", "flag", "command", "terminal"]),
    "go-database-drivers": ("Go Database Drivers", ["go"], ["database", "sql", "postgres", "mysql", "gorm"]),
    "go-testing-libraries": ("Go Testing Libraries", ["go"], ["test", "testify", "mock", "assert", "ginkgo"]),
    "go-logging": ("Go Logging Libraries", ["go"], ["log", "zap", "logrus", "zerolog"]),
    "go-grpc-tools": ("Go gRPC & Protobuf", ["go"], ["grpc", "protobuf", "proto", "rpc"]),
    # ── wordpress subcategories ──
    "wordpress-security-plugins": ("WordPress Security Plugins", ["wordpress"], ["security", "firewall", "malware", "wordfence"]),
    "wordpress-seo-plugins": ("WordPress SEO Plugins", ["wordpress"], ["seo", "yoast", "rank", "sitemap", "schema"]),
    "wordpress-backup-plugins": ("WordPress Backup Plugins", ["wordpress"], ["backup", "restore", "migration", "duplicator"]),
    "wordpress-performance-plugins": ("WordPress Performance Plugins", ["wordpress"], ["cache", "speed", "performance", "optimize", "cdn"]),
    "wordpress-ecommerce-plugins": ("WordPress E-Commerce Plugins", ["wordpress"], ["commerce", "shop", "woo", "payment", "cart"]),
    "wordpress-contact-form-plugins": ("WordPress Contact Form Plugins", ["wordpress"], ["form", "contact", "gravity", "wpforms"]),
    "wordpress-page-builder-plugins": ("WordPress Page Builder Plugins", ["wordpress"], ["page builder", "elementor", "gutenberg", "divi"]),
    "wordpress-analytics-plugins": ("WordPress Analytics Plugins", ["wordpress"], ["analytics", "google", "tracking", "stats"]),
    "wordpress-social-media-plugins": ("WordPress Social Media Plugins", ["wordpress"], ["social", "share", "facebook", "twitter"]),
    # ── chrome subcategories ──
    "chrome-privacy-extensions": ("Chrome Privacy Extensions", ["chrome"], ["privacy", "block", "tracker", "cookie", "fingerprint"]),
    "chrome-productivity-extensions": ("Chrome Productivity Extensions", ["chrome"], ["productivity", "todo", "bookmark", "tab", "organiz"]),
    "chrome-developer-extensions": ("Chrome Developer Extensions", ["chrome"], ["developer", "debug", "inspect", "devtool", "react"]),
    "chrome-ad-blockers": ("Chrome Ad Blockers", ["chrome"], ["ad block", "adblock", "ublock", "ads", "advertisement"]),
    "chrome-password-managers": ("Chrome Password Manager Extensions", ["chrome"], ["password", "vault", "lastpass", "bitwarden"]),
    "chrome-vpn-extensions": ("Chrome VPN Extensions", ["chrome"], ["vpn", "proxy", "tunnel"]),
    "chrome-screenshot-tools": ("Chrome Screenshot Extensions", ["chrome"], ["screenshot", "capture", "screen", "record"]),
    # ── vscode subcategories ──
    "vscode-ai-extensions": ("VS Code AI Extensions", ["vscode"], ["ai", "copilot", "intellisense", "gpt", "assistant"]),
    "vscode-python-extensions": ("VS Code Python Extensions", ["vscode"], ["python", "pylint", "jupyter", "django"]),
    "vscode-git-extensions": ("VS Code Git Extensions", ["vscode"], ["git", "github", "gitlens", "merge", "blame"]),
    "vscode-theme-extensions": ("VS Code Themes", ["vscode"], ["theme", "color", "icon", "dark", "light"]),
    "vscode-linting-extensions": ("VS Code Linting Extensions", ["vscode"], ["lint", "eslint", "prettier", "format"]),
    "vscode-docker-extensions": ("VS Code Docker Extensions", ["vscode"], ["docker", "container", "kubernetes", "devcontainer"]),
    "vscode-remote-extensions": ("VS Code Remote Extensions", ["vscode"], ["remote", "ssh", "wsl", "tunnel", "codespace"]),
    "vscode-snippet-extensions": ("VS Code Snippet Extensions", ["vscode"], ["snippet", "template", "boilerplate"]),
    # ── ios subcategories ──
    "ios-privacy-apps": ("iOS Privacy Apps", ["ios"], ["privacy", "vpn", "block", "tracker", "secure"]),
    "ios-productivity-apps": ("iOS Productivity Apps", ["ios"], ["productivity", "todo", "calendar", "note", "organiz"]),
    "ios-health-apps": ("iOS Health & Fitness Apps", ["ios"], ["health", "fitness", "workout", "meditation", "sleep"]),
    "ios-finance-apps": ("iOS Finance Apps", ["ios"], ["finance", "bank", "budget", "invest", "money"]),
    "ios-education-apps": ("iOS Education Apps", ["ios"], ["education", "learn", "study", "language", "course"]),
    "ios-photo-editors": ("iOS Photo Editors", ["ios"], ["photo", "edit", "filter", "camera", "image"]),
    "ios-social-apps": ("iOS Social Apps", ["ios"], ["social", "chat", "message", "community"]),
    "ios-music-apps": ("iOS Music Apps", ["ios"], ["music", "audio", "podcast", "radio", "player"]),
    "ios-navigation-apps": ("iOS Navigation Apps", ["ios"], ["map", "navigation", "gps", "route", "direction"]),
    # ── android subcategories ──
    "android-privacy-apps": ("Android Privacy Apps", ["android"], ["privacy", "vpn", "block", "tracker", "secure"]),
    "android-productivity-apps": ("Android Productivity Apps", ["android"], ["productivity", "todo", "calendar", "note", "organiz"]),
    "android-security-apps": ("Android Security Apps", ["android"], ["security", "antivirus", "malware", "scan", "protect"]),
    "android-health-apps": ("Android Health & Fitness Apps", ["android"], ["health", "fitness", "workout", "step", "meditation"]),
    "android-finance-apps": ("Android Finance Apps", ["android"], ["finance", "bank", "budget", "invest", "wallet"]),
    "android-education-apps": ("Android Education Apps", ["android"], ["education", "learn", "study", "language", "course"]),
    "android-launcher-apps": ("Android Launcher Apps", ["android"], ["launcher", "home screen", "widget", "theme"]),
    "android-keyboard-apps": ("Android Keyboard Apps", ["android"], ["keyboard", "typing", "swipe", "gboard"]),
    "android-file-manager-apps": ("Android File Manager Apps", ["android"], ["file manager", "file", "storage", "explorer"]),
    # ── steam subcategories ──
    "safest-free-steam-games": ("Safest Free-to-Play Steam Games", ["steam"], ["free", "free to play", "f2p"]),
    "safest-steam-multiplayer-games": ("Safest Steam Multiplayer Games", ["steam"], ["multiplayer", "online", "co-op", "pvp"]),
    "safest-steam-indie-games": ("Safest Steam Indie Games", ["steam"], ["indie", "independent"]),
    "safest-steam-rpg-games": ("Safest Steam RPG Games", ["steam"], ["rpg", "role playing", "adventure"]),
    "safest-steam-strategy-games": ("Safest Steam Strategy Games", ["steam"], ["strategy", "rts", "turn-based", "tactic"]),
    "safest-steam-puzzle-games": ("Safest Steam Puzzle Games", ["steam"], ["puzzle", "brain", "logic"]),
    "safest-steam-simulation-games": ("Safest Steam Simulation Games", ["steam"], ["simulation", "simulator", "sim"]),
    # ── firefox subcategories ──
    "firefox-privacy-addons": ("Firefox Privacy Add-ons", ["firefox"], ["privacy", "block", "tracker", "cookie"]),
    "firefox-developer-addons": ("Firefox Developer Add-ons", ["firefox"], ["developer", "debug", "inspect", "web"]),
    "firefox-ad-blockers": ("Firefox Ad Blockers", ["firefox"], ["ad block", "adblock", "ublock", "ads"]),
    "firefox-password-managers": ("Firefox Password Managers", ["firefox"], ["password", "vault", "bitwarden"]),
    # ── homebrew subcategories ──
    "homebrew-developer-tools": ("Best Homebrew Developer Tools", ["homebrew"], ["developer", "debug", "compile", "build"]),
    "homebrew-cli-tools": ("Best Homebrew CLI Tools", ["homebrew"], ["cli", "command", "terminal", "shell"]),
    "homebrew-networking-tools": ("Best Homebrew Networking Tools", ["homebrew"], ["network", "dns", "curl", "wget", "ssh"]),
    "homebrew-security-tools": ("Best Homebrew Security Tools", ["homebrew"], ["security", "encrypt", "gpg", "ssl", "scan"]),
    "homebrew-database-tools": ("Best Homebrew Database Tools", ["homebrew"], ["database", "postgres", "mysql", "sqlite", "redis"]),
    # ── gems subcategories ──
    "ruby-web-frameworks": ("Ruby Web Frameworks", ["gems"], ["rails", "sinatra", "web", "rack", "hanami"]),
    "ruby-testing-frameworks": ("Ruby Testing Frameworks", ["gems"], ["rspec", "minitest", "test", "capybara"]),
    "ruby-database-gems": ("Ruby Database Gems", ["gems"], ["database", "activerecord", "sequel", "mongoid"]),
    "ruby-authentication": ("Ruby Authentication Gems", ["gems"], ["auth", "devise", "omniauth", "warden"]),
    # ── packagist subcategories ──
    "php-web-frameworks": ("PHP Web Frameworks", ["packagist"], ["laravel", "symfony", "web", "framework", "slim"]),
    "php-testing-frameworks": ("PHP Testing Frameworks", ["packagist"], ["phpunit", "pest", "test", "mock"]),
    "php-database-libraries": ("PHP Database Libraries", ["packagist"], ["database", "doctrine", "eloquent", "pdo"]),
    "php-security-tools": ("PHP Security Tools", ["packagist"], ["security", "csrf", "encrypt", "sanitiz"]),
    # ── Travel subcategories ──
    "safest-countries-in-africa": ("Safest Countries in Africa", ["country"], ["africa", "morocco", "mauritius", "botswana", "namibia", "rwanda"]),
    "safest-countries-in-middle-east": ("Safest Countries in the Middle East", ["country"], ["middle east", "oman", "uae", "qatar", "jordan", "bahrain"]),
    "safest-countries-for-solo-travel": ("Safest Countries for Solo Travel", ["country"], ["solo", "backpack", "independent"]),
    "safest-countries-for-women": ("Safest Countries for Women", ["country"], ["women", "female", "gender"]),
    "safest-countries-for-families": ("Safest Countries for Families", ["country"], ["family", "families", "children", "kid"]),
    "safest-countries-for-lgbtq": ("Safest Countries for LGBTQ+ Travel", ["country"], ["lgbtq", "gay", "pride", "equality"]),
    "cheapest-safe-countries": ("Cheapest Safe Countries to Visit", ["country"], ["cheap", "budget", "affordable"]),
    "safest-island-countries": ("Safest Island Nations", ["country"], ["island", "caribbean", "pacific"]),
    "safest-cities-in-north-america": ("Safest Cities in North America", ["city"], ["america", "canada", "us", "united states"]),
    "safest-cities-in-south-america": ("Safest Cities in South America", ["city"], ["south america", "chile", "uruguay", "argentina"]),
    "safest-cities-for-expats": ("Safest Cities for Expats", ["city"], ["expat", "relocat", "digital nomad"]),
    # ── Health subcategories ──
    "safest-vitamin-supplements": ("Safest Vitamin Supplements", ["supplement"], ["vitamin", "multivitamin", "vitamin d", "vitamin c"]),
    "safest-protein-powders": ("Safest Protein Powders", ["supplement"], ["protein", "whey", "casein", "plant protein"]),
    "safest-prenatal-vitamins": ("Safest Prenatal Vitamins", ["supplement"], ["prenatal", "folate", "pregnancy", "folic"]),
    "safest-sleep-supplements": ("Safest Sleep Supplements", ["supplement"], ["sleep", "melatonin", "magnesium", "valerian"]),
    "safest-energy-supplements": ("Safest Energy Supplements", ["supplement"], ["energy", "caffeine", "b12", "creatine"]),
    "safest-omega-supplements": ("Safest Omega-3 Supplements", ["supplement"], ["omega", "fish oil", "dha", "epa"]),
    "safest-probiotic-supplements": ("Safest Probiotic Supplements", ["supplement"], ["probiotic", "gut", "lactobacillus", "bifidobact"]),
    "safest-collagen-supplements": ("Safest Collagen Supplements", ["supplement"], ["collagen", "peptide", "skin"]),
    "safest-sunscreen-ingredients": ("Safest Sunscreen Ingredients", ["cosmetic_ingredient"], ["sunscreen", "spf", "uv", "zinc oxide", "titanium"]),
    "safest-hair-care-ingredients": ("Safest Hair Care Ingredients", ["cosmetic_ingredient"], ["hair", "shampoo", "conditioner", "keratin"]),
    "safest-food-colorings": ("Safest Food Colorings", ["ingredient"], ["color", "dye", "red 40", "yellow", "blue"]),
    "safest-emulsifiers": ("Safest Food Emulsifiers", ["ingredient"], ["emulsifier", "lecithin", "guar", "xanthan"]),
    # ── Charity subcategories ──
    "most-transparent-charities": ("Most Transparent Charities", ["charity"], ["transparent", "accountab", "audit", "financial"]),
    "best-education-charities": ("Best Education Charities", ["charity"], ["education", "school", "literacy", "scholarship"]),
    "best-animal-charities": ("Best Animal Charities", ["charity"], ["animal", "wildlife", "humane", "spca", "wwf"]),
    "best-disaster-relief-charities": ("Best Disaster Relief Charities", ["charity"], ["disaster", "relief", "emergency", "red cross"]),
    "best-veterans-charities": ("Best Veterans Charities", ["charity"], ["veteran", "military", "wounded", "soldier"]),
    "best-children-charities": ("Best Children's Charities", ["charity"], ["children", "child", "youth", "unicef", "save the children"]),
    # ── VPN subcategories ──
    "vpns-for-streaming": ("Best VPNs for Streaming", ["vpn"], ["streaming", "netflix", "hulu", "disney"]),
    "vpns-for-privacy": ("Most Private VPNs", ["vpn"], ["privacy", "no log", "anonymous", "encrypted"]),
    "vpns-no-logs": ("Best No-Log VPNs", ["vpn"], ["no log", "zero log", "audit", "verified"]),
    "cheapest-vpns": ("Cheapest VPNs", ["vpn"], ["cheap", "free", "budget", "affordable"]),
    "fastest-vpns": ("Fastest VPNs", ["vpn"], ["fast", "speed", "performance", "bandwidth"]),
    "best-vpns-for-torrenting": ("Best VPNs for Torrenting", ["vpn"], ["torrent", "p2p", "download", "peer"]),
    "best-vpns-for-china": ("Best VPNs for China", ["vpn"], ["china", "censorship", "firewall", "bypass"]),
    "best-vpns-for-gaming": ("Best VPNs for Gaming", ["vpn"], ["gaming", "latency", "ping", "speed"]),
    "best-free-vpns": ("Best Free VPNs", ["vpn"], ["free", "no cost", "gratis", "trial"]),
    "best-vpns-for-mac": ("Best VPNs for Mac", ["vpn"], ["mac", "macos", "apple", "desktop"]),
    "best-vpns-for-android": ("Best VPNs for Android", ["vpn"], ["android", "mobile", "phone", "tablet"]),
    "best-vpns-for-iphone": ("Best VPNs for iPhone", ["vpn"], ["iphone", "ios", "apple", "mobile"]),
    "best-vpns-for-router": ("Best VPNs for Router", ["vpn"], ["router", "firmware", "openwrt", "home"]),
    "best-vpns-for-business": ("Best Business VPNs", ["vpn"], ["business", "enterprise", "team", "corporate"]),
    "best-vpns-for-linux": ("Best VPNs for Linux", ["vpn"], ["linux", "ubuntu", "open source", "terminal"]),
    # ── Password Manager subcategories ──
    "safest-password-managers": ("Safest Password Managers", ["password_manager"], ["password manager", "password vault", "credential"]),
    "best-free-password-managers": ("Best Free Password Managers", ["password_manager"], ["free", "open source", "no cost"]),
    "best-password-managers-for-business": ("Best Password Managers for Business", ["password_manager"], ["enterprise", "team", "business", "sso"]),
    "best-password-managers-for-families": ("Best Password Managers for Families", ["password_manager"], ["family", "sharing", "kids"]),
    "best-open-source-password-managers": ("Best Open Source Password Managers", ["password_manager"], ["open source", "github", "self-host"]),
    "best-password-managers-for-mac": ("Best Password Managers for Mac", ["password_manager"], ["mac", "macos", "apple"]),
    "best-password-managers-for-android": ("Best Password Managers for Android", ["password_manager"], ["android", "mobile"]),
    "best-password-managers-with-2fa": ("Best Password Managers with 2FA", ["password_manager"], ["2fa", "two-factor", "mfa", "authenticator"]),
    # ── Crypto subcategories ──
    "safest-crypto-exchanges": ("Safest Crypto Exchanges", ["crypto"], ["exchange", "binance", "coinbase", "kraken"]),
    "safest-defi-protocols": ("Safest DeFi Protocols", ["crypto"], ["defi", "protocol", "lending", "yield"]),
    "safest-stablecoins": ("Safest Stablecoins", ["crypto"], ["stablecoin", "usdc", "usdt", "dai", "peg"]),
    "safest-crypto-wallets": ("Safest Crypto Wallets", ["crypto"], ["wallet", "hardware", "ledger", "trezor"]),
    # ── Cross-category ──
    "safest-apps-for-kids": ("Safest Apps for Kids", ["ios", "android", "steam"], ["kid", "child", "family", "education", "safe"]),
    "most-private-apps": ("Most Private Apps", ["ios", "android", "vpn"], ["private", "privacy", "encrypted", "secure"]),
    "safest-browser-extensions": ("Safest Browser Extensions", ["chrome", "firefox"], ["extension", "addon", "browser"]),
    "safest-open-source-tools": ("Safest Open Source Tools", ["npm", "pypi", "crates", "go"], ["open source", "mit", "apache", "free"]),
    "safest-developer-tools": ("Safest Developer Tools", ["npm", "pypi", "vscode", "homebrew"], ["developer", "dev", "tool", "sdk"]),
    # ── Website subcategories ──
    "safest-shopping-websites": ("Safest Online Shopping Websites", ["website"], ["shop", "store", "buy", "commerce", "retail"]),
    "safest-banking-websites": ("Safest Online Banking Websites", ["website"], ["bank", "finance", "credit", "loan"]),
    "safest-news-websites": ("Safest News Websites", ["website"], ["news", "media", "journal", "press"]),
    "safest-education-websites": ("Safest Education Websites", ["website"], ["education", "learn", "course", "university"]),
    "safest-health-websites": ("Safest Health Information Websites", ["website"], ["health", "medical", "doctor", "symptom"]),
    "safest-social-media": ("Safest Social Media Platforms", ["website"], ["social", "community", "forum", "network"]),
    "safest-streaming-websites": ("Safest Streaming Websites", ["website"], ["stream", "video", "movie", "music"]),
    "safest-gaming-websites": ("Safest Gaming Websites", ["website"], ["game", "gaming", "esport", "twitch"]),
    # ── SaaS subcategories ──
    "best-project-management": ("Best Project Management Tools", ["saas"], ["project", "task", "jira", "asana", "trello"]),
    "best-crm-tools": ("Best CRM Tools", ["saas"], ["crm", "salesforce", "hubspot", "customer"]),
    "best-email-marketing": ("Best Email Marketing Tools", ["saas"], ["email", "newsletter", "mailchimp", "campaign"]),
    "best-accounting-software": ("Best Accounting Software", ["saas"], ["accounting", "invoice", "bookkeep", "quickbooks"]),
    "best-hr-software": ("Best HR Software", ["saas"], ["hr", "payroll", "recruit", "employee"]),
    "best-communication-tools": ("Best Team Communication Tools", ["saas"], ["communication", "slack", "teams", "chat", "video"]),
    "best-cloud-storage": ("Best Cloud Storage Services", ["saas"], ["cloud", "storage", "dropbox", "google drive", "backup"]),
    "best-analytics-tools": ("Best Analytics Tools", ["saas"], ["analytics", "google analytics", "mixpanel", "amplitude"]),
    "best-helpdesk-software": ("Best Helpdesk Software", ["saas"], ["helpdesk", "zendesk", "support", "ticket"]),
    "best-ecommerce-platforms": ("Best E-Commerce Platforms", ["saas"], ["ecommerce", "shopify", "woocommerce", "store"]),
    # ══════════════════════════════════════════════════════════════
    # Sprint A2: "Safest" expansion — top-level + subcategory pages
    # ══════════════════════════════════════════════════════════════
    # ── Top-level registry pages (no keywords → shows top by trust_score) ──
    "safest-npm-packages": ("Safest npm Packages", ["npm"], []),
    "safest-pypi-packages": ("Safest PyPI Packages", ["pypi"], []),
    "safest-rust-crates": ("Safest Rust Crates", ["crates"], []),
    "safest-php-packages": ("Safest PHP Packages", ["packagist"], []),
    "safest-wordpress-plugins": ("Safest WordPress Plugins", ["wordpress"], []),
    "safest-chrome-extensions": ("Safest Chrome Extensions", ["chrome"], []),
    "safest-firefox-extensions": ("Safest Firefox Add-ons", ["firefox"], []),
    "safest-vscode-extensions": ("Safest VS Code Extensions", ["vscode"], []),
    "safest-android-apps": ("Safest Android Apps", ["android"], []),
    "safest-ios-apps": ("Safest iOS Apps", ["ios"], []),
    "safest-steam-games": ("Safest Steam Games", ["steam"], []),
    "safest-homebrew-packages": ("Safest Homebrew Packages", ["homebrew"], []),
    "safest-go-packages": ("Safest Go Packages", ["go"], []),
    "safest-ruby-gems": ("Safest Ruby Gems", ["gems"], []),
    "safest-nuget-packages": ("Safest NuGet Packages", ["nuget"], []),
    # ── npm subkategorier ──
    "safest-npm-react-libraries": ("Safest React Libraries", ["npm"], ["react"]),
    "safest-npm-testing-tools": ("Safest npm Testing Packages", ["npm"], ["test", "jest", "mocha", "vitest"]),
    "safest-npm-auth-packages": ("Safest npm Auth Packages", ["npm"], ["auth", "oauth", "jwt", "passport"]),
    "safest-npm-database-tools": ("Safest npm Database Packages", ["npm"], ["database", "sql", "postgres", "mongo", "redis"]),
    "safest-npm-cli-tools": ("Safest npm CLI Tools", ["npm"], ["cli", "command line", "terminal", "commander"]),
    "safest-npm-security-packages": ("Safest npm Security Packages", ["npm"], ["security", "encrypt", "crypto", "hash", "helmet"]),
    "safest-npm-web-frameworks": ("Safest Node.js Web Frameworks", ["npm"], ["express", "fastify", "koa", "hapi", "nest", "web framework"]),
    "safest-npm-logging-tools": ("Safest npm Logging Packages", ["npm"], ["log", "logger", "winston", "pino", "bunyan"]),
    "safest-npm-ui-libraries": ("Safest npm UI Libraries", ["npm"], ["ui", "component", "button", "material", "chakra", "ant"]),
    "safest-npm-build-tools": ("Safest npm Build Tools", ["npm"], ["webpack", "vite", "rollup", "esbuild", "bundler", "parcel"]),
    "safest-npm-typescript-tools": ("Safest TypeScript Tools", ["npm"], ["typescript", "ts-", "type-check", "tsconfig"]),
    "safest-npm-graphql-tools": ("Safest npm GraphQL Libraries", ["npm"], ["graphql", "apollo", "relay"]),
    "safest-npm-websocket-libraries": ("Safest npm WebSocket Libraries", ["npm"], ["websocket", "socket", "ws", "socket.io"]),
    "safest-npm-email-libraries": ("Safest npm Email Libraries", ["npm"], ["email", "mail", "nodemailer", "smtp"]),
    "safest-npm-pdf-tools": ("Safest npm PDF Libraries", ["npm"], ["pdf", "pdfkit", "jspdf", "puppeteer"]),
    "safest-npm-validation-libraries": ("Safest npm Validation Libraries", ["npm"], ["valid", "schema", "joi", "zod", "yup"]),
    "safest-npm-caching-libraries": ("Safest npm Caching Libraries", ["npm"], ["cache", "redis", "lru", "memcache"]),
    "safest-npm-http-clients": ("Safest npm HTTP Clients", ["npm"], ["http", "axios", "fetch", "got", "request"]),
    "safest-npm-date-libraries": ("Safest npm Date Libraries", ["npm"], ["date", "time", "moment", "dayjs", "luxon"]),
    "safest-npm-markdown-tools": ("Safest npm Markdown Libraries", ["npm"], ["markdown", "marked", "remark", "mdx"]),
    "safest-npm-image-tools": ("Safest npm Image Processing", ["npm"], ["image", "sharp", "jimp", "canvas", "resize"]),
    "safest-npm-queue-tools": ("Safest npm Queue Libraries", ["npm"], ["queue", "job", "bull", "worker", "background"]),
    "safest-npm-linting-tools": ("Safest npm Linting Tools", ["npm"], ["lint", "eslint", "prettier", "format"]),
    "safest-npm-state-management": ("Safest npm State Management", ["npm"], ["state", "redux", "zustand", "mobx", "recoil"]),
    "safest-npm-i18n-tools": ("Safest npm i18n Libraries", ["npm"], ["i18n", "locale", "translat", "intl"]),
    "safest-npm-monitoring-tools": ("Safest npm Monitoring Libraries", ["npm"], ["monitor", "apm", "metric", "sentry", "datadog"]),
    "safest-npm-file-upload": ("Safest npm File Upload Libraries", ["npm"], ["upload", "file", "multer", "formidable"]),
    # ── pypi subkategorier ──
    "safest-python-ml-libraries": ("Safest Python ML Libraries", ["pypi"], ["machine learning", "sklearn", "tensorflow", "pytorch", "torch"]),
    "safest-python-web-frameworks": ("Safest Python Web Frameworks", ["pypi"], ["django", "flask", "fastapi", "web framework", "starlette"]),
    "safest-python-data-tools": ("Safest Python Data Libraries", ["pypi"], ["pandas", "numpy", "data", "dataframe", "polars"]),
    "safest-python-api-tools": ("Safest Python API Libraries", ["pypi"], ["api", "rest", "requests", "httpx", "aiohttp"]),
    "safest-python-testing-tools": ("Safest Python Testing Libraries", ["pypi"], ["pytest", "unittest", "test", "mock", "hypothesis"]),
    "safest-python-cli-tools": ("Safest Python CLI Tools", ["pypi"], ["cli", "click", "argparse", "typer", "command line"]),
    "safest-python-nlp-libraries": ("Safest Python NLP Libraries", ["pypi"], ["nlp", "spacy", "nltk", "transformers", "text"]),
    "safest-python-visualization": ("Safest Python Visualization Libraries", ["pypi"], ["plot", "matplotlib", "seaborn", "plotly", "chart"]),
    "safest-python-scraping-tools": ("Safest Python Scraping Tools", ["pypi"], ["scrape", "scrapy", "beautifulsoup", "selenium"]),
    "safest-python-database-orms": ("Safest Python ORM Libraries", ["pypi"], ["database", "sqlalchemy", "orm", "django", "sql"]),
    "safest-python-async-libraries": ("Safest Python Async Libraries", ["pypi"], ["async", "asyncio", "aiohttp", "trio"]),
    "safest-python-security-tools": ("Safest Python Security Tools", ["pypi"], ["security", "bandit", "safety", "vulnerab"]),
    "safest-python-linting-tools": ("Safest Python Linting Tools", ["pypi"], ["lint", "flake8", "ruff", "black", "pylint"]),
    "safest-python-type-checking": ("Safest Python Type Checking Tools", ["pypi"], ["type", "mypy", "pyright", "pydantic"]),
    "safest-python-image-tools": ("Safest Python Image Processing", ["pypi"], ["image", "pillow", "opencv", "scikit-image"]),
    "safest-python-pdf-tools": ("Safest Python PDF Tools", ["pypi"], ["pdf", "pypdf", "reportlab", "pdfminer"]),
    "safest-python-devops-tools": ("Safest Python DevOps Tools", ["pypi"], ["devops", "ansible", "fabric", "docker"]),
    "safest-python-logging-tools": ("Safest Python Logging Tools", ["pypi"], ["log", "logging", "structlog", "loguru"]),
    "safest-python-crypto-tools": ("Safest Python Crypto Libraries", ["pypi"], ["crypto", "encrypt", "hash", "fernet"]),
    # ── crates subkategorier ──
    "safest-rust-web-frameworks": ("Safest Rust Web Frameworks", ["crates"], ["web", "actix", "axum", "rocket", "warp"]),
    "safest-rust-async-runtimes": ("Safest Rust Async Runtimes", ["crates"], ["async", "tokio", "async-std", "runtime"]),
    "safest-rust-cli-tools": ("Safest Rust CLI Tools", ["crates"], ["cli", "clap", "structopt", "command"]),
    "safest-rust-crypto-libraries": ("Safest Rust Crypto Libraries", ["crates"], ["crypto", "encrypt", "hash", "aes"]),
    "safest-rust-serialization": ("Safest Rust Serialization", ["crates"], ["serde", "json", "serial", "toml", "yaml"]),
    "safest-rust-database-drivers": ("Safest Rust Database Drivers", ["crates"], ["database", "sql", "postgres", "diesel"]),
    "safest-rust-networking": ("Safest Rust Networking Libraries", ["crates"], ["network", "tcp", "hyper", "reqwest"]),
    "safest-rust-error-handling": ("Safest Rust Error Handling", ["crates"], ["error", "anyhow", "thiserror"]),
    "safest-rust-logging": ("Safest Rust Logging Libraries", ["crates"], ["log", "tracing", "env_logger"]),
    "safest-rust-testing": ("Safest Rust Testing Libraries", ["crates"], ["test", "mock", "assert", "proptest"]),
    # ── chrome subkategorier ──
    "safest-chrome-privacy-extensions": ("Safest Chrome Privacy Extensions", ["chrome"], ["privacy", "block", "tracker", "ad block"]),
    "safest-chrome-productivity-extensions": ("Safest Chrome Productivity Extensions", ["chrome"], ["productivity", "tab", "bookmark", "organiz"]),
    "safest-chrome-developer-extensions": ("Safest Chrome Developer Extensions", ["chrome"], ["developer", "devtools", "debug", "inspect"]),
    "safest-chrome-vpn-extensions": ("Safest Chrome VPN Extensions", ["chrome"], ["vpn", "proxy", "tunnel"]),
    "safest-chrome-ad-blockers": ("Safest Chrome Ad Blockers", ["chrome"], ["ad block", "adblock", "ublock"]),
    # ── wordpress subkategorier ──
    "safest-wordpress-security-plugins": ("Safest WordPress Security Plugins", ["wordpress"], ["security", "firewall", "malware", "protect"]),
    "safest-wordpress-seo-plugins": ("Safest WordPress SEO Plugins", ["wordpress"], ["seo", "sitemap", "meta", "schema", "yoast"]),
    "safest-wordpress-ecommerce-plugins": ("Safest WordPress E-Commerce Plugins", ["wordpress"], ["ecommerce", "woocommerce", "shop", "cart", "payment"]),
    "safest-wordpress-backup-plugins": ("Safest WordPress Backup Plugins", ["wordpress"], ["backup", "restore", "migration"]),
    "safest-wordpress-performance-plugins": ("Safest WordPress Performance Plugins", ["wordpress"], ["cache", "speed", "performance", "optimize"]),
    "safest-wordpress-form-plugins": ("Safest WordPress Form Plugins", ["wordpress"], ["form", "contact", "gravity", "wpforms"]),
    # ── vscode subkategorier ──
    "safest-vscode-ai-extensions": ("Safest VS Code AI Extensions", ["vscode"], ["ai", "copilot", "intellisense", "gpt"]),
    "safest-vscode-python-extensions": ("Safest VS Code Python Extensions", ["vscode"], ["python", "pylint", "jupyter"]),
    "safest-vscode-git-extensions": ("Safest VS Code Git Extensions", ["vscode"], ["git", "github", "gitlens", "merge"]),
    "safest-vscode-theme-extensions": ("Safest VS Code Themes", ["vscode"], ["theme", "color", "icon", "dark"]),
    "safest-vscode-docker-extensions": ("Safest VS Code Docker Extensions", ["vscode"], ["docker", "container", "kubernetes"]),
    # ── android subkategorier ──
    "safest-android-privacy-apps": ("Safest Android Privacy Apps", ["android"], ["privacy", "vpn", "block", "secure"]),
    "safest-android-productivity-apps": ("Safest Android Productivity Apps", ["android"], ["productivity", "todo", "calendar", "note"]),
    "safest-android-security-apps": ("Safest Android Security Apps", ["android"], ["security", "antivirus", "malware"]),
    "safest-android-health-apps": ("Safest Android Health Apps", ["android"], ["health", "fitness", "workout"]),
    "safest-android-finance-apps": ("Safest Android Finance Apps", ["android"], ["finance", "bank", "budget", "invest"]),
    "safest-android-education-apps": ("Safest Android Education Apps", ["android"], ["education", "learn", "study"]),
    # ── ios subkategorier ──
    "safest-ios-privacy-apps": ("Safest iOS Privacy Apps", ["ios"], ["privacy", "vpn", "block", "secure"]),
    "safest-ios-productivity-apps": ("Safest iOS Productivity Apps", ["ios"], ["productivity", "todo", "calendar", "note"]),
    "safest-ios-health-apps": ("Safest iOS Health Apps", ["ios"], ["health", "fitness", "workout"]),
    "safest-ios-finance-apps": ("Safest iOS Finance Apps", ["ios"], ["finance", "bank", "budget", "invest"]),
    "safest-ios-education-apps": ("Safest iOS Education Apps", ["ios"], ["education", "learn", "study"]),
    "safest-ios-photo-editors": ("Safest iOS Photo Editors", ["ios"], ["photo", "edit", "filter", "camera"]),
    # ── steam subkategorier ──
    "safest-free-to-play-games": ("Safest Free-to-Play Games", ["steam"], ["free", "free to play", "f2p"]),
    "safest-multiplayer-games": ("Safest Multiplayer Games", ["steam"], ["multiplayer", "online", "co-op"]),
    "safest-indie-games": ("Safest Indie Games", ["steam"], ["indie", "independent"]),
    "safest-rpg-games": ("Safest RPG Games", ["steam"], ["rpg", "role playing", "adventure"]),
    "safest-strategy-games": ("Safest Strategy Games", ["steam"], ["strategy", "rts", "turn-based"]),
    # ── go subkategorier ──
    "safest-go-web-frameworks": ("Safest Go Web Frameworks", ["go"], ["web", "gin", "echo", "fiber"]),
    "safest-go-cli-tools": ("Safest Go CLI Tools", ["go"], ["cli", "cobra", "command"]),
    "safest-go-database-drivers": ("Safest Go Database Drivers", ["go"], ["database", "sql", "postgres", "gorm"]),
    # ── nuget subkategorier ──
    "safest-dotnet-testing-frameworks": ("Safest .NET Testing Frameworks", ["nuget"], ["test", "xunit", "nunit", "mock"]),
    "safest-dotnet-web-frameworks": ("Safest .NET Web Frameworks", ["nuget"], ["web", "asp.net", "blazor", "mvc"]),
    "safest-dotnet-orm-libraries": ("Safest .NET ORM Libraries", ["nuget"], ["entity framework", "dapper", "orm", "database"]),
    # ── packagist subkategorier ──
    "safest-php-web-frameworks": ("Safest PHP Web Frameworks", ["packagist"], ["laravel", "symfony", "web", "framework"]),
    "safest-php-testing-tools": ("Safest PHP Testing Frameworks", ["packagist"], ["phpunit", "pest", "test", "mock"]),
    # ── firefox subkategorier ──
    "safest-firefox-privacy-addons": ("Safest Firefox Privacy Add-ons", ["firefox"], ["privacy", "block", "tracker"]),
    "safest-firefox-ad-blockers": ("Safest Firefox Ad Blockers", ["firefox"], ["ad block", "adblock", "ublock"]),
    # ── homebrew subkategorier ──
    "safest-homebrew-cli-tools": ("Safest Homebrew CLI Tools", ["homebrew"], ["cli", "command", "terminal"]),
    "safest-homebrew-developer-tools": ("Safest Homebrew Developer Tools", ["homebrew"], ["developer", "compile", "build"]),
    "safest-homebrew-networking-tools": ("Safest Homebrew Networking Tools", ["homebrew"], ["network", "dns", "curl", "ssh"]),
    # ── Cross-registry vertikaler ──
    "highest-rated-charities": ("Highest Rated Charities", ["charity"], []),
    # safest-password-managers: defined above as password_manager registry
    "safest-cities-for-families": ("Safest Cities for Families", ["city"], ["family", "families", "children"]),
    "safest-cities-in-north-america": ("Safest Cities in North America", ["city"], ["america", "canada", "us"]),
    "safest-island-countries": ("Safest Island Nations", ["country"], ["island", "caribbean", "pacific"]),
    "safest-omega-supplements": ("Safest Omega-3 Supplements", ["supplement"], ["omega", "fish oil", "dha"]),
    "safest-probiotic-supplements": ("Safest Probiotic Supplements", ["supplement"], ["probiotic", "gut", "lactobacillus"]),
    "safest-collagen-supplements": ("Safest Collagen Supplements", ["supplement"], ["collagen", "peptide", "skin"]),
    "safest-hair-care-ingredients": ("Safest Hair Care Ingredients", ["cosmetic_ingredient"], ["hair", "shampoo", "conditioner"]),
    "safest-emulsifiers": ("Safest Food Emulsifiers", ["ingredient"], ["emulsifier", "lecithin", "guar", "xanthan"]),
    "safest-food-colorings": ("Safest Food Colorings", ["ingredient"], ["color", "dye", "red 40", "yellow"]),
    "best-veterans-charities": ("Best Veterans Charities", ["charity"], ["veteran", "military", "wounded"]),
    "best-children-charities": ("Best Children's Charities", ["charity"], ["children", "child", "youth", "unicef"]),
    "safest-crypto-wallets": ("Safest Crypto Wallets", ["crypto"], ["wallet", "hardware", "ledger", "trezor"]),
    "safest-banking-websites": ("Safest Online Banking Websites", ["website"], ["bank", "finance", "credit"]),
    "safest-news-websites": ("Safest News Websites", ["website"], ["news", "media", "journal"]),
    "safest-education-websites": ("Safest Education Websites", ["website"], ["education", "learn", "university"]),
    "safest-social-media-platforms": ("Safest Social Media Platforms", ["website"], ["social", "community", "network"]),
    "safest-streaming-websites": ("Safest Streaming Websites", ["website"], ["stream", "video", "movie"]),
    # ── Komplettering: saknade kategorier ──
    "safest-cities-for-digital-nomads": ("Safest Cities for Digital Nomads", ["city"], ["nomad", "remote", "coworking", "expat"]),
    "safest-cities-for-students": ("Safest Cities for Students", ["city"], ["student", "university", "college"]),
    "safest-saas-tools": ("Safest SaaS Tools", ["saas"], []),
    "safest-saas-project-management": ("Safest SaaS Project Management Tools", ["saas"], ["project", "management", "task", "kanban"]),
    "safest-saas-crm-tools": ("Safest SaaS CRM Tools", ["saas"], ["crm", "customer", "sales", "hubspot"]),
    "safest-saas-email-tools": ("Safest SaaS Email Tools", ["saas"], ["email", "mail", "newsletter"]),
    "safest-saas-analytics-tools": ("Safest SaaS Analytics Tools", ["saas"], ["analytics", "tracking", "metrics", "dashboard"]),
    "safest-steam-kids-games": ("Safest Steam Games for Kids", ["steam"], ["kids", "family", "children", "educational", "everyone"]),
    "safest-android-kids-apps": ("Safest Android Apps for Kids", ["android"], ["kids", "children", "family", "parental", "educational"]),
    "safest-ios-kids-apps": ("Safest iOS Apps for Kids", ["ios"], ["kids", "children", "family", "parental", "educational"]),
    # ── Web Hosting ──
    "safest-web-hosting": ("Safest Web Hosting Providers", ["hosting"], ["web hosting", "hosting provider", "best hosting"]),
    "best-wordpress-hosting": ("Best WordPress Hosting", ["hosting"], ["wordpress hosting", "managed wordpress", "wp engine", "kinsta"]),
    "best-vps-hosting": ("Best VPS Hosting", ["hosting"], ["vps", "virtual private server", "cloud server"]),
    "best-cloud-hosting": ("Best Cloud Hosting", ["hosting"], ["cloud hosting", "cloud server", "IaaS", "digitalocean", "hetzner"]),
    "best-cheapest-hosting": ("Cheapest Web Hosting", ["hosting"], ["cheap hosting", "budget hosting", "affordable", "$1.99"]),
    "best-fastest-hosting": ("Fastest Web Hosting", ["hosting"], ["fast hosting", "speed", "performance", "turbo", "litespeed"]),
    "best-ecommerce-hosting": ("Best Ecommerce Hosting", ["hosting"], ["ecommerce", "online store", "shopify hosting", "woocommerce"]),
    "best-managed-hosting": ("Best Managed Hosting", ["hosting"], ["managed hosting", "fully managed", "managed wordpress"]),
    "best-static-site-hosting": ("Best Static Site Hosting", ["hosting"], ["static site", "jamstack", "netlify", "vercel", "cloudflare pages"]),
    "best-dedicated-server-hosting": ("Best Dedicated Server Hosting", ["hosting"], ["dedicated server", "bare metal", "own hardware"]),
    "best-hosting-for-developers": ("Best Hosting for Developers", ["hosting"], ["developer hosting", "git deploy", "paas", "heroku", "railway"]),
    "best-european-hosting": ("Best European Web Hosting", ["hosting"], ["european hosting", "gdpr", "eu hosting", "german hosting", "hetzner"]),
    # ── Antivirus & Cybersecurity ──
    "safest-antivirus-software": ("Safest Antivirus Software", ["antivirus"], ["antivirus", "anti-virus", "virus protection", "security software"]),
    "best-free-antivirus": ("Best Free Antivirus", ["antivirus"], ["free antivirus", "free virus protection"]),
    "best-antivirus-for-mac": ("Best Antivirus for Mac", ["antivirus"], ["mac antivirus", "macos security"]),
    "best-antivirus-for-windows": ("Best Antivirus for Windows", ["antivirus"], ["windows antivirus", "windows security", "windows defender"]),
    "best-antivirus-for-android": ("Best Antivirus for Android", ["antivirus"], ["android antivirus", "mobile security"]),
    "best-antivirus-for-business": ("Best Antivirus for Business", ["antivirus"], ["business antivirus", "enterprise endpoint", "edr", "xdr"]),
    "best-malware-removal-tools": ("Best Malware Removal Tools", ["antivirus"], ["malware removal", "malware scanner", "anti-malware"]),
    "best-internet-security-suites": ("Best Internet Security Suites", ["antivirus"], ["internet security", "security suite", "total protection"]),
    # ── SaaS Platforms ──
    "safest-saas-platforms": ("Safest SaaS Platforms", ["saas"], ["saas", "software as a service", "cloud software"]),
    "best-crm-software": ("Best CRM Software", ["saas"], ["crm", "customer relationship", "sales platform", "hubspot", "salesforce"]),
    "best-project-management-tools": ("Best Project Management Tools", ["saas"], ["project management", "task management", "asana", "monday", "clickup"]),
    "best-email-marketing-platforms": ("Best Email Marketing Platforms", ["saas"], ["email marketing", "newsletter", "email automation", "mailchimp"]),
    "best-helpdesk-software": ("Best Helpdesk Software", ["saas"], ["helpdesk", "customer support", "ticketing", "zendesk"]),
    "best-accounting-software": ("Best Accounting Software", ["saas"], ["accounting", "bookkeeping", "invoicing", "xero", "freshbooks"]),
    "best-video-conferencing": ("Best Video Conferencing Tools", ["saas"], ["video conferencing", "video call", "meeting", "zoom"]),
    "best-design-tools": ("Best Design Tools", ["saas"], ["design tool", "graphic design", "ui design", "prototyping", "figma"]),
    "best-hr-software": ("Best HR Software", ["saas"], ["hr software", "human resources", "payroll", "people management"]),
    "best-team-communication": ("Best Team Communication Tools", ["saas"], ["team chat", "messaging", "collaboration", "slack"]),
    "best-cloud-storage": ("Best Cloud Storage", ["saas"], ["cloud storage", "file sharing", "file sync"]),
    "best-free-saas-tools": ("Best Free SaaS Tools", ["saas"], ["free saas", "free software", "freemium"]),
    "best-saas-for-startups": ("Best SaaS for Startups", ["saas"], ["startup tools", "startup stack"]),
    "best-open-source-saas": ("Best Open Source SaaS Alternatives", ["saas"], ["open source saas", "self-hosted", "open source alternative"]),
    "best-ai-writing-tools": ("Best AI Writing Tools", ["saas"], ["ai writing", "ai content", "copywriting ai"]),
    # ── Website Builders ──
    "safest-website-builders": ("Safest Website Builders", ["website_builder"], ["website builder", "site builder", "create website"]),
    "best-ecommerce-website-builders": ("Best Ecommerce Website Builders", ["website_builder"], ["ecommerce builder", "online store builder", "shopify alternative"]),
    "best-free-website-builders": ("Best Free Website Builders", ["website_builder"], ["free website builder", "free site builder"]),
    "best-website-builders-for-small-business": ("Best Website Builders for Small Business", ["website_builder"], ["small business website", "business site builder"]),
    "best-website-builders-for-portfolios": ("Best Website Builders for Portfolios", ["website_builder"], ["portfolio builder", "portfolio site", "designer portfolio"]),
    "best-website-builders-for-blogs": ("Best Website Builders for Blogs", ["website_builder"], ["blog builder", "blogging platform", "start a blog"]),
    "best-no-code-platforms": ("Best No-Code Platforms", ["website_builder"], ["no-code", "nocode", "no code builder", "build without code"]),
    "best-website-builders-for-seo": ("Best Website Builders for SEO", ["website_builder"], ["seo website builder", "seo friendly builder"]),
    # ── Crypto Exchanges ──
    "safest-crypto-exchanges": ("Safest Crypto Exchanges", ["crypto"], ["crypto exchange", "bitcoin exchange", "cryptocurrency exchange"]),
    "best-crypto-exchanges-for-beginners": ("Best Crypto Exchanges for Beginners", ["crypto"], ["beginner crypto", "first crypto", "easy exchange"]),
    "best-decentralized-exchanges": ("Best Decentralized Exchanges (DEX)", ["crypto"], ["dex", "decentralized exchange", "uniswap", "defi exchange"]),
    "best-crypto-exchanges-low-fees": ("Cheapest Crypto Exchanges", ["crypto"], ["low fees", "cheap exchange", "cheapest crypto"]),
    "best-crypto-exchanges-for-trading": ("Best Crypto Exchanges for Trading", ["crypto"], ["trading", "futures", "margin", "derivatives"]),
    "safest-crypto-wallets": ("Safest Crypto Wallets", ["crypto"], ["crypto wallet", "bitcoin wallet", "hardware wallet", "cold storage"]),
    # ── Package registries ──
    "best-php-packages": ("Best PHP Packages", ["packagist"], ["php", "composer", "packagist"]),
    "best-ruby-gems": ("Best Ruby Gems", ["gems"], ["ruby", "gem", "rails"]),
    "best-homebrew-packages": ("Best Homebrew Packages", ["homebrew"], ["homebrew", "brew", "macos"]),
    "best-vscode-extensions": ("Best VS Code Extensions", ["vscode"], ["vscode", "visual studio code", "extension"]),
}


async def _render_best_page(category_slug: str):
    """Render a best-of page. Callable from both seo_programmatic routes and seo_pages fallback."""
    cat = BEST_CATEGORIES.get(category_slug)
    if not cat:
        return HTMLResponse(_page("Category not found | Nerq",
            f'{_breadcrumb(("/best", "best"), ("", "not found"))}<h1>Category not found</h1><p><a href="/best">Browse all categories</a></p>'), status_code=404)

    display_name, db_cats, keywords = cat
    cache_key = f"best:{category_slug}"
    agents = _cached(cache_key)

    if agents is None:
        with get_db_session() as session:
            cat_placeholders = ", ".join(f":c{i}" for i in range(len(db_cats)))
            kw_conditions = " OR ".join(f"LOWER(COALESCE(description, '')) LIKE :k{i}" for i in range(len(keywords)))
            params = {f"c{i}": c for i, c in enumerate(db_cats)}
            params.update({f"k{i}": f"%{k}%" for i, k in enumerate(keywords)})

            # Check software_registry first (for registries like vpn, npm, pypi, etc.)
            _sr_registries = {"vpn", "npm", "pypi", "crates", "go", "gems", "packagist", "nuget",
                              "homebrew", "wordpress", "vscode", "chrome", "firefox", "steam", "ios", "android",
                              "country", "city", "charity", "website", "saas", "ai_tool", "crypto",
                              "ingredient", "supplement", "cosmetic_ingredient",
                              "hosting", "password_manager", "antivirus", "website_builder"}
            _has_sr = any(c in _sr_registries for c in db_cats)
            agents = []

            if _has_sr:
                sr_reg_placeholders = ", ".join(f":sr{i}" for i, c in enumerate(db_cats) if c in _sr_registries)
                sr_params = {f"sr{i}": c for i, c in enumerate(db_cats) if c in _sr_registries}
                if sr_reg_placeholders:
                    # Build keyword filter for subcategory pages
                    # Skip keyword filtering for small registries (<500 entities) — just show top by trust
                    _kw_filter = ""
                    _SMALL_REGISTRIES = {"vpn", "country", "city", "charity", "crypto",
                                         "ingredient", "supplement", "cosmetic_ingredient",
                                         "hosting", "password_manager", "antivirus", "website_builder"}
                    _skip_kw = any(c in _SMALL_REGISTRIES for c in db_cats)
                    if keywords and not _skip_kw:
                        _kw_parts = []
                        for ki, kw in enumerate(keywords):
                            pk = f"_kw{ki}"
                            sr_params[pk] = f"%{kw.lower()}%"
                            _kw_parts.append(f"LOWER(COALESCE(name,'')) LIKE :{pk} OR LOWER(COALESCE(description,'')) LIKE :{pk}")
                        _kw_filter = f"AND ({' OR '.join(_kw_parts)})"
                    sr_rows = session.execute(text(f"""
                        SELECT name, trust_score, trust_grade, downloads, description, registry
                        FROM software_registry
                        WHERE registry IN ({sr_reg_placeholders}) AND enriched_at IS NOT NULL
                          AND trust_score >= 30
                          AND description IS NOT NULL AND LENGTH(description) > 20
                          {_kw_filter}
                        ORDER BY trust_score DESC LIMIT 50
                    """), sr_params).fetchall()
                    agents = [dict(zip(["name", "score", "grade", "stars", "desc", "category"], r)) for r in sr_rows]

            if len(agents) < 15:
                # Try category matching on agents table
                q = f"""
                    SELECT name, trust_score_v2, trust_grade, stars, description, category
                    FROM entity_lookup
                    WHERE is_active = true AND category IN ({cat_placeholders})
                        AND trust_score_v2 > 0
                    ORDER BY trust_score_v2 DESC, COALESCE(stars, 0) DESC
                    LIMIT 20
                """
                rows = session.execute(text(q), {k: v for k, v in params.items() if k.startswith("c")}).fetchall()
                _existing_names = {a["name"].lower() for a in agents}
                for r in rows:
                    d = dict(zip(["name", "score", "grade", "stars", "desc", "category"], r))
                    if d["name"].lower() not in _existing_names:
                        agents.append(d)

            # Keyword fallback: if still <10 results and keywords exist, search by name/description
            if len(agents) < 10 and keywords:
                session.execute(text("SET LOCAL statement_timeout = '3s'"))
                session.execute(text("SET LOCAL work_mem = '2MB'"))
                _kw_or = " OR ".join(f"LOWER(COALESCE(name,'')) LIKE :_fk{i} OR LOWER(COALESCE(description,'')) LIKE :_fk{i}" for i in range(len(keywords)))
                _fk_params = {f"_fk{i}": f"%{kw.lower()}%" for i, kw in enumerate(keywords)}
                # Try software_registry with keyword search (broader than category match)
                _fallback_rows = session.execute(text(f"""
                    SELECT name, trust_score, trust_grade, downloads, description, registry
                    FROM software_registry
                    WHERE trust_score IS NOT NULL AND trust_score >= 30
                      AND description IS NOT NULL AND LENGTH(description) > 20
                      AND ({_kw_or})
                    ORDER BY trust_score DESC LIMIT 50
                """), _fk_params).fetchall()
                _existing_names = {a["name"].lower() for a in agents}
                for r in _fallback_rows:
                    d = dict(zip(["name", "score", "grade", "stars", "desc", "category"], r))
                    if d["name"].lower() not in _existing_names:
                        agents.append(d)

            agents.sort(key=lambda a: float(a.get("score") or 0), reverse=True)
            agents = agents[:50]
            _set_cache(cache_key, agents)

    # Minimum 10 entities required
    if len(agents) < 10:
        return HTMLResponse(_page(f"{display_name} | Nerq",
            f'{_breadcrumb(("/best", "best"), ("", display_name))}<h1>{html.escape(display_name)}</h1>'
            f'<meta name="robots" content="noindex"><p>Not enough data yet. <a href="/best">Browse other categories</a>.</p>'),
            status_code=404)

    # Detect if this is a travel/country category
    _is_travel = any(c in ("country", "city") for c in db_cats)
    _is_charity = any(c == "charity" for c in db_cats)
    _is_health = any(c in ("ingredient", "supplement", "cosmetic_ingredient") for c in db_cats)
    _use_safe_link = _is_travel or _is_charity or _is_health
    _hide_stars = _is_travel or _is_charity or _is_health

    trows = ""
    ld_items = []
    for i, ag in enumerate(agents, 1):
        slug = _safe_slug(ag["name"])
        _link = f"/safe/{slug}"
        _stars_col = "" if _hide_stars else f"<td>{_stars_fmt(ag['stars'])}</td>"
        trows += f'<tr><td>{i}</td><td><a href="{_link}">{html.escape(ag["name"])}</a></td><td>{_score_fmt(ag["score"])}</td><td>{_grade_pill(ag["grade"])}</td>{_stars_col}<td>{html.escape(_trunc(ag["desc"]))}</td></tr>'
        ld_items.append({"@type": "ListItem", "position": i, "name": ag["name"], "url": f"{SITE}{_link}"})

    _stars_th = "" if _hide_stars else "<th>Stars</th>"
    table = f'<table><thead><tr><th>#</th><th>Name</th><th>Trust</th><th>Grade</th>{_stars_th}<th>Description</th></tr></thead><tbody>{trows}</tbody></table>'

    # ── JSON-LD: ItemList + FAQPage + BreadcrumbList + WebPage ──
    _dn_esc = html.escape(display_name)
    _best_prefix = "" if any(display_name.lower().startswith(p) for p in ("best ", "safest ", "most ", "top ")) else "Best "
    _year_suffix = "" if str(YEAR) in display_name else f" {YEAR}"
    _canonical = f"{SITE}/best/{category_slug}"
    title = f"{_best_prefix}{display_name}{_year_suffix} \u2014 Ranked by Trust & Security | Nerq"
    desc = f"Top {len(agents)} {display_name.lower()} ranked by Nerq Trust Score. Independent security and trust analysis."
    h1_text = f"Best {_dn_esc} {YEAR}"

    # FAQ questions for JSON-LD
    faq_items = []
    if _is_travel:
        _kind = "cities" if "city" in db_cats else "countries"
        faq_items = [
            (f"Which {_kind} are safest to visit in {YEAR}?", f"Based on Nerq Safety Scores, the safest destinations are listed above, scored on crime, political stability, health, natural disasters, infrastructure, and traveler rights."),
            ("How are safety scores calculated?", "Nerq scores destinations using data from the Global Peace Index, UNODC crime statistics, World Bank governance indicators, WHO health data, and government travel advisories."),
            ("Are these rankings updated regularly?", "Yes. Safety scores are updated as new data becomes available from international sources."),
        ]
    elif _is_charity:
        faq_items = [
            (f"Which charities are most trustworthy in {YEAR}?", f"Based on Nerq Trust Scores, the top-rated charities are listed above, scored on financial transparency, program effectiveness, governance, and accountability."),
            ("How are charity trust scores calculated?", "Nerq evaluates charities on financial transparency, program expense ratios, governance structure, donor trust signals, and accountability measures."),
            ("Should I donate to the top-rated charity?", "Trust scores indicate organizational integrity, not necessarily alignment with your values. Review each charity's mission and impact areas to find the best match for your donation."),
        ]
    elif _is_health:
        faq_items = [
            (f"Which {display_name.lower()} are safest in {YEAR}?", f"Based on Nerq Safety Scores, the items listed above are ranked by toxicology, regulatory status, long-term safety, and allergen risk data from FDA, EU, and WHO sources."),
            ("How are safety scores calculated?", "Nerq evaluates ingredients and supplements using data from FDA GRAS, EU food additive regulations, WHO IARC classifications, and peer-reviewed toxicology studies."),
            ("Are these rankings updated regularly?", "Yes. Safety scores are updated as new regulatory decisions and scientific studies become available."),
        ]
    else:
        faq_items = [
            (f"What are the best {display_name.lower()} in {YEAR}?", f"Based on Nerq Trust Scores, the top-ranked {display_name.lower()} are listed above, scored on security, activity, documentation, and community metrics."),
            (f"How are {display_name.lower()} ranked?", "Nerq ranks tools using Trust Score v2, which combines security analysis, maintenance activity, documentation quality, and community adoption signals."),
            (f"Are these {display_name.lower()} safe to use?", "Each tool has an individual safety report. Click any tool name to see its detailed trust analysis."),
            ("What does a Nerq Trust Score of A mean?", "An A grade (80-89) means the entity has strong signals across security, maintenance, documentation, and community adoption. A+ (90-100) is the highest possible rating."),
            (f"How does Nerq evaluate {display_name.lower()}?", f"Nerq analyzes {display_name.lower()} across multiple dimensions including security vulnerabilities, license compliance, maintenance activity, documentation quality, and community adoption. Each dimension is scored independently and combined into an overall Trust Score (0-100)."),
        ]

    faq_html = _faq_section(faq_items)

    # Build combined JSON-LD: ItemList + FAQPage + BreadcrumbList + WebPage
    faq_ld = {"@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq_items
    ]}
    breadcrumb_ld = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
        {"@type": "ListItem", "position": 2, "name": "Best", "item": f"{SITE}/best"},
        {"@type": "ListItem", "position": 3, "name": display_name, "item": _canonical},
    ]}
    webpage_ld = {
        "@type": "WebPage",
        "name": f"{_best_prefix}{display_name}{_year_suffix}",
        "description": desc,
        "url": _canonical,
        "dateModified": TODAY,
        "publisher": {"@type": "Organization", "name": "Nerq", "url": f"{SITE}/"},
        "speakable": {"@type": "SpeakableSpecification", "cssSelector": [".pplx-verdict", ".ai-summary", "h1"]},
    }
    item_list_ld = {"@type": "ItemList", "name": f"Best {display_name} {YEAR}", "numberOfItems": len(agents), "itemListElement": ld_items}
    jsonld_str = json.dumps({"@context": "https://schema.org", "@graph": [item_list_ld, faq_ld, breadcrumb_ld, webpage_ld]})

    # ── pplx-verdict + ai-summary ──
    _top = agents[0] if agents else {}
    _top_name = html.escape(_top.get("name", ""))
    _top_score = f"{float(_top.get('score', 0)):.0f}" if _top.get("score") else "?"
    _top_grade = _top.get("grade", "?")
    _enriched_count = len(agents)

    # Top 5 list
    _top5 = ", ".join(f"{i+1}. {html.escape(a.get('name',''))} ({float(a.get('score',0)):.0f}/100)" for i, a in enumerate(agents[:5]))

    # Data-driven insight
    _downloads = [a.get("stars", 0) or 0 for a in agents[:20] if (a.get("stars") or 0) > 0]
    _insight = f"Nerq Trust Scores range from {float(agents[-1].get('score',0)):.0f} to {float(agents[0].get('score',0)):.0f} among the top {len(agents)}." if len(agents) > 1 else ""

    _verdict_html = (
        f'<p class="pplx-verdict" style="font-size:1.05em;line-height:1.65;margin:12px 0 16px;'
        f'padding:14px 18px;background:#f0fdf4;border-left:4px solid #16a34a;border-radius:4px">'
        f'The #1 {html.escape(display_name.lower())} in {YEAR} is <strong>{_top_name}</strong> '
        f'with a Nerq Trust Score of <strong>{_top_score}/100 ({html.escape(_top_grade)})</strong>, '
        f'based on Nerq\'s independent analysis of {_enriched_count} {html.escape(display_name.lower())} '
        f'across 5 trust dimensions. Rankings update daily — last updated: {TODAY}.</p>'
    )

    _summary_html = (
        f'<p class="ai-summary" style="font-size:15px;line-height:1.7;color:#374151;margin-bottom:20px">'
        f'According to Nerq\'s analysis, the top 5 {html.escape(display_name.lower())} by trust score are: '
        f'{_top5}. {_insight} '
        f'Scores are based on 5 independent trust dimensions including security, maintenance, and community adoption. '
        f'Updated daily.</p>'
    )

    # ── Top 10 summary table ──
    _top10_rows = ""
    for i, ag in enumerate(agents[:10], 1):
        _t10_slug = _safe_slug(ag["name"])
        _t10_sc = _score_fmt(ag["score"])
        _t10_gr = _grade_pill(ag["grade"])
        _top10_rows += f'<tr><td>{i}</td><td><a href="/safe/{_t10_slug}">{html.escape(ag["name"])}</a></td><td>{_t10_sc}</td><td>{_t10_gr}</td></tr>'
    _top10_table = (
        f'<table class="best-table" style="width:100%;border-collapse:collapse;margin:20px 0;font-size:14px">'
        f'<caption style="caption-side:top;text-align:left;font-size:15px;font-weight:600;color:#1e293b;padding:0 0 8px">Top 10 {_dn_esc} by Nerq Trust Score ({YEAR})</caption>'
        f'<thead><tr style="background:#f1f5f9;text-align:left">'
        f'<th style="padding:8px 10px;border-bottom:2px solid #cbd5e1;width:40px">#</th>'
        f'<th style="padding:8px 10px;border-bottom:2px solid #cbd5e1">Name</th>'
        f'<th style="padding:8px 10px;border-bottom:2px solid #cbd5e1;width:60px">Trust</th>'
        f'<th style="padding:8px 10px;border-bottom:2px solid #cbd5e1;width:60px">Grade</th>'
        f'</tr></thead><tbody>{_top10_rows}</tbody></table>'
        f'<style>.best-table tbody tr:nth-child(even){{background:#f8fafc}}'
        f'.best-table tbody tr:hover{{background:#e0f2fe}}'
        f'.best-table td{{padding:6px 10px;border-bottom:1px solid #e2e8f0}}'
        f'.best-table a{{color:#2563eb;text-decoration:none}}.best-table a:hover{{text-decoration:underline}}</style>'
    )

    # ── Render body ──
    body = f"""{_breadcrumb(("/best", "best"), ("", display_name))}
<h1>{h1_text}</h1>
{_verdict_html}
{_summary_html}
{_top10_table}
<meta property="og:url" content="{_canonical}">

<h2>Top {len(agents)} {_dn_esc} by Nerq Trust Score</h2>
{table}

<h2>How We Rank {_dn_esc}</h2>
<p>These {display_name.lower()} are ranked by Nerq Trust Score, which evaluates security, maintenance, community adoption, and transparency across multiple data points. Only entities with a trust score of 30 or above are included. Scores are updated continuously as new data becomes available.</p>

{faq_html}"""

    # Security Stack block for VPN, PM, AV best pages
    _SEC_STACK_REGS = {"vpn", "password_manager", "antivirus"}
    if any(c in _SEC_STACK_REGS for c in db_cats):
        _ss_links = ""
        _ss_items = [
            ("&#128274;", "Best VPNs", "/best/safest-vpns", "vpn"),
            ("&#128272;", "Best Password Managers", "/best/safest-password-managers", "password_manager"),
            ("&#128737;", "Best Antivirus", "/best/safest-antivirus-software", "antivirus"),
        ]
        for _ico, _txt, _url, _reg in _ss_items:
            if _reg not in db_cats:
                _ss_links += (f'<a href="{_url}" style="display:flex;align-items:center;gap:8px;'
                    f'padding:10px 14px;border-radius:8px;background:#f8fafc;border:1px solid #e2e8f0;'
                    f'text-decoration:none;color:#1e293b;font-size:14px">'
                    f'<span style="font-size:20px">{_ico}</span>'
                    f'<span style="font-weight:500">{_txt}</span></a>')
        body += (f'\n<div style="margin:24px 0;padding:18px;border:1px solid #d1d5db;border-radius:10px;background:#fafafa">'
            f'<h3 style="margin:0 0 12px;font-size:15px;font-weight:600;color:#334155">Build Your Security Stack</h3>'
            f'<p style="font-size:13px;color:#64748b;margin:0 0 12px">Combine these tools for comprehensive protection:</p>'
            f'<div style="display:flex;flex-wrap:wrap;gap:10px">{_ss_links}</div></div>')

    # Noindex if all db_cats registries are hidden (quality gate)
    try:
        from agentindex.quality_gate import get_publishable_registries
        _pub = get_publishable_registries()
        _has_published = any(c in _pub for c in db_cats)
    except Exception:
        _has_published = True  # Default to index on error
    _robots = "index, follow" if _has_published else "noindex, follow"

    return HTMLResponse(_page(title, body, desc=desc, canonical=_canonical, jsonld=jsonld_str, robots=_robots))


# ── Mount all routes ────────────────────────────────────────
def mount_seo_programmatic(app):
    """Mount programmatic SEO routes onto the FastAPI app."""

    # ── 1. Comparison pages (Enhanced BUILD 15) ────────────
    @app.get("/compare/{slug_a}-vs-{slug_b}", response_class=HTMLResponse)
    async def compare_page(slug_a: str, slug_b: str):
        if slug_a.lower() > slug_b.lower():
            from fastapi.responses import RedirectResponse
            return RedirectResponse(f"/compare/{slug_b}-vs-{slug_a}", status_code=301)

        with get_db_session() as session:
            a = _find_agent(session, slug_a)
            b = _find_agent(session, slug_b)
            if not a or not b:
                missing = slug_a if not a else slug_b
                dn_a = slug_a.replace("-", " ").title()
                dn_b = slug_b.replace("-", " ").title()
                # Queue demand signal
                try:
                    from agentindex.agent_safety_pages import _queue_for_crawling
                    if not a: _queue_for_crawling(slug_a, bot="compare-404")
                    if not b: _queue_for_crawling(slug_b, bot="compare-404")
                except Exception:
                    pass
                return HTMLResponse(_page(
                    f"{dn_a} vs {dn_b} — Not Yet Analyzed | Nerq",
                    f'{_breadcrumb(("/compare", "compare"), ("", f"{dn_a} vs {dn_b}"))}<h1>{html.escape(dn_a)} vs {html.escape(dn_b)} — Not Yet Analyzed</h1><meta name="robots" content="noindex"><p>Nerq has not yet completed a full trust comparison. This comparison has been queued for analysis.</p><p><a href="/compare">Browse existing comparisons</a> &middot; <a href="/">Search Nerq</a></p>',
                ), status_code=200)

        na, nb = html.escape(a["name"]), html.escape(b["name"])
        sa, sb = a.get("trust_score_v2"), b.get("trust_score_v2")
        ga, gb = a.get("trust_grade"), b.get("trust_grade")
        slug_a_safe, slug_b_safe = _safe_slug(a["name"]), _safe_slug(b["name"])
        sec_a, sec_b = a.get("security_score"), b.get("security_score")
        act_a, act_b = a.get("activity_score"), b.get("activity_score")
        doc_a, doc_b = a.get("documentation_score"), b.get("documentation_score")
        pop_a, pop_b = a.get("popularity_score"), b.get("popularity_score")
        stars_a, stars_b = a.get("stars") or 0, b.get("stars") or 0
        lic_a, lic_b = a.get("license") or "Not specified", b.get("license") or "Not specified"
        cat_a, cat_b = a.get("category") or "General", b.get("category") or "General"
        desc_a = html.escape(_trunc(a.get("description") or "", 200))
        desc_b = html.escape(_trunc(b.get("description") or "", 200))

        # ── Featured snippet paragraph (under 50 words, self-contained)
        if sa is not None and sb is not None:
            winner_name = na if sa >= sb else nb
            loser_name = nb if sa >= sb else na
            w_score, l_score = (max(sa, sb), min(sa, sb))
            sec_winner = na if (sec_a or 0) >= (sec_b or 0) else nb
            act_winner = na if (act_a or 0) >= (act_b or 0) else nb
            snippet = f'{na} scores {_score_fmt(sa)}/100 on Nerq\'s trust index compared to {nb}\'s {_score_fmt(sb)}/100. {sec_winner} has a stronger security profile. {act_winner} shows better maintenance activity. For most use cases, {winner_name} is the safer choice in {YEAR}.'
        else:
            snippet = f'Comparing {na} and {nb} on trust, security, and maintenance metrics. Full independent analysis below.'
            winner_name = na

        featured = f'<div style="background:#ecfdf5;border:2px solid #a7f3d0;border-radius:8px;padding:20px;margin:20px 0"><h2 style="margin:0 0 8px 0;font-size:1.1em">Quick Verdict</h2><p style="margin:0;font-size:1.05em;line-height:1.6">{snippet}</p></div>'

        # ── Comparison table (expanded)
        dims = [
            ("Trust Score", _score_fmt(sa), _score_fmt(sb), "Overall trust rating combining all metrics"),
            ("Grade", _grade_pill(ga), _grade_pill(gb), "Letter grade based on trust score percentile"),
            ("Security Score", _score_fmt(sec_a), _score_fmt(sec_b), "Vulnerability exposure, dependency risk, known CVEs"),
            ("Activity Score", _score_fmt(act_a), _score_fmt(act_b), "Commit frequency, issue response time, release cadence"),
            ("Documentation Score", _score_fmt(doc_a), _score_fmt(doc_b), "README quality, API docs, examples, tutorials"),
            ("Popularity Score", _score_fmt(pop_a), _score_fmt(pop_b), "GitHub stars, npm/PyPI downloads, community size"),
            ("GitHub Stars", _stars_fmt(stars_a), _stars_fmt(stars_b), "Community adoption and interest signal"),
            ("Category", html.escape(cat_a), html.escape(cat_b), "Primary classification in Nerq index"),
            ("Language", html.escape(a.get("language") or "-"), html.escape(b.get("language") or "-"), "Primary programming language"),
            ("License", html.escape(lic_a), html.escape(lic_b), "Open source license type"),
        ]
        rows = ""
        for label, va, vb, tooltip in dims:
            rows += f'<tr><td style="font-weight:600" title="{html.escape(tooltip)}">{label}</td><td>{va}</td><td>{vb}</td></tr>'
        table = f'<table><thead><tr><th>Metric</th><th>{na}</th><th>{nb}</th></tr></thead><tbody>{rows}</tbody></table>'

        # ── Dimension-by-dimension analysis (paragraphs for word count + SEO)
        dim_analysis = '<h2>Detailed Comparison</h2>'

        # Security
        if sec_a is not None and sec_b is not None:
            sec_w = na if sec_a >= sec_b else nb
            sec_l = nb if sec_a >= sec_b else na
            dim_analysis += f'<h3>Security</h3><p>{sec_w} leads on security with a score of {_score_fmt(max(sec_a, sec_b))}/100 compared to {sec_l}\'s {_score_fmt(min(sec_a, sec_b))}/100. This score reflects dependency vulnerability analysis, known CVE exposure, and security best practices. A higher security score means fewer known vulnerabilities and better security hygiene in the codebase.</p>'
        else:
            dim_analysis += f'<h3>Security</h3><p>Security scores measure dependency vulnerabilities, CVE exposure, and security practices. {na} scores {_score_fmt(sec_a)} and {nb} scores {_score_fmt(sec_b)} on this dimension.</p>'

        # Maintenance / Activity
        if act_a is not None and act_b is not None:
            act_w = na if act_a >= act_b else nb
            dim_analysis += f'<h3>Maintenance & Activity</h3><p>{act_w} demonstrates stronger maintenance activity ({_score_fmt(max(act_a, act_b))}/100 vs {_score_fmt(min(act_a, act_b))}/100). This metric captures commit frequency, issue response times, and release cadence. Actively maintained tools receive faster security patches and are less likely to accumulate technical debt.</p>'
        else:
            dim_analysis += f'<h3>Maintenance & Activity</h3><p>Activity scores reflect how actively each project is maintained. {na}: {_score_fmt(act_a)}, {nb}: {_score_fmt(act_b)}.</p>'

        # Documentation
        if doc_a is not None and doc_b is not None:
            doc_w = na if doc_a >= doc_b else nb
            dim_analysis += f'<h3>Documentation</h3><p>{doc_w} has better documentation ({_score_fmt(max(doc_a, doc_b))}/100 vs {_score_fmt(min(doc_a, doc_b))}/100). Good documentation reduces onboarding time and helps teams adopt the tool safely. This score evaluates README completeness, API documentation, code examples, and tutorial availability.</p>'
        else:
            dim_analysis += f'<h3>Documentation</h3><p>Documentation quality is evaluated based on README, API docs, and example coverage. {na}: {_score_fmt(doc_a)}, {nb}: {_score_fmt(doc_b)}.</p>'

        # Community / Popularity
        dim_analysis += f'<h3>Community & Adoption</h3><p>{na} has {_stars_fmt(stars_a)} GitHub stars while {nb} has {_stars_fmt(stars_b)}. '
        if stars_a > stars_b * 2:
            dim_analysis += f'{na} has significantly broader community adoption, which typically means more Stack Overflow answers, more third-party tutorials, and faster ecosystem development.'
        elif stars_b > stars_a * 2:
            dim_analysis += f'{nb} has significantly broader community adoption, which typically means more Stack Overflow answers, more third-party tutorials, and faster ecosystem development.'
        else:
            dim_analysis += 'Both tools have comparable community sizes, suggesting similar levels of ecosystem support and third-party resources.'
        dim_analysis += '</p>'

        # Licensing
        dim_analysis += f'<h3>Licensing</h3><p>{na} uses the {html.escape(lic_a)} license while {nb} uses {html.escape(lic_b)}. '
        mit_like = {"mit", "apache-2.0", "apache 2.0", "bsd-3-clause", "bsd-2-clause", "isc"}
        if lic_a.lower() in mit_like and lic_b.lower() in mit_like:
            dim_analysis += 'Both use permissive licenses suitable for commercial use without significant restrictions.'
        elif lic_a.lower() in mit_like:
            dim_analysis += f'{na} has a more permissive license, making it easier to integrate into commercial projects.'
        elif lic_b.lower() in mit_like:
            dim_analysis += f'{nb} has a more permissive license, making it easier to integrate into commercial projects.'
        else:
            dim_analysis += 'Review each license carefully for compatibility with your project requirements.'
        dim_analysis += '</p>'

        # ── When to choose sections (enhanced)
        choose_a_points, choose_b_points = [], []
        if sa and sb:
            if sa > sb:
                choose_a_points.append("Higher overall trust score — more reliable for production use")
            elif sb > sa:
                choose_b_points.append("Higher overall trust score — more reliable for production use")
            if (sec_a or 0) > (sec_b or 0):
                choose_a_points.append("Stronger security profile with fewer known vulnerabilities")
            elif (sec_b or 0) > (sec_a or 0):
                choose_b_points.append("Stronger security profile with fewer known vulnerabilities")
            if (act_a or 0) > (act_b or 0):
                choose_a_points.append("More actively maintained with faster release cadence")
            elif (act_b or 0) > (act_a or 0):
                choose_b_points.append("More actively maintained with faster release cadence")
            if stars_a > stars_b:
                choose_a_points.append(f"Larger community ({_stars_fmt(stars_a)} vs {_stars_fmt(stars_b)} stars)")
            elif stars_b > stars_a:
                choose_b_points.append(f"Larger community ({_stars_fmt(stars_b)} vs {_stars_fmt(stars_a)} stars)")
            if (doc_a or 0) > (doc_b or 0):
                choose_a_points.append("Better documentation for faster onboarding")
            elif (doc_b or 0) > (doc_a or 0):
                choose_b_points.append("Better documentation for faster onboarding")

        def _choice_list(points):
            if not points:
                return '<li>Consider if it better fits your specific use case and tech stack</li>'
            return "".join(f"<li>{p}</li>" for p in points)

        choose_html = f"""
<h2>When to Choose Each Tool</h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0">
<div style="border:1px solid #d1fae5;background:#f0fdf4;border-radius:8px;padding:16px"><h3 style="margin-top:0">Choose {na} if you need:</h3><ul style="color:#4b5563;margin-bottom:0">{_choice_list(choose_a_points)}</ul></div>
<div style="border:1px solid #dbeafe;background:#eff6ff;border-radius:8px;padding:16px"><h3 style="margin-top:0">Choose {nb} if you need:</h3><ul style="color:#4b5563;margin-bottom:0">{_choice_list(choose_b_points)}</ul></div>
</div>"""

        # ── Migration guide
        migration = f"""<h2>Switching from {na} to {nb} (or vice versa)</h2>
<p>When migrating between {na} and {nb}, consider these factors:</p>
<ol>
<li><strong>API Compatibility:</strong> Review both tools' APIs. {na} ({html.escape(cat_a)}) and {nb} ({html.escape(cat_b)}) {'share similar interfaces since they are in the same category' if cat_a.lower() == cat_b.lower() else 'serve different categories, so migration may require significant refactoring'}.</li>
<li><strong>Dependency Changes:</strong> Check your dependency tree. {na} uses {html.escape(a.get("language") or "unspecified")} while {nb} uses {html.escape(b.get("language") or "unspecified")}{'—same ecosystem, so dependency migration should be straightforward' if (a.get("language") or "").lower() == (b.get("language") or "").lower() and a.get("language") else '—different ecosystems may require additional bridging'}.</li>
<li><strong>Security Review:</strong> Run a security audit after migration. Check the <a href="/is-{slug_a_safe}-safe">{na} safety report</a> and <a href="/is-{slug_b_safe}-safe">{nb} safety report</a> for known issues.</li>
<li><strong>Testing:</strong> Ensure your test suite covers all integration points before switching in production.</li>
</ol>"""

        # ── Internal links section (10+ links)
        internal_links = f"""<h2>Related Pages</h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:16px 0">
<div>
<h4>Safety Reports</h4>
<ul>
<li><a href="/is-{slug_a_safe}-safe">Is {na} Safe?</a></li>
<li><a href="/is-{slug_b_safe}-safe">Is {nb} Safe?</a></li>
</ul>
<h4>Alternatives</h4>
<ul>
<li><a href="/alternatives/{slug_a_safe}">{na} Alternatives</a></li>
<li><a href="/alternatives/{slug_b_safe}">{nb} Alternatives</a></li>
</ul>
</div>
<div>
<h4>Guides</h4>
<ul>
<li><a href="/guide/{slug_a_safe}">{na} Guide</a></li>
<li><a href="/guide/{slug_b_safe}">{nb} Guide</a></li>
</ul>
<h4>More</h4>
<ul>
<li><a href="/best/{_to_slug(cat_a)}">Best {html.escape(cat_a)} Tools</a></li>
<li><a href="/leaderboard">Trust Leaderboard</a></li>
<li><a href="/compare">More Comparisons</a></li>
</ul>
</div>
</div>"""

        # ── FAQ (7 questions for rich snippets)
        faq_items = [
            (f"Is {na} better than {nb}?", f"{na} scores {_score_fmt(sa)}/100 on the Nerq Trust Score while {nb} scores {_score_fmt(sb)}/100. {winner_name} has the edge overall, but the best choice depends on your specific requirements including security needs, community support, and tech stack compatibility."),
            (f"Which is safer, {na} or {nb}?", f"Based on independent security analysis, {na} has a security score of {_score_fmt(sec_a)}/100 and {nb} has {_score_fmt(sec_b)}/100. See the full safety reports: <a href='/is-{slug_a_safe}-safe'>{na}</a> | <a href='/is-{slug_b_safe}-safe'>{nb}</a>."),
            (f"Should I switch from {na} to {nb}?", f"If {nb} scores higher on metrics that matter to your use case (security: {_score_fmt(sec_b)}, activity: {_score_fmt(act_b)}, docs: {_score_fmt(doc_b)}), switching may be worthwhile. Consider migration effort and API compatibility first."),
            (f"Is {na} safe to use?", f"{na} has a trust grade of {html.escape(ga or 'N/A')} with {_stars_fmt(stars_a)} GitHub stars. See the <a href='/is-{slug_a_safe}-safe'>full {na} safety report</a> for CVE analysis and dependency audit."),
            (f"Is {nb} safe to use?", f"{nb} has a trust grade of {html.escape(gb or 'N/A')} with {_stars_fmt(stars_b)} GitHub stars. See the <a href='/is-{slug_b_safe}-safe'>full {nb} safety report</a> for CVE analysis and dependency audit."),
            (f"What are alternatives to {na} and {nb}?", f"Nerq indexes thousands of alternatives ranked by trust score. See <a href='/alternatives/{slug_a_safe}'>{na} alternatives</a> and <a href='/alternatives/{slug_b_safe}'>{nb} alternatives</a>."),
            (f"How does Nerq compare {na} and {nb}?", f"Nerq's Trust Score v2 evaluates both tools across security, maintenance activity, documentation quality, and community adoption. Scores are computed independently with no sponsorship influence."),
        ]
        faq = _faq_section(faq_items)

        # ── JSON-LD: FAQPage + Dataset + BreadcrumbList
        faq_ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a_text.replace("<a href='", "").replace("'>", " ").replace("</a>", "")}}
            for q, a_text in faq_items
        ]}
        dataset_ld = {"@context": "https://schema.org", "@type": "Dataset",
            "name": f"{a['name']} vs {b['name']} Trust Comparison",
            "description": f"Independent trust and security comparison of {a['name']} and {b['name']}",
            "dateModified": TODAY,
            "creator": {"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"},
            "variableMeasured": [
                {"@type": "PropertyValue", "name": f"{a['name']} Trust Score", "value": sa},
                {"@type": "PropertyValue", "name": f"{b['name']} Trust Score", "value": sb},
                {"@type": "PropertyValue", "name": f"{a['name']} Security Score", "value": sec_a},
                {"@type": "PropertyValue", "name": f"{b['name']} Security Score", "value": sec_b},
            ]}
        breadcrumb_ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Nerq", "item": SITE},
            {"@type": "ListItem", "position": 2, "name": "Compare", "item": f"{SITE}/compare"},
            {"@type": "ListItem", "position": 3, "name": f"{a['name']} vs {b['name']}"},
        ]}

        canonical = f"{SITE}/compare/{slug_a}-vs-{slug_b}"
        title = f"{a['name']} vs {b['name']} — Comparison {YEAR} | Nerq"
        desc_text = f"{na} scores {_score_fmt(sa)}/100 vs {nb}'s {_score_fmt(sb)}/100. Security, trust, and maintenance comparison."
        verdict_short = f"{winner_name} scores higher ({_score_fmt(max(sa or 0, sb or 0))} vs {_score_fmt(min(sa or 0, sb or 0))})" if sa and sb else "Comparison in progress"

        # ── Last modified visible on page
        updated_tag = f'<p style="color:#6b7280;font-size:0.85em;margin-top:4px">Last updated: {TODAY} | Data refreshed weekly</p>'

        body = f"""{_breadcrumb(("/compare", "compare"), ("", f"{na} vs {nb}"))}
<h1>{na} vs {nb}</h1>
{updated_tag}
<p>{snippet}</p>
{featured}
{table}
{dim_analysis}
{choose_html}
{migration}
{faq}
{internal_links}"""

        return HTMLResponse(_page(title, body, desc=desc_text, canonical=canonical,
            jsonld=json.dumps(faq_ld), extra_ld=json.dumps(dataset_ld),
            nerq_type="comparison", nerq_tools=f"{a['name']},{b['name']}", nerq_verdict=verdict_short))

    # ── Compare hub ─────────────────────────────────────────
    POPULAR_COMPARISONS = {
        "VPN Services": [
            ("nordvpn", "expressvpn"), ("mullvad", "protonvpn"), ("surfshark", "nordvpn"),
            ("cyberghost", "pia"), ("protonvpn", "mullvad"),
        ],
        "Messaging & Social": [
            ("signal", "whatsapp"), ("telegram", "signal"), ("whatsapp", "telegram"),
            ("discord", "slack"), ("tiktok", "instagram"),
        ],
        "Shopping & Marketplaces": [
            ("temu", "amazon"), ("shein", "temu"), ("aliexpress", "amazon"),
            ("ebay", "amazon"), ("wish", "temu"),
        ],
        "Browsers": [
            ("chrome", "firefox"), ("brave", "firefox"), ("safari", "chrome"),
        ],
        "JavaScript & Node.js": [
            ("react", "vue"), ("express", "fastify"), ("next", "nuxt"),
            ("axios", "got"), ("prisma", "drizzle"), ("jest", "vitest"),
        ],
        "Python": [
            ("flask", "django"), ("fastapi", "flask"), ("pandas", "polars"),
        ],
        "WordPress": [
            ("yoast-seo", "rank-math"), ("elementor", "divi"),
        ],
        "Password Managers": [
            ("bitwarden", "lastpass"), ("1password", "bitwarden"),
        ],
        "Email & Privacy": [
            ("protonmail", "gmail"), ("tutanota", "protonmail"),
        ],
        "Developer Tools": [
            ("vscode", "cursor"), ("github-copilot", "cursor"),
            ("vercel", "netlify"), ("docker", "podman"),
        ],
        "AI Tools": [
            ("chatgpt", "claude"), ("cursor", "copilot"), ("langchain", "llamaindex"),
        ],
    }

    @app.get("/compare", response_class=HTMLResponse)
    async def compare_hub():
        # Curated comparison sections
        curated_html = ""
        for category, pairs in POPULAR_COMPARISONS.items():
            links = ""
            for a, b in pairs:
                sa, sb = sorted([a, b])
                label_a = a.replace("-", " ").title()
                label_b = b.replace("-", " ").title()
                links += f'<li><a href="/compare/{sa}-vs-{sb}">{html.escape(label_a)} vs {html.escape(label_b)}</a></li>'
            curated_html += f'<h3>{html.escape(category)}</h3><ul>{links}</ul>'

        # Dynamic pairs from DB as fallback
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT name, trust_score_v2, trust_grade, stars, category
                FROM entity_lookup WHERE is_active = true AND trust_score_v2 IS NOT NULL
                ORDER BY stars DESC NULLS LAST LIMIT 40
            """)).fetchall()
        agents = [dict(zip(["name", "score", "grade", "stars", "category"], r)) for r in rows]

        pairs_html = ""
        seen = set()
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                if len(seen) >= 20:
                    break
                a, b = agents[i], agents[j]
                if a.get("category") and a["category"] == b.get("category"):
                    sa, sb = _to_slug(a["name"]), _to_slug(b["name"])
                    key = tuple(sorted([sa, sb]))
                    if key not in seen:
                        seen.add(key)
                        pairs_html += f'<li><a href="/compare/{key[0]}-vs-{key[1]}">{html.escape(a["name"])} vs {html.escape(b["name"])}</a></li>'

        more_section = ""
        if pairs_html:
            more_section = f'<h3>More from Our Index</h3><ul>{pairs_html}</ul>'

        body = f"""{_breadcrumb(("", "compare"))}
<h1>Compare Software &mdash; Side by Side Trust Analysis</h1>
<p class="desc">Side-by-side trust and security comparisons of popular software, tools, and services.</p>
{curated_html}
{more_section}"""

        return HTMLResponse(_page(f"Compare Software — Side by Side Trust Analysis {YEAR} | Nerq", body,
                                   desc="Compare software side by side on trust, security, and community metrics. VPNs, browsers, packages, AI tools and more.",
                                   canonical=f"{SITE}/compare"))

    # ── 2. Best-of pages ────────────────────────────────────
    @app.get("/best/{category_slug}", response_class=HTMLResponse)
    async def best_of_page(category_slug: str):
        return await _render_best_page(category_slug)

    # ── Best hub ────────────────────────────────────────────
    @app.get("/best", response_class=HTMLResponse)
    async def best_hub():
        # Organize categories into sections
        consumer_prefixes = ("safest-",)
        developer_prefixes = ("best-npm", "best-python", "best-rust", "best-wordpress", "best-vscode")

        consumer_items = ""
        developer_items = ""
        ai_items = ""
        for slug, (name, _, _) in sorted(BEST_CATEGORIES.items(), key=lambda x: x[1][0]):
            link = f'<li style="margin:6px 0"><a href="/best/{slug}">{html.escape(name)}</a></li>'
            if slug.startswith(consumer_prefixes):
                consumer_items += link
            elif slug.startswith(developer_prefixes):
                developer_items += link
            else:
                ai_items += link

        sections = ""
        if consumer_items:
            sections += f'<h2>Consumer Safety</h2><ul>{consumer_items}</ul>'
        if developer_items:
            sections += f'<h2>Developer Tools</h2><ul>{developer_items}</ul>'
        if ai_items:
            sections += f'<h2>AI Tools</h2><ul>{ai_items}</ul>'

        body = f"""{_breadcrumb(("", "best"))}
<h1>Best Software by Category {YEAR}</h1>
<p class="desc">Browse top software by category, ranked by Nerq Trust Score.</p>
{sections}"""
        return HTMLResponse(_page(f"Best Software by Category {YEAR} | Nerq", body,
                                   desc=f"Browse the best software of {YEAR} across {len(BEST_CATEGORIES)} categories, ranked by independent trust scores.",
                                   canonical=f"{SITE}/best"))

    # ── 3a. Alternatives landing page ─────────────────────────
    @app.get("/alternatives", response_class=HTMLResponse)
    async def alternatives_landing():
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT name FROM entity_lookup WHERE is_active = true AND trust_score_v2 > 60
                AND category IS NOT NULL
                ORDER BY COALESCE(stars, 0) DESC LIMIT 60
            """)).fetchall()
        links = "".join(f'<li><a href="/alternatives/{_to_slug(r[0])}">{r[0]} Alternatives</a></li>' for r in rows)
        body = f"""<h1>Software Alternatives — Ranked by Trust</h1>
<p style="font-size:15px;color:#64748b;margin-bottom:24px">Find safer, more trusted alternatives to popular software. Every recommendation is backed by Nerq Trust Scores.</p>
<ul style="columns:2;column-gap:32px;list-style:none;padding:0">{links}</ul>"""
        return HTMLResponse(_page("Software Alternatives Ranked by Trust | Nerq", body,
                                   desc="Find safer alternatives to popular software, ranked by independent trust scores. 204K+ tools compared.",
                                   canonical=f"{SITE}/alternatives"))

    # ── 3b. Alternatives pages ───────────────────────────────
    @app.get("/alternatives/{tool_slug}", response_class=HTMLResponse)
    async def alternatives_page(tool_slug: str):
        with get_db_session() as session:
            tool = _find_agent(session, tool_slug)
            if not tool:
                _dn = tool_slug.replace("-", " ").title()
                return HTMLResponse(_page(f"Alternatives to {_dn} | Nerq",
                    f'{_breadcrumb(("/alternatives", "alternatives"), ("", _dn))}'
                    f'<meta name="robots" content="noindex">'
                    f'<h1>Alternatives to {html.escape(_dn)}</h1>'
                    f'<p>This tool has not been analyzed yet. <a href="/">Search Nerq</a> for trust scores.</p>'), status_code=200)

            cache_key = f"alts:{tool_slug}"
            alts = _cached(cache_key)
            if alts is None:
                cat = tool.get("category")
                _tool_id = tool.get("id")
                if not _tool_id:
                    _tool_id = "00000000-0000-0000-0000-000000000000"
                params: dict = {"tid": str(_tool_id)}
                cat_filter = ""
                if cat:
                    cat_filter = "AND category = :cat"
                    params["cat"] = cat

                rows = session.execute(text(f"""
                    SELECT name, trust_score_v2, trust_grade, stars, description, category
                    FROM entity_lookup
                    WHERE is_active = true AND id != CAST(:tid AS uuid) AND trust_score_v2 > 0
                    {cat_filter}
                    ORDER BY COALESCE(trust_score_v2, 0) DESC, COALESCE(stars, 0) DESC
                    LIMIT 15
                """), params).fetchall()
                alts = [dict(zip(["name", "score", "grade", "stars", "desc", "category"], r)) for r in rows]
                _set_cache(cache_key, alts)

        tn = html.escape(tool["name"])
        ts = tool.get("trust_score_v2")
        tool_slug_safe = _safe_slug(tool["name"])

        intro = f'<p>{tn} has a Nerq Trust Score of <strong>{_score_fmt(ts)}</strong> ({_grade_pill(tool.get("trust_grade"))}). {html.escape(_trunc(tool.get("description") or "", 200))}</p>'

        # Table
        trows = ""
        ld_items = []
        for i, alt in enumerate(alts, 1):
            aslug = _safe_slug(alt["name"])
            diff = _alt_diff(tool, alt)
            trows += f'<tr><td>{i}</td><td><a href="/is-{aslug}-safe">{html.escape(alt["name"])}</a></td><td>{_score_fmt(alt["score"])}</td><td>{_grade_pill(alt["grade"])}</td><td>{_stars_fmt(alt["stars"])}</td><td>{html.escape(diff)}</td></tr>'
            ld_items.append({"@type": "ListItem", "position": i, "name": alt["name"]})

        table = f'<table><thead><tr><th>#</th><th>Name</th><th>Trust</th><th>Grade</th><th>Stars</th><th>Key Difference</th></tr></thead><tbody>{trows}</tbody></table>'

        # Links
        link_rows = ""
        for alt in alts[:5]:
            aslug = _to_slug(alt["name"])
            cmp_a, cmp_b = sorted([tool_slug_safe, aslug])
            link_rows += f'<li><a href="/compare/{cmp_a}-vs-{cmp_b}">{tn} vs {html.escape(alt["name"])}</a></li>'
        links = f"<h2>Compare</h2><ul>{link_rows}</ul>" if link_rows else ""

        faq = _faq_section([
            (f"What are the best alternatives to {tn}?", f"The top alternatives based on Nerq Trust Score are listed above, all independently evaluated for security and reliability."),
            (f"Is it safe to switch from {tn}?", f"Check each alternative's safety report by clicking its name. Trust scores above 70 indicate strong reliability."),
            (f"How does Nerq rank {tn} alternatives?", "Alternatives are ranked by Trust Score v2, combining security, maintenance, documentation, and community signals."),
        ])

        jsonld = json.dumps({"@context": "https://schema.org", "@type": "ItemList", "name": f"{tool['name']} Alternatives", "numberOfItems": len(alts), "itemListElement": ld_items})

        _top_alt_name = html.escape(alts[0]["name"]) if alts else "alternatives"
        _top_alt_score = f"{alts[0]['score']:.0f}" if alts and alts[0].get("score") else "?"
        title = f"{tool['name']} Alternatives {YEAR} \u2014 Safer Options | Nerq"
        desc = f"Top {len(alts)} alternatives to {tool['name']} ({_score_fmt(ts)}). Best alternative: {_top_alt_name} ({_top_alt_score}/100). Ranked by Nerq Trust Score — independent security analysis."

        body = f"""{_breadcrumb(("/best", "best"), ("", f"{tn} Alternatives"))}
<h1>{tn} Alternatives</h1>
<p class="desc">Safer and better-maintained options, ranked by Nerq Trust Score. Updated {TODAY}.</p>
{intro}{table}{links}{faq}"""

        return HTMLResponse(_page(title, body, desc=desc, canonical=f"{SITE}/alternatives/{tool_slug}", jsonld=jsonld))

    # ── 4. Guide pages ──────────────────────────────────────
    @app.get("/guide/{tool_slug}", response_class=HTMLResponse)
    async def guide_page(tool_slug: str):
        with get_db_session() as session:
            tool = _find_agent(session, tool_slug)
            if not tool:
                return HTMLResponse(_page("Guide not found | Nerq",
                    f'{_breadcrumb(("", "not found"))}<h1>Guide not found</h1><p><a href="/discover">Search agents</a></p>'), status_code=404)

            # Get top 5 alternatives for section 5
            cat = tool.get("category")
            params: dict = {"tid": str(tool["id"])}
            cat_filter = ""
            if cat:
                cat_filter = "AND category = :cat"
                params["cat"] = cat
            alt_rows = session.execute(text(f"""
                SELECT name, trust_score_v2, trust_grade, stars
                FROM entity_lookup WHERE is_active = true AND id != CAST(:tid AS uuid) AND trust_score_v2 > 0 {cat_filter}
                ORDER BY COALESCE(trust_score_v2, 0) DESC LIMIT 5
            """), params).fetchall()
            alts = [dict(zip(["name", "score", "grade", "stars"], r)) for r in alt_rows]

        tn = html.escape(tool["name"])
        ts = tool.get("trust_score_v2")
        tg = tool.get("trust_grade")
        tool_slug_safe = _safe_slug(tool["name"])
        desc_text = html.escape(_trunc(tool.get("description") or "An AI tool indexed by Nerq.", 300))

        # Section 1: What is
        sec1 = f"""<h2>What is {tn}?</h2>
<p>{desc_text}</p>
<div class="stat-row">
<div class="stat-item"><div class="num">{_score_fmt(ts)}</div><div class="label">Trust Score</div></div>
<div class="stat-item"><div class="num">{_stars_fmt(tool.get("stars"))}</div><div class="label">Stars</div></div>
<div class="stat-item"><div class="num">{html.escape(tool.get("category") or "General")}</div><div class="label">Category</div></div>
</div>"""

        # Section 2: Is it safe?
        sec2 = f"""<h2>Is {tn} Safe?</h2>
<p>{tn} has a Nerq Trust Score of <strong>{_score_fmt(ts)}/100</strong> with grade {_grade_pill(tg)}.
This score is based on independent analysis of security practices, maintenance activity, and community trust signals.</p>
<p><a href="/is-{tool_slug_safe}-safe">View full {tn} safety report &rarr;</a></p>"""

        # Section 3: Getting started
        source = html.escape(tool.get("source") or "unknown")
        lang = html.escape(tool.get("language") or "Not specified")
        source_url = tool.get("source_url") or ""
        install_hint = f'<code>git clone {html.escape(source_url)}</code>' if "github" in source.lower() and source_url else f"See <a href='{html.escape(source_url)}'>source</a>" if source_url else "Check the official documentation"
        sec3 = f"""<h2>Getting Started</h2>
<table>
<tr><td style="font-weight:600">Source</td><td>{source}</td></tr>
<tr><td style="font-weight:600">Language</td><td>{lang}</td></tr>
<tr><td style="font-weight:600">Stars</td><td>{_stars_fmt(tool.get("stars"))}</td></tr>
<tr><td style="font-weight:600">Author</td><td>{html.escape(tool.get("author") or "Unknown")}</td></tr>
<tr><td style="font-weight:600">Install</td><td>{install_hint}</td></tr>
</table>"""

        # Section 4: Security considerations
        eu_risk = html.escape(tool.get("eu_risk_class") or "Not classified")
        sec4 = f"""<h2>Security Considerations</h2>
<table>
<tr><td style="font-weight:600">Security Score</td><td>{_score_fmt(tool.get("security_score"))}</td></tr>
<tr><td style="font-weight:600">Trust Grade</td><td>{_grade_pill(tg)}</td></tr>
<tr><td style="font-weight:600">EU AI Act Risk Class</td><td>{eu_risk}</td></tr>
<tr><td style="font-weight:600">Activity Score</td><td>{_score_fmt(tool.get("activity_score"))}</td></tr>
<tr><td style="font-weight:600">Documentation Score</td><td>{_score_fmt(tool.get("documentation_score"))}</td></tr>
</table>"""

        # Section 5: Alternatives
        alt_items = ""
        for alt in alts:
            aslug = _safe_slug(alt["name"])
            alt_items += f'<li><a href="/is-{aslug}-safe">{html.escape(alt["name"])}</a> \u2014 Trust Score {_score_fmt(alt["score"])}</li>'
        sec5 = f"""<h2>Alternatives to {tn}</h2>
<ul>{alt_items or '<li>No alternatives found in this category.</li>'}</ul>
<p><a href="/alternatives/{tool_slug}">View all {tn} alternatives &rarr;</a></p>"""

        # FAQ
        faq = _faq_section([
            (f"What is {tn} used for?", desc_text),
            (f"Is {tn} safe to use in production?", f"With a trust score of {_score_fmt(ts)} and grade {html.escape(tg or 'N/A')}, review the <a href='/is-{tool_slug_safe}-safe'>full safety report</a> before production use."),
            (f"How do I install {tn}?", f"Source: {source}. Language: {lang}. See the getting started section above."),
            (f"What are the best alternatives to {tn}?", f"Top alternatives by trust score are listed above. See <a href='/alternatives/{tool_slug}'>all alternatives</a>."),
            (f"Does {tn} comply with the EU AI Act?", f"EU risk classification: {eu_risk}. Check the security section for details."),
            (f"How popular is {tn}?", f"{tn} has {_stars_fmt(tool.get('stars'))} GitHub stars and a popularity score of {_score_fmt(tool.get('popularity_score'))}."),
        ])

        # JSON-LD HowTo
        jsonld = json.dumps({"@context": "https://schema.org", "@type": "HowTo", "name": f"{tool['name']} Guide", "description": f"Setup, security, and trust analysis for {tool['name']}", "step": [
            {"@type": "HowToStep", "name": "Understand the tool", "text": tool.get("description") or ""},
            {"@type": "HowToStep", "name": "Check safety", "text": f"Trust Score: {_score_fmt(ts)}"},
            {"@type": "HowToStep", "name": "Install", "text": f"Source: {tool.get('source', '')}"},
        ]})

        title = f"{tool['name']} Guide {YEAR} \u2014 Setup, Security & Trust Analysis | Nerq"
        desc = f"Complete guide to {tool['name']}: what it is, safety analysis, getting started, and alternatives."

        body = f"""{_breadcrumb(("/best", "tools"), ("", f"{tn} Guide"))}
<h1>{tn} Guide {YEAR}</h1>
<p class="desc">Setup, security analysis, and alternatives. Updated {TODAY}.</p>
{sec1}{sec2}{sec3}{sec4}{sec5}{faq}"""

        return HTMLResponse(_page(title, body, desc=desc, canonical=f"{SITE}/guide/{tool_slug}", jsonld=jsonld))

    # ── 5. Sitemaps ─────────────────────────────────────────
    def _sitemap_xml(urls: list[tuple[str, str]]) -> str:
        entries = ""
        for url, prio in urls:
            entries += f"<url><loc>{html.escape(url)}</loc><lastmod>{TODAY}</lastmod><priority>{prio}</priority></url>\n"
        return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{entries}</urlset>'

    @app.get("/sitemap-compare-pages.xml", response_class=Response)
    async def sitemap_compare():
        cached = _cached("sitemap:compare")
        if cached:
            return Response(cached, media_type="application/xml")

        # Load pre-generated pairs from comparison_generator.py
        import json as _json
        from pathlib import Path as _P
        pairs_file = _P(__file__).parent.parent / "data" / "comparison_pairs.json"
        if pairs_file.exists():
            with open(pairs_file) as f:
                pairs = _json.load(f)
            urls = [(f"{SITE}/compare/{p['slug']}", "0.9") for p in pairs]
        else:
            # Fallback: generate from top 200 agents
            with get_db_session() as session:
                rows = session.execute(text("""
                    SELECT name, category FROM entity_lookup
                    WHERE is_active = true AND trust_score_v2 IS NOT NULL
                    ORDER BY COALESCE(stars, 0) DESC LIMIT 200
                """)).fetchall()

            agents_list = [{"name": r[0], "cat": r[1]} for r in rows]
            urls = []
            seen = set()
            for i in range(len(agents_list)):
                for j in range(i + 1, len(agents_list)):
                    if len(seen) >= 5000:
                        break
                    sa, sb = sorted([_to_slug(agents_list[i]["name"]), _to_slug(agents_list[j]["name"])])
                    key = f"{sa}-vs-{sb}"
                    if key not in seen and sa != sb:
                        seen.add(key)
                        urls.append((f"{SITE}/compare/{key}", "0.9"))

        xml = _sitemap_xml(urls)
        _set_cache("sitemap:compare", xml)
        return Response(xml, media_type="application/xml")

    def _published_best_slugs():
        """Return /best/ slugs whose registries are ALL published."""
        try:
            from agentindex.quality_gate import get_publishable_registries
            pub = get_publishable_registries()
            if not pub:
                return list(BEST_CATEGORIES.keys())  # No gate state = publish all
            return [slug for slug, (_, regs, _) in BEST_CATEGORIES.items()
                    if not regs or any(r in pub for r in regs)]
        except Exception:
            return list(BEST_CATEGORIES.keys())

    @app.get("/sitemap-best.xml", response_class=Response)
    async def sitemap_best():
        slugs = _published_best_slugs()
        urls = [(f"{SITE}/best/{slug}", "0.7") for slug in slugs]
        return Response(_sitemap_xml(urls), media_type="application/xml")

    _BEST_LANGS = ["es","de","fr","ja","pt","id","cs","th","ro","tr","hi","ru","pl","it","ko","vi","nl","sv","zh","da","ar","no"]

    @app.get("/sitemap-best-localized.xml", response_class=Response)
    async def sitemap_best_localized():
        from datetime import date
        now = date.today().isoformat()
        slugs = _published_best_slugs()
        _per_chunk = 10000
        _total = len(slugs) * len(_BEST_LANGS)
        _chunks = max(1, -(-_total // _per_chunk))
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for c in range(_chunks):
            xml += f'  <sitemap><loc>{SITE}/sitemap-best-lang-{c}.xml</loc><lastmod>{now}</lastmod></sitemap>\n'
        xml += '</sitemapindex>'
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-best-lang-{chunk}.xml", response_class=Response)
    async def sitemap_best_lang_chunk(chunk: int):
        from datetime import date
        now = date.today().isoformat()
        _per_chunk = 10000
        slugs = _published_best_slugs()
        all_urls = []
        for slug in slugs:
            for lang in _BEST_LANGS:
                all_urls.append(f"{SITE}/{lang}/best/{slug}")
        start = chunk * _per_chunk
        batch = all_urls[start:start + _per_chunk]
        if not batch:
            return Response('<?xml version="1.0"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>', media_type="application/xml")
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for url in batch:
            xml += f'<url><loc>{url}</loc><lastmod>{now}</lastmod><priority>0.6</priority></url>\n'
        xml += '</urlset>'
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-alternatives.xml", response_class=Response)
    async def sitemap_alternatives():
        cached = _cached("sitemap:alts")
        if cached:
            return Response(cached, media_type="application/xml")
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT name FROM entity_lookup
                WHERE is_active = true AND trust_score_v2 IS NOT NULL
                ORDER BY COALESCE(stars, 0) DESC LIMIT 500
            """)).fetchall()
        urls = [(f"{SITE}/alternatives/{_to_slug(r[0])}", "0.7") for r in rows]
        xml = _sitemap_xml(urls)
        _set_cache("sitemap:alts", xml)
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-guides.xml", response_class=Response)
    async def sitemap_guides():
        cached = _cached("sitemap:guides")
        if cached:
            return Response(cached, media_type="application/xml")
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT name FROM entity_lookup
                WHERE is_active = true AND trust_score_v2 IS NOT NULL
                ORDER BY COALESCE(stars, 0) DESC LIMIT 200
            """)).fetchall()
        urls = [(f"{SITE}/guide/{_to_slug(r[0])}", "0.7") for r in rows]
        xml = _sitemap_xml(urls)
        _set_cache("sitemap:guides", xml)
        return Response(xml, media_type="application/xml")

    # ── 6. SEO page stats dashboard ─────────────────────────
    @app.get("/seo-page-stats", response_class=HTMLResponse)
    async def seo_page_stats():
        import sqlite3
        db_path = os.path.join(os.path.dirname(__file__), "..", "logs", "analytics.db")
        rows = []
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                cur = conn.execute("""
                    SELECT
                        CASE
                            WHEN path LIKE '/compare/%' THEN 'compare'
                            WHEN path LIKE '/best/%' THEN 'best-of'
                            WHEN path LIKE '/alternatives/%' THEN 'alternatives'
                            WHEN path LIKE '/guide/%' THEN 'guide'
                            WHEN path LIKE '/is-%-safe' THEN 'safety'
                            ELSE 'other'
                        END AS page_type,
                        COUNT(*) AS hits,
                        COUNT(DISTINCT path) AS unique_pages
                    FROM page_views
                    WHERE referrer LIKE '%google%' OR referrer LIKE '%bing%' OR referrer LIKE '%duckduckgo%'
                    GROUP BY page_type
                    ORDER BY hits DESC
                """)
                rows = cur.fetchall()
                conn.close()
            except Exception as e:
                logger.warning(f"Analytics DB error: {e}")

        trows = ""
        for r in rows:
            trows += f"<tr><td>{html.escape(str(r[0]))}</td><td>{r[1]}</td><td>{r[2]}</td></tr>"

        if not trows:
            trows = '<tr><td colspan="3" style="color:#6b7280">No analytics data available yet.</td></tr>'

        body = f"""{_breadcrumb(("", "SEO Page Stats"))}
<h1>SEO Page Stats</h1>
<p class="desc">Organic search traffic by page type.</p>
<table>
<thead><tr><th>Page Type</th><th>Organic Hits</th><th>Unique Pages</th></tr></thead>
<tbody>{trows}</tbody>
</table>"""

        return HTMLResponse(_page("SEO Page Stats | Nerq", body, robots="noindex, nofollow"))

    logger.info("Mounted programmatic SEO routes: /compare, /best, /alternatives, /guide, sitemaps")


# ── Helpers (outside mount) ─────────────────────────────────
def _alt_diff(tool: dict, alt: dict) -> str:
    """Generate a short key-difference string between tool and alternative."""
    parts = []
    ts_t = tool.get("trust_score_v2") or 0
    ts_a = alt.get("score") or 0
    if ts_a > ts_t:
        parts.append(f"Higher trust ({_score_fmt(ts_a)} vs {_score_fmt(ts_t)})")
    elif ts_a < ts_t:
        parts.append(f"Lower trust ({_score_fmt(ts_a)} vs {_score_fmt(ts_t)})")

    stars_t = tool.get("stars") or 0
    stars_a = alt.get("stars") or 0
    if stars_a > stars_t * 2:
        parts.append("Much larger community")
    elif stars_a > stars_t:
        parts.append("More stars")

    if alt.get("category") and alt["category"] != tool.get("category"):
        parts.append(f"Category: {alt['category']}")

    return "; ".join(parts) if parts else "Similar scope"
