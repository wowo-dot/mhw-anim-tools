"""Qualify native fixture helpers in Blender; no production writes or retargeting."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time

import bpy
from mathutils import Quaternion

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.formats.lmt.source_bank import LmtSourceBankCache
from core.formats.lmt.source_slots import export_source_slots
from core.formats.lmt.reader import read_lmt_bytes
from core.formats.lmt.semantics import get_usage_semantics
from blender_adapter.pose_helpers import create_evaluated_helper
from blender_adapter.space import TrackSpaceTarget, adapt_track_frames_for_target_space

OUT = Path(sys.argv[sys.argv.index('--')+1]).resolve()
OUT.mkdir(parents=True,exist_ok=False)
SOURCE = Path(r'D:\mh world modding\whole game extract\chunk')
preview = ROOT/'corpus_scans/duplicate_rules/eorzea_20260915/blender_preview/A_Visitor_from_Eorzea_TARGETS_RESEARCH.blend'
with bpy.data.libraries.load(str(preview),link=False) as (available, requested):
    requested.objects = ['Clip 2 - native hunter preview']
template = requested.objects[0]
assert template and template.type == 'ARMATURE'
collection = bpy.data.collections.new('Read-only template in test scene')
collection['~TYPE'] = 'MHW_MOD3_COLLECTION'
bpy.context.scene.collection.children.link(collection)
collection.objects.link(template)
template.animation_data_clear()
cache = LmtSourceBankCache()
idle = cache.load(SOURCE/'hm/common/mot/co00_00/co00_00.lmt')
base = create_evaluated_helper(idle,1,template,base_policy='REST',create_raw_action=False)
native_specs = [('evc0034',0),('evc0034',1),('evc0034',4),('evc0034',14),('evc0035',33),
                ('evc0021',20),('evc0014',14),('evc0074',2),('evc0074',3),('evc0074',5)]
specs=[dict(path=f'event/{event}/pl000_00/pl000_00.lmt',entry=entry,kind='duplicate') for event,entry in native_specs]
inspection = Path(r'D:\mh world modding\base body\Panam_MHW_Rebuild\experiments\Rig44\native_source_inspection.json')
specs += [dict(path=row['path'],entry=row['entry'],kind='ordinary')
          for row in json.loads(inspection.read_text())['clips'] if row['full_id'] in {363,12438,12439,8259}]
rows=[]
for spec in specs:
    started=time.perf_counter()
    bank=cache.load(SOURCE/spec['path'])
    helper=create_evaluated_helper(bank,spec['entry'],template,
        base_policy='ACTION' if 'evc0014' in spec['path'] else 'REST',
        base_action=base.action if 'evc0014' in spec['path'] else None)
    built=time.perf_counter()
    maximum_q=maximum_v=0.
    count=0
    native_end=helper.evaluation.source.header.frame_count-1
    # Every quarter frame, plus nonchronological repeats of boundaries/interior.
    frames=[i*.25 for i in range(native_end*4+1)] + [native_end,0.,native_end*.375]
    for frame in frames:
        posed=helper.set_frame(frame)
        for binding in helper.evaluation.bindings:
            name=binding.target or 'MHW_RootMotion'
            usage=get_usage_semantics(binding.usage)
            expected=adapt_track_frames_for_target_space(helper.armature,TrackSpaceTarget('bone',name),usage,
                [(frame,binding.curve.sample(frame))])[0][1]
            bone=posed.pose.bones[name]
            translation,rotation,scale=bone.matrix_basis.decompose()
            if binding.usage in (0,3):
                target=Quaternion(expected).to_matrix()
                actual=rotation.to_matrix()
                error=max(abs(a-b) for ra,rb in zip(actual,target) for a,b in zip(ra,rb))
                maximum_q=max(maximum_q,error)
                assert error<4e-6,(spec,frame,name,'quaternion',error)
            else:
                actual=scale if binding.usage==2 else translation
                error=max(abs(a-b) for a,b in zip(actual,expected))
                maximum_v=max(maximum_v,error)
                assert error<max(1e-5, max(abs(x) for x in expected)*4e-7),(spec,frame,name,'vector',error)
            count+=1
    sampled=time.perf_counter()
    original=export_source_slots(bank)
    assert original==bank.data and read_lmt_bytes(original,source_name=bank.lmt.source_name)==bank.lmt
    source_action=helper.evaluation.source
    slot=next(i for i,t in enumerate(source_action.tracks) if t.header.buffer_type==1 and t.header.usage==1)
    track=source_action.tracks[slot]
    values=list(track.header.basis)
    values[0]+=0.125
    replacement=replace(track,header=replace(track.header,basis=tuple(values)))
    edited=export_source_slots(bank,{spec['entry']:{slot:replacement}})
    assert edited==export_source_slots(bank,{spec['entry']:{slot:replacement}})
    finished=time.perf_counter()
    row=dict(**spec,source_sha256=bank.sha256,source_frames=native_end+1,quarter_frame_checks=len(frames),
             component_checks=count,max_rotation_matrix_component_error=maximum_q,max_translation_scale_component_error=maximum_v,
             exact_roundtrip=True,edited_slot=slot,edited_output_sha256=hashlib.sha256(edited).hexdigest(),
             seconds=dict(load_and_build=built-started,sample_and_compare=sampled-built,
                          source_export_readback_and_two_edited_audits=finished-sampled,total=finished-started))
    rows.append(row)
    print(json.dumps(row),flush=True)
    obj,act,rawact=helper.armature,helper.action,helper.raw_action
    rigdata=obj.data
    colls=list(obj.users_collection)
    bpy.data.objects.remove(obj,do_unlink=True)
    bpy.data.armatures.remove(rigdata)
    bpy.data.actions.remove(act)
    bpy.data.actions.remove(rawact)
    for c in colls:
        bpy.data.collections.remove(c)
report=dict(blender=bpy.app.version_string,cases=rows,source_cache=cache.stats(),
            timing_scope='Fixture qualification, includes exhaustive comparisons and repeated preservation audits; not a retarget bake benchmark')
(OUT/'report.json').write_text(json.dumps(report,indent=2))
