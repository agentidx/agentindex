"""
nerq savings — LLM cost optimizer.

Scans Python files for LLM API usage patterns and suggests cheaper alternatives.
"""

import os
import re
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

USER_AGENT = "NerqCLI/1.2.0"
API_BASE = os.environ.get("NERQ_API_URL", "https://nerq.ai")

# ── LLM API detection patterns ──
PATTERNS = {
    "openai": {
        "imports": [
            r"(?:from\s+openai|import\s+openai)",
            r"OpenAI\s*\(",
        ],
        "calls": [
            r"ChatCompletion\.create",
            r"chat\.completions\.create",
            r"client\.chat\.completions",
            r"openai\.ChatCompletion",
            r"openai\.Completion",
        ],
        "env_vars": ["OPENAI_API_KEY"],
        "model_patterns": [
            (r'model\s*=\s*["\']([^"\']+)["\']', None),
        ],
        "default_model": "gpt-4o",
    },
    "anthropic": {
        "imports": [
            r"(?:from\s+anthropic|import\s+anthropic)",
            r"Anthropic\s*\(",
        ],
        "calls": [
            r"messages\.create",
            r"client\.messages",
            r"completions\.create",
        ],
        "env_vars": ["ANTHROPIC_API_KEY"],
        "model_patterns": [
            (r'model\s*=\s*["\']([^"\']+)["\']', None),
        ],
        "default_model": "claude-sonnet-4-20250514",
    },
    "google": {
        "imports": [
            r"(?:from\s+google|import\s+google)\.generativeai",
            r"genai\.GenerativeModel",
        ],
        "calls": [
            r"generate_content",
            r"GenerativeModel\s*\(",
        ],
        "env_vars": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
        "model_patterns": [
            (r'GenerativeModel\s*\(\s*["\']([^"\']+)["\']', None),
            (r'model\s*=\s*["\']([^"\']+)["\']', None),
        ],
        "default_model": "gemini-1.5-pro",
    },
    "cohere": {
        "imports": [
            r"(?:from\s+cohere|import\s+cohere)",
            r"cohere\.Client",
        ],
        "calls": [
            r"\.chat\(",
            r"\.generate\(",
        ],
        "env_vars": ["COHERE_API_KEY"],
        "model_patterns": [],
        "default_model": "command-r-plus",
    },
}

# ── Pricing data (per 1M input tokens) ──
PRICING = {
    "gpt-4o": {"provider": "OpenAI", "price": 2.50, "output_price": 10.00},
    "gpt-4o-mini": {"provider": "OpenAI", "price": 0.15, "output_price": 0.60},
    "gpt-4-turbo": {"provider": "OpenAI", "price": 10.00, "output_price": 30.00},
    "gpt-4": {"provider": "OpenAI", "price": 30.00, "output_price": 60.00},
    "gpt-3.5-turbo": {"provider": "OpenAI", "price": 0.50, "output_price": 1.50},
    "o1": {"provider": "OpenAI", "price": 15.00, "output_price": 60.00},
    "o1-mini": {"provider": "OpenAI", "price": 3.00, "output_price": 12.00},
    "o3-mini": {"provider": "OpenAI", "price": 1.10, "output_price": 4.40},
    "claude-opus-4-20250514": {"provider": "Anthropic", "price": 15.00, "output_price": 75.00},
    "claude-sonnet-4-20250514": {"provider": "Anthropic", "price": 3.00, "output_price": 15.00},
    "claude-3-5-sonnet-20241022": {"provider": "Anthropic", "price": 3.00, "output_price": 15.00},
    "claude-3-5-haiku-20241022": {"provider": "Anthropic", "price": 0.80, "output_price": 4.00},
    "claude-3-haiku-20240307": {"provider": "Anthropic", "price": 0.25, "output_price": 1.25},
    "gemini-1.5-pro": {"provider": "Google", "price": 1.25, "output_price": 5.00},
    "gemini-1.5-flash": {"provider": "Google", "price": 0.075, "output_price": 0.30},
    "gemini-2.0-flash": {"provider": "Google", "price": 0.10, "output_price": 0.40},
    "command-r-plus": {"provider": "Cohere", "price": 2.50, "output_price": 10.00},
    "command-r": {"provider": "Cohere", "price": 0.15, "output_price": 0.60},
}

# ── Capability tiers (for suggesting alternatives) ──
CAPABILITY_TIERS = {
    "frontier": ["gpt-4o", "claude-opus-4-20250514", "claude-sonnet-4-20250514", "gemini-1.5-pro", "o1"],
    "strong": ["gpt-4o-mini", "claude-3-5-haiku-20241022", "gemini-2.0-flash", "command-r-plus", "o3-mini"],
    "fast": ["gpt-3.5-turbo", "claude-3-haiku-20240307", "gemini-1.5-flash", "command-r"],
}


def scan_directory(directory="."):
    """Scan Python files for LLM API usage."""
    results = {}  # provider -> {files: [], models: set(), call_count: int}

    skip_dirs = {"venv", ".venv", "node_modules", ".git", "__pycache__", "site-packages", ".tox", "dist", "build"}
    py_files = [
        f for f in Path(directory).rglob("*.py")
        if not any(s in f.parts for s in skip_dirs)
    ]
    if not py_files:
        return results

    for py_file in py_files:
        try:
            content = py_file.read_text(errors="ignore")
        except (OSError, PermissionError):
            continue

        for provider, config in PATTERNS.items():
            has_import = any(re.search(p, content) for p in config["imports"])
            has_call = any(re.search(p, content) for p in config["calls"])

            if has_import or has_call:
                if provider not in results:
                    results[provider] = {"files": [], "models": set(), "call_count": 0}

                rel_path = str(py_file.relative_to(directory)) if py_file.is_relative_to(directory) else str(py_file)
                results[provider]["files"].append(rel_path)

                # Count API calls
                for call_pattern in config["calls"]:
                    results[provider]["call_count"] += len(re.findall(call_pattern, content))

                # Detect models
                for model_pattern, _ in config["model_patterns"]:
                    for match in re.finditer(model_pattern, content):
                        results[provider]["models"].add(match.group(1))

                if not results[provider]["models"]:
                    results[provider]["models"].add(config["default_model"])

    # Also check for env vars in .env files
    for env_file in [".env", ".env.local", ".env.example"]:
        env_path = Path(directory) / env_file
        if env_path.exists():
            try:
                env_content = env_path.read_text(errors="ignore")
                for provider, config in PATTERNS.items():
                    for var in config["env_vars"]:
                        if var in env_content and provider not in results:
                            results[provider] = {
                                "files": [f"({env_file})"],
                                "models": {config["default_model"]},
                                "call_count": 0,
                            }
            except (OSError, PermissionError):
                continue

    return results


def get_alternatives(model):
    """Get cheaper alternatives for a model."""
    if model not in PRICING:
        return []

    current_price = PRICING[model]["price"]
    current_tier = None
    for tier, models in CAPABILITY_TIERS.items():
        if model in models:
            current_tier = tier
            break

    alternatives = []
    for alt_model, alt_info in PRICING.items():
        if alt_model == model:
            continue
        if alt_info["price"] >= current_price:
            continue
        savings_pct = ((current_price - alt_info["price"]) / current_price) * 100
        if savings_pct < 10:
            continue
        alternatives.append({
            "model": alt_model,
            "provider": alt_info["provider"],
            "price": alt_info["price"],
            "savings_pct": savings_pct,
        })

    alternatives.sort(key=lambda x: x["savings_pct"], reverse=True)
    return alternatives[:5]


def estimate_monthly_cost(model, calls_per_day, avg_input_tokens=1000, avg_output_tokens=500):
    """Estimate monthly cost for a model."""
    if model not in PRICING:
        return None

    info = PRICING[model]
    monthly_calls = calls_per_day * 30

    input_cost = (avg_input_tokens * monthly_calls / 1_000_000) * info["price"]
    output_cost = (avg_output_tokens * monthly_calls / 1_000_000) * info["output_price"]
    return round(input_cost + output_cost, 2)


def run_savings(directory=".", calls_per_day=None, verbose=False):
    """Run the savings analysis."""
    print("\033[1m\033[36mScanning for LLM API usage...\033[0m")
    print()

    results = scan_directory(directory)

    if not results:
        print("  No LLM API usage detected in Python files.")
        print()
        print("  Tip: Run this in a directory with Python files that use OpenAI, Anthropic, or Google AI.")
        return

    for provider, data in results.items():
        models = list(data["models"])
        model_str = ", ".join(models)
        provider_display = provider.capitalize()

        print(f"  \033[1mFound: {provider_display} ({model_str})\033[0m in {len(data['files'])} file(s)")
        for f in data["files"][:5]:
            call_label = "API calls detected" if data["call_count"] > 0 else "import detected"
            print(f"    {f} — {call_label}")
        if len(data["files"]) > 5:
            print(f"    ... and {len(data['files']) - 5} more files")
        print()

        for model in models:
            if model not in PRICING:
                print(f"  \033[33mModel '{model}' not in pricing database — skipping alternatives\033[0m")
                continue

            info = PRICING[model]
            print(f"  Current model: \033[1m{model}\033[0m (${info['price']:.2f}/1M input tokens)")
            print()

            if calls_per_day:
                monthly = estimate_monthly_cost(model, calls_per_day)
                if monthly is not None:
                    print(f"  Estimated monthly cost ({calls_per_day:,} calls/day): \033[1m${monthly:,.2f}\033[0m")
                    print()

            alternatives = get_alternatives(model)
            if alternatives:
                print("  \033[32mCheaper alternatives:\033[0m")
                for alt in alternatives:
                    savings_str = f"{alt['savings_pct']:.0f}% savings"
                    print(f"    {alt['model']:30s} — ${alt['price']:.3f}/1M tokens ({savings_str})")

                    if calls_per_day:
                        alt_monthly = estimate_monthly_cost(alt["model"], calls_per_day)
                        if alt_monthly is not None and monthly:
                            saved = monthly - alt_monthly
                            print(f"    {'':30s}   Est. monthly: ${alt_monthly:,.2f} (save ${saved:,.2f}/mo)")
                print()
            else:
                print("  \033[32mAlready using one of the cheapest options!\033[0m")
                print()

    print("  Run '\033[1mnerq savings --estimate 10000\033[0m' to estimate costs for 10K calls/day.")
    print()

    # Try to report to API for analytics
    try:
        payload = json.dumps({
            "providers": list(results.keys()),
            "file_count": sum(len(d["files"]) for d in results.values()),
        }).encode()
        req = Request(
            f"{API_BASE}/v1/analytics/savings-scan",
            data=payload,
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            method="POST",
        )
        urlopen(req, timeout=3)
    except Exception:
        pass
