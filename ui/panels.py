# -*- coding: utf-8 -*-
"""Blender panel classes for the main workspace and TIML inspector."""

import bpy

from .panel_sections import draw_timl_inspector_panel
from .panel_sections import draw_workspace_panel
from .panel_sections import timl_controller_for_object_panel


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
    bl_label = "TIML Inspector"
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


classes = (
    MHWANIMTOOLS_PT_workspace,
    MHWANIMTOOLS_PT_timl_inspector,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
