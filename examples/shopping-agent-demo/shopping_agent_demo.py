#!/usr/bin/env python3
"""
Shopping Agent Demo — Trust-Verified Agentic Commerce
=====================================================
Demonstrates an AI shopping agent using Nerq Commerce to verify
seller trust before purchasing.

Usage:
    python shopping_agent_demo.py
"""

import json
import sys
import time

import requests

NERQ_API = "https://nerq.ai"

# Simulated sellers (real agents from Nerq's index)
SELLERS = [
    {"name": "promptfoo/promptfoo", "service": "LLM evaluation & testing", "price": 49.99},
    {"name": "getzep/graphiti", "service": "Knowledge graph memory", "price": 29.99},
    {"name": "microsoft/qlib", "service": "Quantitative finance toolkit", "price": 79.99},
    {"name": "brainy-brew-trivia-tavern", "service": "Trivia game hosting", "price": 9.99},
    {"name": "kc-llama", "service": "Small language model inference", "price": 19.99},
]

TRUST_THRESHOLD = 60  # Minimum trust score to approve


def verify_seller(agent_name: str, buyer_name: str = "shopping-agent") -> dict:
    """Verify seller trust via Nerq Commerce API."""
    try:
        resp = requests.post(
            f"{NERQ_API}/v1/commerce/verify",
            json={
                "agent_id": buyer_name,
                "counterparty_id": agent_name,
                "transaction_type": "purchase",
                "amount_range": "low",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        pass

    # Fallback: use KYA endpoint
    try:
        resp = requests.get(
            f"{NERQ_API}/v1/agent/kya/{agent_name}",
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            trust = data.get("trust_score") or data.get("trust_score_v2") or 0
            return {
                "verdict": "approve" if trust >= TRUST_THRESHOLD else "reject",
                "counterparty_trust_score": trust,
                "agent_trust_score": None,
                "risk_factors": [],
            }
    except Exception:
        pass

    return {"verdict": "review", "counterparty_trust_score": None, "risk_factors": ["API unreachable"]}


def run_demo():
    """Run the shopping agent demo."""
    item = "GPU compute time for model fine-tuning"

    print("=" * 60)
    print("  NERQ COMMERCE — Shopping Agent Demo")
    print("=" * 60)
    print()
    print(f"  Shopping Agent wants to buy: {item}")
    print(f"  Trust threshold: {TRUST_THRESHOLD}/100")
    print(f"  Checking {len(SELLERS)} potential sellers...")
    print()
    print("-" * 60)

    approved = []
    results = []

    for seller in SELLERS:
        name = seller["name"]
        print(f"\n  Checking seller: {name}")
        print(f"  Service: {seller['service']} (${seller['price']:.2f})")

        t0 = time.time()
        verification = verify_seller(name)
        elapsed = (time.time() - t0) * 1000

        trust = verification.get("counterparty_trust_score")
        verdict = verification.get("verdict", "unknown")
        risk_factors = verification.get("risk_factors", [])

        trust_str = f"{trust:.0f}/100" if trust is not None else "N/A"
        status = "APPROVED" if verdict == "approve" else "REJECTED" if verdict == "reject" else "REVIEW"
        icon = "+" if verdict == "approve" else "x" if verdict == "reject" else "?"

        print(f"  Trust: {trust_str}  |  Verdict: {status} [{icon}]  |  {elapsed:.0f}ms")
        if risk_factors:
            print(f"  Risk factors: {', '.join(risk_factors)}")

        result = {
            "seller": name,
            "service": seller["service"],
            "price": seller["price"],
            "trust_score": trust,
            "verdict": verdict,
            "risk_factors": risk_factors,
            "response_ms": round(elapsed),
        }
        results.append(result)

        if verdict == "approve" and trust is not None:
            approved.append((trust, seller, result))

    print()
    print("-" * 60)

    if approved:
        # Select highest-trust approved seller
        approved.sort(key=lambda x: x[0], reverse=True)
        best_trust, best_seller, best_result = approved[0]
        print(f"\n  >> Selected: {best_seller['name']}")
        print(f"     Trust Score: {best_trust:.0f}/100")
        print(f"     Service: {best_seller['service']}")
        print(f"     Price: ${best_seller['price']:.2f}")
        print(f"     Reason: Highest trusted approved seller")
    else:
        print("\n  >> No sellers passed trust verification.")
        print("     The shopping agent will not proceed with any purchase.")

    print()
    print("=" * 60)
    print("  Demo complete. Results:")
    print(f"  {len(approved)} approved / {len(results)} checked")
    print("=" * 60)

    return {
        "item": item,
        "threshold": TRUST_THRESHOLD,
        "sellers_checked": len(results),
        "sellers_approved": len(approved),
        "selected": best_seller["name"] if approved else None,
        "results": results,
    }


if __name__ == "__main__":
    run_demo()
