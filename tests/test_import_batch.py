from __future__ import annotations

import unittest

from blender_adapter.import_batch import import_all_lmt_actions_to_armature


class _FakeAction:
    def __init__(self, action_id: int):
        self.id = int(action_id)


class _FakeLmt:
    def __init__(self, action_ids):
        self.actions = tuple(_FakeAction(action_id) for action_id in action_ids)


class _FakeSingleResult:
    def __init__(
        self,
        *,
        action_name: str = "",
        imported_track_count: int = 0,
        skipped_track_count: int = 0,
        created_fcurve_count: int = 0,
        frame_end: int = 0,
        diagnostics=(),
        error_count: int = 0,
    ):
        self.action_name = action_name
        self.imported_track_count = imported_track_count
        self.skipped_track_count = skipped_track_count
        self.created_fcurve_count = created_fcurve_count
        self.frame_end = frame_end
        self.diagnostics = tuple(diagnostics)
        self.error_count = int(error_count)


class _FakeDiagnostic:
    def __init__(self, level: str, source: str, message: str):
        self.level = level
        self.source = source
        self.message = message


class ImportBatchTests(unittest.TestCase):
    def test_batch_import_aggregates_successful_actions(self):
        lmt = _FakeLmt([0, 1])

        def _import_action(_lmt, entry_id, _armature_object, *, source_path: str, source_identity=None):
            self.assertEqual(source_path, "sample.lmt")
            self.assertIsNone(source_identity)
            return _FakeSingleResult(
                action_name=f"LMT::sample::{entry_id:03d}",
                imported_track_count=2,
                created_fcurve_count=6,
                frame_end=20 + entry_id,
            )

        result = import_all_lmt_actions_to_armature(
            lmt,
            object(),
            source_path="sample.lmt",
            import_action=_import_action,
        )

        self.assertEqual(result.requested_action_count, 2)
        self.assertEqual(result.imported_action_count, 2)
        self.assertEqual(result.failed_action_count, 0)
        self.assertEqual(result.imported_track_count, 4)
        self.assertEqual(result.created_fcurve_count, 12)
        self.assertEqual(result.frame_end, 21)
        self.assertEqual(
            result.imported_action_names,
            ("LMT::sample::000", "LMT::sample::001"),
        )

    def test_batch_import_continues_after_per_action_failure(self):
        lmt = _FakeLmt([7, 8])

        def _import_action(_lmt, entry_id, _armature_object, *, source_path: str, source_identity=None):
            del source_path
            self.assertIsNone(source_identity)
            if entry_id == 7:
                return _FakeSingleResult(
                    diagnostics=(
                        _FakeDiagnostic("ERROR", "import", "No supported tracks were imported."),
                    ),
                    error_count=1,
                )
            return _FakeSingleResult(
                action_name="LMT::sample::008",
                imported_track_count=3,
                skipped_track_count=1,
                created_fcurve_count=9,
                frame_end=42,
                diagnostics=(
                    _FakeDiagnostic("WARNING", "track 00 / bone 3", "Skipped unsupported buffer type 99."),
                ),
            )

        result = import_all_lmt_actions_to_armature(
            lmt,
            object(),
            source_path="sample.lmt",
            import_action=_import_action,
        )

        self.assertEqual(result.imported_action_count, 1)
        self.assertEqual(result.failed_action_count, 1)
        self.assertEqual(result.imported_track_count, 3)
        self.assertEqual(result.skipped_track_count, 1)
        self.assertEqual(result.frame_end, 42)
        self.assertEqual(result.imported_action_names, ("LMT::sample::008",))
        self.assertTrue(any(item.source.startswith("entry 007 /") for item in result.diagnostics))
        self.assertTrue(any(item.source.startswith("entry 008 /") for item in result.diagnostics))

    def test_batch_import_rejects_missing_entry_ids(self):
        lmt = _FakeLmt([3])

        def _import_action(*args, **kwargs):  # pragma: no cover - should not be called
            raise AssertionError("single-action importer should not run for invalid indices")

        result = import_all_lmt_actions_to_armature(
            lmt,
            object(),
            source_path="sample.lmt",
            import_action=_import_action,
            entry_ids=[1],
        )

        self.assertEqual(result.imported_action_count, 0)
        self.assertEqual(result.failed_action_count, 1)
        self.assertEqual(result.error_count, 1)
        self.assertIn("not present", result.diagnostics[0].message)


if __name__ == "__main__":
    unittest.main()
