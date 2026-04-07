#!/usr/bin/env python3
"""Android App Crawler via google-play-scraper. Permission-weighted trust scoring."""
import json, logging, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("android_crawler")

CATEGORIES = [
    "social media","messaging","video call","photo editor","music player",
    "banking app","crypto wallet","stock trading","payment app","money transfer",
    "fitness tracker","health app","meditation","diet","yoga","running",
    "language learning","education","online course","math","science",
    "shopping","food delivery","grocery","travel","maps","navigation","hotel",
    "news","weather","email client","calendar","clock","alarm",
    "vpn","password manager","security","antivirus","cleaner",
    "ai assistant","chatbot","writing assistant","translator",
    "productivity","notes","todo list","office suite","pdf reader","scanner",
    "streaming video","podcast player","audiobook","music streaming","radio",
    "browser","keyboard","launcher","wallpaper","widget",
    "dating","kids app","parental control","baby","pregnancy",
    "games","puzzle game","action game","strategy","racing","sports game",
    "casino","card game","word game","trivia","board game",
    "file manager","cloud storage","backup","wifi","bluetooth",
    "camera","video editor","voice recorder","screen recorder",
    "calculator","converter","compass","flashlight","qr code",
    "bible","quran","prayer","meditation timer",
    "recipe","cooking","restaurant","food tracker","water tracker",
    "car","driving","parking","gas station","electric vehicle",
    "job search","resume","interview","freelance","remote work",
    "real estate","mortgage","rent","home","interior design",
    "pet","dog","cat","plant","garden",
    "sleep","relaxation","white noise","asmr",
    "period tracker","blood pressure","diabetes","pill reminder",
    "taxi","rideshare","bus","train","flight tracker",
]

TOP_APPS = [
    "com.zhiliaoapp.musically","com.whatsapp","com.instagram.android","com.snapchat.android",
    "org.telegram.messenger","com.discord","us.zoom.videomeetings","com.microsoft.teams",
    "com.slack","com.amazon.mShop.android.shopping","com.ubercab","com.netflix.mediaclient",
    "com.spotify.music","com.google.android.youtube","tv.twitch.android.app",
    "com.openai.chatgpt","co.huggingface.chat",
    "com.nordvpn.android","com.expressvpn.vpn",
    "com.tinder","com.bumble.app","com.roblox.client","com.mojang.minecraftpe",
    "com.duolingo","org.khanacademy.android","com.notion.id","com.todoist",
    "com.canva.editor","com.google.android.apps.maps","com.paypal.android.p2pmobile",
    "com.coinbase.android","com.robinhood.android",
    # Additional top apps
    "com.facebook.katana","com.facebook.orca","com.twitter.android","com.reddit.frontpage",
    "com.pinterest","com.linkedin.android","com.tumblr","com.google.android.gm",
    "com.microsoft.office.outlook","com.yahoo.mobile.client.android.mail",
    "com.google.android.apps.docs","com.microsoft.office.word","com.microsoft.office.excel",
    "com.google.android.keep","com.evernote","com.samsung.android.app.notes",
    "com.adobe.reader","com.microsoft.office.onenote",
    "com.google.android.apps.photos","com.adobe.lrmobile","com.picsart.studio",
    "com.google.android.googlequicksearchbox","com.brave.browser",
    "org.mozilla.firefox","com.opera.browser","com.duckduckgo.mobile.android",
    "com.grammarly.android.keyboard","com.swiftkey.swiftkey",
    "com.waze","com.ubercab.eats","com.grubhub.android",
    "com.walmart.android","com.target.ui","com.ebay.mobile",
    "com.shopify.mobile","com.etsy.android","com.wish.android",
    "com.venmo","com.squareup.cash","com.google.android.apps.walletnfcrel",
    "com.binance.dev","com.kraken.trade","com.bitfinex.bfx",
    "com.hbo.hbonow","com.disney.disneyplus","com.amazon.avod.thirdpartyclient",
    "com.pandora.android","com.soundcloud.android","com.shazam.android",
    "com.strava","com.myfitnesspal.android","com.nike.plusgps",
    "com.headspace.android","com.calm.android",
    "com.king.candycrushsaga","com.supercell.clashofclans","com.dts.freefireth",
    "com.activision.callofduty.shooter","com.pubg.imobile",
    "com.nianticlabs.pokemongo","com.innersloth.spacemafia",
    "org.thoughtcrime.securesms","com.viber.voip",
    "com.google.android.apps.translate","com.deepl.mobiletranslator",
    "com.microsoft.bing","com.google.android.apps.tachyon",
]

HIGH_RISK_PERMS = ["CAMERA","RECORD_AUDIO","READ_CONTACTS","ACCESS_FINE_LOCATION",
                   "READ_PHONE_STATE","READ_SMS","READ_CALL_LOG","READ_EXTERNAL_STORAGE"]


def crawl(limit=5000):
    logger.info(f"Android crawl (limit={limit})")
    try:
        import google_play_scraper as gps
    except ImportError:
        logger.error("google-play-scraper not installed"); return 0

    session = get_session()
    rows = session.execute(text("SELECT slug FROM software_registry WHERE registry='android'")).fetchall()
    seen = {r[0] for r in rows}
    logger.info(f"  Already have {len(seen)} Android apps")

    total = 0; new = 0

    # Phase 1: Direct lookup of top apps
    for pkg_id in TOP_APPS:
        if total >= limit: break
        slug = pkg_id.lower().replace(".", "-")
        if slug in seen: total += 1; continue
        try:
            app = gps.app(pkg_id, lang='en', country='us')
            _store_app(session, app, seen)
            new += 1; total += 1
        except Exception as e:
            logger.debug(f"  {pkg_id}: {e}")
            total += 1
        time.sleep(1)

    # Phase 2: Search by categories
    for cat in CATEGORIES:
        if total >= limit: break
        try:
            results = gps.search(cat, n_hits=50, lang='en', country='us')
            for app in results:
                if total >= limit: break
                slug = (app.get("appId") or "").lower().replace(".", "-")
                if slug in seen: total += 1; continue
                try:
                    detail = gps.app(app["appId"], lang='en', country='us')
                    _store_app(session, detail, seen)
                    new += 1
                except Exception:
                    pass
                total += 1
                time.sleep(1)
        except Exception as e:
            logger.warning(f"Search '{cat}': {e}")

        if total % 100 == 0:
            session.commit()
            logger.info(f"  {total} processed, {new} new")

    session.commit(); session.close()
    logger.info(f"Android complete: {total} processed, {new} NEW")
    return new


def _store_app(session, app, seen):
    name = app.get("title", "")
    pkg_id = app.get("appId", "")
    slug = pkg_id.lower().replace(".", "-")
    if slug in seen: return
    seen.add(slug)

    score_val = app.get("score") or 0
    ratings = app.get("ratings") or 0
    installs = app.get("realInstalls") or app.get("installs") or 0

    # Convert Unix timestamp to ISO date string
    updated = app.get("updated")
    if isinstance(updated, (int, float)):
        from datetime import datetime
        try:
            updated = datetime.utcfromtimestamp(updated).isoformat()
        except (ValueError, OSError):
            updated = None
    elif updated:
        updated = str(updated)[:50]
    else:
        updated = None

    # Permission-weighted trust
    perms = app.get("permissions") or []
    high_risk_count = sum(1 for p in perms if any(h in str(p).upper() for h in HIGH_RISK_PERMS))

    trust = 0
    if score_val >= 4.5 and ratings >= 10000: trust += 30
    elif score_val >= 4.0 and ratings >= 1000: trust += 25
    elif score_val >= 3.5: trust += 15
    elif score_val > 0: trust += 8
    if installs >= 10000000: trust += 20
    elif installs >= 1000000: trust += 15
    elif installs >= 100000: trust += 10
    elif installs >= 10000: trust += 5
    trust -= high_risk_count * 3  # Permission penalty
    if app.get("privacyPolicy"): trust += 5
    if app.get("updated"): trust += 5
    if app.get("developer"): trust += 5
    trust += 5  # In Play Store = some trust
    trust = max(0, min(100, trust))
    grade = "A" if trust >= 80 else "B" if trust >= 60 else "C" if trust >= 40 else "D"

    entry = {"name": name, "slug": slug, "registry": "android",
            "version": app.get("version"), "description": (app.get("summary") or "")[:500],
            "author": app.get("developer") or "", "license": app.get("contentRating") or "",
            "downloads": installs, "stars": int(score_val * 20),
            "last_updated": updated,
            "repository_url": "", "homepage_url": app.get("url") or "",
            "dependencies_count": len(perms),
            "trust_score": round(trust, 1), "trust_grade": grade,
            "raw_data": json.dumps({"appId": pkg_id, "score": score_val, "ratings": ratings,
                                   "containsAds": app.get("containsAds"), "offersIAP": app.get("offersIAP"),
                                   "highRiskPerms": high_risk_count, "genre": app.get("genre")})}
    try:
        session.execute(text("""INSERT INTO software_registry
            (name,slug,registry,version,description,author,license,downloads,stars,last_updated,
             repository_url,homepage_url,dependencies_count,trust_score,trust_grade,raw_data)
            VALUES (:name,:slug,:registry,:version,:description,:author,:license,:downloads,:stars,
             :last_updated,:repository_url,:homepage_url,:dependencies_count,:trust_score,:trust_grade,CAST(:raw_data AS jsonb))
            ON CONFLICT (registry,slug) DO NOTHING
        """), entry)
    except Exception:
        session.rollback()


if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 5000)
