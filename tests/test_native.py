"""Actual Blender gates. An explicitly configured executable must never skip."""

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from polyweft.core import canonical, plan_id, strict_load
from polyweft.native import apply_plan, create_plan, prepare_source, source_info

ROOT = Path(__file__).resolve().parents[1]


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blender = os.environ.get("POLYWEFT_BLENDER")
        if not cls.blender:
            raise unittest.SkipTest(
                "Set POLYWEFT_BLENDER to run native gates; configured CI must execute them"
            )
        if not Path(cls.blender).is_file() or not os.access(cls.blender, os.X_OK):
            raise ValueError("Configured POLYWEFT_BLENDER is missing or not executable")
        spec = importlib.util.spec_from_file_location(
            "polyweft_example", ROOT / "tools/make_example.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.temp = tempfile.TemporaryDirectory(prefix="polyweft-native-")
        cls.folder = Path(cls.temp.name) / "tide"
        cls.example = module.create_example(cls.folder, cls.blender, portable=False)
        cls.plan = cls.example["plan"]
        cls.sources = {
            side: source_info(cls.folder / (side + ".blend"))
            for side in ["base", "left", "right"]
        }

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temp"):
            cls.temp.cleanup()

    def assert_sources_unchanged(self):
        for side, expected in self.sources.items():
            self.assertEqual(source_info(self.folder / (side + ".blend")), expected)

    def test_real_example_all_domains_shared_mesh_and_independent_final_texture(self):
        plan = self.plan
        receipt = self.example["receipt"]
        self.assertFalse(plan["blockers"])
        self.assertEqual(
            {x["domain"] for x in plan["changes"] if x["kind"] == "conflict"},
            {"vertex", "uv", "material"},
        )
        self.assertEqual(len(plan["snapshots"]["base"]["guards"]["shared_users"]), 2)
        self.assertTrue(plan["observed_exclusions"])
        self.assertTrue(receipt["verified_fresh_reopen"])
        self.assertTrue(receipt["input_bytes_unchanged"])
        paths = json.loads((self.folder / "relative-texture-receipt.json").read_text())
        self.assertEqual(len(paths), 5)
        digest = hashlib.sha256(
            (self.folder / "textures/paper.png").read_bytes()
        ).hexdigest()
        for item in paths.values():
            self.assertTrue(item["relative_filepath"].startswith("//"))
            self.assertEqual(item["resolved_texture_sha256"], digest)
        self.assert_sources_unchanged()

    def test_no_clobber_alias_and_required_scope(self):
        for path in [
            self.folder / "base.blend",
            self.folder / "left.blend",
            self.folder / "merged/tide-merged.blend",
        ]:
            with self.subTest(path=path), self.assertRaises(FileExistsError):
                apply_plan(
                    self.folder / "review",
                    path,
                    self.folder / "decisions.json",
                    self.blender,
                    True,
                )
        with self.assertRaises(FileExistsError):
            prepare_source(
                self.folder / "raw.blend",
                "Tide",
                self.folder / "raw.blend",
                self.blender,
            )
        with self.assertRaises(ValueError):
            apply_plan(
                self.folder / "review",
                self.folder / "scope-not-accepted.blend",
                self.folder / "decisions.json",
                self.blender,
                False,
            )
        self.assertFalse((self.folder / "scope-not-accepted.blend").exists())
        self.assert_sources_unchanged()

    def test_stale_unknown_or_unresolved_choices_forbid_output(self):
        decisions = strict_load((self.folder / "decisions.json").read_bytes())
        variants = [
            None,
            dict(decisions, plan_id="0" * 64),
            dict(decisions, choices={}),
            dict(decisions, operations=[]),
        ]
        for index, variant in enumerate(variants):
            destination = self.folder / f"bad-choice-{index}.blend"
            path = None
            if variant is not None:
                path = self.folder / f"bad-choice-{index}.json"
                path.write_bytes(canonical(variant))
            with self.subTest(index=index), self.assertRaises(ValueError):
                apply_plan(
                    self.folder / "review", destination, path, self.blender, True
                )
            self.assertFalse(destination.exists())
        self.assert_sources_unchanged()

    def test_manipulated_plan_and_stale_source_hash_reject_before_native_write(self):
        for index, alteration in enumerate(["value", "source"]):
            review = self.folder / f"manipulated-{index}"
            review.mkdir()
            plan = copy.deepcopy(self.plan)
            if alteration == "value":
                plan["changes"][0]["left"] = [7, 8, 9]
            else:
                plan["sources"]["left"]["sha256"] = "0" * 64
            plan["id"] = plan_id(plan)
            (review / "plan.json").write_bytes(canonical(plan))
            decisions = {
                "schema": "polyweft.decisions.v1",
                "plan_id": plan["id"],
                "choices": {
                    x["key"]: "left" for x in plan["changes"] if x["kind"] == "conflict"
                },
            }
            choice = self.folder / f"manipulated-{index}.json"
            choice.write_bytes(canonical(decisions))
            out = self.folder / f"manipulated-{index}.blend"
            with self.subTest(alteration=alteration), self.assertRaises(ValueError):
                apply_plan(review, out, choice, self.blender, True)
            self.assertFalse(out.exists())
        self.assert_sources_unchanged()

    def test_actual_unprepared_and_shape_key_sources_refuse(self):
        with self.assertRaises(ValueError):
            create_plan(
                self.folder / "raw.blend",
                self.folder / "left.blend",
                self.folder / "right.blend",
                self.folder / "unprepared-review",
                self.blender,
            )
        self.assertFalse((self.folder / "unprepared-review").exists())
        script = self.folder / "shape-key.py"
        target = self.folder / "shape-key.blend"
        script.write_text(
            "import bpy\nbpy.ops.wm.open_mainfile(filepath="
            + repr(str(self.folder / "left.blend"))
            + ",use_scripts=False,load_ui=False)\nobj=next(o for o in bpy.data.objects if o.type=='MESH' and o.data.get('polyweft_schema')=='polyweft.ids.v1')\nobj.shape_key_add(name='Basis')\nbpy.ops.wm.save_as_mainfile(filepath="
            + repr(str(target))
            + ",check_existing=False)\n"
        )
        result = subprocess.run(
            [
                self.blender,
                "--background",
                "--factory-startup",
                "--disable-autoexec",
                "--offline-mode",
                "--python-exit-code",
                "1",
                "--python",
                str(script),
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout[-2000:])
        with self.assertRaisesRegex(ValueError, "Shape-key"):
            create_plan(
                self.folder / "base.blend",
                target,
                self.folder / "right.blend",
                self.folder / "shape-review",
                self.blender,
            )
        self.assertFalse((self.folder / "shape-review").exists())
        self.assert_sources_unchanged()

    def test_native_node_semantics_and_uv_render_selector_are_blockers(self):
        script = self.folder / "semantic-guards.py"
        code = """import bpy
from pathlib import Path
folder=Path(FOLDER)
def opening():
 bpy.ops.wm.open_mainfile(filepath=str(folder/'base.blend'),use_scripts=False,load_ui=False)
 bpy.context.preferences.filepaths.save_version=0
 return next(m for m in bpy.data.meshes if m.get('polyweft_schema')=='polyweft.ids.v1')
mesh=opening();node=mesh.materials[0].node_tree.nodes.get('Principled BSDF');node.mute=True
bpy.ops.wm.save_as_mainfile(filepath=str(folder/'muted.blend'),check_existing=False)
mesh=opening();node=next(n for n in mesh.materials[0].node_tree.nodes if n.bl_idname=='ShaderNodeTexImage');node.image_user.use_cyclic=True
bpy.ops.wm.save_as_mainfile(filepath=str(folder/'image-user.blend'),check_existing=False)
mesh=opening();layer=mesh.uv_layers.new(name='Alternate UV')
for index,item in enumerate(layer.data):item.uv=mesh.uv_layers['Surface UV'].data[index].uv
mesh.uv_layers['Surface UV'].active_render=True
bpy.ops.wm.save_as_mainfile(filepath=str(folder/'two-uv-base.blend'),check_existing=False)
layer.active_render=True
bpy.ops.wm.save_as_mainfile(filepath=str(folder/'uv-selector.blend'),check_existing=False)
""".replace("FOLDER", repr(str(self.folder)))
        script.write_text(code)
        run = subprocess.run(
            [
                self.blender,
                "--background",
                "--factory-startup",
                "--disable-autoexec",
                "--offline-mode",
                "--python-exit-code",
                "1",
                "--python",
                str(script),
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=90,
        )
        self.assertEqual(run.returncode, 0, run.stdout[-2000:])
        for name in ["muted", "image-user"]:
            plan = create_plan(
                self.folder / "base.blend",
                self.folder / (name + ".blend"),
                self.folder / "base.blend",
                self.folder / (name + "-review"),
                self.blender,
            )
            self.assertTrue(plan["blockers"], name)
            destination = self.folder / (name + "-merged.blend")
            with self.assertRaises(ValueError):
                apply_plan(
                    self.folder / (name + "-review"),
                    destination,
                    None,
                    self.blender,
                    True,
                )
            self.assertFalse(destination.exists())
        plan = create_plan(
            self.folder / "two-uv-base.blend",
            self.folder / "uv-selector.blend",
            self.folder / "two-uv-base.blend",
            self.folder / "uv-selector-review",
            self.blender,
        )
        self.assertTrue(
            any("uv_render_clone" in item["message"] for item in plan["blockers"])
        )
        self.assert_sources_unchanged()


if __name__ == "__main__":
    unittest.main()
