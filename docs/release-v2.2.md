# Intentional Hover Study · V2.2

发布原生 iPad 研究采集应用和行动轨迹统一报告。

## 应用

- 14 类任务：A 自然基线7类、B主动Hover4类、C混淆任务3类；姿势和任务可选。
- 中文任务与剩余次数常驻手机区域上方；固定手机仿真几何。
- A/C 失败保留并重试同一计划题，B1–B4 默认各12次，记录成功率。
- C1 小目标、C2 小标记、C3 围绕具体内容对象的48pt范围。
- 新闻长文、双列图文流、六条授权短视频；无答题和输入任务。
- Pencil 原始输入、每日 CSV 追加、恢复和导出快照；V1 与 V2.1 兼容。

打开 `src/HoverIntentStudy.xcodeproj`，使用自己的 Apple 开发者 Team 安装。下载版本源码 ZIP 即含完整工程及场景媒体。

## 报告与回放

- [在线统一报告](https://purryc.github.io/Intentional-Hover-Study/report/study-report.html)：12章、17图、Markdown和汇总参数。
- [Three.js回放工具](https://purryc.github.io/Intentional-Hover-Study/replay/replay-v2.html)：导入自己的CSV，在浏览器内处理，不上传。
- 报告ZIP含完整静态站点，可通过本地HTTP服务打开。

本轮研究仅一位参与者，两轮均右手，先拇指后食指，实测协议V2.1；C检验为回顾性分析。低速、减速或500ms停留单独不足以可靠确认意图；home固定过滤未改善本轮C3。原始CSV、完整逐点回放和个人设备备份保存在本地。

## 实际检查状态

发布准备：核心50/50、分析22/22、公开快照及95处本地链接检查通过；合成CSV在浏览器中成功导入并显示B4圈线事件。此前V2.2模拟器8/8、iOS无签名和本地签名构建通过，目标iPad已安装2.2/build3并启动。

新版真实Pencil逐类试做、15分钟接收/落盘专项和AirDrop尚未验收，见 `qa/verification-public.md`。
