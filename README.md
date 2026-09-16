# Intentional Hover Study

手机操作仿真中的悬停意图研究：原生 iPad 采集应用、14 类任务、真实阅读场景与行动轨迹分析。

**[在线研究报告](https://purryc.github.io/Intentional-Hover-Study/report/study-report.html)** · **[安装应用](https://purryc.github.io/Intentional-Hover-Study/install.html)** · **[Three.js 回放工具](https://purryc.github.io/Intentional-Hover-Study/replay/replay-v2.html)**

报告包含 12 章和 17 张分析图：Hover 指向、菜单后点击、多选、空中圈选、加减速、A1–A7 baseline、C 混淆检验及 home position。实测是一位参与者的右手两种姿势，来自 V2.1；C 留组检验为回顾性分析。当前应用为 V2.2，真机已安装并启动，新版逐类 Pencil 试做和 15 分钟硬件专项仍待验收。

## 2026-09-15 V2.2 修订

A/C 失败后重试当前题，进度成功后推进；B 默认各12次。C 使用更小、围绕具体对象的命中区域。旧会话保留 V2.1；新配置及推进规则见 [协议](docs/protocol-v2.md)，验收见 [公开记录](qa/verification-public.md)。

## iPad 原型

用于采集 Pencil 绑在拇指旁、由笔尖点击／滑动的运动数据。采集界面始终显示中文任务、当前次数／本组总次数、后续剩余次数和操作阶段。

## V2 入口

默认显示14类任务选择：A自然基线7类、B主动Hover4类、C混淆任务3类。单选姿势、多选任务；默认156次短任务＋3段120秒阅读，B1–B4各12次。全部抽象操作使用几何目标。

- B1：停留500ms弹出菜单，再点击指定选项。
- B2/B3和C的HOVER条件：停留500ms自动选择，全程不点击。
- B4：起点稳定后在空中圈住蓝色目标，回到起点自动提交；中断后可在原超时内回起点重画。
- A5/A6/A7：新闻长文、双列图文信息流、六条实际竖屏视频；自然阅读，无答题。
- 实验开始前可修改完整配平重复轮数、时间、尺寸和圈选阈值。
- 模拟模式的“模拟完成一次”会演示短任务；阅读段则演示滚动/导航，仍按设定时间结束。

“旧协议 Test 0–4”保留V1入口；已存在的V1未完成会话优先恢复，结束后可切换V2。下面原Test说明只适用于旧协议。

协议见 [protocol-v2.md](docs/protocol-v2.md)，新字段与回放见 [data-dictionary-v2.md](docs/data-dictionary-v2.md)，媒体来源见 [media-sources.md](docs/media-sources.md)。V2回放入口为 `replay-v2.html`，支持直接导入V2 CSV；自带演示数据明确标记SIMULATED。

## 打开与安装

1. 打开 `src/HoverIntentStudy.xcodeproj`，选择 `HoverIntentStudy` scheme。
2. 用 USB 连接 **12.9 英寸第六代 iPad Pro**，解锁并信任 Mac，在 iPad 设置中启用开发者模式。
3. Xcode → Settings → Accounts 登录你的 Apple ID；在工程的 Signing & Capabilities 选择自己的 Team。无需把账号或签名身份写入源码。
4. 选择连接的 iPad，点击 Run。若提示未受信任，在 iPad 设置 → 通用 → VPN 与设备管理中信任开发者。
5. 使用第二代 Apple Pencil，横屏全屏运行。将 Pencil 靠近屏幕，左侧显示“已收到 Pencil 悬停”后开始。

模拟器会默认进入模拟模式。正式采集要求 `1366×1024 pt`、目标设备型号和实际 Pencil 悬停信号；其他型号／窗口仅用于模拟预览。

## 做一次实验

输入参与者编号，例如 `P01` → 选择 Test → 实验设置中核对参数 → 开始实验。Pencil 悬停在起点，按手机区域正上方的中文任务操作。目标处没有指向停留门槛。

- **任务是什么**：每次显示完整操作，例如“先悬空指准目标，再点击”。
- **还有几次**：例如“第 3 / 72 次 · 后续还有 69 次”，剩余数不包含当前这次。
- **暂停／继续**：当前未完成试次记中断；继续时显示“重做”，从起点开始，不额外推进原定进度。
- **失败／跳过**：保留原始样本，推进到下一个计划任务。
- **重做**：产生新 trialID，与旧试次关联，完成后继续原定顺序。
- **结束实验**：显示有效、失败、跳过和重做记录数量。有效数指原定试次的成功数，重做结果可在 CSV 单独分析。

TAP/HOVER 共 144 次混合计数，两组的几何与光标一致。可在开始前降低重复次数试跑；同组开始后配置锁定。

## 数据与导出

正式数据在应用 `Documents/Data/HoverIntent_YYYY-MM-DD.csv`；模拟数据在 `Documents/SimulatedData/SIMULATED_HoverIntent_YYYY-MM-DD.csv`，两者分开。

点击“导出今天的 CSV”，在系统分享界面选择 AirDrop 和 Mac。每次导出的是已刷新数据的独立快照，iPad 原文件继续保留和追加。历史文件也可以分享。也可从 Finder → iPad → 文件 → Hover Intent Study 取出 Documents 数据。

显示保存失败时，实验暂停，未确认批次保留在内存；按具体错误处理后点击“重试保存”，明确提示空间不足时先释放空间，成功后点击“继续”。不要在保存故障尚未解决时强制退出，未落盘缓存会丢失。正常运行最长每 250 ms 写盘，完成试次、后台和导出强制刷新。CSV 损坏尾行会隔离为 `.bin`，完整旧行保留。

应用重开会发现未结束的组，以暂停状态恢复；继续时重做当前未完成试次。禁止把模拟 CSV 当成真机研究结果。

导出失败会单独显示原因，可再次点击导出，原 CSV 保留并继续追加。只有原始记录写盘失败才暂停实验并显示「重试保存」；导出路径错误不需要释放设备空间。

## 本地验证

```bash
swift test --package-path src/HoverStudyCore --scratch-path .tmp/swift-build
xcodebuild -project src/HoverIntentStudy.xcodeproj -scheme HoverIntentStudy \
  -destination 'platform=iOS Simulator,name=Hover Study QA — iPad Pro 12.9' \
  -derivedDataPath .tmp/DerivedData CODE_SIGNING_ALLOWED=NO test
xcodebuild -project src/HoverIntentStudy.xcodeproj -scheme HoverIntentStudy \
  -destination 'generic/platform=iOS' -derivedDataPath .tmp/DeviceBuild \
  CODE_SIGNING_ALLOWED=NO build
python3 qa/check_csv.py /absolute/path/HoverIntent_YYYY-MM-DD.csv --pandas
```

`--demo` 启动 Test 4 模拟界面；`--smoke` 自动通过输入通道检查每类实验一个试次；这两个参数均强制模拟模式。`--ui-testing` 仅在模拟器清除待恢复的模拟试次，用于界面测试。

工程已生成，可直接打开。新增 App Swift 文件后用 `python3 src/generate_project.py` 重建工程；生成器不保存个人签名设置，可在本地重新选择 Team。

更多说明见 [旧协议说明](docs/experiment.md)、[旧数据字典](docs/data-dictionary.md) 和 [公开验收记录](qa/verification-public.md)。

## 报告、回放与数据可用性

公开报告快照位于 `site/report/`；Three.js 工具位于 `site/replay/`，CSV 在浏览器内处理，不上传。原始 CSV、完整逐点回放、设备备份和个人签名保留在本地。公开图包含研究轨迹的可视化，公开 JSON 仅含汇总及模型参数。

```bash
python3 qa/verify_publication.py
python3 -m http.server 8898 --directory site --bind 127.0.0.1
```

访问 http://127.0.0.1:8898/ 。完整分析需提供本地原始 CSV 并安装 numpy、pandas、matplotlib；方法见 [两轮分析](docs/two-run-analysis-method.md)，发布内容与复现步骤见 [公开发布说明](docs/publishing.md)。

## 目录与素材

- `src/`：Xcode 应用、Swift 核心与测试、授权离线场景素材。
- `docs/`：协议、数据字典、安装、方法及限制。
- `qa/`：检查与分析源码、回放模板、Three.js 依赖及公开验收记录。
- `site/`：可独立部署的公开报告和回放入口。
- `.github/workflows/`：核心测试、无签名构建、分析回归和 Pages 部署。

Big Buck Bunny 视频与配图为 CC BY 3.0，归属与转换见 [媒体来源](docs/media-sources.md)。Three.js r180 为 MIT，许可保留在 [THREE-LICENSE.txt](qa/vendor/THREE-LICENSE.txt)。原创代码和报告当前未指定通用开源许可。
