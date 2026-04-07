"""
Seed initial editorial reviews for top agents.
Inserts factual reviews based on trust_components data.
"""

import os
import sys

# Ensure project is importable
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def main():
    database_url = os.getenv("DATABASE_URL", "postgresql://localhost/agentindex")
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Ensure table exists
    session.execute(text("""
        CREATE TABLE IF NOT EXISTS user_reviews (
            id SERIAL PRIMARY KEY,
            agent_name TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment TEXT,
            reviewer_name TEXT DEFAULT 'Anonymous',
            ip_hash TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            is_editorial BOOLEAN DEFAULT FALSE
        )
    """))
    session.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_user_reviews_agent ON user_reviews(agent_name)
    """))
    session.commit()

    # Get top 20 agents by trust score
    rows = session.execute(text("""
        SELECT name, COALESCE(trust_score_v2, trust_score) as trust_score,
               trust_grade, category, stars, trust_components,
               activity_score, security_score, documentation_score, popularity_score
        FROM agents
        WHERE is_active = true
          AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
          AND agent_type IN ('agent', 'mcp_server', 'tool')
        ORDER BY COALESCE(trust_score_v2, trust_score) DESC
        LIMIT 20
    """)).fetchall()

    seeded = 0
    for r in rows:
        agent = dict(r._mapping)
        name = agent["name"]
        score = float(agent["trust_score"] or 0)
        category = agent.get("category") or "uncategorized"
        stars_count = agent.get("stars") or 0
        activity = agent.get("activity_score")
        security = agent.get("security_score")
        doc_score = agent.get("documentation_score")
        popularity = agent.get("popularity_score")

        # Check if editorial review already exists
        existing = session.execute(text("""
            SELECT id FROM user_reviews
            WHERE agent_name = :name AND is_editorial = true
            LIMIT 1
        """), {"name": name}).fetchone()
        if existing:
            print(f"  Skip {name} — editorial review exists")
            continue

        # Determine rating
        if score >= 85:
            rating = 5
        elif score >= 70:
            rating = 4
        elif score >= 50:
            rating = 3
        else:
            rating = 2

        # Find top component
        sig_pairs = []
        if security is not None:
            sig_pairs.append(("security", float(security)))
        if activity is not None:
            sig_pairs.append(("maintenance", float(activity)))
        if doc_score is not None:
            sig_pairs.append(("documentation", float(doc_score)))
        if popularity is not None:
            sig_pairs.append(("popularity", float(popularity)))

        if sig_pairs:
            top_comp_name, top_comp_score = max(sig_pairs, key=lambda x: x[1])
        else:
            top_comp_name, top_comp_score = "trust", score

        # Maintenance status
        if activity and float(activity) >= 70:
            maint_status = "actively maintained"
        elif activity and float(activity) >= 40:
            maint_status = "moderately maintained"
        else:
            maint_status = "maintenance signals are limited"

        # Recommendation
        if score >= 85:
            recommendation = "Recommended for production use."
        elif score >= 70:
            recommendation = "Suitable for most use cases with standard due diligence."
        elif score >= 50:
            recommendation = "Review the full KYA report before production deployment."
        else:
            recommendation = "Exercise caution; consider higher-rated alternatives."

        # Build comment
        stars_text = f"{stars_count:,} community stars" if stars_count else "growing community"
        comment = (
            f"Strong {top_comp_name} ({top_comp_score:.0f}/100), {maint_status}. "
            f"{category} with {stars_text}. {recommendation}"
        )

        session.execute(text("""
            INSERT INTO user_reviews (agent_name, rating, comment, reviewer_name, ip_hash, is_editorial)
            VALUES (:name, :rating, :comment, 'Nerq Editorial', 'editorial', true)
        """), {"name": name, "rating": rating, "comment": comment})
        seeded += 1
        print(f"  Seeded: {name} — {rating} stars — {score:.1f}/100")

    session.commit()
    session.close()
    print(f"\nDone. Seeded {seeded} editorial reviews.")


if __name__ == "__main__":
    main()
