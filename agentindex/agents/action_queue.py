"""
Action Queue for Missionary 2.0

Manages pending actions with approval workflow:
- AUTO: executed immediately
- APPROVAL: shown in dashboard, waits for approve/reject
- NOTIFY: shown in dashboard, no action needed

REFACTOR v3: Stronger dedup, atomic writes, normalized keys.
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("agentindex.action_queue")

QUEUE_PATH = os.path.expanduser("~/agentindex/action_queue.json")
HISTORY_PATH = os.path.expanduser("~/agentindex/action_history.json")


class ActionLevel:
    AUTO = "auto"
    APPROVAL = "approval"
    NOTIFY = "notify"


ACTION_LEVELS = {
    "update_agent_md": ActionLevel.AUTO,
    "add_search_term": ActionLevel.AUTO,
    "check_endpoint": ActionLevel.AUTO,
    "submit_pr": ActionLevel.APPROVAL,
    "register_registry": ActionLevel.APPROVAL,
    "add_awesome_list": ActionLevel.APPROVAL,
    "add_spider_source": ActionLevel.APPROVAL,
    "new_competitor": ActionLevel.NOTIFY,
    "endpoint_down": ActionLevel.NOTIFY,
    "pr_status_update": ActionLevel.NOTIFY,
    "spy_new_competitor": ActionLevel.NOTIFY,
    "spy_implement_feature": ActionLevel.APPROVAL,
    "spy_improve_visibility": ActionLevel.NOTIFY,
    "spy_competitor_active": ActionLevel.NOTIFY,
    "spy_daily_summary": ActionLevel.NOTIFY,
    "spy_feature_done": ActionLevel.NOTIFY,
    "spy_feature_reminder": ActionLevel.NOTIFY,
    "spy_a2a_outreach": ActionLevel.NOTIFY,
}


def _safe_load_json(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        logger.warning(f"JSON at {path} is not a list, resetting")
        return []
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Failed to load {path}: {e}")
        try:
            with open(path) as f:
                raw = f.read().strip()
            if raw.startswith("["):
                last_brace = raw.rfind("}")
                if last_brace > 0:
                    candidate = raw[:last_brace + 1] + "]"
                    data = json.loads(candidate)
                    logger.info(f"Recovered {len(data)} items from corrupt {path}")
                    return data
        except Exception:
            pass
        return []


def _safe_save_json(path: str, data: list):
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp_path, path)
    except Exception as e:
        logger.error(f"Failed to save {path}: {e}")
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e2:
            logger.error(f"Fallback save also failed for {path}: {e2}")


def _dedup_key(action_type: str, title: str) -> str:
    normalized = re.sub(r'\s*\(\d+\*?\)\s*', '', title).strip()
    return f"{action_type}::{normalized}"


def load_queue() -> list:
    return _safe_load_json(QUEUE_PATH)


def save_queue(queue: list):
    _safe_save_json(QUEUE_PATH, queue)


def load_history() -> list:
    return _safe_load_json(HISTORY_PATH)


def save_history(history: list):
    _safe_save_json(HISTORY_PATH, history)


def add_action(action_type: str, title: str, details: dict = None) -> dict:
    level = ACTION_LEVELS.get(action_type, ActionLevel.NOTIFY)
    queue = load_queue()
    history = load_history()
    key = _dedup_key(action_type, title)

    for a in queue:
        existing_key = _dedup_key(a.get("type", ""), a.get("title", ""))
        if existing_key == key and a.get("status") not in ("rejected",):
            logger.debug(f"Duplicate action skipped (in queue): {title}")
            return a

    for a in history:
        existing_key = _dedup_key(a.get("type", ""), a.get("title", ""))
        if existing_key == key:
            logger.debug(f"Duplicate action skipped (in history): {title}")
            return a

    action = {
        "id": str(uuid.uuid4())[:8],
        "type": action_type,
        "level": level,
        "title": title,
        "details": details or {},
        "status": "pending",
        "created": datetime.utcnow().isoformat(),
    }

    queue.append(action)
    save_queue(queue)
    logger.info(f"Action queued [{level}]: {title}")
    return action


def approve_action(action_id: str) -> Optional[dict]:
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
    queue = load_queue()
    return [a for a in queue if a["status"] == "pending" and a["level"] == ActionLevel.APPROVAL]


def get_approved_actions() -> list:
    queue = load_queue()
    return [a for a in queue if a["status"] == "approved"]




def get_auto_actions() -> list:
    """Get pending auto-level actions ready for immediate execution."""
    queue = load_queue()
    return [a for a in queue if a["status"] == "pending" and a["level"] == ActionLevel.AUTO]

def get_all_actions() -> list:
    return load_queue()


def mark_executed(action_id: str, result: str = "success"):
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
    queue = load_queue()
    history = load_history()
    for i, action in enumerate(queue):
        if action["id"] == action_id:
            action["status"] = "dismissed"
            action["dismissed_at"] = datetime.utcnow().isoformat()
            history.append(action)
            queue.pop(i)
            break
    save_queue(queue)
    save_history(history)


def cleanup_old(days: int = 7):
    queue = load_queue()
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    cleaned = [a for a in queue if a["status"] == "pending" or a.get("created", "")[:10] >= cutoff]
    if len(cleaned) < len(queue):
        logger.info(f"Cleanup: {len(queue)} -> {len(cleaned)}")
        save_queue(cleaned)


def cleanup_queue(max_age_days: int = 7):
    queue = load_queue()
    cutoff = (datetime.utcnow() - timedelta(days=max_age_days)).isoformat()
    cleaned = []
    seen = set()
    for a in queue:
        key = _dedup_key(a.get("type", ""), a.get("title", ""))
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
