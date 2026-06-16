# -*- coding: utf-8 -*-
"""UIList definitions for reviewable import sessions."""

import bpy

from .timl_labels import timl_edit_policy_icon
from .timl_labels import timl_writeback_status_icon


class MHWANIMTOOLS_UL_lmt_entries(bpy.types.UIList):
    bl_idname = "MHWANIMTOOLS_UL_lmt_entries"

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
    ):
        del context, icon, active_data, active_propname, index
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.label(text=f"{item.entry_id:03d}")
            row.label(text=f"{item.frame_count}f")
            offset_text = item.timl_source_offset_display or ("empty" if item.has_timl else "-")
            row.label(text=offset_text)
            if item.has_timl:
                row.label(text=f"{item.timl_type_count}t/{item.timl_transform_count}tr/{item.timl_keyframe_count}k")
            else:
                row.label(text="-")
            icon_name = "CHECKMARK" if item.has_timl else "REMOVE"
            if item.timl_parse_error:
                icon_name = "ERROR"
            row.label(text="", icon=icon_name)
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=str(item.entry_id))


class MHWANIMTOOLS_UL_lmt_tracks(bpy.types.UIList):
    bl_idname = "MHWANIMTOOLS_UL_lmt_tracks"

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
    ):
        del context, data, icon, active_data, active_propname, index
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.label(text=f"T{item.track_index:02d}")
            row.label(text=item.usage_label or f"Usage {item.usage}")
            row.label(text=f"Bone {item.bone_id}")
            row.label(text=item.buffer_code or f"B{item.buffer_type}")
            if item.decode_error:
                row.label(text="Decode error", icon="ERROR")
            else:
                key_text = "?" if item.decoded_key_count < 0 else str(item.decoded_key_count)
                row.label(text=f"{key_text} keys")
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=str(item.track_index))


class MHWANIMTOOLS_UL_timl_transforms(bpy.types.UIList):
    bl_idname = "MHWANIMTOOLS_UL_timl_transforms"

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
    ):
        del context, data, icon, active_data, active_propname, index
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.label(text=item.identity_label or f"Type {item.type_index:02d} / Transform {item.transform_index:02d}")
            row.label(text=item.semantic_label or item.timeline_parameter_label or item.datatype_label or "?")
            row.label(text=f"{item.keyframe_count} keys")
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=f"{item.type_index}:{item.transform_index}")


class MHWANIMTOOLS_UL_timl_file_entries(bpy.types.UIList):
    bl_idname = "MHWANIMTOOLS_UL_timl_file_entries"

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
    ):
        del context, data, icon, active_data, active_propname, index
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.label(text=f"{item.entry_id:03d}")
            row.label(text=item.offset_display or "-")
            if item.has_data:
                row.label(text=f"{item.type_count}t/{item.transform_count}tr/{item.keyframe_count}k")
            else:
                row.label(text="empty")
            icon_name = "CHECKMARK" if item.has_data else "REMOVE"
            if item.parse_error:
                icon_name = "ERROR"
            row.label(text="", icon=icon_name)
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=str(item.entry_id))


class MHWANIMTOOLS_UL_diagnostics(bpy.types.UIList):
    bl_idname = "MHWANIMTOOLS_UL_diagnostics"

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
    ):
        del context, data, icon, active_data, active_propname, index
        icon_name = {"INFO": "INFO", "WARNING": "ERROR", "ERROR": "CANCEL"}.get(item.level, "INFO")
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.label(text=item.level, icon=icon_name)
            if item.source:
                row.label(text=item.source)
            row.label(text=item.message)
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.level[:1])


class MHWANIMTOOLS_UL_timl_blocks(bpy.types.UIList):
    bl_idname = "MHWANIMTOOLS_UL_timl_blocks"

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
    ):
        del context, data, icon, active_data, active_propname, index
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.label(text=f"T{item.type_index:02d}")
            row.label(text=item.block_label or item.timeline_label or item.raw_timeline_label or "?")
            row.label(text=f"{item.transform_count} tr")
            row.label(text=f"{item.keyframe_count} keys")
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=str(item.type_index))


class MHWANIMTOOLS_UL_timl_controller_transforms(bpy.types.UIList):
    bl_idname = "MHWANIMTOOLS_UL_timl_controller_transforms"

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
    ):
        del context, data, icon, active_data, active_propname, index
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.label(text=item.identity_label or f"T{item.type_index:02d}:X{item.transform_index:02d}")
            row.label(text=item.semantic_label or item.timeline_display or item.raw_timeline_display or "?")
            row.label(text=item.data_type_name or "?")
            row.label(text=f"{item.keyframe_count} keys")
            if not str(item.property_name or ""):
                row.label(text="Needs Preview", icon="INFO")
            elif item.edit_policy_label:
                row.label(text=item.edit_policy_label, icon=timl_edit_policy_icon(item.edit_policy_code))
            elif item.writeback_status_label:
                row.label(text=item.writeback_status_label, icon=timl_writeback_status_icon(item.writeback_status_code))
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=f"{item.type_index}:{item.transform_index}")


classes = (
    MHWANIMTOOLS_UL_lmt_entries,
    MHWANIMTOOLS_UL_lmt_tracks,
    MHWANIMTOOLS_UL_timl_transforms,
    MHWANIMTOOLS_UL_timl_file_entries,
    MHWANIMTOOLS_UL_diagnostics,
    MHWANIMTOOLS_UL_timl_blocks,
    MHWANIMTOOLS_UL_timl_controller_transforms,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
