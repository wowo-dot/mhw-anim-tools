from __future__ import annotations

import unittest

from blender_adapter.armature import find_root_bone_name
from blender_adapter.armature import find_track_target_bone_name
from blender_adapter.armature import MHW_ROOT_MOTION_BONE_NAME
from blender_adapter.armature import summarize_track_binding


class FakeBone:
    def __init__(self, name: str, parent=None):
        self.name = name
        self.parent = parent


class FakeBones(dict):
    def __iter__(self):
        return iter(self.values())


class FakeArmatureData:
    def __init__(self, bones):
        self.bones = FakeBones((bone.name, bone) for bone in bones)


class FakeArmatureObject:
    def __init__(self, bones, name: str = "FakeArmature"):
        self.type = "ARMATURE"
        self.name = name
        self.data = FakeArmatureData(bones)


class ArmatureBindingTests(unittest.TestCase):
    def test_find_root_bone_name_prefers_exact_root(self):
        root = FakeBone("Root")
        armature = FakeArmatureObject([root, FakeBone("MhBone_000", parent=root)])
        self.assertEqual(find_root_bone_name(armature), "Root")

    def test_find_track_target_bone_name_accepts_bonefunction_fallback(self):
        root = FakeBone("Root")
        armature = FakeArmatureObject([root, FakeBone("BoneFunction.003", parent=root)])
        bone_name, error = find_track_target_bone_name(armature, bone_id=3, usage=0)
        self.assertEqual(bone_name, "BoneFunction.003")
        self.assertIsNone(error)

    def test_find_root_bone_name_returns_none_for_mhw_style_armature_without_helper(self):
        armature = FakeArmatureObject([FakeBone("MhBone_000"), FakeBone("MhBone_001")])
        self.assertIsNone(find_root_bone_name(armature))

    def test_find_root_bone_name_prefers_synthetic_mhw_root_motion_bone(self):
        helper = FakeBone(MHW_ROOT_MOTION_BONE_NAME)
        armature = FakeArmatureObject(
            [
                helper,
                FakeBone("MhBone_000", parent=helper),
            ]
        )
        self.assertEqual(find_root_bone_name(armature), MHW_ROOT_MOTION_BONE_NAME)

    def test_summarize_track_binding_reports_missing_local_bones(self):
        root = FakeBone("Root")
        armature = FakeArmatureObject([root, FakeBone("MhBone_000", parent=root)])
        summary = summarize_track_binding(
            armature,
            [
                {"usage": 0, "bone_id": 0, "blender_path_hint": "rotation_quaternion"},
                {"usage": 1, "bone_id": 1, "blender_path_hint": "location"},
                {"usage": 4, "bone_id": -1, "blender_path_hint": "location"},
            ],
        )
        self.assertEqual(summary.supported_track_count, 3)
        self.assertEqual(summary.resolved_track_count, 2)
        self.assertEqual(summary.unresolved_track_count, 1)
        self.assertEqual(summary.missing_bone_ids, (1,))
        self.assertTrue(summary.root_required)
        self.assertTrue(summary.root_resolved)
        self.assertEqual(summary.root_target_label, "Root")

    def test_summarize_track_binding_uses_object_root_for_mhw_style_armature_without_helper(self):
        armature = FakeArmatureObject([FakeBone("MhBone_000"), FakeBone("MhBone_001")])
        summary = summarize_track_binding(
            armature,
            [
                {"usage": 4, "bone_id": -1, "blender_path_hint": "location"},
            ],
        )
        self.assertEqual(summary.supported_track_count, 1)
        self.assertEqual(summary.resolved_track_count, 1)
        self.assertTrue(summary.root_required)
        self.assertTrue(summary.root_resolved)
        self.assertEqual(summary.root_target_label, "Armature Object")

    def test_summarize_track_binding_prefers_synthetic_root_helper_when_present(self):
        helper = FakeBone(MHW_ROOT_MOTION_BONE_NAME)
        armature = FakeArmatureObject([helper, FakeBone("MhBone_000", parent=helper)])
        summary = summarize_track_binding(
            armature,
            [
                {"usage": 4, "bone_id": -1, "blender_path_hint": "location"},
            ],
        )
        self.assertEqual(summary.root_target_label, MHW_ROOT_MOTION_BONE_NAME)

    def test_summarize_track_binding_handles_no_armature(self):
        summary = summarize_track_binding(None, [])
        self.assertEqual(summary.supported_track_count, 0)
        self.assertEqual(summary.resolved_track_count, 0)
        self.assertFalse(summary.root_required)
        self.assertFalse(summary.root_resolved)


if __name__ == "__main__":
    unittest.main()
