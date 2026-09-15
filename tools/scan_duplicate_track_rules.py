"""Read-only whole-corpus census for repeated LMT records and rule counterexamples.

This inventories structure, not runtime semantics. Every repeated group retains
ordered record metadata and complete-content fingerprints. Inputs are hashed
before/after reading; memory is bounded to one bank plus its parsed model.
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
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from core.formats.lmt.reader import read_lmt_bytes, TRACK_STRUCT, ACTION_STRUCT
from tools.audit_repeated_track_evidence import inspect_action, raw_records


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def counts(counter, fields):
    return [dict(zip(fields, key if isinstance(key, tuple) else (key,)), count=value)
            for key, value in sorted(counter.items(), key=lambda item: str(item[0]))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--paths', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.source_root.resolve()
    out = args.output.resolve()
    if not out.is_relative_to(PROJECT/'corpus_scans') or out.is_relative_to(source):
        parser.error('Output must be under this checkout/corpus_scans and outside the extract.')
    if out.exists():
        parser.error('Output directory already exists; use a new directory.')
    paths = sorted({Path(line).resolve() for line in args.paths.read_text(encoding='utf-8-sig').splitlines() if line},
                   key=lambda path: str(path).casefold())
    if not paths or any(not p.is_relative_to(source) for p in paths):
        parser.error('All input paths must belong to the named source root.')
    out.mkdir(parents=True)
    total = Counter()
    metadata_all, metadata_dup, metadata_conflicting = Counter(), Counter(), Counter()
    flags_all, flags_dup, group_types, multiplicities, categories = (Counter() for _ in range(5))
    versions, fixtures, errors, banks = Counter(), [], [], []
    start = time.monotonic()
    with (out/'catalogue.jsonl').open('w', encoding='utf-8') as catalogue:
        for file_index, path in enumerate(paths):
            relative = path.relative_to(source).as_posix()
            before = path.stat()
            data = path.read_bytes()
            file_hash = digest(data)
            bank_record = dict(path=relative, sha256=file_hash, bytes=len(data))
            try:
                magic, version, entries, unknown = struct.unpack_from('<4shh8s', data)
                if magic != b'LMT\0' or version != 95 or entries < 0 or 16+8*entries > len(data):
                    raise ValueError('Unexpected LMT header/layout.')
                versions[version] += 1
                duplicate_entries = []
                file_actions = 0
                for entry in range(entries):
                    address = struct.unpack_from('<Q', data, 16+8*entry)[0]
                    if not address:
                        continue
                    header = ACTION_STRUCT.unpack_from(data, address)
                    table, track_count = header[:2]
                    if table+track_count*TRACK_STRUCT.size > len(data) or (track_count and not table):
                        raise ValueError('Invalid track table.')
                    identities = Counter()
                    modes = Counter()
                    for i in range(track_count):
                        codec, usage, mode, tag, bone, weight, size, buf, *_ = TRACK_STRUCT.unpack_from(data, table+i*48)
                        if not math.isfinite(weight):
                            raise ValueError('Non-finite track weight.')
                        identities[bone, usage] += 1
                        modes[mode, tag, struct.pack('<f', weight).hex()] += 1
                    metadata_all.update(modes)
                    flags_word = struct.unpack_from('<I', data, address+64)[0]
                    flags_all[flags_word] += 1
                    total['actions'] += 1
                    total['tracks'] += track_count
                    file_actions += 1
                    if any(n>1 for n in identities.values()):
                        duplicate_entries.append(entry)
                        flags_dup[flags_word] += 1
                if duplicate_entries:
                    bank = read_lmt_bytes(data, source_name=str(path))
                    action_by_id = {a.id:a for a in bank.actions}
                    for entry in duplicate_entries:
                        action = action_by_id[entry]
                        audit = inspect_action(data, action)
                        audit['bank'] = relative
                        audit['bank_sha256'] = file_hash
                        _, records = raw_records(data, entry)
                        static_prefix = next((r['index'] for r in records if r['size']), len(records))
                        audit['initial_empty_buffer_prefix_records'] = static_prefix
                        all_equal = True
                        for group in audit['repeated_groups']:
                            multiplicities[len(group['slots'])] += 1
                            different = not group['exact_content']
                            all_equal &= not different
                            kind = 'identical' if not different else (
                                'conflicting_' + ('static' if group['records'][0]['size']==0 else 'animated')
                                + '_to_' + ('static' if group['records'][-1]['size']==0 else 'animated'))
                            group['structural_kind'] = kind
                            group_types[kind] += 1
                            for row in group['records']:
                                key = row['mode'], row['tag'], struct.pack('<f', row['weight']).hex()
                                metadata_dup[key] += 1
                                if different:
                                    metadata_conflicting[key] += 1
                            group['same_mode_tag_weight'] = len({(r['mode'],r['tag'],struct.pack('<f',r['weight'])) for r in group['records']})==1
                        categories['all_repeated_groups_equal' if all_equal else 'has_conflicting_groups'] += 1
                        roots = defaultdict(list)
                        for check in audit['root_endpoint_checks']:
                            roots[check['usage']].append(check)
                        audit['root_header_candidate_comparisons'] = [dict(usage=usage,
                            slots=[r['slot'] for r in values], distances=[r['distance'] for r in values],
                            unit=values[0]['distance_unit'],
                            note='Payload endpoint/basis against stored action header; not a runtime oracle or injected decoder tail.')
                            for usage,values in roots.items() if len(values)>1]
                        total['duplicate_actions'] += 1
                        total['duplicate_groups'] += audit['duplicate_groups']
                        total['conflicting_groups'] += audit['conflicting_groups']
                        catalogue.write(json.dumps(audit, separators=(',', ':'), allow_nan=False)+'\n')
                        fixtures.append(dict(bank=relative,entry=entry,frames=audit['frames'],tracks=audit['tracks'],
                            groups=audit['duplicate_groups'],conflicting=audit['conflicting_groups'],
                            identical=audit['identical_groups'],flags_word=struct.unpack_from('<I',data,bank.entry_offsets[entry]+64)[0],
                            empty_buffer_prefix=static_prefix,block=audit['descriptive_blocks']))
                    total['duplicate_banks'] += 1
                    del bank
                after = path.stat()
                if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns or digest(path.read_bytes()) != file_hash:
                    raise ValueError('Source changed during scan.')
                bank_record.update(actions=file_actions,duplicate_entries=duplicate_entries,source_unchanged=True)
                total['banks'] += 1
                total['bytes'] += len(data)
            except Exception as exc:
                errors.append(dict(path=relative,error=str(exc),type=type(exc).__name__))
                bank_record['error'] = errors[-1]
            banks.append(bank_record)
            if (file_index+1)%250==0:
                catalogue.flush()
                print(json.dumps(dict(files=file_index+1,total=len(paths),duplicate_actions=total['duplicate_actions'],
                    seconds=round(time.monotonic()-start,2),errors=len(errors))),flush=True)
    summary = dict(status='complete' if not errors else 'completed_with_errors',scope='All listed native LMT banks; structural evidence only.',
        source_root=str(source),input_paths_sha256=digest(args.paths.read_bytes()),script_sha256=digest(Path(__file__).read_bytes()),
        counts=dict(total),versions=counts(versions,('version',)),errors=errors,
        all_track_metadata=counts(metadata_all,('joint_type','unknown_tag','weight_float32_hex')),
        repeated_track_metadata=counts(metadata_dup,('joint_type','unknown_tag','weight_float32_hex')),
        conflicting_track_metadata=counts(metadata_conflicting,('joint_type','unknown_tag','weight_float32_hex')),
        action_flags_all=counts(flags_all,('flags_uint32',)),action_flags_repeated=counts(flags_dup,('flags_uint32',)),
        group_structure=counts(group_types,('kind',)),group_multiplicities=counts(multiplicities,('records',)),
        action_categories=counts(categories,('category',)),
        catalogue_sha256=digest((out/'catalogue.jsonl').read_bytes()),
        elapsed_seconds=time.monotonic()-start)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    (out/'banks.json').write_text(json.dumps(banks,indent=2)+'\n',encoding='utf-8')
    (out/'actions.json').write_text(json.dumps(fixtures,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary),flush=True)
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
