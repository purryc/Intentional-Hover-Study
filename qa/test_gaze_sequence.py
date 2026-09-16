import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from analyze_gaze_v24 import eye_hand_alignment, heat_edges, reading_heat
from sequence_comparison import anchors, bins_for, eligible_segments


class GazeSequenceTests(unittest.TestCase):
    def test_heatmap_does_not_bridge_invalid_frame_or_gap(self):
        samples = [
            dict(t=0., x=10., y=10., validity="TRACKED", calibrationID="a"),
            dict(t=.04, x=10., y=10., validity="TRACKED", calibrationID="a"),
            dict(t=.08, x=None, y=None, validity="NO_TRACKED_FACE", calibrationID="a"),
            dict(t=.12, x=10., y=10., validity="TRACKED", calibrationID="a"),
            dict(t=.28, x=10., y=10., validity="TRACKED", calibrationID="a"),
        ]
        heat, observed = heat_edges(samples, "gaze")
        self.assertAlmostEqual(observed, .04)
        self.assertAlmostEqual(heat[(0, 0)], .04)

    def test_object_alignment_abstains_on_missing_or_low_quality_gaze(self):
        event = dict(type="HOVER_SELECT", t=1., metadata={"objectID": "target"})
        trial = dict(id="t", task="B2", condition="HOVER", events=[event], gaze=[])
        self.assertEqual(eye_hand_alignment([trial])[0]["result"], "ABSTAIN_CALIBRATION")
        trial["gaze"] = [dict(t=.78+i*.02, x=100., y=100., objectID="target",
                              quality="OBJECT_LEVEL_PILOT", validity="TRACKED") for i in range(12)]
        self.assertEqual(eye_hand_alignment([trial])[0]["result"], "MATCH")
        for sample in trial["gaze"]:
            sample["objectID"] = "other"
        self.assertEqual(eye_hand_alignment([trial])[0]["result"], "NO_MATCH")

    def test_reading_heat_excludes_post_trial_transition(self):
        task = dict(t=.01, x=20., y=20., validity="TRACKED", calibrationID="a", sequencePhase="TASK")
        next_task = dict(task, t=.05)
        transition = dict(task, t=.09, sequencePhase="INTER_TRIAL")
        trial = dict(task="A5", condition="NATURAL", posture="THUMB", success=True, duration=.10,
                     gaze=[task, next_task, transition],
                     segments=[[dict(t=p["t"], x=p["x"], y=p["y"], source="PENCIL_HOVER",
                                     sequencePhase=p["sequencePhase"]) for p in [task, next_task, transition]]])
        group = reading_heat([trial])[("A5", "THUMB")]
        self.assertAlmostEqual(group["observedGazeS"], .04)
        self.assertAlmostEqual(group["observedPencilS"], .04)

    def test_b3_sequence_uses_only_nonfinal_selection(self):
        objects = [{"id": f"t{i}", "bounds": {"x": 80, "y": 250+i*100, "width": 50, "height": 50}}
                   for i in range(3)]
        trial = dict(id="b3", task="B3", condition="HOVER", success=True,
                     trial={"objects": objects}, events=[dict(type="HOVER_SELECT", t=2+i,
                     metadata={"objectID": f"t{i}"}) for i in range(3)])
        self.assertEqual(len(list(anchors(trial, None))), 2)

    def test_b2_single_selection_is_included_separately(self):
        trial = dict(id="b2", task="B2", condition="HOVER", success=True,
                     trial={"objects": [{"id": "target", "bounds": {"x": 80, "y": 250, "width": 50, "height": 50}}]},
                     events=[dict(type="HOVER_SELECT", t=2., metadata={"objectID": "target"})])
        self.assertEqual(list(anchors(trial, None)), [("B2 单选", 2., (105., 275.))])

    def test_speed_bins_never_bridge_source_segments(self):
        hover = [dict(t=0., x=0., y=10.), dict(t=.02, x=10., y=10.)]
        touch = [dict(t=.04, x=110., y=10.), dict(t=.06, x=120., y=10.)]
        bins = bins_for([hover, touch], anchor=.04, center=(100., 10.))
        self.assertEqual(sum(v is not None for v in bins["speed"]), 2)
        self.assertLess(max(v for v in bins["speed"] if v is not None), 501)

    def test_signed_z_rate_only_uses_contiguous_hover_samples(self):
        hover_down = [dict(t=0., x=10., y=10., z=.8, source="PENCIL_HOVER"),
                      dict(t=.02, x=10., y=10., z=.6, source="PENCIL_HOVER")]
        hover_up = [dict(t=.20, x=10., y=10., z=.3, source="PENCIL_HOVER"),
                    dict(t=.22, x=10., y=10., z=.4, source="PENCIL_HOVER")]
        touch = [dict(t=.30, x=10., y=10., z=0., source="PENCIL_TOUCH"),
                 dict(t=.32, x=10., y=10., z=.1, source="PENCIL_TOUCH")]
        missing_z = [dict(t=.40, x=10., y=10., z=None, source="PENCIL_HOVER"),
                     dict(t=.42, x=10., y=10., z=.2, source="PENCIL_HOVER")]
        bins = bins_for([hover_down, hover_up, touch, missing_z], anchor=0., center=(10., 10.))
        valid = [v for v in bins["zRate"] if v is not None]
        z_speeds = [v for v in bins["zSpeed"] if v is not None]
        self.assertEqual(len(valid), 2)
        self.assertAlmostEqual(min(valid), -10.)
        self.assertAlmostEqual(max(valid), 5.)
        self.assertEqual(len(z_speeds), 2)
        self.assertAlmostEqual(min(z_speeds), 5.)
        self.assertAlmostEqual(max(z_speeds), 10.)

    def test_z_speed_takes_pairwise_magnitude_before_bin_median(self):
        reversing = [dict(t=t, x=10., y=10., z=z, source="PENCIL_HOVER")
                     for t, z in [(0., .8), (.01, .7), (.02, .8)]]
        bins = bins_for([reversing], anchor=0., center=(10., 10.))
        self.assertAlmostEqual(next(v for v in bins["zRate"] if v is not None), 0.)
        self.assertAlmostEqual(next(v for v in bins["zSpeed"] if v is not None), 10.)

    def test_z_rate_does_not_bridge_long_callback_gap(self):
        gap = [dict(t=0., x=10., y=10., z=.8, source="PENCIL_HOVER"),
               dict(t=.15, x=10., y=10., z=.2, source="PENCIL_HOVER")]
        bins = bins_for([gap], anchor=0., center=(10., 10.))
        self.assertTrue(all(v is None for v in bins["zRate"]))
        self.assertTrue(all(v is None for v in bins["zSpeed"]))

    def test_z_rate_does_not_bridge_excised_off_phone_sample(self):
        points = [dict(t=t, x=x, y=10., z=z, source="PENCIL_HOVER", input="PENCIL")
                  for t, x, z in [(0., 10., .8), (.02, 400., .5), (.04, 10., .2)]]
        trial = dict(segments=[points], events=[], duration=.1)
        segments = eligible_segments(trial, include_touch=False)
        self.assertEqual(len(segments), 2)
        self.assertTrue(all(v is None for v in bins_for(segments, 0., (10., 10.))["zRate"]))
        self.assertTrue(all(v is None for v in bins_for(segments, 0., (10., 10.))["zSpeed"]))


if __name__ == "__main__":
    unittest.main()
