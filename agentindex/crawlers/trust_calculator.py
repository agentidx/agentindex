"""Trust Score Calculator for Software Registry packages."""

from datetime import datetime


def calculate_trust(entry: dict) -> tuple[float, str]:
    """Calculate trust score (0-100) and grade for a registry entry."""
    score = 0.0

    # Maintenance (30 pts)
    lu = entry.get("last_updated")
    if lu:
        try:
            if isinstance(lu, str):
                lu = datetime.fromisoformat(lu.replace("Z", "+00:00"))
            days = (datetime.utcnow() - lu.replace(tzinfo=None)).days
            score += 30 if days < 30 else 25 if days < 90 else 15 if days < 365 else 8 if days < 730 else 3
        except (ValueError, TypeError):
            score += 5
    else:
        score += 5

    # Community (25 pts)
    dl = entry.get("downloads") or 0
    st = entry.get("stars") or 0
    if dl >= 10_000_000: score += 25
    elif dl >= 1_000_000: score += 22
    elif dl >= 100_000: score += 18
    elif dl >= 10_000: score += 14
    elif dl >= 1_000: score += 10
    elif dl > 0: score += 5
    if st >= 10_000: score += 5
    elif st >= 1_000: score += 3
    elif st >= 100: score += 1

    # Security (20 pts)
    lic = entry.get("license") or ""
    good = ["mit", "apache", "bsd", "isc", "mpl"]
    if any(l in lic.lower() for l in good):
        score += 15
    elif lic:
        score += 8
    else:
        score += 2
    score += 5  # Base (no CVE check yet)

    # Stability (15 pts)
    ca = entry.get("created_at")
    if ca:
        try:
            if isinstance(ca, str):
                ca = datetime.fromisoformat(ca.replace("Z", "+00:00"))
            age = (datetime.utcnow() - ca.replace(tzinfo=None)).days
            score += 15 if age > 1825 else 12 if age > 730 else 8 if age > 365 else 5 if age > 90 else 2
        except (ValueError, TypeError):
            score += 5
    else:
        score += 5

    # Metadata (10 pts)
    desc = entry.get("description") or ""
    if len(desc) > 50: score += 5
    elif len(desc) > 10: score += 3
    if entry.get("author"): score += 3
    if entry.get("repository_url") or entry.get("homepage_url"): score += 2

    score = max(0, min(100, score))
    if score >= 90: grade = "A+"
    elif score >= 80: grade = "A"
    elif score >= 70: grade = "B"
    elif score >= 60: grade = "C"
    elif score >= 50: grade = "D"
    else: grade = "F"

    return round(score, 1), grade
