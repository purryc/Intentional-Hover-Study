#!/usr/bin/env python3
"""Read-only V2 reconstruction. Keep legacy rows compatible; never alter input CSV."""
import argparse,csv,hashlib,json,math,shutil
from pathlib import Path

def decoded(value,default=None):
    try:return json.loads(value)
    except (ValueError,TypeError):return default

def reconstruct(source):
    trials={};legacy=0
    with Path(source).open(newline='',encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            m=decoded(row.get('metadata'),{})
            if m.get('protocolVersion') not in ('HOVER_INTENT_V2_1','HOVER_INTENT_V2_2','HOVER_INTENT_V2_3','HOVER_INTENT_V2_4'):legacy+=1;continue
            if not row.get('trialID'):continue
            tid=row['trialID'];tr=trials.setdefault(tid,dict(id=tid,task=row['testID'],group=m.get('taskGroup'),scene=m.get('scene'),posture=m.get('posture'),condition=m.get('condition'),instruction=row.get('taskInstruction'),index=int(row.get('plannedIndex') or 0),total=int(row.get('plannedTotal') or 0),session=row.get('sessionID'),repeat=row.get('isRepeat')=='true',raw=[],gaze=[],events=[],trial={}))
            time=float(row['monotonicTime'])
            if row['recordType']=='EVENT':
                event=dict(t=time,type=row['eventType'],metadata=m);tr['events'].append(event)
                if row['eventType']=='TRIAL_START':tr['trial']=decoded(m.get('trial'),{});tr['start']=time
                if row['eventType']=='TRIAL_END':tr['success']=row.get('success')=='true';tr['error']=row.get('errorType')
            elif row.get('inputType')=='GAZE':
                tr['gaze'].append(dict(t=time,x=float(row['localX']) if row.get('localX') else None,y=float(row['localY']) if row.get('localY') else None,rawX=float(m['rawCameraPlaneX']) if m.get('rawCameraPlaneX') else None,rawY=float(m['rawCameraPlaneY']) if m.get('rawCameraPlaneY') else None,frameTime=float(m['arFrameTimestamp']) if m.get('arFrameTimestamp') else None,quality=m.get('gazeQuality'),validity=m.get('gazeValidity'),objectID=m.get('gazeObjectID'),calibrationID=m.get('calibrationID'),sequencePhase=m.get('sequencePhase','TASK'),sequence=int(row['sequence'])))
            else:
                tr['raw'].append(dict(t=time,x=float(row['localX']),y=float(row['localY']),z=float(row['zOffset']) if row.get('zOffset') else None,source=row['sampleSource'],input=row['inputType'],phase=row.get('hoverState') or row.get('touchState'),sequencePhase=m.get('sequencePhase','TASK'),sequence=int(row['sequence']),inputSequence=int(m.get('inputSequence') or 0)))
    for tr in trials.values():
        tr['start']=tr.get('start',min([p['t'] for p in tr['raw']]+[p['t'] for p in tr['gaze']]+[ev['t'] for ev in tr['events']]))
        begin=None;pollution=[]
        for ev in tr['events']:
            if ev['type']=='POLLUTION_START':begin=ev['t'] if begin is None else begin
            if ev['type']=='POLLUTION_END' and begin is not None:pollution.append([begin,ev['t']]);begin=None
        if begin is not None:pollution.append([begin,math.inf])
        segments=[];segment=[];excluded={};previous=None
        for p in tr.pop('raw'):
            reason='finger' if p['input']!='PENCIL' else 'outside' if not (0<=p['x']<=390 and 0<=p['y']<=830) else 'pollution' if any(a<=p['t']<=b for a,b in pollution) else 'hoverEnd' if 'HOVER' in p['source'] and p['phase'] in ('ENDED','CANCELLED') else None
            if reason:
                excluded[reason]=excluded.get(reason,0)+1
                if segment:segments.append(segment);segment=[]
                previous=None;continue
            if previous and (p['t']-previous['t']>0.1+1e-9 or p['t']<=previous['t'] or p['source']!=previous['source'] or p['phase']=='BEGAN' or previous['phase'] in ('ENDED','CANCELLED')):
                if segment:segments.append(segment);segment=[]
            p['t']-=tr['start'];segment.append(p);previous=dict(p,t=p['t']+tr['start'])
        if segment:segments.append(segment)
        tr['segments']=segments;tr['exclusions']=excluded
        for gaze in tr['gaze']:gaze['t']-=tr['start']
        for ev in tr['events']:ev['t']-=tr['start']
        tr['duration']=max([p['t'] for seg in segments for p in seg]+[ev['t'] for ev in tr['events']]+[0.001])
        tr['pollution']=[[a-tr['start'],None if math.isinf(b) else b-tr['start']] for a,b in pollution]
        tr['motion']=[]
        for si,seg in enumerate(segments):
            previous_v=None
            for a,b in zip(seg,seg[1:]):
                dt=b['t']-a['t'];vx=(b['x']-a['x'])/dt;vy=(b['y']-a['y'])/dt;tv=(a['t']+b['t'])/2
                row=dict(t=tv,speed=math.hypot(vx,vy),segment=si,seq0=a['sequence'],seq1=b['sequence'],acceleration=None,accelerationTime=None,accelSeq0=None,accelSeq1=None,accelSeq2=None)
                if previous_v:
                    vt,pvx,pvy,pseq=previous_v;row['acceleration']=math.hypot(vx-pvx,vy-pvy)/(tv-vt);row['accelerationTime']=(tv+vt)/2;row['accelSeq0']=pseq;row['accelSeq1']=a['sequence'];row['accelSeq2']=b['sequence']
                previous_v=tv,vx,vy,a['sequence'];tr['motion'].append(row)
        candidates=[ev for ev in tr['events'] if ev['type']=='CANDIDATE']
        tr['metrics']=dict(candidates=len(candidates),candidatesPerMinute=len(candidates)*60/tr['duration'],dwellSegments=[ev['metadata'] for ev in tr['events'] if ev['type']=='DWELL_END'],lasso=[ev['metadata'] for ev in tr['events'] if ev['type']=='LASSO_CLOSE'],interruptions=sum(ev['type']=='LASSO_CANCEL' for ev in tr['events']))
        tr['coverage']=[]
        for ev in tr['events']:
            if ev['type']!='TOUCH_DOWN':continue
            intervals=[]
            for seg in segments:
                if not seg or 'HOVER' not in seg[0]['source']:continue
                for a,b in zip(seg,seg[1:]):
                    lo=max(ev['t']-.6,a['t']);hi=min(ev['t'],b['t'])
                    if hi>lo:intervals.append((lo,hi))
            coverage=sum(b-a for a,b in intervals)
            tr['coverage'].append(dict(t=ev['t'],observedMs=coverage*1000,windowMs=600))
    return dict(source=Path(source).name,sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(),legacyRows=legacy,trials=list(trials.values()))

def build(source,out):
    root=Path(__file__).resolve().parents[1];out=Path(out);out.mkdir(parents=True,exist_ok=True)
    data=reconstruct(source) if source else dict(source='尚未导入 V2 CSV',trials=[])
    text=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    (out/'replay-v2.html').write_text((root/'qa/v2_replay.html').read_text().replace('__DATA__',text))
    shutil.copyfile(root/'qa/v2_replay.js',out/'v2_replay.js')
    shutil.copytree(root/'src/App/StudyMedia',out/'Resources',dirs_exist_ok=True)
    vendor=root/'qa/vendor'
    if not vendor.exists():vendor=root/'analysis/trajectory_2026-09-15/vendor'
    if (out/'vendor').resolve()!=vendor.resolve():shutil.copytree(vendor,out/'vendor',dirs_exist_ok=True)
    (out/'v2_trajectories.json').write_text(text)
    rows=[dict(trialID=t['id'],task=t['task'],condition=t['condition'],**m) for t in data['trials'] for m in t['motion']]
    with (out/'v2_motion.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['trialID','task','condition','t','speed','segment','seq0','seq1','acceleration','accelerationTime','accelSeq0','accelSeq1','accelSeq2']);writer.writeheader();writer.writerows(rows)
    print(json.dumps(dict(trials=len(data['trials']),motionRows=len(rows),source=data['source'],output=str(out/'replay-v2.html')),ensure_ascii=False))
    return data
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',nargs='?');p.add_argument('--output',required=True);a=p.parse_args();build(a.source,a.output)
