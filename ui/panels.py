# -*- coding: utf-8 -*-
"""Minimal Blender 4.5 sidebar UI for the rewrite scaffold."""

import json
import os

import bpy

from ..blender_adapter.armature import summarize_track_binding
from ..blender_adapter.space import uses_mhw_model_editor_space_adapter
from ..integration.model_editor import bonefunction_count
from ..integration.model_editor import get_workspace_summary
from ..integration.model_editor import mhbone_count


class MHWANIMTOOLS_PT_workspace(bpy.types.Panel):
    bl_label = "MHW Anim Tools"
    bl_idname = "MHWANIMTOOLS_PT_workspace"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MHW Anim"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        scene_props = context.scene.mhw_anim_tools
        summary = get_workspace_summary(context, scene_props.target_armature)

        header_box = layout.box()
        header_box.label(text="Session Browser", icon="ANIM_DATA")
        header_box.label(text=scene_props.last_status)

        panel_header, panel_body = layout.panel(
            idname="MHWANIMTOOLS_PT_workspace_section",
            default_closed=False,
        )
        panel_header.label(text="Workspace")
        if panel_body is not None:
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
            panel_body.label(text=f"Candidate armatures: {summary['candidate_count']}")
            target = summary["target_armature"]
            if target is not None:
                panel_body.label(text=f"Target MhBones: {mhbone_count(target)}")
                panel_body.label(text=f"Target BoneFunctions: {bonefunction_count(target)}")
                if uses_mhw_model_editor_space_adapter(target):
                    panel_body.label(text="Target space: MHW MOD3 adapter", icon="ORIENTATION_GLOBAL")
                else:
                    panel_body.label(text="Target space: direct / generic", icon="INFO")
            else:
                panel_body.label(text="No target armature selected", icon="ERROR")

        panel_header, panel_body = layout.panel(
            idname="MHWANIMTOOLS_PT_lmt_inspector_section",
            default_closed=False,
        )
        panel_header.label(text="LMT Inspector")
        if panel_body is not None:
            row = panel_body.row(align=True)
            row.scale_y = 1.1
            row.operator("mhw_anim_tools.inspect_lmt", icon="IMPORT")
            row.operator("mhw_anim_tools.clear_lmt_session", icon="TRASH", text="")
            if scene_props.last_lmt_path:
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
                if 0 <= scene_props.selected_entry_index < len(scene_props.lmt_entries):
                    entry = scene_props.lmt_entries[scene_props.selected_entry_index]
                    details = panel_body.box()
                    details.label(text=f"Entry {entry.entry_id:03d}", icon="ACTION")
                    details.label(text=f"Frames: {entry.frame_count}")
                    details.label(text=f"Loop frame: {entry.loop_frame}")
                    details.label(text=f"Tracks: {entry.track_count}")
                    details.label(text=f"Flags: {entry.flags_hex} / {entry.flags2_hex}")
                    details.label(text=f"Action translation: {entry.translation_preview}")
                    details.label(text=f"Action rotation basis: {entry.rotation_preview}")
                    details.label(text="TIML attached" if entry.has_timl else "No TIML attached")
                    if entry.has_timl:
                        timl_box = details.box()
                        timl_box.label(text=f"Attached TIML @ {entry.timl_source_offset_display or 'unknown'}", icon="NODETREE")
                        if entry.timl_parse_error:
                            timl_box.label(text=f"Parse issue: {entry.timl_parse_error}", icon="ERROR")
                        else:
                            timl_box.label(text=f"Types: {entry.timl_type_count}")
                            timl_box.label(text=f"Transforms: {entry.timl_transform_count}")
                            timl_box.label(text=f"Keyframes: {entry.timl_keyframe_count}")
                            timl_box.label(text=f"Anim length: {entry.timl_animation_length:.3f}")
                            timl_box.label(text=f"Loop start: {entry.timl_loop_start_point:.3f}")
                            timl_box.label(text=f"Loop control: {entry.timl_loop_control}")
                            if entry.timl_data_type_breakdown:
                                timl_box.label(text=entry.timl_data_type_breakdown)
                            if entry.timl_timeline_breakdown:
                                timl_box.label(text=entry.timl_timeline_breakdown)
                            import_timl_row = timl_box.row(align=True)
                            import_timl_row.scale_y = 1.1
                            import_timl_row.operator("mhw_anim_tools.import_selected_attached_timl", icon="NODETREE")
                            if scene_props.last_imported_timl_action_name:
                                timl_box.label(
                                    text=(
                                        f"Last TIML import: {scene_props.last_imported_timl_action_name} "
                                        f"on {scene_props.last_imported_timl_object_name}"
                                    )
                                )
                            panel_body.template_list(
                                "MHWANIMTOOLS_UL_timl_transforms",
                                "",
                                scene_props,
                                "timl_transforms",
                                scene_props,
                                "selected_timl_transform_index",
                                rows=6,
                            )
                            if 0 <= scene_props.selected_timl_transform_index < len(scene_props.timl_transforms):
                                timl_transform = scene_props.timl_transforms[scene_props.selected_timl_transform_index]
                                timl_transform_box = panel_body.box()
                                timl_transform_box.label(
                                    text=f"TIML Transform {timl_transform.type_index:02d}:{timl_transform.transform_index:02d}",
                                    icon="IPO_BEZIER",
                                )
                                timl_transform_box.label(text=f"Timeline: {timl_transform.timeline_parameter_label}")
                                timl_transform_box.label(text=f"Datatype hash: {timl_transform.datatype_label}")
                                timl_transform_box.label(text=f"Data type: {timl_transform.data_type_name}")
                                timl_transform_box.label(text=f"Value/control: {timl_transform.value_kind} / {timl_transform.control_kind}")
                                timl_transform_box.label(text=f"Keyframes: {timl_transform.keyframe_count}")
                                timl_transform_box.label(text=f"Frame span: {timl_transform.first_frame:.3f} -> {timl_transform.last_frame:.3f}")
                                if timl_transform.fractional_key_count:
                                    timl_transform_box.label(
                                        text=f"Fractional frames: {timl_transform.fractional_key_count}",
                                        icon="INFO",
                                    )
                                if timl_transform.first_value_preview:
                                    timl_transform_box.label(text=f"First value: {timl_transform.first_value_preview}")
                                if timl_transform.interpolation_summary:
                                    timl_transform_box.label(text=f"Interpolation: {timl_transform.interpolation_summary}")
                                if timl_transform.easing_summary:
                                    timl_transform_box.label(text=f"Easing: {timl_transform.easing_summary}")
                    details.label(text=entry.track_breakdown or "No track breakdown")
                    target = scene_props.target_armature
                    if target is not None and entry.track_payload:
                        try:
                            binding_summary = summarize_track_binding(target, json.loads(entry.track_payload))
                        except json.JSONDecodeError:
                            binding_summary = None
                        if binding_summary is not None:
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
                    import_row = details.row(align=True)
                    import_row.scale_y = 1.1
                    import_row.operator("mhw_anim_tools.import_selected_lmt_action", icon="ACTION")
                    if scene_props.last_imported_action_name:
                        details.label(text=f"Last imported: {scene_props.last_imported_action_name}")
                    panel_body.template_list(
                        "MHWANIMTOOLS_UL_lmt_tracks",
                        "",
                        scene_props,
                        "lmt_tracks",
                        scene_props,
                        "selected_track_index",
                        rows=8,
                    )
                    if 0 <= scene_props.selected_track_index < len(scene_props.lmt_tracks):
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
            else:
                panel_body.label(text="No LMT session loaded yet.", icon="INFO")

        panel_header, panel_body = layout.panel(
            idname="MHWANIMTOOLS_PT_diagnostics_section",
            default_closed=False,
        )
        panel_header.label(text="Diagnostics")
        if panel_body is not None:
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

        panel_header, panel_body = layout.panel(
            idname="MHWANIMTOOLS_PT_export_section",
            default_closed=True,
        )
        panel_header.label(text="Export")
        if panel_body is not None:
            panel_body.prop(scene_props, "export_action")
            target = scene_props.target_armature
            active_action = target.animation_data.action if target and target.animation_data else None
            if scene_props.export_action is None and active_action is not None:
                panel_body.label(text=f"Using active armature action: {active_action.name}", icon="ACTION")
            row = panel_body.row(align=True)
            row.scale_y = 1.1
            row.operator("mhw_anim_tools.analyze_export_action", icon="EXPORT")
            row.operator("mhw_anim_tools.export_lmt_action", icon="FILE_TICK", text="Write LMT")
            if scene_props.last_export_action_name:
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


classes = (MHWANIMTOOLS_PT_workspace,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
