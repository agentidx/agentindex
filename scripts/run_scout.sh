#!/bin/bash
# Nerq Scout — runs every 6 hours
# Discovers top agents, evaluates via KYA, publishes report
cd /Users/anstudio/agentindex
source venv/bin/activate
python3 -m agentindex.nerq_scout_agent >> logs/scout.log 2>&1
