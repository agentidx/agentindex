---
license: cc-by-4.0
task_categories:
  - text-classification
tags:
  - ai-agents
  - trust-scoring
  - security
  - mcp-servers
  - compliance
  - vulnerability-detection
size_categories:
  - 10K<n<100K
---

# Nerq AI Agent Trust Scores Dataset

Trust scores for 10,000+ AI agents covering security, compliance, compatibility, and community signals.
Updated weekly. Sourced from [nerq.ai](https://nerq.ai).

## Features

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Agent/tool name |
| `trust_score` | float | Nerq Trust Score (0-100) |
| `grade` | string | Letter grade (A+ to F) |
| `category` | string | Agent category |
| `known_cves` | int | Number of known CVEs |
| `license` | string | License identifier |
| `license_category` | string | PERMISSIVE / COPYLEFT / PROPRIETARY / UNKNOWN |
| `frameworks` | string | Compatible frameworks (comma-separated) |
| `npm_weekly_downloads` | int | NPM weekly download count |
| `github_stars` | int | GitHub star count |
| `github_forks` | int | GitHub fork count |
| `language` | string | Primary programming language |
| `source` | string | Source registry (github, npm, pypi, huggingface) |
| `last_updated` | date | Last source update date |
| `description` | string | Agent description (max 300 chars) |

## Trust Score Methodology

Nerq Trust Score v3 is calculated across 6 dimensions:

- **Code Quality (20%)** — description quality, CVE count, security advisories
- **Community Adoption (20%)** — stars, downloads, Stack Overflow questions, Reddit mentions
- **Compliance (15%)** — license type, EU AI Act risk classification
- **Operational Health (15%)** — recency, issue close rate, maintenance activity
- **Security (15%)** — CVE count, OpenSSF Scorecard, OSV.dev cross-reference
- **External Validation (15%)** — third-party assessments, community signals, citations

## Data Sources

13+ independent data sources including GitHub, npm, PyPI, HuggingFace, OpenSSF Scorecard, OSV.dev, NVD, Stack Overflow, and Reddit.

## Usage

```python
import pandas as pd
df = pd.read_csv("agents_trust_scores.csv")
safe_agents = df[df["trust_score"] >= 70]
print(f"{len(safe_agents)} agents with trust score >= 70")
```

## Citation

```
@dataset{nerq_trust_scores_2026,
  title={Nerq AI Agent Trust Scores},
  author={Nilsson, Anders},
  year={2026},
  url={https://nerq.ai},
  license={CC-BY-4.0}
}
```

## Updates

This dataset is updated weekly by the Nerq Intelligence pipeline. For real-time data, use the [Nerq API](https://nerq.ai/v1/preflight?target=AGENT_NAME).
