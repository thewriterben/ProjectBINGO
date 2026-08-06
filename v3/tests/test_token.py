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
    tok.transfer(op, a, 40, ts="t1")            # Actor recipient binds account->key
    tok.transfer(op, b, 25, ts="t2")
    tok.transfer(b, a, 10, ts="t3")
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

    # ---- priced sales route proceeds through the provenance split ----
    from provenance.token import token_settlement
    from bingo.models import canonical_json, sha256_hex

    pp9, op9, a9, b9, _ = fresh()
    vsplit = next(e["data"]["split"]["payees"]
                  for e in pp9["events"] if e["type"] == "SALE")
    reg9 = AssetRegistry()
    asset9 = register_rwa(reg9, build(), creator="acct:op")
    tok9 = AssetToken(backing_asset_id=asset9.asset_id, passport_head=pp9["chain_head"],
                      unit="1/100", total_supply=100, issuer=op9,
                      value_split=vsplit, ts="t0")
    tok9.sell(op9, a9, 40, price_cents=4000, ts="t1")             # primary (Actor binds key)
    tok9.sell(a9, b9.account, 10, price_cents=1000, resale_royalty_bps=500, ts="t2")  # resale
    td9 = tok9.to_dict()
    ok, why = verify_token(td9, backing_passport=pp9)
    assert ok, why

    st = token_settlement(td9)
    # primary 4000¢ fully routed to the provenance split; resale seller keeps 95%
    assert st["proceeds_cents"] == 5000
    assert st["paid"].get("acct:a") == 950                 # 1000 - 5% royalty
    # rancher (22%) is paid on the primary AND on the resale royalty
    assert st["paid"]["acct:rancher:sadu"] == (4000 * 2200 // 10000) + (50 * 2200 // 10000)

    # 9. a fabricated payout (validly signed, but legs don't match the split) is caught
    _, op10, a10, b10, _ = fresh()
    tok10 = AssetToken(backing_asset_id="x", passport_head="p", unit="u",
                       total_supply=100, issuer=op10, value_split=vsplit, ts="t0")
    t = tok10.to_dict()
    ev = {"seq": 1, "ts": "t9", "type": "SALE", "signer": "op",
          "data": {"from": "acct:op", "to": "acct:a", "shares": 10, "price_cents": 1000,
                   "primary": True, "royalty_bps": 0,
                   "legs": [{"account": "acct:op", "cents": 1000}]},   # should route to split
          "prev_hash": t["events"][-1]["hash"]}
    body = canonical_json({k: ev[k] for k in
                           ("seq", "ts", "type", "signer", "data", "prev_hash")})
    ev["sig"] = op10.sign(body)
    ev["hash"] = sha256_hex(body + ev["sig"].encode())
    t["events"].append(ev)
    bad, why = verify_token(t)
    assert not bad and "legs don't match" in why[-1], why

    # ---- redemption must be physically settled by the fulfiller ----
    from provenance.token import make_fulfillment, _receipt_body
    ppf, opf, af, bf, _ = fresh()
    assetf = register_rwa(AssetRegistry(), build(), creator="acct:op")
    grocer = Actor.create("grocer", "Grocer", "grocer", "acct:grocer")
    custody_ref = next(e["hash"] for e in ppf["events"] if e["type"] == "CUSTODY")
    tokf = AssetToken(backing_asset_id=assetf.asset_id, passport_head=ppf["chain_head"],
                      unit="u", total_supply=100, issuer=opf, fulfiller=grocer, ts="t0")

    # 10. with a fulfiller, redeeming with NO receipt is refused
    try:
        tokf.redeem(opf, 10, ts="t1")
        assert False, "redeem without receipt should raise"
    except TokenError:
        pass

    # 11. a receipt signed by someone other than the registered fulfiller is refused
    imp = Actor.create("imp", "Imposter", "grocer", "acct:grocer")
    forged = {"token_id": tokf.token_id, "delivery_ref": custody_ref, "units": 10,
              "fulfiller": "grocer", "ts": "t1"}
    forged["sig"] = imp.sign(_receipt_body(forged))     # wrong key, right account/id
    forged["pubkey"] = imp.pubkey_hex
    try:
        tokf.redeem(opf, 10, receipt=forged, ts="t1")
        assert False, "forged receipt should raise"
    except TokenError:
        pass

    # 12. a valid, fulfiller-co-signed receipt lets redemption through, and it
    #     verifies as anchored to the passport's signed custody event
    good = make_fulfillment(grocer, token_id=tokf.token_id, delivery_ref=custody_ref,
                            units=10, ts="t1")
    tokf.redeem(opf, 10, receipt=good, ts="t2")
    okf, whyf = verify_token(tokf.to_dict(), backing_passport=ppf)
    assert okf and any("anchored" in n for n in whyf), whyf

    # 13. a receipt that doesn't cover the shares is refused
    short = make_fulfillment(grocer, token_id=tokf.token_id, delivery_ref=custody_ref,
                             units=3, ts="t3")
    try:
        tokf.redeem(opf, 10, receipt=short, ts="t3")
        assert False, "under-covered receipt should raise"
    except TokenError:
        pass

    # 14. a redemption anchored to a delivery NOT in the passport is caught by verify
    _, opg, _, _, _ = fresh()
    tokg = AssetToken(backing_asset_id="x", passport_head=ppf["chain_head"],
                      unit="u", total_supply=100, issuer=opg, fulfiller=grocer, ts="t0")
    bogus = make_fulfillment(grocer, token_id=tokg.token_id, delivery_ref="00" * 32,
                             units=10, ts="t1")
    tokg.redeem(opg, 10, receipt=bogus, ts="t2")        # locally valid receipt...
    assert verify_token(tokg.to_dict())[0]              # ...passes with no backing
    bad, why = verify_token(tokg.to_dict(), backing_passport=ppf)
    assert not bad and "not anchored" in why[-1], why   # ...but not anchored in the chain

    # round-trips as plain JSON, verifiable offline by anyone
    assert verify_token(json.loads(json.dumps(td)))[0]
    assert verify_token(json.loads(json.dumps(td9)), backing_passport=pp9)[0]
    assert verify_token(json.loads(json.dumps(tokf.to_dict())), backing_passport=ppf)[0]

    print("OK — token issued/sold/redeemed; overdraft, unauthorized transfer, "
          "tamper, forged signer, reorder, supply fudging & fabricated payouts all "
          "caught by replay; sale proceeds route to the rancher; token bound to its "
          "verified provenance; and redemption requires a fulfiller-co-signed receipt "
          "anchored to a real delivery event in the passport.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
