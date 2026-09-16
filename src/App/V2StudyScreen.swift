import HoverStudyCore
import SwiftUI

struct ProtocolScreen: View {
  @State private var legacy =
    !ProcessInfo.processInfo.arguments.contains("--v2-demo")
    && (ProcessInfo.processInfo.arguments.contains("--legacy")
      || (ProcessInfo.processInfo.arguments.contains("--ui-testing")
        && !ProcessInfo.processInfo.arguments.contains("--v2-demo"))
      || ProcessInfo.processInfo.arguments.contains("--demo")
      || ProcessInfo.processInfo.arguments.contains("--smoke")
      || UserDefaults.standard.data(forKey: "HoverStudy.active.v1") != nil)
  var body: some View {
    if legacy {
      LegacyStudyHost(switchProtocol: { legacy = false })
    } else {
      V2StudyScreen(switchProtocol: { legacy = true })
    }
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
  @State private var settings = false
  @State private var history = false
  let switchProtocol: () -> Void
  var body: some View {
    GeometryReader { geometry in
      let scale = min(geometry.size.width / 1366, geometry.size.height / 1024)
      V2CaptureView(store: store, scale: scale, revision: store.revision)
        .overlay(alignment: .topLeading) {
          ZStack(alignment: .topLeading) {
            ScrollView { dashboard }.frame(width: 820, height: 930).offset(x: 56, y: 40)
            prompt.frame(width: 390, height: 194, alignment: .topLeading).offset(x: 976)
            if store.engine.state == .paused || store.error != nil {
              VStack(spacing: 14) {
                Image(systemName: "pause.circle").font(.system(size: 45))
                Text(store.error == nil ? "已暂停" : "保存暂停").font(.title.bold())
                Text("继续后重新开始当前任务")
              }.foregroundStyle(.black).frame(width: 390, height: 220).background(
                .white.opacity(0.96)
              ).offset(x: 976, y: 460)
            }
          }.frame(width: 1366, height: 1024, alignment: .topLeading).scaleEffect(
            scale, anchor: .topLeading)
        }
        .onAppear { store.setGeometry(geometry.size) }.onChange(of: geometry.size) {
          store.setGeometry($0)
        }
    }.ignoresSafeArea().onChange(of: phase) { if $0 != .active { store.background() } }
      .sheet(isPresented: $settings) { V2Settings(store: store) }
      .sheet(item: $store.shareFile) { ShareSheet(url: $0.url) }
      .sheet(isPresented: $history) {
        NavigationStack {
          List(store.files, id: \.self) { file in
            Button(file.lastPathComponent) {
              history = false
              DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { store.export(file) }
            }
          }.navigationTitle("历史 CSV").toolbar { Button("关闭") { history = false } }
        }
      }
  }
  private var prompt: some View {
    VStack(alignment: .leading, spacing: 7) {
      Text(store.engine.current?.task.title ?? "Hover Intent Study · V2").font(.system(size: 14))
        .foregroundStyle(.gray)
      Text(store.engine.current?.instruction ?? "按任务自然操作手机区域").font(
        .system(size: 21, weight: .bold)
      ).fixedSize(horizontal: false, vertical: true).lineSpacing(2)
      Text(store.engine.progress).font(.system(size: 18, weight: .semibold))
      Text(store.engine.hint).font(.system(size: 14)).foregroundStyle(.gray)
    }.padding(.horizontal, 15).padding(.top, 12).foregroundStyle(.white)
      .accessibilityElement(children: .combine).accessibilityIdentifier("v2-participant-prompt")
  }
  private var dashboard: some View {
    let e = store.engine
    return VStack(alignment: .leading, spacing: 19) {
      HStack {
        Text("Hover Intent Study").font(.system(size: 34, weight: .bold))
        Spacer()
        Text("\((e.configurable ? store.config : e.config).revision == nil ? "V2.1" : "V2.2") · \(store.simulation ? "模拟" : "正式采集")").foregroundStyle(
          store.simulation ? .orange : .blue)
      }
      Text("自然基线 → 主动 Hover → 混淆任务").foregroundStyle(.gray)
      HStack(spacing: 24) {
        TextField("参与者", text: $store.participant).textFieldStyle(.roundedBorder).frame(width: 160)
          .disabled(!e.configurable)
        Picker("姿势", selection: $store.config.posture) {
          Text("单手拇指").tag("THUMB")
          Text("托握＋食指").tag("CRADLE_INDEX")
        }.pickerStyle(.segmented).frame(width: 330).disabled(!e.configurable)
        Button("参数设置") { settings = true }.disabled(!e.configurable)
      }
      if e.configurable {
        VStack(alignment: .leading, spacing: 12) {
          HStack {
            Text("选择本次任务").font(.headline)
            Spacer()
            Button("全选") { store.config.tasks = V2Task.allCases }
            Button("清空") { store.config.tasks = [] }
          }
          ForEach(["A", "B", "C"], id: \.self) { group in
            VStack(alignment: .leading, spacing: 6) {
              Text(group == "A" ? "A · 自然基线" : group == "B" ? "B · 主动 Hover" : "C · 混淆任务").font(
                .caption
              ).foregroundStyle(.gray)
              LazyVGrid(
                columns: [GridItem(.flexible()), GridItem(.flexible())], alignment: .leading,
                spacing: 7
              ) {
                ForEach(V2Task.allCases.filter { $0.group == group }, id: \.self) { task in
                  Button {
                    if store.config.tasks.contains(task) {
                      store.config.tasks.removeAll { $0 == task }
                    } else {
                      store.config.tasks.append(task)
                    }
                  } label: {
                    HStack {
                      Image(
                        systemName: store.config.tasks.contains(task)
                          ? "checkmark.circle.fill" : "circle"
                      ).foregroundStyle(store.config.tasks.contains(task) ? .blue : .gray)
                      Text(task.title).font(.system(size: 16))
                      Spacer()
                    }.padding(9).background(Color.white.opacity(0.045)).clipShape(
                      RoundedRectangle(cornerRadius: 8))
                  }.buttonStyle(.plain).accessibilityIdentifier("v2-task-\(task.rawValue)")
                }
              }
            }
          }
          Text(store.countLabel).font(.title3.bold()).accessibilityIdentifier("v2-counts")
          Text("姿势和任务按需选；阅读不答题，输入任务已移除。").font(.caption).foregroundStyle(.gray)
        }.padding(20).background(Color.white.opacity(0.06)).clipShape(
          RoundedRectangle(cornerRadius: 14))
      } else {
        VStack(alignment: .leading, spacing: 12) {
          Text(e.current?.task.title ?? "本组结束").font(.title.bold())
          Text(e.progress).font(.title2)
          Text(e.summary).foregroundStyle(.gray)
          Text(
            "整个会话：\(min(e.index+1,e.schedule.count)) / \(e.schedule.count) · 姿势：\(store.config.posture == "THUMB" ? "单手拇指" : "托握＋食指")"
          ).font(.subheadline)
          Text("条件：\(e.current?.condition ?? "") · 场景：\(e.current?.scene.rawValue ?? "")")
            .foregroundStyle(.gray)
        }.padding(22).frame(maxWidth: .infinity, alignment: .leading).background(
          Color.white.opacity(0.06)
        ).clipShape(RoundedRectangle(cornerRadius: 14))
      }
      HStack {
        Image(systemName: store.ready ? "checkmark.circle.fill" : "pencil.tip.crop.circle")
          .foregroundStyle(store.ready ? .green : .orange)
        Text(
          store.simulation
            ? "模拟数据单独保存，不进入正式采集"
            : store.ready ? "已收到 Pencil 悬停，尺寸符合正式采集" : "请全屏横放目标 iPad，并将 Pencil 靠近屏幕"
        ).font(.subheadline)
      }
      HStack(spacing: 10) {
        Button("开始实验") { store.start() }.buttonStyle(.borderedProminent).disabled(
          !e.configurable || !store.ready || store.planned.isEmpty || store.error != nil
        ).accessibilityIdentifier("v2-start")
        Button(e.state == .paused ? "继续" : "暂停") {
          if e.state == .paused { e.resume(store.clock) } else { e.pause(store.clock) }
        }.buttonStyle(.bordered).disabled(e.configurable || store.error != nil || !store.ready)
        Button(e.requiresValidCompletion ? "重新开始本题" : "跳过") { e.skip(store.clock) }.buttonStyle(.bordered).disabled(
          !e.running || store.error != nil)
        Button("重做当前次") { e.redo(store.clock) }.buttonStyle(.bordered).disabled(
          e.configurable || store.error != nil || !store.ready)
        Button("结束") { e.end(store.clock) }.buttonStyle(.bordered).disabled(e.configurable)
      }.controlSize(.large)
      if let error = store.error {
        VStack(alignment: .leading) {
          Text("保存失败，实验已暂停").foregroundStyle(.red)
          Text(error)
          Button("重试保存") { store.retry() }
        }
      }
      HStack {
        Button("导出 CSV 快照") { store.export() }.buttonStyle(.borderedProminent)
        Button("历史文件") {
          store.loadFiles()
          history = true
        }.buttonStyle(.bordered)
        Spacer()
        Text("已落盘 \(store.stats.writtenSamples) 样本").font(.caption).foregroundStyle(.gray)
      }
      if store.simulation {
        Button("模拟完成一次") { store.simulate() }.disabled(!e.running || store.simulating)
          .accessibilityIdentifier("v2-simulate")
      }
      if e.configurable {
        HStack {
          Toggle(
            "模拟输入", isOn: Binding(get: { store.simulation }, set: { store.changeSimulation($0) })
          ).frame(width: 190)
          Spacer()
          Button("旧协议 Test 0–4", action: switchProtocol)
        }
      }
      if !store.notice.isEmpty { Text(store.notice).font(.subheadline).foregroundStyle(.orange) }
    }.foregroundStyle(.white)
  }
}
struct V2Settings: View {
  @ObservedObject var store: V2Store
  @Environment(\.dismiss) private var dismiss
  @State private var draft = V2Config()
  @State private var message = ""
  var body: some View {
    NavigationStack {
      Form {
        Section("采集量") {
          Stepper("完整配平重复 \(draft.repetitions) 轮", value: $draft.repetitions, in: 1...10)
          if draft.revision != nil {
            Stepper("B 每套配平重复 \(draft.revision!.bRepetitions) 轮（每轮6次）", value: revisionBinding(\.bRepetitions), in: 1...10)
            Text("A/C 失败重试原题；B 成功或失败均进入下一次。")
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
        if !message.isEmpty { Text(message).foregroundStyle(.red) }
      }.navigationTitle("V2 实验参数").toolbar {
        ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
        ToolbarItem(placement: .confirmationAction) {
          Button("保存") {
            do {
              try draft.validate()
              store.config = draft
              dismiss()
            } catch { message = error.localizedDescription }
          }
        }
      }
    }.onAppear { draft = store.config }
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
