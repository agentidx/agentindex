"""
One-Click Integration Code Generator
Automatically generates framework integration code for discovered agents
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
import aiohttp


class CodeIntegrationGenerator:
    """Generates integration code for various frameworks"""
    
    def __init__(self):
        self.templates = {
            "langchain": {
                "python": {
                    "dependencies": ["langchain-core", "requests"],
                    "template": """
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun
import requests
from typing import List


class AgentIndexRetriever(BaseRetriever):
    \"\"\"Custom retriever for AgentIndex API\"\"\"
    
    def __init__(self, api_url: str = "https://api.agentcrawl.dev", limit: int = 5):
        super().__init__()
        self.api_url = api_url
        self.limit = limit
    
    def _get_relevant_documents(
        self, 
        query: str, 
        *, 
        run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        \"\"\"Retrieve relevant agent documents\"\"\"
        
        try:
            response = requests.post(
                f"{self.api_url}/v1/discover",
                json={"need": query, "max_results": self.limit}
            )
            response.raise_for_status()
            
            data = response.json()
            documents = []
            
            for result in data.get("results", []):
                content = f"Agent: {result.get('name', 'Unknown')}\\n"
                content += f"Description: {result.get('description', '')}\\n"
                content += f"Platform: {result.get('source', '')}\\n"
                content += f"URL: {result.get('url', '')}"
                
                metadata = {
                    "agent_id": result.get("id"),
                    "name": result.get("name"),
                    "source": result.get("source"),
                    "url": result.get("url"),
                    "trust_score": result.get("trust_score"),
                    "category": result.get("category")
                }
                
                documents.append(Document(
                    page_content=content,
                    metadata=metadata
                ))
            
            return documents
            
        except Exception as e:
            run_manager.on_retriever_error(e)
            return []


# Usage example
if __name__ == "__main__":
    retriever = AgentIndexRetriever(limit=3)
    docs = retriever.get_relevant_documents("web scraping tool")
    
    for doc in docs:
        print(f"Found: {doc.metadata['name']}")
        print(f"Trust: {doc.metadata['trust_score']}/100")
        print("---")
""",
                    "instructions": """
1. Install dependencies: pip install langchain-core requests
2. Import the AgentIndexRetriever class
3. Initialize with your preferred API URL and result limit
4. Use in LangChain chains as a retriever component
5. Documents include agent metadata for further processing
""",
                    "example_usage": """
from langchain_core.runnables import RunnableLambda
from langchain_core.prompts import ChatPromptTemplate

# Create retriever
retriever = AgentIndexRetriever(limit=5)

# Use in a chain
prompt = ChatPromptTemplate.from_template(
    "Based on these agents: {context}\\n\\nRecommend the best one for: {question}"
)

def format_docs(docs):
    return "\\n\\n".join([doc.page_content for doc in docs])

chain = (
    {"context": retriever | format_docs, "question": RunnableLambda(lambda x: x)}
    | prompt
    | llm  # Your LLM here
)

result = chain.invoke("web scraping automation")
"""
                }
            },
            "crewai": {
                "python": {
                    "dependencies": ["crewai", "requests"],
                    "template": """
import requests
from crewai import Agent, Task, Crew
from typing import List, Dict, Any


class AgentIndexRecruiter:
    \"\"\"Dynamically recruit agents from AgentIndex\"\"\"
    
    def __init__(self, api_url: str = "https://api.agentcrawl.dev"):
        self.api_url = api_url
    
    def discover_agents(self, need: str, limit: int = 3) -> List[Dict[str, Any]]:
        \"\"\"Discover agents matching the need\"\"\"
        try:
            response = requests.post(
                f"{self.api_url}/v1/discover",
                json={"need": need, "max_results": limit}
            )
            response.raise_for_status()
            return response.json().get("results", [])
        except Exception as e:
            print(f"Discovery failed: {e}")
            return []
    
    def create_crewai_agent(self, agent_data: Dict[str, Any]) -> Agent:
        \"\"\"Convert AgentIndex result to CrewAI Agent\"\"\"
        return Agent(
            role=agent_data.get("name", "Specialist"),
            goal=f"Execute tasks using {agent_data.get('category', 'general')} expertise",
            backstory=agent_data.get("description", "Experienced specialist agent"),
            tools=[],  # Add your tools here
            verbose=True,
            allow_delegation=True
        )
    
    def build_dynamic_crew(self, project_description: str) -> Crew:
        \"\"\"Build a crew dynamically based on project needs\"\"\"
        
        # Discover relevant agents
        agents_data = self.discover_agents(project_description, limit=3)
        
        # Convert to CrewAI agents
        agents = [self.create_crewai_agent(data) for data in agents_data]
        
        # Create tasks
        tasks = [
            Task(
                description=f"Analyze and contribute to: {project_description}",
                expected_output="Detailed analysis and recommendations",
                agent=agent
            ) for agent in agents
        ]
        
        return Crew(
            agents=agents,
            tasks=tasks,
            verbose=True,
            memory=True
        )


# Usage example
if __name__ == "__main__":
    recruiter = AgentIndexRecruiter()
    crew = recruiter.build_dynamic_crew("Build a web scraping pipeline")
    
    result = crew.kickoff()
    print(result)
""",
                    "instructions": """
1. Install dependencies: pip install crewai requests  
2. Import the AgentIndexRecruiter class
3. Initialize with API URL
4. Use build_dynamic_crew() for automatic crew creation
5. Customize agent roles and tools as needed
6. Run crew.kickoff() to execute tasks
""",
                    "example_usage": """
# Quick dynamic crew creation
recruiter = AgentIndexRecruiter()

# Build specialized crew
crew = recruiter.build_dynamic_crew("Create a data analysis dashboard")

# Execute the crew
result = crew.kickoff()

# Access individual agents if needed
for agent in crew.agents:
    print(f"Agent: {agent.role}")
    print(f"Backstory: {agent.backstory}")
"""
                }
            },
            "autogen": {
                "python": {
                    "dependencies": ["pyautogen", "requests"],
                    "template": """
import requests
from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
from typing import List, Dict, Any


class AgentIndexDiscovery:
    \"\"\"Discover agents for AutoGen conversations\"\"\"
    
    def __init__(self, api_url: str = "https://api.agentcrawl.dev"):
        self.api_url = api_url
    
    def find_specialists(self, task: str, count: int = 3) -> List[Dict[str, Any]]:
        \"\"\"Find specialist agents for the task\"\"\"
        try:
            response = requests.post(
                f"{self.api_url}/v1/discover", 
                json={"need": task, "max_results": count}
            )
            response.raise_for_status()
            return response.json().get("results", [])
        except Exception as e:
            print(f"Discovery error: {e}")
            return []
    
    def create_autogen_agents(self, task: str) -> List[AssistantAgent]:
        \"\"\"Create AutoGen agents from AgentIndex discoveries\"\"\"
        
        discoveries = self.find_specialists(task, 3)
        agents = []
        
        for i, discovery in enumerate(discoveries):
            agent = AssistantAgent(
                name=f"specialist_{i+1}",
                system_message=f\"\"\"
You are {discovery.get('name', 'a specialist agent')}.
Your expertise: {discovery.get('category', 'general')}
Background: {discovery.get('description', 'Experienced agent')}
Platform: {discovery.get('source', 'unknown')}
Trust Score: {discovery.get('trust_score', 0)}/100

Use your specialized knowledge to contribute to the conversation.
\"\"\",
                llm_config={"model": "gpt-4", "temperature": 0.7}
            )
            agents.append(agent)
        
        return agents
    
    def create_group_chat(self, task: str) -> GroupChat:
        \"\"\"Create a group chat with discovered specialists\"\"\"
        
        # Create specialist agents
        specialists = self.create_autogen_agents(task)
        
        # Add user proxy
        user_proxy = UserProxyAgent(
            name="user_proxy",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=1
        )
        
        # Create group chat
        agents = specialists + [user_proxy]
        
        return GroupChat(
            agents=agents,
            messages=[],
            max_round=10
        )


# Usage example  
if __name__ == "__main__":
    discovery = AgentIndexDiscovery()
    
    # Create specialized group chat
    group_chat = discovery.create_group_chat("web scraping automation")
    
    # Create manager
    manager = GroupChatManager(groupchat=group_chat, llm_config={"model": "gpt-4"})
    
    # Start conversation
    user_proxy = next(agent for agent in group_chat.agents if agent.name == "user_proxy")
    user_proxy.initiate_chat(
        manager, 
        message="Let's build a web scraping system for e-commerce data"
    )
""",
                    "instructions": """
1. Install dependencies: pip install pyautogen requests
2. Import AgentIndexDiscovery class  
3. Use create_group_chat() for automatic specialist discovery
4. Customize LLM config and conversation parameters
5. Use GroupChatManager to orchestrate multi-agent conversations
""",
                    "example_usage": """
# Quick specialist group creation
discovery = AgentIndexDiscovery()

# Create group with relevant specialists  
group_chat = discovery.create_group_chat("machine learning pipeline")

# Set up manager and start conversation
manager = GroupChatManager(groupchat=group_chat)
user_proxy = group_chat.agents[-1]  # Last agent is user proxy

user_proxy.initiate_chat(manager, message="Design an ML training pipeline")
"""
                }
            }
        }
    
    async def generate_integration(
        self, 
        framework: str, 
        language: str,
        agent_id: Optional[str] = None,
        custom_requirements: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate integration code for specified framework and language"""
        
        if framework not in self.templates:
            raise ValueError(f"Framework '{framework}' not supported")
        
        if language not in self.templates[framework]:
            raise ValueError(f"Language '{language}' not supported for {framework}")
        
        template_data = self.templates[framework][language]
        
        integration = {
            "framework": framework,
            "language": language,
            "code": template_data["template"].strip(),
            "dependencies": template_data["dependencies"],
            "instructions": template_data["instructions"].strip(),
            "example_usage": template_data["example_usage"].strip(),
            "generated_at": datetime.utcnow().isoformat()
        }
        
        # Add agent-specific customizations if requested
        if agent_id:
            integration["agent_id"] = agent_id
            integration["code"] = self._customize_for_agent(integration["code"], agent_id)
        
        if custom_requirements:
            integration["custom_requirements"] = custom_requirements
            integration["code"] = self._add_custom_requirements(integration["code"], custom_requirements)
        
        return integration
    
    def _customize_for_agent(self, code: str, agent_id: str) -> str:
        """Customize code for specific agent"""
        # Add agent-specific filtering
        customized = code.replace(
            'json={"need": query, "max_results": self.limit}',
            f'json={{"need": query, "max_results": self.limit, "agent_id": "{agent_id}"}}'
        )
        return customized
    
    def _add_custom_requirements(self, code: str, requirements: str) -> str:
        """Add custom requirements to the code"""
        # Add custom filtering logic
        custom_section = f'''
        
        # Custom requirements: {requirements}
        # TODO: Implement custom filtering logic based on requirements
        '''
        
        return code + custom_section
    
    def get_available_integrations(self) -> List[Dict[str, str]]:
        """Get list of available framework integrations"""
        integrations = []
        
        for framework, languages in self.templates.items():
            for language in languages.keys():
                integrations.append({
                    "framework": framework,
                    "language": language,
                    "description": f"{framework.title()} integration for {language.title()}"
                })
        
        return integrations


if __name__ == "__main__":
    # Demo the generator
    async def demo():
        generator = CodeIntegrationGenerator()
        
        print("🔧 Available Integrations:")
        for integration in generator.get_available_integrations():
            print(f"  - {integration['framework']} ({integration['language']})")
        
        print("\\n🚀 Generating LangChain integration...")
        langchain_integration = await generator.generate_integration("langchain", "python")
        
        print(f"Generated {len(langchain_integration['code'])} characters of code")
        print(f"Dependencies: {', '.join(langchain_integration['dependencies'])}")
    
    asyncio.run(demo())