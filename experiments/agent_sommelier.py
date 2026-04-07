"""
AI Agent Sommelier - Experimental Feature
Personalized agent recommendations based on development patterns and preferences
"""

import asyncio
import asyncpg
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass
import json
import hashlib


@dataclass
class DeveloperProfile:
    """Profile of a developer's interests and patterns"""
    user_id: str
    languages: Set[str]
    categories: Set[str] 
    frameworks: Set[str]
    experience_level: str  # beginner, intermediate, advanced
    project_types: Set[str]
    quality_preference: float  # 0-100, how much they value quality vs novelty
    last_updated: datetime


class AgentSommelier:
    """AI-powered agent recommendation engine"""
    
    def __init__(self, db_url: str = "postgresql://anstudio@localhost/agentindex"):
        self.db_url = db_url
    
    async def analyze_developer_pattern(self, queries: List[str], session_id: Optional[str] = None) -> DeveloperProfile:
        """Analyze search queries to build developer profile"""
        
        # Extract patterns from queries
        languages = set()
        categories = set()
        frameworks = set()
        project_types = set()
        
        # Language detection from queries
        language_keywords = {
            "python": ["python", "django", "flask", "fastapi", "pandas", "numpy"],
            "javascript": ["js", "javascript", "react", "vue", "angular", "node"],
            "typescript": ["typescript", "ts", "angular", "nest"],
            "java": ["java", "spring", "maven", "gradle"],
            "go": ["golang", "go", "gin", "echo"],
            "rust": ["rust", "cargo", "actix"],
            "php": ["php", "laravel", "symfony"]
        }
        
        category_keywords = {
            "web-scraping": ["scraping", "crawl", "extract", "parse", "beautiful soup", "selenium"],
            "data-analysis": ["analysis", "visualization", "pandas", "numpy", "statistics"],
            "api-integration": ["api", "rest", "graphql", "webhook", "integration"],
            "database": ["database", "sql", "postgres", "mysql", "mongodb"],
            "machine-learning": ["ml", "ai", "model", "tensorflow", "pytorch", "sklearn"],
            "devops": ["docker", "kubernetes", "ci/cd", "deployment", "infrastructure"],
            "testing": ["test", "testing", "unittest", "pytest", "jest"],
            "security": ["security", "auth", "encryption", "oauth", "jwt"]
        }
        
        framework_keywords = {
            "django": ["django", "drf", "django rest"],
            "react": ["react", "jsx", "react native"],
            "vue": ["vue", "vuejs", "nuxt"],
            "angular": ["angular", "ng", "typescript"],
            "express": ["express", "node", "express.js"],
            "flask": ["flask", "python web"],
            "fastapi": ["fastapi", "async python"],
            "spring": ["spring", "spring boot", "java web"]
        }
        
        # Analyze each query
        for query in queries:
            query_lower = query.lower()
            
            # Detect languages
            for lang, keywords in language_keywords.items():
                if any(keyword in query_lower for keyword in keywords):
                    languages.add(lang)
            
            # Detect categories
            for cat, keywords in category_keywords.items():
                if any(keyword in query_lower for keyword in keywords):
                    categories.add(cat)
            
            # Detect frameworks
            for fw, keywords in framework_keywords.items():
                if any(keyword in query_lower for keyword in keywords):
                    frameworks.add(fw)
        
        # Determine experience level based on query complexity
        experience_level = self._determine_experience_level(queries)
        
        # Determine quality preference (based on query specificity)
        quality_preference = self._calculate_quality_preference(queries)
        
        # Generate user ID from session or create anonymous one
        user_id = session_id or hashlib.md5("|".join(sorted(queries)).encode()).hexdigest()[:16]
        
        return DeveloperProfile(
            user_id=user_id,
            languages=languages,
            categories=categories,
            frameworks=frameworks,
            experience_level=experience_level,
            project_types=project_types,  # Could be expanded
            quality_preference=quality_preference,
            last_updated=datetime.utcnow()
        )
    
    def _determine_experience_level(self, queries: List[str]) -> str:
        """Determine developer experience level from query patterns"""
        
        beginner_indicators = ["tutorial", "how to", "getting started", "beginner", "learn", "simple"]
        advanced_indicators = ["optimization", "performance", "architecture", "scalability", "enterprise", "microservices"]
        
        beginner_score = sum(1 for query in queries for indicator in beginner_indicators if indicator in query.lower())
        advanced_score = sum(1 for query in queries for indicator in advanced_indicators if indicator in query.lower())
        
        if advanced_score > beginner_score and advanced_score >= 2:
            return "advanced"
        elif beginner_score > 0:
            return "beginner"
        else:
            return "intermediate"
    
    def _calculate_quality_preference(self, queries: List[str]) -> float:
        """Calculate how much user values quality vs novelty"""
        
        quality_indicators = ["reliable", "production", "stable", "enterprise", "tested", "popular"]
        novelty_indicators = ["new", "latest", "cutting edge", "experimental", "beta"]
        
        quality_score = sum(1 for query in queries for indicator in quality_indicators if indicator in query.lower())
        novelty_score = sum(1 for query in queries for indicator in novelty_indicators if indicator in query.lower())
        
        if quality_score == 0 and novelty_score == 0:
            return 70.0  # Default preference
        
        total = quality_score + novelty_score
        return (quality_score / total) * 100 if total > 0 else 70.0
    
    async def get_personalized_recommendations(
        self, 
        profile: DeveloperProfile, 
        limit: int = 10,
        exclude_seen: Optional[Set[str]] = None
    ) -> List[Dict[str, Any]]:
        """Get personalized agent recommendations based on profile"""
        
        conn = await asyncpg.connect(self.db_url)
        exclude_seen = exclude_seen or set()
        
        try:
            # Build dynamic query based on profile
            conditions = ["a.is_active = true"]
            params = []
            param_count = 0
            
            # Language preferences
            if profile.languages:
                param_count += 1
                conditions.append(f"a.language = ANY(${param_count})")
                params.append(list(profile.languages))
            
            # Category preferences  
            if profile.categories:
                param_count += 1
                conditions.append(f"a.category = ANY(${param_count})")
                params.append(list(profile.categories))
            
            # Quality threshold based on preference
            quality_threshold = profile.quality_preference
            if quality_threshold > 50:
                param_count += 1
                conditions.append(f"a.quality_score >= ${param_count}")
                params.append(quality_threshold)
            
            # Experience level adjustments
            if profile.experience_level == "beginner":
                # Prefer well-documented, stable agents
                conditions.append("a.documentation_score > 60")
            elif profile.experience_level == "advanced":
                # Include cutting-edge agents
                conditions.append("a.quality_score > 40")  # Lower threshold for advanced users
            
            # Exclude previously seen agents
            if exclude_seen:
                param_count += 1
                conditions.append(f"a.id NOT IN (SELECT unnest(${param_count}::uuid[]))")
                params.append(list(exclude_seen))
            
            # Build final query
            where_clause = " AND ".join(conditions)
            
            query = f"""
                SELECT a.*, 
                       -- Personalization score calculation
                       CASE 
                           WHEN a.language = ANY($1) THEN 20 ELSE 0 
                       END +
                       CASE 
                           WHEN a.category = ANY($2) THEN 15 ELSE 0
                       END +
                       CASE 
                           WHEN a.quality_score > ${profile.quality_preference} THEN 10 ELSE 0
                       END +
                       -- Popularity bonus
                       LEAST(a.stars::float / 1000 * 5, 10) +
                       -- Recency bonus (newer agents get slight boost)
                       CASE 
                           WHEN a.first_indexed > NOW() - INTERVAL '30 days' THEN 5 ELSE 0
                       END as personalization_score
                FROM agents a
                WHERE {where_clause}
                ORDER BY personalization_score DESC, a.quality_score DESC
                LIMIT ${limit + 5}  -- Get extra for diversity filtering
            """
            
            # Add language and category params at the beginning
            final_params = [
                list(profile.languages) if profile.languages else [],
                list(profile.categories) if profile.categories else []
            ] + params
            
            results = await conn.fetch(query, *final_params)
            
            # Post-process for diversity and explanation
            recommendations = []
            seen_categories = set()
            
            for row in results:
                if len(recommendations) >= limit:
                    break
                
                # Ensure category diversity (max 3 per category)
                cat_count = sum(1 for r in recommendations if r.get("category") == row["category"])
                if cat_count >= 3:
                    continue
                
                rec = dict(row)
                rec["recommendation_reason"] = self._generate_recommendation_reason(rec, profile)
                rec["match_score"] = min(int(rec["personalization_score"]), 100)
                
                recommendations.append(rec)
            
            return recommendations
            
        finally:
            await conn.close()
    
    def _generate_recommendation_reason(self, agent: Dict[str, Any], profile: DeveloperProfile) -> str:
        """Generate human-readable reason for recommendation"""
        
        reasons = []
        
        # Language match
        if agent.get("language") in profile.languages:
            reasons.append(f"You work with {agent['language']}")
        
        # Category match
        if agent.get("category") in profile.categories:
            reasons.append(f"Matches your {agent['category']} interests")
        
        # Quality preference
        if agent.get("quality_score", 0) >= profile.quality_preference:
            reasons.append(f"High quality ({agent['quality_score']:.0f}/100)")
        
        # Experience level match
        if profile.experience_level == "beginner" and agent.get("documentation_score", 0) > 70:
            reasons.append("Well documented for beginners")
        elif profile.experience_level == "advanced" and agent.get("quality_score", 0) < 60:
            reasons.append("Cutting-edge technology")
        
        # Popular
        if agent.get("stars", 0) > 1000:
            reasons.append(f"Popular ({agent['stars']:,} stars)")
        
        # Recent
        if agent.get("first_indexed") and (datetime.utcnow() - agent["first_indexed"]).days < 30:
            reasons.append("Recently discovered")
        
        if reasons:
            return " • ".join(reasons[:2])  # Max 2 reasons
        else:
            return "Recommended for you"
    
    async def save_profile(self, profile: DeveloperProfile) -> None:
        """Save developer profile for future recommendations"""
        
        conn = await asyncpg.connect(self.db_url)
        
        try:
            await self._ensure_profiles_table(conn)
            
            # Upsert profile
            await conn.execute("""
                INSERT INTO developer_profiles (
                    user_id, languages, categories, frameworks, 
                    experience_level, quality_preference, last_updated
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (user_id) DO UPDATE SET
                    languages = EXCLUDED.languages,
                    categories = EXCLUDED.categories,
                    frameworks = EXCLUDED.frameworks,
                    experience_level = EXCLUDED.experience_level,
                    quality_preference = EXCLUDED.quality_preference,
                    last_updated = EXCLUDED.last_updated
            """, 
                profile.user_id,
                list(profile.languages),
                list(profile.categories), 
                list(profile.frameworks),
                profile.experience_level,
                profile.quality_preference,
                profile.last_updated
            )
            
        except asyncpg.UndefinedTableError:
            await self._ensure_profiles_table(conn)
            await self.save_profile(profile)  # Retry
            
        finally:
            await conn.close()
    
    async def _ensure_profiles_table(self, conn: asyncpg.Connection) -> None:
        """Create profiles table if it doesn't exist"""
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS developer_profiles (
                user_id TEXT PRIMARY KEY,
                languages TEXT[] DEFAULT '{}',
                categories TEXT[] DEFAULT '{}',
                frameworks TEXT[] DEFAULT '{}',
                experience_level TEXT DEFAULT 'intermediate',
                quality_preference FLOAT DEFAULT 70.0,
                last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)


class SommelierInterface:
    """Web interface for the Agent Sommelier"""
    
    def __init__(self):
        self.sommelier = AgentSommelier()
    
    async def generate_recommendation_page(
        self, 
        queries: List[str], 
        session_id: Optional[str] = None
    ) -> str:
        """Generate personalized recommendation page"""
        
        # Analyze profile
        profile = await self.sommelier.analyze_developer_pattern(queries, session_id)
        
        # Get recommendations
        recommendations = await self.sommelier.get_personalized_recommendations(profile)
        
        # Save profile for future use
        await self.sommelier.save_profile(profile)
        
        return self._generate_html(profile, recommendations)
    
    def _generate_html(self, profile: DeveloperProfile, recommendations: List[Dict[str, Any]]) -> str:
        """Generate HTML for recommendations"""
        
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>🍷 Your Personal Agent Sommelier</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        .header {{ text-align: center; color: white; margin-bottom: 40px; }}
        .header h1 {{ font-size: 3em; margin-bottom: 10px; text-shadow: 0 2px 4px rgba(0,0,0,0.3); }}
        .profile-card {{ background: rgba(255,255,255,0.95); border-radius: 16px; padding: 25px; margin-bottom: 30px; backdrop-filter: blur(10px); }}
        .profile-badges {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 15px; }}
        .badge {{ background: #3b82f6; color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.8em; }}
        .experience-badge {{ background: #10b981; }}
        .quality-badge {{ background: #f59e0b; }}
        .recommendations {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; }}
        .rec-card {{ background: rgba(255,255,255,0.95); border-radius: 16px; padding: 25px; backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.3); transition: transform 0.3s, box-shadow 0.3s; }}
        .rec-card:hover {{ transform: translateY(-5px); box-shadow: 0 20px 40px rgba(0,0,0,0.2); }}
        .rec-header {{ display: flex; justify-content: between; align-items: flex-start; margin-bottom: 15px; }}
        .rec-title {{ font-size: 1.3em; font-weight: bold; color: #1e293b; margin-bottom: 8px; }}
        .match-score {{ background: linear-gradient(135deg, #3b82f6, #8b5cf6); color: white; padding: 6px 12px; border-radius: 20px; font-size: 0.8em; font-weight: bold; }}
        .rec-description {{ color: #475569; margin-bottom: 15px; line-height: 1.5; }}
        .rec-reason {{ background: #f1f5f9; padding: 10px; border-radius: 8px; font-size: 0.9em; color: #475569; margin-bottom: 15px; }}
        .rec-stats {{ display: flex; gap: 15px; margin-bottom: 15px; }}
        .stat {{ background: white; padding: 8px 12px; border-radius: 6px; font-size: 0.8em; text-align: center; }}
        .rec-actions {{ display: flex; gap: 10px; }}
        .btn {{ padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-size: 0.9em; }}
        .btn-primary {{ background: #3b82f6; color: white; }}
        .btn-secondary {{ background: #e5e7eb; color: #374151; }}
        .sommelier-note {{ background: rgba(255,255,255,0.9); border-radius: 12px; padding: 20px; margin: 30px 0; text-align: center; color: #475569; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🍷 Your Personal Agent Sommelier</h1>
            <p>Curated recommendations based on your development patterns</p>
        </div>
        
        <div class="profile-card">
            <h3>👤 Your Developer Profile</h3>
            <p><strong>Experience Level:</strong> <span class="badge experience-badge">{profile.experience_level.title()}</span></p>
            <p><strong>Quality Preference:</strong> <span class="badge quality-badge">{profile.quality_preference:.0f}% Quality Focus</span></p>
            
            <div class="profile-badges">
                {self._render_profile_badges(profile)}
            </div>
        </div>
        
        <h2 style="color: white; text-align: center; margin-bottom: 30px;">🎯 Personalized Recommendations</h2>
        
        <div class="recommendations">
            {self._render_recommendations(recommendations)}
        </div>
        
        <div class="sommelier-note">
            <h3>🤖 About Your Sommelier</h3>
            <p>Your recommendations are based on analyzing your search patterns, preferred technologies, and quality preferences. 
            The more you use AgentIndex, the better your recommendations become!</p>
            <p><strong>Tip:</strong> Bookmark this page or save your session ID to get consistent recommendations.</p>
        </div>
    </div>
</body>
</html>
        """
    
    def _render_profile_badges(self, profile: DeveloperProfile) -> str:
        """Render profile badges"""
        badges = []
        
        for lang in sorted(profile.languages):
            badges.append(f'<span class="badge">{lang.title()}</span>')
        
        for cat in sorted(profile.categories):
            badges.append(f'<span class="badge">{cat.replace("-", " ").title()}</span>')
        
        return "\\n".join(badges) if badges else '<span class="badge">General Purpose</span>'
    
    def _render_recommendations(self, recommendations: List[Dict[str, Any]]) -> str:
        """Render recommendation cards"""
        if not recommendations:
            return '<p style="color: white; text-align: center;">No recommendations found. Try different search queries!</p>'
        
        html = ""
        for rec in recommendations:
            quality = rec.get("quality_score", 0)
            stars = rec.get("stars", 0)
            
            html += f"""
            <div class="rec-card">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 15px;">
                    <div class="rec-title">{rec.get('name', 'Unknown Agent')}</div>
                    <div class="match-score">{rec.get('match_score', 0)}% Match</div>
                </div>
                
                <div class="rec-description">
                    {rec.get('description', 'No description available')[:150]}...
                </div>
                
                <div class="rec-reason">
                    💡 <strong>Why recommended:</strong> {rec.get('recommendation_reason', 'Matches your interests')}
                </div>
                
                <div class="rec-stats">
                    <div class="stat">
                        <div>Quality</div>
                        <div><strong>{quality:.0f}/100</strong></div>
                    </div>
                    <div class="stat">
                        <div>Stars</div>
                        <div><strong>{stars:,}</strong></div>
                    </div>
                    <div class="stat">
                        <div>Source</div>
                        <div><strong>{rec.get('source', 'Unknown')}</strong></div>
                    </div>
                </div>
                
                <div class="rec-actions">
                    <a href="{rec.get('source_url', '#')}" class="btn btn-primary" target="_blank">View Agent</a>
                    <button class="btn btn-secondary" onclick="saveAgent('{rec.get('id', '')}')">Save for Later</button>
                </div>
            </div>
            """
        
        return html


if __name__ == "__main__":
    async def test_sommelier():
        sommelier = AgentSommelier()
        interface = SommelierInterface()
        
        # Test queries simulating a Python web developer
        test_queries = [
            "python web scraping",
            "django rest api", 
            "database migration tool",
            "automated testing framework",
            "production deployment"
        ]
        
        print("🍷 Testing AI Agent Sommelier...")
        print(f"Sample queries: {test_queries}")
        
        try:
            # Generate recommendations page
            html = await interface.generate_recommendation_page(test_queries, "test-session")
            
            with open("sommelier_demo.html", "w") as f:
                f.write(html)
            
            print("✅ Sommelier test completed!")
            print("📄 Demo saved to sommelier_demo.html")
            
        except Exception as e:
            print(f"❌ Sommelier test failed: {e}")
            print("Note: This experiment requires database setup")
    
    asyncio.run(test_sommelier())