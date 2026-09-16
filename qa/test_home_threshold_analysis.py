"""Checks for independent spatial Home and 500/800 ms counterfactual counts."""
import unittest

from home_threshold_analysis import (THRESHOLDS_MS, weighted_cells, hotspot,
                                     threshold_trial, summarize_threshold, analyze_home_trial)


class SpatialHomeTests(unittest.TestCase):
    def test_position_hotspot_uses_observed_time_not_dwell_events(self):
        # Two intervals at one location outweigh four shorter intervals elsewhere.
        edges = [(0, .08, 100, 100), (.08, .16, 100, 100),
                 (.16, .18, 300, 500), (.18, .20, 300, 500),
                 (.20, .22, 300, 500), (.22, .24, 300, 500)]
        home = hotspot(weighted_cells(edges))
        self.assertEqual((home['x'], home['y']), (110, 110))
        self.assertAlmostEqual(home['observedS'], .24, places=3)

    def test_home_ignores_dwell_events_and_disconnected_gap(self):
        points = []
        for i in range(121):
            points.append({'t': i, 'x': 100, 'y': 100, 'z': .4,
                           'source': 'PENCIL_HOVER', 'input': 'PENCIL', 'sequence': i})
        # The one-second gaps must not be converted into 120 seconds of observed hover.
        trial = {'id': 'trial', 'scene': 'news', 'posture': 'THUMB', 'duration': 120,
                 'task': 'A5', 'condition': 'NATURAL', 'segments': [points],
                 'events': [{'type': 'TRIAL_END', 't': 120}]}
        row = analyze_home_trial(trial, 'day')
        self.assertEqual(row['observedS'], 0)
        self.assertIsNone(row['firstEstimableWallS'])
        self.assertIsNone(row['validatedStableWallS'])


class ThresholdTests(unittest.TestCase):
    def test_threshold_uses_complete_episodes_once(self):
        def event(typ, ms, fired=False):
            return {'type': typ, 'metadata': {'durationMs': str(ms),
                    'candidate': 'true' if fired else 'false', 'objectID': 'object'}}
        trial = {'id': 't', 'task': 'A5', 'condition': 'NATURAL', 'scene': 'news',
                 'posture': 'THUMB', 'duration': 120, 'trial': {'requested': []},
                 'events': [event('DWELL_END', 490), event('DWELL_END', 700, True),
                            event('DWELL_END', 2400, True),
                            event('CANDIDATE', 0), event('CANDIDATE', 0)]}
        row = threshold_trial(trial, 'day')
        self.assertEqual((row['episodes'], row['candidate500'], row['candidate800']), (3, 2, 1))
        self.assertEqual(row['candidateSeries'][THRESHOLDS_MS.index(100)], 3)
        self.assertEqual(row['candidateSeries'][THRESHOLDS_MS.index(500)], row['logged500'])
        self.assertEqual(row['candidateSeries'][THRESHOLDS_MS.index(800)], 1)
        self.assertEqual(row['candidateSeries'][THRESHOLDS_MS.index(1000)], 1)
        grouped = summarize_threshold([row])[0]
        self.assertEqual(grouped['candidateSeries'][THRESHOLDS_MS.index(800)], grouped['candidate800'])

    def test_threshold_grid_includes_exact_bounds_and_is_monotonic(self):
        def dwell(ms, fired=False):
            return {'type': 'DWELL_END', 'metadata': {'durationMs': str(ms),
                    'candidate': 'true' if fired else 'false'}}
        trial = {'id': 'edge', 'task': 'A5', 'scene': 'news', 'posture': 'THUMB',
                 'duration': 120, 'trial': {'requested': []},
                 'events': [dwell(100), dwell(499.9, True), dwell(1000, True),
                            {'type': 'CANDIDATE', 'metadata': {}},
                            {'type': 'CANDIDATE', 'metadata': {}}]}
        row = threshold_trial(trial, 'day')
        counts = row['candidateSeries']
        self.assertEqual((counts[0], counts[THRESHOLDS_MS.index(500)], counts[-1]), (3, 2, 1))
        self.assertTrue(all(a >= b for a, b in zip(counts, counts[1:])))


if __name__ == '__main__':
    unittest.main()
