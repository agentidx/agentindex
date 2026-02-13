"""
AgentIndex Missionary 2.0 (Missionaren) - Refactored

REFACTOR v3: Full idempotency via missionary_state.json
- All awesome lists, registries, and channel state persisted to disk
- run_daily() checks state before creating ANY action
- No duplicate actions even after restart
- State updated by Executor when actions complete
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional

import httpx
from agentindex.db.models import Agent, get_session
from sqlalchemy import select, func, text
from agentindex.agents.action_queue import add_action, ActionLevel, load_queue, load_history

logger = logging.getLogger("agentindex.missionary")

API_ENDPOINT = os.getenv("API_PUBLIC_ENDPOINT", "https://api.agentcrawl.dev")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
STATE_PATH = os.path.expanduser("~/agentindex/missionary_state.json")

DEFAULT_STATE = {
    "awesome_lists": {
        "punkpeye/awesome-mcp-servers": {"name": "Awesome MCP Servers", "stars": 30000, "pr_status": "submitted"},
        "e2b-dev/awesome-ai-agents": {"name": "Awesome AI Agents", "stars": 10000, "pr_status": "submitted"},
        "kyrolabs/awesome-langchain": {"name": "Awesome LangChain", "stars": 7000, "pr_status": "blocked"},
        "f/awesome-chatgpt-prompts": {"name": "Awesome ChatGPT Prompts", "stars": 100000, "pr_status": "not_relevant"},
        "Shubhamsaboo/awesome-llm-apps": {"name": "Awesome LLM Apps", "stars": 5000, "pr_status": "not_submitted"},
        "filipecalegario/awesome-generative-ai": {"name": "Awesome Generative AI", "stars": 5000, "pr_status": "not_submitted"},
        "aimerou/awesome-ai-papers": {"name": "Awesome AI Papers", "stars": 3000, "pr_status": "not_relevant"},
        "mahseema/awesome-ai-tools": {"name": "Awesome AI Tools", "stars": 3000, "pr_status": "not_submitted"},
        "appcypher/awesome-mcp-servers": {"name": "Awesome MCP Servers (appcypher)", "stars": 5100, "pr_status": "submitted"},
        "kaushikb11/awesome-llm-agents": {"name": "Awesome LLM Agents", "stars": 1300, "pr_status": "submitted"},
        "Arindam200/awesome-ai-apps": {"name": "Awesome AI Apps", "stars": 8900, "pr_status": "submitted"},
        "sickn33/antigravity-awesome-skills": {"name": "Antigravity Awesome Skills", "stars": 8700, "pr_status": "submitted"},
    },
    "registries": {
        "smithery": {"name": "Smithery", "url": "https://smithery.ai/server/agentidx/agentcrawl", "status": "listed"},
        "mcphub": {"name": "MCP Hub", "url": "https://mcphub.io", "status": "not_registered"},
        "glama": {"name": "Glama", "url": "https://glama.ai/mcp/servers", "status": "not_registered"},
        "pulsemcp": {"name": "PulseMCP", "url": "https://pulsemcp.com", "status": "not_registered"},
        "mcp.run": {"name": "mcp.run", "url": "https://mcp.run", "status": "not_registered"},
        "composio": {"name": "Composio MCP", "url": "https://composio.dev/mcp", "status": "not_registered"},
    },
    "discovered_channels": {},
    "search_terms_suggested": [],
    "competitors_seen": [],
    "endpoints_alerted": {},
    "last_run": None,
}


class MissionaryState:
    def __init__(self, path: str = STATE_PATH):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    loaded = json.load(f)
                merged = json.loads(json.dumps(DEFAULT_STATE))
                for key in merged:
                    if key in loaded:
                        if isinstance(merged[key], dict) and isinstance(loaded[key], dict):
                            merged[key].update(loaded[key])
                        else:
                            merged[key] = loaded[key]
                return merged
            except Exception as e:
                logger.error(f"Failed to load state, using defaults: {e}")
                return json.loads(json.dumps(DEFAULT_STATE))
        return json.loads(json.dumps(DEFAULT_STATE))

    def save(self):
        self.data["last_run"] = datetime.utcnow().isoformat()
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=2, default=str)
        os.replace(tmp, self.path)

    def awesome_list_needs_tracking(self, repo: str) -> bool:
        return repo not in self.data["awesome_lists"]

    def set_awesome_list(self, repo: str, info: dict):
        self.data["awesome_lists"][repo] = info

    def registry_needs_action(self, key: str) -> bool:
        info = self.data["registries"].get(key)
        if not info:
            return True
        return info.get("status") == "not_registered"

    def channel_already_discovered(self, repo: str) -> bool:
        return repo in self.data["discovered_channels"]

    def add_discovered_channel(self, repo: str, info: dict):
        self.data["discovered_channels"][repo] = {**info, "discovered_at": datetime.utcnow().isoformat()}

    def term_already_suggested(self, term: str) -> bool:
        return term in self.data["search_terms_suggested"]

    def mark_term_suggested(self, term: str):
        if term not in self.data["search_terms_suggested"]:
            self.data["search_terms_suggested"].append(term)

    def competitor_already_seen(self, repo: str) -> bool:
        return repo in self.data["competitors_seen"]

    def mark_competitor_seen(self, repo: str):
        if repo not in self.data["competitors_seen"]:
            self.data["competitors_seen"].append(repo)

    def endpoint_alerted_today(self, endpoint: str) -> bool:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        return self.data["endpoints_alerted"].get(endpoint) == today

    def mark_endpoint_alerted(self, endpoint: str):
        self.data["endpoints_alerted"][endpoint] = datetime.utcnow().strftime("%Y-%m-%d")

    def clear_endpoint_alert(self, endpoint: str):
        self.data["endpoints_alerted"].pop(endpoint, None)


IRRELEVANT_KEYWORDS = [
    "chinese", "leetcode", "interview", "tutorial",
    "shop", "mall", "blog", "cms", "admin",
    "wechat", "android", "ios",
    "spring", "springboot", "springcloud", "mybatis", "thinkphp",
    "laravel", "django", "flask", "crawler", "spider",
    "game", "music", "video",
    "php", "java", "golang", "rust", "ruby", "swift",
    "vpn", "proxy", "shadowsocks", "v2ray", "trojan",
    "docker", "kubernetes", "k8s", "devops", "linux",
    "blockchain", "bitcoin", "crypto", "stock",
    "awesome-go", "awesome-python", "awesome-java", "awesome-rust",
    "finance", "trading", "compression", "security", "json",
    "nacos", "consul", "eureka", "pageindex", "service-mesh",
]

RELEVANT_KEYWORDS = [
    "agent", "mcp", "autonomous agent",
    "discovery", "registry", "directory",
    "langchain", "crewai", "autogen",
    "function-calling", "tool-use", "a2a", "agent2agent",
    "agentic", "multi-agent", "agent framework",
]

EXISTING_SEARCH_TERMS = [
    "ai-agent", "ai agent framework", "autonomous agent", "llm agent",
    "mcp-server", "mcp server", "model context protocol", "mcp tool",
    "langchain agent", "crewai agent", "autogen agent", "llamaindex agent",
    "coding agent", "research agent", "agent framework python",
    "agent orchestration", "multi-agent system", "agent2agent", "a2a protocol",
]


def _is_relevant(repo: dict) -> bool:
    name = (repo.get("name", "") or "").lower()
    desc = (repo.get("description", "") or "").lower()
    full = name + " " + desc
    has_relevant = any(kw in full for kw in RELEVANT_KEYWORDS)
    if not has_relevant:
        return False
    irrelevant_count = sum(1 for kw in IRRELEVANT_KEYWORDS if kw in full)
    if irrelevant_count >= 2:
        return False
    return True


def _is_english(text: str) -> bool:
    if not text:
        return False
    cjk_count = sum(1 for c in text if 0x4E00 <= ord(c) <= 0x9FFF)
    if cjk_count > 2:
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return (ascii_count / len(text)) > 0.85


class Missionary:
    def __init__(self):
        self.session = get_session()
        self.client = httpx.Client(timeout=30)
        self.github_headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        }
        self.state = MissionaryState()
        self.report = {
            "timestamp": datetime.utcnow().isoformat(),
            "actions": [],
            "actions_created": 0,
            "actions_skipped": 0,
            "stats": {},
            "new_channels": [],
            "new_sources": [],
            "new_search_terms": [],
            "competitors": [],
            "presence_tracker": {},
        }

    def _add_action_if_new(self, action_type: str, title: str, details: dict = None) -> bool:
        before_count = len(load_queue())
        add_action(action_type, title, details)
        after_count = len(load_queue())
        if after_count > before_count:
            self.report['actions_created'] += 1
            return True
        self.report['actions_skipped'] += 1
        return False

    def run_daily(self) -> dict:
        logger.info("Missionary 2.0 daily run starting (idempotent mode)...")
        self._collect_stats()
        self._scan_awesome_lists()
        self._scan_registries()
        self._find_new_channels()
        self._suggest_search_terms()
        self._monitor_competitors()
        self._track_presence()
        self._generate_pr_texts()
        self._auto_update_repo_stats()
        self.state.save()
        self._save_report()
        created = self.report["actions_created"]
        skipped = self.report["actions_skipped"]
        logger.info(f"Missionary 2.0 complete. Actions created: {created}, skipped (dedup): {skipped}")
        return self.report

    def _collect_stats(self):
        try:
            response = self.client.get(f"{API_ENDPOINT}/v1/stats")
            if response.status_code == 200:
                self.report["stats"] = response.json()
                logger.info("Stats collected")
        except Exception as e:
            logger.error(f"Failed to collect stats: {e}")
        try:
            result = self.session.execute(
                text("SELECT crawl_status, count(*) FROM agents GROUP BY crawl_status")
            ).fetchall()
            self.report["stats"]["pipeline"] = {row[0]: row[1] for row in result}
            total = self.session.execute(
                text("SELECT count(*) FROM agents WHERE is_active = true")
            ).scalar()
            self.report["stats"]["total_active"] = total
            sources = self.session.execute(
                text("SELECT source, count(*) FROM agents GROUP BY source")
            ).fetchall()
            self.report["stats"]["sources"] = {row[0]: row[1] for row in sources}
            categories = self.session.execute(
                text("SELECT category, count(*) FROM agents WHERE crawl_status IN ('parsed','classified','ranked') GROUP BY category ORDER BY count(*) DESC LIMIT 15")
            ).fetchall()
            self.report["stats"]["top_categories"] = {row[0]: row[1] for row in categories}
        except Exception as e:
            logger.error(f"DB stats error: {e}")

    def _scan_awesome_lists(self):
        logger.info("Scanning for awesome lists...")
        search_queries = [
            "awesome ai agents", "awesome mcp",
            "awesome llm tools", "awesome autonomous agents", "awesome agent framework",
        ]
        for query in search_queries:
            try:
                response = self.client.get(
                    "https://api.github.com/search/repositories",
                    params={"q": f"{query} in:name,description", "sort": "stars", "per_page": 5},
                    headers=self.github_headers,
                )
                if response.status_code == 200:
                    for repo in response.json().get("items", []):
                        repo_full = repo["full_name"]
                        stars = repo.get("stargazers_count", 0)
                        desc = repo.get("description", "") or ""
                        if not self.state.awesome_list_needs_tracking(repo_full):
                            continue
                        if stars > 1000 and _is_english(desc) and _is_relevant(repo):
                            info = {
                                "name": repo["name"], "stars": stars,
                                "pr_status": "not_submitted",
                                "discovered_at": datetime.utcnow().isoformat(),
                            }
                            self.state.set_awesome_list(repo_full, info)
                            self.report["actions"].append(f"NEW AWESOME LIST: {repo['name']} ({stars}*)")
                            self._add_action_if_new(
                                "add_awesome_list", f"Track: {repo['name']}",
                                {"repo": repo_full, "name": repo["name"], "stars": stars, "url": repo["html_url"]},
                            )
                            self.report["new_channels"].append({
                                "repo": repo_full, "name": repo["name"],
                                "stars": stars, "description": desc, "url": repo["html_url"],
                            })
            except Exception as e:
                logger.error(f"GitHub search error for '{query}': {e}")

        for repo, info in self.state.data["awesome_lists"].items():
            if info.get("pr_status") == "submitted":
                self._check_pr_status(repo, info)

    def _check_pr_status(self, repo: str, info: dict):
        try:
            response = self.client.get(
                f"https://api.github.com/repos/{repo}/pulls",
                params={"state": "all", "per_page": 20},
                headers=self.github_headers,
            )
            if response.status_code == 200:
                for pr in response.json():
                    title = pr.get("title", "").lower()
                    if "agentindex" in title or "agentcrawl" in title:
                        state = pr["state"]
                        merged = pr.get("merged_at") is not None
                        if merged:
                            info["pr_status"] = "merged"
                            self.report["actions"].append(f"PR MERGED: {info['name']}")
                        elif state == "closed":
                            info["pr_status"] = "closed"
                            self.report["actions"].append(f"PR CLOSED: {info['name']} - consider resubmitting")
                        else:
                            self.report["actions"].append(f"PR PENDING: {info['name']} - waiting for review")
                        return
        except Exception as e:
            logger.error(f"PR status check error for {repo}: {e}")

    def _scan_registries(self):
        logger.info("Scanning MCP registries...")
        for key, info in self.state.data["registries"].items():
            if self.state.registry_needs_action(key):
                self._add_action_if_new(
                    "register_registry", f"Register: {info['name']}",
                    {"name": info["name"], "url": info["url"], "registry_key": key},
                )
                self.report["actions"].append(f"REGISTER: {info['name']} at {info['url']}")

        try:
            response = self.client.get(
                "https://api.github.com/search/repositories",
                params={"q": "mcp registry OR mcp hub OR mcp directory", "sort": "stars", "per_page": 10},
                headers=self.github_headers,
            )
            if response.status_code == 200:
                for repo in response.json().get("items", []):
                    name = repo["full_name"]
                    stars = repo.get("stargazers_count", 0)
                    if stars > 500 and _is_relevant(repo) and _is_english(repo.get("description", "") or ""):
                        if not self.state.channel_already_discovered(name):
                            self.state.add_discovered_channel(name, {
                                "type": "registry", "name": repo["name"], "stars": stars,
                            })
                            self.report["new_channels"].append({
                                "type": "registry", "name": repo["name"],
                                "repo": name, "stars": stars, "url": repo["html_url"],
                            })
                            self.report["actions"].append(f"NEW REGISTRY: {repo['name']} ({stars}*)")
        except Exception as e:
            logger.error(f"Registry scan error: {e}")

    def _find_new_channels(self):
        logger.info("Finding new channels...")
        channel_searches = [
            "agent marketplace", "ai agent directory",
            "mcp server list", "ai tool directory", "llm tool registry",
        ]
        for query in channel_searches:
            try:
                response = self.client.get(
                    "https://api.github.com/search/repositories",
                    params={"q": query, "sort": "stars", "per_page": 3},
                    headers=self.github_headers,
                )
                if response.status_code == 200:
                    for repo in response.json().get("items", []):
                        repo_full = repo["full_name"]
                        stars = repo.get("stargazers_count", 0)
                        if stars > 1000 and _is_relevant(repo) and _is_english(repo.get("description", "") or ""):
                            if not self.state.channel_already_discovered(repo_full):
                                self.state.add_discovered_channel(repo_full, {
                                    "type": "directory", "name": repo["name"], "stars": stars,
                                })
                                self.report["new_channels"].append({
                                    "type": "directory", "name": repo["name"],
                                    "stars": stars, "url": repo["html_url"],
                                    "description": repo.get("description", ""),
                                })
            except Exception as e:
                logger.error(f"Channel search error: {e}")

    def _suggest_search_terms(self):
        logger.info("Suggesting new search terms...")
        trending_queries = ["ai agent framework", "mcp server tool", "autonomous agent", "llm agent tool"]
        new_terms = []
        for query in trending_queries:
            try:
                response = self.client.get(
                    "https://api.github.com/search/repositories",
                    params={"q": query, "sort": "updated", "per_page": 10},
                    headers=self.github_headers,
                )
                if response.status_code == 200:
                    for repo in response.json().get("items", []):
                        for topic in repo.get("topics", []):
                            if (topic not in EXISTING_SEARCH_TERMS
                                and "agent" in topic
                                and not self.state.term_already_suggested(topic)):
                                new_terms.append(topic)
            except Exception as e:
                logger.error(f"Search term suggestion error: {e}")

        unique_terms = list(set(new_terms))[:10]
        if unique_terms:
            self.report["new_search_terms"] = unique_terms
            self.report["actions"].append(f"NEW SEARCH TERMS: {', '.join(unique_terms)}")
            for term in unique_terms[:5]:
                self.state.mark_term_suggested(term)
                self._add_action_if_new("add_search_term", f"Add search term: {term}", {"term": term})

    def _monitor_competitors(self):
        logger.info("Monitoring competitors...")
        competitor_queries = [
            "agent discovery service", "agent registry api",
            "mcp server discovery", "ai agent index", "agent directory api",
        ]
        skip_names = ["nacos", "pageindex", "consul", "eureka", "etcd", "zookeeper"]
        for query in competitor_queries:
            try:
                response = self.client.get(
                    "https://api.github.com/search/repositories",
                    params={"q": query, "sort": "stars", "per_page": 5},
                    headers=self.github_headers,
                )
                if response.status_code == 200:
                    for repo in response.json().get("items", []):
                        name = repo["full_name"]
                        if "agentidx" in name or "agentindex" in name.lower():
                            continue
                        stars = repo.get("stargazers_count", 0)
                        if (stars > 200 and _is_relevant(repo)
                            and _is_english(repo.get("description", "") or "")
                            and repo["name"].lower() not in skip_names):
                            self.report["competitors"].append({
                                "name": repo["name"], "repo": name, "stars": stars,
                                "description": repo.get("description", ""),
                                "url": repo["html_url"], "updated": repo.get("updated_at", ""),
                            })
            except Exception as e:
                logger.error(f"Competitor search error: {e}")

        if self.report["competitors"]:
            top = sorted(self.report["competitors"], key=lambda x: x["stars"], reverse=True)[:5]
            self.report["actions"].append(
                f"COMPETITORS: Top {len(top)}: " +
                ", ".join(f"{c['name']} ({c['stars']}*)" for c in top)
            )
            for c in top:
                if not self.state.competitor_already_seen(c["repo"]):
                    self.state.mark_competitor_seen(c["repo"])
                    self._add_action_if_new(
                        "new_competitor", f"Competitor: {c['name']}",
                        {"name": c["name"], "stars": c["stars"], "url": c["url"]},
                    )

    def _track_presence(self):
        logger.info("Tracking presence...")
        presence = {
            "api": {"url": "https://api.agentcrawl.dev"},
            "dashboard": {"url": "https://dash.agentcrawl.dev"},
            "mcp_sse": {"url": "https://mcp.agentcrawl.dev"},
            "github": {"url": "https://github.com/agentidx/agentindex"},
            "pypi": {"url": "https://pypi.org/project/agentcrawl/"},
            "npm": {"url": "https://www.npmjs.com/package/@agentidx/sdk"},
            "smithery": {"url": "https://smithery.ai/server/agentidx/agentcrawl"},
        }
        for name, info in presence.items():
            try:
                response = self.client.get(info["url"], follow_redirects=True, timeout=15)
                info["http_status"] = response.status_code
                info["status"] = "live" if response.status_code < 400 else "down"
            except Exception:
                info["status"] = "unreachable"

        self.report["presence_tracker"] = presence
        down = [k for k, v in presence.items() if v["status"] != "live"]
        if down:
            self.report["actions"].append(f"ALERT: Endpoints down: {', '.join(down)}")
            for ep in down:
                if not self.state.endpoint_alerted_today(ep):
                    self.state.mark_endpoint_alerted(ep)
                    self._add_action_if_new(
                        "endpoint_down", f"Endpoint down: {ep}",
                        {"endpoint": ep, "url": presence[ep].get("url", "")},
                    )
        for ep in list(self.state.data["endpoints_alerted"].keys()):
            if ep not in down:
                self.state.clear_endpoint_alert(ep)

    def _generate_pr_texts(self):
        stats = self.report.get("stats", {})
        total = stats.get("total_active", 20000)
        sources = stats.get("sources", {})
        categories = list(stats.get("top_categories", {}).keys())[:10]

        pr_texts = {}
        pr_texts["awesome-ai-agents"] = {
            "title": "Add AgentIndex - AI agent discovery platform",
            "body": (
                f"## AgentIndex\n\n"
                f"**Discovery platform for AI agents.** Find any AI agent by capability - "
                f"search {total:,}+ indexed agents across {len(sources)} sources.\n\n"
                f"- **API:** https://api.agentcrawl.dev\n"
                f"- **MCP Server:** [Smithery](https://smithery.ai/server/agentidx/agentcrawl)\n"
                f"- **SDK:** `pip install agentcrawl` | `npm install @agentidx/sdk`\n"
                f"- **GitHub:** https://github.com/agentidx/agentindex\n\n"
                f"### What it does\n"
                f"AgentIndex crawls and indexes all publicly available AI agents so that agents "
                f"can automatically discover and hire other agents.\n\n"
                f"### Categories\n{', '.join(categories)}\n\n"
                f"### Usage\n```python\nfrom agentcrawl import discover\n"
                f"agents = discover('code review', min_quality=0.7)\n```\n"
            ),
        }
        self.report["pr_texts"] = pr_texts

        for repo, info in self.state.data["awesome_lists"].items():
            if info.get("pr_status") == "not_submitted":
                self._add_action_if_new(
                    "submit_pr", f"PR: {info['name']}",
                    {"repo": repo, "name": info["name"]},
                )

    def _auto_update_repo_stats(self):
        stats = self.report.get("stats", {})
        total = stats.get("total_active", 0)
        if total == 0:
            return
        agent_md_path = os.path.expanduser("~/agentindex/agent.md")
        try:
            if os.path.exists(agent_md_path):
                with open(agent_md_path, "r") as f:
                    content = f.read()
                new_desc = f'description: Discovery service for AI agents. {total:,}+ agents indexed across GitHub, npm, MCP, HuggingFace.'
                if new_desc not in content:
                    content = re.sub(r'description:.*', new_desc, content, count=1)
                    with open(agent_md_path, "w") as f:
                        f.write(content)
                    self.report["actions"].append(f"UPDATED: agent.md with {total:,} agents")
                    self._add_action_if_new("update_agent_md", "Update agent.md", {"total": total})
                    logger.info(f"Updated agent.md with {total:,} agents")
        except Exception as e:
            logger.error(f"Failed to update agent.md: {e}")

    def _save_report(self):
        report_dir = os.path.expanduser("~/agentindex/missionary_reports")
        os.makedirs(report_dir, exist_ok=True)
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        report_path = f"{report_dir}/report-{date_str}.json"
        with open(report_path, "w") as f:
            json.dump(self.report, f, indent=2, default=str)
        summary_path = f"{report_dir}/report-{date_str}.md"
        with open(summary_path, "w") as f:
            f.write(self._generate_summary())
        logger.info(f"Report saved: {report_path}")

    def _generate_summary(self):
        stats = self.report.get("stats", {})
        actions = self.report.get("actions", [])
        presence = self.report.get("presence_tracker", {})
        summary = f"# Missionary Daily Report - {datetime.utcnow().strftime('%Y-%m-%d')}\n\n"
        summary += f"## Index Stats\n- **Total active agents:** {stats.get('total_active', 'N/A')}\n"
        summary += f"- **Sources:** {json.dumps(stats.get('sources', {}))}\n"
        summary += f"- **Pipeline:** {json.dumps(stats.get('pipeline', {}))}\n\n"
        summary += f"## Idempotency Stats\n"
        summary += f"- Actions created: {self.report['actions_created']}\n"
        summary += f"- Actions skipped (dedup): {self.report['actions_skipped']}\n\n"
        summary += "## Presence Status\n"
        for name, info in presence.items():
            emoji = "+" if info.get("status") == "live" else "X"
            summary += f"- [{emoji}] **{name}**: {info.get('url', 'N/A')} ({info.get('status', 'unknown')})\n"
        summary += f"\n## Actions ({len(actions)})\n"
        for i, action in enumerate(actions, 1):
            summary += f"{i}. {action}\n"
        if self.report.get("new_search_terms"):
            summary += f"\n## Suggested New Search Terms\n{', '.join(self.report['new_search_terms'])}\n"
        if self.report.get("competitors"):
            summary += "\n## Competitors\n"
            top_competitors = sorted(self.report["competitors"], key=lambda x: x["stars"], reverse=True)[:5]
            for c in top_competitors:
                desc = (c.get("description", "N/A") or "N/A")[:100]
                summary += f"- **{c['name']}** ({c['stars']}*): {desc}\n"
        return summary

    def generate_all_artifacts(self, output_dir="./missionary_output"):
        self.run_daily()

    def get_publish_checklist(self):
        return self.report.get("actions", [])


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    missionary = Missionary()
    report = missionary.run_daily()
    print(f"\nActions created: {report['actions_created']}, skipped: {report['actions_skipped']}")
    for action in report["actions"]:
        print(f"  -> {action}")
