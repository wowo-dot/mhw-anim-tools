"""Pure TIML presentation helpers shared by Blender UI modules."""

from __future__ import annotations

import ntpath
import os

try:
    from ..core.formats.timl.semantics import format_datatype_hash_label
    from ..core.formats.timl.semantics import format_hash_label
    from ..core.formats.timl.semantics import format_timeline_parameter_label
except ImportError:  # pragma: no cover - test runner imports from addon root
    from core.formats.timl.semantics import format_datatype_hash_label
    from core.formats.timl.semantics import format_hash_label
    from core.formats.timl.semantics import format_timeline_parameter_label


def timl_transform_identity_label(type_index: int, transform_index: int) -> str:
    return f"Type {int(type_index):02d} / Transform {int(transform_index):02d}"


def timl_display_source_name(path_text: str) -> str:
    text = str(path_text or "")
    return ntpath.basename(text) or os.path.basename(text)


def build_timl_source_summary(
    *,
    source_name: str = "",
    entry_id: int | None = None,
    source_offset: int | None = None,
) -> str:
    parts: list[str] = []
    source_text = timl_display_source_name(source_name)
    if source_text:
        parts.append(source_text)
    if entry_id is not None:
        parts.append(f"Entry {int(entry_id):03d}")
    if source_offset is not None:
        parts.append(f"Offset 0x{int(source_offset):X}")
    return " | ".join(parts)


def build_timl_analysis_summary(
    *,
    transform_count: int,
    keyframe_count: int,
    frame_end: int,
    warning_count: int,
    error_count: int,
) -> str:
    return (
        f"Transforms {int(transform_count)} | "
        f"Keys {int(keyframe_count)} | "
        f"Frame end {int(frame_end)} | "
        f"Warnings {int(warning_count)} | "
        f"Errors {int(error_count)}"
    )


def build_timl_writeback_summary(
    *,
    preserve_raw_count: int,
    patch_values_count: int,
    rebuild_count: int,
    blocked_count: int,
) -> str:
    return (
        f"Preserve {int(preserve_raw_count)} | "
        f"Patch {int(patch_values_count)} | "
        f"Rebuild {int(rebuild_count)} | "
        f"Blocked {int(blocked_count)}"
    )


def build_timl_edit_policy_summary(
    *,
    value_only_count: int,
    rebuild_capable_count: int,
    blocked_count: int,
) -> str:
    return (
        f"Value Only {int(value_only_count)} | "
        f"Rebuild OK {int(rebuild_capable_count)} | "
        f"Blocked {int(blocked_count)}"
    )


def timl_transform_semantic_label(timeline_label: str, datatype_label: str, *, data_type_name: str = "") -> str:
    timeline_text = str(timeline_label or "").strip()
    datatype_text = str(datatype_label or "").strip()
    if timeline_text and datatype_text:
        return f"{timeline_text} / {datatype_text}"
    if timeline_text:
        return timeline_text
    if datatype_text:
        return datatype_text
    return str(data_type_name or "Unknown TIML Transform")


def build_timl_transform_labels(
    *,
    type_index: int,
    transform_index: int,
    timeline_hash: int | None = None,
    datatype_hash: int | None = None,
    data_type_name: str = "",
    timeline_label: str = "",
    datatype_label: str = "",
) -> dict[str, str]:
    friendly_timeline = str(timeline_label or "")
    if not friendly_timeline and timeline_hash is not None:
        friendly_timeline = format_timeline_parameter_label(int(timeline_hash))

    friendly_datatype = str(datatype_label or "")
    if not friendly_datatype and datatype_hash is not None:
        friendly_datatype = format_datatype_hash_label(int(datatype_hash))

    raw_timeline = format_hash_label(int(timeline_hash)) if timeline_hash is not None else ""
    raw_datatype = format_hash_label(int(datatype_hash)) if datatype_hash is not None else ""

    return {
        "identity_label": timl_transform_identity_label(type_index, transform_index),
        "semantic_label": timl_transform_semantic_label(
            friendly_timeline,
            friendly_datatype,
            data_type_name=data_type_name,
        ),
        "timeline_label": friendly_timeline,
        "datatype_label": friendly_datatype,
        "raw_timeline_label": raw_timeline,
        "raw_datatype_label": raw_datatype,
    }
