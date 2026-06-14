import unittest

from core.formats.timl.semantics import format_hash_label
from core.formats.timl.semantics import get_data_type_semantics
from core.formats.timl.semantics import get_interpolation_label


class TimlSemanticsTests(unittest.TestCase):
    def test_data_type_semantics_for_color(self):
        semantics = get_data_type_semantics(3)
        self.assertEqual(semantics.name, "color_rgba8")
        self.assertEqual(semantics.value_dimension, 4)
        self.assertEqual(semantics.control_kind, "float")

    def test_unknown_data_type_falls_back_cleanly(self):
        semantics = get_data_type_semantics(999)
        self.assertEqual(semantics.name, "unknown_999")
        self.assertEqual(semantics.value_kind, "unknown")

    def test_interpolation_label_uses_known_names(self):
        self.assertEqual(get_interpolation_label(1), "LINEAR")
        self.assertEqual(get_interpolation_label(99), "INTERP_99")

    def test_hash_label_uses_mapping_when_present(self):
        self.assertEqual(format_hash_label(0x12345678, {0x12345678: "Example"}), "Example")
        self.assertEqual(format_hash_label(0x12345678), "0x12345678")
