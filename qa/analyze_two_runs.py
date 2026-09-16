#!/usr/bin/env python3
"""Descriptive mounted-Pencil comparison; input CSV is never modified."""
import argparse, collections, csv, hashlib, json, math, shutil, sys
from pathlib import Path
import numpy as np
from build_v2_replay import reconstruct, decoded
from explore_hover_intent import annotate, explore

TASKS = ['A1','A2','A3','A4','A5','A6','A7','B1','B2','B3','B4','C1','C2','C3']
TITLES = dict(zip(TASKS,['点击','拖动','垂直滚动','水平滚动','长文阅读','图文浏览','视频浏览','悬停菜单','悬停单选','悬停多选','空中圈选','点击 vs Hover','滚动 vs Hover','阅读 vs Hover']))
SID = ['F9F2D288-18CB-47C8-997E-FA7B3712BF07','BC455353-6D6E-49CD-9A85-00735E40660C']
LABELS = dict(zip(SID,['拇指','食指']))
COLORS = ['#ee8743','#288bce']

def weighted(values, weights, q=.5):
    if not values: return None
    v=np.asarray(values);w=np.asarray(weights);order=np.argsort(v);v=v[order];w=w[order]
    return float(v[min(len(v)-1,np.searchsorted(np.cumsum(w),q*w.sum()))])

def med(values):
    v=[x for x in values if x is not None and math.isfinite(x)]
    return float(np.median(v)) if v else None

def fmt(x, digits=2): return '—' if x is None else f'{x:.{digits}f}'

def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows])

def inventory(source):
    sessions={};counts=collections.Counter();invalid=[];seq_last=None;quality=collections.Counter()
    with source.open(newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f);fields=reader.fieldnames
        for line,r in enumerate(reader,2):
            if None in r or any(v is None for v in r.values()): invalid.append(line);continue
            counts[r['recordType']]+=1
            m=decoded(r.get('metadata'),{});s=sessions.setdefault(r['sessionID'],dict(rows=0,samples=0,first=r['timestamp'],last=r['timestamp'],firstTime=float(r['monotonicTime']),lastTime=float(r['monotonicTime']),protocol=m.get('protocolVersion','legacy'),posture=m.get('posture'),sourceCounts=collections.Counter(),taskEnds=collections.Counter(),simulation=None))
            s['rows']+=1;s['last']=r['timestamp'];s['lastTime']=float(r['monotonicTime'])
            if r['eventType']=='SESSION_START':s['config']=decoded(m.get('config'),{});s['simulation']=m.get('simulation');s['seed']=r['randomSeed']
            if r['recordType']=='SAMPLE':
                s['samples']+=1;s['sourceCounts'][r['sampleSource']]+=1
                if r['sessionID'] in SID:
                    quality[r['sampleSource']]+=1
            if r['eventType']=='TRIAL_END':s['taskEnds'][r['testID']]+=1
    return dict(source=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),bytes=source.stat().st_size,fields=len(fields),rows=dict(counts),invalidCSVLines=invalid,sessions=sessions,selectedSources=dict(quality))

def metrics(tr):
    annotate(tr)
    tr['run']=LABELS[tr['session']]
    end_time=next((e['t'] for e in tr['events'] if e['type']=='TRIAL_END'),tr['duration'])
    clipped=[];outside_trial=0
    for segment in tr['segments']:
        points=[p for p in segment if 0<=p['t']<=end_time+1e-9]
        outside_trial+=len(segment)-len(points)
        if points:clipped.append(points)
    if outside_trial:tr['exclusions']['outsideTrial']=outside_trial
    tr['segments']=clipped
    tr['duration']=end_time
    tr['fingerFailed']=bool(tr['exclusions'].get('finger')) and tr.get('error')=='UNEXPECTED_TOUCH' and not (tr['task'] in ['A5','A6','A7'] or tr['condition']=='NATURAL')
    ev=tr['events'];present=next((e['t'] for e in ev if e['type']=='TARGET_PRESENT_REQUEST'),None);end=next((e['t'] for e in ev if e['type']=='TRIAL_END'),tr['duration'])
    row=dict(run=tr['run'],sessionID=tr['session'],trialID=tr['id'],task=tr['task'],condition=tr['condition'],scene=tr['scene'],posture=tr['posture'],index=tr['index'],repeat=tr['repeat'],success=tr.get('success',False),error=tr.get('error',''),rawSuccess=tr['rawSuccess'],rawError=tr['rawError'],hand=tr['reportedHand'],handSource=tr['handSource'],analysisOverrideReason=tr.get('analysisOverrideReason',''),duration_s=end,target_to_end_s=end-present if present is not None else None,diameter=tr['trial'].get('diameter'),distance=tr['trial'].get('distance'),direction=tr['trial'].get('direction'),requested=json.dumps(tr['trial'].get('requested',[])),retained_points=sum(map(len,tr['segments'])),segments=len(tr['segments']),excluded=json.dumps(tr['exclusions']),finger_failed=tr['fingerFailed'])
    motion=[];primary={};tiny=0;all_edges=0
    for src in ['HOVER','TOUCH']:
        speeds=[];sw=[];accs=[];aw=[];zs=[];zw=[];path=0;observed=0;seg_count=0;dt_all=[];short=0
        for si,seg in enumerate(tr['segments']):
            if not seg or src not in seg[0]['source']:continue
            seg_count+=1;pv=None
            for a,b in zip(seg,seg[1:]):
                dt=b['t']-a['t'];distance=math.hypot(b['x']-a['x'],b['y']-a['y']);vx=(b['x']-a['x'])/dt;vy=(b['y']-a['y'])/dt;tv=(a['t']+b['t'])/2;path+=distance;observed+=dt;dt_all.append(dt);all_edges+=1
                d=dict(run=tr['run'],trialID=tr['id'],task=tr['task'],condition=tr['condition'],scene=tr['scene'],source=src,segment=si,t=tv,dt=dt,speed=math.hypot(vx,vy),seq0=a['sequence'],seq1=b['sequence'],acceleration=None,accelerationTime=None,accelSeq0=None,accelSeq1=None,accelSeq2=None,primarySpeed=dt>=.001,primaryAcceleration=False)
                if pv:
                    d.update(acceleration=math.hypot(vx-pv['vx'],vy-pv['vy'])/(tv-pv['t']),accelerationTime=(tv+pv['t'])/2,accelSeq0=pv['seq'],accelSeq1=a['sequence'],accelSeq2=b['sequence'],primaryAcceleration=dt>=.001 and pv['dt']>=.001)
                    if d['primaryAcceleration']:accs.append(d['acceleration']);aw.append(tv-pv['t'])
                if dt>=.001:
                    speeds.append(d['speed']);sw.append(dt)
                    if src=='HOVER' and a['z'] is not None:zs.append(a['z']);zw.append(dt)
                else:short+=1;tiny+=1
                pv=dict(t=tv,vx=vx,vy=vy,seq=a['sequence'],dt=dt);motion.append(d)
        row.update({f'{src.lower()}_path_pt':path,f'{src.lower()}_observed_s':observed,f'{src.lower()}_speed_median':weighted(speeds,sw),f'{src.lower()}_speed_p95':weighted(speeds,sw,.95),f'{src.lower()}_accel_median':weighted(accs,aw),f'{src.lower()}_accel_p95':weighted(accs,aw,.95),f'{src.lower()}_dt_median_ms':med(dt_all)*1000 if dt_all else None,f'{src.lower()}_short_edges':short})
        primary[src]=dict(speeds=speeds,weights=sw,accels=accs,accelWeights=aw,observed=observed,path=path,dt=dt_all)
        if src=='HOVER':row['z_median_raw']=weighted(zs,zw)
    row['tiny_edge_count']=tiny;row['edge_count']=all_edges
    tr['motion']=motion;tr['primary']=primary
    dw=[e['metadata'] for e in ev if e['type']=='DWELL_END'];candidates=[e for e in ev if e['type']=='CANDIDATE'];row.update(candidates=len(candidates),candidate_rate_per_min=len(candidates)*60/end if end>0 else None,dwell_count=len(dw),candidate_dwell_median_ms=med([float(x['durationMs']) for x in dw if x.get('candidate')=='true']),dwell_median_ms=med([float(x['durationMs']) for x in dw]),lasso_interruptions=sum(e['type']=='LASSO_CANCEL' for e in ev),touch_down_count=sum(e['type']=='TOUCH_DOWN' for e in ev))
    row['min_pre_touch_hover_coverage_ms']=min((x['observedMs'] for x in tr['coverage']),default=None)
    # Longest uninterrupted contact segment: no connections over a gap.
    contacts=[s for s in tr['segments'] if len(s)>1 and 'TOUCH' in s[0]['source']]
    if contacts:
        longest=max(contacts,key=lambda s:s[-1]['t']-s[0]['t']);displacement=math.hypot(longest[-1]['x']-longest[0]['x'],longest[-1]['y']-longest[0]['y']);length=sum(math.hypot(b['x']-a['x'],b['y']-a['y']) for a,b in zip(longest,longest[1:]))
        row['longest_touch_tortuosity']=length/displacement if displacement>=20 else None;row['longest_touch_span_s']=longest[-1]['t']-longest[0]['t']
    else:row['longest_touch_tortuosity']=None;row['longest_touch_span_s']=None
    tr['row']=row;return row

def dump_csv(path,rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,keys);w.writeheader();w.writerows(rows)

def aggregate(trials):
    result=[]
    for task in TASKS:
        for condition in sorted({t['condition'] for t in trials if t['task']==task}):
            for sid in SID:
                ts=[t for t in trials if t['session']==sid and t['task']==task and t['condition']==condition];valid=[t for t in ts if t.get('success')];rows=[t['row'] for t in valid if not t['fingerFailed']]
                result.append(dict(run=LABELS[sid],task=task,condition=condition,attempts=len(ts),success=len(valid),rawSuccess=sum(t['rawSuccess'] for t in ts),analysisOverrides=sum(bool(t.get('analysisOverrideReason'))for t in ts),rate=len(valid)/len(ts) if ts else None,target_to_success_median_s=med([r['target_to_end_s'] for r in rows]),hover_speed_median=med([r['hover_speed_median'] for r in rows]),touch_speed_median=med([r['touch_speed_median'] for r in rows]),touch_tortuosity_median=med([r['longest_touch_tortuosity'] for r in rows]),errors=dict(collections.Counter(t.get('error','') for t in ts if not t.get('success')))))
    return result

def pairs(trials):
    rows=[]
    for task,condition in [('A1','TOUCH'),('A2','TOUCH'),('B1','HOVER'),('B2','HOVER'),('C1','TAP')]:
        maps=[]
        for sid in SID:
            maps.append({(t['trial']['distance'],t['trial']['diameter'],t['trial']['direction']):t for t in trials if t['session']==sid and t['task']==task and t['condition']==condition and t.get('success') and not t['fingerFailed']})
        for key in maps[0].keys()&maps[1].keys():
            a,b=maps[0][key]['row'],maps[1][key]['row'];rows.append(dict(task=task,condition=condition,distance=key[0],diameter=key[1],direction=key[2],thumb_trial=a['trialID'],index_trial=b['trialID'],thumb_target_time_s=a['target_to_end_s'],index_target_time_s=b['target_to_end_s'],index_minus_thumb_s=b['target_to_end_s']-a['target_to_end_s'],thumb_touch_speed=a['touch_speed_median'],index_touch_speed=b['touch_speed_median'],thumb_touch_tortuosity=a['longest_touch_tortuosity'],index_touch_tortuosity=b['longest_touch_tortuosity']))
    return rows

def plots(trials,summary,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Circle,Rectangle
    from matplotlib import font_manager
    font_manager.fontManager.addfont('/System/Library/Fonts/Supplemental/Arial Unicode.ttf');plt.rcParams.update({'font.family':'Arial Unicode MS','axes.unicode_minus':False,'font.size':10})
    def phone(ax):
        ax.set(xlim=(0,390),ylim=(830,0),aspect='equal');ax.add_patch(Rectangle((0,0),390,830,fill=False,color='#8795a3',lw=.8));ax.grid(alpha=.15);ax.set_xlabel('X（pt）');ax.set_ylabel('Y（pt）')
    def lines(ax,ts,color,hover_only=False,after_present=False):
        hover=[];touch=[]
        for t in ts:
            start=next((e['t'] for e in t['events'] if e['type']=='TARGET_PRESENT_REQUEST'),0) if after_present else 0
            for s in t['segments']:
                p=[(p['x'],p['y']) for p in s if p['t']>=start]
                if len(p)>1:
                    (hover if 'HOVER' in s[0]['source'] else touch).append(p)
        if hover:ax.add_collection(LineCollection(hover,colors=color,linewidths=.6,alpha=.5))
        if touch and not hover_only:ax.add_collection(LineCollection(touch,colors='#505862',linewidths=.65,alpha=.35))
    fig,axes=plt.subplots(2,4,figsize=(12,10))
    for i,sid in enumerate(SID):
        for j,task in enumerate(['A1','A2','A3','A4']):
            ax=axes[i,j];phone(ax);ts=[t for t in trials if t['session']==sid and t['task']==task and not t['fingerFailed']];lines(ax,ts,COLORS[i],after_present=True)
            ax.set_title(f'{LABELS[sid]} · {task} {TITLES[task]}\n{sum(bool(t.get("success")) for t in ts)}/{len(ts)} 成功')
    fig.suptitle('抽象任务：实测手机内轨迹（彩色悬停，灰色接触；断线保留）',fontsize=14);fig.tight_layout();fig.savefig(out/'abstract_paths.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(10,10))
    for i,sid in enumerate(SID):
        for j,task in enumerate(['A5','A6','A7']):
            ax=axes[i,j];phone(ax);ts=[t for t in trials if t['session']==sid and t['task']==task and t.get('success')];lines(ax,ts,COLORS[i]);r=ts[0]['row'];ax.set_title(f'{LABELS[sid]} · {TITLES[task]}\n候选 {r["candidates"]} 次 · 有效悬停 {r["hover_observed_s"]:.1f}s')
    fig.suptitle('自然阅读 120 秒：屏幕坐标轨迹；候选≠真实误触',fontsize=14);fig.tight_layout();fig.savefig(out/'reading_paths.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(2,6,figsize=(17,8))
    for i,sid in enumerate(SID):
        for j,t in enumerate([t for t in trials if t['session']==sid and t['task']=='B4']):
            ax=axes[i,j];phone(ax)
            for o in t['trial']['objects']:
                b=o['bounds'];wanted=o['id'] in t['trial']['requested'];ax.add_patch(Circle((b['x']+b['width']/2,b['y']+b['height']/2),b['width']/2,facecolor='#d0efda' if wanted else '#eee',edgecolor='#288b4f' if wanted else '#999'));ax.text(b['x']+b['width']/2,b['y']+b['height']/2,o['id'],ha='center',va='center',fontsize=8)
            current=[]
            for e in t['events']:
                m=e['metadata']
                if e['type']=='LASSO_START':current=[decoded(m.get('start'))]
                if e['type']=='LASSO_POINT':current.append(decoded(m.get('point')))
                if e['type'] in ['LASSO_CANCEL','LASSO_CLOSE']:
                    if len(current)>1:ax.plot([p['x'] for p in current],[p['y'] for p in current],color=COLORS[i],lw=1,alpha=.9 if e['type']=='LASSO_CLOSE' else .4)
                    edge=decoded(m.get('algorithmicClosingEdge'),[])
                    if edge:ax.plot([p['x'] for p in edge],[p['y'] for p in edge],color='#d13b50',ls='--',lw=1)
                    current=[]
            if len(current)>1:ax.plot([p['x'] for p in current],[p['y'] for p in current],color=COLORS[i],lw=.7,alpha=.4)
            p=t['trial']['start'];ax.add_patch(Circle((p['x'],p['y']),20,fill=False,ec='#288bce'));ax.set_title(f'{LABELS[sid]} {j+1}/6\n'+('成功' if t.get('success') else t.get('error','')),fontsize=9)
    fig.suptitle('B4 空中圈选：绿目标为指定集合；浅线中断；红虚线算法闭合边',fontsize=14);fig.tight_layout();fig.savefig(out/'lasso_paths.png',dpi=180);plt.close(fig)
    short=[a for a in summary if a['task'] not in ['A5','A6','A7']];keys=list(dict.fromkeys((a['task'],a['condition']) for a in short));x=np.arange(len(keys));fig,axes=plt.subplots(2,1,figsize=(13,8),sharex=True)
    for i,label in enumerate(LABELS.values()):
        ss=[next(a for a in short if (a['task'],a['condition'])==k and a['run']==label)for k in keys];axes[0].bar(x+(i-.5)*.36,[a['rate']*100 for a in ss],.36,color=COLORS[i],label=label)
        for xx,a in zip(x+(i-.5)*.36,ss):axes[0].text(xx,a['rate']*100+2,f'{a["success"]}/{a["attempts"]}',ha='center',fontsize=8)
        axes[1].plot(x,[a['target_to_success_median_s'] if a['target_to_success_median_s'] is not None else np.nan for a in ss],'o-',color=COLORS[i],label=label)
    axes[0].set(ylim=(0,115),ylabel='成功率（%）');axes[1].set(ylabel='目标出现→成功 中位时间（秒）');axes[0].legend();axes[1].set_xticks(x,[f'{k[0]}\n{k[1]}' for k in keys]);axes[1].grid(alpha=.2);fig.suptitle('任务／条件分别比较；C3 自然 20 秒不与 A 组 120 秒合并');fig.tight_layout();fig.savefig(out/'task_comparison.png',dpi=170);plt.close(fig)
    # Identical A2 geometry with both successful. Use longest real contact segment only.
    matched=pairs(trials);p=next((p for p in matched if p['task']=='A2' and p['distance']==220 and p['diameter']==50 and p['direction']==-1),None)
    if p:
        fig,axes=plt.subplots(3,1,figsize=(10,9))
        for i,key in enumerate(['thumb_trial','index_trial']):
            t=next(t for t in trials if t['id']==p[key]);s=max([s for s in t['segments'] if len(s)>1 and 'TOUCH' in s[0]['source']],key=lambda s:s[-1]['t']-s[0]['t']);start=s[0]['t'];seqs={p['sequence'] for p in s};ms=[m for m in t['motion'] if m['seq0'] in seqs and m['seq1'] in seqs]
            axes[0].plot([p['x'] for p in s],[p['y'] for p in s],'.-',ms=2,lw=.8,color=COLORS[i],label=t['run']);axes[1].plot([m['t']-start for m in ms if m['primarySpeed']],[m['speed'] for m in ms if m['primarySpeed']],color=COLORS[i],lw=.7,label=t['run']);axes[2].plot([m['accelerationTime']-start for m in ms if m['primaryAcceleration']],[m['acceleration'] for m in ms if m['primaryAcceleration']],color=COLORS[i],lw=.7)
        axes[0].invert_yaxis();axes[0].set(xlabel='X（pt；横轴放大以显示侧偏）',ylabel='Y（pt）');axes[0].legend();axes[1].set(ylabel='XY 速度（pt/s）');axes[2].set(ylabel='XY 加速度幅值（pt/s²）',xlabel='本段接触开始后的时间（秒）');fig.suptitle('同几何 A2 示例：距离 220 pt，直径 50 pt，向上拖动\n最长连续接触段；原始导数无平滑，短于 1 ms 支持不进入主图');fig.tight_layout();fig.savefig(out/'matched_drag_motion.png',dpi=170);plt.close(fig)

def compact_replay(trials,source,quality,out):
    root=Path(__file__).resolve().parents[1];keep=[];skipped=0
    for t in trials:
        nt={k:v for k,v in t.items() if k not in ['primary','row','fingerFailed']};last=-math.inf;events=[]
        for e in t['events']:
            m=e['metadata'];is_state=e['type'] in ['SCENE_STATE','SCROLL_STATE'] and m.get('action','SCROLL') in ['SCROLL','INERTIA','VIDEO_PROGRESS']
            if is_state and e['t']-last<.05:skipped+=1;continue
            if is_state:last=e['t']
            events.append(dict(e,metadata={k:v for k,v in m.items() if k not in ['protocolVersion','taskID','taskGroup','scene','posture','condition','contentVersion','sessionPlannedIndex','sampleSequence','trial','points']}))
        nt['events']=sorted(events,key=lambda e:e['t']);nt['motion']=[{k:v for k,v in m.items() if k not in ['run','trialID','task','condition','scene','source']}for m in t['motion']];keep.append(nt)
    data=dict(source=source.name,sha256=quality['sha256'],legacyRows=quality['sessions'][next(k for k,v in quality['sessions'].items() if v['protocol']=='legacy')]['rows'],trials=keep)
    text=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    (out/'replay-data.json').write_text(text)
    bootstrap=json.dumps(dict(source=source.name,trials=[],dataURL='./replay-data.json'),ensure_ascii=False)
    html=(root/'qa/v2_replay.html').read_text().replace('__DATA__',bootstrap).replace('./replay.html','../replay.html').replace('14 类任务 · 蓝线','拇指／食指两轮正式采集 · 蓝线').replace('<div id="message"></div>','<p>第一轮：右手拇指；第二轮：右手食指。B1 选 B 按用户说明覆核，原指令及判定保留。<a href="./report.html">比较报告</a> · <a href="./trial_metrics.csv">逐试次指标</a>。坐标不降采样；场景预览最多 20 Hz（原始状态保留于 CSV）。</p><div id="message">正在加载真实两轮轨迹…</div>')
    (out/'replay-v2.html').write_text(html);js=(root/'qa/v2_replay.js').read_text().replace("option(el,v,v)","option(el,({THUMB:'第一轮 · 右手拇指',CRADLE_INDEX:'第二轮 · 右手食指'})[v]||v,v)")
    # The chart uses primary derivative supports while all derivative rows remain available.
    js=js.replace("if(p[key]===null)continue;", "if(p[key]===null||(key==='speed'&&!p.primarySpeed)||(key==='acceleration'&&!p.primaryAcceleration)){seg=null;continue;}")
    js=js.replace('const metrics=current.motion;','const metrics=current.motion;').replace('metrics.map(m=>m.speed)','metrics.filter(m=>m.primarySpeed).map(m=>m.speed)').replace('metrics.map(m=>m.acceleration||0)','metrics.filter(m=>m.primaryAcceleration).map(m=>m.acceleration||0)')
    js=js.replace('refresh();requestAnimationFrame(animate);',"if(data.dataURL){fetch(data.dataURL).then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(d=>{data=d;refresh()}).catch(e=>{$('message').textContent='加载失败：'+e.message+'。请通过本地服务器打开本页。'})}else refresh();requestAnimationFrame(animate);")
    js=js.replace("['姿势',current.posture]","['原始判定',current.rawSuccess?'成功':current.rawError||'未结束'],['覆核说明',current.analysisOverrideReason?'用户说明所有菜单都理解为选 B，动作完成':'无覆盖'],['操作手',current.reportedHand||'未记录'],['姿势',current.posture]")
    (out/'v2_replay.js').write_text(js);shutil.copytree(root/'src/App/StudyMedia',out/'Resources',dirs_exist_ok=True)
    vendor=root/'qa/vendor'
    if not vendor.exists():vendor=root/'analysis/trajectory_2026-09-15/vendor'
    shutil.copytree(vendor,out/'vendor',dirs_exist_ok=True)
    quality['replay']=dict(trials=len(trials),points=sum(t['row']['retained_points'] for t in trials),scenePreviewMaxHz=20,omittedScenePreviewStates=skipped,htmlBytes=len(html.encode()),dataBytes=len(text.encode()))

def report(trials,summary,paired,quality,out,intent_lines=None):
    lines=['# 拇指／食指两轮行动轨迹分析','',f'来源：`{Path(quality["source"]).name}`。两轮均为 P01 的真实 Pencil 输入。用户确认两轮均右手，第一轮为拇指、第二轮为托握＋食指。手别来源为用户覆核，原日志没有手别字段。','',f'原文件 {quality["bytes"]:,} 字节，{sum(quality["rows"].values()):,} 行、{quality["fields"]} 列。SHA256 `{quality["sha256"]}`。旧协议及 9 秒试操作排除；原文件未改写。','', '## 采集概况','']
    lines[6:6]=['## 这轮数据中的主要规律','',
        '1. **食指的空中圈选更容易完成，但仍有练习效应。** 拇指 2/6、食指 5/6；中断 8→1 次。拇指前四次圈选失败、后两次成功，说明熟悉任务的过程已经发生，不能把全部改善归为姿势。',
        '2. **抽象滚动中，拇指操作节奏更快。** 垂直／水平滚动两轮都 6/6；目标出现至完成中位数分别为拇指 0.91/0.83 秒、食指 1.19/1.11 秒。食指成功拖动的连续路径略直，但四次拖动失败是三次起点尚未准备就触屏、一次源方块外起拖，不能解释为拖动途中失控。',
        '3. **短视频最容易达到静默 500 ms 规则。** 两分钟内拇指／食指候选为 31/37 次，长文为 14/12 次、图文为 13/11 次。视频候选几乎全部来自大面积视频对象；食指同时切换视频更频繁（41 vs 21 次），停留段更短，可能产生更多新的候选机会。这不是已发生 31/37 次误触。',
        '4. **阅读轨迹有固定操作带。** 两姿势都主要在手机右侧活动；长文中食指轨迹更集中于中下部，拇指纵向覆盖更广。长文滚动最大偏移分别约 4,800/2,717 pt，内容浏览进度不同，会影响停留和轨迹，需结合场景状态回放。',
        '5. **B1 菜单动作两轮均完成 6/6。** 用户说明将所有指定项理解为 B；六条原 WRONG_MENU_ITEM 记录按动作完成覆核，原指令与失败判定保留。C1 的 HOVER 两轮均 0/6，仍全部因 Pencil 触屏；此次菜单覆核不改动其他错误。','']
    rr=[]
    for sid in SID:
        s=quality['sessions'][sid];ts=[t for t in trials if t['session']==sid];short=[t for t in ts if t['task'] not in ['A5','A6','A7']];reading=[t for t in ts if t['task'] in ['A5','A6','A7']];success=sum(t.get('success',False) for t in short)
        rr.append([LABELS[sid],s['first'][11:19]+'–'+s['last'][11:19],fmt((s['lastTime']-s['firstTime'])/60),f'{success}/{len(short)}（{success/len(short)*100:.1f}%）',f'{sum(t.get("success",False) for t in reading)}/{len(reading)}',f'{s["samples"]:,}'])
    lines += [table(['姿势','本地时间','会话分钟','短任务动作完成（覆核后）','阅读成功／尝试','接收样本'],rr),'','第二轮 A7 有一次 `REDO_REQUESTED` 的未完成尝试，另一次完成；该部分单独保留，完整阅读比较仅取完成的 120 秒段。两轮均完成所有 14 类任务，没有模拟来源或手指输入。','', '## 任务结果','',table(['任务／条件','拇指成功','食指成功','拇指目标→成功秒','食指目标→成功秒'],[[f'{task} {TITLES[task]} / {cond}',*[f'{a["success"]}/{a["attempts"]}' for a in summary if a['task']==task and a['condition']==cond],*[fmt(a['target_to_success_median_s']) for a in summary if a['task']==task and a['condition']==cond]]for task,cond in dict.fromkeys((a['task'],a['condition'])for a in summary)]),'','时间只比较成功试次，不把快速失败当作更快完成；目标出现前的起点准备不包含在该时间中。C3 自然条件约 20 秒，A5–A7 约 120 秒。','', '![任务结果](task_comparison.png)','', '## 相同几何配对','']
    pairrows=[]
    for task in ['A1','A2','B1','B2','C1']:
        ps=[p for p in paired if p['task']==task]
        pairrows.append([task,len(ps),fmt(med([p['thumb_target_time_s'] for p in ps])),fmt(med([p['index_target_time_s'] for p in ps])),fmt(med([p['index_minus_thumb_s'] for p in ps]))])
    lines += [table(['任务','两轮都成功配对数','拇指秒','食指秒','食指−拇指配对差秒'],pairrows),'','按距离、直径、方向和条件配对；只用双方成功记录。这是描述性对比，样本来自同一人，不能把先后顺序／熟悉程度的影响排除。配对原始 ID 见 [paired_metrics.csv](paired_metrics.csv)。','', '## 行动轨迹与运动','', '![抽象操作](abstract_paths.png)','', '图中彩色为悬停、灰色为接触，全部实测点保留，手机外点、结束回调和缺口处断线。线多／路径长可能包含重定位与等待，不直接代表操作效率。','']
    motionrows=[]
    for task in ['A2','A3','A4','B2','B3','B4']:
        for source in (['TOUCH'] if task in ['A2','A3','A4'] else ['HOVER']):
            values=[]
            for sid in SID:
                ts=[t for t in trials if t['session']==sid and t['task']==task and t.get('success') and not t['fingerFailed']];values.extend([fmt(med([t['row'][source.lower()+'_speed_median']for t in ts]),1),fmt(med([t['row'][source.lower()+'_accel_p95']for t in ts]),0)])
            motionrows.append([task+' / '+source,*values])
    lines += [table(['任务／输入','拇指速度中位 pt/s','拇指加速度 P95 pt/s²','食指速度中位 pt/s','食指加速度 P95 pt/s²'],motionrows),'','每试次先做时间加权分布，再取成功试次中位数；极短支持边不进入主要导数汇总。加速度更易受位置量化和采样时间影响，P95 仅用于观察急停／转向程度。上述任务几何及操作节奏不同，不宜合并成一个“姿势加速度”。','',
        '成功拖动最长连续接触段的路径／端点直线距离，中位数为拇指 1.10、食指 1.05（1 表示直线）。这反映食指成功段略直；目前只有双方成功的 14 个几何可配对，不能忽略失败或用单个段代表整次过程。垂直滚动两姿势约 1.04，水平滚动为 1.07/1.11，食指的速度更慢也没有普遍消除弯曲。','', '![同几何拖动](matched_drag_motion.png)','', '该图为同几何成功拖动示例，最长连续接触段；查看接触路径的横向摆动，以及速度的起步、峰值、减速。原始导数没有平滑，不跨断线连接。它是示例，不代表全部试次。','', '## 自然阅读：候选与停留','']
    readingrows=[];readingdata=[]
    for task in ['A5','A6','A7']:
        for sid in SID:
            t=next(t for t in trials if t['session']==sid and t['task']==task and t.get('success'));r=t['row'];actions=collections.Counter(e['metadata'].get('action') for e in t['events'] if e['type']=='SCENE_STATE');dw=[e['metadata']for e in t['events']if e['type']=='DWELL_END' and e['metadata'].get('candidate')=='true'];duration=r['duration_s'];readingrows.append([TITLES[task],LABELS[sid],r['candidates'],fmt(r['candidate_rate_per_min']),fmt(r['hover_observed_s'],1),fmt(r['candidate_dwell_median_ms']/1000 if r['candidate_dwell_median_ms'] is not None else None),f'打开 {actions["NOTE_OPEN"]} / 翻图 {actions["IMAGE_CHANGE"]} / 视频切换 {actions["VIDEO_CHANGE"]}'])
            states=[decoded(e['metadata'].get('sceneState'),{})for e in t['events'] if e['type']=='SCENE_STATE'];offsets=[s.get('offset',0)for s in states];readingdata.append(dict(run=LABELS[sid],task=task,scene=t['scene'],trialID=t['id'],duration_s=duration,candidates=r['candidates'],candidate_rate_per_min=r['candidate_rate_per_min'],hover_observed_s=r['hover_observed_s'],candidate_dwell_median_s=r['candidate_dwell_median_ms']/1000 if r['candidate_dwell_median_ms']is not None else None,offset_min=min(offsets,default=0),offset_max=max(offsets,default=0),actions=dict(actions),candidate_objects=dict(collections.Counter(e['metadata'].get('objectID')for e in t['events']if e['type']=='CANDIDATE'))))
    dump_csv(out/'reading_metrics.csv',[{**r,'actions':json.dumps(r['actions']),'candidate_objects':json.dumps(r['candidate_objects'])}for r in readingdata])
    lines += [table(['120 秒场景','姿势','候选次数','候选／分钟','有效连续悬停秒','达标停留中位秒','页面操作'],readingrows),'','候选表示同一内容对象内达到了 500 ms 规则，长停留只计一次，不等于实际误触。有效悬停秒是合法连续实测边时长之和，非完整 120 秒的传感覆盖。屏幕轨迹集中也可能是握持习惯或内容位置，滚动后的同一屏幕位置并非同一内容对象。','', '![阅读轨迹](reading_paths.png)','', '## B4 空中圈选','']
    lasso=[]
    for sid in SID:
        ts=[t for t in trials if t['session']==sid and t['task']=='B4'];closes=[e['metadata']for t in ts for e in t['events']if e['type']=='LASSO_CLOSE'];cancel=collections.Counter(e['metadata'].get('reason')for t in ts for e in t['events']if e['type']=='LASSO_CANCEL');lasso.append([LABELS[sid],f'{sum(t.get("success",False)for t in ts)}/6',len(closes),sum(cancel.values()),fmt(med([float(m['duration'])for m in closes])),fmt(med([float(m['pathLength'])for m in closes]),1),fmt(med([float(m['closureDistance'])for m in closes]),1),json.dumps(cancel,ensure_ascii=False)])
    lines += [table(['姿势','成功','有效闭合','中断','闭合耗时秒','实测路径 pt','闭合误差 pt','中断原因'],lasso),'','圈选耗时从开始画线到闭合，排除起点准备；路径不含算法闭合边。没有闭合的失败无法比较完整圈选面积或耗时，已保留中断轨迹。','', '![圈选](lasso_paths.png)','', '## 数据质量与解释边界','']
    qr=[]
    for sid in SID:
        ts=[t for t in trials if t['session']==sid];ex=collections.Counter();sources={k:[]for k in ['HOVER','TOUCH']}
        for t in ts:
            ex.update(t['exclusions'])
            for src in sources:sources[src]+=t['primary'][src]['dt']
        qr.append([LABELS[sid],json.dumps(ex),sum(t['row']['tiny_edge_count']for t in ts),fmt(med(sources['HOVER'])*1000 if sources['HOVER'] else None,2),fmt(med(sources['TOUCH'])*1000 if sources['TOUCH'] else None,2)])
    lines += [table(['姿势','排除坐标数量','<1 ms 连续边','悬停间隔中位 ms','接触间隔中位 ms'],qr),'','回调间隔并非硬件采样率证明。指标限制在 TRIAL_START 至 TRIAL_END，outsideTrial 是间隔中仍标为前一试次的采样，单独计数且原 CSV 保留。全部合法边在 [motion_metrics.csv](motion_metrics.csv) 导出，主要汇总门槛及支持序号可追溯。跨范围或缺口不计算导数，原始 Z 不换算毫米。','', '两轮 C1 的 HOVER 条件均 0/6 成功，错误是 Pencil `UNEXPECTED_TOUCH`；这组当前反映参与者在纯悬停任务中触屏，无法拿失败时间评价悬停性能。其余错误按任务保存于 [task_summary.csv](task_summary.csv)。B1 两轮共 12 次均选 B，六次要求 A 的记录原判失败。按用户看题说明，分析按动作完成覆核，原始失败标记见 rawSuccess/rawError，不改写 CSV。','', '仅有一名参与者每姿势一轮，且拇指先、食指后；该数据支持行为描述和原型诊断，不能给出总体姿势优劣或显著性结论。两轮均为用户确认的右手，本轮比较拇指／食指与顺序影响。','', '## 交付与复现','', '[打开 3D 回放](replay-v2.html) · [逐试次指标](trial_metrics.csv) · [自然阅读指标](reading_metrics.csv) · [质量清单](quality.json)','', '回放中可选“第一轮·拇指／第二轮·食指”、任务和条件。原始坐标不降采样；场景预览最多 20 Hz，CSV 中全部状态保留。读取完整 CSV 后生成本报告，输入哈希复核一致。','', '```sh','PYTHONPATH=.tmp/plot-libs python3 qa/analyze_two_runs.py "data/HoverIntent_2026-09-15 2.csv" --output analysis/trajectory_2026-09-15/hands_run2','```']
    if intent_lines: lines[6:6]=intent_lines
    lines += ['', '## 用户覆核追溯', '', '两轮均右手。B1 原协议各 3/6，动作覆核后各 6/6；短任务原成功分别 106/132、103/132，覆核后 109/132、106/132。覆核只应用于菜单已出现、实际选 B、原错误仅 WRONG_MENU_ITEM 的六条记录。原始 taskInstruction、rawSuccess/rawError 和 CSV 均保留，详见 [analysis-annotations.json](analysis-annotations.json)。更正前的小型报告／指标保存在 revisions/pre-clarification/。']
    (out/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    # A concise, linked browser report: generated figures plus exact tabular summaries.
    import html,re
    def inline(s):
        s=html.escape(s)
        s=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',s)
        s=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',s)
        return re.sub(r'`([^`]+)`',r'<code>\1</code>',s)
    pieces=[];in_table=False
    for line in '\n'.join(lines).splitlines():
        if line.startswith('|'):
            if line.startswith('| ---'):continue
            if not in_table:pieces.append('<table>');in_table=True
            pieces.append('<tr>'+''.join('<td>'+inline(c.strip())+'</td>' for c in line.strip('|').split('|'))+'</tr>');continue
        if in_table:pieces.append('</table>');in_table=False
        if line.startswith('!['):url=line.split('](')[1][:-1];pieces.append(f'<img src="{url}" loading="lazy">')
        elif line.startswith('#'):level=len(line)-len(line.lstrip('#'));pieces.append(f'<h{level}>{html.escape(line[level:].strip())}</h{level}>')
        elif line and line!='```sh' and line!='```':pieces.append('<p>'+inline(line)+'</p>')
    (out/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>拇指／食指轨迹比较</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto;padding:20px;color:#283642;line-height:1.7}table{border-collapse:collapse;width:100%;font-size:13px}td{border:1px solid #ddd;padding:8px}tr:first-child{background:#edf3f8;font-weight:bold}img{max-width:100%}p{overflow-wrap:anywhere}a{color:#1673ad}</style><a href="behavior-overview.html">整体 A/B/C 行为特征</a> · <a href="replay-v2.html">打开 3D 回放</a> · <a href="motion-study.html">加减速与 Hover 多选</a> · <a href="trial_metrics.csv">逐试次指标</a> · <a href="report.md">Markdown 报告</a>'+''.join(pieces))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('source',type=Path);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=a.output;out.mkdir(parents=True,exist_ok=True)
    archive=out/'revisions/pre-clarification';archive.mkdir(parents=True,exist_ok=True)
    for name in ['report.md','report.html','trial_metrics.csv','task_summary.csv','paired_metrics.csv','quality.json','validation.json']:
        if (out/name).exists() and not (archive/name).exists():shutil.copy2(out/name,archive/name)
    print('Inventory',flush=True);quality=inventory(a.source);assert not quality['invalidCSVLines'];assert all(sid in quality['sessions'] for sid in SID)
    print('Reconstruct real continuous samples',flush=True);data=reconstruct(a.source);trials=[t for t in data['trials']if t['session'] in SID]
    for t in trials:metrics(t)
    print('Metrics',len(trials),flush=True);summary=aggregate(trials);paired=pairs(trials);dump_csv(out/'trial_metrics.csv',[t['row']for t in trials]);dump_csv(out/'task_summary.csv',summary);dump_csv(out/'paired_metrics.csv',paired);dump_csv(out/'motion_metrics.csv',[m for t in trials for m in t['motion']])
    quality['comparison']=dict(selectedSessions=SID,labels=LABELS,mappingSource='user-confirmed both RIGHT; first thumb, second index; B1 all B intended',trials=len(trials),allTaskTypes=sorted({t['task']for t in trials}),rawCSVUnchanged=hashlib.sha256(a.source.read_bytes()).hexdigest()==quality['sha256'],tinyEdges=sum(t['row']['tiny_edge_count']for t in trials),motionRows=sum(len(t['motion'])for t in trials))
    print('Figures and report',flush=True);plots(trials,summary,out);intent_lines=explore(trials,out)
    annotations=dict(version='USER_REVIEW_2026-09-15',rawSHA256=quality['sha256'],handMapping={sid:dict(hand='RIGHT',posture=LABELS[sid],source='USER_CONFIRMATION')for sid in SID},clarification='用户说明两轮均右手，B1 全部理解为选择 B；只覆核动作完成，保留原判定及指令。',overrides=[dict(trialID=t['id'],sessionID=t['session'],rawSuccess=t['rawSuccess'],rawError=t['rawError'],analysisSuccess=t['success'],reason=t['analysisOverrideReason'],originalInstruction=t['instruction'])for t in trials if t.get('analysisOverrideReason')])
    (out/'analysis-annotations.json').write_text(json.dumps(annotations,ensure_ascii=False,indent=2))
    report(trials,summary,paired,quality,out,intent_lines);compact_replay(trials,a.source,quality,out);(out/'quality.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2));print(json.dumps(quality['comparison'],ensure_ascii=False),flush=True)

if __name__=='__main__':main()
