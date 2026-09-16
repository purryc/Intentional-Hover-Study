import XCTest
@testable import HoverStudyCore

final class StudyCoreTests: XCTestCase {
    func engine(_ kind: TestKind = .fitts, config: ExperimentConfig = ExperimentConfig()) throws -> ExperimentEngine {
        let e = ExperimentEngine(); try e.start(participant:"P01",test:kind,config:config,seed:42,time:100); return e
    }
    func sample(_ p: Point, time: Double, hover: Bool = true, phase: String = "CHANGED", input: String = "PENCIL") -> InputSample {
        InputSample(time:time,point:Geometry.global(p),source:hover ? "PENCIL_HOVER" : "PENCIL_TOUCH",inputType:input,phase:phase,z:hover ? 0.5 : nil)
    }
    func present(_ e: ExperimentEngine) {
        e.ingest(sample(e.current!.start,time:100)); e.tick(time:100.301)
        if e.test == .comparison { e.tick(time:101.102) }
    }
    func select(_ e: ExperimentEngine, time: Double = 102) {
        let p = e.current!.target
        e.ingest(sample(p,time:time,hover:false,phase:"BEGAN")); e.ingest(sample(p,time:time+0.01,hover:false,phase:"ENDED"))
    }
    func testDefaultSchedulesAndReproducibility() throws {
        let c = ExperimentConfig()
        for (test,count) in [(TestKind.calibration,20),(.fitts,72),(.passThrough,24),(.swipe,12),(.comparison,144)] {
            let a = try TrialRandomizer.make(test:test,config:c,seed:12)
            XCTAssertEqual(a.count,count); XCTAssertEqual(a,try TrialRandomizer.make(test:test,config:c,seed:12))
            XCTAssertTrue(a.allSatisfy{Geometry.contains($0.target,radius:$0.diameter/2)})
        }
        let trials = try TrialRandomizer.make(test:.comparison,config:c,seed:19)
        for d in c.distances { for w in c.diameters { for dir in ["UP","DOWN"] {
            XCTAssertEqual(trials.filter{$0.distance == d && $0.diameter == w && $0.direction == dir && $0.mode == "TAP"}.count,4)
            XCTAssertEqual(trials.filter{$0.distance == d && $0.diameter == w && $0.direction == dir && $0.mode == "HOVER"}.count,4)
        } } }
    }
    func testConfigRejectsImpossibleGeometryAndOddRepetitions() {
        var c = ExperimentConfig(); c.distances = [400]; XCTAssertThrowsError(try c.validate())
        c = ExperimentConfig(); c.repetitions = 3; XCTAssertThrowsError(try c.validate())
        c = ExperimentConfig(); c.timeoutMs = -.infinity; XCTAssertThrowsError(try c.validate())
    }
    func testStartStabilityResetsWhenLeaving() throws {
        let e = try engine(); let p = e.current!.start
        e.ingest(sample(p,time:100)); e.tick(time:100.2); XCTAssertNil(e.targetTime)
        e.ingest(sample(Point(20,20),time:100.21)); e.tick(time:100.7); XCTAssertNil(e.targetTime)
        e.ingest(sample(p,time:100.71)); e.tick(time:101.011); XCTAssertNotNil(e.targetTime)
    }
    func testNoDwellForSelectionAndTouchGroundTruth() throws {
        let e = try engine(.comparison); var events:[StudyEvent] = []; e.onEvent = {events.append($0)}
        present(e); XCTAssertEqual(e.state,.targetPresented)
        select(e,time:101.11); XCTAssertEqual(e.state,.success); XCTAssertTrue(e.outcomes.last!.success)
        XCTAssertTrue(events.contains{$0.type == "TOUCH_DOWN"}); XCTAssertTrue(events.contains{$0.type == "TOUCH_UP"})
        XCTAssertEqual(e.plannedNumber,1); XCTAssertEqual(e.remaining,143)
        e.tick(time:101.6); XCTAssertEqual(e.plannedNumber,2); XCTAssertEqual(e.remaining,142)
    }
    func testPassThroughNeedsCrossingAndEndWithoutTouch() throws {
        let e = try engine(.passThrough); present(e); let c = e.current!
        e.ingest(sample(c.end!,time:101)); XCTAssertNotEqual(e.state,.success)
        e.ingest(sample(c.target,time:101.1)); e.ingest(sample(c.end!,time:101.2)); XCTAssertEqual(e.state,.success)
        let bad = try engine(.passThrough);present(bad);select(bad);XCTAssertEqual(bad.outcomes.last?.error,"UNEXPECTED_TOUCH")
    }
    func testCalibrationCollectsHoldWithoutClick() throws {
        let e = try engine(.calibration); present(e);let p=e.current!.target
        e.ingest(sample(p,time:101));e.tick(time:101.9);XCTAssertNotEqual(e.state,.success)
        e.tick(time:102.01);XCTAssertEqual(e.state,.success)
    }
    func testSwipeRequiresDistanceDirectionAndLift() throws {
        let e = try engine(.swipe);present(e);let p=e.current!.target
        e.ingest(sample(p,time:101,hover:false,phase:"BEGAN"));e.ingest(sample(Point(p.x,p.y-90),time:101.1,hover:false,phase:"MOVED"));XCTAssertEqual(e.state,.action)
        e.ingest(sample(Point(p.x,p.y-90),time:101.2,hover:false,phase:"ENDED"));XCTAssertEqual(e.state,.success)
        let bad = try engine(.swipe);present(bad);let b=bad.current!.target
        bad.ingest(sample(b,time:101,hover:false,phase:"BEGAN"));bad.ingest(sample(Point(b.x+90,b.y),time:101.1,hover:false,phase:"MOVED"));bad.ingest(sample(Point(b.x+90,b.y),time:101.2,hover:false,phase:"ENDED"));XCTAssertEqual(bad.outcomes.last?.error,"INVALID_SWIPE")
    }
    func testHoverEndContactGraceAndTimeout() throws {
        let e = try engine();present(e);let p=e.current!.target
        e.ingest(sample(p,time:101,phase:"ENDED"));e.tick(time:101.1);XCTAssertNotEqual(e.state,.fail)
        select(e,time:101.2);XCTAssertEqual(e.state,.success)
        let lost = try engine();present(lost);lost.ingest(sample(p,time:101,phase:"ENDED"));lost.tick(time:101.51);XCTAssertEqual(lost.outcomes.last?.error,"TRACKING_INTERRUPTED")
        let timeout=try engine();present(timeout);timeout.tick(time:116);XCTAssertEqual(timeout.outcomes.last?.error,"TIMEOUT")
    }
    func testFailureSkipRepeatAndPauseProgress() throws {
        let e=try engine();present(e)
        e.ingest(sample(Point(10,10),time:101,hover:false,phase:"BEGAN"));e.ingest(sample(Point(10,10),time:101.1,hover:false,phase:"ENDED"));XCTAssertEqual(e.outcomes.last?.error,"MISSED_TARGET")
        e.repeatTrial(time:101.2);XCTAssertEqual(e.plannedNumber,1);XCTAssertTrue(e.isRepeat);XCTAssertTrue(e.progress.contains("重做"))
        e.skip(time:101.3);e.tick(time:101.8);XCTAssertEqual(e.plannedNumber,2);XCTAssertFalse(e.isRepeat)
        e.pause(time:102);XCTAssertEqual(e.state,.paused);let old=e.trialID
        e.resume(time:103);XCTAssertEqual(e.plannedNumber,2);XCTAssertNotEqual(e.trialID,old);XCTAssertTrue(e.isRepeat)
    }
    func testOutOfBoundsEarlyTouchFingerAndSyntheticSeparation() throws {
        let early=try engine();select(early,time:100.1);XCTAssertEqual(early.outcomes.last?.error,"EARLY_TOUCH")
        let bounds=try engine();present(bounds);bounds.ingest(sample(Point(-1,415),time:101));XCTAssertEqual(bounds.outcomes.last?.error,"OUT_OF_BOUNDS")
        let finger=try engine();present(finger);finger.ingest(sample(finger.current!.target,time:101,hover:false,phase:"BEGAN",input:"FINGER"));XCTAssertEqual(finger.outcomes.last?.error,"UNEXPECTED_INPUT")
        let real=try engine();let s=InputSample(time:100,point:Geometry.global(real.current!.start),source:"SIMULATED_HOVER");real.ingest(s);XCTAssertEqual(real.state,.waitForStart)
    }
    func testCheckpointRecoveryRetainsInterruptedTrial() throws {
        let e=try engine();var checkpoint:Checkpoint?;e.onCheckpoint={checkpoint=$0};present(e)
        let restored=ExperimentEngine();var ev:[StudyEvent]=[];restored.onEvent={ev.append($0)};restored.restore(checkpoint!,time:200)
        XCTAssertEqual(restored.state,.paused);XCTAssertEqual(restored.outcomes.last?.error,"APP_INTERRUPTED")
        restored.resume(time:201);XCTAssertTrue(restored.isRepeat);XCTAssertEqual(restored.plannedNumber,1);XCTAssertTrue(ev.contains{$0.type == "SESSION_RECOVERED"})
    }
    func testFinalProgressAndPauseAtCompletedTrialAdvance() throws {
        var c=ExperimentConfig();c.swipeRepetitions=1
        let e=try engine(.swipe,config:c);e.skip(time:101);e.pause(time:101.1);e.resume(time:102)
        XCTAssertEqual(e.state,.ended);XCTAssertEqual(e.remaining,0);XCTAssertTrue(e.progress.contains("本组结束"))
        e.repeatTrial(time:103);XCTAssertEqual(e.plannedNumber,1);XCTAssertTrue(e.isRepeat)
    }
    func temp() throws -> URL { let u=FileManager.default.temporaryDirectory.appendingPathComponent("HoverQA-\(UUID().uuidString)");try FileManager.default.createDirectory(at:u,withIntermediateDirectories:true);addTeardownBlock{try? FileManager.default.removeItem(at:u)};return u }
    func testCSVAppendReopenEscapeExportAndSequence() throws {
        let root=try temp();var log:DailyCSVLogger?=try DailyCSVLogger(directory:root,synthetic:true)
        for i in 0..<1000 {log!.append(CSVRow(["recordType":"SAMPLE","participantID":"P01","taskInstruction":"中文, \"指向\"\n换行","monotonicTime":String(i),"sampleSource":"SIMULATED_HOVER"]))}
        try log!.flush();XCTAssertEqual(log!.snapshot().pendingRecords,0);XCTAssertEqual(log!.snapshot().writtenSamples,1000)
        let first=log!.files()[0];let bytes=try Data(contentsOf:first)
        let out=try log!.export(to:root.appendingPathComponent("export"));XCTAssertEqual(try Data(contentsOf:out),bytes)
        log=nil;let reopened=try DailyCSVLogger(directory:root,synthetic:true);reopened.append(CSVRow(["recordType":"EVENT","eventType":"TRIAL_END"]));try reopened.flush()
        let text=try String(contentsOf:first,encoding:.utf8);XCTAssertEqual(text.components(separatedBy:DailyCSVLogger.header).count,2);XCTAssertEqual(text.split(separator:"\n").count,1002);XCTAssertTrue(text.contains("1,1001,EVENT,"));XCTAssertTrue(text.contains("\\n换行"))
        XCTAssertEqual(reopened.snapshot().writtenTrials,1)
    }
    func testCSVPartialTailQuarantineRecovery() throws {
        let root=try temp();var log:DailyCSVLogger?=try DailyCSVLogger(directory:root)
        log!.append(CSVRow(["recordType":"SAMPLE"]));try log!.flush();let file=log!.files()[0];log=nil
        let h=try FileHandle(forWritingTo:file);try h.seekToEnd();try h.write(contentsOf:Data("1,2,SAM".utf8));try h.close()
        let recovered=try DailyCSVLogger(directory:root);recovered.append(CSVRow(["recordType":"EVENT","eventType":"AFTER_RECOVERY"]));try recovered.flush()
        let text=try String(contentsOf:file);XCTAssertTrue(text.contains("CSV_TAIL_RECOVERED"));XCTAssertTrue(text.contains("1,3,EVENT,"));XCTAssertFalse(text.contains("1,2,SAM"))
        let files=try FileManager.default.contentsOfDirectory(at:root,includingPropertiesForKeys:nil);let tail=try XCTUnwrap(files.first{$0.pathExtension == "bin"});XCTAssertEqual(try String(contentsOf:tail),"1,2,SAM")
    }
    func testCSVExportDirectoryURLWithoutTrailingSlash() throws {
        let root=try temp()
        let directory=URL(fileURLWithPath:root.path,isDirectory:false)
        let log=try DailyCSVLogger(directory:directory)
        log.append(CSVRow(["recordType":"SAMPLE"]));try log.flush()
        let source=try XCTUnwrap(log.files().first)
        let copy=try log.export(to:root.appendingPathComponent("export"))
        XCTAssertEqual(try Data(contentsOf:copy),try Data(contentsOf:source))
        let selectedCopy=try log.export(file:source,to:root.appendingPathComponent("selected-export"))
        XCTAssertEqual(try Data(contentsOf:selectedCopy),try Data(contentsOf:source))
    }
    func testCSVExportEquivalentSymlinkDirectory() throws {
        let root=try temp(), data=root.appendingPathComponent("Data"), alias=root.appendingPathComponent("Alias")
        let log=try DailyCSVLogger(directory:data)
        try FileManager.default.createSymbolicLink(at:alias,withDestinationURL:data)
        let source=try XCTUnwrap(log.files().first)
        let copy=try log.export(file:alias.appendingPathComponent(source.lastPathComponent),to:root.appendingPathComponent("export"))
        XCTAssertEqual(try Data(contentsOf:copy),try Data(contentsOf:source))
    }
    func testCSVExportFailureDoesNotLatchStorageErrorOrStopAppend() throws {
        let root=try temp(),log=try DailyCSVLogger(directory:root)
        let destination=root.appendingPathComponent("blocked")
        try Data("file instead of directory".utf8).write(to:destination)
        XCTAssertThrowsError(try log.export(to:destination))
        XCTAssertNil(log.snapshot().error)
        log.append(CSVRow(["recordType":"SAMPLE"]));try log.flush()
        XCTAssertEqual(log.snapshot().writtenSamples,1)
        XCTAssertNotNil(try log.export(to:root.appendingPathComponent("export")))
    }
    func testCSVExportRejectsOutsideSourceAndSourceOverwrite() throws {
        let root=try temp(), data=root.appendingPathComponent("Data"), log=try DailyCSVLogger(directory:data)
        let external=root.appendingPathComponent("outside.csv")
        try Data("keep original".utf8).write(to:external)
        XCTAssertThrowsError(try log.export(file:external,to:root.appendingPathComponent("export")))
        let link=data.appendingPathComponent("linked.csv")
        try FileManager.default.createSymbolicLink(at:link,withDestinationURL:external)
        XCTAssertThrowsError(try log.export(file:link,to:root.appendingPathComponent("export")))
        XCTAssertThrowsError(try log.export(to:data))
        XCTAssertEqual(try Data(contentsOf:external),Data("keep original".utf8))
        XCTAssertNil(log.snapshot().error)
        log.append(CSVRow(["recordType":"SAMPLE"]));try log.flush()
        XCTAssertEqual(log.snapshot().writtenSamples,1)
    }
    func testCSVSchemaMismatchNeverOverwrites() throws {
        let root=try temp();var log:DailyCSVLogger?=try DailyCSVLogger(directory:root);let file=log!.files()[0];log=nil
        let bad=Data("old,header\nkeep,this\n".utf8);try bad.write(to:file)
        XCTAssertThrowsError(try DailyCSVLogger(directory:root));XCTAssertEqual(try Data(contentsOf:file),bad)
    }
    func testCSVCompleteDamagedRowStopsReopenWithoutChangingSource() throws {
        let root=try temp();var log:DailyCSVLogger?=try DailyCSVLogger(directory:root)
        log!.append(CSVRow(["recordType":"SAMPLE"]));try log!.flush()
        let file=log!.files()[0];log=nil
        let handle=try FileHandle(forWritingTo:file);try handle.seekToEnd();try handle.write(contentsOf:Data("1,2,SAMPLE\n".utf8));try handle.close()
        let before=try Data(contentsOf:file)
        XCTAssertThrowsError(try DailyCSVLogger(directory:root))
        XCTAssertEqual(try Data(contentsOf:file),before)
    }
    func testCSVInvalidUTF8StillStopsReopenWithoutChangingSource() throws {
        let root = try temp()
        var log: DailyCSVLogger? = try DailyCSVLogger(directory: root)
        let file = try XCTUnwrap(log?.files().first)
        log = nil
        let handle = try FileHandle(forWritingTo: file)
        try handle.seekToEnd()
        try handle.write(contentsOf: Data([0xFF, 0x0A]))
        try handle.close()
        let before = try Data(contentsOf: file)
        XCTAssertThrowsError(try DailyCSVLogger(directory: root))
        XCTAssertEqual(try Data(contentsOf: file), before)
    }
    func testCSVCrossDayAndExportWhileAppending() throws {
        let root=try temp();let log=try DailyCSVLogger(directory:root)
        let tomorrow=Date().addingTimeInterval(86400)
        log.append(CSVRow(["recordType":"SAMPLE","sessionID":"SAME_SESSION"],date:Date()));log.append(CSVRow(["recordType":"SAMPLE","sessionID":"SAME_SESSION"],date:tomorrow));try log.flush()
        XCTAssertEqual(log.files().count,2)
        let output=try log.export(to:root.appendingPathComponent("export"));let before=try Data(contentsOf:output)
        log.append(CSVRow(["recordType":"EVENT","eventType":"TRIAL_END"]));try log.flush();XCTAssertEqual(try Data(contentsOf:output),before)
        XCTAssertGreaterThan(try Data(contentsOf:root.appendingPathComponent(output.lastPathComponent)).count,before.count)
        XCTAssertEqual(log.snapshot().writtenSamples,1, "Today's dashboard excludes tomorrow's samples")
    }
    func testCSVPartialWriteFailureRetainsBufferAndRetryHasNoDuplicates() throws {
        final class FailOnce: @unchecked Sendable {
            let lock = NSLock(); var remaining = true
            func write(_ handle: FileHandle, _ data: Data) throws {
                lock.lock(); let fail = remaining; remaining = false; lock.unlock()
                if fail { try handle.write(contentsOf: data.prefix(12)); throw NSError(domain:NSPOSIXErrorDomain,code:28) }
                try handle.write(contentsOf:data)
            }
        }
        let root=try temp(), fault=FailOnce()
        let log=try DailyCSVLogger(directory:root,writeBatch:{try fault.write($0,$1)})
        log.append(CSVRow(["recordType":"SAMPLE"]));log.append(CSVRow(["recordType":"EVENT","eventType":"TRIAL_END"]))
        XCTAssertThrowsError(try log.flush());XCTAssertEqual(log.snapshot().pendingRecords,2);XCTAssertNotNil(log.snapshot().error)
        XCTAssertEqual(try String(contentsOf:log.files()[0]),DailyCSVLogger.header)
        try log.retry();XCTAssertNil(log.snapshot().error);XCTAssertEqual(log.snapshot().pendingRecords,0);XCTAssertEqual(log.snapshot().writtenSamples,1);XCTAssertEqual(log.snapshot().writtenTrials,1)
        XCTAssertEqual(try String(contentsOf:log.files()[0]).split(separator:"\n").count,3)
    }
    func testCSVHighVolumeDeliveredRecordsAllPersist() throws {
        let root=try temp();var log:DailyCSVLogger?=try DailyCSVLogger(directory:root,synthetic:true)
        for i in 0..<100_000 { log!.append(CSVRow(["recordType":"SAMPLE","sampleSource":"SIMULATED_HOVER","monotonicTime":String(Double(i)/120),"x":"1171","y":"609","zOffset":"0.5"])) }
        try log!.flush();XCTAssertEqual(log!.snapshot().receivedRecords,100_000);XCTAssertEqual(log!.snapshot().writtenRecords,100_000);XCTAssertEqual(log!.snapshot().pendingRecords,0)
        log=nil
        let reopened=try DailyCSVLogger(directory:root,synthetic:true)
        XCTAssertEqual(reopened.snapshot().writtenRecords,100_000)
        XCTAssertEqual(reopened.snapshot().writtenSamples,100_000)
    }
    func testPersistedOutcomeReconcilesStaleCheckpointAndCSVQuotes() throws {
        let root=try temp(), log=try DailyCSVLogger(directory:root)
        log.append(CSVRow(["recordType":"EVENT","eventType":"TRIAL_END","trialID":"UUID_T1_A1","plannedIndex":"1","success":"true","isRepeat":"false","taskInstruction":"目标, \"选择\"","metadata":"{\"label\":\"TRIAL_END,quote\"}"]))
        try log.flush();let outcome=try XCTUnwrap(log.persistedOutcome(trialID:"UUID_T1_A1"));XCTAssertTrue(outcome.success);XCTAssertNil(outcome.error)
        XCTAssertNil(try log.persistedOutcome(trialID:"NOT_FOUND"))
        let row=try DailyCSVLogger.decodeLine(String(try String(contentsOf:log.files()[0]).split(separator:"\n").last!))
        XCTAssertEqual(row["taskInstruction"],"目标, \"选择\"")
    }
    func testRestoreStorageOrGeometryPauseRepeatsInsteadOfAdvancing() throws {
        for reason in ["STORAGE_ERROR","WINDOW_GEOMETRY_CHANGED"] {
            let e=try engine();var checkpoint:Checkpoint?;e.onCheckpoint={checkpoint=$0};e.pause(time:101,reason:reason)
            let restored=ExperimentEngine();restored.restore(checkpoint!,time:200);restored.resume(time:201)
            XCTAssertEqual(restored.plannedNumber,1);XCTAssertTrue(restored.isRepeat)
        }
    }
}
