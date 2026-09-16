import unittest
from kinematics import derive


def trial(times, xs, segments=None):
    points=[[time, x, 200, .4, 0, 'CHANGED', i+1, None, None, 'CHANGED', 'PENCIL_HOVER', 'PENCIL']
            for i,(time,x) in enumerate(zip(times,xs))]
    return {'id':'synthetic','index':1,'distance':120,'target':[50,200,30],
            'success':True,'points':points,'segments':segments or [list(range(len(points)))],
            'events':[{'type':'TOUCH_DOWN','t':100}]}


class KinematicsTests(unittest.TestCase):
    def test_constant_velocity_with_unequal_intervals(self):
        result,rows=derive(trial([0,10,30,60],[0,1,3,6]))
        self.assertEqual([p[1] for p in result['curves']['speed'][0]],[100,100,100])
        self.assertTrue(all(abs(p[1])<1e-10 for p in result['curves']['acceleration'][0]))
        self.assertEqual(result['touchMs'],100)

    def test_known_acceleration_with_unequal_intervals(self):
        result,rows=derive(trial([0,10,30,60],[0,.005,.045,.18]))
        for r in rows:
            if r['metric']=='acceleration':
                self.assertAlmostEqual(r['value'],100)
                self.assertAlmostEqual(r['ax'],100)
                self.assertAlmostEqual(r['ay'],0)
                self.assertAlmostEqual(r['accelerationMagnitude'],100)

    def test_no_derivative_across_segment_boundary(self):
        result,rows=derive(trial([0,10,20,30],[0,1,1000,1001],[[0,1],[2,3]]))
        self.assertEqual(len(result['curves']['speed']),2)
        self.assertEqual(result['curves']['acceleration'],[])
        self.assertEqual([r['supportSequences'] for r in rows if r['metric']=='speed'],['1;2','3;4'])

    def test_braking_has_negative_signed_rate(self):
        result,rows=derive(trial([0,10,20],[0,2,3]))
        self.assertAlmostEqual(result['curves']['acceleration'][0][0][1],-10000)
        self.assertAlmostEqual(next(r['accelerationMagnitude'] for r in rows if r['metric']=='acceleration'),10000)


if __name__=='__main__':
    unittest.main()
