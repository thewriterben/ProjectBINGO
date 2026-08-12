"""Move one of a node's collections between storage backends.

`bingo/store.py` makes the backend a node-level choice, and `node_store()`
refuses to open an empty store when the other backend's file is sitting right
there with data in it - because an empty asset registry reads as "this creator
has no assets" and an empty payout journal reads as "nothing was ever paid".
That refusal names this command. This is the command.

    python -m bingo.node.migrate_store out/registry/manifests --to sqlite
    python -m bingo.node.migrate_store out/reputation --to json

Take the BASE path, without an extension - the extension follows the backend,
which is the whole point of `node_store`. The source is left in place: a
migration that deletes the thing it was copying has no way back if it was wrong,
and this tool verifies rather than trusts.

What it guarantees:

  * every record is compared **after** the write, read back through a fresh
    connection - not "the copy loop didn't raise"
  * the destination must not already exist unless `--force` says so, so a second
    run cannot silently merge two histories into one
  * the source is never modified, so `--to json` back out is always available

  python -m bingo.node.migrate_store --self-test
"""

from __future__ import annotations

import argparse
import os
import sys

from bingo import store as S

BACKENDS = {"json": ".json", "sqlite": ".db"}


def migrate(base: str, to: str, *, force: bool = False,
            quiet: bool = False) -> dict:
    if to not in BACKENDS:
        raise ValueError(f"unknown backend {to!r} (expected json or sqlite)")
    src_backend = "json" if to == "sqlite" else "sqlite"
    src_path = base + BACKENDS[src_backend]
    dst_path = base + BACKENDS[to]

    if not os.path.exists(src_path):
        raise FileNotFoundError(
            f"nothing to migrate: {src_path} does not exist")
    if os.path.exists(dst_path) and not force:
        raise FileExistsError(
            f"{dst_path} already exists. Refusing to write into it - a second "
            f"run would merge two histories into one and neither would be "
            f"recoverable. Move it aside, or pass --force if you are certain.")

    src = S.open_store(src_path, backend=src_backend)
    try:
        original = dict(src.items())
    finally:
        src.close()

    if os.path.exists(dst_path) and force:
        for stale in (dst_path, dst_path + "-wal", dst_path + "-shm"):
            if os.path.exists(stale):
                os.remove(stale)

    dst = S.open_store(dst_path, backend=to)
    try:
        with dst.transaction():
            for k, v in original.items():
                dst.put(k, v)
    finally:
        dst.close()

    # verify by reading back through a FRESH connection. "the loop didn't raise"
    # is not a check; this is.
    check = S.open_store(dst_path, backend=to)
    try:
        written = dict(check.items())
    finally:
        check.close()
    if written != original:
        missing = sorted(set(original) - set(written))
        changed = sorted(k for k in set(original) & set(written)
                         if original[k] != written[k])
        raise RuntimeError(
            f"migration verification FAILED - {dst_path} does not match "
            f"{src_path}. missing={missing[:5]} changed={changed[:5]}. "
            f"The source is untouched; do not delete it.")

    result = {"from": src_path, "to": dst_path, "records": len(original),
              "verified": True}
    if not quiet:
        print(f"migrated {len(original)} records: {src_path} -> {dst_path}")
        print(f"verified by read-back through a fresh connection.")
        print(f"the source is UNTOUCHED at {src_path} - delete it yourself once "
              f"you are satisfied.")
        print(f"now run this node with BINGO_STORE={to}")
    return result


def self_test() -> int:
    """Exercised by tests/test_store.py too; here so an operator can check the
    tool on their own machine before pointing it at real data."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        base = os.path.join(d, "coll")
        src = S.open_store(base + ".json", backend="json")
        with src.transaction():
            for i in range(30):
                src.put(f"k{i}", {"n": i, "deep": {"list": [i, i + 1]}})
        src.close()

        r = migrate(base, "sqlite", quiet=True)
        assert r["records"] == 30 and r["verified"]

        # refuses to clobber
        try:
            migrate(base, "sqlite", quiet=True)
            raise AssertionError("a second run must refuse")
        except FileExistsError:
            pass

        # and back out again, which is the property that makes this a two-way door
        os.remove(base + ".json")
        r2 = migrate(base, "json", quiet=True)
        assert r2["records"] == 30
        back = S.open_store(base + ".json", backend="json")
        try:
            assert len(back) == 30 and back.get("k7")["deep"]["list"] == [7, 8]
        finally:
            back.close()
    print("OK - migrate_store self-test passes: 30 records json -> sqlite -> "
          "json, verified by read-back each way, and a second run into an "
          "existing destination is refused.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m bingo.node.migrate_store",
        description="Move a node collection between storage backends.")
    p.add_argument("base", nargs="?",
                   help="base path WITHOUT extension, e.g. out/registry/manifests")
    p.add_argument("--to", choices=sorted(BACKENDS), help="destination backend")
    p.add_argument("--force", action="store_true",
                   help="overwrite an existing destination (dangerous)")
    p.add_argument("--self-test", action="store_true",
                   help="check the tool itself and exit")
    a = p.parse_args(argv)
    if a.self_test:
        return self_test()
    if not a.base or not a.to:
        p.error("base and --to are required (or use --self-test)")
    try:
        migrate(a.base, a.to, force=a.force)
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
