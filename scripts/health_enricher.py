#!/usr/bin/env python3
"""
Nerq Health Enricher — Populate dimensions/regulatory JSONB from descriptions + APIs.
Works for ingredient, supplement, and cosmetic_ingredient registries.

Run: python3 scripts/health_enricher.py [--registry ingredient|supplement|cosmetic_ingredient] [--limit N]
"""

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("health_enricher")


def _parse_regulatory(desc, registry):
    """Extract structured regulatory data from description text."""
    if not desc:
        return {}
    dl = desc.lower()
    reg = {}

    # FDA
    if "gras" in dl:
        reg["fda"] = "GRAS (Generally Recognized As Safe)"
    elif "fda approved" in dl or "approved (eu/us)" in dl or "approved by fda" in dl:
        reg["fda"] = "Approved"
    elif "fda banned" in dl or "banned in us" in dl or "banned_us" in dl:
        reg["fda"] = "Banned in US"
    elif "fda warning" in dl:
        reg["fda"] = "FDA Warning"
    elif registry == "supplement":
        reg["fda"] = "DSHEA regulated"

    # EU
    if "eu: approved" in dl or "eu approved" in dl or "approved (eu" in dl:
        reg["efsa"] = "Approved"
    elif "banned in eu" in dl or "eu: banned" in dl or "banned_eu" in dl:
        reg["efsa"] = "Banned in EU"
    elif "restricted" in dl and "eu" in dl:
        reg["efsa"] = "Restricted"
    elif "efsa" in dl:
        reg["efsa"] = "Evaluated by EFSA"

    # E-number
    m = re.search(r'\b(E\d{3}[a-z]?)\b', desc)
    if m:
        reg["e_number"] = m.group(1)

    # IARC
    m = re.search(r'IARC.*?Group\s*(\d[AB]?)', desc, re.I)
    if m:
        g = m.group(1)
        labels = {"1": "Carcinogenic", "2A": "Probably carcinogenic",
                  "2B": "Possibly carcinogenic", "3": "Not classifiable"}
        reg["iarc"] = f"Group {g}: {labels.get(g, '')}"

    # ADI
    m = re.search(r'ADI[:\s]+(\d+[\d.]*\s*mg/kg[^.]*)', desc, re.I)
    if m:
        reg["adi"] = m.group(1).strip()

    # Allergen
    if "allergen" in dl:
        reg["allergen"] = True
    # Banned
    if "banned" in dl:
        reg["has_bans"] = True
    # Controversial
    if any(w in dl for w in ("controversial", "debated", "concern", "linked to")):
        reg["controversial"] = True
    # Pregnancy
    if "pregnancy" in dl and ("not recommended" in dl or "avoid" in dl):
        reg["pregnancy_safe"] = False
    # Evidence level (supplements)
    if "strong evidence" in dl:
        reg["evidence_level"] = "Strong"
    elif "moderate evidence" in dl or "some evidence" in dl:
        reg["evidence_level"] = "Moderate"
    elif "limited evidence" in dl or "emerging" in dl:
        reg["evidence_level"] = "Limited"
    # Drug interactions
    if "drug interaction" in dl or "interact with" in dl:
        reg["drug_interactions"] = True
    # Irritation (cosmetics)
    if "irritation" in dl or "irritant" in dl:
        reg["skin_irritant"] = True

    return reg


def _calculate_dimensions(reg_data, trust_score, registry):
    """Calculate dimension scores from regulatory data."""
    dims = {}

    if registry == "ingredient":
        # Regulatory Status
        fda = reg_data.get("fda", "").lower()
        if "gras" in fda:
            dims["regulatory_status"] = 90
        elif "approved" in fda:
            dims["regulatory_status"] = 80
        elif "banned" in fda:
            dims["regulatory_status"] = 10
        else:
            dims["regulatory_status"] = 50

        efsa = reg_data.get("efsa", "").lower()
        if "banned" in efsa:
            dims["regulatory_status"] = min(dims.get("regulatory_status", 50), 15)

        # Scientific Evidence
        iarc = reg_data.get("iarc", "")
        if "Group 1" in iarc:
            dims["scientific_evidence"] = 15
        elif "Group 2A" in iarc:
            dims["scientific_evidence"] = 30
        elif "Group 2B" in iarc:
            dims["scientific_evidence"] = 45
        elif "Group 3" in iarc:
            dims["scientific_evidence"] = 70
        elif dims.get("regulatory_status", 50) >= 80:
            dims["scientific_evidence"] = 80
        else:
            dims["scientific_evidence"] = 55

        # Health Impact
        hi = 65
        if reg_data.get("has_bans"):
            hi -= 20
        if reg_data.get("allergen"):
            hi -= 10
        if reg_data.get("controversial"):
            hi -= 15
        dims["health_impact"] = max(10, hi)

        # Allergen Risk
        dims["allergen_risk"] = 40 if reg_data.get("allergen") else 80

    elif registry == "supplement":
        ev = reg_data.get("evidence_level", "")
        if ev == "Strong":
            dims["evidence_base"] = 88
        elif ev == "Moderate":
            dims["evidence_base"] = 65
        elif ev == "Limited":
            dims["evidence_base"] = 42
        else:
            dims["evidence_base"] = 55

        dims["safety_profile"] = 75 if not reg_data.get("controversial") else 45
        dims["drug_interactions"] = 45 if reg_data.get("drug_interactions") else 75
        dims["regulatory_status"] = 60  # DSHEA default

    elif registry == "cosmetic_ingredient":
        efsa = reg_data.get("efsa", "").lower()
        dims["regulatory_status"] = 15 if "banned" in efsa else 40 if "restricted" in efsa else 75
        dims["skin_safety"] = 50 if reg_data.get("skin_irritant") else 78
        if reg_data.get("pregnancy_safe") is False:
            dims["skin_safety"] = min(dims["skin_safety"], 55)
        dims["sensitization_risk"] = 40 if reg_data.get("allergen") else 75

    return dims


def enrich_registry(registry, limit=None):
    """Enrich all entities in a registry with parsed regulatory data + dimensions."""
    session = get_session()
    try:
        session.execute(text("SET statement_timeout = '30s'"))
        rows = session.execute(text("""
            SELECT id, slug, name, description, trust_score
            FROM software_registry
            WHERE registry = :reg AND description IS NOT NULL AND description != ''
              AND (dimensions IS NULL OR regulatory IS NULL)
            ORDER BY is_king DESC NULLS LAST, trust_score DESC NULLS LAST
            LIMIT :lim
        """), {"reg": registry, "lim": limit or 10000}).fetchall()

        log.info(f"{registry}: {len(rows)} entities to enrich")
        done = 0
        for r in rows:
            rd = dict(r._mapping)
            reg_data = _parse_regulatory(rd["description"], registry)
            dims = _calculate_dimensions(reg_data, rd["trust_score"] or 50, registry)

            if not reg_data and not dims:
                continue

            # Recalculate total score from dimensions if we have them
            if dims:
                if registry == "ingredient":
                    weights = {"regulatory_status": 0.30, "scientific_evidence": 0.25,
                               "health_impact": 0.25, "allergen_risk": 0.20}
                elif registry == "supplement":
                    weights = {"evidence_base": 0.30, "safety_profile": 0.25,
                               "drug_interactions": 0.20, "regulatory_status": 0.25}
                else:
                    weights = {"regulatory_status": 0.30, "skin_safety": 0.30,
                               "sensitization_risk": 0.20, "skin_safety": 0.20}
                new_score = round(sum(dims.get(k, 50) * w for k, w in weights.items()), 1)
            else:
                new_score = rd["trust_score"] or 50

            # Grade
            if new_score >= 90: grade = "A+"
            elif new_score >= 85: grade = "A"
            elif new_score >= 80: grade = "A-"
            elif new_score >= 75: grade = "B+"
            elif new_score >= 70: grade = "B"
            elif new_score >= 65: grade = "B-"
            elif new_score >= 60: grade = "C+"
            elif new_score >= 55: grade = "C"
            elif new_score >= 50: grade = "C-"
            elif new_score >= 40: grade = "D"
            else: grade = "F"

            session.execute(text("""
                UPDATE software_registry SET
                    dimensions = :dims,
                    regulatory = :reg,
                    trust_score = :score,
                    trust_grade = :grade,
                    enrichment_version = COALESCE(enrichment_version, 0) + 1
                WHERE id = :id
            """), {
                "dims": json.dumps(dims),
                "reg": json.dumps(reg_data),
                "score": new_score,
                "grade": grade,
                "id": str(rd["id"]),
            })
            done += 1
            if done % 200 == 0:
                session.commit()
                log.info(f"  {done} enriched...")

        session.commit()
        log.info(f"{registry}: {done} entities enriched with dimensions + regulatory data")
        return done
    finally:
        session.close()


if __name__ == "__main__":
    registry = None
    limit = None
    for i, arg in enumerate(sys.argv):
        if arg == "--registry" and i + 1 < len(sys.argv):
            registry = sys.argv[i + 1]
        elif arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    total = 0
    if registry:
        total = enrich_registry(registry, limit)
    else:
        for reg in ("ingredient", "supplement", "cosmetic_ingredient"):
            total += enrich_registry(reg, limit)

    log.info(f"Total enriched: {total}")
