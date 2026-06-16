# -*- coding: utf-8 -*-
"""Focused export-prep operators for the rewrite."""

from pathlib import Path
import re

import bpy
from bpy_extras.io_utils import ExportHelper

from ..blender_adapter.export_workflow import analyze_export_action
from ..blender_adapter.export_workflow import analyze_source_export_actions
from ..blender_adapter.export_workflow import effective_export_action
from ..blender_adapter.export_workflow import source_export_actions
from ..blender_adapter.export_workflow import write_export_file
from ..blender_adapter.export_workflow import write_source_export_file
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


class MHWANIMTOOLS_OT_export_lmt_action(bpy.types.Operator, ExportHelper):
    bl_idname = "mhw_anim_tools.export_lmt_action"
    bl_label = "Export LMT Action"
    bl_description = "Write the selected Blender Action as a single-action LMT using the new core writer"

    filename_ext = ".lmt"
    filter_glob: bpy.props.StringProperty(default="*.lmt", options={"HIDDEN"}, maxlen=255)

    def invoke(self, context, _event):
        scene_props = context.scene.mhw_anim_tools
        action = effective_export_action(scene_props)
        if action is not None and not self.filepath:
            self.filepath = _sanitize_export_name(action.name) + self.filename_ext
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

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

        try:
            output_path = write_export_file(self.filepath, analysis)
        except (ValidationError, BinaryFormatError, OSError, ValueError) as exc:
            add_diagnostic(scene_props, "ERROR", "writer", str(exc))
            scene_props.last_export_error_count = analysis.error_count + 1
            scene_props.last_status = f"Export failed: {exc}"
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        scene_props.last_status = (
            f"Exported {analysis.sampling_result.action_name} to {output_path.name}: "
            f"tracks={analysis.plan.supported_track_count}, "
            f"sparse_keys={analysis.reconstructed.sparse_key_count}, "
            f"warnings={analysis.warning_count}, "
            f"entry={analysis.impact_summary.entry_id:03d}, "
            f"mode={analysis.impact_summary.export_mode}"
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_export_source_lmt(bpy.types.Operator, ExportHelper):
    bl_idname = "mhw_anim_tools.export_source_lmt"
    bl_label = "Export Source LMT"
    bl_description = "Write the full source LMT using every imported Blender action from that source file"

    filename_ext = ".lmt"
    filter_glob: bpy.props.StringProperty(default="*.lmt", options={"HIDDEN"}, maxlen=255)

    def invoke(self, context, _event):
        scene_props = context.scene.mhw_anim_tools
        source_path, _export_actions, report = source_export_actions(scene_props, actions=bpy.data.actions)
        if report.error_count:
            scene_props.last_status = report.diagnostics[0].message if report.diagnostics else "Full LMT export is not available for the current selection."
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

        source_path, analyses, report = analyze_source_export_actions(
            scene_props,
            actions=bpy.data.actions,
            objects=bpy.data.objects,
        )
        _publish_report_diagnostics(scene_props, report)
        for analysis in analyses:
            _publish_export_diagnostics(scene_props, analysis.diagnostics)

        if report.error_count or not analyses:
            scene_props.last_status = report.diagnostics[0].message if report.diagnostics else "Full LMT export could not start."
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        anchor_analysis = analyses[0]
        _apply_export_summary(scene_props, anchor_analysis)

        total_warning_count = report.warning_count + sum(int(analysis.warning_count) for analysis in analyses)
        total_error_count = report.error_count + sum(int(analysis.error_count) for analysis in analyses)
        if total_error_count:
            scene_props.last_export_warning_count = total_warning_count
            scene_props.last_export_error_count = total_error_count
            scene_props.last_status = (
                f"Full LMT export analysis failed: {total_error_count} error(s), "
                f"{total_warning_count} warning(s)."
            )
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        try:
            output_path = write_source_export_file(self.filepath, analyses)
        except (ValidationError, BinaryFormatError, OSError, ValueError) as exc:
            add_diagnostic(scene_props, "ERROR", "writer", str(exc))
            scene_props.last_export_warning_count = total_warning_count
            scene_props.last_export_error_count = total_error_count + 1
            scene_props.last_status = f"Full LMT export failed: {exc}"
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        scene_props.last_export_warning_count = total_warning_count
        scene_props.last_export_error_count = total_error_count
        scene_props.last_status = (
            f"Exported full source LMT {Path(source_path).name or output_path.name}: "
            f"edited_actions={len(analyses)}, "
            f"source_actions={anchor_analysis.impact_summary.source_action_count}, "
            f"warnings={total_warning_count}, "
            f"mode=merge"
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


def _menu_export(self, _context):
    self.layout.operator(MHWANIMTOOLS_OT_export_lmt_action.bl_idname, text="MHW Anim Tools LMT (.lmt)")


classes = (
    MHWANIMTOOLS_OT_analyze_export_action,
    MHWANIMTOOLS_OT_export_source_lmt,
    MHWANIMTOOLS_OT_export_lmt_action,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_export.append(_menu_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(_menu_export)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
