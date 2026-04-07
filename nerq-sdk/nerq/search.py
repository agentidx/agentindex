"""Search AI agents and tools by keyword."""

import json
import urllib.request
import urllib.parse

API_URL = "https://nerq.ai"


def search(query, min_trust=0, limit=10, api_url=None):
    """Search for AI agents and tools.

    Args:
        query: Search keywords
        min_trust: Minimum trust score (0-100)
        limit: Max results (default 10)
        api_url: Override API URL

    Returns:
        list of dicts with name, trust_score, grade, description, source
    """
    base = api_url or API_URL
    params = urllib.parse.urlencode({
        "q": query,
        "min_trust": str(min_trust),
        "limit": str(limit),
    })
    url = f"{base}/v1/search?{params}"
    data = json.loads(urllib.request.urlopen(url, timeout=10).read())
    return data.get("results", [])
