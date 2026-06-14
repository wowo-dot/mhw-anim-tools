"""Target-space adaptation for direct Blender action import.

This module keeps Blender-specific rest-pose inspection out of the LMT decoder.
Decoded LMT samples stay in engine-oriented units/space until the final import
step, where we adapt only the targets that are known to come from
MHW_Model_Editor MOD3 armatures.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    from ..core.animation.transforms import transform_blender_object_quaternion_to_mhw_wxyz
    from ..core.animation.transforms import transform_blender_object_translation_to_mhw
    from ..core.animation.transforms import transform_blender_pose_translation_delta_to_mhw
    from ..core.animation.transforms import transform_mhw_object_quaternion_wxyz
    from ..core.animation.transforms import transform_mhw_object_translation
    from ..core.animation.transforms import transform_mhw_pose_translation_to_delta
    from ..integration.mhw_bones import is_mhbone_name
except ImportError:  # pragma: no cover - test runner imports from addon root
    from core.animation.transforms import transform_blender_object_quaternion_to_mhw_wxyz
    from core.animation.transforms import transform_blender_object_translation_to_mhw
    from core.animation.transforms import transform_blender_pose_translation_delta_to_mhw
    from core.animation.transforms import transform_mhw_object_quaternion_wxyz
    from core.animation.transforms import transform_mhw_object_translation
    from core.animation.transforms import transform_mhw_pose_translation_to_delta
    from integration.mhw_bones import is_mhbone_name


MHW_MOD3_COLLECTION_TYPE = "MHW_MOD3_COLLECTION"


@dataclass(frozen=True)
class TrackSpaceTarget:
    kind: str
    name: str


def _is_mod3_collection(collection) -> bool:
    if collection is None:
        return False
    collection_type = collection.get("~TYPE") if hasattr(collection, "get") else None
    collection_name = getattr(collection, "name", "")
    return collection_type == MHW_MOD3_COLLECTION_TYPE or collection_name.endswith(".mod3")


def uses_mhw_model_editor_space_adapter(armature_object) -> bool:
    if armature_object is None or getattr(armature_object, "type", None) != "ARMATURE":
        return False
    if not any(is_mhbone_name(bone.name) for bone in armature_object.data.bones):
        return False
    return any(_is_mod3_collection(collection) for collection in getattr(armature_object, "users_collection", ()))


def bone_rest_local_translation(armature_object, bone_name: str) -> tuple[float, float, float] | None:
    bone = armature_object.data.bones.get(bone_name)
    if bone is None:
        return None
    rest_local = bone.matrix_local.copy()
    if bone.parent is not None:
        rest_local = bone.parent.matrix_local.inverted() @ rest_local
    translation = rest_local.to_translation()
    return (float(translation.x), float(translation.y), float(translation.z))


def adapt_track_frames_for_target_space(armature_object, target, usage_info, frames):
    if not frames or not uses_mhw_model_editor_space_adapter(armature_object):
        return frames

    adapted_frames = []
    if target.kind == "object":
        for timing, value in frames:
            converted = tuple(float(component) for component in value)
            if usage_info.transform == "translation":
                converted = transform_mhw_object_translation(converted)
            elif usage_info.transform == "rotation" and usage_info.is_quaternion:
                converted = transform_mhw_object_quaternion_wxyz(converted)
            adapted_frames.append((timing, converted))
        return adapted_frames

    if target.kind == "bone" and usage_info.transform == "translation":
        baseline = bone_rest_local_translation(armature_object, target.name)
        if baseline is None:
            return frames
        for timing, value in frames:
            converted = transform_mhw_pose_translation_to_delta(tuple(float(component) for component in value), baseline)
            adapted_frames.append((timing, converted))
        return adapted_frames

    return frames


def adapt_track_frames_for_export_space(armature_object, target, usage_info, frames):
    if not frames or not uses_mhw_model_editor_space_adapter(armature_object):
        return frames

    adapted_frames = []
    if target.kind == "object":
        for timing, value in frames:
            converted = tuple(float(component) for component in value)
            if usage_info.transform == "translation":
                converted = transform_blender_object_translation_to_mhw(converted)
            elif usage_info.transform == "rotation" and usage_info.is_quaternion:
                converted = transform_blender_object_quaternion_to_mhw_wxyz(converted)
            adapted_frames.append((timing, converted))
        return adapted_frames

    if target.kind == "bone" and usage_info.transform == "translation":
        baseline = bone_rest_local_translation(armature_object, target.name)
        if baseline is None:
            return frames
        for timing, value in frames:
            converted = transform_blender_pose_translation_delta_to_mhw(tuple(float(component) for component in value), baseline)
            adapted_frames.append((timing, converted))
        return adapted_frames

    return frames
