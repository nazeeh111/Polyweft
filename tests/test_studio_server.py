"""Actual HTTP boundaries of the local static review server."""

import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


class StudioServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        (cls.root / "index.html").write_text("<h1>Original review</h1>")
        (cls.root / "plan.json").write_text('{"scope":"local"}')
        (cls.root / "private.txt").write_text("Never served")
        (cls.root / "app.mjs").symlink_to(cls.root / "private.txt")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "from polyweft.server import serve; import sys; serve(sys.argv[1], int(sys.argv[2]))",
                str(cls.root),
                str(cls.port),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 10
        while True:
            if cls.process.poll() is not None:
                raise AssertionError(
                    "Studio failed: " + cls.process.communicate()[1].decode()
                )
            try:
                with urllib.request.urlopen(cls.base + "/", timeout=0.5) as response:
                    response.read()
                break
            except (OSError, urllib.error.URLError):
                if time.monotonic() > deadline:
                    cls.process.terminate()
                    cls.process.communicate(timeout=5)
                    raise AssertionError("Studio did not become available")
                time.sleep(0.03)

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.communicate(timeout=5)
        cls.temp.cleanup()

    def request(self, path, *, headers=None, method="GET"):
        return urllib.request.urlopen(
            urllib.request.Request(
                self.base + path, headers=headers or {}, method=method
            ),
            timeout=3,
        )

    def reject(self, path, status, **kwargs):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request(path, **kwargs)
        self.assertEqual(caught.exception.code, status)
        caught.exception.close()

    def test_serves_exact_static_plan_with_csp(self):
        with self.request("/plan.json") as response:
            self.assertEqual(response.read(), b'{"scope":"local"}')
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertIn(
                "frame-ancestors 'none'", response.headers["Content-Security-Policy"]
            )
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_private_paths_traversal_and_symlinks_refused(self):
        for path in [
            "/private.txt",
            "/../private.txt",
            "/%2e%2e/private.txt",
            "/app.mjs",
            "/request.json",
        ]:
            self.reject(path, 404)

    def test_mutation_and_foreign_host_origin_refused(self):
        self.reject("/plan.json", 405, method="POST")
        self.reject("/plan.json", 403, headers={"Host": "example.org"})
        self.reject("/plan.json", 403, headers={"Origin": "https://example.org"})
