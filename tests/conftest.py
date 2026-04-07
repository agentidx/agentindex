"""Pytest configuration — sets up Python path so tests can import agentindex.*"""
import sys
from pathlib import Path

# Add the repository root to sys.path so "from agentindex.i18n import ..."
# works in tests regardless of where pytest is invoked from.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
