// swift-tools-version: 5.9
import PackageDescription
let package = Package(name: "HoverStudyCore", platforms: [.iOS(.v16), .macOS(.v13)], products: [.library(name: "HoverStudyCore", targets: ["HoverStudyCore"])], targets: [.target(name: "HoverStudyCore"), .testTarget(name: "HoverStudyCoreTests", dependencies: ["HoverStudyCore"])])
