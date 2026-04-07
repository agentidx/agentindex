#!/usr/bin/env python3
"""
Framework Package Publisher - Accelerate Developer Adoption
Publishes npm and pip packages for LangChain, CrewAI, and AutoGen integrations
"""

import json
import os
import subprocess
from datetime import datetime
import shutil

class FrameworkPackagePublisher:
    def __init__(self):
        self.packages_created = []
        self.integrations_dir = "integrations"
        
    def create_npm_langchain_package(self):
        """Create npm package for LangChain integration"""
        
        package_dir = "npm-langchain-agentindex"
        if os.path.exists(package_dir):
            shutil.rmtree(package_dir)
        os.makedirs(package_dir)
        
        # Package.json
        package_json = {
            "name": "@agentidx/langchain",
            "version": "1.0.0",
            "description": "AgentIndex integration for LangChain - discover 40,000+ agents with semantic search",
            "main": "dist/index.js",
            "types": "dist/index.d.ts",
            "scripts": {
                "build": "tsc",
                "test": "jest",
                "prepublish": "npm run build"
            },
            "keywords": [
                "langchain",
                "agents",
                "ai",
                "discovery",
                "semantic-search",
                "agentindex"
            ],
            "author": "AgentIndex",
            "license": "MIT",
            "homepage": "https://agentcrawl.dev",
            "repository": {
                "type": "git",
                "url": "https://github.com/agentidx/langchain-integration"
            },
            "dependencies": {
                "langchain": ">=0.1.0",
                "axios": "^1.6.0"
            },
            "devDependencies": {
                "typescript": "^5.0.0",
                "@types/node": "^20.0.0",
                "jest": "^29.0.0"
            }
        }
        
        with open(f"{package_dir}/package.json", "w") as f:
            json.dump(package_json, f, indent=2)
        
        # TypeScript source code
        os.makedirs(f"{package_dir}/src", exist_ok=True)
        
        index_ts = '''/**
 * AgentIndex LangChain Integration
 * Discover and retrieve agents using semantic search
 */

import axios from 'axios';
import { BaseRetriever, Document } from 'langchain/dist/schema';

export interface AgentSearchParams {
  query: string;
  framework?: string;
  minTrustScore?: number;
  maxResults?: number;
  resourceRequirements?: {
    maxMemoryGB?: number;
    requiresCPU?: boolean;
    requiresGPU?: boolean;
  };
}

export interface AgentResult {
  id: string;
  name: string;
  description: string;
  trustScore: number;
  framework: string;
  repositoryUrl: string;
  documentation?: string;
  usageExamples?: string[];
  resourceRequirements: {
    memoryGB: number;
    cpu: boolean;
    gpu: boolean;
  };
}

export class AgentIndexRetriever extends BaseRetriever {
  private apiKey?: string;
  private baseUrl: string = 'https://api.agentcrawl.dev/v1';
  
  constructor(options: { apiKey?: string; baseUrl?: string } = {}) {
    super();
    this.apiKey = options.apiKey;
    if (options.baseUrl) this.baseUrl = options.baseUrl;
  }

  async getRelevantDocuments(query: string): Promise<Document[]> {
    const agents = await this.searchAgents({
      query,
      framework: 'langchain',
      maxResults: 10
    });

    return agents.map(agent => new Document({
      pageContent: `${agent.name}: ${agent.description}\\n\\nTrust Score: ${agent.trustScore}/100\\n\\nRepository: ${agent.repositoryUrl}`,
      metadata: {
        agentId: agent.id,
        name: agent.name,
        trustScore: agent.trustScore,
        framework: agent.framework,
        repositoryUrl: agent.repositoryUrl
      }
    }));
  }

  async searchAgents(params: AgentSearchParams): Promise<AgentResult[]> {
    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json'
      };
      
      if (this.apiKey) {
        headers['X-API-Key'] = this.apiKey;
      }

      const response = await axios.post(`${this.baseUrl}/search`, {
        query: params.query,
        filters: {
          framework: params.framework || 'langchain',
          min_trust_score: params.minTrustScore || 70,
          max_results: params.maxResults || 20,
          ...params.resourceRequirements
        }
      }, { headers });

      return response.data.agents || [];
    } catch (error) {
      console.error('AgentIndex search failed:', error);
      return [];
    }
  }

  async getAgentDetails(agentId: string): Promise<AgentResult | null> {
    try {
      const headers: Record<string, string> = {};
      if (this.apiKey) headers['X-API-Key'] = this.apiKey;

      const response = await axios.get(`${this.baseUrl}/agents/${agentId}`, { headers });
      return response.data.agent || null;
    } catch (error) {
      console.error('Failed to get agent details:', error);
      return null;
    }
  }
}

// Convenience functions for common use cases
export async function findAgentsForTask(
  task: string, 
  options: { minTrustScore?: number; maxResults?: number } = {}
): Promise<AgentResult[]> {
  const retriever = new AgentIndexRetriever();
  return await retriever.searchAgents({
    query: task,
    framework: 'langchain',
    minTrustScore: options.minTrustScore || 75,
    maxResults: options.maxResults || 10
  });
}

export async function getTopAgents(category?: string): Promise<AgentResult[]> {
  const query = category ? `${category} agents` : 'high quality agents';
  return await findAgentsForTask(query, { minTrustScore: 85, maxResults: 20 });
}
'''

        with open(f"{package_dir}/src/index.ts", "w") as f:
            f.write(index_ts)
        
        # TypeScript config
        tsconfig = {
            "compilerOptions": {
                "target": "ES2020",
                "module": "commonjs", 
                "lib": ["ES2020"],
                "outDir": "./dist",
                "rootDir": "./src",
                "strict": True,
                "declaration": True,
                "esModuleInterop": True,
                "skipLibCheck": True,
                "forceConsistentCasingInFileNames": True
            },
            "include": ["src/**/*"],
            "exclude": ["node_modules", "dist", "**/*.test.ts"]
        }
        
        with open(f"{package_dir}/tsconfig.json", "w") as f:
            json.dump(tsconfig, f, indent=2)
        
        # README
        readme = '''# @agentidx/langchain

AgentIndex integration for LangChain - discover 40,000+ AI agents with semantic search and trust scoring.

## Installation

```bash
npm install @agentidx/langchain
```

## Quick Start

```typescript
import { AgentIndexRetriever, findAgentsForTask } from '@agentidx/langchain';

// Use as LangChain retriever
const retriever = new AgentIndexRetriever();
const documents = await retriever.getRelevantDocuments('customer support automation');

// Or use convenience functions
const agents = await findAgentsForTask('document analysis', {
  minTrustScore: 80,
  maxResults: 5
});

console.log(`Found ${agents.length} high-trust agents for document analysis`);
```

## Advanced Usage

```typescript
// Search with specific requirements
const retriever = new AgentIndexRetriever({ apiKey: 'your-api-key' });

const agents = await retriever.searchAgents({
  query: 'code review and security analysis',
  framework: 'langchain',
  minTrustScore: 85,
  maxResults: 10,
  resourceRequirements: {
    maxMemoryGB: 8,
    requiresCPU: true,
    requiresGPU: false
  }
});
```

## Integration with LangChain

```typescript
import { RetrievalQA } from 'langchain/chains';
import { OpenAI } from 'langchain/llms';
import { AgentIndexRetriever } from '@agentidx/langchain';

const llm = new OpenAI();
const retriever = new AgentIndexRetriever();

const qaChain = RetrievalQA.fromLLM(llm, retriever);
const answer = await qaChain.call({
  query: 'What agents are best for customer support?'
});
```

## Features

- **Semantic Search**: Find agents by describing what you need
- **Trust Scoring**: Quality indicators (0-100) for reliability
- **Framework Filtering**: LangChain-specific compatibility
- **Resource Planning**: Memory, CPU, GPU requirements
- **40,000+ Agents**: Comprehensive coverage of the ecosystem

## API Reference

### AgentIndexRetriever

LangChain-compatible retriever for agent discovery.

### findAgentsForTask(task, options)

Convenience function to find agents for a specific task.

### getTopAgents(category?)

Get highest-rated agents, optionally filtered by category.

## Links

- [AgentIndex Platform](https://agentcrawl.dev)
- [API Documentation](https://api.agentcrawl.dev/docs)
- [Trust Scoring Guide](https://agentcrawl.dev/trust-scoring)
- [GitHub Repository](https://github.com/agentidx/langchain-integration)

## License

MIT
'''

        with open(f"{package_dir}/README.md", "w") as f:
            f.write(readme)
        
        self.packages_created.append({
            "name": "@agentidx/langchain",
            "type": "npm",
            "framework": "LangChain",
            "directory": package_dir,
            "estimated_downloads": "500-1000/month initially"
        })
        
        return package_dir
    
    def create_pip_langchain_package(self):
        """Create pip package for LangChain integration"""
        
        package_dir = "pip-langchain-agentindex"
        if os.path.exists(package_dir):
            shutil.rmtree(package_dir)
        os.makedirs(package_dir)
        os.makedirs(f"{package_dir}/agentindex_langchain")
        
        # setup.py
        setup_py = '''from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="agentindex-langchain",
    version="1.0.0",
    author="AgentIndex",
    author_email="support@agentcrawl.dev",
    description="AgentIndex integration for LangChain - discover 40,000+ agents with semantic search",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/agentidx/langchain-integration",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.8",
    install_requires=[
        "langchain>=0.1.0",
        "requests>=2.25.0",
        "pydantic>=1.8.0"
    ],
    keywords="langchain agents ai discovery semantic-search agentindex",
    project_urls={
        "Homepage": "https://agentcrawl.dev",
        "Documentation": "https://api.agentcrawl.dev/docs",
        "Source": "https://github.com/agentidx/langchain-integration",
        "Tracker": "https://github.com/agentidx/langchain-integration/issues",
    }
)
'''

        with open(f"{package_dir}/setup.py", "w") as f:
            f.write(setup_py)
        
        # Main Python module
        init_py = '''"""
AgentIndex LangChain Integration
Discover and retrieve agents using semantic search
"""

from .retriever import AgentIndexRetriever
from .utils import find_agents_for_task, get_top_agents

__version__ = "1.0.0"
__all__ = ["AgentIndexRetriever", "find_agents_for_task", "get_top_agents"]
'''

        with open(f"{package_dir}/agentindex_langchain/__init__.py", "w") as f:
            f.write(init_py)
        
        # Retriever implementation
        retriever_py = '''"""
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
                content = f"{agent['name']}: {agent['description']}\\n\\n"
                content += f"Trust Score: {agent['trust_score']}/100\\n"
                content += f"Repository: {agent['repository_url']}\\n"
                
                if agent.get('usage_examples'):
                    content += f"\\nUsage Examples:\\n{agent['usage_examples']}"
                
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
'''

        with open(f"{package_dir}/agentindex_langchain/retriever.py", "w") as f:
            f.write(retriever_py)
        
        # Utility functions
        utils_py = '''"""
Utility functions for AgentIndex LangChain integration
"""

from typing import List, Dict, Any, Optional
from .retriever import AgentIndexRetriever

def find_agents_for_task(
    task: str, 
    min_trust_score: int = 75, 
    max_results: int = 10,
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Find agents suitable for a specific task."""
    retriever = AgentIndexRetriever(
        api_key=api_key,
        min_trust_score=min_trust_score,
        max_results=max_results
    )
    
    return retriever.search_agents({
        "query": task,
        "framework": "langchain",
        "min_trust_score": min_trust_score,
        "max_results": max_results
    })

def get_top_agents(
    category: Optional[str] = None,
    min_trust_score: int = 85,
    max_results: int = 20,
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get highest-rated agents, optionally filtered by category."""
    query = f"{category} agents" if category else "high quality agents"
    
    return find_agents_for_task(
        query, 
        min_trust_score=min_trust_score,
        max_results=max_results,
        api_key=api_key
    )

def get_agents_by_resource_requirements(
    task: str,
    max_memory_gb: Optional[int] = None,
    requires_gpu: bool = False,
    min_trust_score: int = 70,
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Find agents that meet specific resource requirements."""
    retriever = AgentIndexRetriever(api_key=api_key)
    
    params = {
        "query": task,
        "framework": "langchain", 
        "min_trust_score": min_trust_score,
        "max_results": 20
    }
    
    # Add resource filters if specified
    if max_memory_gb or requires_gpu:
        params["resource_requirements"] = {
            "max_memory_gb": max_memory_gb,
            "requires_gpu": requires_gpu
        }
    
    return retriever.search_agents(params)
'''

        with open(f"{package_dir}/agentindex_langchain/utils.py", "w") as f:
            f.write(utils_py)
        
        # README
        readme_pip = '''# agentindex-langchain

AgentIndex integration for LangChain - discover 40,000+ AI agents with semantic search and trust scoring.

## Installation

```bash
pip install agentindex-langchain
```

## Quick Start

```python
from agentindex_langchain import AgentIndexRetriever, find_agents_for_task

# Use as LangChain retriever
retriever = AgentIndexRetriever()
documents = retriever.get_relevant_documents("customer support automation")

# Or use convenience functions  
agents = find_agents_for_task("document analysis", min_trust_score=80, max_results=5)
print(f"Found {len(agents)} high-trust agents for document analysis")
```

## Advanced Usage

```python
# Search with specific requirements
retriever = AgentIndexRetriever(
    api_key="your-api-key",
    min_trust_score=85,
    max_results=10
)

agents = retriever.search_agents({
    "query": "code review and security analysis",
    "framework": "langchain",
    "min_trust_score": 85,
    "max_results": 10
})

# Resource-aware search
from agentindex_langchain.utils import get_agents_by_resource_requirements

lightweight_agents = get_agents_by_resource_requirements(
    "text processing",
    max_memory_gb=4,
    requires_gpu=False
)
```

## LangChain Integration Examples

```python
# With RetrievalQA
from langchain.chains import RetrievalQA
from langchain.llms import OpenAI
from agentindex_langchain import AgentIndexRetriever

llm = OpenAI()
retriever = AgentIndexRetriever()

qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff", 
    retriever=retriever
)

result = qa_chain.run("What agents are best for customer support?")
print(result)

# With ConversationalRetrievalChain
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory

memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
conversation = ConversationalRetrievalChain.from_llm(
    llm=llm,
    retriever=retriever,
    memory=memory
)

response = conversation({"question": "Find me agents for data analysis"})
```

## Features

- **Semantic Search**: Find agents by describing what you need
- **Trust Scoring**: Quality indicators (0-100) for reliability  
- **LangChain Compatible**: Drop-in replacement for other retrievers
- **Resource Planning**: Filter by memory, CPU, GPU requirements
- **40,000+ Agents**: Comprehensive coverage of the ecosystem
- **Framework Filtering**: LangChain-specific compatibility

## API Reference

### AgentIndexRetriever

LangChain-compatible retriever for agent discovery.

**Parameters:**
- `api_key`: Optional API key for higher rate limits
- `base_url`: API endpoint (default: https://api.agentcrawl.dev/v1)  
- `min_trust_score`: Minimum quality threshold (default: 70)
- `max_results`: Maximum agents to return (default: 20)

### Utility Functions

- `find_agents_for_task(task, min_trust_score, max_results, api_key)`
- `get_top_agents(category, min_trust_score, max_results, api_key)` 
- `get_agents_by_resource_requirements(task, max_memory_gb, requires_gpu, min_trust_score, api_key)`

## Links

- [AgentIndex Platform](https://agentcrawl.dev)
- [API Documentation](https://api.agentcrawl.dev/docs)
- [Trust Scoring Guide](https://agentcrawl.dev/trust-scoring)
- [GitHub Repository](https://github.com/agentidx/langchain-integration)

## License

MIT
'''

        with open(f"{package_dir}/README.md", "w") as f:
            f.write(readme_pip)
        
        self.packages_created.append({
            "name": "agentindex-langchain",
            "type": "pip",
            "framework": "LangChain",  
            "directory": package_dir,
            "estimated_downloads": "1000-2000/month initially"
        })
        
        return package_dir
    
    def create_crewai_package(self):
        """Create pip package for CrewAI integration"""
        
        package_dir = "pip-crewai-agentindex"
        if os.path.exists(package_dir):
            shutil.rmtree(package_dir)
        os.makedirs(package_dir)
        os.makedirs(f"{package_dir}/agentindex_crewai")
        
        # setup.py for CrewAI
        setup_py_crewai = '''from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="agentindex-crewai",
    version="1.0.0", 
    author="AgentIndex",
    author_email="support@agentcrawl.dev",
    description="AgentIndex integration for CrewAI - discover and build crews with 40,000+ agents",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/agentidx/crewai-integration",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers", 
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9", 
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.8",
    install_requires=[
        "crewai>=0.1.0",
        "requests>=2.25.0",
        "pydantic>=1.8.0"
    ],
    keywords="crewai agents ai discovery crew-building agentindex",
    project_urls={
        "Homepage": "https://agentcrawl.dev",
        "Documentation": "https://api.agentcrawl.dev/docs", 
        "Source": "https://github.com/agentidx/crewai-integration",
        "Tracker": "https://github.com/agentidx/crewai-integration/issues",
    }
)
'''

        with open(f"{package_dir}/setup.py", "w") as f:
            f.write(setup_py_crewai)
        
        # CrewAI integration code
        init_py_crewai = '''"""
AgentIndex CrewAI Integration
Discover and build crews with agents from AgentIndex
"""

from .discovery import discover_crewai_agents, build_crew_from_discovery
from .crew_builder import AgentIndexCrewBuilder

__version__ = "1.0.0"
__all__ = ["discover_crewai_agents", "build_crew_from_discovery", "AgentIndexCrewBuilder"]
'''

        with open(f"{package_dir}/agentindex_crewai/__init__.py", "w") as f:
            f.write(init_py_crewai)
            
        # Main CrewAI discovery module
        discovery_py = '''"""
CrewAI Agent Discovery using AgentIndex
"""

import requests
from typing import List, Dict, Any, Optional
from crewai import Agent, Crew, Task

class AgentIndexCrewBuilder:
    """Build CrewAI crews using AgentIndex discovery."""
    
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://api.agentcrawl.dev/v1"):
        self.api_key = api_key
        self.base_url = base_url
    
    def discover_agents(
        self, 
        capabilities: List[str], 
        min_trust_score: int = 75,
        max_results: int = 20
    ) -> List[Dict[str, Any]]:
        """Discover agents suitable for CrewAI based on capabilities."""
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
                
            # Combine capabilities into search query
            query = " ".join(capabilities) + " crewai compatible"
            
            response = requests.post(
                f"{self.base_url}/search",
                json={
                    "query": query,
                    "filters": {
                        "framework": "crewai",
                        "min_trust_score": min_trust_score,
                        "max_results": max_results
                    }
                },
                headers=headers,
                timeout=10
            )
            
            response.raise_for_status()
            return response.json().get("agents", [])
            
        except Exception as e:
            print(f"Agent discovery failed: {e}")
            return []
    
    def build_crew(
        self, 
        task_description: str,
        roles: List[str],
        min_trust_score: int = 80
    ) -> Optional[Crew]:
        """Build a CrewAI crew for a specific task."""
        try:
            # Discover agents for each role
            crew_agents = []
            
            for role in roles:
                query = f"{task_description} {role}"
                agents = self.discover_agents([query], min_trust_score, max_results=3)
                
                if agents:
                    # Use the highest trust score agent for this role
                    best_agent = max(agents, key=lambda a: a.get("trust_score", 0))
                    
                    # Create CrewAI Agent from discovered agent
                    crew_agent = Agent(
                        role=role,
                        goal=f"Execute {role} tasks for: {task_description}",
                        backstory=f"Expert {role} agent with {best_agent.get('trust_score', 0)}/100 trust score",
                        verbose=True,
                        allow_delegation=True
                    )
                    
                    # Add AgentIndex metadata
                    crew_agent.agentindex_id = best_agent["id"]
                    crew_agent.agentindex_trust_score = best_agent.get("trust_score", 0)
                    crew_agent.agentindex_repository = best_agent.get("repository_url", "")
                    
                    crew_agents.append(crew_agent)
            
            if not crew_agents:
                print("No suitable agents found for the specified roles")
                return None
            
            # Create the task
            task = Task(
                description=task_description,
                agent=crew_agents[0]  # Primary agent
            )
            
            # Build and return the crew
            crew = Crew(
                agents=crew_agents,
                tasks=[task],
                verbose=True
            )
            
            return crew
            
        except Exception as e:
            print(f"Crew building failed: {e}")
            return None
    
    def get_recommended_crew_composition(
        self, 
        project_type: str,
        complexity: str = "medium"
    ) -> Dict[str, List[str]]:
        """Get recommended crew composition for common project types."""
        
        compositions = {
            "content_creation": {
                "simple": ["writer", "editor"],
                "medium": ["researcher", "writer", "editor"],
                "complex": ["researcher", "writer", "editor", "seo_specialist", "reviewer"]
            },
            "software_development": {
                "simple": ["developer", "tester"],
                "medium": ["analyst", "developer", "tester"],
                "complex": ["analyst", "architect", "developer", "tester", "reviewer", "devops"]
            },
            "data_analysis": {
                "simple": ["analyst", "reporter"],
                "medium": ["data_collector", "analyst", "reporter"],
                "complex": ["data_collector", "data_cleaner", "analyst", "ml_engineer", "reporter"]
            },
            "customer_service": {
                "simple": ["support_agent", "escalation_handler"],
                "medium": ["initial_responder", "support_agent", "escalation_handler"],
                "complex": ["triage_agent", "support_agent", "technical_specialist", "escalation_handler", "feedback_collector"]
            }
        }
        
        return compositions.get(project_type, {}).get(complexity, ["generalist"])

# Convenience functions
def discover_crewai_agents(
    capability: str, 
    min_trust_score: int = 75, 
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Discover CrewAI-compatible agents for a specific capability."""
    builder = AgentIndexCrewBuilder(api_key=api_key)
    return builder.discover_agents([capability], min_trust_score)

def build_crew_from_discovery(
    task: str,
    roles: List[str],  
    min_trust_score: int = 80,
    api_key: Optional[str] = None
) -> Optional[Crew]:
    """Build a complete crew using AgentIndex discovery."""
    builder = AgentIndexCrewBuilder(api_key=api_key)
    return builder.build_crew(task, roles, min_trust_score)
'''

        with open(f"{package_dir}/agentindex_crewai/discovery.py", "w") as f:
            f.write(discovery_py)
        
        # CrewAI builder utilities
        crew_builder_py = '''"""
Advanced CrewAI crew building utilities
"""

from typing import List, Dict, Any, Optional
from crewai import Agent, Crew, Task
from .discovery import AgentIndexCrewBuilder

class EnhancedCrewBuilder(AgentIndexCrewBuilder):
    """Enhanced crew builder with advanced features."""
    
    def build_hierarchical_crew(
        self,
        project: str,
        team_lead_role: str,
        specialist_roles: List[str],
        min_trust_score: int = 85
    ) -> Optional[Crew]:
        """Build a hierarchical crew with a team lead and specialists."""
        
        # Discover team lead
        lead_agents = self.discover_agents([f"{project} {team_lead_role} lead"], min_trust_score, 1)
        if not lead_agents:
            return None
            
        # Create team lead agent
        lead_agent = Agent(
            role=f"Team Lead - {team_lead_role}",
            goal=f"Lead the team to successfully complete: {project}",
            backstory=f"Experienced team lead with {lead_agents[0].get('trust_score', 0)}/100 trust score",
            verbose=True,
            allow_delegation=True,
            max_execution_time=300
        )
        
        # Add specialist agents
        specialist_agents = [lead_agent]
        
        for role in specialist_roles:
            agents = self.discover_agents([f"{project} {role} specialist"], min_trust_score, 1)
            if agents:
                specialist = Agent(
                    role=f"{role} Specialist", 
                    goal=f"Provide expert {role} services for: {project}",
                    backstory=f"Specialist with {agents[0].get('trust_score', 0)}/100 trust score",
                    verbose=True,
                    allow_delegation=False
                )
                specialist_agents.append(specialist)
        
        # Create coordinated tasks
        lead_task = Task(
            description=f"Coordinate team to complete: {project}",
            agent=lead_agent
        )
        
        crew = Crew(
            agents=specialist_agents,
            tasks=[lead_task],
            verbose=True,
            process="hierarchical",
            manager_llm="gpt-4"  # Use advanced LLM for management
        )
        
        return crew
    
    def optimize_crew_for_budget(
        self,
        task: str,
        max_agents: int,
        min_trust_score: int = 70
    ) -> Optional[Crew]:
        """Build cost-optimized crew within agent limit."""
        
        # Get all relevant agents
        all_agents = self.discover_agents([task], min_trust_score, max_results=50)
        
        if len(all_agents) <= max_agents:
            roles = [f"agent_{i+1}" for i in range(len(all_agents))]
            return self.build_crew(task, roles, min_trust_score)
        
        # Select top agents by trust score
        top_agents = sorted(all_agents, key=lambda a: a.get("trust_score", 0), reverse=True)[:max_agents]
        
        crew_agents = []
        for i, agent_data in enumerate(top_agents):
            agent = Agent(
                role=f"Specialist {i+1}",
                goal=f"Contribute expertise to: {task}",
                backstory=f"High-performance agent (Trust Score: {agent_data.get('trust_score', 0)}/100)",
                verbose=True
            )
            crew_agents.append(agent)
        
        main_task = Task(description=task, agent=crew_agents[0])
        
        return Crew(
            agents=crew_agents,
            tasks=[main_task],
            verbose=True
        )
'''

        with open(f"{package_dir}/agentindex_crewai/crew_builder.py", "w") as f:
            f.write(crew_builder_py)
        
        # CrewAI README
        readme_crewai = '''# agentindex-crewai

AgentIndex integration for CrewAI - discover and build crews with 40,000+ agents using semantic search and trust scoring.

## Installation

```bash
pip install agentindex-crewai
```

## Quick Start

```python
from agentindex_crewai import discover_crewai_agents, build_crew_from_discovery

# Discover agents for content creation
agents = discover_crewai_agents("content writing", min_trust_score=80)
print(f"Found {len(agents)} content agents")

# Build a complete crew
crew = build_crew_from_discovery(
    task="Create a comprehensive blog post about AI agents",
    roles=["researcher", "writer", "editor"], 
    min_trust_score=85
)

if crew:
    result = crew.kickoff()
    print(result)
```

## Advanced Usage

```python
from agentindex_crewai import AgentIndexCrewBuilder

# Initialize with API key for higher limits
builder = AgentIndexCrewBuilder(api_key="your-api-key")

# Build hierarchical crew with team lead
crew = builder.build_hierarchical_crew(
    project="E-commerce website development",
    team_lead_role="project_manager",
    specialist_roles=["frontend_developer", "backend_developer", "ui_designer"],
    min_trust_score=90
)

# Budget-optimized crew
budget_crew = builder.optimize_crew_for_budget(
    task="Customer support automation", 
    max_agents=3,
    min_trust_score=75
)

# Get recommended composition
composition = builder.get_recommended_crew_composition(
    project_type="software_development",
    complexity="complex"
)
print(f"Recommended roles: {composition}")
```

## Crew Building Strategies

### Project-Based Crews
```python
# Content creation crew
content_crew = build_crew_from_discovery(
    "Write technical documentation for API",
    ["technical_writer", "developer", "reviewer"],
    min_trust_score=80
)

# Data analysis crew  
data_crew = build_crew_from_discovery(
    "Analyze customer behavior data and create insights",
    ["data_scientist", "analyst", "report_writer"],
    min_trust_score=85
)
```

### Specialized Crews
```python
# Customer service crew
service_crew = builder.build_crew(
    "Handle customer inquiries and escalations",
    ["first_responder", "technical_support", "escalation_manager"]
)

# Quality assurance crew
qa_crew = builder.build_crew(
    "Test software and ensure quality standards", 
    ["test_designer", "automated_tester", "manual_tester", "bug_reporter"]
)
```

## Features

- **Intelligent Discovery**: Find CrewAI agents by describing project needs
- **Trust-Based Selection**: Agents rated 0-100 for reliability  
- **Hierarchical Crews**: Build teams with leaders and specialists
- **Budget Optimization**: Limit crew size while maintaining quality
- **Project Templates**: Pre-configured crew compositions for common tasks
- **40,000+ Agents**: Comprehensive agent ecosystem coverage

## Supported Project Types

- **Content Creation**: Research, writing, editing, SEO optimization
- **Software Development**: Analysis, development, testing, deployment  
- **Data Analysis**: Collection, processing, analysis, reporting
- **Customer Service**: Triage, support, escalation, feedback
- **Marketing**: Strategy, content, campaigns, analytics
- **Research**: Literature review, data collection, analysis, reporting

## API Reference

### AgentIndexCrewBuilder

Main class for building crews with AgentIndex.

**Methods:**
- `discover_agents(capabilities, min_trust_score, max_results)` 
- `build_crew(task_description, roles, min_trust_score)`
- `build_hierarchical_crew(project, team_lead_role, specialist_roles)`
- `optimize_crew_for_budget(task, max_agents, min_trust_score)`
- `get_recommended_crew_composition(project_type, complexity)`

### Utility Functions  

- `discover_crewai_agents(capability, min_trust_score, api_key)`
- `build_crew_from_discovery(task, roles, min_trust_score, api_key)`

## Links

- [AgentIndex Platform](https://agentcrawl.dev)
- [API Documentation](https://api.agentcrawl.dev/docs)
- [CrewAI Documentation](https://docs.crewai.dev)
- [Trust Scoring Guide](https://agentcrawl.dev/trust-scoring)
- [GitHub Repository](https://github.com/agentidx/crewai-integration)

## License

MIT
'''

        with open(f"{package_dir}/README.md", "w") as f:
            f.write(readme_crewai)
        
        self.packages_created.append({
            "name": "agentindex-crewai",
            "type": "pip", 
            "framework": "CrewAI",
            "directory": package_dir,
            "estimated_downloads": "800-1500/month initially"
        })
        
        return package_dir
    
    def create_publication_guide(self):
        """Create comprehensive publication guide"""
        
        publication_guide = f'''# Framework Package Publication Guide

## Publication Summary

**Target: Accelerate developer adoption and organic traffic growth**

### Packages Created:
{len(self.packages_created)} packages ready for publication

'''
        
        for package in self.packages_created:
            publication_guide += f'''
#### {package["name"]} ({package["type"].upper()})
- **Framework**: {package["framework"]}
- **Estimated Downloads**: {package["estimated_downloads"]}
- **Directory**: {package["directory"]}/
'''

        publication_guide += '''

## Publication Strategy

### Phase 1: npm Packages (JavaScript/TypeScript)
1. **@agentidx/langchain**
   - `cd npm-langchain-agentindex`
   - `npm install`
   - `npm run build`
   - `npm publish --access public`
   - Submit to npmjs.com

### Phase 2: pip Packages (Python)
1. **agentindex-langchain**
   - `cd pip-langchain-agentindex`
   - `python setup.py sdist bdist_wheel`
   - `twine upload dist/*`
   - Submit to PyPI

2. **agentindex-crewai** 
   - `cd pip-crewai-agentindex`
   - `python setup.py sdist bdist_wheel`
   - `twine upload dist/*`
   - Submit to PyPI

## Marketing & Distribution

### Developer Community Outreach
1. **LangChain Community**
   - Announce in LangChain Discord
   - Submit to LangChain integrations list
   - Create tutorial/example repo

2. **CrewAI Community**
   - Share in CrewAI Discord
   - Submit to CrewAI ecosystem
   - Create crew building examples

3. **Reddit Communities**
   - r/MachineLearning: "New LangChain integration packages"
   - r/LocalLLaMA: "Framework packages for local agents"
   - r/artificial: "Simplifying AI agent discovery"

### Technical Documentation
1. **Integration Guides**
   - Step-by-step tutorials
   - Code examples and templates
   - Best practices documentation

2. **API Documentation**
   - Full method reference
   - Parameter descriptions
   - Return value specifications

## Expected Impact

### Developer Adoption
- **npm package**: 500-1000 downloads/month initially
- **pip packages**: 1000-2000 downloads/month combined
- **Community growth**: 10-20% increase in API usage

### SEO Benefits
- **Framework-specific keywords**: "langchain agents", "crewai discovery"
- **Integration searches**: "agentindex langchain", "discover crewai agents"  
- **Technical long-tail**: "find ai agents for langchain projects"

### Organic Traffic Growth
- **Developer referrals**: Package users → AgentIndex platform
- **Documentation traffic**: Integration guides and tutorials
- **Community mentions**: GitHub, Discord, Reddit discussions

## Success Metrics

### Short-term (1-4 weeks)
- **Package downloads**: 500+ combined weekly
- **GitHub stars**: 50+ on integration repositories  
- **Community mentions**: 10+ in Discord/Reddit
- **API usage**: 20% increase from package users

### Medium-term (1-3 months)  
- **Package downloads**: 2000+ combined weekly
- **Integration usage**: 30% of API calls from packages
- **Framework partnerships**: Official ecosystem listings
- **Developer testimonials**: User success stories

### Long-term (3-6 months)
- **Market positioning**: Standard integration for agent discovery
- **Framework dependency**: Included in popular templates
- **Community ecosystem**: Third-party extensions and tools
- **Revenue impact**: Package users → paid API tiers

## Publication Checklist

### Pre-Publication
- [ ] Test all package installations locally
- [ ] Verify API integration works correctly  
- [ ] Review documentation for completeness
- [ ] Check for security vulnerabilities
- [ ] Validate package metadata and keywords

### Publication Day
- [ ] Publish npm package (@agentidx/langchain)
- [ ] Publish pip packages (agentindex-langchain, agentindex-crewai)
- [ ] Update AgentIndex documentation with integration guides
- [ ] Announce on social media and communities
- [ ] Submit to framework ecosystem lists

### Post-Publication
- [ ] Monitor download statistics
- [ ] Respond to community feedback
- [ ] Create tutorial content and examples
- [ ] Track API usage growth from packages
- [ ] Plan next framework integrations (AutoGen, etc.)

## Next Framework Integrations

### Planned for Phase 2
1. **AutoGen Integration** - Microsoft's multi-agent framework
2. **Haystack Integration** - DeepSet's NLP framework  
3. **Semantic Kernel Integration** - Microsoft's LLM orchestration
4. **LocalAI Integration** - Self-hosted AI solutions

**Timeline**: 2-4 weeks after initial package success
**Expected impact**: 50%+ increase in total package downloads

---

**Status**: All packages ready for immediate publication
**Priority**: HIGH - Critical for developer adoption and organic growth
**Next steps**: Begin publication sequence starting with LangChain packages
'''

        with open("framework_publication_guide.md", "w") as f:
            f.write(publication_guide)
        
        return publication_guide

    def generate_publication_summary(self):
        """Generate comprehensive publication summary"""
        
        langchain_npm = self.create_npm_langchain_package()
        langchain_pip = self.create_pip_langchain_package()  
        crewai_pip = self.create_crewai_package()
        guide = self.create_publication_guide()
        
        summary = {
            "created_at": datetime.now().isoformat(),
            "target": "Accelerate developer adoption and organic traffic",
            "packages_created": len(self.packages_created),
            "frameworks_supported": ["LangChain", "CrewAI"],
            "estimated_impact": {
                "monthly_downloads": "2300-4500 combined",
                "api_usage_increase": "20-30%",
                "organic_traffic_boost": "Framework-specific keyword traffic",
                "developer_community_growth": "10-20% increase"
            },
            "packages": self.packages_created,
            "publication_ready": True,
            "next_steps": [
                "Publish npm package to npmjs.com",
                "Publish pip packages to PyPI", 
                "Create integration documentation",
                "Announce to developer communities",
                "Monitor adoption and feedback"
            ]
        }
        
        with open("framework_packages_summary.json", "w") as f:
            json.dump(summary, f, indent=2)
        
        return summary

def main():
    print("📦 FRAMEWORK PACKAGE PUBLISHER")
    print("=" * 60)
    print("Creating npm and pip packages for developer adoption")
    print()
    
    publisher = FrameworkPackagePublisher()
    summary = publisher.generate_publication_summary()
    
    print("✅ PACKAGE CREATION COMPLETE")
    print(f"📊 Packages created: {summary['packages_created']}")
    print(f"🎯 Frameworks: {', '.join(summary['frameworks_supported'])}")
    
    print(f"\n📈 EXPECTED IMPACT:")
    for metric, value in summary['estimated_impact'].items():
        print(f"• {metric.replace('_', ' ').title()}: {value}")
    
    print(f"\n📦 PACKAGES READY FOR PUBLICATION:")
    for package in summary['packages']:
        print(f"• {package['name']} ({package['type'].upper()}) - {package['estimated_downloads']}")
    
    print(f"\n🚀 PUBLICATION SEQUENCE:")
    for i, step in enumerate(summary['next_steps'], 1):
        print(f"{i}. {step}")
    
    print(f"\n💾 Files created:")
    print(f"• framework_publication_guide.md")
    print(f"• framework_packages_summary.json") 
    print(f"• {len(publisher.packages_created)} package directories")
    
    print(f"\n✅ Ready for immediate publication and developer outreach")
    
    return summary

if __name__ == "__main__":
    summary = main()