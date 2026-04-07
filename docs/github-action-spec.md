# Nerq Trust Badge — GitHub Action Spec

## Overview

A GitHub Action that automatically adds a Nerq Trust Badge to repository READMEs, showing the agent's trust score from the Nerq index.

## Badge Endpoint

```
https://nerq.ai/badge/{AGENT_NAME}
```

Returns `image/svg+xml`. Cached 1 hour. CORS enabled.

### Variants

| Endpoint | Use case |
|---|---|
| `/badge/{name}` | Lookup by agent name |
| `/badge/npm/{package}` | npm packages |
| `/badge/pypi/{package}` | PyPI packages |

## Action: `nerq/trust-badge-action`

### Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `agent-name` | No | Repository name | Agent name as indexed by Nerq |
| `readme-path` | No | `README.md` | Path to README file |
| `badge-style` | No | `flat` | Badge style (flat only for now) |
| `position` | No | `top` | Where to insert: `top`, `after-title`, or `marker` |
| `marker` | No | `<!-- nerq-badge -->` | HTML comment marker for badge placement |
| `link-to-kya` | No | `true` | Wrap badge in link to KYA report |

### Example Usage

```yaml
name: Update Nerq Trust Badge
on:
  schedule:
    - cron: '0 6 * * 1'  # Weekly on Monday
  workflow_dispatch:

jobs:
  badge:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Add Nerq Trust Badge
        uses: nerq/trust-badge-action@v1
        with:
          agent-name: ${{ github.event.repository.name }}
          position: after-title

      - name: Commit changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git diff --quiet || (git add README.md && git commit -m "chore: update Nerq trust badge" && git push)
```

### What It Does

1. Reads the README file
2. Fetches the current trust score from `https://nerq.ai/v1/agent/kya/{agent-name}`
3. Inserts or updates the badge markdown:
   ```markdown
   [![Nerq Trust](https://nerq.ai/badge/AGENT_NAME)](https://nerq.ai/kya/AGENT_NAME)
   ```
4. If `position: marker`, looks for `<!-- nerq-badge -->` comment and places badge after it
5. If `position: after-title`, finds the first `# ` heading and inserts badge on the next line
6. If `position: top`, prepends badge to the file

### Manual Integration

No action needed — just add this to your README:

**Markdown:**
```markdown
[![Nerq Trust](https://nerq.ai/badge/YOUR_AGENT)](https://nerq.ai/kya/YOUR_AGENT)
```

**HTML:**
```html
<a href="https://nerq.ai/kya/YOUR_AGENT"><img src="https://nerq.ai/badge/YOUR_AGENT" alt="Nerq Trust"></a>
```

**reStructuredText:**
```rst
.. image:: https://nerq.ai/badge/YOUR_AGENT
   :target: https://nerq.ai/kya/YOUR_AGENT
   :alt: Nerq Trust
```

## Implementation Notes

- The action shell script is ~50 lines (curl + sed)
- No Docker required — runs directly on ubuntu-latest
- Badge SVG is served with `Cache-Control: public, max-age=3600`
- If agent not found, badge shows "unknown" in gray — no error
- The action is idempotent: running it twice produces the same result
