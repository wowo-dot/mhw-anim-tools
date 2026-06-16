"""Plan how an imported TIML controller can be written back during merge export."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
import math

try:
    from ..core.formats.timl.embedded_writer import can_preserve_source_curve_semantics
    from ..core.formats.timl.reader import read_timl_data_bytes
    from .timl_authoring import load_deleted_timl_identities
    from .timl_authoring import timl_header_state_from_controller
    from .timl_metadata import TIML_IMPORTED_PREVIEW_SIGNATURE_KEY
    from .timl_preview_state import diff_sampled_transforms_from_imported_signature
    from .timl_sampling import sample_timl_controller_action
except ImportError:  # pragma: no cover - test runner imports from addon root
    from core.formats.timl.embedded_writer import can_preserve_source_curve_semantics
    from core.formats.timl.reader import read_timl_data_bytes
    from blender_adapter.timl_authoring import load_deleted_timl_identities
    from blender_adapter.timl_authoring import timl_header_state_from_controller
    from blender_adapter.timl_metadata import TIML_IMPORTED_PREVIEW_SIGNATURE_KEY
    from blender_adapter.timl_preview_state import diff_sampled_transforms_from_imported_signature
    from blender_adapter.timl_sampling import sample_timl_controller_action


WRITABLE_BLENDER_INTERPOLATIONS = {"CONSTANT", "LINEAR"}
EXACT_INTEGER_FLOAT_LIMIT = 16_777_216
INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1
UINT32_MAX = (1 << 32) - 1


@dataclass(frozen=True)
class TimlWritebackPlanDiagnostic:
    level: str
    source: str
    message: str


@dataclass(frozen=True)
class TimlTransformWritebackPlan:
    type_index: int
    transform_index: int
    status: str
    data_type: int
    source_advanced: bool
    timeline_parameter_hash: int = 0
    datatype_hash: int = 0
    reason: str = ""

    @property
    def identity(self) -> tuple[int, int]:
        return (int(self.type_index), int(self.transform_index))


@dataclass
class TimlControllerWritebackPlan:
    source_entry: object | None = None
    sampled_result: object | None = None
    transform_plans: tuple[TimlTransformWritebackPlan, ...] = ()
    deleted_identities: tuple[tuple[int, int], ...] = ()
    diagnostics: list[TimlWritebackPlanDiagnostic] = field(default_factory=list)

    def add(self, level: str, source: str, message: str):
        self.diagnostics.append(TimlWritebackPlanDiagnostic(level=level, source=source, message=message))

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "ERROR")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "WARNING")

    @property
    def changed_transforms(self) -> tuple[object, ...]:
        if self.sampled_result is None:
            return ()
        planned_identities = {
            plan.identity
            for plan in self.transform_plans
            if plan.status in {"patch_source_values", "rewrite_preview"}
        }
        return tuple(
            transform
            for transform in getattr(self.sampled_result, "sampled_transforms", ())
            if (int(transform.type_index), int(transform.transform_index)) in planned_identities
        )

    @property
    def has_writable_changes(self) -> bool:
        if self.deleted_identities:
            return True
        return any(
            item.status in {"patch_source_values", "rewrite_preview"}
            for item in self.transform_plans
        )


def _safe_get(value_like, key: str, default=None):
    getter = getattr(value_like, "get", None)
    if callable(getter):
        return getter(key, default)
    if isinstance(value_like, dict):
        return value_like.get(key, default)
    return default


def _advanced_source_transform_identities(source_entry) -> set[tuple[int, int]]:
    advanced = set()
    for type_index, type_entry in enumerate(source_entry.types):
        for transform_index, transform in enumerate(type_entry.transforms):
            if any(int(keyframe.interpolation) not in {0, 1} or int(keyframe.easing) != 0 for keyframe in transform.keyframes):
                advanced.add((int(type_index), int(transform_index)))
    return advanced


def _has_unsupported_rebuild_interpolation(sampled_transform) -> bool:
    return any(str(keyframe.interpolation).upper() not in WRITABLE_BLENDER_INTERPOLATIONS for keyframe in sampled_transform.keyframes)


def _unsupported_labels(plans, *, status: str) -> str:
    return ", ".join(
        f"{plan.type_index:02d}:{plan.transform_index:02d}"
        for plan in plans
        if plan.status == status
    )


def _duplicate_sampled_identities(sampled_transforms) -> tuple[tuple[int, int], ...]:
    counts: dict[tuple[int, int], int] = {}
    for transform in sampled_transforms:
        identity = (int(transform.type_index), int(transform.transform_index))
        counts[identity] = counts.get(identity, 0) + 1
    return tuple(sorted(identity for identity, count in counts.items() if count > 1))


def _source_component_count(source_transform) -> int:
    if int(source_transform.data_type) == 3:
        return 4
    return 1


def _is_integral_value(value: float) -> bool:
    return math.isclose(float(value), round(float(value)), rel_tol=0.0, abs_tol=1e-6)


def _sampled_transform_writeback_block_reason(sampled_transform) -> str:
    data_type = int(sampled_transform.data_type)
    components = tuple(
        float(component)
        for keyframe in sampled_transform.keyframes
        for component in keyframe.value
    )
    if data_type == 0:
        if any((not math.isfinite(value)) or int(round(value)) < INT32_MIN or int(round(value)) > INT32_MAX for value in components):
            return "integer_range"
        if any(abs(value) > EXACT_INTEGER_FLOAT_LIMIT for value in components):
            return "integer_precision_risk"
        if any(not _is_integral_value(value) for value in components):
            return "integer_off_grid"
    elif data_type == 1:
        if any((not math.isfinite(value)) or int(round(value)) < 0 or int(round(value)) > UINT32_MAX for value in components):
            return "integer_range"
        if any(abs(value) > EXACT_INTEGER_FLOAT_LIMIT for value in components):
            return "integer_precision_risk"
        if any(not _is_integral_value(value) for value in components):
            return "integer_off_grid"
    elif data_type == 4:
        if any(
            not math.isclose(float(value), 0.0, rel_tol=0.0, abs_tol=1e-6)
            and not math.isclose(float(value), 1.0, rel_tol=0.0, abs_tol=1e-6)
            for value in components
        ):
            return "boolean_off_grid"
    elif data_type == 3:
        if any((not math.isfinite(value)) or value < 0.0 or value > 255.0 for value in components):
            return "color_range"
    return ""


def _sampled_transform_writeback_block_message(reason: str) -> str:
    if reason == "integer_range":
        return "integer preview values fall outside the writable range for this TIML data type"
    if reason == "integer_precision_risk":
        return "integer preview values exceed exact Blender float precision and would round unpredictably"
    if reason == "integer_off_grid":
        return "integer preview values are off-grid and would require lossy quantization"
    if reason == "boolean_off_grid":
        return "boolean preview values are not limited to 0 or 1 and would require lossy quantization"
    if reason == "color_range":
        return "color preview values fall outside the writable 0..255 range and would require clamping"
    return "preview values are not safely writable"


def _sampled_source_mismatch_reason(source_type, source_transform, sampled_transform) -> str:
    if int(sampled_transform.timeline_parameter_hash) != int(source_type.timeline_parameter_hash):
        return "timeline_hash_mismatch"
    if int(sampled_transform.datatype_hash) != int(source_transform.datatype_hash):
        return "datatype_hash_mismatch"
    if int(sampled_transform.data_type) != int(source_transform.data_type):
        return "data_type_mismatch"
    if int(sampled_transform.component_count) != int(_source_component_count(source_transform)):
        return "component_count_mismatch"
    return ""


def _sampled_source_mismatch_message(reason: str, *, source_type, source_transform, sampled_transform) -> str:
    if reason == "timeline_hash_mismatch":
        return (
            "timeline hash changed from "
            f"0x{int(source_type.timeline_parameter_hash) & 0xFFFFFFFF:08X} to "
            f"0x{int(sampled_transform.timeline_parameter_hash) & 0xFFFFFFFF:08X}"
        )
    if reason == "datatype_hash_mismatch":
        return (
            "datatype hash changed from "
            f"0x{int(source_transform.datatype_hash) & 0xFFFFFFFF:08X} to "
            f"0x{int(sampled_transform.datatype_hash) & 0xFFFFFFFF:08X}"
        )
    if reason == "data_type_mismatch":
        return (
            f"data type changed from {int(source_transform.data_type)} "
            f"to {int(sampled_transform.data_type)}"
        )
    if reason == "component_count_mismatch":
        return (
            f"component count changed from {_source_component_count(source_transform)} "
            f"to {int(sampled_transform.component_count)}"
        )
    return "source metadata mismatch"


def _source_entry_has_no_transforms(source_entry) -> bool:
    return not any(getattr(type_entry, "transforms", ()) for type_entry in getattr(source_entry, "types", ()))


def _validate_identity_structure(identities) -> str:
    if not identities:
        return ""
    grouped: dict[int, set[int]] = {}
    for type_index, transform_index in identities:
        grouped.setdefault(int(type_index), set()).add(int(transform_index))
    ordered_type_indices = sorted(grouped)
    if ordered_type_indices != list(range(len(ordered_type_indices))):
        return "type_index_layout"
    for type_index in ordered_type_indices:
        ordered_transform_indices = sorted(grouped[type_index])
        if ordered_transform_indices != list(range(len(ordered_transform_indices))):
            return "transform_index_layout"
    return ""


def _validate_new_payload_structure(sampled_transforms) -> str:
    return _validate_identity_structure(
        (
            (int(sampled_transform.type_index), int(sampled_transform.transform_index))
            for sampled_transform in sampled_transforms
        )
    )


def _validate_new_payload_structure_message(reason: str) -> str:
    if reason == "type_index_layout":
        return "new TIML payloads currently require contiguous type indices starting at 00"
    if reason == "transform_index_layout":
        return "new TIML payloads currently require contiguous transform indices within each type"
    return "new TIML payload structure is not writable"


def _source_identity_map(source_entry) -> dict[tuple[int, int], tuple[object, object]]:
    return {
        (int(type_index), int(transform_index)): (type_entry, transform)
        for type_index, type_entry in enumerate(source_entry.types)
        for transform_index, transform in enumerate(type_entry.transforms)
    }


def _sampled_transform_source_identity(sampled_transform, source_map) -> tuple[int, int] | None:
    source_type_index = getattr(sampled_transform, "source_type_index", None)
    source_transform_index = getattr(sampled_transform, "source_transform_index", None)
    if source_type_index is None or source_transform_index is None:
        return None
    identity = (int(source_type_index), int(source_transform_index))
    if identity not in source_map:
        return None
    return identity


def plan_timl_controller_writeback(controller_object, *, source_bytes: bytes, source_name: str, entry_id: int, source_offset: int):
    plan = TimlControllerWritebackPlan()
    sampled = sample_timl_controller_action(controller_object)
    plan.sampled_result = sampled
    for diagnostic in sampled.diagnostics:
        plan.add(diagnostic.level, diagnostic.source, diagnostic.message)
    if sampled.error_count:
        return plan
    duplicate_identities = _duplicate_sampled_identities(sampled.sampled_transforms)
    if duplicate_identities:
        duplicate_labels = ", ".join(
            f"{type_index:02d}:{transform_index:02d}"
            for type_index, transform_index in duplicate_identities
        )
        plan.add(
            "ERROR",
            "timl.writeback",
            f"TIML controller sampling produced duplicate transform identities: {duplicate_labels}.",
        )
        return plan

    source_entry = read_timl_data_bytes(
        source_bytes,
        data_offset=int(source_offset),
        source_name=source_name,
        entry_id=int(entry_id),
    )
    plan.source_entry = source_entry
    deleted_identities = set(load_deleted_timl_identities(controller_object))
    sampled_map = {
        (int(transform.type_index), int(transform.transform_index)): transform
        for transform in sampled.sampled_transforms
    }
    source_map = _source_identity_map(source_entry)
    deleted_identities = {
        identity
        for identity in deleted_identities
        if identity in source_map
    }
    plan.deleted_identities = tuple(sorted(deleted_identities))
    advanced_identities = _advanced_source_transform_identities(source_entry)

    source_identity_by_current: dict[tuple[int, int], tuple[int, int]] = {}
    claimed_source_identities: set[tuple[int, int]] = set()
    duplicate_source_identities: set[tuple[int, int]] = set()
    for current_identity, sampled_transform in sampled_map.items():
        source_identity = _sampled_transform_source_identity(sampled_transform, source_map)
        if source_identity is None:
            continue
        if source_identity in claimed_source_identities:
            duplicate_source_identities.add(source_identity)
            continue
        claimed_source_identities.add(source_identity)
        source_identity_by_current[current_identity] = source_identity
    if duplicate_source_identities:
        duplicate_labels = ", ".join(
            f"{type_index:02d}:{transform_index:02d}"
            for type_index, transform_index in sorted(duplicate_source_identities)
        )
        plan.add(
            "ERROR",
            "timl.writeback",
            f"TIML controller contains multiple preview bindings for the same source transform identity: {duplicate_labels}.",
        )
        return plan
    for current_identity in sorted(sampled_map):
        if current_identity in source_identity_by_current:
            continue
        if current_identity in deleted_identities:
            continue
        if current_identity not in source_map:
            continue
        if current_identity in claimed_source_identities:
            continue
        claimed_source_identities.add(current_identity)
        source_identity_by_current[current_identity] = current_identity

    diff = diff_sampled_transforms_from_imported_signature(
        _safe_get(controller_object, TIML_IMPORTED_PREVIEW_SIGNATURE_KEY, ""),
        sampled.sampled_transforms,
    )
    if not diff.available:
        plan.add(
            "WARNING",
            "timl.writeback",
            "TIML controller is missing imported preview signature metadata; merge export will treat all analyzable transforms as edited.",
        )
        changed_identities = set(sampled_map)
        unresolved_missing_identities: tuple[tuple[int, int], ...] = ()
    else:
        changed_identities = set(diff.edited_identities)
        unresolved_missing_identities = tuple(
            identity
            for identity in diff.missing_identities
            if identity not in claimed_source_identities and identity not in deleted_identities
        )
        if unresolved_missing_identities:
            missing_labels = ", ".join(
                f"{type_index:02d}:{transform_index:02d}"
                for type_index, transform_index in unresolved_missing_identities
            )
            plan.add(
                "WARNING",
                "timl.writeback",
                f"TIML controller is missing preview curves for source transform(s) {missing_labels}; merge export will preserve their original source data.",
            )
        if not changed_identities and not deleted_identities:
            action_name = ""
            if getattr(sampled, "metadata", None) is not None:
                action_name = str(getattr(sampled.metadata, "action_name", "") or "")
            plan.add(
                "INFO",
                "timl.writeback",
                f"TIML controller '{action_name}' is unchanged; merge export will preserve the original embedded TIML payload.",
            )

    if _source_entry_has_no_transforms(source_entry):
        if not sampled_map:
            return plan
        structure_reason = _validate_new_payload_structure(tuple(sampled_map.values()))
        transform_plans: list[TimlTransformWritebackPlan] = []
        for identity in sorted(sampled_map):
            sampled_transform = sampled_map[identity]
            if structure_reason:
                transform_plans.append(
                    TimlTransformWritebackPlan(
                        type_index=int(sampled_transform.type_index),
                        transform_index=int(sampled_transform.transform_index),
                        status="unsupported_rebuild",
                        data_type=int(sampled_transform.data_type),
                        source_advanced=False,
                        timeline_parameter_hash=int(sampled_transform.timeline_parameter_hash),
                        datatype_hash=int(sampled_transform.datatype_hash),
                        reason=structure_reason,
                    )
                )
                continue
            value_block_reason = _sampled_transform_writeback_block_reason(sampled_transform)
            if value_block_reason:
                transform_plans.append(
                    TimlTransformWritebackPlan(
                        type_index=int(sampled_transform.type_index),
                        transform_index=int(sampled_transform.transform_index),
                        status="unsupported_rebuild",
                        data_type=int(sampled_transform.data_type),
                        source_advanced=False,
                        timeline_parameter_hash=int(sampled_transform.timeline_parameter_hash),
                        datatype_hash=int(sampled_transform.datatype_hash),
                        reason=value_block_reason,
                    )
                )
                plan.add(
                    "ERROR",
                    "timl.writeback",
                    "TIML transform %02d:%02d cannot be written safely because %s."
                    % (
                        int(sampled_transform.type_index),
                        int(sampled_transform.transform_index),
                        _sampled_transform_writeback_block_message(value_block_reason),
                    ),
                )
                continue
            if _has_unsupported_rebuild_interpolation(sampled_transform):
                transform_plans.append(
                    TimlTransformWritebackPlan(
                        type_index=int(sampled_transform.type_index),
                        transform_index=int(sampled_transform.transform_index),
                        status="unsupported_rebuild",
                        data_type=int(sampled_transform.data_type),
                        source_advanced=False,
                        timeline_parameter_hash=int(sampled_transform.timeline_parameter_hash),
                        datatype_hash=int(sampled_transform.datatype_hash),
                        reason="unsupported_interpolation",
                    )
                )
                plan.add(
                    "ERROR",
                    "timl.writeback",
                    "TIML transform %02d:%02d uses unsupported preview interpolation for empty-container writeback."
                    % (int(sampled_transform.type_index), int(sampled_transform.transform_index)),
                )
                continue
            transform_plans.append(
                TimlTransformWritebackPlan(
                    type_index=int(sampled_transform.type_index),
                    transform_index=int(sampled_transform.transform_index),
                    status="rewrite_preview",
                    data_type=int(sampled_transform.data_type),
                    source_advanced=False,
                    timeline_parameter_hash=int(sampled_transform.timeline_parameter_hash),
                    datatype_hash=int(sampled_transform.datatype_hash),
                )
            )
        plan.transform_plans = tuple(transform_plans)
        if structure_reason:
            plan.add(
                "ERROR",
                "timl.writeback",
                _validate_new_payload_structure_message(structure_reason),
            )
        if sampled_map and not plan.error_count:
            plan.add(
                "INFO",
                "timl.writeback",
                "Empty attached TIML container will be rebuilt from the current controller curves.",
            )
        return plan

    preserved_source_identities = tuple(
        identity
        for identity in sorted(source_map)
        if identity not in deleted_identities and identity not in claimed_source_identities
    )
    final_identities = set(sampled_map) | set(preserved_source_identities)
    structure_reason = _validate_identity_structure(final_identities)

    transform_plans: list[TimlTransformWritebackPlan] = []
    if structure_reason:
        for identity in preserved_source_identities:
            source_type, source_transform = source_map[identity]
            transform_plans.append(
                TimlTransformWritebackPlan(
                    type_index=int(identity[0]),
                    transform_index=int(identity[1]),
                    status="preserve_raw",
                    data_type=int(source_transform.data_type),
                    source_advanced=identity in advanced_identities,
                    timeline_parameter_hash=int(source_type.timeline_parameter_hash),
                    datatype_hash=int(source_transform.datatype_hash),
                    reason="missing_sampled_transform" if identity in unresolved_missing_identities else "",
                )
            )
        for identity in sorted(sampled_map):
            sampled_transform = sampled_map[identity]
            transform_plans.append(
                TimlTransformWritebackPlan(
                    type_index=int(sampled_transform.type_index),
                    transform_index=int(sampled_transform.transform_index),
                    status="unsupported_rebuild",
                    data_type=int(sampled_transform.data_type),
                    source_advanced=bool(
                        source_identity_by_current.get(identity) in advanced_identities
                    ),
                    timeline_parameter_hash=int(sampled_transform.timeline_parameter_hash),
                    datatype_hash=int(sampled_transform.datatype_hash),
                    reason=structure_reason,
                )
            )
        for identity in sorted(deleted_identities):
            source_type, source_transform = source_map[identity]
            transform_plans.append(
                TimlTransformWritebackPlan(
                    type_index=int(identity[0]),
                    transform_index=int(identity[1]),
                    status="unsupported_rebuild",
                    data_type=int(source_transform.data_type),
                    source_advanced=identity in advanced_identities,
                    timeline_parameter_hash=int(source_type.timeline_parameter_hash),
                    datatype_hash=int(source_transform.datatype_hash),
                    reason=structure_reason,
                )
            )
        plan.transform_plans = tuple(transform_plans)
        plan.add(
            "ERROR",
            "timl.writeback",
            _validate_new_payload_structure_message(structure_reason),
        )
        return plan

    for identity in preserved_source_identities:
        source_type, source_transform = source_map[identity]
        transform_plans.append(
            TimlTransformWritebackPlan(
                type_index=int(identity[0]),
                transform_index=int(identity[1]),
                status="preserve_raw",
                data_type=int(source_transform.data_type),
                source_advanced=identity in advanced_identities,
                timeline_parameter_hash=int(source_type.timeline_parameter_hash),
                datatype_hash=int(source_transform.datatype_hash),
                reason="missing_sampled_transform" if identity in unresolved_missing_identities else "",
            )
        )

    for identity in sorted(sampled_map):
        sampled_transform = sampled_map[identity]
        source_identity = source_identity_by_current.get(identity)
        source_pair = source_map.get(source_identity) if source_identity is not None else None
        source_type = source_pair[0] if source_pair is not None else None
        source_transform = source_pair[1] if source_pair is not None else None
        source_advanced = source_identity in advanced_identities if source_identity is not None else False

        if source_identity is not None and identity == source_identity and identity not in changed_identities:
            transform_plans.append(
                TimlTransformWritebackPlan(
                    type_index=int(identity[0]),
                    transform_index=int(identity[1]),
                    status="preserve_raw",
                    data_type=int(source_transform.data_type),
                    source_advanced=source_advanced,
                    timeline_parameter_hash=int(source_type.timeline_parameter_hash),
                    datatype_hash=int(source_transform.datatype_hash),
                )
            )
            continue

        mismatch_reason = ""
        if source_transform is not None:
            mismatch_reason = _sampled_source_mismatch_reason(source_type, source_transform, sampled_transform)
            if mismatch_reason:
                transform_plans.append(
                    TimlTransformWritebackPlan(
                        type_index=int(identity[0]),
                        transform_index=int(identity[1]),
                        status="unsupported_rebuild",
                        data_type=int(source_transform.data_type),
                        source_advanced=source_advanced,
                        timeline_parameter_hash=int(source_type.timeline_parameter_hash),
                        datatype_hash=int(source_transform.datatype_hash),
                        reason=mismatch_reason,
                    )
                )
                plan.add(
                    "ERROR",
                    "timl.writeback",
                    "TIML transform %02d:%02d binding metadata no longer matches the imported source payload: %s."
                    % (
                        int(identity[0]),
                        int(identity[1]),
                        _sampled_source_mismatch_message(
                            mismatch_reason,
                            source_type=source_type,
                            source_transform=source_transform,
                            sampled_transform=sampled_transform,
                        ),
                    ),
                )
                continue

        value_block_reason = _sampled_transform_writeback_block_reason(sampled_transform)
        if value_block_reason:
            transform_plans.append(
                TimlTransformWritebackPlan(
                    type_index=int(identity[0]),
                    transform_index=int(identity[1]),
                    status="unsupported_rebuild",
                    data_type=int(source_transform.data_type) if source_transform is not None else int(sampled_transform.data_type),
                    source_advanced=source_advanced,
                    timeline_parameter_hash=int(source_type.timeline_parameter_hash)
                    if source_type is not None
                    else int(sampled_transform.timeline_parameter_hash),
                    datatype_hash=int(source_transform.datatype_hash)
                    if source_transform is not None
                    else int(sampled_transform.datatype_hash),
                    reason=value_block_reason,
                )
            )
            plan.add(
                "ERROR",
                "timl.writeback",
                "TIML transform %02d:%02d cannot be written safely because %s."
                % (
                    int(identity[0]),
                    int(identity[1]),
                    _sampled_transform_writeback_block_message(value_block_reason),
                ),
            )
            continue

        if source_transform is not None and can_preserve_source_curve_semantics(source_transform, sampled_transform):
            transform_plans.append(
                TimlTransformWritebackPlan(
                    type_index=int(identity[0]),
                    transform_index=int(identity[1]),
                    status="patch_source_values",
                    data_type=int(source_transform.data_type),
                    source_advanced=source_advanced,
                    timeline_parameter_hash=int(source_type.timeline_parameter_hash),
                    datatype_hash=int(source_transform.datatype_hash),
                )
            )
            continue

        if source_advanced:
            transform_plans.append(
                TimlTransformWritebackPlan(
                    type_index=int(identity[0]),
                    transform_index=int(identity[1]),
                    status="unsupported_rebuild",
                    data_type=int(source_transform.data_type),
                    source_advanced=source_advanced,
                    timeline_parameter_hash=int(source_type.timeline_parameter_hash),
                    datatype_hash=int(source_transform.datatype_hash),
                    reason="advanced_source_rebuild",
                )
            )
            continue

        if _has_unsupported_rebuild_interpolation(sampled_transform):
            transform_plans.append(
                TimlTransformWritebackPlan(
                    type_index=int(identity[0]),
                    transform_index=int(identity[1]),
                    status="unsupported_rebuild",
                    data_type=int(source_transform.data_type) if source_transform is not None else int(sampled_transform.data_type),
                    source_advanced=source_advanced,
                    timeline_parameter_hash=int(source_type.timeline_parameter_hash)
                    if source_type is not None
                    else int(sampled_transform.timeline_parameter_hash),
                    datatype_hash=int(source_transform.datatype_hash)
                    if source_transform is not None
                    else int(sampled_transform.datatype_hash),
                    reason="unsupported_interpolation",
                )
            )
            continue

        transform_plans.append(
            TimlTransformWritebackPlan(
                type_index=int(identity[0]),
                transform_index=int(identity[1]),
                status="rewrite_preview",
                data_type=int(source_transform.data_type) if source_transform is not None else int(sampled_transform.data_type),
                source_advanced=source_advanced,
                timeline_parameter_hash=int(source_type.timeline_parameter_hash)
                if source_type is not None
                else int(sampled_transform.timeline_parameter_hash),
                datatype_hash=int(source_transform.datatype_hash)
                if source_transform is not None
                else int(sampled_transform.datatype_hash),
            )
        )

    plan.transform_plans = tuple(transform_plans)
    patched_advanced = tuple(
        item
        for item in plan.transform_plans
        if item.source_advanced and item.status == "patch_source_values"
    )
    unsupported = tuple(item for item in plan.transform_plans if item.status == "unsupported_rebuild")

    if patched_advanced:
        plan.add(
            "INFO",
            "timl.writeback",
            "Edited TIML transform(s) %s will keep their original source interpolation/easing semantics while writing updated values."
            % _unsupported_labels(patched_advanced, status="patch_source_values"),
        )
    simple_rebuild = tuple(
        item
        for item in plan.transform_plans
        if not item.source_advanced and item.status == "rewrite_preview"
    )
    if simple_rebuild:
        plan.add(
            "INFO",
            "timl.writeback",
            "Edited TIML transform(s) %s changed preview keyframe structure and will be rebuilt from the current Blender keys."
            % _unsupported_labels(simple_rebuild, status="rewrite_preview"),
        )
    blocked_advanced_rebuild = tuple(item for item in unsupported if item.reason == "advanced_source_rebuild")
    if blocked_advanced_rebuild:
        plan.add(
            "ERROR",
            "timl.writeback",
            "Edited TIML transform(s) %s changed keyframe structure, but their source payload uses advanced interpolation/easing semantics. "
            "Structural rebuild is blocked for now; keep advanced-source edits value-only."
            % _unsupported_labels(blocked_advanced_rebuild, status="unsupported_rebuild"),
        )
    if deleted_identities:
        deleted_labels = ", ".join(f"{type_index:02d}:{transform_index:02d}" for type_index, transform_index in sorted(deleted_identities))
        plan.add(
            "INFO",
            "timl.writeback",
            f"TIML source transform(s) {deleted_labels} will be omitted from the rebuilt payload.",
        )
    unsupported_interpolation = tuple(item for item in unsupported if item.reason == "unsupported_interpolation")
    if unsupported_interpolation:
        plan.add(
            "ERROR",
            "timl.writeback",
            "Edited TIML transform(s) %s use unsupported preview interpolation for structural rebuild. Use CONSTANT or LINEAR keyframes for now."
            % _unsupported_labels(unsupported_interpolation, status="unsupported_rebuild"),
        )

    return plan
