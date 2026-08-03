# Spec: Node Agent (L2)

**Version 0.1 — draft.** The node agent is open-source software a fabricator runs to join the network. It speaks to local machines through drivers, advertises capabilities, accepts jobs, streams signed telemetry, and gets paid by settlement.

## Identity

- Each **node** (an operator's site) holds a keypair (`ed25519`; the v0 prototype uses HMAC with a node secret as a stand-in — the interface is identical: `sign(payload) → sig`).
- Each **machine** under a node has a machine record: `{machine_id, driver, make/model, process, envelope_mm, materials[], tier}`.
- **Human labor registers the same way**: an inspector/finisher/courier is a node with `process: "inspection" | "finishing" | "courier"` and a capability profile instead of an envelope. Same jobs, same evidence, same settlement.

## Capability tiers

| tier | who | typical work | PoF burden |
|---|---|---|---|
| 0 | hobbyist FDM | consumer goods, low-stakes parts | telemetry + frames |
| 1 | professional additive / basic subtractive | functional parts, small runs | + calibrated sample checks |
| 2 | certified shop | toleranced parts, material certs | + second-party QA attestation |
| 3 | specialized (PCBA, tooling, sheet metal) | per specialty | + specialty-specific evidence |

Orders route to the **minimum tier satisfying the spec**. New nodes enter at tier 0 economics regardless of equipment and graduate via history.

## Job lifecycle

```
OFFERED → ACCEPTED → PREPARING → RUNNING → COMPLETE → SHIPPED → DELIVERED → SETTLED
                 ↘ DECLINED                ↘ FAILED (re-routed by orchestrator)
```

A **job** is a batch of units of one asset on one node. Node API (HTTP+JSON in production; in-process in the prototype):

- `GET  /capabilities` → node record + machine list + current load
- `POST /jobs` (offer: asset ref, qty, material, deadline, payment terms) → accept/decline
- `GET  /jobs/{id}` → status + evidence chain so far
- `POST /jobs/{id}/cancel`

## Proof-of-Fabrication (PoF)

PoF is a **hash-chained, Ed25519-signed event log** per job. Each event: `{seq, ts, type, data, prev_hash, sig}` where `prev_hash` chains to the prior event, so the log cannot be reordered or trimmed after the fact, and each event is signed at capture time with the node's Ed25519 key (commitments are cheap; storage of the underlying frames/logs can be lazy). The node's public key is published on its node record and embedded in the `JOB_ACCEPTED` event, so the chain is **self-describing**: anyone holding the public key can verify the entire log independently — hash integrity *and* authorship — without any secret. (v0 ships a stdlib-only pure-Python Ed25519, cross-checked byte-for-byte against RFC 8032 / the `cryptography` library.)

v0 event types:

| type | data |
|---|---|
| `JOB_ACCEPTED` | job terms hash |
| `INPUT_HASH` | sha256 of gcode/toolpath actually loaded |
| `TELEMETRY` | sampled machine state (temps, progress, position) |
| `FRAME` | sha256 of camera capture + stage label |
| `UNIT_COMPLETE` | unit serial, duration, material used |
| `QA` | checklist results; signer may be a second party (tier ≥ 2) |
| `SHIPMENT` | carrier, tracking id, label hash |
| `DELIVERY_CONFIRMED` | carrier webhook / buyer confirmation — **settlement trigger** |

**Trust model (layered, tier-scaled):** no single evidence type is trusted. Telemetry can be forged by a determined node; frames make forgery costlier; QA attestation adds a second staked party; **reputation staking** makes fraud net-negative (confirmed fraud slashes staked earnings history and expels); **arbitration** by staked human arbitrators is the backstop. The design goal is economic: cheating must cost more than honest work at every tier. Low tiers tolerate residual fraud risk via low-stakes order routing.

## Drivers

Driver interface: `prepare(job) → start(unit) → poll() → events`. v0 drivers:

- `mock` — full simulation (prototype/demo)
- `moonraker` — Klipper via Moonraker HTTP API (`/printer/objects/query`, `/printer/print/start`, webcam snapshot for frames)
- `bambu` — Bambu Lab in LAN/Developer Mode (MQTT telemetry + chamber camera)

## Batch & manual-mode evidence (MSLA and undriven machines)

Batch processes (resin plates) and machines without a live driver run in
**manual-attested mode**: the operator attests stage events (batch start,
post-cure) and commits photo hashes as `FRAME` evidence at attestation time.
The chain is identical — hash-linked, signed — but the observer is human, so
the trust load shifts per the tier model: manual-mode jobs REQUIRE
first-article certification per (design, process-package) pair by a paid
inspector node, plus spot-check cadence (every Nth batch physically pulled).
A batch reporting fewer good units than plated fails whole in v0 (nothing
settles, escrow refunds); partial-batch settlement is a v0.2 item.

**Job-class certification:** narrower than tier — a node is certified for a
specific (design, package) pair after a passed first article, and only that
job class routes to it at the declared grade. Certification events live in
the node's reputation record.

Reputation: `score ∈ [0,1]` from completion rate, QA pass rate, on-time rate, dispute outcomes; time-decayed; staked (a slashable fraction of accrued earnings). Nodes may declare `materials_on_hand`; matching routes around declared-dry nodes so one late resin bottle never stalls a run.
