# Observability: a record that survives the incident

_Status: implemented (`bingo/audit.py`, `bingo/health.py`, `bingo/alert.py`, `bingo/node/{backup,watch}.py`), 43/43 suites. Written 2026-08-12._

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

## Alerting: telling a human without training them to ignore you

Everything above produces signal. Nothing read it, and a signal nobody is
watching is a signal that does not exist - "the dashboard would have shown it" is
what people say after an outage nobody saw.

The hard part is not delivery. Delivery is a POST. **The failure mode of an
alerting system is being ignored, and an ignored alerter is worse than none
because it looks like coverage.** So most of `bingo/alert.py`, and most of its
tests, are about restraint:

- **A healthy node sends nothing.** Not "all checks passed" - nothing. A cron job
  that mails you every five minutes to say it is fine is a cron job you filter.
- **One problem is one notification.** Alerts carry a stable `key`; the same
  problem seen forty times increments a counter, and re-notification backs off
  geometrically (at most 6 notifications in 7 hours).
- **Resolution is announced.** A channel that only ever carries bad news is a
  channel people stop opening. But nothing is "resolved" that was never
  announced - that is noise wearing a helpful hat.
- **Escalation jumps the queue.** A warning that becomes critical must not
  inherit the six-hour silence it earned as a warning.
- **Dedupe state persists.** Cron is a fresh process every run; without
  persistence, "have I already said this?" resets each time, which is the same as
  not deduplicating at all.

Severity comes from `health.py`, unchanged. Promoting a warning to critical
because it *feels* important is how a stream becomes unreadable, and that
judgement was already made once.

### The two ways an alerter lies

**Silently failing to deliver.** A webhook with no URL that returns success is
indistinguishable from a healthy one until the incident, so it reports failure.
A total delivery failure is recorded loudly; one exploding channel does not stop
the others; and an alert nobody accepted is **retried next run** rather than
marked as sent - marking it would lose the one message that mattered.

**Going quiet because it died.** No news reads as good news. `python -m
bingo.node.watch` records a heartbeat into the audit log every run, and
`--check-stale` alerts on a stale one - but **a process cannot page you about
its own absence.** If the watcher is not running, neither is any of its code.
Calling this a deadman's switch would be a lie; it is half of one, and the other
half is a second node, an uptime check, or a poll of `/api/health`. The code says
so and a test asserts that it says so.

Exit codes distinguish the three outcomes, so a scheduler never mistakes a run
that *could not check* for a run that found nothing: `0` quiet, `1` firing, `2`
could not check or could not deliver.

Secrets never reach a channel - webhooks post to third parties with their own
retention, so the audit log's redaction applies here for the same reason.

## Two flaky assertions, fixed rather than loosened

Worth recording because the fix is the same lesson as the storage seam: a test
that *usually* passes is the failure mode, not a nuisance.

**My own concurrency assertions were probabilistic.** "The JSON backend loses a
registration" is true under contention and not *guaranteed* on any single round -
measured 18-30 of 32 - so the assertion failed about one full-suite run in four.
The temptation is to weaken the claim to something always true and vacuous.
Instead the tests observe the real code under real contention with a hard bound
(up to 4 rounds, assert the loss was seen), so a genuine fix - `JsonStore`
growing cross-process locking - turns them red instead of quietly passing. The
SQLite side stays exact and unconditional, because it is deterministic by
construction; that asymmetry *is* the difference between the backends and is left
visible.

**And one that was simply wrong.** A test asserted that two audited HTTP requests
appear in the log in request order. Each request gets its own connection and its
own handler thread, and the audit write happens in that thread, so the order was
never guaranteed. Keyed by method now. Chasing it did surface something worth
keeping: `GuardedServer` now drains in-flight handlers on close explicitly. That
is belt-and-braces - `ThreadingMixIn.server_close` already joins today - but the
join depends on `block_on_close` staying True, and `daemon_threads = True` with
`block_on_close = False` would drop handlers silently, losing exactly the audit
records around a restart. There is now a test for the property rather than trust
in a stdlib default.

## Still open

- **No paging integration beyond a generic webhook.** PagerDuty/Opsgenie
  severity mapping, on-call rotation and acknowledgement are not modelled - an
  alert here is fire-and-forget, and nothing tracks whether a human saw it.
- **Rate-limit state is per-node.** Two nodes with the same problem notify
  twice; there is no cross-node grouping.
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
