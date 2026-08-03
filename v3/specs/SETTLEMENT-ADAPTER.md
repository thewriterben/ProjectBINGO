# Spec: Settlement adapter (the real-money seam)

**Version 0.1 — draft.** How BINGO goes from demo-cents to real dollars
without rewriting the network. Companion to SETTLEMENT.md.

## The seam

Orchestration talks to settlement only through the `SettlementBackend`
interface (`bingo/settlement.py`):

```
fund_escrow(order)            # buyer funds the order total, held
settle_job(order, job)        # atomic per-job release on verified delivery
balance(account) / escrow_remaining(order_id) / to_json()   # reporting
```

Swapping the backend is the entire migration path. The orchestrator never
learns whether money is a local ledger row, a Stripe transfer, or an on-chain
split — proven by `tests/test_settlement_adapter.py`, which runs the *same*
orchestrator against both the local `Ledger` and `StripeConnectStub` and gets
byte-identical payouts.

## One leg computation, every backend

`compute_settlement_legs(job)` is pure and shared: node (fabrication +
material + energy) + carrier (logistics) + one leg per payee of every royalty
line (each routed through its own asset's frozen split, integer-residue to the
line's first payee) + the 3% network fee — asserted to sum exactly to the job
total. Because every backend calls it, the money splits identically no matter
the rail. The royalty-enforcement guarantee (fabrication cannot be paid
without paying every royalty line) lives here, once.

## Backends

- **`Ledger`** (local, default) — double-entry integer-cent ledger with a
  journal. The dev/demo path and the source of truth for tests.
- **`StripeConnectStub`** — the shape of the fiat path: `fund_escrow` →
  a manual-capture PaymentIntent held on the platform; `settle_job` →
  a Transfer to each participant's connected account on verified delivery.
  It records the exact PSP calls it *would* make (marked `TODO(real)`), so
  wiring live Stripe is filling in those calls — no orchestration change.
  Money-transmission / KYC compliance is the PSP partner's function.

## Roadmap of backends (not yet built)

- **Stripe Connect (live)** — fill the `TODO(real)` calls; connected accounts
  for nodes/creators; manual-capture escrow; Transfers on delivery. The
  compliance-safe default for US participants who want plain dollars.
- **Stablecoin escrow** — GENIUS-regulated USD stablecoin held in a
  non-custodial escrow contract; settlement releases through 0xSplits-pattern
  split contracts (one per asset's effective split — the on-chain mirror of
  `compute_settlement_legs`). Superfluid-style streaming for continuous
  royalties (e.g. training-material).
- **DGD non-custodial escrow** — the v2 DGD architecture generalized:
  partial release per verified milestone, oracle-verified triggers, DGD as an
  *optional* settlement asset (disclosed, never required); USD rails stay the
  default. Gold-backed tokens sit outside GENIUS's stablecoin regime, so this
  is the securities-adjacent path, sequenced after the fiat rail.

## Invariants any backend must hold

1. Conservation: legs sum exactly to the job total; escrow reaches zero after
   an order's last job settles. (Enforced in `compute_settlement_legs`.)
2. No fabrication payment without full royalty payment — structural, not
   policy. (Same code path.)
3. Settlement fires only on verified delivery (the PoF `DELIVERY_CONFIRMED`
   trigger), and every release is auditable (journal / intent log / on-chain).
4. Refund path: a failed or cancelled job releases nothing; its escrow share
   follows the replacement job or refunds to the buyer.
