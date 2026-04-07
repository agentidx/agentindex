"""Basic tests for the agent."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_tools_import():
    """Tools module should import without errors."""
    import tools
    assert hasattr(tools, "get_tools_for_task")
    assert hasattr(tools, "check_dependency")


def test_config_defaults():
    """Config should have sensible defaults."""
    import config
    assert config.NERQ_MIN_TRUST >= 0
    assert config.NERQ_API_URL.startswith("http")


def test_min_trust_range():
    """MIN_TRUST should be between 0 and 100."""
    from tools import MIN_TRUST
    assert 0 <= MIN_TRUST <= 100
