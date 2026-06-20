# -*- coding: utf-8 -*-
"""Focused export operators for source-backed LMT and TIML workflows."""

from pathlib import Path
import re

import bpy
from bpy_extras.io_utils import ExportHelper

from ..blender_adapter.export_workflow import analyze_export_action
from ..blender_adapter.export_workflow import analyze_lmt_session_export
from ..blender_adapter.export_workflow import effective_export_action
from ..blender_adapter.export_workflow import write_lmt_session_export_file
from ..blender_adapter.timl_file_export import analyze_standalone_timl_export
from ..blender_adapter.timl_file_export import write_standalone_timl_file
from ..blender_adapter.timl_metadata import TIML_SOURCE_KIND_STANDALONE_FILE
from ..blender_adapter.timl_sampling import extract_timl_controller_metadata
from ..blender_adapter.timl_sampling import is_imported_timl_controller
from ..core.diagnostics.errors import BinaryFormatError
from ..core.diagnostics.errors import ValidationError
from .properties import add_diagnostic
from .properties import clear_export_analysis
from .properties import clear_diagnostics


def _sanitize_export_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\\\|?*]+', "_", name or "export")
    cleaned = cleaned.strip(" ._")
    return cleaned or "export"


def _publish_export_diagnostics(scene_props, diagnostics):
    for diagnostic in diagnostics:
        add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)


def _publish_report_diagnostics(scene_props, report):
    for diagnostic in report.diagnostics:
        add_diagnostic(scene_props, diagnostic.level, diagnostic.code, diagnostic.message)


def _apply_export_summary(scene_props, analysis):
    scene_props.export_action = analysis.action
    clear_export_analysis(scene_props)
    if analysis.sampling_result is None or analysis.reconstructed is None or analysis.plan is None:
        return
    scene_props.last_export_action_name = analysis.sampling_result.action_name
    scene_props.last_export_track_count = analysis.sampling_result.sampled_track_count
    scene_props.last_export_sparse_key_count = analysis.reconstructed.sparse_key_count
    scene_props.last_export_supported_track_count = analysis.plan.supported_track_count
    scene_props.last_export_frame_count = analysis.sampling_result.frame_end
    scene_props.last_export_buffer_summary = analysis.plan.buffer_breakdown
    scene_props.last_export_warning_count = analysis.warning_count
    scene_props.last_export_error_count = analysis.error_count
    scene_props.last_export_mode = analysis.impact_summary.export_mode
    scene_props.last_export_source_name = analysis.impact_summary.source_name
    scene_props.last_export_entry_id = analysis.impact_summary.entry_id
    scene_props.last_export_source_action_count = analysis.impact_summary.source_action_count
    scene_props.last_export_preserves_siblings = analysis.impact_summary.preserves_siblings
    scene_props.last_export_matching_timl_controller_count = analysis.impact_summary.matching_timl_controller_count
    scene_props.last_export_matching_timl_controller_names = ", ".join(analysis.impact_summary.matching_timl_controller_names)
    scene_props.last_export_timl_source_scope = analysis.impact_summary.timl_source_scope_label
    scene_props.last_export_timl_writeback_scope = analysis.impact_summary.timl_writeback_scope_label


def _reset_export_summary(scene_props):
    scene_props.last_export_action_name = ""
    scene_props.last_export_track_count = 0
    scene_props.last_export_sparse_key_count = 0
    scene_props.last_export_supported_track_count = 0
    scene_props.last_export_frame_count = 0
    scene_props.last_export_buffer_summary = ""
    scene_props.last_export_warning_count = 0
    scene_props.last_export_error_count = 0
    scene_props.last_export_mode = ""
    scene_props.last_export_source_name = ""
    scene_props.last_export_entry_id = 0
    scene_props.last_export_source_action_count = 0
    scene_props.last_export_preserves_siblings = False
    scene_props.last_export_matching_timl_controller_count = 0
    scene_props.last_export_matching_timl_controller_names = ""
    scene_props.last_export_timl_source_scope = ""
    scene_props.last_export_timl_writeback_scope = ""


def _apply_session_export_summary(scene_props, export_plan):
    clear_export_analysis(scene_props)
    _reset_export_summary(scene_props)
    if export_plan.analyses:
        _apply_export_summary(scene_props, export_plan.analyses[0])
    scene_props.last_export_warning_count = int(export_plan.warning_count)
    scene_props.last_export_error_count = int(export_plan.error_count)
    scene_props.last_export_mode = "merge"
    scene_props.last_export_source_name = str(export_plan.source_path or "")
    scene_props.last_export_source_action_count = int(export_plan.source_action_count)
    scene_props.last_export_preserves_siblings = int(export_plan.source_action_count) > 1
    if getattr(scene_props, "lmt_entries", None) and 0 <= int(scene_props.selected_entry_index) < len(scene_props.lmt_entries):
        scene_props.last_export_entry_id = int(scene_props.lmt_entries[int(scene_props.selected_entry_index)].entry_id)


def _active_timl_controller(scene_props, context):
    controller = scene_props.timl_controller
    if is_imported_timl_controller(controller):
        return controller
    active_object = getattr(context, "active_object", None)
    if is_imported_timl_controller(active_object):
        return active_object
    if scene_props.last_imported_timl_object_name:
        candidate = bpy.data.objects.get(scene_props.last_imported_timl_object_name)
        if is_imported_timl_controller(candidate):
            return candidate
    source_path = str(scene_props.last_timl_path or "")
    session_id = str(scene_props.last_timl_session_id or "")
    if source_path:
        for candidate in bpy.data.objects:
            if not is_imported_timl_controller(candidate):
                continue
            metadata = extract_timl_controller_metadata(candidate)
            if str(metadata.source_kind or "") != TIML_SOURCE_KIND_STANDALONE_FILE:
                continue
            if str(metadata.source_lmt or "") != source_path:
                continue
            if session_id and str(metadata.session_id or "") != session_id:
                continue
            return candidate
    return None


def _publish_standalone_timl_diagnostics(scene_props, diagnostics):
    for diagnostic in diagnostics:
        add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)


class MHWANIMTOOLS_OT_analyze_export_action(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.analyze_export_action"
    bl_label = "Analyze Export Action"
    bl_description = "Sample the selected Blender Action back into normalized MHW track space"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        clear_export_analysis(scene_props)
        analysis = analyze_export_action(scene_props, actions=bpy.data.actions, objects=bpy.data.objects)
        _publish_export_diagnostics(scene_props, analysis.diagnostics)
        if analysis.action is None:
            scene_props.last_status = analysis.status_message
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        _apply_export_summary(scene_props, analysis)

        if analysis.error_count:
            scene_props.last_status = (
                f"Export analysis failed: {analysis.error_count} error(s), "
                f"{analysis.warning_count} warning(s)."
            )
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        scene_props.last_status = (
            f"Analyzed {analysis.sampling_result.action_name}: "
            f"tracks={analysis.sampling_result.sampled_track_count}, "
            f"planned={analysis.plan.supported_track_count}, "
            f"sparse_keys={analysis.reconstructed.sparse_key_count}, "
            f"skipped={analysis.sampling_result.skipped_track_count}, "
            f"warnings={analysis.warning_count}, "
            f"frames=0->{analysis.sampling_result.frame_end}, "
            f"entry={analysis.impact_summary.entry_id:03d}, "
            f"mode={analysis.impact_summary.export_mode}"
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_export_source_lmt(bpy.types.Operator, ExportHelper):
    bl_idname = "mhw_anim_tools.export_source_lmt"
    bl_label = "Export Full LMT"
    bl_description = "Write the full inspected LMT session, including deleted slots, holes, and added entries"

    filename_ext = ".lmt"
    filter_glob: bpy.props.StringProperty(default="*.lmt", options={"HIDDEN"}, maxlen=255)

    def invoke(self, context, _event):
        scene_props = context.scene.mhw_anim_tools
        source_path = str(scene_props.last_lmt_path or "")
        if not source_path or not getattr(scene_props, "lmt_entries", None):
            scene_props.last_status = "Inspect an LMT file before exporting the full source LMT."
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        if not self.filepath:
            source_name = Path(source_path).stem if source_path else getattr(effective_export_action(scene_props), "name", "export")
            self.filepath = _sanitize_export_name(source_name) + self.filename_ext
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        clear_export_analysis(scene_props)

        export_plan = analyze_lmt_session_export(
            scene_props,
            actions=bpy.data.actions,
            objects=bpy.data.objects,
        )
        _publish_export_diagnostics(scene_props, export_plan.diagnostics)
        for analysis in export_plan.analyses:
            _publish_export_diagnostics(scene_props, analysis.diagnostics)

        if export_plan.error_count:
            scene_props.last_status = export_plan.status_message or "Full LMT export could not start."
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        _apply_session_export_summary(scene_props, export_plan)

        try:
            output_path = write_lmt_session_export_file(self.filepath, export_plan)
        except (ValidationError, BinaryFormatError, OSError, ValueError) as exc:
            add_diagnostic(scene_props, "ERROR", "writer", str(exc))
            scene_props.last_export_warning_count = int(export_plan.warning_count)
            scene_props.last_export_error_count = int(export_plan.error_count) + 1
            scene_props.last_status = f"Full LMT export failed: {exc}"
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        scene_props.last_export_warning_count = int(export_plan.warning_count)
        scene_props.last_export_error_count = int(export_plan.error_count)
        scene_props.last_status = (
            f"Exported full source LMT {Path(export_plan.source_path).name or output_path.name}: "
            f"edited_actions={export_plan.edited_action_count}, "
            f"structural_changes={export_plan.structural_change_count}, "
            f"source_actions={export_plan.source_action_count}, "
            f"warnings={export_plan.warning_count}, "
            f"mode=merge"
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_save_timl_file(bpy.types.Operator, ExportHelper):
    bl_idname = "mhw_anim_tools.save_timl_file"
    bl_label = "Export TIML"
    bl_description = "Write the full standalone TIML file from the current imported TIML controller session"

    filename_ext = ".timl"
    filter_glob: bpy.props.StringProperty(default="*.timl", options={"HIDDEN"}, maxlen=255)

    @staticmethod
    def _missing_controller_message(scene_props) -> str:
        if str(getattr(scene_props, "last_timl_path", "") or ""):
            return "Import at least one standalone TIML entry before exporting."
        return "Choose an imported standalone TIML controller before exporting."

    def invoke(self, context, _event):
        scene_props = context.scene.mhw_anim_tools
        controller = _active_timl_controller(scene_props, context)
        if controller is None:
            scene_props.last_status = self._missing_controller_message(scene_props)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        metadata = extract_timl_controller_metadata(controller)
        if not self.filepath:
            source_path = str(metadata.source_lmt or "")
            if source_path.lower().endswith(".timl"):
                self.filepath = source_path
            else:
                self.filepath = _sanitize_export_name(controller.name) + self.filename_ext
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        controller = _active_timl_controller(scene_props, context)
        if controller is None:
            scene_props.last_status = self._missing_controller_message(scene_props)
            add_diagnostic(scene_props, "ERROR", "timl.export", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        analysis = analyze_standalone_timl_export(
            controller,
            controller_objects=bpy.data.objects,
        )
        _publish_standalone_timl_diagnostics(scene_props, analysis.diagnostics)
        if analysis.error_count:
            scene_props.last_status = (
                f"TIML export analysis failed: {analysis.error_count} error(s), "
                f"{analysis.warning_count} warning(s)."
            )
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        try:
            output_path = write_standalone_timl_file(self.filepath, analysis)
        except (ValidationError, BinaryFormatError, OSError, ValueError) as exc:
            add_diagnostic(scene_props, "ERROR", "timl.export", str(exc))
            scene_props.last_status = f"TIML export failed: {exc}"
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        scene_props.last_status = (
            f"Exported {output_path.name}: "
            f"edited_entries={analysis.sampled_entry_count}, "
            f"source_entries={analysis.source_entry_count}, "
            f"transforms={analysis.sampled_transform_count}, "
            f"warnings={analysis.warning_count}"
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}
classes = (
    MHWANIMTOOLS_OT_analyze_export_action,
    MHWANIMTOOLS_OT_export_source_lmt,
    MHWANIMTOOLS_OT_save_timl_file,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
