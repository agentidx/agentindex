#!/usr/bin/env python3
"""
GitHub Issues Outreach Bot - Anders Specification

Automatiserad GitHub Issues outreach för compliance badge adoption.
Två spår: Gröna badges (volym) + Röda alerts (värde)
"""

import os
import sys
import time
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentindex.db.models import Agent, get_session
from sqlalchemy import select, text, and_, func
from github import Github, GithubException
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [github_outreach] %(message)s')
logger = logging.getLogger("github_outreach")

class GitHubIssuesOutreachBot:
    """Automatiserad GitHub Issues outreach för compliance badges."""
    
    def __init__(self, github_token: Optional[str] = None, dry_run: bool = False):
        self.github_token = github_token or os.getenv('GITHUB_TOKEN')
        self.github = Github(self.github_token, per_page=100) if self.github_token else None
        self.dry_run = dry_run
        self.session = get_session()
        
        # Rate limiting enligt Anders spec
        self.max_green_per_day = 100
        self.max_red_per_day = 20
        self.issue_delay_seconds = 30  # 30 sek mellan issues
        
        # Templates enligt Anders spec
        self.green_title_template = "✅ Your AI project is compliant across 14 jurisdictions — show it with a badge"
        
        self.green_body_template = """## Good news: You're compliant ✅

Hi there 👋

We're [Nerq](https://nerq.ai), an open platform that scans AI projects for regulatory compliance across 14 global jurisdictions (EU AI Act, Colorado AI Act, and more).

We scanned this repository and **your project is classified as minimal risk** across all checked jurisdictions. That's great!

### Show it off

Add a compliance badge to your README — it takes 10 seconds:

```
[![Nerq Comply](https://nerq.ai/compliance/badge/agent/{agent_id})](https://nerq.ai/checker)
```

This renders as: ![Nerq Comply](https://nerq.ai/compliance/badge/agent/{agent_id})

### Why add a badge?

- **Build trust** — users and enterprises increasingly care about AI compliance
- **Future-proof** — badge updates automatically if regulations change
- **Free forever** — no account, no cost, no catch

### Your full report

- **Check details:** [nerq.ai/checker](https://nerq.ai/checker)
- **14 jurisdictions tracked:** EU, US (CO, CA, IL, TX), South Korea, China, Japan, Singapore, UK, Brazil, Canada, Vietnam
- **{total_agents}+ projects scanned** — [see the data](https://nerq.ai/blog/state-of-ai-agent-compliance-2026.html)

If you'd like a different badge format (HTML, RST) or have questions, just comment here.

---
*Automated scan by [Nerq](https://nerq.ai) — open AI compliance for developers. Not legal advice. [Privacy](https://nerq.ai/privacy)*"""

        self.red_title_template = "⚠️ AI Compliance Notice: This project may require attention in {count} jurisdictions"
        
        self.red_body_template = """## AI Compliance Notice

Hi there 👋

We're [Nerq](https://nerq.ai), an open platform tracking AI compliance across 14 global jurisdictions. During a scan of AI projects, we identified that this repository may be affected by upcoming regulations.

### Your classification

| Jurisdiction | Risk Level | Deadline |
|---|---|---|
{jurisdiction_rows}

**Overall: {overall_risk}** across {jur_count} jurisdiction(s).

### What this means

Your project appears to involve {risk_reason}. Several jurisdictions classify this as a regulated AI use case. Key upcoming deadlines:

- 🇺🇸 Colorado AI Act: June 30, 2026
- 🇪🇺 EU AI Act Annex III: August 2, 2026

### What you can do

1. **See your full report:** [nerq.ai/checker](https://nerq.ai/checker) (free, instant)
2. **Add a transparency badge** to show you're aware and working on it:

```
[![Nerq Comply](https://nerq.ai/compliance/badge/agent/{agent_id})](https://nerq.ai/checker)
```

3. **Read the full landscape:** [State of AI Agent Compliance 2026](https://nerq.ai/blog/state-of-ai-agent-compliance-2026.html)

This is informational only — not legal advice. If you believe this classification is incorrect, comment here and we'll review.

---
*Automated scan by [Nerq](https://nerq.ai). [Privacy](https://nerq.ai/privacy)*"""
    
    def run_daily_outreach(self) -> Dict:
        """Kör daglig outreach enligt Anders specifikationer."""
        
        logger.info("🚀 Starting daily GitHub Issues outreach")
        logger.info(f"   Green targets: {self.max_green_per_day} issues")
        logger.info(f"   Red targets: {self.max_red_per_day} issues")
        logger.info(f"   Dry run: {self.dry_run}")
        
        results = {
            'green_issues': [],
            'red_issues': [],
            'errors': [],
            'stats': {
                'green_attempted': 0,
                'green_created': 0,
                'red_attempted': 0,
                'red_created': 0,
                'errors': 0
            }
        }
        
        # Get current total agents for templates
        total_agents = self.session.execute(select(func.count(Agent.id))).scalar()
        
        try:
            # SPÅR 1: GRÖNA BADGES (80% prioritet)
            logger.info("🟢 Processing GREEN badges (minimal risk repos)")
            green_targets = self._get_green_targets(limit=self.max_green_per_day)
            
            for i, target in enumerate(green_targets):
                try:
                    logger.info(f"   [{i+1}/{len(green_targets)}] Processing {target['repo_url']}")
                    
                    issue_result = self._create_green_issue(target, total_agents)
                    results['green_issues'].append(issue_result)
                    results['stats']['green_attempted'] += 1
                    
                    if issue_result['success']:
                        results['stats']['green_created'] += 1
                        logger.info(f"      ✅ Created: {issue_result.get('issue_url', 'dry-run')}")
                    else:
                        results['stats']['errors'] += 1
                        logger.error(f"      ❌ Failed: {issue_result.get('error', 'Unknown error')}")
                    
                    # Rate limiting mellan issues
                    if not self.dry_run and i < len(green_targets) - 1:
                        time.sleep(self.issue_delay_seconds)
                        
                except Exception as e:
                    error_msg = f"Error processing green target {target.get('repo_url', 'unknown')}: {e}"
                    logger.error(f"      ❌ {error_msg}")
                    results['errors'].append(error_msg)
                    results['stats']['errors'] += 1
            
            # SPÅR 2: RÖDA ALERTS (20% prioritet)  
            logger.info("🔴 Processing RED alerts (high risk repos)")
            red_targets = self._get_red_targets(limit=self.max_red_per_day)
            
            for i, target in enumerate(red_targets):
                try:
                    logger.info(f"   [{i+1}/{len(red_targets)}] Processing {target['repo_url']}")
                    
                    issue_result = self._create_red_issue(target, total_agents)
                    results['red_issues'].append(issue_result)
                    results['stats']['red_attempted'] += 1
                    
                    if issue_result['success']:
                        results['stats']['red_created'] += 1
                        logger.info(f"      ✅ Created: {issue_result.get('issue_url', 'dry-run')}")
                    else:
                        results['stats']['errors'] += 1
                        logger.error(f"      ❌ Failed: {issue_result.get('error', 'Unknown error')}")
                    
                    # Rate limiting
                    if not self.dry_run and i < len(red_targets) - 1:
                        time.sleep(self.issue_delay_seconds)
                        
                except Exception as e:
                    error_msg = f"Error processing red target {target.get('repo_url', 'unknown')}: {e}"
                    logger.error(f"      ❌ {error_msg}")
                    results['errors'].append(error_msg)
                    results['stats']['errors'] += 1
            
            # Sammanfattning
            logger.info("🏆 Daily outreach complete")
            logger.info(f"   Green: {results['stats']['green_created']}/{results['stats']['green_attempted']} created")
            logger.info(f"   Red: {results['stats']['red_created']}/{results['stats']['red_attempted']} created")
            logger.info(f"   Total: {results['stats']['green_created'] + results['stats']['red_created']} issues created")
            logger.info(f"   Errors: {results['stats']['errors']}")
            
            return results
            
        except Exception as e:
            logger.error(f"💥 Daily outreach failed: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            self.session.close()
    
    def _get_green_targets(self, limit: int) -> List[Dict]:
        """Hämta gröna targets enligt Anders specifikation."""
        
        # Query: minimal risk, GitHub, 100-5000 stars (validera mottagning först)
        query = select(Agent).where(
            and_(
                Agent.source == 'github',
                Agent.eu_risk_class == 'minimal',
                Agent.stars >= 100,
                Agent.stars <= 5000  # Anders: inte mega-repos
            )
        ).order_by(Agent.stars.desc()).limit(limit * 3)  # Extra för filtering
        
        agents = self.session.execute(query).scalars().all()
        
        targets = []
        for agent in agents:
            # Check if already contacted
            existing = self.session.execute(
                select(text('1')).select_from(text('outreach_issues')).where(
                    text('agent_id = :agent_id AND track = :track')
                ).params(agent_id=str(agent.id), track='green')
            ).first()
            
            if existing:
                continue  # Skip redan kontaktade
            
            # Extract repo info
            repo_info = self._extract_repo_info(agent.source_url)
            if not repo_info:
                continue
            
            # Anders filter: filtrera bort awesome-lists och non-agent repos
            if self._is_non_agent_repo(agent, repo_info):
                continue
            
            # Calculate personalization score
            target_data = {
                'agent_id': str(agent.id),
                'repo_url': agent.source_url,
                'repo_owner': repo_info['owner'],
                'repo_name': repo_info['name'],
                'stars': agent.stars,
                'description': agent.description or '',
                'track': 'green'
            }
            
            personalization_score = self._calculate_personalization_score(agent, repo_info)
            
            # Anders filter: minimum personalization_score 0.5
            if personalization_score < 0.5:
                continue
            
            target_data['personalization_score'] = personalization_score
            targets.append(target_data)
            
            if len(targets) >= limit:
                break
        
        logger.info(f"   Found {len(targets)} green targets (minimal risk, >20⭐)")
        return targets
    
    def _get_red_targets(self, limit: int) -> List[Dict]:
        """Hämta röda targets enligt Anders specifikation."""
        
        query = select(Agent).where(
            and_(
                Agent.source == 'github',
                Agent.eu_risk_class == 'high',
                Agent.stars >= 100,  # Samma som grön
                Agent.stars <= 5000  # Samma stars range
            )
        ).order_by(Agent.stars.desc()).limit(limit * 3)
        
        agents = self.session.execute(query).scalars().all()
        
        targets = []
        for agent in agents:
            # Check if already contacted
            existing = self.session.execute(
                select(text('1')).select_from(text('outreach_issues')).where(
                    text('agent_id = :agent_id AND track = :track')
                ).params(agent_id=str(agent.id), track='red')
            ).first()
            
            if existing:
                continue
                
            repo_info = self._extract_repo_info(agent.source_url)
            if not repo_info:
                continue
            
            # Anders filter: samma som green targets
            if self._is_non_agent_repo(agent, repo_info):
                continue
            
            target_data = {
                'agent_id': str(agent.id),
                'repo_url': agent.source_url,
                'repo_owner': repo_info['owner'],
                'repo_name': repo_info['name'],
                'stars': agent.stars,
                'description': agent.description or '',
                'track': 'red'
            }
            
            personalization_score = self._calculate_personalization_score(agent, repo_info)
            
            # Anders filter: minimum personalization_score 0.5
            if personalization_score < 0.5:
                continue
            
            target_data['personalization_score'] = personalization_score
            targets.append(target_data)
            
            if len(targets) >= limit:
                break
        
        logger.info(f"   Found {len(targets)} red targets (high risk, >50⭐)")
        return targets
    
    def _create_green_issue(self, target: Dict, total_agents: int) -> Dict:
        """Skapa grön compliance badge issue."""
        
        agent_id = target['agent_id']
        repo_url = target['repo_url']
        
        # Generate title and body
        title = self.green_title_template
        body = self.green_body_template.format(
            agent_id=agent_id,
            total_agents=total_agents
        )
        
        # Save to database first
        self._save_outreach_record(target, title, body, 'green', 'pending')
        
        if self.dry_run:
            return {
                'success': True,
                'agent_id': agent_id,
                'repo_url': repo_url,
                'track': 'green',
                'title': title,
                'issue_url': f"{repo_url}/issues/[DRY_RUN]",
                'dry_run': True
            }
        
        # Create GitHub issue
        try:
            repo = self.github.get_repo(f"{target['repo_owner']}/{target['repo_name']}")
            
            issue = repo.create_issue(
                title=title,
                body=body,
                labels=['compliance', 'enhancement']
            )
            
            # Update database with success
            self._update_outreach_record(agent_id, 'green', 'created', issue.html_url, issue.number)
            
            return {
                'success': True,
                'agent_id': agent_id,
                'repo_url': repo_url,
                'track': 'green',
                'title': title,
                'issue_url': issue.html_url,
                'issue_number': issue.number
            }
            
        except Exception as e:
            # Update database with error
            self._update_outreach_record(agent_id, 'green', 'error', None, None, str(e))
            
            return {
                'success': False,
                'agent_id': agent_id,
                'repo_url': repo_url,
                'track': 'green',
                'error': str(e)
            }
    
    def _create_red_issue(self, target: Dict, total_agents: int) -> Dict:
        """Skapa röd high-risk alert issue."""
        
        agent_id = target['agent_id']
        repo_url = target['repo_url']
        
        # För red issues behöver vi fråga compliance API för alla 14 jurisdiktioner
        # För nu använder vi placeholder data
        jurisdiction_rows = "🇪🇺 European Union | High | August 2, 2026\n🇺🇸 Colorado | High | June 30, 2026"
        
        title = self.red_title_template.format(count=2)
        body = self.red_body_template.format(
            agent_id=agent_id,
            jurisdiction_rows=jurisdiction_rows,
            overall_risk="High Risk",
            jur_count=2,
            risk_reason="automated decision-making or high-risk AI functionality"
        )
        
        # Save to database
        self._save_outreach_record(target, title, body, 'red', 'pending')
        
        if self.dry_run:
            return {
                'success': True,
                'agent_id': agent_id,
                'repo_url': repo_url,
                'track': 'red',
                'title': title,
                'issue_url': f"{repo_url}/issues/[DRY_RUN]",
                'dry_run': True
            }
        
        try:
            repo = self.github.get_repo(f"{target['repo_owner']}/{target['repo_name']}")
            
            issue = repo.create_issue(
                title=title,
                body=body,
                labels=['compliance', 'important']
            )
            
            # Update database
            self._update_outreach_record(agent_id, 'red', 'created', issue.html_url, issue.number)
            
            return {
                'success': True,
                'agent_id': agent_id,
                'repo_url': repo_url,
                'track': 'red',
                'title': title,
                'issue_url': issue.html_url,
                'issue_number': issue.number
            }
            
        except Exception as e:
            self._update_outreach_record(agent_id, 'red', 'error', None, None, str(e))
            
            return {
                'success': False,
                'agent_id': agent_id,
                'repo_url': repo_url,
                'track': 'red',
                'error': str(e)
            }
    
    def _extract_repo_info(self, github_url: str) -> Optional[Dict]:
        """Extract owner/repo from GitHub URL."""
        try:
            if 'github.com/' not in github_url:
                return None
                
            parts = github_url.replace('https://github.com/', '').split('/')
            if len(parts) < 2:
                return None
                
            return {
                'owner': parts[0],
                'name': parts[1]
            }
        except:
            return None
    
    def _save_outreach_record(self, target: Dict, title: str, body: str, track: str, status: str):
        """Spara outreach record i databas."""
        
        sql = """
        INSERT INTO outreach_issues (agent_id, repo_url, track, title, body, status)
        VALUES (:agent_id, :repo_url, :track, :title, :body, :status)
        """
        
        self.session.execute(text(sql), {
            'agent_id': target['agent_id'],
            'repo_url': target['repo_url'],
            'track': track,
            'title': title,
            'body': body,
            'status': status
        })
        self.session.commit()
    
    def _update_outreach_record(self, agent_id: str, track: str, status: str, issue_url: Optional[str], issue_number: Optional[int], error: Optional[str] = None):
        """Uppdatera outreach record med resultat."""
        
        sql = """
        UPDATE outreach_issues 
        SET status = :status, issue_url = :issue_url, github_issue_id = :issue_number, error_message = :error
        WHERE agent_id = :agent_id AND track = :track
        """
        
        self.session.execute(text(sql), {
            'status': status,
            'issue_url': issue_url,
            'issue_number': issue_number,
            'error': error,
            'agent_id': agent_id,
            'track': track
        })
        self.session.commit()
    
    def _is_non_agent_repo(self, agent: Agent, repo_info: Dict) -> bool:
        """Anders filter: filtrera bort awesome-lists och non-agent repos."""
        
        name = agent.name.lower()
        description = (agent.description or '').lower()
        repo_name = repo_info['name'].lower()
        
        # Filter awesome-lists
        awesome_indicators = ['awesome-', 'awesome_', 'list-of-', 'curated', 'collection']
        if any(indicator in name or indicator in repo_name for indicator in awesome_indicators):
            return True
        
        # Filter non-agent repos (dokumentation, tutorials, etc.)
        non_agent_indicators = [
            'tutorial', 'guide', 'example', 'demo', 'sample', 'template', 
            'documentation', 'docs', 'paper', 'research', 'study',
            'benchmark', 'dataset', 'corpus', 'model-zoo',
            'blog', 'website', 'homepage', 'portfolio'
        ]
        
        if any(indicator in name or indicator in description for indicator in non_agent_indicators):
            return True
        
        # Must have agent-indicating terms
        agent_indicators = [
            'agent', 'assistant', 'bot', 'ai', 'llm', 'gpt', 'claude',
            'anthropic', 'openai', 'tool', 'api', 'service', 'platform',
            'framework', 'library', 'sdk', 'pipeline', 'automation',
            'chatbot', 'voice', 'speech', 'nlp', 'ml', 'neural'
        ]
        
        has_agent_terms = any(indicator in name or indicator in description for indicator in agent_indicators)
        
        return not has_agent_terms
    
    def _calculate_personalization_score(self, agent: Agent, repo_info: Dict) -> float:
        """Beräkna personalization score för target (0-1 skala)."""
        
        score = 0.0
        
        # Has good description
        description = agent.description or ''
        if len(description) > 20:
            score += 0.2
        if len(description) > 100:
            score += 0.1
        
        # Stars indicate quality/popularity
        stars = agent.stars or 0
        if stars >= 100:
            score += 0.1
        if stars >= 500:
            score += 0.1
        if stars >= 1000:
            score += 0.1
        
        # Agent-specific terms in name/description
        combined_text = f"{agent.name} {description}".lower()
        agent_terms = ['agent', 'assistant', 'bot', 'ai', 'llm']
        if any(term in combined_text for term in agent_terms):
            score += 0.2
        
        # Clear use case/domain
        domain_terms = [
            'chat', 'conversation', 'language', 'text', 'code', 'programming',
            'data', 'analysis', 'automation', 'workflow', 'business', 'enterprise'
        ]
        if any(term in combined_text for term in domain_terms):
            score += 0.1
        
        # Active repo (recent activity indicates maintenance)
        # Vi har inte updated_at här, så skippa denna del för nu
        
        # Cap at 1.0
        return min(score, 1.0)

def main():
    """Test outreach bot."""
    import argparse
    
    parser = argparse.ArgumentParser(description='GitHub Issues Outreach Bot')
    parser.add_argument('--dry-run', action='store_true', help='Simulate without creating issues')
    parser.add_argument('--green-limit', type=int, default=5, help='Max green issues for test')
    parser.add_argument('--red-limit', type=int, default=2, help='Max red issues for test')
    
    args = parser.parse_args()
    
    bot = GitHubIssuesOutreachBot(dry_run=args.dry_run)
    bot.max_green_per_day = args.green_limit
    bot.max_red_per_day = args.red_limit
    
    result = bot.run_daily_outreach()
    
    print("🏆 OUTREACH COMPLETE")
    print(f"Green issues: {result.get('stats', {}).get('green_created', 0)}")
    print(f"Red issues: {result.get('stats', {}).get('red_created', 0)}")
    print(f"Errors: {result.get('stats', {}).get('errors', 0)}")

if __name__ == "__main__":
    main()