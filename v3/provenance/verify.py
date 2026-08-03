"""Standalone provenance & ownership verifier — the skeptic's tool.

Point it at a passport or a token file and it tells you, from nothing but the
document, whether the thing is real: every link signed by whoever made it, the
chain unbroken, the money conserved, the ownership never double-spent, and (for
a token) its claim pinned to a passport that itself verifies. No server, no
database, no trust in whoever handed you the file.

  python -m provenance.verify out/passport/<lot>.json
  python -m provenance.verify out/token/<id>.json --passport out/passport/<lot>.json
  python -m provenance.verify out/token/            # every file in a directory

Exit code 0 iff everything checked verifies — so it drops straight into CI or a
buyer's own script.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from .passport import verify_passport
from .token import verify_token
from .transport import verify_transport, escrow_decision


def _load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _label(doc: dict) -> str:
    schema = doc.get("schema", "")
    if "passport" in schema:
        s = doc.get("subject", {})
        return f'passport · {s.get("product", "?")} · lot {s.get("lot", "?")}'
    if "token" in schema:
        return f'token · {doc.get("unit", "?")} · {doc.get("token_id", "")[:12]}…'
    if "transport" in schema:
        s = doc.get("subject", {})
        return f'transport · {s.get("vehicle", "?")} · VIN {s.get("vin", "?")}'
    return "unknown document"


def verify_doc(doc: dict, backing: dict | None = None) -> tuple[bool, list[str]]:
    """Dispatch on the document's schema. A token gets its backing passport if
    one was supplied (so the provenance pin is actually checked)."""
    schema = doc.get("schema", "")
    if "passport" in schema:
        return verify_passport(doc)
    if "token" in schema:
        return verify_token(doc, backing_passport=backing)
    if "transport" in schema:
        ok, notes = verify_transport(doc)
        if ok:
            dec = escrow_decision(doc)
            notes = notes + [f"escrow {dec['status']}"
                             + (f" → ${dec['amount_cents']/100:,.2f} to the bound carrier"
                                if dec.get("release") else "")]
        return ok, notes
    return False, [f"unrecognized schema: {schema or '(none)'}"]


def _verify_one(path: str, backing: dict | None) -> bool:
    try:
        doc = _load(path)
    except Exception as e:
        print(f"✗ {os.path.basename(path)}: cannot read ({e})")
        return False
    ok, notes = verify_doc(doc, backing)
    mark = "✓" if ok else "✗"
    print(f"{mark} {os.path.basename(path)}  [{_label(doc)}]")
    for n in notes:
        print(f"    {n}")
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description="BINGO provenance & token verifier")
    ap.add_argument("path", help="a passport/token .json file, or a directory of them")
    ap.add_argument("--passport", default=None,
                    help="backing passport file for a token, so its provenance "
                         "pin and physical redemptions are checked too")
    args = ap.parse_args(argv)

    backing = None
    if args.passport:
        try:
            backing = _load(args.passport)
        except Exception as e:
            print(f"✗ cannot read backing passport: {e}")
            return 1

    if os.path.isdir(args.path):
        files = sorted(f for f in os.listdir(args.path) if f.endswith(".json"))
        if not files:
            print("(no .json documents in directory)")
            return 1
        results = [_verify_one(os.path.join(args.path, f), backing) for f in files]
        print(f"\n{sum(results)}/{len(results)} verified")
        return 0 if all(results) else 1

    return 0 if _verify_one(args.path, backing) else 1


if __name__ == "__main__":
    sys.exit(main())
