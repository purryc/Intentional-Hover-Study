import HoverStudyCore
import SwiftUI

struct ProtocolScreen: View {
  @State private var legacy =
    !ProcessInfo.processInfo.arguments.contains("--v2-demo")
    && (ProcessInfo.processInfo.arguments.contains("--legacy")
      || ProcessInfo.processInfo.arguments.contains("--ui-testing")
      || ProcessInfo.processInfo.arguments.contains("--demo")
      || ProcessInfo.processInfo.arguments.contains("--smoke")
      || UserDefaults.standard.data(forKey: "HoverStudy.active.v1") != nil)
  var body: some View {
    if legacy { LegacyStudyHost(switchProtocol: { legacy = false }) }
    else { V2StudyScreen() }
  }
}
struct LegacyStudyHost: View {
  @StateObject private var store = StudyStore()
  @Environment(\.scenePhase) private var phase
  let switchProtocol: () -> Void
  var body: some View {
    StudyScreen(store: store).overlay(alignment: .bottomLeading) {
      if store.canConfigure { Button("切换 V2 · 14 类任务", action: switchProtocol).padding(20) }
    }.onChange(of: phase) { if $0 != .active { store.background() } }
  }
}
struct V2StudyScreen: View {
  @StateObject private var store = V2Store()
  @Environment(\.scenePhase) private var phase
  @State private var configurationOpen = true
  @State private var parametersOpen = false
  var body: some View {
    GeometryReader { geometry in
      let scale = min(geometry.size.width / 1366, geometry.size.height / 1024)
      V2CaptureView(store: store, scale: scale, revision: store.revision)
        .overlay(alignment: .topLeading) {
          ZStack(alignment: .topLeading) {
            dashboard.frame(width: 820, height: 930).offset(x: 56, y: 40)
            prompt.frame(width: 390, height: 194, alignment: .topLeading).offset(x: 976)
            if store.gaze.isCalibrating {
              Rectangle().fill(Color.black.opacity(0.93)).frame(width: 390, height: 830)
                .offset(x: 976, y: 194)
              if let target = store.gaze.target {
                Circle().fill(Color.cyan).frame(width: 22, height: 22)
                  .overlay(Circle().stroke(.white, lineWidth: 3))
                  .position(x: 976 + target.x, y: 194 + target.y)
              }
            }
          }.frame(width: 1366, height: 1024, alignment: .topLeading).scaleEffect(scale, anchor: .topLeading)
        }.onAppear { store.setGeometry(geometry.size) }.onChange(of: geometry.size) { store.setGeometry($0) }
    }.ignoresSafeArea().onChange(of: phase) { if $0 != .active { store.background() } }
      .sheet(item: $store.shareFile) { ShareSheet(url: $0.url) }
  }
  private var prompt: some View {
    let ended = store.engine.state == .ended
    return VStack(alignment: .leading, spacing: 7) {
      Text(store.gaze.isCalibrating ? "前摄视线校准" : store.storageLoading ? "实验准备" : ended ? "本组结束" : store.engine.current?.task.title ?? "Hover Intent Study")
        .font(.system(size: 14)).foregroundStyle(.gray)
      Text(store.gaze.isCalibrating ? "请依次只看手机区内的圆点，保持握姿" : store.storageLoading ? "正在检查已有采集数据" : ended ? "本组结束，请选择下一组任务" : store.engine.current?.instruction ?? "选择姿势和任务，开始实验")
        .font(.system(size: 21, weight: .bold))
        .fixedSize(horizontal: false, vertical: true).lineSpacing(2)
      Text(store.gaze.isCalibrating ? store.gaze.progress : store.storageLoading ? "任务清单在左侧" : ended ? store.engine.summary : store.engine.progress)
        .font(.system(size: 18, weight: .semibold))
      Text(promptStatus).font(.system(size: 14))
        .foregroundStyle(store.engine.state == .paused || store.error != nil ? .orange : .gray)
    }.padding(.horizontal, 15).padding(.top, 12).foregroundStyle(.white)
      .accessibilityElement(children: .combine).accessibilityIdentifier("v2-participant-prompt")
  }
  private var promptStatus: String {
    if store.gaze.isCalibrating { return "校准结束后自动开始；无需点击" }
    if store.storageLoading { return "检查完成后可继续未结束的任务" }
    if store.error != nil { return "保存暂停 · 点击“重做当前次”重试保存" }
    if store.engine.state == .ended { return "可调整左侧任务清单后开始新实验" }
    if store.engine.state == .paused { return "已暂停 · 点击“开始实验”继续当前次" }
    if store.engine.current?.scene == .video && store.engine.current?.condition != "HOVER" {
      return store.engine.sceneState.videoPaused ? "视频已暂停 · 点按继续" : "静音播放 · 上下滑动切换"
    }
    return store.engine.hint
  }
  private var dashboard: some View {
    let e = store.engine
    return VStack(alignment: .leading, spacing: 20) {
      HStack {
        Text("Hover Intent Study").font(.system(size: 34, weight: .bold))
        Spacer()
        Text(store.simulation ? "模拟" : "正式采集").foregroundStyle(store.simulation ? .orange : .blue)
      }
      HStack(spacing: 12) {
        Button("开始实验") { store.startOrResume() }.buttonStyle(.borderedProminent)
          .disabled(store.gaze.isCalibrating || !store.ready || store.error != nil || (!e.configurable && e.state != .paused)
            || (e.configurable && store.planned.isEmpty)).accessibilityIdentifier("v2-start")
        Button("重做当前次") { store.redoOrRecover() }.buttonStyle(.bordered)
          .disabled(store.error == nil && (e.configurable || !store.ready)).accessibilityIdentifier("v2-redo")
        Button("导出 CSV") { store.export() }.buttonStyle(.bordered)
          .disabled(store.error != nil).accessibilityIdentifier("v2-export")
        Button("结束实验") { store.endSession() }.buttonStyle(.bordered)
          .disabled(e.configurable || store.storageLoading || store.error != nil)
          .accessibilityIdentifier("v2-end")
      }.controlSize(.large)
      if store.storageLoading {
        HStack(spacing: 12) {
          ProgressView().tint(.white)
          Text("正在检查已有采集数据，完成后即可开始实验")
            .font(.subheadline)
        }
        .foregroundStyle(.white)
        .accessibilityIdentifier("v2-storage-loading")
      }
      ScrollView {
        VStack(alignment: .leading, spacing: 20) {
          DisclosureGroup("实验配置", isExpanded: $configurationOpen) {
              VStack(alignment: .leading, spacing: 16) {
                HStack(spacing: 24) {
                  TextField("参与者", text: $store.participant).textFieldStyle(.roundedBorder).frame(width: 160)
                    .disabled(!e.configurable)
                  Picker("姿势", selection: $store.config.posture) {
                    Text("单手拇指").tag("THUMB")
                    Text("托握＋食指").tag("CRADLE_INDEX")
                  }.pickerStyle(.segmented).frame(width: 330).disabled(!e.configurable)
                }
                if store.config.revision != nil {
                  Toggle("记录前摄视线（试验）", isOn: Binding(
                    get: { store.config.revision?.gazeCollection == true },
                    set: { if e.configurable { store.config.revision?.gazeCollection = $0 } }))
                    .accessibilityIdentifier("v2-gaze-opt-in")
                    .disabled(!e.configurable)
                  Text("开始后自动校准；只保存视线坐标与质量，不保存面部画面。视线不会影响任务成功判定。")
                    .font(.caption).foregroundStyle(.gray)
                }
                ForEach(["A", "B", "C"], id: \.self) { group in
                  VStack(alignment: .leading, spacing: 7) {
                    Toggle(isOn: groupSelection(group)) {
                      Label(group == "A" ? "A · 自然基线" : group == "B" ? "B · 主动 Hover" : "C · 混淆任务",
                        systemImage: groupSelection(group).wrappedValue ? "checkmark.square.fill" : "square")
                        .frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
                    }.toggleStyle(.button).buttonStyle(.plain).font(.subheadline.bold())
                      .accessibilityIdentifier("v2-group-\(group)")
                      .allowsHitTesting(e.configurable)
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 7) {
                      ForEach(V2Task.allCases.filter { $0.group == group }, id: \.self) { task in
                        Toggle(isOn: taskSelection(task)) {
                          Label(task.title, systemImage: store.config.tasks.contains(task) ? "checkmark.circle.fill" : "circle")
                            .frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
                        }.toggleStyle(.button).buttonStyle(.plain).font(.system(size: 16))
                          .padding(9).background(Color.white.opacity(0.045)).clipShape(RoundedRectangle(cornerRadius: 8))
                          .accessibilityIdentifier("v2-task-\(task.rawValue)")
                          .allowsHitTesting(e.configurable)
                      }
                    }
                  }
                }
                DisclosureGroup("实验参数", isExpanded: $parametersOpen) {
                  V2ParameterFields(draft: $store.config).frame(height: 390)
                    .disabled(!e.configurable)
                  Text(store.config.protocolVersion).font(.caption).foregroundStyle(.gray)
                }
              }.padding(.top, 14)
          }.tint(.blue)
          Text(store.countLabel).font(.title3.bold()).accessibilityIdentifier("v2-counts")
          HStack {
            Image(systemName: store.ready ? "checkmark.circle.fill" : "pencil.tip.crop.circle").foregroundStyle(store.ready ? .green : .orange)
            Text(store.simulation ? "模拟数据单独保存" : store.ready ? "Pencil 已就绪" : "请全屏横放 iPad，并将 Pencil 靠近屏幕").font(.subheadline)
          }
          if store.config.usesGazeCollection || e.config.usesGazeCollection {
            Text(store.gaze.status).font(.subheadline)
              .foregroundStyle(store.gaze.qualityPassed ? .green : .orange)
              .accessibilityIdentifier("v2-gaze-status")
          }
          if let error = store.error {
            VStack(alignment: .leading, spacing: 7) {
              Text("保存失败，点击“重做当前次”重试保存").foregroundStyle(.red)
              Text(error).font(.subheadline)
            }
          }
          Text("已落盘 \(store.stats.writtenSamples) 样本").font(.caption).foregroundStyle(.gray)
          if !store.notice.isEmpty { Text(store.notice).font(.subheadline).foregroundStyle(.orange) }
        }.padding(.trailing, 8)
      }
    }.foregroundStyle(.white)
  }
  private func taskSelection(_ task: V2Task) -> Binding<Bool> {
    Binding(get: { store.config.tasks.contains(task) }, set: { selected in
      guard store.engine.configurable else { return }
      store.config.tasks.removeAll { $0 == task }
      if selected { store.config.tasks.append(task) }
    })
  }
  private func groupSelection(_ group: String) -> Binding<Bool> {
    let tasks = V2Task.allCases.filter { $0.group == group }
    return Binding(get: { tasks.allSatisfy { store.config.tasks.contains($0) } }, set: { selected in
      guard store.engine.configurable else { return }
      store.config.tasks.removeAll { $0.group == group }
      if selected { store.config.tasks.append(contentsOf: tasks) }
    })
  }
}
struct V2ParameterFields: View {
  @Binding var draft: V2Config
  var body: some View {
    Form {
        Section("采集量") {
          Stepper("完整配平重复 \(draft.repetitions) 轮", value: $draft.repetitions, in: 1...10)
          if draft.revision != nil {
            Stepper("B 每套配平重复 \(draft.revision!.bRepetitions) 轮（每轮6次）", value: revisionBinding(\.bRepetitions), in: 1...10)
          }
          field("自然阅读秒数", $draft.readingSeconds)
          field("C3 自然短段秒数", $draft.snippetSeconds)
          field("短任务超时秒数", $draft.timeout)
        }
        Section("停留与间隔") {
          field("悬停选择 ms", $draft.dwellMs)
          field("起点稳定 ms", $draft.startMs)
          field("最大回调缺口 ms", $draft.gapMs)
          field("试次间隔秒", $draft.interval)
          field("移动开始阈值 pt", $draft.movementThreshold)
        }
        Section("目标几何") {
          ForEach(0..<3, id: \.self) { i in
            field("距离 \(i+1) pt", $draft.distances[i])
            field("直径 \(i+1) pt", $draft.diameters[i])
          }
          field("B / C 固定距离 pt", $draft.fixedDistance)
          if draft.revision != nil {
            ForEach(0..<3, id: \.self) { i in
              field("C1 直径 \(i+1) pt", Binding(get: { draft.revision!.cDiameters[i] }, set: { draft.revision!.cDiameters[i] = $0 }))
            }
            field("C2 小标记 pt", revisionBinding(\.cMarkerDiameter))
            field("C3 具体对象 pt", revisionBinding(\.cObjectDiameter))
            field("A/C 失败重试间隔秒", revisionBinding(\.retryInterval))
          }
        }
        Section("B4 空中圈选") {
          field("起点与闭合半径 pt", $draft.lassoRadius)
          field("最小离开距离 pt", $draft.lassoDeparture)
          field("最短路径 pt", $draft.lassoLength)
          field("最小围合面积 pt²", $draft.lassoArea)
          Stepper("最少 \(draft.lassoSamples) 个实测点", value: $draft.lassoSamples, in: 3...100)
        }
    }.environment(\.colorScheme, .dark)
  }
  private func revisionBinding<T>(_ key: WritableKeyPath<V2RevisionConfig, T>) -> Binding<T> {
    Binding(get: { draft.revision![keyPath: key] }, set: { draft.revision![keyPath: key] = $0 })
  }
  private func field(_ title: String, _ value: Binding<Double>) -> some View {
    HStack {
      Text(title)
      Spacer()
      TextField(title, value: value, format: .number).keyboardType(.decimalPad)
        .multilineTextAlignment(.trailing).frame(width: 110)
    }
  }
}
