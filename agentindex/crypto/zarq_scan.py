"""
ZARQ Token Scanner — /scan page + POST /v1/scan endpoint
=========================================================
Instant safety assessment for any contract address.
Uses Etherscan API v2 (supports all EVM chains) and Solana RPC.
"""

import json
import logging
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logger = logging.getLogger("zarq.scan")

# ── Config ──────────────────────────────────────────────────────────

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
RISK_DB = str(Path(__file__).parent / "crypto_trust.db")
SEO_DB = str(Path(__file__).parent.parent / "data" / "crypto_trust.db")

# Etherscan v2 API — single endpoint, chain ID selects network
ETHERSCAN_V2_URL = "https://api.etherscan.io/v2/api"

CHAIN_IDS = {
    "ethereum": "1",
    "bsc": "56",
    "polygon": "137",
    "arbitrum": "42161",
    "base": "8453",
    "optimism": "10",
    "avalanche": "43114",
}

SOLANA_RPC = "https://api.mainnet-beta.solana.com"

# ── Models ──────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    contract_address: str
    chain: str = "ethereum"


# ── Etherscan helpers ───────────────────────────────────────────────

def _etherscan_call(chain_id: str, module: str, action: str, address: str, **extra) -> dict | None:
    """Single Etherscan v2 API call."""
    if not ETHERSCAN_API_KEY:
        return None
    params = {
        "chainid": chain_id,
        "module": module,
        "action": action,
        "address": address,
        "apikey": ETHERSCAN_API_KEY,
        **extra,
    }
    try:
        resp = requests.get(ETHERSCAN_V2_URL, params=params, timeout=10)
        data = resp.json()
        if data.get("status") == "1" or (isinstance(data.get("result"), (list, dict, str)) and data.get("message") != "NOTOK"):
            return data.get("result")
    except Exception as e:
        logger.warning(f"Etherscan call failed: {e}")
    return None


def _scan_evm(address: str, chain: str) -> dict:
    """Scan an EVM contract address via Etherscan v2. All 4 API calls run in parallel."""
    chain_id = CHAIN_IDS.get(chain, "1")
    result = {
        "chain": chain,
        "address": address,
        "source": "etherscan",
    }

    # Fire all 4 Etherscan calls in parallel
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_source = pool.submit(_etherscan_call, chain_id, "contract", "getsourcecode", address)
        f_txcount = pool.submit(_etherscan_call, chain_id, "proxy", "eth_getTransactionCount", address)
        f_creation = pool.submit(_etherscan_call, chain_id, "contract", "getcontractcreation", address)
        f_txlist = pool.submit(
            _etherscan_call, chain_id, "account", "txlist", address,
            startblock="0", endblock="99999999", page="1", offset="5", sort="asc",
        )

    # 1. Source code / verification
    source = f_source.result()
    if source and isinstance(source, list) and len(source) > 0:
        sc = source[0]
        result["contract_name"] = sc.get("ContractName") or None
        result["is_verified"] = bool(sc.get("SourceCode"))
        result["compiler"] = sc.get("CompilerVersion") or None
        result["license"] = sc.get("LicenseType") or None
        result["is_proxy"] = bool(sc.get("Proxy") == "1" or sc.get("Implementation"))
        result["implementation"] = sc.get("Implementation") or None
        abi_str = sc.get("ABI", "")
        result["has_mint_function"] = "mint" in abi_str.lower()
        result["has_pause_function"] = "pause" in abi_str.lower()
        result["has_blacklist_function"] = any(w in abi_str.lower() for w in ["blacklist", "blocklist", "deny"])
    else:
        result["is_verified"] = False
        result["contract_name"] = None

    # 2. Transaction count
    tx_count = f_txcount.result()
    if tx_count and isinstance(tx_count, str):
        try:
            result["transaction_count"] = int(tx_count, 16)
        except (ValueError, TypeError):
            result["transaction_count"] = None
    else:
        result["transaction_count"] = None

    # 3. Contract creation info
    creation = f_creation.result()
    if creation and isinstance(creation, list) and len(creation) > 0:
        cr = creation[0]
        result["creator"] = cr.get("contractCreator")
        result["creation_tx"] = cr.get("txHash")
    else:
        result["creator"] = None
        result["creation_tx"] = None

    # 4. First transactions — age and activity
    txs = f_txlist.result()
    if txs and isinstance(txs, list) and len(txs) > 0:
        first_tx = txs[0]
        ts = first_tx.get("timeStamp")
        if ts:
            try:
                creation_time = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                result["creation_date"] = creation_time.isoformat()
                age_days = (datetime.now(timezone.utc) - creation_time).days
                result["age_days"] = age_days
            except (ValueError, TypeError, OSError):
                result["age_days"] = None
    else:
        result["age_days"] = None

    return result


def _scan_solana(address: str) -> dict:
    """Scan a Solana token/program address via public RPC."""
    result = {
        "chain": "solana",
        "address": address,
        "source": "solana_rpc",
    }

    try:
        # Get account info
        resp = requests.post(SOLANA_RPC, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getAccountInfo",
            "params": [address, {"encoding": "jsonParsed"}]
        }, timeout=10)
        data = resp.json().get("result", {})
        value = data.get("value")

        if value:
            result["exists"] = True
            result["lamports"] = value.get("lamports", 0)
            result["owner"] = value.get("owner")
            result["executable"] = value.get("executable", False)
            parsed = value.get("data", {})
            if isinstance(parsed, dict) and "parsed" in parsed:
                info = parsed["parsed"].get("info", {})
                result["token_type"] = parsed["parsed"].get("type")
                result["mint_authority"] = info.get("mintAuthority")
                result["freeze_authority"] = info.get("freezeAuthority")
                result["supply"] = info.get("supply")
                result["decimals"] = info.get("decimals")
                # Risk: mint authority still active = can inflate supply
                result["can_mint"] = bool(info.get("mintAuthority"))
                result["can_freeze"] = bool(info.get("freezeAuthority"))
        else:
            result["exists"] = False

    except Exception as e:
        logger.warning(f"Solana RPC call failed: {e}")
        result["error"] = str(e)

    return result


# ── Risk assessment ─────────────────────────────────────────────────

def _assess_risk_evm(scan_data: dict) -> dict:
    """Compute risk verdict from Etherscan scan data."""
    flags = []
    score = 50  # Start neutral

    # Verification
    if not scan_data.get("is_verified"):
        flags.append({"signal": "Unverified contract", "severity": "high",
                       "detail": "Source code is not verified on the block explorer. Cannot audit logic."})
        score -= 25
    else:
        score += 15

    # Age
    age = scan_data.get("age_days")
    if age is not None:
        if age < 7:
            flags.append({"signal": "Very new contract", "severity": "high",
                           "detail": f"Created {age} days ago. New tokens are significantly riskier."})
            score -= 20
        elif age < 30:
            flags.append({"signal": "Young contract", "severity": "medium",
                           "detail": f"Created {age} days ago. Track record is short."})
            score -= 10
        elif age > 365:
            score += 10

    # Proxy
    if scan_data.get("is_proxy"):
        flags.append({"signal": "Upgradeable proxy", "severity": "medium",
                       "detail": "Contract uses a proxy pattern. Owner can change logic."})
        score -= 5

    # Dangerous functions
    if scan_data.get("has_mint_function"):
        flags.append({"signal": "Has mint function", "severity": "medium",
                       "detail": "Contract has a mint function. Token supply may increase."})
        score -= 5

    if scan_data.get("has_blacklist_function"):
        flags.append({"signal": "Has blacklist function", "severity": "medium",
                       "detail": "Contract can blacklist addresses from transferring."})
        score -= 5

    # Transaction count
    tx_count = scan_data.get("transaction_count")
    if tx_count is not None:
        if tx_count < 10:
            flags.append({"signal": "Very low activity", "severity": "medium",
                           "detail": f"Only {tx_count} transactions. May be inactive or abandoned."})
            score -= 10

    # Clamp
    score = max(0, min(100, score))

    # Verdict
    if score >= 60:
        verdict = "LOW_RISK"
    elif score >= 40:
        verdict = "MEDIUM_RISK"
    elif score >= 20:
        verdict = "HIGH_RISK"
    else:
        verdict = "CRITICAL_RISK"

    if not flags and not scan_data.get("is_verified") and age is None:
        verdict = "INSUFFICIENT_DATA"

    return {
        "verdict": verdict,
        "risk_score": score,
        "risk_flags": flags,
        "flag_count": len(flags),
    }


def _assess_risk_solana(scan_data: dict) -> dict:
    """Compute risk verdict from Solana scan data."""
    flags = []
    score = 50

    if not scan_data.get("exists"):
        return {"verdict": "INSUFFICIENT_DATA", "risk_score": 0, "risk_flags": [
            {"signal": "Account not found", "severity": "high", "detail": "This address does not exist on Solana."}
        ], "flag_count": 1}

    if scan_data.get("can_mint"):
        flags.append({"signal": "Mint authority active", "severity": "high",
                       "detail": "Token supply can be increased by the mint authority. Risk of inflation."})
        score -= 20

    if scan_data.get("can_freeze"):
        flags.append({"signal": "Freeze authority active", "severity": "medium",
                       "detail": "Token accounts can be frozen by the authority."})
        score -= 10

    score = max(0, min(100, score))

    if score >= 60:
        verdict = "LOW_RISK"
    elif score >= 40:
        verdict = "MEDIUM_RISK"
    else:
        verdict = "HIGH_RISK"

    return {
        "verdict": verdict,
        "risk_score": score,
        "risk_flags": flags,
        "flag_count": len(flags),
    }


# ── Database lookup ─────────────────────────────────────────────────

def _lookup_in_db(address: str, chain: str) -> dict | None:
    """Check if this contract address matches a token in our database."""
    # Check SEO DB for contract_address match
    try:
        conn = sqlite3.connect(SEO_DB)
        conn.row_factory = sqlite3.Row
        # Try exact address match (case-insensitive)
        row = conn.execute(
            "SELECT * FROM crypto_tokens WHERE LOWER(contract_address) = LOWER(?) LIMIT 1",
            (address,)
        ).fetchone()

        if not row:
            # Try platforms JSON field
            for r in conn.execute("SELECT * FROM crypto_tokens WHERE platforms IS NOT NULL"):
                platforms = r["platforms"]
                if platforms and address.lower() in platforms.lower():
                    row = r
                    break

        conn.close()

        if row:
            row = dict(row)
            # Also get vitality score
            try:
                rconn = sqlite3.connect(RISK_DB)
                rconn.row_factory = sqlite3.Row
                vrow = rconn.execute(
                    "SELECT * FROM vitality_scores WHERE token_id = ?",
                    (row["id"],)
                ).fetchone()
                rconn.close()
                if vrow:
                    row["vitality_score"] = vrow["vitality_score"]
                    row["vitality_grade"] = vrow["vitality_grade"]
                    row["stress_resilience"] = vrow["stress_resilience"]
            except Exception:
                pass

            return row
    except Exception as e:
        logger.warning(f"DB lookup failed: {e}")

    return None


# ── API Router ──────────────────────────────────────────────────────

router_scan = APIRouter()


@router_scan.post("/v1/scan")
def scan_contract(req: ScanRequest):
    """Scan a contract address for safety."""
    t0 = time.time()
    address = req.contract_address.strip()
    chain = req.chain.lower().strip()

    if not address:
        return {"error": "contract_address is required"}

    # Validate address format
    if chain == "solana":
        if len(address) < 32 or len(address) > 50:
            return {"error": "Invalid Solana address format"}
    else:
        if not address.startswith("0x") or len(address) != 42:
            return {"error": f"Invalid EVM address format. Expected 0x... (42 chars), got {len(address)} chars."}

    response = {
        "contract_address": address,
        "chain": chain,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }

    # Check if in our database
    db_match = _lookup_in_db(address, chain)
    if db_match:
        response["in_database"] = True
        response["token"] = {
            "id": db_match.get("id"),
            "name": db_match.get("name"),
            "symbol": db_match.get("symbol"),
            "trust_score": db_match.get("trust_score"),
            "trust_grade": db_match.get("trust_grade"),
            "market_cap_rank": db_match.get("market_cap_rank"),
            "vitality_score": db_match.get("vitality_score"),
            "vitality_grade": db_match.get("vitality_grade"),
            "token_page": f"https://zarq.ai/token/{db_match.get('id')}",
        }
        response["verdict"] = "RATED"
        response["detail"] = f"This token is in ZARQ's database with a Trust Score of {db_match.get('trust_score', 0):.1f}/100."
    else:
        response["in_database"] = False

        # On-chain scan
        if chain == "solana":
            scan_data = _scan_solana(address)
            risk = _assess_risk_solana(scan_data)
        elif chain in CHAIN_IDS:
            scan_data = _scan_evm(address, chain)
            risk = _assess_risk_evm(scan_data)
        else:
            return {"error": f"Unsupported chain: {chain}. Supported: {', '.join(list(CHAIN_IDS.keys()) + ['solana'])}"}

        response["on_chain"] = scan_data
        response["verdict"] = risk["verdict"]
        response["risk_score"] = risk["risk_score"]
        response["risk_flags"] = risk["risk_flags"]
        response["flag_count"] = risk["flag_count"]

    response["response_time_ms"] = round((time.time() - t0) * 1000)
    return response


# ── Scan Page ───────────────────────────────────────────────────────

def mount_scan_page(app):
    """Mount the /scan page on the ZARQ app."""

    @app.get("/scan", response_class=HTMLResponse)
    def scan_page(request: Request):
        host = request.headers.get("host", "")
        if "zarq.ai" not in host:
            return HTMLResponse(status_code=404, content="<h1>Not found</h1>")
        return HTMLResponse(content=_render_scan_page())


def _render_scan_page() -> str:
    title = "Is This Crypto Token Safe? Free Instant Safety Scanner — ZARQ"
    desc = "Paste any contract address to check if a token is safe. Instant risk assessment for Ethereum, Solana, BSC, and more. Free crypto safety scanner."
    url = "https://zarq.ai/scan"

    faq_items = [
        ("How to check if a token is safe?",
         "Paste the token's contract address into ZARQ's scanner. We check verification status, "
         "contract age, transaction activity, dangerous functions (mint, blacklist), and match "
         "against our database of 15,098 rated tokens. You get an instant verdict: Low Risk, "
         "Medium Risk, High Risk, or Critical Risk."),
        ("What is a rug pull?",
         "A rug pull is a crypto scam where developers abandon a project and take investors' "
         "funds. Warning signs include unverified contracts, very new tokens, active mint authority "
         "(can inflate supply), and blacklist functions (can freeze your tokens). ZARQ's scanner "
         "checks for all of these."),
        ("How to scan a smart contract?",
         "Copy the contract address from a block explorer like Etherscan or Solscan. Paste it "
         "into ZARQ's scanner, select the chain (Ethereum, BSC, Polygon, etc.), and click Scan. "
         "Results appear in under 3 seconds."),
    ]

    faq_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq_items
        ]
    })

    web_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "description": desc,
        "url": url,
        "provider": {"@type": "Organization", "name": "ZARQ", "url": "https://zarq.ai"},
    })

    faq_html = ""
    for q, a in faq_items:
        q_esc = q.replace("&", "&amp;").replace("<", "&lt;")
        a_esc = a.replace("&", "&amp;").replace("<", "&lt;")
        faq_html += f'<div class="faq-item"><h3>{q_esc}</h3><p>{a_esc}</p></div>\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:type" content="website">
<meta name="robots" content="index, follow">
<script type="application/ld+json">{web_schema}</script>
<script type="application/ld+json">{faq_schema}</script>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --white: #fafaf9; --black: #0a0a0a;
  --gray-100: #f5f5f4; --gray-200: #e7e5e4; --gray-400: #a8a29e;
  --gray-500: #78716c; --gray-600: #57534e; --gray-700: #44403c;
  --gray-800: #292524; --gray-900: #1c1917;
  --warm: #c2956b; --warm-light: rgba(194,149,107,0.08);
  --green: #16a34a; --red: #dc2626; --yellow: #d97706;
  --serif: 'DM Serif Display', serif;
  --sans: 'DM Sans', sans-serif;
  --mono: 'JetBrains Mono', monospace;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--white); color: var(--black); font-family: var(--sans); min-height: 100vh; }}
nav {{ padding: 16px 24px; border-bottom: 1px solid var(--gray-200); display: flex; align-items: center; gap: 16px; }}
.nav-mark {{ font-family: var(--mono); font-weight: 500; font-size: 15px; letter-spacing: 0.15em; text-transform: uppercase; color: var(--black); text-decoration: none; }}
.nav-links {{ display: flex; gap: 24px; align-items: center; margin-left: auto; }}
.nav-links a {{ font-family: var(--mono); font-size: 12px; letter-spacing: 0.05em; color: var(--gray-500); text-decoration: none; }}
.nav-links a:hover {{ color: var(--black); }}
.nav-links a.active {{ color: var(--warm); font-weight: 600; }}
.nav-api {{ font-size: 11px; color: var(--warm); border: 1px solid var(--warm); padding: 4px 12px; }}
.nav-api:hover {{ background: var(--warm); color: var(--white); }}
.container {{ max-width: 780px; margin: 0 auto; padding: 48px 24px; }}
h1 {{ font-family: var(--serif); font-size: clamp(26px, 4vw, 40px); color: var(--black); margin-bottom: 12px; line-height: 1.2; }}
.subtitle {{ color: var(--gray-500); font-size: 15px; margin-bottom: 32px; line-height: 1.6; }}
.scan-box {{ background: var(--gray-100); border: 2px solid var(--gray-200); border-radius: 12px; padding: 32px; margin-bottom: 40px; }}
.scan-row {{ display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; }}
.input-group {{ flex: 1; min-width: 260px; }}
.input-group label {{ display: block; font-family: var(--mono); font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--gray-500); margin-bottom: 6px; }}
.input-group input, .input-group select {{
  width: 100%; padding: 12px 16px; border: 1px solid var(--gray-200); border-radius: 8px;
  font-family: var(--mono); font-size: 14px; background: var(--white); color: var(--black);
  outline: none;
}}
.input-group input:focus, .input-group select:focus {{ border-color: var(--warm); }}
.input-group input::placeholder {{ color: var(--gray-400); }}
.chain-select {{ min-width: 140px; flex: 0; }}
.scan-btn {{
  padding: 12px 32px; background: var(--warm); color: var(--white); border: none; border-radius: 8px;
  font-family: var(--mono); font-size: 14px; font-weight: 600; letter-spacing: 0.05em;
  cursor: pointer; white-space: nowrap;
}}
.scan-btn:hover {{ background: #b38460; }}
.scan-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
#results {{ display: none; margin-top: 24px; }}
.result-card {{ background: var(--white); border: 2px solid var(--gray-200); border-radius: 12px; padding: 24px; }}
.verdict {{ font-family: var(--serif); font-size: 28px; margin-bottom: 8px; }}
.verdict.low {{ color: var(--green); }}
.verdict.medium {{ color: var(--yellow); }}
.verdict.high {{ color: var(--red); }}
.verdict.critical {{ color: var(--red); font-weight: 700; }}
.verdict.rated {{ color: var(--warm); }}
.verdict.unknown {{ color: var(--gray-500); }}
.result-meta {{ font-family: var(--mono); font-size: 12px; color: var(--gray-500); margin-bottom: 16px; }}
.flag {{ display: flex; gap: 12px; padding: 12px; border-radius: 8px; margin-bottom: 8px; font-size: 13px; }}
.flag.high {{ background: rgba(220,38,38,0.08); border-left: 3px solid var(--red); }}
.flag.medium {{ background: rgba(217,119,6,0.08); border-left: 3px solid var(--yellow); }}
.flag .signal {{ font-weight: 600; color: var(--black); }}
.flag .detail {{ color: var(--gray-600); }}
.token-match {{ background: var(--warm-light); border: 1px solid var(--warm); border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
.token-match a {{ color: var(--warm); font-weight: 600; }}
.score-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin: 16px 0; }}
.score-cell {{ text-align: center; padding: 12px; background: var(--gray-100); border-radius: 8px; }}
.score-cell .val {{ font-family: var(--mono); font-size: 24px; font-weight: 700; }}
.score-cell .lbl {{ font-family: var(--mono); font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--gray-500); margin-top: 4px; }}
.spinner {{ display: none; text-align: center; padding: 40px; }}
.spinner.active {{ display: block; }}
.spinner-ring {{
  display: inline-block; width: 40px; height: 40px;
  border: 3px solid var(--gray-200); border-top-color: var(--warm);
  border-radius: 50%; animation: spin 0.8s linear infinite;
}}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
.section-title {{ font-family: var(--serif); font-size: 22px; color: var(--black); margin: 40px 0 16px; }}
.edu-content {{ font-size: 14px; color: var(--gray-600); line-height: 1.8; }}
.edu-content strong {{ color: var(--black); }}
.faq {{ margin: 40px 0; }}
.faq-item {{ border-bottom: 1px solid var(--gray-200); padding: 16px 0; }}
.faq-item h3 {{ font-size: 15px; font-weight: 600; color: var(--black); margin-bottom: 6px; }}
.faq-item p {{ font-size: 13px; color: var(--gray-500); line-height: 1.6; }}
footer {{ border-top: 1px solid var(--gray-200); padding: 24px; text-align: center; font-size: 12px; color: var(--gray-500); font-family: var(--mono); }}
@media (max-width: 640px) {{
  .scan-row {{ flex-direction: column; }}
  .chain-select {{ min-width: 100%; }}
}}
</style>
</head>
<body>
<!-- AI-Citable Summary: ZARQ's free token scanner lets anyone check the safety of any cryptocurrency
by pasting its contract address. For tokens in our database (15,098 rated), you get full Trust Score
and Vitality Score. For new tokens, you get an instant risk assessment based on on-chain data
including verification status, contract age, dangerous functions, and transaction activity.
Supports Ethereum, BSC, Polygon, Arbitrum, Base, Optimism, Avalanche, and Solana.
Source: ZARQ (zarq.ai) — independent crypto risk intelligence. -->
<nav>
  <a href="/" class="nav-mark">zarq</a>
  <div class="nav-links">
    <a href="/scan" class="active">Scan</a>
    <a href="/crypto">Ratings</a>
    <a href="/tokens">Tokens</a>
    <a href="/crash-watch">Crash Watch</a>
    <a href="/vitality">Vitality</a>
    <a href="/compare">Compare</a>
    <a href="/docs" class="nav-api">API</a>
  </div>
</nav>
<div class="container">
  <h1>Instant Crypto Safety Check</h1>
  <p class="subtitle">Paste any contract address to check if a token is safe. Instant risk assessment
  powered by on-chain data and ZARQ's database of 15,098 rated tokens.</p>

  <div class="scan-box">
    <div class="scan-row">
      <div class="input-group">
        <label>Contract Address</label>
        <input type="text" id="address" placeholder="0x... or Solana mint address" autocomplete="off" spellcheck="false">
      </div>
      <div class="input-group chain-select">
        <label>Chain</label>
        <select id="chain">
          <option value="ethereum">Ethereum</option>
          <option value="bsc">BSC</option>
          <option value="polygon">Polygon</option>
          <option value="arbitrum">Arbitrum</option>
          <option value="base">Base</option>
          <option value="optimism">Optimism</option>
          <option value="avalanche">Avalanche</option>
          <option value="solana">Solana</option>
        </select>
      </div>
      <button class="scan-btn" id="scanBtn" onclick="doScan()">Scan</button>
    </div>

    <div class="spinner" id="spinner">
      <div class="spinner-ring"></div>
      <p style="margin-top:12px;font-family:var(--mono);font-size:12px;color:var(--gray-500)">
        Scanning on-chain data...</p>
    </div>

    <div id="results"></div>
  </div>

  <h2 class="section-title">What We Check</h2>
  <div class="edu-content">
    <p><strong>For EVM chains</strong> (Ethereum, BSC, Polygon, Arbitrum, Base, Optimism, Avalanche):</p>
    <ul style="margin:8px 0 16px 20px">
      <li><strong>Contract verification</strong> — Is the source code verified? Unverified = can't audit the logic.</li>
      <li><strong>Contract age</strong> — Tokens less than 7 days old are significantly riskier.</li>
      <li><strong>Dangerous functions</strong> — Does the contract have mint, pause, or blacklist capabilities?</li>
      <li><strong>Proxy pattern</strong> — Can the contract be upgraded? Owner could change rules.</li>
      <li><strong>Transaction activity</strong> — Very low activity may indicate abandonment.</li>
    </ul>
    <p><strong>For Solana:</strong></p>
    <ul style="margin:8px 0 16px 20px">
      <li><strong>Mint authority</strong> — Can more tokens be created? Active mint authority = inflation risk.</li>
      <li><strong>Freeze authority</strong> — Can your tokens be frozen? Active freeze authority = centralization risk.</li>
      <li><strong>Account existence</strong> — Does the address actually exist on Solana?</li>
    </ul>
    <p>For tokens already in our database (15,098), you also get the full
    <a href="/methodology" style="color:var(--warm)">Trust Score</a>,
    <a href="/vitality" style="color:var(--warm)">Vitality Score</a>, and crash probability.</p>
    <p style="margin-top:8px">
      <a href="/learn/how-to-check-if-crypto-is-safe" style="color:var(--warm);font-weight:600">
        Read our full guide: 7 risk signals to check before buying any token &rarr;</a>
    </p>
  </div>

  <div class="faq">
    <h2 class="section-title">Frequently Asked Questions</h2>
    {faq_html}
  </div>

  <p style="font-size:12px;color:var(--gray-500);font-family:var(--mono);margin-bottom:40px">
    Not investment advice. On-chain data from Etherscan and Solana RPC. Trust Scores from ZARQ.
    <a href="/methodology" style="color:var(--warm)">Methodology &rarr;</a>
  </p>
</div>
<footer>ZARQ — Independent Crypto Risk Intelligence &nbsp;&middot;&nbsp; zarq.ai</footer>

<script>
function doScan() {{
  const addr = document.getElementById('address').value.trim();
  const chain = document.getElementById('chain').value;
  const btn = document.getElementById('scanBtn');
  const spinner = document.getElementById('spinner');
  const results = document.getElementById('results');

  if (!addr) {{ alert('Please enter a contract address'); return; }}

  btn.disabled = true;
  btn.textContent = 'Scanning...';
  spinner.className = 'spinner active';
  results.style.display = 'none';

  fetch('/v1/scan', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{contract_address: addr, chain: chain}})
  }})
  .then(r => r.json())
  .then(data => {{
    spinner.className = 'spinner';
    btn.disabled = false;
    btn.textContent = 'Scan';
    results.style.display = 'block';
    results.innerHTML = renderResults(data);
  }})
  .catch(err => {{
    spinner.className = 'spinner';
    btn.disabled = false;
    btn.textContent = 'Scan';
    results.style.display = 'block';
    results.innerHTML = '<div class="result-card"><p style="color:var(--red)">Error: ' + err.message + '</p></div>';
  }});
}}

// Allow Enter key to trigger scan
document.getElementById('address').addEventListener('keydown', function(e) {{
  if (e.key === 'Enter') doScan();
}});

function verdictClass(v) {{
  if (!v) return 'unknown';
  if (v === 'RATED') return 'rated';
  if (v === 'LOW_RISK') return 'low';
  if (v === 'MEDIUM_RISK') return 'medium';
  if (v === 'HIGH_RISK' || v === 'CRITICAL_RISK') return 'high';
  return 'unknown';
}}

function verdictLabel(v) {{
  const map = {{
    'RATED': 'In ZARQ Database',
    'LOW_RISK': 'Low Risk',
    'MEDIUM_RISK': 'Medium Risk',
    'HIGH_RISK': 'High Risk',
    'CRITICAL_RISK': 'Critical Risk',
    'INSUFFICIENT_DATA': 'Insufficient Data'
  }};
  return map[v] || v;
}}

function gradeColor(g) {{
  if (!g) return '#78716c';
  const c = g[0].toUpperCase();
  return {{'A':'#16a34a','B':'#65a30d','C':'#d97706','D':'#ea580c','S':'#c2956b','F':'#dc2626'}}[c] || '#78716c';
}}

function renderResults(data) {{
  if (data.error) {{
    return '<div class="result-card"><p style="color:var(--red);font-weight:600">' + data.error + '</p></div>';
  }}

  let html = '<div class="result-card">';
  html += '<div class="verdict ' + verdictClass(data.verdict) + '">' + verdictLabel(data.verdict) + '</div>';
  html += '<div class="result-meta">' + data.chain.toUpperCase() + ' &middot; ' + data.contract_address.substring(0,10) + '...' + data.contract_address.slice(-6) + ' &middot; ' + data.response_time_ms + 'ms</div>';

  // If in database, show full scores
  if (data.in_database && data.token) {{
    const t = data.token;
    html += '<div class="token-match">';
    html += '<strong>' + (t.name || '') + ' (' + (t.symbol || '').toUpperCase() + ')</strong>';
    html += ' — This token is rated by ZARQ. ';
    html += '<a href="' + t.token_page + '">View full report &rarr;</a>';
    html += '</div>';
    html += '<div class="score-grid">';
    if (t.trust_score != null) {{
      html += '<div class="score-cell"><div class="val" style="color:' + gradeColor(t.trust_grade) + '">' + t.trust_score.toFixed(1) + '</div><div class="lbl">Trust Score</div></div>';
      html += '<div class="score-cell"><div class="val" style="color:' + gradeColor(t.trust_grade) + '">' + (t.trust_grade || '?') + '</div><div class="lbl">Grade</div></div>';
    }}
    if (t.vitality_score != null) {{
      html += '<div class="score-cell"><div class="val" style="color:' + gradeColor(t.vitality_grade) + '">' + t.vitality_score.toFixed(1) + '</div><div class="lbl">Vitality</div></div>';
    }}
    if (t.market_cap_rank != null) {{
      html += '<div class="score-cell"><div class="val">#' + t.market_cap_rank + '</div><div class="lbl">Rank</div></div>';
    }}
    html += '</div>';
  }}

  // Show risk flags
  if (data.risk_flags && data.risk_flags.length > 0) {{
    html += '<div style="margin-top:16px">';
    data.risk_flags.forEach(function(f) {{
      html += '<div class="flag ' + f.severity + '">';
      html += '<div><div class="signal">' + f.signal + '</div><div class="detail">' + f.detail + '</div></div>';
      html += '</div>';
    }});
    html += '</div>';
  }}

  // Show on-chain data summary for non-DB tokens
  if (!data.in_database && data.on_chain) {{
    const oc = data.on_chain;
    html += '<div style="margin-top:16px;padding-top:16px;border-top:1px solid var(--gray-200)">';
    html += '<div style="font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:var(--gray-500);margin-bottom:8px">On-Chain Data</div>';
    const items = [];
    if (oc.contract_name) items.push(['Contract', oc.contract_name]);
    if (oc.is_verified !== undefined) items.push(['Verified', oc.is_verified ? 'Yes' : 'No']);
    if (oc.age_days !== undefined && oc.age_days !== null) items.push(['Age', oc.age_days + ' days']);
    if (oc.creator) items.push(['Creator', oc.creator.substring(0,10) + '...']);
    if (oc.is_proxy) items.push(['Proxy', 'Yes (upgradeable)']);
    if (oc.compiler) items.push(['Compiler', oc.compiler.substring(0,20)]);
    // Solana specific
    if (oc.can_mint !== undefined) items.push(['Mint Authority', oc.can_mint ? 'Active' : 'Revoked']);
    if (oc.can_freeze !== undefined) items.push(['Freeze Authority', oc.can_freeze ? 'Active' : 'Revoked']);
    if (oc.supply) items.push(['Supply', parseInt(oc.supply).toLocaleString()]);
    items.forEach(function(pair) {{
      html += '<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:13px;border-bottom:1px solid var(--gray-100)"><span style="color:var(--gray-500)">' + pair[0] + '</span><span>' + pair[1] + '</span></div>';
    }});
    html += '</div>';
  }}

  // Risk score bar for non-DB
  if (data.risk_score !== undefined) {{
    const color = data.risk_score >= 60 ? 'var(--green)' : data.risk_score >= 40 ? 'var(--yellow)' : 'var(--red)';
    html += '<div style="margin-top:16px"><div style="font-family:var(--mono);font-size:11px;color:var(--gray-500)">Risk Score: ' + data.risk_score + '/100</div>';
    html += '<div style="background:var(--gray-200);border-radius:4px;height:8px;margin-top:4px"><div style="background:' + color + ';height:8px;border-radius:4px;width:' + data.risk_score + '%"></div></div></div>';
  }}

  html += '</div>';
  return html;
}}
</script>
</body>
</html>"""
