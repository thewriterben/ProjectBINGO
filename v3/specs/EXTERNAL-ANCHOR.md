# The external anchor

_Status: implemented (`bingo/anchor.py`), 35/35 suites. Written 2026-08-11._

## The problem, twice

Two limitations documented independently in this codebase turned out to be one
limitation wearing two hats:

- **`provenance/coin.py`** - the anti-rollback sidecar pins the last head and
  length, but says outright: "if an attacker can rewrite the anchor too," a
  single self-contained artifact cannot detect a rollback.
- **`bingo/keydir.py`** - a document cannot prove its own age, so someone holding
  a stolen-then-revoked key can always *assert* the signature predates the
  revocation.

Neither is fixable with more signing. The attacker controls every byte of the
artifact they hand you, including any sequence number or timestamp it claims. A
signature proves *who*, and a hash chain proves *this order within this
document* - but nothing inside a document can prove *when, relative to the rest of
the world*. That needs something outside it.

## What it is

A Merkle transparency log - the construction Certificate Transparency uses for
exactly this problem (RFC 6962), implemented in stdlib on the existing kernel.

- **Inclusion proof** - "this statement is in the log at index `i`, under a tree
  of size `n` with root `R`." O(log n) hashes. Answers *was this ever logged?*
- **Consistency proof** - "the tree of size `n` is an append-only extension of the
  earlier tree of size `m`." Answers *did the operator quietly rewrite history?*
  A log that edits or drops a committed entry **cannot produce one** - which is
  what turns rollback from "forbidden" into "detectable."

Hashing is domain-separated exactly as RFC 6962 specifies (`0x00` for leaves,
`0x01` for internal nodes), so an internal node can never be replayed as a logged
statement.

The log stores *hashes*, not content. What is anchored is "this exact artifact
existed by the time the log reached size n"; the artifact stays with whoever holds
it. The anchor is cheap and leaks nothing.

### Correctness

Merkle proof code is easy to get subtly wrong, so it is verified by construction
rather than by inspection: inclusion proofs are checked **exhaustively** for every
tree size 1..24 and every index (including that a proof does not transfer to a
different index), consistency proofs for **every** `(old, new)` pair in that
range, plus 200 randomized rewrite attempts that must all fail to prove
consistent. See `tests/test_anchor.py`.

## Monotonicity: `AnchorService`

A bare log proves *a* statement was logged. A party guarding against **rollback**
needs the opposite question answered - *"what is the LATEST thing anchored under
this key?"* Without that, an attacker who rolls a ledger back to an earlier state
presents the earlier state's perfectly genuine receipt and every proof checks out.

`AnchorService` is the operator-side index that answers it: `anchor(key, payload)`
and `receipt(key)` for the most recent one. It is not a trust addition - everything
it returns is still backed by an inclusion proof against a signed head - it just
supplies the ordering fact the disk-owner cannot supply about themselves.

## Witnesses: what consistency proofs do not fix

Consistency proofs let anyone *who saw an earlier head* detect a rewrite. They do
not stop a log operator **equivocating** - showing one history to you and a
different one to someone else. Neither view is internally inconsistent.

`Witness` is the answer: an independent party that cosigns a tree head **only if
it is consistent with the last head it signed**. A witness that refuses is the
alarm. To fool a relying party checking `k` witnesses, the operator now has to
corrupt `k` independent parties. This is the same reason CT added witness
cosigning, and `verify_witness_quorum()` is fail-closed - unknown witness, bad
signature, or too few cosignatures is a refusal.

## Closing the key-revocation gap

`verify_as_identity()` no longer accepts an *asserted* pre-revocation position.
Accepting a revoked key's signature now requires proof that the signature was
logged **before** the revocation was:

```python
verify_as_identity(msg, sig, directory_doc, anchor={
    "log_pubkey": ..., "revoked_payload": ...,
    "receipt": {"index": i, "sth": {...}, "inclusion": [...]},
    "revocation_receipt": {"index": j, "sth": {...}, "inclusion": [...]},
    "witness_keys": {...}, "quorum": 2,
})
```

Both halves must verify against the same log, and `i < j` strictly. An attacker
who logs their forgery *after* the revocation gets a perfectly valid inclusion
proof and is still refused - **order is the claim**, not mere presence.

## What this actually buys, stated honestly

It does not produce a proof out of nothing. It converts *"trust whatever the
document says about when it was signed"* - a claim the attacker writes themselves,
worth nothing - into *"trust that the log operator and a quorum of independent
witnesses are not all colluding."* That is still a trust assumption. It is a
bounded one, chosen by the relying party, and vastly stronger than what it
replaces.

It also proves **order, not wall-clock time**. That is deliberate: both problems
this was built for are ordering questions ("before or after the revocation?",
"was this entry dropped?"), and wall-clock time would need a timestamp authority
and buy nothing extra here.

## Still open

- ~~**The coin rollback limitation is not yet wired up.**~~ **DONE.**
  `provenance/coin.py` now takes an optional `anchor_service`; when one is
  configured it is **authoritative over the local sidecar** and the check is
  required, not advisory (a missing log key or an unverifiable receipt refuses
  the load rather than degrading to "unanchored"). `tests/test_coin_anchor.py`
  runs the exact attack the module docstring used to concede - truncate the
  signed ledger *and* rewrite `<store>.anchor` so it agrees - **twice**: once
  without a log, where it succeeds and the coin is spent again, and once with,
  where it is refused. Truncation to a legitimately-signed shorter *prefix* (the
  version where nothing on disk looks forged at all) is caught the same way.
- **No log operator is deployed.** `TransparencyLog` runs in-process; production
  needs someone to actually run it, publish heads, and serve proofs - plus real
  independent witnesses, which is an organizational problem more than a technical
  one.
- **No gossip protocol.** Witness cosigning detects equivocation only if relying
  parties actually compare heads. CT solved this with gossip; we have not.
- **Unaudited**, like the rest of the crypto here.
