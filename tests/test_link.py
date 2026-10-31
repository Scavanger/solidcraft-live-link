"""The link against a stand-in for SolidCraft's control channel."""

import json
import socket
import threading
import time

import pytest
from meshes import box
from solidcraft_link import decode
from solidcraft_link.link import Link

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
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def close(self):
        if self.conn is not None:
            try:
                self.conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.conn.close()
        self.server.close()
        self.thread.join(5)

    def _send(self, msg):
        self.conn.sendall((json.dumps(msg) + "\n").encode())

    def _serve(self):
        try:
            self.conn, _ = self.server.accept()
            with self.conn.makefile("rb") as lines:
                for raw in lines:
                    if not self._answer(json.loads(raw)):
                        return
        except (OSError, ValueError):  # closed by the test
            pass

    def _answer(self, req):
        """Answer one request; False ends the connection."""
        self.requests.append(req)
        if len(self.requests) == 1 and req.get("token") != TOKEN:
            self._send({"id": req["id"], "ok": False, "error": "unauthorized"})
            return False
        method = req["method"]
        if method == "control.capabilities":
            self._send({"id": req["id"], "ok": True, "result": {"param_check": ["off"], "live_meshes": self.live_meshes}})
        elif method == "control.subscribe":
            self._send({"id": req["id"], "ok": True, "result": {"document_id": "d-1", "revision": self.revision}})
        elif method == "engine.execute" and req["params"]["command"] == "live.meshes":
            have = set(req["params"]["params"].get("have", []))
            key = f"box{self.revision}"
            meshes = [] if key in have else [box(key)]
            objects = [
                {
                    "key": "Body1",
                    "definition": "Body1",
                    "component": 0,
                    "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                    "mesh": key,
                    "visible": True,
                    "color": [10, 20, 30],
                    "opacity": 1.0,
                }
            ]
            self._send(
                {
                    "id": req["id"],
                    "ok": True,
                    "result": {"document_id": "d-1", "unit": "mm", "up": "Z", "components": [], "objects": objects, "meshes": meshes},
                }
            )
        return True

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


@pytest.fixture
def solidcraft():
    """Makes stand-ins for SolidCraft, closed after the test."""
    fakes = []

    def make(**kwargs):
        fakes.append(FakeSolidCraft(**kwargs))
        return fakes[-1]

    yield make
    for fake in fakes:
        fake.close()


@pytest.fixture
def follow():
    """Connects a link to a stand-in, disconnected after the test: ``(link, scene)``."""
    links = []

    def make(fake, params=dict, live=False):
        scene = Scene()
        link = Link(apply=scene.apply, have=scene.have, params=params)
        link.live = live
        link.connect(port=fake.port, token=TOKEN)
        links.append(link)
        return link, scene

    yield make
    for link in links:
        link.disconnect()


def pump_until(link, done, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        link.pump()
        if done():
            return True
        time.sleep(0.01)
    return False


def test_follows_the_design(solidcraft, follow):
    fake = solidcraft()
    link, scene = follow(fake, params=lambda: {"quality": "fine"}, live=True)
    assert pump_until(link, lambda: len(scene.results) == 1), link.status
    assert link.status == "1 bodies"
    assert set(scene.meshes) == {"box1"}
    first = fake.fetches()[0]["params"]
    assert first == {"command": "live.meshes", "params": {"quality": "fine", "have": []}}
    # A change fetches again, sending the keys it holds.
    fake.change()
    assert pump_until(link, lambda: len(scene.results) == 2), link.status
    assert fake.fetches()[1]["params"]["params"]["have"] == ["box1"]
    assert set(scene.meshes) == {"box1", "box2"}


def test_not_live_waits_for_refresh(solidcraft, follow):
    fake = solidcraft()
    link, scene = follow(fake)
    assert pump_until(link, lambda: len(scene.results) == 1), link.status
    fake.change()
    time.sleep(0.2)
    link.pump()
    assert len(scene.results) == 1
    link.fetch()
    assert pump_until(link, lambda: len(scene.results) == 2), link.status


def test_an_app_without_live_link_is_refused(solidcraft, follow):
    link, scene = follow(solidcraft(live_meshes=None))
    assert pump_until(link, lambda: "update SolidCraft" in link.status), link.status
    assert not scene.results


def test_changes_while_fetching_cost_one_more_fetch(solidcraft, follow):
    fake = solidcraft()
    link, scene = follow(fake, live=True)
    assert pump_until(link, lambda: len(scene.results) == 1), link.status
    # Three events before the first reply is handled: one fetch for all of them.
    link.fetch()
    link.fetch()
    link.fetch()
    assert pump_until(link, lambda: len(scene.results) == 3), link.status
    time.sleep(0.2)
    link.pump()
    assert len(fake.fetches()) == 3


def test_connecting_again_keeps_the_new_connection(solidcraft, follow):
    first, second = solidcraft(), solidcraft()
    link, scene = follow(first)
    assert pump_until(link, lambda: len(scene.results) == 1), link.status
    # Connect elsewhere without disconnecting: the old connection's end must not close the new one.
    link.connect(port=second.port, token=TOKEN)
    assert pump_until(link, lambda: len(scene.results) == 2), link.status
    time.sleep(0.2)
    link.pump()
    assert link.connected, link.status
    assert len(second.fetches()) == 1
