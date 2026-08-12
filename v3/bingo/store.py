"""The storage seam: JSON by default, SQLite when you need real transactions.

BINGO's persistence has been single-file JSON since the first commit. That is a
genuinely good default for this project - a JSON file is inspectable, diffable,
copyable, and needs nothing installed, which is the same property that makes the
documents themselves verifiable by a stranger. It should stay the default.

But it has one failure mode that matters once real money is in the journal:

    process A reads {n: 0}          process B reads {n: 0}
    process A writes {n: 1}         process B writes {n: 1}

Both writes are atomic (`os.replace`), so the file is never torn - and one of the
two updates is silently gone anyway. Atomicity is not isolation. For a payout
journal, "silently gone" means an intent that was recorded and then wasn't, which
is exactly the record the crash-safety design depends on.

The fix is not to make JSON cleverer. It is to make the storage layer a seam, so
an operator who is moving real value can put a real transactional engine behind
it without any calling code changing:

    Store          - get/put/delete/items, plus transaction(), backup(), describe()
    JsonStore      - today's behaviour, unchanged, still the default
    SqliteStore    - stdlib sqlite3, WAL, BEGIN IMMEDIATE, online backup API

`SqliteStore` uses only the standard library, so the "no dependencies" promise in
CONTRIBUTING.md survives intact. Nothing on disk changes unless the operator
chooses it: `open_store()` returns a `JsonStore` unless asked otherwise.

What each backend actually gives you is not a matter of opinion - ask it:

    >>> open_store("out/journal.json").describe()["cross_process_safe"]
    False
    >>> open_store("out/journal.db").describe()["cross_process_safe"]
    True

`tests/test_store.py` demonstrates the lost update above with real concurrent
processes: the JSON backend loses it, the SQLite backend does not, running the
identical calling code.

  python -m tests.test_store
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Iterator

__all__ = ["Store", "JsonStore", "SqliteStore", "open_store", "copy_store",
           "restore", "is_sqlite_path", "retry_transient_io"]

SQLITE_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".sqlite-store")


def is_sqlite_path(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SQLITE_SUFFIXES


# -- the Windows tax on "atomic file swap" -------------------------------------

def retry_transient_io(fn, *, attempts: int = 60, delay: float = 0.01):
    """Retry a file operation through a transient sharing violation.

    POSIX rename semantics let a reader hold an open file through a replace: the
    old inode survives until the reader closes it, so `os.replace` is invisible.
    **Windows does not work that way.** While one process is swapping the file,
    another process opening it gets `PermissionError` (ERROR_ACCESS_DENIED) or
    briefly finds it missing.

    That matters here specifically because the reference node runs Windows. On
    that host the JSON journal does not merely lose a concurrent update - it
    raises. In `PayoutEngine._persist` the raise lands AFTER the rail call, so
    money has moved and the process dies before recording the outcome: exactly
    the ordering the two-phase design exists to prevent.

    A bounded retry removes the spurious hard failure. It does NOT provide
    isolation - nothing at this layer can - so a concurrent update is still lost,
    just quietly rather than explosively. The actual fix is `SqliteStore`.
    """
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except (PermissionError, FileNotFoundError) as e:
            last = e
            time.sleep(delay * (1 + (i % 5)))
    raise last                                   # type: ignore[misc]


# -- the seam ------------------------------------------------------------------

class Store(ABC):
    """A durable map of string key -> JSON-serializable dict.

    Deliberately small. Everything BINGO persists (payout journals, registries,
    ledgers, key directories) is a keyed collection of signed documents, and a
    narrow interface is what lets a backend be swapped without auditing callers.

    The contract every backend must honour:

      * `put` is durable when it returns (or when the enclosing transaction
        commits) - not "probably flushed soon"
      * `transaction()` is the read-modify-write unit; reads inside it see a
        consistent snapshot and writes land together or not at all
      * a backend that CANNOT provide isolation must say so in `describe()`
        rather than quietly pretending - a silent lie here is worse than JSON
    """

    @abstractmethod
    def get(self, key: str) -> dict | None: ...

    @abstractmethod
    def put(self, key: str, value: dict) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def items(self) -> Iterator[tuple[str, dict]]: ...

    @abstractmethod
    def transaction(self): ...

    @abstractmethod
    def backup(self, path: str) -> None: ...

    @abstractmethod
    def describe(self) -> dict: ...

    def keys(self) -> list[str]:
        return [k for k, _ in self.items()]

    def __len__(self) -> int:
        return len(self.keys())

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# -- the default: JSON, exactly as it has always been --------------------------

class JsonStore(Store):
    """One JSON object per file, rewritten atomically. Today's behaviour.

    Honest about what it is: atomic, durable, human-readable, and NOT isolated
    across processes. There is no lock, so two writers race and one loses. That
    is fine for a single-process node and for every demo in this repo; it is not
    fine for a host that is settling real money from more than one process.
    """

    def __init__(self, path: str):
        self.path = path
        self._data: dict[str, dict] = {}
        self._lock = threading.RLock()       # in-process only, and it says so
        self._depth = 0
        if os.path.exists(path):
            self._read()

    # -- disk --
    def _slurp(self) -> str:
        with open(self.path, "r", encoding="utf-8") as f:
            return f.read()

    def _read(self) -> None:
        # retried: on Windows another process mid-swap makes this raise
        raw = retry_transient_io(self._slurp)
        if not raw.strip():
            self._data = {}
            return
        # a corrupt store raises rather than silently starting empty: an empty
        # payout journal reads as "nothing was ever paid", which is the single
        # most dangerous lie this file could tell
        d = json.loads(raw)
        if not isinstance(d, dict):
            raise ValueError(f"{self.path}: store must be a JSON object")
        self._data = d

    def _write(self) -> None:
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        # the scratch name must be unique per writer. A shared `path + ".tmp"`
        # looks harmless and is not: two processes writing at once have one of
        # them `os.replace` the file the other is still about to rename, and the
        # loser dies with FileNotFoundError. Found by test_store's concurrency
        # workers, which is exactly what they are for.
        tmp = f"{self.path}.{os.getpid()}.{threading.get_ident()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())             # durable before the swap, not after
        try:
            retry_transient_io(lambda: os.replace(tmp, self.path))   # atomic
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    # -- Store --
    def get(self, key: str) -> dict | None:
        with self._lock:
            v = self._data.get(key)
            return json.loads(json.dumps(v)) if v is not None else None

    def put(self, key: str, value: dict) -> None:
        with self._lock:
            self._data[key] = value
            if self._depth == 0:
                self._write()                # write-through outside a transaction

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)
            if self._depth == 0:
                self._write()

    def items(self) -> Iterator[tuple[str, dict]]:
        with self._lock:
            return iter(list(self._data.items()))

    @contextmanager
    def transaction(self):
        """Re-reads from disk on entry and writes once on exit.

        Re-reading is what makes this a fair comparison rather than a rigged one:
        the JSON backend does see other processes' committed writes. It still
        loses updates, because seeing them is not the same as excluding them.
        """
        with self._lock:
            outer = self._depth == 0
            if outer and os.path.exists(self.path):
                self._read()
            self._depth += 1
            try:
                yield self
            except BaseException:
                self._depth -= 1
                if self._depth == 0:
                    self._data = {}
                    if os.path.exists(self.path):
                        self._read()         # roll back to what is on disk
                raise
            self._depth -= 1
            if self._depth == 0:
                self._write()

    def backup(self, path: str) -> None:
        with self._lock:
            if self._depth:
                raise RuntimeError("cannot back up from inside a transaction")
            self._write()
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            shutil.copyfile(self.path, path)

    def describe(self) -> dict:
        return {
            "backend": "json",
            "path": self.path,
            "atomic_writes": True,
            "durable": True,
            "transactional": "within one process only",
            "cross_process_safe": False,
            "online_backup": True,
            "note": ("atomic whole-file rewrite. Two processes doing "
                     "read-modify-write will LOSE one of the updates - there is "
                     "no lock. On Windows a concurrent reader additionally hits "
                     "transient sharing violations, which are retried here but "
                     "not eliminated. Human-readable and dependency-free, which "
                     "is why it stays the default; use the sqlite backend on any "
                     "host where more than one process writes real value."),
        }


# -- the opt-in: SQLite, for when it has to actually hold ----------------------

class SqliteStore(Store):
    """stdlib `sqlite3` in WAL mode. Real transactions, real cross-process locks.

    Three settings do the work:

      * `journal_mode=WAL`  - readers do not block the writer, and a crash
        mid-write rolls back rather than truncating
      * `synchronous=FULL`  - a committed payout intent has actually reached the
        disk. This is slower than NORMAL and that is the correct trade for money
      * `BEGIN IMMEDIATE`   - takes the write lock at the START of the
        transaction, not at first write. This is the line that turns a lost
        update into a wait: the second process blocks (up to `timeout`) instead
        of reading stale state and overwriting

    Nothing here is beyond the standard library, so BINGO still installs with
    nothing.
    """

    def __init__(self, path: str, timeout: float = 30.0):
        self.path = path
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        # isolation_level=None: no implicit BEGINs from the driver. We say when a
        # transaction starts, because we need IMMEDIATE and it does not offer it.
        self._conn = sqlite3.connect(path, timeout=timeout, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS kv ("
            "  key   TEXT PRIMARY KEY,"
            "  value TEXT NOT NULL"
            ")")
        self._lock = threading.RLock()
        self._depth = 0

    # -- Store --
    def get(self, key: str) -> dict | None:
        row = self._conn.execute(
            "SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, value: dict) -> None:
        with self._lock:
            if self._depth:
                self._conn.execute(
                    "INSERT INTO kv(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(value, sort_keys=True)))
            else:
                with self.transaction():     # single-op transaction, still locked
                    self.put(key, value)

    def delete(self, key: str) -> None:
        with self._lock:
            if self._depth:
                self._conn.execute("DELETE FROM kv WHERE key = ?", (key,))
            else:
                with self.transaction():
                    self.delete(key)

    def items(self) -> Iterator[tuple[str, dict]]:
        rows = self._conn.execute("SELECT key, value FROM kv ORDER BY key").fetchall()
        return iter([(k, json.loads(v)) for k, v in rows])

    @contextmanager
    def transaction(self):
        with self._lock:
            if self._depth:                  # reentrant: the outermost one commits
                self._depth += 1
                try:
                    yield self
                finally:
                    self._depth -= 1
                return
            self._conn.execute("BEGIN IMMEDIATE")   # take the write lock NOW
            self._depth = 1
            try:
                yield self
            except BaseException:
                self._depth = 0
                self._conn.execute("ROLLBACK")
                raise
            self._depth = 0
            self._conn.execute("COMMIT")

    def backup(self, path: str) -> None:
        """SQLite's online backup API: a consistent snapshot taken WHILE the
        database is in use. Copying the file with `cp` does not give you this -
        it can catch a half-applied WAL."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        dst = sqlite3.connect(path)
        try:
            with dst:
                self._conn.backup(dst)
        finally:
            dst.close()

    def describe(self) -> dict:
        mode = self._conn.execute("PRAGMA journal_mode").fetchone()[0]
        sync = self._conn.execute("PRAGMA synchronous").fetchone()[0]
        return {
            "backend": "sqlite",
            "path": self.path,
            "atomic_writes": True,
            "durable": True,
            "transactional": True,
            "cross_process_safe": True,
            "online_backup": True,
            "journal_mode": mode,
            "synchronous": sync,
            "note": ("WAL + synchronous=FULL + BEGIN IMMEDIATE. Concurrent "
                     "writers serialize instead of clobbering each other; "
                     "backup() is a consistent snapshot of a live database. "
                     "Point-in-time recovery to an arbitrary instant needs WAL "
                     "archiving, which is NOT set up here - what you get is "
                     "recovery to the last backup, plus whatever the journal "
                     "itself lets you replay."),
        }

    def close(self) -> None:
        self._conn.close()


# -- the primitive, for artifacts that are not keyed collections ---------------

def atomic_write_json(path: str, obj, *, indent: int = 2,
                      sort_keys: bool = False) -> str:
    """Write a JSON file crash-safely: temp file, fsync, atomic rename.

    Not everything BINGO persists is a keyed collection. A per-job evidence file
    is a write-once artifact - a `Store` would be the wrong shape for it. But
    "write-once" is not the same as "safe to write carelessly": a bare
    `json.dump` into an open handle truncates the destination first, so a crash
    or a full disk halfway through leaves a **valid-looking, truncated file**,
    and the evidence for a completed job is the thing a payout is justified by.

    This is the floor. Anything that holds state gets at least this.
    """
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=indent, sort_keys=sort_keys)
        f.flush()
        os.fsync(f.fileno())
    try:
        retry_transient_io(lambda: os.replace(tmp, path))
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return path


# -- choosing, moving, restoring -----------------------------------------------

def node_store(base: str, *, backend: str | None = None, **kw) -> Store:
    """Open one of a node's collections, letting the FILE NAME follow the
    backend: `node_store("out/registry/manifests")` opens `manifests.json` by
    default and `manifests.db` under `$BINGO_STORE=sqlite`.

    This is what makes the backend a **node-level** decision instead of a
    per-module one. Every collection a node keeps - the asset registry, the
    reputation book, the payout journal - goes through here, so one environment
    variable moves all of them together and there is no way to end up with half
    a node transactional.

    It also refuses a specific silent failure. If the selected backend's file is
    missing but the *other* backend's file is there with data in it, that is
    almost certainly an operator who flipped `$BINGO_STORE` without migrating.
    Opening empty would be catastrophic and quiet: an empty asset registry reads
    as "this creator has no assets and no splits", and an empty payout journal
    reads as "nothing was ever paid". So it raises, and names the command that
    fixes it.
    """
    choice = (backend or os.environ.get("BINGO_STORE") or "json").strip().lower()
    if choice in ("sqlite", "sqlite3", "db"):
        chosen, sibling, other = base + ".db", base + ".json", "json"
    elif choice in ("json", "file"):
        chosen, sibling, other = base + ".json", base + ".db", "sqlite"
    else:
        raise ValueError(f"unknown store backend {choice!r} "
                         "(expected 'json' or 'sqlite')")
    if not os.path.exists(chosen) and os.path.exists(sibling) \
            and os.path.getsize(sibling) > 2:
        raise RuntimeError(
            f"{chosen} does not exist, but {sibling} does and has data in it.\n"
            f"Refusing to start empty - an empty store reads as 'nothing was "
            f"ever registered/paid', which is a dangerous lie.\n"
            f"Migrate it first:\n"
            f"    python -m bingo.node.migrate_store {base} --to {choice}\n"
            f"or set BINGO_STORE={other} to keep using the existing one.")
    return open_store(chosen, backend=choice, **kw)


def open_store(path: str, *, backend: str | None = None, **kw) -> Store:
    """Pick a backend. JSON unless told otherwise, so no existing deployment
    changes behaviour by upgrading.

    Order: explicit `backend=` > `$BINGO_STORE` > file extension > JSON.
    """
    choice = (backend or os.environ.get("BINGO_STORE") or "").strip().lower()
    if choice in ("sqlite", "sqlite3", "db"):
        return SqliteStore(path, **kw)
    if choice in ("json", "file"):
        return JsonStore(path)
    if choice:
        raise ValueError(f"unknown store backend {choice!r} "
                         "(expected 'json' or 'sqlite')")
    return SqliteStore(path, **kw) if is_sqlite_path(path) else JsonStore(path)


def copy_store(src: Store, dst: Store) -> int:
    """Move every record from one backend to another, in one transaction on the
    destination. Used for migration in BOTH directions - a one-way door is not a
    seam, and an operator who tries SQLite must be able to walk back to JSON."""
    n = 0
    with dst.transaction():
        for key, value in src.items():
            dst.put(key, value)
            n += 1
    return n


def restore(backup_path: str, live_path: str, *, backend: str | None = None) -> Store:
    """Restore a backup over a live path and hand back the opened store.

    Deliberately returns the store rather than just succeeding: a restore that
    was never read back is not a tested restore, and this is the call site where
    that check is cheapest to make.
    """
    if not os.path.exists(backup_path):
        raise FileNotFoundError(backup_path)
    choice = (backend or os.environ.get("BINGO_STORE") or "").strip().lower()
    sqlite_target = (choice in ("sqlite", "sqlite3", "db")
                     or (not choice and is_sqlite_path(live_path)))
    parent = os.path.dirname(os.path.abspath(live_path))
    os.makedirs(parent, exist_ok=True)
    if sqlite_target:
        # go through the backup API rather than copying bytes, so a WAL left
        # beside the old live file cannot be replayed over the restored one
        for stale in (live_path, live_path + "-wal", live_path + "-shm"):
            if os.path.exists(stale):
                os.remove(stale)
        src = sqlite3.connect(backup_path)
        dst = sqlite3.connect(live_path)
        try:
            with dst:
                src.backup(dst)
        finally:
            src.close()
            dst.close()
    else:
        shutil.copyfile(backup_path, live_path)
    return open_store(live_path, backend=backend)
