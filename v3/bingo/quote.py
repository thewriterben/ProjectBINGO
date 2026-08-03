"""L3 — Quoting agent (v0): transparent line-item pricing from network state.

Every number the buyer sees decomposes into what the shop gets, what the
designer gets, what logistics costs, and what the network takes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .dfm import DfmReport
from .models import NodeInfo, Asset, LicenseTemplate

NETWORK_FEE_BPS = 300                 # 3%, published; governance-controlled
MATERIAL_CENTS_PER_G = {"PLA": 3, "PETG": 4, "ABS": 4}   # ~$25-40/kg retail
KWH_CENTS = 15
LOGISTICS_BASE_CENTS = 550            # small-parcel base
LOGISTICS_CENTS_PER_100KM = 40


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass
class JobQuote:
    node: NodeInfo
    qty: int
    fabrication_cents: int
    material_cents: int
    energy_cents: int
    logistics_cents: int
    royalty_cents: int
    fee_cents: int = 0                # filled by allocator (proportional)

    @property
    def subtotal_cents(self) -> int:
        return (self.fabrication_cents + self.material_cents + self.energy_cents
                + self.logistics_cents + self.royalty_cents)

    @property
    def total_cents(self) -> int:
        return self.subtotal_cents + self.fee_cents


def per_unit_royalty_cents(asset: Asset, declared_use: str) -> int:
    lic = asset.license
    if declared_use == "commercial" and lic.template == LicenseTemplate.COMMERCIAL_PER_UNIT:
        return lic.per_unit_cents
    if lic.template == LicenseTemplate.OPEN_ATTRIBUTION:
        return 0
    if declared_use == "personal":
        return 0
    return lic.per_unit_cents


def quote_job(node: NodeInfo, asset: Asset, dfm: DfmReport, qty: int,
              material: str, buyer_lat: float, buyer_lon: float,
              declared_use: str) -> JobQuote:
    machine = node.machines[0]
    hours = dfm.est_hours_per_unit * qty
    fabrication = round(hours * node.rate_cents_per_hour)
    material_c = round(dfm.est_grams_per_unit * qty * MATERIAL_CENTS_PER_G.get(material, 4))
    energy = round(hours * machine.kw * KWH_CENTS)
    km = haversine_km(node.lat, node.lon, buyer_lat, buyer_lon)
    logistics = LOGISTICS_BASE_CENTS + round(km / 100.0 * LOGISTICS_CENTS_PER_100KM)
    royalty = per_unit_royalty_cents(asset, declared_use) * qty
    return JobQuote(node=node, qty=qty, fabrication_cents=fabrication,
                    material_cents=material_c, energy_cents=energy,
                    logistics_cents=logistics, royalty_cents=royalty)


def apply_network_fee(quotes: list[JobQuote]) -> int:
    """Proportional fee per job; order-level rounding residue lands on the
    largest job so totals stay exact. Returns order total."""
    subtotals = [q.subtotal_cents for q in quotes]
    fee_total = round(sum(subtotals) * NETWORK_FEE_BPS / 10_000)
    assigned = 0
    for q in quotes:
        q.fee_cents = (q.subtotal_cents * NETWORK_FEE_BPS) // 10_000
        assigned += q.fee_cents
    if quotes and assigned != fee_total:
        biggest = max(quotes, key=lambda q: q.subtotal_cents)
        biggest.fee_cents += fee_total - assigned
    return sum(q.total_cents for q in quotes)
