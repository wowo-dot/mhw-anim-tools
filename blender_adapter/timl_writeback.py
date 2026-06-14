"""Source-backed TIML controller write-back helpers."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

try:
    from ..core.diagnostics.errors import BinaryFormatError
    from ..core.diagnostics.errors import ValidationError
    from ..core.formats.lmt.export_context import RawTimlPayload
    from ..core.formats.timl.embedded_writer import build_embedded_timl_data_payload
    from ..core.formats.timl.reader import read_timl_data_bytes
    from .timl_export import extract_action_timl_metadata
    from .timl_metadata import TIML_IMPORTED_PREVIEW_SIGNATURE_KEY
    from .timl_preview_state import diff_sampled_transforms_from_imported_signature
    from .timl_sampling import extract_timl_controller_metadata
    from .timl_sampling import is_imported_timl_controller
    from .timl_sampling import sample_timl_controller_action
except ImportError:  # pragma: no cover - test runner imports from addon root
    from core.diagnostics.errors import BinaryFormatError
    from core.diagnostics.errors import ValidationError
    from core.formats.lmt.export_context import RawTimlPayload
    from core.formats.timl.embedded_writer import build_embedded_timl_data_payload
    from core.formats.timl.reader import read_timl_data_bytes
    from blender_adapter.timl_export import extract_action_timl_metadata
    from blender_adapter.timl_metadata import TIML_IMPORTED_PREVIEW_SIGNATURE_KEY
    from blender_adapter.timl_preview_state import diff_sampled_transforms_from_imported_signature
    from blender_adapter.timl_sampling import extract_timl_controller_metadata
    from blender_adapter.timl_sampling import is_imported_timl_controller
    from blender_adapter.timl_sampling import sample_timl_controller_action


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
        if int(metadata.entry_id) != int(action_metadata.entry_id):
            continue
        matches.append(candidate)
    return tuple(sorted(matches, key=lambda item: getattr(item, "name", "")))


def _source_action_by_id(source_lmt, action_id: int):
    for action in source_lmt.actions:
        if int(action.id) == int(action_id):
            return action
    return None


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


def build_matching_timl_writeback(export_action, controller_objects, *, source_lmt, source_bytes: bytes) -> TimlWritebackResult:
    result = TimlWritebackResult()
    action_metadata = extract_action_timl_metadata(export_action)
    if not action_metadata.source_has_timl or not action_metadata.source_lmt:
        return result

    matches = matching_timl_controllers_for_export_action(export_action, controller_objects)
    if not matches:
        return result

    controller = matches[0]
    if len(matches) > 1:
        duplicate_names = ", ".join(getattr(item, "name", "") for item in matches)
        result.add(
            "WARNING",
            "timl.writeback",
            f"Found multiple imported TIML controllers for this source entry ({duplicate_names}); using '{getattr(controller, 'name', '')}'.",
        )

    controller_metadata = extract_timl_controller_metadata(controller)
    source_action = _source_action_by_id(source_lmt, action_metadata.entry_id)
    if source_action is None:
        result.add(
            "ERROR",
            "timl.writeback",
            f"Could not find source LMT action id {action_metadata.entry_id} while preparing TIML write-back.",
        )
        return result

    source_offset = int(controller_metadata.source_offset or source_action.header.timl_offset)
    if source_offset == 0:
        result.add(
            "ERROR",
            "timl.writeback",
            "Matching TIML controller has no valid embedded TIML source offset.",
        )
        return result

    sampled = sample_timl_controller_action(controller)
    for diagnostic in sampled.diagnostics:
        result.add(diagnostic.level, diagnostic.source, diagnostic.message)
    if sampled.error_count:
        return result

    diff = diff_sampled_transforms_from_imported_signature(
        _safe_get(controller, TIML_IMPORTED_PREVIEW_SIGNATURE_KEY, ""),
        sampled.sampled_transforms,
    )
    if not diff.available:
        result.add(
            "WARNING",
            "timl.writeback",
            "TIML controller is missing imported preview signature metadata; merge export will treat all analyzable transforms as edited.",
        )
        changed_transforms = tuple(sampled.sampled_transforms)
    else:
        if diff.missing_identities:
            missing_labels = ", ".join(f"{type_index:02d}:{transform_index:02d}" for type_index, transform_index in diff.missing_identities)
            result.add(
                "WARNING",
                "timl.writeback",
                f"TIML controller is missing preview curves for source transform(s) {missing_labels}; merge export will preserve their original source data.",
            )
        changed_identities = set(diff.edited_identities)
        if not changed_identities:
            result.add(
                "INFO",
                "timl.writeback",
                f"TIML controller '{controller_metadata.action_name}' is unchanged; merge export will preserve the original embedded TIML payload.",
            )
            return result
        changed_transforms = tuple(
            transform
            for transform in sampled.sampled_transforms
            if (int(transform.type_index), int(transform.transform_index)) in changed_identities
        )

    try:
        source_entry = read_timl_data_bytes(
            source_bytes,
            data_offset=source_offset,
            source_name=f"{source_lmt.source_name}#timl",
            entry_id=int(action_metadata.entry_id),
        )
        advanced_identities = _advanced_source_transform_identities(source_entry)
        changed_advanced = sorted(
            (int(transform.type_index), int(transform.transform_index))
            for transform in changed_transforms
            if (int(transform.type_index), int(transform.transform_index)) in advanced_identities
        )
        if changed_advanced:
            changed_labels = ", ".join(f"{type_index:02d}:{transform_index:02d}" for type_index, transform_index in changed_advanced)
            result.add(
                "WARNING",
                "timl.writeback",
                f"Edited TIML transform(s) {changed_labels} were imported from advanced interpolation/easing; merge export will replace those source semantics with the current preview curves.",
            )
        payload, rebase_offsets = build_embedded_timl_data_payload(
            source_entry,
            changed_transforms,
            base_offset=source_offset,
        )
    except (BinaryFormatError, ValidationError, ValueError) as exc:
        result.add("ERROR", "timl.writeback", str(exc))
        return result

    shared_action_ids = tuple(
        int(action.id)
        for action in source_lmt.actions
        if int(action.header.timl_offset) == source_offset
    )
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
                f"Merge export will include {len(changed_transforms)} edited TIML transform(s) "
                f"from '{controller_metadata.action_name}' and preserve untouched source transforms."
            ),
        )

    result.controller_name = controller_metadata.carrier_name
    result.action_name = controller_metadata.action_name
    result.source_offset = source_offset
    result.shared_action_ids = shared_action_ids
    result.replacement_payloads[source_offset] = RawTimlPayload(payload=payload, rebase_offsets=rebase_offsets)
    return result
