"""Consequential numeric controls for source-bound represented surfaces."""

import copy
import hashlib
import unittest

from polyweft.core import build_plan, canonical, resolve_decisions
from polyweft.interference import classify_pair, inspect_surfaces


def fixture():
    points = [
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
    for start in [1, 9]:
        for q in quads:
            faces.extend(
                [
                    [start + q[0], start + q[1], start + q[2]],
                    [start + q[0], start + q[2], start + q[3]],
                ]
            )
    base = {
        "name": "Vent flanges",
        "vertices": [{"id": i + 1, "co": list(p)} for i, p in enumerate(points)],
        "faces": faces,
        "uv_layers": {},
        "material_values": {},
        "guards": {
            "mesh_id": "owned",
            "corner_order": list(range(1, 73)),
            "faces": faces,
        },
        "observed": {},
    }
    left, right = copy.deepcopy(base), copy.deepcopy(base)
    for v in left["vertices"][:8]:
        v["co"][0] += 2
    for v in right["vertices"][8:]:
        v["co"][0] -= 3
    return base, left, right


def plan_and_geometry(base, left, right, decisions=None):
    sources = {
        side: {
            "path": side + ".json",
            "sha256": hashlib.sha256(canonical(s)).hexdigest(),
        }
        for side, s in [("base", base), ("left", left), ("right", right)]
    }
    plan = build_plan(sources, base, left, right)
    if decisions is not None:
        decisions["plan_id"] = plan["id"]
    values = resolve_decisions(plan, decisions)
    combined = copy.deepcopy(right)
    for v in combined["vertices"]:
        v["co"] = values["vertex:" + str(v["id"])]
    geometry = {}
    for side, s in [
        ("base", base),
        ("left", left),
        ("right", right),
        ("merged", combined),
    ]:
        geometry[side] = {
            "vertices": copy.deepcopy(s["vertices"]),
            "faces": copy.deepcopy(s["faces"]),
            "triangles": [
                {
                    "face": i,
                    "vertices": f,
                    "corners": s["guards"]["corner_order"][i * 3 : i * 3 + 3],
                }
                for i, f in enumerate(s["faces"])
            ],
            "complete": True,
            "triangle_count": len(s["faces"]),
        }
    return plan, geometry, decisions


def run(base=None, left=None, right=None, limits=None, decisions=None):
    if base is None:
        base, left, right = fixture()
    p, g, d = plan_and_geometry(base, left, right, decisions)
    return inspect_surfaces(
        p, d, g, {"version": "owned numeric fixture", "build_hash": "none"}, limits
    )


class InterferenceTests(unittest.TestCase):
    def test_disjoint_edits_jointly_interfere_with_exact_pair_provenance(self):
        report = run()
        self.assertTrue(report["complete"])
        self.assertEqual(report["summaries"]["merged"]["crossings"], 20)
        for side in ["base", "left", "right"]:
            self.assertEqual(report["summaries"][side]["crossings"], 0)
        self.assertEqual(len(report["findings"]), 20)
        for f in report["findings"]:
            self.assertEqual(f["classification"], "merge-only")
            self.assertTrue(
                all(
                    f["history"][s]["kind"] == "separated"
                    for s in ["base", "left", "right"]
                )
            )
            self.assertEqual(
                {p["selected"] for p in f["provenance"]}, {"left", "right"}
            )
            self.assertTrue(
                all(p["faces"] and p["source_sha256"] for p in f["provenance"])
            )

    def test_contact_adjacency_and_coplanar_fold_are_distinct(self):
        from fractions import Fraction as F

        exact = lambda rows: [tuple(F(v) for v in row) for row in rows]
        a = exact([(0, 0, 0), (2, 0, 0), (0, 2, 0)])
        for b, ids, kind in [
            ([(0, 0, 0), (2, 0, 0), (0, -2, 0)], [1, 2, 4], "adjacent-boundary"),
            ([(0, 0, 0), (2, 0, 0), (1, 1, 0)], [1, 2, 4], "coplanar-overlap"),
            ([(2, 0, 0), (3, 0, 0), (2, -1, 0)], [4, 5, 6], "contact"),
            ([(0, 0, 0), (1, 0, 0), (2, 0, 0)], [4, 5, 6], "unknown"),
        ]:
            with self.subTest(kind=kind):
                self.assertEqual(
                    classify_pair(a, exact(b), [1, 2, 3], ids)["kind"], kind
                )

    def test_prior_interference_not_blame_merge(self):
        b, _l, _r = fixture()
        for v in b["vertices"][:8]:
            v["co"][0] += 2
        for v in b["vertices"][8:]:
            v["co"][0] -= 3
        report = run(b, b, b)
        self.assertTrue(report["findings"])
        self.assertTrue(
            all(f["classification"] == "prior-interference" for f in report["findings"])
        )

    def test_actual_explicit_choice_is_bound_to_witness(self):
        b, l, r = fixture()
        l["vertices"][8]["co"][1] -= 0.125
        d = {
            "schema": "polyweft.decisions.v1",
            "plan_id": "pending",
            "choices": {"vertex:9": "right"},
        }
        report = run(b, l, r, decisions=d)
        self.assertEqual(report["decisions"], d)
        self.assertTrue(
            any(
                p["vertex"] == 9 and p["explicit_choice"] and p["selected"] == "right"
                for f in report["findings"]
                for p in f["provenance"]
            )
        )

    def test_budgets_never_become_clear_results(self):
        for limits in [
            {"max_exact_tests": 1},
            {"max_broadphase_visits": 1},
            {"max_findings": 2},
            {"max_triangles": 2},
            {"max_provenance_entries": 2},
        ]:
            with self.subTest(limits=limits):
                report = run(limits=limits)
                self.assertFalse(report["complete"])
                self.assertTrue(report["incomplete_reasons"])
        for bad in [
            {"max_exact_tests": True},
            {"max_exact_tests": 0},
            {"unknown_limit": 1},
        ]:
            self.assertRaises(ValueError, run, limits=bad)

    def test_geometry_binding_and_face_order_cannot_be_forged(self):
        b, l, r = fixture()
        p, g, d = plan_and_geometry(b, l, r)
        for mutate in ["coordinate", "face", "corner"]:
            bad = copy.deepcopy(g)
            if mutate == "coordinate":
                bad["merged"]["vertices"][0]["co"][0] += 1
            if mutate == "face":
                bad["left"]["faces"].reverse()
            if mutate == "corner":
                bad["merged"]["triangles"][0]["corners"][0] = 999
            with self.subTest(mutate=mutate):
                self.assertRaises(
                    ValueError,
                    inspect_surfaces,
                    p,
                    d,
                    bad,
                    {"version": "fixture", "build_hash": "none"},
                )

    def test_degenerate_surface_is_incomplete(self):
        b, l, r = fixture()
        for s in [b, l, r]:
            s["vertices"][0]["co"] = s["vertices"][1]["co"][:]
        report = run(b, l, r)
        self.assertFalse(report["complete"])
        self.assertTrue(report["summaries"]["base"]["unknown_faces"])

    def test_scale_translation_preserve_pair_witness_counts(self):
        b, l, r = fixture()
        for s in [b, l, r]:
            for v in s["vertices"]:
                v["co"] = [c * 8 + 16 for c in v["co"]]
        self.assertEqual(run(b, l, r)["summaries"]["merged"]["crossings"], 20)

    def test_vertex_relabel_and_native_triangle_permutation_preserve_face_pairs(self):
        b, l, r = fixture()
        for snapshot in [b, l, r]:
            for vertex in snapshot["vertices"]:
                vertex["id"] += 100
            snapshot["faces"] = [[v + 100 for v in face] for face in snapshot["faces"]]
            snapshot["guards"]["faces"] = snapshot["faces"]
        plan, geometry, decisions = plan_and_geometry(b, l, r)
        geometry["left"]["triangles"].reverse()
        geometry["right"]["triangles"] = (
            geometry["right"]["triangles"][7:] + geometry["right"]["triangles"][:7]
        )
        report = inspect_surfaces(
            plan, decisions, geometry, {"version": "fixture", "build_hash": "none"}
        )
        self.assertEqual(report["summaries"]["merged"]["crossings"], 20)
        self.assertTrue(
            all(f["classification"] == "merge-only" for f in report["findings"])
        )

    def test_prior_same_pair_contact_is_not_strict_new(self):
        b, l, r = fixture()
        for snapshot in [b, l]:
            for vertex in snapshot["vertices"][8:]:
                vertex["co"][0] -= 1.5
        report = run(b, l, r)
        findings = [
            f for f in report["findings"] if f["history"]["left"]["kind"] == "contact"
        ]
        self.assertTrue(findings)
        self.assertTrue(all(f["classification"] == "prior-contact" for f in findings))

    def test_exact_small_separation_stays_separate(self):
        from fractions import Fraction as F

        a = [tuple(map(F, p)) for p in [(0, 0, 0), (1, 0, 0), (0, 1, 0)]]
        b = [(p[0], p[1], F(1, 2**40)) for p in a]
        self.assertEqual(classify_pair(a, b, [1, 2, 3], [4, 5, 6])["kind"], "separated")


if __name__ == "__main__":
    unittest.main()
