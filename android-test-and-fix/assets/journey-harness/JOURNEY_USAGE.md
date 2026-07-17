# Journey 使用场景与执行指南

本文说明 `android-test-and-fix` 何时应该使用 Journey、何时必须跳过、如何从业务需求生成用例，以及独立 AGP 9 壳如何测试低 AGP 老项目。

Journey 是基于自然语言和 AI 判断的黑盒 UI 流程测试。它擅长模拟用户在真实设备上的可见操作，但不能替代 Unit、API 契约、Espresso、Compose UI Test、UIAutomator、截图测试、性能测试或安全测试。

## 先看结论

一句话理解 Journey：

> 像真实用户一样在设备上点击、输入和跳转，并检查页面上是否出现预期结果。

用户不需要决定是否使用 Journey。`android-test-and-fix` 会在需求确认后初判、编码完成后结合实际 diff 终判，只有终判适用才自动生成用例并执行。

| 需求情况 | Journey 是否执行 | 应使用的主要验证方式 |
| --- | --- | --- |
| 没有 UI 变化 | 否 | Unit、参数化、Repository、构建和 lint |
| 只有颜色、字号、间距、图片等视觉变化 | 否 | 截图测试和 `android-verify-ui` |
| 有点击、输入、导航或可见状态流转 | 可能 | 满足稳定前置和可见断言时使用 Journey |
| 依赖验证码、真实支付或第三方页面 | 否 | Mock、UIAutomator 或人工测试 |
| 要验证内部计算、API、数据库、性能或安全 | 否 | 对应专项测试 |

快速决策：

```text
需求和实际 diff 是否改变 UI 行为或可见状态？
├─ 否：不运行 Journey
│  ├─ 无 UI 影响 → SKIPPED_NO_UI
│  └─ 纯视觉变化 → SKIPPED_VISUAL_ONLY
│
└─ 是
   ├─ 前置条件能稳定准备吗？
   ├─ 结果能从页面直接看到吗？
   ├─ 不依赖验证码、真实支付或不可控第三方吗？
   └─ 不要求像素、复杂手势、精确时序或内部数据吗？
       ├─ 全部是 → 自动生成并执行 Journey
       └─ 任一否 → 选择其他测试方式
```

最适合的例子：

```text
点击“重试”
→ 页面重新加载
→ 错误提示消失
→ 显示内容列表
```

最不适合的例子：

```text
按钮圆角必须是 12dp       → 截图/UI 视觉验收
满 100 元减 20 元是否正确  → Unit/参数化测试
请求字段是否叫 user_id    → API 契约测试
启动时间是否低于 800ms     → Macrobenchmark/Perfetto
```

## 目录

1. [先看结论](#先看结论)
2. [核心定位](#核心定位)
3. [谁负责判断和执行](#谁负责判断和执行)
4. [两次判断一次执行](#两次判断一次执行)
5. [适合 Journey 的场景](#适合-journey-的场景)
6. [不适合 Journey 的场景](#不适合-journey-的场景)
7. [测试工具选择表](#测试工具选择表)
8. [BDD 到 Journey 的转换](#bdd-到-journey-的转换)
9. [共享壳与老项目隔离](#共享壳与老项目隔离)
10. [一次性初始化](#一次性初始化)
11. [用例目录与跨项目隔离](#用例目录与跨项目隔离)
12. [配置与执行](#配置与执行)
13. [状态码和安全边界](#状态码和安全边界)
14. [报告与证据](#报告与证据)
15. [常见故障与降级](#常见故障与降级)
16. [最终检查清单](#最终检查清单)

## 核心定位

Journey 主要回答：

> 用户按照明确步骤操作应用后，是否能在页面上看到预期结果？

典型流程：

```text
打开目标页面
→ 点击、输入或滑动
→ 页面导航或状态变化
→ 检查可见文本、控件或结果状态
```

Journey 不能证明：

- 内部业务计算覆盖了全部边界。
- API 请求和响应字段符合契约。
- 数据库或缓存写入完全正确。
- 页面像素、颜色和间距符合设计稿。
- 性能、内存、安全和并发满足要求。
- 所有 Android 版本和设备组合均已通过。

## 谁负责判断和执行

- 用户负责确认业务需求、前置条件和预期结果。
- `android-test-and-fix` 根据需求、BDD 和实际 diff 自动判断 Journey 是否适用。
- 用户不需要选择 Journey，也不需要编写 XML、action/step、文件名或 Gradle task。
- `run_journey.py` 只负责校验、暂存、构建、安装、执行、失败分类和报告。
- `android-verify-ui` 只负责设计稿、截图、布局和视觉还原验收，不生成或执行 Journey。

## 两次判断一次执行

### 第一次：需求确认后初判

根据已确认 BDD 判断：

- 是否存在用户可执行的 UI 操作。
- 是否存在页面上可见的预期结果。
- 前置条件是否可以准备。
- 是否可能受验证码、支付或第三方系统阻塞。

此时只记录 `候选适用` 或 `初判不适用`，可以生成测试用例草稿，但不得启动设备和壳项目。

### 第二次：编码完成后终判

根据实际 diff 再检查：

- 最终是否真的修改 UI 行为或可见状态流转。
- 页面入口、文案和交互是否与需求初判一致。
- 是否已有更确定的 Espresso、Compose UI Test 或 UIAutomator 测试。
- 前置数据和设备环境是否可执行。

需求初判与实际 diff 不一致时，以编码后的终判为准，并在测试报告中说明变化原因。

### 只执行一次

只有终判适用，才生成最终 Journey XML，并使用：

```text
--ui-impact behavior
```

调用 Journey。终判不适用时选择其他测试，不启动壳项目。

## 适合 Journey 的场景

### 页面导航和入口

```text
Given 用户位于首页
When 点击“我的”Tab
Then 显示个人中心标题和设置入口
```

适合验证：

- Tab、按钮、列表项和菜单入口。
- 页面跳转和返回。
- DeepLink 打开目标页面。
- 通知点击后进入指定页面，但跨系统部分可能需要 UIAutomator 辅助。

### 表单输入和可见结果

```text
Given 用户位于新增地址页
When 输入姓名和地址并点击保存
Then 页面提示保存成功并返回地址列表
```

前提是测试数据和后端环境稳定，不涉及真实敏感信息。

### 加载、成功、空态和错误态

适合验证：

- 加载结束后显示列表。
- 搜索无结果时显示空态。
- 请求失败时显示错误提示和重试入口。
- 登录过期时显示明确的重新登录页面。
- 按钮从禁用变为可用。

### 简单用户操作闭环

```text
进入商品详情
→ 点击收藏
→ 收藏图标变为选中
→ 返回列表后收藏状态仍可见
```

Journey 可以验证用户可见结果；收藏数据的持久化仍需 Repository、数据库或仪器测试补充。

### 核心流程冒烟测试

适合覆盖少量高价值主链路：

- 应用启动和首页可见。
- 登录测试账号。
- 搜索并打开详情。
- 创建、编辑或删除测试数据。
- 设置开关的基本操作。
- 关键入口和页面能正常打开。

### 低 AGP 老项目黑盒测试

目标项目使用自己的 Gradle wrapper 构建 APK，不升级 AGP。独立 AGP 9 壳通过实际 APK 的 applicationId 启动应用并执行 Journey，适合：

- 老项目没有现成 UI 自动化框架。
- 不允许升级老项目 Gradle/AGP。
- 只需验证已安装 APK 的少量关键用户流程。
- 项目内部结构复杂，但页面可以从外部稳定操作。

## 不适合 Journey 的场景

### 完全没有 UI 影响

例如：

- mapper、UseCase、Repository 或工具函数修改。
- 排序、价格、时间、权限判断等纯规则变化。
- DTO、数据库、缓存或后台任务修改，但没有可见交互变化。

处理：`SKIPPED_NO_UI`。优先 Unit、参数化、Repository、数据库或系统能力测试。

### 只有视觉变化

例如：

- 颜色、字号、字重、间距、圆角和阴影。
- 图片、图标、字体和布局层级。
- 状态栏、导航栏和 WindowInsets 视觉问题。

处理：`SKIPPED_VISUAL_ONLY`。优先 Paparazzi、Roborazzi、Shot、真实截图和 `android-verify-ui`。

Journey 可以判断元素是否可见，但不能可靠证明 `24dp`、颜色值或像素差异正确。

### 纯业务逻辑和大量输入组合

例如：

- 满减、计费、排序、过滤和权限规则。
- 日期跨天、时区、精度和边界值。
- null、未知枚举、错误码和多状态组合。

原因：Journey 运行慢、组合覆盖差、失败定位不精确。

替代：Unit Test、参数化测试和状态驱动 ViewModel 测试。

### API 契约和网络层内部行为

例如：

- endpoint、请求字段和响应字段。
- DTO、mapper、序列化和错误码兼容。
- 重试次数、缓存策略和 Header。

原因：页面结果不能证明内部契约正确。

替代：MockWebServer、Repository 测试、契约测试和 `android-verify-api-contract`。

### 数据库、缓存和迁移正确性

例如：

- Room migration。
- DataStore/SharedPreferences 写入。
- 旧缓存兼容和数据回滚。
- 多表事务和唯一约束。

Journey 可补充最终用户流程，但不能作为唯一证据。

替代：数据库测试、迁移测试、Repository 测试和仪器测试。

### 强确定性 CI 门禁

不适合把 Journey 作为唯一门禁的场景：

- 金额、订单、库存和权限安全。
- 数据不可丢失的保存流程。
- 法务、金融或合规关键流程。
- 必须每次完全可重复的发布阻断项。

原因：Journey 依赖自然语言、模型判断、设备和服务状态，存在 flaky 风险。

替代：确定性的 Unit、Espresso、Compose UI Test 或 UIAutomator；Journey 只能作为补充冒烟测试。

### 复杂手势和精确时序

例如：

- 多指缩放和旋转。
- 长按拖拽、双击、快速连续点击。
- 折叠屏连续状态和复杂窗口切换。
- 动画必须在指定毫秒内完成。
- 精确坐标、精确滚动距离和帧级判断。

替代：Espresso、Compose UI Test、UIAutomator、Macrobenchmark 或专用手势测试。

### 不可控第三方流程

例如：

- 图形验证码、短信验证码和人机验证。
- 第三方登录授权页。
- 银行、支付、地图或其他外部应用页面。
- WebView 内由外部站点动态生成的复杂内容。

原因：页面、账号、网络和授权状态不可控，模型可能无法稳定复现。

替代：Mock/Fake、测试环境、UIAutomator 或人工测试。

### 高风险或破坏性操作

例如：

- 真实支付、真实下单和真实退款。
- 删除账号、删除生产数据和发送真实消息。
- 清除应用数据、卸载、Monkey 和批量权限操作。

不得默认执行。必须使用隔离测试环境；涉及破坏性操作时还需要用户明确授权。

### 性能、稳定性和资源问题

例如：

- 启动耗时、掉帧、卡顿和滚动性能。
- ANR、内存泄漏、CPU 和电量。
- 并发、竞态和后台限制。

Journey 可以复现入口，但不能完成可靠测量和根因分析。

替代：Macrobenchmark、Perfetto、内存分析、稳定性测试和 `android-audit-stability`。

### 安全和隐私验证

例如：

- Token 是否安全存储。
- 日志是否泄露手机号和密码。
- 组件导出、Intent 注入和 WebView 风险。
- 加密、证书和网络安全配置。

页面可见结果不足以证明安全性。使用静态分析、配置审查、专用安全测试和代码审查。

### 无障碍和国际化完整矩阵

Journey 可以检查某个页面的可见文本和基本操作，但不适合单独证明：

- TalkBack 朗读顺序和语义完整性。
- 键盘、Switch Access 和焦点导航。
- 多语言、RTL、超长文本和所有字体缩放组合。

替代：Accessibility Scanner、Compose/Espresso 语义断言、截图矩阵和人工辅助技术测试。

### 大规模数据和精确数量判断

例如：

- 上千条列表数据。
- 分页总数和精确计数。
- 快速滚动复用、请求乱序和重复数据。

替代：Repository/分页测试、参数化测试、Espresso/Compose UI Test 和性能测试。

### 环境本身不稳定

以下条件不满足时不应强行运行 Journey：

- 没有唯一在线设备。
- Gemini/Studio Labs 未登录或不可用。
- 测试账号、测试数据或后端不稳定。
- Journey task 未生成或无法唯一识别。
- APK 无法构建、安装或启动。

这些属于环境问题，不能归因给目标应用，更不能触发生产代码修复。

## 测试工具选择表

| 验证目标 | 首选工具 | Journey 的角色 |
| --- | --- | --- |
| 业务规则和边界值 | Unit / 参数化测试 | 不使用 |
| ViewModel 输入输出状态 | Unit / Turbine / 参数化测试 | 不使用 |
| View UI 确定性操作 | Espresso | 可补充主流程 |
| Compose 节点和语义 | Compose UI Test | 可补充主流程 |
| 跨应用和系统页面 | UIAutomator | 仅简单场景补充 |
| 像素、颜色和间距 | Screenshot Test + `android-verify-ui` | 不使用 |
| 用户完整操作和可见结果 | Journey | 适合 |
| API 字段和错误码 | 契约/Repository 测试 | 不使用 |
| 数据库和迁移 | Room/仪器测试 | 仅补充最终流程 |
| 性能、ANR 和内存 | Macrobenchmark / Perfetto | 仅用于复现入口 |
| 安全和隐私 | 静态分析/专项安全测试 | 不使用 |

## BDD 到 Journey 的转换

### Given

Given 必须变成可复现的前置条件，例如：

- 测试账号和数据。
- DeepLink 或启动 Activity。
- 权限状态。
- 语言、主题、字体缩放和屏幕方向。

不要把“应用会自动准备好登录和数据”当成默认事实。

### When

- 一个 action 只描述一个主要操作。
- 使用页面上稳定、可见的文案或控件描述目标。
- 避免“随便点一下”“选择对应按钮”等模糊语言。
- 复杂流程拆成多个离散步骤。

### Then

- 每个预期结果写成独立 verify/check。
- 断言页面上可见的文本、控件、选中态或导航结果。
- 不使用 Journey 断言数据库、API 字段或像素值。

示例：

```text
Given：应用位于搜索页，网络和测试数据可用
When：在搜索框输入“Android”并点击搜索
Then：显示搜索结果列表
Then：列表中至少有一项标题包含“Android”
```

XML 的准确 schema 必须以当前 Android Studio `New > Journey Test` 生成的官方模板为准，不要根据本文手写或猜测 DSL。

## 共享壳与老项目隔离

```text
低 AGP 目标项目
  └─ 使用自己的 gradlew 构建 APK
          ↓
从最终 APK 读取真实 applicationId
          ↓
adb 安装并通过 pm path 校验
          ↓
独立 AGP 9 journey-harness
  └─ 注入 JOURNEYS_CUSTOM_APP_ID
          ↓
执行 Journey 并输出报告
```

安全要求：

- 不修改目标项目的 AGP、Gradle 或 Kotlin 版本。
- 壳项目使用独立 `GRADLE_USER_HOME`，避免旧 `~/.gradle/init.d` 和缓存污染。
- 目标包名以 APK 为准，不依赖源码正则。
- 壳、设备和认证失败不能触发目标代码修复。

## 一次性初始化

Journey 是 Studio Labs 预览能力。第一次使用共享壳时：

1. 使用当前 Android Studio 打开本目录。
2. 确认 Studio Labs/Gemini 已启用并登录。
3. 执行 `New > Journey Test`。
4. 让 Android Studio 生成匹配当前版本的 XML schema、testSuites、依赖、Run Configuration 和 Gradle task。
5. 保留官方生成的结构，不手写猜测预览 DSL。

这一步只初始化共享壳一次，不要求每个目标项目重复执行。

## 用例目录与跨项目隔离

当前需求的 Journey 用例默认放在：

```text
<requirement_dir>/test-cases/journeys/*.xml
```

也可以配置 `testing.journey_harness.cases_dir` 或由 Skill 内部使用 `--journeys-dir` 指定。

壳目录：

```text
harness-app/src/main/journeys/
```

只是执行暂存区。脚本会在每次运行前：

1. 校验当前用例集。
2. 清除上一次运行的 `.xml`。
3. 只同步当前需求的用例。
4. 保留 `.xml.example` 和说明文件。

不得把不同项目的需求用例长期混放在共享壳中。

## 配置与执行

默认读取 `profiles/local.yaml`：

```yaml
testing:
  journey_harness:
    cases_dir: null
    module: "app"
    variant: "debug"
    retries: 2
    device: null
    app_package_name: null
    task: null
    precondition:
      clear_app_data: false
      grant_permissions: []
      deep_link: null
      launch_activity: null
```

说明：

- `cases_dir`：默认 `<requirement_dir>/test-cases/journeys`。
- `module`：目标 application 模块。
- `variant`：如 `debug`、`demoDebug`。
- `device`：多设备时填写 adb serial。
- `app_package_name`：通常从 APK 自动读取；`--skip-build` 时必填。
- `task`：无法自动发现 Journey task 时填写。
- `clear_app_data`：破坏性操作，必须明确需要才开启。
- `deep_link` 与 `launch_activity` 只能二选一。

只有模型终判 Journey 适用时才执行：

```bash
python3 android-test-and-fix/scripts/run_journey.py \
  --config profiles/local.yaml \
  --ui-impact behavior
```

`--ui-impact` 是 Skill 内部安全参数，不要求用户选择。脚本将它设为必填，防止未做适用性判断就启动 Journey。

## 状态码和安全边界

| 状态 | 含义 | 是否可修改目标代码 |
| --- | --- | --- |
| `PASS` | Journey 真实执行并通过 | 不需要 |
| `SKIPPED_NO_UI` | 无 UI 影响，Journey 不适用 | 否 |
| `SKIPPED_VISUAL_ONLY` | 纯视觉变化，改用截图或 UI 验收 | 否 |
| `NO_JOURNEY_FOUND` | 已终判需要 Journey，但用例未成功物化 | 先生成用例，不改目标代码 |
| `MALFORMED_JOURNEY` | XML 无效、无 action/step | 修用例，不改目标代码 |
| `HARNESS_UNAVAILABLE` | SDK、设备、wrapper 等前置缺失 | 修环境或降级 |
| `HARNESS_FAILED` | 壳、认证、task 或运行器失败 | 修环境或降级 |
| `APP_ASSERTION_FAILED` | 连续两次出现明确 UI 断言失败 | 先分析根因 |

退出码：

- `0`：通过或明确不适用。
- `1`：壳、环境、用例物化或执行器问题。
- `2`：连续两次真实 UI 断言失败。

退出码 `2` 只允许进入根因分析，不代表生产代码必然有错。确认是生产缺陷才修改目标代码；用例、测试数据或前置条件错误只修测试侧。

## 报告与证据

默认输出：

```text
assets/journey-harness/build/reports/journey-harness/result.json
assets/journey-harness/build/reports/journey-harness/result.md
```

报告包含：

- 状态和退出码。
- 设备、applicationId、APK 和 Gradle task。
- Journey 文件和 action/step 数量。
- 执行轮次和命令。
- 本次截图证据。
- 失败原因和降级建议。

Journey 截图可以交给 `android-verify-ui` 做设计还原对比，但 Journey 通过不能替代视觉验收通过。

## 常见故障与降级

### 没有 Journey 用例

- 先确认终判是否真的适用。
- 不适用：选择其他测试，不生成 Journey。
- 适用：由 `android-test-and-fix` 根据 BDD 自动生成，不能要求用户写 XML。

### 无法识别 Journey task

- 确认已经用当前 Android Studio 执行 `New > Journey Test`。
- 读取官方生成的 task 或在配置中填写完整 task。
- 不硬编码猜测预览版本的任务名。

### 多个设备在线

- 模型从测试环境选择目标设备。
- 无法唯一判断时才要求用户确认设备，而不是随机执行。

### APK 包名无法确定

- 优先使用 `apkanalyzer`。
- 其次使用 `aapt dump badging`。
- `--skip-build` 时才要求配置 `app_package_name`。

### 壳构建被全局 Gradle 配置污染

- 必须使用壳自己的 `.gradle-user-home`。
- 不使用目标项目或用户全局缓存替代隔离目录。

### Gemini、认证或网络不可用

- 标记环境失败。
- 选择 Espresso、Compose UI Test、UIAutomator 或人工测试。
- 不修改目标应用来规避认证问题。

### Journey 断言不稳定

- 检查 action 是否过于模糊。
- 检查 Given、数据和页面入口是否稳定。
- 连续两次明确断言失败后才进入根因分析。
- 强确定性流程改用确定性测试框架。

## 最终检查清单

调用 Journey 前必须全部回答“是”：

- [ ] 需求确认后的 BDD 包含用户 UI 操作和可见结果。
- [ ] 编码后的实际 diff 确实改变 UI 行为或状态流转。
- [ ] 前置条件可以稳定准备。
- [ ] 预期结果可以从页面可见内容判断。
- [ ] 不依赖验证码、真实支付或不可控第三方页面。
- [ ] 不要求像素级精度、复杂手势或精确时序。
- [ ] 没有更合适、更确定的低成本测试方案。
- [ ] 当前用例由 Skill 自动生成且至少包含一个有效步骤。
- [ ] 设备、SDK、壳、认证和目标 APK 环境可用。
- [ ] 测试不会操作生产数据或产生未授权破坏性影响。

任一项为“否”，不要启动 Journey，选择更合适的测试路径并在测试报告中说明原因。
