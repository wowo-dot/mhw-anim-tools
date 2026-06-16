# -*- coding: utf-8 -*-
"""Section drawing helpers for the Blender UI surfaces."""

import json
import os

import bpy

from ..blender_adapter.armature import summarize_track_binding
from ..blender_adapter.space import uses_mhw_model_editor_space_adapter
from ..blender_adapter.timl_sampling import extract_timl_controller_metadata
from ..blender_adapter.timl_sampling import is_imported_timl_controller
from ..integration.model_editor import bonefunction_count
from ..integration.model_editor import get_workspace_summary
from ..integration.model_editor import mhbone_count
from .timl_presenter import build_timl_analysis_summary
from .timl_presenter import build_timl_edit_policy_summary
from .timl_presenter import build_timl_source_summary
from .timl_presenter import build_timl_writeback_summary
from .timl_presenter import timl_display_source_name
from .timl_labels import timl_edit_policy_icon
from .timl_labels import timl_writeback_status_icon
from .addon_preferences import draw_update_notice_box


def timl_controller_for_object_panel(context):
    active_object = getattr(context, "active_object", None)
    if is_imported_timl_controller(active_object):
        return active_object
    controller = context.scene.mhw_anim_tools.timl_controller
    if is_imported_timl_controller(controller) and active_object == controller:
        return controller
    return None


def _workspace_timl_controller(context):
    scene_props = context.scene.mhw_anim_tools
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
    return None


def _display_source_name(path_text: str) -> str:
    return timl_display_source_name(path_text)


def _draw_timl_writeback_counts(layout, scene_props):
    counts_box = layout.box()
    counts_box.label(text="Writeback Modes", icon="FILE_REFRESH")
    counts_box.label(
        text=build_timl_writeback_summary(
            preserve_raw_count=scene_props.last_timl_writeback_preserve_raw_count,
            patch_values_count=scene_props.last_timl_writeback_patch_values_count,
            rebuild_count=scene_props.last_timl_writeback_rebuild_count,
            blocked_count=scene_props.last_timl_writeback_blocked_count,
        )
    )


def _draw_timl_edit_policy_counts(layout, scene_props):
    counts_box = layout.box()
    counts_box.label(text="Edit Policies", icon="KEYFRAME")
    counts_box.label(
        text=build_timl_edit_policy_summary(
            value_only_count=scene_props.last_timl_edit_value_only_count,
            rebuild_capable_count=scene_props.last_timl_edit_rebuild_capable_count,
            blocked_count=scene_props.last_timl_edit_blocked_count,
        )
    )


def _draw_timl_payload_scope(layout, scene_props):
    if not scene_props.last_timl_payload_scope:
        return
    scope_box = layout.box()
    scope_box.label(text="Payload Scope", icon="LINKED")
    scope_box.label(text=scene_props.last_timl_payload_scope)


def _timl_shared_controller_status_label(status: str) -> str:
    labels = {
        "single": "Single Imported Controller",
        "consistent": "Controllers Consistent",
        "conflict": "Controller Conflict",
    }
    return labels.get(str(status or ""), "")


def _draw_timl_shared_controller_summary(layout, scene_props):
    if not scene_props.last_timl_matching_controller_count:
        return
    summary_box = layout.box()
    summary_box.label(text="Shared Controller State", icon="OUTLINER_OB_EMPTY")
    summary_box.label(text=f"Matching controllers: {scene_props.last_timl_matching_controller_count}")
    status_label = _timl_shared_controller_status_label(scene_props.last_timl_shared_controller_status)
    if status_label:
        summary_box.label(text=f"Status: {status_label}")
    if scene_props.last_timl_matching_controller_names:
        summary_box.label(text=scene_props.last_timl_matching_controller_names)


def _draw_workspace_header(layout, scene_props):
    header_box = layout.box()
    header_box.label(text="Session Browser", icon="ANIM_DATA")
    header_box.label(text=scene_props.last_status)
    actions = header_box.row(align=True)
    actions.scale_y = 1.05
    actions.operator("mhw_anim_tools.open_timl_workspace", icon="WORKSPACE", text="Open TIML Workspace")


def _draw_workspace_section(layout, context, scene_props):
    summary = get_workspace_summary(context, scene_props.target_armature)
    panel_header, panel_body = layout.panel(
        idname="MHWANIMTOOLS_PT_workspace_section",
        default_closed=False,
    )
    panel_header.label(text="Workspace")
    if panel_body is None:
        return
    addon_status = summary["addon_status"]
    if addon_status["enabled"]:
        panel_body.label(text="MHW_Model_Editor active", icon="CHECKMARK")
    elif addon_status["available"]:
        panel_body.label(text="MHW_Model_Editor installed but disabled", icon="INFO")
    else:
        panel_body.label(text="Standalone mode", icon="INFO")
    panel_body.prop(scene_props, "target_armature")
    button_row = panel_body.row(align=True)
    button_row.scale_y = 1.1
    button_row.operator("mhw_anim_tools.use_active_armature", icon="EYEDROPPER")
    button_row.operator("mhw_anim_tools.auto_detect_armature", icon="ARMATURE_DATA")
    refresh_row = panel_body.row(align=True)
    refresh_row.scale_y = 1.1
    refresh_row.operator("mhw_anim_tools.refresh_workspace", icon="FILE_REFRESH")
    details_header, details_body = panel_body.panel(
        idname="MHWANIMTOOLS_PT_workspace_details",
        default_closed=True,
    )
    details_header.label(text="Armature Details")
    if details_body is None:
        return
    details_body.label(text=f"Candidate armatures: {summary['candidate_count']}")
    target = summary["target_armature"]
    if target is not None:
        details_body.label(text=f"Target MhBones: {mhbone_count(target)}")
        details_body.label(text=f"Target BoneFunctions: {bonefunction_count(target)}")
        if uses_mhw_model_editor_space_adapter(target):
            details_body.label(text="Target space: MHW MOD3 adapter", icon="ORIENTATION_GLOBAL")
        else:
            details_body.label(text="Target space: direct / generic", icon="INFO")
    else:
        details_body.label(text="No target armature selected", icon="ERROR")


def _draw_entry_binding_summary(details, scene_props, entry):
    details.label(text=entry.track_breakdown or "No track breakdown")
    target = scene_props.target_armature
    if target is None or not entry.track_payload:
        return
    try:
        binding_summary = summarize_track_binding(target, json.loads(entry.track_payload))
    except json.JSONDecodeError:
        binding_summary = None
    if binding_summary is None:
        return
    binding_box = details.box()
    binding_box.label(text="Target Binding", icon="ARMATURE_DATA")
    binding_box.label(
        text=(
            f"Resolvable tracks: {binding_summary.resolved_track_count}/"
            f"{binding_summary.supported_track_count}"
        )
    )
    if binding_summary.root_required:
        root_text = binding_summary.root_target_label or "missing"
        binding_box.label(text=f"Root binding: {root_text}")
    if binding_summary.unresolved_track_count:
        missing = ", ".join(f"{bone_id:03d}" for bone_id in binding_summary.missing_bone_ids[:8])
        suffix = " ..." if len(binding_summary.missing_bone_ids) > 8 else ""
        binding_box.label(
            text=f"Missing bone ids: {missing}{suffix}",
            icon="ERROR",
        )


def _draw_entry_import_section(panel_body, scene_props, entry):
    import_row = panel_body.row(align=True)
    import_row.scale_y = 1.1
    import_row.operator("mhw_anim_tools.import_selected_lmt_action", icon="ACTION", text="Import Selected")
    import_row.operator("mhw_anim_tools.import_all_lmt_actions", icon="ACTION_TWEAK", text="Import All")
    if entry.has_timl:
        timl_row = panel_body.row(align=True)
        timl_row.scale_y = 1.05
        timl_row.operator("mhw_anim_tools.import_selected_attached_timl", icon="IMPORT", text="Import TIML")
        timl_row.operator("mhw_anim_tools.focus_selected_entry_timl_controller", icon="RESTRICT_SELECT_OFF", text="Focus TIML")
        if entry.timl_parse_error:
            panel_body.label(text=f"TIML parse issue: {entry.timl_parse_error}", icon="ERROR")
    if not scene_props.last_imported_action_name:
        return
    if scene_props.last_imported_action_count > 1:
        panel_body.label(
            text=(
                f"Last batch: {scene_props.last_imported_action_count} actions "
                f"(active: {scene_props.last_imported_action_name})"
            )
        )
        return
    panel_body.label(text=f"Last imported: {scene_props.last_imported_action_name}")


def _draw_track_details(panel_body, scene_props):
    panel_body.template_list(
        "MHWANIMTOOLS_UL_lmt_tracks",
        "",
        scene_props,
        "lmt_tracks",
        scene_props,
        "selected_track_index",
        rows=8,
    )
    if not (0 <= scene_props.selected_track_index < len(scene_props.lmt_tracks)):
        return
    track = scene_props.lmt_tracks[scene_props.selected_track_index]
    track_box = panel_body.box()
    track_box.label(text=f"Track {track.track_index:02d}", icon="IPO_BEZIER")
    track_box.label(text=f"Usage: {track.usage_label}")
    track_box.label(text=f"Bone ID: {track.bone_id}")
    track_box.label(text=f"Blender target hint: {track.blender_path_hint or 'n/a'}")
    track_box.label(text=f"Channels: {track.channel_labels}")
    track_box.label(text=f"Encoding: {track.buffer_label} ({track.buffer_code})")
    track_box.label(text=f"Buffer size: {track.buffer_size} bytes @ {track.buffer_offset_display}")
    raw_key_text = "unknown" if track.raw_key_count < 0 else str(track.raw_key_count)
    track_box.label(text=f"Raw key count: {raw_key_text}")
    track_box.label(text=f"Decoded key count: {track.decoded_key_count}")
    if track.first_keyframe >= 0:
        track_box.label(text=f"Decoded frame span: {track.first_keyframe} -> {track.last_keyframe}")
    if track.tail_frame >= 0:
        track_box.label(text=f"Tail frame: {track.tail_frame}")
    track_box.label(text="Has lerp basis" if track.has_lerp else "No lerp basis")
    track_box.label(text=f"Basis: {track.basis_preview}")
    if track.tail_preview:
        track_box.label(text=f"Tail: {track.tail_preview}")
    track_box.label(text=f"Weight: {track.weight:.3f}")
    track_box.label(text=f"Joint type: {track.joint_type} / Tag: {track.unknown_tag}")
    if track.decode_error:
        track_box.label(text=f"Decode issue: {track.decode_error}", icon="ERROR")


def _draw_lmt_inspector_section(layout, scene_props):
    panel_header, panel_body = layout.panel(
        idname="MHWANIMTOOLS_PT_lmt_inspector_section",
        default_closed=False,
    )
    panel_header.label(text="LMT Inspector")
    if panel_body is None:
        return
    row = panel_body.row(align=True)
    row.scale_y = 1.1
    row.operator("mhw_anim_tools.inspect_lmt", icon="IMPORT")
    row.operator("mhw_anim_tools.clear_lmt_session", icon="TRASH", text="")
    if not scene_props.last_lmt_path:
        panel_body.label(text="No LMT session loaded yet.", icon="INFO")
        return

    stats_box = panel_body.box()
    stats_box.label(text=os.path.basename(scene_props.last_lmt_path), icon="CURRENT_FILE")
    stats_box.label(text=f"Entries: {scene_props.last_entry_count}")
    stats_box.label(text=f"Actions: {scene_props.last_action_count}")
    stats_box.label(text=f"Tracks: {scene_props.last_track_count}")
    stats_box.label(text=f"Warnings: {scene_props.last_warning_count}")
    stats_box.label(text=f"Errors: {scene_props.last_error_count}")
    panel_body.template_list(
        "MHWANIMTOOLS_UL_lmt_entries",
        "",
        scene_props,
        "lmt_entries",
        scene_props,
        "selected_entry_index",
        rows=6,
    )
    if not (0 <= scene_props.selected_entry_index < len(scene_props.lmt_entries)):
        return
    entry = scene_props.lmt_entries[scene_props.selected_entry_index]
    details_header, details_body = panel_body.panel(
        idname="MHWANIMTOOLS_PT_lmt_selected_entry",
        default_closed=True,
    )
    details_header.label(text=f"Entry {entry.entry_id:03d}")
    if details_body is not None:
        details_box = details_body.box()
        details_box.label(text=f"Frames: {entry.frame_count}", icon="ACTION")
        details_box.label(text=f"Loop frame: {entry.loop_frame}")
        details_box.label(text=f"Tracks: {entry.track_count}")
        details_box.label(text=f"Flags: {entry.flags_hex} / {entry.flags2_hex}")
        details_box.label(text=f"Action translation: {entry.translation_preview}")
        details_box.label(text=f"Action rotation basis: {entry.rotation_preview}")
        if entry.has_timl:
            details_box.label(text="TIML attached", icon="NODETREE")
        _draw_entry_binding_summary(details_box, scene_props, entry)
        _draw_entry_import_section(details_body, scene_props, entry)

    tracks_header, tracks_body = panel_body.panel(
        idname="MHWANIMTOOLS_PT_lmt_tracks_browser",
        default_closed=True,
    )
    tracks_header.label(text="Tracks")
    if tracks_body is not None:
        _draw_track_details(tracks_body, scene_props)


def _timl_controller_for_file_entry(scene_props, entry_id: int):
    source_path = str(scene_props.last_timl_path or "")
    session_id = str(scene_props.last_timl_session_id or "")
    if not source_path:
        return None
    for candidate in bpy.data.objects:
        if not is_imported_timl_controller(candidate):
            continue
        metadata = extract_timl_controller_metadata(candidate)
        if str(metadata.source_lmt or "") != source_path:
            continue
        if session_id and str(metadata.session_id or "") != session_id:
            continue
        if int(metadata.entry_id) == int(entry_id):
            return candidate
    return None


def _timl_file_import_counts(scene_props):
    imported_count = 0
    importable_count = 0
    for item in scene_props.timl_file_entries:
        if item.has_data:
            importable_count += 1
        if _timl_controller_for_file_entry(scene_props, int(item.entry_id)) is not None:
            imported_count += 1
    return imported_count, importable_count


def _timl_export_readiness(scene_props):
    error_count = int(scene_props.last_timl_analysis_error_count)
    warning_count = int(scene_props.last_timl_analysis_warning_count)
    blocked_count = int(scene_props.last_timl_writeback_blocked_count)
    rebuild_count = int(scene_props.last_timl_writeback_rebuild_count)
    patch_count = int(scene_props.last_timl_writeback_patch_values_count)
    preserve_count = int(scene_props.last_timl_writeback_preserve_raw_count)

    if error_count or blocked_count:
        return "Blocked", "ERROR"
    if warning_count or rebuild_count:
        return "Needs Review", "INFO"
    if patch_count or preserve_count or scene_props.last_timl_writeback_available:
        return "Ready", "CHECKMARK"
    return "Unanalyzed", "INFO"


def _draw_timl_export_summary(panel_body, scene_props):
    if scene_props.last_timl_analysis_controller_name and scene_props.last_timl_writeback_available:
        readiness_label, readiness_icon = _timl_export_readiness(scene_props)
        timl_box = panel_body.box()
        timl_box.label(text="Focused TIML Writeback", icon="NODETREE")
        timl_box.label(text=scene_props.last_timl_analysis_controller_name, icon=readiness_icon)
        timl_box.label(text=f"State: {readiness_label}")
        timl_box.label(
            text=build_timl_writeback_summary(
                preserve_raw_count=scene_props.last_timl_writeback_preserve_raw_count,
                patch_values_count=scene_props.last_timl_writeback_patch_values_count,
                rebuild_count=scene_props.last_timl_writeback_rebuild_count,
                blocked_count=scene_props.last_timl_writeback_blocked_count,
            )
        )
        timl_box.label(
            text=build_timl_edit_policy_summary(
                value_only_count=scene_props.last_timl_edit_value_only_count,
                rebuild_capable_count=scene_props.last_timl_edit_rebuild_capable_count,
                blocked_count=scene_props.last_timl_edit_blocked_count,
            )
        )
        if scene_props.last_timl_payload_scope:
            timl_box.label(text=scene_props.last_timl_payload_scope)

    if scene_props.last_timl_path:
        imported_count, importable_count = _timl_file_import_counts(scene_props)
        timl_box = panel_body.box()
        timl_box.label(text="Standalone TIML", icon="CURRENT_FILE")
        timl_box.label(text=os.path.basename(scene_props.last_timl_path))
        if scene_props.last_timl_entry_count:
            timl_box.label(
                text=(
                    f"Entries: {int(scene_props.last_timl_entry_count)} | "
                    f"Imported: {imported_count}/{importable_count or int(scene_props.last_timl_entry_count)}"
                )
            )
        if imported_count <= 0:
            timl_box.label(text="Import at least one TIML entry before writing.", icon="INFO")
        elif imported_count < importable_count:
            timl_box.label(text="Write TIML will update imported entries and preserve untouched source entries.", icon="INFO")
        else:
            timl_box.label(text="Write TIML is ready to rewrite all imported standalone entries.", icon="CHECKMARK")
        timl_row = timl_box.row(align=True)
        timl_row.scale_y = 1.05
        timl_row.enabled = imported_count > 0
        timl_row.operator("mhw_anim_tools.save_timl_file", icon="FILE_TICK", text="Write TIML")


def _draw_timl_inspector_section(layout, scene_props):
    panel_header, panel_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_inspector_section",
        default_closed=True,
    )
    panel_header.label(text="TIML Inspector")
    if panel_body is None:
        return

    row = panel_body.row(align=True)
    row.scale_y = 1.1
    row.operator("mhw_anim_tools.inspect_timl", icon="IMPORT")
    row.operator("mhw_anim_tools.clear_timl_session", icon="TRASH", text="")
    if not scene_props.last_timl_path:
        panel_body.label(text="No TIML session loaded yet.", icon="INFO")
        return

    stats_box = panel_body.box()
    stats_box.label(text=os.path.basename(scene_props.last_timl_path), icon="CURRENT_FILE")
    stats_box.label(text=f"Entries: {scene_props.last_timl_entry_count}")
    stats_box.label(text=f"Types: {scene_props.last_timl_type_count}")
    stats_box.label(text=f"Transforms: {scene_props.last_timl_transform_count}")
    stats_box.label(text=f"Keyframes: {scene_props.last_timl_keyframe_count}")
    stats_box.label(text=f"Warnings: {scene_props.last_timl_warning_count}")
    stats_box.label(text=f"Errors: {scene_props.last_timl_error_count}")
    imported_count, importable_count = _timl_file_import_counts(scene_props)
    if scene_props.timl_file_entries:
        stats_box.label(text=f"Imported controllers: {imported_count}/{importable_count or len(scene_props.timl_file_entries)}")


def _draw_diagnostics_section(layout, scene_props):
    panel_header, panel_body = layout.panel(
        idname="MHWANIMTOOLS_PT_diagnostics_section",
        default_closed=True,
    )
    panel_header.label(text="Diagnostics")
    if panel_body is None:
        return
    if scene_props.diagnostics:
        panel_body.template_list(
            "MHWANIMTOOLS_UL_diagnostics",
            "",
            scene_props,
            "diagnostics",
            scene_props,
            "selected_diagnostic_index",
            rows=6,
        )
    else:
        panel_body.label(text="No diagnostics for the current session.", icon="CHECKMARK")


def _draw_export_section(layout, scene_props):
    panel_header, panel_body = layout.panel(
        idname="MHWANIMTOOLS_PT_export_section",
        default_closed=True,
    )
    panel_header.label(text="Export")
    if panel_body is None:
        return
    panel_body.prop(scene_props, "export_action")
    target = scene_props.target_armature
    active_action = target.animation_data.action if target and target.animation_data else None
    if scene_props.export_action is None and active_action is not None:
        panel_body.label(text=f"Using active armature action: {active_action.name}", icon="ACTION")
    row = panel_body.row(align=True)
    row.scale_y = 1.1
    row.operator("mhw_anim_tools.analyze_export_action", icon="EXPORT")
    row.operator("mhw_anim_tools.export_source_lmt", icon="FILE_TICK", text="Write Full LMT")
    _draw_timl_export_summary(panel_body, scene_props)

    if not scene_props.last_export_action_name:
        return
    stats_box = panel_body.box()
    stats_box.label(text=f"Last analyzed: {scene_props.last_export_action_name}", icon="ACTION")
    stats_box.label(text=f"Tracks: {scene_props.last_export_track_count}")
    stats_box.label(text=f"Plannable tracks: {scene_props.last_export_supported_track_count}")
    stats_box.label(text=f"Sparse keys: {scene_props.last_export_sparse_key_count}")
    stats_box.label(text=f"Frame end: {scene_props.last_export_frame_count}")
    if scene_props.last_export_buffer_summary:
        stats_box.label(text=f"Buffers: {scene_props.last_export_buffer_summary}")
    stats_box.label(text=f"Warnings: {scene_props.last_export_warning_count}")
    stats_box.label(text=f"Errors: {scene_props.last_export_error_count}")

    if (
        scene_props.last_export_mode
        or scene_props.last_export_source_name
        or scene_props.last_export_matching_timl_controller_count
        or scene_props.last_export_timl_source_scope
        or scene_props.last_export_timl_writeback_scope
    ):
        impact_box = panel_body.box()
        impact_box.label(text="Source Impact", icon="INFO")
        if scene_props.last_export_mode:
            impact_box.label(text=f"Mode: {scene_props.last_export_mode}")
        if scene_props.last_export_source_name:
            impact_box.label(text=f"Source: {_display_source_name(scene_props.last_export_source_name)}")
        impact_box.label(text=f"Entry: {scene_props.last_export_entry_id:03d}")
        if scene_props.last_export_source_action_count:
            impact_box.label(text=f"Source actions: {scene_props.last_export_source_action_count}")
            sibling_text = "yes" if scene_props.last_export_preserves_siblings else "no"
            impact_box.label(text=f"Preserves siblings: {sibling_text}")
        if scene_props.last_export_matching_timl_controller_count:
            impact_box.label(
                text=(
                    "Matching TIML controllers: "
                    f"{scene_props.last_export_matching_timl_controller_count}"
                )
            )
            if scene_props.last_export_matching_timl_controller_names:
                impact_box.label(text=scene_props.last_export_matching_timl_controller_names)
        if scene_props.last_export_timl_source_scope:
            impact_box.label(text=f"TIML source scope: {scene_props.last_export_timl_source_scope}")
        if scene_props.last_export_timl_writeback_scope:
            impact_box.label(text=f"TIML writeback scope: {scene_props.last_export_timl_writeback_scope}")


def draw_workspace_panel(layout, context):
    scene_props = context.scene.mhw_anim_tools
    draw_update_notice_box(layout)
    _draw_workspace_header(layout, scene_props)
    _draw_workspace_section(layout, context, scene_props)
    _draw_lmt_inspector_section(layout, scene_props)
    _draw_timl_inspector_section(layout, scene_props)
    _draw_diagnostics_section(layout, scene_props)
    _draw_export_section(layout, scene_props)


def draw_timl_inspector_panel(layout, context):
    scene_props = context.scene.mhw_anim_tools
    controller = timl_controller_for_object_panel(context)
    if controller is None:
        layout.label(text="Select an imported TIML controller to inspect it.", icon="INFO")
        return

    info_box = layout.box()
    action_row = info_box.row(align=True)
    action_row.scale_y = 1.1
    action_row.operator("mhw_anim_tools.open_timl_workspace", icon="WORKSPACE")
    action_row.operator("mhw_anim_tools.select_timl_controller", icon="RESTRICT_SELECT_OFF", text="Select")

    summary_box = layout.box()
    summary_box.label(text=controller.name, icon="EMPTY_DATA")
    action = controller.animation_data.action if controller.animation_data else None
    if action is not None:
        summary_box.label(text=f"Action: {action.name}", icon="ACTION")
    else:
        summary_box.label(text="No active TIML action on this controller", icon="ERROR")
    source_path = str(controller.get("mhw_anim_tools_timl_source_lmt", ""))
    entry_id = controller.get("mhw_anim_tools_timl_entry_id")
    source_offset = controller.get("mhw_anim_tools_timl_source_offset")
    source_summary = build_timl_source_summary(
        source_name=source_path,
        entry_id=int(entry_id) if entry_id is not None else None,
        source_offset=int(source_offset) if source_offset is not None else None,
    )
    if source_summary:
        summary_box.label(text=source_summary, icon="CURRENT_FILE")

    action_row = layout.row(align=True)
    action_row.scale_y = 1.1
    action_row.operator("mhw_anim_tools.select_timl_controller", icon="RESTRICT_SELECT_OFF")
    action_row.operator("mhw_anim_tools.analyze_timl_controller", icon="FCURVE")

    if scene_props.last_timl_analysis_controller_name == controller.name:
        analysis_box = layout.box()
        analysis_box.label(text="Controller Summary", icon="CHECKMARK")
        analysis_box.label(
            text=build_timl_analysis_summary(
                transform_count=scene_props.last_timl_analysis_transform_count,
                keyframe_count=scene_props.last_timl_analysis_keyframe_count,
                frame_end=scene_props.last_timl_analysis_frame_end,
                warning_count=scene_props.last_timl_analysis_warning_count,
                error_count=scene_props.last_timl_analysis_error_count,
            )
        )
        if scene_props.last_timl_writeback_available:
            _draw_timl_edit_policy_counts(analysis_box, scene_props)
            _draw_timl_writeback_counts(analysis_box, scene_props)
            _draw_timl_payload_scope(analysis_box, scene_props)
            _draw_timl_shared_controller_summary(analysis_box, scene_props)
        else:
            analysis_box.label(text="Source-backed writeback modes are not available for this controller yet.", icon="INFO")
    else:
        layout.label(text="Run Analyze TIML Controller to refresh writeback status.", icon="INFO")

    browser_header, browser_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_inspector_browser",
        default_closed=True,
    )
    browser_header.label(text="Transform Browser")
    if browser_body is not None:
        if not scene_props.timl_controller_transforms:
            browser_body.label(text="No sampled TIML transforms are available yet.", icon="INFO")
        else:
            browser_body.template_list(
                "MHWANIMTOOLS_UL_timl_controller_transforms",
                "",
                scene_props,
                "timl_controller_transforms",
                scene_props,
                "selected_timl_controller_transform_index",
                rows=10,
            )
            browser_body.label(text="Select a transform, then use Graph Editor for key edits.", icon="FCURVE")

    if not (0 <= scene_props.selected_timl_controller_transform_index < len(scene_props.timl_controller_transforms)):
        return

    transform = scene_props.timl_controller_transforms[scene_props.selected_timl_controller_transform_index]

    details_header, details_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_inspector_transform_details",
        default_closed=True,
    )
    details_header.label(text=transform.identity_label or "Selected Transform")
    if details_body is not None:
        title_box = details_body.box()
        title_box.label(text=transform.semantic_label or transform.data_type_name or "Unknown TIML Transform", icon="IPO_BEZIER")
        button_row = details_body.row(align=True)
        button_row.scale_y = 1.1
        button_row.operator("mhw_anim_tools.select_timl_transform_curves", icon="RESTRICT_SELECT_OFF", text="Select Curves")
        details_body.label(text=f"Timeline: {transform.timeline_display or '?'}")
        details_body.label(text=f"Datatype: {transform.datatype_display or '?'}")
        details_body.label(text=f"Storage type: {transform.data_type_name or '?'}")
        if transform.value_kind or transform.control_kind:
            details_body.label(text=f"Value/control: {transform.value_kind or '?'} / {transform.control_kind or '?'}")
        if transform.component_labels:
            details_body.label(text=f"Components: {transform.component_labels}")
        details_body.label(text=f"Keyframes: {transform.keyframe_count}")
        if transform.keyframe_count:
            details_body.label(text=f"Frame span: {transform.first_frame:.3f} -> {transform.last_frame:.3f}")
        if transform.first_value_preview:
            details_body.label(text=f"First value: {transform.first_value_preview}")
        if transform.interpolation_summary:
            details_body.label(text=f"Interpolation: {transform.interpolation_summary}")
        if transform.edit_policy_label:
            details_body.label(
                text=f"Edit policy: {transform.edit_policy_label}",
                icon=timl_edit_policy_icon(transform.edit_policy_code),
            )
        if transform.edit_policy_reason:
            details_body.label(text=transform.edit_policy_reason)
        if transform.writeback_status_label:
            details_body.label(
                text=f"Writeback: {transform.writeback_status_label}",
                icon=timl_writeback_status_icon(transform.writeback_status_code),
            )
        if transform.source_advanced:
            details_body.label(text="Source uses advanced interpolation/easing semantics.", icon="INFO")
        if transform.writeback_reason:
            details_body.label(text=transform.writeback_reason)

    metadata_header, metadata_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_inspector_metadata",
        default_closed=True,
    )
    metadata_header.label(text="Source Metadata")
    if metadata_body is not None:
        if transform.property_name:
            metadata_body.label(text=f"Property: {transform.property_name}")
        if transform.raw_timeline_display:
            metadata_body.label(text=f"Timeline hash: {transform.raw_timeline_display}")
        if transform.raw_datatype_display:
            metadata_body.label(text=f"Datatype hash: {transform.raw_datatype_display}")

    diagnostics_header, diagnostics_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_inspector_diagnostics",
        default_closed=True,
    )
    diagnostics_header.label(text="Diagnostics")
    if diagnostics_body is not None:
        if scene_props.diagnostics:
            diagnostics_body.template_list(
                "MHWANIMTOOLS_UL_diagnostics",
                "",
                scene_props,
                "diagnostics",
                scene_props,
                "selected_diagnostic_index",
                rows=6,
            )
        else:
            diagnostics_body.label(text="No diagnostics for this TIML controller.", icon="CHECKMARK")
