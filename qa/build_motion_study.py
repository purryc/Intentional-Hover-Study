"""Measured acceleration/deceleration and hover multiselect review."""
import argparse,csv,hashlib,json,math
from pathlib import Path
import numpy as np
from analyze_two_runs import dump_csv,weighted,fmt,table
from explore_hover_intent import window_features


def signed_motion(segment):
    rows=[];previous=None
    for a,b in zip(segment,segment[1:]):
        dt=b['t']-a['t']
        if dt<.001 or dt>.100000001:
            previous=None;continue
        vx=(b['x']-a['x'])/dt;vy=(b['y']-a['y'])/dt
        speed=math.hypot(vx,vy);tm=(a['t']+b['t'])/2
        row=dict(t=tm,speed=speed,dt=dt,seq0=a['sequence'],seq1=b['sequence'],speedRate=None,rateTime=None,rateDt=None,rateSeq0=None,rateSeq1=None,rateSeq2=None,vectorAcceleration=None)
        if previous:
            d=tm-previous['t'];row.update(speedRate=(speed-previous['speed'])/d,rateTime=(tm+previous['t'])/2,rateDt=d,rateSeq0=previous['seq0'],rateSeq1=a['sequence'],rateSeq2=b['sequence'],vectorAcceleration=math.hypot(vx-previous['vx'],vy-previous['vy'])/d)
        rows.append(row);previous=dict(row,vx=vx,vy=vy)
    return rows


def trend(rows,key='speed',timekey='t'):
    # Each row retains its support. Missing derivatives divide trend lines.
    values=np.array([r.get(key) if r.get(key) is not None else np.nan for r in rows],float)
    times=np.array([r.get(timekey) if r.get(timekey) is not None else np.nan for r in rows],float)
    result=[]
    for t,v in zip(times,values):
        if not math.isfinite(t) or not math.isfinite(v):result.append(float('nan'));continue
        valid=(abs(times-t)<=.04)&np.isfinite(values)
        result.append(float(np.median(values[valid])))
    return result


def selections(trial):
    rows=[]
    for order,e in enumerate((e for e in trial['events']if e['type']=='HOVER_SELECT'),1):
        start=float(e['metadata']['startTime'])-trial['start'];f=window_features(trial,start,start+.5)
        approach=None
        if f:
            segment=trial['segments'][f['segment']]
            p=[p for p in segment if start-.3<=p['t']<start]
            if len(p)>=8 and p[-1]['t']-p[0]['t']>=.2:
                speeds=[];weights=[]
                for a,b in zip(p,p[1:]):
                    dt=b['t']-a['t']
                    if dt>=.001:speeds.append(math.hypot(b['x']-a['x'],b['y']-a['y'])/dt);weights.append(dt)
                approach=weighted(speeds,weights)
        rows.append(dict(trialID=trial['id'],run=trial['run'],hand='RIGHT',trialIndex=trial['index'],order=order,objectID=e['metadata']['objectID'],dwellStart=start,selectTime=e['t'],actualDwell_ms=(e['t']-start)*1000,dwellSpeed_pt_s=f['speed_median_pt_s']if f else None,dwellRms_pt=f['rms_pt']if f else None,approachSpeed_pt_s=approach,continuousComparison=approach is not None and f is not None,slowdownRatio=(f['speed_median_pt_s']/approach)if f and approach and approach>0 else None))
    return rows


def build(data,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import Circle
    font_manager.fontManager.addfont('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
    plt.rcParams.update({'font.family':'Arial Unicode MS','axes.unicode_minus':False,'font.size':10})
    ts=[t for t in data['trials']if t['task']=='B3'];sel=[r for t in ts for r in selections(t)]
    motion=[];bytrial={}
    for tr in data['trials']:
        if tr['task']not in ['A1','A2','A3','A4','B1','B2','B3','B4']:continue
        bytrial[tr['id']]=[]
        for si,s in enumerate(tr['segments']):
            rows=signed_motion(s);bytrial[tr['id']].append(rows)
            motion.extend(dict(trialID=tr['id'],run=tr['run'],task=tr['task'],source=s[0]['source'],segment=si,**r)for r in rows)
    dump_csv(out/'motion_phases.csv',motion);dump_csv(out/'multiselect_metrics.csv',sel)
    colors=['#7e52d6','#ed8b32','#169c91'];runs=['拇指','食指']
    summaries=[]
    for run in runs:
        r=[r for r in sel if r['run']==run];paired=[r for r in r if r['continuousComparison']]
        summaries.append(dict(run=run,trials=sum(t['run']==run for t in ts),selections=len(r),continuousComparisons=len(paired),approachMedian=float(np.median([r['approachSpeed_pt_s']for r in paired]))if paired else None,dwellMedian=float(np.median([r['dwellSpeed_pt_s']for r in paired]))if paired else None,slowdownRatioMedian=float(np.median([r['slowdownRatio']for r in paired if r['slowdownRatio']is not None]))if paired else None,slowerCount=sum(r['dwellSpeed_pt_s']<r['approachSpeed_pt_s']for r in paired),actualDwellMedian_ms=float(np.median([r['actualDwell_ms']for r in r])),selectionOrders=[r['objectID']for r in r]))
    fig,axes=plt.subplots(2,6,figsize=(16,11))
    for i,run in enumerate(runs):
        for ax,t in zip(axes[i],[t for t in ts if t['run']==run]):
            ax.set(xlim=(0,390),ylim=(830,0),aspect='equal',xticks=[0,195,390]);ax.grid(alpha=.15)
            present=next(e['t']for e in t['events']if e['type']=='TARGET_PRESENT_REQUEST')
            rs=[r for r in sel if r['trialID']==t['id']]
            for obj in t['trial']['objects']:
                b=obj['bounds'];cx=b['x']+b['width']/2;cy=b['y']+b['height']/2
                requested=obj['id']in t['trial']['requested'];ax.add_patch(Circle((cx,cy),b['width']/2,fill=False,edgecolor='#6680a1'if requested else'#ccd3dc',lw=1.5))
                order=next((r['order']for r in rs if r['objectID']==obj['id']),None)
                ax.text(cx,cy,str(order)if order else'·',ha='center',va='center',color=colors[order-1]if order else'#abb4be',fontsize=13)
            for s in t['segments']:
                p=[p for p in s if p['t']>=present]
                if p:ax.plot([p['x']for p in p],[p['y']for p in p],lw=.65,alpha=.6,color='#718299')
                for r in rs:
                    p=[p for p in s if r['dwellStart']<=p['t']<=r['selectTime']]
                    if p:ax.plot([p['x']for p in p],[p['y']for p in p],'.-',ms=2,lw=1,color=colors[r['order']-1])
            ax.set_title(f"{run} · 第 {t['index']}/6 次\n{t['row']['target_to_end_s']:.2f} 秒"if 'row'in t else f"{run} · 第 {t['index']}/6 次\n{t['duration']-present:.2f} 秒")
    fig.suptitle('B3 Hover 多选：两轮全部 12 次实测路径\n圈内数字为实际选择顺序，彩色轨迹为有效 500 ms 停留，灰线含转移与重试；缺口断开',fontsize=13)
    fig.tight_layout();fig.savefig(out/'multiselect_paths.png',dpi=160);plt.close(fig)
    # Deterministic example selection: closest successful trial to median task duration.
    examples=[]
    for run in runs:
        candidates=[t for t in ts if t['run']==run and t['success']]
        duration=lambda t:t['duration']-next(e['t']for e in t['events']if e['type']=='TARGET_PRESENT_REQUEST')
        target=np.median([duration(t)for t in candidates]);examples.append(min(candidates,key=lambda t:abs(duration(t)-target)))
    fig,axes=plt.subplots(2,2,figsize=(14,8))
    for i,t in enumerate(examples):
        present=next(e['t']for e in t['events']if e['type']=='TARGET_PRESENT_REQUEST');rs=[r for r in sel if r['trialID']==t['id']]
        for ax,key,timekey,label in [(axes[i,0],'speed','t','XY 速度（pt/s）'),(axes[i,1],'speedRate','rateTime','有符号速度变化率（pt/s²）')]:
            for rows in bytrial[t['id']]:
                tt=[r[timekey]-present if r[timekey]is not None else np.nan for r in rows];raw=[r[key]if r[key]is not None else np.nan for r in rows];sm=trend(rows,key,timekey)
                ax.plot(tt,raw,color='#9cabbd',alpha=.25,lw=.6)
                ax.plot(tt,sm,color='#2c6599',lw=1.1)
            for r in rs:
                ax.axvspan(r['dwellStart']-present,r['selectTime']-present,color=colors[r['order']-1],alpha=.14)
                ax.axvline(r['selectTime']-present,color=colors[r['order']-1],lw=.9)
                ax.text(r['selectTime']-present,.94,f"选 {r['order']}",transform=ax.get_xaxis_transform(),va='top',ha='right',fontsize=9,color=colors[r['order']-1])
            ax.set(xlim=(0,t['duration']-present),xlabel='目标呈现后的时间（秒）',ylabel=label);ax.grid(alpha=.15)
            if key=='speedRate':ax.axhline(0,color='#444',lw=.7);ax.set_yscale('symlog',linthresh=100)
            ax.set_title(f"{t['run']} · 第 {t['index']}/6 次 · {'正值加速，负值减速'if key=='speedRate'else'峰值为快速移动，低谷为停留'}")
    fig.suptitle('B3 代表试次：选中一个→移向下一个→悬停选中\n浅线原始导数，深线同段 80 ms 中位显示趋势；阴影为有效停留，竖线为选中事件',fontsize=13)
    fig.tight_layout();fig.savefig(out/'multiselect_motion.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(13,7))
    for i,run in enumerate(runs):
        for j in range(3):
            ax=axes[i,j]
            for r in sel:
                if r['run']!=run or r['order']!=j+1:continue
                for rows in bytrial[r['trialID']]:
                    p=[m for m in rows if -.6<=m['t']-r['dwellStart']<=.6]
                    if p:ax.plot([m['t']-r['dwellStart']for m in p],trend(p),lw=.8,alpha=.6,color=colors[j])
            ax.axvspan(0,.5,color=colors[j],alpha=.08);ax.axvline(0,color='#555',lw=.8);ax.set(xlim=(-.6,.6),ylim=(0,None),xlabel='相对有效停留开始（秒）',ylabel='XY 速度（pt/s）',title=f'{run} · 第 {j+1} 个对象');ax.grid(alpha=.15)
    fig.suptitle('B3 36 次选择对齐：每条线为一次选择的实测速度趋势\n0 秒是最终有效停留开始，右侧阴影为 500 ms 停留；每姿势每对象 6 次，缺口断线',fontsize=13)
    fig.tight_layout();fig.savefig(out/'selection_alignment.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(13,7));geometry_examples=[]
    for i,task in enumerate(['A2','B2']):
        for run,color in zip(runs,['#e98737','#278dcc']):
            tr=next(t for t in data['trials']if t['task']==task and t['run']==run and t['success'] and t['trial']['distance']==220 and t['trial']['diameter']==50 and t['trial']['direction']==-1)
            source='TOUCH'if task=='A2'else'HOVER'
            present=next(e['t']for e in tr['events']if e['type']=='TARGET_PRESENT_REQUEST')
            begin=next((s[0]['t']for s in tr['segments']if source in s[0]['source']and s[-1]['t']>=present),present)if task=='A2'else present
            for segment,rows in zip(tr['segments'],bytrial[tr['id']]):
                if source not in segment[0]['source']:continue
                rows=[r for r in rows if r['t']>=begin]
                for ax,key,timekey in [(axes[i,0],'speed','t'),(axes[i,1],'speedRate','rateTime')]:
                    ax.plot([r[timekey]-begin if r[timekey]is not None else np.nan for r in rows],[r[key]if r[key]is not None else np.nan for r in rows],lw=.5,alpha=.15,color=color)
                    ax.plot([r[timekey]-begin if r[timekey]is not None else np.nan for r in rows],trend(rows,key,timekey),lw=1.2,color=color,label=run)
            if task=='B2':
                e=next(e for e in tr['events']if e['type']=='HOVER_SELECT');start=float(e['metadata']['startTime'])-tr['start']
                for ax in axes[i]:ax.axvspan(start-begin,e['t']-begin,color=color,alpha=.08)
            geometry_examples.append(dict(task=task,run=run,trialID=tr['id'],start=begin))
        axes[i,0].set(ylabel='XY 速度（pt/s）',title=task+(' 接触拖动：起步与制动'if task=='A2'else' 悬停单选：接近与停留'))
        axes[i,1].set(ylabel='有符号速度变化率（pt/s²）',title='正值加速，负值减速');axes[i,1].set_yscale('symlog',linthresh=100);axes[i,1].axhline(0,color='#444',lw=.7)
        for ax in axes[i]:
            ax.set(xlim=(0,None),xlabel='接触开始后（秒）'if task=='A2'else'目标出现后（秒）');ax.grid(alpha=.15)
        handles,labels=axes[i,0].get_legend_handles_labels();unique=dict(zip(labels,handles));axes[i,0].legend(unique.values(),unique.keys())
    fig.suptitle('相同几何示例：距离 220 pt、直径 50 pt、向上\n浅线原始导数，深线 80 ms 中位趋势；B2 阴影为有效停留，缺口断线',fontsize=13)
    fig.tight_layout();fig.savefig(out/'pointing_motion.png',dpi=170);plt.close(fig)
    result=dict(source=data['source'],sha256=data['sha256'],bothHands='RIGHT',summaries=summaries,examples=[dict(trialID=t['id'],run=t['run'],index=t['index'])for t in examples],geometryExamples=geometry_examples,signedMotionRows=len(motion),method='signed speed derivative in continuous XY; raw and 80ms display trend; paired approach/dwell windows')
    (out/'motion-study.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    lines=['# 加速／减速与 Hover 多选行动轨迹','',
           '**能看到多目标间移动与停留的结构；每次转移是否明显减速，要逐次检查。** 这是两轮右手操作：拇指、食指各一轮。手机外、手指、结束回调与缺口继续排除，原坐标不平滑。','',
           '## Hover Multiselect（B3）','',
           '两姿势均 6/6 完成，共 36 次悬停选择。每次选择有连续约 500 ms 停留；选择后再移向下一个对象。圈内 1/2/3 标出实际顺序，灰色保留早退、重定位和重试。','',
           table(['姿势','成功／试次','选择数','连续可比窗口','进入前速度中位 pt/s','停留速度中位 pt/s','同次停留／接近速度比中位','停留更慢次数'],[[s['run'],'6/6',s['selections'],s['continuousComparisons'],fmt(s['approachMedian'],1),fmt(s['dwellMedian'],1),fmt(s['slowdownRatioMedian']),s['slowerCount']]for s in summaries]),'',
           '进入前取 300 ms、覆盖至少 200 ms；停留取前 500 ms、覆盖至少 450 ms，且必须处于同一连续悬停段。“连续可比”之外的选择仍展示，但不计算速度下降。速度比 0.5 表示该次停留速度为进入前的一半；统计描述笔尖运动，不推断心理意图。','',
           '**食指的减速结构比较清楚：11 个连续可比的选择全部在进入目标后降速。** 接近速度中位约 218 pt/s，停留约 58 pt/s，同次速度比中位约 0.28，即下降约 72%。拇指只有 1 个选择有足够连续接近数据，其余 17 个缺少所需前窗，不能据此比较两姿势的制动能力，也不能把追踪断开解释为减速。','',
           '![全部多选路径](multiselect_paths.png)','',
           '## 加速与减速怎么看','',
           '**速度曲线上升表示加速，下降表示减速。** 新图的有符号速度变化率正值为加速、负值为减速。旧图的“二维加速度幅值”始终非负，它也包含转向变化，不能据其正负判断加速／减速。','',
           '浅线是原始导数，深线是同一连续段内 80 ms 中位显示趋势。原始回调位置量化会使导数频繁变号；判断一次移动的起步与制动应结合速度峰、有效停留阴影和目标路径。曲线不跨缺口连接，Z 不参与这些 XY 导数。','',
           '![代表多选速度和加减速](multiselect_motion.png)','',
           '代表试次自动选为每姿势完成时长最接近中位数的一次。完整六次对齐如下：','',
           '![选择对齐速度](selection_alignment.png)','',
           '## 单目标：拖动与 Hover 指向','',
           '下面保留相同距离、尺寸和方向的两姿势示例。A2 只展示接触拖动，B2 只展示悬停指向与有效停留；曲线结束处不补造零速度。图用于逐次观察起步、快速移动与制动，不把单个示例当成全部试次的平均曲线。','',
           '![单目标运动](pointing_motion.png)','',
           '## 与空中圈选的区别','',
           'B3 是逐个对象停留选择，适合观察“转移→停留→转移”的分段动作。B4 是持续移动并闭合的圈选，适合看路径弯曲、转向、闭合前制动，不能期待每个对象旁都有 500 ms 低速平台。原报告的圈选图和 3D 回放继续保留。','',
           '当前只有一位参与者，各姿势一轮。这些图可以揭示本轮操作结构，不能证明普遍规律，也不能把采样噪声当成反复动作纠正。','',
           '[打开 3D 回放](replay-v2.html) · [总报告](report.html) · [逐对象指标](multiselect_metrics.csv) · [有符号导数及支持序号](motion_phases.csv) · [方法与结果 JSON](motion-study.json)','']
    (out/'motion-study.md').write_text('\n'.join(lines))
    import html,re
    parts=[];tab=False
    for line in '\n'.join(lines).splitlines():
        if line.startswith('|'):
            if line.startswith('| ---'):continue
            if not tab:parts.append('<table>');tab=True
            parts.append('<tr>'+''.join('<td>'+html.escape(c.strip())+'</td>'for c in line.strip('|').split('|'))+'</tr>');continue
        if tab:parts.append('</table>');tab=False
        if line.startswith('!['):parts.append('<img src="'+line.split('](')[1][:-1]+'">');continue
        if line.startswith('#'):
            level=len(line)-len(line.lstrip('#'));parts.append(f'<h{level}>{html.escape(line[level:].strip())}</h{level}>');continue
        if line:
            text=html.escape(line);text=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',text);text=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',text);parts.append('<p>'+text+'</p>')
    (out/'motion-study.html').write_text('<!doctype html><meta charset="utf-8"><title>加减速与 Hover 多选</title><style>body{font:16px system-ui;max-width:1250px;padding:24px;margin:auto;line-height:1.7;color:#263648}img{width:100%}table{border-collapse:collapse;width:100%;font-size:13px}td{border:1px solid #ddd;padding:8px}tr:first-child{background:#eef3f8}a{color:#1673ad}</style><a href="behavior-overview.html">整体 A/B/C 行为特征</a> · '+''.join(parts))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('dataset',type=Path);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    data=json.loads(a.dataset.read_text());root=Path(__file__).resolve().parents[1]
    assert hashlib.sha256((root/'data'/data['source']).read_bytes()).hexdigest()==data['sha256']
    build(data,a.output)
