"""Machine RWA — finance a machine by selling shares of its future earnings.

A node operator needs $2,000 for another printer. Instead of a bank, they sell
fractional shares of that machine's *future network revenue* to a community of
backers; as the machine earns — from jobs whose fabrication is PoF-verified —
a slice of each payout streams pro-rata to the shareholders until the financing
is repaid (a revenue-share cap), after which 100% reverts to the operator.

The distinctive part (VISION §3-L4): the collateral emits real-time, verifiable
telemetry. Every dollar fed into a distribution here comes from a **settled,
proof-of-fabrication-backed** job — so unlike any off-chain revenue-share, the
income stream underwriting the instrument is itself provable. `verified_machine_
revenue` pulls exactly that from the ledger.

Same kernel as the rest of BINGO:
  * a signed, content-addressed **offering** (terms the operator can't later edit)
  * a hash-chained, Ed25519-signed **ledger** — OPEN → BUY* → EARN* — that
    replays independently: tamper / forge / reorder / oversubscription all caught
  * **atomic distribution to the cent** — each earning splits pro-rata across
    shareholders (residue → the largest holder), the rest to the operator,
    conserving exactly, and never paying investors past the repayment cap
  * **single-use earnings** — each machine-revenue event settles once; a replayed
    event_ref is rejected, so revenue can't be double-distributed

SECURITIES NOTE (interim wording; not legal advice — see SECURITIES.md at the
repo root). A machine revenue-share IS a security in the US: an investment of
money in a common enterprise, for profit (the repayment cap), from the operator's
efforts (Howey), and note-like under Reves. This module is only the primitive
underneath — it records who put in what and what the PoF-verified machine
actually paid back. It does NOT offer, solicit, or sell shares, and this docstring
is not a legal conclusion about any offering. A real raise must ship through a
compliant offering — e.g. Reg CF via a registered funding portal, or Reg D 506(c)
to verified-accredited investors — with the required disclosures, KYC/AML,
transfer restrictions, and (for secondary sales) transfer-agent / trading-venue
rules. Get securities counsel before dollar one.
"""

from __future__ import annotations

from bingo.models import canonical_json, now_iso, sha256_hex
from bingo import crypto
from .passport import Actor


def _verify(body: bytes, sig_hex: str, pub_hex: str) -> bool:
    """Verify an Ed25519 signature given hex-encoded sig + pubkey (as stored)."""
    return crypto.verify(body, bytes.fromhex(sig_hex), bytes.fromhex(pub_hex))

SCHEMA = "bingo/machine-rwa/0.1"
ZERO = "0" * 64


class MachineRwaError(Exception):
    pass


# ── the distribution rule (pure; shared by earn() and verify) ────────────────

def _distribute(holdings: dict, investor_share_bps: int, revenue_cents: int,
                cumulative_paid: int, cap_cents: int,
                cumulative_revenue_before: int | None = None) -> tuple[list, int, int]:
    """Split one machine-revenue event. Returns (legs, to_investors, to_operator).

    The investor pool is `revenue * investor_share_bps`, clamped so cumulative
    investor payout never exceeds the repayment cap. That pool splits pro-rata
    across current shareholders by shares held; the integer-floor residue goes to
    the largest holder (ties → first by account). Everything not paid to
    investors — the operator's slice, plus everything after the cap — is the
    operator's. Conserves to the cent."""
    sold = sum(holdings.values())
    if cumulative_revenue_before is None:
        # per-event pool (legacy / direct callers): bps of THIS event, capped.
        room = max(0, cap_cents - cumulative_paid)
        investor_pool = min((revenue_cents * investor_share_bps) // 10_000, room)
    else:
        # cumulative entitlement: investors are owed their bps of ALL revenue to
        # date (capped) minus what they've already been paid. Fragmenting revenue
        # into many sub-threshold events can no longer round their share to zero —
        # the entitlement accrues on the running total, not per event.
        entitlement = min(((cumulative_revenue_before + revenue_cents) * investor_share_bps)
                          // 10_000, cap_cents)
        investor_pool = max(0, entitlement - cumulative_paid)
        # HARD conservation floor: a single event can never pay investors more
        # than the cash that entered THAT event, so the operator's slice is never
        # negative and no cents are created. (Catch-up from prior sub-cent flooring
        # is at most a few cents, so this clamp only bites the pathological case.)
        investor_pool = min(investor_pool, max(0, revenue_cents))

    legs: list[dict] = []
    dist = 0
    if sold > 0 and investor_pool > 0:
        for acct in sorted(holdings):
            amt = (investor_pool * holdings[acct]) // sold
            if amt > 0:
                legs.append({"account": acct, "cents": amt})
                dist += amt
        residue = investor_pool - dist
        if residue > 0:
            if legs:
                # largest holder among those who got a leg (ties: earliest account)
                top = max(range(len(legs)),
                          key=lambda i: (holdings[legs[i]["account"]], -i))
                legs[top]["cents"] += residue
            else:
                # every holder floored to zero (a pool smaller than the holder
                # count) — the largest holder takes the whole pool, so a tiny
                # capped catch-up still pays out instead of vanishing
                top_acct = max(sorted(holdings), key=lambda a: holdings[a])
                legs.append({"account": top_acct, "cents": residue})
            dist += residue

    to_investors = dist
    to_operator = revenue_cents - to_investors
    return legs, to_investors, to_operator


# ── the instrument ───────────────────────────────────────────────────────────

class MachineShare:
    """A machine-revenue-share offering and its signed cap-table + payout ledger."""

    def __init__(self, *, machine_id: str, total_shares: int, price_cents: int,
                 investor_share_bps: int, repayment_cap_cents: int,
                 operator: Actor, ts: str | None = None):
        if total_shares <= 0 or price_cents <= 0:
            raise MachineRwaError("total_shares and price_cents must be positive")
        if not (0 < investor_share_bps <= 10_000):
            raise MachineRwaError("investor_share_bps must be in (0, 10000]")
        if repayment_cap_cents <= 0:
            raise MachineRwaError("repayment_cap_cents must be positive")
        self.machine_id = machine_id
        self.total_shares = total_shares
        self.price_cents = price_cents
        self.investor_share_bps = investor_share_bps
        self.repayment_cap_cents = repayment_cap_cents
        self.operator_id = operator.actor_id
        self.holders: dict[str, dict] = {}
        self.events: list[dict] = []
        self._emit(operator, "OPEN", {
            "machine_id": machine_id, "total_shares": total_shares,
            "price_cents": price_cents, "investor_share_bps": investor_share_bps,
            "repayment_cap_cents": repayment_cap_cents,
            "operator": operator.public()["account"],
        }, ts)

    # -- signed, hash-chained ledger --
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

    def buy(self, investor: Actor, shares: int, ts: str | None = None) -> int:
        """An investor buys `shares`, advancing `shares * price_cents` of capital
        to the operator. Rejects an oversubscription past total_shares. Returns
        the capital advanced."""
        if shares <= 0:
            raise MachineRwaError("shares must be positive")
        if self.sold_shares() + shares > self.total_shares:
            raise MachineRwaError(
                f"oversubscription: {self.sold_shares()}+{shares} > {self.total_shares}")
        capital = shares * self.price_cents
        self._emit(investor, "BUY",
                   {"buyer": investor.public()["account"], "shares": shares,
                    "capital_cents": capital}, ts)
        return capital

    def earn(self, operator: Actor, revenue_cents: int, event_ref: str,
             ts: str | None = None) -> dict:
        """Record a machine-revenue event and stream the investors' cut. Must be
        signed by the operator who opened the offering; `event_ref` must be unique
        (a replayed one is rejected — revenue settles once). Returns the EARN
        event's data (legs, to_investors, to_operator)."""
        if operator.actor_id != self.operator_id:
            raise MachineRwaError("only the operator who opened the offering may record earnings")
        if revenue_cents <= 0:
            raise MachineRwaError("revenue_cents must be positive")
        if any(e["type"] == "EARN" and e["data"]["event_ref"] == event_ref
               for e in self.events):
            raise MachineRwaError(f"earning event {event_ref!r} already recorded (double count)")
        legs, to_inv, to_op = _distribute(
            self.holdings(), self.investor_share_bps, revenue_cents,
            self.cumulative_paid(), self.repayment_cap_cents,
            cumulative_revenue_before=self._creditable_revenue())
        data = {"revenue_cents": revenue_cents, "event_ref": event_ref,
                "to_investors": to_inv, "to_operator": to_op, "legs": legs,
                "cumulative_after": self.cumulative_paid() + to_inv}
        self._emit(operator, "EARN", data, ts)
        return data

    # -- derived state (from replaying the events) --
    def holdings(self) -> dict[str, int]:
        h: dict[str, int] = {}
        for e in self.events:
            if e["type"] == "BUY":
                d = e["data"]
                h[d["buyer"]] = h.get(d["buyer"], 0) + d["shares"]
        return h

    def sold_shares(self) -> int:
        return sum(self.holdings().values())

    def capital_raised(self) -> int:
        return sum(e["data"]["capital_cents"] for e in self.events if e["type"] == "BUY")

    def cumulative_paid(self) -> int:
        return sum(e["data"]["to_investors"] for e in self.events if e["type"] == "EARN")

    def _creditable_revenue(self) -> int:
        """Revenue that counts toward investor entitlement: only revenue earned
        while there ARE shareholders. Revenue earned before anyone bought (the
        subscription window) went 100% to the operator and can't be retroactively
        claimed by later buyers."""
        total, sold = 0, 0
        for e in self.events:
            if e["type"] == "BUY":
                sold += e["data"]["shares"]
            elif e["type"] == "EARN" and sold > 0:
                total += e["data"]["revenue_cents"]
        return total

    def fully_repaid(self) -> bool:
        return self.cumulative_paid() >= self.repayment_cap_cents

    def investor_earnings(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.events:
            if e["type"] == "EARN":
                for leg in e["data"]["legs"]:
                    out[leg["account"]] = out.get(leg["account"], 0) + leg["cents"]
        return out

    def to_dict(self) -> dict:
        return {"schema": SCHEMA, "machine_id": self.machine_id,
                "total_shares": self.total_shares, "price_cents": self.price_cents,
                "investor_share_bps": self.investor_share_bps,
                "repayment_cap_cents": self.repayment_cap_cents,
                "operator": self.operator_id, "holders": self.holders,
                "events": self.events}


def _body(ev: dict) -> bytes:
    return canonical_json({k: ev[k] for k in
                           ("seq", "ts", "type", "signer", "data", "prev_hash")})


def verify_machine_share(doc: dict) -> tuple[bool, list[str]]:
    """Independently verify a machine-share instrument from the document alone:
    every event's signature + hash-chain link under its registered signer, no
    oversubscription, and every EARN's distribution recomputed and checked
    (pro-rata correct, conserves to the cent, cap never exceeded). Returns
    (ok, notes)."""
    notes: list[str] = []
    events = doc.get("events", [])
    holders = doc.get("holders", {})
    if not events:
        return False, ["no events"]

    # economic terms come from the SIGNED OPEN event, not the mutable top-level
    # fields — otherwise an attacker rewrites the terms the payouts are checked
    # against without breaking any signature.
    open_ev = events[0]
    if open_ev.get("type") != "OPEN":
        return False, ["first event must be OPEN"]
    od = open_ev.get("data", {})
    total = od.get("total_shares")
    bps = od.get("investor_share_bps")
    cap = od.get("repayment_cap_cents")
    price = od.get("price_cents")
    holdings: dict[str, int] = {}
    cumulative = 0            # cumulative paid to investors
    cumulative_revenue = 0    # cumulative machine revenue seen
    seen_refs: set = set()
    prev = ZERO

    for ev in events:
        who = ev.get("signer", "")
        rec = holders.get(who)
        if not rec:
            return False, [f"event {ev['seq']}: signer '{who}' not registered"]
        if ev["prev_hash"] != prev:
            return False, [f"event {ev['seq']}: broken hash chain"]
        body = _body(ev)
        if ev["hash"] != sha256_hex(body + ev["sig"].encode()):
            return False, [f"event {ev['seq']}: hash mismatch (tampered)"]
        try:
            if not _verify(body, ev["sig"], rec["pubkey"]):
                return False, [f"event {ev['seq']}: bad signature for '{who}'"]
        except ValueError:
            return False, [f"event {ev['seq']}: signature/key not hex"]
        prev = ev["hash"]

        d, t = ev["data"], ev["type"]
        if t == "OPEN":
            if ev["seq"] != 0:
                return False, ["OPEN must be the first event"]
            if who != doc.get("operator"):
                return False, ["OPEN not signed by the operator"]
            # the mutable top-level terms must match the signed OPEN event
            for k, signed_v in (("total_shares", total), ("investor_share_bps", bps),
                                ("repayment_cap_cents", cap), ("price_cents", price),
                                ("machine_id", od.get("machine_id"))):
                if doc.get(k) != signed_v:
                    return False, [f"top-level {k} != signed OPEN event"]
        elif t == "BUY":
            if d["shares"] <= 0:
                return False, [f"event {ev['seq']}: non-positive shares"]
            if d["capital_cents"] != d["shares"] * price:
                return False, [f"event {ev['seq']}: capital != shares * price"]
            holdings[d["buyer"]] = holdings.get(d["buyer"], 0) + d["shares"]
            if sum(holdings.values()) > total:
                return False, [f"event {ev['seq']}: oversubscription past total_shares"]
        elif t == "EARN":
            if who != doc.get("operator"):
                return False, [f"event {ev['seq']}: EARN not signed by the operator"]
            if d["event_ref"] in seen_refs:
                return False, [f"event {ev['seq']}: duplicate earning event_ref (double count)"]
            seen_refs.add(d["event_ref"])
            # revenue must be strictly positive — a negative/zero EARN would let an
            # operator net down booked revenue to starve investors (mirror earn())
            if d["revenue_cents"] <= 0:
                return False, [f"event {ev['seq']}: EARN revenue_cents must be positive"]
            legs, to_inv, to_op = _distribute(holdings, bps, d["revenue_cents"], cumulative,
                                              cap, cumulative_revenue_before=cumulative_revenue)
            if legs != d["legs"] or to_inv != d["to_investors"] or to_op != d["to_operator"]:
                return False, [f"event {ev['seq']}: distribution does not match recomputation"]
            if to_inv + to_op != d["revenue_cents"]:
                return False, [f"event {ev['seq']}: distribution does not conserve"]
            if to_op < 0 or to_inv < 0:
                return False, [f"event {ev['seq']}: negative payout slice (over-distribution)"]
            # only revenue earned while there are shareholders is creditable
            if sum(holdings.values()) > 0:
                cumulative_revenue += d["revenue_cents"]
            cumulative += to_inv
            if cumulative > cap:
                return False, [f"event {ev['seq']}: cumulative investor payout exceeds the cap"]
            if d.get("cumulative_after") != cumulative:
                return False, [f"event {ev['seq']}: cumulative_after mismatch"]
        else:
            return False, [f"event {ev['seq']}: unknown event type {t!r}"]

    return True, notes


# ── the PoF tie: only verified machine revenue may be distributed ────────────

def verified_machine_revenue(ledger, node_id: str) -> int:
    """Total revenue a machine actually earned from settled, PoF-backed jobs —
    the sum of the node's settlement legs in the ledger journal. This is the
    income stream that underwrites the instrument, and it is provable: every cent
    traces to a JOB_SETTLEMENT whose fabrication carries a proof-of-fabrication
    chain. Feed *this* into `earn`, not a number someone typed."""
    node_account = f"acct:node:{node_id}"
    total = 0
    for e in ledger.journal:
        if getattr(e, "kind", None) != "JOB_SETTLEMENT":
            continue
        for leg in e.legs:
            if leg.account == node_account:
                total += leg.amount_cents
    return total
