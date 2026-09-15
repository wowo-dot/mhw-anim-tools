"""Blender research utility: hash complete MOD3 mesh buffers for RenderDoc matching.

Requires the separately installed MHW Model Editor, not the animation add-on.
Does not import a scene or save Blender preferences. Output stays in corpus_scans.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys

import addon_utils
import numpy as np

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, action='append', required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
root = Path(__file__).resolve().parents[1] / 'corpus_scans'
destination = args.output.resolve()
if not destination.is_relative_to(root):
    parser.error('Output must be under this checkout/corpus_scans.')
if destination.exists():
    parser.error('Output already exists; choose a new report.')
addon_utils.enable('MHW_Model_Editor-main', default_set=False, persistent=False)
prefix = 'MHW_Model_Editor-main.addons.MHW_Model_Editor.modules.mod3.'
fm = importlib.import_module(prefix + 'file_mod3')
mp = importlib.import_module(prefix + 'mod3_parser')
io = importlib.import_module(prefix + 'blender_mod3')
reports = []
for source in args.source:
    source = source.resolve()
    blob = source.read_bytes()
    raw = fm.readMod3File(str(source), {'importArmatureOnly': False, 'importBoundingBoxes': False})
    local, world, remap = mp.ReadBoneBuffer(raw.skeleton.boneBuffer, raw.fileHeader.boneCount)
    row = dict(source=str(source), sha256=hashlib.sha256(blob).hexdigest(),
               bone_count=raw.fileHeader.boneCount,
               function_by_index={str(k): int(v) for k, v in remap.items()},
               export_matrix=np.array(io.exportMatrix).tolist(),
               parsed_local_matrices=np.array(local).tolist(),
               parsed_world_matrices=np.array(world).tolist(), meshes=[])
    for mi, entry in enumerate(e for group in raw.meshDict.values() for e in group):
        h = entry.meshInfo
        offset = raw.fileHeader.vertexOffset + h.vertexOffset + h.blockSize * (h.vertexSub + h.vertexBase)
        length = h.vertexCount * h.blockSize
        ixoff = raw.fileHeader.faceOffset + h.beforeFaceCount * 2
        assert 0 <= offset <= offset + length <= len(blob)
        assert 0 <= ixoff <= ixoff + h.faceCount * 2 <= len(blob)
        vertices = blob[offset:offset + length]
        indices = blob[ixoff:ixoff + h.faceCount * 2]
        row['meshes'].append(dict(mesh=mi, vertices=h.vertexCount, stride=h.blockSize,
                                 index_count=h.faceCount, vertex_first64=vertices[:64].hex(),
                                 vertex_sha256=hashlib.sha256(vertices).hexdigest(),
                                 index_sha256=hashlib.sha256(indices).hexdigest()))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == row['sha256']
    reports.append(row)
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(dict(sources=reports), indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(report=str(destination), sources=len(reports), meshes=sum(len(r['meshes']) for r in reports))))
