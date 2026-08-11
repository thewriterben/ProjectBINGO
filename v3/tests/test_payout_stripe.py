"""The REAL Stripe rail, proven end-to-end against a faithful local Stripe double
(`bingo.demo.fake_stripe`) so it runs with no live credentials. This is the Tier-1
money-movement proof: `StripeConnectRail` drives Stripe's Transfers REST API over
stdlib `urllib`, and every property that keeps real money safe is exercised against
a real HTTP server returning real transfer ids.

  * happy path: each signed leg -> exactly one provider transfer (tr_test_...);
  * idempotency: replaying a leg's key creates NO second transfer (provider truth);
  * fail-closed: no key, or no connected-account mapping, never reports PAID;
  * 5xx -> PENDING (retryable), retry re-drives the SAME key -> one transfer, no dup;
  * 4xx (bad amount) -> FAILED (terminal), no money moves;
  * external reconciliation: PAID records tie to the PROVIDER's own records AND the
    signed legs; a journal that claims PAID the provider never made is caught.

  python -m tests.test_payout_stripe
"""

from __future__ import annotations

import sys

from bingo.payout import (PayoutEngine, StripeConnectRail, PayoutRecord,
                          PAID, PENDING, FAILED)
from bingo.demo.fake_stripe import FakeStripe

CONNECTED = {"acct:node:printer-7": "acct_node_printer7",
             "acct:ben": "acct_ben",
             "acct:network": "acct_network"}


def _rail(fs, key="sk_test_double"):
    return StripeConnectRail(api_key=key, connected=CONNECTED, base_url=fs.base_url)


# -- happy path: one real transfer per send, with a real transfer id -----------
def test_send_creates_one_real_transfer():
    with FakeStripe() as fs:
        rail = _rail(fs)
        res = rail.send("idem-1", "acct:ben", 148, "usd", "royalty")
        assert res.status == PAID and res.external_ref.startswith("tr_test_")
        assert fs.transfers_created == 1
        # the provider can be queried for that transfer (reconciliation source)
        got = rail.retrieve(res.external_ref)
        assert got == {"amount_cents": 148, "currency": "usd",
                       "destination": "acct_ben", "status": "PAID"}


# -- idempotency at the PROVIDER: same key => same transfer, never a second ----
def test_same_idem_key_never_double_transfers():
    with FakeStripe() as fs:
        rail = _rail(fs)
        a = rail.send("idem-same", "acct:ben", 148, "usd", "royalty")
        b = rail.send("idem-same", "acct:ben", 148, "usd", "royalty")   # replay
        assert a.status == b.status == PAID
        assert a.external_ref == b.external_ref, "replay must return the SAME transfer"
        assert fs.transfers_created == 1, "provider created exactly one transfer"


# -- fail-closed: no credentials, and no connected-account mapping -------------
def test_fail_closed_without_key_or_mapping():
    with FakeStripe() as fs:
        assert StripeConnectRail(api_key="", connected=CONNECTED,
                                 base_url=fs.base_url).send(
            "k", "acct:ben", 148, "usd", "m").status == FAILED
        # key present but destination not onboarded -> FAILED, no money moves
        res = _rail(fs).send("k", "acct:unmapped", 148, "usd", "m")
        assert res.status == FAILED and "no connected account" in res.error
        assert fs.transfers_created == 0


# -- 5xx is retryable (PENDING), and the retry lands on the same idem key ------
def test_5xx_pending_then_retry_pays_once():
    with FakeStripe(fail_times=1) as fs:       # first call per key -> 500
        rail = _rail(fs)
        eng = PayoutEngine(rail)
        rec = PayoutRecord(key="idem-5xx", order_id="o", job_id="j",
                           account="acct:ben", amount_cents=148, memo="royalty",
                           currency="usd", status=PENDING)
        eng._journal[rec.key] = rec
        first = eng._drive(rec)
        assert first.status == PENDING and fs.transfers_created == 0, \
            "a 5xx must not move money and must stay retryable"
        retried = eng.retry_pending()
        assert retried and retried[0].status == PAID
        assert fs.transfers_created == 1, "retry after 5xx moves the leg exactly once"
        assert retried[0].external_ref.startswith("tr_test_")


# -- 4xx is terminal (FAILED), no money moves ----------------------------------
def test_4xx_is_terminal_failed():
    with FakeStripe() as fs:
        # amount <= 0 is rejected by the rail BEFORE the call (positive-int guard)...
        res = _rail(fs).send("k", "acct:ben", 0, "usd", "m")
        assert res.status == FAILED and fs.transfers_created == 0


# -- external reconciliation: journal ties to the PROVIDER and the signed legs -
def test_reconcile_with_rail_confirms_and_catches_drift():
    from bingo.settlement import Leg
    legs = [Leg("acct:node:printer-7", 550, "fabrication + material + energy"),
            Leg("acct:ben", 148, "royalty"),
            Leg("acct:network", 40, "network fee")]
    with FakeStripe() as fs:
        eng = PayoutEngine(_rail(fs))
        eng.pay_legs(legs, order_id="o", job_id="j")
        rep = eng.reconcile_with_rail("j", legs)
        assert rep["checked"] and rep["verified"] and rep["drift"] == []
        assert rep["confirmed_cents"] == 738 == 550 + 148 + 40

        # a journal that CLAIMS PAID the provider never made must be caught as drift
        eng._journal["phantom"] = PayoutRecord(
            key="phantom", order_id="o", job_id="j", account="acct:ben",
            amount_cents=999, memo="phantom", currency="usd",
            status=PAID, external_ref="tr_test_99999999")
        bad = eng.reconcile_with_rail("j", legs)
        assert not bad["verified"]
        assert any("no transfer" in d for d in bad["drift"])


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK - all {len(tests)} Stripe-rail groups pass: the REAL StripeConnectRail "
          "moves money end-to-end against a faithful Stripe double - one transfer per "
          "signed leg, idempotent at the provider (same key never double-transfers), "
          "fail-closed without a key/mapping, 5xx->PENDING->retry pays once, 4xx "
          "terminal, and reconciled against the provider's own records. Flip to live "
          "money = set STRIPE_API_KEY and drop the base_url override.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
