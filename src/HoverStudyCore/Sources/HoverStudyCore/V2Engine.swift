import Foundation

public struct V2Checkpoint: Codable {
  public var config: V2Config
  public var schedule: [V2Trial]
  public var index: Int
  public var attempt: Int
  public var sessionID: String
  public var trialID: String
  public var participant: String
  public var seed: UInt64
  public var synthetic: Bool
  public var outcomes: [TrialOutcome]
  public var completed: Bool
}
public final class V2Engine {
  public private(set) var config = V2Config()
  public private(set) var schedule: [V2Trial] = []
  public private(set) var state: TrialState = .idle
  public private(set) var index = 0, attempt = 0
  public private(set) var sessionID = "", trialID = "", participant = ""
  public private(set) var seed: UInt64 = 0
  public private(set) var synthetic = false
  public private(set) var outcomes: [TrialOutcome] = []
  public private(set) var sceneState = V2SceneState()
  public private(set) var selected: Set<String> = []
  public private(set) var menuOpen = false
  public private(set) var hoverPoint: Point?
  public private(set) var dragPoint: Point?
  public private(set) var stripOffset = 0.0
  public private(set) var lasso: [V2LassoPoint] = []
  public private(set) var lassoSegments: [[V2LassoPoint]] = []
  public private(set) var lassoArmed = false, lassoDeparted = false
  public private(set) var hint = "选择任务和姿势后开始"
  public private(set) var targetTime: Double?
  public private(set) var dwellProgress = 0.0
  public var onEvent: ((StudyEvent) -> Void)?
  public var onCheckpoint: ((V2Checkpoint) -> Void)?
  private var began = 0.0, finished = 0.0, lastHover: Double?, lastReceived: Double?,
    stableSince: Double?
  private var dwellID: String?, dwellSince = 0.0, dwellLast = 0.0, dwellFired = false
  private var dwellSequence = 0, currentSequence = 0
  private var touchStart: Point?, touchLast: Point?, touchTime = 0.0, touchMoved = false
  private var velocity = 0.0, lastTick = 0.0, polluted = false, trialClosed = false
  private var startAnchor: Point?, lassoLength = 0.0
  private var lassoSubmitted = false
  private var fingers: Set<String> = []
  public init() {}
  public var trialStart: Double { began }
  public var current: V2Trial? { schedule.indices.contains(index) ? schedule[index] : nil }
  public var running: Bool { ![.idle, .paused, .ended, .success, .fail].contains(state) }
  public var configurable: Bool { [.idle, .ended].contains(state) }
  public var progress: String {
    if state == .ended { return "本组结束" }
    guard let c = current else { return "尚未开始" }
    return
      "\(attempt>1 ? "重做" : "")第 \(c.ordinal) / \(c.total) \(c.task.reading ? "段" : "次") · 后续 \(max(0,c.total-c.ordinal)) \(c.task.reading ? "段" : "次")"
  }
  public var summary: String {
    if config.revision != nil {
      let valid = Set(outcomes.filter(\.success).map(\.plannedIndex)).count
      let skipped = outcomes.filter { $0.error == "SKIPPED" }.count
      let interrupted = outcomes.filter { ["PAUSED", "BACKGROUND", "PROCESS_INTERRUPTED", "REDO_REQUESTED", "STORAGE_ERROR", "GEOMETRY_CHANGED", "SESSION_ENDED"].contains($0.error ?? "") }.count
      let failed = outcomes.filter { !$0.success }.count - skipped - interrupted
      return "有效 \(valid) / \(schedule.count) 题 · 失败 \(failed) 次 · 跳过 \(skipped) 次 · 中断 \(interrupted) 次 · 已记录 \(outcomes.count) 次尝试"
    }
    let original = outcomes.filter { !$0.isRepeat }
    return
      "有效 \(original.filter{$0.success}.count) · 失败 \(original.filter{!$0.success && $0.error != "SKIPPED"}.count) · 跳过 \(original.filter{$0.error == "SKIPPED"}.count) · 重做记录 \(outcomes.filter{$0.isRepeat}.count)"
  }
  public var objects: [V2Object] {
    guard let c = current else { return [] }
    if c.scene != .abstract {
      var content = V2Content.objects(scene: c.scene, state: sceneState, contentTargets: c.task == .C3 && config.usesContentTargets)
      if c.task == .C3, let revision = config.revision {
        let focus = V2Content.focusObject(scene: c.scene, state: sceneState, size: revision.cObjectDiameter, contentTargets: config.usesContentTargets)
        content.removeAll { $0.id == focus.id }
        if c.scene != .notes || sceneState.detail == nil { content.append(focus) }
      }
      return V2Content.visible(content)
    }
    return c.objects.map { object in
      var o = object
      if o.role == "marker" {
        o.bounds =
          c.horizontal ? o.bounds.shifted(stripOffset, 0) : o.bounds.shifted(0, stripOffset)
      }
      return o
    }
  }
  public var selectionObjects: [V2Object] {
    guard let c = current else { return [] }
    return c.task == .C3 && config.revision != nil ? objects.filter { c.requested.contains($0.id) } : objects.filter { $0.role != "window" }
  }
  public var requiresValidCompletion: Bool {
    current.map { config.requiresValidCompletion($0.task) } ?? false
  }
  public var menuObjects: [V2Object] {
    guard let c = current else { return [] }
    let y = min(620, max(80, (c.objects.first?.bounds.center.y ?? 415) + c.diameter / 2 + 12))
    return ["A", "B", "CANCEL"].enumerated().map { i, id in
      V2Object(
        id, V2Rect(80, y + Double(i) * 52, 230, 48), id == "CANCEL" ? "取消" : "选项 \(id)", "menu")
    }
  }
  public func start(
    participant: String, config: V2Config, seed: UInt64, time: Double, synthetic: Bool
  ) throws {
    guard participant.range(of: "^[A-Za-z0-9_-]{1,32}$", options: .regularExpression) != nil else {
      throw StudyError.invalidParticipant
    }
    schedule = try V2Schedule.make(config, seed: seed)
    self.config = config
    self.participant = participant
    self.seed = seed
    self.synthetic = synthetic
    sessionID = UUID().uuidString
    index = 0
    attempt = 0
    outcomes = []
    trialID = ""
    state = .idle
    emit(
      "SESSION_START", time,
      ["config": v2JSON(config), "schedule": v2JSON(schedule), "contentVersion": config.contentVersion])
    begin(time)
  }
  private func begin(_ t: Double) {
    guard current != nil else {
      state = .ended
      emit("SESSION_END", t)
      checkpoint()
      return
    }
    let previous = trialID
    attempt += 1
    trialID = UUID().uuidString
    trialClosed = false
    began = t
    lastTick = t
    sceneState = V2SceneState()
    selected = []
    menuOpen = false
    hoverPoint = nil
    dragPoint = nil
    stripOffset = 0
    lasso = []
    lassoSegments = []
    lassoArmed = false
    lassoDeparted = false
    lassoLength = 0
    startAnchor = nil
    lassoSubmitted = false
    lastHover = nil
    lastReceived = nil
    stableSince = nil
    dwellID = nil
    dwellProgress = 0
    touchStart = nil
    touchLast = nil
    velocity = 0
    polluted = false
    fingers = []
    targetTime = nil
    state = current!.scene == .abstract ? .waitForStart : .targetPresented
    hint = current!.scene == .abstract ? "请在起点保持稳定" : current!.natural ? "自然阅读即可，无需答题" : "请悬停选择标出的物体"
    emit(
      "TRIAL_START", t,
      [
        "trial": v2JSON(current!),
        "sourceBounds": current!.task == .A2 ? v2JSON(current!.dragBounds()) : "", "redoOf": attempt > 1 ? previous : "",
        "previousTrialID": previous,
        "transitionKind": previous.isEmpty ? "SESSION_START" : attempt > 1 ? "RETRY" : "NEXT_PLANNED",
        "attempt": String(attempt),
      ])
    if state == .targetPresented || current!.task == .B4 { present(t) }
    checkpoint()
  }
  private func present(_ t: Double) {
    targetTime = t
    state = .targetPresented
    emit(
      "TARGET_PRESENT_REQUEST", t, ["objects": v2JSON(objects), "selectionObjects": v2JSON(selectionObjects), "sceneState": v2JSON(sceneState)])
  }
  public func displayFrame(_ t: Double, request: Double, timestamp: Double) {
    guard targetTime == request else { return }
    emit(
      "TARGET_DISPLAY_FRAME", t,
      ["requestTime": String(request), "displayLinkTimestamp": String(timestamp)])
  }
  public func tick(_ t: Double) {
    let dt = max(0, min(0.1, t - lastTick))
    lastTick = t
    let retry = state == .fail && requiresValidCompletion
    let delay = retry ? config.revision!.retryInterval : config.interval
    if [.success, .fail].contains(state), t - finished + 1e-9 >= delay {
      if !retry { index += 1; attempt = 0 }
      begin(t)
      return
    }
    guard running, let c = current else { return }
    if let last = lastReceived, t - last > config.gapMs / 1000 {
      resetDwell(lastHover ?? last, reason: "CALLBACK_GAP")
      stableSince = nil
      if c.task == .B4 && (lassoArmed || !lasso.isEmpty) { cancelLasso(t, reason: "CALLBACK_GAP") }
      lastReceived = nil
      hoverPoint = nil
    }
    if c.scene != .abstract, touchStart == nil, abs(velocity) > 2 {
      let old = sceneState.offset
      sceneState.offset = max(
        0, min(V2Content.maxOffset(scene: c.scene, state: sceneState), old + velocity * dt))
      velocity *= pow(0.08, dt)
      if old != sceneState.offset {
        resetDwell(t, reason: "SCROLL")
        sceneEvent(t, "INERTIA")
      }
    }
    let duration =
      c.natural ? (c.task.reading ? config.readingSeconds : config.snippetSeconds) : config.timeout
    if t - began + 1e-9 >= duration { finish(c.natural, t, error: c.natural ? nil : "TIMEOUT") }
  }
  public func ingest(_ s: InputSample, sequence: Int) {
    guard running, let c = current else { return }
    currentSequence = sequence
    let p = Geometry.local(s.point)
    let t = s.time
    if s.inputType != "PENCIL" {
      let id = s.touchID ?? "unknown-finger"
      if s.phase == "BEGAN" {
        if !polluted { emit("POLLUTION_START", t, ["source": s.source]) }
        fingers.insert(id)
        polluted = true
        resetDwell(t, reason: "FINGER")
        if !c.natural { finish(false, t, error: "UNEXPECTED_TOUCH") }
      }
      if ["ENDED", "CANCELLED"].contains(s.phase) {
        fingers.remove(id)
        if polluted && fingers.isEmpty {
          polluted = false
          emit("POLLUTION_END", t)
        }
      }
      return
    }

    if s.isHover {
      if let last = lastReceived, s.receivedTime - last > config.gapMs / 1000 {
        resetDwell(lastHover ?? t, reason: "CALLBACK_GAP")
        stableSince = nil
        if c.task == .B4 { cancelLasso(t, reason: "CALLBACK_GAP") }
      }
      lastHover = t
      lastReceived = s.receivedTime
      if ["ENDED", "CANCELLED"].contains(s.phase) || !Geometry.contains(p) {
        hoverPoint = nil
        stableSince = nil
        resetDwell(t, reason: s.phase == "ENDED" ? "HOVER_END" : "OUTSIDE")
        if c.task == .B4 { cancelLasso(t, reason: Geometry.contains(p) ? "HOVER_END" : "OUTSIDE") }
        return
      }
      hoverPoint = p
      if polluted || touchStart != nil {
        resetDwell(t, reason: "CONTACT")
        return
      }
      if c.task == .B4 {
        ingestLasso(p, t, sequence)
        return
      }
      if state == .waitForStart || state == .startStable {
        if p.distance(to: c.start) <= 20 {
          if stableSince == nil { stableSince = t }
          state = .startStable
          if (t - stableSince!) * 1000 + 1e-7 >= config.startMs {
            present(t)
            hint = "请操作目标"
            stableSince = nil
          }
        } else {
          stableSince = nil
          state = .waitForStart
        }
        return
      }
      if menuOpen { return }
      let object = (c.scene == .abstract ? selectionObjects : selectionObjects.reversed().map { $0 }).first {
        $0.contains(p) && (c.scene == .abstract || (p.y >= 60 && p.y <= 800))
      }
      let active = c.natural || c.pureHover || c.task == .B1
      guard active, let object else {
        resetDwell(t, reason: "OBJECT_EXIT")
        return
      }
      dwell(object, t, sequence)
    } else {
      resetDwell(t, reason: "TOUCH")
      stableSince = nil
      hoverPoint = nil
      if c.pureHover {
        finish(false, t, error: "UNEXPECTED_TOUCH")
        return
      }
      if !Geometry.contains(p) {
        if touchStart != nil {
          touchStart = nil
          finish(false, t, error: "OUTSIDE_PHONE")
        }
        return
      }
      if c.scene != .abstract {
        sceneTouch(s, p)
        return
      }
      if c.task == .B1 {
        guard menuOpen else {
          finish(false, t, error: "EARLY_TOUCH")
          return
        }
        if s.phase == "BEGAN" { touchStart = p }
        if s.phase == "ENDED" {
          let item = menuObjects.first { $0.bounds.contains(p) }
          if item == nil || item?.id == "CANCEL" {
            menuOpen = false
            touchStart = nil
            emit("MENU_CANCEL", t)
            hint = "请重新悬停唤出菜单"
            return
          }
          let same = touchStart.map { item!.bounds.contains($0) } ?? false
          emit("MENU_SELECT", t, ["item": item!.id])
          finish(
            same && item!.id == c.menuChoice, t,
            error: same && item!.id == c.menuChoice ? nil : "WRONG_MENU_ITEM")
        }
        return
      }
      guard state != .waitForStart && state != .startStable else {
        finish(false, t, error: "EARLY_TOUCH")
        return
      }
      if s.phase == "BEGAN" {
        touchStart = p
        touchLast = p
        touchMoved = false
        touchTime = t
        emit("TOUCH_DOWN", t)
        if c.task == .A2 && !c.dragBounds().contains(p) {
          finish(false, t, error: "WRONG_DRAG_START")
        }
        if c.task == .A2 { dragPoint = p }
        if c.task == .C2 && config.revision != nil && !objects.first(where: { $0.id == "marker" })!.contains(p) {
          finish(false, t, error: "WRONG_SCROLL_START")
        }
      }
      if s.phase == "MOVED", let origin = touchStart, let previous = touchLast {
        if p.distance(to: origin) >= config.movementThreshold && !touchMoved {
          touchMoved = true
          emit("MOVEMENT_START", t)
        }
        if c.task == .A2 { dragPoint = p }
        if c.scroll {
          stripOffset += c.horizontal ? p.x - previous.x : p.y - previous.y
          emit("SCROLL_STATE", t, ["offset": String(stripOffset), "objects": v2JSON(objects)])
        }
        touchLast = p
      }
      if s.phase == "CANCELLED" { finish(false, t, error: "TOUCH_CANCELLED") }
      if s.phase == "ENDED", let start = touchStart {
        emit("TOUCH_UP", t)
        touchStart = nil
        var valid = false
        if c.scroll, let marker = objects.first(where: { $0.id == "marker" }),
          let window = objects.first(where: { $0.id == "window" })
        {
          valid = touchMoved && window.bounds.contains(marker.bounds.center)
          emit("SCROLL_COMMIT", t, ["offset": String(stripOffset), "objects": v2JSON(objects)])
        } else if let target = c.objects.first {
          valid =
            target.contains(p)
            && (c.task == .A2 ? c.dragBounds().contains(start) : target.contains(start))
        }
        finish(valid, t, error: valid ? nil : "MISSED_TARGET")
      }
    }
  }
  private func dwell(_ object: V2Object, _ t: Double, _ sequence: Int) {
    guard let c = current else { return }
    if dwellID != object.id {
      resetDwell(t, reason: "OBJECT_CHANGE")
      dwellID = object.id
      dwellSince = t
      dwellLast = t
      dwellSequence = sequence
      dwellFired = false
      emit("DWELL_START", t, ["objectID": object.id, "bounds": v2JSON(object.bounds)])
    }
    dwellLast = t
    dwellProgress = min(1, (t - dwellSince) * 1000 / config.dwellMs)
    guard !dwellFired, (t - dwellSince) * 1000 + 1e-7 >= config.dwellMs else { return }
    dwellFired = true
    let meta = [
      "objectID": object.id, "startTime": String(dwellSince),
      "startSequence": String(dwellSequence), "endSequence": String(sequence),
      "bounds": v2JSON(object.bounds),
    ]
    if c.natural {
      emit("CANDIDATE", t, meta)
      return
    }
    guard c.requested.contains(object.id) else {
      emit("WRONG_SELECTION", t, meta)
      finish(false, t, error: "WRONG_TARGET")
      return
    }
    if c.task == .B1 {
      menuOpen = true
      emit("MENU_OPEN", t, ["menu": v2JSON(menuObjects), "requestedItem": c.menuChoice])
      hint = "菜单已打开，请点击选项 \(c.menuChoice)"
      return
    }
    if selected.insert(object.id).inserted {
      emit("HOVER_SELECT", t, meta.merging(["selected": v2JSON(selected.sorted())]) { $1 })
    }
    if Set(c.requested) == selected { finish(true, t) }
  }
  private func resetDwell(_ t: Double, reason: String) {
    if let id = dwellID {
      emit(
        "DWELL_END", t,
        [
          "objectID": id, "startTime": String(dwellSince),
          "endTime": String(max(dwellSince, min(t, dwellLast))),
          "durationMs": String(max(0, min(t, dwellLast) - dwellSince) * 1000),
          "candidate": String(dwellFired), "reason": reason, "startSequence": String(dwellSequence),
          "endSequence": String(currentSequence),
        ])
    }
    dwellID = nil
    dwellProgress = 0
    dwellFired = false
  }
  private func ingestLasso(_ p: Point, _ t: Double, _ sequence: Int) {
    guard let c = current else { return }
    if !lassoArmed {
      if p.distance(to: c.start) <= config.lassoRadius {
        if stableSince == nil { stableSince = t }
        if (t - stableSince!) * 1000 + 1e-7 >= config.startMs {
          lassoArmed = true
          startAnchor = p
          lasso = [V2LassoPoint(p, t, sequence)]
          hint = "已准备，请离开起点画圈"
          state = .targetPresented
          if targetTime == nil { present(t) }
          emit("LASSO_ARMED", t, ["start": v2JSON(p)])
        }
      } else {
        stableSince = nil
      }
      return
    }
    guard let anchor = startAnchor else { return }
    if lasso.count == 1 && p.distance(to: c.start) <= config.lassoRadius {
      lasso = [V2LassoPoint(p, t, sequence)]
      startAnchor = p
      return
    }
    if lasso.count == 1 {
      emit("LASSO_START", t, ["start": v2JSON(anchor), "startSequence": String(lasso[0].sequence)])
      hint = "回到起点闭合，不要触屏"
    }
    lassoLength += lasso.last!.point.distance(to: p)
    lasso.append(V2LassoPoint(p, t, sequence))
    emit("LASSO_POINT", t, ["point": v2JSON(p), "sampleSequence": String(sequence)])
    if p.distance(to: anchor) >= config.lassoDeparture { lassoDeparted = true }
    let error = p.distance(to: anchor)
    guard lassoDeparted, error <= config.lassoRadius, lassoLength >= config.lassoLength,
      lasso.count >= config.lassoSamples
    else { return }
    let area = V2Polygon.area(lasso.map(\.point))
    guard area >= config.lassoArea else { return }
    selected = Set(
      c.objects.filter { V2Polygon.contains($0.bounds.center, in: lasso.map(\.point)) }.map(\.id))
    let expected = Set(c.requested)
    lassoSubmitted = true
    emit(
      "LASSO_CLOSE", t,
      [
        "points": v2JSON(lasso), "algorithmicClosingEdge": v2JSON([p, anchor]),
        "closureDistance": String(error), "area": String(area), "pathLength": String(lassoLength),
        "duration": String(t - lasso[0].time), "requested": v2JSON(c.requested),
        "selected": v2JSON(selected.sorted()),
        "missed": v2JSON(expected.subtracting(selected).sorted()),
        "extra": v2JSON(selected.subtracting(expected).sorted()),
        "interruptions": String(lassoSegments.count),
      ])
    finish(selected == expected, t, error: selected == expected ? nil : "LASSO_SELECTION_MISMATCH")
  }
  private func cancelLasso(_ t: Double, reason: String) {
    guard lassoArmed || !lasso.isEmpty else { return }
    lassoSegments.append(lasso)
    emit(
      "LASSO_CANCEL", t,
      ["reason": reason, "points": v2JSON(lasso), "pathLength": String(lassoLength)])
    lasso = []
    lassoArmed = false
    lassoDeparted = false
    lassoLength = 0
    stableSince = nil
    startAnchor = nil
    hint = "圈线已中断，请回起点重新画"
  }
  private func sceneTouch(_ s: InputSample, _ p: Point) {
    guard let c = current else { return }
    let t = s.time
    if s.phase == "BEGAN" {
      touchStart = p
      touchLast = p
      touchTime = t
      touchMoved = false
      velocity = 0
      emit("TOUCH_DOWN", t)
    }
    if s.phase == "MOVED", let a = touchStart, let last = touchLast {
      touchMoved = touchMoved || p.distance(to: a) >= config.movementThreshold
      if c.scene != .video
        && !(c.scene == .notes && sceneState.detail != nil && abs(p.x - a.x) > abs(p.y - a.y))
      {
        let delta = last.y - p.y
        sceneState.offset = max(
          0, min(V2Content.maxOffset(scene: c.scene, state: sceneState), sceneState.offset + delta))
        velocity = delta / max(0.001, t - touchTime)
        sceneEvent(t, "SCROLL")
      }
      touchLast = p
      touchTime = t
    }
    if s.phase == "CANCELLED" {
      touchStart = nil
      velocity = 0
      emit("TOUCH_CANCEL", t)
      return
    }
    if s.phase == "ENDED", let a = touchStart {
      touchStart = nil
      emit("TOUCH_UP", t)
      let dx = p.x - a.x
      let dy = p.y - a.y
      if c.scene == .video {
        if abs(dy) >= 80 && abs(dy) > abs(dx) {
          sceneState.videoIndex = (sceneState.videoIndex + (dy < 0 ? 1 : 5)) % 6
          sceneState.videoTime = 0
          sceneState.videoPaused = false
          sceneState.videoLoops = 0
          sceneEvent(t, "VIDEO_CHANGE")
        } else if !touchMoved {
          sceneState.videoPaused.toggle()
          sceneEvent(t, "VIDEO_TOGGLE")
        }
      } else if c.scene == .notes {
        if sceneState.detail != nil, abs(dx) >= 60 && abs(dx) > abs(dy) {
          sceneState.imageIndex = (sceneState.imageIndex + (dx < 0 ? 1 : 2)) % 3
          sceneEvent(t, "IMAGE_CHANGE")
        } else if !touchMoved {
          if sceneState.detail != nil && p.y < 60 {
            sceneState.detail = nil
            sceneState.offset = sceneState.savedOffset
            sceneEvent(t, "NOTE_BACK")
          } else if sceneState.detail == nil,
            let o = objects.reversed().first(where: { $0.contains(p) }),
            let i = Int(o.id.replacingOccurrences(of: "note-", with: ""))
          {
            sceneState.savedOffset = sceneState.offset
            sceneState.offset = 0
            sceneState.detail = i
            sceneState.imageIndex = 0
            velocity = 0
            sceneEvent(t, "NOTE_OPEN")
          }
        }
      }
    }
  }
  public func videoProgress(_ time: Double, loops: Int, at t: Double) {
    guard running, current?.scene == .video else { return }
    sceneState.videoTime = time
    sceneState.videoLoops = loops
    sceneEvent(t, "VIDEO_PROGRESS")
  }
  private func sceneEvent(_ t: Double, _ action: String) {
    emit(
      "SCENE_STATE", t,
      ["action": action, "sceneState": v2JSON(sceneState), "objects": v2JSON(objects), "selectionObjects": v2JSON(selectionObjects)])
  }
  private func finish(_ success: Bool, _ t: Double, error: String? = nil) {
    guard !trialClosed, current != nil else { return }
    resetDwell(t, reason: "TRIAL_END")
    if !lasso.isEmpty && !lassoSubmitted && error != nil { cancelLasso(t, reason: error!) }
    if polluted {
      emit("POLLUTION_END", t, ["reason": "TRIAL_END"])
      polluted = false
    }
    trialClosed = true
    state = success ? .success : .fail
    finished = t
    hint = !success && requiresValidCompletion ? "未完成，已保留记录；即将重试本题" : "已记录，准备下一次"
    outcomes.append(
      TrialOutcome(
        plannedIndex: index + 1, trialID: trialID, success: success, error: error,
        isRepeat: attempt > 1))
    emit(
      "TRIAL_END", t, ["selected": v2JSON(selected.sorted()), "sceneState": v2JSON(sceneState)],
      success: success, error: error)
    checkpoint()
  }
  public func pause(_ t: Double, reason: String = "PAUSED") {
    guard ![.idle, .ended, .paused].contains(state) else { return }
    if !trialClosed { finish(false, t, error: reason) }
    state = .paused
    hint = "已暂停"
    velocity = 0
    emit("TEST_PAUSE", t)
    checkpoint()
  }
  public func resume(_ t: Double) {
    guard state == .paused else { return }
    if config.revision != nil && trialClosed && outcomes.last(where: { $0.trialID == trialID })?.success == true {
      index += 1
      attempt = 0
    }
    begin(t)
  }
  public func skip(_ t: Double) {
    guard running else { return }
    finish(false, t, error: "SKIPPED")
  }
  public func redo(_ t: Double) {
    guard current != nil, state != .idle, state != .ended else { return }
    if !trialClosed { finish(false, t, error: "REDO_REQUESTED") }
    begin(t)
  }
  public func end(_ t: Double) {
    guard state != .idle && state != .ended else { return }
    if !trialClosed { finish(false, t, error: "SESSION_ENDED") }
    state = .ended
    hint = "本组结束"
    emit("SESSION_END", t)
    checkpoint()
  }
  public var snapshot: V2Checkpoint {
    V2Checkpoint(
      config: config, schedule: schedule, index: index, attempt: attempt, sessionID: sessionID,
      trialID: trialID, participant: participant, seed: seed, synthetic: synthetic,
      outcomes: outcomes, completed: state == .ended)
  }
  public func restore(_ cp: V2Checkpoint, time: Double, persisted: TrialOutcome?) {
    config = cp.config
    schedule = cp.schedule
    index = cp.index
    attempt = cp.attempt
    sessionID = cp.sessionID
    trialID = cp.trialID
    participant = cp.participant
    seed = cp.seed
    synthetic = cp.synthetic
    outcomes = cp.outcomes
    if let persisted, !outcomes.contains(where: { $0.trialID == persisted.trialID }) {
      outcomes.append(persisted)
    }
    state = .paused
    hint = "恢复了未结束的实验，继续将重做当前任务"
    trialClosed = outcomes.contains { $0.trialID == trialID }
    if !trialClosed {
      finish(false, time, error: "PROCESS_INTERRUPTED")
      state = .paused
    }
    emit("SESSION_RECOVER", time)
    checkpoint()
  }
  private func checkpoint() { onCheckpoint?(snapshot) }
  private func emit(
    _ type: String, _ t: Double, _ metadata: [String: String] = [:], success: Bool? = nil,
    error: String? = nil
  ) {
    var m = metadata
    m["protocolVersion"] = config.protocolVersion
    m["progressionPolicy"] = requiresValidCompletion ? "VALID_COMPLETION" : "PLANNED_ATTEMPTS"
    m["attempt"] = String(attempt)
    m["contentVersion"] = config.contentVersion
    m["taskGroup"] = current?.task.group ?? ""
    m["taskID"] = current?.task.rawValue ?? ""
    m["posture"] = config.posture
    m["scene"] = current?.scene.rawValue ?? ""
    m["condition"] = current?.condition ?? ""
    m["sampleSequence"] = String(currentSequence)
    onEvent?(
      StudyEvent(type: type, time: t, state: state, success: success, error: error, metadata: m))
  }
}
