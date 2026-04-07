# agentindex-langchain

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
