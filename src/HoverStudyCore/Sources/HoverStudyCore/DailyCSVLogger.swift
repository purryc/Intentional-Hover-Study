import Foundation

public struct CSVRow: Sendable {
    public var fields: [String: String]
    public var date: Date
    public init(_ fields: [String: String], date: Date = Date()) { self.fields = fields; self.date = date }
}
public struct LoggerStats: Sendable, Equatable {
    public init() {}
    public var receivedRecords: Int = 0
    public var writtenRecords: Int = 0
    public var writtenSamples: Int = 0
    public var writtenTrials: Int = 0
    public var pendingRecords: Int = 0
    public var currentFile: String = ""
    public var error: String?
}
public final class DailyCSVLogger: @unchecked Sendable {
    public static let columns = ["schemaVersion", "sequence", "recordType", "date", "timestamp", "monotonicTime", "receivedMonotonicTime", "timestampSource", "elapsedTimeMs", "participantID", "sessionID", "testID", "trialID", "plannedIndex", "plannedTotal", "remainingAfterCurrent", "isRepeat", "taskInstruction", "conditionID", "trialState", "x", "y", "localX", "localY", "zOffset", "hoverState", "inputType", "sampleSource", "altitudeAngle", "azimuthAngle", "azimuthVectorX", "azimuthVectorY", "rollAngle", "vx", "vy", "speed", "acceleration", "targetID", "targetX", "targetY", "targetWidth", "targetHeight", "distanceA", "targetWidthW", "fittsID", "distanceToTarget", "radialVelocity", "headingError", "touchState", "touchX", "touchY", "eventType", "success", "errorType", "randomSeed", "metadata"]
    public static let header = columns.joined(separator: ",") + "\n"
    public let directory: URL
    public let synthetic: Bool
    public var onError: (@Sendable (String) -> Void)?
    private let queue = DispatchQueue(label: "HoverStudy.CSV", qos: .userInitiated)
    private var timer: DispatchSourceTimer?
    private var stats = LoggerStats()
    private var handles: [String: FileHandle] = [:]
    private var sequences: [String: Int] = [:]
    private var buffers: [String: [(line: String, type: String, event: String)]] = [:]
    private var dailyRecords: [String: Int] = [:]
    private var dailySamples: [String: Int] = [:]
    private var dailyTrials: [String: Int] = [:]
    private let writeBatch: @Sendable (FileHandle, Data) throws -> Void
    private let dateFormatter: DateFormatter
    private let timestampFormatter: ISO8601DateFormatter
    public init(directory: URL, synthetic: Bool = false, writeBatch: @escaping @Sendable (FileHandle, Data) throws -> Void = { try $0.write(contentsOf: $1) }) throws {
        self.directory = directory; self.synthetic = synthetic
        self.writeBatch = writeBatch
        dateFormatter = DateFormatter(); dateFormatter.locale = Locale(identifier: "en_US_POSIX"); dateFormatter.timeZone = .current; dateFormatter.dateFormat = "yyyy-MM-dd"
        timestampFormatter = ISO8601DateFormatter(); timestampFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]; timestampFormatter.timeZone = .current
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        // Validate/create today's file before allowing any experiment to start.
        try queue.sync { _ = try open(day: day(Date())) }
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now() + .milliseconds(250), repeating: .milliseconds(250))
        timer.setEventHandler { [weak self] in
            guard let self, self.stats.error == nil else { return }
            do { try self.flushUnsafe() } catch { self.report(error) }
        }
        self.timer = timer; timer.resume()
    }
    deinit { timer?.cancel(); for handle in handles.values { try? handle.close() } }
    private func day(_ date: Date) -> String { dateFormatter.string(from: date) }
    private func filename(_ day: String) -> String { "\(synthetic ? "SIMULATED_" : "")HoverIntent_\(day).csv" }
    public static func escape(_ value: String) -> String {
        // One physical line per record allows deterministic partial-tail recovery.
        let v = value.replacingOccurrences(of: "\r", with: "\\r").replacingOccurrences(of: "\n", with: "\\n")
        if v.contains(",") || v.contains("\"") { return "\"" + v.replacingOccurrences(of: "\"", with: "\"\"") + "\"" }
        return v
    }
    private func encode(_ fields: [String: String]) -> String { Self.columns.map { Self.escape(fields[$0] ?? "") }.joined(separator: ",") + "\n" }
    public static func decodeLine(_ line: String) throws -> [String: String] {
        let chars = Array(line); var values: [String] = []; var current = ""; var quoted = false; var i = 0
        while i < chars.count {
            let ch = chars[i]
            if ch == "\"" {
                if quoted && i + 1 < chars.count && chars[i + 1] == "\"" { current.append("\""); i += 1 }
                else { quoted.toggle() }
            } else if ch == "," && !quoted { values.append(current); current = "" }
            else { current.append(ch) }
            i += 1
        }
        values.append(current)
        guard !quoted && values.count == columns.count else { throw StudyError.storage("已有 CSV 存在损坏的完整行，请先在 Finder 取出原文件检查。") }
        return Dictionary(uniqueKeysWithValues: zip(columns, values))
    }
    private static func scanExisting(_ data: Data, afterHeader headerLength: Int) throws -> (records: Int, samples: Int, trials: Int, sequence: Int) {
        let sample = Array("SAMPLE".utf8), event = Array("EVENT".utf8), trialEnd = Array("TRIAL_END".utf8)
        let eventColumn = columns.firstIndex(of: "eventType")!
        return try data.withUnsafeBytes { raw in
            let bytes = raw.bindMemory(to: UInt8.self)
            func matches(_ start: Int, _ end: Int, _ value: [UInt8]) -> Bool {
                guard end - start == value.count else { return false }
                for offset in value.indices where bytes[start + offset] != value[offset] { return false }
                return true
            }
            var records = 0, samples = 0, trials = 0, maxSequence = 0
            var rowStart = headerLength
            while rowStart < bytes.count {
                var field = 0, fieldStart = rowStart, position = rowStart
                var quoted = false, sequence = 0, isSample = false, isEvent = false, isTrialEnd = false
                while position < bytes.count {
                    let byte = bytes[position]
                    if byte == 34 {
                        if quoted && position + 1 < bytes.count && bytes[position + 1] == 34 {
                            position += 2
                            continue
                        }
                        quoted.toggle()
                    } else if (byte == 44 && !quoted) || byte == 10 {
                        if field == 1 {
                            guard fieldStart < position else { throw StudyError.storage("CSV 记录序号或记录类型损坏，请保留原文件后检查。") }
                            for index in fieldStart..<position {
                                let digit = bytes[index]
                                guard digit >= 48 && digit <= 57,
                                    sequence <= (Int.max - Int(digit - 48)) / 10 else {
                                    throw StudyError.storage("CSV 记录序号或记录类型损坏，请保留原文件后检查。")
                                }
                                sequence = sequence * 10 + Int(digit - 48)
                            }
                        } else if field == 2 {
                            isSample = matches(fieldStart, position, sample)
                            isEvent = matches(fieldStart, position, event)
                        } else if field == eventColumn {
                            isTrialEnd = matches(fieldStart, position, trialEnd)
                        }
                        field += 1
                        fieldStart = position + 1
                        if byte == 10 { break }
                    }
                    position += 1
                }
                if position < bytes.count && String(bytes: bytes[rowStart..<position], encoding: .utf8) == nil {
                    throw StudyError.storage("CSV 存在无效 UTF-8 字节，请保留原文件后检查。")
                }
                guard position < bytes.count, !quoted, field == columns.count else {
                    throw StudyError.storage("已有 CSV 存在损坏的完整行，请先在 Finder 取出原文件检查。")
                }
                guard sequence > maxSequence, isSample || isEvent else {
                    throw StudyError.storage("CSV 记录序号或记录类型损坏，请保留原文件后检查。")
                }
                maxSequence = sequence
                records += 1
                if isSample { samples += 1 }
                if isTrialEnd { trials += 1 }
                rowStart = position + 1
            }
            return (records, samples, trials, maxSequence)
        }
    }
    private func open(day: String) throws -> FileHandle {
        if let handle = handles[day] { stats.currentFile = filename(day); return handle }
        let url = directory.appendingPathComponent(filename(day))
        let fm = FileManager.default
        if !fm.fileExists(atPath: url.path) { try Data(Self.header.utf8).write(to: url, options: .atomic) }
        var data = try Data(contentsOf: url, options: .mappedIfSafe)
        let header = Data(Self.header.utf8)
        guard data.starts(with: header) else { throw StudyError.schemaMismatch }
        var tail: Data?
        if data.last != 10 {
            guard let last = data.lastIndex(of: 10) else { throw StudyError.schemaMismatch }
            tail = Data(data[(last + 1)..<data.count])
            let tailURL = directory.appendingPathComponent("\(filename(day)).partial-\(UUID().uuidString).bin")
            try tail!.write(to: tailURL, options: .atomic)
            data = Data() // Release the mapping before truncating the incomplete tail.
            let repair = try FileHandle(forWritingTo: url)
            try repair.truncate(atOffset: UInt64(last + 1)); try repair.synchronize(); try repair.close()
            data = try Data(contentsOf: url, options: .mappedIfSafe)
        }
        let existing = try Self.scanExisting(data, afterHeader: header.count)
        dailyRecords[day] = existing.records
        dailySamples[day] = existing.samples; dailyTrials[day] = existing.trials
        stats.writtenSamples += existing.samples; stats.writtenTrials += existing.trials
        stats.writtenRecords += existing.records
        sequences[day] = existing.sequence
        let handle = try FileHandle(forWritingTo: url); try handle.seekToEnd(); handles[day] = handle; stats.currentFile = filename(day)
        if let tail {
            sequences[day] = existing.sequence + 1
            let recovery = encode(["schemaVersion": "1", "sequence": String(existing.sequence + 1), "recordType": "EVENT", "date": day, "timestamp": timestampFormatter.string(from: Date()), "eventType": "CSV_TAIL_RECOVERED", "sampleSource": synthetic ? "SIMULATED_SYSTEM" : "SYSTEM", "metadata": "{\"quarantinedBytes\":\(tail.count)}"])
            try handle.write(contentsOf: Data(recovery.utf8)); try handle.synchronize(); stats.writtenRecords += 1; dailyRecords[day, default: 0] += 1
        }
        return handle
    }
    public func append(_ row: CSVRow) {
        queue.async { [self] in
            stats.receivedRecords += 1
            if !deferredRows.isEmpty { deferredRows.append(row); stats.pendingRecords += 1; return }
            do {
                let d = day(row.date); _ = try open(day: d)
                sequences[d, default: 0] += 1
                var fields = row.fields
                fields["schemaVersion"] = "1"; fields["sequence"] = String(sequences[d]!); fields["date"] = d
                fields["timestamp"] = timestampFormatter.string(from: row.date)
                buffers[d, default: []].append((encode(fields), fields["recordType"] ?? "", fields["eventType"] ?? ""))
                stats.pendingRecords += 1
            } catch {
                // Preserve the unencoded row until a retry can open its day file.
                deferredRows.append(row); stats.pendingRecords += 1; report(error)
            }
        }
    }
    private var deferredRows: [CSVRow] = []
    private func report(_ error: Error) {
        let message = error.localizedDescription
        if stats.error != message { stats.error = message; onError?(message) }
    }
    private func flushUnsafe() throws {
        for d in buffers.keys.sorted() {
            guard let rows = buffers[d], !rows.isEmpty else { continue }
            let handle = try open(day: d)
            let offset = try handle.seekToEnd()
            do {
                try writeBatch(handle, Data(rows.map(\.line).joined().utf8)); try handle.synchronize()
            } catch {
                // Roll back only this unconfirmed batch; it remains buffered for retry.
                do {
                    let url = directory.appendingPathComponent(filename(d))
                    let persisted = try Data(contentsOf: url)
                    if persisted.count > Int(offset) { try persisted.suffix(from: Int(offset)).write(to: directory.appendingPathComponent("failed-batch-\(UUID().uuidString).bin")) }
                    try handle.truncate(atOffset: offset); try handle.seek(toOffset: offset)
                } catch { throw StudyError.storage("无法恢复未确认的写入批次，请重新打开应用并检查隔离文件：\(error.localizedDescription)") }
                throw error
            }
            stats.writtenRecords += rows.count; stats.writtenSamples += rows.filter { $0.type == "SAMPLE" }.count; stats.writtenTrials += rows.filter { $0.event == "TRIAL_END" }.count
            dailyRecords[d, default: 0] += rows.count
            dailySamples[d, default: 0] += rows.filter { $0.type == "SAMPLE" }.count
            dailyTrials[d, default: 0] += rows.filter { $0.event == "TRIAL_END" }.count
            stats.pendingRecords -= rows.count; buffers[d] = []
        }
    }
    public func flush() throws {
        try queue.sync {
            do { try flushUnsafe() } catch { report(error); throw error }
        }
    }
    public func retry() throws {
        try queue.sync {
            do {
                while let row = deferredRows.first {
                    let d = day(row.date); _ = try open(day: d); sequences[d, default: 0] += 1
                    var f = row.fields; f["schemaVersion"] = "1"; f["sequence"] = String(sequences[d]!); f["date"] = d; f["timestamp"] = timestampFormatter.string(from: row.date)
                    buffers[d, default: []].append((encode(f), f["recordType"] ?? "", f["eventType"] ?? "")); deferredRows.removeFirst()
                }
                try flushUnsafe(); stats.error = nil
            } catch { report(error); throw error }
        }
    }
    private func snapshotUnsafe() -> LoggerStats {
        var result = stats
        let today = day(Date())
        result.currentFile = filename(today)
        result.writtenRecords = dailyRecords[today, default: 0]
        result.writtenSamples = dailySamples[today, default: 0]
        result.writtenTrials = dailyTrials[today, default: 0]
        return result
    }
    public func snapshot() -> LoggerStats { queue.sync { snapshotUnsafe() } }
    public func requestSnapshot(_ completion: @escaping @Sendable (LoggerStats) -> Void) {
        queue.async { [self] in completion(snapshotUnsafe()) }
    }
    public func files() -> [URL] {
        queue.sync { ((try? FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)) ?? []).filter { $0.pathExtension == "csv" }.sorted { $0.lastPathComponent > $1.lastPathComponent } }
    }
    /// Reconcile a stale experiment checkpoint with the authoritative persisted journal.
    public func persistedOutcome(trialID: String) throws -> TrialOutcome? {
        try queue.sync {
            let files = try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil).filter { $0.pathExtension == "csv" }.sorted { $0.lastPathComponent > $1.lastPathComponent }
            let needle = Data(trialID.utf8), trialEnd = Data("TRIAL_END".utf8)
            for file in files {
                let content = try Data(contentsOf: file, options: .mappedIfSafe)
                var searchEnd = content.count
                // Search backward without decoding an entire multi-hundred-MB journal.
                while let match = content.range(of: needle, options: .backwards, in: 0..<searchEnd) {
                    let lineStart = content[..<match.lowerBound].lastIndex(of: 10).map { $0 + 1 } ?? 0
                    let lineEnd = content[match.upperBound...].firstIndex(of: 10) ?? content.count
                    let line = content.subdata(in: lineStart..<lineEnd)
                    if line.range(of: trialEnd) != nil {
                        guard let text = String(data: line, encoding: .utf8) else {
                            throw StudyError.storage("CSV 存在无效 UTF-8 字节，请保留原文件后检查。")
                        }
                        let r = try Self.decodeLine(text)
                    if r["trialID"] == trialID && r["eventType"] == "TRIAL_END", let index = Int(r["plannedIndex"] ?? "") {
                        let error = r["errorType"] ?? ""
                        return TrialOutcome(plannedIndex: index, trialID: trialID, success: r["success"] == "true", error: error.isEmpty ? nil : error, isRepeat: r["isRepeat"] == "true")
                    }
                    }
                    if lineStart == 0 { break }
                    searchEnd = lineStart
                }
            }
            return nil
        }
    }
    public func export(file: URL? = nil, to destination: URL) throws -> URL {
        try queue.sync {
            // A source journal write failure must still stop acquisition.
            do { try flushUnsafe() } catch { report(error); throw error }
            do {
                let source = (file ?? directory.appendingPathComponent(filename(day(Date())))).standardizedFileURL.resolvingSymlinksInPath()
                let root = directory.standardizedFileURL.resolvingSymlinksInPath()
                // Compare filesystem paths: URL equality also compares directory slash semantics.
                guard source.deletingLastPathComponent().path == root.path, source.pathExtension == "csv" else { throw StudyError.exportFailure("所选文件不属于当前数据目录，请重新选择历史文件") }
                let copy = destination.appendingPathComponent(source.lastPathComponent)
                guard copy.standardizedFileURL.resolvingSymlinksInPath().path != source.path else { throw StudyError.exportFailure("快照不能覆盖原数据文件，请选择其他导出位置") }
                try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
                try Data(contentsOf: source).write(to: copy, options: .atomic)
                return copy
            } catch let error as StudyError { throw error }
            catch { throw StudyError.exportFailure(error.localizedDescription) }
        }
    }
}
