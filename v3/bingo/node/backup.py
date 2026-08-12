"""Back up a node - and, more importantly, restore one and check it worked.

The production-gap memo asks for "backups, point-in-time recovery, and a tested
restore." The last three words are the whole item. Every system that has ever
lost data had backups; what it did not have was a restore anyone had performed.

So this tool has two verbs and the second one is the point:

    python -m bingo.node.backup out --to backups/2026-08-12
    python -m bingo.node.backup --drill out

`--drill` takes a backup, restores it into a scratch directory, opens every
collection, and compares them record by record against the live node. It does
not touch the live node. It is meant to be run on a schedule, and to fail loudly
the first time a backup stops being restorable - which is the day you want to
find out, rather than the day you need it.

What it copies, and what it deliberately does not:

  * **collections** (registry manifests, reputation book, payout journal, audit
    log) - through `Store.backup()`, so a SQLite backend gets a consistent
    snapshot of a live database rather than a `cp` that can catch a half-applied
    WAL
  * **content blobs and evidence files** - copied byte for byte; they are
    content-addressed or write-once, so there is nothing to be consistent about
  * **NOT the keystore.** Encrypted key material is deliberately excluded. A
    backup is a file that gets copied to laptops, object stores and USB sticks,
    and the passphrase that protects those seeds is one guess away from being
    the only thing between a stolen backup and a stolen identity. Key custody
    has its own story in `specs/KEY-CUSTODY.md`, with its own threat model. A
    tool that quietly swept keys into a nightly tarball would undo it.

The honest limit: this is snapshot recovery, not point-in-time recovery. You get
back what the node looked like when the backup ran, plus whatever the payout
journal and audit chain let you replay. Recovering to an arbitrary instant needs
WAL archiving, which is not set up - see `specs/STORAGE.md`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile

from bingo import store as S

#: Collections a node keeps, by base name (no extension - the extension follows
#: the backend). Kept in one place so a new collection is added once and both
#: the backup and the drill pick it up.
COLLECTIONS = ("manifests", "reputation", "journal", "audit")

#: Directories copied verbatim. Content-addressed or write-once, so there is no
#: consistency question - only presence.
TREES = ("blobs", "evidence")

#: Never backed up. See the module docstring; this is a security decision, not
#: an oversight, and it is a tuple so the reason has somewhere to live.
EXCLUDED = ("keys",)


def _bases(node_dir: str) -> list[str]:
    """Which collections actually exist here, under either backend."""
    found = []
    for name in COLLECTIONS:
        base = os.path.join(node_dir, name)
        if os.path.exists(base + ".json") or os.path.exists(base + ".db"):
            found.append(name)
    return found


def backup(node_dir: str, dest: str, *, quiet: bool = False) -> dict:
    if not os.path.isdir(node_dir):
        raise FileNotFoundError(f"no such node directory: {node_dir}")
    os.makedirs(dest, exist_ok=True)
    done: dict[str, int] = {}

    for name in _bases(node_dir):
        src = S.node_store(os.path.join(node_dir, name))
        try:
            ext = ".db" if isinstance(src, S.SqliteStore) else ".json"
            src.backup(os.path.join(dest, name + ext))
            done[name] = len(src)
        finally:
            src.close()

    trees = []
    for t in TREES:
        s_dir = os.path.join(node_dir, t)
        if os.path.isdir(s_dir):
            shutil.copytree(s_dir, os.path.join(dest, t), dirs_exist_ok=True)
            trees.append(t)

    skipped = [x for x in EXCLUDED if os.path.exists(os.path.join(node_dir, x))]
    if not quiet:
        for k, n in done.items():
            print(f"  {k}: {n} records")
        for t in trees:
            print(f"  {t}/: copied")
        for x in skipped:
            print(f"  {x}/: SKIPPED ON PURPOSE - key material is never backed "
                  f"up here (see the module docstring)")
        print(f"backed up {node_dir} -> {dest}")
        print("this is a backup, not a tested restore. Run --drill.")
    return {"collections": done, "trees": trees, "skipped": skipped,
            "dest": dest}


def drill(node_dir: str, *, quiet: bool = False) -> dict:
    """Back up, restore into scratch, and compare against the live node.

    Read-only with respect to `node_dir`. The comparison is record by record
    rather than file-size or checksum, because a restore that produces a
    same-sized file with different contents is exactly the failure a checksum
    of the backup would not catch."""
    results: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as tmp:
        b_dir = os.path.join(tmp, "backup")
        r_dir = os.path.join(tmp, "restored")
        backup(node_dir, b_dir, quiet=True)
        os.makedirs(r_dir, exist_ok=True)

        for name in _bases(node_dir):
            live = S.node_store(os.path.join(node_dir, name))
            try:
                ext = ".db" if isinstance(live, S.SqliteStore) else ".json"
                expected = dict(live.items())
            finally:
                live.close()

            restored = S.restore(os.path.join(b_dir, name + ext),
                                 os.path.join(r_dir, name + ext))
            try:
                got = dict(restored.items())
            finally:
                restored.close()

            missing = sorted(set(expected) - set(got))
            changed = sorted(k for k in set(expected) & set(got)
                             if expected[k] != got[k])
            extra = sorted(set(got) - set(expected))
            results[name] = {"records": len(expected), "missing": missing[:5],
                             "changed": changed[:5], "extra": extra[:5],
                             "ok": not (missing or changed or extra)}

        # the audit chain has to still VERIFY after a restore, not merely have
        # the same number of rows - a restore that scrambled order would pass a
        # count check and fail this one
        if "audit" in results:
            from bingo.audit import AuditLog
            ext = ".db" if os.path.exists(os.path.join(r_dir, "audit.db")) \
                else ".json"
            st = S.open_store(os.path.join(r_dir, "audit" + ext))
            try:
                ok, notes = AuditLog(store=st).verify()
            finally:
                st.close()
            results["audit"]["chain_verifies"] = ok
            results["audit"]["chain_note"] = notes[-1] if notes else ""
            results["audit"]["ok"] = results["audit"]["ok"] and ok

    ok = all(r["ok"] for r in results.values()) if results else False
    if not quiet:
        if not results:
            print(f"x nothing to restore in {node_dir} - is that the right "
                  f"directory?")
        for name, r in sorted(results.items()):
            mark = "ok  " if r["ok"] else "FAIL"
            print(f"  {mark} {name}: {r['records']} records"
                  + (f", missing={r['missing']}" if r["missing"] else "")
                  + (f", changed={r['changed']}" if r["changed"] else "")
                  + (f", chain={'verifies' if r.get('chain_verifies') else 'BROKEN'}"
                     if "chain_verifies" in r else ""))
        print("RESTORE DRILL PASSED - every record came back identical."
              if ok else
              "RESTORE DRILL FAILED - do not rely on these backups.")
    return {"ok": ok, "collections": results}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m bingo.node.backup",
        description="Back up a node, and prove the backup restores.")
    ap.add_argument("node_dir", help="the node's output directory, e.g. out")
    ap.add_argument("--to", help="destination directory for the backup")
    ap.add_argument("--drill", action="store_true",
                    help="back up, restore to scratch, and compare record by "
                         "record. Does not modify the node.")
    a = ap.parse_args(argv)
    try:
        if a.drill:
            return 0 if drill(a.node_dir)["ok"] else 1
        if not a.to:
            ap.error("--to is required unless --drill is given")
        backup(a.node_dir, a.to)
        return 0
    except (FileNotFoundError, RuntimeError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
