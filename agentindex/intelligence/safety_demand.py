"""
safety_demand.py — Google autocomplete demand signal for AI tool safety queries.

Checks "is X safe" autocomplete for 200+ AI tools, cross-references with
our agents database (trust_score, stars), and ranks by safety demand.

Output: ~/agentindex/data/safety_demand_ranking.json
"""

import json
import time
import sqlite3
import re
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Tool list
# ---------------------------------------------------------------------------

TOOLS = [
    "cursor", "copilot", "github copilot", "tabnine", "codeium", "windsurf",
    "cody", "continue dev", "replit agent", "devin", "bolt new", "lovable",
    "v0", "claude code", "aider", "sweep ai", "chatgpt", "claude", "gemini",
    "perplexity", "mistral", "groq", "together ai", "replicate", "huggingface",
    "langchain", "crewai", "autogen", "llamaindex", "semantic kernel",
    "haystack", "dspy", "smolagents", "mastra", "pydantic ai",
    "auto-gpt", "babyagi", "swe-agent", "open interpreter",
    "taskweaver", "camel ai", "metagpt", "superagent",
    "bolt.new", "lovable dev", "windsurf ai",
    "cursor ai", "cline", "zed ai", "sourcegraph", "coderabbit",
    "qodo", "codium ai", "phind", "blackbox ai", "pieces",
    "mcp server", "claude mcp", "cursor mcp",
    "openai", "anthropic", "cohere", "fireworks ai",
    "n8n", "zapier ai", "make ai", "activepieces",
    "vercel ai", "next js ai", "supabase ai",
    "ollama", "lmstudio", "jan ai", "gpt4all", "koboldcpp",
    "stable diffusion", "comfyui", "automatic1111", "fooocus",
    "midjourney", "dall-e", "flux ai", "ideogram",
    "notion ai", "grammarly", "jasper ai", "copy ai", "writesonic",
    "otter ai", "fireflies ai", "tldv", "krisp",
    "runway ml", "pika", "kling ai", "sora", "luma ai",
    "character ai", "pi ai", "poe", "you com",
    "github actions ai", "vercel v0", "replit", "gitpod",
    "pinecone", "weaviate", "qdrant", "chroma", "milvus",
    "modal", "anyscale", "ray", "weights biases",
    "langsmith", "helicone", "promptlayer",
]

# Deduplicate while preserving order
seen = set()
TOOLS_DEDUPED = []
for t in TOOLS:
    k = t.lower().strip()
    if k not in seen:
        seen.add(k)
        TOOLS_DEDUPED.append(t)

TOOLS = TOOLS_DEDUPED

# ---------------------------------------------------------------------------
# Google autocomplete fetcher
# ---------------------------------------------------------------------------

AUTOCOMPLETE_URL = (
    "https://suggestqueries.google.com/complete/search"
    "?client=firefox&hl=en&q={query}"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
}

DELAY_SECONDS = 0.3


def fetch_autocomplete(tool: str) -> tuple[bool, list[str]]:
    """
    Query Google autocomplete for 'is {tool} safe'.
    Returns (has_safe_suggestion, all_suggestions).
    """
    query = f"is {tool} safe"
    encoded = urllib.parse.quote(query)
    url = AUTOCOMPLETE_URL.format(query=encoded)

    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8")

        data = json.loads(raw)
        # Firefox client returns: ["query", ["sug1", "sug2", ...], ...]
        suggestions = data[1] if len(data) > 1 else []
        if not isinstance(suggestions, list):
            suggestions = []

        # Normalise to strings
        suggestions = [str(s).lower() for s in suggestions]

        # Check if any suggestion contains "safe" (or related safety terms)
        safe_terms = ("safe", "safety", "secure", "privacy", "malware", "virus")
        has_safe = any(
            any(term in s for term in safe_terms)
            for s in suggestions
        )

        return has_safe, [str(s) for s in data[1]] if len(data) > 1 else []

    except Exception as exc:
        print(f"  [warn] autocomplete failed for '{tool}': {exc}")
        return False, []


# ---------------------------------------------------------------------------
# Database cross-reference
# ---------------------------------------------------------------------------

DB_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"


def load_db_signals() -> dict[str, dict]:
    """
    Pull trust_score and stars from agent_trends (best available SQLite source).
    Returns dict keyed by lowercase normalised name.
    """
    signals: dict[str, dict] = {}

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # agent_trends stores stars + trust_score in details JSON
        cur.execute(
            "SELECT agent_name, details FROM agent_trends "
            "WHERE trend_type='popularity_surge' ORDER BY magnitude DESC"
        )
        for row in cur.fetchall():
            agent_name, details_str = row
            try:
                details = json.loads(details_str) if details_str else {}
            except Exception:
                details = {}

            stars = details.get("stars", 0) or 0
            trust_score = details.get("trust_score", None)

            # Normalise the repo-style name (e.g. "Significant-Gravitas/AutoGPT" → "autogpt")
            parts = agent_name.split("/")
            short = parts[-1].lower().replace("-", " ").replace("_", " ").strip()
            full_lower = agent_name.lower()

            record = {
                "agent_name": agent_name,
                "trust_score": trust_score,
                "stars": stars,
            }

            # Index under multiple aliases for fuzzy matching
            for key in [short, full_lower, parts[-1].lower()]:
                if key not in signals or stars > signals[key].get("stars", 0):
                    signals[key] = record

        # Also pull from package_downloads for weekly_downloads proxy
        cur.execute(
            "SELECT package_name, weekly_downloads FROM package_downloads "
            "ORDER BY weekly_downloads DESC"
        )
        for row in cur.fetchall():
            pkg, wdl = row
            key = pkg.lower().replace("-", " ").replace("_", " ").strip()
            if key in signals:
                signals[key]["weekly_downloads"] = wdl or 0
            else:
                signals[key] = {
                    "agent_name": pkg,
                    "trust_score": None,
                    "stars": 0,
                    "weekly_downloads": wdl or 0,
                }

        conn.close()
    except Exception as exc:
        print(f"[warn] DB load failed: {exc}")

    return signals


def match_db(tool: str, db_signals: dict) -> dict:
    """
    Try to find a db record for this tool name.
    Uses a series of normalisation fallbacks.
    """
    # Normalisation candidates
    tool_lower = tool.lower().strip()
    tool_nospace = tool_lower.replace(" ", "")
    tool_dash = tool_lower.replace(" ", "-")
    tool_words = tool_lower.split()

    candidates = [
        tool_lower,
        tool_nospace,
        tool_dash,
        # Just the last word (e.g. "cursor ai" → "cursor")
        tool_words[-1] if tool_words else "",
        # First word
        tool_words[0] if tool_words else "",
    ]

    for candidate in candidates:
        if candidate and candidate in db_signals:
            return db_signals[candidate]

    # Substring match: check if any key starts with tool_lower or vice-versa
    for key, rec in db_signals.items():
        if tool_lower in key or key in tool_lower:
            return rec

    return {}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Safety Demand Ranker — {len(TOOLS)} tools")
    print(f"Loading DB signals from {DB_PATH} ...")
    db_signals = load_db_signals()
    print(f"  Loaded {len(db_signals)} DB signal keys")

    results = []
    total = len(TOOLS)

    for i, tool in enumerate(TOOLS, 1):
        print(f"  [{i:3d}/{total}] checking '{tool}' ...", end=" ", flush=True)

        has_safe, suggestions = fetch_autocomplete(tool)
        db_rec = match_db(tool, db_signals)

        entry = {
            "tool": tool,
            "has_safe_autocomplete": has_safe,
            "suggestions": suggestions,
            "trust_score": db_rec.get("trust_score"),
            "stars": db_rec.get("stars", 0) or 0,
            "weekly_downloads": db_rec.get("weekly_downloads", 0) or 0,
            "db_agent_name": db_rec.get("agent_name"),
        }

        status = "YES" if has_safe else "no"
        print(f"{status} | stars={entry['stars']:,} | suggestions={len(suggestions)}")
        results.append(entry)

        time.sleep(DELAY_SECONDS)

    # ---------------------------------------------------------------------------
    # Ranking: has_safe_autocomplete DESC → stars DESC → weekly_downloads DESC
    # ---------------------------------------------------------------------------
    results.sort(
        key=lambda r: (
            1 if r["has_safe_autocomplete"] else 0,
            r["stars"],
            r["weekly_downloads"],
        ),
        reverse=True,
    )

    # Add rank
    for rank, entry in enumerate(results, 1):
        entry["rank"] = rank

    # ---------------------------------------------------------------------------
    # Save
    # ---------------------------------------------------------------------------
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tools_checked": len(results),
        "has_safe_autocomplete_count": sum(1 for r in results if r["has_safe_autocomplete"]),
        "top_30": results[:30],
        "all": results,
    }

    out_path = Path("/Users/anstudio/agentindex/data/safety_demand_ranking.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nSaved → {out_path}")

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------
    safe_count = output["has_safe_autocomplete_count"]
    print(f"\n{'='*60}")
    print(f"Tools checked        : {len(results)}")
    print(f"Has 'safe' autocomplete: {safe_count} / {len(results)} "
          f"({100 * safe_count / len(results):.1f}%)")
    print(f"\nTop 30 by demand ranking:")
    print(f"{'Rank':<5} {'Tool':<25} {'Safe?':<7} {'Stars':>8}  {'Trust':>6}  Suggestions")
    print("-" * 80)
    for r in results[:30]:
        safe_flag = "YES" if r["has_safe_autocomplete"] else "no"
        trust_str = f"{r['trust_score']:.1f}" if r["trust_score"] else "  n/a"
        sugg_preview = " | ".join(r["suggestions"][:2])
        print(
            f"{r['rank']:<5} {r['tool']:<25} {safe_flag:<7} "
            f"{r['stars']:>8,}  {trust_str:>6}  {sugg_preview}"
        )

    return output


if __name__ == "__main__":
    main()
