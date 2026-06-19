from __future__ import annotations

import unittest

from core.diagnostics.errors import ValidationError
from core.formats.lmt.encoding import quaternion_lerp_promotion_candidates


class LmtEncodingTests(unittest.TestCase):
    def test_quaternion_lerp_promotion_candidates_follow_supported_upgrade_paths(self):
        self.assertEqual(quaternion_lerp_promotion_candidates(7), (7, 15, 14))
        self.assertEqual(quaternion_lerp_promotion_candidates(15), (15, 14))
        self.assertEqual(quaternion_lerp_promotion_candidates(14), (14,))
        self.assertEqual(quaternion_lerp_promotion_candidates(11), (11, 14))
        self.assertEqual(quaternion_lerp_promotion_candidates(12), (12, 14))
        self.assertEqual(quaternion_lerp_promotion_candidates(13), (13, 14))

    def test_quaternion_lerp_promotion_candidates_reject_unknown_types(self):
        with self.assertRaises(ValidationError):
            quaternion_lerp_promotion_candidates(99)


if __name__ == "__main__":
    unittest.main()
