"""Light-touch MHW_Model_Editor discovery for the new rewrite UI."""

from __future__ import annotations

import addon_utils
import bpy

from .mhw_bones import is_bonefunction_name
from .mhw_bones import is_mhbone_name


MHW_ADDON_MODULES = ("MHW_Model_Editor-main", "MHW_Model_Editor")
MHW_MOD3_COLLECTION_TYPE = "MHW_MOD3_COLLECTION"


def get_addon_status():
    module_name = ""
    available = False
    enabled = False
    for module in addon_utils.modules():
        if module.__name__ in MHW_ADDON_MODULES:
            module_name = module.__name__
            available = True
            break
    if module_name:
        _loaded, enabled = addon_utils.check(module_name)
    return {"available": available, "enabled": enabled, "module_name": module_name}


def mhbone_count(armature_object) -> int:
    if armature_object is None or armature_object.type != "ARMATURE":
        return 0
    return sum(1 for bone in armature_object.data.bones if is_mhbone_name(bone.name))


def bonefunction_count(armature_object) -> int:
    if armature_object is None or armature_object.type != "ARMATURE":
        return 0
    return sum(1 for bone in armature_object.data.bones if is_bonefunction_name(bone.name))


def compatible_bone_count(armature_object) -> int:
    return mhbone_count(armature_object) + bonefunction_count(armature_object)


def is_mod3_collection(collection) -> bool:
    if collection is None:
        return False
    return collection.get("~TYPE") == MHW_MOD3_COLLECTION_TYPE or collection.name.endswith(".mod3")


def iter_candidate_armatures():
    candidates = []
    seen = set()
    for collection in bpy.data.collections:
        if not is_mod3_collection(collection):
            continue
        for obj in collection.all_objects:
            if obj.type != "ARMATURE":
                continue
            if obj.name in seen:
                continue
            if compatible_bone_count(obj) > 0:
                candidates.append(obj)
                seen.add(obj.name)
    for obj in bpy.data.objects:
        if obj.type != "ARMATURE" or obj.name in seen:
            continue
        if compatible_bone_count(obj) > 0:
            candidates.append(obj)
            seen.add(obj.name)
    candidates.sort(key=lambda item: (-compatible_bone_count(item), item.name))
    return candidates


def choose_best_armature(context, current=None):
    if current is not None and current.type == "ARMATURE" and compatible_bone_count(current) > 0:
        return current

    active = getattr(context, "object", None)
    if active is not None and active.type == "ARMATURE" and compatible_bone_count(active) > 0:
        return active

    for obj in getattr(context, "selected_objects", ()):
        if obj.type == "ARMATURE" and compatible_bone_count(obj) > 0:
            return obj

    candidates = iter_candidate_armatures()
    return candidates[0] if candidates else None


def get_workspace_summary(context=None, target_armature=None):
    candidates = iter_candidate_armatures()
    return {
        "addon_status": get_addon_status(),
        "candidate_armatures": candidates,
        "candidate_count": len(candidates),
        "target_armature": choose_best_armature(context, target_armature) if context is not None else target_armature,
    }
