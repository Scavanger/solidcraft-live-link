"""The link against a stand-in for SolidCraft's control channel."""

import json
import socket
import threading
import time

from solidcraft_link import decode
from solidcraft_link.link import Link
from meshes import box

TOKEN = "cd" * 32


class FakeSolidCraft:
    """Answers capabilities, subscribe and live.meshes; can push design.changed."""

    def __init__(self, live_meshes=1):
        self.live_meshes = live_meshes
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        self.requests = []
        self.conn = None
        self.revision = 1
        threading.Thread(target=self._serve, daemon=True).start()

    def _send(self, msg):
        self.conn.sendall((json.dumps(msg) + "\n").encode())

    def _serve(self):
        self.conn, _ = self.server.accept()
        for raw in self.conn.makefile("rb"):
            req = json.loads(raw)
            self.requests.append(req)
            if len(self.requests) == 1 and req.get("token") != TOKEN:
                self._send({"id": req["id"], "ok": False, "error": "unauthorized"})
                return
            method = req["method"]
            if method == "control.capabilities":
                self._send({"id": req["id"], "ok": True, "result": {"param_check": ["off"], "live_meshes": self.live_meshes}})
            elif method == "control.subscribe":
                self._send({"id": req["id"], "ok": True, "result": {"document_id": "d-1", "revision": self.revision}})
            elif method == "engine.execute" and req["params"]["command"] == "live.meshes":
                have = set(req["params"]["params"].get("have", []))
                key = f"box{self.revision}"
                meshes = [] if key in have else [box(key)]
                objects = [{"key": "Body1", "definition": "Body1", "component": 0, "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], "mesh": key, "visible": True, "color": [10, 20, 30], "opacity": 1.0}]
                self._send({"id": req["id"], "ok": True, "result": {"document_id": "d-1", "unit": "mm", "up": "Z", "components": [], "objects": objects, "meshes": meshes}})

    def change(self):
        self.revision += 1
        self._send({"event": "design.changed", "params": {"document_id": "d-1", "revision": self.revision}})

    def fetches(self):
        return [r for r in self.requests if r["method"] == "engine.execute"]


class Scene:
    def __init__(self):
        self.meshes = {}
        self.results = []

    def apply(self, result):
        self.results.append(result)
        for m in result["meshes"]:
            assert isinstance(m, decode.Mesh), m
            self.meshes[m.key] = m

    def have(self):
        return set(self.meshes)


def pump_until(link, done, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        link.pump()
        if done():
            return True
        time.sleep(0.01)
    return False


def test_follows_the_design():
    fake = FakeSolidCraft()
    scene = Scene()
    link = Link(apply=scene.apply, have=scene.have, params=lambda: {"quality": "fine"})
    link.live = True
    link.connect(port=fake.port, token=TOKEN)
    assert pump_until(link, lambda: len(scene.results) == 1), link.status
    assert link.status == "1 bodies"
    assert set(scene.meshes) == {"box1"}
    first = fake.fetches()[0]["params"]
    assert first == {"command": "live.meshes", "params": {"quality": "fine", "have": []}}
    # A change fetches again, sending the keys it holds.
    fake.change()
    assert pump_until(link, lambda: len(scene.results) == 2)
    assert fake.fetches()[1]["params"]["params"]["have"] == ["box1"]
    assert set(scene.meshes) == {"box1", "box2"}
    link.disconnect()


def test_not_live_waits_for_refresh():
    fake = FakeSolidCraft()
    scene = Scene()
    link = Link(apply=scene.apply, have=scene.have, params=dict)
    link.connect(port=fake.port, token=TOKEN)
    assert pump_until(link, lambda: len(scene.results) == 1)
    fake.change()
    time.sleep(0.2)
    link.pump()
    assert len(scene.results) == 1
    link.fetch()
    assert pump_until(link, lambda: len(scene.results) == 2)
    link.disconnect()


def test_an_app_without_live_link_is_refused():
    fake = FakeSolidCraft(live_meshes=None)
    scene = Scene()
    link = Link(apply=scene.apply, have=scene.have, params=dict)
    link.connect(port=fake.port, token=TOKEN)
    assert pump_until(link, lambda: "update SolidCraft" in link.status), link.status
    assert not scene.results


def test_changes_while_fetching_cost_one_more_fetch():
    fake = FakeSolidCraft()
    scene = Scene()
    link = Link(apply=scene.apply, have=scene.have, params=dict)
    link.live = True
    link.connect(port=fake.port, token=TOKEN)
    assert pump_until(link, lambda: len(scene.results) == 1)
    # Three events before the first reply is handled: one fetch for all of them.
    link.fetch()
    link.fetch()
    link.fetch()
    assert pump_until(link, lambda: len(scene.results) == 3)
    time.sleep(0.2)
    link.pump()
    assert len(fake.fetches()) == 3
    link.disconnect()
