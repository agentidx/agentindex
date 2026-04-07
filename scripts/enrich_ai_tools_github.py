#!/usr/bin/env python3
"""
Enrich ai_tool entities via GitHub Search API.
Uses multiple tokens for rate limit rotation.
"""
import os, sys, time, json, logging, requests
sys.path.insert(0, os.path.expanduser("~/agentindex"))
os.chdir(os.path.expanduser("~/agentindex"))

from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("enrich_ai_tool")

# Rotate through tokens
TOKENS = []
for key in ["GITHUB_TOKEN", "GITHUB_TOKEN_2", "GITHUB_TOKEN_3", "GITHUB_TOKEN_4"]:
    with open(os.path.expanduser("~/agentindex/.env")) as f:
        for line in f:
            if line.startswith(key + "="):
                TOKENS.append(line.strip().split("=", 1)[1])

log.info(f"Loaded {len(TOKENS)} GitHub tokens")
token_idx = 0

def github_search(query):
    global token_idx
    token = TOKENS[token_idx % len(TOKENS)]
    token_idx += 1
    try:
        r = requests.get(
            "https://api.github.com/search/repositories",
            params={"q": f"{query} in:name", "sort": "stars", "per_page": 1},
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
            timeout=10
        )
        if r.status_code == 403:  # Rate limited
            log.warning(f"Rate limited on token {token_idx % len(TOKENS)}, sleeping 30s")
            time.sleep(30)
            return github_search(query)  # Retry with next token
        if r.status_code != 200:
            return None
        items = r.json().get("items", [])
        if not items:
            return None
        repo = items[0]
        # Verify match — name should be similar to query
        repo_name = repo.get("name", "").lower().replace("-", "").replace("_", "")
        query_clean = query.lower().replace("-", "").replace("_", "")
        if query_clean not in repo_name and repo_name not in query_clean:
            return None  # False match
        return {
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "open_issues": repo.get("open_issues_count", 0),
            "description": repo.get("description", ""),
            "license": (repo.get("license") or {}).get("spdx_id", ""),
            "last_updated": repo.get("pushed_at", ""),
            "full_name": repo.get("full_name", ""),
            "homepage": repo.get("homepage", ""),
        }
    except Exception as e:
        log.warning(f"GitHub error for {query}: {e}")
        return None

def calculate_trust_from_github(data):
    """Calculate trust score from GitHub data."""
    stars = data.get("stars", 0)
    forks = data.get("forks", 0)
    issues = data.get("open_issues", 0)
    license_str = data.get("license", "")
    desc = data.get("description", "")
    
    # Security (base 70, minus for issues ratio)
    security = 70
    if stars > 0:
        issue_ratio = issues / max(stars, 1)
        if issue_ratio < 0.01: security = 90
        elif issue_ratio < 0.05: security = 80
        elif issue_ratio < 0.1: security = 70
        else: security = 60
    
    # Popularity
    if stars > 50000: popularity = 100
    elif stars > 10000: popularity = 90
    elif stars > 5000: popularity = 80
    elif stars > 1000: popularity = 70
    elif stars > 500: popularity = 60
    elif stars > 100: popularity = 50
    elif stars > 10: popularity = 35
    elif stars > 0: popularity = 20
    else: popularity = 0
    
    # Community (forks)
    if forks > 5000: community = 90
    elif forks > 1000: community = 80
    elif forks > 500: community = 70
    elif forks > 100: community = 60
    elif forks > 10: community = 45
    elif forks > 0: community = 30
    else: community = 15
    
    # Quality
    quality = 30
    if license_str and license_str not in ("NOASSERTION", ""): quality += 20
    if desc and len(desc) > 30: quality += 15
    quality = min(100, quality)
    
    # Maintenance (based on recent activity — simplified)
    maintenance = 50  # Default
    
    total = round(
        security * 0.25 + popularity * 0.20 + community * 0.15 + 
        quality * 0.20 + maintenance * 0.20, 1
    )
    
    grade = ("A+" if total >= 90 else "A" if total >= 85 else "A-" if total >= 80 
             else "B+" if total >= 75 else "B" if total >= 70 else "B-" if total >= 65
             else "C+" if total >= 60 else "C" if total >= 55 else "C-" if total >= 50
             else "D" if total >= 40 else "F")
    
    return total, grade

# Main — use fresh session per batch to avoid stale connections
registries = ["ai_tool", "saas"]
for registry in registries:
    session = get_session()
    try:
        session.execute(text("SET statement_timeout = '30s'"))
        rows = session.execute(text("""
            SELECT id, slug, name, stars, repository_url
            FROM software_registry
            WHERE registry = :reg
            ORDER BY is_king DESC NULLS LAST, slug
        """), {"reg": registry}).fetchall()
    finally:
        session.close()

    log.info(f"{registry}: {len(rows)} entities to enrich")

    enriched = 0
    skipped = 0
    for i, row in enumerate(rows):
        pkg_id, slug, name, existing_stars, repo_url = row

        # Skip if already has real GitHub data
        if existing_stars and existing_stars > 0:
            skipped += 1
            continue

        # Search GitHub
        search_term = name or slug
        data = github_search(search_term)

        if data and data["stars"] > 0:
            trust, grade = calculate_trust_from_github(data)
            try:
                s = get_session()
                s.execute(text("SET statement_timeout = '10s'"))
                s.execute(text("""
                    UPDATE software_registry SET
                        stars = :stars, forks = :forks, open_issues = :issues,
                        repository_url = :repo, homepage_url = :homepage,
                        trust_score = :trust, trust_grade = :grade,
                        security_score = :sec, popularity_score = :pop,
                        community_score = :comm, quality_score = :qual,
                        enriched_at = NOW()
                    WHERE id = :id
                """), {
                    "id": str(pkg_id), "stars": data["stars"], "forks": data["forks"],
                    "issues": data["open_issues"],
                    "repo": f"https://github.com/{data['full_name']}",
                    "homepage": data.get("homepage", ""),
                    "trust": trust, "grade": grade,
                    "sec": 70, "pop": min(100, data["stars"] // 100),
                    "comm": min(100, data["forks"] // 10),
                    "qual": 50 + (20 if data.get("license") else 0),
                })
                s.commit()
                s.close()
                enriched += 1
            except Exception as e:
                log.warning(f"DB error for {slug}: {e}")
                try: s.rollback(); s.close()
                except: pass

        if (i + 1) % 50 == 0:
            log.info(f"  {registry}: {i+1}/{len(rows)} processed, {enriched} enriched, {skipped} skipped")

        time.sleep(2.5)  # ~24 req/min across 4 tokens = 6 req/min/token

    log.info(f"{registry} done: {enriched} enriched, {skipped} skipped out of {len(rows)}")

log.info("All done")
