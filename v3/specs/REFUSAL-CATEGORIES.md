# Spec: Refusal Categories & Policy Gating

**Version 0.1 — DRAFT, unreviewed.** Written 2026-08-15 per platform decision
PD-5 (OpenDesignCore `wiki/concepts/platform-decisions.md`): legality gating is
two-tier — design-time refusal at the assistants, fabrication-time refusal at
the nodes — and this network owns the shared category taxonomy. Formats JSON,
hashes SHA-256 hex, timestamps RFC 3339 UTC, matching the other L1 specs.

## The principle

The network does not adjudicate law and does not generate legal claims. It does
three narrower things: (1) names a small, human-maintained set of **categories**
of things that are commonly restricted; (2) requires assets and orders to
**declare** their categories, with misdeclaration handled exactly like license
misdeclaration — fraud, a reputation/arbitration matter; (3) lets every node
**refuse** categories outright, so nothing in a refused category is ever routed
to it. Default stances below are network policy, chosen conservatively;
per-jurisdiction legal mappings are explicitly out of scope for v0 and marked
TODO(source) wherever asserted.

## Taxonomy v0

| category id | covers | default network stance |
|---|---|---|
| `weapons.firearms` | firearms, receivers/frames, suppressors, fire-control parts, magazines | **refuse network-wide** |
| `weapons.other` | items designed as weapons that are not firearms | **refuse network-wide** |
| `regulated.medical` | implants, load-bearing prosthetics, anything marketed with medical claims | refuse unless node opts in and buyer supplies declared certification context |
| `regulated.safety-critical` | certified aviation/automotive/structural parts represented as conforming | refuse unless node opts in with declared certification context |
| `regulated.rf` | RF transmitters outside licence-free operation | node opt-in |
| `covert.surveillance` | skimmers, covert capture devices, credential-theft hardware | **refuse network-wide** |
| `bypass.tools` | lock-bypass and entry tools | node opt-in (jurisdiction-varying; TODO(source)) |
| `ip.counterfeit` | reproductions of trademarked/branded goods represented as genuine | **refuse network-wide** |
| `restricted.paraphernalia` | items restricted in many localities (e.g. drug paraphernalia) | node opt-in (jurisdiction-varying; TODO(source)) |

`none` is the implicit declaration for everything else. The list is intended to
stay small; growth requires a spec revision, not an enum edit in code.

## Where declarations live

- **Asset manifest** (ASSET-GRAPH v0.2 proposal): optional
  `"policy_categories": ["<id>", …]`; absent means `none` **as a declaration**,
  with the same fraud consequences as any misdeclaration.
- **Node record** (NODE-AGENT `/capabilities`): required
  `"refuses": ["<id>", …]` and `"jurisdiction": "<ISO 3166-2>"`. A node may
  refuse anything, including `none`-declared kinds it dislikes; refusal is
  never a reputation event.
- **Matching**: an order whose asset declares category C is routed only to
  nodes that (a) do not refuse C and (b) have opted in where the default
  stance requires opt-in. Network-wide-refuse categories are not routed at all.
- **Intake agent** (L3): screens declarations against geometry/description at
  intake, same posture as the acceptance-grade transparency obligation —
  an interface duty, not fine print. Design-time assistants (OpenDesignCore,
  OpenCircuitCore, deployment tools) apply the same category ids when
  declining to design, so a refusal upstream and a refusal at a node speak
  the same vocabulary.
- **Arbitration**: disputes over declarations resolve against the asset bytes
  and the frozen category list version (this file's hash at order time),
  mirroring the frozen-checklist pattern in ACCEPTANCE.md.

## What this is not

Not a compliance oracle, not legal advice, not a promise that a routed job is
lawful anywhere in particular. Buyers and nodes remain responsible for their
own law. The taxonomy makes good-faith refusal *cheap, shared, and enforceable
at matching time* — that is all, and that is a lot.

## Open

- Per-jurisdiction category mappings: who maintains them, citation standard —
  every entry TODO(source) until then.
- Category list versioning: commit hash of this file into `JOB_ACCEPTED`
  alongside the acceptance checklist hash.
- Vision-screening hooks (ClawCam-style) for intake declaration checks.
