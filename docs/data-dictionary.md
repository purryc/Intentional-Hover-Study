# CSV 数据字典 · schemaVersion 1

UTF-8、逗号分隔、标准双引号转义，每条记录一条物理行。字段中的换行规范化为字面量 `\n`/`\r`，metadata 是可解析 JSON。未支持／未计算字段留空，不伪造零值。

| 字段 | 含义与单位 |
|---|---|
| schemaVersion / sequence | 格式版本；文件内递增记录序号，重开继续 |
| recordType | SAMPLE 原始输入；EVENT 状态／离散事件 |
| date / timestamp | 按本地日期分文件；ISO8601 时间含时区及毫秒 |
| monotonicTime | 开机以来单调时间，秒；悬停是回调接收时刻，触摸是 UITouch.timestamp |
| receivedMonotonicTime | 原始输入在应用收到时的 systemUptime，秒 |
| timestampSource | CALLBACK_SYSTEM_UPTIME / UITOUCH_TIMESTAMP_SYSTEM_UPTIME / SYSTEM_UPTIME / SIMULATED_UPTIME |
| elapsedTimeMs | 相对当前尝试开始的毫秒 |
| participantID / sessionID | 参与者编号；参与者加 UUID 的运行标识 |
| testID / trialID | 0–4；组 ID 加计划序号和尝试序号 |
| plannedIndex / plannedTotal / remainingAfterCurrent | 当前原定序号／本组计划数／不包含当前的后续数 |
| isRepeat / taskInstruction / conditionID | 是否重做；屏幕实际中文主任务；距离、尺寸、方向／模式条件 |
| trialState | 输入时或事件时的实验阶段 |
| x / y | 参考画布全局 XY，pt |
| localX / localY | 手机局部 XY，x−976、y−194；越界数据仍保存 |
| zOffset | 归一化悬停相对距离，不换算毫米；接触行为空 |
| hoverState / touchState | BEGAN / CHANGED（悬停）或 MOVED（接触）/ ENDED / CANCELLED |
| inputType | PENCIL / FINGER，非 Pencil 接触正式试次判输入不符 |
| sampleSource | PENCIL_HOVER / PENCIL_TOUCH / FINGER_TOUCH / SYSTEM；模拟来源统一 SIMULATED_ 前缀 |
| altitudeAngle / azimuthAngle | 弧度 |
| azimuthVectorX / Y | 单位向量 |
| rollAngle | 当前目标 Pencil 不支持，留空 |
| vx / vy / speed / acceleration | 保留 PRD 列；V1 不在线计算，离线按原始时间计算 |
| targetID / targetX / targetY / targetWidth / targetHeight | 目标 ID、全局中心坐标和直径，pt |
| distanceA / targetWidthW / fittsID | 几何距离、宽度，pt；log2(1+A/W) |
| distanceToTarget | 原始输入到目标中心的 XY 距离，pt |
| radialVelocity / headingError | 保留列，离线计算 |
| touchX / touchY | 接触原始行及 TOUCH_DOWN/UP 的全局坐标，pt |
| eventType | SESSION/TEST/TRIAL、STATE_CHANGE、起点稳定、目标进出、接触、滑动和保存恢复等事件 |
| success / errorType | true / false；失败原因，未结束行留空 |
| randomSeed | UInt64 种子；读取 pandas 时可指定为字符串以保持精度 |
| metadata | SESSION_START 保存完整配置、计划、设备、姿态、反馈、画布、时区；TRIAL_START 保存 repeatOfTrialID；SWIPE_END 保存起终点、位移、方向弧度和接触时长 |

TARGET_PRESENT_REQUEST 是状态机请求目标显示的时刻。TARGET_APPEAR 为兼容 PRD 的同义请求事件，不能当作光子级呈现时刻。TARGET_DISPLAY_FRAME 记录首次绘制目标后收到的 CADisplayLink 回调及其 timestamp，提供帧参考，也不是实测屏幕发光时刻。

CSV_TAIL_RECOVERED 记录应用重开时发现并隔离的非完整末行；对应 `.partial-UUID.bin` 文件保留原字节。写入错误时，未确认批次回滚到本批写入前偏移，批次保留在内存供重试；失败后已写的字节留为 failed-batch-UUID.bin。已确认行不被覆盖。

CSV 为增量持久化；强制结束可能丢失最多最近未确认缓冲或故障期间内存中的行，已完成并强制刷新的试次保留。应用 checkpoint 用于恢复实验计划，不代替原始 CSV。

## 读取和触摸前窗口

```python
import pandas as pd

df = pd.read_csv('HoverIntent_2026-09-15.csv', dtype={'randomSeed':'string'})
trial = df[df.trialID == '需要分析的 trialID']
touch = trial[trial.eventType == 'TOUCH_DOWN'].monotonicTime.iloc[0]
hover = trial[(trial.recordType == 'SAMPLE') & trial.sampleSource.str.contains('HOVER', na=False)]
window = hover[hover.monotonicTime.between(touch - 0.6, touch)]
```

有触摸前 600 ms 的查询接口不代表每次都有完整 600 ms 传感覆盖。没有采到的范围必须保留为空，不能插值后称为原始数据。`qa/check_csv.py` 会报告实际点数、最早时间和覆盖缺口。

`csv-check.json` 中的 preTouchCoverage 表示已记录的时间范围从触摸前 600 ms 以前开始；不是要求第一条窗口内离散样本恰好位于 -600 ms，也不证明整个窗口持续有硬件采样。窗口内点数、最早／最近点和最大回调间隔另列，未进行插值。

重开时以已保存的 CSV 中 TRIAL_END 对照 checkpoint，避免已完成试次因 checkpoint 滞后再次被标为中断。当前每日文件的完整行如存在格式、UTF-8、序号损坏则暂停使用，不覆盖原文件。
