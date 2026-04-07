"""
CrewAI integration for AgentIndex
Allows CrewAI agents to discover and recruit specialized agents dynamically
"""

import asyncio
import aiohttp
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class AgentCapability(Enum):
    """Common agent capability categories"""
    WEB_SCRAPING = "web-scraping"
    DATA_ANALYSIS = "data-analysis" 
    CODE_GENERATION = "code-generation"
    DATABASE = "database"
    API_INTEGRATION = "api-integration"
    ML_INFERENCE = "ml-inference"
    FILE_PROCESSING = "file-processing"
    COMMUNICATION = "communication"


@dataclass
class DiscoveredAgent:
    """Represents an agent discovered through AgentIndex"""
    id: str
    name: str
    description: str
    url: str
    platform: str
    trust_score: Optional[float]
    relevance: float
    capabilities: List[str]
    metadata: Dict[str, Any]
    
    def to_crewai_agent_config(self) -> Dict[str, Any]:
        """Convert to CrewAI agent configuration format"""
        return {
            "role": self.name,
            "goal": f"Specialized in {', '.join(self.capabilities)}",
            "backstory": self.description,
            "tools": [self.url] if self.url else [],
            "max_iter": 5,
            "memory": True,
            "verbose": True,
            "metadata": {
                **self.metadata,
                "agentindex_id": self.id,
                "trust_score": self.trust_score,
                "platform": self.platform
            }
        }


class AgentDiscoveryService:
    """Service for discovering agents via AgentIndex API"""
    
    def __init__(self, base_url: str = "https://api.agentcrawl.dev"):
        self.base_url = base_url
    
    async def discover_agents(
        self, 
        need: str, 
        limit: int = 5,
        min_trust_score: float = 60.0,
        category: Optional[str] = None
    ) -> List[DiscoveredAgent]:
        """Discover agents matching the specified need"""
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "need": need,
                    "limit": limit * 2  # Get extra for filtering
                }
                if category:
                    payload["category"] = category
                
                async with session.post(
                    f"{self.base_url}/v1/discover",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    
                    if response.status != 200:
                        raise Exception(f"Discovery API failed: {response.status}")
                    
                    data = await response.json()
                    agents = []
                    
                    for result in data.get("results", []):
                        # Filter by trust score if available
                        trust_score = result.get("trust_score")
                        if trust_score and trust_score < min_trust_score:
                            continue
                        
                        # Extract capabilities from description and category
                        capabilities = self._extract_capabilities(
                            result.get("description", ""),
                            result.get("category", "")
                        )
                        
                        agent = DiscoveredAgent(
                            id=result.get("id", ""),
                            name=result.get("name", "Unknown Agent"),
                            description=result.get("description", ""),
                            url=result.get("url", ""),
                            platform=result.get("source", "unknown"),
                            trust_score=trust_score,
                            relevance=result.get("relevance", 0.0),
                            capabilities=capabilities,
                            metadata={
                                "stars": result.get("stars"),
                                "downloads": result.get("downloads"), 
                                "language": result.get("language"),
                                "category": result.get("category"),
                                "trust_explanation": result.get("trust_explanation")
                            }
                        )
                        
                        agents.append(agent)
                        
                        if len(agents) >= limit:
                            break
                    
                    return agents
                    
        except Exception as e:
            print(f"Agent discovery failed: {e}")
            return []
    
    def _extract_capabilities(self, description: str, category: str) -> List[str]:
        """Extract capabilities from description and category"""
        capabilities = []
        desc_lower = description.lower()
        cat_lower = category.lower() if category else ""
        
        # Map keywords to capabilities
        capability_keywords = {
            AgentCapability.WEB_SCRAPING: ["scraping", "crawling", "web data", "html", "selenium", "playwright"],
            AgentCapability.DATA_ANALYSIS: ["analysis", "pandas", "numpy", "statistics", "visualization"],
            AgentCapability.CODE_GENERATION: ["code", "programming", "generation", "compiler", "syntax"],
            AgentCapability.DATABASE: ["database", "sql", "postgres", "mysql", "mongodb", "orm"],
            AgentCapability.API_INTEGRATION: ["api", "rest", "http", "integration", "webhook"],
            AgentCapability.ML_INFERENCE: ["ml", "machine learning", "model", "inference", "tensorflow", "pytorch"],
            AgentCapability.FILE_PROCESSING: ["file", "document", "pdf", "excel", "csv", "processing"],
            AgentCapability.COMMUNICATION: ["email", "slack", "discord", "notification", "messaging"]
        }
        
        for capability, keywords in capability_keywords.items():
            if any(keyword in desc_lower or keyword in cat_lower for keyword in keywords):
                capabilities.append(capability.value)
        
        # Default capability if none found
        if not capabilities:
            capabilities.append("general-purpose")
        
        return capabilities


class CrewAIAgentRecruitment:
    """Handles dynamic agent recruitment for CrewAI crews"""
    
    def __init__(self):
        self.discovery_service = AgentDiscoveryService()
        self.recruited_agents = {}
    
    async def recruit_specialist(
        self, 
        task_description: str, 
        capability: Optional[AgentCapability] = None
    ) -> Optional[DiscoveredAgent]:
        """Recruit a single specialist agent for a specific task"""
        
        category = capability.value if capability else None
        agents = await self.discovery_service.discover_agents(
            need=task_description,
            limit=1,
            min_trust_score=70.0,
            category=category
        )
        
        if agents:
            agent = agents[0]
            self.recruited_agents[task_description] = agent
            return agent
        
        return None
    
    async def build_specialized_crew(
        self, 
        project_description: str,
        required_capabilities: List[AgentCapability],
        crew_size: int = 3
    ) -> List[DiscoveredAgent]:
        """Build a crew with specific capabilities"""
        
        crew = []
        
        for capability in required_capabilities[:crew_size]:
            agent = await self.recruit_specialist(
                f"{project_description} - {capability.value}",
                capability
            )
            if agent:
                crew.append(agent)
        
        # Fill remaining slots with general agents if needed
        if len(crew) < crew_size:
            general_agents = await self.discovery_service.discover_agents(
                need=project_description,
                limit=crew_size - len(crew)
            )
            crew.extend(general_agents)
        
        return crew
    
    def get_crewai_configs(self, agents: List[DiscoveredAgent]) -> List[Dict[str, Any]]:
        """Convert discovered agents to CrewAI agent configurations"""
        return [agent.to_crewai_agent_config() for agent in agents]


# Example usage and workflow
class AutoCrewBuilder:
    """Automatically builds CrewAI crews based on task requirements"""
    
    def __init__(self):
        self.recruitment = CrewAIAgentRecruitment()
    
    async def create_data_pipeline_crew(self) -> List[Dict[str, Any]]:
        """Create a crew specialized for data pipeline tasks"""
        
        required_capabilities = [
            AgentCapability.WEB_SCRAPING,
            AgentCapability.DATA_ANALYSIS, 
            AgentCapability.DATABASE
        ]
        
        agents = await self.recruitment.build_specialized_crew(
            "Build automated data pipeline",
            required_capabilities,
            crew_size=3
        )
        
        return self.recruitment.get_crewai_configs(agents)
    
    async def create_web_automation_crew(self) -> List[Dict[str, Any]]:
        """Create a crew for web automation tasks"""
        
        agents = await self.recruitment.build_specialized_crew(
            "Automate web interactions and data extraction",
            [AgentCapability.WEB_SCRAPING, AgentCapability.API_INTEGRATION],
            crew_size=2
        )
        
        return self.recruitment.get_crewai_configs(agents)


if __name__ == "__main__":
    # Example usage
    async def demo_crew_recruitment():
        builder = AutoCrewBuilder()
        
        print("🔍 Recruiting data pipeline crew...")
        data_crew = await builder.create_data_pipeline_crew()
        
        print(f"\n📊 Recruited {len(data_crew)} agents for data pipeline:")
        for i, agent_config in enumerate(data_crew, 1):
            print(f"  {i}. {agent_config['role']}")
            print(f"     Platform: {agent_config['metadata']['platform']}")
            print(f"     Trust: {agent_config['metadata']['trust_score']}/100")
        
        print("\n🌐 Recruiting web automation crew...")
        web_crew = await builder.create_web_automation_crew()
        
        print(f"\n🤖 Recruited {len(web_crew)} agents for web automation:")
        for i, agent_config in enumerate(web_crew, 1):
            print(f"  {i}. {agent_config['role']}")
            print(f"     Backstory: {agent_config['backstory'][:100]}...")
    
    asyncio.run(demo_crew_recruitment())