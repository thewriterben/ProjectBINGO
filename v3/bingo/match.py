"""L3 — Matching/scheduling agent (v0).

Scores candidate nodes on tier fit, distance (ship-from-near is distributed
manufacturing's real advantage), reputation, and price; allocates units
across the top nodes so a run parallelizes geographically.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import NodeInfo
from .quote import haversine_km


@dataclass
class ScoredNode:
    node: NodeInfo
    score: float
    km: float


def score_nodes(nodes: list[NodeInfo], *, required_tier: int, material: str,
                buyer_lat: float, buyer_lon: float,
                rate_ceiling_cents: int = 3000) -> list[ScoredNode]:
    scored = []
    for n in nodes:
        if n.tier < required_tier:
            continue
        if not any(material in m.materials for m in n.machines):
            continue
        # declared inventory: a capable-but-dry node doesn't stall the run
        if n.materials_on_hand is not None and material not in n.materials_on_hand:
            continue
        km = haversine_km(n.lat, n.lon, buyer_lat, buyer_lon)
        distance_score = max(0.0, 1.0 - km / 3000.0)          # 0 beyond ~3000 km
        price_score = max(0.0, 1.0 - n.rate_cents_per_hour / rate_ceiling_cents)
        score = 0.40 * n.reputation + 0.35 * distance_score + 0.25 * price_score
        scored.append(ScoredNode(node=n, score=score, km=km))
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def allocate(qty: int, scored: list[ScoredNode], max_nodes: int = 3) -> list[tuple[NodeInfo, int]]:
    """Split qty across up to max_nodes best nodes, weighted by score.
    Every selected node gets >=1 unit; integer residue goes to the best node."""
    chosen = scored[:max_nodes]
    if not chosen:
        raise RuntimeError("no capable nodes for this order")
    if qty <= len(chosen):
        return [(s.node, 1) for s in chosen[:qty]]
    total_score = sum(s.score for s in chosen) or 1.0
    alloc = [max(1, int(qty * s.score / total_score)) for s in chosen]
    while sum(alloc) > qty:
        alloc[alloc.index(max(alloc))] -= 1
    alloc[0] += qty - sum(alloc)                              # residue -> best node
    return [(s.node, a) for s, a in zip(chosen, alloc) if a > 0]
