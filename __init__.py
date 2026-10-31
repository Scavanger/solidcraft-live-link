"""SolidCraft Live Link: follow a SolidCraft design live in Blender.

The design comes over SolidCraft's control channel on this computer (``control.subscribe`` and the
``live.meshes`` command) as welded, quad-dominant meshes with B-rep faces, seams, sharp edges and
custom normals. Blender only reads: the design is never changed from here.
"""

try:
    import bpy
except ImportError:  # Imported outside Blender (the tests): only the modules without bpy are used.
    bpy = None

if bpy is not None:
    from . import operators, properties, ui

    _classes = (
        properties.SolidCraftLinkSettings,
        operators.SOLIDCRAFT_OT_connect,
        operators.SOLIDCRAFT_OT_disconnect,
        operators.SOLIDCRAFT_OT_refresh,
        operators.SOLIDCRAFT_OT_refacet,
        operators.SOLIDCRAFT_OT_clear_refacet,
        operators.SOLIDCRAFT_OT_unwrap,
        operators.SOLIDCRAFT_OT_select_face_group,
        ui.SOLIDCRAFT_PT_link,
        ui.SOLIDCRAFT_PT_tessellation,
        ui.SOLIDCRAFT_PT_tools,
    )

    def register():
        for cls in _classes:
            bpy.utils.register_class(cls)
        bpy.types.Scene.solidcraft_link = bpy.props.PointerProperty(type=properties.SolidCraftLinkSettings)

    def unregister():
        operators.stop()
        del bpy.types.Scene.solidcraft_link
        for cls in reversed(_classes):
            bpy.utils.unregister_class(cls)
