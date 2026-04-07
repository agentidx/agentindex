---
title: "I Built a Browser Extension That Shows Trust Scores on npm, PyPI, and GitHub"
published: false
tags: ["security", "opensource", "webdev", "ai"]
cover_image_description: "A browser showing an npm package page with a floating trust score badge overlay in the corner, green for safe, red for risky."
---

I keep catching myself installing packages I know nothing about. Last month I added an LLM wrapper from npm that had 200 stars and no license file. Turns out it was abandoned, had three unpatched CVEs, and was pulling in a dependency with a known supply chain compromise. I only found out because a colleague happened to mention it.

The AI tooling ecosystem is growing faster than anyone can audit. There are 5 million+ AI assets out there — agents, MCP servers, LangChain tools, Hugging Face models — and most developers evaluate them by star count and README quality. That is not a security strategy.

So I built a browser extension that surfaces trust scores inline, right where you make decisions.

## How It Works

The Nerq browser extension detects when you are viewing a package on npm, PyPI, or a GitHub repository. It sends only the package name to the nerq.ai API, retrieves its trust score, and renders a small badge overlay on the page. No browsing data, no telemetry, no tracking — just a name lookup.

The trust score is a 0-100 composite calculated from:

- **Maintenance signals**: commit recency, release cadence, issue response time
- **Security posture**: known CVEs, dependency audit results, license type
- **Community health**: contributor count, fork-to-star ratio, documentation quality
- **Compliance metadata**: EU AI Act risk classification, GDPR data handling declarations

Each package gets a letter grade (A+ through F) and a recommendation: PROCEED, CAUTION, or DENY.

## What You See

When you visit a page like `npmjs.com/package/some-agent-tool`, a small badge appears showing:

- Trust score (e.g., 74/100)
- Grade (e.g., B+)
- Color-coded: green for PROCEED, amber for CAUTION, red for DENY

Click the badge to expand a detail panel with the full breakdown: maintenance score, security flags, license info, and links to safer alternatives if the score is low.

On GitHub, the extension also checks the repo's associated packages. If a repo publishes to npm and PyPI, you get scores for both.

## Installation

The extension is available as a Chrome/Edge extension (Manifest V3). Install it from the [Chrome Web Store](https://nerq.ai/extension) or load it unpacked for development:

1. Clone the repo or download the latest release
2. Go to `chrome://extensions`, enable Developer mode
3. Click "Load unpacked" and select the extension directory
4. Navigate to any npm, PyPI, or GitHub page — the badge appears automatically

## Privacy

The extension sends only the package name to `nerq.ai/v1/preflight`. No cookies, no page content, no user identifiers. The full privacy policy is embedded in the extension manifest and available at [nerq.ai/privacy](https://nerq.ai/privacy).

## Why This Matters

Supply chain attacks are not theoretical. The 2024 xz backdoor, the ua-parser-js hijack, the event-stream incident — these all targeted packages that developers trusted implicitly. Trust should not be implicit. It should be measurable.

I wanted the friction to be zero. You do not need to change your workflow. You do not need to run a CLI tool or check a dashboard. The score is just there, on the page, when you are making the decision.

## What's Next

I am working on deeper integration: hover tooltips for dependencies listed in `package.json` and `requirements.txt` files on GitHub, and a sidebar panel that shows the trust profile of every dependency in a repo's lockfile.

If you want to try it, head to [nerq.ai](https://nerq.ai) or install the extension directly. The trust score API is free and open — no auth required.

---

*Nerq indexes 5M+ AI assets with trust scores. Available as a browser extension, VS Code extension, GitHub App, MCP Server, and API. [nerq.ai](https://nerq.ai)*
