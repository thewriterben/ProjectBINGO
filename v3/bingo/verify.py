"""Standalone proof-of-fabrication verifier.

Anyone can run this against an evidence file to confirm a job really happened
— ordered, untampered, and signed by the node that claims it — using only the
public key. No node, no secret, no trust in the operator.

  python -m bingo.verify out/evidence/job-abc123.json
  python -m bingo.verify out/evidence/job-abc123.json --pubkey <hex>
  python -m bingo.verify out/evidence/          # verify every file in a dir
"""

from __future__ import annotations

import argparse
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from . import evidence


def _verify_one(path: str, pubkey: str | None) -> bool:
    try:
        ev = evidence.load(path)
    except Exception as e:
        print(f"✗ {os.path.basename(path)}: cannot read ({e})")
        return False
    ok, notes = evidence.verify(ev, pubkey)
    mark = "✓" if ok else "✗"
    print(f"{mark} {os.path.basename(path)}  [{ev.get('job_id','?')}]")
    for n in notes:
        print(f"    {n}")
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description="BINGO proof-of-fabrication verifier")
    ap.add_argument("path", help="evidence .json file, or a directory of them")
    ap.add_argument("--pubkey", default=None,
                    help="expected node public key (hex); default uses the key "
                         "embedded in the evidence and reports it")
    args = ap.parse_args(argv)

    if os.path.isdir(args.path):
        files = sorted(f for f in os.listdir(args.path) if f.endswith(".json"))
        if not files:
            print("(no .json evidence files in directory)")
            return 1
        results = [_verify_one(os.path.join(args.path, f), args.pubkey) for f in files]
        print(f"\n{sum(results)}/{len(results)} verified")
        return 0 if all(results) else 1

    return 0 if _verify_one(args.path, args.pubkey) else 1


if __name__ == "__main__":
    sys.exit(main())
