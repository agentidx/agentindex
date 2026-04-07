"""
LangChain Integration Package for AgentIndex
npm: @agentidx/langchain-retriever
pip: agentcrawl-langchain

Provides seamless integration with LangChain for agent discovery and retrieval.
Budget-optimized with local LLM routing where possible.
"""

from typing import List, Dict, Any, Optional
import requests
from langchain.schema import Document
from langchain.retrievers.base import BaseRetriever
from langchain.callbacks.manager import CallbackManagerForRetrieverRun
from langchain.pydantic_v1 import BaseModel, Field

class AgentIndexRetriever(BaseRetriever, BaseModel):
    """
    LangChain retriever that searches AgentIndex for relevant AI agents.
    
    Usage:
        retriever = AgentIndexRetriever(api_key="your_api_key")
        docs = retriever.get_relevant_documents("web scraping agents")
    """
    
    api_url: str = Field(default="https://api.agentcrawl.dev/v1/discover")
    api_key: Optional[str] = Field(default=None)
    max_results: int = Field(default=10)
    min_trust_score: float = Field(default=60.0)
    categories: Optional[List[str]] = Field(default=None)
    protocols: Optional[List[str]] = Field(default=None)
    
    class Config:
        """Configuration for the retriever."""
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self, 
        query: str, 
        *, 
        run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        """
        Retrieve relevant agents from AgentIndex.
        
        Args:
            query: Search query describing the needed functionality
            run_manager: LangChain callback manager
            
        Returns:
            List of Document objects containing agent information
        """
        
        # Prepare request payload
        payload = {
            "need": query,
            "max_results": self.max_results,
            "min_quality": self.min_trust_score,
        }
        
        if self.categories:
            payload["category"] = self.categories[0]  # API supports single category
            
        if self.protocols:
            payload["protocols"] = self.protocols
            
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            agents = data.get("results", [])
            
            # Convert agents to LangChain Documents
            documents = []
            for agent in agents:
                # Create rich document content
                content = self._format_agent_content(agent)
                
                # Create metadata
                metadata = {
                    "agent_id": agent.get("id"),
                    "name": agent.get("name"),
                    "category": agent.get("category"),
                    "trust_score": agent.get("trust_score"),
                    "source": agent.get("source"),
                    "protocols": agent.get("protocols", []),
                    "author": agent.get("author"),
                    "source_url": agent.get("source_url"),
                    "is_verified": agent.get("is_verified", False)
                }
                
                doc = Document(
                    page_content=content,
                    metadata=metadata
                )
                documents.append(doc)
                
            return documents
            
        except Exception as e:
            # Log error but don't break the chain
            print(f"AgentIndex retrieval error: {e}")
            return []
    
    def _format_agent_content(self, agent: Dict[str, Any]) -> str:
        """Format agent data into readable content for LangChain."""
        
        name = agent.get("name", "Unknown Agent")
        description = agent.get("description", "No description available")
        capabilities = agent.get("capabilities", [])
        trust_score = agent.get("trust_score", 0)
        trust_explanation = agent.get("trust_explanation", "")
        protocols = agent.get("protocols", [])
        invocation = agent.get("invocation", {})
        
        content_parts = [
            f"Agent: {name}",
            f"Description: {description}",
        ]
        
        if capabilities:
            content_parts.append(f"Capabilities: {', '.join(capabilities)}")
            
        if protocols:
            content_parts.append(f"Protocols: {', '.join(protocols)}")
            
        if trust_score:
            content_parts.append(f"Trust Score: {trust_score}/100")
            
        if trust_explanation:
            content_parts.append(f"Trust Details: {trust_explanation}")
            
        if invocation:
            if invocation.get("type") == "npm":
                content_parts.append(f"Installation: npm install {invocation.get('name', '')}")
            elif invocation.get("type") == "pip":
                content_parts.append(f"Installation: pip install {invocation.get('name', '')}")
            elif invocation.get("type") == "github":
                content_parts.append(f"GitHub: {invocation.get('url', '')}")
                
        return "\n".join(content_parts)

    @property
    def _retriever_type(self) -> str:
        """Return the retriever type."""
        return "agentindex"

class AgentRecommendationChain(BaseModel):
    """
    LangChain chain that recommends agents and provides implementation guidance.
    Uses local LLM when possible to optimize costs.
    """
    
    retriever: AgentIndexRetriever
    local_llm_available: bool = Field(default=False)
    
    def __init__(self, **data):
        super().__init__(**data)
        # Check if local LLM is available
        try:
            import requests
            response = requests.get("http://localhost:11434/api/version", timeout=2)
            self.local_llm_available = response.status_code == 200
        except:
            self.local_llm_available = False
    
    def recommend_agents(self, task_description: str) -> Dict[str, Any]:
        """
        Get agent recommendations with implementation guidance.
        
        Args:
            task_description: Description of the task needing agents
            
        Returns:
            Dictionary with recommended agents and guidance
        """
        
        # Retrieve relevant agents
        documents = self.retriever.get_relevant_documents(task_description)
        
        if not documents:
            return {
                "agents": [],
                "guidance": "No suitable agents found for your task.",
                "implementation": "Consider checking if your query is too specific or try broader terms."
            }
        
        # Format recommendations
        recommendations = []
        for doc in documents:
            metadata = doc.metadata
            recommendations.append({
                "name": metadata.get("name"),
                "trust_score": metadata.get("trust_score"),
                "category": metadata.get("category"),
                "description": doc.page_content,
                "protocols": metadata.get("protocols", []),
                "source_url": metadata.get("source_url")
            })
        
        # Generate implementation guidance
        guidance = self._generate_guidance(task_description, documents)
        
        return {
            "agents": recommendations,
            "guidance": guidance,
            "implementation": self._generate_implementation_code(recommendations)
        }
    
    def _generate_guidance(self, task: str, docs: List[Document]) -> str:
        """Generate guidance for using the recommended agents."""
        
        if self.local_llm_available:
            # Use local LLM for guidance generation (cost-optimized)
            return self._generate_guidance_local(task, docs)
        else:
            # Fallback to rule-based guidance
            return self._generate_guidance_rules(task, docs)
    
    def _generate_guidance_local(self, task: str, docs: List[Document]) -> str:
        """Generate guidance using local LLM."""
        try:
            import requests
            
            agent_summaries = []
            for doc in docs[:3]:  # Top 3 agents
                name = doc.metadata.get("name", "Unknown")
                trust = doc.metadata.get("trust_score", 0)
                agent_summaries.append(f"{name} (Trust: {trust}/100)")
            
            prompt = f"""Task: {task}

Recommended agents: {', '.join(agent_summaries)}

Provide brief guidance (2-3 sentences) on how to use these agents for the task."""

            payload = {
                "model": "llama3.2:3b",
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 200, "temperature": 0.1}
            }
            
            response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "").strip()
                
        except Exception:
            pass
        
        # Fallback to rules
        return self._generate_guidance_rules(task, docs)
    
    def _generate_guidance_rules(self, task: str, docs: List[Document]) -> str:
        """Generate rule-based guidance."""
        
        if not docs:
            return "No agents found for your task."
        
        top_agent = docs[0]
        name = top_agent.metadata.get("name", "the recommended agent")
        trust_score = top_agent.metadata.get("trust_score", 0)
        protocols = top_agent.metadata.get("protocols", [])
        
        guidance = f"The top recommendation is {name} with a trust score of {trust_score}/100. "
        
        if "mcp" in protocols:
            guidance += "This is an MCP (Model Context Protocol) agent, which can be used directly with Claude Desktop or other MCP-compatible clients. "
        elif "npm" in protocols:
            guidance += "This is an npm package that can be installed and integrated into your Node.js projects. "
        elif "pip" in protocols:
            guidance += "This is a Python package available via pip for integration into your Python projects. "
        
        if len(docs) > 1:
            guidance += f"Consider combining it with other recommended agents for a more comprehensive solution."
        
        return guidance
    
    def _generate_implementation_code(self, agents: List[Dict]) -> str:
        """Generate sample implementation code."""
        
        if not agents:
            return "# No agents to implement"
        
        top_agent = agents[0]
        protocols = top_agent.get("protocols", [])
        name = top_agent.get("name", "agent")
        
        if "mcp" in protocols:
            return f"""# MCP Integration Example
# Add to Claude Desktop config or use with MCP client

{{
  "mcpServers": {{
    "{name}": {{
      "command": "npx",
      "args": ["{name}"]
    }}
  }}
}}"""
        
        elif "npm" in protocols:
            return f"""# NPM Integration Example
npm install {name}

// Basic usage
const agent = require('{name}');
const result = await agent.process(inputData);"""
        
        elif "pip" in protocols:
            return f"""# Python Integration Example
pip install {name}

# Basic usage
from {name.replace('-', '_')} import Agent
agent = Agent()
result = agent.process(input_data)"""
        
        else:
            return f"""# Integration depends on specific agent protocol
# Check documentation: {top_agent.get('source_url', 'N/A')}
# Agent: {name}"""

# Export main classes for easy import
__all__ = ["AgentIndexRetriever", "AgentRecommendationChain"]

# Package metadata
__version__ = "1.0.0"
__description__ = "LangChain integration for AgentIndex - AI agent discovery and retrieval"
__author__ = "AgentIndex Team"
__email__ = "hello@agentcrawl.dev"