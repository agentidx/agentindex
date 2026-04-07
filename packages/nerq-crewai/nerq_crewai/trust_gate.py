"""
trust_gate — Intercept CrewAI tool calls with Nerq preflight trust checks.
"""

import logging
import time
from functools import wraps
from typing import Optional

import requests

logger = logging.getLogger("nerq.trust_gate")

NERQ_API = "https://nerq.ai"
PREFLIGHT_TIMEOUT = 5.0
CACHE_TTL = 300  # 5 minutes


class TrustError(Exception):
    """Raised when a tool call is denied due to low trust score."""

    def __init__(self, tool_name: str, trust_score: Optional[float], recommendation: str):
        self.tool_name = tool_name
        self.trust_score = trust_score
        self.recommendation = recommendation
        super().__init__(
            f"Trust gate denied '{tool_name}': "
            f"trust={trust_score}, recommendation={recommendation}"
        )


class _PreflightCache:
    """Simple TTL cache for preflight results."""

    def __init__(self, ttl: int = CACHE_TTL):
        self._cache: dict[str, tuple[dict, float]] = {}
        self._ttl = ttl

    def get(self, key: str) -> Optional[dict]:
        if key in self._cache:
            result, ts = self._cache[key]
            if time.time() - ts < self._ttl:
                return result
            del self._cache[key]
        return None

    def set(self, key: str, value: dict):
        self._cache[key] = (value, time.time())
        if len(self._cache) > 5000:
            self._cache.clear()


_cache = _PreflightCache()


def _preflight_check(
    target: str,
    caller: Optional[str] = None,
    api_base: str = NERQ_API,
) -> dict:
    """Run preflight trust check against Nerq API."""
    cached = _cache.get(target.lower())
    if cached:
        return cached

    try:
        params = {"target": target}
        if caller:
            params["caller"] = caller
        resp = requests.get(
            f"{api_base}/v1/preflight",
            params=params,
            timeout=PREFLIGHT_TIMEOUT,
        )
        resp.raise_for_status()
        result = resp.json()
        _cache.set(target.lower(), result)
        return result
    except Exception as e:
        logger.warning(f"Nerq preflight unreachable for '{target}': {e}")
        return {
            "target": target,
            "target_trust": None,
            "target_grade": None,
            "recommendation": "UNKNOWN",
            "interaction_risk": "UNKNOWN",
            "_error": str(e),
        }


def trust_gate_crew(
    crew,
    min_trust: float = 60,
    caller: Optional[str] = None,
    api_base: str = NERQ_API,
):
    """Wrap all agents' tools in a CrewAI Crew with Nerq trust-gating.

    Before each tool invocation, the tool's trust score is checked via the
    Nerq preflight API.

    - DENY (trust < 40): raises TrustError
    - CAUTION (trust 40-69): logs warning, proceeds
    - PROCEED (trust >= 70): proceeds silently
    - UNKNOWN (not found / API unreachable): proceeds with warning

    Args:
        crew: A CrewAI Crew instance.
        min_trust: Minimum trust score to allow (default 60).
            Tools below this raise TrustError.
        caller: Optional caller agent name for interaction risk calculation.
        api_base: Nerq API base URL (default https://nerq.ai).

    Returns:
        The same Crew instance with trust-gated tools.
    """

    def _check_tool(tool_name: str):
        """Check a tool's trust before allowing the call."""
        result = _preflight_check(tool_name, caller=caller, api_base=api_base)
        recommendation = result.get("recommendation", "UNKNOWN")
        trust = result.get("target_trust")

        if recommendation == "DENY":
            raise TrustError(tool_name, trust, recommendation)

        if trust is not None and trust < min_trust:
            raise TrustError(tool_name, trust, f"BELOW_MIN_TRUST ({min_trust})")

        if recommendation == "CAUTION":
            logger.warning(
                f"Nerq trust gate: CAUTION for '{tool_name}' "
                f"(trust={trust}, grade={result.get('target_grade')})"
            )

        if recommendation == "UNKNOWN":
            logger.warning(
                f"Nerq trust gate: '{tool_name}' not found in index, proceeding anyway"
            )

    # Iterate over every agent in the crew and wrap their tools
    for agent in crew.agents:
        if not hasattr(agent, "tools") or not agent.tools:
            continue

        for tool in agent.tools:
            original_run = tool._run

            @wraps(original_run)
            def _gated_run(*args, _orig=original_run, _name=tool.name, **kwargs):
                _check_tool(_name)
                return _orig(*args, **kwargs)

            tool._run = _gated_run

            if hasattr(tool, "_arun"):
                original_arun = tool._arun

                @wraps(original_arun)
                async def _gated_arun(*args, _orig=original_arun, _name=tool.name, **kwargs):
                    _check_tool(_name)
                    return await _orig(*args, **kwargs)

                tool._arun = _gated_arun

    return crew
