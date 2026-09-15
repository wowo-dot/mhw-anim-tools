"""Read authored SDL Draw keys before requesting duplicate-track game captures.

Research only. Uses the observed MHW v32 layout and an existing native census.
Draw enabled is a prerequisite, not proof of visibility or runtime evaluation.
Type 11 / property 3 is the byte-valued boolean track; independently checked
against RevilLib e17f9718ea571f040a7e1f331c28a4d45a6066b5/src/sdl.cpp.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import struct

PROJECT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_player_timeline(data):
    def region(at, size):
        if at < 0 or size < 0 or at + size > len(data):
            raise ValueError('SDL region outside file')
        return data[at:at + size]

    if region(0, 4) != b'SDL\0':
        raise ValueError('Invalid SDL signature')
    version, count = struct.unpack('<HH', region(4, 4))
    strings, = struct.unpack('<Q', region(24, 8))
    if version != 32 or not 40 + count * 48 <= strings < len(data):
        raise ValueError('Unsupported SDL layout')

    def string(at):
        if not strings <= at < len(data):
            raise ValueError('SDL string outside string section')
        return data[at:data.index(0, at)].decode('utf-8')

    rows = []
    for index in range(count):
        typ, prop, n, parent, name, tag, group, frames, values = struct.unpack(
            '<BBHIQI4xQQQ', region(40 + 48 * index, 48))
        rows.append(dict(index=index, type=typ, property=prop, count=n,
                         parent=parent & 0xffffff, parent_flags=parent >> 24,
                         name=string(strings + name), tag=tag, group=group,
                         frame_address=frames, data_address=values))
    wanted = {'pl000_00/Draw', 'pl000_00/mpMotionList',
              'pl000_00/LayerWork/MotionWork/mMotionNoHex'}
    tracks = {}
    for row in rows:
        names, current, seen = [row['name']], row, set()
        while current['type'] not in (1, 2, 3, 4):
            parent = current['parent']
            if parent >= count or parent in seen:
                raise ValueError('Invalid or cyclic SDL ancestry')
            seen.add(parent)
            current = rows[parent]
            names.append(current['name'])
        path = '/'.join(reversed(names))
        if path not in wanted:
            continue
        if path in tracks:
            raise ValueError('Ambiguous repeated SDL property: ' + path)
        n = row['count']
        packed = list(struct.unpack('<' + str(n) + 'I', region(row['frame_address'], 4*n)))
        times = [f & 0xffffff for f in packed]
        if not times or any(a >= b for a, b in zip(times, times[1:])):
            raise ValueError('Empty or ambiguous SDL key times')
        item = dict(row, path=path, times=times, packed_frames=packed,
                    frame_modes=[f >> 24 for f in packed])
        if row['name'] == 'Draw':
            if (row['type'], row['property']) != (11, 3):
                raise ValueError('Unsupported Draw track encoding')
            values = list(region(row['data_address'], n))
            if any(v not in (0, 1) for v in values):
                raise ValueError('Non-boolean Draw value')
        elif row['name'] == 'mMotionNoHex':
            if row['type'] != 6:
                raise ValueError('Unsupported motion selector encoding')
            values = list(struct.unpack('<' + str(n) + 'I', region(row['data_address'], 4*n)))
        else:
            if row['type'] != 13:
                raise ValueError('Unsupported motion resource encoding')
            offsets = struct.unpack('<' + str(n) + 'Q', region(row['data_address'], 8*n))
            values = [dict(resource_hash=struct.unpack('<I', region(strings + at, 4))[0],
                           path=string(strings + at + 4)) for at in offsets]
        item['values'] = values
        tracks[path] = item
    if set(tracks) != wanted:
        raise ValueError('Required player Draw/motion/resource property missing')
    return tracks


def latest(track, tick):
    candidates = [i for i, t in enumerate(track['times']) if t <= tick]
    if not candidates:
        raise ValueError('No authored value before target tick')
    return track['values'][candidates[-1]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--catalogue', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source_root, out = args.source_root.resolve(), args.output.resolve()
    if out.exists() or not out.is_relative_to(PROJECT / 'corpus_scans') or out.is_relative_to(source_root):
        parser.error('Output must be new, inside checkout/corpus_scans, and outside the extract.')
    catalogue_data = args.catalogue.read_bytes()
    banks = defaultdict(list)
    for line in catalogue_data.splitlines():
        row = json.loads(line)
        parts = Path(row['bank']).as_posix().split('/')
        if len(parts) == 4 and parts[0] == 'event' and parts[2:] == ['pl000_00', 'pl000_00.lmt']:
            banks[row['bank']].append(row)
    results, sources = [], {}
    for bank_path, actions in sorted(banks.items()):
        bank_data = (source_root / bank_path).read_bytes()
        if any(sha(bank_data) != a['bank_sha256'] for a in actions):
            raise ValueError('Source bank differs from catalogue: ' + bank_path)
        event = Path(bank_path).parts[1]
        relative_sdl = f'event/{event}/{event}.sdl'
        data = (source_root / relative_sdl).read_bytes()
        tracks = read_player_timeline(data)
        motion = tracks['pl000_00/LayerWork/MotionWork/mMotionNoHex']
        draw = tracks['pl000_00/Draw']
        resource = tracks['pl000_00/mpMotionList']
        entries = {a['entry']: a for a in actions}
        intervals = []
        for i, (tick, selector) in enumerate(zip(motion['times'], motion['values'])):
            entry = selector & 0xfff
            if entry not in entries:
                continue
            expected_resource = str(Path(bank_path).with_suffix('')).replace('\\', '/').lower()
            if latest(resource, tick)['path'].replace('\\', '/').lower() != expected_resource:
                raise ValueError('Selector uses another motion resource')
            end = motion['times'][i+1] if i+1 < len(motion['times']) else None
            initial = latest(draw, tick)
            changes = [dict(tick=t, value=v) for t, v in zip(draw['times'], draw['values'])
                       if t > tick and (end is None or t < end)]
            states = {initial, *(c['value'] for c in changes)}
            classification = ('draw_enabled' if states == {1} else
                              'draw_disabled' if states == {0} else 'draw_changes')
            if end is None:
                classification += '_until_unknown_end'
            a = entries[entry]
            intervals.append(dict(entry=entry, selector_hex=hex(selector), start_tick=tick,
                next_selector_tick=end, source_frames=a['frames'], conflicting_groups=a['conflicting_groups'],
                identical_groups=a['identical_groups'], draw_at_start=initial, draw_changes=changes,
                classification=classification))
        if {r['entry'] for r in intervals} != set(entries):
            raise ValueError('An affected entry is absent from the player selector track')
        sources[bank_path] = sha(bank_data)
        sources[relative_sdl] = sha(data)
        results.append(dict(bank=bank_path, sdl=relative_sdl, tracks=tracks, intervals=intervals))
    for relative, fingerprint in sources.items():
        if sha((source_root / relative).read_bytes()) != fingerprint:
            raise ValueError('Source changed during inspection')
    all_intervals = [r for b in results for r in b['intervals']]
    report = dict(status='complete', catalogue_sha256=sha(catalogue_data), sources=sources,
        sources_unchanged=True, banks=results, affected_player_actions=len(all_intervals),
        draw_disabled=[dict(bank=b['bank'], **r) for b in results for r in b['intervals']
                       if r['classification'].startswith('draw_disabled')],
        limitations='Authored scene schedule, not a runtime visibility/evaluation proof. Low 12 selector bits interpreted as entry IDs. Draw enabled does not guarantee camera/frustum/LOD visibility. Scene ticks and captured render frames are different clocks; hidden clips retain unresolved duplicate semantics.')
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(actions=len(all_intervals), draw_disabled=report['draw_disabled'])))


if __name__ == '__main__':
    main()
