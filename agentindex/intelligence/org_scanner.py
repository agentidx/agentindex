"""
GitHub Organization Scanner v2
================================
Scans a GitHub org's public repos to discover AI tools.

Fixes from v1:
- Sort repos by pushed date (not stars) — active repos have AI tools
- Scan up to 200 repos for large orgs
- Detect AI repos by name/description (not just dependencies)
- Better pyproject.toml parsing
- Scan nested dep files (python/requirements.txt, etc.)
"""

import base64
import json
import logging
import os
import re
import time
from pathlib import Path

import requests as http_requests

logger = logging.getLogger("nerq.org_scanner")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"} if GITHUB_TOKEN else {}

# Known AI packages (Python + JS) — comprehensive list
KNOWN_AI_PACKAGES = {
    # Python LLM providers
    "openai", "anthropic", "google-generativeai", "google-cloud-aiplatform",
    "cohere", "mistralai", "groq", "together", "replicate", "fireworks-ai",
    "anyscale", "deepseek", "cerebras-cloud-sdk",
    # Python frameworks
    "langchain", "langchain-core", "langchain-community", "langchain-openai",
    "langchain-anthropic", "langchain-google-genai",
    "llama-index", "llama-index-core", "crewai", "autogen", "pyautogen",
    "pyautogpt", "haystack-ai", "semantic-kernel", "dspy-ai", "dspy",
    "smolagents", "pydantic-ai", "magentic", "instructor", "outlines",
    "guidance", "lmql", "marvin", "promptflow", "promptflow-core",
    # Python vector DBs
    "pinecone-client", "chromadb", "qdrant-client", "weaviate-client",
    "pymilvus", "lancedb", "pgvector", "elasticsearch",
    # Python ML/DL
    "torch", "pytorch", "tensorflow", "tf-keras", "keras",
    "transformers", "diffusers", "accelerate", "datasets", "tokenizers",
    "safetensors", "peft", "trl", "bitsandbytes", "auto-gptq",
    "sentence-transformers", "faiss-cpu", "faiss-gpu",
    "scikit-learn", "sklearn", "xgboost", "lightgbm", "catboost", "optuna",
    "onnx", "onnxruntime", "onnxruntime-gpu",
    # Python deep learning tools
    "deepspeed", "megatron-lm", "flash-attn", "triton",
    "apex", "fairseq", "allennlp", "spacy", "nltk", "gensim",
    # Python tools
    "huggingface-hub", "wandb", "mlflow", "ray", "vllm", "litellm",
    "modal", "bentoml", "gradio", "streamlit", "chainlit",
    "langserve", "langsmith", "langfuse", "phoenix", "arize",
    "tiktoken", "unstructured", "docling",
    # Python MCP
    "mcp", "modelcontextprotocol",
    # Python image/video
    "opencv-python", "cv2", "pillow", "torchvision", "torchaudio",
    "stable-diffusion", "compel",
    # npm AI
    "@openai/api", "openai", "langchain", "@langchain/core", "@langchain/openai",
    "@langchain/anthropic", "@langchain/community",
    "@anthropic-ai/sdk", "ai", "@ai-sdk/openai", "@ai-sdk/anthropic",
    "@ai-sdk/google", "@ai-sdk/mistral",
    "@modelcontextprotocol/sdk", "llamaindex", "chromadb",
    "@pinecone-database/pinecone", "@huggingface/inference",
    "cohere-ai", "replicate", "@google/generative-ai",
    "@vercel/ai", "ollama", "gpt-3-encoder", "tiktoken",
    "@xenova/transformers", "onnxruntime-web", "onnxruntime-node",
    "tensorflow", "@tensorflow/tfjs", "brain.js",
}

# AI-related repo name patterns — if repo name matches, it IS an AI tool
AI_REPO_PATTERNS = [
    r"(?i)(llm|gpt|copilot|ai[-_]|[-_]ai$|machine[-_]learn|deep[-_]learn|neural)",
    r"(?i)(transformer|diffusion|embedding|vector[-_]|rag[-_]|agent[-_])",
    r"(?i)(openai|anthropic|langchain|autogen|semantic[-_]kernel|guidance)",
    r"(?i)(deepspeed|onnx|tensorflow|pytorch|torch|keras|huggingface)",
    r"(?i)(chatbot|nlp|nlu|speech|vision|recognition|detection|segmentation)",
    r"(?i)(mcp[-_]server|model[-_]context|prompt[-_]|fine[-_]tun)",
]

# AI keywords in repo descriptions
AI_DESC_KEYWORDS = [
    "language model", "llm", "gpt", "artificial intelligence", "machine learning",
    "deep learning", "neural network", "transformer", "embedding", "vector",
    "rag", "retrieval augmented", "agent framework", "ai agent",
    "copilot", "code generation", "text generation", "image generation",
    "diffusion", "fine-tuning", "fine tuning", "prompt engineering",
    "mcp server", "model context protocol",
]

_cache = {}
CACHE_TTL = 86400


def _gh_get(url: str) -> dict | list | None:
    if url in _cache and (time.time() - _cache[url][0]) < CACHE_TTL:
        return _cache[url][1]
    try:
        resp = http_requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 403:
            # Check for rate limit
            remaining = resp.headers.get("X-RateLimit-Remaining", "0")
            if remaining == "0":
                reset = int(resp.headers.get("X-RateLimit-Reset", 0))
                wait = max(1, reset - int(time.time()))
                logger.warning(f"Rate limited, waiting {wait}s")
                if wait < 60:
                    time.sleep(wait + 1)
                    resp = http_requests.get(url, headers=HEADERS, timeout=15)
                    if resp.status_code != 200:
                        return None
                else:
                    logger.warning(f"Rate limit reset in {wait}s, skipping")
                    return None
        if resp.status_code != 200:
            return None
        data = resp.json()
        _cache[url] = (time.time(), data)
        return data
    except Exception as e:
        logger.warning(f"GitHub API error: {e}")
        return None


def _parse_python_deps(content: str) -> set:
    deps = set()
    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-r ") or line.startswith("--"):
            continue
        if line.startswith("-e ") or line.startswith("-f "):
            continue
        name = re.split(r"[=><~!\[;@\s]", line)[0].strip().lower()
        if name and len(name) > 1 and not name.startswith("."):
            deps.add(name)
    return deps


def _parse_pyproject_toml(content: str) -> set:
    """Parse pyproject.toml for dependencies — handles both PEP 621 and Poetry."""
    deps = set()
    in_section = False
    bracket_depth = 0

    for line in content.split("\n"):
        stripped = line.strip()

        # Detect dependency sections
        if re.match(r'\[project\]', stripped) or re.match(r'\[tool\.poetry\]', stripped):
            in_section = False
            continue
        if re.match(r'\[(project\.)?dependencies\]', stripped) or \
           re.match(r'\[tool\.poetry\.dependencies\]', stripped):
            in_section = True
            continue
        if re.match(r'\[(project\.)?optional-dependencies', stripped) or \
           re.match(r'\[tool\.poetry\.(dev-)?dependencies\]', stripped) or \
           re.match(r'\[tool\.poetry\.group\..*\.dependencies\]', stripped):
            in_section = True
            continue
        if stripped.startswith("[") and in_section:
            in_section = False
            continue

        if in_section:
            # Poetry style: package = "^1.0" or package = {version = "^1.0"}
            m = re.match(r'^([a-zA-Z0-9_-]+)\s*=', stripped)
            if m:
                name = m.group(1).strip().lower()
                if name not in ("python", "python_requires"):
                    deps.add(name)

        # PEP 621 inline: dependencies = ["openai>=1.0", "langchain"]
        if "dependencies" in stripped and "=" in stripped and "[" in stripped:
            items = re.findall(r'"([^"]+)"', stripped)
            for item in items:
                name = re.split(r"[=><~!\[;@\s]", item)[0].strip().lower()
                if name and len(name) > 1:
                    deps.add(name)

        # Multi-line dependencies list
        if stripped.startswith('"') and in_section:
            item = stripped.strip('",').strip()
            name = re.split(r"[=><~!\[;@\s]", item)[0].strip().lower()
            if name and len(name) > 1:
                deps.add(name)

    return deps


def _parse_package_json_deps(content: str) -> set:
    deps = set()
    try:
        data = json.loads(content)
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            if key in data and isinstance(data[key], dict):
                deps.update(data[key].keys())
    except (json.JSONDecodeError, AttributeError):
        pass
    return {d.lower() for d in deps}


def _is_ai_repo(repo: dict) -> str | None:
    """Check if a repo is AI-related by name or description. Returns matched keyword or None."""
    name = repo.get("name", "")
    desc = (repo.get("description") or "").lower()
    topics = repo.get("topics", []) or []

    # Check repo name
    for pattern in AI_REPO_PATTERNS:
        if re.search(pattern, name):
            return name

    # Check description
    for kw in AI_DESC_KEYWORDS:
        if kw in desc:
            return kw

    # Check topics
    ai_topics = {"machine-learning", "deep-learning", "ai", "artificial-intelligence",
                 "llm", "nlp", "computer-vision", "transformers", "pytorch", "tensorflow",
                 "gpt", "langchain", "rag", "vector-database", "embedding", "mcp"}
    if set(topics) & ai_topics:
        return f"topic:{list(set(topics) & ai_topics)[0]}"

    return None


def scan_github_org(org_name: str, max_repos: int = 200) -> dict:
    """
    Scan a GitHub org's public repos for AI tools.
    v2: sorts by pushed date, scans more repos, detects by name+description+deps.
    """
    logger.info(f"Scanning GitHub org: {org_name}")

    # Get repos sorted by recently pushed (active repos have AI tools)
    repos = []
    page = 1
    while len(repos) < max_repos:
        url = f"https://api.github.com/orgs/{org_name}/repos?per_page=100&type=public&sort=pushed&direction=desc&page={page}"
        data = _gh_get(url)
        if not data or not isinstance(data, list) or len(data) == 0:
            break
        repos.extend(data)
        page += 1
        if len(data) < 100:
            break
        time.sleep(0.5)

    total_repos = len(repos)
    repos = repos[:max_repos]
    logger.info(f"  Fetched {len(repos)} repos (of {total_repos}) for {org_name}")

    all_deps = set()
    ai_tools = set()
    ai_repos_by_name = []
    dep_files_found = 0
    repos_scanned = 0

    # Phase 1: Detect AI repos by name/description/topics
    for repo in repos:
        match = _is_ai_repo(repo)
        if match:
            repo_short = repo.get("name", "")
            ai_repos_by_name.append({"name": repo_short, "matched_by": match,
                                     "stars": repo.get("stargazers_count", 0)})
            # Add the repo name itself as an "AI tool" if it matches a known package
            name_lower = repo_short.lower().replace("-", "_")
            if name_lower in KNOWN_AI_PACKAGES or repo_short.lower() in KNOWN_AI_PACKAGES:
                ai_tools.add(repo_short.lower())

    logger.info(f"  Phase 1: {len(ai_repos_by_name)} AI repos by name/desc/topic")

    # Phase 2: Scan dependency files
    dep_file_paths = [
        "requirements.txt", "pyproject.toml", "setup.py",
        "package.json",
        "python/requirements.txt", "sdk/python/requirements.txt",
        "requirements-dev.txt", "requirements/base.txt",
    ]

    # Prioritize: AI repos first, then most recently pushed
    scan_priority = []
    ai_repo_names = {r["name"] for r in ai_repos_by_name}
    for repo in repos:
        if repo.get("name") in ai_repo_names:
            scan_priority.insert(0, repo)
        else:
            scan_priority.append(repo)

    for repo in scan_priority[:100]:  # Scan top 100 repos
        repo_full = repo.get("full_name") or f"{org_name}/{repo.get('name', '')}"
        repos_scanned += 1

        for dep_file in dep_file_paths:
            url = f"https://api.github.com/repos/{repo_full}/contents/{dep_file}"
            file_data = _gh_get(url)
            if not file_data or "content" not in file_data:
                continue

            dep_files_found += 1
            try:
                content = base64.b64decode(file_data["content"]).decode("utf-8", errors="replace")
            except Exception:
                continue

            if dep_file.endswith("package.json"):
                deps = _parse_package_json_deps(content)
            elif dep_file.endswith("pyproject.toml"):
                deps = _parse_pyproject_toml(content)
            else:
                deps = _parse_python_deps(content)

            all_deps.update(deps)
            ai_found = deps & KNOWN_AI_PACKAGES
            ai_tools.update(ai_found)

            time.sleep(0.2)

    # Phase 3: Also count AI repos by name as tools (even if no deps found)
    for ar in ai_repos_by_name:
        ar_name = ar["name"].lower()
        # Only add high-signal repos (>100 stars) as AI tools
        if ar["stars"] > 100:
            ai_tools.add(ar_name)

    logger.info(f"  Phase 2: scanned {repos_scanned} repos, {dep_files_found} dep files")
    logger.info(f"  Total AI tools found: {len(ai_tools)}: {sorted(ai_tools)[:20]}")

    return {
        "org": org_name,
        "repos_scanned": repos_scanned,
        "total_repos": total_repos,
        "dep_files_found": dep_files_found,
        "all_deps": list(all_deps),
        "ai_tools_found": list(ai_tools),
        "ai_repos_by_name": ai_repos_by_name,
        "total_deps": len(all_deps),
    }
