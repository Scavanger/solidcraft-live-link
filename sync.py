"""Putting a ``live.meshes`` result into the Blender scene.

- Every SolidCraft body is an object (custom property ``sc_key``), in a collection per component
  under one "SolidCraft" collection.
- Meshes are shared by key (custom property ``sc_mesh_key``): placements of one part are linked
  duplicates, and a mesh whose key comes again is kept as it is (with any UVs made on it).
- Each B-rep edge segment is marked as a UV seam; sharp ones get the ``sharp_edge`` attribute,
  and corners take SolidCraft's surface normals as custom normals. Each polygon's B-rep face is
  the integer face attribute ``sc_face``; the faces' persistent names are the mesh's
  ``sc_face_names`` property.
"""

from array import array

import bpy
from mathutils import Matrix

from . import decode

ROOT = "SolidCraft"
OBJECT_KEY = "sc_key"
MESH_KEY = "sc_mesh_key"
DOCUMENT = "sc_document"


def held_mesh_keys():
    return {m[MESH_KEY] for m in bpy.data.meshes if MESH_KEY in m and m.users > 0}


def _root_collection(scene):
    root = bpy.data.collections.get(ROOT)
    if root is None:
        root = bpy.data.collections.new(ROOT)
    if root.name not in scene.collection.children:
        scene.collection.children.link(root)
    return root


def _component_collection(root, components, component_id):
    """The collection for a component, nested as the components are."""
    if not component_id:
        return root
    chain = []
    seen = set()
    at = component_id
    while at and at in components and at not in seen:
        seen.add(at)
        chain.append(at)
        at = components[at]["parent"]
    parent = root
    for cid in reversed(chain):
        name = f"{components[cid]['name']} [{cid}]"
        coll = parent.children.get(name)
        if coll is None:
            coll = bpy.data.collections.get(name) or bpy.data.collections.new(name)
            if coll.name not in parent.children:
                parent.children.link(coll)
        parent = coll
    return parent


def _material(color, opacity):
    name = "SC #{:02x}{:02x}{:02x}{}".format(*color, "" if opacity >= 1.0 else f" {int(round(opacity * 100))}%")
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    rgba = (*(decode.srgb_to_linear(c) for c in color), 1.0)
    mat.diffuse_color = (*rgba[:3], opacity)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.node_tree else None
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = rgba
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = opacity
    if opacity < 1.0 and hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"
    return mat


def build_mesh(m, scale, name):
    """A new Blender mesh from a decoded mesh, in metres when ``scale`` is 0.001."""
    me = bpy.data.meshes.new(name)
    positions = array("f", m.positions) if scale == 1.0 else array("f", (v * scale for v in m.positions))
    me.vertices.add(m.vertex_count)
    me.vertices.foreach_set("co", positions)
    me.loops.add(len(m.loops))
    me.loops.foreach_set("vertex_index", m.loops)
    me.polygons.add(len(m.poly_sizes))
    me.polygons.foreach_set("loop_start", m.loop_starts)
    me.polygons.foreach_set("loop_total", m.poly_sizes)
    me.update(calc_edges=True)
    me.validate(verbose=False, clean_customdata=False)

    face = me.attributes.new("sc_face", "INT", "FACE")
    face.data.foreach_set("value", m.poly_face)
    me[MESH_KEY] = m.key
    me["sc_face_names"] = list(m.face_names)

    # Seams and sharp edges on the B-rep edge segments.
    ends = array("i", bytes(8 * len(me.edges)))
    me.edges.foreach_get("vertices", ends)
    index = {}
    for i in range(len(me.edges)):
        a, b = ends[2 * i], ends[2 * i + 1]
        index[(a, b) if a < b else (b, a)] = i
    seams = [False] * len(me.edges)
    sharp = [False] * len(me.edges)
    for k, flag in enumerate(m.edge_flags):
        i = index.get((m.edges[2 * k], m.edges[2 * k + 1]))
        if i is None:
            continue
        seams[i] = True
        if flag & decode.SHARP:
            sharp[i] = True
    try:
        me.edges.foreach_set("use_seam", seams)
    except (AttributeError, TypeError):
        attr = me.attributes.get(".uv_seam") or me.attributes.new(".uv_seam", "BOOLEAN", "EDGE")
        attr.data.foreach_set("value", seams)
    attr = me.attributes.get("sharp_edge") or me.attributes.new("sharp_edge", "BOOLEAN", "EDGE")
    attr.data.foreach_set("value", sharp)

    if m.loop_normals is not None:
        me.shade_smooth()
        n = m.loop_normals
        me.normals_split_custom_set([(n[3 * i], n[3 * i + 1], n[3 * i + 2]) for i in range(len(m.loops))])
    return me


def _face_looks(me, faces, poly_face):
    """Per-face colours as further material slots on the mesh (slot 0 is the body's)."""
    look = {}
    for f in faces:
        try:
            face, mat = int(f["face"]), _material(tuple(f["color"]), float(f.get("opacity", 1.0)))
        except (KeyError, TypeError, ValueError):
            continue
        names = [m.name if m else "" for m in me.materials]
        if mat.name not in names[1:]:
            me.materials.append(mat)
            names.append(mat.name)
        look[face] = names.index(mat.name, 1)
    if look:
        me.polygons.foreach_set("material_index", [look.get(face, 0) for face in poly_face])


def apply(result, scale=0.001, context=None):
    """Bring the scene in step with one ``live.meshes`` result."""
    context = context or bpy.context
    scene = context.scene
    document = result.get("document_id") or ""
    root = _root_collection(scene)
    components = {c["id"]: c for c in result.get("components") or [] if isinstance(c, dict) and "id" in c}

    # New meshes, by key; the mesh decoded with them is kept for face looks.
    decoded = {}
    errors = {}
    for m in result.get("meshes") or []:
        if isinstance(m, tuple):
            errors[m[0]] = m[1]
            continue
        decoded[m.key] = m
    meshes = {me[MESH_KEY]: me for me in bpy.data.meshes if MESH_KEY in me}
    for key, m in decoded.items():
        old = meshes.get(key)
        meshes[key] = build_mesh(m, scale, f"SC {key[:8]}")
        if old is not None:
            for obj in [o for o in bpy.data.objects if o.data == old]:
                obj.data = meshes[key]
            if old.users == 0:
                bpy.data.meshes.remove(old)

    objects = {o[OBJECT_KEY]: o for o in bpy.data.objects if OBJECT_KEY in o}
    wanted = set()
    for item in result.get("objects") or []:
        key = item.get("key")
        mesh_key = item.get("mesh")
        if not isinstance(key, str):
            continue
        wanted.add(key)
        if mesh_key not in meshes:
            # Still to come (pending) or not meshed (an error): what is there stays.
            continue
        me = meshes[mesh_key]
        obj = objects.get(key)
        if obj is None:
            obj = bpy.data.objects.new(key, me)
            obj[OBJECT_KEY] = key
        elif obj.data != me:
            obj.data = me
        obj[DOCUMENT] = document
        obj.matrix_world = Matrix(decode.column_major_rows(item.get("matrix"), scale))
        coll = _component_collection(root, components, item.get("component") or 0)
        if coll.name not in [c.name for c in obj.users_collection]:
            for c in list(obj.users_collection):
                c.objects.unlink(obj)
            coll.objects.link(obj)
        if obj.name in context.view_layer.objects:
            obj.hide_set(not item.get("visible", True))
        # The body's look on the object, so placements may differ; face looks on the mesh.
        mat = _material(tuple(item.get("color") or (176, 186, 198)), float(item.get("opacity", 1.0)))
        if not me.materials:
            me.materials.append(mat)
        slot = obj.material_slots[0]
        slot.link = "OBJECT"
        slot.material = mat
        if mesh_key in decoded:
            _face_looks(me, item.get("faces") or [], decoded[mesh_key].poly_face)

    # Bodies that are gone.
    for key, obj in objects.items():
        if key not in wanted:
            bpy.data.objects.remove(obj, do_unlink=True)
    for me in [me for me in bpy.data.meshes if MESH_KEY in me and me.users == 0]:
        bpy.data.meshes.remove(me)
    return errors
