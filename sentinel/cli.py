"""Sentinel CLI — add promises, record observations, run a sweep.

  python -m sentinel.cli add --store promises.json \
      --id P-002 --counterparty "FedEx" \
      --description "Filament, 2-day" --deadline 2026-08-06T23:59:00Z \
      --tracking 123456789012

  python -m sentinel.cli observe --store promises.json --id P-002 \
      --ts 2026-08-05T15:00:00Z --state out_for_delivery --note "Boise"

  python -m sentinel.cli sweep --store promises.json --now 2026-08-06T09:00:00Z
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from .models import Promise
from .store import PromiseStore


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sentinel — promise watchdog")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add")
    a.add_argument("--store", required=True)
    a.add_argument("--id", required=True)
    a.add_argument("--counterparty", required=True)
    a.add_argument("--description", required=True)
    a.add_argument("--deadline", required=True, help="RFC3339 UTC")
    a.add_argument("--tracking", default=None)
    a.add_argument("--order-id", default=None)
    a.add_argument("--url", default=None)
    a.add_argument("--instructions", default="")

    o = sub.add_parser("observe")
    o.add_argument("--store", required=True)
    o.add_argument("--id", required=True)
    o.add_argument("--ts", default=None, help="default: now")
    o.add_argument("--state", required=True)
    o.add_argument("--note", default="")
    o.add_argument("--on-track", choices=["true", "false"], default=None)

    s = sub.add_parser("sweep")
    s.add_argument("--store", required=True)
    s.add_argument("--now", default=None)

    args = ap.parse_args(argv)
    store = PromiseStore(args.store).load()

    if args.cmd == "add":
        signals = {}
        if args.tracking:
            signals["tracking"] = args.tracking
        if args.order_id:
            signals["order_id"] = args.order_id
        if args.url:
            signals["url"] = args.url
        store.add(Promise(id=args.id, counterparty=args.counterparty,
                          description=args.description, deadline=args.deadline,
                          signals=signals, standing_instructions=args.instructions))
        store.save()
        print(f"added {args.id} — deadline {args.deadline}")
        return 0

    if args.cmd == "observe":
        p = next((p for p in store.promises if p.id == args.id), None)
        if not p:
            print(f"no promise {args.id}")
            return 1
        ot = None if args.on_track is None else (args.on_track == "true")
        p.observations.append({"ts": args.ts or _now(), "state": args.state,
                               "note": args.note, "on_track": ot})
        store.save()
        print(f"recorded {args.state} on {args.id}")
        return 0

    if args.cmd == "sweep":
        now = args.now or _now()
        alerts = store.sweep(now)
        store.save()
        if not alerts:
            print(f"sweep {now}: all {len(store.open_promises())} open promise(s) on track — quiet.")
            return 0
        print(f"sweep {now}: {len(alerts)} need attention:")
        for a in alerts:
            print(f"  [{a['status']}] {a['id']} ({a['counterparty']}) — {a['reason']}")
            if a["instructions"]:
                print(f"      standing instruction: {a['instructions']}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
