"""Shared export encoding helpers for LMT writer milestones."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from ...animation.transforms import wxyz_to_xyzw
from ...diagnostics.errors import ValidationError


U16_VECTOR_KEY_STRUCT = struct.Struct("<4H")
U8_VECTOR_KEY_STRUCT = struct.Struct("<4B")
VECTOR_LERP_DEFAULT_TOLERANCE = 1e-4
QUATERNION_LERP_DEFAULT_TOLERANCE = 5e-4
_LERP_COMPONENT_EPSILON = 1e-12


@dataclass(frozen=True)
class QuaternionLerpSpec:
    buffer_type: int
    bits: int
    delta_limit: int
    packed_order: tuple[tuple[str, int], ...]
    stored_axes: tuple[str, ...]


QUATERNION_LERP_SPECS = {
    7: QuaternionLerpSpec(7, 7, 15, (("w", 7), ("z", 7), ("y", 7), ("x", 7), ("frame", 4)), ("x", "y", "z", "w")),
    11: QuaternionLerpSpec(11, 14, 15, (("x", 14), ("y", 0), ("z", 0), ("w", 14), ("frame", 4)), ("x", "w")),
    12: QuaternionLerpSpec(12, 14, 15, (("x", 0), ("y", 14), ("z", 0), ("w", 14), ("frame", 4)), ("y", "w")),
    13: QuaternionLerpSpec(13, 14, 15, (("x", 0), ("y", 0), ("z", 14), ("w", 14), ("frame", 4)), ("z", "w")),
    14: QuaternionLerpSpec(14, 11, 15, (("x", 11), ("y", 11), ("z", 11), ("w", 11), ("frame", 4)), ("x", "y", "z", "w")),
    15: QuaternionLerpSpec(15, 9, 15, (("x", 9), ("y", 9), ("z", 9), ("w", 9), ("frame", 4)), ("x", "y", "z", "w")),
}


def prepare_track_keyframes(track, terminal_frame: int):
    keyframes = [(int(key.frame), tuple(float(component) for component in key.value)) for key in track.keyframes]
    if not keyframes:
        return []
    if keyframes[0][0] > 1:
        keyframes.insert(0, (1, tuple(float(component) for component in track.basis_value)))

    prepared = []
    for index, (frame, value) in enumerate(keyframes):
        next_frame = keyframes[index + 1][0] if index + 1 < len(keyframes) else int(terminal_frame)
        if next_frame < frame:
            raise ValidationError(
                f"Track keyframes are not strictly increasing for bone_id={track.bone_id}, usage={track.usage}."
            )
        prepared.append((frame, value, int(next_frame - frame)))
    return prepared


def coerce_lerp_basis(values) -> tuple[float, float, float, float] | None:
    if not isinstance(values, (tuple, list)) or len(values) != 4:
        return None
    try:
        return tuple(float(component) for component in values)
    except (TypeError, ValueError):
        return None


def normalized_unsigned(raw_value: int, bits: int, offset: int = 8, excluded_range: int = 7) -> float:
    denominator = ((1 << bits) - 1) - excluded_range - offset
    return (int(raw_value) - offset) / denominator


def encode_normalized_unsigned(value: float, bits: int, offset: int = 8, excluded_range: int = 7) -> int:
    denominator = ((1 << bits) - 1) - excluded_range - offset
    return round(float(value) * denominator) + offset


def _buffer_delta_limit(buffer_type: int) -> int:
    if buffer_type == 4:
        return 65535
    if buffer_type == 5:
        return 255
    raise ValidationError(f"Unsupported vector lerp buffer type {buffer_type}.")


def quaternion_lerp_promotion_candidates(buffer_type: int) -> tuple[int, ...]:
    if buffer_type == 7:
        return (7, 15, 14)
    if buffer_type == 15:
        return (15, 14)
    if buffer_type == 14:
        return (14,)
    if buffer_type in {11, 12, 13}:
        return (buffer_type, 14)
    raise ValidationError(f"Unsupported quaternion lerp buffer type {buffer_type}.")


def _quantize_vector_component(
    value: float,
    *,
    mult: float,
    add: float,
    bits: int,
    tolerance: float,
) -> tuple[int, float]:
    if abs(mult) <= _LERP_COMPONENT_EPSILON:
        if abs(float(value) - float(add)) > tolerance:
            raise ValidationError("Vector lerp component falls outside a zero-span source lerp basis.")
        normalized = 0.0
    else:
        normalized = (float(value) - float(add)) / float(mult)
        normalized_tolerance = float(tolerance) / max(abs(float(mult)), _LERP_COMPONENT_EPSILON)
        min_normalized = normalized_unsigned(0, bits)
        max_normalized = normalized_unsigned((1 << bits) - 1, bits)
        if normalized < min_normalized - normalized_tolerance or normalized > max_normalized + normalized_tolerance:
            raise ValidationError("Vector lerp component falls outside the source lerp basis range.")
        normalized = min(max_normalized, max(min_normalized, normalized))

    encoded = encode_normalized_unsigned(normalized, bits)
    decoded = normalized_unsigned(encoded, bits) * float(mult) + float(add)
    return encoded, abs(decoded - float(value))


def _pack_bits(fields: list[tuple[int, int]]) -> bytes:
    value = 0
    shift = 0
    total_bits = 0
    for field_value, bit_count in fields:
        total_bits += bit_count
        if bit_count == 0:
            continue
        value |= (int(field_value) & ((1 << bit_count) - 1)) << shift
        shift += bit_count
    return value.to_bytes(total_bits // 8, "little")


def _quantize_quaternion_component(
    value: float,
    *,
    mult: float,
    add: float,
    bits: int,
    tolerance: float,
) -> tuple[int, float]:
    if abs(mult) <= _LERP_COMPONENT_EPSILON:
        if abs(float(value) - float(add)) > tolerance:
            raise ValidationError("Quaternion lerp component falls outside a zero-span source lerp basis.")
        normalized = 0.0
    else:
        normalized = (float(value) - float(add)) / float(mult)
        normalized_tolerance = float(tolerance) / max(abs(float(mult)), _LERP_COMPONENT_EPSILON)
        min_normalized = normalized_unsigned(0, bits)
        max_normalized = normalized_unsigned((1 << bits) - 1, bits)
        if normalized < min_normalized - normalized_tolerance or normalized > max_normalized + normalized_tolerance:
            raise ValidationError("Quaternion lerp component falls outside the source lerp basis range.")
        normalized = min(max_normalized, max(min_normalized, normalized))

    encoded = encode_normalized_unsigned(normalized, bits)
    decoded = normalized_unsigned(encoded, bits) * float(mult) + float(add)
    return encoded, abs(decoded - float(value))


def _quat_axis_value_from_xyzw(
    values_xyzw: tuple[float, float, float, float],
    axis_name: str,
) -> float:
    mapping = {"x": 0, "y": 1, "z": 2, "w": 3}
    return float(values_xyzw[mapping[axis_name]])


def _quantize_quaternion_keyframe(
    value_wxyz: tuple[float, float, float, float],
    *,
    spec: QuaternionLerpSpec,
    lerp_mult: tuple[float, float, float, float],
    lerp_add: tuple[float, float, float, float],
    tolerance: float,
) -> tuple[dict[str, int], float]:
    value_xyzw = wxyz_to_xyzw(tuple(float(component) for component in value_wxyz))
    encoded_fields: dict[str, int] = {}
    max_error = 0.0
    axis_names = ("x", "y", "z", "w")
    for axis_index, axis_name in enumerate(axis_names):
        component = float(value_xyzw[axis_index])
        if axis_name in spec.stored_axes:
            encoded, error = _quantize_quaternion_component(
                component,
                mult=float(lerp_mult[axis_index]),
                add=float(lerp_add[axis_index]),
                bits=spec.bits,
                tolerance=tolerance,
            )
            encoded_fields[axis_name] = encoded
            max_error = max(max_error, error)
        else:
            fixed_value = float(lerp_add[axis_index])
            error = abs(component - fixed_value)
            if error > tolerance:
                raise ValidationError(
                    f"Quaternion axis {axis_name.upper()} no longer matches the fixed value of the source union lerp basis."
                )
            encoded_fields[axis_name] = 0
            max_error = max(max_error, error)
    return encoded_fields, max_error


def analyze_vector_lerp_track(
    track,
    *,
    buffer_type: int,
    lerp_mult: tuple[float, float, float, float],
    lerp_add: tuple[float, float, float, float],
    terminal_frame: int,
    tolerance: float = VECTOR_LERP_DEFAULT_TOLERANCE,
) -> tuple[bool, float | None, str | None]:
    bits = 16 if int(buffer_type) == 4 else 8
    max_delta = _buffer_delta_limit(buffer_type)
    max_error = 0.0
    try:
        prepared = prepare_track_keyframes(track, terminal_frame)
        for _frame, value, delta in prepared:
            if int(delta) > max_delta:
                return False, None, f"frame delta {delta} exceeds the {max_delta}-frame limit"
            for axis in range(3):
                _encoded, error = _quantize_vector_component(
                    float(value[axis]),
                    mult=float(lerp_mult[axis]),
                    add=float(lerp_add[axis]),
                    bits=bits,
                    tolerance=tolerance,
                )
                max_error = max(max_error, error)
                if error > tolerance:
                    return False, max_error, f"quantization error {error:.6g} exceeds tolerance"
    except ValidationError as exc:
        return False, None, str(exc)
    return True, max_error, None


def analyze_quaternion_lerp_track(
    track,
    *,
    buffer_type: int,
    lerp_mult: tuple[float, float, float, float],
    lerp_add: tuple[float, float, float, float],
    terminal_frame: int,
    tolerance: float = QUATERNION_LERP_DEFAULT_TOLERANCE,
) -> tuple[bool, float | None, str | None]:
    spec = QUATERNION_LERP_SPECS.get(int(buffer_type))
    if spec is None:
        return False, None, f"unsupported quaternion lerp buffer_type {buffer_type}"
    max_error = 0.0
    try:
        prepared = prepare_track_keyframes(track, terminal_frame)
        for _frame, value, delta in prepared:
            if int(delta) > spec.delta_limit:
                return False, None, f"frame delta {delta} exceeds the {spec.delta_limit}-frame limit"
            _encoded, error = _quantize_quaternion_keyframe(
                tuple(float(component) for component in value),
                spec=spec,
                lerp_mult=lerp_mult,
                lerp_add=lerp_add,
                tolerance=tolerance,
            )
            max_error = max(max_error, error)
            if error > tolerance:
                return False, max_error, f"quantization error {error:.6g} exceeds tolerance"
    except ValidationError as exc:
        return False, None, str(exc)
    return True, max_error, None


def encode_vector_lerp_keyframes(
    track,
    *,
    buffer_type: int,
    lerp_mult: tuple[float, float, float, float],
    lerp_add: tuple[float, float, float, float],
    terminal_frame: int,
    tolerance: float = VECTOR_LERP_DEFAULT_TOLERANCE,
) -> bytes:
    bits = 16 if int(buffer_type) == 4 else 8
    max_delta = _buffer_delta_limit(buffer_type)
    prepared = prepare_track_keyframes(track, terminal_frame)
    chunks = []
    for _frame, value, delta in prepared:
        if int(delta) > max_delta:
            raise ValidationError(
                f"Track delta {delta} exceeds the {max_delta}-frame limit for buffer_type {buffer_type} "
                f"(bone_id={track.bone_id}, usage={track.usage})."
            )
        encoded_components = []
        for axis in range(3):
            encoded, error = _quantize_vector_component(
                float(value[axis]),
                mult=float(lerp_mult[axis]),
                add=float(lerp_add[axis]),
                bits=bits,
                tolerance=tolerance,
            )
            if error > tolerance:
                raise ValidationError(
                    f"Vector lerp quantization error {error:.6g} exceeds tolerance for buffer_type {buffer_type} "
                    f"(bone_id={track.bone_id}, usage={track.usage})."
                )
            encoded_components.append(encoded)
        if int(buffer_type) == 4:
            chunks.append(U16_VECTOR_KEY_STRUCT.pack(*encoded_components, int(delta)))
        else:
            chunks.append(U8_VECTOR_KEY_STRUCT.pack(*encoded_components, int(delta)))
    return b"".join(chunks)


def encode_quaternion_lerp_keyframes(
    track,
    *,
    buffer_type: int,
    lerp_mult: tuple[float, float, float, float],
    lerp_add: tuple[float, float, float, float],
    terminal_frame: int,
    tolerance: float = QUATERNION_LERP_DEFAULT_TOLERANCE,
) -> bytes:
    spec = QUATERNION_LERP_SPECS.get(int(buffer_type))
    if spec is None:
        raise ValidationError(f"Unsupported quaternion lerp buffer type {buffer_type}.")
    prepared = prepare_track_keyframes(track, terminal_frame)
    chunks = []
    for _frame, value, delta in prepared:
        if int(delta) > spec.delta_limit:
            raise ValidationError(
                f"Track delta {delta} exceeds the {spec.delta_limit}-frame limit for buffer_type {buffer_type} "
                f"(bone_id={track.bone_id}, usage={track.usage})."
            )
        encoded_components, error = _quantize_quaternion_keyframe(
            tuple(float(component) for component in value),
            spec=spec,
            lerp_mult=lerp_mult,
            lerp_add=lerp_add,
            tolerance=tolerance,
        )
        if error > tolerance:
            raise ValidationError(
                f"Quaternion lerp quantization error {error:.6g} exceeds tolerance for buffer_type {buffer_type} "
                f"(bone_id={track.bone_id}, usage={track.usage})."
            )
        fields = [(encoded_components.get(name, 0), bit_count) for name, bit_count in spec.packed_order if name != "frame"]
        fields.append((int(delta), 4))
        chunks.append(_pack_bits(fields))
    return b"".join(chunks)
