# Project BINGO — architecture

One kernel of cryptographic primitives, pointed at five different domains. This
document maps the shared primitives to each vertical and to the code, so a new
contributor (or a skeptic) can see that it's one system, not five.

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

## The five verticals

| Vertical | Asset | Event log | Value routing | Code |
|---|---|---|---|---|
| **Manufacturing** | design (STL) | proof-of-fabrication | creator royalty at fabrication | `bingo/*`, `bingo/node/*` |
| **RWA provenance** | passport (its content) | lineage→husbandry→harvest→custody→sale | sale split incl. the rancher | `provenance/passport.py`, `register.py` |
| **Tokenization** | claim pinned to passport head | issue→transfer→sale→redeem | primary→split, resale royalty→split | `provenance/token.py` |
| **Auto transport** | custody record | booking(bind carrier)→pickup→delivery | escrow releases only to the bound carrier | `provenance/transport.py` |
| **DGD coins** | coin design + signed credential | persistent redemption ledger | $25 USDC-of-DGD to receiver (backend seam) | `provenance/coin.py`, `coin_server.py` |

The range is the argument: a bracket, a ribeye, a Porsche, and a coin share
nothing except being value that changes hands. One engine handling all four is
the evidence it's infrastructure, not a niche app.

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

## Status

All five verticals run as stdlib Python, **18/18 test suites** (`python
run_tests.py`), committed. Passports, tokens, coins, and bills-of-lading verify
from the document alone. These are working prototypes; real launches need
production keys, hosting, and money-rail integration — the seams for which are
already built (e.g. `DGD_ISSUER_SEED`, `ValidationBackend`, `SettlementBackend`).
