# Original reproducible native render. Reads only explicit owned example files.
import hashlib
import json
import sys
from pathlib import Path

import bpy

args = sys.argv[sys.argv.index("--") + 1 :]
source = Path(args[0]).resolve()
output = Path(args[1]).resolve()
if output.exists():
    raise FileExistsError(str(output))
original = hashlib.sha256(source.read_bytes()).hexdigest()
bpy.ops.wm.open_mainfile(filepath=str(source), use_scripts=False, load_ui=False)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.denoising_use_gpu = False
scene.cycles.samples = 32
scene.render.resolution_x = 1100
scene.render.resolution_y = 860
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(output)
bpy.ops.render.render(write_still=True)
assert hashlib.sha256(source.read_bytes()).hexdigest() == original
print(
    json.dumps(
        {
            "source_sha256": original,
            "image_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "runtime": bpy.app.version_string,
            "source_unchanged": True,
        }
    )
)
