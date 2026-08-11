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

The rail is a seam. `MockRail` is for tests. `StripeConnectRail` is a REAL rail:
it drives Stripe's Transfers REST API (stdlib `urllib`, no SDK dependency) with
Stripe's native `Idempotency-Key` set to our own payout key, and points at Stripe
live, Stripe test mode, or a local Stripe-faithful double via `base_url`. The only
thing standing between the demo and real money is the credential and base URL -
plus the people-process gates (KYC/AML, money-transmission licensing, Connect
payee onboarding, counsel) that are out of code scope. `StablecoinRail` (a
GENIUS-Act USD-stablecoin payout, the lowest-risk fiat rail) is still a scaffold
whose real call is marked TODO(real); it fails closed without a credential.
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


def payout_key(job_id: str, account: str, amount_cents: int, memo: str,
               occurrence: int) -> str:
    """Deterministic idempotency key for one payout leg, bound to its ECONOMIC
    identity (account, amount, memo) plus an occurrence index that disambiguates
    genuinely-identical legs. Crucially it does NOT depend on the leg's position
    in the list, so re-settling the same legs in a different order produces the
    same set of keys and never double-pays."""
    return sha256_hex(canonical_json(
        {"job_id": job_id, "account": account, "amount": amount_cents,
         "memo": memo, "n": occurrence}))


def _leg_keys(job_id: str, legs) -> list:
    """Keys for `legs`, aligned by position but computed order-independently:
    identical (account, amount, memo) legs get occurrence 0, 1, 2 … so the same
    multiset of legs yields the same multiset of keys regardless of order."""
    seen: dict = {}
    keys = []
    for leg in legs:
        ident = (leg.account, leg.amount_cents, leg.memo)
        n = seen.get(ident, 0)
        seen[ident] = n + 1
        keys.append(payout_key(job_id, leg.account, leg.amount_cents, leg.memo, n))
    return keys


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
    """A REAL Stripe Connect Transfers rail, implemented against Stripe's REST API
    with the standard library only (no `stripe` SDK dependency — the kernel stays
    stdlib). `POST /v1/transfers`, form-encoded, `Authorization: Bearer <key>`, and
    Stripe's native `Idempotency-Key` header set to our own deterministic payout
    key — so a retry (ours OR Stripe's) settles each leg exactly once, end to end.

    Fail-closed: no API key or no mapped connected account => FAILED, never PAID.
    Error taxonomy that keeps money safe: a network error, a 429 (rate limit), or a
    5xx (Stripe-side) => PENDING (retryable — `retry_pending()` re-drives with the
    SAME key, so it can't double-pay); a 4xx client error => FAILED (terminal).

    `base_url` (or $STRIPE_BASE_URL) points the rail at an endpoint: Stripe live
    (default), Stripe **test mode** with an `sk_test_...` key (real API, no real
    money), or a local Stripe-faithful double for offline end-to-end tests
    (`bingo.demo.fake_stripe`). The ONLY difference between here and moving real
    money is the key and the base URL."""

    STRIPE_LIVE = "https://api.stripe.com"

    def __init__(self, api_key: str | None = None,
                 connected: dict[str, str] | None = None,
                 base_url: str | None = None, timeout: float = 30.0):
        self._api_key = api_key or os.environ.get("STRIPE_API_KEY", "")
        self._connected = connected or {}     # our acct: URI -> Stripe connected id
        self._base_url = (base_url or os.environ.get("STRIPE_BASE_URL")
                          or self.STRIPE_LIVE).rstrip("/")
        self._timeout = timeout

    # -- stdlib HTTP against the Stripe REST API --------------------------------
    def _request(self, method: str, path: str, form: dict | None = None,
                 idem_key: str = "") -> tuple:
        """Returns (http_status | None, parsed_json). status None => transport
        error (no response) — treated as retryable by callers."""
        import urllib.request, urllib.parse, urllib.error
        url = self._base_url + path
        data = urllib.parse.urlencode(form).encode() if form is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self._api_key)
        if data is not None:
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        if idem_key:
            req.add_header("Idempotency-Key", idem_key)   # Stripe-native idempotency
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return resp.status, json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = {"error": {"message": raw[:200]}}
            return e.code, payload
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return None, {"error": {"message": f"transport error: {e}"}}

    @staticmethod
    def _err(payload: dict) -> str:
        return (payload.get("error") or {}).get("message", "unknown Stripe error")

    def send(self, idem_key, destination, amount_cents, currency, memo) -> RailResult:
        if not self._api_key:
            return RailResult(FAILED, "", "no Stripe credentials (set STRIPE_API_KEY)")
        dest = self._connected.get(destination)
        if not dest:
            return RailResult(FAILED, "", f"no connected account mapped for {destination}")
        if not isinstance(amount_cents, int) or amount_cents <= 0:
            return RailResult(FAILED, "", "amount must be a positive integer (cents)")
        form = {"amount": amount_cents, "currency": currency, "destination": dest,
                "metadata[memo]": memo, "metadata[idem]": idem_key}
        status, payload = self._request("POST", "/v1/transfers", form, idem_key)
        if status is None:
            return RailResult(PENDING, "", self._err(payload))         # network -> retryable
        if 200 <= status < 300:
            return RailResult(PAID, payload.get("id", ""))
        if status == 429 or status >= 500:
            return RailResult(PENDING, "", self._err(payload))          # rate-limit/5xx -> retryable
        return RailResult(FAILED, "", self._err(payload))               # 4xx -> terminal

    def retrieve(self, external_ref: str) -> dict | None:
        """Query Stripe for a transfer, for reconciliation against the provider's
        own records (not just our journal). Returns {'amount_cents', 'currency',
        'destination', 'status'} or None if the provider has no such transfer."""
        if not (self._api_key and external_ref):
            return None
        status, payload = self._request("GET", f"/v1/transfers/{external_ref}")
        if status is None or status >= 400:
            return None
        return {"amount_cents": payload.get("amount"),
                "currency": payload.get("currency"),
                "destination": payload.get("destination"),
                "status": "PAID"}


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
        for key, leg in zip(_leg_keys(job_id, legs), legs):
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
        for key, leg in zip(_leg_keys(job_id, legs), legs):
            expected[key] = leg.amount_cents
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

    def reconcile_with_rail(self, job_id: str, legs) -> dict:
        """The stronger reconciliation: cross-check each PAID record against the
        RAIL'S OWN records (not just our journal) AND against the signed legs.

        `reconcile_job` answers "does our journal tie out to what was owed?" This
        answers "did the money the provider actually moved match what we signed?"
        - the check that catches a journal that says PAID when the provider never
        moved the money, or moved a different amount. Requires a rail exposing
        `retrieve(external_ref) -> {'amount_cents', 'currency', 'destination',
        'status'} | None`; if the rail has no `retrieve`, returns
        {'checked': False} (fail-closed: no external confirmation available).

        Fail-closed: a PAID record the provider can't confirm, or confirms with a
        different amount, is a DRIFT entry - `verified` is False if any drift.
        """
        retrieve = getattr(self.rail, "retrieve", None)
        if not callable(retrieve):
            return {"checked": False, "verified": False,
                    "reason": "rail exposes no retrieve(); no external confirmation",
                    "drift": [], "confirmed_cents": 0}

        owed = {key: leg.amount_cents
                for key, leg in zip(_leg_keys(job_id, legs), legs)}
        recs = {k: r for k, r in self._journal.items()
                if r.job_id == job_id and r.status == PAID}

        drift: list[str] = []
        confirmed = 0
        for key, r in recs.items():
            if not r.external_ref:
                drift.append(f"{r.account}: PAID with no external_ref (unconfirmable)")
                continue
            info = retrieve(r.external_ref)
            if info is None:
                drift.append(
                    f"{r.account}: journal says PAID ({r.amount_cents}c) but provider "
                    f"has no transfer {r.external_ref}")
                continue
            prov_amt = info.get("amount_cents")
            if prov_amt != r.amount_cents:
                drift.append(
                    f"{r.account}: amount drift - journal {r.amount_cents}c, "
                    f"provider {prov_amt}c ({r.external_ref})")
                continue
            if key in owed and owed[key] != r.amount_cents:
                drift.append(
                    f"{r.account}: provider-confirmed {prov_amt}c but signed leg "
                    f"owes {owed[key]}c")
                continue
            confirmed += r.amount_cents
        return {"checked": True, "verified": not drift,
                "confirmed_cents": confirmed, "paid_records": len(recs),
                "drift": drift}

    def to_json(self) -> str:
        return json.dumps({"currency": self.currency,
                           "payouts": [asdict(r) for r in self._journal.values()]},
                          indent=2)
