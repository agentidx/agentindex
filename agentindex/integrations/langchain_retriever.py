"""
LangChain integration for AgentIndex
Allows LangChain agents to discover tools via semantic search
"""

import asyncio
from typing import List, Dict, Any, Optional
import aiohttp
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from pydantic import Field


class AgentIndexRetriever(BaseRetriever):
    """LangChain retriever for AgentIndex semantic tool discovery"""
    
    base_url: str = Field(default="https://api.agentcrawl.dev")
    limit: int = Field(default=10)
    category: Optional[str] = Field(default=None)
    
    class Config:
        arbitrary_types_allowed = True
    
    async def _aget_relevant_documents(
        self, 
        query: str, 
        *, 
        run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        """Async implementation of document retrieval"""
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "need": query,
                    "limit": self.limit
                }
                if self.category:
                    payload["category"] = self.category
                
                async with session.post(
                    f"{self.base_url}/v1/discover",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status != 200:
                        raise Exception(f"API request failed with status {response.status}")
                    
                    data = await response.json()
                    
                    documents = []
                    for result in data.get("results", []):
                        # Create LangChain Document with agent metadata
                        content = self._format_agent_content(result)
                        
                        metadata = {
                            "source": "agentindex",
                            "agent_id": result.get("id"),
                            "name": result.get("name"),
                            "url": result.get("url"),
                            "category": result.get("category"),
                            "relevance": result.get("relevance", 0),
                            "trust_score": result.get("trust_score"),
                            "platform": result.get("source")
                        }
                        
                        # Add platform-specific metadata
                        if result.get("stars"):
                            metadata["stars"] = result["stars"]
                        if result.get("downloads"):
                            metadata["downloads"] = result["downloads"]
                        if result.get("language"):
                            metadata["language"] = result["language"]
                        
                        doc = Document(
                            page_content=content,
                            metadata=metadata
                        )
                        documents.append(doc)
                    
                    return documents
                    
        except Exception as e:
            run_manager.on_retriever_error(e)
            return []
    
    def _get_relevant_documents(
        self, 
        query: str, 
        *, 
        run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        """Sync wrapper for async implementation"""
        return asyncio.run(self._aget_relevant_documents(query, run_manager=run_manager))
    
    def _format_agent_content(self, result: Dict[str, Any]) -> str:
        """Format agent data as readable content for LLM"""
        
        content_parts = [
            f"**{result.get('name', 'Unknown')}**",
            f"Description: {result.get('description', 'No description')}",
            f"URL: {result.get('url', '')}",
            f"Platform: {result.get('source', 'Unknown')}",
        ]
        
        # Add trust score if available
        if result.get("trust_score"):
            trust_explanation = result.get("trust_explanation", "")
            content_parts.append(f"Trust Score: {result['trust_score']}/100 - {trust_explanation}")
        
        # Add platform-specific info
        if result.get("stars"):
            content_parts.append(f"GitHub Stars: {result['stars']:,}")
        
        if result.get("downloads"):
            content_parts.append(f"Downloads: {result['downloads']:,}")
            
        if result.get("language"):
            content_parts.append(f"Language: {result['language']}")
            
        # Add category and relevance
        if result.get("category"):
            content_parts.append(f"Category: {result['category']}")
            
        content_parts.append(f"Relevance: {result.get('relevance', 0):.2f}")
        
        return "\n".join(content_parts)


# Example usage and factory functions
def create_agent_index_retriever(
    limit: int = 10, 
    category: Optional[str] = None,
    base_url: str = "https://api.agentcrawl.dev"
) -> AgentIndexRetriever:
    """Factory function to create AgentIndex retriever"""
    return AgentIndexRetriever(
        limit=limit,
        category=category, 
        base_url=base_url
    )


# LangChain Graph integration example
class AgentDiscoveryChain:
    """Complete LangChain chain for agent discovery and tool usage"""
    
    def __init__(self, llm=None):
        self.retriever = create_agent_index_retriever(limit=5)
        self.llm = llm
    
    async def discover_and_recommend(self, need: str) -> List[Dict[str, Any]]:
        """Discover agents and provide LLM recommendations"""
        
        # Get relevant agents
        documents = await self.retriever._aget_relevant_documents(
            need, 
            run_manager=None  # Simplified for example
        )
        
        recommendations = []
        for doc in documents:
            recommendation = {
                "name": doc.metadata["name"],
                "description": doc.page_content,
                "url": doc.metadata["url"],
                "trust_score": doc.metadata.get("trust_score"),
                "platform": doc.metadata["platform"],
                "relevance": doc.metadata["relevance"]
            }
            recommendations.append(recommendation)
        
        return recommendations


if __name__ == "__main__":
    # Example usage
    async def test_retriever():
        retriever = create_agent_index_retriever(limit=3)
        
        # Test query
        docs = await retriever._aget_relevant_documents(
            "web scraping tool",
            run_manager=None
        )
        
        print(f"Found {len(docs)} relevant agents:")
        for doc in docs:
            print(f"\n--- {doc.metadata['name']} ---")
            print(doc.page_content)
            print(f"Trust Score: {doc.metadata.get('trust_score', 'N/A')}")
    
    asyncio.run(test_retriever())