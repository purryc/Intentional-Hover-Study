import unittest
from analyze_home_position import natural_windows,hotspot,acquisition,fraction_inside,suppress


class HomePositionTests(unittest.TestCase):
    def row(self,x=200,elapsed=1,trial='natural'):
        return dict(cx=x,cy=400,elapsedEnd=elapsed,trialID=trial,scene='news',observed_ms=480,z_median_raw=.4,rms_pt=3,speed_median_pt_s=30)

    def test_prefix_does_not_use_future_positions(self):
        early=[self.row(elapsed=i*.5+.5)for i in range(8)]
        future=[self.row(x=350,elapsed=40+i*.5,trial='future')for i in range(30)]
        a=acquisition(early,dict(train=hotspot(early),replicated=False))
        b=acquisition(early+future,dict(train=hotspot(early+future),replicated=False))
        self.assertEqual(a['checkpoints'][1]['model'],b['checkpoints'][1]['model'])
        self.assertEqual(b['checkpoints'][1]['model']['trainIDs'],['natural'])
        self.assertEqual(b['firstCandidate_s'],5)
        self.assertIsNone(b['retrospectiveStable_s'])

    def test_minimum_main_cluster_support_and_no_intent_labels(self):
        rows=[self.row()for _ in range(5)]
        self.assertFalse(hotspot(rows)['available'])
        rows.append(self.row());a=hotspot(rows)
        self.assertTrue(a['available'])
        changed=[dict(r,label=1,condition='HOVER',objectID='target',task='B2')for r in rows]
        self.assertEqual(a,hotspot(changed))
        self.assertFalse(suppress(rows[0],.79,True))
        self.assertTrue(suppress(rows[0],.8,True))
        self.assertFalse(suppress(rows[0],1,False))

    def test_coverage_is_time_weighted_and_rejects_gaps(self):
        points=[dict(t=i*.002,x=200,y=400)for i in range(10)]+[dict(t=t,x=300,y=400)for t in [.020,.07,.12]]
        model=hotspot([self.row()for _ in range(6)])
        self.assertAlmostEqual(fraction_inside(points,model),1/6)
        points[-1]['t']=.5
        with self.assertRaises(ValueError):fraction_inside(points,model)

    def test_windows_do_not_join_fragments_or_include_starting_dwell(self):
        def seg(a,b,source='PENCIL_HOVER'):
            return [dict(t=i/100,x=200,y=400,z=.4,inputSequence=i,sequence=i,source=source)for i in range(a,b+1,2)]
        tr=dict(id='n',run='拇指',scene='news',duration=3,events=[dict(type='TARGET_PRESENT_REQUEST',t=1)],segments=[seg(0,60),seg(100,122),seg(130,152),seg(200,260,'PENCIL_TOUCH')])
        self.assertEqual(natural_windows(tr),[])
        tr['segments'].append(seg(200,260))
        rows=natural_windows(tr)
        self.assertEqual(len(rows),1)
        self.assertGreaterEqual(rows[0]['first_t'],1)
        self.assertGreaterEqual(rows[0]['first_input_sequence'],200)


if __name__=='__main__':unittest.main()
