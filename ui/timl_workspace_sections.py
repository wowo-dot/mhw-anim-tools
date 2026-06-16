# -*- coding: utf-8 -*-
"""Compact raw TIML workspace sections for the Graph Editor sidebar."""

from __future__ import annotations

import bpy

from ..blender_adapter.timl_metadata import TIML_HEADER_ANIMATION_LENGTH_KEY
from ..blender_adapter.timl_metadata import TIML_HEADER_DATA_INDEX_A_KEY
from ..blender_adapter.timl_metadata import TIML_HEADER_DATA_INDEX_B_KEY
from ..blender_adapter.timl_metadata import TIML_HEADER_LABEL_HASH_KEY
from ..blender_adapter.timl_metadata import TIML_HEADER_LOOP_CONTROL_KEY
from ..blender_adapter.timl_metadata import TIML_HEADER_LOOP_START_POINT_KEY
from ..blender_adapter.timl_sampling import extract_timl_controller_metadata
from ..blender_adapter.timl_sampling import is_imported_timl_controller
from .timl_labels import timl_edit_policy_icon
from .timl_labels import timl_writeback_status_icon


def timl_controller_for_workspace_panel(context):
    scene_props = context.scene.mhw_anim_tools
    candidate = scene_props.timl_controller
    if is_imported_timl_controller(candidate):
        return candidate
    active_object = getattr(context, "active_object", None)
    if is_imported_timl_controller(active_object):
        return active_object
    if scene_props.last_imported_timl_object_name:
        named = bpy.data.objects.get(scene_props.last_imported_timl_object_name)
        if is_imported_timl_controller(named):
            return named
    for named in bpy.data.objects:
        if is_imported_timl_controller(named):
            return named
    return None


def _selected_entry(scene_props):
    items = scene_props.lmt_entries
    index = int(scene_props.selected_entry_index)
    if 0 <= index < len(items):
        return items[index]
    return None


def _controller_for_entry(scene_props, entry):
    if entry is None:
        return None
    source_path = str(scene_props.last_lmt_path or "")
    entry_id = int(entry.entry_id)
    for candidate in bpy.data.objects:
        if not is_imported_timl_controller(candidate):
            continue
        metadata = extract_timl_controller_metadata(candidate)
        if str(metadata.source_lmt or "") != source_path:
            continue
        if int(metadata.entry_id) == entry_id:
            return candidate
    return None


def _selected_timl_block(scene_props):
    items = scene_props.timl_blocks
    index = int(scene_props.selected_timl_block_index)
    if 0 <= index < len(items):
        return items[index]
    return None


def _selected_transform(scene_props):
    items = scene_props.timl_controller_transforms
    index = int(scene_props.selected_timl_controller_transform_index)
    if 0 <= index < len(items):
        return items[index]
    return None


def _header_prop(layout, controller, key: str, label: str):
    if key in controller:
        layout.prop(controller, f'["{key}"]', text=label)


def _draw_workspace_header(layout, scene_props, controller):
    box = layout.box()
    if controller is None:
        box.label(text="No imported TIML controller")
        return
    metadata = extract_timl_controller_metadata(controller)
    box.label(text=controller.name, icon="EMPTY_DATA")
    action = controller.animation_data.action if controller.animation_data else None
    if action is not None:
        box.label(text=f"Action {action.name}", icon="ACTION")
    source_bits = []
    if metadata.source_lmt:
        source_bits.append(str(metadata.source_lmt).split("\\")[-1].split("/")[-1])
    source_bits.append(f"Entry {int(metadata.entry_id):03d}")
    if int(metadata.source_offset):
        source_bits.append(f"Offset 0x{int(metadata.source_offset):X}")
    box.label(text=" | ".join(source_bits), icon="CURRENT_FILE")
    if scene_props.last_timl_analysis_controller_name == controller.name:
        counts = (
            f"Transforms {int(scene_props.last_timl_analysis_transform_count)} | "
            f"Keys {int(scene_props.last_timl_analysis_keyframe_count)} | "
            f"Frame end {int(scene_props.last_timl_analysis_frame_end)} | "
            f"Warnings {int(scene_props.last_timl_analysis_warning_count)} | "
            f"Errors {int(scene_props.last_timl_analysis_error_count)}"
        )
        box.label(text=counts, icon="CHECKMARK")


def _draw_entry_browser(layout, scene_props):
    panel_header, panel_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_workspace_entries",
        default_closed=False,
    )
    panel_header.label(text="Entries")
    if panel_body is None:
        return
    if not scene_props.lmt_entries:
        panel_body.label(text="No LMT session")
        return
    panel_body.template_list(
        "MHWANIMTOOLS_UL_lmt_entries",
        "",
        scene_props,
        "lmt_entries",
        scene_props,
        "selected_entry_index",
        rows=6,
    )
    row = panel_body.row(align=True)
    row.scale_y = 1.05
    row.operator("mhw_anim_tools.import_selected_attached_timl", text="Import Selected", icon="IMPORT")
    row.operator("mhw_anim_tools.import_all_attached_timl", text="Import All", icon="IMPORT")
    row.operator("mhw_anim_tools.focus_selected_entry_timl_controller", text="Focus", icon="RESTRICT_SELECT_OFF")

    entry = _selected_entry(scene_props)
    if entry is None:
        return
    details = panel_body.box()
    details.label(
        text=(
            f"Entry {int(entry.entry_id):03d} | {int(entry.frame_count)}f | "
            f"{entry.timl_source_offset_display or 'No TIML'}"
        )
    )
    if entry.has_timl:
        details.label(
            text=(
                f"{int(entry.timl_type_count)}t | "
                f"{int(entry.timl_transform_count)}tr | "
                f"{int(entry.timl_keyframe_count)}k"
            )
        )
    controller = _controller_for_entry(scene_props, entry)
    details.label(text=f"Imported {controller.name}" if controller is not None else "Not imported")


def _draw_workspace_toolbar(layout):
    row = layout.row(align=True)
    row.scale_y = 1.05
    row.operator("mhw_anim_tools.open_timl_workspace", text="Open TIML Workspace", icon="WORKSPACE")
    row.operator("mhw_anim_tools.select_timl_controller", text="Select Controller", icon="RESTRICT_SELECT_OFF")
    row.operator("mhw_anim_tools.analyze_timl_controller", text="Analyze", icon="FCURVE")


def _draw_header_editor(layout, controller):
    if controller is None:
        return
    panel_header, panel_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_workspace_header",
        default_closed=False,
    )
    panel_header.label(text="Header")
    if panel_body is None:
        return
    row = panel_body.row(align=True)
    row.operator("mhw_anim_tools.edit_timl_header", text="Edit Header", icon="GREASEPENCIL")
    if TIML_HEADER_LABEL_HASH_KEY in controller:
        row.label(text=f"0x{int(controller[TIML_HEADER_LABEL_HASH_KEY]) & 0xFFFFFFFF:08X}")
    _header_prop(panel_body, controller, TIML_HEADER_DATA_INDEX_A_KEY, "data_index_a")
    _header_prop(panel_body, controller, TIML_HEADER_DATA_INDEX_B_KEY, "data_index_b")
    _header_prop(panel_body, controller, TIML_HEADER_ANIMATION_LENGTH_KEY, "animation_length")
    _header_prop(panel_body, controller, TIML_HEADER_LOOP_START_POINT_KEY, "loop_start_point")
    _header_prop(panel_body, controller, TIML_HEADER_LOOP_CONTROL_KEY, "loop_control")


def _draw_type_browser(layout, scene_props):
    panel_header, panel_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_workspace_types",
        default_closed=False,
    )
    panel_header.label(text="Types")
    if panel_body is None:
        return
    panel_body.template_list(
        "MHWANIMTOOLS_UL_timl_blocks",
        "",
        scene_props,
        "timl_blocks",
        scene_props,
        "selected_timl_block_index",
        rows=6,
    )
    row = panel_body.row(align=True)
    row.scale_y = 1.05
    row.operator("mhw_anim_tools.add_timl_type", text="", icon="ADD")
    row.operator("mhw_anim_tools.duplicate_timl_type", text="", icon="DUPLICATE")
    row.operator("mhw_anim_tools.edit_timl_type", text="", icon="GREASEPENCIL")
    row.operator("mhw_anim_tools.delete_timl_type", text="", icon="TRASH")

    block = _selected_timl_block(scene_props)
    if block is None:
        return
    info = panel_body.box()
    info.label(text=f"T{int(block.type_index):02d} | {block.block_label or block.raw_timeline_label or '?'}")
    info.label(text=f"{int(block.transform_count)}tr | {int(block.keyframe_count)}k")
    if int(block.keyframe_count):
        info.label(text=f"{float(block.first_frame):.3f} -> {float(block.last_frame):.3f}")
    if block.raw_timeline_label:
        info.label(text=block.raw_timeline_label)


def _draw_transform_browser(layout, scene_props):
    panel_header, panel_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_workspace_transforms",
        default_closed=False,
    )
    panel_header.label(text="Transforms")
    if panel_body is None:
        return
    panel_body.template_list(
        "MHWANIMTOOLS_UL_timl_controller_transforms",
        "",
        scene_props,
        "timl_controller_transforms",
        scene_props,
        "selected_timl_controller_transform_index",
        rows=10,
    )
    row = panel_body.row(align=True)
    row.scale_y = 1.05
    row.operator("mhw_anim_tools.add_timl_transform", text="", icon="ADD")
    row.operator("mhw_anim_tools.duplicate_timl_transform", text="", icon="DUPLICATE")
    row.operator("mhw_anim_tools.clone_timl_transform_from_existing", text="", icon="PASTEDOWN")
    row.operator("mhw_anim_tools.edit_timl_transform", text="", icon="GREASEPENCIL")
    row.operator("mhw_anim_tools.delete_timl_transform", text="", icon="TRASH")


def _draw_transform_detail(layout, scene_props, controller):
    transform = _selected_transform(scene_props)
    if transform is None or controller is None:
        return
    panel_header, panel_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_workspace_transform_detail",
        default_closed=False,
    )
    panel_header.label(text=transform.identity_label or "Transform")
    if panel_body is None:
        return
    top = panel_body.row(align=True)
    top.operator("mhw_anim_tools.select_timl_transform_curves", text="Curves", icon="FCURVE")
    if int(transform.keyframe_count) > 0:
        top.operator("mhw_anim_tools.use_timl_transform_frame_span", text="Use Span", icon="PREVIEW_RANGE")
    panel_body.label(text=transform.semantic_label or transform.timeline_display or transform.raw_timeline_display or "?")
    if transform.timeline_display:
        panel_body.label(text=transform.timeline_display)
    if transform.raw_timeline_display:
        panel_body.label(text=transform.raw_timeline_display)
    if transform.datatype_display or transform.raw_datatype_display:
        panel_body.label(text=f"{transform.datatype_display or '?'} | {transform.raw_datatype_display or '?'}")
    if transform.data_type_name:
        panel_body.label(text=transform.data_type_name)
    if transform.keyframe_count:
        panel_body.label(text=f"{float(transform.first_frame):.3f} -> {float(transform.last_frame):.3f} | {int(transform.keyframe_count)}k")
    if transform.edit_policy_label:
        panel_body.label(
            text=transform.edit_policy_label,
            icon=timl_edit_policy_icon(transform.edit_policy_code),
        )
    if transform.writeback_status_label:
        panel_body.label(
            text=transform.writeback_status_label,
            icon=timl_writeback_status_icon(transform.writeback_status_code),
        )
    property_name = str(transform.property_name or "")
    if property_name and property_name in controller.keys():
        panel_body.prop(controller, f'["{property_name}"]', text=property_name)
    row = panel_body.row(align=True)
    row.operator("mhw_anim_tools.edit_timl_transform", text="Edit Raw", icon="GREASEPENCIL")


def _draw_workspace_diagnostics(layout, scene_props):
    panel_header, panel_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_workspace_diagnostics",
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
            rows=5,
        )
    else:
        panel_body.label(text="No diagnostics")


def draw_timl_workspace_editor_panel(layout, context):
    scene_props = context.scene.mhw_anim_tools
    controller = timl_controller_for_workspace_panel(context)

    _draw_workspace_header(layout, scene_props, controller)
    _draw_entry_browser(layout, scene_props)
    _draw_workspace_toolbar(layout)

    if controller is None:
        return

    _draw_header_editor(layout, controller)
    _draw_type_browser(layout, scene_props)
    _draw_transform_browser(layout, scene_props)
    _draw_transform_detail(layout, scene_props, controller)
    _draw_workspace_diagnostics(layout, scene_props)
