"""Source-container merge writer for reconstructed LMT actions.

This writer replaces one action inside a parsed source LMT while preserving:

- source container entry count and zero-entry holes
- sibling actions
- raw TIML payload bytes, including shared TIML offsets

It deliberately stays conservative:
- only the selected action is regenerated from reconstructed samples
- sibling actions are copied from parsed source data
- TIML subtrees are preserved raw unless a validated replacement payload is supplied
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

from ...animation.transforms import wxyz_to_xyzw
from ...diagnostics.errors import ValidationError
from .export_context import extract_raw_timl_payload_layouts
from .export_plan import plan_reconstructed_action_export
from .export_plan import resolve_action_frame_count
from .semantics import get_usage_semantics
from .writer import ACTION_STRUCT
from .writer import DEFAULT_VERSION
from .writer import ENTRY_OFFSET_STRUCT
from .writer import EXPECTED_SIGNATURE
from .writer import HEADER_STRUCT
from .writer import LERP_BASIS_STRUCT
from .writer import TRACK_STRUCT
from .writer import _align
from .writer import _basis_xyzw
from .writer import _encode_track_buffer
from .writer import _pad_to
from .writer import _track_write_metadata


UINT64_STRUCT = struct.Struct("<Q")


@dataclass(frozen=True)
class _SerializedTrack:
    buffer_type: int
    usage: int
    joint_type: int
    unknown_tag: int
    bone_id: int
    weight: float
    basis_xyzw: tuple[float, float, float, float]
    raw_buffer: bytes
    lerp_bytes: bytes


@dataclass(frozen=True)
class _SerializedAction:
    action_id: int
    frame_count: int
    loop_frame: int
    null0: tuple[int, int, int]
    translation: tuple[float, float, float, float]
    rotation_lerp: tuple[float, float, float, float]
    flags: int
    null2: bytes
    flags2: int
    null3: tuple[int, int, int, int, int]
    timl_source_offset: int
    tracks: tuple[_SerializedTrack, ...]


def _action_by_id(lmt, action_id: int):
    for action in lmt.actions:
        if int(action.id) == int(action_id):
            return action
    raise ValidationError(f"Could not find source action id {action_id} in '{lmt.source_name}'.")


def _source_track_metadata_map(action) -> dict[tuple[int, int], dict[str, object]]:
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


def _serialize_source_track(track) -> _SerializedTrack:
    lerp_bytes = b""
    if track.lerp_basis is not None:
        lerp_bytes = LERP_BASIS_STRUCT.pack(
            *tuple(float(value) for value in track.lerp_basis.mult),
            *tuple(float(value) for value in track.lerp_basis.add),
        )
    return _SerializedTrack(
        buffer_type=int(track.header.buffer_type),
        usage=int(track.header.usage),
        joint_type=int(track.header.joint_type),
        unknown_tag=int(track.header.unknown_tag),
        bone_id=int(track.header.bone_id),
        weight=float(track.header.weight),
        basis_xyzw=tuple(float(value) for value in track.header.basis),
        raw_buffer=bytes(track.raw_buffer),
        lerp_bytes=lerp_bytes,
    )


def _serialize_source_action(action) -> _SerializedAction:
    return _SerializedAction(
        action_id=int(action.id),
        frame_count=int(action.header.frame_count),
        loop_frame=int(action.header.loop_frame),
        null0=tuple(int(value) for value in action.header.null0),
        translation=tuple(float(value) for value in action.header.translation),
        rotation_lerp=tuple(float(value) for value in action.header.rotation_lerp),
        flags=int(action.header.flags),
        null2=bytes(action.header.null2),
        flags2=int(action.header.flags2),
        null3=tuple(int(value) for value in action.header.null3),
        timl_source_offset=int(action.header.timl_offset),
        tracks=tuple(_serialize_source_track(track) for track in action.tracks),
    )


def _resolved_action_header_vectors(
    reconstructed_action,
    source_action,
    *,
    preserve_source_identities: frozenset[tuple[int, int]] | set[tuple[int, int]] = frozenset(),
) -> tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]:
    translation = tuple(float(value) for value in source_action.header.translation)
    rotation_lerp = tuple(float(value) for value in source_action.header.rotation_lerp)
    for track in reconstructed_action.tracks:
        if (int(track.bone_id), int(track.usage)) in preserve_source_identities:
            continue
        usage_info = get_usage_semantics(track.usage)
        if usage_info.scope != "root" or track.tail_value is None:
            continue
        if usage_info.transform == "translation":
            translation = (
                float(track.tail_value[0]),
                float(track.tail_value[1]),
                float(track.tail_value[2]),
                0.0,
            )
        elif usage_info.transform == "rotation":
            rotation_lerp = wxyz_to_xyzw(tuple(float(component) for component in track.tail_value))
    return translation, rotation_lerp


def _serialize_reconstructed_action(
    reconstructed_action,
    source_action,
    *,
    track_metadata_by_identity: dict[tuple[int, int], dict[str, object]] | None = None,
    preserve_source_identities: frozenset[tuple[int, int]] | set[tuple[int, int]] | None = None,
    raw_quaternion_source_identities: frozenset[tuple[int, int]] | set[tuple[int, int]] | None = None,
) -> _SerializedAction:
    metadata_map = track_metadata_by_identity or _source_track_metadata_map(source_action)
    preserve_source_identities = frozenset(preserve_source_identities or ())
    plan = plan_reconstructed_action_export(
        reconstructed_action,
        track_metadata_by_identity=metadata_map,
        preserve_source_identities=preserve_source_identities,
        raw_quaternion_source_identities=raw_quaternion_source_identities,
    )
    if plan.error_count:
        messages = "; ".join(diagnostic.message for diagnostic in plan.diagnostics if diagnostic.level == "ERROR")
        raise ValidationError(f"Cannot merge-export LMT action '{reconstructed_action.action_name}': {messages}")

    action_frame_count = resolve_action_frame_count(reconstructed_action)
    translation, rotation_lerp = _resolved_action_header_vectors(
        reconstructed_action,
        source_action,
        preserve_source_identities=preserve_source_identities,
    )
    source_tracks_by_identity = {
        (int(track.header.bone_id), int(track.header.usage)): track
        for track in source_action.tracks
    }

    serialized_tracks: list[_SerializedTrack] = []
    for reconstructed_track, planned_track in zip(reconstructed_action.tracks, plan.tracks):
        identity = (int(reconstructed_track.bone_id), int(reconstructed_track.usage))
        if planned_track.preserve_source_raw:
            source_track = source_tracks_by_identity.get(identity)
            if source_track is None:
                raise ValidationError(
                    f"Could not preserve raw source track for bone_id={reconstructed_track.bone_id}, usage={reconstructed_track.usage} because the source track was missing."
                )
            serialized_tracks.append(_serialize_source_track(source_track))
            continue
        metadata = _track_write_metadata(metadata_map, reconstructed_track.bone_id, reconstructed_track.usage)
        usage_info = get_usage_semantics(reconstructed_track.usage)
        raw_buffer = _encode_track_buffer(reconstructed_track, planned_track, action_frame_count)
        lerp_bytes = b""
        if planned_track.lerp_mult is not None and planned_track.lerp_add is not None:
            lerp_bytes = LERP_BASIS_STRUCT.pack(
                *tuple(float(value) for value in planned_track.lerp_mult),
                *tuple(float(value) for value in planned_track.lerp_add),
            )
        serialized_tracks.append(
            _SerializedTrack(
                buffer_type=int(planned_track.buffer_type),
                usage=int(reconstructed_track.usage),
                joint_type=int(metadata.joint_type),
                unknown_tag=int(metadata.unknown_tag),
                bone_id=int(reconstructed_track.bone_id),
                weight=float(metadata.weight),
                basis_xyzw=_basis_xyzw(reconstructed_track, usage_info),
                raw_buffer=raw_buffer,
                lerp_bytes=lerp_bytes,
            )
        )

    return _SerializedAction(
        action_id=int(source_action.id),
        frame_count=int(action_frame_count),
        loop_frame=int(source_action.header.loop_frame),
        null0=tuple(int(value) for value in source_action.header.null0),
        translation=translation,
        rotation_lerp=rotation_lerp,
        flags=int(source_action.header.flags),
        null2=bytes(source_action.header.null2),
        flags2=int(source_action.header.flags2),
        null3=tuple(int(value) for value in source_action.header.null3),
        timl_source_offset=int(source_action.header.timl_offset),
        tracks=tuple(serialized_tracks),
    )


def _serialized_action_size(action: _SerializedAction) -> int:
    current_offset = ACTION_STRUCT.size + (TRACK_STRUCT.size * len(action.tracks))
    current_offset = _align(current_offset, 4)
    for track in action.tracks:
        if track.raw_buffer:
            current_offset += len(track.raw_buffer)
            current_offset = _align(current_offset, 4)
        if track.lerp_bytes:
            current_offset += len(track.lerp_bytes)
            current_offset = _align(current_offset, 4)
    return current_offset


def _serialize_action_bytes(
    action_offset: int,
    action: _SerializedAction,
    *,
    timl_offset: int,
) -> bytes:
    track_table_offset = action_offset + ACTION_STRUCT.size if action.tracks else 0
    current_buffer_offset = action_offset + ACTION_STRUCT.size + (TRACK_STRUCT.size * len(action.tracks))
    current_buffer_offset = _align(current_buffer_offset, 4)

    track_headers: list[bytes] = []
    buffer_chunks: list[bytes] = []
    for track in action.tracks:
        buffer_offset = current_buffer_offset if track.raw_buffer else 0
        if track.raw_buffer:
            current_buffer_offset += len(track.raw_buffer)
            current_buffer_offset = _align(current_buffer_offset, 4)

        lerp_offset = current_buffer_offset if track.lerp_bytes else 0
        if track.lerp_bytes:
            current_buffer_offset += len(track.lerp_bytes)
            current_buffer_offset = _align(current_buffer_offset, 4)

        track_headers.append(
            TRACK_STRUCT.pack(
                int(track.buffer_type),
                int(track.usage),
                int(track.joint_type),
                int(track.unknown_tag),
                int(track.bone_id),
                float(track.weight),
                len(track.raw_buffer),
                int(buffer_offset),
                *track.basis_xyzw,
                int(lerp_offset),
            )
        )
        if track.raw_buffer:
            buffer_chunks.append(track.raw_buffer)
        if track.lerp_bytes:
            buffer_chunks.append(track.lerp_bytes)

    data = bytearray()
    data.extend(
        ACTION_STRUCT.pack(
            int(track_table_offset),
            len(action.tracks),
            int(action.frame_count),
            int(action.loop_frame),
            *tuple(int(value) for value in action.null0),
            *tuple(float(value) for value in action.translation),
            *tuple(float(value) for value in action.rotation_lerp),
            int(action.flags),
            bytes(action.null2),
            int(action.flags2),
            *tuple(int(value) for value in action.null3),
            int(timl_offset),
        )
    )
    for packed_track in track_headers:
        data.extend(packed_track)
    _pad_to(data, 4)
    for chunk in buffer_chunks:
        data.extend(chunk)
        _pad_to(data, 4)
    return bytes(data)


def _rebase_timl_payload(payload, *, source_offset: int, target_offset: int) -> bytes:
    if int(source_offset) == int(target_offset):
        return bytes(payload.payload)
    delta = int(target_offset) - int(source_offset)
    rebased = bytearray(payload.payload)
    for relative_offset in payload.rebase_offsets:
        if relative_offset < 0 or relative_offset + UINT64_STRUCT.size > len(rebased):
            raise ValidationError(
                f"TIML rebase metadata pointed outside the raw payload slice at relative offset {relative_offset}."
            )
        (absolute_offset,) = UINT64_STRUCT.unpack_from(rebased, relative_offset)
        if absolute_offset == 0:
            continue
        UINT64_STRUCT.pack_into(rebased, relative_offset, int(absolute_offset) + delta)
    return bytes(rebased)


def write_merged_lmt_bytes(
    source_lmt,
    source_bytes: bytes,
    reconstructed_action,
    *,
    action_id: int,
    version: int | None = None,
    header_unknown: bytes | None = None,
    track_metadata_by_identity: dict[tuple[int, int], dict[str, object]] | None = None,
    preserve_source_identities: frozenset[tuple[int, int]] | set[tuple[int, int]] | None = None,
    raw_quaternion_source_identities: frozenset[tuple[int, int]] | set[tuple[int, int]] | None = None,
    replacement_timl_payloads: dict[int, object] | None = None,
) -> bytes:
    return write_multi_merged_lmt_bytes(
        source_lmt,
        source_bytes,
        {int(action_id): reconstructed_action},
        version=version,
        header_unknown=header_unknown,
        track_metadata_by_action_id={int(action_id): track_metadata_by_identity} if track_metadata_by_identity is not None else None,
        preserve_source_identities_by_action_id={int(action_id): preserve_source_identities} if preserve_source_identities is not None else None,
        raw_quaternion_source_identities_by_action_id={int(action_id): raw_quaternion_source_identities} if raw_quaternion_source_identities is not None else None,
        replacement_timl_payloads=replacement_timl_payloads,
    )


def write_multi_merged_lmt_bytes(
    source_lmt,
    source_bytes: bytes,
    reconstructed_actions_by_id: dict[int, object],
    *,
    version: int | None = None,
    header_unknown: bytes | None = None,
    track_metadata_by_action_id: dict[int, dict[tuple[int, int], dict[str, object]] | None] | None = None,
    preserve_source_identities_by_action_id: dict[int, frozenset[tuple[int, int]] | set[tuple[int, int]] | None] | None = None,
    raw_quaternion_source_identities_by_action_id: dict[int, frozenset[tuple[int, int]] | set[tuple[int, int]] | None] | None = None,
    replacement_timl_payloads: dict[int, object] | None = None,
) -> bytes:
    if not reconstructed_actions_by_id:
        raise ValidationError("At least one reconstructed source action is required for merged LMT export.")

    normalized_reconstructed_actions_by_id = {
        int(action_id): reconstructed_action
        for action_id, reconstructed_action in dict(reconstructed_actions_by_id).items()
    }
    track_metadata_by_action_id = {
        int(action_id): metadata
        for action_id, metadata in dict(track_metadata_by_action_id or {}).items()
    }
    preserve_source_identities_by_action_id = {
        int(action_id): identities
        for action_id, identities in dict(preserve_source_identities_by_action_id or {}).items()
    }
    raw_quaternion_source_identities_by_action_id = {
        int(action_id): identities
        for action_id, identities in dict(raw_quaternion_source_identities_by_action_id or {}).items()
    }

    source_actions_by_id = {int(action.id): action for action in source_lmt.actions}
    missing_action_ids = sorted(
        action_id
        for action_id in normalized_reconstructed_actions_by_id
        if action_id not in source_actions_by_id
    )
    if missing_action_ids:
        labels = ", ".join(f"{action_id:03d}" for action_id in missing_action_ids)
        raise ValidationError(
            f"Could not find source action id(s) {labels} in '{source_lmt.source_name}'."
        )

    timl_payloads = dict(extract_raw_timl_payload_layouts(source_lmt, source_bytes))
    if replacement_timl_payloads:
        timl_payloads.update({int(offset): payload for offset, payload in replacement_timl_payloads.items()})

    action_records_by_id: dict[int, _SerializedAction] = {}
    for entry_id, entry_offset in enumerate(source_lmt.entry_offsets):
        if int(entry_offset) == 0:
            continue
        source_entry_action = source_actions_by_id.get(entry_id)
        if source_entry_action is None:
            raise ValidationError(
                f"Source LMT entry {entry_id} points to an action offset but no parsed action was available."
            )
        if entry_id in normalized_reconstructed_actions_by_id:
            action_records_by_id[entry_id] = _serialize_reconstructed_action(
                normalized_reconstructed_actions_by_id[entry_id],
                source_entry_action,
                track_metadata_by_identity=track_metadata_by_action_id.get(entry_id),
                preserve_source_identities=preserve_source_identities_by_action_id.get(entry_id),
                raw_quaternion_source_identities=raw_quaternion_source_identities_by_action_id.get(entry_id),
            )
        else:
            action_records_by_id[entry_id] = _serialize_source_action(source_entry_action)

    resolved_version = int(source_lmt.header.version if version is None else version)
    resolved_header_unknown = bytes(source_lmt.header.unknown if header_unknown is None else header_unknown)
    if len(resolved_header_unknown) != 8:
        raise ValidationError("LMT header unknown bytes must be exactly 8 bytes long.")

    header_size = HEADER_STRUCT.size + (ENTRY_OFFSET_STRUCT.size * len(source_lmt.entry_offsets))
    entry_offsets = [0] * len(source_lmt.entry_offsets)
    cursor = _align(header_size, 16)
    for entry_id, source_entry_offset in enumerate(source_lmt.entry_offsets):
        if int(source_entry_offset) == 0:
            continue
        cursor = _align(cursor, 16)
        entry_offsets[entry_id] = cursor
        cursor += _serialized_action_size(action_records_by_id[entry_id])

    timl_payload_order: list[int] = []
    for entry_id, source_entry_offset in enumerate(source_lmt.entry_offsets):
        if int(source_entry_offset) == 0:
            continue
        timl_source_offset = int(action_records_by_id[entry_id].timl_source_offset)
        if timl_source_offset and timl_source_offset not in timl_payload_order:
            timl_payload_order.append(timl_source_offset)

    timl_offsets: dict[int, int] = {}
    cursor = _align(cursor, 16)
    for payload_index, timl_source_offset in enumerate(timl_payload_order):
        payload = timl_payloads.get(timl_source_offset)
        if payload is None:
            raise ValidationError(
                f"Could not preserve TIML payload at source offset {timl_source_offset} from '{source_lmt.source_name}'."
            )
        cursor = _align(cursor, 16)
        timl_offsets[timl_source_offset] = cursor
        cursor += len(payload.payload)
        if payload_index + 1 < len(timl_payload_order):
            cursor = _align(cursor, 16)

    data = bytearray()
    data.extend(
        HEADER_STRUCT.pack(
            EXPECTED_SIGNATURE,
            int(resolved_version),
            len(source_lmt.entry_offsets),
            resolved_header_unknown,
        )
    )
    for entry_offset in entry_offsets:
        data.extend(ENTRY_OFFSET_STRUCT.pack(int(entry_offset)))
    _pad_to(data, 16)

    for entry_id, source_entry_offset in enumerate(source_lmt.entry_offsets):
        if int(source_entry_offset) == 0:
            continue
        action_offset = entry_offsets[entry_id]
        if len(data) < action_offset:
            data.extend(b"\x00" * (action_offset - len(data)))
        action = action_records_by_id[entry_id]
        data.extend(
            _serialize_action_bytes(
                action_offset,
                action,
                timl_offset=timl_offsets.get(int(action.timl_source_offset), 0),
            )
        )

    for payload_index, timl_source_offset in enumerate(timl_payload_order):
        payload = timl_payloads[timl_source_offset]
        payload_offset = timl_offsets[timl_source_offset]
        if len(data) < payload_offset:
            data.extend(b"\x00" * (payload_offset - len(data)))
        data.extend(
            _rebase_timl_payload(
                payload,
                source_offset=int(timl_source_offset),
                target_offset=int(payload_offset),
            )
        )
        if payload_index + 1 < len(timl_payload_order):
            _pad_to(data, 16)

    return bytes(data)


def write_merged_lmt_file(
    path: str | Path,
    source_lmt,
    source_bytes: bytes,
    reconstructed_action,
    **kwargs,
) -> Path:
    output_path = Path(path)
    output_path.write_bytes(
        write_merged_lmt_bytes(
            source_lmt,
            source_bytes,
            reconstructed_action,
            **kwargs,
        )
    )
    return output_path


def write_multi_merged_lmt_file(
    path: str | Path,
    source_lmt,
    source_bytes: bytes,
    reconstructed_actions_by_id: dict[int, object],
    **kwargs,
) -> Path:
    output_path = Path(path)
    output_path.write_bytes(
        write_multi_merged_lmt_bytes(
            source_lmt,
            source_bytes,
            reconstructed_actions_by_id,
            **kwargs,
        )
    )
    return output_path
