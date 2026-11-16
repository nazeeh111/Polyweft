"""Headless, task-owned installed-extension acceptance. Args: ZIP and new folder."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

import bpy

archive, root = map(lambda s: Path(s).resolve(), sys.argv[sys.argv.index('--') + 1:])
root.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_example import inside_blender
from blender_test_isolation import verify
verify(bpy, 'bl_ext.polyweft_accept.polyweft')

repo = bpy.context.preferences.extensions.repos.new(name='Polyweft acceptance', module='polyweft_accept', custom_directory=str(root / 'extensions'))
repo.use_remote_url = False
assert bpy.ops.extensions.package_install_files(filepath=str(archive), repo=repo.module, enable_on_install=True) == {'FINISHED'}
addon = importlib.import_module('bl_ext.polyweft_accept.polyweft')

def state():
    return bpy.context.window_manager.polyweft

def action(name):
    result = bpy.ops.polyweft.action(action=name)
    assert result == {'FINISHED'}, (name, result, state().message)

def wait(job, timeout=180):
    deadline = time.monotonic() + timeout
    while not job.reaped:
        addon._tick()
        if time.monotonic() > deadline:
            raise TimeoutError((job.action, job.status))
        time.sleep(.03)
    return job.status

def run(name):
    action(name)
    job = addon._workflow.driver.active
    status = wait(job)
    assert status['state'] == 'completed', (name, status, state().message)
    return job

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

inside_blender('raw', root)
s = state(); s.prepare_source = str(root/'raw.blend'); s.object_name = 'Tide'; s.prepared_output = str(root/'base.blend')
run('prepare')
# Fault the final receipt itself after a real native publication. Its durable
# output remains reopenable; retrying the same destination must not clobber it.
workflow = importlib.import_module('bl_ext.polyweft_accept.polyweft._engine.workflow')
native = importlib.import_module('bl_ext.polyweft_accept.polyweft._engine.native')
fault_job = root / 'receipt-fault-job'; fault_job.mkdir()
fault_output = root / 'receipt-fault.blend'
(fault_job / 'request.json').write_text(json.dumps({'action':'prepare','args':{
    'source':str(root/'raw.blend'),'object_name':'Tide','output':str(fault_output),'blender':bpy.app.binary_path}}))
original_status = workflow.write_status
def fault_completed(folder, status, stage, **extra):
    if status == 'completed': raise OSError('injected terminal receipt failure')
    return original_status(folder, status, stage, **extra)
with patch.object(workflow, 'write_status', fault_completed):
    try: workflow.execute(fault_job, owner_alive=lambda: True)
    except workflow.PublishedReceiptUnavailable: pass
    else: raise AssertionError('terminal receipt failure was not surfaced')
assert fault_output.is_file()
assert json.loads((fault_job/'status.json').read_text())['state'] != 'failed'
with bpy.data.libraries.load(str(fault_output)) as (available, requested):
    assert 'Tide' in available.objects
fault_hash = digest(fault_output)
try: native.prepare_source(root/'raw.blend', 'Tide', fault_output, bpy.app.binary_path)
except FileExistsError: pass
else: raise AssertionError('retry overwrote a published destination')
assert digest(fault_output) == fault_hash
# Cancel a real prepare while its Blender child is running, then repeat with
# owner-pipe EOF. Both must leave no published destination and reap the child.
cancel_evidence = []
for mode in ('cancel', 'owner_eof'):
    s = state(); s.prepared_output = str(root / (mode + '.blend'))
    action('prepare'); job = addon._workflow.driver.active
    deadline = time.monotonic() + 30
    children = []
    while not children and not job.reaped:
        lines = subprocess.check_output(['ps', '-A', '-o', 'pid=,ppid='], text=True).splitlines()
        children = [int(pid) for pid, ppid in (line.split() for line in lines) if int(ppid) == job.process.pid]
        if time.monotonic() > deadline: raise TimeoutError('No native child observed')
        if not children: time.sleep(.01)
    assert children, job.status
    if mode == 'cancel': job.cancel()
    else: job.process.stdin.close()
    assert wait(job)['state'] == 'cancelled', job.status
    assert not (root / (mode + '.blend')).exists()
    for pid in children:
        try: os.kill(pid, 0)
        except ProcessLookupError: pass
        else: raise AssertionError('Owned native child was not reaped: %d' % pid)
    cancel_evidence.append(mode)
inside_blender('left', root)
inside_blender('right', root)
s = state(); s.base, s.left, s.right = (str(root/(side+'.blend')) for side in ('base','left','right'))
before = {side:digest(root/(side+'.blend')) for side in ('base','left','right')}
run('plan')
s = state(); assert s.plan_current and len(s.conflicts) > 0, s.message
for row in s.conflicts: row.choice = 'left'
s.review_state_path = str(root/'review-choices.json'); action('save_review')
choices = {row.key: row.choice for row in s.conflicts}
# Drop all in-memory workflow authority before recovering the saved document.
assert bpy.ops.preferences.addon_disable(module='bl_ext.polyweft_accept.polyweft') == {'FINISHED'}
assert bpy.ops.preferences.addon_enable(module='bl_ext.polyweft_accept.polyweft') == {'FINISHED'}
addon = importlib.import_module('bl_ext.polyweft_accept.polyweft')
s = state(); s.base, s.left, s.right = (str(root/(side+'.blend')) for side in ('base','left','right'))
s.review_state_path = str(root/'review-choices.json')
action('reload'); job = addon._workflow.driver.active; assert wait(job)['state'] == 'completed', job.status
s = state(); assert s.plan_current and not s.inspection_current
assert {row.key:row.choice for row in s.conflicts} == choices
plan = addon._workflow.plan
decisions = {'schema': 'polyweft.decisions.v1', 'plan_id': plan['id'], 'choices': choices}
run('inspect'); s = state(); assert s.inspection_current, s.message
s.accept_scope = True; s.merged_output = str(root/'merged.blend'); action('apply')
job = addon._workflow.driver.active
# Request late cancellation once the actual published output is visible.
deadline = time.monotonic() + 180
while not (root/'merged.blend').exists() and not job.reaped:
    addon._tick()
    if time.monotonic() > deadline: raise TimeoutError(job.status)
    time.sleep(.01)
assert (root/'merged.blend').exists(), job.status
job.cancel()
assert wait(job)['state'] == 'completed', job.status
assert state().last_output == str(root/'merged.blend'), state().message
receipt = job.status['result']; assert receipt['verified_fresh_reopen'] and receipt['input_bytes_unchanged']
assert before == {side:digest(root/(side+'.blend')) for side in before}
# Reopen the published file independently in this Blender process and inspect destination data.
bpy.ops.wm.open_mainfile(filepath=str(root/'merged.blend'), use_scripts=False, load_ui=False)
assert bpy.context.scene.render.resolution_y == 820
objects = [obj for obj in bpy.data.objects if obj.get('branch_note') == 'Preserve destination note']
assert len(objects) == 1
assert objects[0].data.uv_layers.get('Surface UV') is not None
assert objects[0].data.materials[0].node_tree.nodes.get('Principled BSDF') is not None
core = importlib.import_module('bl_ext.polyweft_accept.polyweft._engine.core')
native = importlib.import_module('bl_ext.polyweft_accept.polyweft._engine.native')
actual = native.capture(bpy.app.binary_path, root/'merged.blend', plan['snapshots']['base']['guards']['mesh_id'], root/'independent-capture', root)
right = plan['snapshots']['right']
assert actual['guards'] == right['guards'] and actual['observed'] == right['observed'] and actual['name'] == right['name']
assert core.canonical({k:v['value'] for k,v in core.flatten(actual).items()}) == core.canonical(core.resolve_decisions(plan, decisions))
# Changed source rejection occurs in the real resume worker.
s = state(); s.base, s.left, s.right = (str(root/(side+'.blend')) for side in ('base','left','right')); s.review_state_path = str(root/'review-choices.json')
with (root/'left.blend').open('ab') as f: f.write(b'changed')
action('reload'); job = addon._workflow.driver.active; status = wait(job)
assert status['state'] == 'failed' and 'source bytes changed' in status.get('error','').lower(), status
assert not state().plan_current
print(json.dumps({'schema':'polyweft.installed-workflow.v1','blender':bpy.app.version_string,'choices':len(choices),'saved_review_reopened':True,'fresh_inspection':True,'fresh_reopen_receipt':True,'independent_payload_and_right_data':True,'source_hashes_unchanged_before_stale_test':True,'changed_source_refused':True,'late_cancel_completed':True,'receipt_failure_output_reopened_and_retry_refused':True,'native_child_cancellation':cancel_evidence,'merged_sha256':digest(root/'merged.blend')},sort_keys=True))
