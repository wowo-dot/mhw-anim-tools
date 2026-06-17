from __future__ import annotations

import unittest

from core.animation.transforms import nlerp_quaternion_wxyz
from core.formats.lmt.decoded import LmtDecodedAction
from core.formats.lmt.decoded import LmtDecodedSample
from core.formats.lmt.decoded import LmtDecodedTrack
from core.formats.lmt.reconstruction import reconstruct_decoded_action
from core.formats.lmt.reconstruction import reconstruct_sampled_action
from core.formats.lmt.reconstruction import reconstruct_track_samples


class FakeSampleFrame:
    def __init__(self, frame: int, value):
        self.frame = frame
        self.value = tuple(value)


class FakeSampledTrack:
    def __init__(self, bone_id: int, usage: int, frames, *, raw_frames=(), authored_frames=(), all_authored_keys_linear=True, authored_frame_end: int | None = None):
        self.bone_id = bone_id
        self.usage = usage
        self.frames = tuple(frames)
        self.raw_frames = tuple(raw_frames)
        self.authored_frames = tuple(int(frame) for frame in authored_frames)
        self.all_authored_keys_linear = bool(all_authored_keys_linear)
        self.authored_frame_end = authored_frame_end


class LmtReconstructionTests(unittest.TestCase):
    def test_constant_local_track_reconstructs_to_basis_only(self):
        reconstructed = reconstruct_track_samples(
            bone_id=0,
            usage=1,
            frames=[
                (0, (0.0, 0.0, 0.0)),
                (1, (0.0, 0.0, 0.0)),
                (2, (0.0, 0.0, 0.0)),
            ],
        )
        self.assertEqual(reconstructed.basis_value, (0.0, 0.0, 0.0))
        self.assertEqual(reconstructed.sparse_key_count, 0)
        self.assertIsNone(reconstructed.tail_frame)
        self.assertIsNone(reconstructed.tail_value)

    def test_root_translation_reconstructs_tail_without_body_keys(self):
        reconstructed = reconstruct_track_samples(
            bone_id=-1,
            usage=4,
            frames=[
                (0, (0.0, 0.0, 0.0)),
                (1, (1.0, 0.0, 0.0)),
                (2, (2.0, 0.0, 0.0)),
                (3, (3.0, 0.0, 0.0)),
            ],
        )
        self.assertEqual(reconstructed.basis_value, (0.0, 0.0, 0.0))
        self.assertEqual(reconstructed.sparse_key_count, 0)
        self.assertEqual(reconstructed.tail_frame, 3)
        self.assertEqual(reconstructed.tail_value, (3.0, 0.0, 0.0))

    def test_piecewise_linear_track_keeps_turning_point(self):
        reconstructed = reconstruct_track_samples(
            bone_id=3,
            usage=1,
            frames=[
                (0, (0.0, 0.0, 0.0)),
                (1, (1.0, 0.0, 0.0)),
                (2, (2.0, 0.0, 0.0)),
                (3, (2.0, 0.0, 0.0)),
            ],
        )
        self.assertEqual([key.frame for key in reconstructed.keyframes], [2, 3])
        self.assertEqual(reconstructed.keyframes[0].value, (2.0, 0.0, 0.0))
        self.assertEqual(reconstructed.keyframes[1].value, (2.0, 0.0, 0.0))

    def test_reconstruct_sampled_action_accumulates_sparse_key_count(self):
        reconstructed = reconstruct_sampled_action(
            action_name="RoundTrip",
            frame_start=0,
            frame_end=3,
            sampled_tracks=[
                FakeSampledTrack(
                    bone_id=0,
                    usage=1,
                    frames=[
                        FakeSampleFrame(0, (0.0, 0.0, 0.0)),
                        FakeSampleFrame(1, (1.0, 0.0, 0.0)),
                        FakeSampleFrame(2, (2.0, 0.0, 0.0)),
                        FakeSampleFrame(3, (2.0, 0.0, 0.0)),
                    ],
                    authored_frame_end=3,
                ),
                FakeSampledTrack(
                    bone_id=-1,
                    usage=4,
                    frames=[
                        FakeSampleFrame(0, (0.0, 0.0, 0.0)),
                        FakeSampleFrame(1, (0.0, 0.0, 1.0)),
                    ],
                ),
            ],
        )
        self.assertEqual(reconstructed.track_count, 2)
        self.assertEqual(reconstructed.sparse_key_count, 2)
        self.assertEqual(reconstructed.tracks[1].tail_frame, 1)

    def test_authored_local_constant_keys_are_preserved(self):
        reconstructed = reconstruct_track_samples(
            bone_id=4,
            usage=1,
            authored_frames=(0, 3),
            frames=[
                (0, (0.0, 0.0, 0.0)),
                (1, (0.0, 0.0, 0.0)),
                (2, (0.0, 0.0, 0.0)),
                (3, (0.0, 0.0, 0.0)),
            ],
        )
        self.assertEqual([key.frame for key in reconstructed.keyframes], [3])
        self.assertEqual(reconstructed.keyframes[0].value, (0.0, 0.0, 0.0))

    def test_authored_local_frames_trim_dense_tail_without_extra_hold_key(self):
        reconstructed = reconstruct_track_samples(
            bone_id=7,
            usage=1,
            authored_frames=(0, 2),
            authored_frame_end=2,
            frames=[
                (0, (0.0, 0.0, 0.0)),
                (1, (1.0, 0.0, 0.0)),
                (2, (2.0, 0.0, 0.0)),
                (3, (2.0, 0.0, 0.0)),
                (4, (2.0, 0.0, 0.0)),
            ],
        )
        self.assertEqual([key.frame for key in reconstructed.keyframes], [2])

    def test_authored_root_last_frame_is_preserved_as_tail(self):
        reconstructed = reconstruct_track_samples(
            bone_id=-1,
            usage=4,
            authored_frames=(0, 1, 3),
            frames=[
                (0, (0.0, 0.0, 0.0)),
                (1, (1.0, 0.0, 0.0)),
                (2, (2.0, 0.0, 0.0)),
                (3, (3.0, 0.0, 0.0)),
            ],
        )
        self.assertEqual([key.frame for key in reconstructed.keyframes], [1])
        self.assertEqual(reconstructed.tail_frame, 3)
        self.assertEqual(reconstructed.tail_value, (3.0, 0.0, 0.0))

    def test_quaternion_track_uses_nlerp_aware_sparsification(self):
        start = (1.0, 0.0, 0.0, 0.0)
        end = (0.0, 1.0, 0.0, 0.0)
        reconstructed = reconstruct_track_samples(
            bone_id=2,
            usage=0,
            authored_frames=(0, 4),
            frames=[
                (0, start),
                (1, nlerp_quaternion_wxyz(start, end, 0.25)),
                (2, nlerp_quaternion_wxyz(start, end, 0.50)),
                (3, nlerp_quaternion_wxyz(start, end, 0.75)),
                (4, end),
            ],
        )
        self.assertEqual([key.frame for key in reconstructed.keyframes], [4])
        self.assertEqual(reconstructed.keyframes[0].value, end)

    def test_trailing_dense_hold_after_authored_end_is_trimmed_for_local_track(self):
        reconstructed = reconstruct_track_samples(
            bone_id=7,
            usage=1,
            authored_frame_end=2,
            frames=[
                (0, (0.0, 0.0, 0.0)),
                (1, (1.0, 0.0, 0.0)),
                (2, (2.0, 0.0, 0.0)),
                (3, (2.0, 0.0, 0.0)),
            ],
        )
        self.assertEqual([key.frame for key in reconstructed.keyframes], [2])

    def test_reconstruct_sampled_action_can_use_raw_quaternion_source_keys(self):
        reconstructed = reconstruct_sampled_action(
            action_name="RawQuatSource",
            frame_start=0,
            frame_end=4,
            raw_quaternion_source_identities={(8, 0)},
            sampled_tracks=[
                FakeSampledTrack(
                    bone_id=8,
                    usage=0,
                    frames=[
                        FakeSampleFrame(0, (1.0, 0.0, 0.0, 0.0)),
                        FakeSampleFrame(1, (0.99, 0.01, 0.0, 0.0)),
                        FakeSampleFrame(4, (0.95, 0.05, 0.0, 0.0)),
                    ],
                    raw_frames=[
                        FakeSampleFrame(0, (1.0, 0.0, 0.0, 0.0)),
                        FakeSampleFrame(1, (1.02, 0.01, 0.0, 0.0)),
                        FakeSampleFrame(2, (1.01, 0.02, 0.0, 0.0)),
                        FakeSampleFrame(3, (0.99, 0.03, 0.0, 0.0)),
                        FakeSampleFrame(4, (0.97, 0.05, 0.0, 0.0)),
                    ],
                    authored_frames=(0, 1, 4),
                ),
            ],
        )

        track = reconstructed.tracks[0]
        self.assertEqual(track.basis_value, (1.0, 0.0, 0.0, 0.0))
        self.assertEqual([key.frame for key in track.keyframes], [1, 4])
        self.assertEqual(track.keyframes[0].value, (1.02, 0.01, 0.0, 0.0))
        self.assertEqual(track.keyframes[1].value, (0.97, 0.05, 0.0, 0.0))

    def test_reconstruct_decoded_action_preserves_sparse_source_semantics(self):
        decoded = LmtDecodedAction(
            action_id=12,
            frame_count=40,
            loop_frame=-1,
            tracks=(
                LmtDecodedTrack(
                    track_index=0,
                    bone_id=3,
                    usage=1,
                    buffer_type=5,
                    basis_value=(0.0, 0.0, 0.0),
                    keyframes=(
                        LmtDecodedSample(frame=0, delta_to_next=2, value=(1.0, 0.0, 0.0)),
                        LmtDecodedSample(frame=2, delta_to_next=38, value=(2.0, 0.0, 0.0)),
                    ),
                ),
                LmtDecodedTrack(
                    track_index=1,
                    bone_id=-1,
                    usage=4,
                    buffer_type=3,
                    basis_value=(0.0, 0.0, 0.0),
                    keyframes=(),
                    tail_frame=40,
                    tail_value=(3.0, 0.0, 0.0),
                ),
            ),
        )

        reconstructed = reconstruct_decoded_action(decoded, action_name="DecodedMirror")

        self.assertEqual(reconstructed.action_name, "DecodedMirror")
        self.assertEqual(reconstructed.frame_start, 0)
        self.assertEqual(reconstructed.frame_end, 40)
        self.assertEqual(reconstructed.track_count, 2)
        self.assertEqual([key.frame for key in reconstructed.tracks[0].keyframes], [0, 2])
        self.assertEqual(reconstructed.tracks[0].keyframes[1].value, (2.0, 0.0, 0.0))
        self.assertEqual(reconstructed.tracks[1].tail_frame, 40)
        self.assertEqual(reconstructed.tracks[1].tail_value, (3.0, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
