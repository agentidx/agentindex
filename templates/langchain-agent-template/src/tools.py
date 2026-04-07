"""Dynamic tool discovery via Nerq Resolve."""
import nerq
import os

MIN_TRUST = int(os.getenv("NERQ_MIN_TRUST", "70"))


def get_tools_for_task(task: str, framework: str = "langchain"):
    """Find the best tools for a task. One call, trust-verified."""
    result = nerq.resolve(task, framework=framework, min_trust=MIN_TRUST)
    if result:
        print(f"  Found: {result.get('name')} (Trust: {result.get('trust_score')})")
    return result


def get_available_tools(tasks: list[str]):
    """Resolve multiple tools at once."""
    tools = []
    for task in tasks:
        tool = get_tools_for_task(task)
        if tool:
            tools.append(tool)
    return tools


def check_dependency(name: str):
    """Trust-check a dependency before importing it."""
    result = nerq.preflight(name)
    trust = result.get("target_trust", 0)
    rec = result.get("recommendation", "UNKNOWN")
    if rec == "DENY":
        raise RuntimeError(f"{name} blocked: trust {trust}, recommendation DENY")
    print(f"  {name}: trust {trust} ({result.get('target_grade', '?')}) — {rec}")
    return result
