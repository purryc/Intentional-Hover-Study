import Foundation
import XCTest
@testable import HoverStudyCore

extension V2Tests {
  func testV22CheckpointKeepsStarTargetsWhenContentFlagIsMissing() throws {
    var object = try JSONSerialization.jsonObject(with: JSONEncoder().encode(V2Config())) as! [String: Any]
    var revision = object["revision"] as! [String: Any]
    revision.removeValue(forKey: "contentTargets")
    object["revision"] = revision
    let old = try JSONDecoder().decode(V2Config.self, from: JSONSerialization.data(withJSONObject: object))
    XCTAssertFalse(old.usesContentTargets)
    XCTAssertEqual(old.protocolVersion, "HOVER_INTENT_V2_2")
    XCTAssertEqual(old.contentVersion, V2Content.version)
    let schedule = try V2Schedule.make(old, seed: 4)
    XCTAssertEqual(schedule.first { $0.task == .C3 && $0.scene == .notes }?.requested, ["note-focus-save"])
  }
  func testContentTargetMapsInsideActualPhotoInAllThreeScenes() throws {
    for scene in [V2Scene.news, .notes, .video] {
      let state = V2SceneState()
      let image = V2Content.focusImage(scene: scene, state: state)
      let focus = V2Content.focusObject(scene: scene, state: state, size: 48, contentTargets: true)
      XCTAssertEqual(focus.role, "content-object")
      XCTAssertEqual(focus.text, "蝴蝶")
      XCTAssertEqual(focus.mediaID, "cover-1")
      XCTAssertEqual(focus.bounds.width, 48)
      XCTAssertTrue(image.bounds.contains(Point(focus.bounds.x, focus.bounds.y)))
      XCTAssertTrue(image.bounds.contains(Point(focus.bounds.x + 48, focus.bounds.y + 48)))
      let scale = max(image.bounds.width / 640, image.bounds.height / 360)
      XCTAssertEqual((focus.bounds.center.x - image.bounds.center.x) / scale + 320, 260, accuracy: 1e-9)
      XCTAssertEqual((focus.bounds.center.y - image.bounds.center.y) / scale + 180, 80, accuracy: 1e-9)
      let objects = V2Content.objects(scene: scene, state: state, contentTargets: true)
      let parent = objects.first { $0.id == (scene == .notes ? "note-0" : image.id) }!
      XCTAssertEqual(parent.mediaID, focus.mediaID)
      XCTAssertEqual(parent.bounds.x, image.bounds.x)
      XCTAssertEqual(parent.bounds.y, image.bounds.y)
    }
  }
  func testC3ScheduleUsesButterflyAndSharesGeometryAcrossConditions() throws {
    let schedule = try V2Schedule.make(V2Config(), seed: 4).filter { $0.task == .C3 }
    XCTAssertEqual(schedule.count, 36)
    for scene in [V2Scene.news, .notes, .video] {
      let trials = schedule.filter { $0.scene == scene }
      XCTAssertEqual(Set(trials.map { $0.requested[0] }), ["\(scene.rawValue)-content-butterfly"])
      XCTAssertEqual(trials.filter { $0.condition == "HOVER" }.count, 6)
      XCTAssertTrue(trials.filter { $0.condition == "HOVER" }.allSatisfy { $0.instruction.contains("蝴蝶") && !$0.instruction.contains("星标") })
    }
  }
  func testStarHoverCannotSelectC3ButButterflyCompletesWithNoTouch() throws {
    for scene in [V2Scene.news, .notes, .video] {
      var config = V2Config(); config.tasks = [.C3]
      let seed = try (0..<1000).first { value in
        let first = try V2Schedule.make(config, seed: UInt64(value)).first!
        return first.scene == scene && first.condition == "HOVER"
      }!
      e = V2Engine(); e.onEvent = { [weak self] in self?.events.append($0) }
      try e.start(participant: "P01", config: config, seed: UInt64(seed), time: t, synthetic: true)
      let focus = e.selectionObjects.first!
      XCTAssertEqual(focus.role, "content-object")
      XCTAssertEqual(e.selectionObjects.count, 1)
      if let star = e.objects.first(where: { $0.id == "video-save" }) {
        hold(star.bounds.center, ms: 600)
        XCTAssertNotEqual(e.state, .success)
      }
      hold(focus.bounds.center, ms: 500)
      XCTAssertEqual(e.state, .success)
      XCTAssertEqual(events.last { $0.type == "HOVER_SELECT" }?.metadata["objectID"], focus.id)
    }
  }
  func testContentFocusFollowsScrollAndV21ReadingKeepsOriginalContent() throws {
    for scene in [V2Scene.news, .notes] {
      var state = V2SceneState()
      let before = V2Content.focusObject(scene: scene, state: state, size: 48, contentTargets: true)
      state.offset = 33
      let after = V2Content.focusObject(scene: scene, state: state, size: 48, contentTargets: true)
      XCTAssertEqual(after.bounds.y, before.bounds.y - 33, accuracy: 1e-9)
      XCTAssertEqual(after.bounds.x, before.bounds.x)
    }
    XCTAssertFalse(V2Content.objects(scene: .news, state: V2SceneState()).contains { $0.id == "news-focus-scene" })
    XCTAssertEqual(V2Content.objects(scene: .notes, state: V2SceneState()).first!.mediaID, "cover-0")
  }
}
