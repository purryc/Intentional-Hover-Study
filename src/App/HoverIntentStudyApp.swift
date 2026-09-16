import SwiftUI
import HoverStudyCore

@main struct HoverIntentStudyApp: App {
    @UIApplicationDelegateAdaptor(OrientationDelegate.self) private var appDelegate
    @Environment(\.scenePhase) private var phase
    var body: some Scene {
        WindowGroup {
            ProtocolScreen()
                .preferredColorScheme(.dark)
                .statusBarHidden()
                .persistentSystemOverlays(.hidden)

        }
    }
}
final class OrientationDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication, supportedInterfaceOrientationsFor window: UIWindow?) -> UIInterfaceOrientationMask { .landscape }
}
struct StudyScreen: View {
    @ObservedObject var store: StudyStore
    @State private var settings = false
    @State private var files = false
    var body: some View {
        GeometryReader { geometry in
            let s = min(geometry.size.width / 1366, geometry.size.height / 1024)
            PencilCaptureView(store: store, scale: s, revision: store.revision)
            .frame(width: geometry.size.width, height: geometry.size.height)
            .overlay(alignment: .topLeading) {
                board.scaleEffect(s, anchor: .topLeading)
                    .frame(width: 1366 * s, height: 1024 * s, alignment: .topLeading)
            }
            .onAppear {
                store.setGeometry(geometry.size)
                if let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene, !scene.interfaceOrientation.isLandscape {
                    scene.requestGeometryUpdate(.iOS(interfaceOrientations: .landscapeRight))
                }
            }
            .onChange(of: geometry.size) { store.setGeometry($0) }
        }
        .ignoresSafeArea()
        .sheet(isPresented: $settings) { SettingsView(store:store) }
        .sheet(isPresented: $files) { fileList }
        .sheet(item: $store.shareFile) { item in ShareSheet(url:item.url) }
    }
    private var board: some View {
        ZStack(alignment: .topLeading) {
            ScrollView { dashboard }.frame(width:820,height:920).offset(x:56,y:52)
            taskPrompt.frame(width:390,height:194,alignment:.topLeading).offset(x:976,y:0)
            if store.engine.state == .paused || store.storageError != nil {
                VStack(spacing:16) {
                    Image(systemName:"pause.circle").font(.system(size:46))
                    Text(store.storageError != nil ? "保存暂停" : "已暂停").font(.system(size:28,weight:.bold))
                    Text("继续后，从当前任务起点重做").font(.system(size:18))
                }.foregroundStyle(.black).frame(width:390,height:240).background(.white.opacity(0.95)).offset(x:976,y:460)
            }
        }.frame(width:1366,height:1024,alignment:.topLeading)
    }
    private var taskPrompt: some View {
        VStack(alignment:.leading,spacing:9) {
            Text(store.engine.state == .idle ? store.selectedTest.title : store.engine.test.title)
                .font(.system(size:15,weight:.medium)).foregroundStyle(.gray)
            Text(store.prompt).font(.system(size:24,weight:.bold)).fixedSize(horizontal:false,vertical:true).lineSpacing(3)
            Text(store.engine.progress).font(.system(size:19,weight:.semibold)).foregroundStyle(.white)
            Text("当前：\(store.engine.state.hint)").font(.system(size:16)).foregroundStyle(.gray)
        }.foregroundStyle(.white).padding(.horizontal,16).padding(.top,18)
            .accessibilityElement(children:.ignore)
            .accessibilityLabel("\(store.engine.state == .idle ? store.selectedTest.title : store.engine.test.title)。\(store.prompt)。\(store.engine.progress)。当前：\(store.engine.state.hint)")
            .accessibilityIdentifier("participant-task-progress")
    }
    private var dashboard: some View {
        VStack(alignment:.leading,spacing:20) {
            HStack(alignment:.firstTextBaseline) {
                Text("Hover Intent Study").font(.system(size:34,weight:.bold))
                Spacer()
                Text(store.simulation ? "模拟采集" : "研究采集").font(.system(size:16,weight:.semibold)).padding(.horizontal,14).padding(.vertical,8).background(store.simulation ? Color.orange.opacity(0.2) : Color.blue.opacity(0.2)).clipShape(Capsule())
            }
            Text("拇指绑笔 · 笔尖点击 / 滑动 · 简单悬停光标").foregroundStyle(.gray)
            HStack(spacing:18) {
                VStack(alignment:.leading,spacing:8) {
                    Text("参与者编号").font(.caption).foregroundStyle(.gray)
                    TextField("P01",text:$store.participant).textFieldStyle(.roundedBorder).autocorrectionDisabled().textInputAutocapitalization(.characters).disabled(!store.canConfigure)
                }.frame(width:170)
                VStack(alignment:.leading,spacing:8) {
                    Text("实验").font(.caption).foregroundStyle(.gray)
                    Picker("实验",selection:$store.selectedTest) { ForEach(TestKind.allCases,id:\.self) { Text($0.title).tag($0) } }.pickerStyle(.menu).disabled(!store.canConfigure)
                }
                Spacer()
                Button("实验设置") { settings = true }.disabled(!store.canConfigure)
            }
            HStack(spacing:10) {
                Image(systemName:store.ready ? "checkmark.circle.fill" : "pencil.tip.crop.circle").foregroundStyle(store.ready ? .green : .orange)
                Text(store.sensorMessage).font(.system(size:17))
            }.padding(16).frame(maxWidth:.infinity,alignment:.leading).background(Color.white.opacity(0.07)).clipShape(RoundedRectangle(cornerRadius:12))
            VStack(alignment:.leading,spacing:12) {
                Text("当前实验").font(.caption).foregroundStyle(.gray)
                Text(store.engine.state == .idle ? "准备开始" : store.engine.test.title).font(.system(size:24,weight:.semibold))
                Text(store.engine.progress).font(.system(size:22,weight:.medium))
                Text(store.engine.summary).foregroundStyle(.gray)
                if let c = store.engine.current { Text("条件：\(c.mode) · 距离 \(Int(c.distance)) pt · 目标 \(Int(c.diameter)) pt · \(c.direction)").font(.system(size:15)).foregroundStyle(.gray) }
                Text("状态：\(store.engine.state.rawValue)").font(.system(.caption,design:.monospaced)).foregroundStyle(.gray)
            }.padding(22).frame(maxWidth:.infinity,alignment:.leading).background(Color.white.opacity(0.07)).clipShape(RoundedRectangle(cornerRadius:14))
            HStack(spacing:12) {
                Button("开始实验") { store.start() }.buttonStyle(.borderedProminent).disabled(!store.canBegin).accessibilityIdentifier("start-test")
                Button(store.engine.state == .paused ? "继续" : "暂停") { if store.engine.state == .paused { store.resume() } else { store.pause() } }.buttonStyle(.bordered).disabled(!store.canControl || [.idle,.ended].contains(store.engine.state))
                Button("跳过") { store.skip() }.buttonStyle(.bordered).disabled(!store.canControl || !store.engine.isRunning)
                Button("重做当前次") { store.repeatTrial() }.buttonStyle(.bordered).disabled(!store.canControl || [.idle].contains(store.engine.state) || !store.ready)
                Button("结束实验") { store.end() }.buttonStyle(.bordered).disabled([.idle,.ended].contains(store.engine.state))
            }.controlSize(.large)
            if let error = store.storageError {
                VStack(alignment:.leading,spacing:8) {
                    Text("保存失败，实验已暂停").font(.headline).foregroundStyle(.red)
                    Text(error).font(.subheadline)
                    Button("重试保存") { store.retryStorage() }.buttonStyle(.borderedProminent)
                }
            }
            VStack(alignment:.leading,spacing:12) {
                HStack { Text("今天的数据").font(.headline); Spacer(); Text(store.storageError != nil ? "保存失败" : store.stats.pendingRecords > 0 ? "正在写入" : "已保存").foregroundStyle(store.storageError != nil ? .red : .green) }
                Text(store.stats.currentFile.isEmpty ? "正在准备文件" : store.stats.currentFile).font(.system(size:17,design:.monospaced))
                HStack(spacing:30) {
                    Text("落盘样本 \(store.stats.writtenSamples)")
                    Text("试次记录 \(store.stats.writtenTrials)")
                    Text("待写入 \(store.stats.pendingRecords)")
                }.font(.system(size:16)).foregroundStyle(.gray)
                HStack {
                    Button("导出今天的 CSV") { store.export() }.buttonStyle(.borderedProminent).disabled(store.storageError != nil)
                    Button("历史文件") { store.loadFiles(); files = true }.buttonStyle(.bordered)
                }
            }.padding(22).frame(maxWidth:.infinity,alignment:.leading).background(Color.white.opacity(0.07)).clipShape(RoundedRectangle(cornerRadius:14))
            HStack {
                Toggle("研究者调试信息",isOn:$store.showDebug).toggleStyle(.switch).frame(width:250)
                Spacer()
                if store.canConfigure { Toggle("模拟输入",isOn:Binding(get:{store.simulation},set:{store.changeMode($0)})).frame(width:180) }
                if store.simulation { Button("模拟完成一次") { store.simulateTrial() }.disabled(!store.engine.isRunning || store.runningSyntheticTrial).accessibilityIdentifier("simulate-trial") }
            }
            if store.showDebug, let input = store.latestInput {
                Text(String(format:"X %.2f   Y %.2f   localX %.2f   localY %.2f   Z %@\n%@ · %@ · %@",input.point.x,input.point.y,input.point.x-976,input.point.y-194,input.z.map{String(format:"%.4f",$0)} ?? "—",input.source,input.phase,store.engine.state.rawValue)).font(.system(size:15,design:.monospaced)).foregroundStyle(.gray)
            }
            if !store.notice.isEmpty { Text(store.notice).font(.system(size:15)).foregroundStyle(.orange) }
        }.foregroundStyle(.white)
    }
    private var fileList: some View {
        NavigationStack {
            List(store.previousFiles,id:\.self) { file in
                Button { files = false; DispatchQueue.main.asyncAfter(deadline:.now()+0.4) { store.export(file) } } label: {
                    HStack { Text(file.lastPathComponent); Spacer(); Image(systemName:"square.and.arrow.up") }
                }
            }.navigationTitle("已保存的 CSV").toolbar { Button("关闭") { files = false } }
        }
    }
}
struct ShareSheet: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> UIActivityViewController { UIActivityViewController(activityItems:[url],applicationActivities:nil) }
    func updateUIViewController(_ controller:UIActivityViewController,context:Context) {}
}
