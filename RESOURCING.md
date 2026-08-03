# Project BINGO — Potential Value & Required Capital

*Companion to VISION.md. August 2026. Honest numbers, milestone-gated.*

---

## 1. Potential value, framed correctly

Because this project is not profit-motivated, "value" has two ledgers: what flows *through* the network to participants, and what the network itself needs to sustain operations. The right headline metric is **participant earnings**, not enterprise value: of every $100 of orders, ~$97 goes to creators, node operators, inspectors, and carriers; ~$3 sustains the network.

**Serviceable market, honestly bounded.** On-demand/custom parts manufacturing is a $25–40B+ segment; Xometry — the category winner — runs ~$800M/yr through it, i.e. low-single-digit penetration after a decade and ~$300M+ of invested capital. The functional-design creator economy barely exists as a paid market today (MakerWorld, Printables et al. pay out single-digit millions per year at 10–20% platform takes); the opportunity is *creating* the per-unit royalty category, not capturing an existing one.

**Concrete value milestones:**

| network scale | GMV/yr | participant earnings/yr | network fee (3%) | comparable |
|---|---|---|---|---|
| Pilot proof | $50K | ~$48K | $1.5K | 20 creators, 10 nodes, 1 category |
| Regional network | $5M | ~$4.8M | $150K | self-sustaining ops, no subsidy |
| Category-real | $100M | ~$97M | $3M | ~1% of Xometry's decade-in scale |
| Norm-setting | $1B+ | ~$970M | $30M | per-unit royalties become industry-standard |

The largest value is the least quantifiable: an existence proof that AI-orchestrated automation can pay the people it depends on, per use, structurally. The mechanism precedent — if it takes hold the way app-store revenue sharing did — is worth more than any plausible fee revenue.

## 2. The team something substantial requires

AI leverage is real and already demonstrated (this prototype was built in hours, not months), so the engineering line is roughly half of what it was in 2018. What AI does *not* compress: community operations, legal structure, physical QA, and support. Fully-loaded costs (salary × ~1.3 for tax/benefits), 2026 US rates:

| role | why it can't be skipped | FTE | loaded cost/yr |
|---|---|---|---|
| Founding engineer (protocol/settlement) | the money path must be boringly correct | 1 | $210–290K |
| Hardware integration engineer | drivers, firmware quirks, QA rigs — physical-world code resists AI leverage | 1 | $170–235K |
| Community & operations lead | onboarding creators/nodes, disputes, support; this IS the product's trust layer | 1 | $105–155K |
| Founder (Ben) | vision, architecture, partnerships — currently unpaid, which is a real line item, not zero | 1 | market: $150–200K |
| Securities/licensing counsel | RegCF setup, license templates, ToS, state money-transmission review | fractional | $60–150K over 18 mo |
| Accounting / 1099-K compliance | thousands of micro-payees is a tax-ops problem from day one | fractional | $20–40K/yr |
| Product liability insurance | a printed part fails in someone's hands eventually | — | $15–40K/yr |
| Design/UX contract | dashboard, storefront, node app | contract | $30–60K one-time |

**Lean AI-native configuration** (founder + 1 senior engineer + ops lead + fractional everything): **~$450–650K/yr burn**.
**Full configuration** (all rows above): **~$800K–1.1M/yr burn**.

## 3. Capital plan, milestone-gated

Each phase's capital is only justified if the previous phase's gate was passed. Skipping gates is how the graveyard filled.

**Phase 0 — Proof of desire. $0–10K, months 0–3 (current).**
Thin vertical on real hardware (done as of tonight), open-source release, 20-creator/10-node pilot in one category (functional consumer parts; the Etsy/MakerWorld-displaced community is the seed). Costs: filament, shipping, a few hardware subsidies, incorporation of a stewardship entity.
*Gate: strangers transacting — at least one creator and one node operator who have never met Ben earning real money.*

**Phase 1 — Legal money, real network. $250–500K, months 3–12.**
Stripe Connect (or equivalent PSP) so dollars flow compliantly; license templates hardened by counsel; 50–100 nodes across 3+ metros; first repeat buyers; ops lead hired; insurance bound. Lean team config, part-year.
*Gate: $10K+/month GMV with organic repeat purchase and a node/creator NPS that recruits itself.*

**Phase 2 — Something substantial. $1.5–3M, months 12–30.**
Full team; multi-city network with tiered QA; CNC/second process family; production-credit pilot with a Centrifuge-class partner; agent-first API public. This is the 24-month build referenced above at $800K–1.1M/yr plus $200–400K of node subsidies, demand generation, and legal.
*Gate: a regional network that clears $5M/yr GMV without per-order subsidy.*

**Phase 3 — Optional scale. $5–15M, months 30+.**
Machine RWA under matured regulation (registered, compliant), buyer-side demand engine, international. Only raise this if Phase 2's unit economics beat the churn curse — Shapeways ($100M+, bankrupt) and Fictiv ($188M, distressed sale) prove capital cannot substitute for that answer.

**Total to "something substantial": ~$2–3.5M over ~30 months.** With aggressive AI leverage and a founder drawing little: plausibly $1.2–2M. Below that, the constraint isn't code — it's that community ops, legal, and physical trust are bought with salaries and years.

## 4. Where the capital can come from without corrupting the mission

**The Digital Gold position changes this section.** Ben co-created DGD (digitalgold.co), now past $80M market cap, with an existing Foundation, community, and legal architecture built specifically to avoid securities classification. That is a materially different starting position from the typical cold-start founder, in three ways:

1. **Capital access.** A Foundation-aligned allocation or ecosystem grant from the DGD side could fund Phases 0–1 ($250–500K) without any external raise, on mission-aligned terms no VC would offer. Honest caveat: market cap is not treasury — what matters is liquid, governance-approved funds, and converting meaningful size against real DGD liquidity without moving the price. Budget from what can actually be deployed, not from the ticker.
2. **A settlement rail with a community attached.** BINGO's settlement layer already generalizes the v2 DGD escrow design; DGD as a supported settlement asset now comes with tens of thousands of potential first participants rather than zero. The DGD community is a plausible seed for node operators and first buyers — distribution, not just money.
3. **Regulatory nuance to respect.** Gold-backed tokens are not "payment stablecoins" under GENIUS (that regime is USD-pegged); they trade as commodity-backed assets (cf. PAXG/XAUT). So: DGD escrow and DGD payouts as an *option* — with USD/GENIUS-stablecoin rails as the default for US participants who don't want commodity tax accounting on every royalty — and clean disclosure that the founder of the network co-created the settlement asset. That conflict is manageable if it's loud and optional, corrosive if it's quiet and required.

Beyond the DGD position:

- **Grants** ($50–300K realistic): open-source infrastructure funders, DePIN ecosystem foundations (peaq, Sui, Filecoin have active programs), NSF SBIR (advanced manufacturing track), fiscal sponsorship via Open Collective in the interim.
- **Regulation Crowdfunding** (up to $5M/12 mo): the mission-aligned instrument — the creators and node operators *become* the owners. Slower, compliance-heavy, and exactly on-thesis.
- **Mission-aligned angels/PBC equity**: acceptable if the entity is a public-benefit corporation or steward-owned structure with the protocol specs irrevocably open. 
- **Not**: a token sale. The landscape research is unambiguous — every predecessor that led with a token died of it. If a network asset ever exists, it comes after revenue, under real regulation, and is never required to participate.
- **Structure**: two-entity pattern — a foundation/coop stewarding the open protocol + a PBC operating company running the reference services. Standard, boring, proven (Linux Foundation → member companies; Signal Foundation → LLC).

## 5. Time — the honest denominator

Software: months (AI has genuinely collapsed this). Network trust: years — Xometry needed ~10 to profitability *with* centralized control. Regulatory clarity for the RWA layer: not ours to schedule (CLARITY still stalled). Founder-time is the single largest capital line in every phase, and the only one that cannot be raised.

The sequencing that respects all of this: **prove desire with $10K before raising $500K; prove economics with $500K before raising $3M.** Each gate passed makes the next raise cheaper and more honest. Each gate skipped is a Shapeways.

## 6. Why this answers the sentiment problem

The public isn't rejecting AI's capability; it's rejecting its distribution. Every phase above ends with a number that ordinary people can verify in their own bank accounts: royalties paid, jobs routed, machines financed by neighbors. Twenty real people earning real money by winter is a stronger argument for AI's legitimacy than any demo, benchmark, or manifesto — and it compounds: every participant becomes the argument. That is the potential value that doesn't fit in the GMV table, and it's the one the project exists for.
