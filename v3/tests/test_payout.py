"""Money movement, safely: paying the signed settlement legs is idempotent (no
double-pay on replay/retry), crash-safe (PENDING journaled before the rail call,
re-driven with the same key), fail-closed without credentials, survives restart,
reconciles against the authoritative legs, and is wired into the orchestrator so
a settled order drives payouts end-to-end.

  python -m tests.test_payout
"""

from __future__ import annotations

import os
import sys
import tempfile

from bingo.settlement import Leg, compute_settlement_legs
from bingo.dfm import DfmReport
from bingo.payout import (
    PayoutEngine, MockRail, StripeConnectRail, StablecoinRail,
    payout_key, PAID, PENDING, FAILED,
)

JOB = "job-1"
ORDER = "order-1"


def settlement_legs():
    # a representative signed settlement: node + carrier + royalty + network fee
    return [
        Leg("acct:node:printer-7", 550, "fabrication + material + energy"),
        Leg("acct:carrier-pool", 22, "logistics"),
        Leg("acct:ben", 148, "royalty 8000bps [design]"),
        Leg("acct:network", 40, "network fee (3%)"),
    ]


def main() -> int:
    legs = settlement_legs()
    owed = sum(l.amount_cents for l in legs)

    # -- happy path: every leg paid once; balances + reconciliation tie out ----
    rail = MockRail()
    eng = PayoutEngine(rail)
    recs = eng.pay_legs(legs, order_id=ORDER, job_id=JOB)
    assert all(r.status == PAID for r in recs)
    assert len(rail.sent) == 4
    assert eng.balance("acct:node:printer-7") == 550
    rep = eng.reconcile_job(JOB, legs)
    assert rep["fully_settled"] and rep["consistent"]
    assert rep["owed_cents"] == owed == rep["paid_cents"]
    assert rep["discrepancies"] == []

    # -- idempotency: paying the SAME settlement again pays nothing twice ------
    recs2 = eng.pay_legs(legs, order_id=ORDER, job_id=JOB)
    assert all(r.status == PAID for r in recs2)
    assert len(rail.sent) == 4, "already-PAID legs must not be re-sent to the rail"
    assert eng.balance("acct:ben") == 148            # not 296
    assert eng.reconcile_job(JOB, legs)["fully_settled"]

    # -- outage: one leg fails -> consistent but not fully settled; retry fixes -
    down = MockRail(fail={"acct:network"})
    eng2 = PayoutEngine(down)
    eng2.pay_legs(legs, order_id=ORDER, job_id=JOB)
    r = eng2.reconcile_job(JOB, legs)
    assert not r["fully_settled"]
    assert r["consistent"], "paid+failed must still account for every owed cent"
    assert r["failed_cents"] == 40 and r["paid_cents"] == owed - 40
    # the rail comes back; retry re-drives ONLY the failed leg, same key, no dup
    eng2.rail = MockRail()
    retried = eng2.retry_pending()
    assert len(retried) == 1 and retried[0].account == "acct:network"
    assert retried[0].status == PAID
    assert eng2.rail.sent == [payout_key(JOB, 3, "acct:network", 40)]
    assert eng2.reconcile_job(JOB, legs)["fully_settled"]
    assert eng2.balance("acct:network") == 40        # paid once, not twice

    # -- in-flight (PENDING) is accounted for, not lost -----------------------
    slow = MockRail(pend={"acct:ben"})
    eng3 = PayoutEngine(slow)
    eng3.pay_legs(legs, order_id=ORDER, job_id=JOB)
    r3 = eng3.reconcile_job(JOB, legs)
    assert not r3["fully_settled"] and r3["consistent"]
    assert r3["pending_cents"] == 148

    # -- fail-closed: a real rail with no credentials never reports PAID -------
    assert StripeConnectRail(api_key="").send("k", "acct:x", 100, "usd", "m").status == FAILED
    assert StablecoinRail(credential="").send("k", "acct:x", 100, "usd", "m").status == FAILED
    noeng = PayoutEngine(StripeConnectRail(api_key=""))
    nrecs = noeng.pay_legs(legs, order_id=ORDER, job_id=JOB)
    assert all(r.status == FAILED for r in nrecs)
    assert noeng.balance("acct:node:printer-7") == 0     # nothing moved
    assert not noeng.reconcile_job(JOB, legs)["fully_settled"]

    # -- persistence: journal survives restart and still blocks double-pay -----
    fd, path = tempfile.mkstemp(suffix=".jsonl"); os.close(fd)
    try:
        e_a = PayoutEngine(MockRail(), journal_path=path)
        e_a.pay_legs(legs, order_id=ORDER, job_id=JOB)
        assert e_a.reconcile_job(JOB, legs)["fully_settled"]
        # a fresh engine loads the same journal; re-paying sends NOTHING new
        fresh_rail = MockRail()
        e_b = PayoutEngine(fresh_rail, journal_path=path)
        e_b.pay_legs(legs, order_id=ORDER, job_id=JOB)
        assert fresh_rail.sent == [], "restart must not re-pay already-PAID legs"
        assert e_b.reconcile_job(JOB, legs)["fully_settled"]
    finally:
        os.remove(path)

    # -- reconciliation catches leakage in BOTH directions --------------------
    eng4 = PayoutEngine(MockRail())
    eng4.pay_legs(legs, order_id=ORDER, job_id=JOB)
    # owed a leg we never paid -> "owed but no payout record"
    extra = legs + [Leg("acct:ghost", 999, "phantom")]
    rlow = eng4.reconcile_job(JOB, extra)
    assert not rlow["consistent"]
    assert any("owed but no payout record" in d for d in rlow["discrepancies"])
    # paid a leg not owed -> "payout not owed (unexpected)"
    rhigh = eng4.reconcile_job(JOB, legs[:3])
    assert not rhigh["consistent"]
    assert any("not owed" in d for d in rhigh["discrepancies"])

    # -- keys are deterministic (stable across retries) -----------------------
    assert payout_key(JOB, 0, "acct:a", 100) == payout_key(JOB, 0, "acct:a", 100)
    assert payout_key(JOB, 0, "acct:a", 100) != payout_key(JOB, 1, "acct:a", 100)

    # -- end-to-end: a real settled order drives payouts through the engine ----
    from tests.test_earnings import build as build_designs
    reg, ledger, orch, bracket, clip = build_designs()
    orch.payout_engine = PayoutEngine(MockRail())
    dfm = DfmReport(True, [], 0, (0, 0, 0), 0.0, 6.0, 0.2)
    o, dfm = orch.place_order(buyer="acct:buyer", asset_id=bracket.asset_id, qty=3,
                              material="PLA", buyer_lat=39.7, buyer_lon=-105.0,
                              dfm_override=dfm)
    jobs = orch.execute_order(o, dfm)
    assert jobs, "expected at least one settled job"
    eng5 = orch.payout_engine
    for job in jobs:                                    # every settled job fully paid
        rep_j = eng5.reconcile_job(job.job_id, compute_settlement_legs(job))
        assert rep_j["fully_settled"], rep_j
    # orchestrator-level idempotency: re-driving the same jobs pays nothing twice
    sent_before = len(eng5.rail.sent)
    for job in jobs:
        eng5.pay_legs(compute_settlement_legs(job), order_id=o.order_id, job_id=job.job_id)
    assert len(eng5.rail.sent) == sent_before, "re-settling must not re-pay"

    print("OK - settlement payouts move money safely: idempotent (a replay/retry "
          "never double-pays), crash-safe (PENDING journaled before the rail call, "
          "re-driven with the same key), fail-closed without credentials, "
          "persistent across restart, and reconciled against the signed legs "
          "(leakage in either direction is caught); and wired into the "
          "orchestrator so a settled order drives payouts end-to-end, idempotently.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
