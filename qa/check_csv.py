#!/usr/bin/env python3
"""Check a real or simulated research CSV without changing it."""
import argparse, csv, json, math, statistics
from pathlib import Path
from collections import defaultdict, Counter
p=argparse.ArgumentParser()
p.add_argument('csv',type=Path)
p.add_argument('--pandas',action='store_true',help='Also load with pandas.read_csv')
p.add_argument('--require-tests',action='store_true',help='Require successful Test 0–4 (for smoke fixtures)')
p.add_argument('--output',type=Path)
args=p.parse_args()
errors=[]; warnings=[]
with args.csv.open(encoding='utf-8',newline='') as f:
 reader=csv.DictReader(f); columns=reader.fieldnames; rows=list(reader)
required={'schemaVersion','sequence','recordType','timestamp','monotonicTime','participantID','sessionID','testID','trialID','taskInstruction','plannedIndex','plannedTotal','remainingAfterCurrent','conditionID','trialState','localX','localY','sampleSource','timestampSource','metadata'}
if not required.issubset(set(columns or [])): errors.append('Missing required columns')
previous=0
trials=defaultdict(list)
synthetic=args.csv.name.startswith('SIMULATED_')
for n,row in enumerate(rows,2):
 if None in row or any(v is None for v in row.values()): errors.append(f'Line {n}: inconsistent column count');continue
 try:
  seq=int(row['sequence']);assert seq>previous;previous=seq
 except Exception: errors.append(f'Line {n}: invalid/non-increasing sequence')
 source=row.get('sampleSource','')
 if source and source.startswith('SIMULATED') != synthetic: errors.append(f'Line {n}: mixed simulated/real input')
 if row.get('recordType') not in {'SAMPLE','EVENT'}:errors.append(f'Line {n}: invalid record type')
 if row.get('metadata'):
  try:json.loads(row['metadata'])
  except Exception:errors.append(f'Line {n}: invalid metadata JSON')
 if row.get('recordType')=='SAMPLE':
  for name in ['monotonicTime','receivedMonotonicTime','x','y','localX','localY']:
   try:assert math.isfinite(float(row[name]))
   except Exception:errors.append(f'Line {n}: invalid {name}')
  try:
   assert abs(float(row['x'])-976-float(row['localX']))<1e-6
   assert abs(float(row['y'])-194-float(row['localY']))<1e-6
  except Exception:errors.append(f'Line {n}: inconsistent global/local coordinates')
 if row.get('trialID'):trials[row['trialID']].append(row)
windows=[]; intervals=[]; instructions=[]
for trialID,items in trials.items():
 relevant=[r for r in items if r['recordType']=='SAMPLE' or r.get('eventType') in {'TRIAL_START','TRIAL_END','TOUCH_DOWN','TARGET_ENTER','TARGET_EXIT','SWIPE_START','SWIPE_END'}]
 taskset={r['taskInstruction'] for r in relevant}
 if len(taskset)>1:errors.append(f'{trialID}: displayed task changed within trial')
 for r in relevant:
  try:
   idx,total,remaining=map(int,(r['plannedIndex'],r['plannedTotal'],r['remainingAfterCurrent']))
   assert 1<=idx<=total and remaining==total-idx
  except Exception:errors.append(f'{trialID}: invalid participant progress')
 if relevant:instructions.append({'trialID':trialID,'instruction':relevant[0]['taskInstruction'],'condition':relevant[0]['conditionID']})
 hover=sorted(float(r['monotonicTime']) for r in items if r['recordType']=='SAMPLE' and 'HOVER' in r['sampleSource'] and r['hoverState'] not in {'ENDED','CANCELLED'})
 intervals += [(b-a)*1000 for a,b in zip(hover,hover[1:]) if b>a]
 for touch in [r for r in items if r.get('eventType')=='TOUCH_DOWN']:
  t=float(touch['monotonicTime']);prior=[v for v in hover if v<=t];pre=[v for v in prior if v>=t-0.6]
  spans600=bool(prior and min(prior)<=t-0.6)
  gaps=[(b-a)*1000 for a,b in zip(pre,pre[1:])]
  windows.append({'trialID':trialID,'touchMonotonicTime':t,'samplesInLast600ms':len(pre),'earliestSampleBeforeTouchMs':round((t-min(pre))*1000,3) if pre else None,'recordingBeganBeforeTouchMs':round((t-min(prior))*1000,3) if prior else None,'lastSampleBeforeTouchMs':round((t-max(pre))*1000,3) if pre else None,'maxCallbackGapInWindowMs':max(gaps) if gaps else None,'preTouchCoverage':spans600,'coverageMeaning':'Recorded range starts before -600 ms; individual sample spacing is reported separately, with no interpolation or hardware continuity claim.'})
  if not pre:warnings.append(f'{trialID}: no hover samples in 600 ms before touch; retain as coverage gap')
  elif not spans600:warnings.append(f'{trialID}: recording began only {(t-min(prior))*1000:.1f} ms before touch; retain as coverage gap')
events=Counter(r.get('eventType') for r in rows if r.get('eventType'))
successful=sorted({int(r['testID']) for r in rows if r.get('eventType')=='TRIAL_END' and r.get('success')=='true' and r['testID'].isdigit()})
if args.require_tests and successful != [0,1,2,3,4]:errors.append(f'Successful tests {successful}; expected [0,1,2,3,4]')
successful_v2=sorted({r['testID'] for r in rows if r.get('eventType')=='TRIAL_END' and r.get('success')=='true' and not r['testID'].isdigit()})
pandas_result=None
if args.pandas:
 import pandas as pd
 df=pd.read_csv(args.csv);pandas_result={'version':pd.__version__,'rows':len(df),'columns':len(df.columns)}
 if len(df)!=len(rows):errors.append('pandas row count differs from CSV parser')
report={'status':'PASS' if not errors else 'FAIL','file':str(args.csv.resolve()),'simulated':synthetic,'rows':len(rows),'samples':sum(r.get('recordType')=='SAMPLE' for r in rows),'events':dict(events),'successfulTests':successful,'successfulV2Tasks':successful_v2,'callbackIntervalsMs':{'count':len(intervals),'median':statistics.median(intervals) if intervals else None,'max':max(intervals) if intervals else None},'touchWindows':windows,'pandas':pandas_result,'instructions':instructions,'errors':errors,'warnings':warnings,'limits':'Callback intervals are delivered API intervals, not proof of hardware sampling rate. Display-frame markers are not photometric measurements.'}
encoded=json.dumps(report,ensure_ascii=False,indent=2)
if args.output:args.output.write_text(encoded+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in {'instructions','touchWindows'}},ensure_ascii=False,indent=2))
raise SystemExit(1 if errors else 0)
