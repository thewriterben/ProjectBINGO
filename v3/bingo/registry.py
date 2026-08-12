"""L1 — Asset Graph registry.

Content-addressed registration with the derivative-composition rule from
specs/ASSET-GRAPH.md: a child's effective split embeds each ancestor's
effective split, scaled by parent_share_bps, frozen at registration time.
"""

from __future__ import annotations

import os

from . import store as _store
from .models import (Asset, Split, SplitPayee, Derivation, License,
                     LicenseTemplate, sha256_hex, canonical_json)


class AssetRegistry:
    def __init__(self):
        self._assets: dict[str, Asset] = {}
        self._blobs: dict[str, bytes] = {}   # content store (stand-in for IPFS/object storage)

    # -- persistence (local store; stand-in for IPFS + chain registry) --------

    def save(self, store_dir: str, *, store=None):
        """Persist through the storage seam (`bingo/store.py`).

        This used to be a bare `json.dump` into an open handle, which truncates
        the destination before writing: a crash or a full disk halfway through
        left a **valid-looking, truncated manifest file**. What is in here is
        every asset's *effective split* - the routing table that decides who
        gets paid - so a half-written one is not a cosmetic loss.

        The default is still a JSON file at the same path with the same shape;
        it is now written atomically and fsynced.

        **One deliberate semantic change:** writing per-key makes this an upsert
        rather than a whole-file replace, so a save merges with what is already
        on disk instead of overwriting it. That is correct here rather than
        merely convenient - asset ids are content-addressed, so a registration
        only ever adds a key nothing else could be writing. Consequence to know:
        this class has no removal API, and if it grows one, deletion will have to
        be explicit rather than implied by absence.

        **What it does NOT fix.** `bingo/register.py` is load -> mutate -> save,
        and those are two separate store sessions - no transaction spans them.
        The upsert shrinks the losing window from that whole span to the save
        itself; it does not remove it, and under real contention the JSON backend
        still drops registrations. Narrowing a race is not closing it, and a race
        that fires rarely is the worse kind. `$BINGO_STORE=sqlite` is what
        actually closes it, by serializing the saves. Demonstrated three ways in
        `tests/test_node_storage.py`.
        """
        os.makedirs(os.path.join(store_dir, "blobs"), exist_ok=True)
        st = store if store is not None else _store.node_store(
            os.path.join(store_dir, "manifests"))
        try:
            with st.transaction():
                for aid, a in self._assets.items():
                    st.put(aid, a.manifest())
        finally:
            if store is None:
                st.close()
        for h, blob in self._blobs.items():
            path = os.path.join(store_dir, "blobs", h)
            if not os.path.exists(path):
                # content-addressed: the name IS the hash, so a torn blob would
                # simply fail its own check on load. Still written via a temp
                # file so a truncated one can't masquerade as complete.
                tmp = f"{path}.{os.getpid()}.tmp"
                with open(tmp, "wb") as f:
                    f.write(blob)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, path)

    @classmethod
    def load(cls, store_dir: str, *, store=None) -> "AssetRegistry":
        reg = cls()
        manifests = cls._read_manifests(store_dir, store)
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

    @staticmethod
    def _read_manifests(store_dir: str, store) -> dict:
        """Read the manifests, tolerating a registry written before the seam.

        A file already on an operator's disk was written by the old code path
        and must keep loading unchanged - a storage refactor that quietly
        orphans existing assets is a data-loss event wearing a tidy diff.
        """
        if store is not None:
            return dict(store.items())
        # under the default backend this resolves to `manifests.json` - the exact
        # path and shape the old code wrote, so legacy files load untouched. A
        # RuntimeError here means BINGO_STORE selects a backend whose file is
        # absent while the other one has data; let it propagate rather than
        # silently loading an empty registry.
        st = _store.node_store(os.path.join(store_dir, "manifests"))
        try:
            return dict(st.items())
        finally:
            st.close()

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
        # the asset_id is CONTENT-addressed — same content/split/license => same id.
        # registered_at is wall-clock metadata, not identity; folding it in made the
        # id time-dependent (violating "same provenance yields the same asset_id"
        # and flaking content-addressing). Hash the manifest WITHOUT it.
        ident = {k: v for k, v in asset.manifest().items() if k != "registered_at"}
        asset.asset_id = sha256_hex(canonical_json(ident))
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
