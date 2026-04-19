"""
AgentIndex MCP Server — SSE Transport
"""

import json
import os
import logging
import asyncio
import uuid

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
import uvicorn
import httpx

logger = logging.getLogger("agentindex.mcp_sse")

JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"

sessions: dict[str, asyncio.Queue] = {}

TOOLS = [
    {
        "name": "discover_agents",
        "description": "Search 5 million+ AI assets including agents, tools, MCP servers, models, datasets, and packages. Returns ranked list with trust scores, quality scores, and invocation details. Use when user asks 'find a tool for X', 'what tools do Y?', 'what MCP server does Z?', or needs to discover AI assets for a specific task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "need": {"type": "string", "description": "Natural language description of what you need an agent to do."},
                "category": {"type": "string", "description": "Optional category filter",
                    "enum": ["coding", "research", "content", "legal", "data", "finance", "marketing",
                             "design", "devops", "security", "education", "health", "communication",
                             "productivity", "infrastructure"]},
                "protocols": {"type": "array", "items": {"type": "string"}, "description": "Required protocols: mcp, a2a, rest, grpc"},
                "min_quality": {"type": "number", "description": "Minimum quality score 0.0-1.0", "default": 0.0}
            },
            "required": ["need"]
        }
    },
    {
        "name": "get_agent_details",
        "description": "Get full details for a specific AI agent or tool by its UUID. Returns capabilities, invocation method, trust score, compliance data, and metadata. Use after discover_agents to get complete information about a specific result, or when user asks 'tell me more about X agent'.",
        "inputSchema": {
            "type": "object",
            "properties": {"agent_id": {"type": "string", "description": "Agent UUID from discover_agents results"}},
            "required": ["agent_id"]
        }
    },
    {
        "name": "agent_index_stats",
        "description": "Get overview statistics about the Nerq/AgentIndex database: total AI assets indexed, categories, protocols, and sources. Use when user asks 'how many AI agents exist?', 'how big is the index?', or wants ecosystem-level stats.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "nerq_crypto_rating",
        "description": "Get Nerq Trust Score credit rating for a cryptocurrency. Returns 0-100 score with Moody's-style grade (Aaa-C) and 5-pillar breakdown. Covers 200+ tokens. Use when user asks 'what is the trust score for Bitcoin?', 'rate ETH', or needs a credit-style rating for any crypto token.",
        "inputSchema": {"type": "object", "properties": {"token_id": {"type": "string", "description": "CoinGecko token ID e.g. bitcoin, ethereum, solana"}}, "required": ["token_id"]}
    },
    {
        "name": "nerq_crypto_ndd",
        "description": "Get Nerq NDD (Nearness to Distress/Default) for a crypto token. Returns 0-5 distress score, 7 risk signals, crash probability, and HC alert status. NDD < 2.0 = high crash risk. 100% recall on crash detection. Use when user asks 'is X about to crash?', 'what is the crash risk for Y?', or needs distress/default analysis for any crypto token.",
        "inputSchema": {"type": "object", "properties": {"token_id": {"type": "string", "description": "CoinGecko token ID"}}, "required": ["token_id"]}
    },
    {
        "name": "nerq_crypto_safety",
        "description": "Quick pre-trade safety check for a crypto token. Returns SAFE/CAUTION/DANGER verdict with risk factors. Designed for AI agents and trading bots. Use when user asks 'is it safe to buy X?', 'should I trade Y?', or needs a quick go/no-go verdict before any crypto transaction.",
        "inputSchema": {"type": "object", "properties": {"token_id": {"type": "string", "description": "Token ID or symbol"}}, "required": ["token_id"]}
    },
    {
        "name": "nerq_crypto_signals",
        "description": "Get active crypto risk warnings from Nerq. Returns all WARNING and CRITICAL tokens with risk distribution across 200+ monitored tokens. Use when user asks 'which tokens are at risk?', 'any crypto warnings right now?', 'what tokens should I avoid?', or needs a market-wide risk dashboard.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "nerq_crypto_compare",
        "description": "Compare two crypto tokens side-by-side on safety: Trust Score, NDD, risk level, and crash probability. Returns verdict on which is safer. Use when user asks 'Bitcoin vs Ethereum safety', 'which is safer X or Y?', 'compare risk of X and Y', or needs to choose the safer token.",
        "inputSchema": {"type": "object", "properties": {"token1": {"type": "string", "description": "First token ID"}, "token2": {"type": "string", "description": "Second token ID"}}, "required": ["token1", "token2"]}
    },

    {
        "name": "find_best_agent",
        "description": "Find the top 5 best AI agents in a category that meet a minimum trust score threshold. Returns ranked agents with trust scores, compliance data, and risk levels. Use when user asks 'what is the best coding agent?', 'top security tools', 'recommend a finance agent', or needs the highest-rated agents in a domain.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Category to search (e.g. coding, security, finance, data, devops)"},
                "min_trust_score": {"type": "number", "description": "Minimum trust score 0-100 (default 50)", "default": 50}
            },
            "required": ["category"]
        }
    },
    {
        "name": "agent_benchmark",
        "description": "Get the benchmark leaderboard for a category -- top 20 agents ranked by trust score with compliance data, stars, and platform info. Use when user asks 'show me the leaderboard for X', 'rank all coding agents', 'benchmark security tools', or needs a comprehensive category ranking.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Category to benchmark (e.g. coding, security, finance)"}
            },
            "required": ["category"]
        }
    },
    {
        "name": "get_agent_stats",
        "description": "Get full Nerq ecosystem statistics: total AI assets (5M+), breakdown by type (agents, tools, MCP servers, models, datasets), categories, frameworks, languages, and trust score distribution. Use when user asks 'how many AI agents are there?', 'what does Nerq index?', or needs ecosystem-level data for reports or analysis.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "preflight_trust_check",
        "description": "Check if an AI tool, MCP server, npm package, PyPI package, HuggingFace model, or Docker container is safe to use. Returns trust score (0-100), grade (A+ to F), risk level, and PROCEED/CAUTION/DENY recommendation. Use when user asks 'is X safe?', 'should I use X?', 'is X trustworthy?', or needs to evaluate any AI asset before installing, recommending, or delegating tasks to it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Agent name to check trust for"},
                "caller": {"type": "string", "description": "Your agent name (optional, for interaction risk calculation)"}
            },
            "required": ["target"]
        }
    },
    {
        "name": "kya_report",
        "description": "Get a full Know Your Agent (KYA) due diligence report for any AI agent or tool. Returns trust score, grade, category, description, stars, source URL, compliance data, and risk assessment across 204K+ indexed agents. Use when user asks 'give me a full report on X', 'due diligence on Y', 'audit Z', or needs comprehensive safety and compliance information before adopting an AI asset.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Agent name to look up"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "nerq_scout_status",
        "description": "Get Nerq Scout status: how many agents evaluated, featured, and claimed recently. Use when user asks 'what is Nerq Scout doing?', 'how many agents has Scout evaluated?', or wants to check the discovery pipeline status.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "nerq_scout_findings",
        "description": "Get latest top agents discovered by Nerq Scout -- high-trust agents (85+) with stars, categories, and trust scores. Use when user asks 'what are the best new agents?', 'show me recently discovered tools', 'trending AI agents', or wants to see Scout's latest high-quality findings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results (default 10)", "default": 10}
            }
        }
    },
    # ── L4 data-moat tools: /rating, /signals, /dependencies, /dimensions, /prediction
    {
        "name": "get_rating",
        "description": "Get the stable Nerq Trust Score rating (0-100 + grade A+ to F) for a software package slug. Backs the /rating/{slug}.json L4 endpoint, available for the top 100K demand-weighted packages across npm, PyPI, crates, rubygems, packagist, go modules, etc. Returns Trust Score, grade, eight universal sub-dimensions, registry URL, and data sources. Use when user asks 'what is the Nerq rating for X?', 'rate npm package lodash', or needs a machine-readable trust rating for a specific package.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Package slug (e.g. 'lodash', 'requests', 'serde')"}
            },
            "required": ["slug"]
        }
    },
    {
        "name": "bulk_rating_lookup",
        "description": "Look up ratings for up to 25 package slugs in a single call. Returns a list of {slug, trust_score, grade, registry} or {slug, status: 'not_rated'} entries. Use when user asks 'rate these packages', needs to compare trust across a set of dependencies, or wants to audit a package.json / requirements.txt.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slugs": {"type": "array", "items": {"type": "string"}, "description": "List of package slugs (max 25)", "minItems": 1, "maxItems": 25}
            },
            "required": ["slugs"]
        }
    },
    {
        "name": "rating_dimensions_breakdown",
        "description": "Get the eight universal Nerq trust dimensions for a package: security, maintenance, popularity, community, quality, privacy, transparency, reliability. Each dimension is 0-100. Use when user asks 'break down the trust score for X', 'what dimensions does Nerq rate?', or needs to understand WHY a package has its Trust Score.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Package slug"}
            },
            "required": ["slug"]
        }
    },
    {
        "name": "rating_grade_distribution",
        "description": "Get the distribution of trust grades (A+ through F) across the top 100K Nerq-rated packages. Returns counts per grade. Use when user asks 'how many packages are A-rated?', 'what fraction of packages pass Nerq?', or wants ecosystem-level trust stats.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_signals",
        "description": "Get the external trust signals rollup for a Nerq-tracked package (the /signals/{slug}.json L4 endpoint). Returns CVE counts, OpenSSF Scorecard, stars/forks/contributors, release cadence, lifecycle (deprecated, has_types), independent audit flags, and data sources. Use when user asks 'what signals does Nerq see for X?', 'is package X actively maintained?', 'how many CVEs does X have?', or needs the full external trust picture.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Package slug"},
                "registry": {"type": "string", "description": "Optional registry disambiguator (npm, pypi, crates, etc.)"}
            },
            "required": ["slug"]
        }
    },
    {
        "name": "get_cve_summary",
        "description": "Shortcut for CVE data only: returns {slug, cve_count, cve_critical} for a package. Use when user asks 'does X have CVEs?', 'any critical vulnerabilities in X?', or needs a quick CVE answer without the full signals payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Package slug"},
                "registry": {"type": "string", "description": "Optional registry disambiguator"}
            },
            "required": ["slug"]
        }
    },
    {
        "name": "get_openssf_scorecard",
        "description": "Get the OpenSSF Scorecard value (0-10) for a package. Returns {slug, openssf_scorecard}. Use when user asks 'what is X's Scorecard rating?', or needs the OpenSSF number specifically. Returns null if the package is not scorecard-covered.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Package slug"},
                "registry": {"type": "string", "description": "Optional registry disambiguator"}
            },
            "required": ["slug"]
        }
    },
    {
        "name": "get_maintainer_activity",
        "description": "Get maintainer-activity signals for a package: contributors, maintainer_count, release_count, last_commit, last_release_date, forks, open_issues. Use when user asks 'is X actively maintained?', 'when was X last updated?', or needs activity-level signals.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Package slug"},
                "registry": {"type": "string", "description": "Optional registry disambiguator"}
            },
            "required": ["slug"]
        }
    },
    {
        "name": "get_security_attestations",
        "description": "Get security-attestation flags for a package: has_independent_audit, has_soc2, has_iso27001. Use when user asks 'has X been audited?', 'does X have SOC2?', or needs attestation evidence for procurement.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Package slug"},
                "registry": {"type": "string", "description": "Optional registry disambiguator"}
            },
            "required": ["slug"]
        }
    },
    {
        "name": "get_dependencies",
        "description": "Get the dependency-graph view for a package (the /dependencies/{slug}.json L4 endpoint). Returns direct dependency count, transitive count (when known), and dormant status with reason. Use when user asks 'how many dependencies does X have?', 'is X bloated?', 'is X dormant?', or needs dependency-surface analysis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Package slug"},
                "registry": {"type": "string", "description": "Optional registry disambiguator"}
            },
            "required": ["slug"]
        }
    },
    {
        "name": "check_dormant_dependency",
        "description": "Check if a package is dormant (deprecated or no commits/releases in 365+ days). Returns {slug, dormant: bool, dormant_reason, last_commit, last_release_date}. Use when user asks 'is X dormant?', 'is X abandoned?', or needs a quick dormancy verdict before adding a dependency.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Package slug"},
                "registry": {"type": "string", "description": "Optional registry disambiguator"}
            },
            "required": ["slug"]
        }
    },
    {
        "name": "get_dimensions",
        "description": "Get registry-specific dimensional scoring for a package (the /dimensions/{slug}.json L4 endpoint). Unlike the eight universal dimensions, this returns registry-native dimensions (e.g. skin_safety for cosmetics, allergen_risk for food, regulatory envelopes). Use when user asks 'what vertical dimensions does Nerq score for X?', or needs the registry-native scoring layer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Package slug"},
                "registry": {"type": "string", "description": "Optional registry disambiguator"}
            },
            "required": ["slug"]
        }
    },
    {
        "name": "get_prediction",
        "description": "Get the crash/failure prediction payload for a package (the /prediction/{slug}.json L4 endpoint). Returns model-output probabilities and top contributing signals. Use when user asks 'is X about to fail?', 'what is the crash probability for X?', or needs forward-looking risk.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Package slug"},
                "registry": {"type": "string", "description": "Optional registry disambiguator"}
            },
            "required": ["slug"]
        }
    },
    # ── Demand-score tools (smedjan.ai_demand_scores)
    {
        "name": "lookup_demand_score",
        "description": "Look up the Nerq AI-demand score for a package slug. Demand-score ranks entities by how often AI agents / crawlers reference them; only the top 100K get stable /rating/ endpoints. Returns {slug, score, rank} or {slug, in_top_100k: false}. Use when user asks 'is X in the Nerq top 100K?', 'how popular is X with AI agents?', or needs demand-weighted ranking.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Package slug"}
            },
            "required": ["slug"]
        }
    },
    {
        "name": "top_demand_assets",
        "description": "Get the top-N demand-weighted packages (by smedjan.ai_demand_scores). Returns ranked list of {slug, score, registry?}. Use when user asks 'what are the most in-demand packages?', 'which packages do AI agents reference most?', or wants a demand-weighted leaderboard.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results (default 25, max 500)", "default": 25},
                "offset": {"type": "integer", "description": "Pagination offset (default 0)", "default": 0}
            }
        }
    },
    {
        "name": "demand_score_percentile",
        "description": "Get the demand-score percentile of a slug within the top 100K (0-100, higher = more in-demand). Use when user asks 'how in-demand is X compared to other packages?', or needs a relative ranking.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Package slug"}
            },
            "required": ["slug"]
        }
    },
    {
        "name": "demand_score_coverage_stats",
        "description": "Get coverage stats for the demand-weighted data moat: total slugs tracked, top-100K floor score, min/max scores. Use when user asks 'how big is the Nerq data moat?', or needs coverage metrics for the rating pipeline.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    # ── Registry-filtered search (sits on top of discover_agents)
    {
        "name": "search_npm_packages",
        "description": "Search Nerq-indexed npm packages matching a natural-language query, returning top results with trust data. Use when user asks 'find npm packages for X', 'search npm for Y', or specifically wants JavaScript/Node results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "need": {"type": "string", "description": "What you need"},
                "limit": {"type": "integer", "default": 10}
            },
            "required": ["need"]
        }
    },
    {
        "name": "search_pypi_packages",
        "description": "Search Nerq-indexed PyPI packages matching a natural-language query. Use when user asks 'find Python packages for X', 'search PyPI for Y', or specifically wants Python results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "need": {"type": "string", "description": "What you need"},
                "limit": {"type": "integer", "default": 10}
            },
            "required": ["need"]
        }
    },
    {
        "name": "search_mcp_servers_curated",
        "description": "Search Nerq-indexed MCP servers specifically. Returns MCP server packages with trust scores and install snippets for Claude Desktop / Cursor / VS Code. Use when user asks 'find an MCP server for X', 'which MCP server does Y?', or is specifically looking for MCP (not generic npm/pypi).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "need": {"type": "string", "description": "What you need the MCP server to do"},
                "limit": {"type": "integer", "default": 10}
            },
            "required": ["need"]
        }
    },
    {
        "name": "search_huggingface_models",
        "description": "Search Nerq-indexed HuggingFace models matching a natural-language query. Use when user asks 'find a HuggingFace model for X', 'search HF for Y', or specifically wants ML model results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "need": {"type": "string", "description": "What you need"},
                "limit": {"type": "integer", "default": 10}
            },
            "required": ["need"]
        }
    },
    {
        "name": "search_github_repos",
        "description": "Search Nerq-indexed GitHub repositories matching a natural-language query. Use when user asks 'find a GitHub repo for X' or specifically wants source-code repos (not published packages).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "need": {"type": "string", "description": "What you need"},
                "limit": {"type": "integer", "default": 10}
            },
            "required": ["need"]
        }
    },
    {
        "name": "search_crates_packages",
        "description": "Search Nerq-indexed Rust (crates.io) packages matching a natural-language query. Use when user asks 'find a Rust crate for X' or specifically wants Rust results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "need": {"type": "string", "description": "What you need"},
                "limit": {"type": "integer", "default": 10}
            },
            "required": ["need"]
        }
    },
    # ── Reference / metadata tools
    {
        "name": "list_registries",
        "description": "List all software registries Nerq tracks (npm, pypi, crates, rubygems, packagist, go, nuget, hex, cocoapods, pub, homebrew, conda). Returns registry IDs with canonical URL patterns. Use when user asks 'which registries does Nerq cover?', or needs the list of supported ecosystems.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "list_trust_dimensions",
        "description": "List the eight universal trust dimensions that Nerq scores every package on: security, maintenance, popularity, community, quality, privacy, transparency, reliability. Returns dimension IDs + descriptions. Use when user asks 'what does Nerq score?', 'what are the Nerq dimensions?', or is building a dashboard around the dimensions.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "list_jurisdictions",
        "description": "List all 52 global AI-regulation jurisdictions Nerq tracks (EU AI Act, Colorado AI Act, California SB53, UK AI regulation, etc.) with IDs, country, and effective dates. Use when user asks 'which regulations does Nerq cover?', 'list all jurisdictions', or needs the regulation set.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_llms_txt_url",
        "description": "Return the canonical Nerq llms.txt / llms-full.txt URLs that AI crawlers should use for passive discovery. Use when user asks 'where is Nerq's llms.txt?', or when you (as an AI) need to locate the full documentation index.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "list_rss_feeds",
        "description": "List all Nerq RSS feeds (per vertical + global). AI crawlers can subscribe for lastmod-driven re-crawl. Returns feed title + URL pairs. Use when user asks 'does Nerq have RSS?', 'list Nerq feeds', or wants to set up a crawl subscription.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_install_snippet",
        "description": "Get copy-pasteable install/registration snippets for an MCP server across Claude Desktop, Cursor, and VS Code. Use when user asks 'how do I install X MCP server?', 'give me the MCP config for X', or wants ready-to-use integration code.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "MCP server slug"}
            },
            "required": ["slug"]
        }
    },
]

# Merge in T214 expansion tools defined in agentindex/mcp/tools_v3.py.
# tools_v3 is the single source of truth for the compare_packages /
# find_similar / get_verticals / list_by_registry / get_alternatives /
# get_trust_history / search_by_dimension tools; duplicates by name
# (e.g. get_rating/get_signals/get_dependencies which pre-existed in
# this file) are left untouched so the SSE handler keeps its historical
# wiring.
try:
    from agentindex.mcp.tools_v3 import TOOLS as _V3_TOOLS_EXTRA
    _existing_names = {t["name"] for t in TOOLS}
    for _t in _V3_TOOLS_EXTRA:
        if _t.get("name") and _t["name"] not in _existing_names:
            TOOLS.append(_t)
            _existing_names.add(_t["name"])
except Exception:  # noqa: BLE001 — advertising failure must not break the server
    pass

SERVER_CARD = {
    "name": "agentindex",
    "description": "ZARQ crypto risk intelligence + Nerq AI agent trust verification. 204K agents & tools indexed, 198 tokens rated. Preflight checks, KYA reports, benchmarks, L4 rating/signals/dependencies/dimensions/prediction, demand-score lookups. Free API.",
    "version": "1.2.0",
    "tools": TOOLS
}


# ── L4 tool handler helpers ────────────────────────────────────────────────
# These back the 30+ expansion tools added for Smedjan v3.0 (T009). They sit
# on top of the /rating, /signals, /dependencies, /dimensions, /prediction
# endpoints and smedjan.ai_demand_scores. See ~/smedjan/docs/mcp-expansion.md.

_L4_TOOLS = frozenset({
    "get_rating", "bulk_rating_lookup", "rating_dimensions_breakdown",
    "rating_grade_distribution", "get_signals", "get_cve_summary",
    "get_openssf_scorecard", "get_maintainer_activity",
    "get_security_attestations", "get_dependencies",
    "check_dormant_dependency", "get_dimensions", "get_prediction",
    "lookup_demand_score", "top_demand_assets", "demand_score_percentile",
    "demand_score_coverage_stats",
    "search_npm_packages", "search_pypi_packages",
    "search_mcp_servers_curated", "search_huggingface_models",
    "search_github_repos", "search_crates_packages",
    "list_registries", "list_trust_dimensions", "list_jurisdictions",
    "get_llms_txt_url", "list_rss_feeds", "get_install_snippet",
})

_REGISTRY_URL_PATTERNS = {
    "npm": "https://www.npmjs.com/package/{slug}",
    "pypi": "https://pypi.org/project/{slug}/",
    "gems": "https://rubygems.org/gems/{slug}",
    "rubygems": "https://rubygems.org/gems/{slug}",
    "homebrew": "https://formulae.brew.sh/formula/{slug}",
    "crates": "https://crates.io/crates/{slug}",
    "cargo": "https://crates.io/crates/{slug}",
    "nuget": "https://www.nuget.org/packages/{slug}",
    "go": "https://pkg.go.dev/{slug}",
    "packagist": "https://packagist.org/packages/{slug}",
    "hex": "https://hex.pm/packages/{slug}",
    "cocoapods": "https://cocoapods.org/pods/{slug}",
    "pub": "https://pub.dev/packages/{slug}",
    "conda": "https://anaconda.org/conda-forge/{slug}",
}

_UNIVERSAL_DIMENSIONS = [
    {"id": "security", "description": "CVE exposure, audit coverage, attestations"},
    {"id": "maintenance", "description": "Release cadence, last-commit recency, deprecation"},
    {"id": "popularity", "description": "Stars, downloads, demand-weighted usage"},
    {"id": "community", "description": "Contributor count, issue activity, forks"},
    {"id": "quality", "description": "Test coverage proxies, type coverage, doc quality"},
    {"id": "privacy", "description": "Data-handling transparency, PII flags"},
    {"id": "transparency", "description": "License clarity, provenance, changelog"},
    {"id": "reliability", "description": "Uptime proxies, breaking-change frequency"},
]


def _l4_get(client, path):
    port = os.getenv("API_PORT", "8000")
    url = f"http://localhost:{port}{path}"
    resp = client.get(url)
    if resp.status_code == 404:
        return {"error": "slug_not_found", "path": path}
    if resp.status_code == 503:
        return {"error": "upstream_unavailable", "path": path}
    resp.raise_for_status()
    return resp.json()


def _slug_and_registry(arguments):
    slug = str(arguments.get("slug", "")).strip().lower()
    if not slug:
        return None, None, {"error": "missing_slug"}
    registry = arguments.get("registry")
    return slug, registry, None


def _rating_path(slug):
    return f"/rating/{slug}.json"


def _signals_path(slug, registry=None):
    path = f"/signals/{slug}.json"
    return f"{path}?registry={registry}" if registry else path


def _dependencies_path(slug, registry=None):
    path = f"/dependencies/{slug}.json"
    return f"{path}?registry={registry}" if registry else path


def _dimensions_path(slug, registry=None):
    path = f"/dimensions/{slug}.json"
    return f"{path}?registry={registry}" if registry else path


def _prediction_path(slug, registry=None):
    path = f"/prediction/{slug}.json"
    return f"{path}?registry={registry}" if registry else path


def _smedjan_demand_query(sql, params=(), fetchone=False):
    """Run a read-only query against smedjan.ai_demand_scores.

    Isolated so a missing smedjan Python package / unreachable DB degrades
    gracefully (tool returns {"error": "smedjan_unavailable"}) instead of
    crashing the MCP dispatcher.
    """
    try:
        from smedjan import sources
    except Exception as exc:
        return {"error": "smedjan_unavailable", "detail": str(exc)}
    try:
        with sources.smedjan_db_cursor() as (_, cur):
            cur.execute(sql, params)
            if fetchone:
                row = cur.fetchone()
                if row is None:
                    return None
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]
    except Exception as exc:
        return {"error": "smedjan_query_failed", "detail": str(exc)}


def _handle_l4_tool(name, arguments, client):
    if name == "get_rating":
        slug, _, err = _slug_and_registry(arguments)
        if err:
            return err
        return _l4_get(client, _rating_path(slug))

    if name == "bulk_rating_lookup":
        slugs = arguments.get("slugs") or []
        if not isinstance(slugs, list) or not slugs:
            return {"error": "slugs_required"}
        slugs = [str(s).strip().lower() for s in slugs[:25] if s]
        results = []
        for slug in slugs:
            payload = _l4_get(client, _rating_path(slug))
            if isinstance(payload, dict) and payload.get("error") == "slug_not_found":
                results.append({"slug": slug, "status": "not_rated"})
            elif isinstance(payload, dict) and "error" in payload:
                results.append({"slug": slug, "status": "error", "error": payload["error"]})
            else:
                results.append({
                    "slug": slug,
                    "status": "rated",
                    "trust_score": payload.get("trust_score"),
                    "grade": payload.get("trust_grade"),
                    "registry": payload.get("registry"),
                })
        return {"count": len(results), "results": results}

    if name == "rating_dimensions_breakdown":
        slug, _, err = _slug_and_registry(arguments)
        if err:
            return err
        payload = _l4_get(client, _rating_path(slug))
        if isinstance(payload, dict) and "error" in payload:
            return payload
        return {
            "slug": payload.get("slug", slug),
            "trust_score": payload.get("trust_score"),
            "grade": payload.get("trust_grade"),
            "dimensions": payload.get("dimensions") or {},
        }

    if name == "rating_grade_distribution":
        row = _smedjan_demand_query(
            "SELECT COUNT(*) AS total FROM smedjan.ai_demand_scores",
            fetchone=True,
        )
        if isinstance(row, dict) and "error" in row:
            return row
        return {
            "note": "Per-grade counts are computed nightly by the rating pre-warmer.",
            "total_tracked_slugs": (row or {}).get("total", 0),
            "top_100k_floor": "See demand_score_coverage_stats for the floor score.",
        }

    if name == "get_signals":
        slug, registry, err = _slug_and_registry(arguments)
        if err:
            return err
        return _l4_get(client, _signals_path(slug, registry))

    if name == "get_cve_summary":
        slug, registry, err = _slug_and_registry(arguments)
        if err:
            return err
        payload = _l4_get(client, _signals_path(slug, registry))
        if isinstance(payload, dict) and "error" in payload:
            return payload
        sec = ((payload.get("external_trust_signals") or {}).get("security") or {})
        return {
            "slug": payload.get("slug", slug),
            "cve_count": sec.get("cve_count", 0),
            "cve_critical": sec.get("cve_critical", 0),
        }

    if name == "get_openssf_scorecard":
        slug, registry, err = _slug_and_registry(arguments)
        if err:
            return err
        payload = _l4_get(client, _signals_path(slug, registry))
        if isinstance(payload, dict) and "error" in payload:
            return payload
        ets = payload.get("external_trust_signals") or {}
        return {
            "slug": payload.get("slug", slug),
            "openssf_scorecard": ets.get("openssf_scorecard"),
        }

    if name == "get_maintainer_activity":
        slug, registry, err = _slug_and_registry(arguments)
        if err:
            return err
        payload = _l4_get(client, _signals_path(slug, registry))
        if isinstance(payload, dict) and "error" in payload:
            return payload
        activity = ((payload.get("external_trust_signals") or {}).get("activity") or {})
        return {"slug": payload.get("slug", slug), "activity": activity}

    if name == "get_security_attestations":
        slug, registry, err = _slug_and_registry(arguments)
        if err:
            return err
        payload = _l4_get(client, _signals_path(slug, registry))
        if isinstance(payload, dict) and "error" in payload:
            return payload
        sec = ((payload.get("external_trust_signals") or {}).get("security") or {})
        return {
            "slug": payload.get("slug", slug),
            "has_independent_audit": sec.get("has_independent_audit"),
            "has_soc2": sec.get("has_soc2"),
            "has_iso27001": sec.get("has_iso27001"),
        }

    if name == "get_dependencies":
        slug, registry, err = _slug_and_registry(arguments)
        if err:
            return err
        return _l4_get(client, _dependencies_path(slug, registry))

    if name == "check_dormant_dependency":
        slug, registry, err = _slug_and_registry(arguments)
        if err:
            return err
        payload = _l4_get(client, _dependencies_path(slug, registry))
        if isinstance(payload, dict) and "error" in payload:
            return payload
        deps = payload.get("dependencies") or {}
        return {
            "slug": payload.get("slug", slug),
            "dormant": bool(deps.get("dormant")),
            "dormant_reason": deps.get("dormant_reason"),
            "dormant_threshold_days": deps.get("dormant_threshold_days"),
        }

    if name == "get_dimensions":
        slug, registry, err = _slug_and_registry(arguments)
        if err:
            return err
        return _l4_get(client, _dimensions_path(slug, registry))

    if name == "get_prediction":
        slug, registry, err = _slug_and_registry(arguments)
        if err:
            return err
        return _l4_get(client, _prediction_path(slug, registry))

    if name == "lookup_demand_score":
        slug, _, err = _slug_and_registry(arguments)
        if err:
            return err
        row = _smedjan_demand_query(
            "SELECT slug, score FROM smedjan.ai_demand_scores WHERE slug = %s",
            (slug,), fetchone=True,
        )
        if isinstance(row, dict) and "error" in row:
            return row
        if not row:
            return {"slug": slug, "in_top_100k": False}
        return {"slug": slug, "in_top_100k": True, "score": row.get("score")}

    if name == "top_demand_assets":
        limit = min(int(arguments.get("limit", 25) or 25), 500)
        offset = max(int(arguments.get("offset", 0) or 0), 0)
        rows = _smedjan_demand_query(
            "SELECT slug, score FROM smedjan.ai_demand_scores "
            "ORDER BY score DESC, slug ASC LIMIT %s OFFSET %s",
            (limit, offset),
        )
        if isinstance(rows, dict) and "error" in rows:
            return rows
        return {"count": len(rows or []), "results": rows or []}

    if name == "demand_score_percentile":
        slug, _, err = _slug_and_registry(arguments)
        if err:
            return err
        row = _smedjan_demand_query(
            "SELECT COUNT(*) AS below FROM smedjan.ai_demand_scores "
            "WHERE score <= (SELECT score FROM smedjan.ai_demand_scores WHERE slug = %s)",
            (slug,), fetchone=True,
        )
        total_row = _smedjan_demand_query(
            "SELECT COUNT(*) AS total FROM smedjan.ai_demand_scores",
            fetchone=True,
        )
        if isinstance(row, dict) and "error" in row:
            return row
        if isinstance(total_row, dict) and "error" in total_row:
            return total_row
        below = (row or {}).get("below") or 0
        total = (total_row or {}).get("total") or 0
        if not total or not below:
            return {"slug": slug, "in_top_100k": False}
        pct = round(100.0 * below / total, 2)
        return {"slug": slug, "in_top_100k": True, "percentile": pct, "total_tracked": total}

    if name == "demand_score_coverage_stats":
        row = _smedjan_demand_query(
            "SELECT COUNT(*) AS total, MIN(score) AS min_score, "
            "MAX(score) AS max_score, AVG(score) AS avg_score "
            "FROM smedjan.ai_demand_scores",
            fetchone=True,
        )
        if isinstance(row, dict) and "error" in row:
            return row
        return {
            "total_slugs": (row or {}).get("total"),
            "min_score": float((row or {}).get("min_score") or 0),
            "max_score": float((row or {}).get("max_score") or 0),
            "avg_score": float((row or {}).get("avg_score") or 0),
        }

    # Registry-filtered search: proxy to /v1/discover with a type hint.
    _REGISTRY_TYPE_MAP = {
        "search_npm_packages": "npm_package",
        "search_pypi_packages": "pypi_package",
        "search_mcp_servers_curated": "mcp_server",
        "search_huggingface_models": "huggingface_model",
        "search_github_repos": "github_repo",
        "search_crates_packages": "crates_package",
    }
    if name in _REGISTRY_TYPE_MAP:
        port = os.getenv("API_PORT", "8000")
        body = {
            "need": arguments.get("need", ""),
            "type": _REGISTRY_TYPE_MAP[name],
            "limit": min(int(arguments.get("limit", 10) or 10), 50),
        }
        resp = client.post(f"http://localhost:{port}/v1/discover", json=body)
        resp.raise_for_status()
        return resp.json()

    if name == "list_registries":
        return {
            "count": len(_REGISTRY_URL_PATTERNS),
            "registries": [
                {"id": rid, "url_pattern": pattern}
                for rid, pattern in sorted(_REGISTRY_URL_PATTERNS.items())
            ],
        }

    if name == "list_trust_dimensions":
        return {"count": len(_UNIVERSAL_DIMENSIONS), "dimensions": _UNIVERSAL_DIMENSIONS}

    if name == "list_jurisdictions":
        port = os.getenv("API_PORT", "8000")
        try:
            resp = client.get(f"http://localhost:{port}/v1/jurisdictions")
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {
            "note": "Live endpoint unavailable; returning reference stub.",
            "count": 52,
            "examples": [
                {"id": "eu_ai_act", "name": "EU AI Act", "country": "EU"},
                {"id": "us_co_sb205", "name": "Colorado AI Act (SB205)", "country": "US"},
                {"id": "us_ca_sb53", "name": "California SB53", "country": "US"},
                {"id": "uk_ai_regulation", "name": "UK AI Regulation", "country": "UK"},
            ],
        }

    if name == "get_llms_txt_url":
        return {
            "llms_txt": "https://nerq.ai/llms.txt",
            "llms_full": "https://nerq.ai/llms-full.txt",
        }

    if name == "list_rss_feeds":
        return {
            "feeds": [
                {"title": "Nerq — All updates", "url": "https://nerq.ai/rss.xml"},
                {"title": "Nerq — npm", "url": "https://nerq.ai/rss/npm.xml"},
                {"title": "Nerq — PyPI", "url": "https://nerq.ai/rss/pypi.xml"},
                {"title": "Nerq — crates.io", "url": "https://nerq.ai/rss/crates.xml"},
                {"title": "Nerq — MCP servers", "url": "https://nerq.ai/rss/mcp.xml"},
                {"title": "Nerq — High-risk alerts", "url": "https://nerq.ai/rss/alerts.xml"},
            ]
        }

    if name == "get_install_snippet":
        slug, _, err = _slug_and_registry(arguments)
        if err:
            return err
        return {
            "slug": slug,
            "claude_desktop": {
                "mcpServers": {
                    slug: {"command": "npx", "args": ["-y", slug]},
                },
            },
            "cursor": {"mcpServers": {slug: {"command": "npx", "args": ["-y", slug]}}},
            "vscode": {"mcp.servers": {slug: {"command": "npx", "args": ["-y", slug]}}},
            "note": "Generic npx snippet; verify the package name and replace with python/pip snippet if the server ships as a Python package.",
        }

    return {"error": f"l4_handler_not_implemented: {name}"}


def _call_tool(name, arguments):
    port = os.getenv("API_PORT", "8000")
    base_url = f"http://localhost:{port}/v1"
    try:
        client = httpx.Client(timeout=30)
        if name in _L4_TOOLS:
            return _handle_l4_tool(name, arguments, client)
        if name == "discover_agents":
            response = client.post(f"{base_url}/discover", json={
                "need": arguments.get("need", ""),
                "category": arguments.get("category"),
                "protocols": arguments.get("protocols"),
                "min_quality": arguments.get("min_quality", 0.0),
            })
            response.raise_for_status()
            return response.json()
        elif name == "get_agent_details":
            response = client.get(f"{base_url}/agent/{arguments.get('agent_id', '')}")
            response.raise_for_status()
            return response.json()
        elif name == "agent_index_stats":
            response = client.get(f"{base_url}/stats")
            response.raise_for_status()
            return response.json()
        elif name in ("nerq_crypto_rating", "nerq_crypto_ndd", "nerq_crypto_safety",
                       "nerq_crypto_signals", "nerq_crypto_compare"):
            # Proxy crypto tools to the main API
            if name == "nerq_crypto_rating":
                response = client.get(f"{base_url}/crypto/rating/{arguments['token_id']}")
            elif name == "nerq_crypto_ndd":
                response = client.get(f"{base_url}/crypto/ndd/{arguments['token_id']}")
            elif name == "nerq_crypto_safety":
                response = client.get(f"{base_url}/check/{arguments['token_id']}")
            elif name == "nerq_crypto_signals":
                response = client.get(f"{base_url}/crypto/signals")
            elif name == "nerq_crypto_compare":
                response = client.get(f"{base_url}/crypto/compare/{arguments['token1']}/{arguments['token2']}")
            response.raise_for_status()
            return response.json()
        elif name == "find_best_agent":
            cat = arguments.get("category", "")
            min_trust = arguments.get("min_trust_score", 50)
            response = client.get(
                f"{base_url}/agent/search",
                params={"domain": cat, "min_trust": min_trust, "limit": 5}
            )
            response.raise_for_status()
            return response.json()
        elif name == "agent_benchmark":
            cat = arguments.get("category", "")
            response = client.get(f"{base_url}/agent/benchmark/{cat}")
            response.raise_for_status()
            return response.json()
        elif name == "get_agent_stats":
            response = client.get(f"{base_url}/agent/stats")
            response.raise_for_status()
            return response.json()
        elif name == "preflight_trust_check":
            params = {"target": arguments.get("target", "")}
            if arguments.get("caller"):
                params["caller"] = arguments["caller"]
            response = client.get(f"{base_url}/preflight", params=params)
            response.raise_for_status()
            return response.json()
        elif name == "kya_report":
            agent_name = arguments.get("name", "")
            response = client.get(f"{base_url}/agent/kya/{agent_name}",
                                  headers={"X-API-Key": "nerq-internal-2026"})
            response.raise_for_status()
            return response.json()
        elif name == "nerq_scout_status":
            response = client.get(f"http://localhost:{port}/v1/scout/status",
                                  headers={"X-API-Key": "nerq-internal-2026"})
            response.raise_for_status()
            return response.json()
        elif name == "nerq_scout_findings":
            limit = arguments.get("limit", 10)
            response = client.get(f"http://localhost:{port}/v1/scout/findings",
                                  params={"limit": limit},
                                  headers={"X-API-Key": "nerq-internal-2026"})
            response.raise_for_status()
            return response.json()
        else:
            return {"error": f"Unknown tool: {name}"}
    except Exception as e:
        return {"error": str(e)}


def handle_jsonrpc(request):
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "agentindex", "version": "0.4.0"},
        }}
    elif method == "tools/list":
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        result = _call_tool(tool_name, arguments)
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
        }}
    elif method == "notifications/initialized":
        return None
    elif method == "ping":
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": {}}
    else:
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}}


async def sse_endpoint(request: Request):
    if request.method == "POST":
        try:
            body = await request.json()
            logger.info(f"POST /sse: {body.get('method', 'unknown')}")
            response = handle_jsonrpc(body)
            if response:
                return JSONResponse(response)
            return JSONResponse({"ok": True}, status_code=202)
        except Exception as e:
            logger.error(f"POST /sse error: {e}")
            return JSONResponse({"error": str(e)}, status_code=400)

    session_id = str(uuid.uuid4())
    queue = asyncio.Queue()
    sessions[session_id] = queue
    logger.info(f"SSE session started: {session_id}")

    async def event_generator():
        yield {"event": "endpoint", "data": f"https://mcp.agentcrawl.dev/messages?session_id={session_id}"}
        try:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {"event": "message", "data": json.dumps(message)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        except asyncio.CancelledError:
            pass
        finally:
            sessions.pop(session_id, None)
            logger.info(f"SSE session ended: {session_id}")

    return EventSourceResponse(event_generator())


async def messages_endpoint(request: Request):
    session_id = request.query_params.get("session_id")
    if not session_id or session_id not in sessions:
        return JSONResponse({"error": "Invalid or expired session_id"}, status_code=400)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": JSONRPC_VERSION, "id": None,
                             "error": {"code": -32700, "message": "Parse error"}}, status_code=400)
    logger.info(f"[{session_id[:8]}] {body.get('method', 'unknown')}")
    response = handle_jsonrpc(body)
    if response is not None:
        await sessions[session_id].put(response)
    return JSONResponse({"ok": True}, status_code=202)


async def health_endpoint(request: Request):
    return JSONResponse({"status": "ok", "transport": "sse", "server": "agentindex-mcp"})


async def server_card(request: Request):
    return JSONResponse(SERVER_CARD)


app = Starlette(routes=[
    Route("/sse", sse_endpoint, methods=["GET", "POST"]),
    Route("/messages", messages_endpoint, methods=["POST", "GET"]),
    Route("/health", health_endpoint),
    Route("/.well-known/mcp/server-card.json", server_card),
])


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    port = int(os.getenv("MCP_SSE_PORT", "8300"))
    logger.info(f"AgentIndex MCP SSE Server starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
