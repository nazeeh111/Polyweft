"""Original Tide sculpture, branch files and verified source-bound review example."""

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def native_stage(stage, folder, blender):
    command = [
        str(blender),
        "--background",
        "--factory-startup",
        "--disable-autoexec",
        "--offline-mode",
        "--python-exit-code",
        "1",
        "--python",
        str(Path(__file__).resolve()),
        "--",
        "--stage",
        stage,
        "--folder",
        str(folder),
    ]
    result = subprocess.run(
        command,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=90,
    )
    if result.returncode:
        raise RuntimeError(result.stdout[-6000:].decode("utf-8", "replace"))


def inside_blender(stage, folder):
    import bpy
    from mathutils import Vector

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    def save(name):
        path = folder / name
        if path.exists():
            raise FileExistsError(str(path))
        bpy.ops.wm.save_as_mainfile(
            filepath=str(path), check_existing=False, relative_remap=True
        )

    if stage == "raw":
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        n, m = 32, 8
        coords = []
        for i in range(n):
            u = 2 * math.pi * i / n
            for j in range(m):
                v = (j / (m - 1) - 0.5) * 0.56
                radius = 1.12 + v * math.cos(1.5 * u)
                coords.append(
                    (
                        radius * math.cos(u),
                        radius * math.sin(u),
                        0.32 * math.sin(2 * u) + v * math.sin(1.5 * u),
                    )
                )
        faces = [
            (i * m + j, ((i + 1) % n) * m + j, ((i + 1) % n) * m + j + 1, i * m + j + 1)
            for i in range(n)
            for j in range(m - 1)
        ]
        mesh = bpy.data.meshes.new("TideRibbon")
        mesh.from_pydata(coords, [], faces)
        mesh.update()
        for face in mesh.polygons:
            face.use_smooth = True
        layer = mesh.uv_layers.new(name="Surface UV")
        for face in mesh.polygons:
            i, j = divmod(face.index, m - 1)
            points = [
                (i / n, j / (m - 1)),
                ((i + 1) / n, j / (m - 1)),
                ((i + 1) / n, (j + 1) / (m - 1)),
                (i / n, (j + 1) / (m - 1)),
            ]
            for corner, value in zip(face.loop_indices, points):
                layer.data[corner].uv = value
        obj = bpy.data.objects.new("Tide", mesh)
        bpy.context.collection.objects.link(obj)
        obj["artist_note"] = "Original sculptural ribbon. Preserve this note."
        alias = bpy.data.objects.new("Tide study", mesh)
        bpy.context.collection.objects.link(alias)
        alias.location = (3.2, 0, 0)
        alias.hide_render = True
        material = bpy.data.materials.new("Cobalt porcelain")
        material.use_nodes = True
        principled = material.node_tree.nodes.get("Principled BSDF")
        principled.inputs["Base Color"].default_value = (0.10, 0.26, 0.42, 1)
        principled.inputs["Roughness"].default_value = 0.45
        material["studio_note"] = "Preserve unrelated material metadata"
        mesh.materials.append(material)
        texture_dir = folder / "textures"
        texture_dir.mkdir(exist_ok=True)
        image = bpy.data.images.new("Paper reference", width=4, height=4)
        image.pixels = [
            v
            for i in range(16)
            for v in ((0.9, 0.85, 0.72, 1) if i % 2 else (0.82, 0.80, 0.70, 1))
        ]
        image.filepath_raw = str(texture_dir / "paper.png")
        image.file_format = "PNG"
        image.save()
        bpy.data.images.remove(image)
        image = bpy.data.images.load(str(texture_dir / "paper.png"))
        image.filepath = "//textures/paper.png"
        node = material.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        node.label = "Relative-path reference, intentionally not connected"
        node.location = (-400, -200)
        mesh["source_note"] = "Shared mesh with a seam-aware UV map"
        camera_data = bpy.data.cameras.new("Camera")
        camera = bpy.data.objects.new("Camera", camera_data)
        bpy.context.collection.objects.link(camera)
        camera.location = (3.4, -4.1, 3.2)
        camera.rotation_euler = (
            (Vector((0, 0, 0)) - camera.location).to_track_quat("-Z", "Y").to_euler()
        )
        camera_data.type = "ORTHO"
        camera_data.ortho_scale = 3.2
        bpy.context.scene.camera = camera
        for name, position, power, scale in [
            ("Key", (0, -3, 5), 900, 4),
            ("Fill", (3, 2, 4), 600, 3),
        ]:
            data = bpy.data.lights.new(name, "AREA")
            data.energy = power
            data.shape = "DISK"
            data.size = scale
            light = bpy.data.objects.new(name, data)
            bpy.context.collection.objects.link(light)
            light.location = position
            light.rotation_euler = (
                (Vector((0, 0, 0)) - light.location).to_track_quat("-Z", "Y").to_euler()
            )
        scene = bpy.context.scene
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = 24
        scene.cycles.denoising_use_gpu = False
        scene.world.color = (0.18, 0.18, 0.18)
        scene.render.resolution_x = 1000
        scene.render.resolution_y = 800
        scene.render.resolution_percentage = 100
        scene["editorial_note"] = (
            "Everything outside the admitted payload comes from destination/right."
        )
        save("raw.blend")
        return
    if stage == "verify-final":
        import hashlib

        checks = {}
        for name in [
            "raw.blend",
            "base.blend",
            "left.blend",
            "right.blend",
            "merged/tide-merged.blend",
        ]:
            bpy.ops.wm.open_mainfile(
                filepath=str(folder / name), use_scripts=False, load_ui=False
            )
            images = [
                i
                for i in bpy.data.images
                if i.source == "FILE" and i.filepath.endswith("paper.png")
            ]
            assert len(images) == 1
            image = images[0]
            resolved = Path(bpy.path.abspath(image.filepath)).resolve()
            assert image.filepath.startswith("//"), (name, image.filepath)
            assert resolved == (folder / "textures/paper.png").resolve(), (
                name,
                resolved,
            )
            assert resolved.read_bytes() == (folder / "textures/paper.png").read_bytes()
            checks[name] = {
                "relative_filepath": image.filepath,
                "resolved_texture_sha256": hashlib.sha256(
                    resolved.read_bytes()
                ).hexdigest(),
            }
        (folder / "relative-texture-receipt.json").write_text(
            json.dumps(checks, indent=2) + "\n"
        )
        return
    bpy.ops.wm.open_mainfile(
        filepath=str(folder / "base.blend"), use_scripts=False, load_ui=False
    )
    mesh = next(
        m for m in bpy.data.meshes if m.get("polyweft_schema") == "polyweft.ids.v1"
    )
    primary = next(
        o
        for o in bpy.data.objects
        if o.get("polyweft_id") == mesh["polyweft_primary_object"]
    )
    material = mesh.materials[0]
    principled = material.node_tree.nodes.get("Principled BSDF")
    uv = mesh.uv_layers["Surface UV"]
    same_vertex = [loop.index for loop in mesh.loops if loop.vertex_index == 0]
    assert len(same_vertex) >= 2
    if stage == "left":
        for index in range(25, 42):
            mesh.vertices[index].co.z += 0.075 * math.sin(math.pi * (index - 24) / 18)
        mesh.vertices[0].co.z += 0.12
        uv.data[same_vertex[0]].uv.x -= 0.08
        uv.data[4].uv.x += 0.04
        principled.inputs["Roughness"].default_value = 0.25
        primary.name = "Tide, branch A naming"
        primary["branch_note"] = "Branch A note outside scope"
        save("left.blend")
    elif stage == "right":
        for index in range(150, 167):
            mesh.vertices[index].co.x += 0.055 * math.sin(math.pi * (index - 149) / 18)
        mesh.vertices[0].co.x += 0.07
        uv.data[same_vertex[-1]].uv.y += 0.08
        uv.data[4].uv.y -= 0.03
        principled.inputs["Roughness"].default_value = 0.65
        principled.inputs["Base Color"].default_value = (0.08, 0.32, 0.47, 1)
        primary["branch_note"] = "Preserve destination note"
        bpy.context.scene.render.resolution_y = 820
        save("right.blend")
    else:
        raise ValueError("Unknown example native stage")


def create_example(folder, blender, portable=True):
    from polyweft.native import apply_plan, create_plan, prepare_source

    folder = Path(folder).absolute()
    if folder.exists():
        raise FileExistsError("Example output must be new")
    folder.mkdir(parents=True)
    native_stage("raw", folder, blender)
    prepare = prepare_source(
        folder / "raw.blend", "Tide", folder / "base.blend", blender
    )
    native_stage("left", folder, blender)
    native_stage("right", folder, blender)
    plan = create_plan(
        folder / "base.blend",
        folder / "left.blend",
        folder / "right.blend",
        folder / "review",
        blender,
    )
    conflicts = [x for x in plan["changes"] if x["kind"] == "conflict"]
    assert {x["domain"] for x in conflicts} == {"vertex", "uv", "material"}, conflicts
    decisions = {
        "schema": "polyweft.decisions.v1",
        "plan_id": plan["id"],
        "choices": {x["key"]: "left" for x in conflicts},
    }
    (folder / "decisions.json").write_text(json.dumps(decisions, indent=2) + "\n")
    receipt = apply_plan(
        folder / "review",
        folder / "merged" / "tide-merged.blend",
        folder / "decisions.json",
        blender,
        True,
    )
    native_stage("verify-final", folder, blender)
    # Portable public evidence does not disclose task-local source paths.
    for item in receipt["sources"].values():
        item["path"] = Path(item["path"]).name
    receipt["output"]["path"] = "merged/tide-merged.blend"
    (folder / "native-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    public = json.loads(json.dumps(plan))
    for item in public["sources"].values():
        item["path"] = Path(item["path"]).name
    (folder / "public-plan.json").write_text(json.dumps(public, indent=2) + "\n")
    if portable:
        (folder / "review" / "plan.json").write_text(
            json.dumps(public, indent=2) + "\n"
        )
    return {"plan": plan, "receipt": receipt, "prepare": prepare, "folder": str(folder)}


if __name__ == "__main__":
    if "--stage" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1 :]
        parser = argparse.ArgumentParser()
        parser.add_argument("--stage")
        parser.add_argument("--folder")
        parsed = parser.parse_args(args)
        inside_blender(parsed.stage, parsed.folder)
    else:
        parser = argparse.ArgumentParser()
        parser.add_argument("--blender", required=True)
        parser.add_argument("--output", required=True)
        args = parser.parse_args()
        result = create_example(args.output, args.blender)
        print(
            json.dumps(
                {
                    "folder": result["folder"],
                    "plan_id": result["plan"]["id"],
                    "changes": len(result["plan"]["changes"]),
                    "verified_fresh_reopen": result["receipt"]["verified_fresh_reopen"],
                },
                indent=2,
            )
        )
