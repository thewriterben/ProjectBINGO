"""L4 — Settlement ledger.

Double-entry, integer cents, atomic per-job release per specs/SETTLEMENT.md.
Local prototype of what becomes stablecoin escrow + split contracts (or DGD
non-custodial escrow with partial release) — the interface is the contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .models import Job, Order, now_iso
from .settlement import (SettlementBackend, SettlementError, SettlementReceipt,
                        Leg, compute_settlement_legs, node_account,
                        NETWORK_ACCOUNT, CARRIER_ACCOUNT)


@dataclass
class JournalEntry:
    entry_id: int
    ts: str
    kind: str                 # ESCROW_FUND | JOB_SETTLEMENT | REFUND
    order_id: str
    job_id: str | None
    legs: list[Leg]
    provenance: dict = field(default_factory=dict)


class Ledger(SettlementBackend):
    """Local double-entry implementation of SettlementBackend (the demo/dev
    path). Same leg math as every other backend via compute_settlement_legs."""

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

        # shared leg math — identical across every backend (asserts conservation)
        legs = compute_settlement_legs(job)

        self.escrow[order.order_id] -= total
        for l in legs:
            self._credit(l.account, l.amount_cents)

        entry_legs = [Leg(l.account, l.amount_cents, l.memo) for l in legs]
        self._append("JOB_SETTLEMENT", order.order_id, job.job_id, entry_legs,
                     provenance={"asset_id": job.asset_id, "node_id": job.node_id,
                                 "qty": job.qty, "pof_chain_head": job.chain_head(),
                                 "royalty_assets": [l.asset_id for l in job.royalty_lines]})
        entry = self.journal[-1]
        return SettlementReceipt(ref=f"journal#{entry.entry_id}", legs=entry.legs)

    # -- reporting --------------------------------------------------------------

    def balance(self, account: str) -> int:
        return self.balances.get(account, 0)

    def escrow_remaining(self, order_id: str) -> int:
        return self.escrow.get(order_id, 0)

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


# back-compat alias (leg account helper now lives in settlement.py)
job_node_account = node_account
