"""Generates a real, watertight binary STL: a simple L-bracket.

Two abutting closed boxes (horizontal plate + vertical wall). Each box is a
closed shell, so the combined mesh passes the edge-manifold check and has a
well-defined volume. Winding is repaired programmatically against signed
volume, which is more robust than hand-deriving 24 triangle orientations.
"""

from __future__ import annotations

import struct


def _box_tris(x0, y0, z0, x1, y1, z1):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    quads = [(0, 3, 2, 1),   # bottom
             (4, 5, 6, 7),   # top
             (0, 1, 5, 4),   # front
             (2, 3, 7, 6),   # back
             (1, 2, 6, 5),   # right
             (0, 4, 7, 3)]   # left
    tris = []
    for a, b, c, d in quads:
        tris.append((v[a], v[b], v[c]))
        tris.append((v[a], v[c], v[d]))
    return tris


def _signed_volume(tris) -> float:
    vol = 0.0
    for v0, v1, v2 in tris:
        vol += (v0[0] * (v1[1] * v2[2] - v1[2] * v2[1])
                - v0[1] * (v1[0] * v2[2] - v1[2] * v2[0])
                + v0[2] * (v1[0] * v2[1] - v1[1] * v2[0]))
    return vol / 6.0


def _fix_winding(tris):
    if _signed_volume(tris) < 0:
        return [(a, c, b) for a, b, c in tris]
    return tris


def bracket_stl() -> bytes:
    """L-bracket: 60x40x4 mm base plate + 60x4x36 mm upright along one edge.
    The upright sinks 0.1 mm into the base so the shells share no coincident
    edges (edge-manifold check counts each undirected edge exactly twice per
    shell); the ~24 mm³ double-counted overlap is noise."""
    base = _fix_winding(_box_tris(0, 0, 0, 60, 40, 4))
    wall = _fix_winding(_box_tris(0.05, 0.05, 3.9, 59.95, 4, 40))
    tris = base + wall
    out = bytearray(b"BINGO v3 demo bracket".ljust(80, b"\0"))
    out += struct.pack("<I", len(tris))
    for v0, v1, v2 in tris:
        out += struct.pack("<3f", 0.0, 0.0, 0.0)          # normals recomputed by slicers
        for v in (v0, v1, v2):
            out += struct.pack("<3f", *v)
        out += struct.pack("<H", 0)
    return bytes(out)


def clip_stl() -> bytes:
    """'Remix': the bracket resized into a slim cable-clip-ish profile.
    Geometrically simple on purpose — the point is the derivative economics."""
    base = _fix_winding(_box_tris(0, 0, 0, 30, 12, 3))
    wall = _fix_winding(_box_tris(0.05, 0.05, 2.9, 29.95, 3, 15))
    tris = base + wall
    out = bytearray(b"BINGO v3 demo clip (remix)".ljust(80, b"\0"))
    out += struct.pack("<I", len(tris))
    for v0, v1, v2 in tris:
        out += struct.pack("<3f", 0.0, 0.0, 0.0)
        for v in (v0, v1, v2):
            out += struct.pack("<3f", *v)
        out += struct.pack("<H", 0)
    return bytes(out)
