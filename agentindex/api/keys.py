"""
AgentIndex API Key Management

Simple API key system for:
- Rate limiting per key (not just per IP)
- Tracking which agents use our service
- Future monetization (paid tiers)
- Abuse detection per key

Keys are free and self-service. An agent registers once,
gets a key, uses it forever. No humans involved.
"""

import hashlib
import secrets
import logging
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Boolean, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from agentindex.db.models import Base, get_session
import uuid

logger = logging.getLogger("agentindex.apikeys")


class ApiKey(Base):
    """API key for an agent consumer."""
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key_hash = Column(String(64), unique=True, nullable=False, index=True)  # SHA-256 hash
    key_prefix = Column(String(8), nullable=False)  # First 8 chars for identification

    # Who registered
    agent_name = Column(String(500))
    agent_url = Column(String(2000))
    contact = Column(String(500))  # optional email or URL

    # Tier
    tier = Column(String(20), default="free")  # free, verified, premium
    rate_limit_per_hour = Column(Integer, default=100)
    max_results_per_request = Column(Integer, default=10)

    # Usage tracking
    total_requests = Column(Integer, default=0)
    last_request_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Status
    is_active = Column(Boolean, default=True)
    is_flagged = Column(Boolean, default=False)  # suspected abuse
    flag_reason = Column(String(500))

    # Watermark: unique per key, embedded in responses for tracking
    watermark = Column(String(16))

    # Metadata
    extra_metadata = Column(JSONB, default=dict)


def generate_key() -> tuple[str, str]:
    """
    Generate a new API key.
    Returns (full_key, key_hash).
    The full key is shown once, the hash is stored.
    """
    raw = secrets.token_urlsafe(32)
    key = f"agx_{raw}"
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return key, key_hash


def register_key(agent_name: str = None, agent_url: str = None,
                  contact: str = None) -> dict:
    """
    Register a new API key. Returns the key (shown only once).
    """
    session = get_session()

    key, key_hash = generate_key()
    watermark = secrets.token_hex(8)

    api_key = ApiKey(
        key_hash=key_hash,
        key_prefix=key[:12],
        agent_name=agent_name,
        agent_url=agent_url,
        contact=contact,
        watermark=watermark,
    )

    session.add(api_key)
    session.commit()

    logger.info(f"New API key registered: {key[:12]}... for {agent_name or 'anonymous'}")

    return {
        "key": key,
        "prefix": key[:12],
        "tier": "free",
        "rate_limit_per_hour": 100,
        "max_results_per_request": 10,
        "message": "Store this key securely. It will not be shown again.",
    }


def validate_key(key: str) -> dict | None:
    """
    Validate an API key. Returns key info or None if invalid.
    """
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    session = get_session()

    api_key = session.query(ApiKey).filter_by(key_hash=key_hash).first()

    if not api_key:
        return None

    if not api_key.is_active:
        return None

    # Update usage
    api_key.total_requests = (api_key.total_requests or 0) + 1
    api_key.last_request_at = datetime.utcnow()
    session.commit()

    return {
        "id": str(api_key.id),
        "tier": api_key.tier,
        "rate_limit_per_hour": api_key.rate_limit_per_hour,
        "max_results_per_request": api_key.max_results_per_request,
        "watermark": api_key.watermark,
        "is_flagged": api_key.is_flagged,
    }


def flag_key(key_hash: str, reason: str):
    """Flag a key for suspected abuse."""
    session = get_session()
    api_key = session.query(ApiKey).filter_by(key_hash=key_hash).first()
    if api_key:
        api_key.is_flagged = True
        api_key.flag_reason = reason
        session.commit()
        logger.warning(f"API key flagged: {api_key.key_prefix}... — {reason}")


def revoke_key(key_hash: str):
    """Revoke an API key."""
    session = get_session()
    api_key = session.query(ApiKey).filter_by(key_hash=key_hash).first()
    if api_key:
        api_key.is_active = False
        session.commit()
        logger.info(f"API key revoked: {api_key.key_prefix}...")
