from __future__ import annotations

import unittest

from blender_adapter.armature import find_root_bone_name
from blender_adapter.armature import find_track_target_bone_name
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

    def test_find_root_bone_name_promotes_mhbone_zero_for_mhw_style_armature(self):
        armature = FakeArmatureObject([FakeBone("MhBone_000"), FakeBone("MhBone_001")])
        self.assertEqual(find_root_bone_name(armature), "MhBone_000")

    def test_find_root_bone_name_prefers_bonefunction_zero_when_mhbone_zero_missing(self):
        armature = FakeArmatureObject([FakeBone("BoneFunction.000"), FakeBone("BoneFunction.001")])
        self.assertEqual(find_root_bone_name(armature), "BoneFunction.000")

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

    def test_summarize_track_binding_uses_mhbone_zero_root_for_mhw_style_armature(self):
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
        self.assertEqual(summary.root_target_label, "MhBone_000")

    def test_summarize_track_binding_handles_no_armature(self):
        summary = summarize_track_binding(None, [])
        self.assertEqual(summary.supported_track_count, 0)
        self.assertEqual(summary.resolved_track_count, 0)
        self.assertFalse(summary.root_required)
        self.assertFalse(summary.root_resolved)


if __name__ == "__main__":
    unittest.main()
