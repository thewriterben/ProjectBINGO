"""DGD promo coin, end to end:

    python -m provenance.coin_demo

Registers the coin as a DGD asset (content-addressed to the STL), mints a small
batch — each coin with a provenance passport (design → resin print → finish), a
signed $25 QR credit credential, AND a scratch-off claim code (physical
anti-copy) — writes a real QR (opening the validation page), then:

  * verifies an authentic coin vs. a counterfeit (self-signed) one, offline
  * redeems $25 once, WITH the scratch-off code (a photographed QR can't)
  * blocks the copied QR / missing code / counterfeit
  * independently replays the redemption ledger

Illustrative names; the crypto is real. The scratch codes below are what gets
printed under each coin's tamper-evident panel.
"""

from __future__ import annotations

import json
import os

from bingo.models import License, LicenseTemplate, Split, SplitPayee
from bingo.registry import AssetRegistry
from .passport import Actor, CutPassport, verify_passport
from .coin import (mint_coin, new_secret, qr_payload, qr_url, parse_qr,
                   verify_credential, RedemptionRegistry, verify_registry, CoinError)

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "out", "coin")
CREDIT = 2500


def register_asset(reg: AssetRegistry):
    with open(os.path.join(HERE, "dgd_coin.stl"), "rb") as f:
        stl = f.read()
    return reg.register(
        kind="design", title="DGD promo coin (Stunning Kasi 1)",
        creator="acct:designer:kasi", content=stl,
        license=License(LicenseTemplate.COMMERCIAL_PER_UNIT, per_unit_cents=0),
        split=Split([SplitPayee("acct:designer:kasi", 4000),
                     SplitPayee("acct:dgd:foundation", 4000),
                     SplitPayee("acct:ben", 2000)]))


def coin_passport(asset_id, serial, designer, printer, issuer) -> CutPassport:
    p = CutPassport(subject={"product": "DGD promo coin", "serial": serial,
                             "asset_id": asset_id[:16]})
    p.attest(designer, "DESIGN", {"asset_id": asset_id, "title": "Stunning Kasi 1",
                                  "designer": "Kasi"}, ts="2026-08-03T20:00:00Z")
    p.attest(printer, "FABRICATION", {"printer": "Creality Halot Mage Pro (MSLA)",
                                      "resin": "Siraya Tech Blu V2 Clear",
                                      "layer_um": 50, "resin_ml": 3.76, "serial": serial},
             ts="2026-08-03T21:30:00Z")
    p.attest(issuer, "FINISH", {"cured": True, "inspected": True,
                                "credit_cents": CREDIT, "serial": serial},
             ts="2026-08-03T22:00:00Z")
    return p


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    reg = AssetRegistry()
    asset = register_asset(reg)
    print(f"DGD coin asset registered: {asset.asset_id[:16]}…  "
          f"(content-addressed to the STL, {asset.content_bytes:,} bytes)")
    print("  split:", " · ".join(f"{p.account.replace('acct:','')} {p.bps/100:g}%"
                                 for p in asset.effective_split.payees))

    dgd = Actor.create("dgd", "Digital Gold Foundation (issuer)", "issuer", "acct:dgd:foundation")
    kasi = Actor.create("kasi", "Kasi (designer)", "designer", "acct:designer:kasi")
    node = Actor.create("ben-msla", "Ben's Halot Mage Pro", "node", "acct:node:ben-msla")

    coins = []  # (serial, passport_dict, credential, scratch_code)
    for n in range(1, 4):
        serial = f"DGD-2026-{n:04d}"
        pp = coin_passport(asset.asset_id, serial, kasi, node, dgd)
        secret = new_secret()
        cred = mint_coin(dgd, serial=serial, passport_head=pp.to_dict()["chain_head"],
                         credit_cents=CREDIT, secret=secret)
        coins.append((serial, pp.to_dict(), cred, secret))

    print(f"\nminted {len(coins)} coins — passport + $25 QR + scratch-off code:")
    for serial, pp, cred, secret in coins:
        pok, _ = verify_passport(pp)
        print(f"  {serial}  passport {'✓' if pok else '✗'}  credit $25  "
              f"scratch-code(under panel): {secret}")

    serial1, pp1, cred1, secret1 = coins[0]
    url = qr_url(cred1, "https://digitalgold.co")
    try:
        import qrcode
        qrcode.make(url).save(os.path.join(OUT, f"{serial1}.png"))
        print(f"\nQR opens: {url[:60]}…  → out/coin/{serial1}.png")
    except Exception as e:
        print("qr image skipped:", e)
    with open(os.path.join(OUT, f"{serial1}.json"), "w") as f:
        json.dump({"credential": cred1, "qr_url": url, "scratch_code": secret1,
                   "passport": pp1}, f, indent=2)

    print("\nauthenticity (offline, against the trusted DGD key):")
    print(f"  genuine coin  → {verify_credential(cred1, dgd.pubkey_hex)[1]}")
    fake = mint_coin(Actor.create("fake", "Counterfeiter", "issuer", "acct:dgd:foundation"),
                     serial=serial1, passport_head=pp1["chain_head"])
    print(f"  counterfeit   → {verify_credential(fake, dgd.pubkey_hex)[1]}")

    print("\nredemption ($25, single-use, requires the physical scratch-off code):")
    validator = Actor.create("dgd-validator", "DGD Validation", "validator", "acct:dgd:validator")
    registry = RedemptionRegistry(validator, trusted_issuer_pubkey=dgd.pubkey_hex)
    scanned = parse_qr(qr_payload(cred1))       # what the page decodes from the QR

    try:
        registry.redeem(scanned, "acct:holder:copycat", ts="2026-08-10T12:00:00Z")
    except CoinError as e:
        print(f"  photographed QR, no code → BLOCKED: {e}")
    rec = registry.redeem(scanned, "acct:holder:ambassador", secret=secret1,
                          ts="2026-08-10T12:01:00Z")
    print(f"  real coin + code         → REDEEMED, ${rec['credit_cents']/100:.0f} to {rec['to']}")
    try:
        registry.redeem(scanned, "acct:holder:thief", secret=secret1, ts="2026-08-10T12:05:00Z")
    except CoinError as e:
        print(f"  code reused (copy)       → BLOCKED: {e}")

    rok, rnotes = verify_registry(registry.to_dict())
    print(f"\nredemption ledger verify → {'OK' if rok else 'FAIL'}: {rnotes[-1]}")
    return 0 if rok else 1


if __name__ == "__main__":
    raise SystemExit(main())
