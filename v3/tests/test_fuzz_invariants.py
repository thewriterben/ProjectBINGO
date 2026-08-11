"""Continuous property-based fuzzing over the kernel's invariants.

Ten red-team rounds found 70 breaks by hand, and the campaign taught two things
that a fixed set of authored test cases cannot keep enforcing:

  1. **Fixes regress.** Round 2 broke two round-1 fixes; the settlement gate
     reopened across rounds 6, 7 and 8. A green suite of authored cases does not
     notice a guard quietly weakening.
  2. **A campaign only covers the surface you aim it at.** The forgeable-key
     default sat in shipped code through ten clean-looking rounds purely because
     no round was ever pointed at key *generation*.

So this generalizes the lessons instead of re-listing the findings. The central
technique is **structure-aware mutation**: build a genuinely valid signed
document, then corrupt it the way an adversary would - delete a field, change its
type, flip a byte, reorder events, duplicate one, negate a number - and hold every
verifier to two properties:

  * **A. it never raises.** A verifier that crashes on hostile input is a denial
    of service and, worse, an exception that some caller may treat as "unknown"
    rather than "no". This is the round-5 lesson, generalized to every input.
  * **B. corrupting SIGNED bytes is always rejected.** Mutations inside an event
    body, its signature, its hash or its chain link must never verify. This is
    the round-2/3 lesson (trust only signed bytes), generalized.

The four subsystems added most recently - payout, keys, keydir, anchor - had no
property-based coverage at all, so they get their own generators here.

Budget and reproducibility: every run picks a seed (or takes `BINGO_FUZZ_SEED`),
**prints it**, and a failure reports the seed so it can be replayed exactly.
`BINGO_FUZZ_ITERS` scales the effort - small by default so every push pays only a
second or two, large for a scheduled deep run.

  python -m tests.test_fuzz_invariants
  BINGO_FUZZ_ITERS=2000 python -m tests.test_fuzz_invariants     # deep run
  BINGO_FUZZ_SEED=12345 python -m tests.test_fuzz_invariants     # replay a failure
"""

from __future__ import annotations

import copy
import json
import os
import random
import sys

from bingo import crypto, keys
from bingo.anchor import (AnchorService, TransparencyLog, leaf_hash,
                          verify_anchored, verify_consistency, verify_inclusion)
from bingo.keydir import KeyDirectory, verify_directory
from bingo.payout import MockRail, PayoutEngine, PAID
from bingo.settlement import Leg

ITERS = int(os.environ.get("BINGO_FUZZ_ITERS", "150"))
SEED = int(os.environ.get("BINGO_FUZZ_SEED", random.randrange(2 ** 31)))
RNG = random.Random(SEED)


class FuzzFailure(AssertionError):
    """Carries the seed, because an unreproducible fuzz failure is nearly useless."""
    def __init__(self, msg: str):
        super().__init__(f"{msg}\n    replay with: BINGO_FUZZ_SEED={SEED} "
                         f"BINGO_FUZZ_ITERS={ITERS} python -m tests.test_fuzz_invariants")


# -- structure-aware mutation --------------------------------------------------

def _paths(obj, prefix=()):
    """Every addressable location in a nested JSON structure."""
    out = [prefix]
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += _paths(v, prefix + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += _paths(v, prefix + (i,))
    return out


def _get(obj, path):
    for p in path:
        obj = obj[p]
    return obj


def _set(obj, path, value):
    for p in path[:-1]:
        obj = obj[p]
    obj[path[-1]] = value


def _delete(obj, path):
    for p in path[:-1]:
        obj = obj[p]
    if isinstance(obj, dict):
        del obj[path[-1]]
    else:
        obj.pop(path[-1])


CORRUPTIONS = ("delete", "retype", "flip", "negate", "inflate", "empty",
               "reorder", "duplicate")


def mutate(doc: dict, rng: random.Random) -> tuple:
    """Return (mutated_copy, path, kind). Deliberately blunt - an attacker is not
    obliged to be tasteful."""
    d = copy.deepcopy(doc)
    paths = [p for p in _paths(d) if p]
    if not paths:
        return d, (), "noop"
    for _ in range(12):                                # find an applicable spot
        path = rng.choice(paths)
        kind = rng.choice(CORRUPTIONS)
        try:
            cur = _get(d, path)
            if kind == "delete":
                _delete(d, path)
            elif kind == "retype":
                _set(d, path, rng.choice([None, [], {}, 0, "", True, 3.5, [1, 2]]))
            elif kind == "flip":
                if not isinstance(cur, str) or not cur:
                    continue
                i = rng.randrange(len(cur))
                repl = "0" if cur[i] != "0" else "1"
                _set(d, path, cur[:i] + repl + cur[i + 1:])
            elif kind == "negate":
                if not isinstance(cur, int) or isinstance(cur, bool):
                    continue
                _set(d, path, -cur - 1)
            elif kind == "inflate":
                if not isinstance(cur, int) or isinstance(cur, bool):
                    continue
                _set(d, path, cur * rng.choice([2, 10, 10 ** 6]) + 1)
            elif kind == "empty":
                if not isinstance(cur, (list, dict, str)):
                    continue
                _set(d, path, type(cur)())
            elif kind == "reorder":
                if not isinstance(cur, list) or len(cur) < 2:
                    continue
                shuffled = list(cur)
                rng.shuffle(shuffled)
                if shuffled == cur:
                    shuffled.reverse()
                _set(d, path, shuffled)
            elif kind == "duplicate":
                if not isinstance(cur, list) or not cur:
                    continue
                _set(d, path, list(cur) + [copy.deepcopy(rng.choice(cur))])
            if d == doc:
                # the "mutation" changed nothing (emptying an already-empty list,
                # shuffling equal elements, ...). Accepting an unchanged document
                # is correct behaviour, so scoring it as a failure would be the
                # fuzzer lying about the code. Try again.
                d = copy.deepcopy(doc)
                continue
            return d, path, kind
        except Exception:
            d = copy.deepcopy(doc)
            continue
    return d, (), "noop"


def _signed_region(path) -> bool:
    """Is this path load-bearing - i.e. must corrupting it always be rejected?

    Being precise here matters, and getting it wrong in either direction is a bug
    in the test rather than the code. Too broad and the fuzzer cries wolf over
    display text; too narrow and it waves through a real hole. What is actually
    load-bearing, established by reading the verifiers rather than guessing:

      * anything under `events` - the hash-chained, signed bodies. This is the
        money, the attestations, and the chain links.
      * `signers.<id>.pubkey` - binds an identity to the key that may sign for it.
        Swap it and you decide who is allowed to attest.
      * top-level `settlement`, `chain_head`, `head` - unsigned mirrors that the
        verifiers cross-check against signed data (the round-1 fix made settlement
        conserve against the signed SALE legs; round 5 bound chain_head).

    Everything else in a `signers` record - `role`, `name`, `account` - is display
    metadata. It reads like it should matter, and it does not: money routes from
    `sale["data"]["legs"]` inside the signed body, and `role` only feeds the
    human-readable chain summary. The fuzzer flagged a deleted `role` on its very
    first run, which is exactly the kind of claim worth checking rather than
    assuming - it turned out to be an imprecise property, not a defect.
    """
    if any(p == "events" for p in path if isinstance(p, str)):
        return True
    if len(path) == 3 and path[0] == "signers" and path[2] == "pubkey":
        return True
    return bool(path) and path[0] in ("settlement", "chain_head", "head")


def _must_reject(doc: dict, path, kind: str) -> bool:
    """Must this particular corruption be rejected?

    Two corruptions look like tampering and are not, and conflating them would
    make the fuzzer demand behaviour that would actually be wrong:

      * **Deleting an optional top-level mirror.** `settlement` / `chain_head` /
        `head` are convenience copies of data that lives in the signed chain. A
        document that simply omits one is not claiming anything false, so it is
        fine. A document that *states a different value* is lying, and must be
        rejected - that distinction is the whole point of the mirrors.
      * **Deleting the LAST event.** That yields a shorter, internally valid,
        earlier state of the same chain - a transport passport that has been
        picked up but not yet delivered, say. It is not a forgery, and no
        self-contained document can tell it from the real earlier state; catching
        it is precisely the job of the external anchor (`bingo/anchor.py`).
        Deleting a *middle* event, by contrast, breaks the hash chain and must be
        caught.
    """
    if kind == "delete" and len(path) == 1 and path[0] in ("settlement", "chain_head",
                                                           "head"):
        return False
    if kind == "delete" and len(path) == 2 and path[0] == "events":
        return path[1] != len(doc.get("events", [])) - 1      # middle only
    return _signed_region(path)


def _fuzz_verifier(name: str, doc: dict, verify, iters: int, stats: dict):
    """Hold `verify` to properties A and B over `iters` mutations."""
    ok, _ = verify(doc)
    if not ok:
        raise FuzzFailure(f"{name}: the UNMUTATED document must verify - the fuzzer "
                          "is testing the wrong thing otherwise")
    for _ in range(iters):
        mutated, path, kind = mutate(doc, RNG)
        if kind == "noop":
            continue
        stats["mutations"] += 1
        try:
            result = verify(mutated)                    # PROPERTY A: never raises
        except Exception as e:
            raise FuzzFailure(
                f"{name}: verifier RAISED on a {kind} at {path} "
                f"({type(e).__name__}: {e}) - verifiers must fail closed, "
                "returning (False, notes)") from None
        if not (isinstance(result, tuple) and len(result) == 2
                and isinstance(result[0], bool)):
            raise FuzzFailure(f"{name}: verifier returned {result!r}, expected "
                              "(bool, notes)")
        accepted = result[0]
        if accepted and _must_reject(doc, path, kind):  # PROPERTY B
            stats["accepted_signed"] += 1
            raise FuzzFailure(
                f"{name}: ACCEPTED a {kind} inside signed bytes at {path} - "
                "a verifier must trust only what the signature covers")
        if not accepted:
            stats["rejected"] += 1


# -- the documents under test --------------------------------------------------

def _passport_doc():
    from provenance.demo import build
    return build().to_dict()


def _transport_doc():
    from provenance.transport import condition, make_acceptance
    from tests.test_transport import actors, subject, booked
    broker, c1, _g, cust = actors()
    pp = booked(broker, c1, cust)
    pp.pickup(c1, condition(12340, damage=[]), ts="t1")
    dcond = condition(12995, damage=["scuff"])
    acc = make_acceptance(cust, vin=subject()["vin"], cond=dcond,
                          booking_hash=pp.events[0]["hash"], ts="t2")
    pp.deliver(c1, acc, dcond, ts="t3")
    return pp.to_dict()


def _machine_rwa_doc():
    from tests.test_machine_rwa import build
    return build()[0].to_dict()          # (share, operator, *investors)


def _keydir_doc():
    s = keys.LocalSigner.generate("n")
    r = keys.LocalSigner.generate("n/rec")
    d = KeyDirectory.genesis("n", s, r.public_key())
    k2 = keys.LocalSigner.generate("n")
    d.rotate(s, k2.public_key())
    d.revoke(r, s.public_key(), "rotated out")
    return d.to_dict()


def test_regression_transport_binds_its_chain_head():
    """Found by this fuzzer, 2026-08-11, on roughly its fifth run.

    `verify_passport` has bound `chain_head` since round 5 - an unbound head lets
    a document advertise someone else's provenance. `verify_transport` never
    checked it, yet appended "chain head ... (verified)" to its notes: a claim in
    the output that the code did not back. Classic sibling-verifier drift, the
    same shape as the round-9 finding (passport accepted negative legs while the
    token verifier rejected them).

    Pinned deterministically here so it cannot silently come back.
    """
    from provenance.transport import verify_transport
    doc = _transport_doc()
    assert verify_transport(doc)[0], "the honest document must verify"

    lying = copy.deepcopy(doc)
    lying["chain_head"] = "0" * 64
    ok, notes = verify_transport(lying)
    assert not ok and "chain_head" in notes[-1], notes

    absent = copy.deepcopy(doc)                 # optional mirror: absence is fine
    del absent["chain_head"]
    assert verify_transport(absent)[0]


def test_document_verifiers_fail_closed_under_mutation():
    """The generalization of the whole red-team campaign."""
    stats = {"mutations": 0, "rejected": 0, "accepted_signed": 0}
    from provenance.machine_rwa import verify_machine_share
    from provenance.passport import verify_passport
    from provenance.transport import verify_transport
    targets = [
        ("passport", _passport_doc(), verify_passport),
        ("transport", _transport_doc(), verify_transport),
        ("machine_rwa", _machine_rwa_doc(), verify_machine_share),
        ("keydir", _keydir_doc(), verify_directory),
    ]
    per = max(10, ITERS // len(targets))
    for name, doc, verify in targets:
        _fuzz_verifier(name, doc, verify, per, stats)
    if stats["rejected"] == 0:
        raise FuzzFailure("no mutation was rejected at all - the fuzzer is not "
                          "actually corrupting anything")


def test_verifiers_survive_arbitrary_junk():
    """Not just mutations of valid documents - total garbage too."""
    from provenance.machine_rwa import verify_machine_share
    from provenance.passport import verify_passport
    from provenance.transport import verify_transport
    junk = [None, [], {}, "", 0, True, {"events": None}, {"events": [None]},
            {"events": [{"seq": "x"}]}, {"events": {}}, [{"a": 1}], {"signers": 5}]
    for _ in range(ITERS // 4 + 4):
        junk.append({"events": [{"seq": RNG.randrange(-5, 5),
                                 "sig": RNG.choice(["", "zz", None, 5]),
                                 "data": RNG.choice([None, [], "x", {}])}]})
    for verify in (verify_passport, verify_transport, verify_machine_share,
                   verify_directory):
        for j in junk:
            try:
                ok, notes = verify(j)
            except Exception as e:
                raise FuzzFailure(f"{verify.__name__} raised on junk {j!r}: "
                                  f"{type(e).__name__}: {e}") from None
            if ok:
                raise FuzzFailure(f"{verify.__name__} ACCEPTED junk {j!r}")


# -- the newer subsystems, which had no property coverage ----------------------

def test_payout_never_double_pays_under_random_replay():
    """Random leg multisets - including duplicates and reorderings, the shape that
    produced the round-1 positional-key bug - driven through random rail outcomes
    and replayed. Nothing may ever be paid twice."""
    for _ in range(max(20, ITERS // 5)):
        n = RNG.randrange(1, 7)
        accounts = [f"acct:a{RNG.randrange(3)}" for _ in range(n)]
        legs = [Leg(a, RNG.randrange(1, 5000), RNG.choice(["fab", "logi", "fee"]))
                for a in accounts]
        failing = {a for a in set(accounts) if RNG.random() < 0.3}
        rail = MockRail(fail=failing)
        eng = PayoutEngine(rail)
        job = f"job-{RNG.randrange(1000)}"
        eng.pay_legs(legs, order_id="o", job_id=job)
        first = len(rail.sent)
        paid_before = {k: r.amount_cents for k, r in eng._journal.items()
                       if r.status == PAID}
        # replay, reordered - must not re-send anything already PAID
        shuffled = list(legs)
        RNG.shuffle(shuffled)
        eng.pay_legs(shuffled, order_id="o", job_id=job)
        paid_after = {k: r.amount_cents for k, r in eng._journal.items()
                      if r.status == PAID}
        for k, amt in paid_before.items():
            if paid_after.get(k) != amt:
                raise FuzzFailure(f"payout: PAID leg {k} changed on replay")
        resent = len(rail.sent) - first
        already = len(paid_before)
        if resent > max(0, len(legs) - already) + len(legs):
            raise FuzzFailure("payout: replay re-sent already-PAID legs")
        rep = eng.reconcile_job(job, legs)
        if not rep["consistent"]:
            raise FuzzFailure(f"payout: reconciliation inconsistent: {rep}")


def test_merkle_proofs_hold_at_random_sizes():
    """test_anchor is exhaustive to 24; go wider and randomly here."""
    for _ in range(max(15, ITERS // 10)):
        n = RNG.randrange(1, 200)
        log = TransparencyLog("f")
        for i in range(n):
            log.append(f"e{i}".encode())
        root = log.root()
        i = RNG.randrange(n)
        if not verify_inclusion(leaf_hash(f"e{i}".encode()), i, n, root,
                                log.inclusion_proof(i)):
            raise FuzzFailure(f"anchor: honest inclusion proof failed (n={n}, i={i})")
        m = RNG.randrange(n + 1)
        old = TransparencyLog("f")
        for j in range(m):
            old.append(f"e{j}".encode())
        if not verify_consistency(m, old.root(), n, root, log.consistency_proof(m)):
            raise FuzzFailure(f"anchor: honest consistency proof failed ({m}->{n})")
        # a corrupted path must be refused, never crash
        bad = [bytes(RNG.randrange(256) for _ in range(32))
               for _ in range(RNG.randrange(0, 4))]
        if verify_inclusion(leaf_hash(f"e{i}".encode()), i, n, root, bad) and bad:
            raise FuzzFailure("anchor: random inclusion path was ACCEPTED")


def test_keystore_roundtrip_and_tamper_under_random_inputs():
    import tempfile
    for _ in range(max(6, ITERS // 25)):
        seed = keys.new_seed()
        pw = "".join(chr(RNG.randrange(33, 127)) for _ in range(RNG.randrange(1, 24)))
        env = keys.encrypt_seed(seed, pw)
        if keys.decrypt_seed(env, pw) != seed:
            raise FuzzFailure("keys: encrypt/decrypt round-trip failed")
        # any corruption of the envelope must be refused (never silently yield a
        # DIFFERENT key, which would sign with a key nobody knows)
        bad = dict(env)
        field = RNG.choice(["ciphertext", "tag", "salt", "nonce"])
        raw = bytearray(bytes.fromhex(bad[field]))
        raw[RNG.randrange(len(raw))] ^= 1 << RNG.randrange(8)
        bad[field] = bytes(raw).hex()
        try:
            keys.decrypt_seed(bad, pw)
            raise FuzzFailure(f"keys: accepted a corrupted {field}")
        except ValueError:
            pass
        # wrong passphrase
        try:
            keys.decrypt_seed(env, pw + "x")
            raise FuzzFailure("keys: accepted a wrong passphrase")
        except ValueError:
            pass


def test_signature_soundness_under_random_inputs():
    """The kernel property everything else rests on."""
    for _ in range(max(10, ITERS // 20)):
        seed = keys.new_seed()
        pub = crypto.publickey(seed)
        msg = bytes(RNG.randrange(256) for _ in range(RNG.randrange(0, 120)))
        sig = crypto.sign(msg, seed, pub)
        if not crypto.verify(msg, sig, pub):
            raise FuzzFailure("crypto: honest signature failed to verify")
        bad_sig = bytearray(sig)
        bad_sig[RNG.randrange(len(bad_sig))] ^= 1 << RNG.randrange(8)
        if crypto.verify(msg, bytes(bad_sig), pub):
            raise FuzzFailure("crypto: accepted a flipped signature")
        if crypto.verify(msg + b"!", sig, pub):
            raise FuzzFailure("crypto: accepted a signature over a different message")
        if crypto.verify(msg, sig, crypto.publickey(keys.new_seed())):
            raise FuzzFailure("crypto: accepted under the wrong public key")


def main() -> int:
    print(f"   fuzz seed={SEED} iters={ITERS} "
          f"(BINGO_FUZZ_SEED / BINGO_FUZZ_ITERS to control)")
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK - all {len(tests)} fuzz groups pass (seed {SEED}): every document "
          "verifier survived structure-aware mutation of valid signed documents "
          "(delete / retype / flip / negate / inflate / empty / reorder / duplicate) "
          "and arbitrary junk WITHOUT raising, and never accepted a corruption of "
          "signed bytes; payouts never double-paid across randomized replays and "
          "reorderings; Merkle inclusion/consistency held at random tree sizes up to "
          "200; the keystore refused every corrupted envelope and wrong passphrase; "
          "and Ed25519 rejected flipped signatures, altered messages, and wrong keys. "
          "Raise BINGO_FUZZ_ITERS for a deeper run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
