import Foundation

/// Device-specific affine mapping from an ARKit camera-plane feature to canvas points.
/// It is a fitted estimate, never a guarantee of object-level gaze accuracy.
public struct GazeCalibrationPair: Sendable {
  public let raw: Point
  public let screen: Point
  public init(raw: Point, screen: Point) { self.raw = raw; self.screen = screen }
}

public struct GazeAffineCalibration: Sendable {
  public let center: Point
  public let scale: Point
  public let xCoefficients: [Double]
  public let yCoefficients: [Double]

  public func map(_ raw: Point) -> Point? {
    guard raw.x.isFinite, raw.y.isFinite else { return nil }
    let u = (raw.x - center.x) / scale.x
    let v = (raw.y - center.y) / scale.y
    let x = xCoefficients[0] + xCoefficients[1] * u + xCoefficients[2] * v
    let y = yCoefficients[0] + yCoefficients[1] * u + yCoefficients[2] * v
    return x.isFinite && y.isFinite ? Point(x, y) : nil
  }

  public static func fit(_ pairs: [GazeCalibrationPair]) -> GazeAffineCalibration? {
    guard pairs.count >= 6, pairs.allSatisfy({
      [$0.raw.x, $0.raw.y, $0.screen.x, $0.screen.y].allSatisfy(\.isFinite)
    }) else { return nil }
    let cx = pairs.map(\.raw.x).reduce(0, +) / Double(pairs.count)
    let cy = pairs.map(\.raw.y).reduce(0, +) / Double(pairs.count)
    let sx = sqrt(pairs.map { pow($0.raw.x - cx, 2) }.reduce(0, +) / Double(pairs.count))
    let sy = sqrt(pairs.map { pow($0.raw.y - cy, 2) }.reduce(0, +) / Double(pairs.count))
    guard sx > 1e-8, sy > 1e-8 else { return nil }
    var ata = Array(repeating: Array(repeating: 0.0, count: 3), count: 3)
    var atx = Array(repeating: 0.0, count: 3)
    var aty = Array(repeating: 0.0, count: 3)
    for pair in pairs {
      let row = [1.0, (pair.raw.x - cx) / sx, (pair.raw.y - cy) / sy]
      for i in 0..<3 {
        atx[i] += row[i] * pair.screen.x
        aty[i] += row[i] * pair.screen.y
        for j in 0..<3 { ata[i][j] += row[i] * row[j] }
      }
    }
    guard let bx = solve(ata, atx), let by = solve(ata, aty) else { return nil }
    return GazeAffineCalibration(center: Point(cx, cy), scale: Point(sx, sy), xCoefficients: bx, yCoefficients: by)
  }

  private static func solve(_ a: [[Double]], _ b: [Double]) -> [Double]? {
    var rows = (0..<3).map { a[$0] + [b[$0]] }
    for col in 0..<3 {
      let pivot = (col..<3).max(by: { abs(rows[$0][col]) < abs(rows[$1][col]) })!
      guard abs(rows[pivot][col]) > 1e-7 else { return nil }
      rows.swapAt(col, pivot)
      let divisor = rows[col][col]
      for j in col...3 { rows[col][j] /= divisor }
      for i in 0..<3 where i != col {
        let factor = rows[i][col]
        for j in col...3 { rows[i][j] -= factor * rows[col][j] }
      }
    }
    return rows.map { $0[3] }
  }
}
