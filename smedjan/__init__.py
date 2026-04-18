"""
Smedjan Factory Core — autonomous task-queue runtime for Nerq / ZARQ.

Layout
------
- config.py         : constants, DSNs, paths, ntfy topic
- schema.sql        : Postgres DDL for smedjan schema
- factory_core.py   : DB operations (claim_next_task, mark_*, approve, ...)
- ntfy.py           : lightweight wrappers around ntfy.sh (no paid APIs)
- cli.py            : argparse CLI (smedjan queue add / list / show / ...)
- worker.py         : subprocess loop (STUB until Phase B activation)
- seeds.sql         : T003..T015 seed tasks
- README.md         : operator notes

All external calls are restricted to the Max-subscription `claude` CLI and
free-tier HTTP (ntfy.sh, Postgres socket). Paid APIs are forbidden — see
feedback memory `feedback_no_paid_apis.md`.
"""

__version__ = "0.1.0-phase-a"
