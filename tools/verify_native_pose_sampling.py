"""Research-only comparison with saved native x64 sampling instructions.

Requires the local evidence used by verify_native_track_binding.py and Unicorn.
Neither the emulator nor the executable is distributed with the add-on.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_native_track_binding import BindingReplay, ROOT, SOURCE, MEM, STATES, TRACKS, STACK
from verify_native_track_binding import UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_RSP, UC_X86_REG_XMM2
from core.formats.lmt.pose_evaluation import compile_pose_curve
from core.formats.lmt.reader import read_lmt_bytes


class SamplingReplay(BindingReplay):
    def set_track(self, track):
        h = track.header
        payload, basis = MEM + 0x100000, MEM + 0x200000
        if len(track.raw_buffer) >= 0x100000:
            raise ValueError("Increase research payload region before replaying this track")
        self.uc.mem_write(payload, track.raw_buffer or bytes(16))
        if track.lerp_basis:
            self.write(basis, '<8f', *track.lerp_basis.mult, *track.lerp_basis.add)
        self.write(TRACKS, '<BBBBifIQ4fQ', h.buffer_type, h.usage, h.joint_type,
                   h.unknown_tag, h.bone_id, h.weight, len(track.raw_buffer), payload,
                   *h.basis, basis if track.lerp_basis else 0)
        self.write(STATES, '<Qf4xQf4x', TRACKS, 0., payload, h.weight)

    def sample(self, frame):
        out, stop = MEM + 0x210000, MEM + 0x3ff000
        self.write(STACK, '<Q', stop)
        for register, value in ((UC_X86_REG_RCX, out), (UC_X86_REG_RDX, STATES), (UC_X86_REG_RSP, STACK)):
            self.uc.reg_write(register, value)
        self.uc.reg_write(UC_X86_REG_XMM2, struct.unpack('<I', struct.pack('<f', frame))[0])
        self.uc.emu_start(0x142234010, stop, count=1000000)
        return struct.unpack('<4f', self.uc.mem_read(out, 16))


def main():
    output = Path(sys.argv[1])
    if output.exists():
        raise FileExistsError(output)
    r = SamplingReplay()
    if '--synthetic' in sys.argv:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
        from pose_test_support import animated
        cases = []
        for codec in (3,4,5,6,7,11,12,13,14,15):
            track = animated(codec)
            r.set_track(track)
            samples = []
            for frame in (0., .25, 2.75, 5., 9.875, 10., 3.5, 0.):
                raw = r.sample(frame)
                value = (raw[3], *raw[:3]) if track.header.usage == 0 else raw[:3]
                samples.append(dict(frame=frame, value=value))
            cases.append(dict(codec=codec, samples=samples))
        loaded = json.loads((ROOT/'loaded_code_report.json').read_text())
        output.write_text(json.dumps(dict(method='Saved native x64 sampler 0x142234010; synthetic input records',
                                          analysis_copy_sha256=loaded['analysis_copy_sha256'], cases=cases), indent=2))
        return
    cases = [('evc0034', (0, 1, 4, 14)), ('evc0035', (33,)), ('evc0021', (20,)),
             ('evc0014', (14,)), ('evc0074', (2, 3, 5))]
    report, codec_counts = [], {}
    for event, entries in cases:
        path = SOURCE / f'event/{event}/pl000_00/pl000_00.lmt'
        data = path.read_bytes()
        bank = read_lmt_bytes(data, source_name=str(path))
        for entry in entries:
            action = next(a for a in bank.actions if a.id == entry)
            maximum = {"quaternion_component": 0., "vector_component": 0.}
            samples, skipped = 0, []
            for index, track in enumerate(action.tracks):
                if track.header.usage not in (0, 1, 2, 3, 4):
                    continue
                try:
                    curve = compile_pose_curve(track)
                except ValueError as exc:
                    skipped.append(dict(slot=index, reason=str(exc)))
                    continue
                r.set_track(track)
                end = action.header.frame_count - 1
                frames = sorted(set([0., end, end*.271, end*.733] +
                                    [min(end, f+.375) for f in curve.frames[::max(1, len(curve.frames)//6)]]))
                # Reuse the native state while reversing/jumping to exercise both seek paths.
                for frame in frames + frames[::-1] + frames[:2]:
                    raw = r.sample(frame)
                    native = (raw[3], *raw[:3]) if curve.quaternion else raw[:3]
                    expected = curve.sample(struct.unpack('<f', struct.pack('<f', frame))[0])
                    error = max(abs(a-b) for a,b in zip(native, expected))
                    field = 'quaternion_component' if curve.quaternion else 'vector_component'
                    maximum[field] = max(maximum[field], error)
                    tolerance = 1e-6 if curve.quaternion else max(2e-5, max(abs(x) for x in native)*3e-7)
                    assert error <= tolerance, (event, entry, index, track.header.buffer_type, frame, error, native, expected)
                    samples += 1
                codec_counts[track.header.buffer_type] = codec_counts.get(track.header.buffer_type, 0) + 1
            row = dict(event=event, entry=entry, sha256=hashlib.sha256(data).hexdigest(),
                       samples=samples, maximum_error=maximum, unsupported=skipped)
            report.append(row)
            print(json.dumps(row), flush=True)
    output.write_text(json.dumps(dict(cases=report, codec_track_counts=codec_counts), indent=2))


if __name__ == '__main__':
    main()
