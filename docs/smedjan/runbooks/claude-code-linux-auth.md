# Claude Code Linux-auth — M0 failure + workaround

**Date:** 2026-04-18
**Claude Code version tested:** 2.1.114 (native binary, Linux x64)
**Test host:** smedjan.nbg1.hetzner (Ubuntu 24.04 LTS)
**Outcome:** M0 **failed**. Worker relocated to Mac Studio (hybrid architecture).

---

## What was attempted

1. `curl -fsSL https://claude.ai/install.sh | bash` — native-binary install succeeded. `/home/smedjan/.local/bin/claude --version` prints `2.1.114`. PATH fixed in `~/.bashrc`.
2. `claude setup-token` (long-lived subscription token) — drove via pexpect. URL-paste OAuth flow. Token never saved; `claude auth status` kept returning `{"loggedIn": false}` after each attempt.
3. `claude auth login --claudeai` — same URL-paste flow, same outcome.
4. Inspected every CLI flag + command for a device-code / API-token / keychain-less flow: none exists. `--bare` mode can only authenticate via `ANTHROPIC_API_KEY`, which is a **paid API path and is forbidden** per `feedback_no_paid_apis.md`.
5. macOS Keychain entry on Mac Studio cannot be exported to Linux (format-incompatible).

## Why URL-paste fails over SSH

The `claude` CLI prints an OAuth authorization URL and waits for the user to paste back the returned code. Two structural problems when this runs inside a remote automation loop:

1. **Code expiry window.** Anthropic's auth code appears to expire ~60–120 s after the user clicks "Authorize" in the browser. The pasted code must reach the waiting CLI inside that window.
2. **Chat-relay RTT.** In our automated setup, each round-trip is: I generate URL → I send URL to user → user opens browser → authorises → user copies code → user sends code to me → I SSH+paste into the waiting process. That chain is reliably >2 minutes; tests confirmed codes were rejected every time.

With `pexpect`/`tmux` automation we got far enough to see the exact CLI output (URL captured cleanly, waiting process confirmed running), but the paste window closed before the code arrived.

## What would unblock a retry

- **Device-code flow.** If Anthropic adds a flow where the CLI prints a *device code* while polling a status endpoint (GitHub CLI pattern), the code-expiry problem evaporates — the user has 10+ min and there is no paste step at all.
- **Long-lived token export.** If `claude setup-token` begins emitting the raw token to stdout (instead of only writing to Keychain/credentials-file on Mac), we could generate it on Mac Studio and copy the file to smedjan.
- **Static API-token mode on the Max plan.** Currently `--bare` mode requires `ANTHROPIC_API_KEY` which is metered paid API. If the Max subscription exposes a persistent bearer token, the worker could use `env ANTHROPIC_API_KEY=... claude --bare ...` without paid-API billing.

**Until then: do not re-attempt Linux auth.** Worker stays on Mac Studio (hybrid).

## Retry signal

Check when Claude Code release notes announce any of:

- `claude setup-token --device-flow` or equivalent
- A "headless Linux" install guide at `https://code.claude.com/docs`
- A new `claude auth` subcommand that accepts a pre-generated code via stdin/arg (not the interactive paste)

When the signal lands, re-run M0 from the top: re-install (or `claude update`), try the new flow, verify `claude -p "hello"` works non-interactively. If green, migrate worker from Mac Studio to smedjan (reverse of M11/M12 worker placement). All other Smedjan components already live on smedjan and do not need to move.

## Current state of the smedjan host

- `/home/smedjan/.local/bin/claude` (v2.1.114) — left installed for easy retry
- PATH updated in `~/.bashrc`
- No credentials, no open processes
- Auth artefacts in `/tmp/claude-*` cleaned
