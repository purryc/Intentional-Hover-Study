import AVFoundation
import HoverStudyCore
import SwiftUI
import UIKit

struct V2CaptureView: UIViewRepresentable {
  let store: V2Store
  let scale: CGFloat
  let revision: Int
  func makeUIView(context: Context) -> V2Canvas {
    let v = V2Canvas()
    v.store = store
    return v
  }
  func updateUIView(_ view: V2Canvas, context: Context) {
    view.store = store
    view.displayScale = scale
    view.setNeedsDisplay()
    view.updateVideo()
  }
}
@MainActor final class V2Canvas: UIView {
  weak var store: V2Store?
  var displayScale: CGFloat = 1
  private var player: AVPlayer?
  private var playerLayer: AVPlayerLayer?
  private var videoID = ""
  private var videoHUD = CALayer()
  private var hudKey = ""
  private var videoObserver: Any?
  private var videoEnd: NSObjectProtocol?
  private var loops = 0
  private var frameKey = ""
  private var displayLink: CADisplayLink?
  private var cursorLayer = CAShapeLayer()
  private var hover: UIHoverGestureRecognizer!
  override init(frame: CGRect) {
    super.init(frame: frame)
    backgroundColor = .black
    isMultipleTouchEnabled = true
    isOpaque = true
    hover = UIHoverGestureRecognizer(target: self, action: #selector(hoverChanged(_:)))
    hover.allowedTouchTypes = [NSNumber(value: UITouch.TouchType.pencil.rawValue)]
    hover.cancelsTouchesInView = false
    addGestureRecognizer(hover)
  }
  required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
  override func didMoveToWindow() {
    super.didMoveToWindow()
    // The window is an ancestor of both the capture canvas and SwiftUI controls;
    // observe Pencil hover globally rather than losing updates over those controls.
    hover.view?.removeGestureRecognizer(hover)
    window?.addGestureRecognizer(hover)
    if window == nil {
      player?.pause()
      displayLink?.invalidate()
      displayLink = nil
    }
  }
  @objc private func hoverChanged(_ recognizer: UIHoverGestureRecognizer) {
    guard let store else { return }
    let p = recognizer.location(in: self)
    let now = ProcessInfo.processInfo.systemUptime
    let phase: String
    switch recognizer.state {
    case .began: phase = "BEGAN"
    case .ended: phase = "ENDED"
    case .cancelled, .failed: phase = "CANCELLED"
    default: phase = "CHANGED"
    }
    let scale = Double(max(displayScale, 0.001))
    let vector = recognizer.azimuthUnitVector(in: self)
    store.receive(
      InputSample(
        time: now, point: Point(Double(p.x) / scale, Double(p.y) / scale), source: "PENCIL_HOVER",
        phase: phase, z: recognizer.zOffset, altitude: recognizer.altitudeAngle,
        azimuth: recognizer.azimuthAngle(in: self), azimuthX: vector.dx, azimuthY: vector.dy,
        roll: nil))
  }
  private func capture(_ touches: Set<UITouch>, event: UIEvent?, phase: String) {
    let now = ProcessInfo.processInfo.systemUptime
    // Predicted touches are deliberately excluded. Coalesced real samples retain original timestamps.
    for touch in touches.sorted(by: { $0.timestamp < $1.timestamp }) {
      let delivered: [UITouch] =
        phase == "MOVED" ? (event?.coalescedTouches(for: touch) ?? [touch]) : [touch]
      for sample in delivered {
        let p = sample.preciseLocation(in: self)
        let scale = Double(max(displayScale, 0.001))
        let pencil = sample.type == .pencil
        let vector = sample.azimuthUnitVector(in: self)
        store?.receive(
          InputSample(
            time: sample.timestamp, receivedTime: now,
            point: Point(Double(p.x) / scale, Double(p.y) / scale),
            source: pencil ? "PENCIL_TOUCH" : "FINGER_TOUCH",
            inputType: pencil ? "PENCIL" : "FINGER", phase: phase,
            altitude: pencil ? sample.altitudeAngle : nil,
            azimuth: pencil ? sample.azimuthAngle(in: self) : nil,
            azimuthX: pencil ? vector.dx : nil, azimuthY: pencil ? vector.dy : nil,
            touchID: String(describing: ObjectIdentifier(touch))))
      }
    }
  }
  override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
    capture(touches, event: event, phase: "BEGAN")
  }
  override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) {
    capture(touches, event: event, phase: "MOVED")
  }
  override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
    capture(touches, event: event, phase: "ENDED")
  }
  override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
    capture(touches, event: event, phase: "CANCELLED")
  }
  func updateVideo() {
    guard let e = store?.engine else { return }
    let visible = e.running && e.current?.scene == .video
    playerLayer?.isHidden = !visible
    videoHUD.isHidden = !visible
    cursorLayer.isHidden = !visible
    guard visible else {
      player?.pause()
      return
    }
    let id = "\(e.trialID)/\(e.sceneState.videoIndex)"
    if id != videoID {
      if let observer = videoObserver { player?.removeTimeObserver(observer) }
      if let observer = videoEnd { NotificationCenter.default.removeObserver(observer) }
      guard
        let url = Bundle.main.url(
          forResource: "video-\(e.sceneState.videoIndex)", withExtension: "mp4",
          subdirectory: "StudyMedia")
      else { return }
      videoID = id
      loops = 0
      player?.pause()
      playerLayer?.removeFromSuperlayer()
      let p = AVPlayer(url: url)
      p.isMuted = true
      player = p
      let l = AVPlayerLayer(player: p)
      l.videoGravity = .resizeAspectFill
      l.backgroundColor = UIColor.black.cgColor
      layer.addSublayer(l)
      playerLayer = l
      videoObserver = p.addPeriodicTimeObserver(
        forInterval: CMTime(seconds: 0.25, preferredTimescale: 600), queue: .main
      ) { [weak self] time in
        Task { @MainActor [weak self] in
          guard let self, self.store?.engine.running == true else { return }
          self.store?.engine.videoProgress(
            time.seconds, loops: self.loops, at: ProcessInfo.processInfo.systemUptime)
        }
      }
      videoEnd = NotificationCenter.default.addObserver(
        forName: .AVPlayerItemDidPlayToEndTime, object: p.currentItem, queue: .main
      ) { [weak self] _ in
        Task { @MainActor [weak self] in
          guard let self else { return }
          self.loops += 1
          self.player?.seek(to: .zero)
          if self.store?.engine.sceneState.videoPaused == false { self.player?.play() }
        }
      }
    }
    playerLayer?.isHidden = false
    playerLayer?.frame = CGRect(
      x: 976 * displayScale, y: 254 * displayScale, width: 390 * displayScale,
      height: 740 * displayScale)
    playerLayer?.borderColor = UIColor.systemBlue.cgColor
    playerLayer?.borderWidth = e.current?.condition == "HOVER" && e.config.revision == nil ? 3 : 0
    if e.sceneState.videoPaused { player?.pause() } else { player?.play() }
    let newHUD = "\(id)/\(e.sceneState.videoPaused)/\(e.current?.condition ?? "")"
    videoHUD.removeFromSuperlayer()
    layer.addSublayer(videoHUD)
    videoHUD.frame = CGRect(
      x: 976 * displayScale, y: 194 * displayScale, width: 390 * displayScale,
      height: 830 * displayScale)
    if hudKey != newHUD {
      hudKey = newHUD
      let format = UIGraphicsImageRendererFormat()
      format.scale = 1
      format.opaque = false
      let image = UIGraphicsImageRenderer(size: CGSize(width: 390, height: 830), format: format)
        .image { context in
          let g = context.cgContext
          UIColor.black.withAlphaComponent(0.45).setFill()
          g.fill(CGRect(x: 0, y: 660, width: 390, height: 140))
          for o in e.objects where ["caption", "control", "image", "content-object"].contains(o.role) {
            if o.role == "image" {
              cover(Int(o.mediaID?.replacingOccurrences(of: "cover-", with: "") ?? "") ?? 0, o.bounds)
            } else if o.role != "content-object" {
              label(o.text, o.bounds, o.role == "control" ? 35 : 18, .white, .semibold)
            }
            if e.current?.condition == "HOVER" && e.current!.requested.contains(o.id) {
              g.setStrokeColor(UIColor.systemBlue.cgColor)
              g.setLineWidth(3)
              g.stroke(cg(o.bounds).insetBy(dx: 2, dy: 2))
            }
          }
          label("森林日常 · 第 \(e.sceneState.videoIndex+1) 集", V2Rect(24, 82, 330, 35), 18, .white)
          label("大雄兔的一天 · 无对白短片", V2Rect(24, 758, 330, 34), 15, .white)
        }
      videoHUD.contents = image.cgImage
    }
    cursorLayer.isHidden = false
    cursorLayer.removeFromSuperlayer()
    layer.addSublayer(cursorLayer)
    cursorLayer.fillColor = UIColor.clear.cgColor
    cursorLayer.strokeColor = UIColor.white.cgColor
    cursorLayer.lineWidth = 2
    if let p = e.hoverPoint {
      cursorLayer.path =
        UIBezierPath(
          ovalIn: CGRect(
            x: (p.x + 976 - 7) * displayScale, y: (p.y + 194 - 7) * displayScale,
            width: 14 * displayScale, height: 14 * displayScale)
        ).cgPath
    } else {
      cursorLayer.path = nil
    }
  }
  private func cg(_ r: V2Rect) -> CGRect {
    CGRect(x: r.x, y: r.y, width: r.width, height: r.height)
  }
  private func label(
    _ s: String, _ r: V2Rect, _ size: CGFloat = 18, _ color: UIColor = .darkGray,
    _ weight: UIFont.Weight = .regular
  ) {
    let paragraph = NSMutableParagraphStyle()
    paragraph.lineSpacing = 6
    (s as NSString).draw(
      in: cg(r),
      withAttributes: [
        .font: UIFont.systemFont(ofSize: size, weight: weight), .foregroundColor: color,
        .paragraphStyle: paragraph,
      ])
  }
  private func circle(_ p: Point, _ radius: Double, _ color: UIColor, fill: Bool = false) {
    let path = UIBezierPath(
      ovalIn: CGRect(x: p.x - radius, y: p.y - radius, width: radius * 2, height: radius * 2))
    color.setStroke()
    color.withAlphaComponent(0.14).setFill()
    path.lineWidth = 3
    if fill { path.fill() }
    path.stroke()
  }
  private var coverCache:[Int:UIImage]=[:]
  private func cover(_ index: Int, _ rect: V2Rect) {
    let key=index%6
    if coverCache[key] == nil, let url=Bundle.main.url(forResource:"cover-\(key)",withExtension:"jpg",subdirectory:"StudyMedia") {coverCache[key]=UIImage(contentsOfFile:url.path)}
    guard let image=coverCache[key],let ctx=UIGraphicsGetCurrentContext() else{return}
    let frame=cg(rect),scale=max(frame.width/image.size.width,frame.height/image.size.height)
    ctx.saveGState();ctx.clip(to:frame)
    image.draw(in:CGRect(x:frame.midX-image.size.width*scale/2,y:frame.midY-image.size.height*scale/2,width:image.size.width*scale,height:image.size.height*scale))
    ctx.restoreGState()
  }

  override func draw(_ rect: CGRect) {
    guard let e = store?.engine, let ctx = UIGraphicsGetCurrentContext() else { return }
    ctx.saveGState()
    ctx.scaleBy(x: displayScale, y: displayScale)
    ctx.translateBy(x: 976, y: 194)
    ctx.clip(to: CGRect(x: 0, y: 0, width: 390, height: 830))
    let dark = e.current?.scene == .video
    (dark ? UIColor.black : UIColor(white: 0.98, alpha: 1)).setFill()
    ctx.fill(CGRect(x: 0, y: 0, width: 390, height: 830))
    guard let c = e.current, !e.configurable else {
      label(e.state == .ended ? "本组结束" : "手机交互区域", V2Rect(85, 370, 270, 80), 26)
      ctx.restoreGState()
      return
    }
    if c.scene != .abstract {
      for o in e.objects {
        switch o.role {
        case "heading": label(o.text, o.bounds, 25, .black, .bold)
        case "paragraph": label(o.text, o.bounds, 19)
        case "byline": label(o.text, o.bounds, 13, .gray)
        case "image":
          cover(Int(o.mediaID?.replacingOccurrences(of:"cover-",with:"") ?? "") ?? 0, o.bounds)
          label(o.text, o.bounds.shifted(12, 10), 14, .white)
        case "card":
          UIColor.white.setFill()
          UIBezierPath(roundedRect: cg(o.bounds), cornerRadius: 12).fill()
          let i = Int(o.id.replacingOccurrences(of: "note-", with: "")) ?? 0
          cover(Int(o.mediaID?.replacingOccurrences(of: "cover-", with: "") ?? "") ?? i, V2Rect(o.bounds.x, o.bounds.y, o.bounds.width, o.bounds.height - 91))
          label(
            o.text, V2Rect(o.bounds.x + 10, o.bounds.y + o.bounds.height - 82, 160, 49), 16, .black,
            .semibold)
          label(
            "日常记录  ♡ \(128+i*37)",
            V2Rect(o.bounds.x + 10, o.bounds.y + o.bounds.height - 28, c.task == .C3 && e.config.revision != nil && !e.config.usesContentTargets && i == 0 ? 110 : 160, 25), 12, .gray)
        case "caption": label(o.text, o.bounds, 18, .white, .semibold)
        case "control": label(o.text, o.bounds, min(35, o.bounds.width - 8), dark ? .white : .darkGray)
        case "back": label(o.text, o.bounds, 19, .black)
        default: break
        }
        if c.condition == "HOVER" && c.requested.contains(o.id) {
          ctx.setStrokeColor(UIColor.systemBlue.cgColor)
          ctx.setLineWidth(3)
          ctx.stroke(cg(o.bounds).insetBy(dx: 2, dy: 2))
        }
      }
      (dark ? UIColor.black : UIColor.white).setFill()
      ctx.fill(CGRect(x: 0, y: 0, width: 390, height: 60))
      ctx.fill(CGRect(x: 0, y: 800, width: 390, height: 30))
      label(
        c.scene == .news
          ? "‹   城市观察"
          : c.scene == .notes
            ? (e.sceneState.detail == nil ? "关注     发现     附近" : "‹ 返回                图文笔记")
            : "关注        推荐        ⌕", V2Rect(18, 17, 355, 40), 20, dark ? .white : .black,
        .semibold)
      label(
        "素材 © Blender Foundation · CC BY 3.0", V2Rect(20, 807, 350, 20), 11,
        dark ? .lightGray : .gray)
      if c.scene == .video {
        label("森林日常 · 第 \(e.sceneState.videoIndex+1) 集", V2Rect(24, 82, 290, 35), 18, .white)
        label("大雄兔的一天 · 无对白短片", V2Rect(24, 758, 320, 34), 15, .white)
      }
    } else {
      if [.waitForStart, .startStable].contains(e.state) && c.task != .B4 {
        circle(c.start, 20, .darkGray)
        label("起点", V2Rect(c.start.x - 25, c.start.y + 30, 90, 35))
      } else {
        if c.scroll {
          UIColor(white: 0.9, alpha: 1).setFill()
          ctx.fill(
            c.horizontal
              ? CGRect(x: 0, y: 355, width: 390, height: 120)
              : CGRect(x: 135, y: 0, width: 120, height: 830))
          for i in -12...12 {
            let a = Double(i) * 60 + e.stripOffset
            UIColor.white.setStroke()
            ctx.setLineWidth(2)
            if c.horizontal {
              ctx.move(to: CGPoint(x: 195 + a, y: 355))
              ctx.addLine(to: CGPoint(x: 195 + a, y: 475))
            } else {
              ctx.move(to: CGPoint(x: 135, y: 415 + a))
              ctx.addLine(to: CGPoint(x: 255, y: 415 + a))
            }
            ctx.strokePath()
          }
        }
        for o in e.objects {
          let blue = c.requested.contains(o.id)
          let color: UIColor = e.selected.contains(o.id) ? .systemGreen : blue ? .systemBlue : .gray
          if o.role == "target" {
            circle(o.bounds.center, o.bounds.width / 2, color, fill: blue)
          } else {
            color.setStroke()
            ctx.setLineWidth(o.role == "window" ? 4 : 2)
            ctx.stroke(cg(o.bounds))
            if o.role == "marker" {
              UIColor.systemBlue.setFill()
              ctx.fill(cg(o.bounds).insetBy(dx: 5, dy: 5))
            }
          }
        }
        if c.task == .A2 {
          UIColor.systemBlue.setFill()
          ctx.fill(cg(c.dragBounds(at:e.dragPoint)))
        }
      }
      if c.task == .B4 {
        // Cancelled strokes remain separate. No line joins missing samples.
        for segment in e.lassoSegments + [e.lasso] where segment.count > 1 {
          let current = segment == e.lasso
          ctx.setStrokeColor((current ? UIColor.systemBlue : UIColor.lightGray).cgColor)
          ctx.setLineWidth(2)
          ctx.beginPath()
          ctx.move(to: CGPoint(x: segment[0].point.x, y: segment[0].point.y))
          for p in segment.dropFirst() { ctx.addLine(to: CGPoint(x: p.point.x, y: p.point.y)) }
          ctx.strokePath()
        }
        circle(c.start, e.config.lassoRadius, .darkGray)
        label("起点", V2Rect(c.start.x - 20, c.start.y - 45, 65, 35), 15)
        if [.success, .fail].contains(e.state), let a = e.lasso.first, let b = e.lasso.last {
          ctx.setLineDash(phase: 0, lengths: [4, 4])
          ctx.setStrokeColor(UIColor.systemOrange.cgColor)
          ctx.move(to: CGPoint(x: a.point.x, y: a.point.y))
          ctx.addLine(to: CGPoint(x: b.point.x, y: b.point.y))
          ctx.strokePath()
          ctx.setLineDash(phase: 0, lengths: [])
        }
      }
      if e.menuOpen {
        for o in e.menuObjects {
          UIColor(white: 0.13, alpha: 1).setFill()
          UIBezierPath(roundedRect: cg(o.bounds), cornerRadius: 8).fill()
          label(o.text, o.bounds.shifted(18, 10), 20, .white)
        }
      }
    }
    if let p = e.hoverPoint { circle(p, 7, dark ? .white : .black) }
    if [.success, .fail].contains(e.state) {
      ctx.setStrokeColor((e.state == .success ? UIColor.systemGreen : UIColor.systemRed).cgColor)
      ctx.setLineWidth(6)
      ctx.stroke(CGRect(x: 3, y: 3, width: 384, height: 824))
    }
    ctx.restoreGState()
    if let request = e.targetTime {
      let key = "\(e.trialID)/\(request)"
      if frameKey != key {
        frameKey = key
        displayLink?.invalidate()
        displayLink = CADisplayLink(target: self, selector: #selector(displayed(_:)))
        displayLink?.add(to: .main, forMode: .common)
      }
    }
  }
  @objc private func displayed(_ link: CADisplayLink) {
    if let t = store?.engine.targetTime {
      store?.engine.displayFrame(
        ProcessInfo.processInfo.systemUptime, request: t, timestamp: link.timestamp)
    }
    displayLink?.invalidate()
    displayLink = nil
  }
}
