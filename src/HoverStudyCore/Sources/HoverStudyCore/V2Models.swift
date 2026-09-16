import Foundation

public enum V2Task: String, Codable, CaseIterable, Sendable {
  case A1, A2, A3, A4, A5, A6, A7, B1, B2, B3, B4, C1, C2, C3
  public var group: String { String(rawValue.prefix(1)) }
  public var title: String {
    rawValue + " · " + [
      "A1": "点击", "A2": "拖动", "A3": "垂直滚动", "A4": "水平滚动", "A5": "新闻长文阅读", "A6": "图文信息流",
      "A7": "短视频流", "B1": "悬停菜单后点击", "B2": "悬停单选", "B3": "悬停多选", "B4": "空中圈选", "C1": "点击 / Hover",
      "C2": "滚动 / Hover", "C3": "阅读停留 / Hover",
    ][rawValue]!
  }
  public var reading: Bool { [.A5, .A6, .A7].contains(self) }
}
public enum V2Scene: String, Codable, CaseIterable, Sendable { case abstract, news, notes, video }
public struct V2RevisionConfig: Codable, Equatable, Sendable {
  public var bRepetitions = 2
  public var cDiameters: [Double] = [24, 36, 48]
  public var cMarkerDiameter = 36.0
  public var cObjectDiameter = 48.0
  public var retryInterval = 1.2
  public init() {}
}
public struct V2Config: Codable, Equatable, Sendable {
  // Optional so checkpoints written before V2.2 decode with their original protocol.
  public var revision: V2RevisionConfig? = V2RevisionConfig()
  public var protocolVersion: String { revision == nil ? "HOVER_INTENT_V2_1" : "HOVER_INTENT_V2_2" }
  public func requiresValidCompletion(_ task: V2Task) -> Bool {
    revision != nil && task.group != "B"
  }
  public var tasks = V2Task.allCases
  public var posture = "THUMB"
  public var repetitions = 1
  public var distances: [Double] = [120, 220, 320]
  public var diameters: [Double] = [30, 50, 80]
  public var fixedDistance = 220.0
  public var dwellMs = 500.0
  public var startMs = 300.0
  public var gapMs = 100.0
  public var timeout = 20.0
  public var readingSeconds = 120.0
  public var snippetSeconds = 20.0
  public var interval = 0.4
  public var movementThreshold = 10.0
  public var lassoRadius = 20.0
  public var lassoDeparture = 40.0
  public var lassoLength = 120.0
  public var lassoSamples = 12
  public var lassoArea = 2000.0
  public init() {}
  public func validate() throws {
    if let r = revision {
      guard (1...10).contains(r.bRepetitions), r.cDiameters.count == 3,
        (r.cDiameters + [r.cMarkerDiameter, r.cObjectDiameter]).allSatisfy({
          $0.isFinite && (10...60).contains($0)
        }), r.retryInterval.isFinite, r.retryInterval > 0,
        r.cDiameters.allSatisfy({ Geometry.contains(Point(195, 415 - fixedDistance), radius: $0 / 2)
          && Geometry.contains(Point(195, 415 + fixedDistance), radius: $0 / 2) })
      else { throw StudyError.invalidConfig }
    }
    guard !tasks.isEmpty, Set(tasks).count == tasks.count,
      ["THUMB", "CRADLE_INDEX"].contains(posture), (1...10).contains(repetitions),
      distances.count == 3, diameters.count == 3,
      [
        dwellMs, startMs, gapMs, timeout, readingSeconds, snippetSeconds, interval,
        movementThreshold, lassoRadius, lassoDeparture, lassoLength, lassoArea, fixedDistance,
      ].allSatisfy({ $0.isFinite && $0 > 0 }), lassoSamples >= 3, lassoRadius <= 30,
      lassoDeparture > lassoRadius,
      (distances + [fixedDistance]).allSatisfy({ d in
        d > 80
          && diameters.allSatisfy({ w in
            w.isFinite && w >= 10 && w <= 100
              && Geometry.contains(Point(195, 415 - d), radius: w / 2)
              && Geometry.contains(Point(195, 415 + d), radius: w / 2)
          })
      })
    else { throw StudyError.invalidConfig }
  }
}
public struct V2Rect: Codable, Equatable, Sendable {
  public var x, y, width, height: Double
  public init(_ x: Double, _ y: Double, _ w: Double, _ h: Double) {
    self.x = x
    self.y = y
    width = w
    height = h
  }
  public var center: Point { Point(x + width / 2, y + height / 2) }
  public func contains(_ p: Point) -> Bool {
    p.x >= x && p.x <= x + width && p.y >= y && p.y <= y + height
  }
  public func shifted(_ x: Double = 0, _ y: Double = 0) -> V2Rect {
    V2Rect(self.x + x, self.y + y, width, height)
  }
}
public struct V2Object: Codable, Equatable, Sendable {
  public var id: String
  public var bounds: V2Rect
  public var text: String
  public var role: String
  public var mediaID: String?
  public init(_ id: String, _ bounds: V2Rect, _ text: String = "", _ role: String = "target") {
    self.id = id
    self.bounds = bounds
    self.text = text
    self.role = role
    if role == "card" || role == "image" {
      let parts=id.split(separator:"-")
      let index = parts.count == 4 && parts[2] == "image" ? (Int(parts[1]) ?? 0)+(Int(parts[3]) ?? 0) : (Int(id.filter(\.isNumber)) ?? 0)
      mediaID="cover-\(index%6)"
    } else if role == "video" {mediaID=id} else {mediaID=nil}
  }
  public func contains(_ p: Point) -> Bool {
    role == "target" ? bounds.center.distance(to: p) <= bounds.width / 2 : bounds.contains(p)
  }
}
public struct V2Trial: Codable, Equatable, Sendable {
  public var task: V2Task
  public var condition: String
  public var scene: V2Scene
  public var ordinal: Int = 1
  public var total: Int = 1
  public var direction: Int
  public var distance: Double
  public var diameter: Double
  public var objects: [V2Object]
  public var requested: [String]
  public var start: Point
  public var menuChoice: String = "A"
  public var instruction: String
  public func dragBounds(at position:Point?=nil)->V2Rect {let p=position ?? start;return V2Rect(p.x-20,p.y-20,40,40)}
  public var natural: Bool { task.reading || (task == .C3 && condition == "NATURAL") }
  public var pureHover: Bool {
    [.B2, .B3, .B4].contains(task) || (task.group == "C" && condition == "HOVER")
  }
  public var scroll: Bool { [.A3, .A4, .C2].contains(task) }
  public var horizontal: Bool { task == .A4 }
}
public enum V2Schedule {
  public static func make(_ c: V2Config, seed: UInt64) throws -> [V2Trial] {
    try c.validate()
    var rng = SeededRandom(seed: seed)
    var result: [V2Trial] = []
    for task in V2Task.allCases where c.tasks.contains(task) {
      var list: [V2Trial] = []
      let modes =
        task.group == "C"
        ? [task == .C1 ? "TAP" : task == .C2 ? "SCROLL" : "NATURAL", "HOVER"]
        : [task.reading ? "NATURAL" : task.group == "B" ? "HOVER" : "TOUCH"]
      let sets = c.repetitions * (task.group == "B" ? (c.revision?.bRepetitions ?? 1) : 1)
      for _ in 0..<sets {
        for mode in modes {
          let scenes: [V2Scene] =
            task == .C3
            ? [.news, .notes, .video]
            : [task == .A5 ? .news : task == .A6 ? .notes : task == .A7 ? .video : .abstract]
          for scene in scenes {
            let count = task.reading ? 1 : [.A1, .A2].contains(task) ? 18 : 6
            for i in 0..<count {
              let dir = i % 2 == 0 ? -1 : 1
              let d = [.A1, .A2].contains(task) ? c.distances[i / 6] : c.fixedDistance
              let w = (task == .C1 ? c.revision?.cDiameters ?? c.diameters : c.diameters)[(i / 2) % 3]
              var objects = [
                V2Object("target", V2Rect(195 - w / 2, 415 + Double(dir) * d - w / 2, w, w))
              ]
              var start = Geometry.center
              var requested = ["target"]
              if [.B3, .B4].contains(task) {
                objects = (0..<6).map { j in
                  V2Object("t\(j)", V2Rect(j < 3 ? 80 : 260, 250 + Double(j % 3) * 100, 50, 50))
                }
                requested = task == .B4 && i % 2 == 0 ? ["t0", "t1"] : ["t0", "t1", "t2"]
                start = Point(45, 220)
              }
              if [.A3, .A4, .C2].contains(task) {
                let horizontal = task == .A4
                start =
                  horizontal
                  ? Point(195 - Double(dir) * 80, 415) : Point(195, 415 - Double(dir) * 120)
                let markerSize = task == .C2 ? c.revision?.cMarkerDiameter ?? 50 : 50
                objects = [
                  V2Object("marker", V2Rect(start.x - markerSize / 2, start.y - markerSize / 2, markerSize, markerSize), "", "marker"),
                  V2Object(
                    "window",
                    horizontal
                      ? V2Rect(195 + Double(dir) * 80 - 40, 375, 80, 80)
                      : V2Rect(155, 415 + Double(dir) * 120 - 40, 80, 80), "", "window"),
                ]
                requested = ["marker"]
                if task == .C2 && c.revision != nil { start = Geometry.center }
              }
              let ms = Int(c.dwellMs)
              let axis = dir < 0 ? (task == .A4 ? "向左" : "向上") : (task == .A4 ? "向右" : "向下")
              let prompt: String
              switch task {
              case .A1: prompt = "自然点击圆形目标，然后抬笔"
              case .A2: prompt = "把起点方块拖入圆形目标，再松开"
              case .A3, .A4: prompt = "\(axis)滑动条带，让标记进入终点窗口后抬笔"
              case .A5: prompt = "自然阅读这篇文章，可上下滚动"
              case .A6: prompt = "自然浏览图文，可打开笔记、左右翻图"
              case .A7: prompt = "自然观看视频，上下切换，点按暂停或继续"
              case .B1: prompt = "悬停\(ms)毫秒唤出菜单，再点击选项 \(i%2 == 0 ? "A" : "B")"
              case .B2: prompt = "在标出的目标上悬停\(ms)毫秒，不要触屏"
              case .B3: prompt = "依次悬停选中三个蓝色目标，不要触屏"
              case .B4: prompt = "在空中画圈，圈住标出的目标，回到起点完成，不要触屏"
              case .C1: prompt = mode == "HOVER" ? "悬停\(ms)毫秒选择目标，不要触屏" : "直接点击目标，然后抬笔"
              case .C2: prompt = mode == "HOVER" ? "在蓝色标记上悬停\(ms)毫秒，不要触屏" : "\(axis)滑动，让标记进入终点窗口后抬笔"
              case .C3:
                let item = scene == .news ? "路线缩略配图" : scene == .notes ? "首张卡片右下角收藏星标" : "视频右侧收藏星标"
                prompt = mode == "HOVER" ? "在\(c.revision == nil ? "蓝框内容" : item)上悬停\(ms)毫秒，不要触屏" : "自然阅读或观看当前内容"
              }
              var trial = V2Trial(
                task: task, condition: mode, scene: scene, direction: dir, distance: d, diameter: w,
                objects: objects, requested: requested, start: start, instruction: prompt)
              trial.menuChoice = i % 2 == 0 ? "A" : "B"
              if scene != .abstract {
                trial.objects = []
                trial.requested = [
                  scene == .news ? "news-p0" : scene == .notes ? "note-0" : "video-0"
                ]
                if task == .C3, let revision = c.revision {
                  trial.requested = [V2Content.focusObject(scene: scene, state: V2SceneState(), size: revision.cObjectDiameter).id]
                  trial.diameter = revision.cObjectDiameter
                }
              }
              if task == .C2 && c.revision != nil { trial.diameter = objects[0].bounds.width; trial.distance = 120 }
              list.append(trial)
            }
          }
        }
      }
      list.shuffle(using: &rng)
      if task.group == "C" {
        // Construct from shuffled condition queues; enforce the run limit without rejection loops.
        var queues = Dictionary(grouping: list, by: { $0.condition })
        var mixed: [V2Trial] = []
        var last = ""
        var run = 0
        while mixed.count < list.count {
          let options = queues.keys.sorted().filter {
            !(queues[$0]?.isEmpty ?? true) && ($0 != last || run < 3)
          }
          guard !options.isEmpty else { throw StudyError.invalidConfig }
          let largest = options.map { queues[$0]!.count }.max()!
          let ties = options.filter { queues[$0]!.count == largest }
          let chosen = ties[Int(rng.next() % UInt64(ties.count))]
          mixed.append(queues[chosen]!.removeLast())
          run = chosen == last ? run + 1 : 1
          last = chosen
        }
        list = mixed
      }
      for i in list.indices {
        list[i].ordinal = i + 1
        list[i].total = list.count
      }
      result += list
    }
    return result
  }
}
public func v2JSON<T: Encodable>(_ value: T) -> String {
  guard let data = try? JSONEncoder().encode(value) else { return "null" }
  return String(data: data, encoding: .utf8) ?? "null"
}
