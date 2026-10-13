"""Original closed-flange native example for four-state interference inspection."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def stage(mode, folder, blender):
    result = subprocess.run(
        [
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
            mode,
            "--folder",
            str(folder),
        ],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=90,
    )
    if result.returncode:
        raise RuntimeError(result.stdout[-6000:].decode("utf-8", "replace"))


def inside(mode, folder):
    import bpy

    folder = Path(folder)
    if mode in {"left", "right"}:
        bpy.ops.wm.open_mainfile(
            filepath=str(folder / "base.blend"), use_scripts=False, load_ui=False
        )
        mesh = bpy.data.objects["Vent flanges"].data
        for vertex in mesh.vertices:
            if mode == "left" and vertex.index < 8:
                vertex.co.x += 2
            if mode == "right" and vertex.index >= 8:
                vertex.co.x -= 3
        mesh.update()
        bpy.ops.wm.save_as_mainfile(
            filepath=str(folder / (mode + ".blend")), check_existing=False
        )
        return
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    if mode == "raw":
        vertices = [
            (-3, -1, -0.25),
            (-1, -1, -0.25),
            (-1, 1, -0.25),
            (-3, 1, -0.25),
            (-3, -1, 0.25),
            (-1, -1, 0.25),
            (-1, 1, 0.25),
            (-3, 1, 0.25),
            (2.5, -0.75, -1),
            (3.5, -0.75, -1),
            (3.5, 0.75, -1),
            (2.5, 0.75, -1),
            (2.5, -0.75, 1),
            (3.5, -0.75, 1),
            (3.5, 0.75, 1),
            (2.5, 0.75, 1),
        ]
        quads = [
            (0, 3, 2, 1),
            (4, 5, 6, 7),
            (0, 1, 5, 4),
            (1, 2, 6, 5),
            (2, 3, 7, 6),
            (3, 0, 4, 7),
        ]
        faces = []
        for start in [0, 8]:
            for q in quads:
                faces.extend(
                    [
                        (start + q[0], start + q[1], start + q[2]),
                        (start + q[0], start + q[2], start + q[3]),
                    ]
                )
        name = "Vent flanges"
    elif mode == "polygons":
        vertices = [
            (0, 0, 0),
            (2, 0, 0),
            (2, 2, 0.5),
            (0, 2, 0),
            (5, 0, 0),
            (7, 0, 0),
            (6, 1, 0),
            (7, 2, 0),
            (5, 2, 0),
        ]
        faces = [(0, 1, 2, 3), (4, 5, 6, 7, 8)]
        name = "Native polygons"
    else:
        raise ValueError("Unknown original generation stage")
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if mode == "raw":
        alias = bpy.data.objects.new("Shared flange study", mesh)
        alias.location.x = 8
        alias.hide_render = True
        bpy.context.collection.objects.link(alias)
        mesh["purpose"] = "Two individually separated edits collide only when combined."
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.wm.save_as_mainfile(
        filepath=str(folder / (mode + ".blend")), check_existing=False
    )


def create_example(folder, blender, portable=True):
    import tempfile

    from polyweft.core import canonical
    from polyweft.native import (
        apply_plan,
        bridge,
        create_plan,
        inspect_plan,
        prepare_source,
        source_info,
    )

    folder = Path(folder).absolute()
    folder.mkdir(parents=True, exist_ok=False)
    stage("raw", folder, blender)
    prepare_source(folder / "raw.blend", "Vent flanges", folder / "base.blend", blender)
    stage("left", folder, blender)
    stage("right", folder, blender)
    sources = {
        s: source_info(folder / (s + ".blend")) for s in ["base", "left", "right"]
    }
    plan = create_plan(
        folder / "base.blend",
        folder / "left.blend",
        folder / "right.blend",
        folder / "review",
        blender,
    )
    if (
        plan["blockers"]
        or len(plan["changes"]) != 16
        or any(c["kind"] == "conflict" for c in plan["changes"])
    ):
        raise AssertionError(
            "Original fixture must have 16 conflict-free vertex changes"
        )
    report = inspect_plan(folder / "review", folder / "inspection", None, blender)
    if not report["complete"] or report["summaries"]["merged"]["crossings"] != 20:
        raise AssertionError("Expected 20 native merge-only face crossings")
    for state in ["base", "left", "right"]:
        if any(
            report["summaries"][state][k]
            for k in ["crossings", "coplanar_overlaps", "contacts"]
        ):
            raise AssertionError("Separate input surfaces should be separated")
        if source_info(folder / (state + ".blend")) != sources[state]:
            raise AssertionError("No-save inspection changed native source")
    merged = folder / "merged" / "flanges-merged.blend"
    applied = apply_plan(folder / "review", merged, None, blender, accept_scope=True)
    with tempfile.TemporaryDirectory(prefix="polyweft-final-surface-") as query:
        reopened = bridge(
            blender,
            {
                "mode": "surface",
                "source": str(merged),
                "mesh_id": plan["snapshots"]["base"]["guards"]["mesh_id"],
            },
            query,
        )
    if canonical(reopened["geometry"]) != canonical(report["geometry"]["merged"]):
        raise AssertionError(
            "Published merged native tessellation differs from inspected combined surface"
        )
    if any(
        source_info(folder / (state + ".blend")) != sources[state] for state in sources
    ):
        raise AssertionError("Final apply/reopen changed a source")
    (folder / "reopened-surface.json").write_bytes(
        canonical(reopened["geometry"]) + b"\n"
    )
    public_apply = json.loads(canonical(applied))
    for info in public_apply["sources"].values():
        info["path"] = Path(info["path"]).name
    public_apply["output"]["path"] = "merged/flanges-merged.blend"
    (folder / "apply-receipt.json").write_bytes(canonical(public_apply) + b"\n")
    public = json.loads(canonical(plan))
    for info in public["sources"].values():
        info["path"] = Path(info["path"]).name
    (folder / "public-plan.json").write_bytes(canonical(public) + b"\n")
    if portable:
        for directory in ["review", "inspection"]:
            (folder / directory / "plan.json").write_bytes(canonical(public) + b"\n")
    receipt = {
        "schema": "polyweft.interference.example.v1",
        "plan_id": plan["id"],
        "inspection_id": report["id"],
        "runtime": report["runtime"],
        "source_sha256": report["source_sha256"],
        "source_unchanged": True,
        "native_vertices": 16,
        "native_faces": 24,
        "findings": len(report["findings"]),
        "complete": report["complete"],
        "published_native_surface_matches_inspection": True,
        "merged_sha256": applied["output"]["sha256"],
    }
    (folder / "native-receipt.json").write_bytes(canonical(receipt) + b"\n")
    return {"folder": folder, "plan": plan, "report": report, "receipt": receipt}


if __name__ == "__main__":
    if "--stage" in sys.argv:
        parser = argparse.ArgumentParser()
        parser.add_argument("--stage")
        parser.add_argument("--folder")
        args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
        inside(args.stage, args.folder)
    else:
        parser = argparse.ArgumentParser()
        parser.add_argument("--blender", required=True)
        parser.add_argument("--output", required=True)
        args = parser.parse_args()
        print(
            json.dumps(create_example(args.output, args.blender)["receipt"], indent=2)
        )
