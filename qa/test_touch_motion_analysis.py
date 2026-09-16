import unittest

from touch_motion_analysis import contact_shape, paired_contacts, summarize


class TouchMotionAnalysisTests(unittest.TestCase):
    def test_pairs_only_complete_contacts_in_event_order(self):
        trial = {"duration": 3.0, "events": [
            {"type": "TOUCH_UP", "t": .1},
            {"type": "TOUCH_DOWN", "t": .3},
            {"type": "TOUCH_UP", "t": .5},
            {"type": "TOUCH_DOWN", "t": 1.0},
            {"type": "TOUCH_DOWN", "t": 1.5},
            {"type": "TOUCH_UP", "t": 1.8},
            {"type": "TOUCH_DOWN", "t": 2.9},
        ]}
        self.assertEqual(paired_contacts(trial), [(.3, .5), (1.5, 1.8)])

    def test_contact_path_does_not_cross_tracking_gap(self):
        segments = [
            [{"t": 0.0, "x": 0, "y": 0}, {"t": .05, "x": 5, "y": 0}],
            [{"t": .25, "x": 100, "y": 0}, {"t": .30, "x": 105, "y": 0}],
        ]
        shape = contact_shape(segments, 0, .3)
        self.assertAlmostEqual(shape["observedPathPt"], 10)
        self.assertAlmostEqual(shape["coverage"], 1 / 3)
        self.assertEqual(len(shape["speed"]), 20)

    def test_incomplete_contact_path_excluded_from_median(self):
        event = {"day": "D", "trialID": "1", "task": "A1", "durationMs": 200,
                 "contactCoverage": .2, "observedPathPt": 999,
                 "preSpeed": [None] * 20, "preZSpeed": [None] * 20,
                 "contactSpeed": [None] * 20}
        row = summarize([event])["A1"]
        self.assertEqual(row["contacts"], 1)
        self.assertIsNone(row["observedPathPt"]["median"])
        self.assertEqual(row["contactDurationMs"]["median"], 200)


if __name__ == "__main__":
    unittest.main()
