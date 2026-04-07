"""Preflight trust check for AI agents."""

import json
import urllib.request
import urllib.parse

API_URL = "https://nerq.ai"


def preflight(target, caller=None, api_url=None):
    """Check trust score for an agent before using it.

    Args:
        target: Agent name to check
        caller: Calling agent name (optional)
        api_url: Override API URL

    Returns:
        dict with target_trust, target_grade, recommendation, security, alternatives
    """
    base = api_url or API_URL
    params = urllib.parse.urlencode({
        k: v for k, v in {"target": target, "caller": caller}.items() if v
    })
    url = f"{base}/v1/preflight?{params}"
    return json.loads(urllib.request.urlopen(url, timeout=10).read())
