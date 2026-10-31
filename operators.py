"""Operators, and the one link the add-on keeps while Blender runs."""

import bpy

from . import properties, sync
from .link import Link

REFACET = "sc_refacet"
PUMP_SECONDS = 0.05

_link = None


def _settings(context=None):
    return (context or bpy.context).scene.solidcraft_link


def _params():
    settings = _settings()
    p = properties.tessellation(settings)
    overrides = []
    for obj in bpy.data.objects:
        if sync.OBJECT_KEY in obj and REFACET in obj:
            o = dict(obj[REFACET].to_dict()) if hasattr(obj[REFACET], "to_dict") else {}
            o["body"] = obj[sync.OBJECT_KEY]
            overrides.append(o)
    if overrides:
        p["overrides"] = overrides
    return p


def _apply(result):
    sync.apply(result, scale=_settings().scale)


def link():
    global _link
    if _link is None:
        _link = Link(apply=_apply, have=sync.held_mesh_keys, params=_params)
    return _link


def _pump():
    if _link is None:
        return None
    try:
        _link.pump()
    except Exception as e:  # noqa: BLE001 - keep the timer alive; say what went wrong
        _link.status = f"Error: {e}"
    _redraw()
    return PUMP_SECONDS if _link.connected or _link.status.startswith("Connecting") else None


def _redraw():
    wm = getattr(bpy.context, "window_manager", None)
    for window in getattr(wm, "windows", []):
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def set_live(live):
    if _link is not None:
        _link.set_live(live)


def stop():
    global _link
    if _link is not None:
        _link.disconnect()
        _link = None
    if bpy.app.timers.is_registered(_pump):
        bpy.app.timers.unregister(_pump)


class SOLIDCRAFT_OT_connect(bpy.types.Operator):
    bl_idname = "solidcraft.connect"
    bl_label = "Connect"
    bl_description = "Connect to SolidCraft running on this computer and follow the open design"

    def execute(self, context):
        s = _settings(context)
        lk = link()
        lk.live = s.live
        try:
            lk.connect(host=s.host, port=s.port or None, token=s.token or None)
        except (OSError, ConnectionError) as e:
            self.report({"ERROR"}, f"SolidCraft: {e}")
            return {"CANCELLED"}
        if not bpy.app.timers.is_registered(_pump):
            bpy.app.timers.register(_pump, first_interval=PUMP_SECONDS, persistent=True)
        return {"FINISHED"}


class SOLIDCRAFT_OT_disconnect(bpy.types.Operator):
    bl_idname = "solidcraft.disconnect"
    bl_label = "Disconnect"
    bl_description = "Stop following SolidCraft (the objects stay)"

    def execute(self, context):
        if _link is not None:
            _link.disconnect()
        return {"FINISHED"}


class SOLIDCRAFT_OT_refresh(bpy.types.Operator):
    bl_idname = "solidcraft.refresh"
    bl_label = "Refresh"
    bl_description = "Fetch the design now"

    @classmethod
    def poll(cls, context):
        return _link is not None and _link.connected

    def execute(self, context):
        link().fetch()
        return {"FINISHED"}


def _selected_bodies(context):
    return [o for o in context.selected_objects if sync.OBJECT_KEY in o]


class SOLIDCRAFT_OT_refacet(bpy.types.Operator):
    bl_idname = "solidcraft.refacet"
    bl_label = "Refacet Selected"
    bl_description = "Mesh the selected bodies with the tessellation settings above; the others keep theirs"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(_selected_bodies(context))

    def execute(self, context):
        p = properties.tessellation(_settings(context))
        p.pop("normals", None)
        for obj in _selected_bodies(context):
            obj[REFACET] = p
        if _link is not None and _link.connected:
            _link.fetch()
        return {"FINISHED"}


class SOLIDCRAFT_OT_clear_refacet(bpy.types.Operator):
    bl_idname = "solidcraft.clear_refacet"
    bl_label = "Use Scene Settings"
    bl_description = "The selected bodies follow the scene's tessellation settings again"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(REFACET in o for o in _selected_bodies(context))

    def execute(self, context):
        for obj in _selected_bodies(context):
            if REFACET in obj:
                del obj[REFACET]
        if _link is not None and _link.connected:
            _link.fetch()
        return {"FINISHED"}


class SOLIDCRAFT_OT_unwrap(bpy.types.Operator):
    bl_idname = "solidcraft.unwrap"
    bl_label = "Unwrap by Faces"
    bl_description = "Unwrap the selected bodies along their B-rep face boundaries (the seams SolidCraft marked)"
    bl_options = {"REGISTER", "UNDO"}

    margin: bpy.props.FloatProperty(name="Margin", default=0.005, min=0.0, max=0.2)

    @classmethod
    def poll(cls, context):
        return bool(_selected_bodies(context))

    def execute(self, context):
        bodies = _selected_bodies(context)
        view_layer = context.view_layer
        active = view_layer.objects.active
        view_layer.objects.active = bodies[0]
        mode = context.mode
        if mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=self.margin)
        bpy.ops.object.mode_set(mode="OBJECT")
        view_layer.objects.active = active
        return {"FINISHED"}


class SOLIDCRAFT_OT_select_face_group(bpy.types.Operator):
    bl_idname = "solidcraft.select_face_group"
    bl_label = "Select B-rep Face"
    bl_description = "In Edit Mode, grow the selection to the whole B-rep faces the selected polygons belong to"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.edit_object
        return obj is not None and obj.type == "MESH" and "sc_face" in obj.data.attributes

    def execute(self, context):
        import bmesh

        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        layer = bm.faces.layers.int.get("sc_face")
        if layer is None:
            return {"CANCELLED"}
        wanted = {f[layer] for f in bm.faces if f.select}
        for f in bm.faces:
            if f[layer] in wanted:
                f.select = True
        bmesh.update_edit_mesh(obj.data)
        return {"FINISHED"}
