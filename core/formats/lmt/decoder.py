"""Decode LMT track buffers into typed sample data."""

from __future__ import annotations

import struct

from ...animation.transforms import xyzw_to_wxyz
from ...diagnostics.errors import BinaryFormatError
from .decoded import LmtDecodedAction
from .decoded import LmtDecodedSample
from .decoded import LmtDecodedTrack
from .quantized import unpack_quantized_fields
from .semantics import get_usage_semantics
from .semantics import raw_key_count


FLOAT_VECTOR_KEY_STRUCT = struct.Struct("<3fI")
U16_VECTOR_KEY_STRUCT = struct.Struct("<4H")
U8_VECTOR_KEY_STRUCT = struct.Struct("<4B")
RECOVERABLE_DECODE_ERRORS = (
    BinaryFormatError,
    struct.error,
    ValueError,
    OverflowError,
)


def _normalized_unsigned(raw_value: int, bits: int) -> float:
    denominator = (1 << bits) - 1
    return int(raw_value) / denominator


def _signed_fraction(raw_value: int, bits: int) -> float:
    max_value = (1 << bits) - 1
    half_range = max_value >> 1
    value = int(raw_value)
    if value > half_range:
        value -= max_value
    return value / float(half_range)


def _decode_q14_component(raw_value: int) -> float:
    return 2.0 * _signed_fraction(raw_value, 14)


def _apply_lerp_xyzw(raw_xyzw: tuple[float, float, float, float], track) -> tuple[float, float, float, float]:
    if track.lerp_basis is None:
        raise BinaryFormatError(
            "LMT track requires lerp basis but none was present",
            source_name="decoded-track",
            buffer_type=track.header.buffer_type,
            bone_id=track.header.bone_id,
        )
    return tuple(
        raw_value * mult + add
        for raw_value, mult, add in zip(raw_xyzw, track.lerp_basis.mult, track.lerp_basis.add)
    )


def _basis_value_for_track(track) -> tuple[float, ...]:
    usage = get_usage_semantics(track.header.usage)
    if usage.is_quaternion:
        return xyzw_to_wxyz(tuple(float(value) for value in track.header.basis))
    return tuple(float(value) for value in track.header.basis[:3])


def _tail_value_for_action(action, track) -> tuple[float, ...] | None:
    usage = get_usage_semantics(track.header.usage)
    if usage.scope != "root" or track.header.bone_id != -1:
        return None
    if usage.transform == "scale":
        return None
    if usage.is_quaternion:
        return xyzw_to_wxyz(tuple(float(value) for value in action.header.rotation_lerp))
    return tuple(float(value) for value in action.header.translation[:3])


def _decode_float_vector_keys(track) -> tuple[LmtDecodedSample, ...]:
    samples: list[LmtDecodedSample] = []
    frame = 0
    for offset in range(0, len(track.raw_buffer), FLOAT_VECTOR_KEY_STRUCT.size):
        x, y, z, delta = FLOAT_VECTOR_KEY_STRUCT.unpack_from(track.raw_buffer, offset)
        samples.append(LmtDecodedSample(frame=frame, delta_to_next=delta, value=(x, y, z)))
        frame += delta
    return tuple(samples)


def _decode_u16_vector_lerp(track) -> tuple[LmtDecodedSample, ...]:
    samples: list[LmtDecodedSample] = []
    frame = 0
    for offset in range(0, len(track.raw_buffer), U16_VECTOR_KEY_STRUCT.size):
        raw_x, raw_y, raw_z, delta = U16_VECTOR_KEY_STRUCT.unpack_from(track.raw_buffer, offset)
        xyzw = (
            _normalized_unsigned(raw_x, 16),
            _normalized_unsigned(raw_y, 16),
            _normalized_unsigned(raw_z, 16),
            0.0,
        )
        lerped_xyzw = _apply_lerp_xyzw(xyzw, track)
        samples.append(
            LmtDecodedSample(
                frame=frame,
                delta_to_next=delta,
                value=tuple(float(value) for value in lerped_xyzw[:3]),
            )
        )
        frame += delta
    return tuple(samples)


def _decode_u8_vector_lerp(track) -> tuple[LmtDecodedSample, ...]:
    samples: list[LmtDecodedSample] = []
    frame = 0
    for offset in range(0, len(track.raw_buffer), U8_VECTOR_KEY_STRUCT.size):
        raw_x, raw_y, raw_z, delta = U8_VECTOR_KEY_STRUCT.unpack_from(track.raw_buffer, offset)
        xyzw = (
            _normalized_unsigned(raw_x, 8),
            _normalized_unsigned(raw_y, 8),
            _normalized_unsigned(raw_z, 8),
            0.0,
        )
        lerped_xyzw = _apply_lerp_xyzw(xyzw, track)
        samples.append(
            LmtDecodedSample(
                frame=frame,
                delta_to_next=delta,
                value=tuple(float(value) for value in lerped_xyzw[:3]),
            )
        )
        frame += delta
    return tuple(samples)


def _decode_q14_keys(track) -> tuple[LmtDecodedSample, ...]:
    samples: list[LmtDecodedSample] = []
    frame = 0
    fields = (
        ("w", 14),
        ("z", 14),
        ("y", 14),
        ("x", 14),
        ("frame", 8),
    )
    for offset in range(0, len(track.raw_buffer), 8):
        packed = unpack_quantized_fields(
            track.raw_buffer[offset:offset + 8],
            unit_bytes=8,
            fields=fields,
        )
        value = (
            _decode_q14_component(packed["w"]),
            _decode_q14_component(packed["x"]),
            _decode_q14_component(packed["y"]),
            _decode_q14_component(packed["z"]),
        )
        samples.append(LmtDecodedSample(frame=frame, delta_to_next=packed["frame"], value=value))
        frame += packed["frame"]
    return tuple(samples)


def _decode_quaternion_lerp(
    track,
    *,
    bits: int,
    packed_order: tuple[tuple[str, int], ...],
    unit_bytes: int,
) -> tuple[LmtDecodedSample, ...]:
    samples: list[LmtDecodedSample] = []
    frame = 0
    stride = sum(bit_count for _name, bit_count in packed_order) // 8
    field_sizes = dict(packed_order)
    for stride_offset in range(0, len(track.raw_buffer), stride):
        packed = unpack_quantized_fields(
            track.raw_buffer[stride_offset:stride_offset + stride],
            unit_bytes=unit_bytes,
            fields=packed_order,
        )
        raw_xyzw = (
            0.0 if field_sizes.get("x", 0) == 0 else _normalized_unsigned(packed.get("x", 0), bits),
            0.0 if field_sizes.get("y", 0) == 0 else _normalized_unsigned(packed.get("y", 0), bits),
            0.0 if field_sizes.get("z", 0) == 0 else _normalized_unsigned(packed.get("z", 0), bits),
            _normalized_unsigned(packed["w"], bits),
        )
        lerped_xyzw = _apply_lerp_xyzw(raw_xyzw, track)
        samples.append(
            LmtDecodedSample(
                frame=frame,
                delta_to_next=packed["frame"],
                value=xyzw_to_wxyz(lerped_xyzw),
            )
        )
        frame += packed["frame"]
    return tuple(samples)


def _decode_supported_track(track) -> tuple[LmtDecodedSample, ...]:
    buffer_type = track.header.buffer_type
    if buffer_type in {1, 2}:
        return ()
    if buffer_type == 3:
        return _decode_float_vector_keys(track)
    if buffer_type == 4:
        return _decode_u16_vector_lerp(track)
    if buffer_type == 5:
        return _decode_u8_vector_lerp(track)
    if buffer_type == 6:
        return _decode_q14_keys(track)
    if buffer_type == 7:
        return _decode_quaternion_lerp(
            track,
            bits=7,
            packed_order=(("w", 7), ("z", 7), ("y", 7), ("x", 7), ("frame", 4)),
            unit_bytes=4,
        )
    if buffer_type == 11:
        return _decode_quaternion_lerp(
            track,
            bits=14,
            packed_order=(("x", 14), ("y", 0), ("z", 0), ("w", 14), ("frame", 4)),
            unit_bytes=4,
        )
    if buffer_type == 12:
        return _decode_quaternion_lerp(
            track,
            bits=14,
            packed_order=(("x", 0), ("y", 14), ("z", 0), ("w", 14), ("frame", 4)),
            unit_bytes=4,
        )
    if buffer_type == 13:
        return _decode_quaternion_lerp(
            track,
            bits=14,
            packed_order=(("x", 0), ("y", 0), ("z", 14), ("w", 14), ("frame", 4)),
            unit_bytes=4,
        )
    if buffer_type == 14:
        return _decode_quaternion_lerp(
            track,
            bits=11,
            packed_order=(("x", 11), ("y", 11), ("z", 11), ("w", 11), ("frame", 4)),
            unit_bytes=2,
        )
    if buffer_type == 15:
        return _decode_quaternion_lerp(
            track,
            bits=9,
            packed_order=(("x", 9), ("y", 9), ("z", 9), ("w", 9), ("frame", 4)),
            unit_bytes=1,
        )
    raise BinaryFormatError(
        "Unsupported LMT buffer type",
        source_name="decoded-track",
        buffer_type=buffer_type,
        bone_id=track.header.bone_id,
    )


def decode_track_samples(action, track, track_index: int, *, strict: bool = False) -> LmtDecodedTrack:
    key_count = raw_key_count(track.header.buffer_type, track.header.buffer_size)
    basis_value = _basis_value_for_track(track)
    tail_value = _tail_value_for_action(action, track)
    try:
        if key_count is None:
            raise BinaryFormatError(
                "Track buffer size does not match expected stride",
                source_name="decoded-track",
                buffer_type=track.header.buffer_type,
                buffer_size=track.header.buffer_size,
                bone_id=track.header.bone_id,
            )
        samples = _decode_supported_track(track)
        return LmtDecodedTrack(
            track_index=track_index,
            bone_id=track.header.bone_id,
            usage=track.header.usage,
            buffer_type=track.header.buffer_type,
            basis_value=basis_value,
            keyframes=samples,
            tail_frame=int(action.header.frame_count) if tail_value is not None else None,
            tail_value=tail_value,
        )
    # Non-strict mode should recover from malformed source data, but it should
    # not hide programmer bugs such as accidental AttributeError/TypeError
    # regressions inside the decoder itself.
    except RECOVERABLE_DECODE_ERRORS as exc:
        if strict:
            raise
        return LmtDecodedTrack(
            track_index=track_index,
            bone_id=track.header.bone_id,
            usage=track.header.usage,
            buffer_type=track.header.buffer_type,
            basis_value=basis_value,
            keyframes=(),
            tail_frame=int(action.header.frame_count) if tail_value is not None else None,
            tail_value=tail_value,
            decode_error=str(exc),
        )


def decode_action_tracks(action, *, strict: bool = False) -> LmtDecodedAction:
    decoded_tracks = tuple(
        decode_track_samples(action, track, track_index=index, strict=strict)
        for index, track in enumerate(action.tracks)
    )
    return LmtDecodedAction(
        action_id=action.id,
        frame_count=action.header.frame_count,
        loop_frame=action.header.loop_frame,
        tracks=decoded_tracks,
    )


def decode_lmt_tracks(lmt, *, strict: bool = False) -> tuple[LmtDecodedAction, ...]:
    return tuple(decode_action_tracks(action, strict=strict) for action in lmt.actions)
