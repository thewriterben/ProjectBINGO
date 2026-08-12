"""An audit log an intruder cannot quietly edit.

The production-gap memo asks for "structured logging" under operational
maturity. Plain structured logging - JSON lines with a timestamp - answers *what
happened* to someone who trusts the file. It answers nothing at all to someone
asking the question that actually matters after an incident:

    is this file still telling me what happened, or did whoever got in
    delete the four lines about themselves?

A log that the attacker can edit is not evidence. It is a story.

BINGO already has the tool for this and uses it everywhere else: a hash-chained,
optionally signed event log, verifiable document-only by a stranger with nothing
installed. The same grammar as a fabrication passport or a custody chain, pointed
at the node's own behaviour. Deleting a record, editing one, reordering two, or
splicing in a record from another log all break the chain and are **detected**,
not merely disapproved of.

What is recorded:

  * every HTTP request - method, path, status, client, latency, auth outcome
  * every payout - the idempotency key, amount, destination account, result
  * process lifecycle, so a gap in the record has an explanation or doesn't

What is **never** recorded, enforced by `_redact` and by a test that greps real
log output for real secrets: bearer tokens, key seeds, passphrases, coin scratch
codes, `Authorization` headers. An audit log is a file people copy around; it is
the last place a credential should end up. The most common way a security
control becomes a vulnerability is by logging what it was protecting.

Honest limits, stated up front rather than in a footnote:

  * **Append-and-chain is a read-modify-write.** Computing the next record's
    `prev` means reading the current head. Under `JsonStore` two processes can
    read the same head and fork the chain. That is *detected* by `verify_audit`
    rather than silent - but detected-corruption is still corruption. Use the
    SQLite backend on a node with more than one writer; `store.transaction()`
    then makes read-head-and-append atomic.
  * **Local storage means local deletion.** Someone with root can delete the
    whole file. The chain proves nothing was *edited*; it cannot prove nothing
    was *removed wholesale*. That is what `bingo/anchor.py` is for - anchoring
    the head externally turns "the log is gone" into "the log is gone and the
    anchor says it existed". `anchor_head()` is the seam; running a log operator
    is still the unsolved organizational half.
  * **Signing is optional.** Unsigned, the chain is tamper-*evident* to anyone
    holding an earlier copy of the head. Signed, a third party can verify it cold.

  python -m bingo.audit --self-test
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import dataclass

from . import store as _store
from .models import canonical_json, sha256_hex

__all__ = ["AuditLog", "verify_audit", "REDACTED", "SENSITIVE_KEYS"]

REDACTED = "[redacted]"
GENESIS = "0" * 64

#: Matched case-insensitively as a SUBSTRING of the key, so `api_token`,
#: `X-Auth-Token` and `tokenValue` are all caught. Biased toward redaction: the
#: cost of blanking something harmless is a less useful log line; the cost of
#: missing one is a credential in a file people email each other.
#:
#: Biased, though, is not indiscriminate. A bare `"auth"` was in this list and
#: was removed: it matched `authenticated`, silently blanking the field that
#: records whether a request passed authentication. That is a *result*, not a
#: credential, and redacting it bought nothing while quietly destroying the
#: signal an operator would use to count failed intrusions. Over-broad
#: redaction has its own failure mode - a log that hides the answer - so the
#: entries here name credentials rather than topics.
SENSITIVE_KEYS = ("token", "secret", "password", "passphrase", "seed",
                  "private", "authorization", "cookie", "scratch",
                  "credential", "api_key", "apikey", "signature")

MAX_FIELD = 512


def _redact(obj, _depth: int = 0):
    """Walk a value and blank anything whose key looks sensitive.

    Fails toward redaction: an unrecognised type is stringified and truncated
    rather than embedded whole, and depth is capped so a hostile nested body
    cannot make the audit writer the expensive part of a request.
    """
    if _depth > 6:
        return "[too deep]"
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            ks = str(k)
            if any(s in ks.lower() for s in SENSITIVE_KEYS):
                out[ks] = REDACTED
            else:
                out[ks] = _redact(v, _depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [_redact(v, _depth + 1) for v in obj[:50]]
    if isinstance(obj, (int, float, bool)) or obj is None:
        return obj
    s = obj if isinstance(obj, str) else repr(obj)
    return s if len(s) <= MAX_FIELD else s[:MAX_FIELD] + "...[truncated]"


def _body(rec: dict) -> dict:
    """Exactly the fields the hash and signature cover. Anything outside this is
    NOT bound, so it must never be anything a reader would rely on.

    `log` is in here for a reason found by the splice test. A hash chain
    identifies a *sequence of contents*, not the log that produced it: two nodes
    that recorded the same events in the same order build byte-identical chains,
    and a record lifted from one into the other is then undetectable - there is
    genuinely nothing to detect. Carrying a per-log id inside the signed body
    binds every record to its own chain, so a spliced record is caught even when
    its content is identical."""
    return {"log": rec["log"], "seq": rec["seq"], "ts": rec["ts"],
            "kind": rec["kind"], "actor": rec["actor"], "data": rec["data"],
            "prev": rec["prev"]}


def record_hash(rec: dict) -> str:
    return sha256_hex(canonical_json(_body(rec)))


# -- the log -------------------------------------------------------------------

class AuditLog:
    """Append-only, hash-chained, optionally signed.

    Backed by the storage seam, so `$BINGO_STORE=sqlite` makes the append
    atomic against other processes along with the rest of the node's state.
    """

    def __init__(self, base: str | None = None, *, store=None, signer=None,
                 clock=None, log_id: str | None = None):
        self._own = store is None
        self._store = store if store is not None else _store.node_store(
            base or os.path.join("out", "audit"))
        self._signer = signer
        self._log_id = log_id
        self._clock = clock or (lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                      time.gmtime()))
        self._lock = threading.Lock()
        # per-instance: a mutable class attribute would silently pool every
        # log's failures into one shared list
        self.errors: list[str] = []

    # -- writing --
    def append(self, kind: str, *, actor: str = "-", **data) -> dict:
        """Add one record. Never raises into the caller.

        Deliberate: an audit write must not be able to fail a payout or turn a
        200 into a 500. A log that can break the thing it observes gets disabled
        by the first person it inconveniences. Failures are reported through
        `self.errors` and by the gap the sequence numbers leave behind.
        """
        try:
            with self._lock, self._store.transaction():
                head = self._head_locked()
                seq = 0 if head is None else head["seq"] + 1
                prev = GENESIS if head is None else head["hash"]
                # minted once at genesis and carried forward, so every record is
                # bound to THIS log. See _body().
                log_id = (head["log"] if head is not None
                          else (self._log_id or os.urandom(8).hex()))
                rec = {"log": log_id, "seq": seq, "ts": self._clock(),
                       "kind": str(kind), "actor": str(actor),
                       "data": _redact(data), "prev": prev}
                rec["hash"] = record_hash(rec)
                if self._signer is not None:
                    rec["signer"] = self._signer.public_key().hex()
                    rec["sig"] = self._signer.sign(
                        canonical_json(_body(rec))).hex()
                self._store.put(f"{seq:012d}", rec)
                return rec
        except Exception as e:                    # noqa: BLE001 - see docstring
            self.errors.append(f"{type(e).__name__}: {e}")
            return {}

    # -- reading --
    def _head_locked(self) -> dict | None:
        recs = self.records()
        return recs[-1] if recs else None

    def records(self) -> list[dict]:
        return [v for _k, v in sorted(self._store.items())]

    def head(self) -> dict | None:
        with self._lock:
            return self._head_locked()

    def head_hash(self) -> str:
        h = self.head()
        return h["hash"] if h else GENESIS

    def log_id(self) -> str | None:
        h = self.head()
        return h["log"] if h else self._log_id

    def verify(self) -> tuple[bool, list[str]]:
        return verify_audit(self.records())

    def export_jsonl(self, path: str) -> str:
        """Ship the log somewhere else. One record per line, in order, exactly
        the bytes a third party needs to run `verify_audit` themselves."""
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in self.records():
                f.write(json.dumps(r, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        _store.retry_transient_io(lambda: os.replace(tmp, path))
        return path

    def anchor_head(self, anchor_service, key: str = "audit") -> dict | None:
        """Publish the current head to an external transparency log.

        The chain proves nothing was *edited*. It cannot prove nothing was
        *deleted wholesale* - someone with root can remove the file. Anchoring
        turns that into a detectable claim: the log is gone AND the anchor says
        it existed at this length. See `bingo/anchor.py`."""
        h = self.head()
        if h is None or anchor_service is None:
            return None
        return anchor_service.anchor(key, {"head": h["hash"], "len": h["seq"] + 1})

    def close(self) -> None:
        if self._own:
            self._store.close()

    def __enter__(self):
        return self

    def __exit__(self, *e):
        self.close()


# -- the verifier --------------------------------------------------------------

def verify_audit(records, *, expect_pubkey_hex: str | None = None,
                 expect_log_id: str | None = None) -> tuple[bool, list[str]]:
    """Fail-closed, like every other verifier in this codebase: returns
    `(ok, notes)` on ANY input, never raises. Hostile input is the normal case
    for a file that survived an incident.
    """
    notes: list[str] = []
    try:
        if not isinstance(records, list):
            return False, ["audit log is not a list of records"]
        if not records:
            return True, ["empty audit log (nothing to verify)"]

        prev_hash = GENESIS
        for i, rec in enumerate(records):
            if not isinstance(rec, dict):
                return False, notes + [f"record {i} is not an object"]
            for field in ("log", "seq", "ts", "kind", "actor", "data", "prev",
                          "hash"):
                if field not in rec:
                    return False, notes + [f"record {i} missing {field!r}"]
            if not isinstance(rec["seq"], int) or isinstance(rec["seq"], bool):
                return False, notes + [f"record {i} has a non-integer seq"]
            if rec["log"] != records[0]["log"]:
                return False, notes + [
                    f"record {i} belongs to log {str(rec['log'])[:16]}..., not "
                    f"{str(records[0]['log'])[:16]}... - a record from another "
                    f"log was spliced in"]
            if expect_log_id is not None and rec["log"] != expect_log_id:
                return False, notes + [
                    f"record {i} is from log {str(rec['log'])[:16]}..., not the "
                    f"expected one"]
            if rec["seq"] != i:
                return False, notes + [
                    f"record {i} claims seq {rec['seq']} - records are missing, "
                    f"reordered, or spliced"]
            if rec["prev"] != prev_hash:
                return False, notes + [
                    f"record {i} does not follow record {i - 1} "
                    f"(prev != previous hash) - the chain is cut or forked"]
            try:
                want = record_hash(rec)
            except (TypeError, ValueError) as e:
                return False, notes + [f"record {i} is not hashable: {e}"]
            if rec["hash"] != want:
                return False, notes + [
                    f"record {i} hash does not match its contents - it was "
                    f"edited after it was written"]

            # a signature, if PRESENT, must be right - and if a pubkey is
            # expected, it must be present. Binding a field only when it happens
            # to be there is not a binding; that lesson cost this codebase
            # round 8.
            has_sig = "sig" in rec or "signer" in rec
            if expect_pubkey_hex is not None and not has_sig:
                return False, notes + [f"record {i} is unsigned but a signing "
                                       f"key was required"]
            if has_sig:
                from . import crypto
                sig, signer = rec.get("sig"), rec.get("signer")
                if not isinstance(sig, str) or not isinstance(signer, str):
                    return False, notes + [f"record {i} has a malformed signature"]
                if expect_pubkey_hex is not None and signer != expect_pubkey_hex:
                    return False, notes + [
                        f"record {i} is signed by {signer[:16]}..., not the "
                        f"expected key"]
                try:
                    ok = crypto.verify(canonical_json(_body(rec)),
                                       bytes.fromhex(sig), bytes.fromhex(signer))
                except (ValueError, TypeError):
                    return False, notes + [f"record {i} signature is not valid hex"]
                if not ok:
                    return False, notes + [f"record {i} signature does not verify"]
            prev_hash = rec["hash"]

        signed = sum(1 for r in records if "sig" in r)
        notes.append(f"{len(records)} records, chain intact, log "
                     f"{str(records[0]['log'])[:12]}..., head "
                     f"{prev_hash[:16]}..., {signed} signed")
        return True, notes
    except Exception as e:                        # noqa: BLE001 - fail closed
        return False, notes + [f"audit log failed to verify: {type(e).__name__}"]


# -- self-test -----------------------------------------------------------------

def _self_test() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        log = AuditLog(os.path.join(d, "audit"))
        for i in range(5):
            log.append("test.event", actor="acct:ben", n=i,
                       api_token="sk_live_do_not_log_me")
        ok, notes = log.verify()
        assert ok, notes
        assert REDACTED in json.dumps(log.records())
        assert "sk_live" not in json.dumps(log.records())
        recs = log.records()
        recs[2]["data"]["n"] = 99
        bad, why = verify_audit(recs)
        assert not bad and "edited after it was written" in why[-1]
        log.close()
    print("OK - audit self-test passes: 5 records chain and verify, a secret "
          "passed straight in is redacted, and editing one record in place is "
          "detected.")
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m bingo.audit")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--verify", metavar="JSONL",
                    help="verify an exported audit log")
    a = ap.parse_args(argv)
    if a.self_test:
        return _self_test()
    if a.verify:
        with open(a.verify, encoding="utf-8") as f:
            recs = [json.loads(l) for l in f if l.strip()]
        ok, notes = verify_audit(recs)
        print(("OK   " if ok else "FAIL ") + "; ".join(notes))
        return 0 if ok else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
