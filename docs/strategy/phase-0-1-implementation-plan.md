# Nerq v2 Implementation Plan — Phase 0 + Phase 1

**Period:** Weeks 1–6 (2026-04-07 through 2026-05-19)
**Scope:** v1 shielding (Phase 0) + v2 skeleton and first cutover (Phase 1)
**Companion to:** ADR-001 Nerq v2 Architecture

---

## Overview

Phase 0 and Phase 1 together establish the foundation for the entire v2 migration. Phase 0 protects v1 from regressions and installs the first disaster recovery capability. Phase 1 builds the v2 skeleton and proves the Strangler Fig pattern works by migrating one page type (`/safe/{entity}`) to the new architecture.

At the end of week 6, the following will be true:

- v1 continues to serve all traffic as today
- A linter prevents new hardcoded internal links from being added anywhere in v1
- Golden file tests catch any byte-drift in the `pplx-verdict`, `ai-summary`, and `SpeakableSpecification` blocks
- A Cloudflare R2 fallback origin means v1 can survive a Mac Studio outage without user-visible downtime
- PostgreSQL is backed up continuously to Backblaze B2 with point-in-time recovery
- The package-page bug (`language column does not exist`) is fixed permanently
- The norska versal-strängar are fixed
- Two Hetzner CPX32 nodes are running in Nürnberg and Helsinki
- PostgreSQL synchronous streaming replication is live from Mac Studio to Nürnberg
- The `nerq-v2` repository contains a working FastAPI application with domain models, migrations, templates, and tests
- The `/safe/{entity}` page type renders in v2 with byte-identical output to v1
- Observability (Prometheus, Grafana, Loki, Alertmanager) is operational on Nürnberg
- One page type has been cut over to v2 and is serving production traffic

Each week ends with an explicit checklist. Do not proceed to the next week until all items are checked.

---

## Working methodology

### How Anders and Claude collaborate during this phase

This plan assumes the following workflow, which is the most reliable given past experience with Claude Code:

1. **Claude (in this chat) designs and writes critical-path code.** This includes: the sacred element module (`nerq.heligt`), the URL helper (`nerq.i18n.urls`), the golden file test framework, the linter, the PostgreSQL replication setup, and the Cloudflare configuration. These pieces are too important to delegate to Claude Code in session, which has been unreliable.

2. **Claude writes Claude Code prompts for mechanical work.** This includes: migrating existing files to use the new URL helper, running audits, generating translations, setting up Docker images. Each prompt has clear acceptance criteria and can be verified after execution.

3. **Anders runs commands on Mac Studio and reports results.** Commands are always wrapped in `bash << 'EOF' ... EOF` heredoc format per the existing memory. Anders pastes outputs back to Claude in chat for verification.

4. **Verification is always external to Claude Code.** After any Claude Code session, Anders runs a verification script that Claude provides. If the verification fails, Claude writes a new prompt for Claude Code to fix the specific failure.

5. **Every week ends with a review meeting.** Anders and Claude review the week's checklist, document what worked and what didn't, and adjust the next week's plan if needed. This is the halfautomatic equivalent of a standup.

### Rules that apply throughout the phase

- **Never touch the `pplx-verdict`, `ai-summary`, or `SpeakableSpecification` elements on v1** without an explicit golden file test verifying the change is intentional. These are protected.
- **Every change to v1 is guarded by the linter.** If the linter blocks a change, the linter wins. The linter is not bypassed.
- **All new code has tests.** No exceptions. Tests run in CI and locally via pre-commit.
- **Commit often, push every time.** GitHub Actions CI runs on every push. Failed CI blocks the next step.
- **If in doubt, ask in chat before executing.** The cost of a 5-minute clarification is always lower than the cost of an incorrect execution.

---

## Phase 0 — Weeks 1–2: Foundation and v1 shielding

### Week 1 — Days 1–5

#### Day 1 (Wednesday April 8) — Sign up and baseline

**Morning (30 minutes):**

Sign up for the new accounts required by the architecture. Use a single email alias for all to keep them organized.

1. Create account at cloudflare.com if not already done. Enable R2 storage. Note the account ID and API token.
2. Create account at hetzner.com/cloud. Add a payment method. Note the project ID.
3. Create account at backblaze.com/b2. Generate an application key. Note the key ID and secret.
4. Create a new GitHub repository named `nerq-v2` (private). Note the clone URL.
5. Install Infisical CLI on Mac Studio for later use.

Paste the four account IDs to Claude (not the secrets, just identifiers) so Claude can verify you're working in the right projects in later commands.

**Afternoon (3 hours):**

Capture a baseline measurement of v1. This is essential for verifying later that nothing has degraded.

Claude provides a baseline script. Anders runs it on Mac Studio. Output is pasted back to chat.

```bash
bash << 'EOF'
mkdir -p /Users/anstudio/nerq-baselines/2026-04-08
cd /Users/anstudio/nerq-baselines/2026-04-08

echo "### BASELINE: v1 status on Dag 32 ###"
date

# 1. AI citation rate (last 24h)
echo ""
echo "### AI citations last 24h ###"
sqlite3 ~/agentindex/logs/analytics.db "
SELECT
  user_agent_category,
  COUNT(*) as requests
FROM requests
WHERE ts > datetime('now', '-24 hours')
  AND is_bot = 1
GROUP BY user_agent_category
ORDER BY requests DESC;
" 2>/dev/null || echo "analytics.db path unknown - skip"

# 2. Human visits last 24h
echo ""
echo "### Human visits last 24h ###"
sqlite3 ~/agentindex/logs/analytics.db "
SELECT COUNT(*)
FROM requests
WHERE ts > datetime('now', '-24 hours') AND is_bot = 0 AND status = 200;
" 2>/dev/null || echo "skip"

# 3. Snapshot of pplx-verdict HTML on 5 representative pages
echo ""
echo "### Sacred element snapshots ###"
for url in \
  "https://nerq.ai/safe/nordvpn" \
  "https://nerq.ai/safe/bitwarden" \
  "https://nerq.ai/de/safe/nordvpn" \
  "https://nerq.ai/ja/safe/nordvpn" \
  "https://nerq.ai/no/safe/nordvpn"; do
  slug=$(echo "$url" | sed 's|https://nerq.ai/||;s|/|_|g')
  curl -s "$url" > "page_${slug}.html"
  echo "  Saved: page_${slug}.html ($(wc -c < page_${slug}.html) bytes)"
done

# 4. Sacred element extraction
echo ""
echo "### Sacred element byte counts ###"
for f in page_*.html; do
  verdict_bytes=$(grep -oE '<div class="pplx-verdict"[^>]*>[^<]*' "$f" 2>/dev/null | wc -c)
  summary_bytes=$(grep -oE '<div class="ai-summary"[^>]*>[^<]*' "$f" 2>/dev/null | wc -c)
  speakable_bytes=$(grep -oE 'SpeakableSpecification' "$f" 2>/dev/null | wc -c)
  echo "  $f: verdict=$verdict_bytes summary=$summary_bytes speakable=$speakable_bytes"
done

# 5. Database size and table counts
echo ""
echo "### Database state ###"
/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql -U anstudio -d agentindex -c "
SELECT
  pg_size_pretty(pg_database_size('agentindex')) as db_size,
  (SELECT COUNT(*) FROM agents WHERE is_active = true) as active_agents,
  (SELECT COUNT(*) FROM entity_lookup WHERE is_active = true) as active_entities;
"

# 6. Filesystem state of agentindex
echo ""
echo "### Codebase state ###"
find /Users/anstudio/agentindex/agentindex -name "*.py" -type f | wc -l
find /Users/anstudio/agentindex/agentindex -name "*.py" -type f -exec wc -l {} + | tail -1

echo ""
echo "BASELINE COMPLETE. Files saved to /Users/anstudio/nerq-baselines/2026-04-08"
EOF
```

**Deliverable:** Baseline directory with HTML snapshots and metrics. This becomes the reference point for all subsequent changes.

#### Day 2 (Thursday April 9) — Install the linter and fix the package bug

**Morning (2 hours):** The i18n module, linter, and pre-commit hook.

Claude writes the code for `nerq.i18n.languages`, `nerq.i18n.urls`, and the linter test. These are the first files of the new architecture, but they live inside the existing v1 codebase temporarily so that the linter can protect v1 immediately.

Claude provides the complete file contents for these files in the chat. Anders creates them on Mac Studio:

1. `agentindex/agentindex/i18n/__init__.py`
2. `agentindex/agentindex/i18n/languages.py` — single source of truth for the 23 current languages plus placeholders for the 27 upcoming languages, with metadata (native name, RTL flag, reference language for translation work)
3. `agentindex/agentindex/i18n/urls.py` — `localize_url()` function with whitelist logic for paths that should be localized
4. `agentindex/tests/test_urls.py` — roughly 40 unit tests covering all edge cases
5. `agentindex/tests/test_no_hardcoded_links.py` — the linter that scans the codebase for hardcoded internal links
6. `.pre-commit-config.yaml` — runs the linter and the tests before every commit

The linter has an initial allowlist of files that are known to contain violations, so that it does not fail immediately. Each file can only stay on the allowlist until week 5. The allowlist shrinks by at least one file per week.

**Afternoon (1 hour):** Fix the package-page bug.

Claude writes a corrected version of the query in `seo_answers_packages.py` line 227 that joins `entity_lookup` to `agents` to get the `language` column. A test is added that verifies the query returns valid results for a sample package. The fix is deployed to v1 immediately.

**Evening verification:**

```bash
bash << 'EOF'
# Verify linter works
cd /Users/anstudio/agentindex
python -m pytest tests/test_no_hardcoded_links.py -v
echo "Linter test exit code: $?"

# Verify package page no longer 500s
curl -s -o /dev/null -w "%{http_code}\n" "https://nerq.ai/package/express"
curl -s -o /dev/null -w "%{http_code}\n" "https://nerq.ai/package/django"

# Verify i18n module imports cleanly
python -c "from agentindex.i18n import languages, urls; print('OK:', len(languages.LANGUAGES), 'languages')"
EOF
```

**End of Day 2 checklist:**

- [ ] Four account IDs shared in chat
- [ ] Baseline captured and committed to `nerq-baselines/`
- [ ] `i18n/languages.py` created with 23 languages and metadata
- [ ] `i18n/urls.py` created with `localize_url()` function and whitelist
- [ ] 40 unit tests pass
- [ ] Linter test passes (with allowlist)
- [ ] Pre-commit hook installed and runs on `git commit`
- [ ] Package-page bug fixed and deployed; package pages return 200
- [ ] No regression in AI citations or human traffic (check after 2 hours)

#### Day 3 (Friday April 10) — Golden file tests for sacred elements

**All day (4–6 hours):** The most important day of Phase 0.

Claude writes the golden file test framework. This framework:

1. Fetches representative pages from v1 (10 pages across languages and verticals)
2. Extracts the `pplx-verdict` block, `ai-summary` block, and `SpeakableSpecification` JSON-LD
3. Saves these as committed fixtures in the repository
4. Provides a `pytest` test that re-extracts these elements on every CI run and compares byte-for-byte against the fixtures
5. Fails CI if any byte has changed

The framework also produces a Prometheus-compatible metric file reporting the number of mismatched bytes, so that after observability is installed in week 2, drift can be tracked over time.

Claude provides:

- `agentindex/tests/sacred/__init__.py`
- `agentindex/tests/sacred/fixtures/` — directory with 30 fixture files (10 pages × 3 element types)
- `agentindex/tests/sacred/test_sacred_bytes.py` — the test itself
- `agentindex/scripts/capture_sacred_fixtures.py` — script to (re)capture fixtures when an intentional change is approved
- `agentindex/docs/sacred_change_procedure.md` — the process for approving intentional changes

The last file is important: any change to a sacred element must go through an explicit review step, not just a code commit. The procedure is:

1. Anders explicitly approves the change in chat
2. Claude writes a PR with the new fixture
3. PR must reference this ADR and explain why the change is safe
4. Claude re-runs the fixture capture
5. CI passes with the new fixture
6. Merge

**Initial run:** Claude runs the fixture capture script to create the initial fixtures. Anders reviews a few of them manually to sanity-check that the extraction is correct.

**End of Day 3 checklist:**

- [ ] Golden file test framework created
- [ ] 30 initial fixtures captured from live v1
- [ ] Sacred test passes on current v1
- [ ] Sacred change procedure document written
- [ ] Change procedure committed to repository

#### Day 4 (Saturday April 11) — Backblaze B2 PostgreSQL backup

**Morning (2 hours):** Install `pgBackRest` on Mac Studio and configure it to push backups to Backblaze B2.

Claude provides:

- Installation commands for `pgBackRest` via Homebrew
- A `pgbackrest.conf` template with placeholders for B2 credentials (pulled from Infisical, not committed)
- Systemd/launchd configuration for continuous WAL archiving
- A full backup command for the initial snapshot
- A restore test script that verifies backups are restorable

**Afternoon (2 hours):** Run the initial full backup and verify it.

The initial backup of the 80GB PostgreSQL database will take several hours depending on bandwidth. During this time, Anders can proceed with other checklist items (see Day 5 items).

After the backup completes, Claude provides a restore verification script that:

1. Downloads the backup from B2 to a temporary directory on Mac Studio
2. Restores it into a separate PostgreSQL instance on a non-standard port
3. Runs a few sanity queries to verify table counts and a sample entity
4. Reports success or failure
5. Cleans up the temporary instance

This verification is the only way to know that the backup actually works. It is not optional.

**End of Day 4 checklist:**

- [ ] `pgBackRest` installed and configured
- [ ] Backblaze B2 bucket created for PostgreSQL backups
- [ ] Initial full backup completed and uploaded to B2
- [ ] WAL archiving running continuously to B2
- [ ] Restore verification passed on a separate PostgreSQL instance
- [ ] Backup schedule active (full backup weekly, differential daily, WAL continuous)

#### Day 5 (Sunday April 12) — Cloudflare R2 fallback origin

**All day (4–6 hours):** Install the first disaster recovery capability for v1.

This day sets up a Cloudflare Worker that serves cached HTML from R2 when the Mac Studio origin is unavailable. This is independently valuable even if v2 is never built: it means the outages described in handover Dag 31 no longer cause user-visible downtime.

The approach:

1. Create an R2 bucket named `nerq-cache-fallback`
2. Write a Cloudflare Worker that:
   - Normally proxies requests to Mac Studio as today
   - On every successful response, asynchronously writes the response to R2 (best effort, no blocking)
   - On Mac Studio 5xx responses or timeout, serves the most recent version from R2 with a `X-Served-From: r2-fallback` header
3. Deploy the Worker with `wrangler`
4. Test by simulating Mac Studio being down (temporarily block its port)

Claude provides the Worker code. Anders deploys it.

**Critical test:** Temporarily stop the uvicorn process on Mac Studio (or block its port with `pfctl`) and verify from a different network that:

- `nerq.ai/safe/nordvpn` still returns 200 (served from R2)
- `X-Served-From: r2-fallback` header is present
- Content matches what was cached from the last successful response
- AI citations continue to increment (check the analytics counter 30 minutes later)

Restart Mac Studio's uvicorn process when the test is complete.

**End of Day 5 checklist:**

- [ ] R2 bucket `nerq-cache-fallback` created
- [ ] Cloudflare Worker deployed
- [ ] Worker proxies all normal traffic correctly
- [ ] Worker writes responses to R2 asynchronously
- [ ] Simulated Mac Studio outage: sajten continues to serve from R2
- [ ] AI citations continue to increment during simulated outage
- [ ] Mac Studio restored after test

### Week 1 summary

At the end of week 1, v1 is meaningfully more robust than it was on Dag 32. The linter prevents regressions. Golden file tests protect the sacred elements. PostgreSQL has offsite backups with point-in-time recovery. Mac Studio is no longer a single point of failure for user-facing HTTP traffic.

None of v2 itself has been built yet. That starts in week 2.

### Week 2 — Days 6–10

#### Day 6 (Monday April 13) — Set up Hetzner CPX32 Nürnberg

**Morning (1 hour):** Provision the first Hetzner node.

Anders goes to the Hetzner console and orders one CPX32 in Nürnberg (nbg1 location). Operating system: Ubuntu 24.04 LTS. SSH key uploaded. Server name: `nerq-nbg-1`.

Once provisioned, Anders notes the IP address and pastes it to Claude.

**Rest of day (4 hours):** Initial server hardening and base software.

Claude provides a setup script that Anders runs via SSH:

1. System updates and reboots
2. Create non-root user `nerq` with sudo
3. Disable root SSH login
4. Configure firewall (ufw): allow 22 (SSH), 80, 443, 5432 only from Mac Studio's Tailscale IP
5. Install Tailscale and join the existing tailnet
6. Install Docker and Docker Compose
7. Install PostgreSQL 16 client tools (not server yet)
8. Install `pgbackrest` client
9. Install Prometheus, Grafana, Loki, Alertmanager as Docker Compose services
10. Install Infisical server as Docker container
11. Set up daily security updates via unattended-upgrades
12. Configure timezone to Europe/Stockholm (matching Mac Studio)

**End of Day 6 checklist:**

- [ ] Hetzner CPX32 Nürnberg provisioned
- [ ] Tailscale connected to tailnet
- [ ] Docker and Docker Compose installed
- [ ] Firewall configured with restrictive rules
- [ ] Prometheus, Grafana, Loki, Alertmanager running as Docker Compose
- [ ] Infisical server running and accessible via Tailscale
- [ ] Can SSH in as `nerq` user only (root disabled)

#### Day 7 (Tuesday April 14) — Set up Hetzner CPX32 Helsinki

Same process as Day 6, but for Helsinki (hel1 location). Server name: `nerq-hel-1`. This node will be the PostgreSQL async replica plus geographic redundancy.

Helsinki does not need Prometheus, Grafana, Loki, or Infisical (those live on Nürnberg). It only needs the base system, Tailscale, Docker, and PostgreSQL client tools.

**End of Day 7 checklist:**

- [ ] Hetzner CPX32 Helsinki provisioned
- [ ] Tailscale connected
- [ ] Docker installed
- [ ] Firewall configured
- [ ] Can SSH in as `nerq` user

#### Day 8 (Wednesday April 15) — PostgreSQL synchronous replication Stockholm to Nürnberg

**All day (4–6 hours):** Configure PostgreSQL streaming replication.

Claude provides:

1. Changes to `postgresql.conf` on Mac Studio (primary) to enable WAL streaming
2. Changes to `pg_hba.conf` to allow replication from Nürnberg's Tailscale IP
3. PostgreSQL installation on Nürnberg as replica (via Docker or native, Claude recommends native at this point for performance)
4. `pg_basebackup` command to initialize Nürnberg from Mac Studio
5. Replication slot configuration
6. Verification queries to confirm replication is live and synchronous

**Critical test:** After replication is live, insert a test row on Mac Studio and verify it appears on Nürnberg within milliseconds. Delete the test row. Confirm deletion propagates.

**End of Day 8 checklist:**

- [ ] PostgreSQL installed on Nürnberg
- [ ] Streaming replication from Stockholm to Nürnberg configured
- [ ] Replication is synchronous (`synchronous_standby_names` set)
- [ ] Replication slot prevents WAL removal
- [ ] Test row round-trip verified
- [ ] Lag monitoring query ready (will integrate into Prometheus next week)

#### Day 9 (Thursday April 16) — PostgreSQL async replication Nürnberg to Helsinki

**All day (3–4 hours):** Set up the second replica in cascade.

Helsinki replicates from Nürnberg, not directly from Mac Studio. This is called cascading replication and reduces load on the primary.

Same process as Day 8 but with asynchronous mode (no `synchronous_standby_names` for Helsinki).

**Critical test:** Same as Day 8 but now verify the full chain: insert on Stockholm, appears on Nürnberg within milliseconds (sync), appears on Helsinki within seconds (async).

**End of Day 9 checklist:**

- [ ] PostgreSQL installed on Helsinki
- [ ] Cascading async replication Nürnberg to Helsinki configured
- [ ] Full chain test passed
- [ ] Both replicas can be manually promoted if primary fails

#### Day 10 (Friday April 17) — End of Phase 0 review

**Morning (2 hours):** Run a comprehensive verification of everything built in Phase 0.

Claude provides a verification script that checks:

- v1 AI citation rate vs baseline from Day 1 (should be within normal variance)
- v1 human traffic vs baseline
- Linter runs clean on current codebase
- Sacred file tests pass
- PostgreSQL backup is current (most recent full backup within 7 days, WAL current)
- R2 fallback origin responds correctly when Mac Studio is stopped (brief test)
- Nürnberg PostgreSQL replica lag is under 1 second
- Helsinki PostgreSQL replica lag is under 10 seconds
- Tailscale connectivity between all three nodes
- Observability stack accessible via Grafana dashboard

**Afternoon (2 hours):** Document Phase 0 learnings.

Claude writes a short Phase 0 retrospective document covering:

- What worked as planned
- What required adjustment
- What was harder than expected
- Any changes needed to ADR-001
- Adjustments to the Phase 1 plan based on learnings

**End of Week 2 checklist (Phase 0 complete):**

- [ ] All Day 1–9 items checked
- [ ] Comprehensive verification script passes
- [ ] Phase 0 retrospective written
- [ ] ADR-001 updated if any changes needed
- [ ] Phase 1 plan reviewed and adjusted
- [ ] Anders confirms readiness to proceed to Phase 1

---

## Phase 1 — Weeks 3–4: v2 skeleton

### Week 3 — Days 11–15

#### Day 11 (Monday April 20) — v2 repository skeleton

**Morning (2 hours):** Initialize the v2 repository with the base structure.

Claude provides the complete directory layout and configuration files:

```
nerq-v2/
├── app/
│   ├── __init__.py
│   ├── main.py                 FastAPI application entry
│   ├── config.py               Pydantic settings loaded from env/Infisical
│   ├── api/
│   │   ├── __init__.py
│   │   └── health.py           Only health endpoint for now
│   ├── core/
│   │   ├── __init__.py
│   │   ├── logging.py          structlog setup
│   │   └── dependencies.py     FastAPI dependencies
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py             SQLAlchemy base class
│   │   ├── session.py          Session factory
│   │   └── models/             (empty, populated day 12)
│   │       └── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   └── (empty, populated day 13)
│   ├── i18n/
│   │   ├── __init__.py
│   │   ├── languages.py        (copied from v1 Phase 0 work)
│   │   ├── urls.py             (copied from v1 Phase 0 work)
│   │   └── translations.py     (copied from v1 Phase 0 work)
│   ├── rendering/
│   │   ├── __init__.py
│   │   ├── templates/          Jinja2 templates, empty for now
│   │   └── projections/        (empty, populated day 14)
│   │       └── __init__.py
│   ├── heligt/                 Sacred elements, populated day 14
│   │   ├── __init__.py
│   │   └── fixtures/           (empty until day 14)
│   └── services/
│       ├── __init__.py
│       └── (empty)
├── alembic/
│   ├── versions/
│   ├── env.py
│   └── alembic.ini
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   └── (empty)
│   ├── integration/
│   │   └── (empty)
│   └── e2e/
│       └── (empty)
├── docs/
│   ├── adr/
│   │   └── ADR-001-nerq-v2-architecture.md    (this ADR)
│   ├── runbook.md
│   └── onboarding.md
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
├── .pre-commit-config.yaml
├── pyproject.toml              Ruff, mypy, pytest config
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

Claude provides the content for every file. Anders commits them in logical chunks (infrastructure first, app skeleton second, tests last). CI runs on every commit; CI must pass at every commit.

**Afternoon (2 hours):** Verify CI works.

- First commit: just the directory structure, pyproject.toml, and an empty `main.py`. CI should pass (nothing to test but lint passes).
- Second commit: add the health endpoint and a test. CI runs mypy, ruff, pytest. All pass.
- Third commit: add Dockerfile. CI builds the Docker image and verifies it starts.

**End of Day 11 checklist:**

- [ ] `nerq-v2` repository initialized on GitHub
- [ ] Complete directory structure committed
- [ ] CI pipeline passes on every commit
- [ ] Docker image builds successfully
- [ ] Health endpoint returns 200 when running locally

#### Day 12 (Tuesday April 21) — Domain models and database

**All day (6 hours):** Implement the core domain models and database schema.

Claude provides:

1. `app/db/models/entity.py` — SQLAlchemy model for `Entity` (the canonical entity table)
2. `app/db/models/trust_score.py` — SQLAlchemy model for trust scores with historical snapshots
3. `app/db/models/agent.py` — SQLAlchemy model for the existing `agents` table, mapped 1:1
4. `app/domain/entity.py` — Pydantic domain model (what the rendering pipeline consumes)
5. `app/domain/trust_score.py` — Pydantic model for trust scores
6. Alembic migration 001: create the new v2 tables (without touching v1 tables yet)
7. `tests/unit/test_entity_model.py` — unit tests for the domain models

The key insight: v2 runs against the same PostgreSQL database as v1. v2 reads from the existing `agents` and `entity_lookup` tables via its new SQLAlchemy models. New v2 tables (for temporal snapshots, version tracking, etc.) are additive — they do not touch existing v1 tables.

This is the Strangler Fig in action at the data layer: both systems coexist on the same database until v1 is decommissioned.

**End of Day 12 checklist:**

- [ ] Domain models for Entity and TrustScore created
- [ ] SQLAlchemy models mapping to existing `agents` and `entity_lookup` tables
- [ ] Alembic migration 001 created and applied to a local test database
- [ ] Unit tests pass
- [ ] v2 can read a sample entity from the production database (via Tailscale)

#### Day 13 (Wednesday April 22) — Repository layer and first query

**All day (6 hours):** Build the repository layer — all database queries flow through typed repository classes.

Claude provides:

1. `app/db/repositories/__init__.py`
2. `app/db/repositories/entity_repository.py` — methods like `get_by_slug()`, `list_by_category()`, `get_with_trust_components()`. All methods return typed domain objects, not tuples or dicts.
3. `tests/integration/test_entity_repository.py` — integration tests that run against a real PostgreSQL database (either a local test DB or a read-only replica)

The repository layer is the permanent fix for the class of bugs that caused the package-page 500 errors: every query has a typed return value, and a column rename on the database side fails at mypy checking time, not in production at runtime.

**Critical acceptance test:** The integration test for `EntityRepository.get_by_slug("nordvpn")` must return a complete `Entity` domain object with trust score, components, and language metadata, all pulled from the real database.

**End of Day 13 checklist:**

- [ ] Entity repository implemented with typed returns
- [ ] Integration tests pass against real database
- [ ] `get_by_slug("nordvpn")` returns a complete Entity with trust data
- [ ] mypy catches any type mismatches at build time

#### Day 14 (Thursday April 23) — Sacred element templates

**All day (6–8 hours):** This is the second most important day after Day 3.

Claude extracts the current `pplx-verdict`, `ai-summary`, and `SpeakableSpecification` templates from v1 and writes them as Jinja2 templates in `app/heligt/`. The templates must produce byte-identical output to v1 for the same input data.

The process:

1. Read the current verdict generation code in v1 (`agent_safety_pages.py`)
2. Write a Jinja2 template `app/heligt/templates/pplx_verdict.html` that produces the same output
3. Write a Python function `render_verdict(entity: Entity) -> str` that uses the template
4. Write a golden file test: for each of the 10 representative entities, assert that `render_verdict(entity)` returns exactly the fixture captured in Phase 0 Day 3
5. Repeat for `ai-summary` and `SpeakableSpecification`

The golden file test is the acceptance criterion. If it passes, the v2 heligt layer is byte-identical to v1. If it fails, we debug until it passes. There is no "close enough."

This is the single most important test in the entire project. If v2 ever ships something that changes these bytes, AI citations will degrade.

**End of Day 14 checklist:**

- [ ] Jinja2 templates for pplx-verdict, ai-summary, SpeakableSpecification
- [ ] Python render functions that accept typed Entity objects
- [ ] Golden file tests pass: all 30 fixture bytes match
- [ ] Prometheus metric for "sacred bytes drift" exposed (will report 0)

#### Day 15 (Friday April 24) — Full `/safe/{entity}` template

**All day (6 hours):** Build the complete Jinja2 template for `/safe/{entity}` pages.

This is the first full page in v2. It composes:

- The sacred elements from `heligt/`
- The page header and navigation (ported from v1)
- The entity details table
- The trust components breakdown
- The alternatives section
- The FAQ section
- The See Also section
- The footer

Claude provides the complete template. Anders tests it locally by rendering it for `nordvpn`, `bitwarden`, `express`, `tiktok`, and 10 other test entities, comparing against the live v1 pages.

The test is: `diff <(render_v2 nordvpn) <(curl v1 /safe/nordvpn)` should produce minimal differences — only things we explicitly want to change (e.g., using `localize_url` for internal links instead of hardcoded strings, which is a fix, not a regression).

**End of Day 15 checklist:**

- [ ] Complete `/safe/{entity}` Jinja2 template
- [ ] Rendering works for 10 test entities
- [ ] Diff vs v1 shows only intentional improvements (URL prefixing)
- [ ] Sacred elements byte-identical
- [ ] End-to-end test: request against v2 returns full HTML for `nordvpn`

### Week 4 — Days 16–20

#### Day 16 (Monday April 27) — Rendering pipeline

**All day (6 hours):** Build the pre-rendering pipeline.

Claude provides:

1. `app/services/render_pipeline.py` — a worker that reads entities from the database, renders them via the Jinja2 template, and uploads to R2
2. `app/services/r2_client.py` — thin wrapper over `boto3` for R2 uploads, handling content hashing and atomic writes (write to staging key, rename to live key)
3. `scripts/render_batch.py` — a script Anders can run to render a batch of entities on demand
4. Redis-backed job queue for incremental renders

**Test:** Run `render_batch.py --category vpn` and verify that all 79 VPN entities are rendered to R2. Fetch one of them directly from R2 and verify the HTML is correct.

**End of Day 16 checklist:**

- [ ] Render pipeline can render a batch of entities
- [ ] Output uploaded to R2 with content hashing
- [ ] Atomic staging-to-live key rename works
- [ ] 79 VPN entities rendered and verified
- [ ] Redis job queue functional

#### Day 17 (Tuesday April 28) — Cloudflare Worker for v2 routing

**All day (5 hours):** Build the Cloudflare Worker that serves v2 content from R2.

This Worker is separate from the Phase 0 fallback Worker (though they share infrastructure). The v2 Worker:

1. Accepts requests matching `/safe/*` (and only `/safe/*` for now)
2. Computes the R2 key for the entity
3. Fetches from R2
4. If found, returns it with appropriate cache headers
5. If not found, falls through to v1 origin (so v2 can be rolled out incrementally)
6. Adds `X-Served-By: v2` header for observability

Initial deployment: the Worker is deployed but routed from a staging URL like `v2.nerq.ai/safe/nordvpn`, not from production. This lets Anders test v2 without affecting live traffic.

**Test:** `curl v2.nerq.ai/safe/nordvpn` returns the v2-rendered HTML from R2. `curl v2.nerq.ai/safe/nonexistent` falls through to v1 origin.

**End of Day 17 checklist:**

- [ ] Cloudflare Worker deployed to staging subdomain
- [ ] `v2.nerq.ai/safe/nordvpn` serves v2 HTML from R2
- [ ] Unknown entities fall through to v1
- [ ] X-Served-By header present

#### Day 18 (Wednesday April 29) — Observability integration

**All day (5 hours):** Connect v2 to the observability stack from Week 2.

Claude provides:

1. structlog configuration that writes to stdout in JSON format
2. Prometheus metrics endpoint on v2 exposing: request count, request duration, render duration, R2 upload success/failure, sacred bytes drift, database query count
3. Loki integration (Promtail running as sidecar, shipping logs to Nürnberg Loki)
4. Grafana dashboard with panels for: v2 request rate, latency, error rate, render throughput, R2 storage usage, sacred bytes drift
5. Alert rules: alert if v2 error rate > 1%, if sacred bytes drift > 0, if render latency > 5s p95, if R2 upload failure rate > 0.1%

**End of Day 18 checklist:**

- [ ] structlog writing JSON logs
- [ ] Prometheus scraping v2 metrics
- [ ] Loki ingesting v2 logs
- [ ] Grafana dashboard live with all panels
- [ ] Alert rules loaded into Alertmanager
- [ ] Test alert fires correctly (trigger a fake error)

#### Day 19 (Thursday April 30) — Staging bake-in

**All day:** Let v2 run on the staging subdomain for 24+ hours with synthetic traffic from multiple locations. Watch the dashboards. Look for any anomalies.

Claude provides a synthetic traffic script that:

- Hits `v2.nerq.ai/safe/{entity}` for 50 different entities every minute
- Varies User-Agent strings to simulate Claude, ChatGPT, Perplexity, Googlebot, and human Firefox/Chrome
- Logs any non-200 responses or latency spikes

Anders runs this script from the Hetzner Helsinki node (so it comes from a different network than Mac Studio).

**End of Day 19 checklist:**

- [ ] 24 hours of synthetic traffic on v2 staging
- [ ] Zero 5xx errors
- [ ] p95 latency < 500ms
- [ ] Sacred bytes drift remains zero
- [ ] No alert fired unexpectedly

#### Day 20 (Friday May 1) — End of Phase 1 review

**Morning (2 hours):** Final verification before cutover decision.

Run the full Phase 1 verification checklist. If anything fails, Day 20 becomes "fix the blocker" and the cutover is delayed to Monday.

If everything passes, make the cutover decision: proceed to Phase 2 on Monday May 4, or extend Phase 1 if there are concerns.

**Afternoon (2 hours):** Phase 1 retrospective and Phase 2 plan adjustment.

Same format as the Phase 0 retrospective.

**End of Week 4 checklist (Phase 1 complete):**

- [ ] All Phase 1 items from Days 11–19 checked
- [ ] 24+ hours of clean staging traffic
- [ ] Phase 1 retrospective written
- [ ] Cutover decision made (proceed to Phase 2 or extend)
- [ ] Anders confirms readiness for production cutover

---

## Phase 2 — Week 5: First production cutover

### Week 5 — Days 21–25

#### Day 21 (Monday May 4) — Canary cutover

**Morning (30 minutes):** Flip Cloudflare routing for 1% of `/safe/*` traffic to v2.

This is done via a Cloudflare Worker rule that routes a small percentage of requests (based on a random cookie or header hash) to the v2 Worker while the rest continue to v1. Both return 200s. AI crawlers and the vast majority of human traffic still see v1. Only a small canary slice sees v2.

Claude provides the Worker rule update.

**Afternoon:** Watch dashboards. Look for:

- Error rate on v2 vs v1 (should be equal)
- Latency on v2 vs v1 (should be comparable)
- Sacred bytes drift (should be zero)
- AI citation rate (should be unchanged)
- Human bounce rate (should be unchanged)

**End of Day 21 checklist:**

- [ ] 1% canary live for `/safe/*`
- [ ] No anomalies observed over 8 hours
- [ ] AI citation rate within normal variance
- [ ] Sacred bytes drift zero

#### Days 22–23 (Tuesday–Wednesday May 5–6) — Ramp up

If Day 21 went well, ramp canary to 10% on Day 22 and 50% on Day 23. Continue to monitor. Any anomaly pauses the ramp immediately.

**End of Day 23 checklist:**

- [ ] 50% of `/safe/*` traffic on v2
- [ ] 48 hours of clean metrics at all traffic levels
- [ ] Sacred bytes drift remains zero

#### Day 24 (Thursday May 7) — Full cutover of `/safe/*`

Flip to 100% of `/safe/*` on v2. v1 still handles all other page types. If anything goes wrong, a single Cloudflare Worker rule change reverts to 100% v1 in under 60 seconds.

**End of Day 24 checklist:**

- [ ] 100% of `/safe/*` on v2
- [ ] 12 hours of clean metrics
- [ ] Rollback procedure tested in a dry run

#### Day 25 (Friday May 8) — Phase 2 retrospective

First production cutover complete. v2 is serving real traffic for real users and real AI crawlers. The Strangler Fig pattern is proven to work for Nerq specifically.

Retrospective format: what worked, what didn't, what to adjust for Phase 3 (migrating the next page types).

**End of Week 5 checklist (Phase 2 complete):**

- [ ] `/safe/{entity}` fully on v2 for all languages
- [ ] No degradation in AI citations or human traffic
- [ ] Rollback procedure documented and tested
- [ ] Phase 2 retrospective written
- [ ] Phase 3 plan drafted (next page types: `/best/`, `/compare/`, `/alternatives/`)

---

## Phase 1 closing notes

At the end of week 5, Nerq has made a fundamental architectural transition. One page type runs on a modern, tested, observable, typed, versioned, and documented v2 platform. The remaining page types are mechanical migrations following the same pattern that is now proven.

v1 continues to run and handles all other page types. There is no urgency to migrate the rest — each page type can be migrated on its own schedule, with the same week-long canary process if needed. The hardest decisions (architecture, sacred element protection, data model, disaster recovery) have all been made and implemented.

Phase 3 begins in week 6, migrating `/best/` as the second page type. Phase 3 and Phase 4 are documented in a separate plan that will be written at the end of week 5 based on learnings from Phases 0–2.

---

## Appendix A: Rollback procedures

Every change in this plan has an explicit rollback procedure. The rollback for the most dangerous actions:

**Rollback of Day 2 linter installation:** Remove the pre-commit hook from `.pre-commit-config.yaml` and revert the commits. Package-page bug stays fixed (separate commit).

**Rollback of Day 3 golden file tests:** Remove the sacred test from CI. The fixtures remain in the repository as documentation.

**Rollback of Day 5 R2 fallback Worker:** Delete the Cloudflare Worker. Origin serves directly again. No data loss.

**Rollback of Day 8–9 PostgreSQL replication:** Stop replication on replicas. Primary is unaffected. Replicas can be wiped and re-initialized.

**Rollback of Day 21 canary:** Single Cloudflare Worker rule change routes 0% to v2. Takes under 60 seconds.

**Rollback of Day 24 full cutover:** Same as Day 21 rollback. v1 still runs and still renders all page types.

**Worst case rollback:** Full `git revert` of all Phase 0 and Phase 1 changes. v1 returns to Dag 32 state. The Hetzner nodes and Backblaze backup remain as disaster recovery.

---

## Appendix B: Critical file paths reference

For Anders' reference during execution:

**v1 (existing):**

- Code: `/Users/anstudio/agentindex/agentindex/`
- API LaunchAgent: `~/Library/LaunchAgents/com.nerq.api.plist`
- PostgreSQL: `/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql -U anstudio -d agentindex`
- Analytics DB: `~/agentindex/logs/analytics.db`

**v2 (new, to be created):**

- Code: `/Users/anstudio/nerq-v2/`
- GitHub: `github.com/[anders-org]/nerq-v2`
- Docker images: `ghcr.io/[anders-org]/nerq-v2:latest`
- R2 bucket (hot path): `nerq-v2-content`
- R2 bucket (fallback): `nerq-cache-fallback`
- B2 bucket (backups): `nerq-pg-backups`

**Hetzner nodes:**

- Nürnberg: `nerq-nbg-1` (Tailscale IP assigned at provisioning)
- Helsinki: `nerq-hel-1` (Tailscale IP assigned at provisioning)

**Baselines:**

- Day 1 baseline: `/Users/anstudio/nerq-baselines/2026-04-08/`

---

## Appendix C: Success metrics for Phase 0 + Phase 1

The phases are successful if, at the end of week 5:

1. **AI citations are within normal variance of the Day 1 baseline.** No degradation attributable to v2.
2. **Human traffic is within normal variance.** Same.
3. **Sacred bytes drift is exactly zero.** No changes to the 30 fixture files.
4. **Zero v2-related incidents.** No pages, no emergency reverts, no 5xx spikes.
5. **The linter is green on the full codebase.** No hardcoded internal links in any file.
6. **Package pages serve correctly.** The Day 32 bug is permanently fixed.
7. **PostgreSQL has a tested, verifiable offsite backup.** Restore verification passes.
8. **Mac Studio outage survival is proven.** Simulated outage test passes.
9. **v2 has served real production traffic for `/safe/*`.** Full cutover reached at Day 24.
10. **The team (Anders + Claude) has written two retrospectives and confirmed readiness for Phase 3.**

If any of these fail, Phase 3 is delayed until the failure is resolved.

---

*End of Phase 0 + Phase 1 Implementation Plan.*
