from __future__ import annotations

import unittest

from ui.timl_labels import count_timl_writeback_statuses
from ui.timl_labels import timl_writeback_reason_label
from ui.timl_labels import timl_writeback_status_label


class TimlUiLabelTests(unittest.TestCase):
    def test_locked_writeback_status_labels_are_stable(self):
        self.assertEqual(timl_writeback_status_label("preserve_raw"), "Preserve Raw")
        self.assertEqual(timl_writeback_status_label("patch_source_values"), "Patch Values")
        self.assertEqual(timl_writeback_status_label("rewrite_preview"), "Rebuild Preview")
        self.assertEqual(timl_writeback_status_label("unsupported_rebuild"), "Blocked")

    def test_reason_label_mentions_constant_or_linear_for_blocked_rebuilds(self):
        message = timl_writeback_reason_label("unsupported_rebuild")
        self.assertIn("CONSTANT", message)
        self.assertIn("LINEAR", message)

    def test_status_counter_tracks_each_writeback_mode(self):
        counts = count_timl_writeback_statuses(
            [
                "preserve_raw",
                "patch_source_values",
                "patch_source_values",
                "rewrite_preview",
                "unsupported_rebuild",
            ]
        )
        self.assertEqual(
            counts,
            {
                "preserve_raw": 1,
                "patch_source_values": 2,
                "rewrite_preview": 1,
                "unsupported_rebuild": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
