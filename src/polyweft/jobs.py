"""Cooperative cancellation for a separately owned workflow process.

No Blender Python threads. Only children created here are stopped and reaped.
Publication is the commit point: later cancellation cannot undo a saved output.
"""

import subprocess
import tempfile
import time
from contextlib import contextmanager
from contextvars import ContextVar

_current = ContextVar("polyweft_job", default=None)


class Cancelled(RuntimeError):
    pass


class JobControl:
    def __init__(self, *, cancelled=lambda: False, owner_alive=lambda: True,
                 timeout=600, progress=lambda stage: None):
        self.cancelled = cancelled
        self.owner_alive = owner_alive
        self.deadline = time.monotonic() + timeout
        self.progress = progress
        self.published = False

    def checkpoint(self, stage=None):
        if self.published:
            return
        if self.cancelled() or not self.owner_alive():
            raise Cancelled("Cancelled before output publication")
        if time.monotonic() >= self.deadline:
            raise TimeoutError("Workflow exceeded its job deadline")
        if stage:
            self.progress(stage)

    def publish(self, action):
        self.checkpoint("Publishing verified output")
        result = action()
        self.published = True
        return result

    def run(self, command, *, timeout, **kwargs):
        self.checkpoint("Running isolated Blender operation")
        deadline = min(self.deadline, time.monotonic() + timeout)
        # Native logs stay on disk while running; only the bounded tail is read.
        with tempfile.TemporaryFile() as log:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, **kwargs)
            try:
                while child.poll() is None:
                    self.checkpoint()
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Isolated Blender operation exceeded its deadline")
                    time.sleep(.05)
                self.checkpoint()
            finally:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                else:
                    child.wait()
            log.seek(0, 2)
            log.seek(max(0, log.tell() - 65536))
            return subprocess.CompletedProcess(command, child.returncode, log.read())


@contextmanager
def controlled(control):
    token = _current.set(control)
    try:
        yield
    finally:
        _current.reset(token)


def checkpoint(stage=None):
    control = _current.get()
    if control:
        control.checkpoint(stage)


def publish(action):
    control = _current.get()
    return control.publish(action) if control else action()


def run_native(command, **kwargs):
    control = _current.get()
    if control:
        return control.run(command, **kwargs)
    return subprocess.run(command, check=False, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
