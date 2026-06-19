"""Read-only parser for Monster Hunter World TIML files."""

from __future__ import annotations

import struct
from pathlib import Path

from ...binary.reader import BinaryReader
from ...diagnostics.errors import BinaryFormatError
from .model import TimlData
from .model import TimlFile
from .model import TimlHeader
from .model import TimlKeyframe
from .model import TimlTransform
from .model import TimlType


HEADER_STRUCT = struct.Struct("<4s8siqI")
ENTRY_OFFSET_STRUCT = struct.Struct("<Q")
DATA_STRUCT = struct.Struct("<QQiiffiI")
TYPE_STRUCT = struct.Struct("<QQIi")
TRANSFORM_STRUCT = struct.Struct("<QQIi")
SIGNED_KEYFRAME_STRUCT = struct.Struct("<iiifhh")
UNSIGNED_KEYFRAME_STRUCT = struct.Struct("<IIIfhh")
FLOAT_KEYFRAME_STRUCT = struct.Struct("<ffffhh")
COLOR_KEYFRAME_STRUCT = struct.Struct("<4Bfffhh")

EXPECTED_SIGNATURE = b"timl"
EXPECTED_LAYOUT_SIGNATURE = bytes((0x00, 0x08, 0x02, 0x18, 0x00, 0x08, 0x02, 0x18))
SUPPORTED_DATA_TYPES = {0, 1, 2, 3, 4}


def _read_header(reader: BinaryReader) -> TimlHeader:
    signature, layout_signature, reserved, entry_table_offset, entry_count = reader.read_struct(HEADER_STRUCT)
    if signature != EXPECTED_SIGNATURE:
        raise BinaryFormatError(
            "Unsupported TIML signature",
            source_name=reader.source_name,
            signature=signature,
        )
    if entry_count < 0:
        raise BinaryFormatError(
            "Negative TIML entry count",
            source_name=reader.source_name,
            entry_count=entry_count,
        )
    return TimlHeader(
        signature=signature,
        layout_signature=layout_signature,
        reserved=reserved,
        entry_table_offset=entry_table_offset,
        entry_count=entry_count,
    )


def _read_entry_offsets(reader: BinaryReader, header: TimlHeader) -> tuple[int, ...]:
    offsets: list[int] = []
    if header.entry_count == 0:
        return ()
    for index in range(header.entry_count):
        (offset,) = reader.read_struct_at(
            header.entry_table_offset + (index * ENTRY_OFFSET_STRUCT.size),
            ENTRY_OFFSET_STRUCT,
        )
        offsets.append(offset)
    return tuple(offsets)


def _read_keyframe(reader: BinaryReader, offset: int, data_type: int) -> TimlKeyframe:
    match int(data_type):
        case 0:
            value, control_left, control_right, frame_timing, interpolation, easing = reader.read_struct_at(
                offset,
                SIGNED_KEYFRAME_STRUCT,
            )
        case 1 | 4:
            value, control_left, control_right, frame_timing, interpolation, easing = reader.read_struct_at(
                offset,
                UNSIGNED_KEYFRAME_STRUCT,
            )
        case 2:
            value, control_left, control_right, frame_timing, interpolation, easing = reader.read_struct_at(
                offset,
                FLOAT_KEYFRAME_STRUCT,
            )
        case 3:
            red, green, blue, alpha, control_left, control_right, frame_timing, interpolation, easing = reader.read_struct_at(
                offset,
                COLOR_KEYFRAME_STRUCT,
            )
            value = (red, green, blue, alpha)
        case _:
            raise BinaryFormatError(
                "Unsupported TIML keyframe data type",
                source_name=reader.source_name,
                offset=offset,
                data_type=data_type,
            )
    return TimlKeyframe(
        data_type=data_type,
        value=value,
        control_left=control_left,
        control_right=control_right,
        frame_timing=frame_timing,
        interpolation=interpolation,
        easing=easing,
    )


def _read_transform(reader: BinaryReader, offset: int) -> TimlTransform:
    keyframe_table_offset, keyframe_count, datatype_hash, data_type = reader.read_struct_at(offset, TRANSFORM_STRUCT)
    if data_type not in SUPPORTED_DATA_TYPES:
        raise BinaryFormatError(
            "Unsupported TIML transform data type",
            source_name=reader.source_name,
            offset=offset,
            data_type=data_type,
            datatype_hash=datatype_hash,
        )
    keyframes = tuple(
        _read_keyframe(reader, keyframe_table_offset + (index * SIGNED_KEYFRAME_STRUCT.size), data_type)
        for index in range(keyframe_count)
    )
    return TimlTransform(
        keyframe_table_offset=keyframe_table_offset,
        keyframe_count=keyframe_count,
        datatype_hash=datatype_hash,
        data_type=data_type,
        keyframes=keyframes,
    )


def _read_type(reader: BinaryReader, offset: int) -> TimlType:
    transform_table_offset, transform_count, timeline_parameter_hash, reserved = reader.read_struct_at(offset, TYPE_STRUCT)
    transforms = tuple(
        _read_transform(reader, transform_table_offset + (index * TRANSFORM_STRUCT.size))
        for index in range(transform_count)
    )
    return TimlType(
        transform_table_offset=transform_table_offset,
        transform_count=transform_count,
        timeline_parameter_hash=timeline_parameter_hash,
        reserved=reserved,
        transforms=transforms,
    )


def _read_data(reader: BinaryReader, entry_id: int, offset: int) -> TimlData:
    (
        type_table_offset,
        type_count,
        data_index_a,
        data_index_b,
        animation_length,
        loop_start_point,
        loop_control,
        label_hash,
    ) = reader.read_struct_at(offset, DATA_STRUCT)
    types = tuple(
        _read_type(reader, type_table_offset + (index * TYPE_STRUCT.size))
        for index in range(type_count)
    )
    return TimlData(
        id=entry_id,
        type_table_offset=type_table_offset,
        type_count=type_count,
        data_index_a=data_index_a,
        data_index_b=data_index_b,
        animation_length=animation_length,
        loop_start_point=loop_start_point,
        loop_control=loop_control,
        label_hash=label_hash,
        types=types,
    )


def read_timl_bytes(data: bytes, source_name: str = "<memory>") -> TimlFile:
    reader = BinaryReader(data, source_name=source_name)
    header = _read_header(reader)
    entry_offsets = _read_entry_offsets(reader, header)
    data_entries = tuple(
        _read_data(reader, entry_id, offset)
        for entry_id, offset in enumerate(entry_offsets)
        if offset != 0
    )
    return TimlFile(
        source_name=source_name,
        file_size=len(data),
        header=header,
        entry_offsets=entry_offsets,
        data_entries=data_entries,
    )


def read_timl_data_bytes(
    data: bytes,
    *,
    data_offset: int = 0,
    source_name: str = "<memory>",
    entry_id: int = 0,
) -> TimlData:
    reader = BinaryReader(data, source_name=source_name)
    return _read_data(reader, entry_id, int(data_offset))


def read_timl_file(path: str | Path) -> TimlFile:
    file_path = Path(path)
    data = file_path.read_bytes()
    return read_timl_bytes(data, source_name=str(file_path))
