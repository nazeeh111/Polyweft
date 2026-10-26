"""Original stdlib three-way payload planning. Never trust proposed operations."""

import copy
import hashlib
import json
import math
from urllib.parse import quote

SCOPE = "Only target mesh XYZ, UV corners and admitted material defaults are merged. Everything else comes from right. This is not a full-scene diff."
MAX_JSON = 64 * 1024 * 1024


def canonical(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("Value must be finite bounded JSON") from error


def strict_load(raw):
    if len(raw) > MAX_JSON:
        raise ValueError("JSON exceeds 64 MiB")

    def pairs(values):
        out = {}
        for key, value in values:
            if key in out:
                raise ValueError("Duplicate JSON key: " + key)
            out[key] = value
        return out

    def constant(value):
        raise ValueError("Nonfinite JSON number: " + value)

    def number(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("JSON number exceeds finite range")
        return parsed

    try:
        return json.loads(
            raw, object_pairs_hook=pairs, parse_constant=constant, parse_float=number
        )
    except (UnicodeError, RecursionError, json.JSONDecodeError) as e:
        raise ValueError("Invalid bounded JSON") from e


def validate_sources(sources):
    if type(sources) is not dict or set(sources) != {"base", "left", "right"}:
        raise ValueError("Exactly three source descriptors required")
    for source in sources.values():
        if type(source) is not dict or set(source) != {"path", "sha256"}:
            raise ValueError("Source requires exactly path and SHA256")
        path, digest = source["path"], source["sha256"]
        if type(path) is not str or not 1 <= len(path) <= 4096 or "\0" in path:
            raise ValueError("Invalid source path")
        if (
            type(digest) is not str
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("Invalid source SHA256")
    return sources


def plan_id(plan):
    if type(plan) is not dict:
        raise ValueError("Plan must be an object")
    validate_sources(plan.get("sources"))
    value = plan.copy()
    value.pop("id", None)
    value["sources"] = {
        side: {"sha256": source["sha256"]}
        for side, source in plan["sources"].items()
    }
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_snapshot(snapshot):
    if type(snapshot) is not dict or not {
        "name",
        "vertices",
        "faces",
        "uv_layers",
        "material_values",
        "guards",
        "observed",
    } <= set(snapshot):
        raise ValueError("Incomplete native snapshot")
    if (
        type(snapshot["name"]) is not str
        or type(snapshot["guards"]) is not dict
        or type(snapshot["observed"]) is not dict
    ):
        raise ValueError("Invalid snapshot metadata")
    vertices = snapshot["vertices"]
    faces = snapshot["faces"]
    layers = snapshot["uv_layers"]
    if (
        type(vertices) is not list
        or not 1 <= len(vertices) <= 20000
        or type(faces) is not list
        or not 1 <= len(faces) <= 20000
    ):
        raise ValueError("Snapshot geometry exceeds admission bounds")

    def vector(value, length):
        if (
            type(value) is not list
            or len(value) != length
            or any(
                type(v) not in (int, float)
                or not -1e9 <= v <= 1e9
                or not math.isfinite(v)
                for v in value
            )
        ):
            raise ValueError("Payload must contain finite atomic vectors")

    ids = set()
    for item in vertices:
        if (
            type(item) is not dict
            or set(item) != {"id", "co"}
            or type(item["id"]) is not int
            or not 1 <= item["id"] < 2**31
            or item["id"] in ids
        ):
            raise ValueError("Duplicate or invalid vertex identity")
        ids.add(item["id"])
        vector(item["co"], 3)
    for face in faces:
        if (
            type(face) is not list
            or not 3 <= len(face) <= 80000
            or any(type(v) is not int or v not in ids for v in face)
        ):
            raise ValueError("Invalid face vertex references")
    if sum(map(len, faces)) > 80000 or type(layers) is not dict or len(layers) > 8:
        raise ValueError("Snapshot corner/layer budget exceeded")
    total = 0
    for name, corners in layers.items():
        if (
            type(name) is not str
            or not 1 <= len(name) <= 128
            or type(corners) is not list
        ):
            raise ValueError("Invalid UV layer")
        total += len(corners)
        seen = set()
        for item in corners:
            if (
                type(item) is not dict
                or set(item) != {"id", "vertex", "uv"}
                or type(item["id"]) is not int
                or not 1 <= item["id"] < 2**31
                or item["id"] in seen
                or type(item["vertex"]) is not int
                or item["vertex"] not in ids
            ):
                raise ValueError("Duplicate or invalid UV corner identity")
            seen.add(item["id"])
            vector(item["uv"], 2)
    if total > 80000:
        raise ValueError("Snapshot UV corner budget exceeded")
    material = snapshot["material_values"]
    if type(material) is not dict or len(material) > 512:
        raise ValueError("Material payload budget exceeded")
    for key, item in material.items():
        if (
            type(key) is not str
            or not key.startswith("material:")
            or type(item) is not dict
            or set(item) != {"label", "value"}
            or type(item["label"]) is not str
        ):
            raise ValueError("Invalid material payload")
        value = item["value"]
        if type(value) is list:
            vector(value, 4)
        elif (
            type(value) not in (int, float)
            or not 0 <= value <= 1
            or not math.isfinite(value)
        ):
            raise ValueError("Invalid admitted material scalar")
    canonical(snapshot)
    return snapshot


def flatten(snapshot):
    result = {}

    def add(key, domain, label, value):
        if key in result:
            raise ValueError("Duplicate supported field identity: " + key)
        result[key] = {"domain": domain, "label": label, "value": value}

    for vertex in snapshot["vertices"]:
        add(
            "vertex:" + str(vertex["id"]),
            "vertex",
            "Vertex " + str(vertex["id"]),
            vertex["co"],
        )
    for name, corners in snapshot["uv_layers"].items():
        for corner in corners:
            add(
                "uv:" + quote(name, safe="") + ":" + str(corner["id"]),
                "uv",
                name + " / corner " + str(corner["id"]),
                corner["uv"],
            )
    for key, item in snapshot.get("material_values", {}).items():
        add(key, "material", item["label"], item["value"])
    canonical(result)
    return result


def build_plan(sources, base, left, right):
    validate_sources(sources)
    for snapshot in (base, left, right):
        validate_snapshot(snapshot)
    blockers = []
    exclusions = []
    for side, snapshot in [("left", left), ("right", right)]:
        if snapshot["guards"] != base["guards"]:
            changed = sorted(set(snapshot["guards"]) | set(base["guards"]))
            for field in changed:
                if snapshot["guards"].get(field) != base["guards"].get(field):
                    blockers.append(
                        {
                            "code": "target-structure-changed",
                            "message": side
                            + " changed guarded target structure: "
                            + field,
                        }
                    )
        for field, value in snapshot.get("observed", {}).items():
            if value != base.get("observed", {}).get(field):
                exclusions.append(
                    side
                    + " changed observed "
                    + field
                    + " outside the payload. It is not merged; the right container supplies it."
                )
    flat = [flatten(x) for x in [base, left, right]]
    keys = set(flat[0])
    changes = []
    if any(set(x) != keys for x in flat[1:]):
        blockers.append(
            {
                "code": "payload-membership-changed",
                "message": "Supported vertex, corner or material field membership changed",
            }
        )
    for key in sorted(set.intersection(*(set(x) for x in flat))):
        original, a, b = (x[key]["value"] for x in flat)
        if original == a == b:
            continue
        kind = (
            "same"
            if a == b
            else "right"
            if a == original
            else "left"
            if b == original
            else "conflict"
        )
        changes.append(
            {
                "key": key,
                "domain": flat[0][key]["domain"],
                "label": flat[0][key]["label"],
                "kind": kind,
                "base": original,
                "left": a,
                "right": b,
            }
        )
    plan = {
        "schema": "polyweft.plan.v1",
        "sources": copy.deepcopy(sources),
        "snapshots": {"base": base, "left": left, "right": right},
        "changes": changes,
        "blockers": blockers,
        "observed_exclusions": sorted(exclusions),
        "scope": SCOPE,
    }
    plan["id"] = plan_id(plan)
    return plan


def verify_plan(plan):
    if (
        type(plan) is not dict
        or set(plan)
        != {
            "schema",
            "id",
            "sources",
            "snapshots",
            "changes",
            "blockers",
            "observed_exclusions",
            "scope",
        }
        or plan["schema"] != "polyweft.plan.v1"
    ):
        raise ValueError("Unsupported plan schema or fields")
    validate_sources(plan["sources"])
    if type(plan["id"]) is not str or plan["scope"] != SCOPE:
        raise ValueError("Invalid plan identity or scope")
    if plan["id"] != plan_id(plan):
        raise ValueError(
            "Plan ID does not bind its exact source hashes, snapshots and changes"
        )
    if type(plan["sources"]) is not dict or type(plan["snapshots"]) is not dict:
        raise ValueError("Plan source and snapshot maps required")
    if set(plan["sources"]) != {"base", "left", "right"} or set(plan["snapshots"]) != {
        "base",
        "left",
        "right",
    }:
        raise ValueError("Plan requires exactly base, left and right")
    expected = build_plan(
        plan["sources"], *(plan["snapshots"][k] for k in ["base", "left", "right"])
    )
    if canonical(expected) != canonical(plan):
        raise ValueError(
            "Plan changes do not match a fresh derivation of captured payloads"
        )
    return plan


def resolve_decisions(plan, decisions=None):
    verify_plan(plan)
    if plan["blockers"]:
        raise ValueError(
            "Target structural blockers forbid apply; inspect plan.blockers"
        )
    conflicts = {x["key"] for x in plan["changes"] if x["kind"] == "conflict"}
    if decisions is None:
        choices = {}
    else:
        if (
            type(decisions) is not dict
            or set(decisions) != {"schema", "plan_id", "choices"}
            or decisions["schema"] != "polyweft.decisions.v1"
            or decisions["plan_id"] != plan["id"]
        ):
            raise ValueError(
                "Decisions have unknown fields or refer to a stale plan ID"
            )
        choices = decisions["choices"]
        if type(choices) is not dict:
            raise ValueError("Decision choices must be a JSON object")
    if set(choices) != conflicts:
        raise ValueError(
            "Choose exactly every conflict key; missing or unknown choices are forbidden"
        )
    if any(
        type(v) is not str or v not in {"base", "left", "right"}
        for v in choices.values()
    ):
        raise ValueError("Conflict choice must be base, left or right")
    expected = flatten(plan["snapshots"]["right"])
    values = {key: copy.deepcopy(item["value"]) for key, item in expected.items()}
    for change in plan["changes"]:
        side = (
            choices[change["key"]]
            if change["kind"] == "conflict"
            else "right"
            if change["kind"] in {"right", "same"}
            else "left"
        )
        values[change["key"]] = copy.deepcopy(change[side])
    return values
