"""Helpers for imported LMT track metadata and raw duplicate-slot bindings."""

from __future__ import annotations

import json
from pathlib import Path
import re

try:
    from ..core.formats.lmt.semantics import get_usage_semantics
except ImportError:  # pragma: no cover - test runner imports from addon root
    from core.formats.lmt.semantics import get_usage_semantics


LMT_IMPORT_TRACK_BINDINGS_KEY = "mhw_anim_tools_lmt_import_track_bindings"
LMT_ARMATURE_IMPORT_MODE = "armature"
LMT_RAW_DUPLICATE_IMPORT_MODE = "raw_duplicate"
LMT_RAW_DUPLICATE_OWNER_OBJECT = "object"
LMT_RAW_DUPLICATE_OWNER_BONE = "bone"
QUATERNION_LERP_BUFFER_TYPES = frozenset({7, 11, 12, 13, 14, 15})

_SOURCE_TAG_PATTERN = re.compile(r"[^0-9A-Za-z]+")


def _safe_get(owner, key: str, default=None):
    getter = getattr(owner, "get", None)
    if callable(getter):
        return getter(key, default)
    if isinstance(owner, dict):
        return owner.get(key, default)
    return default


def _source_tag_for_path(source_path: str) -> str:
    stem = Path(str(source_path or "")).stem or "lmt"
    tag = _SOURCE_TAG_PATTERN.sub("_", stem).strip("_").lower()
    tag = tag[:24].strip("_")
    return tag or "lmt"


def track_display_name(*, bone_id: int, usage: int, track_index: int | None = None) -> str:
    usage_info = get_usage_semantics(int(usage))
    if usage_info.scope == "root":
        target_label = "Root"
    else:
        target_label = f"Bone {int(bone_id)}"
    transform_label = str(usage_info.transform or "value").title()
    if track_index is None:
        return f"{target_label} {transform_label}"
    return f"T{int(track_index):02d} {target_label} {transform_label}"


def raw_duplicate_display_name(*, bone_id: int, usage: int, track_index: int) -> str:
    return f"Raw Duplicate {track_display_name(bone_id=bone_id, usage=usage, track_index=track_index)}"


def raw_duplicate_action_group(*, bone_id: int, usage: int, track_index: int) -> str:
    return f"LMT Raw / {track_display_name(bone_id=bone_id, usage=usage, track_index=track_index)}"


def raw_duplicate_data_path(*, property_name: str, owner_kind: str = "", owner_name: str = "") -> str:
    if str(owner_kind or "") == LMT_RAW_DUPLICATE_OWNER_BONE and str(owner_name or ""):
        return f'pose.bones["{owner_name}"]["{property_name}"]'
    return f'["{property_name}"]'


def raw_duplicate_group_name(
    *,
    bone_id: int,
    usage: int,
    track_index: int,
    owner_kind: str = "",
    owner_name: str = "",
    action_group: str = "",
) -> str:
    if str(owner_kind or "") == LMT_RAW_DUPLICATE_OWNER_BONE:
        base_name = str(action_group or owner_name or "")
        if base_name:
            return f"{base_name} / LMT Raw"
    if str(owner_kind or "") == LMT_RAW_DUPLICATE_OWNER_OBJECT and (int(usage) >= 3 or int(bone_id) == -1):
        base_name = str(action_group or "Root Motion")
        return f"{base_name} / LMT Raw"
    if str(action_group or ""):
        return f"{action_group} / LMT Raw"
    return raw_duplicate_action_group(bone_id=bone_id, usage=usage, track_index=track_index)


def raw_duplicate_property_name(
    *,
    source_path: str,
    action_id: int,
    track_index: int,
    bone_id: int,
    usage: int,
) -> str:
    source_tag = _source_tag_for_path(source_path)
    return (
        f"lmt_raw_{source_tag}_a{int(action_id):03d}_"
        f"t{int(track_index):02d}_b{int(bone_id)}_u{int(usage)}"
    )


def _binding_from_raw(binding) -> dict[str, object] | None:
    if not isinstance(binding, dict):
        return None
    try:
        normalized = {
            "track_index": int(binding.get("track_index", 0)),
            "bone_id": int(binding.get("bone_id", 0)),
            "usage": int(binding.get("usage", 0)),
            "buffer_type": int(binding.get("buffer_type", 0)),
            "import_mode": str(binding.get("import_mode", "") or ""),
            "source_kind": str(binding.get("source_kind", "") or ""),
            "source_name": str(binding.get("source_name", "") or ""),
            "transform": str(binding.get("transform", "") or ""),
            "property_name": str(binding.get("property_name", "") or ""),
            "channel_count": int(binding.get("channel_count", 0) or 0),
            "display_name": str(binding.get("display_name", "") or ""),
            "action_group": str(binding.get("action_group", "") or ""),
            "owner_kind": str(binding.get("owner_kind", "") or ""),
            "owner_name": str(binding.get("owner_name", "") or ""),
            "data_path": str(binding.get("data_path", "") or ""),
            "preserve_raw_quaternion_values": bool(binding.get("preserve_raw_quaternion_values", False)),
        }
    except (TypeError, ValueError):
        return None
    if not normalized["display_name"]:
        if normalized["import_mode"] == LMT_RAW_DUPLICATE_IMPORT_MODE:
            normalized["display_name"] = raw_duplicate_display_name(
                bone_id=normalized["bone_id"],
                usage=normalized["usage"],
                track_index=normalized["track_index"],
            )
        else:
            normalized["display_name"] = track_display_name(
                bone_id=normalized["bone_id"],
                usage=normalized["usage"],
                track_index=normalized["track_index"],
            )
    if normalized["import_mode"] == LMT_RAW_DUPLICATE_IMPORT_MODE:
        if not normalized["action_group"]:
            normalized["action_group"] = raw_duplicate_group_name(
                bone_id=normalized["bone_id"],
                usage=normalized["usage"],
                track_index=normalized["track_index"],
                owner_kind=normalized["owner_kind"],
                owner_name=normalized["owner_name"],
            )
        if not normalized["data_path"] and normalized["property_name"]:
            normalized["data_path"] = raw_duplicate_data_path(
                property_name=normalized["property_name"],
                owner_kind=normalized["owner_kind"],
                owner_name=normalized["owner_name"],
            )
    return normalized


def _binding_property_path(binding: dict[str, object]) -> str:
    data_path = str(binding.get("data_path", "") or "")
    if data_path:
        return data_path
    property_name = str(binding.get("property_name", "") or "")
    if not property_name:
        return ""
    return raw_duplicate_data_path(
        property_name=property_name,
        owner_kind=str(binding.get("owner_kind", "") or ""),
        owner_name=str(binding.get("owner_name", "") or ""),
    )


def raw_duplicate_binding_by_data_path(action) -> dict[str, dict[str, object]]:
    bindings = load_lmt_import_track_bindings(action)
    result: dict[str, dict[str, object]] = {}
    for binding in bindings:
        if binding.get("import_mode") != LMT_RAW_DUPLICATE_IMPORT_MODE:
            continue
        data_path = _binding_property_path(binding)
        if not data_path:
            continue
        result[data_path] = binding
    return result


def ensure_raw_duplicate_property(target_object, binding: dict[str, object], *, basis_value) -> None:
    property_name = str(binding.get("property_name", "") or "")
    values = tuple(float(component) for component in tuple(basis_value or ()))
    if not property_name:
        return
    if len(values) == 1:
        target_object[property_name] = float(values[0])
    else:
        target_object[property_name] = [float(component) for component in values]
    id_properties_ui = getattr(target_object, "id_properties_ui", None)
    if callable(id_properties_ui):
        try:
            id_properties_ui(property_name).update(
                description=str(binding.get("display_name", "") or property_name),
            )
        except Exception:  # pragma: no cover - Blender UI metadata only
            pass


def save_lmt_import_track_bindings(action, bindings) -> None:
    encoded = json.dumps(list(bindings or ()), separators=(",", ":"))
    action[LMT_IMPORT_TRACK_BINDINGS_KEY] = encoded


def clear_lmt_import_track_bindings(action) -> None:
    if LMT_IMPORT_TRACK_BINDINGS_KEY in action:
        del action[LMT_IMPORT_TRACK_BINDINGS_KEY]


def load_lmt_import_track_bindings(action) -> list[dict[str, object]]:
    raw_value = _safe_get(action, LMT_IMPORT_TRACK_BINDINGS_KEY, "")
    if not isinstance(raw_value, str) or not raw_value:
        return []
    try:
        decoded = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    normalized: list[dict[str, object]] = []
    for item in decoded:
        binding = _binding_from_raw(item)
        if binding is not None:
            normalized.append(binding)
    return normalized


def import_track_binding_by_identity(action) -> dict[tuple[int, int], dict[str, object]]:
    bindings = load_lmt_import_track_bindings(action)
    counts: dict[tuple[int, int], int] = {}
    for binding in bindings:
        identity = (int(binding["bone_id"]), int(binding["usage"]))
        counts[identity] = int(counts.get(identity, 0)) + 1
    by_identity: dict[tuple[int, int], dict[str, object]] = {}
    for binding in bindings:
        identity = (int(binding["bone_id"]), int(binding["usage"]))
        if counts.get(identity, 0) != 1:
            continue
        by_identity[identity] = binding
    return by_identity


def bindings_cover_duplicate_identities(bindings, duplicate_track_identities) -> bool:
    binding_counts: dict[tuple[int, int], int] = {}
    for binding in bindings or ():
        identity = (int(binding.get("bone_id", 0)), int(binding.get("usage", 0)))
        binding_counts[identity] = int(binding_counts.get(identity, 0)) + 1
    for bone_id, usage, expected_count in duplicate_track_identities or ():
        if int(binding_counts.get((int(bone_id), int(usage)), 0)) != int(expected_count):
            return False
    return True
