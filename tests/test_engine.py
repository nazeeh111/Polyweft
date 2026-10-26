import copy
import unittest

from polyweft.core import (
    SCOPE,
    build_plan,
    plan_id,
    resolve_decisions,
    strict_load,
    validate_snapshot,
    verify_plan,
)


def snapshot():
    return {
        "name": "Sculpture",
        "vertices": [
            {"id": 1, "co": [0.0, 0.0, 0.0]},
            {"id": 2, "co": [1.0, 0.0, 0.0]},
        ],
        "faces": [[1, 2, 1]],
        "uv_layers": {
            "UVMap": [
                {"id": 1, "vertex": 1, "uv": [0.0, 0.0]},
                {"id": 2, "vertex": 2, "uv": [1.0, 0.0]},
            ]
        },
        "material_values": {
            "material:m:n:Roughness": {"label": "Clay / roughness", "value": 0.5}
        },
        "guards": {"mesh_id": "mesh", "vertex_order": [1, 2], "shape_keys": False},
        "observed": {"object_names": ["Sculpture"], "scene": {"frame_end": 250}},
    }


def sources():
    return {
        k: {
            "path": "/" + k + ".blend",
            "sha256": {"base": "a", "left": "b", "right": "c"}[k] * 64,
        }
        for k in ["base", "left", "right"]
    }


class EngineTests(unittest.TestCase):
    def test_atomic_conflicts_independent_changes_and_same_values(self):
        b = snapshot()
        l = copy.deepcopy(b)
        r = copy.deepcopy(b)
        l["vertices"][0]["co"] = [0, 0, 1]
        r["vertices"][0]["co"] = [1, 0, 0]
        r["vertices"][1]["co"] = [2, 0, 0]
        p = build_plan(sources(), b, l, r)
        self.assertEqual([x["kind"] for x in p["changes"]], ["conflict", "right"])
        self.assertEqual(p["scope"], SCOPE)
        with self.assertRaises(ValueError):
            resolve_decisions(p, None)
        decisions = {
            "schema": "polyweft.decisions.v1",
            "plan_id": p["id"],
            "choices": {"vertex:1": "left"},
        }
        result = resolve_decisions(p, decisions)
        self.assertEqual(result["vertex:1"], [0, 0, 1])
        self.assertEqual(result["vertex:2"], [2, 0, 0])
        r["vertices"][0]["co"] = [0, 0, 1]
        self.assertEqual(build_plan(sources(), b, l, r)["changes"][0]["kind"], "same")

    def test_portable_identity_binds_payload_not_absolute_paths(self):
        b = snapshot()
        p = build_plan(sources(), b, b, b)
        move = copy.deepcopy(p)
        move["sources"]["left"]["path"] = "/elsewhere/left.blend"
        self.assertEqual(plan_id(move), p["id"])
        move["snapshots"]["left"]["vertices"][0]["co"] = [1, 0, 0]
        self.assertNotEqual(plan_id(move), p["id"])
        self.assertRaises(ValueError, verify_plan, move)

    def test_identity_preserves_shared_source_descriptor_behavior(self):
        p = {
            "sources": {
                side: {"path": side + ".blend", "sha256": str(i) * 64}
                for i, side in enumerate(("base", "left", "right"))
            },
            "payload": {"coordinates": [1, 2, 3]},
        }
        p["payload"]["source_alias"] = p["sources"]["base"]
        original = copy.deepcopy(p)
        self.assertEqual(
            plan_id(p),
            "1f3d0b0531b18740e164342d47de697bbc5a61c5db677e22992de28d234eb2d5",
        )
        self.assertEqual(p, original)
        self.assertIs(p["payload"]["source_alias"], p["sources"]["base"])

    def test_tampered_operations_and_stale_extra_choices_rejected(self):
        b = snapshot()
        l = copy.deepcopy(b)
        l["vertices"][0]["co"] = [0, 0, 1]
        p = build_plan(sources(), b, l, b)
        tampered = copy.deepcopy(p)
        tampered["changes"][0]["left"] = [7, 8, 9]
        self.assertRaises(ValueError, verify_plan, tampered)
        for d in [
            {"schema": "polyweft.decisions.v1", "plan_id": "0" * 64, "choices": {}},
            {
                "schema": "polyweft.decisions.v1",
                "plan_id": p["id"],
                "choices": {"vertex:1": "left"},
            },
        ]:
            self.assertRaises(ValueError, resolve_decisions, p, d)

    def test_guard_changes_refuse_and_exclusions_are_observed(self):
        b = snapshot()
        l = copy.deepcopy(b)
        r = copy.deepcopy(b)
        l["guards"]["vertex_order"] = [2, 1]
        l["observed"]["object_names"] = ["Renamed"]
        p = build_plan(sources(), b, l, r)
        self.assertTrue(p["blockers"])
        self.assertTrue(p["observed_exclusions"])
        self.assertRaises(ValueError, resolve_decisions, p, None)

    def test_nonfinite_and_duplicate_json_are_rejected_at_load(self):
        for raw in [
            b'{"x":1,"x":2}',
            b'{"x":NaN}',
            b'{"x":Infinity}',
            b'{"x":1e999}',
            b'{"x":-1e999}',
        ]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                strict_load(raw)

    def test_malformed_metadata_and_payloads_are_ordinary_errors(self):
        b = snapshot()
        p = build_plan(sources(), b, b, b)
        for malformed in [None, [], {}, {"base": None, "left": None, "right": None}]:
            q = copy.deepcopy(p)
            q["sources"] = malformed
            with self.subTest(sources=malformed), self.assertRaises(ValueError):
                verify_plan(q)
        for field, value in [
            ("vertices", None),
            ("guards", []),
            ("name", False),
            ("uv_layers", []),
            ("material_values", None),
        ]:
            q = copy.deepcopy(b)
            q[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_snapshot(q)
        for vector in [[False, 0, 0], [float("nan"), 0, 0], [1e10, 0, 0], [0, 0]]:
            q = copy.deepcopy(b)
            q["vertices"][0]["co"] = vector
            with self.subTest(vector=vector), self.assertRaises(ValueError):
                validate_snapshot(q)
        q = copy.deepcopy(b)
        q["vertices"] = [{"id": i + 1, "co": [0, 0, 0]} for i in range(20001)]
        self.assertRaises(ValueError, validate_snapshot, q)


if __name__ == "__main__":
    unittest.main()
