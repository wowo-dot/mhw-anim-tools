"""Helpers for conservative TIML template authoring."""

from __future__ import annotations

from dataclasses import dataclass
import json
import zlib

try:
    from .timl_metadata import TIML_TEMPLATE_HEADER_KEY
    from .timl_metadata import TIML_TEMPLATE_KIND_KEY
except ImportError:  # pragma: no cover - test runner imports from addon root
    from blender_adapter.timl_metadata import TIML_TEMPLATE_HEADER_KEY
    from blender_adapter.timl_metadata import TIML_TEMPLATE_KIND_KEY


EVENT_LOOP_TEMPLATE_KIND = "event_loop"
EVENT_LOOP_TIMELINE_HASH = 0x24006667
EVENT_LOOP_REQNO_A_HASH = 0xE64D793E
EVENT_LOOP_RELEASE_TIME_A_HASH = 0xE4D7A72E
EVENT_LOOP_MFLAG_HASH = 0x08FD20A6
DEFAULT_EVENT_LOOP_REQNO_A = 7304
DEFAULT_EVENT_LOOP_RELEASE_TIME_A = 100
DEFAULT_EVENT_LOOP_FLAG_ON = 1
DEFAULT_EVENT_LOOP_FLAG_OFF = 0
DEFAULT_EVENT_LOOP_DATA_INDEX_A = 3
DEFAULT_EVENT_LOOP_DATA_INDEX_B = 4


@dataclass(frozen=True)
class TimlTemplateHeader:
    data_index_a: int
    data_index_b: int
    animation_length: float
    loop_start_point: float
    loop_control: int
    label_hash: int


def build_stable_timl_label_hash(source_lmt: str, entry_id: int) -> int:
    seed = f"{str(source_lmt or '')}|{int(entry_id):03d}|timl".encode("utf-8", "replace")
    value = zlib.crc32(seed) & 0xFFFFFFFF
    return value or 1


def default_event_loop_template_header(
    *,
    source_lmt: str,
    entry_id: int,
    animation_length: float,
    data_index_a: int = 0,
    data_index_b: int = 0,
    loop_start_point: float = 0.0,
    loop_control: int = 0,
    label_hash: int = 0,
) -> TimlTemplateHeader:
    resolved_label_hash = int(label_hash) & 0xFFFFFFFF
    if resolved_label_hash == 0:
        resolved_label_hash = build_stable_timl_label_hash(source_lmt, entry_id)
    return TimlTemplateHeader(
        data_index_a=int(data_index_a) if int(data_index_a) != 0 else DEFAULT_EVENT_LOOP_DATA_INDEX_A,
        data_index_b=int(data_index_b) if int(data_index_b) != 0 else DEFAULT_EVENT_LOOP_DATA_INDEX_B,
        animation_length=max(0.0, float(animation_length)),
        loop_start_point=float(loop_start_point),
        loop_control=int(loop_control),
        label_hash=resolved_label_hash,
    )


def encode_timl_template_header(header: TimlTemplateHeader) -> str:
    return json.dumps(
        {
            "data_index_a": int(header.data_index_a),
            "data_index_b": int(header.data_index_b),
            "animation_length": float(header.animation_length),
            "loop_start_point": float(header.loop_start_point),
            "loop_control": int(header.loop_control),
            "label_hash": int(header.label_hash) & 0xFFFFFFFF,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def decode_timl_template_header(value) -> TimlTemplateHeader | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, dict):
        return None
    try:
        return TimlTemplateHeader(
            data_index_a=int(decoded["data_index_a"]),
            data_index_b=int(decoded["data_index_b"]),
            animation_length=float(decoded["animation_length"]),
            loop_start_point=float(decoded["loop_start_point"]),
            loop_control=int(decoded["loop_control"]),
            label_hash=int(decoded["label_hash"]) & 0xFFFFFFFF,
        )
    except (KeyError, TypeError, ValueError):
        return None


def set_timl_template_metadata(target_object, *, kind: str, header: TimlTemplateHeader) -> None:
    target_object[TIML_TEMPLATE_KIND_KEY] = str(kind or "")
    target_object[TIML_TEMPLATE_HEADER_KEY] = encode_timl_template_header(header)


def clear_timl_template_metadata(target_object) -> None:
    if TIML_TEMPLATE_KIND_KEY in target_object:
        del target_object[TIML_TEMPLATE_KIND_KEY]
    if TIML_TEMPLATE_HEADER_KEY in target_object:
        del target_object[TIML_TEMPLATE_HEADER_KEY]


def get_timl_template_kind(target_object) -> str:
    return str(target_object.get(TIML_TEMPLATE_KIND_KEY, "") or "")


def get_timl_template_header(target_object) -> TimlTemplateHeader | None:
    return decode_timl_template_header(target_object.get(TIML_TEMPLATE_HEADER_KEY, ""))
