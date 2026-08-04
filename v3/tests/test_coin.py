"""DGD promo coin bearer credential: offline authenticity, QR round-trip,
single-use redemption of the $25 credit, and a tamper-evident redemption ledger.
Run:

  python -m tests.test_coin
"""

from __future__ import annotations

import json
import sys

from bingo.models import canonical_json, sha256_hex
from provenance.passport import Actor
from provenance.coin import (mint_coin, qr_payload, parse_qr, verify_credential,
                             RedemptionRegistry, verify_registry, CoinError,
                             new_secret, check_secret)


def main() -> int:
    dgd = Actor.create("dgd", "DGD", "issuer", "acct:dgd")
    head = "a" * 64
    cred = mint_coin(dgd, serial="DGD-0001", passport_head=head, credit_cents=2500)

    # 1. authenticity under the TRUSTED key
    ok, _ = verify_credential(cred, dgd.pubkey_hex)
    assert ok

    # 2. counterfeit: a self-signed credential fails against the trusted key
    fake_issuer = Actor.create("fake", "Fake", "issuer", "acct:dgd")
    fake = mint_coin(fake_issuer, serial="DGD-0001", passport_head=head)
    bad, why = verify_credential(fake, dgd.pubkey_hex)
    assert not bad and "counterfeit" in why

    # 3. tamper: bumping the credit to $2500 breaks the signature
    t = dict(cred); t["credit_cents"] = 250000
    assert not verify_credential(t, dgd.pubkey_hex)[0]

    # 4. QR round-trips and still verifies
    parsed = parse_qr(qr_payload(cred))
    assert parsed["serial"] == "DGD-0001" and parsed["passport_head"] == head
    assert verify_credential(parsed, dgd.pubkey_hex)[0]

    # 5. single-use redemption credits $25 exactly once
    validator = Actor.create("val", "Validator", "validator", "acct:val")
    reg = RedemptionRegistry(validator, trusted_issuer_pubkey=dgd.pubkey_hex)
    rec = reg.redeem(parsed, "acct:holder", ts="t1")
    assert rec["credit_cents"] == 2500 and reg.credits["acct:holder"] == 2500
    assert reg.status("DGD-0001") == "REDEEMED"

    # 6. a copied QR (same serial) is blocked on replay; credits unchanged
    try:
        reg.redeem(parsed, "acct:thief", ts="t2")
        assert False, "double redemption should raise"
    except CoinError as e:
        assert "already redeemed" in str(e)
    assert "acct:thief" not in reg.credits

    # 7. a counterfeit is refused at redemption
    try:
        reg.redeem(parse_qr(qr_payload(fake)), "acct:thief", ts="t3")
        assert False, "counterfeit redemption should raise"
    except CoinError as e:
        assert "counterfeit" in str(e)

    # 8. the redemption ledger verifies independently
    ok, notes = verify_registry(reg.to_dict())
    assert ok, notes

    # 9. even a VALIDLY-SIGNED double-redeem in the ledger is caught on replay
    d = reg.to_dict()
    ev = {"seq": len(d["events"]), "ts": "t9", "type": "REDEEM",
          "data": {"serial": "DGD-0001", "to": "acct:y", "credit_cents": 2500},
          "prev_hash": d["events"][-1]["hash"]}
    body = canonical_json({k: ev[k] for k in ("seq", "ts", "type", "data", "prev_hash")})
    ev["sig"] = validator.sign(body)
    ev["hash"] = sha256_hex(body + ev["sig"].encode())
    d["events"].append(ev)
    bad, why = verify_registry(d)
    assert not bad and "twice" in why[-1], why

    # 10. tampering a ledger event is caught
    d2 = reg.to_dict()
    d2["events"][0]["data"]["to"] = "acct:someone-else"
    assert not verify_registry(d2)[0]

    # 11. physical anti-copy: a coin minted with a scratch-off code can't be
    #     redeemed from the QR alone — you need the code (physical possession)
    code = new_secret()
    coin2 = mint_coin(dgd, serial="DGD-0002", passport_head="b" * 64,
                      credit_cents=2500, secret=code)
    assert coin2["secret_hash"] and verify_credential(coin2, dgd.pubkey_hex)[0]
    # the code round-trips through the QR as a commitment (hash), never the secret
    p2 = parse_qr(qr_payload(coin2))
    assert p2["secret_hash"] == coin2["secret_hash"]
    assert code not in json.dumps(p2)          # the QR never carries the code itself
    assert check_secret(p2, code) and not check_secret(p2, "WRON-GXXX-XXXX-XXXX")

    reg2 = RedemptionRegistry(validator, trusted_issuer_pubkey=dgd.pubkey_hex)
    # photographed QR, no code -> refused
    try:
        reg2.redeem(p2, "acct:copycat", ts="t1")
        assert False, "redeem without the code should raise"
    except CoinError as e:
        assert "scratch-off code" in str(e)
    # wrong code -> refused, coin not consumed
    try:
        reg2.redeem(p2, "acct:copycat", ts="t1", secret="WRON-GXXX-XXXX-XXXX")
        assert False
    except CoinError:
        pass
    assert reg2.status("DGD-0002") == "VALID"
    # real code -> redeems once; reusing the code is still blocked (single-use)
    rec2 = reg2.redeem(p2, "acct:owner", ts="t2", secret=code)
    assert rec2["credit_cents"] == 2500
    try:
        reg2.redeem(p2, "acct:thief", ts="t3", secret=code)
        assert False
    except CoinError as e:
        assert "already redeemed" in str(e)
    assert verify_registry(reg2.to_dict())[0]

    print("OK — coin credential authentic vs counterfeit (offline); QR round-trips; "
          "$25 redeemed once, copied-QR and counterfeit both blocked; scratch-off "
          "code required to redeem (photo of QR isn't enough) and never travels in "
          "the QR; redemption ledger tamper-evident, rejects double-redemption.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
