"""Explicit native inputs, bounded Blender bridge, fresh outputs only."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import __version__
from .core import SCOPE
from .native import apply_plan, create_plan, inspect_plan, prepare_source
from .server import serve


def main(argv=None):
    parser = argparse.ArgumentParser(prog="polyweft", description=SCOPE)
    parser.add_argument(
        "--version", action="version", version="Polyweft " + __version__
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("source")
    prepare.add_argument("--object", required=True)
    prepare.add_argument("--output", required=True)
    prepare.add_argument("--blender", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("base")
    plan.add_argument("left")
    plan.add_argument("right")
    plan.add_argument("--output", required=True)
    plan.add_argument("--blender", required=True)
    studio = sub.add_parser("studio")
    studio.add_argument("review")
    studio.add_argument("--port", type=int, default=0)
    inspection = sub.add_parser(
        "inspect", help="Compare native surface interference across four merge states"
    )
    inspection.add_argument("review")
    inspection.add_argument("--decisions")
    inspection.add_argument("--output", required=True)
    inspection.add_argument("--blender", required=True)
    apply = sub.add_parser("apply")
    apply.add_argument("review")
    apply.add_argument("--output", required=True)
    apply.add_argument("--decisions")
    apply.add_argument("--accept-payload-scope", action="store_true")
    apply.add_argument("--blender", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_source(args.source, args.object, args.output, args.blender)
        elif args.command == "plan":
            result = create_plan(
                args.base, args.left, args.right, args.output, args.blender
            )
            result = {
                "schema": "polyweft.plan.receipt.v1",
                "plan_id": result["id"],
                "changes": len(result["changes"]),
                "conflicts": sum(x["kind"] == "conflict" for x in result["changes"]),
                "blockers": result["blockers"],
                "review": str(Path(args.output).absolute()),
                "scope": SCOPE,
            }
        elif args.command == "studio":
            if not 0 <= args.port <= 65535:
                raise ValueError("Port must be 0..65535")
            serve(args.review, args.port)
            return 0
        elif args.command == "inspect":
            result = inspect_plan(
                args.review, args.output, args.decisions, args.blender
            )
        else:
            result = apply_plan(
                args.review,
                args.output,
                args.decisions,
                args.blender,
                args.accept_payload_scope,
            )
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, TimeoutError, subprocess.SubprocessError) as error:
        print("Polyweft: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
