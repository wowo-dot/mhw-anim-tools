"""Helpers for binding decoded LMT tracks onto Blender armatures."""

from __future__ import annotations

from dataclasses import dataclass

try:
    from ..integration.mhw_bones import bonefunction_name_from_index
    from ..integration.mhw_bones import is_bonefunction_name
    from ..integration.mhw_bones import is_mhbone_name
    from ..integration.mhw_bones import mhbone_name_from_index
except ImportError:  # pragma: no cover - test runner imports from addon root
    from integration.mhw_bones import bonefunction_name_from_index
    from integration.mhw_bones import is_bonefunction_name
    from integration.mhw_bones import is_mhbone_name
    from integration.mhw_bones import mhbone_name_from_index


@dataclass(frozen=True)
class ArmatureBindingSummary:
    supported_track_count: int
    resolved_track_count: int
    unresolved_track_count: int
    missing_bone_ids: tuple[int, ...]
    root_required: bool
    root_resolved: bool
    root_target_label: str
    mhbone_count: int
    bonefunction_count: int


@dataclass(frozen=True)
class TrackBindingTarget:
    kind: str
    name: str
    data_path_prefix: str
    action_group: str


def describe_armature_object(obj):
    if obj is None:
        return {"name": "", "type": ""}
    return {"name": getattr(obj, "name", ""), "type": getattr(obj, "type", "")}


def mhbone_count(armature_object) -> int:
    if armature_object is None or armature_object.type != "ARMATURE":
        return 0
    return sum(1 for bone in armature_object.data.bones if is_mhbone_name(bone.name))


def bonefunction_count(armature_object) -> int:
    if armature_object is None or armature_object.type != "ARMATURE":
        return 0
    return sum(1 for bone in armature_object.data.bones if is_bonefunction_name(bone.name))


def has_mhw_style_bones(armature_object) -> bool:
    return mhbone_count(armature_object) > 0 or bonefunction_count(armature_object) > 0


def find_root_bone_name(armature_object) -> str | None:
    if armature_object is None or armature_object.type != "ARMATURE":
        return None
    bones = armature_object.data.bones
    if "Root" in bones:
        return "Root"
    for bone in bones:
        if bone.name.lower() == "root":
            return bone.name
    if has_mhw_style_bones(armature_object):
        return None
    root_candidates = [bone.name for bone in bones if bone.parent is None]
    if len(root_candidates) == 1:
        return root_candidates[0]
    return None


def resolve_track_binding_target(armature_object, bone_id: int, usage: int) -> tuple[TrackBindingTarget | None, str | None]:
    if armature_object is None or armature_object.type != "ARMATURE":
        return None, "No target armature selected."
    bones = armature_object.data.bones
    if usage >= 3 or bone_id == -1:
        root_name = find_root_bone_name(armature_object)
        if root_name is not None:
            return TrackBindingTarget(
                kind="bone",
                name=root_name,
                data_path_prefix=f'pose.bones["{root_name}"]',
                action_group=root_name,
            ), None
        if has_mhw_style_bones(armature_object):
            return TrackBindingTarget(
                kind="object",
                name=armature_object.name,
                data_path_prefix="",
                action_group="Root Motion",
            ), None
        return None, "Root track requires a recognizable root bone."
    candidate_names = (
        mhbone_name_from_index(bone_id),
        bonefunction_name_from_index(bone_id),
    )
    for name in candidate_names:
        if name in bones:
            return TrackBindingTarget(
                kind="bone",
                name=name,
                data_path_prefix=f'pose.bones["{name}"]',
                action_group=name,
            ), None
    return None, f"Target armature is missing bone id {bone_id:03d}."


def find_track_target_bone_name(armature_object, bone_id: int, usage: int) -> tuple[str | None, str | None]:
    target, error = resolve_track_binding_target(armature_object, bone_id, usage)
    if target is None:
        return None, error
    if target.kind != "bone":
        return None, "Resolved track target is not a pose bone."
    return target.name, None


def summarize_track_binding(armature_object, track_specs) -> ArmatureBindingSummary:
    if armature_object is None or armature_object.type != "ARMATURE":
        return ArmatureBindingSummary(
            supported_track_count=0,
            resolved_track_count=0,
            unresolved_track_count=0,
            missing_bone_ids=(),
            root_required=False,
            root_resolved=False,
            root_target_label="",
            mhbone_count=0,
            bonefunction_count=0,
        )

    supported_track_count = 0
    resolved_track_count = 0
    missing_bone_ids: set[int] = set()
    root_required = False
    root_target_label = ""

    for track in track_specs:
        blender_path_hint = track.get("blender_path_hint", "")
        usage = int(track.get("usage", -1))
        bone_id = int(track.get("bone_id", -9999))
        if not blender_path_hint:
            continue
        supported_track_count += 1
        if usage >= 3 or bone_id == -1:
            root_required = True
        target, _error = resolve_track_binding_target(armature_object, bone_id, usage)
        if target is not None:
            resolved_track_count += 1
            if usage >= 3 or bone_id == -1:
                root_target_label = "Armature Object" if target.kind == "object" else target.name
            continue
        if bone_id >= 0:
            missing_bone_ids.add(bone_id)

    unresolved_track_count = supported_track_count - resolved_track_count
    return ArmatureBindingSummary(
        supported_track_count=supported_track_count,
        resolved_track_count=resolved_track_count,
        unresolved_track_count=unresolved_track_count,
        missing_bone_ids=tuple(sorted(missing_bone_ids)),
        root_required=root_required,
        root_resolved=(not root_required) or bool(root_target_label),
        root_target_label=root_target_label,
        mhbone_count=mhbone_count(armature_object),
        bonefunction_count=bonefunction_count(armature_object),
    )
