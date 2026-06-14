"""Plan how an imported TIML controller can be written back during merge export."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

try:
    from ..core.formats.timl.embedded_writer import preserved_source_curve_identities
    from ..core.formats.timl.reader import read_timl_data_bytes
    from .timl_metadata import TIML_IMPORTED_PREVIEW_SIGNATURE_KEY
    from .timl_preview_state import diff_sampled_transforms_from_imported_signature
    from .timl_sampling import sample_timl_controller_action
except ImportError:  # pragma: no cover - test runner imports from addon root
    from core.formats.timl.embedded_writer import preserved_source_curve_identities
    from core.formats.timl.reader import read_timl_data_bytes
    from blender_adapter.timl_metadata import TIML_IMPORTED_PREVIEW_SIGNATURE_KEY
    from blender_adapter.timl_preview_state import diff_sampled_transforms_from_imported_signature
    from blender_adapter.timl_sampling import sample_timl_controller_action


WRITABLE_BLENDER_INTERPOLATIONS = {"CONSTANT", "LINEAR"}


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
    reason: str = ""

    @property
    def identity(self) -> tuple[int, int]:
        return (int(self.type_index), int(self.transform_index))


@dataclass
class TimlControllerWritebackPlan:
    source_entry: object | None = None
    sampled_result: object | None = None
    transform_plans: tuple[TimlTransformWritebackPlan, ...] = ()
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
    sampled_map = {
        (int(transform.type_index), int(transform.transform_index)): transform
        for transform in sampled.sampled_transforms
    }
    advanced_identities = _advanced_source_transform_identities(source_entry)
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
    else:
        changed_identities = set(diff.edited_identities)
        if diff.missing_identities:
            missing_labels = ", ".join(f"{type_index:02d}:{transform_index:02d}" for type_index, transform_index in diff.missing_identities)
            plan.add(
                "WARNING",
                "timl.writeback",
                f"TIML controller is missing preview curves for source transform(s) {missing_labels}; merge export will preserve their original source data.",
            )
        if not changed_identities:
            action_name = ""
            if getattr(sampled, "metadata", None) is not None:
                action_name = str(getattr(sampled.metadata, "action_name", "") or "")
            plan.add(
                "INFO",
                "timl.writeback",
                f"TIML controller '{action_name}' is unchanged; merge export will preserve the original embedded TIML payload.",
            )

    preserved_patch_identities = preserved_source_curve_identities(
        source_entry,
        tuple(sampled_map[identity] for identity in changed_identities if identity in sampled_map),
    )

    transform_plans: list[TimlTransformWritebackPlan] = []
    for type_index, type_entry in enumerate(source_entry.types):
        for transform_index, source_transform in enumerate(type_entry.transforms):
            identity = (int(type_index), int(transform_index))
            sampled_transform = sampled_map.get(identity)
            source_advanced = identity in advanced_identities
            if identity not in changed_identities:
                transform_plans.append(
                    TimlTransformWritebackPlan(
                        type_index=type_index,
                        transform_index=transform_index,
                        status="preserve_raw",
                        data_type=int(source_transform.data_type),
                        source_advanced=source_advanced,
                    )
                )
                continue
            if sampled_transform is None:
                transform_plans.append(
                    TimlTransformWritebackPlan(
                        type_index=type_index,
                        transform_index=transform_index,
                        status="preserve_raw",
                        data_type=int(source_transform.data_type),
                        source_advanced=source_advanced,
                        reason="missing_sampled_transform",
                    )
                )
                continue
            mismatch_reason = _sampled_source_mismatch_reason(type_entry, source_transform, sampled_transform)
            if mismatch_reason:
                transform_plans.append(
                    TimlTransformWritebackPlan(
                        type_index=type_index,
                        transform_index=transform_index,
                        status="unsupported_rebuild",
                        data_type=int(source_transform.data_type),
                        source_advanced=source_advanced,
                        reason=mismatch_reason,
                    )
                )
                plan.add(
                    "ERROR",
                    "timl.writeback",
                    "TIML transform %02d:%02d binding metadata no longer matches the imported source payload: %s."
                    % (
                        int(type_index),
                        int(transform_index),
                        _sampled_source_mismatch_message(
                            mismatch_reason,
                            source_type=type_entry,
                            source_transform=source_transform,
                            sampled_transform=sampled_transform,
                        ),
                    ),
                )
                continue
            if identity in preserved_patch_identities:
                transform_plans.append(
                    TimlTransformWritebackPlan(
                        type_index=type_index,
                        transform_index=transform_index,
                        status="patch_source_values",
                        data_type=int(source_transform.data_type),
                        source_advanced=source_advanced,
                    )
                )
                continue
            if _has_unsupported_rebuild_interpolation(sampled_transform):
                transform_plans.append(
                    TimlTransformWritebackPlan(
                        type_index=type_index,
                        transform_index=transform_index,
                        status="unsupported_rebuild",
                        data_type=int(source_transform.data_type),
                        source_advanced=source_advanced,
                        reason="unsupported_interpolation",
                    )
                )
                continue
            transform_plans.append(
                TimlTransformWritebackPlan(
                    type_index=type_index,
                    transform_index=transform_index,
                    status="rewrite_preview",
                    data_type=int(source_transform.data_type),
                    source_advanced=source_advanced,
                )
            )

    extra_identities = sorted(set(sampled_map) - {plan_item.identity for plan_item in transform_plans})
    if extra_identities:
        extra_labels = ", ".join(f"{type_index:02d}:{transform_index:02d}" for type_index, transform_index in extra_identities)
        plan.add(
            "ERROR",
            "timl.writeback",
            f"TIML controller contains sampled transforms not present in the source payload: {extra_labels}.",
        )

    plan.transform_plans = tuple(transform_plans)
    patched_advanced = tuple(
        item
        for item in plan.transform_plans
        if item.source_advanced and item.status == "patch_source_values"
    )
    rebuilt_advanced = tuple(
        item
        for item in plan.transform_plans
        if item.source_advanced and item.status == "rewrite_preview"
    )
    unsupported = tuple(item for item in plan.transform_plans if item.status == "unsupported_rebuild")

    if patched_advanced:
        plan.add(
            "INFO",
            "timl.writeback",
            "Edited TIML transform(s) %s will keep their original source interpolation/easing semantics while writing updated values."
            % _unsupported_labels(patched_advanced, status="patch_source_values"),
        )
    if rebuilt_advanced:
        plan.add(
            "WARNING",
            "timl.writeback",
            "Edited TIML transform(s) %s changed their preview keyframe structure; merge export will rebuild them from the current preview curves."
            % _unsupported_labels(rebuilt_advanced, status="rewrite_preview"),
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
