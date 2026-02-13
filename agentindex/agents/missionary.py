"""
AgentIndex Missionary 2.0 (Missionären)

Proactive agent that spreads AgentIndex presence through machine-native
and human-discoverable channels. Runs daily as a scheduled job.

Capabilities:
1. Scans for new registries/awesome-lists to register on
2. Generates PR texts with live stats from API
3. Monitors API + Smithery traffic
4. Finds new distribution channels
5. Suggests new search terms for spiders
6. Tracks where we're listed vs not
7. Generates daily action report
8. Auto-updates agent.md/README with live stats
9. Monitors competitors/similar services
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
from agentindex.agents.action_queue import add_action, ActionLevel

logger = logging.getLogger("agentindex.missionary")

API_ENDPOINT = os.getenv("API_PUBLIC_ENDPOINT", "https://api.agentcrawl.dev")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")


class Missionary:
    def __init__(self):
        self.session = get_session()
        self.client = httpx.Client(timeout=30)
        self.github_headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        }
        self.report = {
            "timestamp": datetime.utcnow().isoformat(),
            "actions": [],
            "stats": {},
            "new_channels": [],
            "new_sources": [],
            "new_search_terms": [],
            "competitors": [],
            "presence_tracker": {},
        }

    # --- Filters ---

    IRRELEVANT_KEYWORDS = [
        "chinese", "中文", "leetcode", "interview", "面试", "课程",
        "tutorial", "学习", "笔记", "shop", "mall", "商城", "电商",
        "blog", "博客", "cms", "admin", "后台", "管理系统",
        "wechat", "微信", "weixin", "小程序", "android", "ios",
        "spring", "springboot", "springcloud", "mybatis", "thinkphp",
        "laravel", "django", "flask", "爬虫", "crawler", "spider",
        "game", "游戏", "music", "音乐", "video", "视频",
        "php", "java", "golang", "rust", "ruby", "swift",
        "vpn", "proxy", "shadowsocks", "v2ray", "trojan",
        "docker", "kubernetes", "k8s", "devops", "linux",
        "blockchain", "bitcoin", "crypto", "stock", "量化",
        "awesome-go", "awesome-python", "awesome-java", "awesome-rust",
        "finance", "trading", "compression", "security", "json",
        "nacos", "consul", "eureka", "pageindex", "service-mesh",
        "kubernetes", "操作", "数据", "算法", "编程",
    ]

    RELEVANT_KEYWORDS = [
        "agent", "mcp", "autonomous agent",
        "discovery", "registry", "directory",
        "langchain", "crewai", "autogen",
        "function-calling", "tool-use", "a2a", "agent2agent",
        "agentic", "multi-agent", "agent framework",
    ]

    def _is_relevant(self, repo: dict) -> bool:
        """Check if a repo is relevant to agent/MCP ecosystem."""
        name = (repo.get("name", "") or "").lower()
        desc = (repo.get("description", "") or "").lower()
        full = name + " " + desc

        # Must have at least one relevant keyword
        has_relevant = any(kw in full for kw in self.RELEVANT_KEYWORDS)
        if not has_relevant:
            return False

        # Must not be dominated by irrelevant keywords
        irrelevant_count = sum(1 for kw in self.IRRELEVANT_KEYWORDS if kw in full)
        if irrelevant_count >= 2:
            return False

        return True

    def _is_english(self, text: str) -> bool:
        """Check if text is primarily English/ASCII."""
        if not text:
            return False
        # Reject if contains CJK characters
        cjk_count = sum(1 for c in text if 0x4E00 <= ord(c) <= 0x9FFF)
        if cjk_count > 2:
            return False
        ascii_count = sum(1 for c in text if ord(c) < 128)
        return (ascii_count / len(text)) > 0.85

    # --- Filters ---

    IRRELEVANT_KEYWORDS = [
        "chinese", "中文", "leetcode", "interview", "面试", "课程",
        "tutorial", "学习", "笔记", "shop", "mall", "商城", "电商",
        "blog", "博客", "cms", "admin", "后台", "管理系统",
        "wechat", "微信", "weixin", "小程序", "android", "ios",
        "spring", "springboot", "springcloud", "mybatis", "thinkphp",
        "laravel", "django", "flask", "爬虫", "crawler", "spider",
        "game", "游戏", "music", "音乐", "video", "视频",
        "php", "java", "golang", "rust", "ruby", "swift",
        "vpn", "proxy", "shadowsocks", "v2ray", "trojan",
        "docker", "kubernetes", "k8s", "devops", "linux",
        "blockchain", "bitcoin", "crypto", "stock", "量化",
        "awesome-go", "awesome-python", "awesome-java", "awesome-rust",
        "finance", "trading", "compression", "security", "json",
        "nacos", "consul", "eureka", "pageindex", "service-mesh",
        "kubernetes", "操作", "数据", "算法", "编程",
    ]

    RELEVANT_KEYWORDS = [
        "agent", "mcp", "autonomous agent",
        "discovery", "registry", "directory",
        "langchain", "crewai", "autogen",
        "function-calling", "tool-use", "a2a", "agent2agent",
        "agentic", "multi-agent", "agent framework",
    ]

    def _is_relevant(self, repo: dict) -> bool:
        """Check if a repo is relevant to agent/MCP ecosystem."""
        name = (repo.get("name", "") or "").lower()
        desc = (repo.get("description", "") or "").lower()
        full = name + " " + desc

        # Must have at least one relevant keyword
        has_relevant = any(kw in full for kw in self.RELEVANT_KEYWORDS)
        if not has_relevant:
            return False

        # Must not be dominated by irrelevant keywords
        irrelevant_count = sum(1 for kw in self.IRRELEVANT_KEYWORDS if kw in full)
        if irrelevant_count >= 2:
            return False

        return True

    def _is_english(self, text: str) -> bool:
        """Check if text is primarily English/ASCII."""
        if not text:
            return False
        # Reject if contains CJK characters
        cjk_count = sum(1 for c in text if 0x4E00 <= ord(c) <= 0x9FFF)
        if cjk_count > 2:
            return False
        ascii_count = sum(1 for c in text if ord(c) < 128)
        return (ascii_count / len(text)) > 0.85

    def run_daily(self) -> dict:
        logger.info("Missionary 2.0 daily run starting...")
        self._collect_stats()
        self._scan_awesome_lists()
        self._scan_registries()
        self._find_new_channels()
        self._suggest_search_terms()
        self._monitor_competitors()
        self._track_presence()
        self._generate_pr_texts()
        self._auto_update_repo_stats()
        self._save_report()
        logger.info(f"Missionary 2.0 complete. Actions: {len(self.report['actions'])}")
        return self.report

    def _collect_stats(self):
        try:
            response = self.client.get(f"{API_ENDPOINT}/v1/stats")
            if response.status_code == 200:
                self.report["stats"] = response.json()
                logger.info(f"Stats collected")
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

    AWESOME_LISTS = [
        {"repo": "punkpeye/awesome-mcp-servers", "name": "Awesome MCP Servers", "stars": 30000, "pr_status": "submitted"},
        {"repo": "e2b-dev/awesome-ai-agents", "name": "Awesome AI Agents", "stars": 10000, "pr_status": "not_submitted"},
        {"repo": "kyrolabs/awesome-langchain", "name": "Awesome LangChain", "stars": 7000, "pr_status": "not_submitted"},
        {"repo": "f/awesome-chatgpt-prompts", "name": "Awesome ChatGPT Prompts", "stars": 100000, "pr_status": "not_relevant"},
        {"repo": "Shubhamsaboo/awesome-llm-apps", "name": "Awesome LLM Apps", "stars": 5000, "pr_status": "not_submitted"},
        {"repo": "filipecalegario/awesome-generative-ai", "name": "Awesome Generative AI", "stars": 5000, "pr_status": "not_submitted"},
        {"repo": "aimerou/awesome-ai-papers", "name": "Awesome AI Papers", "stars": 3000, "pr_status": "not_relevant"},
        {"repo": "mahseema/awesome-ai-tools", "name": "Awesome AI Tools", "stars": 3000, "pr_status": "not_submitted"},
    ]

    def _scan_awesome_lists(self):
        logger.info("Scanning for awesome lists...")
        search_queries = [
            "awesome ai agents",
            "awesome mcp",
            "awesome llm tools",
            "awesome autonomous agents",
            "awesome agent framework",
        ]
        found_lists = []
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
                        if stars > 1000 and repo_full not in [a["repo"] for a in self.AWESOME_LISTS]:
                            desc = repo.get("description", "") or ""
                            if self._is_english(desc) and self._is_relevant(repo):
                                found_lists.append({
                                    "repo": repo_full,
                                    "name": repo["name"],
                                    "stars": stars,
                                    "description": desc,
                                    "url": repo["html_url"],
                                })
            except Exception as e:
                logger.error(f"GitHub search error for '{query}': {e}")
        if found_lists:
            seen = set()
            unique = []
            for lst in found_lists:
                if lst["repo"] not in seen:
                    seen.add(lst["repo"])
                    unique.append(lst)
                    self.report["actions"].append(
                        f"NEW AWESOME LIST: {lst['name']} ({lst['stars']}*) - {lst['url']}"
                    )
                    add_action("add_awesome_list", f"Track: {lst['name']}",
                              {"repo": lst["repo"], "name": lst["name"], "stars": lst["stars"], "url": lst["url"]})
            self.report["new_channels"].extend(unique)
            logger.info(f"Found {len(unique)} new awesome lists")
        for lst in self.AWESOME_LISTS:
            if lst["pr_status"] == "submitted":
                self._check_pr_status(lst)

    def _check_pr_status(self, awesome_list):
        try:
            response = self.client.get(
                f"https://api.github.com/repos/{awesome_list['repo']}/pulls",
                params={"state": "all", "per_page": 20},
                headers=self.github_headers,
            )
            if response.status_code == 200:
                for pr in response.json():
                    if "agentindex" in pr.get("title", "").lower() or "agentcrawl" in pr.get("title", "").lower():
                        state = pr["state"]
                        merged = pr.get("merged_at") is not None
                        if merged:
                            self.report["actions"].append(f"PR MERGED: {awesome_list['name']}")
                        elif state == "closed":
                            self.report["actions"].append(f"PR CLOSED: {awesome_list['name']} - consider resubmitting")
                        else:
                            self.report["actions"].append(f"PR PENDING: {awesome_list['name']} - waiting for review")
                        return
        except Exception as e:
            logger.error(f"PR status check error: {e}")

    REGISTRIES = [
        {"name": "Smithery", "url": "https://smithery.ai/server/agentidx/agentcrawl", "status": "listed"},
        {"name": "MCP Hub", "url": "https://mcphub.io", "status": "not_registered"},
        {"name": "Glama", "url": "https://glama.ai/mcp/servers", "status": "not_registered"},
        {"name": "PulseMCP", "url": "https://pulsemcp.com", "status": "not_registered"},
        {"name": "mcp.run", "url": "https://mcp.run", "status": "not_registered"},
        {"name": "Composio MCP", "url": "https://composio.dev/mcp", "status": "not_registered"},
    ]

    def _scan_registries(self):
        logger.info("Scanning MCP registries...")
        for registry in self.REGISTRIES:
            if registry["status"] == "not_registered":
                self.report["actions"].append(f"REGISTER: {registry['name']} at {registry['url']}")
                add_action("register_registry", f"Register: {registry['name']}",
                          {"name": registry["name"], "url": registry["url"]})
        try:
            response = self.client.get(
                "https://api.github.com/search/repositories",
                params={"q": "mcp registry OR mcp hub OR mcp directory", "sort": "stars", "per_page": 10},
                headers=self.github_headers,
            )
            if response.status_code == 200:
                for repo in response.json().get("items", []):
                    name = repo["full_name"]
                    if name not in [r.get("repo", "") for r in self.REGISTRIES]:
                        stars = repo.get("stargazers_count", 0)
                        if stars > 500 and self._is_relevant(repo) and self._is_english(repo.get("description", "") or ""):
                            self.report["new_channels"].append({
                                "type": "registry", "name": repo["name"],
                                "repo": name, "stars": stars, "url": repo["html_url"],
                            })
                            self.report["actions"].append(f"NEW REGISTRY: {repo['name']} ({stars}*) - {repo['html_url']}")
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
                        stars = repo.get("stargazers_count", 0)
                        if stars > 1000 and self._is_relevant(repo) and self._is_english(repo.get("description", "") or ""):
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
                        topics = repo.get("topics", [])
                        for topic in topics:
                            if topic not in self._get_existing_search_terms() and "agent" in topic:
                                new_terms.append(topic)
            except Exception as e:
                logger.error(f"Search term suggestion error: {e}")
        unique_terms = list(set(new_terms))[:10]
        if unique_terms:
            self.report["new_search_terms"] = unique_terms
            self.report["actions"].append(f"NEW SEARCH TERMS: Consider adding: {', '.join(unique_terms)}")
            for term in unique_terms[:5]:
                add_action("add_search_term", f"Add search term: {term}", {"term": term})

    def _get_existing_search_terms(self):
        return [
            "ai-agent", "ai agent framework", "autonomous agent", "llm agent",
            "mcp-server", "mcp server", "model context protocol", "mcp tool",
            "langchain agent", "crewai agent", "autogen agent", "llamaindex agent",
            "coding agent", "research agent", "agent framework python",
            "agent orchestration", "multi-agent system", "agent2agent", "a2a protocol",
        ]

    def _monitor_competitors(self):
        logger.info("Monitoring competitors...")
        competitor_queries = [
            "agent discovery service", "agent registry api",
            "mcp server discovery", "ai agent index", "agent directory api",
        ]
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
                        if "agentidx" not in name and "agentindex" not in name.lower():
                            stars = repo.get("stargazers_count", 0)
                            if stars > 200 and self._is_relevant(repo) and self._is_english(repo.get("description", "") or "") and repo["name"].lower() not in ["nacos", "pageindex", "consul", "eureka", "etcd", "zookeeper"]:
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
                add_action("new_competitor", f"Competitor: {c['name']}",
                          {"name": c["name"], "stars": c["stars"], "url": c["url"]})

    def _track_presence(self):
        logger.info("Tracking presence...")
        presence = {
            "api": {"url": "https://api.agentcrawl.dev", "status": "unknown"},
            "dashboard": {"url": "https://dash.agentcrawl.dev", "status": "unknown"},
            "mcp_sse": {"url": "https://mcp.agentcrawl.dev", "status": "unknown"},
            "github": {"url": "https://github.com/agentidx/agentindex", "status": "unknown"},
            "pypi": {"url": "https://pypi.org/project/agentcrawl/", "status": "unknown", "version": "0.3.1"},
            "npm": {"url": "https://www.npmjs.com/package/@agentidx/sdk", "status": "unknown", "version": "0.3.0", "needs_update": True},
            "smithery": {"url": "https://smithery.ai/server/agentidx/agentcrawl", "status": "unknown"},
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
                add_action("endpoint_down", f"Endpoint down: {ep}",
                          {"endpoint": ep, "url": presence[ep].get("url", "")})

    def _generate_pr_texts(self):
        stats = self.report.get("stats", {})
        total = stats.get("total_active", 20000)
        sources = stats.get("sources", {})
        categories = list(stats.get("top_categories", {}).keys())[:10]
        pr_texts = {}
        pr_texts["awesome-ai-agents"] = {
            "title": "Add AgentIndex - AI agent discovery platform",
            "body": f"## AgentIndex\n\n**Discovery platform for AI agents.** Find any AI agent by capability - search {total:,}+ indexed agents across {len(sources)} sources.\n\n- **API:** https://api.agentcrawl.dev\n- **MCP Server:** [Smithery](https://smithery.ai/server/agentidx/agentcrawl)\n- **SDK:** `pip install agentcrawl` | `npm install @agentidx/sdk`\n- **GitHub:** https://github.com/agentidx/agentindex\n\n### What it does\nAgentIndex crawls and indexes all publicly available AI agents (GitHub, npm, MCP, HuggingFace) so that agents can automatically discover and hire other agents.\n\n### Categories\n{', '.join(categories)}\n\n### Usage\n```python\nfrom agentcrawl import discover\nagents = discover('code review', min_quality=0.7)\n```\n",
        }
        pr_texts["awesome-langchain"] = {
            "title": "Add AgentIndex - agent discovery for LangChain projects",
            "body": f"## AgentIndex\n\nDiscovery API for finding AI agents by capability. Index of {total:,}+ agents.\n\n- **API:** https://api.agentcrawl.dev\n- **SDK:** `pip install agentcrawl`\n- **MCP Server:** [Smithery](https://smithery.ai/server/agentidx/agentcrawl)\n- **GitHub:** https://github.com/agentidx/agentindex\n\n```python\nfrom agentcrawl import discover\nagents = discover('data analysis agent', protocols=['rest'])\n```\n",
        }
        self.report["pr_texts"] = pr_texts
        for name in ["awesome-ai-agents", "awesome-langchain"]:
            lst = next((a for a in self.AWESOME_LISTS if name.replace("-", " ") in a["name"].lower()), None)
            if lst and lst.get("pr_status") == "not_submitted":
                self.report["actions"].append(f"SUBMIT PR: {name} - PR text ready in report")
                add_action("submit_pr", f"PR: {name}",
                          {"repo": lst["repo"], "title": pr_texts[name]["title"], "body": pr_texts[name]["body"]})

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
                content = re.sub(
                    r'description:.*',
                    f'description: Discovery service for AI agents. {total:,}+ agents indexed across GitHub, npm, MCP, HuggingFace.',
                    content, count=1,
                )
                with open(agent_md_path, "w") as f:
                    f.write(content)
                self.report["actions"].append(f"UPDATED: agent.md with {total:,} agents")
                add_action("update_agent_md", "Update agent.md", {"total": total})
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
        summary += "## Presence Status\n"
        for name, info in presence.items():
            emoji = "+" if info.get("status") == "live" else "X"
            summary += f"- [{emoji}] **{name}**: {info.get('url', 'N/A')} ({info.get('status', 'unknown')})\n"
        summary += f"\n## Actions Required ({len(actions)})\n"
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
        if self.report.get("pr_texts"):
            summary += "\n## Ready PR Texts\n"
            for name, pr in self.report["pr_texts"].items():
                summary += f"### {name}\n**Title:** {pr['title']}\n\n"
        return summary

    # Legacy compatibility
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
    print(f"\nActions: {len(report['actions'])}")
    for action in report["actions"]:
        print(f"  -> {action}")
