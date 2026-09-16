import unittest

from dwell_threshold_report import build_dataset, summarize


def event(kind, metadata=None):
    return dict(type=kind, metadata=metadata or {})


def trial(identifier, task, scene, posture, dwells, candidates=0):
    return dict(id=identifier, task=task, scene=scene, posture=posture,
                condition="NATURAL", duration=20.0,
                trial=dict(requested=["butterfly"] if task == "C3" else []),
                events=[event("DWELL_END", row) for row in dwells] +
                       [event("CANDIDATE", {"objectID": "butterfly" if task == "C3" else "article"})
                        for _ in range(candidates)],
                segments=[[dict(t=0.0, source="PENCIL_HOVER"),
                           dict(t=.2, source="PENCIL_HOVER")]])


class DwellThresholdTests(unittest.TestCase):
    def test_each_completed_dwell_counts_once_without_joining_interruptions(self):
        a = trial("a", "A5", "news", "THUMB", [
            dict(objectID="article", durationMs="300", candidate="false"),
            dict(objectID="article", durationMs="300", candidate="false")])
        dataset = build_dataset([a], [])
        self.assertEqual(summarize(dataset, 100, "A")["candidates"], 2)
        self.assertEqual(summarize(dataset, 500, "A")["candidates"], 0)
        self.assertEqual(summarize(dataset, 1000, "A")["candidates"], 0)

    def test_500_ms_logged_trigger_survives_earlier_touch_end_timestamp(self):
        c = trial("c", "C3", "video", "CRADLE_INDEX", [
            dict(objectID="butterfly", durationMs="496.678", candidate="true"),
            dict(objectID="star", durationMs="900", candidate="false")], candidates=1)
        exposure = [dict(trialID="c", hoverObserved_s=2.0, insideObserved_s=.5, visits=1)]
        dataset = build_dataset([c], exposure)
        self.assertEqual(len(dataset["trials"][0]["episodes"]), 1)
        self.assertAlmostEqual(dataset["trials"][0]["episodes"][0]["durationMs"], 496.678)
        self.assertEqual(summarize(dataset, 500, "C3")["candidates"], 1)
        self.assertEqual(summarize(dataset, 525, "C3")["candidates"], 0)
        self.assertEqual(summarize(dataset, 500, "C3")["logged500"], 1)

    def test_long_dwell_counts_once_and_filters_scene_and_posture(self):
        a = trial("a", "A5", "news", "THUMB", [
            dict(objectID="article", durationMs="1200", candidate="true")], candidates=1)
        b = trial("b", "A6", "notes", "CRADLE_INDEX", [
            dict(objectID="note", durationMs="150", candidate="false")])
        dataset = build_dataset([a, b], [])
        self.assertEqual(summarize(dataset, 1000, "A")["candidates"], 1)
        self.assertEqual(summarize(dataset, 100, "A")["candidates"], 2)
        self.assertEqual(summarize(dataset, 100, "A", "THUMB", "news")["candidates"], 1)
        self.assertEqual(summarize(dataset, 100, "A", "THUMB", "notes")["trials"], 0)
        self.assertAlmostEqual(summarize(dataset, 1000, "A")["perMinute"], 1.5)

    def test_500_ms_mismatch_is_visible_not_silently_recounted(self):
        bad = trial("bad", "A5", "news", "THUMB", [
            dict(objectID="article", durationMs="700", candidate="true")], candidates=0)
        with self.assertRaisesRegex(ValueError, "candidate mismatch"):
            build_dataset([bad], [])


if __name__ == "__main__":
    unittest.main()
