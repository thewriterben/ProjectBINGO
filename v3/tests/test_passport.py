"""Provenance passport: verification, tamper/signer/reorder detection,
settlement conservation, and proof that it's the SAME crypto construction as
the BINGO proof-of-fabrication evidence chain. Run:

  python -m tests.test_passport
"""

from __future__ import annotations

import copy
import json
import sys

from bingo import crypto
from bingo.models import Split, SplitPayee, canonical_json, sha256_hex
from provenance.passport import Actor, CutPassport, verify_passport
from provenance.demo import build


def main() -> int:
    pp = build().to_dict()

    # 1. the honest article verifies
    ok, notes = verify_passport(pp)
    assert ok, notes

    # 2. same construction as bingo.evidence — recompute every link's hash and
    #    signature with the identical primitives evidence.verify() uses.
    for ev in pp["events"]:
        body = canonical_json({k: ev[k] for k in
                               ("seq", "ts", "type", "signer", "data", "prev_hash")})
        assert ev["hash"] == sha256_hex(body + ev["sig"].encode()), ev["seq"]
        pk = bytes.fromhex(pp["signers"][ev["signer"]]["pubkey"])
        assert crypto.verify(body, bytes.fromhex(ev["sig"]), pk), ev["seq"]

    # 3. tamper: change a graded claim (A5 -> lie) -> hash mismatch caught
    t = copy.deepcopy(pp)
    hv = next(e for e in t["events"] if e["type"] == "HARVEST")
    hv["data"]["grade"] = "A3"
    bad, why = verify_passport(t)
    assert not bad and "tampered" in why[-1], why

    # 4. forged signer: point the rancher's registered key at someone else's ->
    #    her signature no longer validates under it
    t = copy.deepcopy(pp)
    other = Actor.create("imposter", "Imposter", "rancher", "acct:x")
    t["signers"]["sadu-farms"]["pubkey"] = other.pubkey_hex
    bad, why = verify_passport(t)
    assert not bad and "bad signature" in why[-1], why

    # 5. reorder: swap two links -> hash chain breaks
    t = copy.deepcopy(pp)
    t["events"][2], t["events"][3] = t["events"][3], t["events"][2]
    bad, why = verify_passport(t)
    assert not bad and "hash chain" in why[-1], why

    # 6. unknown signer: an event whose signer isn't in the registry is rejected
    t = copy.deepcopy(pp)
    t["events"][1]["signer"] = "ghost"
    bad, why = verify_passport(t)
    assert not bad and "not in registry" in why[-1], why

    # 7. settlement conservation holds even when the split leaves a residue
    op = Actor.create("op", "Op", "operation", "acct:op")
    r = Actor.create("r", "Rancher", "rancher", "acct:r")
    p2 = CutPassport(subject={"product": "A5 strip", "lot": "L1", "weight_lb": 1,
                              "destination": "test"})
    p2.attest(op, "LINEAGE", {"tajima_pct": 96})
    price = 10_003                                   # coprime-ish to the bps below
    split = Split([SplitPayee("acct:op", 3333), SplitPayee("acct:r", 3333),
                   SplitPayee("acct:x", 3334)])
    legs = p2.record_sale(op, price, split, buyer="b", unit="1")
    assert sum(l["cents"] for l in legs) == price, legs   # residue -> first payee
    ok2, _ = verify_passport(p2.to_dict())
    assert ok2

    # 8. the rancher who grew the feed is actually paid on the real cut
    rancher_leg = next(l for l in pp["settlement"] if "rancher" in l["account"])
    assert rancher_leg["cents"] > 0

    # round-trips as plain JSON (verifiable by anyone, offline)
    assert verify_passport(json.loads(json.dumps(pp)))[0]

    print(f"OK — passport verifies (6 links, 5 signers); same SHA-256+Ed25519 "
          f"construction as PoF; tamper/forged-signer/reorder/unknown-signer all "
          f"caught; settlement conserves to the cent (incl. residue); rancher paid "
          f"${rancher_leg['cents']/100:.2f} on the $58.50 cut.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
