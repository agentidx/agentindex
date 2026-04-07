#!/usr/bin/env python3
"""Chrome Extension Crawler. Uses seed list + Chrome Web Store detail pages."""
import json, logging, sys, time, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("chrome_crawler")

# Seed list of top Chrome extensions (name, slug/id, category, est_users)
TOP_EXTENSIONS = [
    ("uBlock Origin", "cjpalhdlnbpafiamejdnhcphjbkeiagm", "ad_blocker", 40000000),
    ("Adblock Plus", "cfhdojbkjhnklbpkdaibdccddilifddb", "ad_blocker", 10000000),
    ("AdGuard AdBlocker", "bgnkhhnnamicmpeenaelnjfhikgbkllg", "ad_blocker", 8000000),
    ("Bitwarden", "nngceckbapebfimnlniiiahkandclblb", "password_manager", 5000000),
    ("LastPass", "hdokiejnpimakedhajhdlcegeplioahd", "password_manager", 10000000),
    ("1Password", "aeblfdkhhhdcdjpifhhbdiojplfjncoa", "password_manager", 3000000),
    ("Grammarly", "kbfnbcaeplbcioakkpcpgfkobkghlhen", "writing", 30000000),
    ("Honey", "bmnlcjabgnpnenekpadlanbbkooimhnj", "shopping", 17000000),
    ("React Developer Tools", "fmkadmapgofadopljbjfkapdkoienihi", "developer", 5000000),
    ("Vue.js devtools", "nhdogjmejiglipccpnnnanhbledajbpd", "developer", 2000000),
    ("Redux DevTools", "lmhkpmbekcpmknklioeibfkpmmfibljd", "developer", 3000000),
    ("JSON Formatter", "bcjindcccaagfpapjjmafapmmgkkhgoa", "developer", 3000000),
    ("Lighthouse", "blipmdconlkpinefehnmjammfjpmpbjk", "developer", 1000000),
    ("Wappalyzer", "gppongmhjkpfnbhagpmjfkannfbllamg", "developer", 2000000),
    ("HTTPS Everywhere", "gcbommkclmhbdakpeapbgbhloofkprog", "security", 5000000),
    ("Privacy Badger", "pkehgijcmpdhfbdbbnkijodmdjhbjlgp", "privacy", 3000000),
    ("Ghostery", "mlomiejdfkolichcflejclcbmpeaniij", "privacy", 2000000),
    ("Dark Reader", "eimadpbcbfnmbkopoojfekhnkhdbieeh", "accessibility", 6000000),
    ("Notion Web Clipper", "knheggckgoiihginacbkhaalnibhilkk", "productivity", 3000000),
    ("Todoist", "jldhpllghnbhlbpcmnajkpdmadaolakh", "productivity", 1000000),
    ("Momentum", "laookkfknpbbblfpciffpaejjkokdgca", "productivity", 3000000),
    ("Google Translate", "aapbdbdomjkkjkaonfhkkikfgjllcleb", "productivity", 10000000),
    ("ChatGPT for Google", "jgjaeacdkonaoafenlfkkkmbaopkbilf", "ai", 2000000),
    ("Monica AI", "ofpnmcalabcbjgholdjcjblkibolbppb", "ai", 3000000),
    ("Perplexity", "hlnmkgkijafdplientljphkofgnlhdnp", "ai", 1000000),
    ("Sider AI", "difoiogjjojoaoomphldepapgpbgkhkb", "ai", 2000000),
    ("Tampermonkey", "dhdgffkkebhmkfjojejmpbldmpobfkfo", "developer", 10000000),
    ("Stylus", "clngdbkpkpeebahjckkjfobafhncgmne", "developer", 1000000),
    ("ColorZilla", "bhlhnicpbhignbdhedgjhgdocnmhomnp", "developer", 4000000),
    ("Octotree", "bkhaagjahfmjljalopjnoealnfndnagc", "developer", 500000),
]


def crawl(limit=100):
    logger.info(f"Chrome extension crawl (limit={limit})")
    session = get_session(); total = 0

    for name, ext_id, category, est_users in TOP_EXTENSIONS[:limit]:
        slug = name.lower().replace(" ", "-").replace(".", "")
        slug = re.sub(r"[^a-z0-9-]", "", slug).strip("-")

        entry = {"name": name, "slug": slug, "registry": "extension",
                "version": None, "description": f"{name} — Chrome extension ({category})",
                "author": "", "license": "",
                "downloads": est_users, "stars": 0,
                "last_updated": None,
                "repository_url": "", "homepage_url": f"https://chrome.google.com/webstore/detail/{ext_id}",
                "dependencies_count": 0,
                "raw_data": json.dumps({"ext_id": ext_id, "category": category, "est_users": est_users})}
        entry["trust_score"], entry["trust_grade"] = calculate_trust(entry)
        try:
            session.execute(text("""INSERT INTO software_registry
                (name,slug,registry,version,description,author,license,downloads,stars,last_updated,
                 repository_url,homepage_url,dependencies_count,trust_score,trust_grade,raw_data)
                VALUES (:name,:slug,:registry,:version,:description,:author,:license,:downloads,:stars,
                 :last_updated,:repository_url,:homepage_url,:dependencies_count,:trust_score,:trust_grade,CAST(:raw_data AS jsonb))
                ON CONFLICT (registry,slug) DO UPDATE SET downloads=EXCLUDED.downloads,trust_score=EXCLUDED.trust_score,updated_at=NOW()
            """), entry)
            total += 1
        except Exception as e:
            logger.warning(f"{name}: {e}"); session.rollback()
    session.commit(); session.close()
    logger.info(f"Chrome complete: {total}"); return total

if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
