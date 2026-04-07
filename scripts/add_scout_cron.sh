#!/bin/bash
# Add Nerq Scout cron — runs every 6 hours (04:00, 10:00, 16:00, 22:00)
CRON_LINE="0 4,10,16,22 * * * /Users/anstudio/agentindex/scripts/run_scout.sh"

# Check if already exists
if crontab -l 2>/dev/null | grep -q "run_scout.sh"; then
    echo "Scout cron already exists"
    crontab -l | grep scout
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "Scout cron added: $CRON_LINE"
fi
