"""
AI Agent Sommelier - Personalized Agent Recommendations
Machine learning-powered system that learns user preferences and recommends agents
"""

import json
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from collections import defaultdict, Counter
import sqlite3
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import KMeans
import joblib
import os


@dataclass
class UserProfile:
    """User preference profile"""
    user_id: str
    preferences: Dict[str, float]  # category -> preference score
    interaction_history: List[str]  # agent IDs interacted with
    preferred_features: List[str]   # preferred features/keywords
    expertise_level: str           # beginner, intermediate, advanced
    use_cases: List[str]           # common use cases
    last_active: datetime
    created_at: datetime
    
    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            "last_active": self.last_active.isoformat(),
            "created_at": self.created_at.isoformat()
        }


@dataclass
class Recommendation:
    """Agent recommendation with reasoning"""
    agent_id: str
    agent_name: str
    confidence: float
    reasoning: str
    category: str
    trust_score: Optional[float]
    similarity_score: float
    novelty_score: float
    recommendation_type: str  # "similar", "complementary", "trending", "explore"
    
    def to_dict(self) -> Dict:
        return asdict(self)


class AIAgentSommelier:
    """Personalized agent recommendation system"""
    
    def __init__(self, db_path: str = "sommelier_data.db", model_path: str = "sommelier_models/"):
        self.db_path = db_path
        self.model_path = model_path
        self.init_database()
        
        # ML models
        self.vectorizer = None
        self.agent_embeddings = None
        self.user_clusters = None
        self.recommendation_model = None
        
        # Load or initialize models
        self.load_models()
        
        # Category mappings for preferences
        self.categories = [
            "web-scraping", "data-analysis", "api-integration", "code-generation",
            "database", "ml-inference", "file-processing", "communication",
            "automation", "monitoring", "testing", "security"
        ]
    
    def init_database(self):
        """Initialize database for user profiles and interactions"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # User profiles table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                preferences TEXT,  -- JSON
                interaction_history TEXT,  -- JSON
                preferred_features TEXT,   -- JSON
                expertise_level TEXT,
                use_cases TEXT,  -- JSON
                last_active DATETIME,
                created_at DATETIME
            )
        ''')
        
        # User interactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                agent_id TEXT,
                agent_name TEXT,
                category TEXT,
                interaction_type TEXT,  -- view, click, bookmark, rate
                rating REAL,  -- 1-5 stars
                timestamp DATETIME,
                context TEXT  -- search query or use case
            )
        ''')
        
        # Agent features table (cached from main DB)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_features (
                agent_id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                category TEXT,
                features TEXT,  -- JSON array of extracted features
                trust_score REAL,
                popularity_score REAL,
                last_updated DATETIME
            )
        ''')
        
        # Recommendation history
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recommendation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                agent_id TEXT,
                confidence REAL,
                reasoning TEXT,
                recommendation_type TEXT,
                was_clicked BOOLEAN DEFAULT FALSE,
                was_useful BOOLEAN,  -- User feedback
                timestamp DATETIME
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def load_models(self):
        """Load or initialize ML models"""
        os.makedirs(self.model_path, exist_ok=True)
        
        try:
            # Try to load existing models
            self.vectorizer = joblib.load(f"{self.model_path}/vectorizer.pkl")
            self.agent_embeddings = joblib.load(f"{self.model_path}/agent_embeddings.pkl")
            self.user_clusters = joblib.load(f"{self.model_path}/user_clusters.pkl")
            print("✅ Loaded existing ML models")
        except FileNotFoundError:
            # Initialize new models
            self.vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')
            self.agent_embeddings = {}
            self.user_clusters = KMeans(n_clusters=5, random_state=42)
            print("🔄 Initialized new ML models")
    
    def save_models(self):
        """Save ML models to disk"""
        joblib.dump(self.vectorizer, f"{self.model_path}/vectorizer.pkl")
        joblib.dump(self.agent_embeddings, f"{self.model_path}/agent_embeddings.pkl") 
        joblib.dump(self.user_clusters, f"{self.model_path}/user_clusters.pkl")
    
    def update_user_profile(
        self, 
        user_id: str,
        agent_id: str,
        interaction_type: str,
        rating: Optional[float] = None,
        context: Optional[str] = None
    ):
        """Update user profile based on interaction"""
        
        # Log the interaction
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO user_interactions 
            (user_id, agent_id, interaction_type, rating, timestamp, context)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, agent_id, interaction_type, rating, datetime.utcnow(), context))
        
        # Get or create user profile
        profile = self.get_user_profile(user_id)
        if not profile:
            profile = UserProfile(
                user_id=user_id,
                preferences={},
                interaction_history=[],
                preferred_features=[],
                expertise_level="beginner",
                use_cases=[],
                last_active=datetime.utcnow(),
                created_at=datetime.utcnow()
            )
        
        # Update interaction history
        if agent_id not in profile.interaction_history:
            profile.interaction_history.append(agent_id)
        
        profile.last_active = datetime.utcnow()
        
        # Get agent info to update preferences
        cursor.execute('''
            SELECT category, features FROM agent_features WHERE agent_id = ?
        ''', (agent_id,))
        
        agent_info = cursor.fetchone()
        if agent_info:
            category, features_json = agent_info
            
            # Update category preferences
            if category:
                current_score = profile.preferences.get(category, 0.0)
                # Increase preference based on interaction type and rating
                boost = self._calculate_preference_boost(interaction_type, rating)
                profile.preferences[category] = min(1.0, current_score + boost)
            
            # Update preferred features
            if features_json:
                features = json.loads(features_json)
                for feature in features:
                    if feature not in profile.preferred_features:
                        profile.preferred_features.append(feature)
        
        # Save updated profile
        self.save_user_profile(profile)
        conn.commit()
        conn.close()
    
    def _calculate_preference_boost(self, interaction_type: str, rating: Optional[float]) -> float:
        """Calculate how much to boost category preference"""
        base_boosts = {
            "view": 0.05,
            "click": 0.10,
            "bookmark": 0.25,
            "rate": 0.15,
            "download": 0.30
        }
        
        boost = base_boosts.get(interaction_type, 0.05)
        
        # Adjust based on rating
        if rating and rating >= 4.0:
            boost *= 2.0
        elif rating and rating <= 2.0:
            boost *= 0.5
        
        return boost
    
    def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """Get user profile"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM user_profiles WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return None
        
        profile = UserProfile(
            user_id=row[0],
            preferences=json.loads(row[1]) if row[1] else {},
            interaction_history=json.loads(row[2]) if row[2] else [],
            preferred_features=json.loads(row[3]) if row[3] else [],
            expertise_level=row[4] or "beginner",
            use_cases=json.loads(row[5]) if row[5] else [],
            last_active=datetime.fromisoformat(row[6]),
            created_at=datetime.fromisoformat(row[7])
        )
        
        conn.close()
        return profile
    
    def save_user_profile(self, profile: UserProfile):
        """Save user profile"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO user_profiles 
            (user_id, preferences, interaction_history, preferred_features, 
             expertise_level, use_cases, last_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            profile.user_id,
            json.dumps(profile.preferences),
            json.dumps(profile.interaction_history),
            json.dumps(profile.preferred_features),
            profile.expertise_level,
            json.dumps(profile.use_cases),
            profile.last_active,
            profile.created_at
        ))
        
        conn.commit()
        conn.close()
    
    def get_recommendations(
        self, 
        user_id: str, 
        limit: int = 10,
        include_explored: bool = False
    ) -> List[Recommendation]:
        """Get personalized recommendations for user"""
        
        profile = self.get_user_profile(user_id)
        if not profile:
            # Return popular agents for new users
            return self.get_popular_recommendations(limit)
        
        recommendations = []
        
        # Similar agents (based on interaction history)
        similar_recs = self._get_similar_recommendations(profile, limit // 3)
        recommendations.extend(similar_recs)
        
        # Complementary agents (different but useful categories)
        complementary_recs = self._get_complementary_recommendations(profile, limit // 3)
        recommendations.extend(complementary_recs)
        
        # Trending agents in preferred categories
        trending_recs = self._get_trending_recommendations(profile, limit // 3)
        recommendations.extend(trending_recs)
        
        # Exploration recommendations (new categories)
        if include_explored:
            explore_recs = self._get_exploration_recommendations(profile, limit - len(recommendations))
            recommendations.extend(explore_recs)
        
        # Remove duplicates and sort by confidence
        seen = set()
        unique_recommendations = []
        for rec in recommendations:
            if rec.agent_id not in seen:
                seen.add(rec.agent_id)
                unique_recommendations.append(rec)
        
        unique_recommendations.sort(key=lambda x: x.confidence, reverse=True)
        return unique_recommendations[:limit]
    
    def _get_similar_recommendations(self, profile: UserProfile, limit: int) -> List[Recommendation]:
        """Get recommendations similar to user's interaction history"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if not profile.interaction_history:
            conn.close()
            return []
        
        # Get features of agents user has interacted with
        placeholders = ','.join(['?' for _ in profile.interaction_history])
        cursor.execute(f'''
            SELECT agent_id, name, category, features, trust_score
            FROM agent_features 
            WHERE agent_id IN ({placeholders})
        ''', profile.interaction_history)
        
        interacted_agents = cursor.fetchall()
        if not interacted_agents:
            conn.close()
            return []
        
        # Extract features from interacted agents
        all_features = []
        for agent in interacted_agents:
            if agent[3]:  # features column
                features = json.loads(agent[3])
                all_features.extend(features)
        
        feature_counts = Counter(all_features)
        top_features = [f[0] for f in feature_counts.most_common(10)]
        
        # Find agents with similar features that user hasn't interacted with
        cursor.execute('''
            SELECT agent_id, name, category, features, trust_score
            FROM agent_features 
            WHERE agent_id NOT IN ({})
        '''.format(placeholders), profile.interaction_history)
        
        candidate_agents = cursor.fetchall()
        recommendations = []
        
        for agent in candidate_agents:
            agent_id, name, category, features_json, trust_score = agent
            
            if not features_json:
                continue
            
            agent_features = json.loads(features_json)
            
            # Calculate similarity based on feature overlap
            overlap = len(set(agent_features) & set(top_features))
            similarity = overlap / max(len(top_features), 1)
            
            if similarity > 0.2:  # Minimum similarity threshold
                confidence = similarity * 0.8 + (trust_score or 0) * 0.002  # Scale trust score
                
                rec = Recommendation(
                    agent_id=agent_id,
                    agent_name=name,
                    confidence=min(1.0, confidence),
                    reasoning=f"Similar to your previous choices: {', '.join(top_features[:3])}",
                    category=category,
                    trust_score=trust_score,
                    similarity_score=similarity,
                    novelty_score=0.0,
                    recommendation_type="similar"
                )
                
                recommendations.append(rec)
        
        conn.close()
        recommendations.sort(key=lambda x: x.confidence, reverse=True)
        return recommendations[:limit]
    
    def _get_complementary_recommendations(self, profile: UserProfile, limit: int) -> List[Recommendation]:
        """Get recommendations that complement user's existing preferences"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Find categories that complement user's preferences
        complementary_categories = self._get_complementary_categories(profile.preferences)
        
        if not complementary_categories:
            conn.close()
            return []
        
        # Exclude agents user has already interacted with
        exclusions = profile.interaction_history
        placeholders = ','.join(['?' for _ in exclusions]) if exclusions else "NULL"
        
        query = f'''
            SELECT agent_id, name, category, trust_score, popularity_score
            FROM agent_features 
            WHERE category IN ({','.join(['?' for _ in complementary_categories])})
            AND trust_score > 60
        '''
        
        params = complementary_categories
        
        if exclusions:
            query += f' AND agent_id NOT IN ({placeholders})'
            params.extend(exclusions)
        
        query += ' ORDER BY trust_score DESC, popularity_score DESC LIMIT ?'
        params.append(limit * 2)
        
        cursor.execute(query, params)
        candidates = cursor.fetchall()
        
        recommendations = []
        for agent in candidates:
            agent_id, name, category, trust_score, popularity_score = agent
            
            # Calculate confidence based on trust score and complementary fit
            complement_score = self._calculate_complement_score(category, profile.preferences)
            confidence = (trust_score or 50) * 0.008 + complement_score * 0.5
            
            rec = Recommendation(
                agent_id=agent_id,
                agent_name=name,
                confidence=min(1.0, confidence),
                reasoning=f"Complements your {category} workflow",
                category=category,
                trust_score=trust_score,
                similarity_score=0.0,
                novelty_score=complement_score,
                recommendation_type="complementary"
            )
            
            recommendations.append(rec)
        
        conn.close()
        recommendations.sort(key=lambda x: x.confidence, reverse=True)
        return recommendations[:limit]
    
    def _get_complementary_categories(self, preferences: Dict[str, float]) -> List[str]:
        """Get categories that complement user's preferences"""
        # Define category relationships
        complements = {
            "web-scraping": ["data-analysis", "database", "file-processing"],
            "data-analysis": ["visualization", "database", "ml-inference"],
            "api-integration": ["monitoring", "testing", "security"],
            "code-generation": ["testing", "documentation", "refactoring"],
            "database": ["data-analysis", "backup", "monitoring"],
            "ml-inference": ["data-preprocessing", "model-deployment", "monitoring"]
        }
        
        complementary = []
        for category, score in preferences.items():
            if score > 0.3 and category in complements:
                complementary.extend(complements[category])
        
        # Remove duplicates and categories user already prefers
        complementary = list(set(complementary) - set(preferences.keys()))
        return complementary[:5]
    
    def _calculate_complement_score(self, category: str, preferences: Dict[str, float]) -> float:
        """Calculate how well a category complements user preferences"""
        # Higher score for categories that work well with user's preferred categories
        complement_weights = {
            ("web-scraping", "data-analysis"): 0.8,
            ("data-analysis", "visualization"): 0.9,
            ("api-integration", "monitoring"): 0.7,
            ("code-generation", "testing"): 0.8,
        }
        
        max_score = 0.0
        for pref_category, pref_score in preferences.items():
            key = tuple(sorted([category, pref_category]))
            if key in complement_weights:
                score = complement_weights[key] * pref_score
                max_score = max(max_score, score)
        
        return max_score
    
    def _get_trending_recommendations(self, profile: UserProfile, limit: int) -> List[Recommendation]:
        """Get trending agents in user's preferred categories"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        preferred_categories = [cat for cat, score in profile.preferences.items() if score > 0.2]
        if not preferred_categories:
            conn.close()
            return []
        
        # Get trending agents from recommendation history (most recommended recently)
        query = '''
            SELECT r.agent_id, af.name, af.category, af.trust_score,
                   COUNT(*) as recommendation_count
            FROM recommendation_history r
            JOIN agent_features af ON r.agent_id = af.agent_id
            WHERE af.category IN ({}) 
            AND r.timestamp >= ?
            AND r.agent_id NOT IN ({})
            GROUP BY r.agent_id
            ORDER BY recommendation_count DESC, af.trust_score DESC
            LIMIT ?
        '''.format(
            ','.join(['?' for _ in preferred_categories]),
            ','.join(['?' for _ in profile.interaction_history]) if profile.interaction_history else "NULL"
        )
        
        params = preferred_categories + [datetime.utcnow() - timedelta(days=7)]
        if profile.interaction_history:
            params.extend(profile.interaction_history)
        params.append(limit)
        
        cursor.execute(query, params)
        trending_agents = cursor.fetchall()
        
        recommendations = []
        for agent in trending_agents:
            agent_id, name, category, trust_score, rec_count = agent
            
            # Calculate confidence based on trending popularity and user preference
            category_pref = profile.preferences.get(category, 0.0)
            trending_score = min(1.0, rec_count / 10.0)  # Normalize recommendation count
            confidence = category_pref * 0.4 + trending_score * 0.4 + (trust_score or 50) * 0.004
            
            rec = Recommendation(
                agent_id=agent_id,
                agent_name=name,
                confidence=min(1.0, confidence),
                reasoning=f"Trending in {category} - {rec_count} recent recommendations",
                category=category,
                trust_score=trust_score,
                similarity_score=0.0,
                novelty_score=trending_score,
                recommendation_type="trending"
            )
            
            recommendations.append(rec)
        
        conn.close()
        return recommendations
    
    def _get_exploration_recommendations(self, profile: UserProfile, limit: int) -> List[Recommendation]:
        """Get recommendations to help user explore new categories"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Find categories user hasn't explored much
        all_categories = set(self.categories)
        explored_categories = set(profile.preferences.keys())
        unexplored_categories = list(all_categories - explored_categories)
        
        if not unexplored_categories:
            conn.close()
            return []
        
        # Get highly-rated agents from unexplored categories
        query = '''
            SELECT agent_id, name, category, trust_score, popularity_score
            FROM agent_features 
            WHERE category IN ({})
            AND trust_score > 75
            ORDER BY trust_score DESC, popularity_score DESC
            LIMIT ?
        '''.format(','.join(['?' for _ in unexplored_categories]))
        
        cursor.execute(query, unexplored_categories + [limit])
        exploration_agents = cursor.fetchall()
        
        recommendations = []
        for agent in exploration_agents:
            agent_id, name, category, trust_score, popularity_score = agent
            
            # Lower confidence for exploration to balance with other recommendations
            confidence = (trust_score or 50) * 0.006 + 0.2  # Base exploration bonus
            
            rec = Recommendation(
                agent_id=agent_id,
                agent_name=name,
                confidence=min(0.7, confidence),  # Cap exploration confidence
                reasoning=f"Explore {category} - highly rated by the community",
                category=category,
                trust_score=trust_score,
                similarity_score=0.0,
                novelty_score=1.0,
                recommendation_type="explore"
            )
            
            recommendations.append(rec)
        
        conn.close()
        return recommendations
    
    def get_popular_recommendations(self, limit: int = 10) -> List[Recommendation]:
        """Get popular agents for new users"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT agent_id, name, category, trust_score, popularity_score
            FROM agent_features 
            WHERE trust_score > 70
            ORDER BY popularity_score DESC, trust_score DESC
            LIMIT ?
        ''', (limit,))
        
        popular_agents = cursor.fetchall()
        recommendations = []
        
        for agent in popular_agents:
            agent_id, name, category, trust_score, popularity_score = agent
            
            confidence = (trust_score or 50) * 0.008 + (popularity_score or 0) * 0.002
            
            rec = Recommendation(
                agent_id=agent_id,
                agent_name=name,
                confidence=min(1.0, confidence),
                reasoning="Popular choice for getting started",
                category=category,
                trust_score=trust_score,
                similarity_score=0.0,
                novelty_score=0.0,
                recommendation_type="popular"
            )
            
            recommendations.append(rec)
        
        conn.close()
        return recommendations
    
    def log_recommendation_feedback(
        self, 
        user_id: str, 
        agent_id: str, 
        was_clicked: bool = False,
        was_useful: Optional[bool] = None
    ):
        """Log user feedback on recommendations"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE recommendation_history
            SET was_clicked = ?, was_useful = ?
            WHERE user_id = ? AND agent_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (was_clicked, was_useful, user_id, agent_id))
        
        conn.commit()
        conn.close()


# Sommelier HTML interface
SOMMELIER_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>🍷 AI Agent Sommelier</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
        .header { text-align: center; margin-bottom: 30px; }
        .recommendation-card { background: white; border-radius: 10px; padding: 20px; margin: 15px 0; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .agent-name { font-size: 18px; font-weight: bold; color: #333; margin-bottom: 8px; }
        .agent-category { background: #e8f4f8; color: #007cba; padding: 4px 8px; border-radius: 15px; font-size: 12px; margin-right: 10px; }
        .confidence-bar { height: 8px; background: #ddd; border-radius: 4px; margin: 10px 0; overflow: hidden; }
        .confidence-fill { height: 100%; background: linear-gradient(90deg, #28a745, #ffc107, #dc3545); }
        .reasoning { color: #666; font-style: italic; margin: 10px 0; }
        .trust-score { color: #28a745; font-weight: bold; }
        .recommendation-type { float: right; font-size: 12px; color: #666; background: #f8f9fa; padding: 2px 6px; border-radius: 3px; }
        .action-buttons { margin-top: 15px; }
        .btn { padding: 8px 15px; border: none; border-radius: 5px; cursor: pointer; margin-right: 10px; font-size: 14px; }
        .btn-primary { background: #007cba; color: white; }
        .btn-secondary { background: #6c757d; color: white; }
        .btn-success { background: #28a745; color: white; }
        .profile-section { background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .preference-bar { height: 20px; background: #ddd; border-radius: 10px; margin: 5px 0; overflow: hidden; }
        .preference-fill { height: 100%; background: #007cba; }
        .filters { background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .filter-group { display: inline-block; margin-right: 20px; }
        .user-id-input { padding: 10px; border: 1px solid #ddd; border-radius: 5px; margin-right: 10px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🍷 AI Agent Sommelier</h1>
        <p>Personalized agent recommendations based on your preferences and usage patterns</p>
    </div>
    
    <div class="filters">
        <div class="filter-group">
            <label>User ID:</label>
            <input type="text" id="user-id" class="user-id-input" placeholder="Enter your user ID">
            <button class="btn btn-primary" onclick="loadRecommendations()">Get Recommendations</button>
        </div>
        <div class="filter-group">
            <label>Include Exploration:</label>
            <input type="checkbox" id="include-exploration"> Discover new categories
        </div>
    </div>
    
    <div class="profile-section" id="user-profile" style="display: none;">
        <h3>📊 Your Preference Profile</h3>
        <div id="preferences-display">
            <!-- User preferences will be shown here -->
        </div>
    </div>
    
    <div id="recommendations-container">
        <div style="text-align: center; color: #666; padding: 40px;">
            Enter your user ID above to get personalized recommendations
        </div>
    </div>
    
    <script>
        function loadRecommendations() {
            const userId = document.getElementById('user-id').value;
            const includeExploration = document.getElementById('include-exploration').checked;
            
            if (!userId) {
                alert('Please enter a user ID');
                return;
            }
            
            // Show loading state
            document.getElementById('recommendations-container').innerHTML = 
                '<div style="text-align: center; padding: 40px;">🔄 Loading personalized recommendations...</div>';
            
            // Fetch recommendations (this would be an actual API call)
            setTimeout(() => {
                displayRecommendations(getSampleRecommendations());
                displayUserProfile(getSampleProfile());
            }, 1500);
        }
        
        function displayRecommendations(recommendations) {
            const container = document.getElementById('recommendations-container');
            container.innerHTML = '<h2>🎯 Your Personalized Recommendations</h2>';
            
            recommendations.forEach(rec => {
                const card = document.createElement('div');
                card.className = 'recommendation-card';
                card.innerHTML = `
                    <div class="recommendation-type">${rec.recommendation_type}</div>
                    <div class="agent-name">${rec.agent_name}</div>
                    <span class="agent-category">${rec.category}</span>
                    <span class="trust-score">Trust: ${rec.trust_score}/100</span>
                    
                    <div class="confidence-bar">
                        <div class="confidence-fill" style="width: ${rec.confidence * 100}%"></div>
                    </div>
                    
                    <div class="reasoning">${rec.reasoning}</div>
                    
                    <div class="action-buttons">
                        <button class="btn btn-primary" onclick="viewAgent('${rec.agent_id}')">View Agent</button>
                        <button class="btn btn-secondary" onclick="provideFeedback('${rec.agent_id}', 'useful')">👍 Useful</button>
                        <button class="btn btn-secondary" onclick="provideFeedback('${rec.agent_id}', 'not-useful')">👎 Not Useful</button>
                    </div>
                `;
                container.appendChild(card);
            });
        }
        
        function displayUserProfile(profile) {
            const profileSection = document.getElementById('user-profile');
            const preferencesDisplay = document.getElementById('preferences-display');
            
            let html = '';
            Object.entries(profile.preferences).forEach(([category, score]) => {
                html += `
                    <div style="margin: 10px 0;">
                        <label>${category}:</label>
                        <div class="preference-bar">
                            <div class="preference-fill" style="width: ${score * 100}%"></div>
                        </div>
                    </div>
                `;
            });
            
            preferencesDisplay.innerHTML = html;
            profileSection.style.display = 'block';
        }
        
        function viewAgent(agentId) {
            alert(`Viewing agent: ${agentId}`);
            // Record click interaction
            recordInteraction(agentId, 'click');
        }
        
        function provideFeedback(agentId, feedback) {
            alert(`Feedback recorded: ${feedback} for ${agentId}`);
            // This would send feedback to the API
        }
        
        function recordInteraction(agentId, type) {
            // This would record the interaction for improving recommendations
            console.log(`Interaction: ${type} on ${agentId}`);
        }
        
        function getSampleRecommendations() {
            return [
                {
                    agent_id: "agent-1",
                    agent_name: "WebScrapePro",
                    category: "web-scraping",
                    confidence: 0.92,
                    reasoning: "Perfect match for your web automation needs",
                    trust_score: 87,
                    recommendation_type: "similar"
                },
                {
                    agent_id: "agent-2",
                    agent_name: "DataCleanBot",
                    category: "data-analysis", 
                    confidence: 0.78,
                    reasoning: "Complements your scraping workflow",
                    trust_score: 91,
                    recommendation_type: "complementary"
                },
                {
                    agent_id: "agent-3",
                    agent_name: "APIMonitor",
                    category: "monitoring",
                    confidence: 0.65,
                    reasoning: "Trending in monitoring - 15 recent recommendations",
                    trust_score: 83,
                    recommendation_type: "trending"
                }
            ];
        }
        
        function getSampleProfile() {
            return {
                preferences: {
                    "web-scraping": 0.8,
                    "data-analysis": 0.6,
                    "api-integration": 0.4,
                    "automation": 0.7
                }
            };
        }
    </script>
</body>
</html>
'''


if __name__ == "__main__":
    # Demo the sommelier system
    sommelier = AIAgentSommelier()
    
    # Create a sample user interaction
    user_id = "user123"
    
    # Simulate user interactions
    sommelier.update_user_profile(user_id, "agent-1", "click", rating=4.5, context="web scraping")
    sommelier.update_user_profile(user_id, "agent-2", "bookmark", rating=5.0, context="data cleaning")
    
    # Get recommendations
    recommendations = sommelier.get_recommendations(user_id, limit=5)
    
    print(f"🍷 Recommendations for {user_id}:")
    for i, rec in enumerate(recommendations, 1):
        print(f"  {i}. {rec.agent_name} ({rec.category})")
        print(f"     Confidence: {rec.confidence:.2f}")
        print(f"     Reasoning: {rec.reasoning}")
        print(f"     Type: {rec.recommendation_type}")
        print()