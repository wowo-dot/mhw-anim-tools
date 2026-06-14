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


TIML_EDIT_POLICY_LABELS = {
    "value_only": "Value Only",
    "rebuild_capable": "Rebuild OK",
    "blocked": "Blocked",
}


TIML_EDIT_POLICY_ICONS = {
    "value_only": "LOCKED",
    "rebuild_capable": "KEYFRAMES",
    "blocked": "ERROR",
}


def timl_writeback_status_label(status: str) -> str:
    return TIML_WRITEBACK_STATUS_LABELS.get(str(status or ""), "")


def timl_writeback_status_icon(status: str) -> str:
    return TIML_WRITEBACK_STATUS_ICONS.get(str(status or ""), "INFO")


def timl_edit_policy_code(*, source_advanced: bool = False, status: str = "", reason: str = "") -> str:
    status = str(status or "")
    reason = str(reason or "")
    if status == "unsupported_rebuild" and reason.endswith("_mismatch"):
        return "blocked"
    return "value_only" if source_advanced else "rebuild_capable"


def timl_edit_policy_label(policy: str) -> str:
    return TIML_EDIT_POLICY_LABELS.get(str(policy or ""), "")


def timl_edit_policy_icon(policy: str) -> str:
    return TIML_EDIT_POLICY_ICONS.get(str(policy or ""), "INFO")


def timl_edit_policy_reason_label(policy: str) -> str:
    policy = str(policy or "")
    if policy == "value_only":
        return (
            "This transform comes from source-only easing/interpolation semantics, "
            "so structural edits stay blocked and value-only edits remain safe."
        )
    if policy == "rebuild_capable":
        return (
            "This transform uses simple source semantics, so structural edits can "
            "be rebuilt from Blender preview keys when needed."
        )
    if policy == "blocked":
        return (
            "This controller no longer matches the imported source transform "
            "metadata, so writeback is blocked until it is reimported."
        )
    return ""


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
        if reason == "advanced_source_rebuild":
            return "This transform uses source-only easing/interpolation semantics, so structural edits are blocked for now. Value-only edits remain safe."
        return "This transform needs a structural rebuild, but current preview interpolation is unsupported. Use CONSTANT or LINEAR for now."
    return ""


def count_timl_edit_policies(policies) -> dict[str, int]:
    counts = {key: 0 for key in TIML_EDIT_POLICY_LABELS}
    for policy in policies:
        key = str(policy or "")
        if key in counts:
            counts[key] += 1
    return counts


def timl_payload_scope_label(action_ids) -> str:
    normalized = tuple(sorted({int(action_id) for action_id in action_ids}))
    if not normalized:
        return ""
    labels = ", ".join(f"{action_id:03d}" for action_id in normalized)
    if len(normalized) == 1:
        return f"Unique to source action {labels}"
    return f"Shared by source actions {labels}"


def count_timl_writeback_statuses(statuses) -> dict[str, int]:
    counts = {key: 0 for key in TIML_WRITEBACK_STATUS_LABELS}
    for status in statuses:
        key = str(status or "")
        if key in counts:
            counts[key] += 1
    return counts
