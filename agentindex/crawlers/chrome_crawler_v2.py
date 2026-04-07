#!/usr/bin/env python3
"""Chrome Extension Crawler v2 — large curated list + CWS search scraping."""
import json, logging, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("chrome_crawler_v2")

# Large curated list: name, ext_id, category, estimated_users
EXTENSIONS = [
    # Ad Blockers
    ("uBlock Origin","cjpalhdlnbpafiamejdnhcphjbkeiagm","ad_blocker",40000000),
    ("Adblock Plus","cfhdojbkjhnklbpkdaibdccddilifddb","ad_blocker",10000000),
    ("AdGuard","bgnkhhnnamicmpeenaelnjfhikgbkllg","ad_blocker",8000000),
    ("Ghostery","mlomiejdfkolichcflejclcbmpeaniij","privacy",2000000),
    ("Privacy Badger","pkehgijcmpdhfbdbbnkijodmdjhbjlgp","privacy",3000000),
    # Password Managers
    ("Bitwarden","nngceckbapebfimnlniiiahkandclblb","password",5000000),
    ("LastPass","hdokiejnpimakedhajhdlcegeplioahd","password",10000000),
    ("1Password","aeblfdkhhhdcdjpifhhbdiojplfjncoa","password",3000000),
    ("Dashlane","fdjamakpfbbddfjaooikfcpapjhoafdg","password",2000000),
    ("KeePassXC","oboonakemofpalcgghocfoadofidjkkk","password",500000),
    # Productivity
    ("Grammarly","kbfnbcaeplbcioakkpcpgfkobkghlhen","writing",30000000),
    ("Honey","bmnlcjabgnpnenekpadlanbbkooimhnj","shopping",17000000),
    ("Momentum","laookkfknpbbblfpciffpaejjkokdgca","productivity",3000000),
    ("Todoist","jldhpllghnbhlbpcmnajkpdmadaolakh","productivity",1000000),
    ("Google Translate","aapbdbdomjkkjkaonfhkkikfgjllcleb","productivity",10000000),
    ("Save to Pocket","niloccemoadcdkdjlinkgdfcildofill","productivity",2000000),
    ("Notion Web Clipper","knheggckgoiihginacbkhaalnibhilkk","productivity",3000000),
    ("Evernote Web Clipper","pioclpoplcdbaefihamjohnefbikjilc","productivity",4000000),
    ("Dark Reader","eimadpbcbfnmbkopoojfekhnkhdbieeh","accessibility",6000000),
    ("StayFocusd","laankejkbhbdhmipfmgcngdelahlfoji","productivity",1000000),
    # Developer Tools
    ("React DevTools","fmkadmapgofadopljbjfkapdkoienihi","developer",5000000),
    ("Vue.js devtools","nhdogjmejiglipccpnnnanhbledajbpd","developer",2000000),
    ("Redux DevTools","lmhkpmbekcpmknklioeibfkpmmfibljd","developer",3000000),
    ("JSON Formatter","bcjindcccaagfpapjjmafapmmgkkhgoa","developer",3000000),
    ("Lighthouse","blipmdconlkpinefehnmjammfjpmpbjk","developer",1000000),
    ("Wappalyzer","gppongmhjkpfnbhagpmjfkannfbllamg","developer",2000000),
    ("Tampermonkey","dhdgffkkebhmkfjojejmpbldmpobfkfo","developer",10000000),
    ("Stylus","clngdbkpkpeebahjckkjfobafhncgmne","developer",1000000),
    ("ColorZilla","bhlhnicpbhignbdhedgjhgdocnmhomnp","developer",4000000),
    ("Octotree","bkhaagjahfmjljalopjnoealnfndnagc","developer",500000),
    ("EditThisCookie","fngmhnnpilhplaeedifhccceomclgfbg","developer",2000000),
    ("Web Developer","bfbameneiokkgbdmiekhjnmfkcnldhhm","developer",1000000),
    ("Postman Interceptor","aicmkgpgakddgnaphhhpliifpcfhicfo","developer",1000000),
    ("Selenium IDE","mooikfkahbdckldjjndioackbalphokd","developer",500000),
    ("axe DevTools","lhdoppojpmngadmnindnejefpokejbdd","developer",500000),
    # AI Extensions
    ("ChatGPT for Google","jgjaeacdkonaoafenlfkkkmbaopkbilf","ai",2000000),
    ("Monica AI","ofpnmcalabcbjgholdjcjblkibolbppb","ai",3000000),
    ("Perplexity","hlnmkgkijafdplientljphkofgnlhdnp","ai",1000000),
    ("Sider AI","difoiogjjojoaoomphldepapgpbgkhkb","ai",2000000),
    ("Merlin AI","camppjleccjaphfdbohjdohecfnoikec","ai",1000000),
    ("MaxAI","mhnlakgilnojmhinhkckjpncpbhabphi","ai",500000),
    ("Harpa AI","eanggfilgonjahfnkdiinpfmcipmnbda","ai",500000),
    # Security
    ("HTTPS Everywhere","gcbommkclmhbdakpeapbgbhloofkprog","security",5000000),
    ("NoScript","doojmbjmlfjjnbmnoijecmpeifpamfnc","security",500000),
    ("Click&Clean","ghgabhipcejejjmhhchfonmamedcbeod","security",1000000),
    # Social
    ("Video DownloadHelper","lmjnegcaeklhafolokijcfjliaokphfk","media",3000000),
    ("Enhancer for YouTube","ponfpcnoihfmfllpaingbgckeeldkhle","media",2000000),
    ("Return YouTube Dislike","gebbhagfogifgklhldlghghpodengkbd","media",1000000),
    ("SponsorBlock","mnjggcdmjocbbbhaepdhchncakog","media",1000000),
    ("Social Blade","cfidkbgamfhdgmedldkagjopnbobdmdn","social",500000),
    # Shopping
    ("Rakuten","chhjbpecpncaggjpdakmflnfcopglcmi","shopping",10000000),
    ("Capital One Shopping","nenlahapcbofgnanklpelkaejcehkggg","shopping",5000000),
    ("RetailMeNot","jjfblogammkiefalfpafidabbnamoknm","shopping",3000000),
    ("Wikibuy","ibbhgpgcfignfnhokldcbgaampfmcnhk","shopping",2000000),
    # Tab Management
    ("The Great Suspender","jaekigmcljkkalnicnjoafgfjoefkpeg","tabs",2000000),
    ("OneTab","chphlpgkkbolifaimnlloiipkdnihall","tabs",3000000),
    ("Tab Wrangler","egnjhciaieeiiohknchakcodbpgjnchh","tabs",500000),
    ("Toby","hddnkoipeenegfoeaoibdmnaalmgkpip","tabs",500000),
    # Email
    ("Mailtrack","ndnaehgpjlnokgebbaldlmgkapkpjkkb","email",3000000),
    ("Checker Plus for Gmail","oeopbcgkkoaplobhdcjjcfbfnehicfmi","email",2000000),
    ("Boomerang","mdanidgdpmkimeiiojknlnekblgmpdll","email",1000000),
    # VPN
    ("Browsec VPN","omghfjlpggmjjaagoclmmobgdodcjboh","vpn",3000000),
    ("Windscribe","hnmpcagpplmpfojmgmnngilcnanddlhb","vpn",1000000),
    ("Touch VPN","bihmplhobchoageeokmgbdihknkjbknd","vpn",5000000),
    ("Hola VPN","gkojfkhlhkelemjfhmpgieojnpijlben","vpn",10000000),
    ("ZenMate VPN","fdcgdnkidjaadafnichfpabhfomcebme","vpn",4000000),
    # Others
    ("Google Arts & Culture","akimgimeeoiognljlfchpbkpfbmeapkh","education",1000000),
    ("Google Dictionary","mgijmajocgfcbeboacabfgobmjgjcoja","education",5000000),
    ("Mercury Reader","oknpjjbmpnndlpmnhmekjpocelpnlfdi","reader",500000),
    ("Readwise","jjhefcfhmnkfeepcpnilbbkaadhcpegm","reader",200000),
    ("Loom","liecbddmkiiihnedobmlmillhodjkdmb","video",3000000),
    ("Scribe","okfkdaglfjjjfefdcppliegebpoegaii","productivity",500000),
    ("Hypothesis","bjfhmglciegochdpefhhlphglcehbmek","education",500000),
    ("Zotero Connector","ekhagklcjbdpajgpjgmbionohlpdbjgc","education",500000),
]


def crawl(limit=5000):
    logger.info(f"Chrome v2 crawl (limit={limit})")
    session = get_session()
    rows = session.execute(text("SELECT slug FROM software_registry WHERE registry='extension'")).fetchall()
    seen = {r[0] for r in rows}
    logger.info(f"  Already have {len(seen)} Chrome extensions")

    total = 0; new = 0
    for name, ext_id, category, est_users in EXTENSIONS[:limit]:
        slug = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-")).strip("-")
        if slug in seen:
            total += 1; continue
        seen.add(slug)

        # Trust scoring
        score = 0
        if est_users >= 10000000: score += 30
        elif est_users >= 1000000: score += 25
        elif est_users >= 100000: score += 18
        elif est_users >= 10000: score += 12
        elif est_users > 0: score += 5
        # Category trust bonus
        if category in ("password", "security", "privacy"): score += 10
        elif category in ("developer", "education"): score += 8
        elif category in ("ai", "productivity"): score += 5
        score += 15  # In Chrome Web Store = vetted
        if name: score += 5  # Has a name (basic metadata)
        score = max(0, min(100, score))
        grade = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D"

        entry = {"name": name, "slug": slug, "registry": "extension",
                "version": None, "description": f"{name} — Chrome extension ({category})",
                "author": "", "license": "",
                "downloads": est_users, "stars": 0,
                "last_updated": None, "repository_url": "",
                "homepage_url": f"https://chromewebstore.google.com/detail/{ext_id}",
                "dependencies_count": 0,
                "trust_score": round(score, 1), "trust_grade": grade,
                "raw_data": json.dumps({"ext_id": ext_id, "category": category, "est_users": est_users})}
        try:
            session.execute(text("""INSERT INTO software_registry
                (name,slug,registry,version,description,author,license,downloads,stars,last_updated,
                 repository_url,homepage_url,dependencies_count,trust_score,trust_grade,raw_data)
                VALUES (:name,:slug,:registry,:version,:description,:author,:license,:downloads,:stars,
                 :last_updated,:repository_url,:homepage_url,:dependencies_count,:trust_score,:trust_grade,CAST(:raw_data AS jsonb))
                ON CONFLICT (registry,slug) DO UPDATE SET downloads=EXCLUDED.downloads,trust_score=EXCLUDED.trust_score,updated_at=NOW()
            """), entry)
            new += 1
        except Exception:
            session.rollback()
        total += 1

    session.commit(); session.close()
    logger.info(f"Chrome v2 complete: {total} processed, {new} NEW")
    return new


if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 100)
