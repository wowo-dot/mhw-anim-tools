"""Import attached TIML payloads into Blender custom-property actions."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import bpy

from .timl_authoring import ensure_timl_header_props
from .timl_authoring import load_timl_property_names
from .timl_authoring import save_timl_bindings_raw
from .timl_authoring import save_timl_property_names
from ..core.formats.timl.channels import build_timl_transform_samples
from ..core.formats.timl.reader import read_timl_data_bytes
from ..core.formats.timl.semantics import format_datatype_hash_label
from ..core.formats.timl.semantics import format_timeline_parameter_label
from .fcurves import clear_action_fcurves
from .fcurves import assign_action
from .fcurves import clear_action_assignment
from .fcurves import create_action_fcurves
from .fcurves import create_scalar_action_fcurve
from .fcurves import ensure_action
from .fcurves import ensure_object_animation_data
from .timl_metadata import TIML_ACTION_NAME_KEY
from .timl_metadata import TIML_BINDINGS_KEY
from .timl_metadata import TIML_BINDING_META_PREFIX
from .timl_metadata import TIML_DELETED_BINDINGS_KEY
from .timl_metadata import TIML_ENTRY_ID_KEY
from .timl_metadata import TIML_HEADER_ANIMATION_LENGTH_KEY
from .timl_metadata import TIML_HEADER_DATA_INDEX_A_KEY
from .timl_metadata import TIML_HEADER_DATA_INDEX_B_KEY
from .timl_metadata import TIML_HEADER_LABEL_HASH_KEY
from .timl_metadata import TIML_HEADER_LOOP_CONTROL_KEY
from .timl_metadata import TIML_HEADER_LOOP_START_POINT_KEY
from .timl_metadata import TIML_IMPORTED_PREVIEW_SIGNATURE_KEY
from .timl_metadata import TIML_PROPERTY_LIST_KEY
from .timl_metadata import TIML_SESSION_ID_KEY
from .timl_metadata import TIML_SOURCE_ENTRY_COUNT_KEY
from .timl_metadata import TIML_SOURCE_ENTRY_IDS_KEY
from .timl_metadata import TIML_SOURCE_KIND_ATTACHED_LMT
from .timl_metadata import TIML_SOURCE_KIND_KEY
from .timl_metadata import TIML_SOURCE_KIND_STANDALONE_FILE
from .timl_preview_state import imported_preview_signature_json
from .timl_metadata import TIML_SOURCE_LMT_KEY
from .timl_metadata import TIML_SOURCE_OFFSET_KEY
from .timl_templates import clear_timl_template_metadata
from .timl_templates import default_event_loop_template_header
from .timl_templates import EVENT_LOOP_MFLAG_HASH
from .timl_templates import EVENT_LOOP_RELEASE_TIME_A_HASH
from .timl_templates import EVENT_LOOP_REQNO_A_HASH
from .timl_templates import EVENT_LOOP_TEMPLATE_KIND
from .timl_templates import EVENT_LOOP_TIMELINE_HASH
from .timl_templates import DEFAULT_EVENT_LOOP_FLAG_OFF
from .timl_templates import DEFAULT_EVENT_LOOP_FLAG_ON
from .timl_templates import DEFAULT_EVENT_LOOP_RELEASE_TIME_A
from .timl_templates import DEFAULT_EVENT_LOOP_REQNO_A
from .timl_templates import set_timl_template_metadata
from ..core.formats.timl.reader import read_timl_bytes


SUPPORTED_TIML_DATA_TYPES = {0, 1, 2, 3, 4}
EXACT_INTEGER_FLOAT_LIMIT = 16_777_216


@dataclass(frozen=True)
class ImportDiagnostic:
    level: str
    source: str
    message: str


@dataclass
class ImportTimlResult:
    action_name: str = ""
    carrier_name: str = ""
    imported_transform_count: int = 0
    skipped_transform_count: int = 0
    created_fcurve_count: int = 0
    frame_end: int = 0
    diagnostics: list[ImportDiagnostic] = field(default_factory=list)

    def add(self, level: str, source: str, message: str):
        self.diagnostics.append(ImportDiagnostic(level=level, source=source, message=message))

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "WARNING")

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "ERROR")


@dataclass
class ImportTimlFileResult:
    source_path: str = ""
    session_id: str = ""
    imported_entry_ids: list[int] = field(default_factory=list)
    imported_action_names: list[str] = field(default_factory=list)
    imported_carrier_names: list[str] = field(default_factory=list)
    imported_transform_count: int = 0
    skipped_entry_count: int = 0
    frame_end: int = 0
    diagnostics: list[ImportDiagnostic] = field(default_factory=list)

    def add(self, level: str, source: str, message: str):
        self.diagnostics.append(ImportDiagnostic(level=level, source=source, message=message))

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "WARNING")

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "ERROR")

    @property
    def imported_entry_count(self) -> int:
        return len(self.imported_entry_ids)

    @property
    def last_action_name(self) -> str:
        return self.imported_action_names[-1] if self.imported_action_names else ""

    @property
    def last_carrier_name(self) -> str:
        return self.imported_carrier_names[-1] if self.imported_carrier_names else ""


def _scene_frame_int(value) -> int:
    return int(math.ceil(float(value)))


def _slugify_label(label: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", str(label)).strip("_").lower()
    return cleaned or "value"


def _action_name_for_import(source_path: str, action_id: int) -> str:
    stem = Path(source_path).stem
    return f"TIML::{stem}::{action_id:03d}"


def _carrier_name_for_import(source_path: str, action_id: int) -> str:
    stem = Path(source_path).stem
    return f"TIML Controller::{stem}::{action_id:03d}"


def _carrier_parent_name_for_import(source_path: str) -> str:
    return Path(source_path).stem or "TIML"


def _preferred_collection(target_armature):
    if target_armature is not None and target_armature.users_collection:
        return target_armature.users_collection[0]
    return bpy.context.scene.collection


def _ensure_timl_source_parent(source_path: str, *, target_armature=None):
    name = _carrier_parent_name_for_import(source_path)
    parent = bpy.data.objects.get(name)
    if parent is not None:
        if parent.type != "EMPTY":
            raise TypeError(f"Object '{name}' already exists and is not an Empty TIML parent.")
    else:
        parent = bpy.data.objects.new(name, None)
        parent.empty_display_type = "SINGLE_ARROW"
        parent.empty_display_size = 0.2
    collection = _preferred_collection(target_armature)
    if collection not in parent.users_collection:
        collection.objects.link(parent)
    return parent


def _ensure_timl_carrier_object(name: str, *, target_armature=None):
    carrier = bpy.data.objects.get(name)
    if carrier is not None:
        if carrier.type != "EMPTY":
            raise TypeError(f"Object '{name}' already exists and is not an Empty controller.")
    else:
        carrier = bpy.data.objects.new(name, None)
        carrier.empty_display_type = "PLAIN_AXES"
        carrier.empty_display_size = 0.15
    collection = _preferred_collection(target_armature)
    if collection not in carrier.users_collection:
        collection.objects.link(carrier)
    return carrier


def _load_json_list(raw_value) -> list[str]:
    if not isinstance(raw_value, str) or not raw_value:
        return []
    try:
        decoded = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return [str(item) for item in decoded]


def _entry_ids_json(entry_ids) -> str:
    return json.dumps(
        sorted({int(entry_id) for entry_id in entry_ids}),
        separators=(",", ":"),
    )


def _tag_timl_source_metadata(
    controller,
    blender_action,
    *,
    source_path: str,
    source_kind: str,
    entry_id: int,
    source_offset: int,
    source_entry_count: int = 0,
    session_id: str = "",
    source_entry_ids_json: str = "",
) -> None:
    blender_action["mhw_anim_tools_source_lmt"] = source_path
    blender_action["mhw_anim_tools_entry_id"] = int(entry_id)
    blender_action["mhw_anim_tools_source_timl_offset"] = int(source_offset)
    blender_action["mhw_anim_tools_timl_source_kind"] = str(source_kind or "")
    blender_action["mhw_anim_tools_timl_source_entry_count"] = int(source_entry_count)
    blender_action["mhw_anim_tools_timl_session_id"] = str(session_id or "")
    if source_entry_ids_json:
        blender_action["mhw_anim_tools_timl_source_entry_ids"] = str(source_entry_ids_json)
    elif "mhw_anim_tools_timl_source_entry_ids" in blender_action:
        del blender_action["mhw_anim_tools_timl_source_entry_ids"]

    controller[TIML_SOURCE_LMT_KEY] = source_path
    controller[TIML_SOURCE_KIND_KEY] = str(source_kind or "")
    controller[TIML_SOURCE_ENTRY_COUNT_KEY] = int(source_entry_count)
    if source_entry_ids_json:
        controller[TIML_SOURCE_ENTRY_IDS_KEY] = str(source_entry_ids_json)
    else:
        controller[TIML_SOURCE_ENTRY_IDS_KEY] = "[]"
    controller[TIML_ENTRY_ID_KEY] = int(entry_id)
    controller[TIML_SOURCE_OFFSET_KEY] = int(source_offset)
    controller[TIML_SESSION_ID_KEY] = str(session_id or "")
    controller[TIML_ACTION_NAME_KEY] = blender_action.name


def _clear_timl_carrier_properties(carrier):
    for prop_name in load_timl_property_names(carrier):
        if prop_name in carrier:
            del carrier[prop_name]
    for meta_key in list(carrier.keys()):
        if str(meta_key).startswith(TIML_BINDING_META_PREFIX):
            del carrier[meta_key]
    for header_key in (
        TIML_HEADER_DATA_INDEX_A_KEY,
        TIML_HEADER_DATA_INDEX_B_KEY,
        TIML_HEADER_ANIMATION_LENGTH_KEY,
        TIML_HEADER_LOOP_START_POINT_KEY,
        TIML_HEADER_LOOP_CONTROL_KEY,
        TIML_HEADER_LABEL_HASH_KEY,
    ):
        if header_key in carrier:
            del carrier[header_key]
    if TIML_PROPERTY_LIST_KEY in carrier:
        del carrier[TIML_PROPERTY_LIST_KEY]
    if TIML_BINDINGS_KEY in carrier:
        del carrier[TIML_BINDINGS_KEY]
    if TIML_IMPORTED_PREVIEW_SIGNATURE_KEY in carrier:
        del carrier[TIML_IMPORTED_PREVIEW_SIGNATURE_KEY]
    if TIML_DELETED_BINDINGS_KEY in carrier:
        del carrier[TIML_DELETED_BINDINGS_KEY]
    for metadata_key in (
        TIML_SOURCE_KIND_KEY,
        TIML_SOURCE_ENTRY_COUNT_KEY,
        TIML_SOURCE_ENTRY_IDS_KEY,
        TIML_SESSION_ID_KEY,
        TIML_SOURCE_LMT_KEY,
        TIML_ENTRY_ID_KEY,
        TIML_SOURCE_OFFSET_KEY,
        TIML_ACTION_NAME_KEY,
    ):
        if metadata_key in carrier:
            del carrier[metadata_key]
    clear_timl_template_metadata(carrier)


def _prop_name_for_transform(transform_samples) -> str:
    timeline_label = format_timeline_parameter_label(int(transform_samples.timeline_parameter_hash))
    datatype_label = format_datatype_hash_label(int(transform_samples.datatype_hash))
    return _slugify_label(
        f"timl_{timeline_label}_{datatype_label}_"
        f"t{transform_samples.type_index:02d}_x{transform_samples.transform_index:02d}"
    )


def _action_group_for_transform(transform_samples) -> str:
    timeline_label = format_timeline_parameter_label(int(transform_samples.timeline_parameter_hash))
    return f"TIML {timeline_label}"


def _display_name_for_transform(transform_samples) -> str:
    timeline_label = format_timeline_parameter_label(int(transform_samples.timeline_parameter_hash))
    datatype_label = format_datatype_hash_label(int(transform_samples.datatype_hash))
    return (
        f"TIML {transform_samples.type_index:02d}:{transform_samples.transform_index:02d} "
        f"{timeline_label} / {datatype_label} ({transform_samples.data_type_name})"
    )


def _adapt_key_value(transform_samples, value: tuple[float, ...]) -> tuple[float, ...]:
    if transform_samples.data_type == 3:
        return tuple(float(component) / 255.0 for component in value)
    if transform_samples.value_kind == "boolean":
        return (1.0 if bool(value[0]) else 0.0,)
    return tuple(float(component) for component in value)


def _has_advanced_interpolation(transform_samples) -> bool:
    return any(
        int(keyframe.interpolation) not in {0, 1} or int(keyframe.easing) != 0
        for keyframe in transform_samples.keyframes
    )


def _has_integer_precision_risk(transform_samples) -> bool:
    if transform_samples.value_kind not in {"integer", "boolean"}:
        return False
    return any(
        abs(float(component)) > EXACT_INTEGER_FLOAT_LIMIT
        for keyframe in transform_samples.keyframes
        for component in keyframe.value
    )


def _channel_data_for_transform(transform_samples):
    channel_count = transform_samples.component_count
    channel_values = [[] for _ in range(channel_count)]
    channel_interpolations = [[] for _ in range(channel_count)]
    for keyframe in transform_samples.keyframes:
        adapted_value = _adapt_key_value(transform_samples, keyframe.value)
        for index, component in enumerate(adapted_value):
            channel_values[index].append((float(keyframe.frame), float(component)))
            channel_interpolations[index].append(int(keyframe.interpolation))
    return channel_values, channel_interpolations


def _assign_carrier_property(carrier, prop_name: str, transform_samples):
    first_value = _adapt_key_value(transform_samples, transform_samples.keyframes[0].value)
    if len(first_value) == 1:
        carrier[prop_name] = float(first_value[0])
    else:
        carrier[prop_name] = [float(component) for component in first_value]
    try:
        carrier.id_properties_ui(prop_name).update(description=_display_name_for_transform(transform_samples))
    except AttributeError:
        pass


def _event_loop_preview_transform(
    *,
    transform_index: int,
    datatype_hash: int,
    values: tuple[tuple[float, tuple[float, ...]], ...],
):
    keyframes = tuple(
        SimpleNamespace(frame=float(frame), value=tuple(float(component) for component in value), interpolation=1)
        for frame, value in values
    )
    return SimpleNamespace(
        property_name="",
        type_index=0,
        transform_index=int(transform_index),
        timeline_parameter_hash=EVENT_LOOP_TIMELINE_HASH,
        datatype_hash=int(datatype_hash),
        data_type=1,
        data_type_name="uint32",
        value_kind="integer",
        control_kind="integer",
        component_labels=("value",),
        component_count=1,
        keyframes=keyframes,
    )


def seed_eventloop_template_on_controller(
    controller,
    *,
    source_path: str,
    entry_id: int,
    source_offset: int,
    animation_length: float,
    data_index_a: int = 0,
    data_index_b: int = 0,
    loop_start_point: float = 0.0,
    loop_control: int = 0,
    label_hash: int = 0,
):
    if controller is None:
        raise TypeError("TIML controller object is required before seeding an EventLoop template.")

    action_name = _action_name_for_import(source_path, entry_id)
    blender_action = ensure_action(action_name)
    clear_action_fcurves(blender_action)
    _clear_timl_carrier_properties(controller)

    template_header = default_event_loop_template_header(
        source_lmt=source_path,
        entry_id=int(entry_id),
        animation_length=float(animation_length),
        data_index_a=int(data_index_a),
        data_index_b=int(data_index_b),
        loop_start_point=float(loop_start_point),
        loop_control=int(loop_control),
        label_hash=int(label_hash),
    )
    frame_end = max(0.0, float(template_header.animation_length))
    transforms = (
        _event_loop_preview_transform(
            transform_index=0,
            datatype_hash=EVENT_LOOP_REQNO_A_HASH,
            values=((0.0, (float(DEFAULT_EVENT_LOOP_REQNO_A),)),),
        ),
        _event_loop_preview_transform(
            transform_index=1,
            datatype_hash=EVENT_LOOP_RELEASE_TIME_A_HASH,
            values=((0.0, (float(DEFAULT_EVENT_LOOP_RELEASE_TIME_A),)),),
        ),
        _event_loop_preview_transform(
            transform_index=2,
            datatype_hash=EVENT_LOOP_MFLAG_HASH,
            values=(
                (0.0, (float(DEFAULT_EVENT_LOOP_FLAG_ON),)),
                (frame_end, (float(DEFAULT_EVENT_LOOP_FLAG_OFF),)),
            ),
        ),
    )

    animation_data = ensure_object_animation_data(controller)
    blender_action["mhw_anim_tools_import_kind"] = "attached_timl"
    blender_action["mhw_anim_tools_timl_transform_count"] = int(len(transforms))

    property_names: list[str] = []
    bindings: list[dict[str, object]] = []
    for transform in transforms:
        prop_name = _prop_name_for_transform(transform)
        transform.property_name = prop_name
        property_names.append(prop_name)
        bindings.append(
            {
                "property_name": prop_name,
                "type_index": int(transform.type_index),
                "transform_index": int(transform.transform_index),
                "source_type_index": None,
                "source_transform_index": None,
                "timeline_parameter_hash": int(transform.timeline_parameter_hash),
                "datatype_hash": int(transform.datatype_hash),
                "data_type": int(transform.data_type),
                "data_type_name": str(transform.data_type_name),
                "component_labels": list(transform.component_labels),
                "normalized_color": False,
            }
        )
        _assign_carrier_property(controller, prop_name, transform)
        channel_values, channel_interpolations = _channel_data_for_transform(transform)
        create_scalar_action_fcurve(
            blender_action,
            data_path=f'["{prop_name}"]',
            action_group=_action_group_for_transform(transform),
            keyframes=channel_values[0],
            interpolations=channel_interpolations[0],
        )

    assign_action(animation_data, blender_action)
    save_timl_property_names(controller, property_names)
    save_timl_bindings_raw(controller, bindings)
    controller[TIML_IMPORTED_PREVIEW_SIGNATURE_KEY] = imported_preview_signature_json(())
    _tag_timl_source_metadata(
        controller,
        blender_action,
        source_path=source_path,
        source_kind=TIML_SOURCE_KIND_ATTACHED_LMT,
        entry_id=int(entry_id),
        source_offset=int(source_offset),
    )
    ensure_timl_header_props(
        controller,
        source_lmt=source_path,
        entry_id=int(entry_id),
        data_index_a=int(template_header.data_index_a),
        data_index_b=int(template_header.data_index_b),
        animation_length=float(template_header.animation_length),
        loop_start_point=float(template_header.loop_start_point),
        loop_control=int(template_header.loop_control),
        label_hash=int(template_header.label_hash),
    )
    set_timl_template_metadata(
        controller,
        kind=EVENT_LOOP_TEMPLATE_KIND,
        header=template_header,
    )
    return blender_action.name


def _import_timl_data_entry_to_action(
    data_entry,
    *,
    source_path: str,
    entry_id: int,
    import_kind: str,
    source_kind: str,
    source_offset: int,
    source_entry_count: int = 0,
    source_entry_ids_json: str = "",
    session_id: str = "",
    target_armature=None,
):
    result = ImportTimlResult()
    transform_samples = build_timl_transform_samples(data_entry)

    action_name = _action_name_for_import(source_path, entry_id)
    carrier_name = _carrier_name_for_import(source_path, entry_id)
    blender_action = ensure_action(action_name)
    clear_action_fcurves(blender_action)
    blender_action["mhw_anim_tools_import_kind"] = str(import_kind or "")
    blender_action["mhw_anim_tools_timl_transform_count"] = int(len(transform_samples))

    try:
        carrier = _ensure_timl_carrier_object(carrier_name, target_armature=target_armature)
        parent = _ensure_timl_source_parent(source_path, target_armature=target_armature)
    except Exception as exc:
        result.add("ERROR", "timl", str(exc))
        return result

    _clear_timl_carrier_properties(carrier)
    carrier.parent = parent
    animation_data = ensure_object_animation_data(carrier)
    result.action_name = blender_action.name
    result.carrier_name = carrier.name

    if not transform_samples:
        assign_action(animation_data, blender_action)
        save_timl_property_names(carrier, [])
        save_timl_bindings_raw(carrier, [])
        carrier[TIML_IMPORTED_PREVIEW_SIGNATURE_KEY] = imported_preview_signature_json(())
        _tag_timl_source_metadata(
            carrier,
            blender_action,
            source_path=source_path,
            source_kind=source_kind,
            entry_id=int(entry_id),
            source_offset=int(source_offset),
            source_entry_count=int(source_entry_count),
            session_id=str(session_id or ""),
            source_entry_ids_json=str(source_entry_ids_json or ""),
        )
        ensure_timl_header_props(
            carrier,
            source_lmt=source_path,
            entry_id=int(entry_id),
            data_index_a=int(data_entry.data_index_a),
            data_index_b=int(data_entry.data_index_b),
            animation_length=float(data_entry.animation_length),
            loop_start_point=float(data_entry.loop_start_point),
            loop_control=int(data_entry.loop_control),
            label_hash=int(data_entry.label_hash),
        )
        result.add("WARNING", "timl", "TIML container has no transforms yet.")
        return result

    property_names: list[str] = []
    bindings: list[dict[str, object]] = []
    imported_preview_transforms = []
    for transform in transform_samples:
        source_label = f"timl {transform.type_index:02d}:{transform.transform_index:02d}"
        if transform.data_type not in SUPPORTED_TIML_DATA_TYPES:
            result.skipped_transform_count += 1
            result.add("WARNING", source_label, f"Skipped unsupported TIML data type {transform.data_type}.")
            continue
        if not transform.keyframes:
            result.skipped_transform_count += 1
            result.add("WARNING", source_label, "Skipped transform with no keyframes.")
            continue
        if transform.component_count <= 0:
            result.skipped_transform_count += 1
            result.add("WARNING", source_label, "Skipped transform with unknown value dimensions.")
            continue
        if _has_advanced_interpolation(transform):
            result.add(
                "WARNING",
                source_label,
                "Imported advanced TIML interpolation as a constant/linear preview.",
            )
        if _has_integer_precision_risk(transform):
            result.add(
                "WARNING",
                source_label,
                "Integer TIML values exceed exact float precision and may preview approximately in Blender.",
            )

        prop_name = _prop_name_for_transform(transform)
        property_names.append(prop_name)
        bindings.append(
            {
                "property_name": prop_name,
                "type_index": int(transform.type_index),
                "transform_index": int(transform.transform_index),
                "source_type_index": int(transform.type_index),
                "source_transform_index": int(transform.transform_index),
                "timeline_parameter_hash": int(transform.timeline_parameter_hash),
                "datatype_hash": int(transform.datatype_hash),
                "data_type": int(transform.data_type),
                "data_type_name": transform.data_type_name,
                "component_labels": list(transform.component_labels),
                "normalized_color": bool(transform.data_type == 3),
            }
        )

        try:
            _assign_carrier_property(carrier, prop_name, transform)
            channel_values, channel_interpolations = _channel_data_for_transform(transform)
            if transform.component_count == 1:
                created_fcurves = [
                    create_scalar_action_fcurve(
                        blender_action,
                        data_path=f'["{prop_name}"]',
                        action_group=_action_group_for_transform(transform),
                        keyframes=channel_values[0],
                        interpolations=channel_interpolations[0],
                    )
                ]
            else:
                created_fcurves = create_action_fcurves(
                    blender_action,
                    data_path=f'["{prop_name}"]',
                    action_group=_action_group_for_transform(transform),
                    channel_values=channel_values,
                    channel_interpolations=channel_interpolations,
                )
        except Exception as exc:
            result.add("ERROR", source_label, f"Failed to create Blender fcurves: {exc}")
            continue

        result.imported_transform_count += 1
        result.created_fcurve_count += len(created_fcurves)
        result.frame_end = max(result.frame_end, _scene_frame_int(transform.keyframes[-1].frame))
        imported_preview_transforms.append(transform)

    if result.error_count:
        clear_action_fcurves(blender_action)
        for prop_name in property_names:
            if prop_name in carrier:
                del carrier[prop_name]
        if TIML_PROPERTY_LIST_KEY in carrier:
            del carrier[TIML_PROPERTY_LIST_KEY]
        if TIML_BINDINGS_KEY in carrier:
            del carrier[TIML_BINDINGS_KEY]
        if TIML_IMPORTED_PREVIEW_SIGNATURE_KEY in carrier:
            del carrier[TIML_IMPORTED_PREVIEW_SIGNATURE_KEY]
        clear_action_assignment(animation_data, blender_action)
        return result

    if result.imported_transform_count == 0:
        clear_action_fcurves(blender_action)
        result.add("ERROR", "timl", "No supported TIML transforms were imported.")
        return result

    assign_action(animation_data, blender_action)
    save_timl_property_names(carrier, property_names)
    save_timl_bindings_raw(carrier, bindings)
    carrier[TIML_IMPORTED_PREVIEW_SIGNATURE_KEY] = imported_preview_signature_json(imported_preview_transforms)
    _tag_timl_source_metadata(
        carrier,
        blender_action,
        source_path=source_path,
        source_kind=source_kind,
        entry_id=int(entry_id),
        source_offset=int(source_offset),
        source_entry_count=int(source_entry_count),
        session_id=str(session_id or ""),
        source_entry_ids_json=str(source_entry_ids_json or ""),
    )
    ensure_timl_header_props(
        carrier,
        source_lmt=source_path,
        entry_id=int(entry_id),
        data_index_a=int(data_entry.data_index_a),
        data_index_b=int(data_entry.data_index_b),
        animation_length=float(data_entry.animation_length),
        loop_start_point=float(data_entry.loop_start_point),
        loop_control=int(data_entry.loop_control),
        label_hash=int(data_entry.label_hash),
    )
    return result


def import_attached_timl_to_action(lmt, action_index: int, *, source_path: str, source_bytes: bytes, target_armature=None):
    result = ImportTimlResult()
    if action_index < 0 or action_index >= len(lmt.actions):
        result.add("ERROR", "session", "Selected LMT action is out of range for the current session.")
        return result

    source_action = lmt.actions[action_index]
    if not source_action.has_timl or not source_action.header.timl_offset:
        result.add("ERROR", "timl", "The selected LMT entry does not contain an attached TIML payload.")
        return result

    try:
        data_entry = read_timl_data_bytes(
            source_bytes,
            data_offset=int(source_action.header.timl_offset),
            source_name=f"{source_path}#timl",
            entry_id=int(source_action.id),
        )
    except Exception as exc:
        result.add("ERROR", "timl", f"Failed to parse attached TIML payload: {exc}")
        return result
    return _import_timl_data_entry_to_action(
        data_entry,
        source_path=source_path,
        entry_id=int(source_action.id),
        import_kind="attached_timl",
        source_kind=TIML_SOURCE_KIND_ATTACHED_LMT,
        source_offset=int(source_action.header.timl_offset),
        target_armature=target_armature,
    )


def import_standalone_timl_file_to_actions(source_path: str, *, target_armature=None):
    return import_standalone_timl_entries_to_actions(
        source_path,
        entry_ids=None,
        session_id="",
        target_armature=target_armature,
    )


def import_standalone_timl_entries_to_actions(
    source_path: str,
    *,
    entry_ids=None,
    session_id: str = "",
    target_armature=None,
):
    result = ImportTimlFileResult(source_path=str(source_path or ""))
    source_bytes = Path(source_path).read_bytes()
    timl_file = read_timl_bytes(source_bytes, source_name=source_path)
    resolved_session_id = str(session_id or uuid4().hex)
    source_entry_ids = tuple(int(entry.id) for entry in timl_file.data_entries)
    source_entry_ids_json = _entry_ids_json(source_entry_ids)
    result.session_id = resolved_session_id

    if not timl_file.data_entries:
        result.add("WARNING", "timl", "TIML file has no data entries to import.")
        return result

    requested_entry_ids = None if entry_ids is None else {int(entry_id) for entry_id in entry_ids}
    data_entries = tuple(
        entry
        for entry in timl_file.data_entries
        if requested_entry_ids is None or int(entry.id) in requested_entry_ids
    )
    if requested_entry_ids is not None and not data_entries:
        result.add("ERROR", "timl", "Requested TIML entry ids were not found in the source file.")
        return result

    for data_entry in data_entries:
        entry_id = int(data_entry.id)
        entry_offset = int(timl_file.entry_offsets[entry_id]) if 0 <= entry_id < len(timl_file.entry_offsets) else 0
        entry_result = _import_timl_data_entry_to_action(
            data_entry,
            source_path=source_path,
            entry_id=entry_id,
            import_kind="standalone_timl",
            source_kind=TIML_SOURCE_KIND_STANDALONE_FILE,
            source_offset=entry_offset,
            source_entry_count=int(timl_file.header.entry_count),
            source_entry_ids_json=source_entry_ids_json,
            session_id=resolved_session_id,
            target_armature=target_armature,
        )
        result.diagnostics.extend(entry_result.diagnostics)
        if entry_result.error_count:
            result.skipped_entry_count += 1
            continue
        result.imported_entry_ids.append(entry_id)
        result.imported_action_names.append(entry_result.action_name)
        result.imported_carrier_names.append(entry_result.carrier_name)
        result.imported_transform_count += int(entry_result.imported_transform_count)
        result.frame_end = max(result.frame_end, int(entry_result.frame_end))

    return result
