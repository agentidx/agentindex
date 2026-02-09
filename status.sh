#!/bin/bash
# AgentIndex Quick Status
# Run via SSH from anywhere: ssh agentindex@<tailscale-ip> ~/agentindex/status.sh

echo "========================================"
echo "AgentIndex Status — $(date)"
echo "========================================"

# Health report
if [ -f ~/agentindex/health.json ]; then
    echo ""
    echo "HEALTH:"
    python3 -c "
import json
with open('$HOME/agentindex/health.json') as f:
    h = json.load(f)
print(f\"  Status: {h['status'].upper()}\")
print(f\"  Last check: {h['timestamp']}\")
for name, check in h['checks'].items():
    status = check.get('status', 'unknown')
    icon = '✓' if status == 'ok' else '⚠' if status == 'warning' else '✗'
    print(f'  {icon} {name}: {status}')
if h.get('alerts'):
    print(f\"  ALERTS ({len(h['alerts'])}):\")
    for a in h['alerts']:
        print(f\"    [{a['severity']}] {a['component']}: {a['message']}\")
"
fi

# Database stats
echo ""
echo "DATABASE:"
psql agentindex -t -c "
SELECT 'Total agents: ' || count(*) FROM agents
UNION ALL
SELECT 'Active agents: ' || count(*) FROM agents WHERE is_active = true
UNION ALL
SELECT 'New (24h): ' || count(*) FROM agents WHERE first_indexed > NOW() - INTERVAL '24 hours'
;" 2>/dev/null || echo "  Could not connect to database"

echo ""
echo "BY SOURCE:"
psql agentindex -t -c "
SELECT '  ' || source || ': ' || count(*) FROM agents GROUP BY source ORDER BY count(*) DESC;
" 2>/dev/null

echo ""
echo "PIPELINE:"
psql agentindex -t -c "
SELECT '  ' || crawl_status || ': ' || count(*) FROM agents GROUP BY crawl_status ORDER BY count(*) DESC;
" 2>/dev/null

echo ""
echo "DISCOVERY (last 24h):"
psql agentindex -t -c "
SELECT '  Requests: ' || count(*) FROM discovery_log WHERE timestamp > NOW() - INTERVAL '24 hours';
" 2>/dev/null

# Process check
echo ""
echo "PROCESSES:"
if pgrep -f "agentindex.run" > /dev/null; then
    echo "  ✓ AgentIndex running (PID: $(pgrep -f 'agentindex.run'))"
else
    echo "  ✗ AgentIndex NOT running!"
fi

if pgrep -f "ollama" > /dev/null; then
    echo "  ✓ Ollama running"
else
    echo "  ✗ Ollama NOT running!"
fi

if pgrep -f "postgres" > /dev/null; then
    echo "  ✓ PostgreSQL running"
else
    echo "  ✗ PostgreSQL NOT running!"
fi

# Disk
echo ""
echo "DISK:"
df -h / | tail -1 | awk '{print "  Used: " $3 " / " $2 " (" $5 " used)"}'

# Memory
echo ""
echo "MEMORY:"
vm_stat 2>/dev/null | head -5

# Last log entries
echo ""
echo "LAST LOG ENTRIES:"
tail -5 ~/agentindex/agentindex.log 2>/dev/null || echo "  No log file found"

# Alerts
if [ -f ~/agentindex/alerts.log ]; then
    alert_count=$(wc -l < ~/agentindex/alerts.log)
    if [ "$alert_count" -gt 0 ]; then
        echo ""
        echo "RECENT ALERTS:"
        tail -10 ~/agentindex/alerts.log
    fi
fi

echo ""
echo "========================================"
