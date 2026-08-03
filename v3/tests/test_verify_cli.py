"""The standalone verifier CLI: verifies passport & token files from disk,
dispatches by schema, catches tampering, and returns correct exit codes. Run:

  python -m tests.test_verify_cli
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

from bingo.registry import AssetRegistry
from provenance.demo import build as build_passport
from provenance.passport import Actor
from provenance.register import register_rwa
from provenance.token import AssetToken
from provenance import verify as V


def write(d: dict, path: str):
    with open(path, "w") as f:
        json.dump(d, f)
    return path


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        passport = build_passport()
        pp = passport.to_dict()
        pp_path = write(pp, os.path.join(tmp, "passport.json"))

        reg = AssetRegistry()
        asset = register_rwa(reg, build_passport(), creator="acct:op:dgd-wagyu")
        vsplit = next(e["data"]["split"]["payees"] for e in pp["events"] if e["type"] == "SALE")
        op = Actor.create("op", "Op", "operation", "acct:op:dgd-wagyu")
        buyer = Actor.create("buyer", "Buyer", "buyer", "acct:buyer")
        tok = AssetToken(backing_asset_id=asset.asset_id, passport_head=pp["chain_head"],
                         unit="1/100", total_supply=100, issuer=op, value_split=vsplit, ts="t0")
        tok.sell(op, buyer.account, 20, price_cents=2000, ts="t1")
        tok_path = write(tok.to_dict(), os.path.join(tmp, "token.json"))

        # schema dispatch: each file verifies as its own kind
        assert V.verify_doc(V._load(pp_path))[0]
        assert V.verify_doc(V._load(tok_path), backing=pp)[0]

        # exit codes: main() returns 0 for a good file
        assert V.main([pp_path]) == 0
        assert V.main([tok_path, "--passport", pp_path]) == 0

        # a tampered passport file is caught, and main() exits non-zero
        bad = json.loads(json.dumps(pp))
        next(e for e in bad["events"] if e["type"] == "HARVEST")["data"]["grade"] = "A3"
        bad_path = write(bad, os.path.join(tmp, "bad.json"))
        ok, notes = V.verify_doc(V._load(bad_path))
        assert not ok and "tampered" in notes[-1], notes
        assert V.main([bad_path]) == 1

        # a token checked against the WRONG backing passport fails the pin
        other = build_passport().to_dict()
        other["chain_head"] = "de" * 32          # force a different head
        assert not V.verify_doc(V._load(tok_path), backing=other)[0]

        # an unrecognized document is rejected, not silently passed
        junk = write({"schema": "nope", "x": 1}, os.path.join(tmp, "junk.json"))
        assert V.main([junk]) == 1

        # directory mode verifies every file and fails if any fails
        assert V.main([tmp]) == 1                 # tmp contains bad.json + junk.json

    print("OK — verifier CLI dispatches passport/token by schema, verifies from "
          "disk, catches tampering and a wrong backing-passport pin, rejects "
          "unknown docs, and returns correct exit codes (incl. directory mode).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
