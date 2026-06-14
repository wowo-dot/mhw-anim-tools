"""Friendly LMT semantics for diagnostics and Blender-facing summaries.

This module intentionally stays small and data-oriented. It provides readable
labels for track usage and buffer encodings without inheriting the legacy
FreeHK architecture.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LmtUsageSemantics:
    usage: int
    scope: str
    scope_label: str
    transform: str
    transform_label: str
    blender_path_hint: str
    channel_labels: tuple[str, ...]
    is_quaternion: bool


@dataclass(frozen=True)
class LmtBufferSemantics:
    buffer_type: int
    code: str
    label: str
    channel_labels: tuple[str, ...]
    keyframe_stride: int | None
    stores_keyframes: bool
    uses_lerp_basis: bool


_USAGE_TABLE = {
    0: LmtUsageSemantics(
        usage=0,
        scope="local",
        scope_label="Bone Local",
        transform="rotation",
        transform_label="Rotation",
        blender_path_hint="rotation_quaternion",
        channel_labels=("w", "x", "y", "z"),
        is_quaternion=True,
    ),
    1: LmtUsageSemantics(
        usage=1,
        scope="local",
        scope_label="Bone Local",
        transform="translation",
        transform_label="Translation",
        blender_path_hint="location",
        channel_labels=("x", "y", "z"),
        is_quaternion=False,
    ),
    2: LmtUsageSemantics(
        usage=2,
        scope="local",
        scope_label="Bone Local",
        transform="scale",
        transform_label="Scale",
        blender_path_hint="scale",
        channel_labels=("x", "y", "z"),
        is_quaternion=False,
    ),
    3: LmtUsageSemantics(
        usage=3,
        scope="root",
        scope_label="Root / Action",
        transform="rotation",
        transform_label="Rotation",
        blender_path_hint="rotation_quaternion",
        channel_labels=("w", "x", "y", "z"),
        is_quaternion=True,
    ),
    4: LmtUsageSemantics(
        usage=4,
        scope="root",
        scope_label="Root / Action",
        transform="translation",
        transform_label="Translation",
        blender_path_hint="location",
        channel_labels=("x", "y", "z"),
        is_quaternion=False,
    ),
    5: LmtUsageSemantics(
        usage=5,
        scope="root",
        scope_label="Root / Action",
        transform="scale",
        transform_label="Scale",
        blender_path_hint="scale",
        channel_labels=("x", "y", "z"),
        is_quaternion=False,
    ),
}

_BUFFER_TABLE = {
    1: LmtBufferSemantics(1, "fvec_basis", "Float basis vector", ("x", "y", "z"), None, False, False),
    2: LmtBufferSemantics(2, "fquat_basis", "Float basis quaternion", ("w", "x", "y", "z"), None, False, False),
    3: LmtBufferSemantics(3, "fvec_keys", "Float vector keys", ("x", "y", "z"), 16, True, False),
    4: LmtBufferSemantics(4, "u16_vec_lerp", "16-bit vector lerp", ("x", "y", "z"), 8, True, True),
    5: LmtBufferSemantics(5, "u8_vec_lerp", "8-bit vector lerp", ("x", "y", "z"), 4, True, True),
    6: LmtBufferSemantics(6, "q14_keys", "14-bit quaternion keys", ("w", "x", "y", "z"), 8, True, False),
    7: LmtBufferSemantics(7, "q7_lerp", "7-bit quaternion lerp", ("w", "x", "y", "z"), 4, True, True),
    11: LmtBufferSemantics(11, "qxw_lerp", "X/W quaternion union lerp", ("w", "x", "y", "z"), 4, True, True),
    12: LmtBufferSemantics(12, "qyw_lerp", "Y/W quaternion union lerp", ("w", "x", "y", "z"), 4, True, True),
    13: LmtBufferSemantics(13, "qzw_lerp", "Z/W quaternion union lerp", ("w", "x", "y", "z"), 4, True, True),
    14: LmtBufferSemantics(14, "q11_lerp", "11-bit quaternion lerp", ("w", "x", "y", "z"), 6, True, True),
    15: LmtBufferSemantics(15, "q9_lerp", "9-bit quaternion lerp", ("w", "x", "y", "z"), 5, True, True),
}


def get_usage_semantics(usage: int) -> LmtUsageSemantics:
    return _USAGE_TABLE.get(
        usage,
        LmtUsageSemantics(
            usage=usage,
            scope="unknown",
            scope_label="Unknown Scope",
            transform="unknown",
            transform_label="Unknown Transform",
            blender_path_hint="",
            channel_labels=("x", "y", "z"),
            is_quaternion=False,
        ),
    )


def get_buffer_semantics(buffer_type: int) -> LmtBufferSemantics:
    return _BUFFER_TABLE.get(
        buffer_type,
        LmtBufferSemantics(
            buffer_type=buffer_type,
            code=f"buffer_{buffer_type}",
            label=f"Unknown buffer {buffer_type}",
            channel_labels=("x", "y", "z"),
            keyframe_stride=None,
            stores_keyframes=False,
            uses_lerp_basis=False,
        ),
    )


def raw_key_count(buffer_type: int, buffer_size: int) -> int | None:
    semantics = get_buffer_semantics(buffer_type)
    if not semantics.stores_keyframes or not semantics.keyframe_stride:
        return 0
    if buffer_size < 0:
        return None
    if buffer_size % semantics.keyframe_stride != 0:
        return None
    return buffer_size // semantics.keyframe_stride
