#!/usr/bin/env python3
"""
Refresh ZARQ dashboard cache.

Runs _build_dashboard_data() and writes the result to /tmp/zarq_dashboard_cache.json
so that the dashboard endpoint can serve cached data without ever running the
slow build under an HTTP request (which currently takes ~20s).

Designed to be run by launchd every 4 minutes (slightly faster than the
5-minute TTL so cache is always fresh).

Exit codes:
  0 = success
  1 = unrecoverable error
  2 = timeout (took longer than 5 minutes — should never happen normally)
"""
import sys
import os
import time
import json
import signal

# Add repo root so we can import agentindex
sys.path.insert(0, '/Users/anstudio/agentindex')


def timeout_handler(signum, frame):
    print("ERROR: Cache refresh timed out after 600s", flush=True)
    sys.exit(2)


def main():
    # Hard timeout: 10 minutes. Build now takes ~300s due to larger dataset.
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(600)

    try:
        from agentindex.zarq_dashboard import (
            _build_dashboard_data,
            _write_file_cache,
            _DASHBOARD_CACHE_FILE,
        )
    except Exception as e:
        print(f"ERROR: Failed to import zarq_dashboard: {e}", flush=True)
        return 1

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting ZARQ dashboard cache refresh", flush=True)
    print(f"  Target: {_DASHBOARD_CACHE_FILE}", flush=True)

    start = time.time()
    try:
        data = _build_dashboard_data()
    except Exception as e:
        elapsed = time.time() - start
        print(f"ERROR: _build_dashboard_data() failed after {elapsed:.1f}s: {e}", flush=True)
        return 1

    elapsed = time.time() - start
    print(f"  Build completed in {elapsed:.1f}s", flush=True)

    try:
        _write_file_cache(data)
    except Exception as e:
        print(f"ERROR: Failed to write cache: {e}", flush=True)
        return 1

    if os.path.exists(_DASHBOARD_CACHE_FILE):
        size_kb = os.path.getsize(_DASHBOARD_CACHE_FILE) / 1024
        print(f"  Cache written: {size_kb:.1f} KB", flush=True)

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] DONE in {elapsed:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
