"""Tokenize a claim on a real-world asset — ownership as a verifiable ledger.

Brazil already tokenizes cattle; the honest question is what a token is *backed
by*. Here a token is bound to a BINGO RWA asset, which is content-addressed to
its signed provenance passport — so the token names the exact chain of custody
it represents, pinned by the passport's chain head. You cannot mint a claim on
a cow you can't prove.

Ownership itself is a hash-chained, signed ledger, using the SAME Ed25519 +
canonical-JSON construction as the provenance passport and proof-of-fabrication:
  * ISSUE mints the total supply to the issuer (issuer-signed)
  * TRANSFER moves shares, signed by the CURRENT owner (you can only move yours)
  * REDEEM retires shares when the claim is exercised (holder-signed)
verify_token() replays the whole ledger from nothing but the document: every
signature checks under its signer's registered key, no transfer ever overdraws,
and supply is conserved to the share. Double-spend is caught by replay, not
trust.

NOT financial or legal advice, and NOT a securities offering. This is a
technical ownership-and-provenance primitive; a real issuance needs proper
legal structuring and disclosures. It tracks who holds a claim and proves what
backs it — nothing more.
"""

from __future__ import annotations

from bingo.models import canonical_json, now_iso, sha256_hex
from .passport import Actor

SCHEMA = "bingo/token/0.1"
ZERO = "0" * 64


class TokenError(Exception):
    pass


def _payees(value_split) -> list:
    """Normalize a Split | list[{account,bps}] | None into a plain payee list."""
    if value_split is None:
        return []
    if hasattr(value_split, "to_dict"):
        return [dict(p) for p in value_split.to_dict()["payees"]]
    return [dict(p) for p in value_split]


def route(amount_cents: int, payees: list) -> list:
    """Split an amount across payees by bps. Integer-floor; residue -> first
    payee, so cents are conserved exactly (same rule as bingo.settlement)."""
    legs, dist = [], 0
    for p in payees:
        amt = (amount_cents * p["bps"]) // 10_000
        legs.append({"account": p["account"], "cents": amt})
        dist += amt
    residue = amount_cents - dist
    if legs and residue:
        legs[0]["cents"] += residue
    return legs


def _sale_legs(price_cents: int, primary: bool, royalty_bps: int,
               seller_account: str, value_split: list) -> list:
    """Primary sale funds the whole value chain (proceeds -> provenance split,
    the rancher included). Secondary sale pays the seller, minus a resale
    royalty that still routes back through the provenance split — royalty at the
    point of transaction, applied to a real-world-asset claim."""
    if primary:
        return route(price_cents, value_split)
    royalty = (price_cents * royalty_bps) // 10_000
    legs = route(royalty, value_split) if royalty else []
    legs.append({"account": seller_account, "cents": price_cents - royalty})
    return legs


class AssetToken:
    """A transferable claim on a provenance-backed RWA asset."""

    def __init__(self, *, backing_asset_id: str, passport_head: str,
                 unit: str, total_supply: int, issuer: Actor,
                 value_split=None, ts: str | None = None):
        if total_supply <= 0:
            raise TokenError("total_supply must be positive")
        self.backing_asset_id = backing_asset_id
        self.passport_head = passport_head          # pins the exact provenance
        self.unit = unit                            # what ONE share represents
        self.total_supply = total_supply
        self.issuer = issuer.actor_id
        # the value-routing split from the provenance passport (rancher included);
        # embedded so sale proceeds are routable AND independently re-checkable.
        self.value_split = _payees(value_split)
        self.holders: dict[str, dict] = {}          # actor_id -> public record
        self.balances: dict[str, int] = {}          # account -> shares
        self.retired = 0
        self.events: list[dict] = []

        manifest = {"schema": SCHEMA, "backing_asset_id": backing_asset_id,
                    "passport_head": passport_head, "unit": unit,
                    "total_supply": total_supply, "issuer": issuer.actor_id}
        self.token_id = sha256_hex(canonical_json(manifest))
        self._emit(issuer, "ISSUE", {
            "to": issuer.account, "shares": total_supply,
            "backing_asset_id": backing_asset_id, "passport_head": passport_head,
            "unit": unit}, ts=ts)
        self.balances[issuer.account] = total_supply

    # -- signed, hash-chained ledger --------------------------------------

    def _emit(self, actor: Actor, type_: str, data: dict, ts: str | None = None):
        self.holders.setdefault(actor.actor_id, actor.public())
        ev = {"seq": len(self.events), "ts": ts or now_iso(), "type": type_,
              "signer": actor.actor_id, "data": data,
              "prev_hash": self.events[-1]["hash"] if self.events else ZERO}
        body = canonical_json({k: ev[k] for k in
                               ("seq", "ts", "type", "signer", "data", "prev_hash")})
        ev["sig"] = actor.sign(body)
        ev["hash"] = sha256_hex(body + ev["sig"].encode())
        self.events.append(ev)
        return ev

    def transfer(self, sender: Actor, to_account: str, shares: int,
                 ts: str | None = None):
        """Move `shares` from the sender to `to_account`. Only the current
        owner can authorize it (the ledger records the sender's signature),
        and only up to what they actually hold."""
        if shares <= 0:
            raise TokenError("shares must be positive")
        if self.balances.get(sender.account, 0) < shares:
            raise TokenError(f"insufficient balance: {sender.account} holds "
                             f"{self.balances.get(sender.account, 0)}, needs {shares}")
        self._emit(sender, "TRANSFER",
                   {"from": sender.account, "to": to_account, "shares": shares}, ts=ts)
        self.balances[sender.account] -= shares
        self.balances[to_account] = self.balances.get(to_account, 0) + shares
        return self.balances

    def sell(self, seller: Actor, buyer_account: str, shares: int,
             price_cents: int, resale_royalty_bps: int = 0, ts: str | None = None):
        """A PRICED transfer: moves shares AND settles the proceeds. If the
        issuer is selling, all proceeds route through the provenance split (the
        rancher gets paid when the claim is first sold). On a resale, the seller
        is paid, minus a royalty that routes back through the split."""
        if shares <= 0 or price_cents < 0:
            raise TokenError("shares must be positive and price non-negative")
        if self.balances.get(seller.account, 0) < shares:
            raise TokenError(f"insufficient balance: {seller.account} holds "
                             f"{self.balances.get(seller.account, 0)}, needs {shares}")
        primary = seller.actor_id == self.issuer
        if not primary and resale_royalty_bps and not self.value_split:
            raise TokenError("no value split to route a resale royalty through")
        legs = _sale_legs(price_cents, primary, resale_royalty_bps,
                          seller.account, self.value_split)
        self._emit(seller, "SALE", {
            "from": seller.account, "to": buyer_account, "shares": shares,
            "price_cents": price_cents, "primary": primary,
            "royalty_bps": (0 if primary else resale_royalty_bps), "legs": legs}, ts=ts)
        self.balances[seller.account] -= shares
        self.balances[buyer_account] = self.balances.get(buyer_account, 0) + shares
        return legs

    def redeem(self, holder: Actor, shares: int, note: str = "", ts: str | None = None):
        """Retire shares when the underlying claim is exercised (e.g. the cut
        is physically delivered). Reduces the holder's balance and total supply."""
        if shares <= 0:
            raise TokenError("shares must be positive")
        if self.balances.get(holder.account, 0) < shares:
            raise TokenError("insufficient balance to redeem")
        self._emit(holder, "REDEEM",
                   {"account": holder.account, "shares": shares, "note": note}, ts=ts)
        self.balances[holder.account] -= shares
        self.retired += shares
        return self.balances

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA, "token_id": self.token_id,
            "backing_asset_id": self.backing_asset_id,
            "passport_head": self.passport_head, "unit": self.unit,
            "total_supply": self.total_supply, "issuer": self.issuer,
            "value_split": self.value_split,
            "holders": self.holders, "events": self.events,
            "balances": {k: v for k, v in self.balances.items() if v},
            "retired": self.retired,
            "circulating": self.total_supply - self.retired,
        }


# ------------------------------------------------------------------ verify

def _body(ev: dict) -> bytes:
    return canonical_json({k: ev[k] for k in
                           ("seq", "ts", "type", "signer", "data", "prev_hash")})


def _agg(legs: list) -> dict:
    """Aggregate legs to account -> cents (order-independent, merges duplicates
    such as a seller who is also in the provenance split)."""
    out: dict[str, int] = {}
    for l in legs:
        out[l["account"]] = out.get(l["account"], 0) + l["cents"]
    return {k: v for k, v in out.items() if v}


def token_settlement(token: dict) -> dict:
    """Roll up who has been paid across ALL priced sales of this token —
    the loop closure made legible: how much the rancher (and everyone else)
    earned from token activity, on top of the physical sale."""
    total: dict[str, int] = {}
    proceeds = 0
    for ev in token.get("events", []):
        if ev["type"] != "SALE":
            continue
        proceeds += ev["data"]["price_cents"]
        for acct, cents in _agg(ev["data"].get("legs", [])).items():
            total[acct] = total.get(acct, 0) + cents
    return {"proceeds_cents": proceeds,
            "paid": dict(sorted(total.items(), key=lambda kv: -kv[1]))}


def verify_token(token: dict, backing_passport: dict | None = None) -> tuple[bool, list[str]]:
    """Independently verify a token from the document alone: signed hash-chain
    integrity, replayed balances (no overdraft, correct authorization), and
    supply conservation. If the backing passport is supplied, also confirm the
    token is pinned to that exact, verified provenance."""
    from .passport import verify_passport

    notes: list[str] = []
    events = token.get("events", [])
    holders = token.get("holders", {})
    if not events or events[0]["type"] != "ISSUE":
        return False, ["token must open with an ISSUE event"]

    supply = token.get("total_supply", 0)
    bal: dict[str, int] = {}
    retired = 0
    prev = ZERO

    for ev in events:
        who = ev.get("signer", "")
        rec = holders.get(who)
        if not rec:
            return False, notes + [f"event {ev['seq']}: signer '{who}' not registered"]
        if ev["prev_hash"] != prev:
            return False, notes + [f"event {ev['seq']}: broken hash chain"]
        body = _body(ev)
        if ev["hash"] != sha256_hex(body + ev["sig"].encode()):
            return False, notes + [f"event {ev['seq']}: hash mismatch (tampered)"]
        try:
            if not crypto_verify(body, ev["sig"], rec["pubkey"]):
                return False, notes + [f"event {ev['seq']}: bad signature for '{who}'"]
        except ValueError:
            return False, notes + [f"event {ev['seq']}: signature/key not hex"]
        prev = ev["hash"]

        d = ev["data"]
        t = ev["type"]
        if t == "ISSUE":
            if ev["seq"] != 0:
                return False, notes + ["ISSUE must be the first event"]
            if who != token.get("issuer"):
                return False, notes + ["ISSUE not signed by the issuer"]
            bal[d["to"]] = bal.get(d["to"], 0) + d["shares"]
            if d["shares"] != supply:
                return False, notes + ["ISSUE shares != total_supply"]
        elif t == "TRANSFER":
            # only the owner can move their own shares
            if d["from"] != rec["account"]:
                return False, notes + [f"event {ev['seq']}: signer is not the 'from' owner"]
            if bal.get(d["from"], 0) < d["shares"]:
                return False, notes + [f"event {ev['seq']}: overdraft (double-spend) blocked"]
            bal[d["from"]] -= d["shares"]
            bal[d["to"]] = bal.get(d["to"], 0) + d["shares"]
        elif t == "REDEEM":
            if d["account"] != rec["account"]:
                return False, notes + [f"event {ev['seq']}: redeem signer != account"]
            if bal.get(d["account"], 0) < d["shares"]:
                return False, notes + [f"event {ev['seq']}: redeem overdraft"]
            bal[d["account"]] -= d["shares"]
            retired += d["shares"]
        elif t == "SALE":
            # a priced transfer: authorize + move shares like a transfer...
            if d["from"] != rec["account"]:
                return False, notes + [f"event {ev['seq']}: signer is not the 'from' owner"]
            if bal.get(d["from"], 0) < d["shares"]:
                return False, notes + [f"event {ev['seq']}: overdraft (double-spend) blocked"]
            # ...then re-derive the settlement and reject fabricated payouts
            actual_primary = (who == token.get("issuer"))
            if bool(d.get("primary")) != actual_primary:
                return False, notes + [f"event {ev['seq']}: primary flag mismatch"]
            expected = _sale_legs(d["price_cents"], actual_primary,
                                  d.get("royalty_bps", 0), rec["account"],
                                  token.get("value_split", []))
            if _agg(d.get("legs", [])) != _agg(expected):
                return False, notes + [f"event {ev['seq']}: settlement legs don't match the split"]
            if sum(l["cents"] for l in d.get("legs", [])) != d["price_cents"]:
                return False, notes + [f"event {ev['seq']}: sale proceeds not conserved"]
            bal[d["from"]] -= d["shares"]
            bal[d["to"]] = bal.get(d["to"], 0) + d["shares"]
        else:
            return False, notes + [f"event {ev['seq']}: unknown type {t}"]

        if any(v < 0 for v in bal.values()):
            return False, notes + [f"event {ev['seq']}: negative balance"]

    if sum(bal.values()) + retired != supply:
        return False, notes + ["supply not conserved"]

    # optional: the token is only as trustworthy as its backing provenance
    if backing_passport is not None:
        ok, pnotes = verify_passport(backing_passport)
        if not ok:
            return False, notes + ["backing passport does not verify: " + pnotes[-1]]
        if backing_passport.get("chain_head") != token.get("passport_head"):
            return False, notes + ["token not pinned to this passport's chain head"]
        if backing_passport.get("subject", {}):
            notes.append("backed by verified provenance "
                         f"({backing_passport['chain_head'][:12]}…)")

    circ = supply - retired
    notes.append(f"{len(events)} ledger events, {len(holders)} holder(s); "
                 f"{circ}/{supply} shares circulating, {retired} redeemed")
    notes.append(f"replayed with no overdraft; supply conserved to the share")
    return True, notes


def crypto_verify(body: bytes, sig_hex: str, pub_hex: str) -> bool:
    from bingo import crypto
    return crypto.verify(body, bytes.fromhex(sig_hex), bytes.fromhex(pub_hex))
