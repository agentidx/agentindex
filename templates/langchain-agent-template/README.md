# {{PROJECT_NAME}}

[![Nerq Trust Score](https://nerq.ai/badge/{{PROJECT_NAME}}.svg)](https://nerq.ai/safe/{{PROJECT_NAME}})

A LangChain agent with built-in trust verification.

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env  # Add your API keys
python src/agent.py
```

## Features

- Dynamic tool discovery via [Nerq Resolve](https://nerq.ai/gateway)
- Every tool trust-verified before use
- Auto-finds the best tool for any task from 25,000+ options
- Built-in trust monitoring

## How It Works

Instead of hardcoding tools, this agent uses `nerq.resolve()` to find the best tool for each task dynamically:

```python
import nerq
tool = nerq.resolve("code review", framework="langchain", min_trust=70)
```

## Project Structure

```
src/
  agent.py    — Main agent with dynamic tool discovery
  tools.py    — Nerq-powered tool resolution
  config.py   — Configuration management
tests/
  test_agent.py — Basic tests
```

## Trust Verification

This template uses [Nerq](https://nerq.ai) for:
- **Preflight checks** — verify any agent before using it
- **Dynamic discovery** — find the best tool for any task
- **CI/CD** — automated trust checking on every PR

## CI/CD

Trust checking runs automatically on every push and PR via GitHub Actions.
See `.github/workflows/trust-check.yml`.

## License

MIT

Built with [Nerq](https://nerq.ai) — the shortcut to better AI agent results.
