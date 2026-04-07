# create-nerq-agent

**Scaffold a trust-verified AI agent project in seconds.**

```bash
npx create-nerq-agent my-agent
```

Generates a complete agent project with your choice of framework, Nerq trust verification, GitHub Actions CI, and machine discovery built in.

## What you get

```
my-agent/
├── README.md              # With Nerq trust badge
├── requirements.txt       # Framework + nerq
├── .github/
│   └── workflows/
│       └── trust-check.yml  # GitHub Action for trust checking
├── .well-known/
│   └── agent.json         # Machine discovery (A2A protocol)
├── llms.txt               # AI-readable description
├── src/
│   ├── agent.py           # Framework boilerplate
│   └── tools.py           # Dynamic tool discovery via nerq.resolve()
├── nerq.config.json       # Trust verification config
└── LICENSE
```

## Frameworks

- **LangChain** — Full agent with tools and memory
- **CrewAI** — Multi-agent crew setup
- **AutoGen** — Conversational agent framework
- **LlamaIndex** — RAG and data agent
- **Custom** — Minimal OpenAI setup

## Dynamic tool discovery

The generated `tools.py` uses `nerq.resolve()` to find the best tools for any task at runtime:

```python
import nerq

# Find the best tool for a task
tool = nerq.resolve("search github repos")
# Returns: github-mcp-server (Trust: 83, Grade: A)

# Check trust before using a dependency
result = nerq.preflight("langchain")
# Returns: trust_score, grade, recommendation, CVEs
```

Every project created with create-nerq-agent makes Nerq API calls from day 1.

## Options

```bash
npx create-nerq-agent my-agent --framework langchain --skip-prompts
npx create-nerq-agent my-agent --no-badge --no-ci
```

| Flag | Description |
|------|-------------|
| `--framework <name>` | langchain, crewai, autogen, llamaindex, custom |
| `--skip-prompts` | Use defaults, no interactive prompts |
| `--no-badge` | Skip Nerq trust badge in README |
| `--no-ci` | Skip GitHub Action |
| `--no-trust` | Skip trust verification setup |

## License

MIT
