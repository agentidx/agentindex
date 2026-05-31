#!/usr/bin/env python3
"""FB-F2-20260531-003: freshness-refresh prep (read-only, fallback-generated).

Determine the top-5 software_registry registries by ai_demand_scores
coverage (join smedjan.ai_demand_scores -> software_registry on slug,
count matching rows per registry, take the 5 largest), then emit the 200
oldest enriched rows in those registries with their ai_demand_score
left-joined on.

ai_demand_scores carries (slug, score) and has no registry column, so the
registry dimension comes from software_registry; the join key is slug.
The join is cross-DB (software_registry on the Nerq RO replica,
ai_demand_scores on the smedjan DB) so it is assembled with the slug list
passed across.  No enricher call — prep work only; a later non-fallback
task consumes the CSV.

Self-contained: DSN resolution + read-only guard are replicated inline
(mirrors smedjan.config / smedjan.sources) so this runs under any
interpreter that has psycopg2.  Run with:
    /opt/homebrew/bin/python3 smedjan/audits/FB-F2-20260531-003.py
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import tomllib
from pathlib import Path

import psycopg2

OUT_PATH = os.path.expanduser("~/smedjan/audits/FB-F2-20260531-003.csv")

_VAR_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _config_dir() -> Path:
    env = os.environ.get("SMEDJAN_CONFIG_DIR")
    for cand in (
        Path(env) if env else None,
        Path.home() / "smedjan" / "config",
        Path("/home/smedjan/smedjan/config"),
    ):
        if cand and (cand / "config.toml").exists():
            return cand
    raise RuntimeError("no smedjan config.toml found")


def _read_dotenv(path: Path) -> dict:
    out: dict = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _dsn(section: str) -> str:
    """Resolve a DSN from config.toml with ${VAR} substituted from .env."""
    d = _config_dir()
    env = _read_dotenv(d / ".env")
    raw = tomllib.loads((d / "config.toml").read_text())
    dsn = (raw.get(section) or {}).get("dsn")
    if not dsn:
        raise RuntimeError(f"{section}: no DSN in config.toml")

    def _sub(m: "re.Match[str]") -> str:
        key = m.group(1)
        if key not in env:
            raise KeyError(f"config references unset secret ${{{key}}}; check .env")
        return env[key]

    return _VAR_RE.sub(_sub, dsn)


def main() -> int:
    # 1. smedjan DB: ai_demand_scores universe -> score keyed by slug.
    conn = psycopg2.connect(_dsn("smedjan_db"), connect_timeout=15)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT slug, score FROM smedjan.ai_demand_scores")
            ads_rows = cur.fetchall()
    finally:
        conn.close()
    ads_by_slug = {slug: score for slug, score in ads_rows}
    slugs = list(ads_by_slug.keys())

    # 2. Nerq RO: coverage join + 200 oldest rows.
    conn = psycopg2.connect(_dsn("nerq_readonly_source"), connect_timeout=15)
    try:
        with conn.cursor() as cur:
            cur.execute("SET default_transaction_read_only = on")

            # 2a. Top-5 registries by ai_demand_scores coverage: count
            #     software_registry rows per registry whose slug is in ADS.
            cur.execute(
                """
                SELECT registry, COUNT(*) AS n
                FROM software_registry
                WHERE slug = ANY(%s)
                GROUP BY registry
                ORDER BY n DESC, registry ASC
                LIMIT 5
                """,
                (slugs,),
            )
            top_rows = cur.fetchall()
            top5 = [r[0] for r in top_rows]
            coverage = {r[0]: int(r[1]) for r in top_rows}

            # 2b. 200 oldest rows for those registries (Postgres-side ordering).
            cur.execute(
                """
                SELECT slug, registry, enriched_at
                FROM software_registry
                WHERE registry = ANY(%s)
                ORDER BY registry, enriched_at ASC
                LIMIT 200
                """,
                (top5,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    # 3. Write CSV, left-joining ai_demand_score on slug.
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["slug", "registry", "enriched_at", "ai_demand_score"])
        for slug, registry, enriched_at in rows:
            score = ads_by_slug.get(slug)
            w.writerow([
                slug,
                registry,
                enriched_at.isoformat() if enriched_at else "",
                "" if score is None else score,
            ])

    evidence = {
        "row_count": len(rows),
        "top5_registries": top5,
        "top5_coverage": coverage,
        "ai_demand_scores_slug_count": len(slugs),
        "output_path": OUT_PATH,
    }
    print(json.dumps(evidence, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
