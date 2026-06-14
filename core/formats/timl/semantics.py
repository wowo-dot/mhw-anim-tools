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
