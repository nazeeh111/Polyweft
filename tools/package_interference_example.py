"""Package the original native interference case with source and file digests."""

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
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Example archive must be new")
    receipt = json.loads((args.example / "native-receipt.json").read_text())
    applied = json.loads((args.example / "apply-receipt.json").read_text())
    report = json.loads((args.example / "inspection/inspection.json").read_text())
    if (
        not receipt["published_native_surface_matches_inspection"]
        or receipt["inspection_id"] != report["id"]
    ):
        raise ValueError(
            "Published native surface/inspection identity was not verified"
        )
    if not applied["verified_fresh_reopen"] or not applied["input_bytes_unchanged"]:
        raise ValueError(
            "Native apply did not establish reopen and source preservation"
        )
    for side, expected in receipt["source_sha256"].items():
        if digest(args.example / (side + ".blend")) != expected:
            raise ValueError("Example source differs from native receipt: " + side)
    merged = args.example / "merged/flanges-merged.blend"
    if (
        digest(merged) != receipt["merged_sha256"]
        or digest(merged) != applied["output"]["sha256"]
    ):
        raise ValueError("Merged native output differs from reopened receipt")
    project = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "Polyweft-Flanges"
        root.mkdir()
        for name in [
            "raw.blend",
            "base.blend",
            "left.blend",
            "right.blend",
            "native-receipt.json",
            "apply-receipt.json",
            "reopened-surface.json",
        ]:
            shutil.copyfile(args.example / name, root / name)
        for directory in ["merged", "demo"]:
            shutil.copytree(args.example / directory, root / directory)
        shutil.copyfile(project / "LICENSE", root / "LICENSE")
        source = root / "source"
        source.mkdir()
        for name in [
            "README.md",
            "LICENSE",
            "pyproject.toml",
            "MANIFEST.in",
            "CONTRIBUTING.md",
            "SECURITY.md",
        ]:
            shutil.copyfile(project / name, source / name)
        for directory in ["src", "tools", "tests", "docs", "examples", ".github"]:
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
                    ".jpg",
                    ".gif",
                    ".json",
                    ".yml",
                }:
                    continue
                target = source / path.relative_to(project)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        (root / "README.md").write_text(
            "# Polyweft: a clean field merge can create crossing surfaces\n\n"
            "Original 16-vertex, 24-triangle flange study. The three inputs have separated surfaces; "
            "16 independent edits combine into 20 crossing face pairs. The saved merged scene is intentionally intersecting.\n"
            "The report used native Blender "
            + report["runtime"]["version"]
            + " tessellation. "
            "Published native output was freshly reopened and matches the recorded combined surface.\n\n"
            "The browser demo is recorded inspection, not a native writer. Local paths were redacted. "
            "After extracting to a new folder, install the release wheel and regenerate your own local plan:\n\n"
            "```sh\npolyweft plan base.blend left.blend right.blend --output local-review --blender /path/to/blender\n"
            "polyweft inspect local-review --output local-inspection --blender /path/to/blender\n"
            "polyweft studio local-inspection --port 0\n"
            "polyweft apply local-review --output your-merge.blend --accept-payload-scope --blender /path/to/blender\n```\n\n"
            "Keep the original inspection.json unchanged for its checksum. The original example has no field conflicts; "
            "other reviews require decisions exported from their exact local plan. Prepared stable topology is required. "
            "Only the admitted payload is merged; everything else comes from right. Inspection concerns represented "
            "surfaces between distinct target faces, not containment, other objects, within-face distortion or physical safety. "
            "Incomplete results never establish separation.\n\n"
            "Complete original software source and test fixtures are in source/, GPL-3.0-or-later. "
            "Source, example artwork and numerical evidence are original Polyweft work.\n"
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
                    archive.write(
                        path, "Polyweft-Flanges/" + str(path.relative_to(root))
                    )
    print(
        json.dumps(
            {
                "archive": str(args.output),
                "sha256": digest(args.output),
                "manifest_files": len(manifest),
                "inspection_id": report["id"],
                "runtime": report["runtime"],
            }
        )
    )


if __name__ == "__main__":
    main()
