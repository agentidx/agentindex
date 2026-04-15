"""
Nerq Improvement Engine (System 1: Improve Flywheel)
=====================================================
Generates personalized improvement recommendations for any indexed tool.
Each recommendation includes point impact, copy-paste templates, and competitor context.

Usage:
    from agentindex.intelligence.improvement_engine import get_improvements
    plan = get_improvements("langchain")
"""

import html
import json
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy.sql import text

from agentindex.db.models import get_db_session

logger = logging.getLogger("nerq.improvement_engine")


@dataclass
class Action:
    title: str
    points: int
    dimension: str
    description: str
    template: str = ""
    difficulty: str = "easy"  # easy, medium, hard


def _to_slug(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def get_improvements(agent_name: str) -> dict | None:
    """
    Returns personalized improvement plan with point values.

    Returns dict with keys:
        agent: dict with current scores
        actions: list of Action dicts sorted by points desc
        estimated_new_score: float
        competitors: list of dicts in same category
        current_rank: int
        total_in_category: int
    """
    with get_db_session() as session:
        # Find agent — fuzzy match always, prefer by stars
        pattern = agent_name.replace("-", "%")
        session.execute(text("SET LOCAL work_mem = '2MB'"))
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        row = session.execute(text("""
            SELECT el.id, el.name, el.trust_score_v2, el.trust_grade, el.stars, el.description,
                   el.category, a.language, el.author, el.source, el.source_url, el.license,
                   el.security_score, el.activity_score, el.documentation_score,
                   el.popularity_score, el.eu_risk_class, el.agent_type,
                   a.trust_dimensions, a.trust_category_rank, a.trust_category_total
            FROM entity_lookup el
            LEFT JOIN agents a ON a.id = el.id
            WHERE (el.name_lower = :q OR el.name_lower LIKE :p) AND el.is_active = true
            ORDER BY COALESCE(el.stars, 0) DESC
            LIMIT 1
        """), {"q": agent_name.lower(), "p": f"%{pattern}%"}).fetchone()

        if not row:
            return None

        cols = ["id", "name", "trust_score_v2", "trust_grade", "stars", "description",
                "category", "language", "author", "source", "source_url", "license",
                "security_score", "activity_score", "documentation_score",
                "popularity_score", "eu_risk_class", "agent_type",
                "trust_dimensions", "trust_category_rank", "trust_category_total"]
        agent = dict(zip(cols, row))

        # Get competitors in same category
        cat = agent.get("category")
        competitors = []
        if cat:
            comp_rows = session.execute(text("""
                SELECT name, trust_score_v2, trust_grade, stars
                FROM entity_lookup
                WHERE is_active = true AND trust_score_v2 IS NOT NULL
                  AND category = :cat AND id != CAST(:tid AS uuid)
                ORDER BY trust_score_v2 DESC
                LIMIT 10
            """), {"cat": cat, "tid": str(agent["id"])}).fetchall()
            competitors = [dict(zip(["name", "score", "grade", "stars"], r)) for r in comp_rows]

    # Parse trust dimensions if available
    dims = {}
    if agent.get("trust_dimensions"):
        try:
            dims = json.loads(agent["trust_dimensions"]) if isinstance(agent["trust_dimensions"], str) else agent["trust_dimensions"]
        except (json.JSONDecodeError, TypeError):
            pass

    # Generate improvement actions
    actions = _generate_actions(agent, dims)

    # Sort by points descending
    actions.sort(key=lambda a: a.points, reverse=True)

    # Estimate new score
    current_score = agent.get("trust_score_v2") or 0
    total_points = sum(a.points for a in actions)
    # Diminishing returns: each point is worth less as score increases
    estimated_new = min(100, current_score + total_points * 0.7)

    # Current rank
    rank = agent.get("trust_category_rank") or 0
    total = agent.get("trust_category_total") or 0

    return {
        "agent": agent,
        "actions": [vars(a) for a in actions],
        "estimated_new_score": round(estimated_new, 1),
        "total_potential_points": total_points,
        "competitors": competitors,
        "current_rank": rank,
        "total_in_category": total,
        "dimensions": dims,
    }


def _generate_actions(agent: dict, dims: dict) -> list[Action]:
    """Generate specific improvement actions based on weaknesses."""
    actions = []

    sec = agent.get("security_score") or 0
    act = agent.get("activity_score") or 0
    doc = agent.get("documentation_score") or 0
    pop = agent.get("popularity_score") or 0
    lic = agent.get("license") or ""
    source = agent.get("source") or ""
    name = agent.get("name") or ""
    slug = _to_slug(name)

    # Security improvements
    if sec < 70:
        actions.append(Action(
            title="Add SECURITY.md",
            points=3,
            dimension="security",
            description="A SECURITY.md file tells users how to report vulnerabilities. This is a strong trust signal.",
            template=f"""# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| latest  | ✅         |

## Reporting a Vulnerability

Please report security vulnerabilities to security@{slug}.dev

We will respond within 48 hours and provide a fix timeline.

Do NOT open public issues for security vulnerabilities.""",
            difficulty="easy",
        ))

    if sec < 80:
        actions.append(Action(
            title="Add security scanning CI",
            points=3,
            dimension="security",
            description="Automated security scanning in CI catches vulnerabilities before they reach users.",
            template=f"""# .github/workflows/security.yml
name: Security Scan
on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: '0 6 * * 1'

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          severity: 'HIGH,CRITICAL'""",
            difficulty="easy",
        ))

    # Activity improvements
    if act < 60:
        actions.append(Action(
            title="Update dependencies",
            points=2,
            dimension="activity",
            description="Outdated dependencies lower your activity score. Run dependency updates and commit.",
            template="# For Python:\npip install --upgrade -r requirements.txt\npip freeze > requirements.txt\n\n# For Node:\nnpx npm-check-updates -u\nnpm install",
            difficulty="medium",
        ))

    if act < 70:
        actions.append(Action(
            title="Set up automated dependency updates",
            points=2,
            dimension="activity",
            description="Dependabot or Renovate keeps dependencies fresh automatically.",
            template="""# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5""",
            difficulty="easy",
        ))

    # Documentation improvements
    if doc < 60:
        actions.append(Action(
            title="Add comprehensive README sections",
            points=2,
            dimension="documentation",
            description="READMEs with installation, usage examples, and API docs score higher.",
            template=f"""## Installation

```bash
pip install {slug}
```

## Quick Start

```python
from {slug.replace('-', '_')} import Client

client = Client()
result = client.run()
print(result)
```

## API Reference

See [docs/api.md](docs/api.md) for full API documentation.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.""",
            difficulty="easy",
        ))

    if doc < 80:
        actions.append(Action(
            title="Add CONTRIBUTING.md",
            points=1,
            dimension="documentation",
            description="A contributing guide encourages community participation and signals project maturity.",
            template=f"""# Contributing to {name}

## Getting Started

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit changes: `git commit -am 'Add feature'`
4. Push: `git push origin feature/my-feature`
5. Open a Pull Request

## Code Style

- Follow existing code patterns
- Add tests for new features
- Update documentation as needed

## Bug Reports

Use GitHub Issues with a clear description and reproduction steps.""",
            difficulty="easy",
        ))

    # License
    if not lic or lic.lower() in ("none", "unknown", "other"):
        actions.append(Action(
            title="Add a license",
            points=2,
            dimension="security",
            description="Projects without a license cannot be legally used. MIT is the most permissive choice.",
            template="MIT License\n\nCopyright (c) 2026 [Your Name]\n\nPermission is hereby granted, free of charge...",
            difficulty="easy",
        ))

    # Agent.json
    actions.append(Action(
        title="Add .well-known/agent.json",
        points=1,
        dimension="documentation",
        description="The agent.json file makes your tool discoverable by AI agents and registries.",
        template=json.dumps({
            "name": name,
            "description": (agent.get("description") or "")[:200],
            "version": "1.0.0",
            "capabilities": [],
            "trust_score": f"https://nerq.ai/is-{slug}-safe",
        }, indent=2),
        difficulty="easy",
    ))

    # Nerq badge
    repo_slug = agent.get("source_url", "").replace("https://github.com/", "").rstrip("/")
    if not repo_slug:
        repo_slug = slug
    actions.append(Action(
        title="Add Nerq Trust Badge",
        points=1,
        dimension="popularity",
        description="The trust badge shows visitors your security rating at a glance.",
        template=f'[![Nerq Trust Score](https://nerq.ai/badge/{repo_slug})](https://nerq.ai/is-{slug}-safe)',
        difficulty="easy",
    ))

    # Popularity boost
    if pop < 50:
        actions.append(Action(
            title="Add to package registries",
            points=2,
            dimension="popularity",
            description="Publishing to PyPI/npm increases discoverability and downloads.",
            template="# PyPI:\npython -m build\ntwine upload dist/*\n\n# npm:\nnpm publish",
            difficulty="medium",
        ))

    return actions
