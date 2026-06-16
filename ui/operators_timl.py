# -*- coding: utf-8 -*-
"""Focused TIML controller workflow operators."""

import json
from pathlib import Path

import bpy

from ..blender_adapter.timl_authoring import append_timl_binding
from ..blender_adapter.timl_authoring import clone_binding_preview_fcurves
from ..blender_adapter.timl_authoring import create_binding_preview_fcurves
from ..blender_adapter.timl_authoring import default_preview_value_for_data_type
from ..blender_adapter.timl_authoring import ensure_binding_preview_property
from ..blender_adapter.timl_authoring import ensure_timl_header_props
from ..blender_adapter.timl_authoring import load_timl_bindings_raw
from ..blender_adapter.timl_authoring import remove_binding_preview_fcurves
from ..blender_adapter.timl_authoring import remove_timl_binding
from ..blender_adapter.timl_authoring import save_timl_bindings_raw
from ..blender_adapter.timl_authoring import sync_timl_binding_meta_props_from_bindings
from ..blender_adapter.timl_authoring import timl_header_state_from_controller
from ..blender_adapter.timl_metadata import TIML_BINDINGS_KEY
from ..blender_adapter.timl_writeback import assess_timl_controller_shared_payload
from ..blender_adapter.timl_sampling import extract_timl_controller_metadata
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


TIML_DATA_TYPE_ITEMS = (
    ("0", "sint32", ""),
    ("1", "uint32", ""),
    ("2", "float", ""),
    ("3", "color_rgba8", ""),
    ("4", "bool_uint32", ""),
)


def _data_type_name_for_key(key: str) -> str:
    for item_key, label, _description in TIML_DATA_TYPE_ITEMS:
        if str(item_key) == str(key):
            return str(label)
    return str(key)


def _data_type_key_for_name(name: str, *, fallback: str = "1") -> str:
    for item_key, label, _description in TIML_DATA_TYPE_ITEMS:
        if str(label) == str(name):
            return str(item_key)
    return str(fallback)


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


def _parse_hex_u32(text: str, *, fallback: int = 0) -> int:
    text = str(text or "").strip()
    if not text:
        return int(fallback) & 0xFFFFFFFF
    if text.lower().startswith("0x"):
        return int(text, 16) & 0xFFFFFFFF
    return int(text, 16) & 0xFFFFFFFF


def _format_hex_u32(value: int) -> str:
    return f"0x{int(value) & 0xFFFFFFFF:08X}"


def _controller_action(controller):
    animation_data = getattr(controller, "animation_data", None)
    return getattr(animation_data, "action", None) if animation_data is not None else None


def _set_action_transform_count(controller, count: int):
    action = _controller_action(controller)
    if action is not None:
        action["mhw_anim_tools_timl_transform_count"] = int(count)


def _controller_for_selected_entry(scene_props):
    if not scene_props.lmt_entries:
        return None
    entry = scene_props.lmt_entries[min(scene_props.selected_entry_index, len(scene_props.lmt_entries) - 1)]
    source_path = str(scene_props.last_lmt_path or "")
    for candidate in bpy.data.objects:
        if not is_imported_timl_controller(candidate):
            continue
        metadata = extract_timl_controller_metadata(candidate)
        if str(metadata.source_lmt or "") != source_path:
            continue
        if int(metadata.entry_id) == int(entry.entry_id):
            return candidate
    return None


def _binding_for_selected_transform(controller, scene_props):
    transform = _selected_controller_transform(scene_props)
    if transform is None:
        return None
    property_name = str(transform.property_name or "")
    for binding in load_timl_bindings_raw(controller):
        if str(binding["property_name"]) == property_name:
            return binding
    return None


def _bindings_for_selected_type(controller, scene_props):
    block = _selected_timl_block(scene_props)
    if block is None:
        return []
    return [
        binding
        for binding in load_timl_bindings_raw(controller)
        if int(binding["type_index"]) == int(block.type_index)
    ]


def _refresh_timl_controller_after_edit(context, controller):
    scene_props = context.scene.mhw_anim_tools
    scene_props.timl_controller = controller
    _set_active_controller(context, controller)
    try:
        bpy.ops.mhw_anim_tools.analyze_timl_controller()
    except RuntimeError:
        clear_timl_analysis(scene_props)



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


def _selected_entry(scene_props):
    items = scene_props.lmt_entries
    index = int(scene_props.selected_entry_index)
    if 0 <= index < len(items):
        return items[index]
    return None


def _find_transform_item_index(scene_props, property_name: str) -> int:
    property_name = str(property_name or "")
    for index, item in enumerate(scene_props.timl_controller_transforms):
        if str(item.property_name or "") == property_name:
            return index
    return -1


def _find_type_item_index(scene_props, type_index: int) -> int:
    for index, item in enumerate(scene_props.timl_blocks):
        if int(item.type_index) == int(type_index):
            return index
    return -1


def _select_workspace_identity(scene_props, *, property_name: str = "", type_index: int | None = None):
    if property_name:
        transform_index = _find_transform_item_index(scene_props, property_name)
        if transform_index >= 0:
            scene_props.selected_timl_controller_transform_index = transform_index
            if type_index is None:
                type_index = int(scene_props.timl_controller_transforms[transform_index].type_index)
    if type_index is not None:
        block_index = _find_type_item_index(scene_props, int(type_index))
        if block_index >= 0:
            scene_props.selected_timl_block_index = block_index


def _binding_preview_value(controller, property_name: str, data_type: int) -> tuple[float, ...]:
    if controller is None or str(property_name or "") not in controller.keys():
        return default_preview_value_for_data_type(int(data_type))
    value = controller[str(property_name)]
    if isinstance(value, (str, bytes)):
        return default_preview_value_for_data_type(int(data_type))
    try:
        if hasattr(value, "__iter__"):
            return tuple(float(component) for component in value)
    except TypeError:
        pass
    return (float(value),)


def _next_available_type_index(bindings: list[dict[str, object]]) -> int:
    if not bindings:
        return 0
    return max(int(binding["type_index"]) for binding in bindings) + 1


def _next_available_transform_index(bindings: list[dict[str, object]], type_index: int) -> int:
    matching = [
        int(binding["transform_index"])
        for binding in bindings
        if int(binding["type_index"]) == int(type_index)
    ]
    if not matching:
        return 0
    return max(matching) + 1


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


def _frame_selected_timl_curves(context):
    screen = getattr(getattr(context, "window", None), "screen", None)
    if screen is None:
        return
    for area in getattr(screen, "areas", ()):
        area_type = getattr(area, "type", "")
        if area_type not in {"GRAPH_EDITOR", "DOPESHEET_EDITOR"}:
            continue
        region = next((region for region in getattr(area, "regions", ()) if getattr(region, "type", "") == "WINDOW"), None)
        if region is None:
            continue
        with context.temp_override(area=area, region=region):
            try:
                if area_type == "GRAPH_EDITOR":
                    bpy.ops.graph.view_selected()
                elif area_type == "DOPESHEET_EDITOR":
                    bpy.ops.action.view_selected()
            except RuntimeError:
                continue


def _apply_scene_frame_span(scene, *, first_frame: float | None, last_frame: float | None):
    if first_frame is None or last_frame is None:
        return False
    start = int(first_frame)
    end = int(last_frame) if float(last_frame).is_integer() else int(last_frame) + 1
    if end < start:
        end = start
    scene.frame_start = start
    scene.frame_end = end
    scene.frame_current = start
    return True


def _controller_has_timl_bindings(controller) -> bool:
    raw_value = controller.get(TIML_BINDINGS_KEY, "") if controller is not None else ""
    if not isinstance(raw_value, str) or not raw_value:
        return False
    try:
        decoded = json.loads(raw_value)
    except json.JSONDecodeError:
        return False
    return bool(decoded)


def _imported_timl_controller_items(_self, context):
    scene_props = context.scene.mhw_anim_tools
    source_path = str(scene_props.last_lmt_path or "")
    items = []
    for obj in bpy.data.objects:
        if not is_imported_timl_controller(obj):
            continue
        metadata = extract_timl_controller_metadata(obj)
        label = obj.name
        if str(metadata.action_name or ""):
            label = f"{obj.name} | {metadata.action_name}"
        if source_path and str(metadata.source_lmt or "") == source_path:
            label = f"{label} | {metadata.entry_id:03d}"
        items.append((obj.name, label, ""))
    if not items:
        items.append(("", "No imported TIML controllers", ""))
    return items


def _source_binding_items(self, context):
    controller_name = str(getattr(self, "source_controller_name", "") or "")
    controller = bpy.data.objects.get(controller_name)
    bindings = load_timl_bindings_raw(controller) if controller is not None else []
    items = []
    for binding in bindings:
        property_name = str(binding["property_name"])
        label = (
            f"T{int(binding['type_index']):02d}:X{int(binding['transform_index']):02d} | "
            f"0x{int(binding['timeline_parameter_hash']) & 0xFFFFFFFF:08X} | "
            f"0x{int(binding['datatype_hash']) & 0xFFFFFFFF:08X} | "
            f"{str(binding['data_type_name'])}"
        )
        items.append((property_name, label, ""))
    if not items:
        items.append(("", "No source transforms", ""))
    return items


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


class MHWANIMTOOLS_OT_focus_selected_entry_timl_controller(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.focus_selected_entry_timl_controller"
    bl_label = "Focus Imported Controller"
    bl_description = "Focus the imported TIML controller that belongs to the selected LMT entry"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _controller_for_selected_entry(scene_props)
        if controller is None:
            entry = _selected_entry(scene_props)
            if entry is None:
                scene_props.last_status = "Choose an LMT entry first."
            else:
                scene_props.last_status = f"Entry {int(entry.entry_id):03d} has no imported TIML controller yet."
            add_diagnostic(scene_props, "WARNING", "timl.controller", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        scene_props.timl_controller = controller
        _set_active_controller(context, controller)
        if scene_props.last_timl_analysis_controller_name != controller.name:
            try:
                bpy.ops.mhw_anim_tools.analyze_timl_controller()
            except RuntimeError:
                pass
        scene_props.last_status = f"Focused {controller.name}."
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_edit_timl_header(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.edit_timl_header"
    bl_label = "Edit TIML Header"
    bl_description = "Edit raw TIML header fields for the active controller"

    data_index_a: bpy.props.IntProperty(name="data_index_a", default=0)
    data_index_b: bpy.props.IntProperty(name="data_index_b", default=0)
    animation_length: bpy.props.FloatProperty(name="animation_length", default=0.0)
    loop_start_point: bpy.props.FloatProperty(name="loop_start_point", default=0.0)
    loop_control: bpy.props.IntProperty(name="loop_control", default=0)
    label_hash_hex: bpy.props.StringProperty(name="label_hash", default="0x00000000")

    def invoke(self, context, _event):
        controller = _resolve_timl_controller(context)
        if controller is None:
            return self.execute(context)
        metadata = extract_timl_controller_metadata(controller)
        state = timl_header_state_from_controller(
            controller,
            source_lmt=str(metadata.source_lmt or ""),
            entry_id=int(metadata.entry_id),
        )
        self.data_index_a = int(state["data_index_a"])
        self.data_index_b = int(state["data_index_b"])
        self.animation_length = float(state["animation_length"])
        self.loop_start_point = float(state["loop_start_point"])
        self.loop_control = int(state["loop_control"])
        self.label_hash_hex = _format_hex_u32(int(state["label_hash"]))
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "data_index_a")
        layout.prop(self, "data_index_b")
        layout.prop(self, "animation_length")
        layout.prop(self, "loop_start_point")
        layout.prop(self, "loop_control")
        layout.prop(self, "label_hash_hex")

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        if controller is None:
            scene_props.last_status = "Choose an imported TIML controller first."
            add_diagnostic(scene_props, "ERROR", "timl.header", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        metadata = extract_timl_controller_metadata(controller)
        ensure_timl_header_props(
            controller,
            source_lmt=str(metadata.source_lmt or ""),
            entry_id=int(metadata.entry_id),
            data_index_a=int(self.data_index_a),
            data_index_b=int(self.data_index_b),
            animation_length=float(self.animation_length),
            loop_start_point=float(self.loop_start_point),
            loop_control=int(self.loop_control),
            label_hash=_parse_hex_u32(self.label_hash_hex),
        )
        _refresh_timl_controller_after_edit(context, controller)
        scene_props.last_status = f"Updated TIML header for {controller.name}."
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_edit_timl_type(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.edit_timl_type"
    bl_label = "Edit Type"
    bl_description = "Edit the raw type index and timeline hash for the selected TIML type"

    type_index: bpy.props.IntProperty(name="type_index", default=0, min=0)
    timeline_hash_hex: bpy.props.StringProperty(name="timeline_hash", default="0x00000000")

    def invoke(self, context, _event):
        scene_props = context.scene.mhw_anim_tools
        block = _selected_timl_block(scene_props)
        if block is None:
            return self.execute(context)
        self.type_index = int(block.type_index)
        self.timeline_hash_hex = str(block.raw_timeline_label or "0x00000000")
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "type_index")
        layout.prop(self, "timeline_hash_hex")

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        block = _selected_timl_block(scene_props)
        if controller is None or block is None:
            scene_props.last_status = "Choose a TIML type first."
            add_diagnostic(scene_props, "ERROR", "timl.type", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        source_type_index = int(block.type_index)
        target_type_index = int(self.type_index)
        bindings = load_timl_bindings_raw(controller)
        selected_bindings = [binding for binding in bindings if int(binding["type_index"]) == source_type_index]
        if not selected_bindings:
            scene_props.last_status = "The selected TIML type has no editable transforms."
            add_diagnostic(scene_props, "ERROR", "timl.type", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        taken_identities = {
            (int(binding["type_index"]), int(binding["transform_index"]))
            for binding in bindings
            if int(binding["type_index"]) != source_type_index
        }
        for binding in selected_bindings:
            candidate = (target_type_index, int(binding["transform_index"]))
            if candidate in taken_identities:
                scene_props.last_status = (
                    f"Type edit would collide with existing transform {target_type_index:02d}:{int(binding['transform_index']):02d}."
                )
                add_diagnostic(scene_props, "ERROR", "timl.type", scene_props.last_status)
                self.report({"WARNING"}, scene_props.last_status)
                return {"CANCELLED"}

        timeline_hash = _parse_hex_u32(self.timeline_hash_hex)
        for binding in bindings:
            if int(binding["type_index"]) == source_type_index:
                binding["type_index"] = target_type_index
                binding["timeline_parameter_hash"] = timeline_hash
        save_timl_bindings_raw(controller, bindings)
        _refresh_timl_controller_after_edit(context, controller)
        _select_workspace_identity(scene_props, type_index=target_type_index)
        scene_props.last_status = f"Updated type {source_type_index:02d}."
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_edit_timl_transform(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.edit_timl_transform"
    bl_label = "Edit Transform"
    bl_description = "Edit the raw identity for the selected TIML transform"

    type_index: bpy.props.IntProperty(name="type_index", default=0, min=0)
    transform_index: bpy.props.IntProperty(name="transform_index", default=0, min=0)
    timeline_hash_hex: bpy.props.StringProperty(name="timeline_hash", default="0x00000000")
    datatype_hash_hex: bpy.props.StringProperty(name="datatype_hash", default="0x00000000")
    data_type: bpy.props.EnumProperty(name="data_type", items=TIML_DATA_TYPE_ITEMS, default="1")

    def invoke(self, context, _event):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        binding = _binding_for_selected_transform(controller, scene_props) if controller is not None else None
        if binding is None:
            return self.execute(context)
        self.type_index = int(binding["type_index"])
        self.transform_index = int(binding["transform_index"])
        self.timeline_hash_hex = _format_hex_u32(int(binding["timeline_parameter_hash"]))
        self.datatype_hash_hex = _format_hex_u32(int(binding["datatype_hash"]))
        self.data_type = str(int(binding["data_type"]))
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "type_index")
        layout.prop(self, "transform_index")
        layout.prop(self, "timeline_hash_hex")
        layout.prop(self, "datatype_hash_hex")
        layout.prop(self, "data_type")

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        binding = _binding_for_selected_transform(controller, scene_props) if controller is not None else None
        if controller is None or binding is None:
            scene_props.last_status = "Choose a TIML transform first."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        property_name = str(binding["property_name"])
        target_identity = (int(self.type_index), int(self.transform_index))
        bindings = load_timl_bindings_raw(controller)
        for other in bindings:
            if str(other["property_name"]) == property_name:
                continue
            if (int(other["type_index"]), int(other["transform_index"])) == target_identity:
                scene_props.last_status = (
                    f"Transform edit would collide with existing transform {target_identity[0]:02d}:{target_identity[1]:02d}."
                )
                add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
                self.report({"WARNING"}, scene_props.last_status)
                return {"CANCELLED"}

        old_data_type = int(binding["data_type"])
        new_data_type = int(self.data_type)
        binding["type_index"] = int(self.type_index)
        binding["transform_index"] = int(self.transform_index)
        binding["timeline_parameter_hash"] = _parse_hex_u32(self.timeline_hash_hex)
        binding["datatype_hash"] = _parse_hex_u32(self.datatype_hash_hex)
        binding["data_type"] = new_data_type
        binding["data_type_name"] = _data_type_name_for_key(str(new_data_type))
        save_timl_bindings_raw(controller, bindings)

        action = _controller_action(controller)
        if old_data_type != new_data_type and action is not None:
            preview_value = default_preview_value_for_data_type(new_data_type)
            if property_name in controller:
                del controller[property_name]
            ensure_binding_preview_property(controller, binding, preview_value=preview_value)
            remove_binding_preview_fcurves(action, property_name)
            create_binding_preview_fcurves(action, binding, frame=0.0, preview_value=preview_value)

        _refresh_timl_controller_after_edit(context, controller)
        _select_workspace_identity(scene_props, property_name=property_name, type_index=int(self.type_index))
        scene_props.last_status = f"Updated transform {property_name}."
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_add_timl_type(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.add_timl_type"
    bl_label = "Add Type"
    bl_description = "Add a new TIML type by creating its first transform"

    type_index: bpy.props.IntProperty(name="type_index", default=0, min=0)
    timeline_hash_hex: bpy.props.StringProperty(name="timeline_hash", default="0x00000000")
    datatype_hash_hex: bpy.props.StringProperty(name="datatype_hash", default="0x00000000")
    data_type: bpy.props.EnumProperty(name="data_type", items=TIML_DATA_TYPE_ITEMS, default="1")

    def invoke(self, context, _event):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        bindings = load_timl_bindings_raw(controller) if controller is not None else []
        block = _selected_timl_block(scene_props)
        self.type_index = _next_available_type_index(bindings)
        self.timeline_hash_hex = str(block.raw_timeline_label or "0x00000000") if block is not None else "0x00000000"
        transform = _selected_controller_transform(scene_props)
        self.datatype_hash_hex = str(transform.raw_datatype_display or "0x00000000") if transform is not None else "0x00000000"
        self.data_type = _data_type_key_for_name(str(transform.data_type_name or ""), fallback="1")
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "type_index")
        layout.prop(self, "timeline_hash_hex")
        layout.prop(self, "datatype_hash_hex")
        layout.prop(self, "data_type")

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        if controller is None:
            scene_props.last_status = "Choose an imported TIML controller first."
            add_diagnostic(scene_props, "ERROR", "timl.type", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        bindings = load_timl_bindings_raw(controller)
        if any(int(binding["type_index"]) == int(self.type_index) for binding in bindings):
            scene_props.last_status = f"Type {int(self.type_index):02d} already exists."
            add_diagnostic(scene_props, "ERROR", "timl.type", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        binding = append_timl_binding(
            controller,
            type_index=int(self.type_index),
            transform_index=0,
            timeline_parameter_hash=_parse_hex_u32(self.timeline_hash_hex),
            datatype_hash=_parse_hex_u32(self.datatype_hash_hex),
            data_type=int(self.data_type),
        )
        preview_value = default_preview_value_for_data_type(int(self.data_type))
        ensure_binding_preview_property(controller, binding, preview_value=preview_value)
        action = _controller_action(controller)
        if action is not None:
            create_binding_preview_fcurves(action, binding, frame=0.0, preview_value=preview_value)
            _set_action_transform_count(controller, len(load_timl_bindings_raw(controller)))
        _refresh_timl_controller_after_edit(context, controller)
        _select_workspace_identity(scene_props, property_name=str(binding["property_name"]), type_index=int(self.type_index))
        scene_props.last_status = f"Added type {int(self.type_index):02d}."
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_duplicate_timl_type(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.duplicate_timl_type"
    bl_label = "Duplicate Type"
    bl_description = "Duplicate the selected TIML type into a new type index"

    target_type_index: bpy.props.IntProperty(name="target_type_index", default=0, min=0)

    def invoke(self, context, _event):
        controller = _resolve_timl_controller(context)
        bindings = load_timl_bindings_raw(controller) if controller is not None else []
        self.target_type_index = _next_available_type_index(bindings)
        return context.window_manager.invoke_props_dialog(self, width=280)

    def draw(self, _context):
        self.layout.prop(self, "target_type_index")

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        block = _selected_timl_block(scene_props)
        if controller is None or block is None:
            scene_props.last_status = "Choose a TIML type first."
            add_diagnostic(scene_props, "ERROR", "timl.type", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        source_type_index = int(block.type_index)
        target_type_index = int(self.target_type_index)
        bindings = load_timl_bindings_raw(controller)
        source_bindings = [
            binding
            for binding in bindings
            if int(binding["type_index"]) == source_type_index
        ]
        if not source_bindings:
            scene_props.last_status = "The selected TIML type has no transforms to duplicate."
            add_diagnostic(scene_props, "ERROR", "timl.type", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        if any(int(binding["type_index"]) == target_type_index for binding in bindings):
            scene_props.last_status = f"Type {target_type_index:02d} already exists."
            add_diagnostic(scene_props, "ERROR", "timl.type", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        action = _controller_action(controller)
        first_property_name = ""
        for source_binding in sorted(source_bindings, key=lambda item: int(item["transform_index"])):
            new_binding = append_timl_binding(
                controller,
                type_index=target_type_index,
                transform_index=int(source_binding["transform_index"]),
                timeline_parameter_hash=int(source_binding["timeline_parameter_hash"]),
                datatype_hash=int(source_binding["datatype_hash"]),
                data_type=int(source_binding["data_type"]),
            )
            if not first_property_name:
                first_property_name = str(new_binding["property_name"])
            preview_value = _binding_preview_value(controller, str(source_binding["property_name"]), int(source_binding["data_type"]))
            ensure_binding_preview_property(controller, new_binding, preview_value=preview_value)
            if action is not None:
                clone_binding_preview_fcurves(
                    action,
                    source_property_name=str(source_binding["property_name"]),
                    target_property_name=str(new_binding["property_name"]),
                )
        if action is not None:
            _set_action_transform_count(controller, len(load_timl_bindings_raw(controller)))
        _refresh_timl_controller_after_edit(context, controller)
        _select_workspace_identity(scene_props, property_name=first_property_name, type_index=target_type_index)
        scene_props.last_status = f"Duplicated type {source_type_index:02d} to {target_type_index:02d}."
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_delete_timl_type(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.delete_timl_type"
    bl_label = "Delete Type"
    bl_description = "Delete the selected TIML type and all of its transforms"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        block = _selected_timl_block(scene_props)
        if controller is None or block is None:
            scene_props.last_status = "Choose a TIML type first."
            add_diagnostic(scene_props, "ERROR", "timl.type", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        type_index = int(block.type_index)
        bindings = load_timl_bindings_raw(controller)
        property_names = [
            str(binding["property_name"])
            for binding in bindings
            if int(binding["type_index"]) == type_index
        ]
        if not property_names:
            scene_props.last_status = "The selected TIML type has no editable transforms."
            add_diagnostic(scene_props, "ERROR", "timl.type", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        action = _controller_action(controller)
        for property_name in property_names:
            if action is not None:
                remove_binding_preview_fcurves(action, property_name)
            remove_timl_binding(controller, property_name)
            if property_name in controller:
                del controller[property_name]
        if action is not None:
            _set_action_transform_count(controller, len(load_timl_bindings_raw(controller)))
        _refresh_timl_controller_after_edit(context, controller)
        scene_props.last_status = f"Deleted type {type_index:02d}."
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_add_timl_transform(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.add_timl_transform"
    bl_label = "Add Transform"
    bl_description = "Add a raw TIML transform to the selected or specified TIML type"

    type_index: bpy.props.IntProperty(name="type_index", default=0, min=0)
    transform_index: bpy.props.IntProperty(name="transform_index", default=0, min=0)
    timeline_hash_hex: bpy.props.StringProperty(name="timeline_hash", default="0x00000000")
    datatype_hash_hex: bpy.props.StringProperty(name="datatype_hash", default="0x00000000")
    data_type: bpy.props.EnumProperty(name="data_type", items=TIML_DATA_TYPE_ITEMS, default="1")

    def invoke(self, context, _event):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        bindings = load_timl_bindings_raw(controller) if controller is not None else []
        transform = _selected_controller_transform(scene_props)
        block = _selected_timl_block(scene_props)
        if transform is not None:
            self.type_index = int(transform.type_index)
            self.transform_index = _next_available_transform_index(bindings, int(transform.type_index))
            self.timeline_hash_hex = str(transform.raw_timeline_display or "0x00000000")
            self.datatype_hash_hex = str(transform.raw_datatype_display or "0x00000000")
            self.data_type = _data_type_key_for_name(str(transform.data_type_name or ""), fallback="1")
        elif block is not None:
            self.type_index = int(block.type_index)
            self.transform_index = _next_available_transform_index(bindings, int(block.type_index))
            self.timeline_hash_hex = str(block.raw_timeline_label or "0x00000000")
            self.datatype_hash_hex = "0x00000000"
            self.data_type = "1"
        else:
            self.type_index = _next_available_type_index(bindings)
            self.transform_index = 0
            self.timeline_hash_hex = "0x00000000"
            self.datatype_hash_hex = "0x00000000"
            self.data_type = "1"
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "type_index")
        layout.prop(self, "transform_index")
        layout.prop(self, "timeline_hash_hex")
        layout.prop(self, "datatype_hash_hex")
        layout.prop(self, "data_type")

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        if controller is None:
            scene_props.last_status = "Choose an imported TIML controller first."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        bindings = load_timl_bindings_raw(controller)
        identity = (int(self.type_index), int(self.transform_index))
        if any((int(binding["type_index"]), int(binding["transform_index"])) == identity for binding in bindings):
            scene_props.last_status = f"Transform {identity[0]:02d}:{identity[1]:02d} already exists."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        binding = append_timl_binding(
            controller,
            type_index=int(self.type_index),
            transform_index=int(self.transform_index),
            timeline_parameter_hash=_parse_hex_u32(self.timeline_hash_hex),
            datatype_hash=_parse_hex_u32(self.datatype_hash_hex),
            data_type=int(self.data_type),
        )
        preview_value = default_preview_value_for_data_type(int(self.data_type))
        ensure_binding_preview_property(controller, binding, preview_value=preview_value)
        action = _controller_action(controller)
        if action is not None:
            create_binding_preview_fcurves(action, binding, frame=0.0, preview_value=preview_value)
            _set_action_transform_count(controller, len(load_timl_bindings_raw(controller)))
        _refresh_timl_controller_after_edit(context, controller)
        _select_workspace_identity(scene_props, property_name=str(binding["property_name"]), type_index=int(self.type_index))
        scene_props.last_status = f"Added transform {identity[0]:02d}:{identity[1]:02d}."
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_duplicate_timl_transform(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.duplicate_timl_transform"
    bl_label = "Duplicate Transform"
    bl_description = "Duplicate the selected TIML transform"

    target_type_index: bpy.props.IntProperty(name="type_index", default=0, min=0)
    target_transform_index: bpy.props.IntProperty(name="transform_index", default=0, min=0)

    def invoke(self, context, _event):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        bindings = load_timl_bindings_raw(controller) if controller is not None else []
        transform = _selected_controller_transform(scene_props)
        if transform is not None:
            self.target_type_index = int(transform.type_index)
            self.target_transform_index = _next_available_transform_index(bindings, int(transform.type_index))
        return context.window_manager.invoke_props_dialog(self, width=280)

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "target_type_index")
        layout.prop(self, "target_transform_index")

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        binding = _binding_for_selected_transform(controller, scene_props) if controller is not None else None
        if controller is None or binding is None:
            scene_props.last_status = "Choose a TIML transform first."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        bindings = load_timl_bindings_raw(controller)
        target_identity = (int(self.target_type_index), int(self.target_transform_index))
        if any((int(item["type_index"]), int(item["transform_index"])) == target_identity for item in bindings):
            scene_props.last_status = f"Transform {target_identity[0]:02d}:{target_identity[1]:02d} already exists."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        new_binding = append_timl_binding(
            controller,
            type_index=int(self.target_type_index),
            transform_index=int(self.target_transform_index),
            timeline_parameter_hash=int(binding["timeline_parameter_hash"]),
            datatype_hash=int(binding["datatype_hash"]),
            data_type=int(binding["data_type"]),
        )
        preview_value = _binding_preview_value(controller, str(binding["property_name"]), int(binding["data_type"]))
        ensure_binding_preview_property(controller, new_binding, preview_value=preview_value)
        action = _controller_action(controller)
        if action is not None:
            clone_binding_preview_fcurves(
                action,
                source_property_name=str(binding["property_name"]),
                target_property_name=str(new_binding["property_name"]),
            )
            _set_action_transform_count(controller, len(load_timl_bindings_raw(controller)))
        _refresh_timl_controller_after_edit(context, controller)
        _select_workspace_identity(scene_props, property_name=str(new_binding["property_name"]), type_index=int(self.target_type_index))
        scene_props.last_status = f"Duplicated transform to {target_identity[0]:02d}:{target_identity[1]:02d}."
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_clone_timl_transform_from_existing(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.clone_timl_transform_from_existing"
    bl_label = "Clone From Existing"
    bl_description = "Clone a TIML transform from another imported TIML controller"

    source_controller_name: bpy.props.EnumProperty(name="source_controller", items=_imported_timl_controller_items)
    source_property_name: bpy.props.EnumProperty(name="source_transform", items=_source_binding_items)
    target_type_index: bpy.props.IntProperty(name="type_index", default=0, min=0)
    target_transform_index: bpy.props.IntProperty(name="transform_index", default=0, min=0)

    def invoke(self, context, _event):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        bindings = load_timl_bindings_raw(controller) if controller is not None else []
        transform = _selected_controller_transform(scene_props)
        items = _imported_timl_controller_items(self, context)
        self.source_controller_name = next((name for name, _label, _desc in items if name), "")
        if transform is not None:
            self.target_type_index = int(transform.type_index)
            self.target_transform_index = _next_available_transform_index(bindings, int(transform.type_index))
        else:
            self.target_type_index = _next_available_type_index(bindings)
            self.target_transform_index = 0
        source_items = _source_binding_items(self, context)
        self.source_property_name = next((name for name, _label, _desc in source_items if name), "")
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "source_controller_name")
        layout.prop(self, "source_property_name")
        layout.separator()
        layout.prop(self, "target_type_index")
        layout.prop(self, "target_transform_index")

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        target_controller = _resolve_timl_controller(context)
        if target_controller is None:
            scene_props.last_status = "Choose an imported TIML controller first."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        source_controller = bpy.data.objects.get(str(self.source_controller_name or ""))
        if source_controller is None or not is_imported_timl_controller(source_controller):
            scene_props.last_status = "Choose a source TIML controller."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        source_property_name = str(self.source_property_name or "")
        source_binding = next(
            (
                binding
                for binding in load_timl_bindings_raw(source_controller)
                if str(binding["property_name"]) == source_property_name
            ),
            None,
        )
        if source_binding is None:
            scene_props.last_status = "Choose a source TIML transform."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        bindings = load_timl_bindings_raw(target_controller)
        target_identity = (int(self.target_type_index), int(self.target_transform_index))
        if any((int(item["type_index"]), int(item["transform_index"])) == target_identity for item in bindings):
            scene_props.last_status = f"Transform {target_identity[0]:02d}:{target_identity[1]:02d} already exists."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        new_binding = append_timl_binding(
            target_controller,
            type_index=int(self.target_type_index),
            transform_index=int(self.target_transform_index),
            timeline_parameter_hash=int(source_binding["timeline_parameter_hash"]),
            datatype_hash=int(source_binding["datatype_hash"]),
            data_type=int(source_binding["data_type"]),
        )
        preview_value = _binding_preview_value(source_controller, source_property_name, int(source_binding["data_type"]))
        ensure_binding_preview_property(target_controller, new_binding, preview_value=preview_value)
        target_action = _controller_action(target_controller)
        source_action = _controller_action(source_controller)
        if target_action is not None and source_action is not None:
            if target_action == source_action and source_controller == target_controller:
                clone_binding_preview_fcurves(
                    target_action,
                    source_property_name=source_property_name,
                    target_property_name=str(new_binding["property_name"]),
                )
            else:
                copied_curve = False
                for source_fcurve in getattr(source_action, "fcurves", ()):
                    if str(getattr(source_fcurve, "data_path", "")) != f'["{source_property_name}"]':
                        continue
                    copied_curve = True
                    # Recreate external-controller source curves by sampling their current points directly.
                    target_fcurve = target_action.fcurves.new(
                        data_path=f'["{str(new_binding["property_name"])}"]',
                        index=int(getattr(source_fcurve, "array_index", 0)),
                        action_group=str(getattr(source_fcurve, "group", None).name if getattr(source_fcurve, "group", None) else "TIML"),
                    )
                    points = list(getattr(source_fcurve, "keyframe_points", ()))
                    target_fcurve.keyframe_points.add(len(points))
                    for point_index, point in enumerate(points):
                        target_point = target_fcurve.keyframe_points[point_index]
                        target_point.co = tuple(point.co)
                        target_point.interpolation = str(getattr(point, "interpolation", "LINEAR") or "LINEAR")
                    target_fcurve.update()
                if not copied_curve:
                    create_binding_preview_fcurves(target_action, new_binding, frame=0.0, preview_value=preview_value)
            _set_action_transform_count(target_controller, len(load_timl_bindings_raw(target_controller)))
        _refresh_timl_controller_after_edit(context, target_controller)
        _select_workspace_identity(scene_props, property_name=str(new_binding["property_name"]), type_index=int(self.target_type_index))
        scene_props.last_status = (
            f"Cloned {source_property_name} into {target_identity[0]:02d}:{target_identity[1]:02d}."
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_delete_timl_transform(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.delete_timl_transform"
    bl_label = "Delete Transform"
    bl_description = "Delete the selected TIML transform"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        binding = _binding_for_selected_transform(controller, scene_props) if controller is not None else None
        if controller is None or binding is None:
            scene_props.last_status = "Choose a TIML transform first."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        property_name = str(binding["property_name"])
        action = _controller_action(controller)
        if action is not None:
            remove_binding_preview_fcurves(action, property_name)
        remove_timl_binding(controller, property_name)
        if property_name in controller:
            del controller[property_name]
        if action is not None:
            _set_action_transform_count(controller, len(load_timl_bindings_raw(controller)))
        _refresh_timl_controller_after_edit(context, controller)
        scene_props.last_status = f"Deleted transform {property_name}."
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
        _frame_selected_timl_curves(context)
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
        _frame_selected_timl_curves(context)
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
        _frame_selected_timl_curves(context)
        scene_props.last_status = (
            f"Selected {match_count} curve(s) for "
            f"{transform.semantic_label or transform.property_name}. Open Graph Editor to edit keys."
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_use_timl_block_frame_span(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.use_timl_block_frame_span"
    bl_label = "Use TIML Block Frame Span"
    bl_description = "Set the scene playback range to the currently selected TIML block"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        block = _selected_timl_block(scene_props)
        if block is None or int(block.keyframe_count) <= 0:
            scene_props.last_status = "Choose a TIML block with keyframes before using its frame span."
            add_diagnostic(scene_props, "ERROR", "timl.block", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        if not _apply_scene_frame_span(
            context.scene,
            first_frame=float(block.first_frame),
            last_frame=float(block.last_frame),
        ):
            scene_props.last_status = "The selected TIML block does not expose a usable frame span."
            add_diagnostic(scene_props, "ERROR", "timl.block", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        scene_props.last_status = (
            f"Scene frame range set to {float(block.first_frame):.3f} -> {float(block.last_frame):.3f} "
            f"for {block.block_label or 'the selected TIML block'}."
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_use_timl_transform_frame_span(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.use_timl_transform_frame_span"
    bl_label = "Use TIML Transform Frame Span"
    bl_description = "Set the scene playback range to the currently selected TIML transform"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        transform = _selected_controller_transform(scene_props)
        if transform is None or int(transform.keyframe_count) <= 0:
            scene_props.last_status = "Choose a TIML transform with keyframes before using its frame span."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        if not _apply_scene_frame_span(
            context.scene,
            first_frame=float(transform.first_frame),
            last_frame=float(transform.last_frame),
        ):
            scene_props.last_status = "The selected TIML transform does not expose a usable frame span."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        scene_props.last_status = (
            f"Scene frame range set to {float(transform.first_frame):.3f} -> {float(transform.last_frame):.3f} "
            f"for {transform.semantic_label or transform.identity_label or 'the selected TIML transform'}."
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
    MHWANIMTOOLS_OT_focus_selected_entry_timl_controller,
    MHWANIMTOOLS_OT_edit_timl_header,
    MHWANIMTOOLS_OT_edit_timl_type,
    MHWANIMTOOLS_OT_edit_timl_transform,
    MHWANIMTOOLS_OT_add_timl_type,
    MHWANIMTOOLS_OT_duplicate_timl_type,
    MHWANIMTOOLS_OT_delete_timl_type,
    MHWANIMTOOLS_OT_add_timl_transform,
    MHWANIMTOOLS_OT_duplicate_timl_transform,
    MHWANIMTOOLS_OT_clone_timl_transform_from_existing,
    MHWANIMTOOLS_OT_delete_timl_transform,
    MHWANIMTOOLS_OT_select_timl_block_curves,
    MHWANIMTOOLS_OT_select_timl_property_curves,
    MHWANIMTOOLS_OT_select_timl_transform_curves,
    MHWANIMTOOLS_OT_use_timl_block_frame_span,
    MHWANIMTOOLS_OT_use_timl_transform_frame_span,
    MHWANIMTOOLS_OT_create_timl_eventloop,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
