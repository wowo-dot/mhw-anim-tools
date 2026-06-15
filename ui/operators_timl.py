# -*- coding: utf-8 -*-
"""Focused TIML controller workflow operators."""

import json
from pathlib import Path

import bpy

from ..blender_adapter.timl_metadata import TIML_BINDINGS_KEY
from ..blender_adapter.timl_writeback import assess_timl_controller_shared_payload
from ..blender_adapter.timl_sampling import is_imported_timl_controller
from ..blender_adapter.timl_sampling import sample_timl_controller_action
from ..blender_adapter.timl_actions import seed_eventloop_template_on_controller
from ..blender_adapter.timl_templates import default_event_loop_template_header
from ..blender_adapter.timl_writeback_plan import plan_timl_controller_writeback
from ..core.diagnostics.errors import BinaryFormatError
from ..core.diagnostics.errors import ValidationError
from ..core.formats.lmt.reader import read_lmt_bytes
from ..core.formats.timl.reader import read_timl_data_bytes
from .properties import add_diagnostic
from .properties import clear_diagnostics
from .properties import clear_timl_analysis
from .properties import _populate_timl_controller_transform_items
from .properties import set_timl_edit_policy_summary
from .properties import set_timl_payload_scope_summary
from .properties import set_timl_shared_controller_summary
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


def _timl_workspace_name() -> str:
    return "TIML"


def _largest_area(screen, *, excluding: set[str] | None = None):
    excluding = excluding or set()
    candidates = [
        area
        for area in getattr(screen, "areas", ())
        if getattr(area, "type", "") not in excluding
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda area: int(getattr(area, "width", 0)) * int(getattr(area, "height", 0)))


def _graph_editor_areas(screen):
    return tuple(area for area in getattr(screen, "areas", ()) if getattr(area, "type", "") == "GRAPH_EDITOR")


def _dopesheet_areas(screen):
    return tuple(area for area in getattr(screen, "areas", ()) if getattr(area, "type", "") == "DOPESHEET_EDITOR")


def _configure_timl_action_editor(screen):
    areas = list(_dopesheet_areas(screen))
    if not areas:
        candidates = [
            area
            for area in getattr(screen, "areas", ())
            if getattr(area, "type", "") not in {
                "OUTLINER",
                "TOPBAR",
                "STATUSBAR",
                "PREFERENCES",
                "GRAPH_EDITOR",
                "PROPERTIES",
            }
        ]
        if candidates:
            bottom_most = min(
                candidates,
                key=lambda area: (
                    int(getattr(area, "y", 0)),
                    int(getattr(area, "width", 0)) * int(getattr(area, "height", 0)),
                ),
            )
            bottom_most.type = "DOPESHEET_EDITOR"
            areas = list(_dopesheet_areas(screen))
    for area in areas:
        for space in getattr(area, "spaces", ()):
            if getattr(space, "type", "") != "DOPESHEET_EDITOR":
                continue
            if hasattr(space, "ui_mode"):
                try:
                    space.ui_mode = "ACTION"
                except TypeError:
                    pass
            if hasattr(space, "mode"):
                try:
                    space.mode = "ACTION"
                except TypeError:
                    pass
    return bool(areas)


def _configure_timl_workspace(window):
    screen = getattr(window, "screen", None)
    if screen is None:
        return False
    if not _graph_editor_areas(screen):
        graph_area = _largest_area(screen, excluding={"OUTLINER", "TOPBAR", "STATUSBAR", "PREFERENCES"})
        if graph_area is not None:
            graph_area.type = "GRAPH_EDITOR"
    for area in _graph_editor_areas(screen):
        for space in getattr(area, "spaces", ()):
            if getattr(space, "type", "") != "GRAPH_EDITOR":
                continue
            if hasattr(space, "mode"):
                try:
                    space.mode = "FCURVES"
                except TypeError:
                    pass
            if hasattr(space, "show_region_ui"):
                space.show_region_ui = True
    _configure_timl_action_editor(screen)
    return bool(_graph_editor_areas(screen))


def _ensure_timl_workspace(context):
    window = getattr(context, "window", None)
    if window is None:
        return False, "No active Blender window is available."

    workspace = bpy.data.workspaces.get(_timl_workspace_name())
    if workspace is None:
        try:
            bpy.ops.workspace.duplicate()
        except RuntimeError as exc:
            return False, f"Could not create a TIML workspace: {exc}"
        workspace = window.workspace
        workspace.name = _timl_workspace_name()
    window.workspace = workspace
    configured = _configure_timl_workspace(window)
    if not configured:
        return False, "TIML workspace opened, but no Graph Editor area could be prepared."
    return True, ""


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


def _selected_controller_transform(scene_props):
    items = scene_props.timl_controller_transforms
    index = int(scene_props.selected_timl_controller_transform_index)
    if 0 <= index < len(items):
        return items[index]
    return None


def _selected_timl_block(scene_props):
    items = scene_props.timl_blocks
    index = int(scene_props.selected_timl_block_index)
    if 0 <= index < len(items):
        return items[index]
    return None


def _select_controller_curves_by_property_names(controller, property_names):
    action = controller.animation_data.action if controller.animation_data else None
    if action is None:
        return 0
    property_name_set = {str(name) for name in property_names if str(name)}
    if not property_name_set:
        return 0
    match_count = 0
    for fcurve in getattr(action, "fcurves", ()):
        data_path = str(getattr(fcurve, "data_path", ""))
        selected = any(data_path == f'["{property_name}"]' for property_name in property_name_set)
        try:
            fcurve.select = selected
        except AttributeError:
            pass
        for point in getattr(fcurve, "keyframe_points", ()):
            point.select_control_point = selected
            point.select_left_handle = selected
            point.select_right_handle = selected
        if selected:
            match_count += 1
    return match_count


def _controller_has_timl_bindings(controller) -> bool:
    raw_value = controller.get(TIML_BINDINGS_KEY, "") if controller is not None else ""
    if not isinstance(raw_value, str) or not raw_value:
        return False
    try:
        decoded = json.loads(raw_value)
    except json.JSONDecodeError:
        return False
    return bool(decoded)


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
        shared_payload_assessment = None
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
                    if source_lmt is not None:
                        shared_payload_assessment = assess_timl_controller_shared_payload(
                            controller,
                            bpy.data.objects,
                            source_lmt=source_lmt,
                            source_bytes=source_bytes,
                        )
            except OSError as exc:
                add_diagnostic(
                    scene_props,
                    "WARNING",
                    "timl.writeback",
                    f"Could not read source TIML container for writeback planning: {exc}",
                )
            except (BinaryFormatError, ValidationError, ValueError, TypeError) as exc:
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
        if shared_payload_assessment is not None:
            for diagnostic in shared_payload_assessment.diagnostics:
                add_diagnostic(scene_props, diagnostic.level, diagnostic.source, diagnostic.message)
            set_timl_payload_scope_summary(
                scene_props,
                shared_payload_assessment.shared_action_ids,
            )
            set_timl_shared_controller_summary(scene_props, shared_payload_assessment)
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


class MHWANIMTOOLS_OT_open_timl_workspace(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.open_timl_workspace"
    bl_label = "Open TIML Workspace"
    bl_description = "Open or create the dedicated TIML workspace flow around Graph Editor"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        if controller is not None:
            scene_props.timl_controller = controller
            _set_active_controller(context, controller)
        success, message = _ensure_timl_workspace(context)
        if not success:
            scene_props.last_status = message
            add_diagnostic(scene_props, "WARNING", "timl.workspace", message)
            self.report({"WARNING"}, message)
            return {"CANCELLED"}
        if controller is not None and scene_props.last_timl_analysis_controller_name != controller.name:
            try:
                bpy.ops.mhw_anim_tools.analyze_timl_controller()
            except RuntimeError:
                pass
        if controller is not None and not _controller_has_timl_bindings(controller):
            scene_props.timl_editor_tab = "SEMANTIC"
        controller_name = scene_props.timl_controller.name if scene_props.timl_controller is not None else "none"
        scene_props.last_status = f"Opened TIML workspace for controller {controller_name}."
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


class MHWANIMTOOLS_OT_select_timl_block_curves(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.select_timl_block_curves"
    bl_label = "Select TIML Block Curves"
    bl_description = "Select all controller curves that belong to the currently highlighted TIML block"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        if controller is None:
            scene_props.last_status = "Choose an imported TIML controller before selecting TIML block curves."
            add_diagnostic(scene_props, "ERROR", "timl.controller", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        block = _selected_timl_block(scene_props)
        if block is None or not str(block.property_names_json or ""):
            scene_props.last_status = "Choose a semantic TIML block first."
            add_diagnostic(scene_props, "ERROR", "timl.block", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        try:
            property_names = json.loads(block.property_names_json)
        except json.JSONDecodeError:
            property_names = []
        match_count = _select_controller_curves_by_property_names(controller, property_names)
        if match_count <= 0:
            scene_props.last_status = f"No preview curves were found for {block.block_label or 'this block'}."
            add_diagnostic(scene_props, "WARNING", "timl.block", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        _set_active_controller(context, controller)
        scene_props.last_status = (
            f"Selected {match_count} curve(s) for {block.block_label or 'the selected TIML block'}. "
            "Use Graph Editor for key edits."
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_select_timl_property_curves(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.select_timl_property_curves"
    bl_label = "Select TIML Property Curves"
    bl_description = "Select the controller curves for one TIML field/property"

    property_name: bpy.props.StringProperty(name="Property Name", default="")
    display_name: bpy.props.StringProperty(name="Display Name", default="")

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        if controller is None:
            scene_props.last_status = "Choose an imported TIML controller before selecting TIML field curves."
            add_diagnostic(scene_props, "ERROR", "timl.controller", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        property_name = str(self.property_name or "")
        if not property_name:
            scene_props.last_status = "No TIML property name was provided for curve selection."
            add_diagnostic(scene_props, "ERROR", "timl.field", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        match_count = _select_controller_curves_by_property_names(controller, [property_name])
        if match_count <= 0:
            field_name = str(self.display_name or property_name)
            scene_props.last_status = f"No preview curves were found for {field_name}."
            add_diagnostic(scene_props, "WARNING", "timl.field", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        _set_active_controller(context, controller)
        field_name = str(self.display_name or property_name)
        scene_props.last_status = f"Selected {match_count} curve(s) for {field_name}."
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_select_timl_transform_curves(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.select_timl_transform_curves"
    bl_label = "Select TIML Transform Curves"
    bl_description = "Select the controller curves for the currently highlighted TIML transform"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        if controller is None:
            scene_props.last_status = "Choose an imported TIML controller before selecting TIML curves."
            add_diagnostic(scene_props, "ERROR", "timl.controller", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        transform = _selected_controller_transform(scene_props)
        if transform is None or not str(transform.property_name or ""):
            scene_props.last_status = "Choose a TIML transform with imported preview curves first."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        action = controller.animation_data.action if controller.animation_data else None
        if action is None:
            scene_props.last_status = "The selected TIML controller has no active action to inspect."
            add_diagnostic(scene_props, "ERROR", "timl.controller", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        match_count = _select_controller_curves_by_property_names(controller, [transform.property_name])

        if match_count <= 0:
            scene_props.last_status = f"No preview curves were found for {transform.semantic_label or transform.property_name}."
            add_diagnostic(scene_props, "WARNING", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        _set_active_controller(context, controller)
        scene_props.last_status = (
            f"Selected {match_count} curve(s) for "
            f"{transform.semantic_label or transform.property_name}. Open Graph Editor to edit keys."
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_create_timl_eventloop(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.create_timl_eventloop"
    bl_label = "Create EventLoop"
    bl_description = "Seed a conservative EventLoop block into an empty attached TIML container"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        if controller is None:
            scene_props.last_status = "Choose an imported TIML controller before creating an EventLoop."
            add_diagnostic(scene_props, "ERROR", "timl.controller", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        metadata = getattr(sample_timl_controller_action(controller), "metadata", None)
        if metadata is not None and getattr(metadata, "transform_count", 0):
            scene_props.last_status = "This TIML controller already contains imported transforms. EventLoop creation is currently only supported for empty attached TIML containers."
            add_diagnostic(scene_props, "ERROR", "timl.template", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        source_lmt = str(controller.get("mhw_anim_tools_timl_source_lmt", "") or "")
        source_offset = int(controller.get("mhw_anim_tools_timl_source_offset", 0) or 0)
        entry_id = int(controller.get("mhw_anim_tools_timl_entry_id", 0) or 0)
        if not source_lmt or source_offset <= 0:
            scene_props.last_status = "The selected TIML controller is missing source LMT metadata."
            add_diagnostic(scene_props, "ERROR", "timl.template", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        try:
            source_path = Path(source_lmt)
            source_bytes = source_path.read_bytes()
            lmt = read_lmt_bytes(source_bytes, source_name=str(source_path))
            source_action = next((action for action in lmt.actions if int(action.id) == entry_id), None)
            if source_action is None:
                raise ValueError(f"Could not find source action {entry_id:03d} in {source_path.name}.")
            source_entry = read_timl_data_bytes(
                source_bytes,
                data_offset=source_offset,
                source_name=f"{source_path}#timl",
                entry_id=entry_id,
            )
        except (OSError, ValueError, BinaryFormatError) as exc:
            scene_props.last_status = f"Could not load source TIML metadata: {exc}"
            add_diagnostic(scene_props, "ERROR", "timl.template", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        if any(getattr(type_entry, "transforms", ()) for type_entry in getattr(source_entry, "types", ())):
            scene_props.last_status = "This source action already has TIML transforms. EventLoop creation currently targets empty attached TIML containers only."
            add_diagnostic(scene_props, "ERROR", "timl.template", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        frame_end = max(0.0, float(int(source_action.header.frame_count) - 1))
        template_header = default_event_loop_template_header(
            source_lmt=str(source_path),
            entry_id=entry_id,
            animation_length=frame_end,
            data_index_a=int(getattr(source_entry, "data_index_a", 0)),
            data_index_b=int(getattr(source_entry, "data_index_b", 0)),
            loop_start_point=float(getattr(source_entry, "loop_start_point", 0.0)),
            loop_control=int(getattr(source_entry, "loop_control", 0)),
            label_hash=int(getattr(source_entry, "label_hash", 0)),
        )
        seed_eventloop_template_on_controller(
            controller,
            source_path=str(source_path),
            entry_id=entry_id,
            source_offset=source_offset,
            animation_length=template_header.animation_length,
            data_index_a=template_header.data_index_a,
            data_index_b=template_header.data_index_b,
            loop_start_point=template_header.loop_start_point,
            loop_control=template_header.loop_control,
            label_hash=template_header.label_hash,
        )
        scene_props.timl_controller = controller
        scene_props.timl_editor_tab = "SEMANTIC"
        clear_timl_analysis(scene_props)
        try:
            bpy.ops.mhw_anim_tools.analyze_timl_controller()
        except RuntimeError:
            pass
        scene_props.last_status = (
            f"Created an EventLoop TIML block for entry {entry_id:03d}. "
            "Use the Semantic tab and Graph Editor to adjust the loop fields."
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


classes = (
    MHWANIMTOOLS_OT_analyze_timl_controller,
    MHWANIMTOOLS_OT_open_timl_workspace,
    MHWANIMTOOLS_OT_select_timl_controller,
    MHWANIMTOOLS_OT_select_timl_block_curves,
    MHWANIMTOOLS_OT_select_timl_property_curves,
    MHWANIMTOOLS_OT_select_timl_transform_curves,
    MHWANIMTOOLS_OT_create_timl_eventloop,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
