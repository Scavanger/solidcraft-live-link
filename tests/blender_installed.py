"""Run inside Blender after installing the release zip: ``blender --background --python tests/blender_installed.py``.

Checks that the installed extension is enabled and registered its operators and settings, as
Blender loads it for a user (not from this folder). Exits with status 1 on failure.
"""

import sys

import bpy

try:
    for op in ("connect", "disconnect", "refresh", "refacet", "clear_refacet", "unwrap", "select_face_group"):
        getattr(bpy.ops.solidcraft, op).get_rna_type()
    settings = bpy.context.scene.solidcraft_link
    assert settings.quality == "normal" and settings.live, "default settings"
    assert any(m.endswith(".solidcraft_link") for m in bpy.context.preferences.addons.keys()), "the extension is enabled"
except Exception as e:  # noqa: BLE001 - any failure fails the check
    print(f"installed extension: {e!r}")
    sys.exit(1)
print("installed extension: ok")
