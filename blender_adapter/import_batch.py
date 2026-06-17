"""Batch workflow helpers for importing multiple LMT actions."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field


@dataclass(frozen=True)
class BatchImportDiagnostic:
    level: str
    source: str
    message: str


@dataclass
class ImportActionBatchResult:
    requested_action_count: int = 0
    imported_action_count: int = 0
    failed_action_count: int = 0
    imported_track_count: int = 0
    skipped_track_count: int = 0
    created_fcurve_count: int = 0
    frame_end: int = 0
    imported_action_names: tuple[str, ...] = ()
    diagnostics: list[BatchImportDiagnostic] = field(default_factory=list)

    def add(self, level: str, source: str, message: str):
        self.diagnostics.append(BatchImportDiagnostic(level=level, source=source, message=message))

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "WARNING")

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "ERROR")


def _prefixed_source(action_id: int, source: str) -> str:
    prefix = f"entry {int(action_id):03d}"
    source = str(source or "")
    return prefix if not source else f"{prefix} / {source}"


def import_all_lmt_actions_to_armature(
    lmt,
    armature_object,
    *,
    source_path: str,
    import_action,
    entry_indices=None,
    source_identity=None,
):
    """Import one or more LMT actions through the single-action importer callback."""

    result = ImportActionBatchResult()
    if lmt is None:
        result.add("ERROR", "session", "No parsed LMT file is available for batch import.")
        return result

    if entry_indices is None:
        requested_indices = list(range(len(getattr(lmt, "actions", ()))))
    else:
        requested_indices = [int(index) for index in entry_indices]

    result.requested_action_count = len(requested_indices)
    if not requested_indices:
        result.add("ERROR", "session", "The current LMT file contains no actions to import.")
        return result

    imported_action_names: list[str] = []
    for action_index in requested_indices:
        if action_index < 0 or action_index >= len(lmt.actions):
            result.failed_action_count += 1
            result.add(
                "ERROR",
                "session",
                f"Requested LMT action index {action_index} is out of range for batch import.",
            )
            continue

        action_id = int(lmt.actions[action_index].id)
        single_result = import_action(
            lmt,
            action_index,
            armature_object,
            source_path=source_path,
            source_identity=source_identity,
        )
        result.imported_track_count += int(getattr(single_result, "imported_track_count", 0))
        result.skipped_track_count += int(getattr(single_result, "skipped_track_count", 0))
        result.created_fcurve_count += int(getattr(single_result, "created_fcurve_count", 0))
        result.frame_end = max(result.frame_end, int(getattr(single_result, "frame_end", 0) or 0))

        action_name = str(getattr(single_result, "action_name", "") or "")
        if action_name:
            imported_action_names.append(action_name)

        for diagnostic in getattr(single_result, "diagnostics", ()):
            result.add(
                str(getattr(diagnostic, "level", "INFO") or "INFO"),
                _prefixed_source(action_id, getattr(diagnostic, "source", "")),
                str(getattr(diagnostic, "message", "") or ""),
            )

        if int(getattr(single_result, "error_count", 0) or 0):
            result.failed_action_count += 1
        else:
            result.imported_action_count += 1

    result.imported_action_names = tuple(imported_action_names)
    if result.imported_action_count == 0 and not result.error_count:
        result.add("ERROR", "import.batch", "No LMT actions were imported successfully.")
    return result
