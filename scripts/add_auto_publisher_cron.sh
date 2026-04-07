#!/bin/bash
# Add auto_publisher weekly cron — run this once manually
ENTRY='0 6 * * 1 cd ~/agentindex && venv/bin/python -u -m agentindex.crypto.auto_publisher >> ~/agentindex/logs/auto_publisher.log 2>&1'
if crontab -l 2>/dev/null | grep -q auto_publisher; then
    echo "auto_publisher cron already exists"
else
    (crontab -l 2>/dev/null; echo "$ENTRY") | crontab -
    echo "Added: $ENTRY"
fi
crontab -l | grep auto_publisher
