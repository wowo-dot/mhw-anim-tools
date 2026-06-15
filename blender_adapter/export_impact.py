"""Summarize user-visible source impact for LMT export analysis."""

from __future__ import annotations

from dataclasses import dataclass

try:
    from .timl_export import extract_action_timl_metadata
    from .timl_writeback import matching_timl_controllers_for_export_action
    from .timl_writeback import shared_source_action_ids
except ImportError:  # pragma: no cover - test runner imports from addon root
    from blender_adapter.timl_export import extract_action_timl_metadata
    from blender_adapter.timl_writeback import matching_timl_controllers_for_export_action
    from blender_adapter.timl_writeback import shared_source_action_ids


def _source_action_scope_label(action_ids) -> str:
    normalized = tuple(sorted({int(action_id) for action_id in action_ids}))
    if not normalized:
        return ""
    labels = ", ".join(f"{action_id:03d}" for action_id in normalized)
    if len(normalized) == 1:
        return f"Unique to source action {labels}"
    return f"Shared by source actions {labels}"


@dataclass(frozen=True)
class ExportImpactSummary:
    export_mode: str = "standalone"
    source_name: str = ""
    entry_id: int = 0
    source_action_count: int = 0
    preserves_siblings: bool = False
    matching_timl_controller_count: int = 0
    matching_timl_controller_names: tuple[str, ...] = ()
    timl_source_scope_label: str = ""
    timl_writeback_scope_label: str = ""


def build_export_impact_summary(action, metadata, objects) -> ExportImpactSummary:
    action_metadata = extract_action_timl_metadata(action)
    source_name = str(getattr(getattr(metadata, "source_context", None), "source_name", "") or action_metadata.source_lmt or "")
    entry_id = int(getattr(metadata, "action_id", 0) or action_metadata.entry_id or 0)
    export_mode = str(getattr(metadata, "export_mode", "standalone") or "standalone")
    source_lmt = getattr(metadata, "source_lmt", None)
    source_context = getattr(metadata, "source_context", None)
    replacement_timl_payloads = dict(getattr(metadata, "replacement_timl_payloads", {}) or {})

    if source_lmt is not None:
        source_action_count = len(getattr(source_lmt, "actions", ()))
    else:
        source_action_count = int(getattr(source_context, "action_count", 0) or 0)

    preserves_siblings = export_mode == "merge" and source_action_count > 1

    matching_controllers = tuple(matching_timl_controllers_for_export_action(action, objects)) if action is not None else ()
    matching_controller_names = tuple(
        sorted(
            {
                str(getattr(controller, "name", "") or "")
                for controller in matching_controllers
                if str(getattr(controller, "name", "") or "")
            }
        )
    )

    source_timl_offset = int(
        getattr(source_context, "timl_offset", 0)
        or action_metadata.source_timl_offset
        or 0
    )
    timl_source_scope_label = ""
    timl_writeback_scope_label = ""
    if source_lmt is not None and source_timl_offset > 0:
        source_scope_ids = shared_source_action_ids(source_lmt, source_timl_offset)
        timl_source_scope_label = _source_action_scope_label(source_scope_ids)
        if source_timl_offset in replacement_timl_payloads:
            timl_writeback_scope_label = timl_source_scope_label

    return ExportImpactSummary(
        export_mode=export_mode,
        source_name=source_name,
        entry_id=entry_id,
        source_action_count=source_action_count,
        preserves_siblings=preserves_siblings,
        matching_timl_controller_count=len(matching_controllers),
        matching_timl_controller_names=matching_controller_names,
        timl_source_scope_label=timl_source_scope_label,
        timl_writeback_scope_label=timl_writeback_scope_label,
    )
