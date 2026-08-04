"""Machine RWA / node financing: a signed offering + cap-table, capital raised,
earnings streamed pro-rata to shareholders and capped at repayment (then 100%
back to the operator), single-use earning events, PoF-verified revenue as the
only input, and full independent replay (tamper/forge/reorder/oversubscription/
falsified-distribution all caught). Run:

  python -m tests.test_machine_rwa
"""

from __future__ import annotations

import copy
import json
import sys

from bingo.models import canonical_json, sha256_hex
from provenance.passport import Actor
from provenance.machine_rwa import (
    MachineShare, MachineRwaError, _distribute, verify_machine_share,
    verified_machine_revenue,
)


def build():
    op = Actor.create("op", "Operator", "operator", "acct:node:printer-7")
    alice = Actor.create("alice", "Alice", "investor", "acct:alice")
    bob = Actor.create("bob", "Bob", "investor", "acct:bob")
    ms = MachineShare(machine_id="printer-7", total_shares=100, price_cents=1000,
                      investor_share_bps=6000, repayment_cap_cents=120_000,
                      operator=op, ts="t0")
    ms.buy(alice, 60, ts="t1")   # $600
    ms.buy(bob, 40, ts="t2")     # $400  → fully subscribed, $1000 raised
    return ms, op, alice, bob


def main() -> int:
    ms, op, alice, bob = build()

    # offering + cap table verify from the document alone
    ok, notes = verify_machine_share(ms.to_dict())
    assert ok, notes
    assert ms.capital_raised() == 100_000          # $1,000 raised
    assert ms.sold_shares() == 100
    assert ms.holdings() == {"acct:alice": 60, "acct:bob": 40}

    # oversubscription is refused
    carol = Actor.create("carol", "Carol", "investor", "acct:carol")
    try:
        ms.buy(carol, 1, ts="t3")
        assert False, "oversubscription must be rejected"
    except MachineRwaError as e:
        assert "oversubscription" in str(e)

    # a non-operator cannot record earnings
    try:
        ms.earn(alice, 50_000, "evt-x", ts="t4")
        assert False, "only the operator may record earnings"
    except MachineRwaError:
        pass

    # ── earnings stream pro-rata, conserve, and cap at repayment ─────────────
    # event 1: $1,000 revenue → 60% ($600) to investors (alice 360 / bob 240),
    # operator keeps $400.
    d1 = ms.earn(op, 100_000, "job-1", ts="t5")
    assert d1["to_investors"] == 60_000 and d1["to_operator"] == 40_000
    assert {l["account"]: l["cents"] for l in d1["legs"]} == {"acct:alice": 36_000, "acct:bob": 24_000}
    assert ms.cumulative_paid() == 60_000

    # duplicate event_ref rejected (revenue can't be double-distributed)
    try:
        ms.earn(op, 100_000, "job-1", ts="t6")
        assert False, "replayed earning event must be rejected"
    except MachineRwaError as e:
        assert "double count" in str(e)

    # event 2: another $1,000 → investors hit the $1,200 cap exactly.
    d2 = ms.earn(op, 100_000, "job-2", ts="t7")
    assert d2["to_investors"] == 60_000
    assert ms.cumulative_paid() == 120_000 and ms.fully_repaid()

    # event 3: cap reached → investors get nothing, operator keeps 100%.
    d3 = ms.earn(op, 100_000, "job-3", ts="t8")
    assert d3["to_investors"] == 0 and d3["to_operator"] == 100_000
    assert d3["legs"] == []

    # total to investors == the cap == 1.2x the raise; per-investor 60/40 split
    ie = ms.investor_earnings()
    assert ie["acct:alice"] == 72_000 and ie["acct:bob"] == 48_000
    assert sum(ie.values()) == 120_000 == ms.repayment_cap_cents

    # the whole thing still verifies, and round-trips as plain JSON
    ok, notes = verify_machine_share(json.loads(json.dumps(ms.to_dict())))
    assert ok, notes

    # ── residue: an uneven pool still conserves, remainder → largest holder ───
    legs, to_inv, to_op = _distribute({"acct:alice": 60, "acct:bob": 40},
                                      investor_share_bps=6000, revenue_cents=100_001,
                                      cumulative_paid=0, cap_cents=10_000_000)
    assert to_inv + to_op == 100_001
    pool = (100_001 * 6000) // 10_000          # 60000
    by = {l["account"]: l["cents"] for l in legs}
    assert by["acct:alice"] + by["acct:bob"] == pool
    # alice (larger holder) carries any residue
    assert by["acct:alice"] >= (pool * 60) // 100

    # ── tamper / forge / reorder all caught ──────────────────────────────────
    d = ms.to_dict()
    t = copy.deepcopy(d)
    t["events"][1]["data"]["shares"] = 999            # inflate a purchase
    assert not verify_machine_share(t)[0], "tampered shares must be caught"

    f = copy.deepcopy(d)
    imposter = Actor.create("imp", "Imp", "investor", "acct:imp")
    f["holders"]["alice"]["pubkey"] = imposter.public()["pubkey"]
    assert not verify_machine_share(f)[0], "forged signer key must be caught"

    r = copy.deepcopy(d)
    r["events"][1], r["events"][2] = r["events"][2], r["events"][1]
    assert not verify_machine_share(r)[0], "reordered events must be caught"

    # falsified distribution: overpay alice on the LAST event and re-sign it, so
    # the signature is valid but the numbers lie — caught by re-derivation.
    liar = copy.deepcopy(d)
    ev = liar["events"][-1]           # the last EARN (job-3, all to operator)
    ev["data"]["legs"] = [{"account": "acct:alice", "cents": 5_000}]
    ev["data"]["to_investors"] = 5_000
    ev["data"]["to_operator"] = 95_000
    ev["data"]["cumulative_after"] = 125_000
    body = canonical_json({k: ev[k] for k in
                           ("seq", "ts", "type", "signer", "data", "prev_hash")})
    ev["sig"] = op.sign(body)                       # a genuine operator signature…
    ev["hash"] = sha256_hex(body + ev["sig"].encode())
    ok, notes = verify_machine_share(liar)
    assert not ok, "a signed-but-false distribution must be caught by recomputation"

    # ── the PoF tie: only verified machine revenue funds the instrument ───────
    from tests.test_earnings import build as build_designs, order
    reg, ledger, orch, bracket, clip = build_designs()
    order(orch, bracket.asset_id, 5, 39.7, -105.0)       # real settled jobs
    # find a node that actually earned in the settled ledger and read its
    # PoF-verified revenue — the only number allowed to fund an instrument.
    any_node = None
    for e in ledger.journal:
        if getattr(e, "kind", None) == "JOB_SETTLEMENT":
            for leg in e.legs:
                if leg.account.startswith("acct:node:"):
                    any_node = leg.account.split("acct:node:", 1)[1]
    assert any_node, "expected at least one settled node payout in the ledger"
    rev = verified_machine_revenue(ledger, any_node)
    assert rev > 0, "verified machine revenue must be real (ledger-derived)"
    # a node with no settled jobs earns nothing — you can't distribute phantom revenue
    assert verified_machine_revenue(ledger, "ghost-node") == 0

    print("OK — machine-revenue-share offering + cap table signs & verifies "
          "offline; capital raised; earnings stream pro-rata to shareholders and "
          "cap at 1.2x repayment (then 100% back to the operator); duplicate "
          "earnings, non-operator earnings & oversubscription rejected; tamper, "
          "forged key, reorder & a signed-but-false distribution all caught by "
          "replay; and only PoF-verified ledger revenue funds it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
