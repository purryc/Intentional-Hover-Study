import collections
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_two_day_motion_atlas import (add_heat, choose_segment, clean_segments, group_for,
                                        motion_edges, one_event, summarize_curves, to_heat_json)


def points(times, z=None, x=None):
    z = z or [0.8 - i * .02 for i in range(len(times))]
    x = x or [float(i) for i in range(len(times))]
    return [dict(t=t, x=x[i], y=300., z=z[i], input="PENCIL", source="PENCIL_HOVER",
                 sequence=i + 1) for i, t in enumerate(times)]


class MotionAtlasTests(unittest.TestCase):
    def test_task_event_groups_do_not_relabel_c3_natural_without_candidate(self):
        self.assertEqual(group_for(dict(task="B3", condition="HOVER"), dict(type="HOVER_SELECT")), "B3 多选")
        self.assertEqual(group_for(dict(task="A5", condition="NATURAL"), dict(type="CANDIDATE")), "自然阅读候选")
        self.assertIsNone(group_for(dict(task="C3", condition="NATURAL"), dict(type="CANDIDATE")))
        self.assertIsNone(group_for(dict(task="C3", condition="NATURAL"), dict(type="TOUCH_DOWN")))

    def test_trial_end_clips_hover_points(self):
        trial = dict(events=[dict(type="TRIAL_END", t=.4)], duration=.8,
                     segments=[points([0., .1, .2, .3, .4, .5, .6])])
        self.assertEqual(len(clean_segments(trial)[0]), 5)
        simulated = points([0., .1, .2])
        for p in simulated: p["source"] = "SIMULATED_HOVER"
        trial["segments"].append(simulated)
        self.assertEqual(len(clean_segments(trial)), 1)

    def test_no_gap_bridging_or_mixed_segments(self):
        seg = points([0., .02, .04, .20, .22])
        self.assertEqual(len(motion_edges(seg)), 3)
        self.assertIsNone(choose_segment([points([i * .02 for i in range(15)]),
                                          points([.35 + i * .02 for i in range(15)])], .65)[2])

    def test_event_paired_speed_and_z_change(self):
        times = [i * .02 for i in range(51)]
        x = [i * 5. for i in range(26)] + [125. + (i - 25) * .2 for i in range(26, 51)]
        seg = points(times, x=x)
        trial = dict(id="trial-1", task="B3", scene="abstract", posture="THUMB", events=[],
                     start=10., segments=[seg])
        output, _, _ = one_event(trial, "day", dict(type="HOVER_SELECT", t=1.), "B3 多选", 1, [seg])
        self.assertGreater(output["coverageMs"], 450)
        self.assertLess(output["paired"]["speedChange"], 0)
        self.assertLess(output["paired"]["zChange"], 0)
        self.assertEqual(summarize_curves([output])["day|B3 多选"]["trials"], 1)

    def test_heat_weights_elapsed_time_and_deduplicates_windows(self):
        seg = points([0., .02, .04, .06])
        heat = collections.defaultdict(lambda: collections.defaultdict(float))
        seen = set()
        edges = motion_edges(seg)
        add_heat(heat, "day", "THUMB", "B3 多选", "trial", seg, edges, seen=seen)
        add_heat(heat, "day", "THUMB", "B3 多选", "trial", seg, edges, seen=seen)
        data = to_heat_json(heat)["day|THUMB|B3 多选"]
        self.assertAlmostEqual(data["seconds"], .06, places=3)
        cropped = collections.defaultdict(lambda: collections.defaultdict(float))
        add_heat(cropped, "day", "THUMB", "B3 多选", "trial", seg, edges, anchor=.05)
        self.assertAlmostEqual(to_heat_json(cropped)["day|THUMB|B3 多选"]["seconds"], .05, places=3)


if __name__ == "__main__":
    unittest.main()
