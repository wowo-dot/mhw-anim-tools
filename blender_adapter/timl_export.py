"""TIML-related export readiness checks for Blender action metadata."""

from __future__ import annotations

from dataclasses import dataclass

try:
    from ..core.diagnostics.reports import Report
except ImportError:  # pragma: no cover - test runner imports from addon root
    from core.diagnostics.reports import Report


@dataclass(frozen=True)
class ActionTimlMetadata:
    name: str
    import_kind: str
    source_lmt: str
    entry_id: int
    source_timl_offset: int
    source_has_timl: bool


def _safe_get(action_like, key: str, default=None):
    getter = getattr(action_like, "get", None)
    if callable(getter):
        return getter(key, default)
    if isinstance(action_like, dict):
        return action_like.get(key, default)
    return default


def _safe_keys(action_like):
    keys = getattr(action_like, "keys", None)
    if callable(keys):
        try:
            return list(keys())
        except TypeError:
            return []
    if isinstance(action_like, dict):
        return list(action_like.keys())
    return []


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def extract_action_timl_metadata(action_like) -> ActionTimlMetadata:
    name = str(getattr(action_like, "name", _safe_get(action_like, "name", "")) or "")
    return ActionTimlMetadata(
        name=name,
        import_kind=str(_safe_get(action_like, "mhw_anim_tools_import_kind", "")),
        source_lmt=str(_safe_get(action_like, "mhw_anim_tools_source_lmt", "")),
        entry_id=_safe_int(_safe_get(action_like, "mhw_anim_tools_entry_id", 0), 0),
        source_timl_offset=_safe_int(_safe_get(action_like, "mhw_anim_tools_source_timl_offset", 0), 0),
        source_has_timl=bool(_safe_get(action_like, "mhw_anim_tools_source_has_timl", False)),
    )


def assess_timl_export_readiness(action_like, candidate_actions) -> Report:
    """Report whether the selected Blender action is safe for current LMT export.

    Current policy:
    - standalone TIML controller actions cannot be exported back yet
    """

    report = Report()
    metadata = extract_action_timl_metadata(action_like)
    if metadata.import_kind == "attached_timl":
        report.add_error(
            "lmt.export.timl_edit_unsupported",
            (
                f"Action '{metadata.name}' is an imported TIML controller action. "
                "Writing edited TIML controller curves back into LMT/TIML data is not implemented yet."
            ),
        )
        return report
    return report
