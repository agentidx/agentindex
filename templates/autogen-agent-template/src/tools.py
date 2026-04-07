"""Dynamic tool discovery via Nerq Resolve."""
import nerq
import os

MIN_TRUST = int(os.getenv("NERQ_MIN_TRUST", "70"))


def get_tools_for_task(task: str, framework: str = "autogen"):
    """Find the best tools for a task. One call, trust-verified."""
    result = nerq.resolve(task, framework=framework, min_trust=MIN_TRUST)
    if result:
        print(f"  Found: {result.get('name')} (Trust: {result.get('trust_score')})")
    return result


def verify_tool_trust(name: str):
    """Verify a tool is trusted before registering it."""
    result = nerq.preflight(name)
    trust = result.get("target_trust", 0)
    if result.get("recommendation") == "DENY":
        raise RuntimeError(f"{name} blocked: trust {trust}")
    return result
