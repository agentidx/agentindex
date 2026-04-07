#!/usr/bin/env python3
"""
Nerq Comparison Pages Module
==============================
Adds "Best MCP servers for X" and category listing pages.
Mount in discovery.py AFTER seo_pages but BEFORE static files.

Pages generated:
  GET /best-mcp-servers-for-{category}  — Top 10-20 MCP servers per category
  GET /mcp-servers                      — Main MCP directory page
  GET /sitemap-comparisons.xml          — Sitemap for all comparison pages

Categories derived from tags, domains, and description keywords.
Each page is AI-optimized with citable first paragraph and JSON-LD.

Usage in discovery.py:
    from agentindex.comparison_pages import mount_comparison_pages
    mount_comparison_pages(app)
"""

import logging
import json
from datetime import datetime
from fastapi import Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text
from agentindex.db.models import get_session

logger = logging.getLogger("nerq.comparisons")

SITE_URL = "https://nerq.ai"

# ================================================================
# CATEGORY DEFINITIONS
# ================================================================
# Each category: slug, display name, search query (SQL), description
CATEGORIES = [
    # --- Functional categories (from tags) ---
    {
        "slug": "databases",
        "title": "Database & SQL",
        "query_tags": ["database", "sql", "postgres", "postgresql", "mysql", "sqlite", "mongodb", "redis", "supabase", "prisma", "drizzle"],
        "query_desc": ["database", "SQL", "postgres", "mysql", "sqlite", "mongodb", "redis"],
        "desc": "MCP servers that connect AI agents to databases for querying, managing, and analyzing data.",
        "search_term": "best mcp servers for databases",
    },
    {
        "slug": "github",
        "title": "GitHub & Git",
        "query_tags": ["github", "git", "gitlab", "bitbucket", "repository", "version-control"],
        "query_desc": ["GitHub", "git", "repository", "pull request", "commit"],
        "desc": "MCP servers for interacting with GitHub repositories, pull requests, issues, and code reviews.",
        "search_term": "best mcp servers for github",
    },
    {
        "slug": "browser-automation",
        "title": "Browser & Web Automation",
        "query_tags": ["browser", "puppeteer", "playwright", "selenium", "web-scraping", "chrome"],
        "query_desc": ["browser", "web scraping", "puppeteer", "playwright", "chrome", "web automation"],
        "desc": "MCP servers that automate web browsers for scraping, testing, and interacting with web pages.",
        "search_term": "best mcp servers for browser automation",
    },
    {
        "slug": "search",
        "title": "Web Search & RAG",
        "query_tags": ["search", "rag", "semantic-search", "web-search", "retrieval", "embeddings", "knowledge-base"],
        "query_desc": ["search", "RAG", "retrieval", "semantic search", "web search"],
        "desc": "MCP servers for web search, retrieval-augmented generation, and knowledge base queries.",
        "search_term": "best mcp servers for search and RAG",
    },
    {
        "slug": "file-management",
        "title": "File System & Documents",
        "query_tags": ["filesystem", "file", "files", "documents", "pdf", "excel", "csv", "storage", "s3"],
        "query_desc": ["file system", "file management", "PDF", "documents", "Excel", "CSV", "S3"],
        "desc": "MCP servers for reading, writing, and managing files, documents, and cloud storage.",
        "search_term": "best mcp servers for file management",
    },
    {
        "slug": "api-integration",
        "title": "API & Workflow Integration",
        "query_tags": ["api", "rest", "graphql", "webhook", "integration", "n8n", "zapier"],
        "query_desc": ["API", "REST", "webhook", "integration", "workflow", "n8n", "zapier"],
        "desc": "MCP servers for connecting to external APIs, webhooks, and workflow automation platforms.",
        "search_term": "best mcp servers for API integration",
    },
    {
        "slug": "code-development",
        "title": "Code & Development Tools",
        "query_tags": ["developer-tools", "code", "coding", "ide", "linting", "testing", "debugging", "ci-cd"],
        "query_desc": ["code", "development", "IDE", "debugging", "linting", "testing", "CI/CD"],
        "desc": "MCP servers that help with code generation, testing, debugging, and development workflows.",
        "search_term": "best mcp servers for coding",
    },
    {
        "slug": "communication",
        "title": "Slack, Email & Messaging",
        "query_tags": ["slack", "email", "discord", "telegram", "whatsapp", "teams", "messaging", "chat"],
        "query_desc": ["Slack", "email", "Discord", "Telegram", "WhatsApp", "Teams", "messaging"],
        "desc": "MCP servers for sending messages, managing channels, and automating communication platforms.",
        "search_term": "best mcp servers for slack and email",
    },
    {
        "slug": "image-generation",
        "title": "Image Generation & Media",
        "query_tags": ["image-generation", "image", "media", "video", "audio", "stable-diffusion", "dalle", "midjourney"],
        "query_desc": ["image generation", "image", "video", "audio", "media", "stable diffusion"],
        "desc": "MCP servers for generating, editing, and processing images, video, and audio content.",
        "search_term": "best mcp servers for image generation",
    },
    {
        "slug": "memory-context",
        "title": "Memory & Context Management",
        "query_tags": ["memory", "context", "knowledge-base", "vector", "vector-store", "pinecone", "chroma"],
        "query_desc": ["memory", "context", "knowledge base", "vector store", "long-term memory"],
        "desc": "MCP servers for persistent memory, context management, and vector storage for AI agents.",
        "search_term": "best mcp servers for memory and context",
    },
    {
        "slug": "security",
        "title": "Security & Authentication",
        "query_tags": ["security", "auth", "authentication", "oauth", "encryption", "vault"],
        "query_desc": ["security", "authentication", "OAuth", "encryption", "vault", "secrets"],
        "desc": "MCP servers for security scanning, authentication, secrets management, and access control.",
        "search_term": "best mcp servers for security",
    },
    {
        "slug": "automation",
        "title": "Task Automation & Workflows",
        "query_tags": ["automation", "workflow", "cron", "scheduler", "task"],
        "query_desc": ["automation", "workflow", "task management", "scheduling", "cron"],
        "desc": "MCP servers for automating tasks, scheduling jobs, and orchestrating complex workflows.",
        "search_term": "best mcp servers for automation",
    },
    {
        "slug": "monitoring",
        "title": "Monitoring & Observability",
        "query_tags": ["monitoring", "logging", "observability", "metrics", "datadog", "grafana", "prometheus"],
        "query_desc": ["monitoring", "logging", "observability", "metrics", "Datadog", "Grafana"],
        "desc": "MCP servers for monitoring systems, collecting metrics, and managing logs and alerts.",
        "search_term": "best mcp servers for monitoring",
    },
    {
        "slug": "cloud-infrastructure",
        "title": "Cloud & Infrastructure",
        "query_tags": ["aws", "azure", "gcp", "cloud", "docker", "kubernetes", "terraform", "infrastructure"],
        "query_desc": ["AWS", "Azure", "GCP", "cloud", "Docker", "Kubernetes", "Terraform", "infrastructure"],
        "desc": "MCP servers for managing cloud infrastructure, containers, and deployment pipelines.",
        "search_term": "best mcp servers for cloud infrastructure",
    },
    {
        "slug": "data-analysis",
        "title": "Data Analysis & Visualization",
        "query_tags": ["data", "analytics", "visualization", "charts", "pandas", "notebook", "jupyter"],
        "query_desc": ["data analysis", "visualization", "analytics", "charts", "pandas", "notebook"],
        "desc": "MCP servers for analyzing data, creating visualizations, and running data science workflows.",
        "search_term": "best mcp servers for data analysis",
    },
    # --- Industry verticals ---
    {
        "slug": "finance",
        "title": "Finance & Fintech",
        "query_tags": ["finance", "fintech", "trading", "banking", "payment", "stripe", "crypto", "stock"],
        "query_desc": ["finance", "fintech", "trading", "banking", "payment", "stock", "crypto"],
        "desc": "MCP servers for financial data, trading, payments, and fintech integrations.",
        "search_term": "best mcp servers for finance",
    },
    {
        "slug": "healthcare",
        "title": "Healthcare & Medical",
        "query_tags": ["healthcare", "medical", "health", "clinical", "fhir", "hl7"],
        "query_desc": ["healthcare", "medical", "health", "clinical", "FHIR", "patient"],
        "desc": "MCP servers for healthcare data, medical records, clinical workflows, and health compliance.",
        "search_term": "best mcp servers for healthcare",
    },
    {
        "slug": "education",
        "title": "Education & Learning",
        "query_tags": ["education", "learning", "teaching", "school", "academic", "lms"],
        "query_desc": ["education", "learning", "teaching", "academic", "LMS", "course"],
        "desc": "MCP servers for educational tools, learning management, and academic research.",
        "search_term": "best mcp servers for education",
    },
    {
        "slug": "legal",
        "title": "Legal & Compliance",
        "query_tags": ["legal", "compliance", "contract", "law", "regulation", "gdpr"],
        "query_desc": ["legal", "compliance", "contract", "law", "regulation", "GDPR"],
        "desc": "MCP servers for legal research, contract analysis, compliance checking, and regulatory tools.",
        "search_term": "best mcp servers for legal",
    },
    # --- Client-specific ---
    {
        "slug": "claude-desktop",
        "title": "Claude Desktop",
        "query_tags": ["claude-desktop", "claude", "anthropic"],
        "query_desc": ["Claude Desktop"],
        "desc": "The best MCP servers optimized for use with Claude Desktop, Anthropic's AI assistant.",
        "search_term": "best mcp servers for claude desktop",
    },
    {
        "slug": "cursor",
        "title": "Cursor IDE",
        "query_tags": ["cursor", "cursor-ide"],
        "query_desc": ["Cursor", "cursor IDE"],
        "desc": "Top MCP servers for Cursor, the AI-first code editor, ranked by trust score and compliance.",
        "search_term": "best mcp servers for cursor",
    },
    {
        "slug": "vscode",
        "title": "VS Code & Copilot",
        "query_tags": ["vscode", "vs-code", "copilot", "visual-studio-code"],
        "query_desc": ["VS Code", "Visual Studio Code", "Copilot"],
        "desc": "MCP servers that work with Visual Studio Code and GitHub Copilot for AI-assisted development.",
        "search_term": "best mcp servers for vs code",
    },
    # --- Tool-specific categories ---
    {
        "slug": "docker",
        "title": "Docker & Containers",
        "query_tags": ["docker", "container", "dockerfile", "compose", "podman"],
        "query_desc": ["Docker", "container", "Dockerfile", "docker-compose", "Podman"],
        "desc": "MCP servers for managing Docker containers, images, and container orchestration.",
        "search_term": "best mcp servers for docker",
    },
    {
        "slug": "kubernetes",
        "title": "Kubernetes & K8s",
        "query_tags": ["kubernetes", "k8s", "kubectl", "helm", "argo"],
        "query_desc": ["Kubernetes", "k8s", "kubectl", "Helm", "cluster"],
        "desc": "MCP servers for managing Kubernetes clusters, deployments, and cloud-native workloads.",
        "search_term": "best mcp servers for kubernetes",
    },
    {
        "slug": "slack",
        "title": "Slack Integration",
        "query_tags": ["slack", "slack-bot", "slack-api"],
        "query_desc": ["Slack", "Slack bot", "Slack API", "Slack integration"],
        "desc": "MCP servers for Slack: send messages, manage channels, automate workflows in Slack workspaces.",
        "search_term": "best mcp servers for slack",
    },
    {
        "slug": "email",
        "title": "Email & SMTP",
        "query_tags": ["email", "smtp", "imap", "sendgrid", "mailgun", "gmail"],
        "query_desc": ["email", "SMTP", "IMAP", "Gmail", "SendGrid", "Mailgun"],
        "desc": "MCP servers for sending, reading, and managing email through various providers.",
        "search_term": "best mcp servers for email",
    },
    {
        "slug": "notion",
        "title": "Notion & Wikis",
        "query_tags": ["notion", "wiki", "confluence", "knowledge-management"],
        "query_desc": ["Notion", "wiki", "Confluence", "knowledge management"],
        "desc": "MCP servers for interacting with Notion databases, pages, and other wiki platforms.",
        "search_term": "best mcp servers for notion",
    },
    {
        "slug": "jira",
        "title": "Jira & Issue Tracking",
        "query_tags": ["jira", "linear", "asana", "trello", "issue-tracking"],
        "query_desc": ["Jira", "Linear", "Asana", "Trello", "issue tracking", "project management"],
        "desc": "MCP servers for managing issues, tasks, and sprints in Jira, Linear, and other trackers.",
        "search_term": "best mcp servers for jira",
    },
    {
        "slug": "testing",
        "title": "Testing & QA",
        "query_tags": ["testing", "test", "qa", "jest", "pytest", "playwright", "cypress"],
        "query_desc": ["testing", "test automation", "QA", "Jest", "pytest", "Cypress", "Playwright"],
        "desc": "MCP servers for automated testing, quality assurance, and test management.",
        "search_term": "best mcp servers for testing",
    },
    {
        "slug": "documentation",
        "title": "Documentation & Docs",
        "query_tags": ["documentation", "docs", "readme", "docusaurus", "mkdocs", "swagger", "openapi"],
        "query_desc": ["documentation", "docs", "README", "Swagger", "OpenAPI", "API docs"],
        "desc": "MCP servers for generating, managing, and serving technical documentation.",
        "search_term": "best mcp servers for documentation",
    },
    {
        "slug": "pdf",
        "title": "PDF & Document Processing",
        "query_tags": ["pdf", "document", "ocr", "docx", "word"],
        "query_desc": ["PDF", "document processing", "OCR", "Word", "docx"],
        "desc": "MCP servers for reading, creating, and processing PDF files and other document formats.",
        "search_term": "best mcp servers for pdf",
    },
    {
        "slug": "spreadsheets",
        "title": "Spreadsheets & CSV",
        "query_tags": ["spreadsheet", "excel", "csv", "google-sheets", "sheets"],
        "query_desc": ["spreadsheet", "Excel", "CSV", "Google Sheets"],
        "desc": "MCP servers for reading, writing, and analyzing spreadsheet data in Excel, CSV, and Google Sheets.",
        "search_term": "best mcp servers for spreadsheets",
    },
    {
        "slug": "vector-database",
        "title": "Vector Databases",
        "query_tags": ["vector", "vector-store", "vector-database", "pinecone", "chroma", "weaviate", "qdrant", "milvus"],
        "query_desc": ["vector database", "vector store", "Pinecone", "Chroma", "Weaviate", "Qdrant", "Milvus"],
        "desc": "MCP servers for vector databases: store, search, and manage embeddings for RAG and semantic search.",
        "search_term": "best mcp servers for vector databases",
    },
    {
        "slug": "llm",
        "title": "LLM & Model Serving",
        "query_tags": ["llm", "openai", "gpt", "claude", "gemini", "llama", "model-serving", "inference"],
        "query_desc": ["LLM", "OpenAI", "GPT", "Claude", "Gemini", "Llama", "model serving", "inference"],
        "desc": "MCP servers for interacting with large language models, model serving, and AI inference APIs.",
        "search_term": "best mcp servers for llm",
    },
    {
        "slug": "rag",
        "title": "RAG & Knowledge Retrieval",
        "query_tags": ["rag", "retrieval-augmented-generation", "knowledge-retrieval", "embeddings", "chunking"],
        "query_desc": ["RAG", "retrieval augmented generation", "knowledge retrieval", "embeddings"],
        "desc": "MCP servers for building RAG pipelines: chunking, embedding, retrieval, and augmented generation.",
        "search_term": "best mcp servers for rag",
    },
    {
        "slug": "agents",
        "title": "AI Agents & Orchestration",
        "query_tags": ["agent", "agents", "orchestration", "multi-agent", "langchain", "langgraph", "crewai", "autogpt"],
        "query_desc": ["AI agent", "agent orchestration", "multi-agent", "LangChain", "CrewAI", "AutoGPT"],
        "desc": "MCP servers for building, orchestrating, and managing AI agent systems.",
        "search_term": "best mcp servers for ai agents",
    },
    {
        "slug": "browser",
        "title": "Browser Control",
        "query_tags": ["browser", "chrome", "firefox", "puppeteer", "playwright", "headless"],
        "query_desc": ["browser control", "Chrome", "Puppeteer", "Playwright", "headless browser"],
        "desc": "MCP servers for controlling web browsers: navigate, click, scrape, and automate browser sessions.",
        "search_term": "best mcp servers for browser control",
    },
    {
        "slug": "terminal",
        "title": "Terminal & Shell",
        "query_tags": ["terminal", "shell", "cli", "bash", "ssh", "command-line"],
        "query_desc": ["terminal", "shell", "CLI", "bash", "SSH", "command line"],
        "desc": "MCP servers for executing shell commands, managing terminal sessions, and SSH connections.",
        "search_term": "best mcp servers for terminal",
    },
    {
        "slug": "aws",
        "title": "AWS & Amazon Cloud",
        "query_tags": ["aws", "amazon", "s3", "lambda", "ec2", "cloudformation", "bedrock"],
        "query_desc": ["AWS", "Amazon", "S3", "Lambda", "EC2", "CloudFormation", "Bedrock"],
        "desc": "MCP servers for managing AWS services: S3, Lambda, EC2, and other Amazon cloud resources.",
        "search_term": "best mcp servers for aws",
    },
    {
        "slug": "gcp",
        "title": "Google Cloud Platform",
        "query_tags": ["gcp", "google-cloud", "bigquery", "vertex-ai", "cloud-run", "firebase"],
        "query_desc": ["Google Cloud", "GCP", "BigQuery", "Vertex AI", "Cloud Run", "Firebase"],
        "desc": "MCP servers for Google Cloud Platform: BigQuery, Vertex AI, Firebase, and other GCP services.",
        "search_term": "best mcp servers for google cloud",
    },
    {
        "slug": "azure",
        "title": "Microsoft Azure",
        "query_tags": ["azure", "microsoft-azure", "azure-devops", "azure-functions"],
        "query_desc": ["Azure", "Microsoft Azure", "Azure DevOps", "Azure Functions"],
        "desc": "MCP servers for Microsoft Azure: compute, storage, DevOps, and other Azure cloud services.",
        "search_term": "best mcp servers for azure",
    },
    {
        "slug": "supabase",
        "title": "Supabase",
        "query_tags": ["supabase", "supabase-auth", "supabase-storage"],
        "query_desc": ["Supabase", "Supabase auth", "Supabase storage", "Supabase edge"],
        "desc": "MCP servers for Supabase: database, auth, storage, and edge functions.",
        "search_term": "best mcp servers for supabase",
    },
    {
        "slug": "firebase",
        "title": "Firebase",
        "query_tags": ["firebase", "firestore", "firebase-auth", "firebase-hosting"],
        "query_desc": ["Firebase", "Firestore", "Firebase Auth", "Firebase Hosting"],
        "desc": "MCP servers for Firebase: Firestore database, authentication, hosting, and cloud functions.",
        "search_term": "best mcp servers for firebase",
    },
    {
        "slug": "postgres",
        "title": "PostgreSQL",
        "query_tags": ["postgres", "postgresql", "pg", "psql"],
        "query_desc": ["PostgreSQL", "Postgres", "psql", "pg_"],
        "desc": "MCP servers specifically for PostgreSQL: queries, migrations, monitoring, and administration.",
        "search_term": "best mcp servers for postgres",
    },
    {
        "slug": "mysql",
        "title": "MySQL & MariaDB",
        "query_tags": ["mysql", "mariadb"],
        "query_desc": ["MySQL", "MariaDB"],
        "desc": "MCP servers for MySQL and MariaDB: database queries, management, and administration.",
        "search_term": "best mcp servers for mysql",
    },
    {
        "slug": "mongodb",
        "title": "MongoDB",
        "query_tags": ["mongodb", "mongo", "mongoose"],
        "query_desc": ["MongoDB", "Mongo", "Mongoose", "NoSQL"],
        "desc": "MCP servers for MongoDB: document queries, aggregation pipelines, and database management.",
        "search_term": "best mcp servers for mongodb",
    },
    {
        "slug": "redis",
        "title": "Redis & Caching",
        "query_tags": ["redis", "cache", "caching", "memcached"],
        "query_desc": ["Redis", "cache", "caching", "Memcached", "key-value"],
        "desc": "MCP servers for Redis and caching: key-value storage, pub/sub, and cache management.",
        "search_term": "best mcp servers for redis",
    },
    {
        "slug": "graphql",
        "title": "GraphQL",
        "query_tags": ["graphql", "apollo", "hasura"],
        "query_desc": ["GraphQL", "Apollo", "Hasura", "schema"],
        "desc": "MCP servers for GraphQL APIs: queries, mutations, schema introspection, and API integration.",
        "search_term": "best mcp servers for graphql",
    },
    {
        "slug": "rest-api",
        "title": "REST API",
        "query_tags": ["rest", "rest-api", "openapi", "swagger", "http-client"],
        "query_desc": ["REST API", "OpenAPI", "Swagger", "HTTP client", "API endpoint"],
        "desc": "MCP servers for consuming and managing REST APIs: HTTP requests, auth, and API testing.",
        "search_term": "best mcp servers for rest api",
    },
    {
        "slug": "websocket",
        "title": "WebSocket & Realtime",
        "query_tags": ["websocket", "realtime", "socket", "socket-io", "sse"],
        "query_desc": ["WebSocket", "realtime", "Socket.io", "SSE", "streaming"],
        "desc": "MCP servers for WebSocket connections, realtime data, and server-sent events.",
        "search_term": "best mcp servers for websocket",
    },
]


def mount_comparison_pages(app):
    """Mount all comparison page routes onto the FastAPI app."""

    # ================================================================
    # MCP DIRECTORY — Main listing page
    # ================================================================
    @app.get("/mcp-servers", response_class=HTMLResponse)
    def mcp_directory():
        session = get_session()
        try:
            total_mcp = session.execute(text(
                "SELECT COUNT(*) FROM entity_lookup WHERE is_active = true AND agent_type = 'mcp_server'"
            )).scalar() or 0

            # Get top MCP servers — filter to trusted/caution only (trust >= 35)
            top = session.execute(text("""
                SELECT id, name, stars, description,
                       trust_score_v2, trust_grade
                FROM entity_lookup WHERE is_active = true AND agent_type = 'mcp_server'
                AND trust_score_v2 >= 35
                ORDER BY trust_score_v2 DESC NULLS LAST, stars DESC NULLS LAST LIMIT 20
            """)).fetchall()
            top_list = [dict(zip(['id','name','stars','desc','trust_score','trust_grade'], r)) for r in top]

            html = _render_directory_page(total_mcp, top_list)
            return HTMLResponse(content=html)
        finally:
            session.close()

    # ================================================================
    # CATEGORY PAGES — "Best MCP servers for {category}"
    # ================================================================
    @app.get("/best-mcp-servers-for-{category}", response_class=HTMLResponse)
    def category_page(category: str):
        # Find category config
        cat = None
        for c in CATEGORIES:
            if c["slug"] == category:
                cat = c
                break
        if not cat:
            return HTMLResponse(status_code=404, content="<h1>Category not found</h1>")

        session = get_session()
        try:
            # Build query: match tags OR description keywords
            tag_conditions = " OR ".join([f"'{t}' = ANY(tags)" for t in cat["query_tags"]])
            desc_conditions = " OR ".join([f"description ILIKE '%{d}%'" for d in cat["query_desc"]])

            # domains/tags not in entity_lookup — keep on agents with guards
            session.execute(text("SET LOCAL work_mem = '2MB'; SET LOCAL statement_timeout = '5s'"))
            query = f"""
                SELECT id, name, stars, downloads,
                       description, author, license, source_url, domains, tags,
                       trust_score_v2, trust_grade
                FROM agents
                WHERE is_active = true
                AND agent_type = 'mcp_server'
                AND trust_score_v2 >= 35
                AND ({tag_conditions} OR {desc_conditions})
                ORDER BY trust_score_v2 DESC NULLS LAST, stars DESC NULLS LAST
                LIMIT 20
            """
            rows = session.execute(text(query)).fetchall()
            agents = [dict(zip(['id','name','stars','downloads',
                               'desc','author','license','url','domains','tags',
                               'trust_score','trust_grade'], r))
                      for r in rows]

            total_in_cat = session.execute(text(f"""
                SELECT COUNT(*) FROM agents
                WHERE is_active = true AND agent_type = 'mcp_server'
                AND ({tag_conditions} OR {desc_conditions})
            """)).scalar()

            html = _render_category_page(cat, agents, total_in_cat)
            return HTMLResponse(content=html)
        finally:
            session.close()

    # ================================================================
    # COMPARISON SITEMAP
    # ================================================================
    @app.get("/sitemap-comparisons.xml", response_class=Response)
    def sitemap_comparisons():
        now = datetime.utcnow().strftime("%Y-%m-%d")
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

        # MCP directory
        xml += f'  <url><loc>{SITE_URL}/mcp-servers</loc><lastmod>{now}</lastmod><changefreq>daily</changefreq><priority>0.9</priority></url>\n'

        # Category pages
        for cat in CATEGORIES:
            xml += f'  <url><loc>{SITE_URL}/best-mcp-servers-for-{cat["slug"]}</loc><lastmod>{now}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>\n'

        xml += '</urlset>'
        return Response(content=xml, media_type="application/xml")

    logger.info(f"Comparison pages mounted: /mcp-servers, {len(CATEGORIES)} category pages")


# ================================================================
# HTML RENDERING
# ================================================================

def _risk_color(risk):
    return {'unacceptable':'#dc2626','high':'#ea580c','limited':'#ca8a04','minimal':'#16a34a'}.get(risk,'#6b7280')

def _risk_label(risk):
    return {'unacceptable':'PROHIBITED','high':'HIGH RISK','limited':'LIMITED','minimal':'MINIMAL'}.get(risk, (risk or 'N/A').upper())

def _esc(t):
    if not t: return ''
    return str(t).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def _score_display(score):
    if score is None:
        return '<span style="color:#6b7280">Pending</span>'
    color = '#16a34a' if score >= 80 else '#ca8a04' if score >= 50 else '#dc2626'
    return f'<strong style="color:{color}">{score}/100</strong>'

def _trust_display_html(agent):
    """Show trust grade + score badge for tables."""
    ts = agent.get('trust_score')
    tg = agent.get('trust_grade')
    if ts is None:
        return '<span style="color:#6b7280">&mdash;</span>'
    colors = {'A+': '#22c55e', 'A': '#22c55e', 'B': '#3b82f6', 'C': '#eab308', 'D': '#f97316', 'E': '#ef4444', 'F': '#ef4444'}
    c = colors.get(tg, '#6b7280')
    return f'<span style="background:{c}22;color:{c};padding:2px 8px;border-radius:4px;font-weight:700;font-size:13px">{tg}</span> <span style="color:#6b7280;font-size:12px">{ts:.0f}</span>'


def _render_directory_page(total_mcp, top_agents):
    now = datetime.utcnow().strftime("%B %d, %Y")
    
    # Category links
    cat_links = ""
    for cat in CATEGORIES:
        cat_links += f'<a href="/best-mcp-servers-for-{cat["slug"]}" style="display:inline-block;padding:8px 16px;margin:4px;background:#f5f5f5;border:1px solid #e5e7eb;text-decoration:none;color:#1a1a1a;font-size:14px">{cat["title"]}</a>\n'

    # Top agents table
    rows = ""
    for i, a in enumerate(top_agents):
        rows += f"""<tr>
<td style="font-weight:600">{i+1}</td>
<td><a href="/agent/{a['id']}" style="color:#0d9488;text-decoration:none;font-weight:500">{_esc(a['name'][:50])}</a></td>
<td>{a['stars'] or 0:,}</td>
<td>{_trust_display_html(a)}</td>
<td style="font-size:13px;color:#6b7280">{_esc((a['desc'] or '')[:100])}</td>
</tr>"""

    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "MCP Server Directory — All Model Context Protocol Servers",
        "description": f"Complete directory of {total_mcp:,} MCP servers rated by Nerq Trust Score (security, compliance, maintenance, popularity, ecosystem) across 52 jurisdictions.",
        "url": f"{SITE_URL}/mcp-servers",
        "provider": {"@type": "Organization", "name": "Nerq", "url": SITE_URL},
        "about": {"@type": "SoftwareApplication", "applicationCategory": "MCP Server"},
        "numberOfItems": total_mcp
    })

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MCP Server Directory — {total_mcp:,} Model Context Protocol Servers | Nerq</title>
<meta name="description" content="Complete directory of {total_mcp:,} MCP servers ranked by Nerq Trust Score — security, compliance, maintenance, popularity, and ecosystem analysis across 52 jurisdictions.">
<link rel="canonical" href="{SITE_URL}/mcp-servers">
<script type="application/ld+json">{schema}</script>
{_common_styles()}
</head>
<body>
{_header()}
<div class="container">

<div class="section" style="border-left:3px solid #0d9488;margin-top:16px">
<p style="font-size:16px;line-height:1.7">Nerq indexes <strong>{total_mcp:,} MCP (Model Context Protocol) servers</strong> — the largest MCP directory in the world. Each server is rated with a Nerq Trust Score (0–100) based on security, compliance, maintenance, popularity, and ecosystem analysis. Browse by category below or search the full directory.</p>
<small style="color:#6b7280">Last updated: {now} | Data from Nerq's index of {total_mcp:,} MCP servers</small>
</div>

<div class="section">
<h2>Browse by Category</h2>
<div style="display:flex;flex-wrap:wrap;gap:4px">{cat_links}</div>
</div>

<div class="section">
<h2>Top {len(top_agents)} MCP Servers by Trust Score</h2>
<div style="overflow-x:auto">
<table>
<thead><tr><th>#</th><th>Name</th><th>Stars</th><th>Trust</th><th>Description</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</div>
</div>

</div>
{_footer()}
</body></html>"""


def _render_category_page(cat, agents, total_in_cat):
    now = datetime.utcnow().strftime("%B %d, %Y")
    slug = cat["slug"]
    title = cat["title"]
    desc = cat["desc"]
    n = len(agents)

    # Table rows
    rows = ""
    for i, a in enumerate(agents):
        rows += f"""<tr>
<td style="font-weight:600">{i+1}</td>
<td><a href="/agent/{a['id']}" style="color:#0d9488;text-decoration:none;font-weight:500">{_esc(a['name'][:50])}</a></td>
<td>{a['stars'] or 0:,}</td>
<td>{_trust_display_html(a)}</td>
<td style="font-size:13px">{_esc(a['author'] or 'Unknown')}</td>
<td style="font-size:13px">{_esc(a['license'] or 'N/A')}</td>
<td style="font-size:13px;color:#6b7280;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{_esc((a['desc'] or '')[:100])}</td>
</tr>"""

    # Best agent for citable summary
    best = agents[0] if agents else None
    best_text = ""
    if best:
        ts = best.get('trust_score')
        ts_text = f"a trust score of {ts:.0f}/100" if ts else "pending trust assessment"
        best_text = (f"The top-ranked MCP server for {title.lower()} is "
                    f"<strong>{_esc(best['name'])}</strong> with {best['stars'] or 0:,} stars"
                    f" and {ts_text}.")

    # Related categories
    related = ""
    for c in CATEGORIES:
        if c["slug"] != slug:
            related += f'<a href="/best-mcp-servers-for-{c["slug"]}" style="display:inline-block;padding:6px 12px;margin:3px;background:#f5f5f5;border:1px solid #e5e7eb;text-decoration:none;color:#1a1a1a;font-size:13px">{c["title"]}</a>\n'

    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"Best MCP Servers for {title}",
        "description": f"{n} MCP servers for {title.lower()} ranked by stars and compliance score.",
        "url": f"{SITE_URL}/best-mcp-servers-for-{slug}",
        "numberOfItems": n,
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i+1,
                "item": {
                    "@type": "SoftwareApplication",
                    "name": a["name"],
                    "url": f"{SITE_URL}/agent/{a['id']}",
                }
            }
            for i, a in enumerate(agents[:10])
        ],
        "provider": {"@type": "Organization", "name": "Nerq", "url": SITE_URL},
    })

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Best MCP Servers for {title} ({datetime.utcnow().strftime("%B %Y")}) — Top {n} Ranked | Nerq</title>
<meta name="description" content="Top {n} MCP servers for {title.lower()} ranked by stars, compliance score (52 jurisdictions), and trust. Updated {now}.">
<link rel="canonical" href="{SITE_URL}/best-mcp-servers-for-{slug}">
<meta property="og:title" content="Best MCP Servers for {title} — Nerq">
<meta property="og:description" content="Top {n} MCP servers for {title.lower()} with compliance data across 52 jurisdictions.">
<script type="application/ld+json">{schema}</script>
{_common_styles()}
</head>
<body>
{_header()}
<div class="container">

<div class="breadcrumb">
<a href="/" style="font-weight:700;color:#0d9488;text-decoration:none">nerq</a> &rsaquo; <a href="/mcp-servers">MCP Servers</a> &rsaquo; <strong>{title}</strong>
</div>

<!-- AI-Citable Summary -->
<div class="section" style="border-left:3px solid #0d9488;margin-top:16px">
<h1 style="font-size:22px;margin-bottom:12px">Best MCP Servers for {title} ({datetime.utcnow().strftime("%B %Y")})</h1>
<p style="font-size:16px;line-height:1.7">Nerq found <strong>{total_in_cat:,} MCP servers</strong> for {title.lower()}, ranked below by GitHub stars and weighted compliance score across 52 global AI jurisdictions. {best_text} {desc}</p>
<small style="color:#6b7280">Last updated: {now} | {total_in_cat:,} servers in this category | Data from Nerq</small>
</div>

<!-- Ranking Table -->
<div class="section">
<h2>Top {n} MCP Servers for {title}</h2>
<div style="overflow-x:auto">
<table>
<thead><tr><th>#</th><th>Name</th><th>Stars</th><th>Trust</th><th>Author</th><th>License</th><th>Description</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</div>
</div>

<!-- Related Categories -->
<div class="section">
<h2>Other MCP Server Categories</h2>
<div style="display:flex;flex-wrap:wrap;gap:4px">{related}</div>
</div>

<!-- SEO Content -->
<div class="section">
<h2>About MCP Servers for {title}</h2>
<p style="font-size:14px;color:#6b7280;line-height:1.7">{desc} 
Nerq tracks {total_in_cat:,} MCP servers in the {title.lower()} category, 
each assessed against 52 global AI regulations including the EU AI Act, 
US state AI laws (California SB53, Colorado SB205), UK AI Bill, and more. 
Compliance scores are weighted by jurisdiction penalty severity — 
jurisdictions with higher fines (like the EU AI Act at up to €35M) have 
more impact on the score than voluntary frameworks.</p>
<p style="font-size:14px;color:#6b7280;margin-top:12px">
All data is updated regularly. Use the <a href="/docs" style="color:#0d9488">Nerq API</a> 
or <a href="/mcp-servers" style="color:#0d9488">MCP Server</a> for programmatic access.</p>
</div>

</div>
{_footer()}
</body></html>"""


def _common_styles():
    from agentindex.nerq_design import NERQ_CSS
    return f"<style>{NERQ_CSS}</style>"


def _header():
    from agentindex.nerq_design import NERQ_NAV
    return NERQ_NAV


def _footer():
    from agentindex.nerq_design import NERQ_FOOTER
    return NERQ_FOOTER
