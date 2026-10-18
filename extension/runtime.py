"""Blender-free process ownership and bounded interface for the native panel."""

import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

MAX_STATUS = 32 * 1024 * 1024
MAX_REQUEST = 4 * 1024 * 1024
STATES = {"running", "completed", "failed", "cancelled"}
FIELDS = {
    "prepare": {"source", "object_name", "output", "blender"},
    "plan": {"base", "left", "right", "output", "blender"},
    "inspect": {"review", "output", "decisions", "blender"},
    "apply": {"review", "output", "decisions", "blender", "accept_scope"},
    "serve": {"folder"},
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _number(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("Non-finite JSON number")
    return value


def read_json(path, limit=MAX_STATUS):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Interface file is missing or linked")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Interface exceeds its size limit")
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_float=_number,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              ValueError("Non-finite JSON number")))
    except (RecursionError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid interface JSON") from error


def write_new_json(path, value, limit=MAX_REQUEST):
    raw = canonical(value) + b"\n"
    if len(raw) > limit:
        raise ValueError("Interface exceeds its size limit")
    with Path(path).open("xb") as stream:
        stream.write(raw)


def read_status(path):
    value = read_json(path)
    if (type(value) is not dict or not {"state", "stage"} <= set(value)
            or set(value) - {"state", "stage", "result", "error"}
            or type(value["state"]) is not str or value["state"] not in STATES
            or type(value["stage"]) is not str or len(value["stage"]) > 4096
            or ("error" in value and (type(value["error"]) is not str
                                      or len(value["error"]) > 4000))):
        raise ValueError("Invalid workflow status fields")
    return value


def validate_request(action, args):
    if type(action) is not str or action not in FIELDS or type(args) is not dict or set(args) != FIELDS[action]:
        raise ValueError("Invalid workflow action or arguments")
    for key, value in args.items():
        if key == "accept_scope":
            if type(value) is not bool:
                raise ValueError("Scope acceptance must be explicit")
        elif key == "decisions" and value is None:
            continue
        elif type(value) is not str or not value or len(value) > 4096 or "\0" in value:
            raise ValueError("Invalid workflow argument: " + key)


def bundled_python(prefix=None, version=None):
    """Use only Blender's own standalone interpreter, never PATH or a download."""
    prefix = Path(sys.prefix if prefix is None else prefix)
    version = sys.version_info[:2] if version is None else version
    for name in (f"python{version[0]}.{version[1]}", "python3", "python"):
        candidate = prefix / "bin" / name
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            continue
        try:
            result = subprocess.run(
                [str(candidate), "-I", "-c",
                 "import sys; print('%d.%d' % sys.version_info[:2])"],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout.strip() == (
                "%d.%d" % tuple(version)).encode("ascii"):
            return str(candidate)
    raise ValueError("Blender's bundled standalone Python is unavailable or has a different version")


def readonly_url(value):
    if type(value) is not str or len(value) > 256:
        raise ValueError("Invalid inspection address")
    url = urlsplit(value)
    try:
        valid = (url.scheme == "http" and url.hostname == "127.0.0.1"
                 and url.port is not None and 0 < url.port < 65536
                 and url.username is None and url.password is None
                 and url.path == "/" and url.query == "readonly=1"
                 and not url.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Inspection address must be the owned read-only loopback server")
    return value


def source_stamp(paths):
    """Cheap content-change hint, not the engine's authoritative byte identity.

    ctime also changes for permissions and macOS last-used metadata, so it
    cannot identify saved edits. Engine hashing and recapture remain mandatory.
    """
    stamps = []
    for value in paths:
        path = Path(value)
        try:
            stat = path.stat()
            stamps.append((str(path), stat.st_dev, stat.st_ino,
                           stat.st_size, stat.st_mtime_ns))
        except OSError:
            stamps.append((str(path), None))
    return tuple(stamps)


def output_identity(value):
    """Match the engine's resolved parent without following an output leaf link."""
    path = Path(value)
    return str(path.parent.resolve() / path.name)


class Job:
    def __init__(self, folder, action, args, process, log):
        self.folder, self.action, self.args = folder, action, args
        self.process, self.log = process, log
        self.status = {"state": "running", "stage": "Starting " + action}
        self.interface_error = None
        self._stamp = None
        self.cancel_requested = False
        self.reaped = False
        self.browser_opened = False

    def cancel(self, close_pipe=False):
        self.cancel_requested = True
        try:
            (self.folder / "cancel").touch(exist_ok=True)
        except OSError:
            # If recovery storage disappeared or became read-only, EOF is still
            # an authenticated cancellation signal owned by this parent.
            close_pipe = True
        finally:
            if close_pipe and self.process.stdin and not self.process.stdin.closed:
                try:
                    self.process.stdin.close()
                except OSError:
                    pass

    def _read_status(self, *, final=False):
        path = self.folder / "status.json"
        try:
            stat = path.stat()
            stamp = (stat.st_size, stat.st_mtime_ns)
            if final or stamp != self._stamp:
                self.status = read_status(path)
                self._stamp = stamp
        except FileNotFoundError:
            pass
        except (OSError, ValueError, OverflowError) as error:
            self.interface_error = str(error)
            self.cancel()

    def poll(self):
        if self.reaped:
            return True
        self._read_status()
        code = self.process.poll()
        if code is not None and not self.reaped:
            self.process.wait()
            # Atomic terminal publication can occur after our preceding read
            # but before poll reports exit. After wait, reread without caching
            # before deciding that the worker omitted its final receipt.
            self._read_status(final=True)
            self.reaped = True
            if self.process.stdin and not self.process.stdin.closed:
                self.process.stdin.close()
            self.log.close()
            if self.interface_error:
                self.status = {"state": "failed", "stage": "Interface unavailable",
                               "error": self.interface_error}
            elif self.status["state"] == "running":
                self.status = {"state": "failed", "stage": "Worker exited without a final receipt",
                               "error": "Inspect the retained job folder (exit %s)" % code}
        return self.reaped


class Session:
    def __init__(self, extension, jobs_root, python):
        self.extension, self.jobs_root = Path(extension), Path(jobs_root)
        self.python = python
        self.active = None
        self.server = None
        self.retired = []

    def start(self, action, args, decisions=None):
        if action == "serve":
            if self.server is not None:
                raise ValueError("The previous inspection server is still owned")
        elif self.active is not None:
            raise ValueError("Wait for the active worker to exit")
        validate_request(action, args)
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix=action + "-", dir=self.jobs_root))
        args = dict(args)
        if decisions is not None:
            if action not in {"inspect", "apply"}:
                raise ValueError("This action does not accept choices")
            choice_path = folder / "decisions.json"
            write_new_json(choice_path, decisions)
            args["decisions"] = str(choice_path)
        write_new_json(folder / "request.json", {"action": action, "args": args})
        log = (folder / "worker.log").open("xb")
        try:
            process = subprocess.Popen(
                [self.python, "-I", str(self.extension / "worker_entry.py"), str(folder)],
                stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                cwd=str(folder), close_fds=True)
        except BaseException:
            log.close()
            raise
        job = Job(folder, action, args, process, log)
        if action == "serve":
            self.server = job
        else:
            self.active = job
        return job

    def stop_server(self):
        if self.server:
            self.server.cancel(close_pipe=True)
            self.retired.append(self.server)
            self.server = None

    def poll(self):
        complete = None
        if self.active and self.active.poll():
            complete, self.active = self.active, None
        if self.server and self.server.poll():
            self.retired.append(self.server)
            self.server = None
        self.retired[:] = [job for job in self.retired if not job.poll()]
        return complete

    def shutdown(self):
        if self.active:
            self.active.cancel(close_pipe=True)
            self.retired.append(self.active)
            self.active = None
        self.stop_server()

    @property
    def pending(self):
        return bool(self.active or self.server or self.retired)
