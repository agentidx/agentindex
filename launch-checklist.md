# Nerq Launch Checklist — Machine-Adoption Acceleration

## Manual Actions Required

### High Priority — Do First
- [ ] **PyPI publish**: `cd nerq-cli && twine upload dist/nerq-1.1.0*` (needs PyPI credentials)
- [ ] **Show HN**: Post from `community/show-hn.md`
- [ ] **Dev.to publish**: Set DEVTO_API_KEY in .env, then `python -m agentindex.intelligence.devto_publisher`
- [ ] **HuggingFace dataset upload**: Follow `huggingface/UPLOAD_INSTRUCTIONS.md`

### GitHub — Create Repos & Push
- [ ] **GitHub Action repo**: Push `github-action-repo/` to `github.com/nerq-ai/trust-check-action`
  - `cd github-action-repo && git init && git add . && git commit -m "Initial release v1.0.0"`
  - `git remote add origin git@github.com:nerq-ai/trust-check-action.git && git push -u origin main`
  - Create GitHub release v1.0.0 to publish to Marketplace
- [ ] **VS Code extension**: Push `vscode-extension/` and publish with `vsce publish`

### Awesome Lists — Submit PRs
- [ ] PR to `e2b-dev/awesome-ai-agents` (see `awesome-list-prs/awesome-ai-agents.md`)
- [ ] PR to `punkpeye/awesome-mcp-servers` (see `awesome-list-prs/awesome-mcp-servers.md`)
- [ ] PR to `Shubhamsaboo/awesome-llm-apps` (see `awesome-list-prs/awesome-llm-apps.md`)

### Framework PRs — Submit to Framework Repos
- [ ] LangChain: `framework-prs/langchain/` → PR to `langchain-ai/langchain`
- [ ] CrewAI: `framework-prs/crewai/` → PR to `crewai/crewai`
- [ ] AutoGen: `framework-prs/autogen/` → PR to `microsoft/autogen`
- [ ] LlamaIndex: `framework-prs/llamaindex/` → PR to `run-llama/llama_index`
- [ ] Semantic Kernel: `framework-prs/semantic-kernel/` → PR to `microsoft/semantic-kernel`

### Registries
- [ ] **Smithery**: `npx @smithery/cli publish` (needs API key from smithery.ai dashboard)
- [ ] **Glama**: Submit at glama.ai (manual process)

### Partnerships
- [ ] Email Glama partnership proposal (see `partnerships/glama-partnership.md`)
- [ ] Email Smithery partnership proposal (see `partnerships/smithery-partnership.md`)
- [ ] Email AI Agents Directory proposal (see `partnerships/ai-agents-directory-partnership.md`)
- [ ] Share MCP ecosystem proposal with relevant maintainers

### Community Posts
- [ ] Reddit r/MachineLearning (see `community/reddit-post.md`)
- [ ] Reddit r/LocalLLaMA (see `community/reddit-post.md`)
- [ ] Reddit r/artificial (see `community/reddit-post.md`)

## Automated Systems — Already Running

| LaunchAgent | Schedule | Status |
|-------------|----------|--------|
| com.nerq.api | Always on | Active |
| com.nerq.auto-comparisons | Mon 07:00 | Active |
| com.nerq.social-scheduler | Daily 12:00 | Active |
| com.nerq.machine-analytics | Daily 10:00 | Active |
| com.nerq.badge-pr-bot | Daily 11:00 | Active |

## Verification — After Launch

- [ ] `curl nerq.ai/v1/preflight?target=langchain` returns trust score
- [ ] `curl nerq.ai/llms.txt` returns machine-readable API description
- [ ] `curl nerq.ai/health` returns healthy status
- [ ] `curl nerq.ai/agents` returns API directory
- [ ] `curl nerq.ai/.well-known/security.txt` returns security contact
- [ ] `curl nerq.ai/feed/cve-alerts.xml` returns RSS feed
- [ ] `nerq.ai/blog` shows auto-generated comparison posts
- [ ] `nerq.ai/data` shows downloadable datasets
- [ ] `nerq.ai/docs` shows API documentation
