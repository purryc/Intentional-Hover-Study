#!/usr/bin/env python3
"""Boundary checks for the read-only gaze/home summary."""
import unittest

from analyze_gaze_home_latest import hotspot, intervals, paired_distances


class GazeHomeChecks(unittest.TestCase):
    def point(self, t, x=100., y=100., validity='TRACKED'):
        return {'t': t, 'x': x, 'y': y, 'validity': validity, 'calibrationID': 'cal'}

    def test_invalid_or_outside_point_breaks_interval(self):
        pts = [self.point(0), self.point(.02, validity='NO_TRACKED_FACE'),
               self.point(.04), self.point(.06, x=410), self.point(.08)]
        self.assertEqual(list(intervals(pts, gaze=True)), [])

    def test_measured_short_interval_only(self):
        pts = [self.point(0), self.point(.02), self.point(.25), self.point(.27)]
        self.assertEqual([round(dt, 3) for _, dt in intervals(pts, gaze=True)], [.02, .02])

    def test_home_is_weighted_spatial_mode(self):
        center, share, _ = hotspot([(self.point(0, 300, 500), .08),
                                    (self.point(.08, 300, 500), .08),
                                    (self.point(.16, 100, 100), .02)])
        self.assertLessEqual(abs(center[0]-300), 50)
        self.assertLessEqual(abs(center[1]-500), 50)
        self.assertGreater(share, .8)

    def test_pair_requires_hover_interval_at_same_time(self):
        gaze = [self.point(.08), self.point(.10)]
        hover = [self.point(0), self.point(.02), self.point(.18), self.point(.20)]
        self.assertEqual(paired_distances(gaze, hover)['seconds'], 0)


if __name__ == '__main__':
    unittest.main()
