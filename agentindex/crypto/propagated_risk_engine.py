#!/usr/bin/env python3
"""
ZARQ PROPAGATED RISK ENGINE — Sprint 8A
"""
import sqlite3
import json
import os
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "crypto_trust.db")

SCENARIOS = {
    "collapse":   {"label": "Structural Collapse",  "btc_shock": 0.0,   "severity_default": 1.0},
    "btc_crash":  {"label": "BTC -40% Crash",       "btc_shock": -0.40, "severity_default": 0.8},
    "stablecoin": {"label": "Stablecoin Depeg",     "btc_shock": -0.10, "severity_default": 0.9},
    "exchange":   {"label": "Exchange Failure",     "btc_shock": -0.20, "severity_default": 0.7},
    "custom":     {"label": "Custom Scenario",      "btc_shock": 0.0,   "severity_default": 0.5},
}

EDGE_WEIGHTS = {
    "ecosystem":    0.70,
    "correlation":  0.55,
    "bridge":       0.85,
    "stablecoin":   0.90,
    "oracle":       0.75,
    "agent_shared": 0.60,
}

HOP_DAMPENING = 0.65


class PropagatedRiskEngine:

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._nodes: Dict[str, Dict] = {}
        self._edges: Dict[str, List[Dict]] = defaultdict(list)
        self._loaded = False
        self._load_time: Optional[float] = None

    def ensure_loaded(self):
        if not self._loaded:
            self._build_graph()

    def _build_graph(self):
        t0 = time.time()
        logger.info("PropagatedRiskEngine: building graph...")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        self._load_token_nodes(conn)
        self._load_agent_data(conn)
        self._build_edges_from_contagion(conn)
        self._build_edges_from_agents(conn)
        conn.close()
        self._loaded = True
        self._load_time = time.time() - t0
        logger.info(f"PropagatedRiskEngine: {len(self._nodes)} nodes, {sum(len(v) for v in self._edges.values())} edges, {self._load_time:.2f}s")

    def _load_token_nodes(self, conn):
        try:
            rows = conn.execute("""
                SELECT r.token_id, r.risk_level, r.structural_weakness,
                       r.trust_score, r.ndd_current, r.sig6_structure,
                       r.trust_p3, r.ndd_min_4w,
                       COALESCE(d.symbol, r.token_id) as symbol,
                       COALESCE(ch.chain, 'unknown') as chain,
                       c.crash_prob_v3 as crash_probability
                FROM nerq_risk_signals r
                LEFT JOIN (
                    SELECT token_id, symbol
                    FROM crypto_rating_daily
                    WHERE run_date = (SELECT MAX(run_date) FROM crypto_rating_daily)
                ) d ON r.token_id = d.token_id
                LEFT JOIN (
                    SELECT token_id, crash_prob_v3
                    FROM crash_model_v3_predictions
                    WHERE date = (SELECT MAX(date) FROM crash_model_v3_predictions)
                ) c ON r.token_id = c.token_id
                LEFT JOIN (
                    SELECT LOWER(token_symbol) as token_id, chain
                    FROM agent_risk_exposure
                    WHERE chain IS NOT NULL
                    GROUP BY token_symbol
                ) ch ON LOWER(r.token_id) = ch.token_id
                WHERE r.token_id IS NOT NULL
            """).fetchall()
            for row in rows:
                nid = f"token:{row['token_id']}"
                self._nodes[nid] = {
                    "id": nid, "type": "token",
                    "token_id": row["token_id"],
                    "symbol": row["symbol"] or row["token_id"],
                    "chain": "unknown",
                    "risk_level": row["risk_level"] or "UNKNOWN",
                    "structural_weakness": row["structural_weakness"] or 0,
                    "trust_score": row["trust_score"] or 50.0,
                    "ndd": row["ndd_current"] or 0.0,
                    "crash_prob": row["crash_probability"] or 0.0,
                    "sig6": row["sig6_structure"] or 0.0,
                    "p3": row["trust_p3"] or 50.0,
                    "ai_agent_ratio": 0.0,
                    "ai_controlled_tvl_usd": 0.0,
                }
        except Exception as e:
            logger.warning(f"_load_token_nodes: {e}")

    def _load_agent_data(self, conn):
        try:
            rows = conn.execute("""
                SELECT entity_id, ai_agent_ratio, ai_controlled_tvl_usd,
                       total_agents, identified_ai_agents
                FROM agent_activity_index WHERE entity_type = 'token'
            """).fetchall()
            for row in rows:
                nid = f"token:{row['entity_id']}"
                if nid in self._nodes:
                    self._nodes[nid]["ai_agent_ratio"] = row["ai_agent_ratio"] or 0.0
                    self._nodes[nid]["ai_controlled_tvl_usd"] = row["ai_controlled_tvl_usd"] or 0.0
                    self._nodes[nid]["total_agents"] = row["total_agents"] or 0
                    self._nodes[nid]["identified_ai_agents"] = row["identified_ai_agents"] or 0
        except Exception as e:
            logger.warning(f"_load_agent_data: {e}")

    def _build_edges_from_contagion(self, conn):
        import json as _json
        # Hämta chain-data från defi_protocol_tokens
        chain_tokens: Dict[str, List[str]] = defaultdict(list)
        try:
            rows = conn.execute("""
                SELECT d.token_id, d.chains
                FROM defi_protocol_tokens d
                WHERE d.token_id IS NOT NULL AND d.chains IS NOT NULL
            """).fetchall()
            for row in rows:
                nid = f"token:{row[0]}"
                if nid not in self._nodes:
                    continue
                try:
                    chains = _json.loads(row[1])
                    if isinstance(chains, list) and chains:
                        primary_chain = chains[0].lower().replace(" ", "-")
                        self._nodes[nid]["chain"] = primary_chain
                        chain_tokens[primary_chain].append(nid)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"_build_edges_from_contagion chain load: {e}")

        # Bygg ecosystem-kanter för tokens på samma chain
        for chain, token_list in chain_tokens.items():
            if len(token_list) > 1:
                chain_nid = f"chain:{chain}"
                if chain_nid not in self._nodes:
                    self._nodes[chain_nid] = {
                        "id": chain_nid, "type": "chain", "name": chain,
                        "risk_level": "UNKNOWN", "structural_weakness": 0,
                        "trust_score": 50.0, "crash_prob": 0.0, "ai_agent_ratio": 0.0,
                    }
                for token_nid in token_list:
                    self._edges[token_nid].append({"target": chain_nid, "type": "ecosystem", "weight": EDGE_WEIGHTS["ecosystem"]})
                    self._edges[chain_nid].append({"target": token_nid, "type": "ecosystem", "weight": EDGE_WEIGHTS["ecosystem"]})

        # Correlation-kanter: tokens med samma risk_level
        risk_groups: Dict[str, List[str]] = defaultdict(list)
        for nid, node in self._nodes.items():
            if node["type"] == "token" and node.get("risk_level") in ("CRITICAL", "WARNING"):
                risk_groups[node["risk_level"]].append(nid)
        for risk_level, token_list in risk_groups.items():
            weight = EDGE_WEIGHTS["correlation"]
            for i, t1 in enumerate(token_list):
                for t2 in token_list[i+1:]:
                    self._edges[t1].append({"target": t2, "type": "correlation", "weight": weight})
                    self._edges[t2].append({"target": t1, "type": "correlation", "weight": weight})

        # Uppdatera chain på noder som saknar den via defi_protocol_tokens
        try:
            import json as _j2
            rows2 = conn.execute("""
                SELECT LOWER(d.token_id) as tid, d.chains
                FROM defi_protocol_tokens d
                WHERE d.token_id IS NOT NULL AND d.chains IS NOT NULL
            """).fetchall()
            for row in rows2:
                nid = f"token:{row[0]}"
                if nid in self._nodes and self._nodes[nid].get("chain") == "unknown":
                    try:
                        chains = _j2.loads(row[1])
                        if isinstance(chains, list) and chains:
                            primary = chains[0].lower().replace(" ", "-")
                            self._nodes[nid]["chain"] = primary
                            chain_tokens[primary].append(nid)
                    except Exception:
                        pass
            # Maila in nya chain-noder och kanter
            for chain, token_list in chain_tokens.items():
                if len(token_list) > 1:
                    chain_nid = f"chain:{chain}"
                    if chain_nid not in self._nodes:
                        self._nodes[chain_nid] = {
                            "id": chain_nid, "type": "chain", "name": chain,
                            "risk_level": "UNKNOWN", "structural_weakness": 0,
                            "trust_score": 50.0, "crash_prob": 0.0, "ai_agent_ratio": 0.0,
                        }
                    for token_nid in set(token_list):
                        already = any(e["target"] == chain_nid for e in self._edges.get(token_nid, []))
                        if not already:
                            self._edges[token_nid].append({"target": chain_nid, "type": "ecosystem", "weight": EDGE_WEIGHTS["ecosystem"]})
                            self._edges[chain_nid].append({"target": token_nid, "type": "ecosystem", "weight": EDGE_WEIGHTS["ecosystem"]})
        except Exception as e:
            logger.warning(f"defi chain enrichment: {e}")

    def _build_edges_from_agents(self, conn):
        try:
            rows = conn.execute("SELECT agent_id, token_symbol FROM agent_risk_exposure WHERE token_symbol IS NOT NULL").fetchall()
            agent_tokens: Dict[str, List[str]] = defaultdict(list)
            for row in rows:
                sym_lower = (row["token_symbol"] or "").lower()
                # Match på token_id direkt (nid = "token:{token_id}")
                nid = f"token:{sym_lower}"
                if nid in self._nodes:
                    agent_tokens[row["agent_id"]].append(nid)
            for agent_id, token_list in agent_tokens.items():
                unique = list(set(token_list))
                if len(unique) >= 2:
                    for i, t1 in enumerate(unique):
                        for t2 in unique[i+1:]:
                            self._edges[t1].append({"target": t2, "type": "agent_shared", "weight": EDGE_WEIGHTS["agent_shared"], "agent_id": agent_id})
                            self._edges[t2].append({"target": t1, "type": "agent_shared", "weight": EDGE_WEIGHTS["agent_shared"], "agent_id": agent_id})
        except Exception as e:
            logger.warning(f"_build_edges_from_agents: {e}")

    def simulate_cascade(self, trigger_id: str, scenario: str = "collapse", severity: float = 1.0, max_hops: int = 4) -> Dict[str, Any]:
        self.ensure_loaded()
        t0 = time.time()
        trigger_nid = self._resolve_node_id(trigger_id)
        if trigger_nid is None:
            return {"error": f"Node not found: {trigger_id}", "trigger_id": trigger_id}
        scenario_meta = SCENARIOS.get(scenario, SCENARIOS["collapse"])
        btc_shock = scenario_meta["btc_shock"]
        visited: Dict[str, float] = {}
        queue: deque = deque()
        queue.append((trigger_nid, severity, 0))
        cascade_chain: List[Dict] = []
        while queue:
            nid, impact, hop = queue.popleft()
            if nid in visited or hop > max_hops or impact < 0.02:
                continue
            visited[nid] = impact
            node = self._nodes.get(nid, {})
            exposure_usd = self._estimate_exposure_usd(node, impact)
            ai_amplifier = 1.0 + (node.get("ai_agent_ratio", 0.0) * 0.5)
            cascade_chain.append({
                "node_id": nid,
                "node_type": node.get("type", "unknown"),
                "symbol": node.get("symbol") or node.get("name", nid),
                "chain": node.get("chain", ""),
                "hop": hop,
                "impact": round(impact, 4),
                "impact_pct": round(impact * 100, 1),
                "risk_level": node.get("risk_level", "UNKNOWN"),
                "structural_weakness": node.get("structural_weakness", 0),
                "crash_prob": round(node.get("crash_prob", 0.0), 3),
                "trust_score": round(node.get("trust_score", 50.0), 1),
                "ai_agent_ratio": round(node.get("ai_agent_ratio", 0.0), 3),
                "ai_controlled_tvl_usd": node.get("ai_controlled_tvl_usd", 0.0),
                "exposure_usd": round(exposure_usd, 0),
                "is_trigger": hop == 0,
            })
            for edge in self._edges.get(nid, []):
                target_nid = edge["target"]
                if target_nid in visited:
                    continue
                propagated_impact = impact * edge["weight"] * HOP_DAMPENING * ai_amplifier
                if btc_shock < 0 and target_nid.startswith("token:"):
                    target_node = self._nodes.get(target_nid, {})
                    btc_beta = self._estimate_btc_beta(target_node)
                    propagated_impact = max(propagated_impact, abs(btc_shock) * btc_beta)
                queue.append((target_nid, propagated_impact, hop + 1))
        cascade_chain.sort(key=lambda x: (-int(x["is_trigger"]), -x["impact"]))
        total_exposure_usd = sum(n["exposure_usd"] for n in cascade_chain)
        elapsed_ms = round((time.time() - t0) * 1000, 1)
        return {
            "trigger": {"node_id": trigger_nid, "symbol": self._nodes.get(trigger_nid, {}).get("symbol", trigger_id), "severity": severity, "scenario": scenario, "scenario_label": scenario_meta["label"]},
            "simulation": {"nodes_affected": len(cascade_chain), "max_hops_reached": max(n["hop"] for n in cascade_chain) if cascade_chain else 0, "total_exposure_usd": round(total_exposure_usd, 0), "structural_collapses_in_path": len([n for n in cascade_chain if n["structural_weakness"] >= 3 and not n["is_trigger"]]), "high_crash_risk_in_path": len([n for n in cascade_chain if n["crash_prob"] > 0.5 and not n["is_trigger"]]), "ai_amplified_nodes": len([n for n in cascade_chain if n["ai_agent_ratio"] > 0.3 and not n["is_trigger"]])},
            "cascade_chain": cascade_chain,
            "alerts": self._generate_cascade_alerts(cascade_chain, total_exposure_usd),
            "computed_at": datetime.utcnow().isoformat() + "Z",
            "elapsed_ms": elapsed_ms,
        }

    def _resolve_node_id(self, trigger_id: str) -> Optional[str]:
        if trigger_id in self._nodes:
            return trigger_id
        for prefix in ("token:", "chain:", "protocol:"):
            candidate = f"{prefix}{trigger_id}"
            if candidate in self._nodes:
                return candidate
        trigger_upper = trigger_id.upper()
        for nid, node in self._nodes.items():
            if node.get("symbol", "").upper() == trigger_upper:
                return nid
            if node.get("name", "").upper() == trigger_upper:
                return nid
            if node.get("token_id", "").upper() == trigger_upper:
                return nid
        return None

    def _estimate_exposure_usd(self, node: Dict, impact: float) -> float:
        ai_tvl = node.get("ai_controlled_tvl_usd", 0.0) or 0.0
        if ai_tvl > 0:
            return ai_tvl * impact
        baseline = 10_000_000
        risk_multiplier = 1.0 + (node.get("crash_prob", 0.0) * 2.0)
        return baseline * impact * risk_multiplier

    def _estimate_btc_beta(self, node: Dict) -> float:
        risk = node.get("risk_level", "UNKNOWN")
        return {"CRITICAL": 1.4, "WARNING": 1.2, "WATCH": 1.0, "SAFE": 0.7}.get(risk, 1.0)

    def _generate_cascade_alerts(self, chain: List[Dict], total_usd: float) -> List[Dict]:
        alerts = []
        collapses = [n for n in chain if n["structural_weakness"] >= 3 and not n["is_trigger"]]
        if collapses:
            alerts.append({"level": "CRITICAL", "type": "structural_collapse_in_path", "message": f"{len(collapses)} Structural Collapse token(s) in cascade path", "tokens": [n["symbol"] for n in collapses[:5]]})
        if total_usd > 50_000_000:
            alerts.append({"level": "HIGH", "type": "large_exposure", "message": f"Cascade affects ~${total_usd/1e6:.1f}M estimated exposure", "exposure_usd": total_usd})
        ai_nodes = [n for n in chain if n["ai_agent_ratio"] > 0.5 and not n["is_trigger"]]
        if ai_nodes:
            alerts.append({"level": "MEDIUM", "type": "ai_amplification_risk", "message": f"{len(ai_nodes)} node(s) with >50% AI agent control", "nodes": [n["symbol"] for n in ai_nodes[:5]]})
        return alerts

    def export_graph_summary(self, max_nodes: int = 200) -> Dict[str, Any]:
        self.ensure_loaded()
        def risk_score(n):
            return n.get("structural_weakness", 0) * 3 + n.get("crash_prob", 0.0) * 2 + n.get("ai_agent_ratio", 0.0)
        top_nodes = sorted([(nid, n) for nid, n in self._nodes.items() if n["type"] == "token"], key=lambda x: risk_score(x[1]), reverse=True)[:max_nodes]
        node_ids = {nid for nid, _ in top_nodes}
        for nid, node in top_nodes:
            chain_nid = f"chain:{node.get('chain', '')}"
            if chain_nid in self._nodes:
                node_ids.add(chain_nid)
        nodes_out = [{"id": nid, "type": self._nodes[nid].get("type", "token"), "label": self._nodes[nid].get("symbol") or self._nodes[nid].get("name", nid), "risk_level": self._nodes[nid].get("risk_level", "UNKNOWN"), "structural_weakness": self._nodes[nid].get("structural_weakness", 0), "crash_prob": round(self._nodes[nid].get("crash_prob", 0.0), 3), "ai_agent_ratio": round(self._nodes[nid].get("ai_agent_ratio", 0.0), 3)} for nid in node_ids]
        seen_edges = set()
        edges_out = []
        for nid in node_ids:
            for edge in self._edges.get(nid, []):
                if edge["target"] in node_ids:
                    key = tuple(sorted([nid, edge["target"]])) + (edge["type"],)
                    if key not in seen_edges:
                        seen_edges.add(key)
                        edges_out.append({"source": nid, "target": edge["target"], "type": edge["type"], "weight": edge["weight"]})
        return {"nodes": nodes_out, "edges": edges_out, "stats": {"total_nodes": len(self._nodes), "total_edges": sum(len(v) for v in self._edges.values()), "exported_nodes": len(nodes_out), "exported_edges": len(edges_out)}, "computed_at": datetime.utcnow().isoformat() + "Z"}

    def get_hotspots(self, top_n: int = 20) -> Dict[str, Any]:
        self.ensure_loaded()
        hotspots = []
        for nid, node in self._nodes.items():
            if node["type"] != "token":
                continue
            degree = len(self._edges.get(nid, []))
            sw = node.get("structural_weakness", 0)
            cp = node.get("crash_prob", 0.0)
            ai = node.get("ai_agent_ratio", 0.0)
            trust = node.get("trust_score", 50.0)
            hotspot_score = sw * 30 + cp * 25 + (1 - trust / 100) * 20 + ai * 15 + min(degree, 20) * 0.5
            if hotspot_score > 10:
                hotspots.append({"node_id": nid, "symbol": node.get("symbol", nid), "chain": node.get("chain", ""), "risk_level": node.get("risk_level", "UNKNOWN"), "structural_weakness": sw, "crash_prob": round(cp, 3), "trust_score": round(trust, 1), "ai_agent_ratio": round(ai, 3), "graph_degree": degree, "hotspot_score": round(hotspot_score, 1)})
        hotspots.sort(key=lambda x: x["hotspot_score"], reverse=True)
        return {"hotspots": hotspots[:top_n], "total_hotspots_found": len(hotspots), "computed_at": datetime.utcnow().isoformat() + "Z"}

    def get_stats(self) -> Dict[str, Any]:
        self.ensure_loaded()
        node_types = defaultdict(int)
        for node in self._nodes.values():
            node_types[node.get("type", "unknown")] += 1
        return {"loaded": self._loaded, "load_time_s": round(self._load_time or 0, 2), "total_nodes": len(self._nodes), "node_types": dict(node_types), "total_edge_entries": sum(len(v) for v in self._edges.values()), "scenarios_available": list(SCENARIOS.keys())}


_engine_instance = None

def get_engine() -> PropagatedRiskEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = PropagatedRiskEngine(DB_PATH)
    return _engine_instance
