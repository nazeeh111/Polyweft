"""Owned-process lifecycle checks, without native scene or numerical fixtures."""

import os
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from polyweft.jobs import Cancelled, JobControl, controlled, checkpoint, publish
from polyweft.workflow import load_request


class JobTests(unittest.TestCase):
    def test_cancel_before_publication_leaves_destination_absent(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "result"
            control = JobControl(cancelled=lambda: True)
            with controlled(control), self.assertRaises(Cancelled):
                publish(lambda: destination.write_text("new"))
            self.assertFalse(destination.exists())

    def test_publication_wins_over_late_cancellation(self):
        cancelled = False
        control = JobControl(cancelled=lambda: cancelled)
        with controlled(control):
            publish(lambda: None)
            cancelled = True
            checkpoint("Writing receipt")
        self.assertTrue(control.published)

    def test_owned_child_is_reaped_on_cancel(self):
        started = time.monotonic()
        control = JobControl(cancelled=lambda: time.monotonic() - started > .15)
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "pid"
            script = "import os,time,pathlib;pathlib.Path(%r).write_text(str(os.getpid()));time.sleep(30)" % str(marker)
            with self.assertRaises(Cancelled):
                control.run([sys.executable, "-c", script], timeout=10)
            pid = int(marker.read_text())
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
        self.assertLess(time.monotonic() - started, 4)

    def test_deadline_reaps_child_and_retains_diagnostic_tail(self):
        control = JobControl(timeout=.2)
        with self.assertRaises(TimeoutError):
            control.run([sys.executable, "-c", "import time;time.sleep(30)"], timeout=10)
        result = JobControl().run([sys.executable, "-c", "print('diagnostic')"], timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"diagnostic", result.stdout)

    def test_owner_loss_cancels_before_child_launch(self):
        control = JobControl(owner_alive=lambda: False)
        with self.assertRaises(Cancelled):
            control.run(["/path/that/must/not/be/launched"], timeout=5)

    def test_no_control_preserves_normal_publication(self):
        called = []
        publish(lambda: called.append(True))
        self.assertEqual(called, [True])

    def test_receipt_error_after_publication_reports_output_not_failure(self):
        from polyweft.workflow import execute
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            output = folder / "published.blend"
            (folder / "request.json").write_text(json.dumps({"action": "prepare", "args": {
                "source": "source", "object_name": "mesh", "output": str(output), "blender": "blender"}}))
            def publish_then_fail(**kwargs):
                publish(lambda: output.write_bytes(b"published"))
                raise OSError("receipt failed")
            with patch("polyweft.workflow.prepare_source", publish_then_fail):
                execute(folder, owner_alive=lambda: True)
            status = json.loads((folder / "status.json").read_text())
            self.assertEqual(status["state"], "completed")
            self.assertIn("receipt failed", status["result"]["interface_error"])
            self.assertEqual(output.read_bytes(), b"published")

    def test_final_receipt_write_failure_preserves_published_outcome(self):
        from polyweft import workflow
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name); output = folder / "saved.blend"
            (folder / "request.json").write_text(json.dumps({"action": "prepare", "args": {
                "source": "source", "object_name": "mesh", "output": str(output), "blender": "blender"}}))
            def prepare(**kwargs):
                publish(lambda: output.write_bytes(b"published"))
                return {"output": {"path": str(output)}, "verified_fresh_reopen": True}
            original = workflow.write_status
            def fail_completed(folder, state, stage, **extra):
                if state == "completed": raise OSError("receipt unavailable")
                return original(folder, state, stage, **extra)
            execute = workflow.execute
            with patch.object(workflow, "prepare_source", prepare), patch.object(workflow, "write_status", fail_completed), \
                 patch.object(workflow, "execute", lambda folder: execute(folder, owner_alive=lambda: True)), \
                 patch.object(sys, "argv", ["workflow", name]), self.assertRaises(SystemExit) as exit_result:
                workflow.main()
            self.assertEqual(exit_result.exception.code, 3)
            self.assertNotEqual(json.loads((folder / "status.json").read_text())["state"], "failed")
            self.assertEqual(output.read_bytes(), b"published")

    def test_transient_final_receipt_failure_writes_recovery_status(self):
        from polyweft import workflow
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name); output = folder / "saved.blend"
            (folder / "request.json").write_text(json.dumps({"action": "prepare", "args": {
                "source": "source", "object_name": "mesh", "output": str(output), "blender": "blender"}}))
            def prepare(**kwargs):
                publish(lambda: output.write_bytes(b"published"))
                return {"output": {"path": str(output)}, "verified_fresh_reopen": True}
            original = workflow.write_status
            attempts = []
            def fail_once(folder, state, stage, **extra):
                if state == "completed" and not attempts:
                    attempts.append(True)
                    raise OSError("temporary receipt failure")
                return original(folder, state, stage, **extra)
            with patch.object(workflow, "prepare_source", prepare), patch.object(workflow, "write_status", fail_once):
                workflow.execute(folder, owner_alive=lambda: True)
            status = json.loads((folder / "status.json").read_text())
            self.assertEqual(status["state"], "completed")
            self.assertEqual(status["result"]["output"], str(output))
            self.assertIn("temporary receipt failure", status["result"]["interface_error"])

    def test_worker_rejects_unknown_actions_duplicate_keys_and_scope_types(self):
        requests = [
            '{"action":"python","args":{}}',
            '{"action":"serve","action":"serve","args":{"folder":"."}}',
            json.dumps({"action": "apply", "args": {"review": ".", "output": "new.blend", "decisions": None, "blender": "blender", "accept_scope": 1}}),
            json.dumps({"action": "serve", "args": {"folder": ".", "extra": "no"}}),
        ]
        with tempfile.TemporaryDirectory() as folder:
            for request in requests:
                (Path(folder) / "request.json").write_text(request)
                with self.subTest(request=request), self.assertRaises(ValueError):
                    load_request(Path(folder))

    def test_separate_server_worker_exits_on_parent_pipe_eof(self):
        import urllib.request
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            (folder / "index.html").write_text("inspection snapshot")
            (folder / "request.json").write_text(json.dumps({"action": "serve", "args": {"folder": name}}))
            child = subprocess.Popen([sys.executable, "-m", "polyweft.workflow", name],
                                     stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 5
                while True:
                    status = folder / "status.json"
                    doc = json.loads(status.read_text()) if status.exists() else {}
                    if doc.get("result", {}).get("url"):
                        break
                    if time.monotonic() > deadline or child.poll() is not None:
                        self.fail("Worker did not publish its owned server URL")
                    time.sleep(.03)
                url = doc["result"]["url"]
                self.assertTrue(url.endswith("/?readonly=1"))
                with urllib.request.urlopen(url, timeout=2) as response:
                    self.assertEqual(response.read(), b"inspection snapshot")
                child.stdin.close()
                child.wait(timeout=3)
                self.assertEqual(child.returncode, 2)
                self.assertEqual(json.loads(status.read_text())["state"], "cancelled")
                with self.assertRaises(OSError):
                    urllib.request.urlopen(url, timeout=.5)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()
                child.stderr.close()


if __name__ == "__main__":
    unittest.main()
