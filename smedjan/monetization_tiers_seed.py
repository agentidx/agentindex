"""Seed smedjan.monetization_tiers with Keyword-Planner-derived CPC proxies.

Revenue estimation for Nerq relies on the triad Trafik × CTR × RPC. There is no
live affiliate feed today, so RPC is approximated from Google Keyword Planner
category CPC values (static, per-registry). This module both defines the DDL
and seeds the rows; running it is idempotent.

Invocation:
    PYTHONPATH=/Users/anstudio/agentindex \
        /Users/anstudio/agentindex/venv/bin/python3 \
        -m smedjan.monetization_tiers_seed
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from smedjan import sources

log = logging.getLogger("smedjan.monetization_tiers_seed")


DDL = """
CREATE TABLE IF NOT EXISTS smedjan.monetization_tiers (
    path_pattern     text PRIMARY KEY,
    tier             text NOT NULL CHECK (tier IN ('T1','T2','T3')),
    avg_cpc_usd      numeric(6,2),
    rationale        text NOT NULL,
    last_updated     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_monetization_tiers_tier
    ON smedjan.monetization_tiers (tier);
"""


@dataclass(frozen=True)
class TierRow:
    path_pattern: str
    tier: str
    avg_cpc_usd: float
    rationale: str


# Rubric (committed in rationale column):
#   T1 (>= $5.00 avg CPC):
#       /safe/<vpn>, /best/vpn, /compare/<vpn>-vs-*,
#       /safe/<antivirus>, /safe/<password_manager>, /crypto/token/<slug>
#   T2 ($1.00 - $5.00 avg CPC):
#       /safe/<saas>, /safe/<ai_tool>, /compare/*-vs-* in saas+ai_tool,
#       /alternatives/<saas>, /review/<saas>
#   T3 (< $1.00 avg CPC):
#       all open-source package indexes (npm, pypi, crates, go, gems,
#       packagist, homebrew, nuget, vscode), OS/browser app stores
#       (chrome, firefox, ios, android, steam), CMS/content registries
#       (wordpress, website), and long-tail informational verticals
#       (charity, ingredient, supplement, cosmetic_ingredient, city,
#       country).
#
# CPC values are 2026-Q1 Keyword Planner category midpoints; they are static
# seeds — T004-T007 downstream tasks are responsible for refreshing them.


def _t1_rows() -> list[TierRow]:
    rubric = (
        "T1 (>=$5 CPC): affiliate-rich verticals with paid-placement "
        "saturation on Google (VPN, antivirus, password manager, crypto)."
    )
    rows: list[TierRow] = []

    # vpn — Keyword Planner "VPN service" $8-$15 range.
    rows += [
        TierRow("/safe/vpn/{slug}", "T1", 10.50,
                rubric + " /safe/vpn/{slug} is the canonical Nerq VPN review page."),
        TierRow("/best/vpn", "T1", 12.00,
                rubric + " 'best vpn' head term CPC is ~$12 in Keyword Planner."),
        TierRow("/compare/vpn/{a}-vs-{b}", "T1", 8.75,
                rubric + " Head-to-head vpn comparisons match commercial intent."),
        TierRow("/review/vpn/{slug}", "T1", 9.25,
                rubric + " Review-intent queries in the VPN vertical."),
    ]

    # antivirus — Keyword Planner "antivirus software" $6-$12.
    rows += [
        TierRow("/safe/antivirus/{slug}", "T1", 8.25,
                rubric + " Antivirus product pages carry high affiliate CPC."),
        TierRow("/best/antivirus", "T1", 9.50,
                rubric + " 'best antivirus' head term; enterprise + consumer buyers."),
        TierRow("/compare/antivirus/{a}-vs-{b}", "T1", 6.75,
                rubric + " Comparison intent in antivirus stays above $5."),
        TierRow("/review/antivirus/{slug}", "T1", 7.00,
                rubric + " Review-intent for antivirus products."),
    ]

    # password_manager — Keyword Planner $5-$8.
    rows += [
        TierRow("/safe/password-manager/{slug}", "T1", 6.00,
                rubric + " Password manager product pages track 1Password/Bitwarden CPCs."),
        TierRow("/best/password-manager", "T1", 6.75,
                rubric + " 'best password manager' head term."),
        TierRow("/compare/password-manager/{a}-vs-{b}", "T1", 5.25,
                rubric + " Comparison intent (e.g. '1password vs bitwarden')."),
        TierRow("/review/password-manager/{slug}", "T1", 5.50,
                rubric + " Review-intent queries in the password-manager vertical."),
    ]

    # crypto — mixed: token pages + compare + safe.
    rows += [
        TierRow("/crypto/token/{slug}", "T1", 5.75,
                rubric + " /crypto/token/ pages match 'token price + exchange' CPCs."),
        TierRow("/safe/crypto/{slug}", "T1", 5.25,
                rubric + " /safe/crypto mirrors ZARQ trust scoring; high exchange-affiliate CPC."),
        TierRow("/crypto/compare/{a}-vs-{b}", "T1", 5.10,
                rubric + " Token-vs-token comparisons; exchange and wallet affiliates bid here."),
        TierRow("/review/crypto/{slug}", "T1", 5.00,
                rubric + " Review-intent crypto queries; exchange and custodial affiliates."),
    ]
    return rows


def _t2_rows() -> list[TierRow]:
    rubric = (
        "T2 ($1-$5 CPC): SaaS + AI tooling + hosting/site-builders; "
        "SEO affiliate programs exist but CPC saturates mid-range."
    )
    rows: list[TierRow] = []

    # saas — Keyword Planner "saas" tools $1.50-$4.50.
    rows += [
        TierRow("/safe/saas/{slug}", "T2", 2.75,
                rubric + " /safe/saas is the canonical SaaS review slug."),
        TierRow("/compare/saas/{a}-vs-{b}", "T2", 3.25,
                rubric + " 'x vs y' SaaS comparisons — classic mid-funnel intent."),
        TierRow("/alternatives/saas/{slug}", "T2", 3.50,
                rubric + " 'alternatives to x' intent: user near-switching decision."),
        TierRow("/review/saas/{slug}", "T2", 2.25,
                rubric + " Review-intent traffic on SaaS products."),
    ]

    # ai_tool — Keyword Planner "ai tool" $1.25-$3.50.
    rows += [
        TierRow("/safe/ai-tool/{slug}", "T2", 2.00,
                rubric + " AI tool review pages; growing affiliate ecosystem."),
        TierRow("/compare/ai-tool/{a}-vs-{b}", "T2", 2.50,
                rubric + " 'chatgpt vs claude' style comparisons."),
        TierRow("/alternatives/ai-tool/{slug}", "T2", 2.75,
                rubric + " 'alternatives to <ai tool>' intent."),
        TierRow("/review/ai-tool/{slug}", "T2", 1.75,
                rubric + " Review-intent for AI tools."),
    ]

    # hosting — adjacent to SaaS; affiliate CPC solid but not T1.
    rows += [
        TierRow("/safe/hosting/{slug}", "T2", 4.25,
                rubric + " Hosting has strong affiliate payouts (Bluehost/Hostinger) but CPC caps ~$5."),
        TierRow("/compare/hosting/{a}-vs-{b}", "T2", 4.50,
                rubric + " Hosting head-to-head comparisons."),
        TierRow("/alternatives/hosting/{slug}", "T2", 3.75,
                rubric + " 'alternatives to <host>' intent."),
        TierRow("/review/hosting/{slug}", "T2", 4.00,
                rubric + " Review-intent hosting traffic."),
    ]

    # website_builder — Wix/Squarespace/Webflow affiliates.
    rows += [
        TierRow("/safe/website-builder/{slug}", "T2", 3.50,
                rubric + " Website builder review pages."),
        TierRow("/compare/website-builder/{a}-vs-{b}", "T2", 3.75,
                rubric + " 'wix vs squarespace' style comparisons."),
        TierRow("/alternatives/website-builder/{slug}", "T2", 3.25,
                rubric + " 'alternatives to <builder>' intent."),
        TierRow("/review/website-builder/{slug}", "T2", 3.00,
                rubric + " Review-intent website-builder traffic."),
    ]
    return rows


# T3 registries: no direct affiliate program; monetization relies on
# aggregate traffic volume, not per-click value.
_T3_REGISTRIES: dict[str, tuple[float, str]] = {
    # Open-source package indexes — zero commercial intent.
    "npm": (0.35, "OSS JS packages; no affiliate layer."),
    "pypi": (0.35, "OSS Python packages; no affiliate layer."),
    "crates": (0.30, "OSS Rust crates; no affiliate layer."),
    "go": (0.30, "OSS Go modules; no affiliate layer."),
    "gems": (0.30, "OSS Ruby gems; no affiliate layer."),
    "packagist": (0.30, "OSS PHP packages; no affiliate layer."),
    "nuget": (0.35, "OSS .NET packages; no affiliate layer."),
    "homebrew": (0.40, "macOS OSS tap; no affiliate layer."),
    "vscode": (0.45, "VS Code extensions; no affiliate layer."),
    # OS / browser app stores.
    "chrome": (0.50, "Chrome extensions; most are free/freemium."),
    "firefox": (0.45, "Firefox add-ons; mostly free."),
    "ios": (0.65, "iOS apps; affiliate via Apple 2.5% but low per-click."),
    "android": (0.60, "Android apps; no affiliate layer."),
    "steam": (0.55, "Steam games; no affiliate layer."),
    # CMS / content registries.
    "wordpress": (0.75, "WP plugins/themes; some affiliate but low CPC."),
    "website": (0.55, "General website directory; long-tail informational."),
    # Informational / long-tail verticals.
    "charity": (0.25, "Charity directory; no commercial intent."),
    "ingredient": (0.20, "Ingredient safety lookups; informational."),
    "supplement": (0.85, "Supplement queries — some affiliate but under $1."),
    "cosmetic_ingredient": (0.30, "Cosmetic ingredient safety lookups."),
    "city": (0.40, "City directory; informational."),
    "country": (0.35, "Country directory; informational."),
}


def _t3_rows() -> list[TierRow]:
    rubric = (
        "T3 (<$1 CPC): informational or open-source pages. Revenue here "
        "scales with raw traffic (programmatic SEO), not per-click CPC."
    )
    rows: list[TierRow] = []
    for registry, (cpc, note) in _T3_REGISTRIES.items():
        slug_path = registry.replace("_", "-")
        rows += [
            TierRow(
                f"/safe/{slug_path}/{{slug}}", "T3", cpc,
                rubric + f" /safe/{slug_path}: {note}",
            ),
            TierRow(
                f"/compare/{slug_path}/{{a}}-vs-{{b}}", "T3", max(cpc - 0.05, 0.10),
                rubric + f" /compare/{slug_path}: {note}",
            ),
            TierRow(
                f"/alternatives/{slug_path}/{{slug}}", "T3", max(cpc - 0.10, 0.10),
                rubric + f" /alternatives/{slug_path}: {note}",
            ),
        ]
    return rows


def all_rows() -> list[TierRow]:
    return _t1_rows() + _t2_rows() + _t3_rows()


UPSERT = """
INSERT INTO smedjan.monetization_tiers
    (path_pattern, tier, avg_cpc_usd, rationale, last_updated)
VALUES (%s, %s, %s, %s, now())
ON CONFLICT (path_pattern) DO UPDATE
    SET tier         = EXCLUDED.tier,
        avg_cpc_usd  = EXCLUDED.avg_cpc_usd,
        rationale    = EXCLUDED.rationale,
        last_updated = now()
"""


def apply() -> int:
    rows = all_rows()
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute(DDL)
        for r in rows:
            cur.execute(UPSERT, (r.path_pattern, r.tier, r.avg_cpc_usd, r.rationale))
        cur.execute("SELECT COUNT(*) FROM smedjan.monetization_tiers")
        count = cur.fetchone()[0]
    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    n = apply()
    log.info("smedjan.monetization_tiers rows after apply: %d", n)
