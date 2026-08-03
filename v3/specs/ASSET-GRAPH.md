# Spec: Asset Graph (L1)

**Version 0.1 — draft.** Formats are JSON; all money is integer cents (USD-denominated for v0); all hashes are SHA-256 hex; all timestamps are RFC 3339 UTC.

## Asset manifest

An asset is anything the network can use: a part design, an assembly, a print/machining profile, firmware, a QC procedure, or training material. The asset ID is the SHA-256 of its canonical manifest (content addressing — the manifest embeds the content hash, so the ID commits to both metadata and bytes).

```json
{
  "schema": "bingo/asset/0.1",
  "kind": "design",                     // design | profile | software | qc-procedure | training-material
  "title": "PB-001 shelf bracket",
  "creator": "acct:ben",                // account URI of registrant
  "content": {
    "files": [{ "name": "bracket.stl", "sha256": "…", "bytes": 1284, "media_type": "model/stl" }],
    "storage": ["ipfs://…", "https://…"] // ≥1 retrieval hint; availability > ideology
  },
  "license": { … },                     // see License
  "split": { … },                       // see Royalty split
  "derives_from": [                     // empty for original works
    { "asset_id": "…", "parent_share_bps": 2000 }
  ],
  "registered_at": "2026-08-03T00:00:00Z",
  "signature": "…"                      // registrant signs the manifest (ed25519; HMAC placeholder in v0 prototype)
}
```

Registration is **timestamped attestation, not copyright adjudication**. Disputes route to the arbitration backstop (see NODE-AGENT.md §Reputation).

## License

Licenses are machine-readable template + parameters. v0 templates:

| template | meaning | parameters |
|---|---|---|
| `personal` | fabricate for own use only | — |
| `commercial-flat` | unlimited network fabrication after one-time fee | `flat_fee_cents` |
| `commercial-per-unit` | royalty per unit fabricated on-network | `per_unit_cents` |
| `open-attribution` | free fabrication, attribution propagated in provenance | — |
| `network-training` | asset may train network agents; metered share of network fees | `training_share_bps` |

A design may carry multiple templates (e.g. `open-attribution` for hobbyists + `commercial-per-unit` for commercial orders). The order's declared use selects the template; misdeclaration is a reputation/arbitration matter, like all fraud.

## Royalty split

A split is an immutable payout tree in basis points, summing to exactly 10 000.

```json
{
  "schema": "bingo/split/0.1",
  "payees": [
    { "account": "acct:ben", "bps": 8000 },
    { "account": "acct:collaborator", "bps": 2000 }
  ]
}
```

**Derivative composition rule:** if asset B declares `derives_from: [{A, parent_share_bps: p}]`, then B's *effective* split is: A's effective split scaled by `p`, plus B's declared payees scaled by `10000 − p`. Composition is computed at registration time and frozen into B's manifest (`effective_split`), so settlement never needs graph traversal and a later re-registration of A cannot change B's obligations. Chains compose recursively (a remix of a remix embeds both ancestors). Sum must remain exactly 10 000 after integer scaling; residue from rounding goes to the first payee (deterministic).

**Enforcement model:** the split is not a promise — settlement (SETTLEMENT.md) refuses to release fabrication payment except through the design's effective split. On-network fabrication cannot route around it. Off-network leakage (a leaked file printed privately) is out of scope for enforcement and in scope for the network's value proposition: being *on* the network is what earns distribution, logistics, financing, and buyers.

## Provenance record

Every fabricated unit gets a provenance record binding: asset ID → order ID → job ID → node/machine ID → PoF evidence chain hash → delivery confirmation. This is the "birth certificate" that makes per-unit royalties auditable and gives buyers verifiable origin.
