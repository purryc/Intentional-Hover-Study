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
    private func open(day: String) throws -> FileHandle {
        if let handle = handles[day] { stats.currentFile = filename(day); return handle }
        let url = directory.appendingPathComponent(filename(day))
        let fm = FileManager.default
        if !fm.fileExists(atPath: url.path) { try Data(Self.header.utf8).write(to: url, options: .atomic) }
        var data = try Data(contentsOf: url)
        let header = Data(Self.header.utf8)
        guard data.starts(with: header) else { throw StudyError.schemaMismatch }
        var tail: Data?
        if data.last != 10 {
            guard let last = data.lastIndex(of: 10) else { throw StudyError.schemaMismatch }
            tail = data.subdata(in: (last + 1)..<data.count)
            let tailURL = directory.appendingPathComponent("\(filename(day)).partial-\(UUID().uuidString).bin")
            try tail!.write(to: tailURL, options: .atomic)
            let repair = try FileHandle(forWritingTo: url)
            try repair.truncate(atOffset: UInt64(last + 1)); try repair.synchronize(); try repair.close()
            data = data.prefix(last + 1)
        }
        guard let content = String(data: data, encoding: .utf8) else { throw StudyError.storage("CSV 存在无效 UTF-8 字节，请保留原文件后检查。") }
        let lines = content.split(separator: "\n").dropFirst()
        var maxSequence = 0
        var sampleRows = 0, trialRows = 0
        for line in lines {
            let row = try Self.decodeLine(String(line))
            guard let seq = Int(row["sequence"] ?? ""), seq > maxSequence, ["SAMPLE", "EVENT"].contains(row["recordType"] ?? "") else { throw StudyError.storage("CSV 记录序号或记录类型损坏，请保留原文件后检查。") }
            maxSequence = seq
            if row["recordType"] == "SAMPLE" { sampleRows += 1 }
            if row["eventType"] == "TRIAL_END" { trialRows += 1 }
        }
        dailyRecords[day] = lines.count
        dailySamples[day] = sampleRows; dailyTrials[day] = trialRows
        stats.writtenSamples += sampleRows; stats.writtenTrials += trialRows
        stats.writtenRecords += lines.count
        sequences[day] = maxSequence
        let handle = try FileHandle(forWritingTo: url); try handle.seekToEnd(); handles[day] = handle; stats.currentFile = filename(day)
        if let tail {
            sequences[day] = maxSequence + 1
            let recovery = encode(["schemaVersion": "1", "sequence": String(maxSequence + 1), "recordType": "EVENT", "date": day, "timestamp": timestampFormatter.string(from: Date()), "eventType": "CSV_TAIL_RECOVERED", "sampleSource": synthetic ? "SIMULATED_SYSTEM" : "SYSTEM", "metadata": "{\"quarantinedBytes\":\(tail.count)}"])
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
            for file in files {
                let content = try String(contentsOf: file, encoding: .utf8)
                // A UUID cannot contain CSV punctuation; skip decoding unrelated journals/rows.
                guard content.contains(trialID) else { continue }
                for line in content.split(separator: "\n").dropFirst().reversed() where line.contains(trialID) && line.contains("TRIAL_END") {
                    let r = try Self.decodeLine(String(line))
                    if r["trialID"] == trialID && r["eventType"] == "TRIAL_END", let index = Int(r["plannedIndex"] ?? "") {
                        let error = r["errorType"] ?? ""
                        return TrialOutcome(plannedIndex: index, trialID: trialID, success: r["success"] == "true", error: error.isEmpty ? nil : error, isRepeat: r["isRepeat"] == "true")
                    }
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
