"""Synthetic records, authored here rather than copied from game assets."""
from dataclasses import replace
import struct

from core.formats.lmt.model import LmtAction, LmtActionHeader, LmtTrack, LmtTrackHeader, LmtInterpolationBasis
from core.formats.lmt.quantized import pack_quantized_fields


def static(bone=0, usage=1, value=(1., 2., 3.)):
    basis = (value[1], value[2], value[3], value[0]) if usage in (0, 3) else (*value, 0.)
    return LmtTrack(LmtTrackHeader(2 if usage in (0, 3) else 1, usage, 0, 205, bone, 1., 0, 0, basis, 0), b'')


def action(tracks, *, frames=11, loop=2, entry=0):
    header = LmtActionHeader(entry, 0, len(tracks), frames, loop, (0,0,0),
                             (999.,888.,777.,0.), (0.,1.,0.,0.), 0, b'\x00\x00', 0, (0,0,0,0,0), 0)
    return LmtAction(header, tuple(tracks))


def animated(codec, bone=0, usage=None):
    quaternion = codec in (6,7,11,12,13,14,15)
    usage = (0 if quaternion else 1) if usage is None else usage
    mult, add = (1.3, .7, -.4, 1.6), (-.35, -.2, .1, -.4)
    basis = LmtInterpolationBasis(mult, add)
    if codec == 3:
        raw = struct.pack('<3fI3fI', 1., -2., 3., 10, 3., 5., -1., 0)
        basis = None
    elif codec in (4, 5):
        limit = 65520 if codec == 4 else 240
        raw = struct.pack('<8H' if codec == 4 else '<8B', 8, 23, limit, 10, limit, 90, 8, 0)
    else:
        # Deliberately independent declaration from the implementation decoder.
        layouts = {6:(8,[('w',14),('z',14),('y',14),('x',14),('frame',8)]),
                   7:(4,[('w',7),('z',7),('y',7),('x',7),('frame',4)]),
                   11:(4,[('x',14),('w',14),('frame',4)]),
                   12:(4,[('y',14),('w',14),('frame',4)]),
                   13:(4,[('z',14),('w',14),('frame',4)]),
                   14:(2,[('x',11),('y',11),('z',11),('w',11),('frame',4)]),
                   15:(1,[('x',9),('y',9),('z',9),('w',9),('frame',4)])}
        unit, fields = layouts[codec]
        raw = b''
        for key in range(2):
            parts = []
            for name, bits in fields:
                if name == 'frame':
                    value = 10 if key == 0 else 0
                elif codec == 6:
                    value = {'x':900, 'y':-1200, 'z':2500, 'w':-3100}[name] * (1 if key == 0 else -1)
                else:
                    value = 8 + int(((1 << bits)-16) * ({'x':.1,'y':.8,'z':.4,'w':.7}[name] if key == 0 else {'x':.9,'y':.1,'z':.6,'w':.2}[name]))
                parts.append((value, bits))
            raw += pack_quantized_fields(parts, unit_bytes=unit)
        if codec == 6:
            basis = None
    track = static(bone, usage, (1.,0.,0.,0.) if quaternion else (0.,0.,0.))
    return replace(track, header=replace(track.header, buffer_type=codec, buffer_size=len(raw)), raw_buffer=raw, lerp_basis=basis)
