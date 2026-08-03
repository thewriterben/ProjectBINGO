# Join the network as a node

A node is any machine (or skilled person) that fabricates for the network. A
bedroom printer, a print farm, a CNC shop, or a human inspector all join the
same way. This is the pilot process — small, hands-on, and deliberately
narrow while we prove the loop.

## 1. Get the code

```
git clone https://github.com/thewriterben/ProjectBINGO
cd ProjectBINGO/v3
```

Python 3.10+ only. No dependencies to install — the whole thing is stdlib.

## 2. Onboard (creates your identity + proves your install)

```
python -m bingo.node.onboard --name "Your node" --operator acct:you \
    --process fdm --materials PLA,PETG --tier 0
```

This does three things:

- **Creates your node's cryptographic identity** — an Ed25519 keypair. The
  private seed is written to `out/node_identity.json` and never leaves your
  machine. Your public key is what lets anyone verify the work you sign.
- **Runs a self-test** — fabricates a part through your install, signs the
  proof-of-fabrication chain, verifies it under your key, and settles a mock
  order to the cent. If this passes, your install works end to end.
- **Prints your node card** — the JSON block to send the coordinator.

Send that block (never the seed) to whoever is running the pilot.

## 3. Get certified for a job class

Certification is per (design, process) — narrower than a general rating, so
a node good at functional brackets isn't wrongly trusted with premium
finish, and vice versa. The coordinator sends you a **calibration job**:
print it exactly as specified (no improvising the settings — the process
package *is* the job), and ship the first article for grade sign-off by an
inspector. Pass, and that job class routes to you, with periodic spot checks.

## 4. Connect real hardware (when you're ready)

- **Klipper / Moonraker printers (incl. Creality K2 Plus):** the driver
  talks to Moonraker directly. See `bingo/node/k2.py`; run a live dry-run
  with `python -m bingo.node.k2_node --host <printer-ip>`.
- **Resin / MSLA or anything without a live driver:** run in manual-attested
  mode (`python -m bingo.node.manual`) — you confirm each batch stage and
  attach photos, which become the evidence. Higher-grade work leans on
  first-article + spot-check inspection rather than live telemetry.

## What you're agreeing to

- You get paid per verified job, the moment delivery is confirmed, through
  transparent settlement you can see line-by-line. The network fee is a flat
  3% (for comparison, design platforms take 10–50%).
- You declare what you can do (process, materials, tier, materials on hand)
  and only matching work routes to you. You never take work above your
  certified grade.
- Every job you fabricate produces a signed evidence chain anyone can verify.
  That's the deal: the network trusts your work because it's provable, not
  because it knows you.

Questions or your node card ready? Open an issue or reach the coordinator.
