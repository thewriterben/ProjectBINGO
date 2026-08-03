"""L4 — Settlement backend interface + the shared leg computation.

The orchestrator settles through a `SettlementBackend`. The local double-entry
`Ledger` (ledger.py) is one implementation; `StripeConnectStub` is the shape
of the real-money path (PSP holds + transfers). Swapping backends requires
ZERO orchestration change — that is the whole point of this seam, and the path
from demo-cents to regulated stablecoin/fiat settlement.

The royalty-routing + leg math lives here once, so every backend splits money
identically: node + carrier + per-asset royalty lines + network fee, summing
exactly to the job total. See specs/SETTLEMENT.md and specs/SETTLEMENT-ADAPTER.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .models import Job, Order

NETWORK_ACCOUNT = "acct:network"
CARRIER_ACCOUNT = "acct:carrier-pool"


@dataclass
class Leg:
    account: str
    amount_cents: int
    memo: str


@dataclass
class SettlementReceipt:
    """What every backend returns from settle_job — a reference the caller can
    log and the legs that moved, regardless of the underlying rail."""
    ref: str
    legs: list


def node_account(job: Job) -> str:
    return f"acct:node:{job.node_id}"


def compute_settlement_legs(job: Job) -> list[Leg]:
    """Pure: the exact split of a job's total. Every backend uses this, so
    the money moves the same whether it's a local ledger or a real PSP.
    Each royalty line routes through its OWN asset's split; integer-floor
    residue per line goes to that line's first payee (deterministic)."""
    legs: list[Leg] = [
        Leg(node_account(job),
            job.fabrication_cents + job.material_cents + job.energy_cents,
            "fabrication + material + energy"),
        Leg(CARRIER_ACCOUNT, job.logistics_cents, "logistics"),
    ]
    for line in job.royalty_lines:
        tag = line.asset_id[:8]
        distributed = 0
        line_legs: list[Leg] = []
        for p in line.payees:
            amt = (line.cents * p.bps) // 10_000
            if amt > 0:
                line_legs.append(Leg(p.account, amt, f"royalty {p.bps}bps [{tag}]"))
                distributed += amt
        residue = line.cents - distributed
        if line_legs and residue > 0:
            line_legs[0].amount_cents += residue
        legs.extend(line_legs)
    legs.append(Leg(NETWORK_ACCOUNT, job.fee_cents, "network fee (3%)"))

    total = sum(l.amount_cents for l in legs)
    assert total == job.job_total_cents, \
        f"legs {total} != job total {job.job_total_cents}"
    return legs


class SettlementError(Exception):
    pass


class SettlementBackend(ABC):
    """The contract every settlement implementation honors."""

    @abstractmethod
    def fund_escrow(self, order: Order) -> None: ...

    @abstractmethod
    def settle_job(self, order: Order, job: Job): ...

    @abstractmethod
    def balance(self, account: str) -> int: ...

    @abstractmethod
    def escrow_remaining(self, order_id: str) -> int: ...

    @abstractmethod
    def to_json(self) -> str: ...


# --------------------------------------------------------------------------
# Real-money path, stubbed. Same interface, same leg math; instead of moving
# ledger balances it records the PSP calls that WOULD be made. Wiring the real
# API means filling in the marked TODOs — no orchestration change.
# --------------------------------------------------------------------------

@dataclass
class TransferIntent:
    kind: str                 # PAYMENT_INTENT (escrow hold) | TRANSFER (payout)
    order_id: str
    job_id: str | None
    destination: str          # connected-account id (here: our acct: URIs)
    amount_cents: int
    memo: str


class StripeConnectStub(SettlementBackend):
    """Sketch of Stripe Connect: escrow = a PaymentIntent held on the platform;
    settlement = Transfers to each participant's connected account, on verified
    delivery. Compliance (money transmission, KYC) is the PSP/partner's job.
    Records intents instead of calling the API — labelled, not hidden."""

    def __init__(self):
        self.intents: list[TransferIntent] = []
        self._escrow: dict[str, int] = {}
        self._paid: dict[str, int] = {}

    def fund_escrow(self, order: Order) -> None:
        self._escrow[order.order_id] = order.total_cents
        self.intents.append(TransferIntent(
            "PAYMENT_INTENT", order.order_id, None, "platform",
            order.total_cents, f"hold from buyer {order.buyer}"))
        # TODO(real): stripe.PaymentIntent.create(amount=..., capture_method='manual')

    def settle_job(self, order: Order, job: Job):
        total = job.job_total_cents
        if self._escrow.get(order.order_id, 0) < total:
            raise SettlementError(f"escrow underfunded for {job.job_id}")
        legs = compute_settlement_legs(job)
        self._escrow[order.order_id] -= total
        for leg in legs:
            self._paid[leg.account] = self._paid.get(leg.account, 0) + leg.amount_cents
            self.intents.append(TransferIntent(
                "TRANSFER", order.order_id, job.job_id, leg.account,
                leg.amount_cents, leg.memo))
            # TODO(real): stripe.Transfer.create(amount=..., destination=<acct>)
        return SettlementReceipt(ref=f"stripe:{job.job_id}", legs=legs)

    def balance(self, account: str) -> int:
        return self._paid.get(account, 0)

    def escrow_remaining(self, order_id: str) -> int:
        return self._escrow.get(order_id, 0)

    def to_json(self) -> str:
        import json
        return json.dumps({
            "backend": "stripe-connect-stub",
            "escrow": self._escrow,
            "paid": self._paid,
            "intents": [i.__dict__ for i in self.intents],
        }, indent=2)
