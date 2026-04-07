#!/usr/bin/env python3
"""Website Seeds — inserts top 100 websites into software_registry with trust scores.

One-time seed script. All data is hardcoded. No external API calls.

Usage:
    python3 -m agentindex.crawlers.website_seeds
"""
import sys, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
log = logging.getLogger("website_seeds")

WEBSITES = [
    # ── E-commerce ──────────────────────────────────────────────────────
    {"name": "Temu", "slug": "temu", "score": 52, "grade": "C-",
     "desc": "Chinese e-commerce marketplace owned by PDD Holdings. Low prices, direct-from-manufacturer. Mixed reviews on quality and shipping times.", "cat": "e-commerce"},
    {"name": "Shein", "slug": "shein", "score": 48, "grade": "D",
     "desc": "Fast fashion e-commerce platform based in Singapore (Chinese-founded). Known for extremely low prices and environmental/labor concerns.", "cat": "e-commerce"},
    {"name": "AliExpress", "slug": "aliexpress", "score": 55, "grade": "C",
     "desc": "International e-commerce marketplace by Alibaba Group. Direct-from-China marketplace with buyer protection.", "cat": "e-commerce"},
    {"name": "Amazon", "slug": "amazon", "score": 88, "grade": "A",
     "desc": "Largest e-commerce marketplace globally. Public company (AMZN). A-to-z Guarantee buyer protection.", "cat": "e-commerce"},
    {"name": "eBay", "slug": "ebay", "score": 82, "grade": "A-",
     "desc": "Global online marketplace for new and used goods. Public company (EBAY). Money Back Guarantee.", "cat": "e-commerce"},
    {"name": "Walmart", "slug": "walmart", "score": 90, "grade": "A+",
     "desc": "Largest retailer globally with online marketplace. Public company (WMT). Physical stores in 19 countries.", "cat": "e-commerce"},
    {"name": "Etsy", "slug": "etsy", "score": 78, "grade": "B+",
     "desc": "Marketplace for handmade, vintage, and craft supplies. Public company (ETSY). Purchase Protection program.", "cat": "e-commerce"},
    {"name": "Wish", "slug": "wish", "score": 35, "grade": "F",
     "desc": "Discount e-commerce platform. Known for misleading product images and long shipping times. Delisted from major app stores in France.", "cat": "e-commerce"},
    {"name": "DHgate", "slug": "dhgate", "score": 42, "grade": "D",
     "desc": "Chinese wholesale e-commerce platform. B2B focus with consumer sales. Buyer protection varies.", "cat": "e-commerce"},
    {"name": "Banggood", "slug": "banggood", "score": 45, "grade": "D",
     "desc": "Chinese e-commerce retailer. Direct shipping from China warehouses. Variable product quality.", "cat": "e-commerce"},
    {"name": "StockX", "slug": "stockx", "score": 72, "grade": "B",
     "desc": "Authentication-first marketplace for sneakers, streetwear, electronics. Verification process for all items.", "cat": "e-commerce"},
    {"name": "Mercari", "slug": "mercari", "score": 70, "grade": "B",
     "desc": "Peer-to-peer marketplace app. Japanese company (TSE: 4385). Buyer/seller protection.", "cat": "e-commerce"},
    {"name": "Poshmark", "slug": "poshmark", "score": 72, "grade": "B",
     "desc": "Social commerce marketplace for fashion. Acquired by Naver (2023). Posh Protect buyer guarantee.", "cat": "e-commerce"},
    {"name": "Cider", "slug": "cider", "score": 40, "grade": "D",
     "desc": "Fast fashion brand targeting Gen Z. Chinese-founded. Limited transparency on manufacturing.", "cat": "e-commerce"},
    {"name": "Halara", "slug": "halara", "score": 42, "grade": "D",
     "desc": "Activewear brand. Chinese-founded. Low prices, mixed quality reviews.", "cat": "e-commerce"},
    {"name": "Romwe", "slug": "romwe", "score": 40, "grade": "D",
     "desc": "Fast fashion retailer, subsidiary of Shein Group. Data breach history (2018).", "cat": "e-commerce"},
    {"name": "Fashion Nova", "slug": "fashion-nova", "score": 55, "grade": "C",
     "desc": "US-based fast fashion brand. FTC fine for suppressing negative reviews (2022). Los Angeles headquartered.", "cat": "e-commerce"},
    {"name": "TikTok Shop", "slug": "tiktok-shop", "score": 58, "grade": "C+",
     "desc": "In-app shopping feature on TikTok. ByteDance-owned. Buyer protection program. Data privacy concerns.", "cat": "e-commerce"},
    {"name": "Facebook Marketplace", "slug": "facebook-marketplace", "score": 60, "grade": "C+",
     "desc": "Peer-to-peer marketplace integrated into Facebook. Meta-owned. Limited buyer protection for non-shipped items.", "cat": "e-commerce"},

    # ── Finance ─────────────────────────────────────────────────────────
    {"name": "PayPal", "slug": "paypal", "score": 85, "grade": "A",
     "desc": "Online payment platform. Public company (PYPL). Buyer/seller protection. Licensed money transmitter.", "cat": "finance"},
    {"name": "Venmo", "slug": "venmo", "score": 80, "grade": "A-",
     "desc": "Peer-to-peer payment app owned by PayPal. FDIC-insured through partner banks.", "cat": "finance"},
    {"name": "Cash App", "slug": "cash-app", "score": 75, "grade": "B+",
     "desc": "Mobile payment service by Block Inc (formerly Square). Public company (SQ). Bitcoin trading feature.", "cat": "finance"},
    {"name": "Robinhood", "slug": "robinhood", "score": 70, "grade": "B",
     "desc": "Commission-free stock trading app. Public company (HOOD). SIPC protection. SEC/FINRA regulated.", "cat": "finance"},
    {"name": "Coinbase", "slug": "coinbase", "score": 75, "grade": "B+",
     "desc": "Cryptocurrency exchange. Public company (COIN). Licensed in multiple jurisdictions. Insurance for digital assets.", "cat": "finance"},
    {"name": "Binance", "slug": "binance", "score": 50, "grade": "C-",
     "desc": "Cryptocurrency exchange. DOJ settlement (2023). CEO Changpeng Zhao pleaded guilty to AML violations.", "cat": "finance"},
    {"name": "Zelle", "slug": "zelle", "score": 78, "grade": "B+",
     "desc": "Bank-to-bank transfer service. Operated by Early Warning Services (bank consortium). No buyer protection.", "cat": "finance"},
    {"name": "Wise", "slug": "wise", "score": 82, "grade": "A-",
     "desc": "International money transfer service. Public company (LSE: WISE). FCA regulated. Transparent fee structure.", "cat": "finance"},
    {"name": "Stripe", "slug": "stripe", "score": 88, "grade": "A",
     "desc": "Payment processing platform for internet businesses. PCI Level 1 certified. SOC 2 compliant.", "cat": "finance"},
    {"name": "Revolut", "slug": "revolut", "score": 72, "grade": "B",
     "desc": "Digital banking app. UK-based fintech. Banking license in multiple EU countries. 40M+ customers.", "cat": "finance"},
    {"name": "Chime", "slug": "chime", "score": 70, "grade": "B",
     "desc": "US neobank. FDIC-insured through partner banks. No-fee overdraft up to $200. No physical branches.", "cat": "finance"},

    # ── Streaming / Entertainment ───────────────────────────────────────
    {"name": "Netflix", "slug": "netflix", "score": 90, "grade": "A+",
     "desc": "Streaming entertainment service. Public company (NFLX). 260M+ subscribers worldwide.", "cat": "entertainment"},
    {"name": "Spotify", "slug": "spotify", "score": 88, "grade": "A",
     "desc": "Music and podcast streaming platform. Public company (SPOT). 600M+ users.", "cat": "entertainment"},
    {"name": "Disney+", "slug": "disney-plus", "score": 88, "grade": "A",
     "desc": "Streaming service by The Walt Disney Company (DIS). Family-friendly content.", "cat": "entertainment"},
    {"name": "YouTube", "slug": "youtube", "score": 90, "grade": "A+",
     "desc": "Video sharing platform. Owned by Alphabet/Google (GOOGL). 2.5B+ monthly users.", "cat": "entertainment"},
    {"name": "Twitch", "slug": "twitch", "score": 82, "grade": "A-",
     "desc": "Live streaming platform. Owned by Amazon. Focus on gaming and creative content.", "cat": "entertainment"},
    {"name": "Hulu", "slug": "hulu", "score": 82, "grade": "A-",
     "desc": "Streaming service. Majority owned by Disney. Live TV option. US-only.", "cat": "entertainment"},
    {"name": "HBO Max", "slug": "hbo-max", "score": 85, "grade": "A",
     "desc": "Streaming service by Warner Bros. Discovery (WBD). Premium content library.", "cat": "entertainment"},
    {"name": "Peacock", "slug": "peacock", "score": 78, "grade": "B+",
     "desc": "Streaming service by NBCUniversal (Comcast). Free tier available. Live sports.", "cat": "entertainment"},
    {"name": "Apple TV+", "slug": "apple-tv-plus", "score": 90, "grade": "A+",
     "desc": "Streaming service by Apple Inc (AAPL). Original content focus. Bundled with Apple One.", "cat": "entertainment"},

    # ── Social Media ────────────────────────────────────────────────────
    {"name": "Reddit", "slug": "reddit", "score": 75, "grade": "B+",
     "desc": "Social news aggregation and discussion platform. Public company (RDDT).", "cat": "social"},
    {"name": "X (Twitter)", "slug": "twitter", "score": 55, "grade": "C",
     "desc": "Social media platform. Owned by X Corp (Elon Musk). Formerly Twitter. Content moderation changes since 2022 acquisition.", "cat": "social"},
    {"name": "LinkedIn", "slug": "linkedin", "score": 85, "grade": "A",
     "desc": "Professional networking platform. Owned by Microsoft. 900M+ members.", "cat": "social"},
    {"name": "Pinterest", "slug": "pinterest", "score": 80, "grade": "A-",
     "desc": "Visual discovery platform. Public company (PINS). Family-safe content focus.", "cat": "social"},
    {"name": "Snapchat", "slug": "snapchat", "score": 72, "grade": "B",
     "desc": "Multimedia messaging app. Public company (SNAP). Privacy-focused ephemeral messaging.", "cat": "social"},
    {"name": "Telegram", "slug": "telegram-web", "score": 60, "grade": "C+",
     "desc": "Cloud-based messaging service. UAE-based. End-to-end encryption optional (secret chats only).", "cat": "social"},
    {"name": "Discord", "slug": "discord-web", "score": 72, "grade": "B",
     "desc": "Communication platform for communities. US-based. Voice, video, and text. Safety concerns for minors.", "cat": "social"},
    {"name": "WhatsApp", "slug": "whatsapp-web", "score": 78, "grade": "B+",
     "desc": "Messaging app by Meta. End-to-end encrypted. 2B+ users. Metadata sharing with Meta.", "cat": "social"},
    {"name": "TikTok", "slug": "tiktok", "score": 58, "grade": "C+",
     "desc": "Short-form video platform. ByteDance-owned. Data privacy and national security concerns in US/EU.", "cat": "social"},
    {"name": "Threads", "slug": "threads", "score": 72, "grade": "B",
     "desc": "Text-based social media by Meta. Instagram companion app. ActivityPub federation planned.", "cat": "social"},

    # ── Education ───────────────────────────────────────────────────────
    {"name": "Coursera", "slug": "coursera", "score": 85, "grade": "A",
     "desc": "Online learning platform. Public company (COUR). Partnerships with 300+ universities.", "cat": "education"},
    {"name": "Udemy", "slug": "udemy", "score": 78, "grade": "B+",
     "desc": "Online learning marketplace. Acquired by Prosus (2024). 70M+ learners.", "cat": "education"},
    {"name": "Khan Academy", "slug": "khan-academy", "score": 92, "grade": "A+",
     "desc": "Non-profit educational platform. Free courses for all ages. COPPA compliant.", "cat": "education"},
    {"name": "Duolingo", "slug": "duolingo", "score": 85, "grade": "A",
     "desc": "Language learning app. Public company (DUOL). Gamified learning. COPPA compliant.", "cat": "education"},
    {"name": "Skillshare", "slug": "skillshare", "score": 72, "grade": "B",
     "desc": "Online learning community for creative skills. Subscription-based. 30K+ classes.", "cat": "education"},
    {"name": "MasterClass", "slug": "masterclass", "score": 75, "grade": "B+",
     "desc": "Online learning platform featuring celebrity instructors. Premium pricing. High production quality.", "cat": "education"},

    # ── Travel ──────────────────────────────────────────────────────────
    {"name": "Booking.com", "slug": "booking-com", "score": 82, "grade": "A-",
     "desc": "Online travel agency. Booking Holdings (BKNG). Covers 220+ countries.", "cat": "travel"},
    {"name": "Airbnb", "slug": "airbnb", "score": 78, "grade": "B+",
     "desc": "Short-term rental marketplace. Public company (ABNB). Host and guest protection.", "cat": "travel"},
    {"name": "Expedia", "slug": "expedia", "score": 80, "grade": "A-",
     "desc": "Online travel company. Public company (EXPE). Covers flights, hotels, car rentals.", "cat": "travel"},
    {"name": "Tripadvisor", "slug": "tripadvisor", "score": 78, "grade": "B+",
     "desc": "Travel guidance platform. Public company (TRIP). 1B+ reviews and opinions.", "cat": "travel"},
    {"name": "Kayak", "slug": "kayak", "score": 80, "grade": "A-",
     "desc": "Travel search engine. Owned by Booking Holdings. Aggregates prices from hundreds of sites.", "cat": "travel"},

    # ── Food Delivery ───────────────────────────────────────────────────
    {"name": "DoorDash", "slug": "doordash", "score": 75, "grade": "B+",
     "desc": "Food delivery platform. Public company (DASH). Operates in US, Canada, Australia, Japan.", "cat": "food"},
    {"name": "Uber Eats", "slug": "uber-eats", "score": 78, "grade": "B+",
     "desc": "Food delivery by Uber Technologies (UBER). Available in 6,000+ cities.", "cat": "food"},
    {"name": "Instacart", "slug": "instacart", "score": 76, "grade": "B+",
     "desc": "Grocery delivery platform. Public company (CART). Partners with 1,400+ retailers.", "cat": "food"},
    {"name": "Grubhub", "slug": "grubhub", "score": 72, "grade": "B",
     "desc": "Food delivery platform. Owned by Just Eat Takeaway. FTC lawsuit over deceptive practices (2022).", "cat": "food"},

    # ── Cloud / Tech / Productivity ─────────────────────────────────────
    {"name": "Dropbox", "slug": "dropbox", "score": 82, "grade": "A-",
     "desc": "Cloud storage service. Public company (DBX). SOC 2 certified. 700M+ users.", "cat": "cloud"},
    {"name": "Notion", "slug": "notion", "score": 80, "grade": "A-",
     "desc": "Productivity and note-taking app. SOC 2 Type II certified. 100M+ users.", "cat": "productivity"},
    {"name": "Canva", "slug": "canva", "score": 82, "grade": "A-",
     "desc": "Online design platform. Australian company. 170M+ monthly users. SOC 2 compliant.", "cat": "design"},
    {"name": "Zoom", "slug": "zoom", "score": 80, "grade": "A-",
     "desc": "Video conferencing platform. Public company (ZM). End-to-end encryption available.", "cat": "communication"},
    {"name": "Slack", "slug": "slack-web", "score": 85, "grade": "A",
     "desc": "Business communication platform. Owned by Salesforce (CRM). SOC 2/3 certified.", "cat": "communication"},
    {"name": "Google Drive", "slug": "google-drive", "score": 90, "grade": "A+",
     "desc": "Cloud storage by Alphabet/Google (GOOGL). SOC 2/3, ISO 27001 certified. 15GB free.", "cat": "cloud"},
    {"name": "Microsoft 365", "slug": "microsoft-365", "score": 90, "grade": "A+",
     "desc": "Productivity suite by Microsoft (MSFT). SOC 2, ISO 27001 certified. 400M+ paid seats.", "cat": "productivity"},
    {"name": "iCloud", "slug": "icloud", "score": 88, "grade": "A",
     "desc": "Cloud services by Apple Inc (AAPL). End-to-end encryption for most data types. SOC 2 certified.", "cat": "cloud"},
    {"name": "GitHub", "slug": "github-web", "score": 90, "grade": "A+",
     "desc": "Code hosting platform. Owned by Microsoft. 100M+ developers. SOC 2 Type II certified.", "cat": "developer"},

    # ── Dating ──────────────────────────────────────────────────────────
    {"name": "Tinder", "slug": "tinder", "score": 60, "grade": "C+",
     "desc": "Dating app by Match Group (MTCH). Photo verification feature. Reports of bot/scam profiles.", "cat": "dating"},
    {"name": "Bumble", "slug": "bumble", "score": 65, "grade": "B-",
     "desc": "Dating app. Public company (BMBL). Women-first approach. Photo verification.", "cat": "dating"},
    {"name": "Hinge", "slug": "hinge", "score": 65, "grade": "B-",
     "desc": "Dating app by Match Group (MTCH). Designed for serious relationships. Video profiles.", "cat": "dating"},

    # ── Controversial / frequently-searched ─────────────────────────────
    {"name": "OnlyFans", "slug": "onlyfans", "score": 55, "grade": "C",
     "desc": "Content subscription platform. UK-based. Creator monetization. Age verification required.", "cat": "social"},
    {"name": "ChatGPT", "slug": "chatgpt-web", "score": 85, "grade": "A",
     "desc": "AI chatbot by OpenAI. SOC 2 compliant. Data usage policies for training.", "cat": "ai"},
    {"name": "Perplexity", "slug": "perplexity-web", "score": 78, "grade": "B+",
     "desc": "AI-powered search engine. US-based startup. Cites sources in responses.", "cat": "ai"},

    # ── Gaming ──────────────────────────────────────────────────────────
    {"name": "Steam", "slug": "steam-web", "score": 88, "grade": "A",
     "desc": "PC gaming platform by Valve Corporation. 130M+ monthly active users. Refund policy.", "cat": "gaming"},
    {"name": "Epic Games Store", "slug": "epic-games-store", "score": 78, "grade": "B+",
     "desc": "PC game store by Epic Games. Free weekly games. Unreal Engine maker.", "cat": "gaming"},
    {"name": "Roblox", "slug": "roblox", "score": 68, "grade": "B-",
     "desc": "Gaming platform. Public company (RBLX). Popular with children. COPPA concerns and child safety issues.", "cat": "gaming"},

    # ── Health / Fitness ────────────────────────────────────────────────
    {"name": "MyFitnessPal", "slug": "myfitnesspal", "score": 68, "grade": "B-",
     "desc": "Calorie counting and fitness app. Owned by Francisco Partners. Data breach in 2018 (150M users).", "cat": "health"},
    {"name": "Peloton", "slug": "peloton", "score": 70, "grade": "B",
     "desc": "Connected fitness platform. Public company (PTON). Hardware + subscription model.", "cat": "health"},

    # ── News / Media ────────────────────────────────────────────────────
    {"name": "Wikipedia", "slug": "wikipedia", "score": 92, "grade": "A+",
     "desc": "Free online encyclopedia. Wikimedia Foundation (non-profit). Community-edited. No ads.", "cat": "reference"},
    {"name": "Medium", "slug": "medium", "score": 72, "grade": "B",
     "desc": "Online publishing platform. Subscription model. Mix of professional and amateur content.", "cat": "media"},
    {"name": "Substack", "slug": "substack", "score": 72, "grade": "B",
     "desc": "Newsletter platform. Creator-owned subscriber lists. Content moderation debates.", "cat": "media"},

    # ── Real Estate ─────────────────────────────────────────────────────
    {"name": "Zillow", "slug": "zillow", "score": 80, "grade": "A-",
     "desc": "Real estate marketplace. Public company (Z/ZG). Zestimate home valuations. 200M+ monthly visits.", "cat": "real-estate"},
    {"name": "Redfin", "slug": "redfin", "score": 78, "grade": "B+",
     "desc": "Real estate brokerage. Public company (RDFN). Technology-powered agents. Lower commission fees.", "cat": "real-estate"},

    # ── Jobs / Freelance ────────────────────────────────────────────────
    {"name": "Indeed", "slug": "indeed", "score": 82, "grade": "A-",
     "desc": "Job search engine. Owned by Recruit Holdings (Japan). 350M+ monthly visitors.", "cat": "jobs"},
    {"name": "Glassdoor", "slug": "glassdoor", "score": 75, "grade": "B+",
     "desc": "Company review and job listing site. Owned by Recruit Holdings. Anonymous employee reviews.", "cat": "jobs"},
    {"name": "Fiverr", "slug": "fiverr", "score": 72, "grade": "B",
     "desc": "Freelance services marketplace. Public company (FVRR). Buyer protection. Global freelancer network.", "cat": "freelance"},
    {"name": "Upwork", "slug": "upwork", "score": 75, "grade": "B+",
     "desc": "Freelance talent marketplace. Public company (UPWK). Payment protection. Escrow system.", "cat": "freelance"},

    # ── Ride-hailing / Transport ────────────────────────────────────────
    {"name": "Uber", "slug": "uber", "score": 78, "grade": "B+",
     "desc": "Ride-hailing and delivery platform. Public company (UBER). Operates in 70+ countries. Safety features.", "cat": "transport"},
    {"name": "Lyft", "slug": "lyft", "score": 75, "grade": "B+",
     "desc": "Ride-hailing platform. Public company (LYFT). US and Canada. Safety features and driver screening.", "cat": "transport"},

    # ── AI tools ────────────────────────────────────────────────────────
    {"name": "Claude", "slug": "claude-web", "score": 85, "grade": "A",
     "desc": "AI assistant by Anthropic. SOC 2 Type II compliant. Constitutional AI safety approach.", "cat": "ai"},
    {"name": "Midjourney", "slug": "midjourney", "score": 72, "grade": "B",
     "desc": "AI image generation service. US-based. Discord-based interface. Content moderation policies.", "cat": "ai"},
    {"name": "Gemini", "slug": "gemini-web", "score": 85, "grade": "A",
     "desc": "AI assistant by Google DeepMind (Alphabet/GOOGL). Integrated with Google services.", "cat": "ai"},

    # ── Misc popular ────────────────────────────────────────────────────
    {"name": "Craigslist", "slug": "craigslist", "score": 52, "grade": "C-",
     "desc": "Classified ads website. Minimal moderation. No buyer protection. High scam risk for non-local transactions.", "cat": "classifieds"},
    {"name": "OfferUp", "slug": "offerup", "score": 62, "grade": "B-",
     "desc": "Local buying and selling marketplace. TruYou identity verification. In-app messaging. US-based.", "cat": "classifieds"},
]

assert len(WEBSITES) == 100, f"Expected 100 websites, got {len(WEBSITES)}"


def seed():
    """Insert all websites into software_registry."""
    log.info(f"Seeding {len(WEBSITES)} websites into software_registry")
    session = get_session()
    inserted = 0
    updated = 0

    for w in WEBSITES:
        sec = w["score"]       # security_score mirrors trust_score
        pop = 80               # top 100 sites by definition

        try:
            result = session.execute(text("""
                INSERT INTO software_registry
                    (name, slug, registry, description, trust_score, trust_grade,
                     enriched_at, created_at, security_score, popularity_score)
                VALUES
                    (:name, :slug, 'website', :desc, :score, :grade,
                     NOW(), NOW(), :sec, :pop)
                ON CONFLICT (registry, slug) DO UPDATE SET
                    description = EXCLUDED.description,
                    trust_score = EXCLUDED.trust_score,
                    trust_grade = EXCLUDED.trust_grade,
                    security_score = EXCLUDED.security_score,
                    popularity_score = EXCLUDED.popularity_score,
                    enriched_at = NOW()
            """), {
                "name": w["name"],
                "slug": w["slug"],
                "desc": w["desc"],
                "score": w["score"],
                "grade": w["grade"],
                "cat": w["cat"],
                "sec": sec,
                "pop": pop,
            })

            # xacts_committed rowcount: 1 = insert, also 1 on conflict update
            # We check if created_at changed to distinguish, but simpler to just count
            inserted += 1

        except Exception as e:
            log.error(f"Failed to upsert {w['name']}: {e}")
            session.rollback()
            continue

    session.commit()
    session.close()
    log.info(f"Website seed complete: {inserted} upserted")
    return inserted


if __name__ == "__main__":
    total = seed()
    log.info(f"Done. {total}/{len(WEBSITES)} websites seeded.")
