# DGD promo coin — anti-copy & redemption design

A DGD coin is a **$25 bearer instrument**: whoever presents a valid, unredeemed
coin gets the credit. That means it must resist two attacks, and no single
feature covers both. The design layers a digital defense and a physical one so a
failure of either alone doesn't lose the money.

## Threat model

1. **Counterfeit** — someone fabricates their own coin and QR.
2. **Copy / double-redeem** — someone photographs a *genuine* coin's QR (or
   duplicates a genuine coin) and tries to redeem the $25 more than once.

## The defenses

| Attack | Defense | Where it lives |
|---|---|---|
| Counterfeit | Ed25519-signed credential from the DGD issuer key; verified offline in the browser | the QR payload + the validation page |
| Copy of the QR | **Scratch-off claim code** — redemption requires a per-coin secret whose hash is committed in the signed credential; the secret is printed under a tamper-evident panel, never in the QR | `coin.py` (`secret_hash`) + physical panel |
| Double-redeem of one coin | **Single-use redemption ledger** — first redemption retires the serial; every replay is refused | `RedemptionRegistry` (validator-signed, hash-chained) |

The three compose: a photographed QR passes authenticity but has no code; a
stolen code redeems only once; a counterfeit fails authenticity outright.

## What's committed where

- **Public (on the coin, in the QR):** the signed credential — serial, $25
  credit, provenance passport head, issuer, and the *hash* of the scratch code.
  Anyone can verify authenticity and see the coin is worth $25, offline.
- **Secret (under the tamper-evident panel):** the scratch code itself. Its hash
  is in the credential, so revealing it proves physical possession, but the code
  cannot be derived from the public QR. High entropy (~70 bits), so unguessable.
- **Server-side:** the redemption ledger (which serials are spent, who was
  credited) — the single-use authority. Validator-signed and independently
  replayable (`verify_registry`).

## Physical production (per coin)

1. Mint: assign serial, generate a scratch code, sign the credential
   (`mint_coin(..., secret=code)`), keep the code to print. The coin's STL is the
   registered design asset; each coin is content-addressed provenance.
2. Print the coin (MSLA, Siraya Blu). The design already carries security-relief
   features (guilloché rings, binary microtext) that resist casual reproduction.
3. Apply the **public QR** (URL → digitalgold.co/redeem?c=…) openly on the coin.
4. Print the **scratch code under a tamper-evident scratch-off panel** (or a
   destructible holographic seal). If the panel is disturbed on arrival, the
   recipient knows the code may have been exposed — that itself is the signal.
5. Optional stronger uniqueness (only if a coin must be provably one-of-one in
   hand, not just redeemable-once): a serialized holographic security label, or a
   per-coin physical fingerprint (e.g. photographed cure/fleck pattern registered
   at mint). Not required for the $25 redemption guarantee — single-use covers
   that — but worth it for high-value or collectible tiers.

## Honest limits (say these plainly)

- Authenticity proves a coin was **issued by DGD**; it does not, by signature
  alone, prove a coin is **unique** — two identical genuine coins (or a coin and
  a perfect physical clone) look the same to the QR. Uniqueness-in-hand is what
  the tamper-evident panel and optional per-coin physical feature are for.
- The **$25 can only be spent once** regardless of how many copies exist — that
  guarantee is the single-use ledger, and it holds even against a perfect clone.
- The scratch-off is the load-bearing anti-copy for redemption. Its integrity
  depends on the physical panel actually being tamper-evident; source a real
  scratch/seal material, not printed ink that lifts cleanly.

## Redemption UX

Scan the QR → the page shows the coin is genuine and worth $25 (verified in the
browser) → scratch the panel and enter the code → $25 in validation credits is
redeemed, once. A copied QR gets as far as "genuine" and then stalls with no
code; a reused code is refused as already redeemed.
