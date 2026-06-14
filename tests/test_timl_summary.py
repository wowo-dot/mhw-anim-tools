import unittest

from core.formats.timl.reader import read_timl_bytes
from core.formats.timl.summary import build_file_summary
from tests.test_timl_reader import _build_color_timl_bytes
from tests.test_timl_reader import _build_minimal_timl_bytes


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
