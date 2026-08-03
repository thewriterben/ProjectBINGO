# Spec: Settlement (L4)

**Version 0.1 — draft.** All amounts are integer cents. The v0 prototype implements this as a local double-entry ledger; the interfaces are shaped so the ledger can be swapped for on-chain settlement (stablecoin escrow + 0xSplits-pattern contracts, or DGD non-custodial escrow with partial release) without touching the orchestration layer. This generalizes the v2 DGD escrow architecture: partial release per verified milestone, oracle-verified triggers, non-custodial intent.

## Quote → escrow

A quote is transparent line items per allocation (buyer sees every leg — opacity is the incumbent's margin, transparency is ours):

```
per job (one node, q units):
  fabrication   = q × unit_time_h × node_rate_cents_per_h
  material      = q × grams × material_cents_per_g
  energy        = q × unit_time_h × kwh_rate × printer_kw
  logistics     = shipment cost (distance-based, per job)
  royalty       = q × per_unit_cents          (from asset license)
order level:
  network_fee   = fee_bps × (sum of job subtotals)   [v0: 300 bps]
  total         = Σ jobs + network_fee
```

Buyer funds **escrow** for `total` at order placement (card/ACH via PSP, or stablecoin; settlement runs through licensed PSP/custody partners — money-transmission compliance is a partner function in v0/v1).

## Atomic per-job release (partial release)

On each job's `DELIVERY_CONFIRMED` PoF event, settlement executes **one atomic transaction**:

```
escrow(order) −= job_total
  → node account        (fabrication + material + energy)
  → carrier account     (logistics)
  → effective split     (royalty × split bps, integer floor; residue → first payee)
  → network fee account (job's proportional fee share; absorbs rounding residue)
```

Invariants (asserted in the prototype, enforced by contract on-chain):

1. Legs sum exactly to the escrow decrement (no cents created or destroyed).
2. Royalty legs are computed **only** from the asset's frozen `effective_split` — there is no code path that pays fabrication without paying the split. This is the enforcement mechanism; it is structural, not policy.
3. After the final job of an order settles, order escrow is exactly zero.
4. Every leg carries the provenance reference (order/job/asset/PoF chain head hash) — the ledger *is* the audit trail.

Failed/re-routed jobs release nothing; their escrow share follows the replacement job or refunds on cancellation.

## Accounts

`acct:<handle>` URIs. v0: ledger balances + JSON journal. v1: each account binds a payout method (bank via PSP, or wallet). Roadmap: machine-RWA revenue interests and production-credit repayment plug in here as additional legs — same atomic transaction, more payees (which is why the securities-path work can come later without re-architecture).

## Network fee

Flat, published, low single digits (v0: **3%**). Fee changes are a governance action, never a silent config change. For comparison: incumbent marketplaces and design platforms take 10–50%.
