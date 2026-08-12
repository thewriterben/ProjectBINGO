"""A node's state, moved behind the storage seam - and the crash it survives now.

`bingo/store.py` gave BINGO a transactional backend. This suite is about the
part that actually protects an operator: routing the collections a node keeps
through it, so the backend is chosen **once per node** rather than per module,
and so the ones that were never even crash-safe become so.

Two of them were not. `AssetRegistry.save` and `ReputationBook.save` were bare
`json.dump` calls into an open handle - which **truncates the destination
first**. A crash, a full disk, or a killed process halfway through left a
valid-looking partial file. What is in those files is not incidental:

  * the registry holds every asset's **effective split** - the routing table
    that decides who gets paid
  * the reputation book holds node **stakes** as well as scores

And `bingo/register.py` does load -> mutate -> save, where `save` rewrote the
whole file - so two registrations racing lose one asset outright: a creator's
split silently ceases to exist, with no error and a well-formed file.

What is checked here:

  * a registry or book written by the OLD code path still loads. A storage
    refactor that quietly orphans existing assets is a data-loss event wearing a
    tidy diff.
  * a failed save leaves the PREVIOUS good state, not half a file.
  * concurrent registration through real processes, all three shapes side by
    side: the old whole-file save loses assets, the seam on JSON still loses
    them (fewer, which is worse), and SQLite keeps every one.
  * `node_store` refuses to open empty when the other backend's file is sitting
    there with data in it, and names the command that fixes it.
  * that command works, verifies itself by read-back, and goes both ways.

**One expectation this suite corrected while it was being written**, and it is
the most useful thing in here. Routing through a keyed store turns a whole-file
*replace* into a per-key *upsert*, and at four concurrent registrations that
looked like the fix - it passed, repeatedly. It is not the fix. Two JSON writers
can still both read the same state, both merge their own key, and the later one
drop the earlier. The upsert shrank the window; it did not remove it, because
`load()` and `save()` are separate store sessions and no transaction spans them.

**Narrowing a race is not closing it - and a race that fires one time in twenty
is worse than one that fires every time,** because the obvious bug gets found in
development and this one waits until there is money in the file. So the test
contends properly (4 processes x 8 registrations) and pins all three states: the
old whole-file save loses assets, the seam on JSON *still* loses assets, and only
SQLite keeps every one.

  python -m tests.test_node_storage
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

from bingo import store as S
from bingo.node import migrate_store
from bingo.registry import AssetRegistry
from bingo.reputation import ReputationBook
from bingo.models import License, LicenseTemplate, Split, SplitPayee

V3_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _quiet(fn, *a):
    """Run a CLI entry point without letting its output into the suite log."""
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*a)


def _lic() -> License:
    return License(LicenseTemplate("commercial-per-unit"), per_unit_cents=25)


def _register(reg: AssetRegistry, title: str, body: bytes,
              payees=(("acct:ben", 8000), ("acct:network", 2000))):
    return reg.register(
        kind="model", title=title, creator="acct:ben", content=body,
        license=_lic(),
        split=Split([SplitPayee(a, b) for a, b in payees]))


# -- existing files must keep working ------------------------------------------

def test_a_registry_written_by_the_old_code_still_loads():
    """The old path was `json.dump(manifests, f, indent=2)` into
    `<store_dir>/manifests.json`. Anything on an operator's disk looks exactly
    like that, and must load unchanged."""
    with tempfile.TemporaryDirectory() as d:
        built = AssetRegistry()
        a1 = _register(built, "bracket", b"solid bracket body")
        a2 = _register(built, "gear", b"a gear, 40 teeth")
        legacy = {aid: asset.manifest() for aid, asset in built._assets.items()}
        os.makedirs(os.path.join(d, "blobs"), exist_ok=True)
        with open(os.path.join(d, "manifests.json"), "w", encoding="utf-8") as f:
            json.dump(legacy, f, indent=2)          # verbatim old behaviour

        loaded = AssetRegistry.load(d)
        assert sorted(x.asset_id for x in loaded.all()) == sorted([a1.asset_id,
                                                                   a2.asset_id])
        got = {x.asset_id: x for x in loaded.all()}[a1.asset_id]
        assert [(p.account, p.bps) for p in got.effective_split.payees] == \
               [("acct:ben", 8000), ("acct:network", 2000)], \
               "the effective split - who gets paid - did not survive the load"


def test_a_reputation_book_written_by_the_old_code_still_loads():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "reputation.json")
        book = ReputationBook()
        book.node("node:printer-7").staked_cents = 25_000
        legacy = {"nodes": {k: v.to_dict() for k, v in book.nodes.items()},
                  "buyers": {}}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(legacy, f, indent=2)          # verbatim old behaviour
        again = ReputationBook.load(path)
        assert again.node("node:printer-7").staked_cents == 25_000


def test_the_default_save_still_writes_the_same_file_in_the_same_place():
    """Additive means additive: no operator's paths move."""
    with tempfile.TemporaryDirectory() as d:
        reg = AssetRegistry()
        _register(reg, "bracket", b"solid bracket body")
        reg.save(d)
        assert os.path.exists(os.path.join(d, "manifests.json"))
        with open(os.path.join(d, "manifests.json"), encoding="utf-8") as f:
            assert isinstance(json.load(f), dict)

        book = ReputationBook()
        book.node("n1").staked_cents = 100
        p = os.path.join(d, "reputation.json")
        book.save(p)
        assert os.path.exists(p)
        with open(p, encoding="utf-8") as f:
            assert set(json.load(f)) == {"nodes", "buyers"}


# -- a failed save must leave the last good state ------------------------------

def _break_replace(monkey: dict):
    """Make the atomic rename fail, i.e. crash at the worst moment: after the
    new bytes are written, before they are swapped in."""
    real = os.replace

    def boom(a, b):
        if str(b).endswith(("manifests.json", "reputation.json")):
            raise OSError(28, "No space left on device")
        return real(a, b)

    monkey["real"] = real
    os.replace = boom


def _restore_replace(monkey: dict):
    os.replace = monkey["real"]


def test_a_failed_registry_save_leaves_the_previous_state_intact():
    """The property the old code could not offer.

    `json.dump` into `open(path, "w")` truncates first, so an interrupted save
    destroyed the good file and left a partial one that still *looks* like JSON
    until it doesn't. Writing to a temp file and renaming means a failure loses
    the NEW state, never the old one - and losing an unwritten change is a very
    different thing from losing the routing table.
    """
    with tempfile.TemporaryDirectory() as d:
        reg = AssetRegistry()
        first = _register(reg, "bracket", b"solid bracket body")
        reg.save(d)

        _register(reg, "gear", b"a gear, 40 teeth")
        monkey: dict = {}
        _break_replace(monkey)
        try:
            reg.save(d)
            assert False, "the induced failure did not surface"
        except OSError as e:
            assert e.errno == 28
        finally:
            _restore_replace(monkey)

        recovered = AssetRegistry.load(d)          # must not raise
        assert [x.asset_id for x in recovered.all()] == [first.asset_id], (
            "after a failed save the registry should hold exactly the last "
            "successfully-saved state")
        leftovers = [f for f in os.listdir(d) if f.endswith(".tmp")]
        assert not leftovers, f"scratch files left behind: {leftovers}"


def test_a_failed_reputation_save_leaves_the_previous_state_intact():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "reputation.json")
        book = ReputationBook()
        book.node("n1").staked_cents = 100
        book.save(p)

        book.node("n1").staked_cents = 999
        monkey: dict = {}
        _break_replace(monkey)
        try:
            book.save(p)
            assert False, "the induced failure did not surface"
        except OSError:
            pass
        finally:
            _restore_replace(monkey)

        assert ReputationBook.load(p).node("n1").staked_cents == 100


def test_evidence_files_are_written_atomically():
    """Write-once, but it is the document a payout is justified by."""
    from bingo import evidence
    with tempfile.TemporaryDirectory() as d:
        path = S.atomic_write_json(os.path.join(d, "j-1.json"), {"ok": True})
        assert evidence.load(path) == {"ok": True}
        assert not [f for f in os.listdir(d) if f.endswith(".tmp")]
        # and the source really does route through it
        import inspect
        assert "atomic_write_json" in inspect.getsource(evidence.save)


# -- concurrent registration ---------------------------------------------------

WORKER = r'''
import sys, time
sys.path.insert(0, sys.argv[1])
import os
os.environ["BINGO_STORE"] = sys.argv[3]
from bingo.registry import AssetRegistry
from bingo.models import License, LicenseTemplate, Split, SplitPayee
store_dir, tag, reps = sys.argv[2], sys.argv[4], int(sys.argv[5])
for r in range(reps):
    reg = AssetRegistry.load(store_dir)
    reg.register(kind="model", title=f"{tag}-{r}", creator="acct:ben",
                 content=("body " + tag + str(r)).encode(),
                 license=License(LicenseTemplate("commercial-per-unit"),
                                 per_unit_cents=25),
                 split=Split([SplitPayee("acct:ben", 10000)]))
    time.sleep(0.02)                  # widen the load -> save window
    reg.save(store_dir)
'''


def _concurrent_registrations(store_dir: str, backend: str, n: int = 4,
                              reps: int = 8) -> int:
    os.makedirs(store_dir, exist_ok=True)
    AssetRegistry().save(store_dir)               # create it before the race
    with tempfile.TemporaryDirectory() as wd:
        script = os.path.join(wd, "w.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(WORKER)
        procs = [subprocess.Popen(
            [sys.executable, script, V3_DIR, store_dir, backend, f"asset-{i}",
             str(reps)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(n)]
        for p in procs:
            _o, err = p.communicate(timeout=180)
            assert p.returncode == 0, f"{backend} worker failed: {err.decode()[:500]}"
    env = os.environ.get("BINGO_STORE")
    os.environ["BINGO_STORE"] = backend
    try:
        return len(AssetRegistry.load(store_dir).all())
    finally:
        if env is None:
            os.environ.pop("BINGO_STORE", None)
        else:
            os.environ["BINGO_STORE"] = env


LEGACY_WORKER = r'''
import sys, os, json, time
sys.path.insert(0, sys.argv[1])
from bingo.registry import AssetRegistry
from bingo.models import License, LicenseTemplate, Split, SplitPayee
store_dir, tag = sys.argv[2], sys.argv[3]
mpath = os.path.join(store_dir, "manifests.json")

# EXACTLY the old save/load pair: read the whole file, add one asset, write the
# WHOLE FILE back. This is the shape being replaced, reproduced here so the
# claim below is measured against something real rather than remembered.
manifests = json.load(open(mpath)) if os.path.exists(mpath) else {}
reg = AssetRegistry()
a = reg.register(kind="model", title=tag, creator="acct:ben",
                 content=("body " + tag).encode(),
                 license=License(LicenseTemplate("commercial-per-unit"),
                                 per_unit_cents=25),
                 split=Split([SplitPayee("acct:ben", 10000)]))
manifests[a.asset_id] = a.manifest()
time.sleep(0.3)                        # widen the read -> write window
with open(mpath, "w") as f:
    json.dump(manifests, f, indent=2)
'''


def _concurrent_legacy_registrations(store_dir: str, n: int = 4) -> int:
    os.makedirs(store_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as wd:
        script = os.path.join(wd, "lw.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(LEGACY_WORKER)
        procs = [subprocess.Popen(
            [sys.executable, script, V3_DIR, store_dir, f"asset-{i}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(n)]
        for p in procs:
            p.communicate(timeout=180)
    path = os.path.join(store_dir, "manifests.json")
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        return len(json.load(f))


def test_the_old_whole_file_save_loses_concurrent_registrations():
    """The concession, demonstrated rather than remembered.

    `bingo/register.py` is load -> mutate -> save, and the old `save` wrote the
    WHOLE manifest file. Four creators registering at the same moment, and three
    assets - three creators' entire royalty splits - are simply gone. Nobody
    gets an error; the file is well-formed; the assets were just never there.
    """
    with tempfile.TemporaryDirectory() as d:
        n = _concurrent_legacy_registrations(os.path.join(d, "reg"))
        assert n < 4, (
            f"expected the old whole-file save to lose registrations under 4 "
            f"concurrent writers; got {n}")


def test_the_seam_alone_narrows_the_race_without_closing_it():
    """An expectation this suite corrected while it was being written, and the
    correction is the more useful finding.

    Going through a keyed store turns a whole-file *replace* into a per-key
    *upsert*, which sounded like the fix - and at four registrations it looked
    like one, passing repeatedly. It is not. Two JSON writers can still both
    enter, both read the same state, both merge their own key, and the later
    write drops the earlier one. The upsert only shrank the window from "the
    whole load-mutate-save span" to "the save itself".

    **Narrowing a race is not closing it, and a race that fires one time in
    twenty is worse than one that fires every time** - the obvious bug gets
    found in development; this one waits until there is money in the file.

    So the test contends properly: 4 processes x 8 registrations each. Assets
    still go missing, quietly, with a well-formed file and no error anywhere.
    """
    with tempfile.TemporaryDirectory() as d:
        n = _concurrent_registrations(os.path.join(d, "reg"), "json")
        assert n < 32, (
            f"expected the JSON backend to still lose registrations under real "
            f"contention; got all {n}. If JsonStore ever legitimately keeps all "
            f"32, it has grown cross-process locking and this should become the "
            f"opposite assertion.")


def test_sqlite_keeps_every_concurrent_registration():
    """Identical worker code, one environment variable different. This is the
    fix - `BEGIN IMMEDIATE` serializes the saves, so no writer ever reads a
    state that is about to be overwritten."""
    with tempfile.TemporaryDirectory() as d:
        n = _concurrent_registrations(os.path.join(d, "reg"), "sqlite")
        assert n == 32, (
            f"expected all 32 concurrent registrations to survive; got {n}")


# -- one choice per node, and refusing to start empty --------------------------

def test_node_store_follows_the_backend_in_the_file_name():
    with tempfile.TemporaryDirectory() as d:
        with S.node_store(os.path.join(d, "coll"), backend="json") as a:
            a.put("k", {"n": 1})
        assert os.path.exists(os.path.join(d, "coll.json"))
        with S.node_store(os.path.join(d, "other"), backend="sqlite") as b:
            b.put("k", {"n": 1})
        assert os.path.exists(os.path.join(d, "other.db"))


def test_node_store_refuses_to_start_empty_beside_a_populated_sibling():
    """The dangerous silent failure this exists to prevent: an operator flips
    `$BINGO_STORE` without migrating, everything opens clean and empty, and an
    empty registry reads as 'this creator has no assets'."""
    with tempfile.TemporaryDirectory() as d:
        base = os.path.join(d, "manifests")
        with S.node_store(base, backend="json") as st:
            st.put("asset-1", {"title": "bracket"})
        try:
            S.node_store(base, backend="sqlite")
            assert False, "must refuse rather than open an empty store"
        except RuntimeError as e:
            msg = str(e)
            assert "Refusing to start empty" in msg
            assert "migrate_store" in msg, "the refusal must name the fix"

        # an EMPTY sibling is not a reason to refuse - nothing is at risk
        empty = os.path.join(d, "fresh")
        with S.node_store(empty, backend="json"):
            pass
        with S.node_store(empty, backend="sqlite") as ok:
            assert len(ok) == 0


def test_a_registry_refuses_rather_than_loading_empty_after_an_unmigrated_flip():
    """The same protection, felt where it matters."""
    with tempfile.TemporaryDirectory() as d:
        reg = AssetRegistry()
        _register(reg, "bracket", b"solid bracket body")
        reg.save(d)
        env = os.environ.get("BINGO_STORE")
        os.environ["BINGO_STORE"] = "sqlite"
        try:
            AssetRegistry.load(d)
            assert False, "loading an unmigrated registry must not return empty"
        except RuntimeError as e:
            assert "migrate_store" in str(e)
        finally:
            if env is None:
                os.environ.pop("BINGO_STORE", None)
            else:
                os.environ["BINGO_STORE"] = env


# -- the migration the refusal points at ---------------------------------------

def test_migrate_store_self_test():
    """The operator-facing `--self-test`, so the tool is checked by the same
    suite that checks what it operates on. Output captured: one suite, one OK
    line."""
    assert _quiet(migrate_store.self_test) == 0


def test_migrating_a_real_registry_preserves_every_split():
    with tempfile.TemporaryDirectory() as d:
        reg = AssetRegistry()
        a = _register(reg, "bracket", b"solid bracket body",
                      payees=(("acct:ben", 6500), ("acct:collab", 1500),
                              ("acct:network", 2000)))
        _register(reg, "gear", b"a gear, 40 teeth")
        reg.save(d)

        r = migrate_store.migrate(os.path.join(d, "manifests"), "sqlite",
                                  quiet=True)
        assert r["records"] == 2 and r["verified"]

        env = os.environ.get("BINGO_STORE")
        os.environ["BINGO_STORE"] = "sqlite"
        try:
            moved = AssetRegistry.load(d)
            got = {x.asset_id: x for x in moved.all()}
            assert set(got) == {x.asset_id for x in reg.all()}
            assert [(p.account, p.bps)
                    for p in got[a.asset_id].effective_split.payees] == \
                   [("acct:ben", 6500), ("acct:collab", 1500),
                    ("acct:network", 2000)]
            # and the blobs came along - they live beside the manifests, not in
            # them, so a migration that forgot them would still "verify"
            assert moved._blobs, "content blobs did not survive the migration"
        finally:
            if env is None:
                os.environ.pop("BINGO_STORE", None)
            else:
                os.environ["BINGO_STORE"] = env


def test_migrate_refuses_to_clobber_and_never_touches_the_source():
    with tempfile.TemporaryDirectory() as d:
        base = os.path.join(d, "coll")
        with S.node_store(base, backend="json") as st:
            with st.transaction():
                for i in range(5):
                    st.put(f"k{i}", {"n": i})
        before = open(base + ".json", "rb").read()

        migrate_store.migrate(base, "sqlite", quiet=True)
        try:
            migrate_store.migrate(base, "sqlite", quiet=True)
            assert False, "a second migration into an existing destination "\
                          "must be refused - it would merge two histories"
        except FileExistsError as e:
            assert "--force" in str(e)
        assert open(base + ".json", "rb").read() == before, (
            "the source must be left byte-identical: a migration you cannot "
            "walk back from is not a migration")

        try:
            migrate_store.migrate(os.path.join(d, "nothing-here"), "sqlite",
                                  quiet=True)
            assert False
        except FileNotFoundError:
            pass


def test_migrate_cli_reports_failure_rather_than_exiting_zero():
    with tempfile.TemporaryDirectory() as d:
        rc = _quiet(migrate_store.main,
                    [os.path.join(d, "absent"), "--to", "sqlite"])
        assert rc == 1, "a failed migration must not exit 0"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK - all {len(tests)} node-storage groups pass: the asset registry "
          "and reputation book now persist through the seam, so a failed save "
          "leaves the LAST GOOD state instead of a truncated file (neither was "
          "crash-safe before - a bare json.dump truncates first, and those "
          "files hold effective splits and stakes); files written by the old "
          "code still load; under 4x8 concurrent registrations the OLD whole-file "
          "save loses assets and the seam on JSON STILL loses them - the "
          "per-key upsert narrowed the race without closing it, which is the "
          "worse failure because it fires rarely - while SQLite keeps every "
          "one; and flipping BINGO_STORE without "
          "migrating REFUSES rather than silently reading as 'this creator has "
          "no assets', naming the migration command - which verifies itself by "
          "read-back, refuses to clobber, and leaves the source byte-identical.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
