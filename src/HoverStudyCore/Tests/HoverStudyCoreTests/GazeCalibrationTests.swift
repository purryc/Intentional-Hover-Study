import XCTest
@testable import HoverStudyCore

final class GazeCalibrationTests: XCTestCase {
  func testAffineFitUsesTwoDimensionalCalibrationPoints() {
    let pairs = (0..<3).flatMap { row in
      (0..<3).map { col in
        let raw = Point(Double(col) * 0.04 - 0.04, Double(row) * 0.05 - 0.05)
        return GazeCalibrationPair(raw: raw,
          screen: Point(1150 + 260 * raw.x + 80 * raw.y, 600 - 75 * raw.x + 310 * raw.y))
      }
    }
    let fit = GazeAffineCalibration.fit(pairs)
    XCTAssertNotNil(fit)
    let result = fit?.map(Point(0.015, -0.025))
    XCTAssertEqual(result?.x ?? 0, 1150 + 260 * 0.015 - 80 * 0.025, accuracy: 0.001)
    XCTAssertEqual(result?.y ?? 0, 600 - 75 * 0.015 - 310 * 0.025, accuracy: 0.001)
  }

  func testDegenerateOrNonFiniteCalibrationIsRejected() {
    let same = Array(repeating: GazeCalibrationPair(raw: Point(1, 1), screen: Point(2, 2)), count: 9)
    XCTAssertNil(GazeAffineCalibration.fit(same))
    let invalid = (0..<9).map { i in
      GazeCalibrationPair(raw: Point(Double(i), i == 8 ? .nan : Double(i % 3)), screen: Point(100, 100))
    }
    XCTAssertNil(GazeAffineCalibration.fit(invalid))
  }

  func testNewGazeProtocolIsOptIn() {
    var config = V2Config()
    XCTAssertEqual(config.protocolVersion, "HOVER_INTENT_V2_3")
    config.revision?.gazeCollection = true
    XCTAssertEqual(config.protocolVersion, "HOVER_INTENT_V2_4")
    config.revision?.gazeCollection = false
    XCTAssertEqual(config.protocolVersion, "HOVER_INTENT_V2_3")
  }
}
