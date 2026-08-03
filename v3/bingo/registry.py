"""L1 — Asset Graph registry.

Content-addressed registration with the derivative-composition rule from
specs/ASSET-GRAPH.md: a child's effective split embeds each ancestor's
effective split, scaled by parent_share_bps, frozen at registration time.
"""

from __future__ import annotations

import json
import os

from .models import (Asset, Split, SplitPayee, Derivation, License,
                     LicenseTemplate, sha256_hex, canonical_json)


class AssetRegistry:
    def __init__(self):
        self._assets: dict[str, Asset] = {}
        self._blobs: dict[str, bytes] = {}   # content store (stand-in for IPFS/object storage)

    # -- persistence (local store; stand-in for IPFS + chain registry) --------

    def save(self, store_dir: str):
        os.makedirs(os.path.join(store_dir, "blobs"), exist_ok=True)
        manifests = {aid: a.manifest() for aid, a in self._assets.items()}
        with open(os.path.join(store_dir, "manifests.json"), "w") as f:
            json.dump(manifests, f, indent=2)
        for h, blob in self._blobs.items():
            path = os.path.join(store_dir, "blobs", h)
            if not os.path.exists(path):
                with open(path, "wb") as f:
                    f.write(blob)

    @classmethod
    def load(cls, store_dir: str) -> "AssetRegistry":
        reg = cls()
        mpath = os.path.join(store_dir, "manifests.json")
        if not os.path.exists(mpath):
            return reg
        with open(mpath) as f:
            manifests = json.load(f)
        for aid, m in manifests.items():
            lic = m["license"]
            asset = Asset(
                kind=m["kind"], title=m["title"], creator=m["creator"],
                content_sha256=m["content"]["sha256"],
                content_bytes=m["content"]["bytes"],
                license=License(LicenseTemplate(lic["template"]),
                                per_unit_cents=lic["per_unit_cents"],
                                flat_fee_cents=lic["flat_fee_cents"],
                                training_share_bps=lic["training_share_bps"]),
                split=Split([SplitPayee(p["account"], p["bps"])
                             for p in m["split"]["payees"]]),
                derives_from=[Derivation(d["asset_id"], d["parent_share_bps"])
                              for d in m["derives_from"]],
                registered_at=m["registered_at"])
            asset.effective_split = Split([SplitPayee(p["account"], p["bps"])
                                           for p in m["effective_split"]["payees"]])
            asset.asset_id = aid
            reg._assets[aid] = asset
            bpath = os.path.join(store_dir, "blobs", asset.content_sha256)
            if os.path.exists(bpath):
                with open(bpath, "rb") as f:
                    reg._blobs[asset.content_sha256] = f.read()
        return reg

    # -- registration ------------------------------------------------------

    def register(self, *, kind: str, title: str, creator: str, content: bytes,
                 license: License, split: Split,
                 derives_from: list[Derivation] | None = None) -> Asset:
        split.validate()
        derives_from = derives_from or []
        content_hash = sha256_hex(content)
        asset = Asset(kind=kind, title=title, creator=creator,
                      content_sha256=content_hash, content_bytes=len(content),
                      license=license, split=split, derives_from=derives_from)
        asset.effective_split = self._compose_split(split, derives_from)
        asset.effective_split.validate()
        asset.asset_id = sha256_hex(canonical_json(asset.manifest()))
        self._assets[asset.asset_id] = asset
        self._blobs[content_hash] = content
        return asset

    def _compose_split(self, declared: Split, derivations: list[Derivation]) -> Split:
        """Effective split = ancestors' effective splits scaled by their shares,
        plus declared payees scaled by the remainder. Integer bps; rounding
        residue goes to the first declared payee (deterministic)."""
        parent_total = sum(d.parent_share_bps for d in derivations)
        if parent_total >= 10_000:
            raise ValueError("parent shares must total < 10000 bps")

        legs: dict[str, int] = {}

        def add(account: str, bps: int):
            if bps > 0:
                legs[account] = legs.get(account, 0) + bps

        for d in derivations:
            parent = self.get(d.asset_id)
            for p in parent.effective_split.payees:
                add(p.account, (p.bps * d.parent_share_bps) // 10_000)

        remainder = 10_000 - parent_total
        for p in declared.payees:
            add(p.account, (p.bps * remainder) // 10_000)

        # deterministic rounding repair -> first declared payee
        assigned = sum(legs.values())
        if assigned != 10_000:
            first = declared.payees[0].account
            legs[first] = legs.get(first, 0) + (10_000 - assigned)

        return Split(payees=[SplitPayee(a, b) for a, b in sorted(legs.items())])

    # -- reads ---------------------------------------------------------------

    def get(self, asset_id: str) -> Asset:
        return self._assets[asset_id]

    def get_content(self, asset: Asset) -> bytes:
        return self._blobs[asset.content_sha256]

    def all(self) -> list[Asset]:
        return list(self._assets.values())
