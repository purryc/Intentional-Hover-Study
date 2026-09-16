# Intentional Hover Study · 公开发布

仓库：https://github.com/purryc/Intentional-Hover-Study

站点：https://purryc.github.io/Intentional-Hover-Study/

## 发布内容

- 原生 iPad 应用 V2.2 的 Xcode 工程、Swift 核心、测试及六条授权离线视频。
- 统一研究报告：12 章、17 张分析图、Markdown、汇总与模型参数 JSON。
- Three.js 手机轨迹回放工具。初始为空；CSV 在浏览器内读取，不上传。
- 协议、数据字典、分析代码和公开验收记录。

原始 CSV、完整逐点回放 JSON、逐点导数、设备备份、个人签名、设备 UUID 和本机运行日志保留在本地。公开图中包含研究轨迹的可视化，公开 JSON 提供汇总，不提供原始点列。数据来源 SHA256 用于核对本地证据。

公开的是一位参与者的右手拇指与右手食指两轮 V2.1 实测；V2.2 是后续采集修订。C 组已被探索，报告中的留组检查是回顾性的。新目标与重试的真机逐类操作、15 分钟接收/落盘专项及 AirDrop 尚未验收。

## 安装与本地使用

应用从 Xcode 源码安装，使用自己的开发者 Team。仓库不提供可通用安装的个人签名 IPA。步骤见 README。

公开快照已经包含在 `site/`，无需原始数据即可运行：

```bash
python3 qa/verify_publication.py
python3 -m http.server 8898 --directory site --bind 127.0.0.1
```

访问 http://127.0.0.1:8898/ 。回放页可导入自己的 V2.1/V2.2 CSV。

本地完整研究分析需要原始 CSV 和 numpy、pandas、matplotlib，按 `docs/two-run-analysis-method.md` 执行。公开快照不能替代原始数据重新估计轨迹或模型。

已有完整分析结果时重新生成公开版：

```bash
python3 qa/build_public_site.py \
  --analysis analysis/trajectory_2026-09-15/hands_run2 \
  --source 'data/HoverIntent_2026-09-15 2.csv'
python3 qa/verify_publication.py
```

生成器核对原数据和报告来源哈希，复制报告及图，改写本地证据链接，生成汇总 JSON、站点入口和文件哈希清单；不复制原始 CSV。GitHub Actions 检查已提交的公开快照后仅部署 `site/`。

本次发布准备检查：Swift 核心 50/50 通过；七个分析测试模块共22项通过；公开快照12章/17图、95处本地链接与六条视频SHA256检查通过。GitHub检查运行时，本地旧协议CSV兼容检查在未提供私有文件的环境跳过，其余过滤与重建检查使用合成输入。

## 素材与许可

六条视频及配图来自 Blender Foundation 的 Big Buck Bunny，CC BY 3.0，变更和来源见 `docs/media-sources.md`。Three.js r180 与 OrbitControls 为 MIT，许可证保留在 `qa/vendor/THREE-LICENSE.txt`。原创代码和报告目前未指定通用开源许可。
