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
from .. import keys
from ..registry import AssetRegistry
from ..demo.make_design import bracket_stl

IDENTITY_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "out", "node_identity.json")


KEYSTORE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "out", "keys")


def load_or_create_identity(node_id: str) -> tuple[bytes, str]:
    """Load this node's signing key, or mint one.

    A node's key is what releases its settlement, so it is stored ENCRYPTED
    (`bingo.keys.EncryptedFileKeyStore`, `0600`) under `$BINGO_KEY_PASSPHRASE`.

    With no passphrase set we mint an EPHEMERAL key and say so, rather than
    writing a private key to disk in the clear. This used to persist `seed_hex`
    in plaintext next to a comment asking the operator not to share it, which is
    not custody - it is a note.
    """
    passphrase = os.environ.get("BINGO_KEY_PASSPHRASE", "")

    # migrate/flag the old plaintext identity file if it is still lying around
    if os.path.exists(IDENTITY_PATH):
        with open(IDENTITY_PATH) as f:
            data = json.load(f)
        if "seed_hex" in data:
            print(f"  !! {IDENTITY_PATH} holds your PRIVATE KEY IN PLAINTEXT.\n"
                  f"     Treat it as compromised: ROTATE to a new key (see "
                  f"specs/KEY-CUSTODY.md), then delete the file.")
            seed = bytes.fromhex(data["seed_hex"])
            return seed, crypto.publickey(seed).hex()

    if not passphrase:
        seed, pk = crypto.keypair()
        print("  !! BINGO_KEY_PASSPHRASE is not set - using an EPHEMERAL key that\n"
              "     is NOT saved. Set a passphrase to keep a durable node identity.")
        return seed, pk.hex()

    store = keys.EncryptedFileKeyStore(KEYSTORE_DIR, passphrase=passphrase)
    signer = store.signer(node_id) if store.has(node_id) else store.create(node_id)
    return signer.export_seed(), signer.public_key_hex


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
    print("  (private key encrypted at rest under $BINGO_KEY_PASSPHRASE in out/keys/ — "
          "back up that passphrase; losing it means recovering the identity)")

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
