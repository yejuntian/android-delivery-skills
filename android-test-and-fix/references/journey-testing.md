# Journey UI 测试

## 适用性

同时读取已确认 BDD 和编码后实际 diff。无 UI 使用 `SKIPPED_NO_UI`；只有布局、颜色、字号、间距和资源变化使用 `SKIPPED_VISUAL_ONLY`；点击、输入、导航、状态流转或系统交互再按 BDD 分配 `FULL/PARTIAL/NONE`。

初判只登记候选，不启动设备或壳。终判按实际 diff 拆分 Journey 能覆盖和不能覆盖的 Then；只执行一次。适用性不是测试结果，Journey PASS 不替代接口、数据、视觉、性能、安全或它未断言的业务结果。

## BDD 物化

- Given：启动入口、DeepLink、登录、数据、权限、语言、主题、字体和方向等可复现前置。
- When：每个用户动作独立 action。
- Then：每个可观察结果独立 verify/check。
- 多指、长按、双击、折叠、精确计数或复杂条件不稳定时，改用项目已有 Compose/Espresso/UIAutomator 或人工路径。
- 用例说明和 action 用中文，真实界面文案、资源 ID、包名、类名和 schema 保持原值。
- XML 至少包含一个有效 action/check，标记覆盖的 BDD，拒绝零测试假绿。

正式来源为 `<requirement_dir>/test-cases/journeys/<作用域>/`。作用域绑定 Git 基线、需求修订和 UI/API 输入摘要；输入变化后不得复用旧用例。共享壳只读，运行时复制到 `.state/journey-runtime/<scope-key>/`；全局缓存只保存 Gradle 依赖。

## 默认 Android CLI Agent

默认路线由当前 AI 会话执行目标项目 Gradle 和 adb：

- 启动：`adb -s <serial> shell am start -n <pkg>/<activity>`。
- 可见断言：`adb -s <serial> exec-out screencap -p > <step>.png` 后进行真实视觉判断。
- 布局：优先可用的 `android layout` 或 uiautomator dump；返回空 root 时降级截图，不能伪造树。
- 操作：截图定位后使用 `adb shell input tap/text`；中文输入不支持时说明等价替代边界。
- 行为：按明确 TAG 抓 logcat 验证内部行为。

每步只含一个动作或断言，失败、退出、崩溃或冻结时停止后续步骤。记录脱敏命令、截图/布局摘要、状态和说明；输出 `android-test-and-fix/journey-agent` 结果，executed_tests/checks 使用真实完成数量。

## 可选壳

只有用户已选择、默认路线不可用且壳已初始化时调用 `scripts/run_journey.py`。行为型 Journey 必须有 FULL/PARTIAL 和至少一个 covered Then；无 UI 或纯视觉不启动。退出码必须结合状态解释：环境/证据不足先降级默认路线，连续真实 UI 断言失败且确认生产缺陷后才修目标代码。

壳的配置、APK 包名校验、force-stop、截图证据、隔离缓存、初始化和完整状态码见 `../assets/journey-harness/JOURNEY_USAGE.md`。
