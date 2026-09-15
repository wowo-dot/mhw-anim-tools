"""Recheck the 2026-09-15 evc0034 capture analysis against saved source data.

This is a case-specific CPU research utility, outside add-on execution. It
requires system Python with NumPy and the local capture-analysis files. It
verifies fitted-time comparisons; it does not establish authoritative game
timestamps or install a duplicate-resolution rule.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import struct
import sys

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from core.formats.lmt.decoder import decode_action_tracks
from core.formats.lmt.reader import read_lmt_file

BANK_SHA = 'db0fba34294e47e0539d81bc36d919f7f8ba160922e389c92516df08da70b5bc'
BODY_SHA = 'bfdf5604a6d09892621df415bec1e06cd800d662888f8a31462d97e7fed42c64'


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sample(track, frame, slerp):
    if not track.keyframes:
        return np.asarray(track.basis_value, dtype='f8')
    times = np.asarray([k.frame for k in track.keyframes])
    values = np.asarray([k.value for k in track.keyframes], dtype='f8')
    quat = track.usage in (0, 3)
    if quat:
        values /= np.linalg.norm(values, axis=1, keepdims=True)
        for i in range(1, len(values)):
            if values[i] @ values[i - 1] < 0:
                values[i] *= -1
    left = max(0, int(np.searchsorted(times, frame, side='right')) - 1)
    right = min(len(times) - 1, left + 1)
    alpha = np.clip((frame - times[left]) / max(1, times[right] - times[left]), 0, 1)
    a, b = values[left], values[right]
    angle = np.arccos(np.clip(a @ b, -1, 1)) if quat else 0.0
    sine = np.sin(angle)
    if slerp and quat and sine >= 1e-6:
        result = (np.sin((1 - alpha) * angle) * a + np.sin(alpha * angle) * b) / sine
    else:
        result = (1 - alpha) * a + alpha * b
    return result / np.linalg.norm(result) if quat else result


def qmatrix(q):
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def rotation(m):
    u, _, v = np.linalg.svd(m)
    result = u @ v
    require(np.linalg.det(result) > 0, 'Reflected rotation.')
    return result


def angle(a, b):
    return float(np.rad2deg(np.arccos(np.clip((np.sum(a*b)-1)*0.5, -1, 1))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    research = PROJECT / 'corpus_scans'
    runtime = args.runtime.resolve()
    destination = args.output.resolve()
    require(runtime.is_relative_to(research) and destination.is_relative_to(research),
            'Research input/output must be under this checkout/corpus_scans.')
    require(not destination.exists(), 'Output already exists; choose a new file.')
    input_hashes = {}

    def read(path):
        path = Path(path).resolve()
        require(path.is_relative_to(research), 'Derived input outside research directory.')
        blob = path.read_bytes()
        input_hashes[str(path.relative_to(PROJECT))] = digest(blob)
        return blob

    def js(path):
        return json.loads(read(path))

    index = js(runtime / 'native_pose_index.json')
    fit = js(runtime / 'duplicate_candidate_comparison.json')
    coarse = js(runtime / 'alignment_coarse.json')
    root_report = js(runtime / 'root_candidate_comparison.json')
    source = Path(coarse['source'])
    require(digest(source.read_bytes()) == BANK_SHA, 'Unexpected/changed LMT fixture.')
    skeleton_path = Path(index['skeleton_source'])
    blob = skeleton_path.read_bytes()
    require(digest(blob) == BODY_SHA == index['skeleton_sha256'], 'Changed skeleton.')
    count = struct.unpack_from('<H', blob, 6)[0]
    offset = struct.unpack_from('<Q', blob, 48)[0]
    require(count == 86, 'Unexpected skeleton size.')
    infos = [struct.unpack_from('<HBB5f', blob, offset+i*24) for i in range(count)]
    parents = np.array([-1 if row[1] == 255 else row[1] for row in infos])
    matrix_offset = offset + count*24
    local_bind = np.frombuffer(blob, '<f4', count*16, matrix_offset).reshape(count, 4, 4).transpose(0, 2, 1).astype('f8')
    inverse_bind = np.frombuffer(blob, '<f4', count*16, matrix_offset+count*64).reshape(count, 4, 4).transpose(0, 2, 1).astype('f8')
    world_bind = np.linalg.inv(inverse_bind)
    require(max(np.max(np.abs((local_bind[i] if p < 0 else world_bind[p] @ local_bind[i])-world_bind[i]))
                for i, p in enumerate(parents)) < 1e-5, 'Bind hierarchy mismatch.')

    # Verify palette hashes, per-pass equality, source geometry, and the saved
    # reconstruction before looking at any duplicate candidate result.
    poses, functions, draw_count = {}, None, 0
    for entry in index['poses']:
        report = js(entry['extraction'])
        require(report['status'] == 'complete' and report.get('extractor_version', 0) >= 2,
                'Incomplete/old extraction.')
        geometry_blob = read(report['geometry'])
        require(digest(geometry_blob) == report['geometry_sha256'], 'Changed geometry report.')
        geometry = json.loads(geometry_blob)['sources'][1]
        require(geometry['sha256'] == BODY_SHA, 'Unexpected geometry source.')
        these_functions = np.array([geometry['function_by_index'][str(i)] for i in range(count)])
        require(functions is None or np.array_equal(functions, these_functions), 'Different function mapping.')
        functions = these_functions
        slices = []
        for draw in report['draws']:
            if not draw.get('palette') or not any(m['source_index'] == 1 and m['full_vertex_hash_matches']
                                                  for m in draw['vertex_matches']):
                continue
            raw = read(draw['palette']['path'])
            require(digest(raw) == draw['palette']['sha256'], 'Changed palette.')
            constants = [v for block in draw['constants'] for v in block['values']]
            starts = [v['uint'][0] for v in constants if v['name'] == 'iMatrixIndex']
            require(len(starts) == 1, 'Ambiguous palette index.')
            rows = np.frombuffer(raw, '<f4').reshape(-1, 3, 4)[starts[0]:starts[0]+count]
            require(rows.shape == (count, 3, 4) and np.isfinite(rows).all(), 'Invalid palette slice.')
            slices.append(rows.copy())
        require(bool(slices) and all(np.array_equal(s, slices[0]) for s in slices), 'Draws disagree.')
        draw_count += len(slices)
        skin = np.tile(np.eye(4), (count, 1, 1))
        skin[:, :3] = slices[0]
        world = skin @ world_bind
        local = world.copy()
        for i, p in enumerate(parents):
            if p >= 0:
                local[i] = np.linalg.inv(world[p]) @ world[i]
        read(entry['local_pose'])
        with np.load(entry['local_pose'], allow_pickle=False) as saved:
            for key, expected in (('local', local), ('world', world), ('skin', skin)):
                require(np.allclose(saved[key], expected, atol=1e-8, rtol=0), 'Saved pose mismatch: '+key)
            require(np.array_equal(saved['functions'], functions), 'Saved functions mismatch.')
        poses[entry['label']] = (local, world)

    mapping = {int(f):i for i, f in enumerate(functions)}
    bank = read_lmt_file(source)
    decoded = {a.id:decode_action_tracks(a, strict=True) for a in bank.actions if a.id < 300}
    roots = {r['label']:r for r in root_report['poses']}
    errors, root_errors = [], []
    for pose in fit['poses']:
        local, world = poses[pose['label']]
        groups = defaultdict(list)
        for track in decoded[pose['entry']].tracks:
            groups[track.bone_id, track.usage].append(track)
        require(all(len(groups[f, 0]) == 1 for f in pose['fit_bones']), 'A fitting anchor is duplicated.')
        def value(identity, which):
            return sample(groups[identity][which], pose['local_frame'], pose['interpolation'] == 'slerp')
        for d in pose['duplicate_rotations']:
            f = d['bone']
            require([t.track_index for t in groups[f, 0]] == d['slots'], 'Changed record identity.')
            first, last = (qmatrix(value((f, 0), which)) for which in (0, -1))
            observed = rotation(local[mapping[f], :3, :3])
            bind = rotation(local_bind[mapping[f], :3, :3])
            candidates = dict(first=first, last=last, first_times_last=first@last,
                last_times_first=last@first, first_bind_inverse_last=first@bind.T@last,
                last_bind_inverse_first=last@bind.T@first)
            for name, candidate in candidates.items():
                delta = abs(angle(candidate, observed) - d['degrees'][name])
                require(delta < 1e-4, 'Candidate angular result mismatch.')
                errors.append(delta)
        for r in roots[pose['label']]['candidates']:
            root = np.eye(4)
            root[:3, :3] = qmatrix(value((-1, 3), 0 if r['root_rotation'] == 'first' else -1))
            root[:3, 3] = value((-1, 4), 0 if r['root_translation'] == 'first' else -1)[:3]
            body = local_bind[mapping[0]].copy()
            if groups[0, 0]:
                body[:3, :3] = qmatrix(value((0, 0), 0))
            if groups[0, 1]:
                body[:3, 3] = value((0, 1), 0 if r['body0_translation'] == 'first' else -1)[:3]
            predicted = root @ body
            observed = world[mapping[0]]
            delta = abs(float(np.linalg.norm(predicted[:3, 3]-observed[:3, 3])) - r['world_position_error'])
            require(delta < 1e-7, 'Root position result mismatch.')
            require(abs(angle(rotation(observed[:3, :3]), predicted[:3, :3])-r['world_rotation_error_degrees']) < 1e-4,
                    'Root orientation result mismatch.')
            root_errors.append(delta)
    require(digest(source.read_bytes()) == BANK_SHA and digest(skeleton_path.read_bytes()) == BODY_SHA,
            'Source changed during verification.')
    result = dict(status='verified', case='evc0034 / Innerwear 501 / 2026-09-15',
        captures=len(poses), matched_draws=draw_count, duplicate_rotation_candidate_checks=len(errors),
        root_combination_checks=len(root_errors), max_angular_reproduction_difference_degrees=max(errors),
        max_root_position_reproduction_difference=max(root_errors),
        source_hashes=dict(lmt=BANK_SHA, mod3=BODY_SHA), input_hashes=input_hashes,
        verifier_sha256=digest(Path(__file__).read_bytes()),
        limitation='Reproduces fitted-time comparisons from saved GPU palettes; no runtime frame counter, no universal rule, no Blender correctness qualification.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'input_hashes'}))


if __name__ == '__main__':
    main()
