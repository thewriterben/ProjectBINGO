"""Mint a batch of DGD coins and export the variable-data file a label printer
needs — one row per coin, each with its own QR and its own scratch-off code.

    python -m provenance.coin_batch --count 100 --out out/coin/batch.csv

The CSV has: serial, qr_url (the PUBLIC QR to print in gold+black), scratch_code
(the SECRET to print under the tamper-evident panel — handle securely), and
secret_hash / passport_head for your records. Feed qr_url + scratch_code to the
printer as variable data; keep the credentials JSON to load into the redemption
server.

In production, mint with DGD's real issuer key (not the demo key here) so the
QR credentials verify against the key baked into digitalgold.co.
"""

from __future__ import annotations

import argparse
import csv
import json
import os

from .passport import Actor, CutPassport
from .coin import mint_coin, new_secret, qr_url, qr_payload

CREDIT = 2500


def _passport_head(serial: str, issuer: Actor) -> str:
    p = CutPassport(subject={"product": "DGD promo coin", "serial": serial})
    p.attest(issuer, "FINISH", {"serial": serial, "credit_cents": CREDIT},
             ts="2026-08-04T00:00:00Z")
    return p.to_dict()["chain_head"]


def mint_batch(issuer: Actor, count: int, *, start: int = 1, year: int = 2026,
               base: str = "https://digitalgold.co", credit_cents: int = CREDIT,
               short: bool = True):
    """short=True → the QR is a tiny URL (base/r/<serial>) the server resolves to
    the credential; sparse and reliably scannable at 30mm. short=False embeds the
    full signed credential in the QR (verifies offline, but a dense QR that needs
    a larger/flatter print). For a coin, short is the right call."""
    rows, creds = [], []
    for i in range(start, start + count):
        serial = f"DGD-{year}-{i:04d}"
        code = new_secret()
        cred = mint_coin(issuer, serial=serial, passport_head=_passport_head(serial, issuer),
                         credit_cents=credit_cents, secret=code)
        url = f"{base.rstrip('/')}/r/{serial}" if short else qr_url(cred, base)
        rows.append({"serial": serial, "qr_url": url,
                     "scratch_code": code, "secret_hash": cred["secret_hash"],
                     "passport_head": cred["passport_head"]})
        creds.append(cred)
    return rows, creds


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mint a DGD coin batch → variable-data CSV")
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--base", default="https://digitalgold.co")
    ap.add_argument("--full-qr", action="store_true",
                    help="embed the full credential in the QR (offline-verifiable "
                         "but dense); default is a short URL that scans at 30mm")
    ap.add_argument("--out", default="out/coin/batch.csv")
    args = ap.parse_args(argv)

    # DEMO issuer key — replace with DGD's production key for real coins.
    issuer = Actor.create("dgd", "Digital Gold Foundation", "issuer", "acct:dgd:foundation")
    rows, creds = mint_batch(issuer, args.count, start=args.start, base=args.base,
                             short=not args.full_qr)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["serial", "qr_url", "scratch_code",
                                          "secret_hash", "passport_head"])
        w.writeheader()
        w.writerows(rows)
    with open(args.out.rsplit(".", 1)[0] + "_credentials.json", "w") as f:
        json.dump(creds, f, indent=2)

    print(f"minted {len(rows)} coins with issuer {issuer.pubkey_hex[:16]}…")
    print(f"  variable-data for the printer → {args.out}")
    print(f"    columns: serial, qr_url (public, gold+black), scratch_code (SECRET, under panel)")
    print(f"  credentials for the redemption server → "
          f"{args.out.rsplit('.',1)[0]}_credentials.json")
    print(f"  sample row: {rows[0]['serial']} · code {rows[0]['scratch_code']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
