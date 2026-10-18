"""Fixed local extension worker. Run outside Blender with its bundled Python."""

import os
import select
import sys
from pathlib import Path

from .core import canonical, strict_load
from .jobs import Cancelled, JobControl, controlled
from .native import apply_plan, create_plan, inspect_plan, prepare_source
from .server import create_server

MAX_REQUEST = 4 * 1024 * 1024
MAX_STATUS = 32 * 1024 * 1024
FIELDS = {
    "prepare": {"source", "object_name", "output", "blender"},
    "plan": {"base", "left", "right", "output", "blender"},
    "inspect": {"review", "output", "decisions", "blender"},
    "apply": {"review", "output", "decisions", "blender", "accept_scope"},
    "serve": {"folder"},
}


def load_request(folder):
    path = folder / "request.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_REQUEST:
        raise ValueError("Missing, linked or oversized workflow request")
    request = strict_load(path.read_bytes())
    if type(request) is not dict or set(request) != {"action", "args"}:
        raise ValueError("Invalid workflow request fields")
    action, args = request["action"], request["args"]
    if type(action) is not str or action not in FIELDS:
        raise ValueError("Unknown workflow action")
    if type(args) is not dict or set(args) != FIELDS[action]:
        raise ValueError("Invalid workflow action arguments")
    for key, value in args.items():
        if key == "accept_scope":
            if type(value) is not bool:
                raise ValueError("Payload scope acceptance must be explicit")
        elif key == "decisions" and value is None:
            continue
        elif type(value) is not str or not value or len(value) > 4096 or "\0" in value:
            raise ValueError("Invalid workflow text/path: " + key)
    return action, args


def write_status(folder, state, stage, **extra):
    raw = canonical({"state": state, "stage": stage, **extra}) + b"\n"
    if len(raw) > MAX_STATUS:
        raise ValueError("Workflow result exceeds the 32 MiB interface limit")
    temporary = folder / "status.pending"
    temporary.write_bytes(raw)
    os.replace(temporary, folder / "status.json")


def pipe_owner_alive():
    """The add-on alone owns the open write end; EOF means it has gone away."""
    ready, _, _ = select.select([sys.stdin.fileno()], [], [], 0)
    return not ready


def execute(folder, owner_alive=pipe_owner_alive):
    action, args = load_request(folder)
    control = JobControl(
        cancelled=lambda: (folder / "cancel").exists(),
        owner_alive=owner_alive,
        timeout=86400 if action == "serve" else 600,
        progress=lambda stage: write_status(folder, "running", stage),
    )
    with controlled(control):
        control.checkpoint("Starting " + action)
        if action == "serve":
            with create_server(args["folder"]) as server:
                server.timeout = .2
                url = f"http://127.0.0.1:{server.server_port}/?readonly=1"
                write_status(folder, "running", "Read-only inspection open", result={"url": url})
                while True:
                    control.checkpoint()
                    server.handle_request()
        functions = {"prepare": prepare_source, "plan": create_plan,
                     "inspect": inspect_plan, "apply": apply_plan}
        result = functions[action](**args)
        if action == "plan":
            result = {"path": args["output"], "plan_id": result["id"],
                      "changes": len(result["changes"]),
                      "conflicts": sum(c["kind"] == "conflict" for c in result["changes"]),
                      "blockers": result["blockers"]}
        elif action == "inspect":
            result = {"path": args["output"], "inspection_id": result["id"],
                      "plan_id": result["plan_id"], "complete": result["complete"],
                      "decisions": result["decisions"]}
        try:
            write_status(folder, "completed", "Verified " + action, result=result)
        except ValueError:
            # A UI size limit must not turn an already published output into a
            # false failure/cancellation. Retain its location for recovery.
            write_status(folder, "completed", "Output saved; interface result too large",
                         result={"output": args["output"],
                                 "interface_error": "Result exceeds the 32 MiB interface limit"})
        return result


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Expected an owned workflow job directory")
    folder = Path(sys.argv[1]).resolve(strict=True)
    if not folder.is_dir():
        raise SystemExit("Workflow job directory is missing")
    try:
        execute(folder)
    except Cancelled as error:
        write_status(folder, "cancelled", "Cancelled", error=str(error))
        raise SystemExit(2)
    except Exception as error:
        write_status(folder, "failed", "Operation failed", error=str(error)[-4000:])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
