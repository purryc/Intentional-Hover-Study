import unittest
from build_motion_study import signed_motion,selections


class MotionPhaseTests(unittest.TestCase):
    def p(self,t,x,y=0,seq=0):
        return dict(t=t,x=x,y=y,z=.5,source='PENCIL_HOVER',sequence=seq,inputSequence=seq)

    def test_speed_rate_distinguishes_slowdown_from_constant_speed_turn(self):
        rows=signed_motion([self.p(0,0,0,1),self.p(.1,10,0,2),self.p(.2,10,10,3),self.p(.3,10,15,4)])
        self.assertAlmostEqual(rows[1]['speedRate'],0)
        self.assertGreater(rows[1]['vectorAcceleration'],1000)
        self.assertAlmostEqual(rows[2]['speedRate'],-500)
        self.assertEqual((rows[2]['rateSeq0'],rows[2]['rateSeq1'],rows[2]['rateSeq2']),(2,3,4))
        self.assertAlmostEqual(rows[2]['rateTime'],.2)

    def test_gap_and_tiny_support_reset_derivative(self):
        rows=signed_motion([self.p(0,0),self.p(.1,10),self.p(.5,50),self.p(.6,60)])
        self.assertEqual(len(rows),2);self.assertIsNone(rows[1]['speedRate'])
        rows=signed_motion([self.p(0,0),self.p(.1,10),self.p(.1001,11),self.p(.2,20)])
        self.assertIsNone(rows[1]['speedRate'])

    def test_dwell_cannot_use_separate_approach_segment(self):
        dwell=[self.p(i/60,i*.1,seq=i)for i in range(31)]
        approach=[self.p(-.3+i/60,0,seq=100+i)for i in range(18)]
        tr=dict(id='t',run='拇指',index=1,start=0,segments=[approach,dwell],events=[dict(type='HOVER_SELECT',t=.5,metadata=dict(startTime='0',objectID='t0'))])
        result=selections(tr)[0]
        self.assertFalse(result['continuousComparison']);self.assertIsNotNone(result['dwellSpeed_pt_s'])


if __name__=='__main__':unittest.main()
