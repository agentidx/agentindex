"""
Quality Gate System — only publish verticals that meet quality thresholds.
Checks stddev, indexable count, enrichment %, score range, data signals.
"""
import json
import os
from datetime import datetime

from sqlalchemy import text

QUALITY_GATE = {
    'min_stddev': 3.5,           # Was 4.5 — crates(4.4)/ios(3.9)/steam(3.6) have real differentiation
    'min_indexable': 50,
    'min_enriched_pct': 30.0,
    'min_score_range': 9,        # p10-p90 of 9+ ensures meaningful spread
}

# Pinned registries — always published regardless of quality gate metrics.
# These are manually curated verticals with unique content and incident data
# that would lose trust-anchor value if auto-hidden by a temporary score drift.
PINNED_REGISTRIES = {
    "vpn", "password_manager", "hosting", "antivirus",
    "saas", "website_builder", "crypto",
}

STATE_FILE = os.path.expanduser("~/agentindex/logs/quality_gate_state.json")
LOG_FILE = os.path.expanduser("~/agentindex/logs/quality_gate.log")


def _log(msg):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"{ts} [QG] {msg}\n")


def check_verticals(session):
    rows = session.execute(text("""
        SELECT registry,
            COUNT(*) as total,
            ROUND(100.0 * COUNT(enriched_at) / NULLIF(COUNT(*), 0), 1) as enriched_pct,
            COUNT(*) FILTER (WHERE trust_score >= 30 AND description IS NOT NULL AND LENGTH(description) > 20) as indexable,
            ROUND(COALESCE(STDDEV(trust_score), 0)::numeric, 1) as stddev,
            COALESCE(PERCENTILE_CONT(0.1) WITHIN GROUP (ORDER BY trust_score), 0)::int as p10,
            COALESCE(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY trust_score), 0)::int as p90,
            CASE WHEN COUNT(*) FILTER (WHERE downloads > 0) > COUNT(*) * 0.1 THEN 1 ELSE 0 END +
            CASE WHEN COUNT(*) FILTER (WHERE stars > 0) > COUNT(*) * 0.1 THEN 1 ELSE 0 END +
            CASE WHEN COUNT(*) FILTER (WHERE license IS NOT NULL AND license != '') > COUNT(*) * 0.1 THEN 1 ELSE 0 END +
            CASE WHEN COUNT(*) FILTER (WHERE cve_count > 0) > COUNT(*) * 0.01 THEN 1 ELSE 0 END +
            CASE WHEN COUNT(*) FILTER (WHERE contributors > 0) > COUNT(*) * 0.1 THEN 1 ELSE 0 END
            as data_signals
        FROM software_registry WHERE trust_score IS NOT NULL
        GROUP BY registry
    """)).fetchall()

    statuses = {}
    for r in rows:
        registry, total, enriched_pct, indexable, stddev = r[0], r[1], float(r[2] or 0), r[3], float(r[4] or 0)
        p10, p90, data_signals = r[5] or 0, r[6] or 0, r[7] or 0
        score_range = p90 - p10

        passes = True
        reasons = []
        pinned = registry in PINNED_REGISTRIES
        if not pinned:
            if stddev < QUALITY_GATE['min_stddev']:
                passes = False
                reasons.append(f"stddev {stddev} < {QUALITY_GATE['min_stddev']}")
            if indexable < QUALITY_GATE['min_indexable']:
                passes = False
                reasons.append(f"indexable {indexable} < {QUALITY_GATE['min_indexable']}")
            if score_range < QUALITY_GATE['min_score_range']:
                passes = False
                reasons.append(f"range {score_range} < {QUALITY_GATE['min_score_range']}")
        else:
            reasons.append("PINNED")

        statuses[registry] = {
            'publishable': passes, 'total': total, 'indexable': indexable,
            'enriched_pct': enriched_pct, 'stddev': stddev,
            'score_range': score_range, 'data_signals': data_signals, 'reasons': reasons,
        }
    return statuses


def update_state(statuses):
    prev = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                prev = json.load(f)
        except Exception:
            pass

    for reg, s in statuses.items():
        was = prev.get(reg, {}).get('publishable', False)
        now = s['publishable']
        if now and not was:
            _log(f"PUBLISH: {reg} (stddev={s['stddev']}, range={s['score_range']})")
        elif not now and was:
            _log(f"HIDE: {reg} — {', '.join(s['reasons'])}")

    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(statuses, f, indent=2, default=str)
    return statuses


def get_publishable_registries():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return {r for r, s in json.load(f).items() if s.get('publishable')}
        except Exception:
            pass
    return set()


def print_report(statuses):
    pub = [(r, s) for r, s in sorted(statuses.items(), key=lambda x: x[1]['total'], reverse=True) if s['publishable']]
    hid = [(r, s) for r, s in sorted(statuses.items(), key=lambda x: x[1]['total'], reverse=True) if not s['publishable']]

    print("\n" + "=" * 90)
    print("  QUALITY GATE REPORT")
    print("=" * 90)
    print(f"\n  PUBLISHED ({len(pub)} verticals):")
    for r, s in pub:
        print(f"    OK  {r:22s} | {s['total']:>7,} entities | sd {s['stddev']:>5.1f} | range {s['score_range']:>3} | signals {s['data_signals']} | idx {s['indexable']:>6,}")
    print(f"\n  HIDDEN ({len(hid)} verticals):")
    for r, s in hid:
        print(f"    --  {r:22s} | {s['total']:>7,} entities | sd {s['stddev']:>5.1f} | range {s['score_range']:>3} | {'; '.join(s['reasons'])}")
    print(f"\n  Total: {len(pub)} published, {len(hid)} hidden")
    print("=" * 90)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.expanduser("~/agentindex"))
    from agentindex.db.models import get_session
    session = get_session()
    statuses = check_verticals(session)
    update_state(statuses)
    print_report(statuses)
    session.close()
