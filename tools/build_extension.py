"""Build a self-contained, reproducible Blender extension from this source tree."""

import argparse
import hashlib
import json
from pathlib import Path
import tomllib
import zipfile


def package_files(root):
    root = Path(root).resolve(strict=True)
    files = {}
    for base, prefix in ((root / "extension", ""),
                         (root / "src" / "polyweft", "_engine/")):
        if not base.is_dir() or base.is_symlink():
            raise ValueError("Missing or linked extension/engine source directory")
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(base)
            if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            if path.is_symlink():
                raise ValueError("Linked package source is not permitted: " + str(relative))
            if path.is_dir():
                continue
            if not path.is_file():
                raise ValueError("Package source must be a regular file")
            name = prefix + relative.as_posix()
            if name == "PACKAGE-MANIFEST.json" or name in files:
                raise ValueError("Conflicting extension package member")
            files[name] = path.read_bytes()
    license_path = root / "LICENSE"
    if license_path.is_symlink() or not license_path.is_file():
        raise ValueError("The source license must be a regular file")
    files["LICENSE"] = license_path.read_bytes()
    required = {"__init__.py", "runtime.py", "worker_entry.py", "blender_manifest.toml",
                "_engine/workflow.py", "_engine/jobs.py", "_engine/bridge.py",
                "_engine/studio/index.html", "_engine/studio/app.mjs"}
    if required - set(files):
        raise ValueError("Missing required extension resources: " + ", ".join(sorted(required - set(files))))
    manifest = tomllib.loads(files["blender_manifest.toml"].decode("utf-8"))
    if manifest.get("id") != "polyweft" or manifest.get("type") != "add-on":
        raise ValueError("Unexpected Blender extension identity")
    receipt = {"schema": "polyweft.extension.manifest.v1", "version": manifest["version"],
               "files": {name: hashlib.sha256(raw).hexdigest()
                         for name, raw in sorted(files.items())}}
    files["PACKAGE-MANIFEST.json"] = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
    return files


def build(root, output):
    files = package_files(root)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation preserves any existing artifact, including symlinks.
    with output.open("xb") as stream:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, raw in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, raw, compresslevel=9)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New ZIP path; never overwritten")
    args = parser.parse_args()
    try:
        output = build(Path(__file__).resolve().parents[1], args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, "Extension build failed: " + str(error) + "\n")
    print(output)


if __name__ == "__main__":
    main()
