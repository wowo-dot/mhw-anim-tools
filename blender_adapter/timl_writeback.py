"""Source-backed TIML controller write-back helpers."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

try:
    from ..core.diagnostics.errors import BinaryFormatError
    from ..core.diagnostics.errors import ValidationError
    from ..core.formats.lmt.export_context import RawTimlPayload
    from ..core.formats.timl.embedded_writer import build_embedded_timl_data_payload
    from ..core.formats.timl.embedded_writer import build_embedded_timl_data_payload_from_sampled
    from .timl_authoring import timl_header_state_from_controller
    from .timl_export import extract_action_timl_metadata
    from .timl_sampling import extract_timl_controller_metadata
    from .timl_sampling import is_imported_timl_controller
    from .timl_writeback_plan import plan_timl_controller_writeback
except ImportError:  # pragma: no cover - test runner imports from addon root
    from core.diagnostics.errors import BinaryFormatError
    from core.diagnostics.errors import ValidationError
    from core.formats.lmt.export_context import RawTimlPayload
    from core.formats.timl.embedded_writer import build_embedded_timl_data_payload
    from core.formats.timl.embedded_writer import build_embedded_timl_data_payload_from_sampled
    from blender_adapter.timl_authoring import timl_header_state_from_controller
    from blender_adapter.timl_export import extract_action_timl_metadata
    from blender_adapter.timl_sampling import extract_timl_controller_metadata
    from blender_adapter.timl_sampling import is_imported_timl_controller
    from blender_adapter.timl_writeback_plan import plan_timl_controller_writeback


@dataclass(frozen=True)
class TimlWritebackDiagnostic:
    level: str
    source: str
    message: str


@dataclass
class TimlWritebackResult:
    controller_name: str = ""
    action_name: str = ""
    source_offset: int = 0
    shared_action_ids: tuple[int, ...] = ()
    replacement_payloads: dict[int, RawTimlPayload] = field(default_factory=dict)
    diagnostics: list[TimlWritebackDiagnostic] = field(default_factory=list)

    def add(self, level: str, source: str, message: str):
        self.diagnostics.append(TimlWritebackDiagnostic(level=level, source=source, message=message))

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "WARNING")

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "ERROR")


@dataclass(frozen=True)
class TimlSharedPayloadAssessment:
    source_offset: int = 0
    shared_action_ids: tuple[int, ...] = ()
    matching_controller_names: tuple[str, ...] = ()
    status: str = ""
    diagnostics: tuple[TimlWritebackDiagnostic, ...] = ()


def matching_timl_controllers_for_export_action(export_action, controller_objects) -> tuple[object, ...]:
    action_metadata = extract_action_timl_metadata(export_action)
    if not action_metadata.source_lmt or action_metadata.entry_id < 0:
        return ()
    matches = []
    for candidate in controller_objects:
        if not is_imported_timl_controller(candidate):
            continue
        metadata = extract_timl_controller_metadata(candidate)
        if metadata.source_lmt != action_metadata.source_lmt:
            continue
        same_entry = int(metadata.entry_id) == int(action_metadata.entry_id)
        same_offset = (
            int(action_metadata.source_timl_offset) > 0
            and int(metadata.source_offset) == int(action_metadata.source_timl_offset)
        )
        if not same_entry and not same_offset:
            continue
        matches.append((0 if same_entry else 1, candidate))
    return tuple(
        candidate
        for _priority, candidate in sorted(
            matches,
            key=lambda item: (item[0], getattr(item[1], "name", "")),
        )
    )


def _source_action_by_id(source_lmt, action_id: int):
    for action in source_lmt.actions:
        if int(action.id) == int(action_id):
            return action
    return None


def _shared_source_action_ids(source_lmt, source_offset: int) -> tuple[int, ...]:
    return tuple(
        int(action.id)
        for action in source_lmt.actions
        if int(action.header.timl_offset) == int(source_offset)
    )


def shared_source_action_ids(source_lmt, source_offset: int) -> tuple[int, ...]:
    return _shared_source_action_ids(source_lmt, source_offset)


def assess_timl_controller_shared_payload(controller_object, controller_objects, *, source_lmt, source_bytes: bytes) -> TimlSharedPayloadAssessment:
    metadata = extract_timl_controller_metadata(controller_object)
    if not metadata.source_lmt or int(metadata.source_offset) <= 0:
        return TimlSharedPayloadAssessment()

    export_action = {
        "name": metadata.action_name or metadata.carrier_name,
        "mhw_anim_tools_import_kind": "lmt_action",
        "mhw_anim_tools_source_lmt": metadata.source_lmt,
        "mhw_anim_tools_entry_id": int(metadata.entry_id),
        "mhw_anim_tools_source_timl_offset": int(metadata.source_offset),
        "mhw_anim_tools_source_has_timl": True,
    }
    shared_action_ids = shared_source_action_ids(source_lmt, int(metadata.source_offset))
    matches = matching_timl_controllers_for_export_action(export_action, controller_objects)
    matching_controller_names = tuple(
        sorted(
            {
                str(getattr(controller, "name", "") or "")
                for controller in matches
                if str(getattr(controller, "name", "") or "")
            }
        )
    )
    if not matches:
        return TimlSharedPayloadAssessment(
            source_offset=int(metadata.source_offset),
            shared_action_ids=shared_action_ids,
            matching_controller_names=(),
        )

    if len(matches) == 1:
        diagnostics: list[TimlWritebackDiagnostic] = []
        if len(shared_action_ids) > 1:
            shared_labels = ", ".join(f"{action_id:03d}" for action_id in shared_action_ids)
            controller_label = matching_controller_names[0] if matching_controller_names else str(getattr(controller_object, "name", "") or "")
            diagnostics.append(
                TimlWritebackDiagnostic(
                    level="INFO",
                    source="timl.writeback",
                    message=(
                        f"Embedded TIML payload is shared by source actions {shared_labels}, "
                        f"but only one imported controller currently matches it ({controller_label})."
                    ),
                )
            )
        return TimlSharedPayloadAssessment(
            source_offset=int(metadata.source_offset),
            shared_action_ids=shared_action_ids,
            matching_controller_names=matching_controller_names,
            status="single",
            diagnostics=tuple(diagnostics),
        )

    result = build_matching_timl_writeback(
        export_action,
        controller_objects,
        source_lmt=source_lmt,
        source_bytes=source_bytes,
    )
    if result.error_count:
        status = "conflict"
        level = "ERROR"
        message = (
            "Multiple imported TIML controllers match this shared embedded payload, "
            "but they do not currently resolve to one consistent writeback payload."
        )
    else:
        status = "consistent"
        level = "INFO"
        message = (
            "Multiple imported TIML controllers match this shared embedded payload "
            "and currently resolve to one consistent writeback payload."
        )
    return TimlSharedPayloadAssessment(
        source_offset=int(metadata.source_offset),
        shared_action_ids=shared_action_ids,
        matching_controller_names=matching_controller_names,
        status=status,
        diagnostics=(
            TimlWritebackDiagnostic(level=level, source="timl.writeback", message=message),
        ),
    )


def _payload_signature(payload, rebase_offsets) -> tuple[bytes, tuple[int, ...]]:
    return (bytes(payload), tuple(int(offset) for offset in rebase_offsets))


def _source_entry_has_no_transforms(source_entry) -> bool:
    if source_entry is None:
        return True
    return not any(getattr(type_entry, "transforms", ()) for type_entry in getattr(source_entry, "types", ()))

def build_matching_timl_writeback(export_action, controller_objects, *, source_lmt, source_bytes: bytes) -> TimlWritebackResult:
    result = TimlWritebackResult()
    action_metadata = extract_action_timl_metadata(export_action)
    if not action_metadata.source_has_timl or not action_metadata.source_lmt:
        return result

    source_action = _source_action_by_id(source_lmt, action_metadata.entry_id)
    if source_action is None:
        result.add(
            "ERROR",
            "timl.writeback",
            f"Could not find source LMT action id {action_metadata.entry_id} while preparing TIML write-back.",
        )
        return result

    expected_source_offset = int(action_metadata.source_timl_offset or source_action.header.timl_offset)
    if expected_source_offset == 0:
        result.add(
            "ERROR",
            "timl.writeback",
            "Matching TIML controller has no valid embedded TIML source offset.",
        )
        return result

    matches = matching_timl_controllers_for_export_action(export_action, controller_objects)
    if not matches:
        return result

    if len(matches) > 1:
        duplicate_names = ", ".join(getattr(item, "name", "") for item in matches)
        result.add(
            "WARNING",
            "timl.writeback",
            (
                "Found multiple imported TIML controllers for this source payload "
                f"({duplicate_names}); export will compare them before choosing a writeback payload."
            ),
        )
    changed_payloads: list[tuple[str, str, bytes, tuple[int, ...], int]] = []
    invalid_controller_names: list[str] = []

    for controller in matches:
        controller_metadata = extract_timl_controller_metadata(controller)
        controller_name = controller_metadata.carrier_name or getattr(controller, "name", "")
        source_offset = int(controller_metadata.source_offset or source_action.header.timl_offset)
        if source_offset != expected_source_offset:
            result.add(
                "WARNING",
                "timl.writeback",
                (
                    f"Skipping TIML controller '{controller_name}' because it points at source offset "
                    f"0x{source_offset:X}, not the expected shared offset 0x{expected_source_offset:X}."
                ),
            )
            continue

        plan = plan_timl_controller_writeback(
            controller,
            source_bytes=source_bytes,
            source_name=f"{source_lmt.source_name}#timl",
            entry_id=int(action_metadata.entry_id),
            source_offset=source_offset,
        )
        for diagnostic in plan.diagnostics:
            result.add(diagnostic.level, diagnostic.source, diagnostic.message)
        if plan.error_count:
            invalid_controller_names.append(controller_name)
            continue
        changed_transforms = tuple(plan.changed_transforms)
        if not changed_transforms:
            continue

        try:
            if _source_entry_has_no_transforms(plan.source_entry):
                header_state = timl_header_state_from_controller(
                    controller,
                    source_lmt=controller_metadata.source_lmt,
                    entry_id=int(controller_metadata.entry_id),
                )
                payload, rebase_offsets = build_embedded_timl_data_payload_from_sampled(
                    changed_transforms,
                    base_offset=source_offset,
                    data_index_a=int(header_state["data_index_a"]),
                    data_index_b=int(header_state["data_index_b"]),
                    animation_length=float(header_state["animation_length"]),
                    loop_start_point=float(header_state["loop_start_point"]),
                    loop_control=int(header_state["loop_control"]),
                    label_hash=int(header_state["label_hash"]),
                )
            else:
                payload, rebase_offsets = build_embedded_timl_data_payload(
                    plan.source_entry,
                    changed_transforms,
                    base_offset=source_offset,
                )
        except (BinaryFormatError, ValidationError, ValueError) as exc:
            result.add("ERROR", "timl.writeback", str(exc))
            invalid_controller_names.append(controller_name)
            continue
        changed_payloads.append(
            (
                controller_name,
                controller_metadata.action_name,
                payload,
                tuple(rebase_offsets),
                source_offset,
            )
        )

    if not changed_payloads:
        return result

    if invalid_controller_names:
        result.add(
            "ERROR",
            "timl.writeback",
            (
                "Refusing TIML writeback because one or more matching controllers for the same source payload "
                f"could not be planned safely: {', '.join(sorted(invalid_controller_names))}."
            ),
        )
        return result

    grouped_payloads: dict[tuple[bytes, tuple[int, ...]], list[tuple[str, str]]] = {}
    for controller_name, action_name, payload, rebase_offsets, _source_offset in changed_payloads:
        grouped_payloads.setdefault(_payload_signature(payload, rebase_offsets), []).append((controller_name, action_name))

    if len(grouped_payloads) > 1:
        description = "; ".join(
            ", ".join(sorted(controller_name for controller_name, _action_name in names))
            for names in grouped_payloads.values()
        )
        result.add(
            "ERROR",
            "timl.writeback",
            (
                "Refusing TIML writeback because matching controllers for the same shared source payload "
                f"produce different edited TIML data: {description}."
            ),
        )
        return result

    (payload, rebase_offsets), chosen_names = next(iter(grouped_payloads.items()))
    controller_names = sorted(controller_name for controller_name, _action_name in chosen_names)
    action_names = sorted(action_name for _controller_name, action_name in chosen_names if action_name)
    source_offset = int(changed_payloads[0][4])
    shared_action_ids = shared_source_action_ids(source_lmt, source_offset)
    if len(shared_action_ids) > 1:
        shared_labels = ", ".join(f"{action_id:03d}" for action_id in shared_action_ids)
        result.add(
            "WARNING",
            "timl.writeback",
            f"Edited TIML payload is shared by source actions {shared_labels}; merge export will update all of them together.",
        )
    else:
        result.add(
            "INFO",
            "timl.writeback",
            (
                "Merge export will include edited TIML transform data "
                f"from '{', '.join(action_names or controller_names)}' and preserve untouched source transforms."
            ),
        )
    if len(chosen_names) > 1:
        result.add(
            "INFO",
            "timl.writeback",
            (
                "Multiple controllers for the same shared TIML payload resolved to identical edited data: "
                f"{', '.join(controller_names)}."
            ),
        )

    result.controller_name = controller_names[0] if controller_names else ""
    result.action_name = action_names[0] if action_names else ""
    result.source_offset = source_offset
    result.shared_action_ids = shared_action_ids
    result.replacement_payloads[source_offset] = RawTimlPayload(payload=payload, rebase_offsets=rebase_offsets)
    return result
