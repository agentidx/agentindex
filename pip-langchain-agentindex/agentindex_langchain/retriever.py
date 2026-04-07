"""
AgentIndex Retriever for LangChain
"""

import requests
from typing import List, Dict, Any, Optional
from langchain.schema import BaseRetriever, Document
from pydantic import Field

class AgentIndexRetriever(BaseRetriever):
    """AgentIndex retriever for LangChain integration."""
    
    api_key: Optional[str] = Field(default=None)
    base_url: str = Field(default="https://api.agentcrawl.dev/v1")
    default_framework: str = Field(default="langchain")
    min_trust_score: int = Field(default=70)
    max_results: int = Field(default=20)
    
    class Config:
        arbitrary_types_allowed = True
    
    def get_relevant_documents(self, query: str) -> List[Document]:
        """Get relevant agent documents for a query."""
        try:
            agents = self.search_agents({
                "query": query,
                "framework": self.default_framework,
                "min_trust_score": self.min_trust_score,
                "max_results": self.max_results
            })
            
            documents = []
            for agent in agents:
                content = f"{agent['name']}: {agent['description']}\n\n"
                content += f"Trust Score: {agent['trust_score']}/100\n"
                content += f"Repository: {agent['repository_url']}\n"
                
                if agent.get('usage_examples'):
                    content += f"\nUsage Examples:\n{agent['usage_examples']}"
                
                doc = Document(
                    page_content=content,
                    metadata={
                        "agent_id": agent["id"],
                        "name": agent["name"],
                        "trust_score": agent["trust_score"],
                        "framework": agent["framework"],
                        "repository_url": agent["repository_url"]
                    }
                )
                documents.append(doc)
            
            return documents
            
        except Exception as e:
            print(f"AgentIndex search failed: {e}")
            return []
    
    def search_agents(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for agents using AgentIndex API."""
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            
            response = requests.post(
                f"{self.base_url}/search",
                json={
                    "query": params["query"],
                    "filters": {
                        "framework": params.get("framework", self.default_framework),
                        "min_trust_score": params.get("min_trust_score", self.min_trust_score),
                        "max_results": params.get("max_results", self.max_results)
                    }
                },
                headers=headers,
                timeout=10
            )
            
            response.raise_for_status()
            return response.json().get("agents", [])
            
        except requests.RequestException as e:
            print(f"API request failed: {e}")
            return []
        except Exception as e:
            print(f"Search failed: {e}")
            return []
    
    def get_agent_details(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information for a specific agent."""
        try:
            headers = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
                
            response = requests.get(
                f"{self.base_url}/agents/{agent_id}",
                headers=headers,
                timeout=10
            )
            
            response.raise_for_status()
            return response.json().get("agent")
            
        except Exception as e:
            print(f"Failed to get agent details: {e}")
            return None
