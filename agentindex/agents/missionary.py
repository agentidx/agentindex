"""
AgentIndex Missionary (Missionären)

Responsible for making AgentIndex discoverable by other agents
through machine-native channels. No human marketing — only
protocols, packages, and machine-readable presence.

Channels:
1. MCP Registry registration
2. pip/npm package publishing
3. agent.md specification
4. MCP server endpoint (so agents can use us as a tool)
"""

import json
import logging
import os
from datetime import datetime

logger = logging.getLogger("agentindex.missionary")


# --- Channel 1: MCP Server Definition ---

MCP_SERVER_MANIFEST = {
    "name": "agentindex",
    "version": "0.1.0",
    "description": "Discovery service for AI agents. Find any agent by capability.",
    "tools": [
        {
            "name": "discover_agents",
            "description": "Find AI agents that can perform a specific task or have specific capabilities. Returns ranked list of matching agents with invocation details.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "need": {
                        "type": "string",
                        "description": "Natural language description of what you need an agent to do"
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category filter: coding, research, content, legal, data, finance, marketing, design, devops, security, education, health, communication, productivity",
                        "enum": ["coding", "research", "content", "legal", "data", "finance", "marketing", "design", "devops", "security", "education", "health", "communication", "productivity"]
                    },
                    "protocols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Required protocols: mcp, a2a, rest, grpc, websocket"
                    },
                    "min_quality": {
                        "type": "number",
                        "description": "Minimum quality score 0.0-1.0",
                        "default": 0.0
                    }
                },
                "required": ["need"]
            }
        },
        {
            "name": "get_agent_details",
            "description": "Get detailed information about a specific agent by ID",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent UUID from discover_agents results"
                    }
                },
                "required": ["agent_id"]
            }
        },
        {
            "name": "get_index_stats",
            "description": "Get statistics about the AgentIndex: total agents, categories, protocols",
            "inputSchema": {
                "type": "object",
                "properties": {}
            }
        }
    ]
}


def generate_mcp_manifest() -> str:
    """Generate MCP server manifest JSON."""
    return json.dumps(MCP_SERVER_MANIFEST, indent=2)


# --- Channel 2: agent.md specification ---

AGENT_MD_SPEC = """# agent.md Specification v0.1

A standard file for AI agents to declare their capabilities,
making them discoverable by other agents and indexing services.

## Usage

Place an `agent.md` file in the root of your repository or host it at
`/.well-known/agent.md` on your domain.

## Format

```yaml
---
name: your-agent-name
version: 1.0.0
description: One sentence describing what your agent does
capabilities:
  - capability one
  - capability two
  - capability three
category: one of coding|research|content|legal|data|finance|marketing|design|devops|security|education|health|communication|productivity
protocols:
  - mcp
  - rest
invocation:
  type: mcp|api|npm|pip|docker
  install: "npm install your-package"
  endpoint: "https://your-api.com/v1"
pricing:
  model: free|freemium|paid
  price: 0.00
  currency: USD
  unit: per_call|per_month
author: your-name
license: MIT
---

# Your Agent Name

Detailed description of what your agent does and how to use it.
```

## Why

By publishing an agent.md, your agent becomes automatically discoverable
by other agents seeking capabilities. AgentIndex and similar services
crawl and index these files to build a comprehensive directory of
available agents.

## Discovery

Services that index agent.md files:
- AgentIndex discovery API
- MCP registries
- A2A agent card registries
"""


def generate_agent_md_spec() -> str:
    """Generate the agent.md specification document."""
    return AGENT_MD_SPEC


# --- Channel 3: pip package ---

PIP_SETUP_PY = '''"""
agentindex - Discovery SDK for AI agents.

Find any AI agent by capability. Machine-first API.

Usage:
    from agentindex import discover
    
    results = discover("contract review")
    for agent in results:
        print(agent["name"], agent["capabilities"])
"""

from setuptools import setup, find_packages

setup(
    name="agentindex",
    version="0.1.0",
    description="Discovery service for AI agents. Find any agent by capability.",
    long_description="""
# AgentIndex

Discovery service for AI agents. Find any agent by capability.

## Quick Start

```python
from agentindex import discover

# Find agents that can review contracts
results = discover("contract review")

# Find MCP servers for data analysis
results = discover("data analysis", protocols=["mcp"])

# Find high-quality coding agents
results = discover("code review", min_quality=0.7)
```

## As MCP Tool

AgentIndex is available as an MCP server. Add it to your agent's tools
to enable automatic discovery of other agents.

## API

Direct API access:

```
POST https://YOUR_ENDPOINT/v1/discover
{"need": "contract review", "min_quality": 0.5}
```
    """,
    long_description_content_type="text/markdown",
    author="AgentIndex",
    url="https://github.com/agentindex/agentindex-sdk",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=["httpx>=0.25.0"],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries",
        "Programming Language :: Python :: 3",
    ],
    keywords="ai agent discovery mcp a2a llm autonomous",
)
'''

PIP_SDK_CODE = '''"""
AgentIndex Python SDK

Minimal SDK for discovering AI agents.
"""

import httpx
from typing import Optional

DEFAULT_ENDPOINT = "https://YOUR_ENDPOINT/v1"


def discover(
    need: str,
    category: Optional[str] = None,
    protocols: Optional[list] = None,
    min_quality: float = 0.0,
    endpoint: str = DEFAULT_ENDPOINT,
) -> list:
    """
    Find AI agents by capability.
    
    Args:
        need: Natural language description of what you need
        category: Optional category filter
        protocols: Optional list of required protocols
        min_quality: Minimum quality score 0.0-1.0
        endpoint: AgentIndex API endpoint
    
    Returns:
        List of matching agent dicts with name, capabilities, invocation details
    """
    response = httpx.post(
        f"{endpoint}/discover",
        json={
            "need": need,
            "category": category,
            "protocols": protocols,
            "min_quality": min_quality,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("results", [])


def get_agent(agent_id: str, endpoint: str = DEFAULT_ENDPOINT) -> dict:
    """Get detailed info about a specific agent."""
    response = httpx.get(f"{endpoint}/agent/{agent_id}", timeout=30)
    response.raise_for_status()
    return response.json().get("agent", {})


def stats(endpoint: str = DEFAULT_ENDPOINT) -> dict:
    """Get index statistics."""
    response = httpx.get(f"{endpoint}/stats", timeout=30)
    response.raise_for_status()
    return response.json()
'''


# --- Channel 4: npm package ---

NPM_PACKAGE_JSON = {
    "name": "@agentindex/sdk",
    "version": "0.1.0",
    "description": "Discovery service for AI agents. Find any agent by capability.",
    "main": "index.js",
    "keywords": [
        "ai", "agent", "discovery", "mcp", "a2a", "llm",
        "autonomous", "agent-discovery", "agent-index",
        "model-context-protocol", "agent2agent"
    ],
    "license": "MIT",
}

NPM_SDK_CODE = '''/**
 * AgentIndex SDK
 * Discovery service for AI agents. Find any agent by capability.
 */

const DEFAULT_ENDPOINT = "https://YOUR_ENDPOINT/v1";

async function discover(need, options = {}) {
  const { category, protocols, minQuality = 0.0, endpoint = DEFAULT_ENDPOINT } = options;
  
  const response = await fetch(`${endpoint}/discover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      need,
      category,
      protocols,
      min_quality: minQuality,
    }),
  });
  
  if (!response.ok) throw new Error(`AgentIndex error: ${response.status}`);
  const data = await response.json();
  return data.results;
}

async function getAgent(agentId, endpoint = DEFAULT_ENDPOINT) {
  const response = await fetch(`${endpoint}/agent/${agentId}`);
  if (!response.ok) throw new Error(`AgentIndex error: ${response.status}`);
  const data = await response.json();
  return data.agent;
}

async function stats(endpoint = DEFAULT_ENDPOINT) {
  const response = await fetch(`${endpoint}/stats`);
  if (!response.ok) throw new Error(`AgentIndex error: ${response.status}`);
  return response.json();
}

module.exports = { discover, getAgent, stats };
'''


class Missionary:
    """
    Spreads AgentIndex presence through machine-native channels.
    """

    def __init__(self, api_endpoint: str = "https://YOUR_ENDPOINT"):
        self.api_endpoint = api_endpoint

    def generate_all_artifacts(self, output_dir: str = "./missionary_output"):
        """Generate all publishable artifacts."""
        os.makedirs(output_dir, exist_ok=True)

        # MCP manifest
        with open(f"{output_dir}/mcp-manifest.json", "w") as f:
            f.write(generate_mcp_manifest())
        logger.info("Generated MCP manifest")

        # agent.md spec
        with open(f"{output_dir}/agent-md-spec.md", "w") as f:
            f.write(generate_agent_md_spec())
        logger.info("Generated agent.md specification")

        # pip package
        pip_dir = f"{output_dir}/pip-package/agentindex"
        os.makedirs(pip_dir, exist_ok=True)
        with open(f"{output_dir}/pip-package/setup.py", "w") as f:
            f.write(PIP_SETUP_PY.replace("YOUR_ENDPOINT", self.api_endpoint))
        with open(f"{pip_dir}/__init__.py", "w") as f:
            f.write(PIP_SDK_CODE.replace("YOUR_ENDPOINT", self.api_endpoint))
        logger.info("Generated pip package")

        # npm package
        npm_dir = f"{output_dir}/npm-package"
        os.makedirs(npm_dir, exist_ok=True)
        with open(f"{npm_dir}/package.json", "w") as f:
            json.dump(NPM_PACKAGE_JSON, f, indent=2)
        with open(f"{npm_dir}/index.js", "w") as f:
            f.write(NPM_SDK_CODE.replace("YOUR_ENDPOINT", self.api_endpoint))
        logger.info("Generated npm package")

        # Our own agent.md (for our repo)
        our_agent_md = f"""---
name: agentindex
version: 0.1.0
description: Discovery service for AI agents. Find any agent by capability, protocol, or category.
capabilities:
  - agent discovery
  - capability search
  - agent ranking
  - protocol-agnostic search
  - MCP server discovery
  - A2A agent discovery
category: productivity
protocols:
  - mcp
  - rest
invocation:
  type: api
  endpoint: "{self.api_endpoint}/v1"
pricing:
  model: free
author: agentindex
---

# AgentIndex

The most comprehensive index of AI agents. Search by capability, category, or protocol.

## API

```
POST {self.api_endpoint}/v1/discover
{{"need": "what you need", "min_quality": 0.5}}
```

## MCP

Available as MCP tool. Add to your agent's toolset for automatic agent discovery.

## SDK

```
pip install agentindex
npm install @agentindex/sdk
```
"""
        with open(f"{output_dir}/agent.md", "w") as f:
            f.write(our_agent_md)
        logger.info("Generated our agent.md")

        logger.info(f"All missionary artifacts generated in {output_dir}")

    def get_publish_checklist(self) -> list:
        """Return checklist of publishing actions needed."""
        return [
            "[ ] Register MCP server in Anthropic MCP Registry",
            "[ ] Publish pip package: cd pip-package && python -m build && twine upload dist/*",
            "[ ] Publish npm package: cd npm-package && npm publish",
            "[ ] Create GitHub repo with agent.md in root",
            "[ ] Submit PR to awesome-mcp-servers list",
            "[ ] Submit PR to modelcontextprotocol/servers if applicable",
            "[ ] Register in A2A protocol registry if available",
        ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    missionary = Missionary(api_endpoint="https://YOUR_ENDPOINT")
    missionary.generate_all_artifacts()

    print("\nPublish checklist:")
    for item in missionary.get_publish_checklist():
        print(f"  {item}")
