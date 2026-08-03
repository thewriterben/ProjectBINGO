# Production Playbook: DGD Promotional Token

*BINGO's first commercial production scenario — drafted August 2026, from Ben's working setup.*

## The job

Physical DGD promotional coin: DGD symbol on the face, reverse blank with a recess for a QR sticker. Perception target: premium — "the American Express of decentralized currency" in the hand. Process: high-speed MSLA, Siraya Tech Blu V2 Clear, currently validated on a Creality Halot Mage Pro. Today: one person (Ben) can deliver quality consistently; a list of printer owners exists who can't yet. Demand: the Foundation's grassroots/campus program, ongoing.

## Assets to register (L1)

| asset | kind | contents | split (illustrative) |
|---|---|---|---|
| DGD token face | `design` | coin STL, QR-recess spec | Ben / John / Foundation as agreed |
| Halot Mage Pro process package | `profile` | tuned exposure/support/layout, resin spec, plate file | Ben (this is the knowledge asset) |

A production order references both; settlement pays both splits plus the fabricating node. The package royalty is the structural fix for "only I can deliver": Ben's tuning earns on every coin printed by anyone, forever, and the network gains a certified process instead of depending on one operator.

## Node certification (L2 — job-class certification)

Capability requirements declared, not assumed: MSLA process, Halot Mage Pro (or engine-class equivalent, once validated), Siraya Blu V2 Clear on hand. Onboarding for the printer-owner list:

1. Install node agent; declare machine + resin inventory.
2. Print the calibration coin from the registered package (no improvisation — the package IS the job).
3. Ship first article to the inspector node (Ben) for grade-P sign-off — inspection is paid network labor.
4. Pass → certified for this job class; spot-check cadence thereafter (every Nth batch photo-evidenced + periodic physical pull).

Certification is per (design, package) pair — narrower and more honest than a general "tier." A node certified for coins isn't certified for anything else, and vice versa.

## Acceptance (grade P, frozen per batch)

Checklist committed into job terms: face surface finish (no visible layer artifacts at arm's length), material clarity to reference sample, dimensional (diameter/thickness ± tolerance), QR recess flat and sticker-ready, no support scarring on display surfaces. Deviations scored by materiality per specs/ACCEPTANCE.md — a coin that fails the face check is a real event; batch-to-batch tint variance within reference range is not.

## Settlement (L4)

Foundation funds escrow per production order. Per verified batch, one atomic release: node fabrication + resin material + logistics + design split + package split + inspection fee + 3% network fee. Grassroots participants are compensated for **work rendered** — fabrication, inspection, distribution — which is the compliance-cleanest structure available and consistent with the Foundation's digital-commodity discipline (no purchase, no profit expectation; recognition of productive work). DGD-denominated settlement makes the run itself a circulation demonstration: Foundation → node operators → (as suppliers onboard) resin replenishment, without exiting to exchanges.

## What this fixes that today hurts

- **Single point of failure:** today a late resin bottle (see: right now) halts all production. With N certified nodes declaring resin-on-hand, the scheduler routes around any dry node. BINGO doesn't make couriers faster; it makes the run indifferent to any one courier.
- **Quality vs. scale tradeoff:** the process package + first-article certification transfers Ben's judgment without diluting it.
- **Compensating grassroots effort:** transparent per-batch settlement replaces ad-hoc favors with auditable pay for verified work.

## Engineering items (honest)

1. **Halot Mage Pro driver:** not Klipper/Moonraker — Creality resin line speaks its own protocol (Creality Cloud / HALOT OS). Needs its own driver in `v3/bingo/node/`. Until then: manual-mode node agent (operator marks stages, uploads batch photos as FRAME evidence) — acceptable for grade-P work because physical first-article + spot-check inspection carries the trust load, per the tier-scaled PoF model.
2. **MSLA PoF profile:** batch-level evidence (plate photo pre/post, cure log, batch serial) rather than per-unit telemetry; spec addendum to NODE-AGENT.md.
3. **Resin inventory declaration:** add `materials_on_hand` to the node capability record so matching can route on it. Small models change.

## Sequence

Week 1–2: register both assets; write the acceptance checklist with John; manual-mode node agent. Week 2–4: certify 2–3 nodes from the existing list (first articles to Ben). Week 4+: first Foundation production order through full settlement; publish the batch ledger. Every coin handed out on a campus thereafter is a product of the network, paying the people who made it — the physical embodiment of the currency, manufactured by the economy it settles.
