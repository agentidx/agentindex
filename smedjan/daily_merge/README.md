# Modell 3 — Daily-merge (factory-v0 → main)

**Status:** design draft 2026-04-28 (FAS 2 av Hybrid-plan)

## Syfte

Automatisera dygnsmerge av "värdefulla" commits från `smedjan-factory-v0`
till `main`, med:
- Cherry-pick av `agentindex/`-paths
- Direct file-copy av `smedjan/`-paths (eftersom paketet bara existerar i factory)
- Filtrering av noise (audit-spam, FB-F1/F2/F3, docs, chore)
- Smoke-test + canary monitor
- Auto-rollback vid 5xx-burst
- Daily report till `~/smedjan/audit-reports/daily-merge-YYYYMMDD.md`

## Arkitektur

```
smedjan/daily_merge/
├── README.md                    (denna fil)
├── __init__.py
├── classifier.py                ← bestämmer per commit: cherry-pick / file-copy / skip
├── cherry_pick.py               ← apply_cherry_picks(commits)
├── file_copy.py                 ← sync smedjan/ tree från factory → main
├── smoke_test.py                ← 8 endpoints + 5 localized + 10 sacred-bytes
├── canary.py                    ← 30 min 5xx-watch, auto-rollback at >5/2min
├── rollback.py                  ← tag pre-run, restore on fail
├── report.py                    ← skriv ~/smedjan/audit-reports/daily-merge-YYYYMMDD.md
├── drift_detector.py            ← upptäck commits som körts utan att vara i main:s history
└── cli.py                       ← subcommands: dry-run / run / status / rollback / skip
```

## CLI

```bash
smedjan merge dry-run              # visa vad som skulle göras (ingen ändring)
smedjan merge run                  # manuell trigger
smedjan merge status               # senaste run + nästa schedule
smedjan merge skip <task-id>       # markera task som "do not auto-merge"
smedjan merge rollback             # rulla tillbaka senaste run
```

## Filtrering — kategorier (från factory-main-merge-plan-20260428.md)

| Kategori | Regel | Hantering |
|---|---|---|
| **A — feat** | `feat(`, `feat:`, `smedjan T*` med `agentindex/`-files | Cherry-pick (eller file-copy om bara `smedjan/`) |
| **B — fix** | `fix(`, `fix:` med `agentindex/`-files | Cherry-pick |
| **D — worker-internal** | bara `smedjan/`-files | File-copy om relevant module, annars skip |
| **E — noise** | `audit(`, `FB-F[123]-`, `chore`, `docs:` med bara docs/ | Skip permanent |
| Risk=high | i task-DB markerat risk_level='high' | `needs_anders_review` (manual) |

## Restart-procedur — alltid `kickstart -k`

**Aldrig** `launchctl unload + load` (port 8000 race-condition observed
multiple times this session — `[Errno 48] Address already in use` triggar
KeepAlive-restart-loop tills port lediggjordes, ger ~3 min outage).

```bash
launchctl kickstart -k gui/501/com.nerq.api
```

`kickstart -k` skickar SIGTERM och startar nytt instans när det gamla
exited — undviker race. **Alla post-merge API-restarts i Modell 3 använder
detta**.

## Pre-run rollback-tag

Före varje merge-run:
```bash
ROLLBACK_TAG="daily-merge-rollback-$(date +%Y%m%d)"
git tag -f "$ROLLBACK_TAG" main
```

`-f` overrider om dagens tag redan finns (idempotent vid retry). Tagg
behålls 7 dagar (separat cleanup-job).

Auto-rollback (kallas av canary om 5xx-burst):
```bash
git reset --hard "$ROLLBACK_TAG"
launchctl kickstart -k gui/501/com.nerq.api
```

## Drift-detector — exempel 6ce9974

**Anomali observerad 2026-04-28**: Anders' commit `6ce9974` (sync_agent_slugs
COALESCE-fix från 2026-04-23) kördes mot main-tree's `auto_generate_pages.py`
2026-04-24 (gav +24,178 nya slugs uplift) — men `git log --oneline -- agentindex/auto_generate_pages.py`
på main visar inte commiten i historiken. Sista log-entry är `49ce251` (gammalt).

Drift-detector bör:
1. För varje fil i `agentindex/`-tree, jämför `git log` på factory-v0 vs main.
2. Om factory har commit X som modifierar fil F men main inte har den i
   F:s log-history → flagga som "potential drift".
3. Bonus: jämför disk-content (`git show main:F | sha256` vs `git show factory:F | sha256`).
   Om sha256 matchar trots att log skiljer → fixen kördes via direkt
   working-tree-edit (utan commit på main), eller cherry-pick som
   senare blev "garbage-collected" från reachability.

```python
def detect_drift_for_file(path: str) -> dict | None:
    factory_log = git_log("smedjan-factory-v0", path)
    main_log    = git_log("main", path)
    factory_commits = {c.short_hash for c in factory_log}
    main_commits    = {c.short_hash for c in main_log}
    only_factory = factory_commits - main_commits
    if not only_factory:
        return None
    # Compare blob-content
    factory_blob = sha256(git_show("smedjan-factory-v0", path))
    main_blob    = sha256(git_show("main", path))
    return {
        "file": path,
        "factory_only_commits": list(only_factory),
        "blob_match": factory_blob == main_blob,
        "anomaly_type": (
            "blob-match-history-mismatch"     # fix ran via direct edit
            if factory_blob == main_blob
            else "blob-mismatch-needs-merge"  # fix not yet on main
        ),
    }
```

Skriv resultaten till daily-rapporten under "Drift anomalies".

## File-copy strategy (smedjan/-tree)

Eftersom `agentindex/smedjan/` har bara `audits/, measurement/, renderers/, scripts/`
och saknar `planner.py, worker.py, sources.py, factory_core.py, config.py, ntfy.py`
etc, vill vi **inte** automatiskt kopiera 100+ filer på första körningen.

**Strategi**: bara kopiera filer som någon av de godkända commits *touchade*.
Det betyder första körningen drar in den minimala set som de 71 A+B-commits
behöver, inte hela package-trädet.

```python
def files_to_sync(commits: list[Commit]) -> set[Path]:
    """For each commit in factory range, find files under smedjan/ it touches.
    Return as set so dups dedupe."""
    return {f for c in commits for f in c.files if f.startswith("smedjan/")}
```

## Smoke-test

Existing pattern (post-cherry-pick verification):
- 8 base endpoints: /safe/react, /compare/react-vs-vue, /rating/{slug}.json,
  /signals, /dependencies, /dimensions, /model/react, /v1/agent/stats
- 5 localized: /<lang>/safe/<slug> (5 olika lang-koder × 5 olika slugs)
- 10 sacred-bytes: random pages, verifiera `pplx-verdict`, `ai-summary`,
  FAQPage JSON-LD intakta

All 200 + sacred bytes intakta = pass.

## Canary

30 min post-restart watch på api.log, räkna 5xx per min.
- `>5/2min sustained` (= 2 ticks i rad) → auto-rollback
- Annars: pass

## Rollback-tagging

```bash
git tag daily-merge-rollback-$(date +%Y%m%d) main
```
Före varje run. Behålls 7 dagar (cleanup-job rensar äldre).

Auto-rollback:
```bash
git reset --hard daily-merge-rollback-$(date +%Y%m%d)
launchctl kickstart -k gui/501/com.nerq.api
```

## Drift-detector

Upptäck commits som körts (effekt synlig i prod) men finns ej i main:s
git-history för den filen. **Exempel: 6ce9974** (Anders sync_agent_slugs
fix från 23/4 — vi körde scriptet 24/4 och fick +24K slugs uplift, men
git log på `agentindex/auto_generate_pages.py` visar inte 6ce9974 i main:s
history för filen).

```python
def detect_drift(file_path: Path) -> list[Commit]:
    """Find commits on factory-v0 that touched file_path but where the
    final on-main content does not include their effective changes."""
    factory_commits = git_log("smedjan-factory-v0", file_path)
    main_commits    = git_log("main", file_path)
    main_blob_hash  = git_show_blob("main", file_path)

    suspicious = []
    for c in factory_commits:
        if c.hash not in {m.hash for m in main_commits}:
            # Hash not on main — ev. drift
            suspicious.append(c)
    return suspicious
```

Drift-fynd skrivs till daily-rapporten under "Anomalier".

## LaunchAgent plist (com.nerq.smedjan.daily-merge.plist)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" ...>
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nerq.smedjan.daily-merge</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/anstudio/agentindex-factory/scripts/smedjan</string>
        <string>merge</string>
        <string>run</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>3</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/anstudio/smedjan/worker-logs/daily-merge.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/anstudio/smedjan/worker-logs/daily-merge.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

Tider: 03:00 lokal (= 01:00 UTC sommartid). Lugnt fönster.

## Daily report — exempel

Filnamn: `~/smedjan/audit-reports/daily-merge-20260428.md`

```markdown
# Daily merge — 2026-04-28

**Run start:** 03:00:00 UTC
**Run end:**   03:14:23 UTC
**Status:**    ✅ green

## Commits processed

| Category | Picked | Skipped | Total |
|---|---:|---:|---:|
| A — feat | 12 | 0 | 12 |
| B — fix | 4 | 1 (conflict) | 5 |
| D — worker-internal | 0 | 7 (file-copy) | 7 |
| E — noise | 0 | 23 (skip) | 23 |
| **Total** | **16** | **31** | **47** |

## Files synced (smedjan/)
- smedjan/sources.py (modified)
- smedjan/factory_core.py (new)
- (...)

## Smoke test
13/13 endpoints 200 within 5s

## Canary 30 min
0 5xx-bursts; max-1min-rate = 2

## Skipped commits
- `3e1b7cf` — modify/delete on smedjan/scripts/secret_scan.py (needs manual)

## Drift anomalies
- `6ce9974` (sync_agent_slugs fix) — appeared to run in prod 24/4 but
  not in main:s git-history; needs reconciliation.

## Rollback tag
daily-merge-rollback-20260428 → 9f669cc (pre-run)
```

## Första körning — manuell

Efter att hela infrastrukturen är klar:

1. `smedjan merge dry-run` — Anders granskar output
2. Anders säger go eller stop
3. Om go: `smedjan merge run` med `--manual` flagga (skiljer från cron-trigger)
4. Observera 30 min canary
5. Aktivera LaunchAgent: `launchctl load -w ~/Library/LaunchAgents/com.nerq.smedjan.daily-merge.plist`

## Implementation order

1. `classifier.py` (återanvänd `/tmp/factory-analys/classify.py` logic)
2. `drift_detector.py` (för 6ce9974-anomalin och liknande)
3. `cherry_pick.py` (cherry-pick + auto-skip på conflict)
4. `file_copy.py` (smedjan/ tree sync per touched-files)
5. `smoke_test.py` (existing pattern)
6. `canary.py` (5xx-rate watch, auto-rollback hook)
7. `rollback.py` (tag-based)
8. `report.py` (daily markdown)
9. `cli.py` (subcommands)
10. LaunchAgent plist
11. Tester + dry-run + Anders go-ahead

Beräknad tid per modul: 15-30 min. Total: 3-4h.
