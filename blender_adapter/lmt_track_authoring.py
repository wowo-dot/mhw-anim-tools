"""Helpers for editable LMT track authoring on imported Blender Actions."""

from __future__ import annotations

from collections import Counter
import json

try:
    from ..core.formats.lmt.semantics import get_buffer_semantics
    from ..core.formats.lmt.semantics import get_usage_semantics
    from .armature import resolve_track_binding_target
    from .export_sampling import sample_action_for_lmt_export
    from .fcurves import create_action_fcurves
    from .fcurves import create_transform_fcurves
    from .lmt_track_metadata import ensure_raw_duplicate_property
    from .lmt_track_metadata import LMT_RAW_DUPLICATE_IMPORT_MODE
    from .lmt_track_metadata import LMT_RAW_DUPLICATE_OWNER_BONE
    from .lmt_track_metadata import LMT_RAW_DUPLICATE_OWNER_OBJECT
    from .lmt_track_metadata import load_lmt_import_track_bindings
    from .lmt_track_metadata import missing_bone_raw_action_group
    from .lmt_track_metadata import missing_bone_raw_display_name
    from .lmt_track_metadata import raw_duplicate_data_path
    from .lmt_track_metadata import raw_duplicate_group_name
    from .lmt_track_metadata import raw_duplicate_property_name
    from .lmt_track_metadata import save_lmt_import_track_bindings
except ImportError:  # pragma: no cover - test runner imports from addon root
    from core.formats.lmt.semantics import get_buffer_semantics
    from core.formats.lmt.semantics import get_usage_semantics
    from blender_adapter.armature import resolve_track_binding_target
    from blender_adapter.export_sampling import sample_action_for_lmt_export
    from blender_adapter.fcurves import create_action_fcurves
    from blender_adapter.fcurves import create_transform_fcurves
    from blender_adapter.lmt_track_metadata import ensure_raw_duplicate_property
    from blender_adapter.lmt_track_metadata import LMT_RAW_DUPLICATE_IMPORT_MODE
    from blender_adapter.lmt_track_metadata import LMT_RAW_DUPLICATE_OWNER_BONE
    from blender_adapter.lmt_track_metadata import LMT_RAW_DUPLICATE_OWNER_OBJECT
    from blender_adapter.lmt_track_metadata import load_lmt_import_track_bindings
    from blender_adapter.lmt_track_metadata import missing_bone_raw_action_group
    from blender_adapter.lmt_track_metadata import missing_bone_raw_display_name
    from blender_adapter.lmt_track_metadata import raw_duplicate_data_path
    from blender_adapter.lmt_track_metadata import raw_duplicate_group_name
    from blender_adapter.lmt_track_metadata import raw_duplicate_property_name
    from blender_adapter.lmt_track_metadata import save_lmt_import_track_bindings


AUTHORED_BUFFER_TYPE = 0
AUTHORED_BUFFER_CODE = "authored"
AUTHORED_BUFFER_LABEL = "Blender-authored track"


def _safe_action_get(action, key: str, default=None):
    getter = getattr(action, "get", None)
    if callable(getter):
        return getter(key, default)
    if isinstance(action, dict):
        return action.get(key, default)
    return default


def _safe_action_int(action, key: str, default: int = 0) -> int:
    raw_value = _safe_action_get(action, key, default)
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return int(default)


def _safe_action_str(action, key: str) -> str:
    return str(_safe_action_get(action, key, "") or "")


def session_lmt_action_for_entry(actions, *, source_path: str, entry_id: int, preferred_action=None):
    normalized_source = str(source_path or "")
    normalized_entry_id = int(entry_id)
    candidates = [
        action
        for action in tuple(actions or ())
        if _safe_action_str(action, "mhw_anim_tools_import_kind") in {"lmt_action", "lmt_session_entry"}
        and _safe_action_str(action, "mhw_anim_tools_source_lmt") == normalized_source
        and _safe_action_int(action, "mhw_anim_tools_entry_id", -1) == normalized_entry_id
    ]
    if preferred_action in candidates:
        return preferred_action
    if not candidates:
        return None
    candidates.sort(
        key=lambda action: (
            0 if _safe_action_str(action, "mhw_anim_tools_import_kind") == "lmt_session_entry" else 1,
            str(getattr(action, "name", "")),
        )
    )
    return candidates[0]


def _format_vector(values) -> str:
    return ", ".join(f"{float(value):.4f}" for value in tuple(values or ()))


def _source_track_summaries(source_track_payload: str) -> list[dict[str, object]]:
    if not str(source_track_payload or ""):
        return []
    try:
        decoded = json.loads(str(source_track_payload))
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return [dict(item) for item in decoded if isinstance(item, dict)]


def _source_track_summary_maps(source_track_payload: str):
    summaries = _source_track_summaries(source_track_payload)
    by_index: dict[int, dict[str, object]] = {}
    identity_counts: Counter[tuple[int, int]] = Counter()
    for summary in summaries:
        track_index = int(summary.get("track_index", -1))
        if track_index >= 0:
            by_index[track_index] = summary
        identity = (int(summary.get("bone_id", 0)), int(summary.get("usage", 0)))
        identity_counts[identity] += 1
    by_identity = {
        (int(summary.get("bone_id", 0)), int(summary.get("usage", 0))): summary
        for summary in summaries
        if identity_counts[(int(summary.get("bone_id", 0)), int(summary.get("usage", 0)))] == 1
    }
    return summaries, by_index, by_identity


def _binding_by_track_index(action) -> dict[int, dict[str, object]]:
    result: dict[int, dict[str, object]] = {}
    for binding in load_lmt_import_track_bindings(action):
        result[int(binding.get("track_index", -1))] = dict(binding)
    return result


def _data_path_for_sampled_track(track) -> str:
    source_kind = str(getattr(track, "source_kind", "") or "")
    source_name = str(getattr(track, "source_name", "") or "")
    transform = str(getattr(track, "transform", "") or "")
    if source_kind == "bone" and source_name and transform:
        return f'pose.bones["{source_name}"].{transform}'
    return transform


def _display_track_index_for_sampled_track(
    track,
    *,
    source_summary: dict[str, object] | None,
    next_synthetic_index: int,
) -> tuple[int, int]:
    source_track_index = getattr(track, "source_track_index", None)
    if source_track_index is not None:
        return int(source_track_index), next_synthetic_index
    if source_summary is not None:
        try:
            return int(source_summary.get("track_index", next_synthetic_index)), next_synthetic_index
        except (TypeError, ValueError):
            pass
    return next_synthetic_index, next_synthetic_index + 1


def editable_track_summaries_for_action(action, *, armature_object, source_track_payload: str = "") -> list[dict[str, object]]:
    if action is None or armature_object is None or getattr(armature_object, "type", None) != "ARMATURE":
        return []
    sampling = sample_action_for_lmt_export(action, armature_object, sample_frames=(0,))
    source_summaries, source_by_index, source_by_identity = _source_track_summary_maps(source_track_payload)
    known_indices = {
        int(summary.get("track_index", -1))
        for summary in source_summaries
        if int(summary.get("track_index", -1)) >= 0
    }
    known_indices.update(
        int(binding.get("track_index", -1))
        for binding in load_lmt_import_track_bindings(action)
        if int(binding.get("track_index", -1)) >= 0
    )
    next_synthetic_index = (max(known_indices) + 1) if known_indices else 0
    bindings_by_track_index = _binding_by_track_index(action)
    summaries: list[dict[str, object]] = []

    for sampled_track in sampling.sampled_tracks:
        track_index = getattr(sampled_track, "source_track_index", None)
        identity = (int(sampled_track.bone_id), int(sampled_track.usage))
        source_summary = None
        if track_index is not None:
            source_summary = source_by_index.get(int(track_index))
        if source_summary is None:
            source_summary = source_by_identity.get(identity)
        binding = bindings_by_track_index.get(int(track_index)) if track_index is not None else None
        display_track_index, next_synthetic_index = _display_track_index_for_sampled_track(
            sampled_track,
            source_summary=source_summary,
            next_synthetic_index=next_synthetic_index,
        )

        usage_info = get_usage_semantics(int(sampled_track.usage))
        buffer_type = AUTHORED_BUFFER_TYPE
        if source_summary is not None:
            buffer_type = int(source_summary.get("buffer_type", AUTHORED_BUFFER_TYPE))
        elif binding is not None:
            buffer_type = int(binding.get("buffer_type", AUTHORED_BUFFER_TYPE))

        if buffer_type > 0:
            buffer_info = get_buffer_semantics(buffer_type)
            buffer_code = str(buffer_info.code)
            buffer_label = str(buffer_info.label)
        else:
            buffer_code = AUTHORED_BUFFER_CODE
            buffer_label = AUTHORED_BUFFER_LABEL

        authored_frames = tuple(int(frame) for frame in getattr(sampled_track, "authored_frames", ()) or ())
        first_keyframe = authored_frames[0] if authored_frames else -1
        last_keyframe = authored_frames[-1] if authored_frames else -1
        first_frame_value = tuple(getattr(sampled_track.frames[0], "value", ())) if getattr(sampled_track, "frames", ()) else ()
        import_mode = str(binding.get("import_mode", "") or "") if binding is not None else ""
        if not import_mode:
            import_mode = "armature"

        summaries.append(
            {
                "track_index": int(display_track_index),
                "source_track_index": int(track_index) if track_index is not None else -1,
                "bone_id": int(sampled_track.bone_id),
                "usage": int(sampled_track.usage),
                "usage_scope": str(usage_info.scope_label),
                "usage_label": f"{usage_info.scope_label} {usage_info.transform_label}",
                "transform_label": str(usage_info.transform_label),
                "blender_path_hint": str(usage_info.blender_path_hint),
                "channel_labels": ", ".join(str(label) for label in usage_info.channel_labels),
                "buffer_type": int(buffer_type),
                "buffer_code": buffer_code,
                "buffer_label": buffer_label,
                "buffer_size": int(source_summary.get("buffer_size", 0)) if source_summary is not None else 0,
                "buffer_offset": int(source_summary.get("buffer_offset", 0)) if source_summary is not None else 0,
                "raw_key_count": int(source_summary.get("raw_key_count", -1)) if source_summary is not None else len(authored_frames),
                "has_lerp": bool(source_summary.get("has_lerp", False)) if source_summary is not None else False,
                "weight": float(source_summary.get("weight", 1.0)) if source_summary is not None else 1.0,
                "basis_preview": str(source_summary.get("basis_preview", "")) if source_summary is not None else _format_vector(first_frame_value),
                "tail_frame": int(source_summary.get("tail_frame", -1)) if source_summary is not None else -1,
                "tail_preview": str(source_summary.get("tail_preview", "")) if source_summary is not None else "",
                "decoded_key_count": int(source_summary.get("decoded_key_count", len(authored_frames))) if source_summary is not None else len(authored_frames),
                "first_keyframe": int(source_summary.get("first_keyframe", first_keyframe)) if source_summary is not None else first_keyframe,
                "last_keyframe": int(source_summary.get("last_keyframe", last_keyframe)) if source_summary is not None else last_keyframe,
                "decode_error": str(source_summary.get("decode_error", "")) if source_summary is not None else "",
                "unknown_tag": int(source_summary.get("unknown_tag", 205)) if source_summary is not None else 205,
                "joint_type": int(source_summary.get("joint_type", 0)) if source_summary is not None else 0,
                "import_mode": import_mode,
                "source_kind": str(getattr(sampled_track, "source_kind", "") or ""),
                "source_name": str(getattr(sampled_track, "source_name", "") or ""),
                "data_path": str(binding.get("data_path", "") or _data_path_for_sampled_track(sampled_track))
                if binding is not None
                else _data_path_for_sampled_track(sampled_track),
                "channel_count": int(getattr(sampled_track, "channel_count", len(first_frame_value)) or len(first_frame_value)),
                "fallback_reason": str(binding.get("fallback_reason", "") or "") if binding is not None else "",
            }
        )
    return summaries


def next_authored_track_index(action, *, source_track_payload: str = "") -> int:
    known_indices = {
        int(summary.get("track_index", -1))
        for summary in _source_track_summaries(source_track_payload)
        if int(summary.get("track_index", -1)) >= 0
    }
    known_indices.update(
        int(binding.get("track_index", -1))
        for binding in load_lmt_import_track_bindings(action)
        if int(binding.get("track_index", -1)) >= 0
    )
    return (max(known_indices) + 1) if known_indices else 0


def track_identity_exists(action, *, armature_object, source_track_payload: str, bone_id: int, usage: int) -> bool:
    for summary in editable_track_summaries_for_action(
        action,
        armature_object=armature_object,
        source_track_payload=source_track_payload,
    ):
        if int(summary.get("bone_id", 0)) == int(bone_id) and int(summary.get("usage", 0)) == int(usage):
            return True
    return False


def authored_track_basis_for_usage(usage: int) -> tuple[float, ...]:
    usage_info = get_usage_semantics(int(usage))
    if usage_info.is_quaternion:
        return (1.0, 0.0, 0.0, 0.0)
    if usage_info.transform == "scale":
        return (1.0, 1.0, 1.0)
    return (0.0, 0.0, 0.0)


def authored_track_channel_values(usage: int) -> list[list[tuple[float, float]]]:
    return [[(0.0, float(component))] for component in authored_track_basis_for_usage(usage)]


def _resolved_pose_bone(armature_object, bone_name: str):
    pose = getattr(armature_object, "pose", None)
    pose_bones = getattr(pose, "bones", None)
    if pose_bones is None:
        return None
    getter = getattr(pose_bones, "get", None)
    if callable(getter):
        return getter(bone_name)
    try:
        return pose_bones[bone_name]
    except Exception:
        return None


def _delete_custom_property(owner, property_name: str) -> bool:
    if owner is None or not str(property_name or ""):
        return False
    try:
        if property_name in owner:
            del owner[property_name]
            return True
    except Exception:
        return False
    return False


def _ensure_track_quaternion_mode(armature_object, target) -> None:
    if str(getattr(target, "kind", "") or "") == "bone":
        pose_bone = _resolved_pose_bone(armature_object, str(getattr(target, "name", "") or ""))
        if pose_bone is not None:
            try:
                pose_bone.rotation_mode = "QUATERNION"
            except Exception:
                pass
        return
    try:
        armature_object.rotation_mode = "QUATERNION"
    except Exception:
        pass


def _resolve_raw_fallback_target(armature_object, *, bone_id: int, usage: int, track_index: int):
    target, target_error = resolve_track_binding_target(armature_object, bone_id, usage)
    fallback_group = missing_bone_raw_action_group(
        bone_id=int(bone_id),
        usage=int(usage),
        track_index=int(track_index),
    )
    if target is not None and str(getattr(target, "kind", "") or "") == LMT_RAW_DUPLICATE_OWNER_BONE:
        pose_bone = _resolved_pose_bone(armature_object, str(getattr(target, "name", "") or ""))
        if pose_bone is not None:
            return {
                "owner": pose_bone,
                "owner_kind": LMT_RAW_DUPLICATE_OWNER_BONE,
                "owner_name": str(getattr(target, "name", "") or ""),
                "action_group": raw_duplicate_group_name(
                    bone_id=int(bone_id),
                    usage=int(usage),
                    track_index=int(track_index),
                    owner_kind=LMT_RAW_DUPLICATE_OWNER_BONE,
                    owner_name=str(getattr(target, "name", "") or ""),
                    action_group=str(getattr(target, "action_group", "") or ""),
                ),
                "fallback_warning": "",
            }
    if target is not None and str(getattr(target, "kind", "") or "") == LMT_RAW_DUPLICATE_OWNER_OBJECT:
        return {
            "owner": armature_object,
            "owner_kind": LMT_RAW_DUPLICATE_OWNER_OBJECT,
            "owner_name": str(getattr(target, "name", "") or getattr(armature_object, "name", "")),
            "action_group": raw_duplicate_group_name(
                bone_id=int(bone_id),
                usage=int(usage),
                track_index=int(track_index),
                owner_kind=LMT_RAW_DUPLICATE_OWNER_OBJECT,
                owner_name=str(getattr(target, "name", "") or getattr(armature_object, "name", "")),
                action_group=str(getattr(target, "action_group", "") or ""),
            ),
            "fallback_warning": "",
        }
    return {
        "owner": armature_object,
        "owner_kind": LMT_RAW_DUPLICATE_OWNER_OBJECT,
        "owner_name": str(getattr(armature_object, "name", "") or ""),
        "action_group": fallback_group,
        "fallback_warning": str(target_error or ""),
    }


def add_authored_track_to_action(
    action,
    armature_object,
    *,
    source_path: str,
    entry_id: int,
    bone_id: int,
    usage: int,
    source_track_payload: str = "",
) -> dict[str, object]:
    usage_info = get_usage_semantics(int(usage))
    if usage_info.transform not in {"rotation", "translation", "scale"}:
        raise ValueError(f"Unsupported LMT track usage {int(usage)}.")
    if track_identity_exists(
        action,
        armature_object=armature_object,
        source_track_payload=source_track_payload,
        bone_id=int(bone_id),
        usage=int(usage),
    ):
        raise ValueError(f"Track identity bone_id={int(bone_id)} usage={int(usage)} already exists on this action.")

    next_track_index = next_authored_track_index(action, source_track_payload=source_track_payload)
    channel_values = authored_track_channel_values(int(usage))
    target, target_error = resolve_track_binding_target(armature_object, int(bone_id), int(usage))

    if target is not None:
        if usage_info.is_quaternion:
            _ensure_track_quaternion_mode(armature_object, target)
        if str(getattr(target, "kind", "") or "") == "bone":
            create_transform_fcurves(
                action,
                bone_name=str(getattr(target, "name", "") or ""),
                data_path_suffix=str(usage_info.blender_path_hint or ""),
                channel_values=channel_values,
            )
            data_path = f'pose.bones["{str(getattr(target, "name", "") or "")}"].{str(usage_info.blender_path_hint or "")}'
        else:
            create_action_fcurves(
                action,
                data_path=str(usage_info.blender_path_hint or ""),
                action_group=str(getattr(target, "action_group", "") or ""),
                channel_values=channel_values,
            )
            data_path = str(usage_info.blender_path_hint or "")
        return {
            "track_index": int(next_track_index),
            "import_mode": "armature",
            "source_kind": str(getattr(target, "kind", "") or ""),
            "data_path": data_path,
        }

    if int(bone_id) < 0 or str(usage_info.scope or "") == "root":
        raise ValueError(str(target_error or "Root track requires a resolvable target."))

    buffer_type = 2 if usage_info.is_quaternion else 1
    property_name = raw_duplicate_property_name(
        source_path=str(source_path or ""),
        action_id=int(entry_id),
        track_index=int(next_track_index),
        bone_id=int(bone_id),
        usage=int(usage),
    )
    fallback_target = _resolve_raw_fallback_target(
        armature_object,
        bone_id=int(bone_id),
        usage=int(usage),
        track_index=int(next_track_index),
    )
    binding = {
        "track_index": int(next_track_index),
        "bone_id": int(bone_id),
        "usage": int(usage),
        "buffer_type": int(buffer_type),
        "import_mode": LMT_RAW_DUPLICATE_IMPORT_MODE,
        "source_kind": "missing_bone_raw",
        "source_name": "",
        "transform": str(usage_info.blender_path_hint or ""),
        "property_name": property_name,
        "channel_count": len(tuple(authored_track_basis_for_usage(int(usage)))),
        "display_name": missing_bone_raw_display_name(
            bone_id=int(bone_id),
            usage=int(usage),
            track_index=int(next_track_index),
        ),
        "action_group": str(fallback_target["action_group"]),
        "owner_kind": str(fallback_target["owner_kind"]),
        "owner_name": str(fallback_target["owner_name"]),
        "data_path": raw_duplicate_data_path(
            property_name=property_name,
            owner_kind=str(fallback_target["owner_kind"]),
            owner_name=str(fallback_target["owner_name"]),
        ),
        "preserve_raw_quaternion_values": False,
        "fallback_reason": "missing_bone",
        "fallback_detail": str(target_error or ""),
    }
    ensure_raw_duplicate_property(
        fallback_target["owner"],
        binding,
        basis_value=authored_track_basis_for_usage(int(usage)),
    )
    create_action_fcurves(
        action,
        data_path=str(binding["data_path"]),
        action_group=str(binding["action_group"]),
        channel_values=channel_values,
    )
    bindings = load_lmt_import_track_bindings(action)
    bindings.append(binding)
    save_lmt_import_track_bindings(action, bindings)
    return {
        "track_index": int(next_track_index),
        "import_mode": LMT_RAW_DUPLICATE_IMPORT_MODE,
        "source_kind": "missing_bone_raw",
        "data_path": str(binding["data_path"]),
    }


def remove_authored_track_from_action(action, armature_object, *, track_spec: dict[str, object]) -> dict[str, int]:
    data_path = str(track_spec.get("data_path", "") or "")
    channel_count = max(1, int(track_spec.get("channel_count", 1) or 1))
    removed_fcurves = 0
    for fcurve in list(getattr(action, "fcurves", ())):
        if str(getattr(fcurve, "data_path", "") or "") != data_path:
            continue
        array_index = int(getattr(fcurve, "array_index", 0))
        if 0 <= array_index < channel_count:
            action.fcurves.remove(fcurve)
            removed_fcurves += 1

    bindings = load_lmt_import_track_bindings(action)
    removed_bindings = 0
    kept_bindings: list[dict[str, object]] = []
    property_name_to_delete = ""
    owner_kind = ""
    owner_name = ""
    source_track_index = int(track_spec.get("source_track_index", -1) or -1)
    for binding in bindings:
        binding_track_index = int(binding.get("track_index", -1))
        binding_data_path = str(binding.get("data_path", "") or "")
        matches_source_track = source_track_index >= 0 and binding_track_index == source_track_index
        matches_raw_path = bool(data_path) and binding_data_path == data_path
        if matches_source_track or matches_raw_path:
            removed_bindings += 1
            property_name_to_delete = str(binding.get("property_name", "") or property_name_to_delete)
            owner_kind = str(binding.get("owner_kind", "") or owner_kind)
            owner_name = str(binding.get("owner_name", "") or owner_name)
            continue
        kept_bindings.append(binding)
    if removed_bindings != len(bindings):
        save_lmt_import_track_bindings(action, kept_bindings)
    elif removed_bindings > 0:
        save_lmt_import_track_bindings(action, [])

    if property_name_to_delete:
        if owner_kind == LMT_RAW_DUPLICATE_OWNER_BONE and owner_name:
            _delete_custom_property(_resolved_pose_bone(armature_object, owner_name), property_name_to_delete)
        else:
            _delete_custom_property(armature_object, property_name_to_delete)

    return {"removed_fcurves": int(removed_fcurves), "removed_bindings": int(removed_bindings)}
