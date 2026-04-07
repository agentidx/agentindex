---
title: "Adding Trust Score Checks to Your CI/CD Pipeline"
published: false
tags: ["cicd", "security", "devops", "ai"]
cover_image_description: "A terminal window showing a GitHub Actions workflow log with a Nerq preflight check step, displaying trust scores for three packages with green checkmarks and one red X."
---

Your CI pipeline runs linters, tests, and type checkers. But it does not tell you if the AI package someone just added to `requirements.txt` has a trust score of 29 and two unpatched CVEs. Adding a trust score check takes five minutes and catches problems before they reach production.

Here is how to add Nerq's preflight API to your CI/CD pipeline.

## The Preflight API

Nerq exposes a simple REST endpoint for trust verification:

```bash
curl "https://nerq.ai/v1/preflight?target=langchain"
```

Response:

```json
{
  "target": "langchain",
  "trust_score": 82,
  "grade": "A",
  "recommendation": "PROCEED",
  "risk_level": "low",
  "known_cves": 0,
  "license": "MIT",
  "last_commit_days_ago": 2,
  "alternatives": [],
  "response_time_ms": 12.3
}
```

No API key required. No authentication. The endpoint supports CORS and returns results in under 50ms for cached queries.

For multiple packages, use the batch endpoint:

```bash
curl -X POST "https://nerq.ai/v1/preflight/batch" \
  -H "Content-Type: application/json" \
  -d '{"targets": ["langchain", "openai", "sketchy-agent"]}'
```

The batch endpoint handles up to 50 packages per request.

## GitHub Actions Integration

Here is a workflow step that checks all Python dependencies and fails if any score below a threshold:

```yaml
# .github/workflows/trust-check.yml
name: Dependency Trust Check
on:
  pull_request:
    paths:
      - 'requirements*.txt'
      - 'pyproject.toml'

jobs:
  trust-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Extract dependencies
        id: deps
        run: |
          # Extract package names from requirements.txt
          PACKAGES=$(grep -v '^#' requirements.txt | sed 's/[>=<].*//' | tr '\n' ',' | sed 's/,$//')
          echo "packages=$PACKAGES" >> $GITHUB_OUTPUT

      - name: Nerq Preflight Check
        run: |
          THRESHOLD=50
          FAILED=0
          IFS=',' read -ra PKGS <<< "${{ steps.deps.outputs.packages }}"
          for pkg in "${PKGS[@]}"; do
            pkg=$(echo "$pkg" | xargs)  # trim whitespace
            [ -z "$pkg" ] && continue
            RESULT=$(curl -s "https://nerq.ai/v1/preflight?target=$pkg")
            SCORE=$(echo "$RESULT" | jq -r '.trust_score // 0')
            GRADE=$(echo "$RESULT" | jq -r '.grade // "?"')
            REC=$(echo "$RESULT" | jq -r '.recommendation // "UNKNOWN"')
            echo "$pkg: $SCORE/100 ($GRADE) — $REC"
            if [ "$SCORE" -lt "$THRESHOLD" ]; then
              echo "::error::$pkg has trust score $SCORE (below threshold $THRESHOLD)"
              FAILED=1
            fi
          done
          if [ "$FAILED" -eq 1 ]; then
            echo "::error::One or more dependencies failed the trust check."
            exit 1
          fi
```

This workflow runs on every PR that modifies dependency files. It extracts package names, queries the preflight API for each one, and fails the check if any score falls below the threshold.

## Shell Script for Any CI System

Not on GitHub Actions? Here is a standalone script that works with any CI:

```bash
#!/bin/bash
# trust-check.sh — fail if any dependency scores below threshold
THRESHOLD=${1:-50}
FAILED=0

while IFS= read -r line; do
  pkg=$(echo "$line" | sed 's/[>=<].*//' | xargs)
  [ -z "$pkg" ] || [[ "$pkg" == \#* ]] && continue

  result=$(curl -s "https://nerq.ai/v1/preflight?target=$pkg")
  score=$(echo "$result" | jq -r '.trust_score // 0')
  grade=$(echo "$result" | jq -r '.grade // "?"')
  rec=$(echo "$result" | jq -r '.recommendation // "UNKNOWN"')

  if [ "$score" -lt "$THRESHOLD" ]; then
    echo "FAIL: $pkg — $score/100 ($grade) $rec"
    FAILED=1
  else
    echo "OK:   $pkg — $score/100 ($grade) $rec"
  fi
done < requirements.txt

exit $FAILED
```

Run it in any CI: `bash trust-check.sh 50`

## npm / Node.js Variant

For `package.json`, extract dependencies with `jq`:

```bash
PACKAGES=$(jq -r '.dependencies // {} | keys[]' package.json)
for pkg in $PACKAGES; do
  curl -s "https://nerq.ai/v1/preflight?target=$pkg" | \
    jq -r '"  \(.target): \(.trust_score)/100 (\(.grade)) — \(.recommendation)"'
done
```

## What the API Returns

Each preflight response includes:

- **trust_score**: 0-100 composite score
- **grade**: A+ through F
- **recommendation**: PROCEED (score >= 60), CAUTION (40-59), DENY (below 40)
- **risk_level**: low, medium, high
- **known_cves**: count of known vulnerabilities
- **license**: detected license type
- **alternatives**: higher-scored packages in the same category (when score is low)

## Try It Now

Pick a package and run the curl command. No signup, no API key:

```bash
curl "https://nerq.ai/v1/preflight?target=your-package-here"
```

Add the GitHub Actions step to your next PR and see what your dependency tree actually looks like from a trust perspective.

---

*Nerq indexes 5M+ AI assets with trust scores. Available as a browser extension, VS Code extension, GitHub App, MCP Server, and API. [nerq.ai](https://nerq.ai)*
