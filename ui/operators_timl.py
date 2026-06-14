# -*- coding: utf-8 -*-
"""Focused TIML controller workflow operators."""

from pathlib import Path

import bpy

from ..blender_adapter.timl_writeback import shared_source_action_ids
from ..blender_adapter.timl_sampling import is_imported_timl_controller
from ..blender_adapter.timl_sampling import sample_timl_controller_action
from ..blender_adapter.timl_writeback_plan import plan_timl_controller_writeback
from ..core.formats.lmt.reader import read_lmt_bytes
from .properties import add_diagnostic
from .properties import clear_diagnostics
from .properties import clear_timl_analysis
from .properties import _populate_timl_controller_transform_items
from .properties import set_timl_edit_policy_summary
from .properties import set_timl_payload_scope_summary
from .properties import set_timl_writeback_summary


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


def _set_active_controller(context, controller):
    if controller is None:
        return
    for candidate in context.selected_objects:
        candidate.select_set(False)
    controller.select_set(True)
    context.view_layer.objects.active = controller


def _build_source_backed_writeback_plan(controller, metadata, *, source_bytes: bytes):
    if metadata is None:
        return None
    source_lmt = str(getattr(metadata, "source_lmt", "") or "")
    if not source_lmt:
        return None
    return plan_timl_controller_writeback(
        controller,
        source_bytes=source_bytes,
        source_name=f"{source_lmt}#timl",
        entry_id=int(getattr(metadata, "entry_id", 0)),
        source_offset=int(getattr(metadata, "source_offset", 0)),
    )


def _load_source_context(metadata):
    if metadata is None:
        return None, None
    source_lmt = str(getattr(metadata, "source_lmt", "") or "")
    if not source_lmt:
        return None, None
    source_path = Path(source_lmt)
    if not source_path.is_file():
        raise FileNotFoundError(f"TIML source LMT is missing: {source_lmt}")
    source_bytes = source_path.read_bytes()
    source_lmt_file = read_lmt_bytes(source_bytes, source_name=str(source_path))
    return source_bytes, source_lmt_file


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
        writeback_plan = None
        source_lmt = None
        source_bytes = None
        if not result.error_count:
            try:
                source_bytes, source_lmt = _load_source_context(metadata)
                if source_bytes is not None:
                    writeback_plan = _build_source_backed_writeback_plan(
                        controller,
                        metadata,
                        source_bytes=source_bytes,
                    )
            except OSError as exc:
                add_diagnostic(
                    scene_props,
                    "WARNING",
                    "timl.writeback",
                    f"Could not read source TIML container for writeback planning: {exc}",
                )
            except Exception as exc:
                add_diagnostic(
                    scene_props,
                    "WARNING",
                    "timl.writeback",
                    f"Could not build source-backed TIML writeback plan: {exc}",
                )
        if writeback_plan is not None:
            for diagnostic in writeback_plan.diagnostics:
                add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)
            set_timl_writeback_summary(
                scene_props,
                [item.status for item in writeback_plan.transform_plans],
            )
            set_timl_edit_policy_summary(
                scene_props,
                writeback_plan.transform_plans,
            )
            if source_lmt is not None and metadata is not None:
                set_timl_payload_scope_summary(
                    scene_props,
                    shared_source_action_ids(source_lmt, int(getattr(metadata, "source_offset", 0))),
                )
        _populate_timl_controller_transform_items(
            scene_props,
            sampled_result=result,
            writeback_plan=writeback_plan,
        )
        scene_props.last_timl_analysis_warning_count = sum(
            1 for item in scene_props.diagnostics if item.level == "WARNING"
        )
        scene_props.last_timl_analysis_error_count = sum(
            1 for item in scene_props.diagnostics if item.level == "ERROR"
        )

        if scene_props.last_timl_analysis_error_count:
            scene_props.last_status = (
                "TIML analysis failed: "
                f"{scene_props.last_timl_analysis_error_count} error(s), "
                f"{scene_props.last_timl_analysis_warning_count} warning(s)."
            )
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        action_name = metadata.action_name if metadata is not None else ""
        scene_props.last_status = (
            f"Analyzed {action_name}: "
            f"transforms={result.sampled_transform_count}, "
            f"keyframes={result.keyframe_count}, "
            f"warnings={scene_props.last_timl_analysis_warning_count}, "
            f"frames=0->{result.frame_end}"
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_select_timl_controller(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.select_timl_controller"
    bl_label = "Select TIML Controller"
    bl_description = "Select and activate the imported TIML controller object for Properties/Graph inspection"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        if controller is None:
            scene_props.last_status = "Choose an imported TIML controller before trying to inspect it."
            add_diagnostic(scene_props, "ERROR", "timl.controller", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        scene_props.timl_controller = controller
        _set_active_controller(context, controller)
        scene_props.last_status = f"Selected {controller.name} for TIML inspection."
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


classes = (
    MHWANIMTOOLS_OT_analyze_timl_controller,
    MHWANIMTOOLS_OT_select_timl_controller,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
