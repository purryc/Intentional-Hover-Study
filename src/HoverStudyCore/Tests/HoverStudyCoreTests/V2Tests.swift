import XCTest

@testable import HoverStudyCore

final class V2Tests: XCTestCase {
  var e = V2Engine(), t = 10.0, seq = 0, events: [StudyEvent] = []
  override func setUp() {
    e = V2Engine()
    t = 10
    seq = 0
    events = []
    e.onEvent = { [weak self] in self?.events.append($0) }
  }
  func start(_ task: V2Task, _ edit: (inout V2Config) -> Void = { _ in }) throws {
    var c = V2Config()
    c.tasks = [task]
    edit(&c)
    try e.start(participant: "P01", config: c, seed: 4, time: t, synthetic: true)
  }
  func sample(
    _ p: Point, _ phase: String = "CHANGED", touch: Bool = false, dt: Double = 0.02,
    type: String = "PENCIL"
  ) {
    t += dt
    seq += 1
    e.ingest(
      InputSample(
        time: t, point: Geometry.global(p), source: touch ? "SIMULATED_TOUCH" : "SIMULATED_HOVER",
        inputType: type, phase: phase, z: touch ? nil : 0.5), sequence: seq)
  }
  func hold(_ p: Point, ms: Double) {
    sample(p)
    let end = t + ms / 1000
    while t + 0.02 < end - 1e-9 { sample(p) }
    sample(p, dt: end - t)
  }
  func arm() { hold(e.current!.start, ms: 300) }
  func chooseCondition(_ mode: String) {
    while e.current?.condition != mode {
      let c = e.current!
      if c.natural { t += e.config.snippetSeconds; e.tick(t) }
      else {
        arm()
        let a = c.scroll ? c.objects.first { $0.id == "marker" }!.bounds.center : c.objects[0].bounds.center
        sample(a, "BEGAN", touch: true)
        if c.scroll { sample(c.objects.first { $0.id == "window" }!.bounds.center, "MOVED", touch: true) }
        sample(c.scroll ? c.objects.first { $0.id == "window" }!.bounds.center : a, "ENDED", touch: true)
      }
      XCTAssertEqual(e.state, .success)
      t += 0.5
      e.tick(t)
    }
  }
  func loop(_ count: Int = 3) {
    let verts = [
      Point(45, 220), Point(165, 220), Point(165, count == 2 ? 430 : 535),
      Point(45, count == 2 ? 430 : 535), Point(45, 220),
    ]
    for i in 1..<verts.count {
      for j in 1...18 {
        let a = verts[i - 1]
        let b = verts[i]
        let r = Double(j) / 18
        sample(Point(a.x + (b.x - a.x) * r, a.y + (b.y - a.y) * r))
      }
    }
  }
  func testMatrixCountsBalanceSubsetAndSeed() throws {
    let c = V2Config()
    let s = try V2Schedule.make(c, seed: 44)
    XCTAssertEqual(s.filter { !$0.task.reading }.count, 156)
    XCTAssertEqual(s.filter { $0.task.reading }.count, 3)
    XCTAssertEqual(Set(s.map(\.task)).count, 14)
    XCTAssertEqual(s, try V2Schedule.make(c, seed: 44))
    XCTAssertNotEqual(s, try V2Schedule.make(c, seed: 45))
    for task in V2Task.allCases {
      let rows = s.filter { $0.task == task }
      XCTAssertEqual(rows.map(\.ordinal), Array(1...rows.count))
      if task.group == "C" {
        var last = ""
        var run = 0
        for r in rows {
          run = r.condition == last ? run + 1 : 1
          last = r.condition
          XCTAssertLessThanOrEqual(run, 3)
        }
      }
      for r in rows {
        for o in r.objects {
          XCTAssertTrue(Geometry.contains(Point(o.bounds.x, o.bounds.y)))
          XCTAssertTrue(
            Geometry.contains(Point(o.bounds.x + o.bounds.width, o.bounds.y + o.bounds.height)))
        }
      }
    }
    var subset = c
    subset.tasks = [.A7, .B4]
    subset.posture = "CRADLE_INDEX"
    XCTAssertEqual(try V2Schedule.make(subset, seed: 1).count, 13)
    subset.distances[2] = 500
    XCTAssertThrowsError(try subset.validate())
  }
  func testDwell499500AndZeroTouchSelection() throws {
    try start(.B2)
    arm()
    let p = e.current!.objects[0].bounds.center
    hold(p, ms: 499)
    XCTAssertNotEqual(e.state, .success)
    sample(p, dt: 0.001)
    XCTAssertEqual(e.state, .success)
    XCTAssertEqual(events.filter { $0.type == "HOVER_SELECT" }.count, 1)
    XCTAssertFalse(events.contains { $0.type == "TOUCH_DOWN" })
  }
  func testDwellResetsOnExitGapEndAndSwitch() throws {
    try start(.B2)
    arm()
    let p = e.current!.objects[0].bounds.center
    hold(p, ms: 400)
    sample(Point(1, 1))
    hold(p, ms: 400)
    XCTAssertNotEqual(e.state, .success)
    sample(p, dt: 0.101)
    hold(p, ms: 400)
    XCTAssertNotEqual(e.state, .success)
    sample(p, "ENDED")
    hold(p, ms: 499)
    XCTAssertNotEqual(e.state, .success)
    sample(p, dt: 0.001)
    XCTAssertEqual(e.state, .success)
  }
  func testB3NoDuplicateAndWrongSelection() throws {
    try start(.B3)
    arm()
    let c = e.current!
    for id in c.requested {
      let p = c.objects.first { $0.id == id }!.bounds.center
      hold(p, ms: 500)
      if id == c.requested[0] {
        hold(p, ms: 800)
        XCTAssertEqual(e.selected.count, 1)
      }
    }
    XCTAssertEqual(e.state, .success)
    XCTAssertEqual(e.selected.count, 3)
    t += 1
    e.tick(t)
    arm()
    hold(e.current!.objects[5].bounds.center, ms: 500)
    XCTAssertEqual(e.outcomes.last?.error, "WRONG_TARGET")
  }
  func testMenuPersistsCancelAndClick() throws {
    try start(.B1)
    arm()
    hold(e.current!.objects[0].bounds.center, ms: 500)
    XCTAssertTrue(e.menuOpen)
    sample(Point(1, 1))
    sample(Point(1, 1), "ENDED")
    XCTAssertTrue(e.menuOpen)
    let cancel = e.menuObjects[2].bounds.center
    sample(cancel, "BEGAN", touch: true)
    sample(cancel, "ENDED", touch: true)
    XCTAssertFalse(e.menuOpen)
    hold(e.current!.objects[0].bounds.center, ms: 500)
    let item = e.menuObjects.first { $0.id == e.current!.menuChoice }!.bounds.center
    sample(item, "BEGAN", touch: true)
    sample(item, "ENDED", touch: true)
    XCTAssertEqual(e.state, .success)
  }
  func testPureHoverUnexpectedTouch() throws {
    for task in [V2Task.B2, .B3, .B4, .C1, .C2, .C3] {
      e = V2Engine()
      try start(task)
      if task.group == "C" { chooseCondition("HOVER") }
      sample(Point(195, 415), "BEGAN", touch: true)
      XCTAssertEqual(e.outcomes.last?.error, "UNEXPECTED_TOUCH")
    }
  }
  func testAllCConditionsZeroTouchHover() throws {
    for task in [V2Task.C1, .C2, .C3] {
      e = V2Engine()
      try start(task)
      chooseCondition("HOVER")
      if e.current!.scene == .abstract { arm() }
      let id = e.current!.requested[0]
      hold(e.objects.first { $0.id == id }!.bounds.center, ms: 500)
      XCTAssertEqual(e.state, .success, "\(task)")
    }
  }
  func testLassoExactSelectionAndNoJitterSubmission() throws {
    try start(.B4)
    arm()
    for _ in 0..<15 {
      sample(Point(47, 221))
      sample(Point(43, 219))
    }
    XCTAssertTrue(e.running)
    XCTAssertFalse(events.contains { $0.type == "LASSO_CLOSE" })
    loop(e.current!.requested.count)
    XCTAssertEqual(e.state, .success)
    let close = events.first { $0.type == "LASSO_CLOSE" }
    XCTAssertNotNil(close)
    XCTAssertLessThanOrEqual(Double(close!.metadata["closureDistance"]!)!, 20)
    XCTAssertNotNil(close!.metadata["algorithmicClosingEdge"])
  }
  func testLassoWrongSetGapOutsideEndRetryAndTimeout() throws {
    try start(.B4)
    arm()
    sample(Point(160, 220))
    sample(Point(160, 300), dt: 0.101)
    XCTAssertFalse(e.lassoArmed)
    XCTAssertEqual(e.lassoSegments.count, 1)
    arm()
    sample(Point(160, 220))
    sample(Point(-1, 220))
    XCTAssertEqual(e.lassoSegments.count, 2)
    arm()
    sample(Point(160, 220))
    sample(Point(160, 220), "ENDED")
    XCTAssertEqual(e.lassoSegments.count, 3)
    arm()
    loop(e.current!.requested.count == 3 ? 2 : 3)
    XCTAssertEqual(e.outcomes.last?.error, "LASSO_SELECTION_MISMATCH")
    e.redo(t)
    t += 21
    e.tick(t)
    XCTAssertEqual(e.outcomes.last?.error, "TIMEOUT")
  }
  func testPolygonBoundarySelfIntersectionAndTinyArea() {
    let square = [Point(0, 0), Point(100, 0), Point(100, 100), Point(0, 100)]
    XCTAssertTrue(V2Polygon.contains(Point(0, 50), in: square))
    XCTAssertEqual(V2Polygon.area(square), 10000, accuracy: 1e-8)
    let bow = [Point(0, 0), Point(100, 100), Point(0, 100), Point(100, 0)]
    XCTAssertEqual(V2Polygon.area(bow), 5000, accuracy: 1e-8)
    XCTAssertTrue(V2Polygon.contains(Point(50, 10), in: bow))
    XCTAssertFalse(V2Polygon.contains(Point(10, 50), in: bow))
    XCTAssertLessThan(V2Polygon.area([Point(0, 0), Point(10, 0), Point(10, 10)]), 2000)
  }
  func testNaturalCandidateSilentCompleteDurationAndPollution() throws {
    try start(.A5)
    let p = e.objects.first { $0.id == "news-p0" }!.bounds.center
    hold(p, ms: 1800)
    XCTAssertEqual(events.filter { $0.type == "CANDIDATE" }.count, 1)
    XCTAssertFalse(e.menuOpen)
    XCTAssertTrue(e.selected.isEmpty)
    sample(p, "ENDED")
    let end = events.last { $0.type == "DWELL_END" }!
    XCTAssertGreaterThan(Double(end.metadata["durationMs"]!)!, 1700)
    sample(p, "BEGAN", touch: true, type: "FINGER")
    sample(Point(195, 100), "MOVED", touch: true, type: "FINGER")
    XCTAssertEqual(e.sceneState.offset, 0)
    XCTAssertTrue(e.running)
    sample(p, "ENDED", touch: true, type: "FINGER")
    XCTAssertTrue(events.contains { $0.type == "POLLUTION_END" })
    t += 121
    e.tick(t)
    XCTAssertEqual(e.state, .success)
  }
  func testReadingScrollNoteNavigationAndVideoControls() throws {
    try start(.A6)
    let p = e.objects[0].bounds.center
    sample(p, "BEGAN", touch: true)
    sample(p, "ENDED", touch: true)
    XCTAssertEqual(e.sceneState.detail, 0)
    sample(Point(300, 250), "BEGAN", touch: true)
    sample(Point(170, 250), "MOVED", touch: true)
    sample(Point(100, 250), "ENDED", touch: true)
    XCTAssertEqual(e.sceneState.imageIndex, 1)
    sample(Point(25, 30), "BEGAN", touch: true)
    sample(Point(25, 30), "ENDED", touch: true)
    XCTAssertNil(e.sceneState.detail)
    sample(Point(200, 600), "BEGAN", touch: true)
    sample(Point(200, 300), "MOVED", touch: true)
    sample(Point(200, 300), "ENDED", touch: true)
    XCTAssertGreaterThan(e.sceneState.offset, 0)
    e = V2Engine()
    try start(.A7)
    sample(p, "BEGAN", touch: true)
    sample(p, "ENDED", touch: true)
    XCTAssertTrue(e.sceneState.videoPaused)
    sample(Point(200, 650), "BEGAN", touch: true)
    sample(Point(200, 350), "MOVED", touch: true)
    sample(Point(200, 350), "ENDED", touch: true)
    XCTAssertEqual(e.sceneState.videoIndex, 1)
    XCTAssertFalse(e.sceneState.videoPaused)
  }
  func testAbstractTapDragAndBothScrollAxes() throws {
    for task in [V2Task.A1, .A2, .A3, .A4] {
      e = V2Engine()
      try start(task)
      arm()
      let c = e.current!
      let a = task == .A1 ? c.objects[0].bounds.center : c.start
      let b = c.scroll ? c.objects[1].bounds.center : c.objects[0].bounds.center
      sample(a, "BEGAN", touch: true)
      if task != .A1 { sample(b, "MOVED", touch: true) }
      sample(b, "ENDED", touch: true)
      XCTAssertEqual(e.state, .success, "\(task)")
    }
  }
  func testPauseRestoreRedoAndProgress() throws {
    try start(.B4)
    arm()
    sample(Point(160, 220))
    let id = e.trialID
    e.pause(t)
    XCTAssertEqual(e.state, .paused)
    e.resume(t)
    XCTAssertEqual(e.index, 0)
    XCTAssertEqual(e.attempt, 2)
    XCTAssertNotEqual(e.trialID, id)
    XCTAssertTrue(e.progress.contains("重做"))
    XCTAssertTrue(e.lasso.isEmpty)
    let cp = try JSONDecoder().decode(V2Checkpoint.self, from: JSONEncoder().encode(e.snapshot))
    let fresh = V2Engine()
    fresh.restore(cp, time: t, persisted: nil)
    XCTAssertEqual(fresh.state, .paused)
    XCTAssertEqual(fresh.schedule, e.schedule)
    e.skip(t)
    t += 1
    e.tick(t)
    XCTAssertEqual(e.index, 1)
    XCTAssertEqual(e.current!.ordinal, 2)
  }
  func testEveryC3SceneAndBothConditionsComplete() throws {
    try start(.C3)
    for _ in 0..<36 {
      let c = e.current!
      if c.natural {
        t += e.config.snippetSeconds
        e.tick(t)
      } else {
        hold(e.objects.first { $0.id == c.requested[0] }!.bounds.center, ms: 500)
      }
      XCTAssertEqual(e.state, .success, "\(c.scene) / \(c.condition)")
      t += 0.5
      e.tick(t)
    }
    XCTAssertEqual(e.state, .ended)
    XCTAssertEqual(e.outcomes.count, 36)
    XCTAssertEqual(e.progress, "本组结束")
  }
  func testEveryLassoLayoutCompletesWithNoTouch() throws {
    try start(.B4)
    for _ in 0..<12 {
      arm()
      loop(e.current!.requested.count)
      XCTAssertEqual(e.state, .success)
      t += 0.5
      e.tick(t)
    }
    XCTAssertEqual(e.state, .ended)
    XCTAssertEqual(e.outcomes.count, 12)
  }

  func testNoteCarouselUsesDistinctLoggedMedia() throws {
    var state=V2SceneState();state.detail=3
    let first=V2Content.objects(scene:.notes,state:state).first{$0.role == "image"}!
    state.imageIndex=1
    let second=V2Content.objects(scene:.notes,state:state).first{$0.role == "image"}!
    XCTAssertEqual(first.mediaID,"cover-3");XCTAssertEqual(second.mediaID,"cover-4")
    XCTAssertNotEqual(first.mediaID,second.mediaID)
    XCTAssertTrue(v2JSON(second).contains("cover-4"))
  }

  func testDragHitUsesDrawnSquare() throws {
    try start(.A2);arm();let c=e.current!
    sample(Point(c.start.x+24,c.start.y),"BEGAN",touch:true)
    XCTAssertEqual(e.outcomes.last?.error,"WRONG_DRAG_START")
    e.redo(t);arm();let p=Point(c.start.x+19,c.start.y+19)
    XCTAssertTrue(c.dragBounds().contains(p));sample(p,"BEGAN",touch:true)
    sample(c.objects[0].bounds.center,"MOVED",touch:true)
    sample(c.objects[0].bounds.center,"ENDED",touch:true);XCTAssertEqual(e.state,.success)
  }

}
