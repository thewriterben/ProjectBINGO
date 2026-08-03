"""Core data models. All money is integer cents; all hashes SHA-256 hex."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


# ---------------------------------------------------------------- L1: assets

class LicenseTemplate(str, Enum):
    PERSONAL = "personal"
    COMMERCIAL_FLAT = "commercial-flat"
    COMMERCIAL_PER_UNIT = "commercial-per-unit"
    OPEN_ATTRIBUTION = "open-attribution"
    NETWORK_TRAINING = "network-training"


@dataclass
class License:
    template: LicenseTemplate
    per_unit_cents: int = 0
    flat_fee_cents: int = 0
    training_share_bps: int = 0

    def to_dict(self):
        return {"template": self.template.value, "per_unit_cents": self.per_unit_cents,
                "flat_fee_cents": self.flat_fee_cents, "training_share_bps": self.training_share_bps}


@dataclass
class SplitPayee:
    account: str
    bps: int  # basis points of 10_000


@dataclass
class Split:
    payees: list[SplitPayee]

    def validate(self):
        total = sum(p.bps for p in self.payees)
        if total != 10_000:
            raise ValueError(f"split must sum to 10000 bps, got {total}")
        if any(p.bps <= 0 for p in self.payees):
            raise ValueError("split payees must have positive bps")

    def to_dict(self):
        return {"payees": [{"account": p.account, "bps": p.bps} for p in self.payees]}


@dataclass
class Derivation:
    asset_id: str
    parent_share_bps: int  # share of the child's royalty owed to the parent's split


@dataclass
class Asset:
    kind: str
    title: str
    creator: str
    content_sha256: str
    content_bytes: int
    license: License
    split: Split                      # declared payees for THIS asset's own share
    derives_from: list[Derivation] = field(default_factory=list)
    registered_at: str = field(default_factory=now_iso)
    effective_split: Optional[Split] = None  # frozen at registration (composition rule)
    asset_id: str = ""

    def manifest(self) -> dict:
        return {
            "schema": "bingo/asset/0.1",
            "kind": self.kind, "title": self.title, "creator": self.creator,
            "content": {"sha256": self.content_sha256, "bytes": self.content_bytes},
            "license": self.license.to_dict(),
            "split": self.split.to_dict(),
            "effective_split": self.effective_split.to_dict() if self.effective_split else None,
            "derives_from": [{"asset_id": d.asset_id, "parent_share_bps": d.parent_share_bps}
                             for d in self.derives_from],
            "registered_at": self.registered_at,
        }


# ------------------------------------------------------------- L2: fab net

@dataclass
class Machine:
    machine_id: str
    make_model: str
    process: str                      # "fdm" | "sla" | "cnc" | "inspection" | ...
    envelope_mm: tuple[float, float, float]
    materials: list[str]
    kw: float = 0.15                  # nominal power draw while printing


@dataclass
class NodeInfo:
    node_id: str
    operator: str                     # account URI paid for fabrication
    name: str
    lat: float
    lon: float
    tier: int
    rate_cents_per_hour: int
    machines: list[Machine]
    reputation: float = 0.5           # [0,1]; new nodes start mid-low
    completed_jobs: int = 0
    failed_jobs: int = 0
    materials_on_hand: list[str] | None = None  # declared inventory; None = undeclared
                                                # (matching routes around dry nodes when declared)


class JobState(str, Enum):
    OFFERED = "OFFERED"
    ACCEPTED = "ACCEPTED"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    SETTLED = "SETTLED"
    DECLINED = "DECLINED"
    FAILED = "FAILED"


@dataclass
class EvidenceEvent:
    """One link in a job's hash-chained, node-signed PoF log."""
    seq: int
    ts: str
    type: str
    data: dict
    prev_hash: str
    sig: str = ""
    hash: str = ""

    def body(self) -> dict:
        return {"seq": self.seq, "ts": self.ts, "type": self.type,
                "data": self.data, "prev_hash": self.prev_hash}


@dataclass
class RoyaltyLine:
    """One asset's royalty on a job, routed to that asset's own effective
    split at settlement. A job with a design + a process package + a
    derivative carries one line each — each settles to its own payees."""
    asset_id: str
    cents: int
    payees: list  # list[SplitPayee] — the asset's frozen effective_split


@dataclass
class Job:
    job_id: str
    order_id: str
    asset_id: str
    node_id: str
    qty: int
    material: str
    state: JobState = JobState.OFFERED
    evidence: list[EvidenceEvent] = field(default_factory=list)
    # quoted amounts (cents) frozen at match time:
    fabrication_cents: int = 0
    material_cents: int = 0
    energy_cents: int = 0
    logistics_cents: int = 0
    royalty_lines: list[RoyaltyLine] = field(default_factory=list)
    fee_cents: int = 0

    @property
    def royalty_cents(self) -> int:
        """Total royalty across all lines (convenience for totals/quotes)."""
        return sum(l.cents for l in self.royalty_lines)

    @property
    def job_total_cents(self) -> int:
        return (self.fabrication_cents + self.material_cents + self.energy_cents
                + self.logistics_cents + self.royalty_cents + self.fee_cents)

    def chain_head(self) -> str:
        return self.evidence[-1].hash if self.evidence else "0" * 64


@dataclass
class Order:
    order_id: str
    buyer: str
    asset_id: str
    qty: int
    material: str
    buyer_lat: float
    buyer_lon: float
    declared_use: str = "commercial"
    jobs: list[Job] = field(default_factory=list)
    total_cents: int = 0
    created_at: str = field(default_factory=now_iso)

    def summary(self) -> dict:
        d = asdict(self)
        d["jobs"] = [j.job_id for j in self.jobs]
        return d
