# Project BINGO

**An open protocol for distributed manufacturing where creators are paid a
royalty every time their design is fabricated — enforced at the point of
fabrication, not the honor system.**

A buyer's single payment settles atomically across the whole chain — the
fabricator, the designer, logistics, quality — in one transaction. Every job
produces a signed, independently-verifiable proof that it happened. No
platform to trust, no take-rate to fear, no royalty anyone can quietly skip.

> On 2026-08-03 the network settled its first real fabrication: a part
> printed on a Creality K2 Plus, with the designer's royalty paid in the same
> atomic transaction that paid the printer. One node, real hardware, real
> settlement. The rest of this repo is turning that into a network.

## Why

If you make functional designs, the last few years have been a series of
platform betrayals: Etsy banning sales of licensed-design prints, MakerWorld
rewriting creator payouts overnight, Shapeways going bankrupt holding
customers' money. The lesson everyone learned is that *your income exists at
the pleasure of a platform.* Meanwhile per-unit royalties — getting paid each
time your design is actually made — exist only for patent portfolios and chip
IP, never for the individual designer.

BINGO's premise: **anyone who contributes real skill to the network — a
design, a process, a codebase, a machine, an hour of labor — should be paid
every time the network uses it, automatically, without asking a platform's
permission.** It's infrastructure for automation that pays the people it
depends on. Full argument in [VISION.md](VISION.md).

## See it work

Python 3.10+, no dependencies (stdlib only).

```
cd v3
python -m bingo.demo.run          # the full loop across 3 simulated nodes
python -m bingo.verify out/evidence/   # independently verify every job that just ran
```

The demo registers designs (including a remix that auto-pays the original
creator), places orders, fans them across nodes, signs proof-of-fabrication
for each, and settles atomically — then writes `out/dashboard.html` and a
signed evidence file per job that **anyone** can verify with only the node's
public key.

## How it's built (five layers)

- **L1 Asset Graph** — content-addressed designs + process packages, with
  machine-readable licenses and royalty splits that compose through remixes.
- **L2 Fabrication Network** — nodes run an agent that drives machines and
  emits a hash-chained, Ed25519-signed proof-of-fabrication log.
- **L3 Orchestration** — intake → DFM → quote → match → track → settle, as
  replaceable pipeline stages.
- **L4 Settlement** — escrow with atomic per-job release; each royalty line
  routes to its own asset's split; a flat 3% network fee.
- **L5 Interfaces** — dashboard, node tools, and (coming) an agent-first API.

Protocol specs live in [`v3/specs/`](v3/specs/): asset graph, node agent,
settlement, acceptance grades, logistics.

## Join as a node

A bedroom printer, a farm, a machine shop, or a human inspector all join the
same way — see **[docs/JOIN.md](v3/docs/JOIN.md)**. In short:

```
cd v3
python -m bingo.node.onboard --name "Your node" --operator acct:you --materials PLA
```

It creates your cryptographic identity, self-tests your install end to end,
and prints the node card you send to get certified.

## Status

Working prototype, honest about its seams. **Real:** the registry and
composable royalty math; the Ed25519 signed/verifiable evidence chain
(cross-checked against RFC 8032); atomic to-the-cent settlement; real STL
analysis; a live driver that has printed and settled on real hardware;
acceptance grades and materiality. **Stand-ins, clearly marked:** local
ledger (→ regulated stablecoin escrow + split contracts), simulated carrier
confirmation (→ carrier webhooks), the perception/reach work still spec-only.

Not a product yet — an open protocol and a working core, looking for the
first designers and nodes who aren't the author. If that's you, read
[docs/JOIN.md](v3/docs/JOIN.md).

## Docs

- [VISION.md](VISION.md) — what this is and why
- [RESOURCING.md](RESOURCING.md) — potential value and what it takes to build
- [docs/LANDSCAPE-2026.md](docs/LANDSCAPE-2026.md) — the evidence base (what exists, what failed)
- [docs/PROMISE-INTEGRITY.md](docs/PROMISE-INTEGRITY.md) — the sister workstream
- [v3/README.md](v3/README.md) — the working prototype, in detail

MIT licensed.
