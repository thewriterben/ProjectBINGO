"""A physical real-world good is a first-class BINGO asset: registered from its
passport, content-addressed to its provenance, verifiable through the same
marketplace/API surface as a design. Run:

  python -m tests.test_rwa_asset
"""

from __future__ import annotations

import sys

from bingo.registry import AssetRegistry
from provenance.demo import build
from provenance.register import register_rwa, passport_of
from provenance.passport import verify_passport


def main() -> int:
    reg = AssetRegistry()
    asset = register_rwa(reg, build(), creator="acct:op:dgd-wagyu")

    # first-class asset: kind, title, and a real split that routes to the rancher
    assert asset.kind == "rwa", asset.kind
    accts = {p.account: p.bps for p in asset.effective_split.payees}
    assert "acct:rancher:sadu" in accts and accts["acct:rancher:sadu"] > 0
    assert asset.license.flat_fee_cents == 5850            # the $58.50 sale price

    # content-addressing binds provenance: the passport IS the content, so the
    # same provenance yields the same asset_id, and it round-trips exactly.
    asset2 = register_rwa(AssetRegistry(), build(), creator="acct:op:dgd-wagyu")
    assert asset.asset_id == asset2.asset_id, "same provenance must be same id"
    pp = passport_of(reg, asset)
    ok, _ = verify_passport(pp)
    assert ok and pp["subject"]["product"] == "A5 Wagyu ribeye"

    # you can't list what you can't prove: a tampered passport is refused
    p = build()
    p.events[1].data["feed"] = ["sawdust"]                 # break a signed link
    try:
        register_rwa(AssetRegistry(), p, creator="acct:op:dgd-wagyu")
        assert False, "should have refused an unverifiable passport"
    except ValueError as e:
        assert "does not verify" in str(e), e

    # the live server surfaces it exactly like any asset — same marketplace call
    import bingo.server as srv
    rwa = [a for a in srv._assets() if a["kind"] == "rwa"]
    assert rwa, "RWA good must appear in /api/assets"
    prov = rwa[0]["provenance"]
    assert prov["verified"] and prov["grade"] == "A5" and prov["origin"] == "SADU Farms"
    resp = srv._passport(rwa[0]["asset_id"])
    assert resp["verify"]["ok"]
    cert = srv._certificate(rwa[0]["asset_id"])
    assert cert and "SADU Farms" in cert and "VERIFIED" in cert

    print(f"OK — A5 Wagyu registered as a first-class asset "
          f"({asset.asset_id[:12]}…): content-addressed to its passport, "
          f"split routes {accts['acct:rancher:sadu']/100:.0f}% to the rancher, "
          f"unverifiable provenance refused, and it verifies through the live "
          f"marketplace + /passport certificate. A cow beside the brackets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
