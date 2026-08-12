"""Persist and independently verify proof-of-fabrication chains.

The whole point of Ed25519 over HMAC is that a THIRD PARTY can verify a job
happened, holding nothing but the evidence file and a public key. This module
serializes a job's signed chain to disk and verifies one from disk using only
stdlib + bingo.crypto — no node, no agent, no secret. `bingo/verify.py` is the
CLI over it.
"""

from __future__ import annotations

import json
import os

from . import crypto, store
from .models import Job, canonical_json, sha256_hex


def to_dict(job: Job, node_pubkey_hex: str) -> dict:
    return {
        "schema": "bingo/evidence/0.1",
        "job_id": job.job_id,
        "order_id": job.order_id,
        "asset_id": job.asset_id,
        "node_id": job.node_id,
        "node_pubkey": node_pubkey_hex,
        "qty": job.qty,
        "royalty_assets": [l.asset_id for l in job.royalty_lines],
        "events": [
            {"seq": e.seq, "ts": e.ts, "type": e.type, "data": e.data,
             "prev_hash": e.prev_hash, "sig": e.sig, "hash": e.hash}
            for e in job.evidence
        ],
    }


def save(job: Job, node_pubkey_hex: str, out_dir: str) -> str:
    """Write-once artifact, so a `Store` would be the wrong shape - but "written
    once" is not "safe to write carelessly". A bare `json.dump` truncates the
    destination first, and this file is the evidence a payout is justified by.
    `atomic_write_json` is the floor: temp file, fsync, atomic rename."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{job.job_id}.json")
    return store.atomic_write_json(path, to_dict(job, node_pubkey_hex))


def load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _event_body(ev: dict) -> dict:
    # must match EvidenceEvent.body() exactly
    return {"seq": ev["seq"], "ts": ev["ts"], "type": ev["type"],
            "data": ev["data"], "prev_hash": ev["prev_hash"]}


def verify(evidence: dict, expected_pubkey_hex: str | None = None) -> tuple[bool, list[str]]:
    """Independently verify a persisted chain. Returns (ok, notes).
    Uses the pubkey embedded in JOB_ACCEPTED unless one is passed; if both are
    present they must match. Checks: hash-link continuity, per-event hash
    integrity, and ed25519 signature under the node's key.

    Fails CLOSED on any malformed/adversarial document: a third party (and the
    shipped `python -m bingo.verify` directory scan) runs this on untrusted JSON,
    so a missing field or wrong type is a rejection, not an exception that aborts
    the batch."""
    try:
        return _verify(evidence, expected_pubkey_hex)
    except Exception as e:
        return False, [f"malformed evidence document: {type(e).__name__}: {e}"]


def _verify(evidence: dict, expected_pubkey_hex: str | None = None) -> tuple[bool, list[str]]:
    notes: list[str] = []
    events = evidence.get("events", [])
    if not events:
        return False, ["no events"]

    # resolve pubkey: embedded (self-describing) vs supplied
    embedded = evidence.get("node_pubkey", "")
    for ev in events:
        if ev["type"] == "JOB_ACCEPTED":
            embedded = ev["data"].get("node_pubkey", embedded)
            break
    pubkey_hex = expected_pubkey_hex or embedded
    if not pubkey_hex:
        return False, ["no public key available (not embedded, none supplied)"]
    if expected_pubkey_hex and embedded and expected_pubkey_hex != embedded:
        return False, [f"supplied key != embedded key ({expected_pubkey_hex[:12]}… vs {embedded[:12]}…)"]
    try:
        pk = bytes.fromhex(pubkey_hex)
    except ValueError:
        return False, ["public key is not valid hex"]

    prev = "0" * 64
    for ev in events:
        if ev["prev_hash"] != prev:
            return False, notes + [f"event {ev['seq']}: broken hash chain"]
        body = canonical_json(_event_body(ev))
        if ev["hash"] != sha256_hex(body + ev["sig"].encode()):
            return False, notes + [f"event {ev['seq']}: hash mismatch (tampered)"]
        try:
            if not crypto.verify(body, bytes.fromhex(ev["sig"]), pk):
                return False, notes + [f"event {ev['seq']}: bad signature"]
        except ValueError:
            return False, notes + [f"event {ev['seq']}: signature not hex"]
        prev = ev["hash"]

    # bind top-level job identity to the SIGNED JOB_ACCEPTED event — otherwise the
    # unsigned metadata (asset_id/order_id/qty/job_id) can be relabeled, or another
    # node's genuine events spliced into a fabricated job record, and still verify.
    # these fields are REQUIRED-present in the signed JOB_ACCEPTED and bound
    # UNCONDITIONALLY — checking them "if present" let a node omit qty (or any
    # field) to skip its binding/completeness check and be attested for 0 units.
    ja = next((e for e in events if e["type"] == "JOB_ACCEPTED"), None)
    jd = ja.get("data", {}) if ja else {}
    required = ("job_id", "order_id", "asset_id", "node_id", "qty", "royalty_assets")
    if not ja or any(k not in jd for k in required):
        return False, notes + ["no fully-bound job identity (JOB_ACCEPTED must "
                               "carry job_id/order_id/asset_id/node_id/qty/"
                               "royalty_assets) — cannot attribute this chain to a job"]
    for k in required:
        if evidence.get(k) != jd[k]:
            return False, notes + [f"top-level {k} != signed JOB_ACCEPTED "
                                   f"(job identity forged/relabeled)"]
    # the chain must actually EVIDENCE the signed quantity — a chain truncated
    # short of its units (or with none at all) would otherwise settle in full
    # for work never done (proof-of-fabrication soundness / conservation)
    completed = sum(1 for e in events if e["type"] == "UNIT_COMPLETE")
    if completed != jd["qty"]:
        return False, notes + [f"unit evidence incomplete: {completed} "
                               f"UNIT_COMPLETE event(s) for a signed qty of {jd['qty']}"]

    types = [e["type"] for e in events]
    units = types.count("UNIT_COMPLETE")
    notes.append(f"{len(events)} events, {units} unit(s) complete, "
                 f"chain head {events[-1]['hash'][:16]}…")
    notes.append(f"signed by {pubkey_hex[:16]}… (verified)")
    return True, notes
