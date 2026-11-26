"""Fixed local extension worker. Run outside Blender with its bundled Python."""

import os
import select
import sys
from pathlib import Path

from .core import canonical, load_json_file, verify_plan
from .jobs import Cancelled, JobControl, controlled
from .native import apply_plan, create_plan, inspect_plan, prepare_source, source_info
from .server import create_server

from .protocol import MAX_REQUEST, MAX_STATUS, validate_request


class PublishedReceiptUnavailable(RuntimeError):
    """Publication succeeded but no terminal status could be stored."""


def published_without_receipt(folder, output, error):
    try:
        write_status(folder, "completed", "Output published; receipt unavailable",
                     result={"output": output, "interface_error": str(error)[-4000:]})
    except (OSError, ValueError) as fallback_error:
        raise PublishedReceiptUnavailable(
            "Output was published at %s; terminal receipt unavailable: %s" % (output, fallback_error)
        ) from fallback_error


def load_request(folder):
    path = folder / "request.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_REQUEST:
        raise ValueError("Missing, linked or oversized workflow request")
    request = load_json_file(path, MAX_REQUEST)
    if type(request) is not dict or set(request) != {"action", "args"}:
        raise ValueError("Invalid workflow request fields")
    action, args = request["action"], request["args"]
    validate_request(action, args)
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


def resume_review(base, left, right, document):
    path = Path(document)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_REQUEST:
        raise ValueError("Missing, linked or oversized review choices")
    state = load_json_file(path, MAX_REQUEST)
    if type(state) is not dict or set(state) != {"schema", "review", "plan_id", "choices"} or state["schema"] != "polyweft.review-state.v1":
        raise ValueError("Invalid saved review choices")
    if type(state["review"]) is not str or type(state["choices"]) is not dict:
        raise ValueError("Invalid saved review choices")
    review = Path(state["review"]).resolve(strict=True)
    plan_path = review / "plan.json"
    if plan_path.is_symlink() or not plan_path.is_file() or plan_path.stat().st_size > MAX_STATUS:
        raise ValueError("Missing, linked or oversized review plan")
    plan = load_json_file(plan_path, MAX_STATUS)
    verify_plan(plan)
    if plan["id"] != state["plan_id"]:
        raise ValueError("Saved choices and review disagree")
    for side, selected in zip(("base", "left", "right"), (base, left, right)):
        if source_info(selected) != plan["sources"][side]:
            raise ValueError("Review source bytes changed or selected source differs")
    conflicts = {c["key"] for c in plan["changes"] if c["kind"] == "conflict"}
    if set(state["choices"]) - conflicts or any(value not in ("base", "left", "right") for value in state["choices"].values()):
        raise ValueError("Invalid saved whole-value choices")
    return {"path": str(review), "plan_id": plan["id"], "choices": state["choices"]}


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
        functions = {"prepare": prepare_source, "plan": create_plan, "resume": resume_review,
                     "inspect": inspect_plan, "apply": apply_plan}
        try:
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
            write_status(folder, "completed", "Verified " + action, result=result)
        except Exception as error:
            if not control.published or action not in {"prepare", "plan", "inspect", "apply"}:
                raise
            # A publication cannot be undone by a receipt or later operation failure.
            published_without_receipt(folder, args["output"], error)
            return None
        return result


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Expected an owned workflow job directory")
    folder = Path(sys.argv[1]).resolve(strict=True)
    if not folder.is_dir():
        raise SystemExit("Workflow job directory is missing")
    try:
        execute(folder)
    except PublishedReceiptUnavailable as error:
        print(str(error), file=sys.stderr, flush=True)
        raise SystemExit(3)
    except Cancelled as error:
        write_status(folder, "cancelled", "Cancelled", error=str(error))
        raise SystemExit(2)
    except Exception as error:
        write_status(folder, "failed", "Operation failed", error=str(error)[-4000:])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
