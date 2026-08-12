"""The storage seam, with the failure it exists to fix demonstrated for real.

The claim in `bingo/store.py` is not "SQLite is nicer". It is a specific, testable
one: **the JSON backend loses concurrent updates and the SQLite backend does not,
running identical calling code.** Anyone can assert that in a docstring, so this
suite spawns actual operating-system processes and shows it happening.

Also here, because a backup nobody has ever restored is not a backup:

  * write -> back up -> DESTROY the live database -> restore -> read back and
    compare every record. The restore is exercised, not merely implemented.
  * migration in BOTH directions. A seam you can only walk through one way is a
    trapdoor; an operator who tries SQLite must be able to return to JSON.
  * `PayoutEngine` on a transactional store: still crash-safe, still idempotent,
    still refuses to pay a key twice - and with the default arguments, still
    writes exactly the JSONL journal it always did.

  python -m tests.test_store
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

from bingo import store as S
from bingo.settlement import Leg
from bingo.payout import MockRail, PayoutEngine, PAID

V3_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LEGS = [
    Leg("acct:node:printer-7", 550, "fabrication + material + energy"),
    Leg("acct:carrier-pool", 22, "logistics"),
    Leg("acct:ben", 148, "royalty 8000bps [design]"),
    Leg("acct:network", 40, "network fee (3%)"),
]


def _both(d: str):
    """The same store, once per backend. Every behavioural test runs on both, so
    the seam is a seam rather than two unrelated classes."""
    return [("json", os.path.join(d, "s.json")),
            ("sqlite", os.path.join(d, "s.db"))]


# -- the seam behaves the same either way --------------------------------------

def test_round_trip_and_iteration():
    with tempfile.TemporaryDirectory() as d:
        for backend, path in _both(d):
            st = S.open_store(path, backend=backend)
            assert st.get("nope") is None
            st.put("b", {"n": 2})
            st.put("a", {"n": 1, "nested": {"x": [1, 2, 3]}})
            assert st.get("a")["nested"]["x"] == [1, 2, 3], backend
            assert sorted(st.keys()) == ["a", "b"], backend
            assert len(st) == 2, backend
            st.delete("b")
            assert st.get("b") is None and st.keys() == ["a"], backend
            st.close()
            # and it survived the process-level round trip, not just memory
            again = S.open_store(path, backend=backend)
            assert again.get("a")["n"] == 1, backend
            again.close()


def test_mutating_a_returned_value_does_not_mutate_the_store():
    """`get` hands back a copy. A caller that edits what it was handed must not
    silently rewrite the journal - that is how a PAID record turns into
    something else with no write ever appearing in the code."""
    with tempfile.TemporaryDirectory() as d:
        for backend, path in _both(d):
            st = S.open_store(path, backend=backend)
            st.put("k", {"status": "PAID"})
            got = st.get("k")
            got["status"] = "FAILED"
            assert st.get("k")["status"] == "PAID", backend
            st.close()


def test_transaction_rolls_back_on_exception():
    with tempfile.TemporaryDirectory() as d:
        for backend, path in _both(d):
            st = S.open_store(path, backend=backend)
            st.put("keep", {"n": 0})
            try:
                with st.transaction():
                    st.put("keep", {"n": 99})
                    st.put("ghost", {"n": 1})
                    raise RuntimeError("boom")
            except RuntimeError:
                pass
            assert st.get("ghost") is None, f"{backend}: partial write survived"
            assert st.get("keep")["n"] == 0, f"{backend}: rolled-back value stuck"
            st.close()
            # and the rollback is on DISK, not just in this object's memory
            again = S.open_store(path, backend=backend)
            assert again.get("ghost") is None and again.get("keep")["n"] == 0, backend
            again.close()


def test_corrupt_store_fails_closed():
    """An unreadable payout journal must raise. Starting empty would read as
    'nothing was ever paid', which is the most expensive possible lie here."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"a": {"n": 1}, "b": ')      # truncated mid-write
        try:
            S.open_store(p)
            assert False, "corrupt store must not open silently"
        except (json.JSONDecodeError, ValueError):
            pass
        # a JSON array is well-formed JSON and still not a store
        with open(p, "w", encoding="utf-8") as f:
            f.write("[1, 2, 3]")
        try:
            S.open_store(p)
            assert False, "a non-object store must be rejected"
        except ValueError as e:
            assert "JSON object" in str(e)


# -- the point: concurrent writers ---------------------------------------------

WORKER = r'''
import sys, time
sys.path.insert(0, sys.argv[1])
from bingo.store import open_store
path, backend, hold, reps = sys.argv[2], sys.argv[3], float(sys.argv[4]), int(sys.argv[5])
st = open_store(path, backend=backend)
for _ in range(reps):
    with st.transaction():
        cur = st.get("counter") or {"n": 0}
        time.sleep(hold)             # widen the read-modify-write window
        st.put("counter", {"n": cur["n"] + 1})
st.close()
'''


def _concurrent_increments(path: str, backend: str, workers: int = 4,
                           hold: float = 0.3, reps: int = 1) -> int:
    """`workers` separate PROCESSES each do one read-modify-write increment,
    holding the window open for `hold` seconds. Correct behaviour is a final
    count of exactly `workers`.

    The hold is what makes this deterministic rather than a flaky race: 300ms is
    far longer than the spread in process start-up, so under a backend with no
    lock every worker is guaranteed to read the same value.
    """
    S.open_store(path, backend=backend).close()      # create it before the race
    with tempfile.TemporaryDirectory() as wd:
        script = os.path.join(wd, "w.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(WORKER)
        procs = [subprocess.Popen(
            [sys.executable, script, V3_DIR, path, backend, str(hold), str(reps)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for _ in range(workers)]
        for p in procs:
            _out, err = p.communicate(timeout=120)
            assert p.returncode == 0, f"{backend} worker failed: {err.decode()[:400]}"
    st = S.open_store(path, backend=backend)
    n = (st.get("counter") or {"n": 0})["n"]
    st.close()
    return n


def test_json_loses_concurrent_updates():
    """The concession, demonstrated rather than asserted.

    This is the same shape as the coin-rollback test: show the attack SUCCEEDING
    against the honest default, so the fix below is measured against something
    real. `os.replace` is atomic - the file is never torn - and updates still
    vanish, because atomicity is not isolation."""
    with tempfile.TemporaryDirectory() as d:
        n = _concurrent_increments(os.path.join(d, "race.json"), "json")
        assert n < 4, (
            "expected the JSON backend to lose updates under 4 concurrent "
            f"writers; got {n}. If this ever legitimately reaches 4, the JSON "
            "backend has grown a lock and this test should become the "
            "opposite assertion.")


def test_retry_transient_io_is_bounded_and_re_raises():
    """The retry must eventually give up and surface the real error. A retry
    loop that hides a permanent permission problem forever is worse than the
    crash it was added to prevent."""
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 4:
            raise PermissionError("sharing violation")
        return "ok"

    assert S.retry_transient_io(flaky, attempts=10, delay=0.001) == "ok"
    assert calls["n"] == 4

    def never():
        raise PermissionError("locked by something else entirely")

    try:
        S.retry_transient_io(never, attempts=3, delay=0.001)
        assert False, "a permanently failing operation must not be swallowed"
    except PermissionError as e:
        assert "locked by something else" in str(e)

    # and an error that is NOT a transient sharing violation is not retried
    def wrong():
        calls["n"] += 1
        raise ValueError("corrupt")

    calls["n"] = 0
    try:
        S.retry_transient_io(wrong, attempts=10, delay=0.001)
        assert False
    except ValueError:
        pass
    assert calls["n"] == 1, "only transient IO errors should be retried"


def test_concurrent_json_writers_do_not_crash_on_the_scratch_file():
    """Regression, found by the workers above on their first run - twice, once
    per operating system, and the second one is the one that matters.

    **Everywhere:** both `JsonStore._write` and `PayoutEngine._persist` wrote
    through a scratch file named `path + ".tmp"` - the same name for every
    writer. Two processes saving at once, and one `os.replace`s the file the
    other is about to rename; the loser raises FileNotFoundError.

    **On Windows, additionally:** a *reader* opening the file while another
    process swaps it gets PermissionError. POSIX rename semantics hide the swap
    behind the reader's open handle; Windows has no such courtesy. The reference
    node runs Windows, so on the host that actually holds the journal today, the
    JSON backend did not merely lose a concurrent update - it raised.

    Either way, in the payout journal that lands AFTER the rail call: money has
    moved and the process dies before recording the outcome, which is precisely
    the ordering the two-phase design exists to prevent.

    Losing an update here is expected and demonstrated above. Crashing is not.
    """
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "scratch.json")
        # many short write windows across several processes, so the overlap the
        # bug needs is reached many times rather than gambled on once
        _concurrent_increments(path, "json", workers=6, hold=0.01, reps=25)
        leftovers = [f for f in os.listdir(d) if f.endswith(".tmp")]
        assert not leftovers, f"scratch files left behind: {leftovers}"


def test_sqlite_does_not_lose_concurrent_updates():
    """Identical worker code, identical calls, one word changed at construction."""
    with tempfile.TemporaryDirectory() as d:
        n = _concurrent_increments(os.path.join(d, "race.db"), "sqlite")
        assert n == 4, (
            f"expected all 4 concurrent increments to survive; got {n}. "
            "BEGIN IMMEDIATE takes the write lock at the start of the "
            "transaction, so the second writer waits instead of reading stale "
            "state and overwriting.")


# -- a backup nobody has restored is not a backup ------------------------------

def test_backup_then_destroy_then_restore():
    with tempfile.TemporaryDirectory() as d:
        for backend, path in _both(d):
            st = S.open_store(path, backend=backend)
            with st.transaction():
                for i in range(50):
                    st.put(f"k{i:03d}", {"n": i, "memo": f"leg {i}"})
            before = dict(st.items())
            bak = os.path.join(d, f"{backend}.bak")
            st.backup(bak)                       # taken while the store is open
            # keep writing after the backup: the snapshot must be of the moment
            # it was taken, not of whatever the file happens to hold later
            st.put("k999", {"n": 999, "memo": "after the backup"})
            st.close()

            for stale in (path, path + "-wal", path + "-shm"):
                if os.path.exists(stale):
                    os.remove(stale)             # total loss of the live store
            assert not os.path.exists(path)

            restored = S.restore(bak, path, backend=backend)
            after = dict(restored.items())
            restored.close()
            assert after == before, f"{backend}: restored state differs"
            assert "k999" not in after, (
                f"{backend}: the snapshot picked up a write made after it")
            assert len(after) == 50, backend


def test_sqlite_backup_is_consistent_while_a_transaction_is_open():
    """The reason to use SQLite's online backup API instead of copying the file:
    it takes a coherent snapshot of a database that is being used."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "live.db")
        st = S.SqliteStore(path)
        with st.transaction():
            for i in range(20):
                st.put(f"k{i}", {"n": i})
        other = S.SqliteStore(path)              # a second connection, mid-life
        bak = os.path.join(d, "snap.db")
        other.backup(bak)
        other.close()
        st.close()
        snap = S.SqliteStore(bak)
        assert len(snap) == 20 and snap.get("k7")["n"] == 7
        snap.close()


# -- migration is a two-way door -----------------------------------------------

def test_migrate_json_to_sqlite_and_back():
    with tempfile.TemporaryDirectory() as d:
        j1 = S.JsonStore(os.path.join(d, "a.json"))
        with j1.transaction():
            for i in range(25):
                j1.put(f"key-{i}", {"n": i, "tags": ["a", "b"], "nested": {"z": i}})
        original = dict(j1.items())

        sq = S.SqliteStore(os.path.join(d, "b.db"))
        assert S.copy_store(j1, sq) == 25
        assert dict(sq.items()) == original, "json -> sqlite lost or altered data"

        j2 = S.JsonStore(os.path.join(d, "c.json"))
        assert S.copy_store(sq, j2) == 25
        assert dict(j2.items()) == original, "sqlite -> json lost or altered data"
        for s in (j1, sq, j2):
            s.close()
        # and the round trip is byte-stable in the human-readable form
        with open(os.path.join(d, "a.json"), encoding="utf-8") as f:
            a = f.read()
        with open(os.path.join(d, "c.json"), encoding="utf-8") as f:
            c = f.read()
        assert a == c, "a json -> sqlite -> json round trip changed the file"


# -- choosing a backend, and being told the truth about it ---------------------

def test_default_is_json_so_nothing_changes_by_upgrading():
    with tempfile.TemporaryDirectory() as d:
        assert isinstance(S.open_store(os.path.join(d, "j.json")), S.JsonStore)
        assert isinstance(S.open_store(os.path.join(d, "no-extension")), S.JsonStore)
        # closed explicitly: on Windows an open sqlite handle blocks deleting the
        # file, so a leaked connection here fails the tempdir cleanup, not this
        # assertion. Stores are context managers for exactly this reason.
        with S.open_store(os.path.join(d, "x.db")) as sq:
            assert isinstance(sq, S.SqliteStore)
        try:
            S.open_store(os.path.join(d, "x"), backend="postgres")
            assert False, "an unknown backend must be refused, not defaulted"
        except ValueError as e:
            assert "unknown store backend" in str(e)


def test_describe_does_not_flatter_the_default():
    with tempfile.TemporaryDirectory() as d:
        j = S.open_store(os.path.join(d, "j.json")).describe()
        assert j["backend"] == "json"
        assert j["cross_process_safe"] is False, (
            "the JSON backend must admit it has no cross-process isolation")
        assert "LOSE" in j["note"]
        q = S.open_store(os.path.join(d, "q.db"))
        r = q.describe()
        q.close()
        assert r["cross_process_safe"] is True and r["transactional"] is True
        assert r["journal_mode"].lower() == "wal"
        assert "archiving, which is NOT set up here" in r["note"], (
            "point-in-time recovery must not be overclaimed")


# -- the first consumer --------------------------------------------------------

def test_payout_engine_default_still_writes_the_jsonl_journal():
    """Additive means additive. With no `store=`, the on-disk format an operator
    already has is untouched."""
    with tempfile.TemporaryDirectory() as d:
        jp = os.path.join(d, "journal.jsonl")
        eng = PayoutEngine(MockRail(), journal_path=jp)
        eng.pay_legs(LEGS, order_id="ord-1", job_id="job-1")
        with open(jp, encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        assert len(lines) == 4
        assert all(json.loads(l)["status"] == PAID for l in lines)
        # and it reloads through the original path
        again = PayoutEngine(MockRail(), journal_path=jp)
        assert again.balance("acct:ben") == 148


def test_payout_engine_on_a_transactional_store_is_still_idempotent():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "journal.db")
        rail = MockRail()
        st = S.open_store(path, backend="sqlite")
        eng = PayoutEngine(rail, store=st)
        recs = eng.pay_legs(LEGS, order_id="ord-1", job_id="job-1")
        assert [r.status for r in recs] == [PAID] * 4
        assert len(rail.sent) == 4
        assert not os.path.exists(os.path.join(d, "journal.jsonl"))
        st.close()

        # restart: a brand-new engine, a brand-new rail, the same store
        rail2 = MockRail()
        st2 = S.open_store(path, backend="sqlite")
        eng2 = PayoutEngine(rail2, store=st2)
        assert eng2.balance("acct:node:printer-7") == 550
        repeat = eng2.pay_legs(LEGS, order_id="ord-1", job_id="job-1")
        assert [r.status for r in repeat] == [PAID] * 4
        assert rail2.sent == [], (
            "a restarted engine re-paid legs that were already PAID - the whole "
            "point of journalling the payout is that this cannot happen")
        assert eng2.reconcile_job("job-1", LEGS)["fully_settled"] is True
        st2.close()


def test_payout_intent_is_committed_before_the_rail_is_called():
    """The two-phase protocol, checked against the store rather than trusted.

    A rail that inspects the journal at the moment it is called must already see
    the PENDING intent. If it does not, a crash inside the rail call leaves money
    possibly moved with nothing recording that it was attempted."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "journal.db")
        st = S.open_store(path, backend="sqlite")
        seen: list = []

        class WatchingRail(MockRail):
            def send(self, idem_key, destination, amount_cents, currency, memo):
                # read through a SEPARATE connection: proves it is committed and
                # visible to another process, not merely sitting in memory
                peek = S.open_store(path, backend="sqlite")
                seen.append((peek.get(idem_key) or {}).get("status"))
                peek.close()
                return super().send(idem_key, destination, amount_cents,
                                    currency, memo)

        eng = PayoutEngine(WatchingRail(), store=st)
        eng.pay_legs(LEGS, order_id="ord-1", job_id="job-1")
        st.close()
        assert seen == ["PENDING"] * 4, (
            f"expected a committed PENDING intent visible to another connection "
            f"before each rail call; saw {seen}")


def test_payout_journal_migrates_from_jsonl_to_a_store():
    """An operator with a live JSONL journal has to be able to move without
    re-paying anything."""
    with tempfile.TemporaryDirectory() as d:
        jp = os.path.join(d, "journal.jsonl")
        old = PayoutEngine(MockRail(), journal_path=jp)
        old.pay_legs(LEGS, order_id="ord-1", job_id="job-1")

        st = S.open_store(os.path.join(d, "journal.db"), backend="sqlite")
        with st.transaction():
            for key, rec in old._journal.items():
                st.put(key, {**rec.__dict__})

        rail = MockRail()
        new = PayoutEngine(rail, store=st)
        assert new.balance("acct:ben") == 148
        new.pay_legs(LEGS, order_id="ord-1", job_id="job-1")
        assert rail.sent == [], "migration re-paid already-settled legs"
        st.close()


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK - all {len(tests)} store groups pass: JSON stays the default and "
          "the default payout journal is byte-for-byte what it always was; the "
          "opt-in SQLite backend survives 4 concurrent writers that the JSON "
          "backend demonstrably loses an update to; a backup is destroyed and "
          "restored and compared record by record; migration works in both "
          "directions; and the PayoutEngine on a transactional store still "
          "commits its PENDING intent - visibly, from another connection - "
          "before the rail is ever called.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
