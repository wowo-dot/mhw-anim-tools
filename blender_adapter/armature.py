"""Helpers for binding decoded LMT tracks onto Blender armatures."""

from __future__ import annotations

from dataclasses import dataclass

try:  # pragma: no cover - Blender runtime only
    import bpy
except ImportError:  # pragma: no cover - unit tests import from addon root
    bpy = None

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


@dataclass(frozen=True)
class EnsuredRootMotionBone:
    name: str | None
    created: bool
    error: str


MHW_ROOT_MOTION_BONE_NAME = "MHW_RootMotion"


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


def _explicit_root_bone_name(armature_object) -> str | None:
    if armature_object is None or armature_object.type != "ARMATURE":
        return None
    bones = armature_object.data.bones
    if "Root" in bones:
        return "Root"
    for bone in bones:
        if bone.name.lower() == "root":
            return bone.name
    if MHW_ROOT_MOTION_BONE_NAME in bones:
        return MHW_ROOT_MOTION_BONE_NAME
    return None


def _preferred_mhw_root_source_name(armature_object) -> str | None:
    if armature_object is None or armature_object.type != "ARMATURE":
        return None
    bones = armature_object.data.bones
    for preferred_name in ("MhBone_000", "BoneFunction.000"):
        if preferred_name in bones:
            return preferred_name
    for bone in bones:
        if is_mhbone_name(bone.name) or is_bonefunction_name(bone.name):
            return bone.name
    return None


def find_root_bone_name(armature_object) -> str | None:
    if armature_object is None or armature_object.type != "ARMATURE":
        return None
    bones = armature_object.data.bones
    explicit_root = _explicit_root_bone_name(armature_object)
    if explicit_root is not None:
        return explicit_root
    root_candidates = [bone.name for bone in bones if bone.parent is None]
    if len(root_candidates) == 1:
        return root_candidates[0]
    return None


def ensure_mhw_root_motion_bone(armature_object) -> EnsuredRootMotionBone:
    if armature_object is None or armature_object.type != "ARMATURE":
        return EnsuredRootMotionBone(name=None, created=False, error="No target armature selected.")
    if not has_mhw_style_bones(armature_object):
        return EnsuredRootMotionBone(name=find_root_bone_name(armature_object), created=False, error="")

    explicit_root = _explicit_root_bone_name(armature_object)
    if explicit_root is not None:
        return EnsuredRootMotionBone(name=explicit_root, created=False, error="")
    if bpy is None:
        return EnsuredRootMotionBone(name=None, created=False, error="")
    if not hasattr(armature_object.data, "edit_bones"):
        return EnsuredRootMotionBone(name=None, created=False, error="")

    source_name = _preferred_mhw_root_source_name(armature_object)
    if source_name is None:
        return EnsuredRootMotionBone(name=None, created=False, error="")

    view_layer = getattr(bpy.context, "view_layer", None)
    objects = getattr(view_layer, "objects", None) if view_layer is not None else None
    if objects is None:
        return EnsuredRootMotionBone(name=None, created=False, error="Blender view layer is unavailable.")

    active_object = getattr(objects, "active", None)
    active_mode = getattr(active_object, "mode", "OBJECT") if active_object is not None else "OBJECT"
    selected_objects = tuple(getattr(bpy.context, "selected_objects", ()) or ())

    try:
        if active_object is not None and getattr(active_object, "mode", "OBJECT") != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        objects.active = armature_object
        select_set = getattr(armature_object, "select_set", None)
        if callable(select_set):
            select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")

        edit_bones = armature_object.data.edit_bones
        if MHW_ROOT_MOTION_BONE_NAME in edit_bones:
            return EnsuredRootMotionBone(name=MHW_ROOT_MOTION_BONE_NAME, created=False, error="")

        source_bone = edit_bones.get(source_name)
        helper = edit_bones.new(MHW_ROOT_MOTION_BONE_NAME)
        if source_bone is not None:
            helper.matrix = source_bone.matrix.copy()
            helper.length = max(float(source_bone.length), 0.1)
        else:
            helper.head = (0.0, 0.0, 0.0)
            helper.tail = (0.0, 0.0, 0.2)
        helper.use_deform = False
        helper.parent = None

        rootless_bones = [bone for bone in edit_bones if bone.name != MHW_ROOT_MOTION_BONE_NAME and bone.parent is None]
        for bone in rootless_bones:
            bone.parent = helper
            bone.use_connect = False

        bpy.ops.object.mode_set(mode="OBJECT")
        helper_bone = armature_object.data.bones.get(MHW_ROOT_MOTION_BONE_NAME)
        if helper_bone is not None:
            helper_bone.use_deform = False
        return EnsuredRootMotionBone(name=MHW_ROOT_MOTION_BONE_NAME, created=True, error="")
    except Exception as exc:  # pragma: no cover - Blender runtime only
        return EnsuredRootMotionBone(name=None, created=False, error=str(exc))
    finally:  # pragma: no cover - Blender runtime only
        try:
            current_active = getattr(objects, "active", None)
            if current_active is not None and getattr(current_active, "mode", "OBJECT") != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass
        if active_object is not None:
            try:
                objects.active = active_object
            except Exception:
                pass
        for selected in tuple(getattr(bpy.context, "selected_objects", ()) or ()):
            deselect = getattr(selected, "select_set", None)
            if callable(deselect):
                try:
                    deselect(False)
                except Exception:
                    pass
        for selected in selected_objects:
            select = getattr(selected, "select_set", None)
            if callable(select):
                try:
                    select(True)
                except Exception:
                    pass
        if active_object is not None:
            try:
                objects.active = active_object
            except Exception:
                pass
        if active_object is not None and active_mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode=active_mode)
            except Exception:
                pass


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
