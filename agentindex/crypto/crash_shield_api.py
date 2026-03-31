#!/usr/bin/env python3
"""
ZARQ CRASH SHIELD API — Sprint 8B
"""
import sqlite3
import json
import os
import time
import hashlib
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "crypto_trust.db")

CRASH_SHIELD_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS crash_shield_webhooks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        webhook_id TEXT UNIQUE NOT NULL,
        url TEXT NOT NULL,
        portfolio_json TEXT NOT NULL,
        alert_levels TEXT DEFAULT 'CRITICAL,HIGH',
        registered_at TEXT NOT NULL,
        last_triggered TEXT,
        trigger_count INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS crash_shield_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        webhook_id TEXT,
        event_type TEXT NOT NULL,
        trigger_token TEXT,
        alert_level TEXT,
        affected_holdings_json TEXT,
        estimated_loss_usd REAL,
        cascade_depth INTEGER,
        prevented_usd REAL DEFAULT 0,
        fired_at TEXT NOT NULL,
        delivered INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS crash_shield_prevented (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        webhook_id TEXT,
        event_id INTEGER,
        prevented_usd REAL NOT NULL,
        confirmed_at TEXT NOT NULL
    )"""
]

def ensure_crash_shield_tables():
    conn = sqlite3.connect(DB_PATH)
    for stmt in CRASH_SHIELD_SCHEMA:
        conn.execute(stmt)
    conn.commit()
    conn.close()


class PortfolioAnalyzer:

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def analyze(self, holdings: List[Dict], portfolio_value_usd: float = 100_000, include_cascade: bool = True) -> Dict[str, Any]:
        t0 = time.time()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        normalized = self._normalize_holdings(holdings, portfolio_value_usd)
        direct_results = []
        for holding in normalized:
            risk_data = self._get_token_risk(conn, holding["token"])
            direct_results.append({**holding, **risk_data})
        direct_results.sort(key=lambda x: x.get("risk_score", 0), reverse=True)
        portfolio_risk = self._aggregate_portfolio_risk(direct_results)
        cascade_summary = {}
        if include_cascade:
            try:
                from agentindex.crypto.propagated_risk_engine import get_engine
                engine = get_engine()
                cascade_summary = self._compute_indirect_risk(engine, direct_results)
            except Exception as e:
                logger.warning(f"Cascade analysis skipped: {e}")
                cascade_summary = {"error": str(e), "skipped": True}
        conn.close()
        elapsed_ms = round((time.time() - t0) * 1000, 1)
        return {
            "portfolio_summary": portfolio_risk,
            "holdings": direct_results,
            "indirect_risk": cascade_summary,
            "recommendations": self._generate_recommendations(direct_results, portfolio_risk),
            "computed_at": datetime.utcnow().isoformat() + "Z",
            "elapsed_ms": elapsed_ms,
        }

    def _normalize_holdings(self, holdings: List[Dict], total_value: float) -> List[Dict]:
        result = []
        total_weight = sum(h.get("weight", 0) for h in holdings if h.get("weight"))
        has_weights = total_weight > 0
        for h in holdings:
            token = h.get("token") or h.get("symbol") or ""
            if not token:
                continue
            if h.get("value_usd") is not None:
                value_usd = float(h["value_usd"])
                weight = value_usd / total_value if total_value > 0 else 0
            elif "weight" in h and has_weights:
                weight = float(h["weight"]) / total_weight
                value_usd = weight * total_value
            else:
                weight = 1.0 / len(holdings)
                value_usd = weight * total_value
            result.append({"token": token.upper(), "weight": round(weight, 4), "value_usd": round(value_usd, 2)})
        return result

    def _get_token_risk(self, conn, token_symbol: str) -> Dict:
        try:
            # Sök på token_id direkt (lowercase) eller via symbol i crypto_rating_daily
            row = conn.execute("""
                SELECT r.token_id, r.risk_level, r.structural_weakness,
                       r.trust_score, r.ndd_current, r.sig6_structure, r.trust_p3,
                       COALESCE(d.symbol, r.token_id) as symbol,
                       c.crash_prob_v3 as crash_probability
                FROM nerq_risk_signals r
                LEFT JOIN (
                    SELECT token_id, symbol FROM crypto_rating_daily
                    WHERE run_date = (SELECT MAX(run_date) FROM crypto_rating_daily)
                ) d ON r.token_id = d.token_id
                LEFT JOIN (
                    SELECT token_id, crash_prob_v3 FROM crash_model_v3_predictions
                    WHERE date = (SELECT MAX(date) FROM crash_model_v3_predictions)
                ) c ON r.token_id = c.token_id
                WHERE LOWER(r.token_id) = LOWER(?)
                   OR LOWER(COALESCE(d.symbol, '')) = LOWER(?)
                LIMIT 1
            """, (token_symbol, token_symbol)).fetchone()
            if not row:
                return {"found": False, "risk_level": "UNKNOWN", "risk_score": 0, "note": f"Token {token_symbol} not in ZARQ database"}
            sw = row["structural_weakness"] or 0
            cp = row["crash_probability"] or 0.0
            trust = row["trust_score"] or 50.0
            ndd = row["ndd_current"] or 0.0
            risk_score = min(100, sw * 25 + cp * 40 + max(0, (40 - trust)) * 0.5 + max(0, (3 - ndd)) * 3)
            return {
                "found": True, "token_id": row["token_id"], "chain": "unknown",
                "risk_level": row["risk_level"] or "UNKNOWN", "structural_weakness": sw,
                "trust_score": round(trust, 1), "ndd_current": round(ndd, 2),
                "crash_probability": round(cp, 3), "sig6": round(row["sig6_structure"] or 0, 2),
                "p3": round(row["trust_p3"] or 0, 1), "risk_score": round(risk_score, 1),
                "is_structural_collapse": sw >= 3, "is_high_crash_risk": cp > 0.5,
            }
        except Exception as e:
            logger.warning(f"_get_token_risk({token_symbol}): {e}")
            return {"found": False, "risk_level": "UNKNOWN", "risk_score": 0, "error": str(e)}

    def _aggregate_portfolio_risk(self, holdings: List[Dict]) -> Dict:
        if not holdings:
            return {}
        total_value = sum(h.get("value_usd", 0) for h in holdings)
        found = [h for h in holdings if h.get("found")]
        if not found or total_value == 0:
            return {"portfolio_risk_score": 0, "risk_level": "UNKNOWN", "total_value_usd": total_value, "coverage": 0}
        weighted_risk = sum(h["risk_score"] * h["value_usd"] for h in found) / total_value
        collapses = [h for h in found if h.get("is_structural_collapse")]
        high_crash = [h for h in found if h.get("is_high_crash_risk")]
        collapse_exposure = sum(h["value_usd"] for h in collapses)
        collapse_pct = collapse_exposure / total_value * 100 if total_value > 0 else 0
        if weighted_risk >= 60 or collapse_pct >= 30:
            level = "CRITICAL"
        elif weighted_risk >= 40 or collapse_pct >= 15:
            level = "HIGH"
        elif weighted_risk >= 20 or collapse_pct >= 5:
            level = "MEDIUM"
        else:
            level = "LOW"
        return {
            "portfolio_risk_score": round(weighted_risk, 1), "risk_level": level,
            "total_value_usd": round(total_value, 2), "coverage": round(len(found) / len(holdings) * 100, 1),
            "structural_collapses": len(collapses), "collapse_exposure_usd": round(collapse_exposure, 0),
            "collapse_exposure_pct": round(collapse_pct, 1), "high_crash_risk_tokens": len(high_crash),
            "tokens_analyzed": len(found), "tokens_not_found": len(holdings) - len(found),
        }

    def _compute_indirect_risk(self, engine, holdings: List[Dict]) -> Dict:
        critical = [h for h in holdings if h.get("is_structural_collapse") or h.get("is_high_crash_risk")]
        if not critical:
            return {"indirect_risk_level": "LOW", "cascade_simulations": 0, "note": "No high-risk holdings to simulate cascade from"}
        all_affected = set()
        total_indirect_exposure = 0.0
        simulations = []
        for holding in critical[:5]:
            token = holding.get("token", "")
            result = engine.simulate_cascade(trigger_id=token, scenario="collapse", severity=min(1.0, holding.get("risk_score", 50) / 100), max_hops=3)
            if "error" not in result:
                affected = [n["symbol"] for n in result.get("cascade_chain", []) if not n["is_trigger"]]
                all_affected.update(affected)
                total_indirect_exposure += result["simulation"].get("total_exposure_usd", 0)
                simulations.append({"trigger": token, "nodes_affected": result["simulation"]["nodes_affected"], "exposure_usd": result["simulation"]["total_exposure_usd"]})
        holding_tokens = {h["token"] for h in holdings}
        contagion_overlap = holding_tokens & all_affected
        return {
            "indirect_risk_level": "HIGH" if len(contagion_overlap) >= 2 else "MEDIUM" if contagion_overlap else "LOW",
            "cascade_simulations": len(simulations), "simulations": simulations,
            "portfolio_tokens_in_cascade_path": list(contagion_overlap),
            "total_indirect_exposure_usd": round(total_indirect_exposure, 0),
            "unique_external_nodes_affected": len(all_affected),
        }

    def _generate_recommendations(self, holdings: List[Dict], portfolio_risk: Dict) -> List[Dict]:
        recs = []
        for h in holdings:
            if h.get("is_structural_collapse"):
                recs.append({"priority": "CRITICAL", "token": h["token"], "action": "REDUCE_OR_EXIT", "reason": f"Structural Collapse — trust_score {h.get('trust_score','?')}, NDD {h.get('ndd_current','?')}", "weight_pct": round(h.get("weight", 0) * 100, 1), "value_usd": h.get("value_usd", 0)})
            elif h.get("is_high_crash_risk") and h.get("weight", 0) > 0.1:
                recs.append({"priority": "HIGH", "token": h["token"], "action": "REDUCE", "reason": f"High crash probability {h.get('crash_probability', 0):.1%} — consider reducing", "weight_pct": round(h.get("weight", 0) * 100, 1), "value_usd": h.get("value_usd", 0)})
        collapse_pct = portfolio_risk.get("collapse_exposure_pct", 0)
        if collapse_pct > 20:
            recs.append({"priority": "CRITICAL", "token": "PORTFOLIO", "action": "REBALANCE", "reason": f"{collapse_pct:.1f}% of portfolio in Structural Collapse tokens"})
        recs.sort(key=lambda x: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(x["priority"], 4))
        return recs


class CrashShieldManager:

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.analyzer = PortfolioAnalyzer(db_path)
        ensure_crash_shield_tables()

    def register_webhook(self, url: str, portfolio: List[Dict], alert_levels: List[str] = None, portfolio_value_usd: float = 100_000) -> Dict:
        if alert_levels is None:
            alert_levels = ["CRITICAL", "HIGH"]
        webhook_id = hashlib.sha256(f"{url}:{json.dumps(portfolio, sort_keys=True)}:{time.time()}".encode()).hexdigest()[:16]
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("INSERT OR REPLACE INTO crash_shield_webhooks (webhook_id, url, portfolio_json, alert_levels, registered_at) VALUES (?,?,?,?,?)",
                (webhook_id, url, json.dumps(portfolio), ",".join(alert_levels), datetime.utcnow().isoformat() + "Z"))
            conn.commit()
        finally:
            conn.close()
        analysis = self.analyzer.analyze(portfolio, portfolio_value_usd)
        return {
            "webhook_id": webhook_id, "status": "registered", "url": url, "alert_levels": alert_levels,
            "initial_analysis": analysis["portfolio_summary"],
            "immediate_alerts": [h for h in analysis["holdings"] if h.get("is_structural_collapse") or h.get("is_high_crash_risk")],
            "recommendations": analysis["recommendations"],
        }

    def list_webhooks(self) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT webhook_id, url, alert_levels, registered_at, last_triggered, trigger_count, is_active FROM crash_shield_webhooks WHERE is_active = 1 ORDER BY registered_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_prevented_total(self) -> Dict:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT COUNT(*), SUM(estimated_loss_usd), SUM(prevented_usd) FROM crash_shield_events").fetchone()
        conn.close()
        total_at_risk = row[1] or 0
        total_prevented = row[2] or 0
        return {
            "total_events": row[0] or 0,
            "total_at_risk_usd": round(total_at_risk, 0),
            "total_prevented_usd": round(total_prevented, 0),
            "prevention_rate_pct": round(total_prevented / total_at_risk * 100, 1) if total_at_risk > 0 else 0,
            "computed_at": datetime.utcnow().isoformat() + "Z",
        }


_manager_instance = None

def get_crash_shield_manager() -> CrashShieldManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = CrashShieldManager(DB_PATH)
    return _manager_instance
