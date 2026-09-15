"""Headless Blender regression suite. Writes only to an explicit output folder."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy
from mathutils import Quaternion

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from pose_test_support import action, static, animated
from core.formats.lmt.model import LmtFile, LmtHeader
from core.formats.lmt.merge_writer import write_multi_merged_lmt_bytes
from core.formats.lmt.source_bank import LmtSourceBankCache
from core.formats.lmt.source_slots import export_source_slots
from blender_adapter.pose_helpers import create_evaluated_helper, load_helper_source, dispose_evaluated_helper
from blender_adapter.export_sampling import sample_action_for_lmt_export
from blender_adapter.fcurves import assign_action, ensure_armature_animation_data

OUT = Path(sys.argv[sys.argv.index('--')+1]).resolve()
OUT.mkdir(parents=True, exist_ok=False)


def expect_error(callback):
    try:
        callback()
    except ValueError:
        return
    raise AssertionError('Expected a ValueError')


data = bpy.data.armatures.new('source test skeleton')
template = bpy.data.objects.new('source template', data)
bpy.context.scene.collection.objects.link(template)
bpy.context.view_layer.objects.active = template
template.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
for index in (0,1,2):
    bone = data.edit_bones.new(f'BoneFunction.{index:03d}')
    bone.head, bone.tail = (0,index,0), (0,index+1,0)
    if index:
        bone.parent = data.edit_bones['BoneFunction.000']
bpy.ops.object.mode_set(mode='OBJECT')
template.pose.bones['BoneFunction.000'].constraints.new('LIMIT_LOCATION')
original_action = bpy.data.actions.new('Keep original action')
assign_action(ensure_armature_animation_data(template), original_action)
hierarchy = [(b.name, b.parent.name if b.parent else None, tuple(v for row in b.matrix_local for v in row)) for b in data.bones]

tracks = [static(0,0,(1.,0.,0.,0.)), animated(7), static(0,1), animated(4), animated(6,1),
          static(-1,3,(.6,.8,0.,0.)), static(-1,3,(.6,.8,0.,0.)),
          static(-1,4), animated(3,-1,4), static(-1,5), static(99,1)]
source_action = action(tracks)
source = LmtFile('synthetic', 100000, LmtHeader(b'LMT\0',95,1,bytes(8)), (32,), (source_action,))
raw = write_multi_merged_lmt_bytes(source,b'',{})
path = OUT/'synthetic.lmt'
path.write_bytes(raw)
cache = LmtSourceBankCache()
bank = cache.load(path)
helper = create_evaluated_helper(bank,0,template,base_policy='REST')
assert template.animation_data.action == original_action
assert len(template.pose.bones['BoneFunction.000'].constraints) == 1
assert not helper.armature.pose.bones['BoneFunction.000'].constraints
assert hierarchy == [(b.name,b.parent.name if b.parent else None,tuple(v for row in b.matrix_local for v in row)) for b in data.bones]
assert sample_action_for_lmt_export(helper.action,helper.armature).error_count == 1
assert export_source_slots(bank) == raw

frames = [0., .25, 4.5, 9.875, 10., 3.5, 0., 10.]
maximum = 0.
saved = {}
for frame in frames:
    evaluated = helper.set_frame(frame)
    expected = helper.evaluation.sample(frame)
    for (target, usage), value in expected.items():
        bone = evaluated.pose.bones[target or 'MHW_RootMotion']
        translation, rotation, scale = bone.matrix_basis.decompose()
        if usage in (0,3):
            actual, expected_q = rotation.to_matrix(), Quaternion(value).to_matrix()
            error = max(abs(a-b) for ra,rb in zip(actual,expected_q) for a,b in zip(ra,rb))
        else:
            actual = scale if usage == 2 else translation
            error = max(abs(a-b) for a,b in zip(actual,value))
        maximum = max(maximum,error)
        assert error < 3e-6, (frame,target,usage,error,tuple(rotation),value)
    saved[str(frame)] = {b.name:[float(x) for row in b.matrix for x in row] for b in evaluated.pose.bones}
expect_error(lambda: helper.set_frame(11))

# Native-record import variants and their raw actions must be different IDs.
again = create_evaluated_helper(bank,0,template,base_policy='REST')
assert again.action != helper.action and again.raw_action != helper.raw_action
assert again.action.name != helper.action.name and again.raw_action.name != helper.raw_action.name
partial_source = replace(source_action,header=replace(source_action.header,fcurve_count=1),tracks=(static(0,1,(8.,9.,10.)),))
partial_lmt = replace(bank.lmt,actions=(partial_source,))
partial_bank = replace(bank,lmt=partial_lmt)
partial = create_evaluated_helper(partial_bank,0,template,base_policy='ACTION',base_action=helper.action,create_raw_action=False)
for frame in (3.5,9.875,0.):
    posed = partial.set_frame(frame)
    assert tuple(posed.pose.bones['BoneFunction.000'].location) == (8.,9.,10.)
    reference = helper.armature.evaluated_get(bpy.context.evaluated_depsgraph_get())
    for name in ('BoneFunction.001','BoneFunction.002','MHW_RootMotion'):
        assert max(abs(a-b) for ra,rb in zip(posed.pose.bones[name].matrix_basis,reference.pose.bones[name].matrix_basis)
                   for a,b in zip(ra,rb)) < 1e-7
expect_error(lambda: create_evaluated_helper(bank,0,template,base_policy='ACTION',base_action=original_action))
objects_before, actions_before = len(bpy.data.objects), len(bpy.data.actions)
dispose_evaluated_helper(again)
assert len(bpy.data.objects) == objects_before-1 and len(bpy.data.actions) == actions_before-2
assert again.source_bank is None and again.evaluation is None

# Source replacement with unchanged size/time cannot silently reconnect a helper.
assert load_helper_source(helper.armature,cache).sha256 == bank.sha256
changed = bytearray(raw)
changed[8] ^= 1
path.write_bytes(changed)
expect_error(lambda: load_helper_source(helper.armature,cache))
path.write_bytes(raw)

helper_name = helper.armature.name
blend = OUT/'helpers.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(blend))
bpy.ops.wm.open_mainfile(filepath=str(blend))
reopened = bpy.data.objects[helper_name]
for frame, expected in saved.items():
    frame = float(frame)
    bpy.context.scene.frame_set(int(frame),subframe=frame-int(frame))
    evaluated = reopened.evaluated_get(bpy.context.evaluated_depsgraph_get())
    for name, values in expected.items():
        actual = [float(x) for row in evaluated.pose.bones[name].matrix for x in row]
        assert actual == values, (frame,name)
assert load_helper_source(reopened,cache).sha256 == bank.sha256
report = dict(blender=bpy.app.version_string, frame_samples=len(frames),
              maximum_matrix_or_vector_component_error=maximum, save_reopen='byte-identical sampled matrices',
              native_timing=[0,10], source_sha256=sha256(raw).hexdigest(),
              checks=['template untouched','unique evaluated/raw actions','subframe native sampler agreement',
                      'random access','explicit base pass-through','incomplete base rejected',
                      'evaluated export blocked','source replacement rejected','exact source roundtrip',
                      'explicit helper disposal releases owned resources'])
(OUT/'report.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
