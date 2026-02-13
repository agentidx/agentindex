"""
AgentIndex Spionen (Competitor Intelligence Agent)

Autonomous competitive intelligence agent that:
1. SCOUT  — discovers new competitors via GitHub search
2. MONITOR — deep-tracks known competitors (stars, commits, releases, features)
3. BENCHMARK — compares KPIs, flags when we're behind
4. ACT — generates actions to close gaps and stay best-in-class

Runs daily at 08:00 UTC via orchestrator.
Reports to dashboard via Action Queue with approval buttons.
"""

import json
import logging
import os
import re
import base64
from datetime import datetime, timedelta
from typing import Optional

import httpx
from agentindex.db.models import Agent, get_session
from sqlalchemy import select, func, text
from agentindex.agents.action_queue import add_action, ActionLevel

logger = logging.getLogger("agentindex.spionen")

API_ENDPOINT = os.getenv("API_PUBLIC_ENDPOINT", "https://api.agentcrawl.dev")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

KNOWN_COMPETITORS = [
    {
        "repo": "agentic-community/mcp-gateway-registry",
        "name": "mcp-gateway-registry",
        "threat_level": "high",
        "features": {
            "agent_discovery": True,
            "a2a_support": True,
            "semantic_search": True,
            "auto_crawling": False,
            "enterprise_auth": True,
            "mcp_support": True,
            "sdk_python": False,
            "sdk_npm": False,
            "multi_source": False,
        },
    },
    {
        "repo": "liuyoshio/mcp-compass",
        "name": "mcp-compass",
        "threat_level": "medium",
        "features": {
            "agent_discovery": True,
            "a2a_support": False,
            "semantic_search": True,
            "auto_crawling": False,
            "enterprise_auth": False,
            "mcp_support": True,
            "sdk_python": False,
            "sdk_npm": True,
            "multi_source": False,
        },
    },
    {
        "repo": "anthropics/claude-plugins-official",
        "name": "claude-plugins-official",
        "threat_level": "medium",
        "features": {
            "agent_discovery": True,
            "a2a_support": False,
            "semantic_search": False,
            "auto_crawling": False,
            "enterprise_auth": False,
            "mcp_support": True,
            "sdk_python": False,
            "sdk_npm": False,
            "multi_source": False,
        },
    },
    {
        "repo": "modelcontextprotocol/registry",
        "name": "registry",
        "threat_level": "high",
        "features": {
            "agent_discovery": True,
            "a2a_support": False,
            "semantic_search": False,
            "auto_crawling": False,
            "enterprise_auth": False,
            "mcp_support": True,
            "sdk_python": False,
            "sdk_npm": False,
            "multi_source": False,
        },
    },
    {
        "repo": "ArchestraAI/archestra",
        "name": "archestra",
        "threat_level": "high",
        "features": {
            "agent_discovery": True,
            "a2a_support": False,
            "semantic_search": False,
            "auto_crawling": False,
            "enterprise_auth": True,
            "mcp_support": True,
            "sdk_python": False,
            "sdk_npm": False,
            "multi_source": False,
        },
    },
    {
        "repo": "ducthinh993/mcp-context-forge",
        "name": "mcp-context-forge",
        "threat_level": "medium",
        "features": {
            "agent_discovery": True,
            "a2a_support": False,
            "semantic_search": False,
            "auto_crawling": False,
            "enterprise_auth": False,
            "mcp_support": True,
            "sdk_python": False,
            "sdk_npm": False,
            "multi_source": False,
        },
    },
]

OUR_FEATURES = {
    "agent_discovery": True,
    "a2a_support": False,
    "semantic_search": False,
    "auto_crawling": True,
    "enterprise_auth": False,
    "mcp_support": True,
    "sdk_python": True,
    "sdk_npm": True,
    "multi_source": True,
}

FEATURE_PRIORITY = {
    "semantic_search": "critical",
    "a2a_support": "critical",
    "enterprise_auth": "high",
    "agent_discovery": "critical",
    "auto_crawling": "critical",
    "mcp_support": "high",
    "sdk_python": "medium",
    "sdk_npm": "medium",
    "multi_source": "high",
}


class Spionen:

    def __init__(self):
        self.session = get_session()
        self.client = httpx.Client(timeout=30)
        self.github_headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        }
        self.report = {
            "timestamp": datetime.utcnow().isoformat(),
            "our_stats": {},
            "competitors": [],
            "new_competitors": [],
            "benchmarks": [],
            "gaps": [],
            "actions": [],
            "feature_matrix": {},
            "trend": {},
        }
        self.competitors_file = os.path.expanduser("~/agentindex/spionen_competitors.json")
        self.history_file = os.path.expanduser("~/agentindex/spionen_history.json")

    def run_daily(self) -> dict:
        logger.info("=" * 50)
        logger.info("Spionen daily intelligence run starting...")
        logger.info("=" * 50)
        self._collect_our_stats()
        self._scout_new_competitors()
        self._monitor_all_competitors()
        self._run_benchmarks()
        self._generate_actions()
        self._save_report()
        self._save_history()
        logger.info(f"Spionen complete. Gaps: {len(self.report['gaps'])}, Actions: {len(self.report['actions'])}")
        return self.report

    def _collect_our_stats(self):
        logger.info("Collecting our stats...")
        stats = {}
        try:
            resp = self.client.get(f"{API_ENDPOINT}/v1/stats", timeout=10)
            if resp.status_code == 200:
                stats["api"] = resp.json()
        except Exception as e:
            logger.error(f"Failed to get API stats: {e}")
        try:
            total = self.session.execute(text("SELECT count(*) FROM agents")).scalar() or 0
            active = self.session.execute(text("SELECT count(*) FROM agents WHERE is_active = true")).scalar() or 0
            sources = self.session.execute(text("SELECT source, count(*) FROM agents GROUP BY source ORDER BY count(*) DESC")).fetchall()
            categories = self.session.execute(text("SELECT count(DISTINCT category) FROM agents WHERE category IS NOT NULL")).scalar() or 0
            day_ago = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            new_24h = self.session.execute(text(f"SELECT count(*) FROM agents WHERE first_indexed > '{day_ago}'")).scalar() or 0
            stats["index_size"] = total
            stats["active_agents"] = active
            stats["sources"] = {row[0]: row[1] for row in sources}
            stats["source_count"] = len(sources)
            stats["category_count"] = categories
            stats["new_24h"] = new_24h
            stats["features"] = OUR_FEATURES.copy()
        except Exception as e:
            logger.error(f"DB stats error: {e}")
        try:
            resp = self.client.get("https://api.github.com/repos/agentidx/agentindex", headers=self.github_headers)
            if resp.status_code == 200:
                repo = resp.json()
                stats["github_stars"] = repo.get("stargazers_count", 0)
                stats["github_forks"] = repo.get("forks_count", 0)
                stats["github_open_issues"] = repo.get("open_issues_count", 0)
                stats["github_watchers"] = repo.get("watchers_count", 0)
        except Exception as e:
            logger.error(f"GitHub stats error: {e}")
        self.report["our_stats"] = stats
        logger.info(f"Our stats: {stats.get('index_size', '?')} agents, {stats.get('github_stars', '?')} stars")

    def _scout_new_competitors(self):
        logger.info("Scouting for new competitors...")
        search_queries = [
            "agent discovery API", "agent registry service",
            "MCP server discovery", "AI agent index",
            "agent directory API", "agent search engine",
            "MCP registry", "agent marketplace API",
            "agentic discovery", "agent2agent discovery",
        ]
        known_repos = set(c["repo"] for c in self._load_competitors())
        known_repos.add("agentidx/agentindex")
        blocklist_names = {
            "nacos", "consul", "eureka", "etcd", "zookeeper", "pageindex",
            "service-mesh", "kubernetes", "k8s",
            # Not discovery platforms — these are agents/tools/lists
            "deep-research", "ui", "hexstrike-ai", "mindsearch",
            "ai-scientist-v2", "spiceai", "awesome-langgraph",
        }
        # Must specifically be about discovery/registry/directory — not just mention "agent"
        discovery_kw = ["discovery", "registry", "directory", "index", "catalog", "gateway", "hub", "marketplace"]
        found = []
        for query in search_queries:
            try:
                resp = self.client.get(
                    "https://api.github.com/search/repositories",
                    params={"q": query, "sort": "stars", "per_page": 10},
                    headers=self.github_headers,
                )
                if resp.status_code == 200:
                    for repo in resp.json().get("items", []):
                        full_name = repo["full_name"]
                        name = repo["name"].lower()
                        stars = repo.get("stargazers_count", 0)
                        desc = repo.get("description", "") or ""
                        if full_name in known_repos or name in blocklist_names or stars < 100:
                            continue
                        text_combined = f"{name} {desc}".lower()
                        relevant_kw = ["agent", "mcp", "discovery", "registry", "directory", "a2a", "agentic"]
                        if not any(kw in text_combined for kw in relevant_kw):
                            continue
                        # Must be a discovery/registry platform, not just an agent
                        if not any(dkw in text_combined for dkw in discovery_kw):
                            continue
                        if desc:
                            cjk = sum(1 for c in desc if 0x4E00 <= ord(c) <= 0x9FFF)
                            if cjk > 2:
                                continue
                        found.append({
                            "repo": full_name, "name": repo["name"], "stars": stars,
                            "description": desc[:200], "url": repo["html_url"],
                            "updated_at": repo.get("updated_at", ""),
                            "created_at": repo.get("created_at", ""),
                            "language": repo.get("language", ""),
                        })
                        known_repos.add(full_name)
                elif resp.status_code == 403:
                    logger.warning("GitHub API rate limit hit during scouting")
                    break
            except Exception as e:
                logger.error(f"Scout search error for '{query}': {e}")
        seen = set()
        unique = []
        for c in sorted(found, key=lambda x: x["stars"], reverse=True):
            if c["repo"] not in seen:
                seen.add(c["repo"])
                unique.append(c)
        self.report["new_competitors"] = unique
        if unique:
            logger.info(f"Found {len(unique)} new potential competitors")
            for c in unique[:10]:
                logger.info(f"  NEW: {c['name']} ({c['stars']}★) — {c['description'][:80]}")
                add_action("spy_new_competitor", f"New competitor: {c['name']}",
                           {"repo": c["repo"], "name": c["name"], "stars": c["stars"], "url": c["url"], "description": c["description"]})

    def _monitor_all_competitors(self):
        logger.info("Monitoring known competitors...")
        competitors = self._load_competitors()
        for comp in competitors:
            data = self._monitor_one(comp)
            if data:
                self.report["competitors"].append(data)

    def _monitor_one(self, comp: dict) -> Optional[dict]:
        repo_path = comp["repo"]
        logger.info(f"Monitoring {repo_path}...")
        data = {"repo": repo_path, "name": comp["name"], "threat_level": comp.get("threat_level", "unknown"), "known_features": comp.get("features", {})}
        try:
            resp = self.client.get(f"https://api.github.com/repos/{repo_path}", headers=self.github_headers)
            if resp.status_code == 200:
                repo = resp.json()
                data["stars"] = repo.get("stargazers_count", 0)
                data["forks"] = repo.get("forks_count", 0)
                data["open_issues"] = repo.get("open_issues_count", 0)
                data["watchers"] = repo.get("watchers_count", 0)
                data["language"] = repo.get("language", "")
                data["updated_at"] = repo.get("updated_at", "")
                data["pushed_at"] = repo.get("pushed_at", "")
                data["size_kb"] = repo.get("size", 0)
                data["description"] = repo.get("description", "")
            else:
                logger.warning(f"Failed to get repo {repo_path}: {resp.status_code}")
                return None
        except Exception as e:
            logger.error(f"Repo fetch error {repo_path}: {e}")
            return None
        try:
            since = (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
            resp = self.client.get(f"https://api.github.com/repos/{repo_path}/commits",
                                   params={"since": since, "per_page": 100}, headers=self.github_headers)
            if resp.status_code == 200:
                commits = resp.json()
                data["commits_30d"] = len(commits)
                if commits:
                    data["last_commit_date"] = commits[0].get("commit", {}).get("committer", {}).get("date", "")
                    data["last_commit_msg"] = commits[0].get("commit", {}).get("message", "")[:200]
                    data["recent_topics"] = self._extract_topics_from_commits(commits)
            else:
                data["commits_30d"] = 0
        except Exception as e:
            logger.error(f"Commits fetch error {repo_path}: {e}")
        try:
            resp = self.client.get(f"https://api.github.com/repos/{repo_path}/releases",
                                   params={"per_page": 5}, headers=self.github_headers)
            if resp.status_code == 200:
                releases = resp.json()
                data["total_releases"] = len(releases)
                if releases:
                    data["latest_release"] = {
                        "tag": releases[0].get("tag_name", ""), "name": releases[0].get("name", ""),
                        "date": releases[0].get("published_at", ""), "body": (releases[0].get("body", "") or "")[:300],
                    }
        except Exception as e:
            logger.error(f"Releases fetch error {repo_path}: {e}")
        try:
            resp = self.client.get(f"https://api.github.com/repos/{repo_path}/issues",
                                   params={"state": "open", "per_page": 10, "sort": "updated"}, headers=self.github_headers)
            if resp.status_code == 200:
                issues = resp.json()
                data["top_issues"] = [
                    {"title": i.get("title", "")[:100], "labels": [l["name"] for l in i.get("labels", [])],
                     "comments": i.get("comments", 0), "created": i.get("created_at", "")}
                    for i in issues[:5] if not i.get("pull_request")
                ]
        except Exception as e:
            logger.error(f"Issues fetch error {repo_path}: {e}")
        try:
            resp = self.client.get(f"https://api.github.com/repos/{repo_path}/readme", headers=self.github_headers)
            if resp.status_code == 200:
                readme_b64 = resp.json().get("content", "")
                readme_text = base64.b64decode(readme_b64).decode("utf-8", errors="ignore")
                data["readme_features"] = self._extract_features_from_readme(readme_text)
                data["readme_length"] = len(readme_text)
        except Exception as e:
            logger.error(f"README fetch error {repo_path}: {e}")
        return data

    def _extract_topics_from_commits(self, commits: list) -> list:
        keywords = {}
        important_terms = ["semantic", "search", "a2a", "agent2agent", "oauth", "auth", "discovery", "registry",
                           "crawl", "index", "api", "sdk", "performance", "cache", "vector", "embedding", "faiss",
                           "docker", "deploy", "scale", "enterprise", "plugin"]
        for commit in commits:
            msg = (commit.get("commit", {}).get("message", "") or "").lower()
            for term in important_terms:
                if term in msg:
                    keywords[term] = keywords.get(term, 0) + 1
        return sorted(keywords.items(), key=lambda x: x[1], reverse=True)[:10]

    def _extract_features_from_readme(self, readme: str) -> dict:
        readme_lower = readme.lower()
        features = {}
        feature_signals = {
            "semantic_search": ["semantic search", "vector search", "faiss", "embedding", "sentence-transformer"],
            "a2a_support": ["a2a", "agent-to-agent", "agent2agent"],
            "auto_crawling": ["crawl", "auto-discover", "automatic index"],
            "enterprise_auth": ["oauth", "keycloak", "cognito", "enterprise", "rbac"],
            "mcp_support": ["mcp", "model context protocol"],
            "sdk_python": ["pip install", "pypi", "python sdk"],
            "sdk_npm": ["npm install", "npx", "node sdk", "javascript sdk"],
            "multi_source": ["github", "npm", "huggingface", "multiple sources"],
            "docker": ["docker", "docker-compose", "container"],
            "kubernetes": ["kubernetes", "k8s", "helm"],
            "graphql": ["graphql"],
            "rest_api": ["rest api", "openapi", "swagger"],
            "rate_limiting": ["rate limit"],
            "analytics": ["analytics", "dashboard", "metrics"],
        }
        for feature, signals in feature_signals.items():
            features[feature] = any(s in readme_lower for s in signals)
        return features

    def _run_benchmarks(self):
        logger.info("Running benchmarks...")
        our = self.report["our_stats"]
        benchmarks = []
        gaps = []
        for comp in self.report["competitors"]:
            comparison = {"competitor": comp["name"], "repo": comp["repo"], "threat_level": comp.get("threat_level", "unknown"), "kpis": {}}
            our_stars = our.get("github_stars", 0)
            their_stars = comp.get("stars", 0)
            comparison["kpis"]["github_stars"] = {"ours": our_stars, "theirs": their_stars, "we_lead": our_stars >= their_stars}
            if their_stars > our_stars * 2 and their_stars > 100:
                gaps.append({"kpi": "github_stars", "competitor": comp["name"], "ours": our_stars, "theirs": their_stars,
                             "severity": "high", "suggestion": f"{comp['name']} has {their_stars} stars vs our {our_stars}. Need better README, more examples, community engagement."})
            their_commits = comp.get("commits_30d", 0)
            comparison["kpis"]["commits_30d"] = {"theirs": their_commits, "active": their_commits > 10}
            if their_commits > 30:
                gaps.append({"kpi": "development_velocity", "competitor": comp["name"], "theirs": their_commits,
                             "severity": "medium", "suggestion": f"{comp['name']} has {their_commits} commits in 30d — very active development."})
            their_features = comp.get("known_features", {})
            readme_features = comp.get("readme_features", {})
            all_their_features = {**their_features}
            for k, v in readme_features.items():
                if v and k in OUR_FEATURES:
                    all_their_features[k] = True
            for feature, they_have in all_their_features.items():
                we_have = OUR_FEATURES.get(feature, False)
                if they_have and not we_have:
                    priority = FEATURE_PRIORITY.get(feature, "medium")
                    gaps.append({"kpi": f"feature:{feature}", "competitor": comp["name"], "ours": False, "theirs": True,
                                 "severity": "critical" if priority == "critical" else "high",
                                 "suggestion": f"{comp['name']} has {feature} — we don't. Priority: {priority}."})
            comparison["kpis"]["feature_gap"] = {
                "they_have_we_dont": [f for f, v in all_their_features.items() if v and not OUR_FEATURES.get(f, False)],
                "we_have_they_dont": [f for f, v in OUR_FEATURES.items() if v and not all_their_features.get(f, False)],
            }
            benchmarks.append(comparison)
        our_index = our.get("index_size", 0)
        if our_index > 0:
            benchmarks.append({"kpi": "index_size", "ours": our_index, "note": "No competitor has auto-crawling — this is our moat.", "status": "leading"})
        our_sources = our.get("source_count", 0)
        if our_sources >= 5:
            benchmarks.append({"kpi": "source_count", "ours": our_sources, "note": f"We crawl {our_sources} sources automatically.", "status": "leading"})
        seen_gaps = set()
        unique_gaps = []
        for gap in gaps:
            key = f"{gap['kpi']}:{gap['competitor']}"
            if key not in seen_gaps:
                seen_gaps.add(key)
                unique_gaps.append(gap)
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        unique_gaps.sort(key=lambda g: severity_order.get(g["severity"], 99))
        self.report["benchmarks"] = benchmarks
        self.report["gaps"] = unique_gaps
        logger.info(f"Benchmarks complete: {len(benchmarks)} comparisons, {len(unique_gaps)} gaps")

    def _generate_actions(self):
        logger.info("Generating improvement actions...")
        actions = []
        feature_gap_actions = {
            "feature:semantic_search": {
                "type": "spy_implement_feature",
                "title": "🔴 CRITICAL: Implement semantic search (FAISS + sentence-transformers)",
                "details": {"feature": "semantic_search", "approach": "Add FAISS index + sentence-transformers for /v1/discover. Replace keyword matching with vector similarity. Reference: mcp-gateway-registry uses FAISS + all-MiniLM-L6-v2.", "effort": "2-3 days", "impact": "Dramatically better search results, closes biggest feature gap."},
            },
            "feature:a2a_support": {
                "type": "spy_implement_feature",
                "title": "🔴 CRITICAL: Add A2A (Agent-to-Agent) protocol support",
                "details": {"feature": "a2a_support", "approach": "Implement Agent2Agent protocol endpoints. Allow agents to register capabilities and discover each other. Reference: mcp-gateway-registry A2A implementation.", "effort": "3-5 days", "impact": "Enables true agent-to-agent communication through our platform."},
            },
            "feature:enterprise_auth": {
                "type": "spy_implement_feature",
                "title": "🟡 HIGH: Add OAuth/enterprise auth",
                "details": {"feature": "enterprise_auth", "approach": "Add OAuth2 support alongside API keys. Consider Keycloak or Auth0 integration.", "effort": "3-5 days", "impact": "Required for enterprise adoption."},
            },
        }
        processed_features = set()
        for gap in self.report["gaps"]:
            kpi = gap["kpi"]
            if kpi.startswith("feature:") and kpi not in processed_features:
                processed_features.add(kpi)
                if kpi in feature_gap_actions:
                    action_def = feature_gap_actions[kpi]
                    action_def["details"]["competitor"] = gap["competitor"]
                    add_action(action_def["type"], action_def["title"], action_def["details"])
                    actions.append(action_def["title"])
                else:
                    feature_name = kpi.replace("feature:", "")
                    add_action("spy_implement_feature", f"🟡 Feature gap: implement {feature_name}",
                               {"feature": feature_name, "competitor": gap["competitor"], "suggestion": gap["suggestion"]})
                    actions.append(f"Feature gap: {feature_name} (from {gap['competitor']})")
            elif kpi == "github_stars":
                add_action("spy_improve_visibility", f"Stars gap: {gap['competitor']}",
                           {"competitor": gap["competitor"], "their_stars": gap["theirs"], "our_stars": gap["ours"], "suggestion": gap["suggestion"]})
                actions.append(f"Stars gap vs {gap['competitor']}")
            elif kpi == "development_velocity":
                add_action("spy_competitor_active", f"Active competitor: {gap['competitor']}",
                           {"competitor": gap["competitor"], "commits_30d": gap["theirs"]})
                actions.append(f"Active competitor: {gap['competitor']}")
        for nc in self.report.get("new_competitors", [])[:5]:
            actions.append(f"New competitor discovered: {nc['name']} ({nc['stars']}★)")
        if self.report["gaps"]:
            critical = [g for g in self.report["gaps"] if g["severity"] == "critical"]
            high = [g for g in self.report["gaps"] if g["severity"] == "high"]
            add_action("spy_daily_summary", "Spionen daily summary",
                       {"critical_gaps": [g["kpi"] for g in critical], "high_gaps": [g["kpi"] for g in high],
                        "total_competitors": len(self.report["competitors"]), "new_competitors": len(self.report["new_competitors"])})
        self.report["actions"] = actions
        logger.info(f"Generated {len(actions)} actions")

    # =================================================================
    # 6. BACKLOG LOOP — track approved features until implemented
    # =================================================================

    FEATURE_DETECTION = {
        "semantic_search": {
            "code_signals": ["faiss", "sentence_transformers", "sentence-transformers", "vector_search", "embedding_index"],
            "file_patterns": ["**/faiss_index*", "**/embeddings*", "**/vector_store*"],
            "import_check": ["faiss", "sentence_transformers"],
        },
        "a2a_support": {
            "code_signals": ["a2a", "agent2agent", "agent_to_agent", "AgentCard"],
            "file_patterns": ["**/a2a*", "**/agent2agent*"],
            "import_check": [],
        },
        "enterprise_auth": {
            "code_signals": ["oauth", "keycloak", "cognito", "jwt_required", "OAuth2"],
            "file_patterns": ["**/auth/oauth*", "**/auth/keycloak*"],
            "import_check": ["authlib", "python_keycloak"],
        },
    }

    def _check_backlog(self):
        """Check approved features backlog — detect if implemented, remind if not."""
        logger.info("Checking implementation backlog...")
        backlog_path = os.path.expanduser("~/agentindex/spionen_backlog.json")

        if not os.path.exists(backlog_path):
            logger.info("No backlog file found")
            return

        try:
            with open(backlog_path) as f:
                backlog = json.load(f)
        except Exception:
            return

        if not backlog:
            return

        codebase_text = self._scan_codebase()
        changed = False

        for item in backlog:
            if item.get("status") == "done":
                continue

            feature = item["feature"]
            detection = self.FEATURE_DETECTION.get(feature, {})
            code_signals = detection.get("code_signals", [])
            import_checks = detection.get("import_check", [])

            # Check if feature is now implemented
            implemented = False
            evidence = []

            # Scan codebase for signals
            for signal in code_signals:
                if signal.lower() in codebase_text:
                    evidence.append(f"code: '{signal}' found")
                    implemented = True

            # Check if packages are installed
            for pkg in import_checks:
                try:
                    __import__(pkg)
                    evidence.append(f"import: {pkg} installed")
                    implemented = True
                except ImportError:
                    pass

            if implemented:
                item["status"] = "done"
                item["done_at"] = datetime.utcnow().isoformat()
                item["evidence"] = evidence
                changed = True
                logger.info(f"✅ Feature IMPLEMENTED: {feature} — {', '.join(evidence)}")
                # Update OUR_FEATURES
                OUR_FEATURES[feature] = True
                add_action("spy_feature_done", f"✅ Feature implemented: {feature}",
                           {"feature": feature, "evidence": evidence})
                self.report["actions"].append(f"✅ DONE: {feature}")
            else:
                # Remind — feature still not implemented
                days_waiting = 0
                if item.get("approved_at"):
                    try:
                        approved = datetime.fromisoformat(item["approved_at"])
                        days_waiting = (datetime.utcnow() - approved).days
                    except Exception:
                        pass

                urgency = "🔴 OVERDUE" if days_waiting > 7 else "🟡 PENDING"
                logger.info(f"{urgency}: {feature} — approved {days_waiting}d ago, not yet implemented")
                self.report["actions"].append(
                    f"{urgency}: {feature} approved {days_waiting}d ago — still not implemented. "
                    f"Approach: {item.get('approach', 'N/A')[:100]}"
                )
                add_action("spy_feature_reminder", f"Implement {feature}",
                           {"feature": feature, "days_waiting": days_waiting,
                            "approach": item.get("approach", ""), "effort": item.get("effort", "")})

        if changed:
            with open(backlog_path, "w") as f:
                json.dump(backlog, f, indent=2)

        pending = [b for b in backlog if b.get("status") != "done"]
        done = [b for b in backlog if b.get("status") == "done"]
        self.report["backlog"] = {"pending": len(pending), "done": len(done), "items": backlog}
        logger.info(f"Backlog: {len(pending)} pending, {len(done)} done")

    def _scan_codebase(self) -> str:
        """Scan our codebase for feature implementation signals."""
        import glob
        codebase_dir = os.path.expanduser("~/agentindex/agentindex")
        text_parts = []
        for pattern in ["**/*.py"]:
            for filepath in glob.glob(os.path.join(codebase_dir, pattern), recursive=True):
                try:
                    with open(filepath) as f:
                        text_parts.append(f.read().lower())
                except Exception:
                    pass
        # Also check requirements/pyproject
        for extra in ["~/agentindex/requirements.txt", "~/agentindex/pyproject.toml", "~/agentindex/setup.py"]:
            expanded = os.path.expanduser(extra)
            if os.path.exists(expanded):
                try:
                    with open(expanded) as f:
                        text_parts.append(f.read().lower())
                except Exception:
                    pass
        return " ".join(text_parts)

    def _build_feature_matrix(self) -> dict:
        matrix = {"AgentIndex": OUR_FEATURES.copy()}
        for comp in self.report["competitors"]:
            features = comp.get("known_features", {})
            readme_features = comp.get("readme_features", {})
            merged = {**features}
            for k, v in readme_features.items():
                if v:
                    merged[k] = True
            matrix[comp["name"]] = merged
        self.report["feature_matrix"] = matrix
        return matrix

    def _load_competitors(self) -> list:
        if os.path.exists(self.competitors_file):
            try:
                with open(self.competitors_file) as f:
                    stored = json.load(f)
                    if stored:
                        return stored
            except Exception:
                pass
        return KNOWN_COMPETITORS.copy()

    def _save_competitors(self, competitors: list):
        with open(self.competitors_file, "w") as f:
            json.dump(competitors, f, indent=2, default=str)

    def _save_history(self):
        history = []
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file) as f:
                    history = json.load(f)
            except Exception:
                pass
        entry = {
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "our_index_size": self.report["our_stats"].get("index_size", 0),
            "our_stars": self.report["our_stats"].get("github_stars", 0),
            "competitors": [{"name": c["name"], "stars": c.get("stars", 0), "commits_30d": c.get("commits_30d", 0)} for c in self.report["competitors"]],
            "gap_count": len(self.report["gaps"]),
            "critical_gaps": len([g for g in self.report["gaps"] if g["severity"] == "critical"]),
        }
        history.append(entry)
        history = history[-90:]
        with open(self.history_file, "w") as f:
            json.dump(history, f, indent=2, default=str)

    def _save_report(self):
        report_dir = os.path.expanduser("~/agentindex/spionen_reports")
        os.makedirs(report_dir, exist_ok=True)
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        self._build_feature_matrix()
        json_path = f"{report_dir}/report-{date_str}.json"
        with open(json_path, "w") as f:
            json.dump(self.report, f, indent=2, default=str)
        md_path = f"{report_dir}/report-{date_str}.md"
        with open(md_path, "w") as f:
            f.write(self._generate_markdown_report())
        logger.info(f"Spionen report saved: {json_path}")

    def _generate_markdown_report(self) -> str:
        our = self.report["our_stats"]
        r = f"# 🕵️ Spionen Intelligence Report — {datetime.utcnow().strftime('%Y-%m-%d')}\n\n"
        r += "## Our Position\n"
        r += f"- **Index:** {our.get('index_size', '?'):,} agents ({our.get('active_agents', '?'):,} active)\n"
        r += f"- **Sources:** {our.get('source_count', '?')}\n"
        r += f"- **GitHub Stars:** {our.get('github_stars', '?')}\n"
        r += f"- **New 24h:** {our.get('new_24h', '?')}\n\n"
        critical = [g for g in self.report["gaps"] if g["severity"] == "critical"]
        high = [g for g in self.report["gaps"] if g["severity"] == "high"]
        r += f"## Gaps ({len(critical)} critical, {len(high)} high)\n"
        for gap in self.report["gaps"]:
            emoji = "🔴" if gap["severity"] == "critical" else "🟡" if gap["severity"] == "high" else "⚪"
            r += f"- {emoji} **{gap['kpi']}** vs {gap['competitor']}: {gap['suggestion']}\n"
        r += "\n"
        matrix = self.report.get("feature_matrix", {})
        if matrix:
            r += "## Feature Matrix\n"
            all_features = set()
            for features in matrix.values():
                all_features.update(features.keys())
            r += "| Feature |"
            for name in matrix:
                r += f" {name} |"
            r += "\n|---|" + "---|" * len(matrix) + "\n"
            for feature in sorted(all_features):
                priority = FEATURE_PRIORITY.get(feature, "")
                r += f"| {feature} {'⚡' if priority == 'critical' else ''} |"
                for name, features in matrix.items():
                    r += f" {'✅' if features.get(feature) else '❌'} |"
                r += "\n"
            r += "\n"
        r += "## Competitor Activity\n"
        for comp in self.report["competitors"]:
            r += f"### {comp['name']} ({comp.get('stars', '?')}★)\n"
            r += f"- Commits (30d): {comp.get('commits_30d', '?')}\n"
            if comp.get("last_commit_msg"):
                r += f"- Latest: {comp['last_commit_msg'][:100]}\n"
            if comp.get("recent_topics"):
                topics = ", ".join(f"{t[0]}({t[1]})" for t in comp["recent_topics"][:5])
                r += f"- Hot topics: {topics}\n"
            if comp.get("top_issues"):
                r += "- Top issues:\n"
                for issue in comp["top_issues"][:3]:
                    r += f"  - {issue['title']}\n"
            r += "\n"
        if self.report["new_competitors"]:
            r += "## New Competitors Discovered\n"
            for nc in self.report["new_competitors"][:10]:
                r += f"- **{nc['name']}** ({nc['stars']}★): {nc['description'][:100]}\n"
            r += "\n"
        r += f"## Actions ({len(self.report['actions'])})\n"
        for i, action in enumerate(self.report["actions"], 1):
            r += f"{i}. {action}\n"
        return r


SPIONEN_ACTION_LEVELS = {
    "spy_new_competitor": ActionLevel.NOTIFY,
    "spy_implement_feature": ActionLevel.APPROVAL,
    "spy_improve_visibility": ActionLevel.NOTIFY,
    "spy_competitor_active": ActionLevel.NOTIFY,
    "spy_daily_summary": ActionLevel.NOTIFY,
    "spy_feature_done": ActionLevel.NOTIFY,
    "spy_feature_reminder": ActionLevel.NOTIFY,
}


if __name__ == "__main__":
    from dotenv import load_dotenv
    import os
    load_dotenv(os.path.expanduser("~/agentindex/.env"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    spionen = Spionen()
    report = spionen.run_daily()
    print(f"\nGaps: {len(report['gaps'])}")
    for gap in report["gaps"]:
        print(f"  [{gap['severity']}] {gap['kpi']} vs {gap['competitor']}")
    print(f"\nActions: {len(report['actions'])}")
    for action in report["actions"]:
        print(f"  -> {action}")
