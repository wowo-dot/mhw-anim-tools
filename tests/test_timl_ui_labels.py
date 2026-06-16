from __future__ import annotations

import unittest

from ui.timl_labels import count_timl_writeback_statuses
from ui.timl_labels import count_timl_edit_policies
from ui.timl_labels import timl_edit_policy_code
from ui.timl_labels import timl_edit_policy_label
from ui.timl_labels import timl_edit_policy_reason_label
from ui.timl_labels import timl_payload_scope_label
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

    def test_reason_label_mentions_binding_metadata_for_blocked_source_mismatch(self):
        message = timl_writeback_reason_label("unsupported_rebuild", reason="timeline_hash_mismatch")
        self.assertIn("binding metadata", message.lower())

    def test_reason_label_mentions_source_semantics_for_advanced_rebuild_block(self):
        message = timl_writeback_reason_label("unsupported_rebuild", reason="advanced_source_rebuild")
        self.assertIn("source-only easing/interpolation semantics", message)

    def test_reason_label_mentions_quantization_for_integer_blocks(self):
        message = timl_writeback_reason_label("unsupported_rebuild", reason="integer_off_grid")
        self.assertIn("lossy quantization", message)
        self.assertIn("whole-number", message)

    def test_reason_label_mentions_boolean_domain_for_boolean_blocks(self):
        message = timl_writeback_reason_label("unsupported_rebuild", reason="boolean_off_grid")
        self.assertIn("0 or 1", message)

    def test_reason_label_mentions_range_for_color_blocks(self):
        message = timl_writeback_reason_label("unsupported_rebuild", reason="color_range")
        self.assertIn("0..1", message)
        self.assertIn("color range", message)

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

    def test_edit_policy_marks_advanced_source_as_value_only(self):
        policy = timl_edit_policy_code(source_advanced=True)
        self.assertEqual(policy, "value_only")
        self.assertEqual(timl_edit_policy_label(policy), "Value Only")
        self.assertIn("value-only edits remain safe", timl_edit_policy_reason_label(policy))

    def test_edit_policy_marks_simple_source_as_rebuild_capable(self):
        policy = timl_edit_policy_code(source_advanced=False)
        self.assertEqual(policy, "rebuild_capable")
        self.assertEqual(timl_edit_policy_label(policy), "Rebuild OK")
        self.assertIn("rebuilt from Blender preview keys", timl_edit_policy_reason_label(policy))

    def test_edit_policy_marks_missing_preview_binding_as_blocked(self):
        policy = timl_edit_policy_code(
            source_advanced=False,
            status="preserve_raw",
            reason="missing_sampled_transform",
        )
        self.assertEqual(policy, "blocked")
        self.assertIn(
            "sampled preview binding",
            timl_edit_policy_reason_label(policy, reason="missing_sampled_transform"),
        )

    def test_edit_policy_marks_binding_mismatch_as_blocked(self):
        policy = timl_edit_policy_code(
            source_advanced=False,
            status="unsupported_rebuild",
            reason="timeline_hash_mismatch",
        )
        self.assertEqual(policy, "blocked")
        self.assertEqual(timl_edit_policy_label(policy), "Blocked")

    def test_edit_policy_reason_mentions_contiguous_layout_for_extra_transform(self):
        policy = timl_edit_policy_code(
            source_advanced=False,
            status="unsupported_rebuild",
            reason="extra_sampled_transform",
        )
        self.assertEqual(policy, "blocked")
        self.assertIn(
            "contiguous",
            timl_edit_policy_reason_label(policy, reason="extra_sampled_transform"),
        )

    def test_edit_policy_marks_deleted_source_transform_as_blocked(self):
        policy = timl_edit_policy_code(
            source_advanced=False,
            status="unsupported_rebuild",
            reason="deleted_source_transform",
        )
        self.assertEqual(policy, "blocked")
        self.assertIn(
            "marked for deletion",
            timl_edit_policy_reason_label(policy, reason="deleted_source_transform"),
        )

    def test_reason_label_mentions_structural_delete_limit(self):
        message = timl_writeback_reason_label("unsupported_rebuild", reason="deleted_source_transform")
        self.assertIn("marked for deletion", message)
        self.assertIn("contiguous", message)

    def test_reason_label_mentions_reindexing_for_layout_gaps(self):
        message = timl_writeback_reason_label("unsupported_rebuild", reason="transform_index_layout")
        self.assertIn("not contiguous", message)
        self.assertIn("reindexed", message)

    def test_edit_policy_counter_tracks_each_mode(self):
        counts = count_timl_edit_policies(
            [
                "value_only",
                "value_only",
                "rebuild_capable",
                "blocked",
            ]
        )
        self.assertEqual(
            counts,
            {
                "value_only": 2,
                "rebuild_capable": 1,
                "blocked": 1,
            },
        )

    def test_payload_scope_label_marks_shared_payloads(self):
        self.assertEqual(
            timl_payload_scope_label((7, 8)),
            "Shared by source actions 007, 008",
        )
        self.assertEqual(
            timl_payload_scope_label((7,)),
            "Unique to source action 007",
        )


if __name__ == "__main__":
    unittest.main()
