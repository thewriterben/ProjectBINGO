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
import secrets as _secrets

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


# --------------------------------------------------------------- redemption

class RedemptionRegistry:
    """The single-use authority. Retires a coin's credit on first redemption and
    blocks every replay, in a validator-signed, hash-chained, replayable ledger."""

    def __init__(self, validator: Actor, trusted_issuer_pubkey: str):
        self.validator = validator
        self.trusted_issuer_pubkey = trusted_issuer_pubkey
        self.redeemed: dict[str, dict] = {}     # serial -> redemption record
        self.credits: dict[str, int] = {}       # account -> credited cents
        self.events: list[dict] = []            # signed hash-chained ledger

    def _emit(self, type_: str, data: dict, ts: str):
        ev = {"seq": len(self.events), "ts": ts, "type": type_,
              "data": data, "prev_hash": self.events[-1]["hash"] if self.events else ZERO}
        body = canonical_json({k: ev[k] for k in ("seq", "ts", "type", "data", "prev_hash")})
        ev["sig"] = self.validator.sign(body)
        ev["hash"] = sha256_hex(body + ev["sig"].encode())
        self.events.append(ev)
        return ev

    def redeem(self, cred: dict, redeemer_account: str, ts: str,
               secret: str | None = None) -> dict:
        """Validate authenticity, then the physical scratch-off code, then redeem
        $25 to the redeemer — exactly once. A counterfeit fails authenticity; a
        photographed QR fails the code check; a copied code fails single-use."""
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
        rec = {"serial": serial, "to": redeemer_account, "credit_cents": credit, "ts": ts}
        self.redeemed[serial] = rec
        self.credits[redeemer_account] = self.credits.get(redeemer_account, 0) + credit
        self._emit("REDEEM", rec, ts)
        return rec

    def status(self, serial: str) -> str:
        return "REDEEMED" if serial in self.redeemed else "VALID"

    def to_dict(self) -> dict:
        return {"validator": self.validator.public(),
                "trusted_issuer_pubkey": self.trusted_issuer_pubkey,
                "redeemed": self.redeemed, "credits": self.credits,
                "events": self.events}


def verify_registry(reg: dict) -> tuple[bool, list[str]]:
    """Independently replay the redemption ledger: every event validator-signed,
    hash-chained, no serial redeemed twice, credits equal the sum of redemptions."""
    from bingo import crypto
    notes: list[str] = []
    vpub = (reg.get("validator") or {}).get("pubkey")
    if not vpub:
        return False, ["no validator key"]
    seen: set[str] = set()
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
    if credited != {k: v for k, v in reg.get("credits", {}).items() if v}:
        return False, notes + ["credited totals don't match the ledger"]
    notes.append(f"{len(seen)} coin(s) redeemed, no double-redemption; "
                 f"${sum(credited.values())/100:,.2f} in credits, all validator-signed")
    return True, notes
