"""secret_scan.py — API-key hygiene scanner for ~/agentindex.

Scans the repository tree for well-known secret patterns (AWS access
keys, Anthropic API keys, Stripe live keys, GCP service-account JSON
markers, generic PEM private keys) and emits a markdown report listing
only ``path``, ``line``, and ``pattern_name`` — never the matched value
itself. The scanner's output is safe to commit, share, and paste into
chat.

If any hits are found, one ``secret-removal-<slug>`` task is enqueued
per unique file via the Smedjan queue CLI with ``risk=high``. The queue
resolver promotes high-risk rows straight to ``needs_approval`` so a
human decides how to remediate (rotate first, then purge from working
tree and git history — a scanner must never automate key deletion).

Invocation
----------
    python3 -m smedjan.scripts.secret_scan              # scan + enqueue hits
    python3 -m smedjan.scripts.secret_scan --dry-run    # scan + report, no enqueue
    python3 -m smedjan.scripts.secret_scan --verbose    # DEBUG logging

Exclusions
----------
* ``.git/``, ``__pycache__/``, ``node_modules/``, virtualenv dirs.
* ``smedjan/migration-backups/`` (pg_dump intentionally contains blob
  data that looks like random high-entropy strings).
* ``logs/`` (multi-gigabyte SQLite + log files; binary, would be
  skipped anyway but fast-pruning the whole tree saves IO).
* The scanner file itself (its regexes would self-match).
* Files > 10 MB and files that look binary (null byte in first 8 KB).
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("smedjan.secret_scan")

REPO_ROOT = Path(os.path.expanduser("~/agentindex")).resolve()
REPORT_DIR = Path(os.path.expanduser("~/smedjan/audits"))

# Directory basenames that are pruned during os.walk (never descended into).
EXCLUDE_DIR_NAMES = frozenset({
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "dist",
    "build",
})

# Absolute-path prefixes within REPO_ROOT that we refuse to descend into.
# The migration-backups exclusion is in the task spec — pg_dump output
# contains blob data that can trivially match high-entropy regexes.
EXCLUDE_PATH_PREFIXES: tuple[Path, ...] = (
    REPO_ROOT / "smedjan" / "migration-backups",
    REPO_ROOT / "logs",
)

# Don't scan the scanner itself — its own regex literals would match.
SELF_PATH = Path(__file__).resolve()

# Filename allowlist: files by basename that are expected to contain a
# PEM-armoured private key as a placeholder for future integration work
# (e.g. a GitHub App install key). The allowlist only suppresses the
# scan — the file must still be .gitignored (git never sees it).
# Add a filename here instead of exfiltrating the key to silence a flap.
ALLOWLIST_FILENAMES: frozenset[str] = frozenset({
    "github-app-private-key.pem",
})

# Max file size to scan (bytes). 10 MB is generous for source; anything
# larger is almost certainly data/binary and already pruned by the
# binary-detect heuristic, but we short-circuit on size for speed.
MAX_BYTES = 10 * 1024 * 1024

# Secret patterns. The keys of this dict are what appear in reports and
# in enqueued task descriptions — keep them short and stable.
#
# IMPORTANT: matched values are NEVER logged or written to disk. The
# scanner records only (path, lineno, pattern_name).
PATTERNS: dict[str, re.Pattern[str]] = {
    # AWS access key id (IAM user + STS short-term). 20 chars, AKIA/ASIA prefix.
    "aws_access_key":        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    # Anthropic API key — ``sk-ant-`` prefix, opaque body.
    "anthropic_api_key":     re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{32,}"),
    # Stripe live keys. We report live + restricted; test keys (sk_test_)
    # are intentionally NOT flagged — they are safe to ship.
    "stripe_live_secret":    re.compile(r"\bsk_live_[A-Za-z0-9]{16,}"),
    "stripe_live_pub":       re.compile(r"\bpk_live_[A-Za-z0-9]{16,}"),
    "stripe_restricted":     re.compile(r"\brk_live_[A-Za-z0-9]{16,}"),
    # GCP service-account JSON marker. Finding this + a private-key block
    # in the same file is a strong signal.
    "gcp_service_account":   re.compile(r'"type"\s*:\s*"service_account"'),
    # Any PEM-armoured private key (RSA / EC / OpenSSH / plain).
    "pem_private_key":       re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
}


@dataclass(frozen=True)
class Hit:
    path: Path
    lineno: int
    pattern: str


# ── Walking the tree ─────────────────────────────────────────────────────

def _is_probably_binary(path: Path) -> bool:
    """Cheap binary sniff: null byte in first 8 KB → treat as binary."""
    try:
        with path.open("rb") as fh:
            return b"\x00" in fh.read(8192)
    except OSError:
        return True


def _iter_files(root: Path):
    root = root.resolve()
    excluded_prefixes = tuple(str(p) for p in EXCLUDE_PATH_PREFIXES)
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded dirs in-place so os.walk never descends into them.
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIR_NAMES]

        if any(dirpath.startswith(p) for p in excluded_prefixes):
            dirnames[:] = []
            continue

        dp = Path(dirpath)
        for fn in filenames:
            p = dp / fn
            try:
                resolved = p.resolve()
            except OSError:
                continue
            if resolved == SELF_PATH:
                continue
            if fn in ALLOWLIST_FILENAMES:
                log.debug("skip %s: allowlisted filename", p)
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_size > MAX_BYTES:
                log.debug("skip %s: %d bytes > max", p, st.st_size)
                continue
            if _is_probably_binary(p):
                log.debug("skip %s: binary", p)
                continue
            yield p


def scan(root: Path = REPO_ROOT) -> list[Hit]:
    hits: list[Hit] = []
    for path in _iter_files(root):
        try:
            fh = path.open("r", encoding="utf-8", errors="replace")
        except OSError as e:
            log.warning("skip %s: %s", path, e)
            continue
        with fh:
            for lineno, line in enumerate(fh, start=1):
                for name, pat in PATTERNS.items():
                    if pat.search(line):
                        hits.append(Hit(path=path, lineno=lineno, pattern=name))
    return hits


# ── Report ───────────────────────────────────────────────────────────────

def _rel(path: Path) -> Path:
    try:
        return path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return path


def write_report(hits: list[Hit], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    patterns_str = ", ".join(sorted(PATTERNS))
    per_pattern: dict[str, int] = {}
    for h in hits:
        per_pattern[h.pattern] = per_pattern.get(h.pattern, 0) + 1

    lines: list[str] = [
        "# secret_scan.py — dry-run report",
        "",
        f"- Generated (UTC): {now}",
        f"- Root: `{REPO_ROOT}`",
        f"- Patterns scanned: {patterns_str}",
        f"- Total hits: **{len(hits)}**",
        "",
        "## Hits by pattern",
        "",
    ]
    if per_pattern:
        for name in sorted(per_pattern):
            lines.append(f"- `{name}`: {per_pattern[name]}")
    else:
        lines.append("- (none)")
    lines += ["", "## Hits", "", "| Path | Line | Pattern |", "|------|------|---------|"]
    for h in sorted(hits, key=lambda h: (str(h.path), h.lineno, h.pattern)):
        lines.append(f"| `{_rel(h.path)}` | {h.lineno} | `{h.pattern}` |")
    lines.append("")
    out_path.write_text("\n".join(lines))


# ── Enqueue needs_approval tasks ────────────────────────────────────────

_SMEDJAN_CLI = "/Users/anstudio/agentindex/scripts/smedjan"


def _slug_for(path: Path) -> str:
    rel = str(_rel(path))
    slug = re.sub(r"[^A-Za-z0-9]+", "-", rel).strip("-").lower()
    return slug[:70]


def _task_exists(tid: str) -> bool:
    res = subprocess.run(
        [_SMEDJAN_CLI, "queue", "show", tid],
        capture_output=True, text=True, check=False,
    )
    return res.returncode == 0


def enqueue_hits(hits: list[Hit]) -> list[str]:
    """Create one ``secret-removal-<slug>`` task per unique file with hits.

    Idempotent: if a task with the same id already exists (e.g. from a
    previous scan run), we skip it.
    """
    by_file: dict[Path, list[Hit]] = {}
    for h in hits:
        by_file.setdefault(h.path, []).append(h)

    created: list[str] = []
    for path, phits in by_file.items():
        slug = _slug_for(path)
        tid = f"secret-removal-{slug}"[:120]

        if _task_exists(tid):
            log.info("skip enqueue: task %s already exists", tid)
            continue

        patterns = sorted({h.pattern for h in phits})
        lines_hit = sorted({h.lineno for h in phits})
        rel = _rel(path)
        title = f"Secret removal: {rel}"[:200]
        description = (
            f"secret_scan.py flagged {len(phits)} occurrence(s) of pattern(s) "
            f"{patterns} on line(s) {lines_hit} in {rel}. Human review is "
            "required to decide whether these are real credentials or false "
            "positives (test fixtures, docs, example code). If real: rotate "
            "the credential FIRST, then purge from the working tree and from "
            "git history (git filter-repo). This task is needs_approval on "
            "purpose — never automate credential handling."
        )
        acceptance = (
            "Either (a) credential rotated + file cleaned + history scrubbed "
            "and committed, or (b) confirmed false positive and added to the "
            "scanner's allowlist."
        )
        cmd = [
            _SMEDJAN_CLI, "queue", "add",
            "--id", tid,
            "--title", title,
            "--description", description,
            "--acceptance", acceptance,
            "--risk", "high",
            "--whitelist", str(rel),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            log.info("enqueued %s", tid)
            created.append(tid)
        else:
            log.error("queue add failed for %s (rc=%d): %s",
                      tid, res.returncode, (res.stderr or "").strip()[:200])
    return created


# ── Entry point ──────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="secret_scan",
        description="Scan ~/agentindex for secret patterns (path+line+name only).",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="scan and write report; do NOT enqueue tasks.")
    parser.add_argument(
        "--report", type=Path,
        default=REPORT_DIR / f"secret_scan_{datetime.now(timezone.utc).strftime('%Y%m%d')}.md",
        help="where to write the markdown report (default: ~/smedjan/audits/).",
    )
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="DEBUG-level logging.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    log.info("scanning %s (excluding %d dir names, %d path prefixes)",
             REPO_ROOT, len(EXCLUDE_DIR_NAMES), len(EXCLUDE_PATH_PREFIXES))
    hits = scan(REPO_ROOT)
    log.info("scan complete: %d hit(s) across %d pattern(s)",
             len(hits), len({h.pattern for h in hits}))

    write_report(hits, args.report)
    log.info("report written: %s", args.report)

    if hits and not args.dry_run:
        created = enqueue_hits(hits)
        log.info("enqueued %d needs_approval task(s)", len(created))

    return 0


if __name__ == "__main__":
    sys.exit(main())
