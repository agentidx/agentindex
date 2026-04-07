#!/bin/bash
# Add watchdog cron job - Anders specification: */5 * * * *

echo "🐕 Adding watchdog cron job..."

# Get current crontab
crontab -l > temp_cron 2>/dev/null || true

# Add watchdog job if not already present
if ! grep -q "watchdog.py" temp_cron; then
    echo "*/5 * * * * cd /Users/anstudio/agentindex && /Users/anstudio/agentindex/venv/bin/python watchdog.py --single >> watchdog_cron.log 2>&1" >> temp_cron
    
    # Install the new crontab
    crontab temp_cron
    
    echo "✅ Watchdog cron job added - runs every 5 minutes"
else
    echo "⚠️ Watchdog cron job already exists"
fi

# Cleanup
rm -f temp_cron

echo ""
echo "📋 Current cron jobs:"
crontab -l

echo ""
echo "📄 Watchdog will log to: ~/agentindex/watchdog_cron.log"
echo "📄 Status JSON updates: ~/agentindex/watchdog_status.json"