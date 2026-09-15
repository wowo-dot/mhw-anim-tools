"""Read-only evidence audit; this does not define or implement LMT playback rules.

Run with ordinary Python from any directory. Only the explicitly named JSON output
is written. Source files are hashed again after inspection. No Blender is needed.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.formats.lmt.decoder import decode_track_samples
from core.formats.lmt.reader import read_lmt_bytes


FIXTURES = {
    "event/evc0035/pl000_00/pl000_00.lmt": (33,),
    "event/evc0021/pl000_00/pl000_00.lmt": (20,),
    "event/evc0034/pl000_00/pl000_00.lmt": (0, 1, 4, 14),
    "event/evc0014/pl000_00/pl000_00.lmt": (14,),
    "hm/common/mot/co00_03/co00_03.lmt": (150, 151),
    "hm/common/mot/co00_00/co00_00.lmt": (363,),
    "hm/common/mot/co00_02/co00_02.lmt": (67,),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def region(data, offset, length):
    if offset < 0 or length < 0 or offset + length > len(data):
        raise ValueError(f"Out of bounds: {offset}, {length}, {len(data)}")
    return data[offset:offset + length]


def raw_records(data, action_id):
    """Read physical records independently of the add-on's object model.

    For content comparison, normalize the two addresses, retain their presence,
    and include the referenced bytes. Every other header byte stays significant,
    including float encodings (signed zero, NaNs) and the fourth basis component.
    """
    offset, = struct.unpack("<Q", region(data, 16 + 8 * action_id, 8))
    if not offset:
        raise ValueError(f"Missing entry {action_id}")
    table, count = struct.unpack("<QI", region(data, offset, 12))
    records = []
    for index in range(count):
        raw = region(data, table + index * 48, 48)
        codec, usage, mode, tag, bone, weight, size, buf, *rest = struct.unpack(
            "<BBBBifiq4fq", raw)
        lerp = rest[-1]
        if size and not buf:
            raise ValueError("Nonempty buffer has a null address")
        payload = region(data, buf, size) if size else b""
        bounds = region(data, lerp, 32) if lerp else b""
        normalized = bytearray(raw)
        normalized[16:24] = b"\0" * 8
        normalized[40:48] = b"\0" * 8
        content = (bytes(normalized), bool(buf), bool(lerp), payload, bounds)
        fingerprint = sha(bytes(normalized) + bytes((bool(buf), bool(lerp)))
                          + payload + bounds)
        records.append(dict(index=index, bone_id=bone, usage=usage, mode=mode,
                            tag=tag, weight=weight, codec=codec, size=size,
                            buffer_address=buf, lerp_address=lerp,
                            basis=tuple(rest[:4]), content=content,
                            fingerprint=fingerprint))
    return offset, records


def angular_distance(a, b):
    norm = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    if not norm:
        return None
    dot = min(1.0, abs(sum(x*y for x, y in zip(a, b))) / norm)
    return math.degrees(2 * math.acos(dot))


def inspect_action(data, action):
    offset, rows = raw_records(data, action.header.id)
    assert len(rows) == len(action.tracks)
    groups = defaultdict(list)
    root_checks = []
    for row, track in zip(rows, action.tracks):
        h = track.header
        assert (row['codec'], row['bone_id'], row['usage'], row['mode'], row['tag'],
                row['size'], row['buffer_address'], row['lerp_address']) == (
                    h.buffer_type, h.bone_id, h.usage, h.joint_type, h.unknown_tag,
                    h.buffer_size, h.buffer_offset, h.lerp_offset)
        assert row['content'][0][8:12] == struct.pack('<f', h.weight)
        assert row['content'][0][24:40] == struct.pack('<4f', *h.basis)
        assert row['content'][3] == track.raw_buffer
        expected_bounds = (struct.pack('<8f', *track.lerp_basis.mult,
                                      *track.lerp_basis.add)
                           if track.lerp_basis else b'')
        assert row['content'][4] == expected_bounds
        assert region(data, offset + 32, 16) == struct.pack('<4f', *action.header.translation)
        assert region(data, offset + 48, 16) == struct.pack('<4f', *action.header.rotation_lerp)
        groups[row['bone_id'], row['usage']].append(row)
        if h.bone_id == -1 and h.usage in (3, 4):
            decoded = decode_track_samples(action, track, row['index'], strict=True)
            # Never use decoded.tail_value: the decoder injects the action header
            # there, which would make this comparison circular.
            endpoint = decoded.keyframes[-1].value if decoded.keyframes else decoded.basis_value
            if h.usage == 4:
                header_value = action.header.translation[:3]
                error = math.dist(endpoint, header_value)
                unit = 'source_translation_units'
                exact_basis = region(data, offset + 32, 12) == struct.pack('<3f', *h.basis[:3])
            else:
                q = action.header.rotation_lerp
                header_value = (q[3], q[0], q[1], q[2])
                error = angular_distance(endpoint, header_value)
                unit = 'degrees'
                exact_basis = region(data, offset + 48, 16) == struct.pack('<4f', *h.basis)
            root_checks.append(dict(slot=row['index'], usage=h.usage,
                                    payload_keys=len(decoded.keyframes),
                                    last_payload_frame=(decoded.keyframes[-1].frame
                                                        if decoded.keyframes else None),
                                    endpoint_without_injected_tail=endpoint,
                                    header_value=header_value, distance=error,
                                    distance_unit=unit,
                                    stored_basis_matches_header_bytes=exact_basis))
    repeated = []
    for identity, group in groups.items():
        if len(group) < 2:
            continue
        repeated.append(dict(identity=identity, slots=[r['index'] for r in group],
                             exact_content=all(r['content'] == group[0]['content'] for r in group),
                             records=[{k: v for k, v in r.items() if k != 'content'} for r in group]))
    root_slots = [r['index'] for r in rows if (r['bone_id'], r['usage']) == (-1, 3)]
    split = root_slots[1] if len(root_slots) > 1 else None
    block = None
    if split is not None:
        a, b = rows[:split], rows[split:]
        block = dict(split_at_second_root_rotation=split,
                     first_records=len(a), later_records=len(b),
                     first_nonempty_buffers=sum(bool(r['size']) for r in a),
                     later_nonempty_buffers=sum(bool(r['size']) for r in b),
                     interpretation='Descriptive split only; not a proven runtime boundary.')
    return dict(entry=action.header.id, frames=action.header.frame_count,
                loop_frame=action.header.loop_frame, tracks=len(rows),
                unique_identities=len(groups), duplicate_groups=len(repeated),
                identical_groups=sum(g['exact_content'] for g in repeated),
                conflicting_groups=sum(not g['exact_content'] for g in repeated),
                mode_tag_weight_counts=[dict(mode=k[0], tag=k[1], weight=k[2], count=v)
                                       for k, v in sorted(Counter((r['mode'], r['tag'], r['weight'])
                                                                   for r in rows).items())],
                flags=action.header.flags, flags2=action.header.flags2,
                null0=action.header.null0, null2=action.header.null2.hex(), null3=action.header.null3,
                root_endpoint_checks=root_checks, descriptive_blocks=block,
                repeated_groups=repeated, independent_record_crosscheck=True)


def inspect_sdl(data):
    """Exploratory extraction of MHW SDL v32 player motion selectors only.

    Layout checked against the supplied file; not a general SDL reader. The v32
    header is 40 bytes (Revil's earlier header is 32). Preserve upper parent bits
    as unknown flags. A selector's low 12 bits is an explicit hypothesis here.
    No record inside an LMT is assigned an owner by this inspection.
    """
    assert data[:4] == b'SDL\0'
    version, count = struct.unpack_from('<HH', data, 4)
    assert version == 32
    strings, = struct.unpack_from('<Q', data, 24)
    assert 40 + 48 * count <= strings < len(data)

    def string_at(offset):
        assert strings <= offset < len(data)
        return data[offset:data.index(0, offset)].decode('utf-8', errors='strict')

    rows = []
    for index in range(count):
        typ, prop, n, parent, name, tag, group, frames, values = struct.unpack(
            '<BBHIQI4xQQQ', region(data, 40 + index * 48, 48))
        rows.append(dict(index=index, type=typ, property=prop, count=n,
                         parent=parent & 0xffffff, parent_flags=parent >> 24,
                         name=string_at(strings + name), tag=tag, group=group,
                         frame_address=frames, data_address=values))
    result = []
    for row in rows:
        if row['name'] not in ('mpMotionList', 'mMotionNoHex'):
            continue
        names = [row['name']]
        current = row
        seen = set()
        while current['type'] not in (1, 2, 3, 4):
            parent = current['parent']
            assert parent < len(rows) and parent not in seen
            seen.add(parent)
            current = rows[parent]
            names.append(current['name'])
        if names[-1] not in ('pl000_00', 'pl000_00_face'):
            continue
        item = dict(path='/'.join(reversed(names)), index=row['index'],
                    parent_flags=row['parent_flags'])
        n = row['count']
        item['frames'] = [v[0] & 0xffffff for v in struct.iter_unpack(
            '<I', region(data, row['frame_address'], 4 * n))]
        if row['name'] == 'mMotionNoHex':
            assert row['type'] == 6
            vals = [v[0] for v in struct.iter_unpack('<I', region(data, row['data_address'], 4*n))]
            item['values_hex'] = [f'0x{v:x}' for v in vals]
            item['low_12_bits_candidate_entry'] = [v & 0xfff for v in vals]
        else:
            assert row['type'] == 13
            resources = []
            for (relative,) in struct.iter_unpack('<Q', region(data, row['data_address'], 8*n)):
                at = strings + relative
                resource_hash, = struct.unpack('<I', region(data, at, 4))
                resources.append(dict(type_hash=f'0x{resource_hash:08x}', path=string_at(at + 4)))
            item['resources'] = resources
        result.append(item)
    return dict(version=version, tracks=count, interpretation='Exploratory; no within-LMT ownership proven.',
                player_selectors=result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    output = args.output.resolve()
    if output.is_relative_to(root):
        parser.error('Output must be outside the source extract.')
    files = []
    for name, entries in FIXTURES.items():
        path = root / name
        data = path.read_bytes()
        before = sha(data)
        bank = read_lmt_bytes(data, source_name=name)
        actions = {a.header.id: a for a in bank.actions}
        checks = [inspect_action(data, actions[e]) for e in entries]
        if name.startswith('hm/'):
            assert all(c['duplicate_groups'] == 0 for c in checks)
        after = sha(path.read_bytes())
        assert before == after
        files.append(dict(path=name, sha256=before, bytes=len(data), version=bank.header.version,
                          file_unchanged=True, checks=checks))
    sdl_name = 'event/evc0034/evc0034.sdl'
    sdl_path = root / sdl_name
    data = sdl_path.read_bytes()
    before = sha(data)
    sdl = inspect_sdl(data)
    assert before == sha(sdl_path.read_bytes())
    sdl.update(path=sdl_name, sha256=before, file_unchanged=True)
    result = dict(scope='Read-only structural research. No runtime composition is qualified.',
                  tool_sha256=sha(Path(__file__).read_bytes()), sources=files, scheduler=sdl)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    for file in files:
        for c in file['checks']:
            print(file['path'], c['entry'], 'tracks', c['tracks'], 'identical', c['identical_groups'],
                  'conflicting', c['conflicting_groups'])
    print('Independent raw-record checks passed; all inspected source hashes unchanged.')


if __name__ == '__main__':
    main()
