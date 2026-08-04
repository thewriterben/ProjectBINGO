# DGD coin sticker — print spec & sourcing

What to order, who prints it, and the gotchas that decide whether it works. Hand
the "Print spec" section to a label vendor as-is.

## What this actually is (so you call the right vendor)

Not a normal sticker run. Two things make it a **variable-data security label**:

1. **Every coin's QR is different** (a unique code per coin) and
2. **Every coin's scratch-off code is different.**

That's "variable data printing" + "scratch-off security label." A shop that
only does bulk identical stickers can't do this. You supply the per-coin data as
a spreadsheet (the tool below generates it); the printer merges it onto each label.

## Layout (30 mm round)

Two workable options:

- **A — one label, both elements:** 30 mm round; QR in the upper ~18 mm, a
  scratch-off strip across the lower third hiding the code + printed serial.
  Tight but doable.
- **B — two labels (recommended):** a gold+black **QR label** on one face of the
  coin, and a separate small **scratch-off code label** on the other face (or the
  packaging). Cleaner, larger QR, easier to scan, and the tamper-evidence lives
  on its own element. Use this unless you specifically want everything on one side.

## Print spec (give this to the vendor)

- **Shape/size:** round, 30 mm diameter, die-cut (kiss-cut on roll or singles).
- **QR label**
  - **Base color:** gold — **matte, not metallic/foil** (see gotcha #2).
  - **QR color:** matte black.
  - **QR content:** short URL, `https://digitalgold.co/r/<serial>` — variable per
    label. ~20 chars → a sparse QR that scans small (see gotcha #1).
  - **Error correction:** level H.
  - **Quiet zone:** ≥4-module light border around the QR; keep it light-colored
    (a small white/pale inset behind the QR if the base is deep gold).
  - **Human-readable serial** printed under the QR (e.g. `DGD-2026-0001`).
- **Scratch-off code label**
  - **Scratch panel:** silver or gold scratch-off over the printed **variable
    code** (format `XXXX-XXXX-XXXX-XXXX`).
  - **Tamper-evidence:** destructible/acetate scratch material + security slits so
    a lifted/exposed panel is permanently visible. Ask for "tamper-evident
    scratch-off."
  - Optional: holographic scratch finish for extra anti-counterfeit + premium look.
- **Adhesive:** permanent, suited to cured resin (mention the substrate is a
  3D-printed resin coin so they pick the right adhesive).
- **Finish:** matte laminate over the QR (protects + kills glare). No gloss over
  the QR.

## Three gotchas that actually matter

1. **QR density vs. 30 mm.** Encoding the full signed credential makes a ~440-char,
   very dense QR that won't scan reliably at 30 mm on a curved coin. Use the
   **short URL** (`/r/<serial>`) — the server resolves it to the credential. The
   batch tool defaults to this.
2. **Metallic gold kills scannability.** Shiny/foil gold is reflective; glare
   makes scanners miss the QR, and black-on-metallic-gold contrast is marginal.
   Use **matte gold**, keep a **light quiet zone** around the QR, and **test-scan
   a proof** under phone-flash and store lighting before the full run. (Reliable
   scanning wants ~12:1 contrast; black-on-white is 21:1, black-on-matte-gold is
   borderline — the light quiet zone is what saves it.) If you insist on a foil
   look for the coin, put the QR on a matte inset patch.
3. **Handle the scratch codes as secrets.** The `scratch_code` column is the
   money. Send it only to the printer that applies the scratch panel, over a
   secure channel; it should never appear on the public face or in the QR. (It
   doesn't — the QR carries only the code's hash — but the print file does, so
   protect that file.)

## The data file you give the printer

Generate it with the batch tool — one row per coin:

    python -m provenance.coin_batch --count 500 --out out/coin/batch.csv

CSV columns: `serial`, `qr_url` (print in gold+black), `scratch_code` (print
under the panel), plus `secret_hash` / `passport_head` for your records. It also
writes `batch_credentials.json` — load that into the redemption server so the
short `/r/<serial>` URLs resolve. **Mint the real batch with DGD's production
issuer key** (the demo key is a placeholder), so the coins verify against the key
on digitalgold.co.

## Where to get it made

- **Scratch-off specialist** (for the code label): **Scratch Off Systems**
  (scratchoff.com) — round die-cut down to 2″, full-flood gold, holographic and
  tamper-evident (security slits + destructible acetate), MOQ ~250, ~8–10 business
  days. Confirm variable-data (unique code per label) when you quote.
- **Variable-data QR printer** (for the gold+black QR label): **Midwest Label
  Supply** — serialized/variable QR from a CSV, 200 → millions, no setup fee, US.
  Confirm matte-gold stock + 30 mm round die-cut. Alternatives: WePrintBarcodes,
  LabelValue, Lightning Labels.
- **Security-label houses that do both on one label** (variable QR + scratch-off +
  tamper-evidence, if you want option A): **Camcode**, **IMS Brand Protection**,
  and overseas manufacturers on Alibaba (lower unit cost, higher MOQ/lead time).

Get a **physical proof** and scan-test it before committing to a full run — the
gold/contrast behavior is the one thing you can't judge from a screen.
