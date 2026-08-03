"""One unified 'who got paid' view: a 3D-print designer and the Wagyu rancher
in the same list, each with the right source breakdown. Run:

  python -m tests.test_network_earnings
"""

from __future__ import annotations

import sys

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

    rows = network_earnings(ledger, reg, tokens)
    by = {r["account"]: r for r in rows}

    # a 3D-print designer earned design royalties (and nothing from the cow)
    assert by["acct:ben"]["sources"]["design_royalties"] == 320, by["acct:ben"]
    assert by["acct:ben"]["sources"]["rwa_sale"] == 0

    # the rancher earned from BOTH the physical sale and the token sales — one row
    r = by["acct:rancher:sadu"]
    assert r["sources"]["rwa_sale"] == 5850 * 2200 // 10000       # 1287
    assert r["sources"]["token_sales"] == 4000 * 2200 // 10000    # 880
    assert r["total_cents"] == r["sources"]["rwa_sale"] + r["sources"]["token_sales"]

    # the whole point: a designer and a rancher in ONE sorted picture
    assert "acct:ben" in by and "acct:rancher:sadu" in by
    assert all(rows[i]["total_cents"] >= rows[i + 1]["total_cents"]
               for i in range(len(rows) - 1))

    # per-account accessor agrees with the network view
    assert account_earnings(ledger, reg, tokens, "acct:rancher:sadu")["total_cents"] \
        == r["total_cents"]

    print(f"OK — one network earnings view, {len(rows)} accounts paid. "
          f"designer acct:ben ${by['acct:ben']['total_cents']/100:.2f} (design royalties); "
          f"rancher acct:rancher:sadu ${r['total_cents']/100:.2f} "
          f"(${r['sources']['rwa_sale']/100:.2f} physical + "
          f"${r['sources']['token_sales']/100:.2f} token sales) — side by side.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
