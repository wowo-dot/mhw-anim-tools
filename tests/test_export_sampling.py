from __future__ import annotations

import unittest

from blender_adapter.export_sampling import sample_action_for_lmt_export
from blender_adapter.lmt_track_metadata import save_lmt_import_track_bindings


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


class FakeCollection(dict):
    def __init__(self, name: str, collection_type: str = ""):
        super().__init__()
        self.name = name
        if collection_type:
            self["~TYPE"] = collection_type


class FakeArmatureObject:
    def __init__(self, bones, *, name: str = "FakeArmature", users_collection=()):
        self.type = "ARMATURE"
        self.name = name
        self.data = FakeArmatureData(bones)
        self.users_collection = tuple(users_collection)


class FakeFCurve:
    def __init__(self, data_path: str, array_index: int, values_by_frame, *, authored_frames=(), interpolation="LINEAR"):
        self.data_path = data_path
        self.array_index = array_index
        self._values_by_frame = {int(frame): float(value) for frame, value in values_by_frame.items()}
        self.keyframe_points = [
            type(
                "FakeKeyframePoint",
                (),
                {
                    "co": (float(frame), float(self._values_by_frame.get(int(frame), 0.0))),
                    "interpolation": interpolation,
                },
            )()
            for frame in authored_frames
        ]

    def evaluate(self, frame: float) -> float:
        return self._values_by_frame.get(int(frame), 0.0)


class FakeAction(dict):
    def __init__(self, name: str, fcurves, frame_range=(0.0, 0.0)):
        super().__init__()
        self.name = name
        self.fcurves = list(fcurves)
        self.frame_range = frame_range


class ExportSamplingTests(unittest.TestCase):
    def test_samples_root_pose_bone_and_local_bone_tracks(self):
        root = FakeBone("Root")
        local = FakeBone("MhBone_000", parent=root)
        armature = FakeArmatureObject([root, local])
        action = FakeAction(
            "SampleAction",
            [
                FakeFCurve('pose.bones["Root"].location', 0, {0: 0.0, 1: 1.0}),
                FakeFCurve('pose.bones["Root"].location', 1, {0: 0.0, 1: 2.0}),
                FakeFCurve('pose.bones["Root"].location', 2, {0: 0.0, 1: 3.0}),
                FakeFCurve('pose.bones["MhBone_000"].rotation_quaternion', 0, {0: 1.0, 1: 1.0}),
                FakeFCurve('pose.bones["MhBone_000"].rotation_quaternion', 1, {0: 0.0, 1: 0.0}),
                FakeFCurve('pose.bones["MhBone_000"].rotation_quaternion', 2, {0: 0.0, 1: 0.0}),
                FakeFCurve('pose.bones["MhBone_000"].rotation_quaternion', 3, {0: 0.0, 1: 0.1}),
            ],
            frame_range=(0.0, 1.0),
        )

        result = sample_action_for_lmt_export(action, armature)

        self.assertEqual(result.sampled_track_count, 2)
        self.assertEqual(result.skipped_track_count, 0)
        tracks = {(track.bone_id, track.usage): track for track in result.sampled_tracks}
        self.assertIn((-1, 4), tracks)
        self.assertIn((0, 0), tracks)
        self.assertEqual(tracks[(-1, 4)].frames[1].value, (1.0, 2.0, 3.0))
        self.assertEqual(tracks[(0, 0)].frames[0].value, (1.0, 0.0, 0.0, 0.0))

    def test_incomplete_channels_report_warning(self):
        root = FakeBone("Root")
        armature = FakeArmatureObject([root])
        action = FakeAction(
            "BrokenAction",
            [
                FakeFCurve('pose.bones["Root"].location', 0, {0: 0.0}),
                FakeFCurve('pose.bones["Root"].location', 1, {0: 0.0}),
            ],
            frame_range=(0.0, 0.0),
        )

        result = sample_action_for_lmt_export(action, armature)

        self.assertEqual(result.sampled_track_count, 0)
        self.assertEqual(result.skipped_track_count, 1)
        self.assertEqual(result.warning_count, 1)

    def test_mhw_object_root_translation_converts_back_to_engine_space(self):
        mhbone = FakeBone("MhBone_000")
        mod3_collection = FakeCollection("test.mod3", "MHW_MOD3_COLLECTION")
        armature = FakeArmatureObject([mhbone], users_collection=(mod3_collection,))
        action = FakeAction(
            "ObjectRoot",
            [
                FakeFCurve("location", 0, {0: 0.0}),
                FakeFCurve("location", 1, {0: 0.0}),
                FakeFCurve("location", 2, {0: 1.0}),
            ],
            frame_range=(0.0, 0.0),
        )

        result = sample_action_for_lmt_export(action, armature)

        self.assertEqual(result.sampled_track_count, 1)
        track = result.sampled_tracks[0]
        self.assertEqual((track.bone_id, track.usage), (-1, 4))
        self.assertAlmostEqual(track.frames[0].value[0], 0.0, places=6)
        self.assertAlmostEqual(track.frames[0].value[1], 100.0, places=6)
        self.assertAlmostEqual(track.frames[0].value[2], 0.0, places=6)

    def test_local_quaternion_samples_are_normalized_for_export(self):
        bone = FakeBone("MhBone_000")
        armature = FakeArmatureObject([bone])
        action = FakeAction(
            "UnnormalizedQuaternion",
            [
                FakeFCurve('pose.bones["MhBone_000"].rotation_quaternion', 0, {0: 2.0}),
                FakeFCurve('pose.bones["MhBone_000"].rotation_quaternion', 1, {0: 0.0}),
                FakeFCurve('pose.bones["MhBone_000"].rotation_quaternion', 2, {0: 0.0}),
                FakeFCurve('pose.bones["MhBone_000"].rotation_quaternion', 3, {0: 0.0}),
            ],
            frame_range=(0.0, 0.0),
        )

        result = sample_action_for_lmt_export(action, armature)

        self.assertEqual(result.error_count, 0)
        self.assertEqual(result.sampled_track_count, 1)
        self.assertEqual(result.sampled_tracks[0].frames[0].value, (1.0, 0.0, 0.0, 0.0))
        self.assertEqual(result.sampled_tracks[0].raw_frames[0].value, (2.0, 0.0, 0.0, 0.0))

    def test_authored_keyframe_times_are_collected_from_fcurves(self):
        root = FakeBone("Root")
        local = FakeBone("MhBone_000", parent=root)
        armature = FakeArmatureObject([root, local])
        action = FakeAction(
            "AuthoredFrames",
            [
                FakeFCurve('pose.bones["MhBone_000"].location', 0, {0: 0.0, 2: 2.0}, authored_frames=(2,)),
                FakeFCurve('pose.bones["MhBone_000"].location', 1, {0: 0.0, 2: 0.0}, authored_frames=(2,)),
                FakeFCurve('pose.bones["MhBone_000"].location', 2, {0: 0.0, 2: 0.0}, authored_frames=(2,)),
            ],
            frame_range=(0.0, 2.0),
        )

        result = sample_action_for_lmt_export(action, armature)

        self.assertEqual(result.sampled_track_count, 1)
        track = result.sampled_tracks[0]
        self.assertEqual(track.authored_frames, (0, 2))
        self.assertEqual(track.authored_frame_end, 2)

    def test_non_linear_authored_keys_are_flagged(self):
        root = FakeBone("Root")
        local = FakeBone("MhBone_000", parent=root)
        armature = FakeArmatureObject([root, local])
        action = FakeAction(
            "BezierQuat",
            [
                FakeFCurve('pose.bones["MhBone_000"].rotation_quaternion', 0, {0: 1.0, 2: 1.0}, authored_frames=(0, 2), interpolation="BEZIER"),
                FakeFCurve('pose.bones["MhBone_000"].rotation_quaternion', 1, {0: 0.0, 2: 0.0}, authored_frames=(0, 2), interpolation="BEZIER"),
                FakeFCurve('pose.bones["MhBone_000"].rotation_quaternion', 2, {0: 0.0, 2: 0.0}, authored_frames=(0, 2), interpolation="BEZIER"),
                FakeFCurve('pose.bones["MhBone_000"].rotation_quaternion', 3, {0: 0.0, 2: 0.5}, authored_frames=(0, 2), interpolation="BEZIER"),
            ],
            frame_range=(0.0, 2.0),
        )

        result = sample_action_for_lmt_export(action, armature, sample_frames=(0, 2))

        self.assertEqual(result.sampled_track_count, 1)
        self.assertFalse(result.sampled_tracks[0].all_authored_keys_linear)

    def test_samples_raw_duplicate_track_slots_from_custom_properties(self):
        root = FakeBone("Root")
        armature = FakeArmatureObject([root])
        property_name = "lmt_raw_test_a000_t03_b0_u1"
        action = FakeAction(
            "DuplicateRawSlot",
            [
                FakeFCurve(f'["{property_name}"]', 0, {0: 0.0, 2: 2.0}, authored_frames=(0, 2)),
                FakeFCurve(f'["{property_name}"]', 1, {0: 1.0, 2: 3.0}, authored_frames=(0, 2)),
                FakeFCurve(f'["{property_name}"]', 2, {0: 2.0, 2: 4.0}, authored_frames=(0, 2)),
            ],
            frame_range=(0.0, 2.0),
        )
        save_lmt_import_track_bindings(
            action,
            [
                {
                    "track_index": 3,
                    "bone_id": 0,
                    "usage": 1,
                    "buffer_type": 3,
                    "import_mode": "raw_duplicate",
                    "property_name": property_name,
                    "channel_count": 3,
                    "display_name": "T03 Bone 0 Translation",
                    "transform": "location",
                }
            ],
        )

        result = sample_action_for_lmt_export(action, armature)

        self.assertEqual(result.error_count, 0)
        self.assertEqual(result.sampled_track_count, 1)
        track = result.sampled_tracks[0]
        self.assertEqual((track.bone_id, track.usage), (0, 1))
        self.assertEqual(track.source_kind, "raw_duplicate")
        self.assertEqual(track.source_track_index, 3)
        self.assertEqual(track.frames[2].value, (2.0, 3.0, 4.0))


if __name__ == "__main__":
    unittest.main()
