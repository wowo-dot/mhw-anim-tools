"""Build compact summaries from parsed TIML files."""

from __future__ import annotations

from collections import Counter
import math

from .semantics import format_datatype_hash_label
from .semantics import format_timeline_parameter_label
from .semantics import get_data_type_semantics
from .semantics import get_interpolation_label


def _is_integral_frame(value: float) -> bool:
    rounded = round(float(value))
    return math.isclose(float(value), float(rounded), rel_tol=0.0, abs_tol=1e-6)


def _format_value_preview(value) -> str:
    if isinstance(value, tuple):
        return ", ".join(str(int(component)) for component in value)
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(int(value))


def _sorted_count_dict(counter: Counter) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in sorted(counter.items(), key=lambda item: (-item[1], str(item[0])))
    }


def build_transform_summary(
    transform,
    *,
    type_index: int,
    transform_index: int,
    timeline_parameter_hash: int,
    timeline_parameter_names: dict[int, str] | None = None,
    datatype_hash_names: dict[int, str] | None = None,
) -> dict[str, object]:
    semantics = get_data_type_semantics(transform.data_type)
    interpolation_counts = Counter(
        get_interpolation_label(keyframe.interpolation)
        for keyframe in transform.keyframes
    )
    easing_counts = Counter(int(keyframe.easing) for keyframe in transform.keyframes)
    frame_timings = [float(keyframe.frame_timing) for keyframe in transform.keyframes]
    fractional_key_count = sum(1 for value in frame_timings if not _is_integral_frame(value))
    value_preview = _format_value_preview(transform.keyframes[0].value) if transform.keyframes else ""
    return {
        "type_index": int(type_index),
        "transform_index": int(transform_index),
        "datatype_hash": int(transform.datatype_hash),
        "datatype_label": format_datatype_hash_label(int(transform.datatype_hash), datatype_hash_names),
        "timeline_parameter_hash": int(timeline_parameter_hash),
        "timeline_parameter_label": format_timeline_parameter_label(int(timeline_parameter_hash), timeline_parameter_names),
        "data_type": int(transform.data_type),
        "data_type_name": semantics.name,
        "value_kind": semantics.value_kind,
        "value_dimension": semantics.value_dimension,
        "control_kind": semantics.control_kind,
        "keyframe_count": len(transform.keyframes),
        "fractional_key_count": int(fractional_key_count),
        "first_frame": frame_timings[0] if frame_timings else None,
        "last_frame": frame_timings[-1] if frame_timings else None,
        "min_frame": min(frame_timings) if frame_timings else None,
        "max_frame": max(frame_timings) if frame_timings else None,
        "first_value_preview": value_preview,
        "interpolation_counts": _sorted_count_dict(interpolation_counts),
        "easing_counts": _sorted_count_dict(easing_counts),
    }


def build_data_entry_summary(
    entry,
    *,
    timeline_parameter_names: dict[int, str] | None = None,
    datatype_hash_names: dict[int, str] | None = None,
) -> dict[str, object]:
    transform_summaries = [
        build_transform_summary(
            transform,
            type_index=type_index,
            transform_index=transform_index,
            timeline_parameter_hash=type_entry.timeline_parameter_hash,
            timeline_parameter_names=timeline_parameter_names,
            datatype_hash_names=datatype_hash_names,
        )
        for type_index, type_entry in enumerate(entry.types)
        for transform_index, transform in enumerate(type_entry.transforms)
    ]
    data_type_counts = Counter(summary["data_type_name"] for summary in transform_summaries)
    timeline_counts = Counter(summary["timeline_parameter_label"] for summary in transform_summaries)
    return {
        "entry_id": int(entry.id),
        "type_count": len(entry.types),
        "transform_count": len(transform_summaries),
        "keyframe_count": sum(int(summary["keyframe_count"]) for summary in transform_summaries),
        "animation_length": float(entry.animation_length),
        "loop_start_point": float(entry.loop_start_point),
        "loop_control": int(entry.loop_control),
        "label_hash": int(entry.label_hash),
        "data_index_a": int(entry.data_index_a),
        "data_index_b": int(entry.data_index_b),
        "data_type_counts": _sorted_count_dict(data_type_counts),
        "timeline_counts": _sorted_count_dict(timeline_counts),
        "transform_payload": transform_summaries,
    }


def build_file_summary(
    timl,
    *,
    timeline_parameter_names: dict[int, str] | None = None,
    datatype_hash_names: dict[int, str] | None = None,
) -> dict[str, object]:
    entry_summaries = [
        build_data_entry_summary(
            entry,
            timeline_parameter_names=timeline_parameter_names,
            datatype_hash_names=datatype_hash_names,
        )
        for entry in timl.data_entries
    ]
    total_transforms = sum(int(entry["transform_count"]) for entry in entry_summaries)
    total_keyframes = sum(int(entry["keyframe_count"]) for entry in entry_summaries)
    data_type_counts = Counter()
    for entry in entry_summaries:
        data_type_counts.update(entry["data_type_counts"])
    return {
        "source_name": timl.source_name,
        "entry_count": len(entry_summaries),
        "type_count": timl.type_count,
        "transform_count": total_transforms,
        "keyframe_count": total_keyframes,
        "data_type_counts": _sorted_count_dict(data_type_counts),
        "entries": entry_summaries,
    }
