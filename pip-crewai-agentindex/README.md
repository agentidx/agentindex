# agentindex-crewai

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
