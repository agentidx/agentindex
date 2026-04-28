"""
Populate ``smedjan.compare_priority_queue`` and export the top-decile JSON
that feeds ``agentindex/intelligence/comparison_generator.py``.

Source: FU-CITATION-20260422-06.

Why a snapshot table instead of the live view alone
---------------------------------------------------
``smedjan.compare_activation_leaderboard`` re-aggregates 7d of requests on
every SELECT (fine for ad-hoc inspection, expensive if called every time
the /compare/ generator runs). This script samples the view once per
refresh cycle, writes a stable top-decile snapshot into
``smedjan.compare_priority_queue``, and dumps the same snapshot to JSON
at ``~/agentindex/data/compare_priority_queue.json`` for the Nerq-side
generator to pick up.

Top-decile definition
---------------------
Decile of pairs with ``activation_score > 0``. If the view has fewer than
``MIN_DECILE_SIZE`` positive-score pairs, we take all of them rather
than refusing to publish — starvation of the priority queue is worse
than accepting a small sample in the early days of the signal.

Invocation
----------
Run as ``python3 -m smedjan.measurement.compare_activation_refresh``.
Idempotent — wraps the swap in a transaction.

Contract with the Nerq-side generator
-------------------------------------
The JSON is a list of objects with at least:
    {"pair_slug", "slug_a", "slug_b",
     "bot_7d", "ai_mediated_7d", "raw_activation_ratio",
     "slug_age_days", "activation_score", "activation_rank",
     "snapshot_at"}
The generator reads this file (if present) and seeds its output with
``type="priority-activated"`` rows before enumerating its existing
category/global pairs. Slug names are looked up from entity_lookup on
the generator side, not here — this script emits slugs, not display names.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from smedjan.sources import smedjan_db_cursor

log = logging.getLogger("smedjan.measurement.compare_activation_refresh")

MIN_DECILE_SIZE = 25  # Floor so the generator always sees *some* priority.
OUTPUT_JSON = Path.home() / "agentindex" / "data" / "compare_priority_queue.json"


def _read_leaderboard_top_decile(cur) -> list[dict]:
    """Return the top-decile rows (by activation_score) from the live view.

    Decile is computed over pairs with activation_score > 0 — pairs with
    no mediated traffic at all are irrelevant for prioritisation.
    """
    cur.execute(
        """
        WITH positive AS (
            SELECT *
              FROM smedjan.compare_activation_leaderboard
             WHERE activation_score > 0
        ),
        sized AS (
            SELECT greatest(%s, (count(*) / 10)::integer) AS cutoff
              FROM positive
        )
        SELECT pair_slug, slug_a, slug_b,
               bot_7d, ai_mediated_7d,
               raw_activation_ratio, slug_age_days,
               activation_score, activation_rank
          FROM positive, sized
         WHERE activation_rank <= sized.cutoff
         ORDER BY activation_rank ASC
        """,
        (MIN_DECILE_SIZE,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _swap_priority_queue(cur, rows: list[dict], snapshot_at: datetime) -> int:
    """Atomically replace ``smedjan.compare_priority_queue`` with ``rows``."""
    cur.execute(
        """
        CREATE TEMP TABLE _cpq_staging (LIKE smedjan.compare_priority_queue)
        ON COMMIT DROP
        """
    )
    cur.executemany(
        """
        INSERT INTO _cpq_staging
            (pair_slug, slug_a, slug_b, bot_7d, ai_mediated_7d,
             raw_activation_ratio, slug_age_days,
             activation_score, activation_rank, snapshot_at)
        VALUES (%(pair_slug)s, %(slug_a)s, %(slug_b)s, %(bot_7d)s, %(ai_mediated_7d)s,
                %(raw_activation_ratio)s, %(slug_age_days)s,
                %(activation_score)s, %(activation_rank)s, %(snapshot_at)s)
        """,
        [
            {**r, "snapshot_at": snapshot_at}
            for r in rows
        ],
    )
    cur.execute("TRUNCATE smedjan.compare_priority_queue")
    cur.execute(
        """
        INSERT INTO smedjan.compare_priority_queue
            (pair_slug, slug_a, slug_b, bot_7d, ai_mediated_7d,
             raw_activation_ratio, slug_age_days,
             activation_score, activation_rank, snapshot_at)
        SELECT pair_slug, slug_a, slug_b, bot_7d, ai_mediated_7d,
               raw_activation_ratio, slug_age_days,
               activation_score, activation_rank, snapshot_at
          FROM _cpq_staging
        """
    )
    cur.execute("SELECT count(*) FROM smedjan.compare_priority_queue")
    (written,) = cur.fetchone()
    return int(written)


def _write_json(rows: list[dict], snapshot_at: datetime) -> Path:
    """Serialise rows to the Nerq-side priority-queue JSON. Values are
    normalised to JSON-safe types (Decimal/real → float, datetime → iso)."""

    def _safe(v):
        if v is None:
            return None
        if isinstance(v, (int, str)):
            return v
        if isinstance(v, datetime):
            return v.isoformat()
        # Decimal, real, float
        try:
            return float(v)
        except (TypeError, ValueError):
            return str(v)

    payload = {
        "snapshot_at": snapshot_at.isoformat(),
        "source": "smedjan.compare_activation_leaderboard",
        "task": "FU-CITATION-20260422-06",
        "min_decile_size": MIN_DECILE_SIZE,
        "pairs": [
            {k: _safe(v) for k, v in r.items()}
            for r in rows
        ],
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write via rename so the generator never sees a half-written file.
    tmp = OUTPUT_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str))
    tmp.replace(OUTPUT_JSON)
    return OUTPUT_JSON


def refresh() -> dict:
    snapshot_at = datetime.now(timezone.utc)
    with smedjan_db_cursor() as (_, cur):
        rows = _read_leaderboard_top_decile(cur)
        written = _swap_priority_queue(cur, rows, snapshot_at)

    json_path = _write_json(rows, snapshot_at)
    return {
        "pairs_in_snapshot": written,
        "json_path": str(json_path),
        "snapshot_at": snapshot_at.isoformat(timespec="seconds"),
        "top_5_pair_slugs": [r["pair_slug"] for r in rows[:5]],
    }


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    try:
        summary = refresh()
    except Exception as e:  # noqa: BLE001 — top-level guard for systemd/cron
        log.exception("compare_activation_refresh failed: %s", e)
        return 1
    print(
        f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] "
        f"compare_activation_refresh: {summary}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
