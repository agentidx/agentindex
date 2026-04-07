"""
Nerq Outreach — Send compliance alerts to high-risk agent owners.
Uses Resend API. Can be run by Buzz or manually.

Usage:
  python send_outreach.py --dry-run          # Preview first 5 emails
  python send_outreach.py --send --limit 10  # Send first 10
  python send_outreach.py --send             # Send all unsent
"""
import json
import os
import sys
import time
import argparse
import requests
from datetime import datetime
from pathlib import Path

RESEND_API_KEY = os.getenv("RESEND_API_KEY") or open(
    Path(__file__).parent.parent / ".env"
).read().split("RESEND_API_KEY=")[1].strip().split("\n")[0]

TARGETS_FILE = Path(__file__).parent / "targets.json"
SENT_LOG = Path(__file__).parent / "sent_log.json"
FROM_EMAIL = "hello@nerq.ai"
FROM_NAME = "Nerq — AI Compliance"

def load_targets():
    with open(TARGETS_FILE) as f:
        return json.load(f)

def load_sent():
    if SENT_LOG.exists():
        with open(SENT_LOG) as f:
            return json.load(f)
    return {}

def save_sent(sent):
    with open(SENT_LOG, 'w') as f:
        json.dump(sent, f, indent=2)

def days_until_deadline():
    deadline = datetime(2026, 8, 2)
    return (deadline - datetime.now()).days

def generate_email(target):
    name = target["name"]
    category = target["category"] or "AI"
    score = target["compliance_score"] or 0
    days = days_until_deadline()
    repo_url = target["source_url"]
    checker_url = target["checker_url"]
    
    subject = f"Heads up: {name} may need EU AI Act compliance"
    
    body = f"""Hey,

I came across your project {name} ({repo_url}) while building Nerq — we're indexing AI agents and checking them against the EU AI Act.

Your project flagged as high-risk. Not because anything's wrong with it, but because it touches {category} — which the EU considers a high-impact domain under Annex III.

The practical issue: if anyone deploys this commercially in the EU after August 2, 2026 ({days} days from now), they'll need to meet specific compliance requirements — risk management, documentation, human oversight, etc.

I built a free checker that shows exactly which articles apply and what gaps exist: {checker_url}

We've scanned about 24,000 agents so far. Only 153 flagged as high-risk, yours among them. Most people I've talked to had no idea their project fell into this category.

Happy to answer any questions — just reply here.

— Anders
Nerq (https://nerq.ai)
"""
    
    # Convert markdown bold to HTML
    html_body = body.replace("**", "<strong>", 1)
    while "**" in html_body:
        html_body = html_body.replace("**", "</strong>", 1)
        if "**" in html_body:
            html_body = html_body.replace("**", "<strong>", 1)
    html_body = html_body.replace("\n", "<br>\n")
    
    return subject, body, html_body

def send_email(to_email, subject, text_body, html_body):
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": f"{FROM_NAME} <{FROM_EMAIL}>",
            "to": [to_email],
            "subject": subject,
            "text": text_body,
            "html": html_body,
        }
    )
    return resp.status_code, resp.json()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview emails without sending")
    parser.add_argument("--send", action="store_true", help="Actually send emails")
    parser.add_argument("--limit", type=int, default=0, help="Max emails to send (0=all)")
    parser.add_argument("--to-override", type=str, help="Send all to this address instead (for testing)")
    args = parser.parse_args()
    
    if not args.dry_run and not args.send:
        print("Specify --dry-run or --send")
        return
    
    targets = load_targets()
    sent = load_sent()
    unsent = [t for t in targets if t["source_url"] not in sent]
    
    print(f"Total targets: {len(targets)}")
    print(f"Already sent: {len(sent)}")
    print(f"Remaining: {len(unsent)}")
    print()
    
    if args.limit:
        unsent = unsent[:args.limit]
    
    if args.dry_run:
        for t in unsent[:5]:
            subject, text_body, _ = generate_email(t)
            print(f"--- TO: {t['author']} ({t['source_url']})")
            print(f"    SUBJECT: {subject}")
            print(f"    PREVIEW: {text_body[:200]}...")
            print()
        print(f"(Showing {min(5, len(unsent))} of {len(unsent)} unsent)")
        return
    
    # Sending mode
    success = 0
    failed = 0
    for i, t in enumerate(unsent):
        # For GitHub targets, we need their email — use noreply for now
        # Real implementation: Buzz fetches email from GitHub profile API
        if args.to_override:
            to_email = args.to_override
        else:
            to_email = f"{t['github_user']}@users.noreply.github.com" if t['github_user'] else None
            if not to_email:
                print(f"  SKIP {t['name']} — no contact info")
                continue
        
        subject, text_body, html_body = generate_email(t)
        status, resp = send_email(to_email, subject, text_body, html_body)
        
        if status == 200:
            sent[t["source_url"]] = {
                "sent_at": datetime.now().isoformat(),
                "to": to_email,
                "subject": subject,
            }
            save_sent(sent)
            success += 1
            print(f"  ✅ [{i+1}/{len(unsent)}] {t['name']} → {to_email}")
        else:
            failed += 1
            print(f"  ❌ [{i+1}/{len(unsent)}] {t['name']} — {resp}")
        
        time.sleep(0.5)  # Rate limit
    
    print(f"\nDone: {success} sent, {failed} failed")

if __name__ == "__main__":
    main()
