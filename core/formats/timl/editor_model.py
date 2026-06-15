"""Blender-free TIML editor view models for semantic/raw browsing."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .semantics import format_hash_label


@dataclass(frozen=True)
class TimlEditorTransformView:
    type_index: int
    transform_index: int
    property_name: str
    timeline_hash: int
    timeline_label: str
    datatype_hash: int
    datatype_label: str
    data_type_name: str
    keyframe_count: int
    first_frame: float | None
    last_frame: float | None
    semantic_label: str
    writeback_status_code: str
    writeback_status_label: str
    edit_policy_code: str
    edit_policy_label: str


@dataclass(frozen=True)
class TimlEditorBlockView:
    type_index: int
    timeline_hash: int
    timeline_label: str
    raw_timeline_label: str
    block_label: str
    help_text: str
    transform_count: int
    keyframe_count: int
    first_frame: float | None
    last_frame: float | None
    datatype_summary: str
    writeback_summary: str
    edit_policy_summary: str
    transform_labels: tuple[str, ...]
    property_names: tuple[str, ...]
    known_semantic: bool


def timl_editor_block_help_text(timeline_label: str) -> str:
    text = str(timeline_label or "")
    if text == "EventLoop":
        return "Loop and timeline repeat controls for the attached action."
    if text.startswith("EventCollision"):
        return "Collision/event request payload. Meanings may be partially known."
    if text.startswith("EventGroup"):
        return "Grouped timeline event payload with request/release style fields."
    if text == "GameParameter":
        return "Runtime game parameter payload."
    if text.startswith("0x"):
        return "Unknown timeline family. Raw editing may be required."
    return "TIML timeline block."


def timl_editor_field_help_text(timeline_label: str, datatype_label: str, *, data_type_name: str = "") -> str:
    timeline_text = str(timeline_label or "")
    datatype_text = str(datatype_label or "")
    if datatype_text.startswith("ReqNo"):
        return "Known request-number field. Exact gameplay meaning should be validated in-game."
    if datatype_text.startswith("ReleaseTime"):
        return "Known release-time field. Treat this as a timing/control value unless validated otherwise."
    if datatype_text.startswith("mFlag"):
        return "Known flag/control field. Bit meaning may vary by TIML family; keep boolean-like values at 0 or 1 unless validated otherwise."
    if timeline_text == "EventLoop":
        return "Loop-related field inside the EventLoop block."
    if str(data_type_name or "").startswith("color"):
        return "Color preview field. Blender shows normalized values while TIML stores byte color."
    if str(data_type_name or "") == "bool_uint32":
        return "Boolean preview field. Keep values at 0 or 1 for safe writeback."
    if str(data_type_name or "") in {"sint32", "uint32"}:
        return "Integer preview field. Keep values on exact integer steps for safe writeback."
    return "TIML field."


def _sorted_counter_text(counter: Counter[str]) -> str:
    if not counter:
        return ""
    return ", ".join(
        f"{label} {count}"
        for label, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    )


def _block_label(timeline_label: str, raw_timeline_label: str) -> tuple[str, bool]:
    text = str(timeline_label or "").strip()
    raw_text = str(raw_timeline_label or "").strip()
    if text and not text.startswith("0x"):
        return text, True
    if raw_text:
        return f"Unknown Timeline {raw_text}", False
    return "Unknown Timeline", False


def build_timl_editor_block_views(
    transforms: list[TimlEditorTransformView] | tuple[TimlEditorTransformView, ...],
) -> tuple[TimlEditorBlockView, ...]:
    grouped: dict[tuple[int, int], list[TimlEditorTransformView]] = {}
    for transform in transforms:
        key = (int(transform.type_index), int(transform.timeline_hash))
        grouped.setdefault(key, []).append(transform)

    blocks: list[TimlEditorBlockView] = []
    for (type_index, timeline_hash), block_transforms in sorted(grouped.items(), key=lambda item: item[0]):
        first = block_transforms[0]
        raw_timeline_label = format_hash_label(int(timeline_hash))
        block_label, known_semantic = _block_label(first.timeline_label, raw_timeline_label)
        frame_values = [
            float(frame)
            for transform in block_transforms
            for frame in (transform.first_frame, transform.last_frame)
            if frame is not None
        ]
        datatype_counter = Counter(str(transform.datatype_label or transform.data_type_name or "?") for transform in block_transforms)
        writeback_counter = Counter(
            str(transform.writeback_status_label or "Unknown")
            for transform in block_transforms
        )
        edit_counter = Counter(
            str(transform.edit_policy_label or "Unknown")
            for transform in block_transforms
        )
        transform_labels = tuple(
            f"Type {int(transform.type_index):02d} / Transform {int(transform.transform_index):02d} - "
            f"{str(transform.datatype_label or transform.data_type_name or '?')}"
            for transform in sorted(block_transforms, key=lambda item: int(item.transform_index))
        )
        property_names = tuple(
            str(transform.property_name or "")
            for transform in sorted(block_transforms, key=lambda item: int(item.transform_index))
            if str(transform.property_name or "")
        )
        blocks.append(
            TimlEditorBlockView(
                type_index=int(type_index),
                timeline_hash=int(timeline_hash),
                timeline_label=str(first.timeline_label or ""),
                raw_timeline_label=raw_timeline_label,
                block_label=block_label,
                help_text=timl_editor_block_help_text(str(first.timeline_label or "")),
                transform_count=len(block_transforms),
                keyframe_count=sum(int(transform.keyframe_count) for transform in block_transforms),
                first_frame=min(frame_values) if frame_values else None,
                last_frame=max(frame_values) if frame_values else None,
                datatype_summary=_sorted_counter_text(datatype_counter),
                writeback_summary=_sorted_counter_text(writeback_counter),
                edit_policy_summary=_sorted_counter_text(edit_counter),
                transform_labels=transform_labels,
                property_names=property_names,
                known_semantic=known_semantic,
            )
        )
    return tuple(blocks)
