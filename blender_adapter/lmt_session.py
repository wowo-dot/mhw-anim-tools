"""Translate parsed LMT files into Blender session-side summaries."""

from __future__ import annotations

from collections import Counter
import json

try:
    from ..core.formats.lmt.decoder import decode_action_tracks
    from ..core.formats.lmt.semantics import get_buffer_semantics
    from ..core.formats.lmt.semantics import get_usage_semantics
    from ..core.formats.lmt.semantics import raw_key_count
    from ..core.formats.timl.reader import read_timl_data_bytes
    from ..core.formats.timl.summary import build_data_entry_summary
except ImportError:  # pragma: no cover - test runner imports from addon root
    from core.formats.lmt.decoder import decode_action_tracks
    from core.formats.lmt.semantics import get_buffer_semantics
    from core.formats.lmt.semantics import get_usage_semantics
    from core.formats.lmt.semantics import raw_key_count
    from core.formats.timl.reader import read_timl_data_bytes
    from core.formats.timl.summary import build_data_entry_summary


def _format_vector(values):
    return ", ".join(f"{value:.4f}" for value in values)


def build_track_summary(track, decoded_track):
    usage = get_usage_semantics(track.header.usage)
    buffer_info = get_buffer_semantics(track.header.buffer_type)
    key_count = raw_key_count(track.header.buffer_type, track.header.buffer_size)
    return {
        "track_index": decoded_track.track_index,
        "bone_id": track.header.bone_id,
        "usage": track.header.usage,
        "usage_scope": usage.scope_label,
        "usage_label": f"{usage.scope_label} {usage.transform_label}",
        "transform_label": usage.transform_label,
        "blender_path_hint": usage.blender_path_hint,
        "channel_labels": ", ".join(usage.channel_labels),
        "buffer_type": track.header.buffer_type,
        "buffer_code": buffer_info.code,
        "buffer_label": buffer_info.label,
        "buffer_size": track.header.buffer_size,
        "buffer_offset": track.header.buffer_offset,
        "raw_key_count": key_count if key_count is not None else -1,
        "has_lerp": bool(track.lerp_basis),
        "weight": track.header.weight,
        "basis_preview": _format_vector(decoded_track.basis_value),
        "tail_frame": decoded_track.tail_frame or -1,
        "tail_preview": _format_vector(decoded_track.tail_value) if decoded_track.tail_value is not None else "",
        "decoded_key_count": decoded_track.decoded_key_count,
        "first_keyframe": decoded_track.first_keyframe or -1,
        "last_keyframe": decoded_track.last_keyframe or -1,
        "decode_error": decoded_track.decode_error or "",
        "unknown_tag": track.header.unknown_tag,
        "joint_type": track.header.joint_type,
    }


def _track_breakdown(track_summaries):
    counts = Counter(track["transform_label"] for track in track_summaries)
    parts = []
    for label in ("Rotation", "Translation", "Scale"):
        if counts[label]:
            parts.append(f"{counts[label]} {label.lower()[:3]}")
    return ", ".join(parts) if parts else "No tracks"


def _attached_timl_breakdown(counts: dict[str, int]) -> str:
    if not counts:
        return "No TIML transforms"
    return ", ".join(f"{int(value)} {str(label)}" for label, value in counts.items())


def _load_attached_timl_summary(lmt, action, source_bytes: bytes | None, cache: dict[int, dict[str, object]]) -> dict[str, object]:
    default_summary = {
        "timl_source_offset": int(action.header.timl_offset),
        "timl_type_count": 0,
        "timl_transform_count": 0,
        "timl_keyframe_count": 0,
        "timl_animation_length": 0.0,
        "timl_loop_start_point": 0.0,
        "timl_loop_control": 0,
        "timl_data_type_breakdown": "",
        "timl_timeline_breakdown": "",
        "timl_transform_payload": "[]",
        "timl_parse_error": "",
    }
    if not action.has_timl or source_bytes is None:
        return default_summary

    timl_offset = int(action.header.timl_offset)
    if timl_offset not in cache:
        try:
            timl_data = read_timl_data_bytes(
                source_bytes,
                data_offset=timl_offset,
                source_name=f"{lmt.source_name}#timl@0x{timl_offset:X}",
                entry_id=0,
            )
            data_summary = build_data_entry_summary(timl_data)
            cache[timl_offset] = {
                "timl_source_offset": timl_offset,
                "timl_type_count": int(data_summary["type_count"]),
                "timl_transform_count": int(data_summary["transform_count"]),
                "timl_keyframe_count": int(data_summary["keyframe_count"]),
                "timl_animation_length": float(data_summary["animation_length"]),
                "timl_loop_start_point": float(data_summary["loop_start_point"]),
                "timl_loop_control": int(data_summary["loop_control"]),
                "timl_data_type_breakdown": _attached_timl_breakdown(data_summary["data_type_counts"]),
                "timl_timeline_breakdown": _attached_timl_breakdown(data_summary["timeline_counts"]),
                "timl_transform_payload": json.dumps(data_summary["transform_payload"]),
                "timl_parse_error": "",
            }
        except Exception as exc:  # pragma: no cover - surfaced via diagnostics/UI
            cache[timl_offset] = {
                **default_summary,
                "timl_parse_error": str(exc),
            }
    return cache[timl_offset]


def build_action_summary(action, *, lmt=None, source_bytes: bytes | None = None, attached_timl_cache: dict[int, dict[str, object]] | None = None):
    decoded_action = decode_action_tracks(action, strict=False)
    track_summaries = [
        build_track_summary(track, decoded_track)
        for track, decoded_track in zip(action.tracks, decoded_action.tracks)
    ]
    cache = attached_timl_cache if attached_timl_cache is not None else {}
    timl_summary = _load_attached_timl_summary(lmt, action, source_bytes, cache) if lmt is not None else {
        "timl_source_offset": int(action.header.timl_offset),
        "timl_type_count": 0,
        "timl_transform_count": 0,
        "timl_keyframe_count": 0,
        "timl_animation_length": 0.0,
        "timl_loop_start_point": 0.0,
        "timl_loop_control": 0,
        "timl_data_type_breakdown": "",
        "timl_timeline_breakdown": "",
        "timl_transform_payload": "[]",
        "timl_parse_error": "",
    }
    return {
        "entry_id": action.id,
        "entry_state": "source",
        "has_source_action": True,
        "is_synthetic": False,
        "frame_count": action.header.frame_count,
        "loop_frame": action.header.loop_frame,
        "track_count": len(action.tracks),
        "has_timl": action.has_timl,
        "flags": int(action.header.flags),
        "flags2": int(action.header.flags2),
        "flags_hex": f"0x{action.header.flags:02X}",
        "flags2_hex": f"0x{action.header.flags2:02X}",
        "translation_preview": _format_vector(action.header.translation[:3]),
        "rotation_preview": _format_vector(action.header.rotation_lerp),
        "track_breakdown": _track_breakdown(track_summaries),
        "track_payload": json.dumps(track_summaries),
        **timl_summary,
    }


def build_empty_entry_summary(
    entry_id: int,
    *,
    entry_state: str = "source_hole",
    is_synthetic: bool = False,
    has_timl: bool = False,
) -> dict[str, object]:
    return {
        "entry_id": int(entry_id),
        "entry_state": str(entry_state or "source_hole"),
        "has_source_action": False,
        "is_synthetic": bool(is_synthetic),
        "frame_count": 0,
        "loop_frame": -1,
        "track_count": 0,
        "has_timl": bool(has_timl),
        "flags": 0,
        "flags2": 0,
        "flags_hex": "0x00",
        "flags2_hex": "0x00",
        "translation_preview": "0.0000, 0.0000, 0.0000",
        "rotation_preview": "0.0000, 0.0000, 0.0000, 1.0000",
        "track_breakdown": "No tracks",
        "track_payload": "[]",
        "timl_source_offset": 0,
        "timl_type_count": 0,
        "timl_transform_count": 0,
        "timl_keyframe_count": 0,
        "timl_animation_length": 0.0,
        "timl_loop_start_point": 0.0,
        "timl_loop_control": 0,
        "timl_data_type_breakdown": "",
        "timl_timeline_breakdown": "",
        "timl_transform_payload": "[]",
        "timl_parse_error": "",
    }


def build_file_summary(lmt, *, source_bytes: bytes | None = None):
    attached_timl_cache: dict[int, dict[str, object]] = {}
    actions_by_id = {
        int(action.id): action
        for action in getattr(lmt, "actions", ())
    }
    summaries = []
    for entry_id, entry_offset in enumerate(getattr(lmt, "entry_offsets", ())):
        if int(entry_offset) == 0:
            summaries.append(build_empty_entry_summary(entry_id))
            continue
        action = actions_by_id.get(int(entry_id))
        if action is None:
            summaries.append(build_empty_entry_summary(entry_id))
            continue
        summaries.append(
            build_action_summary(
                action,
                lmt=lmt,
                source_bytes=source_bytes,
                attached_timl_cache=attached_timl_cache,
            )
        )
    return summaries
