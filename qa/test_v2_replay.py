import csv,json,tempfile,unittest
from pathlib import Path
from build_v2_replay import reconstruct

class V2ReplayTests(unittest.TestCase):
    def test_pollution_intervals_gaps_and_zero_touch_lasso(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'SIMULATED.csv';rows=[]
            base=dict(trialID='lasso-test',testID='B4',plannedIndex='1',plannedTotal='6',sessionID='sim',isRepeat='false',taskInstruction='圈选')
            meta=dict(protocolVersion='HOVER_INTENT_V2_1',taskGroup='B',taskID='B4',posture='THUMB',scene='abstract',condition='HOVER')
            def event(t,kind,**extra):rows.append(dict(base,recordType='EVENT',monotonicTime=t,eventType=kind,metadata=json.dumps(dict(meta,**extra))))
            def sample(t,x=100,input='PENCIL',phase='CHANGED'):
                rows.append(dict(base,recordType='SAMPLE',monotonicTime=t,localX=x,localY=200,zOffset=.5,sampleSource='SIMULATED_HOVER',inputType=input,hoverState=phase,sequence=len(rows)+1,metadata=json.dumps(dict(meta,inputSequence=len(rows)+1))))
            event(10,'TRIAL_START',trial=json.dumps(dict(task='B4',objects=[])))
            for t in [10,10.02,10.04]:sample(t)
            event(10.05,'POLLUTION_START');sample(10.06,input='FINGER');sample(10.08);event(10.1,'POLLUTION_END')
            for t in [10.12,10.14,10.4,10.42]:sample(t)
            sample(10.44,x=-1);sample(10.46);sample(10.48)
            event(10.5,'LASSO_CLOSE',algorithmicClosingEdge='[{"x":1,"y":2},{"x":2,"y":2}]',selected='["t1"]')
            event(10.51,'TRIAL_END')
            keys=sorted(set().union(*(r.keys() for r in rows)))
            with path.open('w',newline='') as f:w=csv.DictWriter(f,keys);w.writeheader();w.writerows(rows)
            tr=reconstruct(path)['trials'][0]
            self.assertEqual([len(s) for s in tr['segments']],[3,2,2,2]);self.assertEqual(tr['exclusions'],dict(finger=1,pollution=1,outside=1));self.assertEqual(tr['coverage'],[])
            self.assertEqual(len(tr['motion']),5);self.assertEqual(tr['metrics']['lasso'][0]['selected'],'["t1"]')
            for s in tr['segments']:
                for a,b in zip(s,s[1:]):self.assertLessEqual(b['t']-a['t'],.100001)
    def test_legacy_read_only(self):
        root=Path(__file__).resolve().parents[1];source=root/'data/HoverIntent_2026-09-15.csv'
        if not source.exists():self.skipTest('legacy data not on this machine')
        data=reconstruct(source);self.assertEqual(data['trials'],[]);self.assertEqual(data['sha256'],'c91d9bd0d4cce8736b9c0264f0883df42e17224fcd9ac32579f1685ebb4cb1a8')
if __name__=='__main__':unittest.main()
