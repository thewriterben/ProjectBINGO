# Promise Integrity — the second workstream

*Adopted as a standing goal, August 2026. Sibling to the fabrication network; same root, wider blast radius.*

## The problem class

Modern systems make promises no component owns. "Arriving Tuesday" is a statistical estimate typeset as a commitment; when reality diverges, no part of the system is responsible for the gap, the person affected detects the anomaly before the system admits it, and the aftermath cannot be reconstructed even by the operator's own support staff. The human in the equation has total stakes, partial visibility, and zero agency. This is not a manufacturing problem — it is the shape of nearly every bad interaction ordinary people have with automated systems: deliveries, claims, applications, repairs, refunds, appointments.

The gap is not model capability. It is three deployment failures:

1. **Observability** — the edge is denied the state the center holds.
2. **Agency** — the edge cannot act inside the system even when it sees the failure coming.
3. **Allegiance** — deployed AI overwhelmingly serves the counterparty. Support bots deflect; recommendation engines extract; anomaly detection guards the warehouse, not the waiting customer. The organizations able to ship agents at scale are the ones whose incentives point away from shipping *this* agent.

Public confidence in AI will be won or lost here, in the equation: **promises kept + failures explained.** Today's systems do neither, and every unexplained failure is another person concluding this technology isn't for them.

## The solution shape: the edge agent

An agent that works for the person, holding counterparties' promises against observed reality:

- **Promise as first-class object.** Anything owed to you gets a record: who promised, what, by when, evidence, and the observable signals that should track it. A promise that can't be checked is flagged as such at creation — that too is information.
- **Watch.** The agent monitors available signals (tracking feeds, status pages, email/receipts, timelines-vs-norms) and compares trajectory against the pattern of kept promises. Divergence-from-norm is detectable long before breach — Ben detected it by eye; an agent does it continuously.
- **Warn early, with options.** Not "your package is delayed" after the fact — "this is off-pattern *now*; here are your options and their deadlines" while options still exist.
- **Act asynchronously.** Escalate with full state attached, rebook, cancel-and-reorder before cutoffs, file the claim — under standing authorization with caps. Never require the human to catch a phone call.
- **Remember.** Every resolution becomes a record of how that counterparty keeps promises — an individual's (and eventually a commons') accountability memory that no platform can edit.

## Relationship to BINGO

BINGO is instance #1: a full economy built promise-native, where every commitment (delivery, quality grade, custody, payment) is a signed first-class object and settlement enforces the keeping. The specs already written — ACCEPTANCE.md (expectations frozen before work), LOGISTICS.md (one custodian at every instant, exceptions as states with deadlines, deterministic loss attribution) — are Promise Integrity applied inside a system we control end-to-end.

The edge agent is the same discipline pointed outward at systems we *don't* control, where it works with degraded observability and no enforcement — warning, acting, and remembering instead of settling. The two meet in the middle: as counterparties join the network, their promises graduate from watched to enforced.

## First buildable artifact: the Sentinel (v0)

A personal promise-watchdog, buildable with today's pieces, no counterparty permission needed:

1. A promise ledger (a simple doc/store): each entry = counterparty, promise, deadline, tracking signal, standing instructions, status.
2. A scheduled agent that sweeps the ledger daily (or faster near deadlines): checks signals, compares against norms, updates status, and alerts ONLY on divergence or approaching-deadline-with-options — quiet when things are on track.
3. On breach: drafts the escalation with the full state attached (timeline, evidence, what was promised, what happened), ready to send — the "cluster of fucks" reconstructed automatically, because the record was kept from the start.
4. Every outcome logged to the counterparty's file: a private accountability memory that compounds.

v0 is one user (Ben) and unglamorous plumbing. That's correct — BINGO started as one printer. The measure of success is the same: the first moment the agent catches a divergence before its human does, and the human had options because of it.

## The standard to hold

Any system we ship must pass the test today's systems fail: it keeps its promises or it exposes its state — always at least one, aspiring to both. No estimate dressed as a commitment. No exception without a next action and a deadline. No failure the affected person can't reconstruct. If AI can't be used to give ordinary people that much, it doesn't deserve their confidence — and if it can, this is what earning it looks like.
