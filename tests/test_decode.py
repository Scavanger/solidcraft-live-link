import base64

import pytest
from meshes import b64, box
from solidcraft_link import decode


def test_a_box_reads_back():
    m = decode.decode_mesh(box())
    assert m.key == "k1"
    assert m.vertex_count == 8
    assert list(m.poly_sizes) == [4] * 6
    assert list(m.loop_starts) == [0, 4, 8, 12, 16, 20]
    assert len(m.loops) == 24 and len(m.loop_normals) == 72
    # The origin is added back: the corners of a 10 × 20 × 30 box at the origin.
    xs = sorted(set(round(v, 4) for v in m.positions[0::3]))
    zs = sorted(set(round(v, 4) for v in m.positions[2::3]))
    assert xs == [0.0, 10.0] and zs == [0.0, 30.0]
    assert list(m.poly_face) == list(range(6))
    assert len(m.edge_flags) == 12 and all(f == decode.BREP | decode.SHARP for f in m.edge_flags)
    assert m.face_names[1] == "F1:top"


def test_normals_may_be_left_out():
    obj = box()
    del obj["loop_normals"]
    assert decode.decode_mesh(obj).loop_normals is None


@pytest.mark.parametrize(
    "change, message",
    [
        ({"format": "other"}, "not a SolidCraft"),
        ({"version": 2}, "version 2"),
        ({"key": ""}, "no key"),
        ({"positions": "!!!"}, "not base64"),
        ({"positions": b64("f", [0.0, 1.0])}, "whole points"),
        ({"poly_sizes": b64("I", [4] * 5 + [2])}, "corners"),
        ({"loops": b64("I", [0] * 23 + [8])}, "not there"),
        ({"loop_normals": b64("f", [0.0] * 3)}, "loop_normals"),
        ({"poly_face": b64("I", [0])}, "poly_face"),
        ({"edges": b64("I", [0, 99] * 12)}, "not there"),
        ({"edge_flags": base64.b64encode(bytes(3)).decode()}, "edge arrays"),
        ({"origin": [0, 0]}, "origin"),
    ],
)
def test_bad_meshes_are_refused(change, message):
    obj = box()
    obj.update(change)
    with pytest.raises(decode.MeshError, match=message):
        decode.decode_mesh(obj)


def test_matrices_are_column_major():
    m = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 30, 40, 50, 1]
    rows = decode.column_major_rows(m, scale=0.001)
    assert rows[0] == [1.0, 0.0, 0.0, 0.03]
    assert rows[2][3] == pytest.approx(0.05)
    assert decode.column_major_rows("nonsense")[3] == [0.0, 0.0, 0.0, 1.0]


def test_srgb_to_linear():
    assert decode.srgb_to_linear(0) == 0.0
    assert decode.srgb_to_linear(255) == pytest.approx(1.0)
    assert decode.srgb_to_linear(128) == pytest.approx(0.2158605, abs=1e-6)
