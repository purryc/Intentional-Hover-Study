import unittest

from analyze_v23_run import plan_summary, prepare, target_exposure


def event(t, kind, meta=None):
    return dict(t=t, type=kind, metadata=meta or {})


def trial(identifier, task, success, error, attempt, events=None):
    events = events or []
    return dict(id=identifier, session="session-1", posture="THUMB", task=task,
                scene="abstract", condition="HOVER", start=100 + attempt,
                duration=1.2, success=success, error=error, trial=dict(ordinal=1, requested=[]),
                events=[event(0, "TRIAL_START", dict(sessionPlannedIndex="7", attempt=str(attempt),
                                                     redoOf="first" if attempt > 1 else ""))]
                + events + [event(1, "TRIAL_END")],
                segments=[[dict(t=.5, x=100, y=100, source="PENCIL_HOVER"),
                           dict(t=1.1, x=101, y=101, source="PENCIL_HOVER")]],
                exclusions={})


class NewRunAnalysisTests(unittest.TestCase):
    def test_planned_question_counts_retry_without_doubling_progress(self):
        attempts = [trial("first", "C2", False, "UNEXPECTED_TOUCH", 1),
                    trial("second", "C2", True, "", 2)]
        prepare(attempts)
        rows = plan_summary(attempts)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["attempts"], 2)
        self.assertFalse(rows[0]["firstRawSuccess"])
        self.assertTrue(rows[0]["eventualRawSuccess"])
        self.assertEqual(attempts[0]["exclusions"]["outsideTrial"], 1)

    def test_prior_menu_b_clarification_preserves_raw_failure(self):
        attempt = trial("menu", "B1", False, "WRONG_MENU_ITEM", 1,
                        [event(.5, "MENU_OPEN"), event(.8, "MENU_SELECT", {"item": "B"})])
        prepare([attempt])
        self.assertFalse(attempt["rawSuccess"])
        self.assertEqual(attempt["rawError"], "WRONG_MENU_ITEM")
        self.assertTrue(attempt["actionSuccess"])
        self.assertEqual(attempt["override"], "PRIOR_USER_B_ACTION_REVIEW")

    def test_object_move_breaks_exposure_without_joining_positions(self):
        a = dict(x=10, y=90, width=48, height=48)
        b = dict(x=100, y=90, width=48, height=48)
        obj = lambda bounds: '[{"id":"butterfly","bounds":' + __import__("json").dumps(bounds) + "}]"
        tr = dict(id="target", run="拇指", scene="news", condition="NATURAL",
                  planNumber=8, rawSuccess=True, attempt=1,
                  trial=dict(requested=["butterfly"]),
                  events=[event(0, "TARGET_PRESENT_REQUEST", {"selectionObjects": obj(a)}),
                          event(.1, "SCENE_STATE", {"selectionObjects": obj(b)})],
                  segments=[[dict(t=.02, x=20, y=100, source="PENCIL_HOVER"),
                             dict(t=.04, x=21, y=101, source="PENCIL_HOVER"),
                             dict(t=.12, x=120, y=100, source="PENCIL_HOVER"),
                             dict(t=.14, x=121, y=101, source="PENCIL_HOVER")]])
        result = target_exposure(tr)
        self.assertEqual(result["insidePoints"], 4)
        self.assertEqual(result["visits"], 2)
        self.assertAlmostEqual(result["insideObserved_s"], .04)
        self.assertAlmostEqual(result["hoverObserved_s"], .12)


if __name__ == "__main__":
    unittest.main()
