#!/usr/bin/env python3
"""
Refresh analytics weekly dashboard cache.

Runs _query_data() from analytics_weekly.py and writes the result to
/tmp/nerq_analytics_weekly.json so the dashboard endpoint never runs
the slow 50-second build under an HTTP request.

Designed to be run by launchd every 25 minutes (slightly faster than
the 30-minute _CACHE_TTL so cache is always fresh).
"""
import sys
import os
import time
import json
import signal

sys.path.insert(0, '/Users/anstudio/agentindex')


def timeout_handler(signum, frame):
    print("ERROR: Cache refresh timed out after 600s", flush=True)
    sys.exit(2)


def main():
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(600)

    try:
        from agentindex.analytics_weekly import _query_data, _CACHE_FILE
    except Exception as e:
        print(f"ERROR: Failed to import analytics_weekly: {e}", flush=True)
        return 1

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting weekly analytics cache refresh", flush=True)
    print(f"  Target: {_CACHE_FILE}", flush=True)

    start = time.time()
    try:
        data = _query_data()
    except Exception as e:
        elapsed = time.time() - start
        print(f"ERROR: _query_data() failed after {elapsed:.1f}s: {e}", flush=True)
        return 1

    elapsed = time.time() - start
    print(f"  Query completed in {elapsed:.1f}s", flush=True)

    try:
        with open(_CACHE_FILE + ".tmp", "w") as f:
            json.dump(data, f)
        os.replace(_CACHE_FILE + ".tmp", _CACHE_FILE)
    except Exception as e:
        print(f"ERROR: Failed to write cache: {e}", flush=True)
        return 1

    size_kb = os.path.getsize(_CACHE_FILE) / 1024
    print(f"  Cache written: {size_kb:.1f} KB", flush=True)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] DONE in {elapsed:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
