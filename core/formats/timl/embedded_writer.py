"""Write embedded TIML data subtrees for source-backed LMT merge export.

This writer is intentionally conservative:
- it rewrites only the embedded TIML data-entry subtree stored inside an LMT
- it preserves source type/transform ordering and metadata hashes
- it can preserve source keyframe interpolation/easing/control semantics when an
  edited preview still matches the imported keyframe structure
- otherwise it currently supports only constant/linear interpolation on sampled
  Blender controller curves
"""

from __future__ import annotations

import math
import struct

from ...diagnostics.errors import ValidationError
from .reader import COLOR_KEYFRAME_STRUCT
from .reader import DATA_STRUCT
from .reader import FLOAT_KEYFRAME_STRUCT
from .reader import SIGNED_KEYFRAME_STRUCT
from .reader import TRANSFORM_STRUCT
from .reader import TYPE_STRUCT
from .reader import UNSIGNED_KEYFRAME_STRUCT
from .semantics import get_data_type_semantics


INTERPOLATION_NAME_TO_CODE = {
    "CONSTANT": 0,
    "LINEAR": 1,
}
UINT32_MAX = (1 << 32) - 1
INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1
FRAME_TOLERANCE = 1e-6


def _align(offset: int, alignment: int) -> int:
    return (offset + (alignment - 1)) & ~(alignment - 1)


def _coerce_uint32(value: float, *, source: str) -> int:
    rounded = int(round(float(value)))
    if rounded < 0 or rounded > UINT32_MAX:
        raise ValidationError(f"{source} must fit uint32, got {value}.")
    return rounded


def _coerce_int32(value: float, *, source: str) -> int:
    rounded = int(round(float(value)))
    if rounded < INT32_MIN or rounded > INT32_MAX:
        raise ValidationError(f"{source} must fit int32, got {value}.")
    return rounded


def _coerce_rgba8_component(value: float, *, source: str) -> int:
    if not math.isfinite(float(value)):
        raise ValidationError(f"{source} must be finite, got {value}.")
    return max(0, min(255, int(round(float(value)))))


def _interpolation_code(name: str, *, source: str) -> int:
    code = INTERPOLATION_NAME_TO_CODE.get(str(name).upper())
    if code is None:
        raise ValidationError(
            f"{source} uses unsupported interpolation '{name}'. Only CONSTANT/LINEAR are writable right now."
        )
    return code


def _source_preview_interpolation_name(code: int) -> str:
    if int(code) == 0:
        return "CONSTANT"
    return "LINEAR"


def _keyframe_bytes(sampled_transform, *, source_label: str) -> bytes:
    semantics = get_data_type_semantics(sampled_transform.data_type)
    chunks: list[bytes] = []
    previous_frame = None
    for key_index, keyframe in enumerate(sampled_transform.keyframes):
        frame = float(keyframe.frame)
        if not math.isfinite(frame):
            raise ValidationError(f"{source_label} keyframe {key_index} has non-finite frame timing.")
        if previous_frame is not None and frame <= previous_frame:
            raise ValidationError(f"{source_label} keyframe timings must be strictly increasing.")
        previous_frame = frame
        interpolation = _interpolation_code(keyframe.interpolation, source=f"{source_label} keyframe {key_index}")
        easing = 0
        value = tuple(float(component) for component in keyframe.value)

        if sampled_transform.data_type == 0:
            if len(value) != 1:
                raise ValidationError(f"{source_label} signed integer keys must have exactly 1 component.")
            chunks.append(
                SIGNED_KEYFRAME_STRUCT.pack(
                    _coerce_int32(value[0], source=f"{source_label} value"),
                    0,
                    0,
                    frame,
                    interpolation,
                    easing,
                )
            )
            continue
        if sampled_transform.data_type in {1, 4}:
            if len(value) != 1:
                raise ValidationError(f"{source_label} unsigned/bool keys must have exactly 1 component.")
            chunks.append(
                UNSIGNED_KEYFRAME_STRUCT.pack(
                    _coerce_uint32(value[0], source=f"{source_label} value"),
                    0,
                    0,
                    frame,
                    interpolation,
                    easing,
                )
            )
            continue
        if sampled_transform.data_type == 2:
            if len(value) != 1:
                raise ValidationError(f"{source_label} float keys must have exactly 1 component.")
            chunks.append(
                FLOAT_KEYFRAME_STRUCT.pack(
                    float(value[0]),
                    0.0,
                    0.0,
                    frame,
                    interpolation,
                    easing,
                )
            )
            continue
        if sampled_transform.data_type == 3:
            if len(value) != 4:
                raise ValidationError(f"{source_label} color keys must have exactly 4 components.")
            chunks.append(
                COLOR_KEYFRAME_STRUCT.pack(
                    _coerce_rgba8_component(value[0], source=f"{source_label} r"),
                    _coerce_rgba8_component(value[1], source=f"{source_label} g"),
                    _coerce_rgba8_component(value[2], source=f"{source_label} b"),
                    _coerce_rgba8_component(value[3], source=f"{source_label} a"),
                    0.0,
                    0.0,
                    frame,
                    interpolation,
                    easing,
                )
            )
            continue
        raise ValidationError(
            f"{source_label} uses unsupported TIML data type {sampled_transform.data_type} ({semantics.name})."
        )
    return b"".join(chunks)


def build_embedded_timl_data_payload_from_sampled(
    sampled_transforms,
    *,
    base_offset: int,
    data_index_a: int,
    data_index_b: int,
    animation_length: float,
    loop_start_point: float,
    loop_control: int,
    label_hash: int,
) -> tuple[bytes, tuple[int, ...]]:
    """Build a full embedded TIML payload from sampled transforms.

    This is intentionally conservative:
    - type indices must be contiguous from 0..N-1
    - transform indices inside each type must be contiguous from 0..M-1
    - only currently writable scalar/color TIML data types are accepted
    - keyframe interpolation stays limited to CONSTANT/LINEAR
    """

    if not sampled_transforms:
        raise ValidationError("Cannot build an embedded TIML payload from zero sampled transforms.")

    grouped: dict[int, dict[str, object]] = {}
    seen_identities: set[tuple[int, int]] = set()
    for sampled_transform in sampled_transforms:
        type_index = int(sampled_transform.type_index)
        transform_index = int(sampled_transform.transform_index)
        identity = (type_index, transform_index)
        if identity in seen_identities:
            raise ValidationError(
                f"Duplicate TIML sampled transform identity type={type_index} transform={transform_index}."
            )
        seen_identities.add(identity)
        group = grouped.setdefault(
            type_index,
            {
                "timeline_hash": int(sampled_transform.timeline_parameter_hash),
                "transforms": {},
            },
        )
        if int(group["timeline_hash"]) != int(sampled_transform.timeline_parameter_hash):
            raise ValidationError(
                f"TIML type {type_index:02d} mixes multiple timeline hashes and cannot be written safely."
            )
        group["transforms"][transform_index] = sampled_transform

    ordered_type_indices = sorted(grouped)
    expected_type_indices = list(range(len(ordered_type_indices)))
    if ordered_type_indices != expected_type_indices:
        raise ValidationError(
            "TIML sampled type indices must be contiguous from 0 when building a new embedded payload."
        )

    type_records = []
    highest_frame = 0.0
    for type_index in ordered_type_indices:
        transform_map = grouped[type_index]["transforms"]
        ordered_transform_indices = sorted(transform_map)
        expected_transform_indices = list(range(len(ordered_transform_indices)))
        if ordered_transform_indices != expected_transform_indices:
            raise ValidationError(
                f"TIML type {type_index:02d} has non-contiguous transform indices and cannot be written safely."
            )
        transform_records = []
        for transform_index in ordered_transform_indices:
            sampled_transform = transform_map[transform_index]
            source_label = f"TIML {type_index:02d}:{transform_index:02d}"
            keyframe_blob = _keyframe_bytes(sampled_transform, source_label=source_label)
            if sampled_transform.keyframes:
                highest_frame = max(
                    highest_frame,
                    max(float(keyframe.frame) for keyframe in sampled_transform.keyframes),
                )
            transform_records.append(
                {
                    "datatype_hash": int(sampled_transform.datatype_hash),
                    "data_type": int(sampled_transform.data_type),
                    "keyframe_blob": keyframe_blob,
                    "keyframe_count": len(sampled_transform.keyframes),
                    "keyframe_offset": 0,
                    "relative_offset": 0,
                }
            )
        type_records.append(
            {
                "timeline_hash": int(grouped[type_index]["timeline_hash"]),
                "transforms": transform_records,
                "transform_table_offset": 0,
                "relative_offset": 0,
            }
        )

    data_size = DATA_STRUCT.size
    type_table_offset = _align(data_size, 16)
    current_offset = type_table_offset + (TYPE_STRUCT.size * len(type_records))
    current_offset = _align(current_offset, 16)

    rebase_offsets: list[int] = []
    if type_records:
        rebase_offsets.append(0)

    for type_index, type_record in enumerate(type_records):
        type_record["relative_offset"] = type_table_offset + (type_index * TYPE_STRUCT.size)
        if type_record["transforms"]:
            type_record["transform_table_offset"] = current_offset
            rebase_offsets.append(int(type_record["relative_offset"]))
            current_offset += TRANSFORM_STRUCT.size * len(type_record["transforms"])
            current_offset = _align(current_offset, 16)

    for type_record in type_records:
        transforms = type_record["transforms"]
        for transform_index, transform_record in enumerate(transforms):
            transform_record["relative_offset"] = (
                type_record["transform_table_offset"] + (transform_index * TRANSFORM_STRUCT.size)
            )
            if transform_record["keyframe_blob"]:
                transform_record["keyframe_offset"] = current_offset
                rebase_offsets.append(int(transform_record["relative_offset"]))
                current_offset += len(transform_record["keyframe_blob"])
                current_offset = _align(current_offset, 16)

    payload = bytearray(current_offset)
    absolute_type_table_offset = int(base_offset) + int(type_table_offset) if type_records else 0
    DATA_STRUCT.pack_into(
        payload,
        0,
        absolute_type_table_offset,
        len(type_records),
        int(data_index_a),
        int(data_index_b),
        float(max(float(animation_length), float(highest_frame))),
        float(loop_start_point),
        int(loop_control),
        int(label_hash) & 0xFFFFFFFF,
    )

    for type_record in type_records:
        absolute_transform_offset = (
            int(base_offset) + int(type_record["transform_table_offset"])
            if type_record["transforms"]
            else 0
        )
        TYPE_STRUCT.pack_into(
            payload,
            int(type_record["relative_offset"]),
            absolute_transform_offset,
            len(type_record["transforms"]),
            int(type_record["timeline_hash"]),
            0,
        )
        for transform_record in type_record["transforms"]:
            absolute_keyframe_offset = (
                int(base_offset) + int(transform_record["keyframe_offset"])
                if transform_record["keyframe_blob"]
                else 0
            )
            TRANSFORM_STRUCT.pack_into(
                payload,
                int(transform_record["relative_offset"]),
                absolute_keyframe_offset,
                int(transform_record["keyframe_count"]),
                int(transform_record["datatype_hash"]),
                int(transform_record["data_type"]),
            )
            keyframe_offset = int(transform_record["keyframe_offset"])
            keyframe_blob = bytes(transform_record["keyframe_blob"])
            if keyframe_offset and keyframe_blob:
                payload[keyframe_offset : keyframe_offset + len(keyframe_blob)] = keyframe_blob

    return bytes(payload), tuple(int(offset) for offset in rebase_offsets)


def _can_preserve_source_curve_semantics(source_transform, sampled_transform) -> bool:
    if int(sampled_transform.data_type) != int(source_transform.data_type):
        return False
    source_keyframes = tuple(source_transform.keyframes)
    sampled_keyframes = tuple(sampled_transform.keyframes)
    if len(sampled_keyframes) != len(source_keyframes):
        return False
    for source_keyframe, sampled_keyframe in zip(source_keyframes, sampled_keyframes):
        if not math.isclose(float(sampled_keyframe.frame), float(source_keyframe.frame_timing), rel_tol=0.0, abs_tol=FRAME_TOLERANCE):
            return False
        if str(sampled_keyframe.interpolation).upper() != _source_preview_interpolation_name(int(source_keyframe.interpolation)):
            return False
    return True


def can_preserve_source_curve_semantics(source_transform, sampled_transform) -> bool:
    return _can_preserve_source_curve_semantics(source_transform, sampled_transform)


def preserved_source_curve_identities(source_entry, sampled_transforms) -> set[tuple[int, int]]:
    source_map = {
        (int(type_index), int(transform_index)): transform
        for type_index, type_entry in enumerate(source_entry.types)
        for transform_index, transform in enumerate(type_entry.transforms)
    }
    preserved = set()
    for sampled_transform in sampled_transforms:
        identity = (int(sampled_transform.type_index), int(sampled_transform.transform_index))
        source_transform = source_map.get(identity)
        if source_transform is None:
            continue
        if _can_preserve_source_curve_semantics(source_transform, sampled_transform):
            preserved.add(identity)
    return preserved


def _source_value_patched_keyframe_bytes(source_transform, sampled_transform, *, source_label: str) -> bytes:
    if not _can_preserve_source_curve_semantics(source_transform, sampled_transform):
        raise ValidationError(f"{source_label} cannot preserve source semantics because the preview keyframe structure changed.")
    chunks: list[bytes] = []
    for source_keyframe, sampled_keyframe in zip(source_transform.keyframes, sampled_transform.keyframes):
        frame = float(source_keyframe.frame_timing)
        interpolation = int(source_keyframe.interpolation)
        easing = int(source_keyframe.easing)
        value = tuple(float(component) for component in sampled_keyframe.value)

        if source_transform.data_type == 0:
            if len(value) != 1:
                raise ValidationError(f"{source_label} signed integer keys must have exactly 1 component.")
            chunks.append(
                SIGNED_KEYFRAME_STRUCT.pack(
                    _coerce_int32(value[0], source=f"{source_label} value"),
                    _coerce_int32(source_keyframe.control_left, source=f"{source_label} control_left"),
                    _coerce_int32(source_keyframe.control_right, source=f"{source_label} control_right"),
                    frame,
                    interpolation,
                    easing,
                )
            )
            continue
        if source_transform.data_type in {1, 4}:
            if len(value) != 1:
                raise ValidationError(f"{source_label} unsigned/bool keys must have exactly 1 component.")
            chunks.append(
                UNSIGNED_KEYFRAME_STRUCT.pack(
                    _coerce_uint32(value[0], source=f"{source_label} value"),
                    _coerce_uint32(source_keyframe.control_left, source=f"{source_label} control_left"),
                    _coerce_uint32(source_keyframe.control_right, source=f"{source_label} control_right"),
                    frame,
                    interpolation,
                    easing,
                )
            )
            continue
        if source_transform.data_type == 2:
            if len(value) != 1:
                raise ValidationError(f"{source_label} float keys must have exactly 1 component.")
            chunks.append(
                FLOAT_KEYFRAME_STRUCT.pack(
                    float(value[0]),
                    float(source_keyframe.control_left),
                    float(source_keyframe.control_right),
                    frame,
                    interpolation,
                    easing,
                )
            )
            continue
        if source_transform.data_type == 3:
            if len(value) != 4:
                raise ValidationError(f"{source_label} color keys must have exactly 4 components.")
            chunks.append(
                COLOR_KEYFRAME_STRUCT.pack(
                    _coerce_rgba8_component(value[0], source=f"{source_label} r"),
                    _coerce_rgba8_component(value[1], source=f"{source_label} g"),
                    _coerce_rgba8_component(value[2], source=f"{source_label} b"),
                    _coerce_rgba8_component(value[3], source=f"{source_label} a"),
                    float(source_keyframe.control_left),
                    float(source_keyframe.control_right),
                    frame,
                    interpolation,
                    easing,
                )
            )
            continue
        semantics = get_data_type_semantics(source_transform.data_type)
        raise ValidationError(
            f"{source_label} uses unsupported TIML data type {source_transform.data_type} ({semantics.name})."
        )
    return b"".join(chunks)


def _source_keyframe_bytes(source_transform, *, source_label: str) -> bytes:
    semantics = get_data_type_semantics(source_transform.data_type)
    chunks: list[bytes] = []
    for keyframe in source_transform.keyframes:
        frame = float(keyframe.frame_timing)
        interpolation = int(keyframe.interpolation)
        easing = int(keyframe.easing)

        if source_transform.data_type == 0:
            chunks.append(
                SIGNED_KEYFRAME_STRUCT.pack(
                    _coerce_int32(keyframe.value, source=f"{source_label} value"),
                    _coerce_int32(keyframe.control_left, source=f"{source_label} control_left"),
                    _coerce_int32(keyframe.control_right, source=f"{source_label} control_right"),
                    frame,
                    interpolation,
                    easing,
                )
            )
            continue
        if source_transform.data_type in {1, 4}:
            chunks.append(
                UNSIGNED_KEYFRAME_STRUCT.pack(
                    _coerce_uint32(keyframe.value, source=f"{source_label} value"),
                    _coerce_uint32(keyframe.control_left, source=f"{source_label} control_left"),
                    _coerce_uint32(keyframe.control_right, source=f"{source_label} control_right"),
                    frame,
                    interpolation,
                    easing,
                )
            )
            continue
        if source_transform.data_type == 2:
            chunks.append(
                FLOAT_KEYFRAME_STRUCT.pack(
                    float(keyframe.value),
                    float(keyframe.control_left),
                    float(keyframe.control_right),
                    frame,
                    interpolation,
                    easing,
                )
            )
            continue
        if source_transform.data_type == 3:
            value = tuple(int(component) for component in keyframe.value)
            if len(value) != 4:
                raise ValidationError(f"{source_label} color source key must have exactly 4 components.")
            chunks.append(
                COLOR_KEYFRAME_STRUCT.pack(
                    _coerce_rgba8_component(value[0], source=f"{source_label} r"),
                    _coerce_rgba8_component(value[1], source=f"{source_label} g"),
                    _coerce_rgba8_component(value[2], source=f"{source_label} b"),
                    _coerce_rgba8_component(value[3], source=f"{source_label} a"),
                    float(keyframe.control_left),
                    float(keyframe.control_right),
                    frame,
                    interpolation,
                    easing,
                )
            )
            continue
        raise ValidationError(
            f"{source_label} uses unsupported TIML data type {source_transform.data_type} ({semantics.name})."
        )
    return b"".join(chunks)


def _source_identity_map(source_entry) -> dict[tuple[int, int], tuple[object, object]]:
    return {
        (int(type_index), int(transform_index)): (type_entry, transform)
        for type_index, type_entry in enumerate(source_entry.types)
        for transform_index, transform in enumerate(type_entry.transforms)
    }


def _sampled_source_identity(sampled_transform, source_identities: set[tuple[int, int]]) -> tuple[int, int] | None:
    source_type_index = getattr(sampled_transform, "source_type_index", None)
    source_transform_index = getattr(sampled_transform, "source_transform_index", None)
    if source_type_index is None or source_transform_index is None:
        return None
    identity = (int(source_type_index), int(source_transform_index))
    if identity not in source_identities:
        return None
    return identity


def _structure_reason_for_identities(identities) -> str:
    grouped: dict[int, set[int]] = {}
    for type_index, transform_index in identities:
        grouped.setdefault(int(type_index), set()).add(int(transform_index))
    ordered_type_indices = sorted(grouped)
    if ordered_type_indices != list(range(len(ordered_type_indices))):
        return "type_index_layout"
    for type_index in ordered_type_indices:
        ordered_transform_indices = sorted(grouped[type_index])
        if ordered_transform_indices != list(range(len(ordered_transform_indices))):
            return "transform_index_layout"
    return ""


def build_embedded_timl_data_payload(
    source_entry,
    sampled_transforms,
    *,
    base_offset: int,
    deleted_identities=(),
    data_index_a: int | None = None,
    data_index_b: int | None = None,
    animation_length: float | None = None,
    loop_start_point: float | None = None,
    loop_control: int | None = None,
    label_hash: int | None = None,
) -> tuple[bytes, tuple[int, ...]]:
    """Return an embedded TIML payload plus pointer fields that need rebasing.

    `base_offset` is the source absolute TIML offset. The returned payload uses
    absolute offsets anchored to that source location so the merge writer can
    rebase it cleanly when the payload moves inside the output container.
    """

    sampled_map = {}
    for sampled_transform in sampled_transforms:
        identity = (int(sampled_transform.type_index), int(sampled_transform.transform_index))
        if identity in sampled_map:
            raise ValidationError(
                f"Duplicate TIML sampled transform identity type={identity[0]} transform={identity[1]}."
            )
        sampled_map[identity] = sampled_transform

    deleted_identity_set = {
        (int(type_index), int(transform_index))
        for type_index, transform_index in deleted_identities
    }
    source_map = _source_identity_map(source_entry)
    source_identities = set(source_map)

    source_identity_by_current: dict[tuple[int, int], tuple[int, int]] = {}
    claimed_source_identities: set[tuple[int, int]] = set()
    for current_identity, sampled_transform in sampled_map.items():
        source_identity = _sampled_source_identity(sampled_transform, source_identities)
        if source_identity is None:
            continue
        if source_identity in claimed_source_identities:
            raise ValidationError(
                "Multiple TIML sampled transforms point at the same source identity "
                f"type={source_identity[0]} transform={source_identity[1]}."
            )
        claimed_source_identities.add(source_identity)
        source_identity_by_current[current_identity] = source_identity

    for current_identity in sorted(sampled_map):
        if current_identity in source_identity_by_current:
            continue
        if current_identity in deleted_identity_set:
            continue
        if current_identity not in source_map:
            continue
        if current_identity in claimed_source_identities:
            continue
        claimed_source_identities.add(current_identity)
        source_identity_by_current[current_identity] = current_identity

    preserved_source_identities = [
        identity
        for identity in sorted(source_map)
        if identity not in deleted_identity_set and identity not in claimed_source_identities
    ]
    final_identities = set(sampled_map) | set(preserved_source_identities)
    structure_reason = _structure_reason_for_identities(final_identities)
    if structure_reason == "type_index_layout":
        raise ValidationError("TIML sampled type indices must be contiguous from 0 when rebuilding the payload.")
    if structure_reason == "transform_index_layout":
        raise ValidationError("TIML sampled transform indices must be contiguous within each type when rebuilding the payload.")

    timeline_hash_by_type: dict[int, int] = {}
    for identity in sorted(final_identities):
        sampled_transform = sampled_map.get(identity)
        if sampled_transform is not None:
            timeline_hash = int(sampled_transform.timeline_parameter_hash)
        else:
            source_type, _source_transform = source_map[identity]
            timeline_hash = int(source_type.timeline_parameter_hash)
        existing_timeline_hash = timeline_hash_by_type.setdefault(int(identity[0]), timeline_hash)
        if existing_timeline_hash != timeline_hash:
            raise ValidationError(
                f"TIML type {int(identity[0]):02d} mixes multiple timeline hashes and cannot be written safely."
            )

    grouped_final_identities: dict[int, list[tuple[int, int]]] = {}
    for identity in sorted(final_identities):
        grouped_final_identities.setdefault(int(identity[0]), []).append(identity)

    type_records = []
    highest_frame = 0.0
    for type_index in sorted(grouped_final_identities):
        transform_records = []
        for identity in grouped_final_identities[type_index]:
            sampled_transform = sampled_map.get(identity)
            source_identity = source_identity_by_current.get(identity)
            if sampled_transform is None:
                source_identity = identity
            source_pair = source_map.get(source_identity) if source_identity is not None else None
            source_type = source_pair[0] if source_pair is not None else None
            source_transform = source_pair[1] if source_pair is not None else None

            if sampled_transform is None:
                keyframe_bytes = _source_keyframe_bytes(
                    source_transform,
                    source_label=f"TIML {int(identity[0]):02d}:{int(identity[1]):02d}",
                )
                keyframe_count = len(source_transform.keyframes)
                if source_transform.keyframes:
                    highest_frame = max(highest_frame, float(source_transform.keyframes[-1].frame_timing))
                data_type = int(source_transform.data_type)
                datatype_hash = int(source_transform.datatype_hash)
            else:
                if source_transform is not None:
                    if int(sampled_transform.timeline_parameter_hash) != int(source_type.timeline_parameter_hash):
                        raise ValidationError(
                            f"TIML transform {int(identity[0])}:{int(identity[1])} timeline hash changed from "
                            f"0x{int(source_type.timeline_parameter_hash) & 0xFFFFFFFF:08X} to "
                            f"0x{int(sampled_transform.timeline_parameter_hash) & 0xFFFFFFFF:08X}."
                        )
                    if int(sampled_transform.data_type) != int(source_transform.data_type):
                        raise ValidationError(
                            f"TIML transform {int(identity[0])}:{int(identity[1])} data type changed from "
                            f"{source_transform.data_type} to {sampled_transform.data_type}."
                        )
                    if int(sampled_transform.datatype_hash) != int(source_transform.datatype_hash):
                        raise ValidationError(
                            f"TIML transform {int(identity[0])}:{int(identity[1])} datatype hash changed from "
                            f"0x{int(source_transform.datatype_hash) & 0xFFFFFFFF:08X} to "
                            f"0x{int(sampled_transform.datatype_hash) & 0xFFFFFFFF:08X}."
                        )
                if not sampled_transform.keyframes:
                    raise ValidationError(f"TIML transform {int(identity[0])}:{int(identity[1])} has no writable keyframes.")
                highest_frame = max(highest_frame, float(sampled_transform.keyframes[-1].frame))
                if source_transform is not None and _can_preserve_source_curve_semantics(source_transform, sampled_transform):
                    keyframe_bytes = _source_value_patched_keyframe_bytes(
                        source_transform,
                        sampled_transform,
                        source_label=f"TIML {int(identity[0]):02d}:{int(identity[1]):02d}",
                    )
                else:
                    keyframe_bytes = _keyframe_bytes(
                        sampled_transform,
                        source_label=f"TIML {int(identity[0]):02d}:{int(identity[1]):02d}",
                    )
                keyframe_count = len(sampled_transform.keyframes)
                data_type = int(sampled_transform.data_type)
                datatype_hash = int(sampled_transform.datatype_hash)
            transform_records.append(
                {
                    "keyframe_bytes": keyframe_bytes,
                    "keyframe_count": keyframe_count,
                    "data_type": data_type,
                    "datatype_hash": datatype_hash,
                }
            )
        type_records.append(
            {
                "timeline_hash": int(timeline_hash_by_type[type_index]),
                "transform_records": transform_records,
            }
        )

    data_size = DATA_STRUCT.size
    type_table_rel = _align(data_size, 16) if type_records else 0
    current_rel = _align(type_table_rel + (TYPE_STRUCT.size * len(type_records)), 16) if type_records else _align(data_size, 16)

    for type_record in type_records:
        transforms = type_record["transform_records"]
        type_record["transform_table_rel"] = current_rel if transforms else 0
        if transforms:
            current_rel = _align(current_rel + (TRANSFORM_STRUCT.size * len(transforms)), 16)

    for type_record in type_records:
        for transform_record in type_record["transform_records"]:
            keyframe_bytes = transform_record["keyframe_bytes"]
            transform_record["keyframe_table_rel"] = current_rel if keyframe_bytes else 0
            if keyframe_bytes:
                current_rel = _align(current_rel + len(keyframe_bytes), 16)

    payload = bytearray(current_rel)
    rebase_offsets: list[int] = []

    resolved_data_index_a = int(source_entry.data_index_a if data_index_a is None else data_index_a)
    resolved_data_index_b = int(source_entry.data_index_b if data_index_b is None else data_index_b)
    resolved_animation_length = float(source_entry.animation_length if animation_length is None else animation_length)
    resolved_loop_start_point = float(source_entry.loop_start_point if loop_start_point is None else loop_start_point)
    resolved_loop_control = int(source_entry.loop_control if loop_control is None else loop_control)
    resolved_label_hash = int(source_entry.label_hash if label_hash is None else label_hash)

    absolute_type_table_offset = int(base_offset) + int(type_table_rel) if type_table_rel else 0
    if absolute_type_table_offset:
        rebase_offsets.append(0)
    DATA_STRUCT.pack_into(
        payload,
        0,
        absolute_type_table_offset,
        len(type_records),
        resolved_data_index_a,
        resolved_data_index_b,
        max(resolved_animation_length, float(highest_frame)),
        resolved_loop_start_point,
        resolved_loop_control,
        resolved_label_hash,
    )

    for type_index, type_record in enumerate(type_records):
        type_struct_rel = int(type_table_rel) + (type_index * TYPE_STRUCT.size)
        transform_table_rel = int(type_record["transform_table_rel"])
        absolute_transform_table_offset = int(base_offset) + transform_table_rel if transform_table_rel else 0
        if absolute_transform_table_offset:
            rebase_offsets.append(type_struct_rel)
        TYPE_STRUCT.pack_into(
            payload,
            type_struct_rel,
            absolute_transform_table_offset,
            len(type_record["transform_records"]),
            int(type_record["timeline_hash"]),
            0,
        )

        for transform_index, transform_record in enumerate(type_record["transform_records"]):
            transform_struct_rel = transform_table_rel + (transform_index * TRANSFORM_STRUCT.size)
            keyframe_table_rel = int(transform_record["keyframe_table_rel"])
            absolute_keyframe_offset = int(base_offset) + keyframe_table_rel if keyframe_table_rel else 0
            if absolute_keyframe_offset:
                rebase_offsets.append(transform_struct_rel)
            TRANSFORM_STRUCT.pack_into(
                payload,
                transform_struct_rel,
                absolute_keyframe_offset,
                int(transform_record["keyframe_count"]),
                int(transform_record["datatype_hash"]),
                int(transform_record["data_type"]),
            )
            payload[keyframe_table_rel : keyframe_table_rel + len(transform_record["keyframe_bytes"])] = transform_record[
                "keyframe_bytes"
            ]

    return bytes(payload), tuple(rebase_offsets)
