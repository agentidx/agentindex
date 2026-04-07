#!/bin/bash
# Start AgentIndex Watchdog as background process

cd ~/agentindex

# Activate virtual environment
source venv/bin/activate

# Kill any existing watchdog process
pkill -f "python.*watchdog.py" 2>/dev/null || true

# Start watchdog in background
echo "🐕 Starting AgentIndex Watchdog..."
nohup python watchdog.py > watchdog_output.log 2>&1 &

WATCHDOG_PID=$!
echo "✅ Watchdog started with PID: $WATCHDOG_PID"
echo "📄 Logs: ~/agentindex/watchdog.log"
echo "📄 Output: ~/agentindex/watchdog_output.log"
echo ""
echo "To check status: tail -f ~/agentindex/watchdog.log"
echo "To stop: pkill -f 'python.*watchdog.py'"