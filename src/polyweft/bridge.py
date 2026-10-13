"""Fixed Blender-side bridge. User artifacts are data, never Python scripts."""

import hashlib
import json
import math
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import quote, unquote

import bpy

MAX_VERTICES = 20_000
MAX_FACES = 20_000
MAX_CORNERS = 80_000
ID = "polyweft_id"
VID = "polyweft_vertex_id"
CID = "polyweft_corner_id"


def fail(message):
    raise ValueError(message)


def atom(value):
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if isinstance(value, dict):
        return {str(k): atom(v) for k, v in value.items()}
    if isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            fail("Nonfinite native property")
        return value
    if hasattr(value, "to_list"):
        value = value.to_list()
    if isinstance(value, (list, tuple)) or type(value).__name__ in {
        "Vector",
        "Color",
        "Euler",
        "Quaternion",
        "bpy_prop_array",
    }:
        return [atom(v) for v in value]
    fail("Unhandled native property type: " + type(value).__name__)


def custom(data):
    result = {}
    # Blender datablock iteration is not dictionary-key iteration.
    for key in data.keys():  # noqa: SIM118
        if key.startswith("polyweft_") or key == "_RNA_UI":
            continue
        result[key] = atom(data[key])
    return result


def prepare(obj):
    mesh = obj.data
    if mesh.get("polyweft_schema") not in (None, "polyweft.ids.v1"):
        fail("Unknown prepared identity schema")
    mesh["polyweft_schema"] = "polyweft.ids.v1"
    if not mesh.get(ID):
        mesh[ID] = uuid.uuid4().hex
    for name, domain, count in [
        (VID, "POINT", len(mesh.vertices)),
        (CID, "CORNER", len(mesh.loops)),
    ]:
        attribute = mesh.attributes.get(name)
        if attribute is None:
            attribute = mesh.attributes.new(name, "INT", domain)
            for i, item in enumerate(attribute.data):
                item.value = i + 1
        elif (
            attribute.data_type != "INT"
            or attribute.domain != domain
            or len(attribute.data) != count
        ):
            fail("Invalid existing identity attribute " + name)
    for user in bpy.data.objects:
        if user.type == "MESH" and user.data == mesh and not user.get(ID):
            user[ID] = uuid.uuid4().hex
    mesh["polyweft_primary_object"] = identity(obj, "primary object")
    for material in mesh.materials:
        if material is not None:
            if not material.get(ID):
                material[ID] = uuid.uuid4().hex
            if material.node_tree:
                for node in material.node_tree.nodes:
                    if not node.get(ID):
                        node[ID] = uuid.uuid4().hex


def identity(data, label):
    value = data.get(ID)
    if (
        type(value) is not str
        or len(value) != 32
        or any(c not in "0123456789abcdef" for c in value)
    ):
        fail("Missing or malformed prepared " + label + " identity")
    return value


def path_ref(value, reference, library=None):
    if not value:
        return ""
    return os.path.relpath(bpy.path.abspath(value, library=library), reference).replace(
        os.sep, "/"
    )


def node_material(material, reference):
    if material.library or material.override_library:
        fail("Linked or overridden target materials are unsupported")
    mid = identity(material, "material")
    if not material.use_nodes or material.node_tree is None:
        fail("Target materials must use supported nodes")
    if material.node_tree.animation_data is not None:
        fail("Animated or driven target node trees are unsupported")
    nodes = material.node_tree.nodes
    if len(nodes) > 32:
        fail("Target material exceeds 32 nodes")
    values = {}
    struct = []
    ids = set()
    for node in nodes:
        nid = identity(node, "material node")
        if nid in ids:
            fail("Duplicate node identity")
        ids.add(nid)
        if node.bl_idname not in {
            "ShaderNodeBsdfPrincipled",
            "ShaderNodeOutputMaterial",
            "ShaderNodeTexImage",
        }:
            fail("Unsupported material node " + node.bl_idname)
        if node.parent is not None:
            fail("Parented material nodes are unsupported")
        inputs = []
        for socket in node.inputs:
            description = {"id": socket.identifier, "type": socket.bl_rna.identifier}
            if hasattr(socket, "default_value"):
                value = atom(socket.default_value)
                if node.bl_idname == "ShaderNodeBsdfPrincipled" and socket.name in {
                    "Base Color",
                    "Roughness",
                }:
                    key = (
                        "material:"
                        + mid
                        + ":"
                        + nid
                        + ":"
                        + quote(socket.identifier, safe="")
                    )
                    values[key] = {
                        "label": material.name
                        + " / "
                        + node.name
                        + " / "
                        + socket.name,
                        "value": value,
                    }
                else:
                    description["value"] = value
            inputs.append(description)
        semantic = {}
        cosmetic = {
            "rna_type",
            "name",
            "label",
            "location",
            "width",
            "height",
            "dimensions",
            "select",
            "hide",
            "show_options",
            "show_preview",
            "show_texture",
            "use_custom_color",
            "color",
        }
        for prop in node.bl_rna.properties:
            if prop.identifier in cosmetic or prop.identifier.startswith("bl_"):
                continue
            if prop.type in {"BOOLEAN", "INT", "FLOAT", "STRING", "ENUM"}:
                semantic[prop.identifier] = atom(getattr(node, prop.identifier))
        internal_links = sorted(
            [link.from_socket.identifier, link.to_socket.identifier]
            for link in node.internal_links
        )
        descriptor = {
            "id": nid,
            "type": node.bl_idname,
            "semantic": semantic,
            "internal_links": internal_links,
            "inputs": inputs,
            "outputs": [
                {"id": s.identifier, "type": s.bl_rna.identifier} for s in node.outputs
            ],
            "custom": custom(node),
        }
        if node.bl_idname == "ShaderNodeOutputMaterial":
            descriptor.update(
                target=node.target, is_active_output=node.is_active_output
            )
        if node.bl_idname == "ShaderNodeBsdfPrincipled":
            descriptor.update(
                distribution=node.distribution, subsurface_method=node.subsurface_method
            )
        if node.bl_idname == "ShaderNodeTexImage":
            descriptor.update(
                interpolation=node.interpolation,
                projection=node.projection,
                projection_blend=node.projection_blend,
                extension=node.extension,
            )
            image = node.image
            if image is not None:
                if image.library or image.source != "FILE":
                    fail(
                        "Only local FILE images are admitted; generated, sequence, movie and linked target images are unsupported"
                    )
                if image.is_dirty:
                    fail("Unsaved target image pixel edits are unsupported")
                image_user = {
                    prop.identifier: atom(getattr(node.image_user, prop.identifier))
                    for prop in node.image_user.bl_rna.properties
                    if prop.identifier != "rna_type"
                    and prop.type in {"BOOLEAN", "INT", "FLOAT", "STRING", "ENUM"}
                }
                descriptor["image_user"] = image_user
                packed = (
                    None
                    if image.packed_file is None
                    else hashlib.sha256(image.packed_file.data).hexdigest()
                )
                descriptor["image"] = {
                    "packed_sha256": packed,
                    "view_as_render": image.use_view_as_render,
                    "name": image.name,
                    "source": image.source,
                    "path": path_ref(image.filepath, reference, image.library),
                    "packed": image.packed_file is not None,
                    "colorspace": image.colorspace_settings.name,
                    "alpha_mode": image.alpha_mode,
                }
            else:
                descriptor["image"] = None
        struct.append(descriptor)
    links = []
    for link in material.node_tree.links:
        links.append(
            [
                identity(link.from_node, "node"),
                link.from_socket.identifier,
                identity(link.to_node, "node"),
                link.to_socket.identifier,
            ]
        )
    return (
        mid,
        {
            "nodes": sorted(struct, key=lambda x: x["id"]),
            "links": sorted(links),
            "custom": custom(material),
        },
        values,
    )


def snapshot(obj, reference):
    if obj.type != "MESH":
        fail("Target must be a mesh object")
    mesh = obj.data
    if obj.library or obj.override_library or mesh.library or mesh.override_library:
        fail("Linked or library-overridden targets are unsupported")
    if mesh.shape_keys is not None:
        fail("Shape-key target meshes are unsupported")
    if mesh.animation_data is not None:
        fail("Animated or driven target meshes are unsupported")
    if (
        not 1 <= len(mesh.vertices) <= MAX_VERTICES
        or not 1 <= len(mesh.polygons) <= MAX_FACES
        or len(mesh.loops) > MAX_CORNERS
    ):
        fail(
            "Target exceeds 20,000 vertices/faces or 80,000 corners, or has no geometry"
        )
    mid = identity(mesh, "mesh")
    if mesh.get("polyweft_schema") != "polyweft.ids.v1":
        fail("Run prepare before branching this mesh")
    for other in bpy.data.meshes:
        if other != mesh and other.get(ID) == mid:
            fail("Duplicate mesh identity on another datablock")
    attrs = []
    for name, domain, count in [
        (VID, "POINT", len(mesh.vertices)),
        (CID, "CORNER", len(mesh.loops)),
    ]:
        a = mesh.attributes.get(name)
        if (
            a is None
            or a.data_type != "INT"
            or a.domain != domain
            or len(a.data) != count
        ):
            fail("Missing or malformed " + name)
        values = [x.value for x in a.data]
        if any(x <= 0 for x in values) or len(values) != len(set(values)):
            fail("Missing or duplicate " + name + " identity")
        attrs.append(values)
    vids, cids = attrs
    users = []
    user_ids = set()
    observed_users = []
    for user in bpy.data.objects:
        if user.type == "MESH" and user.data == mesh:
            uid = identity(user, "shared object")
            if uid in user_ids:
                fail("Duplicate shared object identity")
            user_ids.add(uid)
            if (
                user.library
                or user.override_library
                or len(user.modifiers)
                or len(user.vertex_groups)
            ):
                fail(
                    "Target users with libraries, modifiers or vertex groups are unsupported"
                )
            if user.material_slots and any(
                s.link != "DATA" for s in user.material_slots
            ):
                fail("Object-linked target material slots are unsupported")
            users.append(uid)
            observed_users.append(
                {
                    "id": uid,
                    "name": user.name,
                    "location": list(user.location),
                    "rotation_mode": user.rotation_mode,
                    "rotation": list(user.rotation_euler),
                    "scale": list(user.scale),
                    "hide_render": user.hide_render,
                    "custom": custom(user),
                    "animation_present": user.animation_data is not None,
                }
            )
    if len(mesh.materials) > 8:
        fail("Target exceeds eight material slots")
    material_guards = {}
    material_values = {}
    slots = []
    material_ptr = {}
    for material in mesh.materials:
        if material is None:
            slots.append(None)
            continue
        material_id, guard, values = node_material(material, reference)
        if (
            material_id in material_ptr
            and material_ptr[material_id] != material.as_pointer()
        ):
            fail("Duplicate material identity")
        material_ptr[material_id] = material.as_pointer()
        slots.append(material_id)
        material_guards[material_id] = guard
        material_values.update(values)
    if len(mesh.uv_layers) > 8 or len(mesh.uv_layers) * len(mesh.loops) > MAX_CORNERS:
        fail("UV layers exceed eight layers or 80,000 total corners")
    uvs = {
        layer.name: [
            {
                "id": cids[i],
                "vertex": vids[mesh.loops[i].vertex_index],
                "uv": list(item.uv),
            }
            for i, item in enumerate(layer.data)
        ]
        for layer in mesh.uv_layers
    }
    if len(uvs) != len(mesh.uv_layers):
        fail("Duplicate UV layer names")
    native_attributes = {}
    skip = {VID, CID, "position", ".corner_vert", ".edge_verts"} | set(uvs)
    for attribute in mesh.attributes:
        if attribute.name in skip or attribute.name.startswith(".select"):
            continue
        rows = []
        for item in attribute.data:
            field = next(
                (k for k in ["value", "vector", "color"] if hasattr(item, k)), None
            )
            if field is None:
                fail("Unhandled target mesh attribute " + attribute.name)
            rows.append(atom(getattr(item, field)))
        native_attributes[attribute.name] = {
            "type": attribute.data_type,
            "domain": attribute.domain,
            "values": rows,
        }
    faces = [[vids[v] for v in polygon.vertices] for polygon in mesh.polygons]
    guards = {
        "mesh_id": mid,
        "primary_object": mesh.get("polyweft_primary_object"),
        "vertex_order": vids,
        "corner_order": cids,
        "faces": faces,
        "edges": [[vids[v] for v in e.vertices] for e in mesh.edges],
        "shared_users": sorted(users),
        "uv_names": list(uvs),
        "uv_render_clone": {
            layer.name: [layer.active_render, layer.active_clone]
            for layer in mesh.uv_layers
        },
        "uv_corner_vertices": {
            name: [c["vertex"] for c in corners] for name, corners in uvs.items()
        },
        "material_slots": slots,
        "materials": material_guards,
        "mesh_custom": custom(mesh),
        "unsupported_attributes": native_attributes,
        "polygon_flags": [[p.material_index, p.use_smooth] for p in mesh.polygons],
        "edge_flags": [[e.use_seam, e.use_edge_sharp] for e in mesh.edges],
        "shape_keys": False,
        "linked": False,
    }
    observed = {
        "active_uv_editor_index": mesh.uv_layers.active_index,
        "objects": sorted(observed_users, key=lambda x: x["id"]),
        "scene": {
            "frame_start": bpy.context.scene.frame_start,
            "frame_end": bpy.context.scene.frame_end,
            "render_engine": bpy.context.scene.render.engine,
            "resolution_x": bpy.context.scene.render.resolution_x,
            "resolution_y": bpy.context.scene.render.resolution_y,
            "custom": custom(bpy.context.scene),
        },
        "material_names": {
            identity(m, "material"): m.name for m in mesh.materials if m is not None
        },
        "material_node_names": {
            identity(m, "material") + ":" + identity(n, "node"): n.name
            for m in mesh.materials
            if m is not None
            for n in m.node_tree.nodes
        },
    }
    result = {
        "name": obj.name,
        "vertices": [{"id": vids[v.index], "co": list(v.co)} for v in mesh.vertices],
        "faces": faces,
        "uv_layers": uvs,
        "material_values": material_values,
        "guards": guards,
        "observed": observed,
    }
    json.dumps(result, allow_nan=False)
    return result


def find_target(mesh_id):
    matches = [m for m in bpy.data.meshes if m.get(ID) == mesh_id]
    if len(matches) != 1:
        fail("Prepared target mesh identity missing or duplicated")
    users = [o for o in bpy.data.objects if o.type == "MESH" and o.data == matches[0]]
    if not users:
        fail("Prepared target mesh has no object user")
    primary = [
        o for o in users if o.get(ID) == matches[0].get("polyweft_primary_object")
    ]
    if len(primary) != 1:
        fail("Prepared primary object identity missing or duplicated")
    return primary[0]


def apply_values(obj, values):
    mesh = obj.data
    vertices = {
        str(x.value): mesh.vertices[i] for i, x in enumerate(mesh.attributes[VID].data)
    }
    corner_indexes = {str(x.value): i for i, x in enumerate(mesh.attributes[CID].data)}
    materials = {identity(m, "material"): m for m in mesh.materials if m is not None}
    for key, value in values.items():
        parts = key.split(":")
        if parts[0] == "vertex":
            vertices[parts[1]].co = value
        elif parts[0] == "uv":
            mesh.uv_layers[unquote(parts[1])].data[corner_indexes[parts[2]]].uv = value
        elif parts[0] == "material":
            material = materials[parts[1]]
            node = next(
                n for n in material.node_tree.nodes if identity(n, "node") == parts[2]
            )
            socket = next(s for s in node.inputs if s.identifier == unquote(parts[3]))
            socket.default_value = value
        else:
            fail("Unknown admitted payload key")
    mesh.update()


def rebase_external_paths(output):
    # Preserve both the physical target and the user's relative/absolute intent.
    # Resolve everything before changing library paths; save without a second remap.
    references = []
    for collection in [
        bpy.data.images,
        bpy.data.movieclips,
        bpy.data.sounds,
        bpy.data.fonts,
        bpy.data.cache_files,
        bpy.data.libraries,
    ]:
        for item in collection:
            if (
                hasattr(item, "filepath")
                and item.filepath
                and not item.filepath.startswith("<")
            ):
                original = item.filepath
                absolute = bpy.path.abspath(
                    original, library=getattr(item, "library", None)
                )
                references.append((item, absolute, original.startswith("//")))
    parent = str(Path(output).parent)
    for item, absolute, relative in references:
        item.filepath = (
            "//" + os.path.relpath(absolute, parent).replace(os.sep, "/")
            if relative
            else absolute
        )


def run(request):
    bpy.context.preferences.filepaths.save_version = 0
    source = request["source"]
    bpy.ops.wm.open_mainfile(filepath=source, use_scripts=False, load_ui=False)
    mode = request["mode"]
    reference = request.get("reference_directory", str(Path(source).parent))
    if mode == "prepare":
        obj = bpy.data.objects.get(request["object"])
        if obj is None or obj.type != "MESH":
            fail("Named mesh object not found")
        prepare(obj)
        captured = snapshot(obj, reference)
        rebase_external_paths(request["output"])
        bpy.ops.wm.save_as_mainfile(
            filepath=request["output"], check_existing=False, relative_remap=False
        )
        return captured
    if mode == "capture-base":
        targets = [
            m for m in bpy.data.meshes if m.get("polyweft_schema") == "polyweft.ids.v1"
        ]
        if len(targets) != 1:
            fail(
                "Base must contain exactly one prepared target mesh; unprepared or multiple targets are ambiguous"
            )
        obj = find_target(identity(targets[0], "mesh"))
    else:
        obj = find_target(request["mesh_id"])
    captured = snapshot(obj, reference)
    if mode in {"capture", "capture-base"}:
        return captured
    if mode == "apply":
        apply_values(obj, request["values"])
        captured = snapshot(obj, reference)
        rebase_external_paths(request["output"])
        bpy.ops.wm.save_as_mainfile(
            filepath=request["output"], check_existing=False, relative_remap=False
        )
        return captured
    fail("Unsupported bridge operation")


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1 :]
    output = Path(args[1])
    try:
        result = {"ok": True, "snapshot": run(json.loads(Path(args[0]).read_text()))}
    except Exception as error:  # noqa: BLE001 - encode native errors at process boundary
        result = {"ok": False, "error": str(error)}
    output.write_text(json.dumps(result, allow_nan=False) + "\n")
    if not result["ok"]:
        raise RuntimeError(result["error"])
