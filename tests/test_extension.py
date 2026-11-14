"""Pure process/package regressions. No Blender or scene fixture is executed."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


runtime = module("extension_runtime", ROOT / "extension" / "runtime.py")
builder = module("extension_builder", ROOT / "tools" / "build_extension.py")


class InterfaceTests(unittest.TestCase):
    def test_strict_bounded_json_and_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "status.json"
            for raw in (b'{"state":"running","state":"completed","stage":"x"}',
                        b'{"state":"unknown","stage":"x"}',
                        b'{"state":"running","stage":"x","unexpected":1}',
                        b'{"state":"running","stage":"x","result":NaN}',
                        b'{"state":"running","stage":"x","result":1e999}',
                        b'[[[[[[[[[['):
                path.write_bytes(raw)
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    runtime.read_status(path)
            path.write_text('{"state":"completed","stage":"saved","result":{"output":"x"}}')
            self.assertEqual(runtime.read_status(path)["state"], "completed")
            with patch.object(runtime, "MAX_STATUS", 5):
                # read_json's explicit limit is also used for loading saved plans.
                self.assertRaises(ValueError, runtime.read_json, path, 5)
            linked = path.parent / "linked.json"
            linked.symlink_to(path)
            self.assertRaises(ValueError, runtime.read_status, linked)
            self.assertRaises(FileExistsError, runtime.write_new_json, path, {})

    def test_fixed_action_arguments_and_readonly_loopback(self):
        good = {"base": "b", "left": "l", "right": "r", "output": "o", "blender": "app"}
        runtime.validate_request("plan", good)
        for action, args in (("eval", good), ("plan", {**good, "code": "x"}),
                             ("plan", {**good, "base": ""}),
                             ("apply", {"review": "r", "output": "o", "decisions": None,
                                        "blender": "b", "accept_scope": 1})):
            self.assertRaises(ValueError, runtime.validate_request, action, args)
        self.assertEqual(runtime.readonly_url("http://127.0.0.1:65535/?readonly=1"),
                         "http://127.0.0.1:65535/?readonly=1")
        for url in ("https://example.com/", "http://localhost:90/?readonly=1",
                    "http://127.0.0.1:90/?readonly=0", "http://127.0.0.1:90/file?readonly=1",
                    "http://user@127.0.0.1:90/?readonly=1", "http://127.0.0.1:99999/?readonly=1",
                    "http://127.0.0.1:90/?readonly=1#extra"):
            self.assertRaises(ValueError, runtime.readonly_url, url)

    def test_interpreter_is_only_bundled_and_version_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix = Path(temporary)
            (prefix / "bin").mkdir()
            self.assertRaises(ValueError, runtime.bundled_python, prefix, (3, 14))
            candidate = prefix / "bin" / ("python%d.%d" % sys.version_info[:2])
            candidate.symlink_to(sys.executable)
            self.assertEqual(runtime.bundled_python(prefix, sys.version_info[:2]), str(candidate))
            self.assertRaises(ValueError, runtime.bundled_python, prefix, (3, 1))

    def test_source_stamp_detects_replacement_and_saved_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "branch.blend"
            path.write_bytes(b"initial")
            stamp = runtime.source_stamp([path])
            path.write_bytes(b"changed")
            self.assertNotEqual(stamp, runtime.source_stamp([path]))
            stamp = runtime.source_stamp([path])
            other = path.with_name("new")
            other.write_bytes(b"changed")
            other.replace(path)
            self.assertNotEqual(stamp, runtime.source_stamp([path]))

    def test_output_identity_follows_parent_but_never_leaf(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "real").mkdir()
            (root / "alias").symlink_to(root / "real", target_is_directory=True)
            leaf = root / "real" / "output.blend"
            leaf.symlink_to(root / "nonexistent")
            self.assertEqual(runtime.output_identity(root / "alias" / "output.blend"), str(leaf))
            self.assertNotEqual(runtime.output_identity(leaf), str(leaf.resolve()))


FAKE_WORKFLOW = '''import json, os, select, sys, time
from pathlib import Path
def main():
    folder = Path(sys.argv[1])
    request = json.loads((folder / "request.json").read_text())
    def status(state, **extra):
        pending = folder / "status.pending"
        pending.write_text(json.dumps({"state": state, "stage": "test worker", **extra}))
        os.replace(pending, folder / "status.json")
    if request["action"] == "plan":
        status("completed", result={"path": request["args"]["output"]})
        return
    status("running", result={"url": "http://127.0.0.1:1234/?readonly=1"})
    while not (folder / "cancel").exists():
        ready, _, _ = select.select([sys.stdin.fileno()], [], [], .02)
        if ready:
            (folder / "saw-eof").write_text("yes")
            break
    status("cancelled")
'''


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        extension = self.root / "extension"
        extension.mkdir()
        shutil.copyfile(ROOT / "extension" / "worker_entry.py", extension / "worker_entry.py")
        (extension / "_engine").mkdir()
        (extension / "_engine" / "__init__.py").write_text("")
        (extension / "_engine" / "workflow.py").write_text(FAKE_WORKFLOW)
        self.session = runtime.Session(extension, self.root / "jobs", sys.executable)

    def drain(self):
        deadline = time.monotonic() + 5
        complete = []
        while self.session.pending and time.monotonic() < deadline:
            result = self.session.poll()
            if result:
                complete.append(result)
            time.sleep(.01)
        self.assertFalse(self.session.pending, "Owned worker did not exit")
        return complete

    def tearDown(self):
        self.session.shutdown()
        self.drain()
        self.temporary.cleanup()

    def test_fixed_launcher_completion_and_job_recovery(self):
        args = {"base": "b", "left": "l", "right": "r", "output": "o", "blender": "app"}
        job = self.session.start("plan", args)
        self.assertRaises(ValueError, self.session.start, "plan", args)
        self.assertEqual(self.drain(), [job])
        self.assertEqual(job.status["state"], "completed")
        self.assertTrue(job.reaped)
        self.assertTrue(job.log.closed)
        self.assertEqual(runtime.read_json(job.folder / "request.json"), {"action": "plan", "args": args})
        self.assertTrue((job.folder / "worker.log").is_file())
        self.assertEqual(job.process.returncode, 0)
        self.assertNotIn("shell", job.process.args)

    def test_cancel_keeps_owner_until_actual_exit_and_does_not_kill(self):
        job = self.session.start("serve", {"folder": "inspection"})
        with patch.object(job.process, "kill", side_effect=AssertionError("No kill")), \
                patch.object(job.process, "terminate", side_effect=AssertionError("No terminate")):
            self.session.stop_server()
            self.assertIn(job, self.session.retired)
            self.drain()
        self.assertTrue((job.folder / "cancel").is_file())
        self.assertTrue(job.process.stdin.closed)
        self.assertEqual(job.status["state"], "cancelled")

    def test_parent_eof_without_cancel_exits_and_is_reaped(self):
        job = self.session.start("serve", {"folder": "inspection"})
        job.process.stdin.close()
        self.drain()
        self.assertTrue((job.folder / "saw-eof").is_file())
        self.assertTrue(job.reaped)

    def test_cancel_marker_failure_still_closes_parent_pipe_and_reaps(self):
        job = self.session.start("serve", {"folder": "inspection"})
        original_touch = Path.touch
        def no_marker(path, *args, **kwargs):
            if path == job.folder / "cancel":
                raise PermissionError("test read-only recovery folder")
            return original_touch(path, *args, **kwargs)
        with patch.object(Path, "touch", no_marker):
            self.session.stop_server()
        self.drain()
        self.assertTrue((job.folder / "saw-eof").is_file())
        self.assertTrue(job.reaped)

    def test_decisions_are_owned_new_file_and_preserved_on_shutdown(self):
        decisions = {"schema": "polyweft.decisions.v1", "plan_id": "a" * 64,
                     "choices": {"vertex:1": "left"}}
        job = self.session.start("inspect", {"review": "r", "output": "o", "decisions": None,
                                              "blender": "app"}, decisions)
        request = runtime.read_json(job.folder / "request.json")
        path = Path(request["args"]["decisions"])
        self.assertEqual(path.parent, job.folder)
        self.assertEqual(runtime.read_json(path), decisions)
        self.session.shutdown()
        self.assertTrue(self.session.pending)
        self.drain()
        self.assertEqual(runtime.read_json(path), decisions)


class FinalStatusRaceTests(unittest.TestCase):
    def interleave(self, initial, final, *, cancel_requested=False):
        """Publish terminal status exactly after the parent's first status read."""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        folder = Path(self.temporary.name)
        status = folder / "status.json"
        if initial is not None:
            status.write_bytes(initial)
        class Process:
            stdin = io.StringIO()
            waited = 0
            def poll(inner):
                if final is not None:
                    pending = folder / "status.pending"
                    pending.write_bytes(final)
                    pending.replace(status)
                return 0
            def wait(inner):
                inner.waited += 1
                return 0
        process = Process()
        log = io.BytesIO()
        job = runtime.Job(folder, "prepare", {"output": "saved-copy"}, process, log)
        job.cancel_requested = cancel_requested
        session = runtime.Session(ROOT / "extension", folder, "never-executed")
        session.active = job
        finished = session.poll()
        self.assertIs(finished, job)
        self.assertIsNone(session.active)
        self.assertEqual(process.waited, 1)
        self.assertTrue(job.reaped)
        self.assertTrue(log.closed)
        self.assertTrue(process.stdin.closed)
        return job

    def test_terminal_publication_between_status_read_and_exit_is_adopted(self):
        final = {"state": "completed", "stage": "Verified prepare", "result": {
            "output": {"path": "saved-copy"}, "verified_fresh_reopen": True}}
        job = self.interleave(runtime.canonical({"state": "running", "stage": "Publishing"}),
                              runtime.canonical(final))
        self.assertEqual(job.status, final)

    def test_terminal_failed_cancelled_and_completion_after_cancel_keep_worker_semantics(self):
        for state in ("failed", "cancelled", "completed"):
            with self.subTest(state=state):
                final = {"state": state, "stage": "Final " + state}
                job = self.interleave(None, runtime.canonical(final), cancel_requested=True)
                self.assertEqual(job.status, final)

    def test_final_missing_running_or_malformed_status_is_never_completion(self):
        for final in (None, runtime.canonical({"state": "running", "stage": "Not done"}), b'{"bad":'):
            with self.subTest(final=final):
                job = self.interleave(None, final)
                self.assertEqual(job.status["state"], "failed")
                self.assertIn(job.status["stage"], {"Interface unavailable", "Worker exited without a final receipt"})

    def test_prior_malformed_interface_remains_a_failure_even_after_terminal_write(self):
        job = self.interleave(b'{"bad":', runtime.canonical({"state": "completed", "stage": "Saved"}))
        self.assertEqual(job.status["state"], "failed")
        self.assertEqual(job.status["stage"], "Interface unavailable")


class PackageTests(unittest.TestCase):
    def test_deterministic_zip_bundles_exact_engine_assets_license_and_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, second = (Path(temporary) / name for name in ("first.zip", "second.zip"))
            builder.build(ROOT, first)
            builder.build(ROOT, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertRaises(FileExistsError, builder.build, ROOT, first)
            with zipfile.ZipFile(first) as archive:
                self.assertIsNone(archive.testzip())
                names = archive.namelist()
                self.assertEqual(len(names), len(set(names)))
                self.assertTrue(all(not name.startswith("/") and ".." not in Path(name).parts for name in names))
                manifest = json.loads(archive.read("PACKAGE-MANIFEST.json"))
                self.assertEqual(set(manifest["files"]), set(names) - {"PACKAGE-MANIFEST.json"})
                for name, digest in manifest["files"].items():
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)
                for path in (ROOT / "src" / "polyweft").rglob("*"):
                    if path.is_file() and "__pycache__" not in path.parts:
                        self.assertEqual(archive.read("_engine/" + path.relative_to(ROOT / "src" / "polyweft").as_posix()), path.read_bytes())
                self.assertEqual(archive.read("LICENSE"), (ROOT / "LICENSE").read_bytes())
                self.assertNotIn("__pycache__", " ".join(names))

    def test_linked_engine_source_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / "extension", root / "extension", ignore=shutil.ignore_patterns("__pycache__"))
            (root / "src" / "polyweft").mkdir(parents=True)
            (root / "src" / "polyweft" / "linked.py").symlink_to(ROOT / "src" / "polyweft" / "core.py")
            shutil.copyfile(ROOT / "LICENSE", root / "LICENSE")
            self.assertRaisesRegex(ValueError, "Linked package", builder.package_files, root)


class Rows(list):
    def add(self):
        row = SimpleNamespace(choice="NONE")
        self.append(row)
        return row


class PanelStateTests(unittest.TestCase):
    """Exercise actual panel transitions with RNA replaced, never a Blender process."""

    def setUp(self):
        import copy
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.core = module("panel_test._engine.core", ROOT / "src" / "polyweft" / "core.py")
        props = ModuleType("bpy.props")
        for name in ("BoolProperty", "CollectionProperty", "EnumProperty", "IntProperty", "PointerProperty", "StringProperty"):
            setattr(props, name, lambda **kwargs: None)
        self.state = SimpleNamespace(base=str(self.root / "base.blend"), left=str(self.root / "left.blend"),
                                     right=str(self.root / "right.blend"), conflicts=Rows(),
                                     plan_current=False, inspection_current=False, accept_scope=False,
                                     busy=False, message="", recovery="", review_path="", last_output="")
        for name in ("base", "left", "right"):
            (self.root / (name + ".blend")).write_bytes(name.encode())
        timers = SimpleNamespace(is_registered=lambda fn: True, register=lambda *args, **kwargs: None)
        self.bpy = SimpleNamespace(context=SimpleNamespace(window_manager=SimpleNamespace(polyweft=self.state)),
                                   props=props, types=SimpleNamespace(PropertyGroup=object, Operator=object,
                                                                    Panel=object, UIList=object),
                                   path=SimpleNamespace(abspath=lambda text: str(Path(text).absolute())),
                                   app=SimpleNamespace(timers=timers, binary_path=sys.executable))
        engine = ModuleType("panel_test._engine")
        spec = importlib.util.spec_from_file_location("panel_test", ROOT / "extension" / "__init__.py",
                                                      submodule_search_locations=[str(ROOT / "extension")])
        self.panel = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"bpy": self.bpy, "bpy.props": props,
                                      "panel_test": self.panel, "panel_test._engine": engine,
                                      "panel_test._engine.core": self.core}):
            spec.loader.exec_module(self.panel)
        snapshot = {"name": "Target", "vertices": [{"id": 1, "co": [0, 0, 0]}],
                    "faces": [[1, 1, 1]], "uv_layers": {}, "material_values": {},
                    "guards": {"mesh_id": "mesh", "vertex_order": [1], "shape_keys": False},
                    "observed": {}}
        left, right = copy.deepcopy(snapshot), copy.deepcopy(snapshot)
        left["vertices"][0]["co"] = [1, 2, 3]
        right["vertices"][0]["co"] = [4, 5, 6]
        sources = {name: {"path": getattr(self.state, name),
                          "sha256": hashlib.sha256((self.root / (name + ".blend")).read_bytes()).hexdigest()}
                   for name in ("base", "left", "right")}
        self.plan = self.core.build_plan(sources, snapshot, left, right)
        self.review = self.root / "review"
        self.review.mkdir()
        (self.review / "plan.json").write_bytes(self.core.canonical(self.plan))
        self.job = SimpleNamespace(args={"output": str(self.review)})
        self.result = {"path": str(self.review), "plan_id": self.plan["id"]}

    def tearDown(self):
        self.temporary.cleanup()

    def load(self):
        self.panel._load_plan(self.job, self.result)

    def test_verified_recovery_whole_choices_and_stale_invalidation(self):
        self.load()
        self.assertTrue(self.state.plan_current)
        self.assertFalse(self.panel._complete(self.state))
        self.assertEqual(self.state.conflicts[0].left, "[1,2,3]")
        self.assertEqual(self.state.conflicts[0].right, "[4,5,6]")
        self.assertRaises(ValueError, self.panel._decisions, self.state)
        self.state.conflicts[0].choice = "left"
        decisions = self.panel._decisions(self.state)
        self.assertEqual(decisions["choices"], {"vertex:1": "left"})
        self.assertTrue(self.panel._complete(self.state))
        self.state.inspection_current = self.state.accept_scope = True
        stopped = []
        self.panel._session = SimpleNamespace(stop_server=lambda: stopped.append(True))
        self.panel._inspection = {"id": "old"}
        self.panel._choice_changed(self.state.conflicts[0], self.bpy.context)
        self.assertFalse(self.state.inspection_current)
        self.assertFalse(self.state.accept_scope)
        self.assertIsNone(self.panel._inspection)
        self.assertEqual(stopped, [True])
        Path(self.state.left).write_bytes(b"saved again")
        self.assertRaisesRegex(ValueError, "saved source changed", self.panel._decisions, self.state)
        self.assertFalse(self.state.plan_current)
        self.assertEqual(self.state.conflicts, [])

    def test_recovery_refuses_wrong_sources_tampered_plan_and_wrong_receipt(self):
        self.state.left = str(self.root / "other.blend")
        self.assertRaisesRegex(ValueError, "selected sources", self.load)
        self.state.left = str(self.root / "left.blend")
        self.result["plan_id"] = "0" * 64
        self.assertRaisesRegex(ValueError, "disagree", self.load)
        self.result["plan_id"] = self.plan["id"]
        self.plan["changes"][0]["left"] = [7, 8, 9]
        (self.review / "plan.json").write_bytes(self.core.canonical(self.plan))
        self.assertRaises(ValueError, self.load)
        self.assertFalse(self.state.plan_current)

    def test_metadata_only_change_does_not_refuse_verified_plan_or_stale_inspection(self):
        path = Path(self.state.left)
        before = path.stat()
        original_bytes = path.read_bytes()
        self.job.source_stamp = self.panel.runtime.source_stamp(self.panel._paths(self.state))
        path.chmod((before.st_mode & 0o777) ^ 0o100)
        after = path.stat()
        self.assertEqual((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns),
                         (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns))
        self.assertNotEqual(before.st_ctime_ns, after.st_ctime_ns)
        self.assertEqual(path.read_bytes(), original_bytes)
        self.load()
        self.assertTrue(self.state.plan_current)
        self.state.conflicts[0].choice = "left"
        self.state.inspection_current = True
        path.chmod(before.st_mode & 0o777)
        self.assertTrue(self.panel._decisions(self.state))
        self.assertTrue(self.state.inspection_current)

    def test_apply_preserves_inspection_scope_and_requires_matching_receipt(self):
        self.load()
        self.state.conflicts[0].choice = "right"
        self.state.inspection_current = self.state.accept_scope = True
        inspection = {"id": "inspection"}
        self.panel._inspection = inspection
        fake_job = SimpleNamespace(folder=self.root)
        self.panel._session = SimpleNamespace(start=lambda *args: fake_job,
                                               stop_server=lambda: self.fail("Apply must retain inspection"))
        self.panel._start("apply", {"output": "unused"})
        self.assertIs(self.panel._inspection, inspection)
        self.assertTrue(self.state.accept_scope)
        target = str(self.root / "merged.blend")
        fake_job.action, fake_job.args = "apply", {"output": target}
        fake_job.status = {"state": "completed", "stage": "Verified apply", "result": {
            "output": {"path": target}, "verified_fresh_reopen": True,
            "input_bytes_unchanged": True}}
        self.panel._finished(fake_job)
        self.assertEqual(self.state.last_output, target)
        fake_job.status["result"]["output"]["path"] = "unrelated"
        self.panel._finished(fake_job)
        self.assertIn("expected fresh-reopen receipt", self.state.message)

    def test_completed_interface_error_retains_honest_output_state(self):
        job = SimpleNamespace(folder=self.root, action="apply", args={"output": "output.blend"},
                              status={"state": "completed", "stage": "Output saved", "result": {
                                  "output": "output.blend", "interface_error": "too large"}})
        self.panel._finished(job)
        self.assertIn("Output completed", self.state.message)
        self.assertIn("Recovery:", self.state.message)
        self.assertFalse(self.state.busy)


if __name__ == "__main__":
    unittest.main()
