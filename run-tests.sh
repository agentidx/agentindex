#!/bin/bash
cd ~/agentindex
python3 -m pytest tests/ -v --tb=short 2>&1 | tee tests/last-run.log
echo "Exit code: $?"
