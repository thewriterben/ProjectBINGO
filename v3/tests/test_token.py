"""RWA tokenization: issue/transfer/redeem, double-spend & authorization
blocked, tamper/forged-signer/reorder caught by independent replay, supply
conserved, and the token bound to its backing provenance. Run:

  python -m tests.test_token
"""

from __future__ import annotations

import copy
import json
import sys

from bingo.registry import AssetRegistry
from provenance.demo import build
from provenance.passport import Actor
from provenance.register import register_rwa
from provenance.token import AssetToken, TokenError, verify_token


def fresh():
    reg = AssetRegistry()
    passport = build()
    asset = register_rwa(reg, passport, creator="acct:op:dgd-wagyu")
    pp = passport.to_dict()
    op = Actor.create("op", "Op", "operation", "acct:op")
    a = Actor.create("a", "A", "buyer", "acct:a")
    b = Actor.create("b", "B", "holder", "acct:b")
    tok = AssetToken(backing_asset_id=asset.asset_id, passport_head=pp["chain_head"],
                     unit="1/100 lot", total_supply=100, issuer=op, ts="t0")
    return pp, op, a, b, tok


def main() -> int:
    pp, op, a, b, tok = fresh()

    # happy path: distribute, secondary transfer, redeem
    tok.transfer(op, a.account, 40, ts="t1")
    tok.transfer(op, b.account, 25, ts="t2")
    tok.transfer(b, a.account, 10, ts="t3")
    tok.redeem(a, 15, note="served", ts="t4")
    td = tok.to_dict()
    assert td["balances"] == {"acct:op": 35, "acct:a": 35, "acct:b": 15}, td["balances"]
    assert td["retired"] == 15 and td["circulating"] == 85

    ok, notes = verify_token(td, backing_passport=pp)
    assert ok, notes

    # 1. live overdraft is blocked at the API (can't move what you don't hold)
    try:
        tok.transfer(b, a.account, 999, ts="tx")
        assert False, "overdraft should raise"
    except TokenError:
        pass

    # 2. a FORGED overdraft in the document is caught by replay
    t = copy.deepcopy(td)
    t["events"][1]["data"]["shares"] = 9999          # (signature now won't match)
    bad, why = verify_token(t)
    assert not bad, why                              # tamper OR overdraft — either way rejected

    # 3. authorization: even a VALIDLY-SIGNED transfer is rejected if the signer
    #    isn't the 'from' owner (defense-in-depth the API itself won't emit).
    from bingo.models import canonical_json, sha256_hex
    _, op2, a2, b2, tok2 = fresh()
    t = tok2.to_dict()
    ev = {"seq": len(t["events"]), "ts": "t9", "type": "TRANSFER", "signer": "op",
          "data": {"from": "acct:a", "to": "acct:op", "shares": 5},  # op moving a's shares
          "prev_hash": t["events"][-1]["hash"]}
    body = canonical_json({k: ev[k] for k in
                           ("seq", "ts", "type", "signer", "data", "prev_hash")})
    ev["sig"] = op2.sign(body)                         # a genuine signature by op
    ev["hash"] = sha256_hex(body + ev["sig"].encode())
    t["events"].append(ev)
    bad, why = verify_token(t)
    assert not bad and "'from' owner" in why[-1], why

    # 4. tamper a redeem note -> hash mismatch
    t = copy.deepcopy(td)
    red = next(e for e in t["events"] if e["type"] == "REDEEM")
    red["data"]["note"] = "lie"
    bad, why = verify_token(t)
    assert not bad and "tampered" in why[-1], why

    # 5. forged signer: repoint a holder's key -> signature fails
    t = copy.deepcopy(td)
    other = Actor.create("x", "X", "holder", "acct:b")
    t["holders"]["b"]["pubkey"] = other.pubkey_hex
    bad, why = verify_token(t)
    assert not bad and "bad signature" in why[-1], why

    # 6. reorder ledger -> broken hash chain
    t = copy.deepcopy(td)
    t["events"][1], t["events"][2] = t["events"][2], t["events"][1]
    bad, why = verify_token(t)
    assert not bad and "hash chain" in why[-1], why

    # 7. supply conservation: fudging total_supply is caught
    t = copy.deepcopy(td)
    t["total_supply"] = 200
    bad, why = verify_token(t)
    assert not bad, why

    # 8. the token is only as good as its backing: wrong passport pin rejected
    _, op3, _, _, _ = fresh()
    tok3 = AssetToken(backing_asset_id="x", passport_head="de" * 32,
                      unit="u", total_supply=10, issuer=op3, ts="t0")
    bad, why = verify_token(tok3.to_dict(), backing_passport=pp)
    assert not bad and "not pinned" in why[-1], why

    # round-trips as plain JSON, verifiable offline by anyone
    assert verify_token(json.loads(json.dumps(td)))[0]

    print("OK — token issued/transferred/redeemed (85/100 circulating, 15 redeemed); "
          "live + forged overdraft blocked; unauthorized transfer, tamper, forged "
          "signer, reorder, supply fudging all caught by replay; token bound to its "
          "verified provenance (wrong pin rejected).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
