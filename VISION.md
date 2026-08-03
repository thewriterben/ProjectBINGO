# Project BINGO v3 — Vision & Architecture

**The Commons Manufacturing Network**

*Draft 1.0 — August 2026*

---

## 0. Mission

Most people have gotten nothing from the AI revolution except anxiety about their jobs. The gains have pooled at the top of the stack — model labs, cloud vendors, and the companies large enough to deploy agents against their own workflows. Meanwhile the people who actually know how to make things — designers, machinists, engineers, artists, firmware hackers, the person who spent two hundred hours perfecting a print profile — capture almost none of the value their knowledge creates when automation uses it.

Project BINGO is a distributed supply and manufacturing network built to invert that. Its premise:

> **Anyone who contributes real skill to the network — a design, a schematic, a codebase, a training corpus, a machine, an hour of labor — should be paid every time the network uses it, automatically, forever, without asking permission from a platform.**

The system connects four things that today live in separate worlds: creators who make designs and knowledge assets, agentic AI that turns intent into manufacturable work, a distributed network of machines and hands that fabricate, and capital rails that finance, escrow, and settle it all. When the loop closes, an individual with a laptop can design something at breakfast, have it manufactured across a network of independent shops by dinner, and earn royalties on every subsequent unit anyone else orders — while the shop owners, material suppliers, couriers, and QA inspectors along the way are all paid the moment their part of the work is verified.

This is not a profit-maximizing venture. It is infrastructure for a world where automation pays the people it learned from and works alongside, instead of strip-mining them. Post-scarcity doesn't arrive by itself; somebody has to build the plumbing.

## 1. Why now (the 2026 convergence)

Five things became true recently that make this buildable now, not five years from now. (Full evidence in `docs/LANDSCAPE-2026.md`.)

**The components exist.** Instant quoting is a solved problem (Xometry processes it at $800M/yr run-rate scale). AI CAM generates most of a 3-axis machining strategy (CloudNC, 1,000+ shops). Print farms run themselves (3DQue, SimplyPrint) and one company already exposes a whole factory as an API (Slant 3D). Text-to-CAD produces real parametric geometry for simple parts (Zoo's Zookeeper agent). Automated DFM checking is a commodity. Nobody has composed these into an open network — but no single component needs to be invented.

**The payment rails matured.** The GENIUS Act made regulated stablecoin payouts the lowest-risk crypto rail in America. Audited, free, production-grade contracts exist for revenue splits (0xSplits) and streaming payments (Superfluid). On-chain receivables financing is a real market (Centrifuge, Maple). Machine tokenization has its first standardized framework (peaq, Feb 2026).

**The niche is verifiably empty.** Across ~650 DePIN projects, one targets fabrication. Per-unit design royalties exist only as corporate patent machinery (semiconductor IP, standards-essential patents) — no such market exists for individual physical-design creators. The intersection — distributed fabrication with enforced creator royalties — has zero credible occupants.

**The creators are being radicalized.** Etsy's ban on selling prints of licensed designs takes effect August 11, 2026. MakerWorld unilaterally rewrote its points economy. Shapeways went bankrupt holding customers' money. Josef Prusa declared open hardware "dead" and retreated to a defensive license. Every 3D-design creator in 2026 has learned the same lesson: *your income exists at the pleasure of a platform.* A neutral network with structurally enforced royalties is the fix, and the audience for it has never been more receptive.

**The failures have been catalogued.** TradeLens, SyncFab, Genesis of Things, OpenBazaar, Story Protocol, NFT royalties — a decade of blockchain-meets-real-world wreckage with legible autopsy reports. We know exactly which mistakes not to repeat.

## 2. Design principles (learned from the graveyard)

1. **The token is not the business model.** Demand pays in dollars and regulated stablecoins. No speculative token is required to use, join, or build on the network. If a network asset exists at all, it comes later, earns nothing from speculation, and is never a prerequisite.
2. **Crypto must be invisible.** A shop owner joins by installing software and connecting a bank account or wallet — their choice. A buyer checks out with a card. The settlement layer is plumbing, mentioned as often as TCP/IP.
3. **Royalties are enforced by physics, not promises.** The NFT royalty collapse proved programmable royalties fail when payment can route around the enforcer. BINGO's royalties cannot be routed around for any fabrication that flows through the network, because the royalty split executes inside the same settlement that pays the fabricator. No payment, no fabrication; no fabrication network, no product. The network is the choke point *in the creator's favor*.
4. **The oracle problem is a first-class engineering target.** Proving a part was actually made, to spec, and shipped is the unsolved problem that killed provenance-on-chain. We attack it with layered evidence (machine telemetry, in-process imaging, QA attestation, reputation staking, dispute arbitration) rather than pretending any single proof suffices.
5. **Neutrality is structural.** No single company — including whatever entity stewards BINGO — may own the network. Protocol governance, open specifications, and forkable open-source implementations are the guarantee, the same way nobody "owns" email.
6. **Solve churn with recurrence.** Prototyping marketplaces die of churn (customers prototype, then leave for cheaper direct suppliers). BINGO's economics are built on what recurs: royalty streams, standing production runs, network-native products, machine financing repayment, and memberships — not one-off quote arbitrage.
7. **Humans stay in the loop where it matters.** Agents draft, check, match, schedule, and settle. Humans approve designs for production, perform skilled fabrication and QA, and arbitrate disputes — and are paid as first-class participants for it, not treated as friction to be optimized away.

## 3. The system: five layers

```
┌────────────────────────────────────────────────────────────────┐
│  L5  INTERFACES        storefronts · APIs · chat/agent intake  │
├────────────────────────────────────────────────────────────────┤
│  L4  CAPITAL RAILS     escrow · royalty splits · machine RWA   │
│                        production credit · streaming payouts   │
├────────────────────────────────────────────────────────────────┤
│  L3  ORCHESTRATION     agentic pipeline: intake → DFM → quote  │
│                        → match → schedule → track → QA → ship  │
├────────────────────────────────────────────────────────────────┤
│  L2  FABRICATION NET   nodes: printers · CNC · shops · farms   │
│                        machine identity · proof-of-fabrication │
├────────────────────────────────────────────────────────────────┤
│  L1  ASSET GRAPH       designs · licenses · provenance ·       │
│                        royalty terms · skill/training assets   │
└────────────────────────────────────────────────────────────────┘
```

### L1 — The Asset Graph (the creator economy substrate)

The Asset Graph is a registry of everything the network can *use*: part designs and assemblies, print/machining profiles, firmware and software, QC procedures, training datasets and skill material for the network's own AI, and derivative relationships between all of the above.

Each asset carries:

- **Content addressing** — the asset is identified by hash; files live in ordinary storage (IPFS or plain object storage — availability matters more than ideology).
- **A machine-readable license** — chosen from a small set of standard templates (personal / commercial-flat / **commercial-per-unit** / open-with-attribution / network-training), inspired by what Creative Commons did for media and what Prusa's Open Community License attempted defensively. Per-unit royalty terms are numbers, not prose.
- **A royalty split** — an immutable payout tree (0xSplits-style). Derivatives compose: if design B remixes design A, B's split embeds A's share automatically. This is Story Protocol's royalty-graph idea rebuilt where it can actually work — at the point of fabrication payment rather than hoping marketplaces honor it.
- **Provenance** — who registered it, when, derived from what. Registration is timestamped attestation, not a claim of legal copyright adjudication; disputes go to the arbitration backstop (L2's staked human arbitrators) like everything else.

**The core mechanic — royalty at point of fabrication:** when a buyer orders a unit manufactured, the order references the design's asset ID. Settlement (L4) will not release fabrication payment except through the design's split. The designer is paid *in the same atomic transaction* as the shop that printed the part. There is no invoice to dodge, no marketplace policy to change, no royalty to "choose" to honor. A design listed per-unit at $0.40 earns $0.40 × every unit, from any buyer, on any node, forever.

**Training-material assets** extend the same mechanic to AI: when the network's design agents are trained or fine-tuned on registered material (print profiles, design libraries, annotated failure datasets), the contributors' assets carry network-training licenses and receive a metered share of network fees — individual, per-asset accounting, not the pooled single-digit-dollar "AI bonus" model that Adobe and Shutterstock use today. Cloudflare is building this for web content; nobody has built it for functional design knowledge.

### L2 — The Fabrication Network

Nodes range from a Bambu printer in a spare bedroom to a five-person CNC shop to a 200-printer farm. Every node runs the **node agent**: open-source software that speaks to local machines (Klipper/Moonraker, Bambu Developer Mode, OctoPrint, LinuxCNC, vendor APIs), advertises capabilities, accepts jobs, streams telemetry, and settles payment.

- **Machine identity:** each machine gets a keypair identity with an attested capability profile (envelope, materials, tolerances, certifications). peaq's Machine RWA framework demonstrated the identity pattern; we adopt the pattern without requiring their chain.
- **Capability tiers:** Tier 0 — hobbyist FDM (consumer goods, low-stakes parts); Tier 1 — professional additive + basic subtractive; Tier 2 — certified shops (materials certs, inspection equipment); Tier 3 — specialized (PCB assembly, injection tooling, sheet metal). Orders route to the minimum tier that satisfies the spec. This is how the network serves both the bedroom printer and the aerospace-adjacent shop without pretending they're interchangeable.
- **Proof-of-fabrication (PoF):** layered, probabilistic, tier-scaled evidence that the physical work happened:
  1. *Telemetry attestation* — signed job logs from the machine (gcode hash, temps, timelapse frames) via the node agent.
  2. *In-process imaging* — camera captures at defined stages, hashed and committed at capture time.
  3. *QA attestation* — for higher tiers, a second party (buyer on receipt, or a paid network inspector) signs off against the spec's checklist; inspectors are themselves network labor, staked and rated.
  4. *Reputation staking* — nodes stake earnings-history value against fraud; confirmed fraud slashes and expels. New nodes start on low-value orders and graduate.
  5. *Arbitration backstop* — disputes go to staked human arbitrators (the one part of SyncFab-era designs worth keeping is that they never solved this; we budget for humans).
  
  No single layer is trustworthy; the stack is designed so cheating costs more than honest work at every tier. This is the hardest problem in the whole system, and it is the moat — whoever solves distributed fabrication trust first owns the category the way Xometry owns curated quoting.
- **Labor as a node type:** skilled humans register like machines — finishers, assemblers, inspectors, couriers, repair techs — with capability profiles, availability, and rates. The agentic pipeline schedules them exactly as it schedules machines, and they're paid by the same settlement. "Solving the human labor problem" doesn't mean eliminating humans; it means giving human work the same first-class, instantly-paid, reputation-bearing status as machine work.

### L3 — The Orchestration Layer (agentic pipeline)

A job moves through a pipeline of specialized agents, each with narrow authority and audited hand-offs:

1. **Intake agent** — converses with the buyer (or their agent — the API is agent-first), turns intent into a structured spec: geometry (uploaded, from the Asset Graph, or drafted via text-to-CAD assist for simple parts), material, quantity, tolerance class, deadline, budget.
2. **Feasibility/DFM agent** — automated manufacturability analysis per candidate process; flags issues back to the buyer or, with permission, applies standard fixes. Assembled from proven techniques (Protolabs-class geometry analysis is a decade old).
3. **Quoting agent** — prices from real network state: node rates, material spot prices, energy, logistics distance, urgency. Transparent line-item output — the buyer sees what the shop gets, what the designer gets, what the network takes. Information asymmetry is the incumbent marketplaces' margin; transparency is ours.
4. **Matching/scheduling agent** — splits the run across nodes by capability tier, geography (ship-from-near), price, reputation, and load. Multi-unit runs parallelize across the network — 500 units as 25 jobs on 25 machines in 25 places, each shipping to its nearest buyers. Distributed manufacturing's actual advantage over the centralized factory is *latency and shipping*, not unit cost; the scheduler is built around that.
5. **Production-tracking agent** — consumes node telemetry, monitors PoF evidence as it accumulates, detects stalls/failures, re-routes failed jobs, keeps the buyer's order view live.
6. **QA agent** — evaluates imaging against spec (vision models are good enough for dimensional sanity checks and defect screening at Tier 0–1), schedules human inspection where the tier demands it.
7. **Logistics agent** — books carriers via API (Shippo/EasyPost-class aggregators to start), generates labels, tracks, and confirms delivery — the delivery confirmation is a PoF input and a settlement trigger.
8. **Settlement agent** — releases escrow through the royalty splits on verified milestones, files the outcome into every participant's reputation.

Agents are replaceable competitors, not a monolith: the pipeline stages are open interfaces (an MCP-style tool protocol), so anyone can run an improved quoting agent or a specialized DFM agent for, say, sheet metal — and charge for it through the same settlement. The orchestration layer is a marketplace of agents, not a product.

### L4 — Capital Rails

- **Settlement & escrow:** buyer funds escrow at order time (card/ACH via a PSP, or stablecoin directly); milestone releases flow through the royalty splits. The **DGD escrow architecture from the v2 repo carries forward here** — non-custodial escrow with partial release and oracle verification is exactly the right shape; v3 generalizes it to settle in any regulated stablecoin, with DGD as a supported (not required) settlement asset. Fiat-in, fiat-out is table stakes; principle 2.
- **Royalty distribution:** immutable split contracts (0xSplits pattern) per asset, composing through derivative chains. Streaming (Superfluid pattern) for continuous flows like training-material royalties.
- **Machine RWA (carefully, legally):** a node operator can finance a new machine by selling fractional interests in that machine's future network revenue. This is a security in the US — full stop — so it ships through the compliant path (Reg CF for community-scale raises, the SEC innovation exemption as it matures, registered transfer agent, KYC'd investors), not through pretending otherwise. peaq's tokenized vertical farm (~200 owners) proves the pattern at small scale. The near-term honest version: a community pre-buys a print farm's capacity; the compliance-heavy version follows the regulatory calendar (CLARITY Act still stalled as of this writing).
- **Production-run financing:** standing purchase orders and receivables become financeable through Centrifuge/Maple-class credit pools — with a structural advantage no off-chain lender has: the collateral (an in-progress production run) emits real-time verifiable telemetry. PoF makes production credit underwritable.
- **Network fee:** a flat, published protocol fee on settled orders (target: low single digits — the network's costs are real but it exists to route value to participants, not extract it). Fee governance is public (L5/governance). For comparison: incumbent marketplaces and design platforms take 10–50%.

### L5 — Interfaces & Governance

- **Surfaces:** a web marketplace (browse designs, order fabrication), a buyer/creator dashboard, the node operator app, and — most importantly — **the open API, designed agent-first**, because within a few years the modal buyer is somebody's AI assistant ordering a replacement part. BINGO should be the endpoint agents call when the physical world needs to change shape.
- **Governance:** phased. Stewardship starts with a foundation (mission-locked, transparent books), moves toward participant governance (creators, node operators, buyers as constituencies) as the network proves out. Governance controls fees, license templates, tier standards, and arbitration policy — not day-to-day operations. No governance token speculation; voting weight derives from verified participation (fabrication history, registered assets in use, purchase history), which is sybil-resistant because participation is PoF-verified and expensive to fake.

## 4. What carries forward from v2

The existing repo (thewriterben/ProjectBINGO) contributes, after honest triage:

**Keep and build on:**
- **The DGD escrow work** (`docs/DGD_PHASE0-5.md`, escrow controllers, signing UI) — the one deliberate, real piece of engineering in the repo. Non-custodial escrow with partial release and oracle verification becomes the settlement agent's core. Generalize the settlement asset; keep the architecture.
- **The core thesis** — "AI-matched manufacturing marketplace with trustless settlement" was right; v3 widens it.
- **The phase discipline** of PROJECT_PLAN/ROADMAP — research → requirements → MVP → pilot → scale remains the right skeleton, re-scoped below.
- **Service boundaries as concepts** — user/order/dispute/supply-chain map loosely to v3 concerns and can inform the eventual service decomposition.

**Retire:**
- The 11 skeletal microservices as *code* (~2,200 LOC of scaffolding; rebuilding costs less than rehabilitating).
- The undecided-option-list technical requirements ("React or Vue," "Ethereum, Polygon, or Solana") — v3 makes decisions.
- The Newerascontinue financial projections (explicitly non-transferable, per their own INDEX).
- Generic Ethereum-marketplace smart contracts — superseded by the settlement design above.

## 5. The thin vertical (proof the loop closes)

One demo, end to end, touching every layer minimally. Scope it to be buildable by one person plus agents:

**"Design → royalty → distributed print → verified → paid."**

1. A creator registers a real, useful design (asset hash + per-unit license + split contract on a testnet or low-cost chain). *(L1)*
2. A buyer orders N units through a minimal web UI; funds go to escrow (testnet stablecoin, or real dollars via Stripe held in a ledger that mirrors the contract). *(L5, L4)*
3. An orchestration script — the embryo of the pipeline — runs DFM checks (slice + printability heuristics), quotes from a rate card, and splits the run across **2–3 real printer nodes** (Benji's own machines + a friend's, or one Slant 3D API call as the "big node" to prove heterogeneity). *(L3, L2)*
4. Node agents (Klipper/Bambu integration) execute, streaming telemetry + timelapse hashes as PoF evidence. *(L2)*
5. On delivery confirmation, settlement executes one atomic distribution: shops paid, designer's royalty paid, network fee logged — visible on a public dashboard: **"Design #1 has earned its creator $X across Y units on Z machines."** *(L4)*

That dashboard number — a designer passively earning per-unit royalties from distributed fabrication — is the whole vision in one integer, and no platform today offers it. It is the demo for creators, node operators, collaborators, and (if ever wanted) funders alike.

**Deliberately excluded from the vertical:** machine RWA (securities counsel first), production credit, CNC/higher tiers, training-material royalties, governance. All follow; none are needed to prove the loop.

## 6. Roadmap (re-scoped)

- **Phase A — Specification (weeks 1–6):** protocol specs for L1 asset/license/split formats, node agent API, PoF evidence format, settlement flows. Written as open specs from day one (the neutrality principle starts at the spec). Parallel: securities counsel consult on the RWA path; license-template legal review.
- **Phase B — Thin vertical (weeks 4–16):** build §5. Real printers, real design, real (small) money. Everything open-source from the first commit.
- **Phase C — Closed pilot (weeks 16–30):** 10–20 creators, 5–10 nodes, 1 product category (functional consumer parts — brackets, fixtures, replacement parts — where Tier 0/1 quality suffices and Etsy-displaced sellers are hungry). Success metric: ≥1 creator earning recurring royalties they'd tweet about unprompted.
- **Phase D — Open the network (months 8–14):** public node onboarding, agent-first API, second process family (CNC via shops using CloudNC-class tooling), inspector/labor nodes, production credit experiment.
- **Phase E — Capital rails & governance (months 12+):** machine RWA under whatever regulatory regime exists by then; participant governance; training-material royalty metering as the network's own AI matures.

## 7. Honest risks

- **The oracle problem may resist layering.** If PoF can't make fraud uneconomical at Tier 0, the network's floor rises to established shops only — still valuable, but less revolutionary. Mitigation: start with low-stakes categories where occasional fraud is survivable and reputation compounds.
- **Churn economics are undefeated so far.** Every manufacturing marketplace has bled. The royalty/recurrence thesis is an argument, not yet evidence. The pilot's job is to produce the evidence.
- **Regulatory drift.** CLARITY stalled; the innovation exemption is young; machine RWA timing is not ours to choose. Mitigation: the core loop (design royalties + fabrication settlement in regulated stablecoins) has a clear legal path today under GENIUS-era rules — running settlement through licensed PSP/custody partners to stay clean on money-transmission — and the securities-adjacent pieces are sequenced last.
- **Cold start.** Two-sided (actually four-sided) network effects are brutal. Mitigation: each side gets standalone value before the network matters — creators get an enforcement-grade licensing registry, node operators get free farm orchestration software, buyers get transparent quotes. The Etsy/MakerWorld refugee wave is the seed community.
- **Incumporation.** Xometry + Siemens could bolt royalties onto their stack. They won't want to (their margin *is* the opacity), but if they do, an open protocol that forces the industry to pay creators per unit is a win condition, not a loss.
- **Scope gravity.** This document describes a decade. The thin vertical is four months. The discipline is shipping §5 before elaborating anything else.

## 8. What this is for

A teenager in a small town with a printer earns real money fabricating parts for neighbors, scheduled by agents, paid the minute the porch camera confirms delivery. A retired machinist's fixture library earns royalties from a thousand shops she'll never visit. A farmer's broken bracket is redesigned, printed twenty minutes away, and delivered same-day for less than shipping from Shenzhen. An open-hardware project funds itself from per-unit royalties instead of begging, because open *and paid* finally coexist. None of them needed permission, a platform's mercy, or a job they hate.

That's the machine we're building. The rest of this repo is the how.

---

*Companion documents: `docs/LANDSCAPE-2026.md` (evidence base) · v2 materials retained under `docs/` for history.*
