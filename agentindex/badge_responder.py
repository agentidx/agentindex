#!/usr/bin/env python3
"""
Badge Responder — Auto-reply to badge outreach GitHub issues.

Checks for new comments on our badge outreach issues and responds
with trust data, methodology explanations, or polite acknowledgements.

Usage:
    python3 -m agentindex.badge_responder              # dry-run (default)
    python3 -m agentindex.badge_responder --live        # auto-post replies
    python3 -m agentindex.badge_responder --live --all  # check all issues, not just unread

Safety:
    - "can't open link" / data requests: auto-posted (purely factual)
    - "not interested" / closings: auto-posted (polite farewell)
    - "what is this" / methodology: auto-posted (educational)
    - "looks good" / accepted: auto-posted (thank you)
    - Unknown intent: saved as draft only, never auto-posted

LaunchAgent: com.nerq.badge-responder (every 2 hours)
"""

import argparse
import json
import logging
import os
import re
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [badge-responder] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("badge_responder")

SCRIPT_DIR = Path(__file__).parent
OUTREACH_LOG = SCRIPT_DIR / "badge_outreach_log.json"
RESPONSE_LOG = SCRIPT_DIR.parent / "logs" / "badge_responses.json"
DRAFT_LOG = SCRIPT_DIR.parent / "logs" / "badge_responses_draft.json"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
API_BASE = "https://api.github.com"
NERQ_API = os.environ.get("NERQ_API", "https://nerq.ai")
BOT_LOGIN = os.environ.get("BADGE_BOT_LOGIN", "")  # filled dynamically

DELAY_BETWEEN_REPLIES = 10  # seconds


# ── GitHub API helpers ──────────────────────────────────

def _gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "NerqBadgeResponder/1.0",
    }


def _gh_get(url):
    req = urllib.request.Request(url, headers=_gh_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        log.error(f"GitHub API error {e.code}: {url}")
        return None


def _gh_post(url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_gh_headers(), method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        log.error(f"GitHub POST error {e.code}: {url}")
        try:
            log.error(f"  Response: {e.read().decode()[:200]}")
        except Exception:
            pass
        return None


def _gh_post_patch(url, body):
    """PATCH request (for closing issues)."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_gh_headers(), method="PATCH")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        log.error(f"GitHub PATCH error {e.code}: {url}")
        return None


def _add_to_blocklist(repo_name):
    """Add repo to outreach blocklist so we never contact them again."""
    try:
        with open(OUTREACH_LOG) as f:
            log_data = json.load(f)
        contacted = log_data.get("contacted", {})
        if repo_name in contacted:
            contacted[repo_name]["status"] = "rejected_spam"
            contacted[repo_name]["blocklisted"] = True
        log_data.setdefault("blocklist", [])
        if repo_name not in log_data["blocklist"]:
            log_data["blocklist"].append(repo_name)
        with open(OUTREACH_LOG, "w") as f:
            json.dump(log_data, f, indent=2, default=str)
    except Exception as e:
        log.error(f"Failed to update blocklist: {e}")


def _get_bot_login():
    """Get authenticated user's login."""
    global BOT_LOGIN
    if BOT_LOGIN:
        return BOT_LOGIN
    user = _gh_get(f"{API_BASE}/user")
    if user:
        BOT_LOGIN = user.get("login", "")
    return BOT_LOGIN


# ── Nerq API helpers ───────────────────────────────────

def _fetch_trust_data(repo_name):
    """Fetch trust data via /v1/preflight."""
    url = f"{NERQ_API}/v1/preflight?target={urllib.request.quote(repo_name)}"
    req = urllib.request.Request(url, headers={"User-Agent": "NerqBadgeResponder/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log.error(f"Nerq API error for {repo_name}: {e}")
        return None


def _format_trust_table(data, repo_name):
    """Format trust data as markdown — safe string formatting."""
    score = data.get("target_trust", "N/A")
    grade = data.get("target_grade", "N/A")
    category = data.get("target_category", "N/A")
    sec = data.get("security", {})
    pop = data.get("popularity", {})
    act = data.get("activity", {})

    cves = sec.get("known_cves", 0)
    license_type = sec.get("license", "Unknown")
    stars = pop.get("github_stars", "N/A")
    if isinstance(stars, int):
        stars_str = f"{stars:,}"
    else:
        stars_str = str(stars)
    last_commit = act.get("last_commit_days_ago", "N/A")

    lines = [
        f"**Trust Report for {repo_name}:**",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| **Trust Score** | {score}/100 ({grade}) |",
        f"| **Category** | {category} |",
        f"| **License** | {license_type} |",
        f"| **Known CVEs** | {cves} |",
        f"| **GitHub Stars** | {stars_str} |",
        f"| **Last Commit** | {last_commit} days ago |",
        f"| **Risk Level** | {data.get('interaction_risk', 'N/A')} |",
        "",
        "You can also check via our API:",
        "```",
        f"curl https://nerq.ai/v1/preflight?target={repo_name}",
        "```",
        "",
        f"Full report: https://nerq.ai/safe/{repo_name}",
    ]
    return "\n".join(lines)


# ── Intent classification ──────────────────────────────

INTENT_PATTERNS = {
    "cant_open": [
        r"can.?t open", r"cannot open", r"link.*(broken|dead|404|not work|doesn.t work|not load)",
        r"page.*(not found|404|blank|empty|error|not load|doesn.t load)",
        r"show.*(me|screenshot|report|data|score)", r"take a screenshot",
        r"unable to (access|open|view|see)", r"not accessible",
        r"could you (show|share|post|provide)", r"what.*(score|result|report)",
        r"^the same\.?$", r"same (issue|problem|error)",  # "the same" = same issue
        r"\u6253\u4e0d\u5f00", r"\u65e0\u6cd5\u6253\u5f00", r"\u770b\u4e0d\u4e86",  # Chinese: can't open
    ],
    "what_is_this": [
        r"what is (this|nerq|trust score)", r"how does.*(scor|work|calculat|rat)",
        r"what does.*(mean|measur|evaluat)", r"how (are|is).*(scor|calculat|determin)",
        r"methodology", r"explain.*(score|rating|trust)",
        r"\u8fd9\u662f\u4ec0\u4e48",  # Chinese: what is this
    ],
    "not_interested": [
        r"not interested", r"no thanks", r"don.?t want", r"please (close|remove|delete|stop)",
        r"didn.?t ask", r"opt.?out", r"unsubscribe",
    ],
    "spam_complaint": [
        r"spam", r"unsolicited", r"promotional", r"not a genuine issue",
        r"bot.?spam", r"stop (opening|creating|posting)", r"abuse",
        r"report.*(spam|abuse)", r"this is (spam|junk|unwanted)",
    ],
    "accepted": [
        r"(looks? good|great|nice|cool|awesome|thanks|thank you|added|merged|will add)",
        r"badge.*(added|merged|included)", r"(already |have )?(added|included|merged)",
        r"appreciate", r"it.?s good", r"i think it.?s good",
        r"\u8c22\u8c22", r"\u611f\u8c22",  # Chinese: thank you
    ],
}


def classify_intent(comment_body):
    """Classify comment intent. Returns (intent, confidence)."""
    text = comment_body.lower().strip()

    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return intent, 0.9

    # Fallback: if very short and has a question mark, treat as data request
    if len(text) < 100 and "?" in text:
        return "cant_open", 0.5

    return "unknown", 0.0


# ── Response generators ────────────────────────────────

def generate_response(intent, repo_name, comment_body):
    """Generate response text based on intent."""
    if intent == "cant_open":
        data = _fetch_trust_data(repo_name)
        if not data:
            return None, False  # can't generate without data
        trust_table = _format_trust_table(data, repo_name)
        reply = (
            f"Thanks for your interest! Here's the trust data directly:\n\n"
            f"{trust_table}\n\n"
            f"The link should also be working now. Let me know if you have any questions!"
        )
        return reply, True  # auto-post OK (purely factual)

    elif intent == "what_is_this":
        data = _fetch_trust_data(repo_name)
        score_line = ""
        if data:
            score = data.get("target_trust", "N/A")
            grade = data.get("target_grade", "N/A")
            score_line = f"\n\nYour project scored **{score}/100 ({grade})**."

        reply = (
            f"Great question! [Nerq](https://nerq.ai) independently analyzes open-source "
            f"AI projects for trust across several dimensions:\n\n"
            f"- **Security**: Known CVEs, dependency vulnerabilities\n"
            f"- **Maintenance**: Commit frequency, release cadence, issue response time\n"
            f"- **License**: License clarity and permissiveness\n"
            f"- **Popularity**: Stars, downloads, dependent projects\n"
            f"- **Ecosystem**: Integration breadth, community health\n"
            f"{score_line}\n\n"
            f"The badge shows this score at a glance and updates automatically. "
            f"Full methodology: https://nerq.ai/trust-score\n\n"
            f"No obligation to add it — just thought you'd find it useful!"
        )
        return reply, True

    elif intent == "not_interested":
        reply = (
            "No problem at all! The badge is always available if you change your mind. "
            "Thanks for checking it out."
        )
        return reply, True

    elif intent == "spam_complaint":
        reply = (
            "Fair point \u2014 apologies for the unsolicited issue. Closing this now. "
            "If you ever want to check your trust score in the future, it's available "
            "at nerq.ai. Thanks for the feedback."
        )
        return reply, True  # auto-post + will be auto-closed

    elif intent == "accepted":
        owner_repo = repo_name.replace("/", "-").lower()
        reply = (
            f"Awesome, thank you! The badge will auto-update as your trust score changes.\n\n"
            f"You can check your project's trust report anytime at: "
            f"https://nerq.ai/safe/{repo_name}\n\n"
            f"And via the API:\n"
            f"```\ncurl https://nerq.ai/v1/preflight?target={repo_name}\n```\n\n"
            f"Thanks for being part of the trust-verified ecosystem!"
        )
        return reply, True

    else:
        return None, False  # unknown intent, don't auto-post


# ── Core logic ─────────────────────────────────────────

def load_outreach_log():
    if OUTREACH_LOG.exists():
        with open(OUTREACH_LOG) as f:
            return json.load(f)
    return {"contacted": {}}


def load_response_log():
    if RESPONSE_LOG.exists():
        with open(RESPONSE_LOG) as f:
            return json.load(f)
    return {"replied": {}}


def save_response_log(data):
    RESPONSE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(RESPONSE_LOG, "w") as f:
        json.dump(data, f, indent=2, default=str)


def save_draft(draft_entry):
    DRAFT_LOG.parent.mkdir(parents=True, exist_ok=True)
    drafts = []
    if DRAFT_LOG.exists():
        try:
            with open(DRAFT_LOG) as f:
                drafts = json.load(f)
        except Exception:
            drafts = []
    drafts.append(draft_entry)
    with open(DRAFT_LOG, "w") as f:
        json.dump(drafts, f, indent=2, default=str)


def extract_repo_from_issue_url(issue_url):
    """Extract owner/repo from GitHub issue URL."""
    m = re.search(r"github\.com/([^/]+)/([^/]+)/issues/", issue_url)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return None


def check_and_respond(live=False, check_all=False):
    """Main loop: check outreach issues for new comments and respond."""
    if not GITHUB_TOKEN:
        log.error("GITHUB_TOKEN required")
        return

    bot_login = _get_bot_login()
    log.info(f"Bot login: {bot_login}")

    outreach = load_outreach_log()
    response_log = load_response_log()
    contacted = outreach.get("contacted", {})

    replied_count = 0
    draft_count = 0
    skipped_count = 0

    for repo_name, info in contacted.items():
        issue_url = info.get("issue_url")
        if not issue_url or "error" in info:
            continue

        # Extract issue API URL
        m = re.search(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)", issue_url)
        if not m:
            continue
        owner, repo, issue_num = m.group(1), m.group(2), m.group(3)
        comments_url = f"{API_BASE}/repos/{owner}/{repo}/issues/{issue_num}/comments"

        # Check if we already processed this issue
        issue_key = f"{owner}/{repo}#{issue_num}"
        last_checked = response_log.get("replied", {}).get(issue_key, {}).get("last_comment_id", 0)

        # Fetch comments
        comments = _gh_get(comments_url)
        if not comments or not isinstance(comments, list):
            continue

        # Find new comments not from us
        new_comments = []
        for c in comments:
            comment_login = c.get("user", {}).get("login", "")
            comment_id = c.get("id", 0)
            if comment_login == bot_login:
                continue  # skip our own comments
            if comment_id <= last_checked and not check_all:
                continue  # already processed
            new_comments.append(c)

        if not new_comments:
            continue

        log.info(f"  {issue_key}: {len(new_comments)} new comment(s)")

        for comment in new_comments:
            comment_id = comment.get("id", 0)
            comment_body = comment.get("body", "")
            comment_user = comment.get("user", {}).get("login", "")
            comment_user_type = comment.get("user", {}).get("type", "User")

            # Skip bot comments (GitHub Actions, Linear, triage bots, etc.)
            if comment_user_type == "Bot" or comment_user.endswith("[bot]"):
                log.info(f"    Skipping bot comment by @{comment_user}")
                response_log.setdefault("replied", {}).setdefault(issue_key, {})
                response_log["replied"][issue_key]["last_comment_id"] = max(
                    comment_id, response_log["replied"][issue_key].get("last_comment_id", 0)
                )
                continue

            intent, confidence = classify_intent(comment_body)
            log.info(f"    Comment by @{comment_user}: intent={intent} (conf={confidence:.1f})")
            log.info(f"    Text: {comment_body[:120]}...")

            reply_text, auto_ok = generate_response(intent, repo_name, comment_body)

            if reply_text and auto_ok and live:
                # Post reply
                post_url = f"{API_BASE}/repos/{owner}/{repo}/issues/{issue_num}/comments"
                result = _gh_post(post_url, {"body": reply_text})
                if result:
                    log.info(f"    Posted reply: {result.get('html_url', 'OK')}")
                    replied_count += 1
                else:
                    log.error(f"    Failed to post reply")

                # Auto-close and blocklist on spam complaints or not_interested
                if intent in ("spam_complaint", "not_interested"):
                    close_url = f"{API_BASE}/repos/{owner}/{repo}/issues/{issue_num}"
                    close_result = _gh_post_patch(close_url, {"state": "closed"})
                    if close_result:
                        log.info(f"    Auto-closed issue")
                    if intent == "spam_complaint":
                        _add_to_blocklist(repo_name)
                        log.info(f"    Added {repo_name} to blocklist")

                time.sleep(DELAY_BETWEEN_REPLIES)

            elif reply_text and auto_ok and not live:
                log.info(f"    [DRY RUN] Would auto-post reply ({len(reply_text)} chars)")
                replied_count += 1

            elif reply_text and not auto_ok:
                # Save as draft
                save_draft({
                    "issue": issue_key,
                    "issue_url": issue_url,
                    "repo": repo_name,
                    "comment_user": comment_user,
                    "comment_body": comment_body[:500],
                    "intent": intent,
                    "confidence": confidence,
                    "draft_reply": reply_text,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                log.info(f"    Saved draft reply (intent={intent}, confidence={confidence:.1f})")
                draft_count += 1

            else:
                # Unknown intent, no reply generated
                save_draft({
                    "issue": issue_key,
                    "issue_url": issue_url,
                    "repo": repo_name,
                    "comment_user": comment_user,
                    "comment_body": comment_body[:500],
                    "intent": intent,
                    "confidence": confidence,
                    "draft_reply": None,
                    "needs_manual_review": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                log.info(f"    Unknown intent — saved for manual review")
                draft_count += 1

            # Update last processed comment
            if issue_key not in response_log.get("replied", {}):
                response_log.setdefault("replied", {})[issue_key] = {}
            response_log["replied"][issue_key]["last_comment_id"] = max(
                comment_id, response_log["replied"][issue_key].get("last_comment_id", 0)
            )
            response_log["replied"][issue_key]["last_checked"] = datetime.now(timezone.utc).isoformat()

    save_response_log(response_log)
    mode = "LIVE" if live else "DRY RUN"
    log.info(f"[{mode}] Done: {replied_count} replied, {draft_count} drafts, {skipped_count} skipped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Badge outreach auto-responder")
    parser.add_argument("--live", action="store_true", help="Actually post replies (default: dry run)")
    parser.add_argument("--all", action="store_true", help="Check all comments, not just unread")
    args = parser.parse_args()

    check_and_respond(live=args.live, check_all=args.all)
