"""
Honest Metrics — daily source of truth for real traction.
Excludes family (Stockholm), internal IPs, cloud providers, and known scrapers.
Runs daily at 08:30 via LaunchAgent.

Usage: python3 -m agentindex.honest_metrics
"""
import sqlite3
import json
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'logs', 'analytics.db')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'daily_metrics.json')

# IPs to exclude from "real human" counts
EXCLUDED_IPS = {
    '83.251.205.179',   # Family (Stockholm)
    'testclient',       # Internal tests
}

# IP prefixes that are cloud/datacenter (not real humans)
CLOUD_PREFIXES = (
    '127.0',            # Localhost
    '194.132.208',      # Known scraper
    '66.249',           # Google
    '64.233',           # Google
    '66.102',           # Google
    '35.',              # GCP / AWS
    '34.',              # GCP
    '52.',              # AWS
    '54.',              # AWS
    '3.',               # AWS
    '13.',              # AWS / Azure
    '64.225',           # DigitalOcean
    '139.59',           # DigitalOcean
    '188.166',          # DigitalOcean
    '157.230',          # DigitalOcean
    '104.197',          # GCP
    '140.235',          # Oracle Cloud
    '65.21',            # Hetzner
    '95.211',           # Leaseweb
    '185.91',           # Hosting
    '43.',              # Cloud Asia
    '98.124.11',        # Automated poller
    '99.231.163',       # Automated poller
    '90.235.10',        # Known scraper
    '162.62',           # Cloud
    '152.32',           # Cloud
    '38.145',           # Cloud
    '176.100',          # Go-http-client
)

CLOUD_IPV6_PREFIXES = (
    '2a06:98c0',        # GCombinator
    '2a02:4780',        # VPS
)


def _is_real_human_ip(ip):
    """Returns True if IP is likely a real human, not cloud/bot/internal."""
    if not ip or ip in EXCLUDED_IPS:
        return False
    for prefix in CLOUD_PREFIXES:
        if ip.startswith(prefix):
            return False
    for prefix in CLOUD_IPV6_PREFIXES:
        if ip.startswith(prefix):
            return False
    return True


def compute_metrics(target_date=None):
    """Compute honest metrics for a given date (defaults to yesterday)."""
    if target_date is None:
        target_date = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')

    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row

    # Real external humans
    rows = conn.execute("""
        SELECT ip, COUNT(*) as hits, COUNT(DISTINCT path) as pages
        FROM requests
        WHERE is_bot = 0 AND date(ts) = ?
        GROUP BY ip
    """, (target_date,)).fetchall()

    real_humans = [r for r in rows if _is_real_human_ip(r['ip'])]
    unique_humans = len(real_humans)
    human_pageviews = sum(r['hits'] for r in real_humans)
    multi_page = sum(1 for r in real_humans if r['pages'] >= 2)

    # AI bot metrics
    ai_row = conn.execute("""
        SELECT
            SUM(CASE WHEN bot_name = 'ChatGPT' THEN 1 ELSE 0 END) as chatgpt_total,
            SUM(CASE WHEN bot_name = 'ChatGPT' AND path LIKE '%preflight%' THEN 1 ELSE 0 END) as chatgpt_preflight,
            SUM(CASE WHEN bot_name = 'ChatGPT' AND path NOT LIKE '%preflight%' AND path NOT LIKE '/badge%' THEN 1 ELSE 0 END) as chatgpt_content,
            SUM(CASE WHEN bot_name = 'Claude' THEN 1 ELSE 0 END) as claude_total,
            SUM(CASE WHEN bot_name = 'Perplexity' THEN 1 ELSE 0 END) as perplexity_total,
            SUM(CASE WHEN bot_name = 'Google' THEN 1 ELSE 0 END) as google_bot,
            SUM(CASE WHEN is_ai_bot = 1 THEN 1 ELSE 0 END) as all_ai_bots,
            COUNT(DISTINCT CASE WHEN is_ai_bot = 1 THEN bot_name END) as ai_systems_count
        FROM requests
        WHERE is_bot = 1 AND date(ts) = ?
    """, (target_date,)).fetchone()

    # Google organic visitors
    google_organic = conn.execute("""
        SELECT COUNT(DISTINCT ip) as visitors
        FROM requests
        WHERE is_bot = 0 AND date(ts) = ?
        AND referrer_domain LIKE '%google%'
    """, (target_date,)).fetchone()['visitors']

    # GitHub referrals
    github_refs = conn.execute("""
        SELECT COUNT(DISTINCT ip) as visitors
        FROM requests
        WHERE is_bot = 0 AND date(ts) = ?
        AND referrer_domain LIKE '%github%'
    """, (target_date,)).fetchone()['visitors']

    # Badge serves (real usage indicator)
    badge_serves = conn.execute("""
        SELECT COUNT(*) as serves
        FROM requests
        WHERE path LIKE '/badge%' AND date(ts) = ?
    """, (target_date,)).fetchone()['serves']

    # Preflight total (all bots)
    preflight_total = conn.execute("""
        SELECT COUNT(*) as total FROM requests
        WHERE path LIKE '%preflight%' AND date(ts) = ?
    """, (target_date,)).fetchone()['total']

    conn.close()

    return {
        "date": target_date,
        "real_humans": {
            "unique_visitors": unique_humans,
            "pageviews": human_pageviews,
            "multi_page_sessions": multi_page,
            "pages_per_visitor": round(human_pageviews / max(unique_humans, 1), 1),
        },
        "ai_machines": {
            "chatgpt_total": ai_row['chatgpt_total'] or 0,
            "chatgpt_preflight": ai_row['chatgpt_preflight'] or 0,
            "chatgpt_content_fetches": ai_row['chatgpt_content'] or 0,
            "claude_total": ai_row['claude_total'] or 0,
            "perplexity_total": ai_row['perplexity_total'] or 0,
            "google_bot": ai_row['google_bot'] or 0,
            "all_ai_bots": ai_row['all_ai_bots'] or 0,
            "ai_systems_active": ai_row['ai_systems_count'] or 0,
        },
        "growth_signals": {
            "google_organic_visitors": google_organic,
            "github_referral_visitors": github_refs,
            "badge_serves": badge_serves,
            "preflight_calls_total": preflight_total,
        },
        "ratio": {
            "ai_to_human": round((ai_row['all_ai_bots'] or 0) / max(unique_humans, 1), 1),
            "machine_pageviews": (ai_row['chatgpt_total'] or 0) + (ai_row['claude_total'] or 0) + (ai_row['perplexity_total'] or 0),
        },
        "computed_at": datetime.utcnow().isoformat(),
    }


def save_metrics(metrics):
    """Append metrics to time series JSON file."""
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    # Load existing
    history = []
    if os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH) as f:
                data = json.load(f)
                history = data.get("days", [])
        except (json.JSONDecodeError, KeyError):
            history = []

    # Remove existing entry for same date
    history = [d for d in history if d.get("date") != metrics["date"]]
    history.append(metrics)
    history.sort(key=lambda x: x["date"])

    # Keep last 90 days
    history = history[-90:]

    with open(OUTPUT_PATH, 'w') as f:
        json.dump({"days": history, "last_updated": datetime.utcnow().isoformat()}, f, indent=2)


def run():
    """Compute metrics for yesterday and today, save both."""
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.utcnow().strftime('%Y-%m-%d')

    for date in [yesterday, today]:
        metrics = compute_metrics(date)
        save_metrics(metrics)
        h = metrics["real_humans"]
        ai = metrics["ai_machines"]
        g = metrics["growth_signals"]
        r = metrics["ratio"]
        print(f"\n{'='*50}")
        print(f"  {date} — Honest Metrics")
        print(f"{'='*50}")
        print(f"  Real humans:     {h['unique_visitors']} unique ({h['pageviews']} pv, {h['multi_page_sessions']} multi-page)")
        print(f"  ChatGPT:         {ai['chatgpt_total']} total ({ai['chatgpt_preflight']} preflight)")
        print(f"  Claude:          {ai['claude_total']}")
        print(f"  Perplexity:      {ai['perplexity_total']}")
        print(f"  Google bot:      {ai['google_bot']}")
        print(f"  Google organic:  {g['google_organic_visitors']} visitors")
        print(f"  GitHub refs:     {g['github_referral_visitors']} visitors")
        print(f"  Badge serves:    {g['badge_serves']}")
        print(f"  Preflight total: {g['preflight_calls_total']}")
        print(f"  AI:Human ratio:  {r['ai_to_human']}:1")


if __name__ == "__main__":
    run()
