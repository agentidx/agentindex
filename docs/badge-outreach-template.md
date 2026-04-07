# Nerq Trust Badge -- Outreach Template

## GitHub Issue Template

Use this template when opening issues on AI repos suggesting they add a Nerq trust badge.

---

**Issue Title:** Add independent trust score badge to README

**Issue Body:**

```markdown
Hi there,

I maintain [Nerq](https://nerq.ai), an independent trust scoring engine for AI projects. We index 5M+ AI assets across GitHub, PyPI, npm, HuggingFace, and Docker Hub, and compute a Trust Score based on maintenance activity, community signals, security posture, and documentation quality.

Your project already has a score on Nerq. You can add a badge to your README that displays it:

[![Nerq Trust Score](https://nerq.ai/badge/{owner}/{repo}.svg)](https://nerq.ai/is-{owner}-{repo}-safe)

```md
[![Nerq Trust Score](https://nerq.ai/badge/{owner}/{repo}.svg)](https://nerq.ai/is-{owner}-{repo}-safe)
```

**What the badge shows:**
- A 0-100 Trust Score computed from public signals (commit frequency, issue response time, CVE history, dependency health, documentation coverage)
- The score updates automatically -- no manual maintenance needed
- Clicking the badge links to a full trust report for the project

**Why this matters:**
- Gives users an at-a-glance trust signal before they adopt a dependency
- Scores are independently computed -- project maintainers cannot pay to change them
- Transparent methodology documented at https://nerq.ai/methodology

**Data sources (5 channels):**
1. GitHub (stars, commits, issue velocity, contributor count)
2. PyPI / npm (download trends, version frequency, dependency tree)
3. HuggingFace (model downloads, community engagement)
4. Docker Hub (pull counts, image update frequency)
5. Security advisories (CVEs, known vulnerabilities)

If a README badge isn't the right fit, there are two other ways to surface trust data:
- **Browser extension:** Users can see trust scores inline on GitHub without any changes to your repo. Available for Chrome and Firefox.
- **GitHub App:** Install once and the score appears as a status check on PRs. No badge markup needed.

Happy to answer any questions. No pressure at all -- just thought it might be useful for your users.
```

---

## Notes for outreach

- Replace `{owner}/{repo}` with the actual org and repo name before posting.
- Do not open more than one issue per repo. If the issue is closed without action, respect that.
- Space out issue creation (no more than 3-4 per day) to avoid looking like spam.
- If a maintainer asks for removal or expresses disinterest, close the issue promptly and thank them.

---

## Target Repos (20)

### AI Frameworks (5)

| Repo | Owner | Badge Markdown |
|------|-------|----------------|
| tensorflow | tensorflow | `[![Nerq Trust Score](https://nerq.ai/badge/tensorflow/tensorflow.svg)](https://nerq.ai/is-tensorflow-tensorflow-safe)` |
| pytorch | pytorch | `[![Nerq Trust Score](https://nerq.ai/badge/pytorch/pytorch.svg)](https://nerq.ai/is-pytorch-pytorch-safe)` |
| transformers | huggingface | `[![Nerq Trust Score](https://nerq.ai/badge/huggingface/transformers.svg)](https://nerq.ai/is-huggingface-transformers-safe)` |
| langchain | langchain-ai | `[![Nerq Trust Score](https://nerq.ai/badge/langchain-ai/langchain.svg)](https://nerq.ai/is-langchain-ai-langchain-safe)` |
| llama_index | run-llama | `[![Nerq Trust Score](https://nerq.ai/badge/run-llama/llama_index.svg)](https://nerq.ai/is-run-llama-llama_index-safe)` |

### AI Tools (5)

| Repo | Owner | Badge Markdown |
|------|-------|----------------|
| ollama | ollama | `[![Nerq Trust Score](https://nerq.ai/badge/ollama/ollama.svg)](https://nerq.ai/is-ollama-ollama-safe)` |
| vllm | vllm-project | `[![Nerq Trust Score](https://nerq.ai/badge/vllm-project/vllm.svg)](https://nerq.ai/is-vllm-project-vllm-safe)` |
| text-generation-webui | oobabooga | `[![Nerq Trust Score](https://nerq.ai/badge/oobabooga/text-generation-webui.svg)](https://nerq.ai/is-oobabooga-text-generation-webui-safe)` |
| open-webui | open-webui | `[![Nerq Trust Score](https://nerq.ai/badge/open-webui/open-webui.svg)](https://nerq.ai/is-open-webui-open-webui-safe)` |
| jan | janhq | `[![Nerq Trust Score](https://nerq.ai/badge/janhq/jan.svg)](https://nerq.ai/is-janhq-jan-safe)` |

### AI Agents (5)

| Repo | Owner | Badge Markdown |
|------|-------|----------------|
| autogen | microsoft | `[![Nerq Trust Score](https://nerq.ai/badge/microsoft/autogen.svg)](https://nerq.ai/is-microsoft-autogen-safe)` |
| crewAI | crewAIInc | `[![Nerq Trust Score](https://nerq.ai/badge/crewAIInc/crewAI.svg)](https://nerq.ai/is-crewAIInc-crewAI-safe)` |
| AutoGPT | Significant-Gravitas | `[![Nerq Trust Score](https://nerq.ai/badge/Significant-Gravitas/AutoGPT.svg)](https://nerq.ai/is-Significant-Gravitas-AutoGPT-safe)` |
| babyagi | yoheinakajima | `[![Nerq Trust Score](https://nerq.ai/badge/yoheinakajima/babyagi.svg)](https://nerq.ai/is-yoheinakajima-babyagi-safe)` |
| MetaGPT | geekan | `[![Nerq Trust Score](https://nerq.ai/badge/geekan/MetaGPT.svg)](https://nerq.ai/is-geekan-MetaGPT-safe)` |

### Developer Tools (5)

| Repo | Owner | Badge Markdown |
|------|-------|----------------|
| fastapi | fastapi | `[![Nerq Trust Score](https://nerq.ai/badge/fastapi/fastapi.svg)](https://nerq.ai/is-fastapi-fastapi-safe)` |
| streamlit | streamlit | `[![Nerq Trust Score](https://nerq.ai/badge/streamlit/streamlit.svg)](https://nerq.ai/is-streamlit-streamlit-safe)` |
| gradio | gradio-app | `[![Nerq Trust Score](https://nerq.ai/badge/gradio-app/gradio.svg)](https://nerq.ai/is-gradio-app-gradio-safe)` |
| chainlit | Chainlit | `[![Nerq Trust Score](https://nerq.ai/badge/Chainlit/chainlit.svg)](https://nerq.ai/is-Chainlit-chainlit-safe)` |
| modal-client | modal-labs | `[![Nerq Trust Score](https://nerq.ai/badge/modal-labs/modal-client.svg)](https://nerq.ai/is-modal-labs-modal-client-safe)` |
