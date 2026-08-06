# Project BINGO — architecture

One kernel of cryptographic primitives, pointed at seven different domains. This
document maps the shared primitives to each vertical and to the code, so a new
contributor (or a skeptic) can see that it's one system, not seven.

## The thesis

The systems that move value run on **trust-by-paperwork** — a label, an invoice,
a promise. BINGO replaces the paperwork with proof: provenance you can verify,
payment that routes automatically to the maker, and fraud that can't *settle*
rather than fraud you have to chase. The goal is not profit extraction but that a
skilled person — a designer, a rancher, a driver — meaningfully shares in what
their work produces.

## The shared kernel

Everything below is built from these, and nothing else:

1. **Content-addressed assets** — an asset's ID is the SHA-256 of its content, so
   identity can't be separated from the thing (`bingo/registry.py`,
   `bingo/models.py`).
2. **Ed25519 signatures** — pure-Python, RFC 8032, verified byte-identical to the
   `cryptography` library; anyone with the public key can verify (`bingo/crypto.py`).
3. **Hash-chained, signed event logs** — each event signed and linked to the last;
   tamper/reorder/forge one link and the chain breaks. The spine of every record.
4. **Atomic value routing** — a payment splits across every contributor to the
   cent, in one transaction; royalty enforced at the point of transaction
   (`bingo/settlement.py`, `provenance/token.py::route`).
5. **Single-use ledgers** — a claim spends exactly once; a copy is caught by
   replay, and (for coins) the ledger persists so it survives restarts.
6. **Independent verification** — every record verifies from the document alone,
   offline (`bingo/verify.py`, `provenance/verify.py`).

## The seven verticals

| Vertical | Asset | Event log | Value routing | Code |
|---|---|---|---|---|
| **Manufacturing** | design (STL) | proof-of-fabrication | creator royalty at fabrication | `bingo/*`, `bingo/node/*` |
| **RWA provenance** | passport (its content) | lineage→husbandry→harvest→custody→sale | sale split incl. the rancher | `provenance/passport.py`, `register.py` |
| **Tokenization** | claim pinned to passport head | issue→transfer→sale→redeem | primary→split, resale royalty→split | `provenance/token.py` |
| **Auto transport** | custody record | booking(bind carrier)→pickup→delivery | escrow releases only to the bound carrier | `provenance/transport.py` |
| **DGD coins** | coin design + signed credential | persistent redemption ledger | $25 USDC-of-DGD to receiver (backend seam) | `provenance/coin.py`, `coin_server.py` |
| **Training royalties** | training corpus (its content) | signed attribution corpus | pool→by-contribution→each asset's split | `bingo/training.py` |
| **Machine RWA** | a machine's future revenue | open→buy*→earn* (signed cap table) | pro-rata to backers, capped at repayment | `provenance/machine_rwa.py` |

The range is the argument: a bracket, a ribeye, a Porsche, a coin, the knowledge
an AI is trained on, and *a share of a printer's future earnings* share nothing
except being value that changes hands. One engine handling all of them is the
evidence it's infrastructure, not a niche app.

### The thesis is machine-checked, not asserted

The table above is a claim, and a claim in a doc fails silently. So the "one
kernel, not seven" thesis is enforced by a conformance suite
(`tests/test_kernel_thesis.py`) that fails if it stops being true:

- **Kernel identity (static).** Every vertical's content-addressing and signing
  are the *same code objects* as the kernel's — checked with `is`. If any
  vertical reimplements sha256 or Ed25519, or a copy drifts, the suite fails.
  This is "one system, not seven," made mechanical (15 bindings across the
  verticals today).
- **Kernel properties (randomized).** Content-addressing, canonical-JSON
  determinism, Ed25519 soundness, and **conservation-to-the-cent** are asserted
  as properties over thousands of random inputs — including nasty residues — for
  three independently-written value routers (token, machine-RWA, training). So a
  pass is not "the cases we imagined," it's "the invariant held on every trial."
- **Uniform offline verification.** Every vertical exposes the same
  `verify(document) -> (ok, notes)` primitive, and tampering *any* event of a
  live record is caught.

The suite is itself tested for teeth: forking a primitive or dropping a
value-routing residue makes it fail, as it must.

### Manufacturing / creator economy
Designs are content-addressed assets with royalty splits; every fabrication emits
a signed PoF chain and pays the creator at the moment of the print, with
network-maintained reputation and F/S/P acceptance grades. Proven on a real K2
print: 44 signed PoF events, atomic settlement. See `bingo/` and `run_tests.py`.

### RWA provenance
Each premium good carries a passport whose links are each signed by the party who
made them; the passport *is* the asset's content. Proven with an A5 Wagyu
ribeye — the rancher paid $12.87 on one cut, verifiable offline.

### Tokenization
A transferable claim pinned to a verified passport; you can't mint a claim on a
thing you can't prove. Ownership is a signed ledger; sale proceeds route through
the provenance split; redemption requires a co-signed physical handoff. Double-
spend, forged signer, fabricated payouts all caught on replay.

### Auto transport
Carrier identity bound at booking; pickup and delivery must be that identity;
escrow releases only to it. A re-brokered load can't verify, so it can't settle —
detection becomes unnecessary. Live demo: `provenance/transport_server.py`.

### DGD promo coins
A $25 bearer QR: Ed25519 credential (counterfeit fails offline) + scratch-off
code committed by hash under a tamper-evident panel (a photographed QR can't
redeem) + a persistent single-use ledger (no double-redeem, survives restarts) +
a `ValidationBackend` seam for the USDC-of-DGD crediting. Page/API in
`provenance/coin_server.py`; batch mint in `provenance/coin_batch.py`.

### Training-material royalties
The mission turned on AI itself: automation pays the people it learned from. A
signed, content-addressed **attribution corpus** records which registered assets
(print profiles, failure datasets, design libraries) trained a model version and
by how much — tamper/forge/reorder caught offline. A `RoyaltyMeter` accrues a
pool from the model's fee-earning *usage*, single-use per event (no double count);
`distribute` splits the pool by contribution share, then each asset's cut through
its own split (co-authors, derivative parents), to the cent. A fine-tune can
declare a base corpus + share, so its usage also pays the base model's teachers —
the training analogue of derivative royalties. Per-asset accounting, not a pooled
"AI bonus" — the thing nobody has built for functional design knowledge.
Demo: `python -m bingo.demo.training`. Code: `bingo/training.py`.

### Machine RWA / node financing
Finance a machine by selling shares of its future revenue. A signed,
content-addressed **offering** fixes the terms (shares, price, the investor
revenue share, a repayment cap); a hash-chained, Ed25519-signed **cap table**
(OPEN → BUY* → EARN*) records the raise and every payout, and rejects
oversubscription. As the machine earns, each event streams the investor pool
**pro-rata to shareholders, capped at repayment** (then 100% reverts to the
operator), conserving to the cent — a signed-but-false distribution is caught by
re-derivation on replay. The distinctive part: only **PoF-verified** ledger
revenue may fund a distribution (`verified_machine_revenue`), so the collateral's
income stream is itself provable. Framed as a technical primitive, not a
securities offering. Demo: `python -m provenance.machine_rwa_demo`. Code:
`provenance/machine_rwa.py`.

## Status

All seven verticals run as stdlib Python, **29/29 test suites** (`python
run_tests.py`) — including a one-kernel conformance suite that machine-checks the
thesis itself, a fail-closed raise-readiness gate for the machine-RWA vertical
(`provenance/raise_readiness.py`), an idempotent, crash-safe, reconciled
payout-execution layer (`bingo/payout.py`) that drives a real Stripe/stablecoin
rail without ever double-paying, and six red-team regression suites pinning 66
adversary-found breaks closed across six rounds (see `claude/REDTEAM-FINDINGS.md`
and `-R2`…`-R6`) — committed. Token share ownership is bound to a key at credit
(an account has one controlling key for life; keyless credits are terminal);
content-addressed ids are deterministic (no wall-clock in the identity hash);
every document verifier fails CLOSED — returns (ok, notes), never raises — on
arbitrary/adversarial input; and the settlement money gate is an `if/raise`, not
an `assert`, so it survives `python -O`.
Every verifier trusts only signed bytes; conservation fails closed (no `assert`).
Passports, tokens, coins, bills-of-lading, training corpora, and machine-share
instruments verify from the document alone. These are
working prototypes; real launches need production keys, hosting, and money-rail
integration — the seams for which are already built (e.g. `DGD_ISSUER_SEED`,
`ValidationBackend`, `SettlementBackend`).
