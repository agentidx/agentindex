"""
AgentIndex Ranker (Rankare)

Nightly batch job that recalculates quality scores for all agents.
Uses AgentRank algorithm — a weighted composite of multiple signals.

AgentRank weights:
  Code quality     20%  (tests, CI, clean code signals)
  Documentation    15%  (README quality, examples, agent.md)
  Maintenance      20%  (recency of updates, response to issues)
  Popularity       15%  (stars, downloads, forks)
  Capability depth 15%  (specificity and breadth of capabilities)
  Security         15%  (license, known vulnerabilities, data access)

Also calculates:
  - Category rankings (top agents per category)
  - Trending agents (rising quality/popularity)
  - Decay for inactive agents
"""

import logging
from datetime import datetime, timedelta
from agentindex.db.models import Agent, DiscoveryLog, get_session
from sqlalchemy import select, func, update
import math

logger = logging.getLogger("agentindex.ranker")

# AgentRank weights
WEIGHTS = {
    "code_quality": 0.20,
    "documentation": 0.15,
    "maintenance": 0.20,
    "popularity": 0.15,
    "capability_depth": 0.15,
    "security": 0.15,
}

# Decay rate for inactive agents (per month of inactivity)
INACTIVITY_DECAY = 0.05

# Boost for agents that get discovered (proves usefulness)
DISCOVERY_BOOST_FACTOR = 0.02


class Ranker:
    """Recalculates AgentRank scores for all active agents."""

    def __init__(self):
        self.session = get_session()

    def run_nightly(self) -> dict:
        """Full ranking cycle."""
        stats = {"ranked": 0, "decayed": 0, "boosted": 0}

        # Step 1: Recalculate base scores
        logger.info("Step 1: Recalculating base scores...")
        stats["ranked"] = self._recalculate_scores()

        # Step 2: Apply inactivity decay
        logger.info("Step 2: Applying inactivity decay...")
        stats["decayed"] = self._apply_decay()

        # Step 3: Apply discovery boost
        logger.info("Step 3: Applying discovery boost...")
        stats["boosted"] = self._apply_discovery_boost()

        # Step 4: Normalize scores within categories
        logger.info("Step 4: Normalizing category rankings...")
        self._normalize_categories()

        self.session.commit()
        logger.info(f"Nightly ranking complete: {stats}")
        return stats

    def _recalculate_scores(self) -> int:
        """Recalculate quality_score for all classified agents."""
        agents = self.session.execute(
            select(Agent).where(
                Agent.is_active == True,
                Agent.crawl_status.in_(["classified", "ranked"]),
            )
        ).scalars().all()

        # Get global stats for normalization
        max_stars = self.session.execute(
            select(func.max(Agent.stars)).where(Agent.is_active == True)
        ).scalar() or 1

        max_downloads = self.session.execute(
            select(func.max(Agent.downloads)).where(Agent.is_active == True)
        ).scalar() or 1

        max_forks = self.session.execute(
            select(func.max(Agent.forks)).where(Agent.is_active == True)
        ).scalar() or 1

        count = 0
        for agent in agents:
            # Code quality: from classification trust signals
            classification = (agent.raw_metadata or {}).get("classification", {})
            trust = classification.get("trust_signals", {})

            code_quality = sum([
                0.3 if trust.get("has_tests") else 0,
                0.2 if trust.get("has_ci") else 0,
                0.2 if trust.get("has_license") else 0,
                0.3 if trust.get("has_examples") else 0,
            ])

            # Documentation: existing score from parser
            documentation = agent.documentation_score or 0.0

            # Maintenance: time since last update
            maintenance = self._calc_maintenance_score(agent)

            # Popularity: normalized stars + downloads + forks
            popularity = self._calc_popularity_score(
                agent, max_stars, max_downloads, max_forks
            )

            # Capability depth: number and specificity of capabilities
            capability_depth = self._calc_capability_depth(agent)

            # Security: from classification
            security = agent.security_score or 0.5  # default to neutral

            # Weighted AgentRank
            agent_rank = (
                code_quality * WEIGHTS["code_quality"] +
                documentation * WEIGHTS["documentation"] +
                maintenance * WEIGHTS["maintenance"] +
                popularity * WEIGHTS["popularity"] +
                capability_depth * WEIGHTS["capability_depth"] +
                security * WEIGHTS["security"]
            )

            # Clamp to 0.0-1.0
            agent.quality_score = max(0.0, min(1.0, agent_rank))

            # Update sub-scores
            agent.activity_score = maintenance
            agent.popularity_score = popularity
            agent.capability_depth_score = capability_depth

            agent.crawl_status = "ranked"
            count += 1

        return count

    def _calc_maintenance_score(self, agent: Agent) -> float:
        """Score based on how recently the agent was updated."""
        if not agent.last_source_update:
            return 0.2  # unknown = low but not zero

        days = (datetime.utcnow() - agent.last_source_update).days

        if days <= 7:
            return 1.0
        elif days <= 30:
            return 0.85
        elif days <= 90:
            return 0.65
        elif days <= 180:
            return 0.45
        elif days <= 365:
            return 0.25
        else:
            return 0.1

    def _calc_popularity_score(self, agent: Agent, max_stars: int,
                                max_downloads: int, max_forks: int) -> float:
        """Normalized popularity using log scale."""
        stars = agent.stars or 0
        downloads = agent.downloads or 0
        forks = agent.forks or 0

        # Log-normalized to avoid mega-repos dominating
        star_score = math.log1p(stars) / math.log1p(max_stars) if max_stars > 0 else 0
        download_score = math.log1p(downloads) / math.log1p(max_downloads) if max_downloads > 0 else 0
        fork_score = math.log1p(forks) / math.log1p(max_forks) if max_forks > 0 else 0

        return (star_score * 0.5) + (download_score * 0.35) + (fork_score * 0.15)

    def _calc_capability_depth(self, agent: Agent) -> float:
        """Score based on capability specificity and count."""
        capabilities = agent.capabilities or []
        n = len(capabilities)

        if n == 0:
            return 0.0
        elif n == 1:
            return 0.3
        elif n <= 3:
            return 0.5
        elif n <= 6:
            return 0.7
        elif n <= 10:
            return 0.85
        else:
            return 0.9  # cap — too many capabilities may mean unfocused

    def _apply_decay(self) -> int:
        """Reduce scores for agents that haven't been updated."""
        cutoff = datetime.utcnow() - timedelta(days=180)

        agents = self.session.execute(
            select(Agent).where(
                Agent.is_active == True,
                Agent.last_source_update < cutoff,
            )
        ).scalars().all()

        count = 0
        for agent in agents:
            months_inactive = (datetime.utcnow() - agent.last_source_update).days / 30
            decay = min(INACTIVITY_DECAY * months_inactive, 0.3)  # max 30% decay
            agent.quality_score = max(0.05, agent.quality_score - decay)
            count += 1

        return count

    def _apply_discovery_boost(self) -> int:
        """Boost agents that appear in discovery results (proves usefulness)."""
        # Count how often each agent appears as top result in last 7 days
        week_ago = datetime.utcnow() - timedelta(days=7)

        results = self.session.execute(
            select(
                DiscoveryLog.top_result_id,
                func.count(DiscoveryLog.id).label("appearances")
            )
            .where(
                DiscoveryLog.timestamp > week_ago,
                DiscoveryLog.top_result_id != None,
            )
            .group_by(DiscoveryLog.top_result_id)
        ).all()

        count = 0
        for agent_id, appearances in results:
            agent = self.session.get(Agent, agent_id)
            if agent and agent.is_active:
                boost = min(DISCOVERY_BOOST_FACTOR * appearances, 0.1)  # max 10% boost
                agent.quality_score = min(1.0, agent.quality_score + boost)
                count += 1

        return count

    def _normalize_categories(self):
        """Ensure relative ranking within categories is sensible."""
        categories = self.session.execute(
            select(Agent.category).where(Agent.is_active == True).distinct()
        ).scalars().all()

        for category in categories:
            if not category:
                continue

            agents = self.session.execute(
                select(Agent)
                .where(Agent.is_active == True, Agent.category == category)
                .order_by(Agent.quality_score.desc())
            ).scalars().all()

            if not agents:
                continue

            # Just log the top agents per category for monitoring
            top_3 = agents[:3]
            names = ", ".join(f"{a.name}({a.quality_score:.2f})" for a in top_3)
            logger.info(f"Category '{category}' top 3: {names} (total: {len(agents)})")

    def get_trending(self, days: int = 7, limit: int = 20) -> list:
        """Get agents with rising discovery frequency."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        results = self.session.execute(
            select(
                DiscoveryLog.top_result_id,
                func.count(DiscoveryLog.id).label("appearances")
            )
            .where(
                DiscoveryLog.timestamp > cutoff,
                DiscoveryLog.top_result_id != None,
            )
            .group_by(DiscoveryLog.top_result_id)
            .order_by(func.count(DiscoveryLog.id).desc())
            .limit(limit)
        ).all()

        trending = []
        for agent_id, appearances in results:
            agent = self.session.get(Agent, agent_id)
            if agent:
                trending.append({
                    "agent": agent.to_discovery_response(),
                    "discovery_appearances": appearances,
                })

        return trending

    def get_category_leaders(self) -> dict:
        """Get top agent per category."""
        categories = self.session.execute(
            select(Agent.category).where(Agent.is_active == True).distinct()
        ).scalars().all()

        leaders = {}
        for category in categories:
            if not category:
                continue

            top = self.session.execute(
                select(Agent)
                .where(Agent.is_active == True, Agent.category == category)
                .order_by(Agent.quality_score.desc())
                .limit(1)
            ).scalar_one_or_none()

            if top:
                leaders[category] = {
                    "name": top.name,
                    "quality_score": top.quality_score,
                    "source": top.source,
                }

        return leaders


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    ranker = Ranker()
    stats = ranker.run_nightly()
    print(f"Ranking complete: {stats}")
    print(f"Category leaders: {ranker.get_category_leaders()}")
