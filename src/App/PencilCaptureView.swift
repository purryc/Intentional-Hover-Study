import SwiftUI
import UIKit
import HoverStudyCore

struct PencilCaptureView: UIViewRepresentable {
    let store: StudyStore
    let scale: CGFloat
    let revision: Int
    func makeUIView(context: Context) -> CaptureCanvas {
        let view = CaptureCanvas(); view.store = store; return view
    }
    func updateUIView(_ view: CaptureCanvas, context: Context) {
        view.displayScale = scale; view.store = store; view.setNeedsDisplay()
    }
}
@MainActor final class CaptureCanvas: UIView {
    weak var store: StudyStore?
    var displayScale: CGFloat = 1
    private var hover: UIHoverGestureRecognizer!
    private var pendingFrame: (trialID: String, request: Double)?
    private var reportedFrameKey = ""
    private var displayLink: CADisplayLink?
    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = .black; isMultipleTouchEnabled = true; isOpaque = true
        hover = UIHoverGestureRecognizer(target: self, action: #selector(hoverChanged(_:)))
        hover.allowedTouchTypes = [NSNumber(value: UITouch.TouchType.pencil.rawValue)]
        hover.cancelsTouchesInView = false; addGestureRecognizer(hover)
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override func didMoveToWindow() {
        super.didMoveToWindow()
        // The window is an ancestor of both the capture canvas and SwiftUI controls;
        // observe Pencil hover globally rather than losing updates over those controls.
        hover.view?.removeGestureRecognizer(hover)
        window?.addGestureRecognizer(hover)
        if window == nil { displayLink?.invalidate(); displayLink = nil }
    }
    @objc private func hoverChanged(_ recognizer: UIHoverGestureRecognizer) {
        guard let store else { return }
        let p = recognizer.location(in: self), now = ProcessInfo.processInfo.systemUptime
        let phase: String
        switch recognizer.state { case .began: phase = "BEGAN"; case .ended: phase = "ENDED"; case .cancelled, .failed: phase = "CANCELLED"; default: phase = "CHANGED" }
        let scale = Double(max(displayScale,0.001))
        let vector = recognizer.azimuthUnitVector(in: self)
        store.receive(InputSample(time: now, point: Point(Double(p.x)/scale,Double(p.y)/scale), source: "PENCIL_HOVER", phase: phase, z: recognizer.zOffset, altitude: recognizer.altitudeAngle, azimuth: recognizer.azimuthAngle(in: self), azimuthX: vector.dx, azimuthY: vector.dy, roll: nil))
    }
    private func capture(_ touches: Set<UITouch>, event: UIEvent?, phase: String) {
        let now = ProcessInfo.processInfo.systemUptime
        // Predicted touches are deliberately excluded. Coalesced real samples retain original timestamps.
        for touch in touches.sorted(by: { $0.timestamp < $1.timestamp }) {
            let delivered: [UITouch] = phase == "MOVED" ? (event?.coalescedTouches(for: touch) ?? [touch]) : [touch]
            for sample in delivered {
                let p = sample.preciseLocation(in: self), scale = Double(max(displayScale,0.001))
                let pencil = sample.type == .pencil
                let vector = sample.azimuthUnitVector(in: self)
                store?.receive(InputSample(time: sample.timestamp, receivedTime: now, point: Point(Double(p.x)/scale,Double(p.y)/scale), source: pencil ? "PENCIL_TOUCH" : "FINGER_TOUCH", inputType: pencil ? "PENCIL" : "FINGER", phase: phase, altitude: pencil ? sample.altitudeAngle : nil, azimuth: pencil ? sample.azimuthAngle(in: self) : nil, azimuthX: pencil ? vector.dx : nil, azimuthY: pencil ? vector.dy : nil))
            }
        }
    }
    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) { capture(touches,event: event,phase: "BEGAN") }
    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) { capture(touches,event: event,phase: "MOVED") }
    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) { capture(touches,event: event,phase: "ENDED") }
    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) { capture(touches,event: event,phase: "CANCELLED") }
    private func point(_ local: Point) -> CGPoint { let p = Geometry.global(local); return CGPoint(x: p.x,y: p.y) }
    private func text(_ text: String, at p: CGPoint, color: UIColor = .darkGray, size: CGFloat = 18, centered: Bool = false) {
        let attributes: [NSAttributedString.Key: Any] = [.font: UIFont.systemFont(ofSize: size, weight: .medium), .foregroundColor: color]
        let measured = (text as NSString).size(withAttributes: attributes)
        (text as NSString).draw(at: CGPoint(x: centered ? p.x - measured.width / 2 : p.x, y: p.y), withAttributes: attributes)
    }
    private func circle(_ local: Point, radius: Double, color: UIColor, filled: Bool = false) {
        let p = point(local), path = UIBezierPath(ovalIn: CGRect(x: p.x-radius,y: p.y-radius,width: radius*2,height: radius*2))
        color.setStroke(); color.setFill(); path.lineWidth = 2; if filled { path.fill() } else { path.stroke() }
    }
    override func draw(_ rect: CGRect) {
        guard let store, let ctx = UIGraphicsGetCurrentContext() else { return }
        ctx.saveGState(); ctx.scaleBy(x: displayScale,y: displayScale)
        let phone = CGRect(x: 976,y:194,width:390,height:830)
        UIColor(white:0.98,alpha:1).setFill(); ctx.fill(phone)
        let e = store.engine
        if let c = e.current, e.state != .ended && e.state != .idle {
            ctx.saveGState(); ctx.clip(to: phone)
            if e.test == .swipe {
                let shift = e.contactActive ? max(0, (650 - (e.lastPoint?.y ?? 650))) : 0
                for i in 0..<8 {
                    let y = 224 + CGFloat(i)*155 - shift
                    UIColor(white:0.93,alpha:1).setFill(); ctx.fill(CGRect(x:994,y:y,width:354,height:135))
                    text("信息卡片 \(i+1)", at: CGPoint(x:1012,y:y+20), size:22)
                    text("接触后向上滑动，浏览下一条",at:CGPoint(x:1012,y:y+67),size:16)
                }
                if e.showTarget { text("↑ 向上滑动",at:point(Point(195,760)),color:.systemBlue,size:22,centered:true) }
            }
            if [.waitForStart,.startStable,.instruction].contains(e.state) {
                circle(c.start,radius:32,color:e.state == .startStable ? .systemBlue : .darkGray)
                circle(c.start,radius:5,color:.darkGray,filled:true)
                let p = point(c.start); text("起点",at:CGPoint(x:p.x,y:p.y+40),size:18,centered:true)
            }
            if e.showTarget && e.test != .swipe {
                circle(c.target,radius:c.diameter/2,color:.systemBlue)
                circle(c.target,radius:3,color:.systemBlue,filled:true)
                let p = point(c.target); text(e.test == .passThrough ? "经过，不点击" : e.test == .calibration ? "悬空保持" : "目标",at:CGPoint(x:p.x,y:p.y+c.diameter/2+12),size:17,centered:true)
                if let end = c.end {
                    circle(end,radius:32,color:.darkGray); let ep = point(end); text("终点",at:CGPoint(x:ep.x,y:ep.y+40),size:18,centered:true)
                    ctx.setStrokeColor(UIColor.lightGray.cgColor); ctx.setLineWidth(1); ctx.setLineDash(phase:0,lengths:[4,6]); ctx.move(to:point(c.start));ctx.addLine(to:point(end));ctx.strokePath();ctx.setLineDash(phase:0,lengths:[])
                }
            }
            if e.hoverActive, let cursor = e.lastPoint { circle(cursor,radius:7,color:.black) }
            ctx.restoreGState()
            if e.state == .success || e.state == .fail {
                ctx.setStrokeColor((e.state == .success ? UIColor.systemGreen : UIColor.systemRed).cgColor);ctx.setLineWidth(5);ctx.stroke(phone.insetBy(dx:3,dy:3))
            }
            if e.showTarget, let request = e.targetTime {
                let key = "\(e.trialID)_\(request)"
                if key != reportedFrameKey {
                    reportedFrameKey = key; pendingFrame = (e.trialID,request)
                    displayLink?.invalidate(); displayLink = CADisplayLink(target:self,selector:#selector(firstFrame(_:)));displayLink?.add(to:.main,forMode:.common)
                }
            }
        } else {
            text(e.state == .ended ? "本组结束" : "手机交互区域",at:CGPoint(x:1171,y:550),color:.darkGray,size:28,centered:true)
            text("390 × 830 pt",at:CGPoint(x:1171,y:595),size:18,centered:true)
        }
        ctx.restoreGState()
    }
    @objc private func firstFrame(_ link: CADisplayLink) {
        if let p = pendingFrame { store?.frame(time:ProcessInfo.processInfo.systemUptime,trialID:p.trialID,requestedAt:p.request,timestamp:link.timestamp) }
        pendingFrame = nil; displayLink?.invalidate();displayLink = nil
    }
}
