#!/usr/bin/env python3
"""
Website Tranco Seeder — seeds top 10K websites from Tranco list.
Trust scores based on Tranco rank + known site data.

Run: python3 -m agentindex.crawlers.website_tranco_seeder [limit]
"""

import csv
import logging
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
log = logging.getLogger("website_tranco")

TRANCO_CSV = "/tmp/top-1m.csv"
BATCH_SIZE = 500

# Skip infrastructure/CDN/API domains (not consumer-facing websites)
SKIP_DOMAINS = {
    "gtld-servers.net", "googleapis.com", "gstatic.com", "cloudflare.com",
    "akamaiedge.net", "akamaitechnologies.com", "cloudfront.net",
    "amazonaws.com", "azure.com", "azurewebsites.net", "github.io",
    "googleusercontent.com", "googlevideo.com", "doubleclick.net",
    "googlesyndication.com", "googleadservices.com", "google-analytics.com",
    "facebook.net", "fbcdn.net", "fbsbx.com", "instagram.com",
    "cdninstagram.com", "whatsapp.net", "oculus.com",
    "apple-dns.net", "icloud-content.com", "mzstatic.com",
    "trafficmanager.net", "msedge.net", "office.net", "outlook.com",
    "microsoftonline.com", "windows.net", "live.com",
    "root-servers.net", "verisign.com", "iana.org",
    "ntp.org", "pool.ntp.org",
}

# Known high-trust sites with curated descriptions
CURATED = {
    "google.com": {"score": 92, "desc": "World's largest search engine by Alphabet Inc. Handles 8.5B+ searches daily."},
    "youtube.com": {"score": 90, "desc": "Video sharing platform by Alphabet/Google. 2.5B+ monthly users."},
    "facebook.com": {"score": 78, "desc": "Social network by Meta Platforms. 3B+ monthly active users."},
    "amazon.com": {"score": 88, "desc": "Largest e-commerce marketplace. Public company (AMZN). A-to-z Guarantee."},
    "twitter.com": {"score": 55, "desc": "Social media platform. Owned by X Corp (Elon Musk). Content moderation changes since 2022."},
    "x.com": {"score": 55, "desc": "Social media platform (formerly Twitter). Owned by X Corp."},
    "wikipedia.org": {"score": 92, "desc": "Free encyclopedia. Non-profit Wikimedia Foundation. 60M+ articles."},
    "reddit.com": {"score": 75, "desc": "Social news aggregation platform. Public company (RDDT)."},
    "tiktok.com": {"score": 58, "desc": "Short-form video platform. ByteDance-owned. Data privacy concerns."},
    "netflix.com": {"score": 90, "desc": "Streaming entertainment. Public company (NFLX). 260M+ subscribers."},
    "linkedin.com": {"score": 85, "desc": "Professional networking. Microsoft-owned. 900M+ members."},
    "pinterest.com": {"score": 80, "desc": "Visual discovery platform. Public company (PINS)."},
    "instagram.com": {"score": 75, "desc": "Photo/video social network. Meta-owned. 2B+ monthly users."},
    "whatsapp.com": {"score": 78, "desc": "Messaging app. Meta-owned. End-to-end encrypted. 2B+ users."},
    "spotify.com": {"score": 88, "desc": "Music streaming. Public company (SPOT). 600M+ users."},
    "ebay.com": {"score": 82, "desc": "Online marketplace. Public company (EBAY). Money Back Guarantee."},
    "walmart.com": {"score": 90, "desc": "Largest retailer. Public company (WMT). Physical stores worldwide."},
    "paypal.com": {"score": 85, "desc": "Online payments. Public company (PYPL). Buyer/seller protection."},
    "twitch.tv": {"score": 80, "desc": "Live streaming platform. Amazon-owned. Focus on gaming."},
    "temu.com": {"score": 52, "desc": "Chinese e-commerce by PDD Holdings. Low prices. Mixed reviews."},
    "shein.com": {"score": 48, "desc": "Fast fashion from Singapore/China. Environmental/labor concerns."},
    "aliexpress.com": {"score": 55, "desc": "International marketplace by Alibaba. Direct-from-China."},
    "wish.com": {"score": 35, "desc": "Discount e-commerce. Misleading product images. Long shipping."},
}


def score_from_rank(rank):
    """Compute trust score from Tranco rank."""
    if rank <= 100: return 85
    if rank <= 500: return 80
    if rank <= 1000: return 75
    if rank <= 5000: return 70
    if rank <= 10000: return 65
    return 60


def grade_from_score(score):
    if score >= 90: return "A+"
    if score >= 85: return "A"
    if score >= 80: return "A-"
    if score >= 75: return "B+"
    if score >= 70: return "B"
    if score >= 65: return "B-"
    if score >= 60: return "C+"
    if score >= 55: return "C"
    if score >= 50: return "C-"
    if score >= 40: return "D"
    return "F"


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10000

    if not Path(TRANCO_CSV).exists():
        log.error(f"Tranco CSV not found: {TRANCO_CSV}")
        log.error("Download: curl -sL https://tranco-list.eu/top-1m.csv.zip -o /tmp/tranco.zip && cd /tmp && unzip tranco.zip")
        sys.exit(1)

    session = get_session()
    session.execute(text("SET statement_timeout = '10s'"))

    done = 0
    batch = 0

    with open(TRANCO_CSV) as f:
        reader = csv.reader(f)
        for row in reader:
            if done >= limit:
                break
            rank = int(row[0])
            domain = row[1].strip().lower()

            # Skip infrastructure domains
            if any(domain.endswith(s) or domain == s for s in SKIP_DOMAINS):
                continue

            # Skip domains with too many subdomains
            if domain.count(".") > 2:
                continue

            slug = re.sub(r'[^a-z0-9]+', '-', domain).strip('-')
            if not slug or len(slug) < 3:
                continue

            # Use curated data if available
            curated = CURATED.get(domain, {})
            score = curated.get("score", score_from_rank(rank))
            desc = curated.get("desc", f"Website ranked #{rank} globally by Tranco.")
            grade = grade_from_score(score)
            is_king = rank <= 1000

            try:
                session.execute(text("""
                    INSERT INTO software_registry
                        (id, name, slug, registry, description, trust_score, trust_grade,
                         enriched_at, created_at, security_score, popularity_score, is_king, downloads)
                    VALUES (:id, :name, :slug, 'website', :desc, :score, :grade,
                            NOW(), NOW(), :sec, :pop, :king, :rank)
                    ON CONFLICT (registry, slug) DO UPDATE SET
                        description = COALESCE(NULLIF(EXCLUDED.description, ''), software_registry.description),
                        trust_score = GREATEST(COALESCE(software_registry.trust_score, 0), EXCLUDED.trust_score),
                        trust_grade = CASE WHEN EXCLUDED.trust_score > COALESCE(software_registry.trust_score, 0)
                                      THEN EXCLUDED.trust_grade ELSE software_registry.trust_grade END,
                        is_king = EXCLUDED.is_king OR software_registry.is_king,
                        downloads = EXCLUDED.downloads,
                        enriched_at = NOW()
                """), {
                    "id": str(uuid.uuid4()),
                    "name": domain,
                    "slug": slug,
                    "desc": desc[:500],
                    "score": score,
                    "grade": grade,
                    "sec": score,
                    "pop": min(95, 100 - rank // 200) if rank < 10000 else 60,
                    "king": is_king,
                    "rank": rank,
                })
                done += 1
                batch += 1
            except Exception as e:
                log.warning(f"Error {domain}: {e}")
                session.rollback()

            if batch >= BATCH_SIZE:
                session.commit()
                log.info(f"Progress: {done}/{limit} (rank {rank})")
                batch = 0

    if batch > 0:
        session.commit()

    session.close()
    log.info(f"Website Tranco seeder complete: {done} websites seeded")


if __name__ == "__main__":
    main()
