"""Production hardening of coin redemption: the ledger persists (a restart never
forgets a spent coin), a tampered ledger file fails closed on load, and the
validation backend posts the $25 credit with safe pending/retry semantics. Run:

  python -m tests.test_redemption
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

from provenance.passport import Actor
from provenance.coin import (mint_coin, RedemptionRegistry, verify_registry,
                             ValidationBackend, StubValidationBackend, CoinError)


class FailBackend(ValidationBackend):
    def __init__(self):
        self.fail = True
        self.calls = 0

    def credit(self, account, cents, coin_serial, ts):
        self.calls += 1
        if self.fail:
            raise RuntimeError("backend down")
        return {"ok": True, "ref": f"ok:{coin_serial}"}


def main() -> int:
    dgd = Actor.create("dgd", "DGD", "issuer", "acct:dgd")
    val = Actor.create("val", "Validator", "validator", "acct:val")
    coin = mint_coin(dgd, serial="DGD-0001", passport_head="a" * 64, credit_cents=2500)
    coin2 = mint_coin(dgd, serial="DGD-0002", passport_head="b" * 64, credit_cents=2500)

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "redemptions.json")

        # --- persistence: redeem, then reload a FRESH registry from disk ---
        r1 = RedemptionRegistry(val, dgd.pubkey_hex, store_path=path,
                                backend=StubValidationBackend())
        rec = r1.redeem(coin, "acct:holder", ts="t1")
        assert rec["credit_status"] == "posted" and rec["credit_ref"] == "stub:DGD-0001"
        assert os.path.exists(path)

        r2 = RedemptionRegistry(val, dgd.pubkey_hex, store_path=path,
                                backend=StubValidationBackend())
        assert r2.status("DGD-0001") == "REDEEMED"          # survived the "restart"
        assert r2.credits.get("acct:holder") == 2500
        # and single-use holds across the restart
        try:
            r2.redeem(coin, "acct:thief", ts="t2")
            assert False, "double redemption across restart should raise"
        except CoinError as e:
            assert "already redeemed" in str(e)

        # --- tampered ledger file fails closed on load ---
        data = json.load(open(path))
        data["events"][0]["data"]["to"] = "acct:attacker"    # rewrite who got paid
        json.dump(data, open(path, "w"))
        try:
            RedemptionRegistry(val, dgd.pubkey_hex, store_path=path)
            assert False, "loading a tampered ledger should raise"
        except CoinError as e:
            assert "verification" in str(e) or "tamper" in str(e).lower()

    # --- backend down: coin still spent, credit goes 'pending', retry posts it ---
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "led.json")
        fb = FailBackend()
        reg = RedemptionRegistry(val, dgd.pubkey_hex, store_path=path, backend=fb)
        rec = reg.redeem(coin2, "acct:holder", ts="t1")
        assert rec["credit_status"] == "pending"             # backend was down...
        assert reg.status("DGD-0002") == "REDEEMED"          # ...but the coin is spent
        assert reg.credits["acct:holder"] == 2500            # credit recorded, awaiting post
        # backend recovers; retry posts exactly the pending one, no double-spend
        fb.fail = False
        posted = reg.retry_pending(ts="t2")
        assert posted == 1 and reg.postings["DGD-0002"]["status"] == "posted"
        # retry again is a no-op (idempotent)
        assert reg.retry_pending(ts="t3") == 0
        # and the signed ledger still verifies
        assert verify_registry(reg.to_dict())[0]

    print("OK — redemption ledger persists (spent coins survive restart & still "
          "block replay), a tampered ledger file fails closed on load, and the "
          "validation backend posts the $25 with safe pending/retry (coin committed "
          "before crediting, so a backend outage never double-credits).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
