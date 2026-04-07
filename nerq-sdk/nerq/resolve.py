"""Find the best tool for any task. One call, one answer."""

import json
import urllib.request
import urllib.parse

API_URL = "https://nerq.ai"


def resolve(task, min_trust=60, client=None, framework=None, api_url=None):
    """Find the best tool for a task.

    Args:
        task: What you need to do (e.g., "search github repos")
        min_trust: Minimum trust score (0-100, default 60)
        client: Client environment (claude, cursor, vscode)
        framework: Framework requirement (langchain, crewai, etc.)
        api_url: Override API URL (default: https://nerq.ai)

    Returns:
        dict with recommendation (name, trust_score, grade, install instructions)
    """
    base = api_url or API_URL
    params = urllib.parse.urlencode({
        k: v for k, v in {
            "task": task,
            "min_trust": str(min_trust),
            "client": client,
            "framework": framework,
        }.items() if v is not None
    })
    url = f"{base}/v1/resolve?{params}"
    data = json.loads(urllib.request.urlopen(url, timeout=10).read())
    return data.get("recommendation", {})
