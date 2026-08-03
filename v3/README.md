# BINGO v3 — thin-vertical prototype

The loop from `VISION.md` §5, running: **design → royalty → distributed fabrication → proof → atomic settlement.**

```
cd v3
python -m bingo.demo.run
```

Pure Python 3.10+, stdlib only. Outputs a console narrative plus `out/dashboard.html` (the royalty counter + full settlement journal) and `out/ledger.json`.

## What the demo does

1. **L1** — two creators register real STL designs (generated, watertight, parseable by any slicer) with per-unit licenses and royalty splits. The second design is a *remix* of the first: its effective split is composed at registration, so the original creators automatically earn from every remix unit — frozen, not policy.
2. **L3** — buyers place orders; the pipeline runs real DFM checks on the STL bytes (bounding box, watertightness, volume via divergence theorem), quotes with transparent line items, and allocates units across three simulated nodes in three cities (ship-from-near scoring).
3. **L2** — each node agent fabricates via a mock driver, emitting a **hash-chained, signed proof-of-fabrication log** (gcode hash, telemetry, frame commitments, unit completions, delivery confirmation). The chain is verified before any money moves.
4. **L4** — on each delivery confirmation, the ledger executes **one atomic release**: node + carrier + royalty split + network fee, integer cents, with asserted invariants (legs sum exactly; escrow zeroes out; royalties flow only through the frozen split).

## Layout

```
specs/            protocol drafts: ASSET-GRAPH, NODE-AGENT, SETTLEMENT
bingo/
  models.py       shared types (assets, splits, jobs, evidence, orders)
  registry.py     L1 — content-addressed registry + derivative split composition
  ledger.py       L4 — double-entry ledger, escrow, atomic per-job settlement
  dfm.py          L3 — STL geometry analysis (real parsing, honest heuristics)
  quote.py        L3 — transparent line-item quoting (3% network fee)
  match.py        L3 — tier/distance/reputation scoring + allocation
  orchestrator.py L3 — the pipeline: intake→DFM→quote→match→dispatch→settle
  node/
    agent.py      L2 — node agent: job lifecycle + hash-chained signed PoF
    drivers.py    L2 — mock driver + generic Moonraker/Bambu stubs
    k2.py         L2 — REAL driver: Creality K2 Plus via Moonraker (stdlib-only)
    k2_node.py    L2 — CLI runner: the thin vertical on real hardware
  demo/           the end-to-end run + dashboard renderer
tests/
  fake_moonraker.py   Moonraker impostor (real endpoint shapes)
  test_k2_driver.py   integration test: K2 driver → PoF chain → settlement
```

## Running on the real K2 Plus

From the machine that can reach the printer (endpoint map confirmed against
the AdvancedStudio diagnostics captures):

```
cd v3
python -m bingo.node.k2_node --host 192.168.1.230              # dry-run check
python -m bingo.node.k2_node --host 192.168.1.230 --gcode path\to\bracket_PLA.gcode --go
```

Slice the part yourself (Creality Print / Orca) — the runner never generates
gcode. It uploads your file, starts the print behind a typed confirmation,
streams telemetry + webcam-frame hashes into the PoF chain, waits for your
receipt confirmation, then settles atomically and writes `out/dashboard.html`.
A failed or cancelled print settles nothing. Test the whole path without
hardware first: `python -m tests.test_k2_driver`.

## What is deliberately fake, and what isn't

**Real:** the STL geometry and its analysis; the split-composition math; the hash-chained evidence structure and its verification; the settlement atomicity and integer-cent invariants; the quoting/matching logic.

**Stand-ins with documented seams:** mock printer driver (→ Moonraker/Bambu, endpoints already stubbed); HMAC signing (→ ed25519); local ledger (→ stablecoin escrow + 0xSplits-pattern contracts, or DGD non-custodial escrow); slice stub (→ PrusaSlicer/OrcaSlicer CLI); simulated carrier confirmation (→ carrier webhooks).

Next steps live in `VISION.md` §6 (Phase B): point one real printer at `drivers.py`, put one real dollar through a PSP, and the demo stops being a demo.
