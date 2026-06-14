"""Immutable-ish data models for parsed TIML files."""

from __future__ import annotations

from dataclasses import dataclass, field


TimlValue = int | float | tuple[int, int, int, int]
TimlControlValue = int | float


DATA_TYPE_NAMES = {
    0: "sint32",
    1: "uint32",
    2: "float",
    3: "color_rgba8",
    4: "bool_uint32",
}
EXPECTED_LAYOUT_SIGNATURE = bytes((0x00, 0x08, 0x02, 0x18, 0x00, 0x08, 0x02, 0x18))


def timl_data_type_name(data_type: int) -> str:
    return DATA_TYPE_NAMES.get(int(data_type), f"unknown_{int(data_type)}")


@dataclass(frozen=True)
class TimlHeader:
    signature: bytes
    layout_signature: bytes
    reserved: int
    entry_table_offset: int
    entry_count: int


@dataclass(frozen=True)
class TimlKeyframe:
    data_type: int
    value: TimlValue
    control_left: TimlControlValue
    control_right: TimlControlValue
    frame_timing: float
    interpolation: int
    easing: int

    @property
    def data_type_name(self) -> str:
        return timl_data_type_name(self.data_type)


@dataclass(frozen=True)
class TimlTransform:
    keyframe_table_offset: int
    keyframe_count: int
    datatype_hash: int
    data_type: int
    keyframes: tuple[TimlKeyframe, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TimlType:
    transform_table_offset: int
    transform_count: int
    timeline_parameter_hash: int
    reserved: int
    transforms: tuple[TimlTransform, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TimlData:
    id: int
    type_table_offset: int
    type_count: int
    data_index_a: int
    data_index_b: int
    animation_length: float
    loop_start_point: float
    loop_control: int
    label_hash: int
    types: tuple[TimlType, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TimlFile:
    source_name: str
    file_size: int
    header: TimlHeader
    entry_offsets: tuple[int, ...]
    data_entries: tuple[TimlData, ...]

    @property
    def data_count(self) -> int:
        return len(self.data_entries)

    @property
    def type_count(self) -> int:
        return sum(len(entry.types) for entry in self.data_entries)

    @property
    def transform_count(self) -> int:
        return sum(len(type_entry.transforms) for entry in self.data_entries for type_entry in entry.types)

    @property
    def keyframe_count(self) -> int:
        return sum(
            len(transform.keyframes)
            for entry in self.data_entries
            for type_entry in entry.types
            for transform in type_entry.transforms
        )
