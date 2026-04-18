# L1 Kings Unlock — Emergency Rollback Runbook

**Purpose:** Restore the `/safe/*` render path to pre-unlock behaviour (Kings only) in under two minutes when an L1 canary shows trouble. Memorise the three commands at the top; everything below them is context.

---

## The three commands (copy-paste)

```bash
# 1 — remove the canary allowlist env var
/usr/libexec/PlistBuddy -c "Delete :EnvironmentVariables:L1_UNLOCK_REGISTRIES" \
  ~/Library/LaunchAgents/com.nerq.api.plist

# 2 — bounce the API (workers reload immediately)
launchctl kickstart -k gui/$(id -u)/com.nerq.api

# 3 — verify locked state
sleep 6
curl -sS http://localhost:8000/safe/espeak | grep -c "Detailed Score Analysis"
# expected output: 0  (Kings would be 1 — espeak is a homebrew non-King)
```

**If step 1 fails with `Does Not Exist`** (the key isn't in the plist), the rollback is effectively already in place — skip to step 2 + 3.

---

## What the rollback does

- Removes the `L1_UNLOCK_REGISTRIES` environment variable from the API's launchd plist.
- Restarts `com.nerq.api`; every uvicorn worker re-imports `agent_safety_pages.py`.
- The module-level `_L1_UNLOCK_ALLOWLIST` becomes an empty frozenset.
- The rendering gate evaluates `_unlock_eligible = False` for every non-King, so non-Kings render pre-unlock output while Kings continue to render their existing sections.
- Result is indistinguishable from the pre-commit-c34b10c production behaviour.

**The rollback does not revert the Python source.** The code stays on disk; the env var is what toggles the feature. A follow-up `git revert` is unnecessary unless a bug is found in the *Kings* render path (it was unchanged by the L1 commits, so this has not happened to date).

---

## When to rollback

Any one of these triggers a rollback — do not wait for a second signal:

| Signal | Source | Threshold |
|---|---|---|
| 5xx rate on gems+homebrew `/safe/*` | analytics.db `requests` table | > 2× baseline over 30 min |
| 5xx rate whole Nerq | analytics.db | > 20% above baseline over 30 min |
| Render-path `Traceback` | `~/agentindex/logs/api_error.log` | any |
| Citation rate on canary cohort | analytics.db (human visits, AI-domain referrer) | drop > 20% vs prior-7-day baseline over 24h |
| Top-10 gems/homebrew GSC query ranking | GSC export | drop > 30% in 48h |
| `system_healthcheck.py` memory alarm | `~/agentindex/logs/healthcheck.db` | RAM > 98% for > 5 min |

Baseline numbers are in `~/smedjan/baselines/L1-canary-gems-homebrew-PRE-2026-04-18.md`.

---

## Rollback drill (evidence the mechanism works)

Run at: 2026-04-18 ~13:14 local.

### 1 — Current state before the drill

```
$ git -C ~/agentindex rev-parse HEAD
37414e8ef4d551bce56d095c13b2185b74b4aff1     # (pre fail-closed fix)
$ /usr/libexec/PlistBuddy -c "Print :EnvironmentVariables" ~/Library/LaunchAgents/com.nerq.api.plist
Dict {
    NERQ_PG_REPLICA = localhost
    NERQ_PG_PRIMARY = 100.119.193.70
}
```

No L1_UNLOCK_REGISTRIES key. Good.

### 2 — Subprocess validation (no production impact)

Each column renders `espeak` (homebrew non-King) + `express` (npm King) in a fresh Python subprocess with a controlled env:

| L1_UNLOCK_REGISTRIES | espeak `has_king` | express `has_king` |
|---|:---:|:---:|
| *(unset)* | **False** ✓ locked | True ✓ King |
| `gems,homebrew` | True ✓ unlocked | True ✓ King |
| `*` | True ✓ unlocked | True ✓ King |
| `npm` | **False** ✓ locked | True ✓ King |

The rollback mechanism (env-var toggle) works: removing the var reverts the non-King code path, the King code path is unaffected.

### 3 — Incident note (why this runbook matters in practice)

At 13:10 local the `com.nerq.master-watchdog` LaunchAgent restarted `com.nerq.api`. The workers reloaded `agent_safety_pages.py` from disk, which at that moment held commit `37414e8` — a version whose default (empty allowlist) unlocked **all** non-skip registries.

The effect was a ~4-minute unintended full rollout in production. No 5xx, no rendering crashes (verified via 0 status≥500 rows in `requests` the last 1h). We caught it when the post-baseline dry-run showed `old_had_king_section = 97/100`.

**Fix (commit `7b8363e`) inverts the default:** empty allowlist = no unlock. A plain kickstart is now a no-op. A canary must explicitly set `L1_UNLOCK_REGISTRIES=gems,homebrew`.

Remediation kickstart at ~13:14: `curl http://localhost:8000/safe/espeak | grep -c "Detailed Score Analysis"` → `0`. Kings still render: `curl http://localhost:8000/safe/express | grep -c "Detailed Score Analysis"` → `1`. Pre-unlock state restored.

---

## Forward recovery after a rollback

Once the trigger is resolved:

```bash
# re-add the canary allowlist (adjust the value for the target wave)
/usr/libexec/PlistBuddy -c \
  "Add :EnvironmentVariables:L1_UNLOCK_REGISTRIES string 'gems,homebrew'" \
  ~/Library/LaunchAgents/com.nerq.api.plist

# if the key still exists and only needs a new value, use Set:
#   /usr/libexec/PlistBuddy -c \
#     "Set :EnvironmentVariables:L1_UNLOCK_REGISTRIES 'gems,homebrew'" \
#     ~/Library/LaunchAgents/com.nerq.api.plist

launchctl kickstart -k gui/$(id -u)/com.nerq.api

sleep 6
# confirm the canary is active (expect 1 for gems/homebrew slugs)
for s in espeak pocketbase a2ps geos cflow; do
  printf "%-20s " "$s"
  curl -sS http://localhost:8000/safe/$s | grep -c "Detailed Score Analysis"
done
```

---

## Nuclear option (full code revert)

Only if a rollback above does not restore pre-change behaviour — i.e. if the **King render path** itself has regressed:

```bash
cd ~/agentindex
git revert --no-edit 7b8363e 37414e8 c34b10c
git push origin main
launchctl kickstart -k gui/$(id -u)/com.nerq.api
```

This reverts three commits to the pre-Smedjan state. After the kickstart, `_render_agent_page` is literally byte-identical to the pre-2026-04-18 production version. Expect ~60 s downtime while workers cold-start.

---

## Contact

- Primary: Anders (k.b.a.nilsson@gmail.com). ntfy topic `nerq-alerts` reaches him.
- Secondary: whoever is driving the Smedjan session that set the canary live.

## Log the rollback

After any rollback, append to `~/smedjan/journal/day-0X-*.md` with: time, trigger, observation window that drove the decision, and whether forward recovery was attempted.
