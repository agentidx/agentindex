#!/usr/bin/env python3
"""
Autonomous Marketing Safety System
Implements industry best practices with automatic monitoring, pause triggers, and escalation
"""

import json
import sqlite3
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import os

@dataclass
class MarketingPost:
    platform: str
    content: str
    post_type: str
    target_audience: str
    timestamp: datetime
    approval_tier: int  # 1=auto, 2=monitored, 3=manual

class MarketingSafetySystem:
    def __init__(self):
        self.db_path = os.path.expanduser("~/agentindex/marketing_safety.db")
        self.init_database()
        
        # HARD SECURITY RULES - ALWAYS FORBIDDEN (from Anders)
        self.ALWAYS_FORBIDDEN = [
            "personal_info_anders", "personal_info_team", "team_personal_details",
            "internal_strategy", "internal_strategies", "competitive_strategy", "konkurrensinfo",
            "financial_info", "financial_details", "revenue", "funding", "costs", "budget_details",
            "money", "pricing_internal", "acquisition", "valuation"
        ]
        
        # Additional safety topics  
        self.FORBIDDEN_TOPICS = self.ALWAYS_FORBIDDEN + [
            "competitor_criticism", "unannounced_features", "user_data",
            "lawsuit", "controversy", "private_data"
        ]
        
        self.APPROVAL_REQUIRED_KEYWORDS = [
            "acquisition", "funding", "partnership", "enterprise",
            "lawsuit", "controversy", "outage", "security", "pricing"
        ]
        
        self.PLATFORM_LIMITS = {
            "reddit": {"posts_per_day": 3, "posts_per_subreddit_week": 1},
            "twitter": {"posts_per_day": 5, "posts_per_hour": 2},
            "linkedin": {"posts_per_week": 5, "posts_per_day": 2},
            "github": {"updates_per_day": 10, "issues_per_day": 5}
        }
        
        # Circuit breaker thresholds
        self.CIRCUIT_BREAKERS = {
            "daily_post_limit": 5,
            "min_engagement_rate": 0.10,
            "max_negative_sentiment": 0.40,
            "max_failed_posts": 3
        }
    
    def init_database(self):
        """Initialize marketing safety database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS marketing_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                platform VARCHAR(50),
                post_type VARCHAR(50),
                content_preview TEXT,
                approval_tier INTEGER,
                safety_score REAL,
                status VARCHAR(20),  -- approved, rejected, posted, failed
                engagement_rate REAL,
                sentiment_score REAL,
                notes TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS safety_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                alert_type VARCHAR(50),
                severity VARCHAR(20),  -- low, medium, high, critical
                message TEXT,
                resolved BOOLEAN DEFAULT FALSE,
                action_taken TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS platform_quotas (
                platform VARCHAR(50),
                date DATE,
                posts_count INTEGER DEFAULT 0,
                engagement_avg REAL DEFAULT 0,
                last_post_time DATETIME,
                PRIMARY KEY (platform, date)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def analyze_content_safety(self, content: str, platform: str, post_type: str) -> Dict:
        """Analyze content for safety and determine approval tier"""
        
        safety_score = 1.0
        warnings = []
        approval_tier = 1  # Default: auto-approved
        
        content_lower = content.lower()
        
        # HARD CHECK: Always forbidden topics (from Anders)
        personal_triggers = ["anders", "team member", "personal", "private", "family", "address", "phone"]
        financial_triggers = ["cost us", "spend", "budget", "revenue", "profit", "funding", "investment", "money"]
        strategy_triggers = ["internal strategy", "competitive advantage", "secret", "confidential", "proprietary"]
        
        for trigger in personal_triggers:
            if trigger in content_lower:
                safety_score = 0.0
                approval_tier = 3
                warnings.append(f"🚨 FORBIDDEN: Contains personal information trigger: {trigger}")
        
        for trigger in financial_triggers:
            if trigger in content_lower:
                safety_score = 0.0  
                approval_tier = 3
                warnings.append(f"🚨 FORBIDDEN: Contains financial information trigger: {trigger}")
                
        for trigger in strategy_triggers:
            if trigger in content_lower:
                safety_score = 0.0
                approval_tier = 3  
                warnings.append(f"🚨 FORBIDDEN: Contains internal strategy trigger: {trigger}")
        
        # Check for general forbidden topics
        for topic in self.FORBIDDEN_TOPICS:
            if topic.replace("_", " ") in content_lower:
                safety_score = 0.0
                approval_tier = 3  # Requires manual approval
                warnings.append(f"Contains forbidden topic: {topic}")
        
        # Check for keywords requiring approval
        for keyword in self.APPROVAL_REQUIRED_KEYWORDS:
            if keyword in content_lower:
                approval_tier = max(approval_tier, 3)
                safety_score *= 0.7
                warnings.append(f"Contains sensitive keyword: {keyword}")
        
        # Platform-specific content analysis
        if platform == "reddit":
            if len(content) > 10000:
                warnings.append("Content very long for Reddit")
                safety_score *= 0.9
            
            # Check for promotional language that might be spam
            promo_words = ["buy", "purchase", "discount", "limited time"]
            promo_count = sum(1 for word in promo_words if word in content_lower)
            if promo_count > 2:
                approval_tier = max(approval_tier, 2)
                warnings.append("High promotional language detected")
        
        # Technical accuracy check (basic)
        tech_claims = ["40,000+ agents", "sub-100ms", "trust scoring", "semantic search"]
        inaccurate_claims = []
        for claim in tech_claims:
            if claim.lower() in content_lower:
                # These are accurate for AgentIndex
                continue
        
        return {
            "safety_score": safety_score,
            "approval_tier": approval_tier,
            "warnings": warnings,
            "safe_to_post": approval_tier <= 1 and safety_score >= 0.8,
            "requires_review": approval_tier == 2,
            "blocked": approval_tier >= 3 or safety_score < 0.5
        }
    
    def check_platform_quotas(self, platform: str) -> Dict:
        """Check if platform posting quotas are within limits"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Get today's stats
        cursor.execute("""
            SELECT posts_count, engagement_avg, last_post_time 
            FROM platform_quotas 
            WHERE platform = ? AND date = ?
        """, (platform, today))
        
        result = cursor.fetchone()
        
        if result:
            posts_today, engagement_avg, last_post = result
            last_post_time = datetime.fromisoformat(last_post) if last_post else None
        else:
            posts_today = 0
            engagement_avg = 0
            last_post_time = None
        
        limits = self.PLATFORM_LIMITS.get(platform, {"posts_per_day": 3})
        max_posts = limits.get("posts_per_day", 3)
        
        # Check time since last post (minimum 1 hour between posts)
        time_since_last = None
        if last_post_time:
            time_since_last = (datetime.now() - last_post_time).total_seconds() / 3600
        
        conn.close()
        
        return {
            "posts_today": posts_today,
            "max_posts": max_posts,
            "quota_available": posts_today < max_posts,
            "engagement_avg": engagement_avg,
            "time_since_last_hours": time_since_last,
            "cooldown_ok": time_since_last is None or time_since_last >= 1.0
        }
    
    def update_platform_quota(self, platform: str, engagement_rate: float = None):
        """Update platform quota after posting"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().strftime('%Y-%m-%d')
        now = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT OR REPLACE INTO platform_quotas 
            (platform, date, posts_count, engagement_avg, last_post_time)
            VALUES (
                ?, ?, 
                COALESCE((SELECT posts_count FROM platform_quotas WHERE platform = ? AND date = ?), 0) + 1,
                COALESCE(?, (SELECT engagement_avg FROM platform_quotas WHERE platform = ? AND date = ?), 0),
                ?
            )
        """, (platform, today, platform, today, engagement_rate, platform, today, now))
        
        conn.commit()
        conn.close()
    
    def check_circuit_breakers(self) -> Dict:
        """Check if any circuit breakers should trigger"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Check daily post limit across all platforms
        cursor.execute("""
            SELECT SUM(posts_count) FROM platform_quotas WHERE date = ?
        """, (today,))
        
        total_posts_today = cursor.fetchone()[0] or 0
        
        # Check recent engagement rates
        cursor.execute("""
            SELECT AVG(engagement_rate) FROM marketing_posts 
            WHERE DATE(timestamp) >= ? AND engagement_rate IS NOT NULL
        """, (today,))
        
        avg_engagement = cursor.fetchone()[0] or 0.5  # Default if no data
        
        # Check recent failures
        cursor.execute("""
            SELECT COUNT(*) FROM marketing_posts 
            WHERE DATE(timestamp) = ? AND status = 'failed'
        """, (today,))
        
        failed_posts = cursor.fetchone()[0] or 0
        
        conn.close()
        
        # Evaluate circuit breakers
        breakers_triggered = []
        
        if total_posts_today >= self.CIRCUIT_BREAKERS["daily_post_limit"]:
            breakers_triggered.append("daily_post_limit")
        
        if avg_engagement < self.CIRCUIT_BREAKERS["min_engagement_rate"]:
            breakers_triggered.append("low_engagement")
        
        if failed_posts >= self.CIRCUIT_BREAKERS["max_failed_posts"]:
            breakers_triggered.append("high_failure_rate")
        
        return {
            "total_posts_today": total_posts_today,
            "avg_engagement": avg_engagement,
            "failed_posts": failed_posts,
            "breakers_triggered": breakers_triggered,
            "system_paused": len(breakers_triggered) > 0
        }
    
    def log_safety_alert(self, alert_type: str, severity: str, message: str):
        """Log safety alert for monitoring"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO safety_alerts (alert_type, severity, message)
            VALUES (?, ?, ?)
        """, (alert_type, severity, message))
        
        conn.commit()
        conn.close()
        
        print(f"🚨 SAFETY ALERT ({severity}): {message}")
    
    def evaluate_marketing_request(self, content: str, platform: str, post_type: str) -> Dict:
        """Main evaluation function for marketing requests"""
        
        # Step 1: Content safety analysis
        safety_analysis = self.analyze_content_safety(content, platform, post_type)
        
        # Step 2: Platform quota check
        quota_status = self.check_platform_quotas(platform)
        
        # Step 3: Circuit breaker check
        circuit_status = self.check_circuit_breakers()
        
        # Step 4: Final decision
        can_post = (
            safety_analysis["safe_to_post"] and
            quota_status["quota_available"] and
            quota_status["cooldown_ok"] and
            not circuit_status["system_paused"]
        )
        
        decision = {
            "approved": can_post,
            "approval_tier": safety_analysis["approval_tier"],
            "safety_score": safety_analysis["safety_score"],
            "platform": platform,
            "post_type": post_type,
            "warnings": safety_analysis["warnings"],
            "quota_status": quota_status,
            "circuit_status": circuit_status,
            "timestamp": datetime.now().isoformat()
        }
        
        # Log potential issues
        if safety_analysis["blocked"]:
            self.log_safety_alert("content_blocked", "high", f"Content blocked for {platform}: {safety_analysis['warnings']}")
        
        if not quota_status["quota_available"]:
            self.log_safety_alert("quota_exceeded", "medium", f"Daily quota exceeded for {platform}")
        
        if circuit_status["system_paused"]:
            self.log_safety_alert("circuit_breaker", "high", f"System paused: {circuit_status['breakers_triggered']}")
        
        return decision
    
    def get_safety_dashboard_data(self) -> Dict:
        """Get data for safety monitoring dashboard"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Daily stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total_posts,
                SUM(CASE WHEN status = 'posted' THEN 1 ELSE 0 END) as successful_posts,
                AVG(engagement_rate) as avg_engagement,
                AVG(safety_score) as avg_safety_score
            FROM marketing_posts 
            WHERE DATE(timestamp) = ?
        """, (today,))
        
        daily_stats = cursor.fetchone()
        
        # Platform breakdown
        cursor.execute("""
            SELECT platform, COUNT(*) as posts, AVG(engagement_rate) as engagement
            FROM marketing_posts 
            WHERE DATE(timestamp) >= ?
            GROUP BY platform
        """, (today,))
        
        platform_stats = cursor.fetchall()
        
        # Recent alerts
        cursor.execute("""
            SELECT alert_type, severity, message, timestamp
            FROM safety_alerts 
            WHERE DATE(timestamp) >= ?
            ORDER BY timestamp DESC
            LIMIT 10
        """, (today,))
        
        recent_alerts = cursor.fetchall()
        
        conn.close()
        
        return {
            "daily_stats": {
                "total_posts": daily_stats[0] or 0,
                "successful_posts": daily_stats[1] or 0,
                "avg_engagement": round(daily_stats[2] or 0, 3),
                "avg_safety_score": round(daily_stats[3] or 0, 3)
            },
            "platform_stats": [
                {"platform": p[0], "posts": p[1], "engagement": round(p[2] or 0, 3)}
                for p in platform_stats
            ],
            "recent_alerts": [
                {"type": a[0], "severity": a[1], "message": a[2], "time": a[3]}
                for a in recent_alerts
            ],
            "circuit_status": self.check_circuit_breakers()
        }

if __name__ == "__main__":
    safety = MarketingSafetySystem()
    
    # Test with prepared Reddit content
    test_content = """
    AgentIndex: Searchable Registry for 40k+ AI Agents
    
    Finding the right AI agent for your ML project is surprisingly painful. You end up scrolling through GitHub, checking random repos, or building from scratch because discovery sucks.

    We built AgentIndex to solve this. It's a searchable registry of 40,000+ agents with semantic search that actually works.
    """
    
    result = safety.evaluate_marketing_request(test_content, "reddit", "product_announcement")
    
    print("🛡️ MARKETING SAFETY EVALUATION")
    print("=" * 50)
    print(f"Approved: {'✅' if result['approved'] else '❌'}")
    print(f"Approval Tier: {result['approval_tier']}")
    print(f"Safety Score: {result['safety_score']:.2f}")
    print(f"Platform: {result['platform']}")
    
    if result['warnings']:
        print("Warnings:")
        for warning in result['warnings']:
            print(f"  ⚠️ {warning}")
    
    print("\nDashboard Data:")
    dashboard = safety.get_safety_dashboard_data()
    print(f"Posts today: {dashboard['daily_stats']['total_posts']}")
    print(f"Circuit breakers: {dashboard['circuit_status']['breakers_triggered']}")