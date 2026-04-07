"""
Daily Automated Report System
Generates and sends daily status report to Discord at 08:00 CET
"""

import psycopg2
import os
import json
import subprocess
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

class DailyReporter:
    """Generate daily reports for AgentIndex."""
    
    def __init__(self):
        self.conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        
    def get_total_agents(self) -> dict:
        """Get total agents and 24h delta."""
        cursor = self.conn.cursor()
        
        # Total agents
        cursor.execute('SELECT COUNT(*) FROM agents WHERE is_active = true')
        total = cursor.fetchone()[0]
        
        # Last 24h
        cursor.execute('SELECT COUNT(*) FROM agents WHERE first_indexed >= NOW() - INTERVAL %s', ('24 hours',))
        delta_24h = cursor.fetchone()[0]
        
        return {'total': total, 'delta_24h': delta_24h}
    
    def get_source_breakdown(self) -> dict:
        """Get agent counts by source with 24h delta."""
        cursor = self.conn.cursor()
        
        # Current totals by source
        cursor.execute('''
            SELECT source, COUNT(*) as total,
                   COUNT(*) FILTER (WHERE first_indexed >= NOW() - INTERVAL '24 hours') as delta_24h
            FROM agents 
            WHERE is_active = true 
            GROUP BY source 
            ORDER BY total DESC
        ''')
        
        sources = {}
        for source, total, delta_24h in cursor.fetchall():
            sources[source] = {'total': total, 'delta': delta_24h}
            
        return sources
    
    def get_queue_status(self) -> dict:
        """Get parser queue status."""
        cursor = self.conn.cursor()
        
        cursor.execute('SELECT crawl_status, COUNT(*) FROM agents GROUP BY crawl_status')
        status = {}
        for crawl_status, count in cursor.fetchall():
            status[crawl_status] = count
            
        return status
    
    def get_error_stats(self) -> dict:
        """Get error statistics from logs."""
        try:
            # Check parser logs for errors in last 24h
            log_files = [
                '~/agentindex/parser_classified.log',
                '~/agentindex/parser_monitor.log', 
                '~/agentindex/parser.log'
            ]
            
            error_count = 0
            error_types = {}
            
            for log_file in log_files:
                if os.path.exists(os.path.expanduser(log_file)):
                    with open(os.path.expanduser(log_file), 'r') as f:
                        lines = f.readlines()
                        
                    # Count errors from last 24h
                    for line in lines:
                        if 'error' in line.lower() and datetime.now().strftime('%Y-%m-%d') in line:
                            error_count += 1
                            # Extract error type
                            if 'MCP compliance error' in line:
                                error_types['MCP compliance'] = error_types.get('MCP compliance', 0) + 1
                            elif 'SQLAlchemy' in line:
                                error_types['Database'] = error_types.get('Database', 0) + 1
                            else:
                                error_types['Other'] = error_types.get('Other', 0) + 1
            
            return {'total_errors': error_count, 'error_types': error_types}
            
        except Exception as e:
            return {'total_errors': 0, 'error_types': {}, 'error': str(e)}
    
    def get_crawler_status(self) -> dict:
        """Get status of crawlers and watchdog."""
        try:
            # Check running processes
            result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
            ps_output = result.stdout
            
            crawlers = {
                'parser': '❌',
                'github_expansion': '❌', 
                'npm_pypi_expansion': '❌',
                'watchdog': '❌'
            }
            
            for line in ps_output.split('\\n'):
                if 'parser_loop' in line and 'python' in line:
                    crawlers['parser'] = '✅'
                elif 'github_expansion' in line:
                    crawlers['github_expansion'] = '✅'  
                elif 'npm_pypi_expansion' in line:
                    crawlers['npm_pypi_expansion'] = '✅'
                elif 'watchdog' in line and 'python' in line:
                    crawlers['watchdog'] = '✅'
            
            return crawlers
            
        except Exception as e:
            return {'error': str(e)}
    
    def calculate_progress_to_goals(self, total_agents: int) -> dict:
        """Calculate progress towards 500K and 1M goals."""
        goal_500k = 500000
        goal_1m = 1000000
        
        target_date_500k = datetime(2026, 3, 7)
        target_date_1m = datetime(2026, 3, 25)
        
        now = datetime.now()
        days_to_500k = (target_date_500k - now).days
        days_to_1m = (target_date_1m - now).days
        
        # Calculate required daily rate
        remaining_500k = goal_500k - total_agents
        remaining_1m = goal_1m - total_agents
        
        daily_rate_needed_500k = remaining_500k / max(days_to_500k, 1)
        daily_rate_needed_1m = remaining_1m / max(days_to_1m, 1)
        
        return {
            'current': total_agents,
            'goal_500k': goal_500k,
            'goal_1m': goal_1m,
            'days_to_500k': days_to_500k,
            'days_to_1m': days_to_1m,
            'daily_rate_needed_500k': int(daily_rate_needed_500k),
            'daily_rate_needed_1m': int(daily_rate_needed_1m),
            'on_track_500k': daily_rate_needed_500k <= 30000,  # Sustainable daily rate
            'on_track_1m': daily_rate_needed_1m <= 30000
        }
    
    def get_compliance_stats(self) -> dict:
        """Get MCP compliance statistics."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute('''
                SELECT eu_risk_class, COUNT(*) 
                FROM agents 
                WHERE eu_risk_class IS NOT NULL 
                GROUP BY eu_risk_class
            ''')
            
            compliance = {}
            for risk_class, count in cursor.fetchall():
                compliance[risk_class] = count
                
            return compliance
            
        except Exception as e:
            return {'error': str(e)}
    
    def generate_report(self) -> str:
        """Generate complete daily report."""
        now = datetime.now()
        
        # Gather all data
        agents = self.get_total_agents()
        sources = self.get_source_breakdown() 
        queue = self.get_queue_status()
        errors = self.get_error_stats()
        crawlers = self.get_crawler_status()
        progress = self.calculate_progress_to_goals(agents['total'])
        compliance = self.get_compliance_stats()
        
        # Calculate hourly rate
        hourly_rate = int(agents['delta_24h'] / 24) if agents['delta_24h'] > 0 else 0
        
        # Format report
        report = f"""**DAGLIG RAPPORT** — {now.strftime('%Y-%m-%d %H:%M')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**📊 Indexering:**
• Total: **{agents['total']:,}** (+{agents['delta_24h']:,} senaste 24h)
• Rate: **{hourly_rate:,}/timme**
• Parser-kö: {queue.get('classified', 0):,}
• Fel senaste 24h: {errors['total_errors']} """

        if errors['error_types']:
            top_errors = sorted(errors['error_types'].items(), key=lambda x: x[1], reverse=True)[:3]
            error_str = ", ".join([f"{k}: {v}" for k, v in top_errors])
            report += f"({error_str})"

        report += f"""

**🔧 Crawlers:**
• Parser: {crawlers.get('parser', '❌')}
• GitHub: {crawlers.get('github_expansion', '❌')}
• npm/PyPI: {crawlers.get('npm_pypi_expansion', '❌')}
• Watchdog: {crawlers.get('watchdog', '❌')}

**📈 Källor (senaste 24h):**"""

        for source, data in sorted(sources.items(), key=lambda x: x[1]['total'], reverse=True)[:6]:
            report += f"\\n• {source}: {data['total']:,} (+{data['delta']})"

        if compliance and 'error' not in compliance:
            report += f"""

**⚖️ Compliance:**
• Klassificerade: {sum(compliance.values()):,}"""
            for risk, count in compliance.items():
                report += f"\\n• {risk}: {count:,}"

        report += f"""

**🎯 Mål-tracking:**
• 500K deadline: {progress['days_to_500k']} dagar kvar
• Rate behövs: {progress['daily_rate_needed_500k']:,}/dag
• On track: {'✅ JA' if progress['on_track_500k'] else '❌ NEJ'}
• 1M deadline: {progress['days_to_1m']} dagar kvar

**📋 Dagens fokus:**
1. Töm parser-kö (classified: {queue.get('classified', 0):,})
2. Deploy Docker Hub spider ({sources.get('docker_hub', {}).get('total', 0)} containers)
3. Deploy Replicate spider ({sources.get('replicate', {}).get('total', 0)} models)
4. Implementera GitHub token rotation"""

        return report
    
    def send_to_discord(self, report: str):
        """Send report to Discord via OpenClaw message tool."""
        # This would be called by OpenClaw cron job
        print(report)
        return report

if __name__ == "__main__":
    reporter = DailyReporter()
    report = reporter.generate_report()
    print(report)