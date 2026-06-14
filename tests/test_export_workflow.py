from __future__ import annotations

from types import SimpleNamespace
import unittest

from blender_adapter.export_workflow import effective_export_action
from blender_adapter.export_workflow import resolve_source_action_export_metadata


class _Action(dict):
    def __init__(self, name: str, **metadata):
        super().__init__(metadata)
        self.name = name


class ExportWorkflowTests(unittest.TestCase):
    def test_effective_export_action_prefers_explicit_scene_selection(self):
        explicit = object()
        active = object()
        scene_props = SimpleNamespace(
            export_action=explicit,
            target_armature=SimpleNamespace(animation_data=SimpleNamespace(action=active)),
        )

        self.assertIs(effective_export_action(scene_props), explicit)

    def test_effective_export_action_falls_back_to_active_armature_action(self):
        active = object()
        scene_props = SimpleNamespace(
            export_action=None,
            target_armature=SimpleNamespace(animation_data=SimpleNamespace(action=active)),
        )

        self.assertIs(effective_export_action(scene_props), active)

    def test_resolve_source_metadata_falls_back_to_cached_context_when_path_missing(self):
        scene_props = SimpleNamespace(
            last_lmt_path="",
            lmt_entries=[],
            selected_entry_index=0,
        )
        action = _Action(
            "LMT::sample::005",
            mhw_anim_tools_entry_id=5,
            mhw_anim_tools_source_lmt="",
            mhw_anim_tools_source_version=95,
            mhw_anim_tools_source_entry_count=1,
            mhw_anim_tools_source_action_count=1,
            mhw_anim_tools_source_has_timl=False,
            mhw_anim_tools_source_timl_offset=0,
        )

        metadata, report = resolve_source_action_export_metadata(scene_props, action)

        self.assertEqual(metadata.export_mode, "standalone")
        self.assertEqual(metadata.version, 95)
        self.assertEqual(metadata.action_id, 5)
        self.assertEqual(report.warning_count, 1)
        self.assertEqual(report.error_count, 0)


if __name__ == "__main__":
    unittest.main()
