#!/bin/bash
# Push latest track-record entry to kbanilsson-pixel/track-record GitHub repo
# Designed to run after daily_track_record.py generates a new entry
set -euo pipefail

TRACK_DIR="$HOME/agentindex/track-record"
REPO_DIR="$HOME/agentindex/track-record-repo"
JSONL="$TRACK_DIR/daily-signals.jsonl"
REMOTE="https://github.com/kbanilsson-pixel/track-record.git"

# --- Ensure JSONL exists ---
if [ ! -f "$JSONL" ]; then
    echo "ERROR: $JSONL not found"
    exit 1
fi

# --- Extract latest entry ---
LATEST=$(tail -1 "$JSONL")
DATE=$(echo "$LATEST" | python3 -c "import sys,json; print(json.load(sys.stdin)['date'])")
HASH=$(echo "$LATEST" | python3 -c "import sys,json; print(json.load(sys.stdin)['hash'])")
WARNINGS=$(echo "$LATEST" | python3 -c "import sys,json; print(json.load(sys.stdin)['zarq_warnings'])")

echo "Date: $DATE | Hash: ${HASH:0:16}... | Warnings: $WARNINGS"

# --- Clone or update repo ---
if [ -d "$REPO_DIR/.git" ]; then
    cd "$REPO_DIR"
    git pull --rebase --quiet
else
    git clone "$REMOTE" "$REPO_DIR" 2>/dev/null || {
        echo "Repo doesn't exist yet. Create it first:"
        echo "  gh repo create kbanilsson-pixel/track-record --public --description 'ZARQ daily risk signals — SHA-256 hash-chained, publicly verifiable'"
        exit 1
    }
    cd "$REPO_DIR"
fi

# --- Write daily file ---
YEAR_DIR="signals/$(echo $DATE | cut -d- -f1)"
mkdir -p "$YEAR_DIR"
DAILY_FILE="$YEAR_DIR/$DATE.json"

echo "$LATEST" | python3 -m json.tool > "$DAILY_FILE"

# --- Append to master JSONL ---
cp "$JSONL" signals/daily-signals.jsonl

# --- Compute verification hash ---
VERIFY_HASH=$(shasum -a 256 "$DAILY_FILE" | cut -d' ' -f1)

# --- Commit and push ---
git add -A
if git diff --cached --quiet; then
    echo "No changes to commit for $DATE"
    exit 0
fi

git commit -m "$(cat <<EOF
$DATE: $WARNINGS warnings | hash: ${HASH:0:16}

SHA-256: $HASH
File hash: $VERIFY_HASH
Tokens: 205 | Warnings: $WARNINGS

Co-Authored-By: ZARQ Risk Engine <noreply@zarq.ai>
EOF
)"

git push
echo "Pushed $DATE track record to GitHub"
