from dataclasses import replace
import json
from pathlib import Path
import unittest

from core.formats.lmt.pose_evaluation import PoseCurve, compile_pose_curve, compile_pose_evaluation
from pose_test_support import action, static, animated


class PoseEvaluationTests(unittest.TestCase):
    def test_order_multiplicity_aliases_and_control_preservation(self):
        tracks = [static(512, 1, (float(i), 0., 0.)) for i in range(257)]
        tracks += [static(7, 1, (999., 0., 0.)), static(-1, 1), static(99, 1),
                   static(25, 3, (1.,0.,0.,0.)), static(-1,5), static(251,1)]
        source = action(tracks)
        plan = compile_pose_evaluation(source, {0:'body',7:'body',251:'control'})
        self.assertTrue(plan.supported)
        self.assertIs(plan.source, source)
        self.assertEqual(plan.sample(3.5)['body',1], (999.,0.,0.))
        self.assertEqual(plan.bindings[0].source_indices, tuple(range(258)))
        self.assertFalse(plan.bindings[0].identical)
        self.assertEqual(len(plan.diagnostics), 3)  # negative, unmapped, root scale
        self.assertEqual(plan.sample(0)[None,3], (1.,0.,0.,0.))

    def test_identical_nonidentity_quaternions_are_applied_once(self):
        track = static(-1, 3, (.6, .8, 0., 0.))
        plan = compile_pose_evaluation(action([track]*13), {})
        self.assertTrue(plan.bindings[0].identical)
        self.assertEqual(plan.sample(10)[None,3], (.6,.8,0.,0.))

    def test_partial_component_pass_through_is_explicit_and_history_free(self):
        plan = compile_pose_evaluation(action([animated(3)]), {0:'body'})
        base = {('body',0):(.6,.8,0.,0.), ('body',2):(2.,3.,4.), ('extra',1):(7.,8.,9.)}
        for t in (0., 3.75, 10., 2.25, 9.5, 0.):
            sampled = plan.sample(t, base=base)
            self.assertEqual(sampled['body',0], base['body',0])
            self.assertEqual(sampled['body',2], base['body',2])
            self.assertEqual(sampled['body',1], compile_pose_curve(animated(3)).sample(t))
        self.assertNotIn(('body',1), base)
        for invalid in (-.1, 11, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                plan.sample(invalid)

    def test_quaternion_interpolation_preserves_raw_lengths(self):
        curve = PoseCurve((0,10), ((2.,0.,0.,0.), (0.,-1.,0.,0.)), True)
        self.assertAlmostEqual(curve.sample(5)[0], 2/(5**.5))
        self.assertAlmostEqual(curve.sample(5)[1], -1/(5**.5))
        opposite = PoseCurve((0,10), ((2.,0.,0.,0.), (-1.,0.,0.,0.)), True)
        self.assertEqual(opposite.sample(5), (1.,0.,0.,0.))

    def test_root_header_is_not_an_injected_sample(self):
        plan = compile_pose_evaluation(action([static(-1,4,(1.,2.,3.))]), {})
        self.assertEqual(plan.sample(9.75)[None,4], (1.,2.,3.))

    def test_static_sampler_copies_basis_without_normalizing(self):
        self.assertEqual(compile_pose_curve(static(0,0,(2.,0.,0.,0.))).sample(0), (2.,0.,0.,0.))

    def test_unknown_winner_and_joint_modes_fail_without_fallback(self):
        bad = replace(static(), header=replace(static().header, buffer_type=255))
        plan = compile_pose_evaluation(action([static(),bad]), {0:'body'})
        self.assertFalse(plan.supported)
        self.assertEqual(plan.bindings[0].source_index, 1)
        with self.assertRaises(ValueError):
            plan.sample(0)
        # Unused codecs do not defeat a later supported record, but an earlier
        # joint mode can affect the destination's downstream processing.
        self.assertTrue(compile_pose_evaluation(action([bad,static()]), {0:'body'}).supported)
        mode = replace(static(), header=replace(static().header, joint_type=1))
        self.assertFalse(compile_pose_evaluation(action([mode,static()]), {0:'body'}).supported)
        weight = replace(static(), header=replace(static().header, weight=0))
        self.assertFalse(compile_pose_evaluation(action([weight]), {0:'body'}).supported)
        self.assertFalse(compile_pose_evaluation(action([static()]), {0:'body'}, version=94).supported)

    def test_missing_or_zero_duration_terminal_is_checked(self):
        original = animated(3)
        missing = replace(original, raw_buffer=original.raw_buffer[:16], header=replace(original.header, buffer_size=16))
        with self.assertRaises(ValueError):
            compile_pose_curve(missing)
        stopped = replace(original, raw_buffer=original.raw_buffer[16:] + original.raw_buffer[:16])
        self.assertEqual(compile_pose_curve(stopped).frames, (0,))

    def test_native_instruction_golden_samples(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/native_pose_samples.json').read_text())
        for case in fixture['cases']:
            curve = compile_pose_curve(animated(case['codec']))
            for row in case['samples']:
                actual = curve.sample(row['frame'])
                for a, b in zip(actual, row['value']):
                    self.assertAlmostEqual(a, b, delta=2e-6)


if __name__ == '__main__':
    unittest.main()
