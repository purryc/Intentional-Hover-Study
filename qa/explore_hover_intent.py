"""Offline instructed-intent exploration, with no future samples or raw-data edits."""
import collections, json, math
from pathlib import Path
import numpy as np


def annotate(trial):
    trial.setdefault('rawSuccess', trial.get('success', False))
    trial.setdefault('rawError', trial.get('error', ''))
    trial['reportedHand'] = 'RIGHT'
    trial['handSource'] = 'USER_CONFIRMATION'
    menu_open = False
    selected_b = False
    for e in trial['events']:
        if e['type'] == 'MENU_OPEN':
            menu_open = True
        if menu_open and e['type'] == 'MENU_SELECT' and e['metadata'].get('item') == 'B':
            selected_b = True
    if trial['task'] == 'B1' and trial['rawError'] == 'WRONG_MENU_ITEM' and menu_open and selected_b:
        trial['success'] = True
        trial['error'] = ''
        trial['analysisOverrideReason'] = 'USER_CONFIRMED_EXPECTED_B'


def window_features(trial, start, end):
    """One measured segment only. Never include a point beyond end or before start."""
    candidates = []
    for si, segment in enumerate(trial['segments']):
        if not segment or 'HOVER' not in segment[0]['source']:
            continue
        p = [p for p in segment if start - 1e-8 <= p['t'] <= end + 1e-8]
        if len(p) >= 12 and p[-1]['t'] - p[0]['t'] >= .45:
            candidates.append((si, p))
    if len(candidates) != 1:
        return None
    si, p = candidates[0]
    xy = np.array([[q['x'], q['y']] for q in p]); ts = np.array([q['t'] for q in p])
    dt = np.diff(ts); delta = np.diff(xy, axis=0)
    if np.any(dt <= 0) or np.any(dt > .100000001):
        return None
    support = dt >= .001
    if not support.any():
        return None
    speed = np.linalg.norm(delta[support], axis=1) / dt[support]
    w = dt[support]; order = np.argsort(speed)
    speed_median = float(speed[order][np.searchsorted(np.cumsum(w[order]), w.sum()/2)])
    # Time-weighted positions using actual measured edges, without interpolation.
    center = np.average(xy[:-1], axis=0, weights=dt)
    rms = float(np.sqrt(np.average(np.sum((xy[:-1]-center)**2, axis=1), weights=dt)))
    z = [q['z'] for q in p if q.get('z') is not None]
    return dict(segment=si, points=len(p), observed_ms=float((ts[-1]-ts[0])*1000),
                first_t=float(ts[0]), last_t=float(ts[-1]), first_input_sequence=p[0]['inputSequence'],
                last_input_sequence=p[-1]['inputSequence'], speed_median_pt_s=speed_median,
                rms_pt=rms, path_pt=float(np.linalg.norm(delta,axis=1).sum()),
                displacement_pt=float(np.linalg.norm(xy[-1]-xy[0])),
                z_median_raw=float(np.median(z)) if z else None)


def episodes(trials):
    rows=[]; excluded=collections.Counter()
    for tr in trials:
        # C3 is the primary matched-scene comparison. A natural baselines and B dwells are descriptive.
        allowed = ['CANDIDATE'] if tr['condition']=='NATURAL' else ['HOVER_SELECT','MENU_OPEN']
        for e in tr['events']:
            if e['type'] not in allowed:
                continue
            m=e['metadata']; start_abs=m.get('startTime')
            if start_abs is None and e['type']=='MENU_OPEN':
                ds=next((d for d in reversed(tr['events']) if d['type']=='DWELL_START' and d['t']<=e['t']),None)
                start = ds['t'] if ds else None
            else:
                start = float(start_abs)-tr['start'] if start_abs is not None else None
            if start is None or start < -1e-8 or start+.5>e['t']+1e-7:
                excluded[tr['task']+'/'+tr['condition']+'/invalid_start']+=1;continue
            f=window_features(tr,start,start+.5)
            if f is None:
                excluded[tr['task']+'/'+tr['condition']+'/incomplete_window']+=1;continue
            rows.append(dict(trialID=tr['id'],sessionID=tr['session'],run=tr['run'],hand='RIGHT',task=tr['task'],
                             scene=tr['scene'],condition=tr['condition'],label=int(tr['condition']!='NATURAL'),
                             label_source='TASK_INSTRUCTION_PROXY',objectID=m.get('objectID','target'),
                             event=e['type'],event_t=e['t'],window_start=start,window_end=start+.5,**f))
    return rows,dict(excluded)


def auc(y, score):
    pos=score[y==1];neg=score[y==0]
    return float(((pos[:,None]>neg).sum()+.5*(pos[:,None]==neg).sum())/(len(pos)*len(neg))) if len(pos) and len(neg) else None


def assess(rows, scores):
    y=np.array([r['label'] for r in rows]);pred=np.array(scores)>=.5
    tp=int(np.sum(pred & (y==1)));fn=int(np.sum(~pred & (y==1)))
    fp=int(np.sum(pred & (y==0)));tn=int(np.sum(~pred & (y==0)))
    recall=tp/(tp+fn) if tp+fn else None;specificity=tn/(tn+fp) if tn+fp else None
    return dict(active=len(y[y==1]),natural=len(y[y==0]),true_active=tp,missed_active=fn,
                natural_called_active=fp,true_natural=tn,active_recall=recall,natural_specificity=specificity,
                balanced_accuracy=(recall+specificity)/2 if recall is not None and specificity is not None else None,
                auc=auc(y,np.asarray(scores)))


def cross_run(rows):
    results=[];used=[r for r in rows if r['task']=='C3']
    features=['speed_median_pt_s','rms_pt']
    for train_run in ['拇指','食指']:
        train=[r for r in used if r['run']==train_run];test=[r for r in used if r['run']!=train_run]
        if not train or not test or len({r['label']for r in train})<2:
            continue
        x=np.log1p(np.array([[r[f]for f in features]for r in train]));y=np.array([r['label']for r in train])
        # Each scene/class cell has equal training weight; no scene or protocol label as feature.
        counts=collections.Counter((r['scene'],r['label'])for r in train)
        weights=np.array([1/counts[r['scene'],r['label']]for r in train]);weights/=weights.sum()
        mean=np.average(x,axis=0,weights=weights)
        scale=np.sqrt(np.average((x-mean)**2,axis=0,weights=weights));scale=np.maximum(scale,1e-6)
        x=(x-mean)/scale;x=np.column_stack([np.ones(len(x)),x]);beta=np.zeros(3)
        for _ in range(1500):
            p=1/(1+np.exp(-np.clip(x@beta,-30,30)))
            grad=x.T@(weights*(p-y));grad[1:]+=.1*beta[1:];beta-=.1*grad
        xt=(np.log1p(np.array([[r[f]for f in features]for r in test]))-mean)/scale
        scores=1/(1+np.exp(-np.clip(np.column_stack([np.ones(len(xt)),xt])@beta,-30,30)))
        results.append(dict(train=train_run,test=test[0]['run'],features=features,threshold=.5,
                            train_active=int(y.sum()),train_natural=int((1-y).sum()),
                            train_trials=len({r['trialID']for r in train}),test_trials=len({r['trialID']for r in test}),
                            coefficients=beta.tolist(),**assess(test,scores),
                            scenes={s:assess([r for r in test if r['scene']==s],scores[[r['scene']==s for r in test]])for s in ['news','notes','video']}))
        for r,p in zip(test,scores):r['cross_run_probability']=float(p)
    return results


def explore(trials,out):
    from analyze_two_runs import dump_csv,table,fmt
    rows,excluded=episodes(trials);validation=cross_run(rows)
    distributions=[]
    for scene in ['news','notes','video']:
        for label in [0,1]:
            rs=[r for r in rows if r['task']=='C3' and r['scene']==scene and r['label']==label]
            distributions.append(dict(scene=scene,label=label,n=len(rs),trials=len({r['trialID']for r in rs}),
                speed_median=float(np.median([r['speed_median_pt_s']for r in rs])) if rs else None,
                rms_median=float(np.median([r['rms_pt']for r in rs])) if rs else None))
    result=dict(method='C3 first 500ms measured-window, two XY features, cross-posture same participant',
                limitations=['one participant','instruction proxy, not individual mental-intent ground truth','successful active windows only','scene geometry and task-order confounding'],
                excluded=excluded,distributions=distributions,cross_run=validation,
                intentional_moving_hover=dict(task='B4',valid_closures=sum(e['type']=='LASSO_CLOSE'for t in trials if t['task']=='B4'for e in t['events'])))
    dump_csv(out/'intent_episodes.csv',rows);(out/'intent_exploration.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,3,figsize=(12,4))
    for ax,scene,title in zip(axs,['news','notes','video'],['长文','图文流','短视频']):
        for label,color,name in [(0,'#84949f','自然候选'),(1,'#8455da','主动悬停')]:
            rs=[r for r in rows if r['task']=='C3' and r['scene']==scene and r['label']==label]
            for run,marker in [('拇指','o'),('食指','^')]:
                ds=[r for r in rs if r['run']==run]
                ax.scatter([r['speed_median_pt_s']for r in ds],[r['rms_pt']for r in ds],s=36,alpha=.75,color=color,marker=marker,label=f'{name} · {run}')
        ax.set(xscale='symlog',yscale='symlog',xlabel='XY 速度中位（pt/s）',ylabel='位置 RMS 散布（pt）',title=title);ax.grid(alpha=.2)
    axs[0].legend(fontsize=8);fig.suptitle('同样达到 500 ms 的 C3 悬停：颜色为指令标签，形状为姿势\n全部来自右手；每点为一个连续实测窗口，不是真实心理意图标签',fontsize=12);fig.tight_layout();fig.savefig(out/'intent_features.png',dpi=170);plt.close(fig)
    lines=['## Intentional Hover：轨迹能区分意图吗？','',
           '**任务指令可以标出主动 Hover；仅凭本轮轨迹还不能可靠确认心理意图。** 以下比较同一 C3 阅读场景中同样达到 500 ms 的主动选择和自然候选。自然候选的“无意图”只是实验指令代理标签。',
           '',table(['场景','指令标签','窗口数／试次数','XY 速度中位 pt/s','位置 RMS 中位 pt'],[[d['scene'],'主动'if d['label']else'自然',f"{d['n']} / {d['trials']}",fmt(d['speed_median'],1),fmt(d['rms_median'],1)]for d in distributions]),
           '', '![主动与自然悬停特征](intent_features.png)','',
           '只取每次对象停留的前 500 ms，不使用确认后的轨迹。要求同一连续段至少 450 ms 覆盖和 12 个点；保留窗口起止及采样序号。不跨缺口，不插值，不把 Z 换算毫米。',
           '', '### 跨姿势探索检验','',
           '使用速度中位数和位置 RMS 两个特征，在整轮上训练，再测试另一整轮。训练时平衡场景和类别权重，固定 0.5 阈值，不用任务名、条件或事件类别预测。AUC 衡量排序区分度（0.5 接近随机、1 为完全分开）；平衡准确率给两个类别相同权重。',
           '',table(['训练→测试','测试主动／自然','主动识别','自然误报为主动','平衡准确率','AUC'],[[v['train']+'→'+v['test'],f"{v['active']} / {v['natural']}",f"{v['true_active']}/{v['active']}",f"{v['natural_called_active']}/{v['natural']}",fmt(v['balanced_accuracy']*100,1)+'%',fmt(v['auc'])]for v in validation]),
           '', '**位置集中程度比速度提供更一致的线索。** 三场景主动窗口的位置散布中位约 4–5 pt，自然候选约 7–15 pt；但长文主动速度约 42 pt/s，自然约 37 pt/s，速度方向并不一致。两次跨轮测试分别把 9/22（40.9%）和 11/47（23.4%）的自然候选误报为主动，当前误报水平不足以支持可靠自动弹菜单。RMS 表示窗口内相对自身中心的位置散布，包含实际移动，不等于手部抖动幅度。',
           '', '这是同一参与者的跨姿势探索，不是独立用户验证。主动条件只比较成功达标窗；未完成纯 Hover 的尝试不能补造正例。不同内容对象大小、候选机会及先后练习仍会影响结果。各场景检验见 [intent_exploration.json](intent_exploration.json)，逐窗口证据见 [intent_episodes.csv](intent_episodes.csv)。',
           '', '**500 ms 只定义规则触发，不能直接表示 intentional hover。** 自然阅读中存在同样长且稳定的停留；长停留的后续时长不能用于 500 ms 时刻的在线判断。B4 则是移动型主动 Hover：本轮共 7 个有效闭合圈，可以识别圈选动作，但不等同于任意悬停意图识别。',
           '', '下一轮应在同一对象、同一视觉反馈下交替采集主动／自然停留，加入随机顺序和练习，并在独立参与者上验证。当前结果用于选择候选特征和定位规则误触风险。','']
    return lines
