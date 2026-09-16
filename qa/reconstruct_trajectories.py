#!/usr/bin/env python3
"""Build an offline replay and plots from recorded Pencil samples; never modify CSV."""
import argparse, collections, csv, hashlib, json, math
from pathlib import Path

GAP_MS = 100
LABELS = {
    'TRIAL_START':'试次开始','START_ZONE_STABLE':'起点稳定','TARGET_APPEAR':'请求显示目标',
    'TARGET_DISPLAY_FRAME':'目标后续显示帧','TARGET_ENTER':'进入目标','TOUCH_DOWN':'接触',
    'TOUCH_UP':'抬笔','HOVER_END':'悬停结束','TRIAL_END':'试次结束',
    'TRIAL_FAIL':'失败','TRIAL_SUCCESS':'成功','TEST_PAUSE':'暂停',
    'SWIPE_START':'滑动开始','SWIPE_END':'滑动结束',
}
ERRORS = {'TRACKING_INTERRUPTED':'悬停中断','EARLY_TOUCH':'目标出现前接触',
          'MISSED_TARGET':'未命中目标','UNEXPECTED_INPUT':'非预期输入','TIMEOUT':'超时',
          'OUT_OF_BOUNDS':'超出区域','SKIPPED':'跳过'}

def number(value):
    if value == '' or value is None: return None
    n = float(value)
    if not math.isfinite(n): raise ValueError('Nonfinite sample')
    return n

def reconstruct(path):
    rows = list(csv.DictReader(path.open(encoding='utf-8', newline='')))
    grouped = collections.defaultdict(list)
    for row in rows:
        if row['trialID']: grouped[row['trialID']].append(row)
    trials = []
    for trial_id, records in grouped.items():
        begin = next((r for r in records if r['eventType']=='TRIAL_START'), None)
        if begin is None: continue
        origin = float(begin['monotonicTime'])
        end = next((r for r in records if r['eventType']=='TRIAL_END'), None)
        points = []
        for r in records:
            if r['recordType'] != 'SAMPLE': continue
            source = r['sampleSource']
            kind = 0 if 'HOVER' in source else (1 if r['inputType']=='PENCIL' else 2)
            points.append([(float(r['monotonicTime'])-origin)*1000,
                number(r['x']), number(r['y']), number(r['zOffset']), kind,
                r['hoverState'] if kind==0 else r['touchState'], int(r['sequence']),
                number(r['altitudeAngle']), number(r['azimuthAngle']), r['trialState'],source,r['inputType']])
        points.sort(key=lambda p:(p[0],p[6]))
        segments, gaps = [], []
        for i,p in enumerate(points):
            prev = points[i-1] if i else None
            discontinuity = prev is None or p[10]!=prev[10] or p[5]=='BEGAN' or prev[5] in ('ENDED','CANCELLED') or p[0]-prev[0]>GAP_MS
            if discontinuity: segments.append([i])
            else: segments[-1].append(i)
            if prev is not None and p[4]==prev[4] and p[0]-prev[0]>GAP_MS:
                gaps.append({'start':prev[0],'end':p[0],'ms':p[0]-prev[0],'kind':p[4]})
        events = [{'t':(float(r['monotonicTime'])-origin)*1000,'type':r['eventType'],
                   'state':r['trialState'],'error':r['errorType'],'seq':int(r['sequence']),
                   'x':number(r['touchX']), 'y':number(r['touchY'])}
                  for r in records if r['recordType']=='EVENT' and r['eventType'] in LABELS]
        events.sort(key=lambda e:(e['t'],e['seq']))
        tx,ty = number(begin['targetX']),number(begin['targetY'])
        duration = max([0]+[p[0] for p in points]+[e['t'] for e in events])
        touch_windows=[]
        for e in events:
            if e['type']!='TOUCH_DOWN':continue
            before=[p for p in points if p[4]==0 and p[5] not in ('ENDED','CANCELLED') and p[0]<=e['t']]
            window=[p for p in before if p[0]>=e['t']-600]
            touch_windows.append({'t':e['t'],'samples':len(window),
                'rangeStartsBefore600ms':bool(before and before[0][0]<=e['t']-600),
                'nearestMs':e['t']-window[-1][0] if window else None})
        trials.append({'id':trial_id,'index':int(begin['plannedIndex']),
            'total':int(begin['plannedTotal']),'test':int(begin['testID']),
            'repeat':begin['isRepeat']=='true','task':begin['taskInstruction'],
            'condition':begin['conditionID'],'success':end['success']=='true' if end else None,
            'error':end['errorType'] if end else '未结束','start':[1171,609],
            'target':[tx,ty,number(begin['targetWidth'])],'distance':number(begin['distanceA']),
            'duration':duration,'endTime':(float(end['monotonicTime'])-origin)*1000 if end else None,
            'points':points,'segments':segments,'gaps':gaps,'events':events,'touchWindows':touch_windows})
    samples=sum(len(t['points']) for t in trials)
    assert samples == sum(r['recordType']=='SAMPLE' for r in rows), 'Replay must retain all input samples'
    return {'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'recordCount':len(rows),'sampleCount':samples,'labels':LABELS,'errors':ERRORS,
        'gapThresholdMs':GAP_MS,'trials':trials}

HTML = r'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pencil 行为轨迹回放</title>
<style>
:root{color-scheme:dark;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;background:#10151d;color:#e8edf5}*{box-sizing:border-box}body{margin:0}header{padding:28px 32px 18px;border-bottom:1px solid #2b3443}h1{font-size:26px;margin:0 0 8px}p{margin:7px 0;color:#aab6c9;line-height:1.65;font-size:14px}main{padding:24px 32px;display:grid;grid-template-columns:minmax(500px,1fr) 330px;gap:24px;max-width:1520px;margin:auto}.panel{background:#19212e;border:1px solid #303d50;border-radius:16px;padding:20px}.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:16px}button,select{background:#253246;border:1px solid #435572;border-radius:8px;padding:9px 13px;color:#e8edf5;font-size:14px;cursor:pointer}button.primary{background:#176abe;border-color:#176abe}.label{font-size:13px;color:#aab6c9}#space{display:block;width:100%;aspect-ratio:1366/1024;background:#0b111a;border-radius:10px}#height{display:block;width:100%;height:155px;margin-top:14px}.legend{display:flex;gap:18px;flex-wrap:wrap;margin-top:14px;font-size:13px}.hover{color:#38d5e8}.touch{color:#ff9854}.target{color:#c2a7ff}input[type=range]{width:100%;accent-color:#38d5e8;margin:18px 0 6px}.stats{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:16px 0}.stat{padding:14px;background:#101722;border-radius:10px}.stat b{display:block;font-size:21px;margin-bottom:5px}.stat span{font-size:12px;color:#aab6c9}h2{font-size:20px;margin:0 0 10px}h3{font-size:15px;margin:20px 0 10px}.event{font-size:13px;border-left:2px solid #52647d;padding:8px 10px;margin:3px 0;display:flex;gap:10px}.event.active{background:#25394d;border-color:#38d5e8}.event span{min-width:70px;color:#91a5c0;font-variant-numeric:tabular-nums}#events{max-height:345px;overflow:auto}.status{padding:5px 9px;border-radius:7px;font-size:13px;background:#27413b}.fail{background:#563133}.details{font-family:ui-monospace,monospace;font-size:12px;overflow-wrap:anywhere;color:#97a8bc}.notice{border-top:1px solid #32415a;margin-top:18px;padding-top:14px}.time{font-variant-numeric:tabular-nums}#reading{font-size:13px;line-height:1.8;min-height:46px}#session{display:flex;gap:3px;flex-wrap:wrap;margin:12px 0}#session button{width:30px;padding:6px 0;font-size:11px;border:0;background:#28493e}#session button.fail{background:#63363b}#session button.selected{outline:2px solid #38d5e8}#summary{font-size:14px}@media(max-width:950px){main{grid-template-columns:1fr;padding:16px}header{padding:20px}.panel{padding:14px}}
</style>
<header><h1>Pencil 行为轨迹回放</h1><div id="summary"></div><p>根据原始坐标和单调时钟重建。悬停 Z 为 API 原值；超过 100 ms、输入切换或悬停结束时断线。轨迹连线只连接实测点。</p></header>
<main><section><div class="panel"><div class="toolbar"><button id="prev">← 上一次</button><select id="trial"></select><button id="next">下一次 →</button><button id="play" class="primary">播放</button><select id="speed"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option><option value="4">4×</option></select><select id="view"><option value="phone" selected>手机区域</option><option value="ipad">整个 iPad</option></select></div>
<canvas id="space"></canvas><div class="legend"><span class="hover">● 悬停轨迹</span><span class="touch">● Pencil 接触 / 点击</span><span style="color:#ef697e">● 手指接触</span><span class="target">○ 目标位置</span><span>○ 起点</span></div>
<input id="seek" type="range" min="0" max="100" step="1"><div class="toolbar"><span class="time" id="time"></span><button id="touchjump">触摸前 600 ms</button><button id="all">看完整轨迹</button></div><canvas id="height"></canvas><div id="reading"></div></div>
<div class="panel" style="margin-top:18px"><h3 style="margin-top:0">整组试次</h3><p>绿色成功，红色失败。点击切换试次。</p><div id="session"></div><p class="details" id="source"></p></div></section>
<aside class="panel"><h2 id="title"></h2><span id="status" class="status"></span><p id="task" style="font-size:17px;color:#eef4fc;margin-top:15px"></p><p id="condition"></p><div class="stats" id="stats"></div><h3>事件时间线</h3><div id="events"></div><h3>触摸前数据覆盖</h3><p id="coverage"></p><div class="notice"><p>显示的是笔尖位置与接触状态。不能由这些数据恢复手部姿态、眼动或“真实意图”。目标显示帧时间是软件帧标记，不是屏幕发光的实测时间。</p><p>整次回放包含结束后保留的输入。悬停离开后不推断其空间位置；请选择“整个 iPad”查看手机区域外的记录。</p></div></aside></main>
<script id="dataset" type="application/json">__DATA__</script>
<script>
const data=JSON.parse(document.getElementById('dataset').textContent),trials=data.trials;
const el=id=>document.getElementById(id);let selected=trials.findIndex(t=>t.success===true),now=0,playing=false,lastFrame=0;
if(selected<0)selected=0;
el('summary').textContent=`${trials.length} 次试验 · ${trials.filter(t=>t.success).length} 次成功 · ${trials.filter(t=>t.success===false).length} 次失败 · ${data.sampleCount.toLocaleString()} 个实测样本`;
el('source').textContent=`来源：${data.file} · SHA-256 ${data.sha256}`;
for(let i=0;i<trials.length;i++){const t=trials[i],o=document.createElement('option');o.value=i;o.textContent=`第 ${t.index} / ${t.total} 次 · ${t.success?'成功':(data.errors[t.error]||t.error)}`;el('trial').append(o);const b=document.createElement('button');b.textContent=t.index;b.className=t.success?'':'fail';b.onclick=()=>select(i);el('session').append(b)}
function stop(){playing=false;el('play').textContent='播放'}
function select(i){stop();selected=Math.max(0,Math.min(trials.length-1,i));const t=trials[selected];el('trial').value=selected;now=t.duration;el('seek').max=t.duration;el('seek').value=now;el('title').textContent=`第 ${t.index} / ${t.total} 次`;el('status').textContent=t.success?'成功':(data.errors[t.error]||t.error);el('status').className='status '+(t.success?'':'fail');el('task').textContent=t.task;el('condition').textContent=`距离 ${t.distance} pt · 目标直径 ${t.target[2]} pt · ${t.target[1]<t.start[1]?'向上':'向下'}`;
el('stats').replaceChildren();for(const [v,k] of [[(t.duration/1000).toFixed(2)+' s','记录时长'],[t.points.length,'原始样本'],[t.points.filter(p=>p[4]===0).length,'悬停样本'],[t.points.filter(p=>p[4]!==0).length,'接触样本（含手指）']]){const box=document.createElement('div');box.className='stat';const b=document.createElement('b');b.textContent=v;const span=document.createElement('span');span.textContent=k;box.append(b,span);el('stats').append(box)}
el('events').replaceChildren();t.events.forEach(e=>{const box=document.createElement('div');box.className='event';const s=document.createElement('span');s.textContent=(e.t/1000).toFixed(3)+' s';const d=document.createElement('div');d.textContent=(data.labels[e.type]||e.type)+(e.error?' · '+(data.errors[e.error]||e.error):'');box.append(s,d);box.onclick=()=>{stop();now=Math.max(0,e.t);el('seek').value=now;draw()};el('events').append(box)});
el('coverage').textContent=t.touchWindows.length?t.touchWindows.map(w=>`${(w.t/1000).toFixed(3)} s 接触前 600 ms：${w.samples} 个悬停点；${w.rangeStartsBefore600ms?'记录起始早于窗口':'记录范围未覆盖完整窗口'}${w.nearestMs!==null?'；最近点距接触 '+w.nearestMs.toFixed(1)+' ms':''}。`).join('\n'):'本次没有 TOUCH_DOWN 事件。';el('touchjump').disabled=!t.touchWindows.length;[...el('session').children].forEach((b,j)=>b.classList.toggle('selected',j===selected));draw()}
function context(id){const c=el(id),r=c.getBoundingClientRect(),d=window.devicePixelRatio||1;c.width=Math.round(r.width*d);c.height=Math.round(r.height*d);const ctx=c.getContext('2d');ctx.scale(d,d);return [ctx,r.width,r.height]}
function draw(){const t=trials[selected];el('time').textContent=`${(now/1000).toFixed(3)} / ${(t.duration/1000).toFixed(3)} s`;const [c,w,h]=context('space');const full=el('view').value==='ipad';const rect=full?[0,0,1366,1024]:[946,164,450,890];const scale=Math.min(w/rect[2],h/rect[3]),ox=(w-rect[2]*scale)/2,oy=(h-rect[3]*scale)/2;const x=v=>ox+(v-rect[0])*scale,y=v=>oy+(v-rect[1])*scale;c.fillStyle='#0b111a';c.fillRect(0,0,w,h);c.fillStyle='#f3f6fa';c.fillRect(x(976),y(194),390*scale,830*scale);c.strokeStyle='#657793';c.lineWidth=1;c.strokeRect(x(976),y(194),390*scale,830*scale);c.fillStyle='#a2b2c9';c.font='12px -apple-system,sans-serif';c.fillText(full?'1366 × 1024 pt · 手机区域在右下角':'手机区域 390 × 830 pt',12,18);
function circle(px,py,r,color,dash=false){c.beginPath();c.setLineDash(dash?[5,5]:[]);c.strokeStyle=color;c.lineWidth=2;c.arc(x(px),y(py),r*scale,0,Math.PI*2);c.stroke();c.setLineDash([])}
circle(t.start[0],t.start[1],32,'#8495ae',true);const appears=t.events.find(e=>e.type==='TARGET_DISPLAY_FRAME')||t.events.find(e=>e.type==='TARGET_APPEAR');circle(t.target[0],t.target[1],t.target[2]/2,appears&&now>=appears.t?'#8461d1':'#c9c3d4',!(appears&&now>=appears.t));
for(const segment of t.segments){const pts=segment.map(i=>t.points[i]).filter(p=>p[0]<=now);if(!pts.length)continue;c.strokeStyle=['#009fb2','#ec752a','#d8485c'][pts[0][4]];c.lineWidth=2;c.beginPath();pts.forEach((p,i)=>i?c.lineTo(x(p[1]),y(p[2])):c.moveTo(x(p[1]),y(p[2])));c.stroke();c.fillStyle=c.strokeStyle;for(const p of pts){c.beginPath();c.arc(x(p[1]),y(p[2]),1.5,0,Math.PI*2);c.fill()}}
for(const e of t.events){if(e.type==='TOUCH_DOWN'&&e.t<=now&&e.x!==null&&e.y!==null){c.fillStyle='#ef7c32';c.beginPath();c.arc(x(e.x),y(e.y),5,0,Math.PI*2);c.fill();circle(e.x,e.y,10/scale,'#dc6522')}}
const visible=t.points.filter(p=>p[0]<=now),p=visible[visible.length-1];if(p&&p[5]!=='ENDED'&&p[5]!=='CANCELLED'&&now-p[0]<=100){circle(p[1],p[2],7/scale,['#00afc1','#ef7c32','#d8485c'][p[4]]);el('reading').textContent=`${['Pencil 悬停','Pencil 接触','手指接触'][p[4]]} · 手机局部坐标 (${(p[1]-976).toFixed(1)}, ${(p[2]-194).toFixed(1)}) pt · Z ${p[3]===null?'未提供':p[3].toFixed(3)} · 原始序号 ${p[6]}`}else{el('reading').textContent='此时没有连续可用的位置样本；不推断光标位置。'}
const [z,zw,zh]=context('height'),left=46,right=14,top=24,bottom=28,pw=zw-left-right,ph=zh-top-bottom;const xx=v=>left+(v/t.duration)*pw,yy=v=>top+(1-v)*ph;z.fillStyle='#121a26';z.fillRect(0,0,zw,zh);z.fillStyle='#a8b9cf';z.font='11px -apple-system,sans-serif';z.fillText('悬停 Z（API 原值）',left,14);[0,0.5,1].forEach(v=>{z.strokeStyle='#2c3a50';z.beginPath();z.moveTo(left,yy(v));z.lineTo(zw-right,yy(v));z.stroke();z.fillStyle='#a8b9cf';z.fillText(String(v),12,yy(v)+4)});for(const seg of t.segments){const pts=seg.map(i=>t.points[i]).filter(p=>p[4]===0&&p[3]!==null);z.strokeStyle='#38d5e8';z.lineWidth=1.5;z.beginPath();pts.forEach((p,i)=>i?z.lineTo(xx(p[0]),yy(p[3])):z.moveTo(xx(p[0]),yy(p[3])));z.stroke();for(const p of pts){z.fillStyle='#38d5e8';z.fillRect(xx(p[0])-0.8,yy(p[3])-0.8,1.6,1.6)}}for(const e of t.events.filter(e=>['TOUCH_DOWN','TARGET_DISPLAY_FRAME','TRIAL_END'].includes(e.type))){z.strokeStyle=e.type==='TOUCH_DOWN'?'#ff9854':'#9c8dbc';z.setLineDash([3,4]);z.beginPath();z.moveTo(xx(e.t),top);z.lineTo(xx(e.t),zh-bottom);z.stroke();z.setLineDash([])}z.strokeStyle='#fff';z.beginPath();z.moveTo(xx(now),top);z.lineTo(xx(now),zh-bottom);z.stroke();z.fillStyle='#a8b9cf';z.fillText('0 s',left,zh-7);z.fillText((t.duration/1000).toFixed(2)+' s',zw-55,zh-7);[...el('events').children].forEach((box,i)=>box.classList.toggle('active',t.events[i].t<=now&&(i===t.events.length-1||t.events[i+1].t>now)))}
el('trial').onchange=()=>select(Number(el('trial').value));el('prev').onclick=()=>select(selected-1);el('next').onclick=()=>select(selected+1);el('view').onchange=draw;el('seek').oninput=()=>{stop();now=Number(el('seek').value);draw()};el('all').onclick=()=>{stop();now=trials[selected].duration;el('seek').value=now;draw()};el('touchjump').onclick=()=>{stop();now=Math.max(0,trials[selected].touchWindows[0].t-600);el('seek').value=now;draw()};el('play').onclick=()=>{if(playing){stop();return}if(now>=trials[selected].duration)now=0;playing=true;lastFrame=0;el('play').textContent='暂停';requestAnimationFrame(frame)};function frame(ts){if(!playing)return;if(lastFrame)now=Math.min(trials[selected].duration,now+(ts-lastFrame)*Number(el('speed').value));lastFrame=ts;el('seek').value=now;draw();if(now>=trials[selected].duration){stop();return}requestAnimationFrame(frame)}window.addEventListener('resize',draw);select(selected);
window.trajectoryReplay={data,select,seek:(ms)=>{stop();now=ms;el('seek').value=ms;draw()},getSelected:()=>selected};
</script></html>'''

def plots(data, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Rectangle
    from matplotlib.font_manager import FontProperties
    font=Path('/System/Library/Fonts/STHeiti Light.ttc')
    if font.exists(): plt.rcParams['font.family']=FontProperties(fname=str(font)).get_name()
    plt.rcParams['axes.unicode_minus']=False
    trials=data['trials']
    examples=[next(t for t in trials if t['success']),next(t for t in trials if t['error']=='TRACKING_INTERRUPTED'),next(t for t in trials if t['error']=='EARLY_TOUCH')]
    fig,axes=plt.subplots(2,3,figsize=(13.5,8.8),gridspec_kw={'height_ratios':[3,1]})
    for col,t in enumerate(examples):
        ax=axes[0,col];ax.set_xlim(-25,415);ax.set_ylim(855,-25);ax.set_aspect('equal');ax.add_patch(Rectangle((0,0),390,830,fill=False,color='#8b98aa'))
        ax.add_patch(Circle((195,415),32,fill=False,color='#8895a6',ls='--'))
        ax.add_patch(Circle((t['target'][0]-976,t['target'][1]-194),t['target'][2]/2,fill=False,color='#8461d1',lw=2))
        for seg in t['segments']:
            ps=[t['points'][i] for i in seg];color={0:'#009fb2',1:'#ec752a',2:'#d8485c'}[ps[0][4]]
            ax.plot([p[1]-976 for p in ps],[p[2]-194 for p in ps],'.-',color=color,lw=1,markersize=2)
        for e in t['events']:
            if e['type']=='TOUCH_DOWN' and e['x'] is not None:ax.scatter(e['x']-976,e['y']-194,s=50,color='#ec752a',zorder=4)
        result='成功' if t['success'] else ERRORS.get(t['error'],t['error'])
        ax.set_title(f"第 {t['index']}/72 次 · {result}\n距离 {t['distance']:g} pt / 直径 {t['target'][2]:g} pt",fontsize=11,pad=12)
        ax.set_xlabel('手机局部 X（pt）');ax.set_ylabel('手机局部 Y（pt，向下为正）')
        z=axes[1,col]
        for seg in t['segments']:
            ps=[t['points'][i] for i in seg if t['points'][i][4]==0 and t['points'][i][3] is not None]
            if ps:z.plot([p[0]/1000 for p in ps],[p[3] for p in ps],'.-',color='#009fb2',lw=1,markersize=2)
        for e in t['events']:
            if e['type'] in ('TOUCH_DOWN','TARGET_DISPLAY_FRAME','TRIAL_END'):
                z.axvline(e['t']/1000,color='#ec752a' if e['type']=='TOUCH_DOWN' else '#8461d1',lw=1,ls='--')
        z.set_xlim(0,t['duration']/1000);z.set_ylim(-0.04,1.04);z.set_xlabel('距试次开始（s）');z.set_ylabel('悬停 Z（API 原值）');z.grid(alpha=.2)
    fig.suptitle('真实 Pencil 行为轨迹：实测点与事件对齐',fontsize=17,y=.98)
    fig.text(.5,.012,'青色：悬停  ·  橙色：接触  ·  紫色：目标／帧标记  |  超过 100 ms 或输入结束时断线；未平滑，未补点。',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.025,1,.94));fig.savefig(output/'trajectory_examples.png',dpi=180);fig.savefig(output/'trajectory_examples.svg');plt.close(fig)
    fig,axes=plt.subplots(8,9,figsize=(14,20))
    for ax,t in zip(axes.flat,trials):
        ax.set_xlim(-10,400);ax.set_ylim(840,-10);ax.set_aspect('equal');ax.set_xticks([]);ax.set_yticks([])
        ax.add_patch(Circle((195,415),32,fill=False,color='#ccd1d9',lw=.5))
        ax.add_patch(Circle((t['target'][0]-976,t['target'][1]-194),t['target'][2]/2,fill=False,color='#8461d1',lw=.8))
        for seg in t['segments']:
            ps=[t['points'][i] for i in seg];ax.plot([p[1]-976 for p in ps],[p[2]-194 for p in ps],color={0:'#009fb2',1:'#ec752a',2:'#d8485c'}[ps[0][4]],lw=.65)
        ax.set_title(f"{t['index']} {'成功' if t['success'] else ERRORS.get(t['error'],t['error'])}",fontsize=7,color='#276342' if t['success'] else '#a3464b')
    fig.suptitle('72 次指向试验 · 手机区域轨迹总览',fontsize=17,y=.995);fig.tight_layout(rect=(0,0,1,.985));fig.savefig(output/'all_72_trajectories.png',dpi=150);plt.close(fig)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('csv',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    data=reconstruct(args.csv)
    (args.output/'trajectories.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    encoded=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    (args.output/'replay.html').write_text(HTML.replace('__DATA__',encoded),encoding='utf-8')
    plots(data,args.output)
    counts=collections.Counter(t['error'] if not t['success'] else 'SUCCESS' for t in data['trials'])
    summary={'source':str(args.csv.resolve()),'sha256':data['sha256'],'trials':len(data['trials']),
        'samplesRetained':data['sampleCount'],'outcomes':dict(counts),'gapThresholdMs':GAP_MS,
        'methods':['Coordinates and monotonic timestamps are unchanged; t is relative to TRIAL_START.',
            'Samples sorted by monotonic time then original sequence; source sequence is retained.',
            'No joining across >100 ms, input changes, BEGAN or previous ENDED/CANCELLED.',
            'Start position is the configured Test 1 center; target uses recorded coordinates.',
            'Playback includes retained post-outcome samples until original trial context changes.',
            'Z is the API value, not physical millimetres; no smoothing or missing-point synthesis.'],
        'limits':['Pencil trajectory does not reconstruct hand posture, eye movements or true intent.',
            'Display frame marker is software timing, not physical screen illumination.',
            'Replay applies to this recorded Test 1 dataset; other task start positions need their configuration.']}
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.output/'README.md').write_text('# Pencil 轨迹回放\n\n打开 `replay.html` 选择试次、拖动时间或播放。可切换手机区域与整个 iPad。\n\n- `trajectory_examples.png/.svg`：成功、悬停中断、提前接触的三个实例；下面为悬停 Z 时间曲线。\n- `all_72_trajectories.png`：全部 72 次总览。\n- `trajectories.json`：全部原始样本的回放表示，保留原记录序号。\n- `summary.json`：来源哈希、方法和限制。\n\n图中线条只连接同一连续采集段的实测点；100 ms 是回放断线阈值，不是意图或成功判定标准。悬停 Z 保留 API 原值，不换算毫米。静态图的目标圆是计划目标位置；动态回放用软件显示帧标记改变目标外观。\n\n这份数据只有 Test 1，显示笔尖行为，不能证明参与者意图。\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
