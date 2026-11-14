"""Polyweft's native, scene-independent Blender workflow panel."""

from pathlib import Path
import tempfile
import webbrowser

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty,
                       IntProperty, PointerProperty, StringProperty)

from . import runtime
from ._engine.core import SCOPE, resolve_decisions, verify_plan

_session = None
_plan = None
_review = None
_source_stamp = None
_inspection = None
_registered = False
_updating = False


def _state(context=None):
    context = context or bpy.context
    return getattr(context.window_manager, "polyweft", None)


def _redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _invalidate_inspection():
    global _inspection
    _inspection = None
    if _session:
        _session.stop_server()
    state = _state()
    if state:
        state.inspection_current = False
        state.accept_scope = False


def _choice_changed(self, context):
    if not _updating:
        _invalidate_inspection()


def _sources_changed(self, context):
    global _plan, _review, _source_stamp
    if _updating:
        return
    _invalidate_inspection()
    _plan = _review = _source_stamp = None
    state = _state(context)
    if state:
        state.conflicts.clear()
        state.plan_current = False
        state.message = "Sources changed. Create a new review."


def _paths(state):
    return tuple(bpy.path.abspath(value) if value else "" for value in
                 (state.base, state.left, state.right))


def _decisions(state):
    if not _plan or not state.plan_current:
        raise ValueError("Create a current review first")
    if runtime.source_stamp(_paths(state)) != _source_stamp:
        _sources_changed(state, bpy.context)
        raise ValueError("A saved source changed. Create a new review.")
    if _plan["blockers"]:
        raise ValueError("This review has structural blockers")
    choices = {row.key: row.choice for row in state.conflicts if row.choice != "NONE"}
    document = {"schema": "polyweft.decisions.v1", "plan_id": _plan["id"],
                "choices": choices}
    resolve_decisions(_plan, document)
    return document


def _complete(state):
    return bool(_plan and state.plan_current and not _plan["blockers"]
                and all(row.choice != "NONE" for row in state.conflicts))


def _driver():
    global _session
    if _session is None:
        root = bpy.utils.extension_path_user(__package__, path="jobs", create=True)
        python = runtime.bundled_python()
        _session = runtime.Session(Path(__file__).parent, root, python)
    return _session


def _artifact(name):
    driver = _driver()
    folder = Path(tempfile.mkdtemp(prefix="output-", dir=driver.jobs_root))
    return str(folder / name)


def _start(action, args, decisions=None):
    driver = _driver()
    if action in {"prepare", "plan", "inspect"}:
        _invalidate_inspection()
    job = driver.start(action, args, decisions)
    state = _state()
    state.recovery = str(job.folder)
    if action != "serve":
        state.busy = True
        state.message = "Starting " + action
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=.15, persistent=True)
    return job


def _load_plan(job, result):
    global _plan, _review, _source_stamp, _updating
    if type(result) is not dict or result.get("path") != runtime.output_identity(job.args["output"]):
        raise ValueError("Review receipt has an unexpected output path")
    raw_path = Path(result["path"]) / "plan.json"
    # Shared engine validation binds every captured value, source hash and change.
    plan = runtime.read_json(raw_path)
    verify_plan(plan)
    if result.get("plan_id") != plan["id"]:
        raise ValueError("Review receipt and saved plan disagree")
    state = _state()
    if getattr(job, "source_stamp", None) is not None and job.source_stamp != runtime.source_stamp(_paths(state)):
        raise ValueError("A saved source changed while creating the review")
    expected = dict(zip(("base", "left", "right"), _paths(state)))
    for side in expected:
        if Path(plan["sources"][side]["path"]).resolve() != Path(expected[side]).resolve():
            raise ValueError("Review no longer belongs to the selected sources")
    _plan, _review = plan, result["path"]
    _source_stamp = runtime.source_stamp(_paths(state))
    _updating = True
    try:
        state.conflicts.clear()
        for change in plan["changes"]:
            if change["kind"] == "conflict":
                row = state.conflicts.add()
                row.key, row.label = change["key"], change["label"]
                row.base = runtime.canonical(change["base"]).decode("ascii")
                row.left = runtime.canonical(change["left"]).decode("ascii")
                row.right = runtime.canonical(change["right"]).decode("ascii")
                row.choice = "NONE"
        state.conflict_index = 0
        state.plan_current = True
        state.review_path = _review
    finally:
        _updating = False
    state.message = "%d changes · %d competing values · %d blockers" % (
        len(plan["changes"]), len(state.conflicts), len(plan["blockers"]))


def _finished(job):
    global _inspection
    state = _state()
    status = job.status
    state.busy = False
    state.message = status["stage"]
    if status["state"] != "completed":
        state.message = status.get("error", status["stage"])
        return
    result = status.get("result")
    try:
        if type(result) is not dict or "interface_error" in result:
            raise ValueError("Output completed; interface unavailable. Open recovery folder for receipt/output.")
        if job.action == "plan":
            _load_plan(job, result)
        elif job.action == "inspect":
            decisions = _decisions(state)
            if (result.get("path") != runtime.output_identity(job.args["output"])
                    or result.get("plan_id") != _plan["id"]
                    or result.get("decisions") != decisions
                    or type(result.get("inspection_id")) is not str
                    or type(result.get("complete")) is not bool):
                raise ValueError("Inspection receipt does not match the current whole choices")
            _inspection = {"path": result["path"], "decisions": decisions,
                           "id": result["inspection_id"]}
            state.inspection_current = True
            state.message = ("Inspection ready. Open the four-state view before accepting scope."
                             if result["complete"] else
                             "Inspection has incomplete coverage. Review its limits in the four-state view.")
        elif job.action in {"prepare", "apply"}:
            output = result.get("output", {})
            if (type(output) is not dict or output.get("path") != runtime.output_identity(job.args["output"])
                    or result.get("verified_fresh_reopen") is not True):
                raise ValueError("Completed output lacks its expected fresh-reopen receipt")
            if job.action == "apply" and result.get("input_bytes_unchanged") is not True:
                raise ValueError("Completed merge lacks its source-byte preservation receipt")
            state.last_output = output["path"]
            state.message = "Verified saved copy: " + output["path"]
    except (ValueError, OSError, KeyError, TypeError) as error:
        state.message = str(error) + " Recovery: " + str(job.folder)


def _tick():
    if not _registered:
        return None
    try:
        driver = _session
        state = _state()
        if driver:
            server = driver.server
            finished = driver.poll()
            if finished:
                _finished(finished)
            state.busy = driver.active is not None
            if driver.active:
                state.message = ("Cancellation requested. Waiting for owned worker to exit."
                                 if driver.active.cancel_requested else driver.active.status["stage"])
            if server and driver.server is None and not server.cancel_requested:
                state.message = server.status.get("error", "Inspection server exited")
            if driver.server and not driver.server.browser_opened:
                result = driver.server.status.get("result")
                if type(result) is dict and "url" in result:
                    try:
                        url = runtime.readonly_url(result["url"])
                        if not _inspection or not state.inspection_current:
                            raise ValueError("Inspection is stale")
                        driver.server.browser_opened = True
                        if not webbrowser.open(url):
                            state.message = "Read-only view: " + url
                    except ValueError as error:
                        driver.stop_server()
                        state.message = str(error)
        if _plan and state.plan_current and runtime.source_stamp(_paths(state)) != _source_stamp:
            _sources_changed(state, bpy.context)
            state.message = "A saved source changed. Create a new review."
        _redraw()
    except Exception as error:
        state = _state()
        if state:
            state.message = "Workflow interface error: " + str(error)[:500]
        if _session:
            _session.shutdown()
    # Keep source invalidation active while a review exists, without a thread.
    return .25 if (_session and _session.pending) or _plan else None


class POLYWEFT_PG_conflict(bpy.types.PropertyGroup):
    key: StringProperty()
    label: StringProperty()
    base: StringProperty()
    left: StringProperty()
    right: StringProperty()
    choice: EnumProperty(name="Whole value", items=[
        ("NONE", "Choose…", "A choice is required"),
        ("base", "Ancestor", "Use the entire ancestor value"),
        ("left", "Left", "Use the entire left branch value"),
        ("right", "Right", "Use the entire right branch value")], update=_choice_changed)


class POLYWEFT_PG_state(bpy.types.PropertyGroup):
    prepare_source: StringProperty(name="Saved source", subtype="FILE_PATH")
    object_name: StringProperty(name="Mesh object", description="Exact object name in the saved source")
    prepared_output: StringProperty(name="Prepared copy", subtype="FILE_PATH")
    base: StringProperty(name="Ancestor", subtype="FILE_PATH", update=_sources_changed)
    left: StringProperty(name="Left branch", subtype="FILE_PATH", update=_sources_changed)
    right: StringProperty(name="Right / destination", subtype="FILE_PATH", update=_sources_changed)
    merged_output: StringProperty(name="Merged copy", subtype="FILE_PATH")
    accept_scope: BoolProperty(name="I accept this limited payload scope", default=False)
    conflicts: CollectionProperty(type=POLYWEFT_PG_conflict)
    conflict_index: IntProperty(default=0)
    busy: BoolProperty(default=False)
    plan_current: BoolProperty(default=False)
    inspection_current: BoolProperty(default=False)
    show_prepare: BoolProperty(name="Prepare before branching", default=True)
    message: StringProperty(default="Choose saved branches. Your active scene stays untouched.")
    recovery: StringProperty(subtype="DIR_PATH")
    review_path: StringProperty(subtype="DIR_PATH")
    last_output: StringProperty(subtype="FILE_PATH")


class POLYWEFT_UL_conflicts(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.label, icon="ERROR" if item.choice == "NONE" else "CHECKMARK")
        row.prop(item, "choice", text="")


class POLYWEFT_OT_action(bpy.types.Operator):
    bl_idname = "polyweft.action"
    bl_label = "Polyweft workflow"
    bl_description = "Run a guarded operation in a separately owned process"
    action: EnumProperty(items=[(value, value.title(), "") for value in
                                ("prepare", "plan", "reload", "inspect", "apply", "serve", "cancel", "stop")])

    def execute(self, context):
        state = _state(context)
        try:
            if self.action == "cancel":
                if _session and _session.active:
                    _session.active.cancel()
                    state.message = "Cancellation requested. Waiting for owned worker to exit."
                return {"FINISHED"}
            if self.action == "stop":
                if _session:
                    _session.stop_server()
                return {"FINISHED"}
            if state.busy:
                raise ValueError("Wait for the active worker to exit")
            blender = str(Path(bpy.app.binary_path).resolve(strict=True))
            if self.action == "prepare":
                args = {"source": bpy.path.abspath(state.prepare_source) if state.prepare_source else "",
                        "object_name": state.object_name,
                        "output": bpy.path.abspath(state.prepared_output) if state.prepared_output else "",
                        "blender": blender}
                _start("prepare", args)
            elif self.action == "plan":
                if not all(_paths(state)):
                    raise ValueError("Choose all three saved branches")
                _sources_changed(state, context)
                stamp = runtime.source_stamp(_paths(state))
                job = _start("plan", dict(zip(("base", "left", "right"), _paths(state)),
                                          output=_artifact("review"), blender=blender))
                job.source_stamp = stamp
            elif self.action == "reload":
                if not state.review_path or not all(_paths(state)):
                    raise ValueError("Select three sources and an existing review folder")
                review = str(Path(bpy.path.abspath(state.review_path)).resolve(strict=True))
                _sources_changed(state, context)
                from types import SimpleNamespace
                plan = runtime.read_json(Path(review) / "plan.json")
                _load_plan(SimpleNamespace(args={"output": review}),
                           {"path": review, "plan_id": plan.get("id")})
                state.message = "Review recovered. Choose whole values and create a fresh inspection."
            elif self.action == "inspect":
                decisions = _decisions(state)
                _start("inspect", {"review": _review, "output": _artifact("inspection"),
                                    "decisions": None, "blender": blender}, decisions)
            elif self.action == "apply":
                decisions = _decisions(state)
                if (not state.inspection_current or not _inspection
                        or _inspection["decisions"] != decisions):
                    raise ValueError("Inspect the current choices before saving")
                if not state.accept_scope:
                    raise ValueError("Accept the limited payload scope before saving")
                if not state.merged_output:
                    raise ValueError("Choose a new merged-copy path")
                _start("apply", {"review": _review,
                                  "output": bpy.path.abspath(state.merged_output),
                                  "decisions": None, "blender": blender,
                                  "accept_scope": True}, decisions)
            elif self.action == "serve":
                if not _inspection or not state.inspection_current:
                    raise ValueError("Inspect the current choices first")
                if _session and _session.server:
                    raise ValueError("The read-only inspection is already open; close it before reopening")
                _start("serve", {"folder": _inspection["path"]})
        except (ValueError, OSError, KeyError) as error:
            state.message = str(error)
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


def _button(layout, action, text, icon="NONE"):
    operator = layout.operator("polyweft.action", text=text, icon=icon)
    operator.action = action


def _wrapped(layout, text, width=46):
    # Wrap at words while retaining whole exact stored value strings below.
    import textwrap
    for line in textwrap.wrap(text, width=width) or [""]:
        layout.label(text=line)


class POLYWEFT_PT_workflow(bpy.types.Panel):
    bl_label = "Polyweft · Branch review"
    bl_idname = "POLYWEFT_PT_workflow"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Polyweft"

    def draw(self, context):
        state = _state(context)
        layout = self.layout
        layout.use_property_split = False
        layout.label(text="Saved files in. A verified new copy out.", icon="OUTLINER_OB_MESH")
        _wrapped(layout, "The active scene is never saved or replaced. Use trusted local files.")
        controls = layout.column()
        controls.enabled = not state.busy
        prep = controls.box()
        prep.prop(state, "show_prepare", icon="TRIA_DOWN" if state.show_prepare else "TRIA_RIGHT", emboss=False)
        if state.show_prepare:
            _wrapped(prep, "Prepare once, then make both branches from that saved copy.")
            prep.prop(state, "prepare_source")
            prep.prop(state, "object_name")
            prep.prop(state, "prepared_output")
            _button(prep, "prepare", "Prepare a new ancestor", "DUPLICATE")
        files = controls.box()
        files.label(text="1  Choose saved branches", icon="FILE_BLEND")
        files.prop(state, "base")
        files.prop(state, "left")
        files.prop(state, "right")
        _button(files, "plan", "Create branch review", "VIEWZOOM")
        files.prop(state, "review_path", text="Saved review")
        _button(files, "reload", "Reload saved review", "FILE_REFRESH")
        if state.plan_current and _plan:
            review = controls.box()
            review.label(text="2  Resolve competing whole values", icon="MOD_DATA_TRANSFER")
            for blocker in _plan["blockers"]:
                _wrapped(review, blocker["message"])
            if state.conflicts:
                selected = sum(row.choice != "NONE" for row in state.conflicts)
                review.label(text="%d / %d chosen" % (selected, len(state.conflicts)))
                review.template_list("POLYWEFT_UL_conflicts", "", state, "conflicts", state, "conflict_index", rows=4)
                row = state.conflicts[min(state.conflict_index, len(state.conflicts) - 1)]
                review.label(text=row.label)
                width = max(20, int(context.region.width / 7) - 8)
                for label, value in (("Ancestor", row.base), ("Left", row.left), ("Right", row.right)):
                    review.label(text=label)
                    _wrapped(review, value, width=width)
                review.prop(row, "choice", expand=True)
            elif not _plan["blockers"]:
                review.label(text="No competing values. Independent edits combine.", icon="CHECKMARK")
            for exclusion in _plan["observed_exclusions"]:
                _wrapped(review, exclusion)
            inspect = review.column()
            inspect.enabled = _complete(state)
            _button(inspect, "inspect", "Inspect these choices", "SHADING_SOLID")
            if state.inspection_current:
                review.label(text="Inspection matches current choices", icon="CHECKMARK")
                _button(review, "serve", "Open read-only four-state view", "URL")
            else:
                review.label(text="Inspection required for current choices", icon="INFO")
            save = controls.box()
            save.label(text="3  Save a verified merged copy", icon="FILE_TICK")
            _wrapped(save, SCOPE)
            save.prop(state, "accept_scope")
            save.prop(state, "merged_output")
            apply = save.column()
            apply.enabled = _complete(state) and state.inspection_current and state.accept_scope and bool(state.merged_output)
            _button(apply, "apply", "Verify and save new .blend", "FILE_TICK")
        status = layout.box()
        status.label(text="Working…" if state.busy else "Workflow status", icon="TIME" if state.busy else "INFO")
        _wrapped(status, state.message)
        if state.busy:
            _button(status, "cancel", "Cancel and wait", "CANCEL")
        if _session and _session.server:
            _button(status, "stop", "Close inspection server", "CANCEL")
        if state.recovery:
            status.prop(state, "recovery", text="Recovery")
            operator = status.operator("wm.path_open", text="Open recovery folder", icon="FILE_FOLDER")
            operator.filepath = state.recovery
        if state.last_output:
            status.prop(state, "last_output", text="Verified output")


_CLASSES = (POLYWEFT_PG_conflict, POLYWEFT_PG_state, POLYWEFT_UL_conflicts,
            POLYWEFT_OT_action, POLYWEFT_PT_workflow)


def register():
    global _registered
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.polyweft = PointerProperty(type=POLYWEFT_PG_state)
    _registered = True


def unregister():
    global _registered, _session, _plan, _review, _inspection, _source_stamp
    _registered = False
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    driver, _session = _session, None
    if driver:
        driver.shutdown()
        # The closure owns every unfinished process even after RNA classes disappear.
        # EOF/cancel lets the worker reap its own native child; never kill unknown PIDs.
        def reap_owned():
            driver.poll()
            return .1 if driver.pending else None
        if driver.pending:
            bpy.app.timers.register(reap_owned, first_interval=.1, persistent=True)
    if hasattr(bpy.types.WindowManager, "polyweft"):
        del bpy.types.WindowManager.polyweft
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    _plan = _review = _inspection = _source_stamp = None
