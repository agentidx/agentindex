"""
Pricing Crawler — Wednesdays 03:00
====================================
Maintains structured pricing data for ~100 commercial AI agents/tools.
Stores plans, pricing models, rate limits, and estimated token costs.

Usage:
    python -m agentindex.crawlers.pricing_crawler
"""

import json
import logging
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import httpx
from sqlalchemy.sql import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [pricing-crawler] %(message)s",
)
logger = logging.getLogger("pricing-crawler")

SQLITE_DB = Path(__file__).parent.parent / "crypto" / "crypto_trust.db"

# ── Curated pricing data ──────────────────────────────────────
# Hard-coded initial data for top agents with known pricing.
# pricing_model: per_seat, per_call, per_token, flat_rate, usage_based, open_source_free

CURATED_PRICING = [
    # ── Coding Agents ──
    {"agent": "Cursor", "plans": [
        {"name": "Hobby", "monthly": 0, "annual_monthly": 0, "limits": "2000 completions/month, 50 slow premium requests/month", "features": "Basic code completion"},
        {"name": "Pro", "monthly": 20, "annual_monthly": 20, "limits": "Unlimited completions, 500 fast premium requests/month", "features": "GPT-4, Claude access, fast completions"},
        {"name": "Business", "monthly": 40, "annual_monthly": 40, "limits": "Unlimited completions, admin dashboard", "features": "Centralized billing, org-wide settings, SAML SSO"},
    ], "model": "per_seat", "url": "https://cursor.com/pricing"},

    {"agent": "GitHub Copilot", "plans": [
        {"name": "Individual", "monthly": 10, "annual_monthly": 10, "limits": "Unlimited suggestions", "features": "Code completion, chat, CLI"},
        {"name": "Business", "monthly": 19, "annual_monthly": 19, "limits": "Unlimited suggestions", "features": "Org management, policy controls, IP indemnity"},
        {"name": "Enterprise", "monthly": 39, "annual_monthly": 39, "limits": "Unlimited suggestions", "features": "Full platform, fine-tuned models, security review"},
    ], "model": "per_seat", "url": "https://github.com/features/copilot"},

    {"agent": "Tabnine", "plans": [
        {"name": "Basic", "monthly": 0, "annual_monthly": 0, "limits": "Short code completions", "features": "Basic AI completions"},
        {"name": "Dev", "monthly": 9, "annual_monthly": 9, "limits": "Unlimited completions", "features": "Whole-line, full-function completions, chat"},
        {"name": "Enterprise", "monthly": 39, "annual_monthly": 39, "limits": "Unlimited", "features": "Private model hosting, SAML, admin controls"},
    ], "model": "per_seat", "url": "https://www.tabnine.com/pricing"},

    {"agent": "Codeium", "plans": [
        {"name": "Individual", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited autocomplete", "features": "Code completion, chat, search"},
        {"name": "Teams", "monthly": 15, "annual_monthly": 12, "limits": "Unlimited", "features": "Admin dashboard, usage analytics, priority support"},
        {"name": "Enterprise", "monthly": None, "annual_monthly": None, "limits": "Custom", "features": "Self-hosted, fine-tuned models, SSO"},
    ], "model": "per_seat", "url": "https://codeium.com/pricing"},

    {"agent": "Sourcegraph Cody", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "500 completions, 20 chats/month", "features": "IDE extension, basic context"},
        {"name": "Pro", "monthly": 9, "annual_monthly": 9, "limits": "Unlimited completions, unlimited chat", "features": "Full context search, multi-repo"},
        {"name": "Enterprise", "monthly": 19, "annual_monthly": 19, "limits": "Unlimited", "features": "SCIM, SSO, custom models, guardrails"},
    ], "model": "per_seat", "url": "https://sourcegraph.com/pricing"},

    {"agent": "Devin", "plans": [
        {"name": "Teams", "monthly": 500, "annual_monthly": 500, "limits": "250 ACUs/month", "features": "Autonomous coding, PR creation, deployment"},
    ], "model": "usage_based", "url": "https://devin.ai/pricing"},

    {"agent": "Replit", "plans": [
        {"name": "Starter", "monthly": 0, "annual_monthly": 0, "limits": "Basic AI features", "features": "Code completion, limited Ghostwriter"},
        {"name": "Replit Core", "monthly": 25, "annual_monthly": 20, "limits": "Unlimited AI", "features": "Ghostwriter, advanced AI, private repls"},
        {"name": "Teams", "monthly": 40, "annual_monthly": 40, "limits": "Unlimited", "features": "Team management, advanced permissions"},
    ], "model": "per_seat", "url": "https://replit.com/pricing"},

    {"agent": "Windsurf", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "Limited credits", "features": "Basic code completion and chat"},
        {"name": "Pro", "monthly": 15, "annual_monthly": 10, "limits": "Unlimited flows, premium models", "features": "Cascade, GPT-4, Claude, multi-file edits"},
        {"name": "Pro Ultimate", "monthly": 60, "annual_monthly": 60, "limits": "Unlimited premium", "features": "Unlimited premium model access"},
    ], "model": "per_seat", "url": "https://windsurf.com/pricing"},

    # ── AI Platforms ──
    {"agent": "openai", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "Limited GPT-4o-mini", "features": "ChatGPT basic access"},
        {"name": "Plus", "monthly": 20, "annual_monthly": 20, "limits": "Extended GPT-4o, DALL-E, browsing", "features": "Priority access, advanced analysis"},
        {"name": "Pro", "monthly": 200, "annual_monthly": 200, "limits": "Unlimited GPT-4o, o1-pro access", "features": "Extended thinking, highest compute"},
        {"name": "API", "monthly": None, "annual_monthly": None, "limits": "Pay per token", "features": "Full API access, fine-tuning"},
    ], "model": "usage_based", "url": "https://openai.com/pricing"},

    {"agent": "anthropic", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "Limited Claude access", "features": "Basic Claude chat"},
        {"name": "Pro", "monthly": 20, "annual_monthly": 20, "limits": "5x more usage", "features": "Priority access, Projects, early features"},
        {"name": "Max", "monthly": 100, "annual_monthly": 100, "limits": "20x more usage", "features": "Extended thinking, highest limits"},
        {"name": "API", "monthly": None, "annual_monthly": None, "limits": "Pay per token", "features": "Full API access, tool use, vision"},
    ], "model": "usage_based", "url": "https://anthropic.com/pricing"},

    {"agent": "google-gemini", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "Limited Gemini access", "features": "Gemini chat, basic features"},
        {"name": "Advanced", "monthly": 20, "annual_monthly": 20, "limits": "Extended Gemini 1.5 Pro", "features": "1M token context, Gems, Google integrations"},
        {"name": "API", "monthly": None, "annual_monthly": None, "limits": "Pay per token", "features": "Full API access"},
    ], "model": "usage_based", "url": "https://ai.google.dev/pricing"},

    {"agent": "mistral", "plans": [
        {"name": "API", "monthly": None, "annual_monthly": None, "limits": "Pay per token", "features": "Mistral Large, Small, Codestral"},
    ], "model": "per_token", "url": "https://mistral.ai/technology/#pricing"},

    {"agent": "cohere", "plans": [
        {"name": "Trial", "monthly": 0, "annual_monthly": 0, "limits": "100 API calls/min", "features": "Command, Embed, Rerank"},
        {"name": "Production", "monthly": None, "annual_monthly": None, "limits": "Pay per token", "features": "Full API, fine-tuning, RAG"},
    ], "model": "per_token", "url": "https://cohere.com/pricing"},

    {"agent": "groq", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "30 RPM, 14,400 RPD", "features": "Ultra-fast inference, open models"},
        {"name": "Pay-as-you-go", "monthly": None, "annual_monthly": None, "limits": "Pay per token", "features": "Higher rate limits, all models"},
    ], "model": "per_token", "url": "https://groq.com/pricing"},

    {"agent": "together-ai", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "$1 free credit", "features": "Access to 100+ open models"},
        {"name": "Pay-as-you-go", "monthly": None, "annual_monthly": None, "limits": "Pay per token", "features": "Dedicated endpoints, fine-tuning"},
    ], "model": "per_token", "url": "https://www.together.ai/pricing"},

    {"agent": "fireworks-ai", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "$1 free credit", "features": "Serverless inference"},
        {"name": "Pay-as-you-go", "monthly": None, "annual_monthly": None, "limits": "Pay per token", "features": "Fast inference, fine-tuning, on-demand"},
    ], "model": "per_token", "url": "https://fireworks.ai/pricing"},

    {"agent": "replicate", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "Limited free predictions", "features": "Run open-source models"},
        {"name": "Pay-as-you-go", "monthly": None, "annual_monthly": None, "limits": "Pay per second of compute", "features": "GPU inference, custom models"},
    ], "model": "usage_based", "url": "https://replicate.com/pricing"},

    {"agent": "anyscale", "plans": [
        {"name": "Endpoints", "monthly": None, "annual_monthly": None, "limits": "Pay per token", "features": "Hosted open-source LLMs, fine-tuning"},
    ], "model": "per_token", "url": "https://www.anyscale.com/pricing"},

    # ── Agent Frameworks ──
    {"agent": "langsmith", "plans": [
        {"name": "Developer", "monthly": 0, "annual_monthly": 0, "limits": "5,000 traces/month", "features": "LLM observability, debugging"},
        {"name": "Plus", "monthly": 39, "annual_monthly": 39, "limits": "Included traces + overage", "features": "Team workspace, advanced analytics"},
        {"name": "Enterprise", "monthly": None, "annual_monthly": None, "limits": "Custom", "features": "SSO, RBAC, self-hosted option"},
    ], "model": "usage_based", "url": "https://www.langchain.com/pricing"},

    {"agent": "crewai", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited local", "features": "Multi-agent framework, Python"},
        {"name": "Enterprise", "monthly": None, "annual_monthly": None, "limits": "Custom", "features": "Managed hosting, monitoring, support"},
    ], "model": "open_source_free", "url": "https://www.crewai.com/"},

    {"agent": "autogen", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "Multi-agent conversation framework"},
    ], "model": "open_source_free", "url": "https://github.com/microsoft/autogen"},

    {"agent": "llamacloud", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "1,000 pages/week parsing", "features": "LlamaParse, managed RAG"},
        {"name": "Starter", "monthly": 35, "annual_monthly": 35, "limits": "8,500 pages/week", "features": "Enhanced parsing, priority support"},
    ], "model": "usage_based", "url": "https://www.llamaindex.ai/pricing"},

    # ── MCP / Automation Tools ──
    {"agent": "zapier", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "100 tasks/month, 5 Zaps", "features": "Basic automation"},
        {"name": "Starter", "monthly": 29.99, "annual_monthly": 19.99, "limits": "750 tasks/month", "features": "Multi-step Zaps, filters"},
        {"name": "Professional", "monthly": 73.50, "annual_monthly": 49, "limits": "2,000 tasks/month", "features": "Webhooks, custom logic"},
        {"name": "Team", "monthly": 103.50, "annual_monthly": 69, "limits": "Shared workspace", "features": "Premier support, shared connections"},
    ], "model": "usage_based", "url": "https://zapier.com/pricing"},

    {"agent": "make", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "1,000 ops/month", "features": "Core apps, 5-min interval"},
        {"name": "Core", "monthly": 10.59, "annual_monthly": 9, "limits": "10,000 ops/month", "features": "Unlimited scenarios"},
        {"name": "Pro", "monthly": 18.82, "annual_monthly": 16, "limits": "10,000 ops/month", "features": "Custom variables, priority execution"},
    ], "model": "usage_based", "url": "https://www.make.com/en/pricing"},

    {"agent": "n8n", "plans": [
        {"name": "Community", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited (self-hosted)", "features": "Open source, full features"},
        {"name": "Starter", "monthly": 24, "annual_monthly": 20, "limits": "2,500 executions/month", "features": "Cloud hosted, 5 workflows"},
        {"name": "Pro", "monthly": 60, "annual_monthly": 50, "limits": "10,000 executions/month", "features": "Unlimited workflows, sharing"},
    ], "model": "usage_based", "url": "https://n8n.io/pricing"},

    {"agent": "activepieces", "plans": [
        {"name": "Community", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited (self-hosted)", "features": "Open source automation"},
        {"name": "Pro", "monthly": 10, "annual_monthly": 10, "limits": "1,000 tasks/month", "features": "Cloud hosted, premium pieces"},
    ], "model": "usage_based", "url": "https://www.activepieces.com/pricing"},

    # ── Search / RAG ──
    {"agent": "perplexity", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "Limited Pro searches", "features": "Quick search, basic sources"},
        {"name": "Pro", "monthly": 20, "annual_monthly": 20, "limits": "300+ Pro searches/day", "features": "GPT-4o, Claude, file upload, API access"},
    ], "model": "per_seat", "url": "https://perplexity.ai/pro"},

    {"agent": "you-com", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "Limited searches", "features": "AI search, basic features"},
        {"name": "YouPro", "monthly": 15, "annual_monthly": 15, "limits": "Unlimited AI search", "features": "GPT-4, image generation, priority access"},
    ], "model": "per_seat", "url": "https://you.com/plans"},

    {"agent": "tavily", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "1,000 API calls/month", "features": "AI search API"},
        {"name": "Starter", "monthly": 80, "annual_monthly": 80, "limits": "24,000 API calls/month", "features": "Priority support"},
        {"name": "Growth", "monthly": 280, "annual_monthly": 280, "limits": "120,000 API calls/month", "features": "Custom domains"},
    ], "model": "per_call", "url": "https://tavily.com/#pricing"},

    {"agent": "exa-ai", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "1,000 requests/month", "features": "Neural search API"},
        {"name": "Basic", "monthly": 100, "annual_monthly": 100, "limits": "10,000 searches/month", "features": "Full API, contents endpoint"},
    ], "model": "per_call", "url": "https://exa.ai/pricing"},

    {"agent": "serper", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "2,500 queries", "features": "Google search API"},
        {"name": "Developer", "monthly": 50, "annual_monthly": 50, "limits": "50,000 queries/month", "features": "All search types"},
    ], "model": "per_call", "url": "https://serper.dev/pricing"},

    # ── Popular Open Source Agents (free) ──
    {"agent": "LangChain", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "LLM application framework"},
    ], "model": "open_source_free", "url": "https://github.com/langchain-ai/langchain"},

    {"agent": "llamaindex", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "RAG framework"},
    ], "model": "open_source_free", "url": "https://github.com/run-llama/llama_index"},

    {"agent": "haystack", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "NLP/RAG framework"},
    ], "model": "open_source_free", "url": "https://github.com/deepset-ai/haystack"},

    {"agent": "dify", "plans": [
        {"name": "Sandbox", "monthly": 0, "annual_monthly": 0, "limits": "200 GPT-4 calls", "features": "LLM app builder"},
        {"name": "Professional", "monthly": 59, "annual_monthly": 59, "limits": "5,000 messages/month", "features": "Custom branding, priority support"},
    ], "model": "usage_based", "url": "https://dify.ai/pricing"},

    {"agent": "flowise", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited (self-hosted)", "features": "Visual LLM flow builder"},
        {"name": "Cloud", "monthly": 35, "annual_monthly": 35, "limits": "10,000 predictions/month", "features": "Managed hosting"},
    ], "model": "open_source_free", "url": "https://flowiseai.com/pricing"},

    {"agent": "langflow", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "Limited", "features": "Visual LLM framework"},
        {"name": "Starter", "monthly": 15, "annual_monthly": 15, "limits": "10,000 runs/month", "features": "Cloud deployment"},
    ], "model": "open_source_free", "url": "https://www.langflow.org/pricing"},

    {"agent": "SWE-agent", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "Autonomous SWE agent"},
    ], "model": "open_source_free", "url": "https://github.com/princeton-nlp/SWE-agent"},

    {"agent": "AutoGPT", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "Autonomous GPT agent"},
    ], "model": "open_source_free", "url": "https://github.com/Significant-Gravitas/AutoGPT"},

    {"agent": "MetaGPT", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "Multi-agent meta-programming"},
    ], "model": "open_source_free", "url": "https://github.com/geekan/MetaGPT"},

    {"agent": "OpenDevin", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "Autonomous dev agent"},
    ], "model": "open_source_free", "url": "https://github.com/OpenDevin/OpenDevin"},

    {"agent": "aider", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "AI pair programming CLI"},
    ], "model": "open_source_free", "url": "https://github.com/paul-gauthier/aider"},

    {"agent": "continue-dev", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "Open-source Copilot alternative"},
    ], "model": "open_source_free", "url": "https://github.com/continuedev/continue"},

    {"agent": "tabby", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited (self-hosted)", "features": "Self-hosted code assistant"},
        {"name": "Cloud", "monthly": 8, "annual_monthly": 8, "limits": "Hosted solution", "features": "Managed deployment"},
    ], "model": "open_source_free", "url": "https://github.com/TabbyML/tabby"},

    {"agent": "open-interpreter", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "Local code interpreter"},
    ], "model": "open_source_free", "url": "https://github.com/OpenInterpreter/open-interpreter"},

    {"agent": "gpt-engineer", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "Specify and generate codebases"},
    ], "model": "open_source_free", "url": "https://github.com/gpt-engineer-org/gpt-engineer"},

    {"agent": "phidata", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "Agent framework with memory"},
    ], "model": "open_source_free", "url": "https://github.com/phidatahq/phidata"},

    {"agent": "semantic-kernel", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "Microsoft AI orchestration SDK"},
    ], "model": "open_source_free", "url": "https://github.com/microsoft/semantic-kernel"},

    {"agent": "embedchain", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "RAG framework"},
    ], "model": "open_source_free", "url": "https://github.com/embedchain/embedchain"},

    {"agent": "promptflow", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "LLM app flow builder"},
    ], "model": "open_source_free", "url": "https://github.com/microsoft/promptflow"},

    {"agent": "vanna-ai", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "Text-to-SQL AI"},
    ], "model": "open_source_free", "url": "https://github.com/vanna-ai/vanna"},

    {"agent": "chatgpt-on-wechat", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "ChatGPT WeChat bot"},
    ], "model": "open_source_free", "url": "https://github.com/zhayujie/chatgpt-on-wechat"},

    {"agent": "lobe-chat", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited (self-hosted)", "features": "Chat client with plugin system"},
    ], "model": "open_source_free", "url": "https://github.com/lobehub/lobe-chat"},

    {"agent": "chatbox", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "Desktop AI chat client"},
    ], "model": "open_source_free", "url": "https://github.com/nicepkg/chatbox"},

    {"agent": "jan", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "Local AI desktop client"},
    ], "model": "open_source_free", "url": "https://github.com/janhq/jan"},

    {"agent": "ollama", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "Local LLM runner"},
    ], "model": "open_source_free", "url": "https://github.com/ollama/ollama"},

    {"agent": "LocalAI", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "OpenAI-compatible local API"},
    ], "model": "open_source_free", "url": "https://github.com/mudler/LocalAI"},

    {"agent": "text-generation-webui", "plans": [
        {"name": "Open Source", "monthly": 0, "annual_monthly": 0, "limits": "Unlimited", "features": "Gradio web UI for LLMs"},
    ], "model": "open_source_free", "url": "https://github.com/oobabooga/text-generation-webui"},

    {"agent": "claude-code", "plans": [
        {"name": "Usage-based", "monthly": None, "annual_monthly": None, "limits": "Anthropic API pricing", "features": "Agentic coding CLI by Anthropic"},
    ], "model": "usage_based", "url": "https://docs.anthropic.com/en/docs/claude-code"},

    {"agent": "Lovable", "plans": [
        {"name": "Starter", "monthly": 0, "annual_monthly": 0, "limits": "Limited messages", "features": "AI app builder"},
        {"name": "Launch", "monthly": 20, "annual_monthly": 16, "limits": "5x message volume", "features": "Custom domains, GitHub sync"},
        {"name": "Scale", "monthly": 50, "annual_monthly": 40, "limits": "Unlimited messages", "features": "Priority support, team features"},
    ], "model": "per_seat", "url": "https://lovable.dev/pricing"},

    {"agent": "Bolt", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "Limited tokens", "features": "AI web app builder"},
        {"name": "Pro", "monthly": 20, "annual_monthly": 16.67, "limits": "10M tokens/month", "features": "Deploy to Netlify, custom domains"},
        {"name": "Pro Plus", "monthly": 50, "annual_monthly": 41.67, "limits": "26M tokens/month", "features": "Priority queue, advanced models"},
    ], "model": "usage_based", "url": "https://bolt.new/pricing"},

    {"agent": "v0", "plans": [
        {"name": "Free", "monthly": 0, "annual_monthly": 0, "limits": "200 credits/month", "features": "UI generation, code snippets"},
        {"name": "Premium", "monthly": 20, "annual_monthly": 20, "limits": "Unlimited generations", "features": "Priority access, team features"},
    ], "model": "per_seat", "url": "https://v0.dev/pricing"},
]

# Agent name patterns that indicate they use a specific LLM
README_MODEL_HINTS = {
    r'\bgpt-?4o?\b': 'gpt-4o',
    r'\bgpt-?4-?turbo\b': 'gpt-4-turbo',
    r'\bgpt-?4o-?mini\b': 'gpt-4o-mini',
    r'\bclaude-?3\.?5?\s*sonnet\b': 'claude-3.5-sonnet',
    r'\bclaude-?3\s*opus\b': 'claude-3-opus',
    r'\bclaude-?3\s*haiku\b': 'claude-3-haiku',
    r'\bgemini[\s-]*pro\b': 'gemini-pro',
    r'\bgemini[\s-]*flash\b': 'gemini-flash',
    r'\bmistral[\s-]*large\b': 'mistral-large',
    r'\bllama[\s-]*3[\s-]*70b\b': 'llama-3-70b',
    r'\bllama[\s-]*3[\s-]*8b\b': 'llama-3-8b',
    r'\bdeepseek[\s-]*v3\b': 'deepseek-v3',
}


def _init_db():
    conn = sqlite3.connect(str(SQLITE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_pricing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            plan_name TEXT,
            price_monthly REAL,
            price_annual_monthly REAL,
            currency TEXT DEFAULT 'USD',
            free_tier_limits TEXT,
            rate_limits TEXT,
            key_features TEXT,
            pricing_url TEXT,
            pricing_model TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ap_name ON agent_pricing(agent_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ap_model ON agent_pricing(pricing_model)")
    conn.commit()
    conn.close()


def _detect_models_from_readme(agent_name, conn_sqlite):
    """Detect LLM model usage from agent_frameworks table data."""
    models = set()

    # Check framework detector results
    fws = conn_sqlite.execute(
        "SELECT framework FROM agent_frameworks WHERE agent_name = ? OR agent_name LIKE ?",
        (agent_name, f"%{agent_name}%")
    ).fetchall()

    for r in fws:
        fw = r[0].lower()
        if fw == "openai":
            models.add("gpt-4o")
        elif fw == "anthropic":
            models.add("claude-3.5-sonnet")
        elif fw in ("google-genai",):
            models.add("gemini-pro")
        elif fw == "mistral":
            models.add("mistral-large")
        elif fw == "groq":
            models.add("llama-3-70b")
        elif fw == "ollama":
            models.add("llama-3-8b")

    return list(models)


def _store_curated_data(conn):
    """Store curated pricing data in SQLite."""
    now = datetime.now().isoformat()
    count = 0

    for entry in CURATED_PRICING:
        agent = entry["agent"]
        model = entry["model"]
        url = entry["url"]

        # Clear old entries
        conn.execute("DELETE FROM agent_pricing WHERE agent_name = ?", (agent,))

        for plan in entry["plans"]:
            free_limits = plan.get("limits") if (plan.get("monthly") or 0) == 0 else None
            conn.execute(
                "INSERT INTO agent_pricing (agent_name, plan_name, price_monthly, price_annual_monthly, "
                "currency, free_tier_limits, key_features, pricing_url, pricing_model, fetched_at) "
                "VALUES (?, ?, ?, ?, 'USD', ?, ?, ?, ?, ?)",
                (
                    agent, plan["name"], plan.get("monthly"), plan.get("annual_monthly"),
                    free_limits, plan.get("features"), url, model, now,
                )
            )
            count += 1

    conn.commit()
    return count


def _detect_open_source_pricing(conn):
    """For agents not in curated list, detect open-source status from license data."""
    from agentindex.db.models import get_session
    session = get_session()

    now = datetime.now().isoformat()
    count = 0

    try:
        # Get agents with permissive licenses that don't have pricing data yet
        existing = set(
            r[0] for r in conn.execute("SELECT DISTINCT agent_name FROM agent_pricing").fetchall()
        )

        oss_rows = conn.execute("""
            SELECT DISTINCT al.agent_name
            FROM agent_licenses al
            WHERE al.license_category IN ('PERMISSIVE', 'COPYLEFT')
            AND al.agent_name NOT IN (SELECT DISTINCT agent_name FROM agent_pricing)
            LIMIT 500
        """).fetchall()

        for r in oss_rows:
            name = r[0]
            if name in existing:
                continue
            conn.execute(
                "INSERT INTO agent_pricing (agent_name, plan_name, price_monthly, price_annual_monthly, "
                "currency, free_tier_limits, key_features, pricing_url, pricing_model, fetched_at) "
                "VALUES (?, 'Open Source', 0, 0, 'USD', 'Unlimited (self-hosted)', 'Open source software', NULL, 'open_source_free', ?)",
                (name, now)
            )
            count += 1
            existing.add(name)

        conn.commit()
    finally:
        session.close()

    return count


def main():
    logger.info("=" * 60)
    logger.info("Pricing Crawler — starting")
    logger.info("=" * 60)

    _init_db()
    conn = sqlite3.connect(str(SQLITE_DB))

    # Step 1: Store curated pricing data
    curated_count = _store_curated_data(conn)
    logger.info(f"  Curated pricing entries: {curated_count}")

    # Step 2: Detect open-source pricing from license data
    oss_count = _detect_open_source_pricing(conn)
    logger.info(f"  Open-source pricing entries: {oss_count}")

    # Step 3: Summary statistics
    total = conn.execute("SELECT COUNT(*) FROM agent_pricing").fetchone()[0]
    agents = conn.execute("SELECT COUNT(DISTINCT agent_name) FROM agent_pricing").fetchone()[0]

    models = conn.execute(
        "SELECT pricing_model, COUNT(DISTINCT agent_name) FROM agent_pricing GROUP BY pricing_model ORDER BY COUNT(*) DESC"
    ).fetchall()

    free_agents = conn.execute(
        "SELECT COUNT(DISTINCT agent_name) FROM agent_pricing WHERE price_monthly = 0 OR price_monthly IS NULL"
    ).fetchone()[0]

    paid_agents = conn.execute(
        "SELECT COUNT(DISTINCT agent_name) FROM agent_pricing WHERE price_monthly > 0"
    ).fetchone()[0]

    conn.close()

    logger.info("")
    logger.info("=" * 60)
    logger.info("Pricing Crawler — COMPLETE")
    logger.info(f"  Total pricing entries: {total}")
    logger.info(f"  Agents with pricing: {agents}")
    logger.info(f"  Agents with free tier: {free_agents}")
    logger.info(f"  Agents with paid plans: {paid_agents}")
    logger.info(f"  Pricing model distribution:")
    for model, count in models:
        logger.info(f"    {model}: {count} agents")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
