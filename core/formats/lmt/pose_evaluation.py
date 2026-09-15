"""CPU evaluation of the verified MHW v95 skeletal binding/sampling path.

This is deliberately separate from the legacy authoring decoder. Source records
are never projected, deduplicated or re-encoded here. See repeated-track-support.md
for the native instruction evidence and the boundary with game layer/control logic.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
import math
import struct

from .model import LmtAction, LmtTrack
from .quantized import unpack_quantized_fields


RULE_VERSION = "mhw-v95-pose-1"
_PACKED = {
    6: (8, 8, (("w", 14), ("z", 14), ("y", 14), ("x", 14), ("frame", 8))),
    7: (4, 4, (("w", 7), ("z", 7), ("y", 7), ("x", 7), ("frame", 4))),
    11: (4, 4, (("x", 14), ("w", 14), ("frame", 4))),
    12: (4, 4, (("y", 14), ("w", 14), ("frame", 4))),
    13: (4, 4, (("z", 14), ("w", 14), ("frame", 4))),
    14: (6, 2, (("x", 11), ("y", 11), ("z", 11), ("w", 11), ("frame", 4))),
    15: (5, 1, (("x", 9), ("y", 9), ("z", 9), ("w", 9), ("frame", 4))),
}
_FLOAT = struct.Struct("<f")


def _f32(value):
    return _FLOAT.unpack(_FLOAT.pack(value))[0]


def _unit(value):
    length = math.sqrt(sum(x*x for x in value))
    if not math.isfinite(length) or length <= 1e-12:
        raise ValueError("Cannot evaluate a zero-length or non-finite quaternion")
    return tuple(x / length for x in value)


def _quantized(raw, bits, mult, add):
    # Saved native samplers: (raw - 8) * float32(1 / (2**bits - 16)).
    # Preserve their rounding at decode time; interpolation uses Python doubles.
    return _f32(_f32(_f32((raw - 8) * _f32(1.0 / ((1 << bits) - 16))) * mult) + add)


@dataclass(frozen=True)
class PoseCurve:
    frames: tuple[int, ...]
    values: tuple[tuple[float, ...], ...]
    quaternion: bool
    normalize_output: bool = True

    def raw_sample(self, frame: float) -> tuple[float, ...]:
        index = max(0, bisect_right(self.frames, frame) - 1)
        value = self.values[index]
        if index + 1 < len(self.frames) and frame > self.frames[index]:
            right = self.values[index + 1]
            factor = (frame - self.frames[index]) / (self.frames[index + 1] - self.frames[index])
            # Native sub_140288F00: shortest hemisphere, raw endpoint lengths,
            # linear interpolation, THEN normalization. No endpoint normalization.
            if self.quaternion and sum(a*b for a, b in zip(value, right)) < 0:
                right = tuple(-x for x in right)
            value = tuple(a + (b-a)*factor for a, b in zip(value, right))
        return value

    def sample(self, frame: float) -> tuple[float, ...]:
        value = self.raw_sample(frame)
        return _unit(value) if self.quaternion and self.normalize_output else value


def compile_pose_curve(track: LmtTrack) -> PoseCurve:
    """Decode one record using the native sampler's quantization convention.

    A zero duration terminates native key traversal. The action-header root tail
    is not a key and is intentionally absent. Unsupported/malformed data fails.
    """
    h = track.header
    codec = h.buffer_type
    quaternion = h.usage in (0, 3)
    allowed = {2, 6, 7, 11, 12, 13, 14, 15} if quaternion else {1, 3, 4, 5}
    if codec not in allowed:
        raise ValueError(f"Unqualified codec/usage pair {codec}/{h.usage}")
    if len(track.raw_buffer) != h.buffer_size:
        raise ValueError("Record buffer length disagrees with its header")
    if codec in (1, 2):
        v = h.basis
        value = (v[3], v[0], v[1], v[2]) if quaternion else v[:3]
        frames, values = (0,), (tuple(value),)
    else:
        stride = {3: 16, 4: 8, 5: 4}.get(codec) or _PACKED[codec][0]
        if not track.raw_buffer or len(track.raw_buffer) % stride:
            raise ValueError("Animated record has an empty or misaligned buffer")
        if codec not in (3, 6) and track.lerp_basis is None:
            raise ValueError("Quantized record has no interpolation basis")
        frames, values = [], []
        frame = 0
        terminated = False
        for offset in range(0, len(track.raw_buffer), stride):
            raw = track.raw_buffer[offset:offset+stride]
            if codec == 3:
                *value, delta = struct.unpack("<3fI", raw)
            elif codec in (4, 5):
                *xyz, delta = struct.unpack("<4H" if codec == 4 else "<4B", raw)
                bits = 16 if codec == 4 else 8
                value = tuple(_quantized(x, bits, m, a) for x, m, a in
                              zip(xyz, track.lerp_basis.mult, track.lerp_basis.add))
            else:
                _, unit, fields = _PACKED[codec]
                packed = unpack_quantized_fields(raw, unit_bytes=unit, fields=fields)
                delta = packed["frame"]
                if codec == 6:
                    value = tuple((packed[k] - (16384 if packed[k] >= 8192 else 0)) / 4096.0
                                  for k in ("w", "x", "y", "z"))
                else:
                    bits = dict(fields)["w"]
                    xyzw = tuple(_quantized(packed[k], bits, m, a) if k in packed else a
                                 for k, m, a in zip("xyzw", track.lerp_basis.mult, track.lerp_basis.add))
                    value = (xyzw[3], *xyzw[:3])
            frames.append(frame)
            values.append(tuple(value))
            if delta == 0:
                terminated = True
                break
            frame += delta
        if not terminated:
            raise ValueError("Animated record has no terminating zero-duration key")
        frames, values = tuple(frames), tuple(values)
    for value in values:
        if not all(math.isfinite(x) for x in value):
            raise ValueError("Record contains non-finite sample values")
        if quaternion:
            _unit(value)
    # Codec 2 copies the reference vector verbatim in the native sampler.
    return PoseCurve(frames, values, quaternion, codec != 2)


@dataclass(frozen=True)
class PoseBinding:
    target: str | None  # None denotes the root/action channel, not a model function.
    usage: int
    source_indices: tuple[int, ...]
    identical: bool
    curve: PoseCurve | None

    @property
    def source_index(self):
        return self.source_indices[-1]


@dataclass(frozen=True)
class PoseDiagnostic:
    level: str
    source_indices: tuple[int, ...]
    message: str


@dataclass(frozen=True)
class PoseEvaluation:
    source: LmtAction
    bindings: tuple[PoseBinding, ...]
    diagnostics: tuple[PoseDiagnostic, ...]
    function_map: tuple[tuple[int, str], ...]

    @property
    def supported(self):
        return not any(d.level == "ERROR" for d in self.diagnostics)

    def sample(self, frame: float, *, base=None):
        """Return a fresh component map; explicit base values pass through holes.

        Keys are (target, usage), root target is None. A caller must provide the
        needed base components for a complete pose; this API never reads history.
        No implicit wrapping, clamping, scene state, global cache or GPU dependency.
        """
        if not self.supported:
            raise ValueError("Unsupported pose context: " + "; ".join(d.message for d in self.diagnostics if d.level == "ERROR"))
        frame = float(frame)
        if not math.isfinite(frame) or not 0 <= frame <= self.source.header.frame_count - 1:
            raise ValueError("Frame must be in the native range 0 through frame_count - 1")
        result = {key: tuple(value) for key, value in (base or {}).items()}
        for binding in self.bindings:
            result[binding.target, binding.usage] = binding.curve.sample(frame)
        return result


def compile_pose_evaluation(action: LmtAction, function_map, *, version: int = 95) -> PoseEvaluation:
    """Bind in file order using the model's masked 9-bit function lookup.

    Mapping values are stable caller-owned target names. Aliases are resolved
    before collisions; no assumption of a maximum duplicate count or block size.
    All original records remain in ``source``, including unbound/control slots.
    """
    from .content_signature import track_content_signature
    mapping = dict(function_map)
    if any(type(k) is not int or not 0 <= k < 512 or not isinstance(v, str) for k, v in mapping.items()):
        raise ValueError("Function map requires 9-bit integer keys and string target names")
    diagnostics, groups = [], {}
    if version != 95:
        diagnostics.append(PoseDiagnostic("ERROR", (), "Native pose rule is qualified only for LMT v95"))
    if action.header.flags2 & 0x10:
        diagnostics.append(PoseDiagnostic("ERROR", (), "Mirroring requires native joint-remapping context"))
    for index, track in enumerate(action.tracks):
        h = track.header
        if h.usage in (3, 4):
            target = None
        elif h.usage in (0, 1, 2) and h.bone_id >= 0 and (h.bone_id & 511) in mapping:
            target = mapping[h.bone_id & 511]
        else:
            diagnostics.append(PoseDiagnostic("INFO", (index,), "Unbound in the skeletal path; original record retained"))
            continue
        groups.setdefault((target, h.usage), []).append(index)
        if h.joint_type != 0:
            diagnostics.append(PoseDiagnostic("ERROR", (index,), "Nonzero joint_type needs additional native joint-mode evaluation"))
    bindings = []
    for (target, usage), indices in groups.items():
        selected = action.tracks[indices[-1]]
        curve = None
        try:
            if selected.header.weight != 1.0:
                raise ValueError("Non-unit record weight needs external layer/blend evaluation")
            curve = compile_pose_curve(selected)
        except ValueError as exc:
            diagnostics.append(PoseDiagnostic("ERROR", (indices[-1],), str(exc)))
        signature = track_content_signature(selected)
        identical = all(track_content_signature(action.tracks[i]) == signature for i in indices)
        bindings.append(PoseBinding(target, usage, tuple(indices), identical, curve))
    return PoseEvaluation(action, tuple(bindings), tuple(diagnostics), tuple(sorted(mapping.items())))
