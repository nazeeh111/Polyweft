"""Create a portable, source-bearing native example bundle with no machine paths."""

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("example", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--runtime", required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Example archive must be new")
    receipt = json.loads((args.example / "native-receipt.json").read_text())
    for side, source in receipt["sources"].items():
        if digest(args.example / (side + ".blend")) != source["sha256"]:
            raise ValueError("Native source bytes disagree with receipt: " + side)
    if digest(args.example / "merged/tide-merged.blend") != receipt["output"]["sha256"]:
        raise ValueError("Native output bytes disagree with reopened receipt")
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / "Polyweft-Tide"
        root.mkdir()
        for name in [
            "raw.blend",
            "base.blend",
            "left.blend",
            "right.blend",
            "decisions.json",
            "native-receipt.json",
            "public-plan.json",
        ]:
            shutil.copyfile(args.example / name, root / name)
        for directory in ["textures", "merged", "demo"]:
            shutil.copytree(args.example / directory, root / directory)
        # Include license and complete corresponding original software source.
        project = Path(__file__).resolve().parents[1]
        shutil.copyfile(project / "LICENSE", root / "LICENSE")
        source_root = root / "source"
        source_root.mkdir()
        for name in [
            "README.md",
            "LICENSE",
            "pyproject.toml",
            "MANIFEST.in",
            "CONTRIBUTING.md",
            "SECURITY.md",
        ]:
            shutil.copyfile(project / name, source_root / name)
        for directory in ["src", "tools", "tests", "docs", "examples"]:
            for path in sorted((project / directory).rglob("*")):
                if (
                    not path.is_file()
                    or path.is_symlink()
                    or "__pycache__" in path.parts
                ):
                    continue
                if path.suffix not in {
                    ".py",
                    ".mjs",
                    ".html",
                    ".css",
                    ".svg",
                    ".md",
                    ".png",
                }:
                    continue
                target = source_root / path.relative_to(project)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        (root / "README.md").write_text(
            "# Polyweft Tide native example\n\n"
            "Original generated ribbon sculpture, with two objects sharing a mesh and independent UV seam edits.\n"
            "Original software source is in source/ and licensed GPL-3.0-or-later (LICENSE).\n"
            "Generated and reopened using Blender "
            + args.runtime
            + ". Artwork and generator are original Polyweft work.\n\n"
            "The browser demo is a review preview. It never writes a native scene.\n"
            "After extracting, generate a local plan using your Blender executable:\n\n"
            "```sh\npolyweft plan base.blend left.blend right.blend --output local-review --blender /path/to/blender\n"
            "polyweft studio local-review --port 6395\n```\n\n"
            "Resolve the three conflicts and export decisions. Then:\n\n"
            "```sh\npolyweft apply local-review --decisions decisions.json --output your-merge.blend "
            "--accept-payload-scope --blender /path/to/blender\n```\n\n"
            "Use decisions exported from your own plan if its identity differs from the recorded example. "
            "Never copy an old plan identity into new choices. The provided merged file and receipt show "
            "one actual result, with left selected for the three competing values. Everything outside "
            "the admitted payload comes from right. Original sources are unchanged.\n"
        )
        manifest = {
            str(p.relative_to(root)): {"bytes": p.stat().st_size, "sha256": digest(p)}
            for p in sorted(root.rglob("*"))
            if p.is_file()
        }
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(
            args.output, "x", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, "Polyweft-Tide/" + str(path.relative_to(root)))
    print(
        json.dumps(
            {
                "archive": str(args.output),
                "sha256": digest(args.output),
                "runtime": args.runtime,
                "plan_id": receipt["plan_id"],
            }
        )
    )


if __name__ == "__main__":
    main()
