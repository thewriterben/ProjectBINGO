"""One unified 'who got paid' view: a 3D-print designer and the Wagyu rancher
in the same list, each with the right source breakdown. Run:

  python -m tests.test_network_earnings
"""

from __future__ import annotations

import sys

from bingo.models import SplitPayee
from bingo.training import Contribution, RoyaltyMeter, Trainer, build_corpus
from provenance.demo import build as build_passport
from provenance.passport import Actor
from provenance.register import register_rwa
from provenance.token import AssetToken
from provenance.earnings_rollup import network_earnings, account_earnings
from tests.test_earnings import build as build_designs, order


def main() -> int:
    # a design fabrication settles royalties into the ledger (ben 80 / alex 20)
    reg, ledger, orch, bracket, clip = build_designs()
    order(orch, bracket.asset_id, 10, 39.7, -105.0)

    # the A5 cut is registered as an RWA asset in the SAME network
    passport = build_passport()
    asset = register_rwa(reg, passport, creator="acct:op:dgd-wagyu")
    pp = passport.to_dict()
    vsplit = next(e["data"]["split"]["payees"] for e in pp["events"] if e["type"] == "SALE")

    # a token on that cut, with a primary sale routing proceeds to the split
    op = Actor.create("op", "Op", "operation", "acct:op:dgd-wagyu")
    chef = Actor.create("chef", "Chef", "buyer", "acct:chef")
    tok = AssetToken(backing_asset_id=asset.asset_id, passport_head=pp["chain_head"],
                     unit="1/100", total_supply=100, issuer=op, value_split=vsplit, ts="t0")
    tok.sell(op, chef.account, 40, price_cents=4000, ts="t1")
    tokens = {tok.token_id: tok.to_dict()}

    # the network's design agent was trained on ben's design library AND a print
    # profile from rosa; a month of usage accrues a $10 pool that settles to them.
    trainer = Trainer.create("net-trainer", "acct:network")
    corpus = build_corpus(trainer, "design-agent-v1", [
        Contribution("asset-lib", 600, [SplitPayee("acct:ben", 10_000)]),
        Contribution("asset-profile", 400, [SplitPayee("acct:rosa", 10_000)]),
    ], ts="t0")
    meter = RoyaltyMeter()
    meter.record_usage("design-agent-v1", "use-1", fee_cents=20_000, training_share_bps=500)  # +1000
    training_legs = meter.settle(corpus)  # ben 600, rosa 400

    rows = network_earnings(ledger, reg, tokens, training_legs=training_legs)
    by = {r["account"]: r for r in rows}

    # a 3D-print designer earned design royalties AND training royalties (his
    # library taught the agent) — two streams, one row, nothing from the cow.
    assert by["acct:ben"]["sources"]["design_royalties"] == 320, by["acct:ben"]
    assert by["acct:ben"]["sources"]["training_royalties"] == 600
    assert by["acct:ben"]["sources"]["rwa_sale"] == 0
    assert by["acct:ben"]["total_cents"] == 320 + 600

    # a print-profile author appears in the SAME list — a fourth kind of
    # participant, earning only because an AI learned from her work.
    assert by["acct:rosa"]["sources"]["training_royalties"] == 400
    assert by["acct:rosa"]["total_cents"] == 400

    # the rancher earned from BOTH the physical sale and the token sales — one row
    r = by["acct:rancher:sadu"]
    assert r["sources"]["rwa_sale"] == 5850 * 2200 // 10000       # 1287
    assert r["sources"]["token_sales"] == 4000 * 2200 // 10000    # 880
    assert r["total_cents"] == r["sources"]["rwa_sale"] + r["sources"]["token_sales"]

    # the whole point: a designer and a rancher in ONE sorted picture
    assert "acct:ben" in by and "acct:rancher:sadu" in by
    assert all(rows[i]["total_cents"] >= rows[i + 1]["total_cents"]
               for i in range(len(rows) - 1))

    # per-account accessor agrees with the network view (both with and without
    # the training stream)
    assert account_earnings(ledger, reg, tokens, "acct:rancher:sadu")["total_cents"] \
        == r["total_cents"]
    assert account_earnings(ledger, reg, tokens, "acct:ben", training_legs)["total_cents"] \
        == by["acct:ben"]["total_cents"]

    print(f"OK — one network earnings view, {len(rows)} accounts paid across FOUR "
          f"streams. designer acct:ben ${by['acct:ben']['total_cents']/100:.2f} "
          f"(${by['acct:ben']['sources']['design_royalties']/100:.2f} design + "
          f"${by['acct:ben']['sources']['training_royalties']/100:.2f} training); "
          f"rancher acct:rancher:sadu ${r['total_cents']/100:.2f} "
          f"(${r['sources']['rwa_sale']/100:.2f} physical + "
          f"${r['sources']['token_sales']/100:.2f} token); print-profile author "
          f"acct:rosa ${by['acct:rosa']['total_cents']/100:.2f} (training) — all in one list.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
