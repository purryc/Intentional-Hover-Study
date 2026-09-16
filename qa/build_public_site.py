#!/usr/bin/env python3
"""Publish an explicit report snapshot; raw capture data never enters the site."""
import argparse
import hashlib
import html
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = 'https://github.com/purryc/Intentional-Hover-Study'
EXPECTED_SHA = '1c2eff5549ea4bafb76b2d7e683e31ef5db07187161ffe2bda50f25859940b89'
UUID = re.compile(r'\b[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\b')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def public_value(value):
    if isinstance(value, dict):
        return {public_value(k): public_value(v) for k, v in value.items()
                if k not in ('trialID', 'trainIDs', 'selectedSessions', 'labels',
                             'deviceID', 'deviceIdentifier', 'signatureExamples')}
    if isinstance(value, list):
        return [public_value(v) for v in value]
    if isinstance(value, str):
        if value.startswith('/Users/'):
            return '[local path withheld]'
        return UUID.sub(lambda m: 'id-' + hashlib.sha256(m[0].encode()).hexdigest()[:10], value)
    return value


def page(title, body):
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#f4f6fa;color:#233349;font:16px/1.8 system-ui,-apple-system,sans-serif}}main{{max-width:1040px;margin:auto;padding:56px 28px 80px}}header{{margin-bottom:44px}}.eyebrow{{color:#2866b0;font-size:13px;font-weight:700;letter-spacing:.12em}}h1{{font-size:clamp(34px,6vw,60px);line-height:1.15;letter-spacing:-.035em;margin:16px 0 24px}}h2{{font-size:26px;margin-top:48px}}h3{{margin-top:0}}p{{max-width:830px}}.lead{{font-size:20px;color:#53647a}}a{{color:#175fab}}.actions{{display:flex;gap:12px;flex-wrap:wrap;margin-top:26px}}.button{{display:inline-block;padding:12px 20px;background:#175fab;color:white;border-radius:9px;text-decoration:none;font-weight:650}}.button.secondary{{background:white;color:#175fab;border:1px solid #d1dcea}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:18px}}.card{{padding:24px;background:white;border:1px solid #e0e6ef;border-radius:14px}}.metric{{font-size:34px;font-weight:750;color:#175fab}}.caption,footer{{font-size:13px;color:#637389}}img{{max-width:100%;height:auto;border-radius:10px;background:white}}code{{background:#e7edf6;padding:3px 6px;font-size:13px}}li{{margin:8px 0}}footer{{margin-top:50px;border-top:1px solid #d7e0eb;padding-top:20px}}@media(max-width:600px){{main{{padding:30px 18px}}.lead{{font-size:18px}}}}
</style></head><body><main><header><div class="eyebrow">INTENTIONAL HOVER STUDY</div>{body}</main></body></html>'''


def build(analysis, source):
    analysis, source = Path(analysis), Path(source)
    assert digest(source) == EXPECTED_SHA, 'The reviewed source data changed'
    snapshot = json.loads((analysis / 'study-report.json').read_text())
    assert snapshot['sha256'] == EXPECTED_SHA
    assert snapshot['sectionCount'] == 12 and len(snapshot['assets']) == 17
    for name, expected in snapshot['evidenceFiles'].items():
        assert digest(analysis / name) == expected, 'Evidence changed: ' + name
    site, report = ROOT / 'site', ROOT / 'site/report'
    report.mkdir(parents=True, exist_ok=True)
    for name in snapshot['assets']:
        assert Path(name).name == name and name.endswith('.png')
        shutil.copyfile(analysis / name, report / name)
    public = {k: public_value(snapshot[k]) for k in
              ('sha256', 'bytes', 'participants', 'hand', 'runs', 'measuredProtocol',
               'appRevision', 'b1OverrideScope', 'sectionCount', 'assets', 'appVerification')}
    public['edition'] = 'PUBLIC_REPORT_AGGREGATES_NO_RAW_SAMPLES'
    public['source'] = Path(snapshot['source']).name
    public['dataAvailability'] = '../data-availability.html'
    results = snapshot['results']
    selections = {
        'quality.json': ('fields', 'rows', 'comparison', 'replay'),
        'behavior-overview.json': ('windows', 'motion', 'targetHover', 'matchedSingleTargets',
                                  'loopScan', 'model', 'c3', 'c3Scenes', 'c2PositiveWindowCheck', 'validationStatus'),
        'motion-study.json': ('summaries', 'signedMotionRows', 'method'),
        'home-position.json': ('method', 'sceneModels', 'crossSceneDistances', 'aSameReadingFuture',
                              'c3Base', 'c3Filter', 'c3Scenes', 'bTransferRisk', 'status', 'cValidation'),
        'intent_exploration.json': ('method', 'limitations', 'distributions', 'cross_run', 'intentional_moving_hover'),
    }
    public['results'] = {name: public_value({k: results[name][k] for k in keys})
                         for name, keys in selections.items()}
    (report / 'study-report.json').write_text(json.dumps(public, ensure_ascii=False, indent=2) + '\n')
    allowed = set(snapshot['assets']) | {'study-report.html', 'study-report.md', 'study-report.json'}
    chapters = {'report.html': '#section-1', 'motion-study.html': '#section-6',
                'behavior-overview.html': '#section-8', 'home-position.html': '#section-9'}

    def link(target):
        if target in allowed or target.startswith(('#', 'https://', 'http://')):
            return target
        if target == 'replay-v2.html':
            return '../replay/replay-v2.html'
        if target in chapters:
            return chapters[target]
        return '../data-availability.html#local-files'

    note = '公开版保留12章、17张分析图与汇总参数；原始CSV、逐点指标及完整轨迹只保存在本地。3D工具需自行导入CSV。'
    text = (analysis / 'study-report.html').read_text()
    text = re.sub(r'\b(href|src)="([^"]+)"', lambda m: f'{m[1]}="{link(m[2])}"', text)
    text = text.replace('<main>', '<main><p><a href="../index.html">← Intentional Hover Study</a></p>'
                        f'<p style="padding:14px;background:#eef4fa;font-size:13px">{note} '
                        '<a href="../data-availability.html">数据与复现说明</a></p>', 1)
    (report / 'study-report.html').write_text(text)
    markdown = (analysis / 'study-report.md').read_text()
    markdown = re.sub(r'(!?\[[^\]]*\])\(([^)]+)\)', lambda m: m[1] + '(' + link(m[2]) + ')', markdown)
    (report / 'study-report.md').write_text('> ' + note + '\n\n' + markdown)
    (site / 'index.html').write_text(page('Intentional Hover Study', '''
<h1>Intentional<br>Hover Study</h1><p class="lead">手机操作仿真中的悬停意图研究。原生 iPad 采集应用、真实阅读场景，以及从行动轨迹寻找意图线索的探索性分析。</p>
<div class="actions"><a class="button" href="report/study-report.html">阅读完整研究报告</a><a class="button secondary" href="install.html">安装 iPad 应用</a><a class="button secondary" href="https://github.com/purryc/Intentional-Hover-Study">GitHub 源码</a></div></header>
<div class="grid"><div class="card"><div class="metric">14</div><h3>任务类型</h3><p>7 类自然基线、4 类主动 Hover、3 类混淆任务。姿势与任务可按需选择。</p></div><div class="card"><div class="metric">12 + 17</div><h3>章节与分析图</h3><p>指向、菜单后点击、多选、圈选、加减速、阅读候选和 home position。</p></div><div class="card"><div class="metric">V2.2</div><h3>当前采集协议</h3><p>156 次短任务＋3 段自然阅读。A/C 失败重试同题，B 各 12 次记录成功率。</p></div></div>
<h2>这轮数据告诉我们什么</h2><p>动作阶段和路径结构最清楚：菜单操作的两阶段、多对象间的移动与驻留、大面积闭合空中路径。低速、减速或停留 500ms 单独区分 intentional hover 的能力有限。</p>
<div class="grid"><div class="card"><h3>静态线索仍有误报</h3><p>C3 回顾性检验识别 23/27 主动窗，却误报 20/69 自然候选。平衡准确率 78.1%。</p></div><div class="card"><h3>位置热点需要重学</h3><p>6 个姿势×场景热点中仅 3 个后半段复现。固定 home 过滤本轮没有改善 C3。</p></div></div>
<p class="caption">一位参与者，两轮均右手：先拇指、后食指；先后顺序及练习效应未分离。实测来自 V2.1，C 曾用于探索，结果不能视为独立验证。Z 为 API 原值，不能解释为毫米。</p>
<a href="report/study-report.html#section-4"><img src="report/multiselect_paths.png" width="2560" height="1760" alt="Hover 多选的完整动作路径"></a>
<h2>在浏览器中重建自己的轨迹</h2><p>Three.js 回放保留手机局部区域的 Pencil 悬停与接触，显示目标、选择、菜单、阅读状态与圈线。导入文件在浏览器内处理；公开页初始为空。</p><div class="actions"><a class="button secondary" href="replay/replay-v2.html">打开 3D 回放工具</a><a href="data-availability.html">数据可用性与复现</a></div>
<footer>应用源码已构建、测试并安装到目标 iPad；新版真实 Pencil 逐类试做、15 分钟硬件专项和 AirDrop 仍待验收。<br>场景视频与配图：Big Buck Bunny © Blender Foundation，CC BY 3.0。Three.js r180：MIT。<a href="https://github.com/purryc/Intentional-Hover-Study/blob/main/docs/media-sources.md">素材来源</a></footer>'''))
    (site / 'install.html').write_text(page('安装应用 · Intentional Hover Study', '''
<p><a href="index.html">← 返回首页</a></p><h1>在 iPad 上开始采集</h1><p class="lead">V2.2 · 原生 SwiftUI + UIKit · Xcode 源码安装</p></header>
<ol><li><a href="https://github.com/purryc/Intentional-Hover-Study/archive/refs/heads/main.zip">下载源码 ZIP</a>，或克隆 GitHub 仓库。</li><li>打开 <code>src/HoverIntentStudy.xcodeproj</code>，选择 HoverIntentStudy scheme。</li><li>连接 12.9 英寸第六代 iPad Pro，解锁、信任 Mac 并启用开发者模式；准备第二代 Apple Pencil。</li><li>在 Xcode 的 Signing &amp; Capabilities 中选择自己的 Team，然后选择 iPad 点击 Run。</li><li>横屏全屏，收到实际 Pencil 悬停后选择参与者、姿势与任务，按手机上方的指令操作。</li></ol>
<p>模拟器自动使用模拟模式。正式数据与 SIMULATED 数据分目录保存；CSV 每日追加、最长 250ms 刷新，导出为独立快照。</p>
<h2>任务与当前逻辑</h2><p>A1–A4 为抽象目标点击、拖动、纵横滚动；A5–A7 为新闻长文、双列图文流和短视频流。B1 菜单后点击、B2 单选、B3 多选、B4 空中圈选；C1–C3 为同场景自然操作与零触屏悬停的混淆对照。</p><p>A/C 未成功会保留尝试并重新开始同一计划题；B 成败均推进，用于计算成功率。全部任务默认 156 次短任务＋3 段两分钟自然阅读。</p>
<div class="actions"><a class="button secondary" href="https://github.com/purryc/Intentional-Hover-Study/blob/main/README.md">详细安装与数据说明</a><a href="https://github.com/purryc/Intentional-Hover-Study/blob/main/qa/verification-public.md">实际验收状态</a></div>
<footer>应用发布为源码工程，使用个人签名安装。新版真机逐类 Pencil 操作与硬件可靠性专项仍待验收。媒体归属见仓库 docs/media-sources.md。</footer>'''))
    (site / 'data-availability.html').write_text(page('数据与复现 · Intentional Hover Study', '''
<p><a href="index.html">← 返回首页</a></p><h1>数据与复现</h1><p class="lead">公开报告提供汇总与图；原始采集文件保存在研究者本地。</p></header>
<h2>可以公开读取的内容</h2><p><a href="report/study-report.html">12 章完整报告</a>、17 张轨迹及统计图、<a href="report/study-report.md">Markdown</a>、<a href="report/study-report.json">汇总与模型参数 JSON</a>、协议、数据字典和分析源码。公开图包含本轮研究轨迹的可视化，JSON 没有原始点列。</p>
<h2 id="local-files">报告中的本地证据</h2><p>逐试次/逐窗口指标、原始运动边、菜单覆核明细、旧详细报告及完整 replay-data.json 保留在本地研究目录。公开报告中这些证据的链接统一指向本说明。旧详细报告的对应内容已整合到统一报告。</p>
<p>原 CSV：HoverIntent_2026-09-15 2.csv；328,198,639 字节；266,246 行 / 56 列。来源 SHA256：</p><p><code>1c2eff5549ea4bafb76b2d7e683e31ef5db07187161ffe2bda50f25859940b89</code></p>
<h2>使用自己的数据</h2><p><a href="replay/replay-v2.html">打开回放工具</a>，选择 V2.1 或 V2.2 CSV。文件通过浏览器 File API 读取和解析，不上传到服务器；可以导出本地分析 JSON 与运动 CSV。</p><p>轨迹限定手机 390×830pt 内的 Pencil；手指、污染、手机外、结束回调与超过 100ms 缺口断线。XY 速度与加速度使用实际时间差，Z 保持 API 原值，显示比例不代表毫米。</p>
<h2>重新运行完整分析</h2><p>需另行提供自己的原始 CSV，并安装 Python、numpy、pandas、matplotlib。研究分析脚本保留本轮会话选择，换数据时需要按实际会话选择调整。<a href="https://github.com/purryc/Intentional-Hover-Study/blob/main/docs/two-run-analysis-method.md">完整方法</a>与<a href="https://github.com/purryc/Intentional-Hover-Study/blob/main/docs/publishing.md">发布说明</a>在仓库中。</p>
<footer>本轮仅一位参与者，右手拇指后右手食指；实测协议 V2.1，应用后续修订为 V2.2。自然候选不等于真实误触；C 留组检验为回顾性分析。</footer>'''))
    replay = site / 'replay'
    replay.mkdir(exist_ok=True)
    template = (ROOT / 'qa/v2_replay.html').read_text().replace('__DATA__', json.dumps({'source': '导入自己的 CSV · 公开页未加载正式数据', 'trials': []}, ensure_ascii=False))
    template = template.replace('<a href="./replay.html">旧协议回放</a>', '<a href="../index.html">研究首页</a><a href="../report/study-report.html">统一报告</a>')
    template = template.replace('<main>', '<main><p>CSV 在浏览器内读取，不上传。公开页初始为空，请导入自己的 V2.1/V2.2 数据。</p>', 1)
    (replay / 'replay-v2.html').write_text(template)
    shutil.copyfile(ROOT / 'qa/v2_replay.js', replay / 'v2_replay.js')
    shutil.copytree(ROOT / 'qa/vendor', replay / 'vendor', dirs_exist_ok=True)
    shutil.copytree(ROOT / 'src/App/StudyMedia', replay / 'Resources', dirs_exist_ok=True)
    (site / '.nojekyll').touch()
    files = {str(p.relative_to(site)): {'sha256': digest(p), 'bytes': p.stat().st_size}
             for p in sorted(site.rglob('*')) if p.is_file() and p.name != 'publication-manifest.json'}
    (site / 'publication-manifest.json').write_text(json.dumps({'name': 'Intentional Hover Study',
        'reportSourceSha256': EXPECTED_SHA, 'rawCaptureIncluded': False,
        'reportChapters': 12, 'reportImages': 17, 'files': files}, ensure_ascii=False, indent=2) + '\n')
    print(f'Built public site: {len(files)} files; no raw capture included')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', required=True)
    parser.add_argument('--source', required=True)
    args = parser.parse_args()
    build(args.analysis, args.source)
