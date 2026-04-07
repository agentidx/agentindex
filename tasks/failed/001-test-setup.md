# Task 001 — Verify Setup

## Goal
Verify that Claude Code can read the project, run commands, and write files.

## Instructions
1. Read CLAUDE.md in the project root and confirm you understand the project structure.
2. List the files in ~/agentindex/agentindex/api/ and report them.
3. Run: python3 -c "import sqlite3; conn = sqlite3.connect('agentindex/crypto/crypto_trust.db'); print('Rows in nerq_risk_signals:', conn.execute('SELECT count(*) FROM nerq_risk_signals').fetchone()[0])"
4. Run: launchctl list | grep -E "nerq|zarq|agentindex" and report the status of each service.
5. Create the file ~/agentindex/tasks/test-output.txt with the text "Claude Code setup verified [current date and time]"

## Acceptance criteria
- [ ] CLAUDE.md read and understood
- [ ] File listing from api/ reported
- [ ] Row count from nerq_risk_signals reported
- [ ] LaunchAgent status reported
- [ ] test-output.txt created

## Result

All 5 steps completed successfully.

### 1. CLAUDE.md read and understood
Read and understood. ZARQ (zarq.ai) = crypto risk intelligence ("Moody's for crypto"). Nerq (nerq.ai) = AI agent search engine (4.66M agents). Both share a FastAPI backend (`agentindex/api/discovery.py`, port 8000). Key rules: heredoc for shell, `launchctl` not `pkill`, never modify schema or `nerq_risk_signals` directly.

### 2. Files in `agentindex/api/`
- `__init__.py`
- `a2a.py`
- `api_protection.py`
- `discovery.py` (main app)
- `discovery.py.bak`
- `integrations.py`
- `keys.py`
- `multi_jurisdiction.py`
- `semantic.py`
- `zarq_router.py`

### 3. Row count from nerq_risk_signals
**205 rows** in `nerq_risk_signals` (matches CLAUDE.md documentation).

### 4. LaunchAgent status
| Service | PID | Status |
|---|---|---|
| com.nerq.api | 54006 | Running (exit -9) |
| com.nerq.crypto-daily | 49817 | Running (exit 1) |
| com.nerq.quick-price-fetch | - | Idle (exit 0) |
| com.nerq.paper-trading-daily | - | Idle (exit 0) |
| com.agentindex.parser | 72389 | Running (exit -15) |
| com.agentindex.mcp-sse | 72399 | Running (exit -15) |
| com.agentindex.dashboard | 72400 | Running (exit -15) |
| com.zarq.mcp-sse | 72398 | Running (exit -15) |
| com.zarq.agent-intelligence | - | Idle (exit 0) |
| com.zarq.weekly-agent-report | - | Idle (exit 0) |

### 5. test-output.txt created
Created at `~/agentindex/tasks/test-output.txt`.

### Files changed
- `tasks/failed/001-test-setup.md` — appended this Result section
- `tasks/test-output.txt` — created (new file)

### Status: PASSED
