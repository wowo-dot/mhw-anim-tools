# -*- coding: utf-8 -*-
"""Milestone-one import/inspection operators."""

import os
from pathlib import Path

import bpy
from bpy_extras.io_utils import ImportHelper

from ..blender_adapter.actions import import_lmt_action_to_armature
from ..blender_adapter.lmt_session import build_file_summary
from ..core.formats.lmt.reader import read_lmt_bytes
from ..core.formats.lmt.reader import read_lmt_file
from ..core.formats.lmt.validation import validate_lmt
from .properties import add_diagnostic
from .properties import clear_diagnostics
from .properties import _populate_track_items
from .properties import _populate_timl_transform_items


class MHWANIMTOOLS_OT_inspect_lmt(bpy.types.Operator, ImportHelper):
    bl_idname = "mhw_anim_tools.inspect_lmt"
    bl_label = "Inspect LMT"
    bl_description = "Parse an LMT with the new core and report high-level counts"

    filename_ext = ".lmt"
    filter_glob: bpy.props.StringProperty(default="*.lmt", options={"HIDDEN"}, maxlen=255)

    def execute(self, context):
        source_bytes = Path(self.filepath).read_bytes()
        lmt = read_lmt_bytes(source_bytes, source_name=self.filepath)
        report = validate_lmt(lmt)
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        scene_props.lmt_entries.clear()
        action_summaries = build_file_summary(lmt, source_bytes=source_bytes)
        for action_summary in action_summaries:
            item = scene_props.lmt_entries.add()
            item.entry_id = action_summary["entry_id"]
            item.frame_count = action_summary["frame_count"]
            item.loop_frame = action_summary["loop_frame"]
            item.track_count = action_summary["track_count"]
            item.has_timl = action_summary["has_timl"]
            item.flags_hex = action_summary["flags_hex"]
            item.flags2_hex = action_summary["flags2_hex"]
            item.translation_preview = action_summary["translation_preview"]
            item.rotation_preview = action_summary["rotation_preview"]
            item.track_breakdown = action_summary["track_breakdown"]
            item.track_payload = action_summary["track_payload"]
            item.timl_source_offset_display = (
                f"0x{int(action_summary['timl_source_offset']):X}" if action_summary["timl_source_offset"] else ""
            )
            item.timl_type_count = int(action_summary["timl_type_count"])
            item.timl_transform_count = int(action_summary["timl_transform_count"])
            item.timl_keyframe_count = int(action_summary["timl_keyframe_count"])
            item.timl_animation_length = float(action_summary["timl_animation_length"])
            item.timl_loop_start_point = float(action_summary["timl_loop_start_point"])
            item.timl_loop_control = int(action_summary["timl_loop_control"])
            item.timl_data_type_breakdown = action_summary["timl_data_type_breakdown"]
            item.timl_timeline_breakdown = action_summary["timl_timeline_breakdown"]
            item.timl_transform_payload = action_summary["timl_transform_payload"]
            item.timl_parse_error = action_summary["timl_parse_error"]
        scene_props.selected_entry_index = 0
        _populate_track_items(scene_props)
        _populate_timl_transform_items(scene_props)
        scene_props.last_lmt_path = self.filepath
        scene_props.last_entry_count = lmt.header.entry_count
        scene_props.last_action_count = lmt.action_count
        scene_props.last_track_count = lmt.track_count
        scene_props.last_warning_count = report.warning_count
        scene_props.last_error_count = report.error_count
        scene_props.last_status = (
            f"Parsed {os.path.basename(self.filepath)}: "
            f"entries={lmt.header.entry_count}, actions={lmt.action_count}, "
            f"tracks={lmt.track_count}, warnings={report.warning_count}, "
            f"errors={report.error_count}"
        )
        if report.warning_count:
            add_diagnostic(scene_props, "WARNING", "validation", f"LMT validation reported {report.warning_count} warning(s).")
        if report.error_count:
            add_diagnostic(scene_props, "ERROR", "validation", f"LMT validation reported {report.error_count} error(s).")
        for action_summary in action_summaries:
            if action_summary["timl_parse_error"]:
                add_diagnostic(
                    scene_props,
                    "WARNING",
                    "timl",
                    f"Entry {int(action_summary['entry_id']):03d} attached TIML could not be parsed: {action_summary['timl_parse_error']}",
                )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_import_selected_lmt_action(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.import_selected_lmt_action"
    bl_label = "Import Selected Action"
    bl_description = "Create a Blender Action on the selected target armature from the chosen LMT entry"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        if not scene_props.last_lmt_path:
            scene_props.last_status = "Inspect an LMT file before importing an action."
            add_diagnostic(scene_props, "ERROR", "session", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        if scene_props.target_armature is None:
            scene_props.last_status = "Choose a target armature before importing an action."
            add_diagnostic(scene_props, "ERROR", "armature", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        lmt = read_lmt_file(scene_props.last_lmt_path)
        result = import_lmt_action_to_armature(
            lmt,
            scene_props.selected_entry_index,
            scene_props.target_armature,
            source_path=scene_props.last_lmt_path,
        )
        for diagnostic in result.diagnostics:
            add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)
        if result.error_count:
            scene_props.last_status = (
                f"Import failed: {result.error_count} error(s), {result.warning_count} warning(s)."
            )
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        scene_props.last_imported_action_name = result.action_name
        scene_props.export_action = bpy.data.actions.get(result.action_name)
        if result.frame_end:
            context.scene.frame_start = min(int(context.scene.frame_start), 0)
            context.scene.frame_end = max(int(context.scene.frame_end), result.frame_end)
        scene_props.last_status = (
            f"Imported {result.action_name}: "
            f"tracks={result.imported_track_count}, "
            f"skipped={result.skipped_track_count}, "
            f"warnings={result.warning_count}"
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_clear_lmt_session(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.clear_lmt_session"
    bl_label = "Clear Session"
    bl_description = "Clear the currently loaded LMT session summary"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        scene_props.lmt_entries.clear()
        scene_props.lmt_tracks.clear()
        scene_props.timl_transforms.clear()
        scene_props.selected_entry_index = 0
        scene_props.selected_track_index = 0
        scene_props.selected_timl_transform_index = 0
        scene_props.last_lmt_path = ""
        scene_props.last_entry_count = 0
        scene_props.last_action_count = 0
        scene_props.last_track_count = 0
        scene_props.last_warning_count = 0
        scene_props.last_error_count = 0
        scene_props.last_imported_action_name = ""
        scene_props.export_action = None
        scene_props.last_export_action_name = ""
        scene_props.last_export_track_count = 0
        scene_props.last_export_sparse_key_count = 0
        scene_props.last_export_supported_track_count = 0
        scene_props.last_export_frame_count = 0
        scene_props.last_export_buffer_summary = ""
        scene_props.last_export_warning_count = 0
        scene_props.last_export_error_count = 0
        scene_props.last_status = "Cleared LMT session."
        return {"FINISHED"}


classes = (
    MHWANIMTOOLS_OT_inspect_lmt,
    MHWANIMTOOLS_OT_import_selected_lmt_action,
    MHWANIMTOOLS_OT_clear_lmt_session,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
