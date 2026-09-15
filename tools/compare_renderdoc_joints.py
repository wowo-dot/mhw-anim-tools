"""Compare independently extracted joint-buffer slices without changing their space.

Research CLI, using NumPy in system Python. Inputs and outputs stay in this
checkout's corpus_scans. Matrix layout (little-endian float32, 3x4 per joint,
iMatrixIndex in joints) follows the earlier capture workflow and remains an
explicit interpretation until the shader/bind-space reconstruction is checked.
This does not infer animation time, track selection, or game motion rules.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def variables(values):
    for value in values:
        yield value
        yield from variables(value.get('members', []))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extraction', type=Path, action='append', required=True)
    parser.add_argument('--source-index', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / 'corpus_scans'

    def checked(path):
        path = Path(path).resolve()
        path.relative_to(root)
        return path

    destination = checked(args.output)
    if destination.exists():
        parser.error('Output already exists; choose a new report directory.')
    reports, arrays = [], {}
    source_hash = None
    for extraction in args.extraction:
        extraction = checked(extraction)
        data = json.loads(extraction.read_text())
        if data['status'] != 'complete' or data.get('extractor_version', 0) < 2:
            raise ValueError('Requires successful per-draw extraction version 2 or newer.')
        geometry_bytes = checked(data['geometry']).read_bytes()
        if hashlib.sha256(geometry_bytes).hexdigest() != data['geometry_sha256']:
            raise ValueError('Geometry report changed.')
        geometry = json.loads(geometry_bytes)['sources'][args.source_index]
        if source_hash is None:
            source_hash = geometry['sha256']
        if geometry['sha256'] != source_hash:
            raise ValueError('Captures use different source geometry.')
        count = geometry['bone_count']
        slices, worlds, draws = [], [], []
        for row in data['draws']:
            if not row.get('palette') or not any(
                m['source_index'] == args.source_index and m['full_vertex_hash_matches']
                for m in row['vertex_matches']
            ):
                continue
            values = [v for b in row['constants'] for v in variables(b['values'])]
            indices = [v['uint'][0] for v in values if v['name'] == 'iMatrixIndex']
            transforms = [v['float'] for v in values if v['name'] == 'fWorld']
            if len(indices) != 1 or len(transforms) != 1:
                raise ValueError('Ambiguous joint index or model-world constant.')
            raw = checked(row['palette']['path']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != row['palette']['sha256']:
                raise ValueError('Palette changed after extraction.')
            start = indices[0]
            buffer = np.frombuffer(raw, dtype='<f4').reshape(-1, 3, 4)
            selected = buffer[start:start + count].copy()
            world = np.asarray(transforms[0], dtype='<f4').reshape(3, 4)
            if selected.shape != (count, 3, 4) or not np.isfinite(selected).all() or not np.isfinite(world).all():
                raise ValueError('Invalid joint slice or model-world transform.')
            slices.append(selected)
            worlds.append(world)
            draws.append(dict(event=row['event'], matrix_index=start, outputs=row['outputs'],
                              slice_sha256=hashlib.sha256(selected.tobytes()).hexdigest(),
                              palette_sha256=row['palette']['sha256']))
        if not slices:
            raise ValueError('No verified draws for the requested source.')
        selected_draw = max(range(len(draws)), key=lambda i: sum(
            output != 'ResourceId::0' for output in draws[i]['outputs']))
        reference = slices[selected_draw]
        label = extraction.parent.name
        if label in arrays:
            raise ValueError('Duplicate capture label.')
        arrays[label] = (np.stack(slices), np.stack(worlds))
        reports.append(dict(label=label, capture=data['capture'], extraction=str(extraction),
                            source=data['sources'][args.source_index], bone_count=count,
                            function_by_index=geometry['function_by_index'], selected_draw=selected_draw,
                            draws=draws, finite=True,
                            within_capture_max_abs_delta=[float(np.max(np.abs(s.astype('f8') - reference))) for s in slices],
                            within_capture_bit_identical=all(s.tobytes() == reference.tobytes() for s in slices)))
    comparisons = []
    for ai, a in enumerate(reports):
        for b in reports[ai + 1:]:
            pa, wa = (v[a['selected_draw']] for v in arrays[a['label']])
            pb, wb = (v[b['selected_draw']] for v in arrays[b['label']])
            comparisons.append(dict(a=a['label'], b=b['label'],
                                    palette_slice_bit_identical=pa.tobytes() == pb.tobytes(),
                                    palette_slice_max_abs_delta=float(np.max(np.abs(pa.astype('f8') - pb))),
                                    model_world_max_abs_delta=float(np.max(np.abs(wa.astype('f8') - wb)))))
    destination.mkdir(parents=True)
    for label, (slices, worlds) in arrays.items():
        np.savez_compressed(destination / (label + '.npz'), joint_rows=slices, model_world_rows=worlds)
    result = dict(status='complete', layout_interpretation='float32 little-endian 3x4 rows per joint; iMatrixIndex in joints',
                  space='Raw shader inputs. Model-world constant saved separately; no root removal, bind conversion or rebasing.',
                  timing='Unaligned: render frames are not LMT frames.', captures=reports, comparisons=comparisons)
    (destination / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(report=str(destination / 'comparison.json'), comparisons=comparisons)))


if __name__ == '__main__':
    main()
