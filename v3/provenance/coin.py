"""DGD promo coin — a physical bearer instrument with a $25 redeemable QR.

Each coin carries a QR that's worth $25 in DGD validation credits. That makes it
money you can photocopy, so it needs two independent defenses, and they map onto
primitives we already have:

  * AUTHENTICITY — the QR payload is an Ed25519-signed credential from the DGD
    issuer key. A counterfeit coin's QR fails verification offline; nobody needs
    to phone home to know it wasn't issued by DGD.
  * SINGLE-USE — a signature can be copied, so authenticity alone can't stop a
    photographed QR from being redeemed twice. The RedemptionRegistry retires a
    serial on first redemption and blocks every replay (a hash-chained,
    validator-signed ledger — the same double-spend guarantee as the token layer).

Each coin is also pinned to a provenance passport (design → resin print → finish)
so "is this a genuine DGD coin, and where did it come from" is answerable, not
asserted. Compact stdlib only (base64 for the QR payload; the QR *image* is drawn
by the demo with the `qrcode` lib).
"""

from __future__ import annotations

import base64
import json
import os
import secrets as _secrets
from abc import ABC, abstractmethod

from bingo.models import canonical_json, sha256_hex
from .passport import Actor

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no ambiguous 0/O/1/I

SCHEMA = "bingo/coin-credential/0.1"
ZERO = "0" * 64


class CoinError(Exception):
    pass


# --------------------------------------------------------------- credential

def new_secret(groups: int = 4, size: int = 4) -> str:
    """A human-enterable scratch-off claim code, e.g. 'K7QM-2XR9-...'. High
    entropy (5 bits/char) so it can't be guessed — only read off the coin."""
    g = ["".join(_secrets.choice(_CODE_ALPHABET) for _ in range(size))
         for _ in range(groups)]
    return "-".join(g)


def secret_commit(secret: str) -> str:
    """The public commitment printed/committed publicly; the secret itself lives
    under the scratch-off. Revealing the secret proves physical possession."""
    return sha256_hex(secret.replace("-", "").upper().encode())


def _cred_body(serial: str, passport_head: str, credit_cents: int,
               issuer: str, secret_hash: str = "") -> bytes:
    return canonical_json({"schema": SCHEMA, "serial": serial,
                           "passport_head": passport_head,
                           "credit_cents": credit_cents, "issuer": issuer,
                           "secret_hash": secret_hash})


def mint_coin(issuer: Actor, *, serial: str, passport_head: str,
              credit_cents: int = 2500, secret: str | None = None) -> dict:
    """Sign a bearer credit credential for one coin. `passport_head` pins it to
    the coin's provenance passport; the signature binds it to the DGD issuer.
    If `secret` is given (a scratch-off code), its HASH is committed in the
    signed credential — redemption then requires revealing the code, so a
    photographed QR alone can't spend the coin. The secret is NOT stored here;
    keep it to print under the coin's tamper-evident panel."""
    secret_hash = secret_commit(secret) if secret else ""
    body = _cred_body(serial, passport_head, credit_cents, issuer.actor_id, secret_hash)
    return {"schema": SCHEMA, "serial": serial, "passport_head": passport_head,
            "credit_cents": credit_cents, "issuer": issuer.actor_id,
            "secret_hash": secret_hash,
            "sig": issuer.sign(body), "pubkey": issuer.pubkey_hex}


def check_secret(cred: dict, secret: str | None) -> bool:
    """Does the revealed scratch-off code match the coin's committed hash?"""
    if not cred.get("secret_hash"):
        return True                       # coin has no scratch-off layer
    return bool(secret) and secret_commit(secret) == cred["secret_hash"]


def qr_payload(cred: dict) -> str:
    """Compact, self-contained string to encode in the coin's QR. Carries the
    signature, so it verifies offline."""
    compact = {"v": 1, "s": cred["serial"], "p": cred["passport_head"],
               "c": cred["credit_cents"], "i": cred["issuer"],
               "h": cred.get("secret_hash", ""),
               "sig": cred["sig"], "k": cred["pubkey"]}
    raw = json.dumps(compact, separators=(",", ":")).encode()
    return "DGD1:" + base64.urlsafe_b64encode(raw).decode()


def qr_url(cred: dict, base: str = "https://digitalgold.co") -> str:
    """A scannable URL for the coin's QR: opens the validation page with the
    credential in the query string, so a phone camera goes straight to redeem."""
    from urllib.parse import quote
    return base.rstrip("/") + "/redeem?c=" + quote(qr_payload(cred), safe="")


def parse_qr(payload: str) -> dict:
    if not payload.startswith("DGD1:"):
        raise CoinError("not a DGD coin QR")
    raw = base64.urlsafe_b64decode(payload[len("DGD1:"):].encode())
    c = json.loads(raw)
    return {"serial": c["s"], "passport_head": c["p"], "credit_cents": c["c"],
            "issuer": c["i"], "secret_hash": c.get("h", ""),
            "sig": c["sig"], "pubkey": c["k"]}


def verify_credential(cred: dict, trusted_issuer_pubkey: str) -> tuple[bool, str]:
    """Offline authenticity check. Verifies the signature under the TRUSTED DGD
    key (not the key the QR carries) — so swapping in a self-signed key fails."""
    from bingo import crypto
    body = _cred_body(cred["serial"], cred["passport_head"],
                      cred["credit_cents"], cred["issuer"],
                      cred.get("secret_hash", ""))
    try:
        ok = crypto.verify(body, bytes.fromhex(cred["sig"]),
                           bytes.fromhex(trusted_issuer_pubkey))
    except (ValueError, KeyError):
        return False, "malformed signature/key"
    if not ok:
        return False, "signature not from the DGD issuer key — counterfeit"
    return True, "authentic DGD credential"


# --------------------------------------------------------- validation backend

class ValidationBackend(ABC):
    """Where the redeemed $25 actually goes. The registry enforces authenticity
    and single-use; this posts the value — '$25 USDC worth of DGD to the
    receiver's account'. DGD's real account/validation system implements this;
    swapping it in changes nothing about the anti-fraud guarantees."""

    @abstractmethod
    def credit(self, account: str, cents: int, coin_serial: str, ts: str) -> dict:
        """Post the credit. Return {'ok': bool, 'ref': str}. Raise to signal a
        transient failure (the redemption stays committed and is retried)."""


class StubValidationBackend(ValidationBackend):
    """Records what it WOULD post. Marks where DGD's USDC-of-DGD crediting plugs
    in (TODO(real): call DGD's account/validation API here).

    CONTRACT: credit() MUST be idempotent on coin_serial — a real backend keys
    on the serial so the same coin can never be credited twice even if the caller
    re-drives it (e.g. after a ledger rollback). This stub models that."""

    def __init__(self):
        self.postings: list[dict] = []
        self._by_serial: dict[str, str] = {}     # coin_serial -> ref (idempotency)

    def credit(self, account: str, cents: int, coin_serial: str, ts: str) -> dict:
        if coin_serial in self._by_serial:
            return {"ok": True, "ref": self._by_serial[coin_serial], "idempotent": True}
        ref = f"stub:{coin_serial}"
        self._by_serial[coin_serial] = ref
        self.postings.append({"account": account, "cents": cents,
                              "coin_serial": coin_serial, "ts": ts, "ref": ref})
        return {"ok": True, "ref": ref}


# --------------------------------------------------------------- redemption

class RedemptionRegistry:
    """The single-use authority. Retires a coin's credit on first redemption and
    blocks every replay, in a validator-signed, hash-chained, replayable ledger.

    Production hardening:
      * `store_path` persists the ledger; it's reloaded (and re-verified) on
        start, so a restart never forgets a spent coin. The file is the source of
        truth — the single-use guarantee survives crashes.
      * `backend` (a ValidationBackend) posts the actual $25 credit. The coin is
        marked spent and persisted BEFORE crediting, so a backend hiccup can
        never double-credit; unposted credits are retried via retry_pending().
      * loading a TAMPERED ledger fails closed: mutation/forgery is caught by the
        validator signatures + hash chain, and *truncation/rollback* (deleting the
        trailing POSTED, or emptying the chain — a valid signed prefix is still a
        valid signed chain) is caught by a sidecar anti-rollback anchor that pins
        the last head+length. If an attacker can rewrite the anchor too, the
        backend's serial-keyed idempotency (see ValidationBackend) still prevents a
        real double-credit.
    """

    def __init__(self, validator: Actor, trusted_issuer_pubkey: str,
                 store_path: str | None = None, backend: "ValidationBackend | None" = None):
        self.validator = validator
        self.trusted_issuer_pubkey = trusted_issuer_pubkey
        self.store_path = store_path
        self.anchor_path = (store_path + ".anchor") if store_path else None
        self.backend = backend
        self.redeemed: dict[str, dict] = {}     # serial -> signed redemption record
        self.credits: dict[str, int] = {}       # account -> credited cents
        self.events: list[dict] = []            # signed hash-chained ledger
        self.postings: dict[str, dict] = {}     # serial -> backend posting status (unsigned)
        if store_path and os.path.exists(store_path):
            self._load()
        elif self.anchor_path and os.path.exists(self.anchor_path):
            # an anti-rollback anchor with NO store file means the ledger was
            # deleted out from under it — starting fresh here would re-redeem every
            # spent coin. Refuse: a present anchor must have its store.
            raise CoinError("redemption ledger missing but its anti-rollback anchor "
                            "exists (store deleted → rollback)")

    def _load(self):
        with open(self.store_path) as f:
            data = json.load(f)
        if data.get("validator", {}).get("pubkey") != self.validator.pubkey_hex:
            raise CoinError("ledger validator key mismatch — refusing to load")
        if data.get("trusted_issuer_pubkey") != self.trusted_issuer_pubkey:
            raise CoinError("ledger issuer key mismatch — refusing to load")
        ok, notes = verify_registry(data)
        if not ok:
            raise CoinError(f"redemption ledger failed verification (tampered?): {notes[-1]}")
        self.events = data.get("events", [])
        self.credits = {k: int(v) for k, v in data.get("credits", {}).items()}
        self.redeemed = {e["data"]["serial"]: e["data"]
                         for e in self.events if e["type"] == "REDEEM"}
        # postings are an unsigned advisory cache; keep only those backed by a
        # signed redemption, and never let them drive a credit decision (see
        # _try_post / retry_pending, which key off the SIGNED chain).
        self.postings = {s: p for s, p in data.get("postings", {}).items()
                         if s in self.redeemed}
        # anti-rollback: a validator-signed chain is still truncatable — any valid
        # PREFIX (incl. empty) of a signed chain is itself a valid signed chain, so
        # deleting the trailing POSTED (or all events) would "forget" a spent coin
        # and re-credit it. The sidecar anchor pins the last-known head+length; the
        # loaded chain must EXTEND it. (Backend idempotency on the serial is the
        # ultimate guarantee if an attacker rewrites the anchor too — see the
        # ValidationBackend contract.)
        if self.anchor_path and os.path.exists(self.anchor_path):
            with open(self.anchor_path) as f:
                anchor = json.load(f)
            alen = anchor.get("len", 0)
            if len(self.events) < alen:
                raise CoinError("redemption ledger rollback/truncation detected "
                                f"({len(self.events)} events < anchored {alen})")
            if alen > 0 and self.events[alen - 1]["hash"] != anchor.get("head"):
                raise CoinError("redemption ledger head anchor mismatch (rollback)")

    def _persist(self):
        if not self.store_path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.store_path)), exist_ok=True)
        tmp = self.store_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        os.replace(tmp, self.store_path)     # atomic — no torn writes
        # update the anti-rollback anchor AFTER the store is committed
        anchor = {"len": len(self.events),
                  "head": self.events[-1]["hash"] if self.events else ZERO}
        atmp = self.anchor_path + ".tmp"
        with open(atmp, "w") as f:
            json.dump(anchor, f)
        os.replace(atmp, self.anchor_path)

    def _emit(self, type_: str, data: dict, ts: str):
        ev = {"seq": len(self.events), "ts": ts, "type": type_,
              "data": data, "prev_hash": self.events[-1]["hash"] if self.events else ZERO}
        body = canonical_json({k: ev[k] for k in ("seq", "ts", "type", "data", "prev_hash")})
        ev["sig"] = self.validator.sign(body)
        ev["hash"] = sha256_hex(body + ev["sig"].encode())
        self.events.append(ev)
        return ev

    def _posted_serials(self) -> set:
        """Serials whose backend credit is durably confirmed — from the SIGNED
        chain, not the unsigned `postings` cache (which an attacker can edit)."""
        return {e["data"]["serial"] for e in self.events if e["type"] == "POSTED"}

    def _try_post(self, serial: str, account: str, cents: int, ts: str) -> str:
        """Credit the backend for a serial — but ONLY against a matching SIGNED
        redemption, and at most once (guarded by a signed POSTED event). An
        injected/edited unsigned posting can never cause a credit, and flipping a
        posting back to 'pending' on disk can never double-credit."""
        rec = self.redeemed.get(serial)
        if not rec or rec.get("to") != account or rec.get("credit_cents") != cents:
            raise CoinError(f"refusing to credit {serial}: no matching signed redemption")
        if serial in self._posted_serials():
            return "posted"                               # already durably posted — idempotent
        status, ref, err = "posted", None, None
        if self.backend:
            try:
                res = self.backend.credit(account, cents, serial, ts)
                ref = res.get("ref")
            except Exception as e:                        # noqa: BLE001 — record, retry later
                status, err = "pending", str(e)
        self.postings[serial] = {"serial": serial, "account": account, "cents": cents,
                                 "status": status, "ref": ref, "error": err}
        if status == "posted":
            self._emit("POSTED", {"serial": serial}, ts)  # tamper-evident: signed into the chain
        return status

    def redeem(self, cred: dict, redeemer_account: str, ts: str,
               secret: str | None = None) -> dict:
        """Validate authenticity, then the physical scratch-off code, then redeem
        $25 to the redeemer — exactly once, durably. A counterfeit fails
        authenticity; a photographed QR fails the code check; a copied code fails
        single-use even across restarts (the ledger is persisted)."""
        ok, why = verify_credential(cred, self.trusted_issuer_pubkey)
        if not ok:
            raise CoinError(f"redemption refused: {why}")
        if cred.get("secret_hash") and not check_secret(cred, secret):
            raise CoinError("wrong or missing scratch-off code — the physical coin "
                            "is required (a photo of the QR isn't enough)")
        serial = cred["serial"]
        if serial in self.redeemed:
            prior = self.redeemed[serial]
            raise CoinError(f"already redeemed at {prior['ts']} — copied/replayed QR")
        credit = int(cred["credit_cents"])
        # 1) commit single-use FIRST and persist — the coin is now durably spent
        rec = {"serial": serial, "to": redeemer_account, "credit_cents": credit, "ts": ts}
        self.redeemed[serial] = rec
        self.credits[redeemer_account] = self.credits.get(redeemer_account, 0) + credit
        self._emit("REDEEM", rec, ts)
        self._persist()
        # 2) then post the actual credit; failure leaves it for retry, never a
        #    double-credit (the spend is committed, and POSTED is signed)
        status = self._try_post(serial, redeemer_account, credit, ts)
        self._persist()
        return {**rec, "credit_status": status,
                "credit_ref": self.postings.get(serial, {}).get("ref")}

    def retry_pending(self, ts: str) -> int:
        """Re-post any credits that didn't land (backend was down). Safe to call
        repeatedly: the eligible set is derived from SIGNED redemptions minus
        SIGNED postings, so a tampered unsigned `postings` status can neither
        inject a credit nor cause a double-credit. Returns how many posted."""
        posted = 0
        already = self._posted_serials()
        for serial, rec in list(self.redeemed.items()):
            if serial in already:
                continue                                  # signed POSTED exists — never re-credit
            if self._try_post(serial, rec["to"], rec["credit_cents"], ts) == "posted":
                posted += 1
        self._persist()
        return posted

    def status(self, serial: str) -> str:
        return "REDEEMED" if serial in self.redeemed else "VALID"

    def to_dict(self) -> dict:
        return {"validator": self.validator.public(),
                "trusted_issuer_pubkey": self.trusted_issuer_pubkey,
                "redeemed": self.redeemed, "credits": self.credits,
                "events": self.events, "postings": self.postings}


def verify_registry(reg: dict) -> tuple[bool, list[str]]:
    """Independently replay the redemption ledger: every event validator-signed,
    hash-chained, no serial redeemed twice, credits equal the sum of redemptions.

    Fails CLOSED on any malformed/adversarial document: the auditor is contracted
    to return (ok, notes) for ANY input (and _load turns a False into a refusal to
    load), so a missing field or wrong type is a rejection, never a crash."""
    try:
        return _verify_registry(reg)
    except Exception as e:
        return False, [f"malformed redemption ledger: {type(e).__name__}: {e}"]


def _verify_registry(reg: dict) -> tuple[bool, list[str]]:
    from bingo import crypto
    notes: list[str] = []
    vpub = (reg.get("validator") or {}).get("pubkey")
    if not vpub:
        return False, ["no validator key"]
    seen: set[str] = set()
    posted_seen: set[str] = set()
    credited: dict[str, int] = {}
    prev = ZERO
    for ev in reg.get("events", []):
        if ev["prev_hash"] != prev:
            return False, notes + [f"event {ev['seq']}: broken hash chain"]
        body = canonical_json({k: ev[k] for k in ("seq", "ts", "type", "data", "prev_hash")})
        if ev["hash"] != sha256_hex(body + ev["sig"].encode()):
            return False, notes + [f"event {ev['seq']}: tampered"]
        try:
            if not crypto.verify(body, bytes.fromhex(ev["sig"]), bytes.fromhex(vpub)):
                return False, notes + [f"event {ev['seq']}: bad validator signature"]
        except (ValueError, KeyError):
            return False, notes + [f"event {ev['seq']}: signature not hex"]
        prev = ev["hash"]
        if ev["type"] == "REDEEM":
            s = ev["data"]["serial"]
            if s in seen:
                return False, notes + [f"event {ev['seq']}: serial {s} redeemed twice"]
            seen.add(s)
            credited[ev["data"]["to"]] = credited.get(ev["data"]["to"], 0) + ev["data"]["credit_cents"]
        elif ev["type"] == "POSTED":
            s = ev["data"]["serial"]
            if s not in seen:
                return False, notes + [f"event {ev['seq']}: POSTED for un-redeemed serial {s}"]
            if s in posted_seen:
                return False, notes + [f"event {ev['seq']}: serial {s} posted twice"]
            posted_seen.add(s)
    if credited != {k: v for k, v in reg.get("credits", {}).items() if v}:
        return False, notes + ["credited totals don't match the ledger"]
    notes.append(f"{len(seen)} coin(s) redeemed, no double-redemption; "
                 f"${sum(credited.values())/100:,.2f} in credits, all validator-signed")
    return True, notes
