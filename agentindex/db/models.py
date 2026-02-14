"""
AgentIndex Database Models

Core data model for indexing AI agents from across the ecosystem.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    create_engine, Column, String, Float, DateTime, Text, Boolean, Integer,
    Index, func
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, UUID
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import text
import uuid
import os

Base = declarative_base()


class Agent(Base):
    """
    Core agent record. One row per discovered agent.
    """
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Source tracking
    source = Column(String(50), nullable=False, index=True)  # github, npm, pip, moltbook, mcp, huggingface
    source_url = Column(Text, nullable=False, unique=True)    # canonical URL
    source_id = Column(String(255))                           # ID within source (e.g., GitHub repo full_name)

    # Identity
    name = Column(String(500), nullable=False)
    description = Column(Text)
    author = Column(String(255))
    license = Column(String(100))

    # Capabilities (what this agent can do)
    capabilities = Column(JSONB, default=list)
    # Example: ["contract analysis", "risk identification", "compliance check"]

    # Categories and tags
    category = Column(String(100), index=True)
    # Example: "legal", "content", "coding", "research", "data"
    tags = Column(ARRAY(String), default=list)
    # Example: ["contracts", "risk", "compliance", "B2B"]

    # How to invoke this agent
    invocation = Column(JSONB, default=dict)
    # Example: {
    #   "type": "mcp",                          # mcp, api, npm, pip, docker, github
    #   "install": "npm install @legal/review",  # install command if applicable
    #   "endpoint": "https://...",               # API endpoint if applicable
    #   "protocol": "a2a",                       # a2a, mcp, rest, grpc
    #   "agent_card_url": "https://.../.well-known/agent.json"
    # }

    # Pricing
    pricing = Column(JSONB, default=dict)
    # Example: {"model": "free"} or {"model": "per_call", "price": 0.50, "currency": "USD"}

    # Quality scores (0.0 - 1.0)
    quality_score = Column(Float, default=0.0)          # overall AgentRank
    documentation_score = Column(Float, default=0.0)    # how well documented
    activity_score = Column(Float, default=0.0)         # maintenance level
    security_score = Column(Float, default=0.0)         # known vulnerabilities
    popularity_score = Column(Float, default=0.0)       # stars, downloads, usage
    capability_depth_score = Column(Float, default=0.0) # specialization level

    # Source metadata
    stars = Column(Integer, default=0)
    forks = Column(Integer, default=0)
    downloads = Column(Integer, default=0)
    last_source_update = Column(DateTime)               # when the agent itself was last updated
    language = Column(String(50))                        # primary programming language
    frameworks = Column(ARRAY(String), default=list)     # e.g., ["langchain", "crewai"]

    # Protocols supported
    protocols = Column(ARRAY(String), default=list)      # e.g., ["mcp", "a2a", "rest"]

    # Our metadata
    first_indexed = Column(DateTime, default=datetime.utcnow)
    last_crawled = Column(DateTime, default=datetime.utcnow)
    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    crawl_status = Column(String(20), default="indexed")  # indexed, parsed, classified, ranked

    # Raw data from crawling (for reprocessing)
    raw_metadata = Column(JSONB, default=dict)

    # Indexes for fast discovery queries
    __table_args__ = (
        Index("idx_agents_category_quality", "category", "quality_score"),
        Index("idx_agents_capabilities", "capabilities", postgresql_using="gin"),
        Index("idx_agents_tags", "tags", postgresql_using="gin"),
        Index("idx_agents_protocols", "protocols", postgresql_using="gin"),
        Index("idx_agents_quality", "quality_score"),
        Index("idx_agents_source_url", "source_url"),
        Index("idx_agents_crawl_status", "crawl_status"),
        Index("idx_agents_is_active", "is_active"),
    )

    def to_discovery_response(self) -> dict:
        """Minimal response for discovery queries. Never expose everything."""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "category": self.category,
            "quality_score": self.quality_score,
            "invocation": self.invocation,
            "protocols": self.protocols,
            "pricing": self.pricing,
            "is_verified": self.is_verified,
            "source_url": self.source_url,
            "stars": self.stars or 0,
            "author": self.author,
            "source": self.source,
        }

    def to_detail_response(self) -> dict:
        """Detailed response for single agent lookup."""
        return {
            **self.to_discovery_response(),
            "tags": self.tags,
            "author": self.author,
            "source": self.source,
            "source_url": self.source_url,
            "documentation_score": self.documentation_score,
            "activity_score": self.activity_score,
            "popularity_score": self.popularity_score,
            "stars": self.stars,
            "frameworks": self.frameworks,
            "last_source_update": self.last_source_update.isoformat() if self.last_source_update else None,
            "first_indexed": self.first_indexed.isoformat() if self.first_indexed else None,
        }


class DiscoveryLog(Base):
    """
    Log of all discovery requests. Critical for understanding demand.
    No identifying information about who is asking.
    """
    __tablename__ = "discovery_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query = Column(JSONB, nullable=False)          # the discovery request
    results_count = Column(Integer, default=0)      # how many results returned
    top_result_id = Column(UUID(as_uuid=True))     # best match agent ID
    response_time_ms = Column(Integer)              # performance tracking
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("idx_discovery_log_timestamp", "timestamp"),
    )


class CrawlJob(Base):
    """
    Track crawl jobs and their status.
    """
    __tablename__ = "crawl_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(50), nullable=False)
    query = Column(String(500))                     # search query used
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    items_found = Column(Integer, default=0)
    items_new = Column(Integer, default=0)
    items_updated = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_crawl_jobs_status", "status"),
    )


class SystemStatus(Base):
    """
    System health metrics, updated by Vakten.
    """
    __tablename__ = "system_status"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metric = Column(String(100), nullable=False)    # e.g., "total_agents", "api_requests_today"
    value = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_system_status_metric", "metric", "timestamp"),
    )


# Database initialization

def get_engine():
    database_url = os.getenv("DATABASE_URL", "postgresql://localhost/agentindex")
    return create_engine(database_url, pool_size=10, max_overflow=20)


def get_session():
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    session = Session()
    return session

def safe_commit(session):
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise


def init_db():
    """Create all tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)

    # Create full-text search index for discovery
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_agents_fts 
            ON agents 
            USING gin(to_tsvector('english', 
                coalesce(name, '') || ' ' || 
                coalesce(description, '') || ' ' || 
                coalesce(category, '')
            ));
        """))
        conn.commit()

    print("Database initialized successfully.")


if __name__ == "__main__":
    init_db()
