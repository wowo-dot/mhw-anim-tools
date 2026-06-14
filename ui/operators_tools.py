# -*- coding: utf-8 -*-
"""Small utility operators for the milestone-one UI."""

import bpy

from ..integration.model_editor import choose_best_armature
from ..integration.model_editor import get_workspace_summary


class MHWANIMTOOLS_OT_refresh_workspace(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.refresh_workspace"
    bl_label = "Refresh Workspace"
    bl_description = "Refresh detected MHW workspace information"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        scene_props.target_armature = choose_best_armature(context, scene_props.target_armature)
        summary = get_workspace_summary(context, scene_props.target_armature)
        addon_status = summary["addon_status"]
        if addon_status["enabled"]:
            mode = "MHW_Model_Editor active"
        elif addon_status["available"]:
            mode = "MHW_Model_Editor installed but disabled"
        else:
            mode = "Standalone mode"
        target_name = summary["target_armature"].name if summary["target_armature"] is not None else "none"
        scene_props.last_status = (
            f"{mode}; candidate armatures={summary['candidate_count']}; target={target_name}"
        )
        return {"FINISHED"}


class MHWANIMTOOLS_OT_use_active_armature(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.use_active_armature"
    bl_label = "Use Active"
    bl_description = "Use the active MHW-style armature as the current target"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        target = choose_best_armature(context)
        if target is None:
            scene_props.last_status = "No active MHW-style armature found."
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        scene_props.target_armature = target
        scene_props.last_status = f"Using {target.name} as target armature."
        return {"FINISHED"}


class MHWANIMTOOLS_OT_auto_detect_armature(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.auto_detect_armature"
    bl_label = "Auto Detect"
    bl_description = "Pick the best detected MHW-style armature in the scene"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        target = choose_best_armature(context, scene_props.target_armature)
        if target is None:
            scene_props.last_status = "No MHW-style armature detected."
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        scene_props.target_armature = target
        scene_props.last_status = f"Auto-detected {target.name}."
        return {"FINISHED"}


classes = (
    MHWANIMTOOLS_OT_refresh_workspace,
    MHWANIMTOOLS_OT_use_active_armature,
    MHWANIMTOOLS_OT_auto_detect_armature,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
