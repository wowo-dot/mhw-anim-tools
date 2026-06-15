from __future__ import annotations

from types import SimpleNamespace
import unittest

from blender_adapter.export_impact import build_export_impact_summary
from blender_adapter.export_workflow import ExportSourceMetadata
from blender_adapter.timl_metadata import TIML_ACTION_NAME_KEY
from blender_adapter.timl_metadata import TIML_BINDINGS_KEY
from blender_adapter.timl_metadata import TIML_ENTRY_ID_KEY
from blender_adapter.timl_metadata import TIML_SOURCE_LMT_KEY
from blender_adapter.timl_metadata import TIML_SOURCE_OFFSET_KEY


class _FakeAnimationData:
    def __init__(self, action):
        self.action = action


class _FakeAction(dict):
    def __init__(self, name: str, **metadata):
        super().__init__(metadata)
        self.name = name


class _FakeController(dict):
    def __init__(self, name: str, *, action=None, **metadata):
        super().__init__(metadata)
        self.name = name
        self.animation_data = _FakeAnimationData(action)


class _FakeHeader:
    def __init__(self, timl_offset: int):
        self.timl_offset = int(timl_offset)


class _FakeSourceAction:
    def __init__(self, action_id: int, timl_offset: int):
        self.id = int(action_id)
        self.header = _FakeHeader(timl_offset)


class _FakeSourceLmt:
    def __init__(self, source_name: str, actions):
        self.source_name = source_name
        self.actions = tuple(actions)


class ExportImpactTests(unittest.TestCase):
    def test_build_export_impact_summary_reports_merge_and_sibling_preservation(self):
        action = _FakeAction(
            "LMT::sample::041",
            mhw_anim_tools_source_lmt="sample.lmt",
            mhw_anim_tools_entry_id=41,
        )
        source_lmt = _FakeSourceLmt(
            "sample.lmt",
            [
                _FakeSourceAction(41, 0),
                _FakeSourceAction(42, 0),
                _FakeSourceAction(43, 0),
            ],
        )
        metadata = ExportSourceMetadata(
            action_id=41,
            source_context=SimpleNamespace(source_name="sample.lmt", action_count=3, timl_offset=0),
            source_lmt=source_lmt,
            export_mode="merge",
        )

        summary = build_export_impact_summary(action, metadata, [])

        self.assertEqual(summary.export_mode, "merge")
        self.assertEqual(summary.source_name, "sample.lmt")
        self.assertEqual(summary.entry_id, 41)
        self.assertEqual(summary.source_action_count, 3)
        self.assertTrue(summary.preserves_siblings)
        self.assertEqual(summary.matching_timl_controller_count, 0)
        self.assertEqual(summary.timl_source_scope_label, "")
        self.assertEqual(summary.timl_writeback_scope_label, "")

    def test_build_export_impact_summary_reports_shared_timl_writeback_scope(self):
        action = _FakeAction(
            "LMT::sample::041",
            mhw_anim_tools_source_lmt="sample.lmt",
            mhw_anim_tools_entry_id=41,
            mhw_anim_tools_source_timl_offset=224,
            mhw_anim_tools_source_has_timl=True,
        )
        controller_action = _FakeAction("TIML::sample::041")
        controller = _FakeController(
            "TIML Controller::sample::041",
            action=controller_action,
            **{
                TIML_SOURCE_LMT_KEY: "sample.lmt",
                TIML_ENTRY_ID_KEY: 41,
                TIML_SOURCE_OFFSET_KEY: 224,
                TIML_ACTION_NAME_KEY: controller_action.name,
                TIML_BINDINGS_KEY: "[]",
            },
        )
        source_lmt = _FakeSourceLmt(
            "sample.lmt",
            [
                _FakeSourceAction(41, 224),
                _FakeSourceAction(455, 224),
                _FakeSourceAction(700, 0),
            ],
        )
        metadata = ExportSourceMetadata(
            action_id=41,
            source_context=SimpleNamespace(source_name="sample.lmt", action_count=3, timl_offset=224),
            source_lmt=source_lmt,
            export_mode="merge",
            replacement_timl_payloads={224: SimpleNamespace(payload=b"timl", rebase_offsets=())},
        )

        summary = build_export_impact_summary(action, metadata, [controller])

        self.assertEqual(summary.matching_timl_controller_count, 1)
        self.assertEqual(summary.matching_timl_controller_names, ("TIML Controller::sample::041",))
        self.assertEqual(summary.timl_source_scope_label, "Shared by source actions 041, 455")
        self.assertEqual(summary.timl_writeback_scope_label, "Shared by source actions 041, 455")

    def test_build_export_impact_summary_uses_standalone_defaults(self):
        action = _FakeAction(
            "LMT::standalone::000",
            mhw_anim_tools_entry_id=0,
        )
        metadata = ExportSourceMetadata(
            action_id=0,
            export_mode="standalone",
        )

        summary = build_export_impact_summary(action, metadata, [])

        self.assertEqual(summary.export_mode, "standalone")
        self.assertEqual(summary.source_name, "")
        self.assertEqual(summary.source_action_count, 0)
        self.assertFalse(summary.preserves_siblings)
        self.assertEqual(summary.matching_timl_controller_count, 0)
        self.assertEqual(summary.matching_timl_controller_names, ())
        self.assertEqual(summary.timl_source_scope_label, "")
        self.assertEqual(summary.timl_writeback_scope_label, "")


if __name__ == "__main__":
    unittest.main()
