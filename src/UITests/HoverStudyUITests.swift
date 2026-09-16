import XCTest

final class HoverStudyUITests: XCTestCase {
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
    func testV2CountsLassoAndProgress() {
        let app=launch(["--v2-demo"])
        let count=app.descendants(matching:.any).matching(identifier:"v2-counts").firstMatch
        XCTAssertTrue(count.waitForExistence(timeout:10));XCTAssertTrue(count.label.contains("156"));XCTAssertTrue(count.label.contains("3 段"))
        screenshot("v2-14-task-selection",app:app)
        app.buttons["清空"].tap();app.buttons["v2-task-B4"].tap()
        XCTAssertTrue(count.label.contains("12 次短任务"));app.buttons["v2-start"].tap()
        let prompt=app.descendants(matching:.any).matching(identifier:"v2-participant-prompt").firstMatch
        XCTAssertTrue(prompt.label.contains("圈住"));XCTAssertTrue(prompt.label.contains("1 / 12"))
        screenshot("v2-lasso-start",app:app)
        app.buttons["v2-simulate"].tap()
        expectation(for:NSPredicate(format:"label CONTAINS %@","2 / 12"),evaluatedWith:prompt);waitForExpectations(timeout:10)
        app.buttons["暂停"].tap();XCTAssertTrue(prompt.label.contains("已暂停"));app.buttons["继续"].tap();XCTAssertTrue(prompt.label.contains("重做"));app.buttons["结束"].tap()
    }
    func testV2ReadingSceneAndExport() {
        let app=launch(["--v2-demo"]);XCTAssertTrue(app.buttons["清空"].waitForExistence(timeout:10));app.buttons["清空"].tap();app.buttons["v2-task-A7"].tap();app.buttons["v2-start"].tap()
        let prompt=app.descendants(matching:.any).matching(identifier:"v2-participant-prompt").firstMatch
        XCTAssertTrue(prompt.label.contains("视频"));XCTAssertTrue(prompt.label.contains("1 / 1 段"))
        // Wait for AVPlayer to decode actual bundled frames.
        let wait=XCTWaiter.wait(for:[XCTestExpectation(description:"video decode")],timeout:3)
        XCTAssertEqual(wait,.timedOut);screenshot("v2-actual-video-playback",app:app)
        app.buttons["结束"].tap();app.buttons["导出 CSV 快照"].tap();screenshot("v2-export-share",app:app)
    }

    func testV2ArticleAndNotesScenes() {
        let app=launch(["--v2-demo"]);XCTAssertTrue(app.buttons["清空"].waitForExistence(timeout:10));app.buttons["清空"].tap();app.buttons["v2-task-A5"].tap();app.buttons["v2-task-A6"].tap();app.buttons["v2-start"].tap()
        let prompt=app.descendants(matching:.any).matching(identifier:"v2-participant-prompt").firstMatch
        XCTAssertTrue(prompt.label.contains("文章"));app.buttons["v2-simulate"].tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format:"label CONTAINS %@","已模拟阅读操作")).firstMatch.waitForExistence(timeout:7));screenshot("v2-news-reading-scrolled",app:app)
        app.buttons["结束"].tap();app.buttons["v2-task-A5"].tap();app.buttons["v2-start"].tap();XCTAssertTrue(prompt.label.contains("图文"))
        app.buttons["v2-simulate"].tap();let wait=XCTWaiter.wait(for:[XCTestExpectation(description:"note interactions")],timeout:3);XCTAssertEqual(wait,.timedOut);screenshot("v2-notes-masonry",app:app);app.buttons["结束"].tap()
    }

    func testV22BaselineRestartRetainsPlannedTrialThenSuccessAdvances() {
        let app=launch(["--v2-demo"])
        XCTAssertTrue(app.buttons["清空"].waitForExistence(timeout:10))
        app.buttons["清空"].tap();app.buttons["v2-task-A1"].tap();app.buttons["v2-start"].tap()
        let prompt=app.descendants(matching:.any).matching(identifier:"v2-participant-prompt").firstMatch
        XCTAssertTrue(prompt.label.contains("1 / 18"))
        app.buttons["重新开始本题"].tap()
        expectation(for:NSPredicate(format:"label CONTAINS %@","重做第 1 / 18"),evaluatedWith:prompt);waitForExpectations(timeout:5)
        screenshot("v22-baseline-retry-same-ordinal",app:app)
        app.buttons["v2-simulate"].tap()
        expectation(for:NSPredicate(format:"label CONTAINS %@","2 / 18"),evaluatedWith:prompt);waitForExpectations(timeout:8)
        app.buttons["结束"].tap()
    }

    func testV22C3ConcreteObjectInstructionAndRender() {
        let app=launch(["--v2-demo"])
        XCTAssertTrue(app.buttons["清空"].waitForExistence(timeout:10))
        app.buttons["清空"].tap();app.buttons["v2-task-C3"].tap();app.buttons["v2-start"].tap()
        let prompt=app.descendants(matching:.any).matching(identifier:"v2-participant-prompt").firstMatch
        // C conditions stay mixed; complete any preceding natural snippets instead of skipping them.
        for _ in 0..<3 where !prompt.label.contains("不要触屏") {
            let label=prompt.label
            expectation(for:NSPredicate(format:"label != %@",label),evaluatedWith:prompt);waitForExpectations(timeout:25)
        }
        XCTAssertTrue(prompt.label.contains("不要触屏"))
        XCTAssertTrue(prompt.label.contains("缩略配图") || prompt.label.contains("收藏星标"))
        screenshot("v22-c3-small-concrete-object",app:app)
        app.buttons["v2-simulate"].tap()
        app.buttons["结束"].tap()
    }

}
