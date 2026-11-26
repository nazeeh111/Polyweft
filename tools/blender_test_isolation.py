"""Refuse test execution unless Blender user resources are task-local."""
import os
from pathlib import Path


def verify(bpy, extension_module):
    root = Path(os.environ['POLYWEFT_ISOLATION_ROOT']).resolve(strict=True)
    for name in ('BLENDER_USER_RESOURCES', 'BLENDER_USER_CONFIG', 'BLENDER_USER_SCRIPTS',
                 'BLENDER_USER_EXTENSIONS', 'BLENDER_USER_DATAFILES', 'TMPDIR'):
        path = Path(os.environ[name]).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError(name + ' must be inside POLYWEFT_ISOLATION_ROOT')
    jobs = Path(bpy.utils.extension_path_user(extension_module, path='jobs', create=False)).resolve()
    if not jobs.is_relative_to(root):
        raise ValueError('Blender extension jobs would escape task-local resources: ' + str(jobs))
    return jobs
