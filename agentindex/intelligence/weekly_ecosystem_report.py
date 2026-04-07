"""
Weekly Ecosystem Report Generator — Mondays 06:00
===================================================
Auto-generates "State of the Agent Economy" report from all data sources.
Outputs: Markdown, Blog HTML, Dev.to draft, Bluesky post.

Usage:
    python -m agentindex.intelligence.weekly_ecosystem_report
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.sql import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [ecosystem-report] %(message)s")
logger = logging.getLogger("ecosystem-report")

SQLITE_DB = Path(__file__).parent.parent / "crypto" / "crypto_trust.db"
REPORTS_DIR = Path(__file__).parent.parent.parent / "docs" / "auto-reports"


def _get_pg_stats():
    """Pull stats from PostgreSQL agents table."""
    from agentindex.db.models import get_session
    session = get_session()
    try:
        total = session.execute(text("SELECT COUNT(*) FROM entity_lookup WHERE is_active = true")).scalar() or 0
        grade_dist = session.execute(text("""
            SELECT trust_grade, COUNT(*) FROM entity_lookup
            WHERE is_active = true AND trust_grade IS NOT NULL
            GROUP BY trust_grade ORDER BY COUNT(*) DESC
        """)).fetchall()
        avg_trust = session.execute(text(
            "SELECT AVG(COALESCE(trust_score_v2, trust_score)) FROM entity_lookup WHERE is_active = true"
        )).scalar() or 0
        cat_dist = session.execute(text("""
            SELECT category, COUNT(*) FROM entity_lookup
            WHERE is_active = true AND category IS NOT NULL
            GROUP BY category ORDER BY COUNT(*) DESC LIMIT 15
        """)).fetchall()
        new_7d = session.execute(text(
            "SELECT COUNT(*) FROM entity_lookup WHERE is_active = true AND first_indexed > NOW() - INTERVAL '7 days'"
        )).scalar() or 0
        verified = session.execute(text(
            "SELECT COUNT(*) FROM entity_lookup WHERE is_active = true AND (is_verified = true OR COALESCE(trust_score_v2, trust_score) >= 70)"
        )).scalar() or 0
        return {
            "total": total, "avg_trust": round(float(avg_trust), 1),
            "grades": {r[0]: r[1] for r in grade_dist},
            "categories": {r[0]: r[1] for r in cat_dist},
            "new_7d": new_7d, "verified": verified,
        }
    finally:
        session.close()


def _get_sqlite_stats():
    """Pull enrichment stats from SQLite."""
    if not SQLITE_DB.exists():
        return {}
    conn = sqlite3.connect(str(SQLITE_DB), timeout=5)
    stats = {}
    try:
        stats["cves_total"] = conn.execute("SELECT COUNT(*) FROM agent_vulnerabilities").fetchone()[0]
        stats["cves_critical"] = conn.execute(
            "SELECT COUNT(*) FROM agent_vulnerabilities WHERE severity = 'CRITICAL'"
        ).fetchone()[0]
        stats["cves_high"] = conn.execute(
            "SELECT COUNT(*) FROM agent_vulnerabilities WHERE severity = 'HIGH'"
        ).fetchone()[0]
    except Exception:
        stats["cves_total"] = 0
    try:
        stats["frameworks_total"] = conn.execute("SELECT COUNT(DISTINCT framework) FROM agent_frameworks").fetchone()[0]
        stats["frameworks_agents"] = conn.execute("SELECT COUNT(DISTINCT agent_name) FROM agent_frameworks").fetchone()[0]
        fw_dist = conn.execute(
            "SELECT framework, COUNT(DISTINCT agent_name) FROM agent_frameworks GROUP BY framework ORDER BY COUNT(*) DESC LIMIT 10"
        ).fetchall()
        stats["framework_dist"] = {r[0]: r[1] for r in fw_dist}
    except Exception:
        stats["frameworks_total"] = 0
    try:
        stats["licensed_agents"] = conn.execute("SELECT COUNT(DISTINCT agent_name) FROM agent_licenses").fetchone()[0]
        lic_dist = conn.execute(
            "SELECT license_category, COUNT(*) FROM agent_licenses GROUP BY license_category ORDER BY COUNT(*) DESC"
        ).fetchall()
        stats["license_dist"] = {r[0]: r[1] for r in lic_dist}
    except Exception:
        stats["licensed_agents"] = 0
    try:
        stats["priced_agents"] = conn.execute("SELECT COUNT(DISTINCT agent_name) FROM agent_pricing").fetchone()[0]
        pm_dist = conn.execute(
            "SELECT pricing_model, COUNT(DISTINCT agent_name) FROM agent_pricing GROUP BY pricing_model ORDER BY COUNT(*) DESC"
        ).fetchall()
        stats["pricing_dist"] = {r[0]: r[1] for r in pm_dist}
    except Exception:
        stats["priced_agents"] = 0
    try:
        stats["mcp_servers"] = conn.execute("SELECT COUNT(DISTINCT server_name) FROM mcp_compatibility").fetchone()[0]
        stats["mcp_clients"] = conn.execute("SELECT COUNT(DISTINCT client) FROM mcp_compatibility").fetchone()[0]
    except Exception:
        stats["mcp_servers"] = 0
    try:
        stats["deps_total"] = conn.execute("SELECT COUNT(DISTINCT agent_name) FROM agent_dependencies").fetchone()[0]
    except Exception:
        stats["deps_total"] = 0
    try:
        stats["trends_7d"] = conn.execute(
            "SELECT COUNT(*) FROM agent_trends WHERE detected_at > datetime('now', '-7 days')"
        ).fetchone()[0]
    except Exception:
        stats["trends_7d"] = 0
    conn.close()
    return stats


def _generate_markdown(pg, sq, now, week_num):
    """Generate the full markdown report."""
    grades = pg.get("grades", {})
    cats = pg.get("categories", {})
    fw_dist = sq.get("framework_dist", {})
    lic_dist = sq.get("license_dist", {})
    pricing_dist = sq.get("pricing_dist", {})

    grade_a = sum(v for k, v in grades.items() if k and k.startswith("A"))
    grade_b = sum(v for k, v in grades.items() if k and k.startswith("B"))
    grade_c = sum(v for k, v in grades.items() if k and k.startswith("C"))
    grade_d = sum(v for k, v in grades.items() if k and k.startswith("D"))
    grade_f = grades.get("F", 0)

    report = f"""---
title: "State of the Agent Economy — Week {week_num}, {now.year}"
date: {now.strftime('%Y-%m-%d')}
---

# State of the Agent Economy — Week {week_num}, {now.year}

*Generated {now.strftime('%B %d, %Y')} by Nerq Intelligence*

## Ecosystem Overview

| Metric | Value |
|--------|-------|
| Total Active Agents | **{pg['total']:,}** |
| New Agents (7 days) | **{pg['new_7d']:,}** |
| Average Trust Score | **{pg['avg_trust']}/100** |
| Verified Agents (≥70) | **{pg['verified']:,}** |
| Known CVEs | **{sq.get('cves_total', 0):,}** |
| Licensed Agents | **{sq.get('licensed_agents', 0):,}** |
| Agents with Pricing | **{sq.get('priced_agents', 0):,}** |

## Trust Score Distribution

| Grade | Count | Share |
|-------|-------|-------|
| A (85+) | {grade_a:,} | {grade_a/max(pg['total'],1)*100:.1f}% |
| B (70-84) | {grade_b:,} | {grade_b/max(pg['total'],1)*100:.1f}% |
| C (55-69) | {grade_c:,} | {grade_c/max(pg['total'],1)*100:.1f}% |
| D (40-54) | {grade_d:,} | {grade_d/max(pg['total'],1)*100:.1f}% |
| F (<40) | {grade_f:,} | {grade_f/max(pg['total'],1)*100:.1f}% |

## Top Categories

| Category | Agents |
|----------|--------|
"""
    for cat, count in list(cats.items())[:10]:
        report += f"| {cat} | {count:,} |\n"

    if fw_dist:
        report += "\n## Framework Adoption\n\n| Framework | Agents |\n|-----------|--------|\n"
        for fw, count in list(fw_dist.items())[:10]:
            report += f"| {fw} | {count} |\n"

    report += f"""
## Security

- **Total known CVEs:** {sq.get('cves_total', 0):,}
- **CRITICAL:** {sq.get('cves_critical', 0):,}
- **HIGH:** {sq.get('cves_high', 0):,}
- **Trends detected (7d):** {sq.get('trends_7d', 0)}

## MCP Ecosystem

- **MCP servers indexed:** {sq.get('mcp_servers', 0):,}
- **MCP clients tracked:** {sq.get('mcp_clients', 0)}
- **Agents with dependencies:** {sq.get('deps_total', 0):,}

## License Distribution

| Category | Count |
|----------|-------|
"""
    for cat, count in list(lic_dist.items())[:5]:
        report += f"| {cat} | {count:,} |\n"

    if pricing_dist:
        report += "\n## Pricing Models\n\n| Model | Agents |\n|-------|--------|\n"
        for model, count in list(pricing_dist.items()):
            report += f"| {model} | {count:,} |\n"

    report += f"""
---

*This report is auto-generated by [Nerq Intelligence](https://nerq.ai/reports). Data sourced from {pg['total']:,} indexed AI agents across GitHub, npm, PyPI, and HuggingFace.*
"""
    return report


def _publish_blog(markdown, now, week_num):
    """Save markdown file for blog auto-discovery."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{now.strftime('%Y-%m-%d')}-weekly.md"
    path = REPORTS_DIR / filename
    path.write_text(markdown)
    logger.info(f"  Blog report saved: {path}")
    return path


def _publish_bluesky(pg, sq, week_num, now):
    """Post headline stats to Bluesky."""
    try:
        from agentindex.bluesky_bot import post_to_bluesky
        text = (
            f"State of the Agent Economy — Week {week_num}\n\n"
            f"{pg['total']:,} agents indexed | avg trust {pg['avg_trust']}/100\n"
            f"{pg['new_7d']} new this week | {sq.get('cves_total', 0)} CVEs tracked\n\n"
            f"Full report: nerq.ai/reports"
        )
        result = post_to_bluesky(text)
        if result:
            logger.info("  Bluesky post published")
        else:
            logger.warning("  Bluesky post failed or dry-run")
    except Exception as e:
        logger.warning(f"  Bluesky post skipped: {e}")


def _publish_devto(markdown, week_num, now):
    """Publish to Dev.to."""
    try:
        key_path = Path.home() / ".config" / "nerq" / "devto_api_key"
        if not key_path.exists():
            logger.info("  Dev.to API key not found, saving draft locally")
            draft_path = REPORTS_DIR / f"devto-week-{week_num}.md"
            draft_path.write_text(markdown)
            return

        import requests
        api_key = key_path.read_text().strip()
        resp = requests.post(
            "https://dev.to/api/articles",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "article": {
                    "title": f"State of the Agent Economy — Week {week_num}, {now.year}",
                    "body_markdown": markdown,
                    "published": True,
                    "tags": ["ai", "agents", "security", "python"],
                    "canonical_url": f"https://nerq.ai/blog/state-of-agents-week-{week_num}",
                    "description": f"Weekly analysis of {now.year}'s AI agent ecosystem: trust scores, CVEs, framework adoption, and pricing trends.",
                }
            },
            timeout=30,
        )
        if resp.status_code in (200, 201):
            logger.info(f"  Dev.to article published: {resp.json().get('url', 'OK')}")
        else:
            logger.warning(f"  Dev.to publish failed ({resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"  Dev.to publish skipped: {e}")


def generate_report():
    """Generate and publish the weekly ecosystem report. Returns the report data dict."""
    now = datetime.now()
    week_num = now.isocalendar()[1]

    logger.info("=" * 60)
    logger.info(f"Weekly Ecosystem Report — Week {week_num}, {now.year}")
    logger.info("=" * 60)

    pg = _get_pg_stats()
    logger.info(f"  PG stats: {pg['total']:,} agents, avg trust {pg['avg_trust']}")

    sq = _get_sqlite_stats()
    logger.info(f"  SQLite stats: {sq.get('cves_total', 0)} CVEs, {sq.get('frameworks_total', 0)} frameworks")

    markdown = _generate_markdown(pg, sq, now, week_num)

    # Publish to all channels
    blog_path = _publish_blog(markdown, now, week_num)
    _publish_bluesky(pg, sq, week_num, now)
    _publish_devto(markdown, week_num, now)

    # Store structured data for API consumption
    report_data = {
        "week": week_num,
        "year": now.year,
        "generated_at": now.isoformat(),
        "ecosystem": {
            "total_agents": pg["total"],
            "new_agents_7d": pg["new_7d"],
            "avg_trust_score": pg["avg_trust"],
            "verified_agents": pg["verified"],
        },
        "security": {
            "total_cves": sq.get("cves_total", 0),
            "critical_cves": sq.get("cves_critical", 0),
            "high_cves": sq.get("cves_high", 0),
        },
        "frameworks": sq.get("framework_dist", {}),
        "licenses": sq.get("license_dist", {}),
        "pricing": sq.get("pricing_dist", {}),
        "mcp": {
            "servers": sq.get("mcp_servers", 0),
            "clients": sq.get("mcp_clients", 0),
        },
        "categories": pg.get("categories", {}),
        "grades": pg.get("grades", {}),
        "report_url": f"https://nerq.ai/blog/state-of-agents-week-{week_num}",
        "blog_path": str(blog_path),
    }

    # Save structured report
    json_path = REPORTS_DIR / f"report-week-{week_num}-{now.year}.json"
    json_path.write_text(json.dumps(report_data, indent=2, default=str))
    logger.info(f"  Structured report saved: {json_path}")

    logger.info("")
    logger.info("=" * 60)
    logger.info("Weekly Ecosystem Report — COMPLETE")
    logger.info(f"  Agents: {pg['total']:,} total, {pg['new_7d']} new")
    logger.info(f"  Trust: avg {pg['avg_trust']}, verified {pg['verified']:,}")
    logger.info(f"  CVEs: {sq.get('cves_total', 0)}, frameworks: {sq.get('frameworks_total', 0)}")
    logger.info("=" * 60)

    return report_data


def main():
    generate_report()


if __name__ == "__main__":
    main()
