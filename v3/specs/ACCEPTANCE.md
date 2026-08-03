# Spec: Acceptance Grades & Defect Materiality

**Version 0.1 — draft.** The trust core of the network: what "good" means is
declared before fabrication, frozen into the job terms, and everything
downstream — matching, payout, reputation, arbitration — measures against the
declaration, never against opinion.

## The principle

A defect has no weight unless it has consequence *against the declared
expectation*. Surface artifacts on a functional part are a non-event; the same
artifacts on a display piece are a real shortfall. The network does not hold
one universal quality bar — it holds every party to the bar they agreed to,
and prices the difference.

## Acceptance grades

Declared per order line at intake; price scales with grade:

| grade | name | the promise | typical checks |
|---|---|---|---|
| **F** | Functional | fits, works, survives its use; cosmetics irrelevant | dimensional (declared critical dims ± tol), material, functional test if declared |
| **S** | Standard | F, plus workmanlike finish: no gross defects on visible surfaces | F checks + layer adhesion, no blobs/scars beyond threshold on marked faces |
| **P** | Premium | F, plus finish quality on marked surfaces; the "it must look right" tier | S checks + surface class per face, color match, agreed post-processing |

Each grade resolves to a concrete **acceptance checklist** generated at order
time (from the asset's spec + the buyer's declarations). The checklist's hash
is committed into the `JOB_ACCEPTED` PoF event — expectations are literally
part of the signed job terms. Neither side can move the bar afterward.

**Buyer-side transparency:** at intake the buyer is shown what each grade
means for THIS part — reference imagery of grade-F vs grade-P outcomes,
price difference, lead-time difference — and must pick. "Customers must
understand exactly what they are asking for" is an interface obligation of
the intake agent, not fine print.

## Defect materiality

When a deviation is found (by buyer, QA, or vision screening), it is scored
on consequence, not existence:

1. **In-grade?** Does the checklist for the declared grade even cover it?
   An ironing artifact on a grade-F order is *out of scope* — no impact,
   no mention, no reputation event.
2. **Functional cascade?** Did it impair the declared use, or propagate
   (warp → misfit → assembly failure)? This is the heavyweight class.
3. **Economic consequence?** Would remedy require rework, markdown, or
   replacement? Materiality weight ∝ remedy cost, bounded by job value.

Only material deviations touch payout or reputation. Remedies scale:
accept-as-is (no event) → cosmetic partial credit (grade P shortfalls) →
reprint at node's cost → refund + reputation event. Frivolous claims cost
the claimant: a buyer whose dispute is scored out-of-grade pays the
arbitration fee and accrues a claim-quality history of their own.

## Reputation is a vector, not a scalar

A node's reputation is per-grade (and per-process): demonstrated consistency
at F, at S, at P — plus timeliness and dispute history. Consequences:

- **Routing = expectation matching.** Premium-demanding buyers route to nodes
  with proven P-grade consistency; a picky customer is a *premium customer*,
  and the node that can satisfy them earns a rate premium for it. Grade-F
  work routes wide — every capable node competes.
- A node is never penalized for the grade it didn't promise. A bedroom
  printer with flawless F-grade history has *excellent* reputation, full
  stop. Grades are markets, not ranks.
- **Buyers have reputation symmetry:** declared-grade dispute rate, claim
  quality. Chronic out-of-grade claimants get priced accordingly by nodes
  choosing whether to accept their offers.

## Arbitration anchored to the frozen checklist

The arbitrator's only question: *does the delivered part meet the checklist
whose hash is in the signed job terms?* — decided against the PoF evidence
chain and delivered-part imagery. Not "is it perfect," not "would I be
happy." Buyer remorse is not a defect; an unmet checklist line is. This is
what makes arbitration cheap, fast, and consistent enough to be staked
human work rather than a court case.

## Why this is the point of the whole system

Human marketplaces resolve quality disputes through power: whoever the
platform fears more wins. This network resolves them through structure:
expectations frozen and hashed before work begins, evidence signed as work
happens, settlement deterministic when the two match. The trust ceiling of
a handshake is the honesty of the two hands; the trust ceiling here is the
integrity of the checklist and the chain — which is exactly the kind of
trust AI and cryptography can manufacture at scale and humans alone cannot.
If the network delivers that, transacting with a stranger's printer three
states away becomes safer than transacting with a known vendor on a
platform's mercy. That is the product.
