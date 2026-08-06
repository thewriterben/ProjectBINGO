"""Regressions for the round-5 red-team breaks (workflow wf_c4b649b2-60f).
Round 5 found 11 confirmed breaks against the round-4-hardened HEAD b64dbba
(machine_rwa found nothing; coin's economic claim was again rejected). Two were
real value/authorization bugs (token negative-shares, terminal-account capture),
two were content/settlement integrity (passport chain_head, no-sale settlement),
one was an untyped signed OPEN, and SIX were the same class: a document verifier
must return (False, notes) on malformed/adversarial input, never raise. Each
assertion FAILS on the round-4 code and PASSES now.

  python -m tests.test_redteam_r5_regressions
"""

from __future__ import annotations

import copy
import sys

import provenance.coin as coin_mod
import provenance.passport as passport_mod
import provenance.transport as transport_mod
import provenance.machine_rwa as mrwa_mod
import provenance.raise_readiness as RR
import bingo.evidence as evidence
from provenance.passport import Actor, CutPassport, verify_passport
from provenance.token import AssetToken, verify_token
from provenance.machine_rwa import verify_machine_share
from bingo.models import canonical_json, sha256_hex

from tests.test_passport import build as build_passport

MSEED = (b"mallory-shared-key" + b"\x00" * 32)[:32]


# ── token: negative-shares TRANSFER drains a victim (CRITICAL) ────────────────
def test_token_rejects_negative_shares():
    iss = Actor.create("iss", "Iss", "issuer", "acct:iss")
    victim = Actor.create("vic", "Victim", "holder", "acct:vic")
    mal = Actor.create("mal", "Mallory", "holder", "acct:mal", seed=MSEED)
    tok = AssetToken(backing_asset_id="a", passport_head="0" * 64, unit="cut",
                     total_supply=100, issuer=iss,
                     value_split=[{"account": "acct:creator", "bps": 10000}], ts="t0")
    tok.transfer(iss, victim, 40, ts="t1")     # victim bound, holds 40
    tok.transfer(iss, mal, 1, ts="t2")         # mallory bound, holds 1
    doc = tok.to_dict()
    assert verify_token(doc)[0]
    t = copy.deepcopy(doc)
    t["holders"]["mal"] = mal.public()
    ev = {"seq": len(t["events"]), "ts": "t9", "type": "TRANSFER", "signer": "mal",
          "data": {"from": "acct:mal", "to": "acct:vic", "to_pubkey": None, "shares": -40},
          "prev_hash": t["events"][-1]["hash"]}
    body = canonical_json({k: ev[k] for k in
                           ("seq", "ts", "type", "signer", "data", "prev_hash")})
    ev["sig"] = mal.sign(body)
    ev["hash"] = sha256_hex(body + ev["sig"].encode())
    t["events"].append(ev)
    # advertise the POST-exploit balances (victim 40->0 drained into mallory 1->41)
    # so the displayed-balances check passes and verify must rely on the shares
    # guard — otherwise the old code rejects on the balance mismatch, not the bug
    t["balances"] = {"acct:iss": 59, "acct:mal": 41}
    ok, _ = verify_token(t)
    assert not ok, "a negative-shares TRANSFER must be rejected"


# ── token: a terminal (keyless) account stays frozen (HIGH) ───────────────────
def test_token_terminal_account_frozen():
    iss = Actor.create("iss", "Iss", "issuer", "acct:iss")
    mal = Actor.create("mal", "Mallory", "holder", "acct:mal", seed=MSEED)
    thief = Actor.create("thief", "Thief", "holder", "acct:frozen", seed=MSEED)  # mallory's key
    tok = AssetToken(backing_asset_id="a", passport_head="0" * 64, unit="cut",
                     total_supply=100, issuer=iss,
                     value_split=[{"account": "acct:creator", "bps": 10000}], ts="t0")
    tok.transfer(iss, "acct:frozen", 50, ts="t1")   # bare string -> terminal, un-spendable
    tok.transfer(iss, mal, 2, ts="t2")              # mallory bound
    assert verify_token(tok.to_dict())[0]
    # mallory sends 1 dust into acct:frozen naming her own key, then sweeps it out
    tok.transfer(mal, thief, 1, ts="t3")            # tries to bind acct:frozen -> mallory key
    tok.transfer(thief, mal, 51, ts="t4")           # sweep the frozen shares
    ok, _ = verify_token(tok.to_dict())
    assert not ok, "a terminal (keyless) account must never become spendable"


# ── passport: chain_head is bound to the real head (HIGH) ─────────────────────
def test_passport_chain_head_bound():
    pp = build_passport().to_dict()
    assert verify_passport(pp)[0]
    t = copy.deepcopy(pp)
    t["chain_head"] = "de" * 32       # a forged/foreign head (provenance substitution)
    ok, why = verify_passport(t)
    assert not ok and "chain_head" in why[-1], "a forged chain_head must be rejected"


# ── passport: no-SALE settlement injection (MEDIUM) ──────────────────────────
def test_passport_no_sale_settlement_rejected():
    op = Actor.create("op", "Op", "operation", "acct:op")
    pp = CutPassport(subject={"product": "A5", "lot": "L", "weight_lb": 1})
    pp.attest(op, "LINEAGE", {"tajima_pct": 96})
    doc = pp.to_dict()
    assert verify_passport(doc)[0]                 # honest no-sale passport
    doc["settlement"] = [{"account": "acct:attacker", "bps": 10000, "cents": 9999999}]
    ok, _ = verify_passport(doc)
    assert not ok, "injected settlement with no SALE must be rejected"


# ── machine_rwa: signed OPEN economic terms must be typed integers (HIGH) ─────
def test_machine_untyped_open_rejected():
    op = Actor.create("op", "Op", "operator", "acct:node:m")
    data = {"machine_id": "m", "total_shares": "100", "price_cents": 100,
            "investor_share_bps": 6000, "repayment_cap_cents": 1000000,
            "operator": "acct:node:m"}
    ev = {"seq": 0, "ts": "t0", "type": "OPEN", "signer": op.actor_id,
          "data": data, "prev_hash": "0" * 64}
    body = canonical_json({k: ev[k] for k in
                           ("seq", "ts", "type", "signer", "data", "prev_hash")})
    ev["sig"] = op.sign(body)
    ev["hash"] = sha256_hex(body + ev["sig"].encode())
    doc = {"machine_id": "m", "total_shares": "100", "price_cents": 100,
           "investor_share_bps": 6000, "repayment_cap_cents": 1000000,
           "operator": op.actor_id, "holders": {op.actor_id: op.public()}, "events": [ev]}
    ok, _ = verify_machine_share(doc)              # must not raise
    assert not ok, "a signed OPEN with a string total_shares must be rejected"
    try:
        RR.term_sheet(doc)
        assert False, "term_sheet must refuse the unverifiable offering"
    except ValueError:
        pass


# ── all verifiers fail CLOSED (return, never raise) on malformed input ────────
def test_verifiers_fail_closed_on_malformed():
    cases = [
        (verify_passport, {"events": [{"type": "X"}], "signers": {}}),
        (transport_mod.verify_transport, {"events": [{"type": "BOOKING", "data": "notadict"}]}),
        (verify_machine_share, {"events": "notalist", "holders": {}}),
        (coin_mod.verify_registry, {"validator": {"pubkey": "aa"}, "events": "notalist"}),
    ]
    for fn, arg in cases:
        ok, notes = fn(arg)          # must RETURN, not raise
        assert ok is False and isinstance(notes, list), (fn.__name__, ok, notes)
    ok, notes = evidence.verify({"events": [{"seq": 0}]}, "aa")
    assert ok is False and isinstance(notes, list)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK — all {len(tests)} round-5 regression groups pass: negative-shares "
          "and terminal-account theft closed in token; passport binds chain_head "
          "and refuses no-sale settlement; machine_rwa rejects untyped OPEN terms; "
          "and every document verifier (coin/passport/transport/machine_rwa/"
          "evidence) fails closed — returns (False, notes) — on malformed input "
          "instead of crashing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
