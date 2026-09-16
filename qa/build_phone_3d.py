#!/usr/bin/env python3
"""Generate a local Three.js phone-only replay; preserve the authoritative CSV."""
import argparse, collections, csv, hashlib, json, shutil
from pathlib import Path
from reconstruct_trajectories import reconstruct
from kinematics import build_kinematics

def build(source, output, three):
    original=reconstruct(source)
    data={k:v for k,v in original.items() if k!='trials'}
    data['trials']=[]; exclusions=collections.Counter()
    retained_sequences=set(); excluded_trials=[]
    for old in original['trials']:
        t={k:v for k,v in old.items() if k not in ('points','segments','gaps','touchWindows')}
        contaminated=any(p[11]!='PENCIL' for p in old['points'])
        if contaminated: excluded_trials.append(t['index'])
        t['excluded']=contaminated;t['points']=[];t['segments']=[];t['gaps']=[]
        for segment in old['segments']:
            current=[]
            for i in segment:
                p=old['points'][i]
                reason=None
                if p[11]!='PENCIL':reason='fingerInput'
                elif contaminated:reason='pencilInFingerAffectedTrial'
                elif not (976<=p[1]<=1366 and 194<=p[2]<=1024):reason='outsidePhone'
                elif p[4]==0 and p[5] in ('ENDED','CANCELLED'):reason='hoverTermination'
                elif p[4]==0 and p[3] is None:reason='missingHoverZ'
                if reason:
                    exclusions[reason]+=1
                    if current:t['segments'].append(current);current=[]
                    continue
                current.append(len(t['points']));t['points'].append(p);retained_sequences.add(p[6])
            if current:t['segments'].append(current)
        for a,b in zip(t['points'],t['points'][1:]):
            if b[0]-a[0]>100:t['gaps'].append({'start':a[0],'end':b[0],'ms':b[0]-a[0]})
        # Only contact events that match a retained Pencil BEGAN sample are visualized.
        t['events']=[e for e in old['events'] if e['type'] not in ('TOUCH_DOWN','TOUCH_UP') or
            (not contaminated and e['x'] is not None and 976<=e['x']<=1366 and 194<=e['y']<=1024 and
             any(abs(p[0]-e['t'])<.05 and p[4]==1 and p[5]==('BEGAN' if e['type']=='TOUCH_DOWN' else 'ENDED') for p in t['points']))]
        t['touchWindows']=[]
        for e in t['events']:
            if e['type']!='TOUCH_DOWN':continue
            before=[p for p in t['points'] if p[4]==0 and p[0]<=e['t']]
            window=[p for p in before if p[0]>=e['t']-600]
            t['touchWindows'].append({'t':e['t'],'samples':len(window),'rangeStartsBefore600ms':bool(before and before[0][0]<=e['t']-600),'nearestMs':e['t']-window[-1][0] if window else None})
        data['trials'].append(t)
    data['originalSampleCount']=original['sampleCount']
    data['sampleCount']=sum(len(t['points']) for t in data['trials'])
    data['exclusions']=dict(exclusions);data['excludedTrials']=excluded_trials
    data['kinematics'],motion_rows=build_kinematics(data)
    data['threeVersion']=json.loads((three/'package.json').read_text())['version']
    assert data['sampleCount']+sum(exclusions.values())==original['sampleCount']
    output.mkdir(parents=True,exist_ok=True)
    if (output/'replay.html').exists() and not (output/'replay-full-ipad-archived.html').exists():
        shutil.copy2(output/'replay.html',output/'replay-full-ipad-archived.html')
    vendor=output/'vendor';vendor.mkdir(exist_ok=True)
    for name in ('three.module.js','three.core.js'):shutil.copy2(three/'build'/name,vendor/name)
    shutil.copy2(three/'examples/jsm/controls/OrbitControls.js',vendor/'OrbitControls.js')
    shutil.copy2(three/'LICENSE',vendor/'THREE-LICENSE.txt')
    here=Path(__file__).parent
    shutil.copy2(here/'phone_3d.js',output/'phone_3d.js')
    shutil.copy2(here/'motion_charts.js',output/'motion_charts.js')
    (output/'phone_kinematics.json').write_text(json.dumps(data['kinematics'],ensure_ascii=False,separators=(',',':')))
    motion_columns=['trialID','plannedIndex','distanceConditionPt','targetDiameterPt','success','segmentID','inputSource','metric','timeFromTrialMs','value','unit','supportSequences','vx','vy','ax','ay','accelerationMagnitude']
    with (output/'phone_kinematics.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=motion_columns);writer.writeheader();writer.writerows(motion_rows)
    encoded=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    (output/'replay.html').write_text((here/'phone_3d.html').read_text().replace('__DATA__',encoded),encoding='utf-8')
    (output/'phone_trajectories.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    with source.open(encoding='utf-8',newline='') as f:
        reader=csv.DictReader(f);rows=list(reader);columns=reader.fieldnames
    with (output/'phone_pencil_samples.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
        writer.writerows(r for r in rows if r['recordType']=='SAMPLE' and int(r['sequence']) in retained_sequences)
    summary={'source':str(source.resolve()),'sourceSHA256':data['sha256'],'originalSamples':original['sampleCount'],
        'phonePencilSamples':data['sampleCount'],'excluded':dict(exclusions),'excludedTrials':excluded_trials,
        'remainingTrials':len(data['trials'])-len(excluded_trials),'threeVersion':data['threeVersion'],
        'method':'Keep Pencil only within local [0,390] × [0,830]. Break at every rejected sample and original segment boundary. Remove all trajectories of finger-affected trials; preserve original trial outcome and exclusion label.',
        'axes':'World X = localX - 195; world Z = localY - 415; world Y = raw hover Z × adjustable visual scale. Pencil contact is on page plane. API Z is not millimetres.',
        'excludedHoverEndMeaning':'ENDED/CANCELLED callbacks are not spatial motion estimates.',
        'libraries':'Local three.js and OrbitControls copied from existing Le2019 viewer, same version, no external requests.'}
    (output/'phone_3d_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    (output/'README-3D.md').write_text('# 手机仿真 3D 轨迹\n\n`replay.html` 为当前入口。拖动旋转、滚轮缩放，可切换俯视、逐次播放和汇总视图。所有依赖位于本地 vendor，无网络请求。ES 模块需要本地 HTTP 服务：\n\n```bash\npython3 -m http.server 8897 --bind 127.0.0.1 --directory /absolute/path/trajectory_2026-09-15\n```\n\n- `phone_trajectories.json`：过滤后带事件的完整回放。\n- `phone_pencil_samples.csv`：过滤后的原始 SAMPLE 列，原坐标、Z、时间和序号不变；不包含 EVENT 行。\n- `phone_3d_summary.json`：来源哈希、排除数量、坐标映射。\n- `replay-full-ipad-archived.html`：更新前视图存档；不用于本次手机仿真分析。\n\n手机区域为 390×830 pt，X 向右、Y 向屏幕下方；3D 竖直轴展示悬停 API Z，不换算毫米。接触点放在页面平面是依据接触状态，不是推算缺失悬停高度。高度显示比例只改变视觉，不改变数据。所有手指样本及受其影响的第 41、57 次试验轨迹排除；原失败标记和序号保留，不重写结果。排除点、来源切换、结束／重启及超过 100 ms 均断线。轨迹未平滑、未补点。\n\n参考：[Three.js 安装](https://threejs.org/manual/en/installation.html)、[OrbitControls](https://threejs.org/docs/pages/OrbitControls.html)。\n',encoding='utf-8')
    with (output/'README-3D.md').open('a',encoding='utf-8') as f:
        f.write('\n## 运动曲线\n\n3D 下方的“运动规律”面板包含平面速度、到目标中心的距离、悬停 Z，及可展开的切向加速度。可逐次查看，或按首次有效 Pencil 落笔对齐（−600 至 +100 ms），按成功/失败、距离、目标尺寸筛选。汇总 3D 轨迹时自动显示落笔对齐曲线；对齐筛选独立于 3D 汇总范围。\n\n默认原始计算曲线；80 ms 中值趋势只在同段内前后 40 ms 对已有指标取中值，不改变坐标、CSV 或导数。Z 不与 XY 合成为物理空间加速度。\n\n`phone_kinematics.csv` 是派生指标长表，保留试次、条件、输入来源、段号、时间及支持样本序号。速度在相邻点时间中点计算，单位 pt/s；切向加速度为相邻速度幅值变化率，单位 pt/s²；另存 vx/vy、ax/ay、accelerationMagnitude（二维加速度幅值）。没有接触的试次不纳入落笔对齐，不跨段插值。完整数据字典见项目 docs/motion-analysis.md。\n')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==data['sha256']
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('csv',type=Path);p.add_argument('output',type=Path);p.add_argument('--three',type=Path,required=True);a=p.parse_args();build(a.csv,a.output,a.three)
