# Observability: a record that survives the incident

_Status: implemented (`bingo/audit.py`, `bingo/health.py`, `bingo/node/backup.py`), 42/42 suites. Written 2026-08-12._

## The question structured logging does not answer

The production-gap memo asks for "structured logging" under operational
maturity. JSON lines with a timestamp answer *what happened* to a reader who
trusts the file. After an incident the question is a different one:

> Is this file still telling me what happened, or did whoever got in delete the
> four lines about themselves?

**A log an attacker can edit is not evidence. It is a story.**

BINGO already owns the tool for this and uses it everywhere else: a hash-chained,
optionally signed event log, verifiable document-only by a stranger with nothing
installed. Same grammar as a fabrication passport or a custody chain, pointed at
the node's own behaviour.

## What is caught

| Tampering | Detected by |
|---|---|
| edit a record in place | its hash no longer matches its contents |
| delete a record | `seq` gap and a broken `prev` link |
| reorder two records | same |
| splice in a record from another log | the per-log id inside the signed body |
| forge a record with a re-chained hash | the signature, when signing is on |
| **truncate the tail** | **nothing inside the file** - see below |

Tail truncation deserves its own row because overclaiming here would be easy.
Lopping records off the end leaves a chain that is *internally perfect* - it is a
valid prefix, exactly like the coin ledger case in red-team round 6. Nothing in
the file can detect it. What catches it is comparing against a head you already
held, or an external anchor (`AuditLog.anchor_head`, `bingo/anchor.py`). The test
pins that boundary deliberately so nobody later assumes more than is true.

### A gap the splice test found

The first version of the splice test failed to fail, and the reason was
substantive rather than a test bug. **A hash chain identifies a sequence of
contents, not the log that produced it.** Two nodes that record the same events
in the same order build byte-identical chains, and a record lifted from one into
the other is undetectable - there is genuinely nothing to detect.

Fixed by minting a per-log id at genesis and carrying it *inside the signed
body*, so every record is bound to its own chain regardless of content. Both
cases are now pinned: the easy one (different content) and the one that was
silently passing.

## Redaction: biased, not indiscriminate

The most common way a security control becomes a vulnerability is by logging
what it was protecting. Bearer tokens, key seeds, passphrases, coin scratch
codes and `Authorization` headers never reach the log; the test puts *real*
secrets through the *real* code path and greps the actual serialized output.
Query strings are stripped from recorded paths, because coin credentials travel
there (`/api/coin?c=...`).

The bias runs toward redaction - blanking something harmless costs a less useful
log line, missing one puts a credential in a file people email each other. But
**over-broad redaction has its own failure mode: a log that hides the answer.** A
bare `"auth"` was in the key list and matched `authenticated`, silently blanking
the field that records whether a request passed authentication. That is a
*result*, not a credential, and it is precisely what an operator would use to
count failed intrusions. The entries now name credentials rather than topics.

## An audit write must never break the thing it observes

`AuditLog.append` never raises into its caller. A logging failure that can fail a
payout or turn a 200 into a 500 is a logging system that gets disabled by the
first person it inconveniences. Failures are recorded in `log.errors` and surface
as a **blocking** health check, and the gap shows up in the sequence numbers.

## Live is not ready

`bingo/health.py` answers two different questions, and conflating them is how a
misconfigured node quietly takes traffic:

- **live** - the process can serve. Restarting would not help. Poll this from a
  load balancer.
- **ready** - the process is in a configuration fit to hold real value.

Exactly one check blocks readiness: **the audit chain must verify.** A node whose
own record of itself does not verify is not a node anyone should send value to,
whatever else is true of it. Variable-time signing and a non-isolated store are
*warnings* - overstating a warning as an outage teaches people to ignore the
endpoint, which is worse than not having one.

The endpoint is safe to expose unauthenticated because it reports **properties,
never values**: whether a token is configured, never the token; which backend,
never what is in it. The most-scraped URL on any service must not become the
reconnaissance one.

## Backups, and the word that matters

`python -m bingo.node.backup out --to backups/2026-08-12` takes the backup.
`python -m bingo.node.backup --drill out` is the point:

> Every system that ever lost data had backups. What it did not have was a
> restore anyone had performed.

The drill takes a backup, restores it into scratch, and compares **record by
record** against the live node - not file sizes, not a checksum of the backup,
because a restore producing a same-sized file with different contents is exactly
what a checksum would miss. The audit chain must additionally still *verify*
after restore, since a scrambled restore would pass a count check. It is
read-only with respect to the live node, and meant to run on a schedule so a
backup that stops being restorable fails loudly on a day you do not need it.

**Key material is never backed up.** A backup is a file that ends up on laptops,
in object stores and on USB sticks, and the passphrase protecting those seeds is
one guess from being the only thing between a stolen backup and a stolen
identity. Key custody has its own threat model in `specs/KEY-CUSTODY.md`; a tool
that quietly swept keys into a nightly tarball would undo it. There is a test
that would fail the day someone "fixes" this for completeness.

## Still open

- **Alerting does not exist.** Nothing watches the health endpoint or the audit
  stream and tells a human. `sentinel/` is the natural home; this increment
  produced the signal, not the notification.
- **No log shipping.** `export_jsonl` writes the file; getting it off the box
  before an intruder deletes it is unsolved, and deletion is the one tampering
  mode the chain cannot catch alone.
- **Anchoring is a seam, not a deployment.** `anchor_head()` exists; running a
  transparency log operator with independent witnesses is still the unsolved
  organizational half, same as §5 of the memo.
- **Concurrent appenders fork the chain under the JSON backend.** Detected, not
  silent - but a detected corruption is still a corruption, and an audit log
  that fails to verify is one you cannot use. `$BINGO_STORE=sqlite` on any node
  with more than one writer.
- **No metrics.** No counters, no latency histograms, nothing a time-series
  system could scrape. The audit log is evidence, not telemetry, and using it as
  both would compromise it as either.
