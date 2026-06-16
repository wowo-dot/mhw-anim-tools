"""Standalone TIML file export helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    from ..core.diagnostics.errors import BinaryFormatError
    from ..core.diagnostics.errors import ValidationError
    from ..core.formats.timl.embedded_writer import build_embedded_timl_data_payload
    from ..core.formats.timl.model import EXPECTED_LAYOUT_SIGNATURE
    from ..core.formats.timl.reader import read_timl_file
    from ..core.formats.timl.writer import resolve_timl_payload_layout
    from ..core.formats.timl.writer import write_timl_payload_map
    from .timl_authoring import load_deleted_timl_identities
    from .timl_authoring import timl_header_state_from_controller
    from .timl_metadata import TIML_SOURCE_KIND_STANDALONE_FILE
    from .timl_sampling import extract_timl_controller_metadata
    from .timl_sampling import is_imported_timl_controller
    from .timl_sampling import sample_timl_controller_action
except ImportError:  # pragma: no cover - test runner imports from addon root
    from blender_adapter.timl_authoring import load_deleted_timl_identities
    from blender_adapter.timl_authoring import timl_header_state_from_controller
    from blender_adapter.timl_metadata import TIML_SOURCE_KIND_STANDALONE_FILE
    from blender_adapter.timl_sampling import extract_timl_controller_metadata
    from blender_adapter.timl_sampling import is_imported_timl_controller
    from blender_adapter.timl_sampling import sample_timl_controller_action
    from core.diagnostics.errors import BinaryFormatError
    from core.diagnostics.errors import ValidationError
    from core.formats.timl.embedded_writer import build_embedded_timl_data_payload
    from core.formats.timl.model import EXPECTED_LAYOUT_SIGNATURE
    from core.formats.timl.reader import read_timl_file
    from core.formats.timl.writer import resolve_timl_payload_layout
    from core.formats.timl.writer import write_timl_payload_map


@dataclass(frozen=True)
class StandaloneTimlExportDiagnostic:
    level: str
    source: str
    message: str


@dataclass(frozen=True)
class StandaloneTimlEntryPlan:
    entry_id: int
    source_entry: object | None = None
    sampled_transforms: tuple[object, ...] = ()
    deleted_identities: tuple[tuple[int, int], ...] = ()
    data_index_a: int = 0
    data_index_b: int = 0
    animation_length: float = 0.0
    loop_start_point: float = 0.0
    loop_control: int = 0
    label_hash: int = 0
    imported: bool = False


@dataclass
class StandaloneTimlExportAnalysis:
    source_path: str = ""
    source_entry_count: int = 0
    source_reserved: int = 0
    source_layout_signature: bytes = EXPECTED_LAYOUT_SIGNATURE
    controller_names: tuple[str, ...] = ()
    sampled_entry_count: int = 0
    sampled_transform_count: int = 0
    keyframe_count: int = 0
    frame_end: int = 0
    entry_plans: tuple[StandaloneTimlEntryPlan, ...] = ()
    diagnostics: list[StandaloneTimlExportDiagnostic] = field(default_factory=list)

    def add(self, level: str, source: str, message: str):
        self.diagnostics.append(StandaloneTimlExportDiagnostic(level=level, source=source, message=message))

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "WARNING")

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "ERROR")


def _matching_standalone_controllers(controller_objects, *, source_path: str, session_id: str) -> tuple[object, ...]:
    matches = []
    for controller in controller_objects:
        if not is_imported_timl_controller(controller):
            continue
        metadata = extract_timl_controller_metadata(controller)
        if str(metadata.source_kind or "") != TIML_SOURCE_KIND_STANDALONE_FILE:
            continue
        if str(metadata.source_lmt or "") != str(source_path or ""):
            continue
        if session_id and str(metadata.session_id or "") != str(session_id):
            continue
        matches.append(controller)
    return tuple(sorted(matches, key=lambda controller: int(extract_timl_controller_metadata(controller).entry_id)))


def _payload_for_plan(plan: StandaloneTimlEntryPlan, *, base_offset: int) -> bytes:
    if plan.source_entry is None:
        raise ValidationError(
            f"Standalone TIML entry {int(plan.entry_id):03d} has no source payload to preserve. "
            "Creating brand-new standalone entry payloads from empty source slots is not available yet."
        )
    payload, _rebase_offsets = build_embedded_timl_data_payload(
        plan.source_entry,
        tuple(plan.sampled_transforms),
        base_offset=int(base_offset),
        deleted_identities=tuple(plan.deleted_identities),
        data_index_a=int(plan.data_index_a),
        data_index_b=int(plan.data_index_b),
        animation_length=float(plan.animation_length),
        loop_start_point=float(plan.loop_start_point),
        loop_control=int(plan.loop_control),
        label_hash=int(plan.label_hash),
    )
    return payload


def analyze_standalone_timl_export(controller_object, *, controller_objects) -> StandaloneTimlExportAnalysis:
    analysis = StandaloneTimlExportAnalysis()
    if controller_object is None or not is_imported_timl_controller(controller_object):
        analysis.add("ERROR", "timl.export", "Choose an imported standalone TIML controller before saving.")
        return analysis

    metadata = extract_timl_controller_metadata(controller_object)
    if str(metadata.source_kind or "") != TIML_SOURCE_KIND_STANDALONE_FILE:
        analysis.add("ERROR", "timl.export", "Selected controller does not come from a standalone TIML file.")
        return analysis
    if not str(metadata.source_lmt or ""):
        analysis.add("ERROR", "timl.export", "Selected standalone TIML controller is missing its source file path.")
        return analysis

    analysis.source_path = str(metadata.source_lmt or "")
    try:
        source_timl = read_timl_file(analysis.source_path)
    except (BinaryFormatError, OSError, ValueError) as exc:
        analysis.add("ERROR", "timl.export", f"Could not read source TIML file: {exc}")
        return analysis

    analysis.source_entry_count = int(source_timl.header.entry_count)
    analysis.source_reserved = int(source_timl.header.reserved)
    analysis.source_layout_signature = bytes(source_timl.header.layout_signature or EXPECTED_LAYOUT_SIGNATURE)
    source_entries_by_id = {int(entry.id): entry for entry in source_timl.data_entries}

    matches = _matching_standalone_controllers(
        controller_objects,
        source_path=analysis.source_path,
        session_id=str(metadata.session_id or ""),
    )
    if not matches:
        analysis.add("ERROR", "timl.export", "No standalone TIML controllers were found for the selected source file.")
        return analysis

    current_entry_ids = [int(extract_timl_controller_metadata(controller).entry_id) for controller in matches]
    duplicate_entry_ids = sorted({entry_id for entry_id in current_entry_ids if current_entry_ids.count(entry_id) > 1})
    if duplicate_entry_ids:
        labels = ", ".join(f"{entry_id:03d}" for entry_id in duplicate_entry_ids)
        analysis.add("ERROR", "timl.export", f"Multiple standalone TIML controllers target the same entry id: {labels}.")
        return analysis

    imported_plans: dict[int, StandaloneTimlEntryPlan] = {}
    controller_names: list[str] = []
    for controller in matches:
        controller_metadata = extract_timl_controller_metadata(controller)
        entry_id = int(controller_metadata.entry_id)
        controller_name = str(getattr(controller, "name", "") or controller_metadata.carrier_name or "")
        if entry_id < 0 or entry_id >= int(source_timl.header.entry_count):
            analysis.add(
                "ERROR",
                "timl.export",
                (
                    f"Standalone TIML controller '{controller_name}' targets entry {entry_id:03d}, "
                    f"outside the source file entry count {int(source_timl.header.entry_count)}."
                ),
            )
            continue

        sample = sample_timl_controller_action(controller)
        for diagnostic in sample.diagnostics:
            analysis.add(diagnostic.level, diagnostic.source, diagnostic.message)
        if sample.error_count:
            continue

        header_state = timl_header_state_from_controller(
            controller,
            source_lmt=str(controller_metadata.source_lmt or ""),
            entry_id=entry_id,
        )
        imported_plans[entry_id] = StandaloneTimlEntryPlan(
            entry_id=entry_id,
            source_entry=source_entries_by_id.get(entry_id),
            sampled_transforms=tuple(sample.sampled_transforms),
            deleted_identities=tuple(load_deleted_timl_identities(controller)),
            data_index_a=int(header_state["data_index_a"]),
            data_index_b=int(header_state["data_index_b"]),
            animation_length=float(header_state["animation_length"]),
            loop_start_point=float(header_state["loop_start_point"]),
            loop_control=int(header_state["loop_control"]),
            label_hash=int(header_state["label_hash"]),
            imported=True,
        )
        controller_names.append(controller_name)
        analysis.sampled_entry_count += 1
        analysis.sampled_transform_count += int(sample.sampled_transform_count)
        analysis.keyframe_count += int(sample.keyframe_count)
        analysis.frame_end = max(analysis.frame_end, int(sample.frame_end))

    if analysis.error_count:
        return analysis
    if not imported_plans:
        analysis.add("ERROR", "timl.export", "No standalone TIML entries were ready to save.")
        return analysis

    entry_plans: list[StandaloneTimlEntryPlan] = []
    for entry_id in range(int(source_timl.header.entry_count)):
        imported_plan = imported_plans.get(entry_id)
        if imported_plan is not None:
            entry_plans.append(imported_plan)
            continue
        source_entry = source_entries_by_id.get(entry_id)
        if source_entry is None:
            continue
        entry_plans.append(
            StandaloneTimlEntryPlan(
                entry_id=entry_id,
                source_entry=source_entry,
                sampled_transforms=(),
                deleted_identities=(),
                data_index_a=int(source_entry.data_index_a),
                data_index_b=int(source_entry.data_index_b),
                animation_length=float(source_entry.animation_length),
                loop_start_point=float(source_entry.loop_start_point),
                loop_control=int(source_entry.loop_control),
                label_hash=int(source_entry.label_hash),
                imported=False,
            )
        )

    analysis.controller_names = tuple(controller_names)
    analysis.entry_plans = tuple(entry_plans)
    return analysis


def write_standalone_timl_file(output_path: str | Path, analysis: StandaloneTimlExportAnalysis) -> Path:
    if analysis.error_count:
        messages = "; ".join(diagnostic.message for diagnostic in analysis.diagnostics if diagnostic.level == "ERROR")
        raise ValidationError(messages or "Standalone TIML export analysis failed.")
    if not analysis.entry_plans:
        raise ValidationError("No standalone TIML entries are available to write.")

    first_pass_payloads = {
        int(plan.entry_id): _payload_for_plan(plan, base_offset=0)
        for plan in analysis.entry_plans
    }
    _entry_table_offset, entry_offsets, _blob_size = resolve_timl_payload_layout(
        first_pass_payloads,
        entry_count=int(analysis.source_entry_count),
    )
    final_payloads = {
        int(plan.entry_id): _payload_for_plan(
            plan,
            base_offset=int(entry_offsets[int(plan.entry_id)]),
        )
        for plan in analysis.entry_plans
    }

    target_path = Path(output_path)
    target_path.write_bytes(
        write_timl_payload_map(
            final_payloads,
            entry_count=int(analysis.source_entry_count),
            reserved=int(analysis.source_reserved),
            layout_signature=bytes(analysis.source_layout_signature or EXPECTED_LAYOUT_SIGNATURE),
        )
    )
    return target_path
