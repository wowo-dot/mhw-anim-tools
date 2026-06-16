from __future__ import annotations

import unittest

from core.animation.transforms import canonicalize_quaternion_frames_wxyz
from core.animation.transforms import nlerp_quaternion_wxyz
from core.animation.transforms import quaternion_multiply_wxyz
from core.animation.transforms import transform_blender_pose_basis_quaternion_to_mhw_wxyz
from core.animation.transforms import transform_blender_pose_basis_scale_to_mhw
from core.animation.transforms import transform_blender_object_quaternion_to_mhw_wxyz
from core.animation.transforms import transform_blender_object_translation_to_mhw
from core.animation.transforms import transform_blender_pose_translation_delta_to_mhw
from core.animation.transforms import transform_mhw_pose_quaternion_to_basis_wxyz
from core.animation.transforms import transform_mhw_pose_scale_to_basis
from core.animation.transforms import transform_mhw_object_quaternion_wxyz
from core.animation.transforms import transform_mhw_object_translation
from core.animation.transforms import transform_mhw_pose_translation_to_delta
from core.animation.transforms import wxyz_to_xyzw
from core.animation.transforms import xyzw_to_wxyz


class TransformHelpersTests(unittest.TestCase):
    def test_xyzw_to_wxyz(self):
        self.assertEqual(xyzw_to_wxyz((1.0, 2.0, 3.0, 4.0)), (4.0, 1.0, 2.0, 3.0))

    def test_wxyz_to_xyzw(self):
        self.assertEqual(wxyz_to_xyzw((4.0, 1.0, 2.0, 3.0)), (1.0, 2.0, 3.0, 4.0))

    def test_canonicalize_quaternion_frames_flips_hemisphere(self):
        frames = [
            (0.0, (1.0, 0.0, 0.0, 0.0)),
            (1.0, (-0.99, 0.1, 0.0, 0.0)),
        ]
        canonical = canonicalize_quaternion_frames_wxyz(frames)
        self.assertAlmostEqual(canonical[1][1][0], 0.99, places=6)
        self.assertAlmostEqual(canonical[1][1][1], -0.1, places=6)

    def test_nlerp_quaternion_wxyz_returns_normalized_midpoint(self):
        midpoint = nlerp_quaternion_wxyz(
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            0.5,
        )
        self.assertAlmostEqual(midpoint[0], 0.7071067811865476, places=6)
        self.assertAlmostEqual(midpoint[1], 0.7071067811865476, places=6)
        self.assertAlmostEqual(midpoint[2], 0.0, places=6)
        self.assertAlmostEqual(midpoint[3], 0.0, places=6)

    def test_transform_mhw_pose_translation_to_delta_uses_rest_baseline(self):
        delta = transform_mhw_pose_translation_to_delta(
            (-31.659901, 37.069901, 0.0),
            (-0.316593, 0.370955, 0.0),
        )
        self.assertAlmostEqual(delta[0], 0.0, places=4)
        self.assertAlmostEqual(delta[1], -0.000256, places=4)
        self.assertAlmostEqual(delta[2], 0.0, places=4)

    def test_transform_mhw_object_translation_rotates_and_scales(self):
        translated = transform_mhw_object_translation((0.0, 100.0, 0.0))
        self.assertAlmostEqual(translated[0], 0.0, places=6)
        self.assertAlmostEqual(translated[1], 0.0, places=6)
        self.assertAlmostEqual(translated[2], 1.0, places=6)

    def test_transform_blender_object_translation_to_mhw_is_inverse(self):
        translated = transform_blender_object_translation_to_mhw((0.0, 0.0, 1.0))
        self.assertAlmostEqual(translated[0], 0.0, places=6)
        self.assertAlmostEqual(translated[1], 100.0, places=6)
        self.assertAlmostEqual(translated[2], 0.0, places=6)

    def test_transform_mhw_object_quaternion_changes_basis(self):
        quarter_turn_y = (0.7071067811865476, 0.0, 0.7071067811865475, 0.0)
        transformed = transform_mhw_object_quaternion_wxyz(quarter_turn_y)
        self.assertAlmostEqual(transformed[0], 0.7071067811865476, places=6)
        self.assertAlmostEqual(transformed[1], 0.0, places=6)
        self.assertAlmostEqual(transformed[2], 0.0, places=6)
        self.assertAlmostEqual(transformed[3], 0.7071067811865475, places=6)

    def test_transform_blender_object_quaternion_to_mhw_is_inverse(self):
        quarter_turn_z = (0.7071067811865476, 0.0, 0.0, 0.7071067811865475)
        transformed = transform_blender_object_quaternion_to_mhw_wxyz(quarter_turn_z)
        self.assertAlmostEqual(transformed[0], 0.7071067811865476, places=6)
        self.assertAlmostEqual(transformed[1], 0.0, places=6)
        self.assertAlmostEqual(transformed[2], 0.7071067811865475, places=6)
        self.assertAlmostEqual(transformed[3], 0.0, places=6)

    def test_transform_blender_pose_translation_delta_to_mhw_is_inverse(self):
        mhw = transform_blender_pose_translation_delta_to_mhw(
            (0.0, -0.000256, 0.0),
            (-0.316593, 0.370955, 0.0),
        )
        self.assertAlmostEqual(mhw[0], -31.6593, places=3)
        self.assertAlmostEqual(mhw[1], 37.0699, places=3)
        self.assertAlmostEqual(mhw[2], 0.0, places=3)

    def test_transform_mhw_pose_translation_respects_rest_rotation(self):
        rest_rotation = (0.7071067811865476, 0.0, 0.0, 0.7071067811865475)
        delta = transform_mhw_pose_translation_to_delta(
            (0.0, 100.0, 0.0),
            (0.0, 0.0, 0.0),
            rest_rotation,
            (1.0, 1.0, 1.0),
        )
        self.assertAlmostEqual(delta[0], 1.0, places=6)
        self.assertAlmostEqual(delta[1], 0.0, places=6)
        self.assertAlmostEqual(delta[2], 0.0, places=6)

    def test_transform_blender_pose_translation_with_rest_rotation_is_inverse(self):
        rest_rotation = (0.7071067811865476, 0.0, 0.0, 0.7071067811865475)
        mhw = transform_blender_pose_translation_delta_to_mhw(
            (1.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            rest_rotation,
            (1.0, 1.0, 1.0),
        )
        self.assertAlmostEqual(mhw[0], 0.0, places=6)
        self.assertAlmostEqual(mhw[1], 100.0, places=6)
        self.assertAlmostEqual(mhw[2], 0.0, places=6)

    def test_transform_mhw_pose_quaternion_to_basis_uses_rest_rotation(self):
        rest_rotation = (0.7071067811865476, 0.0, 0.0, 0.7071067811865475)
        basis_rotation = (0.7071067811865476, 0.7071067811865475, 0.0, 0.0)
        desired_rotation = quaternion_multiply_wxyz(rest_rotation, basis_rotation)
        converted = transform_mhw_pose_quaternion_to_basis_wxyz(
            desired_rotation,
            rest_rotation,
        )
        self.assertAlmostEqual(converted[0], basis_rotation[0], places=6)
        self.assertAlmostEqual(converted[1], basis_rotation[1], places=6)
        self.assertAlmostEqual(converted[2], basis_rotation[2], places=6)
        self.assertAlmostEqual(converted[3], basis_rotation[3], places=6)

    def test_transform_blender_pose_basis_quaternion_to_mhw_is_inverse(self):
        rest_rotation = (0.7071067811865476, 0.0, 0.0, 0.7071067811865475)
        basis_rotation = (0.7071067811865476, 0.7071067811865475, 0.0, 0.0)
        transformed = transform_blender_pose_basis_quaternion_to_mhw_wxyz(
            basis_rotation,
            rest_rotation,
        )
        expected = quaternion_multiply_wxyz(rest_rotation, basis_rotation)
        self.assertAlmostEqual(transformed[0], expected[0], places=6)
        self.assertAlmostEqual(transformed[1], expected[1], places=6)
        self.assertAlmostEqual(transformed[2], expected[2], places=6)
        self.assertAlmostEqual(transformed[3], expected[3], places=6)

    def test_transform_mhw_pose_scale_to_basis_divides_rest_scale(self):
        converted = transform_mhw_pose_scale_to_basis(
            (2.0, 3.0, 4.0),
            (2.0, 3.0, 4.0),
        )
        self.assertEqual(converted, (1.0, 1.0, 1.0))

    def test_transform_blender_pose_basis_scale_to_mhw_is_inverse(self):
        converted = transform_blender_pose_basis_scale_to_mhw(
            (1.5, 2.0, 0.5),
            (2.0, 3.0, 4.0),
        )
        self.assertEqual(converted, (3.0, 6.0, 2.0))


if __name__ == "__main__":
    unittest.main()
