# agent-security

**Know if your AI dependencies are safe. One command.**

```bash
pip install agent-security
agent-security scan requirements.txt
```

Scans all your AI agent dependencies against Nerq's trust database of 204,000+ agents.
Checks for CVEs, license issues, maintenance status, and overall trust score.

## Output

```
agent-security scan: requirements.txt
Scanned 12 dependencies

  OK  langchain: Trust 88 (A), MIT
  OK  openai: Trust 91 (A+), MIT
  !!  some-agent: Trust 48 (C), 1 CVE(s), no license
  !!  risky-tool: Trust 29 (D), 2 CVE(s), AGPL

Summary: 10 trusted, 1 warning(s), 1 critical

Run 'agent-security fix requirements.txt' for improvement recommendations.
```

## Commands

### scan

```bash
agent-security scan requirements.txt
agent-security scan package.json
agent-security scan pyproject.toml
agent-security scan requirements.txt --ci  # exits 1 if critical issues
```

### fix

```bash
agent-security fix requirements.txt
```

Shows specific recommendations for each problematic dependency:
- Alternative packages with higher trust scores
- CVE details and update suggestions

### check

```bash
agent-security check langchain
agent-security check auto-gpt
```

Check trust for a single package.

### badge

```bash
agent-security badge my-project
```

Generates markdown for a Nerq trust badge to add to your README.

### ci

```bash
agent-security ci
```

Outputs a ready-to-use GitHub Action YAML for automated trust checking on every PR.

## Supported files

- `requirements.txt` — Python dependencies
- `package.json` — Node.js dependencies
- `pyproject.toml` — Python project dependencies

## How it works

agent-security calls the [Nerq API](https://nerq.ai/v1/preflight) for each dependency.
Every package is scored on:

- **Security** — Known CVEs and vulnerability history
- **Maintenance** — Update frequency, issue response time
- **Popularity** — Stars, downloads, community size
- **License** — SPDX compliance, commercial friendliness
- **Ecosystem** — Framework compatibility, integration quality

No API key required. Free to use.

## CI Integration

Add to `.github/workflows/trust-check.yml`:

```yaml
name: Agent Security Check
on: [push, pull_request]

jobs:
  trust-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install agent-security
      - run: agent-security scan requirements.txt --ci
```

## License

MIT
