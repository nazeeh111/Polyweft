"""Publish an exact static review of an original native example, without machine paths."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from polyweft.core import (
    canonical,
    plan_id,
    resolve_decisions,
    strict_load,
    verify_plan,
)
from polyweft.native import studio_root


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("review", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    plan = verify_plan(strict_load((args.review / "plan.json").read_bytes()))
    original_id = plan["id"]
    for side, source in plan["sources"].items():
        source["path"] = side + ".blend"
    if plan_id(plan) != original_id:
        raise ValueError("Redaction changed immutable plan identity")
    raw = json.dumps(plan, indent=2, allow_nan=False).encode() + b"\n"
    if b"/Users/" in raw or b"/home/" in raw or b"C:\\Users\\" in raw:
        raise ValueError("Example plan still contains a machine home path")
    args.output.mkdir()
    for name in [
        "index.html",
        "app.mjs",
        "geometry.mjs",
        "inspection.mjs",
        "style.css",
        "mark.svg",
    ]:
        source = studio_root() / name
        if source.is_symlink() or not source.is_file():
            raise ValueError("Expected regular review asset: " + name)
        shutil.copyfile(source, args.output / name)
    (args.output / "plan.json").write_bytes(raw)
    inspection_path = args.review / "inspection.json"
    if inspection_path.exists():
        if inspection_path.is_symlink() or not inspection_path.is_file():
            raise ValueError("Expected a regular inspection report")
        report = strict_load(inspection_path.read_bytes())
        resolve_decisions(plan, report["decisions"])
        content = {k: v for k, v in report.items() if k != "id"}
        if (
            report["schema"] != "polyweft.inspection.v1"
            or report["plan_id"] != original_id
            or report["source_sha256"]
            != {s: plan["sources"][s]["sha256"] for s in ("base", "left", "right")}
            or report["id"] != hashlib.sha256(canonical(content)).hexdigest()
        ):
            raise ValueError(
                "Inspection is not bound to this exact plan/source/choices"
            )
        report_raw = canonical(report) + b"\n"
        if any(path in report_raw for path in (b"/Users/", b"/home/", b"C:\\Users\\")):
            raise ValueError("Inspection contains a machine home path")
        (args.output / "inspection.json").write_bytes(report_raw)
    (args.output / ".nojekyll").write_text("")
    (args.output / "README.txt").write_text(
        "Polyweft original native example review\n"
        "This studio shows captured native Blender data. Geometry is a browser preview.\n"
        "Exported JSON decisions do not save a .blend. Use the installed CLI and Blender.\n"
        "Local source paths were replaced with example labels; plan identity is unchanged.\n"
        "Download source example files and regenerate a local plan before applying.\n"
    )
    print(
        json.dumps(
            {"plan_id": original_id, "output": str(args.output), "redacted_paths": True}
        )
    )


if __name__ == "__main__":
    main()
