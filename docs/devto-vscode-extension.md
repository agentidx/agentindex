---
title: "Check AI Package Trust Scores Without Leaving VS Code"
published: false
tags: ["vscode", "security", "ai", "productivity"]
cover_image_description: "VS Code editor with a package.json file open, showing an inline trust score annotation next to a dependency name with a green checkmark and score of 82."
---

I spend most of my day in VS Code. When I add a new dependency, I do not want to switch to a browser, search for the package, check its GitHub, scan for CVEs, and then come back. I want the trust signal right there in my editor.

So I built a VS Code extension that shows trust scores for AI packages and tools inline, without breaking my flow.

## The Workflow Problem

Here is what adding a dependency usually looks like:

1. You hear about a package or an AI assistant suggests one
2. You add it to `package.json` or `requirements.txt`
3. You run `npm install` or `pip install`
4. Maybe you check the GitHub page. Maybe you do not.
5. You move on

Step 4 is where the security decision should happen, but it rarely does because it requires context-switching. By the time you have checked the repo, read the issues, and searched for CVEs, you have lost 5 minutes and your focus.

## How the Extension Works

The Nerq VS Code extension adds trust scoring directly into your editor:

**Inline annotations**: When you open a `package.json`, `requirements.txt`, `pyproject.toml`, or `go.mod` file, the extension annotates each dependency with its trust score and grade. You see the score right next to the package name as a CodeLens annotation.

**Hover details**: Hover over any dependency to see the full trust breakdown — maintenance score, security flags, license type, last commit date, and recommendation (PROCEED/CAUTION/DENY).

**Command palette**: Run "Nerq: Check Package" from the command palette to look up any package by name. Useful when you are evaluating options before adding a dependency.

**Status bar**: The status bar shows a summary for the current file — how many dependencies are in each trust tier (green/amber/red).

## Installation

Install from the VS Code Marketplace or from a `.vsix` file:

**From Marketplace:**
1. Open VS Code
2. Go to Extensions (Ctrl+Shift+X)
3. Search "Nerq Trust Score"
4. Click Install

**From .vsix (for pre-release or offline):**
1. Download the latest `.vsix` from [nerq.ai/vscode](https://nerq.ai/vscode)
2. In VS Code, open the command palette (Ctrl+Shift+P)
3. Run "Extensions: Install from VSIX..."
4. Select the downloaded file

No API key needed. The extension calls the public Nerq API.

## What You See

Open a `requirements.txt` that looks like this:

```
langchain==0.1.0
openai==1.12.0
sketchy-agent==0.0.3
```

The extension adds CodeLens annotations:

```
langchain==0.1.0        # Trust: 82/100 (A) PROCEED
openai==1.12.0          # Trust: 88/100 (A+) PROCEED
sketchy-agent==0.0.3    # Trust: 31/100 (D) DENY — 2 CVEs, no license
```

Hovering over `sketchy-agent` shows:

```
Trust Score: 31/100 (Grade: D)
Recommendation: DENY
Last commit: 14 months ago
License: None detected
Known CVEs: 2 (1 high, 1 medium)
Alternatives: crewai (78), autogen (75)
```

## Configuration

The extension is zero-config by default, but you can customize it in VS Code settings:

```json
{
  "nerq.threshold": 50,
  "nerq.showInline": true,
  "nerq.showStatusBar": true,
  "nerq.highlightDeny": true
}
```

Set `nerq.threshold` to control which score triggers a warning. Set `nerq.highlightDeny` to add a red underline to packages with a DENY recommendation.

## Privacy

The extension sends only package names to `nerq.ai/v1/preflight`. No code, no file contents, no telemetry. Requests are cached locally for 5 minutes to minimize network calls.

## Try It

Install the extension and open any dependency file. The trust scores appear automatically. If a package looks risky, hover for details and alternatives.

---

*Nerq indexes 5M+ AI assets with trust scores. Available as a browser extension, VS Code extension, GitHub App, MCP Server, and API. [nerq.ai](https://nerq.ai)*
