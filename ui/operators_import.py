# -*- coding: utf-8 -*-
"""Import and inspection operators."""

import json
import os
from pathlib import Path
from uuid import uuid4

import bpy
from bpy_extras.io_utils import ImportHelper

from ..blender_adapter.actions import import_lmt_action_to_armature
from ..blender_adapter.actions import import_empty_lmt_entry_to_armature
from ..blender_adapter.fcurves import assign_action
from ..blender_adapter.fcurves import ensure_armature_animation_data
from ..blender_adapter.import_batch import import_all_lmt_actions_to_armature
from ..blender_adapter.lmt_session import build_empty_entry_summary
from ..blender_adapter.lmt_session import build_file_summary
from ..blender_adapter.lmt_track_authoring import add_authored_track_to_action
from ..blender_adapter.lmt_track_authoring import remove_authored_track_from_action
from ..blender_adapter.lmt_track_authoring import session_lmt_action_for_entry
from ..blender_adapter.source_identity import source_file_identity_from_bytes
from ..blender_adapter.timl_actions import import_attached_timl_to_action
from ..blender_adapter.timl_actions import seed_empty_attached_timl_controller
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
from .properties import refresh_lmt_session_counts


def _selected_timl_file_entry(scene_props):
    items = scene_props.timl_file_entries
    index = int(scene_props.selected_timl_file_entry_index)
    if 0 <= index < len(items):
        return items[index]
    return None


def _selected_lmt_entry(scene_props):
    items = scene_props.lmt_entries
    index = int(scene_props.selected_entry_index)
    if 0 <= index < len(items):
        return items[index]
    return None


def _selected_lmt_track(scene_props):
    items = scene_props.lmt_tracks
    index = int(scene_props.selected_track_index)
    if 0 <= index < len(items):
        return items[index]
    return None


def _selected_entry_action(scene_props):
    entry = _selected_lmt_entry(scene_props)
    if entry is None:
        return None
    preferred = scene_props.export_action
    return session_lmt_action_for_entry(
        bpy.data.actions,
        source_path=str(scene_props.last_lmt_path or ""),
        entry_id=int(getattr(entry, "entry_id", 0)),
        preferred_action=preferred,
    )


def _copy_lmt_summary_to_entry(item, summary: dict[str, object]) -> None:
    item.entry_id = int(summary.get("entry_id", 0))
    item.entry_state = str(summary.get("entry_state", "source") or "source")
    item.has_source_action = bool(summary.get("has_source_action", False))
    item.is_synthetic = bool(summary.get("is_synthetic", False))
    item.frame_count = int(summary.get("frame_count", 0))
    item.loop_frame = int(summary.get("loop_frame", 0))
    item.track_count = int(summary.get("track_count", 0))
    item.has_timl = bool(summary.get("has_timl", False))
    item.flags = int(summary.get("flags", 0))
    item.flags2 = int(summary.get("flags2", 0))
    item.flags_hex = str(summary.get("flags_hex", ""))
    item.flags2_hex = str(summary.get("flags2_hex", ""))
    item.translation_preview = str(summary.get("translation_preview", ""))
    item.rotation_preview = str(summary.get("rotation_preview", ""))
    item.track_breakdown = str(summary.get("track_breakdown", ""))
    item.track_payload = str(summary.get("track_payload", ""))
    timl_source_offset = int(summary.get("timl_source_offset", 0) or 0)
    item.timl_source_offset_display = f"0x{timl_source_offset:X}" if timl_source_offset else ""
    item.timl_type_count = int(summary.get("timl_type_count", 0))
    item.timl_transform_count = int(summary.get("timl_transform_count", 0))
    item.timl_keyframe_count = int(summary.get("timl_keyframe_count", 0))
    item.timl_animation_length = float(summary.get("timl_animation_length", 0.0) or 0.0)
    item.timl_loop_start_point = float(summary.get("timl_loop_start_point", 0.0) or 0.0)
    item.timl_loop_control = int(summary.get("timl_loop_control", 0) or 0)
    item.timl_data_type_breakdown = str(summary.get("timl_data_type_breakdown", ""))
    item.timl_timeline_breakdown = str(summary.get("timl_timeline_breakdown", ""))
    item.timl_transform_payload = str(summary.get("timl_transform_payload", ""))
    item.timl_parse_error = str(summary.get("timl_parse_error", ""))


def _entry_state(entry) -> str:
    return str(getattr(entry, "entry_state", "") or "source")


LMT_TRACK_USAGE_ITEMS = (
    ("0", "Local Rotation", "Author a quaternion rotation track on a target bone"),
    ("1", "Local Translation", "Author a translation track on a target bone"),
    ("2", "Local Scale", "Author a scale track on a target bone"),
    ("3", "Root Rotation", "Author a root/action rotation track"),
    ("4", "Root Translation", "Author a root/action translation track"),
    ("5", "Root Scale", "Author a root/action scale track"),
)


def _seed_added_entry_timl_controller(scene_props, entry, *, target_armature=None, source_entry_count: int = 0):
    return seed_empty_attached_timl_controller(
        source_path=str(scene_props.last_lmt_path or ""),
        entry_id=int(getattr(entry, "entry_id", 0)),
        source_entry_count=int(source_entry_count),
        target_armature=target_armature,
        animation_length=float(getattr(entry, "timl_animation_length", 0.0) or 0.0),
        data_index_a=0,
        data_index_b=0,
        loop_start_point=float(getattr(entry, "timl_loop_start_point", 0.0) or 0.0),
        loop_control=int(getattr(entry, "timl_loop_control", 0) or 0),
        label_hash=0,
    )


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
            _copy_lmt_summary_to_entry(item, action_summary)
        scene_props.selected_entry_index = 0
        _populate_track_items(scene_props)
        _populate_timl_transform_items(scene_props)
        scene_props.last_lmt_path = self.filepath
        refresh_lmt_session_counts(scene_props)
        scene_props.last_warning_count = report.warning_count
        scene_props.last_error_count = report.error_count
        scene_props.last_status = (
            f"Parsed {os.path.basename(self.filepath)}: "
            f"entries={scene_props.last_entry_count}, actions={scene_props.last_action_count}, "
            f"tracks={scene_props.last_track_count}, warnings={report.warning_count}, "
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


class MHWANIMTOOLS_OT_add_lmt_entry(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.add_lmt_entry"
    bl_label = "Add LMT Entry"
    bl_description = "Append a blank LMT entry slot to the current session"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        if not scene_props.last_lmt_path:
            scene_props.last_status = "Inspect an LMT file before adding an entry."
            add_diagnostic(scene_props, "ERROR", "session", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        next_entry_id = max((int(entry.entry_id) for entry in scene_props.lmt_entries), default=-1) + 1
        summary = build_empty_entry_summary(next_entry_id, entry_state="added", is_synthetic=True, has_timl=True)
        item = scene_props.lmt_entries.add()
        _copy_lmt_summary_to_entry(item, summary)
        scene_props.selected_entry_index = len(scene_props.lmt_entries) - 1
        seed_result = _seed_added_entry_timl_controller(
            scene_props,
            item,
            target_armature=scene_props.target_armature,
            source_entry_count=int(getattr(scene_props, "last_entry_count", 0) or 0),
        )
        report_level = {"INFO"}
        for diagnostic in seed_result.diagnostics:
            add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)
        if seed_result.error_count:
            item.has_timl = False
            scene_props.last_status = (
                f"Added entry {next_entry_id:03d}, but the blank TIML controller could not be seeded."
            )
            report_level = {"WARNING"}
        else:
            scene_props.last_imported_timl_action_name = seed_result.action_name
            scene_props.last_imported_timl_object_name = seed_result.carrier_name
            scene_props.timl_controller = bpy.data.objects.get(seed_result.carrier_name)
            clear_timl_analysis(scene_props)
            scene_props.last_status = f"Added entry {next_entry_id:03d} with a blank attached TIML controller."
        refresh_lmt_session_counts(scene_props)
        _populate_track_items(scene_props)
        _populate_timl_transform_items(scene_props)
        self.report(report_level, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_delete_lmt_entry(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.delete_lmt_entry"
    bl_label = "Delete LMT Entry"
    bl_description = "Delete or clear the selected LMT entry slot from the current session export plan"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        entry = _selected_lmt_entry(scene_props)
        if entry is None:
            scene_props.last_status = "Choose an LMT entry first."
            add_diagnostic(scene_props, "ERROR", "session", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        entry_state = _entry_state(entry)
        if entry_state == "source_hole":
            scene_props.last_status = f"Entry {entry.entry_id:03d} is already an empty source slot."
            self.report({"INFO"}, scene_props.last_status)
            return {"CANCELLED"}

        if entry_state == "added":
            scene_props.lmt_entries.remove(int(scene_props.selected_entry_index))
            if scene_props.lmt_entries:
                scene_props.selected_entry_index = min(
                    int(scene_props.selected_entry_index),
                    len(scene_props.lmt_entries) - 1,
                )
            else:
                scene_props.selected_entry_index = 0
            refresh_lmt_session_counts(scene_props)
            _populate_track_items(scene_props)
            _populate_timl_transform_items(scene_props)
            scene_props.last_status = f"Removed added entry {entry.entry_id:03d}."
            self.report({"INFO"}, scene_props.last_status)
            return {"FINISHED"}

        summary = build_empty_entry_summary(int(entry.entry_id), entry_state="deleted", is_synthetic=True)
        _copy_lmt_summary_to_entry(entry, summary)
        refresh_lmt_session_counts(scene_props)
        _populate_track_items(scene_props)
        _populate_timl_transform_items(scene_props)
        scene_props.last_status = f"Marked entry {entry.entry_id:03d} deleted for export."
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_add_lmt_track(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.add_lmt_track"
    bl_label = "Add LMT Track"
    bl_description = "Add a new editable track to the imported Blender Action for the selected LMT entry"

    usage: bpy.props.EnumProperty(name="Track Usage", items=LMT_TRACK_USAGE_ITEMS, default="1")
    bone_id: bpy.props.IntProperty(name="Bone ID", default=0, min=0)

    def invoke(self, context, _event):
        scene_props = context.scene.mhw_anim_tools
        selected_track = _selected_lmt_track(scene_props)
        if selected_track is not None:
            self.usage = str(int(getattr(selected_track, "usage", 1)))
            if int(getattr(selected_track, "bone_id", -1)) >= 0:
                self.bone_id = int(getattr(selected_track, "bone_id", 0))
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "usage")
        if int(self.usage) < 3:
            layout.prop(self, "bone_id")
        else:
            layout.label(text="Root tracks write onto the armature/root motion target.", icon="INFO")

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        entry = _selected_lmt_entry(scene_props)
        if entry is None:
            scene_props.last_status = "Choose an LMT entry first."
            add_diagnostic(scene_props, "ERROR", "track", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        if scene_props.target_armature is None:
            scene_props.last_status = "Choose a target armature before adding a track."
            add_diagnostic(scene_props, "ERROR", "track", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        entry_state = _entry_state(entry)
        if entry_state in {"deleted", "source_hole"}:
            scene_props.last_status = f"Entry {entry.entry_id:03d} is not editable."
            add_diagnostic(scene_props, "ERROR", "track", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        action = _selected_entry_action(scene_props)
        if action is None and entry_state == "added":
            source_bytes, lmt = _try_load_lmt_for_ui(
                scene_props,
                scene_props.last_lmt_path,
                source="track",
                message="Could not read the current LMT session before creating a blank action.",
            )
            if source_bytes is None or lmt is None:
                self.report({"WARNING"}, scene_props.last_status)
                return {"CANCELLED"}
            source_identity = source_file_identity_from_bytes(source_bytes)
            result = import_empty_lmt_entry_to_armature(
                int(entry.entry_id),
                scene_props.target_armature,
                source_path=scene_props.last_lmt_path,
                source_version=int(lmt.header.version),
                source_entry_count=int(len(lmt.entry_offsets)),
                source_action_count=int(lmt.action_count),
                source_identity=source_identity,
            )
            for diagnostic in result.diagnostics:
                add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)
            if result.error_count:
                scene_props.last_status = "Could not create a blank action for this added entry."
                self.report({"WARNING"}, scene_props.last_status)
                return {"CANCELLED"}
            scene_props.last_imported_action_name = result.action_name
            scene_props.last_imported_action_count = 1 if result.action_name else 0
            scene_props.export_action = bpy.data.actions.get(result.action_name)
            action = scene_props.export_action

        if action is None:
            scene_props.last_status = (
                f"Import Selected first for entry {entry.entry_id:03d} before authoring track changes."
            )
            add_diagnostic(scene_props, "WARNING", "track", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        assign_action(ensure_armature_animation_data(scene_props.target_armature), action)
        scene_props.export_action = action

        usage = int(self.usage)
        bone_id = int(self.bone_id) if usage < 3 else -1
        try:
            created = add_authored_track_to_action(
                action,
                scene_props.target_armature,
                source_path=str(scene_props.last_lmt_path or ""),
                entry_id=int(entry.entry_id),
                bone_id=int(bone_id),
                usage=int(usage),
                source_track_payload=str(entry.track_payload or ""),
            )
        except ValueError as exc:
            scene_props.last_status = str(exc)
            add_diagnostic(scene_props, "ERROR", "track", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        _populate_track_items(scene_props)
        for index, item in enumerate(scene_props.lmt_tracks):
            if int(item.track_index) == int(created.get("track_index", -1)):
                scene_props.selected_track_index = index
                break

        scene_props.last_imported_action_name = getattr(action, "name", "")
        scene_props.last_imported_action_count = 1 if scene_props.last_imported_action_name else 0
        if str(created.get("import_mode", "") or "") == "raw_duplicate":
            scene_props.last_status = (
                f"Added raw fallback track T{int(created['track_index']):02d} for missing bone {bone_id:03d}."
            )
        else:
            scene_props.last_status = f"Added track T{int(created['track_index']):02d} to {action.name}."
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_remove_lmt_track(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.remove_lmt_track"
    bl_label = "Remove LMT Track"
    bl_description = "Remove the selected editable track from the imported Blender Action for this LMT entry"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        entry = _selected_lmt_entry(scene_props)
        track = _selected_lmt_track(scene_props)
        if entry is None or track is None:
            scene_props.last_status = "Choose a track first."
            add_diagnostic(scene_props, "ERROR", "track", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        if scene_props.target_armature is None:
            scene_props.last_status = "Choose a target armature before removing a track."
            add_diagnostic(scene_props, "ERROR", "track", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        action = _selected_entry_action(scene_props)
        if action is None:
            scene_props.last_status = "This entry does not have an imported editable action yet."
            add_diagnostic(scene_props, "ERROR", "track", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        previous_index = int(scene_props.selected_track_index)
        removal = remove_authored_track_from_action(
            action,
            scene_props.target_armature,
            track_spec={
                "track_index": int(track.track_index),
                "source_track_index": int(track.source_track_index),
                "bone_id": int(track.bone_id),
                "usage": int(track.usage),
                "data_path": str(track.data_path or ""),
                "channel_count": int(track.channel_count or 0),
            },
        )
        if int(removal.get("removed_fcurves", 0)) <= 0:
            scene_props.last_status = f"Track T{track.track_index:02d} could not be removed from {action.name}."
            add_diagnostic(scene_props, "WARNING", "track", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        _populate_track_items(scene_props)
        if scene_props.lmt_tracks:
            scene_props.selected_track_index = min(previous_index, len(scene_props.lmt_tracks) - 1)
        scene_props.export_action = action
        scene_props.last_imported_action_name = getattr(action, "name", "")
        scene_props.last_imported_action_count = 1 if scene_props.last_imported_action_name else 0
        scene_props.last_status = f"Removed track T{track.track_index:02d} from {action.name}."
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
        entry = _selected_lmt_entry(scene_props)
        if entry is None:
            scene_props.last_status = "Choose an LMT entry first."
            add_diagnostic(scene_props, "ERROR", "session", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        entry_state = _entry_state(entry)
        if entry_state == "deleted":
            scene_props.last_status = f"Entry {entry.entry_id:03d} is marked deleted for export."
            add_diagnostic(scene_props, "ERROR", "session", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        if entry_state == "source_hole":
            scene_props.last_status = f"Entry {entry.entry_id:03d} is an empty source slot."
            add_diagnostic(scene_props, "ERROR", "session", scene_props.last_status)
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
        if entry_state == "added":
            result = import_empty_lmt_entry_to_armature(
                int(entry.entry_id),
                scene_props.target_armature,
                source_path=scene_props.last_lmt_path,
                source_version=int(lmt.header.version),
                source_entry_count=int(len(lmt.entry_offsets)),
                source_action_count=int(lmt.action_count),
                source_identity=source_identity,
            )
        else:
            result = import_lmt_action_to_armature(
                lmt,
                int(entry.entry_id),
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
        _populate_track_items(scene_props)
        if result.frame_end:
            context.scene.frame_start = min(int(context.scene.frame_start), 0)
            context.scene.frame_end = max(int(context.scene.frame_end), result.frame_end)
        if entry_state == "added" and result.imported_track_count <= 0:
            scene_props.last_status = f"Created blank action {result.action_name} for entry {entry.entry_id:03d}."
        else:
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
        entry_ids = [
            int(entry.entry_id)
            for entry in scene_props.lmt_entries
            if _entry_state(entry) == "source" and bool(entry.has_source_action)
        ]
        result = import_all_lmt_actions_to_armature(
            lmt,
            scene_props.target_armature,
            source_path=scene_props.last_lmt_path,
            import_action=import_lmt_action_to_armature,
            entry_ids=entry_ids,
            source_identity=source_identity,
        )
        for diagnostic in result.diagnostics:
            add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)

        if result.imported_action_names:
            scene_props.last_imported_action_name = result.imported_action_names[-1]
            scene_props.last_imported_action_count = len(result.imported_action_names)
            scene_props.export_action = bpy.data.actions.get(scene_props.last_imported_action_name)
            _populate_track_items(scene_props)
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
        entry_state = _entry_state(entry)
        if entry_state == "added":
            result = _seed_added_entry_timl_controller(
                scene_props,
                entry,
                target_armature=scene_props.target_armature,
                source_entry_count=int(getattr(scene_props, "last_entry_count", 0) or 0),
            )
            for diagnostic in result.diagnostics:
                add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)
            if result.error_count:
                scene_props.last_status = (
                    f"Blank TIML seeding failed: {result.error_count} error(s), {result.warning_count} warning(s)."
                )
                self.report({"WARNING"}, scene_props.last_status)
                return {"CANCELLED"}
            entry.has_timl = True
            scene_props.last_imported_timl_action_name = result.action_name
            scene_props.last_imported_timl_object_name = result.carrier_name
            scene_props.timl_controller = bpy.data.objects.get(result.carrier_name)
            clear_timl_analysis(scene_props)
            scene_props.last_status = f"Seeded blank TIML controller {result.carrier_name} for entry {entry.entry_id:03d}."
            self.report({"INFO"}, scene_props.last_status)
            return {"FINISHED"}

        if entry_state != "source" or not bool(entry.has_source_action):
            scene_props.last_status = f"Entry {entry.entry_id:03d} does not have a source LMT action to read TIML from."
            add_diagnostic(scene_props, "ERROR", "timl", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
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
            int(entry.entry_id),
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
            entry_state = _entry_state(entry)
            if entry_state == "added":
                if not bool(entry.has_timl):
                    continue
                result = _seed_added_entry_timl_controller(
                    scene_props,
                    entry,
                    target_armature=scene_props.target_armature,
                    source_entry_count=int(getattr(scene_props, "last_entry_count", 0) or 0),
                )
                for diagnostic in result.diagnostics:
                    add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)
                warning_count += result.warning_count
                if result.error_count:
                    skipped_count += 1
                    continue
                imported_count += 1
                last_result = result
                continue
            if entry_state != "source" or not bool(entry.has_source_action):
                continue
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
                int(entry.entry_id),
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
            scene_props.last_status = "No TIML sessions were imported or seeded."
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        scene_props.last_status = (
            f"Imported or seeded {imported_count} TIML session(s); "
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
                and int(obj.get("mhw_anim_tools_timl_entry_id", -1)) == int(entry.entry_id)
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
    MHWANIMTOOLS_OT_add_lmt_entry,
    MHWANIMTOOLS_OT_delete_lmt_entry,
    MHWANIMTOOLS_OT_add_lmt_track,
    MHWANIMTOOLS_OT_remove_lmt_track,
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
