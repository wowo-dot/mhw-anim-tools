"""Semantic helpers for parsed TIML data."""

from __future__ import annotations

from dataclasses import dataclass

from .model import timl_data_type_name


INTERPOLATION_LABELS = {
    0: "CONSTANT",
    1: "LINEAR",
    2: "QUAD",
    3: "CUBIC",
    4: "QUART",
    5: "EXPO",
    6: "SINE",
}


TIMELINE_PARAMETER_LABELS = {
    0x0CFD985C: "EventCollision00",
    0x7BFAA8CA: "EventCollision01",
    0x62F3F970: "EventCollision02",
    0x15F4C9E6: "EventCollision03",
    0x59C0CAA2: "EventGroup00",
    0x2EC7FA34: "EventGroup01",
    0x37CEAB8E: "EventGroup02",
    0x40C99B18: "EventGroup03",
    0x5EAD0EBB: "EventGroup04",
    0x29AA3E2D: "EventGroup05",
    0x30A36F97: "EventGroup06",
    0x47A45F01: "EventGroup07",
    0x571B4290: "EventGroup08",
    0x201C7206: "EventGroup09",
    0x40DBFBE3: "EventGroup10",
    0x24006667: "EventLoop",
    0x01739779: "GameParameter",
}


DATATYPE_HASH_LABELS = {
    0xE64D793E: "ReqNo A",
    0x7F442884: "ReqNo B",
    0x08431812: "ReqNo C",
    0x96278DB1: "ReqNo D",
    0xE4D7A72E: "ReleaseTime A",
    0x7DDEF694: "ReleaseTime B",
    0x0AD9C602: "ReleaseTime C",
    0x94BD53A1: "ReleaseTime D",
    0x08FD20A6: "mFlag",
    0x6E63FBC7: "mFlag1",
    0xF76AAA7D: "mFlag2",
    0x806D9AEB: "mFlag3",
    0x1E090F48: "mFlag4",
    0x690E3FDE: "mFlag5",
    0xF0076E64: "mFlag6",
}


@dataclass(frozen=True)
class TimlDataTypeSemantics:
    code: int
    name: str
    value_kind: str
    value_dimension: int
    control_kind: str


DATA_TYPE_SEMANTICS = {
    0: TimlDataTypeSemantics(0, "sint32", "integer", 1, "integer"),
    1: TimlDataTypeSemantics(1, "uint32", "integer", 1, "integer"),
    2: TimlDataTypeSemantics(2, "float", "float", 1, "float"),
    3: TimlDataTypeSemantics(3, "color_rgba8", "color", 4, "float"),
    4: TimlDataTypeSemantics(4, "bool_uint32", "boolean", 1, "integer"),
}


def get_data_type_semantics(data_type: int) -> TimlDataTypeSemantics:
    code = int(data_type)
    if code in DATA_TYPE_SEMANTICS:
        return DATA_TYPE_SEMANTICS[code]
    return TimlDataTypeSemantics(code, timl_data_type_name(code), "unknown", 0, "unknown")


def get_interpolation_label(code: int) -> str:
    value = int(code)
    return INTERPOLATION_LABELS.get(value, f"INTERP_{value}")


def format_hash_label(hash_value: int, mapping: dict[int, str] | None = None) -> str:
    value = int(hash_value) & 0xFFFFFFFF
    if mapping and value in mapping:
        return mapping[value]
    return f"0x{value:08X}"


def format_timeline_parameter_label(hash_value: int, mapping: dict[int, str] | None = None) -> str:
    value = int(hash_value) & 0xFFFFFFFF
    if mapping and value in mapping:
        return mapping[value]
    if value in TIMELINE_PARAMETER_LABELS:
        return TIMELINE_PARAMETER_LABELS[value]
    return format_hash_label(value)


def format_datatype_hash_label(hash_value: int, mapping: dict[int, str] | None = None) -> str:
    value = int(hash_value) & 0xFFFFFFFF
    if mapping and value in mapping:
        return mapping[value]
    if value in DATATYPE_HASH_LABELS:
        return DATATYPE_HASH_LABELS[value]
    return format_hash_label(value)
