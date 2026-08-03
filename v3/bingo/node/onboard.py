"""Node onboarding — turn a stranger into a verified BINGO node.

Run this once to join. It (1) creates your node's cryptographic identity,
(2) proves your install works end-to-end with a self-test (no hardware, no
money), and (3) prints the one block of text you send the pilot coordinator
to get certified for a job class.

  python -m bingo.node.onboard --name "Dana's X1C" --operator acct:dana \
      --process fdm --materials PLA,PETG --tier 0

Everything is local. Your private seed never leaves this machine.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from .. import crypto
from ..dfm import DfmReport
from ..ledger import Ledger
from ..models import Job, License, LicenseTemplate, Machine, NodeInfo, Split, SplitPayee
from ..node.agent import NodeAgent
from ..orchestrator import Orchestrator
from ..registry import AssetRegistry
from ..demo.make_design import bracket_stl

IDENTITY_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "out", "node_identity.json")


def load_or_create_identity(node_id: str) -> tuple[bytes, str]:
    os.makedirs(os.path.dirname(IDENTITY_PATH), exist_ok=True)
    if os.path.exists(IDENTITY_PATH):
        with open(IDENTITY_PATH) as f:
            data = json.load(f)
        seed = bytes.fromhex(data["seed_hex"])
        return seed, crypto.publickey(seed).hex()
    seed, pk = crypto.keypair()
    with open(IDENTITY_PATH, "w") as f:
        json.dump({"node_id": node_id, "seed_hex": seed.hex(),
                   "public_key_hex": pk.hex(),
                   "WARNING": "seed_hex is your PRIVATE key — never share it"}, f, indent=2)
    return seed, pk.hex()


def self_test(node: NodeInfo, seed: bytes) -> bool:
    """Run one full job through YOUR node against a throwaway network and
    verify: PoF chain signs+verifies under your key, settlement is exact."""
    reg, ledger = AssetRegistry(), Ledger()
    design = reg.register(kind="design", title="onboarding self-test part",
                          creator="acct:coordinator", content=bracket_stl(),
                          license=License(LicenseTemplate.COMMERCIAL_PER_UNIT, per_unit_cents=25),
                          split=Split([SplitPayee("acct:coordinator", 10000)]))
    agent = NodeAgent(node, seed=seed)
    orch = Orchestrator(reg, ledger, [agent])
    mat = node.machines[0].materials[0]
    dfm = DfmReport(True, [], 0, (0, 0, 0), 0.0, node.machines[0].envelope_mm[2] and 6.0, 0.05)
    order, dfm = orch.place_order(buyer="acct:coordinator", asset_id=design.asset_id,
                                  qty=2, material=mat, buyer_lat=node.lat, buyer_lon=node.lon,
                                  required_tier=node.tier, dfm_override=dfm)
    settled = orch.execute_order(order, dfm)
    job = settled[0]
    ok_chain = NodeAgent.verify_chain(job, agent.public_key_hex)
    ok_escrow = ledger.escrow[order.order_id] == 0
    ok_cents = sum(ledger.balances.values()) == order.total_cents
    return ok_chain and ok_escrow and ok_cents


def main(argv=None):
    ap = argparse.ArgumentParser(description="BINGO node onboarding")
    ap.add_argument("--name", required=True, help="human name for your node")
    ap.add_argument("--operator", required=True, help="your payout account, e.g. acct:dana")
    ap.add_argument("--process", default="fdm", help="fdm | msla | cnc | inspection ...")
    ap.add_argument("--materials", default="PLA", help="comma list, e.g. PLA,PETG")
    ap.add_argument("--tier", type=int, default=0, help="0 hobbyist / 1 pro / 2 certified / 3 specialized")
    ap.add_argument("--machine", default="generic-fdm")
    ap.add_argument("--envelope", default="250x250x250", help="build volume mm, WxDxH")
    ap.add_argument("--lat", type=float, default=0.0)
    ap.add_argument("--lon", type=float, default=0.0)
    ap.add_argument("--rate", type=int, default=300, help="your rate, cents/hour")
    args = ap.parse_args(argv)

    print("── BINGO node onboarding ──")
    mats = [m.strip() for m in args.materials.split(",") if m.strip()]
    env = tuple(float(x) for x in args.envelope.lower().split("x"))
    node_id = "n-" + args.operator.replace("acct:", "")[:12]

    seed, pubkey = load_or_create_identity(node_id)
    print(f"✓ node identity ready — public key {pubkey[:16]}…")
    print(f"  (private seed saved locally at out/node_identity.json — NEVER share it)")

    node = NodeInfo(node_id=node_id, operator=args.operator, name=args.name,
                    lat=args.lat, lon=args.lon, tier=args.tier,
                    rate_cents_per_hour=args.rate,
                    machines=[Machine(machine_id=args.machine, make_model=args.machine,
                                      process=args.process, envelope_mm=env,
                                      materials=mats, kw=0.15)],
                    materials_on_hand=mats)

    print("Running install self-test (fabricate → sign → verify → settle)…")
    if self_test(node, seed):
        print("✓ SELF-TEST PASSED — your install fabricates, signs verifiable PoF, "
              "and settles to the cent.")
    else:
        print("✗ self-test FAILED — do not proceed; report this output.")
        return 1

    print("\n── send this to the pilot coordinator to get certified ──")
    print(json.dumps({
        "node_id": node_id, "name": args.name, "operator": args.operator,
        "public_key_hex": pubkey, "tier": args.tier,
        "process": args.process, "materials": mats,
        "envelope_mm": list(env), "rate_cents_per_hour": args.rate,
    }, indent=2))
    print("\nnext: the coordinator sends a calibration job for your job class; you "
          "print it and ship the first article for grade sign-off. Then you're live.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
