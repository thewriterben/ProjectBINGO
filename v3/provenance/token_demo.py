"""Tokenize the A5 lot end to end, backed by its verified passport.

    python -m provenance.token_demo

Issues 100 shares of one lot, distributes and transfers them, redeems some when
the claim is exercised, and verifies the whole ownership ledger — including that
it's pinned to the exact provenance passport the RWA asset is content-addressed
to. Writes out/token/<token_id>.json. Names are illustrative; the crypto is real.
"""

from __future__ import annotations

import json
import os

from bingo.registry import AssetRegistry
from .demo import build
from .passport import Actor
from .register import register_rwa
from .token import AssetToken, verify_token

OUT = os.path.join(os.path.dirname(__file__), "..", "out", "token")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)

    # the backing: the A5 cut as a provenance-verified, content-addressed asset
    reg = AssetRegistry()
    passport = build()
    asset = register_rwa(reg, passport, creator="acct:op:dgd-wagyu")
    pp = passport.to_dict()

    # the holders (real keys, placeholder identities)
    op = Actor.create("dgd-wagyu", "DGD Wagyu Co.", "operation", "acct:op:dgd-wagyu")
    chef = Actor.create("river-grill", "River Grill (Ketchum)", "buyer", "acct:buyer:river-grill")
    club = Actor.create("wagyu-club", "Wagyu Club member", "holder", "acct:holder:club")

    # issue 100 shares of this one lot, pinned to its provenance
    tok = AssetToken(backing_asset_id=asset.asset_id, passport_head=pp["chain_head"],
                     unit=f'1/100 of lot {pp["subject"]["lot"]}', total_supply=100,
                     issuer=op, ts="2026-07-31T18:00:00Z")

    # primary distribution + a secondary transfer + a redemption
    tok.transfer(op, chef.account, 40, ts="2026-07-31T18:05:00Z")
    tok.transfer(op, club.account, 25, ts="2026-07-31T18:06:00Z")
    tok.transfer(club, chef.account, 10, ts="2026-08-01T09:00:00Z")   # secondary market
    tok.redeem(chef, 15, note="15 portions plated & served", ts="2026-08-02T20:00:00Z")

    td = tok.to_dict()
    path = os.path.join(OUT, f"{tok.token_id}.json")
    with open(path, "w") as f:
        json.dump(td, f, indent=2)

    print(f"Token {tok.token_id[:16]}…  ({td['unit']})")
    print(f"backed by RWA asset {asset.asset_id[:16]}…  → passport {pp['chain_head'][:16]}…")
    print("\nownership ledger:")
    for e in td["events"]:
        who = td["holders"][e["signer"]]["name"]
        d = e["data"]
        if e["type"] == "ISSUE":
            detail = f'mint {d["shares"]} → {d["to"]}'
        elif e["type"] == "TRANSFER":
            detail = f'{d["shares"]}  {d["from"]} → {d["to"]}'
        else:
            detail = f'redeem {d["shares"]} ({d["note"]})'
        print(f"  {e['seq']}. {e['type']:<9} {detail}  [{who}]")

    print("\nbalances:")
    for acct, n in sorted(td["balances"].items()):
        print(f"  {acct:<24} {n:>3} shares")
    print(f"  {'(redeemed/retired)':<24} {td['retired']:>3} shares")
    print(f"  circulating: {td['circulating']}/{td['total_supply']}")

    ok, notes = verify_token(td, backing_passport=pp)
    print(f"\nverify_token (with backing) → {'OK' if ok else 'FAIL'}")
    for n in notes:
        print("  ·", n)
    print(f"\nwrote {os.path.relpath(path)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
