"""Read native Gallery labels and SDL selectors for the known duplicate fixtures.

Research only: reads the extract, writes one JSON outside it, and does not launch
the game or change the add-on. SDL selector interpretation remains provisional.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from audit_repeated_track_evidence import inspect_sdl, raw_records


TARGETS = {
    'evc0034': ((0, 1, 4, 14), '20036'),
    'evc0021': ((20,), '20023'),
    'evc0014': ((14,), '20016'),
    'evc0035': ((33,), '20037'),
}


def read_gmd_labels(data):
    """Decode the unencrypted GMD 0x10302 layout observed in these native files.

    Label table ordinal is NOT the text index. Use the stored text index and
    label offset; otherwise every mapping after the first unlabelled text shifts.
    This is an investigative reader, not general GMD support.
    """
    if data[:4] != b'GMD\0' or len(data) < 40:
        raise ValueError('Not a supported GMD header')
    version, language, u0, u1, label_count, text_count, key_size, text_size, name_size = (
        struct.unpack_from('<9I', data, 4))
    if version != 0x10302 or u0 != 0 or u1 != 0:
        raise ValueError('Only the observed unencrypted GMD variant is supported')
    labels_at = 40 + name_size + 1
    text_at = len(data) - text_size
    keys_at = text_at - key_size
    if not (40 <= labels_at <= keys_at <= text_at <= len(data)):
        raise ValueError('Invalid GMD section bounds')
    if keys_at - (labels_at + label_count * 32) != 2048:
        raise ValueError('Unexpected GMD label/hash table layout')
    if data[labels_at - 1] != 0:
        raise ValueError('Unterminated GMD filename')
    text = data[text_at:].split(b'\0')
    if len(text) != text_count + 1 or text[-1] != b'':
        raise ValueError('Unexpected GMD text count or terminator')
    labels = {}
    for i in range(label_count):
        index, _hash1, _hash2, _padding, key_offset, _next_hash = struct.unpack_from(
            '<4I2Q', data, labels_at + 32 * i)
        if index >= text_count or key_offset >= key_size:
            raise ValueError('Invalid GMD text index or key offset')
        at = keys_at + key_offset
        end = data.index(0, at, text_at)
        name = data[at:end].decode('utf-8')
        if name in labels:
            raise ValueError('Repeated GMD label')
        labels[name] = dict(text_index=index, text=text[index].decode('utf-8'))
    return dict(version=version, language=language, label_count=label_count,
                text_count=text_count, labels=labels)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    output = args.output.resolve()
    if output.is_relative_to(root):
        parser.error('Output must be outside the source extract.')
    sources = {}

    def read(relative):
        path = root / relative
        data = path.read_bytes()
        sources[relative] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        return data

    gallery = read_gmd_labels(read('common/text/cm_gallery_eng.gmd'))
    targets = []
    for event, (entries, pipeline_bank) in TARGETS.items():
        key = event.upper()
        lmt_path = f'event/{event}/pl000_00/pl000_00.lmt'
        lmt = read(lmt_path)
        clips = []
        for entry in entries:
            _offset, rows = raw_records(lmt, entry)
            groups = {}
            for row in rows:
                groups.setdefault((row['bone_id'], row['usage']), []).append(row)
            repeats = [g for g in groups.values() if len(g) > 1]
            identical = sum(all(r['content'] == g[0]['content'] for r in g) for g in repeats)
            clips.append(dict(entry=entry, pipeline_label=f'{pipeline_bank}:{entry}',
                              records=len(rows), identical_groups=identical,
                              conflicting_groups=len(repeats) - identical))
        item = dict(event=event, gallery_key=key, gallery_title=gallery['labels'][key]['text'],
                    gallery_text_index=gallery['labels'][key]['text_index'],
                    gallery_description=gallery['labels'][key + '_INFO']['text'],
                    lmt_path=lmt_path, clips=clips)
        if event == 'evc0034':
            sdl = inspect_sdl(read(f'event/{event}/{event}.sdl'))
            selector = next(s for s in sdl['player_selectors']
                            if s['path'] == 'pl000_00/LayerWork/MotionWork/mMotionNoHex')
            item['candidate_selector_ranges'] = [dict(
                entry=value, selector=selector['values_hex'][i],
                start_tick=selector['frames'][i],
                next_selector_tick=(selector['frames'][i+1] if i+1 < len(selector['frames']) else None),
            ) for i, value in enumerate(selector['low_12_bits_candidate_entry']) if value in entries]
            item['selector_limitations'] = (
                'Low 12 bits interpreted as LMT entry IDs. Tick-to-time and local-frame '
                'alignment are not runtime-verified; capture frame numbers are not LMT frames.')
        targets.append(item)
    for relative, identity in sources.items():
        after = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if after != identity['sha256']:
            raise RuntimeError(f'Source changed during inspection: {relative}')
    result = dict(scope='Native-file identification only; no game capture or runtime rule qualified.',
                  gallery_schema={k: v for k, v in gallery.items() if k != 'labels'},
                  sources=sources, sources_unchanged=True, targets=targets)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    for item in targets:
        print(item['event'], '->', item['gallery_title'], 'entries',
              ', '.join(str(c['entry']) for c in item['clips']))


if __name__ == '__main__':
    main()
