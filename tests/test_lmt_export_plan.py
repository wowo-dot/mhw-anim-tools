from __future__ import annotations

import unittest

from core.formats.lmt.export_plan import plan_reconstructed_action_export
from core.formats.lmt.reconstructed import LmtReconstructedAction
from core.formats.lmt.reconstructed import LmtReconstructedKeyframe
from core.formats.lmt.reconstructed import LmtReconstructedTrack


class LmtExportPlanTests(unittest.TestCase):
    def test_basis_only_vector_track_uses_basis_buffer(self):
        action = LmtReconstructedAction(
            action_name="BasisOnly",
            frame_start=0,
            frame_end=0,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=0,
                    usage=1,
                    basis_value=(0.0, 0.0, 0.0),
                ),
            ),
        )

        plan = plan_reconstructed_action_export(action)

        self.assertEqual(plan.error_count, 0)
        self.assertEqual(plan.tracks[0].buffer_type, 1)
        self.assertTrue(plan.tracks[0].supported)

    def test_keyed_vector_track_uses_float_key_buffer(self):
        action = LmtReconstructedAction(
            action_name="VectorKeys",
            frame_start=0,
            frame_end=4,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=2,
                    usage=1,
                    basis_value=(0.0, 0.0, 0.0),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=2, value=(1.0, 0.0, 0.0)),
                    ),
                ),
            ),
        )

        plan = plan_reconstructed_action_export(action)

        self.assertEqual(plan.tracks[0].buffer_type, 3)
        self.assertTrue(plan.tracks[0].inject_leading_basis_keyframe)
        self.assertIn("Writer must inject a leading hold key at frame 1.", plan.tracks[0].notes)

    def test_basis_only_quaternion_track_uses_basis_quaternion_buffer(self):
        action = LmtReconstructedAction(
            action_name="QuatBasis",
            frame_start=0,
            frame_end=0,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=4,
                    usage=0,
                    basis_value=(1.0, 0.0, 0.0, 0.0),
                ),
            ),
        )

        plan = plan_reconstructed_action_export(action)

        self.assertEqual(plan.tracks[0].buffer_type, 2)
        self.assertTrue(plan.tracks[0].supported)

    def test_root_translation_tail_stays_in_action_header(self):
        action = LmtReconstructedAction(
            action_name="RootTail",
            frame_start=0,
            frame_end=10,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=-1,
                    usage=4,
                    basis_value=(0.0, 0.0, 0.0),
                    tail_frame=10,
                    tail_value=(5.0, 0.0, 0.0),
                ),
            ),
        )

        plan = plan_reconstructed_action_export(action)

        self.assertEqual(plan.error_count, 0)
        self.assertTrue(plan.tracks[0].tail_in_action_header)
        self.assertIn("Tail value must be written to the action header.", plan.tracks[0].notes)

    def test_non_normalized_quaternion_track_is_rejected(self):
        action = LmtReconstructedAction(
            action_name="BadQuat",
            frame_start=0,
            frame_end=1,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=0,
                    basis_value=(2.0, 0.0, 0.0, 0.0),
                ),
            ),
        )

        plan = plan_reconstructed_action_export(action)

        self.assertEqual(plan.error_count, 1)
        self.assertFalse(plan.tracks[0].supported)

    def test_duplicate_track_identity_is_rejected(self):
        action = LmtReconstructedAction(
            action_name="DuplicateIdentity",
            frame_start=0,
            frame_end=1,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=0,
                    usage=1,
                    basis_value=(0.0, 0.0, 0.0),
                ),
                LmtReconstructedTrack(
                    bone_id=0,
                    usage=1,
                    basis_value=(1.0, 0.0, 0.0),
                ),
            ),
        )

        plan = plan_reconstructed_action_export(action)

        self.assertEqual(plan.error_count, 2)
        self.assertFalse(plan.tracks[0].supported)
        self.assertFalse(plan.tracks[1].supported)

    def test_duplicate_track_identity_is_supported_with_source_track_slots(self):
        action = LmtReconstructedAction(
            action_name="DuplicateIdentitySlots",
            frame_start=0,
            frame_end=1,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=0,
                    usage=1,
                    basis_value=(0.0, 0.0, 0.0),
                    source_track_index=0,
                ),
                LmtReconstructedTrack(
                    bone_id=0,
                    usage=1,
                    basis_value=(1.0, 0.0, 0.0),
                    source_track_index=1,
                ),
            ),
        )

        plan = plan_reconstructed_action_export(
            action,
            track_metadata_by_index={
                0: {"buffer_type": 1},
                1: {"buffer_type": 1},
            },
        )

        self.assertEqual(plan.error_count, 0)
        self.assertTrue(all(track.supported for track in plan.tracks))

    def test_invalid_translation_dimension_is_rejected(self):
        action = LmtReconstructedAction(
            action_name="BadTranslation",
            frame_start=0,
            frame_end=1,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=1,
                    usage=1,
                    basis_value=(0.0, 0.0, 0.0, 0.0),
                ),
            ),
        )

        plan = plan_reconstructed_action_export(action)

        self.assertEqual(plan.error_count, 1)
        self.assertFalse(plan.tracks[0].supported)

    def test_q14_quaternion_delta_overflow_is_visible_during_planning(self):
        action = LmtReconstructedAction(
            action_name="HugeQuaternionDelta",
            frame_start=0,
            frame_end=300,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=0,
                    basis_value=(1.0, 0.0, 0.0, 0.0),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=300, value=(0.9238795, 0.3826834, 0.0, 0.0)),
                    ),
                ),
            ),
        )

        plan = plan_reconstructed_action_export(action)

        self.assertEqual(plan.error_count, 1)
        self.assertFalse(plan.tracks[0].supported)
        self.assertIn("255-frame limit", plan.diagnostics[0].message)

    def test_source_u8_vector_lerp_is_preserved_when_values_fit(self):
        action = LmtReconstructedAction(
            action_name="SourceVectorLerp",
            frame_start=0,
            frame_end=8,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=1,
                    basis_value=(0.0, 0.0, 0.0),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=1, value=(-1.0, 12.0, 106.0)),
                        LmtReconstructedKeyframe(frame=4, value=(1.0, 10.0, 101.5)),
                    ),
                ),
            ),
        )

        plan = plan_reconstructed_action_export(
            action,
            track_metadata_by_identity={
                (3, 1): {
                    "buffer_type": 5,
                    "lerp_mult": (2.0, 4.0, 6.0, 1.0),
                    "lerp_add": (-1.0, 10.0, 100.0, 0.0),
                }
            },
        )

        self.assertEqual(plan.error_count, 0)
        self.assertEqual(plan.warning_count, 0)
        self.assertEqual(plan.tracks[0].buffer_type, 5)
        self.assertEqual(plan.tracks[0].lerp_mult, (2.0, 4.0, 6.0, 1.0))
        self.assertEqual(plan.tracks[0].lerp_add, (-1.0, 10.0, 100.0, 0.0))

    def test_source_u8_vector_lerp_promotes_to_u16_when_delta_overflows(self):
        action = LmtReconstructedAction(
            action_name="PromoteVectorLerp",
            frame_start=0,
            frame_end=300,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=1,
                    basis_value=(-1.0, 12.0, 106.0),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=300, value=(-1.0, 12.0, 106.0)),
                    ),
                ),
            ),
        )

        plan = plan_reconstructed_action_export(
            action,
            track_metadata_by_identity={
                (3, 1): {
                    "buffer_type": 5,
                    "lerp_mult": (2.0, 4.0, 6.0, 1.0),
                    "lerp_add": (-1.0, 10.0, 100.0, 0.0),
                }
            },
        )

        self.assertEqual(plan.error_count, 0)
        self.assertEqual(plan.warning_count, 1)
        self.assertEqual(plan.tracks[0].buffer_type, 4)
        self.assertIn("16-bit vector lerp", plan.diagnostics[0].message)

    def test_source_q7_quaternion_lerp_is_preserved_when_values_fit(self):
        action = LmtReconstructedAction(
            action_name="SourceQuatLerp",
            frame_start=0,
            frame_end=8,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=0,
                    basis_value=(1.0, 0.0, 0.0, 0.0),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=1, value=(0.0, 1.0, 0.0, 0.0)),
                    ),
                ),
            ),
        )

        plan = plan_reconstructed_action_export(
            action,
            track_metadata_by_identity={
                (3, 0): {
                    "buffer_type": 7,
                    "lerp_mult": (1.0, 1.0, 1.0, 1.0),
                    "lerp_add": (0.0, 0.0, 0.0, 0.0),
                }
            },
        )

        self.assertEqual(plan.error_count, 0)
        self.assertEqual(plan.warning_count, 0)
        self.assertEqual(plan.tracks[0].buffer_type, 7)
        self.assertEqual(plan.tracks[0].lerp_mult, (1.0, 1.0, 1.0, 1.0))

    def test_source_q7_quaternion_lerp_promotes_to_q11_lerp(self):
        action = LmtReconstructedAction(
            action_name="PromoteQuatLerp",
            frame_start=0,
            frame_end=8,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=0,
                    basis_value=(1.0, 0.0, 0.0, 0.0),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=1, value=(0.70710678, 0.70710678, 0.0, 0.0)),
                    ),
                ),
            ),
        )

        plan = plan_reconstructed_action_export(
            action,
            track_metadata_by_identity={
                (3, 0): {
                    "buffer_type": 7,
                    "lerp_mult": (1.0, 1.0, 1.0, 1.0),
                    "lerp_add": (0.0, 0.0, 0.0, 0.0),
                }
            },
        )

        self.assertEqual(plan.error_count, 0)
        self.assertEqual(plan.warning_count, 1)
        self.assertEqual(plan.tracks[0].buffer_type, 14)
        self.assertIn("11-bit quaternion lerp", plan.diagnostics[0].message)

    def test_source_q7_quaternion_lerp_falls_back_to_q14_keys_when_delta_overflows(self):
        action = LmtReconstructedAction(
            action_name="QuatLerpFallback",
            frame_start=0,
            frame_end=40,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=0,
                    basis_value=(1.0, 0.0, 0.0, 0.0),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=40, value=(0.0, 1.0, 0.0, 0.0)),
                    ),
                ),
            ),
        )

        plan = plan_reconstructed_action_export(
            action,
            track_metadata_by_identity={
                (3, 0): {
                    "buffer_type": 7,
                    "lerp_mult": (1.0, 1.0, 1.0, 1.0),
                    "lerp_add": (0.0, 0.0, 0.0, 0.0),
                }
            },
        )

        self.assertEqual(plan.error_count, 0)
        self.assertEqual(plan.warning_count, 1)
        self.assertEqual(plan.tracks[0].buffer_type, 6)
        self.assertIn("falling back to q14 quaternion keys", plan.diagnostics[0].message.lower())

    def test_preserve_source_identity_suppresses_reencode_warning(self):
        action = LmtReconstructedAction(
            action_name="PreserveSourceQuatLerp",
            frame_start=0,
            frame_end=40,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=0,
                    basis_value=(1.0, 0.0, 0.0, 0.0),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=40, value=(0.0, 1.0, 0.0, 0.0)),
                    ),
                ),
            ),
        )

        plan = plan_reconstructed_action_export(
            action,
            track_metadata_by_identity={
                (3, 0): {
                    "buffer_type": 7,
                    "lerp_mult": (1.0, 1.0, 1.0, 1.0),
                    "lerp_add": (0.0, 0.0, 0.0, 0.0),
                }
            },
            preserve_source_identities={(3, 0)},
        )

        self.assertEqual(plan.error_count, 0)
        self.assertEqual(plan.warning_count, 0)
        self.assertTrue(plan.tracks[0].preserve_source_raw)
        self.assertEqual(plan.tracks[0].buffer_type, 7)

    def test_raw_sensitive_source_quaternion_lerp_allows_non_normalized_values(self):
        action = LmtReconstructedAction(
            action_name="RawSourceQuatLerp",
            frame_start=0,
            frame_end=8,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=0,
                    basis_value=(1.01, 0.0, 0.0, 0.0),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=1, value=(1.02, 0.01, 0.0, 0.0)),
                    ),
                ),
            ),
        )

        plan = plan_reconstructed_action_export(
            action,
            track_metadata_by_identity={
                (3, 0): {
                    "buffer_type": 14,
                    "lerp_mult": (2.0, 2.0, 2.0, 2.0),
                    "lerp_add": (0.0, 0.0, 0.0, 0.0),
                }
            },
            raw_quaternion_source_identities={(3, 0)},
        )

        self.assertEqual(plan.error_count, 0)
        self.assertEqual(plan.tracks[0].buffer_type, 14)
        self.assertIn("raw source-aware quaternion key values", " ".join(plan.tracks[0].notes).lower())

    def test_raw_sensitive_source_q9_quaternion_tolerates_small_basis_drift(self):
        action = LmtReconstructedAction(
            action_name="RawSourceQuatQ9Tolerance",
            frame_start=0,
            frame_end=1,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=15,
                    usage=0,
                    basis_value=(1.0, 0.0, 0.0, 0.0),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=1, value=(0.993962, -0.035516, -0.000105, 0.002003)),
                    ),
                ),
            ),
        )

        plan = plan_reconstructed_action_export(
            action,
            track_metadata_by_identity={
                (15, 0): {
                    "buffer_type": 15,
                    "lerp_mult": (
                        0.06990372389554977,
                        0.008656306192278862,
                        0.16556043922901154,
                        0.013800382614135742,
                    ),
                    "lerp_add": (
                        -0.06990372389554977,
                        0.0,
                        -0.16556043922901154,
                        0.9861996173858643,
                    ),
                }
            },
            raw_quaternion_source_identities={(15, 0)},
        )

        self.assertEqual(plan.error_count, 0)
        self.assertEqual(plan.tracks[0].buffer_type, 15)
        self.assertTrue(plan.tracks[0].supported)

    def test_raw_sensitive_source_quaternion_lerp_refuses_q14_fallback(self):
        action = LmtReconstructedAction(
            action_name="RawSourceQuatFallbackBlocked",
            frame_start=0,
            frame_end=8,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=0,
                    basis_value=(1.2, 0.0, 0.0, 0.0),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=1, value=(1.2, 0.0, 0.0, 0.0)),
                    ),
                ),
            ),
        )

        plan = plan_reconstructed_action_export(
            action,
            track_metadata_by_identity={
                (3, 0): {
                    "buffer_type": 7,
                    "lerp_mult": (1.0, 1.0, 1.0, 1.0),
                    "lerp_add": (0.0, 0.0, 0.0, 0.0),
                }
            },
            raw_quaternion_source_identities={(3, 0)},
        )

        self.assertEqual(plan.error_count, 1)
        self.assertFalse(plan.tracks[0].supported)
        self.assertIn("refusing normalized q14 fallback", plan.diagnostics[0].message.lower())


if __name__ == "__main__":
    unittest.main()
