"""
CrewAI Integration Package for AgentIndex
npm: @agentidx/crewai-discovery
pip: agentcrawl-crewai

Provides seamless integration with CrewAI for discovering and building agent crews.
Budget-optimized with smart agent selection and local LLM routing.
"""

from typing import List, Dict, Any, Optional, Union
import requests
import json
from dataclasses import dataclass
from enum import Enum

class AgentRole(Enum):
    """Common agent roles in CrewAI teams."""
    RESEARCHER = "researcher"
    ANALYZER = "analyzer" 
    WRITER = "writer"
    COORDINATOR = "coordinator"
    SPECIALIST = "specialist"
    REVIEWER = "reviewer"

@dataclass
class AgentProfile:
    """Profile for an agent discovered from AgentIndex."""
    id: str
    name: str
    description: str
    capabilities: List[str]
    trust_score: float
    protocols: List[str]
    category: str
    source_url: Optional[str] = None
    invocation: Optional[Dict] = None
    suggested_role: Optional[AgentRole] = None
    
class AgentIndexCrewBuilder:
    """
    CrewAI integration that discovers and builds agent crews from AgentIndex.
    Uses smart routing to minimize API costs while maximizing agent quality.
    """
    
    def __init__(
        self, 
        api_url: str = "https://api.agentcrawl.dev/v1/discover",
        api_key: Optional[str] = None,
        min_trust_score: float = 65.0
    ):
        self.api_url = api_url
        self.api_key = api_key
        self.min_trust_score = min_trust_score
        self._local_llm_available = self._check_local_llm()
        
    def _check_local_llm(self) -> bool:
        """Check if local LLM is available for cost optimization."""
        try:
            response = requests.get("http://localhost:11434/api/version", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def discover_agents(
        self, 
        task_description: str, 
        max_agents: int = 10,
        categories: Optional[List[str]] = None,
        protocols: Optional[List[str]] = None
    ) -> List[AgentProfile]:
        """
        Discover agents suitable for a given task.
        
        Args:
            task_description: Description of the overall task or project
            max_agents: Maximum number of agents to return
            categories: Filter by specific categories
            protocols: Filter by specific protocols (mcp, npm, pip, etc.)
            
        Returns:
            List of AgentProfile objects
        """
        
        payload = {
            "need": task_description,
            "max_results": max_agents,
            "min_quality": self.min_trust_score,
        }
        
        if categories:
            payload["category"] = categories[0]  # API supports single category
            
        if protocols:
            payload["protocols"] = protocols
            
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
            
            # Convert to AgentProfile objects
            profiles = []
            for agent in agents:
                profile = AgentProfile(
                    id=agent.get("id", ""),
                    name=agent.get("name", ""),
                    description=agent.get("description", ""),
                    capabilities=agent.get("capabilities", []),
                    trust_score=agent.get("trust_score", 0),
                    protocols=agent.get("protocols", []),
                    category=agent.get("category", ""),
                    source_url=agent.get("source_url"),
                    invocation=agent.get("invocation"),
                    suggested_role=self._suggest_role(agent)
                )
                profiles.append(profile)
                
            return profiles
            
        except Exception as e:
            print(f"Agent discovery error: {e}")
            return []
    
    def _suggest_role(self, agent: Dict[str, Any]) -> Optional[AgentRole]:
        """Suggest a CrewAI role based on agent capabilities and category."""
        
        name = agent.get("name", "").lower()
        description = agent.get("description", "").lower()
        category = agent.get("category", "").lower()
        capabilities = [c.lower() for c in agent.get("capabilities", [])]
        
        # Role mapping based on keywords
        role_keywords = {
            AgentRole.RESEARCHER: ["research", "search", "gather", "collect", "crawl", "scrape"],
            AgentRole.ANALYZER: ["analyze", "process", "parse", "extract", "classify", "evaluate"],
            AgentRole.WRITER: ["write", "generate", "create", "compose", "draft", "content"],
            AgentRole.COORDINATOR: ["coordinate", "manage", "orchestrate", "workflow", "pipeline"],
            AgentRole.SPECIALIST: ["specialized", "expert", "specific", "domain", "niche"],
            AgentRole.REVIEWER: ["review", "validate", "check", "verify", "quality", "assess"]
        }
        
        # Score each role based on keyword matches
        role_scores = {}
        text_to_check = f"{name} {description} {category} {' '.join(capabilities)}"
        
        for role, keywords in role_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text_to_check)
            if score > 0:
                role_scores[role] = score
        
        # Return the highest scoring role
        if role_scores:
            return max(role_scores.items(), key=lambda x: x[1])[0]
        
        return AgentRole.SPECIALIST  # Default fallback
    
    def build_crew_for_task(
        self, 
        task_description: str,
        desired_roles: Optional[List[AgentRole]] = None,
        crew_size: int = 3
    ) -> Dict[str, Any]:
        """
        Build a complete crew configuration for a specific task.
        
        Args:
            task_description: Description of the task the crew should accomplish
            desired_roles: Specific roles needed (if None, will auto-suggest)
            crew_size: Target number of agents in the crew
            
        Returns:
            Dictionary with crew configuration and implementation guide
        """
        
        # Discover agents for the task
        agents = self.discover_agents(task_description, max_agents=crew_size * 2)
        
        if not agents:
            return {
                "error": "No suitable agents found for this task",
                "suggestion": "Try broadening your task description or lowering trust score requirements"
            }
        
        # If no specific roles requested, analyze task to suggest roles
        if desired_roles is None:
            desired_roles = self._analyze_task_for_roles(task_description)
        
        # Select best agents for each role
        selected_crew = self._select_optimal_crew(agents, desired_roles, crew_size)
        
        # Generate crew configuration
        crew_config = self._generate_crew_config(selected_crew, task_description)
        
        # Generate implementation code
        implementation = self._generate_implementation_guide(selected_crew, task_description)
        
        return {
            "crew": selected_crew,
            "config": crew_config,
            "implementation": implementation,
            "task_description": task_description,
            "estimated_setup_time": self._estimate_setup_time(selected_crew)
        }
    
    def _analyze_task_for_roles(self, task_description: str) -> List[AgentRole]:
        """Analyze task description to suggest needed roles."""
        
        if self._local_llm_available:
            return self._analyze_task_with_local_llm(task_description)
        else:
            return self._analyze_task_with_rules(task_description)
    
    def _analyze_task_with_local_llm(self, task_description: str) -> List[AgentRole]:
        """Use local LLM to analyze task and suggest roles."""
        try:
            prompt = f"""Task: {task_description}

Suggest 2-4 agent roles needed for this task from:
- researcher: gathering information
- analyzer: processing/analyzing data  
- writer: creating content/reports
- coordinator: managing workflow
- specialist: domain expertise
- reviewer: quality control

Respond with only role names, one per line."""

            payload = {
                "model": "llama3.2:3b",
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 100, "temperature": 0.1}
            }
            
            response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                roles_text = result.get("response", "").strip().lower()
                
                suggested_roles = []
                for line in roles_text.split('\n'):
                    line = line.strip()
                    for role in AgentRole:
                        if role.value in line:
                            suggested_roles.append(role)
                            break
                
                return suggested_roles[:4]  # Max 4 roles
                
        except Exception:
            pass
        
        # Fallback to rule-based
        return self._analyze_task_with_rules(task_description)
    
    def _analyze_task_with_rules(self, task_description: str) -> List[AgentRole]:
        """Rule-based task analysis for role suggestions."""
        
        task_lower = task_description.lower()
        suggested_roles = []
        
        # Common patterns
        if any(word in task_lower for word in ["research", "find", "gather", "collect"]):
            suggested_roles.append(AgentRole.RESEARCHER)
            
        if any(word in task_lower for word in ["analyze", "process", "evaluate", "assess"]):
            suggested_roles.append(AgentRole.ANALYZER)
            
        if any(word in task_lower for word in ["write", "create", "generate", "compose"]):
            suggested_roles.append(AgentRole.WRITER)
            
        if any(word in task_lower for word in ["manage", "coordinate", "organize", "workflow"]):
            suggested_roles.append(AgentRole.COORDINATOR)
            
        # Default fallback
        if not suggested_roles:
            suggested_roles = [AgentRole.RESEARCHER, AgentRole.ANALYZER, AgentRole.WRITER]
        
        return suggested_roles[:3]  # Max 3 roles for rule-based
    
    def _select_optimal_crew(
        self, 
        agents: List[AgentProfile], 
        desired_roles: List[AgentRole], 
        crew_size: int
    ) -> List[AgentProfile]:
        """Select optimal combination of agents for desired roles."""
        
        # Group agents by suggested role
        agents_by_role = {}
        for agent in agents:
            role = agent.suggested_role or AgentRole.SPECIALIST
            if role not in agents_by_role:
                agents_by_role[role] = []
            agents_by_role[role].append(agent)
        
        # Sort agents within each role by trust score
        for role_agents in agents_by_role.values():
            role_agents.sort(key=lambda x: x.trust_score, reverse=True)
        
        # Select best agent for each desired role
        selected_crew = []
        used_agents = set()
        
        for role in desired_roles:
            if role in agents_by_role and len(selected_crew) < crew_size:
                for agent in agents_by_role[role]:
                    if agent.id not in used_agents:
                        selected_crew.append(agent)
                        used_agents.add(agent.id)
                        break
        
        # Fill remaining spots with highest trust score agents
        remaining_agents = [a for a in agents if a.id not in used_agents]
        remaining_agents.sort(key=lambda x: x.trust_score, reverse=True)
        
        while len(selected_crew) < crew_size and remaining_agents:
            selected_crew.append(remaining_agents.pop(0))
        
        return selected_crew
    
    def _generate_crew_config(self, crew: List[AgentProfile], task: str) -> Dict[str, Any]:
        """Generate CrewAI configuration for the selected crew."""
        
        config = {
            "task": task,
            "agents": [],
            "tasks": [],
            "process": "sequential"  # Default process
        }
        
        for i, agent in enumerate(crew):
            agent_config = {
                "role": agent.suggested_role.value if agent.suggested_role else "specialist",
                "goal": f"Execute {agent.suggested_role.value if agent.suggested_role else 'specialist'} tasks for: {task}",
                "backstory": agent.description[:200],  # Truncate for backstory
                "agent_source": {
                    "agentindex_id": agent.id,
                    "name": agent.name,
                    "trust_score": agent.trust_score,
                    "protocols": agent.protocols
                },
                "tools": self._suggest_tools_for_agent(agent)
            }
            config["agents"].append(agent_config)
            
            # Create corresponding task
            task_config = {
                "description": f"Use {agent.name} to {agent.suggested_role.value if agent.suggested_role else 'process'} information for: {task}",
                "agent": i,  # Reference to agent by index
                "expected_output": f"Processed results from {agent.name}"
            }
            config["tasks"].append(task_config)
        
        return config
    
    def _suggest_tools_for_agent(self, agent: AgentProfile) -> List[str]:
        """Suggest CrewAI tools based on agent capabilities."""
        
        tools = []
        capabilities = [c.lower() for c in agent.capabilities]
        
        # Map capabilities to CrewAI tools
        if any("search" in cap or "web" in cap for cap in capabilities):
            tools.append("WebSearchTool")
            
        if any("file" in cap or "read" in cap for cap in capabilities):
            tools.append("FileReadTool")
            
        if any("scrape" in cap or "crawl" in cap for cap in capabilities):
            tools.append("ScrapeWebsiteTool")
            
        if any("code" in cap or "python" in cap for cap in capabilities):
            tools.append("CodeExecutorTool")
        
        # Default tool
        if not tools:
            tools.append("BasicTool")
        
        return tools
    
    def _generate_implementation_guide(self, crew: List[AgentProfile], task: str) -> str:
        """Generate implementation guide for the crew."""
        
        guide_parts = [
            "# CrewAI Implementation Guide",
            f"# Task: {task}",
            "",
            "## Setup Instructions",
            ""
        ]
        
        # Installation instructions
        guide_parts.extend([
            "### 1. Install CrewAI",
            "pip install crewai",
            "",
            "### 2. Install AgentIndex Agents",
            ""
        ])
        
        for agent in crew:
            if agent.invocation:
                if agent.invocation.get("type") == "npm":
                    guide_parts.append(f"npm install {agent.invocation.get('name', agent.name)}")
                elif agent.invocation.get("type") == "pip":
                    guide_parts.append(f"pip install {agent.invocation.get('name', agent.name)}")
                elif agent.invocation.get("type") == "github":
                    guide_parts.append(f"git clone {agent.invocation.get('url', '')}")
            else:
                guide_parts.append(f"# {agent.name}: Check {agent.source_url or 'documentation'} for setup")
        
        guide_parts.extend([
            "",
            "### 3. Basic CrewAI Implementation",
            "",
            "```python",
            "from crewai import Agent, Task, Crew",
            "",
            "# Define agents based on AgentIndex discoveries",
        ])
        
        # Generate agent definitions
        for i, agent in enumerate(crew):
            role = agent.suggested_role.value if agent.suggested_role else "specialist"
            guide_parts.extend([
                f"agent_{i+1} = Agent(",
                f"    role='{role}',",
                f"    goal='Execute {role} tasks for the project',",
                f"    backstory='{agent.description[:100]}...',",
                f"    # Integration with {agent.name} (Trust: {agent.trust_score}/100)",
                f"    tools=[],  # Add your tools here",
                ")",
                ""
            ])
        
        # Generate task definitions
        guide_parts.append("# Define tasks")
        for i, agent in enumerate(crew):
            guide_parts.extend([
                f"task_{i+1} = Task(",
                f"    description='Use {agent.name} for {task}',",
                f"    agent=agent_{i+1}",
                ")",
                ""
            ])
        
        # Generate crew setup
        agent_refs = ", ".join([f"agent_{i+1}" for i in range(len(crew))])
        task_refs = ", ".join([f"task_{i+1}" for i in range(len(crew))])
        
        guide_parts.extend([
            "# Create and run crew",
            f"crew = Crew(",
            f"    agents=[{agent_refs}],",
            f"    tasks=[{task_refs}],",
            f"    process='sequential'",
            ")",
            "",
            "result = crew.kickoff()",
            "print(result)",
            "```",
            "",
            "## Next Steps",
            "1. Customize agent tools based on specific needs",
            "2. Configure integrations with discovered agents", 
            "3. Test the crew with sample data",
            "4. Optimize task dependencies and process flow"
        ])
        
        return "\n".join(guide_parts)
    
    def _estimate_setup_time(self, crew: List[AgentProfile]) -> str:
        """Estimate setup time for the crew."""
        
        base_time = 30  # Base setup time in minutes
        agent_time = len(crew) * 15  # 15 min per agent
        
        # Add complexity based on protocols
        complexity_time = 0
        for agent in crew:
            if "mcp" in agent.protocols:
                complexity_time += 10  # MCP setup
            elif "npm" in agent.protocols or "pip" in agent.protocols:
                complexity_time += 5   # Package installation
            else:
                complexity_time += 15  # Custom integration
        
        total_minutes = base_time + agent_time + complexity_time
        
        if total_minutes < 60:
            return f"{total_minutes} minutes"
        else:
            hours = total_minutes // 60
            minutes = total_minutes % 60
            return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"

# Example usage functions
def quick_crew_for_task(task_description: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """Quick function to build a crew for a task."""
    builder = AgentIndexCrewBuilder(api_key=api_key)
    return builder.build_crew_for_task(task_description)

def discover_agents_by_category(category: str, api_key: Optional[str] = None) -> List[AgentProfile]:
    """Quick function to discover agents by category."""
    builder = AgentIndexCrewBuilder(api_key=api_key)
    return builder.discover_agents(f"agents for {category}", categories=[category])

# Export main classes
__all__ = ["AgentIndexCrewBuilder", "AgentProfile", "AgentRole", "quick_crew_for_task", "discover_agents_by_category"]

# Package metadata
__version__ = "1.0.0"
__description__ = "CrewAI integration for AgentIndex - AI agent crew building and discovery"
__author__ = "AgentIndex Team"
__email__ = "hello@agentcrawl.dev"