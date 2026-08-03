"""Register a real asset into a persistent local registry store.

Examples (from v3/):

  # the coin design
  python -m bingo.register --store out/registry ^
      --file "C:\\path\\to\\dgd_token.stl" --kind design ^
      --title "DGD promotional token" --creator acct:ben ^
      --per-unit 40 --split acct:ben=6000,acct:john=4000

  # Ben's validated process package (the knowledge asset)
  python -m bingo.register --store out/registry ^
      --file "C:\\path\\to\\halot_blu_v2_package.zip" --kind profile ^
      --title "Halot Mage Pro / Siraya Blu V2 process package" ^
      --creator acct:ben --per-unit 10 --split acct:ben=10000

  # list what's registered
  python -m bingo.register --store out/registry --list
"""

from __future__ import annotations

import argparse
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from .models import Derivation, License, LicenseTemplate, Split, SplitPayee
from .registry import AssetRegistry


def parse_split(s: str) -> Split:
    payees = []
    for part in s.split(","):
        account, bps = part.split("=")
        payees.append(SplitPayee(account.strip(), int(bps)))
    return Split(payees)


def main(argv=None):
    ap = argparse.ArgumentParser(description="BINGO asset registration")
    ap.add_argument("--store", required=True, help="registry store directory")
    ap.add_argument("--list", action="store_true", help="list registered assets and exit")
    ap.add_argument("--file", help="content file to register")
    ap.add_argument("--kind", default="design",
                    choices=["design", "profile", "software", "qc-procedure",
                             "training-material", "design-gcode"])
    ap.add_argument("--title")
    ap.add_argument("--creator", default="acct:ben")
    ap.add_argument("--license", default="commercial-per-unit",
                    choices=[t.value for t in LicenseTemplate])
    ap.add_argument("--per-unit", type=int, default=0, help="royalty cents/unit")
    ap.add_argument("--split", default=None, help="acct:a=6000,acct:b=4000 (bps, sums to 10000)")
    ap.add_argument("--derives", default=None,
                    help="parent derivations: <asset_id>=<parent_share_bps>[,...]")
    args = ap.parse_args(argv)

    reg = AssetRegistry.load(args.store)

    if args.list:
        assets = reg.all()
        if not assets:
            print("(registry empty)")
        for a in assets:
            split = " · ".join(f"{p.account}={p.bps}" for p in a.effective_split.payees)
            print(f"{a.asset_id[:16]}…  [{a.kind}]  '{a.title}'  "
                  f"{a.license.per_unit_cents}¢/unit  split: {split}")
        return 0

    if not (args.file and args.title):
        print("✗ --file and --title required to register (or use --list)")
        return 1

    content = open(args.file, "rb").read()
    split = parse_split(args.split) if args.split else Split([SplitPayee(args.creator, 10_000)])
    derives = []
    if args.derives:
        for part in args.derives.split(","):
            aid, bps = part.split("=")
            derives.append(Derivation(aid.strip(), int(bps)))

    asset = reg.register(
        kind=args.kind, title=args.title, creator=args.creator, content=content,
        license=License(LicenseTemplate(args.license), per_unit_cents=args.per_unit),
        split=split, derives_from=derives)
    reg.save(args.store)

    eff = " · ".join(f"{p.account}={p.bps}bps" for p in asset.effective_split.payees)
    print(f"✓ registered [{asset.kind}] '{asset.title}'")
    print(f"  asset_id: {asset.asset_id}")
    print(f"  content:  sha256 {asset.content_sha256[:16]}… ({asset.content_bytes:,} bytes)")
    print(f"  license:  {asset.license.template.value}, {asset.license.per_unit_cents}¢/unit")
    print(f"  effective split: {eff}")
    print(f"  store: {args.store}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
