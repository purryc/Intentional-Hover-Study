import SwiftUI
import HoverStudyCore

struct SettingsView: View {
    @ObservedObject var store: StudyStore
    @Environment(\.dismiss) private var dismiss
    @State private var draft = ExperimentConfig()
    @State private var distances = "120,220,320"
    @State private var sizes = "30,50,80"
    @State private var error = ""
    var body: some View {
        NavigationStack {
            Form {
                Section("目标几何 · 单位 pt") {
                    TextField("距离（逗号分隔）",text:$distances).keyboardType(.numbersAndPunctuation).accessibilityIdentifier("distance-values")
                    TextField("直径（逗号分隔）",text:$sizes).keyboardType(.numbersAndPunctuation).accessibilityIdentifier("diameter-values")
                    Text("起点固定为 (195,415)，目标上下方向均衡；超出手机区域的配置不能开始。")
                }
                Section("次数") {
                    Stepper("指向：每个距离 × 尺寸重复 \(draft.repetitions) 次",value:$draft.repetitions,in:2...40,step:2)
                    Stepper("校准：每方向 \(draft.calibrationRepetitions) 次",value:$draft.calibrationRepetitions,in:1...40)
                    Stepper("经过：每速度 \(draft.passRepetitions) 次",value:$draft.passRepetitions,in:2...40,step:2)
                    Stepper("向上滑动 \(draft.swipeRepetitions) 次",value:$draft.swipeRepetitions,in:1...100)
                    Text("TAP/HOVER 各使用一套指向次数，共同随机混合计数。")
                }
                Section("时长 · 单位 ms") {
                    number("起点稳定",value:$draft.startStableMs)
                    number("校准保持",value:$draft.calibrationHoldMs)
                    number("TAP/HOVER 指令提前显示",value:$draft.instructionMs)
                    number("试次间隔",value:$draft.interTrialMs)
                    number("目标出现后超时",value:$draft.timeoutMs)
                    Text("目标处不设指向停留门槛。悬停结束后给接触事件 500 ms 衔接宽限。")
                }
                Section("滑动 · 单位 pt") {
                    number("滑动开始位移",value:$draft.swipeStartThreshold)
                    number("完成所需向上位移",value:$draft.swipeCompletionDistance)
                }
            }.navigationTitle("实验设置")
                .safeAreaInset(edge: .top) {
                    if !error.isEmpty { Text(error).foregroundStyle(.red).padding().frame(maxWidth:.infinity,alignment:.leading).background(Color.red.opacity(0.08)).accessibilityIdentifier("config-error") }
                }
                .toolbar {
                    ToolbarItem(placement:.cancellationAction) { Button("取消") { dismiss() } }
                    ToolbarItem(placement:.confirmationAction) { Button("保存") { save() } }
                }
                .onAppear {
                    draft = store.config; distances = draft.distances.map { String(Int($0)) }.joined(separator:","); sizes = draft.diameters.map{String(Int($0))}.joined(separator:",")
                }
        }
    }
    private func number(_ label:String,value:Binding<Double>) -> some View {
        HStack { Text(label); Spacer(); TextField(label,value:value,format:.number).multilineTextAlignment(.trailing).keyboardType(.decimalPad).frame(width:130) }
    }
    private func parse(_ text:String) -> [Double]? {
        let parts = text.replacingOccurrences(of:"，",with:",").split(separator:",",omittingEmptySubsequences:false)
        let values = parts.compactMap{Double($0.trimmingCharacters(in:.whitespaces))}
        return values.count == parts.count ? values : nil
    }
    private func save() {
        guard let a = parse(distances),let w = parse(sizes), Set(a).count == a.count, Set(w).count == w.count else { error = "请填写不重复的数字，用逗号分隔。";return }
        draft.distances = a;draft.diameters = w
        do { try draft.validate(); store.config = draft; dismiss() } catch { self.error = error.localizedDescription }
    }
}
