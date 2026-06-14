# -*- coding: utf-8 -*-
"""Scene properties for milestone one."""

import json

import bpy


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
    timeline_parameter_label: bpy.props.StringProperty(name="Timeline Parameter", default="")
    datatype_label: bpy.props.StringProperty(name="Datatype", default="")
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


class MhwAnimToolsDiagnosticItem(bpy.types.PropertyGroup):
    level: bpy.props.StringProperty(name="Level", default="INFO")
    source: bpy.props.StringProperty(name="Source", default="")
    message: bpy.props.StringProperty(name="Message", default="")


def armature_object_poll(_self, obj):
    return obj is not None and obj.type == "ARMATURE"


def clear_diagnostics(scene_props):
    scene_props.diagnostics.clear()
    scene_props.selected_diagnostic_index = 0


def add_diagnostic(scene_props, level: str, source: str, message: str):
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
        item.timeline_parameter_label = transform.get("timeline_parameter_label", "")
        item.datatype_label = transform.get("datatype_label", "")
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


def selected_entry_update(self, _context):
    _populate_track_items(self)
    _populate_timl_transform_items(self)


class MhwAnimToolsSceneProperties(bpy.types.PropertyGroup):
    target_armature: bpy.props.PointerProperty(
        name="Target Armature",
        description="Preferred MHW armature for future preview and export tools",
        type=bpy.types.Object,
        poll=armature_object_poll,
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
    last_imported_timl_action_name: bpy.props.StringProperty(
        name="Last Imported TIML Action",
        default="",
    )
    last_imported_timl_object_name: bpy.props.StringProperty(
        name="Last Imported TIML Object",
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
    last_lmt_path: bpy.props.StringProperty(
        name="Last LMT",
        subtype="FILE_PATH",
        default="",
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
    selected_entry_index: bpy.props.IntProperty(
        name="Selected Entry",
        default=0,
        min=0,
        update=selected_entry_update,
    )
    lmt_entries: bpy.props.CollectionProperty(type=MhwAnimToolsLmtEntryItem)
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
