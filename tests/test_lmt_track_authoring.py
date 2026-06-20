from __future__ import annotations

import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

sys.modules.setdefault("bpy", MagicMock())

from blender_adapter.lmt_track_authoring import add_authored_track_to_action
from blender_adapter.lmt_track_authoring import editable_track_summaries_for_action
from blender_adapter.lmt_track_authoring import remove_authored_track_from_action
from blender_adapter.lmt_track_authoring import session_lmt_action_for_entry
from blender_adapter.lmt_track_metadata import load_lmt_import_track_bindings
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


class FakePoseBone(dict):
    def __init__(self, name: str):
        super().__init__()
        self.name = name


class FakeArmature(dict):
    def __init__(self, bones, *, name: str = "FakeArmature"):
        super().__init__()
        self.type = "ARMATURE"
        self.name = name
        self.data = FakeArmatureData(bones)
        self.pose = SimpleNamespace(bones={bone.name: FakePoseBone(bone.name) for bone in bones})


class FakeFCurves(list):
    def remove(self, fcurve):
        super().remove(fcurve)


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
    def __init__(self, name: str, fcurves=(), frame_range=(0.0, 0.0), **metadata):
        super().__init__(metadata)
        self.name = name
        self.fcurves = FakeFCurves(fcurves)
        self.frame_range = frame_range


class LmtTrackAuthoringTests(unittest.TestCase):
    def test_session_lmt_action_for_entry_matches_source_metadata(self):
        preferred = FakeAction(
            "LMT::sample::005",
            mhw_anim_tools_import_kind="lmt_action",
            mhw_anim_tools_source_lmt="sample.lmt",
            mhw_anim_tools_entry_id=5,
        )
        other = FakeAction(
            "LMT::sample::004",
            mhw_anim_tools_import_kind="lmt_action",
            mhw_anim_tools_source_lmt="sample.lmt",
            mhw_anim_tools_entry_id=4,
        )

        resolved = session_lmt_action_for_entry(
            [other, preferred],
            source_path="sample.lmt",
            entry_id=5,
            preferred_action=preferred,
        )

        self.assertIs(resolved, preferred)

    def test_editable_track_summaries_surface_manual_authored_track(self):
        root = FakeBone("Root")
        local = FakeBone("MhBone_000", parent=root)
        armature = FakeArmature([root, local])
        action = FakeAction(
            "ManualTrack",
            [
                FakeFCurve('pose.bones["MhBone_000"].scale', 0, {0: 1.0, 2: 1.2}, authored_frames=(0, 2)),
                FakeFCurve('pose.bones["MhBone_000"].scale', 1, {0: 1.0, 2: 1.0}, authored_frames=(0, 2)),
                FakeFCurve('pose.bones["MhBone_000"].scale', 2, {0: 1.0, 2: 0.8}, authored_frames=(0, 2)),
            ],
            frame_range=(0.0, 2.0),
        )

        summaries = editable_track_summaries_for_action(
            action,
            armature_object=armature,
            source_track_payload="[]",
        )

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["track_index"], 0)
        self.assertEqual(summaries[0]["source_track_index"], -1)
        self.assertEqual(summaries[0]["buffer_code"], "authored")
        self.assertEqual(summaries[0]["data_path"], 'pose.bones["MhBone_000"].scale')

    def test_add_authored_track_to_action_creates_missing_bone_raw_fallback(self):
        root = FakeBone("Root")
        armature = FakeArmature([root])
        action = FakeAction("AddedRawTrack")

        with patch("blender_adapter.lmt_track_authoring.create_action_fcurves", return_value=[object(), object(), object()]):
            created = add_authored_track_to_action(
                action,
                armature,
                source_path="sample.lmt",
                entry_id=6,
                bone_id=2,
                usage=1,
                source_track_payload="[]",
            )

        self.assertEqual(created["import_mode"], "raw_duplicate")
        bindings = load_lmt_import_track_bindings(action)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0]["fallback_reason"], "missing_bone")
        self.assertIn(bindings[0]["property_name"], armature)

    def test_remove_authored_track_from_action_drops_fcurves_and_binding(self):
        armature = FakeArmature([])
        property_name = "lmt_raw_sample_a006_t00_b2_u1"
        data_path = f'["{property_name}"]'
        action = FakeAction(
            "RemoveRawTrack",
            [
                FakeFCurve(data_path, 0, {0: 0.0}),
                FakeFCurve(data_path, 1, {0: 0.0}),
                FakeFCurve(data_path, 2, {0: 0.0}),
            ],
        )
        armature[property_name] = [0.0, 0.0, 0.0]
        save_lmt_import_track_bindings(
            action,
            [
                {
                    "track_index": 0,
                    "bone_id": 2,
                    "usage": 1,
                    "buffer_type": 1,
                    "import_mode": "raw_duplicate",
                    "property_name": property_name,
                    "channel_count": 3,
                    "display_name": "Missing Bone 002",
                    "transform": "location",
                    "data_path": data_path,
                    "fallback_reason": "missing_bone",
                }
            ],
        )

        removed = remove_authored_track_from_action(
            action,
            armature,
            track_spec={
                "track_index": 0,
                "source_track_index": 0,
                "bone_id": 2,
                "usage": 1,
                "data_path": data_path,
                "channel_count": 3,
            },
        )

        self.assertEqual(removed["removed_fcurves"], 3)
        self.assertEqual(removed["removed_bindings"], 1)
        self.assertEqual(len(action.fcurves), 0)
        self.assertEqual(load_lmt_import_track_bindings(action), [])
        self.assertNotIn(property_name, armature)


if __name__ == "__main__":
    unittest.main()
