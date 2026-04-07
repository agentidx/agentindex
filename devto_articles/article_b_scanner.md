---
title: "Scan Your AI Dependencies for Vulnerabilities — One Command"
published: false
tags: [security, ai, python, opensource]
canonical_url: https://nerq.ai/?utm=devto_b
---

Most security scanning tools were built for traditional software dependencies — npm packages, pip packages, Docker images. They check CVEs, licenses, outdated versions.

AI projects have a different problem. Your dependencies aren't just libraries. They're agents, LLM clients, orchestration frameworks, and MCP servers — each with its own maintenance trajectory, security posture, and cost profile. A CVE scanner won't tell you that your LLM client has a trust score of 42.5, or that your web framework hasn't had a security commit in eight months.

Here's a scanner built for that problem.

## One Command

```bash
curl -s -X POST "https://nerq.ai/v1/scan-project" \
  -H "Content-Type: application/json" \
  -d '{
    "dependencies": [
      {"name": "langchain", "version": "0.2.0"},
      {"name": "openai", "version": "1.0.0"},
      {"name": "flask", "version": "3.0.0"}
    ]
  }' | jq .
```

```json
{
  "project_health_grade": "F",
  "project_health_score": 50.1,
  "total_dependencies": 3,
  "issues": {
    "critical": 0,
    "warnings": 2,
    "low_trust_deps": 2,
    "unscored_deps": 0
  },
  "critical_findings": [
    {
      "severity": "warning",
      "dependency": "openai",
      "trust_score": 42.5,
      "trust_grade": "E",
      "message": "openai has a low trust score (42.5)"
    },
    {
      "severity": "warning",
      "dependency": "flask",
      "trust_score": 49.8,
      "trust_grade": "D",
      "message": "flask has a low trust score (49.8)"
    }
  ],
  "cost_insight": {
    "detected_llm_providers": ["OpenAI"],
    "estimated_monthly_cost_usd": 120,
    "note": "Estimates based on moderate usage patterns."
  },
  "badge_markdown": "[![Nerq Project Health](https://nerq.ai/badge/project/F)](https://nerq.ai/scan)"
}
```

Three dependencies. Two warnings. A project health grade. An estimated monthly LLM cost. All in one API call, no account required.

## What We Found Scanning 627 Real Repos

We've run the scanner against 627 GitHub repositories over the past few months — open-source AI projects, starter templates, production tools. Here's what the data looks like.

**Grade distribution:**

| Grade | Count | % |
|-------|-------|---|
| A     | 91    | 14.5% |
| B     | 305   | 48.6% |
| C     | 198   | 31.6% |
| D     | 29    | 4.6% |
| F     | 4     | 0.6% |

The headline: 5.2% of scanned projects grade D or F. But the more interesting finding is in the dependency-level data.

Across 19,276 total dependencies scanned:

- **13,790 have no license declaration** — that's 71.5% of all deps with no clear licensing
- **3,020 were flagged as low-trust** — meaning their trust score fell below the warning threshold
- Average trust score across all scanned project dependencies: **60.5 / 100**

The no-license number is the one that tends to surprise people. Most developers assume that if a package is on GitHub or PyPI, the licensing situation is fine. In practice, a large portion of AI ecosystem packages have no LICENSE file, no SPDX identifier in `pyproject.toml`, nothing. That's a legal ambiguity problem before it's a security problem.

## The Cost Insight Layer

Something traditional scanners don't do: the API detects which LLM providers your project is talking to and estimates monthly cost.

If it finds `openai`, `anthropic`, `together`, or other provider SDKs in your deps, it attaches a cost estimate based on moderate usage patterns. For the three-dep example above, the estimate is $120/month. That's a rough number, but it's better than no number — and it surfaces the conversation early, before you're arguing about cloud bills in production.

## Adding It to CI

Generate the dep list from your lockfile and pipe it in:

```python
# generate_scan_payload.py
import json, subprocess, sys

# For pip
result = subprocess.run(['pip', 'list', '--format=json'], capture_output=True, text=True)
packages = json.loads(result.stdout)
deps = [{"name": p["name"], "version": p["version"]} for p in packages]
print(json.dumps({"dependencies": deps}))
```

```bash
# In your CI pipeline
python generate_scan_payload.py \
  | curl -s -X POST "https://nerq.ai/v1/scan-project" \
    -H "Content-Type: application/json" \
    -d @- \
  | jq '.project_health_grade'
```

Gate your build on the result:

```bash
GRADE=$(python generate_scan_payload.py \
  | curl -s -X POST "https://nerq.ai/v1/scan-project" \
    -H "Content-Type: application/json" -d @- \
  | jq -r '.project_health_grade')

if [ "$GRADE" = "F" ] || [ "$GRADE" = "D" ]; then
  echo "Project health grade $GRADE — review dependencies before merging"
  exit 1
fi
```

## What the Grades Mean

Grades are based on the aggregate trust score of your dependency tree, weighted by how central each dependency is to the project. A single low-trust LLM client matters more than a low-trust date formatter.

The grades are not a guarantee of safety or a rejection of useful tools. Grade D doesn't mean "don't use this" — it means "this tool has limited maintenance signals, sparse documentation, and no clear security track record." That's useful information. You might use it anyway. You should probably know.

## Add the Badge to Your README

```markdown
[![Nerq Project Health](https://nerq.ai/badge/project/B)](https://nerq.ai/scan)
```

Every scan returns a ready-to-paste badge. It signals to contributors and users that you're tracking dependency health — and it auto-updates as the underlying trust scores change.

**[Run a scan at nerq.ai/scan](https://nerq.ai/?utm=devto_b)** — free, no account needed, works with `requirements.txt`, `package.json`, `pyproject.toml` or a raw JSON dep list.
