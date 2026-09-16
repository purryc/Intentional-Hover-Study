#!/usr/bin/env python3
"""Build the V2.4 source release and a curated, aggregate-only Pages report."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from build_public_site import ROOT, build as build_legacy_site, digest, page

LEGACY_SHA = '1c2eff5549ea4bafb76b2d7e683e31ef5db07187161ffe2bda50f25859940b89'
V23_PREFIX_SHA = '780e62eac61e35d1412bb59e0532ffe0561365fa7238459e4785470ac12c7f12'
V23_PREFIX_BYTES = 477374349
V24_SHA = '270a784611dca91aaa34d783ccdfcb916b249f9307a49d4d03cd66e6984518ba'
FIGURES = {'sequence-comparison.png': 'motion-sequence.png',
           'z-curves.png': 'motion-z-change.png',
           'reading-home-gaze.png': 'reading-home-gaze.png',
           'target-vs-reading.png': 'target-vs-reading.png'}


def prefix_digest(path, size):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        remaining = size
        while remaining:
            block = stream.read(min(1024 * 1024, remaining))
            assert block, 'Current source is shorter than reviewed V2.3 prefix'
            value.update(block)
            remaining -= len(block)
    return value.hexdigest()


def replace_once(path, old, new):
    content = path.read_text()
    assert content.count(old) == 1, f'Unexpected template for {path.name}: {old[:60]}'
    path.write_text(content.replace(old, new))


def combined_page(atlas, gaze):
    reading = {row['task']: row for row in gaze['reading']}
    assert set(reading) == {'A5', 'A6', 'A7'}
    assert len(gaze['a1']) == 18 and all(row['success'] for row in gaze['a1'])
    valid_a1 = [row for row in gaze['a1'] if row['gazeWithinTargetR50'] is not None]
    assert len(valid_a1) == 16 and sum(row['gazeWithinTargetR50'] == 0 for row in valid_a1) == 14
    assert set(gaze['sessionTasks']) == {'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7'}
    calibration = gaze['calibrations']
    assert len(calibration) == 1 and calibration[0]['quality'] == 'COARSE_ONLY'
    assert 200 < calibration[0]['p90Pt'] < 220
    rows = ''.join(f'<tr><th>{name}</th><td>{r["homeCenter"][0]:.0f}, {r["homeCenter"][1]:.0f}</td>'
                   f'<td>{r["gazeHotspotCenter"][0]:.0f}, {r["gazeHotspotCenter"][1]:.0f}</td>'
                   f'<td>{r["centerDistancePt"]:.0f} pt</td><td>{r["hoverWithinHomeR50"]*100:.1f}%</td>'
                   f'<td>{r["gazeWithinHomeR50"]*100:.1f}%</td></tr>'
                   for task, name in [('A5', '新闻长文'), ('A6', '图文流'), ('A7', '短视频流')]
                   for r in [reading[task]])
    b2 = [row for row in atlas['table'] if row['group'] == 'B2 单选']
    b3 = atlas['b3TrialSummary']
    assert len(b2) == len(b3) == 2
    extra = '''<style>
    .report-nav{display:flex;gap:14px;flex-wrap:wrap;margin:22px 0}.panel{padding:28px;margin:22px 0;background:white;border:1px solid #dde6ee;border-radius:18px;box-shadow:0 14px 32px #1c33540a}
    .strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}.strip div{background:#edf5f7;border-radius:12px;padding:16px}.strip strong{display:block;font-size:26px;line-height:1.2;color:#116b74}
    figure{margin:22px 0}figure img{width:100%;border:1px solid #dde6ee}figcaption{font-size:13px;color:#53647a;margin-top:7px}
    .table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px;white-space:nowrap}th,td{padding:9px 10px;border-bottom:1px solid #e0e8ee;text-align:right}th:first-child{text-align:left}thead{background:#edf5f7}
    .caution{padding:16px 19px;border-left:4px solid #d89c38;background:#fff7e9;border-radius:8px}.source-note{font-size:13px;color:#53647a;overflow-wrap:anywhere}
    </style>'''
    body = f'''<p><a href="../index.html">← Intentional Hover Study</a></p><h1>动作轨迹、阅读 Home 与视线</h1>
    <p class="lead">按实验版本综合运动证据与最新前摄探索。先看完整动作，再用有目标的点击检查视线是否足够准确；每组数据保留自己的分母。</p>
    <div class="report-nav"><a class="button" href="#gaze">看眼动结论</a><a class="button secondary" href="study-report.html">V2.1 十二章完整报告</a><a class="button secondary" href="../install.html">采集 App V2.4</a></div></header>
    {extra}
    <section class="panel"><h2>结论先行</h2><div class="strip">
    <div><strong>运动阶段</strong>目标接近、确认和多目标迁移值得连起来看；单一低速或停留仍会出现在自然阅读中。</div>
    <div><strong>Home 是位置</strong>阅读时 Pencil 的空间聚集随场景变化；它不由 500/800 ms 停留阈值定义。</div>
    <div><strong>眼动尚不能筛选</strong>本轮校准 P90 {calibration[0]['p90Pt']:.1f} pt，未通过 48 pt 小对象门槛；没有 B/C 眼动试次。</div></div>
    <p class="caption">同一参与者的不同会话：9/15 V2.1 两种右手姿势；9/16 V2.3 两种姿势的历史快照；9/16 后续 V2.4 只有右手拇指 A1–A7。版本、任务和顺序不同，不能合并计算识别准确率。</p></section>
    <section class="panel" id="motion"><h2>01 · 有目标动作：移向目标 → 确认 → 转移</h2>
    <p>旧两日运动汇总的 B2 悬停单选中，可配对的接近与确认阶段分别有 {b2[0]['paired']}、{b2[1]['paired']} 个事件，后段速度较低的数量也分别为 {b2[0]['speedLower']}、{b2[1]['speedLower']}。B3 多选的连续目标迁移可配对试次为 {b3[0]['pairedTrials']}/{b3[0]['trials']} 与 {b3[1]['pairedTrials']}/{b3[1]['trials']}；速度下降与 Z 原值下降在这些可配对试次均有出现。驻留是协议要求，不能把这些比例当成未受任务约束的意图识别率。</p>
    <figure><img src="combined/motion-sequence.png" alt="Touch、阅读 Home 与主动 Hover 的事件阶段对照"><figcaption>旧两日 V2.1/V2.3 阶段对照。不同事件锚点与可用段数分开展示；空缺处不补点。</figcaption></figure>
    <details><summary>查看 Z 原值变化速度</summary><figure><img loading="lazy" src="combined/motion-z-change.png" alt="各条件 Z 原值变化速度"><figcaption>Z 是 Pencil API 原值，不是毫米；Z 变化率与 XY pt/s 使用不同纵轴。</figcaption></figure></details>
    <p><a href="study-report.html">旧版十二章报告与 C 回顾性检验 →</a></p></section>
    <section class="panel" id="home"><h2>02 · 无指定指向目标的阅读：Pencil Home 与视线</h2>
    <p>V2.4 新会话的新闻、图文、视频各记录约 120 秒。三段手机内连续有效视线共 318.8/360.0 秒，Pencil 悬停共 200.8/360.0 秒。Home 是每段 Pencil 悬停的时间加权 R50 密集区，不依赖同一对象停留多久。</p>
    <div class="table-wrap"><table><thead><tr><th>阅读场景</th><th>Pencil Home (pt)</th><th>视线热点 (pt)</th><th>中心距</th><th>Pencil 在 Home</th><th>视线在 Home</th></tr></thead><tbody>{rows}</tbody></table></div>
    <figure><img src="combined/reading-home-gaze.png" alt="三种阅读场景的 Pencil Home 与视线热区"><figcaption>绿色圆为 Pencil Home R50，青色叉为粗校准视线热点。两行按各自有效观测时间归一化；距离仍受校准误差影响。</figcaption></figure>
    <p>记录坐标的视线热点都位于 Pencil Home 上方。三段只有各一例，Home 中心也随场景改变；不能将图中的距离视作真实眼手分离的精确估计。</p></section>
    <section class="panel" id="gaze"><h2>03 · 已知目标点击，是眼动过滤的正对照</h2>
    <p>18 次成功 A1 点击里，16 次在触屏前 300 ms 有手机内有效视线；其中 <strong>14/16</strong> 次视线没有进入目标中心 R50。试次中位的 Pencil 到目标距离为 11.8 pt，视线为 107.4 pt。若用“眼与笔落在同一小目标”作硬条件，当前估计会拒掉大量已知目标操作。</p>
    <figure><img src="combined/target-vs-reading.png" alt="A1 已知目标正对照及阅读 Home 的眼手比例"><figcaption>左图每个点是一次成功点击的触屏前窗口；右图是阅读的有效观测时间比例。两种任务不作为分类正负真值互换。</figcaption></figure>
    <p class="caution"><strong>目前不能报告 intentional hover 眼动准确率。</strong>一次校准虽记录 4 个独立验证点全覆盖，但 P90 为 {calibration[0]['p90Pt']:.1f} pt，质量标签 COARSE_ONLY；新会话只做到 A1–A7，没有 B1–B4 主动悬停或 C1–C3 同场景条件。视线缺失或校准失败应拒判，不等于用户没看目标。</p>
    <h3>下一步的证据门槛</h3><p>同一姿势先重复校准与阅读后复测；小对象试运行须达到协议的 P90 ≤24 pt、有效帧 ≥70%。若始终不达标，先分析较大内容区域或改用专用眼动仪。之后补 B2/B3、C3 的主动与自然对照，冻结时间窗，再评估 Pencil-only 与 Pencil+gaze 的召回、误触候选及拒判。</p></section>
    <footer class="source-note">原始 CSV 与逐点眼动未公开。9/15 V2.1 来源 SHA-256 {LEGACY_SHA}；9/16 V2.3 历史快照 SHA-256 {V23_PREFIX_SHA}；9/16 V2.4 追加后文件 SHA-256 {V24_SHA}。仅一位参与者，任务指令不是心理意图真值。<a href="../data-availability.html">数据与复现边界</a> · <a href="https://github.com/purryc/Intentional-Hover-Study/blob/main/qa/analyze_gaze_home_latest.py">分析源码</a></footer>'''
    return page('综合研究报告 · Intentional Hover Study', body)


def build(legacy_source, current_source, legacy_analysis, atlas_analysis, gaze_analysis):
    assert digest(legacy_source) == LEGACY_SHA
    assert prefix_digest(current_source, V23_PREFIX_BYTES) == V23_PREFIX_SHA
    assert digest(current_source) == V24_SHA
    atlas = json.loads((atlas_analysis / 'summary.json').read_text())
    gaze = json.loads((gaze_analysis / 'metrics.json').read_text())
    assert [item['sha256'] for item in atlas['inputs']] == [LEGACY_SHA, V23_PREFIX_SHA]
    assert gaze['sha256'] == V24_SHA and gaze['metadataParseErrors'] == 0
    build_legacy_site(legacy_analysis, legacy_source)
    site, report = ROOT/'site', ROOT/'site/report'
    assets = report/'combined'
    assets.mkdir(exist_ok=True)
    for source, output in FIGURES.items():
        root = gaze_analysis if source in ('reading-home-gaze.png', 'target-vs-reading.png') else atlas_analysis
        shutil.copyfile(root/source, assets/output)
    (report/'combined.html').write_text(combined_page(atlas, gaze))
    replace_once(site/'index.html', 'href="report/study-report.html">阅读完整研究报告', 'href="report/combined.html">阅读综合报告')
    replace_once(site/'index.html', '<div class="metric">V2.2</div><h3>当前采集协议</h3>',
                 '<div class="metric">V2.4</div><h3>当前采集协议</h3>')
    replace_once(site/'index.html', '<h2>这轮数据告诉我们什么</h2>',
                 '<p><a href="report/study-report.html">查看旧版 V2.1 十二章完整报告</a></p>\n<h2>这轮数据告诉我们什么</h2>')
    replace_once(site/'index.html', '<h2>在浏览器中重建自己的轨迹</h2>',
                 '<h2>新增：阅读视线的正对照</h2><p>三段阅读里，前摄估计视线与 Pencil Home 在记录坐标上分离；但校准 P90 为 211.9 pt，成功点击的 A1 目标也常被视线估计错过。当前不能把眼手同目标当作 intentional hover 的硬条件。<a href="report/combined.html#gaze">看完整证据 →</a></p>\n<h2>在浏览器中重建自己的轨迹</h2>')
    replace_once(site/'install.html', 'V2.2 · 原生 SwiftUI + UIKit · Xcode 源码安装',
                 'V2.4 · 原生 SwiftUI + UIKit · Xcode 源码安装')
    replace_once(site/'install.html', '<h2>任务与当前逻辑</h2>',
                 '<p>可选前摄视线默认关闭；开启后先进行 9 点校准与 4 点独立验证。视线仅作离线研究，不改变任务成功判断；低质量校准不得用于小目标同对象判定。</p>\n<h2>任务与当前逻辑</h2>')
    replace_once(site/'data-availability.html', '<h2>可以公开读取的内容</h2>',
                 '<h2>可以公开读取的内容</h2><p><a href="report/combined.html">综合研究报告</a>新增 V2.1/V2.3 运动对照及 V2.4 眼动质量检查，只有汇总图和描述，没有逐点视线、试次 ID 或脸部视频。</p>')
    replace_once(site/'data-availability.html', '<h2>使用自己的数据</h2>',
                 f'<p>9/16 追加 V2.4 后的本地 CSV 来源 SHA-256：<code>{V24_SHA}</code>。旧 V2.3 汇总使用追加前的历史前缀：<code>{V23_PREFIX_SHA}</code>。两个快照分开解释。</p>\n<h2>使用自己的数据</h2>')
    replace_once(report/'study-report.html', '<main><p><a href="../index.html">← Intentional Hover Study</a></p>',
                 '<main><p><a href="../index.html">← Intentional Hover Study</a> · <a href="combined.html">查看综合更新（含眼动）</a></p>')
    manifest_path = site/'publication-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest.update(appSourceRevision='HOVER_INTENT_V2_4',
                    combinedReportSourceSha256=[LEGACY_SHA, V23_PREFIX_SHA, V24_SHA],
                    combinedReportImages=len(FIGURES))
    manifest['files'] = {str(path.relative_to(site)): {'sha256': digest(path), 'bytes': path.stat().st_size}
                         for path in sorted(site.rglob('*')) if path.is_file() and path != manifest_path}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(f'Built V2.4 public update: {len(manifest["files"])} files, {len(FIGURES)} curated new figures, no raw CSV')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-source', type=Path, required=True)
    parser.add_argument('--current-source', type=Path, required=True)
    parser.add_argument('--legacy-analysis', type=Path, required=True)
    parser.add_argument('--atlas-analysis', type=Path, required=True)
    parser.add_argument('--gaze-analysis', type=Path, required=True)
    args = parser.parse_args()
    build(args.legacy_source, args.current_source, args.legacy_analysis, args.atlas_analysis, args.gaze_analysis)
