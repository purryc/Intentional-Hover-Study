# 实验配置与实现行为

## 已确认的条件
12.9 英寸第六代 iPad Pro、第二代 Apple Pencil、拇指绑笔、笔尖接触、简单位置圆环。PRD 是第一版范围来源，PDF 的自然 baseline、食指姿态与 13 类任务没有加入第一版。关于裸指的外推仍需其他传感器重复实验。

正式画布 1366×1024 pt，手机区域左上角 (976,194)、宽 390、高 830。横屏方向支持左右两种，正式试次改变窗口尺寸会暂停。预览按比例缩放，全部事件转换回参考坐标；只有正式尺寸能进行正式实验。

## 默认配置

| 参数 | 默认值 |
|---|---|
| 距离 | 120 / 220 / 320 pt |
| 目标直径 | 30 / 50 / 80 pt |
| 指向每条件重复 | 8，要求偶数，上下方向配平 |
| 校准每方向重复 | 5 |
| 经过每速度重复 | 8，要求偶数，上下方向配平 |
| 滑动次数 | 12 |
| 起点半径 / 稳定 | 32 pt / 300 ms |
| 校准目标内保持 | 1000 ms，可移动但须处于目标内，不强制速度阈值 |
| Test 4 起点稳定后的指令阶段 | 800 ms |
| 试次间隔 | 400 ms，最初 120 ms 显示成功／失败边框 |
| 目标出现后超时 | 15000 ms |
| 悬停结束接触衔接宽限 | 500 ms |
| 滑动开始 / 完成 | 移动 >10 pt；向上 ≥80 pt、垂直位移 > 水平位移、抬笔 |

任务指令从试次开始始终可见，因此 Test 4 的 800 ms 是起点稳定后到目标请求呈现的最短指令阶段，不表示参与者此前看不到当前指令。目标处没有 HOVER 停留要求，没有吸附、减速阈值或在线意图分类。

## 任务几何与数量

- Test 0：目标 (195,415)，起点左 (75,415)、右 (315,415)、上 (195,295)、下 (195,535)，共 20 次。先在方向起点准备，再向目标靠近。
- Test 1：起点 (195,415)，目标上下距离 A；9 个距离／尺寸组合各 8 次，共 72 次。
- Test 2：起终点 (195,130) 与 (195,700)，目标 (195,415)、直径 60。三个速度指令各 8 次，共 24 次。成功须存在实际采样点进入中间目标、离开目标后进入终点；不能把未采到的经过补为真实事件。
- Test 3：起点 (195,650)，页面可任意有效位置接触后向上滑动，共 12 次。信息卡片根据接触位移跟随滚动。
- Test 4：复用 Test 1 几何；TAP/HOVER 各 72 次，共 144 次。距离／尺寸／方向的数量完全配平，使用存储种子的 SplitMix64 和洗牌；实际完整计划另存于 SESSION_START。

配置若不能保证目标完整位于手机区域内，明确拒绝保存／开始，不裁切目标或临时改变距离。数值必须正数，重复次数设置上限以防误输入。

## 标签和失败

指令条件代表被要求执行的任务；TOUCH_DOWN 是提交锚点。TARGET_ENTER/EXIT 只表示坐标进入／离开目标的几何区域，MOVEMENT_START 只表示离开起点半径，不能直接当成已确认的意图或瞄准时刻。

失败理由：MISSED_TARGET、EARLY_TOUCH、UNEXPECTED_TOUCH、UNEXPECTED_INPUT、INVALID_SWIPE、OUT_OF_BOUNDS、TRACKING_INTERRUPTED、TOUCH_CANCELLED、TIMEOUT、RESEARCHER_SKIP、RESEARCHER_REPEAT、PAUSE、SYSTEM_INTERRUPT、WINDOW_GEOMETRY_CHANGED、STORAGE_ERROR、APP_INTERRUPTED、TEST_ENDED。

悬停的 ENDED 后先等待接触事件，500 ms 内接触正常继续；未接触且没有重新收到悬停则记追踪中断。回调间隔 >100 ms 单独记录 HOVER_CALLBACK_GAP；静止时没有 changed 回调不能证明传感器丢帧，因此不按回调空档强制失败。成功／失败的接触抬笔原始样本和 TOUCH_UP 都保留。

暂停记当前未完成试次失败，继续产生关联重做；若试次已经完成，则继续到下一计划试次。每条尝试都有自己的 trialID。组汇总不把重做成功覆盖原失败，离线分析自行决定剔除和替代规则。

## 实施依据
UIKit API 和可用性核对本机 Xcode 26.2 的 UIHoverGestureRecognizer.h、UITouch.h、UIEvent.h。悬停 zOffset/XY 使用 UIKit，接触移动使用系统交付的 coalesced touches，不使用 predicted touches。

Apple 官方接口参考：https://developer.apple.com/documentation/uikit/adopting-hover-support-for-apple-pencil
