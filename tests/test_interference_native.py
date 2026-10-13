"""Real native no-save surfaces, not browser-preview triangles."""

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from polyweft.core import canonical
from polyweft.native import create_plan, inspect_plan, prepare_source, source_info

ROOT = Path(__file__).resolve().parents[1]


class NativeInterferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blender = os.environ.get("POLYWEFT_BLENDER")
        if not cls.blender:
            raise unittest.SkipTest(
                "Set POLYWEFT_BLENDER; explicitly configured native gate never skips"
            )
        if not Path(cls.blender).is_file() or not os.access(cls.blender, os.X_OK):
            raise ValueError("Configured Blender is missing or not executable")
        cls.temp = tempfile.TemporaryDirectory(prefix="polyweft-surface-")
        cls.folder = Path(cls.temp.name) / "flanges"
        spec = importlib.util.spec_from_file_location(
            "native_flange_example", ROOT / "tools/make_interference_example.py"
        )
        cls.generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.generator)
        cls.example = cls.generator.create_example(
            cls.folder, cls.blender, portable=False
        )
        cls.sources = {
            s: source_info(cls.folder / (s + ".blend"))
            for s in ["base", "left", "right"]
        }

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temp"):
            cls.temp.cleanup()

    def assert_unchanged(self):
        for side, info in self.sources.items():
            self.assertEqual(source_info(self.folder / (side + ".blend")), info)

    def test_real_four_native_surfaces_match_source_and_merge_witnesses(self):
        r = self.example["report"]
        self.assertTrue(r["complete"])
        self.assertEqual(r["summaries"]["merged"]["crossings"], 20)
        for state in ["base", "left", "right", "merged"]:
            self.assertEqual(len(r["geometry"][state]["vertices"]), 16)
            self.assertEqual(len(r["geometry"][state]["triangles"]), 24)
            self.assertEqual(len(r["geometry"][state]["faces"]), 24)
        self.assertTrue(all(f["classification"] == "merge-only" for f in r["findings"]))
        self.assertEqual(
            json.loads((self.folder / "inspection/inspection.json").read_bytes()), r
        )
        self.assertTrue((self.folder / "merged/flanges-merged.blend").is_file())
        self.assertEqual(
            json.loads((self.folder / "reopened-surface.json").read_bytes()),
            r["geometry"]["merged"],
        )
        self.assertTrue(
            json.loads((self.folder / "apply-receipt.json").read_bytes())[
                "verified_fresh_reopen"
            ]
        )
        self.assertFalse(any(self.folder.glob("*.blend1")))
        self.assert_unchanged()

    def test_stale_choices_and_no_clobber_refuse_without_source_save(self):
        with self.assertRaises(FileExistsError):
            inspect_plan(
                self.folder / "review", self.folder / "inspection", None, self.blender
            )
        decisions = self.folder / "stale-choices.json"
        decisions.write_bytes(
            canonical(
                {"schema": "polyweft.decisions.v1", "plan_id": "0" * 64, "choices": {}}
            )
        )
        target = self.folder / "must-not-exist"
        with self.assertRaises(ValueError):
            inspect_plan(self.folder / "review", target, decisions, self.blender)
        self.assertFalse(target.exists())
        self.assert_unchanged()

    def test_actual_quad_nonplanar_and_concave_native_tessellation(self):
        self.generator.stage("polygons", self.folder, self.blender)
        prepared = self.folder / "polygon-base.blend"
        prepare_source(
            self.folder / "polygons.blend", "Native polygons", prepared, self.blender
        )
        branches = self.folder / "polygon-branches.py"
        branches.write_text(
            "import bpy\nfrom pathlib import Path\np="
            + repr(str(prepared))
            + "\nf=Path("
            + repr(str(self.folder))
            + ")\nfor side in ['left','right']:\n bpy.ops.wm.open_mainfile(filepath=p,use_scripts=False,load_ui=False)\n m=bpy.data.objects['Native polygons'].data\n if side=='left':\n  m.vertices[2].co=(.5,.5,.75)\n  m.vertices[6].co=(8,1,0)\n else:\n  m.vertices[0].co.z=-.5\n  m.vertices[4].co.x=4.5\n m.update()\n bpy.ops.wm.save_as_mainfile(filepath=str(f/('polygon-'+side+'.blend')),check_existing=False)\n"
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
                str(branches),
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout[-2000:])
        review = self.folder / "polygon-review"
        create_plan(
            prepared,
            self.folder / "polygon-left.blend",
            self.folder / "polygon-right.blend",
            review,
            self.blender,
        )
        before = source_info(prepared)
        report = inspect_plan(
            review, self.folder / "polygon-inspection", None, self.blender
        )
        self.assertTrue(report["complete"])
        self.assertEqual(source_info(prepared), before)
        for geometry in report["geometry"].values():
            self.assertEqual([len(f) for f in geometry["faces"]], [4, 5])
            self.assertEqual(
                [sum(t["face"] == i for t in geometry["triangles"]) for i in [0, 1]],
                [2, 3],
            )

        def triangle_vertices(state):
            return sorted(
                tuple(sorted(t["vertices"]))
                for t in report["geometry"][state]["triangles"]
            )

        self.assertNotEqual(
            triangle_vertices("base"),
            triangle_vertices("left"),
            "The concave-to-convex native edit should change its tessellation",
        )
        # Independently ask Blender's public mesh API, without the product bridge.
        script = self.folder / "independent-native-query.py"
        out = self.folder / "independent-triangles.json"
        script.write_text(
            "import bpy,json\nfrom pathlib import Path\nbpy.ops.wm.open_mainfile(filepath="
            + repr(str(prepared))
            + ",use_scripts=False,load_ui=False)\nm=bpy.data.objects['Native polygons'].data\nm.calc_loop_triangles()\nrows=[{'face':t.polygon_index,'vertices':[m.attributes['polyweft_vertex_id'].data[v].value for v in t.vertices],'corners':[m.attributes['polyweft_corner_id'].data[l].value for l in t.loops]} for t in m.loop_triangles]\nPath("
            + repr(str(out))
            + ").write_text(json.dumps(rows))\n"
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
        self.assertEqual(
            report["geometry"]["base"]["triangles"], json.loads(out.read_bytes())
        )
        self.assertEqual(source_info(prepared), before)
        self.assert_unchanged()


if __name__ == "__main__":
    unittest.main()
