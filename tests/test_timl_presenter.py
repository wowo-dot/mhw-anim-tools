import unittest

from ui.timl_presenter import build_timl_analysis_summary
from ui.timl_presenter import build_timl_edit_policy_summary
from ui.timl_presenter import build_timl_source_summary
from ui.timl_presenter import build_timl_transform_labels
from ui.timl_presenter import build_timl_writeback_summary
from ui.timl_presenter import timl_transform_identity_label
from ui.timl_presenter import timl_transform_semantic_label


class TimlPresenterTests(unittest.TestCase):
    def test_identity_label_is_stable(self):
        self.assertEqual(timl_transform_identity_label(0, 2), "Type 00 / Transform 02")

    def test_semantic_label_prefers_timeline_and_datatype(self):
        self.assertEqual(
            timl_transform_semantic_label("EventLoop", "ReqNo A", data_type_name="uint32"),
            "EventLoop / ReqNo A",
        )

    def test_build_transform_labels_uses_curated_known_hashes(self):
        labels = build_timl_transform_labels(
            type_index=0,
            transform_index=1,
            timeline_hash=0x24006667,
            datatype_hash=0xE64D793E,
            data_type_name="uint32",
        )
        self.assertEqual(labels["identity_label"], "Type 00 / Transform 01")
        self.assertEqual(labels["timeline_label"], "EventLoop")
        self.assertEqual(labels["datatype_label"], "ReqNo A")
        self.assertEqual(labels["semantic_label"], "EventLoop / ReqNo A")
        self.assertEqual(labels["raw_timeline_label"], "0x24006667")
        self.assertEqual(labels["raw_datatype_label"], "0xE64D793E")

    def test_build_transform_labels_falls_back_cleanly_for_unknown_hashes(self):
        labels = build_timl_transform_labels(
            type_index=1,
            transform_index=0,
            timeline_hash=0x12345678,
            datatype_hash=0x87654321,
            data_type_name="float",
        )
        self.assertEqual(labels["timeline_label"], "0x12345678")
        self.assertEqual(labels["datatype_label"], "0x87654321")
        self.assertEqual(labels["semantic_label"], "0x12345678 / 0x87654321")

    def test_build_source_summary_compacts_real_identity(self):
        summary = build_timl_source_summary(
            source_name=r"D:\foo\bar\stm730_084_00.lmt",
            entry_id=0,
            source_offset=0x440,
        )
        self.assertEqual(summary, "stm730_084_00.lmt | Entry 000 | Offset 0x440")

    def test_build_analysis_summary_is_compact_and_stable(self):
        summary = build_timl_analysis_summary(
            transform_count=3,
            keyframe_count=4,
            frame_end=40,
            warning_count=1,
            error_count=0,
        )
        self.assertEqual(summary, "Transforms 3 | Keys 4 | Frame end 40 | Warnings 1 | Errors 0")

    def test_build_writeback_summary_is_compact_and_stable(self):
        summary = build_timl_writeback_summary(
            preserve_raw_count=1,
            patch_values_count=2,
            rebuild_count=0,
            blocked_count=1,
        )
        self.assertEqual(summary, "Preserve 1 | Patch 2 | Rebuild 0 | Blocked 1")

    def test_build_edit_policy_summary_is_compact_and_stable(self):
        summary = build_timl_edit_policy_summary(
            value_only_count=2,
            rebuild_capable_count=1,
            blocked_count=0,
        )
        self.assertEqual(summary, "Value Only 2 | Rebuild OK 1 | Blocked 0")


if __name__ == "__main__":
    unittest.main()
