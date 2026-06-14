from __future__ import annotations

import unittest

from core.formats.timl.channels import build_timl_transform_samples
from core.formats.timl.reader import read_timl_bytes
from tests.test_timl_reader import _build_color_timl_bytes
from tests.test_timl_reader import _build_minimal_timl_bytes


class TimlChannelTests(unittest.TestCase):
    def test_build_float_transform_samples(self):
        timl = read_timl_bytes(_build_minimal_timl_bytes(), source_name="minimal.timl")
        entry = timl.data_entries[0]
        transforms = build_timl_transform_samples(entry)

        self.assertEqual(len(transforms), 1)
        transform = transforms[0]
        self.assertEqual(transform.type_index, 0)
        self.assertEqual(transform.transform_index, 0)
        self.assertEqual(transform.timeline_parameter_hash, 0x00112233)
        self.assertEqual(transform.datatype_hash, 0x44556677)
        self.assertEqual(transform.data_type_name, "float")
        self.assertEqual(transform.value_kind, "float")
        self.assertEqual(transform.component_labels, ("value",))
        self.assertEqual(len(transform.keyframes), 2)
        self.assertEqual(transform.keyframes[0].value, (1.0,))
        self.assertEqual(transform.keyframes[1].frame, 24.0)
        self.assertEqual(transform.keyframes[1].interpolation, 2)

    def test_build_color_transform_samples(self):
        timl = read_timl_bytes(_build_color_timl_bytes(), source_name="color.timl")
        entry = timl.data_entries[0]
        transforms = build_timl_transform_samples(entry)

        self.assertEqual(len(transforms), 1)
        transform = transforms[0]
        self.assertEqual(transform.data_type_name, "color_rgba8")
        self.assertEqual(transform.value_kind, "color")
        self.assertEqual(transform.component_labels, ("r", "g", "b", "a"))
        self.assertEqual(transform.keyframes[0].value, (16.0, 32.0, 64.0, 255.0))
        self.assertEqual(transform.keyframes[0].easing, 4)


if __name__ == "__main__":
    unittest.main()
