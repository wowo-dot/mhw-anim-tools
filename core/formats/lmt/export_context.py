"""Source-container metadata helpers for standalone LMT export.

The current writer intentionally emits a single-action LMT. This module keeps
the source-container safety checks close to the core LMT models so the Blender
UI can surface unsafe export cases without burying more policy in operators.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import struct

from ...diagnostics.errors import BinaryFormatError
from ...diagnostics.reports import Report


@dataclass(frozen=True)
class LmtSourceActionExportContext:
    source_name: str
    version: int
    header_unknown: bytes
    entry_count: int
    action_count: int
    action_id: int
    loop_frame: int
    null0: tuple[int, int, int]
    translation: tuple[float, float, float, float]
    rotation_lerp: tuple[float, float, float, float]
    flags: int
    null2: bytes
    flags2: int
    null3: tuple[int, int, int, int, int]
    has_timl: bool
    timl_offset: int
    track_metadata_by_identity: dict[tuple[int, int], dict[str, object]]
    track_metadata_by_index: dict[int, dict[str, object]]
    duplicate_track_identities: tuple[tuple[int, int, int], ...] = ()


@dataclass(frozen=True)
class RawTimlPayload:
    payload: bytes
    rebase_offsets: tuple[int, ...]

TIML_DATA_STRUCT = struct.Struct("<QQiiffiI")
TIML_TYPE_STRUCT = struct.Struct("<QQIi")
TIML_TRANSFORM_STRUCT = struct.Struct("<QQIi")
TIML_KEYFRAME_SIZE = 20


def _align(offset: int, alignment: int) -> int:
    return (offset + (alignment - 1)) & ~(alignment - 1)


def _validate_slice_bounds(
    source_bytes: bytes,
    *,
    offset: int,
    size: int,
    source_name: str,
    label: str,
    timl_offset: int,
) -> None:
    if offset < 0 or offset + size > len(source_bytes):
        raise BinaryFormatError(
            f"{label} points outside the available source bytes",
            source_name=source_name,
            timl_offset=timl_offset,
            offset=offset,
            size=size,
            file_size=len(source_bytes),
        )


def _timl_payload_layout(source_name: str, source_bytes: bytes, timl_offset: int) -> tuple[int, tuple[int, ...]]:
    _validate_slice_bounds(
        source_bytes,
        offset=timl_offset,
        size=TIML_DATA_STRUCT.size,
        source_name=source_name,
        label="TIML data header",
        timl_offset=timl_offset,
    )
    type_offset, type_count, _data_ix0, _data_ix1, _anim_length, _loop_start, _loop_control, _label_hash = (
        TIML_DATA_STRUCT.unpack_from(source_bytes, timl_offset)
    )
    end = _align(timl_offset + TIML_DATA_STRUCT.size, 16)
    rebase_offsets: list[int] = []
    if type_offset != 0:
        rebase_offsets.append(0)
    if type_count <= 0:
        return end, tuple(rebase_offsets)
    if type_offset == 0:
        raise BinaryFormatError(
            "TIML data has child types but no type-table offset",
            source_name=source_name,
            timl_offset=timl_offset,
            type_count=type_count,
        )

    _validate_slice_bounds(
        source_bytes,
        offset=type_offset,
        size=TIML_TYPE_STRUCT.size * int(type_count),
        source_name=source_name,
        label="TIML type table",
        timl_offset=timl_offset,
    )
    end = max(end, _align(int(type_offset) + (TIML_TYPE_STRUCT.size * int(type_count)), 16))

    transforms_to_read: list[tuple[int, int]] = []
    for type_index in range(int(type_count)):
        transform_struct_offset = int(type_offset) + (type_index * TIML_TYPE_STRUCT.size)
        transform_offset, transform_count, _timeline_parameter_hash, _unknown = TIML_TYPE_STRUCT.unpack_from(
            source_bytes,
            transform_struct_offset,
        )
        if transform_offset != 0:
            rebase_offsets.append(transform_struct_offset - timl_offset)
        if transform_count <= 0:
            continue
        if transform_offset == 0:
            raise BinaryFormatError(
                "TIML type has transforms but no transform-table offset",
                source_name=source_name,
                timl_offset=timl_offset,
                type_index=type_index,
                transform_count=transform_count,
            )
        _validate_slice_bounds(
            source_bytes,
            offset=transform_offset,
            size=TIML_TRANSFORM_STRUCT.size * int(transform_count),
            source_name=source_name,
            label="TIML transform table",
            timl_offset=timl_offset,
        )
        end = max(end, _align(int(transform_offset) + (TIML_TRANSFORM_STRUCT.size * int(transform_count)), 16))
        for transform_index in range(int(transform_count)):
            keyframe_struct_offset = int(transform_offset) + (transform_index * TIML_TRANSFORM_STRUCT.size)
            key_offset, key_count, _datatype_hash, _data_type = TIML_TRANSFORM_STRUCT.unpack_from(
                source_bytes,
                keyframe_struct_offset,
            )
            if key_offset != 0:
                rebase_offsets.append(keyframe_struct_offset - timl_offset)
            transforms_to_read.append((int(key_offset), int(key_count)))

    for key_offset, key_count in transforms_to_read:
        if key_count <= 0:
            continue
        if key_offset == 0:
            raise BinaryFormatError(
                "TIML transform has keyframes but no keyframe-table offset",
                source_name=source_name,
                timl_offset=timl_offset,
                key_count=key_count,
            )
        _validate_slice_bounds(
            source_bytes,
            offset=key_offset,
            size=TIML_KEYFRAME_SIZE * int(key_count),
            source_name=source_name,
            label="TIML keyframe table",
            timl_offset=timl_offset,
        )
        end = max(end, _align(int(key_offset) + (TIML_KEYFRAME_SIZE * int(key_count)), 16))
    return end, tuple(rebase_offsets)


def _track_metadata_map(action) -> dict[tuple[int, int], dict[str, object]]:
    return {
        (int(track.header.bone_id), int(track.header.usage)): {
            "buffer_type": int(track.header.buffer_type),
            "joint_type": int(track.header.joint_type),
            "unknown_tag": int(track.header.unknown_tag),
            "weight": float(track.header.weight),
            "lerp_mult": track.lerp_basis.mult if track.lerp_basis is not None else None,
            "lerp_add": track.lerp_basis.add if track.lerp_basis is not None else None,
        }
        for track in action.tracks
    }


def _track_metadata_map_by_index(action) -> dict[int, dict[str, object]]:
    return {
        int(track_index): {
            "buffer_type": int(track.header.buffer_type),
            "joint_type": int(track.header.joint_type),
            "unknown_tag": int(track.header.unknown_tag),
            "weight": float(track.header.weight),
            "lerp_mult": track.lerp_basis.mult if track.lerp_basis is not None else None,
            "lerp_add": track.lerp_basis.add if track.lerp_basis is not None else None,
            "bone_id": int(track.header.bone_id),
            "usage": int(track.header.usage),
        }
        for track_index, track in enumerate(action.tracks)
    }


def find_duplicate_track_identities(action) -> tuple[tuple[int, int, int], ...]:
    duplicate_counts = Counter(
        (int(track.header.bone_id), int(track.header.usage))
        for track in action.tracks
    )
    return tuple(
        (int(bone_id), int(usage), int(count))
        for (bone_id, usage), count in sorted(duplicate_counts.items())
        if int(count) > 1
    )


def build_source_action_export_context(lmt, action_id: int) -> LmtSourceActionExportContext:
    source_action = None
    for candidate in lmt.actions:
        if int(candidate.id) == int(action_id):
            source_action = candidate
            break
    if source_action is None:
        raise ValueError(f"Could not find action id {action_id} in source LMT '{lmt.source_name}'.")

    return LmtSourceActionExportContext(
        source_name=str(lmt.source_name),
        version=int(lmt.header.version),
        header_unknown=bytes(lmt.header.unknown),
        entry_count=int(lmt.header.entry_count),
        action_count=int(lmt.action_count),
        action_id=int(source_action.id),
        loop_frame=int(source_action.header.loop_frame),
        null0=tuple(int(value) for value in source_action.header.null0),
        translation=tuple(float(value) for value in source_action.header.translation),
        rotation_lerp=tuple(float(value) for value in source_action.header.rotation_lerp),
        flags=int(source_action.header.flags),
        null2=bytes(source_action.header.null2),
        flags2=int(source_action.header.flags2),
        null3=tuple(int(value) for value in source_action.header.null3),
        has_timl=bool(source_action.has_timl),
        timl_offset=int(source_action.header.timl_offset),
        track_metadata_by_identity=_track_metadata_map(source_action),
        track_metadata_by_index=_track_metadata_map_by_index(source_action),
        duplicate_track_identities=find_duplicate_track_identities(source_action),
    )


def extract_raw_timl_payload_layouts(lmt, source_bytes: bytes) -> dict[int, RawTimlPayload]:
    payloads: dict[int, RawTimlPayload] = {}
    for action in lmt.actions:
        offset = int(action.header.timl_offset)
        if offset == 0 or offset in payloads:
            continue
        end, rebase_offsets = _timl_payload_layout(lmt.source_name, source_bytes, offset)
        payloads[offset] = RawTimlPayload(
            payload=bytes(source_bytes[offset:end]),
            rebase_offsets=rebase_offsets,
        )
    return payloads


def extract_raw_timl_payloads(lmt, source_bytes: bytes) -> dict[int, bytes]:
    return {
        offset: payload.payload
        for offset, payload in extract_raw_timl_payload_layouts(lmt, source_bytes).items()
    }


def assess_standalone_export_context(context: LmtSourceActionExportContext | None) -> Report:
    report = Report()
    if context is None:
        report.add_warning(
            "lmt.export.standalone",
            "Exporting as a standalone single-action LMT because no source LMT context was available.",
        )
        return report

    if context.has_timl:
        report.add_error(
            "lmt.export.timl",
            "Source action has TIML attached; standalone LMT export would drop the TIML payload.",
        )
    if context.entry_count > 1 or context.action_count > 1:
        report.add_error(
            "lmt.export.container",
            "Source LMT contains multiple entries/actions; standalone export would not preserve sibling actions.",
        )
    return report
