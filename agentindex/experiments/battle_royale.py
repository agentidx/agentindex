"""
Agent Battle Royale - Community Voting System
Interactive feature where users vote on agent matchups
"""

import json
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import uuid


class BattleStatus(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    SCHEDULED = "scheduled"


@dataclass 
class Agent:
    """Agent participating in battles"""
    id: str
    name: str
    description: str
    category: str
    source: str
    url: str
    trust_score: Optional[float]
    stars: Optional[int]
    downloads: Optional[int]
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Battle:
    """Individual battle between two agents"""
    id: str
    agent_a: Agent
    agent_b: Agent
    category: str
    votes_a: int
    votes_b: int
    total_votes: int
    status: BattleStatus
    created_at: datetime
    ends_at: datetime
    battle_prompt: str
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "agent_a": self.agent_a.to_dict(),
            "agent_b": self.agent_b.to_dict(),
            "category": self.category,
            "votes_a": self.votes_a,
            "votes_b": self.votes_b, 
            "total_votes": self.total_votes,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "ends_at": self.ends_at.isoformat(),
            "battle_prompt": self.battle_prompt,
            "winner": self.get_winner(),
            "vote_percentage_a": self.get_vote_percentage_a(),
            "vote_percentage_b": self.get_vote_percentage_b()
        }
    
    def get_winner(self) -> Optional[str]:
        """Get the winning agent ID"""
        if self.status != BattleStatus.COMPLETED:
            return None
        
        if self.votes_a > self.votes_b:
            return self.agent_a.id
        elif self.votes_b > self.votes_a:
            return self.agent_b.id
        else:
            return "tie"
    
    def get_vote_percentage_a(self) -> float:
        """Get vote percentage for agent A"""
        if self.total_votes == 0:
            return 0.0
        return round((self.votes_a / self.total_votes) * 100, 1)
    
    def get_vote_percentage_b(self) -> float:
        """Get vote percentage for agent B"""
        if self.total_votes == 0:
            return 0.0
        return round((self.votes_b / self.total_votes) * 100, 1)


class BattleRoyaleSystem:
    """Manages the agent battle royale system"""
    
    def __init__(self, data_file: str = "battle_royale_data.json"):
        self.data_file = data_file
        self.battles: List[Battle] = []
        self.agents: List[Agent] = []
        self.battle_prompts = [
            "Which agent would you choose for a critical production system?",
            "Which agent has better documentation and ease of use?",
            "Which agent would you trust with sensitive data processing?", 
            "Which agent has a more active development community?",
            "Which agent offers better performance and reliability?",
            "Which agent would you recommend to a beginner?",
            "Which agent has more innovative features?",
            "Which agent would scale better for enterprise use?"
        ]
        self.load_data()
    
    def load_data(self):
        """Load battles and agents from storage"""
        try:
            with open(self.data_file, 'r') as f:
                data = json.load(f)
                
            # Load agents
            for agent_data in data.get("agents", []):
                agent = Agent(**agent_data)
                self.agents.append(agent)
            
            # Load battles
            for battle_data in data.get("battles", []):
                battle = Battle(
                    id=battle_data["id"],
                    agent_a=Agent(**battle_data["agent_a"]),
                    agent_b=Agent(**battle_data["agent_b"]),
                    category=battle_data["category"],
                    votes_a=battle_data["votes_a"],
                    votes_b=battle_data["votes_b"],
                    total_votes=battle_data["total_votes"],
                    status=BattleStatus(battle_data["status"]),
                    created_at=datetime.fromisoformat(battle_data["created_at"]),
                    ends_at=datetime.fromisoformat(battle_data["ends_at"]),
                    battle_prompt=battle_data["battle_prompt"]
                )
                self.battles.append(battle)
                
        except FileNotFoundError:
            # Initialize with empty data
            pass
    
    def save_data(self):
        """Save battles and agents to storage"""
        data = {
            "agents": [agent.to_dict() for agent in self.agents],
            "battles": [battle.to_dict() for battle in self.battles],
            "last_updated": datetime.utcnow().isoformat()
        }
        
        with open(self.data_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_agent(self, agent: Agent):
        """Add an agent to the battle pool"""
        # Check if agent already exists
        existing = next((a for a in self.agents if a.id == agent.id), None)
        if not existing:
            self.agents.append(agent)
            self.save_data()
    
    def create_battle(
        self, 
        category: Optional[str] = None,
        duration_hours: int = 24
    ) -> Battle:
        """Create a new battle between two random agents"""
        
        # Filter agents by category if specified
        available_agents = self.agents
        if category:
            available_agents = [a for a in self.agents if a.category == category]
        
        if len(available_agents) < 2:
            raise ValueError("Not enough agents available for battle")
        
        # Select two random agents
        agent_a, agent_b = random.sample(available_agents, 2)
        
        # Create battle
        battle = Battle(
            id=str(uuid.uuid4()),
            agent_a=agent_a,
            agent_b=agent_b,
            category=category or "general",
            votes_a=0,
            votes_b=0,
            total_votes=0,
            status=BattleStatus.ACTIVE,
            created_at=datetime.utcnow(),
            ends_at=datetime.utcnow() + timedelta(hours=duration_hours),
            battle_prompt=random.choice(self.battle_prompts)
        )
        
        self.battles.append(battle)
        self.save_data()
        return battle
    
    def vote(self, battle_id: str, agent_id: str, voter_ip: Optional[str] = None) -> bool:
        """Cast a vote in a battle"""
        
        battle = next((b for b in self.battles if b.id == battle_id), None)
        if not battle:
            raise ValueError("Battle not found")
        
        if battle.status != BattleStatus.ACTIVE:
            raise ValueError("Battle is not active")
        
        if datetime.utcnow() > battle.ends_at:
            self._complete_battle(battle)
            raise ValueError("Battle has ended")
        
        # Cast vote
        if agent_id == battle.agent_a.id:
            battle.votes_a += 1
        elif agent_id == battle.agent_b.id:
            battle.votes_b += 1
        else:
            raise ValueError("Invalid agent ID")
        
        battle.total_votes += 1
        self.save_data()
        return True
    
    def _complete_battle(self, battle: Battle):
        """Complete a battle and determine winner"""
        battle.status = BattleStatus.COMPLETED
        self.save_data()
    
    def get_active_battles(self) -> List[Battle]:
        """Get all active battles"""
        # Check for expired battles
        now = datetime.utcnow()
        for battle in self.battles:
            if battle.status == BattleStatus.ACTIVE and now > battle.ends_at:
                self._complete_battle(battle)
        
        return [b for b in self.battles if b.status == BattleStatus.ACTIVE]
    
    def get_completed_battles(self, limit: int = 20) -> List[Battle]:
        """Get completed battles"""
        completed = [b for b in self.battles if b.status == BattleStatus.COMPLETED]
        completed.sort(key=lambda x: x.created_at, reverse=True)
        return completed[:limit]
    
    def get_battle_by_id(self, battle_id: str) -> Optional[Battle]:
        """Get a specific battle"""
        return next((b for b in self.battles if b.id == battle_id), None)
    
    def get_leaderboard(self, limit: int = 20) -> List[Dict]:
        """Get agent leaderboard based on battle wins"""
        
        wins = {}
        losses = {}
        total_votes = {}
        
        # Count wins, losses, and total votes for each agent
        for battle in self.battles:
            if battle.status != BattleStatus.COMPLETED:
                continue
                
            winner = battle.get_winner()
            
            # Initialize counts
            for agent in [battle.agent_a, battle.agent_b]:
                if agent.id not in wins:
                    wins[agent.id] = 0
                    losses[agent.id] = 0
                    total_votes[agent.id] = 0
            
            # Count votes
            total_votes[battle.agent_a.id] += battle.votes_a
            total_votes[battle.agent_b.id] += battle.votes_b
            
            # Count wins/losses
            if winner == battle.agent_a.id:
                wins[battle.agent_a.id] += 1
                losses[battle.agent_b.id] += 1
            elif winner == battle.agent_b.id:
                wins[battle.agent_b.id] += 1
                losses[battle.agent_a.id] += 1
            # Ties don't count as wins or losses
        
        # Create leaderboard entries
        leaderboard = []
        for agent in self.agents:
            if agent.id in wins:
                win_count = wins[agent.id]
                loss_count = losses[agent.id]
                total_battles = win_count + loss_count
                win_rate = (win_count / total_battles) * 100 if total_battles > 0 else 0
                
                leaderboard.append({
                    "agent": agent.to_dict(),
                    "wins": win_count,
                    "losses": loss_count,
                    "win_rate": round(win_rate, 1),
                    "total_votes": total_votes.get(agent.id, 0),
                    "battle_score": win_count * 3 + total_votes.get(agent.id, 0) * 0.1
                })
        
        # Sort by battle score (wins weighted more than vote count)
        leaderboard.sort(key=lambda x: x["battle_score"], reverse=True)
        return leaderboard[:limit]
    
    def get_stats(self) -> Dict:
        """Get overall battle royale statistics"""
        active_battles = len(self.get_active_battles())
        completed_battles = len([b for b in self.battles if b.status == BattleStatus.COMPLETED])
        total_votes = sum(b.total_votes for b in self.battles)
        
        categories = list(set(a.category for a in self.agents))
        
        return {
            "total_agents": len(self.agents),
            "active_battles": active_battles,
            "completed_battles": completed_battles,
            "total_votes": total_votes,
            "categories": categories,
            "avg_votes_per_battle": round(total_votes / len(self.battles), 1) if self.battles else 0
        }
    
    def seed_with_sample_agents(self):
        """Seed the system with sample agents for testing"""
        
        sample_agents = [
            Agent(
                id="agent-1",
                name="WebScrapeMaster",
                description="Advanced web scraping tool with JavaScript support",
                category="web-scraping", 
                source="github",
                url="https://github.com/example/webscrapemaster",
                trust_score=85.0,
                stars=1250,
                downloads=15000
            ),
            Agent(
                id="agent-2", 
                name="DataCleaner Pro",
                description="Professional data cleaning and preprocessing toolkit",
                category="data-analysis",
                source="pypi",
                url="https://pypi.org/project/datacleaner-pro",
                trust_score=92.0,
                stars=890,
                downloads=25000
            ),
            Agent(
                id="agent-3",
                name="ScrapingSpider",
                description="Fast and efficient web scraping framework",
                category="web-scraping",
                source="github", 
                url="https://github.com/example/scrapingspider",
                trust_score=78.0,
                stars=2100,
                downloads=8000
            ),
            Agent(
                id="agent-4",
                name="AnalyticsBot",
                description="Automated analytics and reporting agent",
                category="data-analysis",
                source="npm",
                url="https://npmjs.com/package/analyticsbot",
                trust_score=81.0,
                stars=567,
                downloads=12000
            )
        ]
        
        for agent in sample_agents:
            self.add_agent(agent)


# Web interface HTML template
BATTLE_ROYALE_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>🥊 Agent Battle Royale</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
        .header { text-align: center; margin-bottom: 30px; }
        .battle-card { background: white; border-radius: 10px; padding: 20px; margin: 20px 0; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .agents { display: flex; justify-content: space-between; margin: 20px 0; }
        .agent { flex: 1; text-align: center; padding: 15px; border: 2px solid #ddd; border-radius: 8px; margin: 0 10px; }
        .agent:hover { border-color: #007cba; cursor: pointer; }
        .agent.selected { border-color: #007cba; background: #f0f8ff; }
        .vs { text-align: center; font-size: 24px; font-weight: bold; color: #666; margin: 0 20px; align-self: center; }
        .vote-button { background: #007cba; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-size: 16px; }
        .vote-button:hover { background: #005a8a; }
        .vote-button:disabled { background: #ccc; cursor: not-allowed; }
        .results { margin-top: 15px; }
        .vote-bar { height: 20px; background: #ddd; border-radius: 10px; margin: 5px 0; overflow: hidden; }
        .vote-fill { height: 100%; background: #007cba; transition: width 0.3s ease; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
        .stat-card { background: white; padding: 15px; border-radius: 8px; text-align: center; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .leaderboard { background: white; border-radius: 10px; padding: 20px; margin: 20px 0; }
        .leaderboard table { width: 100%; border-collapse: collapse; }
        .leaderboard th, .leaderboard td { padding: 10px; text-align: left; border-bottom: 1px solid #eee; }
        .leaderboard th { background: #f8f9fa; font-weight: bold; }
        .medal { font-size: 20px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🥊 Agent Battle Royale</h1>
        <p>Vote for the best AI agents in head-to-head battles!</p>
    </div>
    
    <div class="stats">
        <div class="stat-card">
            <h3>{{total_agents}}</h3>
            <p>Total Agents</p>
        </div>
        <div class="stat-card">
            <h3>{{active_battles}}</h3>
            <p>Active Battles</p>
        </div>
        <div class="stat-card">
            <h3>{{total_votes}}</h3>
            <p>Total Votes</p>
        </div>
        <div class="stat-card">
            <h3>{{completed_battles}}</h3>
            <p>Completed Battles</p>
        </div>
    </div>
    
    <div id="active-battles">
        <!-- Active battles will be inserted here -->
    </div>
    
    <div class="leaderboard">
        <h2>🏆 Leaderboard</h2>
        <table>
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Agent</th>
                    <th>Wins</th>
                    <th>Win Rate</th>
                    <th>Total Votes</th>
                </tr>
            </thead>
            <tbody id="leaderboard-body">
                <!-- Leaderboard will be inserted here -->
            </tbody>
        </table>
    </div>
    
    <script>
        // JavaScript for interactive voting will go here
        function vote(battleId, agentId) {
            fetch('/api/vote', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({battle_id: battleId, agent_id: agentId})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    location.reload(); // Refresh to show updated results
                } else {
                    alert('Vote failed: ' + data.error);
                }
            });
        }
        
        function selectAgent(battleId, agentId) {
            document.querySelectorAll(`[data-battle="${battleId}"] .agent`).forEach(el => {
                el.classList.remove('selected');
            });
            document.querySelector(`[data-battle="${battleId}"] [data-agent="${agentId}"]`).classList.add('selected');
            document.querySelector(`[data-battle="${battleId}"] .vote-button`).disabled = false;
        }
    </script>
</body>
</html>
'''


if __name__ == "__main__":
    # Demo the battle royale system
    battle_system = BattleRoyaleSystem()
    
    # Seed with sample data
    battle_system.seed_with_sample_agents()
    
    # Create some battles
    battle1 = battle_system.create_battle(category="web-scraping")
    battle2 = battle_system.create_battle(category="data-analysis")
    
    print(f"🥊 Created battles:")
    print(f"  Battle 1: {battle1.agent_a.name} vs {battle1.agent_b.name}")
    print(f"  Battle 2: {battle2.agent_a.name} vs {battle2.agent_b.name}")
    
    # Cast some votes
    battle_system.vote(battle1.id, battle1.agent_a.id)
    battle_system.vote(battle1.id, battle1.agent_b.id)
    battle_system.vote(battle1.id, battle1.agent_a.id)
    
    print(f"\\n📊 Stats: {battle_system.get_stats()}")
    print(f"\\n🏆 Leaderboard:")
    for i, entry in enumerate(battle_system.get_leaderboard(5), 1):
        print(f"  {i}. {entry['agent']['name']} - {entry['wins']} wins ({entry['win_rate']}%)")