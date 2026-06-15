import unittest

from core.formats.timl.reader import read_timl_bytes
from core.formats.timl.summary import build_file_summary
from tests.test_timl_reader import _build_color_timl_bytes
from tests.test_timl_reader import _build_minimal_timl_bytes
from tests.test_timl_reader import DATA_STRUCT
from tests.test_timl_reader import ENTRY_OFFSET_STRUCT
from tests.test_timl_reader import FLOAT_KEYFRAME_STRUCT
from tests.test_timl_reader import HEADER_STRUCT
from tests.test_timl_reader import LAYOUT_SIGNATURE
from tests.test_timl_reader import TRANSFORM_STRUCT
from tests.test_timl_reader import TYPE_STRUCT


def _build_eventloop_timl_bytes() -> bytes:
    header_offset = 0
    entry_table_offset = 32
    data_offset = 48
    type_table_offset = 96
    transform_table_offset = 128
    keyframe_table_offset = 160
    total_size = keyframe_table_offset + FLOAT_KEYFRAME_STRUCT.size
    blob = bytearray(total_size)

    HEADER_STRUCT.pack_into(blob, header_offset, b"timl", LAYOUT_SIGNATURE, 0, entry_table_offset, 1)
    ENTRY_OFFSET_STRUCT.pack_into(blob, entry_table_offset, data_offset)
    DATA_STRUCT.pack_into(blob, data_offset, type_table_offset, 1, 1, 2, 40.0, 0.0, 0, 0x12345678)
    TYPE_STRUCT.pack_into(blob, type_table_offset, transform_table_offset, 1, 0x24006667, 0)
    TRANSFORM_STRUCT.pack_into(blob, transform_table_offset, keyframe_table_offset, 1, 0xE64D793E, 1)
    FLOAT_KEYFRAME_STRUCT.pack_into(blob, keyframe_table_offset, 7.0, 0.0, 0.0, 0.0, 1, 0)
    return bytes(blob)


class TimlSummaryTests(unittest.TestCase):
    def test_build_file_summary_contains_transform_payload(self):
        timl = read_timl_bytes(_build_minimal_timl_bytes(), source_name="minimal.timl")
        summary = build_file_summary(timl)
        self.assertEqual(summary["entry_count"], 1)
        self.assertEqual(summary["transform_count"], 1)
        self.assertEqual(summary["keyframe_count"], 2)
        self.assertEqual(summary["data_type_counts"], {"float": 1})
        transform_payload = summary["entries"][0]["transform_payload"]
        self.assertEqual(len(transform_payload), 1)
        self.assertEqual(transform_payload[0]["data_type_name"], "float")
        self.assertEqual(transform_payload[0]["fractional_key_count"], 0)
        self.assertEqual(transform_payload[0]["interpolation_counts"]["LINEAR"], 1)

    def test_build_file_summary_handles_color_transform(self):
        timl = read_timl_bytes(_build_color_timl_bytes(), source_name="color.timl")
        summary = build_file_summary(timl)
        transform_payload = summary["entries"][0]["transform_payload"][0]
        self.assertEqual(transform_payload["data_type_name"], "color_rgba8")
        self.assertEqual(transform_payload["value_dimension"], 4)
        self.assertEqual(transform_payload["first_value_preview"], "16, 32, 64, 255")

    def test_build_file_summary_uses_curated_friendly_timl_labels_when_known(self):
        timl = read_timl_bytes(_build_eventloop_timl_bytes(), source_name="eventloop.timl")
        summary = build_file_summary(timl)
        transform_payload = summary["entries"][0]["transform_payload"][0]
        self.assertEqual(transform_payload["timeline_parameter_label"], "EventLoop")
        self.assertEqual(transform_payload["datatype_label"], "ReqNo A")
