"""
Nerq MCP Server v2 — AI Agent Compliance as a Service

Exposes Nerq's 5M+ AI asset compliance database as MCP tools.
Any MCP-compatible AI (Claude, GPT, etc.) can check compliance status
for AI agents across 52 global jurisdictions.

This is Nerq's killer feature: instant compliance intelligence for AI systems.

Usage (stdio, for Claude Desktop / MCP clients):
    python -m agentindex.mcp_server_v2

MCP config:
    {
        "nerq": {
            "command": "python",
            "args": ["-m", "agentindex.mcp_server_v2"]
        }
    }
"""

import json
import sys
import os
import logging

sys.path.insert(0, os.path.expanduser("~/agentindex"))

from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

logger = logging.getLogger("nerq.mcp")

JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"

# ============================================================
# TOOL DEFINITIONS
# ============================================================

TOOLS = [
    {
        "name": "check_compliance",
        "description": (
            "Check an AI agent's compliance status across 52 global jurisdictions "
            "including EU AI Act, Colorado AI Act, California SB53, UK AI regulation, "
            "and more. Returns per-jurisdiction risk level, status, triggered criteria, "
            "and compliance notes. Use when user asks 'is X compliant?', 'can I deploy X in the EU?', "
            "'what regulations apply to X?', or needs to assess regulatory risk for any AI system "
            "before deploying it in production."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Agent name, ID, or search term to find the agent"
                },
                "jurisdictions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: specific jurisdiction IDs to check (e.g. ['eu_ai_act', 'us_co_sb205']). If omitted, returns all 52."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "discover_agents",
        "description": (
            "Search 5 million+ AI assets including agents, tools, MCP servers, models, datasets, "
            "and packages by capability, domain, or name. Returns ranked results with trust scores, "
            "risk classification, compliance score, and source info. Use when user asks 'find a tool for X', "
            "'what agents do Y?', 'list MCP servers for Z', or needs to discover AI assets for a specific task."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "need": {
                    "type": "string",
                    "description": "What you need an agent to do, or a name/keyword to search for"
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter",
                    "enum": ["coding", "research", "content", "legal", "data",
                             "finance", "marketing", "design", "devops", "security",
                             "education", "health", "communication", "productivity",
                             "infrastructure"]
                },
                "risk_class": {
                    "type": "string",
                    "description": "Filter by risk class",
                    "enum": ["minimal", "limited", "high", "unacceptable"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 10, max 50)",
                    "default": 10
                }
            },
            "required": ["need"]
        }
    },
    {
        "name": "get_agent_details",
        "description": (
            "Get full details for a specific AI agent or tool including description, capabilities, "
            "compliance score, risk classification across all 52 jurisdictions, and metadata. "
            "Use after discover_agents to get complete information about a specific result, "
            "or when user asks 'tell me more about X', 'what does X do?', or needs the full profile."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Agent UUID or name"
                }
            },
            "required": ["agent_id"]
        }
    },
    {
        "name": "compliance_summary",
        "description": (
            "Get aggregated compliance statistics across the AI ecosystem. How many agents are high-risk? "
            "Which jurisdictions flag the most agents? What domains have the highest risk? "
            "Use when user asks 'how many high-risk AI agents are there?', 'which jurisdictions are strictest?', "
            "or needs data for reports, dashboards, and regulatory analysis."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "group_by": {
                    "type": "string",
                    "description": "Group statistics by dimension",
                    "enum": ["jurisdiction", "risk_class", "agent_type", "domain"],
                    "default": "risk_class"
                },
                "jurisdiction_id": {
                    "type": "string",
                    "description": "Optional: filter to specific jurisdiction"
                }
            }
        }
    },
    {
        "name": "nerq_stats",
        "description": "Get overview statistics about Nerq's database: total AI assets indexed (5M+), jurisdictions covered (52), risk distribution, and source breakdown. Use when user asks 'how many AI agents exist?', 'how big is the Nerq database?', or wants ecosystem-level stats.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]

SERVER_INFO = {
    "name": "nerq",
    "version": "2.0.0",
    "description": (
        "Nerq: The AI Asset Search Engine. "
        "5M+ AI assets indexed & trust scored across 52 global jurisdictions. "
        "Check compliance status for any AI agent instantly."
    )
}

# ============================================================
# DATABASE ACCESS
# ============================================================

def _get_db():
    """Get database connection."""
    from agentindex.db_config import get_read_conn
    return get_read_conn()


def _query(sql, params=None, fetchone=False):
    """Execute query and return results as list of dicts."""
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(sql, params or ())
    cols = [d[0] for d in cur.description]
    if fetchone:
        row = cur.fetchone()
        conn.close()
        return dict(zip(cols, row)) if row else None
    rows = cur.fetchall()
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


# ============================================================
# TOOL IMPLEMENTATIONS
# ============================================================

def _check_compliance(args):
    """Check compliance for an agent across jurisdictions."""
    query = args.get("query", "")
    jurisdictions = args.get("jurisdictions")
    
    # Find the agent
    agent = _query(
        """SELECT id, name, description, agent_type, risk_class,
                  compliance_score, eu_risk_class,
                  trust_score_v2, trust_grade
           FROM entity_lookup
           WHERE id::text = %s OR name ILIKE %s OR name_lower LIKE %s
           LIMIT 1""",
        (query, query, f"%{query.lower()}%"),
        fetchone=True
    )
    
    if not agent:
        return {"error": f"Agent not found: {query}", "suggestion": "Try discover_agents to search"}
    
    # Fetch jurisdiction statuses
    j_sql = """
        SELECT ajs.jurisdiction_id, ajs.status, ajs.risk_level, 
               ajs.triggered_criteria, ajs.compliance_notes,
               jr.name as jurisdiction_name, jr.country, jr.effective_date,
               jr.penalty_max
        FROM agent_jurisdiction_status ajs
        JOIN jurisdiction_registry jr ON jr.id = ajs.jurisdiction_id
        WHERE ajs.agent_id = %s
    """
    j_params = [agent['id']]
    
    if jurisdictions:
        j_sql += " AND ajs.jurisdiction_id = ANY(%s)"
        j_params.append(jurisdictions)
    
    j_sql += " ORDER BY ajs.risk_level DESC, jr.name"
    
    statuses = _query(j_sql, j_params)
    
    # Count risk levels
    high = sum(1 for j in statuses if j['risk_level'] in ('high', 'unacceptable'))
    limited = sum(1 for j in statuses if j['risk_level'] == 'limited')
    minimal = sum(1 for j in statuses if j['risk_level'] == 'minimal')
    
    return {
        "agent": {
            "id": agent['id'],
            "name": agent['name'],
            "type": agent['agent_type'],
            "trust_score": agent.get('trust_score_v2'),
            "trust_grade": agent.get('trust_grade'),
            "risk_class": agent['risk_class'],
            "compliance_score": agent['compliance_score'],
        },
        "summary": {
            "jurisdictions_checked": len(statuses),
            "high_risk": high,
            "limited_risk": limited,
            "minimal_risk": minimal
        },
        "jurisdictions": [
            {
                "id": j['jurisdiction_id'],
                "name": j['jurisdiction_name'],
                "country": j['country'],
                "risk_level": j['risk_level'],
                "status": j['status'],
                "triggered_criteria": j['triggered_criteria'],
                "notes": j['compliance_notes'],
                "effective_date": str(j['effective_date']) if j['effective_date'] else None,
                "max_penalty": j['penalty_max']
            }
            for j in statuses
        ]
    }


def _discover_agents(args):
    """Search for agents."""
    need = args.get("need", "")
    category = args.get("category")
    risk_class = args.get("risk_class")
    limit = min(args.get("limit", 10), 50)
    
    conditions = ["(name ILIKE %s OR description ILIKE %s)"]
    params = [f"%{need}%", f"%{need}%"]
    
    if category:
        conditions.append("category = %s")
        params.append(category)
    if risk_class:
        conditions.append("risk_class = %s")
        params.append(risk_class)
    
    where = " AND ".join(conditions)
    params.append(limit)
    
    agents = _query(f"""
        SELECT id, name, description, agent_type, risk_class,
               compliance_score, source, stars, downloads,
               trust_score_v2, trust_grade
        FROM entity_lookup
        WHERE {where} AND is_active = true
        ORDER BY trust_score_v2 DESC NULLS LAST, stars DESC NULLS LAST
        LIMIT %s
    """, params)
    
    return {
        "results": len(agents),
        "agents": [
            {
                "id": a['id'],
                "name": a['name'],
                "description": (a['description'] or '')[:200],
                "type": a['agent_type'],
                "trust_score": a.get('trust_score_v2'),
                "trust_grade": a.get('trust_grade'),
                "risk_class": a['risk_class'],
                "compliance_score": a['compliance_score'],
                "domains": a['domains'],
                "source": a['source'],
                "stars": a['stars'],
                "downloads": a['downloads']
            }
            for a in agents
        ]
    }


def _get_agent_details(args):
    """Get full agent details with compliance."""
    agent_id = args.get("agent_id", "")

    agent = _query(
        """SELECT id, name, description, agent_type, risk_class,
                  compliance_score, eu_risk_class, source, source_url, author,
                  stars, downloads, license,
                  first_indexed
           FROM entity_lookup WHERE id::text = %s OR name ILIKE %s LIMIT 1""",
        (agent_id, agent_id),
        fetchone=True
    )
    
    if not agent:
        return {"error": f"Agent not found: {agent_id}"}
    
    # Get jurisdiction summary
    j_summary = _query("""
        SELECT risk_level, COUNT(*) as count
        FROM agent_jurisdiction_status 
        WHERE agent_id = %s 
        GROUP BY risk_level
    """, (agent['id'],))
    
    return {
        "agent": {
            k: (str(v) if k == 'first_indexed' and v else v)
            for k, v in agent.items()
        },
        "compliance": {
            "score": agent['compliance_score'],
            "risk_class": agent['risk_class'],
            "jurisdictions_assessed": sum(j['count'] for j in j_summary),
            "risk_breakdown": {j['risk_level']: j['count'] for j in j_summary}
        }
    }


def _compliance_summary(args):
    """Get aggregated compliance statistics."""
    group_by = args.get("group_by", "risk_class")
    jurisdiction_id = args.get("jurisdiction_id")
    
    if group_by == "risk_class":
        return {"summary": _query(
            "SELECT risk_class, COUNT(*) as count FROM entity_lookup WHERE risk_class IS NOT NULL GROUP BY risk_class ORDER BY count DESC"
        )}
    
    elif group_by == "jurisdiction":
        sql = """
            SELECT jurisdiction_id, risk_level, COUNT(*) as count
            FROM agent_jurisdiction_status
        """
        params = []
        if jurisdiction_id:
            sql += " WHERE jurisdiction_id = %s"
            params.append(jurisdiction_id)
        sql += " GROUP BY jurisdiction_id, risk_level ORDER BY jurisdiction_id, count DESC"
        # Use sampling for speed on 253M rows
        return {"summary": _query(sql.replace("FROM agent_jurisdiction_status", 
                "FROM agent_jurisdiction_status TABLESAMPLE SYSTEM(1)"), params)}
    
    elif group_by == "agent_type":
        return {"summary": _query(
            "SELECT agent_type, risk_class, COUNT(*) as count FROM entity_lookup WHERE agent_type IS NOT NULL GROUP BY agent_type, risk_class ORDER BY count DESC LIMIT 50"
        )}

    elif group_by == "domain":
        return {"summary": _query(
            "SELECT risk_class, COUNT(*) as count FROM entity_lookup WHERE risk_class IS NOT NULL GROUP BY risk_class ORDER BY count DESC LIMIT 50"
        )}
    
    return {"error": f"Unknown group_by: {group_by}"}


def _nerq_stats(args):
    """Get overview statistics."""
    stats = _query("SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE is_active) as active FROM entity_lookup", fetchone=True)
    risk = _query("SELECT risk_class, COUNT(*) as count FROM entity_lookup GROUP BY risk_class ORDER BY count DESC")
    types = _query("SELECT agent_type, COUNT(*) as count FROM entity_lookup GROUP BY agent_type ORDER BY count DESC LIMIT 10")
    sources = _query("SELECT source, COUNT(*) as count FROM entity_lookup GROUP BY source ORDER BY count DESC LIMIT 10")
    j_count = _query("SELECT COUNT(*) as count FROM jurisdiction_registry", fetchone=True)
    
    return {
        "database": {
            "total_agents": stats['total'],
            "active_agents": stats['active'],
            "jurisdictions": j_count['count'],
            "last_updated": "2026-02-23"
        },
        "risk_distribution": {r['risk_class']: r['count'] for r in risk if r['risk_class']},
        "agent_types": {t['agent_type']: t['count'] for t in types if t['agent_type']},
        "top_sources": {s['source']: s['count'] for s in sources}
    }


TOOL_HANDLERS = {
    "check_compliance": _check_compliance,
    "discover_agents": _discover_agents,
    "get_agent_details": _get_agent_details,
    "compliance_summary": _compliance_summary,
    "nerq_stats": _nerq_stats,
}

# ============================================================
# MCP PROTOCOL (STDIO)
# ============================================================

def handle_jsonrpc(request):
    """Handle a JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})
    
    if method == "initialize":
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": req_id,
            "result": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "serverInfo": SERVER_INFO,
                "capabilities": {
                    "tools": {"listChanged": False}
                }
            }
        }
    
    elif method == "notifications/initialized":
        return None  # No response for notifications
    
    elif method == "tools/list":
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": req_id,
            "result": {"tools": TOOLS}
        }
    
    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        
        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": f"Unknown tool: {tool_name}"})}],
                    "isError": True
                }
            }
        
        try:
            result = handler(arguments)
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, default=str, ensure_ascii=False)}],
                    "isError": False
                }
            }
        except Exception as e:
            logger.error(f"Tool error {tool_name}: {e}")
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
                    "isError": True
                }
            }
    
    elif method == "ping":
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": {}}
    
    else:
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }


def main():
    """Run MCP server over stdio."""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                       format="%(asctime)s [nerq-mcp] %(message)s")
    logger.info("Nerq MCP Server v2.0 starting (stdio mode)")
    logger.info(f"Tools: {[t['name'] for t in TOOLS]}")
    
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({
                "jsonrpc": JSONRPC_VERSION,
                "error": {"code": -32700, "message": "Parse error"}
            }) + "\n")
            sys.stdout.flush()
            continue
        
        response = handle_jsonrpc(request)
        
        if response is not None:
            sys.stdout.write(json.dumps(response, default=str) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
