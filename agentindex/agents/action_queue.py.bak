"""
Action Queue for Missionary 2.0

Manages pending actions with approval workflow:
- AUTO: executed immediately
- APPROVAL: shown in dashboard, waits for approve/reject
- NOTIFY: shown in dashboard, no action needed

Actions are stored in ~/agentindex/action_queue.json
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger("agentindex.action_queue")

QUEUE_PATH = os.path.expanduser("~/agentindex/action_queue.json")
HISTORY_PATH = os.path.expanduser("~/agentindex/action_history.json")


class ActionLevel:
    AUTO = "auto"
    APPROVAL = "approval"
    NOTIFY = "notify"


# Define which action types map to which level
ACTION_LEVELS = {
    # Auto-execute
    "update_agent_md": ActionLevel.AUTO,
    "add_search_term": ActionLevel.AUTO,
    "check_endpoint": ActionLevel.AUTO,

    # Needs approval
    "submit_pr": ActionLevel.APPROVAL,
    "register_registry": ActionLevel.APPROVAL,
    "add_awesome_list": ActionLevel.APPROVAL,
    "add_spider_source": ActionLevel.APPROVAL,

    # Notify only
    "new_competitor": ActionLevel.NOTIFY,
    "endpoint_down": ActionLevel.NOTIFY,
    "pr_status_update": ActionLevel.NOTIFY,

    # Spionen (Competitor Intelligence)
    "spy_new_competitor": ActionLevel.NOTIFY,
    "spy_implement_feature": ActionLevel.APPROVAL,
    "spy_improve_visibility": ActionLevel.NOTIFY,
    "spy_competitor_active": ActionLevel.NOTIFY,
    "spy_daily_summary": ActionLevel.NOTIFY,
    "spy_feature_done": ActionLevel.NOTIFY,
    "spy_feature_reminder": ActionLevel.NOTIFY,
    "spy_a2a_outreach": ActionLevel.NOTIFY,
}


def load_queue() -> list:
    if os.path.exists(QUEUE_PATH):
        with open(QUEUE_PATH) as f:
            return json.load(f)
    return []


def save_queue(queue: list):
    with open(QUEUE_PATH, "w") as f:
        json.dump(queue, f, indent=2, default=str)


def load_history() -> list:
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH) as f:
            return json.load(f)
    return []


def save_history(history: list):
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2, default=str)


def add_action(action_type: str, title: str, details: dict = None) -> dict:
    """Add an action to the queue."""
    level = ACTION_LEVELS.get(action_type, ActionLevel.NOTIFY)
    action = {
        "id": str(uuid.uuid4())[:8],
        "type": action_type,
        "level": level,
        "title": title,
        "details": details or {},
        "status": "pending",
        "created": datetime.utcnow().isoformat(),
    }

    queue = load_queue()

    # Check for duplicates (same type + title) in ANY non-rejected status
    existing = [a for a in queue if a["type"] == action_type and a["title"] == title and a["status"] in ("pending", "approved", "done")]
    if existing:
        logger.debug(f"Duplicate action skipped: {title}")
        return existing[0]

    # Also check history for recently completed actions (prevent re-generation)
    try:
        history = []
        if os.path.exists(HISTORY_PATH):
            with open(HISTORY_PATH) as f:
                history = json.load(f)
        hist_match = [a for a in history if a.get("type") == action_type and a.get("title") == title]
        if hist_match:
            logger.debug(f"Action already in history, skipped: {title}")
            return hist_match[-1]
    except Exception:
        pass

    queue.append(action)
    save_queue(queue)
    logger.info(f"Action queued [{level}]: {title}")
    return action


def approve_action(action_id: str) -> Optional[dict]:
    """Approve a pending action."""
    queue = load_queue()
    for action in queue:
        if action["id"] == action_id and action["status"] == "pending":
            action["status"] = "approved"
            action["approved_at"] = datetime.utcnow().isoformat()
            save_queue(queue)
            logger.info(f"Action approved: {action['title']}")
            return action
    return None


def reject_action(action_id: str) -> Optional[dict]:
    """Reject a pending action."""
    queue = load_queue()
    for action in queue:
        if action["id"] == action_id and action["status"] == "pending":
            action["status"] = "rejected"
            action["rejected_at"] = datetime.utcnow().isoformat()
            save_queue(queue)
            logger.info(f"Action rejected: {action['title']}")
            return action
    return None


def get_pending_actions() -> list:
    """Get all pending actions needing approval."""
    queue = load_queue()
    return [a for a in queue if a["status"] == "pending" and a["level"] == ActionLevel.APPROVAL]


def get_approved_actions() -> list:
    """Get approved actions ready for execution."""
    queue = load_queue()
    return [a for a in queue if a["status"] == "approved"]


def get_all_actions() -> list:
    """Get all actions grouped by status."""
    queue = load_queue()
    return queue


def mark_executed(action_id: str, result: str = "success"):
    """Mark an approved action as executed and move to history."""
    queue = load_queue()
    history = load_history()

    for i, action in enumerate(queue):
        if action["id"] == action_id:
            action["status"] = "executed"
            action["executed_at"] = datetime.utcnow().isoformat()
            action["result"] = result
            history.append(action)
            queue.pop(i)
            break

    save_queue(queue)
    save_history(history)


def mark_dismissed(action_id: str):
    """Dismiss a notify-only action."""
    queue = load_queue()
    for i, action in enumerate(queue):
        if action["id"] == action_id:
            action["status"] = "dismissed"
            queue.pop(i)
            break
    save_queue(queue)


def cleanup_old(days: int = 7):
    """Remove old completed actions from queue."""
    queue = load_queue()
    cutoff = datetime.utcnow().isoformat()[:10]
    queue = [a for a in queue if a["status"] == "pending" or a.get("created", "")[:10] >= cutoff]
    save_queue(queue)


def cleanup_queue(max_age_days: int = 7):
    """Remove old notify actions and duplicates."""
    from datetime import timedelta
    queue = load_queue()
    cutoff = (datetime.utcnow() - timedelta(days=max_age_days)).isoformat()
    
    cleaned = []
    seen = set()
    for a in queue:
        key = (a.get("type", ""), a.get("title", ""))
        if key in seen:
            continue
        seen.add(key)
        if a.get("level") == "notify" and a.get("status") == "pending":
            if a.get("created", "") < cutoff:
                continue
        cleaned.append(a)
    
    if len(cleaned) < len(queue):
        logger.info(f"Queue cleanup: {len(queue)} -> {len(cleaned)} actions")
        save_queue(cleaned)
    return len(queue) - len(cleaned)
