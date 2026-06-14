# -*- coding: utf-8 -*-
"""UIList definitions for reviewable import sessions."""

import bpy


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
            row.label(text=f"{item.track_count} tracks")
            if item.track_breakdown:
                row.label(text=item.track_breakdown)
            row.label(text="TIML" if item.has_timl else "-", icon="CHECKMARK" if item.has_timl else "REMOVE")
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


classes = (
    MHWANIMTOOLS_UL_lmt_entries,
    MHWANIMTOOLS_UL_lmt_tracks,
    MHWANIMTOOLS_UL_diagnostics,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
