"""
Sprint 7: Wallet Behavior Analysis
Analyserar on-chain beteende för att klassificera AI-agenter vs mänskliga wallets.
Använder Etherscan API för transaktionshistorik.
"""
import sqlite3, json, os, time, logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import requests
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)).replace("/agentindex-factory/", "/agentindex/"),
    "crypto_trust.db",
)
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
ETHERSCAN_BASE = "https://api.etherscan.io/v2/api"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ─── Heuristik-vikter ────────────────────────────────────────────────────────
# Varje signal bidrar till P(AI-agent) confidence score 0.0-1.0

AGENT_SIGNALS = {
    # Beteendesignaler som tyder på AI-agent
    "high_tx_frequency":     0.20,  # >10 tx/dag i snitt
    "night_activity":        0.15,  # aktiv 00-06 UTC (människor sover)
    "weekend_activity":      0.10,  # aktiv lördagar/söndagar lika mycket som vardagar
    "regular_intervals":     0.20,  # tx med regelbundna tidsintervall (cron-mönster)
    "zero_failed_tx":        0.10,  # inga misslyckade transaktioner (bot retry-logik)
    "defi_only":             0.15,  # enbart DeFi-interaktioner, inga NFT/vanliga transfers
    "multi_protocol":        0.10,  # interagerar med 3+ protokoll (diversifierad strategi)
}

# Agenttyp-klassificering baserat på protokoll-interaktioner
AGENT_TYPE_PATTERNS = {
    "yield-agent":    ["compound", "aave", "yearn", "convex", "curve", "lido", "rocketpool"],
    "trading-agent":  ["uniswap", "sushiswap", "1inch", "paraswap", "0x", "cowswap"],
    "arb-agent":      ["flashloan", "balancer", "dydx", "aave", "compound"],  # multi-protokoll snabb
    "bridge-agent":   ["across", "stargate", "hop", "synapse", "multichain"],
    "governance-agent": ["snapshot", "tally", "compound-governor", "aave-governance"],
}

# ─── DB Setup ────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS wallet_behavior (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_address TEXT NOT NULL UNIQUE,
            chain TEXT NOT NULL DEFAULT 'ethereum',
            
            -- Beteendemätningar
            tx_count_30d INTEGER DEFAULT 0,
            tx_count_90d INTEGER DEFAULT 0,
            avg_tx_per_day REAL DEFAULT 0,
            night_tx_ratio REAL DEFAULT 0,     -- andel tx 00-06 UTC
            weekend_tx_ratio REAL DEFAULT 0,   -- andel tx lör-sön
            interval_regularity REAL DEFAULT 0, -- 0=kaotisk, 1=perfekt cron
            failed_tx_ratio REAL DEFAULT 0,
            unique_protocols INTEGER DEFAULT 0,
            defi_tx_ratio REAL DEFAULT 0,
            
            -- Klassificering
            agent_type TEXT,                   -- yield-agent, trading-agent, arb-agent, etc
            confidence REAL DEFAULT 0.0,       -- P(AI-agent) 0.0-1.0
            confidence_signals TEXT,           -- JSON: vilka signaler triggades
            is_ai_agent INTEGER DEFAULT 0,     -- 1 om confidence >= 0.65
            
            -- Metadata
            first_tx_date TEXT,
            last_tx_date TEXT,
            analyzed_at TEXT,
            raw_stats_json TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_wb_address ON wallet_behavior(wallet_address);
        CREATE INDEX IF NOT EXISTS idx_wb_confidence ON wallet_behavior(confidence DESC);
        CREATE INDEX IF NOT EXISTS idx_wb_type ON wallet_behavior(agent_type);
        CREATE INDEX IF NOT EXISTS idx_wb_chain ON wallet_behavior(chain);

        CREATE TABLE IF NOT EXISTS agent_activity_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,   -- 'token', 'protocol', 'chain'
            entity_id TEXT NOT NULL,     -- token address / protocol name / chain name
            entity_name TEXT,
            entity_symbol TEXT,
            
            -- Index-värden
            total_agents INTEGER DEFAULT 0,
            identified_ai_agents INTEGER DEFAULT 0,
            ai_agent_ratio REAL DEFAULT 0,      -- andel AI-agenter av alla wallets
            
            -- TVL-kontroll (om tillgänglig)
            ai_controlled_tvl_usd REAL,
            total_tvl_usd REAL,
            ai_tvl_ratio REAL,                  -- "X% av TVL kontrolleras av AI-agenter"
            
            -- Aktivitet
            avg_agent_confidence REAL DEFAULT 0,
            top_agent_types TEXT,               -- JSON: {type: count}
            agent_ids_json TEXT,                -- JSON: lista av agent_id
            
            computed_at TEXT,
            UNIQUE(entity_type, entity_id)
        );

        CREATE INDEX IF NOT EXISTS idx_aai_entity ON agent_activity_index(entity_type, entity_id);
        CREATE INDEX IF NOT EXISTS idx_aai_ratio ON agent_activity_index(ai_agent_ratio DESC);
    """)
    conn.commit()
    conn.close()
    log.info("DB-tabeller initierade")

# ─── Etherscan API ────────────────────────────────────────────────────────────

def etherscan_get(params: dict, retries: int = 3) -> Optional[dict]:
    """Gör ett Etherscan API-anrop med retry-logik."""
    params["apikey"] = ETHERSCAN_API_KEY
    params.setdefault("chainid", 1)
    for attempt in range(retries):
        try:
            r = requests.get(ETHERSCAN_BASE, params=params, timeout=15)
            data = r.json()
            if data.get("status") == "1":
                return data
            # Rate limit
            if "Max rate limit" in str(data.get("result", "")):
                time.sleep(2 ** attempt)
                continue
            return data
        except Exception as e:
            log.warning(f"Etherscan fel (försök {attempt+1}): {e}")
            time.sleep(1)
    return None

def fetch_tx_history(address: str, days: int = 90) -> list:
    """Hämta transaktionshistorik för en wallet de senaste N dagarna."""
    start_block = 0  # Vi filtrerar på datum istället
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_ts = int(cutoff.timestamp())

    all_txs = []

    # Normala transaktioner
    data = etherscan_get({
        "module": "account",
        "action": "txlist",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "desc",
        "offset": 200,
        "page": 1
    })
    if data and isinstance(data.get("result"), list):
        txs = [t for t in data["result"] if int(t.get("timeStamp", 0)) >= cutoff_ts]
        all_txs.extend(txs)

    # Internal transactions (DeFi-interaktioner)
    data_internal = etherscan_get({
        "module": "account",
        "action": "txlistinternal",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "desc",
        "offset": 200,
        "page": 1
    })
    if data_internal and isinstance(data_internal.get("result"), list):
        internal = [t for t in data_internal["result"] if int(t.get("timeStamp", 0)) >= cutoff_ts]
        all_txs.extend(internal)

    return all_txs

# ─── Heuristik-analys ────────────────────────────────────────────────────────

def analyze_tx_behavior(txs: list) -> dict:
    """Analysera transaktionsmönster och räkna ut beteendesignaler."""
    if not txs:
        return {}

    timestamps = sorted([int(t.get("timeStamp", 0)) for t in txs if t.get("timeStamp")])
    if not timestamps:
        return {}

    dts = [datetime.fromtimestamp(ts, tz=timezone.utc) for ts in timestamps]
    total = len(dts)

    # Tidsspan
    first_dt = dts[0]
    last_dt = dts[-1]
    span_days = max(1, (last_dt - first_dt).days)

    # Frekvens
    avg_per_day = total / span_days

    # Natt-aktivitet (00-06 UTC)
    night_txs = sum(1 for dt in dts if 0 <= dt.hour < 6)
    night_ratio = night_txs / total

    # Helg-aktivitet
    weekend_txs = sum(1 for dt in dts if dt.weekday() >= 5)
    weekend_ratio = weekend_txs / total

    # Intervall-regularitet (låg std = regelbundet = trolig bot)
    if len(timestamps) >= 5:
        intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
        mean_interval = sum(intervals) / len(intervals)
        if mean_interval > 0:
            variance = sum((x - mean_interval)**2 for x in intervals) / len(intervals)
            std = variance ** 0.5
            cv = std / mean_interval  # Coefficient of variation
            regularity = max(0.0, 1.0 - min(cv, 1.0))
        else:
            regularity = 0.0
    else:
        regularity = 0.0

    # Misslyckade transaktioner
    failed = sum(1 for t in txs if t.get("isError") == "1")
    failed_ratio = failed / total if total > 0 else 0

    # Unika protokoll (to-adresser)
    to_addresses = set(t.get("to", "").lower() for t in txs if t.get("to"))
    unique_protocols = len(to_addresses)

    # DeFi-ratio (approximation: internal txs = DeFi-interaktioner)
    internal_count = sum(1 for t in txs if "contractAddress" not in t and t.get("to"))
    defi_ratio = min(1.0, internal_count / max(1, total))

    return {
        "tx_count": total,
        "avg_tx_per_day": round(avg_per_day, 2),
        "night_tx_ratio": round(night_ratio, 3),
        "weekend_tx_ratio": round(weekend_ratio, 3),
        "interval_regularity": round(regularity, 3),
        "failed_tx_ratio": round(failed_ratio, 3),
        "unique_protocols": unique_protocols,
        "defi_tx_ratio": round(defi_ratio, 3),
        "first_tx_date": first_dt.isoformat(),
        "last_tx_date": last_dt.isoformat(),
        "span_days": span_days,
    }

def compute_confidence(stats: dict) -> tuple[float, dict]:
    """
    Beräkna P(AI-agent) baserat på heuristiker.
    Returnerar (confidence, signals_dict).
    """
    signals = {}
    score = 0.0

    if stats.get("avg_tx_per_day", 0) >= 5:
        signals["high_tx_frequency"] = True
        score += AGENT_SIGNALS["high_tx_frequency"]

    if stats.get("night_tx_ratio", 0) >= 0.20:
        signals["night_activity"] = True
        score += AGENT_SIGNALS["night_activity"]

    # Helg-aktivitet: bots jobbar lika mycket helg som vardag
    # Förväntat helg-ratio för människa: ~2/7 = 0.286
    # En bot som kör 24/7 har ~0.286. Vi letar efter avvikelse UPPÅT.
    if stats.get("weekend_tx_ratio", 0) >= 0.30:
        signals["weekend_activity"] = True
        score += AGENT_SIGNALS["weekend_activity"]

    if stats.get("interval_regularity", 0) >= 0.60:
        signals["regular_intervals"] = True
        score += AGENT_SIGNALS["regular_intervals"]

    if stats.get("failed_tx_ratio", 1) < 0.01:
        signals["zero_failed_tx"] = True
        score += AGENT_SIGNALS["zero_failed_tx"]

    if stats.get("defi_tx_ratio", 0) >= 0.80:
        signals["defi_only"] = True
        score += AGENT_SIGNALS["defi_only"]

    if stats.get("unique_protocols", 0) >= 3:
        signals["multi_protocol"] = True
        score += AGENT_SIGNALS["multi_protocol"]

    return round(min(score, 1.0), 3), signals

def classify_agent_type(txs: list, stats: dict) -> Optional[str]:
    """Klassificera agenttyp baserat på protokoll-interaktioner."""
    if not txs:
        return None

    # Hämta alla adresser som wallets interagerat med
    to_addresses = " ".join([
        t.get("to", "").lower() + " " + t.get("input", "").lower()[:20]
        for t in txs
    ])

    # Räkna mönster
    type_scores = {}
    for agent_type, keywords in AGENT_TYPE_PATTERNS.items():
        hits = sum(1 for kw in keywords if kw in to_addresses)
        if hits > 0:
            type_scores[agent_type] = hits

    if not type_scores:
        # Fallback baserat på frekvens
        if stats.get("avg_tx_per_day", 0) >= 20:
            return "arb-agent"
        elif stats.get("defi_tx_ratio", 0) >= 0.8:
            return "yield-agent"
        return "unknown-agent"

    return max(type_scores, key=type_scores.get)

# ─── Huvud-analysflöde ────────────────────────────────────────────────────────

def analyze_wallet(address: str, chain: str = "ethereum") -> Optional[dict]:
    """
    Komplett analys av en wallet-adress.
    Returnerar behavior-dict eller None om otillräcklig data.
    """
    if not address or len(address) < 10:
        return None

    log.info(f"Analyserar wallet: {address[:10]}...")

    txs = fetch_tx_history(address, days=90)
    if len(txs) < 3:
        log.debug(f"  För få transaktioner ({len(txs)}), hoppar över")
        return None

    stats = analyze_tx_behavior(txs)
    if not stats:
        return None

    confidence, signals = compute_confidence(stats)
    agent_type = classify_agent_type(txs, stats) if confidence >= 0.30 else None

    result = {
        "wallet_address": address.lower(),
        "chain": chain,
        "tx_count_90d": stats.get("tx_count", 0),
        "avg_tx_per_day": stats.get("avg_tx_per_day", 0),
        "night_tx_ratio": stats.get("night_tx_ratio", 0),
        "weekend_tx_ratio": stats.get("weekend_tx_ratio", 0),
        "interval_regularity": stats.get("interval_regularity", 0),
        "failed_tx_ratio": stats.get("failed_tx_ratio", 0),
        "unique_protocols": stats.get("unique_protocols", 0),
        "defi_tx_ratio": stats.get("defi_tx_ratio", 0),
        "agent_type": agent_type,
        "confidence": confidence,
        "confidence_signals": json.dumps(signals),
        "is_ai_agent": 1 if confidence >= 0.35 else 0,
        "first_tx_date": stats.get("first_tx_date"),
        "last_tx_date": stats.get("last_tx_date"),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "raw_stats_json": json.dumps(stats),
    }

    return result

def save_wallet_behavior(data: dict):
    """Spara eller uppdatera wallet behavior i DB."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO wallet_behavior
        (wallet_address, chain, tx_count_90d, avg_tx_per_day,
         night_tx_ratio, weekend_tx_ratio, interval_regularity,
         failed_tx_ratio, unique_protocols, defi_tx_ratio,
         agent_type, confidence, confidence_signals, is_ai_agent,
         first_tx_date, last_tx_date, analyzed_at, raw_stats_json)
        VALUES (:wallet_address, :chain, :tx_count_90d, :avg_tx_per_day,
                :night_tx_ratio, :weekend_tx_ratio, :interval_regularity,
                :failed_tx_ratio, :unique_protocols, :defi_tx_ratio,
                :agent_type, :confidence, :confidence_signals, :is_ai_agent,
                :first_tx_date, :last_tx_date, :analyzed_at, :raw_stats_json)
        ON CONFLICT(wallet_address) DO UPDATE SET
            tx_count_90d=excluded.tx_count_90d,
            avg_tx_per_day=excluded.avg_tx_per_day,
            night_tx_ratio=excluded.night_tx_ratio,
            weekend_tx_ratio=excluded.weekend_tx_ratio,
            interval_regularity=excluded.interval_regularity,
            failed_tx_ratio=excluded.failed_tx_ratio,
            unique_protocols=excluded.unique_protocols,
            defi_tx_ratio=excluded.defi_tx_ratio,
            agent_type=excluded.agent_type,
            confidence=excluded.confidence,
            confidence_signals=excluded.confidence_signals,
            is_ai_agent=excluded.is_ai_agent,
            last_tx_date=excluded.last_tx_date,
            analyzed_at=excluded.analyzed_at,
            raw_stats_json=excluded.raw_stats_json
    """, data)
    conn.commit()
    conn.close()

def run_batch_analysis(limit: int = 500):
    """
    Analysera creator_address-wallets från agent_crypto_profile
    som inte analyserats ännu (eller är äldre än 7 dagar).
    """
    init_db()

    conn = sqlite3.connect(DB_PATH)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    # Hämta unika wallet-adresser från agent_crypto_profile
    rows = conn.execute("""
        SELECT DISTINCT a.creator_address, a.chain
        FROM agent_crypto_profile a
        LEFT JOIN wallet_behavior wb ON LOWER(a.creator_address) = wb.wallet_address
        WHERE a.creator_address IS NOT NULL
          AND a.creator_address != ''
          AND length(a.creator_address) >= 10
          AND (wb.wallet_address IS NULL OR wb.analyzed_at < ?)
        LIMIT ?
    """, (cutoff, limit)).fetchall()
    conn.close()

    log.info(f"Wallets att analysera: {len(rows)}")

    analyzed = 0
    ai_found = 0
    for address, chain in rows:
        result = analyze_wallet(address, chain or "ethereum")
        if result:
            save_wallet_behavior(result)
            analyzed += 1
            if result["is_ai_agent"]:
                ai_found += 1
            log.info(f"  {address[:10]}... confidence={result['confidence']} type={result['agent_type']}")
        time.sleep(0.25)  # Etherscan rate limit: 5 req/s på free tier

    log.info(f"Analys klar: {analyzed} wallets, {ai_found} identifierade AI-agenter")
    return analyzed, ai_found

if __name__ == "__main__":
    run_batch_analysis(limit=200)
