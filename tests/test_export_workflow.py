from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from blender_adapter.export_workflow import effective_export_action
from blender_adapter.export_workflow import resolve_source_action_export_metadata
from blender_adapter.export_workflow import source_export_actions
from blender_adapter.lmt_track_metadata import save_lmt_import_track_bindings
from blender_adapter.source_identity import SOURCE_FILE_SHA256_KEY
from blender_adapter.source_identity import SOURCE_FILE_SIZE_KEY
from core.formats.lmt.export_context import LmtSourceActionExportContext


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

    def test_resolve_source_metadata_errors_when_imported_action_is_missing_source_path(self):
        scene_props = SimpleNamespace(
            last_lmt_path="",
            lmt_entries=[],
            selected_entry_index=0,
        )
        action = _Action(
            "LMT::sample::005",
            mhw_anim_tools_import_kind="lmt_action",
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
        self.assertEqual(report.error_count, 1)
        self.assertEqual(report.diagnostics[0].code, "lmt.export.source_path")

    def test_resolve_source_metadata_errors_when_imported_action_lacks_identity_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "sample.lmt"
            source_path.write_bytes(b"LMT")
            scene_props = SimpleNamespace(
                last_lmt_path="",
                lmt_entries=[],
                selected_entry_index=0,
            )
            action = _Action(
                "LMT::sample::005",
                mhw_anim_tools_import_kind="lmt_action",
                mhw_anim_tools_entry_id=5,
                mhw_anim_tools_source_lmt=str(source_path),
            )

            with patch("blender_adapter.export_workflow.read_lmt_bytes", return_value=object()):
                with patch(
                    "blender_adapter.export_workflow.build_source_action_export_context",
                    return_value=LmtSourceActionExportContext(
                        source_name=str(source_path),
                        version=95,
                        header_unknown=b"\x00" * 8,
                        entry_count=1,
                        action_count=1,
                        action_id=5,
                        loop_frame=-1,
                        null0=(0, 0, 0),
                        translation=(0.0, 0.0, 0.0, 0.0),
                        rotation_lerp=(0.0, 0.0, 0.0, 1.0),
                        flags=0,
                        null2=b"\x00\x00",
                        flags2=0,
                        null3=(0, 0, 0, 0, 0),
                        has_timl=False,
                        timl_offset=0,
                        track_metadata_by_identity={},
                        track_metadata_by_index={},
                    ),
                ):
                    _metadata, report = resolve_source_action_export_metadata(scene_props, action)

        self.assertEqual(report.error_count, 1)
        self.assertEqual(report.diagnostics[0].code, "lmt.export.source_identity")

    def test_resolve_source_metadata_errors_when_imported_action_has_invalid_entry_metadata(self):
        scene_props = SimpleNamespace(
            last_lmt_path="fallback.lmt",
            lmt_entries=[],
            selected_entry_index=0,
        )
        action = _Action(
            "LMT::sample::broken",
            mhw_anim_tools_import_kind="lmt_action",
            mhw_anim_tools_entry_id="not-an-int",
            mhw_anim_tools_source_lmt="sample.lmt",
        )

        _metadata, report = resolve_source_action_export_metadata(scene_props, action)

        self.assertEqual(report.error_count, 1)
        self.assertEqual(report.diagnostics[0].code, "lmt.export.source_entry")

    def test_resolve_source_metadata_errors_when_imported_source_file_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "sample.lmt"
            source_bytes = b"LMT"
            source_path.write_bytes(source_bytes)
            scene_props = SimpleNamespace(
                last_lmt_path="",
                lmt_entries=[],
                selected_entry_index=0,
            )
            action = _Action(
                "LMT::sample::005",
                mhw_anim_tools_import_kind="lmt_action",
                mhw_anim_tools_entry_id=5,
                mhw_anim_tools_source_lmt=str(source_path),
                **{
                    SOURCE_FILE_SIZE_KEY: len(source_bytes) + 1,
                    SOURCE_FILE_SHA256_KEY: "0" * 64,
                },
            )

            with patch("blender_adapter.export_workflow.read_lmt_bytes", return_value=object()):
                with patch(
                    "blender_adapter.export_workflow.build_source_action_export_context",
                    return_value=LmtSourceActionExportContext(
                        source_name=str(source_path),
                        version=95,
                        header_unknown=b"\x00" * 8,
                        entry_count=1,
                        action_count=1,
                        action_id=5,
                        loop_frame=-1,
                        null0=(0, 0, 0),
                        translation=(0.0, 0.0, 0.0, 0.0),
                        rotation_lerp=(0.0, 0.0, 0.0, 1.0),
                        flags=0,
                        null2=b"\x00\x00",
                        flags2=0,
                        null3=(0, 0, 0, 0, 0),
                        has_timl=False,
                        timl_offset=0,
                        track_metadata_by_identity={},
                        track_metadata_by_index={},
                    ),
                ):
                    _metadata, report = resolve_source_action_export_metadata(scene_props, action)

        self.assertEqual(report.error_count, 1)
        self.assertEqual(report.diagnostics[0].code, "lmt.export.source_identity")
        self.assertIn("has changed since import", report.diagnostics[0].message)

    def test_resolve_source_metadata_errors_when_imported_source_read_fails(self):
        scene_props = SimpleNamespace(
            last_lmt_path="",
            lmt_entries=[],
            selected_entry_index=0,
        )
        action = _Action(
            "LMT::sample::005",
            mhw_anim_tools_import_kind="lmt_action",
            mhw_anim_tools_entry_id=5,
            mhw_anim_tools_source_lmt="missing.lmt",
            **{
                SOURCE_FILE_SIZE_KEY: 3,
                SOURCE_FILE_SHA256_KEY: "0" * 64,
            },
        )

        with patch("pathlib.Path.read_bytes", side_effect=OSError("missing")):
            _metadata, report = resolve_source_action_export_metadata(scene_props, action)

        self.assertEqual(report.error_count, 1)
        self.assertEqual(report.diagnostics[0].code, "lmt.export.source_read")

    def test_resolve_source_metadata_errors_when_imported_source_entry_is_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "sample.lmt"
            source_bytes = b"LMT"
            source_path.write_bytes(source_bytes)
            scene_props = SimpleNamespace(
                last_lmt_path="",
                lmt_entries=[],
                selected_entry_index=0,
            )
            action = _Action(
                "LMT::sample::005",
                mhw_anim_tools_import_kind="lmt_action",
                mhw_anim_tools_entry_id=5,
                mhw_anim_tools_source_lmt=str(source_path),
                **{
                    SOURCE_FILE_SIZE_KEY: len(source_bytes),
                    SOURCE_FILE_SHA256_KEY: "b1ce5beca8515c53ee6b56242a4401ef07fb4e31448f3486837449d276001664",
                },
            )

            with patch("blender_adapter.export_workflow.read_lmt_bytes", return_value=object()):
                with patch(
                    "blender_adapter.export_workflow.build_source_action_export_context",
                    side_effect=ValueError("missing entry"),
                ):
                    _metadata, report = resolve_source_action_export_metadata(scene_props, action)

        self.assertEqual(report.error_count, 1)
        self.assertEqual(report.diagnostics[0].code, "lmt.export.source_entry")

    def test_resolve_source_metadata_blocks_duplicate_raw_track_identities(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "duplicate.lmt"
            source_path.write_bytes(b"LMT")
            scene_props = SimpleNamespace(
                last_lmt_path="",
                lmt_entries=[],
                selected_entry_index=0,
            )
            action = _Action(
                "LMT::duplicate::000",
                mhw_anim_tools_entry_id=0,
                mhw_anim_tools_source_lmt=str(source_path),
            )
            source_context = LmtSourceActionExportContext(
                source_name=str(source_path),
                version=95,
                header_unknown=b"\x00" * 8,
                entry_count=1,
                action_count=1,
                action_id=0,
                loop_frame=-1,
                null0=(0, 0, 0),
                translation=(0.0, 0.0, 0.0, 0.0),
                rotation_lerp=(0.0, 0.0, 0.0, 1.0),
                flags=0,
                null2=b"\x00\x00",
                flags2=0,
                null3=(0, 0, 0, 0, 0),
                has_timl=False,
                timl_offset=0,
                track_metadata_by_identity={(0, 1): {"buffer_type": 1}},
                track_metadata_by_index={0: {"buffer_type": 1}, 1: {"buffer_type": 1}},
                duplicate_track_identities=((0, 1, 2),),
            )

            with patch("blender_adapter.export_workflow.read_lmt_bytes", return_value=object()):
                with patch(
                    "blender_adapter.export_workflow.build_source_action_export_context",
                    return_value=source_context,
                ):
                    metadata, report = resolve_source_action_export_metadata(scene_props, action)

        self.assertEqual(metadata.export_mode, "merge")
        self.assertEqual(report.error_count, 1)
        self.assertEqual(report.diagnostics[0].code, "lmt.export.track_identity")
        self.assertIn("raw-slot bindings", report.diagnostics[0].message)

    def test_resolve_source_metadata_allows_duplicate_raw_track_identities_with_bindings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "duplicate.lmt"
            source_path.write_bytes(b"LMT")
            scene_props = SimpleNamespace(
                last_lmt_path="",
                lmt_entries=[],
                selected_entry_index=0,
            )
            action = _Action(
                "LMT::duplicate::000",
                mhw_anim_tools_entry_id=0,
                mhw_anim_tools_source_lmt=str(source_path),
            )
            save_lmt_import_track_bindings(
                action,
                [
                    {"track_index": 0, "bone_id": 0, "usage": 1, "import_mode": "raw_duplicate"},
                    {"track_index": 1, "bone_id": 0, "usage": 1, "import_mode": "raw_duplicate"},
                ],
            )
            source_context = LmtSourceActionExportContext(
                source_name=str(source_path),
                version=95,
                header_unknown=b"\x00" * 8,
                entry_count=1,
                action_count=1,
                action_id=0,
                loop_frame=-1,
                null0=(0, 0, 0),
                translation=(0.0, 0.0, 0.0, 0.0),
                rotation_lerp=(0.0, 0.0, 0.0, 1.0),
                flags=0,
                null2=b"\x00\x00",
                flags2=0,
                null3=(0, 0, 0, 0, 0),
                has_timl=False,
                timl_offset=0,
                track_metadata_by_identity={(0, 1): {"buffer_type": 1}},
                track_metadata_by_index={0: {"buffer_type": 1}, 1: {"buffer_type": 1}},
                duplicate_track_identities=((0, 1, 2),),
            )

            with patch("blender_adapter.export_workflow.read_lmt_bytes", return_value=object()):
                with patch(
                    "blender_adapter.export_workflow.build_source_action_export_context",
                    return_value=source_context,
                ):
                    metadata, report = resolve_source_action_export_metadata(scene_props, action)

        self.assertEqual(metadata.export_mode, "merge")
        self.assertEqual(report.error_count, 0)

    def test_source_export_actions_collects_matching_imported_lmt_actions_only(self):
        anchor = _Action(
            "LMT::sample::007",
            mhw_anim_tools_import_kind="lmt_action",
            mhw_anim_tools_source_lmt="sample.lmt",
            mhw_anim_tools_entry_id=7,
        )
        actions = [
            _Action(
                "TIML::sample::007",
                mhw_anim_tools_import_kind="attached_timl",
                mhw_anim_tools_source_lmt="sample.lmt",
                mhw_anim_tools_entry_id=7,
            ),
            _Action(
                "LMT::sample::003",
                mhw_anim_tools_import_kind="lmt_action",
                mhw_anim_tools_source_lmt="sample.lmt",
                mhw_anim_tools_entry_id=3,
            ),
            _Action(
                "LMT::other::001",
                mhw_anim_tools_import_kind="lmt_action",
                mhw_anim_tools_source_lmt="other.lmt",
                mhw_anim_tools_entry_id=1,
            ),
            anchor,
        ]
        scene_props = SimpleNamespace(
            export_action=anchor,
            last_lmt_path="",
        )

        source_path, export_actions, report = source_export_actions(scene_props, actions=actions)

        self.assertEqual(source_path, "sample.lmt")
        self.assertEqual([action.name for action in export_actions], ["LMT::sample::003", "LMT::sample::007"])
        self.assertEqual(report.error_count, 0)

    def test_source_export_actions_rejects_timl_controller_anchor(self):
        anchor = _Action(
            "TIML::sample::007",
            mhw_anim_tools_import_kind="attached_timl",
            mhw_anim_tools_source_lmt="sample.lmt",
            mhw_anim_tools_entry_id=7,
        )
        scene_props = SimpleNamespace(
            export_action=anchor,
            last_lmt_path="",
        )

        source_path, export_actions, report = source_export_actions(scene_props, actions=[anchor])

        self.assertEqual(source_path, "")
        self.assertEqual(export_actions, ())
        self.assertEqual(report.error_count, 1)

    def test_source_export_actions_rejects_duplicate_entry_ids(self):
        anchor = _Action(
            "LMT::sample::007",
            mhw_anim_tools_import_kind="lmt_action",
            mhw_anim_tools_source_lmt="sample.lmt",
            mhw_anim_tools_entry_id=7,
        )
        duplicate = _Action(
            "LMT::sample::007.copy",
            mhw_anim_tools_import_kind="lmt_action",
            mhw_anim_tools_source_lmt="sample.lmt",
            mhw_anim_tools_entry_id=7,
        )
        scene_props = SimpleNamespace(
            export_action=anchor,
            last_lmt_path="",
        )

        _source_path, export_actions, report = source_export_actions(
            scene_props,
            actions=[anchor, duplicate],
        )

        self.assertEqual([action.name for action in export_actions], ["LMT::sample::007"])
        self.assertEqual(report.error_count, 1)


if __name__ == "__main__":
    unittest.main()
