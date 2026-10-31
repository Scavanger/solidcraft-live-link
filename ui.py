"""The SolidCraft tab in the 3D viewport's sidebar."""

import bpy

from . import operators, sync


class _Panel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SolidCraft"


class SOLIDCRAFT_PT_link(_Panel, bpy.types.Panel):
    bl_idname = "SOLIDCRAFT_PT_link"
    bl_label = "Live Link"

    def draw(self, context):
        s = context.scene.solidcraft_link
        lk = operators._link
        col = self.layout.column()
        if lk is not None and lk.connected:
            row = col.row(align=True)
            row.operator("solidcraft.disconnect", icon="UNLINKED")
            row.operator("solidcraft.refresh", icon="FILE_REFRESH")
        else:
            col.operator("solidcraft.connect", icon="LINKED")
        col.prop(s, "live")
        col.label(text=lk.status if lk is not None else "Not connected")
        col.prop(s, "scale")
        box = col.box()
        box.label(text="Connection")
        box.prop(s, "host")
        box.prop(s, "port")
        box.prop(s, "token")


class SOLIDCRAFT_PT_tessellation(_Panel, bpy.types.Panel):
    bl_idname = "SOLIDCRAFT_PT_tessellation"
    bl_label = "Tessellation"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.solidcraft_link
        col = self.layout.column()
        col.prop(s, "topology")
        col.prop(s, "use_chord")
        if s.use_chord:
            col.prop(s, "chord_relative")
            col.prop(s, "angle")
        else:
            col.prop(s, "quality")
        col.prop(s, "normals")
        row = col.row(align=True)
        row.operator("solidcraft.refacet")
        row.operator("solidcraft.clear_refacet", text="", icon="X")
        obj = context.active_object
        if obj is not None and sync.OBJECT_KEY in obj:
            refacet = obj.get(operators.REFACET)
            text = ", ".join(f"{k} {v}" for k, v in refacet.to_dict().items()) if refacet is not None else "scene settings"
            col.label(text=f"{obj[sync.OBJECT_KEY]}: {text}")


class SOLIDCRAFT_PT_tools(_Panel, bpy.types.Panel):
    bl_idname = "SOLIDCRAFT_PT_tools"
    bl_label = "Tools"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        col = self.layout.column()
        col.operator("solidcraft.unwrap", icon="UV")
        col.operator("solidcraft.select_face_group", icon="FACESEL")
        obj = context.active_object
        if obj is not None and obj.type == "MESH" and sync.MESH_KEY in obj.data:
            st = obj.data
            col.label(text=f"{len(st.polygons)} polygons, {len(st.vertices)} vertices")
