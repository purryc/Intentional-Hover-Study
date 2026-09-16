"""Consolidate immutable derived results; never recalculate from decimated replay states."""
import argparse
import hashlib
import html
import json
import re
import struct
from pathlib import Path

EXPECTED_SHA = '1c2eff5549ea4bafb76b2d7e683e31ef5db07187161ffe2bda50f25859940b89'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def section(text, heading):
    match = re.search(r'^## ' + re.escape(heading) + r'\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    if not match:
        raise ValueError('Missing report section: ' + heading)
    return match.group(1).strip()


def inline(s):
    s = html.escape(s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', s)


def render(markdown):
    body, nav = [], []
    table, listing, code = False, False, False
    for line in markdown.splitlines():
        if line.startswith('```'):
            if code: body.append('</code></pre>')
            else: body.append('<pre><code>')
            code = not code
            continue
        if code:
            body.append(html.escape(line) + '\n'); continue
        if line.startswith('|'):
            if re.fullmatch(r'[\s|:\-]+', line): continue
            if not table: body.append('<div class="table-wrap"><table>'); table = True
            cells = line.strip('|').split('|')
            body.append('<tr>' + ''.join('<td>' + inline(c.strip()) + '</td>' for c in cells) + '</tr>')
            continue
        if table: body.append('</table></div>'); table = False
        item = re.match(r'^(?:- |\d+\. )(.*)', line)
        if item:
            if not listing: body.append('<ul>'); listing = True
            body.append('<li>' + inline(item[1]) + '</li>'); continue
        if listing: body.append('</ul>'); listing = False
        image = re.match(r'^!\[([^\]]*)\]\(([^)]+)\)$', line)
        if image:
            body.append('<figure><a href="' + html.escape(image[2]) + '"><img loading="lazy" src="' + html.escape(image[2]) + '" alt="' + html.escape(image[1]) + '"></a><figcaption>' + html.escape(image[1]) + '</figcaption></figure>'); continue
        heading = re.match(r'^(#{1,6})\s+(.*)', line)
        if heading:
            n, label = len(heading[1]), heading[2]
            identifier = 'section-' + str(len(nav) + 1) if n == 2 else ''
            if n == 2: nav.append((identifier, label))
            body.append(f'<h{n} id="{identifier}">{inline(label)}</h{n}>'); continue
        if line.strip(): body.append('<p>' + inline(line) + '</p>')
    if table: body.append('</table></div>')
    if listing: body.append('</ul>')
    links = ''.join(f'<a href="#{i}">{html.escape(label)}</a>' for i, label in nav)
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Hover Intent Study · 统一研究报告</title><style>
:root{color-scheme:light;--ink:#253448;--blue:#1664af}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f2f5f8;color:var(--ink);font:16px/1.8 system-ui,-apple-system,sans-serif}.layout{display:grid;grid-template-columns:225px minmax(0,1180px);max-width:1460px;margin:auto;gap:32px;padding:28px}nav{position:sticky;top:24px;height:calc(100vh - 48px);overflow:auto;font-size:13px}nav strong{display:block;margin:0 8px 16px}nav a{display:block;padding:7px 9px;border-radius:6px;color:#42536a;text-decoration:none}nav a:hover{background:#e0eaf5}main{background:white;padding:40px;border-radius:16px;box-shadow:0 2px 14px #142b4b08;min-width:0}h1{font-size:34px;line-height:1.3;margin:0 0 24px}h2{font-size:25px;border-top:1px solid #dce4ed;padding-top:35px;margin-top:46px;scroll-margin-top:20px}h3{font-size:19px;margin-top:30px}a{color:var(--blue)}p,li{overflow-wrap:anywhere}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px;margin:16px 0}td{padding:10px;border:1px solid #d9e1e9}tr:first-child{background:#edf3fa;font-weight:650}figure{margin:28px 0}img{width:100%;height:auto;border:1px solid #e1e7ee;border-radius:10px}figcaption{font-size:13px;color:#6a7b8e;margin-top:7px}code,pre{font-size:12px;background:#eef2f7}pre{padding:18px;overflow:auto}.badge{display:inline-block;background:#eaf3fd;color:#185b99;border-radius:6px;padding:4px 12px;font-size:12px;margin-bottom:20px}.actions{font-size:13px;display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px}@media(max-width:950px){.layout{display:block;padding:12px}nav{position:relative;top:0;height:auto;margin-bottom:20px;display:flex;flex-wrap:wrap}nav strong{width:100%}main{padding:22px}h1{font-size:27px}}@media print{nav,.actions{display:none}.layout{display:block;padding:0}main{padding:0;box-shadow:none}body{background:white}h2{break-after:avoid}figure,tr{break-inside:avoid}a{color:inherit;text-decoration:none}}
</style></head><body><div class="layout"><nav><strong>统一研究报告 · 目录</strong>''' + links + '''</nav><main><div class="badge">P01 · 右手拇指 / 右手食指 · V2.1 实测</div><div class="actions"><a href="study-report.md">报告 Markdown</a><a href="study-report.json">来源与结果 JSON</a><a href="replay-v2.html">手机 3D 轨迹回放</a><a href="../../../../qa/v2-2-verification.md">新版验收记录（本地文件）</a><button onclick="window.print()">打印 / 保存 PDF</button></div>''' + ''.join(body) + '</main></div></body></html>'


def build(out, source):
    digest = sha(source)
    if digest != EXPECTED_SHA: raise ValueError('Source CSV differs from reviewed data')
    texts = {name: (out / name).read_text() for name in ['report.md', 'motion-study.md', 'behavior-overview.md', 'home-position.md']}
    r, b, m, h = [texts[name] for name in ['report.md', 'behavior-overview.md', 'motion-study.md', 'home-position.md']]
    data = {name: json.loads((out / name).read_text()) for name in ['quality.json', 'behavior-overview.json', 'motion-study.json', 'home-position.json', 'intent_exploration.json']}
    for name in ['quality.json', 'behavior-overview.json', 'motion-study.json', 'home-position.json']:
        assert data[name]['sha256'] == digest, name
    root = Path(__file__).resolve().parents[1]
    status_path = root / 'qa/v2-3-verification.json'
    status = json.loads(status_path.read_text()) if status_path.exists() else {'status': 'IN_PROGRESS', 'physicalPencilValidation': 'NOT_RUN'}
    sections = []
    def add(title, content): sections.append('## ' + title + '\n\n' + content.strip())
    intro = '''# Hover Intent Study：行动轨迹与意图特征统一报告

**本轮最清楚的区别是动作阶段和路径结构：B1 两阶段菜单操作、B3 多对象“移动→驻留→再移动”、B4 大面积闭合空中路径。减速、低速或500ms停留单独区分 intentional hover 的能力有限。**

- 两轮都是右手：第一轮绑拇指，第二轮托握＋食指；仅一位参与者，先后顺序与练习效应未分离。
- 静态两特征模型在 C3 回顾性留组检验中识别23/27主动窗，却把20/69自然候选误报为主动；平衡准确率78.1%，目前不能作为可靠自动唤出规则。
- B4 原协议成功7/12；独立几何扫描在8/12次圈选尝试发现闭合候选，A基线103次尝试中为0，但B1和C3自然各有1次，圈形并不等于意图。
- 6个姿势×场景位置模型只有3个热点在后半段复现。固定50pt home过滤没有减少C3自然误报，并误排1个主动窗；应保留为位置参考，当前不部署硬过滤。
- 新采集协议 V2.3 已将C3改为配图里的蝴蝶，并简化界面；下文实测结论全部来自旧 V2.1，不把新版实现当成新增实验结果。

本报告汇总此前两轮比较、静态意图区分、运动阶段、多选、A/B→C检验与home位置分析；完整原CSV、失败尝试及原菜单判定保留。图点击可查看原始分辨率。'''
    add('1. 参与者、采集概况与完整任务结果', section(r, '采集概况') + '\n\n### 14类任务结果\n\n' + section(r, '任务结果') + '\n\n### 同几何姿势配对\n\n' + section(r, '相同几何配对') + '\n\n### 用户覆核\n\n' + section(r, '用户覆核追溯'))
    add('2. A1–A7 手机 baseline 与阅读场景', section(b, '2. A1–A7 的基线是什么') + '\n\n### 120秒自然阅读与场景操作\n\n' + section(r, '自然阅读：候选与停留') + '\n\n### 本轮场景与姿势变化\n\n' + section(r, '这轮数据中的主要规律'))
    add('3. B1/B2：Hover pointing、菜单后点击', section(b, '1. 四类主动行为与基线的关系') + '\n\n### 匹配几何与目标停留\n\n' + section(b, '3. 小目标驻留：和 A1 相比有区别，但大部分是协议决定'))
    add('4. B3：Hover multiselect 的完整过程', section(m, 'Hover Multiselect（B3）'))
    add('5. B4：空中圈选的成功、轨迹与闭合候选', section(r, 'B4 空中圈选') + '\n\n### 全任务独立闭合扫描\n\n' + section(b, '6. 闭合路径是否在 A 中也出现'))
    add('6. 速度、加速、减速与接近制动', section(m, '加速与减速怎么看') + '\n\n### 同几何单目标示例\n\n' + section(m, '单目标：拖动与 Hover 指向') + '\n\n### 所有主动任务的阶段比较\n\n' + section(b, '5. 接近→制动能否成为组合特征') + '\n\n### 原始二维导数与姿势分布\n\n' + section(r, '行动轨迹与运动'))
    add('7. Intentional hover：静态线索与两种检验', section(b, '4. 静态 Hover 与阅读：哪些特征真正重叠') + '\n\n### 较早的C3跨姿势探索\n\n' + section(r, 'Intentional Hover：轨迹能区分意图吗？') + '\n\n**上述跨姿势模型使用一轮C3拟合、另一轮C3检查；下节A/B模型只用A/B拟合、C3检查。训练来源不同，准确率不能混用，也都缺独立参与者验证。**')
    add('8. C1–C3：混淆验证的实际覆盖与结果', section(b, '7. C1–C3 的角色：你的理解成立，但覆盖有限') + '\n\n### 冻结A/B后检验C3\n\n' + section(b, '8. 冻结 A/B 特征后，在 C3 上实际检验'))
    home_intro = h.split('## 1.')[0].split('\n', 2)[-1].strip()
    home_parts = [home_intro]
    for heading in re.findall(r'^## (.*)$', h, re.M):
        if heading.startswith('6.'): continue
        home_parts.append('### ' + heading + '\n\n' + section(h, heading))
    add('9. Home position：能检测到什么、多久可用', '\n\n'.join(home_parts))
    add('10. 可保留的行为特征与下一轮验证', section(b, '9. 最值得保留的行为特征') + '''

### 建议的分析边界

- 在线候选只用判定时已经收到的数据，接触或菜单出现后的动作用于完成分析，不能作为出现前意图预测的输入。
- 静态指向/驻留与移动型圈选分开建模；B3 的对象转移序列需要专项困难负例，不能被C3阅读窗口的准确率代替。
- 自然候选标签来自指令，若要测真实误触，需要独立人工意图标注或用户确认；本轮没有真实误触地面真值。
- 新一轮先练习 C 的零触屏条件，再固定特征与阈值，并用新参与者检验。失败重试保留全量尝试，用首次成功率和每题重试数避免“收齐有效数据=全部容易成功”的解释。''')
    status_table = '| 检查 | 实际状态 |\n| --- | --- |\n' + '\n'.join('| ' + k + ' | ' + str(v) + ' |' for k, v in status.items() if isinstance(v, (str, int)))
    add('11. 本次采集App修订：V2.3（与实测结果分开）', '''
A/C 用于有效baseline与混淆验证，B用于成功率和行为轨迹，因此采用不同推进策略。

| 修订 | 新行为 |
| --- | --- |
| A1–A7 / C1–C3 | 失败保留记录，1.2秒后重试同一计划题；不换条件/几何，不增加原定进度，成功后进入下一题 |
| 重做当前次 | 保留当前尝试并重试原计划题；不增加计划进度。后台后“开始实验”继续 |
| B1–B4 | 默认各12次（原各6次），B配平套数可独立配置；成功/失败均推进，所有尝试保留 |
| 默认总量 | 156次短任务＋3段120秒阅读，姿势/任务仍任选 |
| C1 | 24/36/48pt小圆，距离220pt，两方向两条件配平 |
| C2 | 36×36pt标记，80×80pt终点窗口；中心起点与标记分离120pt，滚动需从标记接触开始 |
| C3 | 新闻正文前配图、图文首卡图片和视频画面内固定配图，均指向同一授权素材里的蝴蝶；只框蝴蝶周围48×48pt，不指向收藏星标。新闻/图文随页面滚动；视频继续播放，配图本身固定，不作为动态视频物体跟踪 |
| C3自然候选 | 同一指定小对象静默候选，反馈保持自然；不再把整个视频或卡片作为目标 |
| 采集界面 | 只保留“开始实验”“重做当前次”“导出 CSV”三个任务操作；姿势、任务及参数放配置区，旧协议开发/恢复路径保留 |
| 旧数据/旧会话 | 不改写；无revision配置保持V2.1，缺少contentTargets字段保持V2.2，新会话默认V2.3 |

原CSV仍是旧目标与旧推进规则。新版缩小对象会改变候选机会，不能把新旧每分钟候选率不分协议直接比较。B1原菜单覆核只是本轮分析注释，新App仍要求完成屏幕上明确提示的菜单项。

### 本次验证状态

''' + status_table)
    add('12. 单位、数据质量、可追溯方法与交付', '''
**pt 是界面坐标单位（point，点）。** 手机仿真宽390pt、高830pt；“RMS 4–5pt”表示500ms窗口内笔尖相对该窗口自身中心的二维散布，约为手机宽度的1%–1.3%，不是离目标中心4–5pt，也不是毫米或纯生理抖动。XY速度用pt/s，有符号速度变化率用pt/s²。Z保留API原始值，3D回放的高度只是显示比例，不能合成物理三维加速度。

''' + section(r, '数据质量与解释边界') + '''

### 数据完整性与覆盖

原CSV266,246行、56列：165,474条SAMPLE与100,772条EVENT；无残缺CSV行。本文两轮接收150,905个样本，过滤后回放保留150,040个手机内点；排除699个手机外点和166个试次边界外点。两轮未发现手指/模拟/污染输入；全文件旧协议中有手指样本，未混入本次分析。

146,265条合法连续运动边保留；其中2条短于1ms的边从主要导数统计排除，原坐标不删除。超100ms、输入来源切换、结束/重新开始、范围外和污染处断线；不平滑坐标、不补点。曲线仅在同段显示80ms中值趋势。前接近300ms需至少200ms覆盖，驻留500ms需450ms和12个点。接触前600ms覆盖按实际连续有效边计算，不能用窗口最早/最晚时间冒充完整覆盖，逐试次指标可查。

两轮各持续超过15分钟是观察到的会话时长；本报告没有完成新版15分钟硬件接收/落盘专项比对。悬停回调间隔约16.67ms、接触约4ms，不能据此宣称硬件频率或全时段无采样缺口。完整SCROLL/VIDEO事件用于统计，回放场景状态预览最高20Hz，不能从预览数量重算滚动次数。

### 单一入口与详细证据

[手机3D回放](replay-v2.html) · [逐试次数据](trial_metrics.csv) · [原始运动边](motion_metrics.csv) · [有符号阶段导数](motion_phases.csv) · [多选逐对象指标](multiselect_metrics.csv)

[静态窗口和C检验分数](behavior_windows.csv) · [目标内停留指标](target_hover_features.csv) · [阅读场景指标](reading_metrics.csv) · [home候选窗](home_candidates.csv) · [home过滤逐窗](home_filter_windows.csv) · [菜单覆核](analysis-annotations.json)

[原两轮比较报告](report.html) · [加减速/多选细图](motion-study.html) · [A/B/C详细报告](behavior-overview.html) · [home详细报告](home-position.html) · [来源与结果快照](study-report.json)

来源文件：HoverIntent_2026-09-15 2.csv；328,198,639字节。SHA256：`''' + digest + '''`。本报告生成前复核原文件哈希与各分析快照一致，未修改原CSV。复现命令：

```sh
python3 qa/build_study_report.py --source "data/HoverIntent_2026-09-15 2.csv" --output analysis/trajectory_2026-09-15/hands_run2
```

本报告汇编脚本仅依赖Python标准库。原分析脚本与测试保留在qa/；所有图和窗口证据保留，没有将算法闭合边或统计位置中心伪装成实测点。''')
    markdown = (intro + '\n\n' + '\n\n'.join(sections) + '\n').replace('两轮均完成所有 14 类任务', '两轮均尝试全部 14 类任务')
    # Strip links that would go outside the HTTP root; native file links remain in the final response.
    page = render(markdown).replace('<a href="../../../../qa/v2-2-verification.md">新版验收记录（本地文件）</a>', '')
    assets = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', markdown)
    for asset in assets:
        assert (out / asset).is_file(), asset
        with (out / asset).open('rb') as f:
            header = f.read(24)
        assert header[:8] == b'\x89PNG\r\n\x1a\n', asset
        width, height = struct.unpack('>II', header[16:24])
        page = page.replace('src="' + html.escape(asset) + '"', 'src="' + html.escape(asset) + f'" width="{width}" height="{height}"')
    snapshot = {'source': str(source), 'sha256': digest, 'bytes': source.stat().st_size, 'participants': 1, 'hand': 'RIGHT', 'runs': ['THUMB', 'CRADLE_INDEX'], 'measuredProtocol': 'HOVER_INTENT_V2_1', 'appRevision': 'HOVER_INTENT_V2_3', 'b1OverrideScope': '6 WRONG_MENU_ITEM records after MENU_OPEN with actual B; raw retained', 'sectionCount': len(sections), 'assets': sorted(set(assets)), 'evidenceFiles': {name: sha(out / name) for name in list(texts) + list(data)}, 'results': data, 'appVerification': status}
    (out / 'study-report.md').write_text(markdown)
    (out / 'study-report.html').write_text(page)
    (out / 'study-report.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
    # Only add a navigation link; original report bodies remain intact.
    for name in texts:
        html_path = out / name.replace('.md', '.html')
        old = html_path.read_text()
        link = '<p data-unified-report><a href="study-report.html">打开统一研究报告：全部结果、方法与新版采集修改</a></p>'
        if 'data-unified-report' not in old:
            end = old.index('</style>') + len('</style>')
            html_path.write_text(old[:end] + link + old[end:])
    print(json.dumps({'sections': len(sections), 'images': len(assets), 'sha256': digest, 'htmlBytes': (out / 'study-report.html').stat().st_size}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.output, args.source)
