"""Execute saved, unmodified x64 binding instructions in an isolated CPU emulator.

Stops after the binding loop, before pose evaluation. No connection to the game.
Unicorn is a research-only dependency in research_deps, never an add-on dependency.
"""
import collections
import hashlib
import json
import os
import pathlib
import struct
import sys

ROOT = pathlib.Path(os.environ.get('MHW_NATIVE_BINDING_EVIDENCE',
    str(pathlib.Path(__file__).resolve().parents[1] / 'corpus_scans/duplicate_rules/native_evaluator_20260915')))
sys.path.insert(0, str(ROOT / 'research_deps'))
import unicorn
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_PROT_READ, UC_PROT_EXEC, UC_HOOK_CODE
from unicorn.x86_const import *

SOURCE = pathlib.Path(os.environ.get('MHW_NATIVE_SOURCE_ROOT', r'D:\mh world modding\whole game extract\chunk'))
IMAGE = 0x140000000
MEM = 0x10000000
COMPONENT = MEM
MODEL = MEM + 0x10000
JOINTS = MEM + 0x20000
LOOKUP = MEM + 0x30000
STATES = MEM + 0x40000
MOTION = MEM + 0x50000
TRACKS = MEM + 0x60000
STACK = MEM + 0x300008
HELPER = 0x1422341E0
BINDERS = (
    ('layer', 0x14224C200, 0x14224CC8D),
    ('component', 0x14237C980, 0x14237D311),
    ('alternate_joint_storage', 0x142642A30, 0x142643269),
)


class BindingReplay:
    def __init__(self):
        inventory = json.loads((ROOT / 'executable_inventory.json').read_text())
        report = json.loads((ROOT / 'loaded_code_report.json').read_text())
        blob = (ROOT / 'MonsterHunterWorld_loaded_analysis.exe').read_bytes()
        assert hashlib.sha256(blob).hexdigest() == report['analysis_copy_sha256']
        self.uc = Uc(UC_ARCH_X86, UC_MODE_64)
        self.uc.mem_map(IMAGE, 0x5600000)
        for s in inventory['sections']:
            self.uc.mem_write(IMAGE + s['rva'], blob[s['raw']:s['raw'] + s['raw_size']])
        self.uc.mem_protect(IMAGE, 0x5600000, UC_PROT_READ | UC_PROT_EXEC)
        self.uc.mem_map(MEM, 0x400000)
        self.calls = []
        self.uc.hook_add(UC_HOOK_CODE, self.visit_helper, begin=HELPER, end=HELPER)

    def visit_helper(self, uc, address, size, user):
        self.calls.append((uc.reg_read(UC_X86_REG_RCX), uc.reg_read(UC_X86_REG_RDX)))

    def write(self, address, fmt, *values):
        self.uc.mem_write(address, struct.pack(fmt, *values))

    def run(self, binder, header, tracks, mapping, layer=0, bank=0, slot=0):
        uc = self.uc
        assert len(tracks) % 48 == 0 and len(tracks) < 0x100000
        uc.mem_write(MEM, bytes(0x60000))
        uc.mem_write(TRACKS, tracks)
        uc.mem_write(MOTION, bytes(header))
        self.write(MOTION, '<Q', TRACKS)
        self.write(MOTION + 8, '<I', len(tracks)//48)
        self.write(COMPONENT + 96, '<Q', MODEL)
        self.write(MODEL + 1192, '<Q', JOINTS)
        self.write(MODEL + 1200, '<Q', LOOKUP)
        self.write(COMPONENT + 1992, '<Q', JOINTS)
        lookup = bytearray([255]*512)
        for key, index in mapping.items():
            assert 0 <= key < 512 and 0 <= index < 255
            lookup[key] = index
        uc.mem_write(LOOKUP, bytes(lookup))
        if binder[0] == 'layer':
            state = COMPONENT + 128 + 9584*bank + (4848 if layer else 48) + 432*slot
            self.write(state + 304, '<Q', STATES)
            args = (COMPONENT, bank, layer, slot)
            self.write(STACK + 40, '<Q', MOTION)
        else:
            state = COMPONENT + 128 + 432*slot
            self.write(state + 304, '<Q', STATES)
            args = (COMPONENT, slot, MOTION, 0)
        for r in (UC_X86_REG_RAX, UC_X86_REG_RBX, UC_X86_REG_RBP, UC_X86_REG_RSI, UC_X86_REG_RDI,
                  UC_X86_REG_R10, UC_X86_REG_R11, UC_X86_REG_R12, UC_X86_REG_R13, UC_X86_REG_R14, UC_X86_REG_R15):
            uc.reg_write(r, 0)
        for r, value in zip((UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9), args):
            uc.reg_write(r, value)
        uc.reg_write(UC_X86_REG_RSP, STACK)
        uc.reg_write(UC_X86_REG_EFLAGS, 2)
        self.calls = []
        expected_calls = []
        expected = {}
        ignored = collections.Counter()
        for i in range(len(tracks)//48):
            raw = tracks[i*48:(i+1)*48]
            codec, usage, joint_type, tag, bone, weight = struct.unpack_from('<BBBBif', raw)
            assert joint_type == 0, 'Nonzero joint type requires a different harness qualification'
            dest = None
            if usage in (0,1,2) and bone >= 0 and (bone & 511) in mapping:
                dest = STATES + 104*mapping[bone & 511] + 32*usage
            elif usage == 3:
                dest = state + 272
            elif usage == 4:
                dest = state + 240
            if dest is None:
                ignored[str(usage)] += 1
            else:
                expected_calls.append((dest, TRACKS + 48*i))
                expected[dest] = i
        uc.emu_start(binder[1], binder[2], timeout=10000000, count=max(10000, (len(tracks)//48)*300))
        assert uc.reg_read(UC_X86_REG_RIP) == binder[2], hex(uc.reg_read(UC_X86_REG_RIP))
        assert self.calls == expected_calls, (binder[0], 'binding sequence mismatch', self.calls[:10], expected_calls[:10])
        actual = {}
        for index in set(mapping.values()):
            for usage in (0,1,2):
                dest = STATES + 104*index + 32*usage
                actual[dest] = bytes(uc.mem_read(dest, 32))
        for dest in (state+240, state+272):
            actual[dest] = bytes(uc.mem_read(dest, 32))
        for dest, data in actual.items():
            if dest not in expected:
                assert struct.unpack_from('<Q', data)[0] == 0
                continue
            i = expected[dest]
            raw = tracks[48*i:48*i+48]
            assert struct.unpack_from('<Q', data)[0] == TRACKS + 48*i
            assert data[8:12] == bytes(4)
            assert data[16:24] == raw[16:24]
            assert data[24:28] == raw[8:12]
        return dict(bindings=len(expected_calls), destinations=len(expected), ignored=dict(ignored),
                    selected_slots=sorted(expected.values()))


def make_track(bone, usage, marker=0, weight=1., codec=1, tag=205):
    return struct.pack('<BBBBifIQ4fQ', codec, usage, 0, tag, bone, weight, 0,
                       0x60000000 + marker*16, float(marker), 2., 3., 4., 0)


def main():
    out = ROOT / sys.argv[1]
    assert not out.exists()
    replay = BindingReplay()
    header = bytearray(96)
    struct.pack_into('<IIi', header, 8, 0, 100, 0)
    synthetic = []
    for n in (1,2,3,6,7,13,257):
        tracks = b''.join(make_track(b, u, j) for j in range(n) for b,u in ((0,0),(0,1),(0,2),(-1,3),(-1,4),(-1,5)))
        for binder in BINDERS:
            result = replay.run(binder, header, tracks, {0:0})
            synthetic.append(dict(case=f'multiplicity_{n}', binder=binder[0], **result))
    # Distinct identifiers alias a single mapped destination; root usages ignore ID.
    tracks = b''.join([make_track(0,0,1), make_track(512,0,2), make_track(7,0,3),
                       make_track(9,1,4), make_track(-1,1,5), make_track(-7,3,6),
                       make_track(5,3,7), make_track(-1,4,8), make_track(42,4,9),
                       make_track(-1,5,10), make_track(0,7,11)])
    for binder in BINDERS:
        synthetic.append(dict(case='mapped_aliases_missing_ids_and_root_destinations', binder=binder[0],
                              **replay.run(binder, header, tracks, {0:0,7:0})))
    # Later weight zero still replaces the pointer; this is binding, not downstream blending.
    for flags in (0,1,2,0x1000000,0x10000000,0x11000003,0xffffffff):
        struct.pack_into('<I', header, 64, flags)
        tracks = make_track(0,0,1,weight=1.) + make_track(0,0,2,weight=0.,codec=255,tag=0)
        for binder in BINDERS:
            synthetic.append(dict(case=f'flags_{flags:x}_zero_weight_unknown_codec', binder=binder[0],
                                  **replay.run(binder, header, tracks, {0:0})))
    struct.pack_into('<I', header, 64, 0)
    for bank, layer, slot in ((0,0,0),(5,0,3),(0,1,0),(5,1,3)):
        tracks = make_track(0,0,1) + make_track(0,0,2)
        synthetic.append(dict(case=f'layer_configuration_{bank}_{layer}_{slot}', binder='layer',
                              **replay.run(BINDERS[0], header, tracks, {0:0}, layer, bank, slot)))
    print('Synthetic tests passed',len(synthetic),flush=True)
    if len(sys.argv) > 2 and sys.argv[2] == '--synthetic-only':
        out.write_text(json.dumps(dict(synthetic=synthetic),indent=2))
        return
    census = ROOT.parent / 'generalization_20260915'
    actions = json.loads((census / 'actions.json').read_text())
    banks = {x['path']:x for x in json.loads((census / 'banks.json').read_text())}
    by_bank = collections.defaultdict(list)
    for action in actions:
        by_bank[action['bank']].append(action['entry'])
    results = []
    source_reports = []
    ordinary = 0
    for bank, entries in sorted(by_bank.items()):
        path = SOURCE / bank
        before = path.stat()
        blob = path.read_bytes()
        digest = hashlib.sha256(blob).hexdigest()
        assert digest == banks[bank]['sha256'], bank
        assert blob[:4] == b'LMT\0' and struct.unpack_from('<H',blob,4)[0] == 95
        count = struct.unpack_from('<H',blob,6)[0]
        # One ordinary populated control from each affected bank when available.
        control = next((i for i in range(count) if i not in entries and struct.unpack_from('<Q',blob,16+8*i)[0]),None)
        cases = [(i,'duplicate') for i in entries]
        if control is not None:
            cases.append((control,'ordinary'))
            ordinary += 1
        for entry, kind in cases:
            offset = struct.unpack_from('<Q',blob,16+8*entry)[0]
            native_header = blob[offset:offset+96]
            track_offset, track_count = struct.unpack_from('<QI',native_header)
            tracks = blob[track_offset:track_offset+48*track_count]
            assert len(tracks) == 48*track_count
            functions = sorted(set(struct.unpack_from('<i',tracks,i*48+4)[0] & 511 for i in range(track_count)
                                   if struct.unpack_from('<i',tracks,i*48+4)[0] >= 0))
            partitions = [functions[i:i+255] for i in range(0,len(functions),255)] or [[]]
            rows = []
            for partition in partitions:
                mapping = {key:i for i,key in enumerate(partition)}
                for binder in BINDERS:
                    rows.append(dict(binder=binder[0], mapped_function_ids=partition,
                                     **replay.run(binder,native_header,tracks,mapping)))
            results.append(dict(bank=bank,entry=entry,kind=kind,track_count=track_count,replays=rows))
        after = path.stat()
        assert (before.st_size,before.st_mtime_ns) == (after.st_size,after.st_mtime_ns)
        source_reports.append(dict(bank=bank,sha256=digest,unchanged=True))
        if len(source_reports) % 10 == 0:
            print('Banks',len(source_reports),'cases',len(results),flush=True)
    report = dict(status='passed',scope='Native binding-loop instruction replay only; not full native pose evaluation.',
                  unicorn_version=unicorn.__version__, image_sha256=json.loads((ROOT/'loaded_code_report.json').read_text())['analysis_copy_sha256'],
                  counts=dict(duplicate_actions=len(actions),ordinary_actions=ordinary,banks=len(source_reports),
                              native_replays=sum(len(x['replays']) for x in results),
                              binding_calls=sum(r['bindings'] for x in results for r in x['replays']),
                              synthetic_replays=len(synthetic)),
                  synthetic=synthetic,sources=source_reports,results=results)
    out.write_text(json.dumps(report,indent=2))
    print(json.dumps(report['counts']),flush=True)


if __name__ == '__main__':
    main()
