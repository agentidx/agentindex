#!/usr/bin/env python3
"""
AgentIndex Watchdog - Crawler Reliability Monitor

Monitors crawler processes and database activity to ensure continuous indexing.
Automatically restarts failed crawlers and logs all issues.

CRITICAL: This is blocking priority - crawlers must never stay down unnoticed.
"""

import os
import sys
import time
import subprocess
import psutil
import logging
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

# Add project path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentindex.db.models import Agent, get_session
from sqlalchemy import func, select

# Setup dedicated logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [WATCHDOG] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('watchdog.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("watchdog")

class CrawlerWatchdog:
    """Monitors and auto-restarts AgentIndex crawlers for maximum reliability."""
    
    def __init__(self):
        self.check_interval = 60  # Check every 60 seconds
        self.indexing_timeout = 15  # Alert if no indexing for 15 minutes
        self.max_restart_attempts = 3  # Max restarts per hour
        
        # Crawler definitions
        self.crawlers = {
            'github_expansion': {
                'script': 'run_github_expansion.py',
                'process_name': 'run_github_expansion.py',
                'description': 'GitHub Expanded Spider',
                'restart_command': ['python', 'run_github_expansion.py'],
                'source_filter': ['github']
            },
            'npm_pypi_expansion': {
                'script': 'run_npm_pypi_expansion.py', 
                'process_name': 'run_npm_pypi_expansion.py',
                'description': 'npm/PyPI Expansion Spider',
                'restart_command': ['python', 'run_npm_pypi_expansion.py'],
                'source_filter': ['npm', 'pypi']
            },
            'parser_loop': {
                'script': 'run_parser_loop.py',
                'process_name': 'run_parser_loop.py',
                'description': 'Compliance Parser',
                'restart_command': ['python', 'run_parser_loop.py'],
                'source_filter': []  # Parser doesn't create agents
            }
        }
        
        # State tracking
        self.restart_counts = {name: 0 for name in self.crawlers}
        self.last_restart_reset = datetime.now()
        self.last_known_total = 0
        self.status_file = 'watchdog_status.json'
        self.daily_restart_counts = {name: 0 for name in self.crawlers}
        self.last_daily_reset = datetime.now().date()
        
        # External health check settings  
        self.external_check_url = "https://nerq.ai/v1/health"
        self.last_external_check = None
        self.external_check_interval = 5 * 60  # 5 minutes
        self.external_status_ok = True
        
        logger.info("🐕 Watchdog initialized - monitoring crawler reliability")
        logger.info(f"   Monitored crawlers: {list(self.crawlers.keys())}")
        logger.info(f"   Check interval: {self.check_interval}s")
        logger.info(f"   Indexing timeout: {self.indexing_timeout} minutes")
        logger.info(f"   External health check: {self.external_check_url} (every {self.external_check_interval//60} min)")
    
    def check_external_health(self) -> bool:
        """Check external endpoint health every 5 minutes."""
        
        now = datetime.now()
        
        # Only check every 5 minutes
        if (self.last_external_check and 
            (now - self.last_external_check).total_seconds() < self.external_check_interval):
            return self.external_status_ok
            
        logger.info("🌐 Checking external health endpoint...")
        
        try:
            response = requests.get(self.external_check_url, timeout=10)
            
            if response.status_code == 200:
                try:
                    # Check if response contains expected JSON with status "ok"
                    data = response.json()
                    if data.get('status') == 'ok':
                        if not self.external_status_ok:  # Was down, now up
                            logger.critical("✅ EXTERNAL ACCESS RESTORED - nerq.ai/v1/health responding OK")
                        else:
                            logger.info("✅ External endpoint healthy (status: ok)")
                        self.external_status_ok = True
                    else:
                        logger.critical(f"🚨 EXTERNAL ACCESS DOWN - Invalid response: {data.get('status', 'unknown')}")
                        self.external_status_ok = False
                except:
                    logger.critical(f"🚨 EXTERNAL ACCESS DOWN - Invalid JSON response")
                    self.external_status_ok = False
            else:
                logger.critical(f"🚨 EXTERNAL ACCESS DOWN - HTTP {response.status_code}")
                self.external_status_ok = False
                
        except Exception as e:
            logger.critical(f"🚨 EXTERNAL ACCESS DOWN - Connection error: {e}")
            self.external_status_ok = False
            
        self.last_external_check = now
        return self.external_status_ok

    def run_watch_loop(self):
        """Main watchdog monitoring loop."""
        
        logger.info("🚀 Starting crawler watchdog monitoring")
        
        while True:
            try:
                # Reset restart counts hourly
                if datetime.now() - self.last_restart_reset > timedelta(hours=1):
                    self.restart_counts = {name: 0 for name in self.crawlers}
                    self.last_restart_reset = datetime.now()
                    logger.info("🔄 Restart counts reset (hourly)")
                
                # Check all crawlers
                self.check_all_crawlers()
                
                # Check overall indexing activity
                self.check_indexing_activity()
                
                # Check external endpoint health (every 5 min)
                self.check_external_health()
                
                # Anders: Update JSON status för dashboard
                self.update_status_file()
                
                # Brief status report
                self.log_status()
                
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                logger.info("🛑 Watchdog stopped by user")
                break
            except Exception as e:
                logger.error(f"💥 Watchdog error: {e}")
                time.sleep(self.check_interval)  # Continue despite errors
    
    def check_all_crawlers(self):
        """Check all defined crawlers."""
        
        for crawler_name, crawler_config in self.crawlers.items():
            try:
                self.check_single_crawler(crawler_name, crawler_config)
            except Exception as e:
                logger.error(f"❌ Error checking {crawler_name}: {e}")
    
    def check_single_crawler(self, name: str, config: Dict):
        """Check individual crawler process."""
        
        # Check if process is running
        is_running, pid = self.is_process_running(config['process_name'])
        
        if not is_running:
            logger.warning(f"💀 {config['description']} is DOWN (no process found)")
            self.handle_dead_crawler(name, config, reason="process_not_found")
            return
        
        # Check if process is actually working (for indexing crawlers)
        if config['source_filter']:  # Only for crawlers that create agents
            recent_activity = self.check_crawler_activity(config['source_filter'])
            if not recent_activity:
                logger.warning(f"⏰ {config['description']} is STALLED (no indexing activity)")
                self.handle_stalled_crawler(name, config, pid)
                return
        
        # Crawler is healthy
        logger.debug(f"✅ {config['description']} healthy (PID: {pid})")
    
    def is_process_running(self, process_name: str) -> Tuple[bool, Optional[int]]:
        """Check if process with given name is running."""
        
        try:
            for proc in psutil.process_iter(['pid', 'cmdline']):
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if process_name in cmdline and 'python' in cmdline.lower():
                        return True, proc.info['pid']
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return False, None
        except Exception:
            return False, None
    
    def check_crawler_activity(self, sources: List[str]) -> bool:
        """Check if crawler has indexed agents recently."""
        
        try:
            session = get_session()
            
            # Check for agents from these sources in last 15 minutes
            cutoff_time = datetime.utcnow() - timedelta(minutes=self.indexing_timeout)
            
            recent_count = session.execute(
                select(func.count(Agent.id)).where(
                    Agent.source.in_(sources),
                    Agent.first_indexed >= cutoff_time
                )
            ).scalar()
            
            session.close()
            return recent_count > 0
            
        except Exception as e:
            logger.error(f"❌ Database check error: {e}")
            return True  # Assume healthy if can't check
    
    def check_indexing_activity(self):
        """Check overall indexing activity across all sources."""
        
        try:
            session = get_session()
            
            current_total = session.execute(select(func.count(Agent.id))).scalar()
            
            # Check if total has increased since last check
            if current_total > self.last_known_total:
                agents_added = current_total - self.last_known_total
                logger.debug(f"📈 Database growth: +{agents_added} agents (total: {current_total:,})")
            elif current_total == self.last_known_total:
                # No growth - check if this is expected
                recent_activity = session.execute(
                    select(func.count(Agent.id)).where(
                        Agent.first_indexed >= datetime.utcnow() - timedelta(minutes=self.indexing_timeout)
                    )
                ).scalar()
                
                if recent_activity == 0:
                    logger.warning(f"📊 No indexing activity for {self.indexing_timeout} minutes - checking crawlers")
            
            self.last_known_total = current_total
            session.close()
            
        except Exception as e:
            logger.error(f"❌ Database activity check error: {e}")
    
    def handle_dead_crawler(self, name: str, config: Dict, reason: str):
        """Handle completely dead crawler process."""
        
        # Anders: STOPPA vid 3+ restarts - troligen underliggande problem
        if self.restart_counts[name] >= self.max_restart_attempts:
            logger.critical(f"🚨 CRITICAL: {config['description']} exceeded restart limit ({self.max_restart_attempts})")
            logger.critical(f"🚨 CRITICAL: repeated crash - stopping automatic restarts")
            
            # Capture detailed crash logs för analysis
            self.capture_crash_logs(config['process_name'], critical=True)
            
            # Update status with critical state
            self.update_status_file()
            return
        
        logger.warning(f"🔄 Restarting {config['description']} (reason: {reason}, attempt {self.restart_counts[name] + 1}/{self.max_restart_attempts})")
        
        # Anders: SPARA crash-loggen INNAN restart för diagnostik
        crash_details = self.capture_crash_logs(config['process_name'], save_for_analysis=True)
        
        # Restart the crawler
        success = self.restart_crawler(name, config)
        
        if success:
            self.restart_counts[name] += 1
            self.daily_restart_counts[name] += 1
            logger.info(f"✅ {config['description']} restarted successfully (restart #{self.restart_counts[name]})")
        else:
            logger.error(f"❌ Failed to restart {config['description']}")
            
        # Update status after restart attempt
        self.update_status_file()
    
    def handle_stalled_crawler(self, name: str, config: Dict, pid: int):
        """Handle crawler that's running but not producing results."""
        
        logger.info(f"🔄 Killing stalled {config['description']} (PID: {pid})")
        
        try:
            # Kill existing process
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=10)
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            try:
                proc.kill()  # Force kill if terminate didn't work
            except psutil.NoSuchProcess:
                pass
        
        # Restart
        self.handle_dead_crawler(name, config, "stalled_process")
    
    def restart_crawler(self, name: str, config: Dict) -> bool:
        """Restart a crawler process."""
        
        try:
            # Change to correct directory
            os.chdir(os.path.dirname(os.path.abspath(__file__)))
            
            # Activate venv and run command
            cmd = [
                'bash', '-c', 
                f'source venv/bin/activate && {" ".join(config["restart_command"])} > /dev/null 2>&1 &'
            ]
            
            result = subprocess.run(cmd, check=True)
            
            # Wait a moment and verify it started
            time.sleep(3)
            is_running, new_pid = self.is_process_running(config['process_name'])
            
            if is_running:
                logger.info(f"✅ {config['description']} started with PID: {new_pid}")
                return True
            else:
                logger.error(f"❌ {config['description']} failed to start")
                return False
                
        except Exception as e:
            logger.error(f"❌ Restart error for {config['description']}: {e}")
            return False
    
    def capture_crash_logs(self, process_name: str, critical: bool = False, save_for_analysis: bool = False):
        """Anders: SPARA crash-loggen för diagnostik - identifiera faktisk orsak."""
        
        crash_details = {
            'timestamp': datetime.now().isoformat(),
            'process_name': process_name,
            'logs_captured': []
        }
        
        try:
            # Try to get logs from common log locations
            log_files = ['parser.log', 'crawler.log', 'nohup.out', 'watchdog_output.log']
            
            for log_file in log_files:
                if os.path.exists(log_file):
                    # Get last 100 lines som Anders specificerade
                    result = subprocess.run(
                        ['tail', '-100', log_file], 
                        capture_output=True, text=True
                    )
                    
                    if result.stdout:
                        crash_details['logs_captured'].append({
                            'file': log_file,
                            'content': result.stdout
                        })
                        
                        if critical:
                            logger.critical(f"🚨 CRITICAL CRASH LOG from {log_file}:")
                        else:
                            logger.warning(f"📄 Crash log from {log_file}:")
                            
                        # Visa sista 20 rader i main log för immediate visibility
                        for line in result.stdout.split('\n')[-20:]:
                            if line.strip():
                                log_level = logger.critical if critical else logger.warning
                                log_level(f"   {line}")
                        
                        # Anders: Identifiera orsak från loggar
                        self.diagnose_crash_cause(result.stdout, process_name)
                        
                        break
            
            # Anders: SPARA för analysis om begärt
            if save_for_analysis or critical:
                crash_file = f"crash_analysis_{process_name}_{int(datetime.now().timestamp())}.json"
                
                with open(crash_file, 'w') as f:
                    import json
                    json.dump(crash_details, f, indent=2)
                
                logger.info(f"💾 Crash details saved to {crash_file} for analysis")
                        
        except Exception as e:
            logger.error(f"❌ Could not capture crash logs: {e}")
        
        return crash_details
    
    def diagnose_crash_cause(self, log_content: str, process_name: str):
        """Anders: Identifiera faktisk orsak - inte bara 'exec failed'."""
        
        log_lower = log_content.lower()
        
        # OOM (Out of Memory)
        if any(indicator in log_lower for indicator in ['memory', 'oom', 'killed', 'signal 9']):
            logger.error(f"🧠 DIAGNOSIS: {process_name} - OUT OF MEMORY (OOM)")
            
        # GitHub Rate Limit
        elif any(indicator in log_lower for indicator in ['rate limit', 'api rate limit', '403', 'abuse']):
            logger.error(f"⏳ DIAGNOSIS: {process_name} - GITHUB RATE LIMIT hit")
            
        # Network/Connection issues  
        elif any(indicator in log_lower for indicator in ['connection', 'timeout', 'network', 'dns', 'unreachable']):
            logger.error(f"🌐 DIAGNOSIS: {process_name} - NETWORK/CONNECTION error")
            
        # Disk Full
        elif any(indicator in log_lower for indicator in ['disk', 'space', 'no space left']):
            logger.error(f"💾 DIAGNOSIS: {process_name} - DISK SPACE issue")
            
        # Python exceptions
        elif any(indicator in log_lower for indicator in ['traceback', 'exception', 'error:']):
            logger.error(f"🐍 DIAGNOSIS: {process_name} - PYTHON EXCEPTION (see logs)")
            
        # Database issues
        elif any(indicator in log_lower for indicator in ['database', 'postgresql', 'connection pool']):
            logger.error(f"🗃️ DIAGNOSIS: {process_name} - DATABASE connectivity issue")
            
        else:
            logger.error(f"❓ DIAGNOSIS: {process_name} - UNKNOWN cause (check crash logs)")
    
    def update_status_file(self):
        """Anders: Status till JSON-fil som dashboard kan läsa."""
        
        try:
            # Reset daily counts if new day
            today = datetime.now().date()
            if today > self.last_daily_reset:
                self.daily_restart_counts = {name: 0 for name in self.crawlers}
                self.last_daily_reset = today
                
            session = get_session()
            
            # Current totals
            current_total = session.execute(select(func.count(Agent.id))).scalar()
            
            # Minutes since last indexed agent
            latest_agent = session.execute(
                select(Agent.first_indexed).order_by(Agent.first_indexed.desc()).limit(1)
            ).scalar()
            
            minutes_since_last = 0
            if latest_agent:
                minutes_since_last = (datetime.utcnow() - latest_agent).total_seconds() / 60
            
            # Hourly rate (last hour)
            hour_ago = datetime.utcnow() - timedelta(hours=1)
            hourly_count = session.execute(
                select(func.count(Agent.id)).where(Agent.first_indexed >= hour_ago)
            ).scalar()
            
            # Crawler status
            crawler_status = {}
            for name, config in self.crawlers.items():
                is_running, pid = self.is_process_running(config['process_name'])
                
                # Check if critical (too many restarts)
                is_critical = self.restart_counts[name] >= self.max_restart_attempts
                
                crawler_status[name] = {
                    'running': is_running,
                    'pid': pid,
                    'description': config['description'],
                    'restarts_today': self.daily_restart_counts[name],
                    'restarts_this_hour': self.restart_counts[name],
                    'status': 'critical' if is_critical else ('running' if is_running else 'down'),
                    'last_check': datetime.now().isoformat()
                }
            
            status = {
                'timestamp': datetime.now().isoformat(),
                'total_agents': current_total,
                'minutes_since_last_indexed': round(minutes_since_last, 1),
                'hourly_indexing_rate': hourly_count,
                'crawlers': crawler_status,
                'watchdog_healthy': True,
                'external_health': {
                    'url': self.external_check_url,
                    'status': 'ok' if self.external_status_ok else 'down',
                    'last_check': self.last_external_check.isoformat() if self.last_external_check else None
                },
                'alerts': []
            }
            
            # Add alerts
            if minutes_since_last > 15:
                status['alerts'].append(f"⚠️ No indexing for {minutes_since_last:.1f} minutes")
            
            # External health alert
            if not self.external_status_ok:
                status['alerts'].append(f"🚨 EXTERNAL ACCESS DOWN - {self.external_check_url} not responding")
            
            for name, info in crawler_status.items():
                if info['status'] == 'critical':
                    status['alerts'].append(f"🚨 CRITICAL: {info['description']} stopped after {info['restarts_this_hour']} restarts")
                elif not info['running']:
                    status['alerts'].append(f"❌ {info['description']} is down")
            
            # Write JSON status
            import json
            with open(self.status_file, 'w') as f:
                json.dump(status, f, indent=2)
                
            session.close()
            
        except Exception as e:
            logger.error(f"❌ Could not update status file: {e}")
    
    def log_status(self):
        """Log brief status summary."""
        
        running_crawlers = []
        for name, config in self.crawlers.items():
            is_running, pid = self.is_process_running(config['process_name'])
            if is_running:
                running_crawlers.append(f"{name}({pid})")
        
        logger.info(f"📊 Status: {len(running_crawlers)}/{len(self.crawlers)} crawlers running: {', '.join(running_crawlers)}")

    def run_single_check(self):
        """Anders: Single check för cron job - */5 minuter."""
        
        logger.info("🔍 Running single watchdog check (cron mode)")
        
        try:
            # Reset restart counts hourly
            if datetime.now() - self.last_restart_reset > timedelta(hours=1):
                self.restart_counts = {name: 0 for name in self.crawlers}
                self.last_restart_reset = datetime.now()
                logger.info("🔄 Restart counts reset (hourly)")
            
            # Check all crawlers
            self.check_all_crawlers()
            
            # Check overall indexing activity
            self.check_indexing_activity()
            
            # Check external endpoint health (every 5 min)
            self.check_external_health()
            
            # Update JSON status för dashboard
            self.update_status_file()
            
            # Status summary
            self.log_status()
            
            logger.info("✅ Single watchdog check completed")
            
        except Exception as e:
            logger.error(f"💥 Watchdog check failed: {e}")
            raise

def main():
    """Main watchdog entry point."""
    
    import argparse
    parser = argparse.ArgumentParser(description='AgentIndex Crawler Watchdog')
    parser.add_argument('--single', action='store_true', 
                       help='Run single check (for cron) instead of continuous loop')
    args = parser.parse_args()
    
    if args.single:
        # Anders: Cron mode - single check
        watchdog = CrawlerWatchdog()
        watchdog.run_single_check()
    else:
        # Continuous monitoring mode
        print("🐕 AgentIndex Crawler Watchdog")
        print("=" * 40)
        print("Monitoring crawler reliability for continuous indexing")
        print("Press Ctrl+C to stop")
        print()
        
        watchdog = CrawlerWatchdog()
        
        try:
            watchdog.run_watch_loop()
        except KeyboardInterrupt:
            print("\n🛑 Watchdog stopped")
        except Exception as e:
            print(f"\n💥 Watchdog crashed: {e}")
            logger.error(f"Watchdog crashed: {e}")
            raise

if __name__ == "__main__":
    main()