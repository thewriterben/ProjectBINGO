# The storage seam

_Status: implemented (`bingo/store.py`), wired into node state, 40/40 suites. Written 2026-08-12._

## The problem

BINGO has persisted everything to single-file JSON since the first commit. That
is a good default and it should stay the default. A JSON file is inspectable,
diffable, greppable, copyable, and needs nothing installed - the same property
that makes the signed documents themselves verifiable by a stranger with a
stock Python.

It has exactly one failure mode that matters once real money is in the file:

```
process A reads  {n: 0}          process B reads  {n: 0}
process A writes {n: 1}          process B writes {n: 1}
```

Both writes are atomic - `os.replace` means the file is never torn - and one of
the two updates is silently gone anyway.

**Atomicity is not isolation.** Atomicity says a reader never sees half a write.
Isolation says two writers can't interleave a read-modify-write. The payout
journal needs the second one: `PayoutEngine` commits a PENDING intent to disk
*before* calling the rail, and that ordering is the whole crash-safety argument.
An intent that was written and then silently overwritten by a concurrent process
is worse than one that was never written, because the code believes it is there.

Nothing in this repo triggered that bug, because every node process today is a
single process. That is a deployment accident, not a property.

## The shape of the fix

Not "make JSON cleverer". Make storage a seam, the same way the payout rail and
the signer are seams, so an operator moving real value can put a real engine
behind it without any calling code changing:

| | `JsonStore` (default) | `SqliteStore` (opt-in) |
|---|---|---|
| atomic writes | yes | yes |
| durable (fsync) | yes | yes (`synchronous=FULL`) |
| transactional | within one process | yes |
| **cross-process safe** | **no** | **yes** (`BEGIN IMMEDIATE`) |
| online backup | file copy | SQLite backup API |
| dependencies | none | none (stdlib `sqlite3`) |

`SqliteStore` is standard library only, so the no-dependencies promise in
CONTRIBUTING.md survives intact. `cryptography` remains the only optional
dependency in the project, and it is still optional.

### Three settings do the work

- `journal_mode=WAL` - readers don't block the writer; a crash mid-write rolls
  back rather than truncating.
- `synchronous=FULL` - a committed payout intent has actually reached the disk.
  Slower than `NORMAL`, and that is the correct trade for money.
- `BEGIN IMMEDIATE` - takes the write lock at the **start** of the transaction
  rather than at first write. This is the single line that converts a lost update
  into a wait. With SQLite's default `BEGIN DEFERRED` the second writer reads
  first, then tries to upgrade, and either clobbers or deadlocks - the test suite
  demonstrates that too.

## Not overclaiming: what "recovery" means here

`backup()` gives a **consistent snapshot of a live database**, which a `cp` of a
WAL-mode SQLite file does not. `restore()` puts one back and hands you the opened
store, because a restore that was never read back is not a tested restore.

Point-in-time recovery to an *arbitrary instant* requires WAL archiving, which is
**not** set up here. What an operator actually gets is: recovery to the last
backup, plus whatever the journal itself permits replaying. `describe()` says so
in as many words, and a test asserts that it keeps saying so.

## Ask, don't infer

Every backend reports its own properties, in the same spirit as
`keys.signing_path_report()`:

```python
>>> open_store("out/journal.json").describe()["cross_process_safe"]
False
>>> open_store("out/journal.db").describe()["cross_process_safe"]
True
```

A backend that cannot provide isolation must say so rather than quietly
pretending. A silent lie in `describe()` would be worse than JSON.

## Additive, and a two-way door

- `open_store()` returns a `JsonStore` unless asked otherwise. Extension `.db` /
  `.sqlite` / `.sqlite3`, `backend="sqlite"`, or `$BINGO_STORE=sqlite` opt in.
- `PayoutEngine(rail, journal_path=...)` is untouched: the same JSONL journal,
  byte for byte, tested explicitly. The store is a new `store=` keyword.
- `copy_store(src, dst)` migrates in **both** directions, and the JSON ->
  SQLite -> JSON round trip is asserted byte-identical. A seam you can only walk
  through one way is a trapdoor.

## What the tests actually prove

`tests/test_store.py` does not assert the claim, it demonstrates it - four real
operating-system processes, identical worker code, one word changed at
construction:

- JSON backend: loses updates. Asserted, not hoped for.
- SQLite backend: all four survive.
- Write -> back up -> **destroy the live database** -> restore -> compare every
  record, and confirm the snapshot did not pick up a write made after it.
- `PayoutEngine` on a store: the PENDING intent is visible **from a separate
  connection** at the moment the rail is called. The two-phase ordering is
  checked against the disk rather than trusted.

## Two bugs this found

The concurrency workers broke on their first run, and then broke again for a
different reason on the other operating system.

**Everywhere - the shared scratch file.** Both `JsonStore._write` and the
pre-existing `PayoutEngine._persist` wrote through a scratch file named
`path + ".tmp"` - the same name for every writer. Two processes saving at once,
and one `os.replace`s the file the other is about to rename; the loser raises
`FileNotFoundError`. Fixed in both: the scratch name now carries pid and thread
id, and is cleaned up if the rename fails.

**On Windows - `os.replace` is not invisible to readers.** POSIX rename semantics
let a reader hold an open file straight through a replace; the old inode survives
until it closes. Windows has no such courtesy: a process opening the file while
another swaps it gets `PermissionError` (ERROR_ACCESS_DENIED), or briefly finds it
missing. The suite passed in Linux CI and failed on the device.

That second one matters more than it looks, because **the reference node runs
Windows**. On the host that actually holds the payout journal today, the JSON
backend was not merely losing a concurrent update - it was raising. And in
`PayoutEngine._persist` the raise lands *after* the rail call: money has moved,
and the process dies before recording the outcome. That is exactly the ordering
the two-phase design exists to prevent, reintroduced by a filesystem detail.

Fixed with a bounded retry (`store.retry_transient_io`) on both the read and the
swap, in the store and in the payout journal. Honest about what that buys: it
removes the spurious hard failure, and it does **not** provide isolation. A
concurrent update is still lost, just quietly rather than explosively. The actual
fix is `SqliteStore`.

Both are pinned by deterministic regressions - 6 processes x 25 write cycles,
which catches the old code 6 times out of 6 - plus a unit test that the retry is
bounded, re-raises the real error, and does not retry non-transient failures.

## Wiring it in: one choice per node

A seam only one module uses is a seam in name. `node_store(base)` opens a
collection with the **file name following the backend** - `manifests.json` by
default, `manifests.db` under `$BINGO_STORE=sqlite` - so one environment
variable moves a node's whole state together and there is no way to end up with
half a node transactional. Now behind it:

- `AssetRegistry` (asset manifests, i.e. every **effective split**)
- `ReputationBook` (scores and node **stakes**)
- `PayoutEngine` (the journal, opt-in via `store=`)
- `evidence.save` uses `atomic_write_json` rather than a Store - a per-job
  evidence file is a write-once artifact, so a keyed collection is the wrong
  shape, but "written once" is not "safe to write carelessly"

### Two of these were never crash-safe

`AssetRegistry.save` and `ReputationBook.save` were bare `json.dump` calls into
an open handle, and `open(path, "w")` **truncates the destination first**. A
crash, a full disk, or a killed process halfway through left a valid-looking
partial file where the routing table used to be. Now a failed save loses the
*new* state and never the old one, which is a completely different event.

### Refusing to start empty

If the selected backend's file is missing but the other backend's file is there
with data in it, `node_store` **raises** and names the migration command. This is
the same fail-closed reasoning as the corrupt-journal check: an empty asset
registry reads as *"this creator has no assets and no splits"*, and starting
clean would be both catastrophic and silent.

`python -m bingo.node.migrate_store <base> --to sqlite|json` is that command. It
verifies by reading every record back through a fresh connection rather than
trusting that the copy loop didn't raise, refuses a destination that already
exists (a second run would merge two histories irreversibly), and leaves the
source byte-identical so `--to json` back out is always available.

## Narrowing a race is not closing it

The most useful thing this work produced is a correction to its own first
conclusion, so it is recorded rather than quietly fixed.

Routing the registry through a keyed store turns a whole-file **replace** into a
per-key **upsert**. At four concurrent registrations that looked like the fix -
the test passed, repeatedly. It is not the fix. `bingo/register.py` is
load -> mutate -> save across two separate store sessions, and no transaction
spans them; two JSON writers can still both read the same state, both merge
their own key, and the later drop the earlier. The upsert shrank the window from
the whole load-mutate-save span to the save itself.

**A race that fires one time in twenty is worse than one that fires every time.**
The obvious bug gets found in development; the rare one waits until there is
money in the file. So the suite contends properly - 4 processes x 8
registrations - and pins all three states: the old whole-file save loses assets,
the seam on JSON *still* loses them, and only SQLite keeps every one.

## Still open

- Nothing in the repo *defaults* to the transactional backend. That is
  deliberate for now, but the day a node settles real money from more than one
  process, `JsonStore` is the wrong choice and only the operator can make that
  call - and as the race above shows, the JSON default is genuinely lossy under
  concurrency, not merely theoretically so.
- `provenance/coin.py`'s redemption ledger and anchor sidecar still write JSON
  directly. They are already atomic, so this is tidiness rather than a hole, but
  it means the coin vertical does not follow `$BINGO_STORE` with the rest of the
  node yet.
- No WAL archiving, so no true point-in-time recovery. See above.
