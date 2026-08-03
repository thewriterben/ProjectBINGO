# Contributing to Project BINGO (v3)

The working system lives in `v3/` (the manufacturing network) and `sentinel/`
(the Promise Integrity watchdog). This guide is for that code. The repo root
has older v2 material kept for history.

## Ground rules

1. **Stdlib only.** No third-party dependencies. The whole thing must run with
   a bare Python 3.10+. This is a hard constraint, not a preference — it's why
   a node operator can join with nothing to install. (Vendored crypto lives in
   `bingo/crypto.py`; it's public-domain RFC 8032 math, cross-checked against
   the `cryptography` library in dev but never imported at runtime.)
2. **Specs are the contract.** `v3/specs/` describes the protocol
   (ASSET-GRAPH, NODE-AGENT, SETTLEMENT, SETTLEMENT-ADAPTER, ACCEPTANCE,
   LOGISTICS). Change behavior → change the spec in the same PR.
3. **Money math is asserted.** Settlement conserves cents and routes each
   royalty line through its own split. If you touch it, the invariants in
   `compute_settlement_legs` and the tests must still hold.
4. **Honesty over polish.** If something is a stub, label it a stub (see the
   `TODO(real)` markers in `settlement.py`). A documented seam is fine; a
   hidden one is not.

## Run the tests

```
python run_tests.py          # from repo root — runs everything, stdlib only
```

Individual suites (from `v3/`):

```
python -m bingo.demo.run                 # the full loop, writes out/
python -m tests.test_settlement_adapter  # one example suite
python -m bingo.crypto                   # ed25519 self-test
```

CI (`.github/workflows/bingo-ci.yml`) runs `run_tests.py` on every push/PR to
`v3/` or `sentinel/`. Green is required.

## Where things live

```
v3/bingo/
  models.py        core types (assets, splits, jobs, evidence, orders)
  registry.py      L1 — content-addressed registry + royalty composition
  acceptance.py    L3 — F/S/P grades, checklists, materiality
  dfm.py quote.py match.py   L3 — feasibility, pricing, matching
  reputation.py    network-maintained per-grade reputation + staking
  orchestrator.py  L3 — the pipeline
  settlement.py    L4 — backend interface + shared leg math + Stripe stub
  ledger.py        L4 — local double-entry backend
  evidence.py verify.py   persist + independently verify PoF chains
  crypto.py        ed25519 (vendored, stdlib)
  server.py        L5 — web dashboard + agent-first API
  node/            L2 — agent, drivers (mock, k2), onboarding, manual mode
sentinel/          Promise Integrity watchdog (classifier, store, CLI)
```

## Good first contributions

- A new node **driver** (`bingo/node/`) for another machine/firmware —
  implement `prepare()` + `run_unit()`/`run_batch()`, following `k2.py`.
- A new **settlement backend** — implement `SettlementBackend`; reuse
  `compute_settlement_legs` so the money splits identically.
- Sharper **DFM checks** for a specific process (sheet metal, PCB, resin).
- Hardening the **acceptance checklists** per grade/process.

Open an issue describing the change before a large PR. Small, tested, spec-
aligned PRs merge fastest.
