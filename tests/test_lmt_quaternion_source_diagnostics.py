from __future__ import annotations

import unittest

from core.formats.lmt.decoded import LmtDecodedAction
from core.formats.lmt.decoded import LmtDecodedSample
from core.formats.lmt.decoded import LmtDecodedTrack
from core.formats.lmt.quaternion_source_diagnostics import identify_raw_sensitive_quaternion_identities


class QuaternionSourceDiagnosticsTests(unittest.TestCase):
    def test_identifies_non_unit_quaternion_lerp_track(self):
        decoded = LmtDecodedAction(
            action_id=0,
            frame_count=10,
            loop_frame=-1,
            tracks=(
                LmtDecodedTrack(
                    track_index=0,
                    bone_id=5,
                    usage=0,
                    buffer_type=14,
                    basis_value=(1.0, 0.0, 0.0, 0.0),
                    keyframes=(
                        LmtDecodedSample(
                            frame=4,
                            delta_to_next=0,
                            value=(1.1, 0.0, 0.0, 0.0),
                        ),
                    ),
                ),
            ),
        )

        identities = identify_raw_sensitive_quaternion_identities(decoded)

        self.assertEqual(identities, frozenset({(5, 0)}))

    def test_ignores_unit_quaternion_key_track(self):
        decoded = LmtDecodedAction(
            action_id=0,
            frame_count=10,
            loop_frame=-1,
            tracks=(
                LmtDecodedTrack(
                    track_index=0,
                    bone_id=6,
                    usage=0,
                    buffer_type=6,
                    basis_value=(1.0, 0.0, 0.0, 0.0),
                    keyframes=(
                        LmtDecodedSample(
                            frame=4,
                            delta_to_next=0,
                            value=(0.7071067811865476, 0.7071067811865476, 0.0, 0.0),
                        ),
                    ),
                ),
            ),
        )

        identities = identify_raw_sensitive_quaternion_identities(decoded)

        self.assertEqual(identities, frozenset())


if __name__ == "__main__":
    unittest.main()
