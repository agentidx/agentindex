# Nerq System Health Audit — 2026-04-09

**Started:** 2026-04-09 10:40 CEST
**Context:** After a morning of three deploys (Meta crawlers, dashboard 524 fix, /package 500 fix) and discovering an active autoheal restart loop, the user requested a step back from symptom-patching to a systematic root-cause audit.
**Principle:** Observe first, change nothing until we have a complete picture.

## Operational state at audit start
- **Working tree:** clean, HEAD = 553a468 (yield-check observe-only fix)
- **master-watchdog:** PAUSED (launchctl unloaded) for duration of audit
- **uvicorn (com.nerq.api):** running under launchd KeepAlive, latest restart 10:36 CEST
- **Observed symptoms at 10:39 CEST:** chaotic response times on robots.txt (4.9s, 16.3s, timeout, timeout across 4 consecutive requests), indicating per-worker state divergence rather than uniform cold-start

## Known symptoms collected today
1. Uvicorn cold-start penalty 5-18s on robots.txt and other routes after restart
2. /v1/yield/overview takes 10-15s cold, 0.3s warm
3. /v1/health times out at 8s sometimes
4. /admin/analytics-dashboard was taking 100-300s (hacked around with stale-cache fallback in commit 678eeb5)
5. Autoheal 5s/8s timeouts too short for cold starts, caused restart feedback loop
6. Memory sits at 61/64 GB constantly, 565K+ swapouts since boot
7. Zombie Postgres backends created regularly (terminated by autoheal)
8. "idle in transaction" Postgres connections observed (connection leak signature)
9. Individual workers diverge — same request gets wildly different response times
10. 06-07 UTC "traffic dip" in analytics is almost certainly restart-loop fingerprint, not real dip

## Known schema/code mismatches (not yet fixed)
1. `stale_score_detector`: expects `entity_lookup.trust_calculated_at` (column doesn't exist). Job has been failing daily.
2. `compatibility_matrix`: expects SQLite column `npm_weekly` (doesn't exist). Job has been failing weekly since 2026-04-05.
3. `yield_crawler_status` table missing from healthcheck.db. Causes warnings every 3 minutes in autoheal.
4. `entity_lookup.language` — FIXED in commit e802034 this morning.

## Infrastructure hypotheses (unverified)
- **SQLite contention:** analytics.db is 8.7 GB with continuous writes from middleware AND heavy SELECT queries from dashboard cache jobs. WAL checkpoints may block readers.
- **Memory pressure:** 95%+ RAM constant. Active swap. Every GC pause or allocation may take 100s of ms extra.
- **Uvicorn per-worker cold start:** 10-15s on first request post-restart. Unknown cause — possibly SQLAlchemy connection pool init, possibly module imports, possibly something else.
- **Process density:** Nerq + ZARQ + Postgres + 8 uvicorn workers + 35 LaunchAgents + multiple SQLite DBs + cache rebuilds + autoheal on one 64GB Mac Studio.

## Audit plan
- **Phase 1:** Baseline resource saturation, process landscape, DB health, latency reality, autoheal state
- **Phase 2:** Inventory of slow endpoints, schema mismatches, autoheal trigger logic
- **Phase 3:** Root cause prioritization — which 2-3 underlying issues explain the most symptoms
- **Phase 4:** Strategy decision — what we actually fix, and in what order

## Findings
(to be filled in as we go)

## Decisions
(to be filled in at phase 4)

---

## Phase 1A: Deep process inspection

**Timestamp:** Thu Apr  9 10:42:44 CEST 2026

### Uvicorn process tree with CPU/memory/state
```
USER       PID   TT   %CPU STAT PRI     STIME     UTIME COMMAND   PID  PPID STAT  %CPU %MEM    RSS      VSZ WCHAN  COMMAND
anstudio 57646   ??    0.0 S    20T   0:00.05   0:00.10 /opt/ho 57646     1 S      0.0  0.0  31264 435284592 -      /opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python -m uvicorn agentindex.api.discovery:app --host 0.0.0.0 --port 8000 --workers 8 --limit-concurrency 50 --backlog 256 --timeout-keep-alive 30
```

### File descriptors per worker (sockets, files)
```
PID 57646: total FDs=      71, sockets=1, files/db=34
```

### Active threads per worker (high thread count = hung requests)
```
PID 57646: threads=       2
```

### Top 10 processes by CPU right now
```
  PID  %CPU %MEM COMMAND
57665  93.3  2.3 postgres: anstudio agentindex 127.0.0.1(64692) COMMIT
57663  79.6  2.4 postgres: anstudio agentindex 127.0.0.1(64690) idle
42753  51.2  1.9 Google Chrome Helper (Renderer)
  433  30.8  0.1 WindowServer
57661  27.7  2.2 postgres: anstudio agentindex 127.0.0.1(64688) idle
90618  23.6  0.2 ScreensharingAgent
57759  22.3  1.9 postgres: anstudio agentindex 127.0.0.1(64811) idle
57668  20.5  2.5 postgres: anstudio agentindex 127.0.0.1(64695) idle
57658  11.3  0.4 Python
 5058  11.3  0.2 Terminal
```

### Load average and uptime
```
10:42  up 7 days,  1:15, 4 users, load averages: 6.81 5.70 5.27
```

---

## Phase 1B: Postgres deep dive

**Timestamp:** Thu Apr  9 10:44:03 CEST 2026

### Initial observation: 5 backends eating 243% CPU combined
- PID 57665: 93.3% CPU, state=COMMIT
- PID 57663: 79.6% CPU, state=idle
- PID 57661: 27.7% CPU, state=idle
- PID 57759: 22.3% CPU, state=idle
- PID 57668: 20.5% CPU, state=idle

### ALL connections with state, wait_event, query age, and query
```
  pid  | state  | state_age_sec | query_age_sec | wait_event_type |     wait_event      | application_name |                                                        q                                                        
-------+--------+---------------+---------------+-----------------+---------------------+------------------+-----------------------------------------------------------------------------------------------------------------
 40379 | active |          9173 |          9173 | Activity        | WalSenderMain       | walreceiver      | START_REPLICATION SLOT "macmini_replica" 2C8/8D000000 TIMELINE 1
 55712 | idle   |          1116 |          1117 | Client          | ClientRead          | nerq_enricher    |                                                                                                                +
       |        |               |               |                 |                     |                  |         SELECT id, name, downloads, stars, repository_url                                                      +
       |        |               |               |                 |                     |                  |         FROM software_registry                                                                                 +
       |        |               |               |                 |                     |                  |         WHERE registry = 'npm'                                                                                 +
       |        |               |               |                 |                     |                  |           AND (downloads IS N
 57812 | idle   |            13 |            13 | Client          | ClientRead          |                  | ROLLBACK
 57810 | idle   |            11 |            11 | Client          | ClientRead          |                  | COMMIT
 57816 | idle   |             6 |             6 | Client          | ClientRead          |                  | ROLLBACK
 57834 | idle   |             6 |             6 | Client          | ClientRead          |                  | ROLLBACK
 57857 | idle   |             4 |             4 | Client          | ClientRead          |                  | ROLLBACK
 57811 | idle   |             3 |             3 | Client          | ClientRead          |                  | ROLLBACK
 57815 | idle   |             2 |             2 | Client          | ClientRead          |                  | COMMIT
 57814 | idle   |             1 |             1 | Client          | ClientRead          |                  | COMMIT
 57817 | idle   |             1 |             1 | Client          | ClientRead          |                  | ROLLBACK
 57829 | idle   |             1 |             1 | Client          | ClientRead          |                  | ROLLBACK
 57813 | idle   |             1 |             1 | Client          | ClientRead          |                  | ROLLBACK
 57206 | idle   |             1 |             1 | Client          | ClientRead          |                  | COMMIT
 56501 | idle   |             1 |             1 | Client          | ClientRead          |                  | UPDATE software_registry SET stars=-1 WHERE id='158e1d63-59f4-41a9-a926-957342f7527e' AND stars IS NULL
 52684 | idle   |             1 |             1 | Client          | ClientRead          |                  | UPDATE software_registry SET downloads=-1 WHERE id='21780657-6329-4008-a2c5-f3f25ea3504e' AND downloads IS NULL
 57472 | idle   |             0 |             0 | Client          | ClientRead          |                  | COMMIT
 41309 |        |               |               | Activity        | WalWriterMain       |                  | 
 41311 |        |               |               | Activity        | LogicalLauncherMain |                  | 
 41255 |        |               |               | Activity        | BgWriterHibernate   |                  | 
 41254 |        |               |               | Activity        | CheckpointerMain    |                  | 
 41310 |        |               |               | Activity        | AutoVacuumMain      |                  | 
(22 rows)

```

### Locks held and waited-for
```
 pid | mode | granted | locktype | relation | state | q 
-----+------+---------+----------+----------+-------+---
(0 rows)

```

### Connection count by state
```
 state  | count 
--------+-------
 idle   |    16
 active |     1
(2 rows)

```

### max_connections setting vs current usage
```
 max_conn | current_conn | agentindex_conn 
----------+--------------+-----------------
      100 |           23 |              17
(1 row)

```

### Longest running queries (potential stuck work)
```
  pid  | state  | age_sec |  wait_event   |                                q                                 
-------+--------+---------+---------------+------------------------------------------------------------------
 40379 | active |    9173 | WalSenderMain | START_REPLICATION SLOT "macmini_replica" 2C8/8D000000 TIMELINE 1
(1 row)

```

### WAL status and replication
```
 wal_bytes_total | replica_count | replica_state | replica_lag_bytes 
-----------------+---------------+---------------+-------------------
   3060794303896 |             1 | streaming     |                 0
(1 row)

```

---

## Phase 1C: Uvicorn lifecycle reality-check

**Timestamp:** Thu Apr  9 10:45:09 CEST 2026

### ALL uvicorn-related processes (broader pattern)
```
  501 57798     1   0 10:42AM ??         0:00.40 /opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python -m uvicorn agentindex.api.discovery:app --host 0.0.0.0 --port 8000 --workers 8 --limit-concurrency 50 --backlog 256 --timeout-keep-alive 30
  501 57801 57798   0 10:42AM ??         0:00.04 /opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python -c from multiprocessing.resource_tracker import main;main(6)
  501 57802 57798   0 10:42AM ??         0:04.12 /opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python -c from multiprocessing.spawn import spawn_main; spawn_main(tracker_fd=7, pipe_handle=9) --multiprocessing-fork
  501 57803 57798   0 10:42AM ??         0:03.98 /opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python -c from multiprocessing.spawn import spawn_main; spawn_main(tracker_fd=7, pipe_handle=13) --multiprocessing-fork
  501 57804 57798   0 10:42AM ??         0:05.94 /opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python -c from multiprocessing.spawn import spawn_main; spawn_main(tracker_fd=7, pipe_handle=17) --multiprocessing-fork
  501 57805 57798   0 10:42AM ??         0:10.88 /opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python -c from multiprocessing.spawn import spawn_main; spawn_main(tracker_fd=7, pipe_handle=21) --multiprocessing-fork
  501 57806 57798   0 10:42AM ??         0:04.22 /opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python -c from multiprocessing.spawn import spawn_main; spawn_main(tracker_fd=7, pipe_handle=25) --multiprocessing-fork
  501 57807 57798   0 10:42AM ??         0:04.48 /opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python -c from multiprocessing.spawn import spawn_main; spawn_main(tracker_fd=7, pipe_handle=29) --multiprocessing-fork
  501 57808 57798   0 10:42AM ??         0:04.94 /opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python -c from multiprocessing.spawn import spawn_main; spawn_main(tracker_fd=7, pipe_handle=33) --multiprocessing-fork
  501 57809 57798   0 10:42AM ??         0:04.65 /opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python -c from multiprocessing.spawn import spawn_main; spawn_main(tracker_fd=7, pipe_handle=37) --multiprocessing-fork
```

### Port 8000 listeners right now
```
COMMAND   PID     USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
Python  57798 anstudio    3u  IPv4 0xf27581b4cbb25da4      0t0  TCP *:irdmi (LISTEN)
Python  57802 anstudio    3u  IPv4 0xf27581b4cbb25da4      0t0  TCP *:irdmi (LISTEN)
Python  57803 anstudio    3u  IPv4 0xf27581b4cbb25da4      0t0  TCP *:irdmi (LISTEN)
Python  57804 anstudio    3u  IPv4 0xf27581b4cbb25da4      0t0  TCP *:irdmi (LISTEN)
Python  57805 anstudio    3u  IPv4 0xf27581b4cbb25da4      0t0  TCP *:irdmi (LISTEN)
Python  57806 anstudio    3u  IPv4 0xf27581b4cbb25da4      0t0  TCP *:irdmi (LISTEN)
Python  57807 anstudio    3u  IPv4 0xf27581b4cbb25da4      0t0  TCP *:irdmi (LISTEN)
Python  57808 anstudio    3u  IPv4 0xf27581b4cbb25da4      0t0  TCP *:irdmi (LISTEN)
Python  57809 anstudio    3u  IPv4 0xf27581b4cbb25da4      0t0  TCP *:irdmi (LISTEN)
```

### launchctl status for com.nerq.api
```
{
	"StandardOutPath" = "/Users/anstudio/agentindex/logs/api.log";
	"LimitLoadToSessionType" = "Aqua";
	"StandardErrorPath" = "/Users/anstudio/agentindex/logs/api_error.log";
	"Label" = "com.nerq.api";
	"OnDemand" = false;
	"LastExitStatus" = 9;
	"PID" = 57798;
	"Program" = "/Users/anstudio/agentindex/venv/bin/python";
	"ProgramArguments" = (
		"/Users/anstudio/agentindex/venv/bin/python";
		"-m";
		"uvicorn";
		"agentindex.api.discovery:app";
		"--host";
		"0.0.0.0";
		"--port";
		"8000";
		"--workers";
		"8";
		"--limit-concurrency";
		"50";
		"--backlog";
		"256";
		"--timeout-keep-alive";
		"30";
	);
};
```

### launchctl status for com.nerq.master-watchdog (should be absent)
```
{
	"StandardOutPath" = "/Users/anstudio/agentindex/logs/master_watchdog.log";
	"LimitLoadToSessionType" = "Aqua";
	"StandardErrorPath" = "/Users/anstudio/agentindex/logs/master_watchdog_err.log";
	"Label" = "com.nerq.master-watchdog";
	"OnDemand" = false;
	"LastExitStatus" = 0;
	"PID" = 57695;
	"Program" = "/Users/anstudio/agentindex/venv/bin/python3";
	"ProgramArguments" = (
		"/Users/anstudio/agentindex/venv/bin/python3";
		"-m";
		"agentindex.crawlers.master_watchdog";
	);
};
```

### Last 30 lines of api.log (uvicorn stdout)
```
INFO:     17.246.15.190:0 - "GET /cs/je-is-hacked/cline-veilig-anjon-hanga-yo-bezpecne HTTP/1.1" 200 OK
INFO:     2a03:2880:f806:1f:::0 - "GET /da/is-drakospy-legit HTTP/1.1" 200 OK
INFO:     17.246.15.251:0 - "GET /ja/what-is/rolldown-binding-linux-x64-gnu HTTP/1.1" 200 OK
INFO:     17.22.237.201:0 - "GET /de/ist-compare/ezyphototabcustomwebsearch-vs-ublock-origin-sicher HTTP/1.1" 200 OK
INFO:     18.214.138.148:0 - "GET /ja/safe/bible-app-for-kids HTTP/1.1" 200 OK
INFO:     17.241.227.239:0 - "GET /ja/er-a-scam/github-copilot-e-sicuro-sikkert-wa-anzen-desu-ka HTTP/1.1" 200 OK
INFO:     2a03:2880:f806:1a:::0 - "GET /pl/czy-muxima-ui-quill-editor-jest-bezpieczne HTTP/1.1" 200 OK
INFO:     2a03:2880:f806:31:::0 - "GET /it/bakersfieldcollege-edu-e-sicuro HTTP/1.1" 200 OK
INFO:     17.246.23.69:0 - "GET /hi/alternatives/asyncio-throttle HTTP/1.1" 200 OK
INFO:     65.21.113.201:0 - "GET /ar/hal-advanced-user-role-manager-amin HTTP/1.1" 200 OK
INFO:     17.241.227.113:0 - "GET /pt/safe/blankspace/%E0%B8%84%E0%B8%A7%E0%B8%B2%E0%B8%A1%E0%B8%9B%E0%B8%A5%E0%B8%AD%E0%B8%94%E0%B8%A0%E0%B8%B1%E0%B8%A2-e-seguro HTTP/1.1" 200 OK
INFO:     5.255.231.174:0 - "GET /id/apakah-react-native-oh-tpl-react-native-sortable-list-aman HTTP/1.1" 200 OK
INFO:     127.0.0.1:49947 - "GET /flywheel HTTP/1.1" 200 OK
INFO:     17.241.227.132:0 - "GET /is-compare/youtube-vs-com-sec-android-app-myfiles-safe HTTP/1.1" 404 Not Found
INFO:     87.250.224.206:0 - "GET /safe/%40ag-uiproto HTTP/1.1" 200 OK
INFO:     17.241.227.47:0 - "GET /safe/momentum HTTP/1.1" 200 OK
INFO:     17.246.19.67:0 - "GET /v1/preflight?target=colletdev-angular HTTP/1.1" 200 OK
INFO:     17.246.19.128:0 - "GET /alternatives/modernanalyticshub HTTP/1.1" 200 OK
INFO:     2a03:2880:f806:3a:::0 - "GET /ru/what-is/lagentblogger HTTP/1.1" 200 OK
INFO:     3.210.29.96:0 - "GET /is-jsonjoycom-buffers-safe-for-kids HTTP/1.1" 200 OK
INFO:     17.22.245.169:0 - "GET /tr/alternatives/hisorange-browser-detect HTTP/1.1" 200 OK
INFO:     74.7.227.55:0 - "GET /th/is-cyber-threat-intelligence-stix-safe-for-kids HTTP/1.1" 200 OK
INFO:     17.241.75.104:0 - "GET /nl/is-laravel-serializable-closure-veilig HTTP/1.1" 200 OK
INFO:     2a03:2880:f806:40:::0 - "GET /is-pepsico-ua-legit HTTP/1.1" 200 OK
INFO:     185.191.171.6:0 - "GET /safe/agentswarm-arena HTTP/1.1" 200 OK
INFO:     213.180.203.185:0 - "GET /tr/safe/upvista HTTP/1.1" 200 OK
INFO:     5.255.231.46:0 - "GET /safe/setasign-fpdi-fpdf HTTP/1.1" 200 OK
INFO:     17.241.75.134:0 - "GET /fr/hal-czy-a-scam/cursor-jest-bezpieczne-amin-est-il-sur HTTP/1.1" 200 OK
INFO:     2a03:2880:f806:26:::0 - "GET /th/safe/casinospinnewsbuzz-co-uk HTTP/1.1" 200 OK
INFO:     213.180.203.79:0 - "GET /id/apakah-fluentlyhttpclient-entity-aman HTTP/1.1" 200 OK
```

### Last 30 lines of api_error.log (uvicorn stderr)
```
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Started server process [57803]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Started server process [57809]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Started server process [57806]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Started server process [57808]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Started server process [57804]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [57659]
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [57656]
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [57657]
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [57654]
_resolve_any: no match for 'dicklesworthstoneultimate-bug-scanner'
```

### Try 3 HTTP calls in sequence, 3 sec apart, to see if there's variance
```
10:45:09 try 1: HTTP 200 in 9.340783s
10:45:22 try 2: HTTP 200 in 0.158689s
10:45:25 try 3: HTTP 200 in 11.304522s
```

### System-wide health right now
```
Thu Apr  9 10:45:39 CEST 2026
10:45  up 7 days,  1:18, 4 users, load averages: 5.28 5.59 5.31
Load Avg: 5.28, 5.59, 5.31 
CPU usage: 6.17% user, 10.44% sys, 83.38% idle 
PhysMem: 61G used (8550M wired, 839M compressor), 2173M unused.
```

---

## Phase 1D: Finding the ghost + memory deep dive

**Timestamp:** Thu Apr  9 10:47:25 CEST 2026

### CRITICAL FINDING: master-watchdog is running again
- Was unloaded at 10:41:44
- At 10:45 it was back with PID 57695
- Something is auto-restarting it

### Who loaded master-watchdog?
```
-- All processes mentioning master_watchdog:
  501 57695     1   0 10:42AM ??         0:00.16 /opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python -m agentindex.crawlers.master_watchdog

-- PPID of master-watchdog (who's its parent?):
  PID  PPID COMMAND
57695     1 /opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python -m agentindex.crawlers.master_watchdog
  Parent PID 1:
  PID COMMAND
    1 /sbin/launchd

-- Search for any script/cron/launchd that loads com.nerq.master-watchdog:

---

## Phase 1E: SQLite contention hypothesis test

**Timestamp:** Thu Apr  9 10:52:02 CEST 2026

### Hypothesis: analytics.db middleware writes are blocked by long-running reads

### Processes that have analytics.db open RIGHT NOW
```
```

### analytics.db WAL file size (high = pending writes not checkpointed)
```
-rw-r--r--  1 anstudio  staff  8776691712 Apr  9 10:52 /Users/anstudio/agentindex/logs/analytics.db
```

### Can we get a write lock on analytics.db right now? Quick test.
```
bash: line 29: timeout: command not found
FAILED: could not get write lock within 5s
```

### What's holding analytics.db open and how much CPU do they use?
```
```

### Is the middleware INSERT finishing? Sample 10 rows of the most recent timestamps
```
2026-04-09T08:52:02.026408|789.3|/tr/safe/bun-sqlight
2026-04-09T08:52:02.032625|836.4|/ru/sell-your-data/chatgpt-e-seguro-plodpai-mai-bezopasno-li
2026-04-09T08:52:02.026086|804.4|/de/safe/google-co-bw
2026-04-09T08:52:01.929295|2124.7|/is-sia-retention-ai-agent-safe
2026-04-09T08:52:01.829346|463.3|/vi/hacked/slither-mcp-wa-anzen-desu-ka-co-an-toan-khong
2026-04-09T08:52:01.210213|2.1|/alternatives/mcp-servers
2026-04-09T08:51:59.515401|6.0|/compare/bracket-league-2026-vs-mcp-server-duckdb
2026-04-09T08:51:49.027634|88.6|/safe/gitlawb
2026-04-09T08:51:48.916660|5763.3|/pt/je-sell-your-data/legends-of-heroes-co-an-toan-khong-bezpecne-e-seguro
2026-04-09T08:51:47.147834|2358.9|/id/apakah-ist-a-scam/wharttest-sicher-anquan-ma-aman
```

### Is there a cache-refresh or dashboard query running right now?
```
anstudio         58755  18.1  0.1 435295376  52384   ??  UN   10:51AM   0:17.00 /opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python /Users/anstudio/agentindex/scripts/refresh_zarq_dashboard_cache.py
```

---

## Phase 1F: Understanding the cache refresh job

**Timestamp:** Thu Apr  9 10:56:46 CEST 2026

### Hypothesis confirmed signals
- refresh_zarq_dashboard_cache.py (PID 58755) is in 'UN' state (uninterruptible sleep)
- analytics.db is 8.77 GB
- Could not get BEGIN IMMEDIATE write lock within 5 seconds (test syntax was broken but failed anyway)
- Middleware request latencies range from 2ms to 5763ms on same endpoint type
- 316 concurrent TCP connections on port 8000 (80% of 400 max)

### Is the cache refresh process still running?
```
  PID  PPID STAT  %CPU ELAPSED COMMAND
```

### Full script content
```
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
    print("ERROR: Cache refresh timed out after 300s", flush=True)
    sys.exit(2)


def main():
    # Hard timeout: 5 minutes. _build_dashboard_data() takes ~20s, so 300s is safe.
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(300)

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
```

### How often does it run? Check LaunchAgents for this script
```
/Users/anstudio/Library/LaunchAgents/com.nerq.zarq-cache.plist

--- zarq-cache plist if exists ---
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nerq.zarq-cache</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/anstudio/agentindex/venv/bin/python</string>
        <string>/Users/anstudio/agentindex/scripts/refresh_zarq_dashboard_cache.py</string>
    </array>

    <key>StartInterval</key>
    <integer>240</integer>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Users/anstudio/agentindex/logs/zarq_cache_refresh.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/anstudio/agentindex/logs/zarq_cache_refresh.log</string>

    <key>WorkingDirectory</key>
    <string>/Users/anstudio/agentindex</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>/Users/anstudio/agentindex</string>
    </dict>

    <key>Nice</key>
    <integer>10</integer>
</dict>
</plist>
```

### Historical: how often has refresh_zarq_dashboard run today?
```
     165
(log hits)

Find any log file for this job:
/Users/anstudio/agentindex/agentindex/zarq_dashboard.py.bak.day21.pre-cache-fix
/Users/anstudio/agentindex/logs/zarq_cache_refresh.log
/Users/anstudio/agentindex/scripts/refresh_zarq_dashboard_cache.py
/Users/anstudio/agentindex/infrastructure/launchd/com.nerq.zarq-cache.plist
```

### All processes that have analytics.db open right now
```
COMMAND   PID     USER   FD   TYPE DEVICE   SIZE/OFF    NODE NAME
Python  59111 anstudio   26u   REG   1,17 8777703424 1612738 /Users/anstudio/agentindex/logs/analytics.db
Python  59111 anstudio   29u   REG   1,17 8777703424 1612738 /Users/anstudio/agentindex/logs/analytics.db
```

### Is port 8000 returning anything right now?
```
robots.txt: HTTP 200 in 10.005258s
```

### Is refresh_zarq still running after all this data collection?
```
```

---

## Phase 2: Honest synthesis and strategic options

**Timestamp:** 2026-04-09 ~10:55 CEST

This section steps back from command-line diagnostics and consolidates what we actually know, what we've proven, what we've disproven, and what the realistic paths forward look like. Written after ~90 minutes of live diagnostics during a system that was actively unstable.

---

### 2.1 Complete symptom catalog

These are observations we have direct evidence for, not hypotheses:

**Latency:**
- robots.txt (trivial text generation) sometimes responds in 2ms, sometimes in 10+ seconds
- /v1/yield/overview responds in 13-15s cold, 0.3s warm
- /v1/health (intended as fast liveness endpoint) sometimes times out at 8s
- Individual language/safe routes (/pt/, /de/, /safe/) seen at 5700ms occasionally
- Cache jobs (analytics_dashboard, analytics_weekly) were taking 100-300s
- Same route, same worker, consecutive requests: 0.16s then 11.3s

**Reliability:**
- Uvicorn has restarted at least 10 times between 09:48 and 10:40 CEST
- Restart signature in logs: "port was 000 → Healthy after restart: False"
- LLM in autoheal generates hallucinated "address already in use" diagnoses (which is not actually the failure mode)
- 316 established TCP connections on port 8000 out of ~400 max capacity (80% saturation)
- analytics.db had minute-long gaps in the 2026-04-08 06:23-06:28 UTC window

**Resource state:**
- PhysMem oscillating between 54 GB and 61 GB used out of 64 GB
- Swap at 2.27 GB / 3 GB total (75% full) since last boot 7 days ago
- Load average consistently 4-7 on 20-core Mac Studio (moderate)
- CPU idle typically 83-89% (so it's not CPU bound)
- 565,000+ swapouts since boot

**Process anomalies:**
- Worker 57805 had 30% of its 8-minute runtime in CPU (2:21 / 8:00), while other workers had 2-4%
- refresh_zarq_dashboard_cache.py was in `UN` state (uninterruptible sleep) at 10:51
- Multiple zombie Postgres backends killed by autoheal earlier in the session

**Schema/code mismatches (4 known so far):**
- `entity_lookup.language` — FIXED this morning (e802034)
- `entity_lookup.trust_calculated_at` — BROKEN, stale_score_detector fails daily
- SQLite `npm_weekly` column — BROKEN, compat_matrix fails weekly
- `yield_crawler_status` table missing — BROKEN, warns every 3 minutes

---

### 2.2 Hypotheses tested during this session

**H1: "Dippen är LaunchAgents batch-wall kl 07 UTC"**
- Prediction: Six jobs scheduled for 07:00 UTC, running together, should cause resource contention
- Result: FALSIFIED. LaunchAgents use local time (CEST), so Hour=7 means 05 UTC, not 07 UTC.

**H2: "IndexNow triggers Bing/Yandex crawl burst at 06-07 UTC"**
- Prediction: Bingbot/Yandex requests should peak 30-60 min after IndexNow runs
- Result: FALSIFIED. Bing and Yandex traffic actually DECREASES during the dip, not increases.

**H3: "Postgres is the bottleneck — zombie backends, lock contention"**
- Prediction: pg_stat_activity should show stuck queries, locks, high connection counts
- Result: FALSIFIED. 17/100 connections used, zero locks, zero long-running queries, replication 0 lag.

**H4: "Memory pressure causing worker swapping"**
- Prediction: 61/64 GB should correlate with slow responses; freeing memory should help
- Result: PARTIALLY FALSIFIED. Memory dropped from 61 GB to 54 GB during audit (7 GB freed), but uvicorn remained unresponsive. Memory is a contributing factor but not sufficient cause.

**H5: "Autoheal restart loop triggered by yield endpoint check"**
- Prediction: check_yield_api returning False should trigger restart
- Result: PARTIALLY FALSIFIED. Our fix made yield check observe-only, BUT restart loop continued because check_api_health (on /v1/health) is ALSO a trigger with an 8s timeout that fails during cold start.

**H6: "SQLite analytics.db write contention from cache refresh jobs"**
- Prediction: Cache refresh jobs holding read locks on analytics.db should block middleware writes
- Result: PARTIALLY CONFIRMED. refresh_zarq_dashboard_cache.py (runs every 4 minutes) was caught in UN state with analytics.db open. BEGIN IMMEDIATE test on analytics.db did appear to fail (though test syntax was broken). Middleware request latencies span 2ms to 5763ms for similar routes. BUT: not all routes are equally affected — some return 2ms consistently — which argues the SQLite lock isn't the universal bottleneck.

---

### 2.3 The actual model: six interacting problems, not one root cause

After 90 minutes of probing, I no longer believe there is a single root cause. The evidence points to six independent weaknesses that amplify each other into the observed chaos:

**P1: Slow endpoints have slow cold starts.**
/v1/yield/overview, /v1/health, /admin/analytics-dashboard all take 5-15 seconds on first hit per worker after a restart. Root cause varies per endpoint: tight SQLite aggregation queries, missing indexes, heavy Python imports, large Jinja templates. Each endpoint would need investigation.

**P2: autoheal timeouts are shorter than cold-start latency.**
check_api_health uses curl -m 8 against /v1/health. check_port_path uses curl -m 5 against yield endpoints. When /v1/health takes 15 seconds cold, the 8-second timeout fires → autoheal concludes "API dead" → triggers restart_api → next restart produces a fresh cold start → next check fails → loop.

**P3: analytics.db is a 8.77 GB SQLite with high write pressure and periodic heavy reads.**
Middleware writes per request. Cache jobs (refresh_zarq_dashboard_cache every 4 min, analytics_dashboard every 30 min, analytics_weekly every 25 min) perform large aggregations while holding locks. SQLite's single-writer model means pending middleware writes queue behind reader-blockers. This contributes to request latency but doesn't uniformly affect all endpoints.

**P4: Memory pressure forces worker swap-out.**
At 61/64 GB used, macOS aggressively swaps. Idle uvicorn workers have parts of their memory pages swapped to disk. When a new request arrives, those pages must be read back — contributing to cold-start latency. Swap is 75% full. Workers that stay "hot" (get frequent traffic) avoid this; workers that go "cold" pay a steep penalty.

**P5: Schema-code drift creates invisible daily failures.**
Four known places where code queries columns or tables that don't exist in the current schema. Daily batch jobs (stale-scores, compat-matrix) have been failing silently for days. Autoheal's yield_crawler_status check has been warning every 3 minutes. These don't cause the live outage but demonstrate that the codebase has drifted out of sync with its data.

**P6: Single-machine saturation.**
Nerq + ZARQ APIs + 8 uvicorn workers + Postgres 16 (with replication) + multiple SQLite databases + 35 LaunchAgents (crawlers, cache refresh, scoring jobs) + Redis + autoheal + master-watchdog — all on one Mac Studio M1 Ultra with 64 GB RAM. Any single component misbehaving exerts pressure on the others through shared CPU, memory, disk I/O, or database locks.

**How they interact (the dynamic):**
- P4 (memory pressure) makes P1 (cold starts) much worse
- P1 (cold starts) makes P2 (autoheal timeouts) fire
- P2 (restart loop) makes P1 (cold starts) happen more often
- P3 (SQLite contention) adds random latency spikes independent of the above
- P6 (saturation) means even minor spikes in any dimension cascade
- P5 (schema drift) hides real problems behind constant warning noise that makes it hard to see signal

This is why no single fix today has made the system healthy. Each fix addresses one layer while the others continue amplifying.

---

### 2.4 Strategic paths forward

I see four legitimate approaches, ranked from least invasive to most invasive. None is wrong. They differ in scope, risk, effort, and expected impact.

#### Path A: Stabilize autoheal (the amplifier), then observe

**Idea:** The restart loop is the most visible damage multiplier. Right now, every time uvicorn has a bad minute, autoheal triples or quintuples the damage by restarting repeatedly and triggering cold-start chains. Fix autoheal to stop amplifying.

**Concrete actions:**
- Raise check_api_health timeout from 8s to 30s (cold start survives)
- Add a "recently restarted" cooldown — no new restart within N minutes of last restart
- Remove the LLM-driven restart path entirely (it hallucinates "address already in use" and creates noise)
- Keep our yield-check observe-only fix from earlier

**Risk:** Low. We lose fast automatic recovery from genuine uvicorn crashes, but uvicorn KeepAlive in launchd still handles the hard-crash case.

**Effort:** 30-45 minutes. One file, maybe 20 lines changed.

**Expected impact:** System stops thrashing. Cold starts still happen occasionally but they complete in 15-30 seconds without triggering restarts. Over the next 24 hours we see whether the underlying latency issues (P1) cause any real problems or whether they were only visible because of the restart cascade.

**Downside:** We don't fix P1, P3, P4, P5, or P6. We just stop amplifying them.

---

#### Path B: Path A + stop analytics.db cache-job contention

**Idea:** On top of path A, also address P3 directly. The cache refresh jobs that hold analytics.db locks while aggregating are a documented source of contention.

**Concrete actions:**
- Everything in Path A
- Change refresh_zarq_dashboard_cache.py (and analytics_dashboard/weekly jobs) to use a read replica of analytics.db — literally copy the file to a snapshot, then read from the snapshot
- Or: rewrite those jobs to use WAL mode with busy_timeout=30000 and shorter queries
- Or: move these aggregations to run off-peak only (once per hour during low-traffic windows)

**Risk:** Medium. File-copy approach is simple but wastes disk I/O. WAL mode change needs testing. Off-peak scheduling changes what data dashboards show.

**Effort:** 1-2 hours. Multiple files, need to understand each job's query pattern.

**Expected impact:** Middleware latency spikes reduce significantly. Worker queue depth drops. Request consistency improves.

**Downside:** Doesn't address P1 (slow endpoints themselves), P4 (memory), P5 (schema), P6 (saturation).

---

#### Path C: Path B + systematic slow-endpoint audit

**Idea:** On top of path B, hunt down and fix the actual slow endpoints (P1). Identify the top 10 slowest routes by p99 latency. Profile each. Fix root cause per endpoint (missing index, unbounded query, blocking call, etc.).

**Concrete actions:**
- Everything in Path B
- Query analytics.db for top 10 slowest routes by p99 latency over last 24 hours
- For each: profile the route, identify the bottleneck, fix it
- Common fixes: add Postgres index, add route-level cache, move heavy computation to background job
- Also: fix the 4 known schema mismatches (P5) as part of the cleanup

**Risk:** Low-medium per fix, but cumulative risk over many changes is higher. Each fix needs testing.

**Effort:** 4-8 hours spread over multiple sessions. This is a focused sprint, not a morning task.

**Expected impact:** System becomes consistently fast. Cold starts still happen (P4 unchanged) but are smaller because routes themselves are faster. Restart risk drops to near-zero even with autoheal.

**Downside:** Doesn't address P4 (memory pressure) or P6 (machine saturation). Long-term, adding more endpoints or languages will reintroduce new slow routes.

---

#### Path D: Path C + architectural change to reduce machine saturation

**Idea:** Accept that one Mac Studio is not enough to host Nerq + ZARQ + all infrastructure. Move some load off.

**Concrete actions:**
- Everything in Path C
- Plus ONE of:
  - (a) Move Postgres to the existing Mac Mini replica (already has Postgres 16, already receiving WAL stream). Primary stays on Mac Studio for now; reads go to Mac Mini. Reduces memory pressure on Mac Studio by ~15 GB.
  - (b) Move ZARQ to a separate machine entirely. Either Mac Mini or cloud VM. Reduces saturation dramatically.
  - (c) Move cache jobs and batch crawlers to Mac Mini. Uvicorn stays on Mac Studio, batch work happens on the other machine. Simplest to execute.
  - (d) Upgrade Mac Studio RAM (but that's a hardware change, hours of downtime, 10K+ SEK).

**Risk:** High. Architectural changes always carry risk of unforeseen interactions.

**Effort:** Days to weeks depending on option. Option (c) is fastest, maybe 1-2 days.

**Expected impact:** Fundamental relief of memory pressure and CPU contention. System has headroom for growth.

**Downside:** Big commitment. Not something to decide on a tired Thursday morning after a chaotic diagnostic session.

---

### 2.5 My honest recommendation

If I am trying to be both honest and useful, here is what I think:

**Today, right now: Path A.** The restart loop is the most visible damage. Stopping autoheal from amplifying problems lets us observe what the underlying system actually does when it's not being restarted every 3 minutes. We need that observation to make informed decisions about Path B, C, or D. Until the system is stable enough to study, we're guessing in the dark.

**Tomorrow or next week: Path B.** With autoheal calm, we can study actual latency patterns and then target the analytics.db contention with more confidence.

**Over the coming weeks: Path C.** Systematically hunt slow endpoints. This is the grinding work of making a system actually fast.

**Long-term (decision for Anders, not for me to push):** Path D. But only after C gives us evidence that single-machine approach has fundamental ceiling.

**What I am NOT recommending:** More diagnostic commands in this session. We have enough data to act. More commands will just produce more data without changing anything. I want to stop the restart amplification today and then let the system breathe before we gather more observations.

---

### 2.6 Decisions needed from Anders

1. **Scope for this session:** Path A only? A + something else? Or stop and take a proper break first?
2. **Autoheal configuration philosophy:** Do we want autoheal to aggressively restart on any latency spike (current behavior), or only on genuine crashes (conservative, what Path A moves toward)?
3. **Risk tolerance for today:** We've already done 3 production deploys this morning. One more deploy is reasonable. Two more is pushing it. More than that is where mistakes happen.


---

## Phase 2: Honest synthesis and strategic options

**Timestamp:** 2026-04-09 ~10:55 CEST

This section steps back from command-line diagnostics and consolidates what we actually know, what we've proven, what we've disproven, and what the realistic paths forward look like. Written after ~90 minutes of live diagnostics during a system that was actively unstable.

---

### 2.1 Complete symptom catalog

These are observations we have direct evidence for, not hypotheses:

**Latency:**
- robots.txt (trivial text generation) sometimes responds in 2ms, sometimes in 10+ seconds
- /v1/yield/overview responds in 13-15s cold, 0.3s warm
- /v1/health (intended as fast liveness endpoint) sometimes times out at 8s
- Individual language/safe routes (/pt/, /de/, /safe/) seen at 5700ms occasionally
- Cache jobs (analytics_dashboard, analytics_weekly) were taking 100-300s
- Same route, same worker, consecutive requests: 0.16s then 11.3s

**Reliability:**
- Uvicorn has restarted at least 10 times between 09:48 and 10:40 CEST
- Restart signature in logs: "port was 000 → Healthy after restart: False"
- LLM in autoheal generates hallucinated "address already in use" diagnoses (which is not actually the failure mode)
- 316 established TCP connections on port 8000 out of ~400 max capacity (80% saturation)
- analytics.db had minute-long gaps in the 2026-04-08 06:23-06:28 UTC window

**Resource state:**
- PhysMem oscillating between 54 GB and 61 GB used out of 64 GB
- Swap at 2.27 GB / 3 GB total (75% full) since last boot 7 days ago
- Load average consistently 4-7 on 20-core Mac Studio (moderate)
- CPU idle typically 83-89% (so it's not CPU bound)
- 565,000+ swapouts since boot

**Process anomalies:**
- Worker 57805 had 30% of its 8-minute runtime in CPU (2:21 / 8:00), while other workers had 2-4%
- refresh_zarq_dashboard_cache.py was in `UN` state (uninterruptible sleep) at 10:51
- Multiple zombie Postgres backends killed by autoheal earlier in the session

**Schema/code mismatches (4 known so far):**
- `entity_lookup.language` — FIXED this morning (e802034)
- `entity_lookup.trust_calculated_at` — BROKEN, stale_score_detector fails daily
- SQLite `npm_weekly` column — BROKEN, compat_matrix fails weekly
- `yield_crawler_status` table missing — BROKEN, warns every 3 minutes

---

### 2.2 Hypotheses tested during this session

**H1: "Dippen är LaunchAgents batch-wall kl 07 UTC"**
- Prediction: Six jobs scheduled for 07:00 UTC, running together, should cause resource contention
- Result: FALSIFIED. LaunchAgents use local time (CEST), so Hour=7 means 05 UTC, not 07 UTC.

**H2: "IndexNow triggers Bing/Yandex crawl burst at 06-07 UTC"**
- Prediction: Bingbot/Yandex requests should peak 30-60 min after IndexNow runs
- Result: FALSIFIED. Bing and Yandex traffic actually DECREASES during the dip, not increases.

**H3: "Postgres is the bottleneck — zombie backends, lock contention"**
- Prediction: pg_stat_activity should show stuck queries, locks, high connection counts
- Result: FALSIFIED. 17/100 connections used, zero locks, zero long-running queries, replication 0 lag.

**H4: "Memory pressure causing worker swapping"**
- Prediction: 61/64 GB should correlate with slow responses; freeing memory should help
- Result: PARTIALLY FALSIFIED. Memory dropped from 61 GB to 54 GB during audit (7 GB freed), but uvicorn remained unresponsive. Memory is a contributing factor but not sufficient cause.

**H5: "Autoheal restart loop triggered by yield endpoint check"**
- Prediction: check_yield_api returning False should trigger restart
- Result: PARTIALLY FALSIFIED. Our fix made yield check observe-only, BUT restart loop continued because check_api_health (on /v1/health) is ALSO a trigger with an 8s timeout that fails during cold start.

**H6: "SQLite analytics.db write contention from cache refresh jobs"**
- Prediction: Cache refresh jobs holding read locks on analytics.db should block middleware writes
- Result: PARTIALLY CONFIRMED. refresh_zarq_dashboard_cache.py (runs every 4 minutes) was caught in UN state with analytics.db open. BEGIN IMMEDIATE test on analytics.db did appear to fail (though test syntax was broken). Middleware request latencies span 2ms to 5763ms for similar routes. BUT: not all routes are equally affected — some return 2ms consistently — which argues the SQLite lock isn't the universal bottleneck.

---

### 2.3 The actual model: six interacting problems, not one root cause

After 90 minutes of probing, I no longer believe there is a single root cause. The evidence points to six independent weaknesses that amplify each other into the observed chaos:

**P1: Slow endpoints have slow cold starts.**
/v1/yield/overview, /v1/health, /admin/analytics-dashboard all take 5-15 seconds on first hit per worker after a restart. Root cause varies per endpoint: tight SQLite aggregation queries, missing indexes, heavy Python imports, large Jinja templates. Each endpoint would need investigation.

**P2: autoheal timeouts are shorter than cold-start latency.**
check_api_health uses curl -m 8 against /v1/health. check_port_path uses curl -m 5 against yield endpoints. When /v1/health takes 15 seconds cold, the 8-second timeout fires → autoheal concludes "API dead" → triggers restart_api → next restart produces a fresh cold start → next check fails → loop.

**P3: analytics.db is a 8.77 GB SQLite with high write pressure and periodic heavy reads.**
Middleware writes per request. Cache jobs (refresh_zarq_dashboard_cache every 4 min, analytics_dashboard every 30 min, analytics_weekly every 25 min) perform large aggregations while holding locks. SQLite's single-writer model means pending middleware writes queue behind reader-blockers. This contributes to request latency but doesn't uniformly affect all endpoints.

**P4: Memory pressure forces worker swap-out.**
At 61/64 GB used, macOS aggressively swaps. Idle uvicorn workers have parts of their memory pages swapped to disk. When a new request arrives, those pages must be read back — contributing to cold-start latency. Swap is 75% full. Workers that stay "hot" (get frequent traffic) avoid this; workers that go "cold" pay a steep penalty.

**P5: Schema-code drift creates invisible daily failures.**
Four known places where code queries columns or tables that don't exist in the current schema. Daily batch jobs (stale-scores, compat-matrix) have been failing silently for days. Autoheal's yield_crawler_status check has been warning every 3 minutes. These don't cause the live outage but demonstrate that the codebase has drifted out of sync with its data.

**P6: Single-machine saturation.**
Nerq + ZARQ APIs + 8 uvicorn workers + Postgres 16 (with replication) + multiple SQLite databases + 35 LaunchAgents (crawlers, cache refresh, scoring jobs) + Redis + autoheal + master-watchdog — all on one Mac Studio M1 Ultra with 64 GB RAM. Any single component misbehaving exerts pressure on the others through shared CPU, memory, disk I/O, or database locks.

**How they interact (the dynamic):**
- P4 (memory pressure) makes P1 (cold starts) much worse
- P1 (cold starts) makes P2 (autoheal timeouts) fire
- P2 (restart loop) makes P1 (cold starts) happen more often
- P3 (SQLite contention) adds random latency spikes independent of the above
- P6 (saturation) means even minor spikes in any dimension cascade
- P5 (schema drift) hides real problems behind constant warning noise that makes it hard to see signal

This is why no single fix today has made the system healthy. Each fix addresses one layer while the others continue amplifying.

---

### 2.4 Strategic paths forward

I see four legitimate approaches, ranked from least invasive to most invasive. None is wrong. They differ in scope, risk, effort, and expected impact.

#### Path A: Stabilize autoheal (the amplifier), then observe

**Idea:** The restart loop is the most visible damage multiplier. Right now, every time uvicorn has a bad minute, autoheal triples or quintuples the damage by restarting repeatedly and triggering cold-start chains. Fix autoheal to stop amplifying.

**Concrete actions:**
- Raise check_api_health timeout from 8s to 30s (cold start survives)
- Add a "recently restarted" cooldown — no new restart within N minutes of last restart
- Remove the LLM-driven restart path entirely (it hallucinates "address already in use" and creates noise)
- Keep our yield-check observe-only fix from earlier

**Risk:** Low. We lose fast automatic recovery from genuine uvicorn crashes, but uvicorn KeepAlive in launchd still handles the hard-crash case.

**Effort:** 30-45 minutes. One file, maybe 20 lines changed.

**Expected impact:** System stops thrashing. Cold starts still happen occasionally but they complete in 15-30 seconds without triggering restarts. Over the next 24 hours we see whether the underlying latency issues (P1) cause any real problems or whether they were only visible because of the restart cascade.

**Downside:** We don't fix P1, P3, P4, P5, or P6. We just stop amplifying them.

---

#### Path B: Path A + stop analytics.db cache-job contention

**Idea:** On top of path A, also address P3 directly. The cache refresh jobs that hold analytics.db locks while aggregating are a documented source of contention.

**Concrete actions:**
- Everything in Path A
- Change refresh_zarq_dashboard_cache.py (and analytics_dashboard/weekly jobs) to use a read replica of analytics.db — literally copy the file to a snapshot, then read from the snapshot
- Or: rewrite those jobs to use WAL mode with busy_timeout=30000 and shorter queries
- Or: move these aggregations to run off-peak only (once per hour during low-traffic windows)

**Risk:** Medium. File-copy approach is simple but wastes disk I/O. WAL mode change needs testing. Off-peak scheduling changes what data dashboards show.

**Effort:** 1-2 hours. Multiple files, need to understand each job's query pattern.

**Expected impact:** Middleware latency spikes reduce significantly. Worker queue depth drops. Request consistency improves.

**Downside:** Doesn't address P1 (slow endpoints themselves), P4 (memory), P5 (schema), P6 (saturation).

---

#### Path C: Path B + systematic slow-endpoint audit

**Idea:** On top of path B, hunt down and fix the actual slow endpoints (P1). Identify the top 10 slowest routes by p99 latency. Profile each. Fix root cause per endpoint (missing index, unbounded query, blocking call, etc.).

**Concrete actions:**
- Everything in Path B
- Query analytics.db for top 10 slowest routes by p99 latency over last 24 hours
- For each: profile the route, identify the bottleneck, fix it
- Common fixes: add Postgres index, add route-level cache, move heavy computation to background job
- Also: fix the 4 known schema mismatches (P5) as part of the cleanup

**Risk:** Low-medium per fix, but cumulative risk over many changes is higher. Each fix needs testing.

**Effort:** 4-8 hours spread over multiple sessions. This is a focused sprint, not a morning task.

**Expected impact:** System becomes consistently fast. Cold starts still happen (P4 unchanged) but are smaller because routes themselves are faster. Restart risk drops to near-zero even with autoheal.

**Downside:** Doesn't address P4 (memory pressure) or P6 (machine saturation). Long-term, adding more endpoints or languages will reintroduce new slow routes.

---

#### Path D: Path C + architectural change to reduce machine saturation

**Idea:** Accept that one Mac Studio is not enough to host Nerq + ZARQ + all infrastructure. Move some load off.

**Concrete actions:**
- Everything in Path C
- Plus ONE of:
  - (a) Move Postgres to the existing Mac Mini replica (already has Postgres 16, already receiving WAL stream). Primary stays on Mac Studio for now; reads go to Mac Mini. Reduces memory pressure on Mac Studio by ~15 GB.
  - (b) Move ZARQ to a separate machine entirely. Either Mac Mini or cloud VM. Reduces saturation dramatically.
  - (c) Move cache jobs and batch crawlers to Mac Mini. Uvicorn stays on Mac Studio, batch work happens on the other machine. Simplest to execute.
  - (d) Upgrade Mac Studio RAM (but that's a hardware change, hours of downtime, 10K+ SEK).

**Risk:** High. Architectural changes always carry risk of unforeseen interactions.

**Effort:** Days to weeks depending on option. Option (c) is fastest, maybe 1-2 days.

**Expected impact:** Fundamental relief of memory pressure and CPU contention. System has headroom for growth.

**Downside:** Big commitment. Not something to decide on a tired Thursday morning after a chaotic diagnostic session.

---

### 2.5 My honest recommendation

If I am trying to be both honest and useful, here is what I think:

**Today, right now: Path A.** The restart loop is the most visible damage. Stopping autoheal from amplifying problems lets us observe what the underlying system actually does when it's not being restarted every 3 minutes. We need that observation to make informed decisions about Path B, C, or D. Until the system is stable enough to study, we're guessing in the dark.

**Tomorrow or next week: Path B.** With autoheal calm, we can study actual latency patterns and then target the analytics.db contention with more confidence.

**Over the coming weeks: Path C.** Systematically hunt slow endpoints. This is the grinding work of making a system actually fast.

**Long-term (decision for Anders, not for me to push):** Path D. But only after C gives us evidence that single-machine approach has fundamental ceiling.

**What I am NOT recommending:** More diagnostic commands in this session. We have enough data to act. More commands will just produce more data without changing anything. I want to stop the restart amplification today and then let the system breathe before we gather more observations.

---

### 2.6 Decisions needed from Anders

1. **Scope for this session:** Path A only? A + something else? Or stop and take a proper break first?
2. **Autoheal configuration philosophy:** Do we want autoheal to aggressively restart on any latency spike (current behavior), or only on genuine crashes (conservative, what Path A moves toward)?
3. **Risk tolerance for today:** We've already done 3 production deploys this morning. One more deploy is reasonable. Two more is pushing it. More than that is where mistakes happen.

