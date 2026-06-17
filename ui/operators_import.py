# -*- coding: utf-8 -*-
"""Import and inspection operators."""

import json
import os
from pathlib import Path
from uuid import uuid4

import bpy
from bpy_extras.io_utils import ImportHelper

from ..blender_adapter.actions import import_lmt_action_to_armature
from ..blender_adapter.import_batch import import_all_lmt_actions_to_armature
from ..blender_adapter.lmt_session import build_file_summary
from ..blender_adapter.source_identity import source_file_identity_from_bytes
from ..blender_adapter.timl_actions import import_attached_timl_to_action
from ..blender_adapter.timl_actions import import_standalone_timl_entries_to_actions
from ..core.diagnostics.errors import BinaryFormatError
from ..core.formats.lmt.reader import read_lmt_bytes
from ..core.formats.lmt.validation import validate_lmt
from ..core.formats.timl.reader import read_timl_bytes
from ..core.formats.timl.summary import build_file_summary as build_timl_file_summary
from ..core.formats.timl.validation import validate_timl
from .properties import add_diagnostic
from .properties import clear_export_analysis
from .properties import clear_diagnostics
from .properties import clear_timl_file_session
from .properties import _populate_track_items
from .properties import _populate_timl_transform_items
from .properties import clear_timl_analysis


def _selected_timl_file_entry(scene_props):
    items = scene_props.timl_file_entries
    index = int(scene_props.selected_timl_file_entry_index)
    if 0 <= index < len(items):
        return items[index]
    return None


def _read_lmt_source_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


def _load_lmt_from_path(path: str):
    source_bytes = _read_lmt_source_bytes(path)
    return source_bytes, read_lmt_bytes(source_bytes, source_name=path)


def _load_timl_from_path(path: str):
    source_bytes = Path(path).read_bytes()
    return source_bytes, read_timl_bytes(source_bytes, source_name=path)


def _report_file_read_failure(scene_props, *, source: str, message: str, exc: Exception):
    scene_props.last_status = message
    add_diagnostic(scene_props, "ERROR", source, f"{message} {exc}")


def _try_load_lmt_for_ui(scene_props, path: str, *, source: str, message: str):
    try:
        return _load_lmt_from_path(path)
    except (OSError, ValueError, TypeError, BinaryFormatError) as exc:
        _report_file_read_failure(scene_props, source=source, message=message, exc=exc)
        return None, None


def _try_load_timl_for_ui(scene_props, path: str, *, source: str, message: str):
    try:
        return _load_timl_from_path(path)
    except (OSError, ValueError, TypeError, BinaryFormatError) as exc:
        _report_file_read_failure(scene_props, source=source, message=message, exc=exc)
        return None, None


def _populate_timl_file_session(scene_props, timl, report) -> None:
    scene_props.timl_file_entries.clear()
    scene_props.selected_timl_file_entry_index = 0
    summary = build_timl_file_summary(timl)
    entries_by_id = {int(entry["entry_id"]): entry for entry in summary["entries"]}
    for entry_id in range(int(timl.header.entry_count)):
        item = scene_props.timl_file_entries.add()
        item.entry_id = int(entry_id)
        offset = int(timl.entry_offsets[entry_id]) if entry_id < len(timl.entry_offsets) else 0
        item.has_data = bool(offset)
        item.offset_display = f"0x{offset:X}" if offset else ""
        entry_summary = entries_by_id.get(int(entry_id))
        if entry_summary is None:
            continue
        item.type_count = int(entry_summary["type_count"])
        item.transform_count = int(entry_summary["transform_count"])
        item.keyframe_count = int(entry_summary["keyframe_count"])
        item.animation_length = float(entry_summary["animation_length"])
        item.loop_start_point = float(entry_summary["loop_start_point"])
        item.loop_control = int(entry_summary["loop_control"])
        item.data_index_a = int(entry_summary["data_index_a"])
        item.data_index_b = int(entry_summary["data_index_b"])
        item.label_hash_display = f"0x{int(entry_summary['label_hash']) & 0xFFFFFFFF:08X}"
        item.data_type_breakdown = ", ".join(
            f"{count} {label}" for label, count in dict(entry_summary["data_type_counts"]).items()
        )
        item.timeline_breakdown = ", ".join(
            f"{count} {label}" for label, count in dict(entry_summary["timeline_counts"]).items()
        )
        item.transform_payload = json.dumps(entry_summary["transform_payload"])

    scene_props.last_timl_entry_count = int(timl.header.entry_count)
    scene_props.last_timl_type_count = int(timl.type_count)
    scene_props.last_timl_transform_count = int(timl.transform_count)
    scene_props.last_timl_keyframe_count = int(timl.keyframe_count)
    scene_props.last_timl_warning_count = int(report.warning_count)
    scene_props.last_timl_error_count = int(report.error_count)


class MHWANIMTOOLS_OT_inspect_lmt(bpy.types.Operator, ImportHelper):
    bl_idname = "mhw_anim_tools.inspect_lmt"
    bl_label = "Inspect LMT"
    bl_description = "Parse an LMT and report high-level counts"

    filename_ext = ".lmt"
    filter_glob: bpy.props.StringProperty(default="*.lmt", options={"HIDDEN"}, maxlen=255)

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        source_bytes, lmt = _try_load_lmt_for_ui(
            scene_props,
            self.filepath,
            source="session",
            message=f"Could not inspect LMT '{os.path.basename(self.filepath)}'.",
        )
        if source_bytes is None or lmt is None:
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        report = validate_lmt(lmt)
        scene_props.lmt_entries.clear()
        scene_props.last_imported_action_name = ""
        scene_props.last_imported_action_count = 0
        scene_props.last_imported_timl_action_name = ""
        scene_props.last_imported_timl_object_name = ""
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


class MHWANIMTOOLS_OT_inspect_timl(bpy.types.Operator, ImportHelper):
    bl_idname = "mhw_anim_tools.inspect_timl"
    bl_label = "Inspect TIML"
    bl_description = "Parse a standalone TIML file and build a browsable session"

    filename_ext = ".timl"
    filter_glob: bpy.props.StringProperty(default="*.timl", options={"HIDDEN"}, maxlen=255)

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        clear_timl_analysis(scene_props)
        clear_timl_file_session(scene_props)
        scene_props.last_imported_timl_action_name = ""
        scene_props.last_imported_timl_object_name = ""

        source_bytes, timl = _try_load_timl_for_ui(
            scene_props,
            self.filepath,
            source="session",
            message=f"Could not inspect TIML '{os.path.basename(self.filepath)}'.",
        )
        if source_bytes is None or timl is None:
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        report = validate_timl(timl)
        _populate_timl_file_session(scene_props, timl, report)
        scene_props.last_timl_path = self.filepath
        scene_props.last_timl_session_id = uuid4().hex
        scene_props.last_status = (
            f"Parsed {os.path.basename(self.filepath)}: "
            f"entries={timl.header.entry_count}, types={timl.type_count}, "
            f"transforms={timl.transform_count}, keyframes={timl.keyframe_count}, "
            f"warnings={report.warning_count}, errors={report.error_count}"
        )
        if report.warning_count:
            add_diagnostic(scene_props, "WARNING", "validation", f"TIML validation reported {report.warning_count} warning(s).")
        if report.error_count:
            add_diagnostic(scene_props, "ERROR", "validation", f"TIML validation reported {report.error_count} error(s).")
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
        source_bytes, lmt = _try_load_lmt_for_ui(
            scene_props,
            scene_props.last_lmt_path,
            source="session",
            message="Could not read the current LMT session for import.",
        )
        if source_bytes is None or lmt is None:
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        source_identity = source_file_identity_from_bytes(source_bytes)
        result = import_lmt_action_to_armature(
            lmt,
            scene_props.selected_entry_index,
            scene_props.target_armature,
            source_path=scene_props.last_lmt_path,
            source_identity=source_identity,
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
        scene_props.last_imported_action_count = 1 if result.action_name else 0
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


class MHWANIMTOOLS_OT_import_all_lmt_actions(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.import_all_lmt_actions"
    bl_label = "Import All Actions"
    bl_description = "Create Blender Actions on the selected target armature from every LMT entry in the current source file"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        if not scene_props.last_lmt_path:
            scene_props.last_status = "Inspect an LMT file before importing all actions."
            add_diagnostic(scene_props, "ERROR", "session", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        if scene_props.target_armature is None:
            scene_props.last_status = "Choose a target armature before importing all actions."
            add_diagnostic(scene_props, "ERROR", "armature", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        source_bytes, lmt = _try_load_lmt_for_ui(
            scene_props,
            scene_props.last_lmt_path,
            source="session",
            message="Could not read the current LMT session for batch import.",
        )
        if source_bytes is None or lmt is None:
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        source_identity = source_file_identity_from_bytes(source_bytes)
        result = import_all_lmt_actions_to_armature(
            lmt,
            scene_props.target_armature,
            source_path=scene_props.last_lmt_path,
            import_action=import_lmt_action_to_armature,
            source_identity=source_identity,
        )
        for diagnostic in result.diagnostics:
            add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)

        if result.imported_action_names:
            scene_props.last_imported_action_name = result.imported_action_names[-1]
            scene_props.last_imported_action_count = len(result.imported_action_names)
            scene_props.export_action = bpy.data.actions.get(scene_props.last_imported_action_name)
        else:
            scene_props.last_imported_action_name = ""
            scene_props.last_imported_action_count = 0

        if result.frame_end:
            context.scene.frame_start = min(int(context.scene.frame_start), 0)
            context.scene.frame_end = max(int(context.scene.frame_end), result.frame_end)

        if result.imported_action_count == 0:
            scene_props.last_status = (
                "Batch import failed: "
                f"{result.failed_action_count} action(s) failed, "
                f"{result.warning_count} warning(s)."
            )
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        scene_props.last_status = (
            f"Imported {result.imported_action_count}/{result.requested_action_count} LMT actions: "
            f"tracks={result.imported_track_count}, "
            f"failed={result.failed_action_count}, "
            f"warnings={result.warning_count}"
        )
        if result.failed_action_count or result.warning_count:
            self.report({"WARNING"}, scene_props.last_status)
        else:
            self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_import_selected_attached_timl(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.import_selected_attached_timl"
    bl_label = "Import Attached TIML"
    bl_description = "Create a Blender Action on a dedicated TIML controller object from the attached TIML payload"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        scene_props.last_imported_timl_action_name = ""
        scene_props.last_imported_timl_object_name = ""
        if not scene_props.last_lmt_path:
            scene_props.last_status = "Inspect an LMT file before importing attached TIML."
            add_diagnostic(scene_props, "ERROR", "session", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        if not scene_props.lmt_entries:
            scene_props.last_status = "No LMT entries are loaded in the current session."
            add_diagnostic(scene_props, "ERROR", "session", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        entry = scene_props.lmt_entries[min(scene_props.selected_entry_index, len(scene_props.lmt_entries) - 1)]
        if not entry.has_timl:
            scene_props.last_status = f"Entry {entry.entry_id:03d} does not contain an attached TIML payload."
            add_diagnostic(scene_props, "ERROR", "timl", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        if entry.timl_parse_error:
            scene_props.last_status = f"Entry {entry.entry_id:03d} attached TIML could not be parsed."
            add_diagnostic(scene_props, "ERROR", "timl", f"{scene_props.last_status} {entry.timl_parse_error}")
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        source_bytes, lmt = _try_load_lmt_for_ui(
            scene_props,
            scene_props.last_lmt_path,
            source="timl",
            message="Could not read the current LMT session for attached TIML import.",
        )
        if source_bytes is None or lmt is None:
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        result = import_attached_timl_to_action(
            lmt,
            scene_props.selected_entry_index,
            source_path=scene_props.last_lmt_path,
            source_bytes=source_bytes,
            target_armature=scene_props.target_armature,
        )
        for diagnostic in result.diagnostics:
            add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)
        if result.error_count:
            scene_props.last_status = (
                f"TIML import failed: {result.error_count} error(s), {result.warning_count} warning(s)."
            )
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        scene_props.last_imported_timl_action_name = result.action_name
        scene_props.last_imported_timl_object_name = result.carrier_name
        scene_props.timl_controller = bpy.data.objects.get(result.carrier_name)
        clear_timl_analysis(scene_props)
        if result.frame_end:
            context.scene.frame_start = min(int(context.scene.frame_start), 0)
            context.scene.frame_end = max(int(context.scene.frame_end), result.frame_end)
        scene_props.last_status = (
            f"Imported {result.action_name} on {result.carrier_name}: "
            f"transforms={result.imported_transform_count}, "
            f"skipped={result.skipped_transform_count}, "
            f"warnings={result.warning_count}"
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_import_all_attached_timl(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.import_all_attached_timl"
    bl_label = "Import All TIML"
    bl_description = "Import every attached TIML payload from the current LMT session"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        scene_props.last_imported_timl_action_name = ""
        scene_props.last_imported_timl_object_name = ""
        if not scene_props.last_lmt_path:
            scene_props.last_status = "Inspect an LMT file before importing attached TIML."
            add_diagnostic(scene_props, "ERROR", "session", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        if not scene_props.lmt_entries:
            scene_props.last_status = "No LMT entries are loaded in the current session."
            add_diagnostic(scene_props, "ERROR", "session", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        source_bytes, lmt = _try_load_lmt_for_ui(
            scene_props,
            scene_props.last_lmt_path,
            source="timl",
            message="Could not read the current LMT session for batch TIML import.",
        )
        if source_bytes is None or lmt is None:
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        imported_count = 0
        skipped_count = 0
        warning_count = 0
        frame_end = 0
        last_result = None

        for entry_index, entry in enumerate(scene_props.lmt_entries):
            if not entry.has_timl:
                continue
            if entry.timl_parse_error:
                skipped_count += 1
                add_diagnostic(
                    scene_props,
                    "WARNING",
                    "timl",
                    f"Entry {entry.entry_id:03d} attached TIML could not be parsed: {entry.timl_parse_error}",
                )
                continue
            result = import_attached_timl_to_action(
                lmt,
                entry_index,
                source_path=scene_props.last_lmt_path,
                source_bytes=source_bytes,
                target_armature=scene_props.target_armature,
            )
            for diagnostic in result.diagnostics:
                add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)
            warning_count += result.warning_count
            if result.error_count:
                skipped_count += 1
                continue
            imported_count += 1
            frame_end = max(frame_end, int(result.frame_end))
            last_result = result

        if frame_end:
            context.scene.frame_start = min(int(context.scene.frame_start), 0)
            context.scene.frame_end = max(int(context.scene.frame_end), frame_end)

        if last_result is not None:
            scene_props.last_imported_timl_action_name = last_result.action_name
            scene_props.last_imported_timl_object_name = last_result.carrier_name
            scene_props.timl_controller = bpy.data.objects.get(last_result.carrier_name)
            clear_timl_analysis(scene_props)

        if imported_count <= 0:
            scene_props.last_status = "No attached TIML payloads were imported."
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        scene_props.last_status = (
            f"Imported {imported_count} attached TIML payload(s); "
            f"skipped={skipped_count}, warnings={warning_count}"
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_import_selected_timl_entry(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.import_selected_timl_entry"
    bl_label = "Import Selected TIML Entry"
    bl_description = "Import the selected standalone TIML entry into the TIML workspace"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        scene_props.last_imported_timl_action_name = ""
        scene_props.last_imported_timl_object_name = ""
        if not scene_props.last_timl_path:
            scene_props.last_status = "Inspect a TIML file before importing an entry."
            add_diagnostic(scene_props, "ERROR", "session", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        entry = _selected_timl_file_entry(scene_props)
        if entry is None:
            scene_props.last_status = "Choose a TIML entry first."
            add_diagnostic(scene_props, "ERROR", "timl", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        if not entry.has_data:
            scene_props.last_status = f"TIML entry {int(entry.entry_id):03d} is empty."
            add_diagnostic(scene_props, "ERROR", "timl", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        try:
            result = import_standalone_timl_entries_to_actions(
                scene_props.last_timl_path,
                entry_ids=(int(entry.entry_id),),
                session_id=str(scene_props.last_timl_session_id or ""),
                target_armature=scene_props.target_armature,
            )
        except Exception as exc:
            scene_props.last_status = f"TIML import failed: {exc}"
            add_diagnostic(scene_props, "ERROR", "timl", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        for diagnostic in result.diagnostics:
            add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)

        if result.error_count or result.imported_entry_count <= 0:
            scene_props.last_status = (
                f"TIML import failed: {result.error_count} error(s), "
                f"{result.warning_count} warning(s)."
            )
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        scene_props.last_imported_timl_action_name = result.last_action_name
        scene_props.last_imported_timl_object_name = result.last_carrier_name
        scene_props.timl_controller = bpy.data.objects.get(result.last_carrier_name)
        clear_timl_analysis(scene_props)
        if result.frame_end:
            context.scene.frame_start = min(int(context.scene.frame_start), 0)
            context.scene.frame_end = max(int(context.scene.frame_end), int(result.frame_end))

        if scene_props.timl_controller is not None:
            try:
                bpy.ops.mhw_anim_tools.open_timl_workspace()
            except RuntimeError:
                pass

        scene_props.last_status = (
            f"Imported TIML entry {int(entry.entry_id):03d}: "
            f"transforms={result.imported_transform_count}, "
            f"warnings={result.warning_count}"
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_import_all_timl_entries(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.import_all_timl_entries"
    bl_label = "Import All TIML Entries"
    bl_description = "Import every non-empty entry from the inspected standalone TIML file"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        scene_props.last_imported_timl_action_name = ""
        scene_props.last_imported_timl_object_name = ""
        if not scene_props.last_timl_path:
            scene_props.last_status = "Inspect a TIML file before importing entries."
            add_diagnostic(scene_props, "ERROR", "session", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        try:
            result = import_standalone_timl_entries_to_actions(
                scene_props.last_timl_path,
                entry_ids=None,
                session_id=str(scene_props.last_timl_session_id or ""),
                target_armature=scene_props.target_armature,
            )
        except Exception as exc:
            scene_props.last_status = f"TIML import failed: {exc}"
            add_diagnostic(scene_props, "ERROR", "timl", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        for diagnostic in result.diagnostics:
            add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)
        if result.error_count or result.imported_entry_count <= 0:
            scene_props.last_status = (
                f"TIML import failed: {result.error_count} error(s), "
                f"{result.warning_count} warning(s)."
            )
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        scene_props.last_imported_timl_action_name = result.last_action_name
        scene_props.last_imported_timl_object_name = result.last_carrier_name
        scene_props.timl_controller = bpy.data.objects.get(result.last_carrier_name)
        clear_timl_analysis(scene_props)
        if result.frame_end:
            context.scene.frame_start = min(int(context.scene.frame_start), 0)
            context.scene.frame_end = max(int(context.scene.frame_end), int(result.frame_end))
        scene_props.last_status = (
            f"Imported {result.imported_entry_count} TIML entr{'y' if result.imported_entry_count == 1 else 'ies'}: "
            f"transforms={result.imported_transform_count}, warnings={result.warning_count}"
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_focus_selected_timl_entry_controller(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.focus_selected_timl_entry_controller"
    bl_label = "Focus TIML Entry Controller"
    bl_description = "Focus the imported TIML controller for the selected standalone TIML entry"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        entry = _selected_timl_file_entry(scene_props)
        if entry is None:
            scene_props.last_status = "Choose a TIML entry first."
            add_diagnostic(scene_props, "WARNING", "timl.controller", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        if not scene_props.last_timl_path:
            scene_props.last_status = "Inspect a TIML file first."
            add_diagnostic(scene_props, "WARNING", "timl.controller", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        controller = next(
            (
                obj for obj in bpy.data.objects
                if bool(obj)
                and str(obj.get("mhw_anim_tools_timl_source_lmt", "") or "") == str(scene_props.last_timl_path or "")
                and str(obj.get("mhw_anim_tools_timl_session_id", "") or "") == str(scene_props.last_timl_session_id or "")
                and int(obj.get("mhw_anim_tools_timl_entry_id", -1) or -1) == int(entry.entry_id)
            ),
            None,
        )
        if controller is None:
            scene_props.last_status = f"TIML entry {int(entry.entry_id):03d} has not been imported yet."
            add_diagnostic(scene_props, "WARNING", "timl.controller", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        scene_props.timl_controller = controller
        if context.mode == "OBJECT":
            for candidate in context.selected_objects:
                candidate.select_set(False)
            controller.select_set(True)
            context.view_layer.objects.active = controller
        if scene_props.last_timl_analysis_controller_name != controller.name:
            try:
                bpy.ops.mhw_anim_tools.analyze_timl_controller()
            except RuntimeError:
                pass
        scene_props.last_status = f"Focused {controller.name}."
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
        scene_props.last_imported_action_count = 0
        scene_props.last_imported_timl_action_name = ""
        scene_props.last_imported_timl_object_name = ""
        clear_timl_analysis(scene_props)
        scene_props.export_action = None
        clear_export_analysis(scene_props)
        scene_props.last_status = "Cleared LMT session."
        return {"FINISHED"}


class MHWANIMTOOLS_OT_clear_timl_session(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.clear_timl_session"
    bl_label = "Clear TIML Session"
    bl_description = "Clear the currently loaded standalone TIML session summary"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        clear_timl_file_session(scene_props)
        scene_props.last_imported_timl_action_name = ""
        scene_props.last_imported_timl_object_name = ""
        clear_timl_analysis(scene_props)
        scene_props.last_status = "Cleared TIML session."
        return {"FINISHED"}


classes = (
    MHWANIMTOOLS_OT_inspect_lmt,
    MHWANIMTOOLS_OT_inspect_timl,
    MHWANIMTOOLS_OT_import_selected_lmt_action,
    MHWANIMTOOLS_OT_import_all_lmt_actions,
    MHWANIMTOOLS_OT_import_selected_attached_timl,
    MHWANIMTOOLS_OT_import_all_attached_timl,
    MHWANIMTOOLS_OT_import_selected_timl_entry,
    MHWANIMTOOLS_OT_import_all_timl_entries,
    MHWANIMTOOLS_OT_focus_selected_timl_entry_controller,
    MHWANIMTOOLS_OT_clear_lmt_session,
    MHWANIMTOOLS_OT_clear_timl_session,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
