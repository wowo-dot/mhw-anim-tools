from __future__ import annotations

import unittest

from core.formats.timl.editor_model import TimlEditorTransformView
from core.formats.timl.editor_model import build_timl_editor_block_views
from core.formats.timl.editor_model import timl_editor_field_help_text


class TimlEditorModelTests(unittest.TestCase):
    def test_groups_known_eventloop_transforms_into_one_block(self):
        transforms = [
            TimlEditorTransformView(
                type_index=1,
                transform_index=0,
                property_name="timl_loop_reqno",
                timeline_hash=0x24006667,
                timeline_label="EventLoop",
                datatype_hash=0xE64D793E,
                datatype_label="ReqNo A",
                data_type_name="uint32",
                keyframe_count=1,
                first_frame=0.0,
                last_frame=0.0,
                semantic_label="EventLoop / ReqNo A",
                writeback_status_code="patch_source_values",
                writeback_status_label="Patch Values",
                edit_policy_code="rebuild_capable",
                edit_policy_label="Rebuild OK",
            ),
            TimlEditorTransformView(
                type_index=1,
                transform_index=1,
                property_name="timl_loop_flag",
                timeline_hash=0x24006667,
                timeline_label="EventLoop",
                datatype_hash=0x08FD20A6,
                datatype_label="mFlag",
                data_type_name="uint32",
                keyframe_count=2,
                first_frame=0.0,
                last_frame=40.0,
                semantic_label="EventLoop / mFlag",
                writeback_status_code="preserve_raw",
                writeback_status_label="Preserve Raw",
                edit_policy_code="rebuild_capable",
                edit_policy_label="Rebuild OK",
            ),
        ]

        blocks = build_timl_editor_block_views(transforms)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_label, "EventLoop")
        self.assertTrue(blocks[0].known_semantic)
        self.assertEqual(blocks[0].transform_count, 2)
        self.assertEqual(blocks[0].keyframe_count, 3)
        self.assertEqual(blocks[0].first_frame, 0.0)
        self.assertEqual(blocks[0].last_frame, 40.0)
        self.assertIn("ReqNo A 1", blocks[0].datatype_summary)
        self.assertIn("Patch Values 1", blocks[0].writeback_summary)

    def test_unknown_timeline_stays_visible_and_raw(self):
        transforms = [
            TimlEditorTransformView(
                type_index=3,
                transform_index=4,
                property_name="timl_unknown",
                timeline_hash=0x12345678,
                timeline_label="0x12345678",
                datatype_hash=0x87654321,
                datatype_label="0x87654321",
                data_type_name="float",
                keyframe_count=1,
                first_frame=5.0,
                last_frame=5.0,
                semantic_label="0x12345678 / 0x87654321",
                writeback_status_code="unsupported_rebuild",
                writeback_status_label="Blocked",
                edit_policy_code="blocked",
                edit_policy_label="Blocked",
            ),
        ]

        blocks = build_timl_editor_block_views(transforms)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_label, "Unknown Timeline 0x12345678")
        self.assertFalse(blocks[0].known_semantic)
        self.assertEqual(blocks[0].raw_timeline_label, "0x12345678")
        self.assertIn("Unknown timeline family", blocks[0].help_text)

    def test_known_field_help_text_stays_honest_but_useful(self):
        self.assertIn(
            "request-number",
            timl_editor_field_help_text("EventLoop", "ReqNo A", data_type_name="uint32").lower(),
        )
        self.assertIn(
            "loop-related",
            timl_editor_field_help_text("EventLoop", "0x12345678", data_type_name="float").lower(),
        )
        self.assertIn(
            "0 or 1",
            timl_editor_field_help_text("EventLoop", "mFlag", data_type_name="bool_uint32"),
        )


if __name__ == "__main__":
    unittest.main()
