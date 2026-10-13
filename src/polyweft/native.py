"""Bounded fixed-script Blender orchestration with source and no-clobber guards."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .core import (
    SCOPE,
    build_plan,
    canonical,
    flatten,
    resolve_decisions,
    strict_load,
    verify_plan,
)

MAX_BLEND = 512 * 1024 * 1024
TIMEOUT = 90


def source_info(path):
    path = Path(path).expanduser().resolve(strict=True)
    if not path.is_file() or path.stat().st_size > MAX_BLEND:
        raise ValueError("Native source must be a regular file no larger than 512 MiB")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "sha256": digest.hexdigest()}


def new_output(path):
    path = Path(path).expanduser().absolute()
    if os.path.lexists(path):
        raise FileExistsError("Output already exists; use a new path: " + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.parent.resolve() / path.name


def bridge(blender, request, folder):
    executable = Path(blender).expanduser().resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError("Blender executable is not executable")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    request_path = folder / "request.json"
    response_path = folder / "response.json"
    request_path.write_bytes(canonical(request))
    command = [
        str(executable),
        "--background",
        "--factory-startup",
        "--disable-autoexec",
        "--offline-mode",
        "--python-exit-code",
        "1",
        "--python",
        str(Path(__file__).with_name("bridge.py")),
        "--",
        str(request_path),
        str(response_path),
    ]
    environment = os.environ.copy()
    for key in (
        "BLENDER_USER_CONFIG",
        "BLENDER_USER_SCRIPTS",
        "BLENDER_USER_DATAFILES",
        "BLENDER_USER_EXTENSIONS",
    ):
        target = folder / key.lower()
        target.mkdir(exist_ok=True)
        environment[key] = str(target)
    result = subprocess.run(
        command,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=TIMEOUT,
        env=environment,
    )
    if not response_path.exists():
        raise ValueError(
            "Blender bridge failed before producing a response. "
            + result.stdout[-2000:].decode("utf-8", "replace")
        )
    response = strict_load(response_path.read_bytes())
    if result.returncode or not response.get("ok"):
        raise ValueError(
            "Native admission/operation failed: "
            + response.get("error", "unknown error")
        )
    if set(response) != {"ok", "snapshot"}:
        raise ValueError("Unexpected native bridge response")
    return response["snapshot"]


def capture(blender, path, mesh_id, folder, reference=None):
    return bridge(
        blender,
        {
            "mode": "capture",
            "source": str(path),
            "mesh_id": mesh_id,
            "reference_directory": str(reference or Path(path).parent),
        },
        folder,
    )


@contextmanager
def native_temp(parent):
    # Save and final publication share the exact parent, preserving relative paths.
    descriptor, name = tempfile.mkstemp(
        prefix=".polyweft-", suffix=".blend", dir=parent
    )
    os.close(descriptor)
    path = Path(name)
    try:
        yield path
    finally:
        if path.exists():
            path.unlink()


def publish_native(temp, output):
    # Hard link publication is atomic no-clobber within this output filesystem.
    os.link(temp, output)


def _check_sources(sources):
    for value in sources.values():
        if source_info(value["path"]) != value:
            raise ValueError(
                "Source bytes changed or are unavailable: " + value["path"]
            )


def prepare_source(source, object_name, output, blender):
    original = source_info(source)
    output = new_output(output)
    with (
        tempfile.TemporaryDirectory(prefix=".polyweft-", dir=output.parent) as folder,
        native_temp(output.parent) as temp,
    ):
        folder = Path(folder)
        snapshot = bridge(
            blender,
            {
                "mode": "prepare",
                "source": original["path"],
                "object": object_name,
                "output": str(temp),
                "reference_directory": str(Path(original["path"]).parent),
            },
            folder / "prepare",
        )
        verified = capture(
            blender,
            temp,
            snapshot["guards"]["mesh_id"],
            folder / "verify",
            Path(original["path"]).parent,
        )
        if canonical(snapshot) != canonical(verified):
            raise ValueError(
                "Fresh prepared-file verification disagreed with captured state"
            )
        _check_sources({"source": original})
        publish_native(temp, output)
    return {
        "schema": "polyweft.prepare.receipt.v1",
        "source": original,
        "output": source_info(output),
        "mesh_id": snapshot["guards"]["mesh_id"],
        "scope": SCOPE,
        "verified_fresh_reopen": True,
    }


def studio_root():
    installed = Path(__file__).parent / "studio"
    return (
        installed
        if installed.is_dir()
        else Path(__file__).resolve().parents[1] / "studio"
    )


def create_plan(base, left, right, output, blender):
    sources = {
        side: source_info(path)
        for side, path in [("base", base), ("left", left), ("right", right)]
    }
    destination = new_output(output)
    with tempfile.TemporaryDirectory(
        prefix=".polyweft-review-", dir=destination.parent
    ) as folder:
        folder = Path(folder)
        # Capture base mesh by discovering its prepared identity in a fixed bridge.
        request = {
            "mode": "capture-base",
            "source": sources["base"]["path"],
            "reference_directory": str(Path(sources["base"]["path"]).parent),
        }
        base_snapshot = bridge(blender, request, folder / "native-base")
        mesh_id = base_snapshot["guards"]["mesh_id"]
        snapshots = {"base": base_snapshot}
        for side in ["left", "right"]:
            snapshots[side] = capture(
                blender, sources[side]["path"], mesh_id, folder / ("native-" + side)
            )
        plan = build_plan(sources, *(snapshots[k] for k in ["base", "left", "right"]))
        _check_sources(sources)
        bundle = folder / "review"
        bundle.mkdir()
        (bundle / "plan.json").write_bytes(
            json.dumps(plan, indent=2, allow_nan=False).encode() + b"\n"
        )
        assets = studio_root()
        if not assets.is_dir():
            raise ValueError("Installed studio assets are missing")
        for filename in [
            "index.html",
            "app.mjs",
            "style.css",
            "geometry.mjs",
            "mark.svg",
        ]:
            src = assets / filename
            if not src.is_file() or src.is_symlink():
                raise ValueError(
                    "Studio asset missing or not a regular file: " + filename
                )
            shutil.copyfile(src, bundle / filename)
        # Exclusive reservation prevents POSIX rename from replacing an empty directory.
        destination.mkdir()
        created = []
        try:
            for filename in [
                "index.html",
                "app.mjs",
                "style.css",
                "geometry.mjs",
                "mark.svg",
                "plan.json",
            ]:
                target = destination / filename
                os.link(bundle / filename, target)
                created.append(target)
        except BaseException:
            for target in created:
                target.unlink()
            try:
                destination.rmdir()
            except OSError:
                pass
            raise
    return plan


def apply_plan(review, output, decisions, blender, accept_scope=False):
    if not accept_scope:
        raise ValueError("Apply requires --accept-payload-scope: " + SCOPE)
    review = Path(review).resolve(strict=True)
    if not review.is_dir() or (review / "plan.json").is_symlink():
        raise ValueError("Review must contain a regular plan.json")
    original_plan = verify_plan(strict_load((review / "plan.json").read_bytes()))
    supplied = None if decisions is None else strict_load(Path(decisions).read_bytes())
    expected_values = resolve_decisions(original_plan, supplied)
    sources = original_plan["sources"]
    _check_sources(sources)
    destination = new_output(output)
    mesh_id = original_plan["snapshots"]["base"]["guards"]["mesh_id"]
    with (
        tempfile.TemporaryDirectory(
            prefix=".polyweft-", dir=destination.parent
        ) as folder,
        native_temp(destination.parent) as temp,
    ):
        folder = Path(folder)
        recaptured = {}
        for side in ["base", "left", "right"]:
            recaptured[side] = capture(
                blender, sources[side]["path"], mesh_id, folder / ("capture-" + side)
            )
        fresh = build_plan(sources, *(recaptured[k] for k in ["base", "left", "right"]))
        if canonical(fresh) != canonical(original_plan):
            raise ValueError("Plan no longer matches fresh native source capture")
        values = resolve_decisions(fresh, supplied)
        if canonical(values) != canonical(expected_values):
            raise ValueError("Resolved payload changed during fresh capture")
        reference = Path(sources["right"]["path"]).parent
        applied = bridge(
            blender,
            {
                "mode": "apply",
                "source": sources["right"]["path"],
                "mesh_id": mesh_id,
                "values": values,
                "output": str(temp),
                "reference_directory": str(reference),
            },
            folder / "apply",
        )
        actual = capture(blender, temp, mesh_id, folder / "verify", reference)
        if canonical(actual) != canonical(applied):
            raise ValueError(
                "Fresh native reopen differs from the applied native snapshot"
            )
        if (
            actual["guards"] != recaptured["right"]["guards"]
            or actual["observed"] != recaptured["right"]["observed"]
            or actual["name"] != recaptured["right"]["name"]
        ):
            raise ValueError(
                "Native merge changed guarded structure or observed destination-container data"
            )
        if canonical({k: v["value"] for k, v in flatten(actual).items()}) != canonical(
            values
        ):
            raise ValueError(
                "Reopened native payload does not equal the resolved source-bound fields"
            )
        _check_sources(sources)
        publish_native(temp, destination)
    return {
        "schema": "polyweft.apply.receipt.v1",
        "plan_id": fresh["id"],
        "sources": sources,
        "output": source_info(destination),
        "supported_changes": len(fresh["changes"]),
        "conflict_choices": {} if supplied is None else supplied["choices"],
        "verified_fresh_reopen": True,
        "input_bytes_unchanged": True,
        "scope": SCOPE,
        "observed_exclusions": fresh["observed_exclusions"],
    }
