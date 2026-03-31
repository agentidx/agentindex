"""
Framework Integration Endpoints
API endpoints for LangChain, CrewAI, and other framework integrations
"""

import logging
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import os

logger = logging.getLogger("agentindex.integrations")

app = FastAPI(
    title="AgentIndex Integrations API",
    description="Framework integration endpoints for LangChain, CrewAI, etc.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import integration classes
from agentindex.integrations.langchain_retriever import AgentIndexRetriever
from agentindex.integrations.crewai_discovery import AgentDiscoveryService, CrewAIAgentRecruitment


# --- Models ---

class LangChainSearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 10
    category: Optional[str] = None

class LangChainDocument(BaseModel):
    page_content: str
    metadata: dict

class LangChainSearchResponse(BaseModel):
    documents: List[LangChainDocument]
    total: int
    query_time_ms: int

class CrewAIDiscoveryRequest(BaseModel):
    need: str
    limit: Optional[int] = 3
    min_trust_score: Optional[float] = 60.0
    category: Optional[str] = None

class CrewAIAgent(BaseModel):
    id: str
    name: str
    description: str
    url: str
    platform: str
    trust_score: Optional[float]
    relevance: float
    capabilities: List[str]
    crew_config: dict

class CrewAIDiscoveryResponse(BaseModel):
    agents: List[CrewAIAgent]
    total: int
    query_time_ms: int

class CodeGenerationRequest(BaseModel):
    framework: str
    language: str
    agent_id: Optional[str] = None
    custom_requirements: Optional[str] = None

class CodeGenerationResponse(BaseModel):
    framework: str
    language: str
    code: str
    dependencies: List[str]
    instructions: str
    example_usage: str
    generated_at: str


# --- LangChain Integration ---

@app.post("/v1/langchain/search", response_model=LangChainSearchResponse)
async def langchain_search(request: LangChainSearchRequest):
    """
    LangChain-compatible search endpoint
    Returns Document objects ready for LangChain chains
    """
    start_time = datetime.utcnow()
    
    try:
        # Initialize retriever
        retriever = AgentIndexRetriever(
            api_url="http://localhost:8100",  # Internal API call
            limit=request.limit
        )
        
        # Mock CallbackManagerForRetrieverRun for API use
        class MockCallbackManager:
            def on_retriever_error(self, error):
                logger.error(f"Retriever error: {error}")
        
        # Get documents
        documents = await retriever._aget_relevant_documents(
            request.query, 
            run_manager=MockCallbackManager()
        )
        
        # Convert to response format
        doc_responses = []
        for doc in documents:
            doc_responses.append(LangChainDocument(
                page_content=doc.page_content,
                metadata=doc.metadata
            ))
        
        query_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return LangChainSearchResponse(
            documents=doc_responses,
            total=len(doc_responses),
            query_time_ms=query_time
        )
        
    except Exception as e:
        logger.error(f"LangChain search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- CrewAI Integration ---

@app.post("/v1/crewai/discover", response_model=CrewAIDiscoveryResponse)
async def crewai_discover_agents(request: CrewAIDiscoveryRequest):
    """
    CrewAI agent discovery endpoint
    Returns agents formatted for CrewAI crew building
    """
    start_time = datetime.utcnow()
    
    try:
        # Initialize discovery service
        recruitment = CrewAIAgentRecruitment()
        
        # Discover agents
        discovered_agents = await recruitment.discovery_service.discover_agents(
            need=request.need,
            limit=request.limit,
            min_trust_score=request.min_trust_score,
            category=request.category
        )
        
        # Format for response
        crew_agents = []
        for agent in discovered_agents:
            crew_config = agent.to_crewai_agent_config()
            
            crew_agents.append(CrewAIAgent(
                id=agent.id,
                name=agent.name,
                description=agent.description,
                url=agent.url,
                platform=agent.platform,
                trust_score=agent.trust_score,
                relevance=agent.relevance,
                capabilities=agent.capabilities,
                crew_config=crew_config
            ))
        
        query_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return CrewAIDiscoveryResponse(
            agents=crew_agents,
            total=len(crew_agents),
            query_time_ms=query_time
        )
        
    except Exception as e:
        logger.error(f"CrewAI discovery failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/crewai/build-crew")
async def build_specialized_crew(request: CrewAIDiscoveryRequest):
    """
    Build a complete CrewAI crew configuration
    Returns ready-to-use crew setup
    """
    start_time = datetime.utcnow()
    
    try:
        recruitment = CrewAIAgentRecruitment()
        
        # Build crew 
        discovered_agents = await recruitment.build_specialized_crew(
            request.need,
            [],  # Let it auto-determine capabilities
            3    # Default crew size
        )
        
        # Extract crew configuration
        crew_config = {
            "agents": [],
            "tasks": [],
            "crew_settings": {
                "verbose": True,
                "memory": True
            }
        }
        
        # Add agent configurations
        for agent in discovered_agents:
            agent_config = agent.to_crewai_agent_config()
            crew_config["agents"].append(agent_config)
        
        # Add default task configurations  
        crew_config["tasks"].append({
            "description": f"Complete the task: {request.need}",
            "expected_output": "A comprehensive solution addressing the specified need",
            "agent_role": discovered_agents[0].name if discovered_agents else "Lead Agent"
        })
        
        query_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return {
            "crew_config": crew_config,
            "agent_count": len(crew_config["agents"]),
            "task_count": len(crew_config["tasks"]),
            "query_time_ms": query_time,
            "usage_example": '''
from crewai import Agent, Task, Crew

# Use the returned crew_config to create your crew
agents = [Agent(**agent_config) for agent_config in crew_config["agents"]]
tasks = [Task(**task_config) for task_config in crew_config["tasks"]]

crew = Crew(agents=agents, tasks=tasks, verbose=True)
result = crew.kickoff()
'''
        }
        
    except Exception as e:
        logger.error(f"Crew building failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Code Generation ---

@app.post("/v1/generate-integration", response_model=CodeGenerationResponse)
async def generate_integration_code(request: CodeGenerationRequest):
    """
    Generate integration code for various frameworks
    """
    try:
        from agentindex.experiments.integration_generator import CodeIntegrationGenerator
        
        generator = CodeIntegrationGenerator()
        
        integration = await generator.generate_integration(
            framework=request.framework,
            language=request.language,
            agent_id=request.agent_id,
            custom_requirements=request.custom_requirements
        )
        
        return CodeGenerationResponse(**integration)
        
    except Exception as e:
        logger.error(f"Code generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/integrations/available")
async def get_available_integrations():
    """
    Get list of available framework integrations
    """
    try:
        from agentindex.experiments.integration_generator import CodeIntegrationGenerator
        
        generator = CodeIntegrationGenerator()
        available = generator.get_available_integrations()
        
        return {
            "integrations": available,
            "total": len(available),
            "frameworks": list(set(i["framework"] for i in available)),
            "languages": list(set(i["language"] for i in available))
        }
        
    except Exception as e:
        logger.error(f"Failed to get available integrations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Health & Status ---

@app.get("/v1/health")
async def health_check():
    """Health check for integrations API"""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "langchain": "available",
            "crewai": "available", 
            "code_generator": "available"
        }
    }


@app.get("/")
async def root():
    """API information"""
    return {
        "service": "AgentIndex Integrations API",
        "version": "1.0.0",
        "endpoints": {
            "langchain": "/v1/langchain/search",
            "crewai": "/v1/crewai/discover",
            "code_generation": "/v1/generate-integration",
            "available": "/v1/integrations/available"
        },
        "documentation": "/docs",
        "powered_by": "AgentIndex"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8201)