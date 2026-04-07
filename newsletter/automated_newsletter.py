"""
Automated Newsletter System
Creates and schedules weekly newsletters via OpenClaw cron system
"""

import asyncio
from datetime import datetime
from newsletter.weekly_report_real import WeeklyReportGenerator, NewsletterFormatter


class AutomatedNewsletterService:
    """Handles automated newsletter generation and distribution"""
    
    def __init__(self):
        self.generator = WeeklyReportGenerator()
        self.formatter = NewsletterFormatter()
    
    async def generate_and_save_newsletter(self) -> str:
        """Generate current newsletter and save to file"""
        
        # Generate stats
        stats = await self.generator.generate_weekly_report()
        
        # Format as markdown
        newsletter_content = self.formatter.format_markdown_newsletter(stats)
        
        # Save with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d")
        filename = f"weekly_newsletter_{timestamp}.md"
        filepath = f"newsletter/{filename}"
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(newsletter_content)
        
        print(f"📧 Newsletter saved to {filepath}")
        print(f"📊 Stats: {stats.total_agents:,} total agents, +{stats.new_agents} new")
        
        return filepath
    
    def create_newsletter_summary(self, stats) -> str:
        """Create short summary for system notifications"""
        return f"""📧 Weekly Newsletter Generated
        
📊 Stats Summary:
• {stats.total_agents:,} total agents
• +{stats.new_agents} new this week  
• {len(stats.hot_categories)} active categories
• Top language: Python ({stats.trending_languages[0]['agent_count']} agents)

Newsletter ready for distribution!"""


async def main():
    """Main function for cron job execution"""
    
    service = AutomatedNewsletterService()
    
    try:
        # Generate newsletter
        filepath = await service.generate_and_save_newsletter()
        
        # Create summary
        stats = await service.generator.generate_weekly_report()
        summary = service.create_newsletter_summary(stats)
        
        print("\n" + "="*60)
        print("WEEKLY NEWSLETTER GENERATED!")
        print("="*60)
        print(summary)
        print(f"\nFile saved: {filepath}")
        
        return True
        
    except Exception as e:
        error_msg = f"❌ Newsletter generation failed: {e}"
        print(error_msg)
        return False


if __name__ == "__main__":
    success = asyncio.run(main())