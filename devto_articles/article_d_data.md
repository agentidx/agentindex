---
title: "We Scanned 4.5 Million AI Assets — The Results Are a Wake-Up Call"
published: false
tags: [security, ai, opensource, data]
canonical_url: https://nerq.ai/?utm=devto_d
---

Over the past year we've been crawling, indexing, and scoring AI assets across every major registry: GitHub, HuggingFace, PyPI, npm, Docker Hub, and more. The index now covers 4,518,802 active assets — agents, tools, MCP servers, models, and datasets.

We computed a Trust Score for each one. Then we looked at the distribution.

It's not what you'd hope for.

## The Grade Distribution

Every asset in the index gets a letter grade based on its aggregate Trust Score. Here's where 4.5 million assets land:

| Grade | Count     | % of total |
|-------|-----------|------------|
| A+    | 32        | <0.01% |
| A     | 971       | 0.02% |
| B     | 8,891     | 0.20% |
| C     | 38,651    | 0.86% |
| D     | 4,378,026 | 96.9% |
| E     | 92,024    | 2.04% |
| F     | 164       | <0.01% |

96.9% of active AI assets in the ecosystem grade D.

That's not a sign that the scoring is too strict. The Trust Score is designed to reflect the actual signals developers use to evaluate software quality: maintenance activity, documentation, license clarity, security hygiene, community engagement. A grade-D asset has weak or absent signals across most of those dimensions.

The ecosystem is young. A large fraction of what's been published is experimental, abandoned, or thinly documented. That's not surprising. What's surprising is how concentrated the top of the distribution is: 1,003 assets at A or A+ out of 4.5 million.

## What the Score Measures

The Trust Score is a composite of five dimensions, each scored 0–100:

**Quality score** — Code structure, presence of tests, release discipline, dependency management. The average quality score across all GitHub assets in the index is 0.31 out of 100 on the raw scale. That's not a rounding error.

**Documentation score** — README completeness, presence of examples, API reference, installation instructions. Average: 0.35. In practice, 100% of GitHub repos in the index have documentation scores below 10. Many have a README that's three lines long.

**Activity score** — Commit frequency over the trailing 12 months, issue response time, contributor count. Average: 0.68. Slightly better, but still very low in absolute terms.

**Security score** — Dependency audit status, presence of a SECURITY.md, CVE history, code scanning integration. Average: 0.01. Nearly zero. The security signal is effectively absent across the index.

**Popularity score** — Stars, forks, downloads, downstream dependents. This is where the distribution is most unequal: a handful of repos have tens of thousands of stars; the median is in the low single digits.

## The License Problem

99% of all active assets in the index have no license declaration. Among higher-scored assets (trust score above 40), it's still 91% without a clear license.

This is partly a GitHub culture artifact — many developers don't add a LICENSE file because the tool is "just for personal use" or "not production-ready yet." But it becomes a problem when those tools end up in enterprise AI stacks through transitive dependencies. No license means no clear terms of use, no warranty disclaimer, no guidance on commercial use.

It also drags the trust score down. A missing license is a documentation gap and a legal ambiguity. Both are signals the scorer penalizes.

## Project-Level Scans: A Better Picture

The index-level data is bleak because it includes everything — early experiments, one-off scripts, abandoned repos. The project scan data is more optimistic because it covers repos people are actually using and updating.

We've scanned 627 real AI projects via the `/v1/scan-project` endpoint. The grade distribution there:

| Grade | Count | % |
|-------|-------|---|
| A     | 91    | 14.5% |
| B     | 305   | 48.6% |
| C     | 198   | 31.6% |
| D     | 29    | 4.6% |
| F     | 4     | 0.6% |

Average trust score across dependencies in those projects: 60.5 / 100. That's a B–/C+ range, which is not great but is meaningfully better than the index average.

Across 19,276 dependency relationships in those 627 scans:
- **13,790 deps (71.5%) have no license declaration**
- **3,020 deps were flagged as low-trust** (below the warning threshold)

The license number holds even at the project level. Active, maintained, real-world AI projects are overwhelmingly pulling in unlicensed dependencies.

## MCP Servers: A Specific Concern

The 23,745 MCP servers in the index deserve separate attention. MCP servers aren't passive libraries — they run as processes with access to whatever the user grants them: filesystems, databases, credentials, external APIs.

Their grade distribution:

| Grade | Count | % |
|-------|-------|---|
| A+ / A | 164  | 0.7% |
| B      | 1,430 | 6.0% |
| C      | 2,416 | 10.2% |
| D      | 14,414 | 60.7% |
| E      | 5,249 | 22.1% |

60.7% of MCP servers grade D. These are tools that run inside your AI assistant's context, often with broad permissions, often written quickly by individual developers experimenting with the format. Most are harmless. But "harmless" and "low-trust" are not the same thing — and the difference matters when you're granting a tool access to your filesystem.

## What This Actually Means

We're not publishing these numbers to discourage AI development. The ecosystem is early, and early ecosystems have messy quality distributions. That's normal.

The problem is the absence of visibility. Before this kind of index existed, there was no easy way to check the trust posture of an AI tool before integrating it. You could read the README, star count, and gut-feel your way to a decision. Now there's a 4.5-million-asset database with computed scores, updated continuously, with a free API.

Use it. Check the tools you depend on. Run a project scan before your next deploy. Look at the security score column — even if it's zero, knowing it's zero is information.

The index is at **[nerq.ai](https://nerq.ai/?utm=devto_d)**. Free search, free API, no account needed.

---

*Methodology note: Trust Scores are computed from publicly available signals (GitHub API, package registry metadata, documentation analysis). They are quality and maintenance signals, not security audits. A high trust score does not guarantee safety; a low trust score does not guarantee danger. The scores reflect what the data shows, not what we wish it showed.*
