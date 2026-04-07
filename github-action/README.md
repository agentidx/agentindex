# Nerq Trust Check — GitHub Action

Verify AI agent and dependency trust scores in your CI/CD pipeline.

## Usage

```yaml
- name: Check agent trust scores
  uses: nerq-ai/nerq-trust-check@v1
  with:
    agents: "langchain,autogpt,crewai"
    min-score: 60
    fail-on-critical-cve: true

- name: Scan requirements.txt
  uses: nerq-ai/nerq-trust-check@v1
  with:
    requirements-file: "requirements.txt"
    min-score: 70
```

## Inputs

| Input | Description | Default |
|-------|-------------|---------|
| `agents` | Comma-separated agent names | |
| `requirements-file` | Path to requirements.txt or package.json | |
| `min-score` | Minimum trust score (0-100) | `60` |
| `fail-on-cve` | Fail if any CVE found | `false` |
| `fail-on-critical-cve` | Fail if CRITICAL CVE found | `true` |

## Outputs

| Output | Description |
|--------|-------------|
| `results` | JSON array of check results |
| `passed` | `true` if all checks passed |
| `agents-checked` | Number of agents checked |
