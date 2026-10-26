"""Run with Blender --background --factory-startup --python, then -- ZIP.

Install the actual archive and exercise its bundled worker with an intentionally
missing source. This checks registration and process wiring, not mesh geometry
or hands-on panel usability. No source scene is created, opened or captured.
"""

import importlib
import json
from pathlib import Path
import sys
import tempfile
import time

import bpy


def check(archive):
    with tempfile.TemporaryDirectory(prefix="polyweft-installed-") as temporary:
        root = Path(temporary).resolve()
        repo = bpy.context.preferences.extensions.repos.new(
            name="Polyweft installed check", module="polyweft_check",
            custom_directory=str(root / "extensions"))
        repo.use_remote_url = False
        module_name = "bl_ext." + repo.module + ".polyweft"
        result = bpy.ops.extensions.package_install_files(
            filepath=str(archive), repo=repo.module, enable_on_install=True)
        assert result == {"FINISHED"}, result
        addon = importlib.import_module(module_name)
        state = bpy.context.window_manager.polyweft
        before = (bpy.data.filepath, bpy.data.is_dirty,
                  tuple(sorted(obj.name for obj in bpy.data.objects)))
        missing = root / "intentionally-missing.blend"
        output = root / "must-not-exist.blend"
        state.prepare_source = str(missing)
        state.object_name = "Missing"
        state.prepared_output = str(output)
        assert bpy.ops.polyweft.action(action="prepare") == {"FINISHED"}
        job = addon._session.active
        assert job is not None
        deadline = time.monotonic() + 30
        try:
            while not job.reaped:
                addon._tick()
                if time.monotonic() > deadline:
                    raise TimeoutError("Installed worker did not finish")
                time.sleep(.05)
            assert job.status["state"] == "failed", job.status
            assert str(missing) in job.status.get("error", ""), job.status
            assert not output.exists()
            assert not state.busy
            assert before == (bpy.data.filepath, bpy.data.is_dirty,
                              tuple(sorted(obj.name for obj in bpy.data.objects)))
            record = {"schema": "polyweft.installed-registration.v1",
                      "blender": bpy.app.version_string,
                      "archive": str(archive), "worker_exit": job.process.returncode,
                      "worker_reaped": job.reaped, "missing_source_refused": True,
                      "editor_unchanged": True,
                      "limit": "Registration/worker wiring only; no native merge or hands-on UI claim"}
        finally:
            bpy.ops.preferences.addon_disable(module=module_name)
        assert job.process.poll() is not None and job.reaped
        assert not hasattr(bpy.types.WindowManager, "polyweft")
        print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    if len(args) != 1:
        raise ValueError("Expected one extension ZIP after --")
    check(Path(args[0]).resolve(strict=True))
