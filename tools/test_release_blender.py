"""Load and exercise the packaged UI without installing it."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import zipfile

import bpy

args=sys.argv[sys.argv.index('--')+1:]
package,out=map(lambda value:Path(value).resolve(),args)
out.mkdir(parents=True,exist_ok=False)
with zipfile.ZipFile(package) as archive:
    for name in archive.namelist():
        assert name.startswith('mhw_anim_tools/') and '..' not in Path(name).parts
    archive.extractall(out)
manifest=json.loads((out/'mhw_anim_tools/BUILD_MANIFEST.json').read_text())
for name,digest in manifest['files'].items():
    assert hashlib.sha256((out/'mhw_anim_tools'/name).read_bytes()).hexdigest()==digest
sys.path.insert(0,str(out))
addon=importlib.import_module('mhw_anim_tools')
assert Path(addon.__file__).resolve()==out/'mhw_anim_tools/__init__.py'
addon.register()
from mhw_anim_tools.core.formats.lmt.model import LmtHeader,LmtFile,LmtActionHeader,LmtAction,LmtTrackHeader,LmtTrack
from mhw_anim_tools.core.formats.lmt.merge_writer import write_multi_merged_lmt_bytes

data=bpy.data.armatures.new('UI test')
rig=bpy.data.objects.new('UI test',data)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active=rig
rig.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
bone=data.edit_bones.new('BoneFunction.000')
bone.head,bone.tail=(0,0,0),(0,1,0)
bpy.ops.object.mode_set(mode='OBJECT')
track=LmtTrack(LmtTrackHeader(1,1,0,205,0,1.,0,0,(1.,2.,3.,0.),0),b'')
header=LmtActionHeader(0,0,1,1,-1,(0,0,0),(0.,0.,0.,0.),(0.,0.,0.,1.),0,bytes(2),0,(0,0,0,0,0),0)
lmt=LmtFile('test',1024,LmtHeader(b'LMT\0',95,1,bytes(8)),(32,),(LmtAction(header,(track,)),))
source=out/'ui_test.lmt'
source.write_bytes(write_multi_merged_lmt_bytes(lmt,b'',{}))
props=bpy.context.scene.mhw_anim_tools
props.target_armature=rig
assert bpy.ops.mhw_anim_tools.inspect_lmt(filepath=str(source))=={'FINISHED'}
assert bpy.ops.mhw_anim_tools.build_pose_helper(base_policy='REST')=={'FINISHED'}
helper=bpy.context.view_layer.objects.active
assert helper!=rig and helper.get('mhw_anim_tools_pose_rule')
assert tuple(helper.animation_data.action.frame_range)==(0.,0.)
assert tuple(helper.pose.bones['BoneFunction.000'].location)==(1.,2.,3.)
addon.unregister()
report=dict(package_sha256=hashlib.sha256(package.read_bytes()).hexdigest(),blender=bpy.app.version_string,
            version=manifest['version'],checks=['manifest verified','package loaded without install','register/unregister',
                                              'inspector and helper UI operators','one-frame native range'])
(out/'package_test.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
