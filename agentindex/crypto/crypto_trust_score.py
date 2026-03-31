"""
Nerq Crypto Module — Trust Score Engine
Punkt 29: Scora alla crypto-entiteter med samma 5-dimensionella system som Trust Score v2.2.

Dimensions (same weights as agent Trust Score):
  Security    (30%) — audits, hacks, contract risk, reserves
  Compliance  (25%) — regulatory status, KYC, jurisdiction
  Maintenance (20%) — activity, updates, team presence
  Popularity  (15%) — volume, TVL, holders, market cap rank
  Ecosystem   (10%) — integrations, chains, partnerships

Grades: A+ (90+), A (80-89), B+ (70-79), B (60-69), C+ (50-59),
        C (40-49), D+ (30-39), D (20-29), F (0-19)

Usage:
    python3 crypto_trust_score.py                  # Score everything
    python3 crypto_trust_score.py --tokens-only    # Only tokens
    python3 crypto_trust_score.py --exchanges-only # Only exchanges
    python3 crypto_trust_score.py --defi-only      # Only DeFi protocols
    python3 crypto_trust_score.py --stats          # Print score distribution
"""

import argparse
import json
import math
import time
import sys
from datetime import datetime, timezone

from crypto_models import get_db, init_db


# ── Grade System ──────────────────────────────────────────────────

GRADE_THRESHOLDS = [
    (90, "A+"), (80, "A"), (70, "B+"), (60, "B"),
    (50, "C+"), (40, "C"), (30, "D+"), (20, "D"), (0, "F")
]

def score_to_grade(score):
    """Convert 0-100 score to letter grade."""
    if score is None:
        return "F"
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


# ── Utility Functions ─────────────────────────────────────────────

def clamp(val, lo=0, hi=100):
    """Clamp value between lo and hi."""
    if val is None:
        return 0
    return max(lo, min(hi, val))


def log_scale(val, median, max_score=100):
    """
    Logarithmic scaling — good for highly skewed distributions.
    Returns 0-max_score where median input ≈ 50.
    """
    if not val or val <= 0:
        return 0
    if not median or median <= 0:
        median = 1
    # log(val/median) centered at 0, scale to 0-100
    ratio = val / median
    scaled = 50 + 25 * math.log10(max(ratio, 0.001))
    return clamp(scaled, 0, max_score)


def rank_scale(rank, total, max_score=100):
    """
    Convert a rank (1=best) to a score where #1 = max_score, last = 0.
    """
    if not rank or not total or total <= 1:
        return 50  # neutral if unknown
    percentile = 1 - ((rank - 1) / (total - 1))
    return clamp(percentile * max_score)


def bool_score(val, weight=20):
    """Convert a boolean signal to a score component."""
    return weight if val else 0


def age_score(date_str, max_years=5, max_score=30):
    """Score based on age — older = more trustworthy, up to max_years."""
    if not date_str:
        return 0
    try:
        if isinstance(date_str, (int, float)):
            # Unix timestamp
            dt = datetime.fromtimestamp(date_str, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - dt).days
        age_years = age_days / 365.25
        return clamp((age_years / max_years) * max_score, 0, max_score)
    except (ValueError, TypeError, OSError):
        return 0


# ── Token Trust Score ─────────────────────────────────────────────

def score_token(token):
    """
    Score a token across 5 dimensions.
    Uses data from both /markets and /coins/{id} endpoints.
    """
    # ── Security (30%) ────────────────────────────────────
    security = 0

    # Has contract audit?
    security += bool_score(token.get("has_audit"), 25)

    # Has verified status on CoinGecko?
    security += bool_score(token.get("is_verified"), 15)

    # Has known contract address (not just a native coin)?
    has_contract = bool(token.get("contract_address") or token.get("platforms"))
    platforms = {}
    if token.get("platforms"):
        try:
            platforms = json.loads(token["platforms"]) if isinstance(token["platforms"], str) else token["platforms"]
        except (json.JSONDecodeError, TypeError):
            pass

    # Multi-chain presence = more vetted
    num_chains = len(platforms) if platforms else (1 if not has_contract else 0)
    security += clamp(num_chains * 5, 0, 15)

    # Market cap as proxy for "survived long enough to accumulate value"
    mcap = token.get("market_cap_usd") or 0
    if mcap > 10_000_000_000:      # >$10B
        security += 25
    elif mcap > 1_000_000_000:     # >$1B
        security += 20
    elif mcap > 100_000_000:       # >$100M
        security += 15
    elif mcap > 10_000_000:        # >$10M
        security += 10
    elif mcap > 1_000_000:         # >$1M
        security += 5

    # ATH/ATL ratio — extreme crash from ATH suggests risk
    ath = token.get("ath_usd") or 0
    price = token.get("current_price_usd") or 0
    if ath > 0 and price > 0:
        recovery = price / ath
        if recovery > 0.5:
            security += 10
        elif recovery > 0.1:
            security += 5
        # Catastrophic crash penalty — tokens that lost >95% are fundamentally broken
        if recovery < 0.01:      # >99% crash (e.g. Luna, FTT)
            security -= 40
        elif recovery < 0.05:    # >95% crash
            security -= 25
        elif recovery < 0.1:     # >90% crash
            security -= 15

    # Max supply defined = deflationary/capped = good
    security += bool_score(token.get("max_supply"), 10)

    security = clamp(security)

    # ── Compliance (25%) ──────────────────────────────────
    compliance = 0

    # Market cap rank as proxy for regulatory scrutiny survival
    rank = token.get("market_cap_rank")
    if rank:
        if rank <= 20:
            compliance += 35
        elif rank <= 100:
            compliance += 28
        elif rank <= 500:
            compliance += 20
        elif rank <= 2000:
            compliance += 12
        else:
            compliance += 5

    # Has homepage (basic legitimacy)
    compliance += bool_score(token.get("homepage"), 15)

    # Has social presence (team is public)
    compliance += bool_score(token.get("twitter_handle"), 10)
    compliance += bool_score(token.get("subreddit_url"), 5)
    compliance += bool_score(token.get("telegram_url"), 5)

    # Categories available (CoinGecko vetted)
    categories = []
    if token.get("categories"):
        try:
            categories = json.loads(token["categories"]) if isinstance(token["categories"], str) else token["categories"]
        except (json.JSONDecodeError, TypeError):
            pass
    compliance += clamp(len(categories) * 5, 0, 15)

    # Fully diluted valuation exists (transparency)
    compliance += bool_score(token.get("fully_diluted_valuation"), 10)

    # Supply transparency
    if token.get("circulating_supply") and token.get("total_supply"):
        circ = token["circulating_supply"]
        total = token["total_supply"]
        if total > 0:
            ratio = circ / total
            compliance += clamp(ratio * 15, 0, 15)  # Higher circulating % = more transparent

    compliance = clamp(compliance)

    # ── Maintenance (20%) ─────────────────────────────────
    maintenance = 0

    # GitHub activity (from detail crawl)
    github_repos = []
    if token.get("github_repos"):
        try:
            github_repos = json.loads(token["github_repos"]) if isinstance(token["github_repos"], str) else token["github_repos"]
        except (json.JSONDecodeError, TypeError):
            pass

    has_github = len(github_repos) > 0
    maintenance += bool_score(has_github, 20)

    # GitHub metrics
    stars = token.get("github_stars") or 0
    forks = token.get("github_forks") or 0
    contributors = token.get("github_contributors") or 0

    if stars > 1000:
        maintenance += 15
    elif stars > 100:
        maintenance += 10
    elif stars > 10:
        maintenance += 5

    if contributors > 50:
        maintenance += 15
    elif contributors > 10:
        maintenance += 10
    elif contributors > 3:
        maintenance += 5

    # Issue resolution rate
    total_issues = token.get("github_total_issues") or 0
    closed_issues = token.get("github_closed_issues") or 0
    if total_issues > 0:
        resolution = closed_issues / total_issues
        maintenance += clamp(resolution * 15, 0, 15)

    # Price activity (not dead coin)
    vol = token.get("total_volume_24h_usd") or 0
    if vol > 1_000_000:
        maintenance += 15
    elif vol > 100_000:
        maintenance += 10
    elif vol > 10_000:
        maintenance += 5
    elif vol > 0:
        maintenance += 2

    # Not a stale token — has recent price change
    change_24h = token.get("price_change_24h_pct")
    if change_24h is not None:
        maintenance += 10  # at least it's trading

    maintenance = clamp(maintenance)

    # ── Popularity (15%) ──────────────────────────────────
    popularity = 0

    # Market cap rank (top = popular)
    if rank:
        popularity += rank_scale(rank, 15000)  # 15K tokens total

    # 24h volume
    if vol > 1_000_000_000:
        popularity += 30
    elif vol > 100_000_000:
        popularity += 25
    elif vol > 10_000_000:
        popularity += 20
    elif vol > 1_000_000:
        popularity += 15
    elif vol > 100_000:
        popularity += 10
    elif vol > 0:
        popularity += 3

    # Social following
    twitter_followers = token.get("twitter_followers") or 0
    if twitter_followers > 1_000_000:
        popularity += 20
    elif twitter_followers > 100_000:
        popularity += 15
    elif twitter_followers > 10_000:
        popularity += 10
    elif twitter_followers > 1_000:
        popularity += 5

    reddit_subs = token.get("reddit_subscribers") or 0
    if reddit_subs > 100_000:
        popularity += 10
    elif reddit_subs > 10_000:
        popularity += 7
    elif reddit_subs > 1_000:
        popularity += 4

    popularity = clamp(popularity)

    # ── Ecosystem (10%) ───────────────────────────────────
    ecosystem = 0

    # Multi-chain support
    if num_chains >= 5:
        ecosystem += 30
    elif num_chains >= 3:
        ecosystem += 25
    elif num_chains >= 2:
        ecosystem += 20
    elif num_chains >= 1:
        ecosystem += 10

    # Categories = integrations/use cases
    ecosystem += clamp(len(categories) * 8, 0, 30)

    # Has DeFi presence (implied by categories)
    defi_cats = [c for c in categories if c and ("defi" in c.lower() or "dex" in c.lower() or "lending" in c.lower() or "yield" in c.lower())]
    ecosystem += clamp(len(defi_cats) * 10, 0, 20)

    # GitHub forks = ecosystem adoption
    if forks > 500:
        ecosystem += 20
    elif forks > 100:
        ecosystem += 15
    elif forks > 20:
        ecosystem += 10
    elif forks > 5:
        ecosystem += 5

    ecosystem = clamp(ecosystem)

    # ── Weighted Total ────────────────────────────────────
    total = (
        security * 0.30 +
        compliance * 0.25 +
        maintenance * 0.20 +
        popularity * 0.15 +
        ecosystem * 0.10
    )

    return {
        "trust_score": round(total, 1),
        "trust_grade": score_to_grade(total),
        "security_score": round(security, 1),
        "compliance_score": round(compliance, 1),
        "maintenance_score": round(maintenance, 1),
        "popularity_score": round(popularity, 1),
        "ecosystem_score": round(ecosystem, 1),
    }


# ── Exchange Trust Score ──────────────────────────────────────────

def score_exchange(ex):
    """Score an exchange across 5 dimensions."""

    # ── Security (30%) ────────────────────────────────────
    security = 0

    # CoinGecko trust score (1-10)
    cg_trust = ex.get("trust_score_cg") or 0
    security += clamp(cg_trust * 10, 0, 40)

    # Has proof of reserves
    security += bool_score(ex.get("proof_of_reserves"), 20)

    # Age — older exchanges more trusted
    year = ex.get("year_established")
    if year:
        age = 2026 - year
        if age >= 8:
            security += 25
        elif age >= 5:
            security += 20
        elif age >= 3:
            security += 15
        elif age >= 1:
            security += 8

    # Hack history penalty
    hack_data = ex.get("hack_history")
    if hack_data:
        try:
            hacks = json.loads(hack_data) if isinstance(hack_data, str) else hack_data
            if isinstance(hacks, list) and len(hacks) > 0:
                security -= min(len(hacks) * 10, 30)
        except (json.JSONDecodeError, TypeError):
            pass

    security = clamp(security)

    # ── Compliance (25%) ──────────────────────────────────
    compliance = 0

    # Country known = registered somewhere
    compliance += bool_score(ex.get("country"), 15)

    # Regulatory status (from enrichment data)
    reg_data = ex.get("regulatory_status")
    num_jurisdictions = 0
    if reg_data:
        try:
            regs = json.loads(reg_data) if isinstance(reg_data, str) else reg_data
            if isinstance(regs, dict):
                num_jurisdictions = len(regs)
                # More jurisdictions = more compliant
                if num_jurisdictions >= 5:
                    compliance += 35
                elif num_jurisdictions >= 3:
                    compliance += 25
                elif num_jurisdictions >= 1:
                    compliance += 15
        except (json.JSONDecodeError, TypeError):
            pass

    # CoinGecko trust score rank (proxy for legitimacy)
    trust_rank = ex.get("trust_score_rank") or 9999
    if trust_rank <= 10:
        compliance += 35
    elif trust_rank <= 50:
        compliance += 25
    elif trust_rank <= 100:
        compliance += 18
    elif trust_rank <= 300:
        compliance += 10
    else:
        compliance += 3

    # Has URL (basic legitimacy)
    compliance += bool_score(ex.get("url"), 10)

    # No trading incentives = less likely to fake volume
    compliance += 15 if not ex.get("has_trading_incentive") else 0

    # Age-based compliance
    if year:
        age = 2026 - year
        if age >= 5:
            compliance += 15
        elif age >= 3:
            compliance += 10
        elif age >= 1:
            compliance += 5

    compliance = clamp(compliance)

    # ── Maintenance (20%) ─────────────────────────────────
    maintenance = 0

    # Active trading volume = operational
    vol_btc = ex.get("trade_volume_24h_btc") or 0
    if vol_btc > 10000:
        maintenance += 40
    elif vol_btc > 1000:
        maintenance += 30
    elif vol_btc > 100:
        maintenance += 20
    elif vol_btc > 10:
        maintenance += 10
    elif vol_btc > 0:
        maintenance += 5

    # CoinGecko trust score as activity proxy
    maintenance += clamp(cg_trust * 6, 0, 30)

    # Has been around (not a fly-by-night)
    if year and (2026 - year) >= 2:
        maintenance += 20
    elif year:
        maintenance += 10

    maintenance = clamp(maintenance)

    # ── Popularity (15%) ──────────────────────────────────
    popularity = 0

    # Volume rank
    if trust_rank:
        popularity += rank_scale(trust_rank, 1029)

    # Absolute volume
    if vol_btc > 100000:
        popularity += 30
    elif vol_btc > 10000:
        popularity += 20
    elif vol_btc > 1000:
        popularity += 15
    elif vol_btc > 100:
        popularity += 10

    popularity = clamp(popularity)

    # ── Ecosystem (10%) ───────────────────────────────────
    ecosystem = 0

    # Name recognition / trust rank
    if trust_rank <= 20:
        ecosystem += 50
    elif trust_rank <= 50:
        ecosystem += 35
    elif trust_rank <= 100:
        ecosystem += 25
    elif trust_rank <= 200:
        ecosystem += 15
    else:
        ecosystem += 5

    # Country presence = regulatory integration
    ecosystem += bool_score(ex.get("country"), 20)

    # High volume = deep liquidity ecosystem
    if vol_btc > 50000:
        ecosystem += 30
    elif vol_btc > 5000:
        ecosystem += 20
    elif vol_btc > 500:
        ecosystem += 10

    ecosystem = clamp(ecosystem)

    # ── Weighted Total ────────────────────────────────────
    total = (
        security * 0.30 +
        compliance * 0.25 +
        maintenance * 0.20 +
        popularity * 0.15 +
        ecosystem * 0.10
    )

    return {
        "trust_score": round(total, 1),
        "trust_grade": score_to_grade(total),
        "security_score": round(security, 1),
        "compliance_score": round(compliance, 1),
        "maintenance_score": round(maintenance, 1),
        "popularity_score": round(popularity, 1),
        "ecosystem_score": round(ecosystem, 1),
    }


# ── DeFi Protocol Trust Score ────────────────────────────────────

def score_defi(protocol):
    """Score a DeFi protocol across 5 dimensions."""

    tvl = protocol.get("tvl_usd") or 0

    # Parse hack history
    hacks = []
    total_stolen = 0
    if protocol.get("hack_history"):
        try:
            hack_data = json.loads(protocol["hack_history"]) if isinstance(protocol["hack_history"], str) else protocol["hack_history"]
            hacks = hack_data.get("incidents", []) if isinstance(hack_data, dict) else hack_data
            total_stolen = hack_data.get("total_stolen_usd", 0) if isinstance(hack_data, dict) else 0
        except (json.JSONDecodeError, TypeError):
            pass

    # Parse audit status
    has_audit = False
    if protocol.get("audit_status"):
        try:
            audit_data = json.loads(protocol["audit_status"]) if isinstance(protocol["audit_status"], str) else protocol["audit_status"]
            audits = audit_data.get("audits", []) if isinstance(audit_data, dict) else audit_data
            has_audit = len(audits) > 0 if isinstance(audits, list) else bool(audits)
        except (json.JSONDecodeError, TypeError):
            pass

    # Parse chains
    chains = []
    if protocol.get("chains"):
        try:
            chains = json.loads(protocol["chains"]) if isinstance(protocol["chains"], str) else protocol["chains"]
        except (json.JSONDecodeError, TypeError):
            pass

    # ── Security (30%) ────────────────────────────────────
    security = 0

    # Audit status
    security += 30 if has_audit else 0

    # Hack history penalty
    if len(hacks) > 0:
        security -= min(len(hacks) * 15, 40)
        # Extra penalty for large hacks
        if total_stolen > 100_000_000:
            security -= 20
        elif total_stolen > 10_000_000:
            security -= 10

    # TVL as security proxy (more TVL = more scrutiny, more to lose)
    if tvl > 1_000_000_000:
        security += 25
    elif tvl > 100_000_000:
        security += 20
    elif tvl > 10_000_000:
        security += 15
    elif tvl > 1_000_000:
        security += 10
    elif tvl > 100_000:
        security += 5

    # Multi-chain = more audited deployments
    security += clamp(len(chains) * 3, 0, 15)

    security = clamp(security)

    # ── Compliance (25%) ──────────────────────────────────
    compliance = 0

    # Has website
    compliance += bool_score(protocol.get("url"), 15)

    # Has social presence
    compliance += bool_score(protocol.get("twitter"), 15)
    compliance += bool_score(protocol.get("github"), 15)

    # Audit = compliance effort
    compliance += 20 if has_audit else 0

    # TVL implies institutional trust
    if tvl > 1_000_000_000:
        compliance += 25
    elif tvl > 100_000_000:
        compliance += 20
    elif tvl > 10_000_000:
        compliance += 15
    elif tvl > 1_000_000:
        compliance += 10

    # No hack history = clean record
    if len(hacks) == 0:
        compliance += 15

    compliance = clamp(compliance)

    # ── Maintenance (20%) ─────────────────────────────────
    maintenance = 0

    # TVL change 1d — active and not collapsing
    change_1d = protocol.get("tvl_change_1d")
    if change_1d is not None:
        maintenance += 15  # has recent data = active
        if change_1d > -10:
            maintenance += 10  # not in freefall

    # TVL change 7d
    change_7d = protocol.get("tvl_change_7d")
    if change_7d is not None:
        if change_7d > 0:
            maintenance += 15  # growing
        elif change_7d > -20:
            maintenance += 10  # stable
        else:
            maintenance += 3   # declining but alive

    # Has GitHub
    maintenance += bool_score(protocol.get("github"), 20)

    # Has twitter (team communicates)
    maintenance += bool_score(protocol.get("twitter"), 10)

    # TVL > 0 means operational
    if tvl > 0:
        maintenance += 15

    maintenance = clamp(maintenance)

    # ── Popularity (15%) ──────────────────────────────────
    popularity = 0

    # TVL-based popularity
    if tvl > 10_000_000_000:
        popularity += 50
    elif tvl > 1_000_000_000:
        popularity += 40
    elif tvl > 100_000_000:
        popularity += 30
    elif tvl > 10_000_000:
        popularity += 25
    elif tvl > 1_000_000:
        popularity += 18
    elif tvl > 100_000:
        popularity += 10
    elif tvl > 0:
        popularity += 5

    # Multi-chain = more users
    popularity += clamp(len(chains) * 5, 0, 25)

    # Category bonus (DEXs and Lending = high usage)
    cat = (protocol.get("category") or "").lower()
    if cat in ("dexs", "lending", "liquid staking", "bridge"):
        popularity += 15
    elif cat in ("yield", "derivatives", "cdp"):
        popularity += 10

    popularity = clamp(popularity)

    # ── Ecosystem (10%) ───────────────────────────────────
    ecosystem = 0

    # Multi-chain deployment
    if len(chains) >= 10:
        ecosystem += 40
    elif len(chains) >= 5:
        ecosystem += 30
    elif len(chains) >= 3:
        ecosystem += 25
    elif len(chains) >= 2:
        ecosystem += 15
    elif len(chains) >= 1:
        ecosystem += 8

    # Category depth
    if cat:
        ecosystem += 15

    # GitHub = open source ecosystem
    ecosystem += bool_score(protocol.get("github"), 20)

    # TVL implies ecosystem integration
    if tvl > 100_000_000:
        ecosystem += 25
    elif tvl > 10_000_000:
        ecosystem += 15
    elif tvl > 1_000_000:
        ecosystem += 10

    ecosystem = clamp(ecosystem)

    # ── Weighted Total ────────────────────────────────────
    total = (
        security * 0.30 +
        compliance * 0.25 +
        maintenance * 0.20 +
        popularity * 0.15 +
        ecosystem * 0.10
    )

    return {
        "trust_score": round(total, 1),
        "trust_grade": score_to_grade(total),
        "security_score": round(security, 1),
        "compliance_score": round(compliance, 1),
        "maintenance_score": round(maintenance, 1),
        "popularity_score": round(popularity, 1),
        "ecosystem_score": round(ecosystem, 1),
    }


# ── Batch Scoring ─────────────────────────────────────────────────

def score_all_tokens():
    """Score all tokens in the database."""
    print("\n🪙  SCORING TOKENS")
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    rows = conn.execute("SELECT * FROM crypto_tokens").fetchall()
    print(f"   {len(rows)} tokens to score\n")

    scored = 0
    for row in rows:
        token = dict(row)
        scores = score_token(token)

        conn.execute("""
            UPDATE crypto_tokens SET
                trust_score = ?, trust_grade = ?,
                security_score = ?, compliance_score = ?,
                maintenance_score = ?, popularity_score = ?,
                ecosystem_score = ?, scored_at = ?
            WHERE id = ?
        """, (
            scores["trust_score"], scores["trust_grade"],
            scores["security_score"], scores["compliance_score"],
            scores["maintenance_score"], scores["popularity_score"],
            scores["ecosystem_score"], now,
            token["id"]
        ))
        scored += 1

        if scored % 5000 == 0:
            conn.commit()
            print(f"   💾 {scored} tokens scored...")

    conn.commit()
    conn.close()
    print(f"✅ {scored} tokens scored")
    return scored


def score_all_exchanges():
    """Score all exchanges in the database."""
    print("\n🏦 SCORING EXCHANGES")
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    rows = conn.execute("SELECT * FROM crypto_exchanges").fetchall()
    print(f"   {len(rows)} exchanges to score\n")

    scored = 0
    for row in rows:
        ex = dict(row)
        scores = score_exchange(ex)

        conn.execute("""
            UPDATE crypto_exchanges SET
                trust_score = ?, trust_grade = ?,
                security_score = ?, compliance_score = ?,
                maintenance_score = ?, popularity_score = ?,
                ecosystem_score = ?, scored_at = ?
            WHERE id = ?
        """, (
            scores["trust_score"], scores["trust_grade"],
            scores["security_score"], scores["compliance_score"],
            scores["maintenance_score"], scores["popularity_score"],
            scores["ecosystem_score"], now,
            ex["id"]
        ))
        scored += 1

    conn.commit()
    conn.close()
    print(f"✅ {scored} exchanges scored")
    return scored


def score_all_defi():
    """Score all DeFi protocols in the database."""
    print("\n🏗️  SCORING DEFI PROTOCOLS")
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    rows = conn.execute("SELECT * FROM crypto_defi_protocols").fetchall()
    print(f"   {len(rows)} protocols to score\n")

    scored = 0
    for row in rows:
        protocol = dict(row)
        scores = score_defi(protocol)

        conn.execute("""
            UPDATE crypto_defi_protocols SET
                trust_score = ?, trust_grade = ?,
                security_score = ?, compliance_score = ?,
                maintenance_score = ?, popularity_score = ?,
                ecosystem_score = ?, scored_at = ?
            WHERE id = ?
        """, (
            scores["trust_score"], scores["trust_grade"],
            scores["security_score"], scores["compliance_score"],
            scores["maintenance_score"], scores["popularity_score"],
            scores["ecosystem_score"], now,
            protocol["id"]
        ))
        scored += 1

        if scored % 2000 == 0:
            conn.commit()
            print(f"   💾 {scored} protocols scored...")

    conn.commit()
    conn.close()
    print(f"✅ {scored} DeFi protocols scored")
    return scored


# ── Stats & Distribution ─────────────────────────────────────────

def print_stats():
    """Print comprehensive scoring statistics."""
    conn = get_db()

    print("\n" + "=" * 60)
    print("  NERQ CRYPTO TRUST SCORE — DISTRIBUTION")
    print("=" * 60)

    for table, label in [
        ("crypto_tokens", "TOKENS"),
        ("crypto_exchanges", "EXCHANGES"),
        ("crypto_defi_protocols", "DEFI PROTOCOLS")
    ]:
        total = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()["c"]
        scored = conn.execute(f"SELECT COUNT(*) as c FROM {table} WHERE trust_score IS NOT NULL").fetchone()["c"]

        if scored == 0:
            print(f"\n📊 {label}: {total} total, 0 scored")
            continue

        avg = conn.execute(f"SELECT AVG(trust_score) as a FROM {table} WHERE trust_score IS NOT NULL").fetchone()["a"]
        median_row = conn.execute(f"""
            SELECT trust_score FROM {table} WHERE trust_score IS NOT NULL 
            ORDER BY trust_score LIMIT 1 OFFSET {scored // 2}
        """).fetchone()
        median = median_row["trust_score"] if median_row else 0

        print(f"\n📊 {label}: {scored:,} scored (avg: {avg:.1f}, median: {median:.1f})")

        # Grade distribution
        grades = conn.execute(f"""
            SELECT trust_grade, COUNT(*) as c FROM {table} 
            WHERE trust_grade IS NOT NULL 
            GROUP BY trust_grade ORDER BY 
            CASE trust_grade 
                WHEN 'A+' THEN 1 WHEN 'A' THEN 2 WHEN 'B+' THEN 3 
                WHEN 'B' THEN 4 WHEN 'C+' THEN 5 WHEN 'C' THEN 6 
                WHEN 'D+' THEN 7 WHEN 'D' THEN 8 WHEN 'F' THEN 9 
            END
        """).fetchall()

        for g in grades:
            pct = (g["c"] / scored) * 100
            bar = "█" * int(pct / 2)
            print(f"   {g['trust_grade']:>3}: {g['c']:>6,} ({pct:5.1f}%) {bar}")

        # Top 5
        name_col = "name"
        top = conn.execute(f"""
            SELECT {name_col}, trust_score, trust_grade FROM {table} 
            WHERE trust_score IS NOT NULL 
            ORDER BY trust_score DESC LIMIT 5
        """).fetchall()

        print(f"\n   Top 5 {label.lower()}:")
        for t in top:
            print(f"     {t['trust_grade']} ({t['trust_score']:5.1f}) — {t['name']}")

        # Bottom 5
        bottom = conn.execute(f"""
            SELECT {name_col}, trust_score, trust_grade FROM {table} 
            WHERE trust_score IS NOT NULL 
            ORDER BY trust_score ASC LIMIT 5
        """).fetchall()

        print(f"   Bottom 5 {label.lower()}:")
        for t in bottom:
            print(f"     {t['trust_grade']} ({t['trust_score']:5.1f}) — {t['name']}")

    conn.close()


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Nerq Crypto Trust Score Engine")
    parser.add_argument("--tokens-only", action="store_true")
    parser.add_argument("--exchanges-only", action="store_true")
    parser.add_argument("--defi-only", action="store_true")
    parser.add_argument("--stats", action="store_true", help="Print score distribution")
    args = parser.parse_args()

    init_db()

    if args.stats:
        print_stats()
        return

    print("=" * 60)
    print("  NERQ CRYPTO TRUST SCORE ENGINE")
    print(f"  Dimensions: Security(30%) Compliance(25%) Maintenance(20%)")
    print(f"              Popularity(15%) Ecosystem(10%)")
    print(f"  Started: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    start = time.time()
    score_all = not (args.tokens_only or args.exchanges_only or args.defi_only)

    if score_all or args.tokens_only:
        score_all_tokens()
    if score_all or args.exchanges_only:
        score_all_exchanges()
    if score_all or args.defi_only:
        score_all_defi()

    elapsed = time.time() - start
    print(f"\n⏱️  Total scoring time: {elapsed:.1f} seconds")

    print_stats()


if __name__ == "__main__":
    main()
