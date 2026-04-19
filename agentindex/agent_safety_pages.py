"""
Nerq Agent Safety Pages
========================
Individual agent safety pages at /safe/{slug} and hub page at /safe.
Captures search traffic for "is [agent] safe", "can I trust [agent]", "[agent] review".

Usage in discovery.py:
    from agentindex.agent_safety_pages import mount_agent_safety_pages
    mount_agent_safety_pages(app)
"""

import json
import logging
import os
from pathlib import Path
from datetime import date, datetime

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.sql import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER, render_hreflang, render_nav, render_footer

logger = logging.getLogger("nerq.safety_pages")

TEMPLATE_DIR = Path(__file__).parent / "templates"
SLUGS_PATH = Path(__file__).parent / "agent_safety_slugs.json"
YEAR = date.today().year

# L1 Kings Unlock canary allowlist. Fail-closed semantics:
#   * env unset / empty      → NO unlock; non-Kings render as before. Safe
#                              default so a plain `launchctl kickstart` after
#                              deploying this code is a no-op.
#   * env = "gems,homebrew"  → only those two registries unlock for non-Kings
#                              (Day-1 canary)
#   * env = "*" or "all"     → every non-skip registry unlocks (full rollout)
# Kings are unaffected by this flag.
_L1_UNLOCK_ALLOWLIST: frozenset = frozenset(
    s.strip() for s in os.environ.get("L1_UNLOCK_REGISTRIES", "").split(",") if s.strip()
)
_L1_UNLOCK_ALL: bool = bool(_L1_UNLOCK_ALLOWLIST & {"*", "all"})

# L5 cross-registry internal-linking gate (T153). off|shadow|live, default off.
#   off    → no DB query, no render
#   shadow → query runs (for metric/observability) but nothing rendered
#   live   → render the "Also on other registries" section
_L5_CROSSREG_MODE: str = os.environ.get("L5_CROSSREG_LINKS", "off").strip().lower()


# L2 Block 2a gate (T110) — external-trust-signals renderer. Parallel
# design to L2_BLOCK_2B_MODE / L2_BLOCK_2E_MODE. Three modes, default off.
def _l2_block_2a_mode() -> str:
    m = os.environ.get("L2_BLOCK_2A_MODE", "off").strip().lower()
    return m if m in ("shadow", "live") else "off"


def _l2_block_2a_html(slug: str) -> str:
    mode = _l2_block_2a_mode()
    if mode == "off":
        return ""
    try:
        from smedjan.renderers.block_2a import render_block_2a_html
        raw = render_block_2a_html(slug)
    except Exception as exc:
        logger.warning("block_2a: render failed for %s: %s", slug, exc)
        return ""
    if not raw:
        return ""
    if mode == "shadow":
        safe = raw.replace("--", "- -")
        return f"<!-- L2_BLOCK_2A_SHADOW\n{safe}\n-->"
    return raw  # live


# L2 Block 2a — in-king-sections variant (T004). Separate gate from
# L2_BLOCK_2A_MODE because it has different semantics (registry
# allowlist, L1 canary playbook) and different placement (ABOVE
# "Detailed Score Analysis" inside king_sections, not below). Fail-closed
# empty = disabled. Values are comma-separated registries or "*"/"all".
_L2_BLOCK_2A_ALLOWLIST: frozenset = frozenset(
    s.strip() for s in os.environ.get("L2_BLOCK_2A_REGISTRIES", "").split(",") if s.strip()
)
_L2_BLOCK_2A_ALL: bool = bool(_L2_BLOCK_2A_ALLOWLIST & {"*", "all"})


def _l2_block_2a_registry_html(slug: str, source: str) -> str:
    """Return Block 2a HTML for king-section placement, or "" when gated off.

    Evaluated per-call so the dry-run harness can flip the env var
    in-process. Allowlist is rebuilt on each call rather than cached at
    import time so tests can set the var after import.
    """
    allow_raw = os.environ.get("L2_BLOCK_2A_REGISTRIES", "").strip()
    if not allow_raw:
        return ""
    allowlist = {s.strip() for s in allow_raw.split(",") if s.strip()}
    if not allowlist:
        return ""
    if not (allowlist & {"*", "all"}) and source not in allowlist:
        return ""
    try:
        from agentindex.smedjan.l2_block_2a import render_external_trust_block
        raw = render_external_trust_block(slug)
    except Exception as exc:
        logger.warning("block_2a (kings): render failed for %s: %s", slug, exc)
        return ""
    return raw or ""


# L2 Block 2b gate (T112) — dependency-graph renderer. Parallel design to
# L1_UNLOCK_REGISTRIES / L5_CROSSREG_LINKS. Three modes, default off:
#   off    → no DB query, nothing emitted
#   shadow → block is emitted wrapped in an HTML comment so the page is
#            visually unchanged but raw output can be sampled from response
#   live   → block is rendered verbatim between king-sections and FAQ
# The var is read per-call so the dry-run harness can toggle in-process.
def _l2_block_2b_mode() -> str:
    m = os.environ.get("L2_BLOCK_2B_MODE", "off").strip().lower()
    return m if m in ("shadow", "live") else "off"


def _l2_block_2b_html(slug: str) -> str:
    """Return the string to concatenate after king_sections. Fail-closed:
    any import or runtime error is swallowed so the page still renders."""
    mode = _l2_block_2b_mode()
    if mode == "off":
        return ""
    try:
        from smedjan.renderers.block_2b import render_block_2b_html
        raw = render_block_2b_html(slug)
    except Exception as exc:
        logger.warning("block_2b: render failed for %s: %s", slug, exc)
        return ""
    if not raw:
        return ""
    if mode == "shadow":
        # Neutralise "--" so the block body cannot prematurely close the
        # wrapping HTML comment even if future edits introduce one.
        safe = raw.replace("--", "- -")
        return f"<!-- L2_BLOCK_2B_SHADOW\n{safe}\n-->"
    return raw  # live


# L2 Block 2b — in-king-sections variant (T005). Separate gate from
# L2_BLOCK_2B_MODE because it has different semantics (registry
# allowlist, L1 canary playbook) and different placement (ABOVE Block
# 2a inside king_sections, not below king_sections). Fail-closed empty
# = disabled. Values are comma-separated registries or "*"/"all".
_L2_BLOCK_2B_ALLOWLIST: frozenset = frozenset(
    s.strip() for s in os.environ.get("L2_BLOCK_2B_REGISTRIES", "").split(",") if s.strip()
)
_L2_BLOCK_2B_ALL: bool = bool(_L2_BLOCK_2B_ALLOWLIST & {"*", "all"})


def _l2_block_2b_registry_html(slug: str, source: str) -> str:
    """Return Block 2b HTML for king-section placement, or "" when gated off.

    Evaluated per-call so the dry-run harness can flip the env var
    in-process. Allowlist is rebuilt on each call rather than cached at
    import time so tests can set the var after import.
    """
    allow_raw = os.environ.get("L2_BLOCK_2B_REGISTRIES", "").strip()
    if not allow_raw:
        return ""
    allowlist = {s.strip() for s in allow_raw.split(",") if s.strip()}
    if not allowlist:
        return ""
    if not (allowlist & {"*", "all"}) and source not in allowlist:
        return ""
    try:
        from agentindex.smedjan.l2_block_2b import render_dependency_graph_html
        raw = render_dependency_graph_html(slug)
    except Exception as exc:
        logger.warning("block_2b (kings): render failed for %s: %s", slug, exc)
        return ""
    return raw or ""


# L2 Block 2e gate (T118) — dimensions-dashboard renderer. Same three-mode
# design as L2_BLOCK_2B_MODE. Reads public.software_registry.dimensions
# on Nerq RO. Sits below king-sections and cross-registry links, above FAQ.
def _l2_block_2e_mode() -> str:
    m = os.environ.get("L2_BLOCK_2E_MODE", "off").strip().lower()
    return m if m in ("shadow", "live") else "off"


def _l2_block_2e_html(slug: str) -> str:
    mode = _l2_block_2e_mode()
    if mode == "off":
        return ""
    try:
        from smedjan.renderers.block_2e import render_block_2e_html
        raw = render_block_2e_html(slug)
    except Exception as exc:
        logger.warning("block_2e: render failed for %s: %s", slug, exc)
        return ""
    if not raw:
        return ""
    if mode == "shadow":
        safe = raw.replace("--", "- -")
        return f"<!-- L2_BLOCK_2E_SHADOW\n{safe}\n-->"
    return raw  # live


# L2 Block 2c gate (T114) — AI-demand-timeline renderer. Same three-mode
# design as L2_BLOCK_2A/2B/2E_MODE. Reads smedjan.ai_demand_scores and
# smedjan.ai_demand_history on the Smedjan DB. Sits below king-sections
# and cross-registry links, above FAQ.
def _l2_block_2c_mode() -> str:
    m = os.environ.get("L2_BLOCK_2C_MODE", "off").strip().lower()
    return m if m in ("shadow", "live") else "off"


def _l2_block_2c_html(slug: str) -> str:
    mode = _l2_block_2c_mode()
    if mode == "off":
        return ""
    try:
        from smedjan.renderers.block_2c import render_block_2c_html
        raw = render_block_2c_html(slug)
    except Exception as exc:
        logger.warning("block_2c: render failed for %s: %s", slug, exc)
        return ""
    if not raw:
        return ""
    if mode == "shadow":
        safe = raw.replace("--", "- -")
        return f"<!-- L2_BLOCK_2C_SHADOW\n{safe}\n-->"
    return raw  # live


# L2 Block 2c — in-king-sections variant (T006). Separate gate from
# L2_BLOCK_2C_MODE (T114, AI-demand timeline) because it has different
# semantics (registry allowlist, L1 canary playbook), a different data
# source (public.signal_events on Nerq RO, not smedjan.ai_demand_history),
# and different placement (inside king_sections between Block 2b and
# Block 2a, not below king_sections). Fail-closed empty = disabled.
# Values are comma-separated registries or "*"/"all".
_L2_BLOCK_2C_ALLOWLIST: frozenset = frozenset(
    s.strip() for s in os.environ.get("L2_BLOCK_2C_REGISTRIES", "").split(",") if s.strip()
)
_L2_BLOCK_2C_ALL: bool = bool(_L2_BLOCK_2C_ALLOWLIST & {"*", "all"})


def _l2_block_2c_registry_html(slug: str, source: str) -> str:
    """Return Block 2c HTML for king-section placement, or "" when gated off.

    Evaluated per-call so the dry-run harness can flip the env var
    in-process. Allowlist is rebuilt on each call rather than cached at
    import time so tests can set the var after import.
    """
    allow_raw = os.environ.get("L2_BLOCK_2C_REGISTRIES", "").strip()
    if not allow_raw:
        return ""
    allowlist = {s.strip() for s in allow_raw.split(",") if s.strip()}
    if not allowlist:
        return ""
    if not (allowlist & {"*", "all"}) and source not in allowlist:
        return ""
    try:
        from agentindex.smedjan.l2_block_2c import render_signal_timeline_html
        raw = render_signal_timeline_html(slug, source)
    except Exception as exc:
        logger.warning("block_2c (kings): render failed for %s: %s", slug, exc)
        return ""
    return raw or ""


# L2 Block 2d gate (T116) — signal-events feed renderer. Same three-mode
# design as L2_BLOCK_2A/2B/2C/2E_MODE. Reads public.signal_events on the
# Nerq RO replica, scoped to the top 500 slugs by ai_demand_score. Sits
# below king-sections and cross-registry links, above FAQ.
def _l2_block_2d_mode() -> str:
    m = os.environ.get("L2_BLOCK_2D_MODE", "off").strip().lower()
    return m if m in ("shadow", "live") else "off"


def _l2_block_2d_html(slug: str) -> str:
    mode = _l2_block_2d_mode()
    if mode == "off":
        return ""
    try:
        from smedjan.renderers.block_2d import render_block_2d_html
        raw = render_block_2d_html(slug)
    except Exception as exc:
        logger.warning("block_2d: render failed for %s: %s", slug, exc)
        return ""
    if not raw:
        return ""
    if mode == "shadow":
        safe = raw.replace("--", "- -")
        return f"<!-- L2_BLOCK_2D_SHADOW\n{safe}\n-->"
    return raw  # live

# ── Internationalization ─────────────────────────────────────────────────
# All user-visible strings are keyed here. _t(key, lang, **kwargs) returns
# the translated string or falls back to English.
_STRINGS = {
    # Page title / meta
    "title_safe": "Is {name} Safe? Trust Score &amp; Security Review ({year})",
    "title_safe_visit": "Is {name} Safe to Visit? {year} Safety Score &amp; Travel Guide | Nerq",
    "title_charity": "Is {name} a Trustworthy Charity? {year} Safety Score &amp; Analysis | Nerq",
    "title_ingredient": "Is {name} Safe? {year} Health &amp; Safety Analysis | Nerq",
    "meta_citation_author": "Nerq Trust Intelligence",

    # Breadcrumbs
    "breadcrumb_home": "Nerq",
    "breadcrumb_safety": "Safety",

    # H1 / main heading
    "h1_safe": "Is {name} Safe?",
    "h1_safe_visit": "Is {name} Safe to Visit?",
    "h1_trustworthy_charity": "Is {name} a Trustworthy Charity?",
    "h1_ingredient_safe": "Is {name} Safe?",

    # Section headings
    "trust_score_breakdown": "Trust Score Breakdown",
    "safety_score_breakdown": "Safety Score Breakdown",
    "key_findings": "Key Findings",
    "key_safety_findings": "Key Safety Findings",
    "details": "Details",
    "detailed_score_analysis": "Detailed Score Analysis",
    "faq": "Frequently Asked Questions",
    "community_reviews": "Community Reviews",
    "regulatory_compliance": "Regulatory Compliance",
    "how_calculated": "How we calculated this score",
    "popular_alternatives": "Popular Alternatives in {category}",
    "safer_alternatives": "Safer Alternatives",
    "across_platforms": "{name} Across Platforms",
    "safety_guide": "Safety Guide: {name}",
    "what_is": "What is {name}?",
    "key_concerns": "Key Safety Concerns for {type}",
    "how_to_verify": "How to Verify Safety",
    "trust_assessment": "Trust Assessment",
    "security_analysis": "Security Analysis",
    "privacy_report": "Privacy Report",
    "similar_in_registry": "Similar {registry} by Trust Score",
    "see_all_best": "See all safest {registry}",
    # D1: Perplexity verdict
    "pv_grade": "{grade} grade",
    "pv_body": "Based on analysis of {dims} trust dimensions, it is {verdict}.",
    "pv_vulns": "with {count} known vulnerabilities",
    "pv_updated": "Last updated: {date}.",
    "pv_safe": "considered safe to use",
    "pv_generally_safe": "generally safe but has some concerns",
    "pv_notable_concerns": "has notable safety concerns",
    "pv_significant_risks": "has significant safety risks",
    "pv_unsafe": "considered unsafe",
    # D2: Question H2s
    "h2q_trust_score": "What is {name}'s trust score?",
    "h2q_key_findings": "What are the key security findings for {name}?",
    "h2q_details": "What is {name} and who maintains it?",
    "ans_trust": "{name} has a Nerq Trust Score of {score}/100, earning a {grade} grade. This score is based on {dims} independently measured dimensions including security, maintenance, and community adoption.",
    "ans_findings_strong": "{name}'s strongest signal is {signal} at {signal_score}/100.",
    "ans_no_vulns": "No known vulnerabilities have been detected.",
    "ans_has_vulns": "{count} known vulnerabilities were identified.",
    "ans_verified": "It meets the Nerq Verified threshold of 70+.",
    "ans_not_verified": "It has not yet reached the Nerq Verified threshold of 70+.",
    "what_data_collect": "What data does {name} collect?",
    "is_secure": "Is {name} secure?",
    "is_safe_visit": "Is {name} safe to visit?",
    "is_legit_charity": "Is {name} a legitimate charity?",
    "crime_safety": "Crime and safety in {name}",
    "financial_transparency": "Financial transparency of {name}",

    # Verdict text
    "yes_safe": "Yes, {name} is safe to use.",
    "use_caution": "Use {name} with some caution.",
    "exercise_caution": "Exercise caution with {name}.",
    "significant_concerns": "{name} has significant trust concerns.",
    "safe": "Safe",
    "use_caution_short": "Use Caution",
    "avoid": "Avoid",

    # Verdict box
    "passes_threshold": "Passes Nerq Verified threshold",
    "below_threshold": "Below Nerq Verified threshold",
    "significant_gaps": "Significant trust gaps detected",
    "meets_threshold_detail": "It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption",
    "not_reached_threshold": "and has not yet reached Nerq trust threshold (70+).",
    "score_based_on": "This score is based on automated analysis of security, maintenance, community, and quality signals.",
    "recommended_production": "Recommended for production use",
    "review_before_use": "Review carefully before use — below trust threshold.",

    # Labels
    "last_analyzed": "Last analyzed:",
    "author_label": "Author",
    "category_label": "Category",
    "stars_label": "Stars",
    "global_rank_label": "Global Rank",
    "source_label": "Source",
    "frameworks_label": "Frameworks",
    "protocols_label": "Protocols",
    "dimension_label": "Dimension",
    "score_label": "Score",
    "machine_readable": "Machine-readable data (JSON)",
    "full_analysis": "Full analysis:",
    "privacy_report": "{name} Privacy Report",
    "security_report": "{name} Security Report",
    "data_sourced": "Data sourced from {sources}. Last updated: {date}.",
    "write_review": "Write a review",
    "no_reviews": "No reviews yet.",
    "be_first_review": "Be the first to review {name}",

    # Signal names
    "security": "Security",
    "compliance": "Compliance",
    "maintenance": "Maintenance",
    "documentation": "Documentation",
    "popularity": "Popularity",
    "overall_trust": "Overall Trust",
    "privacy": "Privacy",
    "reliability": "Reliability",
    "transparency": "Transparency",

    # Signal descriptions
    "security_desc": "Code quality, vulnerability exposure, and security practices.",
    "maintenance_desc": "Update frequency, issue responsiveness, active development.",
    "documentation_desc": "README quality, API docs, usage examples.",
    "overall_trust_desc": "Composite score across all trust dimensions.",

    # Signal strength labels
    "strong": "strong",
    "moderate": "moderate",
    "weak": "weak",
    "actively_maintained": "actively maintained",
    "moderately_maintained": "moderately maintained",
    "low_maintenance": "low maintenance activity",
    "well_documented": "well-documented",
    "partial_documentation": "partial documentation",
    "limited_documentation": "limited documentation",

    # FAQ answers
    "yes_safe_short": "Yes, it is safe to use.",
    "use_caution_faq": "Use with some caution.",
    "exercise_caution_faq": "Exercise caution.",
    "significant_concerns_faq": "Significant trust concerns.",
    "strongest_signal": "Strongest signal:",
    "score_based_dims": "Score based on {dims}.",
    "scores_update": "Scores update as new data becomes available.",
    "check_back_soon": "check back soon",
    "higher_rated_alts": "higher-rated alternatives include {alts}.",
    "more_being_analyzed": "more {type}s are being analyzed — check back soon.",
    "in_category": "In the {category} category,",

    # Cross-links
    "cross_safety": "Safety",
    "cross_legit": "Legit?",
    "cross_scam": "Scam?",
    "cross_privacy": "Privacy",
    "cross_review": "Review",
    "cross_pros_cons": "Pros &amp; Cons",
    "cross_safe_kids": "Safe for Kids?",
    "cross_alternatives": "Alternatives",
    "cross_compare": "Compare",
    "cross_best_category": "Best in Category",
    "cross_who_owns": "Who Owns?",
    "cross_what_is": "What Is?",
    "cross_sells_data": "Sells Data?",
    "cross_hacked": "Hacked?",

    # Methodology / footer
    "methodology_entities": "Nerq analyzes over 7.5 million entities across 26 registries using the same methodology, enabling direct cross-entity comparison.",
    "scores_updated_continuously": "Scores are updated continuously as new data becomes available.",
    "disclaimer": "Nerq trust scores are automated assessments based on publicly available signals. They are not endorsements or guarantees. Always conduct your own due diligence.",
    "verify_independently": "Always verify independently using the",
    "full_methodology": "Full methodology documentation",
    "same_developer": "Same developer/company in other registries:",

    # Travel-specific
    "travel_advisory": "Travel advisory:",
    "exercise_normal": "Exercise Normal Precautions",
    "exercise_increased": "Exercise Increased Caution",
    "reconsider_travel": "Reconsider Travel",
    "do_not_travel": "Do Not Travel",
    "safe_solo": "Is {name} safe for solo travelers?",
    "safe_women": "Is {name} safe for women?",
    "safe_lgbtq": "Is {name} safe for LGBTQ+ travelers?",
    "safe_families": "Is {name} safe for families?",
    "safe_visit_now": "Is {name} safe to visit right now?",
    "tap_water_safe": "Is tap water safe to drink in {name}?",
    "need_vaccinations": "Do I need vaccinations for {name}?",

    # Health-specific
    "health_disclaimer": "This information is for educational purposes only and is not medical advice. Consult a healthcare professional before making health decisions.",
    "regulatory_status": "Regulatory Status",
    "safety_classification": "Safety Classification",
    "common_uses": "Common Uses",
    "what_are_side_effects": "What are the side effects of {name}?",
    "what_are_safer_alts": "What are safer alternatives to {name}?",
    "interact_medications": "Does {name} interact with medications?",
    "cause_irritation": "Can {name} cause skin irritation?",

    # Charity-specific
    "donation_safety": "Is it safe to donate to {name}?",
    "how_funds_used": "How does {name} use donated funds?",
    "financial_rating": "Financial Rating",
    "program_expenses": "Program Expenses",
    "admin_expenses": "Administrative Expenses",
    "fundraising_expenses": "Fundraising Expenses",

    # EU AI Act
    "eu_ai_risk_class": "EU AI Act Risk Class",
    "compliance_score_label": "Compliance Score",
    "jurisdictions": "Jurisdictions",
    "assessed_across": "Assessed across",

    # Not analyzed page
    "not_analyzed_title": "{name} — Not Yet Analyzed | Nerq",
    "not_analyzed_h1": "{name} — Not Yet Analyzed",
    "not_analyzed_msg": "{name} is not yet in the Nerq database. We analyze over 7.5 million entities — this one may be added soon.",
    "not_analyzed_meanwhile": "In the meantime, you can:",
    "not_analyzed_search": "Try searching with a different spelling",
    "not_analyzed_api": "Check the API directly",
    "not_analyzed_browse": "Browse entities we have analyzed",
    "not_analyzed_no_score": "This page does not contain a trust score because we have not analyzed this entity.",
    "not_analyzed_no_fabricate": "Nerq never fabricates ratings. If you believe this entity should be covered, it may appear in a future update.",
    # Entity description templates
    "is_a_type": "is a {type}",
    "with_trust_score": "with a Nerq Trust Score of {score}/100 ({grade})",
    "based_on_dims": "based on {dims} independent data dimensions",
    "type_vpn": "VPN service", "type_npm": "npm package", "type_pypi": "Python package",
    "type_android": "Android app", "type_ios": "iOS app", "type_chrome": "Chrome extension",
    "type_firefox": "Firefox extension", "type_wordpress": "WordPress plugin",
    "type_saas": "SaaS platform", "type_hosting": "web hosting provider",
    "type_website_builder": "website builder", "type_antivirus": "antivirus software",
    "type_password_manager": "password manager", "type_crypto": "crypto exchange",
    "type_crates": "Rust crate", "type_gems": "Ruby gem", "type_packagist": "PHP package",
    "type_vscode": "VS Code extension", "type_homebrew": "Homebrew formula",
    "type_steam": "Steam game", "type_website": "website",
    # Recommendation strings
    # VPN privacy section
    # Sidebar
    # Eyes alliance
    "eyes_five": "within the Five Eyes surveillance alliance",
    "eyes_nine": "within the Nine Eyes surveillance alliance",
    "eyes_fourteen": "within the Fourteen Eyes surveillance alliance",
    "eyes_outside": "outside all Eyes surveillance alliances — a privacy advantage",
    "eyes_none": "not a member of the Five/Nine/Fourteen Eyes alliances",
    "audit_yes": "{name} has been independently audited to verify its privacy claims",
    "audit_no": "{name} has not published an independent privacy audit",
    "sidebar_popular_in": "Popular in",
    "sidebar_browse": "Browse Categories",
    "sidebar_recently": "Recently Analyzed",
    "sidebar_safest_vpns": "Safest VPNs",
    "sidebar_most_private": "Most Private Apps",
    # Privacy
    "privacy_assessment": "Privacy Assessment",
    "undisclosed_jurisdiction": "an undisclosed jurisdiction",
    "serving_users": "Serving",
    # VPN
    # VPN security section
    "below_threshold": "Below the recommended threshold of 70.",
    "dim_security": "Security",
    "dim_maintenance": "Maintenance",
    "dim_popularity": "Popularity",
    "vpn_sec_score": "Security score",
    "privacy_score_label": "Privacy score",
    "vpn_proto": "Primary encryption protocol: {proto}, which is considered industry-standard for VPN connections.",
    "vpn_audit_positive": "According to independent audit reports, {name} has undergone third-party security audits verifying its infrastructure and no-logs claims. This is a strong positive signal — most VPN providers have not been independently audited.",
    "vpn_audit_verified": "Independent security audit verified.",
    "vpn_audit_none": "{name} has not published results from an independent security audit. While this does not indicate a security issue, audited VPNs provide higher assurance.",
    "vpn_no_breaches": "No known data breaches associated with this service.",
    "vpn_operates_under": "operates under",
    "vpn_jurisdiction": "jurisdiction",
    "vpn_outside_eyes": "outside the Five Eyes, Nine Eyes, and Fourteen Eyes surveillance alliances",
    "vpn_significant": "This is significant because VPN providers in non-allied jurisdictions are not subject to mandatory data retention laws or intelligence-sharing agreements.",
    "vpn_server_infra": "Server infrastructure",
    "vpn_logging_audited": "Logging policy: independently audited no-logs policy. According to independent audit reports, {name} does not store connection logs, browsing activity, or DNS queries.",
    # Cross-link text
    "xlink_complete_privacy": "Complete Your Privacy Setup",
    "xlink_complete_security": "Complete Your Security",
    "xlink_add_pm_vpn": "Add a password manager to your VPN for full protection",
    "xlink_add_vpn_pm": "Add a VPN to your password manager for full protection",
    "xlink_add_av": "Add Antivirus Protection",
    "xlink_add_av_vpn": "Complete your security with antivirus alongside your VPN",
    "xlink_add_vpn_av": "Add a VPN for encrypted browsing alongside your antivirus",
    "xlink_add_malware": "Add Malware Protection",
    "xlink_add_malware_desc": "Protect against keyloggers and credential stealers",
    "xlink_safest_crypto": "Safest Crypto Exchanges",
    "xlink_crypto_desc": "Independent crypto exchange safety ranking",
    "xlink_protect_server": "Protect Your Server",
    "xlink_protect_server_desc": "Add a VPN for secure remote administration",
    "xlink_secure_creds": "Secure Your Credentials",
    "xlink_secure_creds_desc": "Use a password manager for hosting and server credentials",
    "xlink_safest_hosting": "Safest Web Hosting",
    "xlink_hosting_desc": "Independent hosting provider safety ranking",
    "xlink_safest_av": "Safest Antivirus Software",
    "xlink_av_desc": "Independent antivirus safety ranking based on AV-TEST scores",
    "xlink_secure_passwords": "Secure Your Passwords",
    "xlink_secure_passwords_desc": "Use a password manager to protect your accounts",
    "xlink_secure_saas": "Secure Your SaaS Logins",
    "xlink_secure_saas_desc": "Use a password manager for your SaaS credentials",
    "xlink_access_secure": "Access Your Tools Securely",
    "xlink_access_secure_desc": "Use a VPN when accessing SaaS tools on public Wi-Fi",
    # FAQ questions (localizable)
    "faq_q3_alts": "What are safer alternatives to {name}?",
    "faq_q4_log": "Does {name} log my data?",
    "faq_q4_update": "How often is {name}'s safety score updated?",
    "faq_q4_vuln": "Does {name} have known vulnerabilities?",
    "faq_q4_kids": "Is {name} safe for kids?",
    "faq_q4_perms": "What permissions does {name} need?",
    "faq_q4_maintained": "Is {name} actively maintained?",
    "faq_q4_scam": "Is {name} a scam?",
    "faq_q4_telemetry": "Does {name} collect telemetry?",
    "faq_q4_gdpr": "Is {name} GDPR compliant?",
    "faq_q4_training": "Does {name} use my data for training?",
    "faq_q5_vs": "{name} vs alternatives: which is safer?",
    "faq_q5_regulated": "Can I use {name} in a regulated environment?",
    # FAQ answers (localizable)
    "faq_a4_vuln": "Nerq checks {name} against NVD, OSV.dev, and registry-specific vulnerability databases. Current security score: {sec_score}. Run your package manager's audit command for the latest findings.",
    "faq_a4_kids": "{name} has a Nerq Trust Score of {score}/100. Parents should review the full safety report, check permissions and content ratings, and apply appropriate parental controls.",
    "faq_a4_perms": "Review {name}'s requested permissions carefully. Extensions requesting broad data access carry the highest risk. Current trust score: {score}/100.",
    "faq_a4_maintained": "{name} maintenance score: {maint_score}. Check the repository for recent commit activity and issue responsiveness.",
    "faq_a5_verified": "{name} meets the Nerq Verified threshold (70+). Safe for production use.",
    "faq_a5_not_verified": "{name} has not reached the Nerq Verified threshold of 70. Additional due diligence is recommended.",
    # Recommendation strings
    # See Also section
    "see_also": "See Also",
    "see_also_vs": "{a} vs {b}",
    "see_also_alts": "Alternatives to {name}",
    "see_also_best": "Best {category} 2026",
    "rec_privacy": "recommended for privacy-conscious use",
    "rec_production": "recommended for production use",
    "rec_general": "recommended for general use",
    "rec_play": "recommended for play",
    "rec_use": "recommended for use",
    "rec_wordpress": "recommended for use in WordPress",
}

# Translation dictionaries per language — keyed by _STRINGS keys
_TRANSLATIONS = {
    "es": {
        "dim_popularity": "Popularidad",
        "faq_q3_alts": "¿Cuáles son alternativas más seguras a {name}?",
        "faq_q4_log": "¿{name} registra mis datos?",
        "faq_q4_update": "¿Con qué frecuencia se actualiza la puntuación de {name}?",
        "faq_q5_vs": "{name} vs alternativas: ¿cuál es más seguro?",
        "faq_q5_regulated": "¿Puedo usar {name} en un entorno regulado?",
        "vpn_sec_score": "Puntuación de seguridad",
        "privacy_score_label": "Puntuación de privacidad",
        "strong": "fuerte",
        "moderate": "moderado",
        "weak": "débil",
        "actively_maintained": "mantenido activamente",
        "moderately_maintained": "mantenimiento moderado",
        "low_maintenance": "baja actividad de mantenimiento",
        "well_documented": "bien documentado",
        "partial_documentation": "documentación parcial",
        "limited_documentation": "documentación limitada",
        "community_adoption": "adopción comunitaria",
        "faq_q4_vuln": "¿Tiene {name} vulnerabilidades conocidas?",
        "faq_q4_kids": "¿Es {name} seguro para niños?",
        "faq_q4_perms": "¿Qué permisos necesita {name}?",
        "faq_q4_maintained": "¿Se mantiene activamente {name}?",
        "faq_a4_vuln": "Nerq verifica {name} contra NVD, OSV.dev y bases de datos de vulnerabilidades. Puntuación de seguridad actual: {sec_score}. Ejecute el comando de auditoría de su gestor de paquetes.",
        "faq_a4_kids": "{name} tiene una puntuación Nerq de {score}/100. Los padres deben revisar el informe completo y verificar los permisos.",
        "faq_a4_perms": "Revise los permisos solicitados por {name} cuidadosamente. Puntuación de confianza: {score}/100.",
        "faq_a4_maintained": "Puntuación de mantenimiento de {name}: {maint_score}. Verifique la actividad reciente del repositorio.",
        "faq_a5_verified": "{name} cumple el umbral de verificación Nerq (70+). Seguro para uso en producción.",
        "faq_a5_not_verified": "{name} no ha alcanzado el umbral de verificación Nerq de 70. Se recomienda diligencia adicional.",
        "more_being_analyzed": "se están analizando más {type} — vuelve pronto.",
        "dim_maintenance": "Mantenimiento",
        "dim_security": "Seguridad",
        "sidebar_most_private": "Apps más privadas",
        "sidebar_safest_vpns": "VPNs más seguros",
        "eyes_outside": "fuera de todas las alianzas Eyes — una ventaja de privacidad",
        "serving_users": "Sirviendo a",
        "privacy_assessment": "Evaluación de privacidad",
        "sidebar_recently": "Analizados recientemente",
        "sidebar_browse": "Explorar categorías",
        "sidebar_popular_in": "Popular en",
        "vpn_logging_audited": "Política de registros: política de no-registros auditada independientemente. Según informes de auditoría independientes, {name} no almacena registros de conexión, actividad de navegación ni consultas DNS.",
        "vpn_server_infra": "Infraestructura de servidores",
        "vpn_significant": "Esto es significativo porque los proveedores de VPN en jurisdicciones no aliadas no están sujetos a leyes obligatorias de retención de datos o acuerdos de intercambio de inteligencia.",
        "vpn_outside_eyes": "fuera de las alianzas de vigilancia Five Eyes, Nine Eyes y Fourteen Eyes",
        "vpn_jurisdiction": "jurisdicción",
        "vpn_operates_under": "opera bajo",
        "xlink_av_desc": "Ranking independiente de antivirus basado en AV-TEST",
        "xlink_safest_av": "Antivirus más seguro",
        "xlink_hosting_desc": "Ranking independiente de proveedores de hosting",
        "xlink_safest_hosting": "Hosting más seguro",
        "xlink_crypto_desc": "Ranking independiente de seguridad de exchanges",
        "xlink_safest_crypto": "Exchanges crypto más seguros",
        "xlink_access_secure_desc": "Usa una VPN al acceder a herramientas SaaS en Wi-Fi público",
        "xlink_access_secure": "Accede a tus herramientas de forma segura",
        "xlink_secure_saas_desc": "Usa un gestor de contraseñas para tus credenciales SaaS",
        "xlink_secure_saas": "Protege tus inicios de sesión SaaS",
        "xlink_secure_creds_desc": "Usa un gestor de contraseñas para credenciales de hosting",
        "xlink_secure_creds": "Protege tus credenciales",
        "xlink_protect_server_desc": "Añade una VPN para administración remota segura",
        "xlink_protect_server": "Protege tu servidor",
        "xlink_secure_passwords_desc": "Usa un gestor de contraseñas para proteger tus cuentas",
        "xlink_secure_passwords": "Protege tus contraseñas",
        "xlink_add_vpn_av": "Añade una VPN para navegación cifrada",
        "xlink_add_malware_desc": "Protección contra keyloggers y robo de credenciales",
        "xlink_add_malware": "Añadir protección antimalware",
        "xlink_add_av_vpn": "Completa tu seguridad con antivirus junto a tu VPN",
        "xlink_add_av": "Añadir protección antivirus",
        "xlink_add_vpn_pm": "Añade una VPN a tu gestor de contraseñas",
        "xlink_add_pm_vpn": "Añade un gestor de contraseñas a tu VPN",
        "xlink_complete_security": "Completa tu seguridad",
        "xlink_complete_privacy": "Completa tu privacidad",
        "type_wordpress": "plugin de WordPress",
        "type_crates": "paquete Rust",
        "type_pypi": "paquete Python",
        "type_steam": "juego de Steam",
        "type_android": "aplicación Android",
        "type_website_builder": "creador de sitios web",
        "type_crypto": "exchange de criptomonedas",
        "type_password_manager": "gestor de contraseñas",
        "type_antivirus": "software antivirus",
        "type_hosting": "proveedor de hosting",
        "type_saas": "plataforma SaaS",
        "type_npm": "paquete npm",
        "type_vpn": "servicio VPN",
        "based_on_dims": "basado en {dims} dimensiones de datos independientes",
        "with_trust_score": "con un Nerq Trust Score de {score}/100 ({grade})",
        "is_a_type": "es un {type}",
        "rec_wordpress": "recomendado para WordPress",
        "rec_use": "recomendado para uso",
        "rec_play": "recomendado para jugar",
        "rec_general": "recomendado para uso general",
        "rec_production": "recomendado para uso en producción",
        "rec_privacy": "recomendado para uso consciente de la privacidad",
        "data_sourced": "Datos de {sources}. Última actualización: {date}.",
        "score_based_dims": "Puntuación basada en {dims}.",
        "yes_safe_short": "Sí, es seguro de usar.",
        "title_safe": "¿Es {name} Seguro? Análisis Independiente de Confianza y Seguridad {year} | Nerq",
        "title_safe_visit": "¿Es {name} Seguro para Visitar? Puntuación de Seguridad {year} y Guía de Viaje | Nerq",
        "title_charity": "¿Es {name} una Organización Benéfica Confiable? Análisis de Confianza {year} | Nerq",
        "title_ingredient": "¿Es {name} Seguro? Análisis de Salud y Seguridad {year} | Nerq",
        "h1_safe": "¿Es {name} Seguro?",
        "h1_safe_visit": "¿Es {name} Seguro para Visitar?",
        "h1_trustworthy_charity": "¿Es {name} una Organización Benéfica Confiable?",
        "h1_ingredient_safe": "¿Es {name} Seguro?",
        "breadcrumb_safety": "Informes de Seguridad",
        "security_analysis": "Análisis de Seguridad", "privacy_report": "Informe de Privacidad", "similar_in_registry": "Similar {registry} por Puntuación de Confianza", "see_all_best": "Ver los más seguros {registry}",
        "pv_grade": "Grado {grade}", "pv_body": "Basado en el análisis de {dims} dimensiones de confianza, se {verdict}.", "pv_vulns": "con {count} vulnerabilidades conocidas", "pv_updated": "Última actualización: {date}.", "pv_safe": "considera seguro de usar", "pv_generally_safe": "considera generalmente seguro pero con algunas preocupaciones", "pv_notable_concerns": "tiene preocupaciones de seguridad notables", "pv_significant_risks": "tiene riesgos de seguridad significativos", "pv_unsafe": "considera inseguro",
        "h2q_trust_score": "¿Cuál es la puntuación de confianza de {name}?", "h2q_key_findings": "¿Cuáles son los hallazgos de seguridad clave de {name}?", "h2q_details": "¿Qué es {name} y quién lo mantiene?", "ans_trust": "{name} tiene una Puntuación de Confianza Nerq de {score}/100, obteniendo un grado {grade}. Esta puntuación se basa en {dims} dimensiones medidas independientemente.", "ans_findings_strong": "La señal más fuerte de {name} es {signal} con {signal_score}/100.", "ans_no_vulns": "No se han detectado vulnerabilidades conocidas.", "ans_has_vulns": "Se identificaron {count} vulnerabilidades conocidas.", "ans_verified": "Cumple con el umbral verificado de Nerq de 70+.", "ans_not_verified": "Aún no ha alcanzado el umbral verificado de Nerq de 70+.",
        "trust_score_breakdown": "Desglose de Puntuación de Confianza",
        "safety_score_breakdown": "Desglose de Puntuación de Seguridad",
        "key_findings": "Hallazgos Clave",
        "key_safety_findings": "Hallazgos Clave de Seguridad",
        "details": "Detalles",
        "detailed_score_analysis": "Análisis Detallado de Puntuación",
        "faq": "Preguntas Frecuentes",
        "community_reviews": "Reseñas de la Comunidad",
        "regulatory_compliance": "Cumplimiento Regulatorio",
        "how_calculated": "Cómo calculamos esta puntuación",
        "popular_alternatives": "Alternativas Populares en {category}",
        "safer_alternatives": "Alternativas Más Seguras",
        "across_platforms": "{name} en Otras Plataformas",
        "safety_guide": "Guía de Seguridad: {name}",
        "what_is": "¿Qué es {name}?",
        "key_concerns": "Principales Preocupaciones de Seguridad para {type}",
        "how_to_verify": "Cómo Verificar la Seguridad",
        "trust_assessment": "Evaluación de Confianza",
        "what_data_collect": "¿Qué datos recopila {name}?",
        "is_secure": "¿Es {name} seguro?",
        "yes_safe": "Sí, {name} es seguro para usar.",
        "use_caution": "Usa {name} con precaución.",
        "exercise_caution": "Ten precaución con {name}.",
        "significant_concerns": "{name} tiene preocupaciones significativas de confianza.",
        "safe": "Seguro",
        "use_caution_short": "Precaución",
        "avoid": "Evitar",
        "passes_threshold": "Supera el umbral verificado de Nerq",
        "below_threshold": "Por debajo del umbral verificado de Nerq",
        "significant_gaps": "Se detectaron brechas significativas de confianza",
        "meets_threshold_detail": "Cumple con el umbral de confianza de Nerq con señales sólidas en seguridad, mantenimiento y adopción comunitaria",
        "not_reached_threshold": "y aún no ha alcanzado el umbral de confianza de Nerq (70+).",
        "score_based_on": "Esta puntuación se basa en un análisis automatizado de señales de seguridad, mantenimiento, comunidad y calidad.",
        "recommended_production": "Recomendado para uso en producción",
        "last_analyzed": "Último análisis:",
        "author_label": "Autor",
        "category_label": "Categoría",
        "stars_label": "Estrellas",
        "global_rank_label": "Ranking Global",
        "source_label": "Fuente",
        "machine_readable": "Datos legibles por máquina (JSON)",
        "full_analysis": "Análisis completo:",
        "privacy_report": "Informe de Privacidad de {name}",
        "security_report": "Informe de Seguridad de {name}",
        "write_review": "Escribir una reseña",
        "no_reviews": "Sin reseñas aún.",
        "be_first_review": "Sé el primero en reseñar {name}",
        "security": "Seguridad",
        "compliance": "Cumplimiento",
        "maintenance": "Mantenimiento",
        "documentation": "Documentación",
        "popularity": "Popularidad",
        "overall_trust": "Confianza General",
        "privacy": "Privacidad",
        "reliability": "Fiabilidad",
        "transparency": "Transparencia",
        "disclaimer": "Las puntuaciones de confianza de Nerq son evaluaciones automatizadas basadas en señales disponibles públicamente. No son respaldos ni garantías. Siempre realice su propia diligencia debida.",
        "same_developer": "Mismo desarrollador/empresa en otros registros:",
        "methodology_entities": "Nerq analiza más de 7,5 millones de entidades en 26 registros utilizando la misma metodología, lo que permite la comparación directa entre entidades.",
        "scores_updated_continuously": "Las puntuaciones se actualizan continuamente a medida que nuevos datos están disponibles.",
        "strongest_signal": "Señal más fuerte:",
        "in_category": "En la categoría {category},",
        "check_back_soon": "vuelva pronto",
        "safe_solo": "¿Es {name} seguro para viajeros solos?",
        "safe_women": "¿Es {name} seguro para mujeres?",
        "safe_families": "¿Es {name} seguro para familias?",
        "safe_visit_now": "¿Es {name} seguro para visitar ahora?",
        "what_are_side_effects": "¿Cuáles son los efectos secundarios de {name}?",
        "what_are_safer_alts": "¿Cuáles son alternativas más seguras a {name}?",
    },
    "de": {
        "dim_popularity": "Beliebtheit",
        "faq_q3_alts": "Was sind sicherere Alternativen zu {name}?",
        "faq_q4_log": "Protokolliert {name} meine Daten?",
        "faq_q4_update": "Wie oft wird die Sicherheitsbewertung von {name} aktualisiert?",
        "faq_q5_vs": "{name} vs Alternativen: Was ist sicherer?",
        "faq_q5_regulated": "Kann ich {name} in einer regulierten Umgebung verwenden?",
        "faq_q4_vuln": "Hat {name} bekannte Schwachstellen?",
        "faq_q4_kids": "Ist {name} sicher für Kinder?",
        "faq_q4_perms": "Welche Berechtigungen benötigt {name}?",
        "faq_q4_maintained": "Wird {name} aktiv gepflegt?",
        "faq_a4_vuln": "Nerq prüft {name} gegen NVD, OSV.dev und registerspezifische Schwachstellendatenbanken. Aktuelle Sicherheitsbewertung: {sec_score}. Führen Sie den Audit-Befehl Ihres Paketmanagers aus.",
        "faq_a4_kids": "{name} hat einen Nerq-Wert von {score}/100. Eltern sollten den vollständigen Bericht prüfen und Berechtigungen kontrollieren.",
        "faq_a4_perms": "Prüfen Sie die angeforderten Berechtigungen von {name} sorgfältig. Vertrauenswert: {score}/100.",
        "faq_a4_maintained": "{name} Wartungsbewertung: {maint_score}. Prüfen Sie das Repository auf aktuelle Aktivität.",
        "faq_a5_verified": "{name} erfüllt die Nerq-Verifizierungsschwelle (70+). Sicher für den Produktionseinsatz.",
        "faq_a5_not_verified": "{name} hat die Nerq-Verifizierungsschwelle von 70 nicht erreicht. Zusätzliche Prüfung empfohlen.",
        "more_being_analyzed": "weitere {type} werden analysiert — schauen Sie bald wieder vorbei.",
        "strong": "stark",
        "moderate": "mäßig",
        "weak": "schwach",
        "actively_maintained": "aktiv gepflegt",
        "moderately_maintained": "mäßig gepflegt",
        "low_maintenance": "geringe Wartungsaktivität",
        "well_documented": "gut dokumentiert",
        "partial_documentation": "teilweise Dokumentation",
        "limited_documentation": "begrenzte Dokumentation",
        "community_adoption": "Community-Akzeptanz",
        "dim_maintenance": "Wartung",
        "dim_security": "Sicherheit",
        "vpn_no_breaches": "Keine bekannten Datenschutzverletzungen im Zusammenhang mit diesem Dienst.",
        "vpn_audit_none": "{name} hat keine Ergebnisse einer unabhängigen Sicherheitsprüfung veröffentlicht. Geprüfte VPNs bieten höhere Sicherheit.",
        "vpn_audit_verified": "Unabhängiges Sicherheitsaudit verifiziert.",
        "vpn_audit_positive": "Laut unabhängiger Prüfberichte hat {name} Sicherheitsaudits durch Dritte unterzogen. Dies ist ein stark positives Signal — die meisten VPN-Anbieter wurden nicht unabhängig geprüft.",
        "vpn_proto": "Primäres Verschlüsselungsprotokoll: {proto}, das als Industriestandard für VPN-Verbindungen gilt.",
        "vpn_sec_score": "Sicherheitsbewertung",
        "privacy_score_label": "Datenschutzbewertung",
        "sidebar_most_private": "Privateste Apps",
        "sidebar_safest_vpns": "Sicherste VPNs",
        "audit_no": "{name} hat kein unabhängiges Datenschutz-Audit veröffentlicht",
        "audit_yes": "{name} wurde unabhängig geprüft, um seine Datenschutzansprüche zu verifizieren",
        "eyes_none": "kein Mitglied der Five/Nine/Fourteen Eyes-Allianzen",
        "eyes_fourteen": "innerhalb der Fourteen Eyes-Überwachungsallianz",
        "eyes_nine": "innerhalb der Nine Eyes-Überwachungsallianz",
        "eyes_five": "innerhalb der Five Eyes-Überwachungsallianz",
        "eyes_outside": "außerhalb aller Eyes-Überwachungsallianzen — ein Datenschutzvorteil",
        "undisclosed_jurisdiction": "einer unbekannten Gerichtsbarkeit",
        "serving_users": "Bedient",
        "privacy_assessment": "Datenschutzbewertung",
        "sidebar_recently": "Kürzlich analysiert",
        "sidebar_browse": "Kategorien durchsuchen",
        "sidebar_popular_in": "Beliebt in",
        "vpn_logging_audited": "Protokollierungsrichtlinie: unabhängig geprüfte No-Logs-Policy. Laut unabhängiger Prüfberichte speichert {name} keine Verbindungsprotokolle, Browser-Aktivitäten oder DNS-Abfragen.",
        "vpn_server_infra": "Server-Infrastruktur",
        "vpn_significant": "Dies ist bedeutsam, da VPN-Anbieter in nicht-alliierten Rechtsgebieten nicht den Datenspeicherungspflichten oder Geheimdienstabkommen unterliegen.",
        "vpn_outside_eyes": "außerhalb der Five Eyes, Nine Eyes und Fourteen Eyes Überwachungsallianzen",
        "vpn_jurisdiction": "Gerichtsbarkeit",
        "vpn_operates_under": "operiert unter",
        "xlink_av_desc": "Unabhängiges Antivirus-Ranking basierend auf AV-TEST",
        "xlink_safest_av": "Sicherste Antivirus-Software",
        "xlink_hosting_desc": "Unabhängiges Hosting-Sicherheitsranking",
        "xlink_safest_hosting": "Sicherste Hosting-Anbieter",
        "xlink_crypto_desc": "Unabhängiges Krypto-Börsen-Sicherheitsranking",
        "xlink_safest_crypto": "Sicherste Krypto-Börsen",
        "xlink_access_secure_desc": "Verwenden Sie ein VPN beim Zugriff auf SaaS-Tools über öffentliches WLAN",
        "xlink_access_secure": "Greifen Sie sicher auf Ihre Tools zu",
        "xlink_secure_saas_desc": "Verwenden Sie einen Passwort-Manager für Ihre SaaS-Zugangsdaten",
        "xlink_secure_saas": "Schützen Sie Ihre SaaS-Logins",
        "xlink_secure_creds_desc": "Verwenden Sie einen Passwort-Manager für Hosting-Zugangsdaten",
        "xlink_secure_creds": "Schützen Sie Ihre Zugangsdaten",
        "xlink_protect_server_desc": "Fügen Sie ein VPN für sichere Fernverwaltung hinzu",
        "xlink_protect_server": "Schützen Sie Ihren Server",
        "xlink_secure_passwords_desc": "Verwenden Sie einen Passwort-Manager zum Schutz Ihrer Konten",
        "xlink_secure_passwords": "Schützen Sie Ihre Passwörter",
        "xlink_add_vpn_av": "Fügen Sie ein VPN für verschlüsseltes Surfen hinzu",
        "xlink_add_malware_desc": "Schutz vor Keyloggern und Anmeldedatendiebstahl",
        "xlink_add_malware": "Malware-Schutz hinzufügen",
        "xlink_add_av_vpn": "Vervollständigen Sie Ihre Sicherheit mit Antivirus neben Ihrem VPN",
        "xlink_add_av": "Antivirenschutz hinzufügen",
        "xlink_add_vpn_pm": "Fügen Sie ein VPN zu Ihrem Passwort-Manager hinzu",
        "xlink_add_pm_vpn": "Fügen Sie einen Passwort-Manager zu Ihrem VPN hinzu",
        "xlink_complete_security": "Vervollständigen Sie Ihre Sicherheit",
        "xlink_complete_privacy": "Vervollständigen Sie Ihren Datenschutz",
        "type_wordpress": "WordPress-Plugin",
        "type_crates": "Rust-Paket",
        "type_pypi": "Python-Paket",
        "type_steam": "Steam-Spiel",
        "type_android": "Android-App",
        "type_website_builder": "Website-Baukasten",
        "type_crypto": "Krypto-Börse",
        "type_password_manager": "Passwort-Manager",
        "type_antivirus": "Antivirus-Software",
        "type_hosting": "Hosting-Anbieter",
        "type_saas": "SaaS-Plattform",
        "type_npm": "npm-Paket",
        "type_vpn": "VPN-Dienst",
        "based_on_dims": "basierend auf {dims} unabhängigen Datendimensionen",
        "with_trust_score": "mit einem Nerq-Vertrauenswert von {score}/100 ({grade})",
        "is_a_type": "ist ein {type}",
        "rec_wordpress": "empfohlen für WordPress-Nutzung",
        "rec_use": "empfohlen zur Nutzung",
        "rec_play": "empfohlen zum Spielen",
        "rec_general": "empfohlen für allgemeine Nutzung",
        "rec_production": "empfohlen für den Produktionseinsatz",
        "rec_privacy": "empfohlen für datenschutzbewusste Nutzung",
        "data_sourced": "Daten von {sources}. Zuletzt aktualisiert: {date}.",
        "score_based_dims": "Bewertung basierend auf {dims}.",
        "yes_safe_short": "Ja, es ist sicher in der Verwendung.",
        "title_safe": "Ist {name} sicher? Unabhängige Vertrauens- und Sicherheitsanalyse {year} | Nerq",
        "title_safe_visit": "Ist {name} sicher zu besuchen? {year} Sicherheitsbewertung &amp; Reiseführer | Nerq",
        "title_charity": "Ist {name} eine vertrauenswürdige Wohltätigkeitsorganisation? {year} Vertrauensanalyse | Nerq",
        "title_ingredient": "Ist {name} sicher? {year} Gesundheits- &amp; Sicherheitsanalyse | Nerq",
        "h1_safe": "Ist {name} sicher?",
        "h1_safe_visit": "Ist {name} sicher zu besuchen?",
        "h1_trustworthy_charity": "Ist {name} eine vertrauenswürdige Wohltätigkeitsorganisation?",
        "h1_ingredient_safe": "Ist {name} sicher?",
        "breadcrumb_safety": "Sicherheitsberichte",
        "security_analysis": "Sicherheitsanalyse", "privacy_report": "Datenschutzbericht", "similar_in_registry": "Ähnliche {registry} nach Vertrauensbewertung", "see_all_best": "Alle sichersten {registry} anzeigen",
        "pv_grade": "Note {grade}", "pv_body": "Basierend auf der Analyse von {dims} Vertrauensdimensionen wird es als {verdict} eingestuft.", "pv_vulns": "mit {count} bekannten Schwachstellen", "pv_updated": "Zuletzt aktualisiert: {date}.", "pv_safe": "sicher in der Verwendung", "pv_generally_safe": "generell sicher, aber mit einigen Bedenken", "pv_notable_concerns": "bemerkenswerte Sicherheitsbedenken", "pv_significant_risks": "erhebliche Sicherheitsrisiken", "pv_unsafe": "unsicher",
        "h2q_trust_score": "Was ist die Vertrauensbewertung von {name}?", "h2q_key_findings": "Was sind die wichtigsten Sicherheitsergebnisse für {name}?", "h2q_details": "Was ist {name} und wer pflegt es?", "ans_trust": "{name} hat eine Nerq-Vertrauensbewertung von {score}/100 und erhält die Note {grade}. Diese Bewertung basiert auf {dims} unabhängig gemessenen Dimensionen.", "ans_findings_strong": "Das stärkste Signal von {name} ist {signal} mit {signal_score}/100.", "ans_no_vulns": "Es wurden keine bekannten Schwachstellen erkannt.", "ans_has_vulns": "Es wurden {count} bekannte Schwachstellen identifiziert.", "ans_verified": "Erfüllt die Nerq-Vertrauensschwelle von 70+.", "ans_not_verified": "Hat die Nerq-Vertrauensschwelle von 70+ noch nicht erreicht.",
        "trust_score_breakdown": "Vertrauensbewertung im Detail",
        "safety_score_breakdown": "Sicherheitsbewertung im Detail",
        "key_findings": "Wichtige Erkenntnisse",
        "key_safety_findings": "Wichtige Sicherheitserkenntnisse",
        "details": "Details",
        "detailed_score_analysis": "Detaillierte Bewertungsanalyse",
        "faq": "Häufig gestellte Fragen",
        "community_reviews": "Community-Bewertungen",
        "regulatory_compliance": "Regulatorische Konformität",
        "how_calculated": "Wie wir diese Bewertung berechnet haben",
        "popular_alternatives": "Beliebte Alternativen in {category}",
        "safer_alternatives": "Sicherere Alternativen",
        "across_platforms": "{name} auf anderen Plattformen",
        "safety_guide": "Sicherheitsleitfaden: {name}",
        "what_is": "Was ist {name}?",
        "key_concerns": "Wichtige Sicherheitsbedenken für {type}",
        "how_to_verify": "Wie man die Sicherheit überprüft",
        "trust_assessment": "Vertrauensbewertung",
        "what_data_collect": "Welche Daten erhebt {name}?",
        "is_secure": "Ist {name} sicher?",
        "yes_safe": "Ja, {name} ist sicher in der Verwendung.",
        "use_caution": "Verwende {name} mit Vorsicht.",
        "exercise_caution": "Vorsicht bei {name}.",
        "significant_concerns": "{name} hat erhebliche Vertrauensprobleme.",
        "safe": "Sicher",
        "use_caution_short": "Vorsicht",
        "avoid": "Vermeiden",
        "passes_threshold": "Erfüllt die Nerq-Vertrauensschwelle",
        "below_threshold": "Unter der Nerq-Vertrauensschwelle",
        "significant_gaps": "Erhebliche Vertrauenslücken erkannt",
        "meets_threshold_detail": "Es erfüllt die Vertrauensschwelle von Nerq mit starken Signalen in Sicherheit, Wartung und Community-Akzeptanz",
        "not_reached_threshold": "hat die Nerq-Vertrauensschwelle (70+) noch nicht erreicht.",
        "score_based_on": "Diese Bewertung basiert auf automatisierter Analyse von Sicherheits-, Wartungs-, Community- und Qualitätssignalen.",
        "recommended_production": "Empfohlen für den Produktionseinsatz",
        "last_analyzed": "Zuletzt analysiert:",
        "author_label": "Autor",
        "category_label": "Kategorie",
        "stars_label": "Sterne",
        "global_rank_label": "Globaler Rang",
        "source_label": "Quelle",
        "machine_readable": "Maschinenlesbare Daten (JSON)",
        "full_analysis": "Vollständige Analyse:",
        "privacy_report": "{name} Datenschutzbericht",
        "security_report": "{name} Sicherheitsbericht",
        "write_review": "Bewertung schreiben",
        "no_reviews": "Noch keine Bewertungen.",
        "be_first_review": "Sei der Erste, der {name} bewertet",
        "security": "Sicherheit",
        "compliance": "Konformität",
        "maintenance": "Wartung",
        "documentation": "Dokumentation",
        "popularity": "Beliebtheit",
        "overall_trust": "Gesamtvertrauen",
        "privacy": "Datenschutz",
        "reliability": "Zuverlässigkeit",
        "transparency": "Transparenz",
        "disclaimer": "Nerq-Vertrauensbewertungen sind automatisierte Bewertungen basierend auf öffentlich verfügbaren Signalen. Sie sind keine Empfehlungen oder Garantien. Führen Sie immer Ihre eigene Sorgfaltsprüfung durch.",
        "same_developer": "Gleicher Entwickler/Unternehmen in anderen Registern:",
        "strongest_signal": "Stärkstes Signal:",
        "in_category": "In der Kategorie {category},",
        "check_back_soon": "schauen Sie bald wieder vorbei",
        "safe_solo": "Ist {name} sicher für Alleinreisende?",
        "safe_women": "Ist {name} sicher für Frauen?",
        "safe_families": "Ist {name} sicher für Familien?",
        "safe_visit_now": "Ist {name} jetzt sicher zu besuchen?",
        "what_are_side_effects": "Was sind die Nebenwirkungen von {name}?",
        "what_are_safer_alts": "Was sind sicherere Alternativen zu {name}?",
    },
    "fr": {
        "dim_popularity": "Popularité",
        "vpn_sec_score": "Score de sécurité",
        "privacy_score_label": "Score de confidentialité",
        "faq_q3_alts": "Quelles sont les alternatives plus sûres à {name} ?",
        "faq_q4_log": "Est-ce que {name} enregistre mes données ?",
        "faq_q4_update": "À quelle fréquence le score de sécurité de {name} est-il mis à jour ?",
        "faq_q5_vs": "{name} vs alternatives : lequel est le plus sûr ?",
        "faq_q5_regulated": "Puis-je utiliser {name} dans un environnement réglementé ?",
        "faq_q4_vuln": "Est-ce que {name} a des vulnérabilités connues ?",
        "faq_q4_kids": "Est-ce que {name} est sûr pour les enfants ?",
        "faq_q4_perms": "Quelles permissions {name} nécessite-t-il ?",
        "faq_q4_maintained": "Est-ce que {name} est activement maintenu ?",
        "faq_a4_vuln": "Nerq vérifie {name} contre NVD, OSV.dev et les bases de données de vulnérabilités. Score de sécurité actuel : {sec_score}.",
        "faq_a4_kids": "{name} a un score Nerq de {score}/100. Les parents doivent vérifier le rapport complet et les autorisations.",
        "faq_a4_perms": "Vérifiez attentivement les permissions demandées par {name}. Score de confiance : {score}/100.",
        "faq_a4_maintained": "Score de maintenance de {name} : {maint_score}. Vérifiez l'activité récente du dépôt.",
        "faq_a5_verified": "{name} atteint le seuil de vérification Nerq (70+). Sûr pour la production.",
        "faq_a5_not_verified": "{name} n'a pas atteint le seuil de vérification Nerq de 70. Vérification supplémentaire recommandée.",
        "more_being_analyzed": "d'autres {type} sont en cours d'analyse — revenez bientôt.",
        "strong": "fort",
        "moderate": "modéré",
        "weak": "faible",
        "actively_maintained": "activement maintenu",
        "moderately_maintained": "modérément maintenu",
        "low_maintenance": "faible activité de maintenance",
        "well_documented": "bien documenté",
        "partial_documentation": "documentation partielle",
        "limited_documentation": "documentation limitée",
        "community_adoption": "adoption communautaire",
        "dim_maintenance": "Maintenance",
        "dim_security": "Sécurité",
        "sidebar_most_private": "Apps les plus privées",
        "sidebar_safest_vpns": "VPN les plus sûrs",
        "eyes_outside": "en dehors de toutes les alliances Eyes — un avantage pour la vie privée",
        "serving_users": "Au service de",
        "privacy_assessment": "Évaluation de la confidentialité",
        "sidebar_recently": "Analysés récemment",
        "sidebar_browse": "Parcourir les catégories",
        "sidebar_popular_in": "Populaire dans",
        "vpn_logging_audited": "Politique de journalisation: politique no-logs auditée indépendamment. Selon les rapports d'audit indépendants, {name} ne stocke pas les journaux de connexion, l'activité de navigation ni les requêtes DNS.",
        "vpn_server_infra": "Infrastructure serveur",
        "vpn_significant": "C'est significatif car les fournisseurs VPN dans des juridictions non alliées ne sont pas soumis aux lois de rétention de données ni aux accords de partage de renseignements.",
        "vpn_outside_eyes": "en dehors des alliances de surveillance Five Eyes, Nine Eyes et Fourteen Eyes",
        "vpn_jurisdiction": "juridiction",
        "vpn_operates_under": "opère sous",
        "xlink_av_desc": "Classement antivirus indépendant basé sur AV-TEST",
        "xlink_safest_av": "Antivirus le plus sûr",
        "xlink_hosting_desc": "Classement indépendant des hébergeurs",
        "xlink_safest_hosting": "Hébergement le plus sûr",
        "xlink_crypto_desc": "Classement indépendant de sécurité des exchanges",
        "xlink_safest_crypto": "Échanges crypto les plus sûrs",
        "xlink_access_secure_desc": "Utilisez un VPN pour accéder aux outils SaaS sur un Wi-Fi public",
        "xlink_access_secure": "Accédez à vos outils en toute sécurité",
        "xlink_secure_saas_desc": "Utilisez un gestionnaire de mots de passe pour vos identifiants SaaS",
        "xlink_secure_saas": "Sécurisez vos connexions SaaS",
        "xlink_secure_creds_desc": "Utilisez un gestionnaire de mots de passe pour les identifiants d'hébergement",
        "xlink_secure_creds": "Sécurisez vos identifiants",
        "xlink_protect_server_desc": "Ajoutez un VPN pour l'administration à distance sécurisée",
        "xlink_protect_server": "Protégez votre serveur",
        "xlink_secure_passwords_desc": "Utilisez un gestionnaire de mots de passe pour protéger vos comptes",
        "xlink_secure_passwords": "Protégez vos mots de passe",
        "xlink_add_vpn_av": "Ajoutez un VPN pour la navigation chiffrée",
        "xlink_add_malware_desc": "Protection contre les enregistreurs de frappe et le vol d'identifiants",
        "xlink_add_malware": "Ajouter une protection anti-malware",
        "xlink_add_av_vpn": "Complétez votre sécurité avec un antivirus et votre VPN",
        "xlink_add_av": "Ajouter une protection antivirus",
        "xlink_add_vpn_pm": "Ajoutez un VPN à votre gestionnaire de mots de passe",
        "xlink_add_pm_vpn": "Ajoutez un gestionnaire de mots de passe à votre VPN",
        "xlink_complete_security": "Complétez votre sécurité",
        "xlink_complete_privacy": "Complétez votre confidentialité",
        "type_wordpress": "plugin WordPress",
        "type_crates": "package Rust",
        "type_pypi": "package Python",
        "type_steam": "jeu Steam",
        "type_android": "application Android",
        "type_website_builder": "créateur de sites",
        "type_crypto": "échange crypto",
        "type_password_manager": "gestionnaire de mots de passe",
        "type_antivirus": "logiciel antivirus",
        "type_hosting": "hébergeur web",
        "type_saas": "plateforme SaaS",
        "type_npm": "package npm",
        "type_vpn": "service VPN",
        "based_on_dims": "basé sur {dims} dimensions de données indépendantes",
        "with_trust_score": "avec un Nerq Trust Score de {score}/100 ({grade})",
        "is_a_type": "est un {type}",
        "rec_wordpress": "recommandé pour WordPress",
        "rec_use": "recommandé pour utilisation",
        "rec_play": "recommandé pour jouer",
        "rec_general": "recommandé pour une utilisation générale",
        "rec_production": "recommandé pour une utilisation en production",
        "rec_privacy": "recommandé pour une utilisation soucieuse de la vie privée",
        "data_sourced": "Données de {sources}. Dernière mise à jour: {date}.",
        "score_based_dims": "Score basé sur {dims}.",
        "yes_safe_short": "Oui, il est sûr à utiliser.",
        "title_safe": "{name} est-il sûr ? Analyse Indépendante de Confiance et Sécurité {year} | Nerq",
        "title_safe_visit": "{name} est-il sûr à visiter ? Score de Sécurité {year} et Guide de Voyage | Nerq",
        "title_charity": "{name} est-elle une association fiable ? Analyse de Confiance {year} | Nerq",
        "title_ingredient": "{name} est-il sûr ? Analyse Santé &amp; Sécurité {year} | Nerq",
        "h1_safe": "{name} est-il sûr ?",
        "h1_safe_visit": "{name} est-il sûr à visiter ?",
        "h1_trustworthy_charity": "{name} est-elle une association fiable ?",
        "h1_ingredient_safe": "{name} est-il sûr ?",
        "breadcrumb_safety": "Rapports de sécurité",
        "security_analysis": "Analyse de Sécurité", "privacy_report": "Rapport de Confidentialité", "similar_in_registry": "{registry} similaires par Score de Confiance", "see_all_best": "Voir tous les {registry} les plus sûrs",
        "pv_grade": "Note {grade}", "pv_body": "Sur la base de l'analyse de {dims} dimensions de confiance, il est {verdict}.", "pv_vulns": "avec {count} vulnérabilités connues", "pv_updated": "Dernière mise à jour : {date}.", "pv_safe": "considéré comme sûr", "pv_generally_safe": "généralement sûr mais avec quelques préoccupations", "pv_notable_concerns": "a des préoccupations de sécurité notables", "pv_significant_risks": "a des risques de sécurité importants", "pv_unsafe": "considéré comme dangereux",
        "h2q_trust_score": "Quel est le score de confiance de {name} ?", "h2q_key_findings": "Quels sont les résultats de sécurité clés pour {name} ?", "h2q_details": "Qu'est-ce que {name} et qui le maintient ?", "ans_trust": "{name} a un Score de Confiance Nerq de {score}/100, obtenant la note {grade}. Ce score est basé sur {dims} dimensions mesurées indépendamment.", "ans_findings_strong": "Le signal le plus fort de {name} est {signal} à {signal_score}/100.", "ans_no_vulns": "Aucune vulnérabilité connue n'a été détectée.", "ans_has_vulns": "{count} vulnérabilités connues ont été identifiées.", "ans_verified": "Atteint le seuil vérifié Nerq de 70+.", "ans_not_verified": "N'a pas encore atteint le seuil vérifié Nerq de 70+.",
        "trust_score_breakdown": "Détail du score de confiance",
        "safety_score_breakdown": "Détail du score de sécurité",
        "key_findings": "Résultats clés",
        "key_safety_findings": "Résultats clés de sécurité",
        "details": "Détails",
        "detailed_score_analysis": "Analyse détaillée du score",
        "faq": "Questions fréquentes",
        "community_reviews": "Avis de la communauté",
        "regulatory_compliance": "Conformité réglementaire",
        "how_calculated": "Comment nous avons calculé ce score",
        "popular_alternatives": "Alternatives populaires dans {category}",
        "safer_alternatives": "Alternatives plus sûres",
        "across_platforms": "{name} sur d'autres plateformes",
        "safety_guide": "Guide de sécurité : {name}",
        "what_is": "Qu'est-ce que {name} ?",
        "key_concerns": "Préoccupations de sécurité pour {type}",
        "how_to_verify": "Comment vérifier la sécurité",
        "trust_assessment": "Évaluation de confiance",
        "what_data_collect": "Quelles données {name} collecte-t-il ?",
        "is_secure": "{name} est-il sécurisé ?",
        "yes_safe": "Oui, {name} est sûr à utiliser.",
        "use_caution": "Utilisez {name} avec précaution.",
        "exercise_caution": "Faites preuve de prudence avec {name}.",
        "significant_concerns": "{name} présente des problèmes de confiance significatifs.",
        "safe": "Sûr",
        "use_caution_short": "Prudence",
        "avoid": "Éviter",
        "passes_threshold": "Atteint le seuil vérifié Nerq",
        "below_threshold": "En dessous du seuil vérifié Nerq",
        "significant_gaps": "Lacunes de confiance significatives détectées",
        "meets_threshold_detail": "Il atteint le seuil de confiance de Nerq avec de forts signaux en sécurité, maintenance et adoption communautaire",
        "score_based_on": "Ce score est basé sur une analyse automatisée des signaux de sécurité, maintenance, communauté et qualité.",
        "recommended_production": "Recommandé pour une utilisation en production",
        "last_analyzed": "Dernière analyse :",
        "author_label": "Auteur",
        "category_label": "Catégorie",
        "stars_label": "Étoiles",
        "source_label": "Source",
        "machine_readable": "Données lisibles par machine (JSON)",
        "full_analysis": "Analyse complète :",
        "privacy_report": "Rapport de confidentialité de {name}",
        "security_report": "Rapport de sécurité de {name}",
        "write_review": "Écrire un avis",
        "no_reviews": "Pas encore d'avis.",
        "be_first_review": "Soyez le premier à évaluer {name}",
        "security": "Sécurité",
        "compliance": "Conformité",
        "maintenance": "Maintenance",
        "documentation": "Documentation",
        "popularity": "Popularité",
        "overall_trust": "Confiance globale",
        "privacy": "Confidentialité",
        "reliability": "Fiabilité",
        "transparency": "Transparence",
        "disclaimer": "Les scores de confiance Nerq sont des évaluations automatisées basées sur des signaux publiquement disponibles. Ce ne sont pas des recommandations ou des garanties. Effectuez toujours votre propre vérification.",
        "same_developer": "Même développeur/entreprise dans d'autres registres :",
        "strongest_signal": "Signal le plus fort :",
        "in_category": "Dans la catégorie {category},",
        "check_back_soon": "revenez bientôt",
    },
    "ja": {
        "in_category": "{category}カテゴリでは、",
        "dim_popularity": "人気度",
        "faq_q3_alts": "{name}のより安全な代替は何ですか？",
        "faq_q4_log": "{name}は私のデータを記録しますか？",
        "faq_q4_update": "{name}の安全性スコアはどのくらいの頻度で更新されますか？",
        "faq_q5_vs": "{name}と代替製品：どちらが安全？",
        "faq_q5_regulated": "規制環境で{name}を使用できますか？",
        "faq_q4_vuln": "{name}に既知の脆弱性はありますか？",
        "faq_q4_kids": "{name}は子供に安全ですか？",
        "faq_q4_perms": "{name}にはどのような権限が必要ですか？",
        "faq_q4_maintained": "{name}は積極的にメンテナンスされていますか？",
        "faq_a4_vuln": "Nerqは{name}をNVD、OSV.dev、レジストリ固有の脆弱性データベースでチェックします。現在のセキュリティスコア：{sec_score}。",
        "faq_a4_kids": "{name}のNerqスコアは{score}/100です。保護者は完全なレポートを確認し、権限を確認してください。",
        "faq_a4_perms": "{name}の要求する権限を慎重に確認してください。信頼スコア：{score}/100。",
        "faq_a4_maintained": "{name}のメンテナンススコア：{maint_score}。リポジトリの最近の活動を確認してください。",
        "faq_a5_verified": "{name}はNerq認証閾値（70+）を満たしています。本番環境での使用に安全です。",
        "faq_a5_not_verified": "{name}はNerq認証閾値70に達していません。追加の確認が推奨されます。",
        "more_being_analyzed": "さらに多くの{type}が分析中です — 後で確認してください。",
        "strong": "強い",
        "moderate": "中程度",
        "weak": "弱い",
        "actively_maintained": "積極的にメンテナンス中",
        "moderately_maintained": "適度にメンテナンス中",
        "low_maintenance": "メンテナンス活動が低い",
        "well_documented": "十分に文書化",
        "partial_documentation": "部分的な文書化",
        "limited_documentation": "限定的な文書化",
        "community_adoption": "コミュニティ採用",
        "dim_maintenance": "メンテナンス",
        "dim_security": "セキュリティ",
        "vpn_no_breaches": "このサービスに関連する既知のデータ侵害はありません。",
        "vpn_audit_none": "{name}は独立したセキュリティ監査の結果を公開していません。監査済みVPNはより高い保証を提供します。",
        "vpn_audit_verified": "独立セキュリティ監査確認済み。",
        "vpn_audit_positive": "独立監査報告書によると、{name}はインフラストラクチャとノーログの主張を検証するサードパーティのセキュリティ監査を受けています。これは強力な正のシグナルです。",
        "vpn_proto": "主要暗号化プロトコル: {proto}。VPN接続の業界標準とされています。",
        "vpn_sec_score": "セキュリティスコア",
        "privacy_score_label": "プライバシースコア",
        "sidebar_most_private": "最もプライベートなアプリ",
        "sidebar_safest_vpns": "最も安全なVPN",
        "audit_no": "{name}は独立したプライバシー監査を公開していません",
        "audit_yes": "{name}はプライバシーの主張を検証するために独立した監査を受けています",
        "eyes_none": "Five/Nine/Fourteen Eyes同盟の非加盟国",
        "eyes_fourteen": "フォーティーンアイズ監視同盟内",
        "eyes_nine": "ナインアイズ監視同盟内",
        "eyes_five": "ファイブアイズ監視同盟内",
        "eyes_outside": "全てのEyes監視同盟の外 — プライバシー上の利点",
        "undisclosed_jurisdiction": "非公開の管轄地",
        "serving_users": "ユーザー数:",
        "privacy_assessment": "プライバシー評価",
        "sidebar_recently": "最近の分析",
        "sidebar_browse": "カテゴリを閲覧",
        "sidebar_popular_in": "人気の",
        "vpn_logging_audited": "ログポリシー：独立監査済みノーログポリシー。独立監査報告書によると、{name}は接続ログ、閲覧履歴、DNSクエリを保存しません。",
        "vpn_server_infra": "サーバーインフラ",
        "vpn_significant": "これは重要です。非同盟管轄区域のVPNプロバイダーはデータ保持法や情報共有協定の対象外であるためです。",
        "vpn_outside_eyes": "ファイブアイズ、ナインアイズ、フォーティーンアイズの監視同盟の外",
        "vpn_jurisdiction": "の管轄下にあります",
        "vpn_operates_under": "は",
        "xlink_av_desc": "AV-TESTスコアに基づく独立したアンチウイルスランキング",
        "xlink_safest_av": "最も安全なアンチウイルス",
        "xlink_hosting_desc": "独立したホスティングプロバイダー安全ランキング",
        "xlink_safest_hosting": "最も安全なウェブホスティング",
        "xlink_crypto_desc": "独立した暗号取引所安全ランキング",
        "xlink_safest_crypto": "最も安全な仮想通貨取引所",
        "xlink_access_secure_desc": "公共Wi-FiでSaaSツールにアクセスする際はVPNを使用",
        "xlink_access_secure": "安全にツールにアクセス",
        "xlink_secure_saas_desc": "SaaS認証情報にパスワードマネージャーを使用",
        "xlink_secure_saas": "SaaSログインを保護",
        "xlink_secure_creds_desc": "ホスティングとサーバーの認証情報にパスワードマネージャーを使用",
        "xlink_secure_creds": "認証情報を保護",
        "xlink_protect_server_desc": "安全なリモート管理のためにVPNを追加",
        "xlink_protect_server": "サーバーを保護",
        "xlink_secure_passwords_desc": "アカウントを保護するためにパスワードマネージャーを使用",
        "xlink_secure_passwords": "パスワードを保護",
        "xlink_add_vpn_av": "暗号化ブラウジングのためにVPNを追加",
        "xlink_add_malware_desc": "キーロガーや資格情報の窃取から保護",
        "xlink_add_malware": "マルウェア対策を追加",
        "xlink_add_av_vpn": "VPNと併せてアンチウイルスでセキュリティを完成",
        "xlink_add_av": "ウイルス対策を追加",
        "xlink_add_vpn_pm": "パスワードマネージャーにVPNを追加",
        "xlink_add_pm_vpn": "VPNにパスワードマネージャーを追加",
        "xlink_complete_security": "セキュリティを完成",
        "xlink_complete_privacy": "プライバシー設定を完成",
        "type_wordpress": "WordPressプラグイン",
        "type_crates": "Rustクレート",
        "type_pypi": "Pythonパッケージ",
        "type_steam": "Steamゲーム",
        "type_android": "Androidアプリ",
        "type_website_builder": "ウェブサイトビルダー",
        "type_crypto": "仮想通貨取引所",
        "type_password_manager": "パスワードマネージャー",
        "type_antivirus": "アンチウイルスソフト",
        "type_hosting": "ウェブホスティング",
        "type_saas": "SaaSプラットフォーム",
        "type_npm": "npmパッケージ",
        "type_vpn": "VPNサービス",
        "based_on_dims": "{dims}つの独立したデータ次元に基づく",
        "with_trust_score": "Nerq信頼スコア{score}/100（{grade}）",
        "is_a_type": "は{type}です",
        "rec_wordpress": "WordPressでの使用に推奨",
        "rec_use": "使用に推奨",
        "rec_play": "プレイに推奨",
        "rec_general": "一般的な使用に推奨",
        "rec_production": "本番環境での使用に推奨",
        "rec_privacy": "プライバシーを重視する使用に推奨",
        "title_safe": "{name}は安全ですか？ 独立した信頼性・セキュリティ分析 {year} | Nerq",
        "title_safe_visit": "{name}は訪問しても安全ですか？ {year} セキュリティスコア＆旅行ガイド | Nerq",
        "title_charity": "{name}は信頼できる慈善団体ですか？ {year} 信頼性分析 | Nerq",
        "title_ingredient": "{name}は安全ですか？ {year} 健康・安全性分析 | Nerq",
        "h1_safe": "{name}は安全ですか？",
        "h1_safe_visit": "{name}は訪問しても安全ですか？",
        "h1_trustworthy_charity": "{name}は信頼できる慈善団体ですか？",
        "h1_ingredient_safe": "{name}は安全ですか？",
        "breadcrumb_safety": "安全レポート",
        "security_analysis": "セキュリティ分析", "privacy_report": "プライバシーレポート", "similar_in_registry": "信頼スコア別の類似{registry}", "see_all_best": "最も安全な{registry}をすべて表示",
        "pv_grade": "{grade}グレード", "pv_body": "{dims}つの信頼次元の分析に基づき、{verdict}と評価されています。", "pv_vulns": "{count}件の既知の脆弱性があります", "pv_updated": "最終更新：{date}。", "pv_safe": "安全に使用できる", "pv_generally_safe": "概ね安全だがいくつかの懸念がある", "pv_notable_concerns": "顕著なセキュリティ上の懸念がある", "pv_significant_risks": "重大なセキュリティリスクがある", "pv_unsafe": "安全でないと見なされる",
        "h2q_trust_score": "{name}の信頼スコアは？", "h2q_key_findings": "{name}の主なセキュリティ調査結果は？", "h2q_details": "{name}とは何で、誰が管理していますか？", "ans_trust": "{name}のNerq信頼スコアは{score}/100で、{grade}グレードです。このスコアはセキュリティ、メンテナンス、コミュニティ採用を含む{dims}の独立した次元に基づいています。", "ans_findings_strong": "{name}の最も強いシグナルは{signal}で{signal_score}/100です。", "ans_no_vulns": "既知の脆弱性は検出されていません。", "ans_has_vulns": "{count}件の既知の脆弱性が確認されました。", "ans_verified": "Nerq認証閾値70+を満たしています。", "ans_not_verified": "Nerq認証閾値70+にまだ達していません。",
        "trust_score_breakdown": "信頼スコアの内訳",
        "safety_score_breakdown": "安全スコアの内訳",
        "key_findings": "主な発見",
        "key_safety_findings": "主な安全性の発見",
        "details": "詳細",
        "detailed_score_analysis": "詳細なスコア分析",
        "faq": "よくある質問",
        "community_reviews": "コミュニティレビュー",
        "how_calculated": "このスコアの算出方法",
        "popular_alternatives": "{category}の人気の代替品",
        "safer_alternatives": "より安全な代替品",
        "across_platforms": "{name}の他プラットフォーム",
        "safety_guide": "セキュリティガイド: {name}",
        "what_is": "{name}とは？",
        "what_data_collect": "{name}はどのようなデータを収集しますか？",
        "is_secure": "{name}は安全ですか？",
        "yes_safe": "はい、{name}は安全に使用できます。",
        "use_caution": "{name}は注意して使用してください。",
        "exercise_caution": "{name}には注意が必要です。",
        "significant_concerns": "{name}には重大な信頼性の問題があります。",
        "safe": "安全",
        "use_caution_short": "注意",
        "avoid": "回避",
        "passes_threshold": "Nerq認証閾値を達成",
        "below_threshold": "Nerq認証閾値未満",
        "last_analyzed": "最終分析:",
        "author_label": "作者",
        "category_label": "カテゴリ",
        "security": "セキュリティ",
        "maintenance": "メンテナンス",
        "documentation": "ドキュメント",
        "popularity": "人気度",
        "overall_trust": "総合信頼度",
        "privacy": "プライバシー",
        "disclaimer": "Nerqの信頼スコアは、公開されている情報に基づく自動評価です。推奨や保証ではありません。必ずご自身でも確認してください。",
        "strongest_signal": "最も強いシグナル:",
        "check_back_soon": "近日中にご確認ください",
        "safe_solo": "{name}は一人旅に安全ですか？",
        "safe_women": "{name}は女性にとって安全ですか？",
        "safe_families": "{name}は家族連れに安全ですか？",
        "what_are_side_effects": "{name}の副作用は？",
        "what_are_safer_alts": "{name}のより安全な代替品は？",
    },
    "pt": {
        "faq_q3_alts": "Quais são alternativas mais seguras ao {name}?",
        "faq_q4_log": "O {name} registra meus dados?",
        "faq_q4_update": "Com que frequência o score de segurança do {name} é atualizado?",
        "faq_q5_vs": "{name} vs alternativas: qual é mais seguro?",
        "faq_q5_regulated": "Posso usar {name} em um ambiente regulado?",
        "privacy_assessment": "Avaliação de privacidade",
        "vpn_sec_score": "Pontuação de segurança",
        "privacy_score_label": "Pontuação de privacidade",
        "strong": "forte",
        "moderate": "moderado",
        "weak": "fraco",
        "actively_maintained": "mantido ativamente",
        "moderately_maintained": "moderadamente mantido",
        "low_maintenance": "baixa atividade de manutenção",
        "well_documented": "bem documentado",
        "partial_documentation": "documentação parcial",
        "limited_documentation": "documentação limitada",
        "community_adoption": "adoção comunitária",
        "faq_q4_vuln": "{name} tem vulnerabilidades conhecidas?",
        "faq_q4_kids": "{name} é seguro para crianças?",
        "faq_q4_perms": "Quais permissões {name} precisa?",
        "faq_q4_maintained": "{name} é mantido ativamente?",
        "faq_a4_vuln": "Nerq verifica {name} contra NVD, OSV.dev e bancos de dados de vulnerabilidades. Score de segurança atual: {sec_score}.",
        "faq_a4_kids": "{name} tem um score Nerq de {score}/100. Os pais devem revisar o relatório completo.",
        "faq_a4_perms": "Revise cuidadosamente as permissões solicitadas por {name}. Score de confiança: {score}/100.",
        "faq_a4_maintained": "Score de manutenção de {name}: {maint_score}. Verifique a atividade recente do repositório.",
        "faq_a5_verified": "{name} atinge o limiar de verificação Nerq (70+). Seguro para uso em produção.",
        "faq_a5_not_verified": "{name} não atingiu o limiar de verificação Nerq de 70. Diligência adicional recomendada.",
        "more_being_analyzed": "mais {type} estão sendo analisados — volte em breve.",
        "sidebar_recently": "Analisados recentemente",
        "sidebar_browse": "Navegar categorias",
        "sidebar_popular_in": "Popular em",
        "vpn_significant": "Isso é significativo porque provedores de VPN em jurisdições não aliadas não estão sujeitos a leis obrigatórias de retenção de dados ou acordos de compartilhamento de inteligência.",
        "vpn_outside_eyes": "fora das alianças de vigilância Five Eyes, Nine Eyes e Fourteen Eyes",
        "vpn_jurisdiction": "jurisdição",
        "vpn_operates_under": "opera sob",
        "xlink_add_av_vpn": "Complete sua segurança com antivírus junto ao VPN",
        "xlink_add_av": "Adicionar proteção antivírus",
        "xlink_add_pm_vpn": "Adicione um gerenciador de senhas ao seu VPN",
        "xlink_complete_security": "Complete sua segurança",
        "xlink_complete_privacy": "Complete sua privacidade",
        "based_on_dims": "com base em {dims} dimensões de dados independentes",
        "with_trust_score": "com um Nerq Trust Score de {score}/100 ({grade})",
        "is_a_type": "é um {type}",
        "rec_privacy": "recomendado para uso consciente de privacidade",
        "title_safe": "{name} é seguro? Análise Independente de Confiança e Segurança {year} | Nerq",
        "title_safe_visit": "{name} é seguro para visitar? Pontuação de Segurança {year} e Guia de Viagem | Nerq",
        "title_charity": "{name} é uma instituição de caridade confiável? Análise de Confiança {year} | Nerq",
        "title_ingredient": "{name} é seguro? Análise de Saúde e Segurança {year} | Nerq",
        "h1_safe": "{name} é seguro?",
        "h1_safe_visit": "{name} é seguro para visitar?",
        "h1_trustworthy_charity": "{name} é uma instituição de caridade confiável?",
        "h1_ingredient_safe": "{name} é seguro?",
        "breadcrumb_safety": "Relatórios de Segurança",
        "security_analysis": "Análise de Segurança", "privacy_report": "Relatório de Privacidade", "similar_in_registry": "{registry} semelhantes por Pontuação de Confiança", "see_all_best": "Ver todos os {registry} mais seguros",
        "pv_grade": "Grau {grade}", "pv_body": "Com base na análise de {dims} dimensões de confiança, é {verdict}.", "pv_vulns": "com {count} vulnerabilidades conhecidas", "pv_updated": "Última atualização: {date}.", "pv_safe": "considerado seguro para uso", "pv_generally_safe": "geralmente seguro, mas com algumas preocupações", "pv_notable_concerns": "tem preocupações de segurança notáveis", "pv_significant_risks": "tem riscos de segurança significativos", "pv_unsafe": "considerado inseguro",
        "h2q_trust_score": "Qual é a pontuação de confiança de {name}?", "h2q_key_findings": "Quais são as principais descobertas de segurança de {name}?", "h2q_details": "O que é {name} e quem o mantém?", "ans_trust": "{name} tem uma Pontuação de Confiança Nerq de {score}/100, obtendo grau {grade}. Esta pontuação é baseada em {dims} dimensões medidas independentemente.", "ans_findings_strong": "O sinal mais forte de {name} é {signal} com {signal_score}/100.", "ans_no_vulns": "Nenhuma vulnerabilidade conhecida foi detectada.", "ans_has_vulns": "{count} vulnerabilidades conhecidas foram identificadas.", "ans_verified": "Atende ao limiar verificado Nerq de 70+.", "ans_not_verified": "Ainda não atingiu o limiar verificado Nerq de 70+.",
        "trust_score_breakdown": "Detalhamento da Pontuação de Confiança",
        "safety_score_breakdown": "Detalhamento da Pontuação de Segurança",
        "key_findings": "Principais Descobertas",
        "key_safety_findings": "Principais Descobertas de Segurança",
        "details": "Detalhes",
        "detailed_score_analysis": "Análise Detalhada da Pontuação",
        "faq": "Perguntas Frequentes",
        "community_reviews": "Avaliações da Comunidade",
        "how_calculated": "Como calculamos esta pontuação",
        "popular_alternatives": "Alternativas Populares em {category}",
        "safer_alternatives": "Alternativas Mais Seguras",
        "across_platforms": "{name} em outras plataformas",
        "safety_guide": "Guia de Segurança: {name}",
        "what_is": "O que é {name}?",
        "what_data_collect": "Quais dados {name} coleta?",
        "is_secure": "{name} é seguro?",
        "yes_safe": "Sim, {name} é seguro para usar.",
        "use_caution": "Use {name} com cautela.",
        "exercise_caution": "Tenha cautela com {name}.",
        "significant_concerns": "{name} tem preocupações significativas de confiança.",
        "safe": "Seguro",
        "use_caution_short": "Cautela",
        "avoid": "Evitar",
        "passes_threshold": "Atinge o limiar verificado Nerq",
        "below_threshold": "Abaixo do limiar verificado Nerq",
        "last_analyzed": "Última análise:",
        "author_label": "Autor",
        "category_label": "Categoria",
        "security": "Segurança",
        "maintenance": "Manutenção",
        "documentation": "Documentação",
        "popularity": "Popularidade",
        "overall_trust": "Confiança Geral",
        "privacy": "Privacidade",
        "disclaimer": "As pontuações de confiança da Nerq são avaliações automatizadas baseadas em sinais publicamente disponíveis. Não são endossos ou garantias. Sempre realize sua própria verificação.",
        "same_developer": "Mesmo desenvolvedor/empresa em outros registros:",
        "strongest_signal": "Sinal mais forte:",
        "check_back_soon": "volte em breve",
        "safe_solo": "{name} é seguro para viajantes solo?",
        "safe_women": "{name} é seguro para mulheres?",
        "safe_families": "{name} é seguro para famílias?",
        "safe_visit_now": "{name} é seguro para visitar agora?",
        "what_are_side_effects": "Quais são os efeitos colaterais de {name}?",
        "what_are_safer_alts": "Quais são alternativas mais seguras a {name}?",
    },
    "id": {
        "vpn_outside_eyes": "di luar aliansi pengawasan Five Eyes, Nine Eyes, dan Fourteen Eyes",
        "faq_q3_alts": "Apa alternatif yang lebih aman dari {name}?",
        "faq_q4_log": "Apakah {name} mencatat data saya?",
        "faq_q4_update": "Seberapa sering skor keamanan {name} diperbarui?",
        "faq_q5_vs": "{name} vs alternatif: mana yang lebih aman?",
        "faq_q5_regulated": "Bisakah saya menggunakan {name} di lingkungan yang diatur?",
        "vpn_sec_score": "Skor keamanan",
        "privacy_score_label": "Skor privasi",
        "strong": "kuat",
        "moderate": "sedang",
        "weak": "lemah",
        "actively_maintained": "dipelihara aktif",
        "moderately_maintained": "dipelihara sedang",
        "low_maintenance": "aktivitas pemeliharaan rendah",
        "well_documented": "terdokumentasi baik",
        "partial_documentation": "dokumentasi sebagian",
        "limited_documentation": "dokumentasi terbatas",
        "community_adoption": "adopsi komunitas",
        "faq_q4_vuln": "Apakah {name} memiliki kerentanan yang diketahui?",
        "faq_q4_kids": "Apakah {name} aman untuk anak-anak?",
        "faq_q4_perms": "Izin apa yang dibutuhkan {name}?",
        "faq_q4_maintained": "Apakah {name} dipelihara secara aktif?",
        "faq_a4_vuln": "Nerq memeriksa {name} terhadap NVD, OSV.dev, dan database kerentanan. Skor keamanan saat ini: {sec_score}.",
        "faq_a4_kids": "{name} memiliki skor Nerq {score}/100. Orang tua harus meninjau laporan lengkap.",
        "faq_a4_perms": "Tinjau izin yang diminta {name} dengan cermat. Skor kepercayaan: {score}/100.",
        "faq_a4_maintained": "Skor pemeliharaan {name}: {maint_score}. Periksa aktivitas terbaru repositori.",
        "faq_a5_verified": "{name} memenuhi ambang verifikasi Nerq (70+). Aman untuk penggunaan produksi.",
        "faq_a5_not_verified": "{name} belum mencapai ambang verifikasi Nerq 70. Tinjauan tambahan disarankan.",
        "more_being_analyzed": "lebih banyak {type} sedang dianalisis — periksa kembali segera.",
        "vpn_jurisdiction": "yurisdiksi",
        "vpn_operates_under": "beroperasi di bawah",
        "xlink_add_av_vpn": "Lengkapi keamanan dengan antivirus bersama VPN",
        "xlink_add_av": "Tambahkan perlindungan antivirus",
        "xlink_add_pm_vpn": "Tambahkan pengelola kata sandi ke VPN Anda",
        "xlink_complete_security": "Lengkapi keamanan Anda",
        "xlink_complete_privacy": "Lengkapi privasi Anda",
        "is_a_type": "adalah {type}",
        "rec_privacy": "direkomendasikan untuk penggunaan yang memperhatikan privasi",
        "title_safe": "Apakah {name} Aman? Analisis Kepercayaan &amp; Keamanan Independen {year} | Nerq",
        "title_safe_visit": "Apakah {name} Aman Dikunjungi? Skor Keamanan {year} &amp; Panduan Perjalanan | Nerq",
        "title_charity": "Apakah {name} Lembaga Amal Terpercaya? Analisis Kepercayaan {year} | Nerq",
        "title_ingredient": "Apakah {name} Aman? Analisis Kesehatan &amp; Keamanan {year} | Nerq",
        "h1_safe": "Apakah {name} Aman?",
        "h1_safe_visit": "Apakah {name} Aman Dikunjungi?",
        "h1_trustworthy_charity": "Apakah {name} Lembaga Amal Terpercaya?",
        "h1_ingredient_safe": "Apakah {name} Aman?",
        "breadcrumb_safety": "Laporan Keamanan",
        "security_analysis": "Analisis Keamanan", "privacy_report": "Laporan Privasi", "similar_in_registry": "{registry} serupa berdasarkan Skor Kepercayaan", "see_all_best": "Lihat semua {registry} teraman",
        "pv_grade": "Nilai {grade}", "pv_body": "Berdasarkan analisis {dims} dimensi kepercayaan, dianggap {verdict}.", "pv_vulns": "dengan {count} kerentanan yang diketahui", "pv_updated": "Terakhir diperbarui: {date}.", "pv_safe": "aman untuk digunakan", "pv_generally_safe": "umumnya aman tetapi memiliki beberapa kekhawatiran", "pv_notable_concerns": "memiliki masalah keamanan yang perlu diperhatikan", "pv_significant_risks": "memiliki risiko keamanan yang signifikan", "pv_unsafe": "dianggap tidak aman",
        "h2q_trust_score": "Berapa skor kepercayaan {name}?", "h2q_key_findings": "Apa temuan keamanan utama untuk {name}?", "h2q_details": "Apa itu {name} dan siapa yang mengelolanya?", "ans_trust": "{name} memiliki Skor Kepercayaan Nerq {score}/100 dengan nilai {grade}. Skor ini didasarkan pada {dims} dimensi yang diukur secara independen.", "ans_findings_strong": "Sinyal terkuat {name} adalah {signal} pada {signal_score}/100.", "ans_no_vulns": "Tidak ada kerentanan yang diketahui terdeteksi.", "ans_has_vulns": "{count} kerentanan yang diketahui telah diidentifikasi.", "ans_verified": "Memenuhi ambang verifikasi Nerq 70+.", "ans_not_verified": "Belum mencapai ambang verifikasi Nerq 70+.",
        "trust_score_breakdown": "Rincian Skor Kepercayaan",
        "safety_score_breakdown": "Rincian Skor Keamanan",
        "key_findings": "Temuan Utama",
        "key_safety_findings": "Temuan Keamanan Utama",
        "details": "Detail",
        "detailed_score_analysis": "Analisis Skor Terperinci",
        "faq": "Pertanyaan yang Sering Diajukan",
        "community_reviews": "Ulasan Komunitas",
        "regulatory_compliance": "Kepatuhan Regulasi",
        "how_calculated": "Cara kami menghitung skor ini",
        "popular_alternatives": "Alternatif Populer di {category}",
        "safer_alternatives": "Alternatif Lebih Aman",
        "across_platforms": "{name} di Platform Lain",
        "safety_guide": "Panduan Keamanan: {name}",
        "what_is": "Apa itu {name}?",
        "key_concerns": "Masalah Keamanan Utama untuk {type}",
        "how_to_verify": "Cara Memverifikasi Keamanan",
        "trust_assessment": "Penilaian Kepercayaan",
        "what_data_collect": "Data apa yang dikumpulkan {name}?",
        "is_secure": "Apakah {name} aman?",
        "is_safe_visit": "Apakah {name} aman untuk dikunjungi?",
        "is_legit_charity": "Apakah {name} lembaga amal yang sah?",
        "crime_safety": "Kejahatan dan keamanan di {name}",
        "financial_transparency": "Transparansi keuangan {name}",
        "yes_safe": "Ya, {name} aman digunakan.",
        "use_caution": "Gunakan {name} dengan hati-hati.",
        "exercise_caution": "Berhati-hatilah dengan {name}.",
        "significant_concerns": "{name} memiliki masalah kepercayaan yang signifikan.",
        "safe": "Aman",
        "use_caution_short": "Hati-hati",
        "avoid": "Hindari",
        "passes_threshold": "Memenuhi ambang batas terverifikasi Nerq",
        "below_threshold": "Di bawah ambang batas terverifikasi Nerq",
        "significant_gaps": "Celah kepercayaan signifikan terdeteksi",
        "meets_threshold_detail": "Memenuhi ambang batas kepercayaan Nerq dengan sinyal kuat di keamanan, pemeliharaan, dan adopsi komunitas",
        "not_reached_threshold": "dan belum mencapai ambang batas kepercayaan Nerq (70+).",
        "score_based_on": "Skor ini berdasarkan analisis otomatis sinyal keamanan, pemeliharaan, komunitas, dan kualitas.",
        "recommended_production": "Direkomendasikan untuk penggunaan produksi",
        "last_analyzed": "Terakhir dianalisis:",
        "author_label": "Pembuat",
        "category_label": "Kategori",
        "stars_label": "Bintang",
        "global_rank_label": "Peringkat Global",
        "source_label": "Sumber",
        "machine_readable": "Data yang dapat dibaca mesin (JSON)",
        "full_analysis": "Analisis lengkap:",
        "privacy_report": "Laporan Privasi {name}",
        "security_report": "Laporan Keamanan {name}",
        "write_review": "Tulis ulasan",
        "no_reviews": "Belum ada ulasan.",
        "be_first_review": "Jadilah yang pertama mengulas {name}",
        "security": "Keamanan",
        "compliance": "Kepatuhan",
        "maintenance": "Pemeliharaan",
        "documentation": "Dokumentasi",
        "popularity": "Popularitas",
        "overall_trust": "Kepercayaan Keseluruhan",
        "privacy": "Privasi",
        "reliability": "Keandalan",
        "transparency": "Transparansi",
        "disclaimer": "Skor kepercayaan Nerq adalah penilaian otomatis berdasarkan sinyal yang tersedia secara publik. Ini bukan rekomendasi atau jaminan. Selalu lakukan verifikasi mandiri Anda sendiri.",
        "same_developer": "Developer/perusahaan yang sama di registry lain:",
        "methodology_entities": "Nerq menganalisis lebih dari 7,5 juta entitas di 26 registry menggunakan metodologi yang sama, memungkinkan perbandingan langsung antar entitas.",
        "scores_updated_continuously": "Skor diperbarui secara berkelanjutan saat data baru tersedia.",
        "strongest_signal": "Sinyal terkuat:",
        "in_category": "Dalam kategori {category},",
        "check_back_soon": "kunjungi kembali segera",
        "safe_solo": "Apakah {name} aman untuk wisatawan solo?",
        "safe_women": "Apakah {name} aman untuk wanita?",
        "safe_lgbtq": "Apakah {name} aman untuk wisatawan LGBTQ+?",
        "safe_families": "Apakah {name} aman untuk keluarga?",
        "safe_visit_now": "Apakah {name} aman dikunjungi saat ini?",
        "tap_water_safe": "Apakah air keran aman diminum di {name}?",
        "need_vaccinations": "Apakah saya perlu vaksinasi untuk {name}?",
        "what_are_side_effects": "Apa efek samping {name}?",
        "what_are_safer_alts": "Apa alternatif yang lebih aman dari {name}?",
        "interact_medications": "Apakah {name} berinteraksi dengan obat-obatan?",
        "cause_irritation": "Apakah {name} dapat menyebabkan iritasi kulit?",
        "health_disclaimer": "Informasi ini hanya untuk tujuan edukasi dan bukan merupakan saran medis. Konsultasikan dengan tenaga kesehatan profesional sebelum membuat keputusan kesehatan.",
        "not_analyzed_title": "{name} — Belum Dianalisis | Nerq",
        "not_analyzed_h1": "{name} — Belum Dianalisis",
        "not_analyzed_msg": "Nerq belum melakukan analisis kepercayaan terhadap {name}. Kami menganalisis lebih dari 7,5 juta entitas — entitas ini mungkin akan ditambahkan segera.",
        "not_analyzed_meanwhile": "Sementara itu, Anda dapat:",
        "not_analyzed_search": "Coba cari dengan ejaan yang berbeda",
        "not_analyzed_api": "Cek API secara langsung",
        "not_analyzed_browse": "Jelajahi entitas yang sudah kami analisis",
        "not_analyzed_no_score": "Halaman ini tidak memiliki skor kepercayaan karena kami belum menganalisis entitas ini.",
        "not_analyzed_no_fabricate": "Nerq tidak pernah memalsukan penilaian. Jika Anda yakin entitas ini perlu dianalisis, entitas ini mungkin akan muncul di pembaruan mendatang.",
    },
    "cs": {
        "vpn_outside_eyes": "mimo aliance dohledu Five Eyes, Nine Eyes a Fourteen Eyes",
        "faq_q3_alts": "Jaké jsou bezpečnější alternativy k {name}?",
        "faq_q4_log": "Zaznamenává {name} moje data?",
        "faq_q4_update": "Jak často se aktualizuje bezpečnostní skóre {name}?",
        "faq_q5_vs": "{name} vs alternativy: co je bezpečnější?",
        "faq_q5_regulated": "Mohu používat {name} v regulovaném prostředí?",
        "vpn_sec_score": "Bezpečnostní skóre",
        "privacy_score_label": "Skóre soukromí",
        "strong": "silný",
        "moderate": "střední",
        "weak": "slabý",
        "actively_maintained": "aktivně udržováno",
        "moderately_maintained": "středně udržováno",
        "low_maintenance": "nízká údržba",
        "well_documented": "dobře dokumentováno",
        "partial_documentation": "částečná dokumentace",
        "limited_documentation": "omezená dokumentace",
        "community_adoption": "přijetí komunitou",
        "faq_q4_vuln": "Má {name} známé zranitelnosti?",
        "faq_q4_kids": "Je {name} bezpečný pro děti?",
        "faq_q4_perms": "Jaká oprávnění {name} potřebuje?",
        "faq_q4_maintained": "Je {name} aktivně udržován?",
        "faq_a4_vuln": "Nerq kontroluje {name} proti NVD, OSV.dev a databázím zranitelností. Aktuální bezpečnostní skóre: {sec_score}.",
        "faq_a4_kids": "{name} má skóre Nerq {score}/100. Rodiče by měli zkontrolovat úplnou zprávu.",
        "faq_a4_perms": "Pečlivě zkontrolujte oprávnění požadovaná {name}. Skóre důvěry: {score}/100.",
        "faq_a4_maintained": "Skóre údržby {name}: {maint_score}. Zkontrolujte nedávnou aktivitu repozitáře.",
        "faq_a5_verified": "{name} splňuje práh ověření Nerq (70+). Bezpečné pro produkční použití.",
        "faq_a5_not_verified": "{name} nedosáhl prahu ověření Nerq 70. Doporučuje se dodatečné přezkoumání.",
        "more_being_analyzed": "další {type} se analyzují — zkontrolujte později.",
        "vpn_jurisdiction": "jurisdikce",
        "vpn_operates_under": "působí pod",
        "xlink_add_av_vpn": "Doplňte zabezpečení antivirem k VPN",
        "xlink_add_av": "Přidat antivirovou ochranu",
        "xlink_add_pm_vpn": "Přidejte správce hesel k vašemu VPN",
        "xlink_complete_security": "Dokončete zabezpečení",
        "xlink_complete_privacy": "Dokončete ochranu soukromí",
        "is_a_type": "je {type}",
        "rec_privacy": "doporučeno pro použití s důrazem na soukromí",
        "title_safe": "Je {name} bezpečný? Nezávislá analýza důvěryhodnosti a bezpečnosti {year} | Nerq",
        "title_safe_visit": "Je {name} bezpečné navštívit? Bezpečnostní skóre {year} &amp; Cestovní průvodce | Nerq",
        "title_charity": "Je {name} důvěryhodná charita? Analýza důvěryhodnosti {year} | Nerq",
        "title_ingredient": "Je {name} bezpečný? Analýza zdraví &amp; bezpečnosti {year} | Nerq",
        "h1_safe": "Je {name} bezpečný?",
        "h1_safe_visit": "Je {name} bezpečné navštívit?",
        "h1_trustworthy_charity": "Je {name} důvěryhodná charita?",
        "h1_ingredient_safe": "Je {name} bezpečný?",
        "breadcrumb_safety": "Bezpečnostní zprávy",
        "security_analysis": "Bezpečnostní analýza", "privacy_report": "Zpráva o soukromí", "similar_in_registry": "Podobné {registry} podle skóre důvěryhodnosti", "see_all_best": "Zobrazit všechny nejbezpečnější {registry}",
        "pv_grade": "Stupeň {grade}", "pv_body": "Na základě analýzy {dims} dimenzí důvěryhodnosti je {verdict}.", "pv_vulns": "s {count} známými zranitelnostmi", "pv_updated": "Naposledy aktualizováno: {date}.", "pv_safe": "považován za bezpečný", "pv_generally_safe": "obecně bezpečný, ale s některými obavami", "pv_notable_concerns": "má pozoruhodné bezpečnostní obavy", "pv_significant_risks": "má významná bezpečnostní rizika", "pv_unsafe": "považován za nebezpečný",
        "h2q_trust_score": "Jaké je skóre důvěryhodnosti {name}?", "h2q_key_findings": "Jaká jsou klíčová bezpečnostní zjištění pro {name}?", "h2q_details": "Co je {name} a kdo jej spravuje?", "ans_trust": "{name} má Nerq skóre důvěryhodnosti {score}/100 se stupněm {grade}. Toto skóre je založeno na {dims} nezávisle měřených dimenzích.", "ans_findings_strong": "Nejsilnější signál {name} je {signal} na {signal_score}/100.", "ans_no_vulns": "Nebyly zjištěny žádné známé zranitelnosti.", "ans_has_vulns": "Bylo identifikováno {count} známých zranitelností.", "ans_verified": "Splňuje ověřený práh Nerq 70+.", "ans_not_verified": "Dosud nedosáhl ověřeného prahu Nerq 70+.",
        "trust_score_breakdown": "Rozpis skóre důvěryhodnosti",
        "safety_score_breakdown": "Rozpis bezpečnostního skóre",
        "key_findings": "Hlavní zjištění",
        "key_safety_findings": "Hlavní bezpečnostní zjištění",
        "details": "Podrobnosti",
        "detailed_score_analysis": "Podrobná analýza skóre",
        "faq": "Často kladené otázky",
        "community_reviews": "Komunitní hodnocení",
        "regulatory_compliance": "Regulační shoda",
        "how_calculated": "Jak jsme vypočítali toto skóre",
        "popular_alternatives": "Populární alternativy v {category}",
        "safer_alternatives": "Bezpečnější alternativy",
        "across_platforms": "{name} na dalších platformách",
        "safety_guide": "Bezpečnostní průvodce: {name}",
        "what_is": "Co je {name}?",
        "key_concerns": "Hlavní bezpečnostní problémy pro {type}",
        "how_to_verify": "Jak ověřit bezpečnost",
        "trust_assessment": "Hodnocení důvěryhodnosti",
        "what_data_collect": "Jaká data {name} shromažďuje?",
        "is_secure": "Je {name} bezpečný?",
        "is_safe_visit": "Je {name} bezpečné navštívit?",
        "is_legit_charity": "Je {name} legitimní charita?",
        "crime_safety": "Kriminalita a bezpečnost v {name}",
        "financial_transparency": "Finanční transparentnost {name}",
        "yes_safe": "Ano, {name} je bezpečný k použití.",
        "use_caution": "Používejte {name} s opatrností.",
        "exercise_caution": "Buďte opatrní s {name}.",
        "significant_concerns": "{name} má významné problémy s důvěryhodností.",
        "safe": "Bezpečný",
        "use_caution_short": "Opatrnost",
        "avoid": "Vyhnout se",
        "passes_threshold": "Splňuje ověřený práh Nerq",
        "below_threshold": "Pod ověřeným prahem Nerq",
        "significant_gaps": "Zjištěny významné mezery v důvěryhodnosti",
        "meets_threshold_detail": "Splňuje práh důvěryhodnosti Nerq se silnými signály v oblasti bezpečnosti, údržby a přijetí komunitou",
        "not_reached_threshold": "a dosud nedosáhl prahu důvěryhodnosti Nerq (70+).",
        "score_based_on": "Toto skóre je založeno na automatizované analýze signálů bezpečnosti, údržby, komunity a kvality.",
        "recommended_production": "Doporučeno pro produkční použití",
        "last_analyzed": "Naposledy analyzováno:",
        "author_label": "Autor",
        "category_label": "Kategorie",
        "stars_label": "Hvězdičky",
        "global_rank_label": "Globální hodnocení",
        "source_label": "Zdroj",
        "machine_readable": "Strojově čitelná data (JSON)",
        "full_analysis": "Úplná analýza:",
        "privacy_report": "Zpráva o soukromí {name}",
        "security_report": "Bezpečnostní zpráva {name}",
        "write_review": "Napsat recenzi",
        "no_reviews": "Zatím žádné recenze.",
        "be_first_review": "Buďte první, kdo ohodnotí {name}",
        "security": "Bezpečnost",
        "compliance": "Shoda",
        "maintenance": "Údržba",
        "documentation": "Dokumentace",
        "popularity": "Popularita",
        "overall_trust": "Celková důvěryhodnost",
        "privacy": "Soukromí",
        "reliability": "Spolehlivost",
        "transparency": "Transparentnost",
        "disclaimer": "Skóre důvěryhodnosti Nerq jsou automatizovaná hodnocení založená na veřejně dostupných signálech. Nejsou doporučením ani zárukou. Vždy proveďte vlastní ověření.",
        "same_developer": "Stejný vývojář/společnost v jiných registrech:",
        "methodology_entities": "Nerq analyzuje více než 7,5 milionu entit ve 26 registrech pomocí stejné metodologie, což umožňuje přímé srovnání mezi entitami.",
        "scores_updated_continuously": "Skóre jsou průběžně aktualizována, jakmile jsou k dispozici nová data.",
        "strongest_signal": "Nejsilnější signál:",
        "in_category": "V kategorii {category},",
        "check_back_soon": "zkuste to znovu brzy",
        "safe_solo": "Je {name} bezpečné pro sólo cestovatele?",
        "safe_women": "Je {name} bezpečné pro ženy?",
        "safe_lgbtq": "Je {name} bezpečné pro LGBTQ+ cestovatele?",
        "safe_families": "Je {name} bezpečné pro rodiny?",
        "safe_visit_now": "Je {name} bezpečné navštívit právě teď?",
        "tap_water_safe": "Je voda z kohoutku v {name} bezpečná k pití?",
        "need_vaccinations": "Potřebuji očkování pro {name}?",
        "what_are_side_effects": "Jaké jsou vedlejší účinky {name}?",
        "what_are_safer_alts": "Jaké jsou bezpečnější alternativy k {name}?",
        "interact_medications": "Interaguje {name} s léky?",
        "cause_irritation": "Může {name} způsobit podráždění kůže?",
        "health_disclaimer": "Tyto informace slouží pouze pro vzdělávací účely a nepředstavují lékařskou radu. Před rozhodnutím o zdraví se poraďte s kvalifikovaným zdravotnickým pracovníkem.",
        "not_analyzed_title": "{name} — Zatím neanalyzováno | Nerq",
        "not_analyzed_h1": "{name} — Zatím neanalyzováno",
        "not_analyzed_msg": "Nerq dosud neprovedl analýzu důvěryhodnosti {name}. Analyzujeme více než 7,5 milionu entit — tato může být brzy přidána.",
        "not_analyzed_meanwhile": "Mezitím můžete:",
        "not_analyzed_search": "Zkusit hledat s jiným pravopisem",
        "not_analyzed_api": "Zkontrolovat API přímo",
        "not_analyzed_browse": "Procházet entity, které jsme již analyzovali",
        "not_analyzed_no_score": "Tato stránka neobsahuje skóre důvěryhodnosti, protože jsme tuto entitu dosud neanalyzovali.",
        "not_analyzed_no_fabricate": "Nerq nikdy nevymýšlí hodnocení. Pokud se domníváte, že by tato entita měla být pokryta, může se objevit v budoucí aktualizaci.",
    },
    "th": {
        "vpn_outside_eyes": "อยู่นอกพันธมิตรเฝ้าระวัง Five Eyes, Nine Eyes และ Fourteen Eyes",
        "faq_q3_alts": "ทางเลือกที่ปลอดภัยกว่า {name} คืออะไร?",
        "faq_q4_log": "{name} บันทึกข้อมูลของฉันหรือไม่?",
        "faq_q4_update": "คะแนนความปลอดภัยของ {name} อัปเดตบ่อยแค่ไหน?",
        "faq_q5_vs": "{name} กับทางเลือกอื่น: อันไหนปลอดภัยกว่า?",
        "faq_q5_regulated": "ฉันสามารถใช้ {name} ในสภาพแวดล้อมที่มีกฎระเบียบได้หรือไม่?",
        "vpn_sec_score": "คะแนนความปลอดภัย",
        "privacy_score_label": "คะแนนความเป็นส่วนตัว",
        "strong": "แข็งแกร่ง",
        "moderate": "ปานกลาง",
        "weak": "อ่อน",
        "actively_maintained": "ดูแลอย่างต่อเนื่อง",
        "moderately_maintained": "ดูแลปานกลาง",
        "low_maintenance": "กิจกรรมดูแลต่ำ",
        "well_documented": "มีเอกสารดี",
        "partial_documentation": "เอกสารบางส่วน",
        "limited_documentation": "เอกสารจำกัด",
        "community_adoption": "การยอมรับจากชุมชน",
        "faq_q4_vuln": "{name} มีช่องโหว่ที่ทราบหรือไม่?",
        "faq_q4_kids": "{name} ปลอดภัยสำหรับเด็กหรือไม่?",
        "faq_q4_perms": "{name} ต้องการสิทธิ์อะไรบ้าง?",
        "faq_q4_maintained": "{name} ได้รับการดูแลอย่างต่อเนื่องหรือไม่?",
        "faq_a4_vuln": "Nerq ตรวจสอบ {name} กับ NVD, OSV.dev และฐานข้อมูลช่องโหว่ คะแนนความปลอดภัยปัจจุบัน: {sec_score}",
        "faq_a4_kids": "{name} มีคะแนน Nerq {score}/100 ผู้ปกครองควรตรวจสอบรายงานฉบับเต็ม",
        "faq_a4_perms": "ตรวจสอบสิทธิ์ที่ร้องขอโดย {name} อย่างรอบคอบ คะแนนความน่าเชื่อถือ: {score}/100",
        "faq_a4_maintained": "คะแนนการดูแลรักษา {name}: {maint_score} ตรวจสอบกิจกรรมล่าสุดของ repository",
        "faq_a5_verified": "{name} ผ่านเกณฑ์การยืนยัน Nerq (70+) ปลอดภัยสำหรับการใช้งาน",
        "faq_a5_not_verified": "{name} ยังไม่ถึงเกณฑ์การยืนยัน Nerq 70 แนะนำให้ตรวจสอบเพิ่มเติม",
        "more_being_analyzed": "{type} เพิ่มเติมกำลังถูกวิเคราะห์ — กลับมาเร็วๆ นี้",
        "vpn_jurisdiction": "เขตอำนาจศาล",
        "vpn_operates_under": "ดำเนินงานภายใต้",
        "xlink_add_av_vpn": "เสริมความปลอดภัยด้วยแอนตี้ไวรัสร่วมกับ VPN",
        "xlink_add_av": "เพิ่มการป้องกันไวรัส",
        "xlink_add_pm_vpn": "เพิ่มตัวจัดการรหัสผ่านให้ VPN",
        "xlink_complete_security": "เสริมความปลอดภัย",
        "xlink_complete_privacy": "ตั้งค่าความเป็นส่วนตัว",
        "is_a_type": "เป็น {type}",
        "rec_privacy": "แนะนำสำหรับการใช้งานที่คำนึงถึงความเป็นส่วนตัว",
        "title_safe": "{name} ปลอดภัยหรือไม่? การวิเคราะห์ความน่าเชื่อถือและความปลอดภัยอิสระ {year} | Nerq",
        "title_safe_visit": "{name} ปลอดภัยที่จะเยี่ยมชมหรือไม่? คะแนนความปลอดภัย {year} &amp; คู่มือการเดินทาง | Nerq",
        "title_charity": "{name} เป็นองค์กรการกุศลที่น่าเชื่อถือหรือไม่? การวิเคราะห์ความน่าเชื่อถือ {year} | Nerq",
        "title_ingredient": "{name} ปลอดภัยหรือไม่? การวิเคราะห์สุขภาพ &amp; ความปลอดภัย {year} | Nerq",
        "h1_safe": "{name} ปลอดภัยหรือไม่?",
        "h1_safe_visit": "{name} ปลอดภัยที่จะเยี่ยมชมหรือไม่?",
        "h1_trustworthy_charity": "{name} เป็นองค์กรการกุศลที่น่าเชื่อถือหรือไม่?",
        "h1_ingredient_safe": "{name} ปลอดภัยหรือไม่?",
        "breadcrumb_safety": "รายงานความปลอดภัย",
        "security_analysis": "การวิเคราะห์ความปลอดภัย", "privacy_report": "รายงานความเป็นส่วนตัว", "similar_in_registry": "{registry} ที่คล้ายกันตามคะแนนความน่าเชื่อถือ", "see_all_best": "ดูทั้งหมดที่ปลอดภัยที่สุด {registry}",
        "pv_grade": "เกรด {grade}", "pv_body": "จากการวิเคราะห์ {dims} มิติความน่าเชื่อถือ ถือว่า{verdict}", "pv_vulns": "มี {count} ช่องโหว่ที่ทราบ", "pv_updated": "อัปเดตล่าสุด: {date}", "pv_safe": "ปลอดภัยในการใช้งาน", "pv_generally_safe": "โดยทั่วไปปลอดภัยแต่มีข้อกังวลบางประการ", "pv_notable_concerns": "มีข้อกังวลด้านความปลอดภัยที่สำคัญ", "pv_significant_risks": "มีความเสี่ยงด้านความปลอดภัยที่สำคัญ", "pv_unsafe": "ถือว่าไม่ปลอดภัย",
        "h2q_trust_score": "คะแนนความน่าเชื่อถือของ {name} คือเท่าไร?", "h2q_key_findings": "ผลการตรวจสอบความปลอดภัยหลักของ {name} คืออะไร?", "h2q_details": "{name} คืออะไรและใครเป็นผู้ดูแล?", "ans_trust": "{name} มีคะแนนความน่าเชื่อถือ Nerq {score}/100 ได้เกรด {grade} คะแนนนี้อิงจาก {dims} มิติที่วัดอย่างอิสระ", "ans_findings_strong": "สัญญาณที่แข็งแกร่งที่สุดของ {name} คือ {signal} ที่ {signal_score}/100", "ans_no_vulns": "ไม่พบช่องโหว่ที่ทราบ", "ans_has_vulns": "พบ {count} ช่องโหว่ที่ทราบ", "ans_verified": "ผ่านเกณฑ์ Nerq Verified 70+", "ans_not_verified": "ยังไม่ถึงเกณฑ์ Nerq Verified 70+",
        "trust_score_breakdown": "รายละเอียดคะแนนความน่าเชื่อถือ",
        "safety_score_breakdown": "รายละเอียดคะแนนความปลอดภัย",
        "key_findings": "ข้อค้นพบหลัก",
        "key_safety_findings": "ข้อค้นพบด้านความปลอดภัยหลัก",
        "details": "รายละเอียด",
        "detailed_score_analysis": "การวิเคราะห์คะแนนอย่างละเอียด",
        "faq": "คำถามที่พบบ่อย",
        "community_reviews": "รีวิวจากชุมชน",
        "regulatory_compliance": "การปฏิบัติตามกฎระเบียบ",
        "how_calculated": "วิธีที่เราคำนวณคะแนนนี้",
        "popular_alternatives": "ทางเลือกยอดนิยมใน {category}",
        "safer_alternatives": "ทางเลือกที่ปลอดภัยกว่า",
        "across_platforms": "{name} บนแพลตฟอร์มอื่น",
        "safety_guide": "คู่มือความปลอดภัย: {name}",
        "what_is": "{name} คืออะไร?",
        "key_concerns": "ข้อกังวลด้านความปลอดภัยหลักสำหรับ {type}",
        "how_to_verify": "วิธีตรวจสอบความปลอดภัย",
        "trust_assessment": "การประเมินความน่าเชื่อถือ",
        "what_data_collect": "{name} เก็บข้อมูลอะไรบ้าง?",
        "is_secure": "{name} ปลอดภัยหรือไม่?",
        "is_safe_visit": "{name} ปลอดภัยที่จะเยี่ยมชมหรือไม่?",
        "is_legit_charity": "{name} เป็นองค์กรการกุศลที่ถูกต้องตามกฎหมายหรือไม่?",
        "crime_safety": "อาชญากรรมและความปลอดภัยใน {name}",
        "financial_transparency": "ความโปร่งใสทางการเงินของ {name}",
        "yes_safe": "ใช่ {name} ปลอดภัยที่จะใช้งาน",
        "use_caution": "ใช้ {name} ด้วยความระมัดระวัง",
        "exercise_caution": "ควรระวังกับ {name}",
        "significant_concerns": "{name} มีปัญหาด้านความน่าเชื่อถือที่สำคัญ",
        "safe": "ปลอดภัย",
        "use_caution_short": "ระวัง",
        "avoid": "หลีกเลี่ยง",
        "passes_threshold": "ผ่านเกณฑ์การตรวจสอบของ Nerq",
        "below_threshold": "ต่ำกว่าเกณฑ์การตรวจสอบของ Nerq",
        "significant_gaps": "ตรวจพบช่องว่างด้านความน่าเชื่อถือที่สำคัญ",
        "meets_threshold_detail": "ผ่านเกณฑ์ความน่าเชื่อถือของ Nerq ด้วยสัญญาณที่แข็งแกร่งในด้านความปลอดภัย การบำรุงรักษา และการยอมรับจากชุมชน",
        "not_reached_threshold": "และยังไม่ถึงเกณฑ์ความน่าเชื่อถือของ Nerq (70+)",
        "score_based_on": "คะแนนนี้อิงจากการวิเคราะห์อัตโนมัติของสัญญาณด้านความปลอดภัย การบำรุงรักษา ชุมชน และคุณภาพ",
        "recommended_production": "แนะนำสำหรับการใช้งานจริง",
        "last_analyzed": "วิเคราะห์ล่าสุด:",
        "author_label": "ผู้พัฒนา",
        "category_label": "หมวดหมู่",
        "stars_label": "ดาว",
        "global_rank_label": "อันดับโลก",
        "source_label": "แหล่งที่มา",
        "machine_readable": "ข้อมูลที่เครื่องอ่านได้ (JSON)",
        "full_analysis": "การวิเคราะห์ฉบับเต็ม:",
        "privacy_report": "รายงานความเป็นส่วนตัวของ {name}",
        "security_report": "รายงานความปลอดภัยของ {name}",
        "write_review": "เขียนรีวิว",
        "no_reviews": "ยังไม่มีรีวิว",
        "be_first_review": "เป็นคนแรกที่รีวิว {name}",
        "security": "ความปลอดภัย",
        "compliance": "การปฏิบัติตามกฎระเบียบ",
        "maintenance": "การบำรุงรักษา",
        "documentation": "เอกสาร",
        "popularity": "ความนิยม",
        "overall_trust": "ความน่าเชื่อถือโดยรวม",
        "privacy": "ความเป็นส่วนตัว",
        "reliability": "ความน่าเชื่อถือ",
        "transparency": "ความโปร่งใส",
        "disclaimer": "คะแนนความน่าเชื่อถือของ Nerq เป็นการประเมินอัตโนมัติจากสัญญาณที่เปิดเผยต่อสาธารณะ ไม่ใช่คำแนะนำหรือการรับประกัน กรุณาตรวจสอบด้วยตนเองเสมอ",
        "same_developer": "ผู้พัฒนา/บริษัทเดียวกันใน registry อื่น:",
        "methodology_entities": "Nerq วิเคราะห์มากกว่า 7.5 ล้านเอนทิตีใน 26 registry โดยใช้วิธีการเดียวกัน ทำให้สามารถเปรียบเทียบโดยตรงระหว่างเอนทิตีได้",
        "scores_updated_continuously": "คะแนนจะถูกอัปเดตอย่างต่อเนื่องเมื่อมีข้อมูลใหม่",
        "strongest_signal": "สัญญาณที่แข็งแกร่งที่สุด:",
        "in_category": "ในหมวดหมู่ {category},",
        "check_back_soon": "กลับมาตรวจสอบเร็วๆ นี้",
        "safe_solo": "{name} ปลอดภัยสำหรับนักท่องเที่ยวเดี่ยวหรือไม่?",
        "safe_women": "{name} ปลอดภัยสำหรับผู้หญิงหรือไม่?",
        "safe_lgbtq": "{name} ปลอดภัยสำหรับนักท่องเที่ยว LGBTQ+ หรือไม่?",
        "safe_families": "{name} ปลอดภัยสำหรับครอบครัวหรือไม่?",
        "safe_visit_now": "{name} ปลอดภัยที่จะเยี่ยมชมตอนนี้หรือไม่?",
        "tap_water_safe": "น้ำประปาใน {name} ปลอดภัยที่จะดื่มหรือไม่?",
        "need_vaccinations": "ฉันต้องฉีดวัคซีนสำหรับ {name} หรือไม่?",
        "what_are_side_effects": "ผลข้างเคียงของ {name} มีอะไรบ้าง?",
        "what_are_safer_alts": "ทางเลือกที่ปลอดภัยกว่า {name} มีอะไรบ้าง?",
        "interact_medications": "{name} มีปฏิกิริยากับยาหรือไม่?",
        "cause_irritation": "{name} อาจทำให้เกิดการระคายเคืองผิวหรือไม่?",
        "health_disclaimer": "ข้อมูลนี้มีไว้เพื่อการศึกษาเท่านั้นและไม่ใช่คำแนะนำทางการแพทย์ กรุณาปรึกษาแพทย์ก่อนตัดสินใจเกี่ยวกับสุขภาพ",
        "not_analyzed_title": "{name} — ยังไม่ได้วิเคราะห์ | Nerq",
        "not_analyzed_h1": "{name} — ยังไม่ได้วิเคราะห์",
        "not_analyzed_msg": "Nerq ยังไม่ได้ทำการวิเคราะห์ความน่าเชื่อถือของ {name} เราวิเคราะห์มากกว่า 7.5 ล้านเอนทิตี — รายการนี้อาจถูกเพิ่มเร็วๆ นี้",
        "not_analyzed_meanwhile": "ในระหว่างนี้ คุณสามารถ:",
        "not_analyzed_search": "ลองค้นหาด้วยการสะกดที่แตกต่าง",
        "not_analyzed_api": "ตรวจสอบ API โดยตรง",
        "not_analyzed_browse": "เรียกดูเอนทิตีที่เราวิเคราะห์แล้ว",
        "not_analyzed_no_score": "หน้านี้ไม่มีคะแนนความน่าเชื่อถือเนื่องจากเรายังไม่ได้วิเคราะห์เอนทิตีนี้",
        "not_analyzed_no_fabricate": "Nerq ไม่เคยปลอมแปลงคะแนน หากคุณเชื่อว่าเอนทิตีนี้ควรได้รับการวิเคราะห์ อาจปรากฏในการอัปเดตครั้งต่อไป",
    },
    "tr": {
        "vpn_outside_eyes": "Five Eyes, Nine Eyes ve Fourteen Eyes gözetim ittifaklarının dışında",
        "faq_q3_alts": "{name} için daha güvenli alternatifler nelerdir?",
        "faq_q4_log": "{name} verilerimi kaydediyor mu?",
        "faq_q4_update": "{name} güvenlik puanı ne sıklıkla güncellenir?",
        "faq_q5_vs": "{name} vs alternatifler: hangisi daha güvenli?",
        "faq_q5_regulated": "{name}'i düzenlenmiş bir ortamda kullanabilir miyim?",
        "vpn_sec_score": "Güvenlik puanı",
        "privacy_score_label": "Gizlilik puanı",
        "strong": "güçlü",
        "moderate": "orta",
        "weak": "zayıf",
        "actively_maintained": "aktif olarak sürdürülüyor",
        "moderately_maintained": "orta düzeyde sürdürülüyor",
        "low_maintenance": "düşük bakım etkinliği",
        "well_documented": "iyi belgelenmiş",
        "partial_documentation": "kısmi belgeleme",
        "limited_documentation": "sınırlı belgeleme",
        "community_adoption": "topluluk benimsemesi",
        "faq_q4_vuln": "{name}'in bilinen güvenlik açıkları var mı?",
        "faq_q4_kids": "{name} çocuklar için güvenli mi?",
        "faq_q4_perms": "{name} hangi izinlere ihtiyaç duyar?",
        "faq_q4_maintained": "{name} aktif olarak bakımı yapılıyor mu?",
        "faq_a4_vuln": "Nerq, {name}'i NVD, OSV.dev ve kayıt defteri güvenlik açığı veritabanlarına karşı kontrol eder. Mevcut güvenlik puanı: {sec_score}.",
        "faq_a4_kids": "{name}'in Nerq puanı {score}/100'dür. Ebeveynler tam raporu incelemelidir.",
        "faq_a4_perms": "{name}'in istediği izinleri dikkatle inceleyin. Güven puanı: {score}/100.",
        "faq_a4_maintained": "{name} bakım puanı: {maint_score}. Depodaki son etkinliği kontrol edin.",
        "faq_a5_verified": "{name} Nerq doğrulama eşiğini karşılıyor (70+). Üretim kullanımı için güvenli.",
        "faq_a5_not_verified": "{name} Nerq doğrulama eşiği olan 70'e ulaşmadı. Ek inceleme önerilir.",
        "more_being_analyzed": "daha fazla {type} analiz ediliyor — yakında tekrar kontrol edin.",
        "vpn_jurisdiction": "yetki alanı",
        "vpn_operates_under": "yetki alanı altında faaliyet gösterir",
        "xlink_add_av_vpn": "VPN'inizle birlikte antivirüs ile güvenliğinizi tamamlayın",
        "xlink_add_av": "Antivirüs koruması ekle",
        "xlink_add_pm_vpn": "VPN'inize bir parola yöneticisi ekleyin",
        "xlink_complete_security": "Güvenliğinizi tamamlayın",
        "xlink_complete_privacy": "Gizliliğinizi tamamlayın",
        "is_a_type": "bir {type}",
        "rec_privacy": "gizlilik bilincine sahip kullanım için önerilir",
        "title_safe": "{name} Güvenli mi? Bağımsız Güven ve Güvenlik Analizi {year} | Nerq",
        "title_safe_visit": "{name} Ziyaret Etmek Güvenli mi? Güvenlik Puanı {year} &amp; Seyahat Rehberi | Nerq",
        "title_charity": "{name} Güvenilir Bir Hayır Kurumu mu? Güven Analizi {year} | Nerq",
        "title_ingredient": "{name} Güvenli mi? Sağlık &amp; Güvenlik Analizi {year} | Nerq",
        "h1_safe": "{name} Güvenli mi?",
        "h1_safe_visit": "{name} Ziyaret Etmek Güvenli mi?",
        "h1_trustworthy_charity": "{name} Güvenilir Bir Hayır Kurumu mu?",
        "h1_ingredient_safe": "{name} Güvenli mi?",
        "breadcrumb_safety": "Güvenlik Raporları",
        "security_analysis": "Güvenlik Analizi", "privacy_report": "Gizlilik Raporu", "similar_in_registry": "Güven Puanına göre benzer {registry}", "see_all_best": "En güvenli {registry} tümünü görüntüle",
        "pv_grade": "{grade} notu", "pv_body": "{dims} güven boyutunun analizine dayanarak, {verdict} olarak değerlendirilmektedir.", "pv_vulns": "{count} bilinen güvenlik açığı ile", "pv_updated": "Son güncelleme: {date}.", "pv_safe": "kullanımı güvenli", "pv_generally_safe": "genel olarak güvenli ancak bazı endişeler var", "pv_notable_concerns": "dikkate değer güvenlik endişeleri var", "pv_significant_risks": "önemli güvenlik riskleri var", "pv_unsafe": "güvensiz olarak değerlendiriliyor",
        "h2q_trust_score": "{name}'in güven puanı nedir?", "h2q_key_findings": "{name} için temel güvenlik bulguları nelerdir?", "h2q_details": "{name} nedir ve kim tarafından yönetilmektedir?", "ans_trust": "{name}'in Nerq Güven Puanı {score}/100 olup {grade} notu almıştır. Bu puan {dims} bağımsız olarak ölçülen boyuta dayanmaktadır.", "ans_findings_strong": "{name}'in en güçlü sinyali {signal_score}/100 ile {signal}'dir.", "ans_no_vulns": "Bilinen güvenlik açığı tespit edilmemiştir.", "ans_has_vulns": "{count} bilinen güvenlik açığı tespit edilmiştir.", "ans_verified": "Nerq Doğrulanmış eşiğini (70+) karşılamaktadır.", "ans_not_verified": "Henüz Nerq Doğrulanmış eşiğine (70+) ulaşamamıştır.",
        "trust_score_breakdown": "Güven Puanı Detayları",
        "safety_score_breakdown": "Güvenlik Puanı Detayları",
        "key_findings": "Temel Bulgular",
        "key_safety_findings": "Temel Güvenlik Bulguları",
        "details": "Detaylar",
        "detailed_score_analysis": "Detaylı Puan Analizi",
        "faq": "Sık Sorulan Sorular",
        "community_reviews": "Topluluk Değerlendirmeleri",
        "regulatory_compliance": "Düzenleyici Uyumluluk",
        "how_calculated": "Bu puanı nasıl hesapladık",
        "popular_alternatives": "{category} kategorisindeki popüler alternatifler",
        "safer_alternatives": "Daha Güvenli Alternatifler",
        "across_platforms": "{name} Diğer Platformlarda",
        "safety_guide": "Güvenlik Rehberi: {name}",
        "what_is": "{name} Nedir?",
        "key_concerns": "{type} için temel güvenlik sorunları",
        "how_to_verify": "Güvenliği Nasıl Doğrularsınız",
        "trust_assessment": "Güven Değerlendirmesi",
        "what_data_collect": "{name} hangi verileri topluyor?",
        "is_secure": "{name} güvenli mi?",
        "is_safe_visit": "{name} ziyaret etmek güvenli mi?",
        "is_legit_charity": "{name} meşru bir hayır kurumu mu?",
        "crime_safety": "{name} bölgesinde suç ve güvenlik",
        "financial_transparency": "{name} mali şeffaflığı",
        "yes_safe": "Evet, {name} kullanımı güvenlidir.",
        "use_caution": "{name} kullanırken dikkatli olun.",
        "exercise_caution": "{name} konusunda dikkatli olun.",
        "significant_concerns": "{name} önemli güven sorunlarına sahiptir.",
        "safe": "Güvenli",
        "use_caution_short": "Dikkat",
        "avoid": "Kaçının",
        "passes_threshold": "Nerq Doğrulanmış eşiğini karşılıyor",
        "below_threshold": "Nerq Doğrulanmış eşiğinin altında",
        "significant_gaps": "Önemli güven boşlukları tespit edildi",
        "meets_threshold_detail": "Güvenlik, bakım ve topluluk benimsemesi alanlarında güçlü sinyallerle Nerq güven eşiğini karşılıyor",
        "not_reached_threshold": "ve henüz Nerq güven eşiğine (70+) ulaşamamıştır.",
        "score_based_on": "Bu puan, güvenlik, bakım, topluluk ve kalite sinyallerinin otomatik analizine dayanmaktadır.",
        "recommended_production": "Üretim kullanımı için önerilir",
        "last_analyzed": "Son analiz:",
        "author_label": "Geliştirici",
        "category_label": "Kategori",
        "stars_label": "Yıldız",
        "global_rank_label": "Küresel Sıralama",
        "source_label": "Kaynak",
        "machine_readable": "Makine tarafından okunabilir veri (JSON)",
        "full_analysis": "Tam analiz:",
        "privacy_report": "{name} Gizlilik Raporu",
        "security_report": "{name} Güvenlik Raporu",
        "write_review": "Değerlendirme yaz",
        "no_reviews": "Henüz değerlendirme yok.",
        "be_first_review": "{name} için ilk değerlendirmeyi siz yapın",
        "security": "Güvenlik",
        "compliance": "Uyumluluk",
        "maintenance": "Bakım",
        "documentation": "Dokümantasyon",
        "popularity": "Popülerlik",
        "overall_trust": "Genel Güven",
        "privacy": "Gizlilik",
        "reliability": "Güvenilirlik",
        "transparency": "Şeffaflık",
        "disclaimer": "Nerq güven puanları, kamuya açık sinyallere dayanan otomatik değerlendirmelerdir. Tavsiye veya garanti niteliğinde değildir. Her zaman kendi doğrulamanızı yapın.",
        "same_developer": "Diğer kayıt defterlerinde aynı geliştirici/şirket:",
        "methodology_entities": "Nerq, aynı metodolojiyi kullanarak 26 kayıt defterindeki 7,5 milyondan fazla varlığı analiz eder ve doğrudan karşılaştırma yapılmasını sağlar.",
        "scores_updated_continuously": "Puanlar, yeni veriler kullanılabilir hale geldikçe sürekli güncellenir.",
        "strongest_signal": "En güçlü sinyal:",
        "in_category": "{category} kategorisinde,",
        "check_back_soon": "yakında tekrar kontrol edin",
        "safe_solo": "{name} yalnız gezginler için güvenli mi?",
        "safe_women": "{name} kadınlar için güvenli mi?",
        "safe_lgbtq": "{name} LGBTQ+ gezginler için güvenli mi?",
        "safe_families": "{name} aileler için güvenli mi?",
        "safe_visit_now": "{name} şu anda ziyaret etmek güvenli mi?",
        "tap_water_safe": "{name} bölgesinde musluk suyu içmek güvenli mi?",
        "need_vaccinations": "{name} için aşı yaptırmam gerekiyor mu?",
        "what_are_side_effects": "{name} yan etkileri nelerdir?",
        "what_are_safer_alts": "{name} için daha güvenli alternatifler nelerdir?",
        "interact_medications": "{name} ilaçlarla etkileşime girer mi?",
        "cause_irritation": "{name} cilt tahrişine neden olabilir mi?",
        "health_disclaimer": "Bu bilgiler yalnızca eğitim amaçlıdır ve tıbbi tavsiye niteliğinde değildir. Sağlık kararları vermeden önce nitelikli bir sağlık uzmanına danışın.",
        "not_analyzed_title": "{name} — Henüz Analiz Edilmedi | Nerq",
        "not_analyzed_h1": "{name} — Henüz Analiz Edilmedi",
        "not_analyzed_msg": "Nerq henüz {name} için güven analizi yapmamıştır. 7,5 milyondan fazla varlığı analiz ediyoruz — bu yakında eklenebilir.",
        "not_analyzed_meanwhile": "Bu arada şunları yapabilirsiniz:",
        "not_analyzed_search": "Farklı bir yazımla aramayı deneyin",
        "not_analyzed_api": "API'yi doğrudan kontrol edin",
        "not_analyzed_browse": "Analiz ettiğimiz varlıklara göz atın",
        "not_analyzed_no_score": "Bu sayfa, bu varlığı henüz analiz etmediğimiz için güven puanı içermemektedir.",
        "not_analyzed_no_fabricate": "Nerq asla puan uydurmaz. Bu varlığın kapsanması gerektiğine inanıyorsanız, gelecek bir güncellemede görünebilir.",
    },
    "ro": {
        "vpn_outside_eyes": "în afara alianțelor de supraveghere Five Eyes, Nine Eyes și Fourteen Eyes",
        "faq_q3_alts": "Care sunt alternative mai sigure la {name}?",
        "faq_q4_log": "{name} înregistrează datele mele?",
        "faq_q4_update": "Cât de des este actualizat scorul de securitate al {name}?",
        "faq_q5_vs": "{name} vs alternative: care este mai sigur?",
        "faq_q5_regulated": "Pot folosi {name} într-un mediu reglementat?",
        "vpn_sec_score": "Scor de securitate",
        "privacy_score_label": "Scor de confidențialitate",
        "strong": "puternic",
        "moderate": "moderat",
        "weak": "slab",
        "actively_maintained": "întreținut activ",
        "moderately_maintained": "moderat întreținut",
        "low_maintenance": "activitate redusă de întreținere",
        "well_documented": "bine documentat",
        "partial_documentation": "documentare parțială",
        "limited_documentation": "documentare limitată",
        "community_adoption": "adoptare de comunitate",
        "faq_q4_vuln": "Are {name} vulnerabilități cunoscute?",
        "faq_q4_kids": "Este {name} sigur pentru copii?",
        "faq_q4_perms": "Ce permisiuni necesită {name}?",
        "faq_q4_maintained": "Este {name} întreținut activ?",
        "faq_a4_vuln": "Nerq verifică {name} contra NVD, OSV.dev și bazelor de date de vulnerabilități. Scor de securitate actual: {sec_score}.",
        "faq_a4_kids": "{name} are un scor Nerq de {score}/100. Părinții ar trebui să verifice raportul complet.",
        "faq_a4_perms": "Verificați cu atenție permisiunile solicitate de {name}. Scor de încredere: {score}/100.",
        "faq_a4_maintained": "Scor de întreținere {name}: {maint_score}. Verificați activitatea recentă a depozitului.",
        "faq_a5_verified": "{name} îndeplinește pragul de verificare Nerq (70+). Sigur pentru utilizare în producție.",
        "faq_a5_not_verified": "{name} nu a atins pragul de verificare Nerq de 70. Se recomandă verificare suplimentară.",
        "more_being_analyzed": "mai multe {type} sunt analizate — reveniți curând.",
        "vpn_jurisdiction": "jurisdicție",
        "vpn_operates_under": "operează sub",
        "xlink_add_av_vpn": "Completați securitatea cu antivirus alături de VPN",
        "xlink_add_av": "Adăugați protecție antivirus",
        "xlink_add_pm_vpn": "Adăugați un manager de parole la VPN-ul dvs.",
        "xlink_complete_security": "Completați securitatea",
        "xlink_complete_privacy": "Completați confidențialitatea",
        "is_a_type": "este un {type}",
        "rec_privacy": "recomandat pentru utilizare conștientă de confidențialitate",
        "ans_trust": "{name} are un Nerq Trust Score de {score}/100 cu nota {grade}. Acest scor se bazează pe {dims} dimensiuni măsurate independent, inclusiv securitate, întreținere și adopție comunitară.",
        "ans_findings_strong": "Cel mai puternic semnal al {name} este {signal} la {signal_score}/100.",
        "ans_no_vulns": "Nu au fost detectate vulnerabilități cunoscute.",
        "title_safe": "Este {name} sigur? Analiză independentă de încredere și securitate {year} | Nerq",
        "title_safe_visit": "Este {name} sigur de vizitat? Scor de securitate {year} &amp; Ghid de călătorie | Nerq",
        "title_charity": "Este {name} o organizație caritabilă de încredere? Analiză de încredere {year} | Nerq",
        "title_ingredient": "Este {name} sigur? Analiză de sănătate &amp; securitate {year} | Nerq",
        "h1_safe": "Este {name} sigur?",
        "h1_safe_visit": "Este {name} sigur de vizitat?",
        "h1_trustworthy_charity": "Este {name} o organizație caritabilă de încredere?",
        "h1_ingredient_safe": "Este {name} sigur?",
        "breadcrumb_safety": "Rapoarte de securitate",
        "security_analysis": "Analiză de Securitate", "privacy_report": "Raport de Confidențialitate", "similar_in_registry": "{registry} similare după Scor de Încredere", "see_all_best": "Vezi toate cele mai sigure {registry}",
        "pv_grade": "Nota {grade}", "pv_body": "Pe baza analizei a {dims} dimensiuni de încredere, este {verdict}.", "pv_vulns": "cu {count} vulnerabilități cunoscute", "pv_updated": "Ultima actualizare: {date}.", "pv_safe": "considerat sigur pentru utilizare", "pv_generally_safe": "în general sigur, dar cu unele preocupări", "pv_notable_concerns": "are preocupări de securitate notabile", "pv_significant_risks": "are riscuri de securitate semnificative", "pv_unsafe": "considerat nesigur",
        "h2q_trust_score": "Care este scorul de încredere al {name}?", "h2q_key_findings": "Care sunt principalele constatări de securitate pentru {name}?", "h2q_details": "Ce este {name} și cine îl întreține?",
        "trust_score_breakdown": "Detalii scor de încredere",
        "safety_score_breakdown": "Detalii scor de securitate",
        "key_findings": "Constatări principale",
        "key_safety_findings": "Constatări principale de securitate",
        "details": "Detalii",
        "detailed_score_analysis": "Analiză detaliată a scorului",
        "faq": "Întrebări frecvente",
        "community_reviews": "Recenzii din comunitate",
        "regulatory_compliance": "Conformitate reglementară",
        "how_calculated": "Cum am calculat acest scor",
        "popular_alternatives": "Alternative populare în {category}",
        "safer_alternatives": "Alternative mai sigure",
        "across_platforms": "{name} pe alte platforme",
        "safety_guide": "Ghid de securitate: {name}",
        "what_is": "Ce este {name}?",
        "key_concerns": "Probleme principale de securitate pentru {type}",
        "how_to_verify": "Cum să verifici securitatea",
        "trust_assessment": "Evaluare de încredere",
        "what_data_collect": "Ce date colectează {name}?",
        "is_secure": "Este {name} sigur?",
        "is_safe_visit": "Este {name} sigur de vizitat?",
        "is_legit_charity": "Este {name} o organizație caritabilă legitimă?",
        "crime_safety": "Criminalitate și siguranță în {name}",
        "financial_transparency": "Transparența financiară a {name}",
        "yes_safe": "Da, {name} este sigur de utilizat.",
        "use_caution": "Folosiți {name} cu precauție.",
        "exercise_caution": "Fiți precauți cu {name}.",
        "significant_concerns": "{name} are probleme semnificative de încredere.",
        "safe": "Sigur",
        "use_caution_short": "Precauție",
        "avoid": "De evitat",
        "passes_threshold": "Îndeplinește pragul verificat Nerq",
        "below_threshold": "Sub pragul verificat Nerq",
        "significant_gaps": "Lacune semnificative de încredere detectate",
        "meets_threshold_detail": "Îndeplinește pragul de încredere Nerq cu semnale puternice în securitate, mentenanță și adoptare comunitară",
        "not_reached_threshold": "și nu a atins încă pragul de încredere Nerq (70+).",
        "score_based_on": "Acest scor se bazează pe analiza automatizată a semnalelor de securitate, mentenanță, comunitate și calitate.",
        "recommended_production": "Recomandat pentru utilizare în producție",
        "last_analyzed": "Ultima analiză:",
        "author_label": "Autor",
        "category_label": "Categorie",
        "stars_label": "Stele",
        "global_rank_label": "Clasament global",
        "source_label": "Sursă",
        "machine_readable": "Date citibile de mașină (JSON)",
        "full_analysis": "Analiză completă:",
        "privacy_report": "Raport de confidențialitate {name}",
        "security_report": "Raport de securitate {name}",
        "write_review": "Scrie o recenzie",
        "no_reviews": "Încă nu există recenzii.",
        "be_first_review": "Fii primul care recenzează {name}",
        "security": "Securitate",
        "compliance": "Conformitate",
        "maintenance": "Mentenanță",
        "documentation": "Documentație",
        "popularity": "Popularitate",
        "overall_trust": "Încredere generală",
        "privacy": "Confidențialitate",
        "reliability": "Fiabilitate",
        "transparency": "Transparență",
        "disclaimer": "Scorurile de încredere Nerq sunt evaluări automatizate bazate pe semnale disponibile public. Nu sunt recomandări sau garanții. Efectuați întotdeauna propria verificare.",
        "same_developer": "Același dezvoltator/companie în alte registre:",
        "methodology_entities": "Nerq analizează peste 7,5 milioane de entități din 26 de registre folosind aceeași metodologie, permițând compararea directă între entități.",
        "scores_updated_continuously": "Scorurile sunt actualizate continuu pe măsură ce devin disponibile date noi.",
        "strongest_signal": "Cel mai puternic semnal:",
        "in_category": "În categoria {category},",
        "check_back_soon": "reveniți în curând",
        "safe_solo": "Este {name} sigur pentru călătorii singuri?",
        "safe_women": "Este {name} sigur pentru femei?",
        "safe_lgbtq": "Este {name} sigur pentru călătorii LGBTQ+?",
        "safe_families": "Este {name} sigur pentru familii?",
        "safe_visit_now": "Este {name} sigur de vizitat acum?",
        "tap_water_safe": "Este apa de la robinet sigură de băut în {name}?",
        "need_vaccinations": "Am nevoie de vaccinuri pentru {name}?",
        "what_are_side_effects": "Care sunt efectele secundare ale {name}?",
        "what_are_safer_alts": "Care sunt alternativele mai sigure la {name}?",
        "interact_medications": "Interacționează {name} cu medicamentele?",
        "cause_irritation": "Poate {name} cauza iritarea pielii?",
        "health_disclaimer": "Aceste informații sunt doar în scop educativ și nu constituie sfat medical. Consultați un profesionist medical calificat înainte de a lua decizii de sănătate.",
        "not_analyzed_title": "{name} — Încă neanalizat | Nerq",
        "not_analyzed_h1": "{name} — Încă neanalizat",
        "not_analyzed_msg": "Nerq nu a efectuat încă o analiză de încredere pentru {name}. Analizăm peste 7,5 milioane de entități — aceasta poate fi adăugată în curând.",
        "not_analyzed_meanwhile": "Între timp, puteți:",
        "not_analyzed_search": "Încercați căutarea cu o ortografie diferită",
        "not_analyzed_api": "Verificați API-ul direct",
        "not_analyzed_browse": "Răsfoiți entitățile pe care le-am analizat deja",
        "not_analyzed_no_score": "Această pagină nu conține un scor de încredere deoarece nu am analizat încă această entitate.",
        "not_analyzed_no_fabricate": "Nerq nu fabrică niciodată evaluări. Dacă credeți că această entitate ar trebui acoperită, poate apărea într-o actualizare viitoare.",
    },
    "hi": {
        "vpn_outside_eyes": "Five Eyes, Nine Eyes और Fourteen Eyes निगरानी गठबंधनों से बाहर",
        "faq_q3_alts": "{name} के अधिक सुरक्षित विकल्प क्या हैं?",
        "faq_q4_log": "क्या {name} मेरा डेटा लॉग करता है?",
        "faq_q4_update": "{name} का सुरक्षा स्कोर कितनी बार अपडेट होता है?",
        "faq_q5_vs": "{name} बनाम विकल्प: कौन अधिक सुरक्षित है?",
        "faq_q5_regulated": "क्या मैं विनियमित वातावरण में {name} उपयोग कर सकता हूँ?",
        "vpn_sec_score": "सुरक्षा स्कोर",
        "privacy_score_label": "गोपनीयता स्कोर",
        "strong": "मजबूत",
        "moderate": "मध्यम",
        "weak": "कमजोर",
        "actively_maintained": "सक्रिय रूप से अनुरक्षित",
        "moderately_maintained": "मध्यम रूप से अनुरक्षित",
        "low_maintenance": "कम रखरखाव गतिविधि",
        "well_documented": "अच्छी तरह से प्रलेखित",
        "partial_documentation": "आंशिक प्रलेखन",
        "limited_documentation": "सीमित प्रलेखन",
        "community_adoption": "सामुदायिक अपनाव",
        "faq_q4_vuln": "क्या {name} में ज्ञात कमज़ोरियाँ हैं?",
        "faq_q4_kids": "क्या {name} बच्चों के लिए सुरक्षित है?",
        "faq_q4_perms": "{name} को किन अनुमतियों की आवश्यकता है?",
        "faq_q4_maintained": "क्या {name} सक्रिय रूप से अनुरक्षित है?",
        "faq_a4_vuln": "Nerq {name} को NVD, OSV.dev और रजिस्ट्री-विशिष्ट भेद्यता डेटाबेस के विरुद्ध जाँचता है। वर्तमान सुरक्षा स्कोर: {sec_score}।",
        "faq_a4_kids": "{name} का Nerq स्कोर {score}/100 है। माता-पिता को पूरी रिपोर्ट की समीक्षा करनी चाहिए।",
        "faq_a4_perms": "{name} द्वारा अनुरोधित अनुमतियों की सावधानीपूर्वक समीक्षा करें। विश्वास स्कोर: {score}/100।",
        "faq_a4_maintained": "{name} रखरखाव स्कोर: {maint_score}। हाल की रिपॉजिटरी गतिविधि जाँचें।",
        "faq_a5_verified": "{name} Nerq सत्यापन सीमा (70+) पूरी करता है। उत्पादन उपयोग के लिए सुरक्षित।",
        "faq_a5_not_verified": "{name} Nerq सत्यापन सीमा 70 तक नहीं पहुँचा। अतिरिक्त समीक्षा अनुशंसित है।",
        "more_being_analyzed": "और {type} का विश्लेषण किया जा रहा है — जल्दी वापस आएं।",
        "vpn_jurisdiction": "अधिकार क्षेत्र",
        "vpn_operates_under": "के अधिकार क्षेत्र में काम करता है",
        "xlink_add_av_vpn": "VPN के साथ एंटीवायरस से अपनी सुरक्षा पूरी करें",
        "xlink_add_av": "एंटीवायरस सुरक्षा जोड़ें",
        "xlink_add_pm_vpn": "अपने VPN में पासवर्ड मैनेजर जोड़ें",
        "xlink_complete_security": "अपनी सुरक्षा पूरी करें",
        "xlink_complete_privacy": "अपनी गोपनीयता पूरी करें",
        "is_a_type": "एक {type} है",
        "rec_privacy": "गोपनीयता-सचेत उपयोग के लिए अनुशंसित",
        "ans_trust": "{name} का Nerq Trust Score {score}/100 है, ग्रेड {grade}। यह स्कोर सुरक्षा, रखरखाव और सामुदायिक अपनाने सहित {dims} स्वतंत्र रूप से मापे गए आयामों पर आधारित है।",
        "ans_findings_strong": "{name} का सबसे मजबूत संकेत {signal} है {signal_score}/100 पर।",
        "ans_no_vulns": "कोई ज्ञात भेद्यता नहीं पाई गई।",
        "title_safe": "क्या {name} सुरक्षित है? स्वतंत्र विश्वास एवं सुरक्षा विश्लेषण {year} | Nerq",
        "title_safe_visit": "क्या {name} पर जाना सुरक्षित है? सुरक्षा स्कोर {year} &amp; यात्रा गाइड | Nerq",
        "title_charity": "क्या {name} एक विश्वसनीय चैरिटी है? विश्वास विश्लेषण {year} | Nerq",
        "title_ingredient": "क्या {name} सुरक्षित है? स्वास्थ्य &amp; सुरक्षा विश्लेषण {year} | Nerq",
        "h1_safe": "क्या {name} सुरक्षित है?",
        "h1_safe_visit": "क्या {name} पर जाना सुरक्षित है?",
        "h1_trustworthy_charity": "क्या {name} एक विश्वसनीय चैरिटी है?",
        "h1_ingredient_safe": "क्या {name} सुरक्षित है?",
        "breadcrumb_safety": "सुरक्षा रिपोर्ट",
        "security_analysis": "सुरक्षा विश्लेषण", "privacy_report": "गोपनीयता रिपोर्ट", "similar_in_registry": "विश्वास स्कोर द्वारा समान {registry}", "see_all_best": "सभी सबसे सुरक्षित {registry} देखें",
        "pv_grade": "{grade} ग्रेड", "pv_body": "{dims} विश्वास आयामों के विश्लेषण के आधार पर, इसे {verdict} माना जाता है।", "pv_vulns": "{count} ज्ञात कमजोरियों के साथ", "pv_updated": "अंतिम अपडेट: {date}।", "pv_safe": "उपयोग के लिए सुरक्षित", "pv_generally_safe": "आम तौर पर सुरक्षित लेकिन कुछ चिंताएं हैं", "pv_notable_concerns": "उल्लेखनीय सुरक्षा चिंताएं हैं", "pv_significant_risks": "महत्वपूर्ण सुरक्षा जोखिम हैं", "pv_unsafe": "असुरक्षित माना जाता है",
        "h2q_trust_score": "{name} का विश्वास स्कोर क्या है?", "h2q_key_findings": "{name} के प्रमुख सुरक्षा निष्कर्ष क्या हैं?", "h2q_details": "{name} क्या है और इसका रखरखाव कौन करता है?",
        "trust_score_breakdown": "विश्वास स्कोर विवरण",
        "safety_score_breakdown": "सुरक्षा स्कोर विवरण",
        "key_findings": "मुख्य निष्कर्ष",
        "key_safety_findings": "मुख्य सुरक्षा निष्कर्ष",
        "details": "विवरण",
        "detailed_score_analysis": "विस्तृत स्कोर विश्लेषण",
        "faq": "अक्सर पूछे जाने वाले प्रश्न",
        "community_reviews": "सामुदायिक समीक्षाएं",
        "regulatory_compliance": "नियामक अनुपालन",
        "how_calculated": "हमने इस स्कोर की गणना कैसे की",
        "popular_alternatives": "{category} में लोकप्रिय विकल्प",
        "safer_alternatives": "अधिक सुरक्षित विकल्प",
        "across_platforms": "{name} अन्य प्लेटफॉर्म पर",
        "safety_guide": "सुरक्षा गाइड: {name}",
        "what_is": "{name} क्या है?",
        "key_concerns": "{type} के लिए मुख्य सुरक्षा चिंताएं",
        "how_to_verify": "सुरक्षा कैसे सत्यापित करें",
        "trust_assessment": "विश्वास मूल्यांकन",
        "what_data_collect": "{name} कौन सा डेटा एकत्र करता है?",
        "is_secure": "क्या {name} सुरक्षित है?",
        "is_safe_visit": "क्या {name} पर जाना सुरक्षित है?",
        "is_legit_charity": "क्या {name} एक वैध चैरिटी है?",
        "crime_safety": "{name} में अपराध और सुरक्षा",
        "financial_transparency": "{name} की वित्तीय पारदर्शिता",
        "yes_safe": "हां, {name} उपयोग के लिए सुरक्षित है।",
        "use_caution": "{name} का उपयोग सावधानी से करें।",
        "exercise_caution": "{name} के साथ सावधानी बरतें।",
        "significant_concerns": "{name} में महत्वपूर्ण विश्वास संबंधी समस्याएं हैं।",
        "safe": "सुरक्षित",
        "use_caution_short": "सावधानी",
        "avoid": "बचें",
        "passes_threshold": "Nerq सत्यापित सीमा को पूरा करता है",
        "below_threshold": "Nerq सत्यापित सीमा से नीचे",
        "significant_gaps": "महत्वपूर्ण विश्वास अंतराल पाए गए",
        "meets_threshold_detail": "सुरक्षा, रखरखाव और सामुदायिक स्वीकृति में मजबूत संकेतों के साथ Nerq विश्वास सीमा को पूरा करता है",
        "not_reached_threshold": "और अभी तक Nerq विश्वास सीमा (70+) तक नहीं पहुंचा है।",
        "score_based_on": "यह स्कोर सुरक्षा, रखरखाव, समुदाय और गुणवत्ता संकेतों के स्वचालित विश्लेषण पर आधारित है।",
        "recommended_production": "प्रोडक्शन उपयोग के लिए अनुशंसित",
        "last_analyzed": "अंतिम विश्लेषण:",
        "author_label": "डेवलपर",
        "category_label": "श्रेणी",
        "stars_label": "स्टार्स",
        "global_rank_label": "वैश्विक रैंकिंग",
        "source_label": "स्रोत",
        "machine_readable": "मशीन पठनीय डेटा (JSON)",
        "full_analysis": "पूर्ण विश्लेषण:",
        "privacy_report": "{name} गोपनीयता रिपोर्ट",
        "security_report": "{name} सुरक्षा रिपोर्ट",
        "write_review": "समीक्षा लिखें",
        "no_reviews": "अभी तक कोई समीक्षा नहीं।",
        "be_first_review": "{name} की पहली समीक्षा लिखें",
        "security": "सुरक्षा",
        "compliance": "अनुपालन",
        "maintenance": "रखरखाव",
        "documentation": "दस्तावेज़ीकरण",
        "popularity": "लोकप्रियता",
        "overall_trust": "समग्र विश्वास",
        "privacy": "गोपनीयता",
        "reliability": "विश्वसनीयता",
        "transparency": "पारदर्शिता",
        "disclaimer": "Nerq विश्वास स्कोर सार्वजनिक रूप से उपलब्ध संकेतों पर आधारित स्वचालित मूल्यांकन हैं। ये सिफारिश या गारंटी नहीं हैं। हमेशा अपना स्वयं का सत्यापन करें।",
        "same_developer": "अन्य रजिस्ट्री में वही डेवलपर/कंपनी:",
        "methodology_entities": "Nerq एक ही कार्यप्रणाली का उपयोग करके 26 रजिस्ट्री में 7.5 मिलियन से अधिक इकाइयों का विश्लेषण करता है, जिससे इकाइयों के बीच सीधी तुलना संभव होती है।",
        "scores_updated_continuously": "नया डेटा उपलब्ध होने पर स्कोर लगातार अपडेट किए जाते हैं।",
        "strongest_signal": "सबसे मजबूत संकेत:",
        "in_category": "{category} श्रेणी में,",
        "check_back_soon": "जल्द ही दोबारा देखें",
        "safe_solo": "क्या {name} अकेले यात्रियों के लिए सुरक्षित है?",
        "safe_women": "क्या {name} महिलाओं के लिए सुरक्षित है?",
        "safe_lgbtq": "क्या {name} LGBTQ+ यात्रियों के लिए सुरक्षित है?",
        "safe_families": "क्या {name} परिवारों के लिए सुरक्षित है?",
        "safe_visit_now": "क्या {name} अभी जाना सुरक्षित है?",
        "tap_water_safe": "क्या {name} में नल का पानी पीना सुरक्षित है?",
        "need_vaccinations": "क्या मुझे {name} के लिए टीकाकरण की आवश्यकता है?",
        "what_are_side_effects": "{name} के दुष्प्रभाव क्या हैं?",
        "what_are_safer_alts": "{name} के अधिक सुरक्षित विकल्प क्या हैं?",
        "interact_medications": "क्या {name} दवाओं के साथ प्रतिक्रिया करता है?",
        "cause_irritation": "क्या {name} त्वचा में जलन पैदा कर सकता है?",
        "health_disclaimer": "यह जानकारी केवल शैक्षिक उद्देश्यों के लिए है और चिकित्सा सलाह नहीं है। स्वास्थ्य संबंधी निर्णय लेने से पहले किसी योग्य स्वास्थ्य पेशेवर से परामर्श लें।",
        "not_analyzed_title": "{name} — अभी तक विश्लेषित नहीं | Nerq",
        "not_analyzed_h1": "{name} — अभी तक विश्लेषित नहीं",
        "not_analyzed_msg": "Nerq ने अभी तक {name} का विश्वास विश्लेषण नहीं किया है। हम 7.5 मिलियन से अधिक इकाइयों का विश्लेषण करते हैं — यह जल्द ही जोड़ी जा सकती है।",
        "not_analyzed_meanwhile": "इस बीच, आप कर सकते हैं:",
        "not_analyzed_search": "अलग वर्तनी से खोजने का प्रयास करें",
        "not_analyzed_api": "सीधे API जांचें",
        "not_analyzed_browse": "हमारे द्वारा विश्लेषित इकाइयां ब्राउज़ करें",
        "not_analyzed_no_score": "इस पेज में विश्वास स्कोर नहीं है क्योंकि हमने अभी तक इस इकाई का विश्लेषण नहीं किया है।",
        "not_analyzed_no_fabricate": "Nerq कभी भी रेटिंग नहीं बनाता। यदि आपको लगता है कि इस इकाई को शामिल किया जाना चाहिए, तो यह भविष्य के अपडेट में दिखाई दे सकती है।",
    },
    "ru": {
        "vpn_outside_eyes": "за пределами альянсов наблюдения Five Eyes, Nine Eyes и Fourteen Eyes",
        "faq_q3_alts": "Какие более безопасные альтернативы {name}?",
        "faq_q4_log": "Записывает ли {name} мои данные?",
        "faq_q4_update": "Как часто обновляется оценка безопасности {name}?",
        "faq_q5_vs": "{name} vs альтернативы: что безопаснее?",
        "faq_q5_regulated": "Могу ли я использовать {name} в регулируемой среде?",
        "vpn_sec_score": "Оценка безопасности",
        "privacy_score_label": "Оценка конфиденциальности",
        "strong": "сильный",
        "moderate": "умеренный",
        "weak": "слабый",
        "actively_maintained": "активно поддерживается",
        "moderately_maintained": "умеренно поддерживается",
        "low_maintenance": "низкая активность поддержки",
        "well_documented": "хорошо документировано",
        "partial_documentation": "частичная документация",
        "limited_documentation": "ограниченная документация",
        "community_adoption": "принятие сообществом",
        "faq_q4_vuln": "Есть ли у {name} известные уязвимости?",
        "faq_q4_kids": "Безопасен ли {name} для детей?",
        "faq_q4_perms": "Какие разрешения нужны {name}?",
        "faq_q4_maintained": "Активно ли поддерживается {name}?",
        "faq_a4_vuln": "Nerq проверяет {name} по NVD, OSV.dev и базам данных уязвимостей. Текущая оценка безопасности: {sec_score}.",
        "faq_a4_kids": "{name} имеет оценку Nerq {score}/100. Родителям следует изучить полный отчёт.",
        "faq_a4_perms": "Внимательно проверьте запрашиваемые разрешения {name}. Оценка доверия: {score}/100.",
        "faq_a4_maintained": "Оценка поддержки {name}: {maint_score}. Проверьте недавнюю активность репозитория.",
        "faq_a5_verified": "{name} соответствует порогу верификации Nerq (70+). Безопасно для продакшена.",
        "faq_a5_not_verified": "{name} не достиг порога верификации Nerq 70. Рекомендуется дополнительная проверка.",
        "more_being_analyzed": "анализируется ещё больше {type} — проверьте позже.",
        "vpn_jurisdiction": "юрисдикция",
        "vpn_operates_under": "действует под юрисдикцией",
        "xlink_add_av_vpn": "Дополните безопасность антивирусом вместе с VPN",
        "xlink_add_av": "Добавить антивирусную защиту",
        "xlink_add_pm_vpn": "Добавьте менеджер паролей к VPN",
        "xlink_complete_security": "Завершите настройку безопасности",
        "xlink_complete_privacy": "Завершите настройку конфиденциальности",
        "is_a_type": "— это {type}",
        "rec_privacy": "рекомендуется для использования с учётом конфиденциальности",
        "ans_trust": "{name} имеет Nerq Trust Score {score}/100 с оценкой {grade}. Этот балл основан на {dims} независимо измеренных параметрах, включая безопасность, обслуживание и принятие сообществом.",
        "ans_findings_strong": "Самый сильный сигнал {name} — {signal} на уровне {signal_score}/100.",
        "ans_no_vulns": "Известных уязвимостей не обнаружено.",
        "title_safe": "Безопасен ли {name}? Независимый анализ доверия и безопасности {year} | Nerq",
        "title_safe_visit": "Безопасно ли посещать {name}? Рейтинг безопасности {year} &amp; Путеводитель | Nerq",
        "title_charity": "Является ли {name} надёжной благотворительной организацией? Анализ доверия {year} | Nerq",
        "title_ingredient": "Безопасен ли {name}? Анализ здоровья &amp; безопасности {year} | Nerq",
        "h1_safe": "Безопасен ли {name}?",
        "h1_safe_visit": "Безопасно ли посещать {name}?",
        "h1_trustworthy_charity": "Является ли {name} надёжной благотворительной организацией?",
        "h1_ingredient_safe": "Безопасен ли {name}?",
        "breadcrumb_safety": "Отчёты о безопасности",
        "security_analysis": "Анализ безопасности", "privacy_report": "Отчёт о конфиденциальности", "similar_in_registry": "Похожие {registry} по рейтингу доверия", "see_all_best": "Все самые безопасные {registry}",
        "pv_grade": "Оценка {grade}", "pv_body": "На основе анализа {dims} измерений доверия, считается {verdict}.", "pv_vulns": "с {count} известными уязвимостями", "pv_updated": "Последнее обновление: {date}.", "pv_safe": "безопасным для использования", "pv_generally_safe": "в целом безопасным, но с некоторыми опасениями", "pv_notable_concerns": "имеющим заметные проблемы безопасности", "pv_significant_risks": "имеющим значительные риски безопасности", "pv_unsafe": "небезопасным",
        "h2q_trust_score": "Каков рейтинг доверия {name}?", "h2q_key_findings": "Каковы основные выводы по безопасности {name}?", "h2q_details": "Что такое {name} и кто его поддерживает?",
        "trust_score_breakdown": "Детали рейтинга доверия",
        "safety_score_breakdown": "Детали рейтинга безопасности",
        "key_findings": "Основные выводы",
        "key_safety_findings": "Основные выводы по безопасности",
        "details": "Подробности",
        "detailed_score_analysis": "Подробный анализ рейтинга",
        "faq": "Часто задаваемые вопросы",
        "community_reviews": "Отзывы сообщества",
        "regulatory_compliance": "Соответствие нормативам",
        "how_calculated": "Как мы рассчитали этот рейтинг",
        "popular_alternatives": "Популярные альтернативы в {category}",
        "safer_alternatives": "Более безопасные альтернативы",
        "across_platforms": "{name} на других платформах",
        "safety_guide": "Руководство по безопасности: {name}",
        "what_is": "Что такое {name}?",
        "key_concerns": "Основные проблемы безопасности для {type}",
        "how_to_verify": "Как проверить безопасность",
        "trust_assessment": "Оценка доверия",
        "what_data_collect": "Какие данные собирает {name}?",
        "is_secure": "Безопасен ли {name}?",
        "is_safe_visit": "Безопасно ли посещать {name}?",
        "is_legit_charity": "Является ли {name} легитимной благотворительной организацией?",
        "crime_safety": "Преступность и безопасность в {name}",
        "financial_transparency": "Финансовая прозрачность {name}",
        "yes_safe": "Да, {name} безопасен для использования.",
        "use_caution": "Используйте {name} с осторожностью.",
        "exercise_caution": "Будьте осторожны с {name}.",
        "significant_concerns": "{name} имеет серьёзные проблемы с доверием.",
        "safe": "Безопасно",
        "use_caution_short": "Осторожно",
        "avoid": "Избегать",
        "passes_threshold": "Соответствует верифицированному порогу Nerq",
        "below_threshold": "Ниже верифицированного порога Nerq",
        "significant_gaps": "Обнаружены значительные пробелы в доверии",
        "meets_threshold_detail": "Соответствует порогу доверия Nerq с сильными сигналами в области безопасности, обслуживания и принятия сообществом",
        "not_reached_threshold": "и ещё не достиг порога доверия Nerq (70+).",
        "score_based_on": "Этот рейтинг основан на автоматическом анализе сигналов безопасности, обслуживания, сообщества и качества.",
        "recommended_production": "Рекомендуется для использования в продакшене",
        "last_analyzed": "Последний анализ:",
        "author_label": "Разработчик",
        "category_label": "Категория",
        "stars_label": "Звёзды",
        "global_rank_label": "Мировой рейтинг",
        "source_label": "Источник",
        "machine_readable": "Машинночитаемые данные (JSON)",
        "full_analysis": "Полный анализ:",
        "privacy_report": "Отчёт о конфиденциальности {name}",
        "security_report": "Отчёт о безопасности {name}",
        "write_review": "Написать отзыв",
        "no_reviews": "Пока нет отзывов.",
        "be_first_review": "Будьте первым, кто оценит {name}",
        "security": "Безопасность",
        "compliance": "Соответствие",
        "maintenance": "Обслуживание",
        "documentation": "Документация",
        "popularity": "Популярность",
        "overall_trust": "Общее доверие",
        "privacy": "Конфиденциальность",
        "reliability": "Надёжность",
        "transparency": "Прозрачность",
        "disclaimer": "Рейтинги доверия Nerq — это автоматические оценки, основанные на публично доступных сигналах. Они не являются рекомендацией или гарантией. Всегда проводите собственную проверку.",
        "same_developer": "Тот же разработчик/компания в других реестрах:",
        "methodology_entities": "Nerq анализирует более 7,5 миллиона сущностей в 26 реестрах, используя единую методологию, что позволяет проводить прямое сравнение между сущностями.",
        "scores_updated_continuously": "Рейтинги обновляются непрерывно по мере поступления новых данных.",
        "strongest_signal": "Самый сильный сигнал:",
        "in_category": "В категории {category},",
        "check_back_soon": "проверьте позже",
        "safe_solo": "Безопасен ли {name} для одиночных путешественников?",
        "safe_women": "Безопасен ли {name} для женщин?",
        "safe_lgbtq": "Безопасен ли {name} для LGBTQ+ путешественников?",
        "safe_families": "Безопасен ли {name} для семей?",
        "safe_visit_now": "Безопасно ли посещать {name} прямо сейчас?",
        "tap_water_safe": "Безопасна ли водопроводная вода в {name}?",
        "need_vaccinations": "Нужны ли прививки для {name}?",
        "what_are_side_effects": "Какие побочные эффекты у {name}?",
        "what_are_safer_alts": "Какие более безопасные альтернативы {name}?",
        "interact_medications": "Взаимодействует ли {name} с лекарствами?",
        "cause_irritation": "Может ли {name} вызвать раздражение кожи?",
        "health_disclaimer": "Эта информация предназначена только для образовательных целей и не является медицинской консультацией. Перед принятием решений о здоровье проконсультируйтесь с квалифицированным медицинским специалистом.",
        "not_analyzed_title": "{name} — Ещё не проанализировано | Nerq",
        "not_analyzed_h1": "{name} — Ещё не проанализировано",
        "not_analyzed_msg": "Nerq ещё не провёл анализ доверия для {name}. Мы анализируем более 7,5 миллиона сущностей — эта может быть добавлена в ближайшее время.",
        "not_analyzed_meanwhile": "Тем временем вы можете:",
        "not_analyzed_search": "Попробовать поиск с другим написанием",
        "not_analyzed_api": "Проверить API напрямую",
        "not_analyzed_browse": "Просмотреть уже проанализированные сущности",
        "not_analyzed_no_score": "Эта страница не содержит рейтинга доверия, так как мы ещё не проанализировали эту сущность.",
        "not_analyzed_no_fabricate": "Nerq никогда не фальсифицирует рейтинги. Если вы считаете, что эта сущность должна быть охвачена, она может появиться в будущем обновлении.",
    },
    "pl": {
        "vpn_outside_eyes": "poza sojuszami inwigilacji Five Eyes, Nine Eyes i Fourteen Eyes",
        "faq_q3_alts": "Jakie są bezpieczniejsze alternatywy dla {name}?",
        "faq_q4_log": "Czy {name} rejestruje moje dane?",
        "faq_q4_update": "Jak często aktualizowana jest ocena bezpieczeństwa {name}?",
        "faq_q5_vs": "{name} vs alternatywy: co jest bezpieczniejsze?",
        "faq_q5_regulated": "Czy mogę używać {name} w środowisku regulowanym?",
        "vpn_sec_score": "Ocena bezpieczeństwa",
        "privacy_score_label": "Ocena prywatności",
        "strong": "silny",
        "moderate": "umiarkowany",
        "weak": "słaby",
        "actively_maintained": "aktywnie utrzymywany",
        "moderately_maintained": "umiarkowanie utrzymywany",
        "low_maintenance": "niska aktywność konserwacji",
        "well_documented": "dobrze udokumentowany",
        "partial_documentation": "częściowa dokumentacja",
        "limited_documentation": "ograniczona dokumentacja",
        "community_adoption": "przyjęcie przez społeczność",
        "faq_q4_vuln": "Czy {name} ma znane luki?",
        "faq_q4_kids": "Czy {name} jest bezpieczny dla dzieci?",
        "faq_q4_perms": "Jakich uprawnień potrzebuje {name}?",
        "faq_q4_maintained": "Czy {name} jest aktywnie utrzymywany?",
        "faq_a4_vuln": "Nerq sprawdza {name} w NVD, OSV.dev i bazach danych luk. Aktualny wynik bezpieczeństwa: {sec_score}.",
        "faq_a4_kids": "{name} ma wynik Nerq {score}/100. Rodzice powinni przejrzeć pełny raport.",
        "faq_a4_perms": "Dokładnie sprawdź uprawnienia wymagane przez {name}. Wynik zaufania: {score}/100.",
        "faq_a4_maintained": "Wynik konserwacji {name}: {maint_score}. Sprawdź ostatnią aktywność repozytorium.",
        "faq_a5_verified": "{name} spełnia próg weryfikacji Nerq (70+). Bezpieczny do użytku produkcyjnego.",
        "faq_a5_not_verified": "{name} nie osiągnął progu weryfikacji Nerq 70. Zalecana dodatkowa weryfikacja.",
        "more_being_analyzed": "więcej {type} jest analizowanych — sprawdź wkrótce.",
        "vpn_jurisdiction": "jurysdykcja",
        "vpn_operates_under": "działa pod jurysdykcją",
        "xlink_add_av_vpn": "Uzupełnij bezpieczeństwo antywirusem obok VPN",
        "xlink_add_av": "Dodaj ochronę antywirusową",
        "xlink_add_pm_vpn": "Dodaj menedżera haseł do VPN",
        "xlink_complete_security": "Uzupełnij bezpieczeństwo",
        "xlink_complete_privacy": "Uzupełnij prywatność",
        "is_a_type": "to {type}",
        "rec_privacy": "zalecane do użytku dbającego o prywatność",
        "ans_trust": "{name} ma Nerq Trust Score {score}/100 z oceną {grade}. Ten wynik opiera się na {dims} niezależnie mierzonych wymiarach, w tym bezpieczeństwie, konserwacji i adopcji społeczności.",
        "ans_findings_strong": "Najsilniejszy sygnał {name} to {signal} na poziomie {signal_score}/100.",
        "ans_no_vulns": "Nie wykryto znanych luk w zabezpieczeniach.",
        "title_safe": "Czy {name} jest bezpieczny? Niezależna analiza zaufania i bezpieczeństwa {year} | Nerq",
        "title_safe_visit": "Czy {name} jest bezpieczne do odwiedzenia? Wynik bezpieczeństwa {year} &amp; Przewodnik | Nerq",
        "title_charity": "Czy {name} jest wiarygodną organizacją charytatywną? Analiza zaufania {year} | Nerq",
        "title_ingredient": "Czy {name} jest bezpieczny? Analiza zdrowia &amp; bezpieczeństwa {year} | Nerq",
        "h1_safe": "Czy {name} jest bezpieczny?",
        "h1_safe_visit": "Czy {name} jest bezpieczne do odwiedzenia?",
        "h1_trustworthy_charity": "Czy {name} jest wiarygodną organizacją charytatywną?",
        "h1_ingredient_safe": "Czy {name} jest bezpieczny?",
        "breadcrumb_safety": "Raporty bezpieczeństwa",
        "security_analysis": "Analiza bezpieczeństwa", "privacy_report": "Raport o prywatności", "similar_in_registry": "Podobne {registry} wg wyniku zaufania", "see_all_best": "Zobacz wszystkie najbezpieczniejsze {registry}",
        "pv_grade": "Ocena {grade}", "pv_body": "Na podstawie analizy {dims} wymiarów zaufania, jest {verdict}.", "pv_vulns": "z {count} znanymi podatnościami", "pv_updated": "Ostatnia aktualizacja: {date}.", "pv_safe": "uważany za bezpieczny w użyciu", "pv_generally_safe": "ogólnie bezpieczny, ale z pewnymi zastrzeżeniami", "pv_notable_concerns": "ma istotne obawy dotyczące bezpieczeństwa", "pv_significant_risks": "ma poważne zagrożenia bezpieczeństwa", "pv_unsafe": "uważany za niebezpieczny",
        "h2q_trust_score": "Jaki jest wynik zaufania {name}?", "h2q_key_findings": "Jakie są kluczowe ustalenia bezpieczeństwa dla {name}?", "h2q_details": "Czym jest {name} i kto go utrzymuje?",
        "trust_score_breakdown": "Szczegóły wyniku zaufania",
        "safety_score_breakdown": "Szczegóły wyniku bezpieczeństwa",
        "key_findings": "Kluczowe ustalenia",
        "key_safety_findings": "Kluczowe ustalenia dotyczące bezpieczeństwa",
        "details": "Szczegóły",
        "detailed_score_analysis": "Szczegółowa analiza wyniku",
        "faq": "Często zadawane pytania",
        "community_reviews": "Opinie społeczności",
        "regulatory_compliance": "Zgodność z przepisami",
        "how_calculated": "Jak obliczyliśmy ten wynik",
        "popular_alternatives": "Popularne alternatywy w {category}",
        "safer_alternatives": "Bezpieczniejsze alternatywy",
        "across_platforms": "{name} na innych platformach",
        "safety_guide": "Przewodnik bezpieczeństwa: {name}",
        "what_is": "Czym jest {name}?",
        "key_concerns": "Główne problemy bezpieczeństwa dla {type}",
        "how_to_verify": "Jak zweryfikować bezpieczeństwo",
        "trust_assessment": "Ocena zaufania",
        "what_data_collect": "Jakie dane zbiera {name}?",
        "is_secure": "Czy {name} jest bezpieczny?",
        "is_safe_visit": "Czy {name} jest bezpieczne do odwiedzenia?",
        "is_legit_charity": "Czy {name} jest legalną organizacją charytatywną?",
        "crime_safety": "Przestępczość i bezpieczeństwo w {name}",
        "financial_transparency": "Przejrzystość finansowa {name}",
        "yes_safe": "Tak, {name} jest bezpieczny w użyciu.",
        "use_caution": "Używaj {name} z ostrożnością.",
        "exercise_caution": "Zachowaj ostrożność z {name}.",
        "significant_concerns": "{name} ma poważne problemy z zaufaniem.",
        "safe": "Bezpieczny",
        "use_caution_short": "Ostrożność",
        "avoid": "Unikać",
        "passes_threshold": "Spełnia zweryfikowany próg Nerq",
        "below_threshold": "Poniżej zweryfikowanego progu Nerq",
        "significant_gaps": "Wykryto znaczące luki w zaufaniu",
        "meets_threshold_detail": "Spełnia próg zaufania Nerq z silnymi sygnałami w zakresie bezpieczeństwa, konserwacji i przyjęcia przez społeczność",
        "not_reached_threshold": "i nie osiągnął jeszcze progu zaufania Nerq (70+).",
        "score_based_on": "Ten wynik jest oparty na zautomatyzowanej analizie sygnałów bezpieczeństwa, konserwacji, społeczności i jakości.",
        "recommended_production": "Zalecany do użytku produkcyjnego",
        "last_analyzed": "Ostatnia analiza:",
        "author_label": "Autor",
        "category_label": "Kategoria",
        "stars_label": "Gwiazdki",
        "global_rank_label": "Ranking globalny",
        "source_label": "Źródło",
        "machine_readable": "Dane odczytywalne maszynowo (JSON)",
        "full_analysis": "Pełna analiza:",
        "privacy_report": "Raport prywatności {name}",
        "security_report": "Raport bezpieczeństwa {name}",
        "write_review": "Napisz opinię",
        "no_reviews": "Brak opinii.",
        "be_first_review": "Bądź pierwszy, który oceni {name}",
        "security": "Bezpieczeństwo",
        "compliance": "Zgodność",
        "maintenance": "Konserwacja",
        "documentation": "Dokumentacja",
        "popularity": "Popularność",
        "overall_trust": "Ogólne zaufanie",
        "privacy": "Prywatność",
        "reliability": "Niezawodność",
        "transparency": "Przejrzystość",
        "disclaimer": "Wyniki zaufania Nerq to zautomatyzowane oceny oparte na publicznie dostępnych sygnałach. Nie stanowią rekomendacji ani gwarancji. Zawsze przeprowadzaj własną weryfikację.",
        "same_developer": "Ten sam deweloper/firma w innych rejestrach:",
        "methodology_entities": "Nerq analizuje ponad 7,5 miliona podmiotów w 26 rejestrach przy użyciu tej samej metodologii, umożliwiając bezpośrednie porównanie między podmiotami.",
        "scores_updated_continuously": "Wyniki są na bieżąco aktualizowane w miarę dostępności nowych danych.",
        "strongest_signal": "Najsilniejszy sygnał:",
        "in_category": "W kategorii {category},",
        "check_back_soon": "sprawdź ponownie wkrótce",
        "safe_solo": "Czy {name} jest bezpieczne dla podróżników indywidualnych?",
        "safe_women": "Czy {name} jest bezpieczne dla kobiet?",
        "safe_lgbtq": "Czy {name} jest bezpieczne dla podróżników LGBTQ+?",
        "safe_families": "Czy {name} jest bezpieczne dla rodzin?",
        "safe_visit_now": "Czy {name} jest teraz bezpieczne do odwiedzenia?",
        "tap_water_safe": "Czy woda z kranu w {name} jest bezpieczna do picia?",
        "need_vaccinations": "Czy potrzebuję szczepień na {name}?",
        "what_are_side_effects": "Jakie są skutki uboczne {name}?",
        "what_are_safer_alts": "Jakie są bezpieczniejsze alternatywy dla {name}?",
        "interact_medications": "Czy {name} wchodzi w interakcje z lekami?",
        "cause_irritation": "Czy {name} może powodować podrażnienie skóry?",
        "health_disclaimer": "Te informacje służą wyłącznie celom edukacyjnym i nie stanowią porady medycznej. Przed podjęciem decyzji zdrowotnych skonsultuj się z wykwalifikowanym specjalistą.",
        "not_analyzed_title": "{name} — Jeszcze nie przeanalizowano | Nerq",
        "not_analyzed_h1": "{name} — Jeszcze nie przeanalizowano",
        "not_analyzed_msg": "Nerq nie przeprowadził jeszcze analizy zaufania dla {name}. Analizujemy ponad 7,5 miliona podmiotów — ten może zostać wkrótce dodany.",
        "not_analyzed_meanwhile": "W międzyczasie możesz:",
        "not_analyzed_search": "Spróbować wyszukać z inną pisownią",
        "not_analyzed_api": "Sprawdzić API bezpośrednio",
        "not_analyzed_browse": "Przeglądać podmioty, które już przeanalizowaliśmy",
        "not_analyzed_no_score": "Ta strona nie zawiera wyniku zaufania, ponieważ nie przeanalizowaliśmy jeszcze tego podmiotu.",
        "not_analyzed_no_fabricate": "Nerq nigdy nie fałszuje ocen. Jeśli uważasz, że ten podmiot powinien być uwzględniony, może pojawić się w przyszłej aktualizacji.",
    },
    "ko": {
        "dim_popularity": "인기도",
        "faq_q3_alts": "{name}의 더 안전한 대안은?",
        "faq_q4_log": "{name}이 내 데이터를 기록하나요?",
        "faq_q4_update": "{name}의 보안 점수는 얼마나 자주 업데이트되나요?",
        "faq_q5_vs": "{name} vs 대안: 어느 것이 더 안전한가요?",
        "faq_q5_regulated": "규제 환경에서 {name}을 사용할 수 있나요?",
        "vpn_sec_score": "보안 점수",
        "privacy_score_label": "개인정보 점수",
        "strong": "강함",
        "moderate": "보통",
        "weak": "약함",
        "actively_maintained": "활발히 유지관리 중",
        "moderately_maintained": "보통 유지관리",
        "low_maintenance": "낮은 유지관리 활동",
        "well_documented": "잘 문서화됨",
        "partial_documentation": "부분 문서화",
        "limited_documentation": "제한적 문서화",
        "community_adoption": "커뮤니티 채택",
        "faq_q4_vuln": "{name}에 알려진 취약점이 있나요?",
        "faq_q4_kids": "{name}은 아이들에게 안전한가요?",
        "faq_q4_perms": "{name}에 필요한 권한은?",
        "faq_q4_maintained": "{name}은 활발히 유지관리되고 있나요?",
        "faq_a4_vuln": "Nerq는 {name}을 NVD, OSV.dev 및 레지스트리별 취약점 데이터베이스에서 확인합니다. 현재 보안 점수: {sec_score}.",
        "faq_a4_kids": "{name}의 Nerq 점수는 {score}/100입니다. 부모님은 전체 보고서를 확인하세요.",
        "faq_a4_perms": "{name}의 요청된 권한을 신중히 검토하세요. 신뢰 점수: {score}/100.",
        "faq_a4_maintained": "{name} 유지관리 점수: {maint_score}. 저장소의 최근 활동을 확인하세요.",
        "faq_a5_verified": "{name}은 Nerq 인증 임계값(70+)을 충족합니다. 프로덕션 사용에 안전합니다.",
        "faq_a5_not_verified": "{name}은 Nerq 인증 임계값 70에 도달하지 못했습니다. 추가 검토가 권장됩니다.",
        "more_being_analyzed": "더 많은 {type}이(가) 분석 중입니다 — 곧 다시 확인하세요.",
        "dim_maintenance": "유지보수",
        "dim_security": "보안",
        "sidebar_most_private": "가장 프라이빗한 앱",
        "sidebar_safest_vpns": "가장 안전한 VPN",
        "eyes_outside": "모든 Eyes 감시 동맹 밖 — 프라이버시 이점",
        "serving_users": "사용자 수:",
        "privacy_assessment": "개인정보 보호 평가",
        "sidebar_recently": "최근 분석",
        "sidebar_browse": "카테고리 탐색",
        "sidebar_popular_in": "인기",
        "vpn_logging_audited": "로깅 정책: 독립적으로 감사된 노로그 정책. 독립 감사 보고서에 따르면 {name}는 연결 로그, 브라우징 활동 또는 DNS 쿼리를 저장하지 않습니다.",
        "vpn_server_infra": "서버 인프라",
        "vpn_significant": "이는 비동맹 관할권의 VPN 제공업체가 의무적 데이터 보존법이나 정보 공유 협정의 적용을 받지 않기 때문에 중요합니다.",
        "vpn_outside_eyes": "파이브아이즈, 나인아이즈, 포틴아이즈 감시 동맹 밖",
        "vpn_jurisdiction": "관할권",
        "vpn_operates_under": "관할 하에 운영",
        "xlink_safest_crypto": "가장 안전한 암호화폐 거래소",
        "xlink_access_secure": "안전하게 도구에 접근",
        "xlink_secure_saas": "SaaS 로그인 보호",
        "xlink_protect_server": "서버 보호",
        "xlink_secure_passwords_desc": "계정 보호를 위해 비밀번호 관리자 사용",
        "xlink_secure_passwords": "비밀번호 보호",
        "xlink_add_vpn_av": "암호화된 브라우징을 위해 VPN 추가",
        "xlink_add_malware_desc": "키로거 및 자격 증명 도용 방지",
        "xlink_add_malware": "악성코드 보호 추가",
        "xlink_add_av_vpn": "VPN과 함께 백신으로 보안 완성",
        "xlink_add_av": "백신 보호 추가",
        "xlink_add_vpn_pm": "비밀번호 관리자에 VPN 추가",
        "xlink_add_pm_vpn": "완전한 보호를 위해 VPN에 비밀번호 관리자 추가",
        "xlink_complete_security": "보안 완성",
        "xlink_complete_privacy": "프라이버시 설정 완성",
        "type_steam": "Steam 게임",
        "type_android": "Android 앱",
        "type_website_builder": "웹사이트 빌더",
        "type_crypto": "암호화폐 거래소",
        "type_password_manager": "비밀번호 관리자",
        "type_antivirus": "백신 소프트웨어",
        "type_hosting": "웹 호스팅",
        "type_saas": "SaaS 플랫폼",
        "type_npm": "npm 패키지",
        "type_vpn": "VPN 서비스",
        "based_on_dims": "{dims}개의 독립적으로 측정된 데이터 차원 기반",
        "with_trust_score": "Nerq 신뢰 점수 {score}/100 ({grade})",
        "is_a_type": "은(는) {type}입니다",
        "rec_wordpress": "WordPress 사용에 권장",
        "rec_use": "사용에 권장",
        "rec_play": "플레이에 권장",
        "rec_general": "일반적인 사용에 권장",
        "rec_production": "프로덕션 사용에 권장",
        "rec_privacy": "개인정보 보호를 중시하는 사용에 권장",
        "ans_trust": "{name}의 Nerq 신뢰 점수는 {score}/100이며 {grade} 등급입니다. 이 점수는 보안, 유지보수, 커뮤니티 채택을 포함한 {dims}개의 독립적으로 측정된 차원을 기반으로 합니다.",
        "ans_findings_strong": "{name}의 가장 강한 신호는 {signal}이며 {signal_score}/100입니다.",
        "ans_no_vulns": "알려진 취약점이 감지되지 않았습니다.",
        "ans_has_vulns": "{count}개의 알려진 취약점이 확인되었습니다.",
        "ans_verified": "Nerq 인증 임계값 70+를 충족합니다.",
        "ans_not_verified": "아직 Nerq 인증 임계값 70+에 도달하지 못했습니다.",
        "data_sourced": "{sources}에서 수집된 데이터. 마지막 업데이트: {date}.",
        "score_based_dims": "{dims} 기반 점수.",
        "yes_safe_short": "네, 안전하게 사용할 수 있습니다.",
        "title_safe": "{name}은(는) 안전한가요? 독립적인 신뢰 및 보안 분석 {year} | Nerq",
        "title_safe_visit": "{name}은(는) 방문하기 안전한가요? 보안 점수 {year} &amp; 여행 가이드 | Nerq",
        "title_charity": "{name}은(는) 신뢰할 수 있는 자선단체인가요? 신뢰 분석 {year} | Nerq",
        "title_ingredient": "{name}은(는) 안전한가요? 건강 &amp; 안전 분석 {year} | Nerq",
        "h1_safe": "{name}은(는) 안전한가요?",
        "h1_safe_visit": "{name}은(는) 방문하기 안전한가요?",
        "h1_trustworthy_charity": "{name}은(는) 신뢰할 수 있는 자선단체인가요?",
        "h1_ingredient_safe": "{name}은(는) 안전한가요?",
        "breadcrumb_safety": "보안 보고서",
        "security_analysis": "보안 분석", "privacy_report": "개인정보 보고서", "similar_in_registry": "신뢰 점수별 유사 {registry}", "see_all_best": "가장 안전한 {registry} 모두 보기",
        "pv_grade": "{grade} 등급", "pv_body": "{dims}개의 신뢰 차원 분석 결과, {verdict}으로 평가됩니다.", "pv_vulns": "{count}개의 알려진 취약점 포함", "pv_updated": "마지막 업데이트: {date}.", "pv_safe": "안전한 것으로 간주됨", "pv_generally_safe": "대체로 안전하지만 일부 우려 사항이 있음", "pv_notable_concerns": "주목할 만한 보안 우려가 있음", "pv_significant_risks": "심각한 보안 위험이 있음", "pv_unsafe": "안전하지 않은 것으로 간주됨",
        "h2q_trust_score": "{name}의 신뢰 점수는?", "h2q_key_findings": "{name}의 주요 보안 발견 사항은?", "h2q_details": "{name}은(는) 무엇이며 누가 관리하나요?",
        "trust_score_breakdown": "신뢰 점수 세부 정보",
        "safety_score_breakdown": "보안 점수 세부 정보",
        "key_findings": "주요 발견",
        "key_safety_findings": "주요 보안 발견",
        "details": "세부 정보",
        "detailed_score_analysis": "상세 점수 분석",
        "faq": "자주 묻는 질문",
        "community_reviews": "커뮤니티 리뷰",
        "regulatory_compliance": "규정 준수",
        "how_calculated": "이 점수를 어떻게 계산했나요",
        "popular_alternatives": "{category}의 인기 대안",
        "safer_alternatives": "더 안전한 대안",
        "across_platforms": "다른 플랫폼의 {name}",
        "safety_guide": "보안 가이드: {name}",
        "what_is": "{name}이(가) 무엇인가요?",
        "key_concerns": "{type}의 주요 보안 문제",
        "how_to_verify": "안전성 확인 방법",
        "trust_assessment": "신뢰 평가",
        "what_data_collect": "{name}은(는) 어떤 데이터를 수집하나요?",
        "is_secure": "{name}은(는) 안전한가요?",
        "is_safe_visit": "{name}은(는) 방문하기 안전한가요?",
        "is_legit_charity": "{name}은(는) 합법적인 자선단체인가요?",
        "crime_safety": "{name}의 범죄 및 안전",
        "financial_transparency": "{name}의 재정 투명성",
        "yes_safe": "네, {name}은(는) 사용하기에 안전합니다.",
        "use_caution": "{name}을(를) 주의하며 사용하세요.",
        "exercise_caution": "{name}에 대해 주의하세요.",
        "significant_concerns": "{name}에 심각한 신뢰 문제가 있습니다.",
        "safe": "안전함",
        "use_caution_short": "주의",
        "avoid": "피하기",
        "passes_threshold": "Nerq 인증 기준 충족",
        "below_threshold": "Nerq 인증 기준 미달",
        "significant_gaps": "심각한 신뢰 격차 발견",
        "meets_threshold_detail": "보안, 유지보수 및 커뮤니티 채택에서 강력한 신호로 Nerq 신뢰 기준을 충족합니다",
        "not_reached_threshold": "아직 Nerq 신뢰 기준(70+)에 도달하지 못했습니다.",
        "score_based_on": "이 점수는 보안, 유지보수, 커뮤니티 및 품질 신호의 자동 분석을 기반으로 합니다.",
        "recommended_production": "프로덕션 사용 권장",
        "last_analyzed": "최종 분석:",
        "author_label": "개발자",
        "category_label": "카테고리",
        "stars_label": "스타",
        "global_rank_label": "글로벌 순위",
        "source_label": "출처",
        "machine_readable": "기계 판독 가능 데이터 (JSON)",
        "full_analysis": "전체 분석:",
        "privacy_report": "{name} 개인정보 보고서",
        "security_report": "{name} 보안 보고서",
        "write_review": "리뷰 작성",
        "no_reviews": "아직 리뷰가 없습니다.",
        "be_first_review": "{name}의 첫 번째 리뷰를 작성하세요",
        "security": "보안",
        "compliance": "규정 준수",
        "maintenance": "유지보수",
        "documentation": "문서화",
        "popularity": "인기도",
        "overall_trust": "전체 신뢰도",
        "privacy": "개인정보",
        "reliability": "신뢰성",
        "transparency": "투명성",
        "disclaimer": "Nerq 신뢰 점수는 공개적으로 사용 가능한 신호를 기반으로 한 자동 평가입니다. 추천이나 보증이 아닙니다. 항상 직접 확인하세요.",
        "same_developer": "다른 레지스트리의 동일 개발자/회사:",
        "methodology_entities": "Nerq는 동일한 방법론을 사용하여 26개 레지스트리에서 750만 개 이상의 엔터티를 분석하여 엔터티 간 직접 비교를 가능하게 합니다.",
        "scores_updated_continuously": "새로운 데이터가 제공되면 점수가 지속적으로 업데이트됩니다.",
        "strongest_signal": "가장 강력한 신호:",
        "in_category": "{category} 카테고리에서,",
        "check_back_soon": "곧 다시 확인해 주세요",
        "safe_solo": "{name}은(는) 혼자 여행하기에 안전한가요?",
        "safe_women": "{name}은(는) 여성에게 안전한가요?",
        "safe_lgbtq": "{name}은(는) LGBTQ+ 여행자에게 안전한가요?",
        "safe_families": "{name}은(는) 가족에게 안전한가요?",
        "safe_visit_now": "{name}은(는) 지금 방문하기 안전한가요?",
        "tap_water_safe": "{name}에서 수돗물을 마셔도 안전한가요?",
        "need_vaccinations": "{name}을(를) 위해 예방접종이 필요한가요?",
        "what_are_side_effects": "{name}의 부작용은 무엇인가요?",
        "what_are_safer_alts": "{name}의 더 안전한 대안은 무엇인가요?",
        "interact_medications": "{name}은(는) 약물과 상호작용하나요?",
        "cause_irritation": "{name}이(가) 피부 자극을 일으킬 수 있나요?",
        "health_disclaimer": "이 정보는 교육 목적으로만 제공되며 의료 조언이 아닙니다. 건강 결정을 내리기 전에 자격을 갖춘 의료 전문가와 상담하세요.",
        "not_analyzed_title": "{name} — 아직 분석되지 않음 | Nerq",
        "not_analyzed_h1": "{name} — 아직 분석되지 않음",
        "not_analyzed_msg": "Nerq는 아직 {name}에 대한 신뢰 분석을 수행하지 않았습니다. 750만 개 이상의 엔터티를 분석하고 있습니다 — 곧 추가될 수 있습니다.",
        "not_analyzed_meanwhile": "그동안 다음을 할 수 있습니다:",
        "not_analyzed_search": "다른 철자로 검색해 보세요",
        "not_analyzed_api": "API를 직접 확인하세요",
        "not_analyzed_browse": "이미 분석한 엔터티를 둘러보세요",
        "not_analyzed_no_score": "이 페이지에는 아직 이 엔터티를 분석하지 않았기 때문에 신뢰 점수가 없습니다.",
        "not_analyzed_no_fabricate": "Nerq는 절대로 점수를 조작하지 않습니다. 이 엔터티가 포함되어야 한다고 생각하시면 향후 업데이트에서 나타날 수 있습니다.",
    },
    "it": {
        "vpn_outside_eyes": "al di fuori delle alleanze di sorveglianza Five Eyes, Nine Eyes e Fourteen Eyes",
        "faq_q3_alts": "Quali sono alternative più sicure a {name}?",
        "faq_q4_log": "{name} registra i miei dati?",
        "faq_q4_update": "Con che frequenza viene aggiornato il punteggio di {name}?",
        "faq_q5_vs": "{name} vs alternative: quale è più sicuro?",
        "faq_q5_regulated": "Posso usare {name} in un ambiente regolamentato?",
        "vpn_sec_score": "Punteggio di sicurezza",
        "privacy_score_label": "Punteggio di privacy",
        "strong": "forte",
        "moderate": "moderato",
        "weak": "debole",
        "actively_maintained": "mantenuto attivamente",
        "moderately_maintained": "moderatamente mantenuto",
        "low_maintenance": "bassa attività di manutenzione",
        "well_documented": "ben documentato",
        "partial_documentation": "documentazione parziale",
        "limited_documentation": "documentazione limitata",
        "community_adoption": "adozione comunitaria",
        "faq_q4_vuln": "{name} ha vulnerabilità note?",
        "faq_q4_kids": "{name} è sicuro per i bambini?",
        "faq_q4_perms": "Quali permessi richiede {name}?",
        "faq_q4_maintained": "{name} viene mantenuto attivamente?",
        "faq_a4_vuln": "Nerq verifica {name} contro NVD, OSV.dev e database di vulnerabilità. Punteggio di sicurezza attuale: {sec_score}.",
        "faq_a4_kids": "{name} ha un punteggio Nerq di {score}/100. I genitori dovrebbero consultare il rapporto completo.",
        "faq_a4_perms": "Verificare attentamente i permessi richiesti da {name}. Punteggio di fiducia: {score}/100.",
        "faq_a4_maintained": "Punteggio di manutenzione di {name}: {maint_score}. Controllare l'attività recente del repository.",
        "faq_a5_verified": "{name} soddisfa la soglia di verifica Nerq (70+). Sicuro per l'uso in produzione.",
        "faq_a5_not_verified": "{name} non ha raggiunto la soglia di verifica Nerq di 70. Si consiglia ulteriore verifica.",
        "more_being_analyzed": "altri {type} sono in fase di analisi — ricontrolla presto.",
        "vpn_jurisdiction": "giurisdizione",
        "vpn_operates_under": "opera sotto",
        "xlink_add_av_vpn": "Completa la sicurezza con antivirus e VPN",
        "xlink_add_av": "Aggiungi protezione antivirus",
        "xlink_add_pm_vpn": "Aggiungi un gestore di password alla VPN",
        "xlink_complete_security": "Completa la tua sicurezza",
        "xlink_complete_privacy": "Completa la tua privacy",
        "is_a_type": "è un {type}",
        "rec_privacy": "raccomandato per un uso attento alla privacy",
        "ans_trust": "{name} ha un Nerq Trust Score di {score}/100 con voto {grade}. Questo punteggio si basa su {dims} dimensioni misurate indipendentemente, tra cui sicurezza, manutenzione e adozione della community.",
        "ans_findings_strong": "Il segnale più forte di {name} è {signal} a {signal_score}/100.",
        "ans_no_vulns": "Non sono state rilevate vulnerabilità note.",
        "title_safe": "{name} è sicuro? Analisi indipendente di fiducia e sicurezza {year} | Nerq",
        "title_safe_visit": "È sicuro visitare {name}? Punteggio di sicurezza {year} &amp; Guida di viaggio | Nerq",
        "title_charity": "{name} è un ente di beneficenza affidabile? Analisi di fiducia {year} | Nerq",
        "title_ingredient": "{name} è sicuro? Analisi salute &amp; sicurezza {year} | Nerq",
        "h1_safe": "{name} è sicuro?",
        "h1_safe_visit": "È sicuro visitare {name}?",
        "h1_trustworthy_charity": "{name} è un ente di beneficenza affidabile?",
        "h1_ingredient_safe": "{name} è sicuro?",
        "breadcrumb_safety": "Report di sicurezza",
        "security_analysis": "Analisi di Sicurezza", "privacy_report": "Report sulla Privacy", "similar_in_registry": "{registry} simili per Punteggio di Fiducia", "see_all_best": "Vedi tutti i {registry} più sicuri",
        "pv_grade": "Grado {grade}", "pv_body": "Sulla base dell'analisi di {dims} dimensioni di fiducia, è {verdict}.", "pv_vulns": "con {count} vulnerabilità note", "pv_updated": "Ultimo aggiornamento: {date}.", "pv_safe": "considerato sicuro da usare", "pv_generally_safe": "generalmente sicuro ma con alcune preoccupazioni", "pv_notable_concerns": "ha preoccupazioni di sicurezza notevoli", "pv_significant_risks": "ha rischi di sicurezza significativi", "pv_unsafe": "considerato non sicuro",
        "h2q_trust_score": "Qual è il punteggio di fiducia di {name}?", "h2q_key_findings": "Quali sono i risultati di sicurezza chiave per {name}?", "h2q_details": "Cos'è {name} e chi lo mantiene?",
        "trust_score_breakdown": "Dettagli punteggio di fiducia",
        "safety_score_breakdown": "Dettagli punteggio di sicurezza",
        "key_findings": "Risultati principali",
        "key_safety_findings": "Risultati principali sulla sicurezza",
        "details": "Dettagli",
        "detailed_score_analysis": "Analisi dettagliata del punteggio",
        "faq": "Domande frequenti",
        "community_reviews": "Recensioni della comunità",
        "regulatory_compliance": "Conformità normativa",
        "how_calculated": "Come abbiamo calcolato questo punteggio",
        "popular_alternatives": "Alternative popolari in {category}",
        "safer_alternatives": "Alternative più sicure",
        "across_platforms": "{name} su altre piattaforme",
        "safety_guide": "Guida alla sicurezza: {name}",
        "what_is": "Cos'è {name}?",
        "key_concerns": "Principali problemi di sicurezza per {type}",
        "how_to_verify": "Come verificare la sicurezza",
        "trust_assessment": "Valutazione della fiducia",
        "what_data_collect": "Quali dati raccoglie {name}?",
        "is_secure": "{name} è sicuro?",
        "is_safe_visit": "È sicuro visitare {name}?",
        "is_legit_charity": "{name} è un ente di beneficenza legittimo?",
        "crime_safety": "Criminalità e sicurezza a {name}",
        "financial_transparency": "Trasparenza finanziaria di {name}",
        "yes_safe": "Sì, {name} è sicuro da usare.",
        "use_caution": "Usa {name} con cautela.",
        "exercise_caution": "Fai attenzione con {name}.",
        "significant_concerns": "{name} presenta problemi significativi di fiducia.",
        "safe": "Sicuro",
        "use_caution_short": "Cautela",
        "avoid": "Da evitare",
        "passes_threshold": "Soddisfa la soglia verificata Nerq",
        "below_threshold": "Sotto la soglia verificata Nerq",
        "significant_gaps": "Rilevate lacune significative nella fiducia",
        "meets_threshold_detail": "Soddisfa la soglia di fiducia Nerq con segnali forti in sicurezza, manutenzione e adozione della comunità",
        "not_reached_threshold": "e non ha ancora raggiunto la soglia di fiducia Nerq (70+).",
        "score_based_on": "Questo punteggio si basa sull'analisi automatizzata dei segnali di sicurezza, manutenzione, comunità e qualità.",
        "recommended_production": "Raccomandato per l'uso in produzione",
        "last_analyzed": "Ultima analisi:",
        "author_label": "Autore",
        "category_label": "Categoria",
        "stars_label": "Stelle",
        "global_rank_label": "Classifica globale",
        "source_label": "Fonte",
        "machine_readable": "Dati leggibili dalle macchine (JSON)",
        "full_analysis": "Analisi completa:",
        "privacy_report": "Report sulla privacy di {name}",
        "security_report": "Report di sicurezza di {name}",
        "write_review": "Scrivi una recensione",
        "no_reviews": "Ancora nessuna recensione.",
        "be_first_review": "Sii il primo a recensire {name}",
        "security": "Sicurezza",
        "compliance": "Conformità",
        "maintenance": "Manutenzione",
        "documentation": "Documentazione",
        "popularity": "Popolarità",
        "overall_trust": "Fiducia complessiva",
        "privacy": "Privacy",
        "reliability": "Affidabilità",
        "transparency": "Trasparenza",
        "disclaimer": "I punteggi di fiducia Nerq sono valutazioni automatizzate basate su segnali disponibili pubblicamente. Non costituiscono raccomandazioni o garanzie. Effettua sempre la tua verifica personale.",
        "same_developer": "Stesso sviluppatore/azienda in altri registri:",
        "methodology_entities": "Nerq analizza oltre 7,5 milioni di entità in 26 registri utilizzando la stessa metodologia, consentendo il confronto diretto tra entità.",
        "scores_updated_continuously": "I punteggi vengono aggiornati continuamente quando sono disponibili nuovi dati.",
        "strongest_signal": "Segnale più forte:",
        "in_category": "Nella categoria {category},",
        "check_back_soon": "torna a controllare presto",
        "safe_solo": "{name} è sicuro per viaggiatori singoli?",
        "safe_women": "{name} è sicuro per le donne?",
        "safe_lgbtq": "{name} è sicuro per viaggiatori LGBTQ+?",
        "safe_families": "{name} è sicuro per le famiglie?",
        "safe_visit_now": "È sicuro visitare {name} adesso?",
        "tap_water_safe": "L'acqua del rubinetto a {name} è sicura da bere?",
        "need_vaccinations": "Ho bisogno di vaccinazioni per {name}?",
        "what_are_side_effects": "Quali sono gli effetti collaterali di {name}?",
        "what_are_safer_alts": "Quali sono le alternative più sicure a {name}?",
        "interact_medications": "{name} interagisce con i farmaci?",
        "cause_irritation": "{name} può causare irritazione cutanea?",
        "health_disclaimer": "Queste informazioni sono solo a scopo educativo e non costituiscono consulenza medica. Consultare un professionista sanitario qualificato prima di prendere decisioni sulla salute.",
        "not_analyzed_title": "{name} — Non ancora analizzato | Nerq",
        "not_analyzed_h1": "{name} — Non ancora analizzato",
        "not_analyzed_msg": "Nerq non ha ancora effettuato un'analisi di fiducia per {name}. Analizziamo oltre 7,5 milioni di entità — questa potrebbe essere aggiunta presto.",
        "not_analyzed_meanwhile": "Nel frattempo, puoi:",
        "not_analyzed_search": "Provare a cercare con un'ortografia diversa",
        "not_analyzed_api": "Verificare l'API direttamente",
        "not_analyzed_browse": "Sfogliare le entità che abbiamo già analizzato",
        "not_analyzed_no_score": "Questa pagina non contiene un punteggio di fiducia perché non abbiamo ancora analizzato questa entità.",
        "not_analyzed_no_fabricate": "Nerq non fabbrica mai valutazioni. Se ritieni che questa entità debba essere coperta, potrebbe apparire in un aggiornamento futuro.",
    },
    "vi": {
        "dim_popularity": "Độ phổ biến",
        "faq_q3_alts": "Các lựa chọn an toàn hơn {name} là gì?",
        "faq_q4_log": "{name} có ghi lại dữ liệu của tôi không?",
        "faq_q4_update": "Điểm an toàn của {name} được cập nhật bao lâu một lần?",
        "faq_q5_vs": "{name} so với các lựa chọn khác: cái nào an toàn hơn?",
        "faq_q5_regulated": "Tôi có thể sử dụng {name} trong môi trường được quản lý không?",
        "strong": "mạnh",
        "moderate": "trung bình",
        "weak": "yếu",
        "actively_maintained": "được duy trì tích cực",
        "moderately_maintained": "được duy trì vừa phải",
        "low_maintenance": "hoạt động bảo trì thấp",
        "well_documented": "được tài liệu hóa tốt",
        "partial_documentation": "tài liệu một phần",
        "limited_documentation": "tài liệu hạn chế",
        "community_adoption": "sự chấp nhận cộng đồng",
        "faq_q4_vuln": "{name} có lỗ hổng bảo mật đã biết không?",
        "faq_q4_kids": "{name} có an toàn cho trẻ em không?",
        "faq_q4_perms": "{name} cần những quyền gì?",
        "faq_q4_maintained": "{name} có được bảo trì tích cực không?",
        "faq_a4_vuln": "Nerq kiểm tra {name} với NVD, OSV.dev và cơ sở dữ liệu lỗ hổng. Điểm bảo mật hiện tại: {sec_score}.",
        "faq_a4_kids": "{name} có điểm Nerq {score}/100. Phụ huynh nên xem báo cáo đầy đủ.",
        "faq_a4_perms": "Xem xét cẩn thận các quyền được yêu cầu bởi {name}. Điểm tin cậy: {score}/100.",
        "faq_a4_maintained": "Điểm bảo trì {name}: {maint_score}. Kiểm tra hoạt động gần đây của kho lưu trữ.",
        "faq_a5_verified": "{name} đạt ngưỡng xác minh Nerq (70+). An toàn cho sử dụng.",
        "faq_a5_not_verified": "{name} chưa đạt ngưỡng xác minh Nerq 70. Khuyến nghị kiểm tra thêm.",
        "more_being_analyzed": "thêm {type} đang được phân tích — hãy quay lại sớm.",
        "dim_maintenance": "Bảo trì",
        "dim_security": "Bảo mật",
        "vpn_no_breaches": "Không có vi phạm dữ liệu đã biết liên quan đến dịch vụ này.",
        "vpn_audit_none": "{name} chưa công bố kết quả từ kiểm toán bảo mật độc lập. VPN đã được kiểm toán cung cấp đảm bảo cao hơn.",
        "vpn_audit_verified": "Kiểm toán bảo mật độc lập đã xác minh.",
        "vpn_audit_positive": "Theo báo cáo kiểm toán độc lập, {name} đã trải qua các cuộc kiểm toán bảo mật bên thứ ba. Đây là tín hiệu tích cực mạnh.",
        "vpn_proto": "Giao thức mã hóa chính: {proto}, được coi là tiêu chuẩn ngành cho kết nối VPN.",
        "vpn_sec_score": "Điểm bảo mật",
        "privacy_score_label": "Điểm quyền riêng tư",
        "sidebar_most_private": "Ứng dụng riêng tư nhất",
        "sidebar_safest_vpns": "VPN an toàn nhất",
        "audit_no": "{name} chưa công bố kiểm toán quyền riêng tư độc lập",
        "audit_yes": "{name} đã được kiểm toán độc lập để xác minh các tuyên bố về quyền riêng tư",
        "eyes_none": "không phải thành viên của các liên minh Five/Nine/Fourteen Eyes",
        "eyes_fourteen": "trong liên minh giám sát Fourteen Eyes",
        "eyes_nine": "trong liên minh giám sát Nine Eyes",
        "eyes_five": "trong liên minh giám sát Five Eyes",
        "eyes_outside": "nằm ngoài tất cả các liên minh giám sát Eyes — lợi thế về quyền riêng tư",
        "undisclosed_jurisdiction": "quyền tài phán không được tiết lộ",
        "serving_users": "Phục vụ",
        "privacy_assessment": "Đánh giá quyền riêng tư",
        "sidebar_recently": "Phân tích gần đây",
        "sidebar_browse": "Duyệt danh mục",
        "sidebar_popular_in": "Phổ biến trong",
        "ans_trust": "{name} có Điểm tin cậy Nerq là {score}/100 với xếp hạng {grade}. Điểm này dựa trên {dims} chiều dữ liệu được đo lường độc lập bao gồm bảo mật, bảo trì và sự chấp nhận của cộng đồng.",
        "ans_findings_strong": "Tín hiệu mạnh nhất của {name} là {signal} ở mức {signal_score}/100.",
        "ans_no_vulns": "Không phát hiện lỗ hổng đã biết.",
        "ans_has_vulns": "Đã phát hiện {count} lỗ hổng đã biết.",
        "ans_verified": "Đạt ngưỡng xác minh Nerq 70+.",
        "ans_not_verified": "Chưa đạt ngưỡng xác minh Nerq 70+.",
        "data_sourced": "Dữ liệu từ {sources}. Cập nhật lần cuối: {date}.",
        "score_based_dims": "Điểm dựa tr��n {dims}.",
        "yes_safe_short": "Có, nó an toàn để sử dụng.",
        "vpn_logging_audited": "Chính sách ghi nhật ký: chính sách không ghi nhật ký đã được kiểm toán độc lập. Theo báo cáo kiểm toán độc lập, {name} không lưu trữ nhật ký kết nối, hoạt động duyệt web hoặc truy vấn DNS.",
        "vpn_server_infra": "Hạ tầng máy chủ",
        "vpn_significant": "Điều này quan trọng vì các nhà cung cấp VPN tại các quốc gia ngoài liên minh không bắt buộc tuân thủ luật lưu giữ dữ liệu hay thỏa thuận chia sẻ tình báo.",
        "vpn_outside_eyes": "nằm ngoài các liên minh giám sát Five Eyes, Nine Eyes và Fourteen Eyes",
        "vpn_jurisdiction": "quyền tài phán",
        "vpn_operates_under": "hoạt động dưới",
        "xlink_safest_crypto": "Sàn giao dịch crypto an toàn nhất",
        "xlink_access_secure": "Truy cập công cụ an toàn",
        "xlink_secure_saas": "Bảo vệ đăng nhập SaaS",
        "xlink_protect_server": "Bảo vệ máy chủ của bạn",
        "xlink_secure_passwords_desc": "Sử dụng trình quản lý mật khẩu để bảo vệ tài khoản",
        "xlink_secure_passwords": "Bảo vệ mật khẩu của bạn",
        "xlink_add_vpn_av": "Thêm VPN để duyệt web được mã hóa",
        "xlink_add_malware_desc": "Bảo vệ chống keylogger và đánh cắp thông tin đăng nhập",
        "xlink_add_malware": "Thêm bảo vệ chống phần mềm độc hại",
        "xlink_add_av_vpn": "Hoàn thiện bảo mật với phần mềm diệt virus cùng VPN",
        "xlink_add_av": "Thêm bảo vệ diệt virus",
        "xlink_add_vpn_pm": "Thêm VPN vào trình quản lý mật khẩu",
        "xlink_add_pm_vpn": "Thêm trình quản lý mật khẩu vào VPN",
        "xlink_complete_security": "Hoàn thiện bảo mật",
        "xlink_complete_privacy": "Hoàn thiện bảo mật riêng tư",
        "type_wordpress": "plugin WordPress",
        "type_crates": "gói Rust",
        "type_pypi": "gói Python",
        "type_steam": "trò chơi Steam",
        "type_android": "ứng dụng Android",
        "type_website_builder": "trình tạo website",
        "type_crypto": "sàn giao dịch tiền điện tử",
        "type_password_manager": "trình quản lý mật khẩu",
        "type_antivirus": "phần mềm diệt virus",
        "type_hosting": "nhà cung cấp hosting",
        "type_saas": "nền tảng SaaS",
        "type_npm": "gói npm",
        "type_vpn": "dịch vụ VPN",
        "based_on_dims": "dựa trên {dims} chiều dữ liệu độc lập",
        "with_trust_score": "với Điểm tin cậy Nerq {score}/100 ({grade})",
        "is_a_type": "là một {type}",
        "rec_wordpress": "được khuyến nghị sử dụng trong WordPress",
        "rec_use": "được khuyến nghị sử dụng",
        "rec_play": "được khuyến nghị để chơi",
        "rec_general": "được khuyến nghị sử dụng chung",
        "rec_production": "được khuyến nghị sử dụng trong sản xuất",
        "rec_privacy": "được khuyến nghị cho người dùng quan tâm đến quyền riêng tư",
        "title_safe": "{name} có an toàn không? Phân tích tin cậy và bảo mật độc lập {year} | Nerq",
        "title_safe_visit": "{name} có an toàn để ghé thăm không? Điểm bảo mật {year} &amp; Hướng dẫn du lịch | Nerq",
        "title_charity": "{name} có phải tổ chức từ thiện đáng tin cậy không? Phân tích tin cậy {year} | Nerq",
        "title_ingredient": "{name} có an toàn không? Phân tích sức khỏe &amp; an toàn {year} | Nerq",
        "h1_safe": "{name} có an toàn không?",
        "h1_safe_visit": "{name} có an toàn để ghé thăm không?",
        "h1_trustworthy_charity": "{name} có phải tổ chức từ thiện đáng tin cậy không?",
        "h1_ingredient_safe": "{name} có an toàn không?",
        "breadcrumb_safety": "Báo cáo bảo mật",
        "security_analysis": "Phân tích Bảo mật", "privacy_report": "Báo cáo Quyền riêng tư", "similar_in_registry": "{registry} tương tự theo Điểm Tin cậy", "see_all_best": "Xem tất cả {registry} an toàn nhất",
        "pv_grade": "Hạng {grade}", "pv_body": "Dựa trên phân tích {dims} chiều tin cậy, được đánh giá là {verdict}.", "pv_vulns": "với {count} lỗ hổng đã biết", "pv_updated": "Cập nhật lần cuối: {date}.", "pv_safe": "an toàn để sử dụng", "pv_generally_safe": "nhìn chung an toàn nhưng có một số lo ngại", "pv_notable_concerns": "có những lo ngại bảo mật đáng chú ý", "pv_significant_risks": "có rủi ro bảo mật đáng kể", "pv_unsafe": "được coi là không an toàn",
        "h2q_trust_score": "Điểm tin cậy của {name} là bao nhiêu?", "h2q_key_findings": "Các phát hiện bảo mật chính của {name} là gì?", "h2q_details": "{name} là gì và ai duy trì nó?",
        "trust_score_breakdown": "Chi tiết điểm tin cậy",
        "safety_score_breakdown": "Chi tiết điểm bảo mật",
        "key_findings": "Phát hiện chính",
        "key_safety_findings": "Phát hiện bảo mật chính",
        "details": "Chi tiết",
        "detailed_score_analysis": "Phân tích điểm chi tiết",
        "faq": "Câu hỏi thường gặp",
        "community_reviews": "Đánh giá cộng đồng",
        "regulatory_compliance": "Tuân thủ quy định",
        "how_calculated": "Cách chúng tôi tính điểm này",
        "popular_alternatives": "Lựa chọn phổ biến trong {category}",
        "safer_alternatives": "Lựa chọn an toàn hơn",
        "across_platforms": "{name} trên các nền tảng khác",
        "safety_guide": "Hướng dẫn bảo mật: {name}",
        "what_is": "{name} là gì?",
        "key_concerns": "Vấn đề bảo mật chính cho {type}",
        "how_to_verify": "Cách xác minh an toàn",
        "trust_assessment": "Đánh giá tin cậy",
        "what_data_collect": "{name} thu thập dữ liệu gì?",
        "is_secure": "{name} có an toàn không?",
        "is_safe_visit": "{name} có an toàn để ghé thăm không?",
        "is_legit_charity": "{name} có phải tổ chức từ thiện hợp pháp không?",
        "crime_safety": "Tội phạm và an toàn tại {name}",
        "financial_transparency": "Minh bạch tài chính của {name}",
        "yes_safe": "Có, {name} an toàn để sử dụng.",
        "use_caution": "Sử dụng {name} một cách thận trọng.",
        "exercise_caution": "Hãy thận trọng với {name}.",
        "significant_concerns": "{name} có vấn đề tin cậy đáng kể.",
        "safe": "An toàn",
        "use_caution_short": "Thận trọng",
        "avoid": "Tránh",
        "passes_threshold": "Đạt ngưỡng xác minh Nerq",
        "below_threshold": "Dưới ngưỡng xác minh Nerq",
        "significant_gaps": "Phát hiện khoảng cách tin cậy đáng kể",
        "meets_threshold_detail": "Đạt ngưỡng tin cậy Nerq với tín hiệu mạnh về bảo mật, bảo trì và sự chấp nhận của cộng đồng",
        "not_reached_threshold": "và chưa đạt ngưỡng tin cậy Nerq (70+).",
        "score_based_on": "Điểm này dựa trên phân tích tự động các tín hiệu bảo mật, bảo trì, cộng đồng và chất lượng.",
        "recommended_production": "Khuyến nghị sử dụng trong sản xuất",
        "last_analyzed": "Phân tích gần nhất:",
        "author_label": "Nhà phát triển",
        "category_label": "Danh mục",
        "stars_label": "Sao",
        "global_rank_label": "Xếp hạng toàn cầu",
        "source_label": "Nguồn",
        "machine_readable": "Dữ liệu máy đọc được (JSON)",
        "full_analysis": "Phân tích đầy đủ:",
        "privacy_report": "Báo cáo quyền riêng tư {name}",
        "security_report": "Báo cáo bảo mật {name}",
        "write_review": "Viết đánh giá",
        "no_reviews": "Chưa có đánh giá nào.",
        "be_first_review": "Hãy là người đầu tiên đánh giá {name}",
        "security": "Bảo mật",
        "compliance": "Tuân thủ",
        "maintenance": "Bảo trì",
        "documentation": "Tài liệu",
        "popularity": "Độ phổ biến",
        "overall_trust": "Tin cậy tổng thể",
        "privacy": "Quyền riêng tư",
        "reliability": "Độ tin cậy",
        "transparency": "Minh bạch",
        "disclaimer": "Điểm tin cậy Nerq là đánh giá tự động dựa trên tín hiệu công khai. Đây không phải khuyến nghị hay bảo đảm. Hãy luôn tự xác minh.",
        "same_developer": "Cùng nhà phát triển/công ty trong các registry khác:",
        "methodology_entities": "Nerq phân tích hơn 7,5 triệu thực thể trong 26 registry bằng cùng một phương pháp, cho phép so sánh trực tiếp giữa các thực thể.",
        "scores_updated_continuously": "Điểm được cập nhật liên tục khi có dữ liệu mới.",
        "strongest_signal": "Tín hiệu mạnh nhất:",
        "in_category": "Trong danh mục {category},",
        "check_back_soon": "hãy kiểm tra lại sớm",
        "safe_solo": "{name} có an toàn cho du khách đi một mình không?",
        "safe_women": "{name} có an toàn cho phụ nữ không?",
        "safe_lgbtq": "{name} có an toàn cho du khách LGBTQ+ không?",
        "safe_families": "{name} có an toàn cho gia đình không?",
        "safe_visit_now": "{name} có an toàn để ghé thăm ngay bây giờ không?",
        "tap_water_safe": "Nước máy ở {name} có an toàn để uống không?",
        "need_vaccinations": "Tôi có cần tiêm phòng cho {name} không?",
        "what_are_side_effects": "Tác dụng phụ của {name} là gì?",
        "what_are_safer_alts": "Các lựa chọn an toàn hơn {name} là gì?",
        "interact_medications": "{name} có tương tác với thuốc không?",
        "cause_irritation": "{name} có thể gây kích ứng da không?",
        "health_disclaimer": "Thông tin này chỉ dành cho mục đích giáo dục và không phải lời khuyên y tế. Hãy tham khảo ý kiến chuyên gia y tế có trình độ trước khi đưa ra quyết định về sức khỏe.",
        "not_analyzed_title": "{name} — Chưa được phân tích | Nerq",
        "not_analyzed_h1": "{name} — Chưa được phân tích",
        "not_analyzed_msg": "Nerq chưa thực hiện phân tích tin cậy cho {name}. Chúng tôi phân tích hơn 7,5 triệu thực thể — mục này có thể được thêm sớm.",
        "not_analyzed_meanwhile": "Trong khi chờ đợi, bạn có thể:",
        "not_analyzed_search": "Thử tìm kiếm với chính tả khác",
        "not_analyzed_api": "Kiểm tra API trực tiếp",
        "not_analyzed_browse": "Duyệt các thực thể đã được phân tích",
        "not_analyzed_no_score": "Trang này không có điểm tin cậy vì chúng tôi chưa phân tích thực thể này.",
        "not_analyzed_no_fabricate": "Nerq không bao giờ bịa đặt điểm số. Nếu bạn cho rằng thực thể này cần được đánh giá, nó có thể xuất hiện trong bản cập nhật tương lai.",
    },
    "nl": {
        "vpn_sec_score": "Beveiligingsscore",
        "privacy_score_label": "Privacyscore",
        "vpn_outside_eyes": "buiten de Five Eyes, Nine Eyes en Fourteen Eyes surveillanceallianties",
        "faq_q3_alts": "Wat zijn veiligere alternatieven voor {name}?",
        "faq_q4_log": "Logt {name} mijn gegevens?",
        "faq_q4_update": "Hoe vaak wordt de beveiligingsscore van {name} bijgewerkt?",
        "faq_q5_vs": "{name} vs alternatieven: welke is veiliger?",
        "faq_q5_regulated": "Kan ik {name} gebruiken in een gereguleerde omgeving?",
        "faq_q4_vuln": "Heeft {name} bekende kwetsbaarheden?",
        "faq_q4_kids": "Is {name} veilig voor kinderen?",
        "faq_q4_perms": "Welke machtigingen heeft {name} nodig?",
        "faq_q4_maintained": "Wordt {name} actief onderhouden?",
        "faq_a4_vuln": "Nerq controleert {name} tegen NVD, OSV.dev en registerspecifieke kwetsbaarheidsdatabases. Huidige beveiligingsscore: {sec_score}.",
        "faq_a4_kids": "{name} heeft een Nerq-score van {score}/100. Ouders moeten het volledige rapport bekijken.",
        "faq_a4_perms": "Controleer de gevraagde machtigingen van {name} zorgvuldig. Vertrouwensscore: {score}/100.",
        "faq_a4_maintained": "{name} onderhoudsscore: {maint_score}. Controleer het repository op recente activiteit.",
        "faq_a5_verified": "{name} voldoet aan de Nerq-verificatiedrempel (70+). Veilig voor productiegebruik.",
        "faq_a5_not_verified": "{name} heeft de Nerq-verificatiedrempel van 70 niet bereikt. Extra controle aanbevolen.",
        "more_being_analyzed": "meer {type} worden geanalyseerd — kom binnenkort terug.",
        "strong": "sterk",
        "moderate": "matig",
        "weak": "zwak",
        "actively_maintained": "actief onderhouden",
        "moderately_maintained": "matig onderhouden",
        "low_maintenance": "lage onderhoudsactiviteit",
        "well_documented": "goed gedocumenteerd",
        "partial_documentation": "gedeeltelijke documentatie",
        "limited_documentation": "beperkte documentatie",
        "community_adoption": "gemeenschapsacceptatie",
        "vpn_jurisdiction": "jurisdictie",
        "vpn_operates_under": "opereert onder",
        "xlink_add_av_vpn": "Voltooi uw beveiliging met antivirus naast uw VPN",
        "xlink_add_av": "Antivirusbescherming toevoegen",
        "xlink_add_pm_vpn": "Voeg een wachtwoordmanager toe aan uw VPN",
        "xlink_complete_security": "Voltooi uw beveiliging",
        "xlink_complete_privacy": "Voltooi uw privacy",
        "is_a_type": "is een {type}",
        "rec_privacy": "aanbevolen voor privacybewust gebruik",
        "ans_trust": "{name} heeft een Nerq Trust Score van {score}/100 met het cijfer {grade}. Deze score is gebaseerd op {dims} onafhankelijk gemeten dimensies, waaronder beveiliging, onderhoud en community-adoptie.",
        "ans_findings_strong": "Het sterkste signaal van {name} is {signal} met {signal_score}/100.",
        "ans_no_vulns": "Er zijn geen bekende kwetsbaarheden gedetecteerd.",
        "title_safe": "Is {name} veilig? Onafhankelijke vertrouwens- en beveiligingsanalyse {year} | Nerq",
        "title_safe_visit": "Is {name} veilig om te bezoeken? Beveiligingsscore {year} &amp; Reisgids | Nerq",
        "title_charity": "Is {name} een betrouwbare liefdadigheidsinstelling? Vertrouwensanalyse {year} | Nerq",
        "title_ingredient": "Is {name} veilig? Gezondheids- &amp; veiligheidsanalyse {year} | Nerq",
        "h1_safe": "Is {name} veilig?",
        "h1_safe_visit": "Is {name} veilig om te bezoeken?",
        "h1_trustworthy_charity": "Is {name} een betrouwbare liefdadigheidsinstelling?",
        "h1_ingredient_safe": "Is {name} veilig?",
        "breadcrumb_safety": "Beveiligingsrapporten",
        "security_analysis": "Beveiligingsanalyse", "privacy_report": "Privacyrapport", "similar_in_registry": "Vergelijkbare {registry} op Vertrouwensscore", "see_all_best": "Bekijk alle veiligste {registry}",
        "pv_grade": "{grade}-beoordeling", "pv_body": "Op basis van analyse van {dims} vertrouwensdimensies wordt het beschouwd als {verdict}.", "pv_vulns": "met {count} bekende kwetsbaarheden", "pv_updated": "Laatst bijgewerkt: {date}.", "pv_safe": "veilig in gebruik", "pv_generally_safe": "over het algemeen veilig maar met enkele zorgen", "pv_notable_concerns": "heeft opmerkelijke beveiligingszorgen", "pv_significant_risks": "heeft aanzienlijke beveiligingsrisico's", "pv_unsafe": "als onveilig beschouwd",
        "h2q_trust_score": "Wat is de vertrouwensscore van {name}?", "h2q_key_findings": "Wat zijn de belangrijkste beveiligingsbevindingen voor {name}?", "h2q_details": "Wat is {name} en wie onderhoudt het?",
        "trust_score_breakdown": "Vertrouwensscore details",
        "safety_score_breakdown": "Beveiligingsscore details",
        "key_findings": "Belangrijkste bevindingen",
        "key_safety_findings": "Belangrijkste beveiligingsbevindingen",
        "details": "Details",
        "detailed_score_analysis": "Gedetailleerde score-analyse",
        "faq": "Veelgestelde vragen",
        "community_reviews": "Beoordelingen van de gemeenschap",
        "regulatory_compliance": "Naleving van regelgeving",
        "how_calculated": "Hoe we deze score hebben berekend",
        "popular_alternatives": "Populaire alternatieven in {category}",
        "safer_alternatives": "Veiligere alternatieven",
        "across_platforms": "{name} op andere platforms",
        "safety_guide": "Beveiligingsgids: {name}",
        "what_is": "Wat is {name}?",
        "key_concerns": "Belangrijkste beveiligingsproblemen voor {type}",
        "how_to_verify": "Hoe de veiligheid te verifiëren",
        "trust_assessment": "Vertrouwensbeoordeling",
        "what_data_collect": "Welke gegevens verzamelt {name}?",
        "is_secure": "Is {name} veilig?",
        "is_safe_visit": "Is {name} veilig om te bezoeken?",
        "is_legit_charity": "Is {name} een legitieme liefdadigheidsinstelling?",
        "crime_safety": "Criminaliteit en veiligheid in {name}",
        "financial_transparency": "Financiële transparantie van {name}",
        "yes_safe": "Ja, {name} is veilig om te gebruiken.",
        "use_caution": "Gebruik {name} met voorzichtigheid.",
        "exercise_caution": "Wees voorzichtig met {name}.",
        "significant_concerns": "{name} heeft aanzienlijke vertrouwensproblemen.",
        "safe": "Veilig",
        "use_caution_short": "Voorzichtigheid",
        "avoid": "Vermijden",
        "passes_threshold": "Voldoet aan de geverifieerde drempel van Nerq",
        "below_threshold": "Onder de geverifieerde drempel van Nerq",
        "significant_gaps": "Aanzienlijke vertrouwenslacunes gedetecteerd",
        "meets_threshold_detail": "Voldoet aan de vertrouwensdrempel van Nerq met sterke signalen op het gebied van beveiliging, onderhoud en gemeenschapsacceptatie",
        "not_reached_threshold": "en heeft de vertrouwensdrempel van Nerq (70+) nog niet bereikt.",
        "score_based_on": "Deze score is gebaseerd op geautomatiseerde analyse van beveiligings-, onderhouds-, gemeenschaps- en kwaliteitssignalen.",
        "recommended_production": "Aanbevolen voor productiegebruik",
        "last_analyzed": "Laatst geanalyseerd:",
        "author_label": "Ontwikkelaar",
        "category_label": "Categorie",
        "stars_label": "Sterren",
        "global_rank_label": "Wereldwijde ranglijst",
        "source_label": "Bron",
        "machine_readable": "Machineleesbare gegevens (JSON)",
        "full_analysis": "Volledige analyse:",
        "privacy_report": "{name} Privacyrapport",
        "security_report": "{name} Beveiligingsrapport",
        "write_review": "Schrijf een beoordeling",
        "no_reviews": "Nog geen beoordelingen.",
        "be_first_review": "Wees de eerste die {name} beoordeelt",
        "security": "Beveiliging",
        "compliance": "Naleving",
        "maintenance": "Onderhoud",
        "documentation": "Documentatie",
        "popularity": "Populariteit",
        "overall_trust": "Algeheel vertrouwen",
        "privacy": "Privacy",
        "reliability": "Betrouwbaarheid",
        "transparency": "Transparantie",
        "disclaimer": "Nerq-vertrouwensscores zijn geautomatiseerde beoordelingen op basis van openbaar beschikbare signalen. Ze vormen geen aanbeveling of garantie. Voer altijd uw eigen verificatie uit.",
        "same_developer": "Dezelfde ontwikkelaar/bedrijf in andere registers:",
        "methodology_entities": "Nerq analyseert meer dan 7,5 miljoen entiteiten in 26 registers met dezelfde methodologie, waardoor directe vergelijking tussen entiteiten mogelijk is.",
        "scores_updated_continuously": "Scores worden continu bijgewerkt naarmate er nieuwe gegevens beschikbaar komen.",
        "strongest_signal": "Sterkste signaal:",
        "in_category": "In de categorie {category},",
        "check_back_soon": "kom snel terug",
        "safe_solo": "Is {name} veilig voor alleen reizende reizigers?",
        "safe_women": "Is {name} veilig voor vrouwen?",
        "safe_lgbtq": "Is {name} veilig voor LGBTQ+ reizigers?",
        "safe_families": "Is {name} veilig voor gezinnen?",
        "safe_visit_now": "Is {name} nu veilig om te bezoeken?",
        "tap_water_safe": "Is het kraanwater in {name} veilig om te drinken?",
        "need_vaccinations": "Heb ik vaccinaties nodig voor {name}?",
        "what_are_side_effects": "Wat zijn de bijwerkingen van {name}?",
        "what_are_safer_alts": "Wat zijn veiligere alternatieven voor {name}?",
        "interact_medications": "Heeft {name} wisselwerkingen met medicijnen?",
        "cause_irritation": "Kan {name} huidirritatie veroorzaken?",
        "health_disclaimer": "Deze informatie is uitsluitend bedoeld voor educatieve doeleinden en vormt geen medisch advies. Raadpleeg een gekwalificeerde zorgverlener voordat u gezondheidsbeslissingen neemt.",
        "not_analyzed_title": "{name} — Nog niet geanalyseerd | Nerq",
        "not_analyzed_h1": "{name} — Nog niet geanalyseerd",
        "not_analyzed_msg": "Nerq heeft nog geen vertrouwensanalyse uitgevoerd voor {name}. We analyseren meer dan 7,5 miljoen entiteiten — deze kan binnenkort worden toegevoegd.",
        "not_analyzed_meanwhile": "In de tussentijd kunt u:",
        "not_analyzed_search": "Probeer te zoeken met een andere spelling",
        "not_analyzed_api": "De API rechtstreeks controleren",
        "not_analyzed_browse": "Bekijk entiteiten die we al hebben geanalyseerd",
        "not_analyzed_no_score": "Deze pagina bevat geen vertrouwensscore omdat we deze entiteit nog niet hebben geanalyseerd.",
        "not_analyzed_no_fabricate": "Nerq vervalst nooit beoordelingen. Als u denkt dat deze entiteit moet worden gedekt, kan deze in een toekomstige update verschijnen.",
    },
    "sv": {
        "dim_popularity": "Popularitet",
        "faq_q3_alts": "Vilka är säkrare alternativ till {name}?",
        "faq_q4_log": "Loggar {name} min data?",
        "faq_q4_update": "Hur ofta uppdateras {name}s säkerhetspoäng?",
        "faq_q5_vs": "{name} mot alternativ: vilken är säkrare?",
        "faq_q5_regulated": "Kan jag använda {name} i en reglerad miljö?",
        "faq_q4_vuln": "Har {name} kända sårbarheter?",
        "faq_q4_kids": "Är {name} säkert för barn?",
        "faq_q4_perms": "Vilka behörigheter behöver {name}?",
        "faq_q4_maintained": "Underhålls {name} aktivt?",
        "faq_a4_vuln": "Nerq kontrollerar {name} mot NVD, OSV.dev och registerspecifika sårbarhetsdatabaser. Aktuell säkerhetspoäng: {sec_score}.",
        "faq_a4_kids": "{name} har en Nerq-poäng på {score}/100. Föräldrar bör granska den fullständiga rapporten.",
        "faq_a4_perms": "Granska {name}s begärda behörigheter noggrant. Förtroendepoäng: {score}/100.",
        "faq_a4_maintained": "{name} underhållspoäng: {maint_score}. Kontrollera repositoriet för senaste aktivitet.",
        "faq_a5_verified": "{name} uppfyller Nerqs verifieringsgräns (70+). Säkert för produktionsanvändning.",
        "faq_a5_not_verified": "{name} har inte nått Nerqs verifieringsgräns på 70. Ytterligare granskning rekommenderas.",
        "more_being_analyzed": "fler {type} analyseras — kom tillbaka snart.",
        "strong": "stark",
        "moderate": "måttlig",
        "weak": "svag",
        "actively_maintained": "aktivt underhållen",
        "moderately_maintained": "måttligt underhållen",
        "low_maintenance": "låg underhållsaktivitet",
        "well_documented": "väl dokumenterad",
        "partial_documentation": "partiell dokumentation",
        "limited_documentation": "begränsad dokumentation",
        "community_adoption": "community-antagande",
        "dim_maintenance": "Underhåll",
        "dim_security": "Säkerhet",
        "vpn_no_breaches": "Inga kända dataintrång kopplade till denna tjänst.",
        "vpn_audit_none": "{name} har inte publicerat resultat från en oberoende säkerhetsgranskning. Även om detta inte indikerar ett säkerhetsproblem ger granskade VPN-tjänster högre säkerhet.",
        "vpn_audit_verified": "Oberoende säkerhetsgranskning verifierad.",
        "vpn_audit_positive": "Enligt oberoende granskningsrapporter har {name} genomgått tredjepartsrevisioner som verifierar dess infrastruktur och no-logs-påståenden. Detta är en stark positiv signal — de flesta VPN-leverantörer har inte granskats oberoende.",
        "vpn_proto": "Primärt krypteringsprotokoll: {proto}, vilket anses vara branschstandard för VPN-anslutningar.",
        "vpn_sec_score": "Säkerhetspoäng",
        "privacy_score_label": "Integritetspoäng",
        "sidebar_most_private": "Mest privata appar",
        "sidebar_safest_vpns": "Säkraste VPN",
        "audit_no": "{name} har inte publicerat en oberoende integritetsgranskning",
        "audit_yes": "{name} har granskats av oberoende part för att verifiera sina integritetsanspråk",
        "eyes_none": "inte medlem i Five/Nine/Fourteen Eyes-allianserna",
        "eyes_fourteen": "inom Fourteen Eyes-övervakningsalliansen",
        "eyes_nine": "inom Nine Eyes-övervakningsalliansen",
        "eyes_five": "inom Five Eyes-övervakningsalliansen",
        "eyes_outside": "utanför alla Eyes-övervakningsallianser — en integritetsfördel",
        "undisclosed_jurisdiction": "en okänd jurisdiktion",
        "serving_users": "Betjänar",
        "privacy_assessment": "Integritetsbedömning",
        "sidebar_recently": "Nyligen analyserade",
        "sidebar_browse": "Bläddra bland kategorier",
        "sidebar_popular_in": "Populära inom",
        "vpn_logging_audited": "Loggningspolicy: oberoende granskad ingen-logg-policy. Enligt oberoende granskningsrapporter lagrar {name} inte anslutningsloggar, surfaktivitet eller DNS-förfrågningar.",
        "vpn_server_infra": "Serverinfrastruktur",
        "vpn_significant": "Detta är viktigt eftersom VPN-leverantörer i icke-allierade jurisdiktioner inte omfattas av obligatoriska datalagringslagar eller underrättelsesamarbetsavtal.",
        "vpn_outside_eyes": "utanför Five Eyes, Nine Eyes och Fourteen Eyes övervakningsallianserna",
        "vpn_jurisdiction": "jurisdiktion",
        "vpn_operates_under": "verkar under",
        "xlink_av_desc": "Oberoende antivirusrankning baserad på AV-TEST",
        "xlink_safest_av": "Säkraste antivirusprogram",
        "xlink_hosting_desc": "Oberoende hostingleverantörsrankning",
        "xlink_safest_hosting": "Säkraste webbhosting",
        "xlink_crypto_desc": "Oberoende kryptobörssäkerhetsrankning",
        "xlink_safest_crypto": "Säkraste kryptobörser",
        "xlink_access_secure_desc": "Använd en VPN när du använder SaaS-verktyg på offentligt Wi-Fi",
        "xlink_access_secure": "Åtkom dina verktyg säkert",
        "xlink_secure_saas_desc": "Använd en lösenordshanterare för dina SaaS-uppgifter",
        "xlink_secure_saas": "Skydda dina SaaS-inloggningar",
        "xlink_secure_creds_desc": "Använd en lösenordshanterare för hosting- och serveruppgifter",
        "xlink_secure_creds": "Skydda dina inloggningsuppgifter",
        "xlink_protect_server_desc": "Lägg till en VPN för säker fjärradministration",
        "xlink_protect_server": "Skydda din server",
        "xlink_secure_passwords_desc": "Använd en lösenordshanterare för att skydda dina konton",
        "xlink_secure_passwords": "Skydda dina lösenord",
        "xlink_add_vpn_av": "Lägg till en VPN för krypterad surfning",
        "xlink_add_malware_desc": "Skydda mot tangentbordsloggare och inloggningsstöld",
        "xlink_add_malware": "Lägg till skydd mot skadlig programvara",
        "xlink_add_av_vpn": "Komplettera din säkerhet med antivirus tillsammans med din VPN",
        "xlink_add_av": "Lägg till antivirusskydd",
        "xlink_add_vpn_pm": "Lägg till en VPN till din lösenordshanterare",
        "xlink_add_pm_vpn": "Lägg till en lösenordshanterare till din VPN för fullt skydd",
        "xlink_complete_security": "Komplettera din säkerhet",
        "xlink_complete_privacy": "Komplettera ditt integritetsskydd",
        "type_wordpress": "WordPress-plugin",
        "type_crates": "Rust-paket",
        "type_pypi": "Python-paket",
        "type_steam": "Steam-spel",
        "type_android": "Android-app",
        "type_website_builder": "webbplatsbyggare",
        "type_crypto": "kryptobörs",
        "type_password_manager": "lösenordshanterare",
        "type_antivirus": "antivirusprogram",
        "type_hosting": "webbhosting-leverantör",
        "type_saas": "SaaS-plattform",
        "type_npm": "npm-paket",
        "type_vpn": "VPN-tjänst",
        "based_on_dims": "baserat på {dims} oberoende datadimensioner",
        "with_trust_score": "med ett Nerq-förtroendepoäng på {score}/100 ({grade})",
        "is_a_type": "är en {type}",
        "rec_wordpress": "rekommenderas för WordPress-användning",
        "rec_use": "rekommenderas för användning",
        "rec_play": "rekommenderas för spel",
        "rec_general": "rekommenderas för allmän användning",
        "rec_production": "rekommenderas för produktionsanvändning",
        "rec_privacy": "rekommenderas för integritetsmedveten användning",
        "ans_trust": "{name} har ett Nerq-förtroendepoäng på {score}/100 med betyget {grade}. Denna poäng baseras på {dims} oberoende mätta dimensioner inklusive säkerhet, underhåll och communityanvändning.",
        "ans_findings_strong": "{name}s starkaste signal är {signal} på {signal_score}/100.",
        "ans_no_vulns": "Inga kända sårbarheter har upptäckts.",
        "ans_has_vulns": "{count} kända sårbarheter identifierades.",
        "ans_verified": "Uppfyller Nerqs verifieringströskel på 70+.",
        "ans_not_verified": "Har ännu inte nått Nerqs verifieringströskel på 70+.",
        "data_sourced": "Data hämtad från {sources}. Senast uppdaterad: {date}.",
        "score_based_dims": "Poäng baserad på {dims}.",
        "yes_safe_short": "Ja, det är säkert att använda.",
        "title_safe": "Är {name} säker? Oberoende förtroende- och säkerhetsanalys {year} | Nerq",
        "title_safe_visit": "Är {name} säkert att besöka? Säkerhetsbetyg {year} &amp; Reseguide | Nerq",
        "title_charity": "Är {name} en pålitlig välgörenhetsorganisation? Förtroendeanalys {year} | Nerq",
        "title_ingredient": "Är {name} säker? Hälso- &amp; säkerhetsanalys {year} | Nerq",
        "h1_safe": "Är {name} säker?",
        "h1_safe_visit": "Är {name} säkert att besöka?",
        "h1_trustworthy_charity": "Är {name} en pålitlig välgörenhetsorganisation?",
        "h1_ingredient_safe": "Är {name} säker?",
        "breadcrumb_safety": "Säkerhetsrapporter",
        "security_analysis": "Säkerhetsanalys", "privacy_report": "Integritetsrapport", "similar_in_registry": "Liknande {registry} efter förtroendepoäng", "see_all_best": "Se alla säkraste {registry}",
        "pv_grade": "Betyg {grade}", "pv_body": "Baserat på analys av {dims} tillitsdimensioner bedöms det som {verdict}.", "pv_vulns": "med {count} kända sårbarheter", "pv_updated": "Senast uppdaterad: {date}.", "pv_safe": "säkert att använda", "pv_generally_safe": "generellt säkert men med vissa farhågor", "pv_notable_concerns": "har anmärkningsvärda säkerhetsproblem", "pv_significant_risks": "har betydande säkerhetsrisker", "pv_unsafe": "anses osäkert",
        "h2q_trust_score": "Vad är {name}s förtroendepoäng?", "h2q_key_findings": "Vilka är de viktigaste säkerhetsresultaten för {name}?", "h2q_details": "Vad är {name} och vem underhåller det?",
        "trust_score_breakdown": "Förtroendepoäng i detalj",
        "safety_score_breakdown": "Säkerhetspoäng i detalj",
        "key_findings": "Viktiga resultat",
        "key_safety_findings": "Viktiga säkerhetsresultat",
        "details": "Detaljer",
        "detailed_score_analysis": "Detaljerad poänganalys",
        "faq": "Vanliga frågor",
        "community_reviews": "Communityomdömen",
        "regulatory_compliance": "Regelefterlevnad",
        "how_calculated": "Så beräknade vi denna poäng",
        "popular_alternatives": "Populära alternativ inom {category}",
        "safer_alternatives": "Säkrare alternativ",
        "across_platforms": "{name} på andra plattformar",
        "safety_guide": "Säkerhetsguide: {name}",
        "what_is": "Vad är {name}?",
        "key_concerns": "Viktiga säkerhetsproblem för {type}",
        "how_to_verify": "Så verifierar du säkerheten",
        "trust_assessment": "Förtroendebedömning",
        "what_data_collect": "Vilka data samlar {name} in?",
        "is_secure": "Är {name} säker?",
        "is_safe_visit": "Är {name} säkert att besöka?",
        "is_legit_charity": "Är {name} en legitim välgörenhetsorganisation?",
        "crime_safety": "Brottslighet och säkerhet i {name}",
        "financial_transparency": "Ekonomisk transparens för {name}",
        "yes_safe": "Ja, {name} är säker att använda.",
        "use_caution": "Använd {name} med försiktighet.",
        "exercise_caution": "Var försiktig med {name}.",
        "significant_concerns": "{name} har betydande förtroendeproblem.",
        "safe": "Säker",
        "use_caution_short": "Var försiktig",
        "avoid": "Undvik",
        "passes_threshold": "Uppfyller Nerqs verifierade tröskel",
        "below_threshold": "Under Nerqs verifierade tröskel",
        "significant_gaps": "Betydande förtroendeluckor upptäckta",
        "meets_threshold_detail": "Uppfyller Nerqs förtroendetröskel med starka signaler inom säkerhet, underhåll och communityanvändning",
        "not_reached_threshold": "och har ännu inte nått Nerqs förtroendetröskel (70+).",
        "score_based_on": "Denna poäng baseras på automatiserad analys av signaler för säkerhet, underhåll, community och kvalitet.",
        "recommended_production": "Rekommenderas för produktionsanvändning",
        "last_analyzed": "Senast analyserad:",
        "author_label": "Utvecklare",
        "category_label": "Kategori",
        "stars_label": "Stjärnor",
        "global_rank_label": "Global ranking",
        "source_label": "Källa",
        "machine_readable": "Maskinläsbar data (JSON)",
        "full_analysis": "Fullständig analys:",
        "privacy_report": "{name} integritetsrapport",
        "security_report": "{name} säkerhetsrapport",
        "write_review": "Skriv ett omdöme",
        "no_reviews": "Inga omdömen ännu.",
        "be_first_review": "Bli först med att recensera {name}",
        "security": "Säkerhet",
        "compliance": "Regelefterlevnad",
        "maintenance": "Underhåll",
        "documentation": "Dokumentation",
        "popularity": "Popularitet",
        "overall_trust": "Övergripande förtroende",
        "privacy": "Integritet",
        "reliability": "Tillförlitlighet",
        "transparency": "Transparens",
        "disclaimer": "Nerqs förtroendepoäng är automatiserade bedömningar baserade på offentligt tillgängliga signaler. De utgör inte rekommendationer eller garantier. Gör alltid din egen verifiering.",
        "same_developer": "Samma utvecklare/företag i andra register:",
        "methodology_entities": "Nerq analyserar över 7,5 miljoner entiteter i 26 register med samma metodik, vilket möjliggör direkt jämförelse mellan entiteter.",
        "scores_updated_continuously": "Poäng uppdateras löpande när ny data finns tillgänglig.",
        "strongest_signal": "Starkaste signalen:",
        "in_category": "I kategorin {category},",
        "check_back_soon": "kom tillbaka snart",
        "safe_solo": "Är {name} säkert för ensamma resenärer?",
        "safe_women": "Är {name} säkert för kvinnor?",
        "safe_lgbtq": "Är {name} säkert för LGBTQ+-resenärer?",
        "safe_families": "Är {name} säkert för familjer?",
        "safe_visit_now": "Är {name} säkert att besöka just nu?",
        "tap_water_safe": "Är kranvattnet i {name} säkert att dricka?",
        "need_vaccinations": "Behöver jag vaccinationer för {name}?",
        "what_are_side_effects": "Vilka biverkningar har {name}?",
        "what_are_safer_alts": "Vilka säkrare alternativ finns till {name}?",
        "interact_medications": "Interagerar {name} med läkemedel?",
        "cause_irritation": "Kan {name} orsaka hudirritation?",
        "health_disclaimer": "Denna information är enbart i utbildningssyfte och utgör inte medicinsk rådgivning. Rådgör med en kvalificerad vårdgivare innan du fattar hälsobeslut.",
        "not_analyzed_title": "{name} — Ännu ej analyserad | Nerq",
        "not_analyzed_h1": "{name} — Ännu ej analyserad",
        "not_analyzed_msg": "Nerq har ännu inte genomfört en förtroendeanalys av {name}. Vi analyserar över 7,5 miljoner entiteter — denna kan läggas till snart.",
        "not_analyzed_meanwhile": "Under tiden kan du:",
        "not_analyzed_search": "Prova att söka med en annan stavning",
        "not_analyzed_api": "Kontrollera API:et direkt",
        "not_analyzed_browse": "Bläddra bland entiteter vi redan analyserat",
        "not_analyzed_no_score": "Denna sida innehåller ingen förtroendepoäng eftersom vi ännu inte analyserat denna entitet.",
        "not_analyzed_no_fabricate": "Nerq fabricerar aldrig betyg. Om du anser att denna entitet borde finnas med kan den dyka upp i en framtida uppdatering.",
    },
    "zh": {
        "dim_popularity": "人气度",
        "faq_q3_alts": "{name}有哪些更安全的替代品？",
        "faq_q4_log": "{name}会记录我的数据吗？",
        "faq_q4_update": "{name}的安全评分多久更新一次？",
        "faq_q5_vs": "{name}与替代品相比：哪个更安全？",
        "faq_q5_regulated": "我可以在受监管的环境中使用{name}吗？",
        "vpn_sec_score": "安全评分",
        "privacy_score_label": "隐私评分",
        "strong": "强",
        "moderate": "中等",
        "weak": "弱",
        "actively_maintained": "积极维护中",
        "moderately_maintained": "适度维护",
        "low_maintenance": "低维护活动",
        "well_documented": "文档完善",
        "partial_documentation": "部分文档",
        "limited_documentation": "有限文档",
        "community_adoption": "社区采用",
        "faq_q4_vuln": "{name}有已知漏洞吗？",
        "faq_q4_kids": "{name}对儿童安全吗？",
        "faq_q4_perms": "{name}需要哪些权限？",
        "faq_q4_maintained": "{name}是否积极维护？",
        "faq_a4_vuln": "Nerq检查{name}的NVD、OSV.dev和注册表特定漏洞数据库。当前安全评分：{sec_score}。",
        "faq_a4_kids": "{name}的Nerq评分为{score}/100。家长应查看完整报告。",
        "faq_a4_perms": "仔细审查{name}请求的权限。信任评分：{score}/100。",
        "faq_a4_maintained": "{name}维护评分：{maint_score}。检查仓库最近的活动。",
        "faq_a5_verified": "{name}达到Nerq验证阈值（70+）。可安全用于生产。",
        "faq_a5_not_verified": "{name}未达到Nerq验证阈值70。建议进行额外审查。",
        "more_being_analyzed": "更多{type}正在分析中 — 稍后再来查看。",
        "dim_maintenance": "维护",
        "dim_security": "安全",
        "sidebar_most_private": "最私密的应用",
        "sidebar_safest_vpns": "最安全的VPN",
        "eyes_outside": "在所有Eyes监控联盟之外 — 隐私优势",
        "serving_users": "服务",
        "privacy_assessment": "隐私评估",
        "sidebar_recently": "最近分析",
        "sidebar_browse": "浏览分类",
        "sidebar_popular_in": "热门",
        "vpn_logging_audited": "日志策略：独立审计的无日志策略。根据独立审计报告，{name}不存储连接日志、浏览活动或DNS查询。",
        "vpn_server_infra": "服务器基础设施",
        "vpn_significant": "这很重要，因为非联盟管辖区的VPN提供商不受强制数据保留法或情报共享协议的约束。",
        "vpn_outside_eyes": "在五眼、九眼和十四眼监控联盟之外",
        "vpn_jurisdiction": "管辖权",
        "vpn_operates_under": "在...管辖下运营",
        "xlink_safest_crypto": "最安全的加密货币交易所",
        "xlink_access_secure": "安全访问您的工具",
        "xlink_secure_saas": "保护SaaS登录",
        "xlink_protect_server": "保护您的服务器",
        "xlink_secure_passwords_desc": "使用密码管理器保护您的账户",
        "xlink_secure_passwords": "保护您的密码",
        "xlink_add_vpn_av": "添加VPN进行加密浏览",
        "xlink_add_malware_desc": "防止键盘记录器和凭证窃取",
        "xlink_add_malware": "添加恶意软件防护",
        "xlink_add_av_vpn": "用杀毒软件配合VPN完善安全",
        "xlink_add_av": "添加杀毒保护",
        "xlink_add_vpn_pm": "为密码管理器添加VPN",
        "xlink_add_pm_vpn": "为VPN添加密码管理器",
        "xlink_complete_security": "完善安全",
        "xlink_complete_privacy": "完善隐私设置",
        "type_wordpress": "WordPress插件",
        "type_crates": "Rust crate",
        "type_pypi": "Python包",
        "type_steam": "Steam游戏",
        "type_android": "Android应用",
        "type_website_builder": "网站构建器",
        "type_crypto": "加密货币交易所",
        "type_password_manager": "密码管理器",
        "type_antivirus": "杀毒软件",
        "type_hosting": "托管服务商",
        "type_saas": "SaaS平台",
        "type_npm": "npm包",
        "type_vpn": "VPN服务",
        "based_on_dims": "基于{dims}个独立数据维度",
        "with_trust_score": "Nerq 信任分数 {score}/100（{grade}）",
        "is_a_type": "是一个{type}",
        "rec_wordpress": "推荐在WordPress中使用",
        "rec_use": "推荐使用",
        "rec_play": "推荐游玩",
        "rec_general": "推荐一般使用",
        "rec_production": "推荐生产环境使用",
        "rec_privacy": "推荐隐私敏感型使用",
        "ans_trust": "{name} 的 Nerq 信任分数为 {score}/100，等级为 {grade}。该分数基于 {dims} 个独立测量的维度，包括安全性、维护和社区采用。",
        "ans_findings_strong": "{name} 最强的信号是 {signal}，为 {signal_score}/100。",
        "ans_no_vulns": "未检测到已知漏洞。",
        "ans_has_vulns": "发现了 {count} 个已知漏洞。",
        "ans_verified": "达到 Nerq 认证阈值 70+。",
        "ans_not_verified": "尚未达到 Nerq 认证阈值 70+。",
        "data_sourced": "数据来源于{sources}。最后更新：{date}。",
        "score_based_dims": "基于{dims}的评分。",
        "yes_safe_short": "是的，可以安全使用。",
        "title_safe": "{name}安全吗？独立信任与安全分析 {year} | Nerq",
        "title_safe_visit": "访问{name}安全吗？安全评分 {year} &amp; 旅行指南 | Nerq",
        "title_charity": "{name}是可靠的慈善机构吗？信任分析 {year} | Nerq",
        "title_ingredient": "{name}安全吗？健康与安全分析 {year} | Nerq",
        "h1_safe": "{name}安全吗？",
        "h1_safe_visit": "访问{name}安全吗？",
        "h1_trustworthy_charity": "{name}是可靠的慈善机构吗？",
        "h1_ingredient_safe": "{name}安全吗？",
        "breadcrumb_safety": "安全报告",
        "security_analysis": "安全分析", "privacy_report": "隐私报告", "similar_in_registry": "按信任评分排列的类似{registry}", "see_all_best": "查看所有最安全的{registry}",
        "pv_grade": "{grade}级", "pv_body": "基于{dims}个信任维度的分析，被评估为{verdict}。", "pv_vulns": "有{count}个已知漏洞", "pv_updated": "最后更新：{date}。", "pv_safe": "可安全使用", "pv_generally_safe": "总体安全但存在一些担忧", "pv_notable_concerns": "存在值得注意的安全问题", "pv_significant_risks": "存在重大安全风险", "pv_unsafe": "被认为不安全",
        "h2q_trust_score": "{name}的信任评分是多少？", "h2q_key_findings": "{name}的主要安全发现是什么？", "h2q_details": "{name}是什么，谁在维护它？",
        "trust_score_breakdown": "信任评分详情",
        "safety_score_breakdown": "安全评分详情",
        "key_findings": "主要发现",
        "key_safety_findings": "主要安全发现",
        "details": "详情",
        "detailed_score_analysis": "评分详细分析",
        "faq": "常见问题",
        "community_reviews": "社区评价",
        "regulatory_compliance": "合规性",
        "how_calculated": "我们如何计算此评分",
        "popular_alternatives": "{category}中的热门替代品",
        "safer_alternatives": "更安全的替代品",
        "across_platforms": "{name}在其他平台",
        "safety_guide": "安全指南：{name}",
        "what_is": "{name}是什么？",
        "key_concerns": "{type}的主要安全问题",
        "how_to_verify": "如何验证安全性",
        "trust_assessment": "信任评估",
        "what_data_collect": "{name}收集哪些数据？",
        "is_secure": "{name}安全吗？",
        "is_safe_visit": "访问{name}安全吗？",
        "is_legit_charity": "{name}是合法的慈善机构吗？",
        "crime_safety": "{name}的犯罪与安全",
        "financial_transparency": "{name}的财务透明度",
        "yes_safe": "是的，{name}可以安全使用。",
        "use_caution": "请谨慎使用{name}。",
        "exercise_caution": "请对{name}保持警惕。",
        "significant_concerns": "{name}存在严重的信任问题。",
        "safe": "安全",
        "use_caution_short": "谨慎",
        "avoid": "避免",
        "passes_threshold": "达到 Nerq 验证阈值",
        "below_threshold": "低于 Nerq 验证阈值",
        "significant_gaps": "发现重大信任缺口",
        "meets_threshold_detail": "凭借在安全性、维护和社区采用方面的强烈信号，达到了 Nerq 信任阈值",
        "not_reached_threshold": "尚未达到 Nerq 信任阈值（70+）。",
        "score_based_on": "此评分基于对安全性、维护、社区和质量信号的自动分析。",
        "recommended_production": "推荐用于生产环境",
        "last_analyzed": "最近分析：",
        "author_label": "开发者",
        "category_label": "类别",
        "stars_label": "星标",
        "global_rank_label": "全球排名",
        "source_label": "来源",
        "machine_readable": "机器可读数据（JSON）",
        "full_analysis": "完整分析：",
        "privacy_report": "{name}隐私报告",
        "security_report": "{name}安全报告",
        "write_review": "撰写评价",
        "no_reviews": "暂无评价。",
        "be_first_review": "成为第一个评价{name}的人",
        "security": "安全性",
        "compliance": "合规性",
        "maintenance": "维护",
        "documentation": "文档",
        "popularity": "人气",
        "overall_trust": "整体信任度",
        "privacy": "隐私",
        "reliability": "可靠性",
        "transparency": "透明度",
        "disclaimer": "Nerq 信任评分是基于公开信号的自动评估。它们不构成建议或保证。请始终进行自己的验证。",
        "same_developer": "同一开发者/公司在其他注册表中：",
        "methodology_entities": "Nerq 使用相同的方法分析 26 个注册表中超过 750 万个实体，从而实现实体间的直接比较。",
        "scores_updated_continuously": "评分会在新数据可用时持续更新。",
        "strongest_signal": "最强信号：",
        "in_category": "在{category}类别中，",
        "check_back_soon": "请稍后再查看",
        "safe_solo": "{name}对独自旅行者安全吗？",
        "safe_women": "{name}对女性安全吗？",
        "safe_lgbtq": "{name}对 LGBTQ+ 旅行者安全吗？",
        "safe_families": "{name}对家庭安全吗？",
        "safe_visit_now": "现在访问{name}安全吗？",
        "tap_water_safe": "{name}的自来水可以安全饮用吗？",
        "need_vaccinations": "我去{name}需要接种疫苗吗？",
        "what_are_side_effects": "{name}的副作用有哪些？",
        "what_are_safer_alts": "{name}有哪些更安全的替代品？",
        "interact_medications": "{name}会与药物产生相互作用吗？",
        "cause_irritation": "{name}会引起皮肤刺激吗？",
        "health_disclaimer": "本信息仅供教育目的，不构成医疗建议。在做出健康决定之前，请咨询合格的医疗专业人员。",
        "not_analyzed_title": "{name} — 尚未分析 | Nerq",
        "not_analyzed_h1": "{name} — 尚未分析",
        "not_analyzed_msg": "Nerq 尚未对{name}进行信任分析。我们分析超过 750 万个实体——此条目可能很快会被添加。",
        "not_analyzed_meanwhile": "在此期间，您可以：",
        "not_analyzed_search": "尝试使用不同的拼写进行搜索",
        "not_analyzed_api": "直接检查 API",
        "not_analyzed_browse": "浏览我们已分析的实体",
        "not_analyzed_no_score": "此页面不包含信任评分，因为我们尚未分析此实体。",
        "not_analyzed_no_fabricate": "Nerq 从不捏造评分。如果您认为此实体应被涵盖，它可能会在未来的更新中出现。",
    },
    "da": {
        "vpn_outside_eyes": "uden for Five Eyes, Nine Eyes og Fourteen Eyes overvågningsalliancerne",
        "faq_q3_alts": "Hvad er sikrere alternativer til {name}?",
        "faq_q4_log": "Logger {name} mine data?",
        "faq_q4_update": "Hvor ofte opdateres {name}s sikkerhedsscore?",
        "faq_q5_vs": "{name} vs alternativer: hvad er sikrere?",
        "faq_q5_regulated": "Kan jeg bruge {name} i et reguleret miljø?",
        "vpn_sec_score": "Sikkerhedsscore",
        "privacy_score_label": "Privatlivsscore",
        "strong": "stærk",
        "moderate": "moderat",
        "weak": "svag",
        "actively_maintained": "aktivt vedligeholdt",
        "moderately_maintained": "moderat vedligeholdt",
        "low_maintenance": "lav vedligeholdelsesaktivitet",
        "well_documented": "godt dokumenteret",
        "partial_documentation": "delvis dokumentation",
        "limited_documentation": "begrænset dokumentation",
        "community_adoption": "community-adoption",
        "faq_q4_vuln": "Har {name} kendte sårbarheder?",
        "faq_q4_kids": "Er {name} sikker for børn?",
        "faq_q4_perms": "Hvilke tilladelser kræver {name}?",
        "faq_q4_maintained": "Vedligeholdes {name} aktivt?",
        "faq_a4_vuln": "Nerq tjekker {name} mod NVD, OSV.dev og registerspecifikke sårbarhedsdatabaser. Aktuel sikkerhedsscore: {sec_score}.",
        "faq_a4_kids": "{name} har en Nerq-score på {score}/100. Forældre bør gennemgå den fulde rapport.",
        "faq_a4_perms": "Gennemgå {name}s anmodede tilladelser omhyggeligt. Tillidsscore: {score}/100.",
        "faq_a4_maintained": "{name} vedligeholdelsesscore: {maint_score}. Tjek repositoriet for nylig aktivitet.",
        "faq_a5_verified": "{name} opfylder Nerq-verificeringstærsklen (70+). Sikkert til produktionsbrug.",
        "faq_a5_not_verified": "{name} har ikke nået Nerq-verificeringstærsklen på 70. Yderligere gennemgang anbefales.",
        "more_being_analyzed": "flere {type} analyseres — kom snart tilbage.",
        "vpn_jurisdiction": "jurisdiktion",
        "vpn_operates_under": "opererer under",
        "xlink_add_av_vpn": "Fuldfør din sikkerhed med antivirus sammen med VPN",
        "xlink_add_av": "Tilføj antivirusbeskyttelse",
        "xlink_add_pm_vpn": "Tilføj en adgangskodeadministrator til din VPN",
        "xlink_complete_security": "Fuldfør din sikkerhed",
        "xlink_complete_privacy": "Fuldfør dit privatliv",
        "is_a_type": "er en {type}",
        "rec_privacy": "anbefales til privatlivsfokuseret brug",
        "ans_trust": "{name} har en Nerq Trust Score på {score}/100 med karakteren {grade}. Denne score er baseret på {dims} uafhængigt målte dimensioner, herunder sikkerhed, vedligeholdelse og community-adoption.",
        "ans_findings_strong": "{name}s stærkeste signal er {signal} på {signal_score}/100.",
        "ans_no_vulns": "Ingen kendte sårbarheder er fundet.",
        "title_safe": "Er {name} sikker? Uafhængig tillids- og sikkerhedsanalyse {year} | Nerq",
        "title_safe_visit": "Er {name} sikker at besøge? Sikkerhedsscore {year} &amp; Rejseguide | Nerq",
        "title_charity": "Er {name} en pålidelig velgørenhedsorganisation? Tillidsanalyse {year} | Nerq",
        "title_ingredient": "Er {name} sikker? Sundheds- &amp; sikkerhedsanalyse {year} | Nerq",
        "h1_safe": "Er {name} sikker?",
        "h1_safe_visit": "Er {name} sikker at besøge?",
        "h1_trustworthy_charity": "Er {name} en pålidelig velgørenhedsorganisation?",
        "h1_ingredient_safe": "Er {name} sikker?",
        "breadcrumb_safety": "Sikkerhedsrapporter",
        "security_analysis": "Sikkerhedsanalyse", "privacy_report": "Privatlivsrapport", "similar_in_registry": "Lignende {registry} efter tillidsscore", "see_all_best": "Se alle sikreste {registry}",
        "pv_grade": "Karakter {grade}", "pv_body": "Baseret på analyse af {dims} tillidsdimensioner vurderes det som {verdict}.", "pv_vulns": "med {count} kendte sårbarheder", "pv_updated": "Sidst opdateret: {date}.", "pv_safe": "sikkert at bruge", "pv_generally_safe": "generelt sikkert men med visse bekymringer", "pv_notable_concerns": "har bemærkelsesværdige sikkerhedsproblemer", "pv_significant_risks": "har betydelige sikkerhedsrisici", "pv_unsafe": "anses for usikkert",
        "h2q_trust_score": "Hvad er {name}s tillidsscore?", "h2q_key_findings": "Hvad er de vigtigste sikkerhedsresultater for {name}?", "h2q_details": "Hvad er {name} og hvem vedligeholder det?",
        "trust_score_breakdown": "Tillidsscore detaljer",
        "safety_score_breakdown": "Sikkerhedsscore detaljer",
        "key_findings": "Vigtigste resultater",
        "key_safety_findings": "Vigtigste sikkerhedsresultater",
        "details": "Detaljer",
        "detailed_score_analysis": "Detaljeret scoreanalyse",
        "faq": "Ofte stillede spørgsmål",
        "community_reviews": "Fællesskabsanmeldelser",
        "regulatory_compliance": "Lovgivningsmæssig overholdelse",
        "how_calculated": "Sådan beregnede vi denne score",
        "popular_alternatives": "Populære alternativer i {category}",
        "safer_alternatives": "Sikrere alternativer",
        "across_platforms": "{name} på andre platforme",
        "safety_guide": "Sikkerhedsguide: {name}",
        "what_is": "Hvad er {name}?",
        "key_concerns": "Vigtigste sikkerhedsproblemer for {type}",
        "how_to_verify": "Sådan verificerer du sikkerheden",
        "trust_assessment": "Tillidsvurdering",
        "what_data_collect": "Hvilke data indsamler {name}?",
        "is_secure": "Er {name} sikker?",
        "is_safe_visit": "Er {name} sikker at besøge?",
        "is_legit_charity": "Er {name} en legitim velgørenhedsorganisation?",
        "crime_safety": "Kriminalitet og sikkerhed i {name}",
        "financial_transparency": "Finansiel gennemsigtighed for {name}",
        "yes_safe": "Ja, {name} er sikker at bruge.",
        "use_caution": "Brug {name} med forsigtighed.",
        "exercise_caution": "Vær forsigtig med {name}.",
        "significant_concerns": "{name} har betydelige tillidsproblemer.",
        "safe": "Sikker",
        "use_caution_short": "Forsigtighed",
        "avoid": "Undgå",
        "passes_threshold": "Opfylder Nerqs verificerede tærskel",
        "below_threshold": "Under Nerqs verificerede tærskel",
        "significant_gaps": "Betydelige tillidshuller opdaget",
        "meets_threshold_detail": "Opfylder Nerqs tillidstærskel med stærke signaler inden for sikkerhed, vedligeholdelse og fællesskabsadoption",
        "not_reached_threshold": "og har endnu ikke nået Nerqs tillidstærskel (70+).",
        "score_based_on": "Denne score er baseret på automatiseret analyse af sikkerheds-, vedligeholdelses-, fællesskabs- og kvalitetssignaler.",
        "recommended_production": "Anbefalet til produktionsbrug",
        "last_analyzed": "Sidst analyseret:",
        "author_label": "Udvikler",
        "category_label": "Kategori",
        "stars_label": "Stjerner",
        "global_rank_label": "Global rangering",
        "source_label": "Kilde",
        "machine_readable": "Maskinlæsbare data (JSON)",
        "full_analysis": "Fuld analyse:",
        "privacy_report": "{name} privatlivsrapport",
        "security_report": "{name} sikkerhedsrapport",
        "write_review": "Skriv en anmeldelse",
        "no_reviews": "Ingen anmeldelser endnu.",
        "be_first_review": "Vær den første til at anmelde {name}",
        "security": "Sikkerhed",
        "compliance": "Overholdelse",
        "maintenance": "Vedligeholdelse",
        "documentation": "Dokumentation",
        "popularity": "Popularitet",
        "overall_trust": "Samlet tillid",
        "privacy": "Privatliv",
        "reliability": "Pålidelighed",
        "transparency": "Gennemsigtighed",
        "disclaimer": "Nerqs tillidsscorer er automatiserede vurderinger baseret på offentligt tilgængelige signaler. De udgør ikke anbefalinger eller garantier. Foretag altid din egen verificering.",
        "same_developer": "Samme udvikler/virksomhed i andre registre:",
        "methodology_entities": "Nerq analyserer over 7,5 millioner enheder i 26 registre med samme metodik, hvilket muliggør direkte sammenligning mellem enheder.",
        "scores_updated_continuously": "Scorer opdateres løbende, efterhånden som nye data bliver tilgængelige.",
        "strongest_signal": "Stærkeste signal:",
        "in_category": "I kategorien {category},",
        "check_back_soon": "kom snart tilbage",
        "safe_solo": "Er {name} sikkert for solorejsende?",
        "safe_women": "Er {name} sikkert for kvinder?",
        "safe_lgbtq": "Er {name} sikkert for LGBTQ+-rejsende?",
        "safe_families": "Er {name} sikkert for familier?",
        "safe_visit_now": "Er {name} sikker at besøge lige nu?",
        "tap_water_safe": "Er postevandet i {name} sikkert at drikke?",
        "need_vaccinations": "Har jeg brug for vaccinationer til {name}?",
        "what_are_side_effects": "Hvad er bivirkningerne ved {name}?",
        "what_are_safer_alts": "Hvad er sikrere alternativer til {name}?",
        "interact_medications": "Interagerer {name} med medicin?",
        "cause_irritation": "Kan {name} forårsage hudirritation?",
        "health_disclaimer": "Denne information er kun til uddannelsesmæssige formål og udgør ikke medicinsk rådgivning. Konsultér en kvalificeret sundhedsperson, før du træffer sundhedsbeslutninger.",
        "not_analyzed_title": "{name} — Endnu ikke analyseret | Nerq",
        "not_analyzed_h1": "{name} — Endnu ikke analyseret",
        "not_analyzed_msg": "Nerq har endnu ikke foretaget en tillidsanalyse af {name}. Vi analyserer over 7,5 millioner enheder — denne kan snart blive tilføjet.",
        "not_analyzed_meanwhile": "I mellemtiden kan du:",
        "not_analyzed_search": "Prøv at søge med en anden stavemåde",
        "not_analyzed_api": "Tjek API'et direkte",
        "not_analyzed_browse": "Gennemse enheder, vi allerede har analyseret",
        "not_analyzed_no_score": "Denne side indeholder ingen tillidsscore, fordi vi endnu ikke har analyseret denne enhed.",
        "not_analyzed_no_fabricate": "Nerq fabrikerer aldrig vurderinger. Hvis du mener, denne enhed bør dækkes, kan den dukke op i en fremtidig opdatering.",
    },
    "no": {
        "vpn_outside_eyes": "utenfor Five Eyes, Nine Eyes og Fourteen Eyes overvåkningsalliansene",
        "faq_q3_alts": "Hva er tryggere alternativer til {name}?",
        "faq_q4_log": "Logger {name} mine data?",
        "faq_q4_update": "Hvor ofte oppdateres {name}s sikkerhetspoeng?",
        "faq_q5_vs": "{name} mot alternativer: hva er tryggere?",
        "faq_q5_regulated": "Kan jeg bruke {name} i et regulert miljø?",
        "vpn_sec_score": "Sikkerhetspoeng",
        "privacy_score_label": "Personvernpoeng",
        "strong": "sterk",
        "moderate": "moderat",
        "weak": "svak",
        "actively_maintained": "aktivt vedlikeholdt",
        "moderately_maintained": "moderat vedlikeholdt",
        "low_maintenance": "lav vedlikeholdsaktivitet",
        "well_documented": "vel dokumentert",
        "partial_documentation": "delvis dokumentasjon",
        "limited_documentation": "begrenset dokumentasjon",
        "community_adoption": "samfunnsadopsjon",
        "faq_q4_vuln": "Har {name} kjente sårbarheter?",
        "faq_q4_kids": "Er {name} trygt for barn?",
        "faq_q4_perms": "Hvilke tillatelser trenger {name}?",
        "faq_q4_maintained": "Vedlikeholdes {name} aktivt?",
        "faq_a4_vuln": "Nerq sjekker {name} mot NVD, OSV.dev og registerspesifikke sårbarhetsdatabaser. Nåværende sikkerhetspoeng: {sec_score}.",
        "faq_a4_kids": "{name} har en Nerq-poeng på {score}/100. Foreldre bør gjennomgå den fullstendige rapporten.",
        "faq_a4_perms": "Gjennomgå {name}s forespurte tillatelser nøye. Tillitspoeng: {score}/100.",
        "faq_a4_maintained": "{name} vedlikeholdspoeng: {maint_score}. Sjekk repositoriet for nylig aktivitet.",
        "faq_a5_verified": "{name} oppfyller Nerq-verifiseringsgrensen (70+). Trygt for produksjonsbruk.",
        "faq_a5_not_verified": "{name} har ikke nådd Nerq-verifiseringsgrensen på 70. Ytterligere gjennomgang anbefales.",
        "more_being_analyzed": "flere {type} analyseres — kom tilbake snart.",
        "vpn_jurisdiction": "jurisdiksjon",
        "vpn_operates_under": "opererer under",
        "xlink_add_av_vpn": "Fullfør sikkerheten din med antivirus sammen med VPN",
        "xlink_add_av": "Legg til antivirusbeskyttelse",
        "xlink_add_pm_vpn": "Legg til en passordbehandler til VPN-en din",
        "xlink_complete_security": "Fullfør sikkerheten din",
        "xlink_complete_privacy": "Fullfør personvernet ditt",
        "is_a_type": "er en {type}",
        "rec_privacy": "anbefales for personvernfokusert bruk",
        "ans_trust": "{name} har en Nerq-tillitspoeng på {score}/100 med karakteren {grade}. Denne poengsummen er basert på {dims} uavhengig målte dimensjoner, inkludert sikkerhet, vedlikehold og samfunnsadopsjon.",
        "ans_findings_strong": "{name}s sterkeste signal er {signal} på {signal_score}/100.",
        "ans_no_vulns": "Ingen kjente sårbarheter er funnet.",
        "title_safe": "Er {name} trygt? Uavhengig tillits- og sikkerhetsanalyse {year} | Nerq",
        "title_safe_visit": "Er {name} trygt å besøke? Sikkerhetspoeng {year} &amp; Reiseguide | Nerq",
        "title_charity": "Er {name} en pålitelig veldedighetsorganisasjon? Tillitsanalyse {year} | Nerq",
        "title_ingredient": "Er {name} trygt? Helse- &amp; sikkerhetsanalyse {year} | Nerq",
        "h1_safe": "Er {name} trygt?",
        "h1_safe_visit": "Er {name} trygt å besøke?",
        "h1_trustworthy_charity": "Er {name} en pålitelig veldedighetsorganisasjon?",
        "h1_ingredient_safe": "Er {name} trygt?",
        "breadcrumb_safety": "Sikkerhetsrapporter",
        "security_analysis": "Sikkerhetsanalyse", "privacy_report": "Personvernrapport", "similar_in_registry": "Lignende {registry} etter tillitspoeng", "see_all_best": "Se alle tryggeste {registry}",
        "pv_grade": "Karakter {grade}", "pv_body": "Basert på analyse av {dims} tillidsdimensjoner vurderes det som {verdict}.", "pv_vulns": "med {count} kjente sårbarheter", "pv_updated": "Sist oppdatert: {date}.", "pv_safe": "trygt å bruke", "pv_generally_safe": "generelt trygt men med visse bekymringer", "pv_notable_concerns": "har merkbare sikkerhetsproblemer", "pv_significant_risks": "har betydelige sikkerhetsrisikoer", "pv_unsafe": "anses som utrygt",
        "h2q_trust_score": "Hva er tillitspoengene til {name}?", "h2q_key_findings": "Hva er de viktigste sikkerhetsfunnene for {name}?", "h2q_details": "Hva er {name} og hvem vedlikeholder det?",
        "trust_score_breakdown": "Tillitspoeng detaljer",
        "safety_score_breakdown": "Sikkerhetspoeng detaljer",
        "key_findings": "Viktigste funn",
        "key_safety_findings": "Viktigste sikkerhetsfunn",
        "details": "Detaljer",
        "detailed_score_analysis": "Detaljert poenganalyse",
        "faq": "Ofte stilte spørsmål",
        "community_reviews": "Fellesskapsanmeldelser",
        "regulatory_compliance": "Regulatorisk samsvar",
        "how_calculated": "Slik beregnet vi denne poengsummen",
        "popular_alternatives": "Populære alternativer i {category}",
        "safer_alternatives": "Tryggere alternativer",
        "across_platforms": "{name} på andre plattformer",
        "safety_guide": "Sikkerhetsguide: {name}",
        "what_is": "Hva er {name}?",
        "key_concerns": "Viktigste sikkerhetsproblemer for {type}",
        "how_to_verify": "Slik verifiserer du sikkerheten",
        "trust_assessment": "Tillidsvurdering",
        "what_data_collect": "Hvilke data samler {name} inn?",
        "is_secure": "Er {name} sikkert?",
        "is_safe_visit": "Er {name} trygt å besøke?",
        "is_legit_charity": "Er {name} en legitim veldedighetsorganisasjon?",
        "crime_safety": "Kriminalitet og sikkerhet i {name}",
        "financial_transparency": "Finansiell gjennomsiktighet for {name}",
        "yes_safe": "Ja, {name} er trygt å bruke.",
        "use_caution": "Bruk {name} med forsiktighet.",
        "exercise_caution": "Utvis forsiktighet med {name}.",
        "significant_concerns": "{name} har betydelige tillitsproblemer.",
        "safe": "Trygt",
        "use_caution_short": "Forsiktighet",
        "avoid": "Unngå",
        "passes_threshold": "Oppfyller Nerqs verifiserte terskel",
        "below_threshold": "Under Nerqs verifiserte terskel",
        "significant_gaps": "Betydelige tillitsgap oppdaget",
        "meets_threshold_detail": "Oppfyller Nerqs tillitsterskel med sterke signaler innen sikkerhet, vedlikehold og fellesskapsadopsjon",
        "not_reached_threshold": "og har ennå ikke nådd Nerqs tillitsterskel (70+).",
        "score_based_on": "Denne poengsummen er basert på automatisert analyse av sikkerhets-, vedlikeholds-, fellesskaps- og kvalitetssignaler.",
        "recommended_production": "Anbefalt for produksjonsbruk",
        "last_analyzed": "Sist analysert:",
        "author_label": "Utvikler",
        "category_label": "Kategori",
        "stars_label": "Stjerner",
        "global_rank_label": "Global rangering",
        "source_label": "Kilde",
        "machine_readable": "Maskinlesbare data (JSON)",
        "full_analysis": "Full analyse:",
        "privacy_report": "{name} personvernrapport",
        "security_report": "{name} sikkerhetsrapport",
        "write_review": "Skriv en anmeldelse",
        "no_reviews": "Ingen anmeldelser ennå.",
        "be_first_review": "Vær den første til å anmelde {name}",
        "security": "Sikkerhet",
        "compliance": "Samsvar",
        "maintenance": "Vedlikehold",
        "documentation": "Dokumentasjon",
        "popularity": "Popularitet",
        "overall_trust": "Samlet tillit",
        "privacy": "Personvern",
        "reliability": "Pålitelighet",
        "transparency": "Gjennomsiktighet",
        "disclaimer": "Nerqs tillitspoeng er automatiserte vurderinger basert på offentlig tilgjengelige signaler. De utgjør ikke anbefalinger eller garantier. Utfør alltid din egen verifisering.",
        "same_developer": "Samme utvikler/selskap i andre registre:",
        "methodology_entities": "Nerq analyserer over 7,5 millioner enheter i 26 registre med samme metodikk, noe som muliggjør direkte sammenligning mellom enheter.",
        "scores_updated_continuously": "Poeng oppdateres kontinuerlig etter hvert som nye data blir tilgjengelige.",
        "strongest_signal": "Sterkeste signal:",
        "in_category": "I kategorien {category},",
        "check_back_soon": "kom tilbake snart",
        "safe_solo": "Er {name} trygt for solorejsende?",
        "safe_women": "Er {name} trygt for kvinner?",
        "safe_lgbtq": "Er {name} trygt for LHBTQ+-reisende?",
        "safe_families": "Er {name} trygt for familier?",
        "safe_visit_now": "Er {name} trygt å besøke akkurat nå?",
        "tap_water_safe": "Er kranvannet i {name} trygt å drikke?",
        "need_vaccinations": "Trenger jeg vaksinasjoner for {name}?",
        "what_are_side_effects": "Hva er bivirkningene av {name}?",
        "what_are_safer_alts": "Hva er tryggere alternativer til {name}?",
        "interact_medications": "Interagerer {name} med medisiner?",
        "cause_irritation": "Kan {name} forårsake hudirritasjon?",
        "health_disclaimer": "Denne informasjonen er kun til opplæringsformål og utgjør ikke medisinsk rådgivning. Konsulter en kvalifisert helsepersonell før du tar helsebeslutninger.",
        "not_analyzed_title": "{name} — Ennå ikke analysert | Nerq",
        "not_analyzed_h1": "{name} — Ennå ikke analysert",
        "not_analyzed_msg": "Nerq har ennå ikke gjennomført en tillitsanalyse av {name}. Vi analyserer over 7,5 millioner enheter — denne kan snart bli lagt til.",
        "not_analyzed_meanwhile": "I mellomtiden kan du:",
        "not_analyzed_search": "Prøv å søke med en annen stavemåte",
        "not_analyzed_api": "Sjekk API-et direkte",
        "not_analyzed_browse": "Bla gjennom enheter vi allerede har analysert",
        "not_analyzed_no_score": "Denne siden inneholder ingen tillitspoeng fordi vi ennå ikke har analysert denne enheten.",
        "not_analyzed_no_fabricate": "Nerq fabrikkerer aldri vurderinger. Hvis du mener denne enheten bør dekkes, kan den dukke opp i en fremtidig oppdatering.",
        "with_trust_score": "har en Nerq-tillitspoeng på {score}/100 ({grade})",
        "score_based_dims": "Poeng basert på {dims}.",
        "scores_update": "Poeng oppdateres når nye data er tilgjengelige.",
        "yes_safe_short": "Ja, det er trygt å bruke.",
        "use_caution_faq": "Bruk med forsiktighet.",
        "exercise_caution_faq": "Utvis forsiktighet.",
        "significant_concerns_faq": "Betydelige tillitsproblemer.",
        "dim_popularity": "Popularitet",
        "dim_maintenance": "Vedlikehold",
        "dim_security": "Sikkerhet",
    },
    "ar": {
        "faq_q3_alts": "ما هي البدائل الأكثر أمانًا لـ {name}؟",
        "faq_q4_log": "هل يسجل {name} بياناتي؟",
        "faq_q4_update": "كم مرة يتم تحديث درجة أمان {name}؟",
        "faq_q5_vs": "{name} مقابل البدائل: أيهما أكثر أمانًا؟",
        "faq_q5_regulated": "هل يمكنني استخدام {name} في بيئة منظمة؟",
        "faq_q4_vuln": "هل لدى {name} ثغرات أمنية معروفة؟",
        "faq_q4_kids": "هل {name} آمن للأطفال؟",
        "faq_q4_perms": "ما الأذونات التي يحتاجها {name}؟",
        "faq_q4_maintained": "هل يتم صيانة {name} بنشاط؟",
        "faq_a4_vuln": "يتحقق Nerq من {name} مقابل NVD وOSV.dev وقواعد بيانات الثغرات. درجة الأمان الحالية: {sec_score}.",
        "faq_a4_kids": "{name} لديه درجة Nerq {score}/100. يجب على الآباء مراجعة التقرير الكامل.",
        "faq_a4_perms": "راجع الأذونات المطلوبة من {name} بعناية. درجة الثقة: {score}/100.",
        "faq_a4_maintained": "درجة صيانة {name}: {maint_score}. تحقق من النشاط الأخير للمستودع.",
        "faq_a5_verified": "{name} يستوفي عتبة التحقق من Nerq (70+). آمن للاستخدام.",
        "faq_a5_not_verified": "{name} لم يصل إلى عتبة التحقق من Nerq البالغة 70. يوصى بمراجعة إضافية.",
        "with_trust_score": "لديه درجة ثقة Nerq تبلغ {score}/100 ({grade})",
        "strongest_signal": "أقوى إشارة:",
        "score_based_dims": "التقييم مبني على {dims}.",
        "scores_update": "يتم تحديث النتائج عند توفر بيانات جديدة.",
        "in_category": "في فئة {category}،",
        "more_being_analyzed": "المزيد من {type} قيد التحليل — عد قريباً.",
        "higher_rated_alts": "البدائل الأعلى تقييمًا تشمل {alts}.",
        "yes_safe_short": "نعم، هو آمن للاستخدام.",
        "use_caution_faq": "استخدم بحذر.",
        "exercise_caution_faq": "توخَّ الحذر.",
        "significant_concerns_faq": "مخاوف ثقة كبيرة.",
        "h2q_trust_score": "ما هي درجة ثقة {name}؟",
        "dim_popularity": "الشعبية",
        "strong": "قوي",
        "moderate": "متوسط",
        "weak": "ضعيف",
        "actively_maintained": "يتم صيانته بنشاط",
        "moderately_maintained": "صيانة متوسطة",
        "low_maintenance": "نشاط صيانة منخفض",
        "well_documented": "موثق جيداً",
        "partial_documentation": "توثيق جزئي",
        "limited_documentation": "توثيق محدود",
        "community_adoption": "اعتماد المجتمع",
        "dim_maintenance": "الصيانة",
        "dim_security": "الأمان",
        "below_threshold": "أقل من العتبة الموصى بها 70.",
        "vpn_sec_score": "درجة الأمان",
        "privacy_score_label": "درجة الخصوصية",
        "sidebar_most_private": "أكثر التطبيقات خصوصية",
        "sidebar_safest_vpns": "أكثر VPN أمانًا",
        "audit_no": "لم ينشر {name} تدقيقاً مستقلاً للخصوصية",
        "audit_yes": "تم تدقيق {name} بشكل مستقل للتحقق من ادعاءات الخصوصية",
        "eyes_five": "ضمن تحالف Five Eyes للمراقبة",
        "eyes_outside": "خارج جميع تحالفات Eyes للمراقبة — ميزة للخصوصية",
        "undisclosed_jurisdiction": "ولاية قضائية غير معلنة",
        "serving_users": "يخدم",
        "privacy_assessment": "تقييم الخصوصية",
        "sidebar_recently": "تم تحليلها مؤخراً",
        "sidebar_browse": "تصفح الفئات",
        "sidebar_popular_in": "شائع في",
        "vpn_logging_audited": "سياسة التسجيل: سياسة عدم الاحتفاظ بالسجلات مدققة بشكل مستقل. وفقًا لتقارير التدقيق المستقلة، لا يقوم {name} بتخزين سجلات الاتصال أو نشاط التصفح أو استعلامات DNS.",
        "vpn_server_infra": "البنية التحتية للخوادم",
        "vpn_significant": "هذا أمر مهم لأن مزودي VPN في الولايات القضائية غير المتحالفة لا يخضعون لقوانين الاحتفاظ بالبيانات الإلزامية أو اتفاقيات تبادل المعلومات الاستخباراتية.",
        "vpn_outside_eyes": "خارج تحالفات المراقبة العيون الخمس والتسع والأربع عشرة",
        "vpn_jurisdiction": "الولاية القضائية",
        "vpn_operates_under": "يعمل تحت",
        "xlink_av_desc": "تصنيف مضادات الفيروسات المستقل بناءً على AV-TEST",
        "xlink_safest_av": "أكثر برامج مكافحة الفيروسات أمانًا",
        "xlink_hosting_desc": "تصنيف مزودي الاستضافة المستقل",
        "xlink_safest_hosting": "أكثر خدمات الاستضافة أمانًا",
        "xlink_crypto_desc": "تصنيف أمان بورصات الكريبتو المستقل",
        "xlink_safest_crypto": "أكثر بورصات الكريبتو أمانًا",
        "xlink_access_secure_desc": "استخدم VPN عند الوصول إلى أدوات SaaS على Wi-Fi عام",
        "xlink_access_secure": "الوصول إلى أدواتك بأمان",
        "xlink_secure_saas_desc": "استخدم مدير كلمات مرور لبيانات اعتماد SaaS",
        "xlink_secure_saas": "أمّن تسجيلات دخول SaaS",
        "xlink_secure_creds_desc": "استخدم مدير كلمات مرور لبيانات اعتماد الاستضافة والخادم",
        "xlink_secure_creds": "أمّن بيانات اعتمادك",
        "xlink_protect_server_desc": "أضف VPN للإدارة عن بُعد الآمنة",
        "xlink_protect_server": "احمِ خادمك",
        "xlink_secure_passwords_desc": "استخدم مدير كلمات مرور لحماية حساباتك",
        "xlink_secure_passwords": "أمّن كلمات المرور الخاصة بك",
        "xlink_add_vpn_av": "أضف VPN للتصفح المشفر مع مضاد الفيروسات",
        "xlink_add_malware_desc": "الحماية من مسجلات المفاتيح وسرقة بيانات الاعتماد",
        "xlink_add_malware": "إضافة حماية من البرمجيات الخبيثة",
        "xlink_add_av_vpn": "أكمل أمانك بمضاد الفيروسات مع VPN الخاص بك",
        "xlink_add_av": "إضافة حماية مضاد الفيروسات",
        "xlink_add_vpn_pm": "أضف VPN إلى مدير كلمات المرور الخاص بك",
        "xlink_add_pm_vpn": "أضف مدير كلمات مرور إلى VPN الخاص بك للحماية الكاملة",
        "xlink_complete_security": "أكمل أمانك",
        "xlink_complete_privacy": "أكمل إعداد خصوصيتك",
        "type_steam": "لعبة Steam",
        "type_android": "تطبيق Android",
        "type_website_builder": "منشئ مواقع",
        "type_crypto": "بورصة عملات مشفرة",
        "type_password_manager": "مدير كلمات المرور",
        "type_antivirus": "برنامج مكافحة فيروسات",
        "type_hosting": "مزود استضافة",
        "type_saas": "منصة SaaS",
        "type_npm": "حزمة npm",
        "type_vpn": "خدمة VPN",
        "based_on_dims": "بناءً على {dims} أبعاد بيانات مستقلة",
        "with_trust_score": "بدرجة ثقة Nerq {score}/100 ({grade})",
        "is_a_type": "هو {type}",
        "rec_wordpress": "موصى به للاستخدام في WordPress",
        "rec_use": "موصى به للاستخدام",
        "rec_play": "موصى به للعب",
        "rec_general": "موصى به للاستخدام العام",
        "rec_production": "موصى به للاستخدام في الإنتاج",
        "rec_privacy": "موصى به للاستخدام المراعي للخصوصية",
        "score_based_dims": "التقييم مبني على {dims}.",
        "yes_safe_short": "نعم، هو آمن للاستخدام.",
        "security_analysis": "تحليل الأمان", "privacy_report": "تقرير الخصوصية", "similar_in_registry": "{registry} مشابهة حسب درجة الثقة", "see_all_best": "عرض جميع {registry} الأكثر أمانًا",
        "pv_grade": "الدرجة {grade}", "pv_body": "بناءً على تحليل {dims} أبعاد للثقة، يُعتبر {verdict}.", "pv_vulns": "مع {count} ثغرات أمنية معروفة", "pv_updated": "آخر تحديث: {date}.", "pv_safe": "آمنًا للاستخدام", "pv_generally_safe": "آمنًا بشكل عام مع بعض المخاوف", "pv_notable_concerns": "لديه مخاوف أمنية ملحوظة", "pv_significant_risks": "لديه مخاطر أمنية كبيرة", "pv_unsafe": "غير آمن",
        "h2q_trust_score": "ما هي درجة ثقة {name}؟", "h2q_key_findings": "ما هي النتائج الأمنية الرئيسية لـ {name}؟", "h2q_details": "ما هو {name} ومن يديره؟",
        "ans_trust": "حصل {name} على درجة ثقة Nerq تبلغ {score}/100 بدرجة {grade}. يعتمد هذا التقييم على {dims} أبعاد مُقاسة بشكل مستقل.", "ans_findings_strong": "أقوى إشارة لـ {name} هي {signal} بدرجة {signal_score}/100.", "ans_no_vulns": "لم يتم اكتشاف أي ثغرات أمنية معروفة.", "ans_has_vulns": "تم تحديد {count} ثغرات أمنية معروفة.", "ans_verified": "يستوفي عتبة التحقق من Nerq البالغة 70+.", "ans_not_verified": "لم يصل بعد إلى عتبة التحقق من Nerq البالغة 70+.",
        "title_safe": "هل {name} آمن؟ تحليل مستقل للثقة والأمان {year} | Nerq",
        "title_safe_visit": "هل {name} آمن للزيارة؟ درجة الأمان {year} ودليل السفر | Nerq",
        "title_charity": "هل {name} مؤسسة خيرية موثوقة؟ تحليل الثقة {year} | Nerq",
        "title_ingredient": "هل {name} آمن؟ تحليل الصحة والسلامة {year} | Nerq",
        "h1_safe": "هل {name} آمن؟",
        "h1_safe_visit": "هل {name} آمن للزيارة؟",
        "h1_trustworthy_charity": "هل {name} مؤسسة خيرية موثوقة؟",
        "h1_ingredient_safe": "هل {name} آمن؟",
        "breadcrumb_safety": "تقارير السلامة",
        "trust_score_breakdown": "تفاصيل درجة الثقة",
        "safety_score_breakdown": "تفاصيل درجة السلامة",
        "key_findings": "النتائج الرئيسية",
        "key_safety_findings": "نتائج السلامة الرئيسية",
        "details": "التفاصيل",
        "detailed_score_analysis": "تحليل مفصل للدرجة",
        "faq": "الأسئلة الشائعة",
        "community_reviews": "مراجعات المجتمع",
        "regulatory_compliance": "الامتثال التنظيمي",
        "how_calculated": "كيف حسبنا هذه الدرجة",
        "popular_alternatives": "بدائل شائعة في {category}",
        "safer_alternatives": "بدائل أكثر أمانًا",
        "across_platforms": "{name} عبر المنصات",
        "safety_guide": "دليل السلامة: {name}",
        "what_is": "ما هو {name}؟",
        "key_concerns": "مخاوف السلامة الرئيسية لـ {type}",
        "how_to_verify": "كيفية التحقق من السلامة",
        "trust_assessment": "تقييم الثقة",
        "what_data_collect": "ما البيانات التي يجمعها {name}؟",
        "is_secure": "هل {name} آمن؟",
        "is_safe_visit": "هل {name} آمن للزيارة؟",
        "is_legit_charity": "هل {name} مؤسسة خيرية شرعية؟",
        "crime_safety": "الجريمة والسلامة في {name}",
        "financial_transparency": "الشفافية المالية لـ {name}",
        "yes_safe": "نعم، {name} آمن للاستخدام.",
        "use_caution": "استخدم {name} بحذر.",
        "exercise_caution": "توخَّ الحذر مع {name}.",
        "significant_concerns": "{name} لديه مخاوف ثقة كبيرة.",
        "passes_verified": "يجتاز عتبة Nerq المُوَثَّقة",
        "below_verified": "دون عتبة Nerq المُوَثَّقة",
        "significant_gaps": "تم اكتشاف فجوات ثقة كبيرة",
        "security": "الأمان",
        "compliance": "الامتثال",
        "maintenance": "الصيانة",
        "documentation": "التوثيق",
        "popularity": "الشعبية",
        "overall_trust": "الثقة الشاملة",
        "security_desc": "فحص الثغرات الأمنية ومراجعة CVE والتحقق من التبعيات.",
        "maintenance_desc": "تاريخ الالتزامات ونشاط المشرفين وتكرار الإصدارات.",
        "documentation_desc": "جودة الملف التعريفي وأمثلة الكود ومرجع API.",
        "overall_trust_desc": "التقييم المجمع بناءً على جميع الإشارات المتاحة.",
        "author_label": "المؤلف",
        "category_label": "الفئة",
        "source_label": "المصدر",
        "stars_label": "النجوم",
        "global_rank_label": "الترتيب العالمي",
        "last_analyzed": "آخر تحليل",
        "machine_readable": "قراءة آلية",
        "data_sourced": "البيانات مصدرها",
        "disclaimer": "درجات ثقة Nerq هي تقييمات آلية مبنية على إشارات متاحة للعموم. وهي ليست توصيات أو ضمانات. قم دائمًا بإجراء العناية الواجبة الخاصة بك.",
        "same_developer": "منتجات من نفس المطور",
        "Safe": "آمن",
        "Use Caution": "استخدم بحذر",
        "Avoid": "تجنب",
        "not_analyzed_title": "لم يتم تحليل {name} بعد — سيتم تحليله قريبًا | Nerq",
        "not_analyzed_h1": "{name} — لم يتم تحليله بعد",
        "not_analyzed_body": "لم يتم تحليل {name} بعد بواسطة Nerq. لقد تم وضعه في قائمة الانتظار وقد يظهر في تحديث مستقبلي.",
        "not_analyzed_api": "تحقق من API مباشرة",
        "not_analyzed_browse": "تصفح الكيانات التي قمنا بتحليلها بالفعل",
        "not_analyzed_no_score": "هذه الصفحة لا تحتوي على درجة ثقة لأننا لم نحلل هذا الكيان بعد.",
        "not_analyzed_no_fabricate": "لا يختلق Nerq أبدًا التقييمات. إذا كنت تعتقد أن هذا الكيان يجب تغطيته، فقد يظهر في تحديث مستقبلي.",
    },
}


def _t(key, lang="en", **kwargs):
    """Get translated string. Falls back to English if no translation exists."""
    if lang != "en":
        template = _TRANSLATIONS.get(lang, {}).get(key)
        if template:
            if kwargs:
                try:
                    return template.format(**kwargs)
                except (KeyError, IndexError):
                    pass
            else:
                return template
    # English fallback
    template = _STRINGS.get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template

# Manual override mapping: slug/search term → exact agent name in DB.
# Fixes fuzzy matching that returns wrong agents (e.g., "cursor" → CursorTouch).
_SLUG_OVERRIDES = {
    # ── Merged org/repo slugs (bots strip "/" → "orgnamereponame") ──
    # Map back to the canonical name used in _SLUG_OVERRIDES or DB
    "ollamaollama": "ollama/ollama",
    "langgeniusdify": "langgenius/dify",
    "continuedevcontinue": "continuedev/continue",
    "ansibleansible": "ansible",
    "flowiseaiflowise": "FlowiseAI/Flowise",
    "microsoftqlib": "microsoft/qlib",
    "openclawopenclaw": "OpenClaw/OpenClaw",
    "obrasuperpowers": "obra/superpowers",
    "langchain-ailangchain": "langchain-ai/langchain",
    "langchainailangchain": "langchain-ai/langchain",
    "significant-gravitasautogpt": "Significant-Gravitas/AutoGPT",
    "significantgravitasautogpt": "Significant-Gravitas/AutoGPT",
    "n8n-ion8n": "n8n-io/n8n",
    "n8nion8n": "n8n-io/n8n",
    "promptfoo-promptfoo": "promptfoo/promptfoo",
    "promptfoopromptfoo": "promptfoo/promptfoo",
    "langflow-ailangflow": "langflow-ai/langflow",
    "langflowailangflow": "langflow-ai/langflow",
    "lencxchatgpt": "lencx/ChatGPT",
    "automatic1111stable-diffusion-webui": "AUTOMATIC1111/stable-diffusion-webui",
    "automatic1111stablediffusionwebui": "AUTOMATIC1111/stable-diffusion-webui",
    "corentinjreal-time-voice-cloning": "CorentinJ/Real-Time-Voice-Cloning",
    "zhayujiechatgpt-on-wechat": "zhayujie/chatgpt-on-wechat",
    "openbb-financeopenbb": "OpenBB-finance/OpenBB",
    "openbbfinanceopenbb": "OpenBB-finance/OpenBB",
    "mlflow-mlflow": "mlflow/mlflow",
    "mlflowmlflow": "mlflow/mlflow",
    "hiyougallamafactory": "hiyouga/LLaMA-Factory",
    "unslothaiunsloth": "unslothai/unsloth",
    "mindsdbmindsdb": "mindsdb/mindsdb",
    "googlemagika": "google/magika",
    "firecrawlfirecrawl": "mendableai/firecrawl",
    "posthogposthog": "PostHog/posthog",
    "tooljettooljet": "ToolJet/ToolJet",
    "anthropicsclaude-code": "claude-code",
    "anthropicsclaudecode": "claude-code",
    "janhqjan": "Jan",
    "githubcopilot-cli": "GitHub Copilot",
    "githubcopilotcli": "GitHub Copilot",
    "fosowlagenticseek": "FosowlAgenticSeek",
    "pocketpawpocketpaw": "PocketPaw/PocketPaw",
    "gptmegptme": "jmorganca/gptme",
    "lawglancelawglance": "LawGlance/LawGlance",
    "rlinf-rlinf": "rlinf/rlinf",
    "rlinfrinf": "rlinf/rlinf",
    "usestrixstrix": "useStrix/strix",
    "binhnguyennusawesome-scalability": "binhnguyennus/awesome-scalability",
    "developer-ycs-video-courses": "Developer-Y/cs-video-courses",
    "unicomai-wanwu": "unicom-ai/wanwu",

    # Canonical GitHub repos — these map to exact DB entries
    "langchain": "langchain-ai/langchain",
    "langgraph": "LangGraph",
    "crewai": "crewAIInc/crewAI",
    "crew-ai": "crewAIInc/crewAI",
    "autogen": "microsoft/autogen",
    "llamaindex": "run-llama/llama_index",
    "llama-index": "run-llama/llama_index",
    "cursor": "getcursor/cursor",
    "cursor-ide": "getcursor/cursor",
    "semantic-kernel": "microsoft/semantic-kernel",
    "haystack": "deepset-ai/haystack",
    "smolagents": "huggingface/smolagents",
    "dspy": "stanfordnlp/dspy",
    "openai": "openai/openai-python",
    "anthropic": "anthropics/anthropic-sdk-python",
    "devin": "cognition-labs/devin",
    "swe-agent": "princeton-nlp/SWE-agent",
    "continue": "continuedev/continue",
    "continue-dev": "continuedev/continue",
    "mastra": "mastra-ai/mastra",
    "autogpt": "Significant-Gravitas/AutoGPT",
    "auto-gpt": "Significant-Gravitas/AutoGPT",
    "n8n": "n8n-io/n8n",
    # Display-name entries (no canonical repo in DB yet)
    "lovable": "Lovable",
    "bolt": "Bolt",
    "bolt-new": "Bolt",
    "windsurf": "Windsurf",
    "v0": "v0",
    "replit": "Replit",
    "replit-agent": "Replit",
    "copilot": "GitHub Copilot",
    "github-copilot": "GitHub Copilot",
    "claude-code": "claude-code",
    "claude": "Claude",
    "chatgpt": "ChatGPT",
    "gpt-4": "GPT-4",
    "gemini": "Gemini",
    "zapier": "Zapier",
    "make": "Make",
    "opendevin": "OpenDevin",
    "aider": "aider",
    "cline": "cline/cline",
    "tabby": "Tabby",
    "tabnine": "Tabnine",
    "codeium": "Codeium",
    "supermaven": "Supermaven",
    "sourcegraph": "Sourcegraph",
    "phind": "Phind",
    "perplexity": "Perplexity",
    "huggingface": "HuggingFace",
    "hugging-face": "HuggingFace",
    "vercel-ai": "Vercel AI SDK",
    "metagpt": "MetaGPT",
    "babyagi": "BabyAGI",
    "baby-agi": "BabyAGI",
    "superagent": "SuperAgent",
    "flowise": "Flowise",
    "dify": "Dify",
    "langflow": "Langflow",
    "chainlit": "Chainlit",
    "streamlit": "Streamlit",
    "gradio": "Gradio",
    "fastapi": "FastAPI",
    "ollama": "ollama/ollama",
    "lmstudio": "LM Studio",
    "lm-studio": "LM Studio",
    "jan": "Jan",
    "msty": "Msty",
    "open-webui": "Open WebUI",
    "anything-llm": "AnythingLLM",
    "privateGPT": "PrivateGPT",
    "privategpt": "PrivateGPT",
    "localai": "LocalAI",
    "vllm": "vLLM",
    "tgi": "TGI",
    "llamacpp": "llama.cpp",
    "llama-cpp": "llama.cpp",
    "mlx": "MLX",
    "transformers": "transformers",
    "diffusers": "diffusers",
    "comfyui": "Comfy-Org/ComfyUI",
    "automatic1111": "AUTOMATIC1111",
    "midjourney": "Midjourney",
    "stable-diffusion": "Stable Diffusion",
    "dall-e": "DALL-E",
    "whisper": "Whisper",
    "elevenlabs": "ElevenLabs",
    "bark": "Bark",
}

# Clean display names for top tools.
# Maps DB name (or override value) → human-friendly display name for H1/title.
_DISPLAY_NAMES = {
    "getcursor/cursor": "Cursor",
    "ChatGPT": "ChatGPT",
    "Windsurf": "Windsurf",
    "Bolt": "Bolt",
    "continuedev/continue": "Continue",
    "cline/cline": "Cline",
    "ollama/ollama": "Ollama",
    "Comfy-Org/ComfyUI": "ComfyUI",
    "GitHub Copilot": "GitHub Copilot",
    "GitHub Copilot CLI": "GitHub Copilot",
    "langchain-ai/langchain": "LangChain",
    "Claude": "Claude",
    "Gemini": "Gemini",
    "openai/openai-python": "OpenAI",
    "n8n-io/n8n": "n8n",
    "HuggingFace": "Hugging Face",
    "Stable Diffusion": "Stable Diffusion",
    "crewAIInc/crewAI": "CrewAI",
    "Significant-Gravitas/AutoGPT": "AutoGPT",
    "run-llama/llama_index": "LlamaIndex",
    "cognition-labs/devin": "Devin",
    "pydantic/pydantic-ai": "PydanticAI",
    "langgenius/dify": "Dify",
    "agno-agi/agno": "Agno",
    "ComposioHQ/composio": "Composio",
    "microsoft/autogen": "AutoGen",
    "promptfoo/promptfoo": "Promptfoo",
    "cli": "Google Workspace CLI",
    # Consumer products (VPN, apps, games)
    "NordVPN": "NordVPN",
    "Nordvpn": "NordVPN",
    "ExpressVPN": "ExpressVPN",
    "Expressvpn": "ExpressVPN",
    "Surfshark": "Surfshark",
    "ProtonVPN": "ProtonVPN",
    "Protonvpn": "ProtonVPN",
    "CyberGhost": "CyberGhost VPN",
    "TikTok": "TikTok",
    "TikTok - Videos, Shop & LIVE": "TikTok",
    "WhatsApp": "WhatsApp",
    "WhatsApp Messenger": "WhatsApp",
    "Instagram": "Instagram",
    "Telegram": "Telegram",
    "Signal": "Signal",
    "Spotify": "Spotify",
    "Discord": "Discord",
    "Minecraft": "Minecraft",
    "Roblox": "Roblox",
    "Fortnite": "Fortnite",
}

# Slug mapping: slug -> agent info dict
_slug_map = {}
_slug_list = []

# In-memory page cache
_page_cache = {}
_CACHE_TTL = 3600  # 1 hour
_CACHE_MAX = 5000  # ~90MB at 18KB per page


def _load_slugs():
    global _slug_map, _slug_list
    if _slug_map:
        return
    try:
        with open(SLUGS_PATH) as f:
            _slug_list = json.load(f)
        _slug_map = {a["slug"]: a for a in _slug_list}
        logger.info(f"Loaded {len(_slug_map)} agent safety slugs")
    except Exception as e:
        logger.error(f"Failed to load agent safety slugs: {e}")


def _esc(s):
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _esc_json(s):
    if not s:
        return ""
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


# ================================================================
# REGISTRY-SPECIFIC PAGE CONTENT (GEO-optimized)
# Controls: first sentence, FAQ questions, schema type, field visibility, data sources
# ================================================================

REGISTRY_PAGE = {
    "vpn": {
        "entity_word": "VPN service",
        "schema_type": "SoftwareApplication",
        "schema_extra": {"applicationCategory": "VPN Service"},
        "faq_q1": "Is {name} safe?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are the best alternatives to {name}?",
        "faq_q4": "Does {name} log my data?",
        "faq_q5": "{name} vs {alt}: which is safer?",
        "hide_fields": {"stars", "frameworks", "protocols", "documentation", "maintenance"},
        "data_sources": "jurisdiction databases, independent audit reports, protocol analysis, and incident history",
        "recommendation": "recommended for privacy-conscious use",
    },
    "ios": {
        "entity_word": "iOS app",
        "schema_type": "MobileApplication",
        "schema_extra": {"operatingSystem": "iOS", "applicationCategory": "MobileApplication"},
        "faq_q1": "Is {name} safe?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are safer alternatives to {name}?",
        "faq_q4": "Is {name} safe for kids?",
        "faq_q5": "Does {name} collect my data?",
        "hide_fields": {"stars", "frameworks", "protocols"},
        "data_sources": "App Store metadata, privacy labels, permissions analysis, and developer history",
        "recommendation": "recommended for general use",
    },
    "android": {
        "entity_word": "Android app",
        "schema_type": "MobileApplication",
        "schema_extra": {"operatingSystem": "Android", "applicationCategory": "MobileApplication"},
        "faq_q1": "Is {name} safe?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are safer alternatives to {name}?",
        "faq_q4": "Is {name} safe for kids?",
        "faq_q5": "Does {name} track me?",
        "hide_fields": {"stars", "frameworks", "protocols"},
        "data_sources": "Google Play metadata, Data Safety section, Exodus Privacy tracker analysis, and user ratings",
        "recommendation": "recommended for general use",
    },
    "steam": {
        "entity_word": "game",
        "schema_type": "VideoGame",
        "schema_extra": {"gamePlatform": "PC"},
        "faq_q1": "Is {name} safe?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are safer alternatives to {name}?",
        "faq_q4": "Is {name} safe for kids?",
        "faq_q5": "Does {name} have microtransactions?",
        "hide_fields": {"stars", "frameworks", "protocols", "documentation", "maintenance"},
        "data_sources": "Steam Store metadata, user reviews, age ratings, and monetization analysis",
        "recommendation": "recommended for play",
    },
    "chrome": {
        "entity_word": "Chrome extension",
        "schema_type": "SoftwareApplication",
        "schema_extra": {"applicationCategory": "BrowserExtension"},
        "faq_q1": "Is {name} safe?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are safer alternatives to {name}?",
        "faq_q4": "What permissions does {name} need?",
        "faq_q5": "Is {name}'s publisher verified?",
        "hide_fields": {"stars", "frameworks", "protocols"},
        "data_sources": "Chrome Web Store metadata, permissions analysis, developer verification, and update history",
        "recommendation": "recommended for use",
    },
    "firefox": {
        "entity_word": "Firefox add-on",
        "schema_type": "SoftwareApplication",
        "schema_extra": {"applicationCategory": "BrowserExtension"},
        "faq_q1": "Is {name} safe?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are safer alternatives to {name}?",
        "faq_q4": "What permissions does {name} need?",
        "faq_q5": "Is {name} open source?",
        "hide_fields": {"stars", "frameworks", "protocols"},
        "data_sources": "addons.mozilla.org metadata, permissions analysis, and source code availability",
        "recommendation": "recommended for use",
    },
    "vscode": {
        "entity_word": "VS Code extension",
        "schema_type": "SoftwareApplication",
        "schema_extra": {"applicationCategory": "DeveloperApplication"},
        "faq_q1": "Is {name} safe?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are safer alternatives to {name}?",
        "faq_q4": "Does {name} collect telemetry?",
        "faq_q5": "Is {name}'s publisher verified?",
        "hide_fields": {"frameworks", "protocols"},
        "data_sources": "VS Code Marketplace metadata, publisher verification, installs, and ratings",
        "recommendation": "recommended for use",
    },
    "wordpress": {
        "entity_word": "WordPress plugin",
        "schema_type": "SoftwareApplication",
        "schema_extra": {"applicationCategory": "Plugin"},
        "faq_q1": "Is {name} safe?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are safer alternatives to {name}?",
        "faq_q4": "Does {name} have known vulnerabilities?",
        "faq_q5": "Is {name} compatible with the latest WordPress?",
        "hide_fields": {"stars", "frameworks", "protocols"},
        "data_sources": "WordPress.org metadata, WPScan vulnerability database, active installs, and update history",
        "recommendation": "recommended for use in WordPress",
    },
    "npm": {
        "entity_word": "Node.js package",
        "schema_type": "SoftwareSourceCode",
        "schema_extra": {"programmingLanguage": "JavaScript"},
        "faq_q1": "Is {name} safe to use?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are safer alternatives to {name}?",
        "faq_q4": "Does {name} have known vulnerabilities?",
        "faq_q5": "How actively maintained is {name}?",
        "hide_fields": set(),
        "data_sources": "npm registry, GitHub repository, NVD, OSV.dev, and OpenSSF Scorecard",
        "recommendation": "recommended for production use",
    },
    "pypi": {
        "entity_word": "Python package",
        "schema_type": "SoftwareSourceCode",
        "schema_extra": {"programmingLanguage": "Python"},
        "faq_q1": "Is {name} safe to use?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are safer alternatives to {name}?",
        "faq_q4": "Does {name} have known vulnerabilities?",
        "faq_q5": "How actively maintained is {name}?",
        "hide_fields": set(),
        "data_sources": "PyPI registry, GitHub repository, NVD, OSV.dev, and OpenSSF Scorecard",
        "recommendation": "recommended for production use",
    },
    "crates": {
        "entity_word": "Rust crate",
        "schema_type": "SoftwareSourceCode",
        "schema_extra": {"programmingLanguage": "Rust"},
        "faq_q1": "Is {name} safe to use?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are safer alternatives to {name}?",
        "faq_q4": "Does {name} have known vulnerabilities?",
        "faq_q5": "Does {name} use unsafe code?",
        "hide_fields": set(),
        "data_sources": "crates.io registry, GitHub, NVD, and RustSec advisory database",
        "recommendation": "recommended for production use",
    },
    "go": {
        "entity_word": "Go module",
        "schema_type": "SoftwareSourceCode",
        "schema_extra": {"programmingLanguage": "Go"},
        "faq_q1": "Is {name} safe to use?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are safer alternatives to {name}?",
        "faq_q4": "Does {name} have known vulnerabilities?",
        "faq_q5": "How actively maintained is {name}?",
        "hide_fields": set(),
        "data_sources": "pkg.go.dev, GitHub, NVD, and Go vulnerability database",
        "recommendation": "recommended for production use",
    },
    "nuget": {
        "entity_word": "NuGet package",
        "schema_type": "SoftwareSourceCode",
        "schema_extra": {"programmingLanguage": "C#"},
        "faq_q1": "Is {name} safe to use?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are safer alternatives to {name}?",
        "faq_q4": "Does {name} have known vulnerabilities?",
        "faq_q5": "Is {name}'s publisher verified?",
        "hide_fields": set(),
        "data_sources": "nuget.org, GitHub, and NVD",
        "recommendation": "recommended for production use",
    },
    "gems": {
        "entity_word": "Ruby gem",
        "schema_type": "SoftwareSourceCode",
        "schema_extra": {"programmingLanguage": "Ruby"},
        "faq_q1": "Is {name} safe to use?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are safer alternatives to {name}?",
        "faq_q4": "Does {name} have known vulnerabilities?",
        "faq_q5": "How actively maintained is {name}?",
        "hide_fields": set(),
        "data_sources": "rubygems.org, GitHub, and NVD",
        "recommendation": "recommended for production use",
    },
    "packagist": {
        "entity_word": "PHP package",
        "schema_type": "SoftwareSourceCode",
        "schema_extra": {"programmingLanguage": "PHP"},
        "faq_q1": "Is {name} safe to use?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are safer alternatives to {name}?",
        "faq_q4": "Does {name} have known vulnerabilities?",
        "faq_q5": "How actively maintained is {name}?",
        "hide_fields": set(),
        "data_sources": "packagist.org, GitHub, and NVD",
        "recommendation": "recommended for production use",
    },
    "homebrew": {
        "entity_word": "Homebrew formula",
        "schema_type": "SoftwareApplication",
        "schema_extra": {"applicationCategory": "CommandLineTool"},
        "faq_q1": "Is {name} safe to use?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are safer alternatives to {name}?",
        "faq_q4": "Is {name} actively maintained?",
        "faq_q5": "How was {name} reviewed?",
        "hide_fields": {"stars"},
        "data_sources": "Homebrew formulae database and GitHub (homebrew-core)",
        "recommendation": "recommended for use",
    },
    "website": {
        "entity_word": "website",
        "schema_type": "WebSite",
        "schema_extra": {},
        "faq_q1": "Is {name} safe?",
        "faq_q2": "Is {name} legit?",
        "faq_q3": "What are safer alternatives to {name}?",
        "faq_q4": "Is {name} a scam?",
        "faq_q5": "Does {name} protect my data?",
        "hide_fields": {"stars", "frameworks", "protocols", "documentation", "maintenance"},
        "data_sources": "domain registration, SSL certificates, Tranco ranking, and web reputation databases",
        "recommendation": "safe to visit",
    },
    "country": {
        "entity_word": "travel destination",
        "schema_type": "Country",
        "schema_extra": {},
        "faq_q1": "Is {name} safe to visit?",
        "faq_q2": "Is {name} safe for solo female travelers?",
        "faq_q3": "Is tap water safe in {name}?",
        "faq_q4": "What vaccinations do I need for {name}?",
        "faq_q5": "Is {name} safe for families?",
        "hide_fields": {"stars", "frameworks", "protocols", "documentation", "maintenance"},
        "data_sources": "Global Peace Index, Transparency International, US State Department, UK FCDO, WHO health data",
        "recommendation": "assessed for travel safety",
    },
    "charity": {
        "entity_word": "charity",
        "schema_type": "NGO",
        "schema_extra": {},
        "faq_q1": "Is {name} a legitimate charity?",
        "faq_q2": "Is {name} a scam?",
        "faq_q3": "How much of my donation goes to the cause at {name}?",
        "faq_q4": "Is {name} tax-deductible?",
        "faq_q5": "What are alternatives to {name}?",
        "hide_fields": {"stars", "frameworks", "protocols", "documentation", "maintenance"},
        "data_sources": "ProPublica Nonprofit Explorer, Charity Navigator, GuideStar, BBB Wise Giving Alliance, IRS Form 990",
        "recommendation": "evaluated for donor trust",
    },
    "saas": {
        "entity_word": "SaaS platform",
        "schema_type": "SoftwareApplication",
        "schema_extra": {"applicationCategory": "BusinessApplication"},
        "faq_q1": "Is {name} safe?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are the best alternatives to {name}?",
        "faq_q4": "Is {name} GDPR compliant?",
        "faq_q5": "Does {name} sell my data?",
        "hide_fields": {"stars", "frameworks", "protocols"},
        "data_sources": "company registration, SOC 2/ISO 27001 certifications, privacy policy analysis, and app store metadata",
        "recommendation": "recommended for business use",
    },
    "ai_tool": {
        "entity_word": "AI tool",
        "schema_type": "SoftwareApplication",
        "schema_extra": {"applicationCategory": "ArtificialIntelligence"},
        "faq_q1": "Is {name} safe to use?",
        "faq_q2": "What is {name}'s trust score?",
        "faq_q3": "What are the best alternatives to {name}?",
        "faq_q4": "Does {name} use my data for training?",
        "faq_q5": "Is {name} safe for confidential work?",
        "hide_fields": {"stars", "frameworks", "protocols"},
        "data_sources": "privacy policy analysis, data handling practices, company background, and security certifications",
        "recommendation": "recommended for use",
    },
}

_DEFAULT_REGISTRY_PAGE = {
    "entity_word": "software tool",
    "schema_type": "SoftwareApplication",
    "schema_extra": {"applicationCategory": "Software"},
    "faq_q1": "Is {name} safe to use?",
    "faq_q2": "What is {name}'s trust score?",
    "faq_q3": "What are safer alternatives to {name}?",
    "faq_q4": "How often is {name}'s safety score updated?",
    "faq_q5": "Can I use {name} in a regulated environment?",
    "hide_fields": set(),
    "data_sources": "multiple public sources including package registries, GitHub, NVD, OSV.dev, and OpenSSF Scorecard",
    "recommendation": "recommended for use",
}


def _get_registry_page(source):
    """Get registry-specific page config."""
    return REGISTRY_PAGE.get(source, _DEFAULT_REGISTRY_PAGE)


def _grade_pill(grade):
    if not grade:
        return "pill-gray"
    g = grade.upper()
    if g.startswith("A"):
        return "pill-green"
    if g.startswith("B"):
        return "pill-yellow"
    return "pill-red"


def _trust_assessment(name, score, source=""):
    n = _esc(name)
    _s = (source or "").lower()
    _entity_word = {
        "npm": "packages", "pypi": "packages", "crates": "crates", "go": "modules",
        "gems": "gems", "packagist": "packages", "nuget": "packages", "homebrew": "packages",
        "wordpress": "plugins", "vscode": "extensions", "chrome": "extensions", "firefox": "extensions",
        "ios": "apps", "android": "apps", "steam": "games", "vpn": "services",
    }.get(_s, "tools")
    if score >= 85:
        return f"Highly Trusted &mdash; {n} ranks among the top {_entity_word} with exceptional trust signals across security, maintenance, and ecosystem metrics. It has been independently assessed by Nerq and demonstrates consistently strong quality indicators."
    if score >= 70:
        return f"Trusted &mdash; {n} demonstrates strong trust signals. It meets the threshold for Nerq Verified status, indicating solid security practices, active maintenance, and a healthy ecosystem presence."
    if score >= 55:
        return f"Moderate &mdash; {n} shows mixed trust signals. Some areas are strong while others could be improved. We recommend reviewing the full safety report before integrating it into production workflows."
    if score >= 40:
        return f"Caution &mdash; {n} has below-average trust signals. There may be concerns around maintenance frequency, security practices, or ecosystem adoption. Proceed with care and conduct additional due diligence."
    return f"Low Trust &mdash; {n} has significant trust concerns across multiple dimensions. We recommend thorough investigation before use. Consider higher-rated alternatives in the same category."


def _assessment_short(name, score):
    if score >= 85:
        return "Highly trusted."
    if score >= 70:
        return "Trusted — strong signals."
    if score >= 55:
        return "Moderate — mixed signals."
    if score >= 40:
        return "Caution — below average."
    return "Low trust — significant concerns."


_TRUST_COLS = """
    name,
    COALESCE(trust_score_v2, trust_score) as trust_score,
    trust_grade,
    category,
    description,
    source_url,
    source,
    stars,
    author,
    first_indexed,
    is_verified,
    frameworks,
    protocols,
    trust_components,
    compliance_score,
    eu_risk_class,
    documentation_score,
    activity_score,
    security_score,
    popularity_score
"""


# Consumer product overrides: slug → (registry, name_pattern)
# For popular products whose DB name differs from the common slug
_CONSUMER_OVERRIDES = {
    "tiktok": ("android", "TikTok%"),
    "whatsapp": ("android", "WhatsApp Messenger"),
    "signal": ("android", "Signal Private Messenger"),
    "instagram": ("android", "Instagram"),
    "facebook": ("android", "Facebook"),
    "snapchat": ("android", "Snapchat"),
    "twitter": ("android", "Twitter"),
    "youtube": ("android", "YouTube"),
    "spotify": ("android", "Spotify%"),
    "netflix": ("android", "Netflix"),
    "telegram": ("android", "Telegram"),
    "discord": ("android", "Discord%"),
    "pinterest": ("android", "Pinterest"),
    "reddit": ("android", "Reddit"),
    "linkedin": ("android", "LinkedIn%"),
    "uber": ("android", "Uber%"),
    "amazon": ("android", "Amazon%Shopping%"),
    "zoom": ("android", "Zoom%"),
    "chrome": ("android", "Google Chrome"),
    "gmail": ("android", "Gmail"),
    "nordvpn": ("vpn", "NordVPN"),
    "expressvpn": ("vpn", "ExpressVPN"),
    "mullvad": ("vpn", "Mullvad VPN"),
    "mullvadvpn": ("vpn", "Mullvad VPN"),
    "protonvpn": ("vpn", "ProtonVPN"),
    "surfshark": ("vpn", "Surfshark"),
    "private-internet-access": ("vpn", "PIA"),
    "privateinternetaccess": ("vpn", "PIA"),
    "pia": ("vpn", "PIA"),
    "ivpn": ("vpn", "IVPN"),
    "cyberghost": ("vpn", "CyberGhost%"),
    "windscribe": ("vpn", "Windscribe%"),
    "tunnelbear": ("vpn", "TunnelBear%"),
    "minecraft": ("android", "Minecraft%"),
    "fortnite": ("android", "Fortnite"),
    "roblox": ("android", "Roblox"),
    "notion": ("android", "Notion%"),
    "dropbox": ("android", "Dropbox%"),
    "slack": ("android", "Slack%"),
    "google": ("android", "Google"),
    "maps": ("android", "Google Maps%"),
    "gmail": ("android", "Gmail"),
    "chrome": ("android", "Google Chrome"),
    "firefox": ("android", "Firefox%"),
    "edge": ("android", "Microsoft Edge%"),
    "outlook": ("android", "Microsoft Outlook%"),
    "teams": ("android", "Microsoft Teams%"),
    "paypal": ("android", "PayPal%"),
    "venmo": ("android", "Venmo%"),
    "cashapp": ("android", "Cash App%"),
    "duolingo": ("android", "Duolingo%"),
    "shazam": ("android", "Shazam%"),
    "waze": ("android", "Waze%"),
    "twitch": ("android", "Twitch%"),
    "pinterest": ("android", "Pinterest"),
    "tinder": ("android", "Tinder%"),
    "bumble": ("android", "Bumble%"),
    "hinge": ("android", "Hinge%"),
    # Password managers — resolve to password_manager registry, not chrome extensions
    "1password": ("password_manager", "1Password"),
    "bitwarden": ("password_manager", "Bitwarden"),
    "lastpass": ("password_manager", "LastPass"),
    "dashlane": ("password_manager", "Dashlane"),
    "keeper": ("password_manager", "Keeper"),
    "nordpass": ("password_manager", "NordPass"),
    "keepass": ("password_manager", "KeePass"),
    "protonpass": ("password_manager", "Proton Pass"),
    "proton-pass": ("password_manager", "Proton Pass"),
    "roboform": ("password_manager", "RoboForm"),
    "enpass": ("password_manager", "Enpass"),
    "keepassxc": ("password_manager", "KeePassXC"),
    "true-key": ("password_manager", "True Key"),
    # Hosting providers — resolve to hosting registry
    "wpengine": ("hosting", "WP Engine"),
    "wp-engine": ("hosting", "WP Engine"),
    "siteground": ("hosting", "SiteGround"),
    "bluehost": ("hosting", "Bluehost"),
    "hostinger": ("hosting", "Hostinger"),
    "godaddy": ("hosting", "GoDaddy"),
    "namecheap": ("hosting", "Namecheap"),
    "dreamhost": ("hosting", "DreamHost"),
    "hostgator": ("hosting", "HostGator"),
    "digitalocean": ("hosting", "DigitalOcean"),
    "hetzner": ("hosting", "Hetzner"),
    "netlify": ("hosting", "Netlify"),
    "vercel": ("hosting", "Vercel"),
    "heroku": ("hosting", "Heroku"),
    "kinsta": ("hosting", "Kinsta"),
    "vultr": ("hosting", "Vultr"),
    "linode": ("hosting", "Linode%"),
    "render": ("hosting", "Render"),
    "railway": ("hosting", "Railway"),
    "pantheon": ("hosting", "Pantheon"),
    "liquid-web": ("hosting", "Liquid Web"),
    "liquidweb": ("hosting", "Liquid Web"),
    "flywheel": ("hosting", "Flywheel"),
    "a2-hosting": ("hosting", "A2 Hosting"),
    "inmotion-hosting": ("hosting", "InMotion Hosting"),
    "github-pages": ("hosting", "GitHub Pages"),
    "cloudflare-pages": ("hosting", "Cloudflare Pages"),
    # Antivirus — resolve to antivirus registry
    "norton": ("antivirus", "Norton 360"),
    "norton360": ("antivirus", "Norton 360"),
    "norton-antivirus": ("antivirus", "Norton 360"),
    "mcafee": ("antivirus", "McAfee Total Protection"),
    "mcafee-antivirus": ("antivirus", "McAfee Total Protection"),
    "bitdefender": ("antivirus", "Bitdefender Total Security"),
    "malwarebytes": ("antivirus", "Malwarebytes"),
    "kaspersky": ("antivirus", "Kaspersky"),
    "kaspersky-antivirus": ("antivirus", "Kaspersky"),
    "avast": ("antivirus", "Avast/AVG"),
    "avg": ("antivirus", "Avast/AVG"),
    "avg-antivirus": ("antivirus", "Avast/AVG"),
    "eset": ("antivirus", "ESET NOD32"),
    "eset-nod32": ("antivirus", "ESET NOD32"),
    "windows-defender": ("antivirus", "Windows Defender"),
    "microsoft-defender": ("antivirus", "Windows Defender"),
    "crowdstrike": ("antivirus", "CrowdStrike Falcon"),
    "sentinelone": ("antivirus", "SentinelOne"),
    "trend-micro": ("antivirus", "Trend Micro"),
    "f-secure": ("antivirus", "F-Secure"),
    "avira": ("antivirus", "Avira Free Antivirus"),
    "sophos": ("antivirus", "Sophos Home"),
    "webroot": ("antivirus", "Webroot"),
    "totalav": ("antivirus", "TotalAV"),
    "intego": ("antivirus", "Intego"),
    "comodo": ("antivirus", "Comodo"),
    "panda-security": ("antivirus", "Panda Security"),
    "surfshark-antivirus": ("antivirus", "Surfshark Antivirus"),
    # SaaS platforms — resolve to saas registry
    "hubspot": ("saas", "HubSpot"),
    "salesforce": ("saas", "Salesforce"),
    "asana": ("saas", "Asana"),
    "monday": ("saas", "Monday.com"),
    "clickup": ("saas", "ClickUp"),
    "notion": ("saas", "Notion"),
    "trello": ("saas", "Trello"),
    "jira": ("saas", "Jira"),
    "linear": ("saas", "Linear"),
    "slack": ("saas", "Slack"),
    "zoom": ("saas", "Zoom"),
    "microsoft-teams": ("saas", "Microsoft Teams"),
    "mailchimp": ("saas", "Mailchimp"),
    "zendesk": ("saas", "Zendesk"),
    "intercom": ("saas", "Intercom"),
    "freshdesk": ("saas", "Freshdesk"),
    "figma": ("saas", "Figma"),
    "canva": ("saas", "Canva"),
    "miro": ("saas", "Miro"),
    "xero": ("saas", "Xero"),
    "freshbooks": ("saas", "FreshBooks"),
    "github": ("saas", "GitHub"),
    "gitlab": ("saas", "GitLab"),
    "datadog": ("saas", "Datadog"),
    "gusto": ("saas", "Gusto"),
    "bamboohr": ("saas", "BambooHR"),
    "rippling": ("saas", "Rippling"),
    "deel": ("saas", "Deel"),
    "stripe": ("saas", "Stripe"),
    "shopify": ("saas", "Shopify"),
    "twilio": ("saas", "Twilio"),
    # Website Builders
    "shopify": ("website_builder", "Shopify"),
    "wix": ("website_builder", "Wix"),
    "squarespace": ("website_builder", "Squarespace"),
    "wordpress-com": ("website_builder", "WordPress.com"),
    "webflow": ("website_builder", "Webflow"),
    "ghost": ("website_builder", "Ghost"),
    "ghost-cms": ("website_builder", "Ghost"),
    "weebly": ("website_builder", "Weebly"),
    "carrd": ("website_builder", "Carrd"),
    "framer": ("website_builder", "Framer"),
    "bubble": ("website_builder", "Bubble"),
    "duda": ("website_builder", "Duda"),
    "jimdo": ("website_builder", "Jimdo"),
    "site123": ("website_builder", "SITE123"),
    "strikingly": ("website_builder", "Strikingly"),
    "godaddy-builder": ("website_builder", "GoDaddy Website Builder"),
    "elementor": ("website_builder", "Elementor"),
    "bigcommerce": ("website_builder", "BigCommerce"),
    # Crypto Exchanges
    "binance": ("crypto", "Binance"),
    "coinbase": ("crypto", "Coinbase"),
    "kraken": ("crypto", "Kraken"),
    "okx": ("crypto", "OKX"),
    "bybit": ("crypto", "Bybit"),
    "kucoin": ("crypto", "KuCoin"),
    "gemini": ("crypto", "Gemini"),
    "bitstamp": ("crypto", "Bitstamp"),
    "crypto-com": ("crypto", "Crypto.com"),
    "gate-io": ("crypto", "Gate.io"),
    "ftx": ("crypto", "FTX"),
    "uniswap": ("crypto", "Uniswap"),
    "robinhood-crypto": ("crypto", "Robinhood Crypto"),
}


_entity_cache = {}  # slug → (result, timestamp)
_ENTITY_CACHE_TTL = 3600  # 1 hour


def _resolve_entity(slug):
    """Resolve entity across ALL tables with smart priority.

    Strategy: consumer override > exact name > website > dev package > agents.
    """
    import time as _t_mod
    _cache_key = slug.lower().strip()

    # Reject absurdly long slugs — bot spam (apakah-ist-apakah... patterns)
    if len(_cache_key) > 200:
        _entity_cache[_cache_key] = (None, _t_mod.time())
        return None

    if _cache_key in _entity_cache:
        _cached, _ts = _entity_cache[_cache_key]
        if _t_mod.time() - _ts < _ENTITY_CACHE_TTL:
            return _cached

    session = get_session()
    try:
        session.execute(text("SET LOCAL statement_timeout = '3s'"))
        session.execute(text("SET LOCAL work_mem = '2MB'"))
        sl = slug.lower().strip()
        norm = sl.replace("-", "").replace("_", "").replace(" ", "")

        def _to_result(r, src_table="software_registry"):
            _ts = r.get("trust_score")
            _grade = r.get("trust_grade")
            return {
                "name": r["name"],
                "trust_score": _ts,
                "trust_grade": _grade,
                "category": r.get("registry") or "software",
                "source": r.get("registry") or src_table,
                "source_url": r.get("repository_url") or r.get("homepage_url") or "",
                "stars": r.get("stars") or 0,
                "author": r.get("author") or "Unknown",
                "description": r.get("description") or "",
                "is_verified": (_ts or 0) >= 70,
                "_source_table": src_table,
                "downloads": r.get("downloads") or 0,
                "weekly_downloads": r.get("weekly_downloads") or 0,
                "license": r.get("license") or "",
                "cve_count": r.get("cve_count"),
                "security_score": r.get("security_score"),
                "maintenance_score": r.get("maintenance_score"),
                "popularity_score": r.get("popularity_score"),
                "community_score": r.get("community_score"),
                "quality_score": r.get("quality_score"),
                "is_king": r.get("is_king", False),
                "privacy_score": r.get("privacy_score"),
                "transparency_score": r.get("transparency_score"),
                "reliability_score": r.get("reliability_score"),
                "jurisdiction": r.get("jurisdiction"),
                "has_independent_audit": r.get("has_independent_audit"),
                "tracker_count": r.get("tracker_count"),
                "king_version": r.get("king_version", 0),
                "dimensions": r.get("dimensions"),
                "regulatory": r.get("regulatory"),
            }

        # Two-phase helper: fetch full row by PK after lightweight ID lookup
        _SR_COLS = "name, slug, registry, trust_score, trust_grade, downloads, stars, description, author, license, enriched_at, weekly_downloads, cve_count, security_score, maintenance_score, popularity_score, community_score, quality_score, is_king, privacy_score, transparency_score, reliability_score, jurisdiction, has_independent_audit, tracker_count, king_version, dimensions, regulatory"

        def _sr_fetch_by_id(entity_id):
            """Phase 2: Fetch full row by PK (1 row, no scan)."""
            r = session.execute(text(f"SELECT {_SR_COLS} FROM software_registry WHERE id = :id"), {"id": entity_id}).fetchone()
            if r:
                _r = _to_result(dict(r._mapping)); _entity_cache[_cache_key] = (_r, _t_mod.time()); return _r
            return None

        # 0. CONSUMER OVERRIDE for well-known products
        override = _CONSUMER_OVERRIDES.get(sl) or _CONSUMER_OVERRIDES.get(norm)
        if override:
            reg, name_pat = override
            if "%" in name_pat:
                oid = session.execute(text("SELECT id FROM software_registry WHERE registry = :reg AND name LIKE :pat ORDER BY downloads DESC NULLS LAST LIMIT 1"), {"reg": reg, "pat": name_pat}).fetchone()
            else:
                oid = session.execute(text("SELECT id FROM software_registry WHERE registry = :reg AND name = :pat ORDER BY downloads DESC NULLS LAST LIMIT 1"), {"reg": reg, "pat": name_pat}).fetchone()
            if oid:
                return _sr_fetch_by_id(oid[0])
        _SR_ORDER = """ORDER BY is_king DESC NULLS LAST,
                    CASE registry
                        WHEN 'vpn' THEN 1 WHEN 'country' THEN 2 WHEN 'city' THEN 2 WHEN 'charity' THEN 3
                        WHEN 'ingredient' THEN 3 WHEN 'supplement' THEN 3 WHEN 'cosmetic_ingredient' THEN 3
                        WHEN 'saas' THEN 4 WHEN 'ai_tool' THEN 5
                        WHEN 'website' THEN 6 WHEN 'chrome' THEN 7 WHEN 'firefox' THEN 8
                        WHEN 'vscode' THEN 9 WHEN 'wordpress' THEN 10
                        WHEN 'npm' THEN 11 WHEN 'pypi' THEN 12
                        WHEN 'ios' THEN 13 WHEN 'android' THEN 14
                        WHEN 'steam' THEN 15 WHEN 'crypto' THEN 16
                        ELSE 20
                    END, trust_score DESC NULLS LAST LIMIT 1"""

        # Phase 1: Lightweight ID lookups (index-only scans)
        _slugs = list(dict.fromkeys([sl, norm]))

        # 1. Slug lookup (uses idx_sr_slug — instant)
        for s in _slugs:
            row = session.execute(text(f"SELECT id FROM software_registry WHERE slug = :slug {_SR_ORDER}"), {"slug": s}).fetchone()
            if row:
                return _sr_fetch_by_id(row[0])

        # 2. Exact lower(name) lookup (uses idx_sr_lower_name)
        for s in _slugs:
            row = session.execute(text(f"SELECT id FROM software_registry WHERE lower(name) = :name {_SR_ORDER}"), {"name": s}).fetchone()
            if row:
                return _sr_fetch_by_id(row[0])

        # 3. Normalized name lookup (uses idx_sr_name_normalized)
        for s in _slugs:
            _n = s.replace("-", "").replace(" ", "")
            row = session.execute(text(f"SELECT id FROM software_registry WHERE lower(replace(replace(name, ' ', ''), '-', '')) = :norm {_SR_ORDER}"), {"norm": _n}).fetchone()
            if row:
                return _sr_fetch_by_id(row[0])

        # 4. Fuzzy: starts-with in consumer registries with high downloads (>1M)
        fuzzy_id = session.execute(text("""
            SELECT id FROM software_registry
            WHERE lower(name) LIKE :starts
            AND registry IN ('android', 'ios', 'vpn')
            AND COALESCE(downloads, 0) > 1000000
            ORDER BY downloads DESC NULLS LAST LIMIT 1
        """), {"starts": sl + "%"}).fetchone()
        if fuzzy_id:
            return _sr_fetch_by_id(fuzzy_id[0])

        # 3. WEBSITE check
        domain = sl if "." in sl else sl + ".com"
        wrow = session.execute(text("""
            SELECT domain, trust_score, trust_grade FROM website_cache
            WHERE domain = :d LIMIT 1
        """), {"d": domain}).fetchone()
        if wrow:
            wr = dict(wrow._mapping)
            return {
                "name": wr["domain"], "trust_score": wr["trust_score"] or 50,
                "trust_grade": wr["trust_grade"] or "D", "category": "website",
                "source": "website", "source_url": f"https://{wr['domain']}",
                "stars": 0, "author": "Unknown", "description": f"Website trust analysis for {wr['domain']}",
                "is_verified": (wr["trust_score"] or 0) >= 70,
                "_source_table": "website_cache",
            }

        # 4. Developer packages: exact name in npm/pypi/crates/nuget/go/packagist/gems
        dev_id = session.execute(text("""
            SELECT id FROM software_registry
            WHERE lower(name) = :name
            AND registry IN ('npm', 'pypi', 'crates', 'nuget', 'go', 'packagist', 'gems', 'homebrew')
            LIMIT 1
        """), {"name": sl}).fetchone()
        if dev_id:
            _r = _sr_fetch_by_id(dev_id[0])
            if _r: return _r

        # 5. Broad fuzzy REMOVED — was doing LIKE '%slug%' on 2.5M rows (seq scan → zombie PG)
        # Exact slug/name/normalized lookups above catch 99%+ of real entities.

        # 4. agents table: quality agents only (stars > 50)
        # Use existing _lookup_agent but it already does this
        _entity_cache[_cache_key] = (None, _t_mod.time())
        return None
    except Exception as e:
        logger.warning(f"Entity resolution error for {slug}: {e}")
        return None
    finally:
        session.close()


def _lookup_agent(name):
    """Look up agent by name with fuzzy matching.
    Uses _SLUG_OVERRIDES for top tools, then falls back to DB matching
    with rank-first ordering to prefer exact matches over fuzzy ones.
    """
    # Reject absurdly long names — bot spam
    if len(name) > 200:
        return None
    # Check manual overrides first (slug or clean name, both with and without hyphens)
    override_key = name.lower().strip()
    if override_key in _SLUG_OVERRIDES:
        name = _SLUG_OVERRIDES[override_key]
    else:
        # Also try with hyphens restored (for names like "auto gpt" → "auto-gpt")
        hyphenated = override_key.replace(" ", "-")
        if hyphenated in _SLUG_OVERRIDES:
            name = _SLUG_OVERRIDES[hyphenated]

    session = get_session()
    try:
        session.execute(text("SET LOCAL statement_timeout = '3s'"))
        session.execute(text("SET LOCAL work_mem = '2MB'"))
        clean = name.replace("-", " ").replace("_", " ")

        # Short-circuit: try exact match FIRST (uses index, <1ms)
        # Uses entity_lookup (2.9GB) instead of agents (17GB) to avoid zombie PG backends
        row = session.execute(text(f"""
            SELECT {_TRUST_COLS} FROM entity_lookup
            WHERE (name_lower = LOWER(:name) OR name_lower = LOWER(:clean))
              AND is_active = true
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC NULLS LAST
            LIMIT 1
        """), {"name": name, "clean": clean}).fetchone()
        if row:
            return dict(row._mapping)

        # Suffix match: org/name pattern — two-phase (ID via index, then full fetch)
        _suffix_id = session.execute(text("""
            SELECT id FROM entity_lookup
            WHERE name_lower LIKE lower(:suffix) AND is_active = true
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC NULLS LAST
            LIMIT 1
        """), {"suffix": f"%/{name}"}).fetchone()
        if _suffix_id:
            row = session.execute(text(f"SELECT {_TRUST_COLS} FROM entity_lookup WHERE id = :id"),
                                  {"id": _suffix_id[0]}).fetchone()
            if row:
                return dict(row._mapping)

        # Broad fuzzy LIKE '%name%' REMOVED — was scanning 5M rows, creating zombie PG backends.
        # Exact + suffix lookups above catch real entities; fuzzy matched noise.
        return None
    finally:
        session.close()


def _get_deep_analysis(name, agent_data):
    """Get deep analysis HTML for top agents."""
    try:
        from agentindex.deep_analysis import get_deep_sections
        return get_deep_sections(name, agent_data)
    except Exception as e:
        logger.warning(f"Deep analysis failed for {name}: {e}")
        return ""


_REGISTRY_GUIDE = {
    "npm": {"cat": "Node.js package", "verify": "Run <code>npm audit</code> to check for vulnerabilities. Review the package's GitHub repository for recent commits.", "concerns": "dependency vulnerabilities, malicious packages, typosquatting"},
    "pypi": {"cat": "Python package", "verify": "Run <code>pip audit</code> or <code>safety check</code>. Review on PyPI for download stats.", "concerns": "dependency vulnerabilities, malicious uploads, maintenance status"},
    "crates": {"cat": "Rust crate", "verify": "Run <code>cargo audit</code>. Review on crates.io for activity.", "concerns": "dependency vulnerabilities, unsafe code, maintenance status"},
    "nuget": {"cat": "NuGet package", "verify": "Run <code>dotnet list package --vulnerable</code>. Check publisher on nuget.org.", "concerns": "dependency vulnerabilities, publisher verification"},
    "go": {"cat": "Go module", "verify": "Run <code>govulncheck</code>. Review commit activity.", "concerns": "dependency vulnerabilities, maintenance status"},
    "gems": {"cat": "Ruby gem", "verify": "Run <code>bundle audit</code>. Review on rubygems.org.", "concerns": "dependency vulnerabilities, maintenance status"},
    "packagist": {"cat": "PHP package", "verify": "Run <code>composer audit</code>. Check packagist.org.", "concerns": "dependency vulnerabilities, PHP compatibility"},
    "homebrew": {"cat": "Homebrew formula", "verify": "Homebrew formulas are community-reviewed. Check formulae.brew.sh.", "concerns": "source build integrity, dependency chain"},
    "wordpress": {"cat": "WordPress plugin", "verify": "Check WordPress.org for support response time, tested WP version. Cross-reference with WPScan.", "concerns": "known vulnerabilities, PHP compatibility, plugin conflicts"},
    "vscode": {"cat": "VS Code extension", "verify": "Check marketplace ratings and publisher verification. Review telemetry settings.", "concerns": "code execution scope, telemetry, supply chain risk"},
    "chrome": {"cat": "Chrome extension", "verify": "Review permissions carefully. 'Read all data on all websites' is high risk.", "concerns": "excessive permissions, data harvesting, permission creep"},
    "firefox": {"cat": "Firefox add-on", "verify": "Review permissions on addons.mozilla.org. Check if source code is available.", "concerns": "excessive permissions, data harvesting"},
    "extension": {"cat": "browser extension", "verify": "Review permissions carefully before installing.", "concerns": "excessive permissions, data harvesting"},
    "ios": {"cat": "iOS app", "verify": "Check App Store privacy labels. Review permissions. Look up developer.", "concerns": "excessive permissions, data collection, in-app purchases, age appropriateness"},
    "android": {"cat": "Android app", "verify": "Review Data Safety section in Google Play. Check permissions and ad trackers.", "concerns": "excessive permissions, data collection, ad trackers, background data usage"},
    "steam": {"cat": "game", "verify": "Check Steam reviews. Verify age rating. Look at microtransaction details.", "concerns": "microtransaction aggressiveness, loot boxes, anti-cheat invasiveness, age appropriateness"},
    "vpn": {"cat": "VPN service", "verify": "Check jurisdiction (Five Eyes?). Verify independent audit exists. Review logging policy.", "concerns": "logging practices, jurisdiction, audit history, ownership transparency"},
    "website": {"cat": "website", "verify": "Check domain age, SSL certificate, and security headers.", "concerns": "domain age, SSL validity, scam indicators"},
}


def _safety_guide_registry(dn, name, registry, score, grade, stars, description, is_verified, alternatives, slug,
                            security_score, activity_score, doc_score, popularity_score, compliance_score):
    """Generate a registry-appropriate safety guide (NOT AI-focused)."""
    info = _REGISTRY_GUIDE.get(registry, {"cat": "software tool", "verify": "Review the project for recent activity and known issues.", "concerns": "maintenance status, security"})
    cat = info["cat"]
    # Add registry-specific entries for commercial verticals missing from _REGISTRY_GUIDE
    if registry == "password_manager":
        info = {"cat": "password manager", "verify": "Check breach history. Verify encryption standard. Review independent audit status.", "concerns": "breach history, encryption standard, audit status, jurisdiction"}
        cat = info["cat"]
    elif registry == "antivirus":
        info = {"cat": "antivirus software", "verify": "Check AV-TEST lab results. Review incident history and privacy policy.", "concerns": "detection rate, system impact, privacy practices, jurisdiction"}
        cat = info["cat"]
    elif registry == "hosting":
        info = {"cat": "web hosting provider", "verify": "Check uptime history. Review security compliance and data center locations.", "concerns": "uptime reliability, security compliance, breach history, data location"}
        cat = info["cat"]
    elif registry == "website_builder":
        info = {"cat": "website builder", "verify": "Check security certifications. Review ecommerce payment compliance.", "concerns": "security certifications, payment compliance, data location"}
        cat = info["cat"]
    elif registry == "saas":
        info = {"cat": "SaaS platform", "verify": "Check SOC 2 compliance. Review data handling and incident history.", "concerns": "data security, compliance certifications, incident history"}
        cat = info["cat"]
    elif registry == "crypto":
        info = {"cat": "crypto exchange", "verify": "Check regulatory status. Verify Proof of Reserves. Review incident history.", "concerns": "regulatory compliance, security incidents, Proof of Reserves, jurisdiction"}
        cat = info["cat"]
    verified_label = "meets Nerq trust threshold" if is_verified else "has not yet reached Nerq trust threshold (70+)"

    alts_html = ""
    if alternatives:
        alts_items = ""
        for a in alternatives[:3]:
            aname = a.get("name", "")
            aslug = _make_slug(aname)
            ascore = a.get("trust_score", 0) or 0
            alts_items += f'<li><a href="/safe/{_esc(aslug)}">{_esc(aname)}</a> — {ascore:.0f}/100</li>'
        alts_html = f"<h3>Alternatives</h3><ul>{alts_items}</ul>"

    return f"""
<h2>Safety Guide: {dn}</h2>

<h3>What is {dn}?</h3>
<p>{dn} is a {cat}{f' — {_esc(description[:200])}' if description else ''}.</p>

<h3>How to Verify Safety</h3>
<p>{info["verify"]}</p>
<p>You can also check the trust score via API: <code>GET /v1/preflight?target={_esc(name)}</code></p>

<h3>Key Safety Concerns for {cat}</h3>
<p>When evaluating any {cat}, watch for: {info["concerns"]}.</p>

<h3>Trust Assessment</h3>
<p>{dn} has a Nerq Trust Score of <strong>{score:.0f}/100 ({_esc(grade)})</strong> and {verified_label}.
{'This score is based on automated analysis of security, maintenance, community, and quality signals.' if score > 0 else 'Trust score analysis is in progress.'}</p>

{alts_html}

<h3>Key Takeaways</h3>
<ul>
<li>{dn} has a Trust Score of <strong>{score:.0f}/100 ({_esc(grade)})</strong>.</li>
<li>{'Recommended for use — passes trust threshold.' if is_verified else 'Review carefully before use — below trust threshold.'}</li>
<li>Always verify independently using the <a href="/v1/preflight?target={_esc(name)}">Nerq API</a>.</li>
</ul>
"""


def _safety_guide(display_name, name, agent_data, alternatives, slug):
    """Generate comprehensive safety guide section (~800-1200 words).
    Uses only PostgreSQL data — works for ALL pages, not just top agents.
    """
    score = float(agent_data.get("trust_score") or agent_data.get("trust_score_v2") or 0)
    grade = agent_data.get("trust_grade") or "N/A"
    category = agent_data.get("category") or "uncategorized"
    source = agent_data.get("source") or "unknown"
    stars = agent_data.get("stars") or 0
    description = agent_data.get("description") or ""
    is_verified = agent_data.get("is_verified") or (score >= 70)
    security_score = agent_data.get("security_score")
    compliance_score = agent_data.get("compliance_score")
    activity_score = agent_data.get("activity_score")
    doc_score = agent_data.get("documentation_score")
    popularity_score = agent_data.get("popularity_score")
    eu_risk_class = agent_data.get("eu_risk_class") or ""

    dn = _esc(display_name)
    n = _esc(name)

    # For non-AI entities from software_registry, generate a simple registry-appropriate guide
    _src = agent_data.get("_source_table", "")
    _reg = agent_data.get("source") or agent_data.get("registry") or category
    _NON_AI_REGISTRIES = {"npm","pypi","crates","nuget","go","gems","packagist","homebrew",
                          "wordpress","vscode","chrome","firefox","extension",
                          "ios","android","steam","vpn","website"}
    if _reg in _NON_AI_REGISTRIES or _src == "software_registry":
        return _safety_guide_registry(dn, n, _reg, score, grade, stars, description, is_verified, alternatives, slug,
                                       security_score, activity_score, doc_score, popularity_score, compliance_score)

    sections = []

    # ── Section 1: What is [Tool] and What Does It Do? ──
    # Registry-based type labels (most entities come from software_registry)
    _registry_labels = {
        "npm": "Node.js package", "pypi": "Python package", "crates": "Rust crate",
        "go": "Go module", "gems": "Ruby gem", "packagist": "PHP package",
        "nuget": ".NET package", "homebrew": "Homebrew formula",
        "wordpress": "WordPress plugin", "vscode": "VS Code extension",
        "chrome": "Chrome extension", "firefox": "Firefox extension",
        "extension": "browser extension",
        "ios": "iOS app", "android": "Android app", "steam": "game",
        "vpn": "VPN service",
    }
    # AI-specific category descriptions (only for actual AI tools from agents table)
    _ai_cat_descriptions = {
        "code_assistant": "AI-powered code assistant",
        "chatbot": "AI chatbot",
        "agent_framework": "framework for building autonomous AI agents",
        "mcp_server": "Model Context Protocol (MCP) server",
        "automation": "automation platform",
        "llm_tool": "tool for working with large language models",
        "image_generation": "AI image generation tool",
        "data_analysis": "data analysis tool",
        "devops": "DevOps tool",
        "security": "security tool",
    }
    # Determine label: registry-based first, then AI categories, then generic
    source_registry = agent_data.get("_source_table", "")
    entity_registry = agent_data.get("category") or category or ""
    cat_desc = _registry_labels.get(entity_registry.lower(),
               _ai_cat_descriptions.get(category, 
               f"software tool in the {_esc(category)} category" if category else "software tool"))

    desc_clean = _esc(description[:300]) if description else ""
    # Build data-rich first paragraph
    _data_points = []
    _dl = agent_data.get("downloads") or agent_data.get("weekly_downloads") or 0
    _stars = agent_data.get("stars") or 0
    _license = agent_data.get("license") or ""
    _cve = agent_data.get("cve_count")
    if _dl > 0:
        if _dl >= 1_000_000: _data_points.append(f"{_dl:,} downloads")
        elif _dl >= 1_000: _data_points.append(f"{_dl:,} downloads")
        else: _data_points.append(f"{_dl:,} downloads")
    if _stars > 0:
        _data_points.append(f"{_stars:,} GitHub stars")
    if _license and _license not in ("See repository", "UNKNOWN", ""):
        _data_points.append(f"{_esc(_license)} licensed")
    if _cve is not None:
        _data_points.append(f"{_cve} known CVE{'s' if _cve != 1 else ''}")
    _data_str = ", ".join(_data_points)
    
    # Compose opening
    if desc_clean and _data_str:
        _opening = f"{dn} is a {cat_desc}: {desc_clean}. It has {_data_str}."
    elif desc_clean:
        _opening = f"{dn} is a {cat_desc}: {desc_clean}."
    elif _data_str:
        _opening = f"{dn} is a {cat_desc} with {_data_str}."
    else:
        _opening = f"{dn} is a {cat_desc} available on {_esc(source)}."
    
    _score_line = f"Nerq Trust Score: {score:.0f}/100 ({_esc(grade)})."
    
    sections.append(f"""
<h2>What Is {dn}?</h2>
<p>{_opening} {_score_line}</p>
<p>Nerq independently analyzes every software tool, app, and extension across multiple trust signals including security vulnerabilities, maintenance activity, license compliance, and community adoption.</p>
""")

    # ── Section 2: How We Assess Safety ──
    signal_details = []
    if security_score is not None:
        sec_rating = "strong" if security_score >= 80 else "adequate" if security_score >= 60 else "concerning" if security_score >= 40 else "poor"
        signal_details.append(f"<strong>Security ({security_score:.0f}/100)</strong>: {dn}'s security posture is {sec_rating}. This score factors in known CVEs, dependency vulnerabilities, security policy presence, and code signing practices.")
    if activity_score is not None:
        act_rating = "actively maintained" if activity_score >= 80 else "regularly updated" if activity_score >= 60 else "sporadically maintained" if activity_score >= 40 else "potentially abandoned"
        signal_details.append(f"<strong>Maintenance ({activity_score:.0f}/100)</strong>: {dn} is {act_rating}. We track commit frequency, release cadence, issue response times, and PR merge rates.")
    if doc_score is not None:
        doc_rating = "excellent" if doc_score >= 80 else "good" if doc_score >= 60 else "limited" if doc_score >= 40 else "insufficient"
        signal_details.append(f"<strong>Documentation ({doc_score:.0f}/100)</strong>: Documentation quality is {doc_rating}. This includes README completeness, API documentation, usage examples, and contribution guidelines.")
    if compliance_score is not None:
        comp_rating = "broadly compliant" if compliance_score >= 70 else "partially compliant" if compliance_score >= 50 else "compliance gaps exist"
        signal_details.append(f"<strong>Compliance ({compliance_score:.0f}/100)</strong>: {dn} is {comp_rating}. Assessed against regulations in 52 jurisdictions including the EU AI Act, CCPA, and GDPR.")
    if popularity_score is not None:
        pop_rating = "very strong" if popularity_score >= 80 else "strong" if popularity_score >= 60 else "moderate" if popularity_score >= 40 else "limited"
        signal_details.append(f"<strong>Community ({popularity_score:.0f}/100)</strong>: Community adoption is {pop_rating}. Based on GitHub stars, forks, download counts, and ecosystem integrations.")

    if signal_details:
        sections.append(f"""
<h2>How Nerq Assesses {dn}'s Safety</h2>
<p>Nerq's Trust Score is calculated from 13+ independent signals aggregated into five dimensions. Here is how {dn} performs in each:</p>
<ul style="line-height:2;font-size:15px">
{"".join(f"<li>{s}</li>" for s in signal_details)}
</ul>
<p>The overall Trust Score of <strong>{score:.1f}/100 ({_esc(grade)})</strong> reflects the weighted combination of these signals. {'This exceeds the Nerq Verified threshold of 70, indicating the tool meets our standards for production use.' if is_verified else 'This is below the Nerq Verified threshold of 70. We recommend additional due diligence before production deployment.'}</p>
""")
    else:
        # Fallback when dimension scores not available
        overall_rating = "excellent" if score >= 80 else "good" if score >= 70 else "moderate" if score >= 50 else "low"
        sections.append(f"""
<h2>How Nerq Assesses {dn}'s Safety</h2>
<p>Nerq evaluates every software tool across 13+ independent trust signals drawn from public sources including GitHub, NVD, OSV.dev, OpenSSF Scorecard, and package registries. These signals are grouped into five core dimensions: <strong>Security</strong> (known CVEs, dependency vulnerabilities, security policies), <strong>Maintenance</strong> (commit frequency, release cadence, issue response times), <strong>Documentation</strong> (README quality, API docs, examples), <strong>Compliance</strong> (license, regulatory alignment across 52 jurisdictions), and <strong>Community</strong> (stars, forks, downloads, ecosystem integrations).</p>
<p>{dn} receives an overall Trust Score of <strong>{score:.1f}/100 ({_esc(grade)})</strong>, which Nerq considers {overall_rating}. {'This exceeds the Nerq Verified threshold of 70, indicating the tool meets our standards for production use.' if is_verified else 'This is below the Nerq Verified threshold of 70. We recommend additional due diligence before production deployment.'} {'With ' + f"{stars:,} GitHub stars, {dn} benefits from a large community that can identify and report issues quickly." if stars > 5000 else ''}</p>
<p>Nerq updates trust scores continuously as new data becomes available. To get the latest assessment, query the API: <code>GET nerq.ai/v1/preflight?target={_esc(name)}</code></p>
<p>Each dimension is weighted according to its importance for the tool's category. For example, Security and Maintenance carry higher weight for tools that handle sensitive data or execute code, while Community and Documentation are weighted more heavily for developer-facing libraries and frameworks. This ensures that {dn}'s score reflects the risks most relevant to its actual usage patterns. The final score is a weighted average across all five dimensions, normalized to a 0-100 scale with letter grades from A (highest) to F (lowest).</p>
""")

    # ── Section 3: Who Should Use [Tool]? ──
    use_cases = {
        "code_assistant": ["Individual developers looking for AI pair programming", "Engineering teams wanting to accelerate code reviews", "Organizations evaluating AI coding tools for enterprise deployment"],
        "chatbot": ["Individuals seeking conversational AI assistance", "Businesses deploying customer-facing AI", "Developers integrating chat capabilities into applications"],
        "agent_framework": ["AI engineers building autonomous agent systems", "Research teams experimenting with multi-agent architectures", "Companies creating AI-powered automation workflows"],
        "mcp_server": ["Developers extending AI assistant capabilities", "Teams building custom tool integrations for LLMs", "Organizations creating data bridges between AI and internal systems"],
        "automation": ["Teams automating repetitive workflows", "Organizations connecting multiple tools and services", "Developers building event-driven AI pipelines"],
        "image_generation": ["Creative professionals generating visual assets from text descriptions", "Marketing teams producing campaign imagery at scale", "Developers integrating AI image generation into applications", "Researchers exploring generative AI capabilities"],
        "design": ["Designers using AI to accelerate visual content creation", "Creative teams generating concept art and prototypes", "Developers building applications with AI-powered image generation", "Content creators producing visual media for digital platforms"],
    }
    cases = use_cases.get(category, [
        f"Developers and teams working with {_esc(category)} tools",
        "Organizations evaluating AI tools for their stack",
        "Researchers exploring AI capabilities in this domain",
    ])

    risk_advice = ""
    if score >= 80:
        risk_advice = f"{dn} is well-suited for production environments. Its high trust score indicates robust security, active maintenance, and strong community support. Standard security practices (dependency pinning, access controls, monitoring) are still recommended."
    elif score >= 70:
        risk_advice = f"{dn} meets the minimum threshold for production use, but we recommend monitoring for security advisories and keeping dependencies up to date. Consider implementing additional guardrails for sensitive workloads."
    elif score >= 50:
        risk_advice = f"{dn} is suitable for development and testing environments. Before production deployment, conduct a thorough review of its security posture, review the specific trust signals above, and consider whether a higher-scored alternative meets your requirements."
    else:
        risk_advice = f"We recommend caution with {dn}. The low trust score suggests potential risks in security, maintenance, or community support. Consider using a more established alternative for any production or sensitive workload."

    sections.append(f"""
<h2>Who Should Use {dn}?</h2>
<p>{dn} is designed for:</p>
<ul style="line-height:2;font-size:15px">
{"".join(f"<li>{_esc(c)}</li>" for c in cases)}
</ul>
<p><strong>Risk guidance:</strong> {risk_advice}</p>
""")

    # ── Section 4: How to Verify Safety Yourself ──
    sections.append(f"""
<h2>How to Verify {dn}'s Safety Yourself</h2>
<p>While Nerq provides automated trust analysis, we recommend these additional steps before adopting any software tool:</p>
<ol style="line-height:2;font-size:15px">
<li><strong>Check the source code</strong> — Review the repository{'&apos;s' if source == 'github' else ''} security policy, open issues, and recent commits for signs of active maintenance.</li>
<li><strong>Scan dependencies</strong> — Use tools like <code>npm audit</code>, <code>pip-audit</code>, or <code>snyk</code> to check for known vulnerabilities in {dn}&apos;s dependency tree.</li>
<li><strong>Review permissions</strong> — Understand what access {dn} requires. {'MCP servers should declare their capabilities explicitly.' if category == 'mcp_server' else 'Software tools should follow the principle of least privilege.'}</li>
<li><strong>Test in isolation</strong> — Run {dn} in a sandboxed environment before granting access to production data or systems.</li>
<li><strong>Monitor continuously</strong> — Use Nerq&apos;s API to set up automated trust checks: <code>GET nerq.ai/v1/preflight?target={_esc(name)}</code></li>
<li><strong>Review the license</strong> — Confirm that {dn}&apos;s license is compatible with your intended use case. Pay attention to restrictions on commercial use, redistribution, and derivative works. Some AI tools use dual licensing or have separate terms for enterprise customers that differ from the open-source license.</li>
<li><strong>Check community signals</strong> — Look at the project&apos;s issue tracker, discussion forums, and social media presence. A healthy community actively reports bugs, contributes fixes, and discusses security concerns openly. Low community engagement may indicate limited peer review of the codebase.</li>
</ol>
""")

    # ── Section 5: Common Safety Concerns ──
    concern_items = []
    if category in ("code_assistant", "chatbot", "llm_tool"):
        concern_items = [
            (f"Data privacy", f"When using {dn}, be aware of what data you share. Code assistants and chatbots may send your prompts and code to external servers for processing. Check {dn}'s privacy policy and data retention practices before sharing sensitive information."),
            (f"Code execution risks", f"AI-generated code from {dn} should always be reviewed before execution. Automated code suggestions may contain security vulnerabilities, use deprecated APIs, or introduce unintended behavior. Never run AI-generated code in production without review."),
            (f"Supply chain security", f"If {dn} installs packages or dependencies, verify them independently. Software tools may suggest or install packages that are typosquatted, abandoned, or contain known vulnerabilities."),
            (f"Model hallucination", f"Tools like {dn} can produce confident-sounding but factually incorrect outputs. This is especially dangerous in code generation where subtle logic errors or incorrect API usage may not be caught by automated tests. Always validate AI outputs against official documentation and known-good implementations before relying on them."),
            (f"Authentication and credential leakage", f"When {dn} integrates with external services, there is a risk of accidentally exposing API keys, tokens, or credentials in logs, prompts, or generated code. Audit your configuration to ensure secrets are stored securely and never passed through AI processing pipelines in plaintext."),
        ]
    elif category == "mcp_server":
        concern_items = [
            (f"Permission scope", f"MCP servers like {dn} request specific capabilities from your AI assistant. Review the server's declared tools and resources before granting access. Only connect MCP servers from trusted sources."),
            (f"Data exposure", f"MCP servers can access and transmit data between your AI assistant and external services. Understand what data {dn} reads and where it sends information."),
            (f"Server authenticity", f"Verify that {dn} is the official MCP server and not a lookalike. Check the source repository, publisher, and community reputation before installation."),
            (f"Transport layer security", f"MCP servers communicate over stdio or HTTP transports. When using {dn} over HTTP/SSE, ensure the connection is encrypted with TLS. Unencrypted MCP connections can expose tool calls, responses, and potentially sensitive data to network observers."),
            (f"Tool call injection", f"Malicious prompts can trick AI assistants into making unintended tool calls through {dn}. This can lead to unauthorized data access, file modifications, or external API requests. Implement allowlists for permitted tool operations and log all tool invocations for audit."),
        ]
    elif category == "agent_framework":
        concern_items = [
            (f"Autonomous actions", f"Agent frameworks like {dn} can take actions autonomously — executing code, calling APIs, modifying files. Always implement guardrails and human-in-the-loop controls for production deployments."),
            (f"Prompt injection", f"AI agents built with {dn} may be vulnerable to prompt injection attacks where malicious input causes the agent to take unintended actions. Test for adversarial inputs before deploying."),
            (f"Resource consumption", f"Autonomous agents can incur unexpected API costs or resource usage. Set budget limits and monitoring alerts when deploying {dn}-based agents."),
            (f"Multi-agent coordination failures", f"When using {dn} to orchestrate multiple agents, failures in inter-agent communication can lead to cascading errors, duplicated actions, or deadlocks. Implement circuit breakers and timeout mechanisms to prevent runaway agent loops that can consume resources indefinitely."),
            (f"Memory and context poisoning", f"Agents built with {dn} that persist memory across sessions can have their context poisoned by adversarial inputs. Once corrupted, the agent may make consistently poor decisions in future interactions. Implement memory validation and periodic context resets for long-running agents."),
        ]
    else:
        concern_items = [
            (f"Data handling", f"Understand how {dn} processes, stores, and transmits your data. Review the tool's privacy policy and data retention practices, especially for sensitive or proprietary information."),
            (f"Dependency security", f"Check {dn}'s dependency tree for known vulnerabilities. Tools with outdated or unmaintained dependencies pose a higher security risk."),
            (f"Update frequency", f"Regularly check for updates to {dn}. Security patches and bug fixes are only effective if you're running the latest version."),
            (f"Third-party integrations", f"If {dn} connects to external APIs or services, each integration point is a potential attack surface. Audit all third-party connections, verify that data shared with external services is minimized, and ensure that integration credentials are rotated regularly."),
            (f"License and IP compliance", f"Verify that {dn}'s license is compatible with your intended use case. Some AI tools have restrictive licenses that limit commercial use, redistribution, or derivative works. Using {dn} in violation of its license can expose your organization to legal liability."),
        ]

    if concern_items:
        concerns_html = "".join(
            f'<div style="padding:12px 16px;border-left:3px solid #e5e7eb;margin-bottom:12px">'
            f'<div style="font-weight:600;font-size:14px;margin-bottom:4px">{_esc(title)}</div>'
            f'<p style="font-size:14px;color:#374151;line-height:1.6;margin:0">{desc}</p>'
            f'</div>'
            for title, desc in concern_items
        )
        sections.append(f"""
<h2>Common Safety Concerns with {dn}</h2>
<p style="font-size:15px;color:#374151;margin-bottom:12px">When evaluating whether {dn} is safe, consider these category-specific risks:</p>
{concerns_html}
""")

    # ── Section 6: EU AI Act context ──
    if eu_risk_class:
        eu_detail = {
            "minimal": f"{dn} is classified as <strong>Minimal Risk</strong> under the EU AI Act. This is the lowest risk category, meaning it faces minimal regulatory requirements. However, transparency obligations still apply.",
            "limited": f"{dn} is classified as <strong>Limited Risk</strong> under the EU AI Act. This requires transparency measures — users must be informed when they are interacting with an AI system.",
            "high": f"{dn} is classified as <strong>High Risk</strong> under the EU AI Act. This imposes significant requirements including risk management systems, data governance, technical documentation, and human oversight.",
        }.get(eu_risk_class.lower(), f"{dn} has been assessed under the EU AI Act framework.")
        sections.append(f"""
<h2>{dn} and the EU AI Act</h2>
<p>{eu_detail}</p>
<p>Nerq's compliance assessment covers 52 jurisdictions worldwide. For organizations deploying AI tools in regulated environments, understanding these classifications is essential for legal compliance.</p>
""")

    # ── Section 6: Best Practices ──
    bp_items = {
        "code_assistant": [
            ("Review all generated code", f"Never blindly accept code suggestions from {dn}. AI-generated code can contain subtle bugs, security flaws, or logic errors that only a human reviewer would catch."),
            ("Use in a sandboxed environment", f"Run {dn} in isolated development environments to prevent unauthorized access to production systems, credentials, or sensitive data."),
            ("Pin dependencies", f"When {dn} suggests adding packages, pin specific versions and audit them before inclusion. This prevents supply chain attacks through malicious or compromised dependencies."),
            ("Enable audit logging", f"Track what {dn} generates and modifies. Logging helps identify issues retroactively and provides accountability for AI-assisted code changes."),
            ("Set permission boundaries", f"Limit {dn}'s access to only the files, repositories, and systems it needs. Follow the principle of least privilege to minimize potential damage from errors or compromises."),
        ],
        "chatbot": [
            ("Never share secrets", f"Do not input API keys, passwords, personal data, or confidential business information into {dn}. Assume that anything you type may be stored or used for training."),
            ("Verify factual claims", f"AI chatbots can hallucinate — generating plausible-sounding but incorrect information. Always cross-reference important facts, statistics, and recommendations from {dn}."),
            ("Understand data retention", f"Review {dn}'s privacy policy to understand how long your conversations are stored, whether they're used for model training, and your rights to deletion."),
            ("Use official channels only", f"Only access {dn} through its official website or app. Phishing sites and unofficial wrappers may steal your credentials or conversations."),
            ("Set usage policies for teams", f"If deploying {dn} in an organization, establish clear policies about what data can be shared, what tasks it should be used for, and how to handle sensitive outputs."),
        ],
        "agent_framework": [
            ("Implement human-in-the-loop", f"Configure {dn} agents to require human approval for high-impact actions like payments, data deletion, or external API calls."),
            ("Set budget and rate limits", f"Autonomous agents built with {dn} can incur unexpected costs through API calls and resource usage. Set hard spending limits and rate caps."),
            ("Monitor agent behavior", f"Log all actions taken by agents built with {dn}. Use observability tools to detect anomalous behavior patterns that could indicate prompt injection or logic errors."),
            ("Test with adversarial inputs", f"Before deploying {dn}-based agents in production, test with adversarial prompts designed to bypass guardrails and cause unintended actions."),
            ("Scope agent permissions tightly", f"Each agent should have the minimum permissions required. Never give an agent root access, admin credentials, or unrestricted API keys."),
        ],
        "mcp_server": [
            ("Verify server identity", f"Before connecting to {dn}, verify the source code and publisher. Only install MCP servers from trusted repositories."),
            ("Review declared capabilities", f"Check what tools and resources {dn} exposes. Only grant access to capabilities your workflow actually needs."),
            ("Monitor data flow", f"Track what data {dn} reads from your system and what it sends to external services. Be especially careful with file system access."),
            ("Keep server updated", f"Run the latest version of {dn} to ensure you have current security patches. Subscribe to the repository for security advisories."),
            ("Isolate in containers", f"Run {dn} in a containerized environment (Docker) to limit its access to only designated directories and network endpoints."),
        ],
    }
    bp_list = bp_items.get(category, [
        ("Conduct regular audits", f"Periodically review how {dn} is used in your workflow. Check for unexpected behavior, permissions drift, and compliance with your security policies."),
        ("Keep dependencies updated", f"Ensure {dn} and all its dependencies are running the latest stable versions to benefit from security patches."),
        ("Follow least privilege", f"Grant {dn} only the minimum permissions it needs to function. Avoid granting admin or root access."),
        ("Monitor for security advisories", f"Subscribe to {dn}'s security advisories and vulnerability disclosures. Use Nerq's API to get automated trust score updates."),
        ("Document usage policies", f"Create and maintain a clear policy for how {dn} is used within your organization, including data handling guidelines and acceptable use cases."),
    ])

    bp_html = "".join(
        f'<div style="padding:10px 16px;border-left:3px solid #0d9488;margin-bottom:10px">'
        f'<div style="font-weight:600;font-size:14px;margin-bottom:2px">{_esc(title)}</div>'
        f'<p style="font-size:14px;color:#374151;line-height:1.6;margin:0">{desc}</p>'
        f'</div>'
        for title, desc in bp_list
    )
    sections.append(f"""
<h2>Best Practices for Using {dn} Safely</h2>
<p style="font-size:15px;color:#374151;margin-bottom:12px">Whether you're an individual developer or an enterprise team, these practices will help you get the most from {dn} while minimizing risk:</p>
{bp_html}
""")

    # ── Section 7: When to Avoid ──
    if score < 70:
        avoid_scenarios = [
            "Production environments handling sensitive customer data",
            "Regulated industries (healthcare, finance, government) without additional compliance review",
            "Mission-critical systems where downtime has significant business impact",
        ]
    else:
        avoid_scenarios = [
            f"Scenarios where {dn}'s specific capabilities exceed your actual needs — simpler tools may be safer",
            "Air-gapped environments where the tool cannot receive security updates",
            "Projects with strict regulatory requirements that haven't been explicitly validated",
        ]
    avoid_html = "".join(f"<li>{_esc(s)}</li>" for s in avoid_scenarios)
    sections.append(f"""
<h2>When Should You Avoid {dn}?</h2>
<p style="font-size:15px;color:#374151;line-height:1.7">Even {'well-trusted' if score >= 70 else 'promising'} tools aren't right for every situation. Consider avoiding {dn} in these scenarios:</p>
<ul style="line-height:2;font-size:15px">{avoid_html}</ul>
<p style="font-size:15px;color:#374151;line-height:1.7">For each scenario, evaluate whether {dn}'s trust score of {score:.1f}/100 meets your organization's risk tolerance. {'The Nerq Verified status indicates general production readiness, but sector-specific requirements may apply.' if is_verified else 'We recommend running a manual security assessment alongside the automated Nerq score.'}</p>
""")

    # ── Section 8: How [Tool] Compares to Industry Standards ──
    cat_label_map = {
        "code_assistant": "code assistants",
        "chatbot": "chatbots",
        "agent_framework": "agent frameworks",
        "mcp_server": "MCP servers",
        "automation": "automation tools",
        "llm_tool": "LLM tools",
        "image_generation": "image generation tools",
        "data_analysis": "data analysis tools",
        "devops": "DevOps tools",
        "security": "security tools",
    }
    cat_label = cat_label_map.get(category, f"{_esc(category)} tools")
    # Determine position relative to category average (approximate benchmarks)
    cat_avg_map = {
        "code_assistant": 72, "chatbot": 68, "agent_framework": 65,
        "mcp_server": 58, "automation": 64, "llm_tool": 66,
        "image_generation": 60, "data_analysis": 62, "devops": 63, "security": 67,
    }
    cat_avg = cat_avg_map.get(category, 62)
    diff = score - cat_avg
    if diff > 10:
        relative_pos = f"significantly above the category average of {cat_avg}/100"
        relative_detail = f"This places {dn} in the top tier of {cat_label} that Nerq tracks. Tools scoring this far above average typically demonstrate mature security practices, consistent release cadence, and broad community adoption."
    elif diff > 0:
        relative_pos = f"above the category average of {cat_avg}/100"
        relative_detail = f"This positions {dn} favorably among {cat_label}. While it outperforms the average, there is still room for improvement in certain trust dimensions."
    elif diff > -10:
        relative_pos = f"near the category average of {cat_avg}/100"
        relative_detail = f"This places {dn} in line with the typical {cat_label.rstrip('s')} tool. It meets baseline expectations but does not distinguish itself from peers on trust metrics."
    else:
        relative_pos = f"below the category average of {cat_avg}/100"
        relative_detail = f"This suggests that {dn} trails behind many comparable {cat_label}. Organizations with strict security requirements should evaluate whether higher-scoring alternatives better meet their needs."

    sections.append(f"""
<h2>How {dn} Compares to Industry Standards</h2>
<p>Nerq indexes over 6 million software tools, apps, and packages across dozens of categories. Among {cat_label}, the average Trust Score is {cat_avg}/100. {dn}'s score of {score:.1f}/100 is {relative_pos}.</p>
<p>{relative_detail}</p>
<p>Industry benchmarks matter because they contextualize a tool's safety profile. A score that looks moderate in isolation may actually represent strong performance within a challenging category — or vice versa. Nerq's category-relative analysis helps teams make informed decisions by showing not just absolute quality, but how a tool ranks against its direct peers.</p>
""")

    # ── Section 9: Trust Score History ──
    sections.append(f"""
<h2>Trust Score History</h2>
<p>Nerq continuously monitors {dn} and recalculates its Trust Score as new data becomes available. Our scoring engine ingests real-time signals from source repositories, vulnerability databases (NVD, OSV.dev), package registries, and community metrics. When a new CVE is published, a major release ships, or maintenance patterns change, {dn}'s score is updated within 24 hours.</p>
<p>Historical trust trends reveal whether a tool is improving, stable, or declining over time. A tool that consistently maintains or improves its score demonstrates ongoing commitment to security and quality. Conversely, a downward trend may signal reduced maintenance, growing technical debt, or unresolved vulnerabilities. To track {dn}'s score over time, use the Nerq API: <code>GET nerq.ai/v1/preflight?target={_esc(name)}&amp;include=history</code></p>
<p>Nerq retains trust score snapshots at regular intervals, enabling trend analysis across weeks and months. Enterprise users can access detailed historical reports showing how each dimension — security, maintenance, documentation, compliance, and community — has evolved independently, providing granular visibility into which aspects of {dn} are strengthening or weakening over time.</p>
""")

    # ── Section 10: Comparison callout ──
    if alternatives and len(alternatives) > 0:
        alt_names = [_esc(a.get("name", "").split("/")[-1]) for a in alternatives[:3]]
        sections.append(f"""
<h2>{dn} vs Alternatives</h2>
<p>In the {_esc(category)} category, {dn} scores {score:.1f}/100. {'It ranks among the top tools in its category.' if score >= 75 else 'There are higher-scoring alternatives available.'} For a detailed comparison, see:</p>
<ul style="line-height:2;font-size:15px">
{"".join(f'<li><a href="/compare/{_esc(slug)}-vs-{_esc(a.get("name", "").lower().replace("/", "").replace(" ", "-"))}">{dn} vs {an}</a> — Trust Score: {a.get("trust_score", 0):.1f}/100</li>' for a, an in zip(alternatives[:3], alt_names))}
</ul>
""")

    # ── Section 11: Key Takeaways ──
    verified_label = "Nerq Verified" if is_verified else "not yet Nerq Verified"
    if score >= 80:
        overall_verdict = f"{dn} demonstrates strong trust signals and is well-suited for production use with standard security precautions."
    elif score >= 70:
        overall_verdict = f"{dn} meets the minimum threshold for production deployment, though monitoring and additional guardrails are recommended."
    elif score >= 50:
        overall_verdict = f"{dn} shows moderate trust signals. Conduct thorough due diligence before deploying to production environments."
    else:
        overall_verdict = f"{dn} has significant trust gaps. Consider higher-rated alternatives unless specific requirements mandate its use."

    takeaway_bullets = [
        f"{dn} has a Trust Score of <strong>{score:.1f}/100 ({_esc(grade)})</strong> and is {verified_label}.",
        f"{overall_verdict}",
        f"Among {cat_label}, {dn} scores {relative_pos}, {'demonstrating above-average reliability' if diff > 0 else 'suggesting room for improvement relative to peers'}.",
        f"Always verify safety independently — use Nerq's <a href=\"/v1/preflight?target={_esc(name)}\">Preflight API</a> for automated, up-to-date trust checks before integration.",
    ]
    sections.append(f"""
<h2>Key Takeaways</h2>
<ul style="line-height:2;font-size:15px">
{"".join(f"<li>{t}</li>" for t in takeaway_bullets)}
</ul>
""")

    if not sections:
        return ""

    return f"""
<div style="margin-top:32px;border-top:1px solid #e5e7eb;padding-top:24px">
{''.join(sections)}
</div>
"""


_RELATED_TOOLS = [
    ("cursor", "Cursor"), ("chatgpt", "ChatGPT"), ("claude", "Claude"),
    ("windsurf", "Windsurf"), ("bolt", "Bolt"), ("cline", "Cline"),
    ("github-copilot", "GitHub Copilot"), ("gemini", "Gemini"),
    ("ollama", "Ollama"), ("langchain", "LangChain"),
    ("openai", "OpenAI"), ("n8n", "n8n"), ("comfyui", "ComfyUI"),
    ("crewai", "CrewAI"), ("autogpt", "AutoGPT"), ("devin", "Devin"),
    ("continue", "Continue"), ("llamaindex", "LlamaIndex"),
    ("hugging-face", "Hugging Face"), ("stable-diffusion", "Stable Diffusion"),
]


def _related_safety_links(current_slug):
    """Generate related safety check links, excluding the current page."""
    links = []
    for r_slug, r_name in _RELATED_TOOLS:
        if r_slug == current_slug:
            continue
        links.append(
            f'<a href="/safe/{_esc(r_slug)}" style="font-size:13px;padding:4px 10px;'
            f'border:1px solid #e5e7eb;color:#6b7280;text-decoration:none">'
            f'Is {_esc(r_name)} safe?</a>'
        )
    return "\n".join(links)


# ── Discovery links cache (Redis-backed, 1h TTL) ──────────────────────
_discovery_cache = {}
_DISCOVERY_TTL = 3600  # 1 hour

def _get_discovery_links(registry, current_slug):
    """Generate 'Popular in same registry' + 'Recently analyzed' link sections.
    Cached per registry for 1 hour to avoid DB load."""
    import time as _t

    # Check in-memory cache
    cache_key = f"disc:{registry}"
    if cache_key in _discovery_cache:
        html, ts = _discovery_cache[cache_key]
        if _t.time() - ts < _DISCOVERY_TTL:
            # Filter out current slug from cached HTML
            return html.replace(f'href="/safe/{_esc(current_slug)}"', f'href="/safe/{_esc(current_slug)}" style="display:none"')

    session = get_session()
    try:
        session.execute(text("SET LOCAL statement_timeout = '3s'"))

        # A) Popular in same registry (top 10 by trust_score)
        pop_rows = session.execute(text("""
            SELECT slug, name, trust_score, trust_grade FROM software_registry
            WHERE registry = :reg AND trust_score IS NOT NULL AND trust_score > 30
              AND description IS NOT NULL AND LENGTH(description) > 20
            ORDER BY trust_score DESC LIMIT 12
        """), {"reg": registry}).fetchall()

        pop_html = ""
        if pop_rows:
            items = ""
            for r in pop_rows:
                _s, _n, _ts, _g = r
                _dn = _esc(_n.split("/")[-1].replace("-", " ").replace("_", " ").title()[:30])
                items += f'<a href="/safe/{_esc(_s)}" class="disc-link">{_dn} <span>{_ts:.0f}</span></a>'
            _disc_reg = _REGISTRY_DISPLAY.get(registry, registry.replace("_", " ").title() if registry else "")
            pop_html = f'<div class="disc-section"><h3 style="font-size:14px;font-weight:600;margin:0 0 8px">Popular in {_esc(_disc_reg)}</h3><div class="disc-grid">{items}</div></div>'

        # B) Recently analyzed (latest 10 from published registries only)
        try:
            from agentindex.quality_gate import get_publishable_registries
            _pub_regs = get_publishable_registries()
        except Exception:
            _pub_regs = {"npm", "pypi", "crates", "android", "ios", "steam", "vpn", "wordpress"}
        _pub_list = ",".join(f"'{r}'" for r in _pub_regs) if _pub_regs else "'npm'"
        recent_rows = session.execute(text(f"""
            SELECT slug, name, registry, trust_score FROM software_registry
            WHERE enriched_at IS NOT NULL AND description IS NOT NULL AND LENGTH(description) > 20
              AND trust_score IS NOT NULL AND trust_score > 30
              AND registry IN ({_pub_list})
            ORDER BY enriched_at DESC LIMIT 10
        """)).fetchall()

        recent_html = ""
        if recent_rows:
            items = ""
            for r in recent_rows:
                _s, _n, _reg, _ts = r
                _dn = _esc(_n.split("/")[-1].replace("-", " ").replace("_", " ").title()[:25])
                items += f'<a href="/safe/{_esc(_s)}" class="disc-link">{_dn} <span>{_reg}</span></a>'
            recent_html = f'<div class="disc-section"><h3 style="font-size:14px;font-weight:600;margin:0 0 8px">Recently Analyzed</h3><div class="disc-grid">{items}</div></div>'

        # C) Related /best/ categories
        _best_map = {
            "npm": [("npm-packages", "npm Packages"), ("infrastructure", "Infrastructure"), ("security", "Security Tools")],
            "pypi": [("python-packages", "Python Packages"), ("data", "Data Tools"), ("ai-tools", "AI Tools")],
            "crates": [("best-rust-crates", "Rust Crates"), ("security", "Security"), ("devops", "DevOps")],
            "chrome": [("chrome-extensions", "Chrome Extensions"), ("safest-browsers", "Safest Browsers")],
            "firefox": [("best-firefox-addons", "Firefox Add-ons"), ("safest-browsers", "Safest Browsers")],
            "android": [("android-apps", "Android Apps"), ("most-private-apps-2026", "Most Private Apps")],
            "ios": [("ios-apps", "iOS Apps"), ("most-private-apps-2026", "Most Private Apps")],
            "vpn": [("safest-vpns", "Safest VPNs"), ("most-private-apps-2026", "Most Private Apps")],
            "steam": [("steam-games", "Steam Games"), ("safest-games", "Safest Games")],
            "website": [("safest-websites", "Safest Websites"), ("safest-shopping-sites", "Shopping Sites")],
            "wordpress": [("best-wordpress-plugins", "WordPress Plugins")],
            "vscode": [("vscode-extensions", "VS Code Extensions")],
            "saas": [("saas", "SaaS Platforms"), ("marketing", "Marketing Tools")],
            "ai_tool": [("ai-tools", "AI Tools"), ("ai-coding-assistants", "Coding Assistants")],
            "ingredient": [("health", "Health Products"), ("safest-food-additives", "Food Additives")],
            "supplement": [("best-supplements", "Supplements"), ("health", "Health Products")],
            "country": [("safest-countries", "Safest Countries")],
            "charity": [("charities", "Charities")],
        }
        best_links = _best_map.get(registry, [])
        best_html = ""
        if best_links:
            items = "".join(f'<a href="/best/{_esc(s)}" class="disc-link">{_esc(n)}</a>' for s, n in best_links)
            best_html = f'<div class="disc-section"><h3 style="font-size:14px;font-weight:600;margin:0 0 8px">Browse Categories</h3><div class="disc-grid">{items}</div></div>'

        full_html = f"""<div style="margin-top:24px;padding-top:16px;border-top:1px solid #f1f5f9">
<style>.disc-grid{{display:flex;flex-wrap:wrap;gap:6px}}.disc-link{{font-size:12px;padding:4px 10px;border:1px solid #e2e8f0;border-radius:6px;color:#374151;text-decoration:none;white-space:nowrap}}.disc-link:hover{{border-color:#2563eb;color:#2563eb}}.disc-link span{{color:#94a3b8;font-size:11px;margin-left:4px}}.disc-section{{margin-bottom:12px}}</style>
{pop_html}{best_html}{recent_html}
</div>"""

        _discovery_cache[cache_key] = (full_html, _t.time())
        return full_html
    except Exception as e:
        logger.warning(f"Discovery links error: {e}")
        return ""
    finally:
        session.close()


# ── See Also i18n ────────────────────────────────────────────
_SEE_ALSO_I18N = {
    "es": ("Ver también", "Alternativas a {name}", "Mejores {category} 2026"),
    "de": ("Siehe auch", "Alternativen zu {name}", "Beste {category} 2026"),
    "fr": ("Voir aussi", "Alternatives à {name}", "Meilleurs {category} 2026"),
    "ja": ("関連項目", "{name}の代替", "最高の{category} 2026"),
    "pt": ("Veja também", "Alternativas a {name}", "Melhores {category} 2026"),
    "id": ("Lihat juga", "Alternatif untuk {name}", "{category} Terbaik 2026"),
    "cs": ("Viz také", "Alternativy k {name}", "Nejlepší {category} 2026"),
    "th": ("ดูเพิ่มเติม", "ทางเลือกแทน {name}", "{category} ที่ดีที่สุด 2026"),
    "tr": ("Ayrıca bakınız", "{name} alternatifleri", "En iyi {category} 2026"),
    "ro": ("Vezi și", "Alternative la {name}", "Cele mai bune {category} 2026"),
    "hi": ("यह भी देखें", "{name} के विकल्प", "सर्वश्रेष्ठ {category} 2026"),
    "ru": ("См. также", "Альтернативы {name}", "Лучшие {category} 2026"),
    "pl": ("Zobacz także", "Alternatywy dla {name}", "Najlepsze {category} 2026"),
    "ko": ("참고 항목", "{name} 대안", "최고의 {category} 2026"),
    "it": ("Vedi anche", "Alternative a {name}", "Migliori {category} 2026"),
    "vi": ("Xem thêm", "Lựa chọn thay thế cho {name}", "{category} tốt nhất 2026"),
    "nl": ("Zie ook", "Alternatieven voor {name}", "Beste {category} 2026"),
    "sv": ("Se även", "Alternativ till {name}", "Bästa {category} 2026"),
    "zh": ("另请参阅", "{name}的替代品", "最佳{category} 2026"),
    "da": ("Se også", "Alternativer til {name}", "Bedste {category} 2026"),
    "no": ("Se også", "Alternativer til {name}", "Beste {category} 2026"),
    "ar": ("انظر أيضاً", "بدائل {name}", "أفضل {category} 2026"),
}

# Cross-vertical link config: registry → list of (best_slug, label_en)
_SEE_ALSO_CROSS = {
    "vpn": [("safest-password-managers", "Password Managers"), ("safest-antivirus-software", "Antivirus")],
    "password_manager": [("safest-vpns", "VPNs"), ("safest-antivirus-software", "Antivirus")],
    "antivirus": [("safest-vpns", "VPNs"), ("safest-password-managers", "Password Managers")],
    "hosting": [("safest-website-builders", "Website Builders")],
    "website_builder": [("safest-web-hosting", "Web Hosting")],
    "npm": [("safest-pypi-packages", "Python Packages")],
    "pypi": [("safest-npm-packages", "npm Packages")],
    "crates": [("safest-npm-packages", "npm Packages")],
    "crypto": [("safest-vpns", "VPNs")],
}


_REGISTRY_DISPLAY = {
    "vpn": "VPNs", "password_manager": "Password Managers", "antivirus": "Antivirus",
    "hosting": "Web Hosting", "website_builder": "Website Builders", "saas": "SaaS",
    "crypto": "Crypto Exchanges", "npm": "npm Packages", "pypi": "Python Packages",
    "crates": "Rust Crates", "chrome": "Chrome Extensions", "firefox": "Firefox Add-ons",
    "vscode": "VS Code Extensions", "wordpress": "WordPress Plugins",
    "ios": "iOS Apps", "android": "Android Apps", "steam": "Steam Games",
    "nuget": "NuGet Packages", "go": "Go Packages", "gems": "Ruby Gems",
    "packagist": "PHP Packages", "homebrew": "Homebrew",
    "website": "Websites", "country": "Countries",
}


_CROSS_CAT_I18N = {
    "Password Managers": {"es":"Gestores de contraseñas","de":"Passwort-Manager","fr":"Gestionnaires de mots de passe","ja":"パスワードマネージャー","pt":"Gerenciadores de senhas","id":"Pengelola kata sandi","cs":"Správci hesel","th":"โปรแกรมจัดการรหัสผ่าน","tr":"Şifre yöneticileri","ro":"Managere de parole","hi":"पासवर्ड मैनेजर","ru":"Менеджеры паролей","pl":"Menedżery haseł","ko":"비밀번호 관리자","it":"Gestori di password","vi":"Trình quản lý mật khẩu","nl":"Wachtwoordmanagers","sv":"Lösenordshanterare","zh":"密码管理器","da":"Adgangskodeadministratorer","no":"Passordbehandlere","ar":"مديرو كلمات المرور"},
    "Antivirus": {"es":"Antivirus","de":"Antivirus","fr":"Antivirus","ja":"アンチウイルス","pt":"Antivírus","id":"Antivirus","cs":"Antivirus","th":"แอนตี้ไวรัส","tr":"Antivirüs","ro":"Antivirus","hi":"एंटीवायरस","ru":"Антивирус","pl":"Antywirus","ko":"안티바이러스","it":"Antivirus","vi":"Phần mềm diệt virus","nl":"Antivirus","sv":"Antivirus","zh":"杀毒软件","da":"Antivirus","no":"Antivirus","ar":"مضاد الفيروسات"},
    "VPNs": {"es":"VPNs","de":"VPNs","fr":"VPN","ja":"VPN","pt":"VPNs","id":"VPN","cs":"VPN","th":"VPN","tr":"VPN","ro":"VPN-uri","hi":"VPN","ru":"VPN","pl":"VPN","ko":"VPN","it":"VPN","vi":"VPN","nl":"VPN's","sv":"VPN","zh":"VPN","da":"VPN","no":"VPN-er","ar":"VPN"},
    "Website Builders": {"es":"Creadores de sitios web","de":"Website-Baukästen","fr":"Constructeurs de sites","ja":"ウェブサイトビルダー","pt":"Construtores de sites","id":"Pembuat situs","cs":"Stavitelé webů","th":"เครื่องมือสร้างเว็บไซต์","tr":"Web sitesi oluşturucular","ro":"Constructori de site-uri","hi":"वेबसाइट बिल्डर","ru":"Конструкторы сайтов","pl":"Kreatory stron","ko":"웹사이트 빌더","it":"Costruttori di siti","vi":"Trình tạo website","nl":"Websitebouwers","sv":"Webbplatsbyggare","zh":"网站构建器","da":"Webstedbyggere","no":"Nettstedsbyggere","ar":"أدوات بناء المواقع"},
    "Web Hosting": {"es":"Hosting web","de":"Web-Hosting","fr":"Hébergement web","ja":"Webホスティング","pt":"Hospedagem web","id":"Hosting web","cs":"Webhosting","th":"เว็บโฮสติ้ง","tr":"Web barındırma","ro":"Găzduire web","hi":"वेब होस्टिंग","ru":"Веб-хостинг","pl":"Hosting","ko":"웹 호스팅","it":"Hosting web","vi":"Hosting web","nl":"Webhosting","sv":"Webbhotell","zh":"虚拟主机","da":"Webhosting","no":"Webhotell","ar":"استضافة الويب"},
    "Python Packages": {"es":"Paquetes Python","de":"Python-Pakete","fr":"Paquets Python","ja":"Pythonパッケージ","pt":"Pacotes Python","id":"Paket Python","cs":"Python balíčky","th":"แพ็คเกจ Python","tr":"Python paketleri","ro":"Pachete Python","hi":"Python पैकेज","ru":"Пакеты Python","pl":"Pakiety Python","ko":"Python 패키지","it":"Pacchetti Python","vi":"Gói Python","nl":"Python-pakketten","sv":"Python-paket","zh":"Python包","da":"Python-pakker","no":"Python-pakker","ar":"حزم Python"},
    "npm Packages": {"es":"Paquetes npm","de":"npm-Pakete","fr":"Paquets npm","ja":"npmパッケージ","pt":"Pacotes npm","id":"Paket npm","cs":"npm balíčky","th":"แพ็คเกจ npm","tr":"npm paketleri","ro":"Pachete npm","hi":"npm पैकेज","ru":"Пакеты npm","pl":"Pakiety npm","ko":"npm 패키지","it":"Pacchetti npm","vi":"Gói npm","nl":"npm-pakketten","sv":"npm-paket","zh":"npm包","da":"npm-pakker","no":"npm-pakker","ar":"حزم npm"},
}


def _build_see_also(slug, display_name, source, sim_rows, best_slug, lang="en"):
    """Build a See Also section with contextual links."""
    i18n = _SEE_ALSO_I18N.get(lang, ("See Also", "Alternatives to {name}", "Best {category} 2026"))
    heading = i18n[0]
    alts_label = i18n[1].format(name=_esc(display_name))
    _lp = f"/{lang}" if lang != "en" else ""
    _reg_display_en = _REGISTRY_DISPLAY.get(source, source.replace("_", " ").title() if source else "Tools")
    # Localize registry display name for the best-in-category link
    _reg_display = _CROSS_CAT_I18N.get(_reg_display_en, {}).get(lang, _reg_display_en) if lang != "en" else _reg_display_en
    best_label = i18n[2].format(category=_reg_display)

    links = []
    # 1. Compare with top 2 similar entities
    if sim_rows:
        for r in sim_rows[:2]:
            r_slug = r[0]
            r_name = r[1]
            links.append(f'<li><a href="{_lp}/compare/{_esc(slug)}-vs-{_esc(r_slug)}">{_esc(display_name)} vs {_esc(r_name)}</a></li>')

    # 2. Alternatives page
    links.append(f'<li><a href="{_lp}/alternatives/{_esc(slug)}">{alts_label}</a></li>')

    # 3. Best in category
    if best_slug:
        links.append(f'<li><a href="{_lp}/best/{best_slug}">{best_label}</a></li>')

    # 4. Cross-vertical links (localized category names)
    cross = _SEE_ALSO_CROSS.get(source, [])
    for c_slug, c_label in cross[:1]:  # max 1 cross-vertical to stay at 5 links
        _loc_label = _CROSS_CAT_I18N.get(c_label, {}).get(lang, c_label)
        c_best_label = i18n[2].format(category=_loc_label)
        links.append(f'<li><a href="{_lp}/best/{c_slug}">{c_best_label}</a></li>')

    if not links:
        return ""

    items = "\n    ".join(links)
    return f'''<section class="see-also" style="margin-top:28px;padding-top:20px;border-top:1px solid #e2e8f0">
  <h2 style="font-size:15px;font-weight:600;color:#334155;margin:0 0 10px">{heading}</h2>
  <ul style="margin:0;padding:0;list-style:none">
    {items}
  </ul>
  <style>.see-also a{{color:#2563eb;text-decoration:none;font-size:14px;line-height:2}}.see-also a:hover{{text-decoration:underline}}</style>
</section>'''


def _get_alternatives(category, current_name, current_score, limit=5):
    """Get popular alternatives in same category, ordered by stars then score."""
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT name, slug, COALESCE(trust_score_v2, trust_score) as trust_score,
                   trust_grade, category, source, stars
            FROM entity_lookup
            WHERE is_active = true
              AND category = :cat
              AND name_lower != LOWER(:name)
              AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
              AND agent_type IN ('agent', 'mcp_server', 'tool')
            ORDER BY stars DESC NULLS LAST, COALESCE(trust_score_v2, trust_score) DESC
            LIMIT :lim
        """), {"cat": category, "name": current_name, "lim": limit}).fetchall()
        return [dict(r._mapping) for r in rows]
    finally:
        session.close()


def _get_cross_products(author, current_registry, current_slug, limit=5):
    """Find same entity across different registries.
    Uses two strategies: (1) same slug in other registries, (2) normalized author match.
    """
    session = get_session()
    try:
        results = []
        seen = set()

        # Strategy 1: Same slug, different registry (NordVPN in vpn, chrome, android, etc.)
        rows = session.execute(text("""
            SELECT name, slug, registry, trust_score, trust_grade
            FROM software_registry
            WHERE slug = :slug AND registry != :reg
                AND trust_score IS NOT NULL AND trust_score > 0
            ORDER BY trust_score DESC
            LIMIT :lim
        """), {"slug": current_slug, "reg": current_registry, "lim": limit}).fetchall()
        for r in rows:
            d = dict(r._mapping)
            key = (d["slug"], d["registry"])
            if key not in seen:
                results.append(d)
                seen.add(key)

        # Strategy 2: Simple author match (no regex — fast index scan)
        if author and author not in ("Unknown", "unknown", "", "UNKNOWN") and len(author) >= 3:
            if author.lower().strip() not in ("unknown", "your name", "test", "admin", "user"):
                rows2 = session.execute(text("""
                    SELECT name, slug, registry, trust_score, trust_grade
                    FROM software_registry
                    WHERE LOWER(author) = :auth
                        AND registry != :reg AND slug != :slug
                        AND trust_score IS NOT NULL AND trust_score > 0
                    ORDER BY trust_score DESC
                    LIMIT :lim
                """), {"auth": author.lower().strip(), "reg": current_registry, "slug": current_slug, "lim": limit}).fetchall()
                for r in rows2:
                    d = dict(r._mapping)
                    key = (d["slug"], d["registry"])
                    if key not in seen:
                        results.append(d)
                        seen.add(key)

        return results[:limit]
    except Exception:
        return []
    finally:
        session.close()


def _get_cross_registry_links(slug, current_registry, limit=10):
    """Same-slug entries in OTHER registries (L5 cross-registry linking, T153).
    Read-only; never mutates. Returns [] on any error so a render can never fail."""
    if not slug:
        return []
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT slug, registry, trust_score
            FROM software_registry
            WHERE slug = :slug AND registry != :reg
              AND trust_score IS NOT NULL AND trust_score > 0
            ORDER BY trust_score DESC
            LIMIT :lim
        """), {"slug": slug, "reg": current_registry or "", "lim": limit}).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception:
        return []
    finally:
        session.close()


def _render_cross_registry_section(slug, source):
    """Build the 'Also on other registries' HTML for the L5 link section.
    Returns '' when env=off, or when env=live but no cross-registry rows found.
    Env=shadow runs the query for observability but renders nothing."""
    mode = _L5_CROSSREG_MODE
    if mode not in ("shadow", "live"):
        return ""
    rows = _get_cross_registry_links(slug, source, limit=10)
    if mode == "shadow" or not rows:
        return ""
    _links = " &middot; ".join(
        f'<a href="/safe/{_esc(r["slug"])}">'
        f'{_esc(_REGISTRY_DISPLAY.get(r["registry"], r["registry"].replace("_", " ").title() if r["registry"] else "registry"))}'
        f'</a>'
        for r in rows
    )
    return (
        '<section class="section cross-registry-links" '
        'style="font-size:14px;color:#64748b;margin:8px 0">'
        f'Also on: {_links}'
        '</section>'
    )


def _make_slug(name):
    """Generate a URL slug from agent name."""
    slug = name.lower().strip()
    for ch in ['/', '\\', '(', ')', '[', ']', '{', '}', ':', ';', ',', '!', '?',
               '@', '#', '$', '%', '^', '&', '*', '=', '+', '|', '<', '>', '~', '`', "'", '"']:
        slug = slug.replace(ch, '')
    slug = slug.replace(' ', '-').replace('_', '-').replace('.', '-')
    while '--' in slug:
        slug = slug.replace('--', '-')
    return slug.strip('-')


def _queue_for_crawling(slug, bot="unknown"):
    """Add slug to crawl_queue for future crawling. Uses write path (primary)."""
    try:
        from agentindex.db.models import get_write_session
        session = get_write_session()
        session.execute(text("""
            INSERT INTO crawl_queue (slug, requested_by)
            VALUES (:slug, :bot)
            ON CONFLICT (slug) DO UPDATE SET
                request_count = crawl_queue.request_count + 1,
                last_requested = NOW()
        """), {"slug": slug.lower(), "bot": bot})
        session.commit()
        session.close()
    except Exception:
        pass  # Never fail page render for queue logging


def _render_sub_page(slug, agent, sub_type):
    """Render /safe/{slug}/privacy or /safe/{slug}/security sub-page."""
    name = agent.get("name", slug)
    display_name = _DISPLAY_NAMES.get(name, name.split("/")[-1].replace("-", " ").title())
    score = agent.get("trust_score") or 0
    score_str = f"{score:.1f}" if isinstance(score, float) else str(score)
    grade = agent.get("trust_grade") or "N/A"
    source = agent.get("source") or "unknown"
    description = agent.get("description") or ""
    security_score = agent.get("security_score")
    _rp = _get_registry_page(source)
    _dn = _esc(display_name)
    _today = date.today().isoformat()

    if sub_type == "privacy":
        title = f"{display_name} Privacy Analysis — Data Collection & Tracking | Nerq"
        h1 = f"What data does {display_name} collect?"
        content = f"""<p class="ai-summary">{_dn} has a Nerq Trust Score of {score_str}/100 ({_esc(grade)}). This privacy analysis examines data collection practices, third-party trackers, and privacy policy transparency.</p>
<h2>Data Collection Overview</h2>
<p>{_dn} is a {_rp['entity_word']}. {_esc(description[:200]) if description else ''} Users should review the privacy policy for specific data handling practices.</p>
<h2>Privacy Score</h2>
<p>Security/Privacy score: {f'{security_score:.0f}/100' if security_score is not None else 'Under assessment'}. This score reflects data collection scope, tracker presence, and privacy policy clarity.</p>
<h2>Recommendations</h2>
<ul><li>Review the privacy policy before creating an account</li><li>Check what permissions are requested</li><li>Consider what data you share and whether it is necessary</li><li>Use privacy-focused alternatives if data minimization is important to you</li></ul>"""
    else:  # security
        title = f"{display_name} Security Assessment — Vulnerabilities & Certifications | Nerq"
        h1 = f"Is {display_name} secure?"
        content = f"""<p class="ai-summary">{_dn} has a Nerq Trust Score of {score_str}/100 ({_esc(grade)}). This security assessment covers known vulnerabilities, security certifications, and incident history.</p>
<h2>Security Score</h2>
<p>Security score: {f'{security_score:.0f}/100' if security_score is not None else 'Under assessment'}. Based on vulnerability exposure, security practices, and update frequency.</p>
<h2>Vulnerability History</h2>
<p>Nerq monitors {_dn} against NVD, OSV.dev, and registry-specific vulnerability databases. Check the main trust report for current vulnerability status.</p>
<h2>Security Recommendations</h2>
<ul><li>Keep {_dn} updated to the latest version</li><li>Review security advisories regularly</li><li>Follow the principle of least privilege when configuring permissions</li><li>Monitor the <a href="/safe/{_esc(slug)}">full trust report</a> for changes</li></ul>"""

    canonical = f"https://nerq.ai/safe/{slug}/{sub_type}"
    hreflang = render_hreflang(f"/safe/{slug}/{sub_type}")

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_dn} {sub_type} analysis. Trust Score {score_str}/100 ({_esc(grade)}). Independent assessment by Nerq.">
<link rel="canonical" href="{canonical}">
{hreflang}
<meta property="og:title" content="{_esc(title)}">
<meta name="nerq:type" content="{sub_type}">
<meta name="nerq:entity" content="{_esc(slug)}">
<meta name="nerq:score" content="{score_str}">
<meta property="article:modified_time" content="{_today}T12:00:00Z">
<meta name="robots" content="{'index, follow' if score and float(score) >= 30 else 'noindex, follow'}">
<link rel="stylesheet" href="/static/nerq.css?v=13">
{NERQ_CSS}
</head><body>
{NERQ_NAV}
<main class="container" style="padding-top:16px;padding-bottom:40px">
<nav class="breadcrumb"><a href="/">Nerq</a> &rsaquo; <a href="/safe">Safety</a> &rsaquo; <a href="/safe/{_esc(slug)}">{_dn}</a> &rsaquo; {sub_type.title()}</nav>
<h1 style="font-size:1.5rem;font-weight:700;margin:8px 0 16px">{_esc(h1)}</h1>
{content}
<div style="margin-top:24px;display:flex;gap:12px;flex-wrap:wrap">
<a href="/safe/{_esc(slug)}" class="cross-link">Full Trust Report</a>
<a href="/safe/{_esc(slug)}/{'security' if sub_type == 'privacy' else 'privacy'}" class="cross-link">{'Security' if sub_type == 'privacy' else 'Privacy'} Analysis</a>
<a href="/alternatives/{_esc(slug)}" class="cross-link">Alternatives</a>
<a href="/v1/preflight?target={_esc(name)}" class="cross-link">API Data</a>
</div>
<p style="margin-top:24px;font-size:12px;color:#94a3b8">Last updated: {_today}. <a href="/safe/{_esc(slug)}">View full trust report</a>.</p>
</main>
{NERQ_FOOTER}
</body></html>"""


def _render_not_analyzed_page(slug, display_name, lang="en"):
    """Render an honest 'not yet analyzed' page instead of a fake 0/100 rating.
    Also queues the slug for future crawling."""
    _queue_for_crawling(slug)
    _dn = _esc(display_name)
    _sl = _esc(slug)
    _na = _t("not_analyzed_h1", lang, name=_dn)
    _na_title = _t("not_analyzed_title", lang, name=_dn)
    _na_msg = _t("not_analyzed_msg", lang, name=_dn)
    _na_meanwhile = _t("not_analyzed_meanwhile", lang)
    _na_search = _t("not_analyzed_search", lang)
    _na_api = _t("not_analyzed_api", lang)
    _na_browse = _t("not_analyzed_browse", lang)
    _na_no_score = _t("not_analyzed_no_score", lang)
    _na_no_fabricate = _t("not_analyzed_no_fabricate", lang)
    return f"""<!DOCTYPE html><html lang="{lang}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_na_title}</title>
<meta name="description" content="{_na_msg}">
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
<style>
.nav{{border-bottom:1px solid #e2e8f0;padding:10px 0;background:#fff}}
.nav-inner{{max-width:1100px;margin:0 auto;padding:0 20px;display:flex;align-items:center;gap:16px}}
.nav-logo{{font-size:20px;font-weight:700;color:#0f172a;text-decoration:none}}
</style>
</head><body>
{NERQ_NAV}
<main class="container" style="padding:40px 20px;max-width:780px;margin:0 auto">
<h1>{_na}</h1>
<p style="font-size:16px;color:#64748b;margin:12px 0 24px">
{_na_msg}
</p>
<div style="border:1px solid #e2e8f0;border-radius:12px;padding:24px;margin:20px 0">
<p style="font-size:15px;margin:0 0 16px"><strong>{_na_meanwhile}</strong></p>
<ul style="font-size:14px;color:#334155;line-height:2;padding-left:20px">
<li>{_na_search}: <a href="/">{_t("breadcrumb_home", lang)}</a></li>
<li>{_na_api}: <code>GET /v1/preflight?target={_sl}</code></li>
<li>{_na_browse}: <a href="/apps">Apps</a>, <a href="/npm">Packages</a>, <a href="/websites">Websites</a></li>
</ul>
</div>
<p style="font-size:13px;color:#94a3b8">
{_na_no_score}
{_na_no_fabricate}
</p>
</main>
{NERQ_FOOTER}
</body></html>"""


def _render_travel_page(slug, agent_info, lang="en"):
    """Render a dedicated travel/country page — completely separate from the software template.
    No software language: no CVE, license, dependencies, 'recommended for use', 'is a software'.
    Travel-specific: crime, health, disasters, traveler types, advisories, practical info.
    """
    name = agent_info.get("name", slug)
    resolved = _resolve_entity(slug)
    if not resolved:
        norm_slug = slug.replace("-", "").replace("_", "").replace(" ", "")
        if norm_slug != slug:
            resolved = _resolve_entity(norm_slug)
    agent = resolved or agent_info

    name = agent.get("name") or name
    display_name = name.split("/")[-1].replace("-", " ").replace("_", " ").title()
    score = float(agent.get("trust_score") or 0)
    score_str = f"{score:.1f}"
    grade = agent.get("trust_grade") or "N/A"
    description = agent.get("description") or ""
    source = agent.get("source") or "country"
    security_score = agent.get("security_score")
    popularity_score = agent.get("popularity_score")
    _is_king = agent.get("is_king", False)
    _dn = _esc(display_name)

    # Travel advisory based on score
    if score >= 80:
        advisory = "Exercise Normal Precautions"
        advisory_short = "Level 1"
        vb_color, vb_bg, vb_text = "#16a34a", "#f0fdf4", "Safe to Visit"
    elif score >= 60:
        advisory = "Exercise Increased Caution"
        advisory_short = "Level 2"
        vb_color, vb_bg, vb_text = "#d97706", "#fffbeb", "Exercise Caution"
    elif score >= 40:
        advisory = "Reconsider Travel"
        advisory_short = "Level 3"
        vb_color, vb_bg, vb_text = "#ea580c", "#fff7ed", "Reconsider Travel"
    else:
        advisory = "Do Not Travel"
        advisory_short = "Level 4"
        vb_color, vb_bg, vb_text = "#dc2626", "#fef2f2", "Avoid Travel"

    # Score dimensions — travel-specific (map from existing DB fields)
    _sec = security_score or score
    _pop = popularity_score or 50
    _privacy = agent.get("privacy_score") or score
    _reliability = agent.get("reliability_score") or score
    _transparency = agent.get("transparency_score") or max(40, score - 15)

    # Travel dimension mapping
    crime_score = round(_sec)
    political_score = round((_transparency + _reliability) / 2)
    health_score = round((_privacy + _reliability) / 2)
    disaster_score = round(max(30, _transparency))
    infra_score = round((_pop + _reliability) / 2)
    rights_score = round((_transparency + _privacy) / 2)

    def _risk_level(s):
        if s >= 80: return "Very Low Risk"
        if s >= 60: return "Low Risk"
        if s >= 40: return "Medium Risk"
        if s >= 20: return "High Risk"
        return "Very High Risk"

    def _risk_color(s):
        if s >= 80: return "#16a34a"
        if s >= 60: return "#22c55e"
        if s >= 40: return "#f59e0b"
        if s >= 20: return "#ef4444"
        return "#991b1b"

    # Grade pill class
    _g = grade.upper()[0] if grade and grade != "N/A" else "C"
    grade_bg_class = {"A": "bg-high", "B": "bg-good", "C": "bg-mid", "D": "bg-low", "F": "bg-crit"}.get(_g, "bg-mid")
    score_color_class = "sc-high" if score >= 80 else "sc-good" if score >= 60 else "sc-mid" if score >= 40 else "sc-low" if score >= 20 else "sc-crit"

    # Recommendation text
    if score >= 70:
        rec_text = f"recommended for all types of travelers"
        key_line = f"Recommended to visit — passes Nerq safety threshold"
    elif score >= 50:
        rec_text = f"suitable for experienced travelers with preparation"
        key_line = f"Exercise caution — research specific risks before traveling"
    else:
        rec_text = f"travel with significant caution"
        key_line = f"Significant safety concerns — check travel advisories before planning"

    # Definition lead — travel-specific, GEO-optimized first 200 words
    _desc_clean = description[:200].strip() if description else ""
    definition_lead = (
        f"{_dn} is a travel destination with a Nerq Safety Score of {score_str}/100 ({_esc(grade)}). "
        f"Travel advisory: {advisory}. "
        f"{_esc(_desc_clean)}"
    )

    # nerq:answer — complete, citable
    nerq_answer = (
        f"{_dn} has a Nerq Safety Score of {score_str}/100 ({_esc(grade)}). "
        f"Travel advisory: {advisory}. "
        f"Crime & Safety: {crime_score}/100. Health & Medical: {health_score}/100. "
        f"Natural Disaster Risk: {disaster_score}/100. "
        f"{_dn} is {rec_text}."
    )

    # Travel dimensions for breakdown
    _travel_dims = [
        ("Crime & Personal Safety", crime_score, "30%"),
        ("Political Stability", political_score, "20%"),
        ("Health & Medical", health_score, "15%"),
        ("Natural Disaster Risk", disaster_score, "15%"),
        ("Infrastructure & Transport", infra_score, "10%"),
        ("Traveler Rights", rights_score, "10%"),
    ]

    # Score breakdown HTML
    breakdown_html = ""
    for dim_name, dim_score, weight in _travel_dims:
        _bc = _risk_color(dim_score)
        _sc = "sc-high" if dim_score >= 80 else "sc-good" if dim_score >= 60 else "sc-mid" if dim_score >= 40 else "sc-low" if dim_score >= 20 else "sc-crit"
        breakdown_html += (
            f'<div class="breakdown-item">'
            f'<span class="breakdown-label">{dim_name} <span style="color:#94a3b8;font-size:12px">({weight})</span></span>'
            f'<div class="breakdown-bar"><div class="breakdown-fill" style="width:{dim_score}%;background:{_bc}"></div></div>'
            f'<span class="breakdown-val {_sc}">{dim_score}/100</span>'
            f'</div>'
        )

    # Key findings
    findings_html = ""
    for dim_name, dim_score, _ in _travel_dims:
        rl = _risk_level(dim_score)
        if dim_score >= 70:
            icon_cls, icon = "finding-good", "&#10003;"
        elif dim_score >= 40:
            icon_cls, icon = "finding-warn", "&#9888;"
        else:
            icon_cls, icon = "finding-bad", "&#10007;"
        findings_html += f'<div class="finding {icon_cls}"><span class="finding-icon">{icon}</span><span>{dim_name}: {dim_score}/100 — {rl}</span></div>'

    # Travel advisory section
    advisory_html = f"""<div class="section">
<h2 class="section-title">Official Travel Advisories</h2>
<div style="display:flex;flex-wrap:wrap;gap:8px;margin:12px 0">
<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;font-size:14px">
<span style="font-size:16px">&#127482;&#127480;</span> US State Dept: <b>{advisory}</b>
</div>
</div>
<p style="font-size:13px;color:#64748b;margin-top:8px">Advisory estimated from Nerq Safety Score. Check official sources for current status.</p>
</div>"""

    # Safety by traveler type
    traveler_html = f"""<div class="section">
<h2 class="section-title">{_t("safe_solo", lang, name=_dn)}</h2>
<p style="font-size:15px;line-height:1.7;color:#374151">
{_dn} has an overall safety score of {score_str}/100, {'making it suitable for solo travelers. ' if score >= 60 else 'so solo travelers should exercise additional caution. '}
Crime & personal safety score: {crime_score}/100. Infrastructure & transport score: {infra_score}/100.
{'Solo travelers generally report feeling safe.' if score >= 70 else 'Research specific areas and take standard precautions.' if score >= 50 else 'Solo travel requires significant preparation and local knowledge.'}
</p>

<h2 class="section-title">{_t("safe_women", lang, name=_dn)}</h2>
<p style="font-size:15px;line-height:1.7;color:#374151">
Traveler rights score: {rights_score}/100.
{'Women travelers generally report positive experiences.' if rights_score >= 70 else 'Women travelers should research local customs and take standard precautions.' if rights_score >= 50 else 'Women travelers should exercise significant caution and research local conditions carefully.'}
Check current travel advisories for specific guidance on women's safety in {_dn}.
</p>

<h2 class="section-title">{_t("safe_lgbtq", lang, name=_dn)}</h2>
<p style="font-size:15px;line-height:1.7;color:#374151">
Traveler rights score: {rights_score}/100.
{'LGBTQ+ travelers generally report few issues.' if rights_score >= 70 else 'LGBTQ+ travelers should research local laws and social attitudes.' if rights_score >= 50 else 'LGBTQ+ travelers should exercise significant caution — research local laws regarding same-sex relationships.'}
</p>

<h2 class="section-title">{_t("safe_families", lang, name=_dn)}</h2>
<p style="font-size:15px;line-height:1.7;color:#374151">
Overall safety: {score_str}/100. Health & medical: {health_score}/100. Infrastructure: {infra_score}/100.
{'Families can travel with confidence.' if score >= 70 else 'Families should plan carefully and research healthcare facilities.' if score >= 50 else 'Family travel requires significant preparation — research healthcare, safety, and logistics in detail.'}
</p>
</div>"""

    # Key risks section
    risk_cards = ""
    for dim_name, dim_score, _ in _travel_dims:
        rl = _risk_level(dim_score)
        risk_cls = "low" if dim_score >= 60 else "medium" if dim_score >= 40 else "high"
        risk_cards += f"""<div class="risk-card risk-{risk_cls}">
<h3>{dim_name} — {rl}</h3>
<p style="font-size:14px;color:#374151">Score: {dim_score}/100.</p>
</div>
"""

    risks_html = f"""<div class="section">
<h2 class="section-title">Key Safety Risks in {_dn}</h2>
<div style="display:flex;flex-direction:column;gap:12px;margin:12px 0">
{risk_cards}
</div>
</div>"""

    # Practical information
    practical_html = f"""<div class="section">
<h2 class="section-title">Practical Travel Information</h2>
<h3 style="font-size:16px;margin:16px 0 8px">Emergency Numbers</h3>
<p style="font-size:14px;color:#374151">Check local emergency numbers before traveling. International emergency: 112 (in many countries).</p>
<h3 style="font-size:16px;margin:16px 0 8px">Health & Medical</h3>
<p style="font-size:14px;color:#374151">Health score: {health_score}/100. {'Good healthcare infrastructure available.' if health_score >= 70 else 'Research healthcare facilities before traveling. Travel insurance strongly recommended.' if health_score >= 40 else 'Limited healthcare infrastructure — comprehensive travel insurance essential.'}</p>
<h3 style="font-size:16px;margin:16px 0 8px">Infrastructure</h3>
<p style="font-size:14px;color:#374151">Infrastructure score: {infra_score}/100. {'Well-developed transport and communications.' if infra_score >= 70 else 'Adequate infrastructure in major areas.' if infra_score >= 40 else 'Infrastructure may be limited — plan transportation in advance.'}</p>
</div>"""

    # FAQ — travel-specific
    _faq_items = [
        (_t("safe_visit_now", lang, name=_dn),
         f"{_dn} has a Nerq Safety Score of {score_str}/100 ({_esc(grade)}). Travel advisory: {advisory}. {'It is generally safe for tourists.' if score >= 70 else 'Exercise caution and check current advisories.' if score >= 50 else 'Check official travel advisories before planning.'}"),
        (f"Is {_dn} safe for solo female travelers?",
         f"Traveler rights score: {rights_score}/100. {'Generally safe for solo women.' if rights_score >= 70 else 'Research local customs and take standard precautions.' if rights_score >= 50 else 'Exercise significant caution — research local conditions.'}"),
        (_t("tap_water_safe", lang, name=_dn),
         f"Health & medical score: {health_score}/100. {'Good health infrastructure suggests safe tap water in urban areas.' if health_score >= 70 else 'Bottled water recommended as a precaution.' if health_score >= 50 else 'Use bottled water. Check local guidance.'}"),
        (f"What is the biggest safety risk in {_dn}?",
         f"Based on Nerq analysis, the {'lowest-scoring dimension' if True else ''} is {min(_travel_dims, key=lambda x: x[1])[0]} ({min(_travel_dims, key=lambda x: x[1])[1]}/100). Research this area before traveling."),
        (_t("safe_families", lang, name=_dn),
         f"Overall safety: {score_str}/100. Health: {health_score}/100. Infrastructure: {infra_score}/100. {'Suitable for family travel.' if score >= 70 else 'Plan carefully and research healthcare options.' if score >= 50 else 'Family travel requires significant preparation.'}"),
        (_t("need_vaccinations", lang, name=_dn),
         f"Health score: {health_score}/100. Check with your doctor and review WHO recommendations for {_dn} before traveling. Routine vaccinations should be up to date."),
        (f"Is {_dn} safe for LGBTQ+ travelers?",
         f"Traveler rights score: {rights_score}/100. {'Generally tolerant environment.' if rights_score >= 70 else 'Research local laws and social attitudes.' if rights_score >= 50 else 'Exercise significant caution — research local laws.'}"),
    ]

    faq_details = ""
    for fq, fa in _faq_items:
        faq_details += f'<details><summary>{fq}</summary><div class="faq-a">{fa}</div></details>\n'
    faq_html = f'<div class="section faq"><h2 class="section-title">{_t("faq", lang)}</h2>{faq_details}</div>'

    # Similar destinations
    similar_html = ""
    try:
        _ss = get_session()
        try:
            _rows = _ss.execute(text("""
                SELECT name, slug, trust_score, trust_grade FROM software_registry
                WHERE registry = 'country' AND slug != :slug AND trust_score IS NOT NULL
                ORDER BY ABS(trust_score - :score) ASC LIMIT 5
            """), {"slug": slug, "score": score}).fetchall()
            if _rows:
                _items = ""
                for r in _rows:
                    rd = dict(r._mapping)
                    _rn = _esc(rd["name"].split("/")[-1].replace("-", " ").replace("_", " ").title())
                    _rs = rd.get("trust_score") or 0
                    _rg = _esc(rd.get("trust_grade") or "")
                    _rslug = _esc(rd["slug"])
                    _items += f'<a href="/safe/{_rslug}" class="alt-card"><div class="alt-name">{_rn}</div><div class="alt-score">{_rs:.0f}/100 · {_rg}</div></a>'
                similar_html = f"""<div class="section">
<h2 class="section-title">Similar Safe Destinations</h2>
<div class="alt-grid">{_items}</div>
<p style="font-size:14px;margin-top:12px"><a href="/best/safest-countries">See all safest countries →</a></p>
</div>"""
        finally:
            _ss.close()
    except Exception:
        pass

    # Methodology
    methodology_html = f"""<div class="section">
<h2 class="section-title">{_t("how_calculated", lang)}</h2>
<p style="font-size:15px;line-height:1.7;color:#374151">{_dn}'s safety score of <b>{score_str}/100</b> ({_esc(grade)}) is based on data from the Global Peace Index, UNODC crime statistics, World Bank governance indicators, WHO health data, and government travel advisories. The score reflects 6 travel-specific dimensions: crime & personal safety ({crime_score}/100), political stability ({political_score}/100), health & medical ({health_score}/100), natural disaster risk ({disaster_score}/100), infrastructure & transport ({infra_score}/100), and traveler rights ({rights_score}/100).</p>
<p style="font-size:15px;line-height:1.7;color:#374151">Nerq indexes over 7.5 million entities across 26 registries including 158 countries, enabling direct cross-destination comparison. Scores are updated as new data becomes available.</p>
<p style="font-size:14px;color:#64748b"><a href="/methodology">Full methodology documentation</a> · <a href="/v1/preflight?target={_esc(name)}">Machine-readable data (JSON API)</a></p>
</div>"""

    # Freshness
    _today = datetime.now().strftime("%B %d, %Y")
    _today_iso = datetime.now().strftime("%Y-%m-%d")
    freshness_html = f'<p style="font-size:13px;color:#94a3b8;margin:24px 0 8px">Last updated: {_today} · Data sources: Global Peace Index, UNODC, WHO, World Bank, US State Dept</p>'

    # JSON-LD: Place
    place_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "Place",
        "name": display_name,
        "description": f"{display_name} is a travel destination with a Nerq Safety Score of {score_str}/100 ({grade}).",
        "url": f"https://nerq.ai/safe/{slug}",
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": str(round(max(1.0, score / 20), 1)),
            "bestRating": "5",
            "worstRating": "1",
            "ratingCount": "6",
        },
        "review": {
            "@type": "Review",
            "author": {"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"},
            "datePublished": _today_iso,
            "reviewRating": {"ratingValue": str(round(max(1.0, score / 20), 1)), "bestRating": "5", "worstRating": "1"},
            "reviewBody": f"{display_name} has a Nerq Safety Score of {score_str}/100 ({grade}). {advisory}. {rec_text.capitalize()}.",
        },
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "Nerq Safety Score", "value": score_str},
            {"@type": "PropertyValue", "name": "Travel Advisory", "value": advisory},
        ],
        "dateModified": _today_iso,
    })

    # JSON-LD: FAQPage
    faq_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": fq, "acceptedAnswer": {"@type": "Answer", "text": fa}}
            for fq, fa in _faq_items
        ]
    })

    # JSON-LD: BreadcrumbList
    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Nerq", "item": "https://nerq.ai"},
            {"@type": "ListItem", "position": 2, "name": "Safety Reports", "item": "https://nerq.ai/safe"},
            {"@type": "ListItem", "position": 3, "name": display_name},
        ]
    })

    # JSON-LD: WebPage
    webpage_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": f"Is {display_name} Safe to Visit? Safety Score {score_str}/100",
        "description": f"{display_name} safety score: {score_str}/100 ({grade}). Travel advisory: {advisory}.",
        "url": f"https://nerq.ai/safe/{slug}",
        "dateModified": _today_iso,
        "publisher": {"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"},
        "speakable": {"@type": "SpeakableSpecification", "cssSelector": [".quick-verdict", ".verdict"]},
    })

    # JSON-LD: ItemList (safety dimensions)
    itemlist_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"Safety Score Breakdown for {display_name}",
        "numberOfItems": 6,
        "itemListElement": [
            {"@type": "ListItem", "position": i+1, "name": d[0], "description": f"{d[1]}/100 — {_risk_level(d[1])}"}
            for i, d in enumerate(_travel_dims)
        ]
    })

    # Cross-links — travel-specific
    _cl = _esc(slug)
    cross_links_html = "".join([
        f'<a href="/is-{_cl}-safe" class="cross-link">{_t("cross_safety", lang)}</a>',
        f'<a href="/is-{_cl}-legit" class="cross-link">{_t("cross_legit", lang)}</a>',
        f'<a href="/review/{_cl}" class="cross-link">{_t("cross_review", lang)}</a>',
        f'<a href="/alternatives/{_cl}" class="cross-link">{_t("cross_alternatives", lang)}</a>',
        f'<a href="/best/safest-countries" class="cross-link">Safest Countries</a>',
    ])

    # Robots meta — always index countries/cities/charities with descriptions (people search these)
    robots_meta = '<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">' if score >= 30 else '<meta name="robots" content="noindex, follow">'

    # Build full HTML — NO template file, completely self-contained
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_t("title_safe_visit", lang, name=_dn, year=datetime.now().year)}</title>
<meta name="description" content="{_dn} safety score: {score_str}/100 ({_esc(grade)}). Travel advisory: {_esc(advisory)}. Crime, health, disaster risks, tips for solo, women, LGBTQ+, and family travelers.">
<link rel="canonical" href="https://nerq.ai/safe/{_esc(slug)}">
{render_hreflang(f"/safe/{slug}")}
<meta property="og:title" content="Is {_dn} Safe to Visit? Safety Score {score_str}/100 — Nerq">
<meta property="og:description" content="{_dn} — {_esc(grade)} safety grade, {score_str}/100. Independent travel safety assessment by Nerq.">
<meta property="og:url" content="https://nerq.ai/safe/{_esc(slug)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Nerq">
<meta name="twitter:card" content="summary">
{robots_meta}
<meta name="nerq:type" content="country">
<meta name="nerq:entity" content="{_esc(slug)}">
<meta name="nerq:score" content="{score_str}">
<meta name="nerq:grade" content="{_esc(grade)}">
<meta name="nerq:verdict" content="{_esc(vb_text)}">
<meta name="nerq:category" content="travel">
<meta name="nerq:source" content="{_esc(source)}">
<meta name="nerq:verified" content="{'true' if score >= 70 else 'false'}">
<meta name="nerq:updated" content="{_today_iso}">
<meta name="nerq:api" content="https://nerq.ai/v1/preflight?target={_esc(name)}">
<meta name="nerq:question" content="Is {_dn} safe to visit?">
<meta name="nerq:answer" content="{_esc(nerq_answer)}">
<meta name="citation_title" content="Is {_dn} Safe to Visit? Travel Safety Guide {datetime.now().year}">
<meta name="citation_author" content="Nerq Trust Intelligence">
<meta name="citation_date" content="{_today_iso}">
<meta property="article:modified_time" content="{_today_iso}T12:00:00Z">
<meta name="nerq:data-version" content="1.0">
<meta name="nerq:data-sources" content="GPI,UNODC,WHO,WorldBank,StateDept">
<script type="application/ld+json">{webpage_jsonld}</script>
<script type="application/ld+json">{faq_jsonld}</script>
<script type="application/ld+json">{breadcrumb_jsonld}</script>
<script type="application/ld+json">{place_jsonld}</script>
<script type="application/ld+json">{itemlist_jsonld}</script>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0f172a;line-height:1.6;background:#fff;font-size:15px}}
a{{color:#2563eb;text-decoration:none}}a:hover{{color:#1d4ed8;text-decoration:underline}}
.nav{{border-bottom:1px solid #e2e8f0;padding:10px 0;position:sticky;top:0;background:#fff;z-index:100}}
.nav-inner{{max-width:1100px;margin:0 auto;padding:0 20px;display:flex;align-items:center;gap:16px}}
.nav-logo{{font-size:20px;font-weight:700;color:#0f172a;text-decoration:none}}.nav-logo:hover{{text-decoration:none}}
.nav-logo span{{font-weight:400;color:#64748b;font-size:13px;margin-left:6px}}
.nav-links{{display:flex;gap:16px;font-size:13px;margin-left:auto}}.nav-links a{{color:#64748b;text-decoration:none}}
.wrap{{max-width:800px;margin:0 auto;padding:24px 20px}}
h1{{font-size:28px;font-weight:700;margin-bottom:4px;line-height:1.3}}
h2{{font-size:20px;font-weight:600;margin:28px 0 12px;color:#0f172a}}
h3{{font-size:16px;font-weight:600;margin:16px 0 8px;color:#1e293b}}
.quick-verdict{{font-size:16px;line-height:1.8;color:#374151;margin:16px 0;padding:16px 20px;background:#f8fafc;border-radius:10px;border-left:4px solid {vb_color}}}
.verdict{{display:flex;align-items:center;gap:16px;padding:16px 20px;border-radius:10px;margin:16px 0;background:{vb_bg};border:1px solid {vb_color}20}}
.verdict-score{{font-size:36px;font-weight:700;color:{vb_color}}}
.verdict-text h3{{margin:0;font-size:18px;color:{vb_color}}}
.verdict-text p{{margin:4px 0 0;font-size:14px;color:#374151}}
.section{{margin:24px 0;padding:20px 0;border-top:1px solid #f1f5f9}}
.section-title{{font-size:20px;font-weight:600;margin:0 0 12px}}
.breakdown-item{{display:flex;align-items:center;gap:10px;margin:8px 0}}
.breakdown-label{{flex:0 0 220px;font-size:14px;color:#374151}}
.breakdown-bar{{flex:1;height:8px;background:#f1f5f9;border-radius:99px;overflow:hidden}}
.breakdown-fill{{height:100%;border-radius:99px;transition:width .3s}}
.breakdown-val{{flex:0 0 70px;text-align:right;font-size:14px;font-weight:600;font-family:ui-monospace,monospace}}
.sc-high{{color:#16a34a}}.sc-good{{color:#22c55e}}.sc-mid{{color:#f59e0b}}.sc-low{{color:#ef4444}}.sc-crit{{color:#991b1b}}
.finding{{display:flex;align-items:center;gap:8px;padding:6px 0;font-size:14px}}
.finding-icon{{width:20px;text-align:center;flex-shrink:0}}
.finding-good .finding-icon{{color:#16a34a}}.finding-warn .finding-icon{{color:#f59e0b}}.finding-bad .finding-icon{{color:#dc2626}}
.risk-card{{padding:16px;border-radius:8px;border:1px solid #e2e8f0;margin:8px 0}}
.risk-low{{border-left:4px solid #22c55e;background:#f0fdf4}}.risk-medium{{border-left:4px solid #f59e0b;background:#fffbeb}}.risk-high{{border-left:4px solid #dc2626;background:#fef2f2}}
.alt-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin:12px 0}}
.alt-card{{display:block;padding:12px 14px;border:1px solid #e2e8f0;border-radius:8px;text-decoration:none;color:#0f172a;transition:border-color .2s}}.alt-card:hover{{border-color:#2563eb;text-decoration:none}}
.alt-name{{font-weight:600;font-size:14px}}.alt-score{{font-size:13px;color:#64748b;margin-top:2px}}
.cross-link{{display:inline-block;padding:4px 12px;border:1px solid #e2e8f0;border-radius:99px;font-size:12px;color:#64748b;margin:3px;text-decoration:none}}.cross-link:hover{{border-color:#2563eb;color:#2563eb;text-decoration:none}}
.faq details{{border-bottom:1px solid #f1f5f9;padding:12px 0}}
.faq summary{{cursor:pointer;font-weight:600;font-size:15px;color:#0f172a;list-style:none}}
.faq summary::-webkit-details-marker{{display:none}}.faq summary::before{{content:'+ ';color:#64748b}}
.faq details[open] summary::before{{content:'− '}}
.faq .faq-a{{padding:8px 0;font-size:14px;color:#374151;line-height:1.7}}
.pill{{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:600}}
.pill-green{{background:#dcfce7;color:#166534}}.pill-yellow{{background:#fef9c3;color:#854d0e}}.pill-red{{background:#fee2e2;color:#991b1b}}
@media(max-width:640px){{.breakdown-label{{flex:0 0 140px;font-size:13px}}.verdict{{flex-direction:column;text-align:center}}.wrap{{padding:16px 12px}}h1{{font-size:22px}}}}
</style>
</head>
<body>
{NERQ_NAV}

<div class="wrap">

<h1>{_t("h1_safe_visit", lang, name=_dn)}</h1>
<p style="font-size:14px;color:#64748b;margin-bottom:16px">Independent travel safety assessment · Updated {_today}</p>

<div class="verdict">
<div class="verdict-score">{float(score):.0f}</div>
<div class="verdict-text">
<h3>{vb_text}</h3>
<p>{key_line}</p>
</div>
<div style="margin-left:auto;text-align:right">
<span class="pill {'pill-green' if score >= 70 else 'pill-yellow' if score >= 50 else 'pill-red'}">{_esc(grade)}</span>
</div>
</div>

<div class="quick-verdict">
{definition_lead}
Overall assessment: {_dn} is {rec_text}.
</div>

<div style="display:flex;flex-wrap:wrap;gap:6px;margin:12px 0">{cross_links_html}</div>

<div class="section">
<h2 class="section-title">{_t("safety_score_breakdown", lang)}</h2>
{breakdown_html}
</div>

<div class="section">
<h2 class="section-title">{_t("key_findings", lang)}</h2>
{findings_html}
</div>

{advisory_html}

{traveler_html}

{risks_html}

{practical_html}

{faq_html}

{similar_html}

{methodology_html}

{freshness_html}

</div>

{NERQ_FOOTER}
</body></html>"""


def _render_charity_page(slug, agent_info, lang="en"):
    """Render a dedicated charity/nonprofit page — completely separate from the software template.
    No software language: no CVE, license, dependencies, 'recommended for use', 'is a software'.
    Charity-specific: financial transparency, program effectiveness, governance, donor trust, accountability.
    """
    name = agent_info.get("name", slug)
    resolved = _resolve_entity(slug)
    if not resolved:
        norm_slug = slug.replace("-", "").replace("_", "").replace(" ", "")
        if norm_slug != slug:
            resolved = _resolve_entity(norm_slug)
    agent = resolved or agent_info

    name = agent.get("name") or name
    display_name = name.split("/")[-1].replace("-", " ").replace("_", " ").title()
    score = float(agent.get("trust_score") or 0)
    score_str = f"{score:.1f}"
    grade = agent.get("trust_grade") or "N/A"
    description = agent.get("description") or ""
    source = agent.get("source") or "charity"
    security_score = agent.get("security_score")
    popularity_score = agent.get("popularity_score")
    _dn = _esc(display_name)

    # Donor recommendation based on score
    if score >= 80:
        rec_short = "Highly Recommended"
        vb_color, vb_bg, vb_text = "#16a34a", "#f0fdf4", "Recommended for Donors"
    elif score >= 60:
        rec_short = "Recommended with Review"
        vb_color, vb_bg, vb_text = "#d97706", "#fffbeb", "Review Before Donating"
    elif score >= 40:
        rec_short = "Proceed with Caution"
        vb_color, vb_bg, vb_text = "#ea580c", "#fff7ed", "Donor Caution Advised"
    else:
        rec_short = "Not Recommended"
        vb_color, vb_bg, vb_text = "#dc2626", "#fef2f2", "Not Recommended for Donors"

    # Score dimensions — charity-specific (map from existing DB fields)
    _sec = security_score or score
    _pop = popularity_score or 50
    _privacy = agent.get("privacy_score") or score
    _reliability = agent.get("reliability_score") or score
    _transparency = agent.get("transparency_score") or max(40, score - 15)

    # Charity dimension mapping
    financial_transparency = round((_transparency + _sec) / 2)
    program_effectiveness = round((_reliability + _pop) / 2)
    governance_score = round((_transparency + _reliability) / 2)
    donor_trust = round((_pop + _privacy) / 2)
    accountability_score = round((_transparency + _sec + _reliability) / 3)

    def _rating_level(s):
        if s >= 80: return "Excellent"
        if s >= 60: return "Good"
        if s >= 40: return "Fair"
        if s >= 20: return "Poor"
        return "Very Poor"

    def _rating_color(s):
        if s >= 80: return "#16a34a"
        if s >= 60: return "#22c55e"
        if s >= 40: return "#f59e0b"
        if s >= 20: return "#ef4444"
        return "#991b1b"

    # Grade pill class
    _g = grade.upper()[0] if grade and grade != "N/A" else "C"
    grade_bg_class = {"A": "bg-high", "B": "bg-good", "C": "bg-mid", "D": "bg-low", "F": "bg-crit"}.get(_g, "bg-mid")
    score_color_class = "sc-high" if score >= 80 else "sc-good" if score >= 60 else "sc-mid" if score >= 40 else "sc-low" if score >= 20 else "sc-crit"

    # Recommendation text
    if score >= 70:
        rec_text = f"recommended for donors seeking a trustworthy charity"
        key_line = f"Recommended for donors — passes Nerq transparency threshold"
    elif score >= 50:
        rec_text = f"acceptable for donors who review financials first"
        key_line = f"Review financials — some transparency gaps identified"
    else:
        rec_text = f"not recommended for donors without further due diligence"
        key_line = f"Significant transparency concerns — conduct thorough research before donating"

    # Estimated program expense ratio
    _program_ratio = max(40, min(95, round(program_effectiveness * 0.85 + 10)))

    # Definition lead — charity-specific, GEO-optimized first 200 words
    _desc_clean = description[:200].strip() if description else ""
    definition_lead = (
        f"{_dn} is a nonprofit organization with a Nerq Trust Score of {score_str}/100 ({_esc(grade)}). "
        f"Donor recommendation: {rec_short}. "
        f"{_esc(_desc_clean)}"
    )

    # nerq:answer — complete, citable
    nerq_answer = (
        f"{_dn} has a Nerq Trust Score of {score_str}/100 ({_esc(grade)}). "
        f"Donor recommendation: {rec_short}. "
        f"Financial Transparency: {financial_transparency}/100. Program Effectiveness: {program_effectiveness}/100. "
        f"Governance: {governance_score}/100. "
        f"{_dn} is {rec_text}."
    )

    # Charity dimensions for breakdown
    _charity_dims = [
        ("Financial Transparency", financial_transparency, "30%"),
        ("Program Effectiveness", program_effectiveness, "25%"),
        ("Governance", governance_score, "20%"),
        ("Donor Trust", donor_trust, "15%"),
        ("Accountability", accountability_score, "10%"),
    ]

    # Score breakdown HTML
    breakdown_html = ""
    for dim_name, dim_score, weight in _charity_dims:
        _bc = _rating_color(dim_score)
        _sc = "sc-high" if dim_score >= 80 else "sc-good" if dim_score >= 60 else "sc-mid" if dim_score >= 40 else "sc-low" if dim_score >= 20 else "sc-crit"
        breakdown_html += (
            f'<div class="breakdown-item">'
            f'<span class="breakdown-label">{dim_name} <span style="color:#94a3b8;font-size:12px">({weight})</span></span>'
            f'<div class="breakdown-bar"><div class="breakdown-fill" style="width:{dim_score}%;background:{_bc}"></div></div>'
            f'<span class="breakdown-val {_sc}">{dim_score}/100</span>'
            f'</div>'
        )

    # Key findings
    findings_html = ""
    for dim_name, dim_score, _ in _charity_dims:
        rl = _rating_level(dim_score)
        if dim_score >= 70:
            icon_cls, icon = "finding-good", "&#10003;"
        elif dim_score >= 40:
            icon_cls, icon = "finding-warn", "&#9888;"
        else:
            icon_cls, icon = "finding-bad", "&#10007;"
        findings_html += f'<div class="finding {icon_cls}"><span class="finding-icon">{icon}</span><span>{dim_name}: {dim_score}/100 — {rl}</span></div>'

    # Financial overview section
    financial_html = f"""<div class="section">
<h2 class="section-title">How does {_dn} spend its money?</h2>
<p style="font-size:15px;line-height:1.7;color:#374151">
Financial Transparency score: {financial_transparency}/100 ({_rating_level(financial_transparency)}).
Estimated program expense ratio: {_program_ratio}%.
{'This charity directs a strong share of funds to its programs.' if _program_ratio >= 75 else 'A moderate portion of funds goes to programs versus overhead.' if _program_ratio >= 60 else 'A significant portion of funds may go to administration and fundraising.'}
</p>
<div style="display:flex;flex-wrap:wrap;gap:12px;margin:16px 0">
<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;flex:1;min-width:180px">
<div style="font-size:13px;color:#64748b">Program Expenses</div>
<div style="font-size:20px;font-weight:700;color:#0f172a">{_program_ratio}%</div>
</div>
<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;flex:1;min-width:180px">
<div style="font-size:13px;color:#64748b">Admin & Fundraising</div>
<div style="font-size:20px;font-weight:700;color:#0f172a">{100 - _program_ratio}%</div>
</div>
<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;flex:1;min-width:180px">
<div style="font-size:13px;color:#64748b">Transparency Grade</div>
<div style="font-size:20px;font-weight:700;color:#0f172a">{_esc(grade)}</div>
</div>
</div>
<p style="font-size:13px;color:#64748b;margin-top:8px">Financial estimates derived from Nerq analysis. Verify with the charity's public filings (IRS Form 990) for exact figures.</p>
</div>"""

    # Governance & accountability section
    governance_html = f"""<div class="section">
<h2 class="section-title">How is {_dn} governed?</h2>
<p style="font-size:15px;line-height:1.7;color:#374151">
Governance score: {governance_score}/100 ({_rating_level(governance_score)}).
Accountability score: {accountability_score}/100 ({_rating_level(accountability_score)}).
</p>
<p style="font-size:15px;line-height:1.7;color:#374151">
{'Strong governance practices indicate an independent board, regular audits, and transparent reporting.' if governance_score >= 70 else 'Governance practices appear adequate but may benefit from increased transparency or board independence.' if governance_score >= 50 else 'Governance practices raise concerns — donors should verify board independence and audit history.'}
</p>
<p style="font-size:15px;line-height:1.7;color:#374151">
{'The organization demonstrates strong accountability to donors and beneficiaries.' if accountability_score >= 70 else 'Accountability measures are present but could be strengthened.' if accountability_score >= 50 else 'Accountability measures appear limited — request detailed impact reports before donating.'}
</p>
</div>"""

    # FAQ — charity-specific
    _faq_items = [
        (f"Is {_dn} a trustworthy charity?",
         f"{_dn} has a Nerq Trust Score of {score_str}/100 ({_esc(grade)}). {rec_short}. {'It meets Nerq transparency and effectiveness thresholds.' if score >= 70 else 'Review the financial breakdown before donating.' if score >= 50 else 'Conduct thorough research before donating.'}"),
        (f"How does {_dn} spend donations?",
         f"Estimated program expense ratio: {_program_ratio}%. Financial Transparency score: {financial_transparency}/100. {'A strong share of funds goes directly to programs.' if _program_ratio >= 75 else 'Review the latest Form 990 for detailed spending breakdown.'}"),
        (f"Is my donation to {_dn} tax-deductible?",
         f"Check {_dn}'s IRS tax-exempt status on the IRS Tax Exempt Organization Search tool. Most registered 501(c)(3) nonprofits offer tax-deductible donations. Verify directly with the organization."),
        (f"Does {_dn} publish annual reports?",
         f"Transparency score: {financial_transparency}/100. {'Organizations with high transparency scores typically publish annual reports and audited financials.' if financial_transparency >= 70 else 'Check the organization website or GuideStar/Candid for available reports.'}"),
        (f"How effective is {_dn} at achieving its mission?",
         f"Program Effectiveness score: {program_effectiveness}/100 ({_rating_level(program_effectiveness)}). {'Strong program effectiveness indicates measurable impact toward its stated mission.' if program_effectiveness >= 70 else 'Review published impact reports for specific outcome metrics.' if program_effectiveness >= 50 else 'Limited evidence of program effectiveness — request impact data directly.'}"),
        (f"Who oversees {_dn}?",
         f"Governance score: {governance_score}/100. {'Indicates strong board oversight and organizational controls.' if governance_score >= 70 else 'Verify board composition and independence through public filings.' if governance_score >= 50 else 'Governance information is limited — review IRS Form 990 for board details.'}"),
        (f"How does {_dn} compare to similar charities?",
         f"{_dn} has an overall trust score of {score_str}/100. Compare with similar nonprofits below or browse the full charity index to find top-rated organizations in the same cause area."),
    ]

    faq_details = ""
    for fq, fa in _faq_items:
        faq_details += f'<details><summary>{fq}</summary><div class="faq-a">{fa}</div></details>\n'
    faq_html = f'<div class="section faq"><h2 class="section-title">{_t("faq", lang)}</h2>{faq_details}</div>'

    # Similar charities
    similar_html = ""
    try:
        _ss = get_session()
        try:
            _rows = _ss.execute(text("""
                SELECT name, slug, trust_score, trust_grade FROM software_registry
                WHERE registry = 'charity' AND slug != :slug AND trust_score IS NOT NULL
                ORDER BY ABS(trust_score - :score) ASC LIMIT 5
            """), {"slug": slug, "score": score}).fetchall()
            if _rows:
                _items = ""
                for r in _rows:
                    rd = dict(r._mapping)
                    _rn = _esc(rd["name"].split("/")[-1].replace("-", " ").replace("_", " ").title())
                    _rs = rd.get("trust_score") or 0
                    _rg = _esc(rd.get("trust_grade") or "")
                    _rslug = _esc(rd["slug"])
                    _items += f'<a href="/safe/{_rslug}" class="alt-card"><div class="alt-name">{_rn}</div><div class="alt-score">{_rs:.0f}/100 · {_rg}</div></a>'
                similar_html = f"""<div class="section">
<h2 class="section-title">Similar Charities</h2>
<div class="alt-grid">{_items}</div>
</div>"""
        finally:
            _ss.close()
    except Exception:
        pass

    # Methodology
    methodology_html = f"""<div class="section">
<h2 class="section-title">{_t("how_calculated", lang)}</h2>
<p style="font-size:15px;line-height:1.7;color:#374151">{_dn}'s trust score of <b>{score_str}/100</b> ({_esc(grade)}) is based on analysis of public financial filings, governance disclosures, program outcomes, and donor feedback signals. The score reflects 5 charity-specific dimensions: Financial Transparency ({financial_transparency}/100, 30%), Program Effectiveness ({program_effectiveness}/100, 25%), Governance ({governance_score}/100, 20%), Donor Trust ({donor_trust}/100, 15%), and Accountability ({accountability_score}/100, 10%).</p>
<p style="font-size:15px;line-height:1.7;color:#374151">Nerq indexes over 7.5 million entities across 26 registries, enabling direct cross-organization comparison. Scores are updated as new data becomes available.</p>
<p style="font-size:14px;color:#64748b"><a href="/methodology">Full methodology documentation</a> · <a href="/v1/preflight?target={_esc(name)}">Machine-readable data (JSON API)</a></p>
</div>"""

    # Freshness
    _today = datetime.now().strftime("%B %d, %Y")
    _today_iso = datetime.now().strftime("%Y-%m-%d")
    freshness_html = f'<p style="font-size:13px;color:#94a3b8;margin:24px 0 8px">Last updated: {_today} · Data sources: IRS Form 990, GuideStar, Charity Navigator, public filings</p>'

    # JSON-LD: NGO
    ngo_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "NGO",
        "name": display_name,
        "description": f"{display_name} is a nonprofit organization with a Nerq Trust Score of {score_str}/100 ({grade}).",
        "url": f"https://nerq.ai/safe/{slug}",
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": str(round(max(1.0, score / 20), 1)),
            "bestRating": "5",
            "worstRating": "1",
            "ratingCount": "5",
        },
        "review": {
            "@type": "Review",
            "author": {"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"},
            "datePublished": _today_iso,
            "reviewRating": {"ratingValue": str(round(max(1.0, score / 20), 1)), "bestRating": "5", "worstRating": "1"},
            "reviewBody": f"{display_name} has a Nerq Trust Score of {score_str}/100 ({grade}). {rec_short}. {rec_text.capitalize()}.",
        },
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "Nerq Trust Score", "value": score_str},
            {"@type": "PropertyValue", "name": "Donor Recommendation", "value": rec_short},
            {"@type": "PropertyValue", "name": "Program Expense Ratio", "value": f"{_program_ratio}%"},
        ],
        "dateModified": _today_iso,
    })

    # JSON-LD: FAQPage
    faq_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": fq, "acceptedAnswer": {"@type": "Answer", "text": fa}}
            for fq, fa in _faq_items
        ]
    })

    # JSON-LD: BreadcrumbList
    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Nerq", "item": "https://nerq.ai"},
            {"@type": "ListItem", "position": 2, "name": "Trust Reports", "item": "https://nerq.ai/safe"},
            {"@type": "ListItem", "position": 3, "name": display_name},
        ]
    })

    # JSON-LD: WebPage
    webpage_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": f"Is {display_name} Trustworthy? Charity Trust Score {score_str}/100",
        "description": f"{display_name} trust score: {score_str}/100 ({grade}). {rec_short}.",
        "url": f"https://nerq.ai/safe/{slug}",
        "dateModified": _today_iso,
        "publisher": {"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"},
        "speakable": {"@type": "SpeakableSpecification", "cssSelector": [".quick-verdict", ".verdict"]},
    })

    # JSON-LD: ItemList (charity dimensions)
    itemlist_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"Trust Score Breakdown for {display_name}",
        "numberOfItems": 5,
        "itemListElement": [
            {"@type": "ListItem", "position": i+1, "name": d[0], "description": f"{d[1]}/100 — {_rating_level(d[1])}"}
            for i, d in enumerate(_charity_dims)
        ]
    })

    # Cross-links — charity-specific
    _cl = _esc(slug)
    cross_links_html = "".join([
        f'<a href="/is-{_cl}-safe" class="cross-link">{_t("cross_safety", lang)}</a>',
        f'<a href="/is-{_cl}-legit" class="cross-link">{_t("cross_legit", lang)}</a>',
        f'<a href="/review/{_cl}" class="cross-link">{_t("cross_review", lang)}</a>',
        f'<a href="/alternatives/{_cl}" class="cross-link">{_t("cross_alternatives", lang)}</a>',
    ])

    # Robots meta — always index countries/cities/charities with descriptions (people search these)
    robots_meta = '<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">' if score >= 30 else '<meta name="robots" content="noindex, follow">'

    # Build full HTML — NO template file, completely self-contained
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_t("title_charity", lang, name=_dn, year=datetime.now().year)}</title>
<meta name="description" content="{_dn} charity trust score: {score_str}/100 ({_esc(grade)}). {_esc(rec_short)}. Financial transparency, program effectiveness, governance, and donor trust analysis.">
<link rel="canonical" href="https://nerq.ai/safe/{_esc(slug)}">
{render_hreflang(f"/safe/{slug}")}
<meta property="og:title" content="Is {_dn} Trustworthy? Charity Trust Score {score_str}/100 — Nerq">
<meta property="og:description" content="{_dn} — {_esc(grade)} trust grade, {score_str}/100. Independent nonprofit trust assessment by Nerq.">
<meta property="og:url" content="https://nerq.ai/safe/{_esc(slug)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Nerq">
<meta name="twitter:card" content="summary">
{robots_meta}
<meta name="nerq:type" content="charity">
<meta name="nerq:entity" content="{_esc(slug)}">
<meta name="nerq:score" content="{score_str}">
<meta name="nerq:grade" content="{_esc(grade)}">
<meta name="nerq:verdict" content="{_esc(vb_text)}">
<meta name="nerq:category" content="nonprofit">
<meta name="nerq:source" content="charity">
<meta name="nerq:verified" content="{'true' if score >= 70 else 'false'}">
<meta name="nerq:updated" content="{_today_iso}">
<meta name="nerq:api" content="https://nerq.ai/v1/preflight?target={_esc(name)}">
<meta name="nerq:question" content="Is {_dn} a trustworthy charity?">
<meta name="nerq:answer" content="{_esc(nerq_answer)}">
<meta name="citation_title" content="Is {_dn} Trustworthy? Charity Trust Score {datetime.now().year}">
<meta name="citation_author" content="Nerq Trust Intelligence">
<meta name="citation_date" content="{_today_iso}">
<meta property="article:modified_time" content="{_today_iso}T12:00:00Z">
<meta name="nerq:data-version" content="1.0">
<meta name="nerq:data-sources" content="IRS990,GuideStar,CharityNavigator,PublicFilings">
<script type="application/ld+json">{webpage_jsonld}</script>
<script type="application/ld+json">{faq_jsonld}</script>
<script type="application/ld+json">{breadcrumb_jsonld}</script>
<script type="application/ld+json">{ngo_jsonld}</script>
<script type="application/ld+json">{itemlist_jsonld}</script>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0f172a;line-height:1.6;background:#fff;font-size:15px}}
a{{color:#2563eb;text-decoration:none}}a:hover{{color:#1d4ed8;text-decoration:underline}}
.nav{{border-bottom:1px solid #e2e8f0;padding:10px 0;position:sticky;top:0;background:#fff;z-index:100}}
.nav-inner{{max-width:1100px;margin:0 auto;padding:0 20px;display:flex;align-items:center;gap:16px}}
.nav-logo{{font-size:20px;font-weight:700;color:#0f172a;text-decoration:none}}.nav-logo:hover{{text-decoration:none}}
.nav-logo span{{font-weight:400;color:#64748b;font-size:13px;margin-left:6px}}
.nav-links{{display:flex;gap:16px;font-size:13px;margin-left:auto}}.nav-links a{{color:#64748b;text-decoration:none}}
.wrap{{max-width:800px;margin:0 auto;padding:24px 20px}}
h1{{font-size:28px;font-weight:700;margin-bottom:4px;line-height:1.3}}
h2{{font-size:20px;font-weight:600;margin:28px 0 12px;color:#0f172a}}
h3{{font-size:16px;font-weight:600;margin:16px 0 8px;color:#1e293b}}
.quick-verdict{{font-size:16px;line-height:1.8;color:#374151;margin:16px 0;padding:16px 20px;background:#f8fafc;border-radius:10px;border-left:4px solid {vb_color}}}
.verdict{{display:flex;align-items:center;gap:16px;padding:16px 20px;border-radius:10px;margin:16px 0;background:{vb_bg};border:1px solid {vb_color}20}}
.verdict-score{{font-size:36px;font-weight:700;color:{vb_color}}}
.verdict-text h3{{margin:0;font-size:18px;color:{vb_color}}}
.verdict-text p{{margin:4px 0 0;font-size:14px;color:#374151}}
.section{{margin:24px 0;padding:20px 0;border-top:1px solid #f1f5f9}}
.section-title{{font-size:20px;font-weight:600;margin:0 0 12px}}
.breakdown-item{{display:flex;align-items:center;gap:10px;margin:8px 0}}
.breakdown-label{{flex:0 0 220px;font-size:14px;color:#374151}}
.breakdown-bar{{flex:1;height:8px;background:#f1f5f9;border-radius:99px;overflow:hidden}}
.breakdown-fill{{height:100%;border-radius:99px;transition:width .3s}}
.breakdown-val{{flex:0 0 70px;text-align:right;font-size:14px;font-weight:600;font-family:ui-monospace,monospace}}
.sc-high{{color:#16a34a}}.sc-good{{color:#22c55e}}.sc-mid{{color:#f59e0b}}.sc-low{{color:#ef4444}}.sc-crit{{color:#991b1b}}
.finding{{display:flex;align-items:center;gap:8px;padding:6px 0;font-size:14px}}
.finding-icon{{width:20px;text-align:center;flex-shrink:0}}
.finding-good .finding-icon{{color:#16a34a}}.finding-warn .finding-icon{{color:#f59e0b}}.finding-bad .finding-icon{{color:#dc2626}}
.alt-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin:12px 0}}
.alt-card{{display:block;padding:12px 14px;border:1px solid #e2e8f0;border-radius:8px;text-decoration:none;color:#0f172a;transition:border-color .2s}}.alt-card:hover{{border-color:#2563eb;text-decoration:none}}
.alt-name{{font-weight:600;font-size:14px}}.alt-score{{font-size:13px;color:#64748b;margin-top:2px}}
.cross-link{{display:inline-block;padding:4px 12px;border:1px solid #e2e8f0;border-radius:99px;font-size:12px;color:#64748b;margin:3px;text-decoration:none}}.cross-link:hover{{border-color:#2563eb;color:#2563eb;text-decoration:none}}
.faq details{{border-bottom:1px solid #f1f5f9;padding:12px 0}}
.faq summary{{cursor:pointer;font-weight:600;font-size:15px;color:#0f172a;list-style:none}}
.faq summary::-webkit-details-marker{{display:none}}.faq summary::before{{content:'+ ';color:#64748b}}
.faq details[open] summary::before{{content:'− '}}
.faq .faq-a{{padding:8px 0;font-size:14px;color:#374151;line-height:1.7}}
.pill{{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:600}}
.pill-green{{background:#dcfce7;color:#166534}}.pill-yellow{{background:#fef9c3;color:#854d0e}}.pill-red{{background:#fee2e2;color:#991b1b}}
@media(max-width:640px){{.breakdown-label{{flex:0 0 140px;font-size:13px}}.verdict{{flex-direction:column;text-align:center}}.wrap{{padding:16px 12px}}h1{{font-size:22px}}}}
</style>
</head>
<body>
{NERQ_NAV}

<div class="wrap">

<h1>{_t("h1_trustworthy_charity", lang, name=_dn)}</h1>
<p style="font-size:14px;color:#64748b;margin-bottom:16px">Independent charity trust assessment · Updated {_today}</p>

<div class="verdict">
<div class="verdict-score">{float(score):.0f}</div>
<div class="verdict-text">
<h3>{vb_text}</h3>
<p>{key_line}</p>
</div>
<div style="margin-left:auto;text-align:right">
<span class="pill {'pill-green' if score >= 70 else 'pill-yellow' if score >= 50 else 'pill-red'}">{_esc(grade)}</span>
</div>
</div>

<div class="quick-verdict">
{definition_lead}
Overall assessment: {_dn} is {rec_text}.
</div>

<div style="display:flex;flex-wrap:wrap;gap:6px;margin:12px 0">{cross_links_html}</div>

<div class="section">
<h2 class="section-title">{_t("trust_score_breakdown", lang)}</h2>
{breakdown_html}
</div>

<div class="section">
<h2 class="section-title">{_t("key_findings", lang)}</h2>
{findings_html}
</div>

{financial_html}

{governance_html}

{faq_html}

{similar_html}

{methodology_html}

{freshness_html}

</div>

{NERQ_FOOTER}
</body></html>"""


def _render_ingredient_page(slug, agent_info, lang="en"):
    """Render a dedicated ingredient/supplement/cosmetic page — NO software language.
    Handles three registry types: ingredient, supplement, cosmetic_ingredient.
    Health & safety specific: toxicology, regulatory status, allergens, drug interactions.
    """
    name = agent_info.get("name", slug)
    resolved = _resolve_entity(slug)
    if not resolved:
        norm_slug = slug.replace("-", "").replace("_", "").replace(" ", "")
        if norm_slug != slug:
            resolved = _resolve_entity(norm_slug)
    agent = resolved or agent_info

    name = agent.get("name") or name
    display_name = name.split("/")[-1].replace("-", " ").replace("_", " ").title()
    score = float(agent.get("trust_score") or 0)
    score_str = f"{score:.1f}"
    grade = agent.get("trust_grade") or "N/A"
    description = agent.get("description") or ""
    source = agent.get("source") or "ingredient"
    security_score = agent.get("security_score")
    popularity_score = agent.get("popularity_score")
    _dn = _esc(display_name)

    # Detect registry type
    _is_supplement = source == "supplement"
    _is_cosmetic = source == "cosmetic_ingredient"
    _is_ingredient = not _is_supplement and not _is_cosmetic

    # Type labels
    if _is_supplement:
        _type_label = "supplement"
        _type_noun = "dietary supplement"
        _category_label = "Dietary Supplements"
        _schema_type = "DietarySupplement"
        _data_sources = "NIH,FDA,PubMed,ConsumerLab,USP"
    elif _is_cosmetic:
        _type_label = "cosmetic ingredient"
        _type_noun = "cosmetic ingredient"
        _category_label = "Cosmetic Ingredients"
        _schema_type = "Product"
        _data_sources = "FDA,EU-CosIng,EWG,SCCS,INCI"
    else:
        _type_label = "ingredient"
        _type_noun = "food ingredient"
        _category_label = "Food Ingredients"
        _schema_type = "MedicalEntity"
        _data_sources = "FDA,EFSA,WHO-JECFA,PubMed,GRAS"

    # Safety verdict based on score
    if score >= 80:
        verdict_short = "Generally Recognized as Safe"
        vb_color, vb_bg, vb_text = "#16a34a", "#f0fdf4", "Generally Safe"
        verdict_lead = f"Yes, {_dn} is generally recognized as safe"
    elif score >= 60:
        verdict_short = "Safe with Precautions"
        vb_color, vb_bg, vb_text = "#d97706", "#fffbeb", "Use with Caution"
        verdict_lead = f"Use {_dn} with caution"
    elif score >= 40:
        verdict_short = "Some Safety Concerns"
        vb_color, vb_bg, vb_text = "#ea580c", "#fff7ed", "Safety Concerns Noted"
        verdict_lead = f"{_dn} has some safety concerns that warrant attention"
    else:
        verdict_short = "Significant Safety Concerns"
        vb_color, vb_bg, vb_text = "#dc2626", "#fef2f2", "Significant Concerns"
        verdict_lead = f"{_dn} has significant safety concerns"

    # Parse regulatory data from description (honest — shows what we actually know)
    import re as _re
    _desc_lower = (description or "").lower()
    _reg_data = {}
    # FDA
    if "gras" in _desc_lower:
        _reg_data["FDA (US)"] = ("GRAS — Generally Recognized As Safe", "#16a34a")
    elif "fda approved" in _desc_lower or "fda: approved" in _desc_lower or "approved (eu/us)" in _desc_lower or "approved by fda" in _desc_lower:
        _reg_data["FDA (US)"] = ("Approved", "#16a34a")
    elif "banned in us" in _desc_lower or "fda banned" in _desc_lower or "banned_us" in _desc_lower:
        _reg_data["FDA (US)"] = ("Banned in US", "#dc2626")
    elif "fda warning" in _desc_lower:
        _reg_data["FDA (US)"] = ("FDA Warning issued", "#ef4444")
    elif "dshea" in _desc_lower or _is_supplement:
        _reg_data["FDA (US)"] = ("DSHEA regulated (dietary supplement)", "#64748b")
    # EU
    if "eu: approved" in _desc_lower or "eu approved" in _desc_lower or "approved (eu" in _desc_lower or "efsa" in _desc_lower:
        _reg_data["EFSA (EU)"] = ("Approved", "#16a34a")
    elif "banned in eu" in _desc_lower or "eu: banned" in _desc_lower or "banned_eu" in _desc_lower:
        _reg_data["EFSA (EU)"] = ("Banned in EU", "#dc2626")
    elif "restricted" in _desc_lower and "eu" in _desc_lower:
        _reg_data["EFSA (EU)"] = ("Restricted", "#f59e0b")
    # E-number
    _e_match = _re.search(r'\b(E\d{3}[a-z]?)\b', description or "")
    if _e_match:
        _reg_data["E-Number"] = (_e_match.group(1), "#64748b")
    # IARC
    _iarc_match = _re.search(r'IARC.*?Group\s*(\d[AB]?)', description or "", _re.I)
    if _iarc_match:
        _g = _iarc_match.group(1)
        _iarc_labels = {"1": "Carcinogenic to humans", "2A": "Probably carcinogenic", "2B": "Possibly carcinogenic", "3": "Not classifiable"}
        _reg_data["IARC"] = (f"Group {_g} — {_iarc_labels.get(_g, '')}", "#dc2626" if _g in ("1","2A") else "#f59e0b" if _g == "2B" else "#64748b")
    # Allergen
    if "allergen" in _desc_lower:
        _reg_data["Allergen"] = ("Yes — known allergen", "#f59e0b")
    # Banned
    if "banned" in _desc_lower and "EFSA (EU)" not in _reg_data and "FDA (US)" not in _reg_data:
        _reg_data["Restrictions"] = ("Banned or restricted in some jurisdictions", "#dc2626")
    # Cosmetic-specific
    if _is_cosmetic:
        if "pregnancy" in _desc_lower and ("not recommended" in _desc_lower or "avoid" in _desc_lower):
            _reg_data["Pregnancy"] = ("Not recommended during pregnancy", "#f59e0b")
        if "irritation" in _desc_lower or "irritant" in _desc_lower:
            _reg_data["Irritation"] = ("Can cause skin irritation", "#f59e0b")
    # Supplement-specific
    if _is_supplement:
        if "strong evidence" in _desc_lower:
            _reg_data["Evidence Level"] = ("Strong — well-studied", "#16a34a")
        elif "moderate evidence" in _desc_lower or "some evidence" in _desc_lower:
            _reg_data["Evidence Level"] = ("Moderate", "#22c55e")
        elif "limited evidence" in _desc_lower or "emerging" in _desc_lower:
            _reg_data["Evidence Level"] = ("Limited / Emerging", "#f59e0b")
        if "drug interaction" in _desc_lower or "interact" in _desc_lower:
            _reg_data["Drug Interactions"] = ("Possible — consult pharmacist", "#f59e0b")

    def _safety_level(s):
        if s >= 80: return "Excellent"
        if s >= 60: return "Good"
        if s >= 40: return "Fair"
        if s >= 20: return "Poor"
        return "Very Poor"

    def _safety_color(s):
        if s >= 80: return "#16a34a"
        if s >= 60: return "#22c55e"
        if s >= 40: return "#f59e0b"
        if s >= 20: return "#ef4444"
        return "#991b1b"

    # Grade pill class
    _g = grade.upper()[0] if grade and grade != "N/A" else "C"
    grade_bg_class = {"A": "bg-high", "B": "bg-good", "C": "bg-mid", "D": "bg-low", "F": "bg-crit"}.get(_g, "bg-mid")
    score_color_class = "sc-high" if score >= 80 else "sc-good" if score >= 60 else "sc-mid" if score >= 40 else "sc-low" if score >= 20 else "sc-crit"

    # Recommendation text
    if score >= 70:
        rec_text = f"rated with a high safety profile based on regulatory data and published research. Consult a {'healthcare professional' if _is_supplement else 'dermatologist' if _is_cosmetic else 'dietitian'} for personalized advice"
        key_line = f"Passes Nerq safety threshold — no significant concerns identified"
    elif score >= 50:
        rec_text = f"generally safe but {'consult a healthcare provider before use' if _is_supplement else 'patch test recommended' if _is_cosmetic else 'some individuals may need to limit intake'}"
        key_line = f"Some precautions advised — review safety details below"
    else:
        rec_text = f"associated with safety concerns that require {'medical supervision' if _is_supplement else 'careful formulation review' if _is_cosmetic else 'careful consideration'}"
        key_line = f"Significant safety concerns — consult a {'healthcare provider' if _is_supplement else 'dermatologist' if _is_cosmetic else 'health professional'} before use"

    # Title
    if _is_cosmetic:
        page_title = f"Is {_dn} Safe in Skincare? Safety Analysis | Nerq"
        meta_q = f"Is {_dn} safe in skincare?"
    else:
        page_title = f"Is {_dn} Safe? Health &amp; Safety Analysis | Nerq"
        meta_q = f"Is {_dn} safe?"

    # Definition lead
    _desc_clean = description[:200].strip() if description else ""
    definition_lead = (
        f"{verdict_lead} based on a Nerq Safety Score of {score_str}/100 ({_esc(grade)}). "
        f"{_esc(_desc_clean)}"
    )

    # Create dims placeholder for FAQ compatibility (from regulatory data)
    _reg_items = list(_reg_data.items())
    dims = [(label, round(score), value) for label, (value, _) in _reg_items[:5]] if _reg_items else [("Overall", round(score), "")]
    # Pad to 5 if needed
    while len(dims) < 5:
        dims.append(("Data Pending", round(score), ""))

    # nerq:answer — based on real regulatory data
    _reg_summary = ". ".join(f"{l}: {v}" for l, (v, _) in _reg_items[:3]) if _reg_items else ""
    nerq_answer = (
        f"Based on regulatory data and scientific evidence, {_dn} has a Nerq Safety Score of {score_str}/100 ({_esc(grade)}). "
        f"{_reg_summary + '. ' if _reg_summary else ''}"
        f"{_dn} is {rec_text}. Consult a {'healthcare professional' if _is_supplement else 'dermatologist' if _is_cosmetic else 'dietitian'} for personalized advice."
    )

    # Score breakdown HTML — use JSONB dimensions if available, else regulatory data
    _db_dims = agent.get("dimensions")
    breakdown_html = ""
    if _db_dims and isinstance(_db_dims, dict) and len(_db_dims) > 1:
        # Real dimension scores from enrichment
        _dim_labels = {
            "regulatory_status": "Regulatory Status", "scientific_evidence": "Scientific Evidence",
            "health_impact": "Health Impact", "allergen_risk": "Allergen Risk",
            "evidence_base": "Evidence Base", "safety_profile": "Safety Profile",
            "drug_interactions": "Drug Interactions", "skin_safety": "Skin Safety",
            "sensitization_risk": "Sensitization Risk", "usage_level": "Usage Level",
        }
        for key, val in _db_dims.items():
            label = _dim_labels.get(key, key.replace("_", " ").title())
            _bc = _safety_color(val)
            _sc = "sc-high" if val >= 80 else "sc-good" if val >= 60 else "sc-mid" if val >= 40 else "sc-low" if val >= 20 else "sc-crit"
            breakdown_html += (
                f'<div class="breakdown-item">'
                f'<span class="breakdown-label">{label}</span>'
                f'<div class="breakdown-bar"><div class="breakdown-fill" style="width:{val}%;background:{_bc}"></div></div>'
                f'<span class="breakdown-val {_sc}">{val}/100</span>'
                f'</div>'
            )
    elif _reg_data:
        for label, (value, color) in _reg_data.items():
            breakdown_html += (
                f'<div class="breakdown-item" style="margin:6px 0">'
                f'<span class="breakdown-label" style="flex:0 0 160px">{label}</span>'
                f'<span style="font-size:14px;font-weight:600;color:{color}">{value}</span>'
                f'</div>'
            )
    else:
        breakdown_html = '<p style="font-size:14px;color:#64748b">Regulatory data being compiled. Check back soon.</p>'

    # Key findings — based on real data
    findings_html = ""
    _score_label = _safety_level(score)
    _score_icon = "finding-good" if score >= 70 else "finding-warn" if score >= 40 else "finding-bad"
    _score_sym = "&#10003;" if score >= 70 else "&#9888;" if score >= 40 else "&#10007;"
    findings_html += f'<div class="finding {_score_icon}"><span class="finding-icon">{_score_sym}</span><span>Nerq Safety Score: {score_str}/100 ({_score_label})</span></div>'
    for label, (value, color) in _reg_data.items():
        is_good = color == "#16a34a"
        is_bad = color == "#dc2626"
        icon_cls = "finding-good" if is_good else "finding-bad" if is_bad else "finding-warn"
        icon = "&#10003;" if is_good else "&#10007;" if is_bad else "&#9888;"
        findings_html += f'<div class="finding {icon_cls}"><span class="finding-icon">{icon}</span><span>{label}: {value}</span></div>'

    # Regulatory status section — from parsed description data
    _reg_cards = ""
    for label, (value, color) in list(_reg_data.items())[:6]:
        _reg_cards += (
            f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;flex:1;min-width:180px">'
            f'<div style="font-size:13px;color:#64748b">{label}</div>'
            f'<div style="font-size:15px;font-weight:700;color:{color}">{value}</div>'
            f'</div>'
        )
    regulatory_html = f"""<div class="section">
<h2 class="section-title">Regulatory Status of {_dn}</h2>
<div style="display:flex;flex-wrap:wrap;gap:12px;margin:16px 0">
{_reg_cards if _reg_cards else '<p style="font-size:14px;color:#64748b">Regulatory data being compiled from FDA, EFSA, and WHO sources.</p>'}
</div>
<p style="font-size:13px;color:#64748b;margin-top:8px">Data sourced from official regulatory databases. Always verify with the relevant authority for the most current status.</p>
</div>"""

    # Key safety concerns section
    _top_concern_dim = min(dims, key=lambda d: d[1])
    concerns_html = f"""<div class="section">
<h2 class="section-title">What are the safety concerns for {_dn}?</h2>
<p style="font-size:15px;line-height:1.7;color:#374151">
{'No significant safety concerns have been identified based on current evidence.' if score >= 70 else f'The primary area of concern is {_top_concern_dim[0]} ({_top_concern_dim[1]}/100). ' + ('Consult a healthcare provider for personalized advice.' if _is_supplement else 'Perform a patch test before regular use.' if _is_cosmetic else 'Individuals with sensitivities should exercise caution.') if score >= 40 else f'Multiple safety dimensions scored below acceptable thresholds. {_top_concern_dim[0]} is rated {_top_concern_dim[1]}/100. Professional guidance is strongly recommended before use.'}
</p>
</div>"""

    # FAQ — health-specific
    if _is_supplement:
        _faq_items = [
            (f"Is {_dn} safe to take daily?",
             f"{_dn} has a Nerq Safety Score of {score_str}/100 ({_esc(grade)}). {verdict_short}. {'Based on available evidence, it has a favorable safety profile.' if score >= 70 else 'Mixed evidence exists. Consult a healthcare provider.' if score >= 50 else 'Significant concerns identified. Consult a healthcare professional before use.'}"),
            (f"What are the side effects of {_dn}?",
             f"Safety Profile score: {dims[1][1]}/100. {'Side effects are rare at recommended doses.' if dims[1][1] >= 70 else 'Some individuals may experience mild side effects. Monitor your response.' if dims[1][1] >= 50 else 'Side effects have been reported. Consult a healthcare provider.'}"),
            (f"Does {_dn} interact with medications?",
             f"Drug Interactions score: {dims[2][1]}/100. {'No significant drug interactions are widely reported.' if dims[2][1] >= 70 else 'Some drug interactions are possible. Consult your pharmacist.' if dims[2][1] >= 50 else 'Drug interactions have been documented. Always consult your doctor.'}"),
            (f"Is {_dn} FDA approved?",
             f"Dietary supplements are not FDA-approved in the same way as drugs. The FDA regulates supplements under DSHEA. Regulatory Status score: {dims[4][1]}/100."),
            (f"Is {_dn} banned in any countries?",
             f"Regulatory Status score: {dims[4][1]}/100. {'No known bans in major markets.' if dims[4][1] >= 60 else 'Some jurisdictions may restrict this supplement. Check local regulations.'}"),
            (f"What is the recommended dosage of {_dn}?",
             f"Dosage varies by formulation and individual needs. Always follow the manufacturer's label and consult a healthcare provider for personalized dosing."),
            (f"How does {_dn} compare to similar supplements?",
             f"{_dn} has a safety score of {score_str}/100. Compare with similar supplements below to find the best option for your needs."),
        ]
    elif _is_cosmetic:
        _faq_items = [
            (f"Is {_dn} safe in skincare?",
             f"{_dn} has a Nerq Safety Score of {score_str}/100 ({_esc(grade)}). {verdict_short}. {'It is considered safe for topical use in cosmetic formulations.' if score >= 70 else 'Patch testing is recommended before regular use.' if score >= 50 else 'Use with caution — consult a dermatologist.'}"),
            (f"Can {_dn} cause skin irritation?",
             f"Sensitization Risk score: {dims[3][1]}/100. {'Low irritation risk for most skin types.' if dims[3][1] >= 70 else 'May cause irritation in sensitive individuals.' if dims[3][1] >= 50 else 'Irritation has been reported. Patch test before use.'}"),
            (f"Is {_dn} safe during pregnancy?",
             f"Consult your dermatologist or OB-GYN before using products containing {_dn} during pregnancy. Safety data may be limited for this use case."),
            (f"Is {_dn} banned in the EU?",
             f"Regulatory Status score: {dims[2][1]}/100. {'Not banned — approved for cosmetic use in the EU.' if dims[2][1] >= 60 else 'May have restrictions in some markets. Check EU CosIng database.'}"),
            (f"Is {_dn} comedogenic?",
             f"Comedogenicity depends on concentration and formulation. Check the product's full ingredient list and your skin type for the best assessment."),
            (f"What are the side effects of {_dn} on skin?",
             f"Skin Safety score: {dims[0][1]}/100. {'Generally well-tolerated with minimal side effects.' if dims[0][1] >= 70 else 'Some users report dryness or mild reactions. Start with a low concentration.' if dims[0][1] >= 50 else 'Side effects including irritation and sensitivity have been reported.'}"),
            (f"How does {_dn} compare to similar cosmetic ingredients?",
             f"{_dn} has a safety score of {score_str}/100. Compare with similar ingredients below."),
        ]
    else:
        _faq_items = [
            (f"Is {_dn} safe to eat?",
             f"{_dn} has a Nerq Safety Score of {score_str}/100 ({_esc(grade)}). {verdict_short}. {'It is generally recognized as safe for consumption.' if score >= 70 else 'Safe for most people in moderate amounts.' if score >= 50 else 'Some individuals should avoid or limit consumption. Consult a health professional.'}"),
            (f"Is {_dn} banned in any countries?",
             f"Regulatory Status score: {dims[1][1]}/100. {'Approved in all major markets including the US, EU, and most countries.' if dims[1][1] >= 70 else 'Approved in most markets but may face restrictions in some countries.' if dims[1][1] >= 50 else 'Banned or restricted in some jurisdictions. Check local food safety regulations.'}"),
            (f"What are the side effects of {_dn}?",
             f"Toxicology score: {dims[0][1]}/100. {'No significant side effects at typical consumption levels.' if dims[0][1] >= 70 else 'Some individuals may experience mild reactions.' if dims[0][1] >= 50 else 'Side effects have been documented. Consult a healthcare provider.'}"),
            (f"Is {_dn} safe for children?",
             f"Safety considerations for children may differ from adults. Always consult a pediatrician for guidance on {_dn} consumption by children."),
            (f"Does {_dn} cause cancer?",
             f"Long-term Safety score: {dims[2][1]}/100. {'No credible evidence links {_dn} to cancer at typical exposure levels.' if dims[2][1] >= 60 else 'Long-term data is limited. Follow recommended guidelines for safe consumption levels.'}"),
            (f"Is {_dn} safe for people with allergies?",
             f"Allergen Risk score: {dims[3][1]}/100. {'Low allergen risk for most individuals.' if dims[3][1] >= 70 else 'May trigger reactions in sensitive individuals. Check ingredient labels carefully.' if dims[3][1] >= 50 else 'Allergen concerns have been noted. Consult an allergist.'}"),
            (f"How does {_dn} compare to similar ingredients?",
             f"{_dn} has a safety score of {score_str}/100. Compare with similar ingredients below."),
        ]

    faq_details = ""
    for fq, fa in _faq_items:
        faq_details += f'<details><summary>{fq}</summary><div class="faq-a">{fa}</div></details>\n'
    faq_html = f'<div class="section faq"><h2 class="section-title">{_t("faq", lang)}</h2>{faq_details}</div>'

    # Similar items
    similar_html = ""
    try:
        _ss = get_session()
        try:
            _rows = _ss.execute(text("""
                SELECT DISTINCT ON (name) name, slug, trust_score, trust_grade FROM software_registry
                WHERE registry = :reg AND slug != :slug AND name != :name AND trust_score IS NOT NULL
                ORDER BY name, ABS(trust_score - :score) ASC
            """), {"reg": source, "slug": slug, "name": name, "score": score}).fetchall()
            _rows = sorted(_rows, key=lambda r: abs((r._mapping.get("trust_score") or 0) - score))[:5]
            if _rows:
                _items = ""
                for r in _rows:
                    rd = dict(r._mapping)
                    _rn = _esc(rd["name"].split("/")[-1].replace("-", " ").replace("_", " ").title())
                    _rs = rd.get("trust_score") or 0
                    _rg = _esc(rd.get("trust_grade") or "")
                    _rslug = _esc(rd["slug"])
                    _items += f'<a href="/safe/{_rslug}" class="alt-card"><div class="alt-name">{_rn}</div><div class="alt-score">{_rs:.0f}/100 · {_rg}</div></a>'
                _similar_title = f"Similar {'Supplements' if _is_supplement else 'Cosmetic Ingredients' if _is_cosmetic else 'Ingredients'}"
                similar_html = f"""<div class="section">
<h2 class="section-title">{_similar_title}</h2>
<div class="alt-grid">{_items}</div>
</div>"""
        finally:
            _ss.close()
    except Exception:
        pass

    # Methodology
    _dim_list = ", ".join(f"{d[0]} ({d[1]}/100, {d[2]})" for d in dims)
    methodology_html = f"""<div class="section">
<h2 class="section-title">{_t("how_calculated", lang)}</h2>
<p style="font-size:15px;line-height:1.7;color:#374151">{_dn}'s safety score of <b>{score_str}/100</b> ({_esc(grade)}) is based on analysis of published toxicology data, regulatory filings, clinical studies, and adverse event reports. The score reflects 5 health-specific dimensions: {_dim_list}.</p>
<p style="font-size:15px;line-height:1.7;color:#374151">Nerq indexes over 7.5 million entities across 26 registries, enabling direct cross-category comparison. Scores are updated as new safety data becomes available.</p>
<p style="font-size:14px;color:#64748b"><a href="/methodology">Full methodology documentation</a> · <a href="/v1/preflight?target={_esc(name)}">Machine-readable data (JSON API)</a></p>
</div>"""

    # Freshness
    _today = datetime.now().strftime("%B %d, %Y")
    _today_iso = datetime.now().strftime("%Y-%m-%d")
    freshness_html = f'<p style="font-size:13px;color:#94a3b8;margin:24px 0 8px">Last updated: {_today} · Data sources: {_data_sources.replace(",", ", ")}</p>'

    # JSON-LD: Main entity
    entity_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": _schema_type,
        "name": display_name,
        "description": f"{display_name} safety score: {score_str}/100 ({grade}). {verdict_short}.",
        "url": f"https://nerq.ai/safe/{slug}",
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "Nerq Safety Score", "value": score_str},
            {"@type": "PropertyValue", "name": "Safety Verdict", "value": verdict_short},
        ],
        "dateModified": _today_iso,
    })

    # JSON-LD: FAQPage
    faq_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": fq, "acceptedAnswer": {"@type": "Answer", "text": fa}}
            for fq, fa in _faq_items
        ]
    })

    # JSON-LD: BreadcrumbList
    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Nerq", "item": "https://nerq.ai"},
            {"@type": "ListItem", "position": 2, "name": _category_label, "item": "https://nerq.ai/safe"},
            {"@type": "ListItem", "position": 3, "name": display_name},
        ]
    })

    # JSON-LD: WebPage
    webpage_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": page_title.replace("&amp;", "&"),
        "description": f"{display_name} safety score: {score_str}/100 ({grade}). {verdict_short}.",
        "url": f"https://nerq.ai/safe/{slug}",
        "dateModified": _today_iso,
        "publisher": {"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"},
        "speakable": {"@type": "SpeakableSpecification", "cssSelector": [".quick-verdict", ".verdict"]},
    })

    # JSON-LD: ItemList (dimensions)
    itemlist_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"Safety Score Breakdown for {display_name}",
        "numberOfItems": 5,
        "itemListElement": [
            {"@type": "ListItem", "position": i+1, "name": d[0], "description": f"{d[1]}/100 — {_safety_level(d[1])}"}
            for i, d in enumerate(dims)
        ]
    })

    # Cross-links — health-relevant only
    _cl = _esc(slug)
    cross_links_html = "".join([
        f'<a href="/is-{_cl}-safe" class="cross-link">{_t("cross_safety", lang)}</a>',
        f'<a href="/is-{_cl}-legit" class="cross-link">{_t("cross_legit", lang)}</a>',
        f'<a href="/review/{_cl}" class="cross-link">{_t("cross_review", lang)}</a>',
        f'<a href="/alternatives/{_cl}" class="cross-link">{_t("cross_alternatives", lang)}</a>',
    ])

    # Health disclaimer — registry-specific
    health_disclaimer_html = _t("health_disclaimer", lang)

    # Robots meta — always index if has description
    robots_meta = '<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">' if score >= 30 else '<meta name="robots" content="noindex, follow">'

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_t("title_ingredient", lang, name=_dn, year=datetime.now().year)}</title>
<meta name="description" content="{_dn} safety score: {score_str}/100 ({_esc(grade)}). {_esc(verdict_short)}. {'Toxicology, regulatory status, allergen risk, and long-term safety analysis.' if _is_ingredient else 'Evidence base, safety profile, drug interactions, and quality analysis.' if _is_supplement else 'Skin safety, toxicology, sensitization risk, and regulatory analysis.'}">
<link rel="canonical" href="https://nerq.ai/safe/{_esc(slug)}">
{render_hreflang(f"/safe/{slug}")}
<meta property="og:title" content="{page_title} — Nerq">
<meta property="og:description" content="{_dn} — {_esc(grade)} safety grade, {score_str}/100. Independent health safety analysis by Nerq.">
<meta property="og:url" content="https://nerq.ai/safe/{_esc(slug)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Nerq">
<meta name="twitter:card" content="summary">
{robots_meta}
<meta name="nerq:type" content="{_esc(source)}">
<meta name="nerq:entity" content="{_esc(slug)}">
<meta name="nerq:score" content="{score_str}">
<meta name="nerq:grade" content="{_esc(grade)}">
<meta name="nerq:verdict" content="{_esc(vb_text)}">
<meta name="nerq:category" content="{_esc(_type_label)}">
<meta name="nerq:source" content="{_esc(source)}">
<meta name="nerq:verified" content="{'true' if score >= 70 else 'false'}">
<meta name="nerq:updated" content="{_today_iso}">
<meta name="nerq:api" content="https://nerq.ai/v1/preflight?target={_esc(name)}">
<meta name="nerq:question" content="{_esc(meta_q)}">
<meta name="nerq:answer" content="{_esc(nerq_answer)}">
<meta name="citation_title" content="{page_title.replace('&amp;', '&')} {datetime.now().year}">
<meta name="citation_author" content="Nerq Safety Intelligence">
<meta name="citation_date" content="{_today_iso}">
<meta property="article:modified_time" content="{_today_iso}T12:00:00Z">
<meta name="nerq:data-version" content="1.0">
<meta name="nerq:data-sources" content="{_data_sources}">
<script type="application/ld+json">{webpage_jsonld}</script>
<script type="application/ld+json">{faq_jsonld}</script>
<script type="application/ld+json">{breadcrumb_jsonld}</script>
<script type="application/ld+json">{entity_jsonld}</script>
<script type="application/ld+json">{itemlist_jsonld}</script>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0f172a;line-height:1.6;background:#fff;font-size:15px}}
a{{color:#2563eb;text-decoration:none}}a:hover{{color:#1d4ed8;text-decoration:underline}}
.nav{{border-bottom:1px solid #e2e8f0;padding:10px 0;position:sticky;top:0;background:#fff;z-index:100}}
.nav-inner{{max-width:1100px;margin:0 auto;padding:0 20px;display:flex;align-items:center;gap:16px}}
.nav-logo{{font-size:20px;font-weight:700;color:#0f172a;text-decoration:none}}.nav-logo:hover{{text-decoration:none}}
.nav-logo span{{font-weight:400;color:#64748b;font-size:13px;margin-left:6px}}
.nav-links{{display:flex;gap:16px;font-size:13px;margin-left:auto}}.nav-links a{{color:#64748b;text-decoration:none}}
.wrap{{max-width:800px;margin:0 auto;padding:24px 20px}}
h1{{font-size:28px;font-weight:700;margin-bottom:4px;line-height:1.3}}
h2{{font-size:20px;font-weight:600;margin:28px 0 12px;color:#0f172a}}
h3{{font-size:16px;font-weight:600;margin:16px 0 8px;color:#1e293b}}
.quick-verdict{{font-size:16px;line-height:1.8;color:#374151;margin:16px 0;padding:16px 20px;background:#f8fafc;border-radius:10px;border-left:4px solid {vb_color}}}
.verdict{{display:flex;align-items:center;gap:16px;padding:16px 20px;border-radius:10px;margin:16px 0;background:{vb_bg};border:1px solid {vb_color}20}}
.verdict-score{{font-size:36px;font-weight:700;color:{vb_color}}}
.verdict-text h3{{margin:0;font-size:18px;color:{vb_color}}}
.verdict-text p{{margin:4px 0 0;font-size:14px;color:#374151}}
.section{{margin:24px 0;padding:20px 0;border-top:1px solid #f1f5f9}}
.section-title{{font-size:20px;font-weight:600;margin:0 0 12px}}
.breakdown-item{{display:flex;align-items:center;gap:10px;margin:8px 0}}
.breakdown-label{{flex:0 0 220px;font-size:14px;color:#374151}}
.breakdown-bar{{flex:1;height:8px;background:#f1f5f9;border-radius:99px;overflow:hidden}}
.breakdown-fill{{height:100%;border-radius:99px;transition:width .3s}}
.breakdown-val{{flex:0 0 70px;text-align:right;font-size:14px;font-weight:600;font-family:ui-monospace,monospace}}
.sc-high{{color:#16a34a}}.sc-good{{color:#22c55e}}.sc-mid{{color:#f59e0b}}.sc-low{{color:#ef4444}}.sc-crit{{color:#991b1b}}
.finding{{display:flex;align-items:center;gap:8px;padding:6px 0;font-size:14px}}
.finding-icon{{width:20px;text-align:center;flex-shrink:0}}
.finding-good .finding-icon{{color:#16a34a}}.finding-warn .finding-icon{{color:#f59e0b}}.finding-bad .finding-icon{{color:#dc2626}}
.alt-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin:12px 0}}
.alt-card{{display:block;padding:12px 14px;border:1px solid #e2e8f0;border-radius:8px;text-decoration:none;color:#0f172a;transition:border-color .2s}}.alt-card:hover{{border-color:#2563eb;text-decoration:none}}
.alt-name{{font-weight:600;font-size:14px}}.alt-score{{font-size:13px;color:#64748b;margin-top:2px}}
.cross-link{{display:inline-block;padding:4px 12px;border:1px solid #e2e8f0;border-radius:99px;font-size:12px;color:#64748b;margin:3px;text-decoration:none}}.cross-link:hover{{border-color:#2563eb;color:#2563eb;text-decoration:none}}
.faq details{{border-bottom:1px solid #f1f5f9;padding:12px 0}}
.faq summary{{cursor:pointer;font-weight:600;font-size:15px;color:#0f172a;list-style:none}}
.faq summary::-webkit-details-marker{{display:none}}.faq summary::before{{content:'+ ';color:#64748b}}
.faq details[open] summary::before{{content:'− '}}
.faq .faq-a{{padding:8px 0;font-size:14px;color:#374151;line-height:1.7}}
.pill{{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:600}}
.pill-green{{background:#dcfce7;color:#166534}}.pill-yellow{{background:#fef9c3;color:#854d0e}}.pill-red{{background:#fee2e2;color:#991b1b}}
@media(max-width:640px){{.breakdown-label{{flex:0 0 140px;font-size:13px}}.verdict{{flex-direction:column;text-align:center}}.wrap{{padding:16px 12px}}h1{{font-size:22px}}}}
</style>
</head>
<body>
{NERQ_NAV}

<div class="wrap">

<h1>{_t("h1_ingredient_safe", lang, name=_dn)}</h1>
<p style="font-size:14px;color:#64748b;margin-bottom:16px">Independent {'skincare' if _is_cosmetic else 'health'} safety analysis · Updated {_today}</p>

<div class="verdict">
<div class="verdict-score">{float(score):.0f}</div>
<div class="verdict-text">
<h3>{vb_text}</h3>
<p>{key_line}</p>
</div>
<div style="margin-left:auto;text-align:right">
<span class="pill {'pill-green' if score >= 70 else 'pill-yellow' if score >= 50 else 'pill-red'}">{_esc(grade)}</span>
</div>
</div>

<div class="quick-verdict">
{definition_lead}
Overall assessment: {_dn} is {rec_text}.
</div>

<div style="display:flex;flex-wrap:wrap;gap:6px;margin:12px 0">{cross_links_html}</div>

{health_disclaimer_html}

<div class="section">
<h2 class="section-title">{_t("safety_score_breakdown", lang)}</h2>
{breakdown_html}
</div>

<div class="section">
<h2 class="section-title">{_t("key_safety_findings", lang)}</h2>
{findings_html}
</div>

{regulatory_html}

{concerns_html}

{faq_html}

{similar_html}

{methodology_html}

{freshness_html}

<p style="font-size:12px;color:#94a3b8;margin-top:20px;border-top:1px solid #e2e8f0;padding-top:10px">
This page is for informational purposes only and does not constitute medical, nutritional, or dermatological advice.
Always consult a qualified professional before making health-related decisions.
Data sourced from FDA, EFSA, NIH, and peer-reviewed research.
<a href="/health-disclaimer" style="color:#64748b">Full health disclaimer</a>.
</p>

</div>

{NERQ_FOOTER}
</body></html>"""


def _render_agent_page(slug, agent_info, lang="en"):
    """Render a full agent safety page. Pass lang for native i18n."""
    # Look up fresh data from DB
    name = agent_info.get("name", slug)

    # Try smart entity resolution first (checks software_registry, website_cache)
    # Also try normalized slug (no hyphens) for cases like "nord-vpn" → "nordvpn"
    resolved = _resolve_entity(slug)
    if not resolved:
        norm_slug = slug.replace("-", "").replace("_", "").replace(" ", "")
        if norm_slug != slug:
            resolved = _resolve_entity(norm_slug)
    if resolved:
        agent = resolved
    else:
        agent = _lookup_agent(name)
        # Also try normalized name
        if not agent:
            norm_name = name.replace("-", "").replace("_", "").replace(" ", "")
            if norm_name != name:
                agent = _lookup_agent(norm_name)
    if not agent:
        # NO ENTITY FOUND — show "Not yet analyzed" page, NOT a fake 0/100 rating
        display_name = name.split("/")[-1].replace("-", " ").replace("_", " ").title()
        return _render_not_analyzed_page(slug, display_name, lang=lang)

    # Route country/city pages to dedicated travel template (no software language)
    _resolved_source = agent.get("source") or agent.get("registry") or ""
    if _resolved_source in ("country", "city"):
        return _render_travel_page(slug, agent, lang=lang)
    if _resolved_source == "charity":
        return _render_charity_page(slug, agent, lang=lang)
    if _resolved_source in ("ingredient", "supplement", "cosmetic_ingredient"):
        return _render_ingredient_page(slug, agent, lang=lang)

    name = agent.get("name") or name
    # Derive a clean display name for titles/headings (e.g. "getcursor/cursor" → "Cursor")
    display_name = _DISPLAY_NAMES.get(name)
    if not display_name:
        # Fallback: strip org prefix and title-case
        display_name = name.split("/")[-1].replace("-", " ").replace("_", " ").title()
    score = agent.get("trust_score") or 0

    # ── Well-known tool score floors ──
    # Some DB entries represent wrong entities (e.g. HuggingFace fan spaces
    # instead of the real product). For widely-used tools with no known
    # critical security issues, apply a credible minimum score.
    # Question answered: "Is this tool safe to use?" — YES for all of these.
    _SCORE_FLOORS = {
        # Keys are LOWERCASED for case-insensitive matching.
        # Includes both override names and actual DB names.
        "getcursor/cursor": 78,         # 50K+ stars, massive adoption, backed by a16z
        "chatgpt": 82,                  # Most-used AI tool, enterprise SOC2
        "github copilot": 80,           # Microsoft-backed, enterprise-grade
        "github copilot cli": 80,
        "windsurf": 75,                 # Codeium-backed IDE, growing adoption
        "bolt": 73,                     # StackBlitz product, well-funded
        "claude": 82,                   # Anthropic product, SOC2/enterprise
        "claude-code": 82,
        "gemini": 80,                   # Google product, enterprise
        "huggingface": 79,              # ML platform, massive ecosystem
        "hugging face": 79,
        "stable diffusion": 72,         # Widely used, open-source core
        "comfy (stable diffusion)": 72,
        "openai/openai-python": 83,     # Official OpenAI SDK, 25K stars
        "cognition-labs/devin": 70,     # Cognition Labs, well-funded
        "devin": 70,
        "lovable": 72,                  # Funded startup, growing
        "replit": 76,                   # Major platform, millions of users
        "v0": 74,                       # Vercel product
        "midjourney": 73,               # Widely used image gen
        "pydantic/pydantic-ai": 78,     # Pydantic team, 15K+ stars, well-maintained
        "pydantic-ai": 78,
        "langgenius/dify": 76,          # 130K+ stars, major AI platform
        "dify": 76,
        "n8n-io/n8n": 78,              # 177K+ stars, major automation platform
        "n8n": 78,
        "agno-agi/agno": 76,           # 38K+ stars, popular framework
        "agno": 76,
        "run-llama/llama_index": 79,   # 47K+ stars, LlamaIndex
        "llamaindex": 79,
        "composiohq/composio": 78,     # 27K+ stars, integration platform
        "composio": 78,
        # Well-known packages (same floors as preflight _TRUST_FLOOR)
        "openai": 85, "anthropic": 85, "tensorflow": 88, "pytorch": 88,
        "transformers": 87, "numpy": 90, "pandas": 90, "scikit-learn": 88,
        "react": 90, "next.js": 88, "nextjs": 88, "vercel": 85,
        "stripe": 88, "fastapi": 86, "flask": 85, "django": 88,
        "express": 86, "axios": 84, "lodash": 88, "webpack": 82,
        "typescript": 90, "eslint": 85, "prettier": 84, "jest": 86,
        "vue": 88, "angular": 87, "svelte": 85, "tailwindcss": 86,
        "moment": 75, "requests": 88, "boto3": 86, "sqlalchemy": 87,
        "scipy": 88, "matplotlib": 87, "pillow": 85,
    }
    # Also check slug (for entities resolved from software_registry)
    floor = _SCORE_FLOORS.get(name.lower(), 0) or _SCORE_FLOORS.get(slug.lower(), 0)
    if floor and score < floor:
        score = float(floor)

    score_str = f"{score:.1f}" if isinstance(score, float) else str(score)
    grade = agent.get("trust_grade") or "N/A"
    # Recalculate grade if score was floored
    if floor and score >= floor:
        if score >= 90: grade = "A+"
        elif score >= 85: grade = "A"
        elif score >= 80: grade = "A-"
        elif score >= 75: grade = "B+"
        elif score >= 70: grade = "B"
        elif score >= 65: grade = "B-"
        elif score >= 60: grade = "C+"
        elif score >= 55: grade = "C"
        else: grade = "C-"
    category = agent.get("category") or "uncategorized"
    source = agent.get("source") or "unknown"
    source_url = agent.get("source_url") or ""
    stars = agent.get("stars") or 0
    author = agent.get("author") or "Unknown"
    description = agent.get("description") or ""
    is_verified = agent.get("is_verified") or (score >= 70)
    frameworks = agent.get("frameworks") or []
    protocols = agent.get("protocols") or []
    compliance_score = agent.get("compliance_score")
    eu_risk_class = agent.get("eu_risk_class") or ""
    doc_score = agent.get("documentation_score")
    activity_score = agent.get("activity_score")
    security_score = agent.get("security_score")
    popularity_score = agent.get("popularity_score")

    assessment = _trust_assessment(name, float(score), source)
    assessment_short = _assessment_short(name, float(score))
    pill_class = _grade_pill(grade)

    # Registry-specific page config (GEO)
    _rp = _get_registry_page(source)
    _entity_word = _rp["entity_word"]
    _hidden = _rp.get("hide_fields", set())

    # Definition Lead — first sentence IS the answer (GEO principle #1)
    _desc_suffix = ""
    if description:
        # Clean up: remove redundant name prefix, get first sentence
        _desc_clean = description.strip()
        _dn_lower = display_name.lower()
        # Strip "Name — " or "Name: " or "Name - " prefix
        for sep in [" — ", " - ", ": ", " – "]:
            if sep in _desc_clean:
                parts = _desc_clean.split(sep, 1)
                if parts[0].lower().replace(" ", "") in _dn_lower.replace(" ", "") or _dn_lower.replace(" ", "") in parts[0].lower().replace(" ", ""):
                    _desc_clean = parts[1]
                    break
        _desc_short = _desc_clean.split(".")[0].strip()[:80]
        if _desc_short and len(_desc_short) > 10 and _desc_short.lower() not in _dn_lower:
            # Use parenthetical for long/complex descriptions, "for X" for short technical ones
            if len(_desc_short) > 50 or _desc_short[0].isupper():
                _desc_suffix = ""  # Skip overly long/complex descriptions
            else:
                _desc_suffix = f" ({_desc_short})"
    _article = "an" if _entity_word[0].lower() in "aeiou" else "a"
    _rank_text = ""
    if source == "website" and agent.get("downloads") and int(agent.get("downloads", 0)) < 100000:
        _rank_text = f", ranked #{int(agent['downloads']):,} globally (Tranco)"
    _extra_lead = ""
    if source == "country":
        _s = float(score)
        _adv = "Exercise Normal Precautions" if _s >= 80 else "Exercise Increased Caution" if _s >= 60 else "Reconsider Travel" if _s >= 40 else "Do Not Travel"
        _extra_lead = f" Travel advisory: {_adv}. {_esc(description[:150]) if description else ''}"
    # Verdict-first definition lead (LLMs cite first sentence)
    _score_f = float(score)
    if _score_f >= 70:
        _verdict_prefix = _t("yes_safe", lang, name=_esc(display_name))
    elif _score_f >= 50:
        _verdict_prefix = _t("use_caution", lang, name=_esc(display_name))
    elif _score_f >= 30:
        _verdict_prefix = _t("exercise_caution", lang, name=_esc(display_name))
    else:
        _verdict_prefix = _t("significant_concerns", lang, name=_esc(display_name))
    _n_dims = len([s for s in [security_score, activity_score, popularity_score, doc_score, compliance_score] if s is not None])
    _entity_type_local = _t(f"type_{source}", lang) if _t(f"type_{source}", lang) != f"type_{source}" else _entity_word
    definition_lead = (
        f"{_verdict_prefix} "
        f"{_esc(display_name)} {_t('is_a_type', lang, type=_entity_type_local)}"
        f"{_desc_suffix}{_rank_text} {_t('with_trust_score', lang, score=score_str, grade=_esc(grade))}"
        f"{', ' + _t('based_on_dims', lang, dims=str(max(_n_dims, 3))) if _n_dims else ''}"
        f".{_extra_lead}"
    )

    # nerq:answer — self-contained, AI-extractable (GEO principle #2)
    _dn = _esc(display_name)
    nerq_answer = (
        f"{_verdict_prefix} "
        f"{_dn} is a {_entity_word} with a Nerq Trust Score of {score_str}/100 ({_esc(grade)}). "
        f"{'Nerq Verified — meets the 70+ trust threshold.' if is_verified else 'Below the Nerq Verified threshold of 70.'}"
    )

    # AI summary — must include score, category, verified status, and one specific signal
    verified_text = "It is Nerq Verified (trust score >= 70)." if is_verified else "It has not yet reached the Nerq Verified threshold (70+)."
    # Find the strongest signal for the summary
    _sig_pairs = []
    if security_score is not None:
        _sig_pairs.append(("security", security_score))
    if compliance_score is not None:
        _sig_pairs.append(("compliance", compliance_score))
    if activity_score is not None:
        _sig_pairs.append(("maintenance", activity_score))
    if doc_score is not None:
        _sig_pairs.append(("documentation", doc_score))
    if popularity_score is not None:
        _sig_pairs.append(("popularity", popularity_score))
    best_sig_text = ""
    if _sig_pairs:
        best_pair = max(_sig_pairs, key=lambda x: x[1])
        best_sig_text = f"Its strongest signal is {best_pair[0]} ({best_pair[1]:.0f}/100). "
    # Compliance jurisdiction count
    _compliance_count = ""
    if compliance_score is not None and compliance_score > 0:
        _approx_jurisdictions = int(compliance_score * 52 / 100)
        _eu_note = " EU AI Act compliant." if eu_risk_class and eu_risk_class.lower() in ("minimal", "limited") else ""
        _compliance_count = f" Compliance: {_approx_jurisdictions} of 52 jurisdictions.{_eu_note}"

    ai_summary = (
        f"{_esc(name)} has a Nerq Trust Score of {score_str}/100 ({_esc(grade)}). "
        f"{'Recommended — meets Nerq Verified threshold.' if is_verified else 'Not yet Nerq Verified (requires 70+).'} "
        f"{best_sig_text}"
        f"{_compliance_count} "
        f"Last verified: {datetime.now().strftime('%Y-%m-%d')}."
    )

    # Signals grid
    signals = []
    if security_score is not None:
        signals.append((_t("security", lang), f"{security_score:.0f}", _t("security_desc", lang)))
    if compliance_score is not None:
        signals.append((_t("compliance", lang), f"{compliance_score:.0f}", f"Regulatory alignment. EU AI Act risk class: {_esc(eu_risk_class) or 'N/A'}."))
    if activity_score is not None:
        signals.append((_t("maintenance", lang), f"{activity_score:.0f}", _t("maintenance_desc", lang)))
    if doc_score is not None:
        signals.append((_t("documentation", lang), f"{doc_score:.0f}", _t("documentation_desc", lang)))
    if popularity_score is not None:
        _pop_detail = {
            "vpn": "Based on server count and market presence.",
            "ios": f"{stars:,} installs on App Store." if stars else "App Store presence.",
            "android": f"{stars:,} installs on Google Play." if stars else "Google Play presence.",
            "steam": f"{stars:,} players." if stars else "Steam community.",
            "chrome": f"{stars:,} users." if stars else "Chrome Web Store.",
            "firefox": f"{stars:,} daily users." if stars else "Firefox Add-ons.",
            "vscode": f"{stars:,} installs." if stars else "VS Code Marketplace.",
            "wordpress": f"{stars:,} active installs." if stars else "WordPress.org.",
            "website": f"Tranco rank: {stars}." if stars else "Web presence.",
        }.get(source, f"{stars:,} stars on {_esc(source)}." if stars else "Community adoption.")
        signals.append((_t("popularity", lang), f"{popularity_score:.0f}", f"Community adoption. {_pop_detail}"))
    if not signals:
        signals.append((_t("overall_trust", lang), score_str, _t("overall_trust_desc", lang)))

    signals_html = ""
    for sig_name, sig_val, sig_desc in signals:
        signals_html += (
            f'<div class="signal-card">'
            f'<div class="sig-name">{sig_name}</div>'
            f'<div class="sig-val">{sig_val}</div>'
            f'<div class="sig-desc">{sig_desc}</div>'
            f'</div>'
        )

    # Verified badge HTML
    verified_badge = '<span class="pill pill-green" style="font-size:11px">verified</span>' if is_verified else ""

    # Source link
    source_link = f'<a href="{_esc(source_url)}">{_esc(source_url)}</a>' if source_url else "N/A"

    # Frameworks row (hidden for non-dev registries)
    frameworks_row = ""
    if frameworks and "frameworks" not in _hidden:
        fw_html = " &middot; ".join(_esc(f) for f in frameworks[:5])
        frameworks_row = f'<tr><td style="color:#6b7280">Frameworks</td><td>{fw_html}</td></tr>'

    # Protocols row (hidden for non-dev registries)
    protocols_row = ""
    if protocols and "protocols" not in _hidden:
        pr_html = " &middot; ".join(_esc(p) for p in protocols[:5])
        protocols_row = f'<tr><td style="color:#6b7280">Protocols</td><td>{pr_html}</td></tr>'

    # Alternatives section
    alternatives = _get_alternatives(category, name, float(score))
    alternatives_section = ""
    if alternatives:
        cards = ""
        for alt in alternatives:
            alt_slug = alt.get("slug") or _make_slug(alt["name"])
            alt_score = alt.get("trust_score") or 0
            cards += (
                f'<a href="/safe/{_esc(alt_slug)}" class="alt-card">'
                f'<div class="alt-name">{_esc(alt["name"])}</div>'
                f'<div class="alt-score">{alt_score:.1f}/100 &middot; {_esc(alt.get("trust_grade", ""))}</div>'
                f'<div class="alt-cat">{_esc(alt.get("source", ""))}</div>'
                f'</a>'
            )
        alternatives_section = (
            f'<h2>{_t("popular_alternatives", lang, category=_esc(category))}</h2>'
            f'<div class="alt-grid">{cards}</div>'
        )

    # ── CTA buttons for security/privacy deep-dive ──
    _sec_label = _t("security_analysis", lang, name=_esc(display_name))
    _pri_label = _t("privacy_report", lang, name=_esc(display_name))
    cta_buttons = f"""<div style="display:flex;gap:10px;margin:16px 0">
<a href="/safe/{_esc(slug)}/security" style="flex:1;padding:12px;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;text-decoration:none;text-align:center;color:#991b1b;font-weight:600;font-size:14px">{_sec_label} &rarr;</a>
<a href="/safe/{_esc(slug)}/privacy" style="flex:1;padding:12px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;text-decoration:none;text-align:center;color:#1e40af;font-weight:600;font-size:14px">{_pri_label} &rarr;</a>
</div>"""

    # ── Similar entities from same registry ──
    _sim_rows = []
    similar_entities_html = ""
    _REGISTRY_BEST_MAP = {
        "npm": "npm-packages", "pypi": "python-packages", "crates": "best-rust-crates",
        "nuget": "dotnet-testing-frameworks", "go": "go-web-frameworks",
        "wordpress": "best-wordpress-plugins", "chrome": "chrome-extensions",
        "firefox": "firefox-addons", "vscode": "best-vscode-extensions",
        "ios": "ios-apps", "android": "android-apps", "steam": "steam-games",
        "vpn": "safest-vpns", "password_manager": "safest-password-managers",
        "antivirus": "safest-antivirus-software", "hosting": "safest-web-hosting",
        "website_builder": "safest-website-builders", "homebrew": "homebrew-cli-tools",
        "gems": "ruby-web-frameworks", "packagist": "php-web-frameworks",
        "website": "safest-websites", "saas": "saas-tools",
        "country": "safest-countries", "city": "safest-cities",
        "charity": "charities", "ingredient": "safest-food-additives",
        "supplement": "best-supplements", "cosmetic_ingredient": "safest-skincare-ingredients",
        "crypto": "safest-crypto-exchanges",
    }
    try:
        _sim_session = get_session()
        _sim_rows = _sim_session.execute(text("""
            SELECT slug, name, trust_score FROM software_registry
            WHERE registry = :reg AND slug != :current
              AND trust_score BETWEEN :lo AND :hi
              AND enriched_at IS NOT NULL AND description IS NOT NULL
            ORDER BY trust_score DESC LIMIT 5
        """), {"reg": source, "current": slug, "lo": max(0, float(score) - 10), "hi": float(score) + 10}).fetchall()
        _sim_session.close()
        if _sim_rows:
            _sim_links = "".join(
                f'<a href="/safe/{_esc(r[0])}" style="display:inline-block;padding:6px 14px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;text-decoration:none;color:#334155;margin:3px">{_esc(r[1])} <span style="color:#64748b">({r[2]:.0f})</span></a>'
                for r in _sim_rows
            )
            _reg_display = source.replace("_", " ").title() if source else "entities"
            similar_entities_html = f'<div style="margin:20px 0"><h2 style="font-size:16px;font-weight:600;margin-bottom:8px">{_t("similar_in_registry", lang, registry=_esc(_reg_display))}</h2><div style="display:flex;flex-wrap:wrap;gap:4px">{_sim_links}</div>'
            # Best category link
            _best_slug = _REGISTRY_BEST_MAP.get(source)
            if _best_slug:
                similar_entities_html += f'<div style="margin-top:10px"><a href="/best/{_best_slug}" style="font-size:13px;color:#2563eb">{_t("see_all_best", lang, registry=_esc(_reg_display))} &rarr;</a></div>'
            similar_entities_html += '</div>'
            # Compare links from similar entities
            _cmp_links = "".join(
                f'<a href="/compare/{_esc(slug)}-vs-{_esc(r[0])}" style="display:inline-block;padding:6px 14px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;text-decoration:none;color:#334155;margin:3px">{_esc(display_name)} vs {_esc(r[1])}</a>'
                for r in _sim_rows[:3]
            )
            if _cmp_links:
                similar_entities_html += f'<div style="margin:12px 0 20px"><h3 style="font-size:14px;font-weight:600;margin-bottom:8px">Compare</h3><div style="display:flex;flex-wrap:wrap;gap:4px">{_cmp_links}</div></div>'
    except Exception:
        pass

    # ── Cross-product trust map ──
    cross_products = _get_cross_products(author, source, slug)
    cross_product_html = ""
    if cross_products:
        _cp_items = ""
        for cp in cross_products:
            _cp_slug = _make_slug(cp["name"])
            _cp_score = cp.get("trust_score") or 0
            _cp_items += (
                f'<a href="/safe/{_esc(_cp_slug)}" class="alt-card">'
                f'<div class="alt-name">{_esc(cp["name"])}</div>'
                f'<div class="alt-score">{_cp_score:.0f}/100 &middot; {_esc(cp.get("registry", ""))}</div>'
                f'</a>'
            )
        cross_product_html = (
            f'<h2>{_t("across_platforms", lang, name=_esc(display_name))}</h2>'
            f'<p style="font-size:14px;color:#64748b;margin:4px 0 12px">{_t("same_developer", lang)}</p>'
            f'<div class="alt-grid">{_cp_items}</div>'
        )

    # ── FAQ generation (GEO: prompt-aligned, registry-specific) ──
    best_signal = max(signals, key=lambda x: float(x[1]) if x[1].replace('.', '').isdigit() else 0) if signals else ("Overall", score_str, "")
    _dn_esc = _esc(display_name)
    _n_esc = _esc(name)
    _rec_text_en = _rp.get("recommendation", "recommended for use")
    # Translate recommendation via _t() key mapping
    _REC_KEYS = {
        "recommended for privacy-conscious use": "rec_privacy",
        "recommended for production use": "rec_production",
        "recommended for general use": "rec_general",
        "recommended for play": "rec_play",
        "recommended for use": "rec_use",
        "recommended for use in WordPress": "rec_wordpress",
    }
    _rec_key = _REC_KEYS.get(_rec_text_en, "rec_use")
    _rec_text = _t(_rec_key, lang) if lang != "en" else _rec_text_en

    # Build score dimensions list (only non-hidden ones) — localized
    _score_dims = []
    if security_score is not None:
        _score_dims.append(f"{_t('dim_security', lang)} ({security_score:.0f}/100)")
    if "maintenance" not in _hidden and activity_score is not None:
        _score_dims.append(f"{_t('dim_maintenance', lang)} ({activity_score:.0f}/100)")
    if popularity_score is not None:
        _score_dims.append(f"{_t('dim_popularity', lang)} ({popularity_score:.0f}/100)")
    if "documentation" not in _hidden and doc_score is not None:
        _score_dims.append(f"{_t('documentation', lang)} ({doc_score:.0f}/100)")
    _dims_text = ", ".join(_score_dims) if _score_dims else "multiple trust dimensions"

    # FAQ Q1: "Is X safe?" — verdict-first answer (localized)
    faq_q1 = _t("h1_safe", lang, name=_dn_esc)
    _faq_verdict = _t("yes_safe_short", lang) if float(score) >= 70 else _t("use_caution_faq", lang) if float(score) >= 50 else _t("exercise_caution_faq", lang) if float(score) >= 30 else _t("significant_concerns_faq", lang)
    faq_a1 = (
        f"{_faq_verdict} "
        f"{_n_esc} {_t('with_trust_score', lang, score=score_str, grade=_esc(grade))}. "
        f"{_t('strongest_signal', lang)} {best_signal[0].lower()} ({best_signal[1]}/100). "
        f"{_t('score_based_dims', lang, dims=_dims_text)}"
    )

    # FAQ Q2: "What is X's trust score?" (localized)
    faq_q2 = _t("h2q_trust_score", lang, name=_dn_esc)
    faq_a2 = (
        f"{_n_esc}: {score_str}/100 ({_esc(grade)}). "
        f"{_t('score_based_dims', lang, dims=_dims_text)} "
        f"{'Compliance: ' + str(round(compliance_score)) + '/100. ' if compliance_score else ''}"
        f"{_t('scores_update', lang)} "
        f"API: GET nerq.ai/v1/preflight?target={_esc(name)}"
    )

    # FAQ Q3: Alternatives (localized)
    alt_names = ", ".join(f"{_esc(a['name'])} ({a.get('trust_score', 0):.0f}/100)" for a in alternatives[:3]) if alternatives else ""
    # Use _t() for common FAQ questions, fall back to English registry-specific
    _faq_q3_t = _t("faq_q3_alts", lang, name=_dn_esc)
    faq_q3 = _faq_q3_t if _faq_q3_t != "faq_q3_alts" else _rp["faq_q3"].format(name=_dn_esc)
    _faq_cat_en = _REGISTRY_DISPLAY.get(category, category.replace("_", " ").title() if category else "")
    _faq_cat = _CROSS_CAT_I18N.get(_faq_cat_en, {}).get(lang, _faq_cat_en) if lang != "en" else _faq_cat_en
    faq_a3 = (
        f"{_t('in_category', lang, category=_esc(_faq_cat))} "
        + (f"{_t('higher_rated_alts', lang, alts=alt_names)} " if alternatives else f"{_t('more_being_analyzed', lang, type=_entity_word)} ")
        + f"{_n_esc} scores {score_str}/100."
    )

    # FAQ Q4: Registry-specific question (fully localized)
    _top_alt = alternatives[0] if alternatives else None
    _q4_en = _rp.get("faq_q4", "How often is {name}'s safety score updated?")
    _q4_key = _q4_en.lower()
    # Map English pattern → _t() key
    _Q4_MAP = [
        ("log", "faq_q4_log"), ("track", "faq_q4_log"), ("collect", "faq_q4_log"),
        ("vulnerabilit", "faq_q4_vuln"), ("kid", "faq_q4_kids"),
        ("permission", "faq_q4_perms"), ("maintained", "faq_q4_maintained"),
        ("scam", "faq_q4_scam"), ("telemetry", "faq_q4_telemetry"),
        ("gdpr", "faq_q4_gdpr"), ("training", "faq_q4_training"),
        ("updated", "faq_q4_update"),
    ]
    _q4_tkey = None
    for _pat, _key in _Q4_MAP:
        if _pat in _q4_key:
            _q4_tkey = _key
            break
    if _q4_tkey:
        _q4_t = _t(_q4_tkey, lang, name=_dn_esc)
        faq_q4 = _q4_t if _q4_t != _q4_tkey else _q4_en.format(name=_dn_esc, alt=_esc(_top_alt["name"]) if _top_alt else "alternatives")
    else:
        faq_q4 = _q4_en.format(name=_dn_esc, alt=_esc(_top_alt["name"]) if _top_alt else "alternatives")
    # Generate answer based on question topic (localized)
    _sec_str = f'{security_score:.0f}/100' if security_score is not None else 'N/A'
    _maint_str = f'{activity_score:.0f}/100' if activity_score is not None else 'N/A'
    if "log" in _q4_key or "track" in _q4_key or "collect" in _q4_key:
        faq_a4 = f"Nerq assesses {_dn_esc}'s data practices as part of its trust score ({score_str}/100). {_t('vpn_sec_score', lang)}: {_sec_str}. Review the full safety report for detailed privacy analysis."
    elif "vulnerabilit" in _q4_key:
        faq_a4 = _t("faq_a4_vuln", lang, name=_dn_esc, sec_score=_sec_str)
    elif "kid" in _q4_key:
        faq_a4 = _t("faq_a4_kids", lang, name=_dn_esc, score=score_str)
    elif "permission" in _q4_key:
        faq_a4 = _t("faq_a4_perms", lang, name=_dn_esc, score=score_str)
    elif "maintained" in _q4_key:
        faq_a4 = _t("faq_a4_maintained", lang, name=_dn_esc, maint_score=_maint_str)
    else:
        faq_a4 = (
            f"Nerq continuously monitors {_dn_esc} and updates its trust score as new data becomes available. "
            f"Current: {score_str}/100 ({_esc(grade)}), last verified {datetime.now().strftime('%Y-%m-%d')}. "
            f"API: GET nerq.ai/v1/preflight?target={_esc(name)}"
        )

    # FAQ Q5: Registry-specific question (fully localized)
    _q5_en = _rp.get("faq_q5", "Can I use {name} in a regulated environment?")
    _q5_key = _q5_en.lower()
    _Q5_MAP = [
        ("vs", "faq_q5_vs"), ("which is safer", "faq_q5_vs"),
        ("regulated", "faq_q5_regulated"),
        ("maintained", "faq_q4_maintained"), ("scam", "faq_q4_scam"),
        ("telemetry", "faq_q4_telemetry"), ("gdpr", "faq_q4_gdpr"),
        ("training", "faq_q4_training"),
    ]
    _q5_tkey = None
    for _pat, _key in _Q5_MAP:
        if _pat in _q5_key:
            _q5_tkey = _key
            break
    if _q5_tkey:
        _q5_t = _t(_q5_tkey, lang, name=_dn_esc)
        faq_q5 = _q5_t if _q5_t != _q5_tkey else _q5_en.format(name=_dn_esc, alt=_esc(_top_alt["name"]) if _top_alt else "alternatives", alt_slug=_make_slug(_top_alt["name"]) if _top_alt else "")
    else:
        faq_q5 = _q5_en.format(name=_dn_esc, alt=_esc(_top_alt["name"]) if _top_alt else "alternatives", alt_slug=_make_slug(_top_alt["name"]) if _top_alt else "")
    if "vs" in _q5_key or "which is safer" in _q5_key:
        if _top_alt:
            faq_a5 = f"{_dn_esc}: {score_str}/100. {_esc(_top_alt['name'])}: {_top_alt.get('trust_score', 0):.0f}/100."
        else:
            faq_a5 = f"{_dn_esc} scores {score_str}/100."
    elif "regulated" in _q5_key:
        faq_a5 = _t("faq_a5_verified", lang, name=_dn_esc) if is_verified else _t("faq_a5_not_verified", lang, name=_dn_esc)
    elif "maintained" in _q5_key:
        faq_a5 = _t("faq_a4_maintained", lang, name=_dn_esc, maint_score=_maint_str)
    elif "telemetry" in _q5_key:
        faq_a5 = f"Review {_dn_esc}'s documentation for telemetry settings. Trust score: {score_str}/100. Check the extension's settings for opt-out options."
    elif "unsafe" in _q5_key.lower():
        faq_a5 = f"Check {_dn_esc}'s crate documentation for unsafe code usage. Trust score: {score_str}/100. Fewer unsafe blocks generally indicates better memory safety."
    elif "collect" in _q5_key.lower() or "track" in _q5_key.lower() or "data" in _q5_key.lower():
        faq_a5 = f"Review {_dn_esc}'s privacy labels and data safety sections. Security score: {f'{security_score:.0f}/100' if security_score is not None else 'N/A'}. Trust score: {score_str}/100."
    elif "kid" in _q5_key.lower():
        faq_a5 = f"Check {_dn_esc}'s age rating and content ratings. Trust score: {score_str}/100. Always enable parental controls and review content before allowing children to use it."
    elif "reviewed" in _q5_key.lower():
        faq_a5 = f"Nerq analyzes {_dn_esc} using data from {_rp.get('data_sources', 'multiple sources')}. Trust score: {score_str}/100 ({_esc(grade)})."
    else:
        faq_a5 = _t("faq_a5_verified", lang, name=_dn_esc) if is_verified else _t("faq_a5_not_verified", lang, name=_dn_esc)

    # Build FAQ HTML section
    _faq_items = [
        (faq_q1, faq_a1), (faq_q2, faq_a2), (faq_q3, faq_a3),
        (faq_q4, faq_a4), (faq_q5, faq_a5),
    ]
    _faq_details = ""
    for fq, fa in _faq_items:
        _faq_details += f'<details><summary>{fq}</summary><div class="faq-a">{fa}</div></details>\n'
    faq_section_html = f'<div class="section faq"><h2 class="section-title">{_t("faq", lang)}</h2>{_faq_details}</div>'

    # JSON-LD: WebPage
    webpage_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": f"{_t('h1_safe', lang, name=display_name)} — {_t('trust_score_breakdown', lang)} {score_str}/100",
        "description": f"{display_name} — {_entity_type_local} — Nerq Trust Score {score_str}/100 ({grade}).",
        "url": f"https://nerq.ai/safe/{slug}",
        "dateModified": datetime.now().strftime("%Y-%m-%d"),
        "publisher": {"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"},
        "speakable": {"@type": "SpeakableSpecification", "cssSelector": [".pplx-verdict", ".ai-summary", ".verdict"]},
    })

    # JSON-LD: FAQPage (matches visible FAQ — GEO principle: prompt-aligned)
    faq_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": fq,
             "acceptedAnswer": {"@type": "Answer", "text": fa.replace("&mdash;", "—")}}
            for fq, fa in _faq_items
        ]
    }, separators=(',', ':'))

    # JSON-LD: BreadcrumbList
    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Nerq", "item": "https://nerq.ai"},
            {"@type": "ListItem", "position": 2, "name": "Safety Reports", "item": "https://nerq.ai/safe"},
            {"@type": "ListItem", "position": 3, "name": display_name},
        ]
    })

    # Reviews section
    reviews_section = ""
    try:
        review_rows = session_reviews = None
        _rs = get_session()
        try:
            stats_row = _rs.execute(text("""
                SELECT AVG(rating) as avg_rating, COUNT(*) as review_count
                FROM user_reviews WHERE agent_name = :name
            """), {"name": name}).fetchone()
            review_rows = _rs.execute(text("""
                SELECT rating, comment, reviewer_name, created_at, is_editorial
                FROM user_reviews WHERE agent_name = :name
                ORDER BY is_editorial DESC, created_at DESC LIMIT 10
            """), {"name": name}).fetchall()
        finally:
            _rs.close()

        avg_rating = 0
        review_count = 0
        if stats_row:
            sm = dict(stats_row._mapping)
            avg_rating = round(float(sm["avg_rating"]), 1) if sm["avg_rating"] else 0
            review_count = int(sm["review_count"]) if sm["review_count"] else 0

        if review_count > 0:
            # Stars display
            full_stars = int(avg_rating)
            remaining = 5 - full_stars
            stars_html = ('&#9733;' * full_stars) + ('&#9734;' * remaining)

            reviews_cards = ""
            for rv in (review_rows or []):
                rv_d = dict(rv._mapping)
                rv_rating = rv_d.get("rating", 0)
                rv_comment = rv_d.get("comment") or ""
                rv_reviewer = rv_d.get("reviewer_name") or "Anonymous"
                rv_date = str(rv_d.get("created_at") or "")[:10]
                rv_editorial = rv_d.get("is_editorial", False)
                editorial_tag = ' <span class="pill pill-green" style="font-size:10px">Editorial</span>' if rv_editorial else ""
                rv_stars = '&#9733;' * rv_rating + '&#9734;' * (5 - rv_rating)
                reviews_cards += (
                    f'<div class="card" style="padding:16px">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
                    f'<div><span style="color:#f59e0b;font-size:14px">{rv_stars}</span> '
                    f'<span style="color:#6b7280;font-size:13px">{_esc(rv_reviewer)}{editorial_tag}</span></div>'
                    f'<span style="color:#6b7280;font-size:12px">{_esc(rv_date)}</span>'
                    f'</div>'
                    f'<p style="font-size:14px;color:#374151;line-height:1.6;margin:0">{_esc(rv_comment)}</p>'
                    f'</div>'
                )

            reviews_section = (
                f'<h2>{_t("community_reviews", lang)}</h2>'
                f'<div style="display:flex;align-items:center;gap:12px;margin:8px 0 16px">'
                f'<span style="color:#f59e0b;font-size:20px">{stars_html}</span>'
                f'<span style="color:#6b7280;font-size:14px">{avg_rating}/5 ({review_count} review{"s" if review_count != 1 else ""})</span>'
                f'<a href="/review/{_esc(slug)}" style="font-size:13px;margin-left:auto">{_t("write_review", lang)}</a>'
                f'</div>'
                f'{reviews_cards}'
            )
        else:
            reviews_section = (
                f'<h2>{_t("community_reviews", lang)}</h2>'
                f'<p style="color:#6b7280;font-size:14px">{_t("no_reviews", lang)} '
                f'<a href="/review/{_esc(slug)}">{_t("be_first_review", lang, name=_esc(name))}</a>.</p>'
            )
    except Exception as e:
        logger.warning(f"Failed to load reviews for {name}: {e}")
        reviews_section = ""

    # Compliance section
    compliance_section = ""
    if eu_risk_class or compliance_score:
        risk_pill = ""
        if eu_risk_class:
            risk_colors = {"minimal": "pill-green", "limited": "pill-yellow", "high": "pill-red"}
            risk_pill = f'<span class="pill {risk_colors.get(eu_risk_class, "pill-gray")}">{_esc(eu_risk_class.upper())}</span>'

        score_text = f'<span style="font-family:ui-monospace,monospace;font-size:14px">{round(compliance_score)}/100</span>' if compliance_score else ""

        compliance_section = (
            f'<h2>{_t("regulatory_compliance", lang)}</h2>'
            f'<div class="card" style="padding:16px">'
            f'<table style="margin:0">'
            f'<tr><td style="color:#6b7280;width:160px">{_t("eu_ai_risk_class", lang)}</td><td>{risk_pill or "Not assessed"}</td></tr>'
            f'<tr><td style="color:#6b7280">{_t("compliance_score_label", lang)}</td><td>{score_text or "N/A"}</td></tr>'
            f'<tr><td style="color:#6b7280">{_t("jurisdictions", lang)}</td><td>{_t("assessed_across", lang)} <a href="/compliance">52 jurisdictions</a></td></tr>'
            f'</table>'
            f'</div>'
        )

    # Safety verdict for featured snippet
    if float(score) >= 70:
        safety_verdict = "YES"
        verdict_detail = f"It meets Nerq's trust threshold with strong signals across security, maintenance, and community adoption"
        verdict_recommendation = f"{_rec_text.capitalize()} — review the full report below for specific considerations"
        verdict_color = "green"
    elif float(score) >= 50:
        safety_verdict = "CAUTION"
        verdict_detail = f"It has moderate trust signals but shows some areas of concern that warrant attention"
        verdict_recommendation = f"Suitable for development use — review security and maintenance signals before production deployment"
        verdict_color = "amber"
    else:
        safety_verdict = "NO — USE WITH CAUTION"
        verdict_detail = f"It has below-average trust signals with significant gaps in security, maintenance, or documentation"
        verdict_recommendation = f"Not recommended for production use without thorough manual review and additional security measures"
        verdict_color = "red"

    # ── Verdict box variables ──
    _score_f = float(score)
    if _score_f >= 70:
        vb_color = "#16a34a"
        vb_bg = "#f0fdf4"
        vb_icon = "\u2705"   # check mark
        vb_text = _t("safe", lang)
    elif _score_f >= 40:
        vb_color = "#d97706"
        vb_bg = "#fffbeb"
        vb_icon = "\u26a0\ufe0f"  # warning
        vb_text = _t("use_caution_short", lang)
    else:
        vb_color = "#dc2626"
        vb_bg = "#fef2f2"
        vb_icon = "\U0001f534"   # red circle
        vb_text = _t("avoid", lang)

    # Key line for verdict box
    if _score_f >= 70:
        key_line = f"{_t('passes_threshold', lang)} \u2014 {_rec_text}"
    elif _score_f >= 40:
        key_line = f"{_t('below_threshold', lang)} \u2014 review signals before deploying"
    else:
        key_line = f"{_t('significant_gaps', lang)} \u2014 not recommended without manual review"

    # ── Why This Score bullets ──
    _why_bullets = []
    if security_score is not None:
        _sec_label = _t("strong", lang) if security_score >= 70 else _t("moderate", lang) if security_score >= 40 else _t("weak", lang)
        _why_bullets.append(f"<li>{_t('vpn_sec_score', lang)}: {security_score:.0f}/100 ({_sec_label})</li>")
    if activity_score is not None:
        _act_label = _t("actively_maintained", lang) if activity_score >= 70 else _t("moderately_maintained", lang) if activity_score >= 40 else _t("low_maintenance", lang)
        _why_bullets.append(f"<li>{_t('maintenance', lang)}: {activity_score:.0f}/100 \u2014 {_act_label}</li>")
    if compliance_score is not None:
        _comp_label = f"covers {int(compliance_score * 52 / 100)} of 52 jurisdictions"
        _why_bullets.append(f"<li>{_t('compliance', lang)}: {compliance_score:.0f}/100 \u2014 {_comp_label}</li>")
    if doc_score is not None:
        _doc_label = _t("well_documented", lang) if doc_score >= 70 else _t("partial_documentation", lang) if doc_score >= 40 else _t("limited_documentation", lang)
        _why_bullets.append(f"<li>{_t('documentation', lang)}: {doc_score:.0f}/100 \u2014 {_doc_label}</li>")
    if popularity_score is not None:
        _reg_disp = _REGISTRY_DISPLAY.get(source, source.replace("_", " ") if source else "")
        _pop_label = {
            "vpn": _t("widely_used_vpn", lang) if lang != "en" and _t("widely_used_vpn", lang) != "widely_used_vpn" else "widely used VPN service",
            "ios": f"{stars:,} App Store installs" if stars else "App Store presence",
            "android": f"{stars:,} Google Play installs" if stars else "Google Play presence",
            "steam": f"{stars:,} players" if stars else "Steam community",
            "chrome": f"{stars:,} Chrome users" if stars else "Chrome Web Store",
            "firefox": f"{stars:,} daily users" if stars else "Firefox Add-ons",
            "vscode": f"{stars:,} VS Code installs" if stars else "VS Code Marketplace",
            "wordpress": f"{stars:,} active installs" if stars else "WordPress.org",
            "website": f"Tranco rank {stars}" if stars else "web presence",
        }.get(source, f"{stars:,} stars on {_esc(_reg_disp)}" if stars else _t("community_adoption", lang) if lang != "en" and _t("community_adoption", lang) != "community_adoption" else "community adoption")
        _why_bullets.append(f"<li>{_t('popularity', lang)}: {popularity_score:.0f}/100 \u2014 {_pop_label}</li>")
    if not _why_bullets:
        _why_bullets.append(f"<li>Composite trust score: {score_str}/100 across all available signals</li>")
    why_this_score_bullets = "\n".join(_why_bullets)

    # ── Safer Alternatives section ──
    safer_alternatives_section = ""
    if alternatives:
        # Filter to alternatives with higher scores
        _safer = [a for a in alternatives if (a.get("trust_score") or 0) > _score_f]
        if _safer:
            _sa_cards = ""
            for alt in _safer[:4]:
                alt_slug = alt.get("slug") or _make_slug(alt["name"])
                alt_score = alt.get("trust_score") or 0
                _sa_cards += (
                    f'<a href="/safe/{_esc(alt_slug)}" class="alt-card">'
                    f'<div class="alt-name">{_esc(alt["name"])}</div>'
                    f'<div class="alt-score">{alt_score:.1f}/100 &middot; {_esc(alt.get("trust_grade", ""))}</div>'
                    f'<div class="alt-cat">{_esc(alt.get("source", ""))}</div>'
                    f'</a>'
                )
            safer_alternatives_section = (
                f'<h2>{_t("safer_alternatives", lang)}</h2>'
                f'<p style="font-size:15px;color:#374151;margin:4px 0 12px">Higher-rated {_entity_word}s you may want to consider:</p>'
                f'<div class="alt-grid">{_sa_cards}</div>'
            )

    # Badge markdown
    badge_md = f"[![Nerq Trust Score](https://nerq.ai/badge/{_esc(name)})](https://nerq.ai/safe/{_esc(slug)})"

    # ── New design: score color classes ──
    _s = float(score)
    if _s >= 80: score_color_class = "sc-high"
    elif _s >= 60: score_color_class = "sc-good"
    elif _s >= 40: score_color_class = "sc-mid"
    elif _s >= 20: score_color_class = "sc-low"
    else: score_color_class = "sc-crit"

    _g = grade.upper()[0] if grade and grade != "N/A" else "D"
    grade_bg_class = {"A": "bg-high", "B": "bg-good", "C": "bg-mid", "D": "bg-low", "F": "bg-crit"}.get(_g, "bg-mid")

    # Verdict box border color
    vb_border = vb_color

    # Score as integer for verdict display
    score_int = f"{float(score):.0f}"

    # ── D1: Perplexity-optimized verdict (self-contained, extractable, fully localized) ──
    _vuln_count = agent.get("cve_count") or 0
    _sig_count = len([s for s in [security_score, compliance_score, activity_score, doc_score, popularity_score] if s is not None]) or 5
    _s_f = float(score)
    if _s_f >= 80: _safety_v = _t("pv_safe", lang)
    elif _s_f >= 60: _safety_v = _t("pv_generally_safe", lang)
    elif _s_f >= 40: _safety_v = _t("pv_notable_concerns", lang)
    elif _s_f >= 20: _safety_v = _t("pv_significant_risks", lang)
    else: _safety_v = _t("pv_unsafe", lang)
    _pv_grade = _t("pv_grade", lang, grade=_esc(grade))
    _pv_body = _t("pv_body", lang, dims=str(_sig_count), verdict=f"<strong>{_safety_v}</strong>")
    _pv_vulns = f" {_t('pv_vulns', lang, count=str(_vuln_count))}" if _vuln_count else ""
    _pv_updated = _t("pv_updated", lang, date=datetime.now().strftime('%Y-%m-%d'))
    _pplx_verdict = (
        f"<strong>{_esc(display_name)}</strong> — Nerq Trust Score "
        f"<strong>{score_str}/100 ({_pv_grade})</strong>. "
        f"{_pv_body}{_pv_vulns} {_pv_updated}"
    )

    # ── D2: Question-format H2s with answer summaries (fully localized) ──
    _dn = _esc(display_name)
    _h2_trust = _t("h2q_trust_score", lang, name=_dn)
    _ans_trust = _t("ans_trust", lang, name=_dn, score=score_str, grade=_esc(grade), dims=str(_sig_count))
    _h2_findings = _t("h2q_key_findings", lang, name=_dn)
    _best_sig = max(signals, key=lambda x: float(x[1]) if x[1].replace('.', '').isdigit() else 0) if signals else ("Overall", score_str, "")
    _vuln_text = _t("ans_no_vulns", lang) if not _vuln_count else _t("ans_has_vulns", lang, count=str(_vuln_count))
    _verified_text = _t("ans_verified", lang) if is_verified else _t("ans_not_verified", lang)
    _ans_findings = (
        f"{_t('ans_findings_strong', lang, name=_dn, signal=_best_sig[0].lower(), signal_score=_best_sig[1])} "
        f"{_vuln_text} {_verified_text}"
    )
    _h2_details = _t("h2q_details", lang, name=_dn)

    # Trust breakdown with progress bars (new design)
    signals_breakdown_html = ""
    for sig_name, sig_val, sig_desc in signals:
        sv = float(sig_val) if sig_val.replace('.', '').isdigit() else 0
        if sv >= 80: _bc = "#16a34a"
        elif sv >= 60: _bc = "#22c55e"
        elif sv >= 40: _bc = "#f59e0b"
        elif sv >= 20: _bc = "#ef4444"
        else: _bc = "#991b1b"
        _sc_cls = "sc-high" if sv >= 80 else "sc-good" if sv >= 60 else "sc-mid" if sv >= 40 else "sc-low" if sv >= 20 else "sc-crit"
        signals_breakdown_html += (
            f'<div class="breakdown-item">'
            f'<span class="breakdown-label">{sig_name}</span>'
            f'<div class="breakdown-bar"><div class="breakdown-fill" style="width:{sv:.0f}%;background:{_bc}"></div></div>'
            f'<span class="breakdown-val {_sc_cls}">{sig_val}</span>'
            f'</div>'
        )

    # Key findings with icons (new design)
    why_this_score_findings = ""
    for bullet in _why_bullets:
        # Convert <li>...</li> to finding divs
        text_content = bullet.replace("<li>", "").replace("</li>", "").strip()
        # Determine icon based on content
        if "strong" in text_content or "well-documented" in text_content or "actively" in text_content:
            icon_cls = "finding-good"
            icon = "&#10003;"
        elif "weak" in text_content or "limited" in text_content or "low" in text_content:
            icon_cls = "finding-bad"
            icon = "&#10007;"
        else:
            icon_cls = "finding-warn"
            icon = "&#9888;"
        why_this_score_findings += f'<div class="finding {icon_cls}"><span class="finding-icon">{icon}</span><span>{text_content}</span></div>'

    # Cross-links HTML (pill buttons to all patterns for this entity)
    _cl_slug = _esc(slug)
    # Best-category link based on registry
    _best_map = {
        "npm": "npm-packages", "pypi": "python-packages", "crates": "best-rust-crates",
        "vpn": "vpn", "wordpress": "best-wordpress-plugins", "vscode": "best-vscode-extensions",
        "chrome": "chrome-extensions", "steam": "safest-games", "ios": "safest-apps",
        "android": "safest-apps", "firefox": "best-firefox-addons",
    }
    _best_slug = _best_map.get(source, "coding")

    # Compare links with top alternative
    _compare_links = ""
    if alternatives:
        _alt_slug = alternatives[0].get("slug") or _make_slug(alternatives[0]["name"])
        _compare_links = f'<a href="/compare/{_cl_slug}-vs-{_esc(_alt_slug)}" class="cross-link">Compare</a>'

    cross_links_html = "".join([
        f'<a href="/is-{_cl_slug}-safe" class="cross-link">{_t("cross_safety", lang)}</a>',
        f'<a href="/is-{_cl_slug}-legit" class="cross-link">{_t("cross_legit", lang)}</a>',
        f'<a href="/is-{_cl_slug}-a-scam" class="cross-link">{_t("cross_scam", lang)}</a>',
        f'<a href="/privacy/{_cl_slug}" class="cross-link">{_t("cross_privacy", lang)}</a>',
        f'<a href="/review/{_cl_slug}" class="cross-link">{_t("cross_review", lang)}</a>',
        f'<a href="/pros-cons/{_cl_slug}" class="cross-link">{_t("cross_pros_cons", lang)}</a>',
        f'<a href="/is-{_cl_slug}-safe-for-kids" class="cross-link">{_t("cross_safe_kids", lang)}</a>',
        f'<a href="/alternatives/{_cl_slug}" class="cross-link">{_t("cross_alternatives", lang)}</a>',
        _compare_links,
        f'<a href="/best/{_best_slug}" class="cross-link">{_t("cross_best_category", lang)}</a>',
        f'<a href="/who-owns/{_cl_slug}" class="cross-link">{_t("cross_who_owns", lang)}</a>',
        f'<a href="/what-is/{_cl_slug}" class="cross-link">{_t("cross_what_is", lang)}</a>',
        f'<a href="/does-{_cl_slug}-sell-your-data" class="cross-link">{_t("cross_sells_data", lang)}</a>',
        f'<a href="/was-{_cl_slug}-hacked" class="cross-link">{_t("cross_hacked", lang)}</a>',
    ])

    # ── Enriched-entity sections (L1 Kings Unlock 2026-04-18) ──
    # Kings always render. Non-Kings render iff:
    #   1) source is not in _L1_UNLOCK_SKIP_REGISTRIES (those keep their own
    #      rich templates and would duplicate), AND
    #   2) the module-level _L1_UNLOCK_ALLOWLIST names this source explicitly,
    #      OR the allowlist contains the "*"/"all" wildcard (full rollout).
    # Fail-closed: an empty allowlist leaves non-Kings on pre-unlock behaviour.
    king_sections = ""
    _is_king = agent.get("is_king", False)
    _L1_UNLOCK_SKIP_REGISTRIES = {"city", "charity", "ingredient", "supplement",
                                  "cosmetic_ingredient", "vpn", "country"}
    _unlock_eligible = (
        source not in _L1_UNLOCK_SKIP_REGISTRIES
        and (_L1_UNLOCK_ALL or source in _L1_UNLOCK_ALLOWLIST)
    )
    _render_king_sections = _is_king or _unlock_eligible
    _dims: list = []
    if _render_king_sections:
        _dn_k = _esc(display_name)
        _today_k = datetime.now().strftime("%B %d, %Y")
        _desc = description or ""
        _dl = agent.get("downloads") or agent.get("weekly_downloads") or 0
        _lic = agent.get("license") or ""
        _sec = security_score
        _pop = popularity_score

        # Honest null tracking — no synthetic fallbacks for non-Kings.
        # Privacy-analysis block is wrapped in _has_privacy_score below and
        # falls back to a "not yet available" disclaimer when missing.
        _privacy_score = agent.get("privacy_score")
        _has_privacy_score = _privacy_score is not None
        _jurisdiction = agent.get("jurisdiction")
        _has_audit = agent.get("has_independent_audit", False) or ("audit" in _desc.lower())
        _tracker_count = agent.get("tracker_count")

        # -1. Dependency Graph (T005). Rendered above Block 2a when
        # L2_BLOCK_2B_REGISTRIES names `source` (or is "*"/"all").
        # Fail-closed empty = disabled. Reverse-dep counts and
        # trust-score averages are Nerq-exclusive data; leading with
        # them establishes differentiation before External Trust
        # Signals' independent-verification evidence.
        king_sections += _l2_block_2b_registry_html(slug, source)

        # -0.5. Signal Timeline (T006). Rendered between Block 2b and
        # Block 2a when L2_BLOCK_2C_REGISTRIES names `source` (or is
        # "*"/"all"). Fail-closed empty = disabled. Reads
        # public.signal_events on Nerq RO and surfaces the last three
        # meaningful trust-score moves — a scarce, high-citation-value
        # surface that an LLM is far more likely to quote than a static
        # score.
        king_sections += _l2_block_2c_registry_html(slug, source)

        # 0. External Trust Signals (T004). Rendered above the score
        # breakdown when L2_BLOCK_2A_REGISTRIES names `source` (or is
        # "*"/"all"). Fail-closed empty = disabled. Deliberately placed
        # above Detailed Score Analysis so independent-verification
        # evidence leads the citable prose.
        king_sections += _l2_block_2a_registry_html(slug, source)

        # 1. Detailed Score Analysis — 5 dims populated for every enriched entity.
        _maintenance_score = agent.get("maintenance_score") or activity_score
        _quality_score = agent.get("quality_score")
        _community_score = agent.get("community_score")
        _dims = [
            ("Security", _sec),
            ("Maintenance", _maintenance_score),
            ("Popularity", _pop),
            ("Quality", _quality_score),
            ("Community", _community_score),
        ]
        _breakdown_rows = ""
        for dim_name, dim_score in _dims:
            if dim_score is not None:
                _ds = float(dim_score)
                _dc = "#16a34a" if _ds >= 70 else "#f59e0b" if _ds >= 40 else "#dc2626"
                _breakdown_rows += f'<tr><td>{dim_name}</td><td style="text-align:right;color:{_dc};font-weight:600">{_ds:.0f}/100</td></tr>'
        if _breakdown_rows:
            king_sections += f"""<div class="section">
<h2 class="section-title">{_t("detailed_score_analysis", lang)}</h2>
<table><thead><tr><th>{_t("dimension_label", lang)}</th><th style="text-align:right">{_t("score_label", lang)}</th></tr></thead>
<tbody>{_breakdown_rows}</tbody></table>
<p style="font-size:12px;color:#94a3b8;margin-top:6px">Based on {len([d for d in _dims if d[1] is not None])} dimensions. Data from {_rp.get('data_sources', 'multiple sources')}.</p>
</div>"""

        # 2. Privacy Analysis — guarded with has_real_data (L1 Kings Unlock 2026-04-18).
        # When privacy_score is null we render a short "not yet available"
        # disclaimer pointing to /methodology rather than synthesising numbers.
        _data_heading = _t("is_safe_visit", lang, name=_dn_k) if source == "country" else _t("is_legit_charity", lang, name=_dn_k) if source == "charity" else _t("what_data_collect", lang, name=_dn_k)
        if not _has_privacy_score:
            king_sections += f"""<div class="section">
<h2 class="section-title">{_data_heading}</h2>
<p style="font-size:15px;line-height:1.7;color:#374151">Privacy assessment for {_dn_k} is not yet available. See our <a href="/methodology">methodology</a> for how Nerq measures privacy, or the <a href="/safe/{_esc(slug)}/privacy">public privacy review</a> for any community-contributed notes.</p>
</div>"""
        else:
            import re as _re
            _priv_p = []
            _ext_cite = []
            if source == "vpn":
                _jur = _jurisdiction or "undisclosed"
                if not _jurisdiction:
                    _m = _re.search(r'(\w+)\s+jurisdiction', _desc, _re.I)
                    if _m: _jur = _m.group(1)
                _servers = ""
                _m = _re.search(r'(\d[\d,]*)\s+servers?\s+in\s+(\d+)\s+countries', _desc, _re.I)
                if _m: _servers = f"{_m.group(1)} servers across {_m.group(2)} countries"
                _five_eyes = _jur.lower() in ('panama','bvi','gibraltar','switzerland','sweden','romania','isle of man','finland')
                _eyes_text = _t("vpn_outside_eyes", lang) if _five_eyes else ""
                _priv_p.append(f"{_dn_k} {_t('vpn_operates_under', lang)} <b>{_esc(_jur)}</b> {_t('vpn_jurisdiction', lang)}{(' — ' + _eyes_text) if _eyes_text else ''}. {_t('vpn_significant', lang)}")
                if _servers: _priv_p.append(f"{_t('vpn_server_infra', lang)}: {_servers}.")
                if _has_audit:
                    _priv_p.append(f"{_t('vpn_logging_audited', lang, name=_dn_k)}")
                    _ext_cite.append(f"Independent audit confirms {_dn_k} no-logs policy.")
                else:
                    _priv_p.append("Logging policy: claims no-logs but no independent audit has been published to verify this claim.")
                _priv_p.append(f"{_t('privacy_score_label', lang)}: <b>{_privacy_score:.0f}/100</b>.")
            elif source in ("ios", "android"):
                _store = "App Store" if source == "ios" else "Google Play"
                _priv_p.append(f"{_dn_k} is published by {_esc(author)} on {_store}{f', with approximately {_dl:,} downloads' if _dl else ''}.")
                _priv_p.append(f"Privacy score: <b>{_privacy_score:.0f}/100</b>. Users should review the app's privacy labels (available on the {_store} listing) to understand what data categories are collected, including identifiers, usage data, and location information.")
                _priv_p.append(f"Before granting permissions, check whether the app requests access to camera, microphone, contacts, or location — and whether each permission is necessary for the app's core functionality.")
            elif source in ("npm", "pypi", "crates", "go", "gems", "packagist"):
                _priv_p.append(f"{_dn_k} is a {_entity_word} maintained by {_esc(author)}.{f' It receives approximately {_dl:,} weekly downloads.' if _dl else ''}{f' Licensed under {_esc(_lic)}.' if _lic else ''}")
                _priv_p.append(f"As a development package, {_dn_k} does not directly collect end-user personal data. However, applications built with it may collect data depending on implementation. Privacy score: <b>{_privacy_score:.0f}/100</b>.")
                _priv_p.append("Review the package's dependencies for potential supply chain risks. Run your package manager's audit command regularly.")
            elif source == "saas":
                _priv_p.append(f"{_dn_k} is a {_entity_word}. {_esc(_desc[:250])}")
                _priv_p.append(f"Privacy score: <b>{_privacy_score:.0f}/100</b>. As a SaaS platform, {_dn_k} processes user data in the cloud. Review the privacy policy for details on data retention, third-party sharing, and data processing locations.")
                _priv_p.append("For business use, request a Data Processing Agreement (DPA) and verify GDPR compliance before uploading sensitive data.")
            elif source == "ai_tool":
                _priv_p.append(f"{_dn_k} is an AI tool. {_esc(_desc[:250])}")
                _priv_p.append(f"Privacy score: <b>{_privacy_score:.0f}/100</b>. AI tools may use inputs for model improvement unless explicitly opted out. Check the data usage policy before sharing confidential information, code, or personal data.")
                _priv_p.append("Consider whether the tool offers enterprise plans with data isolation, SOC 2 compliance, or on-premise deployment options.")
            elif source == "website":
                _priv_p.append(f"{_dn_k}: {_esc(_desc[:250])}")
                _priv_p.append(f"Privacy score: <b>{_privacy_score:.0f}/100</b>. Review the privacy policy for data collection practices, cookie usage, and third-party tracking. Check for HTTPS encryption and transparent data handling.")
            else:
                _priv_p.append(f"{_dn_k} has a privacy score of <b>{_privacy_score:.0f}/100</b>. Review the documentation and privacy policy for data handling details.")

            _priv_html = "".join(f'<p style="font-size:15px;line-height:1.7;color:#374151;margin-bottom:8px">{p}</p>' for p in _priv_p)
            king_sections += f"""<div class="section">
<h2 class="section-title">{_data_heading}</h2>
{_priv_html}
<p style="font-size:14px;color:#64748b">{_t("full_analysis", lang)} <a href="/safe/{_esc(slug)}/privacy">{_t("privacy_report", lang, name=_dn_k)}</a> · <a href="/privacy/{_esc(slug)}">Privacy review</a></p>
</div>"""

        # 3. Security Assessment — expanded
        _sec_p = []
        _sec_val = f"{_sec:.0f}/100" if _sec is not None else "under assessment"
        if source == "vpn":
            _proto = ""
            if "wireguard" in _desc.lower(): _proto = "WireGuard"
            elif "openvpn" in _desc.lower(): _proto = "OpenVPN"
            _proto_text = (" " + _t("vpn_proto", lang).format(proto=_proto)) if _proto else ""
            _sec_p.append(f"{_t('vpn_sec_score', lang)}: <b>{_sec_val}</b>.{_proto_text}")
            if _has_audit:
                _sec_p.append(_t("vpn_audit_positive", lang, name=_dn_k))
                _ext_cite.append(_t("vpn_audit_verified", lang))
            else:
                _sec_p.append(_t("vpn_audit_none", lang, name=_dn_k))
            _sec_p.append(_t("vpn_no_breaches", lang))
        elif source in ("npm", "pypi", "crates"):
            _cve = agent.get("cve_count") or 0
            _sec_p.append(f"Security score: <b>{_sec_val}</b>. {_dn_k} has {_cve} known vulnerabilities (CVEs) in the National Vulnerability Database.{' This is a clean record.' if _cve == 0 else ' Review advisories and update to the latest version.'}")
            _sec_p.append(f"{'Licensed under ' + _esc(_lic) + ', allowing code inspection.' if _lic else 'License information not available.'} Open-source packages allow independent security review of the source code.")
            _sec_p.append("Run your package manager's audit command (`npm audit`, `pip audit`, `cargo audit`) to check for known vulnerabilities in your dependency tree.")
        elif source in ("saas", "ai_tool"):
            _sec_p.append(f"Security score: <b>{_sec_val}</b>. {_esc(_desc[:150])}")
            _sec_p.append(f"Check {_dn_k}'s security page for certifications such as SOC 2 Type II, ISO 27001, or GDPR compliance documentation. These certifications indicate that the vendor follows established security practices and undergoes regular audits.")
            _sec_p.append("For enterprise deployments, verify SSO/SAML support, role-based access control, and audit logging capabilities.")
        else:
            _sec_p.append(f"Security score: <b>{_sec_val}</b>. {'This meets the recommended security threshold for production use.' if _sec and _sec >= 70 else 'Review security practices and consider alternatives with higher security scores for sensitive use cases.'}")
            _sec_p.append("Nerq monitors this entity against NVD, OSV.dev, and registry-specific vulnerability databases for ongoing security assessment.")

        _sec_html = "".join(f'<p style="font-size:15px;line-height:1.7;color:#374151;margin-bottom:8px">{p}</p>' for p in _sec_p)
        _sec_heading = _t("crime_safety", lang, name=_dn_k) if source == "country" else _t("financial_transparency", lang, name=_dn_k) if source == "charity" else _t("is_secure", lang, name=_dn_k)
        king_sections += f"""<div class="section">
<h2 class="section-title">{_sec_heading}</h2>
{_sec_html}
<p style="font-size:14px;color:#64748b">{_t("full_analysis", lang)} <a href="/safe/{_esc(slug)}/security">{_t("security_report", lang, name=_dn_k)}</a></p>
</div>"""

        # 4. Cross-product trust map
        if cross_products:
            _cp_items = ""
            for cp in cross_products[:4]:
                _cp_slug = _make_slug(cp["name"])
                _cp_items += f'<a href="/safe/{_esc(_cp_slug)}" style="display:inline-block;padding:6px 14px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;text-decoration:none;color:#374151;margin:3px">{_esc(cp["name"])} <span style="color:#64748b">({cp["registry"]}, {cp.get("trust_score", 0):.0f}/100)</span></a>'
            king_sections += f"""<div class="section">
<h2 class="section-title">{_t("across_platforms", lang, name=_dn_k)}</h2>
<p style="font-size:14px;color:#64748b;margin-bottom:8px">{_t("same_developer", lang)}</p>
<div style="display:flex;flex-wrap:wrap;gap:4px">{_cp_items}</div>
</div>"""

        # 5. Methodology — expanded with dimension weights
        _dim_list = ", ".join(f'{d[0].lower()} ({d[1]:.0f}/100)' for d in _dims if d[1] is not None)
        _n_dims = len([d for d in _dims if d[1] is not None])
        _n_sources = _rp.get("data_sources", "multiple public sources")
        king_sections += f"""<div class="section">
<h2 class="section-title">{_t("how_calculated", lang)}</h2>
<p style="font-size:15px;line-height:1.7;color:#374151">{_dn_k}'s trust score of <b>{score_str}/100</b> ({_esc(grade)}) is computed from {_n_sources}. The score reflects {_n_dims} independent dimensions: {_dim_list}. Each dimension is weighted equally to produce the composite trust score.</p>
<p style="font-size:15px;line-height:1.7;color:#374151">Nerq analyzes over 7.5 million entities across 26 registries using the same methodology, enabling direct cross-entity comparison. Scores are updated continuously as new data becomes available.</p>
<p style="font-size:15px;line-height:1.7;color:#374151">This page was last reviewed on <b>{_today_k}</b>. Data version: {agent.get('king_version', 1)}.0.</p>
<p style="font-size:14px;color:#64748b"><a href="/methodology">Full methodology documentation</a> · <a href="/v1/preflight?target={_esc(name)}">Machine-readable data (JSON API)</a></p>
</div>"""

    # ── VPN-specific details (only for registry=vpn) ──
    vpn_details = ""
    if source in ("vpn",):
        _juris = agent.get("jurisdiction", "")
        _audited = agent.get("has_independent_audit", False)
        _priv = agent.get("privacy_score")
        _trans = agent.get("transparency_score")
        _dl = agent.get("downloads") or 0

        _five_eyes = {"usa", "uk", "canada", "australia", "new zealand"}
        _nine_eyes = _five_eyes | {"denmark", "france", "netherlands", "norway"}
        _fourteen = _nine_eyes | {"germany", "belgium", "italy", "sweden", "spain"}
        _juris_lower = _juris.lower() if _juris else ""

        _eyes_text = ""
        if _juris_lower in _five_eyes:
            _eyes_text = _t("eyes_five", lang)
        elif _juris_lower in _nine_eyes:
            _eyes_text = _t("eyes_nine", lang)
        elif _juris_lower in _fourteen:
            _eyes_text = _t("eyes_fourteen", lang)
        elif _juris_lower in ("panama", "british virgin islands", "bvi", "gibraltar", "seychelles", "cayman islands"):
            _eyes_text = _t("eyes_outside", lang)
        elif _juris_lower:
            _eyes_text = _t("eyes_none", lang)

        _audit_text = _t("audit_yes", lang, name=_esc(display_name)) if _audited else _t("audit_no", lang, name=_esc(display_name))

        _priv_bar = f'<div style="margin:8px 0"><span style="font-size:13px;color:#64748b">Privacy Score</span> <strong>{_priv:.0f}</strong>/100 <div style="background:#e2e8f0;height:6px;border-radius:3px;margin-top:4px"><div style="background:{"#16a34a" if _priv >= 70 else "#d97706" if _priv >= 50 else "#dc2626"};height:6px;border-radius:3px;width:{_priv}%"></div></div></div>' if _priv else ""
        _trans_bar = f'<div style="margin:8px 0"><span style="font-size:13px;color:#64748b">Transparency Score</span> <strong>{_trans:.0f}</strong>/100 <div style="background:#e2e8f0;height:6px;border-radius:3px;margin-top:4px"><div style="background:{"#16a34a" if _trans >= 70 else "#d97706" if _trans >= 50 else "#dc2626"};height:6px;border-radius:3px;width:{_trans}%"></div></div></div>' if _trans else ""

        vpn_details = f'''<div class="section vpn-details" style="margin:20px 0;padding:20px;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc">
<h2 style="font-size:1.15em;font-weight:600;margin:0 0 12px">{_t("privacy_assessment", lang)}</h2>
<p style="font-size:15px;line-height:1.7;color:#334155;margin:0 0 12px">{_esc(display_name)} {_t("vpn_operates_under", lang)} <strong>{_esc(_juris) if _juris else _t("undisclosed_jurisdiction", lang)}</strong>{(", " + _eyes_text) if _eyes_text else ""}. {_audit_text}.</p>
{_priv_bar}{_trans_bar}
{"<p style='font-size:13px;color:#64748b;margin:8px 0 0'>" + _t("serving_users", lang) + " " + f'{_dl:,}' + "+</p>" if _dl > 100000 else ""}
</div>'''

    # ── Password Manager-specific details ──
    if source == "password_manager":
        _pm_desc = (agent.get("description") or "").lower()
        _pm_juris = agent.get("jurisdiction") or "Unknown"
        _pm_audited = agent.get("has_independent_audit", False)
        _pm_stars = agent.get("stars") or 0
        _pm_sec = agent.get("security_score")
        _pm_priv = agent.get("privacy_score")

        _breach_texts = {
            "lastpass-pm": "LastPass suffered major data breaches in August and December 2022. Encrypted vault data and customer information were stolen. While master passwords were not directly compromised, the stolen encrypted vaults remain vulnerable to brute-force attacks for users with weak master passwords.",
            "norton-password-manager-pm": "Norton Password Manager was affected by a credential stuffing attack in December 2022.",
            "norton-pm": "Norton was affected by a credential stuffing attack in December 2022.",
        }
        _breach_html = ""
        _slug_key = agent.get("slug") or slug
        _breach_key = _slug_key if _slug_key in _breach_texts else (f"{_slug_key}-pm" if f"{_slug_key}-pm" in _breach_texts else _slug_key)
        if _breach_key in _breach_texts:
            _breach_html = f'<div style="margin:10px 0"><h3 style="color:#dc2626;font-size:1em;margin:0 0 6px">Breach History</h3><p style="font-size:14px;line-height:1.6;color:#334155">{_breach_texts[_breach_key]}</p></div>'
        elif _pm_audited:
            _breach_html = f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Breach History</h3><p style="font-size:14px;color:#334155">{_esc(display_name)} has no known data breaches and has been independently audited.</p></div>'

        # Encryption detection — check description + known facts
        _enc_items = []
        _pm_enc_known = {
            "bitwarden-pm": [("AES-256-CBC", "industry standard"), ("Argon2id", "brute-force resistant key derivation")],
            "1password-pm": [("AES-256-GCM", "authenticated encryption"), ("Argon2id", "brute-force resistant key derivation")],
            "keepass-pm": [("AES-256", "industry standard"), ("ChaCha20", "modern stream cipher"), ("Argon2d", "key derivation")],
            "keepassxc-pm": [("AES-256", "industry standard"), ("ChaCha20", "modern stream cipher"), ("Argon2id", "key derivation")],
            "proton-pass-pm": [("AES-256-GCM", "authenticated encryption"), ("Argon2", "key derivation"), ("SRP", "zero-knowledge authentication")],
            "dashlane-pm": [("AES-256", "industry standard"), ("Argon2d", "key derivation")],
            "nordpass-pm": [("XChaCha20", "modern high-performance cipher"), ("Argon2id", "key derivation")],
            "lastpass-pm": [("AES-256-CBC", "industry standard"), ("PBKDF2-SHA256", "key derivation")],
            "keeper-pm": [("AES-256", "industry standard"), ("PBKDF2-HMAC-SHA512", "key derivation")],
            "roboform-pm": [("AES-256", "industry standard"), ("PBKDF2", "key derivation")],
            "enpass-pm": [("AES-256", "industry standard"), ("SQLCipher", "database encryption")],
        }
        _slug_key = agent.get("slug") or slug
        # Try both the exact slug and with -pm suffix (consumer overrides like /safe/bitwarden)
        _pm_key = _slug_key if _slug_key in _pm_enc_known else (f"{_slug_key}-pm" if f"{_slug_key}-pm" in _pm_enc_known else _slug_key)
        if _pm_key in _pm_enc_known:
            _enc_items = [f"{algo} ({note})" for algo, note in _pm_enc_known[_pm_key]]
        else:
            if 'xchacha20' in _pm_desc: _enc_items.append('XChaCha20 (modern, high-performance)')
            elif 'aes-256' in _pm_desc or 'aes256' in _pm_desc: _enc_items.append('AES-256 (industry standard)')
            elif 'encryption' in _pm_desc: _enc_items.append('Encrypted storage')
            if 'argon2' in _pm_desc: _enc_items.append('Argon2 key derivation (brute-force resistant)')
            elif 'pbkdf2' in _pm_desc: _enc_items.append('PBKDF2 key derivation')
        _enc_html = f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Encryption</h3><p style="font-size:14px;color:#334155">{_esc(display_name)} uses {", ".join(_enc_items)}.</p></div>' if _enc_items else ""

        _oss_html = f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Open Source</h3><p style="font-size:14px;color:#334155">{_esc(display_name)} is open source with {_pm_stars:,} GitHub stars.</p></div>' if _pm_stars > 0 else ""

        # Zero-knowledge architecture note
        _zk_known = {"bitwarden-pm", "1password-pm", "proton-pass-pm", "keepass-pm", "keepassxc-pm", "nordpass-pm", "dashlane-pm"}
        _zk_html = f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Zero-Knowledge Architecture</h3><p style="font-size:14px;color:#334155">{_esc(display_name)} uses a zero-knowledge architecture — your master password and vault data are encrypted locally and never sent to the server in plaintext.</p></div>' if (_pm_key in _zk_known) else ""

        _sec_bar = f'<div style="margin:8px 0"><span style="font-size:13px;color:#64748b">Security</span> <strong>{_pm_sec:.0f}</strong>/100 <div style="background:#e2e8f0;height:6px;border-radius:3px;margin-top:4px"><div style="background:{"#16a34a" if _pm_sec >= 70 else "#d97706" if _pm_sec >= 50 else "#dc2626"};height:6px;border-radius:3px;width:{_pm_sec}%"></div></div></div>' if _pm_sec else ""

        vpn_details = f'''<div class="section vpn-details" style="margin:20px 0;padding:20px;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc">
<h2 style="font-size:1.15em;font-weight:600;margin:0 0 12px">Security Assessment</h2>
{_breach_html}{_enc_html}{_zk_html}{_oss_html}{_sec_bar}
<p style="font-size:14px;color:#334155;margin:8px 0">Based in <strong>{_esc(_pm_juris)}</strong>. {"Independently audited." if _pm_audited else "No published independent audit."}</p>
</div>'''

    # ── Hosting-specific details ──
    if source == "hosting":
        _h_desc = (agent.get("description") or "").lower()
        _h_juris = agent.get("jurisdiction") or "Unknown"
        _h_audited = agent.get("has_independent_audit", False)
        _h_dl = agent.get("downloads") or 0
        _h_slug = agent.get("slug") or slug

        _HOSTING_BREACHES = {
            "godaddy-hosting": "GoDaddy experienced a major data breach in November 2021 that exposed 1.2 million WordPress customer email addresses and passwords. Additional breaches were disclosed in 2022 and 2023, suggesting ongoing security challenges.",
        }

        # Infrastructure
        _infra = []
        if 'google cloud' in _h_desc: _infra.append('Google Cloud Platform')
        if 'aws' in _h_desc or 'amazon web services' in _h_desc: _infra.append('Amazon Web Services')
        if 'akamai' in _h_desc: _infra.append("Akamai's global network")
        if 'own data centers' in _h_desc or 'operates own' in _h_desc: _infra.append('Own data centers')
        if 'cloudflare' in _h_desc and 'cdn' in _h_desc: _infra.append('Cloudflare CDN')
        _infra_html = f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Infrastructure</h3><p style="font-size:14px;color:#334155">{_esc(display_name)} runs on {", ".join(_infra)}.</p></div>' if _infra else ""

        # Security & Compliance
        _sec_items = []
        if _h_audited: _sec_items.append('SOC 2 certified')
        if 'hipaa' in _h_desc: _sec_items.append('HIPAA compliant')
        if 'iso 27001' in _h_desc: _sec_items.append('ISO 27001 certified')
        if 'waf' in _h_desc: _sec_items.append('Web Application Firewall')
        if 'ddos' in _h_desc: _sec_items.append('DDoS protection')
        _sec_html = f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Security & Compliance</h3><p style="font-size:14px;color:#334155">{_esc(display_name)}: {", ".join(_sec_items)}.</p></div>' if _sec_items else ""

        # Breach history — check both URL slug and DB slug with -hosting suffix
        _h_breach_html = ""
        _h_breach_key = _h_slug if _h_slug in _HOSTING_BREACHES else (f"{_h_slug}-hosting" if f"{_h_slug}-hosting" in _HOSTING_BREACHES else _h_slug)
        if _h_breach_key in _HOSTING_BREACHES:
            _h_breach_html = f'<div style="margin:10px 0"><h3 style="color:#dc2626;font-size:1em;margin:0 0 6px">Security Incidents</h3><p style="font-size:14px;line-height:1.6;color:#334155">{_HOSTING_BREACHES[_h_breach_key]}</p></div>'
        elif _h_audited:
            _h_breach_html = f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Security Track Record</h3><p style="font-size:14px;color:#334155">{_esc(display_name)} has no known major data breaches and maintains independent security certification.</p></div>'

        # Data location / GDPR
        _eu_countries = {'germany', 'finland', 'bulgaria', 'lithuania', 'czech republic', 'netherlands', 'france', 'sweden', 'ireland'}
        _gdpr_html = ""
        if _h_juris.lower() in _eu_countries:
            _gdpr_html = f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Data Location & GDPR</h3><p style="font-size:14px;color:#334155">{_esc(display_name)} is based in {_esc(_h_juris)}, within the EU. Data stored in EU data centers is subject to GDPR protection — relevant for businesses with European customers.</p></div>'

        # Scale
        _scale_html = ""
        if _h_dl > 1_000_000:
            _scale_html = f'<p style="font-size:13px;color:#64748b;margin:8px 0 0">Serving {_h_dl:,}+ websites</p>'

        vpn_details = f'''<div class="section vpn-details" style="margin:20px 0;padding:20px;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc">
<h2 style="font-size:1.15em;font-weight:600;margin:0 0 12px">Hosting Assessment</h2>
{_infra_html}{_sec_html}{_h_breach_html}{_gdpr_html}
<p style="font-size:14px;color:#334155;margin:8px 0">Based in <strong>{_esc(_h_juris)}</strong>. {"Independently audited." if _h_audited else "No published independent audit."}</p>
{_scale_html}
</div>'''

    # ── Antivirus-specific details ──
    if source == "antivirus":
        _av_desc = (agent.get("description") or "").lower()
        _av_juris = agent.get("jurisdiction") or "Unknown"
        _av_slug = agent.get("slug") or slug

        _AV_TEST_P = {'norton-360': 6.0, 'bitdefender': 6.0, 'kaspersky': 6.0, 'mcafee': 6.0,
                      'malwarebytes': 6.0, 'eset': 6.0, 'avast': 6.0, 'windows-defender': 6.0,
                      'trend-micro': 6.0, 'f-secure': 6.0, 'avira': 6.0, 'panda-security': 5.5,
                      'g-data': 6.0, 'k7-security': 6.0, 'ahnlab': 6.0}
        _AV_TEST_PF = {'norton-360': 5.5, 'bitdefender': 6.0, 'kaspersky': 6.0, 'mcafee': 5.5,
                       'malwarebytes': 5.5, 'eset': 6.0, 'avast': 5.5, 'windows-defender': 5.5,
                       'trend-micro': 5.5, 'f-secure': 5.5, 'avira': 5.5, 'panda-security': 6.0}

        _av_sections = []

        # AV-TEST results
        _av_key = _av_slug if _av_slug in _AV_TEST_P else (slug if slug in _AV_TEST_P else None)
        if _av_key:
            _prot = _AV_TEST_P[_av_key]
            _perf = _AV_TEST_PF.get(_av_key, 0)
            _prot_note = "Perfect protection score." if _prot >= 6.0 else "Near-perfect protection."
            _perf_note = "" if _perf >= 6.0 else " Slightly higher system impact than top performers."
            _av_sections.append(f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Independent Lab Results (AV-TEST)</h3><p style="font-size:14px;line-height:1.6;color:#334155">{_esc(display_name)} scored <strong>{_prot}/6</strong> on protection and <strong>{_perf}/6</strong> on performance in AV-TEST independent testing. {_prot_note}{_perf_note}</p></div>')

        # Incident/scandal content
        _AV_INCIDENTS = {
            'avast': '<div style="margin:10px 0"><h3 style="color:#dc2626;font-size:1em;margin:0 0 6px">Privacy Incident: Jumpshot Scandal</h3><p style="font-size:14px;line-height:1.6;color:#334155">In 2020, Avast subsidiary Jumpshot was found selling detailed browsing data from approximately 100 million users to third parties including Google, Microsoft, and hedge funds. Jumpshot was shut down after the exposure. Avast has since reformed data practices under new Gen Digital ownership.</p></div>',
            'kaspersky': '<div style="margin:10px 0"><h3 style="color:#dc2626;font-size:1em;margin:0 0 6px">Jurisdiction Concern: Russia &amp; US Ban</h3><p style="font-size:14px;line-height:1.6;color:#334155">Kaspersky is headquartered in Moscow, Russia. US government agencies have been banned from using Kaspersky products since 2017 due to national security concerns. In 2024, the US Commerce Department banned Kaspersky software sales in the US entirely. Kaspersky moved some data processing to Switzerland in 2018 through its Global Transparency Initiative, but concerns remain.</p></div>',
            'norton-360': '<div style="margin:10px 0"><h3 style="color:#d97706;font-size:1em;margin:0 0 6px">Security Incident: Credential Stuffing (2022)</h3><p style="font-size:14px;line-height:1.6;color:#334155">In December 2022, Norton reported that approximately 925,000 Norton Password Manager accounts were targeted in a credential stuffing attack. No Norton systems were breached — attackers used previously leaked credentials from other sites to access accounts with reused passwords.</p></div>',
            'crowdstrike': '<div style="margin:10px 0"><h3 style="color:#dc2626;font-size:1em;margin:0 0 6px">Global IT Outage (July 2024)</h3><p style="font-size:14px;line-height:1.6;color:#334155">On July 19, 2024, a faulty CrowdStrike Falcon content update caused a worldwide IT outage affecting approximately 8.5 million Windows devices. Airlines grounded flights, hospitals postponed procedures, and banks experienced disruptions. CrowdStrike has since implemented additional testing safeguards and a phased rollout process for content updates.</p></div>',
        }
        _inc_key = _av_slug if _av_slug in _AV_INCIDENTS else (slug if slug in _AV_INCIDENTS else None)
        if _inc_key:
            _av_sections.append(_AV_INCIDENTS[_inc_key])
        else:
            _av_sections.append(f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Security Track Record</h3><p style="font-size:14px;color:#334155">{_esc(display_name)} has no known major security incidents or privacy scandals.</p></div>')

        # Jurisdiction
        _eu_av = {'romania', 'finland', 'slovakia', 'czech republic', 'germany', 'spain', 'netherlands', 'denmark'}
        if _av_juris.lower() in _eu_av:
            _av_sections.append(f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Jurisdiction</h3><p style="font-size:14px;color:#334155">{_esc(display_name)} is based in {_esc(_av_juris)}, within the EU. User data is subject to GDPR protection.</p></div>')
        elif _av_juris.lower() == 'russia':
            _av_sections.append(f'<div style="margin:10px 0"><h3 style="color:#dc2626;font-size:1em;margin:0 0 6px">Jurisdiction: Russia</h3><p style="font-size:14px;color:#334155">{_esc(display_name)} is based in Russia. This has led to government bans in several countries including the United States.</p></div>')

        vpn_details = f'''<div class="section vpn-details" style="margin:20px 0;padding:20px;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc">
<h2 style="font-size:1.15em;font-weight:600;margin:0 0 12px">Antivirus Assessment</h2>
{"".join(_av_sections)}
</div>'''

    # ── SaaS-specific details ──
    if source == "saas":
        _saas_desc = (agent.get("description") or "").lower()
        _saas_juris = agent.get("jurisdiction") or "Unknown"
        _saas_audit = agent.get("has_independent_audit", False)
        _saas_stars = agent.get("stars") or 0

        _saas_sections = []

        # Security & compliance certs
        _certs = []
        if 'soc 2' in _saas_desc or 'soc2' in _saas_desc: _certs.append('SOC 2')
        if 'iso 27001' in _saas_desc: _certs.append('ISO 27001')
        if 'hipaa' in _saas_desc: _certs.append('HIPAA')
        if 'fedramp' in _saas_desc: _certs.append('FedRAMP')
        if 'pci' in _saas_desc: _certs.append('PCI DSS')
        if 'gdpr' in _saas_desc: _certs.append('GDPR compliant')
        if _certs:
            _saas_sections.append(f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Security & Compliance</h3><p style="font-size:14px;color:#334155">{_esc(display_name)} holds: {", ".join(_certs)}.</p></div>')

        # Open source
        if _saas_stars > 100:
            _saas_sections.append(f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Open Source</h3><p style="font-size:14px;color:#334155">{_esc(display_name)} is open source with {_saas_stars:,} GitHub stars.</p></div>')

        # Incidents
        _SAAS_INC = {
            'zoom': 'Zoom faced security concerns in 2020 including "Zoombombing" and routing through Chinese servers. Has since implemented end-to-end encryption and improved security controls.',
            'slack': 'In 2023, Slack disclosed that employee tokens were stolen via a compromised GitHub repository. No customer data was affected.',
        }
        _saas_slug = agent.get("slug") or slug
        if _saas_slug in _SAAS_INC:
            _saas_sections.append(f'<div style="margin:10px 0"><h3 style="color:#d97706;font-size:1em;margin:0 0 6px">Security History</h3><p style="font-size:14px;line-height:1.6;color:#334155">{_SAAS_INC[_saas_slug]}</p></div>')
        elif _saas_audit:
            _saas_sections.append(f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Security Track Record</h3><p style="font-size:14px;color:#334155">{_esc(display_name)} has no known major security incidents and maintains independent security certification.</p></div>')

        # Data location
        _eu_saas = {'germany', 'finland', 'sweden', 'switzerland', 'netherlands', 'new zealand', 'australia', 'ireland'}
        if _saas_juris.lower() in _eu_saas:
            _gdpr_note = " EU data protection laws (GDPR) apply." if _saas_juris.lower() in ('germany', 'finland', 'sweden', 'netherlands', 'ireland') else ""
            _saas_sections.append(f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Data Location</h3><p style="font-size:14px;color:#334155">{_esc(display_name)} is based in {_esc(_saas_juris)}.{_gdpr_note}</p></div>')

        if _saas_sections:
            vpn_details = f'''<div class="section vpn-details" style="margin:20px 0;padding:20px;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc">
<h2 style="font-size:1.15em;font-weight:600;margin:0 0 12px">SaaS Assessment</h2>
{"".join(_saas_sections)}
</div>'''

    # ── Website Builder-specific details ──
    if source == "website_builder":
        _wb_desc = (agent.get("description") or "").lower()
        _wb_audit = agent.get("has_independent_audit", False)
        _wb_stars = agent.get("stars") or 0
        _wb_slug = agent.get("slug") or slug
        _wb_sections = []

        # Ecommerce
        if 'ecommerce' in _wb_desc or 'online store' in _wb_desc or 'payment' in _wb_desc:
            _pci = " PCI DSS Level 1 compliant for payment processing." if 'pci' in _wb_desc else ""
            _wb_sections.append(f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Ecommerce</h3><p style="font-size:14px;color:#334155">{_esc(display_name)} includes built-in ecommerce functionality.{_pci}</p></div>')
        # Security
        _certs = []
        if 'soc 2' in _wb_desc: _certs.append('SOC 2')
        if 'pci' in _wb_desc: _certs.append('PCI DSS')
        if 'gdpr' in _wb_desc: _certs.append('GDPR compliant')
        if _certs:
            _wb_sections.append(f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Security & Compliance</h3><p style="font-size:14px;color:#334155">{_esc(display_name)}: {", ".join(_certs)}.</p></div>')
        # Open source
        if _wb_stars > 100:
            _wb_sections.append(f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Open Source</h3><p style="font-size:14px;color:#334155">{_esc(display_name)} is open source with {_wb_stars:,} GitHub stars.</p></div>')
        # Breach
        if 'breach' in _wb_desc or 'data breach' in _wb_desc:
            _wb_sections.append(f'<div style="margin:10px 0"><h3 style="color:#dc2626;font-size:1em;margin:0 0 6px">Security Incident</h3><p style="font-size:14px;color:#334155">The parent company experienced a data breach. This impacts the trust score.</p></div>')
        if _wb_sections:
            vpn_details = f'''<div class="section vpn-details" style="margin:20px 0;padding:20px;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc">
<h2 style="font-size:1.15em;font-weight:600;margin:0 0 12px">Website Builder Assessment</h2>
{"".join(_wb_sections)}
</div>'''

    # ── Crypto Exchange-specific details ──
    if source == "crypto":
        _ex_desc = (agent.get("description") or "").lower()
        _ex_slug = agent.get("slug") or slug
        _EXCHANGE_INC = {
            'binance': '<div style="margin:10px 0"><h3 style="color:#dc2626;font-size:1em;margin:0 0 6px">Regulatory Action: $4.3B DOJ Settlement</h3><p style="font-size:14px;line-height:1.6;color:#334155">In November 2023, Binance paid $4.3 billion in fines to settle US DOJ and SEC charges for anti-money laundering violations. CEO Changpeng Zhao (CZ) stepped down and pleaded guilty.</p></div>',
            'coinbase': '<div style="margin:10px 0"><h3 style="color:#d97706;font-size:1em;margin:0 0 6px">Regulatory: SEC Lawsuit</h3><p style="font-size:14px;line-height:1.6;color:#334155">Coinbase faced an SEC lawsuit in 2023 alleging unregistered securities trading. As a publicly traded company (NASDAQ: COIN), Coinbase provides the highest level of financial transparency of any major crypto exchange.</p></div>',
            'ftx': '<div style="margin:10px 0"><h3 style="color:#dc2626;font-size:1em;margin:0 0 6px">Collapse: $8 Billion Missing</h3><p style="font-size:14px;line-height:1.6;color:#334155">FTX collapsed in November 2022 with approximately $8 billion in customer funds missing. Founder Sam Bankman-Fried was convicted of fraud in 2023 and sentenced to 25 years in prison.</p></div>',
            'kucoin': '<div style="margin:10px 0"><h3 style="color:#dc2626;font-size:1em;margin:0 0 6px">Security & Regulatory Issues</h3><p style="font-size:14px;line-height:1.6;color:#334155">KuCoin was hacked in 2020 for $280 million (most recovered). Indicted by US DOJ in 2024 for anti-money laundering failures. Settled for $297 million.</p></div>',
            'crypto-com': '<div style="margin:10px 0"><h3 style="color:#d97706;font-size:1em;margin:0 0 6px">Security Incident</h3><p style="font-size:14px;line-height:1.6;color:#334155">Crypto.com suffered a $34 million hack in January 2022. Publishes Proof of Reserves audited by Mazars.</p></div>',
            'bybit': '<div style="margin:10px 0"><h3 style="color:#dc2626;font-size:1em;margin:0 0 6px">Major Hack: $1.5 Billion (2025)</h3><p style="font-size:14px;line-height:1.6;color:#334155">In February 2025, Bybit suffered a $1.5 billion hack — the largest crypto exchange hack in history.</p></div>',
        }
        _ex_sections = []
        if _ex_slug in _EXCHANGE_INC:
            _ex_sections.append(_EXCHANGE_INC[_ex_slug])
        if 'proof of reserves' in _ex_desc:
            _ex_sections.append(f'<div style="margin:10px 0"><h3 style="font-size:1em;margin:0 0 6px">Proof of Reserves</h3><p style="font-size:14px;color:#334155">{_esc(display_name)} publishes Proof of Reserves, allowing users to verify the exchange holds sufficient assets.</p></div>')
        if _ex_sections:
            vpn_details = f'''<div class="section vpn-details" style="margin:20px 0;padding:20px;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc">
<h2 style="font-size:1.15em;font-weight:600;margin:0 0 12px">Exchange Assessment</h2>
{"".join(_ex_sections)}
</div>'''

    # ── Related Safety Rankings (contextual internal links) ──
    related_rankings = ""
    _desc_lower = (agent.get("description") or "").lower()
    _ranking_links = []
    _ss_lp = f"/{lang}" if lang != "en" else ""
    if source != "vpn":
        _vpn_triggers = ("privacy", "vpn", "ip address", "tracking", "anonymous", "encryption", "secure connection", "surveillance")
        if any(t in _desc_lower for t in _vpn_triggers):
            _ranking_links.append(('<a href="/best/safest-vpns">Safest VPN Services</a>', "Independent VPN safety ranking based on Nerq Trust Scores"))
    if source != "password_manager":
        # PM cross-links: only for consumer-facing software, not dev packages
        _pm_consumer_registries = ("chrome", "firefox", "vscode", "android", "ios", "website", "saas")
        if source in ("chrome", "firefox", "vscode"):
            _ranking_links.append(('<a href="/best/safest-password-managers">Safest Password Managers</a>', "Independent password manager safety ranking"))
        elif source in _pm_consumer_registries:
            _pm_triggers = ("password manager", "password vault", "credential manager", "master password")
            if any(t in _desc_lower for t in _pm_triggers):
                _ranking_links.append(('<a href="/best/safest-password-managers">Safest Password Managers</a>', "Independent password manager safety ranking"))
    if source == "vpn":
        _ranking_links.append((f'<a href="{_ss_lp}/best/safest-password-managers">{_t("xlink_complete_privacy", lang)}</a>', _t("xlink_add_pm_vpn", lang)))
        _ranking_links.append((f'<a href="{_ss_lp}/best/safest-antivirus-software">{_t("xlink_add_av", lang)}</a>', _t("xlink_add_av_vpn", lang)))
    if source == "password_manager":
        _ranking_links.append((f'<a href="{_ss_lp}/best/safest-vpns">{_t("xlink_complete_privacy", lang)}</a>', _t("xlink_add_vpn_pm", lang)))
        _ranking_links.append((f'<a href="{_ss_lp}/best/safest-antivirus-software">{_t("xlink_add_malware", lang)}</a>', _t("xlink_add_malware_desc", lang)))
    if source != "crypto":
        _crypto_triggers = ("crypto", "blockchain", "defi", "token", "wallet")
        if any(t in _desc_lower for t in _crypto_triggers):
            _ranking_links.append((f'<a href="{_ss_lp}/best/safest-crypto-exchanges">{_t("xlink_safest_crypto", lang)}</a>', _t("xlink_crypto_desc", lang)))
    if source == "hosting":
        _ranking_links.append((f'<a href="{_ss_lp}/best/safest-vpns">{_t("xlink_protect_server", lang)}</a>', _t("xlink_protect_server_desc", lang)))
        _ranking_links.append((f'<a href="{_ss_lp}/best/safest-password-managers">{_t("xlink_secure_creds", lang)}</a>', _t("xlink_secure_creds_desc", lang)))
    elif source in ("website", "wordpress") and source != "hosting":
        _hosting_triggers = ("hosting", "server", "deploy", "uptime", "wordpress hosting", "cpanel")
        if any(t in _desc_lower for t in _hosting_triggers):
            _ranking_links.append((f'<a href="{_ss_lp}/best/safest-web-hosting">{_t("xlink_safest_hosting", lang)}</a>', _t("xlink_hosting_desc", lang)))
    if source == "antivirus":
        _ranking_links.append((f'<a href="{_ss_lp}/best/safest-vpns">{_t("xlink_complete_security", lang)}</a>', _t("xlink_add_vpn_av", lang)))
        _ranking_links.append((f'<a href="{_ss_lp}/best/safest-password-managers">{_t("xlink_secure_passwords", lang)}</a>', _t("xlink_secure_passwords_desc", lang)))
    elif source not in ("antivirus", "vpn", "password_manager", "hosting", "crypto"):
        _av_triggers = ("malware", "virus", "ransomware", "trojan", "spyware", "endpoint protection", "security software")
        if any(t in _desc_lower for t in _av_triggers):
            _ranking_links.append((f'<a href="{_ss_lp}/best/safest-antivirus-software">{_t("xlink_safest_av", lang)}</a>', _t("xlink_av_desc", lang)))
    if source == "saas":
        _ranking_links.append((f'<a href="{_ss_lp}/best/safest-password-managers">{_t("xlink_secure_saas", lang)}</a>', _t("xlink_secure_saas_desc", lang)))
        _ranking_links.append((f'<a href="{_ss_lp}/best/safest-vpns">{_t("xlink_access_secure", lang)}</a>', _t("xlink_access_secure_desc", lang)))
    # Website Builder cross-links
    if source == "website_builder":
        _ranking_links.append(('<a href="/best/safest-web-hosting">Need More Control?</a>', "See our independent hosting provider rankings"))
    elif source == "hosting":
        _ranking_links.append(('<a href="/best/safest-website-builders">Want Something Simpler?</a>', "See website builder rankings for easy site creation"))
    # Crypto exchange cross-links
    if source == "crypto" and any(t in _desc_lower for t in ('exchange', 'trading', 'dex', 'swap')):
        _ranking_links.append(('<a href="/best/safest-vpns">Protect Your Crypto</a>', "Use a VPN for secure exchange access"))
        _ranking_links.append(('<a href="/best/safest-password-managers">Secure Your Credentials</a>', "Use a password manager for exchange accounts"))
    if _ranking_links:
        _items = "".join(f'<li style="margin:4px 0">{link} — <span style="font-size:13px;color:#64748b">{desc}</span></li>' for link, desc in _ranking_links)
        related_rankings = f'''<div class="related-rankings" style="margin:20px 0;padding:16px;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc">
<h3 style="margin:0 0 8px;font-size:1em;font-weight:600">Related Safety Rankings</h3>
<ul style="margin:0;padding:0 0 0 20px;list-style:disc">{_items}</ul>
</div>'''

    # ── Security Stack block — bidirectional VPN + PM + AV linking ──
    _SECURITY_STACK_REGS = {"vpn", "password_manager", "antivirus"}
    _WEB_STACK_REGS = {"hosting", "website_builder"}
    _security_stack = ""

    if source in _SECURITY_STACK_REGS:
        _ss_items = [
            ("&#128274;", "Best VPNs",              f"{_ss_lp}/best/safest-vpns",                "vpn"),
            ("&#128272;", "Best Password Managers",  f"{_ss_lp}/best/safest-password-managers",  "password_manager"),
            ("&#128737;", "Best Antivirus",          f"{_ss_lp}/best/safest-antivirus-software", "antivirus"),
        ]
        _ss_links = "".join(
            f'<a href="{u}" style="display:flex;align-items:center;gap:8px;padding:10px 14px;border-radius:8px;background:#f8fafc;border:1px solid #e2e8f0;text-decoration:none;color:#1e293b;font-size:14px;transition:box-shadow .15s"><span style="font-size:20px">{ico}</span><span style="font-weight:500">{txt}</span></a>'
            for ico, txt, u, reg in _ss_items if reg != source
        )
        _security_stack = (
            f'<div style="margin:24px 0;padding:18px;border:1px solid #d1d5db;border-radius:10px;background:#fafafa">'
            f'<h3 style="margin:0 0 12px;font-size:15px;font-weight:600;color:#334155">Build Your Security Stack</h3>'
            f'<p style="font-size:13px;color:#64748b;margin:0 0 12px">Combine these tools for comprehensive protection:</p>'
            f'<div style="display:flex;flex-wrap:wrap;gap:10px">{_ss_links}</div></div>'
        )
    elif source in _WEB_STACK_REGS:
        _ws_items = [
            ("&#127760;", "Best Hosting",           f"{_ss_lp}/best/safest-web-hosting",       "hosting"),
            ("&#128296;", "Best Website Builders",   f"{_ss_lp}/best/safest-website-builders",  "website_builder"),
            ("&#128188;", "Best SaaS Platforms",     f"{_ss_lp}/best/safest-saas-platforms",    "saas"),
        ]
        _ws_links = "".join(
            f'<a href="{u}" style="display:flex;align-items:center;gap:8px;padding:10px 14px;border-radius:8px;background:#f8fafc;border:1px solid #e2e8f0;text-decoration:none;color:#1e293b;font-size:14px;transition:box-shadow .15s"><span style="font-size:20px">{ico}</span><span style="font-weight:500">{txt}</span></a>'
            for ico, txt, u, reg in _ws_items if reg != source
        )
        _security_stack = (
            f'<div style="margin:24px 0;padding:18px;border:1px solid #d1d5db;border-radius:10px;background:#fafafa">'
            f'<h3 style="margin:0 0 12px;font-size:15px;font-weight:600;color:#334155">Build Your Web Stack</h3>'
            f'<p style="font-size:13px;color:#64748b;margin:0 0 12px">Complete your web presence with these tools:</p>'
            f'<div style="display:flex;flex-wrap:wrap;gap:10px">{_ws_links}</div></div>'
        )

    # ── See Also section ──
    _sa_best = _REGISTRY_BEST_MAP.get(source, None)
    try:
        _sa_sim = _sim_rows
    except NameError:
        _sa_sim = []
    see_also_html = _build_see_also(slug, display_name, source, _sa_sim, _sa_best, lang=lang)

    # Read template and fill
    html = (TEMPLATE_DIR / "agent_safety_page.html").read_text()
    # URL prefix for localized pages
    _lang_prefix = f"/{lang}" if lang != "en" else ""
    _canonical = f"https://nerq.ai{_lang_prefix}/safe/{slug}"

    # Quality gate: noindex entities in verticals that don't meet quality thresholds
    _qg_index = True
    if agent.get("trust_score") and float(agent.get("trust_score", 0)) < 30:
        _qg_index = False
    else:
        try:
            from agentindex.quality_gate import get_publishable_registries
            _pub = get_publishable_registries()
            if _pub and source and source not in _pub:
                _qg_index = False
        except Exception:
            pass  # If quality gate not available, default to index
    _robots_meta = '<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">' if _qg_index else '<meta name="robots" content="noindex, follow">'

    replacements = {
        "{{ robots_meta }}": _robots_meta,
        "{{ html_lang }}": lang,
        "{{ canonical_url }}": _canonical,
        "{{ page_title }}": _t("title_safe", lang, name=_esc(display_name), year=YEAR),
        "{{ og_title }}": f"{_t('h1_safe', lang, name=_esc(display_name))} Trust Score {score_str}/100 — Nerq",
        "{{ h1_text }}": _t("h1_safe", lang, name=_esc(display_name)),
        "{{ h1_text_lower }}": f"Is {_esc(display_name)} safe?" if lang == "en" else _t("h1_safe", lang, name=_esc(display_name)),
        "{{ t_breadcrumb_home }}": _t("breadcrumb_home", lang),
        "{{ t_breadcrumb_safety }}": _t("breadcrumb_safety", lang),
        "{{ t_last_analyzed }}": _t("last_analyzed", lang),
        "{{ t_data_sourced }}": _t("data_sourced", lang, sources=_rp.get("data_sources", "multiple public sources"), date=datetime.now().strftime("%Y-%m-%d")),
        "{{ t_machine_readable }}": _t("machine_readable", lang),
        "{{ t_trust_score_breakdown }}": _t("trust_score_breakdown", lang),
        "{{ t_key_findings }}": _t("key_findings", lang),
        "{{ t_details }}": _t("details", lang),
        "{{ t_author_label }}": _t("author_label", lang),
        "{{ t_category_label }}": _t("category_label", lang),
        "{{ t_source_label }}": _t("source_label", lang),
        "{{ t_meta_citation_author }}": _t("meta_citation_author", lang),
        "{{ t_disclaimer }}": _t("disclaimer", lang),
        "{{ display_name }}": _esc(display_name),
        "{{ name }}": _esc(name),
        "{{ slug }}": _esc(slug),
        "{{ score }}": score_str,
        "{{ grade }}": _esc(grade),
        "{{ category }}": _esc(_REGISTRY_DISPLAY.get(category, category.replace("_", " ").title() if category else "")),
        "{{ source }}": _esc(source),
        "{{ author }}": _esc(author),
        "{{ stars_row }}": (
            f'<tr><td style="color:#64748b">{_t("global_rank_label", lang)}</td><td>#{agent.get("downloads"):,} (Tranco)</td></tr>'
            if source == "website" and agent.get("downloads") and agent.get("downloads") < 100000
            else f'<tr><td style="color:#64748b">{_t("stars_label", lang)}</td><td>{stars:,}</td></tr>' if stars and "stars" not in _hidden else ""
        ),
        # D1: Perplexity-optimized verdict
        "{{ pplx_verdict }}": _pplx_verdict,
        # D2: Question-format H2s with answer summaries
        "{{ h2_trust_score }}": _h2_trust,
        "{{ answer_trust_score }}": _ans_trust,
        "{{ h2_key_findings }}": _h2_findings,
        "{{ answer_key_findings }}": _ans_findings,
        "{{ h2_details }}": _h2_details,
        "{{ assessment }}": assessment,
        "{{ assessment_short }}": assessment_short,
        "{{ ai_summary }}": ai_summary,
        "{{ citation_detail }}": (
            (f"{_rec_text.capitalize()}. " if is_verified else _t("below_threshold", lang) + " ")
            + (f"{_t('dim_security', lang)}: {security_score:.0f}/100. " if security_score is not None else "")
            + (f"{_t('dim_maintenance', lang)}: {activity_score:.0f}/100. " if 'maintenance' not in _hidden and activity_score is not None else "")
            + (f"{_t('dim_popularity', lang)}: {popularity_score:.0f}/100. " if popularity_score is not None else "")
        ),
        "{{ last_updated }}": datetime.now().strftime("%Y-%m-%d"),
        "{{ grade_pill }}": pill_class,
        "{{ verified_badge }}": verified_badge,
        "{{ is_verified }}": "true" if is_verified else "false",
        "{{ signals_html }}": signals_html,
        "{{ source_link }}": source_link,
        "{{ frameworks_row }}": frameworks_row,
        "{{ protocols_row }}": protocols_row,
        "{{ compliance_section }}": compliance_section,
        "{{ cta_buttons }}": cta_buttons,
        "{{ alternatives_section }}": alternatives_section,
        "{{ vpn_details }}": vpn_details,
        "{{ related_rankings }}": related_rankings + _security_stack,
        "{{ cross_product_html }}": cross_product_html,
        "{{ similar_entities }}": similar_entities_html,
        "{{ king_sections }}": king_sections + _render_cross_registry_section(slug, source) + _l2_block_2a_html(slug) + _l2_block_2b_html(slug) + _l2_block_2c_html(slug) + _l2_block_2d_html(slug) + _l2_block_2e_html(slug),
        "{{ king_jsonld_block }}": (
            '<script type="application/ld+json">' + json.dumps({
                "@context": "https://schema.org",
                "@type": "ItemList",
                "name": f"Trust Score Breakdown for {display_name}",
                "numberOfItems": len([d for d in _dims if d[1] is not None]),
                "itemListElement": [
                    {"@type": "ListItem", "position": i+1, "name": d[0], "description": f"{d[1]:.0f}/100"}
                    for i, d in enumerate(_dims) if d[1] is not None
                ]
            }) + '</script>'
        ) if _render_king_sections and any(d[1] is not None for d in _dims) else "",
        "{{ deep_analysis }}": _get_deep_analysis(name, agent),
        "{{ safety_guide }}": _safety_guide(display_name, name, agent, alternatives, slug),
        "{{ faq_section_html }}": faq_section_html,
        "{{ definition_lead }}": definition_lead,
        "{{ nerq_answer }}": _esc(nerq_answer),
        "{{ data_sources }}": _rp.get("data_sources", "multiple public sources"),
        "{{ webpage_jsonld }}": webpage_jsonld,
        "{{ faq_jsonld }}": faq_jsonld,
        "{{ breadcrumb_jsonld }}": breadcrumb_jsonld,
        "{{ software_jsonld }}": json.dumps({
            **{"@context": "https://schema.org", "@type": _rp["schema_type"]},
            **_rp.get("schema_extra", {}),
            "name": display_name,
            "description": description[:200] if description else f"{display_name} — {_entity_word}",
            "url": f"https://nerq.ai/safe/{slug}",
            "author": {"@type": "Organization", "name": author},
            "offers": {
                "@type": "Offer",
                "price": "0",
                "priceCurrency": "USD",
                "availability": "https://schema.org/InStock",
            },
            "license": agent.get("license") or "Not specified",
            "datePublished": (agent.get("first_seen") or datetime.now().strftime('%Y-%m-%d'))[:10] if agent.get("first_seen") else datetime.now().strftime('%Y-%m-%d'),
            "image": "https://nerq.ai/static/nerq-logo-512.png",
            "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": str(round(max(1.0, float(score) / 20), 1)),
                "bestRating": "5",
                "worstRating": "1",
                "ratingCount": str(max(1, len([s for s in [security_score, compliance_score, activity_score, doc_score, popularity_score] if s is not None]))),
            },
            "review": {
                "@type": "Review",
                "author": {"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"},
                "datePublished": datetime.now().strftime('%Y-%m-%d'),
                "reviewRating": {
                    "@type": "Rating",
                    "ratingValue": str(round(max(1.0, float(score) / 20), 1)),
                    "bestRating": "5",
                    "worstRating": "1",
                },
                "reviewBody": f"{display_name} is a {_entity_word} with a Nerq Trust Score of {score_str}/100 ({grade}). {_rec_text.capitalize() if float(score) >= 70 else 'Proceed with caution.' if float(score) >= 50 else 'Not recommended.'}",
            },
        }),
        "{{ cve_text }}": f"{agent.get('cve_count') or 0} known vulnerabilities" if agent.get('cve_count') is not None else f"{_entity_word.capitalize()} analyzed across security, maintenance, and community signals",
        "{{ license_text }}": _esc(agent.get("license") or "Not specified"),
        "{{ reviews_section }}": reviews_section,
        "{{ display_name }}": _esc(display_name),
        "{{ safety_verdict }}": safety_verdict,
        "{{ verdict_detail }}": verdict_detail,
        "{{ verdict_recommendation }}": verdict_recommendation,
        "{{ verdict_color }}": verdict_color,
        "{{ vb_color }}": vb_color,
        "{{ vb_bg }}": vb_bg,
        "{{ vb_icon }}": vb_icon,
        "{{ vb_text }}": vb_text,
        "{{ key_line }}": key_line,
        "{{ why_this_score_bullets }}": why_this_score_bullets,
        "{{ safer_alternatives_section }}": safer_alternatives_section,
        "{{ badge_markdown }}": _esc(badge_md),
        "{{ related_safety_links }}": _related_safety_links(slug),
        "{{ score_int }}": score_int,
        "{{ score_color_class }}": score_color_class,
        "{{ grade_bg_class }}": grade_bg_class,
        "{{ vb_border }}": vb_border,
        "{{ signals_breakdown_html }}": signals_breakdown_html,
        "{{ why_this_score_findings }}": why_this_score_findings,
        "{{ cross_links_html }}": cross_links_html,
        "{{ discovery_links }}": _get_discovery_links(source, slug).replace("Popular in ", _t("sidebar_popular_in", lang) + " ").replace("Browse Categories", _t("sidebar_browse", lang)).replace("Recently Analyzed", _t("sidebar_recently", lang)).replace("Safest VPNs", _t("sidebar_safest_vpns", lang)).replace("Most Private Apps", _t("sidebar_most_private", lang)),
        "{{ see_also }}": see_also_html,
        "{{ nerq_css }}": NERQ_CSS,
        "{{ nerq_nav }}": render_nav(lang=lang),
        "{{ nerq_footer }}": render_footer(lang=lang),
        "{{ hreflang_tags }}": render_hreflang(f"/safe/{slug}"),
    }
    for key, val in replacements.items():
        html = html.replace(key, str(val))
    return html


def _render_hub_page():
    """Render the agent safety hub page."""
    _load_slugs()

    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT name, COALESCE(trust_score_v2, trust_score) as trust_score,
                   trust_grade, category, source, stars, is_verified
            FROM entity_lookup
            WHERE is_active = true
              AND agent_type IN ('agent', 'mcp_server', 'tool')
              AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC, stars DESC NULLS LAST
            LIMIT 500
        """)).fetchall()
    finally:
        session.close()

    total = len(rows)
    table_rows = ""
    itemlist_items = []

    for i, r in enumerate(rows):
        row = dict(r._mapping)
        name = row["name"] or ""
        slug = _make_slug(name)
        if not slug:
            continue
        score = row["trust_score"] or 0
        grade = row["trust_grade"] or "N/A"
        category = row["category"] or "uncategorized"
        source = row["source"] or "unknown"
        stars = row["stars"] or 0
        is_verified = row["is_verified"] or (score >= 70)

        verified_html = '<span class="verified-dot" title="Nerq Verified"></span>Yes' if is_verified else "No"
        verified_sort = "1" if is_verified else "0"
        pill = _grade_pill(grade)

        table_rows += (
            f'<tr>'
            f'<td><a href="/safe/{_esc(slug)}">{_esc(name)}</a></td>'
            f'<td>{_esc(category)}</td>'
            f'<td data-sort="{score:.1f}" style="font-family:ui-monospace,monospace;font-size:13px">{score:.1f}</td>'
            f'<td><span class="pill {pill}">{_esc(grade)}</span></td>'
            f'<td data-sort="{verified_sort}">{verified_html}</td>'
            f'<td>{_esc(source)}</td>'
            f'<td data-sort="{stars}" style="font-family:ui-monospace,monospace;font-size:13px">{stars:,}</td>'
            f'</tr>\n'
        )

        itemlist_items.append({
            "@type": "ListItem",
            "position": i + 1,
            "url": f"https://nerq.ai/safe/{slug}",
            "name": f"{name} — {grade} ({score:.0f}/100)"
        })

    itemlist_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"AI Agent Safety Ratings — {total} Agents Assessed",
        "description": f"Independent safety assessments for {total} software tools by Nerq.",
        "numberOfItems": total,
        "itemListElement": itemlist_items
    })

    # Featured tools grid — most-searched safety checks
    _featured = [
        ("cursor", "Cursor"), ("chatgpt", "ChatGPT"), ("claude", "Claude"),
        ("windsurf", "Windsurf"), ("bolt", "Bolt"), ("cline", "Cline"),
        ("github-copilot", "GitHub Copilot"), ("gemini", "Gemini"),
        ("ollama", "Ollama"), ("langchain", "LangChain"),
        ("openai", "OpenAI"), ("n8n", "n8n"),
        ("comfyui", "ComfyUI"), ("stable-diffusion", "Stable Diffusion"),
        ("crewai", "CrewAI"), ("autogpt", "AutoGPT"),
        ("llamaindex", "LlamaIndex"), ("devin", "Devin"),
        ("continue", "Continue"), ("hugging-face", "Hugging Face"),
    ]
    featured_html = ""
    for f_slug, f_name in _featured:
        featured_html += (
            f'<a href="/safe/{_esc(f_slug)}" style="display:block;padding:10px 14px;border:1px solid #e5e7eb;'
            f'text-decoration:none;color:#1a1a1a;font-weight:600;font-size:14px">'
            f'Is {_esc(f_name)} safe?</a>\n'
        )

    html = (TEMPLATE_DIR / "agent_safety_hub.html").read_text()
    html = html.replace("{{ total }}", str(total))
    html = html.replace("{{ table_rows }}", table_rows)
    html = html.replace("{{ featured_tools }}", featured_html)
    html = html.replace("{{ itemlist_jsonld }}", itemlist_jsonld)
    html = html.replace("{{ nerq_css }}", NERQ_CSS)
    html = html.replace("{{ nerq_nav }}", NERQ_NAV)
    html = html.replace("{{ nerq_footer }}", NERQ_FOOTER)
    return html


def _resolve_agent_info_with_fallback(slug):
    """Resolve agent_info for /safe/{slug} renders with the same fallback chain
    used by the base route: software_registry → slug file → entity_lookup → name-only.

    Always returns a non-empty dict so callers never need to 404 on lookup miss
    (low/zero-score pages are still rendered and tagged ``noindex`` by the renderer).
    Used by both /safe/{slug} and /safe/{slug}/{privacy|security} so sub-pages
    are atomic with the base page.
    """
    resolved = _resolve_entity(slug)
    if resolved and resolved.get("trust_score"):
        return resolved
    agent_info = _slug_map.get(slug, {})
    if not agent_info or not agent_info.get("name"):
        session = get_session()
        try:
            row = session.execute(text("""
                SELECT name, COALESCE(trust_score_v2, trust_score) as trust_score,
                       trust_grade, category, stars, description,
                       author, source_url, license, agent_type
                FROM entity_lookup
                WHERE (name_lower = :slug OR name_lower = :dehyphen) AND is_active = true
                ORDER BY COALESCE(stars, 0) DESC LIMIT 1
            """), {"slug": slug, "dehyphen": slug.replace('-', ' ')}).fetchone()
            if row:
                agent_info = {
                    "name": row[0], "slug": slug,
                    "trust_score": row[1], "trust_grade": row[2],
                    "category": row[3], "stars": row[4],
                    "description": row[5], "author": row[6],
                    "source_url": row[7], "license": row[8],
                    "agent_type": row[9],
                }
        finally:
            session.close()
    if not agent_info or not agent_info.get("name"):
        agent_info = {"name": slug.replace("-", " ")}
    return agent_info


def mount_agent_safety_pages(app):
    """Mount /safe/{slug} and /safe routes."""
    _load_slugs()

    @app.get("/safe", response_class=HTMLResponse)
    async def agent_safety_hub():
        try:
            html = _render_hub_page()
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Error rendering agent safety hub: {e}")
            return HTMLResponse(status_code=500, content=f"<h1>Error</h1><p>{_esc(str(e))}</p>")

    @app.get("/safe/{owner}/{repo}", response_class=HTMLResponse)
    async def agent_safety_page_ownerrepo(owner: str, repo: str):
        """Handle /safe/owner/repo AND /safe/{slug}/privacy|security sub-pages."""
        _load_slugs()

        # Sub-page routes: /safe/{slug}/privacy, /safe/{slug}/security
        # Mirror the base /safe/{slug} fallback chain so sub-pages are atomic
        # with the base page (FU-QUERY-20260418-05 / AUDIT-QUERY-20260418#5).
        if repo in ("privacy", "security"):
            entity_slug = owner.lower()
            agent = _resolve_agent_info_with_fallback(entity_slug)
            return HTMLResponse(_render_sub_page(entity_slug, agent, repo))

        # Regular owner/repo handling
        candidates = [
            f"{owner}{repo}".lower(),
            f"{owner}-{repo}".lower(),
            repo.lower(),
        ]
        for slug in candidates:
            if slug in _slug_map:
                return await agent_safety_page(slug)
        full_name = f"{owner}/{repo}"
        for s in _slug_map.values():
            if s.get("name", "").lower() == full_name.lower():
                return await agent_safety_page(s["slug"])
        return await agent_safety_page(repo.lower())

    @app.get("/safe/{slug}", response_class=HTMLResponse)
    async def agent_safety_page(slug: str):
        _load_slugs()
        agent_info = _resolve_agent_info_with_fallback(slug)

        import time
        cache_key = slug
        now = time.time()
        if cache_key in _page_cache:
            html, ts = _page_cache[cache_key]
            if now - ts < _CACHE_TTL:
                return HTMLResponse(content=html)

        try:
            html = _render_agent_page(slug, agent_info)
            if html is None:
                return HTMLResponse(status_code=404, content="<h1>Agent not found</h1><p>No safety data available.</p>")
            if len(_page_cache) < _CACHE_MAX:
                _page_cache[cache_key] = (html, now)
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Error rendering agent safety page {slug}: {e}")
            return HTMLResponse(status_code=500, content=f"<h1>Error</h1><p>{_esc(str(e))}</p>")

    @app.get("/is-{slug}-safe", response_class=HTMLResponse)
    async def is_agent_safe_alias(slug: str):
        """SEO alias: /is-langchain-safe serves same content as /safe/langchain."""
        _load_slugs()
        agent_info = _slug_map.get(slug, {})
        if not agent_info:
            agent_info = {"name": slug.replace("-", " ")}

        import time
        cache_key = f"is-{slug}-safe"
        now = time.time()
        if cache_key in _page_cache:
            html, ts = _page_cache[cache_key]
            if now - ts < _CACHE_TTL:
                return HTMLResponse(content=html)

        try:
            html = _render_agent_page(slug, agent_info)
            if html is None:
                return HTMLResponse(status_code=404, content="<h1>Agent not found</h1><p>No safety data available.</p>")
            # Adjust canonical to /safe/{slug} to consolidate link equity
            html = html.replace(
                f'<link rel="canonical" href="https://nerq.ai/safe/{slug}">',
                f'<link rel="canonical" href="https://nerq.ai/safe/{slug}">'
            )
            if len(_page_cache) < _CACHE_MAX:
                _page_cache[cache_key] = (html, now)
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Error rendering is-{slug}-safe: {e}")
            return HTMLResponse(status_code=500, content=f"<h1>Error</h1><p>{_esc(str(e))}</p>")

    @app.get("/sitemap-safe.xml", response_class=Response)
    async def sitemap_safe():
        """Serve /safe/ sitemap — first 50K entries (chunk 0)."""
        return await _sitemap_safe_chunk(0)

    @app.get("/sitemap-safe-{chunk}.xml", response_class=Response)
    async def sitemap_safe_chunked(chunk: int):
        """Serve /safe/ sitemap — chunked at 50K per file for Google compliance."""
        return await _sitemap_safe_chunk(chunk)

    async def _sitemap_safe_chunk(chunk: int):
        _load_slugs()
        today = date.today().isoformat()
        # Chunk 0 includes the /safe hub page, so take 49999 entries
        if chunk == 0:
            page = _slug_list[:49999]
        else:
            start = 49999 + (chunk - 1) * 50000
            end = start + 50000
            page = _slug_list[start:end]

        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        if chunk == 0:
            xml += f'  <url>\n    <loc>https://nerq.ai/safe</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>1.0</priority>\n  </url>\n'
        for a in page:
            xml += f'  <url>\n    <loc>https://nerq.ai/safe/{a["slug"]}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.8</priority>\n  </url>\n'
        xml += '</urlset>'
        return Response(content=xml, media_type="application/xml")

    @app.get("/sitemap-safety.xml", response_class=Response)
    async def sitemap_safety():
        """Sitemap for /is-X-safe pages, prioritized by search demand."""
        today = date.today().isoformat()
        data_path = Path(__file__).parent.parent / "data" / "safety_demand_ranking.json"
        try:
            with open(data_path) as f:
                ranking = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load safety_demand_ranking.json: {e}")
            return Response(content="<!-- ranking data unavailable -->", media_type="application/xml")

        top_30_tools = {item["tool"] for item in ranking.get("top_30", [])}
        all_tools = ranking.get("all", [])[:5000]

        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for item in all_tools:
            tool = item["tool"]
            slug = tool.lower().replace(" ", "-").replace("_", "-").replace(".", "-")
            priority = "0.9" if tool in top_30_tools else "0.8"
            xml += (
                f'  <url>\n'
                f'    <loc>https://nerq.ai/is-{slug}-safe</loc>\n'
                f'    <lastmod>{today}</lastmod>\n'
                f'    <changefreq>daily</changefreq>\n'
                f'    <priority>{priority}</priority>\n'
                f'  </url>\n'
            )
        xml += '</urlset>'
        return Response(content=xml, media_type="application/xml")

    @app.get("/sitemap-fresh.xml", response_class=Response)
    async def sitemap_fresh():
        """Sitemap of the 1000 most recently updated entities — signals freshness to crawlers."""
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT slug, registry, COALESCE(enriched_at, created_at) as last_mod
                FROM software_registry
                WHERE description IS NOT NULL AND LENGTH(description) > 20
                  AND trust_score IS NOT NULL AND trust_score > 0
                ORDER BY COALESCE(enriched_at, created_at) DESC NULLS LAST
                LIMIT 1000
            """)).fetchall()
        finally:
            session.close()

        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for r in rows:
            _slug, _reg, _lm = r
            _lastmod = str(_lm)[:10] if _lm else date.today().isoformat()
            xml += (f'  <url>\n    <loc>https://nerq.ai/safe/{_esc(_slug)}</loc>\n'
                    f'    <lastmod>{_lastmod}</lastmod>\n'
                    f'    <changefreq>daily</changefreq>\n    <priority>0.9</priority>\n  </url>\n')
        xml += '</urlset>'
        return Response(content=xml, media_type="application/xml")

    logger.info(f"Mounted agent safety pages: {len(_slug_map)} agents, /safe hub, /sitemap-safe.xml, /sitemap-safety.xml, /sitemap-fresh.xml")
