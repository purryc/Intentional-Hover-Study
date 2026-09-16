import SwiftUI
import UIKit
import HoverStudyCore
import Darwin

@MainActor final class StudyStore: ObservableObject {
    let engine = ExperimentEngine()
    @Published var participant = "P01"
    @Published var selectedTest: TestKind = .fitts
    @Published var config = ExperimentConfig()
    @Published var simulation = false
    @Published var showDebug = false
    @Published var revision = 0
    @Published var storageError: String?
    @Published var notice = ""
    @Published var stats = LoggerStats()
    @Published var shareFile: ShareFile?
    @Published var previousFiles: [URL] = []
    @Published var canvasSize = CGSize.zero
    private(set) var latestInput: InputSample?
    @Published var hoverSeen = false
    @Published var runningSyntheticTrial = false
    private var formalLogger: DailyCSVLogger?
    private var simulatedLogger: DailyCSVLogger?
    private var timer: Timer?
    private var tickCount = 0
    private var displayDirty = false
    private var sampleCount = 0
    private var lastSampleTime: Double?
    private var lastHoverTime: Double?
    private var errorHandling = false
    private var deviceID: String = ""
    private let checkpointKey = "HoverStudy.active.v1"
    private var smokeStarted = false
    var clock: Double { ProcessInfo.processInfo.systemUptime }
    var logger: DailyCSVLogger? { simulation ? simulatedLogger : formalLogger }
    var geometryValid: Bool { abs(canvasSize.width - 1366) < 0.5 && abs(canvasSize.height - 1024) < 0.5 }
    var targetHardware: Bool { ["iPad14,5", "iPad14,6"].contains(deviceID) }
    var ready: Bool { simulation || (targetHardware && geometryValid && hoverSeen) }
    var sensorMessage: String {
        if simulation { return "模拟输入 · 与正式数据分开保存" }
        if !targetHardware { return "请使用 12.9 英寸第六代 iPad Pro" }
        if !geometryValid { return "请横屏全屏打开，关闭窗口缩放" }
        if !hoverSeen { return "请将 Pencil 靠近屏幕，确认悬停信号" }
        return "已收到 Pencil 悬停 · 可以开始"
    }
    var canConfigure: Bool { [.idle, .ended].contains(engine.state) }
    var canControl: Bool { storageError == nil }
    var canBegin: Bool { canConfigure && ready && storageError == nil && logger != nil }
    var prompt: String { engine.current?.instruction ?? "选择实验，准备开始" }
    init() {
        var system = utsname(); uname(&system)
        deviceID = withUnsafePointer(to: &system.machine) { p in p.withMemoryRebound(to: CChar.self, capacity: 1) { String(cString: $0) } }
        #if targetEnvironment(simulator)
        simulation = true
        #endif
        if ProcessInfo.processInfo.arguments.contains("--simulate") || ProcessInfo.processInfo.arguments.contains("--demo") || ProcessInfo.processInfo.arguments.contains("--smoke") { simulation = true }
        #if targetEnvironment(simulator)
        if ProcessInfo.processInfo.arguments.contains("--ui-testing") { UserDefaults.standard.removeObject(forKey: checkpointKey) }
        #endif
        openLoggers()
        engine.onEvent = { [weak self] event in self?.record(event) }
        engine.onCheckpoint = { [weak self] c in
            guard let self else { return }
            if let c, let data = try? JSONEncoder().encode(c) { UserDefaults.standard.set(data, forKey: self.checkpointKey) }
            else { UserDefaults.standard.removeObject(forKey: self.checkpointKey) }
        }
        if let data = UserDefaults.standard.data(forKey: checkpointKey), var checkpoint = try? JSONDecoder().decode(Checkpoint.self, from: data) {
            simulation = checkpoint.synthetic; participant = checkpoint.participant; selectedTest = checkpoint.test; config = checkpoint.config
            do {
                if !checkpoint.outcomes.contains(where: { $0.trialID == checkpoint.trialID }), let outcome = try logger?.persistedOutcome(trialID: checkpoint.trialID) { checkpoint.outcomes.append(outcome) }
            } catch { storageError = error.localizedDescription }
            engine.restore(checkpoint, time: clock); notice = "发现未结束的实验。继续后从当前任务起点重做，原记录保留。"
        }
        UIApplication.shared.isIdleTimerDisabled = true
        timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.tick() }
        }
        if let timer { RunLoop.main.add(timer, forMode: .common) }
    }
    private func openLoggers() {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        do {
            if formalLogger == nil { formalLogger = try DailyCSVLogger(directory: documents.appendingPathComponent("Data")) }
            if simulatedLogger == nil { simulatedLogger = try DailyCSVLogger(directory: documents.appendingPathComponent("SimulatedData"), synthetic: true) }
            for log in [formalLogger, simulatedLogger].compactMap({ $0 }) {
                log.onError = { [weak self] message in DispatchQueue.main.async { self?.handleStorageError(message) } }
            }
        } catch { storageError = error.localizedDescription }
    }
    private func tick() {
        if !simulation && engine.isRunning && !geometryValid { engine.pause(time: clock, reason: "WINDOW_GEOMETRY_CHANGED") }
        if storageError == nil { engine.tick(time: clock) }
        tickCount += 1
        if displayDirty { revision &+= 1; displayDirty = false }
        if tickCount.isMultiple(of: 8) {
            logger?.requestSnapshot { [weak self] stats in DispatchQueue.main.async { if self?.stats != stats { self?.stats = stats } } }
        }
        if !smokeStarted && canvasSize.width > 0 {
            smokeStarted = true
            if ProcessInfo.processInfo.arguments.contains("--smoke") { Task { await self.smoke() } }
            else if ProcessInfo.processInfo.arguments.contains("--verify-export") { export() }
            else if ProcessInfo.processInfo.arguments.contains("--demo") && canConfigure { selectedTest = .comparison; start() }
        }
    }
    func setGeometry(_ size: CGSize) { canvasSize = size }
    func start() {
        guard canBegin else { notice = sensorMessage; return }
        do {
            try config.validate(); try logger?.flush()
            let seed = UInt64.random(in: 1...UInt64.max)
            try engine.start(participant: participant, test: selectedTest, config: config, seed: seed, time: clock, synthetic: simulation)
            notice = ""; sampleCount = 0; lastSampleTime = nil; lastHoverTime = nil; revision &+= 1
        } catch { notice = error.localizedDescription }
    }
    func pause(reason: String = "PAUSE") { engine.pause(time: clock, reason: reason); revision &+= 1 }
    func resume() {
        guard canControl && ready else { notice = storageError ?? sensorMessage; return }
        engine.resume(time: clock); revision &+= 1
    }
    func skip() { guard canControl else { return }; engine.skip(time: clock); revision &+= 1 }
    func repeatTrial() { guard canControl && ready else { return }; engine.repeatTrial(time: clock); revision &+= 1 }
    func end() { engine.end(time: clock); revision &+= 1 }
    func background() {
        if engine.isRunning { pause(reason: "SYSTEM_INTERRUPT") }
        do { try logger?.flush() } catch { handleStorageError(error.localizedDescription) }
    }
    func changeMode(_ value: Bool) {
        guard canConfigure else { return }; simulation = value; storageError = logger?.snapshot().error; stats = logger?.snapshot() ?? LoggerStats(); notice = ""; revision &+= 1
    }
    func receive(_ s: InputSample) {
        if !hoverSeen && s.isHover && !s.isSynthetic && s.inputType == "PENCIL" && !["ENDED", "CANCELLED"].contains(s.phase) { hoverSeen = true }
        latestInput = s
        displayDirty = true
        guard engine.state != .idle && engine.state != .ended, s.isSynthetic == engine.synthetic else { return }
        let fields = sampleFields(s)
        logger?.append(CSVRow(fields, date: Date().addingTimeInterval(s.time - s.receivedTime)))
        sampleCount += 1
        if s.isHover {
            if let last = lastHoverTime, s.receivedTime - last > 0.1 {
                appendSystem("HOVER_CALLBACK_GAP", at: s.receivedTime, metadata: ["intervalMs": String((s.receivedTime-last)*1000), "meaning": "CALLBACK_GAP_NOT_PROVEN_SENSOR_LOSS"])
            }
            lastHoverTime = s.receivedTime
        }
        lastSampleTime = s.time
        if storageError == nil { engine.ingest(s) }
    }
    private func context(time: Double) -> [String: String] {
        let e = engine
        var f: [String: String] = ["participantID": e.participant, "sessionID": e.sessionID, "testID": String(e.test.rawValue), "trialID": e.trialID, "plannedIndex": String(e.plannedNumber), "plannedTotal": String(e.schedule.count), "remainingAfterCurrent": String(e.remaining), "isRepeat": String(e.isRepeat), "taskInstruction": prompt, "trialState": e.state.rawValue, "monotonicTime": String(time), "elapsedTimeMs": String((time-e.trialStart)*1000), "randomSeed": String(e.seed)]
        if let c = e.current {
            f["conditionID"] = c.conditionID; f["targetID"] = "\(e.trialID)_TARGET"; f["targetX"] = String(Geometry.global(c.target).x); f["targetY"] = String(Geometry.global(c.target).y); f["targetWidth"] = String(c.diameter); f["targetHeight"] = String(c.diameter); f["distanceA"] = String(c.distance); f["targetWidthW"] = String(c.diameter); f["fittsID"] = String(c.fittsID)
        }
        return f
    }
    private func sampleFields(_ s: InputSample) -> [String: String] {
        var f = context(time: s.time); let local = Geometry.local(s.point)
        f["recordType"] = "SAMPLE"; f["x"] = String(s.point.x); f["y"] = String(s.point.y); f["localX"] = String(local.x); f["localY"] = String(local.y)
        f["receivedMonotonicTime"] = String(s.receivedTime); f["inputType"] = s.inputType; f["sampleSource"] = s.source
        f["timestampSource"] = s.isSynthetic ? "SIMULATED_UPTIME" : s.isHover ? "CALLBACK_SYSTEM_UPTIME" : "UITOUCH_TIMESTAMP_SYSTEM_UPTIME"
        f[s.isHover ? "hoverState" : "touchState"] = s.phase
        for (name, value) in [("zOffset",s.z), ("altitudeAngle",s.altitude), ("azimuthAngle",s.azimuth), ("azimuthVectorX",s.azimuthX), ("azimuthVectorY",s.azimuthY), ("rollAngle",s.roll)] { if let value { f[name] = String(value) } }
        if !s.isHover { f["touchX"] = String(s.point.x); f["touchY"] = String(s.point.y) }
        if let target = engine.current?.target { f["distanceToTarget"] = String(local.distance(to: target)) }
        return f
    }
    private func json(_ dictionary: [String: String]) -> String {
        guard let data = try? JSONSerialization.data(withJSONObject: dictionary, options: [.sortedKeys]) else { return "{}" }
        return String(decoding: data, as: UTF8.self)
    }
    private func record(_ ev: StudyEvent) {
        var f = context(time: ev.time); f["recordType"] = "EVENT"; f["eventType"] = ev.type; f["trialState"] = ev.state.rawValue; f["timestampSource"] = "SYSTEM_UPTIME"; f["sampleSource"] = engine.synthetic ? "SIMULATED_SYSTEM" : "SYSTEM"; f["inputType"] = "PENCIL"
        if let success = ev.success { f["success"] = String(success) }; f["errorType"] = ev.error
        var metadata = ev.metadata
        if ev.type == "SESSION_START" {
            metadata["config"] = String(decoding: (try? JSONEncoder().encode(engine.config)) ?? Data(), as: UTF8.self)
            metadata["schedule"] = String(decoding: (try? JSONEncoder().encode(engine.schedule)) ?? Data(), as: UTF8.self)
            metadata["deviceIdentifier"] = deviceID; metadata["osVersion"] = UIDevice.current.systemVersion; metadata["holdingCondition"] = "THUMB_MOUNTED_PENCIL"; metadata["commitInput"] = "PENCIL_TIP"; metadata["cursorFeedback"] = "SIMPLE_RING"; metadata["canvas"] = "1366x1024pt"; metadata["phoneRect"] = "976,194,390,830"; metadata["appVersion"] = "1.0"; metadata["timeZone"] = TimeZone.current.identifier; metadata["simulation"] = String(engine.synthetic)
        }
        f["touchX"] = ev.metadata["touchX"]; f["touchY"] = ev.metadata["touchY"]; f["metadata"] = json(metadata)
        logger?.append(CSVRow(f))
        if ["TRIAL_END", "SESSION_END", "TEST_PAUSE"].contains(ev.type) {
            do { try logger?.flush() } catch { DispatchQueue.main.async { [weak self] in self?.handleStorageError(error.localizedDescription) } }
        }
        revision &+= 1
    }
    private func appendSystem(_ type: String, at time: Double, metadata: [String: String]) {
        record(StudyEvent(type: type, time: time, state: engine.state, metadata: metadata))
    }
    private func handleStorageError(_ message: String) {
        guard !errorHandling else { return }; errorHandling = true; storageError = message
        if engine.isRunning { engine.pause(time: clock, reason: "STORAGE_ERROR") }
        errorHandling = false; revision &+= 1
    }
    func retryStorage() {
        do { openLoggers(); try logger?.retry(); guard logger != nil else { return }; storageError = nil; notice = "已补写缓存。点击继续，从当前任务起点重做。"; stats = logger!.snapshot() }
        catch { storageError = error.localizedDescription }
    }
    func export(_ file: URL? = nil) {
        guard storageError == nil else { return }
        do {
            let destination = FileManager.default.temporaryDirectory.appendingPathComponent("Exports/\(UUID().uuidString)")
            guard let url = try logger?.export(file: file, to: destination) else { return }
            shareFile = ShareFile(url: url); notice = "已生成 CSV 快照，原文件继续保留。"
        } catch {
            if logger?.snapshot().error != nil { handleStorageError(error.localizedDescription) }
            else { shareFile = nil; notice = error.localizedDescription }
        }
    }
    func loadFiles() { previousFiles = logger?.files() ?? [] }
    func frame(time: Double, trialID: String, requestedAt: Double, timestamp: Double) { engine.displayFrame(time: time, trialID: trialID, requestedAt: requestedAt, frameTimestamp: timestamp) }
    func simulateTrial() {
        guard simulation && engine.isRunning && !runningSyntheticTrial && canControl else { return }
        runningSyntheticTrial = true
        Task { await runSyntheticTrial(); runningSyntheticTrial = false }
    }
    private func send(_ p: Point, hover: Bool = true, phase: String = "CHANGED", z: Double? = 0.5) {
        let t = clock
        receive(InputSample(time: t, point: Geometry.global(p), source: hover ? "SIMULATED_HOVER" : "SIMULATED_TOUCH", inputType: "PENCIL", phase: phase, z: hover ? z : nil))
    }
    private func wait(_ seconds: Double) async { try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000)) }
    private func runSyntheticTrial() async {
        guard let c = engine.current else { return }
        let id = engine.trialID
        send(c.start, phase: "BEGAN")
        // Keep sending stationary samples so logger timing and the same engine paths are exercised.
        while [.waitForStart, .startStable, .instruction].contains(engine.state) && engine.trialID == id {
            send(c.start); await wait(0.02)
        }
        guard engine.trialID == id && engine.isRunning else { return }
        let steps = 35
        for i in 1...steps {
            let ratio = Double(i) / Double(steps)
            send(Point(c.start.x + (c.target.x - c.start.x) * ratio, c.start.y + (c.target.y - c.start.y) * ratio), z: 0.6 - ratio * 0.2)
            await wait(0.02)
            guard engine.trialID == id && engine.isRunning else { return }
        }
        if engine.test == .calibration {
            for _ in 0..<Int(engine.config.calibrationHoldMs / 20 + 4) { send(c.target); await wait(0.02); if engine.trialID != id { return } }
        } else if engine.test == .passThrough, let end = c.end {
            for i in 1...35 { let r = Double(i)/35; send(Point(c.target.x + (end.x-c.target.x)*r,c.target.y+(end.y-c.target.y)*r)); await wait(0.02); if engine.trialID != id { return } }
        } else {
            send(c.target, phase: "ENDED", z: 0)
            send(c.target, hover: false, phase: "BEGAN")
            await wait(0.04)
            if engine.test == .swipe {
                for i in 1...12 { send(Point(c.target.x,c.target.y-Double(i)*10), hover: false, phase: "MOVED"); await wait(0.02) }
                send(Point(c.target.x,c.target.y-120), hover: false, phase: "ENDED")
            } else { send(c.target, hover: false, phase: "ENDED") }
        }
    }
    private func smoke() async {
        if engine.state == .paused { end() }
        simulation = true; participant = "SIM_QA"
        config = ExperimentConfig(); config.repetitions = 2; config.calibrationRepetitions = 1; config.passRepetitions = 2; config.swipeRepetitions = 1
        for test in TestKind.allCases {
            selectedTest = test; start(); await runSyntheticTrial(); await wait(0.5); end(); await wait(0.1)
        }
        do { try logger?.flush(); notice = "模拟检查已完成 Test 0–4，查看 SimulatedData CSV。" } catch { handleStorageError(error.localizedDescription) }
        config = ExperimentConfig(); selectedTest = .comparison; start()
    }
}
struct ShareFile: Identifiable { let id = UUID(); let url: URL }
