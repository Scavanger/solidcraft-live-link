"""Reading SolidCraft's live-link meshes (format ``solidcraft.live-mesh`` version 1).

Each array arrives as base64 of little-endian values and becomes an ``array.array`` here, which
Blender's ``foreach_set`` takes as it is. Everything is checked before Blender sees it: a bad
index would otherwise reach the mesh. No bpy here, so it can be tested on its own.
"""

import base64
import binascii
import sys
from array import array

FORMAT = "solidcraft.live-mesh"
VERSION = 1

# Edge flags.
BREP = 1
SHARP = 2
TANGENT = 4
SURFACE_SEAM = 8

_U32 = "I" if array("I").itemsize == 4 else "L"


class MeshError(ValueError):
    """A mesh that cannot be read."""


def _bytes(obj, key, required=True):
    text = obj.get(key)
    if text is None:
        if required:
            raise MeshError(f"the mesh has no {key}")
        return None
    if not isinstance(text, str):
        raise MeshError(f"{key} is not a base64 string")
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as e:
        raise MeshError(f"{key} is not base64: {e}") from None


def _typed(code, data, key):
    a = array(code)
    if len(data) % a.itemsize:
        raise MeshError(f"{key} has {len(data)} bytes, not a whole number of values")
    a.frombytes(data)
    if sys.byteorder == "big":
        a.byteswap()
    return a


class Mesh:
    """One decoded mesh: positions in millimetres with ``origin`` added back."""

    __slots__ = (
        "key",
        "positions",
        "poly_sizes",
        "loop_starts",
        "loops",
        "loop_normals",
        "poly_face",
        "edges",
        "edge_flags",
        "edge_brep",
        "face_names",
        "stats",
    )

    @property
    def vertex_count(self):
        return len(self.positions) // 3


def decode_mesh(obj):
    """A :class:`Mesh` from one entry of ``live.meshes``' ``meshes``; :class:`MeshError` when it
    is not one this add-on can read."""
    if not isinstance(obj, dict) or obj.get("format") != FORMAT:
        raise MeshError("not a SolidCraft live-link mesh")
    if obj.get("version") != VERSION:
        raise MeshError(f"mesh version {obj.get('version')} is not supported (this add-on reads version {VERSION}); update the add-on")
    key = obj.get("key")
    if not isinstance(key, str) or not key:
        raise MeshError("the mesh has no key")
    origin = obj.get("origin") or [0.0, 0.0, 0.0]
    if not (isinstance(origin, list) and len(origin) == 3 and all(isinstance(v, (int, float)) for v in origin)):
        raise MeshError("the mesh's origin is not three numbers")

    m = Mesh()
    m.key = key
    positions = _typed("f", _bytes(obj, "positions"), "positions")
    if len(positions) % 3:
        raise MeshError("positions are not whole points")
    ox, oy, oz = (float(v) for v in origin)
    if ox or oy or oz:
        for i in range(0, len(positions), 3):
            positions[i] += ox
            positions[i + 1] += oy
            positions[i + 2] += oz
    m.positions = positions
    vertices = len(positions) // 3

    m.poly_sizes = _typed(_U32, _bytes(obj, "poly_sizes"), "poly_sizes")
    m.loops = _typed(_U32, _bytes(obj, "loops"), "loops")
    starts = array(_U32, bytes(4 * len(m.poly_sizes)))
    total = 0
    for i, n in enumerate(m.poly_sizes):
        if n < 3:
            raise MeshError(f"polygon {i} has {n} corners")
        starts[i] = total
        total += n
    if total != len(m.loops):
        raise MeshError(f"the polygons have {total} corners but {len(m.loops)} are given")
    if m.loops and max(m.loops) >= vertices:
        raise MeshError("a corner names a vertex that is not there")
    m.loop_starts = starts

    normals = _bytes(obj, "loop_normals", required=False)
    m.loop_normals = _typed("f", normals, "loop_normals") if normals is not None else None
    if m.loop_normals is not None and len(m.loop_normals) != 3 * len(m.loops):
        raise MeshError("loop_normals do not match the corners")

    m.poly_face = _typed(_U32, _bytes(obj, "poly_face"), "poly_face")
    if len(m.poly_face) != len(m.poly_sizes):
        raise MeshError("poly_face does not match the polygons")

    m.edges = _typed(_U32, _bytes(obj, "edges"), "edges")
    m.edge_flags = _bytes(obj, "edge_flags")
    m.edge_brep = _typed(_U32, _bytes(obj, "edge_brep"), "edge_brep")
    if len(m.edges) != 2 * len(m.edge_flags) or len(m.edge_brep) != len(m.edge_flags):
        raise MeshError("the edge arrays do not match")
    if m.edges and max(m.edges) >= vertices:
        raise MeshError("an edge names a vertex that is not there")

    names = obj.get("face_names") or []
    m.face_names = [n if isinstance(n, str) else "" for n in names] if isinstance(names, list) else []
    m.stats = obj.get("stats") if isinstance(obj.get("stats"), dict) else {}
    return m


def column_major_rows(matrix, scale=1.0):
    """The 4×4 rows of a column-major matrix (16 numbers), its translation multiplied by
    ``scale``; the identity when it is not 16 numbers."""
    if not (isinstance(matrix, list) and len(matrix) == 16 and all(isinstance(v, (int, float)) for v in matrix)):
        return [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
    rows = [[float(matrix[col * 4 + row]) for col in range(4)] for row in range(4)]
    for row in range(3):
        rows[row][3] *= scale
    return rows


def srgb_to_linear(c):
    """One sRGB channel (0–255) as linear light (0–1), for a material's base colour."""
    v = max(0.0, min(1.0, c / 255.0))
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
