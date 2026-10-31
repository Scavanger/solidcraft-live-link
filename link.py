"""Following the design: connect, subscribe, and fetch meshes when it changes.

One ``live.meshes`` request is out at a time. A change that comes meanwhile is noted and fetched
once the reply is in, so a burst of edits costs one more request, not one per edit. The scene is
changed only through the ``apply`` and ``have`` functions given, so this runs without Blender.
"""

import time

from . import discovery
from .client import Client

SUPPORTED_MESH_VERSION = 1


class Link:
    def __init__(self, apply, have, params, client=None, clock=time.monotonic):
        """``apply(result)`` puts a ``live.meshes`` result in the scene, ``have()`` lists the mesh
        keys held, ``params()`` gives the request's tessellation parameters and overrides."""
        self.client = client or Client()
        self.apply = apply
        self.have = have
        self.params = params
        self.clock = clock
        self.live = False
        self.status = "Not connected"
        self.document_id = None
        self._in_flight = False
        self._dirty = False
        self._pending_since = None
        self._last_poll = 0.0

    @property
    def connected(self):
        return self.client.connected

    def connect(self, host="127.0.0.1", port=None, token=None):
        if token is None:
            port, token = discovery.find(port)
            if token is None:
                self.status = f"No SolidCraft found (no token for port {port})"
                raise ConnectionError(self.status)
        elif port is None:
            port = discovery.DEFAULT_PORT
        self.client.connect(host, port, token)
        self.status = f"Connecting to port {port}…"
        self.client.request("control.capabilities", {}, self._on_capabilities)

    def disconnect(self):
        self.client.close()
        self._in_flight = self._dirty = False
        self._pending_since = None
        self.status = "Not connected"

    def set_live(self, live):
        self.live = live
        if live and self.connected:
            self.fetch()

    def fetch(self):
        """Ask for the design now, or as soon as the request out is answered."""
        if not self.connected:
            return
        if self._in_flight:
            self._dirty = True
            return
        params = dict(self.params())
        params["have"] = sorted(self.have())
        self._in_flight = True
        self._dirty = False
        self.client.request("engine.execute", {"command": "live.meshes", "params": params}, self._on_meshes, meshes=True)

    def pump(self):
        """Run what came in; call from a timer on Blender's main thread."""
        self.client.pump(self._on_event, self._on_closed)
        # A request the app has not answered in time is still running there: ask for its reply.
        if self._pending_since is not None and self.connected and self.clock() - self._last_poll > 1.0:
            self._last_poll = self.clock()
            self.client.request("control.pending", {}, self._on_pending)

    def _on_capabilities(self, reply):
        version = (reply.get("result") or {}).get("live_meshes") if reply.get("ok") else None
        if version != SUPPORTED_MESH_VERSION:
            self.status = (
                "This SolidCraft has no live link (update SolidCraft)"
                if version is None
                else f"SolidCraft sends mesh version {version}; update the add-on"
            )
            self.client.close()
            return
        self.client.request("control.subscribe", {}, self._on_subscribed)

    def _on_subscribed(self, reply):
        if not reply.get("ok"):
            self.status = f"Could not follow the design: {reply.get('error')}"
            return
        self.document_id = (reply.get("result") or {}).get("document_id")
        self.status = "Connected"
        self.fetch()

    def _on_event(self, msg):
        if msg.get("event") != "design.changed":
            return
        self.document_id = (msg.get("params") or {}).get("document_id", self.document_id)
        if self.live:
            self.fetch()

    def _on_meshes(self, reply):
        if not reply.get("ok") and reply.get("running"):
            # Still computing in the app (a very large design): its reply is kept for us.
            self._pending_since = self.clock()
            self.status = "SolidCraft is still meshing…"
            return
        self._in_flight = False
        self._pending_since = None
        if not reply.get("ok"):
            self.status = f"SolidCraft: {reply.get('error')}"
            return
        result = reply.get("result") or {}
        self.document_id = result.get("document_id", self.document_id)
        try:
            self.apply(result)
        except Exception as e:  # noqa: BLE001 - shown to the user; the link keeps running
            self.status = f"Could not update the scene: {e}"
            return
        objects = len(result.get("objects") or [])
        self.status = f"{objects} bodies"
        if result.get("pending") or self._dirty:
            self.fetch()

    def _on_pending(self, reply):
        result = reply.get("result") or {}
        if result.get("done") and isinstance(result.get("reply"), dict):
            self._pending_since = None
            from .client import _decode_meshes

            inner = result["reply"]
            _decode_meshes(inner)
            self._on_meshes(inner)
        elif result.get("pending") is None:
            # Nothing outstanding any more: ask again.
            self._pending_since = None
            self._in_flight = False
            self.fetch()

    def _on_closed(self, reason):
        self._in_flight = self._dirty = False
        self._pending_since = None
        self.status = f"Disconnected: {reason}"
