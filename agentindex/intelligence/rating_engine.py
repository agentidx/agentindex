"""
Universal AI Stack Rating Engine
==================================
Rates any entity based on their AI tool usage.

Rating Scale (Moody's-inspired):
  AAA: 95-100  AA: 85-94  A: 75-84  BBB: 65-74
  BB: 55-64    B: 45-54   CCC: 30-44  CC: 15-29  C: 0-14
"""

import logging

logger = logging.getLogger("nerq.rating_engine")


def score_to_rating(score: float) -> str:
    if score >= 95: return "AAA"
    if score >= 85: return "AA"
    if score >= 75: return "A"
    if score >= 65: return "BBB"
    if score >= 55: return "BB"
    if score >= 45: return "B"
    if score >= 30: return "CCC"
    if score >= 15: return "CC"
    return "C"


def rating_color(rating: str) -> str:
    return {"AAA": "#16a34a", "AA": "#16a34a", "A": "#0d9488",
            "BBB": "#ca8a04", "BB": "#f59e0b", "B": "#f97316",
            "CCC": "#dc2626", "CC": "#dc2626", "C": "#7f1d1d"}.get(rating, "#6b7280")


def rate_entity(tools_found: list, metadata: dict = None) -> dict:
    """
    Rate an entity based on discovered AI tools.

    tools_found: list of dicts with keys: name, trust_score, grade, category, stars, downloads, issues
    metadata: optional dict with entity context

    Returns full rating dict.
    """
    metadata = metadata or {}
    repos_scanned = metadata.get("repos_scanned", 0)

    if not tools_found:
        # No tools found — distinguish between "no data" and "genuinely no AI"
        disclaimer = "No AI tools discovered in public repositories."
        if repos_scanned > 50:
            disclaimer += " Large org scanned — AI tools may exist in private repos."
        return {
            "rating": "NR", "score": 0, "tools_analyzed": 0,
            "rating_qualifier": "insufficient_data",
            "dependencies_total": 0, "critical_issues": 0, "health_warnings": 0,
            "tool_breakdown": [],
            "risk_factors": [{"severity": "INFO", "description": disclaimer}],
            "predictions": {}, "compliance_signals": {},
        }

    # Preliminary rating qualifier for limited data
    rating_qualifier = "full"
    if len(tools_found) < 3:
        rating_qualifier = "preliminary"

    # Calculate component scores
    trust_scores = [t.get("trust_score") or 0 for t in tools_found]
    avg_trust = sum(trust_scores) / len(trust_scores) if trust_scores else 0

    # Count issues
    critical = sum(1 for t in tools_found if (t.get("trust_score") or 0) < 30)
    warnings = sum(1 for t in tools_found if 30 <= (t.get("trust_score") or 0) < 50)
    high_trust = sum(1 for t in tools_found if (t.get("trust_score") or 0) >= 70)

    # Diversity score (how many different categories)
    categories = set(t.get("category") or "unknown" for t in tools_found)
    diversity_score = min(20, len(categories) * 4)

    # Maintenance score (proportion with good trust)
    maintenance_score = (high_trust / max(1, len(tools_found))) * 30

    # Risk penalty
    risk_penalty = critical * 5 + warnings * 2

    # Volume bonus (more tools = more sophisticated stack)
    volume_bonus = min(15, len(tools_found) * 0.5)

    # Composite score
    score = avg_trust * 0.4 + diversity_score + maintenance_score + volume_bonus - risk_penalty
    score = max(0, min(100, score))

    # For preliminary ratings (1-2 tools), apply a floor so we don't unfairly penalize
    # Entities with few detected tools are likely incomplete scans, not bad stacks
    if rating_qualifier == "preliminary" and score < 40:
        score = max(score, 40)  # Floor at BB- for preliminary ratings

    rating = score_to_rating(score)

    # Build risk factors
    risk_factors = []
    single_maintainer = [t for t in tools_found if (t.get("stars") or 0) > 1000 and (t.get("trust_score") or 0) < 50]
    if single_maintainer:
        risk_factors.append({"severity": "HIGH", "description": f"{len(single_maintainer)} popular but low-trust dependencies"})

    low_trust_tools = [t["name"] for t in tools_found if (t.get("trust_score") or 0) < 40]
    if low_trust_tools:
        risk_factors.append({"severity": "MEDIUM", "description": f"Low-trust tools: {', '.join(low_trust_tools[:5])}"})

    if len(tools_found) < 3:
        risk_factors.append({"severity": "INFO",
                            "description": f"Preliminary rating — only {len(tools_found)} AI tool(s) detected from "
                                          f"{repos_scanned} public repos. Rating may not reflect complete internal AI stack."})

    # Predictions
    at_risk = sum(1 for t in tools_found if (t.get("trust_score") or 0) < 50)
    predictions = {
        "components_at_risk_6m": at_risk,
        "predicted_incidents_12m": round(at_risk * 0.7, 1),
        "weakest_link": min(tools_found, key=lambda t: t.get("trust_score") or 0)["name"] if tools_found else None,
        "weakest_link_trust": min(t.get("trust_score") or 0 for t in tools_found) if tools_found else 0,
    }

    # Sort tool breakdown by trust score
    tool_breakdown = sorted(tools_found, key=lambda t: t.get("trust_score") or 0, reverse=True)

    return {
        "rating": rating,
        "rating_qualifier": rating_qualifier,
        "score": round(score, 1),
        "tools_analyzed": len(tools_found),
        "dependencies_total": sum(t.get("deps", 0) for t in tools_found),
        "critical_issues": critical,
        "health_warnings": warnings,
        "tool_breakdown": tool_breakdown,
        "risk_factors": risk_factors,
        "predictions": predictions,
        "compliance_signals": metadata.get("compliance", {}),
    }
