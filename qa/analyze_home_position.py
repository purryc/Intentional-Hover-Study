"""Causal prefix estimates of natural hover hotspots; offline filter risk check."""
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
from analyze_two_runs import dump_csv,fmt,table
from analyze_behavior_overview import presentation,report_html,predict
from explore_hover_intent import episodes,window_features,assess

CHECKPOINTS=[2,5,10,15,20,30,45,60]
SCENES=['news','notes','video']
SCENE_NAMES=dict(news='新闻长文',notes='图文信息流',video='短视频流')
RUNS=['拇指','食指']
RADII=[30,50,80]


def low_motion(row):
    return row['rms_pt']<=15 and row['speed_median_pt_s']<=100


def measured_center(points):
    dt=np.diff([p['t']for p in points]);xy=np.array([[p['x'],p['y']]for p in points])
    center=np.average(xy[:-1],axis=0,weights=dt)
    return dict(cx=float(center[0]),cy=float(center[1]))


def natural_windows(tr):
    start=presentation(tr)
    if start is None:return []
    rows=[]
    for si,segment in enumerate(tr['segments']):
        ps=[p for p in segment if p['t']>=start]
        if len(ps)<12 or 'HOVER'not in ps[0]['source']:continue
        begin=ps[0]['t'];n=0
        while begin+n*.5+.45<=ps[-1]['t']+1e-9 and begin+(n+1)*.5<=tr['duration']+1e-9:
            a=begin+n*.5;b=a+.5;n+=1
            f=window_features(dict(segments=[ps]),a,b)
            if f is None:continue
            p=[p for p in ps if a-1e-8<=p['t']<=b+1e-8]
            r=dict(trialID=tr['id'],run=tr['run'],scene=tr['scene'],segment=si,start=a,end=b,
                   elapsedEnd=b-start,half='TRAIN'if b-start<=60 else'CHECK'if a-start>=60 else'STRADDLE',
                   **{k:v for k,v in f.items()if k!='segment'},**measured_center(p))
            r['lowMotion']=low_motion(r);rows.append(r)
    return rows


def hotspot(rows,radius=50,scene_balanced=False):
    """Only rows supplied by the caller are used; no future or condition labels."""
    rows=[r for r in rows if low_motion(r)]
    if not rows:return None
    xy=np.array([[r['cx'],r['cy']]for r in rows]);w=np.array([r['observed_ms']/1000 for r in rows])
    if scene_balanced:
        for scene in set(r['scene']for r in rows):
            mask=np.array([r['scene']==scene for r in rows]);w[mask]/=w[mask].sum()
    inside=np.linalg.norm(xy[:,None,:]-xy[None,:,:],axis=2)<=radius
    anchor=int(np.argmax(inside@w));mask=inside[anchor]
    center=np.average(xy[mask],axis=0,weights=w[mask])
    # Recount support in the actual final circle rather than in the initial anchor circle.
    mask=np.linalg.norm(xy-center,axis=1)<=radius
    return dict(cx=float(center[0]),cy=float(center[1]),radius=radius,eligibleWindows=len(rows),
                clusterWindows=int(mask.sum()),clusterWeightShare=float(w[mask].sum()/w.sum()),
                clusterObserved_s=float(sum(r['observed_ms']/1000 for r,m in zip(rows,mask)if m)),
                available=bool(mask.sum()>=6),sceneBalanced=scene_balanced,
                trainIDs=sorted(set(r['trialID']for r in rows)),
                rawZMedian=float(np.median([r['z_median_raw']for r,m in zip(rows,mask)if m and r['z_median_raw']is not None]))if any(r['z_median_raw']is not None for r,m in zip(rows,mask)if m)else None)


def distance(a,b):
    return math.hypot(a['cx']-b['cx'],a['cy']-b['cy'])if a is not None and b is not None else None


def learn_model(train,check,radius=50,scene_balanced=False):
    model=hotspot(train,radius,scene_balanced);later=hotspot(check,radius,scene_balanced)
    delta=distance(model,later)
    replicated=bool(model and later and model['available']and later['available']and delta<=50)
    return dict(train=model,check=later,centerShift_pt=delta,replicated=replicated,
                status='REPLICATED_HOTSPOT'if replicated else'TRAIN_ONLY_UNCONFIRMED'if model and model['available']else'INSUFFICIENT_HOVER')


def acquisition(rows,model):
    estimates=[];previous=None;first=None;tentative=None
    for t in CHECKPOINTS:
        visible=[r for r in rows if r['elapsedEnd']<=t+1e-9]
        h=hotspot(visible)
        estimate=dict(elapsed_s=t,totalCompleteWindows=len(visible),model=h,shiftFromPrevious_pt=distance(h,previous),distanceTo60s_pt=distance(h,model['train']))
        if h and h['available']:
            if first is None:first=t
            if previous and previous['available']and h['eligibleWindows']>previous['eligibleWindows']and distance(h,previous)<=20 and tentative is None:tentative=t
        previous=h;estimates.append(estimate)
    stable=None
    if model['replicated']:
        for i,e in enumerate(estimates):
            if e['model']and e['model']['available']and all(q['model']and q['model']['available']and q['distanceTo60s_pt']<=20 for q in estimates[i:]):
                stable=e['elapsed_s'];break
    return dict(firstCandidate_s=first,onlineTentative_s=tentative,retrospectiveStable_s=stable,checkpoints=estimates)


def fraction_inside(points,model):
    if model is None or len(points)<12:return None
    dt=np.diff([p['t']for p in points])
    if np.any(dt<=0)or np.any(dt>.100000001):raise ValueError('noncontinuous window')
    xy=np.array([[p['x'],p['y']]for p in points[:-1]])
    inside=np.linalg.norm(xy-np.array([model['cx'],model['cy']]),axis=1)<=model['radius']
    return float(np.sum(dt[inside])/dt.sum())


def suppress(row,fraction,model_usable):
    # No task, intention label or object ID is consulted by the gate.
    return bool(model_usable and fraction is not None and fraction>=.8 and low_motion(row))


def build(data,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import Circle
    font_manager.fontManager.addfont('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
    plt.rcParams.update({'font.family':'Arial Unicode MS','axes.unicode_minus':False,'font.size':10})
    baselines=[t for t in data['trials']if t['task']in ['A5','A6','A7']and t['success']]
    assert len(baselines)==6
    windows=[r for tr in baselines for r in natural_windows(tr)]
    models={};summary=[]
    for run in RUNS:
        for scene in SCENES:
            rows=[r for r in windows if r['run']==run and r['scene']==scene]
            by_radius={radius:learn_model([r for r in rows if r['half']=='TRAIN'],[r for r in rows if r['half']=='CHECK'],radius)for radius in RADII}
            main=by_radius[50];acq=acquisition(rows,main)
            models[run,scene]=by_radius
            summary.append(dict(run=run,scene=scene,trialID=next(t['id']for t in baselines if t['run']==run and t['scene']==scene),
                                totalCompleteWindows=len(rows),lowMotionWindows=sum(r['lowMotion']for r in rows),
                                rawHoverObserved_s=sum(s[-1]['t']-s[0]['t']for t in baselines if t['run']==run and t['scene']==scene for s in t['segments']if s and'HOVER'in s[0]['source']),
                                **main,acquisition=acq,sensitivity={str(r):v for r,v in by_radius.items()}))
        rows=[r for r in windows if r['run']==run]
        models[run,'TRANSFER']={radius:learn_model([r for r in rows if r['half']=='TRAIN'],[r for r in rows if r['half']=='CHECK'],radius,True)for radius in RADII}
    eps,exclusions=episodes(data['trials']);ab=json.loads((out/'behavior-overview.json').read_text())['model']
    gates=[];trial_by_id={t['id']:t for t in data['trials']}
    for r in eps:
        if r['task']not in ['B1','B2','B3','C3']:continue
        scene=r['scene']if r['task']=='C3'else'TRANSFER';tr=trial_by_id[r['trialID']]
        p=[p for p in tr['segments'][r['segment']]if r['window_start']-1e-8<=p['t']<=r['window_end']+1e-8]
        item=dict(**r,**measured_center(p),homeModelScene=scene,ab_score=float(predict(ab,[r])[0]),evaluation='C3_TRANSFER'if r['task']=='C3'else'B_READING_TRANSFER')
        if r['task']=='C3':
            baseline_trial=next(t for t in baselines if t['run']==r['run']and t['scene']==r['scene'])
            item['modelAge_s']=tr['start']+r['window_start']-baseline_trial['start']-60
        for radius in RADII:
            model=models[r['run'],scene][radius];fraction=fraction_inside(p,model['train'])
            item.update({f'fraction_R{radius}':fraction,f'replicated_R{radius}':model['replicated'],f'suppressed_R{radius}':suppress(r,fraction,model['replicated'])})
        item['abWithHome_score']=0.0 if item['suppressed_R50']else item['ab_score'];gates.append(item)
    c3=[r for r in gates if r['task']=='C3']
    metrics={}
    for radius in RADII:
        scores=[0 if r[f'suppressed_R{radius}']else 1 for r in c3]
        metrics[str(radius)]=dict(homeOnly=assess(c3,scores),withAB=assess(c3,[0 if r[f'suppressed_R{radius}']else r['ab_score']for r in c3]),
                                 naturalSuppressed=sum(r['label']==0 and r[f'suppressed_R{radius}']for r in c3),
                                 activeSuppressed=sum(r['label']==1 and r[f'suppressed_R{radius}']for r in c3),
                                 usableWindows=sum(r[f'replicated_R{radius}']for r in c3))
    baseline=assess(c3,[r['ab_score']for r in c3]);per_scene={};transfer=[]
    for scene in SCENES:
        rows=[r for r in c3 if r['scene']==scene]
        per_scene[scene]=dict(base=assess(rows,[r['ab_score']for r in rows]),homeOnly=assess(rows,[0 if r['suppressed_R50']else 1 for r in rows]),withAB=assess(rows,[r['abWithHome_score']for r in rows]))
    for task in ['B1','B2','B3']:
        for run in RUNS:
            rows=[r for r in gates if r['task']==task and r['run']==run]
            transfer.append(dict(task=task,run=run,windows=len(rows),suppressed=sum(r['suppressed_R50']for r in rows),usable=sum(r['replicated_R50']for r in rows)))
    same_segment=[]
    for run in RUNS:
        for scene in SCENES:
            rows=[r for r in eps if r['task']in ['A5','A6','A7']and r['run']==run and r['scene']==scene and r['window_start']>=60 and r['window_end']<=120]
            model=models[run,scene][50]['train'];removed=0
            for r in rows:
                tr=trial_by_id[r['trialID']];p=[p for p in tr['segments'][r['segment']]if r['window_start']-1e-8<=p['t']<=r['window_end']+1e-8]
                fraction=fraction_inside(p,model);usable=bool(model and model['available']);flag=suppress(r,fraction,usable);removed+=flag
                gates.append(dict(**r,**measured_center(p),homeModelScene=scene,evaluation='A_SAME_READING_FUTURE',fraction_R50=fraction,trainingModelUsable=usable,suppressed_R50=flag))
            later_c=[r for r in c3 if r['run']==run and r['scene']==scene]
            same_segment.append(dict(run=run,scene=scene,naturalWindows=len(rows),suppressed=removed,trainingModelUsable=bool(model and model['available']),
                                     c3ModelAgeMedian_s=float(np.median([r['modelAge_s']for r in later_c]))if later_c else None))
    cross_scene=[]
    for run in RUNS:
        for i,a in enumerate(SCENES):
            for b in SCENES[i+1:]:cross_scene.append(dict(run=run,scene1=a,scene2=b,centerDistance_pt=distance(models[run,a][50]['train'],models[run,b][50]['train'])))
    # All models remain frozen at the first minute; the second minute is only a check.
    result=dict(source=data['source'],sha256=data['sha256'],hand='RIGHT',method=dict(window_s=.5,minCoverage_ms=450,minPoints=12,rmsMaximum_pt=15,speedMaximum_pt_s=100,radiusPrimary_pt=50,radiusSensitivity_pt=RADII,insideFractionMinimum=.8,train_s=60,check_s=60,minClusterWindows=6,maxCheckCenterShift_pt=50),
                sceneModels=summary,transferModels={run:models[run,'TRANSFER'][50]for run in RUNS},crossSceneDistances=cross_scene,
                aSameReadingFuture=same_segment,c3Base=baseline,c3Filter=metrics,c3Scenes=per_scene,bTransferRisk=transfer,episodeExclusions=exclusions,
                status='EXPLORATORY_OBSERVED_PHONE_XY_HOTSPOTS_NOT_CONFIRMED_REST',cValidation='RETROSPECTIVE_SAME_PARTICIPANT')
    dump_csv(out/'home_candidates.csv',windows);dump_csv(out/'home_filter_windows.csv',gates)
    fig,axes=plt.subplots(2,3,figsize=(12,9))
    for i,run in enumerate(RUNS):
        for j,scene in enumerate(SCENES):
            ax=axes[i,j];ax.set(xlim=(0,390),ylim=(830,0),aspect='equal',xticks=[0,195,390]);ax.grid(alpha=.12)
            rows=[r for r in windows if r['run']==run and r['scene']==scene and r['lowMotion']]
            for half,color,marker in [('TRAIN','#378db4','o'),('CHECK','#d99347','^')]:
                rs=[r for r in rows if r['half']==half];ax.scatter([r['cx']for r in rs],[r['cy']for r in rs],s=16,alpha=.55,color=color,marker=marker,label='前60秒'if half=='TRAIN'else'后60秒')
            cs=[r for r in c3 if r['run']==run and r['scene']==scene and r['label']==0]
            ax.scatter([r['cx']for r in cs],[r['cy']for r in cs],s=15,alpha=.55,color='#77a67b',marker='s',label='后续C3自然候选')
            m=models[run,scene][50]
            for role,color in [('train','#2875a3'),('check','#b87930')]:
                h=m[role]
                if h:
                    ax.add_patch(Circle((h['cx'],h['cy']),50,fill=False,edgecolor=color,lw=1.5,ls='-'if role=='train'else'--'));ax.scatter([h['cx']],[h['cy']],s=50,color=color,marker='+')
            ax.scatter([195],[415],marker='x',s=26,color='#aaa',label='实验起点；不参与估计')
            ax.set_title(run+' · '+SCENE_NAMES[scene]+'\n'+('热点复现'if m['replicated']else'候选未确认'if m['train']and m['train']['available']else'有效悬停不足'))
            if i==0 and j==0:ax.legend(fontsize=7,loc='upper left')
    fig.suptitle('自然低运动热点及后续C3自然候选：统计窗口中心，不是拼接轨迹\n圆半径固定50pt；蓝圆前60秒估计，橙圆后60秒检验，绿方块后续C3；灰色固定起点不是home',fontsize=12)
    fig.tight_layout();fig.savefig(out/'home_position_map.png',dpi=165);plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(13,7))
    for ax,s in zip(axes.flat,summary):
        e=s['acquisition']['checkpoints'];x=[v['elapsed_s']for v in e];y=[v['distanceTo60s_pt']if v['distanceTo60s_pt']is not None else np.nan for v in e]
        ax.plot(x,y,'o-',color='#3588aa',label='相对60秒中心偏差');ax.axhline(20,color='#999',ls='--',lw=.8)
        ax2=ax.twinx();ax2.plot(x,[v['model']['clusterWindows']if v['model']else 0 for v in e],'^--',color='#c49454',alpha=.7);ax2.axhline(6,color='#c49454',alpha=.35,ls=':')
        ax.set(title=s['run']+' · '+SCENE_NAMES[s['scene']],xlabel='场景开始后墙钟时间（s）',ylabel='中心偏差（pt）',ylim=(0,None));ax2.set_ylabel('主簇完整500ms窗数');ax.grid(alpha=.1)
    fig.suptitle('多久拿到位置：前缀只使用当时已结束的实测窗口\n蓝线偏差是回顾性检查；至少6个主簇窗才有初步候选，缺少感应数据时不能估计',fontsize=12)
    fig.tight_layout();fig.savefig(out/'home_acquisition.png',dpi=165);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.8))
    names=['只用速度/RMS','再加50pt home'];vals=[baseline,metrics['50']['withAB']]
    axes[0].bar(np.arange(2)-.16,[v['active_recall']*100 for v in vals],width=.32,label='主动召回',color='#745bb1')
    axes[0].bar(np.arange(2)+.16,[v['natural_called_active']/v['natural']*100 for v in vals],width=.32,label='自然候选误报',color='#b28b57')
    axes[0].set(xticks=range(2),xticklabels=names,ylabel='C3窗口百分比',ylim=(0,100));axes[0].legend();axes[0].grid(axis='y',alpha=.12)
    for radius,color in zip(RADII,['#658d9e','#8d65ac','#b99867']):
        v=metrics[str(radius)]['withAB'];axes[1].scatter(v['natural_called_active']/v['natural']*100,v['active_recall']*100,s=90,label=f'{radius} pt（{metrics[str(radius)]["usableWindows"]}窗有模型）',color=color)
    axes[1].set(xlabel='自然候选误报（%）',ylabel='主动召回（%）',xlim=(0,100),ylim=(0,100));axes[1].legend(fontsize=9);axes[1].grid(alpha=.12)
    fig.suptitle('Home过滤的收益与误排风险：同姿势、同场景 A 基线估计 → C3回顾性检验\n仅可信热点内≥80%覆盖且低运动时抑制；30/80pt只是敏感性检查，不用C选参数',fontsize=12)
    fig.tight_layout();fig.savefig(out/'home_filter_tradeoff.png',dpi=165);plt.close(fig)
    (out/'home-position.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    rows=[]
    for s in summary:
        tr=s['train'];ck=s['check'];a=s['acquisition']
        rows.append([s['run']+'／'+SCENE_NAMES[s['scene']],f"({fmt(tr['cx'],0)}, {fmt(tr['cy'],0)})"if tr else'不足',str(tr['clusterWindows'])if tr else'0',str(ck['clusterWindows'])if ck else'0',fmt(s['centerShift_pt'],1),str(a['firstCandidate_s'])+'s'if a['firstCandidate_s']else'不足',str(a['onlineTentative_s'])+'s'if a['onlineTentative_s']else'未暂稳',str(a['retrospectiveStable_s'])+'s'if a['retrospectiveStable_s']else'未复现','复现热点'if s['replicated']else'未确认'])
    main=metrics['50'];combined=main['withAB'];lines=[
        '# Home position：同场景位置估计与过滤风险','',
        '**能够估计手机内反复出现的低运动热点，尚不能把热点直接认定为自然休息位置。** 只用 A5–A7 自然基线学习，每姿势／场景分别估计；固定实验起点不进入学习。两轮均右手，拇指先、食指后。','',
        '## 1. 这次实际估计到什么','',
        table(['姿势／场景','前60s XY中心（pt）','前主簇窗数','后主簇窗数','前后偏差pt','初步候选','在线暂稳','回顾性稳定时间','状态'],rows),'',
        '坐标为手机局部坐标，左上角(0,0)，右下角(390,830)。圆半径固定50pt，主簇至少6个非重叠500ms完整窗；这些是统计中心，不伪装成实测坐标。前后主簇各≥6窗且中心差≤50pt才记“复现热点”。Z保留原API值，不参与主要位置判断，不换算毫米。','',
        '![自然热点](home_position_map.png)','',
        '## 2. 在同一场景下需要多久','',
        '初步候选只表示至少积累约3秒有效低运动悬停，墙钟时间取决于真实感应覆盖。在线暂稳要求至少两个有新增窗口的检查点中心差≤20pt；它可能随后漂移。回顾性稳定时间另外要求此后各检查点始终接近60秒中心，并通过后60秒复现检查，不能把未来确认当成实时已知事实。取样检查点为2/5/10/15/20/30/45/60秒，时间是该网格上的观测上界。','',
        '![获取时间](home_acquisition.png)','',
        '若笔尖长时间离开感应范围，系统拿不到其实际位置；缺口不当作休息。低运动也可能是正在阅读、对准或看菜单，因此3秒累计数据不等于3秒就确认心理home。实际在线使用需显示/维护置信度，未确认时不进行位置拒绝。','',
        '## 3. 同一姿势能否全场景共用一个home','',
        table(['姿势','场景对','前60秒中心距离pt'],[[r['run'],SCENE_NAMES[r['scene1']]+'／'+SCENE_NAMES[r['scene2']],fmt(r['centerDistance_pt'],1)]for r in cross_scene]),'',
        '页面布局和手部操作位置会影响热点，应先按姿势和场景建立位置参考；手机屏幕位置与阅读内容对象是不同参照，页面滚动不能把同屏位置误当成同一内容对象。握姿变化应重新学习。','',
        '## 4. 用home抑制规则可能触发，实际收益如何','',
        table(['同段自然阅读：前60s估计→后60s检查','自然候选窗','位置规则抑制窗','后续C3应用时模型年龄中位min'],[[r['run']+'／'+SCENE_NAMES[r['scene']],r['naturalWindows'],r['suppressed'],fmt(r['c3ModelAgeMedian_s']/60,1)if r['c3ModelAgeMedian_s']is not None else'—']for r in same_segment]),'',
        '同段检查只用训练主簇足够的模型，不用后半段结果选择模型；只有自然条件，所以候选减少量不等于意图识别性能。后续C3虽然场景名称相同，已隔多个操作阶段，内容及笔尖常驻位置可能改变；旧参考点的迁移效果需单独测量。','',
        '冻结A前60秒中心，以A后60秒确认是否复现，不用B/C调整中心或半径。仅当同姿势／同场景模型复现、当前500ms窗≥80%实测时间在home圆内、速度中位≤100pt/s且RMS≤15pt时模拟降低触发；其余窗口保留。此处为了测风险模拟完全抑制，产品只应把home作为负向先验并允许明确主动操作。','',
        table(['C3成功/自然候选窗口','主动识别','自然候选误报','平衡准确率'],[
            ['原A/B速度-RMS模型',f"{baseline['true_active']}/{baseline['active']}",f"{baseline['natural_called_active']}/{baseline['natural']}",fmt(baseline['balanced_accuracy']*100,1)+'%'],
            ['只用home过滤，其余均视为候选',f"{main['homeOnly']['true_active']}/{main['homeOnly']['active']}",f"{main['homeOnly']['natural_called_active']}/{main['homeOnly']['natural']}",fmt(main['homeOnly']['balanced_accuracy']*100,1)+'%'],
            ['速度-RMS＋50pt home',f"{combined['true_active']}/{combined['active']}",f"{combined['natural_called_active']}/{combined['natural']}",fmt(combined['balanced_accuracy']*100,1)+'%']]),'',
        f"50pt规则在96个C3窗口中有 {main['usableWindows']} 个具备复现模型，抑制 {main['naturalSuppressed']}/69 个自然候选，同时误排 {main['activeSuppressed']}/27 个成功主动窗。模型缺失窗口不抑制；这些不是实际误触/心理意图标签。",'',
        '**本轮固定home没有改善C3区分：自然误报没有减少，还误排了一个主动窗。** 即使把半径扩到80pt，原模型自然误报仅由20降至18，同时主动识别23降至22，平衡准确率77.7%仍低于原78.1%。不能据此部署固定位置拒绝规则。','',
        table(['阅读场景','原主动识别／自然误报','加home后主动识别／自然误报'],[[SCENE_NAMES[s],f"{v['base']['true_active']}/{v['base']['active']} · {v['base']['natural_called_active']}/{v['base']['natural']}",f"{v['withAB']['true_active']}/{v['withAB']['active']} · {v['withAB']['natural_called_active']}/{v['withAB']['natural']}" ]for s,v in per_scene.items()]),'',
        '![过滤代价](home_filter_tradeoff.png)','',
        '## 5. 可以用到哪些行为，哪些不能硬过滤','',
        table(['主动任务／姿势','完整500ms窗','跨阅读home模型可用窗','模拟误排窗'],[[r['task']+'／'+r['run'],r['windows'],r['usable'],r['suppressed']]for r in transfer]),'',
        'B1–B3 的表只检查阅读home向抽象任务迁移的误排，不能冒充同场景验证。若指定目标就在home附近，用户仍能有主动意图；B1菜单后移动/点击、B3多目标转移与B4闭合路径必须保留。B4不参与静态位置抑制，不裁剪home内轨迹；强制起点也不能被当成无意图区。','',
        '## 6. 当前结论与下一步','',
        f"同段自然阅读的 {sum(r['naturalWindows']for r in same_segment)} 个后60秒候选中，仅 {sum(r['suppressed']for r in same_segment)} 个被固定50pt规则抑制；参考点对规则候选的过滤收益很有限。C3应用时距估计约6–11分钟，场景名称相同仍不足以保证同一位置参考有效。",'',
        '当前检测对象是Pencil笔尖的手机内XY低运动热点。它需要自然休息标注或相同对象的主动/自然困难对照才能确认home属性。位置应与接近/离开、速度变化、对象命中及后续行为组合使用；参考点需要随场景/握姿变化重估，不把模型训练进当前采集App。单参与者两姿势、C已探索、主动成功窗口筛选及感应覆盖不足继续限制结果。','',
        '[整体行为报告](behavior-overview.html) · [home窗口与原始序号](home_candidates.csv) · [过滤逐窗证据](home_filter_windows.csv) · [模型/时间/敏感性参数](home-position.json) · [3D回放](replay-v2.html)','',
        f"原始数据：{data['source']}；SHA256 {data['sha256']}。原文件只读，未删除/修改任何数据；不改变旧报告或协议判定。"]
    (out/'home-position.md').write_text('\n'.join(lines));report_html(lines,out/'home-position.html','<a href="behavior-overview.html">整体 A/B/C 行为特征</a> · <a href="replay-v2.html">3D 回放</a>')
    print(json.dumps(dict(sceneModels=[{k:s[k]for k in ['run','scene','status','centerShift_pt','acquisition']}for s in summary],filter=metrics,c3Base=baseline,bTransfer=transfer),ensure_ascii=False,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('dataset',type=Path);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    d=json.loads(a.dataset.read_text());root=Path(__file__).resolve().parents[1]
    assert hashlib.sha256((root/'data'/d['source']).read_bytes()).hexdigest()==d['sha256']
    build(d,a.output)
