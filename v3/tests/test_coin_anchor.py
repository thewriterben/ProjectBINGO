"""The coin rollback limitation, closed.

`provenance/coin.py` used to concede this in its own docstring: the anti-rollback
sidecar pins the last head+length, but "**if an attacker can rewrite the anchor
too**" a self-contained artifact cannot detect a rollback. An attacker who owns
the disk truncates the signed ledger AND rewrites `<store>.anchor` to match, and
every remaining check passes -- because a valid signed chain has valid signed
PREFIXES, and the only thing distinguishing "legitimate ledger" from "truncated
ledger" was a file the attacker just edited.

Wiring an external `AnchorService` moves the authority for "how long was this
ledger?" to a party the disk-owner does not control. `test_the_attack_the_docstring_
conceded` runs that exact attack twice -- once without the log (it SUCCEEDS, which
is what the concession meant) and once with it (refused).

  python -m tests.test_coin_anchor
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

from bingo import keys
from bingo.anchor import AnchorService, TransparencyLog
from provenance.coin import CoinError, RedemptionRegistry, mint_coin
from provenance.passport import Actor


class StubBackend:
    def post_credit(self, coin_serial, account, cents, ref=None):
        return {"ok": True, "ref": f"stub:{coin_serial}"}


def _service():
    log_signer = keys.LocalSigner.generate("anchor-log")
    return AnchorService(TransparencyLog("coin-log", signer=log_signer)), log_signer


def _redeem_one(path, service=None, pubkey=None, dgd=None, val=None, coin=None):
    """Open a ledger, redeem one coin, return the ledger."""
    reg = RedemptionRegistry(val, dgd.pubkey_hex, store_path=path,
                             backend=StubBackend(), anchor_service=service,
                             anchor_log_pubkey=pubkey)
    reg.redeem(coin, "acct:holder", ts="t1")
    return reg


def _rollback_the_disk(path):
    """The attack: truncate the signed ledger AND rewrite the local sidecar so it
    agrees. Everything on disk is now internally consistent."""
    data = json.load(open(path))
    data["events"] = []                       # forget the spend entirely
    data["credits"] = {}
    data["postings"] = {}
    json.dump(data, open(path, "w"))
    json.dump({"len": 0, "head": "0" * 64}, open(path + ".anchor", "w"))


def test_the_attack_the_docstring_conceded():
    dgd = Actor.create("dgd", "DGD", "issuer", "acct:dgd")
    val = Actor.create("val", "Validator", "validator", "acct:val")

    # ---- 1. WITHOUT an external log: the rollback SUCCEEDS -------------------
    # (this is the concession, demonstrated rather than asserted)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "r.json")
        coin = mint_coin(dgd, serial="DGD-1", passport_head="a" * 64, credit_cents=2500)
        _redeem_one(path, dgd=dgd, val=val, coin=coin)
        _rollback_the_disk(path)
        reopened = RedemptionRegistry(val, dgd.pubkey_hex, store_path=path,
                                      backend=StubBackend())
        assert reopened.status("DGD-1") != "REDEEMED", (
            "without an external anchor the rollback is invisible - if this ever "
            "starts failing, the local sidecar somehow got stronger and this "
            "test's premise needs revisiting")
        # ...and the coin can be spent a second time
        reopened.redeem(coin, "acct:thief", ts="t2")

    # ---- 2. WITH an external log: refused ------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "r.json")
        svc, log_signer = _service()
        pub = log_signer.public_key()
        coin = mint_coin(dgd, serial="DGD-2", passport_head="b" * 64, credit_cents=2500)
        _redeem_one(path, svc, pub, dgd, val, coin)
        _rollback_the_disk(path)
        try:
            RedemptionRegistry(val, dgd.pubkey_hex, store_path=path,
                               backend=StubBackend(), anchor_service=svc,
                               anchor_log_pubkey=pub)
            assert False, "the external anchor must catch a rewritten sidecar"
        except CoinError as e:
            assert "external log" in str(e) and "rollback" in str(e).lower(), e


def test_deleting_the_whole_store_is_refused():
    """The cheapest rollback of all: delete the ledger and its sidecar. The log
    still remembers there were events."""
    dgd = Actor.create("dgd", "DGD", "issuer", "acct:dgd")
    val = Actor.create("val", "Validator", "validator", "acct:val")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "r.json")
        svc, log_signer = _service()
        pub = log_signer.public_key()
        coin = mint_coin(dgd, serial="DGD-3", passport_head="c" * 64, credit_cents=2500)
        _redeem_one(path, svc, pub, dgd, val, coin)
        os.remove(path)
        os.remove(path + ".anchor")
        try:
            RedemptionRegistry(val, dgd.pubkey_hex, store_path=path,
                               backend=StubBackend(), anchor_service=svc,
                               anchor_log_pubkey=pub)
            assert False, "a deleted store must be refused when the log has events"
        except CoinError as e:
            assert "external anchor log records prior events" in str(e), e


def test_partial_truncation_to_a_VALID_signed_prefix_is_refused():
    """The subtle version, and the one the sidecar existed for.

    An attacker does not hand you an internally-inconsistent file - they hand you
    a genuinely valid, correctly-signed SHORTER ledger, because every prefix of a
    signed hash chain is itself a signed hash chain. Here we build that prefix
    honestly (redeem only the first coin, same validator, same timestamps, so the
    events are byte-identical to the real ledger's first half) and drop it in
    place, sidecar and all. Nothing on disk is forgeable-looking; only the
    external log knows the ledger was ever longer.
    """
    dgd = Actor.create("dgd", "DGD", "issuer", "acct:dgd")
    val = Actor.create("val", "Validator", "validator", "acct:val")
    c1 = mint_coin(dgd, serial="DGD-4", passport_head="d" * 64, credit_cents=2500)
    c2 = mint_coin(dgd, serial="DGD-5", passport_head="e" * 64, credit_cents=2500)

    with tempfile.TemporaryDirectory() as tmp:
        # the real ledger: both coins spent, anchored externally
        path = os.path.join(tmp, "r.json")
        svc, log_signer = _service()
        pub = log_signer.public_key()
        reg = _redeem_one(path, svc, pub, dgd, val, c1)
        reg.redeem(c2, "acct:holder", ts="t2")

        # the attacker's replacement: a legitimately-signed ledger with ONLY c1
        prefix_path = os.path.join(tmp, "prefix.json")
        RedemptionRegistry(val, dgd.pubkey_hex, store_path=prefix_path,
                           backend=StubBackend()).redeem(c1, "acct:holder", ts="t1")
        prefix = json.load(open(prefix_path))
        assert len(prefix["events"]) < len(reg.events), "prefix must be shorter"

        json.dump(prefix, open(path, "w"))
        json.dump({"len": len(prefix["events"]),
                   "head": prefix["events"][-1]["hash"]}, open(path + ".anchor", "w"))

        # it is a perfectly valid ledger on its own terms...
        RedemptionRegistry(val, dgd.pubkey_hex, store_path=path, backend=StubBackend())
        # ...and the external log refuses it
        try:
            RedemptionRegistry(val, dgd.pubkey_hex, store_path=path,
                               backend=StubBackend(), anchor_service=svc,
                               anchor_log_pubkey=pub)
            assert False, "truncation to a valid signed prefix must be caught"
        except CoinError as e:
            assert "external log" in str(e), e


def test_honest_restart_still_works():
    """The check must not cost an honest operator anything: reopen, single-use
    still holds, and the ledger keeps working."""
    dgd = Actor.create("dgd", "DGD", "issuer", "acct:dgd")
    val = Actor.create("val", "Validator", "validator", "acct:val")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "r.json")
        svc, log_signer = _service()
        pub = log_signer.public_key()
        coin = mint_coin(dgd, serial="DGD-6", passport_head="f" * 64, credit_cents=2500)
        _redeem_one(path, svc, pub, dgd, val, coin)

        again = RedemptionRegistry(val, dgd.pubkey_hex, store_path=path,
                                   backend=StubBackend(), anchor_service=svc,
                                   anchor_log_pubkey=pub)
        assert again.status("DGD-6") == "REDEEMED"
        assert again.credits.get("acct:holder") == 2500
        try:
            again.redeem(coin, "acct:thief", ts="t9")
            assert False, "single-use must still hold across an anchored restart"
        except CoinError as e:
            assert "already redeemed" in str(e)
        # a further redemption re-anchors, and the ledger reopens cleanly again
        c2 = mint_coin(dgd, serial="DGD-7", passport_head="0" * 64, credit_cents=2500)
        again.redeem(c2, "acct:holder", ts="t10")
        third = RedemptionRegistry(val, dgd.pubkey_hex, store_path=path,
                                   backend=StubBackend(), anchor_service=svc,
                                   anchor_log_pubkey=pub)
        assert third.status("DGD-7") == "REDEEMED"


def test_anchor_verification_fails_closed():
    """A configured anchor must never degrade to 'unanchored' on bad input."""
    dgd = Actor.create("dgd", "DGD", "issuer", "acct:dgd")
    val = Actor.create("val", "Validator", "validator", "acct:val")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "r.json")
        svc, log_signer = _service()
        pub = log_signer.public_key()
        coin = mint_coin(dgd, serial="DGD-8", passport_head="1" * 64, credit_cents=2500)
        _redeem_one(path, svc, pub, dgd, val, coin)

        # a service configured with NO log key cannot be trusted
        try:
            RedemptionRegistry(val, dgd.pubkey_hex, store_path=path,
                               backend=StubBackend(), anchor_service=svc)
            assert False, "an anchor service with no log key must be refused"
        except CoinError as e:
            assert "no log public key" in str(e)

        # a receipt signed by somebody else's log must not verify
        impostor = keys.LocalSigner.generate("evil-log")
        try:
            RedemptionRegistry(val, dgd.pubkey_hex, store_path=path,
                               backend=StubBackend(), anchor_service=svc,
                               anchor_log_pubkey=impostor.public_key())
            assert False, "a receipt from an untrusted log must be refused"
        except CoinError as e:
            assert "did not verify" in str(e)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK - all {len(tests)} coin-anchor groups pass: the rollback the module "
          "docstring used to concede - truncate the signed ledger AND rewrite the "
          "local sidecar so it agrees - is demonstrated to SUCCEED without an "
          "external log and to be REFUSED with one. Deleting the store outright, "
          "and dropping only the trailing events, are both caught too; an honest "
          "restart is unaffected and single-use still holds; and a configured "
          "anchor fails closed rather than degrading to unanchored when the log key "
          "is missing or the receipt comes from an untrusted log.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
