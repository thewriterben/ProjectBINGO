"""L4 — Settlement ledger.

Double-entry, integer cents, atomic per-job release per specs/SETTLEMENT.md.
Local prototype of what becomes stablecoin escrow + split contracts (or DGD
non-custodial escrow with partial release) — the interface is the contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .models import Job, Order, now_iso

NETWORK_ACCOUNT = "acct:network"
CARRIER_ACCOUNT = "acct:carrier-pool"


@dataclass
class Leg:
    account: str
    amount_cents: int
    memo: str


@dataclass
class JournalEntry:
    entry_id: int
    ts: str
    kind: str                 # ESCROW_FUND | JOB_SETTLEMENT | REFUND
    order_id: str
    job_id: str | None
    legs: list[Leg]
    provenance: dict = field(default_factory=dict)


class SettlementError(Exception):
    pass


class Ledger:
    def __init__(self):
        self.balances: dict[str, int] = {}
        self.escrow: dict[str, int] = {}       # order_id -> remaining cents
        self.journal: list[JournalEntry] = []

    # -- internals -----------------------------------------------------------

    def _credit(self, account: str, cents: int):
        self.balances[account] = self.balances.get(account, 0) + cents

    def _append(self, kind: str, order_id: str, job_id: str | None,
                legs: list[Leg], provenance: dict | None = None):
        self.journal.append(JournalEntry(
            entry_id=len(self.journal) + 1, ts=now_iso(), kind=kind,
            order_id=order_id, job_id=job_id, legs=legs,
            provenance=provenance or {}))

    # -- escrow ---------------------------------------------------------------

    def fund_escrow(self, order: Order):
        """Buyer funds the full order total (via PSP/stablecoin in production)."""
        self.escrow[order.order_id] = order.total_cents
        self._append("ESCROW_FUND", order.order_id, None,
                     [Leg(f"escrow:{order.order_id}", order.total_cents,
                          f"buyer {order.buyer} funds order")])

    # -- atomic per-job settlement ---------------------------------------------

    def settle_job(self, order: Order, job: Job) -> JournalEntry:
        """One atomic release on DELIVERY_CONFIRMED. Invariants asserted:
        legs sum exactly to the escrow decrement; each royalty line flows only
        through its own asset's frozen effective split — a design, a process
        package, and a derivative each reach their own payees in this single
        atomic transaction."""
        total = job.job_total_cents
        if self.escrow.get(order.order_id, 0) < total:
            raise SettlementError(
                f"escrow underfunded for {job.job_id}: "
                f"{self.escrow.get(order.order_id, 0)} < {total}")

        node_account = job_node_account(job)
        legs: list[Leg] = [
            Leg(node_account, job.fabrication_cents + job.material_cents + job.energy_cents,
                "fabrication + material + energy"),
            Leg(CARRIER_ACCOUNT, job.logistics_cents, "logistics"),
        ]

        # Royalty legs, PER ASSET: each line routes through its own split.
        # This is the ONLY code path that pays fabrication, and it cannot pay
        # fabrication without paying every registered royalty line.
        for line in job.royalty_lines:
            tag = line.asset_id[:8]
            distributed = 0
            line_legs: list[Leg] = []
            for p in line.payees:
                amt = (line.cents * p.bps) // 10_000
                if amt > 0:
                    line_legs.append(Leg(p.account, amt, f"royalty {p.bps}bps [{tag}]"))
                    distributed += amt
            residue = line.cents - distributed             # integer-floor residue
            if line_legs and residue > 0:
                line_legs[0].amount_cents += residue       # deterministic: first payee
            legs.extend(line_legs)

        legs.append(Leg(NETWORK_ACCOUNT, job.fee_cents, "network fee (3%)"))

        # invariant 1: conservation of cents
        assert sum(l.amount_cents for l in legs) == total, "settlement legs != escrow decrement"

        self.escrow[order.order_id] -= total
        for l in legs:
            self._credit(l.account, l.amount_cents)

        entry_legs = [Leg(l.account, l.amount_cents, l.memo) for l in legs]
        self._append("JOB_SETTLEMENT", order.order_id, job.job_id, entry_legs,
                     provenance={"asset_id": job.asset_id, "node_id": job.node_id,
                                 "qty": job.qty, "pof_chain_head": job.chain_head(),
                                 "royalty_assets": [l.asset_id for l in job.royalty_lines]})
        return self.journal[-1]

    # -- reporting --------------------------------------------------------------

    def balance(self, account: str) -> int:
        return self.balances.get(account, 0)

    def to_json(self) -> str:
        return json.dumps({
            "balances": self.balances,
            "escrow": self.escrow,
            "journal": [{
                "entry_id": e.entry_id, "ts": e.ts, "kind": e.kind,
                "order_id": e.order_id, "job_id": e.job_id,
                "legs": [{"account": l.account, "cents": l.amount_cents, "memo": l.memo}
                         for l in e.legs],
                "provenance": e.provenance,
            } for e in self.journal],
        }, indent=2)


def job_node_account(job: Job) -> str:
    return f"acct:node:{job.node_id}"
