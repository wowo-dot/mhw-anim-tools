from __future__ import annotations

import unittest

from core.formats.lmt.decoded import LmtDecodedAction
from core.formats.lmt.decoded import LmtDecodedSample
from core.formats.lmt.decoded import LmtDecodedTrack
from core.formats.lmt.source_preservation import identify_preservable_decoded_track_identities


class _Sample:
    def __init__(self, frame: int, value):
        self.frame = frame
        self.value = tuple(float(component) for component in value)


class _SampledTrack:
    def __init__(self, bone_id: int, usage: int, frames):
        self.bone_id = bone_id
        self.usage = usage
        self.frames = tuple(_Sample(frame, value) for frame, value in frames)


class LmtSourcePreservationTests(unittest.TestCase):
    def test_identifies_unchanged_dense_quaternion_track(self):
        decoded = LmtDecodedAction(
            action_id=0,
            frame_count=2,
            loop_frame=-1,
            tracks=(
                LmtDecodedTrack(
                    track_index=0,
                    bone_id=3,
                    usage=0,
                    buffer_type=15,
                    basis_value=(0.99, 0.0, 0.0, 0.1),
                    keyframes=(
                        LmtDecodedSample(frame=0, delta_to_next=2, value=(0.99, 0.0, 0.0, 0.1)),
                        LmtDecodedSample(frame=2, delta_to_next=0, value=(0.97, 0.0, 0.0, 0.25)),
                    ),
                ),
            ),
        )

        sampled = (
            _SampledTrack(
                3,
                0,
                (
                    (0, (0.9949371890224981, 0.0, 0.0, 0.1004987059618685)),
                    (1, (0.984427575508482, 0.0, 0.0, 0.1757906384836575)),
                    (2, (0.968355193071311, 0.0, 0.0, 0.24957608068848222)),
                ),
            ),
        )

        identities = identify_preservable_decoded_track_identities(decoded, sampled)

        self.assertEqual(identities, frozenset({(3, 0)}))

    def test_rejects_changed_dense_quaternion_track(self):
        decoded = LmtDecodedAction(
            action_id=0,
            frame_count=2,
            loop_frame=-1,
            tracks=(
                LmtDecodedTrack(
                    track_index=0,
                    bone_id=3,
                    usage=0,
                    buffer_type=15,
                    basis_value=(0.99, 0.0, 0.0, 0.1),
                    keyframes=(
                        LmtDecodedSample(frame=0, delta_to_next=2, value=(0.99, 0.0, 0.0, 0.1)),
                        LmtDecodedSample(frame=2, delta_to_next=0, value=(0.97, 0.0, 0.0, 0.25)),
                    ),
                ),
            ),
        )

        sampled = (
            _SampledTrack(
                3,
                0,
                (
                    (0, (0.9949371890224981, 0.0, 0.0, 0.1004987059618685)),
                    (1, (1.0, 0.0, 0.0, 0.0)),
                    (2, (0.968355193071311, 0.0, 0.0, 0.24957608068848222)),
                ),
            ),
        )

        identities = identify_preservable_decoded_track_identities(decoded, sampled)

        self.assertEqual(identities, frozenset())
