"""
Experiments API Server
Unified API server for all experimental features
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json

# Import experimental modules
from agentindex.experiments.battle_royale import BattleRoyaleSystem, Agent as BRAgent
from agentindex.experiments.discovery_dashboard import DiscoveryDashboard, QueryAnalytics
from agentindex.experiments.ai_sommelier import AIAgentSommelier, UserProfile
from agentindex.experiments.integration_generator import CodeIntegrationGenerator


app = FastAPI(
    title="AgentIndex Experiments API",
    description="Experimental features and innovations",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize experiment systems
battle_royale = BattleRoyaleSystem()
dashboard = DiscoveryDashboard()
sommelier = AIAgentSommelier()
code_generator = CodeIntegrationGenerator()

# Seed battle royale with sample data
battle_royale.seed_with_sample_agents()

# Models
class BattleVoteRequest(BaseModel):
    battle_id: str
    agent_id: str
    voter_ip: Optional[str] = None

class UserInteractionRequest(BaseModel):
    user_id: str
    agent_id: str
    interaction_type: str
    rating: Optional[float] = None
    context: Optional[str] = None

class RecommendationRequest(BaseModel):
    user_id: str
    limit: int = 10
    include_explored: bool = False

class QueryLogRequest(BaseModel):
    query: str
    results_count: int
    response_time_ms: int
    category: Optional[str] = None
    protocols: List[str] = []
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    results: List[Dict] = []


# Battle Royale Endpoints
@app.get("/experiments/battle-royale", response_class=HTMLResponse)
async def battle_royale_interface():
    """Battle Royale web interface"""
    from agentindex.experiments.battle_royale import BATTLE_ROYALE_HTML
    
    stats = battle_royale.get_stats()
    leaderboard = battle_royale.get_leaderboard(10)
    active_battles = battle_royale.get_active_battles()
    
    # Simple template substitution
    html = BATTLE_ROYALE_HTML.replace("{{total_agents}}", str(stats["total_agents"]))
    html = html.replace("{{active_battles}}", str(stats["active_battles"]))
    html = html.replace("{{total_votes}}", str(stats["total_votes"]))
    html = html.replace("{{completed_battles}}", str(stats["completed_battles"]))
    
    return html

@app.post("/experiments/battle-royale/create")
async def create_battle(category: Optional[str] = None, duration_hours: int = 24):
    """Create a new battle"""
    try:
        battle = battle_royale.create_battle(category, duration_hours)
        return {"success": True, "battle": battle.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/experiments/battle-royale/vote")
async def vote_in_battle(vote_request: BattleVoteRequest):
    """Vote in a battle"""
    try:
        battle_royale.vote(vote_request.battle_id, vote_request.agent_id, vote_request.voter_ip)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/experiments/battle-royale/battles/active")
async def get_active_battles():
    """Get active battles"""
    battles = battle_royale.get_active_battles()
    return {"battles": [battle.to_dict() for battle in battles]}

@app.get("/experiments/battle-royale/battles/completed")
async def get_completed_battles(limit: int = 20):
    """Get completed battles"""
    battles = battle_royale.get_completed_battles(limit)
    return {"battles": [battle.to_dict() for battle in battles]}

@app.get("/experiments/battle-royale/leaderboard")
async def get_battle_leaderboard(limit: int = 20):
    """Get battle leaderboard"""
    leaderboard = battle_royale.get_leaderboard(limit)
    return {"leaderboard": leaderboard}

@app.get("/experiments/battle-royale/stats")
async def get_battle_stats():
    """Get battle statistics"""
    return battle_royale.get_stats()


# Discovery Dashboard Endpoints
@app.get("/experiments/dashboard", response_class=HTMLResponse)
async def dashboard_interface():
    """Discovery Dashboard web interface"""
    from agentindex.experiments.discovery_dashboard import DASHBOARD_HTML
    
    dashboard_data = dashboard.get_dashboard_data(24)
    summary = dashboard_data["summary"]
    
    # Simple template substitution
    html = DASHBOARD_HTML.replace("{{total_queries}}", str(summary["total_queries"]))
    html = html.replace("{{unique_agents}}", str(summary["unique_agents_searched"]))
    html = html.replace("{{avg_response}}", str(summary["avg_results_per_query"]))
    html = html.replace("{{queries_per_hour}}", str(summary["queries_per_hour"]))
    html = html.replace("{{last_updated}}", dashboard_data["last_updated"])
    
    return html

@app.post("/experiments/dashboard/log")
async def log_query_analytics(log_request: QueryLogRequest):
    """Log a query for analytics"""
    analytics = QueryAnalytics(
        query=log_request.query,
        timestamp=datetime.utcnow(),
        results_count=log_request.results_count,
        response_time_ms=log_request.response_time_ms,
        category=log_request.category,
        protocols=log_request.protocols,
        user_agent=log_request.user_agent,
        ip_address=log_request.ip_address
    )
    
    dashboard.log_query(analytics, log_request.results)
    return {"success": True}

@app.get("/experiments/dashboard/data")
async def get_dashboard_data(hours: int = 24):
    """Get dashboard data"""
    return dashboard.get_dashboard_data(hours)

@app.get("/experiments/dashboard/trending/queries")
async def get_trending_queries(hours: int = 24, limit: int = 20):
    """Get trending queries"""
    return {"queries": dashboard.get_trending_queries(hours, limit)}

@app.get("/experiments/dashboard/trending/agents")
async def get_trending_agents(hours: int = 24, limit: int = 15):
    """Get trending agents"""
    trending = dashboard.get_trending_agents(hours, limit)
    return {"agents": [agent.to_dict() for agent in trending]}

@app.get("/experiments/dashboard/insights")
async def get_dashboard_insights(hours: int = 24):
    """Get AI-generated insights"""
    insights = dashboard.generate_insights(hours)
    return {"insights": insights}


# AI Sommelier Endpoints
@app.get("/experiments/sommelier", response_class=HTMLResponse)
async def sommelier_interface():
    """AI Sommelier web interface"""
    from agentindex.experiments.ai_sommelier import SOMMELIER_HTML
    return SOMMELIER_HTML

@app.post("/experiments/sommelier/interaction")
async def log_user_interaction(interaction: UserInteractionRequest):
    """Log user interaction"""
    sommelier.update_user_profile(
        interaction.user_id,
        interaction.agent_id,
        interaction.interaction_type,
        interaction.rating,
        interaction.context
    )
    return {"success": True}

@app.post("/experiments/sommelier/recommendations")
async def get_personalized_recommendations(req: RecommendationRequest):
    """Get personalized recommendations"""
    recommendations = sommelier.get_recommendations(
        req.user_id, 
        req.limit, 
        req.include_explored
    )
    
    return {
        "user_id": req.user_id,
        "recommendations": [rec.to_dict() for rec in recommendations]
    }

@app.get("/experiments/sommelier/profile/{user_id}")
async def get_user_profile(user_id: str):
    """Get user preference profile"""
    profile = sommelier.get_user_profile(user_id)
    
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")
    
    return profile.to_dict()

@app.post("/experiments/sommelier/feedback")
async def log_recommendation_feedback(
    user_id: str,
    agent_id: str, 
    was_clicked: bool = False,
    was_useful: Optional[bool] = None
):
    """Log feedback on recommendations"""
    sommelier.log_recommendation_feedback(user_id, agent_id, was_clicked, was_useful)
    return {"success": True}


# Code Integration Generator Endpoints
@app.post("/experiments/integrations/generate")
async def generate_integration_code(
    framework: str,
    language: str,
    agent_id: Optional[str] = None,
    custom_requirements: Optional[str] = None
):
    """Generate integration code"""
    try:
        integration = await code_generator.generate_integration(
            framework, language, agent_id, custom_requirements
        )
        return integration
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/experiments/integrations/available")
async def get_available_integrations():
    """Get available integrations"""
    integrations = code_generator.get_available_integrations()
    return {
        "integrations": integrations,
        "frameworks": list(set(i["framework"] for i in integrations)),
        "languages": list(set(i["language"] for i in integrations))
    }


# General Experiment Endpoints
@app.get("/experiments")
async def list_experiments():
    """List all available experiments"""
    return {
        "experiments": [
            {
                "id": "battle-royale",
                "name": "🥊 Agent Battle Royale",
                "description": "Community voting system for agent comparisons",
                "url": "/experiments/battle-royale",
                "api_endpoints": [
                    "/experiments/battle-royale/create",
                    "/experiments/battle-royale/vote",
                    "/experiments/battle-royale/leaderboard"
                ]
            },
            {
                "id": "dashboard",
                "name": "📊 Discovery Dashboard",
                "description": "Real-time analytics and trending insights",
                "url": "/experiments/dashboard",
                "api_endpoints": [
                    "/experiments/dashboard/data",
                    "/experiments/dashboard/trending/queries",
                    "/experiments/dashboard/insights"
                ]
            },
            {
                "id": "sommelier",
                "name": "🍷 AI Agent Sommelier",
                "description": "Personalized agent recommendations",
                "url": "/experiments/sommelier",
                "api_endpoints": [
                    "/experiments/sommelier/recommendations",
                    "/experiments/sommelier/interaction",
                    "/experiments/sommelier/profile"
                ]
            },
            {
                "id": "integration-generator",
                "name": "⚡ One-Click Integration Generator",
                "description": "Auto-generates framework integration code",
                "api_endpoints": [
                    "/experiments/integrations/generate",
                    "/experiments/integrations/available"
                ]
            }
        ],
        "total": 4,
        "description": "Google 20%-time inspired experimental features"
    }

@app.get("/experiments/stats")
async def get_experiment_stats():
    """Get statistics across all experiments"""
    
    # Battle Royale stats
    br_stats = battle_royale.get_stats()
    
    # Dashboard stats
    dashboard_data = dashboard.get_dashboard_data(24)
    
    # Sommelier stats (would need to implement in sommelier class)
    # For now, just return placeholder
    
    # Integration generator stats
    available_integrations = code_generator.get_available_integrations()
    
    return {
        "battle_royale": {
            "total_agents": br_stats["total_agents"],
            "active_battles": br_stats["active_battles"],
            "total_votes": br_stats["total_votes"]
        },
        "dashboard": {
            "total_queries_24h": dashboard_data["summary"]["total_queries"],
            "unique_agents_searched": dashboard_data["summary"]["unique_agents_searched"],
            "avg_response_time": dashboard_data["response_times"].get("avg", 0)
        },
        "sommelier": {
            "total_users": "N/A",  # Would implement this
            "recommendations_generated": "N/A",
            "avg_satisfaction": "N/A"
        },
        "integration_generator": {
            "available_frameworks": len(set(i["framework"] for i in available_integrations)),
            "available_languages": len(set(i["language"] for i in available_integrations)),
            "total_integrations": len(available_integrations)
        },
        "last_updated": datetime.utcnow().isoformat()
    }

@app.get("/experiments/health")
async def experiments_health():
    """Health check for all experiments"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "experiments": {
            "battle_royale": "operational",
            "dashboard": "operational", 
            "sommelier": "operational",
            "integration_generator": "operational"
        }
    }

@app.get("/")
async def root():
    """Experiments API root"""
    return {
        "service": "AgentIndex Experiments API",
        "version": "1.0.0",
        "description": "Google 20%-time inspired experimental features",
        "experiments_available": 4,
        "endpoints": {
            "list_experiments": "/experiments",
            "battle_royale": "/experiments/battle-royale",
            "dashboard": "/experiments/dashboard", 
            "sommelier": "/experiments/sommelier",
            "integration_generator": "/experiments/integrations"
        },
        "documentation": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8302)