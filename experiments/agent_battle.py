"""
Agent Battle Royale - Experimental Feature
Head-to-head comparison of agents in same category with voting
"""

import asyncio
import asyncpg
import random
from typing import List, Dict, Any, Optional
from datetime import datetime
import json


class AgentBattleArena:
    """Handles agent vs agent comparisons with community voting"""
    
    def __init__(self, db_url: str = "postgresql://anstudio@localhost/agentindex"):
        self.db_url = db_url
    
    async def create_battle(self, category: str = None) -> Dict[str, Any]:
        """Create a new agent battle in specified category"""
        
        conn = await asyncpg.connect(self.db_url)
        
        try:
            # Get two random high-quality agents from same category
            query = """
                SELECT id, name, description, source_url, source, 
                       quality_score, stars, downloads, category
                FROM agents 
                WHERE is_active = true 
                AND quality_score > 50
            """
            
            params = []
            if category:
                query += " AND category = $1"
                params.append(category)
            
            query += " ORDER BY RANDOM() LIMIT 2"
            
            agents = await conn.fetch(query, *params)
            
            if len(agents) < 2:
                raise ValueError("Not enough agents found for battle")
            
            agent1, agent2 = agents[0], agents[1]
            
            # Create battle record
            battle_id = await conn.fetchval("""
                INSERT INTO agent_battles (agent1_id, agent2_id, category, created_at)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """, agent1['id'], agent2['id'], category, datetime.utcnow())
            
            battle = {
                "battle_id": str(battle_id),
                "category": category or "mixed",
                "created_at": datetime.utcnow().isoformat(),
                "agent1": dict(agent1),
                "agent2": dict(agent2),
                "votes": {"agent1": 0, "agent2": 0},
                "status": "active"
            }
            
            return battle
            
        except asyncpg.UndefinedTableError:
            # Create battles table if it doesn't exist
            await self._create_battles_table(conn)
            return await self.create_battle(category)
            
        finally:
            await conn.close()
    
    async def _create_battles_table(self, conn: asyncpg.Connection):
        """Create agent battles table for experiment tracking"""
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_battles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                agent1_id UUID REFERENCES agents(id),
                agent2_id UUID REFERENCES agents(id),
                category TEXT,
                agent1_votes INTEGER DEFAULT 0,
                agent2_votes INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE,
                ended_at TIMESTAMP WITH TIME ZONE,
                winner_id UUID
            )
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_battles_category 
            ON agent_battles(category) WHERE ended_at IS NULL
        """)
    
    async def cast_vote(self, battle_id: str, vote_for: str, voter_id: Optional[str] = None) -> Dict[str, Any]:
        """Cast a vote in an active battle"""
        
        conn = await asyncpg.connect(self.db_url)
        
        try:
            # Update vote count
            if vote_for == "agent1":
                await conn.execute("""
                    UPDATE agent_battles 
                    SET agent1_votes = agent1_votes + 1
                    WHERE id = $1 AND ended_at IS NULL
                """, battle_id)
            elif vote_for == "agent2":
                await conn.execute("""
                    UPDATE agent_battles 
                    SET agent2_votes = agent2_votes + 1
                    WHERE id = $1 AND ended_at IS NULL
                """, battle_id)
            
            # Get updated battle state
            battle = await conn.fetchrow("""
                SELECT *, 
                       a1.name as agent1_name, a1.description as agent1_desc,
                       a2.name as agent2_name, a2.description as agent2_desc
                FROM agent_battles b
                JOIN agents a1 ON b.agent1_id = a1.id
                JOIN agents a2 ON b.agent2_id = a2.id
                WHERE b.id = $1
            """, battle_id)
            
            if not battle:
                raise ValueError("Battle not found or already ended")
            
            # Check if battle should end (after 10 votes or 24 hours)
            total_votes = battle['agent1_votes'] + battle['agent2_votes']
            time_elapsed = datetime.utcnow() - battle['created_at']
            
            if total_votes >= 10 or time_elapsed.days >= 1:
                winner_id = (battle['agent1_id'] if battle['agent1_votes'] > battle['agent2_votes'] 
                           else battle['agent2_id'])
                
                await conn.execute("""
                    UPDATE agent_battles 
                    SET ended_at = $1, winner_id = $2
                    WHERE id = $3
                """, datetime.utcnow(), winner_id, battle_id)
            
            return {
                "battle_id": str(battle['id']),
                "votes": {
                    "agent1": battle['agent1_votes'],
                    "agent2": battle['agent2_votes']
                },
                "total_votes": total_votes,
                "status": "ended" if total_votes >= 10 or time_elapsed.days >= 1 else "active"
            }
            
        finally:
            await conn.close()
    
    async def get_battle_leaderboard(self, category: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top agents by battle wins"""
        
        conn = await asyncpg.connect(self.db_url)
        
        try:
            query = """
                SELECT a.name, a.source, a.category, a.quality_score,
                       COUNT(*) as battle_wins,
                       AVG(CASE 
                           WHEN b.agent1_id = a.id THEN b.agent1_votes::float / (b.agent1_votes + b.agent2_votes)
                           ELSE b.agent2_votes::float / (b.agent1_votes + b.agent2_votes)
                       END) as avg_vote_share
                FROM agents a
                JOIN agent_battles b ON (a.id = b.winner_id)
                WHERE b.ended_at IS NOT NULL
            """
            
            params = []
            if category:
                query += " AND b.category = $1"
                params.append(category)
            
            query += """
                GROUP BY a.id, a.name, a.source, a.category, a.quality_score
                ORDER BY battle_wins DESC, avg_vote_share DESC
                LIMIT ${}
            """.format(len(params) + 1)
            
            params.append(limit)
            
            results = await conn.fetch(query, *params)
            return [dict(row) for row in results]
            
        finally:
            await conn.close()


class BattleWebInterface:
    """Simple web interface for agent battles"""
    
    def generate_battle_html(self, battle: Dict[str, Any]) -> str:
        """Generate HTML for a battle"""
        
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Agent Battle: {battle['agent1']['name']} vs {battle['agent2']['name']}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: #f5f7fa; }}
        .battle-arena {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 12px; padding: 30px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .vs-header {{ text-align: center; margin-bottom: 30px; }}
        .vs-title {{ font-size: 2em; color: #2563eb; margin-bottom: 10px; }}
        .category-badge {{ background: #10b981; color: white; padding: 4px 12px; border-radius: 16px; font-size: 0.9em; }}
        .fighters {{ display: grid; grid-template-columns: 1fr auto 1fr; gap: 20px; align-items: center; }}
        .fighter {{ background: #f8fafc; padding: 20px; border-radius: 8px; text-align: center; border: 2px solid #e2e8f0; transition: all 0.3s; }}
        .fighter:hover {{ border-color: #2563eb; transform: translateY(-2px); }}
        .fighter-name {{ font-size: 1.3em; font-weight: bold; margin-bottom: 10px; color: #1e293b; }}
        .fighter-desc {{ color: #64748b; margin-bottom: 15px; font-size: 0.9em; }}
        .fighter-stats {{ display: flex; justify-content: center; gap: 15px; margin-bottom: 15px; }}
        .stat {{ background: white; padding: 8px 12px; border-radius: 6px; font-size: 0.8em; }}
        .vote-btn {{ background: #2563eb; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: bold; }}
        .vote-btn:hover {{ background: #1d4ed8; }}
        .vs-divider {{ font-size: 2em; color: #dc2626; font-weight: bold; }}
        .vote-count {{ text-align: center; margin: 20px 0; }}
        .progress-bar {{ background: #e5e7eb; border-radius: 10px; height: 8px; margin: 10px 0; }}
        .progress-fill {{ background: #2563eb; height: 100%; border-radius: 10px; transition: width 0.3s; }}
    </style>
</head>
<body>
    <div class="battle-arena">
        <div class="vs-header">
            <h1 class="vs-title">⚔️ Agent Battle Royale</h1>
            <div class="category-badge">{battle['category']}</div>
        </div>
        
        <div class="fighters">
            <div class="fighter" onclick="vote('agent1')">
                <div class="fighter-name">{battle['agent1']['name']}</div>
                <div class="fighter-desc">{battle['agent1']['description'][:100]}...</div>
                <div class="fighter-stats">
                    <div class="stat">⭐ {battle['agent1'].get('stars', 0):,}</div>
                    <div class="stat">📊 {battle['agent1'].get('quality_score', 0):.1f}/100</div>
                    <div class="stat">{battle['agent1']['source']}</div>
                </div>
                <button class="vote-btn">Vote for {battle['agent1']['name']}</button>
                <div class="vote-count">{battle['votes']['agent1']} votes</div>
            </div>
            
            <div class="vs-divider">VS</div>
            
            <div class="fighter" onclick="vote('agent2')">
                <div class="fighter-name">{battle['agent2']['name']}</div>
                <div class="fighter-desc">{battle['agent2']['description'][:100]}...</div>
                <div class="fighter-stats">
                    <div class="stat">⭐ {battle['agent2'].get('stars', 0):,}</div>
                    <div class="stat">📊 {battle['agent2'].get('quality_score', 0):.1f}/100</div>
                    <div class="stat">{battle['agent2']['source']}</div>
                </div>
                <button class="vote-btn">Vote for {battle['agent2']['name']}</button>
                <div class="vote-count">{battle['votes']['agent2']} votes</div>
            </div>
        </div>
        
        <div style="text-align: center; margin-top: 30px;">
            <p>🔥 <strong>Agent Battle Royale</strong> - Community-driven agent discovery</p>
            <p><a href="/battle/new">Start New Battle</a> | <a href="/battle/leaderboard">View Leaderboard</a></p>
            <p><small>Powered by <a href="https://agentcrawl.dev">AgentIndex</a></small></p>
        </div>
    </div>
    
    <script>
        async function vote(agent) {{
            try {{
                const response = await fetch('/battle/{battle['battle_id']}/vote', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ vote_for: agent }})
                }});
                
                if (response.ok) {{
                    location.reload();
                }}
            }} catch (error) {{
                console.error('Vote failed:', error);
            }}
        }}
    </script>
</body>
</html>
        """


if __name__ == "__main__":
    async def test_battle_system():
        arena = AgentBattleArena()
        
        print("🎮 Creating agent battle...")
        try:
            battle = await arena.create_battle(category="coding")
            print(f"⚔️ Battle created: {battle['agent1']['name']} vs {battle['agent2']['name']}")
            print(f"🏷️ Category: {battle['category']}")
            
            # Generate HTML
            web = BattleWebInterface()
            html = web.generate_battle_html(battle)
            
            with open("battle_demo.html", "w") as f:
                f.write(html)
            print("📄 Battle HTML demo saved to battle_demo.html")
            
        except Exception as e:
            print(f"❌ Battle creation failed: {e}")
            print("Note: This experiment requires database setup")
    
    asyncio.run(test_battle_system())