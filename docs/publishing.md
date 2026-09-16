# Intentional Hover Study · 公开发布

仓库：https://github.com/purryc/Intentional-Hover-Study

站点：https://purryc.github.io/Intentional-Hover-Study/

## 发布内容

- 原生 iPad 应用 V2.4 的 Xcode 工程、Swift 核心、测试及六条授权离线视频；前摄视线默认关闭，开启后需校准。
- 综合报告含四张经过审查的派生图；旧版 12 章、17 图、Markdown 和汇总 JSON 原样保留并注明来源版本。
- Three.js 手机轨迹回放工具。初始为空；CSV 在浏览器内读取，不上传。
- 综合报告串联 V2.1/V2.3 运动形态与 V2.4 阅读视线正对照；只发布汇总说明与少量派生图，不发布逐点眼动、试次 ID 或原始面部画面。
- 协议、数据字典、分析代码和公开验收记录。

原始 CSV、完整逐点回放 JSON、逐点导数、设备备份、个人签名、设备 UUID 和本机运行日志保留在本地。公开图中包含研究轨迹的可视化，公开 JSON 提供汇总，不提供原始点列。数据来源 SHA256 用于核对本地证据。

旧版 12 章报告来自一位参与者的右手拇指与右手食指两轮 V2.1 实测。综合页另引用追加前的 V2.3 两轮运动汇总及后续 V2.4 单手拇指新会话，逐版注明证据范围；不能把跨协议和跨日差异解释为模型准确率改善。V2.4 前摄校准未通过小对象门槛，眼动仅为粗区域探索。C 组已被探索，报告中的留组检查是回顾性的。新目标与重试的真机逐类操作、15 分钟接收/落盘专项及 AirDrop 尚未验收。

## 安装与本地使用

应用从 Xcode 源码安装，使用自己的开发者 Team。仓库不提供可通用安装的个人签名 IPA。步骤见 README。

公开快照已经包含在 `site/`，无需原始数据即可运行：

```bash
python3 qa/verify_publication.py
python3 -m http.server 8898 --directory site --bind 127.0.0.1
```

访问 http://127.0.0.1:8898/ 。回放页可导入自己的 V2 CSV；公开页不预载原始采集。

本次综合更新运行 `qa/build_public_update.py`，输入 9/15 原文件和 9/16 已追加 V2.4 的原文件。生成器核对 9/15 全文件 SHA、9/16 历史 V2.3 字节前缀 SHA 与最新全文件 SHA，先重建旧版站点，再复制经过审查的四张汇总图、生成 `site/report/combined.html` 并更新公开文件清单。旧版报告保留原版本和 12 章/17 图。发布前运行 `qa/verify_publication.py`、核心测试与无签名构建，并检查暂存清单、Pages 部署及线上链接。

本地完整研究分析需要原始 CSV 和 numpy、pandas、matplotlib，按 `docs/two-run-analysis-method.md` 执行。公开快照不能替代原始数据重新估计轨迹或模型。

已有完整分析结果时重新生成公开版：

```bash
python3 qa/build_public_update.py \
  --legacy-source 'data/HoverIntent_2026-09-15 2.csv' \
  --current-source 'data/HoverIntent_2026-09-16.csv' \
  --legacy-analysis analysis/trajectory_2026-09-15/hands_run2 \
  --atlas-analysis analysis/trajectory_2026-09-16/two_day_motion_atlas \
  --gaze-analysis analysis/trajectory_2026-09-16/gaze_home_latest
python3 qa/verify_publication.py
```

生成器核对原数据和报告来源哈希，复制报告及图，改写本地证据链接，生成汇总 JSON、站点入口和文件哈希清单；不复制原始 CSV。GitHub Actions 检查已提交的公开快照后仅部署 `site/`。

本次发布准备检查：Swift 核心 60/60 通过；分析回归 55 项中 54 通过、1 项按原有条件跳过；模拟器 UI 12/12、模拟器及设备无签名构建通过；公开快照 48 个文件、109 处本地链接，旧报告 12 章/17 图，综合页四张图。GitHub 检查运行时，本地旧协议 CSV 兼容检查在未提供私有文件的环境跳过，其余过滤与重建检查使用合成输入。真机专项状态见 [V2.4 公开验收记录](../qa/verification-v2-4-public.md)。

## 素材与许可

六条视频及配图来自 Blender Foundation 的 Big Buck Bunny，CC BY 3.0，变更和来源见 `docs/media-sources.md`。Three.js r180 与 OrbitControls 为 MIT，许可证保留在 `qa/vendor/THREE-LICENSE.txt`。原创代码和报告目前未指定通用开源许可。
