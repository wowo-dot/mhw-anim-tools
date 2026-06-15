# -*- coding: utf-8 -*-
"""Blender panel classes for the main workspace and TIML inspector."""

import bpy
import traceback

from .panel_sections import draw_timl_inspector_panel
from .panel_sections import draw_workspace_panel
from .panel_sections import timl_controller_for_object_panel
from .timl_workspace_sections import draw_timl_workspace_editor_panel


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
        draw_workspace_panel(layout, context)


class MHWANIMTOOLS_PT_timl_inspector(bpy.types.Panel):
    bl_label = "TIML Inspector (Fallback)"
    bl_idname = "MHWANIMTOOLS_PT_timl_inspector"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    @classmethod
    def poll(cls, context):
        del cls
        return timl_controller_for_object_panel(context) is not None

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        draw_timl_inspector_panel(layout, context)


class MHWANIMTOOLS_PT_timl_workspace_editor(bpy.types.Panel):
    bl_label = "TIML Workspace"
    bl_idname = "MHWANIMTOOLS_PT_timl_workspace_editor"
    bl_space_type = "GRAPH_EDITOR"
    bl_region_type = "UI"
    bl_category = "MHW Anim"

    @classmethod
    def poll(cls, context):
        del cls, context
        return True

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        try:
            draw_timl_workspace_editor_panel(layout, context)
        except Exception as exc:  # pragma: no cover - Blender UI fallback
            print("MHW Anim Tools TIML workspace draw failed:")
            traceback.print_exc()
            error_box = layout.box()
            error_box.label(text="TIML workspace UI failed to draw.", icon="ERROR")
            error_box.label(text=str(exc))
            error_box.label(text="Reload Scripts after updating the add-on.", icon="INFO")


classes = (
    MHWANIMTOOLS_PT_workspace,
    MHWANIMTOOLS_PT_timl_inspector,
    MHWANIMTOOLS_PT_timl_workspace_editor,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
