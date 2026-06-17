from __future__ import annotations

import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

sys.modules.setdefault("bpy", MagicMock())

from blender_adapter.actions import import_lmt_action_to_armature
from blender_adapter.lmt_track_metadata import load_lmt_import_track_bindings
from blender_adapter.lmt_track_metadata import save_lmt_import_track_bindings
from core.formats.lmt.model import LmtAction
from core.formats.lmt.model import LmtActionHeader
from core.formats.lmt.model import LmtFile
from core.formats.lmt.model import LmtHeader
from core.formats.lmt.model import LmtTrack
from core.formats.lmt.model import LmtTrackHeader


def _track(
    *,
    bone_id: int,
    usage: int,
    buffer_type: int = 1,
) -> LmtTrack:
    return LmtTrack(
        header=LmtTrackHeader(
            buffer_type=buffer_type,
            usage=usage,
            joint_type=0,
            unknown_tag=205,
            bone_id=bone_id,
            weight=1.0,
            buffer_size=0,
            buffer_offset=0,
            basis=(0.0, 0.0, 0.0, 1.0),
            lerp_offset=0,
        ),
        raw_buffer=b"",
        lerp_basis=None,
    )


class _FakeDecodedTrack:
    def __init__(self, track_index: int, *, bone_id: int, usage: int, buffer_type: int = 1):
        self.track_index = track_index
        self.bone_id = bone_id
        self.usage = usage
        self.buffer_type = buffer_type
        self.basis_value = (0.0, 0.0, 0.0)
        self.keyframes = ()
        self.tail_frame = None
        self.tail_value = None
        self.decode_error = None


class _FakeAction(dict):
    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.slots = []


class _FakeSlot:
    def __init__(self, handle: int):
        self.handle = handle


class _FakeBone:
    def __init__(self, name: str, parent=None):
        self.name = name
        self.parent = parent


class _FakeBones(dict):
    def __iter__(self):
        return iter(self.values())


class _FakePoseBone(dict):
    def __init__(self, name: str):
        super().__init__()
        self.name = name


class _FakeArmature(dict):
    def __init__(self, bone_names=()):
        super().__init__()
        self.type = "ARMATURE"
        bones = [_FakeBone(name) for name in bone_names]
        self.data = SimpleNamespace(bones=_FakeBones((bone.name, bone) for bone in bones))
        self.pose = SimpleNamespace(bones={name: _FakePoseBone(name) for name in bone_names})
        self.name = "FakeArmature"


class LmtActionImportTests(unittest.TestCase):
    def test_import_binds_action_slot_after_fcurves_create_legacy_slot(self):
        action = LmtAction(
            header=LmtActionHeader(
                id=0,
                fcurve_offset=0,
                fcurve_count=1,
                frame_count=10,
                loop_frame=-1,
                null0=(0, 0, 0),
                translation=(0.0, 0.0, 0.0, 0.0),
                rotation_lerp=(0.0, 0.0, 0.0, 1.0),
                flags=0,
                null2=b"\x00\x00",
                flags2=0,
                null3=(0, 0, 0, 0, 0),
                timl_offset=0,
            ),
            tracks=(_track(bone_id=0, usage=3),),
        )
        lmt = LmtFile(
            source_name="slot_bind.lmt",
            file_size=0,
            header=LmtHeader(signature=b"LMT\x00", version=95, entry_count=1, unknown=b"\x00" * 8),
            entry_offsets=(32,),
            actions=(action,),
        )
        armature_object = _FakeArmature(bone_names=("MhBone_000",))
        fake_action = _FakeAction("LMT::slot_bind::000")
        fake_animation_data = SimpleNamespace(action=None, action_slot=None, action_slot_handle=0)

        def _create_fcurves(_action, **_kwargs):
            fake_action.slots = [_FakeSlot(777)]
            return [object(), object(), object()]

        with patch(
            "blender_adapter.actions.decode_action_tracks",
            return_value=SimpleNamespace(tracks=(_FakeDecodedTrack(0, bone_id=0, usage=3),)),
        ):
            with patch("blender_adapter.actions.ensure_action", return_value=fake_action):
                with patch(
                    "blender_adapter.actions.ensure_armature_animation_data",
                    return_value=fake_animation_data,
                ):
                    with patch(
                        "blender_adapter.actions.create_transform_fcurves",
                        side_effect=_create_fcurves,
                    ):
                        with patch(
                            "blender_adapter.actions.create_action_fcurves",
                            side_effect=_create_fcurves,
                        ):
                            result = import_lmt_action_to_armature(
                                lmt,
                                0,
                                armature_object,
                                source_path="slot_bind.lmt",
                            )

        self.assertEqual(result.error_count, 0)
        self.assertIs(fake_animation_data.action, fake_action)
        self.assertIs(fake_animation_data.action_slot, fake_action.slots[0])
        self.assertEqual(fake_animation_data.action_slot_handle, 777)

    def test_import_warns_when_source_action_has_duplicate_raw_track_identities(self):
        action = LmtAction(
            header=LmtActionHeader(
                id=0,
                fcurve_offset=0,
                fcurve_count=2,
                frame_count=10,
                loop_frame=-1,
                null0=(0, 0, 0),
                translation=(0.0, 0.0, 0.0, 0.0),
                rotation_lerp=(0.0, 0.0, 0.0, 1.0),
                flags=0,
                null2=b"\x00\x00",
                flags2=0,
                null3=(0, 0, 0, 0, 0),
                timl_offset=0,
            ),
            tracks=(
                _track(bone_id=0, usage=1),
                _track(bone_id=0, usage=1),
            ),
        )
        lmt = LmtFile(
            source_name="duplicate.lmt",
            file_size=0,
            header=LmtHeader(signature=b"LMT\x00", version=95, entry_count=1, unknown=b"\x00" * 8),
            entry_offsets=(32,),
            actions=(action,),
        )
        armature_object = _FakeArmature(bone_names=("MhBone_000",))
        fake_action = _FakeAction("LMT::duplicate::000")
        fake_animation_data = SimpleNamespace(action=None)

        with patch(
            "blender_adapter.actions.decode_action_tracks",
            return_value=SimpleNamespace(
                tracks=(
                    _FakeDecodedTrack(0, bone_id=0, usage=1),
                    _FakeDecodedTrack(1, bone_id=0, usage=1),
                )
            ),
        ):
            with patch("blender_adapter.actions.ensure_action", return_value=fake_action):
                with patch(
                    "blender_adapter.actions.ensure_armature_animation_data",
                    return_value=fake_animation_data,
                ):
                    with patch(
                        "blender_adapter.actions.create_action_fcurves",
                        return_value=[object(), object(), object()],
                    ):
                        result = import_lmt_action_to_armature(
                            lmt,
                            0,
                            armature_object,
                            source_path="duplicate.lmt",
                        )

        self.assertTrue(
            any(
                "raw duplicate pose-bone or armature channels" in diagnostic.message
                for diagnostic in result.diagnostics
            )
        )
        self.assertTrue(fake_action["mhw_anim_tools_source_has_duplicate_track_identities"])
        self.assertIn("bone_id=0, usage=1, count=2", fake_action["mhw_anim_tools_source_duplicate_track_identities"])
        bindings = load_lmt_import_track_bindings(fake_action)
        self.assertEqual(len(bindings), 2)
        self.assertTrue(all(binding["import_mode"] == "raw_duplicate" for binding in bindings))
        self.assertTrue(all(binding["display_name"].startswith("Raw Duplicate ") for binding in bindings))
        self.assertTrue(all(binding["owner_kind"] == "bone" for binding in bindings))
        self.assertTrue(all(binding["owner_name"] == "MhBone_000" for binding in bindings))
        self.assertTrue(all(binding["action_group"] == "MhBone_000 / LMT Raw" for binding in bindings))
        self.assertTrue(all(binding["data_path"].startswith('pose.bones["MhBone_000"]["') for binding in bindings))
        self.assertIn(bindings[0]["property_name"], armature_object.pose.bones["MhBone_000"])

    def test_import_falls_back_to_armature_object_when_duplicate_pose_target_is_missing(self):
        action = LmtAction(
            header=LmtActionHeader(
                id=0,
                fcurve_offset=0,
                fcurve_count=2,
                frame_count=10,
                loop_frame=-1,
                null0=(0, 0, 0),
                translation=(0.0, 0.0, 0.0, 0.0),
                rotation_lerp=(0.0, 0.0, 0.0, 1.0),
                flags=0,
                null2=b"\x00\x00",
                flags2=0,
                null3=(0, 0, 0, 0, 0),
                timl_offset=0,
            ),
            tracks=(
                _track(bone_id=0, usage=1),
                _track(bone_id=0, usage=1),
            ),
        )
        lmt = LmtFile(
            source_name="duplicate.lmt",
            file_size=0,
            header=LmtHeader(signature=b"LMT\x00", version=95, entry_count=1, unknown=b"\x00" * 8),
            entry_offsets=(32,),
            actions=(action,),
        )
        armature_object = _FakeArmature()
        fake_action = _FakeAction("LMT::duplicate::000")
        fake_animation_data = SimpleNamespace(action=None)

        with patch(
            "blender_adapter.actions.decode_action_tracks",
            return_value=SimpleNamespace(
                tracks=(
                    _FakeDecodedTrack(0, bone_id=0, usage=1),
                    _FakeDecodedTrack(1, bone_id=0, usage=1),
                )
            ),
        ):
            with patch("blender_adapter.actions.ensure_action", return_value=fake_action):
                with patch(
                    "blender_adapter.actions.ensure_armature_animation_data",
                    return_value=fake_animation_data,
                ):
                    with patch(
                        "blender_adapter.actions.create_action_fcurves",
                        return_value=[object(), object(), object()],
                    ):
                        result = import_lmt_action_to_armature(
                            lmt,
                            0,
                            armature_object,
                            source_path="duplicate.lmt",
                        )

        bindings = load_lmt_import_track_bindings(fake_action)
        self.assertEqual(bindings[0]["owner_kind"], "object")
        self.assertEqual(bindings[0]["data_path"], f'["{bindings[0]["property_name"]}"]')
        self.assertIn(bindings[0]["property_name"], armature_object)
        self.assertTrue(any("armature-attached raw slot" in diagnostic.message for diagnostic in result.diagnostics))

    def test_reimport_clears_legacy_armature_raw_slot_before_migrating_to_pose_bone(self):
        action = LmtAction(
            header=LmtActionHeader(
                id=0,
                fcurve_offset=0,
                fcurve_count=2,
                frame_count=10,
                loop_frame=-1,
                null0=(0, 0, 0),
                translation=(0.0, 0.0, 0.0, 0.0),
                rotation_lerp=(0.0, 0.0, 0.0, 1.0),
                flags=0,
                null2=b"\x00\x00",
                flags2=0,
                null3=(0, 0, 0, 0, 0),
                timl_offset=0,
            ),
            tracks=(
                _track(bone_id=0, usage=1),
                _track(bone_id=0, usage=1),
            ),
        )
        lmt = LmtFile(
            source_name="duplicate.lmt",
            file_size=0,
            header=LmtHeader(signature=b"LMT\x00", version=95, entry_count=1, unknown=b"\x00" * 8),
            entry_offsets=(32,),
            actions=(action,),
        )
        armature_object = _FakeArmature(bone_names=("MhBone_000",))
        fake_action = _FakeAction("LMT::duplicate::000")
        fake_animation_data = SimpleNamespace(action=None)
        legacy_property_name = "lmt_raw_duplicate_a000_t00_b0_u1"
        armature_object[legacy_property_name] = [9.0, 9.0, 9.0]
        save_lmt_import_track_bindings(
            fake_action,
            [
                {
                    "track_index": 0,
                    "bone_id": 0,
                    "usage": 1,
                    "buffer_type": 3,
                    "import_mode": "raw_duplicate",
                    "property_name": legacy_property_name,
                    "channel_count": 3,
                    "display_name": "Legacy Raw Duplicate",
                    "transform": "location",
                }
            ],
        )

        with patch(
            "blender_adapter.actions.decode_action_tracks",
            return_value=SimpleNamespace(
                tracks=(
                    _FakeDecodedTrack(0, bone_id=0, usage=1),
                    _FakeDecodedTrack(1, bone_id=0, usage=1),
                )
            ),
        ):
            with patch("blender_adapter.actions.ensure_action", return_value=fake_action):
                with patch(
                    "blender_adapter.actions.ensure_armature_animation_data",
                    return_value=fake_animation_data,
                ):
                    with patch(
                        "blender_adapter.actions.create_action_fcurves",
                        return_value=[object(), object(), object()],
                    ):
                        result = import_lmt_action_to_armature(
                            lmt,
                            0,
                            armature_object,
                            source_path="duplicate.lmt",
                        )

        self.assertNotIn(legacy_property_name, armature_object)
        bindings = load_lmt_import_track_bindings(fake_action)
        self.assertIn(bindings[0]["property_name"], armature_object.pose.bones["MhBone_000"])
        self.assertTrue(any("stale raw duplicate-slot" in diagnostic.message for diagnostic in result.diagnostics))


if __name__ == "__main__":
    unittest.main()
