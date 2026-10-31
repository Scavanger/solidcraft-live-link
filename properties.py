"""The add-on's settings, kept with the scene."""

import bpy

QUALITIES = [
    ("coarse", "Coarse", "SolidCraft's coarse display quality"),
    ("normal", "Normal", "SolidCraft's normal display quality"),
    ("fine", "Fine", "SolidCraft's fine display quality"),
    ("ultra", "Ultra", "SolidCraft's ultra display quality"),
]
TOPOLOGIES = [
    ("ngons", "N-gons and quads", "One polygon per flat face, quads on curved faces"),
    ("quads", "Quads", "Quads where triangles make good ones, no n-gons"),
    ("triangles", "Triangles", "Triangles only"),
]


def _live_changed(self, context):
    from . import operators

    operators.set_live(self.live)


class SolidCraftLinkSettings(bpy.types.PropertyGroup):
    host: bpy.props.StringProperty(name="Host", default="127.0.0.1", description="Where SolidCraft runs (this computer)")
    port: bpy.props.IntProperty(name="Port", default=0, min=0, max=65535, description="0: find the running SolidCraft by itself")
    token: bpy.props.StringProperty(
        name="Token",
        default="",
        subtype="PASSWORD",
        description="Empty: read it from SolidCraft's token file. Needed only when Blender cannot see that file (a sandboxed install)",
    )
    live: bpy.props.BoolProperty(name="Live", default=True, update=_live_changed, description="Fetch the design whenever it changes")
    scale: bpy.props.FloatProperty(
        name="Scale",
        default=0.001,
        min=1e-6,
        max=1000.0,
        precision=4,
        description="Blender units per millimetre (0.001: metres)",
    )
    quality: bpy.props.EnumProperty(name="Quality", items=QUALITIES, default="normal")
    use_chord: bpy.props.BoolProperty(name="Own Tolerance", default=False, description="Set the chord and angle instead of a quality")
    chord_relative: bpy.props.FloatProperty(
        name="Chord",
        default=0.001,
        min=1e-6,
        max=0.1,
        precision=6,
        description="Most a facet may stand off the surface, as a share of the body's size",
    )
    angle: bpy.props.FloatProperty(
        name="Angle",
        default=0.349066,
        min=0.0174533,
        max=1.5708,
        subtype="ANGLE",
        description="Most one facet of a curved face may turn",
    )
    topology: bpy.props.EnumProperty(name="Topology", items=TOPOLOGIES, default="ngons")
    normals: bpy.props.BoolProperty(name="Surface Normals", default=True, description="Shade with SolidCraft's surface normals")


def tessellation(settings):
    """The request's tessellation parameters from the settings."""
    p = {"topology": settings.topology, "normals": settings.normals}
    if settings.use_chord:
        p["chord_relative"] = settings.chord_relative
        p["angle_deg"] = round(settings.angle * 57.29577951308232, 6)
    else:
        p["quality"] = settings.quality
    return p
