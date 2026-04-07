"""Basic tests."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

def test_tools_import():
    import tools
    assert hasattr(tools, "get_tools_for_task")

def test_min_trust():
    from tools import MIN_TRUST
    assert 0 <= MIN_TRUST <= 100
