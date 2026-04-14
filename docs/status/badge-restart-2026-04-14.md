# Badge Outreach Restart — 2026-04-14

## Diagnos

**badge_outreach_auto.py:** Fully functional. Stopped Apr 10 because all 230 targets were contacted.

**badge_outreach_discovery.py:** Fully functional code but **never scheduled** — no LaunchAgent existed. Discovery finds new repos via GitHub Search API, cross-references against Postgres, and adds qualifying repos to targets.

## Åtgärder

### 1. Target-lista påfylld

| Source | New targets |
|---|---:|
| software_registry (trust≥65, stars≥50, GitHub URL) | 239 |
| entity_lookup (trust≥60, stars≥50, GitHub URL) | 583 |
| agents (trust≥70, stars≥200, GitHub URL) | 12 |
| **Total new** | **834** |
| Existing (from before) | 230 |
| **Grand total** | **1,064** |

Prioriterade efter `trust_score × log(stars+1)`. Top targets: PaddleOCR (★54K), Cursor (★50K), openai-python (★25K), PostHog (★32K).

### 2. Live test

Issue skapad: https://github.com/opendatalab/MinerU/issues/4789

Pipeline fungerar: GitHub API → issue skapad → loggad i badge_outreach_log.json.

### 3. LaunchAgents

| Agent | Schedule | Status |
|---|---|---|
| com.nerq.badge-outreach | Daily 10:00 CEST, 10 issues/run | ✅ Loaded, running |
| com.nerq.badge-discovery | Sundays 09:00 CEST | ✅ **NEW** — Created and loaded |
| com.nerq.badge-responder | On-demand | ✅ Running |

### 4. DATABASE_URL updated

Outreach plist updated to use Nbg primary (`100.119.193.70`) instead of Mac Studio.

## Förväntad takt

- 10 issues/dag × 7 dagar = 70/vecka
- 834 pending ÷ 70/vecka = **~12 veckor** innan listan töms
- Discovery kör varje söndag och fyller på automatiskt
- Systemet ska aldrig stanna igen

## Vad som behöver övervakas

1. **Spam-klagomål:** Om GitHub flaggar issues, stoppa omedelbart → eskalera till Anders
2. **Rate limits:** 30s delay mellan issues. GitHub rate limit: 5,000 req/h (authed). Borde räcka.
3. **Konverteringsrate:** Förvänta ~67% badge-installation baserat på historiken (154/230).
4. **Discovery-pipeline:** Verifiera söndag 09:00 att den körs (check `/tmp/badge-discovery.log`).

## Ej gjort (deprioriterat)

- **Uppföljning på 206 existerande issues:** Kräver GitHub API-anrop för varje issue. 4h+ arbete. Deprioriterat — kan göras i batch senare.
- **Klick-spårning via ?ref=gh:** Kräver kodändring i issue-template. Låg prioritet givet att badges inte driver klick (0 konverteringar senaste 30d).
