"""Read a saved RDC and match body draws against complete MOD3 vertex buffers.

Run with qrenderdoc --python. MHW_RD_PROJECT names this checkout;
MHW_RD_REPLAY_REQUEST names a JSON with capture, geometry, and output paths.
All output and request paths must be in corpus_scans. The game is not controlled.
Raw joint palettes and shader constants are preserved without rebasing the root.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

import renderdoc as rd

root = Path(os.environ['MHW_RD_PROJECT']).resolve() / 'corpus_scans'


def checked(path):
    result = Path(path).resolve()
    result.relative_to(root)
    return result


request = json.loads(checked(os.environ['MHW_RD_REPLAY_REQUEST']).read_text(encoding='utf-8-sig'))
capture = checked(request['capture'])
geometry = checked(request['geometry'])
dest = checked(request['output'])
dest.mkdir(parents=True, exist_ok=False)
signatures = json.loads(geometry.read_text())['sources']
meshes = [(si, m) for si, s in enumerate(signatures) for m in s['meshes']]
counts = {m['index_count'] for _, m in meshes}
report = dict(status='starting', capture=str(capture), geometry=str(geometry),
              extractor_version=2, palette_read_policy='read independently at every matched draw; deduplicate by content',
              geometry_sha256=hashlib.sha256(geometry.read_bytes()).hexdigest(),
              sources=[dict(source=s['source'], sha256=s['sha256']) for s in signatures],
              draws=[], skipped_large_vertex_buffers=[], vertex_buffer_limit_bytes=64 * 1024 * 1024)
cap = controller = None


def save():
    (dest / 'extraction.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


def variable(v):
    row = dict(name=v.name, type=str(v.type), rows=v.rows, columns=v.columns)
    if v.members:
        row['members'] = [variable(m) for m in v.members]
    else:
        row['float'] = list(v.value.f32v)[:v.rows * v.columns]
        row['uint'] = list(v.value.u32v)[:v.rows * v.columns]
    return row


try:
    cap = rd.OpenCaptureFile()
    report['open_file'] = str(cap.OpenFile(str(capture), '', None))
    thumb = cap.GetThumbnail(rd.FileType.PNG, 0)
    (dest / 'thumbnail.png').write_bytes(bytes(thumb.data))
    save()
    result, controller = cap.OpenCapture(rd.ReplayOptions(), None)
    report['open_capture'] = str(result)
    if controller is None:
        raise RuntimeError(str(result))
    report['api'] = str(controller.GetAPIProperties().pipelineType)
    structured = controller.GetStructuredFile()
    candidates = []

    def visit(nodes):
        for a in nodes:
            if a.flags & rd.ActionFlags.Drawcall and a.numIndices in counts:
                candidates.append(a)
            visit(a.children)

    visit(controller.GetRootActions())
    report['candidate_count'] = len(candidates)
    save()
    buffers = {}
    palettes = {}
    for action in candidates:
        controller.SetFrameEvent(action.eventId, True)
        pipe = controller.GetPipelineState()
        matches = []
        for vb in pipe.GetVBuffers():
            if vb.resourceId == rd.ResourceId.Null():
                continue
            if vb.byteSize > report['vertex_buffer_limit_bytes']:
                report['skipped_large_vertex_buffers'].append(dict(event=action.eventId, bytes=vb.byteSize))
                continue
            key = (str(vb.resourceId), vb.byteOffset, vb.byteSize)
            if key not in buffers:
                buffers[key] = bytes(controller.GetBufferData(vb.resourceId, vb.byteOffset, vb.byteSize))
            data = buffers[key]
            for source_index, mesh in meshes:
                if mesh['index_count'] != action.numIndices:
                    continue
                prefix = bytes.fromhex(mesh['vertex_first64'])
                if not prefix:
                    continue
                offset = data.find(prefix)
                while offset >= 0:
                    block = data[offset:offset + mesh['vertices'] * mesh['stride']]
                    if hashlib.sha256(block).hexdigest() == mesh['vertex_sha256']:
                        matches.append(dict(source_index=source_index, mesh=mesh['mesh'],
                                            vertex_sha256=mesh['vertex_sha256'], resource=str(vb.resourceId),
                                            offset=vb.byteOffset + offset, full_vertex_hash_matches=True))
                    offset = data.find(prefix, offset + 1)
        if not matches:
            continue
        row = dict(event=action.eventId, name=action.GetName(structured), indices=action.numIndices,
                   base_vertex=action.baseVertex, index_offset=action.indexOffset,
                   outputs=[str(d.resource) for d in pipe.GetOutputTargets()], vertex_matches=matches,
                   constants=[])
        report['draws'].append(row)
        reflection = pipe.GetShaderReflection(rd.ShaderStage.Vertex)
        if reflection:
            row['vertex_shader'] = str(reflection.resourceId)
            for i, cb in enumerate(reflection.constantBlocks):
                d = pipe.GetConstantBlock(rd.ShaderStage.Vertex, i, 0).descriptor
                values = controller.GetCBufferVariableContents(
                    pipe.GetGraphicsPipelineObject(), reflection.resourceId, rd.ShaderStage.Vertex,
                    reflection.entryPoint, i, d.resource, d.byteOffset, d.byteSize)
                row['constants'].append(dict(block=cb.name, values=[variable(v) for v in values]))
            for binding in pipe.GetReadOnlyResources(rd.ShaderStage.Vertex):
                if binding.access.index >= len(reflection.readOnlyResources):
                    continue
                if reflection.readOnlyResources[binding.access.index].name != 'gJointMatrixBuffer':
                    continue
                d = binding.descriptor
                # Dynamic buffers may be overwritten between draws. Resource identity
                # alone is not a valid cache key for independent pose comparisons.
                data = bytes(controller.GetBufferData(d.resource, d.byteOffset, d.byteSize))
                key = hashlib.sha256(data).hexdigest()
                if key not in palettes:
                    filename = dest / ('joint_palette_%d.bin' % len(palettes))
                    filename.write_bytes(data)
                    palettes[key] = dict(path=str(filename), sha256=key, bytes=len(data))
                row['palette'] = dict(palettes[key], resource=str(d.resource), byte_offset=d.byteOffset,
                                      byte_size=d.byteSize)
        save()
    report['verified_body_events'] = [r['event'] for r in report['draws'] if r.get('palette')]
    report['status'] = 'complete' if report['verified_body_events'] else 'no_verified_body_palette'
except Exception:
    report['status'] = 'failed'
    report['error'] = traceback.format_exc()
finally:
    save()
    if controller:
        controller.Shutdown()
    if cap:
        cap.Shutdown()
sys.exit(0 if report['status'] == 'complete' else 1)
