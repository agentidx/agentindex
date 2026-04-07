---
title: "Automated Dependency Trust Reports on Every PR"
published: false
tags: ["github", "security", "devops", "ai"]
cover_image_description: "A GitHub pull request comment showing a formatted trust report table with package names, trust scores, grades, and PROCEED/CAUTION/DENY recommendations."
---

Every dependency change in a pull request is a security decision. But most teams review dependency bumps by glancing at the diff in `package.json` or `requirements.txt` and clicking merge. There is no context about whether that new package is maintained, has known vulnerabilities, or even has a license.

I built a GitHub App that fixes this. Every time a PR touches a dependency file, it posts a trust report as a comment with scores, grades, and recommendations for every added or changed package.

## The Problem

Your CI pipeline checks if the code compiles and if tests pass. It does not tell you that the new `ai-agent-helper` package you just added has a trust score of 23/100, no commits in 14 months, and two unpatched CVEs. That context matters more than whether the tests are green.

## How It Works

The Nerq GitHub App watches for pull requests that modify dependency files:

- `package.json` / `package-lock.json` (npm)
- `requirements.txt` / `pyproject.toml` / `Pipfile` (Python)
- `go.mod` (Go)
- `Cargo.toml` (Rust)
- `pom.xml` / `build.gradle` (Java)

When it detects a change, it extracts the added or modified packages, batch-queries the Nerq preflight API, and posts a PR comment with a trust report.

## Example Output

Here is what the comment looks like on a PR that adds two new Python packages:

```
## Nerq Dependency Trust Report

| Package         | Score | Grade | Recommendation | Flags              |
|-----------------|-------|-------|-----------------|--------------------|
| langchain       |  82   |  A    | PROCEED         |                    |
| sketchy-agent   |  31   |  D    | DENY            | No license, 2 CVEs |

Summary: 1 of 2 packages flagged. Review sketchy-agent before merging.

Safer alternatives for sketchy-agent:
  → crewai (Score: 78, Grade: B+)
  → autogen (Score: 75, Grade: B+)
```

The report includes:

- **Trust score** (0-100) and **letter grade** (A+ to F)
- **Recommendation**: PROCEED, CAUTION, or DENY
- **Flags**: missing license, known CVEs, abandoned maintenance, excessive permissions
- **Alternatives**: higher-scored packages in the same category

## Setup

Install the GitHub App from [nerq.ai/github-app](https://nerq.ai/github-app):

1. Click "Install" and select the repositories you want to monitor
2. The app requests read access to pull requests and code (to parse dependency files) and write access to PR comments
3. That is it — no configuration file needed. The next PR that touches a dependency file gets a trust report.

You can customize behavior with a `.nerq.yml` file in your repo root:

```yaml
# .nerq.yml
threshold: 50          # Flag packages below this score
deny_below: 30         # Block merging below this score (requires branch protection)
ignore:
  - internal-package   # Skip specific packages
report_on:
  - added              # Only report on new packages (not updates)
```

## Under the Hood

The app uses the Nerq batch preflight endpoint:

```
POST https://nerq.ai/v1/preflight/batch
Content-Type: application/json

{
  "targets": ["langchain", "sketchy-agent"],
  "caller": "github-app"
}
```

Each target returns a trust score, grade, recommendation, and enrichment data including known CVEs, license info, and cheaper or safer alternatives. The batch endpoint handles up to 50 packages per request, which covers most PRs.

## Why Not Just Use Dependabot?

Dependabot alerts you to known CVEs in existing dependencies. It does not evaluate new packages being added. It does not tell you if a package is abandoned, unlicensed, or poorly maintained. The Nerq GitHub App complements Dependabot — it covers the gap between "no known CVE" and "actually trustworthy."

## Get Started

Install the app at [nerq.ai/github-app](https://nerq.ai/github-app) or try the API directly:

```bash
curl "https://nerq.ai/v1/preflight?target=langchain"
```

No API key required. Free for public repositories.

---

*Nerq indexes 5M+ AI assets with trust scores. Available as a browser extension, VS Code extension, GitHub App, MCP Server, and API. [nerq.ai](https://nerq.ai)*
