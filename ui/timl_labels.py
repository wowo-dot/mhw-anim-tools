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
    "rebuild_capable": "KEYFRAME",
    "blocked": "ERROR",
}


def timl_writeback_status_label(status: str) -> str:
    return TIML_WRITEBACK_STATUS_LABELS.get(str(status or ""), "")


def timl_writeback_status_icon(status: str) -> str:
    return TIML_WRITEBACK_STATUS_ICONS.get(str(status or ""), "INFO")


def timl_edit_policy_code(*, source_advanced: bool = False, status: str = "", reason: str = "") -> str:
    status = str(status or "")
    reason = str(reason or "")
    if status == "preserve_raw" and reason == "missing_sampled_transform":
        return "blocked"
    if status == "unsupported_rebuild" and (
        reason.endswith("_mismatch")
        or reason in {
            "extra_sampled_transform",
            "deleted_source_transform",
            "type_index_layout",
            "transform_index_layout",
        }
    ):
        return "blocked"
    return "value_only" if source_advanced else "rebuild_capable"


def timl_edit_policy_label(policy: str) -> str:
    return TIML_EDIT_POLICY_LABELS.get(str(policy or ""), "")


def timl_edit_policy_icon(policy: str) -> str:
    return TIML_EDIT_POLICY_ICONS.get(str(policy or ""), "INFO")


def timl_edit_policy_reason_label(policy: str, *, reason: str = "") -> str:
    policy = str(policy or "")
    reason = str(reason or "")
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
        if reason == "missing_sampled_transform":
            return (
                "This source transform no longer has a sampled preview binding, "
                "so raw source data will be preserved until the preview binding is recreated."
            )
        if reason == "extra_sampled_transform":
            return (
                "This transform was added in Blender, but the surrounding raw TIML "
                "layout still needs to be made contiguous before export can rebuild it safely."
            )
        if reason == "deleted_source_transform":
            return (
                "This source transform is explicitly marked for deletion, but the "
                "remaining raw TIML layout is still not contiguous enough to rebuild safely."
            )
        if reason in {"type_index_layout", "transform_index_layout"}:
            return (
                "The current raw TIML layout has index gaps or collisions. Reindex the "
                "remaining types/transforms into one contiguous layout before exporting."
            )
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
        if reason == "extra_sampled_transform":
            return "This added transform is fine in principle, but export is blocked until the final raw TIML indices are contiguous."
        if reason == "deleted_source_transform":
            return "This source transform is marked for deletion, but export is blocked until the final raw TIML indices are contiguous."
        if reason == "type_index_layout":
            return "Type indices are not contiguous from 00 in the final raw TIML layout, so export is blocked until they are reindexed."
        if reason == "transform_index_layout":
            return "Transform indices are not contiguous inside one or more TIML types, so export is blocked until they are reindexed."
        if reason == "advanced_source_rebuild":
            return "This transform uses source-only easing/interpolation semantics, so structural edits are blocked for now. Value-only edits remain safe."
        if reason == "integer_off_grid":
            return "This integer transform currently uses non-integral preview values and would need lossy quantization, so export is blocked until the keys are set to exact whole-number values."
        if reason == "integer_precision_risk":
            return "This integer transform exceeds exact Blender float precision, so export is blocked until the keys are re-entered as safe whole-number values."
        if reason == "integer_range":
            return "This integer transform is outside the writable TIML integer range, so export is blocked until the values are brought back into range."
        if reason == "boolean_off_grid":
            return "This boolean transform currently uses preview values other than 0 or 1, so export is blocked until the keys are made explicitly boolean."
        if reason == "color_range":
            return "This color transform currently goes outside the writable preview range, so export is blocked until the keys are brought back into the 0..1 color range."
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
