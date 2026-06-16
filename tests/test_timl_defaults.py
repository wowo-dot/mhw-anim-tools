from __future__ import annotations

from types import SimpleNamespace
import unittest

from ui.timl_defaults import data_type_key_for_name
from ui.timl_defaults import next_available_transform_index
from ui.timl_defaults import next_available_type_index
from ui.timl_defaults import seed_add_timl_transform_defaults
from ui.timl_defaults import seed_add_timl_type_defaults


TIML_DATA_TYPE_ITEMS = (
    ("0", "sint32", ""),
    ("1", "uint32", ""),
    ("2", "float", ""),
    ("3", "color_rgba8", ""),
    ("4", "bool_uint32", ""),
)


class TimlDefaultsTests(unittest.TestCase):
    def test_data_type_key_for_name_falls_back_cleanly(self):
        self.assertEqual(
            data_type_key_for_name("float", items=TIML_DATA_TYPE_ITEMS, fallback="1"),
            "2",
        )
        self.assertEqual(
            data_type_key_for_name("missing", items=TIML_DATA_TYPE_ITEMS, fallback="1"),
            "1",
        )

    def test_next_available_indices_follow_existing_bindings(self):
        bindings = [
            {"type_index": 0, "transform_index": 0},
            {"type_index": 2, "transform_index": 1},
            {"type_index": 2, "transform_index": 4},
        ]
        self.assertEqual(next_available_type_index(bindings), 3)
        self.assertEqual(next_available_transform_index(bindings, 2), 5)
        self.assertEqual(next_available_transform_index(bindings, 9), 0)

    def test_seed_add_type_defaults_handles_empty_state_without_selected_transform(self):
        block = SimpleNamespace(raw_timeline_label="0x24006667")
        defaults = seed_add_timl_type_defaults(
            [],
            selected_block=block,
            selected_transform=None,
            data_type_items=TIML_DATA_TYPE_ITEMS,
        )
        self.assertEqual(defaults.type_index, 0)
        self.assertEqual(defaults.timeline_hash_hex, "0x24006667")
        self.assertEqual(defaults.datatype_hash_hex, "0x00000000")
        self.assertEqual(defaults.data_type_key, "1")

    def test_seed_add_type_defaults_reuses_selected_transform_metadata(self):
        transform = SimpleNamespace(
            raw_timeline_display="0x24006667",
            raw_datatype_display="0xE64D793E",
            data_type_name="float",
        )
        defaults = seed_add_timl_type_defaults(
            [{"type_index": 0, "transform_index": 0}],
            selected_transform=transform,
            data_type_items=TIML_DATA_TYPE_ITEMS,
        )
        self.assertEqual(defaults.type_index, 1)
        self.assertEqual(defaults.timeline_hash_hex, "0x24006667")
        self.assertEqual(defaults.datatype_hash_hex, "0xE64D793E")
        self.assertEqual(defaults.data_type_key, "2")

    def test_seed_add_transform_defaults_prefers_selected_block_then_empty_fallback(self):
        block = SimpleNamespace(type_index=3, raw_timeline_label="0x24006667")
        from_block = seed_add_timl_transform_defaults(
            [{"type_index": 3, "transform_index": 0}],
            selected_block=block,
            data_type_items=TIML_DATA_TYPE_ITEMS,
        )
        self.assertEqual(from_block.type_index, 3)
        self.assertEqual(from_block.transform_index, 1)
        self.assertEqual(from_block.timeline_hash_hex, "0x24006667")
        self.assertEqual(from_block.datatype_hash_hex, "0x00000000")
        self.assertEqual(from_block.data_type_key, "1")

        empty = seed_add_timl_transform_defaults([], data_type_items=TIML_DATA_TYPE_ITEMS)
        self.assertEqual(empty.type_index, 0)
        self.assertEqual(empty.transform_index, 0)
        self.assertEqual(empty.timeline_hash_hex, "0x00000000")
        self.assertEqual(empty.datatype_hash_hex, "0x00000000")
        self.assertEqual(empty.data_type_key, "1")


if __name__ == "__main__":
    unittest.main()
