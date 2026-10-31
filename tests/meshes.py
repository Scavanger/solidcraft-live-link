"""Live-link meshes written the way SolidCraft writes them (docs/formats/live-mesh.md)."""

import base64
import struct


def b64(fmt, values):
    return base64.b64encode(struct.pack("<" + fmt * len(values), *values)).decode("ascii")


def box(key="k1", size=(10.0, 20.0, 30.0), origin=(5.0, 10.0, 15.0)):
    """A box as six quads on eight corners, positions relative to its centre."""
    a, b, c = size
    corners = [(x * a, y * b, z * c) for z in (0, 1) for y in (0, 1) for x in (0, 1)]
    faces = [[0, 2, 3, 1], [4, 5, 7, 6], [0, 1, 5, 4], [2, 6, 7, 3], [0, 4, 6, 2], [1, 3, 7, 5]]
    normals = [(0, 0, -1), (0, 0, 1), (0, -1, 0), (0, 1, 0), (-1, 0, 0), (1, 0, 0)]
    positions = [v - o for p in corners for v, o in zip(p, origin, strict=True)]
    loops = [i for f in faces for i in f]
    loop_normals = [v for n in normals for _ in range(4) for v in n]
    edges = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]
    return {
        "format": "solidcraft.live-mesh",
        "version": 1,
        "key": key,
        "origin": list(origin),
        "counts": {"vertices": 8, "polygons": 6, "loops": 24, "edges": 12},
        "positions": b64("f", positions),
        "poly_sizes": b64("I", [4] * 6),
        "loops": b64("I", loops),
        "loop_normals": b64("f", loop_normals),
        "poly_face": b64("I", list(range(6))),
        "edges": b64("I", [v for e in edges for v in e]),
        "edge_flags": base64.b64encode(bytes([3] * 12)).decode("ascii"),
        "edge_brep": b64("I", list(range(12))),
        "face_names": [f"F1:{n}" for n in ("bottom", "top", "front", "back", "left", "right")],
        "stats": {"triangles": 0, "quads": 6, "ngons": 0, "open_edges": 0},
    }
