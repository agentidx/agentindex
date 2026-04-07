"""
Question Generator (BUILD 10A)
===============================
Generates answerable questions for top tools using template patterns.
No external API calls — uses templates + DB data to create SEO-valuable Q&A pages.

Usage:
    python -m agentindex.intelligence.question_generator
"""

import json
import logging
import re
import sys
from pathlib import Path

from sqlalchemy.sql import text

from agentindex.db.models import get_db_session

logger = logging.getLogger("nerq.question_gen")

DATA_DIR = Path(__file__).parent.parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "generated_questions.json"

QUERY_TEMPLATES = [
    ("is {tool} safe", "safety"),
    ("is {tool} free", "pricing"),
    ("is {tool} open source", "licensing"),
    ("is {tool} secure", "safety"),
    ("is {tool} good", "review"),
    ("is {tool} worth it", "review"),
    ("is {tool} better than", "comparison"),
    ("does {tool} have vulnerabilities", "safety"),
    ("does {tool} support python", "compatibility"),
    ("does {tool} cost money", "pricing"),
    ("can {tool} be trusted", "safety"),
    ("can {tool} be used commercially", "licensing"),
    ("can {tool} be self hosted", "deployment"),
    ("what is {tool}", "overview"),
    ("what is {tool} used for", "overview"),
    ("what license is {tool}", "licensing"),
    ("how to install {tool}", "setup"),
    ("how to use {tool}", "setup"),
    ("how secure is {tool}", "safety"),
    ("{tool} alternatives", "alternatives"),
    ("{tool} vs", "comparison"),
    ("{tool} pricing", "pricing"),
    ("{tool} security", "safety"),
    ("{tool} review", "review"),
    ("{tool} trust score", "safety"),
    ("{tool} dependencies", "safety"),
    ("{tool} license", "licensing"),
    ("{tool} vulnerabilities", "safety"),
]


def _to_slug(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _clean_name(name: str) -> str:
    """Extract short display name from full repo name."""
    if "/" in name:
        name = name.split("/")[-1]
    return name.replace("-", " ").replace("_", " ").strip()


def generate_questions(limit: int = 200) -> list[dict]:
    """Generate answerable questions for top tools."""
    with get_db_session() as session:
        rows = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade, stars, category, license,
                   description, source, security_score, downloads
            FROM entity_lookup
            WHERE is_active = true AND trust_score_v2 IS NOT NULL
            ORDER BY COALESCE(stars, 0) DESC
            LIMIT :lim
        """), {"lim": limit}).fetchall()

    cols = ["name", "score", "grade", "stars", "category", "license",
            "description", "source", "security_score", "downloads"]
    tools = [dict(zip(cols, r)) for r in rows]

    questions = []
    seen_slugs = set()

    for tool in tools:
        full_name = tool["name"]
        short_name = _clean_name(full_name)
        slug_base = _to_slug(full_name)

        for template, qtype in QUERY_TEMPLATES:
            question_text = template.format(tool=short_name)
            slug = _to_slug(question_text)

            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            # Generate answer based on question type and tool data
            answer = _generate_answer(question_text, qtype, tool, short_name)
            if not answer:
                continue

            questions.append({
                "slug": slug,
                "question": question_text.title() if not question_text[0].isupper() else question_text,
                "type": qtype,
                "tool_name": full_name,
                "tool_display": short_name,
                "answer_short": answer["short"],
                "answer_detail": answer["detail"],
                "score": tool.get("score"),
                "grade": tool.get("grade"),
                "stars": tool.get("stars"),
                "priority": _priority_score(tool, qtype),
            })

    # Sort by priority (popular tools + high-value question types first)
    questions.sort(key=lambda q: q["priority"], reverse=True)

    return questions


def _priority_score(tool: dict, qtype: str) -> float:
    """Score question priority by estimated search volume."""
    stars = tool.get("stars") or 0
    base = min(100, stars / 1000)  # Normalize stars

    type_weights = {
        "safety": 1.5,
        "alternatives": 1.4,
        "comparison": 1.3,
        "review": 1.2,
        "pricing": 1.1,
        "licensing": 1.0,
        "overview": 0.9,
        "setup": 0.8,
        "compatibility": 0.7,
        "deployment": 0.7,
    }
    return base * type_weights.get(qtype, 0.8)


def _generate_answer(question: str, qtype: str, tool: dict, display: str) -> dict | None:
    """Generate structured answer from our data."""
    score = tool.get("score") or 0
    grade = tool.get("grade") or "N/A"
    lic = tool.get("license") or ""
    desc = tool.get("description") or ""
    stars = tool.get("stars") or 0
    sec = tool.get("security_score") or 0
    slug = _to_slug(tool["name"])

    if qtype == "safety":
        safe_word = "relatively safe" if score >= 70 else "moderate risk" if score >= 50 else "higher risk"
        return {
            "short": f"Based on independent analysis, {display} is **{safe_word}** with a Nerq Trust Score of {score:.0f}/100 (Grade {grade}). This score reflects security practices, maintenance activity, and community trust signals.",
            "detail": f"Security Score: {sec:.0f}/100. {display} has {stars:,} GitHub stars and is actively maintained. See the [full safety report](/is-{slug}-safe) for detailed analysis.",
        }

    if qtype == "pricing":
        is_free = lic and lic.lower() not in ("proprietary", "commercial", "unknown", "none", "other")
        if is_free:
            return {
                "short": f"**Yes, {display} is free.** It is open source under the {lic} license. You can use it without paying for the software itself.",
                "detail": f"While the software is free, some tools (like LLM frameworks) may require paid API keys for connected services. Trust Score: {score:.0f}/100.",
            }
        else:
            return {
                "short": f"{display} licensing information: {lic or 'Not specified'}. Check the project's official documentation for current pricing details.",
                "detail": f"Trust Score: {score:.0f}/100. Stars: {stars:,}.",
            }

    if qtype == "licensing":
        return {
            "short": f"{display} uses the **{lic or 'unspecified'}** license. {'This is a permissive license allowing commercial use.' if lic and 'mit' in lic.lower() else 'Check the license terms for your specific use case.'}",
            "detail": f"Trust Score: {score:.0f}/100. For full compliance details, see the [safety report](/is-{slug}-safe).",
        }

    if qtype == "review":
        quality = "excellent" if score >= 85 else "good" if score >= 70 else "average" if score >= 50 else "below average"
        return {
            "short": f"{display} receives an **{quality}** independent trust rating of {score:.0f}/100 (Grade {grade}) from Nerq, based on security, maintenance, documentation, and community metrics.",
            "detail": f"Stars: {stars:,}. {desc[:200] if desc else ''} See [alternatives](/alternatives/{slug}) and [full report](/is-{slug}-safe).",
        }

    if qtype == "alternatives":
        return {
            "short": f"Top alternatives to {display} are ranked by independent trust scores on Nerq. The best alternatives are tools in the same category ({tool.get('category') or 'general'}) with high security and maintenance ratings.",
            "detail": f"{display} scores {score:.0f}/100. See the [full alternatives list](/alternatives/{slug}) ranked by trust.",
        }

    if qtype == "comparison":
        return {
            "short": f"{display} scores {score:.0f}/100 on the Nerq Trust Score. Compare it side-by-side with alternatives using independent security and reliability metrics.",
            "detail": f"Use [Nerq Compare](/compare) to see {display} vs any other tool.",
        }

    if qtype == "overview":
        return {
            "short": f"{display} is a {tool.get('category') or 'tool'} with {stars:,} GitHub stars and a Nerq Trust Score of {score:.0f}/100. {desc[:150] if desc else ''}",
            "detail": f"See the [complete guide](/guide/{slug}) and [safety report](/is-{slug}-safe).",
        }

    if qtype == "setup":
        src = tool.get("source") or "unknown"
        return {
            "short": f"To get started with {display}, visit the project on {src}. The tool is {'open source' if lic else 'available'} and has {stars:,} community stars.",
            "detail": f"See the [complete setup guide](/guide/{slug}) for installation instructions and security considerations.",
        }

    if qtype in ("compatibility", "deployment"):
        return {
            "short": f"{display} details are available in its [full guide](/guide/{slug}). Trust Score: {score:.0f}/100.",
            "detail": f"Stars: {stars:,}. Category: {tool.get('category') or 'general'}.",
        }

    return None


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logger.info("Generating questions...")

    questions = generate_questions(limit=500)
    logger.info(f"Generated {len(questions)} unique answerable questions")

    # Save all
    top = questions
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(top, f, indent=2)

    logger.info(f"Saved {len(top)} questions to {OUTPUT_FILE}")

    # Stats
    by_type = {}
    for q in top:
        by_type[q["type"]] = by_type.get(q["type"], 0) + 1
    for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
        logger.info(f"  {t}: {c}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
