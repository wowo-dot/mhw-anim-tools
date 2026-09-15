import hashlib
import json
import pathlib
import struct
from verify_native_track_binding import *

out = ROOT / (sys.argv[1] if len(sys.argv) > 1 else 'native_consumer_verification.json')
assert not out.exists()
header = bytearray(96)
struct.pack_into('<IIi', header, 8, 0, 100, 0)
replay = BindingReplay()
rows = []

# Native control consumer's search block, after its caller supplies Motion* in RAX.
# Stop before the first match is bound/sampled; original search instructions only.
for case, tracks in [
    ('two_distinct_control_records', make_track(251,1,11)+make_track(251,1,22)),
    ('reversed_control_records', make_track(251,1,22)+make_track(251,1,11)),
    ('skip_wrong_usage_and_id', make_track(251,0,1)+make_track(250,1,2)+make_track(251,1,11)+make_track(251,1,22)),
]:
    native_pose = replay.run(BINDERS[0],header,tracks,{251:0,250:1})
    replay.uc.reg_write(UC_X86_REG_RAX,MOTION)
    replay.uc.emu_start(0x140A8EDBA,0x140A8EE05,count=10000)
    assert replay.uc.reg_read(UC_X86_REG_RIP) == 0x140A8EE05
    index = (replay.uc.reg_read(UC_X86_REG_RDX)-TRACKS)//48
    expected = next(i for i in range(len(tracks)//48)
                    if tracks[48*i+1] == 1 and struct.unpack_from('<i',tracks,48*i+4)[0] == 251)
    assert index == expected
    last = max(i for i in range(len(tracks)//48)
               if tracks[48*i+1] == 1 and struct.unpack_from('<i',tracks,48*i+4)[0] == 251)
    assert expected != last
    rows.append(dict(case=case,control_selected_slot=index,pose_selected_slot=last))

class WrongFirstWins(BindingReplay):
    def visit_helper(self, uc, address, size, user):
        super().visit_helper(uc,address,size,user)
        destination = uc.reg_read(UC_X86_REG_RCX)
        if struct.unpack('<Q',uc.mem_read(destination,8))[0]:
            # Deliberate negative test only: skip the native helper on occupied slots.
            sp = uc.reg_read(UC_X86_REG_RSP)
            ret = struct.unpack('<Q',uc.mem_read(sp,8))[0]
            uc.reg_write(UC_X86_REG_RSP,sp+8)
            uc.reg_write(UC_X86_REG_RIP,ret)

negative = []
for binder in BINDERS:
    broken = WrongFirstWins()
    try:
        broken.run(binder,header,make_track(0,0,1)+make_track(0,0,2),{0:0})
    except AssertionError:
        negative.append(dict(binder=binder[0],incorrect_first_wins_rejected=True))
    else:
        raise AssertionError('Incorrect first-wins unexpectedly passed')

corpus_controls = []
catalogue = [json.loads(line) for line in (ROOT.parent/'generalization_20260915/catalogue.jsonl').read_text().splitlines()]
for action in catalogue:
    group = next((g for g in action['repeated_groups'] if g['identity'] == [251,1]), None)
    if not group:
        continue
    blob = (SOURCE/action['bank']).read_bytes()
    assert hashlib.sha256(blob).hexdigest() == action['bank_sha256']
    offset = struct.unpack_from('<Q',blob,16+8*action['entry'])[0]
    native_header = blob[offset:offset+96]
    track_offset,count = struct.unpack_from('<QI',native_header)
    tracks = blob[track_offset:track_offset+48*count]
    replay.run(BINDERS[0],native_header,tracks,{251:0})
    replay.uc.reg_write(UC_X86_REG_RAX,MOTION)
    replay.uc.emu_start(0x140A8EDBA,0x140A8EE05,count=100000)
    assert replay.uc.reg_read(UC_X86_REG_RIP) == 0x140A8EE05
    selected = (replay.uc.reg_read(UC_X86_REG_RDX)-TRACKS)//48
    assert selected == group['slots'][0]
    corpus_controls.append(dict(bank=action['bank'],entry=action['entry'],control_selected_slot=selected,
                                pose_selected_slot=group['slots'][-1],identical=group['exact_content']))

report = dict(status='passed',control_consumer='0x140a8ed80; isolated search 0x140a8edba..0x140a8ee05',
              implication='A single record-list deduplication policy cannot preserve every native consumer.',
              control_checks=rows,negative_checks=negative,corpus_controls=corpus_controls,
              corpus_control_counts=dict(groups=len(corpus_controls), conflicting=sum(not x['identical'] for x in corpus_controls)))
out.write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
