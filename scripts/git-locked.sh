#!/usr/bin/env bash
# git-locked.sh — serialise `git add / commit / push` across Smedjan
# workers. macOS has no flock(1), so we use a tiny Python helper that
# takes an fcntl exclusive lock + execs git with the remaining args.
# Exit 2 if the lock cannot be acquired within 60 s.
set -euo pipefail

LOCK_DIR="${HOME}/.smedjan"
LOCK_FILE="${LOCK_DIR}/git.lock"
mkdir -p "$LOCK_DIR"

exec /usr/bin/python3 - "$LOCK_FILE" "$@" <<'PY'
import fcntl, os, sys, time
lock_path, *git_args = sys.argv[1:]
fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
deadline = time.monotonic() + 60
while True:
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        break
    except BlockingIOError:
        if time.monotonic() >= deadline:
            sys.stderr.write(f"git-locked.sh: could not acquire {lock_path} within 60s\n")
            sys.exit(2)
        time.sleep(0.25)
# Exec git with the remaining args; the lock is released on process exit.
os.execvp("git", ["git", *git_args])
PY
