import ARKit
import AVFoundation
import HoverStudyCore
import simd

struct GazeObservation {
  let frameTime: Double
  let receivedTime: Double
  let raw: Point?
  let screen: Point?
  let reason: String
}

/// Opt-in, passive face-gaze estimate. No camera frames or face geometry are persisted.
final class GazeCapture: NSObject, ARSessionDelegate {
  enum Phase { case idle, requesting, calibrating, ready, unavailable }
  private let session = ARSession()
  private let calibrationTargets: [Point] = [
    Point(40, 80), Point(195, 80), Point(350, 80),
    Point(40, 415), Point(195, 415), Point(350, 415),
    Point(40, 750), Point(195, 750), Point(350, 750),
    Point(100, 245), Point(290, 245), Point(100, 585), Point(290, 585),
  ]
  private let stepDuration = 1.15
  private let settlingDuration = 0.40
  private var stepStarted = 0.0
  private var sessionStarted = 0.0
  private var calibratedAt: Double?
  private var stepIndex = 0
  private var stepSamples: [Point] = []
  private var stepFrames = 0
  private var fitPairs: [GazeCalibrationPair] = []
  private var validationPairs: [GazeCalibrationPair] = []
  private var validationFrames = 0
  private var validationValidFrames = 0
  private var frameReceiptDeltas: [Double] = []
  private var fit: GazeAffineCalibration?
  private var lastTracked: Bool?
  private(set) var phase: Phase = .idle
  private(set) var calibrationID = ""
  private(set) var quality = "NOT_CALIBRATED"
  private(set) var validationP90Pt: Double?
  private(set) var validationCoverage = 0.0
  private(set) var status = "视线采集未开启"
  var onFinished: ((String) -> Void)?
  var onObservation: ((GazeObservation) -> Void)?
  var onTrackingChange: ((Bool, String) -> Void)?

  var isCalibrating: Bool { phase == .requesting || phase == .calibrating }
  var isReady: Bool { phase == .ready }
  var target: Point? { phase == .calibrating && stepIndex < calibrationTargets.count ? calibrationTargets[stepIndex] : nil }
  var progress: String { "视线校准 \(min(stepIndex + 1, calibrationTargets.count)) / \(calibrationTargets.count)" }
  var qualityPassed: Bool { quality == "OBJECT_LEVEL_PILOT" }
  var calibrationAgeS: Double? { calibratedAt.map { ProcessInfo.processInfo.systemUptime - $0 } }

  func begin() {
    stop()
    calibrationID = UUID().uuidString
    guard ARFaceTrackingConfiguration.isSupported else {
      finishUnavailable("此设备不支持前摄面部追踪")
      return
    }
    phase = .requesting
    status = "正在请求前摄权限"
    switch AVCaptureDevice.authorizationStatus(for: .video) {
    case .authorized: startARSession()
    case .notDetermined:
      AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
        DispatchQueue.main.async {
          guard let self, self.phase == .requesting else { return }
          if granted { self.startARSession() }
          else { self.finishUnavailable("前摄权限未开启，继续只记录 Pencil") }
        }
      }
    default: finishUnavailable("前摄权限未开启，继续只记录 Pencil")
    }
  }

  private func startARSession() {
    session.delegate = self
    session.delegateQueue = .main
    sessionStarted = ProcessInfo.processInfo.systemUptime
    session.run(ARFaceTrackingConfiguration(), options: [.resetTracking, .removeExistingAnchors])
    stepIndex = 0
    // Camera startup may take longer than a target step. Begin timing at the first frame.
    stepStarted = 0
    phase = .calibrating
    status = "请只看圆点，保持当前握姿和距离"
  }

  func stop() {
    session.pause()
    phase = .idle
    fit = nil
    stepSamples.removeAll()
    fitPairs.removeAll()
    validationPairs.removeAll()
    validationFrames = 0
    validationValidFrames = 0
    frameReceiptDeltas.removeAll()
    lastTracked = nil
    quality = "NOT_CALIBRATED"
    validationP90Pt = nil
    validationCoverage = 0
    calibratedAt = nil
    sessionStarted = 0
    status = "视线采集未开启"
  }

  func tick(_ time: Double) {
    guard phase == .calibrating else { return }
    if stepStarted == 0 {
      if sessionStarted > 0 && time - sessionStarted > 10 {
        finishUnavailable("前摄尚未返回画面，继续只记录 Pencil")
      }
      return
    }
    while time - stepStarted >= stepDuration && phase == .calibrating {
      completeStep()
      stepStarted += stepDuration
    }
  }

  private func completeStep() {
    if stepSamples.count >= 6 {
      let xs = stepSamples.map(\.x).sorted()
      let ys = stepSamples.map(\.y).sorted()
      let raw = Point(xs[xs.count / 2], ys[ys.count / 2])
      let pair = GazeCalibrationPair(raw: raw, screen: Geometry.global(calibrationTargets[stepIndex]))
      if stepIndex < 9 { fitPairs.append(pair) }
      else { validationPairs.append(pair) }
    }
    stepIndex += 1
    stepSamples.removeAll(keepingCapacity: true)
    stepFrames = 0
    if stepIndex == 9 { fit = GazeAffineCalibration.fit(fitPairs) }
    if stepIndex == calibrationTargets.count { completeCalibration() }
  }

  private func completeCalibration() {
    guard let fit, validationPairs.count >= 3 else {
      finishUnavailable("视线校准采样不足，继续只记录 Pencil")
      return
    }
    let errors = validationPairs.compactMap { pair in fit.map(pair.raw)?.distance(to: pair.screen) }.sorted()
    guard errors.count >= 3 else {
      finishUnavailable("视线校准无法计算，继续只记录 Pencil")
      return
    }
    validationP90Pt = errors[max(0, Int(ceil(Double(errors.count) * 0.9)) - 1)]
    validationCoverage = validationFrames > 0 ? Double(validationValidFrames) / Double(validationFrames) : 0
    quality = validationP90Pt! <= 24 && validationCoverage >= 0.70 ? "OBJECT_LEVEL_PILOT" : "COARSE_ONLY"
    calibratedAt = ProcessInfo.processInfo.systemUptime
    phase = .ready
    status = qualityPassed
      ? "视线已校准；可作小对象探索，不改变任务判定"
      : "视线已记录，精度不足以判断 48 pt 小对象"
    onFinished?(quality)
  }

  private func finishUnavailable(_ reason: String) {
    session.pause()
    phase = .unavailable
    quality = "UNAVAILABLE"
    status = reason
    onFinished?(quality)
  }

  var calibrationMetadata: [String: String] {
    var result = [
      "calibrationID": calibrationID, "quality": quality,
      "fitPoints": String(fitPairs.count), "validationPoints": String(validationPairs.count),
      "validationCoverage": String(validationCoverage),
      "projection": "ARKIT_FACE_LOOK_AT_TO_CAMERA_Z0_AFFINE",
      "cameraFramesStored": "false",
    ]
    if let validationP90Pt { result["validationP90Pt"] = String(validationP90Pt) }
    result["fitPairs"] = fitPairs.map {
      "\($0.raw.x),\($0.raw.y),\($0.screen.x),\($0.screen.y)"
    }.joined(separator: ";")
    result["heldOutPairs"] = validationPairs.map {
      "\($0.raw.x),\($0.raw.y),\($0.screen.x),\($0.screen.y)"
    }.joined(separator: ";")
    if !frameReceiptDeltas.isEmpty {
      let sorted = frameReceiptDeltas.sorted()
      result["frameToReceiptDeltaMedianS"] = String(sorted[sorted.count / 2])
      result["frameToReceiptDeltaP90S"] = String(sorted[max(0, Int(ceil(Double(sorted.count) * 0.9)) - 1)])
    }
    if let fit {
      result["rawCenter"] = "\(fit.center.x),\(fit.center.y)"
      result["rawScale"] = "\(fit.scale.x),\(fit.scale.y)"
      result["xCoefficients"] = fit.xCoefficients.map { String($0) }.joined(separator: ",")
      result["yCoefficients"] = fit.yCoefficients.map { String($0) }.joined(separator: ",")
    }
    return result
  }

  func session(_ session: ARSession, didUpdate frame: ARFrame) {
    guard phase == .calibrating || phase == .ready else { return }
    let now = ProcessInfo.processInfo.systemUptime
    if phase == .calibrating && stepStarted == 0 { stepStarted = now }
    if phase == .calibrating && frameReceiptDeltas.count < 600 {
      frameReceiptDeltas.append(now - frame.timestamp)
    }
    let face = frame.anchors.compactMap { $0 as? ARFaceAnchor }.first(where: { $0.isTracked })
    let raw = face.flatMap { Self.cameraPlaneFeature(face: $0, camera: frame.camera) }
    let tracked = raw != nil
    if lastTracked != tracked {
      lastTracked = tracked
      onTrackingChange?(tracked, tracked ? "TRACKING_RESUMED" : "NO_TRACKED_FACE")
    }
    if phase == .calibrating {
      stepFrames += 1
      if stepIndex >= 9 { validationFrames += 1; if tracked { validationValidFrames += 1 } }
      if let raw, now - stepStarted >= settlingDuration { stepSamples.append(raw) }
    }
    let mapped = raw.flatMap { fit?.map($0) }
    onObservation?(GazeObservation(
      frameTime: frame.timestamp, receivedTime: now, raw: raw,
      screen: mapped,
      reason: raw == nil ? "NO_TRACKED_FACE" : mapped == nil ? "UNCALIBRATED" : "TRACKED"))
  }

  func session(_ session: ARSession, didFailWithError error: Error) {
    if phase == .calibrating || phase == .requesting {
      finishUnavailable("前摄追踪失败，继续只记录 Pencil")
    } else if phase == .ready {
      phase = .unavailable
      quality = "UNAVAILABLE"
      status = "前摄追踪中断，Pencil 仍继续记录"
      onTrackingChange?(false, "ARSESSION_ERROR")
    }
  }

  private static func cameraPlaneFeature(face: ARFaceAnchor, camera: ARCamera) -> Point? {
    let cameraFromFace = simd_inverse(camera.transform) * face.transform
    let left = cameraFromFace * face.leftEyeTransform * SIMD4<Float>(0, 0, 0, 1)
    let right = cameraFromFace * face.rightEyeTransform * SIMD4<Float>(0, 0, 0, 1)
    let eye = (left + right) * 0.5
    let look = cameraFromFace * SIMD4<Float>(face.lookAtPoint.x, face.lookAtPoint.y, face.lookAtPoint.z, 1)
    let dz = look.z - eye.z
    guard abs(dz) > 1e-5 else { return nil }
    let scale = -eye.z / dz
    let x = Double(eye.x + scale * (look.x - eye.x))
    let y = Double(eye.y + scale * (look.y - eye.y))
    guard x.isFinite, y.isFinite, abs(x) < 5, abs(y) < 5 else { return nil }
    return Point(x, y)
  }
}
