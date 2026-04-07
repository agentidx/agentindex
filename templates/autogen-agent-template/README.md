# {{PROJECT_NAME}}

[![Nerq Trust Score](https://nerq.ai/badge/{{PROJECT_NAME}}.svg)](https://nerq.ai/safe/{{PROJECT_NAME}})

An AutoGen agent with built-in trust verification.

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
python src/agent.py
```

## Features

- Dynamic tool discovery via [Nerq Resolve](https://nerq.ai/gateway)
- Trust-verified tool registration
- Auto-finds the best tool for any task from 25,000+ options

## How It Works

```python
import nerq
tool = nerq.resolve("code review", framework="autogen", min_trust=70)
```

Built with [Nerq](https://nerq.ai) — the shortcut to better AI agent results.
