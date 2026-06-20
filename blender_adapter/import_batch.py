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
    entry_ids=None,
    source_identity=None,
):
    """Import one or more LMT actions through the single-action importer callback."""

    result = ImportActionBatchResult()
    if lmt is None:
        result.add("ERROR", "session", "No parsed LMT file is available for batch import.")
        return result

    if entry_ids is None:
        requested_ids = [int(getattr(action, "id", 0)) for action in getattr(lmt, "actions", ())]
    else:
        requested_ids = [int(entry_id) for entry_id in entry_ids]

    result.requested_action_count = len(requested_ids)
    if not requested_ids:
        result.add("ERROR", "session", "The current LMT file contains no actions to import.")
        return result

    actions_by_id = {
        int(getattr(action, "id", -1)): action
        for action in getattr(lmt, "actions", ())
    }
    imported_action_names: list[str] = []
    for entry_id in requested_ids:
        source_action = actions_by_id.get(int(entry_id))
        if source_action is None:
            result.failed_action_count += 1
            result.add(
                "ERROR",
                "session",
                f"Requested LMT entry {int(entry_id):03d} is not present in the current source file.",
            )
            continue

        single_result = import_action(
            lmt,
            int(entry_id),
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
                _prefixed_source(int(entry_id), getattr(diagnostic, "source", "")),
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
