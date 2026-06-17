from __future__ import annotations

import unittest

from core.diagnostics.errors import ValidationError
from core.formats.lmt.decoder import decode_action_tracks
from core.formats.lmt.reader import read_lmt_bytes
from core.formats.lmt.reconstructed import LmtReconstructedAction
from core.formats.lmt.reconstructed import LmtReconstructedKeyframe
from core.formats.lmt.reconstructed import LmtReconstructedTrack
from core.formats.lmt.validation import validate_lmt
from core.formats.lmt.writer import write_lmt_bytes


class LmtWriterTests(unittest.TestCase):
    def test_write_basis_only_root_translation_tail_roundtrips(self):
        source = LmtReconstructedAction(
            action_name="RootTranslation",
            frame_start=0,
            frame_end=10,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=-1,
                    usage=4,
                    basis_value=(0.0, 0.0, 0.0),
                    tail_frame=10,
                    tail_value=(5.0, 6.0, 7.0),
                ),
            ),
        )

        payload = write_lmt_bytes(source)
        lmt = read_lmt_bytes(payload, source_name="roundtrip-root-translation.lmt")
        report = validate_lmt(lmt)
        decoded = decode_action_tracks(lmt.actions[0], strict=True)
        track = decoded.tracks[0]

        self.assertEqual(report.error_count, 0)
        self.assertEqual(track.basis_value, (0.0, 0.0, 0.0))
        self.assertEqual(track.tail_frame, 10)
        self.assertEqual(track.tail_value, (5.0, 6.0, 7.0))
        self.assertEqual(track.keyframes, ())

    def test_write_basis_only_action_preserves_nonzero_duration(self):
        source = LmtReconstructedAction(
            action_name="BasisOnlyDuration",
            frame_start=0,
            frame_end=20,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=1,
                    basis_value=(0.5, 1.0, 1.5),
                ),
            ),
        )

        payload = write_lmt_bytes(source)
        lmt = read_lmt_bytes(payload, source_name="basis-only-duration.lmt")

        self.assertEqual(lmt.actions[0].header.frame_count, 20)

    def test_write_preserves_explicit_source_header_version_and_unknown_bytes(self):
        source = LmtReconstructedAction(
            action_name="HeaderMetadata",
            frame_start=0,
            frame_end=0,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=1,
                    basis_value=(0.5, 1.0, 1.5),
                ),
            ),
        )

        payload = write_lmt_bytes(source, version=88, header_unknown=b"ABCDEFGH")
        lmt = read_lmt_bytes(payload, source_name="header-metadata.lmt")

        self.assertEqual(lmt.header.version, 88)
        self.assertEqual(lmt.header.unknown, b"ABCDEFGH")

    def test_write_float_vector_key_track_roundtrips(self):
        source = LmtReconstructedAction(
            action_name="VectorKeys",
            frame_start=0,
            frame_end=6,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=1,
                    basis_value=(0.5, 1.0, 1.5),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=0, value=(1.25, 2.5, -3.75)),
                        LmtReconstructedKeyframe(frame=5, value=(4.0, 5.0, 6.0)),
                    ),
                ),
            ),
        )

        payload = write_lmt_bytes(source)
        lmt = read_lmt_bytes(payload, source_name="roundtrip-vector-keys.lmt")
        decoded = decode_action_tracks(lmt.actions[0], strict=True)
        track = decoded.tracks[0]

        self.assertEqual(track.basis_value, (0.5, 1.0, 1.5))
        self.assertEqual([sample.frame for sample in track.keyframes], [0, 5])
        self.assertEqual(track.keyframes[0].value, (1.25, 2.5, -3.75))
        self.assertEqual(track.keyframes[1].value, (4.0, 5.0, 6.0))

    def test_write_injects_frame_zero_hold_for_delayed_local_key(self):
        source = LmtReconstructedAction(
            action_name="DelayedKey",
            frame_start=0,
            frame_end=3,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=1,
                    basis_value=(0.5, 1.0, 1.5),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=2, value=(4.0, 5.0, 6.0)),
                    ),
                ),
            ),
        )

        payload = write_lmt_bytes(source)
        lmt = read_lmt_bytes(payload, source_name="delayed-key.lmt")
        decoded = decode_action_tracks(lmt.actions[0], strict=True)
        track = decoded.tracks[0]

        self.assertEqual([sample.frame for sample in track.keyframes], [0, 2])
        self.assertEqual(track.keyframes[0].value, (0.5, 1.0, 1.5))
        self.assertEqual(track.keyframes[1].value, (4.0, 5.0, 6.0))

    def test_write_q14_quaternion_track_roundtrips(self):
        keyed_rotation = (0.9238795, 0.3826834, 0.0, 0.0)
        source = LmtReconstructedAction(
            action_name="QuaternionKeys",
            frame_start=0,
            frame_end=9,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=0,
                    basis_value=(1.0, 0.0, 0.0, 0.0),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=0, value=keyed_rotation),
                    ),
                ),
            ),
        )

        payload = write_lmt_bytes(source)
        lmt = read_lmt_bytes(payload, source_name="roundtrip-q14.lmt")
        decoded = decode_action_tracks(lmt.actions[0], strict=True)
        track = decoded.tracks[0]

        self.assertEqual(track.keyframes[0].frame, 0)
        self.assertAlmostEqual(track.keyframes[0].value[0], keyed_rotation[0], delta=1e-4)
        self.assertAlmostEqual(track.keyframes[0].value[1], keyed_rotation[1], delta=1e-4)
        self.assertAlmostEqual(track.keyframes[0].value[2], 0.0, delta=1e-4)
        self.assertAlmostEqual(track.keyframes[0].value[3], 0.0, delta=1e-4)

    def test_write_q14_quaternion_with_negative_component_roundtrips(self):
        keyed_rotation = (0.9238795, -0.3826834, 0.0, 0.0)
        source = LmtReconstructedAction(
            action_name="NegativeQuaternion",
            frame_start=0,
            frame_end=9,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=0,
                    basis_value=(1.0, 0.0, 0.0, 0.0),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=0, value=keyed_rotation),
                    ),
                ),
            ),
        )

        payload = write_lmt_bytes(source)
        lmt = read_lmt_bytes(payload, source_name="negative-q14.lmt")
        decoded = decode_action_tracks(lmt.actions[0], strict=True)
        track = decoded.tracks[0]

        self.assertAlmostEqual(track.keyframes[0].value[0], keyed_rotation[0], delta=1e-4)
        self.assertAlmostEqual(track.keyframes[0].value[1], keyed_rotation[1], delta=2e-4)
        self.assertAlmostEqual(track.keyframes[0].value[2], 0.0, delta=1e-4)
        self.assertAlmostEqual(track.keyframes[0].value[3], 0.0, delta=1e-4)

    def test_write_q14_rejects_delta_over_255(self):
        source = LmtReconstructedAction(
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

        with self.assertRaisesRegex(ValidationError, "exceeds the 255-frame limit"):
            write_lmt_bytes(source)

    def test_write_rejects_duplicate_track_identity(self):
        source = LmtReconstructedAction(
            action_name="DuplicateIdentity",
            frame_start=0,
            frame_end=0,
            tracks=(
                LmtReconstructedTrack(bone_id=0, usage=1, basis_value=(0.0, 0.0, 0.0)),
                LmtReconstructedTrack(bone_id=0, usage=1, basis_value=(1.0, 0.0, 0.0)),
            ),
        )

        with self.assertRaises(ValidationError):
            write_lmt_bytes(source)

    def test_write_supports_duplicate_track_identity_with_source_track_slots(self):
        source = LmtReconstructedAction(
            action_name="DuplicateIdentitySlots",
            frame_start=0,
            frame_end=0,
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

        payload = write_lmt_bytes(
            source,
            track_metadata_by_index={
                0: {"buffer_type": 1},
                1: {"buffer_type": 1},
            },
        )
        lmt = read_lmt_bytes(payload, source_name="duplicate-slots.lmt")
        decoded = decode_action_tracks(lmt.actions[0], strict=True)

        self.assertEqual(len(decoded.tracks), 2)
        self.assertEqual(decoded.tracks[0].basis_value, (0.0, 0.0, 0.0))
        self.assertEqual(decoded.tracks[1].basis_value, (1.0, 0.0, 0.0))

    def test_write_source_u8_vector_lerp_roundtrips(self):
        first_value = (-1.0, 12.007843137254902, 106.0)
        second_value = (1.0, 10.0, 101.50588235294117)
        source = LmtReconstructedAction(
            action_name="VectorLerp8",
            frame_start=0,
            frame_end=8,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=1,
                    basis_value=(0.0, 0.0, 0.0),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=0, value=first_value),
                        LmtReconstructedKeyframe(frame=3, value=second_value),
                    ),
                ),
            ),
        )

        payload = write_lmt_bytes(
            source,
            track_metadata_by_identity={
                (3, 1): {
                    "buffer_type": 5,
                    "lerp_mult": (2.0, 4.0, 6.0, 1.0),
                    "lerp_add": (-1.0, 10.0, 100.0, 0.0),
                }
            },
        )
        lmt = read_lmt_bytes(payload, source_name="vector-lerp-u8.lmt")
        decoded = decode_action_tracks(lmt.actions[0], strict=True)
        track = decoded.tracks[0]

        self.assertEqual(track.buffer_type, 5)
        self.assertEqual(track.keyframes[0].frame, 0)
        self.assertEqual(track.keyframes[1].frame, 3)
        self.assertAlmostEqual(track.keyframes[0].value[0], first_value[0], delta=1e-4)
        self.assertAlmostEqual(track.keyframes[0].value[1], first_value[1], delta=1e-4)
        self.assertAlmostEqual(track.keyframes[0].value[2], first_value[2], delta=1e-4)
        self.assertAlmostEqual(track.keyframes[1].value[0], second_value[0], delta=1e-4)
        self.assertAlmostEqual(track.keyframes[1].value[1], second_value[1], delta=1e-4)
        self.assertAlmostEqual(track.keyframes[1].value[2], second_value[2], delta=1e-4)

    def test_write_source_u8_vector_lerp_promotes_to_u16(self):
        first_value = (-1.0, 12.007843137254902, 106.0)
        source = LmtReconstructedAction(
            action_name="VectorLerpPromote",
            frame_start=0,
            frame_end=300,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=1,
                    basis_value=first_value,
                    keyframes=(
                        LmtReconstructedKeyframe(frame=300, value=first_value),
                    ),
                ),
            ),
        )

        payload = write_lmt_bytes(
            source,
            track_metadata_by_identity={
                (3, 1): {
                    "buffer_type": 5,
                    "lerp_mult": (2.0, 4.0, 6.0, 1.0),
                    "lerp_add": (-1.0, 10.0, 100.0, 0.0),
                }
            },
        )
        lmt = read_lmt_bytes(payload, source_name="vector-lerp-u16.lmt")
        decoded = decode_action_tracks(lmt.actions[0], strict=True)
        track = decoded.tracks[0]

        self.assertEqual(track.buffer_type, 4)
        self.assertEqual(track.keyframes[0].frame, 0)
        self.assertEqual(track.keyframes[1].frame, 300)
        self.assertAlmostEqual(track.keyframes[0].value[0], first_value[0], delta=1e-4)
        self.assertAlmostEqual(track.keyframes[0].value[1], first_value[1], delta=1e-4)
        self.assertAlmostEqual(track.keyframes[0].value[2], first_value[2], delta=1e-4)
        self.assertAlmostEqual(track.keyframes[1].value[0], first_value[0], delta=1e-4)
        self.assertAlmostEqual(track.keyframes[1].value[1], first_value[1], delta=1e-4)
        self.assertAlmostEqual(track.keyframes[1].value[2], first_value[2], delta=1e-4)

    def test_write_source_q7_quaternion_lerp_roundtrips(self):
        source = LmtReconstructedAction(
            action_name="QuaternionLerp7",
            frame_start=0,
            frame_end=8,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=0,
                    basis_value=(1.0, 0.0, 0.0, 0.0),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=0, value=(0.0, 1.0, 0.0, 0.0)),
                    ),
                ),
            ),
        )

        payload = write_lmt_bytes(
            source,
            track_metadata_by_identity={
                (3, 0): {
                    "buffer_type": 7,
                    "lerp_mult": (1.0, 1.0, 1.0, 1.0),
                    "lerp_add": (0.0, 0.0, 0.0, 0.0),
                }
            },
        )
        lmt = read_lmt_bytes(payload, source_name="quat-lerp-7.lmt")
        decoded = decode_action_tracks(lmt.actions[0], strict=True)
        track = decoded.tracks[0]

        self.assertEqual(track.buffer_type, 7)
        self.assertEqual(track.keyframes[0].frame, 0)
        self.assertAlmostEqual(track.keyframes[0].value[0], 0.0, delta=1e-4)
        self.assertAlmostEqual(track.keyframes[0].value[1], 1.0, delta=1e-4)
        self.assertAlmostEqual(track.keyframes[0].value[2], 0.0, delta=1e-4)
        self.assertAlmostEqual(track.keyframes[0].value[3], 0.0, delta=1e-4)

    def test_write_source_qxw_union_lerp_roundtrips(self):
        source = LmtReconstructedAction(
            action_name="QuaternionUnionLerp",
            frame_start=0,
            frame_end=8,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=0,
                    basis_value=(1.0, 0.0, 0.0, 0.0),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=0, value=(0.0, 1.0, 0.0, 0.0)),
                    ),
                ),
            ),
        )

        payload = write_lmt_bytes(
            source,
            track_metadata_by_identity={
                (3, 0): {
                    "buffer_type": 11,
                    "lerp_mult": (1.0, 1.0, 1.0, 1.0),
                    "lerp_add": (0.0, 0.0, 0.0, 0.0),
                }
            },
        )
        lmt = read_lmt_bytes(payload, source_name="quat-union.lmt")
        decoded = decode_action_tracks(lmt.actions[0], strict=True)
        track = decoded.tracks[0]

        self.assertEqual(track.buffer_type, 11)
        self.assertEqual(track.keyframes[0].frame, 0)
        self.assertAlmostEqual(track.keyframes[0].value[0], 0.0, delta=1e-4)
        self.assertAlmostEqual(track.keyframes[0].value[1], 1.0, delta=1e-4)
        self.assertAlmostEqual(track.keyframes[0].value[2], 0.0, delta=1e-4)
        self.assertAlmostEqual(track.keyframes[0].value[3], 0.0, delta=1e-4)

    def test_write_source_q7_quaternion_lerp_promotes_to_q11_lerp(self):
        source = LmtReconstructedAction(
            action_name="QuaternionLerpPromote",
            frame_start=0,
            frame_end=8,
            tracks=(
                LmtReconstructedTrack(
                    bone_id=3,
                    usage=0,
                    basis_value=(1.0, 0.0, 0.0, 0.0),
                    keyframes=(
                        LmtReconstructedKeyframe(frame=0, value=(0.70710678, 0.70710678, 0.0, 0.0)),
                    ),
                ),
            ),
        )

        payload = write_lmt_bytes(
            source,
            track_metadata_by_identity={
                (3, 0): {
                    "buffer_type": 7,
                    "lerp_mult": (1.0, 1.0, 1.0, 1.0),
                    "lerp_add": (0.0, 0.0, 0.0, 0.0),
                }
            },
        )
        lmt = read_lmt_bytes(payload, source_name="quat-promote.lmt")
        decoded = decode_action_tracks(lmt.actions[0], strict=True)
        track = decoded.tracks[0]

        self.assertEqual(track.buffer_type, 14)
        self.assertEqual(track.keyframes[0].frame, 0)
        self.assertAlmostEqual(track.keyframes[0].value[0], 0.70710678, delta=5e-4)
        self.assertAlmostEqual(track.keyframes[0].value[1], 0.70710678, delta=5e-4)
        self.assertAlmostEqual(track.keyframes[0].value[2], 0.0, delta=1e-4)
        self.assertAlmostEqual(track.keyframes[0].value[3], 0.0, delta=1e-4)


if __name__ == "__main__":
    unittest.main()
