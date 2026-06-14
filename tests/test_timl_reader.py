from __future__ import annotations

import struct
import unittest

from core.formats.timl.model import timl_data_type_name
from core.formats.timl.reader import read_timl_bytes


HEADER_STRUCT = struct.Struct("<4s8siqI")
ENTRY_OFFSET_STRUCT = struct.Struct("<Q")
DATA_STRUCT = struct.Struct("<QQiiffiI")
TYPE_STRUCT = struct.Struct("<QQIi")
TRANSFORM_STRUCT = struct.Struct("<QQIi")
FLOAT_KEYFRAME_STRUCT = struct.Struct("<ffffhh")
COLOR_KEYFRAME_STRUCT = struct.Struct("<4Bfffhh")

LAYOUT_SIGNATURE = bytes((0x00, 0x08, 0x02, 0x18, 0x00, 0x08, 0x02, 0x18))


def _build_minimal_timl_bytes() -> bytes:
    header_offset = 0
    entry_table_offset = 32
    data_offset = 48
    type_table_offset = 96
    transform_table_offset = 128
    keyframe_table_offset = 160
    total_size = keyframe_table_offset + (2 * FLOAT_KEYFRAME_STRUCT.size)
    blob = bytearray(total_size)

    HEADER_STRUCT.pack_into(blob, header_offset, b"timl", LAYOUT_SIGNATURE, 0, entry_table_offset, 1)
    ENTRY_OFFSET_STRUCT.pack_into(blob, entry_table_offset, data_offset)
    DATA_STRUCT.pack_into(blob, data_offset, type_table_offset, 1, 11, 22, 60.0, 12.0, 3, 0x12345678)
    TYPE_STRUCT.pack_into(blob, type_table_offset, transform_table_offset, 1, 0x00112233, 0)
    TRANSFORM_STRUCT.pack_into(blob, transform_table_offset, keyframe_table_offset, 2, 0x44556677, 2)
    FLOAT_KEYFRAME_STRUCT.pack_into(blob, keyframe_table_offset + (0 * FLOAT_KEYFRAME_STRUCT.size), 1.0, 0.0, 0.0, 0.0, 1, 0)
    FLOAT_KEYFRAME_STRUCT.pack_into(blob, keyframe_table_offset + (1 * FLOAT_KEYFRAME_STRUCT.size), 2.5, 0.0, 0.0, 24.0, 2, 1)
    return bytes(blob)


def _build_color_timl_bytes() -> bytes:
    header_offset = 0
    entry_table_offset = 32
    data_offset = 48
    type_table_offset = 96
    transform_table_offset = 128
    keyframe_table_offset = 160
    total_size = keyframe_table_offset + COLOR_KEYFRAME_STRUCT.size
    blob = bytearray(total_size)

    HEADER_STRUCT.pack_into(blob, header_offset, b"timl", LAYOUT_SIGNATURE, 0, entry_table_offset, 1)
    ENTRY_OFFSET_STRUCT.pack_into(blob, entry_table_offset, data_offset)
    DATA_STRUCT.pack_into(blob, data_offset, type_table_offset, 1, 1, 2, 30.0, 0.0, 0, 0x01020304)
    TYPE_STRUCT.pack_into(blob, type_table_offset, transform_table_offset, 1, 0xABCD, 0)
    TRANSFORM_STRUCT.pack_into(blob, transform_table_offset, keyframe_table_offset, 1, 0xDEAD, 3)
    COLOR_KEYFRAME_STRUCT.pack_into(blob, keyframe_table_offset, 16, 32, 64, 255, 0.25, 0.75, 8.0, 3, 4)
    return bytes(blob)


class TimlReaderTests(unittest.TestCase):
    def test_parse_minimal_timl(self):
        timl = read_timl_bytes(_build_minimal_timl_bytes(), source_name="minimal.timl")
        self.assertEqual(timl.source_name, "minimal.timl")
        self.assertEqual(timl.header.signature, b"timl")
        self.assertEqual(timl.header.entry_table_offset, 32)
        self.assertEqual(timl.header.entry_count, 1)
        self.assertEqual(timl.entry_offsets, (48,))
        self.assertEqual(timl.data_count, 1)
        self.assertEqual(timl.type_count, 1)
        self.assertEqual(timl.transform_count, 1)
        self.assertEqual(timl.keyframe_count, 2)

        entry = timl.data_entries[0]
        self.assertEqual(entry.id, 0)
        self.assertEqual(entry.type_table_offset, 96)
        self.assertEqual(entry.type_count, 1)
        self.assertEqual(entry.animation_length, 60.0)
        self.assertEqual(entry.loop_start_point, 12.0)
        self.assertEqual(entry.loop_control, 3)
        self.assertEqual(entry.label_hash, 0x12345678)

        transform = entry.types[0].transforms[0]
        self.assertEqual(transform.datatype_hash, 0x44556677)
        self.assertEqual(transform.data_type, 2)
        self.assertEqual(len(transform.keyframes), 2)
        self.assertEqual(transform.keyframes[0].value, 1.0)
        self.assertEqual(transform.keyframes[1].value, 2.5)
        self.assertEqual(transform.keyframes[1].frame_timing, 24.0)

    def test_parse_color_timl_keyframe(self):
        timl = read_timl_bytes(_build_color_timl_bytes(), source_name="color.timl")
        keyframe = timl.data_entries[0].types[0].transforms[0].keyframes[0]
        self.assertEqual(keyframe.data_type, 3)
        self.assertEqual(keyframe.value, (16, 32, 64, 255))
        self.assertEqual(keyframe.control_left, 0.25)
        self.assertEqual(keyframe.control_right, 0.75)
        self.assertEqual(keyframe.frame_timing, 8.0)
        self.assertEqual(keyframe.interpolation, 3)
        self.assertEqual(keyframe.easing, 4)

    def test_data_type_name_helper(self):
        self.assertEqual(timl_data_type_name(2), "float")
        self.assertEqual(timl_data_type_name(999), "unknown_999")
