"""Generic raw TIML controller authoring helpers."""

from __future__ import annotations

import json
import re

try:
    from ..core.formats.timl.model import timl_data_type_name
    from ..core.formats.timl.semantics import get_data_type_semantics
    from .timl_metadata import TIML_BINDING_META_PREFIX
    from .timl_metadata import TIML_BINDINGS_KEY
    from .timl_metadata import TIML_HEADER_ANIMATION_LENGTH_KEY
    from .timl_metadata import TIML_HEADER_DATA_INDEX_A_KEY
    from .timl_metadata import TIML_HEADER_DATA_INDEX_B_KEY
    from .timl_metadata import TIML_HEADER_LABEL_HASH_KEY
    from .timl_metadata import TIML_HEADER_LOOP_CONTROL_KEY
    from .timl_metadata import TIML_HEADER_LOOP_START_POINT_KEY
    from .timl_metadata import TIML_PROPERTY_LIST_KEY
    from .timl_templates import build_stable_timl_label_hash
except ImportError:  # pragma: no cover - test runner imports from addon root
    from core.formats.timl.model import timl_data_type_name
    from core.formats.timl.semantics import get_data_type_semantics
    from blender_adapter.timl_metadata import TIML_BINDING_META_PREFIX
    from blender_adapter.timl_metadata import TIML_BINDINGS_KEY
    from blender_adapter.timl_metadata import TIML_HEADER_ANIMATION_LENGTH_KEY
    from blender_adapter.timl_metadata import TIML_HEADER_DATA_INDEX_A_KEY
    from blender_adapter.timl_metadata import TIML_HEADER_DATA_INDEX_B_KEY
    from blender_adapter.timl_metadata import TIML_HEADER_LABEL_HASH_KEY
    from blender_adapter.timl_metadata import TIML_HEADER_LOOP_CONTROL_KEY
    from blender_adapter.timl_metadata import TIML_HEADER_LOOP_START_POINT_KEY
    from blender_adapter.timl_metadata import TIML_PROPERTY_LIST_KEY
    from blender_adapter.timl_templates import build_stable_timl_label_hash


_SLUG = re.compile(r"[^0-9A-Za-z_]+")
HEADER_KEYS = (
    TIML_HEADER_DATA_INDEX_A_KEY,
    TIML_HEADER_DATA_INDEX_B_KEY,
    TIML_HEADER_ANIMATION_LENGTH_KEY,
    TIML_HEADER_LOOP_START_POINT_KEY,
    TIML_HEADER_LOOP_CONTROL_KEY,
    TIML_HEADER_LABEL_HASH_KEY,
)
DEFAULT_COMPONENT_LABELS = {
    3: ("r", "g", "b", "a"),
}


def _slugify(text: str) -> str:
    return _SLUG.sub("_", str(text or "")).strip("_").lower() or "value"


def _binding_prop_name_from_identity(type_index: int, transform_index: int, timeline_hash: int, datatype_hash: int) -> str:
    return (
        f"timl_t{int(type_index):02d}_x{int(transform_index):02d}_"
        f"{int(timeline_hash) & 0xFFFFFFFF:08x}_{int(datatype_hash) & 0xFFFFFFFF:08x}"
    )


def _binding_meta_key(property_name: str, field_name: str) -> str:
    return f"{TIML_BINDING_META_PREFIX}{_slugify(property_name)}_{field_name}"


def _default_component_labels_for_data_type(data_type: int) -> tuple[str, ...]:
    semantics = get_data_type_semantics(int(data_type))
    if int(data_type) in DEFAULT_COMPONENT_LABELS:
        return DEFAULT_COMPONENT_LABELS[int(data_type)]
    if int(semantics.value_dimension) <= 1:
        return ("value",)
    return tuple(f"c{index}" for index in range(int(semantics.value_dimension)))


def default_preview_value_for_data_type(data_type: int) -> tuple[float, ...]:
    semantics = get_data_type_semantics(int(data_type))
    if int(data_type) == 3:
        return (1.0, 1.0, 1.0, 1.0)
    if int(semantics.value_dimension) <= 1:
        return (0.0,)
    return tuple(0.0 for _index in range(int(semantics.value_dimension)))


def load_timl_property_names(controller_object) -> list[str]:
    raw_value = controller_object.get(TIML_PROPERTY_LIST_KEY, "") if controller_object is not None else ""
    if not isinstance(raw_value, str) or not raw_value:
        return []
    try:
        decoded = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return [str(item) for item in decoded if str(item)]


def save_timl_property_names(controller_object, property_names) -> None:
    controller_object[TIML_PROPERTY_LIST_KEY] = json.dumps(
        [str(name) for name in property_names if str(name)],
        separators=(",", ":"),
    )


def load_timl_bindings_raw(controller_object) -> list[dict[str, object]]:
    raw_value = controller_object.get(TIML_BINDINGS_KEY, "") if controller_object is not None else ""
    if not isinstance(raw_value, str) or not raw_value:
        return []
    try:
        decoded = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    bindings: list[dict[str, object]] = []
    for entry in decoded:
        if not isinstance(entry, dict):
            continue
        property_name = str(entry.get("property_name", "") or "")
        if not property_name:
            continue
        data_type = int(entry.get("data_type", 0) or 0)
        bindings.append(
            {
                "property_name": property_name,
                "type_index": int(entry.get("type_index", 0) or 0),
                "transform_index": int(entry.get("transform_index", 0) or 0),
                "timeline_parameter_hash": int(entry.get("timeline_parameter_hash", 0) or 0),
                "datatype_hash": int(entry.get("datatype_hash", 0) or 0),
                "data_type": data_type,
                "data_type_name": str(entry.get("data_type_name", "") or timl_data_type_name(data_type)),
                "component_labels": list(entry.get("component_labels", ()) or _default_component_labels_for_data_type(data_type)),
                "normalized_color": bool(entry.get("normalized_color", int(data_type) == 3)),
            }
        )
    return bindings


def save_timl_bindings_raw(controller_object, bindings: list[dict[str, object]]) -> None:
    encoded = []
    for binding in bindings:
        data_type = int(binding.get("data_type", 0) or 0)
        encoded.append(
            {
                "property_name": str(binding.get("property_name", "") or ""),
                "type_index": int(binding.get("type_index", 0) or 0),
                "transform_index": int(binding.get("transform_index", 0) or 0),
                "timeline_parameter_hash": int(binding.get("timeline_parameter_hash", 0) or 0),
                "datatype_hash": int(binding.get("datatype_hash", 0) or 0),
                "data_type": data_type,
                "data_type_name": str(binding.get("data_type_name", "") or timl_data_type_name(data_type)),
                "component_labels": list(binding.get("component_labels", ()) or _default_component_labels_for_data_type(data_type)),
                "normalized_color": bool(binding.get("normalized_color", int(data_type) == 3)),
            }
        )
    controller_object[TIML_BINDINGS_KEY] = json.dumps(encoded, separators=(",", ":"))
    sync_timl_binding_meta_props_from_bindings(controller_object)


def sync_timl_binding_meta_props_from_bindings(controller_object) -> None:
    bindings = load_timl_bindings_raw(controller_object)
    expected_keys: set[str] = set()
    for binding in bindings:
        property_name = str(binding["property_name"])
        values = {
            "type_index": int(binding["type_index"]),
            "transform_index": int(binding["transform_index"]),
            "timeline_hash": int(binding["timeline_parameter_hash"]) & 0xFFFFFFFF,
            "datatype_hash": int(binding["datatype_hash"]) & 0xFFFFFFFF,
            "data_type": int(binding["data_type"]),
        }
        for field_name, value in values.items():
            prop_key = _binding_meta_key(property_name, field_name)
            controller_object[prop_key] = value
            expected_keys.add(prop_key)
    stale_keys = [
        key
        for key in controller_object.keys()
        if str(key).startswith(TIML_BINDING_META_PREFIX) and str(key) not in expected_keys
    ]
    for key in stale_keys:
        del controller_object[key]


def sync_timl_bindings_from_meta_props(controller_object) -> list[dict[str, object]]:
    bindings = load_timl_bindings_raw(controller_object)
    for binding in bindings:
        property_name = str(binding["property_name"])
        binding["type_index"] = int(controller_object.get(_binding_meta_key(property_name, "type_index"), binding["type_index"]))
        binding["transform_index"] = int(controller_object.get(_binding_meta_key(property_name, "transform_index"), binding["transform_index"]))
        binding["timeline_parameter_hash"] = int(
            controller_object.get(_binding_meta_key(property_name, "timeline_hash"), binding["timeline_parameter_hash"])
        ) & 0xFFFFFFFF
        binding["datatype_hash"] = int(
            controller_object.get(_binding_meta_key(property_name, "datatype_hash"), binding["datatype_hash"])
        ) & 0xFFFFFFFF
        binding["data_type"] = int(controller_object.get(_binding_meta_key(property_name, "data_type"), binding["data_type"]))
        binding["data_type_name"] = timl_data_type_name(int(binding["data_type"]))
        binding["component_labels"] = list(_default_component_labels_for_data_type(int(binding["data_type"])))
        binding["normalized_color"] = int(binding["data_type"]) == 3
    save_timl_bindings_raw(controller_object, bindings)
    return bindings


def ensure_timl_header_props(
    controller_object,
    *,
    source_lmt: str = "",
    entry_id: int = 0,
    data_index_a: int = 0,
    data_index_b: int = 0,
    animation_length: float = 0.0,
    loop_start_point: float = 0.0,
    loop_control: int = 0,
    label_hash: int = 0,
) -> None:
    resolved_label_hash = int(label_hash) & 0xFFFFFFFF
    if resolved_label_hash == 0:
        resolved_label_hash = build_stable_timl_label_hash(str(source_lmt or ""), int(entry_id))
    controller_object[TIML_HEADER_DATA_INDEX_A_KEY] = int(data_index_a)
    controller_object[TIML_HEADER_DATA_INDEX_B_KEY] = int(data_index_b)
    controller_object[TIML_HEADER_ANIMATION_LENGTH_KEY] = float(animation_length)
    controller_object[TIML_HEADER_LOOP_START_POINT_KEY] = float(loop_start_point)
    controller_object[TIML_HEADER_LOOP_CONTROL_KEY] = int(loop_control)
    controller_object[TIML_HEADER_LABEL_HASH_KEY] = int(resolved_label_hash)


def timl_header_state_from_controller(controller_object, *, source_lmt: str = "", entry_id: int = 0) -> dict[str, object]:
    ensure_timl_header_props(
        controller_object,
        source_lmt=source_lmt,
        entry_id=entry_id,
        data_index_a=int(controller_object.get(TIML_HEADER_DATA_INDEX_A_KEY, 0) or 0),
        data_index_b=int(controller_object.get(TIML_HEADER_DATA_INDEX_B_KEY, 0) or 0),
        animation_length=float(controller_object.get(TIML_HEADER_ANIMATION_LENGTH_KEY, 0.0) or 0.0),
        loop_start_point=float(controller_object.get(TIML_HEADER_LOOP_START_POINT_KEY, 0.0) or 0.0),
        loop_control=int(controller_object.get(TIML_HEADER_LOOP_CONTROL_KEY, 0) or 0),
        label_hash=int(controller_object.get(TIML_HEADER_LABEL_HASH_KEY, 0) or 0),
    )
    return {
        "data_index_a": int(controller_object.get(TIML_HEADER_DATA_INDEX_A_KEY, 0) or 0),
        "data_index_b": int(controller_object.get(TIML_HEADER_DATA_INDEX_B_KEY, 0) or 0),
        "animation_length": float(controller_object.get(TIML_HEADER_ANIMATION_LENGTH_KEY, 0.0) or 0.0),
        "loop_start_point": float(controller_object.get(TIML_HEADER_LOOP_START_POINT_KEY, 0.0) or 0.0),
        "loop_control": int(controller_object.get(TIML_HEADER_LOOP_CONTROL_KEY, 0) or 0),
        "label_hash": int(controller_object.get(TIML_HEADER_LABEL_HASH_KEY, 0) or 0) & 0xFFFFFFFF,
    }


def append_timl_binding(
    controller_object,
    *,
    property_name: str | None = None,
    type_index: int,
    transform_index: int,
    timeline_parameter_hash: int,
    datatype_hash: int,
    data_type: int,
) -> dict[str, object]:
    bindings = load_timl_bindings_raw(controller_object)
    binding = {
        "property_name": str(property_name or _binding_prop_name_from_identity(type_index, transform_index, timeline_parameter_hash, datatype_hash)),
        "type_index": int(type_index),
        "transform_index": int(transform_index),
        "timeline_parameter_hash": int(timeline_parameter_hash) & 0xFFFFFFFF,
        "datatype_hash": int(datatype_hash) & 0xFFFFFFFF,
        "data_type": int(data_type),
        "data_type_name": timl_data_type_name(int(data_type)),
        "component_labels": list(_default_component_labels_for_data_type(int(data_type))),
        "normalized_color": int(data_type) == 3,
    }
    bindings.append(binding)
    save_timl_bindings_raw(controller_object, bindings)
    property_names = load_timl_property_names(controller_object)
    if binding["property_name"] not in property_names:
        property_names.append(binding["property_name"])
        save_timl_property_names(controller_object, property_names)
    return binding


def remove_timl_binding(controller_object, property_name: str) -> None:
    property_name = str(property_name or "")
    bindings = [binding for binding in load_timl_bindings_raw(controller_object) if str(binding["property_name"]) != property_name]
    save_timl_bindings_raw(controller_object, bindings)
    property_names = [name for name in load_timl_property_names(controller_object) if str(name) != property_name]
    save_timl_property_names(controller_object, property_names)
    for field_name in ("type_index", "transform_index", "timeline_hash", "datatype_hash", "data_type"):
        prop_key = _binding_meta_key(property_name, field_name)
        if prop_key in controller_object:
            del controller_object[prop_key]


def ensure_binding_preview_property(controller_object, binding: dict[str, object], *, preview_value=None) -> None:
    property_name = str(binding["property_name"])
    value = tuple(preview_value or default_preview_value_for_data_type(int(binding["data_type"])))
    if len(value) == 1:
        controller_object[property_name] = float(value[0])
    else:
        controller_object[property_name] = [float(component) for component in value]


def create_binding_preview_fcurves(action, binding: dict[str, object], *, frame: float = 0.0, preview_value=None) -> None:
    try:
        from .fcurves import create_action_fcurves
        from .fcurves import create_scalar_action_fcurve
    except ImportError:  # pragma: no cover - test runner imports from addon root
        from blender_adapter.fcurves import create_action_fcurves
        from blender_adapter.fcurves import create_scalar_action_fcurve

    property_name = str(binding["property_name"])
    value = tuple(preview_value or default_preview_value_for_data_type(int(binding["data_type"])))
    action_group = f"TIML {int(binding['type_index']):02d}:{int(binding['transform_index']):02d}"
    if len(value) == 1:
        create_scalar_action_fcurve(
            action,
            data_path=f'["{property_name}"]',
            action_group=action_group,
            keyframes=[(float(frame), float(value[0]))],
            interpolations=[1],
        )
        return
    channel_values = [[(float(frame), float(component))] for component in value]
    channel_interpolations = [[1] for _index in value]
    create_action_fcurves(
        action,
        data_path=f'["{property_name}"]',
        action_group=action_group,
        channel_values=channel_values,
        channel_interpolations=channel_interpolations,
    )


def clone_binding_preview_fcurves(action, *, source_property_name: str, target_property_name: str) -> None:
    source_path = f'["{str(source_property_name)}"]'
    target_path = f'["{str(target_property_name)}"]'
    source_fcurves = [
        fcurve
        for fcurve in getattr(action, "fcurves", ())
        if str(getattr(fcurve, "data_path", "")) == source_path
    ]
    for source_fcurve in source_fcurves:
        target_fcurve = action.fcurves.new(
            data_path=target_path,
            index=int(getattr(source_fcurve, "array_index", 0)),
            action_group=str(getattr(source_fcurve, "group", None).name if getattr(source_fcurve, "group", None) else "TIML"),
        )
        points = list(getattr(source_fcurve, "keyframe_points", ()))
        target_fcurve.keyframe_points.add(len(points))
        for index, point in enumerate(points):
            target_point = target_fcurve.keyframe_points[index]
            target_point.co = tuple(point.co)
            target_point.interpolation = str(getattr(point, "interpolation", "LINEAR") or "LINEAR")
        target_fcurve.update()


def remove_binding_preview_fcurves(action, property_name: str) -> None:
    data_path = f'["{str(property_name)}"]'
    for fcurve in list(getattr(action, "fcurves", ())):
        if str(getattr(fcurve, "data_path", "")) == data_path:
            action.fcurves.remove(fcurve)
