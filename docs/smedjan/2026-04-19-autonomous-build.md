# Smedjan autonomous build — 2026-04-19

## Progress report #1 — end of Phase A/B/C seed (09:19 UTC)

### Phase A: parallelism infrastructure — DONE
Commit `dccbf53` on `smedjan-factory-v0`.

- `smedjan.tasks.session_affinity` (text) column + index. Values `a`/`b`/`c`/`d` route tasks to specific workers; NULL = any-worker pool.
- `factory_core.claim_next_task(affinity=…)` — prefers own-affinity over NULL via SQL CASE. Same FOR UPDATE SKIP LOCKED semantics.
- `factory_core.reclaim_stuck_tasks()` returns orphaned `in_progress` rows (claim > 30 min AND heartbeat > 5 min) to queued with audit note appended. Wrapped in `scripts/smedjan-reclaim.py` + `com.nerq.smedjan.reclaim.plist` (StartInterval=600 s).
- `scripts/git-locked.sh` — fcntl exclusive lock on `~/.smedjan/git.lock` (macOS has no flock(1); embedded Python does the syscall). Workers use this for every git add/commit/push.
- 4 LaunchAgent plists (com.nerq.smedjan.worker-{a,b,c,d}.plist) each with `SMEDJAN_WORKER_AFFINITY` env. Old single-worker plist unloaded `-w`.

A3 (richer dedup) is partial — fallback_generator has ON CONFLICT (id) DO NOTHING as the critical-path guard. A deeper "same-description within 7d" dedup ships in a later iteration.

### Phase B: 45 primary tasks seeded — DONE
- L1 Kings Unlock: **3 tasks** (T100 Wave 2, T101 Wave 3, T102 observation-expander)
- L2 Unrendered Data Surfacer: **10 tasks** (Block 2a…2e × renderer+rollout)
- L3 AI Demand Signal: **2 tasks** (T130 Planner priority bias, T131 velocity surge detector)
- L4 Data Moat Endpoints: **7 tasks** (T140–T144 five JSON endpoints, T145 llms.txt vertical extension, T146 MCP expansion)
- L5 Distribution: **5 tasks** (T150 GSC sitemap, T151 Bing WMT, T152 IndexNow batch, T153 cross-registry linking, T154 Wikidata skeleton)
- L6 Quality Gate: **5 tasks** (T160 F1-v2, T161 F2-v2, T162 sacred-byte verifier, T163 template consistency, T164 threshold retune)
- L7 Measurement: **4 tasks** (T170 GSC pull, T171 Bing pull, T172 citation sampler, T173 KPI dashboard)
- L8 Infrastructure: **9 tasks** (T180–T188)

### Phase C: 10 diagnostic A-tasks seeded — DONE
A1–A10 all `session_affinity='d'`, risk=low, auto-yes. Specs were inferred from Anders' names (the reference chat-thread wasn't in my context); each task description is self-contained.

### Phase D: 4 workers + reclaim active
```
worker-a (PID 65382) — affinity=a (L1/L2 deploys+renderers)
worker-b (PID 65878) — affinity=b (L4 endpoints)
worker-c (PID 66394) — affinity=c (L5/L6/L7 distribution+quality+measurement)
worker-d (PID 66907) — affinity=d (diagnostics + fabrik-code)
reclaim  (StartInterval 600s)
```

All four are currently mid-task with concurrent claims on different FB-F2/FB-F3 rows — so parallelism is observably live. No git-push collisions seen during the transition window; the git-lock was exercised by my own commits while workers were cycling.

### Queue state

| Status | NULL-affinity | a | b | c | d | Total |
|---|---:|---:|---:|---:|---:|---:|
| in_progress | 5 | 0 | 0 | 0 | 0 | 5 |
| queued | 7 | 1 | 0 | 0 | 26 | 34 |
| needs_approval | 8 | 6 | 5 | 7 | 0 | 26 |
| pending | 4 | 6 | 2 | 2 | 0 | 14 |

26 tasks need Anders approval before workers can pick them (risk=medium — L1 deploys, L2 renderers, L4 endpoints, MCP expansion, cross-registry rendering). 14 pending are dep-blocked (mostly waiting for T003 or T100).

### Blockers
- None worker-internal. Workers are live + cycling.
- **Anders-approval blockers**: 26 tasks in needs_approval. When approved they go into queued and a worker claims on the next tick.
- **Known caveat**: 2-3 L5/L7 tasks (GSC/Bing/citation sampling) will STATUS:blocked when they reach the worker if credentials aren't at the expected paths. That's designed behaviour — worker moves on.

### Time-to-full-factory estimate
- Auto-yes tasks (34 queued): at 4 workers × ~3 min/task avg, clearing the queue takes **~25 min** (ignoring fallback churn in parallel).
- needs_approval tasks: blocked on Anders' review cadence. ~30 min to approve all + dependencies to unfurl.
- **If Anders approves all 26 tonight: full factory operational ~2 h**. If not, we run with 34 + follow-ups through the night on diagnostics + L8 infra, then resume L1/L2/L4 pathways on approval.

### Paid-API defense
- Worker plists explicitly set `ANTHROPIC_API_KEY=""`.
- `invoke_claude()` strips the env var from the subprocess as well.
- Max-subscription `claude.ai` OAuth is the only auth path. No paid-API calls observed in worker logs.

### Next report
After 6h (≈15:20 UTC), or immediately on any of:
- ≥ 1 canary 5xx alert
- ≥ 1 reclaim firing (suggests a stuck task)
- Anders-initiated resume signal
