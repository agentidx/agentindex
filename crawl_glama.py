#!/usr/bin/env python3
"""
Glama.ai MCP Registry Crawler

Fetches all MCP servers from Glama's API and imports them into AgentIndex.
Glama has 17,600+ MCP servers — the largest MCP registry.

API: https://glama.ai/api/mcp/v1/servers (paginated, cursor-based)

Usage:
    python3 crawl_glama.py
"""

import requests
import psycopg2
import psycopg2.extras
import json
import logging
import os
import time
import uuid
import hashlib
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [glama] %(message)s")
logger = logging.getLogger("glama")

DB_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex')
GLAMA_API = "https://glama.ai/api/mcp/v1/servers"
PAGE_SIZE = 100  # Max per page
SOURCE = "glama_mcp"


def generate_agent_id(name: str, source: str) -> str:
    """Generate deterministic UUID from name + source."""
    raw = f"{source}:{name}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


def classify_domains(server: dict) -> list:
    """Extract domains from server attributes and description."""
    domains = set()
    desc = (server.get('description') or '').lower()
    attrs = server.get('attributes') or []
    tags = server.get('tags') or []
    all_text = f"{desc} {' '.join(attrs)} {' '.join(tags)}"

    domain_keywords = {
        'healthcare': ['health', 'medical', 'clinical', 'patient', 'diagnosis', 'fhir', 'hl7'],
        'finance': ['finance', 'banking', 'payment', 'trading', 'stock', 'crypto', 'invoice', 'stripe'],
        'legal': ['legal', 'law', 'compliance', 'contract', 'regulation'],
        'education': ['education', 'learning', 'academic', 'course', 'tutor'],
        'security': ['security', 'auth', 'encryption', 'vulnerability', 'pentest', 'cybersecurity'],
        'code': ['code', 'github', 'git', 'developer', 'programming', 'ide', 'cursor', 'vscode'],
        'media': ['image', 'video', 'audio', 'content', 'creative', 'design', 'art'],
        'nlp': ['language', 'text', 'translation', 'nlp', 'chat', 'conversation'],
        'science': ['research', 'science', 'data', 'analytics', 'arxiv'],
        'transportation': ['transport', 'vehicle', 'driving', 'navigation', 'maps'],
    }

    for domain, keywords in domain_keywords.items():
        if any(kw in all_text for kw in keywords):
            domains.add(domain)

    return list(domains) if domains else ['general']


def extract_tags(server: dict) -> list:
    """Extract tags from server data."""
    tags = set()

    # From attributes
    for attr in (server.get('attributes') or []):
        tags.add(attr.replace(':', '-'))

    # From tools
    for tool in (server.get('tools') or []):
        name = tool.get('name', '')
        if name:
            tags.add(f"tool:{name}")

    # From repository topics
    repo = server.get('repository') or {}
    for topic in (repo.get('topics') or []):
        tags.add(topic)

    return list(tags)[:20]  # Max 20 tags


def fetch_all_servers():
    """Fetch all servers from Glama API with cursor pagination."""
    all_servers = []
    cursor = None
    page = 0

    while True:
        params = {'limit': PAGE_SIZE}
        if cursor:
            params['cursor'] = cursor

        try:
            resp = requests.get(GLAMA_API, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"API error: {e}")
            break

        servers = data.get('servers', [])
        if not servers:
            break

        all_servers.extend(servers)
        page += 1
        logger.info(f"Page {page}: {len(servers)} servers (total: {len(all_servers)})")

        page_info = data.get('pageInfo', {})
        if not page_info.get('hasNextPage'):
            break

        cursor = page_info.get('endCursor')
        time.sleep(0.3)  # Be polite

    return all_servers


def import_to_db(servers: list):
    """Import Glama servers into agentindex database."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # Check existing
    cur.execute("SELECT name FROM agents WHERE source = %s", (SOURCE,))
    existing = {r[0] for r in cur.fetchall()}
    logger.info(f"Existing {SOURCE} agents: {len(existing)}")

    inserted = 0
    updated = 0
    skipped = 0

    for server in servers:
        repo = server.get('repository') or {}
        repo_url = repo.get('url', '')
        owner = repo.get('owner', '')
        repo_name = repo.get('name', '')

        # Build canonical name
        if owner and repo_name:
            name = f"{owner}/{repo_name}"
        elif repo_url:
            name = repo_url.replace('https://github.com/', '').strip('/')
        else:
            name = server.get('id', f"glama-{uuid.uuid4().hex[:8]}")

        agent_id = generate_agent_id(name, SOURCE)
        description = (server.get('description') or '')[:2000]
        domains = classify_domains(server)
        tags = extract_tags(server)

        # Extract tools as capabilities
        capabilities = []
        for tool in (server.get('tools') or [])[:10]:
            tool_name = tool.get('name', '')
            if tool_name:
                capabilities.append(tool_name)

        # Stars and metadata
        stars = repo.get('stars', 0) or 0
        source_url = repo_url or f"https://glama.ai/mcp/servers/{server.get('id', '')}"
        license_info = repo.get('license', '')

        # Raw metadata
        raw_meta = {
            'glama_id': server.get('id'),
            'attributes': server.get('attributes'),
            'tools': server.get('tools'),
            'environmentVariablesJsonSchema': server.get('environmentVariablesJsonSchema'),
            'repository': repo,
            'created_at': server.get('createdAt'),
            'updated_at': server.get('updatedAt'),
        }

        if name in existing:
            # Update existing
            try:
                cur.execute("""
                    UPDATE agents SET 
                        description = COALESCE(NULLIF(%s, ''), description),
                        domains = %s,
                        tags = %s,
                        capabilities = %s,
                        stars = GREATEST(stars, %s),
                        source_url = COALESCE(NULLIF(%s, ''), source_url),
                        raw_metadata = raw_metadata || %s,
                        last_crawled = NOW()
                    WHERE name = %s AND source = %s
                """, (description, domains, tags, capabilities, stars,
                      source_url, json.dumps(raw_meta), name, SOURCE))
                updated += 1
            except Exception as e:
                logger.error(f"Update error for {name}: {e}")
                conn.rollback()
                continue
        else:
            # Insert new
            try:
                cur.execute("""
                    INSERT INTO agents (id, name, description, source, source_url, 
                        agent_type, domains, tags, capabilities, stars, license,
                        protocols, raw_metadata, crawl_status, is_active,
                        first_indexed, last_crawled)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (id) DO NOTHING
                """, (agent_id, name, description, SOURCE, source_url,
                      'mcp_server', domains, tags, capabilities, stars,
                      license_info, ['mcp'], json.dumps(raw_meta),
                      'indexed', True))
                inserted += 1
            except Exception as e:
                logger.error(f"Insert error for {name}: {e}")
                conn.rollback()
                continue

        if (inserted + updated) % 500 == 0:
            conn.commit()
            logger.info(f"Progress: {inserted} inserted, {updated} updated, {skipped} skipped")

    conn.commit()

    logger.info(f"\n{'='*60}")
    logger.info(f"GLAMA IMPORT COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Total fetched: {len(servers)}")
    logger.info(f"Inserted: {inserted}")
    logger.info(f"Updated: {updated}")
    logger.info(f"Skipped: {skipped}")
    logger.info(f"Already existed: {len(existing)}")

    conn.close()
    return inserted, updated


def run():
    """Main entry point."""
    logger.info("Starting Glama MCP registry crawl...")
    logger.info(f"API: {GLAMA_API}")

    # Fetch all servers
    servers = fetch_all_servers()
    logger.info(f"Fetched {len(servers)} servers from Glama")

    if not servers:
        logger.error("No servers fetched — aborting")
        return

    # Import to database
    inserted, updated = import_to_db(servers)

    # Run classification on new agents
    if inserted > 0:
        logger.info(f"\nClassifying {inserted} new agents...")
        try:
            from classify_agents_rules import classify_unclassified
            classify_unclassified()
            logger.info("Classification complete")
        except Exception as e:
            logger.info(f"Auto-classification skipped: {e}")
            logger.info("Run: python3 classify_agents_rules.py")


if __name__ == "__main__":
    run()
