"""Load the add-on's modules that do not need Blender as the package ``solidcraft_link``."""

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if "solidcraft_link" not in sys.modules:
    package = types.ModuleType("solidcraft_link")
    package.__path__ = [str(ROOT)]
    sys.modules["solidcraft_link"] = package
