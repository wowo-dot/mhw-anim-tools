# -*- coding: utf-8 -*-
"""Focused export-prep operators for the rewrite."""

from pathlib import Path
import re

import bpy
from bpy_extras.io_utils import ExportHelper

from ..blender_adapter.export_sampling import sample_action_for_lmt_export
from ..blender_adapter.timl_export import assess_timl_export_readiness
from ..blender_adapter.timl_writeback import build_matching_timl_writeback
from ..blender_adapter.timl_writeback import matching_timl_controllers_for_export_action
from ..core.diagnostics.errors import BinaryFormatError
from ..core.diagnostics.errors import ValidationError
from ..core.diagnostics.reports import Report
from ..core.formats.lmt.decoder import decode_action_tracks
from ..core.formats.lmt.export_context import assess_standalone_export_context
from ..core.formats.lmt.export_context import build_source_action_export_context
from ..core.formats.lmt.export_context import LmtSourceActionExportContext
from ..core.formats.lmt.export_plan import plan_reconstructed_action_export
from ..core.formats.lmt.merge_writer import write_merged_lmt_file
from ..core.formats.lmt.quaternion_source_diagnostics import identify_raw_sensitive_quaternion_identities
from ..core.formats.lmt.reader import read_lmt_bytes
from ..core.formats.lmt.reconstruction import reconstruct_sampled_action
from ..core.formats.lmt.source_preservation import identify_preservable_decoded_track_identities
from ..core.formats.lmt.writer import DEFAULT_VERSION
from ..core.formats.lmt.writer import write_lmt_file
from .properties import add_diagnostic
from .properties import clear_diagnostics


def _effective_export_action(scene_props):
    if scene_props.export_action is not None:
        return scene_props.export_action
    target = scene_props.target_armature
    if target is None or target.animation_data is None:
        return None
    return target.animation_data.action


def _sanitize_export_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\\\|?*]+', "_", name or "export")
    cleaned = cleaned.strip(" ._")
    return cleaned or "export"


def _set_export_summary(scene_props, action, result, reconstructed, plan):
    combined_warning_count = result.warning_count + plan.warning_count
    combined_error_count = result.error_count + plan.error_count

    scene_props.export_action = action
    scene_props.last_export_action_name = result.action_name
    scene_props.last_export_track_count = result.sampled_track_count
    scene_props.last_export_sparse_key_count = reconstructed.sparse_key_count
    scene_props.last_export_supported_track_count = plan.supported_track_count
    scene_props.last_export_frame_count = result.frame_end
    scene_props.last_export_buffer_summary = plan.buffer_breakdown
    scene_props.last_export_warning_count = combined_warning_count
    scene_props.last_export_error_count = combined_error_count
    return combined_warning_count, combined_error_count


def _default_export_metadata():
    return {
        "version": DEFAULT_VERSION,
        "header_unknown": b"\x00" * 8,
        "action_id": 0,
        "loop_frame": -1,
        "flags": 0,
        "flags2": 0,
        "track_metadata_by_identity": None,
        "source_context": None,
        "source_lmt": None,
        "source_bytes": None,
        "export_mode": "standalone",
        "preserve_source_track_identities": frozenset(),
        "raw_quaternion_source_identities": frozenset(),
        "replacement_timl_payloads": {},
    }


def _fallback_source_context_from_action(action) -> LmtSourceActionExportContext | None:
    if action is None:
        return None
    if not any(str(key).startswith("mhw_anim_tools_source_") for key in action.keys()):
        return None
    try:
        action_id = int(action.get("mhw_anim_tools_entry_id", 0))
        version = int(action.get("mhw_anim_tools_source_version", DEFAULT_VERSION))
        entry_count = int(action.get("mhw_anim_tools_source_entry_count", 1))
        action_count = int(action.get("mhw_anim_tools_source_action_count", 1))
        has_timl = bool(action.get("mhw_anim_tools_source_has_timl", False))
        timl_offset = int(action.get("mhw_anim_tools_source_timl_offset", 0))
    except (TypeError, ValueError):
        return None
    return LmtSourceActionExportContext(
        source_name=str(action.get("mhw_anim_tools_source_lmt", "")),
        version=version,
        header_unknown=b"\x00" * 8,
        entry_count=entry_count,
        action_count=action_count,
        action_id=action_id,
        loop_frame=-1,
        null0=(0, 0, 0),
        translation=(0.0, 0.0, 0.0, 0.0),
        rotation_lerp=(0.0, 0.0, 0.0, 1.0),
        flags=0,
        null2=b"\x00\x00",
        flags2=0,
        null3=(0, 0, 0, 0, 0),
        has_timl=has_timl,
        timl_offset=timl_offset,
        track_metadata_by_identity={},
    )


def _analyze_for_export(scene_props):
    action = _effective_export_action(scene_props)
    readiness_report = assess_timl_export_readiness(action, bpy.data.actions) if action is not None else Report()
    for diagnostic in readiness_report.diagnostics:
        add_diagnostic(scene_props, diagnostic.level.upper(), diagnostic.code, diagnostic.message)
    if readiness_report.error_count:
        scene_props.last_status = "Selected action cannot be exported with the current TIML writer coverage."
        return None, None, None, None, None, readiness_report

    if scene_props.target_armature is None:
        message = "Choose a target armature before analyzing export data."
        add_diagnostic(scene_props, "ERROR", "armature", message)
        scene_props.last_status = message
        return None, None, None, None, None, readiness_report

    if action is None:
        message = "Choose a Blender Action before analyzing export data."
        add_diagnostic(scene_props, "ERROR", "action", message)
        scene_props.last_status = message
        return None, None, None, None, None, readiness_report

    result = sample_action_for_lmt_export(action, scene_props.target_armature)
    for diagnostic in result.diagnostics:
        add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)
    metadata, metadata_report = _resolve_source_action_export_metadata(scene_props, action)
    timl_matches = matching_timl_controllers_for_export_action(action, bpy.data.objects) if action is not None else ()
    if metadata["export_mode"] != "merge" and timl_matches:
        joined_names = ", ".join(getattr(item, "name", "") for item in timl_matches)
        message = (
            f"Found imported TIML controller(s) for this source entry ({joined_names}), "
            "but the current export is falling back to standalone mode and will ignore edited TIML data."
        )
        metadata_report.add_warning("lmt.export.timl", message)
    if metadata["source_lmt"] is not None:
        source_action = None
        for candidate in metadata["source_lmt"].actions:
            if int(candidate.id) == int(metadata["action_id"]):
                source_action = candidate
                break
        if source_action is not None:
            decoded_source_action = decode_action_tracks(source_action, strict=False)
            metadata["preserve_source_track_identities"] = identify_preservable_decoded_track_identities(
                decoded_source_action,
                result.sampled_tracks,
            )
            raw_sensitive_identities = identify_raw_sensitive_quaternion_identities(decoded_source_action)
            metadata["raw_quaternion_source_identities"] = raw_sensitive_identities
            if raw_sensitive_identities:
                preserved_raw_sensitive = raw_sensitive_identities & set(metadata["preserve_source_track_identities"])
                unpreserved_raw_sensitive = raw_sensitive_identities - set(metadata["preserve_source_track_identities"])
                if preserved_raw_sensitive and metadata["export_mode"] == "merge":
                    add_diagnostic(
                        scene_props,
                        "INFO",
                        "lmt.export.quaternion_source",
                        (
                            f"Merge export will preserve {len(preserved_raw_sensitive)} source quaternion lerp track(s) "
                            "whose raw non-unit key magnitudes matter for sparse structure."
                        ),
                    )
                if unpreserved_raw_sensitive:
                    add_diagnostic(
                        scene_props,
                        "WARNING",
                        "lmt.export.quaternion_source",
                        (
                            f"{len(unpreserved_raw_sensitive)} source quaternion lerp track(s) rely on raw non-unit key magnitudes; "
                            "motion-equivalent normalized rebuilds may use denser keys than the source track structure."
                        ),
                    )
        timl_writeback = build_matching_timl_writeback(
            action,
            bpy.data.objects,
            source_lmt=metadata["source_lmt"],
            source_bytes=metadata["source_bytes"],
        )
        metadata["replacement_timl_payloads"] = dict(timl_writeback.replacement_payloads)
        for diagnostic in timl_writeback.diagnostics:
            metadata_report.add(diagnostic.level.lower(), diagnostic.source, diagnostic.message)
    reconstructed = reconstruct_sampled_action(
        action_name=result.action_name,
        frame_start=result.frame_start,
        frame_end=result.frame_end,
        sampled_tracks=result.sampled_tracks,
        raw_quaternion_source_identities=metadata["raw_quaternion_source_identities"],
    )
    for diagnostic in metadata_report.diagnostics:
        add_diagnostic(scene_props, diagnostic.level.upper(), diagnostic.code, diagnostic.message)
    plan = plan_reconstructed_action_export(
        reconstructed,
        track_metadata_by_identity=metadata["track_metadata_by_identity"],
        preserve_source_identities=metadata["preserve_source_track_identities"],
        raw_quaternion_source_identities=metadata["raw_quaternion_source_identities"],
    )
    for diagnostic in plan.diagnostics:
        add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)
    metadata_report.diagnostics.extend(readiness_report.diagnostics)
    return action, result, reconstructed, plan, metadata, metadata_report


def _resolve_source_action_export_metadata(scene_props, action):
    metadata = _default_export_metadata()
    report = Report()
    source_path = ""
    entry_id = 0
    fallback_context = _fallback_source_context_from_action(action)
    if action is not None:
        source_path = str(action.get("mhw_anim_tools_source_lmt", ""))
        try:
            entry_id = int(action.get("mhw_anim_tools_entry_id", 0))
        except (TypeError, ValueError):
            report.add_warning(
                "lmt.export.source_entry",
                f"Action '{action.name}' has invalid source entry metadata; exporting with entry 0 defaults.",
            )
            entry_id = 0
    if not source_path and scene_props.last_lmt_path:
        source_path = scene_props.last_lmt_path
        if scene_props.lmt_entries and 0 <= scene_props.selected_entry_index < len(scene_props.lmt_entries):
            entry_id = int(scene_props.lmt_entries[scene_props.selected_entry_index].entry_id)

    if not source_path:
        if fallback_context is not None:
            report.add_warning(
                "lmt.export.source_path",
                "Source LMT path is unavailable; exporting with cached container metadata and default track metadata.",
            )
        fallback_report = assess_standalone_export_context(fallback_context)
        report.diagnostics.extend(fallback_report.diagnostics)
        if fallback_context is not None:
            metadata.update(
                {
                    "version": fallback_context.version,
                    "action_id": fallback_context.action_id,
                    "source_context": fallback_context,
                    "export_mode": "standalone",
                }
            )
        return metadata, report

    try:
        source_bytes = Path(source_path).read_bytes()
        lmt = read_lmt_bytes(source_bytes, source_name=source_path)
    except (OSError, ValueError, TypeError, BinaryFormatError) as exc:
        report.add_warning(
            "lmt.export.source_read",
            f"Could not reuse source LMT metadata from '{source_path}'; exporting with defaults instead ({exc}).",
        )
        fallback_report = assess_standalone_export_context(fallback_context)
        report.diagnostics.extend(fallback_report.diagnostics)
        if fallback_context is not None:
            metadata.update(
                {
                    "version": fallback_context.version,
                    "action_id": fallback_context.action_id,
                    "source_context": fallback_context,
                    "export_mode": "standalone",
                }
            )
        return metadata, report

    try:
        source_context = build_source_action_export_context(lmt, entry_id)
    except ValueError:
        report.add_warning(
            "lmt.export.source_entry",
            f"Could not find source LMT entry {entry_id} in '{source_path}'; exporting with default metadata.",
        )
        fallback_report = assess_standalone_export_context(fallback_context)
        report.diagnostics.extend(fallback_report.diagnostics)
        if fallback_context is not None:
            metadata.update(
                {
                    "version": fallback_context.version,
                    "action_id": fallback_context.action_id,
                    "source_context": fallback_context,
                    "export_mode": "standalone",
                }
            )
        return metadata, report

    metadata.update(
        {
            "version": source_context.version,
            "header_unknown": source_context.header_unknown,
            "action_id": source_context.action_id,
            "loop_frame": source_context.loop_frame,
            "flags": source_context.flags,
            "flags2": source_context.flags2,
            "track_metadata_by_identity": source_context.track_metadata_by_identity,
            "source_context": source_context,
            "source_lmt": lmt,
            "source_bytes": source_bytes,
            "export_mode": "merge",
        }
    )
    return metadata, report


class MHWANIMTOOLS_OT_analyze_export_action(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.analyze_export_action"
    bl_label = "Analyze Export Action"
    bl_description = "Sample the selected Blender Action back into normalized MHW track space"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        action, result, reconstructed, plan, metadata, metadata_report = _analyze_for_export(scene_props)
        if action is None:
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        combined_warning_count, combined_error_count = _set_export_summary(
            scene_props,
            action,
            result,
            reconstructed,
            plan,
        )
        combined_warning_count += metadata_report.warning_count
        scene_props.last_export_warning_count = combined_warning_count
        combined_error_count += metadata_report.error_count
        scene_props.last_export_error_count = combined_error_count

        if combined_error_count:
            scene_props.last_status = (
                f"Export analysis failed: {combined_error_count} error(s), "
                f"{combined_warning_count} warning(s)."
            )
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        scene_props.last_status = (
            f"Analyzed {result.action_name}: "
            f"tracks={result.sampled_track_count}, "
            f"planned={plan.supported_track_count}, "
            f"sparse_keys={reconstructed.sparse_key_count}, "
            f"skipped={result.skipped_track_count}, "
            f"warnings={combined_warning_count}, "
            f"frames=0->{result.frame_end}, "
            f"mode={metadata['export_mode']}"
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
        action = _effective_export_action(scene_props)
        if action is not None and not self.filepath:
            self.filepath = _sanitize_export_name(action.name) + self.filename_ext
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        action, result, reconstructed, plan, metadata, metadata_report = _analyze_for_export(scene_props)
        if action is None:
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        combined_warning_count, combined_error_count = _set_export_summary(
            scene_props,
            action,
            result,
            reconstructed,
            plan,
        )
        combined_warning_count += metadata_report.warning_count
        scene_props.last_export_warning_count = combined_warning_count
        combined_error_count += metadata_report.error_count
        scene_props.last_export_error_count = combined_error_count
        if combined_error_count:
            scene_props.last_status = (
                f"Export analysis failed: {combined_error_count} error(s), "
                f"{combined_warning_count} warning(s)."
            )
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        try:
            if metadata["source_lmt"] is not None and metadata["source_bytes"] is not None:
                output_path = write_merged_lmt_file(
                    self.filepath,
                    metadata["source_lmt"],
                    metadata["source_bytes"],
                    reconstructed,
                    action_id=metadata["action_id"],
                    version=metadata["version"],
                    header_unknown=metadata["header_unknown"],
                    track_metadata_by_identity=metadata["track_metadata_by_identity"],
                    preserve_source_identities=metadata["preserve_source_track_identities"],
                    raw_quaternion_source_identities=metadata["raw_quaternion_source_identities"],
                    replacement_timl_payloads=metadata["replacement_timl_payloads"],
                )
            else:
                output_path = write_lmt_file(
                    self.filepath,
                    reconstructed,
                    version=metadata["version"],
                    header_unknown=metadata["header_unknown"],
                    action_id=metadata["action_id"],
                    loop_frame=metadata["loop_frame"],
                    flags=metadata["flags"],
                    flags2=metadata["flags2"],
                    track_metadata_by_identity=metadata["track_metadata_by_identity"],
                    raw_quaternion_source_identities=metadata["raw_quaternion_source_identities"],
                )
        except (ValidationError, BinaryFormatError, OSError, ValueError) as exc:
            add_diagnostic(scene_props, "ERROR", "writer", str(exc))
            scene_props.last_export_error_count = combined_error_count + 1
            scene_props.last_status = f"Export failed: {exc}"
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        scene_props.last_status = (
            f"Exported {result.action_name} to {output_path.name}: "
            f"tracks={plan.supported_track_count}, "
            f"sparse_keys={reconstructed.sparse_key_count}, "
            f"warnings={combined_warning_count}, "
            f"mode={metadata['export_mode']}"
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


def _menu_export(self, _context):
    self.layout.operator(MHWANIMTOOLS_OT_export_lmt_action.bl_idname, text="MHW Anim Tools LMT (.lmt)")


classes = (
    MHWANIMTOOLS_OT_analyze_export_action,
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
