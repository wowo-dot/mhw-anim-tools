"""Translate parsed LMT files into Blender session-side summaries."""

from __future__ import annotations

from collections import Counter
import json

try:
    from ..core.formats.lmt.decoder import decode_action_tracks
    from ..core.formats.lmt.semantics import get_buffer_semantics
    from ..core.formats.lmt.semantics import get_usage_semantics
    from ..core.formats.lmt.semantics import raw_key_count
except ImportError:  # pragma: no cover - test runner imports from addon root
    from core.formats.lmt.decoder import decode_action_tracks
    from core.formats.lmt.semantics import get_buffer_semantics
    from core.formats.lmt.semantics import get_usage_semantics
    from core.formats.lmt.semantics import raw_key_count


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


def build_action_summary(action):
    decoded_action = decode_action_tracks(action, strict=False)
    track_summaries = [
        build_track_summary(track, decoded_track)
        for track, decoded_track in zip(action.tracks, decoded_action.tracks)
    ]
    return {
        "entry_id": action.id,
        "frame_count": action.header.frame_count,
        "loop_frame": action.header.loop_frame,
        "track_count": len(action.tracks),
        "has_timl": action.has_timl,
        "flags_hex": f"0x{action.header.flags:02X}",
        "flags2_hex": f"0x{action.header.flags2:02X}",
        "translation_preview": _format_vector(action.header.translation[:3]),
        "rotation_preview": _format_vector(action.header.rotation_lerp),
        "track_breakdown": _track_breakdown(track_summaries),
        "track_payload": json.dumps(track_summaries),
    }


def build_file_summary(lmt):
    return [build_action_summary(action) for action in lmt.actions]
