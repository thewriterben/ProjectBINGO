"""Register a physical real-world good as a first-class BINGO asset.

The trick that makes provenance native rather than bolted-on: an RWA asset's
*content is its passport*. BINGO already content-addresses every asset by the
SHA-256 of its bytes; for a design that's the STL, for a real-world good it's
the signed provenance passport. So the asset_id binds cryptographically to the
exact chain of custody — you cannot swap the provenance without minting a
different asset — and the asset's royalty split is simply the passport's own
value-routing split (the rancher included). Same registry, same marketplace,
same settlement primitives; a cow is just an asset whose blob is its history.
"""

from __future__ import annotations

import json

from bingo.models import (License, LicenseTemplate, Split, SplitPayee,
                          canonical_json)
from bingo.registry import AssetRegistry
from .passport import CutPassport, verify_passport


def _sale(pp: dict) -> dict:
    return next((e["data"] for e in pp["events"] if e["type"] == "SALE"), {})


def register_rwa(registry: AssetRegistry, passport: CutPassport, *,
                 creator: str):
    """Register a real-world good from its verified passport. The passport
    (canonical JSON) IS the asset content; its sale split IS the asset split.
    Refuses to register a passport that doesn't verify — you can't list what
    you can't prove."""
    pp = passport.to_dict()
    ok, notes = verify_passport(pp)
    if not ok:
        raise ValueError(f"passport does not verify: {notes[-1]}")

    sale = _sale(pp)
    payees = sale.get("split", {}).get("payees")
    if not payees:
        raise ValueError("passport has no sale split to route value through")
    split = Split([SplitPayee(p["account"], p["bps"]) for p in payees])
    price = int(sale.get("price_cents", 0))

    subj = pp["subject"]
    title = f'{subj.get("product","RWA")} · lot {subj.get("lot","")}'.strip(" ·")
    content = canonical_json(pp)                      # the passport IS the content

    return registry.register(
        kind="rwa", title=title, creator=creator, content=content,
        license=License(LicenseTemplate.COMMERCIAL_FLAT, flat_fee_cents=price),
        split=split)


def passport_of(registry: AssetRegistry, asset) -> dict:
    """Recover the passport for a registered RWA asset from its content blob.
    Because the blob is the passport, this round-trips exactly."""
    return json.loads(registry.get_content(asset).decode())
