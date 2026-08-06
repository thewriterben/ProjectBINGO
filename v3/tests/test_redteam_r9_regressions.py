"""Regressions for the round-9 red-team break (workflow wf_5c177baa-fb5).
Round 9: 6 of 7 surfaces found NOTHING; one MEDIUM remained. verify_passport
checked only the by-ACCOUNT aggregate of SALE legs, so offsetting +/- legs for the
same account (e.g. rancher +$10.39 / -$9.99) conserved on net and matched the
split, yet rendered a VERIFIED certificate showing a payee receiving far more than
the sale price (and would over-pay any consumer that pays positive legs without
netting). The sibling token verifier already rejected negative legs; passport did
not. Fix: reject any negative per-leg payout. Assertion FAILS on round-8 code and
PASSES now.

  python -m tests.test_redteam_r9_regressions
"""

from __future__ import annotations

import sys

from provenance.passport import Actor, CutPassport, verify_passport


def test_passport_rejects_negative_legs():
    op = Actor.create("op", "Op", "operation", "acct:op")
    pp = CutPassport(subject={"product": "A5", "lot": "L", "weight_lb": 1})
    pp.attest(op, "LINEAGE", {"tajima_pct": 96})
    split = {"payees": [{"account": "acct:rancher", "bps": 4000},
                        {"account": "acct:grocer", "bps": 6000}]}
    # legs net to rancher 40c / grocer 60c (matches the 40/60 split and totals the
    # $1.00 price), but include a +$10.39 and a -$9.99 leg for the rancher
    legs = [{"account": "acct:rancher", "bps": 4000, "cents": 1039},
            {"account": "acct:rancher", "bps": 0, "cents": -999},
            {"account": "acct:grocer", "bps": 6000, "cents": 60}]
    pp.attest(op, "SALE", {"buyer": "b", "unit": "1", "price_cents": 100,
                           "split": split, "legs": legs})
    pp.settlement = legs
    ok, why = verify_passport(pp.to_dict())
    assert not ok and "negative payout leg" in why[-1], \
        "offsetting negative settlement legs must be rejected (money not routed as shown)"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK — all {len(tests)} round-9 regression group passes: verify_passport "
          "now rejects negative per-leg payouts (parity with the token verifier), so "
          "offsetting +/- legs can't render a VERIFIED certificate that shows a payee "
          "receiving more than the sale price.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
