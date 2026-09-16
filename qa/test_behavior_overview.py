import math
import unittest
from analyze_behavior_overview import loop_candidate,pre_target_hover,fit_ab,predict


class BehaviorOverviewTests(unittest.TestCase):
    def points(self,radius=65,angle=2*math.pi):
        return [dict(t=i/60,x=195+radius*math.cos(angle*i/60),y=415+radius*math.sin(angle*i/60),sequence=i,source='PENCIL_HOVER')for i in range(61)]

    def test_raw_closed_loop_vs_small_jitter_and_open_path(self):
        result=loop_candidate(self.points())
        self.assertIsNotNone(result)
        self.assertGreater(result['area'],10000)
        self.assertLessEqual(result['distance'],20)
        self.assertTrue(result['algorithmClosingEdge'])
        self.assertIn(result['seq0'],range(61));self.assertIn(result['seq1'],range(61))
        self.assertIsNone(loop_candidate(self.points(radius=4)))
        self.assertIsNone(loop_candidate(self.points(angle=math.pi)))

    def test_missing_callbacks_cannot_form_a_loop(self):
        points=self.points()
        for p in points[30:]:p['t']+=.2
        with self.assertRaises(ValueError):loop_candidate(points)
        self.assertIsNone(loop_candidate(points[:30]))
        self.assertIsNone(loop_candidate(points[30:]))

    def test_target_hover_excludes_starting_dwell_and_uses_circle(self):
        def ps(a,b,x=195,y=195):
            return [dict(t=i/100,x=x,y=y,sequence=i,source='PENCIL_HOVER')for i in range(a,b+1,2)]
        # Corners of a target bounding box are outside the rendered circle.
        tr=dict(trial=dict(objects=[dict(id='target',bounds=dict(x=185,y=185,width=20,height=20))]),duration=2,events=[dict(type='TARGET_PRESENT_REQUEST',t=1)],segments=[ps(0,50),ps(100,120,186,186),ps(125,145),ps(155,175)])
        result=pre_target_hover(tr)
        self.assertAlmostEqual(result['preTargetHover_ms'],200)
        self.assertEqual(result['targetHoverPoints'],22)
        # A later TOUCH segment limits the usable target dwell.
        tr['segments'].append([dict(t=1.4,x=195,y=195,source='PENCIL_TOUCH')])
        self.assertAlmostEqual(pre_target_hover(tr)['preTargetHover_ms'],140)

    def test_c_labels_and_features_do_not_change_ab_fit(self):
        rows=[]
        for task,label,base in [('A5',0,80),('A6',0,120),('B1',1,30),('B2',1,40)]:
            for i in range(3):rows.append(dict(task=task,label=label,trialID=task,speed_median_pt_s=base+i,rms_pt=base/8+i))
        model=fit_ab(rows)
        extra=[dict(task='C3',label=1,trialID='test',speed_median_pt_s=float('nan'),rms_pt=float('nan'))]
        self.assertEqual(model,fit_ab(rows+extra))
        self.assertFalse(model['cUsedForFit'])
        self.assertEqual(model['trainPositive'],6);self.assertEqual(model['trainNegative'],6)
        clean=dict(speed_median_pt_s=32,rms_pt=5)
        changed=dict(clean,task='C3',label=0,condition='NATURAL',scene='video',event='CANDIDATE')
        self.assertAlmostEqual(predict(model,[clean])[0],predict(model,[changed])[0])


if __name__=='__main__':unittest.main()
