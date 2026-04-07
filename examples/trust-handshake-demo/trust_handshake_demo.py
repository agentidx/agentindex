#!/usr/bin/env python3
"""
Trust Handshake Demo — Two agents verify each other through Nerq.

Shows how Agent A (researcher) checks trust before delegating to Agent B.
Uses real Nerq API data.

Usage: python trust_handshake_demo.py
"""
import requests
import json
import sys

NERQ_API = "https://nerq.ai"
THRESHOLD = 70

def preflight_check(agent_name: str, caller: str = "demo-researcher") -> dict:
    """Call Nerq preflight to check an agent's trust score."""
    try:
        resp = requests.get(
            f"{NERQ_API}/v1/preflight",
            params={"target": agent_name, "caller": caller},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        return {"target": agent_name, "trust_score": None, "recommendation": "UNKNOWN"}
    except Exception as e:
        return {"target": agent_name, "trust_score": None, "recommendation": "UNKNOWN", "error": str(e)}

def trust_gate(result: dict, threshold: int = THRESHOLD) -> bool:
    """Apply trust gate: approve if score >= threshold."""
    score = result.get("trust_score")
    if score is None:
        return False
    return score >= threshold

def main():
    print("=" * 60)
    print("  Nerq Trust Handshake Demo")
    print("  Agent A (researcher) verifying agents before delegation")
    print("=" * 60)

    # Real agents from the Nerq index
    candidates = ["langchain", "crewai", "autogpt", "SWE-agent", "gpt-researcher"]

    print(f"\nThreshold: {THRESHOLD}")
    print(f"Candidates: {', '.join(candidates)}\n")

    approved = []
    rejected = []

    for name in candidates:
        print(f"  Checking {name}...")
        result = preflight_check(name)
        score = result.get("trust_score")
        grade = result.get("trust_grade", "?")
        rec = result.get("recommendation", "UNKNOWN")

        passed = trust_gate(result)
        status = "APPROVED" if passed else "REJECTED"
        icon = "✓" if passed else "✗"

        score_str = f"{score:.1f}" if score else "N/A"
        print(f"    {icon} {name}: score={score_str}, grade={grade}, rec={rec} → {status}")

        if passed:
            approved.append(name)
        else:
            rejected.append(name)

    print(f"\n{'=' * 60}")
    print(f"  Results: {len(approved)} approved, {len(rejected)} rejected")
    if approved:
        print(f"  Delegating to: {approved[0]}")
    else:
        print(f"  No trusted agents found. Aborting delegation.")
    print(f"{'=' * 60}")

    # Show the protocol flow
    print(f"\n  Protocol flow:")
    print(f"  1. Agent A discovered {len(candidates)} candidate agents")
    print(f"  2. Agent A called GET /v1/preflight for each")
    print(f"  3. Trust gate (threshold={THRESHOLD}) approved {len(approved)}/{len(candidates)}")
    if approved:
        print(f"  4. Agent A delegates task to {approved[0]}")
    print(f"\n  Spec: https://nerq.ai/protocol")
    print(f"  Integrate: https://nerq.ai/integrate")

if __name__ == "__main__":
    main()
