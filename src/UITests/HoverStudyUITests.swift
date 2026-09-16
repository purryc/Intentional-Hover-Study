import XCTest

final class HoverStudyUITests: XCTestCase {
    func testStartupValidatesExistingJournalWithoutBlockingFirstScreen() {
        continueAfterFailure = false
        XCUIDevice.shared.orientation = .landscapeLeft
        let app = XCUIApplication()
        app.launch()
        let export = app.buttons["v2-export"]
        XCTAssertTrue(export.waitForExistence(timeout: 15), "The first screen should appear while the journal is checked")
        let loading = app.descendants(matching: .any).matching(identifier: "v2-storage-loading").firstMatch
        expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: loading)
        waitForExpectations(timeout: 240)
        XCTAssertTrue(export.isEnabled, "The journal must open before acquisition is permitted")
    }
    func launch(_ arguments: [String] = []) -> XCUIApplication {
        continueAfterFailure = false
        XCUIDevice.shared.orientation = .landscapeLeft
        let app = XCUIApplication();app.launchArguments = ["--ui-testing","--simulate"] + arguments;app.launch();return app
    }
    func screenshot(_ name:String,app:XCUIApplication) {
        let attachment = XCTAttachment(screenshot:app.screenshot());attachment.name=name;attachment.lifetime = .keepAlways;add(attachment)
    }
    func testTaskCountsSkipRepeatPauseAndCompletion() {
        let app=launch();let start=app.buttons["start-test"];XCTAssertTrue(start.waitForExistence(timeout:10));start.tap()
        let prompt=app.descendants(matching:.any).matching(identifier:"participant-task-progress").firstMatch
        XCTAssertTrue(prompt.waitForExistence(timeout:5));XCTAssertTrue(prompt.label.contains("1 / 72"));XCTAssertTrue(prompt.label.contains("后续还有 71 次"));XCTAssertTrue(prompt.label.contains("先悬空指准目标，再点击"))
        app.buttons["simulate-trial"].tap()
        let progress2=NSPredicate(format:"label CONTAINS %@","2 / 72")
        expectation(for:progress2,evaluatedWith:prompt);waitForExpectations(timeout:10)
        app.buttons["跳过"].tap()
        expectation(for:NSPredicate(format:"label CONTAINS %@","3 / 72"),evaluatedWith:prompt);waitForExpectations(timeout:5)
        XCTAssertTrue(prompt.label.contains("后续还有 69 次"));screenshot("fitts-trial-03-of-72",app:app)
        app.buttons["暂停"].tap();XCTAssertTrue(prompt.label.contains("已暂停"))
        app.buttons["继续"].tap();XCTAssertTrue(prompt.label.contains("重做"));XCTAssertTrue(prompt.label.contains("3 / 72"))
        app.buttons["结束实验"].tap();XCTAssertTrue(prompt.label.contains("本组结束"));screenshot("ended-summary",app:app)
    }
    func testComparisonPromptAndLongPassInstruction() {
        let app=launch(["--demo"]);let prompt=app.descendants(matching:.any).matching(identifier:"participant-task-progress").firstMatch;XCTAssertTrue(prompt.waitForExistence(timeout:10))
        XCTAssertTrue(prompt.label.contains("1 / 144"));XCTAssertTrue(prompt.label.contains("后续还有 143 次"));screenshot("tap-hover-shared-progress",app:app)
        app.buttons["结束实验"].tap()
        app.buttons.matching(NSPredicate(format:"label CONTAINS %@","Test 4")).firstMatch.tap()
        app.buttons["Test 2 · 悬空经过"].tap();app.buttons["start-test"].tap()
        XCTAssertTrue(prompt.label.contains("不要触屏"));XCTAssertTrue(prompt.label.contains("1 / 24"));screenshot("pass-through-instruction",app:app)
    }
    func testSettingsRejectInvalidGeometryAndExportSnapshot() {
        let app=launch();app.buttons["实验设置"].tap()
        let field=app.textFields["distance-values"];XCTAssertTrue(field.waitForExistence(timeout:5));field.tap()
        field.press(forDuration:1.2)
        if app.menuItems["Select All"].exists {app.menuItems["Select All"].tap();field.typeText("400")}
        else {field.typeText(String(repeating:XCUIKeyboardKey.delete.rawValue,count:20)+"400")}
        app.buttons["保存"].tap();XCTAssertTrue(app.staticTexts.matching(NSPredicate(format:"label CONTAINS %@","配置无法运行")).firstMatch.waitForExistence(timeout:5))
        app.buttons["取消"].tap();app.buttons["导出今天的 CSV"].tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format:"label CONTAINS %@","已生成 CSV 快照")).firstMatch.waitForExistence(timeout:5));screenshot("csv-share-sheet",app:app)
    }
    func selectOnly(_ task: String, app: XCUIApplication) {
        XCTAssertTrue(app.switches["v2-group-A"].waitForExistence(timeout:10))
        for group in ["A","B","C"] {
            let toggle = app.switches["v2-group-\(group)"];toggle.tap()
            XCTAssertEqual(toggle.value as? String,"0")
        }
        app.switches["v2-task-\(task)"].tap()
        XCTAssertTrue(app.buttons["v2-start"].isEnabled)
    }
    func v2Prompt(_ app: XCUIApplication) -> XCUIElement {
        app.descendants(matching:.any).matching(identifier:"v2-participant-prompt").firstMatch
    }
    func assertFourActions(_ app: XCUIApplication) {
        for label in ["开始实验","重做当前次","导出 CSV","结束实验"] { XCTAssertTrue(app.buttons[label].exists) }
        for label in ["暂停","继续","跳过","结束","历史文件","模拟完成一次","旧协议 Test 0–4","参数设置"] {
            XCTAssertFalse(app.buttons[label].exists, label)
        }
    }
    func testV23CountsFourActionsAndLassoRedo() {
        let app=launch(["--v2-demo"])
        let count=app.descendants(matching:.any).matching(identifier:"v2-counts").firstMatch
        XCTAssertTrue(count.waitForExistence(timeout:10))
        XCTAssertTrue(count.label.contains("156"));XCTAssertTrue(count.label.contains("3 段"))
        assertFourActions(app);screenshot("v23-simplified-task-selection",app:app)
        selectOnly("B4",app:app);XCTAssertTrue(count.label.contains("12 次短任务"))
        app.buttons["v2-start"].tap()
        let prompt=v2Prompt(app)
        XCTAssertTrue(prompt.label.contains("圈住"));XCTAssertTrue(prompt.label.contains("1 / 12"))
        app.buttons["v2-redo"].tap()
        expectation(for:NSPredicate(format:"label CONTAINS %@","重做第 1 / 12"),evaluatedWith:prompt)
        waitForExpectations(timeout:5);assertFourActions(app);screenshot("v23-lasso-redo",app:app)
    }
    func testV23ReadingSceneActualVideoAndExport() {
        let app=launch(["--v2-demo"]);selectOnly("A7",app:app);app.buttons["v2-start"].tap()
        let prompt=v2Prompt(app)
        XCTAssertTrue(prompt.label.contains("视频"));XCTAssertTrue(prompt.label.contains("1 / 1 段"))
        XCTAssertEqual(XCTWaiter.wait(for:[XCTestExpectation(description:"video decode")],timeout:3),.timedOut)
        screenshot("v23-actual-video-playback",app:app);assertFourActions(app)
        app.buttons["v2-export"].tap()
        XCTAssertTrue(app.otherElements["ActivityListView"].waitForExistence(timeout:5)
            || app.buttons["Close"].exists || app.buttons["关闭"].exists)
        screenshot("v23-csv-export",app:app)
    }
    func testV23ArticleAndNotesScenes() {
        for (task,label) in [("A5","文章"),("A6","图文")] {
            let app=launch(["--v2-demo"]);selectOnly(task,app:app);app.buttons["v2-start"].tap()
            XCTAssertTrue(v2Prompt(app).label.contains(label));assertFourActions(app)
            screenshot("v23-reading-\(task)",app:app);app.terminate()
        }
    }
    func testV23BaselineRedoRetainsPlannedOrdinalAndBackgroundResume() {
        let app=launch(["--v2-demo"]);selectOnly("A1",app:app);app.buttons["v2-start"].tap()
        let prompt=v2Prompt(app);XCTAssertTrue(prompt.label.contains("1 / 18"))
        app.buttons["v2-redo"].tap()
        expectation(for:NSPredicate(format:"label CONTAINS %@","重做第 1 / 18"),evaluatedWith:prompt)
        waitForExpectations(timeout:5)
        XCUIDevice.shared.press(.home);app.activate()
        let start = app.buttons["v2-start"]
        expectation(for:NSPredicate(format:"isHittable == true"),evaluatedWith:start)
        waitForExpectations(timeout:5);XCTAssertTrue(start.isEnabled)
        XCTAssertTrue(prompt.label.contains("已暂停"))
        XCTAssertTrue(prompt.label.contains("点击“开始实验”继续当前次"))
        XCTAssertTrue(app.switches["v2-task-A1"].exists, "Pausing must keep the task catalog visible")
        XCTAssertTrue(app.descendants(matching:.any).matching(identifier:"v2-counts").firstMatch.exists)
        // Resolve the new foreground frame instead of reusing its pre-Home activation point.
        start.coordinate(withNormalizedOffset:CGVector(dx:0.5,dy:0.5)).tap()
        expectation(for:NSPredicate(format:"NOT (label CONTAINS %@)","已暂停"),evaluatedWith:prompt)
        waitForExpectations(timeout:5);XCTAssertTrue(prompt.label.contains("1 / 18"))
        assertFourActions(app)
        screenshot("v23-background-resume-same-ordinal",app:app)
    }
    func testV2JournalRestoreKeepsTaskCatalogAndTopInstruction() {
        let app=launch(["--v2-demo"])
        selectOnly("A1",app:app)
        app.buttons["v2-start"].tap()
        XCTAssertTrue(v2Prompt(app).label.contains("1 / 18"))
        app.terminate()
        // The first launch clears any previous simulator checkpoint; the second uses the saved one.
        app.launchArguments=["--v2-demo"]
        app.launch()
        let prompt=v2Prompt(app)
        XCTAssertTrue(prompt.waitForExistence(timeout:15))
        let loading=app.descendants(matching:.any).matching(identifier:"v2-storage-loading").firstMatch
        expectation(for:NSPredicate(format:"exists == false"),evaluatedWith:loading)
        waitForExpectations(timeout:30)
        XCTAssertTrue(prompt.label.contains("已暂停"))
        XCTAssertTrue(prompt.label.contains("点击“开始实验”继续当前次"))
        XCTAssertTrue(prompt.label.contains("自然点击圆形目标"))
        XCTAssertTrue(app.switches["v2-task-A1"].exists)
        XCTAssertTrue(app.descendants(matching:.any).matching(identifier:"v2-counts").firstMatch.exists)
        screenshot("v2-restored-catalog-and-top-instruction",app:app)
    }
    func testV23C3TargetsPhotoObjectAndRetainsFourActions() {
        // Reproducible first HOVER trial in each scene, using the real mixed schedule.
        for (scene,seed) in [("news",8),("notes",1),("video",21)] {
            let app=launch(["--v2-demo","--v2-seed=\(seed)"])
            selectOnly("C3",app:app);app.buttons["v2-start"].tap()
            let prompt=v2Prompt(app)
            expectation(for:NSPredicate(format:"label CONTAINS %@","不要触屏"),evaluatedWith:prompt)
            waitForExpectations(timeout:5)
            XCTAssertTrue(prompt.label.contains("蝴蝶"));XCTAssertFalse(prompt.label.contains("星标"))
            assertFourActions(app)
            screenshot("v23-c3-\(scene)-butterfly",app:app);app.terminate()
        }
    }
    func testV2EndSessionKeepsCatalogAndClearsRecovery() {
        let app=launch(["--v2-demo"])
        selectOnly("A1",app:app)
        app.buttons["v2-start"].tap()
        XCTAssertTrue(v2Prompt(app).label.contains("1 / 18"))
        app.buttons["v2-end"].tap()
        XCTAssertTrue(v2Prompt(app).label.contains("本组结束"))
        XCTAssertTrue(app.switches["v2-task-A1"].exists)
        XCTAssertTrue(app.switches["v2-task-C3"].exists)
        screenshot("v2-ended-task-catalog",app:app)
        app.terminate()
        app.launchArguments=["--v2-demo"]
        app.launch()
        let loading=app.descendants(matching:.any).matching(identifier:"v2-storage-loading").firstMatch
        expectation(for:NSPredicate(format:"exists == false"),evaluatedWith:loading)
        waitForExpectations(timeout:30)
        XCTAssertTrue(v2Prompt(app).label.contains("选择姿势和任务，开始实验"))
        XCTAssertFalse(v2Prompt(app).label.contains("重做第"))
        XCTAssertTrue(app.switches["v2-task-C3"].exists)
    }
    func testV2OneTimeDiscardOnlyClearsUnfinishedA1Checkpoint() {
        let app=launch(["--v2-demo"])
        selectOnly("A1",app:app)
        app.buttons["v2-start"].tap()
        XCTAssertTrue(v2Prompt(app).label.contains("1 / 18"))
        app.terminate()
        app.launchArguments=["--v2-demo","--discard-unfinished-v2-a1"]
        app.launch()
        let loading=app.descendants(matching:.any).matching(identifier:"v2-storage-loading").firstMatch
        expectation(for:NSPredicate(format:"exists == false"),evaluatedWith:loading)
        waitForExpectations(timeout:30)
        XCTAssertTrue(v2Prompt(app).label.contains("选择姿势和任务，开始实验"))
        XCTAssertTrue(app.switches["v2-task-A1"].exists)
        XCTAssertTrue(app.switches["v2-task-C3"].exists)
        app.terminate()
        app.launchArguments=["--v2-demo"]
        app.launch()
        XCTAssertTrue(v2Prompt(app).waitForExistence(timeout:15))
        XCTAssertFalse(v2Prompt(app).label.contains("重做第"))
    }
}
