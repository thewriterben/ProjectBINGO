"""Raise-readiness: the term sheet renders from the signed offering, and
"ready to raise?" is a fail-closed function - NOT ready without every compliance
gate AND a real verified-revenue basis; disclosure inputs refuse a phantom basis.

  python -m tests.test_raise_readiness
"""

from __future__ import annotations

import copy
import sys

from tests.test_machine_rwa import build
from provenance.raise_readiness import (
    RaiseReadiness, readiness_report, term_sheet, disclosure_inputs,
    REQUIRED_GATES,
)


def _ready_ctx() -> RaiseReadiness:
    return RaiseReadiness(
        counsel_opinion=True, exemption="reg_cf",
        funding_portal="Example Portal LLC (FINRA-registered)",
        transfer_agent="Example Transfer Agent Inc.",
        kyc_aml=True, escrow=True, blue_sky=True, marketing_reviewed=True,
        required_revenue_months=3,
    )


def main() -> int:
    ms = build()[0]
    doc = ms.to_dict()
    good_periods = [40_000, 55_000, 60_000]     # 3 PoF-verified periods

    # -- term sheet renders from the signed offering, pinned to its hash -------
    ts_none = term_sheet(doc)
    assert "NOT AN OFFER" in ts_none
    assert doc["events"][0]["hash"][:16] in ts_none          # pinned to OPEN event
    assert "NONE YET" in ts_none                              # no revenue basis shown
    ts_rev = term_sheet(doc, good_periods)
    assert "Revenue basis" in ts_rev and "3 PoF-verified" in ts_rev
    assert "not guaranteed" in ts_rev.lower()

    # -- fail-closed: empty context + no revenue is NOT ready, and says why ----
    empty = readiness_report(doc, [], RaiseReadiness())
    assert empty["is_ready"] is False
    for gate in REQUIRED_GATES:
        assert any(gate in b for b in empty["blockers"]), f"{gate} not flagged"
    assert any("verified-revenue" in b for b in empty["blockers"])

    # -- fully satisfied + real revenue basis => ready ------------------------
    full = readiness_report(doc, good_periods, _ready_ctx())
    assert full["is_ready"] is True, full["blockers"]
    assert full["blockers"] == []
    assert full["revenue_basis_cents"] == sum(good_periods)
    assert full["revenue_periods"] == 3
    assert full["terms"]["max_return_multiple"] > 1.0        # 1.2x in the fixture

    # -- remove ONE gate -> not ready, with exactly that blocker --------------
    ctx = _ready_ctx(); ctx.escrow = False
    r = readiness_report(doc, good_periods, ctx)
    assert r["is_ready"] is False
    assert any("escrow" in b for b in r["blockers"])
    assert not any("counsel_opinion" in b for b in r["blockers"])  # others still ok

    # -- not enough real revenue -> not ready (no underwriting phantom revenue) -
    thin = readiness_report(doc, [40_000, 0, 50_000], _ready_ctx())  # only 2 positive
    assert thin["is_ready"] is False
    assert any("verified-revenue" in b for b in thin["blockers"])

    # -- an unknown exemption is rejected -------------------------------------
    ctx2 = _ready_ctx(); ctx2.exemption = "reg_zz"
    r2 = readiness_report(doc, good_periods, ctx2)
    assert r2["is_ready"] is False
    assert any("unknown exemption" in b for b in r2["blockers"])

    # -- an offering that doesn't verify can never be ready --------------------
    bad = copy.deepcopy(doc)
    bad["events"][1]["data"]["shares"] = 999_999      # tamper a BUY
    rb = readiness_report(bad, good_periods, _ready_ctx())
    assert rb["is_ready"] is False
    assert any("offering does not verify" in b for b in rb["blockers"])

    # -- disclosure inputs: refuse a phantom basis, assemble a real one -------
    try:
        disclosure_inputs(doc, [], _ready_ctx())
        assert False, "disclosure_inputs must refuse with no verified revenue"
    except ValueError:
        pass
    di = disclosure_inputs(doc, good_periods, _ready_ctx())
    assert di["exemption_sought"] == "reg_cf"
    assert di["financial_basis"]["total_verified_revenue_cents"] == sum(good_periods)
    assert di["risk_factors"] and di["still_required_from_counsel"]
    assert "not a filing" in di["DISCLAIMER"].lower()

    print("OK - term sheet renders from the signed offering (pinned to its OPEN "
          "hash, NOT-AN-OFFER, revenue shown only when real); readiness is "
          "fail-closed across all "
          f"{len(REQUIRED_GATES)} compliance gates + a real verified-revenue "
          "basis; one missing gate or thin revenue flips it to NOT READY with the "
          "specific blocker; a non-verifying offering can never be ready; and "
          "disclosure inputs refuse a phantom basis.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
