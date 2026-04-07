"""
One-Click Integration Generator - Experimental Feature
Automatically generates integration code for popular frameworks
"""

import asyncio
import asyncpg
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass
import json


@dataclass
class IntegrationTemplate:
    """Template for generating integration code"""
    framework: str
    language: str
    template: str
    dependencies: List[str]
    instructions: str
    example_usage: str


class CodeIntegrationGenerator:
    """Generates integration code for various frameworks"""
    
    def __init__(self, db_url: str = "postgresql://anstudio@localhost/agentindex"):
        self.db_url = db_url
        self.templates = self._load_integration_templates()
    
    def _load_integration_templates(self) -> Dict[str, IntegrationTemplate]:
        """Load predefined integration templates"""
        
        return {
            "langchain-python": IntegrationTemplate(
                framework="LangChain",
                language="Python",
                template="""
# Auto-generated AgentIndex integration for LangChain
from typing import List
import asyncio
import aiohttp
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun

class AgentIndexRetriever(BaseRetriever):
    '''LangChain retriever for AgentIndex agent discovery'''
    
    def __init__(self, api_url: str = "https://api.agentcrawl.dev", limit: int = 5):
        super().__init__()
        self.api_url = api_url
        self.limit = limit
    
    async def _aget_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        '''Async retrieve relevant agents'''
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_url}/v1/discover",
                json={"need": query, "limit": self.limit}
            ) as response:
                data = await response.json()
                
                documents = []
                for agent in data.get("results", []):
                    doc = Document(
                        page_content=f"**{agent['name']}**: {agent['description']}\\n"
                                   f"URL: {agent['url']}\\n"
                                   f"Trust Score: {agent.get('trust_score', 'N/A')}/100",
                        metadata={
                            "agent_name": agent["name"],
                            "agent_url": agent["url"],
                            "trust_score": agent.get("trust_score"),
                            "relevance": agent.get("relevance"),
                            "source": "agentindex"
                        }
                    )
                    documents.append(doc)
                
                return documents
    
    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        '''Sync wrapper for async retrieve'''
        return asyncio.run(self._aget_relevant_documents(query, run_manager=run_manager))

# Usage example:
# retriever = AgentIndexRetriever()
# docs = retriever.invoke("web scraping tools")
# print(f"Found {len(docs)} relevant agents")
""",
                dependencies=["langchain-core", "aiohttp"],
                instructions="1. Install dependencies: pip install langchain-core aiohttp\\n2. Import and use AgentIndexRetriever in your LangChain chains",
                example_usage="""
from langchain_core.runnables import RunnableLambda

# Create retriever
agent_retriever = AgentIndexRetriever(limit=3)

# Use in a chain
def format_agents(docs):
    return "\\n\\n".join([doc.page_content for doc in docs])

chain = agent_retriever | RunnableLambda(format_agents)
result = chain.invoke("python web scraping")
print(result)
"""
            ),
            
            "crewai-python": IntegrationTemplate(
                framework="CrewAI",
                language="Python", 
                template="""
# Auto-generated AgentIndex integration for CrewAI
import asyncio
import aiohttp
from typing import List, Dict, Any
from crewai import Agent, Task, Crew

class AgentIndexRecruiter:
    '''Discovers and recruits agents for CrewAI crews'''
    
    def __init__(self, api_url: str = "https://api.agentcrawl.dev"):
        self.api_url = api_url
    
    async def discover_agents(self, need: str, limit: int = 3) -> List[Dict[str, Any]]:
        '''Discover agents matching the need'''
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_url}/v1/discover",
                json={"need": need, "limit": limit}
            ) as response:
                data = await response.json()
                return data.get("results", [])
    
    def create_crew_agent(self, agent_data: Dict[str, Any]) -> Agent:
        '''Convert discovered agent to CrewAI Agent'''
        return Agent(
            role=f"{agent_data['name']} Specialist",
            goal=f"Use {agent_data['name']} for {agent_data.get('category', 'general')} tasks",
            backstory=f"I'm an expert with {agent_data['name']}: {agent_data['description'][:100]}...",
            verbose=True,
            allow_delegation=False,
            tools=[]  # Add actual tools based on agent_data['url']
        )
    
    async def build_specialized_crew(self, project_description: str) -> Crew:
        '''Build a CrewAI crew with discovered agents'''
        discovered = await self.discover_agents(project_description, limit=3)
        
        agents = []
        tasks = []
        
        for i, agent_data in enumerate(discovered):
            # Create CrewAI agent
            crew_agent = self.create_crew_agent(agent_data)
            agents.append(crew_agent)
            
            # Create corresponding task
            task = Task(
                description=f"Use {agent_data['name']} to help with: {project_description}",
                expected_output=f"Results from {agent_data['name']} analysis",
                agent=crew_agent
            )
            tasks.append(task)
        
        return Crew(
            agents=agents,
            tasks=tasks,
            verbose=True
        )

# Usage example:
# recruiter = AgentIndexRecruiter()
# crew = await recruiter.build_specialized_crew("web scraping project")
# result = crew.kickoff()
""",
                dependencies=["crewai", "aiohttp"],
                instructions="1. Install dependencies: pip install crewai aiohttp\\n2. Use AgentIndexRecruiter to dynamically build crews",
                example_usage="""
import asyncio

async def main():
    recruiter = AgentIndexRecruiter()
    
    # Build crew for web scraping project
    crew = await recruiter.build_specialized_crew("web scraping and data analysis")
    
    # Run the crew
    result = crew.kickoff(inputs={
        "project": "Scrape e-commerce data and analyze pricing trends"
    })
    
    print(result)

asyncio.run(main())
"""
            ),
            
            "react-typescript": IntegrationTemplate(
                framework="React",
                language="TypeScript",
                template="""
// Auto-generated AgentIndex integration for React
import React, { useState, useEffect } from 'react';

interface Agent {
  id: string;
  name: string;
  description: string;
  url: string;
  trust_score?: number;
  relevance: number;
  source: string;
}

interface AgentIndexClientProps {
  apiUrl?: string;
  defaultLimit?: number;
}

interface UseAgentSearchResult {
  agents: Agent[];
  loading: boolean;
  error: string | null;
  search: (query: string) => Promise<void>;
}

// Custom hook for agent search
export const useAgentSearch = (
  apiUrl = 'https://api.agentcrawl.dev',
  defaultLimit = 5
): UseAgentSearchResult => {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const search = async (query: string) => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`${apiUrl}/v1/discover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ need: query, limit: defaultLimit })
      });
      
      if (!response.ok) {
        throw new Error(`Search failed: ${response.status}`);
      }
      
      const data = await response.json();
      setAgents(data.results || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
      setAgents([]);
    } finally {
      setLoading(false);
    }
  };
  
  return { agents, loading, error, search };
};

// Agent card component
interface AgentCardProps {
  agent: Agent;
  onSelect?: (agent: Agent) => void;
}

export const AgentCard: React.FC<AgentCardProps> = ({ agent, onSelect }) => {
  return (
    <div 
      className="agent-card"
      style={{
        border: '1px solid #e5e7eb',
        borderRadius: '8px',
        padding: '16px',
        margin: '8px 0',
        cursor: onSelect ? 'pointer' : 'default'
      }}
      onClick={() => onSelect?.(agent)}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
        <h3 style={{ margin: '0 0 8px 0', color: '#1f2937' }}>{agent.name}</h3>
        {agent.trust_score && (
          <span 
            style={{
              background: '#10b981',
              color: 'white',
              padding: '2px 8px',
              borderRadius: '12px',
              fontSize: '0.75rem'
            }}
          >
            {agent.trust_score}/100
          </span>
        )}
      </div>
      
      <p style={{ color: '#6b7280', margin: '8px 0' }}>
        {agent.description}
      </p>
      
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '0.875rem', color: '#9ca3af' }}>
          {agent.source} • {(agent.relevance * 100).toFixed(0)}% match
        </span>
        <a 
          href={agent.url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: '#3b82f6', textDecoration: 'none' }}
          onClick={(e) => e.stopPropagation()}
        >
          View →
        </a>
      </div>
    </div>
  );
};

// Main search component
export const AgentIndexSearch: React.FC<AgentIndexClientProps> = ({ 
  apiUrl, 
  defaultLimit 
}) => {
  const { agents, loading, error, search } = useAgentSearch(apiUrl, defaultLimit);
  const [query, setQuery] = useState('');
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      search(query.trim());
    }
  };
  
  return (
    <div className="agent-index-search">
      <form onSubmit={handleSubmit} style={{ marginBottom: '20px' }}>
        <div style={{ display: 'flex', gap: '8px' }}>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search for agents (e.g., 'web scraping tool')"
            style={{
              flex: 1,
              padding: '12px',
              border: '1px solid #d1d5db',
              borderRadius: '6px',
              fontSize: '16px'
            }}
          />
          <button
            type="submit"
            disabled={loading || !query.trim()}
            style={{
              padding: '12px 24px',
              background: '#3b82f6',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '16px'
            }}
          >
            {loading ? 'Searching...' : 'Search'}
          </button>
        </div>
      </form>
      
      {error && (
        <div style={{ color: '#ef4444', marginBottom: '16px' }}>
          Error: {error}
        </div>
      )}
      
      <div className="agent-results">
        {agents.map((agent) => (
          <AgentCard key={agent.id} agent={agent} />
        ))}
      </div>
      
      {agents.length === 0 && !loading && !error && (
        <div style={{ textAlign: 'center', color: '#6b7280', padding: '40px' }}>
          Search for agents to get started
        </div>
      )}
    </div>
  );
};
""",
                dependencies=["react", "@types/react"],
                instructions="1. Install dependencies: npm install react @types/react\\n2. Import and use AgentIndexSearch component\\n3. Add CSS classes as needed",
                example_usage="""
// App.tsx
import React from 'react';
import { AgentIndexSearch } from './components/AgentIndexSearch';

function App() {
  return (
    <div className="App">
      <h1>Find AI Agents</h1>
      <AgentIndexSearch defaultLimit={8} />
    </div>
  );
}

export default App;
"""
            ),
            
            "nextjs-typescript": IntegrationTemplate(
                framework="Next.js",
                language="TypeScript",
                template="""
// Auto-generated AgentIndex integration for Next.js
// pages/api/agents/search.ts
import type { NextApiRequest, NextApiResponse } from 'next';

interface AgentSearchRequest {
  need: string;
  limit?: number;
  category?: string;
}

interface Agent {
  id: string;
  name: string;
  description: string;
  url: string;
  trust_score?: number;
  relevance: number;
  source: string;
}

interface AgentSearchResponse {
  results: Agent[];
  total: number;
  query_time_ms: number;
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse<AgentSearchResponse | { error: string }>
) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }
  
  const { need, limit = 10, category }: AgentSearchRequest = req.body;
  
  if (!need) {
    return res.status(400).json({ error: 'Search query required' });
  }
  
  try {
    const response = await fetch('https://api.agentcrawl.dev/v1/discover', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ need, limit, category })
    });
    
    if (!response.ok) {
      throw new Error(`API request failed: ${response.status}`);
    }
    
    const data = await response.json();
    res.status(200).json(data);
  } catch (error) {
    console.error('Agent search failed:', error);
    res.status(500).json({ 
      error: error instanceof Error ? error.message : 'Search failed' 
    });
  }
}

// hooks/useAgentSearch.ts
import { useState, useCallback } from 'react';

interface UseAgentSearchResult {
  agents: Agent[];
  loading: boolean;
  error: string | null;
  search: (query: string, category?: string) => Promise<void>;
}

export const useAgentSearch = (): UseAgentSearchResult => {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const search = useCallback(async (query: string, category?: string) => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch('/api/agents/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ need: query, category, limit: 10 })
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Search failed');
      }
      
      const data = await response.json();
      setAgents(data.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }, []);
  
  return { agents, loading, error, search };
};

// components/AgentSearch.tsx
import React, { useState } from 'react';
import { useAgentSearch } from '../hooks/useAgentSearch';

export const AgentSearch: React.FC = () => {
  const { agents, loading, error, search } = useAgentSearch();
  const [query, setQuery] = useState('');
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      await search(query.trim());
    }
  };
  
  return (
    <div className="max-w-4xl mx-auto p-6">
      <form onSubmit={handleSubmit} className="mb-8">
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search for agents..."
            className="flex-1 px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Searching...' : 'Search'}
          </button>
        </div>
      </form>
      
      {error && (
        <div className="mb-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
          {error}
        </div>
      )}
      
      <div className="grid gap-4">
        {agents.map((agent) => (
          <div key={agent.id} className="p-4 border border-gray-200 rounded-lg hover:shadow-md transition-shadow">
            <div className="flex justify-between items-start mb-2">
              <h3 className="text-lg font-semibold text-gray-900">{agent.name}</h3>
              {agent.trust_score && (
                <span className="px-2 py-1 bg-green-100 text-green-800 text-xs rounded-full">
                  {agent.trust_score}/100
                </span>
              )}
            </div>
            <p className="text-gray-600 mb-3">{agent.description}</p>
            <div className="flex justify-between items-center text-sm text-gray-500">
              <span>{agent.source} • {Math.round(agent.relevance * 100)}% match</span>
              <a href={agent.url} target="_blank" rel="noopener noreferrer" 
                 className="text-blue-600 hover:underline">
                View Agent →
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
""",
                dependencies=["next", "react", "@types/react", "@types/node", "tailwindcss"],
                instructions="1. Install dependencies: npm install next react @types/react @types/node\\n2. Add API route and components\\n3. Configure Tailwind CSS for styling",
                example_usage="""
// pages/index.tsx
import { AgentSearch } from '../components/AgentSearch';

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="container mx-auto py-12">
        <h1 className="text-4xl font-bold text-center mb-8">
          Discover AI Agents
        </h1>
        <AgentSearch />
      </div>
    </div>
  );
}
"""
            ),
            
            "fastapi-python": IntegrationTemplate(
                framework="FastAPI",
                language="Python",
                template="""
# Auto-generated AgentIndex integration for FastAPI
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import httpx
import asyncio

app = FastAPI(title="AgentIndex Integration API")

class AgentSearchRequest(BaseModel):
    need: str
    limit: Optional[int] = 10
    category: Optional[str] = None

class Agent(BaseModel):
    id: str
    name: str
    description: str
    url: str
    trust_score: Optional[float] = None
    relevance: float
    source: str

class AgentSearchResponse(BaseModel):
    results: List[Agent]
    total: int
    query_time_ms: int

class AgentIndexClient:
    '''Client for interacting with AgentIndex API'''
    
    def __init__(self, base_url: str = "https://api.agentcrawl.dev"):
        self.base_url = base_url
        self.client = httpx.AsyncClient()
    
    async def search_agents(
        self, 
        need: str, 
        limit: int = 10, 
        category: Optional[str] = None
    ) -> AgentSearchResponse:
        '''Search for agents matching the need'''
        
        payload = {"need": need, "limit": limit}
        if category:
            payload["category"] = category
        
        try:
            response = await self.client.post(
                f"{self.base_url}/v1/discover",
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            
            return AgentSearchResponse(**data)
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, 
                              detail=f"AgentIndex API error: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, 
                              detail=f"Search failed: {str(e)}")
    
    async def close(self):
        '''Close the HTTP client'''
        await self.client.aclose()

# Global client instance
agent_client = AgentIndexClient()

@app.on_event("shutdown")
async def shutdown_event():
    await agent_client.close()

@app.post("/search", response_model=AgentSearchResponse)
async def search_agents(request: AgentSearchRequest):
    '''Search for AI agents'''
    return await agent_client.search_agents(
        need=request.need,
        limit=request.limit,
        category=request.category
    )

@app.get("/discover", response_model=AgentSearchResponse)
async def discover_agents(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Number of results"),
    category: Optional[str] = Query(None, description="Filter by category")
):
    '''Discover AI agents via GET request'''
    return await agent_client.search_agents(
        need=q,
        limit=limit, 
        category=category
    )

@app.get("/agents/recommend/{user_preference}")
async def recommend_agents(
    user_preference: str,
    limit: int = Query(5, ge=1, le=20)
):
    '''Get personalized agent recommendations'''
    
    # This could be enhanced with user profiling
    search_terms = {
        "beginner": "beginner friendly tutorial tools",
        "webdev": "web development frameworks",
        "datascience": "data analysis machine learning",
        "devops": "deployment automation infrastructure"
    }
    
    query = search_terms.get(user_preference, user_preference)
    return await agent_client.search_agents(need=query, limit=limit)

@app.get("/")
async def root():
    '''API information'''
    return {
        "service": "AgentIndex Integration API",
        "version": "1.0.0",
        "endpoints": [
            "POST /search - Search for agents",
            "GET /discover - Discover agents via query parameter",
            "GET /agents/recommend/{preference} - Get recommendations"
        ],
        "powered_by": "https://agentcrawl.dev"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
""",
                dependencies=["fastapi", "uvicorn", "httpx", "pydantic"],
                instructions="1. Install dependencies: pip install fastapi uvicorn httpx pydantic\\n2. Run with: uvicorn main:app --reload\\n3. Access API docs at http://localhost:8000/docs",
                example_usage="""
# client_example.py
import httpx
import asyncio

async def test_api():
    async with httpx.AsyncClient() as client:
        # Search for agents
        response = await client.post(
            "http://localhost:8000/search",
            json={"need": "web scraping tool", "limit": 5}
        )
        data = response.json()
        print(f"Found {len(data['results'])} agents")
        
        # Get recommendations
        response = await client.get(
            "http://localhost:8000/agents/recommend/webdev?limit=3"
        )
        data = response.json()
        print(f"Recommended {len(data['results'])} agents for web development")

asyncio.run(test_api())
"""
            )
        }
    
    async def generate_integration(
        self,
        framework: str,
        language: str,
        agent_id: Optional[str] = None,
        custom_requirements: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate integration code for specified framework"""
        
        template_key = f"{framework.lower()}-{language.lower()}"
        
        if template_key not in self.templates:
            available = list(self.templates.keys())
            raise ValueError(f"Template not found. Available: {available}")
        
        template = self.templates[template_key]
        
        # If specific agent requested, customize the integration
        if agent_id:
            agent_data = await self._get_agent_data(agent_id)
            if agent_data:
                template = self._customize_for_agent(template, agent_data)
        
        # Apply custom requirements if provided
        if custom_requirements:
            template = self._apply_custom_requirements(template, custom_requirements)
        
        return {
            "framework": template.framework,
            "language": template.language,
            "code": template.template,
            "dependencies": template.dependencies,
            "instructions": template.instructions,
            "example_usage": template.example_usage,
            "generated_at": datetime.utcnow().isoformat(),
            "customized_for_agent": agent_id is not None
        }
    
    async def _get_agent_data(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent data for customization"""
        conn = await asyncpg.connect(self.db_url)
        
        try:
            result = await conn.fetchrow(
                "SELECT * FROM agents WHERE id = $1",
                agent_id
            )
            return dict(result) if result else None
        finally:
            await conn.close()
    
    def _customize_for_agent(self, template: IntegrationTemplate, agent_data: Dict[str, Any]) -> IntegrationTemplate:
        """Customize template for specific agent"""
        
        agent_name = agent_data.get("name", "Unknown Agent")
        agent_url = agent_data.get("source_url", "")
        
        # Add agent-specific comments and examples
        customized_template = template.template.replace(
            "# Auto-generated AgentIndex integration",
            f"# Auto-generated integration for {agent_name} via AgentIndex"
        )
        
        # Add agent-specific usage example
        agent_example = f"""
# Specific integration for {agent_name}
# Agent URL: {agent_url}
# Use this integration to discover {agent_name} and similar tools
"""
        
        return IntegrationTemplate(
            framework=template.framework,
            language=template.language,
            template=customized_template + agent_example,
            dependencies=template.dependencies,
            instructions=template.instructions,
            example_usage=template.example_usage
        )
    
    def _apply_custom_requirements(self, template: IntegrationTemplate, requirements: str) -> IntegrationTemplate:
        """Apply custom requirements to template"""
        
        custom_note = f"""
# Custom Requirements Applied:
# {requirements}
"""
        
        return IntegrationTemplate(
            framework=template.framework,
            language=template.language, 
            template=template.template + custom_note,
            dependencies=template.dependencies,
            instructions=template.instructions + f"\\n\\nCustom: {requirements}",
            example_usage=template.example_usage
        )
    
    def get_available_integrations(self) -> List[Dict[str, str]]:
        """Get list of available integration templates"""
        
        return [
            {
                "key": key,
                "framework": template.framework,
                "language": template.language,
                "description": f"{template.framework} integration for {template.language}"
            }
            for key, template in self.templates.items()
        ]


class IntegrationWebInterface:
    """Web interface for code generation"""
    
    def __init__(self):
        self.generator = CodeIntegrationGenerator()
    
    def generate_integration_page(self) -> str:
        """Generate web interface for integration generation"""
        
        available_integrations = self.generator.get_available_integrations()
        
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>⚡ One-Click Integration Generator</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ text-align: center; color: white; margin-bottom: 40px; }}
        .header h1 {{ font-size: 3em; margin-bottom: 10px; text-shadow: 0 2px 4px rgba(0,0,0,0.3); }}
        .integration-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; margin-bottom: 40px; }}
        .integration-card {{ background: rgba(255,255,255,0.95); border-radius: 16px; padding: 25px; backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.3); transition: transform 0.3s; cursor: pointer; }}
        .integration-card:hover {{ transform: translateY(-5px); }}
        .framework-icon {{ font-size: 2em; margin-bottom: 15px; }}
        .framework-name {{ font-size: 1.3em; font-weight: bold; color: #1e293b; margin-bottom: 8px; }}
        .framework-desc {{ color: #64748b; margin-bottom: 15px; }}
        .language-badge {{ background: #3b82f6; color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.8em; }}
        .generate-btn {{ width: 100%; padding: 12px; background: #10b981; color: white; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; margin-top: 15px; }}
        .generate-btn:hover {{ background: #059669; }}
        .code-output {{ background: rgba(255,255,255,0.95); border-radius: 16px; padding: 25px; backdrop-filter: blur(10px); margin-top: 20px; display: none; }}
        .code-block {{ background: #1e293b; color: #f8fafc; padding: 20px; border-radius: 8px; font-family: 'Courier New', monospace; font-size: 0.9em; line-height: 1.4; overflow-x: auto; }}
        .copy-btn {{ background: #3b82f6; color: white; padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; margin-top: 10px; }}
        .instructions {{ background: #f0fdf4; border: 1px solid #bbf7d0; padding: 15px; border-radius: 8px; margin: 15px 0; }}
        .tab-buttons {{ display: flex; gap: 10px; margin-bottom: 20px; }}
        .tab-btn {{ padding: 10px 20px; background: #e5e7eb; border: none; border-radius: 6px; cursor: pointer; }}
        .tab-btn.active {{ background: #3b82f6; color: white; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚡ One-Click Integration Generator</h1>
            <p>Generate ready-to-use integration code for popular frameworks</p>
        </div>
        
        <div class="integration-grid">
            {self._render_integration_cards(available_integrations)}
        </div>
        
        <div id="codeOutput" class="code-output">
            <h3>Generated Integration Code</h3>
            <div class="tab-buttons">
                <button class="tab-btn active" onclick="showTab('code')">Code</button>
                <button class="tab-btn" onclick="showTab('instructions')">Setup Instructions</button>
                <button class="tab-btn" onclick="showTab('example')">Usage Example</button>
            </div>
            
            <div id="codeTab" class="tab-content active">
                <pre id="generatedCode" class="code-block"></pre>
                <button class="copy-btn" onclick="copyCode()">Copy Code</button>
            </div>
            
            <div id="instructionsTab" class="tab-content">
                <div id="setupInstructions" class="instructions"></div>
            </div>
            
            <div id="exampleTab" class="tab-content">
                <pre id="usageExample" class="code-block"></pre>
                <button class="copy-btn" onclick="copyExample()">Copy Example</button>
            </div>
        </div>
    </div>
    
    <script>
        async function generateIntegration(framework, language) {{
            const response = await fetch('/generate-integration', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ framework, language }})
            }});
            
            const data = await response.json();
            
            document.getElementById('generatedCode').textContent = data.code;
            document.getElementById('setupInstructions').innerHTML = data.instructions.replace(/\\n/g, '<br>');
            document.getElementById('usageExample').textContent = data.example_usage;
            
            document.getElementById('codeOutput').style.display = 'block';
            document.getElementById('codeOutput').scrollIntoView({{ behavior: 'smooth' }});
        }}
        
        function showTab(tabName) {{
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            
            // Show selected tab
            document.getElementById(tabName + 'Tab').classList.add('active');
            event.target.classList.add('active');
        }}
        
        function copyCode() {{
            navigator.clipboard.writeText(document.getElementById('generatedCode').textContent);
            alert('Code copied to clipboard!');
        }}
        
        function copyExample() {{
            navigator.clipboard.writeText(document.getElementById('usageExample').textContent);
            alert('Example copied to clipboard!');
        }}
    </script>
</body>
</html>
        """
    
    def _render_integration_cards(self, integrations: List[Dict[str, str]]) -> str:
        """Render integration option cards"""
        
        framework_icons = {
            "LangChain": "🦜",
            "CrewAI": "👥", 
            "React": "⚛️",
            "Next.js": "▲",
            "FastAPI": "🚀"
        }
        
        cards = []
        for integration in integrations:
            icon = framework_icons.get(integration["framework"], "🔧")
            cards.append(f"""
            <div class="integration-card" onclick="generateIntegration('{integration['framework']}', '{integration['language']}')">
                <div class="framework-icon">{icon}</div>
                <div class="framework-name">{integration['framework']}</div>
                <div class="framework-desc">{integration['description']}</div>
                <div class="language-badge">{integration['language']}</div>
                <button class="generate-btn">Generate Integration →</button>
            </div>
            """)
        
        return "\\n".join(cards)


if __name__ == "__main__":
    async def test_generator():
        generator = CodeIntegrationGenerator()
        interface = IntegrationWebInterface()
        
        print("⚡ Testing Integration Generator...")
        
        try:
            # Test code generation
            integration = await generator.generate_integration("LangChain", "Python")
            
            print("✅ Generated LangChain integration!")
            print(f"   Framework: {integration['framework']}")
            print(f"   Language: {integration['language']}")
            print(f"   Dependencies: {integration['dependencies']}")
            
            # Generate web interface
            html = interface.generate_integration_page()
            with open("integration_generator.html", "w") as f:
                f.write(html)
            print("📄 Web interface saved to integration_generator.html")
            
        except Exception as e:
            print(f"❌ Test failed: {e}")
    
    asyncio.run(test_generator())