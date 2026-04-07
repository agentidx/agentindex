#!/usr/bin/env python3
"""VPN Database Loader — loads curated VPN data from JSON, calculates trust scores."""
import json, logging, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("vpn_loader")

VPN_DATA = [
    {"name":"NordVPN","slug":"nordvpn","jurisdiction":"Panama","five_eyes":False,"audited":True,"open_source":True,"no_log":"audited","servers":5800,"countries":60,"breaches":1,"protocols":["WireGuard","OpenVPN"],"price":12.99,"free":False,"warrant_canary":True,"kill_switch":True},
    {"name":"ExpressVPN","slug":"expressvpn","jurisdiction":"BVI","five_eyes":False,"audited":True,"open_source":True,"no_log":"audited","servers":3000,"countries":94,"breaches":0,"protocols":["Lightway","OpenVPN"],"price":12.95,"free":False,"warrant_canary":False,"kill_switch":True},
    {"name":"Surfshark","slug":"surfshark","jurisdiction":"Netherlands","five_eyes":False,"audited":True,"open_source":False,"no_log":"audited","servers":3200,"countries":100,"breaches":0,"protocols":["WireGuard","OpenVPN"],"price":12.95,"free":False,"warrant_canary":True,"kill_switch":True},
    {"name":"ProtonVPN","slug":"protonvpn","jurisdiction":"Switzerland","five_eyes":False,"audited":True,"open_source":True,"no_log":"audited","servers":3000,"countries":71,"breaches":0,"protocols":["WireGuard","OpenVPN","Stealth"],"price":9.99,"free":True,"warrant_canary":True,"kill_switch":True},
    {"name":"Mullvad","slug":"mullvad","jurisdiction":"Sweden","five_eyes":False,"audited":True,"open_source":True,"no_log":"audited","servers":700,"countries":40,"breaches":0,"protocols":["WireGuard","OpenVPN"],"price":5.00,"free":False,"warrant_canary":False,"kill_switch":True},
    {"name":"CyberGhost","slug":"cyberghost","jurisdiction":"Romania","five_eyes":False,"audited":True,"open_source":False,"no_log":"audited","servers":9700,"countries":91,"breaches":0,"protocols":["WireGuard","OpenVPN"],"price":12.99,"free":False,"warrant_canary":False,"kill_switch":True},
    {"name":"PIA","slug":"pia","jurisdiction":"US","five_eyes":True,"audited":True,"open_source":True,"no_log":"audited","servers":35000,"countries":84,"breaches":0,"protocols":["WireGuard","OpenVPN"],"price":11.95,"free":False,"warrant_canary":False,"kill_switch":True},
    {"name":"IPVanish","slug":"ipvanish","jurisdiction":"US","five_eyes":True,"audited":False,"open_source":False,"no_log":"claimed","servers":2200,"countries":75,"breaches":1,"protocols":["WireGuard","OpenVPN"],"price":12.99,"free":False,"warrant_canary":False,"kill_switch":True},
    {"name":"TunnelBear","slug":"tunnelbear","jurisdiction":"Canada","five_eyes":True,"audited":True,"open_source":False,"no_log":"audited","servers":5000,"countries":47,"breaches":0,"protocols":["OpenVPN","IKEv2"],"price":9.99,"free":True,"warrant_canary":False,"kill_switch":True},
    {"name":"Windscribe","slug":"windscribe","jurisdiction":"Canada","five_eyes":True,"audited":False,"open_source":True,"no_log":"claimed","servers":600,"countries":63,"breaches":0,"protocols":["WireGuard","OpenVPN"],"price":9.00,"free":True,"warrant_canary":True,"kill_switch":True},
    {"name":"Atlas VPN","slug":"atlas-vpn","jurisdiction":"US","five_eyes":True,"audited":False,"open_source":False,"no_log":"claimed","servers":1000,"countries":44,"breaches":0,"protocols":["WireGuard"],"price":10.99,"free":True,"warrant_canary":False,"kill_switch":True},
    {"name":"StrongVPN","slug":"strongvpn","jurisdiction":"US","five_eyes":True,"audited":False,"open_source":False,"no_log":"claimed","servers":950,"countries":30,"breaches":0,"protocols":["WireGuard","OpenVPN"],"price":10.99,"free":False,"warrant_canary":False,"kill_switch":True},
    {"name":"VyprVPN","slug":"vyprvpn","jurisdiction":"Switzerland","five_eyes":False,"audited":True,"open_source":False,"no_log":"audited","servers":700,"countries":70,"breaches":0,"protocols":["WireGuard","OpenVPN","Chameleon"],"price":12.95,"free":False,"warrant_canary":False,"kill_switch":True},
    {"name":"Hotspot Shield","slug":"hotspot-shield","jurisdiction":"US","five_eyes":True,"audited":False,"open_source":False,"no_log":"claimed","servers":1800,"countries":80,"breaches":0,"protocols":["Catapult Hydra"],"price":12.99,"free":True,"warrant_canary":False,"kill_switch":True},
    {"name":"IVPN","slug":"ivpn","jurisdiction":"Gibraltar","five_eyes":False,"audited":True,"open_source":True,"no_log":"audited","servers":80,"countries":32,"breaches":0,"protocols":["WireGuard","OpenVPN"],"price":6.00,"free":False,"warrant_canary":True,"kill_switch":True},
    {"name":"AirVPN","slug":"airvpn","jurisdiction":"Italy","five_eyes":False,"audited":False,"open_source":True,"no_log":"claimed","servers":300,"countries":24,"breaches":0,"protocols":["WireGuard","OpenVPN"],"price":7.00,"free":False,"warrant_canary":True,"kill_switch":True},
    {"name":"hide.me","slug":"hide-me","jurisdiction":"Malaysia","five_eyes":False,"audited":True,"open_source":False,"no_log":"audited","servers":2100,"countries":79,"breaches":0,"protocols":["WireGuard","OpenVPN"],"price":9.95,"free":True,"warrant_canary":False,"kill_switch":True},
    {"name":"Mozilla VPN","slug":"mozilla-vpn","jurisdiction":"US","five_eyes":True,"audited":True,"open_source":True,"no_log":"audited","servers":500,"countries":30,"breaches":0,"protocols":["WireGuard"],"price":9.99,"free":False,"warrant_canary":False,"kill_switch":True},
    {"name":"Astrill","slug":"astrill","jurisdiction":"Seychelles","five_eyes":False,"audited":False,"open_source":False,"no_log":"claimed","servers":300,"countries":56,"breaches":0,"protocols":["OpenVPN","WireGuard","StealthVPN"],"price":20.00,"free":False,"warrant_canary":False,"kill_switch":True},
    {"name":"PureVPN","slug":"purevpn","jurisdiction":"BVI","five_eyes":False,"audited":True,"open_source":False,"no_log":"audited","servers":6500,"countries":71,"breaches":1,"protocols":["WireGuard","OpenVPN"],"price":10.95,"free":False,"warrant_canary":False,"kill_switch":True},
]


def _vpn_trust_score(v):
    score = 0
    # Jurisdiction
    if not v.get("five_eyes"): score += 15
    # Audit
    if v.get("audited") and v.get("no_log") == "audited": score += 25
    elif v.get("no_log") == "claimed": score += 10
    # Open source
    if v.get("open_source"): score += 15
    # Track record
    breaches = v.get("breaches", 0)
    if breaches == 0: score += 10
    else: score += max(0, 10 - breaches * 5)
    # Protocols
    protos = v.get("protocols", [])
    if any("wireguard" in p.lower() for p in protos): score += 10
    elif any("openvpn" in p.lower() for p in protos): score += 5
    # Features
    if v.get("warrant_canary"): score += 5
    if v.get("kill_switch"): score += 5
    # Server coverage
    if v.get("countries", 0) >= 50: score += 5
    elif v.get("countries", 0) >= 20: score += 3
    # Base
    score += 5
    return max(0, min(100, score))


def load():
    logger.info(f"Loading {len(VPN_DATA)} VPNs")
    session = get_session(); total = 0
    for v in VPN_DATA:
        score = _vpn_trust_score(v)
        grade = "A+" if score >= 90 else "A" if score >= 80 else "B" if score >= 70 else "C" if score >= 60 else "D"
        entry = {"name": v["name"], "slug": v["slug"], "registry": "vpn",
                "version": None,
                "description": f"{v['name']} VPN — {v['jurisdiction']} jurisdiction. {v.get('servers',0)} servers in {v.get('countries',0)} countries. {'Audited no-log.' if v.get('audited') else 'Claimed no-log.'}",
                "author": v["name"], "license": "",
                "downloads": v.get("servers", 0) * 1000,  # Proxy
                "stars": 0, "last_updated": None,
                "repository_url": "", "homepage_url": f"https://{v.get('slug','')}.com",
                "dependencies_count": 0, "trust_score": round(score, 1), "trust_grade": grade,
                "raw_data": json.dumps(v)}
        try:
            session.execute(text("""INSERT INTO software_registry
                (name,slug,registry,version,description,author,license,downloads,stars,last_updated,
                 repository_url,homepage_url,dependencies_count,trust_score,trust_grade,raw_data)
                VALUES (:name,:slug,:registry,:version,:description,:author,:license,:downloads,:stars,
                 :last_updated,:repository_url,:homepage_url,:dependencies_count,:trust_score,:trust_grade,CAST(:raw_data AS jsonb))
                ON CONFLICT (registry,slug) DO UPDATE SET trust_score=EXCLUDED.trust_score,trust_grade=EXCLUDED.trust_grade,updated_at=NOW()
            """), entry)
            total += 1
        except Exception as e:
            logger.warning(f"{v['name']}: {e}"); session.rollback()
    session.commit(); session.close()
    logger.info(f"VPN load complete: {total}"); return total

if __name__ == "__main__":
    load()
