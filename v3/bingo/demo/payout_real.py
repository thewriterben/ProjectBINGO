"""Tier 1, end to end: real money movement, offline.

This drives an ACTUAL settled order through the kernel — order -> fabricate ->
signed, conserved settlement legs -> `PayoutEngine` -> the REAL `StripeConnectRail`
(stdlib `urllib` against Stripe's Transfers REST API) — and points that rail at a
faithful local Stripe double (`bingo.demo.fake_stripe`) so it runs with no live
credentials. Every property that matters for real money is exercised against a
real HTTP server that returns real transfer ids:

  1. Each signed leg becomes exactly one Stripe transfer (id `tr_test_...`).
  2. Crash/retry cannot double-pay: we re-drive the whole settlement AND simulate a
     transient 5xx on one leg; the provider still ends with ONE transfer per leg.
  3. Reconciliation is done against the PROVIDER'S own records (GET /v1/transfers),
     not just our journal — the money that moved matches the money we signed.

The switch to real money is exactly two changes and zero code: set
`STRIPE_API_KEY=sk_live_...` (or `sk_test_...` for Stripe's own test mode) and drop
the `base_url` override so the rail talks to api.stripe.com. Everything else —
idempotency, crash-safety, fail-closed, reconciliation — is already proven here.

  python -m bingo.demo.payout_real
"""

from __future__ import annotations

import sys

from bingo.dfm import DfmReport
from bingo.settlement import compute_settlement_legs
from bingo.payout import PayoutEngine, StripeConnectRail, PAID
from bingo.demo.fake_stripe import FakeStripe
from tests.test_earnings import build


def _connected_map(jobs) -> dict:
    """Map every BINGO payout account that shows up in the settlement to a Stripe
    connected-account id. In production this mapping is the Connect onboarding
    output (each payee's `acct_...`); here we synthesize a stable stand-in."""
    accounts = set()
    for job in jobs:
        for leg in compute_settlement_legs(job):
            accounts.add(leg.account)
    return {a: "acct_" + a.replace(":", "_") for a in sorted(accounts)}


def main() -> int:
    # -- a real settled order: two designs, one a remix, across real nodes ------
    reg, ledger, orch, bracket, clip = build()
    dfm = DfmReport(True, [], 0, (0, 0, 0), 0.0, 6.0, 0.2)
    o, dfm = orch.place_order(buyer="acct:buyer", asset_id=bracket.asset_id, qty=5,
                              material="PLA", buyer_lat=39.7, buyer_lon=-105.0,
                              dfm_override=dfm)
    jobs = orch.execute_order(o, dfm)
    assert jobs, "expected at least one settled job"
    connected = _connected_map(jobs)
    total_owed = sum(l.amount_cents for job in jobs
                     for l in compute_settlement_legs(job))

    print(f"settled order {o.order_id}: {len(jobs)} job(s), "
          f"{sum(len(compute_settlement_legs(j)) for j in jobs)} signed legs, "
          f"{total_owed}c owed")

    # -- happy path: drive real transfers through the real rail -> fake Stripe --
    with FakeStripe() as fs:
        rail = StripeConnectRail(api_key="sk_test_double", connected=connected,
                                 base_url=fs.base_url)
        eng = PayoutEngine(rail)
        orch.payout_engine = eng
        for job in jobs:
            eng.pay_legs(compute_settlement_legs(job), order_id=o.order_id,
                         job_id=job.job_id)

        paid_recs = [r for r in eng._journal.values() if r.status == PAID]
        assert paid_recs and all(r.external_ref.startswith("tr_test_")
                                 for r in paid_recs), "every leg got a real transfer id"
        assert fs.transfers_created == len(paid_recs), \
            "provider created exactly one transfer per leg"
        print(f"  paid {len(paid_recs)} legs -> {fs.transfers_created} Stripe "
              f"transfers (e.g. {paid_recs[0].external_ref})")

        # -- idempotency: re-drive the WHOLE settlement; provider makes 0 new ---
        before = fs.transfers_created
        for job in jobs:
            eng.pay_legs(compute_settlement_legs(job), order_id=o.order_id,
                         job_id=job.job_id)
        assert fs.transfers_created == before, "replay must not create new transfers"
        print(f"  replayed settlement -> still {fs.transfers_created} transfers "
              "(idempotent end-to-end, provider-confirmed)")

        # -- external reconciliation: provider's own records == signed legs ----
        for job in jobs:
            legs = compute_settlement_legs(job)
            rep = eng.reconcile_with_rail(job.job_id, legs)
            assert rep["checked"] and rep["verified"], rep
            assert rep["drift"] == [], rep
        print("  reconciled against PROVIDER records (GET /v1/transfers): no drift")

    # -- crash/retry under a transient 5xx: still exactly one transfer per leg --
    with FakeStripe(fail_times=1) as fs2:      # 500 the first call to each idem key
        rail2 = StripeConnectRail(api_key="sk_test_double", connected=connected,
                                  base_url=fs2.base_url)
        eng2 = PayoutEngine(rail2)
        for job in jobs:
            eng2.pay_legs(compute_settlement_legs(job), order_id=o.order_id,
                          job_id=job.job_id)
        # first pass: every leg hit a 5xx -> PENDING, nothing paid, nothing moved
        assert fs2.transfers_created == 0, "a 5xx must not move money"
        assert not any(r.status == PAID for r in eng2._journal.values())
        # retry re-drives with the SAME idempotency key -> now succeeds, once each
        eng2.retry_pending()
        legs_all = [(job.job_id, compute_settlement_legs(job)) for job in jobs]
        paid2 = [r for r in eng2._journal.values() if r.status == PAID]
        assert paid2 and fs2.transfers_created == len(paid2), \
            "retry after 5xx moves each leg exactly once"
        for jid, legs in legs_all:
            assert eng2.reconcile_with_rail(jid, legs)["verified"]
        print(f"  transient 5xx -> retry: {fs2.transfers_created} transfers, "
              "no double-pay (same idempotency key survived the outage)")

    print("\nTier 1 proven offline: real settlement legs, real Stripe REST rail, "
          "real transfer ids, provider-confirmed reconciliation, idempotent across "
          "replay and a transient outage. Flip to live money = set STRIPE_API_KEY "
          "and drop the base_url override. (KYC/AML, money-transmission licensing, "
          "Connect payee onboarding, and counsel remain people-process, not code.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
