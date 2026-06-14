from __future__ import annotations

import unittest

from blender_adapter.timl_export import assess_timl_export_readiness
from blender_adapter.timl_export import extract_action_timl_metadata


def _action(
    *,
    name: str,
    import_kind: str = "",
    source_lmt: str = "",
    entry_id: int = 0,
    source_has_timl: bool = False,
):
    return {
        "name": name,
        "mhw_anim_tools_import_kind": import_kind,
        "mhw_anim_tools_source_lmt": source_lmt,
        "mhw_anim_tools_entry_id": entry_id,
        "mhw_anim_tools_source_has_timl": source_has_timl,
    }


class TimlExportReadinessTests(unittest.TestCase):
    def test_extract_action_timl_metadata_reads_known_fields(self):
        metadata = extract_action_timl_metadata(
            _action(
                name="TIML::sample::000",
                import_kind="attached_timl",
                source_lmt="sample.lmt",
                entry_id=5,
                source_has_timl=True,
            )
        )

        self.assertEqual(metadata.name, "TIML::sample::000")
        self.assertEqual(metadata.import_kind, "attached_timl")
        self.assertEqual(metadata.source_lmt, "sample.lmt")
        self.assertEqual(metadata.entry_id, 5)
        self.assertTrue(metadata.source_has_timl)

    def test_attached_timl_controller_action_is_not_exportable_yet(self):
        report = assess_timl_export_readiness(
            _action(
                name="TIML::sample::000",
                import_kind="attached_timl",
                source_lmt="sample.lmt",
                entry_id=5,
            ),
            [],
        )

        self.assertEqual(report.error_count, 1)
        self.assertEqual(report.warning_count, 0)
        self.assertEqual(report.diagnostics[0].code, "lmt.export.timl_edit_unsupported")

    def test_matching_timl_controller_action_warns_that_edits_are_ignored(self):
        export_action = _action(
            name="LMT::sample::005",
            import_kind="lmt_action",
            source_lmt="sample.lmt",
            entry_id=5,
            source_has_timl=True,
        )
        imported_timl = _action(
            name="TIML::sample::005",
            import_kind="attached_timl",
            source_lmt="sample.lmt",
            entry_id=5,
        )

        report = assess_timl_export_readiness(export_action, [export_action, imported_timl])

        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 1)
        self.assertEqual(report.diagnostics[0].code, "lmt.export.timl_edits_ignored")

    def test_non_timl_action_with_no_matching_controller_is_clear(self):
        export_action = _action(
            name="LMT::sample::005",
            import_kind="lmt_action",
            source_lmt="sample.lmt",
            entry_id=5,
            source_has_timl=True,
        )

        report = assess_timl_export_readiness(export_action, [export_action])

        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 0)


if __name__ == "__main__":
    unittest.main()
