"""
Export high-risk agents with contact info for outreach.
Generates a JSON file that the send script uses.
"""
import json
from sqlalchemy import text
import sys
sys.path.insert(0, '/Users/anstudio/agentindex')
from agentindex.db.models import get_session

session = get_session()
rows = session.execute(text("""
    SELECT name, author, source_url, source, eu_risk_class, 
           compliance_score, eu_risk_confidence, category, description
    FROM agents 
    WHERE eu_risk_class = 'high'
    ORDER BY eu_risk_confidence DESC NULLS LAST, name
""")).fetchall()

targets = []
for r in rows:
    source_url = r[2]
    github_user = source_url.split('github.com/')[-1].split('/')[0] if 'github.com' in source_url else None
    repo_name = source_url.split('github.com/')[-1] if 'github.com' in source_url else None
    
    targets.append({
        "name": r[0],
        "author": r[1],
        "source_url": r[2],
        "source": r[3],
        "risk_class": r[4],
        "compliance_score": r[5],
        "confidence": r[6],
        "category": r[7],
        "description": (r[8] or "")[:200],
        "github_user": github_user,
        "repo": repo_name,
        "checker_url": f"https://nerq.ai/checker",
        "outreach_method": "github_issue" if 'github.com' in source_url else "manual",
    })

outpath = '/Users/anstudio/agentindex/outreach/targets.json'
with open(outpath, 'w') as f:
    json.dump(targets, f, indent=2)

print(f"✅ Exported {len(targets)} targets to {outpath}")
print(f"   GitHub (issue-able): {sum(1 for t in targets if t['outreach_method'] == 'github_issue')}")
print(f"   Manual: {sum(1 for t in targets if t['outreach_method'] == 'manual')}")

session.close()
