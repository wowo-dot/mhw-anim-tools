"""Reproduce saved evc0074 root/body comparisons on CPU; research only.

Checks source/palette identities and fitted-time results without replaying the
RDC or trusting saved reconstructed matrices. This does not qualify runtime
timestamps, a universal duplicate rule, or Blender/retargeting accuracy.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import io
from itertools import product
import json
from pathlib import Path
import struct
import sys

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from core.formats.lmt.reader import read_lmt_bytes
from core.formats.lmt.decoder import decode_action_tracks
from verify_duplicate_runtime_evidence import digest, require, sample, qmatrix, rotation, angle

BANK_SHA = 'b5d1f5664cbbf9efcda4720966301ab851477f5d708baaba0d9a35116dc128c4'
BODY_SHA = 'bfdf5604a6d09892621df415bec1e06cd800d662888f8a31462d97e7fed42c64'
GEOMETRY_SHA = '3d7bc8d3d630b838850ac6347ad5edb56b0c5c7f4a938e97ae10343f29702434'
KEYS = [(-1,3),(-1,4),(-1,5),(0,0),(0,1),(0,2)]
NAMES = ['root_rotation','root_translation','root_scale','body0_rotation','body0_translation','body0_scale']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    research = PROJECT / 'corpus_scans'
    destination = args.output.resolve()
    require(destination.is_relative_to(research) and not destination.exists(),
            'Output must be new and under checkout/corpus_scans.')
    hashes = {}

    def read(path):
        path = Path(path).resolve()
        require(path.is_relative_to(research), 'Derived input outside research directory.')
        data = path.read_bytes()
        hashes[str(path.relative_to(PROJECT))] = digest(data)
        return data

    def js(path):
        return json.loads(read(path))

    analysis = js(args.analysis)
    require(analysis['status'] == 'complete' and not analysis['unavailable'], 'Incomplete analysis.')
    source = Path(analysis['source'])
    bank_blob = source.read_bytes()
    require(digest(bank_blob) == BANK_SHA == analysis['source_sha256'], 'Changed/wrong LMT fixture.')
    mesh_path = Path(analysis['geometry_source'])
    blob = mesh_path.read_bytes()
    require(digest(blob) == BODY_SHA == analysis['geometry_sha256'], 'Changed/wrong MOD3 fixture.')
    count = struct.unpack_from('<H', blob, 6)[0]
    require(count == 86, 'Unexpected skeleton size.')
    offset = struct.unpack_from('<Q', blob, 48)[0]
    infos = [struct.unpack_from('<HBB5f', blob, offset + i*24) for i in range(count)]
    parents = np.array([-1 if r[1] == 255 else r[1] for r in infos])
    at = offset + count*24
    local_bind = np.frombuffer(blob, '<f4', count*16, at).reshape(count,4,4).transpose(0,2,1).astype('f8')
    inverse_bind = np.frombuffer(blob, '<f4', count*16, at+count*64).reshape(count,4,4).transpose(0,2,1).astype('f8')
    world_bind = np.linalg.inv(inverse_bind)
    require(max(np.max(np.abs((local_bind[i] if p < 0 else world_bind[p] @ local_bind[i])-world_bind[i]))
                for i,p in enumerate(parents)) < 1e-5, 'Bind hierarchy mismatch.')
    bank = read_lmt_bytes(bank_blob, source_name=str(source))
    actions = {a.id:a for a in bank.actions if a.id < 300}
    decoded = {i:decode_action_tracks(a, strict=True) for i,a in actions.items()}
    draw_count, combination_count, sweep_count = 0, 0, 0
    max_position_delta, max_angle_delta = 0.0, 0.0
    sweep_rows = []
    capture_slices = set()
    for pose in analysis['poses']:
        extraction = js(pose['extraction'])
        require(extraction['status'] == 'complete' and extraction['extractor_version'] == 2,
                'Old or incomplete extraction.')
        geometry_blob = read(extraction['geometry'])
        require(digest(geometry_blob) == GEOMETRY_SHA == extraction['geometry_sha256'], 'Changed geometry map.')
        geometry = json.loads(geometry_blob)['sources'][1]
        require(geometry['sha256'] == BODY_SHA, 'Wrong body geometry.')
        functions = np.array([geometry['function_by_index'][str(i)] for i in range(count)])
        mapping = {int(f):i for i,f in enumerate(functions)}
        slices, evidence = [], []
        for draw in extraction['draws']:
            if not draw.get('palette') or not any(m['source_index'] == 1 and m['full_vertex_hash_matches']
                                                   for m in draw['vertex_matches']):
                continue
            raw = read(draw['palette']['path'])
            require(digest(raw) == draw['palette']['sha256'], 'Palette hash mismatch.')
            indices = [v['uint'][0] for block in draw['constants'] for v in block['values'] if v['name']=='iMatrixIndex']
            require(len(indices) == 1, 'Ambiguous palette index.')
            rows = np.frombuffer(raw, '<f4').reshape(-1,3,4)[indices[0]:indices[0]+count]
            require(rows.shape == (count,3,4) and np.isfinite(rows).all(), 'Invalid palette slice.')
            slices.append(rows.copy())
            evidence.append(dict(event=draw['event'],slice_sha256=digest(rows.tobytes()),
                matrix_index=indices[0],palette_sha256=draw['palette']['sha256']))
        require(slices and all(s.tobytes()==slices[0].tobytes() for s in slices), 'Matched draws disagree.')
        require(evidence == pose['draws'] and len(slices)==pose['matched_draws'], 'Reported draw evidence differs.')
        draw_count += len(slices)
        capture_slices.add(digest(slices[0].tobytes()))
        skin = np.tile(np.eye(4), (count,1,1))
        skin[:,:3] = slices[0]
        world = skin @ world_bind
        local = world.copy()
        for i,p in enumerate(parents):
            if p>=0:
                local[i] = np.linalg.inv(world[p]) @ world[i]
        with np.load(io.BytesIO(read(pose['local_pose'])), allow_pickle=False) as saved:
            for name,value in [('world',world),('local',local),('skin',skin),('all_joint_rows',np.stack(slices))]:
                require(np.allclose(saved[name], value, atol=1e-8, rtol=0), 'Saved reconstruction mismatch: '+name)
            require(np.array_equal(saved['functions'], functions) and np.array_equal(saved['parents'], parents),
                    'Saved skeleton mapping mismatch.')
        require(np.allclose(pose['observed_body0_world'], world[mapping[0]], atol=1e-8, rtol=0), 'Observed body transform differs.')
        entry, frame = pose['entry'], pose['source_frame']
        require(0 <= frame <= actions[entry].header.frame_count-1, 'Fitted frame outside native interval.')
        groups = defaultdict(list)
        for t in decoded[entry].tracks:
            groups[t.bone_id,t.usage].append(t)
        require(all(len(groups[f,0])==1 for f in range(5,13)), 'Duplicated/missing alignment anchor.')
        slerp = pose['interpolation']=='slerp'
        arm_angles = [angle(qmatrix(sample(groups[f,0][0],frame,slerp)),rotation(local[mapping[f],:3,:3])) for f in range(5,13)]
        angular_delta = float(np.max(np.abs(np.asarray(arm_angles)-pose['unique_arm_degrees'])))
        require(angular_delta < 1e-4, 'Arm comparison mismatch.')
        require(abs(float(np.sqrt(np.mean(np.square(arm_angles))))-pose['unique_arm_rms_degrees']) < 1e-4,
                'Arm RMS mismatch.')
        max_angle_delta = max(max_angle_delta, angular_delta)
        duplicates = [k for k in KEYS if len(groups[k])>1]
        require([list(k) for k in duplicates] == pose['duplicate_identities'], 'Duplicate identities differ.')
        require(all(len(groups[k])<=2 for k in KEYS), 'Unsupported fixture multiplicity.')
        expected_slots = {tuple(groups[k][i].track_index if groups[k] else None for k,i in zip(KEYS,indices))
                          for indices in product(*(range(max(1,len(groups[k]))) for k in KEYS))}
        actual_slots = [tuple(c['selected_source_slots'][name] for name in NAMES) for c in pose['candidates']]
        require(len(actual_slots)==len(set(actual_slots)) and set(actual_slots)==expected_slots, 'Missing/repeated candidate combination.')

        def predicted(candidate, time, use_slerp):
            slots = candidate['selected_source_slots']
            matrices = []
            for bone,start in [(-1,0),(0,3)]:
                result = np.eye(4) if bone==-1 else local_bind[mapping[bone]].copy()
                for component,transform in enumerate(('rotation','translation','scale')):
                    key, name = KEYS[start+component], NAMES[start+component]
                    slot = slots[name]
                    if slot is None:
                        continue
                    tracks = [t for t in groups[key] if t.track_index==slot]
                    require(len(tracks)==1, 'Incorrect source slot ownership.')
                    value = sample(tracks[0],time,use_slerp)
                    if transform=='rotation': result[:3,:3] = qmatrix(value)
                    elif transform=='translation': result[:3,3] = value[:3]
                    else: result[:3,:3] *= value[:3][None,:]
                matrices.append(result)
            return matrices[0] @ matrices[1]

        seen = world[mapping[0]]
        for candidate in pose['candidates']:
            value = predicted(candidate,frame,slerp)
            require(np.allclose(value,candidate['predicted_world'],atol=1e-8,rtol=0), 'Candidate transform mismatch.')
            position_error = float(np.linalg.norm(value[:3,3]-seen[:3,3]))
            orientation_error = angle(rotation(value[:3,:3]),rotation(seen[:3,:3]))
            delta = abs(position_error-candidate['position_error'])
            require(delta < 1e-7, 'Candidate position result mismatch.')
            require(abs(orientation_error-candidate['rotation_error_degrees']) < 1e-4, 'Candidate angle mismatch.')
            max_position_delta = max(max_position_delta,delta)
            max_angle_delta = max(max_angle_delta,abs(orientation_error-candidate['rotation_error_degrees']))
            combination_count += 1
        if duplicates:
            # Independently sample the stated sensitivity window. This uses
            # scalar sampling, separately from the vectorized analysis sweep.
            last = next(c for c in pose['candidates'] if c['choice']=='all_last')
            alternatives = [c for c in pose['candidates'] if c is not last]
            worst_later, best_alternative = 0.0, float('inf')
            for use_slerp in (False,True):
                for time in np.linspace(*pose['sensitivity']['time_range'],81):
                    later_error = float(np.linalg.norm(predicted(last,time,use_slerp)[:3,3]-seen[:3,3]))
                    other_errors = [float(np.linalg.norm(predicted(c,time,use_slerp)[:3,3]-seen[:3,3])) for c in alternatives]
                    require(later_error < min(other_errors), 'Later selection does not win sensitivity sample.')
                    worst_later = max(worst_later,later_error)
                    best_alternative = min(best_alternative,*other_errors)
                    sweep_count += 1
            sweep_rows.append(dict(frame=pose['render_frame'],entry=entry,all_samples_later_closer=True,
                                   worst_later_position_error=worst_later,best_alternative_position_error=best_alternative))
    require(digest(source.read_bytes())==BANK_SHA and digest(mesh_path.read_bytes())==BODY_SHA, 'Native source changed.')
    result = dict(status='verified',case='evc0074 / Innerwear 501 / 2026-09-15',captures=len(analysis['poses']),
        distinct_pose_slices=len(capture_slices),matched_draws=draw_count,candidate_combinations=combination_count,
        independent_sensitivity_times=sweep_count,sensitivity=sweep_rows,
        max_position_reproduction_difference=max_position_delta,max_angular_reproduction_difference_degrees=max_angle_delta,
        source_hashes=dict(lmt=BANK_SHA,mod3=BODY_SHA),input_hashes=hashes,
        verifier_sha256=digest(Path(__file__).read_bytes()),math_helper_sha256=digest((PROJECT/'tools/verify_duplicate_runtime_evidence.py').read_bytes()),
        limitation='Fitted-time comparisons, not game counters or a general duplicate rule. Zero/identity first records make some composition candidates coincide with later selection.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('input_hashes','sensitivity')}))


if __name__=='__main__':
    main()
