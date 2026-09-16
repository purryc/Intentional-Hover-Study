# V2 数据与回放字典

## 兼容性
CSV 的56列与 schemaVersion=1 保持不变；协议由 metadata.protocolVersion=`HOVER_INTENT_V2_1` / `HOVER_INTENT_V2_2` / `HOVER_INTENT_V2_3` / `HOVER_INTENT_V2_4` 区分。旧 testID 是0–4，新 testID 是A1–C3。不要把新 testID 转为整数。`qa/check_csv.py` 支持混合协议的同日文件。

V2.4 可选视线样本使用 `inputType=GAZE`、`sampleSource=FRONT_CAMERA_GAZE`；校准原始特征、屏幕估计、有效性、校准 ID 与相机帧时间写入 metadata。前摄拒绝或失跟踪时坐标留空，不填零。新 App 的试次间样本以 metadata.`sequencePhase=INTER_TRIAL` 标明，仍归属刚结束的 trialID；下一次 `TRIAL_START` 带 `previousTrialID` 和 `transitionKind`，供完整动作序列重建。旧会话无此字段时，回放按 `TASK` 处理。

每个 SAMPLE 和 EVENT：participantID、sessionID、trialID、taskInstruction、plannedIndex、plannedTotal、remainingAfterCurrent、conditionID、monotonicTime、randomSeed。plannedIndex/Total按当前任务计算，C条件共用进度；metadata.sessionPlannedIndex给出整个会话位置。每个实际重做使用新 trialID、isRepeat=true；TRIAL_START.metadata.redoOf关联前次。

## 原始采样
- x/y：固定iPad画布坐标pt；localX/localY：减去(976,194)后的手机局部pt。原值保留，包括手机外样本。
- zOffset：API原值，可为空，绝不换算毫米。仅悬停具有Z；接触回放位于页面平面。
- sampleSource：PENCIL_HOVER / PENCIL_TOUCH / FINGER_TOUCH；模拟来源SIMULATED开头并保存于SimulatedData。
- hoverState / touchState：BEGAN、CHANGED/MOVED、ENDED、CANCELLED。
- timestampSource：悬停CALLBACK_SYSTEM_UPTIME，接触UITOUCH_TIMESTAMP_SYSTEM_UPTIME，事件SYSTEM_UPTIME，模拟SIMULATED_UPTIME。
- receivedMonotonicTime：收到回调的uptime；接触monotonicTime保留UITouch.timestamp，合并触摸保留每个真实采样；不使用预测触摸。
- altitudeAngle、azimuthAngle、azimuthVectorX/Y：可用时原值。当前设备采集路径的rollAngle为空，不推算。
- sequence：落盘文件行序号；metadata.inputSequence：本次进程接收样本序号。事件中的sampleSequence和B4点内sequence关联同一trialID的inputSequence，不能直接当作文件行号。
- metadata.touchID：本次接触对象的进程内身份，供重叠手指接触污染合并，不是参与者标识。

## 通用 metadata
protocolVersion、taskGroup(A/B/C)、taskID、posture(THUMB/CRADLE_INDEX)、scene(abstract/news/notes/video)、condition(TOUCH/TAP/SCROLL/HOVER/NATURAL)、contentVersion。
SESSION_START含config、实际schedule、设备型号、系统与App版本、手机矩形、模拟标记。
A2的sourceBounds是40×40pt源方块；起始接触必须在所绘方块内。A2释放位置、A3/A4移动标记中心落入目标区域即成功。
TRIAL_START.trial含instruction、ordinal/total、distance/diameter、direction(-1上/左,+1下/右)、requested对象集合、objects边界、start起点、menuChoice。
TARGET_PRESENT_REQUEST含objects与sceneState；TARGET_DISPLAY_FRAME含requestTime及displayLinkTimestamp，表示后续显示回调，不声称光学呈现测量。

## 场景与选择事件
- SCENE_STATE：action + sceneState + 当时objects（可见对象含屏幕边界和实际文本）。state保存offset、savedOffset、detail、imageIndex、videoIndex、videoTime、videoPaused、videoLoops。
- 内容坐标→屏幕：文章/列表/详情对象减offset；返回笔记列表恢复savedOffset。视频无连续滚动偏移，按videoIndex切页。
- SCROLL_STATE/SCROLL_COMMIT：抽象条带offset及实际marker/window边界；绘制和终点判定共享这些对象。
- MENU_OPEN：菜单对象和requestedItem；MENU_CANCEL可重试；MENU_SELECT保留实际item。
- DWELL_START：对象id、边界、起始时间与样本支持。DWELL_END：startTime/endTime/durationMs、首末样本序号、candidate是否达标及结束原因。截止到最后有效样本，不把缺口补成长停留。
- CANDIDATE：自然阅读同对象达到500ms的“规则可能触发”，一个完整停留只产生一次。并非真实误触/意图标签。
- HOVER_SELECT：对象id、边界、起始时间、样本支持及累积selected；B1以MENU_OPEN替代选择事件。
- POLLUTION_START/END：所有同时存在的手指接触合并为污染段；仅最后一根手指离开后结束。自然阅读保持运行，分析剔除污染段内样本。失败/结束会截断仍持续的污染段并标注TRIAL_END。

## B4
LASSO_ARMED记录起点稳定；离开前最后一个真实点作为实际起点，LASSO_START保存该点及支持序号。等待期间不计入圈选路径或耗时。
LASSO_POINT：逐个原始手机XY、单调时间、inputSequence。不平滑、不补点。
LASSO_CANCEL：reason、未完成points、pathLength；下一圈另起一段，不跨缺口。
LASSO_CLOSE：原始points、algorithmicClosingEdge（末点→首点）、closureDistance(pt)、pathLength(pt，实测边不含算法闭合边)、area(pt²，奇偶填充)、duration(s)、requested/selected/missed/extra、interruptions。
圆中心在多边形内或边界算选中。自交面积按奇偶扫描线积分，不使用会抵消两叶的有符号面积。

## 生成与使用回放
```bash
python3 qa/build_v2_replay.py /path/to/HoverIntent_YYYY-MM-DD.csv --output analysis/trajectory_YYYY-MM-DD
python3 -m http.server 8897 --bind 127.0.0.1 --directory analysis/trajectory_YYYY-MM-DD
```
打开replay-v2.html，或直接在页面导入CSV。V2不会修改旧replay.html使用的旧数据。原始CSV保留不动；生成v2_trajectories.json和v2_motion.csv，含来源哈希。页面可再次导出分析JSON及运动CSV。
过滤A/B/C、任务、场景、姿势、条件；按接触/悬停选择/菜单/候选/圈选闭合定位。无接触的试次仍保留。圈线为原始XY/Z；橙色虚线是算法闭合边。
连续段按输入来源、结束事件、被排除点、≤0或>100ms间隔拆分。速度由相邻原始XY点求差，时间取中点；二维加速度幅值由相邻速度向量再求差；accelerationTime为两条速度中点的中点，accelSeq0/1/2保留三个原始支持点。Z单独显示。原始CSV导数列不填入估算，导数只在分析CSV生成。
触摸前600ms报告连续有效悬停边覆盖的实际毫秒数，不把最早时间早于窗口等同于完整覆盖。自然候选率目前按该试次已记录的总时长计算，污染排除数单独报告。

## 研究限制
六条25秒竖屏短片来自同一授权动画作品，不代表内容多样性；文本为自写原型内容。视频回放按记录的播放时间定位，精度受编码帧与250ms视频进度记录限制。没有推断用户意图或真实误触标签。

## V2.2 扩展
config.revision 保存 bRepetitions(默认2)、cDiameters([24,36,48])、cMarkerDiameter(36)、cObjectDiameter(48)、retryInterval(1.2)。revision缺失表示旧协议，保持每个B6题和旧自动推进。
metadata.progressionPolicy=VALID_COMPLETION / PLANNED_ATTEMPTS，metadata.attempt 是同一计划题的实际尝试序号。A/C 的 isRepeat 不表示额外有效配额：按 sessionID + sessionPlannedIndex 去重统计有效题，按 trialID 统计全部尝试。
selectionObjects 为当前实际提交/候选对象的边界，与 objects 的呈现和滚动同步。C3 小对象ID为 news-focus-photo、note-focus-save、video-save；只对该对象记录静默自然候选。TARGET_PRESENT_REQUEST/SCENE_STATE 保存 selectionObjects。新小区域与旧整内容区域的候选率必须分协议比较。

## V2.3 内容对象
config.revision.contentTargets=true 表示新内容对象协议；旧revision缺少该字段时仍为V2.2。contentVersion=reading-2026-09-v3-butterfly；C3焦点ID为news-content-butterfly、notes-content-butterfly、video-content-butterfly，role=content-object，mediaID=cover-1。objects保存完整配图/卡片位置，selectionObjects只保存蝴蝶周围默认48×48pt范围。两条件共享布局，新闻/图文随滚动更新；视频为画面内固定配图对象，背景视频另记真实进度，不代表动态视频对象跟踪。旧对象标签及正式CSV不改写。

## V2.4 前摄视线补充
仅当 config.revision.gazeCollection=true 时使用 V2.4；默认关闭。`SAMPLE` 中 `inputType=GAZE`、`sampleSource=FRONT_CAMERA_GAZE` 表示前摄估计，不能当 Pencil 点或触摸点。原 56 列不变。有效样本 x/y 是校准后的 iPad 全屏坐标、localX/localY 是手机局部坐标；追踪丢失或未校准时四者为空。无论是否在手机区内，原样本均保留；热区仅纳入有效且在手机区域内的帧。Z、角度和接触字段对 gaze 为空。

`monotonicTime`/`receivedMonotonicTime` 是本进程收到 ARFrame 时的 uptime；原始 `ARFrame.timestamp` 在 metadata.arFrameTimestamp，`timestampSource=ARFRAME_CAPTURE_TIMESTAMP_IN_METADATA_RECEIVED_UPTIME`。不要直接假定相机帧时间与 Pencil/触摸时间具有相同零点；计算并报告帧接收延迟/抖动后才做毫秒级眼手先后比较。

metadata.calibrationID、gazeQuality、gazeValidity、rawCameraPlaneX/Y、phoneRegion、gazeObjectID/gazeObjectBounds（若命中）用于质量和对象关联。`GAZE_CALIBRATION` 事件含拟合系数、独立验证点误差 P90/覆盖及校准 ID。`GAZE_UNAVAILABLE`、`GAZE_TRACKING_LOST/RESUMED` 表示不可用与恢复，不能当作没有看目标。精度未达到试验门槛时仅做较大内容区域热区，不对 48 pt 小目标报告同对象命中。旧解析器和轨迹分析必须排除 GAZE 输入，不能让其打断 Pencil 连续段；新版回放将 gaze 单独呈现。详见 [V2.4 实验方案](protocol-gaze-v2-4.md)。
