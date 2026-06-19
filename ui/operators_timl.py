# -*- coding: utf-8 -*-
"""Focused TIML controller workflow operators."""

import json
from pathlib import Path

import bpy

from ..blender_adapter.timl_authoring import append_timl_binding
from ..blender_adapter.timl_authoring import clear_deleted_timl_identity
from ..blender_adapter.timl_authoring import clone_binding_preview_fcurves
from ..blender_adapter.timl_authoring import create_binding_preview_fcurves
from ..blender_adapter.timl_authoring import delete_timl_transform_binding
from ..blender_adapter.timl_authoring import delete_timl_type_bindings
from ..blender_adapter.timl_authoring import default_preview_value_for_data_type
from ..blender_adapter.timl_authoring import ensure_binding_preview_property
from ..blender_adapter.timl_authoring import ensure_timl_header_props
from ..blender_adapter.timl_authoring import insert_timl_transform_slot
from ..blender_adapter.timl_authoring import insert_timl_type_slot
from ..blender_adapter.timl_authoring import load_timl_bindings_raw
from ..blender_adapter.timl_authoring import mark_deleted_timl_identity
from ..blender_adapter.timl_authoring import move_timl_transform_binding
from ..blender_adapter.timl_authoring import move_timl_type_bindings
from ..blender_adapter.timl_authoring import remove_binding_preview_fcurves
from ..blender_adapter.timl_authoring import remove_timl_binding
from ..blender_adapter.timl_authoring import retag_binding_preview_fcurve_groups
from ..blender_adapter.timl_authoring import save_timl_bindings_raw
from ..blender_adapter.timl_authoring import seed_binding_source_identity
from ..blender_adapter.timl_authoring import sync_timl_binding_meta_props_from_bindings
from ..blender_adapter.timl_authoring import timl_binding_identity
from ..blender_adapter.timl_authoring import timl_binding_source_identity
from ..blender_adapter.timl_authoring import timl_header_state_from_controller
from ..blender_adapter.fcurves import create_action_fcurves
from ..blender_adapter.fcurves import bind_action_slot
from ..blender_adapter.fcurves import create_scalar_action_fcurve
from ..blender_adapter.timl_metadata import TIML_BINDINGS_KEY
from ..blender_adapter.timl_metadata import TIML_SOURCE_KIND_ATTACHED_LMT
from ..blender_adapter.timl_metadata import TIML_SOURCE_KIND_STANDALONE_FILE
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
from ..core.formats.timl.channels import build_timl_transform_samples
from ..core.formats.timl.reader import read_timl_data_bytes
from ..core.formats.timl.reader import read_timl_bytes
from .properties import add_diagnostic
from .properties import clear_diagnostics
from .properties import clear_timl_analysis
from .properties import _populate_timl_controller_transform_items
from .properties import set_timl_edit_policy_summary
from .properties import set_timl_payload_scope_summary
from .properties import set_timl_shared_controller_summary
from .properties import set_timl_writeback_summary
from .timl_defaults import data_type_key_for_name as _data_type_key_for_name
from .timl_defaults import next_available_transform_index as _next_available_transform_index
from .timl_defaults import next_available_type_index as _next_available_type_index
from .timl_defaults import seed_add_timl_transform_defaults
from .timl_defaults import seed_add_timl_type_defaults


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


def _ensure_controller_action_slot_binding(controller, action=None) -> None:
    animation_data = getattr(controller, "animation_data", None)
    if animation_data is None:
        return
    bind_action_slot(animation_data, action)


def _save_timl_bindings_with_preview_groups(controller, bindings) -> None:
    save_timl_bindings_raw(controller, bindings)
    action = _controller_action(controller)
    if action is not None:
        retag_binding_preview_fcurve_groups(action, bindings)


def _retag_controller_preview_groups(controller) -> None:
    action = _controller_action(controller)
    if action is None:
        return
    retag_binding_preview_fcurve_groups(action, load_timl_bindings_raw(controller))


def _source_identities_from_entry(source_entry) -> set[tuple[int, int]]:
    if source_entry is None:
        return set()
    return {
        (int(type_index), int(transform_index))
        for type_index, type_entry in enumerate(getattr(source_entry, "types", ()))
        for transform_index, _transform in enumerate(getattr(type_entry, "transforms", ()))
    }


def _seed_missing_binding_source_origins(bindings, source_entry) -> list[dict[str, object]]:
    source_identities = _source_identities_from_entry(source_entry)
    updated = []
    for binding in bindings:
        item = dict(binding)
        if timl_binding_identity(item) in source_identities:
            seed_binding_source_identity(item)
        updated.append(item)
    return updated


def _safe_source_entry_for_controller_object(controller):
    if controller is None:
        return None
    metadata = extract_timl_controller_metadata(controller)
    try:
        _source_bytes, source_entry = _source_entry_for_controller(metadata)
    except (BinaryFormatError, FileNotFoundError, OSError, ValidationError, ValueError):
        return None
    return source_entry


def _binding_source_identity_for_entry(binding, source_entry):
    source_identity = timl_binding_source_identity(binding)
    if source_identity is not None and _source_identity_exists(source_entry, source_identity):
        return source_identity
    current_identity = timl_binding_identity(binding)
    if _source_identity_exists(source_entry, current_identity):
        return current_identity
    return None


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


def _binding_for_identity(controller, *, type_index: int, transform_index: int):
    for binding in load_timl_bindings_raw(controller):
        if int(binding["type_index"]) == int(type_index) and int(binding["transform_index"]) == int(transform_index):
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


def _workspace_pointer(workspace) -> int:
    pointer_getter = getattr(workspace, "as_pointer", None)
    if not callable(pointer_getter):
        return 0
    try:
        return int(pointer_getter())
    except (TypeError, ValueError, RuntimeError):
        return 0


def _is_new_workspace_candidate(workspace, *, existing_workspace_ids: set[int], existing_workspace_names: set[str]) -> bool:
    if workspace is None:
        return False
    pointer = _workspace_pointer(workspace)
    if pointer and pointer not in existing_workspace_ids:
        return True
    name = str(getattr(workspace, "name", "") or "")
    return bool(name) and name not in existing_workspace_names


def _duplicated_workspace(window, *, existing_workspace_ids: set[int], existing_workspace_names: set[str]):
    active_workspace = getattr(window, "workspace", None)
    if _is_new_workspace_candidate(
        active_workspace,
        existing_workspace_ids=existing_workspace_ids,
        existing_workspace_names=existing_workspace_names,
    ):
        return active_workspace

    return next(
        (
            workspace_item
            for workspace_item in bpy.data.workspaces
            if _is_new_workspace_candidate(
                workspace_item,
                existing_workspace_ids=existing_workspace_ids,
                existing_workspace_names=existing_workspace_names,
            )
        ),
        None,
    )


def _schedule_timl_workspace_configuration(window, workspace, scene=None, controller_name: str = "") -> None:
    state = {"attempts_remaining": 12}

    def _configure_once():
        try:
            if window is None or workspace is None:
                return None

            if getattr(window, "workspace", None) != workspace:
                window.workspace = workspace
                state["attempts_remaining"] -= 1
                return 0.05 if state["attempts_remaining"] > 0 else None

            screen = getattr(window, "screen", None)
            configured = _configure_timl_screen(screen)
            configured = _configure_timl_workspace(workspace, window=window) or configured
            graph_ready = bool(_graph_editor_areas(screen)) if screen is not None else False
            action_ready = _configure_timl_action_editor(screen)

            if not (configured and graph_ready and action_ready):
                state["attempts_remaining"] -= 1
                return 0.05 if state["attempts_remaining"] > 0 else None

            if scene is not None and controller_name:
                scene_props = getattr(scene, "mhw_anim_tools", None)
                if (
                    scene_props is not None
                    and str(scene_props.last_timl_analysis_controller_name or "") != str(controller_name)
                ):
                    try:
                        bpy.ops.mhw_anim_tools.analyze_timl_controller()
                    except RuntimeError:
                        pass
            return None
        except ReferenceError:
            return None

    bpy.app.timers.register(_configure_once, first_interval=0.05)


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
            if hasattr(space, "mode"):
                try:
                    space.mode = "ACTION"
                except TypeError:
                    pass
    return bool(areas)


def _configure_timl_screen(screen):
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


def _configure_timl_workspace(workspace, window=None):
    configured = False
    screens = tuple(getattr(workspace, "screens", ())) if workspace is not None else ()
    if not screens and window is not None:
        fallback_screen = getattr(window, "screen", None)
        screens = (fallback_screen,) if fallback_screen is not None else ()
    for screen in screens:
        configured = _configure_timl_screen(screen) or configured
    return configured


def _ensure_timl_workspace(context, *, controller_name: str = ""):
    window = getattr(context, "window", None)
    if window is None:
        return False, "No active Blender window is available."

    workspace = bpy.data.workspaces.get(_timl_workspace_name())
    if workspace is None:
        existing_workspace_ids = {_workspace_pointer(workspace_item) for workspace_item in bpy.data.workspaces}
        existing_workspace_names = {
            str(getattr(workspace_item, "name", "") or "")
            for workspace_item in bpy.data.workspaces
        }
        try:
            bpy.ops.workspace.duplicate()
        except RuntimeError as exc:
            return False, f"Could not create a TIML workspace: {exc}"
        workspace = _duplicated_workspace(
            window,
            existing_workspace_ids=existing_workspace_ids,
            existing_workspace_names=existing_workspace_names,
        )
        if workspace is None:
            return False, "TIML workspace duplication succeeded, but the new workspace could not be identified."
        workspace.name = _timl_workspace_name()
    window.workspace = workspace
    _schedule_timl_workspace_configuration(
        window,
        workspace,
        scene=getattr(context, "scene", None),
        controller_name=controller_name,
    )
    return True, ""


def _build_source_backed_writeback_plan(controller, metadata, *, source_bytes: bytes):
    if metadata is None:
        return None
    if str(getattr(metadata, "source_kind", "") or "") == TIML_SOURCE_KIND_STANDALONE_FILE:
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
    if str(getattr(metadata, "source_kind", "") or "") == TIML_SOURCE_KIND_STANDALONE_FILE:
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


def _selected_transform_identity(scene_props):
    transform = _selected_controller_transform(scene_props)
    if transform is None:
        return None
    return (int(transform.type_index), int(transform.transform_index))


def _source_entry_for_controller(metadata):
    if metadata is None:
        return None, None
    source_kind = str(getattr(metadata, "source_kind", "") or "")
    source_path = str(getattr(metadata, "source_lmt", "") or "")
    if not source_path:
        return None, None

    if source_kind == TIML_SOURCE_KIND_STANDALONE_FILE:
        source_file = Path(source_path)
        if not source_file.is_file():
            raise FileNotFoundError(f"TIML source file is missing: {source_path}")
        source_bytes = source_file.read_bytes()
        entry_id = int(getattr(metadata, "entry_id", 0))
        source_offset = int(getattr(metadata, "source_offset", 0))
        if source_offset <= 0:
            timl_file = read_timl_bytes(source_bytes, source_name=str(source_file))
            if 0 <= entry_id < len(timl_file.entry_offsets):
                source_offset = int(timl_file.entry_offsets[entry_id])
        if source_offset <= 0:
            return source_bytes, None
        source_entry = read_timl_data_bytes(
            source_bytes,
            data_offset=source_offset,
            source_name=str(source_file),
            entry_id=entry_id,
        )
        return source_bytes, source_entry

    source_bytes, _source_lmt_file = _load_source_context(metadata)
    if source_bytes is None:
        return None, None
    source_entry = read_timl_data_bytes(
        source_bytes,
        data_offset=int(getattr(metadata, "source_offset", 0)),
        source_name=f"{str(getattr(metadata, 'source_lmt', '') or '')}#timl",
        entry_id=int(getattr(metadata, "entry_id", 0)),
    )
    return source_bytes, source_entry


def _source_identity_exists(source_entry, identity: tuple[int, int]) -> bool:
    if source_entry is None or identity is None:
        return False
    type_index, transform_index = (int(identity[0]), int(identity[1]))
    if type_index < 0 or type_index >= len(getattr(source_entry, "types", ())):
        return False
    type_entry = source_entry.types[type_index]
    return 0 <= transform_index < len(getattr(type_entry, "transforms", ()))


def _preview_value_from_source_transform(transform_samples) -> tuple[float, ...]:
    if not getattr(transform_samples, "keyframes", ()):
        return default_preview_value_for_data_type(int(getattr(transform_samples, "data_type", 0)))
    value = tuple(float(component) for component in transform_samples.keyframes[0].value)
    return _preview_value_from_source_components(
        value,
        data_type=int(getattr(transform_samples, "data_type", 0)),
        value_kind=str(getattr(transform_samples, "value_kind", "") or ""),
    )


def _preview_value_from_source_components(value, *, data_type: int, value_kind: str) -> tuple[float, ...]:
    value = tuple(float(component) for component in value)
    if int(data_type) == 3:
        return tuple(component / 255.0 for component in value)
    if str(value_kind or "") == "boolean":
        return (1.0 if bool(value[0]) else 0.0,)
    return value


def _create_preview_curves_from_source_transform(action, binding: dict[str, object], transform_samples) -> None:
    property_name = str(binding["property_name"])
    data_path = f'["{property_name}"]'
    action_group = f"TIML {int(binding['type_index']):02d}:{int(binding['transform_index']):02d}"
    channel_count = len(tuple(getattr(transform_samples, "component_labels", ()))) or 1
    channel_values = [[] for _index in range(channel_count)]
    channel_interpolations = [[] for _index in range(channel_count)]
    for keyframe in getattr(transform_samples, "keyframes", ()):
        preview_value = _preview_value_from_source_components(
            getattr(keyframe, "value", ()),
            data_type=int(getattr(transform_samples, "data_type", 0)),
            value_kind=str(getattr(transform_samples, "value_kind", "") or ""),
        )
        interpolation = 0 if int(getattr(keyframe, "interpolation", 0)) == 0 else 1
        for index, component in enumerate(preview_value):
            channel_values[index].append((float(keyframe.frame), float(component)))
            channel_interpolations[index].append(interpolation)
    if channel_count == 1:
        create_scalar_action_fcurve(
            action,
            data_path=data_path,
            action_group=action_group,
            keyframes=channel_values[0],
            interpolations=channel_interpolations[0],
        )
        return
    create_action_fcurves(
        action,
        data_path=data_path,
        action_group=action_group,
        channel_values=channel_values,
        channel_interpolations=channel_interpolations,
    )


def _materialize_binding_from_source_transform(
    context,
    controller,
    scene_props,
    source_transform,
    *,
    refresh: bool = True,
):
    existing_binding = _binding_for_identity(
        controller,
        type_index=int(source_transform.type_index),
        transform_index=int(source_transform.transform_index),
    )
    if existing_binding is not None:
        return existing_binding, ""
    if not getattr(source_transform, "keyframes", ()):
        return None, "The selected TIML transform has no source keyframes to preview."

    binding = append_timl_binding(
        controller,
        type_index=int(source_transform.type_index),
        transform_index=int(source_transform.transform_index),
        source_type_index=int(source_transform.type_index),
        source_transform_index=int(source_transform.transform_index),
        timeline_parameter_hash=int(source_transform.timeline_parameter_hash),
        datatype_hash=int(source_transform.datatype_hash),
        data_type=int(source_transform.data_type),
    )
    preview_value = _preview_value_from_source_transform(source_transform)
    ensure_binding_preview_property(controller, binding, preview_value=preview_value)
    action = _controller_action(controller)
    if action is None:
        remove_timl_binding(controller, str(binding["property_name"]))
        if str(binding["property_name"]) in controller:
            del controller[str(binding["property_name"])]
        return None, "The selected TIML controller has no editable action for preview-curve creation."
    _create_preview_curves_from_source_transform(action, binding, source_transform)
    _ensure_controller_action_slot_binding(controller, action)
    _set_action_transform_count(controller, len(load_timl_bindings_raw(controller)))
    clear_deleted_timl_identity(
        controller,
        type_index=int(source_transform.type_index),
        transform_index=int(source_transform.transform_index),
    )
    if refresh:
        _refresh_timl_controller_after_edit(context, controller)
        _select_workspace_identity(
            scene_props,
            property_name=str(binding["property_name"]),
            type_index=int(source_transform.type_index),
        )
    return binding, ""


def _materialize_preview_binding_from_source(context, controller, scene_props):
    transform_item = _selected_controller_transform(scene_props)
    if controller is None or transform_item is None:
        return None, "Choose a TIML transform first."
    existing_binding = _binding_for_selected_transform(controller, scene_props)
    if existing_binding is not None:
        return existing_binding, ""

    metadata = extract_timl_controller_metadata(controller)
    try:
        _source_bytes, source_entry = _source_entry_for_controller(metadata)
    except (BinaryFormatError, FileNotFoundError, OSError, ValidationError, ValueError) as exc:
        return None, f"Could not load source TIML data: {exc}"
    if source_entry is None:
        return None, "The selected TIML controller is missing readable source TIML data."

    identity = (int(transform_item.type_index), int(transform_item.transform_index))
    if not _source_identity_exists(source_entry, identity):
        return None, "The selected TIML transform does not exist in the imported source payload."

    source_transform = next(
        (
            transform
            for transform in build_timl_transform_samples(source_entry)
            if (int(transform.type_index), int(transform.transform_index)) == identity
        ),
        None,
    )
    if source_transform is None:
        return None, "The selected TIML transform could not be reconstructed from the source payload."
    return _materialize_binding_from_source_transform(context, controller, scene_props, source_transform)


def _materialize_type_preview_bindings_from_source(context, controller, scene_props, type_index: int):
    if controller is None:
        return [], "Choose a TIML type first."
    metadata = extract_timl_controller_metadata(controller)
    try:
        _source_bytes, source_entry = _source_entry_for_controller(metadata)
    except (BinaryFormatError, FileNotFoundError, OSError, ValidationError, ValueError) as exc:
        return [], f"Could not load source TIML data: {exc}"
    if source_entry is None or int(type_index) < 0 or int(type_index) >= len(getattr(source_entry, "types", ())):
        return [], "The selected TIML type does not exist in the imported source payload."

    created_bindings = []
    for source_transform in build_timl_transform_samples(source_entry):
        if int(source_transform.type_index) != int(type_index):
            continue
        binding, error_message = _materialize_binding_from_source_transform(
            context,
            controller,
            scene_props,
            source_transform,
            refresh=False,
        )
        if binding is None:
            return [], error_message
        created_bindings.append(binding)
    if created_bindings:
        _refresh_timl_controller_after_edit(context, controller)
        _select_workspace_identity(
            scene_props,
            property_name=str(created_bindings[0]["property_name"]),
            type_index=int(type_index),
        )
    return created_bindings, ""


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
        target_controller_name = controller.name if controller is not None else ""
        success, message = _ensure_timl_workspace(context, controller_name=target_controller_name)
        if not success:
            scene_props.last_status = message
            add_diagnostic(scene_props, "WARNING", "timl.workspace", message)
            self.report({"WARNING"}, message)
            return {"CANCELLED"}
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
        source_transform_count = sum(
            1
            for item in scene_props.timl_controller_transforms
            if int(item.type_index) == source_type_index
        )
        selected_bindings = [binding for binding in bindings if int(binding["type_index"]) == source_type_index]
        if len(selected_bindings) < source_transform_count:
            created_bindings, error_message = _materialize_type_preview_bindings_from_source(
                context,
                controller,
                scene_props,
                source_type_index,
            )
            if not selected_bindings and not created_bindings:
                scene_props.last_status = error_message or "The selected TIML type has no editable transforms."
                add_diagnostic(scene_props, "ERROR", "timl.type", scene_props.last_status)
                self.report({"WARNING"}, scene_props.last_status)
                return {"CANCELLED"}
            bindings = load_timl_bindings_raw(controller)
            selected_bindings = [binding for binding in bindings if int(binding["type_index"]) == source_type_index]

        bindings = _seed_missing_binding_source_origins(
            bindings,
            _safe_source_entry_for_controller_object(controller),
        )
        selected_property_names = {
            str(binding["property_name"])
            for binding in selected_bindings
        }
        timeline_hash = _parse_hex_u32(self.timeline_hash_hex)
        occupied_type_indices = {
            int(binding["type_index"])
            for binding in bindings
            if int(binding["type_index"]) != source_type_index
        }
        if target_type_index in occupied_type_indices:
            bindings = move_timl_type_bindings(
                bindings,
                source_type_index=source_type_index,
                target_type_index=target_type_index,
            )
        for binding in bindings:
            if str(binding["property_name"]) in selected_property_names:
                binding["type_index"] = target_type_index
                binding["timeline_parameter_hash"] = timeline_hash
        _save_timl_bindings_with_preview_groups(controller, bindings)
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
        transform = _selected_controller_transform(scene_props)
        if binding is not None:
            self.type_index = int(binding["type_index"])
            self.transform_index = int(binding["transform_index"])
            self.timeline_hash_hex = _format_hex_u32(int(binding["timeline_parameter_hash"]))
            self.datatype_hash_hex = _format_hex_u32(int(binding["datatype_hash"]))
            self.data_type = str(int(binding["data_type"]))
        elif transform is not None:
            self.type_index = int(transform.type_index)
            self.transform_index = int(transform.transform_index)
            self.timeline_hash_hex = str(transform.raw_timeline_display or "0x00000000")
            self.datatype_hash_hex = str(transform.raw_datatype_display or "0x00000000")
            self.data_type = _data_type_key_for_name(str(transform.data_type_name or ""), fallback="1")
        else:
            return self.execute(context)
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
        if controller is None:
            scene_props.last_status = "Choose a TIML transform first."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        if binding is None:
            binding, error_message = _materialize_preview_binding_from_source(context, controller, scene_props)
            if binding is None:
                scene_props.last_status = error_message or "Choose a TIML transform first."
                add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
                self.report({"WARNING"}, scene_props.last_status)
                return {"CANCELLED"}

        property_name = str(binding["property_name"])
        target_identity = (int(self.type_index), int(self.transform_index))
        bindings = load_timl_bindings_raw(controller)
        bindings = _seed_missing_binding_source_origins(
            bindings,
            _safe_source_entry_for_controller_object(controller),
        )
        source_identity = None
        for item in bindings:
            if str(item["property_name"]) == property_name:
                source_identity = timl_binding_identity(item)
                break
        if source_identity is None:
            scene_props.last_status = "Could not find the selected TIML transform binding."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        occupied_by_other = any(
            str(other["property_name"]) != property_name
            and timl_binding_identity(other) == target_identity
            for other in bindings
        )
        if occupied_by_other:
            bindings = move_timl_transform_binding(
                bindings,
                source_type_index=int(source_identity[0]),
                source_transform_index=int(source_identity[1]),
                target_type_index=int(target_identity[0]),
                target_transform_index=int(target_identity[1]),
            )

        old_data_type = int(binding["data_type"])
        new_data_type = int(self.data_type)
        updated_binding = None
        for item in bindings:
            if str(item["property_name"]) != property_name:
                continue
            item["type_index"] = int(self.type_index)
            item["transform_index"] = int(self.transform_index)
            item["timeline_parameter_hash"] = _parse_hex_u32(self.timeline_hash_hex)
            item["datatype_hash"] = _parse_hex_u32(self.datatype_hash_hex)
            item["data_type"] = new_data_type
            item["data_type_name"] = _data_type_name_for_key(str(new_data_type))
            updated_binding = item
            break
        _save_timl_bindings_with_preview_groups(controller, bindings)

        action = _controller_action(controller)
        if old_data_type != new_data_type and action is not None:
            preview_value = default_preview_value_for_data_type(new_data_type)
            if property_name in controller:
                del controller[property_name]
            ensure_binding_preview_property(
                controller,
                updated_binding or binding,
                preview_value=preview_value,
            )
            remove_binding_preview_fcurves(action, property_name)
            create_binding_preview_fcurves(
                action,
                updated_binding or binding,
                frame=0.0,
                preview_value=preview_value,
            )
            _ensure_controller_action_slot_binding(controller, action)
            _retag_controller_preview_groups(controller)

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
        transform = _selected_controller_transform(scene_props)
        defaults = seed_add_timl_type_defaults(
            bindings,
            selected_block=block,
            selected_transform=transform,
            data_type_items=TIML_DATA_TYPE_ITEMS,
        )
        self.type_index = int(defaults.type_index)
        self.timeline_hash_hex = str(defaults.timeline_hash_hex)
        self.datatype_hash_hex = str(defaults.datatype_hash_hex)
        self.data_type = str(defaults.data_type_key)
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
            bindings = _seed_missing_binding_source_origins(
                bindings,
                _safe_source_entry_for_controller_object(controller),
            )
            bindings = insert_timl_type_slot(bindings, type_index=int(self.type_index))
            _save_timl_bindings_with_preview_groups(controller, bindings)
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
            _ensure_controller_action_slot_binding(controller, action)
            _set_action_transform_count(controller, len(load_timl_bindings_raw(controller)))
        _refresh_timl_controller_after_edit(context, controller)
        _select_workspace_identity(scene_props, property_name=str(binding["property_name"]), type_index=int(self.type_index))
        scene_props.last_status = f"Added type {int(self.type_index):02d}."
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_materialize_timl_transform_preview(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.materialize_timl_transform_preview"
    bl_label = "Create Preview Binding"
    bl_description = "Recreate editable Blender preview curves for the selected source TIML transform"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        if controller is None:
            scene_props.last_status = "Choose an imported TIML controller first."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        binding, error_message = _materialize_preview_binding_from_source(context, controller, scene_props)
        if binding is None:
            scene_props.last_status = error_message or "Could not create a preview binding for the selected TIML transform."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        scene_props.last_status = (
            f"Created editable preview curves for T{int(binding['type_index']):02d}:X{int(binding['transform_index']):02d}."
        )
        self.report({"INFO"}, scene_props.last_status)
        return {"FINISHED"}


class MHWANIMTOOLS_OT_materialize_timl_block_previews(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.materialize_timl_block_previews"
    bl_label = "Create Block Previews"
    bl_description = "Create editable Blender preview curves for every source-backed transform in the selected TIML block"

    def execute(self, context):
        scene_props = context.scene.mhw_anim_tools
        controller = _resolve_timl_controller(context)
        block = _selected_timl_block(scene_props)
        if controller is None or block is None:
            scene_props.last_status = "Choose a TIML type first."
            add_diagnostic(scene_props, "ERROR", "timl.block", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        existing_count = sum(
            1
            for binding in load_timl_bindings_raw(controller)
            if int(binding["type_index"]) == int(block.type_index)
        )
        bindings, error_message = _materialize_type_preview_bindings_from_source(
            context,
            controller,
            scene_props,
            int(block.type_index),
        )
        if not bindings:
            scene_props.last_status = error_message or "Could not create preview curves for the selected TIML block."
            add_diagnostic(scene_props, "ERROR", "timl.block", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        created_count = max(0, len(bindings) - int(existing_count))
        if created_count <= 0:
            scene_props.last_status = f"Type {int(block.type_index):02d} already has preview curves for every source transform."
        else:
            scene_props.last_status = (
                f"Created {created_count} preview entr{'y' if created_count == 1 else 'ies'} "
                f"for type {int(block.type_index):02d}."
            )
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
        source_transform_count = sum(
            1
            for item in scene_props.timl_controller_transforms
            if int(item.type_index) == source_type_index
        )
        source_bindings = [
            binding
            for binding in bindings
            if int(binding["type_index"]) == source_type_index
        ]
        if len(source_bindings) < source_transform_count:
            created_bindings, error_message = _materialize_type_preview_bindings_from_source(
                context,
                controller,
                scene_props,
                source_type_index,
            )
            if not source_bindings and not created_bindings:
                scene_props.last_status = error_message or "The selected TIML type has no transforms to duplicate."
                add_diagnostic(scene_props, "ERROR", "timl.type", scene_props.last_status)
                self.report({"WARNING"}, scene_props.last_status)
                return {"CANCELLED"}
            bindings = load_timl_bindings_raw(controller)
            source_bindings = [
                binding
                for binding in bindings
                if int(binding["type_index"]) == source_type_index
            ]
        source_bindings_snapshot = [dict(binding) for binding in source_bindings]
        if any(int(binding["type_index"]) == target_type_index for binding in bindings):
            bindings = _seed_missing_binding_source_origins(
                bindings,
                _safe_source_entry_for_controller_object(controller),
            )
            bindings = insert_timl_type_slot(bindings, type_index=target_type_index)
            _save_timl_bindings_with_preview_groups(controller, bindings)
        action = _controller_action(controller)
        first_property_name = ""
        for source_binding in sorted(source_bindings_snapshot, key=lambda item: int(item["transform_index"])):
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
            _ensure_controller_action_slot_binding(controller, action)
            _set_action_transform_count(controller, len(load_timl_bindings_raw(controller)))
            _retag_controller_preview_groups(controller)
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
        type_identities = {
            (int(item.type_index), int(item.transform_index))
            for item in scene_props.timl_controller_transforms
            if int(item.type_index) == type_index
        }
        source_entry = _safe_source_entry_for_controller_object(controller)
        bindings = _seed_missing_binding_source_origins(bindings, source_entry)
        source_backed_identities = {
            _binding_source_identity_for_entry(binding, source_entry)
            for binding in bindings
            if int(binding["type_index"]) == type_index
        }
        source_backed_identities.update(
            identity
            for identity in type_identities
            if _source_identity_exists(source_entry, identity)
        )
        source_backed_identities.discard(None)
        if not any(int(binding["type_index"]) == type_index for binding in bindings) and not source_backed_identities:
            scene_props.last_status = "The selected TIML type has no editable transforms."
            add_diagnostic(scene_props, "ERROR", "timl.type", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        action = _controller_action(controller)
        updated_bindings, removed_property_names = delete_timl_type_bindings(bindings, type_index=type_index)
        _save_timl_bindings_with_preview_groups(controller, updated_bindings)
        for property_name in removed_property_names:
            if action is not None:
                remove_binding_preview_fcurves(action, property_name)
            if property_name in controller:
                del controller[property_name]
            remove_timl_binding(controller, property_name)
        for source_type_index, source_transform_index in source_backed_identities:
            mark_deleted_timl_identity(
                controller,
                type_index=int(source_type_index),
                transform_index=int(source_transform_index),
            )
        if action is not None:
            _set_action_transform_count(controller, len(load_timl_bindings_raw(controller)))
        _refresh_timl_controller_after_edit(context, controller)
        if source_backed_identities:
            scene_props.last_status = (
                f"Marked type {type_index:02d} for deletion from the source TIML payload."
            )
        else:
            scene_props.last_status = f"Deleted local type {type_index:02d}."
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
        defaults = seed_add_timl_transform_defaults(
            bindings,
            selected_block=block,
            selected_transform=transform,
            data_type_items=TIML_DATA_TYPE_ITEMS,
        )
        self.type_index = int(defaults.type_index)
        self.transform_index = int(defaults.transform_index)
        self.timeline_hash_hex = str(defaults.timeline_hash_hex)
        self.datatype_hash_hex = str(defaults.datatype_hash_hex)
        self.data_type = str(defaults.data_type_key)
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
            bindings = _seed_missing_binding_source_origins(
                bindings,
                _safe_source_entry_for_controller_object(controller),
            )
            bindings = insert_timl_transform_slot(
                bindings,
                type_index=int(self.type_index),
                transform_index=int(self.transform_index),
            )
            _save_timl_bindings_with_preview_groups(controller, bindings)
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
            _ensure_controller_action_slot_binding(controller, action)
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
        if controller is None:
            scene_props.last_status = "Choose a TIML transform first."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        if binding is None:
            binding, error_message = _materialize_preview_binding_from_source(context, controller, scene_props)
            if binding is None:
                scene_props.last_status = error_message or "Choose a TIML transform first."
                add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
                self.report({"WARNING"}, scene_props.last_status)
                return {"CANCELLED"}
        bindings = load_timl_bindings_raw(controller)
        target_identity = (int(self.target_type_index), int(self.target_transform_index))
        if any((int(item["type_index"]), int(item["transform_index"])) == target_identity for item in bindings):
            bindings = _seed_missing_binding_source_origins(
                bindings,
                _safe_source_entry_for_controller_object(controller),
            )
            bindings = insert_timl_transform_slot(
                bindings,
                type_index=int(self.target_type_index),
                transform_index=int(self.target_transform_index),
            )
            _save_timl_bindings_with_preview_groups(controller, bindings)
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
            _ensure_controller_action_slot_binding(controller, action)
            _set_action_transform_count(controller, len(load_timl_bindings_raw(controller)))
            _retag_controller_preview_groups(controller)
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
            bindings = _seed_missing_binding_source_origins(
                bindings,
                _safe_source_entry_for_controller_object(target_controller),
            )
            bindings = insert_timl_transform_slot(
                bindings,
                type_index=int(self.target_type_index),
                transform_index=int(self.target_transform_index),
            )
            _save_timl_bindings_with_preview_groups(target_controller, bindings)
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
                _ensure_controller_action_slot_binding(target_controller, target_action)
            _set_action_transform_count(target_controller, len(load_timl_bindings_raw(target_controller)))
            _retag_controller_preview_groups(target_controller)
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
        transform = _selected_controller_transform(scene_props)
        binding = _binding_for_selected_transform(controller, scene_props) if controller is not None else None
        if controller is None:
            scene_props.last_status = "Choose a TIML transform first."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        identity = None
        if transform is not None:
            identity = (int(transform.type_index), int(transform.transform_index))
        elif binding is not None:
            identity = (int(binding["type_index"]), int(binding["transform_index"]))
        if identity is None:
            scene_props.last_status = "Choose a TIML transform first."
            add_diagnostic(scene_props, "ERROR", "timl.transform", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}
        source_entry = _safe_source_entry_for_controller_object(controller)
        source_backed_identity = None
        bindings = load_timl_bindings_raw(controller)
        bindings = _seed_missing_binding_source_origins(bindings, source_entry)
        if binding is not None:
            selected_binding = next(
                (
                    item
                    for item in bindings
                    if str(item["property_name"]) == str(binding["property_name"])
                ),
                None,
            )
            if selected_binding is not None:
                source_backed_identity = _binding_source_identity_for_entry(selected_binding, source_entry)
        if source_backed_identity is None and _source_identity_exists(source_entry, identity):
            source_backed_identity = identity
        action = _controller_action(controller)
        if binding is not None:
            updated_bindings, removed_binding = delete_timl_transform_binding(
                bindings,
                type_index=int(identity[0]),
                transform_index=int(identity[1]),
            )
            property_name = str((removed_binding or {}).get("property_name", binding["property_name"]))
            _save_timl_bindings_with_preview_groups(controller, updated_bindings)
            if action is not None:
                remove_binding_preview_fcurves(action, property_name)
            if property_name in controller:
                del controller[property_name]
            remove_timl_binding(controller, property_name)
        if source_backed_identity is not None:
            mark_deleted_timl_identity(
                controller,
                type_index=int(source_backed_identity[0]),
                transform_index=int(source_backed_identity[1]),
            )
        else:
            clear_deleted_timl_identity(
                controller,
                type_index=int(identity[0]),
                transform_index=int(identity[1]),
            )
        if action is not None:
            _set_action_transform_count(controller, len(load_timl_bindings_raw(controller)))
        _refresh_timl_controller_after_edit(context, controller)
        if source_backed_identity is not None:
            scene_props.last_status = (
                f"Marked transform {int(source_backed_identity[0]):02d}:{int(source_backed_identity[1]):02d} "
                "for deletion from the source TIML payload."
            )
        else:
            scene_props.last_status = f"Deleted local transform {identity[0]:02d}:{identity[1]:02d}."
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
            scene_props.last_status = "Choose a TIML type first."
            add_diagnostic(scene_props, "ERROR", "timl.block", scene_props.last_status)
            self.report({"WARNING"}, scene_props.last_status)
            return {"CANCELLED"}

        try:
            property_names = json.loads(block.property_names_json)
        except json.JSONDecodeError:
            property_names = []
        match_count = _select_controller_curves_by_property_names(controller, property_names)
        if match_count <= 0:
            scene_props.last_status = (
                f"No preview curves were found for {block.block_label or 'this block'}. "
                "Create block previews first if you want direct Graph Editor editing."
            )
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
            scene_props.last_status = (
                f"No preview curves were found for {field_name}. "
                "Create a preview binding first if you want direct Graph Editor editing."
            )
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
            scene_props.last_status = (
                f"No preview curves were found for {transform.semantic_label or transform.property_name}. "
                "Create a preview binding first if you want direct Graph Editor editing."
            )
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
        clear_timl_analysis(scene_props)
        try:
            bpy.ops.mhw_anim_tools.analyze_timl_controller()
        except RuntimeError:
            pass
        scene_props.last_status = (
            f"Created an EventLoop TIML block for entry {entry_id:03d}. "
            "Use TIML Workspace and Graph Editor to adjust the loop fields."
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
    MHWANIMTOOLS_OT_materialize_timl_transform_preview,
    MHWANIMTOOLS_OT_materialize_timl_block_previews,
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
