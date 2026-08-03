"""L3 — DFM agent (v0): real geometry checks on binary STL.

Parses binary STL from bytes; computes bounding box, signed volume
(divergence theorem over triangles), watertightness (every undirected edge
shared by exactly two triangles), and derives mass/time estimates used by
quoting. Honest heuristics, clearly labeled — this is the embryo of the
feasibility agent, not a slicer.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

# FDM heuristics (documented assumptions, tune later / per-profile)
PLA_DENSITY_G_CM3 = 1.24
EFFECTIVE_SOLIDITY = 0.42        # walls + infill as fraction of bounding solid volume
DEPOSITION_MM3_PER_S = 6.0       # realistic average FDM throughput


@dataclass
class DfmReport:
    ok: bool
    issues: list[str]
    triangles: int
    bbox_mm: tuple[float, float, float]
    volume_mm3: float
    est_grams_per_unit: float
    est_hours_per_unit: float


def parse_binary_stl(data: bytes) -> list[tuple]:
    if len(data) < 84:
        raise ValueError("not a binary STL (too short)")
    (count,) = struct.unpack_from("<I", data, 80)
    expected = 84 + count * 50
    if len(data) < expected:
        raise ValueError(f"binary STL truncated: {len(data)} < {expected}")
    tris = []
    off = 84
    for _ in range(count):
        vals = struct.unpack_from("<12fH", data, off)
        v0 = vals[3:6]; v1 = vals[6:9]; v2 = vals[9:12]
        tris.append((v0, v1, v2))
        off += 50
    return tris


def _signed_volume(tris) -> float:
    vol = 0.0
    for v0, v1, v2 in tris:
        vol += (v0[0] * (v1[1] * v2[2] - v1[2] * v2[1])
                - v0[1] * (v1[0] * v2[2] - v1[2] * v2[0])
                + v0[2] * (v1[0] * v2[1] - v1[1] * v2[0]))
    return vol / 6.0


def _watertight(tris) -> bool:
    edges: dict[tuple, int] = {}
    for v0, v1, v2 in tris:
        pts = [tuple(round(c, 4) for c in v) for v in (v0, v1, v2)]
        for a, b in ((pts[0], pts[1]), (pts[1], pts[2]), (pts[2], pts[0])):
            key = (a, b) if a <= b else (b, a)
            edges[key] = edges.get(key, 0) + 1
    return all(n == 2 for n in edges.values())


def analyze(stl_bytes: bytes, envelope_mm: tuple[float, float, float]) -> DfmReport:
    issues: list[str] = []
    tris = parse_binary_stl(stl_bytes)

    xs = [v[0] for t in tris for v in t]
    ys = [v[1] for t in tris for v in t]
    zs = [v[2] for t in tris for v in t]
    bbox = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))

    vol = abs(_signed_volume(tris))
    if vol < 1.0:
        issues.append("degenerate geometry: near-zero volume")
    if not _watertight(tris):
        issues.append("mesh is not watertight (non-manifold edges)")

    # envelope fit in any axis-aligned orientation (sorted-dims comparison)
    if sorted(bbox) > sorted(envelope_mm):
        issues.append(f"part {bbox} exceeds machine envelope {envelope_mm}")

    material_mm3 = vol * EFFECTIVE_SOLIDITY
    grams = material_mm3 / 1000.0 * PLA_DENSITY_G_CM3
    hours = material_mm3 / DEPOSITION_MM3_PER_S / 3600.0

    return DfmReport(ok=not issues, issues=issues, triangles=len(tris),
                     bbox_mm=bbox, volume_mm3=vol,
                     est_grams_per_unit=grams, est_hours_per_unit=hours)
