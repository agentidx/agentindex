"""Nerq API Protection - Rate limiting, source_url hiding, logging, honeypots"""
import time, hashlib, logging, json, os
from datetime import datetime
from typing import Optional
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("nerq.api.protection")
_rate_store = {}

TIERS = {
    "free": {"requests_per_hour": 60, "requests_per_day": 200, "max_results": 5, "show_source_url": False},
    "basic": {"requests_per_hour": 500, "requests_per_day": 5000, "max_results": 25, "show_source_url": True},
    "pro": {"requests_per_hour": 5000, "requests_per_day": 50000, "max_results": 50, "show_source_url": True},
    "internal": {"requests_per_hour": 999999, "requests_per_day": 999999, "max_results": 100, "show_source_url": True},
}
API_KEYS = {}

def _load_api_keys():
    internal_key = os.getenv("NERQ_INTERNAL_API_KEY", "nerq-internal-2026")
    API_KEYS[hashlib.sha256(internal_key.encode()).hexdigest()] = {"tier": "internal", "owner": "nerq"}
    keys_file = os.path.expanduser("~/agentindex/api_keys.json")
    if os.path.exists(keys_file):
        for k in json.load(open(keys_file)):
            API_KEYS[hashlib.sha256(k["key"].encode()).hexdigest()] = {"tier": k.get("tier","basic"), "owner": k.get("owner","unknown")}

def get_client_tier(request):
    auth = request.headers.get("Authorization", "")
    api_key = auth[7:] if auth.startswith("Bearer ") else request.query_params.get("api_key") or request.headers.get("X-API-Key")
    if api_key:
        kh = hashlib.sha256(api_key.encode()).hexdigest()
        if kh in API_KEYS: return API_KEYS[kh]["tier"], API_KEYS[kh].get("owner")
    return "free", None

def check_rate_limit_tiered(request):
    client_ip = request.client.host if request.client else "unknown"
    tier_name, owner = get_client_tier(request)
    tier = TIERS[tier_name]
    now = time.time()
    key = f"{client_ip}:{tier_name}"
    if key not in _rate_store: _rate_store[key] = []
    _rate_store[key] = [t for t in _rate_store[key] if t > now - 86400]
    hour_count = sum(1 for t in _rate_store[key] if t > now - 3600)
    day_count = len(_rate_store[key])
    if hour_count >= tier["requests_per_hour"]:
        raise HTTPException(status_code=429, detail={"error":"rate_limit_exceeded","tier":tier_name,"limit":tier["requests_per_hour"],"upgrade":"Contact hello@nerq.ai"})
    if day_count >= tier["requests_per_day"]:
        raise HTTPException(status_code=429, detail={"error":"daily_limit_exceeded","tier":tier_name,"limit":tier["requests_per_day"]})
    _rate_store[key].append(now)
    return {"tier": tier_name, "owner": owner, "limits": tier, "hour_count": hour_count+1, "day_count": day_count+1}

_log_buffer = []
def log_api_request(request, tier_info, status, time_ms):
    _log_buffer.append({"ts":datetime.utcnow().isoformat(),"ip_hash":hashlib.sha256((request.client.host or "").encode()).hexdigest()[:16],"path":request.url.path,"tier":tier_info["tier"],"status":status,"time_ms":time_ms,"ua":(request.headers.get("user-agent") or "")[:100]})
    if len(_log_buffer) >= 50:
        os.makedirs(os.path.expanduser("~/agentindex/logs"), exist_ok=True)
        with open(os.path.expanduser(f"~/agentindex/logs/api_{datetime.utcnow().strftime('%Y-%m-%d')}.jsonl"),"a") as f:
            for e in _log_buffer: f.write(json.dumps(e)+"\n")
        _log_buffer.clear()

HONEYPOT_IDS = {"00000000-dead-beef-0000-000000000001","00000000-dead-beef-0000-000000000002","00000000-dead-beef-0000-000000000003"}
def check_honeypot_access(agent_id, request):
    if agent_id in HONEYPOT_IDS:
        logger.warning(f"HONEYPOT: {agent_id} ip={request.client.host}")

class ApiProtectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not request.url.path.startswith("/v1/") or request.url.path in ("/v1/health","/health"):
            return await call_next(request)
        start = time.time()
        try:
            tier_info = check_rate_limit_tiered(request)
            response = await call_next(request)
            ms = int((time.time()-start)*1000)
            log_api_request(request, tier_info, response.status_code, ms)
            response.headers["X-Nerq-Tier"] = tier_info["tier"]
            response.headers["X-Nerq-Rate-Hour"] = f"{tier_info['hour_count']}/{tier_info['limits']['requests_per_hour']}"
            return response
        except HTTPException as e:
            return JSONResponse(status_code=e.status_code, content=e.detail if isinstance(e.detail,dict) else {"error":e.detail})

def setup_api_protection(app):
    _load_api_keys()
    app.add_middleware(ApiProtectionMiddleware)
    logger.info(f"API protection enabled: {len(API_KEYS)} keys, {len(TIERS)} tiers")
