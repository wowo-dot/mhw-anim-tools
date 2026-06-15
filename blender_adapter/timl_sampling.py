"""Sample imported TIML controller actions back into typed TIML value space."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
import json
import math
import re

try:
    from ..core.formats.timl.semantics import get_data_type_semantics
    from .timl_metadata import TIML_ACTION_NAME_KEY
    from .timl_metadata import TIML_BINDINGS_KEY
    from .timl_metadata import TIML_ENTRY_ID_KEY
    from .timl_metadata import TIML_SOURCE_LMT_KEY
    from .timl_metadata import TIML_SOURCE_OFFSET_KEY
except ImportError:  # pragma: no cover - test runner imports from addon root
    from core.formats.timl.semantics import get_data_type_semantics
    from blender_adapter.timl_metadata import TIML_ACTION_NAME_KEY
    from blender_adapter.timl_metadata import TIML_BINDINGS_KEY
    from blender_adapter.timl_metadata import TIML_ENTRY_ID_KEY
    from blender_adapter.timl_metadata import TIML_SOURCE_LMT_KEY
    from blender_adapter.timl_metadata import TIML_SOURCE_OFFSET_KEY


CUSTOM_PROPERTY_PATH = re.compile(r'^\["(?P<name>.+)"\]$')
SUPPORTED_BLENDER_INTERPOLATIONS = {"CONSTANT", "LINEAR"}
EXACT_INTEGER_FLOAT_LIMIT = 16_777_216


@dataclass(frozen=True)
class TimlControllerMetadata:
    carrier_name: str
    action_name: str
    source_lmt: str
    entry_id: int
    source_offset: int
    transform_count: int


@dataclass(frozen=True)
class TimlControllerBinding:
    property_name: str
    type_index: int
    transform_index: int
    timeline_parameter_hash: int
    datatype_hash: int
    data_type: int
    data_type_name: str
    component_labels: tuple[str, ...]
    normalized_color: bool

    @property
    def component_count(self) -> int:
        return len(self.component_labels)

    @property
    def label(self) -> str:
        return f"timl {self.type_index:02d}:{self.transform_index:02d}"


@dataclass(frozen=True)
class SampledTimlKeyframe:
    frame: float
    value: tuple[float, ...]
    interpolation: str


@dataclass(frozen=True)
class SampledTimlTransform:
    property_name: str
    type_index: int
    transform_index: int
    timeline_parameter_hash: int
    datatype_hash: int
    data_type: int
    data_type_name: str
    value_kind: str
    control_kind: str
    component_labels: tuple[str, ...]
    keyframes: tuple[SampledTimlKeyframe, ...]

    @property
    def component_count(self) -> int:
        return len(self.component_labels)


@dataclass(frozen=True)
class TimlSamplingDiagnostic:
    level: str
    source: str
    message: str


@dataclass
class TimlSamplingResult:
    metadata: TimlControllerMetadata | None = None
    sampled_transform_count: int = 0
    skipped_transform_count: int = 0
    keyframe_count: int = 0
    frame_end: int = 0
    sampled_transforms: tuple[SampledTimlTransform, ...] = ()
    diagnostics: list[TimlSamplingDiagnostic] = field(default_factory=list)

    def add(self, level: str, source: str, message: str):
        self.diagnostics.append(TimlSamplingDiagnostic(level=level, source=source, message=message))

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "WARNING")

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "ERROR")


def _safe_get(value_like, key: str, default=None):
    getter = getattr(value_like, "get", None)
    if callable(getter):
        return getter(key, default)
    if isinstance(value_like, dict):
        return value_like.get(key, default)
    return default


def _safe_name(value_like) -> str:
    return str(getattr(value_like, "name", _safe_get(value_like, "name", "")) or "")


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _scene_frame_int(value) -> int:
    return int(math.ceil(float(value)))


def _parse_property_path(data_path: str):
    match = CUSTOM_PROPERTY_PATH.match(data_path or "")
    if match is None:
        return None
    return match.group("name")


def _animation_action(target_object):
    animation_data = getattr(target_object, "animation_data", None)
    if animation_data is None:
        return None
    return getattr(animation_data, "action", None)


def is_imported_timl_controller(target_object) -> bool:
    if target_object is None:
        return False
    return bool(_safe_get(target_object, TIML_BINDINGS_KEY, "")) and bool(_safe_get(target_object, TIML_ACTION_NAME_KEY, ""))


def extract_timl_controller_metadata(controller_object, action=None) -> TimlControllerMetadata:
    active_action = action if action is not None else _animation_action(controller_object)
    return TimlControllerMetadata(
        carrier_name=_safe_name(controller_object),
        action_name=_safe_name(active_action) or str(_safe_get(controller_object, TIML_ACTION_NAME_KEY, "")),
        source_lmt=str(_safe_get(controller_object, TIML_SOURCE_LMT_KEY, "")),
        entry_id=_safe_int(_safe_get(controller_object, TIML_ENTRY_ID_KEY, 0), 0),
        source_offset=_safe_int(_safe_get(controller_object, TIML_SOURCE_OFFSET_KEY, 0), 0),
        transform_count=_safe_int(
            _safe_get(active_action, "mhw_anim_tools_timl_transform_count", 0),
            _safe_int(_safe_get(controller_object, "mhw_anim_tools_timl_transform_count", 0), 0),
        ),
    )


def _parse_timl_bindings(controller_object) -> tuple[TimlControllerBinding, ...]:
    raw_value = _safe_get(controller_object, TIML_BINDINGS_KEY, "")
    if not isinstance(raw_value, str) or not raw_value:
        return ()
    try:
        decoded = json.loads(raw_value)
    except json.JSONDecodeError:
        return ()
    if not isinstance(decoded, list):
        return ()

    bindings: list[TimlControllerBinding] = []
    for entry in decoded:
        if not isinstance(entry, dict):
            continue
        component_labels = tuple(str(label) for label in entry.get("component_labels", ()))
        bindings.append(
            TimlControllerBinding(
                property_name=str(entry.get("property_name", "")),
                type_index=_safe_int(entry.get("type_index", 0), 0),
                transform_index=_safe_int(entry.get("transform_index", 0), 0),
                timeline_parameter_hash=_safe_int(entry.get("timeline_parameter_hash", 0), 0),
                datatype_hash=_safe_int(entry.get("datatype_hash", 0), 0),
                data_type=_safe_int(entry.get("data_type", 0), 0),
                data_type_name=str(entry.get("data_type_name", "")),
                component_labels=component_labels,
                normalized_color=bool(entry.get("normalized_color", False)),
            )
        )
    return tuple(bindings)


def _duplicate_binding_labels(bindings: tuple[TimlControllerBinding, ...], *, key_getter, label_getter) -> tuple[str, ...]:
    counts: dict[object, int] = {}
    labels: dict[object, str] = {}
    for binding in bindings:
        key = key_getter(binding)
        counts[key] = counts.get(key, 0) + 1
        labels.setdefault(key, label_getter(binding))
    return tuple(sorted(labels[key] for key, count in counts.items() if count > 1))


def _collect_property_groups(action):
    groups: dict[str, dict[int, object]] = {}
    unsupported_paths: list[str] = []
    for fcurve in getattr(action, "fcurves", ()):
        property_name = _parse_property_path(getattr(fcurve, "data_path", ""))
        if property_name is None:
            unsupported_paths.append(getattr(fcurve, "data_path", ""))
            continue
        groups.setdefault(property_name, {})[int(getattr(fcurve, "array_index", 0))] = fcurve
    return groups, tuple(sorted(set(filter(None, unsupported_paths))))


def _authored_frame_values(fcurve) -> list[float]:
    frames: list[float] = []
    for point in getattr(fcurve, "keyframe_points", ()):
        co = getattr(point, "co", None)
        if co is None:
            continue
        try:
            frames.append(float(co[0]))
        except (TypeError, ValueError, IndexError):
            continue
    return frames


def _shared_authored_frames(channel_map) -> tuple[float, ...] | None:
    channel_frames = [tuple(_authored_frame_values(fcurve)) for _index, fcurve in sorted(channel_map.items())]
    if not channel_frames or not channel_frames[0]:
        return tuple()
    reference = channel_frames[0]
    for frames in channel_frames[1:]:
        if frames != reference:
            return None
    return tuple(reference)


def _interpolation_name_for_frame(fcurve, frame: float) -> str | None:
    for point in getattr(fcurve, "keyframe_points", ()):
        co = getattr(point, "co", None)
        if co is None:
            continue
        try:
            point_frame = float(co[0])
        except (TypeError, ValueError, IndexError):
            continue
        if math.isclose(point_frame, float(frame), rel_tol=0.0, abs_tol=1e-6):
            return str(getattr(point, "interpolation", "LINEAR") or "LINEAR").upper()
    return None


def _shared_interpolation(channel_map, frame: float) -> str | None:
    names = {
        name
        for _index, fcurve in sorted(channel_map.items())
        for name in (_interpolation_name_for_frame(fcurve, frame),)
        if name is not None
    }
    if not names:
        return None
    if len(names) != 1:
        return None
    return next(iter(names))


def _to_timl_value(binding: TimlControllerBinding, semantics, preview_value: tuple[float, ...]) -> tuple[float, ...]:
    if binding.normalized_color or semantics.value_kind == "color":
        return tuple(float(component) * 255.0 for component in preview_value)
    return tuple(float(component) for component in preview_value)


def _has_color_preview_out_of_range(preview_values) -> bool:
    return any(
        float(component) < -1e-6 or float(component) > 1.0 + 1e-6
        for preview_value in preview_values
        for component in preview_value
    )


def _has_integer_precision_risk(native_values) -> bool:
    return any(
        abs(float(component)) > EXACT_INTEGER_FLOAT_LIMIT
        for native_value in native_values
        for component in native_value
    )


def _has_non_integral_values(native_values) -> bool:
    return any(
        not math.isclose(float(component), round(float(component)), rel_tol=0.0, abs_tol=1e-6)
        for native_value in native_values
        for component in native_value
    )


def _has_non_boolean_values(native_values) -> bool:
    return any(
        not math.isclose(float(component), 0.0, rel_tol=0.0, abs_tol=1e-6)
        and not math.isclose(float(component), 1.0, rel_tol=0.0, abs_tol=1e-6)
        for native_value in native_values
        for component in native_value
    )


def _validate_transform_values(result: TimlSamplingResult, binding: TimlControllerBinding, semantics, preview_values, native_values):
    source = binding.label
    if semantics.value_kind == "color" and _has_color_preview_out_of_range(preview_values):
        result.add(
            "WARNING",
            source,
            "Color preview values fall outside the expected 0..1 Blender range and will block safe TIML writeback until they are brought back into range.",
        )
    if semantics.value_kind == "integer":
        if _has_integer_precision_risk(native_values):
            result.add(
                "WARNING",
                source,
                "Integer TIML values exceed exact float precision and may round when written back.",
            )
        if _has_non_integral_values(native_values):
            result.add(
                "WARNING",
                source,
                "Integer TIML preview values are off-grid and would need quantization before export.",
            )
    if semantics.value_kind == "boolean" and _has_non_boolean_values(native_values):
        result.add(
            "WARNING",
            source,
            "Boolean TIML preview values are not 0/1 and would need quantization before export.",
        )


def sample_timl_controller_action(controller_object, action=None) -> TimlSamplingResult:
    result = TimlSamplingResult()
    if controller_object is None:
        result.add("ERROR", "timl.controller", "Choose a TIML controller object before analyzing controller curves.")
        return result

    action = action if action is not None else _animation_action(controller_object)
    if action is None:
        result.add("ERROR", "timl.controller", "Selected TIML controller object has no active action.")
        return result

    metadata = extract_timl_controller_metadata(controller_object, action=action)
    result.metadata = metadata
    if str(_safe_get(action, "mhw_anim_tools_import_kind", "")) != "attached_timl":
        result.add(
            "WARNING",
            "timl.controller",
            f"Action '{metadata.action_name}' is not marked as an imported TIML controller action; analysis may be incomplete.",
        )

    bindings = _parse_timl_bindings(controller_object)
    if not bindings:
        result.add("ERROR", "timl.controller", "TIML controller is missing binding metadata.")
        return result
    duplicate_identities = _duplicate_binding_labels(
        bindings,
        key_getter=lambda binding: (binding.type_index, binding.transform_index),
        label_getter=lambda binding: binding.label,
    )
    if duplicate_identities:
        result.add(
            "ERROR",
            "timl.controller",
            "TIML controller binding metadata contains duplicate source transform identities: %s."
            % ", ".join(duplicate_identities),
        )
    duplicate_properties = _duplicate_binding_labels(
        bindings,
        key_getter=lambda binding: binding.property_name,
        label_getter=lambda binding: binding.property_name,
    )
    if duplicate_properties:
        result.add(
            "ERROR",
            "timl.controller",
            "TIML controller binding metadata reuses custom property names across multiple transforms: %s."
            % ", ".join(duplicate_properties),
        )
    if result.error_count:
        return result

    property_groups, unsupported_paths = _collect_property_groups(action)
    for path in unsupported_paths:
        result.add("WARNING", "fcurve", f"Skipped unsupported TIML controller data path '{path}'.")

    binding_names = {binding.property_name for binding in bindings}
    for property_name in sorted(set(property_groups) - binding_names):
        result.add(
            "WARNING",
            "timl.controller",
            f"Found unbound custom-property curves for '{property_name}'; they will be ignored by TIML analysis.",
        )

    sampled_transforms: list[SampledTimlTransform] = []
    for binding in sorted(bindings, key=lambda item: (item.type_index, item.transform_index, item.property_name)):
        semantics = get_data_type_semantics(binding.data_type)
        channel_count = binding.component_count or max(semantics.value_dimension, 1)
        source = binding.label
        channel_map = property_groups.get(binding.property_name)
        if not channel_map:
            result.skipped_transform_count += 1
            result.add("WARNING", source, f"Missing controller curves for '{binding.property_name}'.")
            continue
        if set(channel_map) != set(range(channel_count)):
            result.skipped_transform_count += 1
            result.add(
                "WARNING",
                source,
                f"Incomplete controller channels for '{binding.property_name}'; expected {channel_count}, found {len(channel_map)}.",
            )
            continue

        authored_frames = _shared_authored_frames(channel_map)
        if authored_frames is None:
            result.skipped_transform_count += 1
            result.add(
                "WARNING",
                source,
                "Per-channel TIML keyframe times no longer match; split channel retiming is not supported yet.",
            )
            continue
        if not authored_frames:
            result.skipped_transform_count += 1
            result.add("WARNING", source, "TIML controller transform has no authored keyframes.")
            continue

        keyframes: list[SampledTimlKeyframe] = []
        preview_values: list[tuple[float, ...]] = []
        native_values: list[tuple[float, ...]] = []
        warned_unsupported_interpolation = False
        for frame in authored_frames:
            interpolation = _shared_interpolation(channel_map, frame)
            if interpolation is None:
                result.skipped_transform_count += 1
                result.add(
                    "WARNING",
                    source,
                    "Per-channel TIML interpolation no longer matches at one or more keyframes.",
                )
                keyframes = []
                break
            if interpolation not in SUPPORTED_BLENDER_INTERPOLATIONS and not warned_unsupported_interpolation:
                result.add(
                    "WARNING",
                    source,
                    f"Blender interpolation '{interpolation}' is not part of the current TIML write coverage.",
                )
                warned_unsupported_interpolation = True

            preview_value = tuple(float(channel_map[index].evaluate(frame)) for index in range(channel_count))
            native_value = _to_timl_value(binding, semantics, preview_value)
            preview_values.append(preview_value)
            native_values.append(native_value)
            keyframes.append(
                SampledTimlKeyframe(
                    frame=float(frame),
                    value=native_value,
                    interpolation=interpolation,
                )
            )
        if not keyframes:
            continue
        _validate_transform_values(result, binding, semantics, tuple(preview_values), tuple(native_values))

        sampled_transforms.append(
            SampledTimlTransform(
                property_name=binding.property_name,
                type_index=binding.type_index,
                transform_index=binding.transform_index,
                timeline_parameter_hash=binding.timeline_parameter_hash,
                datatype_hash=binding.datatype_hash,
                data_type=binding.data_type,
                data_type_name=binding.data_type_name or semantics.name,
                value_kind=semantics.value_kind,
                control_kind=semantics.control_kind,
                component_labels=binding.component_labels or tuple(f"c{index}" for index in range(channel_count)),
                keyframes=tuple(keyframes),
            )
        )
        result.sampled_transform_count += 1
        result.keyframe_count += len(keyframes)
        result.frame_end = max(result.frame_end, _scene_frame_int(keyframes[-1].frame))

    result.sampled_transforms = tuple(sampled_transforms)
    expected_transform_count = metadata.transform_count
    if expected_transform_count and result.sampled_transform_count != expected_transform_count:
        result.add(
            "WARNING",
            "timl.controller",
            (
                f"Analyzed {result.sampled_transform_count} TIML transform(s), "
                f"but imported action metadata expected {expected_transform_count}."
            ),
        )
    if result.sampled_transform_count == 0 and not result.error_count:
        result.add("ERROR", "timl.controller", "No TIML controller transforms were analyzable from the selected action.")
    return result
