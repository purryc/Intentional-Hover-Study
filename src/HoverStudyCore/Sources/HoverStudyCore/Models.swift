import Foundation

public struct Point: Codable, Equatable, Sendable {
    public var x: Double
    public var y: Double
    public init(_ x: Double, _ y: Double) { self.x = x; self.y = y }
    public func distance(to p: Point) -> Double { hypot(x - p.x, y - p.y) }
}
public enum Geometry {
    public static let canvas = Point(1366, 1024)
    public static let origin = Point(976, 194)
    public static let phoneSize = Point(390, 830)
    public static let center = Point(195, 415)
    public static func local(_ global: Point) -> Point { Point(global.x - origin.x, global.y - origin.y) }
    public static func global(_ local: Point) -> Point { Point(local.x + origin.x, local.y + origin.y) }
    public static func contains(_ p: Point, radius: Double = 0) -> Bool {
        p.x >= radius && p.x <= 390 - radius && p.y >= radius && p.y <= 830 - radius
    }
}
public enum TestKind: Int, CaseIterable, Codable, Sendable {
    case calibration = 0, fitts, passThrough, swipe, comparison
    public var title: String {
        switch self {
        case .calibration: return "Test 0 · 悬停校准"
        case .fitts: return "Test 1 · 悬空指向"
        case .passThrough: return "Test 2 · 悬空经过"
        case .swipe: return "Test 3 · 滑动准备"
        case .comparison: return "Test 4 · 直接点击 / 悬空指向"
        }
    }
}
public struct ExperimentConfig: Codable, Equatable, Sendable {
    public var distances: [Double] = [120, 220, 320]
    public var diameters: [Double] = [30, 50, 80]
    public var repetitions = 8
    public var calibrationRepetitions = 5
    public var passRepetitions = 8
    public var swipeRepetitions = 12
    public var startStableMs: Double = 300
    public var calibrationHoldMs: Double = 1000
    public var instructionMs: Double = 800
    public var interTrialMs: Double = 400
    public var timeoutMs: Double = 15000
    public var swipeStartThreshold: Double = 10
    public var swipeCompletionDistance: Double = 80
    public init() {}
    public func validate() throws {
        guard !distances.isEmpty, !diameters.isEmpty,
              distances.allSatisfy({ $0.isFinite && $0 > 0 }),
              diameters.allSatisfy({ $0.isFinite && $0 >= 10 && $0 <= 160 }),
              repetitions >= 2, repetitions <= 40, repetitions.isMultiple(of: 2),
              (1...40).contains(calibrationRepetitions), (2...40).contains(passRepetitions), passRepetitions.isMultiple(of: 2),
              (1...100).contains(swipeRepetitions),
              [startStableMs, calibrationHoldMs, instructionMs, interTrialMs, timeoutMs, swipeStartThreshold, swipeCompletionDistance].allSatisfy({ $0.isFinite && $0 > 0 }),
              timeoutMs > calibrationHoldMs, swipeCompletionDistance > swipeStartThreshold,
              distances.allSatisfy({ d in diameters.allSatisfy({ w in Geometry.contains(Point(195, 415 - d), radius: w / 2) && Geometry.contains(Point(195, 415 + d), radius: w / 2) && d > 32 + w / 2 }) })
        else { throw StudyError.invalidConfig }
    }
}
public enum StudyError: LocalizedError {
    case invalidConfig, invalidParticipant, schemaMismatch, storage(String), exportFailure(String)
    public var errorDescription: String? {
        switch self {
        case .invalidConfig: return "配置无法运行：检查距离、目标边界、正数时长；指向和经过重复次数须为偶数。"
        case .invalidParticipant: return "参与者编号请使用 1–32 位字母、数字、下划线或短横线，例如 P01。"
        case .schemaMismatch: return "现有 CSV 表头与当前版本不一致。请先导出已有数据，再使用相同版本继续采集。"
        case .storage(let message): return "保存失败：\(message)。请点击重试保存；仍失败时保留原数据并检查文件。"
        case .exportFailure(let message): return "导出失败：\(message)。原数据保留，可重试导出。"
        }
    }
}
public struct TrialCondition: Codable, Equatable, Sendable {
    public var conditionID: String
    public var instruction: String
    public var start: Point
    public var target: Point
    public var end: Point?
    public var diameter: Double
    public var distance: Double
    public var direction: String
    public var mode: String
    public var fittsID: Double { distance > 0 ? log2(1 + distance / diameter) : 0 }
}
public struct SeededRandom: RandomNumberGenerator {
    private var state: UInt64
    public init(seed: UInt64) { state = seed }
    public mutating func next() -> UInt64 {
        state &+= 0x9e3779b97f4a7c15
        var z = state
        z = (z ^ (z >> 30)) &* 0xbf58476d1ce4e5b9
        z = (z ^ (z >> 27)) &* 0x94d049bb133111eb
        return z ^ (z >> 31)
    }
}
public enum TrialRandomizer {
    public static func make(test: TestKind, config c: ExperimentConfig, seed: UInt64) throws -> [TrialCondition] {
        try c.validate()
        var items: [TrialCondition] = []
        switch test {
        case .fitts, .comparison:
            for mode in (test == .comparison ? ["TAP", "HOVER"] : ["HOVER"]) {
                for a in c.distances { for w in c.diameters { for r in 0..<c.repetitions {
                    let sign = r.isMultiple(of: 2) ? -1.0 : 1.0
                    let direction = sign < 0 ? "UP" : "DOWN"
                    items.append(TrialCondition(conditionID: "\(mode)_A\(a)_W\(w)_\(direction)", instruction: mode == "TAP" ? "目标出现后，自然地直接点击" : "先悬空指准目标，再点击", start: Geometry.center, target: Point(195, 415 + sign * a), diameter: w, distance: a, direction: direction, mode: mode))
                } } }
            }
        case .calibration:
            for (name, point) in [("左侧", Point(75,415)), ("右侧", Point(315,415)), ("上方", Point(195,295)), ("下方", Point(195,535))] {
                for _ in 0..<c.calibrationRepetitions {
                    items.append(TrialCondition(conditionID: "CAL_\(name)", instruction: "从\(name)靠近目标，悬空保持稳定，不要触屏", start: point, target: Geometry.center, diameter: 50, distance: 120, direction: name, mode: "CALIBRATION"))
                }
            }
        case .passThrough:
            for speed in ["慢速", "自然速度", "快速"] {
                for r in 0..<c.passRepetitions {
                    let up = r.isMultiple(of: 2)
                    items.append(TrialCondition(conditionID: "PASS_\(speed)_\(up ? "UP" : "DOWN")", instruction: "\(speed)悬空经过中间目标，到达终点，不要触屏", start: Point(195, up ? 700 : 130), target: Geometry.center, end: Point(195, up ? 130 : 700), diameter: 60, distance: 285, direction: up ? "UP" : "DOWN", mode: speed))
                }
            }
        case .swipe:
            for _ in 0..<c.swipeRepetitions {
                items.append(TrialCondition(conditionID: "SWIPE_UP", instruction: "接触页面后，向上滑动", start: Point(195,650), target: Point(195,650), diameter: 80, distance: 0, direction: "UP", mode: "SWIPE"))
            }
        }
        var rng = SeededRandom(seed: seed)
        return items.shuffled(using: &rng)
    }
}
public enum TrialState: String, Codable, Sendable {
    case idle = "IDLE", waitForStart = "WAIT_FOR_START", startStable = "START_STABLE", instruction = "INSTRUCTION", targetPresented = "TARGET_PRESENTED", movement = "MOVEMENT", action = "ACTION", success = "SUCCESS", fail = "FAIL", interTrial = "INTER_TRIAL_DELAY", paused = "PAUSED", ended = "ENDED"
    public var hint: String {
        switch self {
        case .idle: return "选择实验，核对配置后开始"
        case .waitForStart, .startStable: return "请在起点保持稳定"
        case .instruction: return "请看任务提示，等待目标出现"
        case .targetPresented, .movement: return "请操作目标"
        case .action: return "正在记录接触操作"
        case .success, .fail, .interTrial: return "已记录，准备下一次"
        case .paused: return "已暂停"
        case .ended: return "本组结束"
        }
    }
}
public struct InputSample: Sendable {
    public var time: Double
    public var receivedTime: Double
    public var point: Point
    public var source: String
    public var inputType: String
    public var phase: String
    public var z: Double?
    public var altitude: Double?
    public var azimuth: Double?
    public var azimuthX: Double?
    public var azimuthY: Double?
    public var roll: Double?
    public var touchID: String?
    public init(time: Double, receivedTime: Double? = nil, point: Point, source: String = "PENCIL_HOVER", inputType: String = "PENCIL", phase: String = "CHANGED", z: Double? = nil, altitude: Double? = nil, azimuth: Double? = nil, azimuthX: Double? = nil, azimuthY: Double? = nil, roll: Double? = nil, touchID: String? = nil) {
        self.time = time; self.receivedTime = receivedTime ?? time; self.point = point; self.source = source; self.inputType = inputType; self.phase = phase; self.z = z; self.altitude = altitude; self.azimuth = azimuth; self.azimuthX = azimuthX; self.azimuthY = azimuthY; self.roll = roll; self.touchID = touchID
    }
    public var isHover: Bool { source.contains("HOVER") }
    public var isSynthetic: Bool { source.hasPrefix("SIMULATED") }
}
public struct StudyEvent: Sendable {
    public init(type: String, time: Double, state: TrialState, success: Bool? = nil, error: String? = nil, metadata: [String: String] = [:]) {
        self.type = type; self.time = time; self.state = state; self.success = success; self.error = error; self.metadata = metadata
    }
    public var type: String
    public var time: Double
    public var state: TrialState
    public var success: Bool?
    public var error: String?
    public var metadata: [String: String]
}
public struct TrialOutcome: Codable, Equatable, Sendable {
    public var plannedIndex: Int
    public var trialID: String
    public var success: Bool
    public var error: String?
    public var isRepeat: Bool
}
public struct Checkpoint: Codable {
    public var participant: String
    public var sessionID: String
    public var test: TestKind
    public var config: ExperimentConfig
    public var seed: UInt64
    public var schedule: [TrialCondition]
    public var index: Int
    public var attempt: Int
    public var trialID: String
    public var outcomes: [TrialOutcome]
    public var isRepeat: Bool
    public var interrupted: Bool
    public var synthetic: Bool
}
