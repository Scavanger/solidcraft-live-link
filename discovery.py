"""Finding the running SolidCraft: its control-channel port and this launch's token.

SolidCraft writes the port of its most recently started window to ``control/current.port`` and a
token per port to ``control/<port>.token``, in a folder only the user can read (see SolidCraft's
``docs/control-protocol.md``). No bpy here, so it can be tested on its own.
"""

import os
import sys
from pathlib import Path

DEFAULT_PORT = 27878


def control_dirs(env=None, home=None, platform=None):
    """The folders SolidCraft may keep its control files in, most likely first."""
    env = os.environ if env is None else env
    home = Path.home() if home is None else Path(home)
    platform = sys.platform if platform is None else platform
    dirs = []
    if env.get("SOLIDCRAFT_CONTROL_DIR"):
        dirs.append(Path(env["SOLIDCRAFT_CONTROL_DIR"]))
    if platform.startswith("win"):
        local = Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local")
        dirs.append(local / "SolidCraft" / "control")
        # An app installed from an MSIX package keeps its AppData in the package's own folder.
        packages = local / "Packages"
        try:
            for package in sorted(packages.iterdir()):
                candidate = package / "LocalCache" / "Local" / "SolidCraft" / "control"
                if candidate.is_dir():
                    dirs.append(candidate)
        except OSError:
            pass
    elif platform == "darwin":
        dirs.append(home / "Library" / "Application Support" / "SolidCraft" / "control")
    else:
        data = Path(env["XDG_DATA_HOME"]) if env.get("XDG_DATA_HOME") else home / ".local" / "share"
        dirs.append(data / "solidcraft" / "control")
    return dirs


def _read(path):
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None


def find(port=None, env=None, home=None, platform=None):
    """``(port, token)`` of the running SolidCraft, or ``(port, None)`` when no token is found.

    With ``port`` given, only its token is looked for; otherwise the newest discovery file names
    the port.
    """
    dirs = control_dirs(env, home, platform)
    if port is None:
        newest = None
        for d in dirs:
            path = d / "current.port"
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            text = _read(path)
            if text and text.isdigit() and 0 < int(text) < 65536 and (newest is None or mtime > newest[0]):
                newest = (mtime, int(text))
        port = newest[1] if newest else DEFAULT_PORT
    for d in dirs:
        token = _read(d / f"{port}.token")
        if token and all(c in "0123456789abcdefABCDEF" for c in token) and len(token) >= 32:
            return port, token
    return port, None
