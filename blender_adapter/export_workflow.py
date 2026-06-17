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
    from ..core.formats.lmt.merge_writer import write_multi_merged_lmt_file
    from ..core.formats.lmt.quaternion_source_diagnostics import identify_raw_sensitive_quaternion_identities
    from ..core.formats.lmt.reader import read_lmt_bytes
    from ..core.formats.lmt.reconstruction import reconstruct_sampled_action
    from ..core.formats.lmt.source_preservation import identify_preservable_decoded_track_identities
    from ..core.formats.lmt.writer import DEFAULT_VERSION
    from ..core.formats.lmt.writer import write_lmt_file
    from .export_sampling import sample_action_for_lmt_export
    from .export_impact import ExportImpactSummary
    from .export_impact import build_export_impact_summary
    from .lmt_track_metadata import bindings_cover_duplicate_identities
    from .lmt_track_metadata import load_lmt_import_track_bindings
    from .source_identity import load_source_file_identity
    from .source_identity import source_file_identity_from_bytes
    from .source_identity import SourceFileIdentity
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
    from core.formats.lmt.merge_writer import write_multi_merged_lmt_file
    from core.formats.lmt.quaternion_source_diagnostics import identify_raw_sensitive_quaternion_identities
    from core.formats.lmt.reader import read_lmt_bytes
    from core.formats.lmt.reconstruction import reconstruct_sampled_action
    from core.formats.lmt.source_preservation import identify_preservable_decoded_track_identities
    from core.formats.lmt.writer import DEFAULT_VERSION
    from core.formats.lmt.writer import write_lmt_file
    from blender_adapter.export_impact import ExportImpactSummary
    from blender_adapter.export_impact import build_export_impact_summary
    from blender_adapter.lmt_track_metadata import bindings_cover_duplicate_identities
    from blender_adapter.lmt_track_metadata import load_lmt_import_track_bindings
    from blender_adapter.source_identity import load_source_file_identity
    from blender_adapter.source_identity import source_file_identity_from_bytes
    from blender_adapter.source_identity import SourceFileIdentity
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
    track_metadata_by_index: dict[int, dict[str, object]] | None = None
    source_context: LmtSourceActionExportContext | None = None
    source_lmt: object | None = None
    source_bytes: bytes | None = None
    imported_source_identity: SourceFileIdentity | None = None
    resolved_source_identity: SourceFileIdentity | None = None
    export_mode: str = "standalone"
    preserve_source_track_identities: frozenset[tuple[int, int]] = frozenset()
    raw_quaternion_source_identities: frozenset[tuple[int, int]] = frozenset()
    replacement_timl_payloads: dict[int, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ExportAnalysis:
    action: object | None = None
    sampling_result: object | None = None
    reconstructed: object | None = None
    plan: object | None = None
    metadata: ExportSourceMetadata = field(default_factory=ExportSourceMetadata)
    impact_summary: ExportImpactSummary = field(default_factory=ExportImpactSummary)
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


def _safe_action_get(action, key: str, default=None):
    getter = getattr(action, "get", None)
    if callable(getter):
        return getter(key, default)
    if isinstance(action, dict):
        return action.get(key, default)
    return default


def _safe_action_import_kind(action) -> str:
    return str(_safe_action_get(action, "mhw_anim_tools_import_kind", "") or "")


def _imported_lmt_action_requires_source(action) -> bool:
    return _safe_action_import_kind(action) == "lmt_action"


def _source_identity_mismatch_message(
    source_path: str,
    imported_identity: SourceFileIdentity,
    resolved_identity: SourceFileIdentity,
) -> str:
    return (
        f"Source LMT '{source_path}' has changed since import. "
        f"Imported size/hash was {imported_identity.size} bytes / {imported_identity.sha256}, "
        f"current size/hash is {resolved_identity.size} bytes / {resolved_identity.sha256}. "
        "Re-inspect and re-import before exporting."
    )


def _safe_action_source_lmt(action) -> str:
    return str(_safe_action_get(action, "mhw_anim_tools_source_lmt", "") or "")


def _safe_action_entry_id(action, default: int = 0) -> int:
    try:
        return int(_safe_action_get(action, "mhw_anim_tools_entry_id", default))
    except (TypeError, ValueError):
        return default


def _workflow_diagnostic(level: str, source: str, message: str) -> ExportWorkflowDiagnostic:
    return ExportWorkflowDiagnostic(level=level.upper(), source=source, message=message)


def _report_diagnostics(report: Report) -> list[ExportWorkflowDiagnostic]:
    return [
        _workflow_diagnostic(diagnostic.level, diagnostic.code, diagnostic.message)
        for diagnostic in report.diagnostics
    ]


def _has_report_error(report: Report, code: str) -> bool:
    return any(
        str(getattr(diagnostic, "code", "") or "") == str(code)
        and str(getattr(diagnostic, "level", "") or "").lower() == "error"
        for diagnostic in report.diagnostics
    )


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
        track_metadata_by_index={},
    )


def _standalone_metadata_from_context(
    fallback_context: LmtSourceActionExportContext | None,
    *,
    report: Report,
    imported_source_identity: SourceFileIdentity | None = None,
) -> ExportSourceMetadata:
    fallback_report = assess_standalone_export_context(fallback_context)
    report.diagnostics.extend(fallback_report.diagnostics)
    if fallback_context is None:
        return ExportSourceMetadata(imported_source_identity=imported_source_identity)
    return ExportSourceMetadata(
        version=fallback_context.version,
        action_id=fallback_context.action_id,
        track_metadata_by_identity=fallback_context.track_metadata_by_identity,
        track_metadata_by_index=fallback_context.track_metadata_by_index,
        source_context=fallback_context,
        imported_source_identity=imported_source_identity,
        export_mode="standalone",
    )


def resolve_source_action_export_metadata(
    scene_props,
    action,
    *,
    source_cache: dict[str, tuple[bytes, object]] | None = None,
) -> tuple[ExportSourceMetadata, Report]:
    metadata = _default_export_metadata()
    report = Report()
    source_path = ""
    entry_id = 0
    fallback_context = _fallback_source_context_from_action(action)
    imported_source_identity = load_source_file_identity(action) if action is not None else None
    source_required = _imported_lmt_action_requires_source(action)
    if action is not None:
        source_path = str(action.get("mhw_anim_tools_source_lmt", ""))
        try:
            entry_id = int(action.get("mhw_anim_tools_entry_id", 0))
        except (TypeError, ValueError):
            if source_required:
                report.add_error(
                    "lmt.export.source_entry",
                    (
                        f"Imported LMT action '{getattr(action, 'name', '')}' has invalid source entry metadata. "
                        "Re-inspect and re-import before exporting."
                    ),
                )
                return _standalone_metadata_from_context(
                    fallback_context,
                    report=report,
                    imported_source_identity=imported_source_identity,
                ), report
            report.add_warning(
                "lmt.export.source_entry",
                f"Action '{action.name}' has invalid source entry metadata; exporting with entry 0 defaults.",
            )
            entry_id = 0
    if not source_required and not source_path and scene_props.last_lmt_path:
        source_path = scene_props.last_lmt_path
        if scene_props.lmt_entries and 0 <= scene_props.selected_entry_index < len(scene_props.lmt_entries):
            entry_id = int(scene_props.lmt_entries[scene_props.selected_entry_index].entry_id)

    if not source_path:
        if source_required:
            report.add_error(
                "lmt.export.source_path",
                "Imported LMT action is missing its source path metadata. Re-inspect and re-import before exporting.",
            )
            return _standalone_metadata_from_context(
                fallback_context,
                report=report,
                imported_source_identity=imported_source_identity,
            ), report
        if fallback_context is not None:
            report.add_warning(
                "lmt.export.source_path",
                "Source LMT path is unavailable; exporting with cached container metadata and default track metadata.",
            )
        return _standalone_metadata_from_context(
            fallback_context,
            report=report,
            imported_source_identity=imported_source_identity,
        ), report

    if source_required and imported_source_identity is None:
        report.add_error(
            "lmt.export.source_identity",
            (
                f"Imported LMT action '{getattr(action, 'name', '')}' is missing source identity metadata. "
                "Re-inspect and re-import before exporting."
            ),
        )

    try:
        cached_source = source_cache.get(source_path) if source_cache is not None else None
        if cached_source is None:
            source_bytes = Path(source_path).read_bytes()
            lmt = read_lmt_bytes(source_bytes, source_name=source_path)
            if source_cache is not None:
                source_cache[source_path] = (source_bytes, lmt)
        else:
            source_bytes, lmt = cached_source
    except (OSError, ValueError, TypeError, BinaryFormatError) as exc:
        if source_required:
            report.add_error(
                "lmt.export.source_read",
                f"Could not read the imported source LMT '{source_path}'. Re-inspect and re-import before exporting ({exc}).",
            )
            return _standalone_metadata_from_context(
                fallback_context,
                report=report,
                imported_source_identity=imported_source_identity,
            ), report
        report.add_warning(
            "lmt.export.source_read",
            f"Could not reuse source LMT metadata from '{source_path}'; exporting with defaults instead ({exc}).",
        )
        return _standalone_metadata_from_context(
            fallback_context,
            report=report,
            imported_source_identity=imported_source_identity,
        ), report

    resolved_source_identity = source_file_identity_from_bytes(source_bytes)
    if imported_source_identity is not None and resolved_source_identity != imported_source_identity:
        report.add_error(
            "lmt.export.source_identity",
            _source_identity_mismatch_message(source_path, imported_source_identity, resolved_source_identity),
        )

    try:
        source_context = build_source_action_export_context(lmt, entry_id)
    except ValueError:
        if source_required:
            report.add_error(
                "lmt.export.source_entry",
                f"Could not find imported source entry {entry_id} in '{source_path}'. Re-inspect and re-import before exporting.",
            )
            return _standalone_metadata_from_context(
                fallback_context,
                report=report,
                imported_source_identity=imported_source_identity,
            ), report
        report.add_warning(
            "lmt.export.source_entry",
            f"Could not find source LMT entry {entry_id} in '{source_path}'; exporting with default metadata.",
        )
        return _standalone_metadata_from_context(
            fallback_context,
            report=report,
            imported_source_identity=imported_source_identity,
        ), report

    metadata = ExportSourceMetadata(
        version=source_context.version,
        header_unknown=source_context.header_unknown,
        action_id=source_context.action_id,
        loop_frame=source_context.loop_frame,
        flags=source_context.flags,
        flags2=source_context.flags2,
        track_metadata_by_identity=source_context.track_metadata_by_identity,
        track_metadata_by_index=source_context.track_metadata_by_index,
        source_context=source_context,
        source_lmt=lmt,
        source_bytes=source_bytes,
        imported_source_identity=imported_source_identity,
        resolved_source_identity=resolved_source_identity,
        export_mode="merge",
    )
    if source_context.duplicate_track_identities:
        import_track_bindings = load_lmt_import_track_bindings(action)
        if not bindings_cover_duplicate_identities(import_track_bindings, source_context.duplicate_track_identities):
            duplicate_labels = ", ".join(
                f"bone_id={bone_id}, usage={usage}, count={count}"
                for bone_id, usage, count in source_context.duplicate_track_identities
            )
            report.add_error(
                "lmt.export.track_identity",
                (
                    "Source action contains duplicate raw track identities, but this imported Blender action does not "
                    f"carry the required per-track raw-slot bindings yet: {duplicate_labels}. Re-import the action "
                    "to refresh its raw duplicate-slot bindings."
                ),
            )
    return metadata, report


def source_export_actions(scene_props, *, actions, action=None) -> tuple[str, tuple[object, ...], Report]:
    report = Report()
    anchor_action = action if action is not None else effective_export_action(scene_props)
    if anchor_action is None:
        report.add_error(
            "lmt.export.source_action",
            "Choose an imported LMT action before exporting the full source file.",
        )
        return "", (), report

    import_kind = _safe_action_import_kind(anchor_action)
    if import_kind != "lmt_action":
        report.add_error(
            "lmt.export.source_action",
            (
                f"Action '{getattr(anchor_action, 'name', '')}' is not an imported LMT action. "
                "Full source export requires a source-backed LMT action, not a TIML controller or standalone action."
            ),
        )
        return "", (), report

    source_path = _safe_action_source_lmt(anchor_action) or str(scene_props.last_lmt_path or "")
    if not source_path:
        report.add_error(
            "lmt.export.source_path",
            "Selected imported LMT action is missing its source file path, so full-source export cannot continue.",
        )
        return "", (), report

    source_actions_by_id: dict[int, object] = {}
    duplicate_ids: set[int] = set()
    invalid_actions: list[str] = []
    for candidate in actions:
        if _safe_action_import_kind(candidate) != "lmt_action":
            continue
        if _safe_action_source_lmt(candidate) != source_path:
            continue
        entry_id = _safe_action_entry_id(candidate, default=-1)
        if entry_id < 0:
            invalid_actions.append(str(getattr(candidate, "name", "") or "<unnamed action>"))
            continue
        if entry_id in source_actions_by_id:
            duplicate_ids.add(entry_id)
            continue
        source_actions_by_id[entry_id] = candidate

    if invalid_actions:
        invalid_labels = ", ".join(invalid_actions)
        report.add_error(
            "lmt.export.source_entry",
            f"Imported LMT action metadata is missing a valid source entry id for: {invalid_labels}.",
        )
    if duplicate_ids:
        duplicate_labels = ", ".join(f"{entry_id:03d}" for entry_id in sorted(duplicate_ids))
        report.add_error(
            "lmt.export.source_entry",
            (
                "Found multiple imported Blender actions mapped to the same source LMT entry id(s): "
                f"{duplicate_labels}."
            ),
        )

    ordered_actions = tuple(candidate for _entry_id, candidate in sorted(source_actions_by_id.items()))
    if not ordered_actions:
        report.add_error(
            "lmt.export.source_action",
            f"No imported LMT actions from '{source_path}' are available for full-source export.",
        )
    return source_path, ordered_actions, report


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
        if metadata.source_context is not None and metadata.source_context.duplicate_track_identities:
            preserve_source_track_identities = frozenset()
        else:
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
        track_metadata_by_index=metadata.track_metadata_by_index,
        source_context=metadata.source_context,
        source_lmt=metadata.source_lmt,
        source_bytes=metadata.source_bytes,
        export_mode=metadata.export_mode,
        preserve_source_track_identities=frozenset(preserve_source_track_identities),
        raw_quaternion_source_identities=frozenset(raw_quaternion_source_identities),
        replacement_timl_payloads=replacement_timl_payloads,
    )


def analyze_action_for_export(
    scene_props,
    action,
    *,
    actions,
    objects,
    source_cache: dict[str, tuple[bytes, object]] | None = None,
) -> ExportAnalysis:
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

    metadata, metadata_report = resolve_source_action_export_metadata(
        scene_props,
        action,
        source_cache=source_cache,
    )
    if metadata_report.error_count:
        workflow_diagnostics.extend(_report_diagnostics(metadata_report))
        warning_count = sampling_result.warning_count + metadata_report.warning_count
        error_count = sampling_result.error_count + metadata_report.error_count
        impact_summary = build_export_impact_summary(action, metadata, objects)
        if _has_report_error(metadata_report, "lmt.export.track_identity"):
            status_message = (
                "Selected action is missing the raw duplicate-track slot bindings required for source-backed export."
            )
        else:
            status_message = metadata_report.diagnostics[0].message if metadata_report.diagnostics else ""
        return ExportAnalysis(
            action=action,
            sampling_result=sampling_result,
            metadata=metadata,
            impact_summary=impact_summary,
            diagnostics=tuple(workflow_diagnostics),
            warning_count=warning_count,
            error_count=error_count,
            status_message=status_message,
        )
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
        track_metadata_by_index=metadata.track_metadata_by_index,
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
    impact_summary = build_export_impact_summary(action, metadata, objects)
    return ExportAnalysis(
        action=action,
        sampling_result=sampling_result,
        reconstructed=reconstructed,
        plan=plan,
        metadata=metadata,
        impact_summary=impact_summary,
        diagnostics=tuple(workflow_diagnostics),
        warning_count=warning_count,
        error_count=error_count,
    )


def analyze_export_action(scene_props, *, actions, objects) -> ExportAnalysis:
    return analyze_action_for_export(
        scene_props,
        effective_export_action(scene_props),
        actions=actions,
        objects=objects,
    )


def analyze_source_export_actions(
    scene_props,
    *,
    actions,
    objects,
    action=None,
) -> tuple[str, tuple[ExportAnalysis, ...], Report]:
    source_path, export_actions, report = source_export_actions(
        scene_props,
        actions=actions,
        action=action,
    )
    if report.error_count:
        return source_path, (), report

    source_cache: dict[str, tuple[bytes, object]] = {}
    analyses = tuple(
        analyze_action_for_export(
            scene_props,
            export_action,
            actions=actions,
            objects=objects,
            source_cache=source_cache,
        )
        for export_action in export_actions
    )
    return source_path, analyses, report


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
            track_metadata_by_index=metadata.track_metadata_by_index,
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
        track_metadata_by_index=metadata.track_metadata_by_index,
        raw_quaternion_source_identities=metadata.raw_quaternion_source_identities,
    )


def _timl_payload_signature(raw_timl_payload) -> tuple[bytes, tuple[int, ...]]:
    return (
        bytes(getattr(raw_timl_payload, "payload", b"")),
        tuple(int(offset) for offset in getattr(raw_timl_payload, "rebase_offsets", ())),
    )


def write_source_export_file(filepath: str, analyses: tuple[ExportAnalysis, ...] | list[ExportAnalysis]):
    normalized_analyses = tuple(analyses)
    if not normalized_analyses:
        raise ValidationError("No analyzed source actions were provided for full LMT export.")

    anchor_analysis = normalized_analyses[0]
    anchor_metadata = anchor_analysis.metadata
    anchor_source_name = str(getattr(getattr(anchor_metadata, "source_context", None), "source_name", "") or "")
    if anchor_metadata.source_lmt is None or anchor_metadata.source_bytes is None or not anchor_source_name:
        raise ValidationError("Full LMT export requires source-backed imported actions with readable source metadata.")
    if (
        anchor_metadata.imported_source_identity is None
        or anchor_metadata.resolved_source_identity is None
        or anchor_metadata.imported_source_identity != anchor_metadata.resolved_source_identity
    ):
        raise ValidationError(
            "Full LMT export requires an unchanged imported source LMT. Re-inspect and re-import before exporting."
        )

    reconstructed_actions_by_id: dict[int, object] = {}
    track_metadata_by_action_id: dict[int, dict[tuple[int, int], dict[str, object]] | None] = {}
    track_metadata_by_index_by_action_id: dict[int, dict[int, dict[str, object]] | None] = {}
    preserve_source_identities_by_action_id: dict[int, frozenset[tuple[int, int]]] = {}
    raw_quaternion_source_identities_by_action_id: dict[int, frozenset[tuple[int, int]]] = {}
    replacement_timl_payloads: dict[int, object] = {}

    for analysis in normalized_analyses:
        if analysis.reconstructed is None or analysis.plan is None:
            raise ValidationError("Full LMT export analysis is incomplete; analyze each source action before writing.")
        if analysis.error_count:
            raise ValidationError(
                f"Cannot write full source LMT while action '{getattr(analysis.action, 'name', '')}' still has export errors."
            )

        metadata = analysis.metadata
        source_name = str(getattr(getattr(metadata, "source_context", None), "source_name", "") or "")
        if metadata.source_lmt is None or metadata.source_bytes is None or not source_name:
            raise ValidationError(
                f"Action '{getattr(analysis.action, 'name', '')}' is not source-backed, so it cannot participate in full LMT export."
            )
        if (
            metadata.imported_source_identity is None
            or metadata.resolved_source_identity is None
            or metadata.imported_source_identity != metadata.resolved_source_identity
        ):
            raise ValidationError(
                f"Action '{getattr(analysis.action, 'name', '')}' no longer matches its imported source LMT. Re-inspect and re-import before exporting."
            )
        if source_name != anchor_source_name:
            raise ValidationError(
                "Full LMT export can only combine Blender actions imported from the same source LMT file."
            )
        if bytes(metadata.source_bytes) != bytes(anchor_metadata.source_bytes):
            raise ValidationError(
                "Source LMT bytes changed between analyzed actions; re-run export analysis before writing the full file."
            )

        action_id = int(metadata.action_id)
        if action_id in reconstructed_actions_by_id:
            raise ValidationError(
                f"Source LMT entry {action_id:03d} was analyzed more than once for full export."
            )

        reconstructed_actions_by_id[action_id] = analysis.reconstructed
        track_metadata_by_action_id[action_id] = metadata.track_metadata_by_identity
        track_metadata_by_index_by_action_id[action_id] = metadata.track_metadata_by_index
        preserve_source_identities_by_action_id[action_id] = metadata.preserve_source_track_identities
        raw_quaternion_source_identities_by_action_id[action_id] = metadata.raw_quaternion_source_identities

        for source_offset, payload in dict(metadata.replacement_timl_payloads or {}).items():
            normalized_source_offset = int(source_offset)
            existing_payload = replacement_timl_payloads.get(normalized_source_offset)
            if existing_payload is None:
                replacement_timl_payloads[normalized_source_offset] = payload
                continue
            if _timl_payload_signature(existing_payload) != _timl_payload_signature(payload):
                raise ValidationError(
                    (
                        "Conflicting TIML writeback payloads were produced for shared source offset "
                        f"{normalized_source_offset} while exporting '{anchor_source_name}'."
                    )
                )

    return write_multi_merged_lmt_file(
        filepath,
        anchor_metadata.source_lmt,
        anchor_metadata.source_bytes,
        reconstructed_actions_by_id,
        version=anchor_metadata.version,
        header_unknown=anchor_metadata.header_unknown,
        track_metadata_by_action_id=track_metadata_by_action_id,
        track_metadata_by_index_by_action_id=track_metadata_by_index_by_action_id,
        preserve_source_identities_by_action_id=preserve_source_identities_by_action_id,
        raw_quaternion_source_identities_by_action_id=raw_quaternion_source_identities_by_action_id,
        replacement_timl_payloads=replacement_timl_payloads,
    )
