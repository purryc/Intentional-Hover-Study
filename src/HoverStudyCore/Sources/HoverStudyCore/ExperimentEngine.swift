import Foundation

/// Input processing stays on the application's main thread. CSV writing runs independently.
public final class ExperimentEngine {
    public private(set) var participant = ""
    public private(set) var sessionID = ""
    public private(set) var test: TestKind = .fitts
    public private(set) var config = ExperimentConfig()
    public private(set) var seed: UInt64 = 0
    public private(set) var schedule: [TrialCondition] = []
    public private(set) var index = 0
    public private(set) var attempt = 0
    public private(set) var trialID = ""
    public private(set) var state: TrialState = .idle
    public private(set) var trialStart: Double = 0
    public private(set) var targetTime: Double?
    public private(set) var outcomes: [TrialOutcome] = []
    public private(set) var isRepeat = false
    public private(set) var synthetic = false
    public private(set) var lastPoint: Point?
    public private(set) var hoverActive = false
    public private(set) var contactActive = false
    public private(set) var lastError = ""
    public var onEvent: ((StudyEvent) -> Void)?
    public var onCheckpoint: ((Checkpoint?) -> Void)?
    private var stableSince: Double?
    private var holdSince: Double?
    private var instructionSince: Double?
    private var finishTime: Double?
    private var hoverEndTime: Double?
    private var targetInside = false
    private var targetCrossed = false
    private var startWasInside = false
    private var touchStart: Point?
    private var touchTime: Double?
    private var touchHit = false
    private var swipeStarted = false
    private var continuationIndex: Int?
    private var pausedNeedsAdvance = false
    public var current: TrialCondition? { schedule.indices.contains(index) ? schedule[index] : nil }
    public var plannedNumber: Int { schedule.isEmpty ? 0 : min(index + 1, schedule.count) }
    public var remaining: Int { max(0, schedule.count - plannedNumber) }
    public var isRunning: Bool { ![.idle, .paused, .ended].contains(state) }
    public var showTarget: Bool { targetTime != nil && ![.waitForStart, .startStable, .instruction, .paused, .idle, .ended].contains(state) }
    public var progress: String {
        guard !schedule.isEmpty else { return "尚未开始" }
        if state == .ended { return "本组结束 · \(schedule.count) 次计划任务" }
        return "\(isRepeat ? "重做" : "第") \(plannedNumber) / \(schedule.count) 次 · 后续还有 \(remaining) 次"
    }
    public var summary: String {
        let original = outcomes.filter { !$0.isRepeat }
        let skipped = original.filter { $0.error == "RESEARCHER_SKIP" }.count
        return "有效 \(original.filter(\.success).count) · 失败 \(original.filter { !$0.success && $0.error != "RESEARCHER_SKIP" }.count) · 跳过 \(skipped) · 重做 \(outcomes.filter(\.isRepeat).count)"
    }
    public init() {}
    private func event(_ type: String, at time: Double, success: Bool? = nil, error: String? = nil, metadata: [String: String] = [:]) {
        onEvent?(StudyEvent(type: type, time: time, state: state, success: success, error: error, metadata: metadata))
    }
    private func transition(_ next: TrialState, at time: Double) {
        let old = state; state = next
        event("STATE_CHANGE", at: time, metadata: ["from": old.rawValue, "to": next.rawValue])
    }
    public func start(participant: String, test: TestKind, config: ExperimentConfig, seed: UInt64, time: Double, synthetic: Bool = false) throws {
        guard participant.range(of: "^[A-Za-z0-9_-]{1,32}$", options: .regularExpression) != nil else { throw StudyError.invalidParticipant }
        let trials = try TrialRandomizer.make(test: test, config: config, seed: seed)
        self.participant = participant; self.test = test; self.config = config; self.seed = seed; self.synthetic = synthetic
        sessionID = "\(participant)_\(UUID().uuidString)"; schedule = trials; index = 0; attempt = 0; outcomes = []; isRepeat = false; continuationIndex = nil
        trialID = ""; trialStart = time; state = .idle
        event("SESSION_START", at: time); event("TEST_START", at: time)
        beginTrial(at: time)
    }
    private func beginTrial(at time: Double, previous: String? = nil) {
        attempt += 1
        trialID = "\(sessionID)_T\(index + 1)_A\(attempt)"
        trialStart = time; targetTime = nil; stableSince = nil; holdSince = nil; instructionSince = nil; finishTime = nil; hoverEndTime = nil
        hoverActive = false; contactActive = false; lastPoint = nil; targetInside = false; targetCrossed = false; startWasInside = false; touchStart = nil; touchTime = nil; touchHit = false; swipeStarted = false; lastError = ""; pausedNeedsAdvance = false
        transition(.waitForStart, at: time)
        event("TRIAL_START", at: time, metadata: previous.map { ["repeatOfTrialID": $0] } ?? [:])
        saveCheckpoint()
    }
    private func saveCheckpoint(interrupted: Bool = false) {
        guard state != .idle && state != .ended else { onCheckpoint?(nil); return }
        onCheckpoint?(Checkpoint(participant: participant, sessionID: sessionID, test: test, config: config, seed: seed, schedule: schedule, index: index, attempt: attempt, trialID: trialID, outcomes: outcomes, isRepeat: isRepeat, interrupted: interrupted, synthetic: synthetic))
    }
    public func restore(_ c: Checkpoint, time: Double) {
        participant = c.participant; sessionID = c.sessionID; test = c.test; config = c.config; seed = c.seed; schedule = c.schedule; index = c.index; attempt = c.attempt; trialID = c.trialID; outcomes = c.outcomes; isRepeat = c.isRepeat; synthetic = c.synthetic; trialStart = time; state = .paused
        let alreadyCompleted = outcomes.contains { $0.trialID == c.trialID }
        let interruptionErrors: Set<String> = ["PAUSE", "SYSTEM_INTERRUPT", "APP_INTERRUPTED", "WINDOW_GEOMETRY_CHANGED", "STORAGE_ERROR"]
        pausedNeedsAdvance = alreadyCompleted && !interruptionErrors.contains(outcomes.last?.error ?? "")
        // The checkpoint is written at trial boundaries. Its active attempt may have been abruptly interrupted.
        if !alreadyCompleted {
            outcomes.append(TrialOutcome(plannedIndex: index + 1, trialID: trialID, success: false, error: "APP_INTERRUPTED", isRepeat: isRepeat))
            event("TRIAL_FAIL", at: time, success: false, error: "APP_INTERRUPTED")
            event("TRIAL_END", at: time, success: false, error: "APP_INTERRUPTED")
        }
        event("SESSION_RECOVERED", at: time, metadata: ["interruptedTrialID": trialID]); saveCheckpoint(interrupted: true)
    }
    public func ingest(_ s: InputSample) {
        guard isRunning, let c = current else { return }
        guard s.isSynthetic == synthetic else { return }
        let p = Geometry.local(s.point)
        if s.isHover {
            if s.phase == "ENDED" || s.phase == "CANCELLED" {
                hoverActive = false; stableSince = nil; holdSince = nil
                event("HOVER_END", at: s.time)
                if [.waitForStart, .startStable].contains(state) { transition(.waitForStart, at: s.time); startWasInside = false }
                else if !contactActive && targetTime != nil { hoverEndTime = s.receivedTime }
                return
            }
            hoverActive = true; hoverEndTime = nil; lastPoint = p
            if !Geometry.contains(p) {
                if targetTime != nil && ![.success, .fail, .interTrial].contains(state) { finish(false, error: "OUT_OF_BOUNDS", at: s.time) }
                else { stableSince = nil; startWasInside = false; if state == .startStable { transition(.waitForStart, at: s.time) } }
                return
            }
            if state == .waitForStart || state == .startStable {
                let inside = p.distance(to: c.start) <= 32
                if inside && !startWasInside { stableSince = s.receivedTime; transition(.startStable, at: s.time); event("START_ZONE_ENTER", at: s.time) }
                if !inside { stableSince = nil; if startWasInside { event("START_ZONE_EXIT", at: s.time); transition(.waitForStart, at: s.time) } }
                startWasInside = inside
            }
            if [.targetPresented, .movement].contains(state) {
                if state == .targetPresented && p.distance(to: c.start) > 32 { transition(.movement, at: s.time); event("MOVEMENT_START", at: s.time) }
                let inside = p.distance(to: c.target) <= c.diameter / 2
                if inside != targetInside {
                    targetInside = inside
                    event(inside ? "TARGET_ENTER" : "TARGET_EXIT", at: s.time)
                    if inside { targetCrossed = true; holdSince = s.receivedTime } else { holdSince = nil }
                }
                if test == .passThrough, targetCrossed, !targetInside, let end = c.end, p.distance(to: end) <= 32 { finish(true, at: s.time) }
            }
        } else {
            if s.phase == "BEGAN" { event("TOUCH_DOWN", at: s.time, metadata: ["touchX": String(s.point.x), "touchY": String(s.point.y)]) }
            if s.phase == "ENDED" { event("TOUCH_UP", at: s.time, metadata: ["touchX": String(s.point.x), "touchY": String(s.point.y)]) }
            if s.phase == "CANCELLED" { event("TOUCH_CANCEL", at: s.time) }
            guard ![.success, .fail, .interTrial].contains(state) else { return }
            if s.phase == "BEGAN" {
                hoverEndTime = nil; contactActive = true; touchStart = p; touchTime = s.time; lastPoint = p
                guard s.inputType == "PENCIL" else { finish(false, error: "UNEXPECTED_INPUT", at: s.time); return }
                guard targetTime != nil else { finish(false, error: "EARLY_TOUCH", at: s.time); return }
                guard Geometry.contains(p) else { finish(false, error: "OUT_OF_BOUNDS", at: s.time); return }
                if test == .passThrough || test == .calibration { finish(false, error: "UNEXPECTED_TOUCH", at: s.time); return }
                touchHit = test == .swipe || p.distance(to: c.target) <= c.diameter / 2
                transition(.action, at: s.time)
            } else if s.phase == "MOVED", contactActive {
                lastPoint = p
                if !Geometry.contains(p) { finish(false, error: "OUT_OF_BOUNDS", at: s.time); return }
                if test == .swipe, !swipeStarted, let start = touchStart, p.distance(to: start) > config.swipeStartThreshold {
                    swipeStarted = true; event("SWIPE_START", at: s.time)
                }
            } else if s.phase == "ENDED", contactActive {
                contactActive = false
                if test == .swipe, let start = touchStart {
                    let dx = p.x - start.x, dy = p.y - start.y
                    let ok = Geometry.contains(p) && swipeStarted && -dy >= config.swipeCompletionDistance && abs(dy) > abs(dx)
                    event("SWIPE_END", at: s.time, metadata: ["touchStartLocalX": String(start.x), "touchStartLocalY": String(start.y), "touchEndLocalX": String(p.x), "touchEndLocalY": String(p.y), "swipeDistance": String(hypot(dx,dy)), "swipeDirection": String(atan2(dy,dx)), "touchDurationMs": String((s.time - (touchTime ?? s.time)) * 1000)])
                    finish(ok, error: ok ? nil : "INVALID_SWIPE", at: s.time)
                } else { finish(touchHit, error: touchHit ? nil : "MISSED_TARGET", at: s.time) }
            } else if s.phase == "CANCELLED", contactActive { contactActive = false; finish(false, error: "TOUCH_CANCELLED", at: s.time) }
        }
    }
    public func tick(time: Double) {
        guard isRunning else { return }
        if state == .startStable, hoverActive, let t = stableSince, (time - t) * 1000 >= config.startStableMs {
            event("START_ZONE_STABLE", at: time)
            if test == .comparison { instructionSince = time; transition(.instruction, at: time) }
            else { presentTarget(at: time) }
        }
        if state == .instruction, let t = instructionSince, (time - t) * 1000 >= config.instructionMs { presentTarget(at: time) }
        if test == .calibration, [.targetPresented, .movement].contains(state), hoverActive, targetInside, let t = holdSince, (time - t) * 1000 >= config.calibrationHoldMs { finish(true, at: time) }
        // A Pencil contact normally terminates hover first. Allow its touch event to arrive before treating hover loss as interruption.
        if let t = hoverEndTime, !contactActive, (time - t) >= 0.5, [.targetPresented, .movement].contains(state) { finish(false, error: "TRACKING_INTERRUPTED", at: time) }
        if let t = targetTime, (time - t) * 1000 >= config.timeoutMs, [.targetPresented, .movement, .action].contains(state) { finish(false, error: "TIMEOUT", at: time) }
        if [.success, .fail].contains(state), let t = finishTime, time - t >= 0.12 { transition(.interTrial, at: time) }
        if state == .interTrial, let t = finishTime, (time - t) * 1000 >= config.interTrialMs { advance(at: time) }
    }
    private func presentTarget(at time: Double) {
        targetTime = time; transition(.targetPresented, at: time)
        event("TARGET_PRESENT_REQUEST", at: time); event("TARGET_APPEAR", at: time, metadata: ["timingMeaning": "STATE_REQUEST_NOT_PHOTOMETRIC"])
        saveCheckpoint()
    }
    public func displayFrame(time: Double, trialID: String, requestedAt: Double, frameTimestamp: Double) {
        guard self.trialID == trialID, targetTime == requestedAt else { return }
        event("TARGET_DISPLAY_FRAME", at: time, metadata: ["displayLinkTimestamp": String(frameTimestamp), "presentationRequestTime": String(requestedAt), "timingMeaning": "FIRST_DISPLAY_LINK_AFTER_TARGET_DRAW_NOT_PHOTOMETRIC"])
    }
    private func finish(_ success: Bool, error: String? = nil, at time: Double) {
        guard isRunning && ![.success, .fail, .interTrial].contains(state) else { return }
        lastError = error ?? ""; finishTime = time; hoverEndTime = nil
        transition(success ? .success : .fail, at: time)
        outcomes.append(TrialOutcome(plannedIndex: index + 1, trialID: trialID, success: success, error: error, isRepeat: isRepeat))
        event(success ? "TRIAL_SUCCESS" : "TRIAL_FAIL", at: time, success: success, error: error)
        event("TRIAL_END", at: time, success: success, error: error)
        saveCheckpoint()
    }
    private func advance(at time: Double) {
        index = continuationIndex ?? index + 1; continuationIndex = nil; isRepeat = false
        if index >= schedule.count { end(time: time) } else { beginTrial(at: time) }
    }
    public func skip(time: Double) {
        guard isRunning, ![.success, .fail, .interTrial].contains(state) else { return }
        event("TRIAL_SKIP", at: time); finish(false, error: "RESEARCHER_SKIP", at: time)
    }
    public func pause(time: Double, reason: String = "PAUSE") {
        guard isRunning else { return }
        let wasFinished = [.success, .fail, .interTrial].contains(state)
        if !wasFinished { finish(false, error: reason, at: time) }
        pausedNeedsAdvance = wasFinished
        transition(.paused, at: time); hoverActive = false; contactActive = false
        event("TEST_PAUSE", at: time, error: reason); saveCheckpoint(interrupted: true)
    }
    public func resume(time: Double) {
        guard state == .paused else { return }
        event("TEST_RESUME", at: time)
        if pausedNeedsAdvance { advance(at: time) }
        else {
            let prior = trialID
            if !isRepeat { continuationIndex = index + 1 }
            isRepeat = true; beginTrial(at: time, previous: prior)
        }
    }
    public func repeatTrial(time: Double) {
        guard !schedule.isEmpty, state != .idle else { return }
        let prior: String
        if state == .ended {
            index = schedule.count - 1; prior = outcomes.last?.trialID ?? trialID; continuationIndex = schedule.count
            event("TEST_REOPEN_FOR_REPEAT", at: time)
        } else {
            prior = trialID
            if isRunning && ![.success, .fail, .interTrial].contains(state) { finish(false, error: "RESEARCHER_REPEAT", at: time) }
            if !isRepeat { continuationIndex = index + 1 }
        }
        isRepeat = true; beginTrial(at: time, previous: prior)
    }
    public func end(time: Double) {
        guard state != .idle && state != .ended else { return }
        if isRunning && ![.success, .fail, .interTrial].contains(state) { finish(false, error: "TEST_ENDED", at: time) }
        transition(.ended, at: time); hoverActive = false; contactActive = false
        event("TEST_END", at: time, metadata: ["summary": summary]); event("SESSION_END", at: time); onCheckpoint?(nil)
    }
}
