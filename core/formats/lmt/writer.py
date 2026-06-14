"""Binary writer for reconstructed LMT actions.

This writer currently covers:

- basis vector tracks (`buffer_type` 1)
- basis quaternion tracks (`buffer_type` 2)
- float vector key tracks (`buffer_type` 3)
- 16-bit vector lerp tracks (`buffer_type` 4)
- 8-bit vector lerp tracks (`buffer_type` 5)
- q14 quaternion key tracks (`buffer_type` 6)
- quaternion lerp tracks (`buffer_type` 7, 11, 12, 13, 14, 15)

The writer stays conservative:
- it refuses duplicate `bone_id + usage` identities
- it validates component counts per usage
- it emits a plain single-action `.lmt` without TIML/events
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

from ...animation.transforms import wxyz_to_xyzw
from ...diagnostics.errors import ValidationError
from .encoding import encode_quaternion_lerp_keyframes
from .encoding import encode_vector_lerp_keyframes
from .encoding import prepare_track_keyframes
from .export_plan import plan_reconstructed_action_export
from .export_plan import resolve_action_frame_count
from .semantics import get_usage_semantics


HEADER_STRUCT = struct.Struct("<4shh8s")
ENTRY_OFFSET_STRUCT = struct.Struct("<Q")
ACTION_STRUCT = struct.Struct("<QIIi3i4f4fB2sB5iQ")
TRACK_STRUCT = struct.Struct("<BBBBifiq4fq")
FLOAT_VECTOR_KEY_STRUCT = struct.Struct("<3fI")
LERP_BASIS_STRUCT = struct.Struct("<4f4f")

EXPECTED_SIGNATURE = b"LMT\x00"
DEFAULT_VERSION = 95


@dataclass(frozen=True)
class LmtTrackWriteMetadata:
    joint_type: int = 0
    unknown_tag: int = 205
    weight: float = 1.0


def _align(offset: int, alignment: int) -> int:
    return (offset + (alignment - 1)) & ~(alignment - 1)


def _pad_to(data: bytearray, alignment: int) -> None:
    padded_size = _align(len(data), alignment)
    if padded_size > len(data):
        data.extend(b"\x00" * (padded_size - len(data)))


def _encode_q14_component(value: float) -> int:
    half_value = float(value) / 2.0
    if half_value < 0.0:
        magnitude = round(abs(half_value) * ((1 << 13) - 1))
        return magnitude ^ ((1 << 14) - 1)
    return round(half_value * ((1 << 13) - 1))


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


def _default_root_translation() -> tuple[float, float, float, float]:
    return (0.0, 0.0, 0.0, 0.0)


def _default_root_rotation_xyzw() -> tuple[float, float, float, float]:
    return (0.0, 0.0, 0.0, 1.0)


def _action_tail_header_values(reconstructed_action) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
    translation = _default_root_translation()
    rotation_xyzw = _default_root_rotation_xyzw()
    for track in reconstructed_action.tracks:
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
            rotation_xyzw = wxyz_to_xyzw(tuple(float(component) for component in track.tail_value))
    return translation, rotation_xyzw


def _prepare_encoded_keyframes(track, terminal_frame: int, *, max_delta: int | None = None):
    prepared = prepare_track_keyframes(track, terminal_frame)
    if max_delta is not None:
        for _frame, _value, delta in prepared:
            if delta > int(max_delta):
                raise ValidationError(
                    f"Track delta {delta} exceeds the {max_delta}-frame limit for buffer_type 6 "
                    f"(bone_id={track.bone_id}, usage={track.usage})."
                )
    return prepared


def _encode_float_vector_track(track, action_frame_count: int) -> bytes:
    prepared = _prepare_encoded_keyframes(track, action_frame_count + 1)
    return b"".join(
        FLOAT_VECTOR_KEY_STRUCT.pack(
            float(value[0]),
            float(value[1]),
            float(value[2]),
            int(delta),
        )
        for _frame, value, delta in prepared
    )


def _encode_q14_track(track, action_frame_count: int) -> bytes:
    prepared = _prepare_encoded_keyframes(track, action_frame_count + 1, max_delta=255)
    return b"".join(
        _pack_bits(
            [
                (_encode_q14_component(value[0]), 14),
                (_encode_q14_component(value[3]), 14),
                (_encode_q14_component(value[2]), 14),
                (_encode_q14_component(value[1]), 14),
                (int(delta), 8),
            ]
        )
        for _frame, value, delta in prepared
    )


def _basis_xyzw(track, usage_info) -> tuple[float, float, float, float]:
    if usage_info.is_quaternion:
        return wxyz_to_xyzw(tuple(float(component) for component in track.basis_value))
    return (
        float(track.basis_value[0]),
        float(track.basis_value[1]),
        float(track.basis_value[2]),
        0.0,
    )


def _track_write_metadata(track_metadata_by_identity, bone_id: int, usage: int) -> LmtTrackWriteMetadata:
    if not track_metadata_by_identity:
        return LmtTrackWriteMetadata()
    metadata = track_metadata_by_identity.get((int(bone_id), int(usage)))
    if metadata is None:
        return LmtTrackWriteMetadata()
    if isinstance(metadata, LmtTrackWriteMetadata):
        return metadata
    return LmtTrackWriteMetadata(
        joint_type=int(metadata.get("joint_type", 0)),
        unknown_tag=int(metadata.get("unknown_tag", 205)),
        weight=float(metadata.get("weight", 1.0)),
    )


def _encode_track_buffer(track, planned_track, action_frame_count: int) -> bytes:
    if planned_track.buffer_type in {1, 2}:
        return b""
    if planned_track.buffer_type == 3:
        return _encode_float_vector_track(track, action_frame_count)
    if planned_track.buffer_type in {4, 5}:
        if planned_track.lerp_mult is None or planned_track.lerp_add is None:
            raise ValidationError(
                f"Vector lerp buffer_type {planned_track.buffer_type} requires lerp basis metadata "
                f"(bone_id={track.bone_id}, usage={track.usage})."
            )
        return encode_vector_lerp_keyframes(
            track,
            buffer_type=planned_track.buffer_type,
            lerp_mult=planned_track.lerp_mult,
            lerp_add=planned_track.lerp_add,
            terminal_frame=action_frame_count + 1,
        )
    if planned_track.buffer_type in {7, 11, 12, 13, 14, 15}:
        if planned_track.lerp_mult is None or planned_track.lerp_add is None:
            raise ValidationError(
                f"Quaternion lerp buffer_type {planned_track.buffer_type} requires lerp basis metadata "
                f"(bone_id={track.bone_id}, usage={track.usage})."
            )
        return encode_quaternion_lerp_keyframes(
            track,
            buffer_type=planned_track.buffer_type,
            lerp_mult=planned_track.lerp_mult,
            lerp_add=planned_track.lerp_add,
            terminal_frame=action_frame_count + 1,
        )
    if planned_track.buffer_type == 6:
        return _encode_q14_track(track, action_frame_count)
    raise ValidationError(
        f"Buffer type {planned_track.buffer_type} is not supported by the first writer milestone."
    )


def write_lmt_bytes(
    reconstructed_action,
    *,
    version: int = DEFAULT_VERSION,
    header_unknown: bytes = b"\x00" * 8,
    action_id: int = 0,
    loop_frame: int = -1,
    flags: int = 0,
    flags2: int = 0,
    track_metadata_by_identity: dict[tuple[int, int], LmtTrackWriteMetadata | dict[str, float | int]] | None = None,
    raw_quaternion_source_identities: frozenset[tuple[int, int]] | set[tuple[int, int]] | None = None,
) -> bytes:
    if len(header_unknown) != 8:
        raise ValidationError("LMT header unknown bytes must be exactly 8 bytes long.")
    plan = plan_reconstructed_action_export(
        reconstructed_action,
        track_metadata_by_identity=track_metadata_by_identity,
        raw_quaternion_source_identities=raw_quaternion_source_identities,
    )
    if plan.error_count:
        messages = "; ".join(diagnostic.message for diagnostic in plan.diagnostics if diagnostic.level == "ERROR")
        raise ValidationError(f"Cannot write LMT action '{reconstructed_action.action_name}': {messages}")

    action_frame_count = resolve_action_frame_count(reconstructed_action)
    root_translation, root_rotation_xyzw = _action_tail_header_values(reconstructed_action)

    encoded_tracks = []
    for reconstructed_track, planned_track in zip(reconstructed_action.tracks, plan.tracks):
        metadata = _track_write_metadata(track_metadata_by_identity, reconstructed_track.bone_id, reconstructed_track.usage)
        usage_info = get_usage_semantics(reconstructed_track.usage)
        raw_buffer = _encode_track_buffer(reconstructed_track, planned_track, action_frame_count)
        encoded_tracks.append(
            {
                "track": reconstructed_track,
                "planned": planned_track,
                "metadata": metadata,
                "usage_info": usage_info,
                "raw_buffer": raw_buffer,
            }
        )

    entry_table_size = ENTRY_OFFSET_STRUCT.size
    action_offset = _align(HEADER_STRUCT.size + entry_table_size, 16)
    fcurve_offset = action_offset + ACTION_STRUCT.size
    track_table_size = TRACK_STRUCT.size * len(encoded_tracks)
    data = bytearray()
    data.extend(HEADER_STRUCT.pack(EXPECTED_SIGNATURE, int(version), 1, bytes(header_unknown)))
    data.extend(ENTRY_OFFSET_STRUCT.pack(action_offset))
    _pad_to(data, 16)

    current_buffer_offset = fcurve_offset + track_table_size
    track_headers = []
    buffer_chunks: list[bytes] = []
    for item in encoded_tracks:
        raw_buffer = item["raw_buffer"]
        lerp_bytes = b""
        if item["planned"].lerp_mult is not None and item["planned"].lerp_add is not None:
            lerp_bytes = LERP_BASIS_STRUCT.pack(
                *item["planned"].lerp_mult,
                *item["planned"].lerp_add,
            )
        buffer_offset = current_buffer_offset if raw_buffer else 0
        if raw_buffer:
            current_buffer_offset = _align(current_buffer_offset + len(raw_buffer), 4)
        lerp_offset = current_buffer_offset if lerp_bytes else 0
        if lerp_bytes:
            current_buffer_offset = _align(current_buffer_offset + len(lerp_bytes), 4)
        track_headers.append(
            TRACK_STRUCT.pack(
                int(item["planned"].buffer_type),
                int(item["track"].usage),
                int(item["metadata"].joint_type),
                int(item["metadata"].unknown_tag),
                int(item["track"].bone_id),
                float(item["metadata"].weight),
                len(raw_buffer),
                int(buffer_offset),
                *_basis_xyzw(item["track"], item["usage_info"]),
                int(lerp_offset),
            )
        )
        if raw_buffer:
            buffer_chunks.append(raw_buffer)
        if lerp_bytes:
            buffer_chunks.append(lerp_bytes)

    data.extend(
        ACTION_STRUCT.pack(
            fcurve_offset,
            len(encoded_tracks),
            int(action_frame_count),
            int(loop_frame),
            0,
            0,
            0,
            *root_translation,
            *root_rotation_xyzw,
            int(flags),
            b"\x00\x00",
            int(flags2),
            0,
            0,
            0,
            0,
            0,
            0,
        )
    )
    for packed_track in track_headers:
        data.extend(packed_track)
    for raw_buffer in buffer_chunks:
        data.extend(raw_buffer)
        _pad_to(data, 4)
    return bytes(data)


def write_lmt_file(
    path: str | Path,
    reconstructed_action,
    **kwargs,
) -> Path:
    output_path = Path(path)
    output_path.write_bytes(write_lmt_bytes(reconstructed_action, **kwargs))
    return output_path
