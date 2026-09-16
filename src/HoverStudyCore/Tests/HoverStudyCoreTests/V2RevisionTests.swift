import Foundation
import XCTest
@testable import HoverStudyCore

extension V2Tests {
  func testRevisionDefaultsAndOldCheckpointCompatibility() throws {
    var new = V2Config()
    XCTAssertEqual(new.protocolVersion, "HOVER_INTENT_V2_3")
    let rows = try V2Schedule.make(new, seed: 11)
    for task in [V2Task.B1, .B2, .B3, .B4] {
      let group = rows.filter { $0.task == task }
      XCTAssertEqual(group.count, 12)
      XCTAssertEqual(group.filter { $0.direction == -1 }.count, 6)
    }
    XCTAssertEqual(rows.filter { $0.task == .B4 && $0.requested.count == 2 }.count, 6)
    var object = try JSONSerialization.jsonObject(with: JSONEncoder().encode(new)) as! [String: Any]
    object.removeValue(forKey: "revision")
    let old = try JSONDecoder().decode(V2Config.self, from: JSONSerialization.data(withJSONObject: object))
    XCTAssertNil(old.revision)
    XCTAssertEqual(old.protocolVersion, "HOVER_INTENT_V2_1")
    XCTAssertEqual(try V2Schedule.make(old, seed: 11).count, 135)
    XCTAssertFalse(old.requiresValidCompletion(.A1))
    new.revision!.bRepetitions = 3
    XCTAssertEqual(try V2Schedule.make(new, seed: 11).filter { $0.task == .B1 }.count, 18)
    new.revision!.cObjectDiameter = 200
    XCTAssertThrowsError(try new.validate())
  }

  func testEveryBaselineAndCFailureRetriesIdenticalPlannedTrial() throws {
    for task in V2Task.allCases where task.group != "B" {
      try start(task)
      let trial = e.current!, id = e.trialID, session = e.sessionID
      e.skip(t)
      XCTAssertEqual(e.state, .fail)
      XCTAssertTrue(e.hint.contains("重试本题"))
      t += 0.5; e.tick(t)
      XCTAssertEqual(e.trialID, id)
      t += 0.8; e.tick(t)
      XCTAssertEqual(e.current, trial)
      XCTAssertEqual(e.sessionID, session)
      XCTAssertEqual(e.index, 0)
      XCTAssertEqual(e.attempt, 2)
      XCTAssertNotEqual(e.trialID, id)
      let event = events.last { $0.type == "TRIAL_START" }!
      XCTAssertEqual(event.metadata["redoOf"], id)
      XCTAssertEqual(event.metadata["previousTrialID"], id)
      XCTAssertEqual(event.metadata["transitionKind"], "RETRY")
      XCTAssertEqual(event.metadata["progressionPolicy"], "VALID_COMPLETION")
      XCTAssertFalse(e.outcomes[0].success)
      XCTAssertTrue(e.progress.contains("重做第 1 /"))
    }
  }

  func testSuccessfulRetryCountsOneValidTrialAndKeepsFailure() throws {
    try start(.A1)
    arm(); sample(Point(1, 1), "BEGAN", touch: true); sample(Point(1, 1), "ENDED", touch: true)
    XCTAssertEqual(e.state, .fail)
    t += 1.3; e.tick(t); arm()
    let p = e.current!.objects[0].bounds.center
    sample(p, "BEGAN", touch: true); sample(p, "ENDED", touch: true)
    XCTAssertEqual(e.state, .success)
    XCTAssertEqual(e.outcomes.count, 2)
    XCTAssertTrue(e.outcomes[1].isRepeat)
    XCTAssertTrue(e.summary.contains("有效 1 / 18"))
    XCTAssertTrue(e.summary.contains("失败 1 次"))
    t += 0.5; e.tick(t)
    XCTAssertEqual(e.current!.ordinal, 2)
    XCTAssertEqual(e.attempt, 1)
  }

  func testBFailureAdvancesButRemainsAnAttempt() throws {
    for task in [V2Task.B1, .B2, .B3, .B4] {
      try start(task); arm(); sample(Point(195, 415), "BEGAN", touch: true)
      XCTAssertEqual(e.state, .fail)
      XCTAssertEqual(e.outcomes.count, 1)
      t += 0.5; e.tick(t)
      XCTAssertEqual(e.current!.ordinal, 2)
      XCTAssertEqual(e.attempt, 1)
      XCTAssertEqual(events.last { $0.type == "TRIAL_START" }!.metadata["progressionPolicy"], "PLANNED_ATTEMPTS")
      XCTAssertEqual(events.last { $0.type == "TRIAL_START" }!.metadata["previousTrialID"], e.outcomes[0].trialID)
      XCTAssertEqual(events.last { $0.type == "TRIAL_START" }!.metadata["transitionKind"], "NEXT_PLANNED")
    }
  }

  func testC1SmallCircleAndC2SeparateOriginAndSmallMarker() throws {
    var c = V2Config(); c.tasks = [.C1, .C2]
    let rows = try V2Schedule.make(c, seed: 4)
    XCTAssertEqual(Set(rows.filter { $0.task == .C1 }.map(\.diameter)), [24, 36, 48])
    for row in rows.filter({ $0.task == .C2 }) {
      XCTAssertEqual(row.objects[0].bounds.width, 36)
      XCTAssertEqual(row.start.distance(to: row.objects[0].bounds.center), 120)
    }
    try start(.C2); chooseCondition("HOVER"); arm()
    hold(e.current!.start, ms: 500)
    XCTAssertNotEqual(e.state, .success)
    let marker = e.objects.first { $0.id == "marker" }!
    hold(Point(marker.bounds.x - 1, marker.bounds.center.y), ms: 500)
    XCTAssertNotEqual(e.state, .success)
    hold(marker.bounds.center, ms: 499)
    XCTAssertNotEqual(e.state, .success)
    sample(marker.bounds.center, dt: 0.001)
    XCTAssertEqual(e.state, .success)
  }

  func testC2ScrollRequiresActualMarkerStartAndCompletes() throws {
    try start(.C2); chooseCondition("SCROLL"); arm()
    sample(e.current!.start, "BEGAN", touch: true)
    XCTAssertEqual(e.outcomes.last!.error, "WRONG_SCROLL_START")
    let row = e.current!
    t += 1.3; e.tick(t); XCTAssertEqual(e.current, row); arm()
    let a = e.objects.first { $0.id == "marker" }!.bounds.center
    let b = e.objects.first { $0.id == "window" }!.bounds.center
    sample(a, "BEGAN", touch: true); sample(b, "MOVED", touch: true); sample(b, "ENDED", touch: true)
    XCTAssertEqual(e.state, .success)
  }

  func testC3NaturalUsesOnlySameSmallFocalObjectWithoutFeedback() throws {
    try start(.C3); chooseCondition("NATURAL")
    let focus = e.selectionObjects[0]
    XCTAssertEqual(focus.bounds.width, 48)
    let other = e.objects.first { !e.current!.requested.contains($0.id) && $0.role != "byline" }!
    hold(other.bounds.center, ms: 600)
    let before = events.filter { $0.type == "CANDIDATE" }.count
    hold(focus.bounds.center, ms: 600)
    XCTAssertEqual(events.filter { $0.type == "CANDIDATE" }.count, before + 1)
    XCTAssertEqual(events.last { $0.type == "CANDIDATE" }!.metadata["objectID"], focus.id)
    XCTAssertTrue(e.selected.isEmpty)
    XCTAssertFalse(e.menuOpen)
    XCTAssertNotEqual(e.state, .success)
  }

  func testRecoveryAfterSuccessfulTrialAdvancesAndAfterFailureRetries() throws {
    try start(.A1); arm()
    let p = e.current!.objects[0].bounds.center
    sample(p, "BEGAN", touch: true); sample(p, "ENDED", touch: true)
    let cp = e.snapshot
    let fresh = V2Engine(); fresh.restore(cp, time: t, persisted: nil); fresh.resume(t + 1)
    XCTAssertEqual(fresh.current!.ordinal, 2)
    XCTAssertEqual(fresh.outcomes.count, 1)
    e = fresh; e.skip(t + 1)
    let failed = e.snapshot, id = e.trialID
    let restored = V2Engine(); restored.restore(failed, time: t + 2, persisted: nil); restored.resume(t + 3)
    XCTAssertEqual(restored.current!.ordinal, 2)
    XCTAssertEqual(restored.attempt, 2)
    XCTAssertNotEqual(restored.trialID, id)
  }
}
