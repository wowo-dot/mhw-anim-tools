# -*- coding: utf-8 -*-
"""Dedicated TIML workspace editor sections for the Graph Editor sidebar."""

from __future__ import annotations

import json

import bpy

from ..blender_adapter.timl_sampling import is_imported_timl_controller
from ..blender_adapter.timl_metadata import TIML_BINDINGS_KEY
from ..core.formats.timl.editor_model import timl_editor_field_help_text
from .timl_labels import timl_edit_policy_icon
from .timl_labels import timl_writeback_status_icon
from .timl_presenter import build_timl_analysis_summary
from .timl_presenter import build_timl_edit_policy_summary
from .timl_presenter import build_timl_source_summary
from .timl_presenter import build_timl_transform_labels
from .timl_presenter import build_timl_writeback_summary


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


def _draw_workspace_summary(layout, scene_props, controller):
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
    if scene_props.last_timl_analysis_controller_name == controller.name:
        summary_box.label(
            text=build_timl_analysis_summary(
                transform_count=scene_props.last_timl_analysis_transform_count,
                keyframe_count=scene_props.last_timl_analysis_keyframe_count,
                frame_end=scene_props.last_timl_analysis_frame_end,
                warning_count=scene_props.last_timl_analysis_warning_count,
                error_count=scene_props.last_timl_analysis_error_count,
            ),
            icon="CHECKMARK",
        )
        if scene_props.last_timl_writeback_available:
            summary_box.label(
                text=build_timl_edit_policy_summary(
                    value_only_count=scene_props.last_timl_edit_value_only_count,
                    rebuild_capable_count=scene_props.last_timl_edit_rebuild_capable_count,
                    blocked_count=scene_props.last_timl_edit_blocked_count,
                ),
                icon="KEYFRAME",
            )
            summary_box.label(
                text=build_timl_writeback_summary(
                    preserve_raw_count=scene_props.last_timl_writeback_preserve_raw_count,
                    patch_values_count=scene_props.last_timl_writeback_patch_values_count,
                    rebuild_count=scene_props.last_timl_writeback_rebuild_count,
                    blocked_count=scene_props.last_timl_writeback_blocked_count,
                ),
                icon="FILE_REFRESH",
            )


def _draw_workspace_actions(layout):
    button_row = layout.row(align=True)
    button_row.scale_y = 1.1
    button_row.operator("mhw_anim_tools.open_timl_workspace", icon="WORKSPACE")
    button_row.operator("mhw_anim_tools.select_timl_controller", icon="RESTRICT_SELECT_OFF", text="Select Controller")
    button_row.operator("mhw_anim_tools.analyze_timl_controller", icon="FCURVE", text="Analyze")


def _draw_workspace_common_tasks(layout):
    tasks_header, tasks_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_workspace_common_tasks",
        default_closed=False,
    )
    tasks_header.label(text="Common Tasks")
    if tasks_body is None:
        return
    tasks_body.label(
        text="Use this space to inspect TIML meaning, edit values, and drive key timing from Graph Editor.",
        icon="INFO",
    )
    tasks_body.label(text="For empty attached TIML slots, start by creating an EventLoop block here.")


def _controller_has_bindings(controller) -> bool:
    raw_value = controller.get(TIML_BINDINGS_KEY, "") if controller is not None else ""
    if not isinstance(raw_value, str) or not raw_value:
        return False
    try:
        decoded = json.loads(raw_value)
    except json.JSONDecodeError:
        return False
    return bool(decoded)


def _load_controller_bindings(controller) -> dict[str, dict[str, object]]:
    raw_value = controller.get(TIML_BINDINGS_KEY, "") if controller is not None else ""
    if not isinstance(raw_value, str) or not raw_value:
        return {}
    try:
        decoded = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, list):
        return {}
    bindings: dict[str, dict[str, object]] = {}
    for entry in decoded:
        if not isinstance(entry, dict):
            continue
        property_name = str(entry.get("property_name", "") or "")
        if property_name:
            bindings[property_name] = entry
    return bindings


def _field_display_label(transform_item, binding_entry: dict[str, object]) -> str:
    datatype_label = str(getattr(transform_item, "datatype_display", "") or "")
    if datatype_label and not datatype_label.startswith("0x"):
        return datatype_label
    timeline_label = str(getattr(transform_item, "timeline_display", "") or "")
    if timeline_label and not timeline_label.startswith("0x"):
        return timeline_label
    labels = build_timl_transform_labels(
        type_index=int(binding_entry.get("type_index", getattr(transform_item, "type_index", 0))),
        transform_index=int(binding_entry.get("transform_index", getattr(transform_item, "transform_index", 0))),
        timeline_hash=int(binding_entry.get("timeline_parameter_hash", 0)),
        datatype_hash=int(binding_entry.get("datatype_hash", 0)),
        data_type_name=str(binding_entry.get("data_type_name", getattr(transform_item, "data_type_name", "")) or ""),
    )
    return str(labels["datatype_label"] or labels["semantic_label"] or labels["identity_label"])


def _semantic_block_field_rows(scene_props, block, controller):
    bindings_by_name = _load_controller_bindings(controller)
    transforms_by_name = {
        str(item.property_name or ""): item
        for item in scene_props.timl_controller_transforms
        if str(item.property_name or "")
    }
    property_names: list[str] = []
    if str(block.property_names_json or ""):
        try:
            property_names = [str(name) for name in json.loads(block.property_names_json) if str(name)]
        except json.JSONDecodeError:
            property_names = []
    rows = []
    for property_name in property_names:
        transform_item = transforms_by_name.get(property_name)
        binding_entry = bindings_by_name.get(property_name, {})
        if transform_item is None and not binding_entry:
            continue
        display_label = _field_display_label(transform_item, binding_entry)
        raw_datatype = str(
            (getattr(transform_item, "raw_datatype_display", "") if transform_item is not None else "")
            or build_timl_transform_labels(
                type_index=int(binding_entry.get("type_index", 0)),
                transform_index=int(binding_entry.get("transform_index", 0)),
                timeline_hash=int(binding_entry.get("timeline_parameter_hash", 0)),
                datatype_hash=int(binding_entry.get("datatype_hash", 0)),
                data_type_name=str(binding_entry.get("data_type_name", "") or ""),
            )["raw_datatype_label"]
        )
        data_type_name = str(
            (getattr(transform_item, "data_type_name", "") if transform_item is not None else "")
            or binding_entry.get("data_type_name", "")
            or ""
        )
        identity_label = str(
            (getattr(transform_item, "identity_label", "") if transform_item is not None else "")
            or build_timl_transform_labels(
                type_index=int(binding_entry.get("type_index", 0)),
                transform_index=int(binding_entry.get("transform_index", 0)),
            )["identity_label"]
        )
        rows.append(
            {
                "property_name": property_name,
                "display_label": display_label,
                "identity_label": identity_label,
                "raw_datatype": raw_datatype,
                "data_type_name": data_type_name,
                "edit_policy_label": str(getattr(transform_item, "edit_policy_label", "") if transform_item is not None else ""),
                "writeback_status_label": str(getattr(transform_item, "writeback_status_label", "") if transform_item is not None else ""),
                "help_text": timl_editor_field_help_text(
                    str(block.timeline_label or ""),
                    display_label,
                    data_type_name=data_type_name,
                ),
            }
        )
    rows.sort(key=lambda item: (item["identity_label"], item["display_label"]))
    return rows


def _draw_semantic_block_fields(layout, scene_props, block, controller):
    fields_header, fields_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_workspace_semantic_fields",
        default_closed=False,
    )
    fields_header.label(text="Editable Fields")
    if fields_body is None:
        return
    field_rows = _semantic_block_field_rows(scene_props, block, controller)
    if not field_rows:
        fields_body.label(text="No preview fields are available for this TIML block yet.", icon="INFO")
        return
    fields_body.label(text="Edit values here, then adjust timing/keys in Graph Editor.", icon="FCURVE")
    for field in field_rows:
        field_box = fields_body.box()
        title_row = field_box.row(align=True)
        title_row.label(text=field["display_label"], icon="DOT")
        select_op = title_row.operator(
            "mhw_anim_tools.select_timl_property_curves",
            text="",
            icon="RESTRICT_SELECT_OFF",
            emboss=False,
        )
        select_op.property_name = field["property_name"]
        select_op.display_name = field["display_label"]
        if controller is not None and field["property_name"] in controller.keys():
            field_box.prop(controller, f'["{field["property_name"]}"]', text="")
        else:
            field_box.label(text="Backing controller property is missing.", icon="ERROR")
        meta_bits = [field["identity_label"]]
        if field["data_type_name"]:
            meta_bits.append(field["data_type_name"])
        if field["raw_datatype"]:
            meta_bits.append(field["raw_datatype"])
        field_box.label(text=" | ".join(meta_bits))
        if field["edit_policy_label"] or field["writeback_status_label"]:
            status_bits = [bit for bit in (field["edit_policy_label"], field["writeback_status_label"]) if bit]
            field_box.label(text=" / ".join(status_bits), icon="KEYFRAME")
        if field["help_text"]:
            field_box.label(text=field["help_text"], icon="INFO")


def _draw_semantic_tab(layout, scene_props, controller):
    browser_header, browser_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_workspace_semantic_browser",
        default_closed=False,
    )
    browser_header.label(text="Semantic Blocks")
    if browser_body is not None:
        if not scene_props.timl_blocks:
            if controller is not None and not _controller_has_bindings(controller):
                browser_body.label(text="This attached TIML container is currently empty.", icon="INFO")
                browser_body.label(text="Create an EventLoop block to start authoring loop metadata.", icon="IPO_BEZIER")
                action_row = browser_body.row(align=True)
                action_row.scale_y = 1.1
                action_row.operator("mhw_anim_tools.create_timl_eventloop", icon="ADD", text="Create EventLoop")
            else:
                browser_body.label(text="Analyze the controller to build semantic TIML blocks.", icon="INFO")
            return
        browser_body.template_list(
            "MHWANIMTOOLS_UL_timl_blocks",
            "",
            scene_props,
            "timl_blocks",
            scene_props,
            "selected_timl_block_index",
            rows=8,
        )
        browser_body.label(text="Known blocks are grouped first; unknown timelines stay visible and honest.", icon="NODETREE")

    if not (0 <= scene_props.selected_timl_block_index < len(scene_props.timl_blocks)):
        return
    block = scene_props.timl_blocks[scene_props.selected_timl_block_index]
    details_header, details_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_workspace_semantic_details",
        default_closed=False,
    )
    details_header.label(text=block.block_label or "Selected Block")
    if details_body is None:
        return
    title_box = details_body.box()
    title_box.label(text=block.block_label or block.timeline_label or "TIML Block", icon="IPO_BEZIER")
    if block.help_text:
        title_box.label(text=block.help_text)
    action_row = details_body.row(align=True)
    action_row.scale_y = 1.1
    action_row.operator("mhw_anim_tools.select_timl_block_curves", icon="RESTRICT_SELECT_OFF", text="Select Block Curves")
    details_body.label(text=f"Type: {int(block.type_index):02d}")
    if block.known_semantic:
        details_body.label(text=f"Timeline: {block.timeline_label}")
    else:
        details_body.label(text=f"Timeline: {block.raw_timeline_label}")
    details_body.label(text=f"Transforms: {block.transform_count}")
    details_body.label(text=f"Keyframes: {block.keyframe_count}")
    if block.keyframe_count:
        details_body.label(text=f"Frame span: {block.first_frame:.3f} -> {block.last_frame:.3f}")
    if block.datatype_summary:
        details_body.label(text=f"Fields: {block.datatype_summary}")
    if block.edit_policy_summary:
        details_body.label(text=f"Edit policy: {block.edit_policy_summary}", icon="KEYFRAME")
    if block.writeback_summary:
        details_body.label(text=f"Writeback: {block.writeback_summary}", icon="FILE_REFRESH")
    transform_labels = json.loads(block.transform_labels_json) if block.transform_labels_json else []
    if transform_labels:
        transform_box = details_body.box()
        transform_box.label(text="Contained Transforms", icon="LINENUMBERS_ON")
        for label in transform_labels[:8]:
            transform_box.label(text=label)
        if len(transform_labels) > 8:
            transform_box.label(text=f"... and {len(transform_labels) - 8} more")
    _draw_semantic_block_fields(layout, scene_props, block, controller)


def _draw_raw_tab(layout, scene_props, controller):
    browser_header, browser_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_workspace_raw_browser",
        default_closed=False,
    )
    browser_header.label(text="Raw Transforms")
    if browser_body is not None:
        if not scene_props.timl_controller_transforms:
            if controller is not None and not _controller_has_bindings(controller):
                browser_body.label(text="This attached TIML slot is empty right now.", icon="INFO")
                browser_body.label(text="Create an EventLoop block to start authoring loop metadata.")
                action_row = browser_body.row(align=True)
                action_row.scale_y = 1.1
                action_row.operator("mhw_anim_tools.create_timl_eventloop", icon="ADD", text="Create EventLoop")
            else:
                browser_body.label(text="No raw TIML transforms are available yet.", icon="INFO")
                browser_body.label(text="Run Analyze to rebuild the raw TIML browser from the controller action.")
            return
        browser_body.template_list(
            "MHWANIMTOOLS_UL_timl_controller_transforms",
            "",
            scene_props,
            "timl_controller_transforms",
            scene_props,
            "selected_timl_controller_transform_index",
            rows=10,
        )
        browser_body.label(text="This raw view stays close to the actual TIML transform structure.", icon="MODIFIER")

    if not (0 <= scene_props.selected_timl_controller_transform_index < len(scene_props.timl_controller_transforms)):
        return
    transform = scene_props.timl_controller_transforms[scene_props.selected_timl_controller_transform_index]
    details_header, details_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_workspace_raw_details",
        default_closed=False,
    )
    details_header.label(text=transform.identity_label or "Selected Transform")
    if details_body is None:
        return
    title_box = details_body.box()
    title_box.label(text=transform.semantic_label or transform.data_type_name or "Unknown TIML Transform", icon="IPO_BEZIER")
    action_row = details_body.row(align=True)
    action_row.scale_y = 1.1
    action_row.operator("mhw_anim_tools.select_timl_transform_curves", icon="RESTRICT_SELECT_OFF", text="Select Curves")
    details_body.label(text=f"Timeline: {transform.timeline_display or transform.raw_timeline_display or '?'}")
    details_body.label(text=f"Datatype: {transform.datatype_display or transform.raw_datatype_display or '?'}")
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
    if transform.writeback_reason:
        details_body.label(text=transform.writeback_reason)

    metadata_header, metadata_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_workspace_raw_metadata",
        default_closed=True,
    )
    metadata_header.label(text="Raw Metadata")
    if metadata_body is not None:
        if transform.property_name:
            metadata_body.label(text=f"Property: {transform.property_name}")
        if transform.raw_timeline_display:
            metadata_body.label(text=f"Timeline hash: {transform.raw_timeline_display}")
        if transform.raw_datatype_display:
            metadata_body.label(text=f"Datatype hash: {transform.raw_datatype_display}")


def _draw_workspace_diagnostics(layout, scene_props):
    diagnostics_header, diagnostics_body = layout.panel(
        idname="MHWANIMTOOLS_PT_timl_workspace_diagnostics",
        default_closed=True,
    )
    diagnostics_header.label(text="Diagnostics")
    if diagnostics_body is None:
        return
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


def draw_timl_workspace_editor_panel(layout, context):
    scene_props = context.scene.mhw_anim_tools
    controller = timl_controller_for_workspace_panel(context)

    if controller is None:
        layout.label(text="No imported TIML controller found in this scene yet.", icon="INFO")
        row = layout.row(align=True)
        row.scale_y = 1.1
        row.operator("mhw_anim_tools.open_timl_workspace", icon="WORKSPACE")
        return

    _draw_workspace_summary(layout, scene_props, controller)
    _draw_workspace_actions(layout)

    tab_row = layout.row(align=True)
    tab_row.prop(scene_props, "timl_editor_tab", expand=True)

    if scene_props.timl_editor_tab == "SEMANTIC":
        _draw_workspace_common_tasks(layout)
        _draw_semantic_tab(layout, scene_props, controller)
    else:
        _draw_raw_tab(layout, scene_props, controller)

    _draw_workspace_diagnostics(layout, scene_props)
