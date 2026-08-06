"""L4 money movement - the safe execution layer that actually pays the legs.

`settlement.py` computes WHO gets paid and HOW MUCH (the signed, conserved legs).
This module MOVES the money - or rather, drives a real payout rail to move it -
with the properties that keep real money from going wrong:

  * **Idempotency.** Every payout has a deterministic key derived from the
    settlement (job + leg index + account + amount). Paying the same settlement
    twice pays each account exactly once - a replay, a retry, or a double-call
    can't double-pay. This is the single most important property for real money.
  * **Crash-safety (two-phase).** The intent is journaled as PENDING *before* the
    rail is called, and only flipped to PAID after the rail confirms. A crash
    mid-payout leaves a PENDING record that `retry_pending()` re-drives with the
    SAME idempotency key - so an outage never loses a payout and never repeats one
    (the same discipline as coin redemption: commit before crediting).
  * **Fail-closed.** A rail with no credentials returns FAILED, never PAID. A
    payout to an account not in the signed legs is never created. Nothing is
    silently dropped.
  * **Reconciliation.** `reconcile_job()` checks the money movement back against
    the authoritative signed legs: every owed cent is PAID or in-flight, nothing
    was paid that wasn't owed, and the sums tie out - so "did the right money
    move?" is answerable from records, not trust.

The rail is a seam. `MockRail` is for tests; `StripeConnectRail` and
`StablecoinRail` (a GENIUS-Act USD-stablecoin payout, the lowest-risk fiat rail)
are scaffolds whose real calls are marked TODO(real) and which fail closed
without credentials - so this environment can prove the safety machinery without
moving a real cent.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict

from .models import canonical_json, sha256_hex

PENDING = "PENDING"
PAID = "PAID"
FAILED = "FAILED"


def payout_key(job_id: str, index: int, account: str, amount_cents: int) -> str:
    """Deterministic idempotency key for one payout leg. Stable across retries
    (same settlement -> same key), unique per leg (index disambiguates identical
    account+amount legs)."""
    return sha256_hex(canonical_json(
        {"job_id": job_id, "i": index, "account": account, "amount": amount_cents}))


@dataclass
class RailResult:
    status: str            # PAID | PENDING | FAILED
    external_ref: str = ""
    error: str = ""


@dataclass
class PayoutRecord:
    key: str
    order_id: str
    job_id: str
    account: str
    amount_cents: int
    memo: str
    currency: str
    status: str
    external_ref: str = ""
    error: str = ""
    attempts: int = 0


# -- the rail seam -------------------------------------------------------------

class PayoutRail(ABC):
    """Moves `amount_cents` to `destination`, keyed by `idem_key`. Real rails
    (Stripe, stablecoin) pass idem_key to the provider so THEIR side is idempotent
    too. Must be safe to call twice with the same idem_key."""
    @abstractmethod
    def send(self, idem_key: str, destination: str, amount_cents: int,
             currency: str, memo: str) -> RailResult: ...


class MockRail(PayoutRail):
    """Deterministic rail for tests. Everything succeeds unless its destination is
    in `fail` or `pend`. Records each idem_key it was asked to send, so tests can
    prove the engine calls the rail once per key (idempotency)."""
    def __init__(self, fail: set[str] | None = None, pend: set[str] | None = None):
        self.fail = set(fail or ())
        self.pend = set(pend or ())
        self.sent: list[str] = []

    def send(self, idem_key, destination, amount_cents, currency, memo) -> RailResult:
        self.sent.append(idem_key)
        if destination in self.fail:
            return RailResult(FAILED, "", "mock: forced failure")
        if destination in self.pend:
            return RailResult(PENDING, f"mock-pending:{idem_key[:8]}")
        return RailResult(PAID, f"mock:{idem_key[:8]}")


class StripeConnectRail(PayoutRail):
    """Scaffold for Stripe Connect Transfers. Fail-closed without an API key; the
    real call is one marked line. Stripe natively takes an idempotency key, so
    retries are safe end-to-end."""
    def __init__(self, api_key: str | None = None,
                 connected: dict[str, str] | None = None):
        self._api_key = api_key or os.environ.get("STRIPE_API_KEY", "")
        self._connected = connected or {}     # our acct: URI -> Stripe connected id

    def send(self, idem_key, destination, amount_cents, currency, memo) -> RailResult:
        if not self._api_key:
            return RailResult(FAILED, "", "no Stripe credentials (set STRIPE_API_KEY)")
        dest = self._connected.get(destination)
        if not dest:
            return RailResult(FAILED, "", f"no connected account mapped for {destination}")
        # TODO(real): import stripe; stripe.api_key = self._api_key
        #   tr = stripe.Transfer.create(amount=amount_cents, currency=currency,
        #       destination=dest, metadata={"memo": memo},
        #       idempotency_key=idem_key)
        #   return RailResult(PAID, tr.id)
        raise NotImplementedError("real Stripe transfer not wired in this environment")


class StablecoinRail(PayoutRail):
    """Scaffold for a regulated USD-stablecoin payout (GENIUS Act, the lowest-risk
    rail per LANDSCAPE-2026). Fail-closed without an issuer/custody credential."""
    def __init__(self, credential: str | None = None,
                 wallets: dict[str, str] | None = None):
        self._cred = credential or os.environ.get("STABLECOIN_CREDENTIAL", "")
        self._wallets = wallets or {}         # our acct: URI -> chain address

    def send(self, idem_key, destination, amount_cents, currency, memo) -> RailResult:
        if not self._cred:
            return RailResult(FAILED, "", "no stablecoin credential (set STABLECOIN_CREDENTIAL)")
        addr = self._wallets.get(destination)
        if not addr:
            return RailResult(FAILED, "", f"no payout wallet mapped for {destination}")
        # TODO(real): issuer_client.transfer(to=addr, amount=amount_cents,
        #   currency=currency, reference=idem_key)  # reference => idempotent
        raise NotImplementedError("real stablecoin transfer not wired in this environment")


# -- the engine ----------------------------------------------------------------

class PayoutEngine:
    """Drives a rail to pay the signed settlement legs, idempotently and crash-
    safely, journaling every intent. Optionally persists the journal to JSONL so
    payouts survive a restart and still can't be repeated."""

    def __init__(self, rail: PayoutRail, journal_path: str | None = None,
                 currency: str = "usd"):
        self.rail = rail
        self.currency = currency
        self.journal_path = journal_path
        self._journal: dict[str, PayoutRecord] = {}
        if journal_path and os.path.exists(journal_path):
            self._load()

    # -- persistence (best-effort; a corrupt line fails closed on load) --
    def _load(self) -> None:
        with open(self.journal_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)                 # corrupt journal -> raise (fail closed)
                self._journal[d["key"]] = PayoutRecord(**d)

    def _persist(self) -> None:
        if not self.journal_path:
            return
        tmp = self.journal_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for rec in self._journal.values():
                f.write(json.dumps(asdict(rec)) + "\n")
        os.replace(tmp, self.journal_path)           # atomic swap

    def _drive(self, rec: PayoutRecord) -> PayoutRecord:
        """Two-phase: persist PENDING intent, call the rail, persist the outcome.
        Never pays a key already PAID."""
        if rec.status == PAID:
            return rec
        rec.status = PENDING
        self._journal[rec.key] = rec
        self._persist()                              # intent committed BEFORE rail call
        res = self.rail.send(rec.key, rec.account, rec.amount_cents,
                             rec.currency, rec.memo)
        rec.attempts += 1
        rec.status, rec.external_ref, rec.error = res.status, res.external_ref, res.error
        self._persist()
        return rec

    def pay_legs(self, legs, *, order_id: str, job_id: str) -> list[PayoutRecord]:
        """Pay each settlement leg exactly once. Legs are the SIGNED settlement
        legs (settlement.compute_settlement_legs / SettlementReceipt.legs). Called
        again with the same legs, already-PAID legs are skipped - idempotent."""
        out: list[PayoutRecord] = []
        for i, leg in enumerate(legs):
            key = payout_key(job_id, i, leg.account, leg.amount_cents)
            existing = self._journal.get(key)
            if existing and existing.status == PAID:
                out.append(existing)                 # idempotent: never double-pay
                continue
            rec = existing or PayoutRecord(
                key=key, order_id=order_id, job_id=job_id, account=leg.account,
                amount_cents=leg.amount_cents, memo=leg.memo, currency=self.currency,
                status=PENDING)
            out.append(self._drive(rec))
        return out

    def retry_pending(self) -> list[PayoutRecord]:
        """Re-drive every PENDING/FAILED payout with its SAME idempotency key -
        safe to call after a crash or an outage; can't double-pay a PAID leg."""
        return [self._drive(r) for r in list(self._journal.values())
                if r.status in (PENDING, FAILED)]

    def balance(self, account: str) -> int:
        """Total actually PAID to an account."""
        return sum(r.amount_cents for r in self._journal.values()
                   if r.account == account and r.status == PAID)

    def reconcile_job(self, job_id: str, legs) -> dict:
        """Check money movement back against the authoritative signed legs.

        `consistent` = no unexpected payouts, and every owed cent is accounted for
        (PAID + PENDING + FAILED == owed). `fully_settled` = additionally every
        owed leg is PAID. Discrepancies (owed-but-missing, amount mismatch, or a
        payout not owed) are listed - fail-closed: any leakage shows up here.
        """
        expected: dict[str, int] = {}
        for i, leg in enumerate(legs):
            expected[payout_key(job_id, i, leg.account, leg.amount_cents)] = leg.amount_cents
        recs = {k: r for k, r in self._journal.items() if r.job_id == job_id}

        discrepancies: list[str] = []
        for key, amt in expected.items():
            r = recs.get(key)
            if r is None:
                discrepancies.append(f"owed but no payout record ({amt}c)")
            elif r.amount_cents != amt:
                discrepancies.append(
                    f"amount mismatch for {r.account}: owed {amt}c, record {r.amount_cents}c")
        for key, r in recs.items():
            if key not in expected:
                discrepancies.append(
                    f"payout not owed (unexpected): {r.account} {r.amount_cents}c [{r.status}]")

        owed = sum(expected.values())
        paid = sum(r.amount_cents for r in recs.values() if r.status == PAID)
        pending = sum(r.amount_cents for r in recs.values() if r.status == PENDING)
        failed = sum(r.amount_cents for r in recs.values() if r.status == FAILED)
        consistent = not discrepancies and (paid + pending + failed == owed)
        return {
            "consistent": consistent,
            "fully_settled": consistent and paid == owed,
            "owed_cents": owed, "paid_cents": paid,
            "pending_cents": pending, "failed_cents": failed,
            "discrepancies": discrepancies,
        }

    def to_json(self) -> str:
        return json.dumps({"currency": self.currency,
                           "payouts": [asdict(r) for r in self._journal.values()]},
                          indent=2)
