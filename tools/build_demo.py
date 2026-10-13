"""Publish an exact static review of an original native example, without machine paths."""

import argparse
import json
import shutil
from pathlib import Path

from polyweft.core import plan_id, strict_load, verify_plan
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
    for name in ["index.html", "app.mjs", "geometry.mjs", "style.css", "mark.svg"]:
        source = studio_root() / name
        if source.is_symlink() or not source.is_file():
            raise ValueError("Expected regular review asset: " + name)
        shutil.copyfile(source, args.output / name)
    (args.output / "plan.json").write_bytes(raw)
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
