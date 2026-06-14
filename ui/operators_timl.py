# -*- coding: utf-8 -*-
"""Focused TIML controller workflow operators."""

import bpy

from ..blender_adapter.timl_sampling import is_imported_timl_controller
from ..blender_adapter.timl_sampling import sample_timl_controller_action
from .properties import add_diagnostic
from .properties import clear_diagnostics
from .properties import clear_timl_analysis


def _resolve_timl_controller(context):
    scene_props = context.scene.mhw_anim_tools
    controller = scene_props.timl_controller
    if is_imported_timl_controller(controller):
        return controller

    active_object = getattr(context, "active_object", None)
    if is_imported_timl_controller(active_object):
        scene_props.timl_controller = active_object
        return active_object

    if scene_props.last_imported_timl_object_name:
        candidate = bpy.data.objects.get(scene_props.last_imported_timl_object_name)
        if is_imported_timl_controller(candidate):
            scene_props.timl_controller = candidate
            return candidate

    for candidate in bpy.data.objects:
        if is_imported_timl_controller(candidate):
            scene_props.timl_controller = candidate
            return candidate
    return None


class MHWANIMTOOLS_OT_analyze_timl_controller(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.analyze_timl_controller"
    bl_label = "Analyze TIML Controller"
    bl_description = "Sample the imported TIML controller action back into typed TIML value space"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        clear_diagnostics(scene_props)
        clear_timl_analysis(scene_props)

        controller = _resolve_timl_controller(context)
        if controller is None:
            scene_props.last_status = "Choose an imported TIML controller object before analyzing TIML curves."
            add_diagnostic(scene_props, "ERROR", "timl.controller", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        result = sample_timl_controller_action(controller)
        for diagnostic in result.diagnostics:
            add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)

        metadata = result.metadata
        if metadata is not None:
            scene_props.timl_controller = controller
            scene_props.last_timl_analysis_controller_name = metadata.carrier_name
            scene_props.last_timl_analysis_action_name = metadata.action_name
        scene_props.last_timl_analysis_transform_count = result.sampled_transform_count
        scene_props.last_timl_analysis_keyframe_count = result.keyframe_count
        scene_props.last_timl_analysis_frame_end = result.frame_end
        scene_props.last_timl_analysis_warning_count = result.warning_count
        scene_props.last_timl_analysis_error_count = result.error_count

        if result.error_count:
            scene_props.last_status = (
                f"TIML analysis failed: {result.error_count} error(s), {result.warning_count} warning(s)."
            )
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        action_name = metadata.action_name if metadata is not None else ""
        scene_props.last_status = (
            f"Analyzed {action_name}: "
            f"transforms={result.sampled_transform_count}, "
            f"keyframes={result.keyframe_count}, "
            f"warnings={result.warning_count}, "
            f"frames=0->{result.frame_end}"
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


classes = (MHWANIMTOOLS_OT_analyze_timl_controller,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
