"""Orchestrate Blender-side LMT export analysis and source-aware writing.

This module keeps the UI operators thin:
- Blender Action selection and target-armature state still come from scene props
- export sampling, source metadata reuse, TIML writeback matching, and planning
  live here instead of inside the operator module
- binary writers remain in ``core.formats.lmt``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    from ..core.diagnostics.errors import BinaryFormatError
    from ..core.diagnostics.errors import ValidationError
    from ..core.diagnostics.reports import Report
    from ..core.formats.lmt.decoder import decode_action_tracks
    from ..core.formats.lmt.export_context import assess_standalone_export_context
    from ..core.formats.lmt.export_context import build_source_action_export_context
    from ..core.formats.lmt.export_context import LmtSourceActionExportContext
    from ..core.formats.lmt.export_plan import plan_reconstructed_action_export
    from ..core.formats.lmt.merge_writer import write_merged_lmt_file
    from ..core.formats.lmt.quaternion_source_diagnostics import identify_raw_sensitive_quaternion_identities
    from ..core.formats.lmt.reader import read_lmt_bytes
    from ..core.formats.lmt.reconstruction import reconstruct_sampled_action
    from ..core.formats.lmt.source_preservation import identify_preservable_decoded_track_identities
    from ..core.formats.lmt.writer import DEFAULT_VERSION
    from ..core.formats.lmt.writer import write_lmt_file
    from .export_sampling import sample_action_for_lmt_export
    from .timl_export import assess_timl_export_readiness
    from .timl_writeback import build_matching_timl_writeback
    from .timl_writeback import matching_timl_controllers_for_export_action
except ImportError:  # pragma: no cover - test runner imports from addon root
    from core.diagnostics.errors import BinaryFormatError
    from core.diagnostics.errors import ValidationError
    from core.diagnostics.reports import Report
    from core.formats.lmt.decoder import decode_action_tracks
    from core.formats.lmt.export_context import assess_standalone_export_context
    from core.formats.lmt.export_context import build_source_action_export_context
    from core.formats.lmt.export_context import LmtSourceActionExportContext
    from core.formats.lmt.export_plan import plan_reconstructed_action_export
    from core.formats.lmt.merge_writer import write_merged_lmt_file
    from core.formats.lmt.quaternion_source_diagnostics import identify_raw_sensitive_quaternion_identities
    from core.formats.lmt.reader import read_lmt_bytes
    from core.formats.lmt.reconstruction import reconstruct_sampled_action
    from core.formats.lmt.source_preservation import identify_preservable_decoded_track_identities
    from core.formats.lmt.writer import DEFAULT_VERSION
    from core.formats.lmt.writer import write_lmt_file
    from blender_adapter.export_sampling import sample_action_for_lmt_export
    from blender_adapter.timl_export import assess_timl_export_readiness
    from blender_adapter.timl_writeback import build_matching_timl_writeback
    from blender_adapter.timl_writeback import matching_timl_controllers_for_export_action


@dataclass(frozen=True)
class ExportWorkflowDiagnostic:
    level: str
    source: str
    message: str


@dataclass(frozen=True)
class ExportSourceMetadata:
    version: int = DEFAULT_VERSION
    header_unknown: bytes = b"\x00" * 8
    action_id: int = 0
    loop_frame: int = -1
    flags: int = 0
    flags2: int = 0
    track_metadata_by_identity: dict[tuple[int, int], dict[str, object]] | None = None
    source_context: LmtSourceActionExportContext | None = None
    source_lmt: object | None = None
    source_bytes: bytes | None = None
    export_mode: str = "standalone"
    preserve_source_track_identities: frozenset[tuple[int, int]] = frozenset()
    raw_quaternion_source_identities: frozenset[tuple[int, int]] = frozenset()
    replacement_timl_payloads: dict[int, bytes] = field(default_factory=dict)


@dataclass(frozen=True)
class ExportAnalysis:
    action: object | None = None
    sampling_result: object | None = None
    reconstructed: object | None = None
    plan: object | None = None
    metadata: ExportSourceMetadata = field(default_factory=ExportSourceMetadata)
    diagnostics: tuple[ExportWorkflowDiagnostic, ...] = ()
    warning_count: int = 0
    error_count: int = 0
    status_message: str = ""

    @property
    def is_ready(self) -> bool:
        return (
            self.action is not None
            and self.sampling_result is not None
            and self.reconstructed is not None
            and self.plan is not None
            and self.error_count == 0
        )


def effective_export_action(scene_props):
    if scene_props.export_action is not None:
        return scene_props.export_action
    target = scene_props.target_armature
    if target is None or target.animation_data is None:
        return None
    return target.animation_data.action


def _default_export_metadata() -> ExportSourceMetadata:
    return ExportSourceMetadata()


def _workflow_diagnostic(level: str, source: str, message: str) -> ExportWorkflowDiagnostic:
    return ExportWorkflowDiagnostic(level=level.upper(), source=source, message=message)


def _report_diagnostics(report: Report) -> list[ExportWorkflowDiagnostic]:
    return [
        _workflow_diagnostic(diagnostic.level, diagnostic.code, diagnostic.message)
        for diagnostic in report.diagnostics
    ]


def _fallback_source_context_from_action(action) -> LmtSourceActionExportContext | None:
    if action is None:
        return None
    if not any(str(key).startswith("mhw_anim_tools_source_") for key in action.keys()):
        return None
    try:
        action_id = int(action.get("mhw_anim_tools_entry_id", 0))
        version = int(action.get("mhw_anim_tools_source_version", DEFAULT_VERSION))
        entry_count = int(action.get("mhw_anim_tools_source_entry_count", 1))
        action_count = int(action.get("mhw_anim_tools_source_action_count", 1))
        has_timl = bool(action.get("mhw_anim_tools_source_has_timl", False))
        timl_offset = int(action.get("mhw_anim_tools_source_timl_offset", 0))
    except (TypeError, ValueError):
        return None
    return LmtSourceActionExportContext(
        source_name=str(action.get("mhw_anim_tools_source_lmt", "")),
        version=version,
        header_unknown=b"\x00" * 8,
        entry_count=entry_count,
        action_count=action_count,
        action_id=action_id,
        loop_frame=-1,
        null0=(0, 0, 0),
        translation=(0.0, 0.0, 0.0, 0.0),
        rotation_lerp=(0.0, 0.0, 0.0, 1.0),
        flags=0,
        null2=b"\x00\x00",
        flags2=0,
        null3=(0, 0, 0, 0, 0),
        has_timl=has_timl,
        timl_offset=timl_offset,
        track_metadata_by_identity={},
    )


def _standalone_metadata_from_context(
    fallback_context: LmtSourceActionExportContext | None,
    *,
    report: Report,
) -> ExportSourceMetadata:
    fallback_report = assess_standalone_export_context(fallback_context)
    report.diagnostics.extend(fallback_report.diagnostics)
    if fallback_context is None:
        return _default_export_metadata()
    return ExportSourceMetadata(
        version=fallback_context.version,
        action_id=fallback_context.action_id,
        source_context=fallback_context,
        export_mode="standalone",
    )


def resolve_source_action_export_metadata(scene_props, action) -> tuple[ExportSourceMetadata, Report]:
    metadata = _default_export_metadata()
    report = Report()
    source_path = ""
    entry_id = 0
    fallback_context = _fallback_source_context_from_action(action)
    if action is not None:
        source_path = str(action.get("mhw_anim_tools_source_lmt", ""))
        try:
            entry_id = int(action.get("mhw_anim_tools_entry_id", 0))
        except (TypeError, ValueError):
            report.add_warning(
                "lmt.export.source_entry",
                f"Action '{action.name}' has invalid source entry metadata; exporting with entry 0 defaults.",
            )
            entry_id = 0
    if not source_path and scene_props.last_lmt_path:
        source_path = scene_props.last_lmt_path
        if scene_props.lmt_entries and 0 <= scene_props.selected_entry_index < len(scene_props.lmt_entries):
            entry_id = int(scene_props.lmt_entries[scene_props.selected_entry_index].entry_id)

    if not source_path:
        if fallback_context is not None:
            report.add_warning(
                "lmt.export.source_path",
                "Source LMT path is unavailable; exporting with cached container metadata and default track metadata.",
            )
        return _standalone_metadata_from_context(fallback_context, report=report), report

    try:
        source_bytes = Path(source_path).read_bytes()
        lmt = read_lmt_bytes(source_bytes, source_name=source_path)
    except (OSError, ValueError, TypeError, BinaryFormatError) as exc:
        report.add_warning(
            "lmt.export.source_read",
            f"Could not reuse source LMT metadata from '{source_path}'; exporting with defaults instead ({exc}).",
        )
        return _standalone_metadata_from_context(fallback_context, report=report), report

    try:
        source_context = build_source_action_export_context(lmt, entry_id)
    except ValueError:
        report.add_warning(
            "lmt.export.source_entry",
            f"Could not find source LMT entry {entry_id} in '{source_path}'; exporting with default metadata.",
        )
        return _standalone_metadata_from_context(fallback_context, report=report), report

    metadata = ExportSourceMetadata(
        version=source_context.version,
        header_unknown=source_context.header_unknown,
        action_id=source_context.action_id,
        loop_frame=source_context.loop_frame,
        flags=source_context.flags,
        flags2=source_context.flags2,
        track_metadata_by_identity=source_context.track_metadata_by_identity,
        source_context=source_context,
        source_lmt=lmt,
        source_bytes=source_bytes,
        export_mode="merge",
    )
    return metadata, report


def _augment_source_metadata_with_action(
    metadata: ExportSourceMetadata,
    action,
    sampling_result,
    objects,
    *,
    report: Report,
) -> ExportSourceMetadata:
    timl_matches = matching_timl_controllers_for_export_action(action, objects) if action is not None else ()
    if metadata.export_mode != "merge" and timl_matches:
        joined_names = ", ".join(getattr(item, "name", "") for item in timl_matches)
        report.add_warning(
            "lmt.export.timl",
            (
                f"Found imported TIML controller(s) for this source entry ({joined_names}), "
                "but the current export is falling back to standalone mode and will ignore edited TIML data."
            ),
        )

    if metadata.source_lmt is None:
        return metadata

    source_action = None
    for candidate in metadata.source_lmt.actions:
        if int(candidate.id) == int(metadata.action_id):
            source_action = candidate
            break

    preserve_source_track_identities = metadata.preserve_source_track_identities
    raw_quaternion_source_identities = metadata.raw_quaternion_source_identities
    replacement_timl_payloads = dict(metadata.replacement_timl_payloads)
    if source_action is not None:
        decoded_source_action = decode_action_tracks(source_action, strict=False)
        preserve_source_track_identities = identify_preservable_decoded_track_identities(
            decoded_source_action,
            sampling_result.sampled_tracks,
        )
        raw_quaternion_source_identities = identify_raw_sensitive_quaternion_identities(decoded_source_action)
        if raw_quaternion_source_identities:
            preserved_raw_sensitive = raw_quaternion_source_identities & set(preserve_source_track_identities)
            unpreserved_raw_sensitive = raw_quaternion_source_identities - set(preserve_source_track_identities)
            if preserved_raw_sensitive and metadata.export_mode == "merge":
                report.add(
                    "info",
                    "lmt.export.quaternion_source",
                    (
                        f"Merge export will preserve {len(preserved_raw_sensitive)} source quaternion lerp track(s) "
                        "whose raw non-unit key magnitudes matter for sparse structure."
                    ),
                )
            if unpreserved_raw_sensitive:
                report.add_warning(
                    "lmt.export.quaternion_source",
                    (
                        f"{len(unpreserved_raw_sensitive)} source quaternion lerp track(s) rely on raw non-unit key magnitudes; "
                        "motion-equivalent normalized rebuilds may use denser keys than the source track structure."
                    ),
                )

    timl_writeback = build_matching_timl_writeback(
        action,
        objects,
        source_lmt=metadata.source_lmt,
        source_bytes=metadata.source_bytes,
    )
    replacement_timl_payloads.update(timl_writeback.replacement_payloads)
    for diagnostic in timl_writeback.diagnostics:
        report.add(diagnostic.level.lower(), diagnostic.source, diagnostic.message)

    return ExportSourceMetadata(
        version=metadata.version,
        header_unknown=metadata.header_unknown,
        action_id=metadata.action_id,
        loop_frame=metadata.loop_frame,
        flags=metadata.flags,
        flags2=metadata.flags2,
        track_metadata_by_identity=metadata.track_metadata_by_identity,
        source_context=metadata.source_context,
        source_lmt=metadata.source_lmt,
        source_bytes=metadata.source_bytes,
        export_mode=metadata.export_mode,
        preserve_source_track_identities=frozenset(preserve_source_track_identities),
        raw_quaternion_source_identities=frozenset(raw_quaternion_source_identities),
        replacement_timl_payloads=replacement_timl_payloads,
    )


def analyze_export_action(scene_props, *, actions, objects) -> ExportAnalysis:
    action = effective_export_action(scene_props)
    workflow_diagnostics: list[ExportWorkflowDiagnostic] = []

    readiness_report = assess_timl_export_readiness(action, actions) if action is not None else Report()
    workflow_diagnostics.extend(_report_diagnostics(readiness_report))
    if readiness_report.error_count:
        return ExportAnalysis(
            diagnostics=tuple(workflow_diagnostics),
            warning_count=readiness_report.warning_count,
            error_count=readiness_report.error_count,
            status_message="Selected action cannot be exported with the current TIML writer coverage.",
        )

    if scene_props.target_armature is None:
        message = "Choose a target armature before analyzing export data."
        workflow_diagnostics.append(_workflow_diagnostic("ERROR", "armature", message))
        return ExportAnalysis(
            diagnostics=tuple(workflow_diagnostics),
            error_count=1,
            status_message=message,
        )

    if action is None:
        message = "Choose a Blender Action before analyzing export data."
        workflow_diagnostics.append(_workflow_diagnostic("ERROR", "action", message))
        return ExportAnalysis(
            diagnostics=tuple(workflow_diagnostics),
            error_count=1,
            status_message=message,
        )

    sampling_result = sample_action_for_lmt_export(action, scene_props.target_armature)
    workflow_diagnostics.extend(
        _workflow_diagnostic(diagnostic.level, diagnostic.source, diagnostic.message)
        for diagnostic in sampling_result.diagnostics
    )

    metadata, metadata_report = resolve_source_action_export_metadata(scene_props, action)
    metadata = _augment_source_metadata_with_action(
        metadata,
        action,
        sampling_result,
        objects,
        report=metadata_report,
    )

    reconstructed = reconstruct_sampled_action(
        action_name=sampling_result.action_name,
        frame_start=sampling_result.frame_start,
        frame_end=sampling_result.frame_end,
        sampled_tracks=sampling_result.sampled_tracks,
        raw_quaternion_source_identities=metadata.raw_quaternion_source_identities,
    )

    plan = plan_reconstructed_action_export(
        reconstructed,
        track_metadata_by_identity=metadata.track_metadata_by_identity,
        preserve_source_identities=metadata.preserve_source_track_identities,
        raw_quaternion_source_identities=metadata.raw_quaternion_source_identities,
    )

    workflow_diagnostics.extend(_report_diagnostics(metadata_report))
    workflow_diagnostics.extend(
        _workflow_diagnostic(diagnostic.level, diagnostic.source, diagnostic.message)
        for diagnostic in plan.diagnostics
    )

    warning_count = sampling_result.warning_count + metadata_report.warning_count + plan.warning_count
    error_count = sampling_result.error_count + metadata_report.error_count + plan.error_count
    return ExportAnalysis(
        action=action,
        sampling_result=sampling_result,
        reconstructed=reconstructed,
        plan=plan,
        metadata=metadata,
        diagnostics=tuple(workflow_diagnostics),
        warning_count=warning_count,
        error_count=error_count,
    )


def write_export_file(filepath: str, analysis: ExportAnalysis):
    if analysis.reconstructed is None or analysis.plan is None:
        raise ValidationError("Export analysis is incomplete; run analysis before writing an LMT file.")

    metadata = analysis.metadata
    if metadata.source_lmt is not None and metadata.source_bytes is not None:
        return write_merged_lmt_file(
            filepath,
            metadata.source_lmt,
            metadata.source_bytes,
            analysis.reconstructed,
            action_id=metadata.action_id,
            version=metadata.version,
            header_unknown=metadata.header_unknown,
            track_metadata_by_identity=metadata.track_metadata_by_identity,
            preserve_source_identities=metadata.preserve_source_track_identities,
            raw_quaternion_source_identities=metadata.raw_quaternion_source_identities,
            replacement_timl_payloads=metadata.replacement_timl_payloads,
        )
    return write_lmt_file(
        filepath,
        analysis.reconstructed,
        version=metadata.version,
        header_unknown=metadata.header_unknown,
        action_id=metadata.action_id,
        loop_frame=metadata.loop_frame,
        flags=metadata.flags,
        flags2=metadata.flags2,
        track_metadata_by_identity=metadata.track_metadata_by_identity,
        raw_quaternion_source_identities=metadata.raw_quaternion_source_identities,
    )
