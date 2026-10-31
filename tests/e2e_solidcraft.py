"""Against a running SolidCraft (no Blender): ``python tests/e2e_solidcraft.py [port]``.

Starts a new design in the running app, follows it with the link, builds a box, a cylinder cut
and a fillet through a second connection, and checks what arrives after each change. Changes the
design open in that SolidCraft: run it on a scratch window.
"""

import json
import socket
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
package = types.ModuleType("solidcraft_link")
package.__path__ = [str(ROOT)]
sys.modules["solidcraft_link"] = package

from solidcraft_link import decode, discovery  # noqa: E402
from solidcraft_link.link import Link  # noqa: E402


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


class Scene:
    def __init__(self):
        self.meshes = {}
        self.objects = []
        self.updates = 0

    def apply(self, result):
        for m in result["meshes"]:
            if isinstance(m, tuple):
                raise RuntimeError(f"mesh {m[0]}: {m[1]}")
            self.meshes[m.key] = m
        self.objects = result["objects"]
        self.updates += 1

    def have(self):
        return set(self.meshes)

    def mesh_of(self, key):
        return next(self.meshes[o["mesh"]] for o in self.objects if o["key"] == key)


def wait(link, until, timeout=60.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        link.pump()
        if until():
            return
        time.sleep(0.02)
    raise TimeoutError(link.status)


def euler(m):
    edges = set()
    for i, n in enumerate(m.poly_sizes):
        s = m.loop_starts[i]
        corners = m.loops[s : s + n]
        for k in range(n):
            a, b = corners[k], corners[(k + 1) % n]
            edges.add((min(a, b), max(a, b)))
    return m.vertex_count - len(edges) + len(m.poly_sizes)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else None
    port, token = discovery.find(port)
    if token is None:
        sys.exit(f"no SolidCraft token for port {port}")
    cmd = Commands(port, token)
    cmd.run("file.new", {"name": "Live link check"})
    scene = Scene()
    link = Link(apply=scene.apply, have=scene.have, params=lambda: {"quality": "normal"})
    link.live = True
    link.connect(port=port, token=token)
    wait(link, lambda: scene.updates >= 1)
    print("connected:", link.status)

    steps = [
        ("solid.box", {"length": 40, "width": 30, "height": 10, "body_name": "Plate"}),
        ("solid.cylinder", {"radius": 6, "height": 10, "base": [20, 15, 0], "operation": "cut", "targets": ["Plate"]}),
        ("solid.fillet", {"edges": [[20, 0, 10]], "radius": 3}),
    ]
    for command, params in steps:
        before = scene.updates
        started = time.monotonic()
        cmd.run(command, params)

        def arrived(before=before):
            return scene.updates > before and any(o["key"] == "Plate" for o in scene.objects) and scene.objects[0]["mesh"] in scene.meshes

        wait(link, arrived)
        m = scene.mesh_of("Plate")
        flags = list(m.edge_flags)
        print(
            f"{command}: {time.monotonic() - started:.2f}s, {m.vertex_count} vertices, stats {m.stats}, euler {euler(m)}, "
            f"sharp {sum(1 for f in flags if f & decode.SHARP)}, tangent {sum(1 for f in flags if f & decode.TANGENT)}"
        )
        assert m.stats.get("open_edges") == 0, m.stats
    assert euler(scene.mesh_of("Plate")) == 0, "a plate with a hole has genus one"
    link.disconnect()
    print("e2e: ok")


if __name__ == "__main__":
    main()
