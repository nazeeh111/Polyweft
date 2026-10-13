"""Source-bound four-state surface interference, exact on represented coordinates.

This is a diagnostic of native tessellated target surfaces, not a solid collision
or clearance certificate. Incomplete work never becomes an absence claim.
"""

import copy
import hashlib
import itertools
import time
from fractions import Fraction as F

from .core import canonical, resolve_decisions, verify_plan

STATES = ("base", "left", "right", "merged")
INTERFERENCE_SCOPE = "Between distinct native tessellated target polygon faces in object-local coordinates only. This is not solid collision, within-polygon distortion, physical clearance, artistic validity or all-scene safety."
DEFAULT_LIMITS = {
    "max_triangles": 80000,
    "max_broadphase_visits": 100000,
    "max_polygon_pairs": 20000,
    "max_exact_tests": 50000,
    "max_findings": 200,
    "max_witnesses_per_state": 8,
    "max_provenance_entries": 10000,
    "max_seconds": 15,
    "max_report_bytes": 32 * 1024 * 1024,
}
KINDS = {
    "separated",
    "adjacent-boundary",
    "contact",
    "crossing",
    "coplanar-overlap",
    "unknown",
}


def _limits(supplied):
    result = DEFAULT_LIMITS.copy()
    if supplied is not None:
        if type(supplied) is not dict or set(supplied) - set(result):
            raise ValueError("Unknown inspection limit")
        for key, value in supplied.items():
            if type(value) is not int or not 1 <= value <= result[key]:
                raise ValueError(
                    "Inspection limits must be positive integers no higher than defaults"
                )
            result[key] = value
    return result


def _choices(plan, decisions):
    resolve_decisions(plan, decisions)
    return (
        copy.deepcopy(decisions)
        if decisions is not None
        else {"schema": "polyweft.decisions.v1", "plan_id": plan["id"], "choices": {}}
    )


def _prepare_geometry(plan, decisions, geometry, limits):
    if type(geometry) is not dict or set(geometry) != set(STATES):
        raise ValueError("Inspection requires four native surface states")
    values = resolve_decisions(plan, decisions)
    base = plan["snapshots"]["base"]
    corners = base["guards"].get("corner_order")
    if (
        type(corners) is not list
        or len(corners) != sum(map(len, base["faces"]))
        or any(type(c) is not int or c < 1 for c in corners)
        or len(set(corners)) != len(corners)
    ):
        raise ValueError("Native face corner identities are required")
    corner_map = {}
    offset = 0
    for face, vertices in enumerate(base["faces"]):
        for corner, vertex in zip(corners[offset : offset + len(vertices)], vertices):
            corner_map[corner] = (face, vertex)
        offset += len(vertices)
    prepared = {}
    for state in STATES:
        g = geometry[state]
        if type(g) is not dict or not {
            "vertices",
            "faces",
            "triangles",
            "complete",
            "triangle_count",
        } <= set(g):
            raise ValueError("Invalid native surface envelope")
        expected = plan["snapshots"][state if state != "merged" else "right"][
            "vertices"
        ]
        if state == "merged":
            expected = [
                {"id": v["id"], "co": values["vertex:" + str(v["id"])]}
                for v in expected
            ]
        if (
            canonical(g["vertices"]) != canonical(expected)
            or g["faces"] != base["faces"]
        ):
            raise ValueError(
                "Native surface does not match source/choice coordinates and stable face identity"
            )
        if (
            type(g["complete"]) is not bool
            or type(g["triangle_count"]) is not int
            or g["triangle_count"] < 0
            or type(g["triangles"]) is not list
            or len(g["triangles"]) > DEFAULT_LIMITS["max_triangles"]
            or len(g["triangles"]) > g["triangle_count"]
        ):
            raise ValueError("Native surface exceeds represented triangle limits")
        if g["complete"] and g["triangle_count"] != len(g["triangles"]):
            raise ValueError("Complete native surface omitted triangles")
        points = {v["id"]: tuple(F(c) for c in v["co"]) for v in expected}
        by_face = {i: [] for i in range(len(base["faces"]))}
        unknown = set()
        bounds = {}
        triangles = []
        seen = set()
        for index, triangle in enumerate(g["triangles"]):
            if type(triangle) is not dict or set(triangle) != {
                "face",
                "vertices",
                "corners",
            }:
                raise ValueError("Invalid native triangle fields")
            face, vertices, ids = (
                triangle["face"],
                triangle["vertices"],
                triangle["corners"],
            )
            if (
                type(face) is not int
                or face not in by_face
                or type(vertices) is not list
                or type(ids) is not list
                or len(vertices) != 3
                or len(ids) != 3
                or len(set(ids)) != 3
                or any(
                    type(c) is not int
                    or type(v) is not int
                    or corner_map.get(c) != (face, v)
                    for c, v in zip(ids, vertices)
                )
            ):
                raise ValueError(
                    "Native triangle does not belong to its stable parent face/corners"
                )
            signature = (face, tuple(ids))
            if signature in seen:
                raise ValueError("Duplicate native triangle")
            seen.add(signature)
            tri = [points[v] for v in vertices]
            triangles.append(tri)
            if index >= limits["max_triangles"]:
                unknown.add(face)
                continue
            by_face[face].append(index)
            if len(set(vertices)) != 3 or normal(tri) == (0, 0, 0):
                unknown.add(face)
        for face, indices in by_face.items():
            if len(indices) != len(base["faces"][face]) - 2:
                unknown.add(face)
            if indices:
                flat = [p for i in indices for p in triangles[i]]
                bounds[face] = tuple(
                    (min(p[a] for p in flat), max(p[a] for p in flat)) for a in range(3)
                )
        prepared[state] = {
            "points": points,
            "by_face": by_face,
            "triangles": triangles,
            "unknown": unknown,
            "bounds": bounds,
            "boundary_edges": {
                face: _boundary_edges(vertices)
                for face, vertices in enumerate(g["faces"])
            },
        }
    return prepared


def inspect_surfaces(plan, decisions, geometry, runtime, limits=None):
    """Compare stable polygon pairs across four independently tessellated states."""
    verify_plan(plan)
    limits = _limits(limits)
    decisions = _choices(plan, decisions)
    if (
        type(runtime) is not dict
        or set(runtime) != {"version", "build_hash"}
        or any(type(v) is not str or len(v) > 256 for v in runtime.values())
    ):
        raise ValueError("Invalid native runtime identity")
    prepared = _prepare_geometry(plan, decisions, geometry, limits)
    started = time.monotonic()
    reasons = []
    work = {
        "broadphase_visits": 0,
        "candidate_polygon_pairs": 0,
        "exact_tests": 0,
        "inspected_polygon_pairs": 0,
        "reported_findings": 0,
        "unreported_findings": 0,
        "witnesses_truncated": 0,
        "unknown_pair_states": 0,
        "provenance_entries": 0,
        "provenance_omitted": 0,
    }

    def reason(message):
        if message not in reasons:
            reasons.append(message)

    def expired():
        if time.monotonic() - started >= limits["max_seconds"]:
            reason("Inspection time limit reached")
            return True
        return False

    for state in STATES:
        if not geometry[state]["complete"]:
            reason(state + " native surface was truncated")
        if prepared[state]["unknown"]:
            reason(state + " has degenerate or incompletely represented polygon faces")
    pairs = set()
    broadphase_stopped = False
    # Union candidates from all four states, so source-only interference is retained.
    for state in STATES:
        bounds = prepared[state]["bounds"]
        active = []
        for face in sorted(bounds, key=lambda f: (bounds[f][0][0], f)):
            if expired():
                broadphase_stopped = True
                break
            current = bounds[face]
            active = [f for f in active if bounds[f][0][1] >= current[0][0]]
            for previous in active:
                if work["broadphase_visits"] >= limits["max_broadphase_visits"]:
                    reason("Broadphase comparison limit reached")
                    broadphase_stopped = True
                    break
                work["broadphase_visits"] += 1
                if all(
                    bounds[previous][a][1] >= current[a][0]
                    and current[a][1] >= bounds[previous][a][0]
                    for a in (1, 2)
                ):
                    pair = tuple(sorted((previous, face)))
                    if pair not in pairs and len(pairs) >= limits["max_polygon_pairs"]:
                        reason("Candidate polygon-pair limit reached")
                        broadphase_stopped = True
                        break
                    pairs.add(pair)
            if broadphase_stopped:
                break
            active.append(face)
        if broadphase_stopped:
            break
    work["candidate_polygon_pairs"] = len(pairs)
    findings = []
    summaries = {
        state: {
            "crossings": 0,
            "coplanar_overlaps": 0,
            "contacts": 0,
            "unknown_faces": sorted(prepared[state]["unknown"]),
            "unknown_pairs": 0,
        }
        for state in STATES
    }
    rank = {
        "separated": 0,
        "adjacent-boundary": 1,
        "contact": 2,
        "crossing": 3,
        "coplanar-overlap": 4,
    }

    def pair_state(state, faces):
        p = prepared[state]
        if any(f in p["unknown"] for f in faces):
            return {"kind": "unknown", "witnesses": []}
        witnesses = []
        kind = "separated"
        uncertain = False
        for a, b in itertools.product(*(p["by_face"][f] for f in faces)):
            if expired() or work["exact_tests"] >= limits["max_exact_tests"]:
                reason(
                    "Exact triangle-pair limit reached"
                    if work["exact_tests"] >= limits["max_exact_tests"]
                    else "Inspection time limit reached"
                )
                uncertain = True
                break
            work["exact_tests"] += 1
            ta, tb = geometry[state]["triangles"][a], geometry[state]["triangles"][b]
            result = classify_pair(
                p["triangles"][a],
                p["triangles"][b],
                ta["vertices"],
                tb["vertices"],
                p["boundary_edges"][ta["face"]],
                p["boundary_edges"][tb["face"]],
            )
            if result["kind"] == "unknown":
                uncertain = True
                continue
            if rank[result["kind"]] > rank[kind]:
                kind = result["kind"]
            if result["kind"] in {"contact", "crossing", "coplanar-overlap"}:
                if len(witnesses) < limits["max_witnesses_per_state"]:
                    witnesses.append(
                        {
                            "triangles": [a, b],
                            "kind": result["kind"],
                            "points": result["points"],
                        }
                    )
                else:
                    work["witnesses_truncated"] += 1
                    # Keep a witness for the strongest positive classification.
                    least = min(
                        range(len(witnesses)), key=lambda i: rank[witnesses[i]["kind"]]
                    )
                    if rank[result["kind"]] > rank[witnesses[least]["kind"]]:
                        witnesses[least] = {
                            "triangles": [a, b],
                            "kind": result["kind"],
                            "points": result["points"],
                        }
        # A positive witness survives partial work. Absence never does.
        if uncertain and kind not in {"crossing", "coplanar-overlap"}:
            kind = "unknown"
        return {"kind": kind, "witnesses": witnesses, "complete": not uncertain}

    changed_vertices = {
        int(c["key"].split(":")[1]): c
        for c in plan["changes"]
        if c["domain"] == "vertex"
    }
    changed_ids = set(changed_vertices)
    face_changes = [
        set(face) & changed_ids for face in plan["snapshots"]["base"]["faces"]
    ]
    for faces in sorted(pairs):
        if expired() or work["exact_tests"] >= limits["max_exact_tests"]:
            reason(
                "Exact triangle-pair limit reached"
                if work["exact_tests"] >= limits["max_exact_tests"]
                else "Inspection time limit reached"
            )
            break
        history = {state: pair_state(state, faces) for state in STATES}
        work["inspected_polygon_pairs"] += 1
        for state, result in history.items():
            field = {
                "crossing": "crossings",
                "coplanar-overlap": "coplanar_overlaps",
                "contact": "contacts",
                "unknown": "unknown_pairs",
            }.get(result["kind"])
            if field:
                summaries[state][field] += 1
            if result["kind"] == "unknown":
                work["unknown_pair_states"] += 1
        kinds = [history[s]["kind"] for s in STATES[:3]]
        if history["merged"]["kind"] not in {"crossing", "coplanar-overlap"}:
            continue
        classification = (
            "prior-interference"
            if any(k in {"crossing", "coplanar-overlap"} for k in kinds)
            else "uncertain-history"
            if any(k == "unknown" for k in kinds)
            else "prior-contact"
            if any(k == "contact" for k in kinds)
            else "merge-only"
        )
        if len(findings) >= limits["max_findings"]:
            work["unreported_findings"] += 1
            reason("Finding report limit reached")
            continue
        provenance = []
        affected = sorted(face_changes[faces[0]] | face_changes[faces[1]])
        remaining = limits["max_provenance_entries"] - work["provenance_entries"]
        if len(affected) > remaining:
            work["provenance_omitted"] += len(affected) - remaining
            reason("Provenance entry report limit reached")
        for vertex in affected[:remaining]:
            change = changed_vertices[vertex]
            on_faces = [
                f for f in faces if vertex in plan["snapshots"]["base"]["faces"][f]
            ]
            if not on_faces:
                continue
            selected = (
                decisions["choices"][change["key"]]
                if change["kind"] == "conflict"
                else "left"
                if change["kind"] == "left"
                else "right"
            )
            provenance.append(
                {
                    "key": change["key"],
                    "vertex": vertex,
                    "faces": on_faces,
                    "selected": selected,
                    "explicit_choice": change["kind"] == "conflict",
                    "base": change["base"],
                    "value": change[selected],
                    "source_sha256": plan["sources"][selected]["sha256"],
                }
            )
            work["provenance_entries"] += 1
        findings.append(
            {
                "faces": list(faces),
                "classification": classification,
                "history": history,
                "provenance": provenance,
            }
        )
    if work["witnesses_truncated"]:
        reason("Per-state witness display limit reached")
    work["reported_findings"] = len(findings)
    complete = not reasons
    report = {
        "schema": "polyweft.inspection.v1",
        "plan_id": plan["id"],
        "decisions": decisions,
        "source_sha256": {s: plan["sources"][s]["sha256"] for s in STATES[:3]},
        "runtime": runtime,
        "scope": INTERFERENCE_SCOPE,
        "complete": complete,
        "summary_scope": "all pairs" if complete else "bounded inspected pairs",
        "incomplete_reasons": reasons,
        "limits": limits,
        "work": work,
        "geometry": copy.deepcopy(geometry),
        "summaries": summaries,
        "findings": findings,
    }
    report["id"] = hashlib.sha256(canonical(report)).hexdigest()
    if len(canonical(report)) > limits["max_report_bytes"]:
        raise ValueError(
            "Inspection exceeds serialized report limit; no result may be treated as clear"
        )
    return report


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def scale(a, s):
    return tuple(x * s for x in a)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def normal(triangle):
    return cross(sub(triangle[1], triangle[0]), sub(triangle[2], triangle[0]))


def inside(point, triangle, strict=False):
    n = normal(triangle)
    signs = [
        dot(cross(sub(b, a), sub(point, a)), n)
        for a, b in zip(triangle, triangle[1:] + triangle[:1])
    ]
    return all(x > 0 if strict else x >= 0 for x in signs)


def point_on_segment(point, a, b):
    direction = sub(b, a)
    if direction == (0, 0, 0):
        return point == a
    return cross(sub(point, a), direction) == (0, 0, 0) and 0 <= dot(
        sub(point, a), direction
    ) <= dot(direction, direction)


def plane_points(edges, triangle):
    """Exact edge/plane points that also lie in the other triangle."""
    n = normal(triangle)
    points = set()
    for a, b in zip(edges, edges[1:] + edges[:1]):
        da, db = (dot(n, sub(v, triangle[0])) for v in (a, b))
        if da == 0 and inside(a, triangle):
            points.add(a)
        if db == 0 and inside(b, triangle):
            points.add(b)
        if da * db < 0:
            p = add(a, scale(sub(b, a), da / (da - db)))
            if inside(p, triangle):
                points.add(p)
    return points


def coplanar_polygon(a, b):
    """Clip one triangle by another in a nonsingular exact 2D projection."""
    n = normal(a)
    drop = max(range(3), key=lambda i: abs(n[i]))
    axes = [i for i in range(3) if i != drop]
    project = lambda p: tuple(p[i] for i in axes)
    orient = lambda a, b, p: (
        (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    )
    clip = [project(p) for p in b]
    polygon = [project(p) for p in a]
    sign = 1 if orient(*clip) > 0 else -1
    for x, y in zip(clip, clip[1:] + clip[:1]):
        result = []
        if not polygon:
            break
        for p, q in zip(polygon, polygon[1:] + polygon[:1]):
            dp, dq = sign * orient(x, y, p), sign * orient(x, y, q)
            if dp >= 0:
                result.append(p)
            if (dp < 0) != (dq < 0):
                t = dp / (dp - dq)
                result.append(tuple(p[i] + t * (q[i] - p[i]) for i in range(2)))
        polygon = result

    def lift(p):
        out = [F(0)] * 3
        for axis, value in zip(axes, p):
            out[axis] = value
        out[drop] = (dot(n, a[0]) - sum(n[i] * out[i] for i in axes)) / n[drop]
        return tuple(out)

    points = set(map(lift, polygon))
    area2 = abs(
        sum(
            p[0] * q[1] - q[0] * p[1]
            for p, q in zip(polygon, polygon[1:] + polygon[:1])
        )
    )
    return points, area2 > 0


def _boundary_edges(vertices):
    return {frozenset((a, b)) for a, b in zip(vertices, vertices[1:] + vertices[:1])}


def classify_pair(a, b, ids_a, ids_b, boundary_edges_a=None, boundary_edges_b=None):
    """Suppress only joins on actual shared parent boundaries, not tessellation diagonals.

    Standalone triangles default to their three boundary edges. Native inspection
    supplies both original polygon boundaries independently of their triangulation.
    """
    if normal(a) == (0, 0, 0) or normal(b) == (0, 0, 0):
        return {"kind": "unknown", "reason": "degenerate triangle"}
    # Broad phase uses closed bounds so exact contacts are not discarded.
    if any(
        max(p[i] for p in a) < min(p[i] for p in b)
        or max(p[i] for p in b) < min(p[i] for p in a)
        for i in range(3)
    ):
        return {"kind": "separated"}
    coplanar = (
        cross(normal(a), normal(b)) == (0, 0, 0)
        and dot(normal(a), sub(b[0], a[0])) == 0
    )
    if coplanar:
        points, positive_area = coplanar_polygon(a, b)
    else:
        points = plane_points(a, b) | plane_points(b, a)
        positive_area = False
    if not points:
        return {"kind": "separated"}
    common = set(ids_a) & set(ids_b)
    expected = [p for vid, p in zip(ids_a, a) if vid in common]
    if len(common) == 1 and all(p == expected[0] for p in points):
        return {"kind": "adjacent-boundary"}
    shared_edge = frozenset(common)
    edges_a = _boundary_edges(ids_a) if boundary_edges_a is None else boundary_edges_a
    edges_b = _boundary_edges(ids_b) if boundary_edges_b is None else boundary_edges_b
    if (
        len(common) == 2
        and shared_edge in edges_a
        and shared_edge in edges_b
        and all(point_on_segment(p, *expected) for p in points)
    ):
        return {"kind": "adjacent-boundary"}
    if positive_area:
        kind = "coplanar-overlap"
    elif len(points) > 1:
        endpoints = max(
            itertools.combinations(points, 2), key=lambda pq: dot(sub(*pq), sub(*pq))
        )
        midpoint = scale(add(*endpoints), F(1, 2))
        kind = (
            "crossing"
            if inside(midpoint, a, True) and inside(midpoint, b, True)
            else "contact"
        )
    else:
        kind = "contact"
    return {"kind": kind, "points": [[str(v) for v in p] for p in sorted(points)]}
