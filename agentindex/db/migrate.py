"""
Database migration helper.

Ensures all tables exist including newer ones (api_keys etc).
Run: python -m agentindex.db.migrate
"""

from agentindex.db.models import Base, get_engine
from agentindex.api.keys import ApiKey  # Import to register model


def migrate():
    """Create any missing tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    print("Migration complete — all tables created/verified.")


if __name__ == "__main__":
    migrate()
