#!/usr/bin/env python3
"""
Tunnel Repair Script
Automatic detection and repair of Cloudflare tunnel issues
"""

import requests
import subprocess
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [tunnel] %(message)s")
logger = logging.getLogger("tunnel_repair")

def check_tunnel_health():
    """Check if tunnel is working correctly."""
    tests = [
        ("https://api.agentcrawl.dev/v1/health", "API endpoint"),
        ("https://agentcrawl.dev", "Landing page"),
        ("https://dash.agentcrawl.dev", "Dashboard")
    ]
    
    problems = []
    
    for url, name in tests:
        try:
            response = requests.get(url, timeout=10, allow_redirects=False)
            
            if response.status_code == 301:
                location = response.headers.get('location', '')
                if 'nerq.ai' in location:
                    problems.append(f"{name}: 301 redirect to nerq.ai (DNS problem)")
                else:
                    problems.append(f"{name}: 301 redirect to {location}")
            elif response.status_code >= 400:
                problems.append(f"{name}: HTTP {response.status_code}")
            else:
                logger.info(f"✅ {name}: HTTP {response.status_code}")
                
        except Exception as e:
            problems.append(f"{name}: Connection error - {e}")
    
    return problems

def check_cloudflared_process():
    """Check if cloudflared is running."""
    try:
        result = subprocess.run(['pgrep', '-f', 'cloudflared'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            logger.info(f"✅ Cloudflared running: {len(pids)} processes")
            return True
        else:
            logger.error("❌ Cloudflared not running")
            return False
    except Exception as e:
        logger.error(f"❌ Error checking cloudflared: {e}")
        return False

def restart_cloudflared():
    """Restart cloudflared with correct config."""
    try:
        logger.info("🔄 Restarting cloudflared...")
        
        # Kill existing processes
        subprocess.run(['pkill', '-f', 'cloudflared'], 
                      capture_output=True, text=True)
        time.sleep(3)
        
        # Start with correct config
        config_path = "/Users/anstudio/.cloudflared/config.yml"
        cmd = f"cd ~/.cloudflared && nohup cloudflared tunnel --config config.yml run > cloudflared_auto.log 2>&1 & disown"
        
        subprocess.run(cmd, shell=True, check=True)
        logger.info("✅ Cloudflared restarted")
        
        # Wait for tunnel to establish
        time.sleep(15)
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to restart cloudflared: {e}")
        return False

def repair_tunnel():
    """Main repair function."""
    logger.info("🔧 Starting tunnel health check and repair...")
    
    # Check if cloudflared is running
    if not check_cloudflared_process():
        logger.info("🚨 Cloudflared not running, attempting restart...")
        if restart_cloudflared():
            logger.info("✅ Cloudflared restarted successfully")
        else:
            logger.error("❌ Failed to restart cloudflared")
            return False
    
    # Check tunnel health
    problems = check_tunnel_health()
    
    if not problems:
        logger.info("🎉 All tunnel endpoints healthy!")
        return True
    
    logger.warning(f"🚨 Found {len(problems)} tunnel problems:")
    for problem in problems:
        logger.warning(f"   - {problem}")
    
    # If we have 301 redirects to nerq.ai, this is a DNS issue
    if any('nerq.ai' in problem for problem in problems):
        logger.error("🚨 DNS issue detected: domains redirecting to nerq.ai")
        logger.error("   This requires Cloudflare DNS configuration fix")
        logger.error("   Action required: Contact Anders to fix DNS settings")
        return False
    
    # Try restarting cloudflared for other issues
    logger.info("🔄 Attempting cloudflared restart to fix tunnel issues...")
    if restart_cloudflared():
        # Recheck after restart
        time.sleep(20)
        new_problems = check_tunnel_health()
        
        if not new_problems:
            logger.info("✅ Tunnel issues resolved after restart!")
            return True
        else:
            logger.warning(f"⚠️ Still have {len(new_problems)} problems after restart")
            return False
    else:
        logger.error("❌ Failed to restart cloudflared")
        return False

if __name__ == "__main__":
    success = repair_tunnel()
    exit(0 if success else 1)