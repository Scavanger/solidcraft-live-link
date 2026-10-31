"""The control-channel connection: JSON lines over a local socket, read on a thread of its own.

Blender's data may only be touched on its main thread, so the reader thread never calls back:
it parses lines (and decodes meshes, the slow part) and queues them, and :meth:`Client.pump`,
called from a timer on the main thread, hands them on. No bpy here.
"""

import json
import queue
import socket
import threading

from . import decode

# The control channel refuses a request line over 16 MiB; ours are far smaller.
MAX_REQUEST = 16 << 20


class Client:
    def __init__(self):
        self._sock = None
        self._lock = threading.Lock()
        self._queue = queue.Queue()
        self._next_id = 1
        self._waiting = {}  # id -> (callback, decode meshes?)
        self._token = None
        self._thread = None

    @property
    def connected(self):
        return self._sock is not None

    def connect(self, host, port, token, timeout=5.0):
        """Open the connection; the token goes with the first request."""
        self.close()
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(None)
        self._sock = sock
        self._token = token
        self._thread = threading.Thread(target=self._read, args=(sock,), name="solidcraft-link", daemon=True)
        self._thread.start()

    def close(self):
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        with self._lock:
            self._waiting.clear()

    def request(self, method, params=None, callback=None, meshes=False):
        """Send a request; ``callback(reply)`` runs in :meth:`pump` when its reply comes. With
        ``meshes``, the reply's ``result.meshes`` arrive decoded (see :func:`decode.decode_mesh`)."""
        if self._sock is None:
            raise ConnectionError("not connected to SolidCraft")
        with self._lock:
            rid = self._next_id
            self._next_id += 1
            line = {"id": rid, "method": method, "params": params or {}}
            if self._token is not None:
                line["token"] = self._token
                self._token = None
            self._waiting[rid] = (callback, meshes)
        data = (json.dumps(line, separators=(",", ":")) + "\n").encode("utf-8")
        if len(data) > MAX_REQUEST:
            raise ValueError("request too large for the control channel")
        try:
            self._sock.sendall(data)
        except OSError as e:
            self._queue.put(("closed", str(e)))
            raise ConnectionError(str(e)) from None
        return rid

    def pump(self, on_event, on_closed, limit=64):
        """Hand on what the reader queued: replies to their callbacks, events to ``on_event``,
        a lost connection to ``on_closed``. Main thread only."""
        for _ in range(limit):
            try:
                kind, *rest = self._queue.get_nowait()
            except queue.Empty:
                return
            if kind == "reply":
                callback, reply = rest
                if callback is not None:
                    callback(reply)
            elif kind == "event":
                on_event(rest[0])
            elif kind == "closed":
                self.close()
                on_closed(rest[0])
                return

    def _read(self, sock):
        try:
            with sock.makefile("rb") as stream:
                for raw in stream:
                    try:
                        msg = json.loads(raw)
                    except ValueError:
                        continue
                    if not isinstance(msg, dict):
                        continue
                    if "event" in msg and "id" not in msg:
                        self._queue.put(("event", msg))
                        continue
                    with self._lock:
                        callback, meshes = self._waiting.pop(msg.get("id"), (None, False))
                    if meshes:
                        _decode_meshes(msg)
                    self._queue.put(("reply", callback, msg))
            reason = "SolidCraft closed the connection"
        except (OSError, ValueError) as e:  # ValueError: the stream was closed under the read
            reason = str(e)
        # Only a connection SolidCraft ended is reported: one closed here (a disconnect, or a new
        # connect) must not close the connection that replaced it.
        if self._sock is sock:
            self._queue.put(("closed", reason))


def _decode_meshes(reply):
    """Decode a ``live.meshes`` reply's meshes in place (on the reader thread): each becomes a
    :class:`decode.Mesh`, or an ``(key, error)`` pair."""
    result = reply.get("result")
    if not reply.get("ok") or not isinstance(result, dict):
        return
    out = []
    for m in result.get("meshes") or []:
        try:
            out.append(decode.decode_mesh(m))
        except decode.MeshError as e:
            out.append((m.get("key") if isinstance(m, dict) else None, str(e)))
    result["meshes"] = out
