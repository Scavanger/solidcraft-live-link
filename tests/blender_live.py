"""Against a running SolidCraft, inside Blender:
``blender --background --factory-startup --python tests/blender_live.py -- PORT [OUT_DIR]``.

Registers the add-on, connects with its own operator, builds a plate with a hole and a fillet in
SolidCraft through a second connection and checks the meshes Blender made after each change, then
refacets the plate. Changes the design open in that SolidCraft: run it on a scratch window. With
OUT_DIR it saves the scene and a render there. Exits with status 1 on the first failure.
"""

import importlib.util
import json
import socket
import sys
import time
import traceback
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent.parent


def load():
    spec = importlib.util.spec_from_file_location("solidcraft_link", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    module = importlib.util.module_from_spec(spec)
    sys.modules["solidcraft_link"] = module
    spec.loader.exec_module(module)
    module.register()
    return module


class Commands:
    """A plain second connection that runs commands."""

    def __init__(self, port, token):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=60)
        self.lines = self.sock.makefile("rb")
        self.token = token
        self.next = 1

    def run(self, command, params=None):
        line = {"id": self.next, "method": "engine.execute", "params": {"command": command, "params": params or {}}}
        if self.token:
            line["token"], self.token = self.token, None
        self.next += 1
        self.sock.sendall((json.dumps(line) + "\n").encode())
        while True:
            reply = json.loads(self.lines.readline())
            if reply.get("id") == line["id"]:
                if not reply.get("ok"):
                    raise RuntimeError(f"{command}: {reply.get('error')}")
                return reply["result"]


def check(cond, what):
    if not cond:
        raise AssertionError(what)


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    port = int(args[0]) if args else None
    out = Path(args[1]) if len(args) > 1 else None
    load()
    from solidcraft_link import discovery, operators, sync

    port, token = discovery.find(port)
    check(token is not None, f"no SolidCraft token for port {port}")
    cmd = Commands(port, token)
    cmd.run("file.new", {"name": "Blender live check"})

    settings = bpy.context.scene.solidcraft_link
    settings.port = port
    check(bpy.ops.solidcraft.connect() == {"FINISHED"}, "connect")
    link = operators.link()

    def wait(until, what, timeout=60.0):
        # Timers do not run in the background: pump as the add-on's timer would.
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            operators._pump()
            if until():
                return
            time.sleep(0.02)
        raise TimeoutError(f"{what}: {link.status}")

    wait(lambda: link.status.endswith("bodies"), "first fetch")

    def plate_key():
        obj = bpy.data.objects.get("Plate")
        return obj.data.get(sync.MESH_KEY) if obj is not None else None

    def inspect(label):
        obj = bpy.data.objects["Plate"]
        me = obj.data
        check(not me.validate(verbose=False), f"{label}: Blender had to fix the mesh")
        bm = bmesh.new()
        bm.from_mesh(me)
        manifold = all(len(e.link_faces) == 2 for e in bm.edges)
        loose = sum(1 for v in bm.verts if not v.link_edges)
        euler = len(bm.verts) - len(bm.edges) + len(bm.faces)
        bm.free()
        sizes = [len(p.vertices) for p in me.polygons]
        sharp = me.attributes.get("sharp_edge")
        sharp_n = sum(1 for d in sharp.data if d.value) if sharp is not None else 0
        seams = sum(1 for e in me.edges if e.use_seam) if hasattr(me.edges[0], "use_seam") else -1
        print(
            f"{label}: {len(me.vertices)} verts, {len(me.polygons)} polys "
            f"(tri {sizes.count(3)}, quad {sizes.count(4)}, ngon {sum(1 for n in sizes if n > 4)}), "
            f"euler {euler}, sharp {sharp_n}, seams {seams}"
        )
        check(manifold and loose == 0, f"{label}: closed, nothing loose")
        check(me.has_custom_normals, f"{label}: custom normals")
        check("sc_face" in me.attributes and "sc_face_names" in me, f"{label}: B-rep faces kept")
        return len(me.vertices), euler

    steps = [
        ("solid.box", {"length": 40, "width": 30, "height": 10, "body_name": "Plate"}),
        ("solid.cylinder", {"radius": 6, "height": 10, "base": [20, 15, 0], "operation": "cut", "targets": ["Plate"]}),
        ("solid.fillet", {"edges": [[20, 0, 10]], "radius": 3}),
    ]
    for command, params in steps:
        before = plate_key()
        cmd.run(command, params)
        wait(lambda: plate_key() not in (None, before), command)
        verts, euler = inspect(command)
    check(euler == 0, "a plate with a hole has genus one")
    check(abs(bpy.data.objects["Plate"].dimensions.x - 0.04) < 1e-6, "40 mm is 0.04 m")

    # Refacet the plate alone, coarser.
    obj = bpy.data.objects["Plate"]
    before = plate_key()
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    settings.quality = "coarse"
    check(bpy.ops.solidcraft.refacet() == {"FINISHED"}, "refacet")
    settings.quality = "normal"
    wait(lambda: plate_key() != before, "refacet")
    coarse, _ = inspect("refacet coarse")
    check(coarse < verts, f"coarse has fewer vertices: {coarse} vs {verts}")

    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        render(out, sync)
        bpy.ops.wm.save_as_mainfile(filepath=str(out / "live-link.blend"))
    link.disconnect()
    print("blender live: ok")


def render(out, sync):
    """A workbench render of the plate with its edges, as evidence."""
    scene = bpy.context.scene
    obj = bpy.data.objects["Plate"]
    for other in [o for o in bpy.data.objects if sync.OBJECT_KEY not in o]:
        bpy.data.objects.remove(other)  # the factory scene's cube, light and camera
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x, scene.render.resolution_y = 1200, 800
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = False
    wire = obj.modifiers.new("edges", "WIREFRAME")
    wire.thickness = 0.0002
    wire.use_replace = False
    wire.material_offset = 0
    data = bpy.data.cameras.new("Camera")
    data.type = "ORTHO"
    data.ortho_scale = 1.6 * max(obj.dimensions)
    cam = bpy.data.objects.new("Camera", data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    centre = sum(corners, Vector()) / 8
    cam.location = centre + Vector((0.6, -0.8, 0.7)) * max(obj.dimensions) * 3
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(out / "live-link.png")
    bpy.ops.render.render(write_still=True)
    obj.modifiers.remove(wire)


try:
    main()
except Exception:
    traceback.print_exc()
    sys.exit(1)
