import unittest
from analyze_two_runs import SID, metrics, weighted


class TwoRunAnalysisTests(unittest.TestCase):
    def test_time_weighted_quantiles_do_not_count_callbacks_equally(self):
        self.assertEqual(weighted([1000, 10], [.001, 1]), 10)
        self.assertEqual(weighted([10, 1000], [1, .001], .95), 10)

    def test_vector_acceleration_support_and_tiny_interval_flag(self):
        def p(t, x, y, seq):
            return dict(t=t, x=x, y=y, z=.5, sequence=seq, source='PENCIL_HOVER')
        trial = dict(session=SID[0],id='test',task='B2',condition='HOVER',scene='abstract',posture='THUMB',index=1,repeat=False,trial=dict(distance=220,diameter=50,direction=-1,requested=['t0']),success=True,error='',duration=.4,exclusions={},coverage=[],events=[dict(t=0,type='TARGET_PRESENT_REQUEST',metadata={}),dict(t=.4,type='TRIAL_END',metadata={})],segments=[[p(0,0,0,1),p(.1,10,0,2),p(.2,10,10,3)],[p(.3,20,20,4),p(.3001,21,20,5)]])
        trial['segments'].append([p(.5,30,30,6),p(.6,100,100,7)])
        row=metrics(trial)
        self.assertEqual(trial['exclusions']['outsideTrial'],2)
        self.assertEqual(len(trial['segments']),2)
        self.assertEqual(row['tiny_edge_count'],1)
        self.assertAlmostEqual(row['hover_speed_median'],100)
        motion=trial['motion'][1]
        self.assertAlmostEqual(motion['acceleration'],2**.5*1000)
        self.assertAlmostEqual(motion['accelerationTime'],.1)
        self.assertEqual((motion['accelSeq0'],motion['accelSeq1'],motion['accelSeq2']),(1,2,3))
        self.assertFalse(trial['motion'][2]['primarySpeed'])
        self.assertIsNone(trial['motion'][2]['acceleration'])


if __name__=='__main__':unittest.main()
