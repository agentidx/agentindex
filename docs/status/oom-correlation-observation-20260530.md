# OOM correlation observation — 2026-05-30

> Observation-only memo. Not a decision. Anders may use this to lower the
> Patroni-recovery priority in ADR-003a, but the ADR itself is not
> amended here.

## Question

Is the 2026-05-26 23:17 Patroni OOM-kill on Nbg (ADR-003a issue 1) the
*cause* of the saturation pattern, or a *consequence* of an underlying
slow-query problem that R-SW (commit `04ee95e`) just fixed?

## Data points

### A. Nbg PG statement_timeout cancellations by day

```
2026-04-14: 1
2026-05-27: 361
2026-05-28: 790
2026-05-29: 594
2026-05-30: 1228  (incident day — peak)
```

Source: `/var/log/postgresql/postgresql-16-main.log*` on `nerq-nbg-root`,
filtered for "canceling statement due to statement timeout". The earliest
recurrent event recorded was 2026-05-27 00:32:08 — a
`SELECT slug, name, registry, trust_score FROM software_registry` (the
exact pattern fixed by STEP 2).

### B. Timeline alignment

| Time | Event |
|---|---|
| 2026-04-12 09:32 | PG stopped on Hel (ADR-003a) |
| 2026-04-14 (~1 cancel) | First statement_timeout in current log window |
| 2026-04-15 13:23 | PgBouncer "server conn crashed?" first appears |
| 2026-05-03 | Nbg first OOM event (per CLAUDE.md memory) |
| 2026-05-05 09:06 | PgBouncer agentindex_write → Hel (silent failure starts) |
| 2026-05-23 06:16 | Patroni on Hel exits (etcd-quorum loss) |
| **2026-05-26 23:17** | **Patroni on Nbg OOM-killed** |
| **2026-05-27 00:32** | **First statement_timeout cancel after the OOM (9h later)** |
| 2026-05-27 18:17 | PG shut down on Nbg (controlled) |
| 2026-05-30 08:43 | com.nerq.api crash-loop start |
| 2026-05-30 11:42 | R-SW PREP-1 deployed (DDL out of boot path) |
| 2026-05-30 17:52 | R-SW STEP 2 deployed (text_pattern_ops index) |

### C. Memory footprint of slow `lower(name) LIKE` scans

For software_registry (2.9 M rows, 1.6 GB on disk):

- Per-query scan: PG holds the registry-prefix btree pages + filter-loop
  buffer. With `lower(name) LIKE '%pat%'` (substring), every row's
  `lower(name)` computation is in working memory until the filter
  decides.
- Concurrent calls: 5 (observed in the morning capture) → cumulative
  working set in the hundreds of MB.
- Plus PgBouncer connection state, autovacuum, WAL replay, normal
  query traffic.

Nbg has 16 GB RAM. Per ADR-003a issue 2 the host was at 13/15 GB +
7.5 GB swap. Tight margin. Five concurrent expensive queries are
plausible OOM triggers.

## Plausible causal hypothesis

```
Slow software_registry LIKE queries (chronic, growing with traffic)
        │
        ▼
PG working-set memory grows under concurrent calls
        │
        ▼
Nbg hits OOM-killer territory → 2026-05-26 23:17 Patroni gets sacrificed
        │
        ▼
Without Patroni, PG keeps running. Slow queries keep multiplying.
        │
        ▼
2026-05-30 morning: enough concurrent slow queries to push past
                    statement_timeout, every query cancelled, PgBouncer
                    sees "server conn crashed?", API workers fail boot,
                    restart-loop amplifies the load further.
```

If this hypothesis holds, **fixing the slow query (STEP 2) removes the
upstream pressure**, which removes the OOM source, which removes the
need to bring Patroni back urgently.

## What this is NOT evidence of

- It is not proof. We don't have Nbg memory traces from 2026-05-26.
- It does not exonerate the 2-node etcd / HA topology (ADR-003a issue 3
  remains real — single-node failure intolerance).
- Mac Studio's stale replica (ADR-003a issue 5) and the Cloudflare LB
  gap (issue 4) are unaffected by this.

## Watch-criteria over the next 7 days

If the hypothesis is right:

1. `statement_timeout` cancel count per day drops below the
   2026-04-14 baseline (~1).
2. PgBouncer `server conn crashed?` events <5/day sustained.
3. `com.nerq.api runs` increments by <5/day.
4. The new infra healthcheck (commit `ef7efe1`) registers zero
   `SLOW_QUERY` or `SLOW_TRENDING` alerts.

If those four hold for 7 days, ADR-003a issue 1 (Patroni dead)
demotes from "P0 must-fix" to "P3 — fix when convenient." The HA
benefit of running Patroni doesn't go away, but the urgency does.

If any of them re-trip, there's a second cause we haven't found.

## What to NOT do based on this memo

- Do not amend ADR-003a yet. Wait for the 7-day data.
- Do not skip the eventual Patroni recovery — single-node PG is still
  single-failure-intolerant. Just lower its priority.
- Do not assume any other ADR-003a issue is implicitly resolved.
