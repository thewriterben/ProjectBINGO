"""Regressions for the round-6 red-team breaks (workflow wf_1c1f69aa-fc3).
Round 6's automated verifiers were killed by a session usage limit, so these 5
attacker claims were adjudicated by hand (each reproduced against the round-5
HEAD 8deb11e) and fixed. machine_rwa found nothing (three rounds clean). Each
assertion FAILS on the round-5 code and PASSES now.

  python -m tests.test_redteam_r6_regressions
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from provenance.passport import Actor, CutPassport, verify_passport
from provenance.token import verify_token
from provenance.transport import damage_delta
from provenance.coin import mint_coin, RedemptionRegistry, StubValidationBackend, CoinError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── coin: deleting the store while the anchor remains is a rollback (HIGH) ─────
def test_coin_store_deletion_caught():
    dgd = Actor.create("dgd", "DGD", "issuer", "acct:dgd")
    val = Actor.create("val", "V", "validator", "acct:val")
    coin = mint_coin(dgd, serial="S1", passport_head="a" * 64, credit_cents=2500)
    d = tempfile.mkdtemp()
    path = os.path.join(d, "store.json")
    try:
        r = RedemptionRegistry(val, dgd.pubkey_hex, store_path=path, backend=StubValidationBackend())
        r.redeem(coin, "acct:holder", ts="t1")
        os.remove(path)                      # delete the store, LEAVE the .anchor
        try:
            RedemptionRegistry(val, dgd.pubkey_hex, store_path=path, backend=StubValidationBackend())
            assert False, "store deleted out from under its anchor must fail closed"
        except CoinError:
            pass
    finally:
        __import__("shutil").rmtree(d, ignore_errors=True)


# ── passport: negative-price SALE injects never-paid legs (MEDIUM) ────────────
def test_passport_rejects_negative_price():
    op = Actor.create("op", "Op", "operation", "acct:op")
    pp = CutPassport(subject={"product": "A5", "lot": "L", "weight_lb": 1})
    pp.attest(op, "LINEAGE", {"tajima_pct": 96})
    split = {"payees": [{"account": "acct:op", "bps": 10000}]}
    legs = [{"account": "acct:op", "bps": 10000, "cents": -10000}]
    pp.attest(op, "SALE", {"buyer": "b", "unit": "1", "price_cents": -10000,
                           "split": split, "legs": legs})
    pp.settlement = legs
    ok, why = verify_passport(pp.to_dict())
    assert not ok and "non-negative" in why[-1], "a negative-price SALE must be rejected"


# ── token: verify_token fails closed on malformed input (MEDIUM) ──────────────
def test_token_verify_fail_closed():
    ok, notes = verify_token({"events": "notalist", "holders": {}})   # must not raise
    assert ok is False and isinstance(notes, list)
    ok, notes = verify_token({"events": [{"type": "ISSUE"}], "holders": {}})
    assert ok is False and isinstance(notes, list)


# ── transport: damage list must be strings (escrow_decision robustness, LOW) ──
def test_transport_damage_strings():
    assert damage_delta({"damage": ["old"]}, {"damage": ["old", "new"]}) == ["new"]
    from provenance.transport import (condition, make_acceptance, verify_transport)
    from tests.test_transport import actors, subject, booked
    broker, c1, _g, cust = actors()
    pp = booked(broker, c1, cust)
    pp.pickup(c1, condition(12340), ts="t1")
    acc = make_acceptance(cust, vin=subject()["vin"], cond=condition(12995),
                          booking_hash=pp.events[0]["hash"], ts="t2")
    pp.deliver(c1, acc, condition(12995), ts="t3")
    d = pp.to_dict()
    d["events"][1]["data"]["condition"]["damage"] = [1, 2]   # non-string elements
    ok, _ = verify_transport(d)
    assert not ok, "non-string damage elements must be rejected before settlement"


# ── orchestrator: the PoF settlement gate is not an assert (survives -O) (HIGH)
def test_settlement_gate_survives_dash_O():
    script = (
        "import bingo.node.agent as A\n"
        "A.NodeAgent.verify_chain = staticmethod(lambda *a, **k: False)\n"
        "from bingo.dfm import DfmReport\n"
        "from tests.test_earnings import build\n"
        "reg, ledger, orch, bracket, clip = build()\n"
        "dfm = DfmReport(True, [], 0, (0,0,0), 0.0, 6.0, 0.2)\n"
        "o, dfm = orch.place_order(buyer='acct:b', asset_id=bracket.asset_id, qty=1,\n"
        "    material='PLA', buyer_lat=39.7, buyer_lon=-105.0, dfm_override=dfm)\n"
        "try:\n"
        "    orch.execute_order(o, dfm)\n"
        "    print('SETTLED')\n"
        "except Exception:\n"
        "    print('REFUSED')\n"
    )
    env = dict(os.environ, PYTHONPATH=".", PYTHONUTF8="1")
    proc = subprocess.run([sys.executable, "-O", "-c", script], cwd=ROOT,
                          env=env, capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    assert "REFUSED" in out and "SETTLED" not in out, \
        f"under -O the PoF settlement gate must still refuse a bad chain; got: {out!r}"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK — all {len(tests)} round-6 regression groups pass: coin catches "
          "store-deletion rollback; passport rejects negative-price SALE; "
          "verify_token fails closed; transport rejects non-string damage; and the "
          "PoF settlement gate is an if/raise that survives `python -O` (no assert).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
