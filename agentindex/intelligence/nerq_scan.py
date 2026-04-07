#!/usr/bin/env python3
"""
nerq scan — Post-install trust scan for AI packages

Scans your environment for installed AI agents, tools, and MCP servers,
then looks up trust scores via the Nerq API.

Usage:
    python -m agentindex.intelligence.nerq_scan
    python -m agentindex.intelligence.nerq_scan --json
    python -m agentindex.intelligence.nerq_scan --min-trust 70
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Use urllib so we have zero external dependencies
import urllib.request
import urllib.parse
import urllib.error

# ── Known AI packages to look for ───────────────────────────────

AI_PIP_PACKAGES = {
    # LLM providers
    "openai", "anthropic", "google-generativeai", "google-cloud-aiplatform",
    "cohere", "mistralai", "groq", "together", "replicate", "fireworks-ai",
    "ai21", "aleph-alpha-client", "huggingface-hub",
    # Agent frameworks
    "langchain", "langchain-core", "langchain-community", "langchain-openai",
    "langchain-anthropic", "langgraph", "langsmith",
    "crewai", "crewai-tools",
    "autogen", "pyautogen", "autogen-agentchat",
    "llama-index", "llama-index-core", "llamaindex",
    "semantic-kernel",
    "dspy", "dspy-ai",
    "phidata", "phi",
    "haystack-ai", "farm-haystack",
    "smolagents",
    "pydantic-ai",
    "agno",
    "camel-ai",
    "taskweaver",
    "agency-swarm",
    "swarm",
    # MCP
    "mcp", "fastmcp",
    # Vector DBs / retrieval
    "chromadb", "pinecone-client", "weaviate-client", "qdrant-client",
    "milvus", "pymilvus", "faiss-cpu", "faiss-gpu", "lancedb",
    # ML/DL frameworks
    "transformers", "diffusers", "accelerate", "peft", "trl",
    "torch", "torchvision", "tensorflow", "keras", "jax", "flax",
    "onnxruntime", "vllm", "llama-cpp-python",
    # Evaluation / observability
    "ragas", "deepeval", "langfuse", "phoenix", "arize",
    "mlflow", "wandb", "neptune",
    # Embedding / NLP
    "sentence-transformers", "tiktoken", "tokenizers", "spacy",
    # Guardrails
    "guardrails-ai", "nemoguardrails",
}

AI_NPM_PACKAGES = {
    "@langchain/core", "@langchain/openai", "@langchain/anthropic",
    "@langchain/community", "langchain",
    "openai", "@anthropic-ai/sdk",
    "@google/generative-ai", "cohere-ai",
    "@modelcontextprotocol/sdk", "@modelcontextprotocol/server-filesystem",
    "@modelcontextprotocol/server-github", "@modelcontextprotocol/server-postgres",
    "@modelcontextprotocol/server-brave-search", "@modelcontextprotocol/server-memory",
    "ai", "@ai-sdk/openai", "@ai-sdk/anthropic", "@ai-sdk/google",
    "llamaindex",
    "autogen",
    "@microsoft/semantic-kernel",
    "chromadb", "@pinecone-database/pinecone", "weaviate-ts-client",
    "@qdrant/js-client-rest",
    "transformers.js", "@xenova/transformers", "@huggingface/inference",
    "ollama", "ollama-ai-provider",
}

NERQ_API = "https://nerq.ai"
RESOLVE_TIMEOUT = 8  # seconds per lookup

# ── Scanners ─────────────────────────────────────────────────────

def scan_pip() -> list[dict]:
    """Find installed pip packages that are AI-related."""
    found = []
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return found
        packages = json.loads(result.stdout)
    except Exception:
        return found

    for pkg in packages:
        name = pkg.get("name", "").lower()
        # Normalize: pip uses dashes and underscores interchangeably
        normalized = name.replace("_", "-")
        if normalized in AI_PIP_PACKAGES or name in AI_PIP_PACKAGES:
            found.append({
                "name": pkg["name"],
                "version": pkg.get("version", "?"),
                "source": "pip",
                "ecosystem": "python",
            })

    return found


def scan_npm() -> list[dict]:
    """Find installed npm packages (global + local node_modules) that are AI-related."""
    found = []

    # Check global npm packages
    try:
        result = subprocess.run(
            ["npm", "list", "-g", "--depth=0", "--json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 or result.stdout.strip():
            data = json.loads(result.stdout)
            deps = data.get("dependencies", {})
            for name, info in deps.items():
                if name in AI_NPM_PACKAGES:
                    found.append({
                        "name": name,
                        "version": info.get("version", "?"),
                        "source": "npm-global",
                        "ecosystem": "node",
                    })
    except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired):
        pass

    # Check local node_modules in cwd
    local_nm = Path.cwd() / "node_modules"
    if local_nm.is_dir():
        for pkg_name in AI_NPM_PACKAGES:
            pkg_dir = local_nm / pkg_name
            pkg_json = pkg_dir / "package.json"
            if pkg_json.is_file():
                try:
                    meta = json.loads(pkg_json.read_text())
                    found.append({
                        "name": pkg_name,
                        "version": meta.get("version", "?"),
                        "source": "npm-local",
                        "ecosystem": "node",
                    })
                except Exception:
                    found.append({
                        "name": pkg_name,
                        "version": "?",
                        "source": "npm-local",
                        "ecosystem": "node",
                    })

    return found


def scan_mcp_configs() -> list[dict]:
    """Find MCP server configurations."""
    found = []
    config_locations = [
        Path.home() / ".config" / "mcp" / "mcp.json",
        Path.home() / ".config" / "mcp" / "config.json",
        Path.home() / ".mcp.json",
        Path.cwd() / ".mcp.json",
        Path.cwd() / "mcp.json",
        # Claude Desktop config
        Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        # Cursor config
        Path.home() / ".cursor" / "mcp.json",
    ]

    for config_path in config_locations:
        if not config_path.is_file():
            continue
        try:
            data = json.loads(config_path.read_text())
            servers = data.get("mcpServers", data.get("servers", {}))
            if isinstance(servers, dict):
                for server_name, server_config in servers.items():
                    cmd = ""
                    if isinstance(server_config, dict):
                        cmd = server_config.get("command", "")
                        args = server_config.get("args", [])
                        if isinstance(args, list) and args:
                            # Try to extract the package name from args
                            for arg in args:
                                if isinstance(arg, str) and not arg.startswith("-"):
                                    cmd = f"{cmd} {arg}"
                                    break
                    found.append({
                        "name": server_name,
                        "version": "mcp-server",
                        "source": f"mcp-config:{config_path.name}",
                        "ecosystem": "mcp",
                        "command": cmd.strip(),
                    })
        except Exception:
            continue

    return found


# ── API lookup ───────────────────────────────────────────────────

def lookup_trust_score(package_name: str, ecosystem: str = "python") -> dict | None:
    """Look up a package's trust score via Nerq resolve API."""
    # Construct a task query that will match the package name
    task = f"{package_name} {ecosystem} AI tool"
    params = urllib.parse.urlencode({
        "task": task,
        "min_trust": "0",
        "limit": "3",
    })
    url = f"{NERQ_API}/v1/resolve?{params}"

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "nerq-scan/1.0",
            "Accept": "application/json",
        })
        resp = urllib.request.urlopen(req, timeout=RESOLVE_TIMEOUT)
        data = json.loads(resp.read().decode())

        # The resolve API returns a recommendation + alternatives
        rec = data.get("recommendation", {})
        alts = data.get("alternatives", [])
        all_candidates = [rec] + alts if rec else alts

        # Find the best match by name similarity
        pkg_lower = package_name.lower().replace("-", "").replace("_", "").replace("@", "").replace("/", "")
        best = None
        best_score = 0

        for candidate in all_candidates:
            cand_name = (candidate.get("name") or "").lower().replace("-", "").replace("_", "").replace(" ", "")
            # Exact or substring match
            if pkg_lower in cand_name or cand_name in pkg_lower:
                match_score = 2  # strong match
            elif any(tok in cand_name for tok in pkg_lower.split()):
                match_score = 1  # partial match
            else:
                match_score = 0

            if match_score > best_score:
                best_score = match_score
                best = candidate

        if best and best_score > 0:
            return {
                "trust_score": best.get("trust_score"),
                "grade": best.get("grade") or best.get("trust_grade"),
                "nerq_url": best.get("details_url", ""),
                "matched_name": best.get("name", ""),
            }

    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            OSError, TimeoutError):
        pass

    return None


# ── Display ──────────────────────────────────────────────────────

def _grade_color(grade: str | None) -> str:
    """ANSI color for trust grade."""
    if not grade:
        return ""
    g = grade.upper()
    if g.startswith("A"):
        return "\033[92m"  # green
    elif g.startswith("B"):
        return "\033[93m"  # yellow
    elif g.startswith("C"):
        return "\033[33m"  # orange-ish
    else:
        return "\033[91m"  # red


def _score_color(score: float | None) -> str:
    """ANSI color for trust score."""
    if score is None:
        return "\033[90m"  # gray
    if score >= 70:
        return "\033[92m"
    elif score >= 50:
        return "\033[93m"
    else:
        return "\033[91m"

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def print_table(results: list[dict], show_warnings: bool = True, min_trust: int = 50):
    """Print results as a formatted table."""
    if not results:
        print(f"\n{DIM}No AI packages found in your environment.{RESET}")
        return

    # Header
    print(f"\n{BOLD}  nerq scan{RESET} — AI package trust report")
    print(f"  {DIM}Scanned {len(results)} AI package(s){RESET}\n")

    # Column widths
    name_w = max(len(r["name"]) for r in results)
    name_w = max(name_w, 12)
    name_w = min(name_w, 40)
    ver_w = max(len(r["version"]) for r in results)
    ver_w = max(ver_w, 7)
    ver_w = min(ver_w, 15)

    # Header row
    hdr = (
        f"  {'Package':<{name_w}}  {'Version':<{ver_w}}  {'Source':<12}"
        f"  {'Score':>5}  {'Grade':<5}  Status"
    )
    print(f"{DIM}{hdr}{RESET}")
    print(f"  {'─' * (name_w + ver_w + 45)}")

    warnings = []

    for r in results:
        name = r["name"][:name_w]
        ver = r["version"][:ver_w]
        src = r["source"][:12]
        score = r.get("trust_score")
        grade = r.get("grade")
        nerq_url = r.get("nerq_url", "")

        score_str = f"{score:5.1f}" if score is not None else "  n/a"
        grade_str = grade or "—"
        sc = _score_color(score)
        gc = _grade_color(grade)

        # Status indicator
        if score is None:
            status = f"{DIM}not indexed{RESET}"
        elif score < min_trust:
            status = f"\033[91m!! LOW TRUST{RESET}"
            warnings.append(r)
        elif score >= 70:
            status = f"\033[92mok{RESET}"
        else:
            status = f"\033[93mfair{RESET}"

        print(
            f"  {name:<{name_w}}  {ver:<{ver_w}}  {src:<12}"
            f"  {sc}{score_str}{RESET}  {gc}{grade_str:<5}{RESET}  {status}"
        )

    # Warnings summary
    if warnings and show_warnings:
        print(f"\n  {BOLD}\033[91m{'!' * 3} {len(warnings)} package(s) with trust score below {min_trust}:{RESET}")
        for w in warnings:
            url_hint = f"  {DIM}{w.get('nerq_url', '')}{RESET}" if w.get("nerq_url") else ""
            print(
                f"    \033[91m- {w['name']}{RESET} "
                f"(score: {w.get('trust_score', '?')}, grade: {w.get('grade', '?')})"
                f"{url_hint}"
            )
        print(f"\n  {DIM}Review low-trust packages at https://nerq.ai before using in production.{RESET}")

    # Summary
    scored = [r for r in results if r.get("trust_score") is not None]
    if scored:
        avg = sum(r["trust_score"] for r in scored) / len(scored)
        print(f"\n  {DIM}Average trust score: {avg:.1f} across {len(scored)} indexed package(s){RESET}")
    print()


def print_json(results: list[dict]):
    """Print results as JSON."""
    output = {
        "scan_results": results,
        "summary": {
            "total_found": len(results),
            "indexed": len([r for r in results if r.get("trust_score") is not None]),
            "warnings": len([r for r in results if (r.get("trust_score") or 100) < 50]),
        },
    }
    print(json.dumps(output, indent=2))


# ── Main ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="nerq scan",
        description="Scan your environment for AI packages and check their trust scores.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--min-trust", type=int, default=50,
        help="Minimum trust score threshold for warnings (default: 50)",
    )
    parser.add_argument(
        "--skip-api", action="store_true",
        help="Skip API lookups (just list found packages)",
    )
    parser.add_argument(
        "--pip-only", action="store_true",
        help="Only scan pip packages",
    )
    parser.add_argument(
        "--npm-only", action="store_true",
        help="Only scan npm packages",
    )
    parser.add_argument(
        "--mcp-only", action="store_true",
        help="Only scan MCP server configs",
    )

    args = parser.parse_args()

    # Determine what to scan
    scan_all = not (args.pip_only or args.npm_only or args.mcp_only)

    if not args.json:
        print(f"\n{BOLD}  nerq scan{RESET} {DIM}v1.0{RESET}")
        print(f"  {DIM}Scanning for AI packages...{RESET}")

    results = []

    # Scan pip
    if scan_all or args.pip_only:
        if not args.json:
            print(f"  {DIM}  [pip] scanning python packages...{RESET}", end="", flush=True)
        pip_results = scan_pip()
        results.extend(pip_results)
        if not args.json:
            print(f" found {len(pip_results)}")

    # Scan npm
    if scan_all or args.npm_only:
        if not args.json:
            print(f"  {DIM}  [npm] scanning node packages...{RESET}", end="", flush=True)
        npm_results = scan_npm()
        results.extend(npm_results)
        if not args.json:
            print(f" found {len(npm_results)}")

    # Scan MCP configs
    if scan_all or args.mcp_only:
        if not args.json:
            print(f"  {DIM}  [mcp] scanning MCP server configs...{RESET}", end="", flush=True)
        mcp_results = scan_mcp_configs()
        results.extend(mcp_results)
        if not args.json:
            print(f" found {len(mcp_results)}")

    if not results:
        if args.json:
            print_json([])
        else:
            print(f"\n  {DIM}No AI packages found.{RESET}\n")
        return

    # Look up trust scores
    if not args.skip_api:
        if not args.json:
            print(f"\n  {DIM}  Looking up trust scores via nerq.ai...{RESET}", flush=True)

        for i, r in enumerate(results):
            if not args.json:
                pct = int((i + 1) / len(results) * 100)
                print(
                    f"\r  {DIM}  [{pct:3d}%] Checking {r['name']:<35}{RESET}",
                    end="", flush=True,
                )

            lookup = lookup_trust_score(r["name"], r.get("ecosystem", ""))
            if lookup:
                r["trust_score"] = lookup.get("trust_score")
                r["grade"] = lookup.get("grade")
                r["nerq_url"] = lookup.get("nerq_url")
                r["matched_name"] = lookup.get("matched_name")

        if not args.json:
            print(f"\r  {DIM}  [100%] Done.{' ' * 40}{RESET}")

    # Output
    if args.json:
        print_json(results)
    else:
        print_table(results, show_warnings=True, min_trust=args.min_trust)


if __name__ == "__main__":
    main()
