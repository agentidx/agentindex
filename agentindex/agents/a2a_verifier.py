"""
AgentIndex A2A Verifier & Outreach

Autonomous pipeline:
1. VERIFY — Ping all agents claiming A2A, check for live Agent Cards
2. ENRICH — Update verified agents with data from their Agent Card
3. OUTREACH — Send a helpful message to newly verified agents

Runs every 12 hours. Outreach is one-time per agent (tracked).
"""

import os
import json
import time
import logging
import hashlib
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy import select, func
from agentindex.db.models import Agent, get_session, safe_commit
from agentindex.agents.action_queue import add_action, ActionLevel

logger = logging.getLogger("agentindex.a2a_verifier")

# Persistent state
STATE_FILE = os.path.expanduser("~/agentindex/a2a_verifier_state.json")
REQUEST_TIMEOUT = 8.0
BATCH_SIZE = 50  # Verify 50 agents per run to avoid overloading


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "verified": {},       # agent_id -> {verified_at, card_url, name}
        "outreach_sent": {},  # agent_id -> {sent_at, method, response}
        "failed": {},         # domain -> {last_tried, fail_count}
        "last_run": None,
    }


def _save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


class A2AVerifier:

    def __init__(self):
        self.state = _load_state()
        self.github_token = os.getenv("GITHUB_TOKEN", "")
        self.stats = {
            "checked": 0,
            "verified": 0,
            "enriched": 0,
            "outreach_sent": 0,
            "outreach_skipped": 0,
            "failed": 0,
        }

    def run(self) -> dict:
        """Run full verify + outreach cycle."""
        logger.info("=" * 50)
        logger.info("A2A Verifier & Outreach starting...")
        logger.info("=" * 50)

        session = get_session()

        try:
            # Phase 1: Verify — check A2A agents for live Agent Cards
            self._verify_agents(session)

            # Phase 2: Outreach — message newly verified agents
            self._outreach_new_agents(session)

            self.state["last_run"] = datetime.utcnow().isoformat()
            _save_state(self.state)

        except Exception as e:
            logger.error(f"A2A Verifier failed: {e}")
        finally:
            session.close()

        logger.info(f"A2A Verifier complete: {self.stats}")
        return self.stats

    # =================================================================
    # Phase 1: VERIFY
    # =================================================================

    def _verify_agents(self, session):
        """Check agents with a2a protocol for live Agent Cards."""
        logger.info("Phase 1: Verifying A2A agents...")

        # Get agents claiming A2A that we haven't verified recently
        already_verified = set(self.state["verified"].keys())

        agents = session.execute(
            select(Agent).where(
                Agent.protocols.any("a2a"),
                Agent.is_active == True,
            ).order_by(Agent.quality_score.desc())
        ).scalars().all()

        logger.info(f"  {len(agents)} agents claim A2A protocol")

        # Prioritize: unverified first, then re-verify old ones
        to_check = []
        for agent in agents:
            aid = str(agent.id)
            if aid not in already_verified:
                to_check.insert(0, agent)  # Unverified first
            else:
                # Re-verify after 7 days
                verified_at = self.state["verified"].get(aid, {}).get("verified_at", "")
                if verified_at:
                    try:
                        days_ago = (datetime.utcnow() - datetime.fromisoformat(verified_at)).days
                        if days_ago > 7:
                            to_check.append(agent)
                    except Exception:
                        pass

        to_check = to_check[:BATCH_SIZE]
        logger.info(f"  Checking {len(to_check)} agents this run")

        for agent in to_check:
            self._verify_one(agent, session)
            time.sleep(0.5)

    def _verify_one(self, agent: Agent, session):
        """Verify a single agent — try to fetch its Agent Card."""
        self.stats["checked"] += 1
        aid = str(agent.id)

        # Determine URL to check
        urls_to_try = []

        # From invocation endpoint
        inv = agent.invocation or {}
        if inv.get("agent_card_url"):
            urls_to_try.append(inv["agent_card_url"])
        if inv.get("endpoint"):
            base = inv["endpoint"].rstrip("/")
            urls_to_try.append(base + "/.well-known/agent-card.json")
            urls_to_try.append(base + "/.well-known/agent.json")

        # From source URL (if it's a deployed service)
        if agent.source_url and not agent.source_url.startswith("https://github.com"):
            base = agent.source_url.rstrip("/")
            urls_to_try.append(base + "/.well-known/agent-card.json")
            urls_to_try.append(base + "/.well-known/agent.json")

        # Try to find homepage in raw_metadata
        raw = agent.raw_metadata or {}
        homepage = raw.get("homepage") or raw.get("homepage_url", "")
        if homepage and not any(skip in homepage for skip in ["github.com", "npmjs.com", "pypi.org"]):
            base = homepage.rstrip("/")
            urls_to_try.append(base + "/.well-known/agent-card.json")
            urls_to_try.append(base + "/.well-known/agent.json")

        if not urls_to_try:
            return

        # Check failed domains
        for url in urls_to_try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lower()
            fail_info = self.state.get("failed", {}).get(domain, {})
            if fail_info.get("fail_count", 0) >= 3:
                continue  # Skip domains that consistently fail

            try:
                resp = httpx.get(url, timeout=REQUEST_TIMEOUT, follow_redirects=True)
                if resp.status_code == 200:
                    try:
                        card = resp.json()
                    except Exception:
                        continue

                    if isinstance(card, dict) and "name" in card:
                        # VERIFIED!
                        logger.info(f"  ✅ VERIFIED: {agent.name} — live at {url}")
                        self.stats["verified"] += 1

                        # Update agent
                        agent.is_verified = True
                        agent.quality_score = min(1.0, (agent.quality_score or 0.5) + 0.1)
                        if "live-a2a" not in (agent.tags or []):
                            agent.tags = list(set((agent.tags or []) + ["live-a2a", "verified"]))

                        # Enrich from Agent Card
                        self._enrich_from_card(agent, card, url)

                        safe_commit(session)

                        # Save state
                        self.state["verified"][aid] = {
                            "verified_at": datetime.utcnow().isoformat(),
                            "card_url": url,
                            "name": card.get("name", agent.name),
                            "skills": [s.get("name", "") for s in card.get("skills", []) if isinstance(s, dict)],
                        }
                        return

            except Exception:
                # Track failed domain
                self.state.setdefault("failed", {}).setdefault(domain, {"fail_count": 0})
                self.state["failed"][domain]["fail_count"] += 1
                self.state["failed"][domain]["last_tried"] = datetime.utcnow().isoformat()

        self.stats["failed"] += 1

    def _enrich_from_card(self, agent: Agent, card: dict, card_url: str):
        """Enrich agent data from its Agent Card."""
        self.stats["enriched"] += 1

        # Update description if better
        card_desc = card.get("description", "")
        if card_desc and len(card_desc) > len(agent.description or ""):
            agent.description = card_desc[:500]

        # Update capabilities from skills
        skills = card.get("skills", [])
        if skills:
            capabilities = []
            for s in skills:
                if isinstance(s, dict):
                    if s.get("name"):
                        capabilities.append(s["name"])
                    if s.get("description"):
                        capabilities.append(s["description"][:100])
            if capabilities:
                agent.capabilities = capabilities

        # Update invocation
        agent.invocation = {
            "type": "a2a",
            "endpoint": card.get("url", ""),
            "protocol": "a2a",
            "agent_card_url": card_url,
            "authentication": card.get("authentication", {}),
            "version": card.get("version", ""),
        }

        # Store full card in raw_metadata
        agent.raw_metadata = {
            **(agent.raw_metadata or {}),
            "agent_card": card,
            "last_verified": datetime.utcnow().isoformat(),
        }

    # =================================================================
    # Phase 2: OUTREACH — helpful message to new A2A agents
    # =================================================================

    def _outreach_new_agents(self, session):
        """Send outreach to newly verified agents we haven't contacted."""
        logger.info("Phase 2: Outreach to new verified agents...")

        for aid, info in self.state.get("verified", {}).items():
            if aid in self.state.get("outreach_sent", {}):
                self.stats["outreach_skipped"] += 1
                continue

            # Get agent
            try:
                import uuid
                agent = session.execute(
                    select(Agent).where(Agent.id == uuid.UUID(aid))
                ).scalar_one_or_none()
            except Exception:
                continue

            if not agent:
                continue

            # Try outreach methods in order of preference
            success = False

            # Method 1: A2A message (if they have a live endpoint)
            if not success:
                success = self._outreach_via_a2a(agent, info)

            # Method 2: GitHub Issue (if it's a GitHub repo)
            if not success and agent.source_url and "github.com" in agent.source_url:
                success = self._outreach_via_github(agent, info)

            if success:
                self.stats["outreach_sent"] += 1
                self.state.setdefault("outreach_sent", {})[aid] = {
                    "sent_at": datetime.utcnow().isoformat(),
                    "agent_name": agent.name,
                }
                add_action(
                    "spy_a2a_outreach",
                    f"Outreach sent to {agent.name}",
                    {"agent_id": aid, "name": agent.name}
                )
            else:
                self.stats["outreach_skipped"] += 1

    def _outreach_via_a2a(self, agent: Agent, info: dict) -> bool:
        """Send a helpful A2A message to the agent."""
        inv = agent.invocation or {}
        endpoint = inv.get("endpoint", "")
        if not endpoint:
            return False

        # Craft a genuinely helpful message
        our_stats = self._get_our_stats()
        message = {
            "jsonrpc": "2.0",
            "id": f"agentindex-hello-{str(agent.id)[:8]}",
            "method": "message/send",
            "params": {
                "message": {
                    "parts": [{
                        "type": "text",
                        "text": (
                            f"Hi from AgentIndex! Your agent '{agent.name}' has been automatically "
                            f"discovered and listed in our index of {our_stats['total']}+ AI agents. "
                            f"Other agents can now find you via semantic search and the A2A protocol at "
                            f"https://api.agentcrawl.dev/a2a — no action needed on your part. "
                            f"If you'd like to update your listing or opt out, visit "
                            f"https://github.com/agentidx/agentindex"
                        )
                    }]
                }
            }
        }

        try:
            resp = httpx.post(
                endpoint,
                json=message,
                timeout=REQUEST_TIMEOUT,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 200:
                logger.info(f"  📨 A2A outreach sent to {agent.name}")
                return True
        except Exception as e:
            logger.debug(f"  A2A outreach failed for {agent.name}: {e}")

        return False

    def _outreach_via_github(self, agent: Agent, info: dict) -> bool:
        """Open a friendly GitHub Issue on the agent's repo."""
        if not self.github_token:
            return False

        source_url = agent.source_url or ""
        # Extract owner/repo from GitHub URL
        import re
        match = re.match(r'https://github\.com/([^/]+/[^/]+)', source_url)
        if not match:
            return False

        repo_full = match.group(1)
        our_stats = self._get_our_stats()

        title = f"🎉 {agent.name} is now discoverable on AgentIndex"
        body = (
            f"Hi! 👋\n\n"
            f"We wanted to let you know that **{agent.name}** has been automatically "
            f"discovered and listed on [AgentIndex](https://agentcrawl.dev) — "
            f"a discovery service for AI agents.\n\n"
            f"### What this means\n\n"
            f"- Your agent is now searchable among **{our_stats['total']}+ indexed agents**\n"
            f"- Other AI agents can find you via **semantic search** and the **A2A protocol**\n"
            f"- Your A2A Agent Card was verified as live ✅\n\n"
            f"### How agents find you\n\n"
            f"```bash\n"
            f"# Via A2A protocol\n"
            f"curl -X POST https://api.agentcrawl.dev/a2a \\\n"
            f'  -H "Content-Type: application/json" \\\n'
            f"  -d '{{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"method\":\"message/send\","
            f"\"params\":{{\"message\":{{\"parts\":[{{\"type\":\"text\","
            f"\"text\":\"Find {agent.name}\"}}]}}}}}}'\n"
            f"```\n\n"
            f"### No action needed\n\n"
            f"Your listing is automatic and free. If you'd like to:\n"
            f"- **Update your listing**: we pull data from your Agent Card automatically\n"
            f"- **Opt out**: just let us know in this issue\n"
            f"- **Learn more**: [github.com/agentidx/agentindex](https://github.com/agentidx/agentindex)\n\n"
            f"Happy building! 🤖\n\n"
            f"---\n"
            f"*This issue was created automatically by [AgentIndex](https://agentcrawl.dev), "
            f"the discovery service for AI agents.*"
        )

        try:
            resp = httpx.post(
                f"https://api.github.com/repos/{repo_full}/issues",
                headers={
                    "Authorization": f"token {self.github_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={"title": title, "body": body, "labels": ["agentindex"]},
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 201:
                logger.info(f"  📬 GitHub issue created for {repo_full}")
                return True
            elif resp.status_code == 403:
                logger.debug(f"  No permission to create issue on {repo_full}")
            elif resp.status_code == 410:
                logger.debug(f"  Issues disabled on {repo_full}")
        except Exception as e:
            logger.debug(f"  GitHub outreach failed for {repo_full}: {e}")

        return False

    def _get_our_stats(self) -> dict:
        """Get current index stats for outreach messages."""
        try:
            resp = httpx.get("https://api.agentcrawl.dev/v1/stats", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return {"total": data.get("total_agents", 36000)}
        except Exception:
            pass
        return {"total": 36000}


def run_a2a_verifier() -> dict:
    verifier = A2AVerifier()
    return verifier.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    from dotenv import load_dotenv
    load_dotenv(os.path.expanduser("~/agentindex/.env"))
    stats = run_a2a_verifier()
    print(f"\nStats: {json.dumps(stats, indent=2)}")
