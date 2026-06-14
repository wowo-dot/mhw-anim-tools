"""Stable TIML UI labels and short writeback explanations."""

from __future__ import annotations


TIML_WRITEBACK_STATUS_LABELS = {
    "preserve_raw": "Preserve Raw",
    "patch_source_values": "Patch Values",
    "rewrite_preview": "Rebuild Preview",
    "unsupported_rebuild": "Blocked",
}


TIML_WRITEBACK_STATUS_ICONS = {
    "preserve_raw": "LOCKED",
    "patch_source_values": "GREASEPENCIL",
    "rewrite_preview": "FILE_REFRESH",
    "unsupported_rebuild": "ERROR",
}


def timl_writeback_status_label(status: str) -> str:
    return TIML_WRITEBACK_STATUS_LABELS.get(str(status or ""), "")


def timl_writeback_status_icon(status: str) -> str:
    return TIML_WRITEBACK_STATUS_ICONS.get(str(status or ""), "INFO")


def timl_writeback_reason_label(status: str, *, reason: str = "", source_advanced: bool = False) -> str:
    status = str(status or "")
    reason = str(reason or "")
    if status == "preserve_raw":
        if reason == "missing_sampled_transform":
            return "The sampled controller no longer exposes this transform, so export will keep the original source payload."
        if source_advanced:
            return "The transform is unchanged, so export will keep the original source interpolation and easing data."
        return "The transform is unchanged, so export will keep the original source bytes."
    if status == "patch_source_values":
        if source_advanced:
            return "Export will patch edited values into the original source curve structure and preserve advanced easing/interpolation."
        return "Export will patch edited values into the original source curve structure."
    if status == "rewrite_preview":
        if source_advanced:
            return "Preview structure changed, so export must rebuild this transform from Blender keys and cannot preserve source-only easing details."
        return "Preview structure changed, so export will rebuild this transform from the current Blender keys."
    if status == "unsupported_rebuild":
        if reason.endswith("_mismatch"):
            return "Controller binding metadata no longer matches the imported TIML source transform, so export is blocked."
        return "This transform needs a structural rebuild, but current preview interpolation is unsupported. Use CONSTANT or LINEAR for now."
    return ""


def count_timl_writeback_statuses(statuses) -> dict[str, int]:
    counts = {key: 0 for key in TIML_WRITEBACK_STATUS_LABELS}
    for status in statuses:
        key = str(status or "")
        if key in counts:
            counts[key] += 1
    return counts
