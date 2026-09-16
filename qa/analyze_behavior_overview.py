"""A/B behavior discovery, retrospective frozen-feature C checks; raw data stays read-only."""
import argparse,collections,hashlib,json,math
from pathlib import Path
import numpy as np
import pandas as pd
from analyze_two_runs import weighted,med,fmt,table,dump_csv
from explore_hover_intent import episodes,assess,window_features
from build_motion_study import signed_motion,trend

TASKS=['A1','A2','A3','A4','A5','A6','A7','B1','B2','B3','B4','C1','C2','C3']
NAMES=['点击','拖动','纵向滚动','横向滚动','长文阅读','图文浏览','短视频浏览','Hover 后点击','Hover 指向／单选','Hover 多选','空中圈选','点击 vs Hover','滚动 vs Hover','阅读 vs Hover']
TITLES=dict(zip(TASKS,NAMES))


def presentation(tr):
    return next((e['t']for e in tr['events']if e['type']=='TARGET_PRESENT_REQUEST'),None)


def after_present(tr):
    start=presentation(tr)
    return [[p for p in s if p['t']>=start]for s in tr['segments']]if start is not None else []


def loop_candidate(segment):
    """No event labels. Scan raw anchors; algorithm closure is explicitly bounded at 20pt."""
    if len(segment)<12:return None
    tt=np.array([p['t']for p in segment]);xy=np.array([[p['x'],p['y']]for p in segment])
    if np.any(np.diff(tt)<=0)or np.any(np.diff(tt)>.100000001):raise ValueError('noncontinuous input')
    last=-math.inf;best=None
    for i in range(len(tt)-11):
        if tt[i]-last<.1:continue
        last=tt[i];end=np.searchsorted(tt,tt[i]+3,side='right')
        if end-i<12:continue
        p=xy[i:end];t=tt[i:end]-tt[i]
        distances=np.linalg.norm(p-p[0],axis=1)
        path=np.r_[0,np.cumsum(np.linalg.norm(np.diff(p,axis=0),axis=1))]
        cross=np.r_[0,np.cumsum(p[:-1,0]*p[1:,1]-p[1:,0]*p[:-1,1])]
        area=np.abs(cross+p[:,0]*p[0,1]-p[0,0]*p[:,1])/2
        valid=(t>=.5)&(np.arange(len(t))>=11)&(distances<=20)&(np.maximum.accumulate(distances)>=40)&(path>=120)&(area>=2000)
        idx=np.flatnonzero(valid)
        if len(idx):
            j=int(idx[0]);cand=dict(start=float(tt[i]),end=float(tt[i+j]),duration=float(t[j]),distance=float(distances[j]),path=float(path[j]),area=float(area[j]),seq0=segment[i]['sequence'],seq1=segment[i+j]['sequence'],algorithmClosingEdge=True)
            if best is None or cand['area']>best['area']:best=cand
    return best


def pre_target_hover(tr):
    """Inside the drawn circular target; longest measured run before contact/selection/menu."""
    start=presentation(tr)
    objects={o['id']:o for o in tr['trial'].get('objects',[])}
    # B3 has multiple objects; this feature is only used for matched single target tasks.
    obj=objects.get('target')
    if start is None or obj is None:return None
    touch=next((p['t']for s in tr['segments']for p in s if 'TOUCH'in p['source']and p['t']>=start),None)
    action=next((e['t']for e in tr['events']if e['type']in ['HOVER_SELECT','MENU_OPEN']),None)
    end=min([x for x in [touch,action,tr['duration']]if x is not None])
    b=obj['bounds'];cx=b['x']+b['width']/2;cy=b['y']+b['height']/2;r=b['width']/2
    best=0.;hits=0
    for s in tr['segments']:
        if not s or 'HOVER'not in s[0]['source']:continue
        began=None;last=None
        for p in s:
            inside=start<=p['t']<=end and math.hypot(p['x']-cx,p['y']-cy)<=r
            if not inside:began=None;last=None;continue
            hits+=1
            if began is None:began=p['t']
            last=p['t'];best=max(best,last-began)
    return dict(preTargetHover_ms=best*1000,targetHoverPoints=hits,cutoff=end)


def task_features(tr):
    row=dict(trialID=tr['id'],task=tr['task'],run=tr['run'],condition=tr['condition'],scene=tr['scene'],success=tr['success'],rawSuccess=tr['rawSuccess'],error=tr['error'],duration=tr['duration'],presented=presentation(tr)is not None)
    segs=[s for s in after_present(tr)if s];touch=sum(p['phase']=='BEGAN'and'TOUCH'in p['source']for s in segs for p in s)
    row['contactBegins']=touch;row['selections']=sum(e['type']=='HOVER_SELECT'for e in tr['events']);row['menus']=sum(e['type']=='MENU_OPEN'for e in tr['events'])
    candidate=None
    for src in ['HOVER','TOUCH']:
        speed=[];weights=[];acc=[];aw=[];pos=[];pw=[];neg=[];nw=[];observed=0
        for s in segs:
            if src not in s[0]['source']:continue
            m=signed_motion(s)
            for e in m:
                speed.append(e['speed']);weights.append(e['dt']);observed+=e['dt']
                if e['speedRate']is not None:
                    acc.append(e['vectorAcceleration']);aw.append(e['rateDt'])
                    if e['speedRate']>0:pos.append(e['speedRate']);pw.append(e['rateDt'])
                    if e['speedRate']<0:neg.append(-e['speedRate']);nw.append(e['rateDt'])
            if src=='HOVER':
                c=loop_candidate(s)
                if c and(candidate is None or c['area']>candidate['area']):candidate=c
        row.update({src.lower()+'_observed':observed,src.lower()+'_speed':weighted(speed,weights),src.lower()+'_accel_p95':weighted(acc,aw,.95),src.lower()+'_positive_rate_p95':weighted(pos,pw,.95),src.lower()+'_negative_rate_p95':weighted(neg,nw,.95)})
    row['loopCandidate']=candidate is not None;row['loopEvidence']=json.dumps(candidate)
    target=pre_target_hover(tr)
    if target:row.update(target)
    return row


def fit_ab(rows):
    train=[r for r in rows if r['task']in ['A5','A6','A7','B1','B2','B3']]
    assert all(r['task'][0]in 'AB'for r in train)
    fs=['speed_median_pt_s','rms_pt'];x=np.log1p(np.array([[r[f]for f in fs]for r in train]));y=np.array([r['label']for r in train])
    counts=collections.Counter((r['label'],r['trialID'])for r in train)
    trials={c:len({r['trialID']for r in train if r['label']==c})for c in [0,1]}
    w=np.array([1/(counts[r['label'],r['trialID']]*trials[r['label']])for r in train]);w/=w.sum()
    mu=np.average(x,axis=0,weights=w);sd=np.maximum(np.sqrt(np.average((x-mu)**2,axis=0,weights=w)),1e-6)
    x=np.column_stack([np.ones(len(x)),(x-mu)/sd]);b=np.zeros(3)
    for _ in range(1500):
        p=1/(1+np.exp(-np.clip(x@b,-30,30)));grad=x.T@(w*(p-y));grad[1:]+=.1*b[1:];b-=.1*grad
    return dict(features=fs,mean=mu.tolist(),scale=sd.tolist(),beta=b.tolist(),regularization=.1,threshold=.5,trainRows=len(train),trainPositive=int(y.sum()),trainNegative=int((1-y).sum()),trainTrials=trials,trainTaskCounts=dict(collections.Counter(r['task']for r in train)),cUsedForFit=False)


def predict(model,rows):
    if not rows:return np.array([])
    x=np.log1p(np.array([[r[f]for f in model['features']]for r in rows]));x=(x-np.array(model['mean']))/np.array(model['scale'])
    return 1/(1+np.exp(-np.clip(np.column_stack([np.ones(len(x)),x])@np.array(model['beta']),-30,30)))


def report_html(lines,path,navigation=''):
    import html,re
    out=[];in_table=False
    for s in '\n'.join(lines).splitlines():
        if s.startswith('|'):
            if s.startswith('| ---'):continue
            if not in_table:out.append('<table>');in_table=True
            out.append('<tr>'+''.join('<td>'+html.escape(c.strip())+'</td>'for c in s.strip('|').split('|'))+'</tr>');continue
        if in_table:out.append('</table>');in_table=False
        if s.startswith('!['):out.append('<img src="'+s.split('](')[1][:-1]+'">');continue
        if s.startswith('#'):
            n=len(s)-len(s.lstrip('#'));out.append(f'<h{n}>{html.escape(s[n:].strip())}</h{n}>');continue
        if s:
            t=html.escape(s);t=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',t);t=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',t);out.append('<p>'+t+'</p>')
    title='Home position 估计与过滤'if path.name=='home-position.html'else'A/B 行为特征与 C 验证'
    path.write_text('<!doctype html><meta charset="utf-8"><title>'+title+'</title><style>body{max-width:1250px;margin:auto;padding:28px;font:16px system-ui;line-height:1.7;color:#233646}table{width:100%;border-collapse:collapse;font-size:13px}td{padding:9px;border:1px solid #d7dfe7}tr:first-child{background:#edf3f8;font-weight:bold}img{width:100%}a{color:#1673ad}p{overflow-wrap:anywhere}</style>'+navigation+''.join(out))


def build(data,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font_manager.fontManager.addfont('/System/Library/Fonts/Supplemental/Arial Unicode.ttf');plt.rcParams.update({'font.family':'Arial Unicode MS','axes.unicode_minus':False,'font.size':10})
    trials=data['trials'];features=[task_features(t)for t in trials];eps,excluded=episodes(trials)
    model=fit_ab(eps);test=[r for r in eps if r['task']=='C3'];scores=predict(model,test);checked=assess(test,scores)
    for r,p in zip(test,scores):r['ab_score']=float(p)
    scene_checks={s:assess([r for r in test if r['scene']==s],scores[[r['scene']==s for r in test]])for s in ['news','notes','video']}
    c2=[r for r in eps if r['task']=='C2'];c2_check=assess(c2,predict(model,c2))
    approach=[]
    for r in eps:
        if r['task']not in ['B1','B2','B3']:continue
        tr=next(t for t in trials if t['id']==r['trialID']);s=tr['segments'][r['segment']]
        p=[p for p in s if r['window_start']-.3<=p['t']<r['window_start']]
        before=None
        if len(p)>=8 and p[-1]['t']-p[0]['t']>=.2:
            mm=signed_motion(p);before=weighted([m['speed']for m in mm],[m['dt']for m in mm])
        approach.append(dict(task=r['task'],run=r['run'],trialID=r['trialID'],windowStart=r['window_start'],approach=before,dwell=r['speed_median_pt_s'],slower=r['speed_median_pt_s']<before if before is not None else None))
    dump_csv(out/'behavior_task_features.csv',features);dump_csv(out/'target_hover_features.csv',[r for r in features if 'preTargetHover_ms'in r]);dump_csv(out/'behavior_windows.csv',eps)
    motion_summary=[];window_summary=[];target_summary=[];loop_summary=[]
    for task in TASKS:
        fs=[f for f in features if f['task']==task];valid=[f for f in fs if f['success']]
        motion_summary.append(dict(task=task,attempts=len(fs),success=len(valid),contactTrials=sum(f['contactBegins']>0 for f in valid),hoverSpeed=med([f['hover_speed']for f in valid]),touchSpeed=med([f['touch_speed']for f in valid]),hoverAccelP95=med([f['hover_accel_p95']for f in valid]),touchAccelP95=med([f['touch_accel_p95']for f in valid])))
        rs=[r for r in eps if r['task']==task]
        if rs:window_summary.append(dict(task=task,n=len(rs),speed=med([r['speed_median_pt_s']for r in rs]),rms=med([r['rms_pt']for r in rs])))
        rs=[f for f in valid if 'preTargetHover_ms'in f and f['presented']]
        if rs:target_summary.append(dict(task=task,n=len(rs),median_ms=med([f['preTargetHover_ms']for f in rs]),zeroHits=sum(f['targetHoverPoints']==0 for f in rs),over500=sum(f['preTargetHover_ms']>=500 for f in rs)))
        h=sum(f['hover_observed']for f in fs);loop_summary.append(dict(task=task,trials=len(fs),withLoop=sum(f['loopCandidate']for f in fs),hoverObserved_s=h))
    matched=[]
    def geometry_key(t):return(t['session'],t['trial']['distance'],t['trial']['diameter'],t['trial']['direction'])
    maps={task:{geometry_key(t):t for t in trials if t['task']==task and t['success']and presentation(t)is not None and t['trial']['distance']==220}for task in ['A1','B1','B2']}
    common=set(maps['A1'])&set(maps['B1'])&set(maps['B2'])
    for task in ['A1','B1','B2']:
        ids={maps[task][k]['id']for k in common};rs=[f for f in features if f['trialID']in ids]
        matched.append(dict(task=task,n=len(rs),preTargetHoverMedian_ms=med([f['preTargetHover_ms']for f in rs]),noTargetHover=sum(f['targetHoverPoints']==0 for f in rs)))
    menu=[dict(trialID=t['id'],run=t['run'],menuToClick_s=next(e['t']for e in t['events']if e['type']=='MENU_SELECT')-next(e['t']for e in t['events']if e['type']=='MENU_OPEN'))for t in trials if t['task']=='B1']
    result=dict(source=data['source'],sha256=data['sha256'],hand='RIGHT',windows=window_summary,motion=motion_summary,targetHover=target_summary,matchedSingleTargets=matched,approach=approach,menu=menu,loopScan=loop_summary,model=model,c3=checked,c3Scenes=scene_checks,c2PositiveWindowCheck=c2_check,episodeExclusions=excluded,validationStatus='RETROSPECTIVE_SAME_PARTICIPANT_C_PREVIOUSLY_EXPLORED')
    # A/B candidate windows, separated by task to reveal scene dependence.
    fig,axes=plt.subplots(1,3,figsize=(14,4.7))
    tasks=['A5','A6','A7','B1','B2','B3'];colors=['#93a2ae']*3+['#8b60d1']*3
    for ax,key,label in [(axes[0],'speed_median_pt_s','前 500 ms 速度中位（pt/s）'),(axes[1],'rms_pt','前 500 ms 位置 RMS（pt）')]:
        for i,(task,col)in enumerate(zip(tasks,colors)):
            v=[r[key]for r in eps if r['task']==task]
            ax.boxplot(v,positions=[i],widths=.55,showfliers=False,patch_artist=True,boxprops=dict(facecolor=col,alpha=.5))
            ax.scatter(i+np.linspace(-.15,.15,len(v)),v,s=9,alpha=.45,color=col)
        ax.set(xticks=range(6),xticklabels=tasks,ylabel=label,yscale='symlog',ylim=(0,None));ax.grid(axis='y',alpha=.15)
    for s,col in zip(['A5','A6','A7'],['#637d96','#bd8754','#57979a']):
        r=[r for r in eps if r['task']==s];axes[2].scatter([r['speed_median_pt_s']for r in r],[r['rms_pt']for r in r],s=20,alpha=.5,color=col,label=s+' 自然')
    r=[r for r in eps if r['task']in ['B1','B2','B3']];axes[2].scatter([r['speed_median_pt_s']for r in r],[r['rms_pt']for r in r],s=22,color='#8756d1',alpha=.6,label='B1–B3 主动')
    axes[2].set(xscale='symlog',yscale='symlog',xlabel='速度（pt/s）',ylabel='位置 RMS（pt）',xlim=(0,None),ylim=(0,None));axes[2].legend(fontsize=9);axes[2].grid(alpha=.15)
    fig.suptitle('A 自然阅读与 B1–B3 主动停留：同样达标 500 ms 的窗口\n长文／图文与主动 Hover 重叠；视频差异更大。500 ms 本身不作为分类特征',fontsize=13);fig.tight_layout();fig.savefig(out/'behavior_feature_atlas.png',dpi=165);plt.close(fig)
    # Representative full action families. Baselines use same geometry where available.
    fig,axes=plt.subplots(2,4,figsize=(15,8))
    examples=[]
    for j,task in enumerate(['B1','B2','B3','B4']):
        candidates=[t for t in trials if t['task']==task and t['run']=='食指'and t['success']and(task not in ['B1','B2']or geometry_key(t)in common)]
        dur=lambda t:t['duration']-presentation(t)
        center=np.median([dur(t)for t in candidates]);b=min(candidates,key=lambda t:abs(dur(t)-center))
        if task in ['B1','B2']:
            a=next(t for t in trials if t['task']=='A1'and t['run']=='食指'and t['success']and all(t['trial'][k]==b['trial'][k]for k in ['distance','diameter','direction']))
        elif task=='B3':a=next(t for t in trials if t['task']=='A6'and t['run']=='食指'and t['success'])
        else:a=next(t for t in trials if t['task']=='A7'and t['run']=='食指'and t['success'])
        examples.append(dict(bTask=task,bTrial=b['id'],aTask=a['task'],aTrial=a['id'],matchedGeometry=task in ['B1','B2']))
        for i,t in enumerate([a,b]):
            ax=axes[i,j];ax.set(xlim=(0,390),ylim=(830,0),aspect='equal',xticks=[0,195,390]);ax.grid(alpha=.12)
            if t['trial'].get('objects'):
                from matplotlib.patches import Circle
                for obj in t['trial']['objects']:
                    bo=obj['bounds'];ax.add_patch(Circle((bo['x']+bo['width']/2,bo['y']+bo['height']/2),bo['width']/2,fill=False,edgecolor='#acb8c5'))
            if t['task']=='B1':
                from matplotlib.patches import Rectangle
                opened=next(e for e in t['events']if e['type']=='MENU_OPEN')
                for item in json.loads(opened['metadata']['menu']):
                    bo=item['bounds'];ax.add_patch(Rectangle((bo['x'],bo['y']),bo['width'],bo['height'],fill=False,edgecolor='#aa8ac7',lw=.7))
                    ax.text(bo['x']+bo['width']-15,bo['y']+bo['height']/2,item['id']if item['id']!='CANCEL'else'×',fontsize=7,ha='right',va='center',color='#8650d1')
            for s in after_present(t):
                if not s:continue
                ax.plot([p['x']for p in s],[p['y']for p in s],color='#ee963d'if'TOUCH'in s[0]['source']else'#4f8da9',alpha=.65,lw=.6)
            for e in t['events']:
                if e['type']in ['HOVER_SELECT','MENU_OPEN']:
                    near=[p for s in t['segments']for p in s if abs(p['t']-e['t'])<.02]
                    if near:ax.scatter([near[-1]['x']],[near[-1]['y']],color='#8650d1',s=28)
            ax.set_title(f'{t["task"]} {TITLES[t["task"]]}\n'+('相同几何点击对照'if i==0 and j<2 else'阅读基线；几何未配对'if i==0 else'主动行为示例'))
    fig.suptitle('完整行动家族：上排基线、下排主动 Hover（食指代表例）\n蓝线悬停、橙线接触、紫点达标事件；所有实测段断线保留。阅读为 120 s，短任务时长不同，不比较线密度',fontsize=12);fig.tight_layout();fig.savefig(out/'behavior_signatures.png',dpi=165);plt.close(fig)
    result['signatureExamples']=examples
    # Raw phase curves use the same representative trials as the path diagram.
    fig,axes=plt.subplots(2,4,figsize=(15,7))
    for j,example in enumerate(examples):
        b=next(t for t in trials if t['id']==example['bTrial'])
        a=next(t for t in trials if t['id']==example['aTrial'])
        compared=[a,b]if example['matchedGeometry']else[b]
        for tr in compared:
            is_b=tr['id']==b['id'];start=presentation(tr)
            for s in after_present(tr):
                if len(s)<2:continue
                rows=signed_motion(s);color=('#ee963d'if'TOUCH'in s[0]['source']else'#4f8da9')if is_b else'#a2a7ae'
                for i,key,tk in [(0,'speed','t'),(1,'speedRate','rateTime')]:
                    tt=[r[tk]-start if r[tk]is not None else np.nan for r in rows]
                    vv=[r[key]if r[key]is not None else np.nan for r in rows]
                    axes[i,j].plot(tt,vv,lw=.5,alpha=.35,color=color,ls='-'if is_b else'--')
                    if is_b:axes[i,j].plot(tt,trend(rows,key,tk),lw=1,color=color)
        start=presentation(b)
        for r in eps:
            if r['trialID']==b['id']:
                for ax in axes[:,j]:ax.axvspan(r['window_start']-start,r['window_end']-start,color='#aa88da',alpha=.13)
        for e in b['events']:
            if e['type']in ['HOVER_SELECT','MENU_OPEN','MENU_SELECT','LASSO_CLOSE']:
                for ax in axes[:,j]:ax.axvline(e['t']-start,color='#8650d1',lw=.7,alpha=.7)
                axes[0,j].text(e['t']-start,.98,{'MENU_OPEN':'菜单','MENU_SELECT':'点击','HOVER_SELECT':'选择','LASSO_CLOSE':'闭合'}[e['type']],rotation=90,transform=axes[0,j].get_xaxis_transform(),va='top',fontsize=7)
        for i,ax in enumerate(axes[:,j]):
            ax.set(xlim=(0,b['duration']-start),yscale='symlog',xlabel='目标呈现后（s）');ax.grid(alpha=.15)
            ax.set_ylabel('速度（pt/s）'if i==0 else'速度变化率（pt/s²）')
            if i==0:ax.set_ylim(bottom=0)
            else:ax.axhline(0,color='#777',lw=.6)
        axes[0,j].set_title(b['task']+' '+TITLES[b['task']]+('\n灰虚线：同几何 A1'if example['matchedGeometry']else'\n无同几何 A 对照'))
    fig.suptitle('四类主动行为的速度与加减速：与路径图相同的食指代表试次\n蓝＝悬停，橙＝接触；细线原始导数，粗线同段 80 ms 中位趋势；紫色为驻留／事件，缺口断开',fontsize=12)
    fig.tight_layout();fig.savefig(out/'behavior_phase_curves.png',dpi=165);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4.5))
    for s,col in zip(['news','notes','video'],['#708b9d','#ae835a','#438d86']):
        for label,marker in [(0,'o'),(1,'^')]:
            rs=[r for r in test if r['scene']==s and r['label']==label];axes[0].scatter([r['rms_pt']for r in rs],[r['ab_score']for r in rs],color=col,marker=marker,s=27,alpha=.7,label=s+(' 主动'if label else' 自然'))
    axes[0].axhline(.5,color='#444',ls='--',lw=1);axes[0].set(xlabel='位置 RMS（pt）',ylabel='冻结 A/B 模型分数',xscale='symlog',xlim=(0,None));axes[0].legend(fontsize=8);axes[0].grid(alpha=.15)
    cm=np.array([[checked['true_natural'],checked['natural_called_active']],[checked['missed_active'],checked['true_active']]])
    axes[1].imshow(cm,cmap='Blues');axes[1].set(xticks=[0,1],xticklabels=['判为自然','判为主动'],yticks=[0,1],yticklabels=['自然候选','主动指令'],title='C3 回顾性留组检验：窗口数')
    for i in range(2):
        for j in range(2):axes[1].text(j,i,str(cm[i,j]),ha='center',va='center',fontsize=22,color='white'if cm[i,j]>30 else'#24435f')
    fig.suptitle('训练只用 A/B；冻结速度＋位置散布后检验 C3\n测试任务未参与本次拟合，但 C 此前已探索；分数未校准为真实意图概率',fontsize=12);fig.tight_layout();fig.savefig(out/'ab_discovery_c_check.png',dpi=165);plt.close(fig)
    (out/'behavior-overview.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    lines=['# 整体行为特征：A 基线 → B 主动行为 → C 混淆检验','',
        '**整体看，最有用的是动作阶段与路径结构。低速、减速、500 ms 停留都不能单独证明主动意图。** 两轮均右手，第一轮拇指、第二轮食指；B1 统一点击 B 按用户说明记动作完成，原判定保留。','',
        '## 1. 四类主动行为与基线的关系','',
        table(['主动行为','本轮可见结构','最相关 A 基线','区别强弱与限制'],[
            ['B2 Hover pointing／单选','接近目标→目标内停留→零触屏选择','A1 同几何点击；A5/A6 阅读停留','完成结构不同；低速与制动同样出现在点击和阅读中，500 ms 是协议设定'],
            ['B1 Hover 后点击','目标内停留→菜单保持打开→移向菜单项并点击','A1 同几何点击','两阶段动作清楚；菜单出现后的证据只能验证已完成动作，不能回推出现前的心理意图'],
            ['B3 Hover multiselect','目标 1 驻留→转移→目标 2 驻留→转移→目标 3 驻留，全程无接触','A5/A6 内容停留／对象切换','顺序空间转移比单次低速更有辨识度；本轮无同布局的自然多点操作基线'],
            ['B4 空中圈选','连续移动→较大面积闭合路径→提交对象集合','A 自然悬停与接触操作','本轮路径结构最独特；需独立滑窗查基线是否也有闭合轮廓，且缺少同布局非圈选条件']]),'',
        '本轮 B2 是纯悬停指向／单选，不是旧协议 Test 1 的指向后点击。B3/B4 的指定对象和完成要求由任务决定，不能把任务要求本身称为新发现的心理意图特征。','',
        '![完整行为家族](behavior_signatures.png)','',
        '## 2. A1–A7 的基线是什么','',
        table(['任务','完成／尝试','成功试次有接触数','目标后悬停速度中位 pt/s','接触速度中位 pt/s'],[[s['task']+' '+TITLES[s['task']],f"{s['success']}/{s['attempts']}",s['contactTrials'],fmt(s['hoverSpeed'],1),fmt(s['touchSpeed'],1)]for s in motion_summary if s['task'].startswith('A')]),'',
        'A1 是目标接近后落笔；A2 是接触中的起步、拖动与制动；A3/A4 是定向接触移动；这些也会出现加速峰和减速。因此“有减速”不是 Hover 独有特征。A5–A7 是悬停、接触、滚动、内容导航交替；自然同对象达标候选不要求笔尖静止。短视频对象范围大，笔尖移动较远仍可留在同一对象内。','',
        '速度每试次先作同段时间加权，再取成功试次中位数，且仅取目标出现后。自然阅读长达 120 秒，不能把其总路径、最大速度或线密度与几秒钟短任务直接比较。第二轮 A7 的未完成重做另计尝试，完整阅读对比取完成段。','',
        '## 3. 小目标驻留：和 A1 相比有区别，但大部分是协议决定','',
        table(['距离 220 pt、同姿势／尺寸／方向配对','共同成功试次数','触屏／菜单／选择前目标内最长连续悬停中位 ms','没有观测到目标内悬停'],[[s['task'],s['n'],fmt(s['preTargetHoverMedian_ms'],1),s['noTargetHover']]for s in matched]),'',
        '仅比较三任务均成功的 10 套相同几何，未成功 A1 不补造匹配。全部 33 个成功 A1 中也有 1 次点击前目标内连续悬停约 1,331 ms：超过 500 ms 并不等于在执行主动 Hover 选择。','',
        '只计圆形目标内、目标呈现后的实测连续悬停；A1 在首个接触处截止，B1 在菜单出现处截止，B2 在悬停选择处截止。零命中并不证明没有对准，可能是接近末段超出悬停感应或直接落笔。B1/B2 的长驻留由 500 ms 规则强制，不能当作自由行为分离验证。','',
        '## 4. 静态 Hover 与阅读：哪些特征真正重叠','',
        table(['达标窗口来自','500 ms 窗数','速度中位 pt/s','位置 RMS 中位 pt'],[[s['task']+' '+TITLES[s['task']],s['n'],fmt(s['speed'],1),fmt(s['rms'],1)]for s in window_summary if s['task'][0]in 'AB']),'',
        '这里比较同样达标 500 ms 的对象窗，排除了“是否达标”这个任务规则捷径。新闻候选 RMS 约 6 pt，B1/B2/B3 约 5–6 pt；单靠位置稳定无法明显区分。短视频自然候选约 24 pt，与主动 Hover 的距离更大，图文居中。主动停留的速度也并不总比阅读慢。','',
        '![A/B 静态特征分布](behavior_feature_atlas.png)','',
        '## 5. 接近→制动能否成为组合特征','',
        table(['任务／姿势','有效停留窗','有完整连续接近窗','停留更慢次数','接近／停留速度中位 pt/s'],[[task+' / '+run,len(rs),len(valid),sum(r['slower']for r in valid),fmt(med([r['approach']for r in valid]),1)+' / '+fmt(med([r['dwell']for r in valid]),1)]for task in ['B1','B2','B3']for run in ['拇指','食指']for rs in [[r for r in approach if r['task']==task and r['run']==run]]for valid in [[r for r in rs if r['approach']is not None]]]),'',
        '接近取最终有效停留前 300 ms，需同段覆盖至少 200 ms；停留取前 500 ms，需覆盖至少 450 ms。可以检查“先较快移动→进入目标后减速→持续局部驻留”，但追踪缺口会让接近阶段不可观测。A 点击／拖动也有制动，因此需再加对象约束、是否接触和后续转移结构。缺口不当作停顿，原始导数抖动不当作动作纠正。','',
        f'B1 菜单打开至点击的时间中位约 {fmt(med([r["menuToClick_s"]for r in menu]))} 秒，形成第二个操作阶段；B3 共 36 次离散选择，每次任务三次驻留、两次对象转移。各轮 B3 全部按 t0→t1→t2 选择，当前尚未观察自由选择顺序。[查看加减速与多选细图](motion-study.html)。','',
        '![四类行为速度及加减速](behavior_phase_curves.png)','',
        '曲线仅展示代表试次，不是总体平均或显著性检验。正速度变化率为加速、负值为减速；转弯可以有较大二维加速度但不改变速度大小。B4 主要是连续空中移动与闭合，而不是多次低速驻留。原始位置噪声与回调时间抖动会放大导数，不能把每个正负尖峰解释成一次有意识的加速或纠正。','',
        '## 6. 闭合路径是否在 A 中也出现','',
        table(['任务','保留尝试数','含独立闭合候选的尝试数','目标后可观测连续悬停秒'],[[s['task'],s['trials'],s['withLoop'],fmt(s['hoverObserved_s'],1)]for s in loop_summary if s['task'][0]in 'AB']),'',
        '扫描不读取 LASSO_CLOSE 或任务名作为识别依据。每 100 ms 选一个实测起点，扫描 0.5–3 秒连续悬停窗，要求回到 20 pt 内、离起点至少 40 pt、路径至少 120 pt、至少 12 点、面积至少 2,000 pt²。只允许末点到首点的算法闭合边，不跨缺口。自然长段有更多候选机会，表中同时报告实际可观测悬停秒。候选表示闭合轮廓，不表示成功选对对象或真实圈选意图；扫描会漏掉起点错位、时间窗外或追踪中断的圈线。','',
        'A1–A7 的 103 个保留尝试均未发现该闭合候选。B4 候选 8 次包含 6 个成功和 2 个失败试次；协议实际成功为 7/12，独立滑窗还漏掉 1 个成功试次。B1 有 1 个闭合候选，C3 自然阅读也有 1 个，因此该几何结构辨识度较强，仍不足以唯一确认圈选意图。','',
        '## 7. C1–C3 的角色：你的理解成立，但覆盖有限','',
        table(['混淆任务','主要验证什么','本轮数据是否够用'],[
            ['C1 同目标点击 vs Hover','A1/B2 的接近、局部停留及落笔边界','TAP 12/12；HOVER 0/12，全部触屏。缺完整 500 ms 正例，不能验证成功纯 Hover 的分离性能'],
            ['C2 同条带滚动 vs Hover','A3/A4 定向接触移动 vs 悬停选择标记','SCROLL 4/12；HOVER 4/12。滚动其余 8 次提前触屏，目标未显示；成功 HOVER 初始已在标记处，不适合验证远目标接近制动'],
            ['C3 同阅读内容自然 vs Hover','A5–A7 自然停留 vs 主动对象停留','NATURAL 36/36；HOVER 27/36。可作成功窗口检验：69 自然候选 vs 27 主动窗；9 个未成功主动试次另保留']]),'',
        '**正确流程是 A/B 发现候选特征→冻结特征／阈值→C 检验混淆。** 不能继续在 C 上挑特征、调阈值后把相同 C 当独立验证。先前我们已用 C3 做探索，因此下面叫“回顾性留组检验”。本次拟合只用 A/B，C 未参与参数拟合，但它不是此前完全未查看的新测试集。','',
        'C1–C3 没有 B3/B4 的同布局自然多目标或非圈选条件，也没有 B1 菜单两阶段混淆对照；它们主要验证静态 Hover 和接触／阅读边界，不能覆盖全部四类主动行为。','',
        '## 8. 冻结 A/B 特征后，在 C3 上实际检验','',
        f'训练：A5–A7 的 {model["trainNegative"]} 个自然候选窗与 B1–B3 的 {model["trainPositive"]} 个主动窗；两个 XY 特征为速度中位数与位置 RMS。类别权重相同，每类内按试次均衡，避免长阅读或 B3 的多个对象支配拟合。只在训练集标准化，固定正则 0.1、阈值 0.5；不用事件类别、任务 ID、Z 或选择后的样本作预测特征。','',
        table(['C3 检验','结果'],[['主动正确识别',f'{checked["true_active"]}/{checked["active"]}'],['自然候选误报为主动',f'{checked["natural_called_active"]}/{checked["natural"]}（{checked["natural_called_active"]/checked["natural"]*100:.1f}%）'],['平衡准确率',f'{checked["balanced_accuracy"]*100:.1f}%'],['AUC',fmt(checked['auc'])]]),'',
        table(['阅读场景','主动识别','自然误报','平衡准确率','AUC'],[[s,f'{v["true_active"]}/{v["active"]}',f'{v["natural_called_active"]}/{v["natural"]}',f'{v["balanced_accuracy"]*100:.1f}%',fmt(v['auc'])]for s,v in scene_checks.items()]),'',
        '![冻结 A/B 后 C3 检验](ab_discovery_c_check.png)','',
        f'C2 四个完整主动窗被同一模型识别 {c2_check["true_active"]}/4；没有成熟的自然候选负例，不能报告其完整二分类准确率。C1 没有完整主动达标窗，不补造正例。接触发生后的“有／无接触”可以识别已完成动作，但不能作为接触前的意图预测证据。','',
        '## 9. 最值得保留的行为特征','',
        table(['特征家族','本轮判断','用途'],[
            ['速度／加减速幅值','A/B 都有，单独区分弱；易受采样抖动影响','组合中的运动阶段信号，保留实际时间差'],
            ['小区域驻留与目标命中','主动与新闻／图文有明显重叠，视频差异更大','候选筛选，必须结合对象边界和感应覆盖'],
            ['接近制动＋局部驻留＋无接触','比单一停留更有解释力，但连续接近覆盖有限','B2 指向／静态选择的候选组合，待同对象验证'],
            ['悬停→菜单→再定位→点击','完整操作结构清楚，含界面状态的任务证据','B1 动作识别；不能当菜单出现前的独立意图分类器'],
            ['多个对象离散驻留及转移','B3 有清楚重复节奏，当前顺序与对象由任务固定','多选手势家族识别，需相同布局自然对照'],
            ['无接触的大面积闭合路径','B4 是当前最强路径结构候选，独立扫描结果见上表','圈选手势识别；与静态意图分开评估']]),'',
        '**下一轮最该补的是困难负例和专项混淆对照。** C1/C2 先练习并重新采集完整正例；为 B3 增加同布局自然经过／多点点击，为 B4 增加同布局不闭合经过／空中划动；C3 在相同对象大小、反馈和内容阶段采集主动／自然条件。固定特征后交给未参加训练的新参与者，不只复测同一人。','',
        '[逐试次特征](behavior_task_features.csv) · [窗口及 C3 分数](behavior_windows.csv) · [结果与模型参数](behavior-overview.json) · [原总报告](report.html) · [加减速细图](motion-study.html) · [3D 回放](replay-v2.html)','',
        f'数据来源：{data["source"]}；SHA256 {data["sha256"]}。原 CSV 未改动，保留全部失败、原菜单指令和用户覆核。自然候选的标签来自任务指令，不是逐段确认的心理意图；单参与者两姿势与先后练习效应仍限制泛化。']
    (out/'behavior-overview.md').write_text('\n'.join(lines));report_html(lines,out/'behavior-overview.html','<a href="home-position.html">Home position 与过滤</a> · <a href="replay-v2.html">3D 回放</a>')
    print(json.dumps(dict(windows=window_summary,matched=matched,loops=loop_summary,c3=checked,c2=c2_check),ensure_ascii=False,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('dataset',type=Path);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    data=json.loads(a.dataset.read_text());root=Path(__file__).resolve().parents[1]
    assert hashlib.sha256((root/'data'/data['source']).read_bytes()).hexdigest()==data['sha256']
    build(data,a.output)
