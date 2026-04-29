"""
Sprint 7 WOW Analysis
=====================
WOW 1: AI-agent riskexponering (vilka agenter sitter i WARNING/CRITICAL tokens)
WOW 2: AI-agent kraschexponering (crash_prob_v3 > 0.5)
WOW 3: Structural Collapse-exponering (structural_weakness = 3)
WOW 5: Chain koncentrationsrisk med crash_prob-koppling
TIER 2: Daglig agent_protocol_snapshot för framtida exodus-backtest
"""
import os
import sqlite3, json, logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)).replace("/agentindex-factory/", "/agentindex/"),
    "crypto_trust.db",
)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ─── DB Setup ────────────────────────────────────────────────────────────────

def init_wow_tables(conn):
    conn.executescript("""
        -- WOW 1/2/3: Agent risk exponering
        CREATE TABLE IF NOT EXISTS agent_risk_exposure (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            agent_source TEXT NOT NULL,
            agent_name TEXT,
            chain TEXT,
            token_symbol TEXT,
            token_address TEXT,
            market_cap_usd REAL,

            -- Risk från nerq_risk_signals
            risk_level TEXT,           -- SAFE/WATCH/WARNING/CRITICAL
            structural_weakness INTEGER, -- 0-3
            trust_p3 REAL,
            sig6_structure REAL,
            ndd_current REAL,

            -- Crash från crash_model_v3
            crash_prob_v3 REAL,
            crash_label INTEGER,

            -- Flaggor
            is_structural_collapse INTEGER DEFAULT 0,  -- structural_weakness = 3
            is_high_crash_risk INTEGER DEFAULT 0,      -- crash_prob > 0.5
            is_warning_or_critical INTEGER DEFAULT 0,  -- risk_level WARNING/CRITICAL

            computed_at TEXT,
            UNIQUE(agent_id, agent_source, token_symbol)
        );
        CREATE INDEX IF NOT EXISTS idx_are_risk ON agent_risk_exposure(risk_level);
        CREATE INDEX IF NOT EXISTS idx_are_collapse ON agent_risk_exposure(is_structural_collapse);
        CREATE INDEX IF NOT EXISTS idx_are_crash ON agent_risk_exposure(crash_prob_v3 DESC);
        CREATE INDEX IF NOT EXISTS idx_are_source ON agent_risk_exposure(agent_source);

        -- WOW 5: Chain koncentrationsrisk
        CREATE TABLE IF NOT EXISTS chain_concentration_risk (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chain TEXT NOT NULL UNIQUE,
            total_agents INTEGER DEFAULT 0,
            total_market_cap_usd REAL DEFAULT 0,
            ai_agent_ratio REAL DEFAULT 0,

            -- Riskexponering
            agents_in_critical INTEGER DEFAULT 0,
            agents_in_warning INTEGER DEFAULT 0,
            agents_in_watch INTEGER DEFAULT 0,
            agents_in_safe INTEGER DEFAULT 0,
            agents_structural_collapse INTEGER DEFAULT 0,
            agents_high_crash_risk INTEGER DEFAULT 0,

            -- Kapital i riskzonen
            mcap_in_critical_usd REAL DEFAULT 0,
            mcap_in_warning_usd REAL DEFAULT 0,
            mcap_high_crash_risk_usd REAL DEFAULT 0,
            mcap_structural_collapse_usd REAL DEFAULT 0,

            -- Koncentrationsrisk-score 0-10
            concentration_risk_score REAL DEFAULT 0,
            risk_summary TEXT,

            computed_at TEXT
        );

        -- TIER 2: Daglig snapshot för exodus-backtest
        CREATE TABLE IF NOT EXISTS agent_protocol_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            protocol_id TEXT NOT NULL,
            agent_count INTEGER DEFAULT 0,
            total_market_cap_usd REAL DEFAULT 0,
            sources_json TEXT,
            UNIQUE(snapshot_date, protocol_id)
        );
        CREATE INDEX IF NOT EXISTS idx_aps_date ON agent_protocol_snapshot(snapshot_date);
        CREATE INDEX IF NOT EXISTS idx_aps_protocol ON agent_protocol_snapshot(protocol_id);
    """)
    conn.commit()
    log.info("WOW-tabeller initierade")

# ─── WOW 1/2/3: Agent Risk Exponering ────────────────────────────────────────

def compute_agent_risk_exposure(conn):
    """
    Kopplar agent_crypto_profile → nerq_risk_signals + crash_model_v3_predictions
    via token_symbol. Sparar i agent_risk_exposure.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Hämta senaste risk_signals per token
    risk_map = {}
    rows = conn.execute("""
        SELECT token_id, risk_level, structural_weakness, trust_p3,
               sig6_structure, ndd_current
        FROM nerq_risk_signals
    """).fetchall()
    for r in rows:
        risk_map[r["token_id"].upper()] = dict(r)

    # Hämta senaste crash_prob per token
    crash_map = {}
    rows = conn.execute("""
        SELECT token_id, crash_prob_v3, crash_label
        FROM crash_model_v3_predictions
        WHERE date = (SELECT MAX(date) FROM crash_model_v3_predictions)
    """).fetchall()
    for r in rows:
        crash_map[r["token_id"].upper()] = dict(r)

    # Hämta alla agenter med token_symbol
    agents = conn.execute("""
        SELECT agent_id, source, agent_name, chain,
               token_symbol, token_address, market_cap_usd
        FROM agent_crypto_profile
        WHERE token_symbol IS NOT NULL AND token_symbol != ''
    """).fetchall()

    saved = 0
    for a in agents:
        sym = (a["token_symbol"] or "").upper()
        risk = risk_map.get(sym, {})
        crash = crash_map.get(sym, {})

        if not risk and not crash:
            continue  # Ingen matchning, hoppa över

        risk_level = risk.get("risk_level")
        sw = risk.get("structural_weakness", 0) or 0
        crash_prob = crash.get("crash_prob_v3", 0) or 0

        try:
            conn.execute("""
                INSERT INTO agent_risk_exposure
                (agent_id, agent_source, agent_name, chain, token_symbol,
                 token_address, market_cap_usd, risk_level, structural_weakness,
                 trust_p3, sig6_structure, ndd_current, crash_prob_v3, crash_label,
                 is_structural_collapse, is_high_crash_risk, is_warning_or_critical,
                 computed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(agent_id, agent_source, token_symbol) DO UPDATE SET
                    risk_level=excluded.risk_level,
                    structural_weakness=excluded.structural_weakness,
                    trust_p3=excluded.trust_p3,
                    crash_prob_v3=excluded.crash_prob_v3,
                    is_structural_collapse=excluded.is_structural_collapse,
                    is_high_crash_risk=excluded.is_high_crash_risk,
                    is_warning_or_critical=excluded.is_warning_or_critical,
                    computed_at=excluded.computed_at
            """, (
                a["agent_id"], a["source"], a["agent_name"], a["chain"],
                a["token_symbol"], a["token_address"], a["market_cap_usd"],
                risk_level,
                sw,
                risk.get("trust_p3"), risk.get("sig6_structure"), risk.get("ndd_current"),
                crash_prob, crash.get("crash_label"),
                1 if sw >= 3 else 0,
                1 if crash_prob > 0.5 else 0,
                1 if risk_level in ("WARNING", "CRITICAL") else 0,
                now
            ))
            saved += 1
        except Exception as e:
            log.warning(f"Fel för {a['agent_id']}: {e}")

    conn.commit()
    log.info(f"Agent risk exponering: {saved} agenter matchade")
    return saved

# ─── WOW 5: Chain Koncentrationsrisk ────────────────────────────────────────

def compute_chain_concentration_risk(conn):
    """
    Per chain: hur mycket kapital sitter i riskzonen?
    Beräknar koncentrationsrisk-score 0-10.
    """
    now = datetime.now(timezone.utc).isoformat()

    chains = conn.execute("""
        SELECT LOWER(chain) as chain,
               COUNT(*) as total_agents,
               SUM(market_cap_usd) as total_mcap
        FROM agent_crypto_profile
        WHERE chain IS NOT NULL AND chain != ''
        GROUP BY LOWER(chain)
        HAVING total_agents >= 3
        ORDER BY total_agents DESC
    """).fetchall()

    for c in chains:
        chain = c["chain"]
        total = c["total_agents"]
        total_mcap = c["total_mcap"] or 0

        # Riskfördelning för denna chain
        risk_dist = conn.execute("""
            SELECT
                SUM(CASE WHEN risk_level='CRITICAL' THEN 1 ELSE 0 END) as critical,
                SUM(CASE WHEN risk_level='WARNING' THEN 1 ELSE 0 END) as warning,
                SUM(CASE WHEN risk_level='WATCH' THEN 1 ELSE 0 END) as watch,
                SUM(CASE WHEN risk_level='SAFE' THEN 1 ELSE 0 END) as safe,
                SUM(CASE WHEN is_structural_collapse=1 THEN 1 ELSE 0 END) as collapse,
                SUM(CASE WHEN is_high_crash_risk=1 THEN 1 ELSE 0 END) as high_crash,
                SUM(CASE WHEN risk_level='CRITICAL' THEN COALESCE(market_cap_usd,0) ELSE 0 END) as mcap_critical,
                SUM(CASE WHEN risk_level='WARNING' THEN COALESCE(market_cap_usd,0) ELSE 0 END) as mcap_warning,
                SUM(CASE WHEN is_high_crash_risk=1 THEN COALESCE(market_cap_usd,0) ELSE 0 END) as mcap_crash,
                SUM(CASE WHEN is_structural_collapse=1 THEN COALESCE(market_cap_usd,0) ELSE 0 END) as mcap_collapse
            FROM agent_risk_exposure
            WHERE LOWER(chain) = ?
        """, (chain,)).fetchone()

        # Fallback: räkna från agent_crypto_profile om inga risk-matchningar
        if not risk_dist or risk_dist["critical"] is None:
            agents_at_risk = 0
            mcap_critical = 0
            mcap_warning = 0
            mcap_crash = 0
            mcap_collapse = 0
            n_critical = n_warning = n_watch = n_safe = n_collapse = n_crash = 0
        else:
            n_critical = risk_dist["critical"] or 0
            n_warning = risk_dist["warning"] or 0
            n_watch = risk_dist["watch"] or 0
            n_safe = risk_dist["safe"] or 0
            n_collapse = risk_dist["collapse"] or 0
            n_crash = risk_dist["high_crash"] or 0
            mcap_critical = risk_dist["mcap_critical"] or 0
            mcap_warning = risk_dist["mcap_warning"] or 0
            mcap_crash = risk_dist["mcap_crash"] or 0
            mcap_collapse = risk_dist["mcap_collapse"] or 0

        # Koncentrationsrisk-score 0-10
        # Baseras på: andel agenter i riskzonen + kapitalkoncentration
        risk_agents = n_critical + n_warning + n_collapse
        risk_ratio = risk_agents / total if total > 0 else 0
        mcap_risk_ratio = (mcap_critical + mcap_warning) / total_mcap if total_mcap > 0 else 0

        # Hög agentkoncentration på en chain ökar risken (systemisk)
        # Om 90%+ av alla agenter är på en chain → multiplicera risken
        total_all_agents = conn.execute("SELECT COUNT(*) FROM agent_crypto_profile").fetchone()[0]
        chain_concentration = total / total_all_agents if total_all_agents > 0 else 0

        score = (
            risk_ratio * 4.0 +           # 40% vikt: andel riskagenter
            mcap_risk_ratio * 3.0 +      # 30% vikt: kapital i risk
            chain_concentration * 3.0    # 30% vikt: systemisk koncentration
        ) * 10

        score = min(round(score, 2), 10.0)

        # Human-readable summary
        risk_pct = round(risk_ratio * 100, 1)
        mcap_risk_m = round((mcap_critical + mcap_warning) / 1e6, 1)
        summary = (
            f"{total:,} AI-agenter på {chain.title()}. "
            f"{risk_pct}% exponerade mot WARNING/CRITICAL tokens. "
            f"${mcap_risk_m}M i riskkapital. "
            f"Koncentrationsrisk: {score}/10."
        )

        conn.execute("""
            INSERT INTO chain_concentration_risk
            (chain, total_agents, total_market_cap_usd, ai_agent_ratio,
             agents_in_critical, agents_in_warning, agents_in_watch, agents_in_safe,
             agents_structural_collapse, agents_high_crash_risk,
             mcap_in_critical_usd, mcap_in_warning_usd,
             mcap_high_crash_risk_usd, mcap_structural_collapse_usd,
             concentration_risk_score, risk_summary, computed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(chain) DO UPDATE SET
                total_agents=excluded.total_agents,
                total_market_cap_usd=excluded.total_market_cap_usd,
                agents_in_critical=excluded.agents_in_critical,
                agents_in_warning=excluded.agents_in_warning,
                agents_structural_collapse=excluded.agents_structural_collapse,
                agents_high_crash_risk=excluded.agents_high_crash_risk,
                mcap_in_critical_usd=excluded.mcap_in_critical_usd,
                mcap_high_crash_risk_usd=excluded.mcap_high_crash_risk_usd,
                concentration_risk_score=excluded.concentration_risk_score,
                risk_summary=excluded.risk_summary,
                computed_at=excluded.computed_at
        """, (
            chain, total, total_mcap, chain_concentration,
            n_critical, n_warning, n_watch, n_safe,
            n_collapse, n_crash,
            mcap_critical, mcap_warning, mcap_crash, mcap_collapse,
            score, summary, now
        ))

    conn.commit()
    log.info(f"Chain koncentrationsrisk beräknad för {len(chains)} chains")

# ─── TIER 2: Daglig Protocol Snapshot ────────────────────────────────────────

def take_protocol_snapshot(conn):
    """
    Daglig snapshot av agent-räkning per protokoll.
    Bygger tidsseriedata för framtida exodus-backtest.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Räkna agenter per relation_type='protocol' entity
    protocols = conn.execute("""
        SELECT r.entity_id as protocol_id,
               COUNT(DISTINCT r.agent_id) as agent_count,
               SUM(COALESCE(a.market_cap_usd, 0)) as total_mcap,
               GROUP_CONCAT(DISTINCT a.source) as sources
        FROM agent_crypto_relations r
        JOIN agent_crypto_profile a ON r.agent_id = a.agent_id AND r.agent_source = a.source
        WHERE r.relation_type = 'protocol'
        GROUP BY r.entity_id
    """).fetchall()

    # Lägg också till chain-level snapshots
    chains = conn.execute("""
        SELECT LOWER(chain) as protocol_id,
               COUNT(*) as agent_count,
               SUM(COALESCE(market_cap_usd, 0)) as total_mcap,
               GROUP_CONCAT(DISTINCT source) as sources
        FROM agent_crypto_profile
        WHERE chain IS NOT NULL AND chain != ''
        GROUP BY LOWER(chain)
    """).fetchall()

    saved = 0
    for p in list(protocols) + list(chains):
        try:
            conn.execute("""
                INSERT INTO agent_protocol_snapshot
                (snapshot_date, protocol_id, agent_count, total_market_cap_usd, sources_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_date, protocol_id) DO UPDATE SET
                    agent_count=excluded.agent_count,
                    total_market_cap_usd=excluded.total_market_cap_usd
            """, (today, p["protocol_id"], p["agent_count"],
                  p["total_mcap"], p["sources"]))
            saved += 1
        except Exception as e:
            log.warning(f"Snapshot fel för {p['protocol_id']}: {e}")

    conn.commit()
    log.info(f"Protocol snapshot {today}: {saved} protokoll/chains")
    return saved

# ─── WOW Stats för rapport och API ───────────────────────────────────────────

def get_wow_stats(conn) -> dict:
    """Sammanfattning av alla WOW-analyser."""

    # WOW 1: Riskfördelning
    risk_dist = conn.execute("""
        SELECT risk_level, COUNT(*) as n, SUM(COALESCE(market_cap_usd,0)) as mcap
        FROM agent_risk_exposure
        GROUP BY risk_level ORDER BY
        CASE risk_level WHEN 'CRITICAL' THEN 1 WHEN 'WARNING' THEN 2
                        WHEN 'WATCH' THEN 3 WHEN 'SAFE' THEN 4 ELSE 5 END
    """).fetchall()

    # WOW 2: Kraschexponering
    crash_stats = conn.execute("""
        SELECT
            COUNT(*) as total_matched,
            SUM(is_high_crash_risk) as high_crash_count,
            SUM(CASE WHEN is_high_crash_risk=1 THEN COALESCE(market_cap_usd,0) ELSE 0 END) as mcap_at_risk,
            AVG(crash_prob_v3) as avg_crash_prob
        FROM agent_risk_exposure
        WHERE crash_prob_v3 IS NOT NULL
    """).fetchone()

    # WOW 3: Structural Collapse
    collapse_agents = conn.execute("""
        SELECT agent_id, agent_source, agent_name, chain, token_symbol,
               market_cap_usd, structural_weakness, trust_p3, crash_prob_v3
        FROM agent_risk_exposure
        WHERE is_structural_collapse=1
        ORDER BY COALESCE(market_cap_usd,0) DESC
        LIMIT 20
    """).fetchall()

    # Top WARNING/CRITICAL agenter
    top_risk_agents = conn.execute("""
        SELECT agent_id, agent_source, agent_name, chain, token_symbol,
               market_cap_usd, risk_level, crash_prob_v3, structural_weakness
        FROM agent_risk_exposure
        WHERE risk_level IN ('WARNING', 'CRITICAL')
        ORDER BY COALESCE(market_cap_usd,0) DESC
        LIMIT 20
    """).fetchall()

    # Top crash-exponerade agenter
    top_crash_agents = conn.execute("""
        SELECT agent_id, agent_source, agent_name, chain, token_symbol,
               market_cap_usd, crash_prob_v3, risk_level
        FROM agent_risk_exposure
        WHERE is_high_crash_risk=1
        ORDER BY crash_prob_v3 DESC
        LIMIT 20
    """).fetchall()

    # WOW 5: Chain ranking
    chain_ranking = conn.execute("""
        SELECT chain, total_agents, total_market_cap_usd,
               agents_in_critical, agents_in_warning,
               agents_structural_collapse, agents_high_crash_risk,
               mcap_in_critical_usd, mcap_high_crash_risk_usd,
               concentration_risk_score, risk_summary
        FROM chain_concentration_risk
        ORDER BY concentration_risk_score DESC
    """).fetchall()

    # Totala exponeringssiffror
    total_agents = conn.execute("SELECT COUNT(*) FROM agent_crypto_profile").fetchone()[0]
    matched_agents = conn.execute("SELECT COUNT(DISTINCT agent_id) FROM agent_risk_exposure").fetchone()[0]

    return {
        "total_agents_indexed": total_agents,
        "agents_with_risk_data": matched_agents,
        "coverage_pct": round(matched_agents / total_agents * 100, 1) if total_agents > 0 else 0,
        "risk_distribution": [dict(r) for r in risk_dist],
        "crash_exposure": dict(crash_stats) if crash_stats else {},
        "structural_collapse_agents": [dict(r) for r in collapse_agents],
        "top_warning_critical_agents": [dict(r) for r in top_risk_agents],
        "top_crash_risk_agents": [dict(r) for r in top_crash_agents],
        "chain_concentration_ranking": [dict(r) for r in chain_ranking],
    }

# ─── Main ─────────────────────────────────────────────────────────────────────

def run():
    conn = get_conn()
    log.info("=== Sprint 7 WOW Analysis ===")

    init_wow_tables(conn)

    log.info("[1/4] Beräknar agent risk exponering (WOW 1/2/3)...")
    matched = compute_agent_risk_exposure(conn)

    log.info("[2/4] Beräknar chain koncentrationsrisk (WOW 5)...")
    compute_chain_concentration_risk(conn)

    log.info("[3/4] Tar daglig protocol snapshot (Tier 2)...")
    take_protocol_snapshot(conn)

    log.info("[4/4] Sammanställer WOW stats...")
    stats = get_wow_stats(conn)
    conn.close()

    print("\n" + "="*60)
    print("SPRINT 7 WOW RESULTS")
    print("="*60)
    print(f"\nTotala agenter:        {stats['total_agents_indexed']:,}")
    print(f"Med riskdata:          {stats['agents_with_risk_data']:,} ({stats['coverage_pct']}%)")

    print("\n--- WOW 1: Riskfördelning ---")
    for r in stats["risk_distribution"]:
        mcap_m = round((r["mcap"] or 0) / 1e6, 1)
        print(f"  {r['risk_level'] or 'OKÄND':10} {r['n']:6,} agenter  ${mcap_m}M")

    ce = stats["crash_exposure"]
    print(f"\n--- WOW 2: Kraschexponering ---")
    print(f"  Agenter med crash_prob > 0.5: {ce.get('high_crash_count', 0):,}")
    print(f"  Kapital i riskzonen:          ${round((ce.get('mcap_at_risk') or 0)/1e6, 1)}M")
    print(f"  Snitt crash_prob:             {round((ce.get('avg_crash_prob') or 0)*100, 1)}%")

    print(f"\n--- WOW 3: Structural Collapse ---")
    print(f"  Agenter i Structural Collapse-tokens: {len(stats['structural_collapse_agents'])}")
    for a in stats["structural_collapse_agents"][:5]:
        mcap = round((a["market_cap_usd"] or 0) / 1e6, 2)
        print(f"  {a['agent_name'] or a['agent_id']:30} {a['token_symbol']:8} ${mcap}M  crash:{round((a['crash_prob_v3'] or 0)*100, 0)}%")

    print(f"\n--- WOW 5: Chain Koncentrationsrisk ---")
    for c in stats["chain_concentration_ranking"][:8]:
        mcap_m = round((c["total_market_cap_usd"] or 0) / 1e6, 1)
        print(f"  {c['chain']:15} {c['total_agents']:6,} agenter  ${mcap_m}M  risk:{c['concentration_risk_score']}/10")

    return stats

if __name__ == "__main__":
    run()
