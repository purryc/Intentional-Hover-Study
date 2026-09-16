import Foundation

public enum V2Polygon {
  public static func contains(_ p: Point, in polygon: [Point]) -> Bool {
    guard polygon.count >= 3 else { return false }
    var inside = false
    for i in polygon.indices {
      let a = polygon[i]
      let b = polygon[(i + 1) % polygon.count]
      let cross = (p.x - a.x) * (b.y - a.y) - (p.y - a.y) * (b.x - a.x)
      if abs(cross) < 1e-7 && p.x >= min(a.x, b.x) - 1e-8 && p.x <= max(a.x, b.x) + 1e-8
        && p.y >= min(a.y, b.y) - 1e-8 && p.y <= max(a.y, b.y) + 1e-8
      {
        return true
      }
      if (a.y > p.y) != (b.y > p.y), p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x {
        inside.toggle()
      }
    }
    return inside
  }
  /// Integrate even-odd scanline widths. Split at vertices AND edge intersections,
  /// so a figure-eight measures both lobes instead of cancelling signed areas.
  public static func area(_ p: [Point]) -> Double {
    guard p.count >= 3 else { return 0 }
    let edges = p.indices.map { (p[$0], p[($0 + 1) % p.count]) }
    var ys = p.map(\.y)
    for i in edges.indices {
      for j in edges.indices where j > i {
        let (a, b) = edges[i]
        let (c, d) = edges[j]
        let rx = b.x - a.x
        let ry = b.y - a.y
        let sx = d.x - c.x
        let sy = d.y - c.y
        let den = rx * sy - ry * sx
        if abs(den) < 1e-10 { continue }
        let t = ((c.x - a.x) * sy - (c.y - a.y) * sx) / den
        let u = ((c.x - a.x) * ry - (c.y - a.y) * rx) / den
        if t > 0 && t < 1 && u > 0 && u < 1 { ys.append(a.y + t * ry) }
      }
    }
    ys = Array(Set(ys)).sorted()
    var area = 0.0
    for i in 1..<ys.count {
      let y = (ys[i] + ys[i - 1]) / 2
      let xs = edges.compactMap { a, b -> Double? in
        guard (a.y > y) != (b.y > y) else { return nil }
        return a.x + (y - a.y) * (b.x - a.x) / (b.y - a.y)
      }.sorted()
      var width = 0.0
      for j in stride(from: 0, to: xs.count - 1, by: 2) { width += xs[j + 1] - xs[j] }
      area += width * (ys[i] - ys[i - 1])
    }
    return area
  }
}
public struct V2LassoPoint: Codable, Equatable, Sendable {
  public var point: Point
  public var time: Double
  public var sequence: Int
  public init(_ point: Point, _ time: Double, _ sequence: Int) {
    self.point = point
    self.time = time
    self.sequence = sequence
  }
}
public struct V2SceneState: Codable, Equatable, Sendable {
  public var offset = 0.0
  public var savedOffset = 0.0
  public var detail: Int? = nil
  public var imageIndex = 0
  public var videoIndex = 0
  public var videoTime = 0.0
  public var videoPaused = false
  public var videoLoops = 0
  public init() {}
}
public enum V2Content {
  public static let version = "reading-2026-09-v2"
  public static func focusObject(scene: V2Scene, state: V2SceneState, size: Double) -> V2Object {
    switch scene {
    case .news:
      var photo = V2Object("news-focus-photo", V2Rect(300, 430 - state.offset, size, size), "", "image")
      photo.mediaID = "cover-0"
      return photo
    case .notes:
      return V2Object("note-focus-save", V2Rect(182 - size, 343 - size - state.offset, size, size), "☆", "control")
    case .video:
      return V2Object("video-save", V2Rect(354.5 - size / 2, 627.5 - size / 2, size, size), "☆", "control")
    case .abstract:
      return V2Object("none", V2Rect(0, 0, 0, 0))
    }
  }
  public static let headlines = [
    "把周末留给一条慢慢走的路", "城市里的树，比我们想象的更忙", "从一杯咖啡开始的街区观察", "不赶时间，才能看见日常的细节", "在阳台种下一个小小的春天",
    "下班以后，去河边看一会儿云",
  ]
  public static let paragraphs = [
    "清晨七点，街角的面包店刚刚开门。有人牵着狗走过，有人靠在长椅上看报纸。我们平常急着穿过的街区，在这个时间展现了另一种节奏。今天，不妨跟着这条路线，重新认识身边熟悉的地方。",
    "沿着河岸走十分钟，就能到达一片树荫。风吹过的时候，叶子的影子在石板路上慢慢移动。这里没有需要打卡的景点，也没有规定的路线。你可以停下来，也可以继续往前。",
    "住在附近的居民说，最喜欢这里的原因是变化。春天有新叶，夏天有蝉鸣，秋天的光线会更柔和。每次经过，同样的地方总有一点不同。城市生活里的惊喜，往往藏在这些微小的变化中。",
    "路边的小店也有自己的故事。修鞋的师傅在这里工作了二十年，花店的老板会把当天剩下的花摆在门外。买东西的人和路过的人聊几句话，街道就不再只是从一个地方通向另一个地方的通道。",
    "如果走累了，可以找一张长椅坐下。把手机放低一点，看行人来来往往。并不需要每一分钟都有明确的用途。短暂的停留，有时候恰好能让接下来的事情变得轻松一些。",
    "我们记录了沿途的声音：自行车铃、远处的公交车、树叶摩擦，还有孩子追逐时的笑声。当你开始留意这些声音，一条再普通不过的路，也会变得有层次。",
    "午后的阳光照进窗边，咖啡店里的人渐渐多起来。有的人带着一本书，有的人只是看着窗外。这里的菜单很简单，店主却能记住许多常客的偏好。人与地方之间的联系，就这样一点一点积累。",
    "回程不一定要走原路。拐进没走过的小巷，你也许会遇见一面新画的墙、一棵开花的树，或者一只晒太阳的猫。保持一点好奇，是这次散步唯一需要准备的东西。",
    "这篇记录并不是一份必须完成的清单。每个人都有自己的步速，也会被不同的细节吸引。你可以选择其中一小段，也可以只在家附近走一圈，让熟悉的日常重新变得可见。",
    "傍晚时分，河面的颜色变深了。早上匆忙赶路的人开始慢下来，桥上的灯一盏一盏亮起。一天结束之前，还有足够的时间，把目光从目的地移到眼前的生活。",
  ]
  public static func objects(scene: V2Scene, state: V2SceneState) -> [V2Object] {
    switch scene {
    case .abstract: return []
    case .news:
      var o = [
        V2Object("news-title", V2Rect(22, 80 - state.offset, 346, 90), headlines[0], "heading"),
        V2Object(
          "news-author", V2Rect(22, 179 - state.offset, 346, 35), "城市观察 · 原创专栏 · 2026年9月", "byline"),
      ]
      for i in 0..<20 {
        let y = 230 + Double(i) * 265 - state.offset
        o.append(
          V2Object(
            "news-p\(i)", V2Rect(22, y, 346, 180), paragraphs[i % paragraphs.count], "paragraph"))
        if i % 3 == 1 {
          o.append(
            V2Object("news-img\(i)", V2Rect(22, y + 184, 346, 76), "沿途的风景 · 图 \(i+1)", "image"))
        }
      }
      return o
    case .notes:
      if let d = state.detail {
        return [
          V2Object("back", V2Rect(12, 8, 68, 45), "‹ 返回", "back"),
          V2Object(
            "note-\(d)-image-\(state.imageIndex)", V2Rect(0, 64 - state.offset, 390, 360),
            "\(state.imageIndex+1) / 3", "image"),
          V2Object(
            "note-\(d)-title", V2Rect(20, 440 - state.offset, 350, 80), headlines[d % 6], "heading"),
          V2Object(
            "note-\(d)-body", V2Rect(20, 535 - state.offset, 350, 550),
            paragraphs[d % 10] + "\n\n" + paragraphs[(d + 1) % 10], "paragraph"),
        ]
      }
      var o: [V2Object] = []
      var ys = [76.0, 76.0]
      for i in 0..<30 {
        let col = i % 2
        let h = Double([275, 320, 295][i % 3])
        o.append(
          V2Object(
            "note-\(i)", V2Rect(10 + Double(col) * 190, ys[col] - state.offset, 180, h),
            headlines[i % 6], "card"))
        ys[col] += h + 12
      }
      return o
    case .video:
      return [
        V2Object(
          "video-\(state.videoIndex)", V2Rect(0, 60, 390, 740), headlines[state.videoIndex % 6],
          "video"),
        V2Object(
          "video-caption-\(state.videoIndex)", V2Rect(20, 675, 285, 85),
          "@森林放映室\n" + headlines[state.videoIndex % 6], "caption"),
        V2Object("video-like", V2Rect(327, 435, 55, 65), "♡", "control"),
        V2Object("video-comment", V2Rect(327, 515, 55, 65), "◯", "control"),
        V2Object("video-save", V2Rect(327, 595, 55, 65), "☆", "control"),
      ]
    }
  }
  public static func maxOffset(scene: V2Scene, state: V2SceneState) -> Double {
    scene == .news ? 4800 : scene == .notes ? (state.detail == nil ? 4200 : 450) : 0
  }
  public static func visible(_ objects: [V2Object]) -> [V2Object] {
    objects.filter { $0.bounds.y + $0.bounds.height > 60 && $0.bounds.y < 800 }
  }
  public static func hit(_ point: Point, scene: V2Scene, state: V2SceneState) -> V2Object? {
    guard point.y >= 60 && point.y <= 800 else { return nil }
    return objects(scene: scene, state: state).reversed().first { $0.bounds.contains(point) }
  }
}
