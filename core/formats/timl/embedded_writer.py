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


def build_embedded_timl_data_payload(source_entry, sampled_transforms, *, base_offset: int) -> tuple[bytes, tuple[int, ...]]:
    """Return an embedded TIML payload plus pointer fields that need rebasing.

    `base_offset` is the source absolute TIML offset. The returned payload uses
    absolute offsets anchored to that source location so the merge writer can
    rebase it cleanly when the payload moves inside the output container.
    """

    transform_map = {}
    for transform in sampled_transforms:
        identity = (int(transform.type_index), int(transform.transform_index))
        if identity in transform_map:
            raise ValidationError(
                f"Duplicate TIML sampled transform identity type={identity[0]} transform={identity[1]}."
            )
        transform_map[identity] = transform

    type_records = []
    highest_frame = 0.0
    for type_index, type_entry in enumerate(source_entry.types):
        transform_records = []
        for transform_index, source_transform in enumerate(type_entry.transforms):
            identity = (int(type_index), int(transform_index))
            sampled_transform = transform_map.pop(identity, None)
            if sampled_transform is None:
                keyframe_bytes = _source_keyframe_bytes(
                    source_transform,
                    source_label=f"TIML {type_index:02d}:{transform_index:02d}",
                )
                keyframe_count = len(source_transform.keyframes)
                if source_transform.keyframes:
                    highest_frame = max(highest_frame, float(source_transform.keyframes[-1].frame_timing))
            else:
                if int(sampled_transform.timeline_parameter_hash) != int(type_entry.timeline_parameter_hash):
                    raise ValidationError(
                        f"TIML transform {type_index}:{transform_index} timeline hash changed from "
                        f"0x{int(type_entry.timeline_parameter_hash) & 0xFFFFFFFF:08X} to "
                        f"0x{int(sampled_transform.timeline_parameter_hash) & 0xFFFFFFFF:08X}."
                    )
                if int(sampled_transform.data_type) != int(source_transform.data_type):
                    raise ValidationError(
                        f"TIML transform {type_index}:{transform_index} data type changed from "
                        f"{source_transform.data_type} to {sampled_transform.data_type}."
                    )
                if int(sampled_transform.datatype_hash) != int(source_transform.datatype_hash):
                    raise ValidationError(
                        f"TIML transform {type_index}:{transform_index} datatype hash changed from "
                        f"0x{int(source_transform.datatype_hash) & 0xFFFFFFFF:08X} to "
                        f"0x{int(sampled_transform.datatype_hash) & 0xFFFFFFFF:08X}."
                    )
                if not sampled_transform.keyframes:
                    raise ValidationError(f"TIML transform {type_index}:{transform_index} has no writable keyframes.")
                highest_frame = max(highest_frame, float(sampled_transform.keyframes[-1].frame))
                if _can_preserve_source_curve_semantics(source_transform, sampled_transform):
                    keyframe_bytes = _source_value_patched_keyframe_bytes(
                        source_transform,
                        sampled_transform,
                        source_label=f"TIML {type_index:02d}:{transform_index:02d}",
                    )
                else:
                    keyframe_bytes = _keyframe_bytes(
                        sampled_transform,
                        source_label=f"TIML {type_index:02d}:{transform_index:02d}",
                    )
                keyframe_count = len(sampled_transform.keyframes)
            transform_records.append(
                {
                    "source_transform": source_transform,
                    "sampled_transform": sampled_transform,
                    "keyframe_bytes": keyframe_bytes,
                    "keyframe_count": keyframe_count,
                }
            )
        type_records.append(
            {
                "source_type": type_entry,
                "transform_records": transform_records,
            }
        )

    if transform_map:
        extra = ", ".join(f"{type_index}:{transform_index}" for type_index, transform_index in sorted(transform_map))
        raise ValidationError(f"Sampled TIML data contains transforms not present in the source entry: {extra}.")

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

    absolute_type_table_offset = int(base_offset) + int(type_table_rel) if type_table_rel else 0
    if absolute_type_table_offset:
        rebase_offsets.append(0)
    DATA_STRUCT.pack_into(
        payload,
        0,
        absolute_type_table_offset,
        len(type_records),
        int(source_entry.data_index_a),
        int(source_entry.data_index_b),
        max(float(source_entry.animation_length), float(highest_frame)),
        float(source_entry.loop_start_point),
        int(source_entry.loop_control),
        int(source_entry.label_hash),
    )

    for type_index, type_record in enumerate(type_records):
        type_struct_rel = int(type_table_rel) + (type_index * TYPE_STRUCT.size)
        transform_table_rel = int(type_record["transform_table_rel"])
        absolute_transform_table_offset = int(base_offset) + transform_table_rel if transform_table_rel else 0
        if absolute_transform_table_offset:
            rebase_offsets.append(type_struct_rel)
        source_type = type_record["source_type"]
        TYPE_STRUCT.pack_into(
            payload,
            type_struct_rel,
            absolute_transform_table_offset,
            len(type_record["transform_records"]),
            int(source_type.timeline_parameter_hash),
            int(source_type.reserved),
        )

        for transform_index, transform_record in enumerate(type_record["transform_records"]):
            transform_struct_rel = transform_table_rel + (transform_index * TRANSFORM_STRUCT.size)
            keyframe_table_rel = int(transform_record["keyframe_table_rel"])
            absolute_keyframe_offset = int(base_offset) + keyframe_table_rel if keyframe_table_rel else 0
            if absolute_keyframe_offset:
                rebase_offsets.append(transform_struct_rel)
            source_transform = transform_record["source_transform"]
            TRANSFORM_STRUCT.pack_into(
                payload,
                transform_struct_rel,
                absolute_keyframe_offset,
                int(transform_record["keyframe_count"]),
                int(source_transform.datatype_hash),
                int(source_transform.data_type),
            )
            payload[keyframe_table_rel : keyframe_table_rel + len(transform_record["keyframe_bytes"])] = transform_record[
                "keyframe_bytes"
            ]

    return bytes(payload), tuple(rebase_offsets)
