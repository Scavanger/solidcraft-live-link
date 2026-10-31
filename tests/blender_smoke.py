"""Run inside Blender: ``blender --background --factory-startup --python tests/blender_smoke.py``.

Registers the add-on from this folder, puts a stand-in ``live.meshes`` result into the scene and
checks what it made. Exits with status 1 on the first failure.
"""

import importlib.util
import sys
import traceback
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))


def load():
    spec = importlib.util.spec_from_file_location("solidcraft_link", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    module = importlib.util.module_from_spec(spec)
    sys.modules["solidcraft_link"] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def result(meshes, objects):
    return {
        "document_id": "d-1",
        "unit": "mm",
        "up": "Z",
        "components": [{"id": 3, "name": "Bracket", "parent": 0}],
        "objects": objects,
        "meshes": meshes,
    }


def obj(key, mesh, x=0.0, component=3, color=(32, 160, 128), faces=None):
    return {
        "key": key,
        "definition": "Part",
        "component": component,
        "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, 0, 0, 1],
        "mesh": mesh,
        "visible": True,
        "color": list(color),
        "opacity": 1.0,
        "faces": faces or [],
    }


def main():
    load()
    from meshes import box
    from solidcraft_link import decode, sync

    def check(cond, what):
        if not cond:
            raise AssertionError(what)

    mesh = decode.decode_mesh(box("k1"))
    faces = [{"face": 1, "color": [255, 0, 0], "opacity": 1.0}]
    sync.apply(result([mesh], [obj("Body1", "k1", faces=faces), obj("Body1 (K:2)", "k1", x=30.0, color=(200, 200, 0))]), scale=0.001)

    a, b = bpy.data.objects["Body1"], bpy.data.objects["Body1 (K:2)"]
    me = a.data
    check(a.data == b.data, "placements share one mesh")
    check(
        (len(me.vertices), len(me.polygons), len(me.edges)) == (8, 6, 12),
        f"8/6/12, got {len(me.vertices)}/{len(me.polygons)}/{len(me.edges)}",
    )
    check(abs(b.matrix_world.translation.x - 0.03) < 1e-9, f"30 mm is 0.03 m, got {b.matrix_world.translation.x}")
    xs = sorted({round(v.co.x, 6) for v in me.vertices})
    check(xs == [0.0, 0.01], f"10 mm box in metres, got {xs}")
    seams = [e.use_seam for e in me.edges] if hasattr(me.edges[0], "use_seam") else list(me.attributes[".uv_seam"].data)
    check(all(seams), "every box edge is a seam")
    sharp = me.attributes.get("sharp_edge")
    check(sharp is not None and all(d.value for d in sharp.data), "every box edge is sharp")
    face = me.attributes.get("sc_face")
    check(face is not None and sorted(d.value for d in face.data) == list(range(6)), "sc_face per polygon")
    check(list(me["sc_face_names"])[1] == "F1:top", "face names kept")
    check(me.has_custom_normals, "custom normals set")
    check(a.users_collection[0].name == "Bracket [3]", f"component collection, got {a.users_collection[0].name}")
    check(a.users_collection[0].name in bpy.data.collections["SolidCraft"].children, "under SolidCraft")
    check(
        a.material_slots[0].link == "OBJECT" and a.material_slots[0].material != b.material_slots[0].material, "each placement its own look"
    )
    check(any(p.material_index == 1 for p in me.polygons), "the red face has its own slot")
    check(sync.held_mesh_keys() == {"k1"}, f"held keys, got {sync.held_mesh_keys()}")

    # The same mesh again (the caller had it): nothing is rebuilt.
    sync.apply(result([], [obj("Body1", "k1"), obj("Body1 (K:2)", "k1", x=40.0)]), scale=0.001)
    check(bpy.data.objects["Body1"].data == me, "a held mesh is kept")
    check(abs(bpy.data.objects["Body1 (K:2)"].matrix_world.translation.x - 0.04) < 1e-9, "moved")

    # A changed body gets a new mesh; the old one goes when nothing uses it.
    sync.apply(result([decode.decode_mesh(box("k2", size=(5.0, 5.0, 5.0)))], [obj("Body1", "k2")]), scale=0.001)
    check("Body1 (K:2)" not in bpy.data.objects, "a body that is gone is removed")
    check(bpy.data.objects["Body1"].data[sync.MESH_KEY] == "k2", "new mesh")
    check(sync.held_mesh_keys() == {"k2"}, f"old mesh removed, got {sync.held_mesh_keys()}")

    # A body whose mesh is still to come keeps what it has.
    sync.apply(result([], [obj("Body1", "k3")]), scale=0.001)
    check("Body1" in bpy.data.objects and bpy.data.objects["Body1"].data[sync.MESH_KEY] == "k2", "pending keeps the object")
    print("blender smoke: ok")


try:
    main()
except Exception:
    traceback.print_exc()
    sys.exit(1)
