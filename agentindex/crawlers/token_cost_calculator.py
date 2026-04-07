"""
Token Cost Calculator — Wednesdays 04:00
==========================================
Estimates per-task costs for agents based on which LLM they use.
Cross-references framework detector data with published model pricing.

Usage:
    python -m agentindex.crawlers.token_cost_calculator
"""

import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy.sql import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [token-cost] %(message)s",
)
logger = logging.getLogger("token-cost")

SQLITE_DB = Path(__file__).parent.parent / "crypto" / "crypto_trust.db"

# ── Model pricing per 1M tokens (USD) ─────────────────────────
MODEL_PRICING = {
    'gpt-4o': {'input': 2.50, 'output': 10.00},
    'gpt-4o-mini': {'input': 0.15, 'output': 0.60},
    'gpt-4-turbo': {'input': 10.00, 'output': 30.00},
    'gpt-4': {'input': 30.00, 'output': 60.00},
    'gpt-3.5-turbo': {'input': 0.50, 'output': 1.50},
    'claude-opus-4': {'input': 15.00, 'output': 75.00},
    'claude-sonnet-4': {'input': 3.00, 'output': 15.00},
    'claude-3-opus': {'input': 15.00, 'output': 75.00},
    'claude-3.5-sonnet': {'input': 3.00, 'output': 15.00},
    'claude-3-haiku': {'input': 0.25, 'output': 1.25},
    'gemini-pro': {'input': 0.50, 'output': 1.50},
    'gemini-flash': {'input': 0.075, 'output': 0.30},
    'gemini-2.0-flash': {'input': 0.10, 'output': 0.40},
    'mistral-large': {'input': 2.00, 'output': 6.00},
    'mistral-small': {'input': 0.20, 'output': 0.60},
    'llama-3-70b': {'input': 0.59, 'output': 0.79},
    'llama-3-8b': {'input': 0.05, 'output': 0.08},
    'llama-3.1-405b': {'input': 3.00, 'output': 3.00},
    'deepseek-v3': {'input': 0.27, 'output': 1.10},
    'deepseek-r1': {'input': 0.55, 'output': 2.19},
    'qwen-2.5-72b': {'input': 0.40, 'output': 0.40},
    'command-r-plus': {'input': 2.50, 'output': 10.00},
}

# ── Task token profiles ───────────────────────────────────────
TASK_PROFILES = {
    'code_review': {'input': 4000, 'output': 2000, 'description': 'Review a code change (~200 lines)'},
    'code_generation': {'input': 2000, 'output': 4000, 'description': 'Generate a function or module'},
    'chat_response': {'input': 1000, 'output': 500, 'description': 'Single conversational turn'},
    'document_analysis': {'input': 10000, 'output': 2000, 'description': 'Analyze a document (~5 pages)'},
    'data_extraction': {'input': 5000, 'output': 1000, 'description': 'Extract structured data'},
    'bug_fix': {'input': 3000, 'output': 2000, 'description': 'Diagnose and fix a bug'},
    'test_generation': {'input': 2000, 'output': 3000, 'description': 'Generate unit tests'},
}

# ── Framework → default model mapping ─────────────────────────
FRAMEWORK_MODEL_MAP = {
    'openai': 'gpt-4o',
    'anthropic': 'claude-3.5-sonnet',
    'google-genai': 'gemini-pro',
    'mistral': 'mistral-large',
    'groq': 'llama-3-70b',
    'ollama': 'llama-3-8b',
    'cohere': 'command-r-plus',
    'transformers': 'llama-3-8b',
    'pytorch': 'llama-3-8b',
    'vercel-ai': 'gpt-4o',
}

# ── Agent → known model mapping (curated) ─────────────────────
AGENT_MODELS = {
    'Cursor': ['gpt-4o', 'claude-3.5-sonnet'],
    'GitHub Copilot': ['gpt-4o'],
    'Tabnine': ['gpt-4o-mini'],
    'Windsurf': ['gpt-4o', 'claude-3.5-sonnet'],
    'Sourcegraph Cody': ['claude-3.5-sonnet'],
    'Devin': ['claude-3.5-sonnet', 'gpt-4o'],
    'Replit': ['gpt-4o-mini'],
    'Lovable': ['claude-3.5-sonnet'],
    'Bolt': ['claude-3.5-sonnet', 'gpt-4o'],
    'v0': ['gpt-4o'],
    'claude-code': ['claude-sonnet-4'],
    'aider': ['gpt-4o', 'claude-3.5-sonnet', 'deepseek-v3'],
    'continue-dev': ['gpt-4o', 'claude-3.5-sonnet', 'llama-3-70b'],
    'open-interpreter': ['gpt-4o', 'claude-3.5-sonnet'],
    'SWE-agent': ['gpt-4o', 'claude-3.5-sonnet'],
    'AutoGPT': ['gpt-4o'],
    'MetaGPT': ['gpt-4o', 'claude-3.5-sonnet'],
    'gpt-engineer': ['gpt-4o'],
    'perplexity': ['gpt-4o', 'claude-3.5-sonnet'],
}


def _init_db():
    conn = sqlite3.connect(str(SQLITE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_cost_estimates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            model_used TEXT NOT NULL,
            task_type TEXT NOT NULL,
            estimated_input_tokens INTEGER,
            estimated_output_tokens INTEGER,
            estimated_cost_usd REAL,
            notes TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ace_name ON agent_cost_estimates(agent_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ace_model ON agent_cost_estimates(model_used)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ace_task ON agent_cost_estimates(task_type)")
    conn.commit()
    conn.close()


def _calculate_cost(model, input_tokens, output_tokens):
    """Calculate cost for a given model and token counts."""
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        return None
    input_cost = (input_tokens / 1_000_000) * pricing['input']
    output_cost = (output_tokens / 1_000_000) * pricing['output']
    return round(input_cost + output_cost, 6)


def _detect_models_for_agent(agent_name, conn):
    """Detect which LLM models an agent uses."""
    models = set()

    # Check curated mapping first
    if agent_name in AGENT_MODELS:
        return AGENT_MODELS[agent_name]

    # Check framework detector data
    fws = conn.execute(
        "SELECT framework FROM agent_frameworks WHERE agent_name = ? OR agent_name LIKE ?",
        (agent_name, f"%{agent_name}%")
    ).fetchall()

    for r in fws:
        fw = r[0].lower()
        mapped = FRAMEWORK_MODEL_MAP.get(fw)
        if mapped:
            models.add(mapped)

    # If we found frameworks but no model mapping, default to gpt-4o
    if fws and not models:
        models.add('gpt-4o-mini')

    return list(models)


def main():
    logger.info("=" * 60)
    logger.info("Token Cost Calculator — starting")
    logger.info("=" * 60)

    _init_db()
    conn = sqlite3.connect(str(SQLITE_DB))

    # Clear old estimates
    conn.execute("DELETE FROM agent_cost_estimates")
    conn.commit()

    now = datetime.now().isoformat()
    total_estimates = 0
    agents_with_costs = set()
    model_usage = {}

    # Process curated agents first
    for agent_name, models in AGENT_MODELS.items():
        for model in models:
            for task_type, profile in TASK_PROFILES.items():
                cost = _calculate_cost(model, profile['input'], profile['output'])
                if cost is not None:
                    conn.execute(
                        "INSERT INTO agent_cost_estimates (agent_name, model_used, task_type, "
                        "estimated_input_tokens, estimated_output_tokens, estimated_cost_usd, notes, fetched_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (agent_name, model, task_type, profile['input'], profile['output'],
                         cost, f"Curated model mapping. {profile['description']}", now)
                    )
                    total_estimates += 1
                    agents_with_costs.add(agent_name)
                    model_usage[model] = model_usage.get(model, 0) + 1

    conn.commit()
    logger.info(f"  Curated agent costs: {len(AGENT_MODELS)} agents, {total_estimates} estimates")

    # Process agents from framework detector
    fw_agents = conn.execute("""
        SELECT DISTINCT agent_name FROM agent_frameworks
        WHERE agent_name NOT IN ({})
    """.format(",".join(f"'{a}'" for a in AGENT_MODELS.keys()))).fetchall()

    framework_estimates = 0
    for row in fw_agents:
        agent_name = row[0]
        models = _detect_models_for_agent(agent_name, conn)

        if not models:
            continue

        # Use first (most likely) model for framework-detected agents
        model = models[0]

        for task_type, profile in TASK_PROFILES.items():
            cost = _calculate_cost(model, profile['input'], profile['output'])
            if cost is not None:
                conn.execute(
                    "INSERT INTO agent_cost_estimates (agent_name, model_used, task_type, "
                    "estimated_input_tokens, estimated_output_tokens, estimated_cost_usd, notes, fetched_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (agent_name, model, task_type, profile['input'], profile['output'],
                     cost, f"Framework-detected model. {profile['description']}", now)
                )
                total_estimates += 1
                framework_estimates += 1
                agents_with_costs.add(agent_name)
                model_usage[model] = model_usage.get(model, 0) + 1

    conn.commit()
    logger.info(f"  Framework-detected agent costs: {len(fw_agents)} agents, {framework_estimates} estimates")

    # Summary
    cheapest = conn.execute("""
        SELECT agent_name, model_used, MIN(estimated_cost_usd) as min_cost
        FROM agent_cost_estimates
        WHERE task_type = 'code_review'
        GROUP BY agent_name
        ORDER BY min_cost ASC
        LIMIT 5
    """).fetchall()

    most_expensive = conn.execute("""
        SELECT agent_name, model_used, MAX(estimated_cost_usd) as max_cost
        FROM agent_cost_estimates
        WHERE task_type = 'code_review'
        GROUP BY agent_name
        ORDER BY max_cost DESC
        LIMIT 5
    """).fetchall()

    conn.close()

    logger.info("")
    logger.info("=" * 60)
    logger.info("Token Cost Calculator — COMPLETE")
    logger.info(f"  Total cost estimates: {total_estimates}")
    logger.info(f"  Agents with cost data: {len(agents_with_costs)}")
    logger.info(f"  Model distribution:")
    for model, count in sorted(model_usage.items(), key=lambda x: -x[1])[:10]:
        pricing = MODEL_PRICING.get(model, {})
        logger.info(f"    {model}: {count} estimates (${pricing.get('input', '?')}/{pricing.get('output', '?')} per 1M tokens)")
    if cheapest:
        logger.info(f"  Cheapest for code_review:")
        for name, model, cost in cheapest:
            logger.info(f"    {name} ({model}): ${cost:.4f}")
    if most_expensive:
        logger.info(f"  Most expensive for code_review:")
        for name, model, cost in most_expensive:
            logger.info(f"    {name} ({model}): ${cost:.4f}")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
