"""
Trust Scoring System for AgentIndex
Calculates comprehensive trust scores for all agents based on multiple factors
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy import text, update
from sqlalchemy.orm import Session
from agentindex.db.models import get_session, get_write_session, Agent
import json
import math


class TrustScorer:
    """Comprehensive trust scoring system for AI agents"""
    
    def __init__(self):
        self.logger = logging.getLogger("agentindex.trust_scorer")
        
        # Scoring weights (total should be 1.0)
        self.weights = {
            "popularity": 0.25,      # Stars, downloads, forks
            "recency": 0.20,         # How recently updated
            "activity": 0.15,        # Development activity level
            "documentation": 0.15,   # Quality of documentation
            "community": 0.15,       # Community indicators
            "stability": 0.10        # Version stability, breaking changes
        }
        
        # Score explanations for transparency
        self.explanation_templates = {
            "excellent": "✅ Highly available, 🔥 Very popular, 🆕 Recently updated",
            "good": "✅ Well maintained, ⭐ Popular, 📝 Good documentation", 
            "fair": "⚠️ Moderately active, 📊 Some community adoption",
            "poor": "🚨 Low activity, ⚠️ Limited documentation, 🔍 Needs review"
        }
    
    async def calculate_trust_score(self, agent: Agent) -> Dict[str, Any]:
        """Calculate comprehensive trust score for a single agent"""
        
        scores = {}
        
        # 1. Popularity Score (0-100)
        scores["popularity"] = self._calculate_popularity_score(agent)
        
        # 2. Recency Score (0-100) 
        scores["recency"] = self._calculate_recency_score(agent)
        
        # 3. Activity Score (0-100)
        scores["activity"] = self._calculate_activity_score(agent)
        
        # 4. Documentation Score (0-100)
        scores["documentation"] = self._calculate_documentation_score(agent)
        
        # 5. Community Score (0-100)
        scores["community"] = self._calculate_community_score(agent)
        
        # 6. Stability Score (0-100)
        scores["stability"] = self._calculate_stability_score(agent)
        
        # Calculate weighted total
        total_score = sum(
            scores[component] * self.weights[component] 
            for component in scores
        )
        
        # Generate explanation
        explanation = self._generate_explanation(total_score, scores, agent)
        
        return {
            "total_score": round(total_score, 1),
            "component_scores": scores,
            "explanation": explanation,
            "calculated_at": datetime.utcnow().isoformat()
        }
    
    def _calculate_popularity_score(self, agent: Agent) -> float:
        """Calculate popularity score based on stars, downloads, etc."""
        score = 0.0
        
        # Stars (0-40 points)
        if agent.stars:
            # Logarithmic scale for stars: 1-10 = 10pts, 11-100 = 20pts, 101-1000 = 30pts, 1000+ = 40pts
            if agent.stars >= 1000:
                score += 40
            elif agent.stars >= 100:
                score += 30
            elif agent.stars >= 10:
                score += 20
            elif agent.stars >= 1:
                score += 10
        
        # Downloads (0-30 points)
        if agent.downloads:
            if agent.downloads >= 100000:
                score += 30
            elif agent.downloads >= 10000:
                score += 25
            elif agent.downloads >= 1000:
                score += 20
            elif agent.downloads >= 100:
                score += 15
            elif agent.downloads >= 10:
                score += 10
        
        # Forks (0-20 points)
        if agent.forks:
            if agent.forks >= 100:
                score += 20
            elif agent.forks >= 20:
                score += 15
            elif agent.forks >= 5:
                score += 10
            elif agent.forks >= 1:
                score += 5
        
        # Source credibility (0-10 points)
        source_scores = {
            "github": 10,
            "npm": 8,
            "pypi": 8,
            "huggingface": 7,
            "mcp": 6
        }
        score += source_scores.get(agent.source, 3)
        
        return min(100.0, score)
    
    def _calculate_recency_score(self, agent: Agent) -> float:
        """Calculate recency score based on last update"""
        if not agent.last_source_update:
            return 30.0  # Default for unknown
        
        days_since_update = (datetime.utcnow() - agent.last_source_update).days
        
        if days_since_update <= 7:
            return 100.0
        elif days_since_update <= 30:
            return 90.0
        elif days_since_update <= 90:
            return 75.0
        elif days_since_update <= 180:
            return 60.0
        elif days_since_update <= 365:
            return 40.0
        else:
            return 20.0
    
    def _calculate_activity_score(self, agent: Agent) -> float:
        """Calculate activity score based on development indicators"""
        score = 50.0  # Base score
        
        # Adjust based on existing quality scores
        if hasattr(agent, 'activity_score') and agent.activity_score:
            score = agent.activity_score * 100
        
        # Boost for recent indexing (new discoveries)
        if agent.first_indexed:
            days_since_indexed = (datetime.utcnow() - agent.first_indexed).days
            if days_since_indexed <= 30:
                score += 20  # Recently discovered = likely active
        
        return min(100.0, score)
    
    def _calculate_documentation_score(self, agent: Agent) -> float:
        """Calculate documentation score based on description quality and metadata"""
        score = 0.0
        
        # Description quality (0-40 points)
        if agent.description:
            desc_length = len(agent.description)
            if desc_length >= 200:
                score += 40
            elif desc_length >= 100:
                score += 30
            elif desc_length >= 50:
                score += 20
            elif desc_length >= 20:
                score += 10
        
        # Name quality (0-15 points)
        if agent.name:
            name_length = len(agent.name)
            if 10 <= name_length <= 50:  # Well-sized name
                score += 15
            elif 5 <= name_length <= 100:
                score += 10
            elif name_length >= 2:
                score += 5
        
        # Capabilities documentation (0-20 points)
        if agent.capabilities and len(agent.capabilities) > 0:
            score += min(20, len(agent.capabilities) * 5)
        
        # Category classification (0-10 points)
        if agent.category:
            score += 10
        
        # License information (0-10 points)
        if agent.license:
            score += 10
        
        # Use existing documentation_score if available (0-5 points bonus)
        if hasattr(agent, 'documentation_score') and agent.documentation_score:
            score += agent.documentation_score * 5
        
        return min(100.0, score)
    
    def _calculate_community_score(self, agent: Agent) -> float:
        """Calculate community engagement score"""
        score = 40.0  # Base score
        
        # Language ecosystem bonus
        language_scores = {
            "python": 15,
            "javascript": 15,
            "typescript": 15,
            "java": 10,
            "go": 10,
            "rust": 8,
            "cpp": 5
        }
        
        if agent.language:
            score += language_scores.get(agent.language.lower(), 3)
        
        # Framework bonus (community adoption indicator)
        if agent.frameworks:
            framework_scores = {
                "langchain": 10,
                "crewai": 8,
                "autogen": 7,
                "openai": 5
            }
            for framework in agent.frameworks:
                score += framework_scores.get(framework.lower(), 2)
        
        # Author reputation (simple heuristic)
        if agent.author and len(agent.author) > 0:
            score += 10
        
        # Multiple protocol support (interoperability)
        if agent.protocols and len(agent.protocols) > 1:
            score += 15
        
        return min(100.0, score)
    
    def _calculate_stability_score(self, agent: Agent) -> float:
        """Calculate stability/reliability score"""
        score = 60.0  # Base assumption of stability
        
        # Verified agents get boost
        if agent.is_verified:
            score += 30
        
        # Active agents are more stable
        if agent.is_active:
            score += 10
        else:
            score -= 40  # Inactive agents lose points
        
        # Long-term presence indicator
        if agent.first_indexed:
            days_indexed = (datetime.utcnow() - agent.first_indexed).days
            if days_indexed >= 365:  # Been around for a year
                score += 20
            elif days_indexed >= 90:  # 3 months
                score += 10
        
        # Quality score correlation
        if agent.quality_score and agent.quality_score > 0:
            score += agent.quality_score * 20  # Quality score is 0-1, so this adds 0-20
        
        return min(100.0, max(0.0, score))
    
    def _generate_explanation(self, total_score: float, scores: Dict[str, float], agent: Agent) -> str:
        """Generate human-readable explanation for the trust score"""
        
        # Determine overall category
        if total_score >= 80:
            category = "excellent"
        elif total_score >= 60:
            category = "good"
        elif total_score >= 40:
            category = "fair"
        else:
            category = "poor"
        
        explanation_parts = []
        
        # Add specific reasons based on top scoring components
        top_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
        
        for component, score in top_scores:
            if score >= 80:
                if component == "popularity":
                    if agent.stars and agent.stars >= 100:
                        explanation_parts.append(f"🔥 Very popular ({agent.stars}+ stars)")
                    elif agent.downloads and agent.downloads >= 1000:
                        explanation_parts.append(f"📈 High adoption ({agent.downloads}+ downloads)")
                    else:
                        explanation_parts.append("⭐ Popular in community")
                elif component == "recency":
                    explanation_parts.append("🆕 Recently updated")
                elif component == "activity":
                    explanation_parts.append("🚀 Highly active development")
                elif component == "documentation":
                    explanation_parts.append("📝 Well documented")
                elif component == "community":
                    explanation_parts.append("👥 Strong community")
                elif component == "stability":
                    explanation_parts.append("✅ Highly stable")
        
        # Add status indicators
        if agent.is_verified:
            explanation_parts.insert(0, "✅ Verified")
        if not agent.is_active:
            explanation_parts.append("⚠️ Inactive")
        
        return ", ".join(explanation_parts) if explanation_parts else self.explanation_templates[category]
    
    async def batch_update_all_agents(self, batch_size: int = 500, limit: Optional[int] = None):
        """Update trust scores for all agents in batches"""
        
        self.logger.info("🚀 Starting trust scoring batch update for all agents")
        
        session = get_write_session()

        try:
            # Memory guards to avoid zombie PG backends on 17GB agents table
            session.execute(text("SET LOCAL work_mem = '2MB'"))
            session.execute(text("SET LOCAL statement_timeout = '30s'"))

            # Check if trust_score column exists, if not add it
            await self._ensure_trust_score_column(session)

            # Get total count
            total_count = session.execute(
                text("SELECT COUNT(*) FROM agents WHERE is_active = true")
            ).scalar()
            
            if limit:
                total_count = min(total_count, limit)
                
            self.logger.info(f"📊 Processing {total_count} agents in batches of {batch_size}")
            
            processed = 0
            updated = 0
            
            # Process in batches
            offset = 0
            while offset < total_count:
                # Get batch of agents
                batch_query = text("""
                    SELECT id, source, name, description, author, license, capabilities,
                           category, tags, stars, forks, downloads, last_source_update,
                           language, frameworks, protocols, first_indexed, is_verified,
                           is_active, quality_score, activity_score, documentation_score
                    FROM agents 
                    WHERE is_active = true
                    ORDER BY first_indexed DESC
                    LIMIT :limit OFFSET :offset
                """)
                
                current_limit = min(batch_size, total_count - offset)
                batch_results = session.execute(
                    batch_query, 
                    {"limit": current_limit, "offset": offset}
                ).fetchall()
                
                # Process each agent in batch
                trust_updates = []
                
                for row in batch_results:
                    try:
                        # Create agent object from row data
                        agent = self._row_to_agent(row)
                        
                        # Calculate trust score
                        trust_data = await self.calculate_trust_score(agent)
                        
                        # Prepare update data
                        trust_updates.append({
                            "agent_id": str(agent.id),
                            "trust_score": trust_data["total_score"],
                            "trust_explanation": trust_data["explanation"],
                            "trust_components": json.dumps(trust_data["component_scores"]),
                            "trust_calculated_at": datetime.utcnow()
                        })
                        
                        updated += 1
                        
                    except Exception as e:
                        self.logger.warning(f"Failed to calculate trust score for agent {row[0]}: {e}")
                
                # Batch update trust scores
                if trust_updates:
                    await self._batch_update_trust_scores(session, trust_updates)
                
                processed += len(batch_results)
                offset += batch_size
                
                # Progress report
                progress = (processed / total_count) * 100
                self.logger.info(f"📈 Progress: {processed}/{total_count} ({progress:.1f}%) - Updated: {updated}")
                
                # Brief pause to avoid overwhelming the database
                await asyncio.sleep(0.1)
            
            session.commit()
            self.logger.info(f"✅ Trust scoring batch update completed: {updated}/{total_count} agents updated")
            
            return {
                "total_processed": processed,
                "successfully_updated": updated,
                "completion_time": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            session.rollback()
            self.logger.error(f"❌ Batch update failed: {e}")
            raise
        finally:
            session.close()
    
    def _row_to_agent(self, row) -> Agent:
        """Convert database row to Agent object"""
        agent = Agent()
        
        # Map row data to agent attributes
        agent.id = row[0]
        agent.source = row[1]
        agent.name = row[2]
        agent.description = row[3]
        agent.author = row[4]
        agent.license = row[5]
        agent.capabilities = row[6] if row[6] else []
        agent.category = row[7]
        agent.tags = row[8] if row[8] else []
        agent.stars = row[9]
        agent.forks = row[10]
        agent.downloads = row[11]
        agent.last_source_update = row[12]
        agent.language = row[13]
        agent.frameworks = row[14] if row[14] else []
        agent.protocols = row[15] if row[15] else []
        agent.first_indexed = row[16]
        agent.is_verified = row[17]
        agent.is_active = row[18]
        agent.quality_score = row[19]
        agent.activity_score = row[20]
        agent.documentation_score = row[21]
        
        return agent
    
    async def _ensure_trust_score_column(self, session: Session):
        """Ensure trust_score column exists in agents table"""
        
        try:
            # Check if columns exist
            check_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'agents' 
                AND column_name IN ('trust_score', 'trust_explanation', 'trust_components', 'trust_calculated_at')
            """)
            
            existing_columns = [row[0] for row in session.execute(check_query).fetchall()]
            
            # Add missing columns
            columns_to_add = [
                ("trust_score", "REAL"),
                ("trust_explanation", "TEXT"),
                ("trust_components", "JSONB"),
                ("trust_calculated_at", "TIMESTAMP")
            ]
            
            for col_name, col_type in columns_to_add:
                if col_name not in existing_columns:
                    alter_query = text(f"ALTER TABLE agents ADD COLUMN {col_name} {col_type}")
                    session.execute(alter_query)
                    self.logger.info(f"✅ Added column {col_name} to agents table")
            
            session.commit()
            
        except Exception as e:
            self.logger.warning(f"Could not add trust score columns (might already exist): {e}")
    
    async def _batch_update_trust_scores(self, session: Session, trust_updates: List[Dict]):
        """Update trust scores for a batch of agents"""
        
        try:
            for update_data in trust_updates:
                update_query = text("""
                    UPDATE agents 
                    SET trust_score = :trust_score,
                        trust_explanation = :trust_explanation,
                        trust_components = :trust_components,
                        trust_calculated_at = :trust_calculated_at
                    WHERE id = CAST(:agent_id AS uuid)
                """)
                
                session.execute(update_query, update_data)
                
        except Exception as e:
            self.logger.error(f"Batch update failed: {e}")
            raise
    
    async def get_top_trusted_agents(self, limit: int = 20, category: Optional[str] = None) -> List[Dict]:
        """Get top trusted agents"""
        
        session = get_write_session()

        try:
            session.execute(text("SET LOCAL work_mem = '2MB'"))
            session.execute(text("SET LOCAL statement_timeout = '30s'"))
            query = """
                SELECT id, name, category, trust_score, trust_explanation, source, stars
                FROM agents
                WHERE trust_score IS NOT NULL
                AND is_active = true
            """
            
            params = {}
            
            if category:
                query += " AND category = :category"
                params["category"] = category
            
            query += " ORDER BY trust_score DESC LIMIT :limit"
            params["limit"] = limit
            
            results = session.execute(text(query), params).fetchall()
            
            return [
                {
                    "id": str(row[0]),
                    "name": row[1],
                    "category": row[2],
                    "trust_score": row[3],
                    "explanation": row[4],
                    "source": row[5],
                    "stars": row[6]
                }
                for row in results
            ]
            
        finally:
            session.close()


if __name__ == "__main__":
    # Demo trust scoring
    async def demo():
        scorer = TrustScorer()
        
        print("🔄 Running trust scoring batch update for all agents...")
        result = await scorer.batch_update_all_agents(batch_size=100, limit=500)  # Demo with 500 agents
        
        print(f"✅ Batch update completed:")
        print(f"   Total processed: {result['total_processed']}")
        print(f"   Successfully updated: {result['successfully_updated']}")
        print(f"   Completion time: {result['completion_time']}")
        
        print("\n🏆 Top trusted agents:")
        top_agents = await scorer.get_top_trusted_agents(10)
        for i, agent in enumerate(top_agents, 1):
            print(f"  {i}. {agent['name']} ({agent['category']}) - {agent['trust_score']}/100")
            print(f"     {agent['explanation']}")
    
    asyncio.run(demo())