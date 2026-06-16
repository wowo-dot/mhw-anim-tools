"""Import decoded LMT actions into Blender Actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    from ..core.animation.transforms import canonicalize_quaternion_frames_wxyz
    from ..core.formats.lmt.decoder import decode_action_tracks
    from ..core.formats.lmt.export_context import find_duplicate_track_identities
    from ..core.formats.lmt.semantics import get_usage_semantics
    from .armature import resolve_track_binding_target
    from .fcurves import build_channel_value_lists
    from .fcurves import create_action_fcurves
    from .fcurves import create_transform_fcurves
    from .fcurves import ensure_action
    from .fcurves import ensure_armature_animation_data
    from .lmt_track_metadata import clear_lmt_import_track_bindings
    from .lmt_track_metadata import ensure_raw_duplicate_property
    from .lmt_track_metadata import LMT_ARMATURE_IMPORT_MODE
    from .lmt_track_metadata import LMT_RAW_DUPLICATE_IMPORT_MODE
    from .lmt_track_metadata import QUATERNION_LERP_BUFFER_TYPES
    from .lmt_track_metadata import raw_duplicate_action_group
    from .lmt_track_metadata import raw_duplicate_property_name
    from .lmt_track_metadata import save_lmt_import_track_bindings
    from .lmt_track_metadata import track_display_name
    from .space import adapt_track_frames_for_target_space
except ImportError:  # pragma: no cover - test runner imports from addon root
    from core.animation.transforms import canonicalize_quaternion_frames_wxyz
    from core.formats.lmt.decoder import decode_action_tracks
    from core.formats.lmt.export_context import find_duplicate_track_identities
    from core.formats.lmt.semantics import get_usage_semantics
    from blender_adapter.armature import resolve_track_binding_target
    from blender_adapter.fcurves import build_channel_value_lists
    from blender_adapter.fcurves import create_action_fcurves
    from blender_adapter.fcurves import create_transform_fcurves
    from blender_adapter.fcurves import ensure_action
    from blender_adapter.fcurves import ensure_armature_animation_data
    from blender_adapter.lmt_track_metadata import clear_lmt_import_track_bindings
    from blender_adapter.lmt_track_metadata import ensure_raw_duplicate_property
    from blender_adapter.lmt_track_metadata import LMT_ARMATURE_IMPORT_MODE
    from blender_adapter.lmt_track_metadata import LMT_RAW_DUPLICATE_IMPORT_MODE
    from blender_adapter.lmt_track_metadata import QUATERNION_LERP_BUFFER_TYPES
    from blender_adapter.lmt_track_metadata import raw_duplicate_action_group
    from blender_adapter.lmt_track_metadata import raw_duplicate_property_name
    from blender_adapter.lmt_track_metadata import save_lmt_import_track_bindings
    from blender_adapter.lmt_track_metadata import track_display_name
    from blender_adapter.space import adapt_track_frames_for_target_space


SUPPORTED_BUFFER_TYPES = {1, 2, 3, 4, 5, 6, 7, 11, 12, 13, 14, 15}


@dataclass(frozen=True)
class ImportDiagnostic:
    level: str
    source: str
    message: str


@dataclass
class ImportActionResult:
    action_name: str = ""
    imported_track_count: int = 0
    skipped_track_count: int = 0
    created_fcurve_count: int = 0
    frame_end: int = 0
    diagnostics: list[ImportDiagnostic] = field(default_factory=list)

    def add(self, level: str, source: str, message: str):
        self.diagnostics.append(ImportDiagnostic(level=level, source=source, message=message))

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "WARNING")

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.level == "ERROR")


def _build_track_frames(decoded_track, usage_info):
    frames = [(0.0, tuple(decoded_track.basis_value))]
    frames.extend((float(sample.frame), tuple(sample.value)) for sample in decoded_track.keyframes)
    if decoded_track.tail_frame is not None and decoded_track.tail_value is not None:
        frames.append((float(decoded_track.tail_frame), tuple(decoded_track.tail_value)))
    if usage_info.is_quaternion:
        frames = canonicalize_quaternion_frames_wxyz(frames)
    return frames


def _ensure_quaternion_mode(armature_object, bone_name: str):
    pose_bone = armature_object.pose.bones.get(bone_name)
    if pose_bone is not None:
        pose_bone.rotation_mode = "QUATERNION"


def _ensure_object_quaternion_mode(armature_object):
    armature_object.rotation_mode = "QUATERNION"


def _action_name_for_import(source_path: str, action_id: int) -> str:
    stem = Path(source_path).stem
    return f"LMT::{stem}::{action_id:03d}"


def _format_duplicate_track_identities(duplicate_track_identities) -> str:
    return "; ".join(
        f"bone_id={bone_id}, usage={usage}, count={count}"
        for bone_id, usage, count in duplicate_track_identities
    )


def import_lmt_action_to_armature(lmt, action_index: int, armature_object, *, source_path: str) -> ImportActionResult:
    result = ImportActionResult()
    if armature_object is None or armature_object.type != "ARMATURE":
        result.add("ERROR", "armature", "Select a target armature before importing an LMT action.")
        return result
    if action_index < 0 or action_index >= len(lmt.actions):
        result.add("ERROR", "session", "Selected LMT action is out of range for the current session.")
        return result

    source_action = lmt.actions[action_index]
    decoded_action = decode_action_tracks(source_action, strict=False)
    duplicate_track_identities = find_duplicate_track_identities(source_action)
    duplicate_identity_counts = {
        (int(bone_id), int(usage)): int(count)
        for bone_id, usage, count in duplicate_track_identities
    }
    action_name = _action_name_for_import(source_path, source_action.id)
    blender_action = ensure_action(action_name)
    clear_lmt_import_track_bindings(blender_action)
    blender_action["mhw_anim_tools_source_lmt"] = source_path
    blender_action["mhw_anim_tools_entry_id"] = int(source_action.id)
    blender_action["mhw_anim_tools_import_kind"] = "lmt_action"
    blender_action["mhw_anim_tools_source_version"] = int(lmt.header.version)
    blender_action["mhw_anim_tools_source_entry_count"] = int(lmt.header.entry_count)
    blender_action["mhw_anim_tools_source_action_count"] = int(lmt.action_count)
    blender_action["mhw_anim_tools_source_has_timl"] = bool(source_action.has_timl)
    blender_action["mhw_anim_tools_source_timl_offset"] = int(source_action.header.timl_offset)
    blender_action["mhw_anim_tools_source_has_duplicate_track_identities"] = bool(duplicate_track_identities)
    blender_action["mhw_anim_tools_source_duplicate_track_identities"] = _format_duplicate_track_identities(
        duplicate_track_identities
    )

    animation_data = ensure_armature_animation_data(armature_object)
    animation_data.action = blender_action
    result.action_name = blender_action.name
    imported_track_bindings: list[dict[str, object]] = []
    if duplicate_track_identities:
        result.add(
            "WARNING",
            "import",
            (
                "Source action contains duplicate raw track identities: "
                f"{blender_action['mhw_anim_tools_source_duplicate_track_identities']}. "
                "These tracks are imported as raw Graph Editor slots on the armature object instead of normal pose "
                "channels, so they remain editable and source-backed exportable without pretending Blender can map "
                "them to one bone transform."
            ),
        )

    for decoded_track in decoded_action.tracks:
        usage_info = get_usage_semantics(decoded_track.usage)
        source_label = f"track {decoded_track.track_index:02d} / bone {decoded_track.bone_id}"
        track_identity = (int(decoded_track.bone_id), int(decoded_track.usage))

        if usage_info.transform not in {"rotation", "translation", "scale"} or not usage_info.blender_path_hint:
            result.skipped_track_count += 1
            result.add("WARNING", source_label, f"Skipped unsupported usage {decoded_track.usage}.")
            continue
        if decoded_track.buffer_type not in SUPPORTED_BUFFER_TYPES:
            result.skipped_track_count += 1
            result.add("WARNING", source_label, f"Skipped unsupported buffer type {decoded_track.buffer_type}.")
            continue
        if decoded_track.decode_error:
            result.skipped_track_count += 1
            result.add("WARNING", source_label, f"Skipped undecodable track: {decoded_track.decode_error}")
            continue

        if duplicate_identity_counts.get(track_identity, 0) > 1:
            frames = _build_track_frames(decoded_track, usage_info)
            property_name = raw_duplicate_property_name(
                source_path=source_path,
                action_id=int(source_action.id),
                track_index=int(decoded_track.track_index),
                bone_id=int(decoded_track.bone_id),
                usage=int(decoded_track.usage),
            )
            binding = {
                "track_index": int(decoded_track.track_index),
                "bone_id": int(decoded_track.bone_id),
                "usage": int(decoded_track.usage),
                "buffer_type": int(decoded_track.buffer_type),
                "import_mode": LMT_RAW_DUPLICATE_IMPORT_MODE,
                "source_kind": "raw_duplicate",
                "source_name": "",
                "transform": str(usage_info.blender_path_hint or ""),
                "property_name": property_name,
                "channel_count": len(tuple(decoded_track.basis_value)),
                "display_name": track_display_name(
                    bone_id=int(decoded_track.bone_id),
                    usage=int(decoded_track.usage),
                    track_index=int(decoded_track.track_index),
                ),
                "action_group": raw_duplicate_action_group(
                    bone_id=int(decoded_track.bone_id),
                    usage=int(decoded_track.usage),
                    track_index=int(decoded_track.track_index),
                ),
                "preserve_raw_quaternion_values": bool(
                    usage_info.is_quaternion and int(decoded_track.buffer_type) in QUATERNION_LERP_BUFFER_TYPES
                ),
            }
            ensure_raw_duplicate_property(armature_object, binding, basis_value=decoded_track.basis_value)
            created_fcurves = create_action_fcurves(
                blender_action,
                data_path=f'["{property_name}"]',
                action_group=str(binding["action_group"]),
                channel_values=build_channel_value_lists(frames),
            )
            imported_track_bindings.append(binding)
            result.imported_track_count += 1
            result.created_fcurve_count += len(created_fcurves)
            result.frame_end = max(result.frame_end, int(frames[-1][0]) if frames else source_action.header.frame_count)
            continue

        target, target_error = resolve_track_binding_target(
            armature_object,
            decoded_track.bone_id,
            decoded_track.usage,
        )
        if target is None:
            result.skipped_track_count += 1
            result.add("WARNING", source_label, target_error or "Could not resolve target binding.")
            continue

        if usage_info.is_quaternion:
            if target.kind == "bone":
                _ensure_quaternion_mode(armature_object, target.name)
            else:
                _ensure_object_quaternion_mode(armature_object)

        frames = _build_track_frames(decoded_track, usage_info)
        frames = adapt_track_frames_for_target_space(
            armature_object,
            target,
            usage_info,
            frames,
        )
        channel_values = build_channel_value_lists(frames)
        if target.kind == "bone":
            created_fcurves = create_transform_fcurves(
                blender_action,
                bone_name=target.name,
                data_path_suffix=usage_info.blender_path_hint,
                channel_values=channel_values,
            )
        else:
            created_fcurves = create_action_fcurves(
                blender_action,
                data_path=usage_info.blender_path_hint,
                action_group=target.action_group,
                channel_values=channel_values,
            )
        imported_track_bindings.append(
            {
                "track_index": int(decoded_track.track_index),
                "bone_id": int(decoded_track.bone_id),
                "usage": int(decoded_track.usage),
                "buffer_type": int(decoded_track.buffer_type),
                "import_mode": LMT_ARMATURE_IMPORT_MODE,
                "source_kind": str(target.kind or ""),
                "source_name": str(target.name or ""),
                "transform": str(usage_info.blender_path_hint or ""),
                "property_name": "",
                "channel_count": len(tuple(decoded_track.basis_value)),
                "display_name": track_display_name(
                    bone_id=int(decoded_track.bone_id),
                    usage=int(decoded_track.usage),
                    track_index=int(decoded_track.track_index),
                ),
                "action_group": str(target.action_group or ""),
                "preserve_raw_quaternion_values": bool(
                    usage_info.is_quaternion and int(decoded_track.buffer_type) in QUATERNION_LERP_BUFFER_TYPES
                ),
            }
        )
        result.imported_track_count += 1
        result.created_fcurve_count += len(created_fcurves)
        result.frame_end = max(result.frame_end, int(frames[-1][0]) if frames else source_action.header.frame_count)

    save_lmt_import_track_bindings(blender_action, imported_track_bindings)
    if result.imported_track_count == 0 and not result.error_count:
        result.add("ERROR", "import", "No supported tracks were imported.")
    return result
