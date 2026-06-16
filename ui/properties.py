# -*- coding: utf-8 -*-
"""Scene properties for the Blender UI surfaces."""

import json

import bpy

from ..core.diagnostics.collections import has_text_diagnostic
from ..core.formats.timl.editor_model import TimlEditorTransformView
from ..core.formats.timl.editor_model import build_timl_editor_block_views
from ..core.formats.timl.model import timl_data_type_name
from .timl_presenter import build_timl_transform_labels
from .timl_labels import count_timl_edit_policies
from .timl_labels import count_timl_writeback_statuses
from .timl_labels import timl_edit_policy_code
from .timl_labels import timl_edit_policy_label
from .timl_labels import timl_edit_policy_reason_label
from .timl_labels import timl_payload_scope_label
from .timl_labels import timl_writeback_reason_label
from .timl_labels import timl_writeback_status_label

class MhwAnimToolsLmtEntryItem(bpy.types.PropertyGroup):
    entry_id: bpy.props.IntProperty(name="Entry ID", default=0)
    frame_count: bpy.props.IntProperty(name="Frame Count", default=0, min=0)
    loop_frame: bpy.props.IntProperty(name="Loop Frame", default=0)
    track_count: bpy.props.IntProperty(name="Track Count", default=0, min=0)
    has_timl: bpy.props.BoolProperty(name="Has TIML", default=False)
    flags_hex: bpy.props.StringProperty(name="Flags", default="")
    flags2_hex: bpy.props.StringProperty(name="Flags2", default="")
    translation_preview: bpy.props.StringProperty(name="Translation", default="")
    rotation_preview: bpy.props.StringProperty(name="Rotation", default="")
    track_breakdown: bpy.props.StringProperty(name="Track Breakdown", default="")
    track_payload: bpy.props.StringProperty(name="Track Payload", default="", options={"HIDDEN"})
    timl_source_offset_display: bpy.props.StringProperty(name="TIML Offset", default="")
    timl_type_count: bpy.props.IntProperty(name="TIML Type Count", default=0, min=0)
    timl_transform_count: bpy.props.IntProperty(name="TIML Transform Count", default=0, min=0)
    timl_keyframe_count: bpy.props.IntProperty(name="TIML Keyframe Count", default=0, min=0)
    timl_animation_length: bpy.props.FloatProperty(name="TIML Animation Length", default=0.0)
    timl_loop_start_point: bpy.props.FloatProperty(name="TIML Loop Start", default=0.0)
    timl_loop_control: bpy.props.IntProperty(name="TIML Loop Control", default=0)
    timl_data_type_breakdown: bpy.props.StringProperty(name="TIML Data Types", default="")
    timl_timeline_breakdown: bpy.props.StringProperty(name="TIML Timelines", default="")
    timl_transform_payload: bpy.props.StringProperty(name="TIML Transform Payload", default="", options={"HIDDEN"})
    timl_parse_error: bpy.props.StringProperty(name="TIML Parse Error", default="")


class MhwAnimToolsLmtTrackItem(bpy.types.PropertyGroup):
    track_index: bpy.props.IntProperty(name="Track Index", default=0, min=0)
    bone_id: bpy.props.IntProperty(name="Bone ID", default=0)
    usage: bpy.props.IntProperty(name="Usage", default=0)
    usage_scope: bpy.props.StringProperty(name="Usage Scope", default="")
    usage_label: bpy.props.StringProperty(name="Usage Label", default="")
    transform_label: bpy.props.StringProperty(name="Transform", default="")
    blender_path_hint: bpy.props.StringProperty(name="Blender Path", default="")
    channel_labels: bpy.props.StringProperty(name="Channels", default="")
    buffer_type: bpy.props.IntProperty(name="Buffer Type", default=0)
    buffer_code: bpy.props.StringProperty(name="Buffer Code", default="")
    buffer_label: bpy.props.StringProperty(name="Buffer Label", default="")
    buffer_size: bpy.props.IntProperty(name="Buffer Size", default=0)
    buffer_offset_display: bpy.props.StringProperty(name="Buffer Offset", default="")
    raw_key_count: bpy.props.IntProperty(name="Raw Keys", default=0)
    decoded_key_count: bpy.props.IntProperty(name="Decoded Keys", default=0)
    first_keyframe: bpy.props.IntProperty(name="First Key", default=-1)
    last_keyframe: bpy.props.IntProperty(name="Last Key", default=-1)
    has_lerp: bpy.props.BoolProperty(name="Has Lerp", default=False)
    weight: bpy.props.FloatProperty(name="Weight", default=0.0)
    basis_preview: bpy.props.StringProperty(name="Basis", default="")
    tail_frame: bpy.props.IntProperty(name="Tail Frame", default=-1)
    tail_preview: bpy.props.StringProperty(name="Tail", default="")
    decode_error: bpy.props.StringProperty(name="Decode Error", default="")
    unknown_tag: bpy.props.IntProperty(name="Unknown Tag", default=0)
    joint_type: bpy.props.IntProperty(name="Joint Type", default=0)


class MhwAnimToolsTimlTransformItem(bpy.types.PropertyGroup):
    type_index: bpy.props.IntProperty(name="Type Index", default=0, min=0)
    transform_index: bpy.props.IntProperty(name="Transform Index", default=0, min=0)
    identity_label: bpy.props.StringProperty(name="Identity", default="")
    semantic_label: bpy.props.StringProperty(name="Semantic Label", default="")
    timeline_parameter_label: bpy.props.StringProperty(name="Timeline Parameter", default="")
    datatype_label: bpy.props.StringProperty(name="Datatype", default="")
    raw_timeline_parameter_label: bpy.props.StringProperty(name="Timeline Hash", default="")
    raw_datatype_label: bpy.props.StringProperty(name="Datatype Hash", default="")
    data_type_name: bpy.props.StringProperty(name="Data Type", default="")
    value_kind: bpy.props.StringProperty(name="Value Kind", default="")
    control_kind: bpy.props.StringProperty(name="Control Kind", default="")
    keyframe_count: bpy.props.IntProperty(name="Keyframes", default=0, min=0)
    fractional_key_count: bpy.props.IntProperty(name="Fractional Keyframes", default=0, min=0)
    first_frame: bpy.props.FloatProperty(name="First Frame", default=0.0)
    last_frame: bpy.props.FloatProperty(name="Last Frame", default=0.0)
    first_value_preview: bpy.props.StringProperty(name="First Value", default="")
    interpolation_summary: bpy.props.StringProperty(name="Interpolation", default="")
    easing_summary: bpy.props.StringProperty(name="Easing", default="")


class MhwAnimToolsTimlFileEntryItem(bpy.types.PropertyGroup):
    entry_id: bpy.props.IntProperty(name="Entry ID", default=0, min=0)
    has_data: bpy.props.BoolProperty(name="Has Data", default=False)
    offset_display: bpy.props.StringProperty(name="Offset", default="")
    type_count: bpy.props.IntProperty(name="Type Count", default=0, min=0)
    transform_count: bpy.props.IntProperty(name="Transform Count", default=0, min=0)
    keyframe_count: bpy.props.IntProperty(name="Keyframe Count", default=0, min=0)
    animation_length: bpy.props.FloatProperty(name="Animation Length", default=0.0)
    loop_start_point: bpy.props.FloatProperty(name="Loop Start", default=0.0)
    loop_control: bpy.props.IntProperty(name="Loop Control", default=0)
    data_index_a: bpy.props.IntProperty(name="Data Index A", default=0)
    data_index_b: bpy.props.IntProperty(name="Data Index B", default=0)
    label_hash_display: bpy.props.StringProperty(name="Label Hash", default="")
    data_type_breakdown: bpy.props.StringProperty(name="Data Types", default="")
    timeline_breakdown: bpy.props.StringProperty(name="Timelines", default="")
    transform_payload: bpy.props.StringProperty(name="Transform Payload", default="", options={"HIDDEN"})
    parse_error: bpy.props.StringProperty(name="Parse Error", default="")


class MhwAnimToolsTimlControllerTransformItem(bpy.types.PropertyGroup):
    type_index: bpy.props.IntProperty(name="Type Index", default=0, min=0)
    transform_index: bpy.props.IntProperty(name="Transform Index", default=0, min=0)
    identity_label: bpy.props.StringProperty(name="Identity", default="")
    semantic_label: bpy.props.StringProperty(name="Semantic Label", default="")
    property_name: bpy.props.StringProperty(name="Property Name", default="")
    timeline_display: bpy.props.StringProperty(name="Timeline", default="")
    datatype_display: bpy.props.StringProperty(name="Datatype", default="")
    raw_timeline_display: bpy.props.StringProperty(name="Timeline Hash", default="")
    raw_datatype_display: bpy.props.StringProperty(name="Datatype Hash", default="")
    data_type_name: bpy.props.StringProperty(name="Data Type", default="")
    value_kind: bpy.props.StringProperty(name="Value Kind", default="")
    control_kind: bpy.props.StringProperty(name="Control Kind", default="")
    component_labels: bpy.props.StringProperty(name="Components", default="")
    keyframe_count: bpy.props.IntProperty(name="Keyframes", default=0, min=0)
    first_frame: bpy.props.FloatProperty(name="First Frame", default=0.0)
    last_frame: bpy.props.FloatProperty(name="Last Frame", default=0.0)
    first_value_preview: bpy.props.StringProperty(name="First Value", default="")
    interpolation_summary: bpy.props.StringProperty(name="Interpolation", default="")
    edit_policy_code: bpy.props.StringProperty(name="Edit Policy Code", default="")
    edit_policy_label: bpy.props.StringProperty(name="Edit Policy", default="")
    edit_policy_reason: bpy.props.StringProperty(name="Edit Policy Reason", default="")
    writeback_status_code: bpy.props.StringProperty(name="Writeback Status Code", default="")
    writeback_status_label: bpy.props.StringProperty(name="Writeback Status", default="")
    writeback_reason: bpy.props.StringProperty(name="Writeback Reason", default="")
    source_advanced: bpy.props.BoolProperty(name="Advanced Source", default=False)


class MhwAnimToolsTimlBlockItem(bpy.types.PropertyGroup):
    type_index: bpy.props.IntProperty(name="Type Index", default=0, min=0)
    timeline_hash: bpy.props.IntProperty(name="Timeline Hash", default=0)
    timeline_label: bpy.props.StringProperty(name="Timeline", default="")
    raw_timeline_label: bpy.props.StringProperty(name="Timeline Hash Display", default="")
    block_label: bpy.props.StringProperty(name="Block Label", default="")
    help_text: bpy.props.StringProperty(name="Help Text", default="")
    transform_count: bpy.props.IntProperty(name="Transform Count", default=0, min=0)
    keyframe_count: bpy.props.IntProperty(name="Keyframe Count", default=0, min=0)
    first_frame: bpy.props.FloatProperty(name="First Frame", default=0.0)
    last_frame: bpy.props.FloatProperty(name="Last Frame", default=0.0)
    datatype_summary: bpy.props.StringProperty(name="Datatype Summary", default="")
    writeback_summary: bpy.props.StringProperty(name="Writeback Summary", default="")
    edit_policy_summary: bpy.props.StringProperty(name="Edit Policy Summary", default="")
    transform_labels_json: bpy.props.StringProperty(name="Transform Labels", default="", options={"HIDDEN"})
    property_names_json: bpy.props.StringProperty(name="Property Names", default="", options={"HIDDEN"})
    known_semantic: bpy.props.BoolProperty(name="Known Semantic", default=False)


class MhwAnimToolsDiagnosticItem(bpy.types.PropertyGroup):
    level: bpy.props.StringProperty(name="Level", default="INFO")
    source: bpy.props.StringProperty(name="Source", default="")
    message: bpy.props.StringProperty(name="Message", default="")


def armature_object_poll(_self, obj):
    return obj is not None and obj.type == "ARMATURE"


def timl_controller_object_poll(_self, obj):
    return obj is not None and obj.type == "EMPTY"


def clear_diagnostics(scene_props):
    scene_props.diagnostics.clear()
    scene_props.selected_diagnostic_index = 0


def clear_export_analysis(scene_props):
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


def clear_timl_file_session(scene_props):
    scene_props.last_timl_path = ""
    scene_props.last_timl_session_id = ""
    scene_props.last_timl_entry_count = 0
    scene_props.last_timl_type_count = 0
    scene_props.last_timl_transform_count = 0
    scene_props.last_timl_keyframe_count = 0
    scene_props.last_timl_warning_count = 0
    scene_props.last_timl_error_count = 0
    scene_props.timl_file_entries.clear()
    scene_props.selected_timl_file_entry_index = 0


def add_diagnostic(scene_props, level: str, source: str, message: str):
    if has_text_diagnostic(
        scene_props.diagnostics,
        level=level,
        source=source,
        message=message,
    ):
        return
    item = scene_props.diagnostics.add()
    item.level = level
    item.source = source
    item.message = message


def _populate_track_items(scene_props):
    scene_props.lmt_tracks.clear()
    scene_props.selected_track_index = 0
    if not scene_props.lmt_entries:
        return
    entry_index = min(scene_props.selected_entry_index, len(scene_props.lmt_entries) - 1)
    entry = scene_props.lmt_entries[entry_index]
    if not entry.track_payload:
        return
    try:
        track_items = json.loads(entry.track_payload)
    except json.JSONDecodeError:
        return
    for track in track_items:
        item = scene_props.lmt_tracks.add()
        item.track_index = int(track.get("track_index", 0))
        item.bone_id = int(track.get("bone_id", 0))
        item.usage = int(track.get("usage", 0))
        item.usage_scope = track.get("usage_scope", "")
        item.usage_label = track.get("usage_label", "")
        item.transform_label = track.get("transform_label", "")
        item.blender_path_hint = track.get("blender_path_hint", "")
        item.channel_labels = track.get("channel_labels", "")
        item.buffer_type = int(track.get("buffer_type", 0))
        item.buffer_code = track.get("buffer_code", "")
        item.buffer_label = track.get("buffer_label", "")
        item.buffer_size = int(track.get("buffer_size", 0))
        item.buffer_offset_display = f"0x{int(track.get('buffer_offset', 0)):X}"
        item.raw_key_count = int(track.get("raw_key_count", 0))
        item.decoded_key_count = int(track.get("decoded_key_count", 0))
        item.first_keyframe = int(track.get("first_keyframe", -1))
        item.last_keyframe = int(track.get("last_keyframe", -1))
        item.has_lerp = bool(track.get("has_lerp", False))
        item.weight = float(track.get("weight", 0.0))
        item.basis_preview = track.get("basis_preview", "")
        item.tail_frame = int(track.get("tail_frame", -1))
        item.tail_preview = track.get("tail_preview", "")
        item.decode_error = track.get("decode_error", "")
        item.unknown_tag = int(track.get("unknown_tag", 0))
        item.joint_type = int(track.get("joint_type", 0))


def _populate_timl_transform_items(scene_props):
    scene_props.timl_transforms.clear()
    scene_props.selected_timl_transform_index = 0
    if not scene_props.lmt_entries:
        return
    entry_index = min(scene_props.selected_entry_index, len(scene_props.lmt_entries) - 1)
    entry = scene_props.lmt_entries[entry_index]
    if not entry.timl_transform_payload:
        return
    try:
        transform_items = json.loads(entry.timl_transform_payload)
    except json.JSONDecodeError:
        return
    for transform in transform_items:
        item = scene_props.timl_transforms.add()
        item.type_index = int(transform.get("type_index", 0))
        item.transform_index = int(transform.get("transform_index", 0))
        labels = build_timl_transform_labels(
            type_index=item.type_index,
            transform_index=item.transform_index,
            timeline_label=str(transform.get("timeline_parameter_label", "")),
            datatype_label=str(transform.get("datatype_label", "")),
            timeline_hash=int(transform.get("timeline_parameter_hash", 0)),
            datatype_hash=int(transform.get("datatype_hash", 0)),
            data_type_name=str(transform.get("data_type_name", "")),
        )
        item.identity_label = labels["identity_label"]
        item.semantic_label = labels["semantic_label"]
        item.timeline_parameter_label = labels["timeline_label"]
        item.datatype_label = labels["datatype_label"]
        item.raw_timeline_parameter_label = labels["raw_timeline_label"]
        item.raw_datatype_label = labels["raw_datatype_label"]
        item.data_type_name = transform.get("data_type_name", "")
        item.value_kind = transform.get("value_kind", "")
        item.control_kind = transform.get("control_kind", "")
        item.keyframe_count = int(transform.get("keyframe_count", 0))
        item.fractional_key_count = int(transform.get("fractional_key_count", 0))
        item.first_frame = float(transform.get("first_frame", 0.0) or 0.0)
        item.last_frame = float(transform.get("last_frame", 0.0) or 0.0)
        item.first_value_preview = transform.get("first_value_preview", "")
        item.interpolation_summary = ", ".join(
            f"{str(label)}={int(value)}"
            for label, value in dict(transform.get("interpolation_counts", {})).items()
        )
        item.easing_summary = ", ".join(
            f"{str(label)}={int(value)}"
            for label, value in dict(transform.get("easing_counts", {})).items()
        )


def _preview_value_text(value) -> str:
    if not value:
        return ""
    if len(value) == 1:
        return f"{float(value[0]):.4f}"
    return ", ".join(f"{float(component):.4f}" for component in value)


def _interpolation_summary_for_sampled_transform(transform) -> str:
    counts: dict[str, int] = {}
    for keyframe in getattr(transform, "keyframes", ()):
        label = str(getattr(keyframe, "interpolation", "") or "")
        counts[label] = counts.get(label, 0) + 1
    return ", ".join(
        f"{label}={count}"
        for label, count in sorted(counts.items(), key=lambda item: (item[0], item[1]))
    )


def _populate_timl_controller_transform_items(scene_props, sampled_result=None, writeback_plan=None):
    scene_props.timl_controller_transforms.clear()
    scene_props.selected_timl_controller_transform_index = 0

    sampled_map = {}
    if sampled_result is not None:
        sampled_map = {
            (int(transform.type_index), int(transform.transform_index)): transform
            for transform in getattr(sampled_result, "sampled_transforms", ())
        }
    plan_map = {}
    plan_items = []
    if writeback_plan is not None:
        plan_items = list(getattr(writeback_plan, "transform_plans", ()))
        plan_map = {
            (int(item.type_index), int(item.transform_index)): item
            for item in plan_items
        }

    if plan_items:
        identities = sorted(plan_map)
    else:
        identities = sorted(sampled_map)

    for identity in identities:
        sampled_transform = sampled_map.get(identity)
        plan_item = plan_map.get(identity)
        item = scene_props.timl_controller_transforms.add()
        item.type_index = int(identity[0])
        item.transform_index = int(identity[1])
        item.identity_label = build_timl_transform_labels(
            type_index=item.type_index,
            transform_index=item.transform_index,
        )["identity_label"]

        if sampled_transform is not None:
            labels = build_timl_transform_labels(
                type_index=item.type_index,
                transform_index=item.transform_index,
                timeline_hash=int(getattr(sampled_transform, "timeline_parameter_hash", 0)),
                datatype_hash=int(getattr(sampled_transform, "datatype_hash", 0)),
                data_type_name=str(getattr(sampled_transform, "data_type_name", "") or ""),
            )
            item.property_name = str(getattr(sampled_transform, "property_name", "") or "")
            item.semantic_label = labels["semantic_label"]
            item.timeline_display = labels["timeline_label"]
            item.datatype_display = labels["datatype_label"]
            item.raw_timeline_display = labels["raw_timeline_label"]
            item.raw_datatype_display = labels["raw_datatype_label"]
            item.data_type_name = str(getattr(sampled_transform, "data_type_name", "") or "")
            item.value_kind = str(getattr(sampled_transform, "value_kind", "") or "")
            item.control_kind = str(getattr(sampled_transform, "control_kind", "") or "")
            item.component_labels = ", ".join(str(label) for label in getattr(sampled_transform, "component_labels", ()))
            keyframes = tuple(getattr(sampled_transform, "keyframes", ()))
            item.keyframe_count = len(keyframes)
            if keyframes:
                item.first_frame = float(keyframes[0].frame)
                item.last_frame = float(keyframes[-1].frame)
                item.first_value_preview = _preview_value_text(getattr(keyframes[0], "value", ()))
            item.interpolation_summary = _interpolation_summary_for_sampled_transform(sampled_transform)
        elif plan_item is not None:
            labels = build_timl_transform_labels(
                type_index=item.type_index,
                transform_index=item.transform_index,
                timeline_hash=int(getattr(plan_item, "timeline_parameter_hash", 0)),
                datatype_hash=int(getattr(plan_item, "datatype_hash", 0)),
                data_type_name=timl_data_type_name(int(getattr(plan_item, "data_type", 0))),
            )
            item.semantic_label = labels["semantic_label"]
            item.timeline_display = labels["timeline_label"]
            item.datatype_display = labels["datatype_label"]
            item.raw_timeline_display = labels["raw_timeline_label"]
            item.raw_datatype_display = labels["raw_datatype_label"]
            item.data_type_name = timl_data_type_name(int(getattr(plan_item, "data_type", 0)))

        if plan_item is not None:
            status_code = str(getattr(plan_item, "status", "") or "")
            reason = str(getattr(plan_item, "reason", "") or "")
            source_advanced = bool(getattr(plan_item, "source_advanced", False))
            policy_code = timl_edit_policy_code(
                source_advanced=source_advanced,
                status=status_code,
                reason=reason,
            )
            item.edit_policy_code = policy_code
            item.edit_policy_label = timl_edit_policy_label(policy_code)
            item.edit_policy_reason = timl_edit_policy_reason_label(policy_code, reason=reason)
            item.writeback_status_code = status_code
            item.writeback_status_label = timl_writeback_status_label(status_code)
            item.writeback_reason = timl_writeback_reason_label(
                status_code,
                reason=reason,
                source_advanced=source_advanced,
            )
            item.source_advanced = source_advanced
        else:
            item.writeback_reason = "Source-backed writeback analysis is not available for this controller yet."

    _populate_timl_controller_block_items(scene_props)


def _build_timl_editor_transform_views(scene_props):
    transforms: list[TimlEditorTransformView] = []
    for item in scene_props.timl_controller_transforms:
        transforms.append(
            TimlEditorTransformView(
                type_index=int(item.type_index),
                transform_index=int(item.transform_index),
                property_name=str(item.property_name or ""),
                timeline_hash=int(item.raw_timeline_display.replace("0x", ""), 16) if str(item.raw_timeline_display).startswith("0x") else 0,
                timeline_label=str(item.timeline_display or ""),
                datatype_hash=int(item.raw_datatype_display.replace("0x", ""), 16) if str(item.raw_datatype_display).startswith("0x") else 0,
                datatype_label=str(item.datatype_display or ""),
                data_type_name=str(item.data_type_name or ""),
                keyframe_count=int(item.keyframe_count),
                first_frame=float(item.first_frame) if int(item.keyframe_count) else None,
                last_frame=float(item.last_frame) if int(item.keyframe_count) else None,
                semantic_label=str(item.semantic_label or ""),
                writeback_status_code=str(item.writeback_status_code or ""),
                writeback_status_label=str(item.writeback_status_label or ""),
                edit_policy_code=str(item.edit_policy_code or ""),
                edit_policy_label=str(item.edit_policy_label or ""),
            )
        )
    return transforms


def _populate_timl_controller_block_items(scene_props):
    scene_props.timl_blocks.clear()
    scene_props.selected_timl_block_index = 0
    transforms = _build_timl_editor_transform_views(scene_props)
    for block in build_timl_editor_block_views(transforms):
        item = scene_props.timl_blocks.add()
        item.type_index = int(block.type_index)
        item.timeline_hash = int(block.timeline_hash)
        item.timeline_label = str(block.timeline_label or "")
        item.raw_timeline_label = str(block.raw_timeline_label or "")
        item.block_label = str(block.block_label or "")
        item.help_text = str(block.help_text or "")
        item.transform_count = int(block.transform_count)
        item.keyframe_count = int(block.keyframe_count)
        if block.first_frame is not None:
            item.first_frame = float(block.first_frame)
        if block.last_frame is not None:
            item.last_frame = float(block.last_frame)
        item.datatype_summary = str(block.datatype_summary or "")
        item.writeback_summary = str(block.writeback_summary or "")
        item.edit_policy_summary = str(block.edit_policy_summary or "")
        item.transform_labels_json = json.dumps(list(block.transform_labels))
        item.property_names_json = json.dumps(list(block.property_names))
        item.known_semantic = bool(block.known_semantic)


def selected_entry_update(self, _context):
    _populate_track_items(self)
    _populate_timl_transform_items(self)


def clear_timl_analysis(scene_props):
    scene_props.last_timl_analysis_controller_name = ""
    scene_props.last_timl_analysis_action_name = ""
    scene_props.last_timl_analysis_transform_count = 0
    scene_props.last_timl_analysis_keyframe_count = 0
    scene_props.last_timl_analysis_frame_end = 0
    scene_props.last_timl_analysis_warning_count = 0
    scene_props.last_timl_analysis_error_count = 0
    scene_props.last_timl_writeback_available = False
    scene_props.last_timl_writeback_preserve_raw_count = 0
    scene_props.last_timl_writeback_patch_values_count = 0
    scene_props.last_timl_writeback_rebuild_count = 0
    scene_props.last_timl_writeback_blocked_count = 0
    scene_props.last_timl_edit_value_only_count = 0
    scene_props.last_timl_edit_rebuild_capable_count = 0
    scene_props.last_timl_edit_blocked_count = 0
    scene_props.last_timl_payload_scope = ""
    scene_props.last_timl_matching_controller_count = 0
    scene_props.last_timl_matching_controller_names = ""
    scene_props.last_timl_shared_controller_status = ""
    scene_props.timl_controller_transforms.clear()
    scene_props.selected_timl_controller_transform_index = 0
    scene_props.timl_blocks.clear()
    scene_props.selected_timl_block_index = 0


def set_timl_writeback_summary(scene_props, statuses):
    counts = count_timl_writeback_statuses(statuses)
    scene_props.last_timl_writeback_available = any(counts.values())
    scene_props.last_timl_writeback_preserve_raw_count = counts["preserve_raw"]
    scene_props.last_timl_writeback_patch_values_count = counts["patch_source_values"]
    scene_props.last_timl_writeback_rebuild_count = counts["rewrite_preview"]
    scene_props.last_timl_writeback_blocked_count = counts["unsupported_rebuild"]


def set_timl_edit_policy_summary(scene_props, plan_items):
    policies = [
        timl_edit_policy_code(
            source_advanced=bool(getattr(item, "source_advanced", False)),
            status=str(getattr(item, "status", "") or ""),
            reason=str(getattr(item, "reason", "") or ""),
        )
        for item in plan_items
    ]
    counts = count_timl_edit_policies(policies)
    scene_props.last_timl_edit_value_only_count = counts["value_only"]
    scene_props.last_timl_edit_rebuild_capable_count = counts["rebuild_capable"]
    scene_props.last_timl_edit_blocked_count = counts["blocked"]


def set_timl_payload_scope_summary(scene_props, action_ids):
    scene_props.last_timl_payload_scope = timl_payload_scope_label(action_ids)


def set_timl_shared_controller_summary(scene_props, assessment):
    scene_props.last_timl_matching_controller_count = len(getattr(assessment, "matching_controller_names", ()) or ())
    scene_props.last_timl_matching_controller_names = ", ".join(
        str(name)
        for name in (getattr(assessment, "matching_controller_names", ()) or ())
        if str(name)
    )
    scene_props.last_timl_shared_controller_status = str(getattr(assessment, "status", "") or "")


class MhwAnimToolsSceneProperties(bpy.types.PropertyGroup):
    target_armature: bpy.props.PointerProperty(
        name="Target Armature",
        description="Preferred MHW armature for future preview and export tools",
        type=bpy.types.Object,
        poll=armature_object_poll,
    )
    timl_controller: bpy.props.PointerProperty(
        name="TIML Controller",
        description="Imported TIML controller object for the active TIML editing workflow",
        type=bpy.types.Object,
        poll=timl_controller_object_poll,
    )
    export_action: bpy.props.PointerProperty(
        name="Export Action",
        description="Blender Action to analyze for the reverse LMT export path",
        type=bpy.types.Action,
    )
    last_status: bpy.props.StringProperty(
        name="Status",
        default="Ready",
    )
    last_imported_action_name: bpy.props.StringProperty(
        name="Last Imported Action",
        default="",
    )
    last_imported_action_count: bpy.props.IntProperty(
        name="Last Imported Action Count",
        default=0,
        min=0,
    )
    last_imported_timl_action_name: bpy.props.StringProperty(
        name="Last Imported TIML Action",
        default="",
    )
    last_imported_timl_object_name: bpy.props.StringProperty(
        name="Last Imported TIML Object",
        default="",
    )
    last_timl_analysis_controller_name: bpy.props.StringProperty(
        name="Last TIML Analysis Controller",
        default="",
    )
    last_timl_analysis_action_name: bpy.props.StringProperty(
        name="Last TIML Analysis Action",
        default="",
    )
    last_timl_analysis_transform_count: bpy.props.IntProperty(
        name="TIML Transform Count",
        default=0,
        min=0,
    )
    last_timl_analysis_keyframe_count: bpy.props.IntProperty(
        name="TIML Keyframe Count",
        default=0,
        min=0,
    )
    last_timl_analysis_frame_end: bpy.props.IntProperty(
        name="TIML Frame End",
        default=0,
        min=0,
    )
    last_timl_analysis_warning_count: bpy.props.IntProperty(
        name="TIML Warning Count",
        default=0,
        min=0,
    )
    last_timl_analysis_error_count: bpy.props.IntProperty(
        name="TIML Error Count",
        default=0,
        min=0,
    )
    last_timl_writeback_available: bpy.props.BoolProperty(
        name="TIML Writeback Available",
        default=False,
    )
    last_timl_writeback_preserve_raw_count: bpy.props.IntProperty(
        name="TIML Preserve Raw Count",
        default=0,
        min=0,
    )
    last_timl_writeback_patch_values_count: bpy.props.IntProperty(
        name="TIML Patch Values Count",
        default=0,
        min=0,
    )
    last_timl_writeback_rebuild_count: bpy.props.IntProperty(
        name="TIML Rebuild Preview Count",
        default=0,
        min=0,
    )
    last_timl_writeback_blocked_count: bpy.props.IntProperty(
        name="TIML Blocked Count",
        default=0,
        min=0,
    )
    last_timl_edit_value_only_count: bpy.props.IntProperty(
        name="TIML Value-Only Count",
        default=0,
        min=0,
    )
    last_timl_edit_rebuild_capable_count: bpy.props.IntProperty(
        name="TIML Rebuild-Capable Count",
        default=0,
        min=0,
    )
    last_timl_edit_blocked_count: bpy.props.IntProperty(
        name="TIML Edit-Blocked Count",
        default=0,
        min=0,
    )
    last_timl_payload_scope: bpy.props.StringProperty(
        name="TIML Payload Scope",
        default="",
    )
    last_timl_matching_controller_count: bpy.props.IntProperty(
        name="TIML Matching Controller Count",
        default=0,
        min=0,
    )
    last_timl_matching_controller_names: bpy.props.StringProperty(
        name="TIML Matching Controller Names",
        default="",
    )
    last_timl_shared_controller_status: bpy.props.StringProperty(
        name="TIML Shared Controller Status",
        default="",
    )
    last_export_action_name: bpy.props.StringProperty(
        name="Last Export Action",
        default="",
    )
    last_export_track_count: bpy.props.IntProperty(
        name="Export Track Count",
        default=0,
        min=0,
    )
    last_export_sparse_key_count: bpy.props.IntProperty(
        name="Export Sparse Keys",
        default=0,
        min=0,
    )
    last_export_supported_track_count: bpy.props.IntProperty(
        name="Supported Export Tracks",
        default=0,
        min=0,
    )
    last_export_frame_count: bpy.props.IntProperty(
        name="Export Frame Count",
        default=0,
        min=0,
    )
    last_export_buffer_summary: bpy.props.StringProperty(
        name="Export Buffer Summary",
        default="",
    )
    last_export_warning_count: bpy.props.IntProperty(
        name="Export Warnings",
        default=0,
        min=0,
    )
    last_export_error_count: bpy.props.IntProperty(
        name="Export Errors",
        default=0,
        min=0,
    )
    last_export_mode: bpy.props.StringProperty(
        name="Export Mode",
        default="",
    )
    last_export_source_name: bpy.props.StringProperty(
        name="Export Source Name",
        default="",
    )
    last_export_entry_id: bpy.props.IntProperty(
        name="Export Entry ID",
        default=0,
    )
    last_export_source_action_count: bpy.props.IntProperty(
        name="Export Source Action Count",
        default=0,
        min=0,
    )
    last_export_preserves_siblings: bpy.props.BoolProperty(
        name="Export Preserves Siblings",
        default=False,
    )
    last_export_matching_timl_controller_count: bpy.props.IntProperty(
        name="Export Matching TIML Controllers",
        default=0,
        min=0,
    )
    last_export_matching_timl_controller_names: bpy.props.StringProperty(
        name="Export Matching TIML Controller Names",
        default="",
    )
    last_export_timl_source_scope: bpy.props.StringProperty(
        name="Export TIML Source Scope",
        default="",
    )
    last_export_timl_writeback_scope: bpy.props.StringProperty(
        name="Export TIML Writeback Scope",
        default="",
    )
    last_lmt_path: bpy.props.StringProperty(
        name="Last LMT",
        subtype="FILE_PATH",
        default="",
    )
    last_timl_path: bpy.props.StringProperty(
        name="Last TIML",
        subtype="FILE_PATH",
        default="",
    )
    last_timl_session_id: bpy.props.StringProperty(
        name="TIML Session ID",
        default="",
        options={"HIDDEN"},
    )
    last_entry_count: bpy.props.IntProperty(
        name="Entry Count",
        default=0,
        min=0,
    )
    last_action_count: bpy.props.IntProperty(
        name="Action Count",
        default=0,
        min=0,
    )
    last_track_count: bpy.props.IntProperty(
        name="Track Count",
        default=0,
        min=0,
    )
    last_warning_count: bpy.props.IntProperty(
        name="Warnings",
        default=0,
        min=0,
    )
    last_error_count: bpy.props.IntProperty(
        name="Errors",
        default=0,
        min=0,
    )
    last_timl_entry_count: bpy.props.IntProperty(
        name="TIML Entry Count",
        default=0,
        min=0,
    )
    last_timl_type_count: bpy.props.IntProperty(
        name="TIML Type Count",
        default=0,
        min=0,
    )
    last_timl_transform_count: bpy.props.IntProperty(
        name="TIML Transform Count",
        default=0,
        min=0,
    )
    last_timl_keyframe_count: bpy.props.IntProperty(
        name="TIML Keyframe Count",
        default=0,
        min=0,
    )
    last_timl_warning_count: bpy.props.IntProperty(
        name="TIML Warnings",
        default=0,
        min=0,
    )
    last_timl_error_count: bpy.props.IntProperty(
        name="TIML Errors",
        default=0,
        min=0,
    )
    selected_entry_index: bpy.props.IntProperty(
        name="Selected Entry",
        default=0,
        min=0,
        update=selected_entry_update,
    )
    lmt_entries: bpy.props.CollectionProperty(type=MhwAnimToolsLmtEntryItem)
    selected_timl_file_entry_index: bpy.props.IntProperty(
        name="Selected TIML Entry",
        default=0,
        min=0,
    )
    timl_file_entries: bpy.props.CollectionProperty(type=MhwAnimToolsTimlFileEntryItem)
    selected_track_index: bpy.props.IntProperty(
        name="Selected Track",
        default=0,
        min=0,
    )
    lmt_tracks: bpy.props.CollectionProperty(type=MhwAnimToolsLmtTrackItem)
    selected_timl_transform_index: bpy.props.IntProperty(
        name="Selected TIML Transform",
        default=0,
        min=0,
    )
    timl_transforms: bpy.props.CollectionProperty(type=MhwAnimToolsTimlTransformItem)
    selected_timl_controller_transform_index: bpy.props.IntProperty(
        name="Selected TIML Controller Transform",
        default=0,
        min=0,
    )
    timl_controller_transforms: bpy.props.CollectionProperty(type=MhwAnimToolsTimlControllerTransformItem)
    selected_timl_block_index: bpy.props.IntProperty(
        name="Selected TIML Block",
        default=0,
        min=0,
    )
    timl_blocks: bpy.props.CollectionProperty(type=MhwAnimToolsTimlBlockItem)
    selected_diagnostic_index: bpy.props.IntProperty(
        name="Selected Diagnostic",
        default=0,
        min=0,
    )
    diagnostics: bpy.props.CollectionProperty(type=MhwAnimToolsDiagnosticItem)


classes = (
    MhwAnimToolsLmtEntryItem,
    MhwAnimToolsLmtTrackItem,
    MhwAnimToolsTimlTransformItem,
    MhwAnimToolsTimlFileEntryItem,
    MhwAnimToolsTimlControllerTransformItem,
    MhwAnimToolsTimlBlockItem,
    MhwAnimToolsDiagnosticItem,
    MhwAnimToolsSceneProperties,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mhw_anim_tools = bpy.props.PointerProperty(type=MhwAnimToolsSceneProperties)


def unregister():
    del bpy.types.Scene.mhw_anim_tools
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
