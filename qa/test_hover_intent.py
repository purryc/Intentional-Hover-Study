import unittest
from explore_hover_intent import annotate, window_features, cross_run


class HoverIntentTests(unittest.TestCase):
    def test_user_override_requires_menu_then_b_and_only_wrong_item(self):
        def trial(error, events):
            return dict(task='B1',success=False,error=error,events=events)
        events=[dict(type='MENU_OPEN',metadata={}),dict(type='MENU_SELECT',metadata=dict(item='B'))]
        t=trial('WRONG_MENU_ITEM',events);annotate(t)
        self.assertTrue(t['success']);self.assertFalse(t['rawSuccess'])
        self.assertEqual(t['rawError'],'WRONG_MENU_ITEM');self.assertEqual(t['reportedHand'],'RIGHT')
        annotate(t);self.assertFalse(t['rawSuccess'])
        for err,ev in [('UNEXPECTED_TOUCH',events),('WRONG_MENU_ITEM',events[1:]),('WRONG_MENU_ITEM',list(reversed(events))),('WRONG_MENU_ITEM',[events[0],dict(type='MENU_SELECT',metadata=dict(item='A'))])]:
            t=trial(err,ev);annotate(t);self.assertFalse(t['success'])

    def test_window_excludes_future_and_never_combines_short_segments(self):
        points=[dict(t=i/60,x=i,y=0,z=.5,source='PENCIL_HOVER',inputSequence=i)for i in range(61)]
        points[31]['x']=10000
        f=window_features(dict(segments=[points]),0,.5)
        self.assertEqual(f['points'],31);self.assertEqual(f['last_input_sequence'],30)
        self.assertAlmostEqual(f['speed_median_pt_s'],60)
        self.assertIsNone(window_features(dict(segments=[points[:16],points[16:31]]),0,.5))
        points[16]['t']=points[15]['t']
        self.assertIsNone(window_features(dict(segments=[points]),0,.5))

    def test_cross_run_holds_out_every_trial_in_other_run(self):
        rows=[]
        for run in ['拇指','食指']:
            for label in [0,1]:
                for i in range(4):
                    rows.append(dict(task='C3',run=run,label=label,scene='news',trialID=run+str(label)+str(i),speed_median_pt_s=100 if not label else 10,rms_pt=15 if not label else 2))
        result=cross_run(rows)
        self.assertEqual(len(result),2)
        self.assertTrue(all(v['train']!=v['test'] and v['train_trials']==8 and v['test_trials']==8 for v in result))
        self.assertTrue(all(v['auc']==1 for v in result))


if __name__=='__main__':unittest.main()
