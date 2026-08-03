"""L3 — Acceptance grades & checklists (spec: specs/ACCEPTANCE.md).

Expectations are declared BEFORE fabrication and frozen into the job terms:
the grade picks a concrete checklist, the checklist's hash is committed into
the JOB_ACCEPTED PoF event, and neither side can move the bar afterward.
Price scales with grade because finish quality costs machine time and QA.
"""

from __future__ import annotations

from enum import Enum

from .models import canonical_json, sha256_hex


class Grade(str, Enum):
    F = "F"   # Functional — fits, works, survives its use; cosmetics irrelevant
    S = "S"   # Standard   — F + workmanlike finish, no gross defects on visible faces
    P = "P"   # Premium    — F + finish quality on marked surfaces ("must look right")


# Fabrication multiplier: premium finish demands more machine time + care + QA.
# Documented assumptions; tune per process later.
GRADE_MULTIPLIER = {Grade.F: 1.00, Grade.S: 1.20, Grade.P: 1.50}

GRADE_NAME = {Grade.F: "Functional", Grade.S: "Standard", Grade.P: "Premium"}

# Minimum node tier that may take work at each grade (matches NODE-AGENT tiers).
GRADE_MIN_TIER = {Grade.F: 0, Grade.S: 1, Grade.P: 2}


def build_checklist(grade: Grade, asset_title: str, material: str) -> list[str]:
    """Concrete acceptance checklist for THIS job. Additive by grade."""
    items = [
        f"dimensional: critical dimensions of '{asset_title}' within declared tolerance",
        f"material: fabricated in {material} as ordered",
        "functional: part performs its declared function / fits its mating parts",
    ]
    if grade in (Grade.S, Grade.P):
        items += [
            "surface: no gross defects (blobs, stringing, layer separation) on visible faces",
            "adhesion: layers/structure bonded, no delamination",
        ]
    if grade == Grade.P:
        items += [
            "surface class: finish quality on marked display faces to reference",
            "color/clarity: matches the agreed reference sample",
            "post-processing: agreed finishing steps completed",
            "second-party QA: independent inspector sign-off (tier >= 2)",
        ]
    return items


def checklist_hash(items: list[str]) -> str:
    return sha256_hex(canonical_json(items))


def materiality(grade: Grade, deviation_covered: bool, functional_impact: bool,
                remedy_cost_cents: int, job_value_cents: int) -> dict:
    """Score a reported deviation by CONSEQUENCE, not existence (ACCEPTANCE §
    'Defect materiality'). Out-of-grade cosmetic deviations weigh zero."""
    if not deviation_covered:
        return {"material": False, "weight": 0.0,
                "reason": "out of scope for the declared grade — no impact"}
    if functional_impact:
        return {"material": True, "weight": 1.0,
                "reason": "functional cascade — heaviest class"}
    weight = min(1.0, remedy_cost_cents / job_value_cents) if job_value_cents else 0.0
    return {"material": weight > 0, "weight": round(weight, 3),
            "reason": f"economic consequence ~{weight*100:.0f}% of job value"}
