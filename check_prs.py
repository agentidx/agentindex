"""
AgentIndex PR Monitor — Kör dagligen via cron
Kollar status på alla öppna PRs, rapporterar ändringar,
och lämnar uppföljningskommentar efter 7 dagar utan aktivitet.
"""
import requests, json, os
from datetime import datetime, timedelta

TOKEN = os.environ.get('GITHUB_TOKEN', '')
if not TOKEN:
    with open(os.path.join(os.path.dirname(__file__), '.env')) as f:
        for line in f:
            if line.startswith('GITHUB_TOKEN='):
                TOKEN = line.strip().split('=', 1)[1]

HEADERS = {'Authorization': f'token {TOKEN}', 'Accept': 'application/vnd.github.v3+json'}
STATE_FILE = os.path.join(os.path.dirname(__file__), 'missionary_state.json')
LOG_FILE = os.path.join(os.path.dirname(__file__), 'pr_monitor.log')

FOLLOWUP_MSG = (
    "Hi! Just checking in on this PR. "
    "Happy to make any changes if needed. Thanks for maintaining this great list! 🙏"
)

def log(msg):
    ts = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
    line = f'[{ts}] {msg}'
    print(line)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')

def check_prs():
    with open(STATE_FILE) as f:
        state = json.load(f)

    changes = []
    for repo, info in state.get('awesome_lists', {}).items():
        if info.get('pr_status') != 'submitted':
            continue
        pr_num = info.get('pr_number')
        if not pr_num:
            continue

        r = requests.get(
            f'https://api.github.com/repos/{repo}/pulls/{pr_num}',
            headers=HEADERS, timeout=10
        )
        if not r.ok:
            log(f'WARN: {repo} #{pr_num} fetch failed: {r.status_code}')
            continue

        pr = r.json()
        gh_state = pr['state']
        merged = pr.get('merged', False)
        created = datetime.strptime(pr['created_at'][:10], '%Y-%m-%d')
        age_days = (datetime.utcnow() - created).days

        if merged:
            log(f'MERGED: {repo} #{pr_num} !!!')
            info['pr_status'] = 'merged'
            changes.append(f'MERGED: {repo} #{pr_num}')
        elif gh_state == 'closed':
            log(f'CLOSED: {repo} #{pr_num}')
            info['pr_status'] = 'closed'
            changes.append(f'CLOSED: {repo} #{pr_num}')
        elif age_days >= 7 and not info.get('followup_sent'):
            log(f'FOLLOWUP: {repo} #{pr_num} (age: {age_days} days)')
            r2 = requests.post(
                f'https://api.github.com/repos/{repo}/issues/{pr_num}/comments',
                headers=HEADERS,
                json={'body': FOLLOWUP_MSG},
                timeout=10
            )
            if r2.status_code in (200, 201):
                info['followup_sent'] = True
                log(f'  Comment posted OK')
                changes.append(f'FOLLOWUP sent: {repo} #{pr_num}')
            else:
                log(f'  Comment failed: {r2.status_code}')
        else:
            log(f'OK: {repo} #{pr_num} ({gh_state}, {age_days}d old)')

    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

    if changes:
        log(f'SUMMARY: {len(changes)} changes: {changes}')
    else:
        log('SUMMARY: No changes')

if __name__ == '__main__':
    check_prs()
