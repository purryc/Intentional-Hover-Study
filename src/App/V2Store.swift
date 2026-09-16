import HoverStudyCore
import SwiftUI

@MainActor final class V2Store: ObservableObject {
  let engine = V2Engine()
  @Published var config = V2Config()
  @Published var participant = "P01"
  @Published var revision = 0
  @Published var error: String?
  @Published var notice = ""
  @Published var stats = LoggerStats()
  @Published var shareFile: ShareFile?
  @Published var files: [URL] = []
  @Published var hoverSeen = false
  @Published var canvas = CGSize.zero
  @Published var simulation = false
  @Published var simulating = false
  private var logger: DailyCSVLogger?
  private var timer: Timer?
  private var inputSequence = 0, ticks = 0
  private var deviceID = ""
  private var handlingError = false
  private let key = "HoverStudy.active.v2"
  var clock: Double { ProcessInfo.processInfo.systemUptime }
  var ready: Bool {
    simulation
      || (["iPad14,5", "iPad14,6"].contains(deviceID) && abs(canvas.width - 1366) < 1
        && abs(canvas.height - 1024) < 1 && hoverSeen)
  }
  var planned: [V2Trial] { (try? V2Schedule.make(config, seed: 0)) ?? [] }
  var countLabel: String {
    let p = planned
    return "\(p.filter{!$0.task.reading}.count) 次短任务 ＋ \(p.filter{$0.task.reading}.count) 段阅读"
  }
  init() {
    var info = utsname()
    uname(&info)
    deviceID = withUnsafePointer(to: &info.machine) {
      $0.withMemoryRebound(to: CChar.self, capacity: 1) { String(cString: $0) }
    }
    #if targetEnvironment(simulator)
      simulation = true
      if ProcessInfo.processInfo.arguments.contains("--ui-testing") {
        UserDefaults.standard.removeObject(forKey: key)
      }
    #endif
    if ProcessInfo.processInfo.arguments.contains("--v2-demo") { simulation = true }
    engine.onEvent = { [weak self] in self?.record($0) }
    engine.onCheckpoint = { [weak self] cp in
      guard let self else { return }
      if cp.completed {
        UserDefaults.standard.removeObject(forKey: self.key)
        if self.config.revision == nil {
          self.config.revision = V2RevisionConfig()
          self.notice = "旧会话已结束，下一会话使用 V2.2 的有效题重试与小目标配置。"
        }
      } else if let data = try? JSONEncoder().encode(cp) {
        UserDefaults.standard.set(data, forKey: self.key)
      }
    }
    if let data = UserDefaults.standard.data(forKey: key),
      let cp = try? JSONDecoder().decode(V2Checkpoint.self, from: data), !cp.completed
    {
      config = cp.config
      participant = cp.participant
      simulation = cp.synthetic
      openLogger()
      var persisted = try? logger?.persistedOutcome(trialID: cp.trialID)
      persisted?.plannedIndex = cp.index + 1
      engine.restore(cp, time: clock, persisted: persisted)
    } else {
      openLogger()
    }
    timer = Timer.scheduledTimer(withTimeInterval: 1 / 30, repeats: true) { [weak self] _ in
      Task { @MainActor in self?.tick() }
    }
    UIApplication.shared.isIdleTimerDisabled = true
  }
  deinit { timer?.invalidate() }
  func setGeometry(_ size: CGSize) {
    canvas = size
    if engine.running && !ready { engine.pause(clock, reason: "GEOMETRY_CHANGED") }
  }
  func openLogger() {
    guard logger == nil else { return }
    do {
      let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
      logger = try DailyCSVLogger(
        directory: documents.appendingPathComponent(simulation ? "SimulatedData" : "Data"),
        synthetic: simulation)
      logger?.onError = { [weak self] message in
        Task { @MainActor in self?.storageFailure(message) }
      }
      files = logger?.files() ?? []
    } catch { self.error = error.localizedDescription }
  }
  func changeSimulation(_ value: Bool) {
    guard engine.configurable else { return }
    try? logger?.flush()
    logger = nil
    simulation = value
    openLogger()
  }
  func start() {
    guard ready, error == nil, engine.configurable else { return }
    do {
      try logger?.flush()
      try engine.start(
        participant: participant, config: config, seed: UInt64.random(in: 1...UInt64.max),
        time: clock, synthetic: simulation)
    } catch { notice = error.localizedDescription }
    revision &+= 1
  }
  func tick() {
    if error == nil { engine.tick(clock) }
    ticks += 1
    revision &+= 1
    if ticks % 15 == 0 { stats = logger?.snapshot() ?? LoggerStats() }
  }
  func background() {
    engine.pause(clock, reason: "BACKGROUND")
    flush()
  }
  func flush() { do { try logger?.flush() } catch { storageFailure(error.localizedDescription) } }
  private func storageFailure(_ message: String) {
    guard !handlingError else { return }
    handlingError = true
    error = message
    engine.pause(clock, reason: "STORAGE_ERROR")
    handlingError = false
  }
  func retry() {
    do {
      openLogger()
      try logger?.retry()
      error = nil
      notice = "已补写缓存，点击继续重做当前任务"
    } catch { self.error = error.localizedDescription }
  }
  func export(_ file: URL? = nil) {
    do {
      if let url = try logger?.export(
        file: file,
        to: FileManager.default.temporaryDirectory.appendingPathComponent(
          "Exports/\(UUID().uuidString)"))
      {
        shareFile = ShareFile(url: url)
      }
    } catch {
      notice = error.localizedDescription
      if logger?.snapshot().error != nil { storageFailure(error.localizedDescription) }
    }
  }
  func loadFiles() { files = logger?.files() ?? [] }
  func receive(_ s: InputSample) {
    if s.isHover && !s.isSynthetic { hoverSeen = true }
    guard engine.running, s.isSynthetic == engine.synthetic else { return }
    inputSequence += 1
    let p = Geometry.local(s.point)
    var f = context(s.time)
    f["recordType"] = "SAMPLE"
    f["x"] = String(s.point.x)
    f["y"] = String(s.point.y)
    f["localX"] = String(p.x)
    f["localY"] = String(p.y)
    f["receivedMonotonicTime"] = String(s.receivedTime)
    f["inputType"] = s.inputType
    f["sampleSource"] = s.source
    f[s.isHover ? "hoverState" : "touchState"] = s.phase
    f["timestampSource"] =
      s.isSynthetic
      ? "SIMULATED_UPTIME"
      : s.isHover ? "CALLBACK_SYSTEM_UPTIME" : "UITOUCH_TIMESTAMP_SYSTEM_UPTIME"
    for (name, value) in [
      ("zOffset", s.z), ("altitudeAngle", s.altitude), ("azimuthAngle", s.azimuth),
      ("azimuthVectorX", s.azimuthX), ("azimuthVectorY", s.azimuthY), ("rollAngle", s.roll),
    ] { if let value { f[name] = String(value) } }
    if !s.isHover {
      f["touchX"] = String(s.point.x)
      f["touchY"] = String(s.point.y)
    }
    var m = metadata()
    m["inputSequence"] = String(inputSequence)
    m["touchID"] = s.touchID
    f["metadata"] = v2JSON(m)
    logger?.append(CSVRow(f, date: Date().addingTimeInterval(s.time - s.receivedTime)))
    if error == nil { engine.ingest(s, sequence: inputSequence) }
  }
  private func metadata() -> [String: String] {
    [
      "protocolVersion": engine.config.protocolVersion, "taskGroup": engine.current?.task.group ?? "",
      "progressionPolicy": engine.requiresValidCompletion ? "VALID_COMPLETION" : "PLANNED_ATTEMPTS",
      "attempt": String(engine.attempt),
      "taskID": engine.current?.task.rawValue ?? "", "posture": engine.config.posture,
      "scene": engine.current?.scene.rawValue ?? "", "condition": engine.current?.condition ?? "",
      "contentVersion": V2Content.version,
    ]
  }
  private func context(_ t: Double) -> [String: String] {
    let c = engine.current
    var f: [String: String] = [:]
    f["participantID"] = engine.participant
    f["sessionID"] = engine.sessionID
    f["testID"] = c?.task.rawValue ?? "V2"
    f["trialID"] = engine.trialID
    f["plannedIndex"] = String(c?.ordinal ?? 0)
    f["plannedTotal"] = String(c?.total ?? 0)
    f["remainingAfterCurrent"] = String(max(0, (c?.total ?? 0) - (c?.ordinal ?? 0)))
    f["isRepeat"] = String(engine.attempt > 1)
    f["taskInstruction"] = c?.instruction ?? ""
    f["trialState"] = engine.state.rawValue
    f["monotonicTime"] = String(t)
    f["elapsedTimeMs"] = String(max(0, t - engine.trialStart) * 1000)
    f["randomSeed"] = String(engine.seed)
    f["conditionID"] = c?.condition ?? ""

    if let c {
      f["distanceA"] = String(c.distance)
      f["targetWidthW"] = String(c.diameter)
      if let o = c.objects.first {
        let p = Geometry.global(o.bounds.center)
        f["targetID"] = o.id
        f["targetX"] = String(p.x)
        f["targetY"] = String(p.y)
        f["targetWidth"] = String(o.bounds.width)
        f["targetHeight"] = String(o.bounds.height)
      }
    }
    return f
  }
  private func record(_ event: StudyEvent) {
    var f = context(event.time)
    var m = event.metadata
    f["recordType"] = "EVENT"
    f["eventType"] = event.type
    f["trialState"] = event.state.rawValue
    f["timestampSource"] = "SYSTEM_UPTIME"
    f["sampleSource"] = engine.synthetic ? "SIMULATED_SYSTEM" : "SYSTEM"
    f["success"] = event.success.map(String.init)
    f["errorType"] = event.error
    m["sessionPlannedIndex"] = String(engine.index + 1)
    if event.type == "SESSION_START" {
      m["deviceIdentifier"] = deviceID
      m["osVersion"] = UIDevice.current.systemVersion
      m["appVersion"] = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "2.2"
      m["phoneRect"] = "976,194,390,830"
      m["simulation"] = String(simulation)
    }
    f["metadata"] = v2JSON(m)
    logger?.append(CSVRow(f, date: Date().addingTimeInterval(event.time - clock)))
    if ["TRIAL_END", "SESSION_END", "TEST_PAUSE"].contains(event.type) { flush() }
  }
  func simulate() {
    guard simulation, engine.running, !simulating else { return }
    simulating = true
    Task {
      await simulationRun()
      simulating = false
    }
  }
  private func send(_ p: Point, _ phase: String = "CHANGED", touch: Bool = false) {
    receive(
      InputSample(
        time: clock, point: Geometry.global(p),
        source: touch ? "SIMULATED_TOUCH" : "SIMULATED_HOVER", phase: phase, z: touch ? nil : 0.5))
  }
  private func hold(_ p: Point, _ ms: Double) async {
    let until = clock + ms / 1000 + 0.04
    while clock < until && engine.running {
      send(p)
      try? await Task.sleep(nanoseconds: 16_000_000)
    }
  }
  private func simulatedSwipe(_ a: Point, _ b: Point) async {
    send(a, "BEGAN", touch: true)
    for i in 1...20 {
      let r = Double(i) / 20
      send(Point(a.x + (b.x - a.x) * r, a.y + (b.y - a.y) * r), "MOVED", touch: true)
      try? await Task.sleep(nanoseconds: 16_000_000)
    }
    send(b, "ENDED", touch: true)
  }
  private func simulationRun() async {
    guard let c = engine.current else { return }
    await hold(c.start, engine.config.startMs)
    if c.task == .B4 {
      let h = c.requested.count == 2 ? 430.0 : 535.0
      let vertices = [Point(45, 220), Point(165, 220), Point(165, h), Point(45, h), Point(45, 220)]
      for i in 1..<vertices.count {
        for j in 1...18 {
          let r = Double(j) / 18
          let a = vertices[i - 1]
          let b = vertices[i]
          send(Point(a.x + (b.x - a.x) * r, a.y + (b.y - a.y) * r))
          try? await Task.sleep(nanoseconds: 16_000_000)
        }
      }
      return
    }
    if c.natural {
      if let o = engine.objects.first(where: { ["paragraph", "card", "video"].contains($0.role) }) {
        await hold(o.bounds.center, engine.config.dwellMs + 100)
      }
      if c.scene == .notes, let o = engine.objects.first(where: { $0.role == "card" }) {
        send(o.bounds.center, "BEGAN", touch: true)
        send(o.bounds.center, "ENDED", touch: true)
        await simulatedSwipe(Point(310, 260), Point(90, 260))
        try? await Task.sleep(nanoseconds: 250_000_000)
        send(Point(30, 30), "BEGAN", touch: true)
        send(Point(30, 30), "ENDED", touch: true)
      }
      if c.scene == .video {
        send(Point(180, 400), "BEGAN", touch: true)
        send(Point(180, 400), "ENDED", touch: true)
        try? await Task.sleep(nanoseconds: 300_000_000)
      }
      await simulatedSwipe(Point(195, 650), Point(195, 350))
      notice = "已模拟阅读操作，阅读段按设定时间结束。"
      return
    }
    if c.pureHover || c.task == .B1 {
      for id in c.requested {
        if let o = engine.objects.first(where: { $0.id == id }) {
          await hold(o.bounds.center, engine.config.dwellMs)
        }
      }
      if c.task == .B1, let o = engine.menuObjects.first(where: { $0.id == c.menuChoice }) {
        send(o.bounds.center, "BEGAN", touch: true)
        send(o.bounds.center, "ENDED", touch: true)
      }
      return
    }
    let start = c.scroll ? c.objects.first(where: { $0.id == "marker" })!.bounds.center : c.task == .A2 ? c.start : c.objects[0].bounds.center
    let end =
      c.scroll
      ? c.objects.first(where: { $0.id == "window" })!.bounds.center : c.objects[0].bounds.center
    send(start, "BEGAN", touch: true)
    if c.task == .A2 || c.scroll {
      for i in 1...20 {
        let r = Double(i) / 20
        send(
          Point(start.x + (end.x - start.x) * r, start.y + (end.y - start.y) * r), "MOVED",
          touch: true)
        try? await Task.sleep(nanoseconds: 16_000_000)
      }
    }
    send(end, "ENDED", touch: true)
  }
}
