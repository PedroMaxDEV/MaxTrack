import unittest
from stabilization import stabilize, smoothing_alpha, approach_depth, CABIN_SIDE_VIEW, CABIN_YAW_LIMIT, CabinMotion
import math

class StabilizationTests(unittest.TestCase):
    def test_depth_has_deadband_and_forward_limit(self):
        self.assertEqual(approach_depth(.3,.29),0.)
        self.assertEqual(approach_depth(.3,.305),0.)
        self.assertLess(approach_depth(.3,.36),0.)
        self.assertEqual(approach_depth(.3,.9),-.12)
    def test_legacy_smoothing_exact(self):
        for error in (0,5,13,30):
            tau=.012+.61*.25
            if error>12:tau*=.55
            self.assertEqual(smoothing_alpha(error,1/30,.61,False),1-math.exp(-(1/30)/tau))
    def test_turn_response_is_faster_without_disabling_smoothing(self):
        self.assertGreater(smoothing_alpha(8,1/30,.61),smoothing_alpha(8,1/30,.61,False))
        self.assertLess(smoothing_alpha(.2,1/30,.61),smoothing_alpha(8,1/30,.61))
    def test_still_head_noise_is_held(self):
        position=20.
        for value in [20.2,19.8,20.4,19.6]*100:
            position=stabilize(value,position,.6)
            self.assertEqual(position,20.)
    def test_slow_motion_is_not_lost(self):
        position=0.
        for n in range(1,101):position=stabilize(n*.05,position,.6)
        self.assertAlmostEqual(position,4.4)
    def test_turn_has_bounded_offset(self):
        self.assertAlmostEqual(stabilize(40,0,.6),39.4)
        self.assertAlmostEqual(stabilize(-40,0,.6),-39.4)
    def test_zero_disables(self):
        self.assertEqual(stabilize(20.2,20,0),20.2)

    def test_cabin_motion_requires_both_lean_and_turn_for_lateral_shift(self):
        def settle(yaw, span):
            motion = CabinMotion()
            motion.update(0., 0., .25, .25, 1/15)
            for _ in range(30):
                output = motion.update(yaw, 0., span, .25, 1/15)
            return output

        normal_turn = settle(35., .25)
        straight_lean = settle(0., .35)
        left = settle(-35., .35)
        right = settle(35., .35)
        self.assertEqual(normal_turn[2:], (0., 0.))
        self.assertLess(straight_lean[2], -.1)
        self.assertEqual(straight_lean[3], 0.)
        self.assertGreater(right[0], normal_turn[0] + 15.)
        self.assertAlmostEqual(left[0], -right[0])
        self.assertAlmostEqual(left[3], -right[3])
        self.assertGreater(right[3], .06)
        self.assertLessEqual(settle(130., .4)[0], CABIN_YAW_LIMIT)

    def test_cabin_motion_smooths_noise_and_returns_to_center_on_loss(self):
        motion = CabinMotion()
        motion.update(0., 0., .25, .25, .1)
        _, _, _, side = motion.update(35., 0., .29, .25, .1)
        self.assertLessEqual(side, .055)
        previous = motion.output[0]
        self.assertEqual(motion.lost(.1, .1)[0], previous)
        self.assertLess(motion.lost(.25, .1)[0], previous)
        self.assertEqual(motion.lost(1., .1), (0., 0., 0., 0.))
        motion.update(0., 0., .35, .25, .1)
        motion.recenter()
        self.assertEqual(motion.update(0., 0., .35, .25, .1), (0., 0., 0., 0.))

    def test_wide_turn_moves_continuously_and_returns_from_either_side(self):
        for fps in (15, 30, 60):
            for direction in (-1, 1):
                with self.subTest(fps=fps, direction=direction):
                    motion = CabinMotion()
                    motion.update(0., 0., .25, .25, 1/fps)
                    outward = [0.] + [
                        direction * motion.update(direction*46., 0., .30, .25, 1/fps)[0]
                        for _ in range(fps)
                    ]
                    self.assertAlmostEqual(outward[-1], CABIN_SIDE_VIEW, delta=1.)
                    self.assertTrue(all(0 <= end-start <= 420/fps + .001
                                        for start, end in zip(outward, outward[1:])))
                    inward = [outward[-1]] + [
                        direction * motion.update(0., 0., .25, .25, 1/fps)[0]
                        for _ in range(fps)
                    ]
                    self.assertLess(inward[-1], 1.)
                    self.assertTrue(all(0 <= start-end <= 420/fps + .001
                                        for start, end in zip(inward, inward[1:])))
