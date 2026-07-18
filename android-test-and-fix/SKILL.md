---
name: android-test-and-fix
description: Android 测试驱动交付与自修复闭环。适用于 Android 需求、Bug 修复或功能迭代中，将已确认 BDD 物化为自动测试，按实际 diff 生成并执行单元测试、参数化测试、构建、lint、仪器、截图或 Journey UI 测试；低 AGP 老项目可通过独立 AGP 9 journey-harness 测试已安装 APK。测试失败时定位根因、修改代码并重跑，直到必需门禁全绿或连续三轮同根因受阻。完整交付时必须使用；单独调用时也可生成测试矩阵和验证报告。
---

# Android 测试与失败自修复

## 共享规则

执行本 Skill 前，必须先遵守 `../_shared/android-global-rules.md`。由 `android-implement-and-verify` 调用时启用自修复；单独要求“仅测试/仅报告”时不得修改生产代码。

## 定位

把已确认 BDD 和实际 diff 转成可执行测试，运行验证并关闭失败。测试环境不具备时生成最小可执行测试或人工路径，并如实标记未验证。

## 职责边界

- **负责**：BDD 测试物化、测试/构建/lint 执行、失败根因定位、代码修复、回归重跑和全绿门禁。
- **调用**：完整交付必跑；也可单独要求“补测试并修到通过”。
- **不负责**：替代需求确认、接口契约来源、设计稿判断或发布上线。
- **只报告模式**：用户明确要求“仅测试/仅报告”时不得修改生产代码；否则名称中的 `fix` 表示失败后必须修复并重跑。
- **与 UI 验收协作**：不调用 `android-verify-ui`，只输出测试结果和截图证据供其独立做设计还原验收。

## 内置资源

- `scripts/run_journey.py`：Journey 预检、目标 APK 构建安装、重试、错误分类和测试报告生成。
- `scripts/detect_package.py`：仅作源码阶段 applicationId 诊断；正式执行从 APK 读取真实包名。
- `scripts/tests/`：Journey 执行器回归测试。
- `assets/journey-harness/`：独立 AGP 9/Gradle 9.1 测试壳；不升级或修改低 AGP 目标项目。
- `assets/journey-harness/JOURNEY_USAGE.md`：Journey 适用性、禁用场景、工具选择、壳初始化、配置、状态码和故障降级的完整指南；判断是否调用 Journey 或排查壳问题时必须读取。

## 闭环执行顺序

1. 建立 `BDD -> 测试方法 -> 断言 -> 执行命令` 映射，确保每条 Then 有落点。
2. 检索现有测试目录、依赖、基类、fixture、命名和 Gradle task；沿用项目范式。
3. 为本次行为新增或补强测试。优先黑盒状态/输出断言，不测试实现细节。
4. 先运行新增/受影响测试，再运行相关模块测试、构建和 lint；按业务需求、BDD 和实际 diff 选择测试类型。只有 Journey 适用性门禁通过时才调用 `run_journey.py`。
5. 失败时保留原始命令、退出码和首个根因，修改最小范围代码后重跑。生产缺陷修生产代码；测试本身错误才修测试。
6. 每轮修复后重跑失败项和受影响回归集。连续 3 轮同一根因仍失败才暂停。
7. 全部必需门禁通过后才输出交付结论。

禁止通过删除测试、注释断言、扩大容差、添加无依据 sleep、`@Ignore`、排除 Gradle task 或把失败改成人工项来造绿。

## Android CLI / Gradle / adb 使用策略

- 只在需要真实构建、安装运行、自动测试、截图、logcat 或设备兼容验证时调用。
- 先识别本机是否存在 Android CLI、`./gradlew`、`adb`、可用模拟器或真机；不可用时如实报告。
- 优先使用项目已有 Gradle task 和测试框架；Android CLI 能提供更稳定的设备、SDK、模拟器或测试能力时再使用。
- 不得在需求理解阶段用 CLI 代替需求确认；测试命令只能验证实现结果，不能替代产品、设计或后端确认。
- 涉及清数据、卸载、Monkey、真实支付、真实删除、生产环境接口或破坏性操作时，必须用户明确同意。
- 每次执行后记录命令、退出码、关键日志、失败原因和剩余风险；没有实际执行不得写成已通过。

## 失败分类与降级记录

- 每个失败命令或测试先按共享规则标记一个当前主分类：`REQUIREMENT_BLOCKED`、`ENVIRONMENT_FAILED`、`TEST_FAILED`、`IMPLEMENTATION_FAILED` 或 `UNKNOWN`。测试失败只证明观察结果不符，不能直接证明生产代码有错。
- 优先由对应测试框架、专项 Skill/智能体和外部工具采集证据，状态记为 `SPECIALIST_ACTIVE`。工具或专项能力失败时，必须保留原始失败，并先向用户说明降级内容，不能把“改用通用 AI”写成原能力已通过。
- 完整交付或“补测试并修到通过”模式下，只有证据充分、修改低风险且存在等价重验时，通用 AI 才能以 `AI_FALLBACK_ACTIVE` 接管最小修复；只报告模式、`UNKNOWN` 或关键证据不足时不得修改生产代码。
- 缺少业务预期、测试数据、设备动作、权限或授权时使用 `USER_INPUT_REQUIRED`；专项能力与 AI 均无法关闭、同一根因连续 3 轮失败或必需测试没有等价替代时使用 `BLOCKED`。
- 替代测试只有覆盖同一 BDD、运行条件和风险时才能替代原测试。缺少真机、目标 Android 版本、真实 UI、性能或线上环境能力时，对应项保持“未验证”，不得计入全绿。

发生失败或降级时，测试报告固定记录：

```text
失败与降级记录：
- 失败分类：
- 触发步骤/测试：
- 原计划专项能力/工具：
- 失败原因与已尝试方式：
- 证据：命令、退出码、关键日志、报告或产物路径
- 当前状态：SPECIALIST_ACTIVE / AI_FALLBACK_ACTIVE / USER_INPUT_REQUIRED / BLOCKED
- AI 替代方式与最小修改：
- 损失的验证能力：
- 重验命令与结果：
- 剩余风险：
- 需要用户提供的输入：无 / 具体输入
```

## 测试用例生成

编码后必须按需求和实际改动生成测试用例，至少考虑：

- 正常路径。
- 空数据、空列表、空对象。
- 异常数据：null、缺字段、空字符串、未知枚举、类型异常。
- 网络异常：无网络、超时、服务端错误、登录过期。
- 权限异常：拒绝、永久拒绝、降级展示。
- 生命周期：返回、旋转、后台切前台、页面销毁后回调。
- 列表场景：快速滑动、分页、刷新、重复点击、复用错位、请求乱序。
- 本地数据：旧缓存、清缓存、迁移失败、默认值。
- UI 状态：加载、成功、失败、空态、禁用、选中。
- 灰度开关：开启、关闭、默认值缺失。
- Android 版本兼容：项目 `minSdk` 到目标 `targetSdk` 范围内的权限、存储、通知、后台任务、系统组件和 UI 行为差异。
- 回归影响：相关入口、详情页、搜索、筛选、推送、DeepLink。

每条用例标注：用例名、前置条件、步骤、预期结果、自动化类型、是否本次必须执行。

### 黑盒状态驱动底线

- 严禁编写单纯验证“内部方法调用次数”（如 `verify(repository).fetchData()`）的自嗨式白盒单测。此类测试不仅无法反映真实业务，还会阻碍后续代码重构。
- 必须强制编写基于“状态驱动”的黑盒测试：输入特定的 Action，断言最终吐出的 `UI State` 或实际返回数据是否正确，确保重构内部代码逻辑时不破坏测试用例。
### 业务逻辑测试优先级

当本次需求主要是业务逻辑变更且不涉及 UI 或接口契约时，优先选择：

- Unit：核心规则、UseCase、ViewModel、mapper、工具函数、状态计算。
- 参数化测试：多输入、多边界、多状态组合的规则判断。
- 回归测试：相邻业务流程、旧规则兼容、默认值和异常分支。
- 最小构建：执行当前模块可用的 assemble / test / lint。

默认不要求截图测试、UIAutomator、视觉对比或接口契约测试，除非实际 diff 涉及 UI 层或接口层。

## 自动化类型

- Unit：ViewModel、UseCase、Repository、mapper、工具函数。
- UI：Compose UI Test、Espresso、UIAutomator。
- Screenshot：Paparazzi、Roborazzi、Shot 或项目已有截图方案。
- CLI：Gradle 构建、lint、adb 安装、截图、logcat。
- Manual：需要人工确认的设计稿、复杂交互、第三方环境、真实后端数据。

## Journey UI 测试

Journey 属于 UI 功能测试用例，由本 Skill 根据已确认 BDD 生成和执行；`android-verify-ui` 只消费截图或结果做设计还原验收，不管理 Journey 用例。

不得要求用户编写或提供 Journey XML、action/step、文件名或 Gradle task。必须先从已确认需求、BDD、实际 diff、现有测试和页面入口自动生成当前需求的测试用例；只有无法确定业务前置条件或预期结果时，才询问缺失的业务含义。`NO_JOURNEY_FOUND` 是本 Skill 需要补齐测试物化的内部门禁，不是把技术工作转交给用户的提示。

### 适用性门禁

生成 Journey 前先同时检查需求和实际 diff，不得因为项目有界面就默认运行：

| UI 影响 | Journey 处理 | 状态 |
| --- | --- | --- |
| 无 UI 文件、可见状态或用户交互变化 | 不生成用例，不启动 SDK、设备或壳 | `SKIPPED_NO_UI` |
| 只有布局、颜色、字号、间距、图片等视觉变化 | 不运行 Journey；按需运行截图测试，并提示单独视觉验收 | `SKIPPED_VISUAL_ONLY` |
| 用户操作、导航、输入、可见状态流转或系统交互变化 | 自动从 BDD 生成 Journey 并执行 | `PASS` / `NO_JOURNEY_FOUND` / 失败状态 |

`NO_JOURNEY_FOUND` 只允许出现在已经判定为“UI 行为/状态流转需要 Journey”之后。无 UI 或纯视觉需求使用对应 `SKIPPED_*`，不算测试失败，也不得要求用户补 Journey 场景。

Journey 是否适用必须由模型根据用户业务需求、已确认 BDD、实际 diff、前置条件和预期结果自动判断，不得要求用户选择 `none`、`visual` 或 `behavior`。调用前在测试矩阵中记录“Journey：适用/不适用 + 原因”。只有同时满足以下条件才调用 Journey：

1. 本次需求改变用户操作、导航、输入或可见状态流转。
2. Given 前置条件可以稳定准备，不依赖验证码、真实支付或不可控第三方环境。
3. Then 可以通过页面上可见的文本、控件或状态判断。
4. 不要求像素级精度、复杂手势、精确时序或内部数据证明。

任一条件不满足时，自动选择 Unit、Espresso、Compose UI Test、UIAutomator、截图测试或人工路径，不得启动 Journey 壳。

采用“两次判断、一次执行”：

1. **需求确认后初判**：根据已确认 BDD 标记 `候选适用 / 初判不适用`，用于提前设计测试。候选适用时可以生成 Journey 用例草稿，但不得启动设备或壳。
2. **编码完成后终判**：读取实际 diff、最终页面入口和可执行前置条件，重新判断并记录最终原因。
3. **只执行一次**：只有终判为适用时才物化最终 XML，并以 `--ui-impact behavior` 调用脚本；终判不适用时选择其他测试，不调用 Journey。

需求初判与实际 diff 不一致时，以编码后的终判为准，并在测试报告中说明变化原因。

### BDD 物化规则

- 把 `Given` 转成可复现前置条件：启动入口、DeepLink、登录/数据、权限、语言、主题、字体和方向。壳只负责启动应用，不能隐式满足前置条件。
- 把每个 `When` 拆成独立 action，避免一个 action 包含多个操作。
- 把每个 `Then` 写成独立 verify/check action，不得只隐含在操作描述中。
- 把 Journey XML 作为当前需求的测试用例，默认放入 `<requirement_dir>/test-cases/journeys/<需求作用域>/[场景名].xml`；完整流程的作用域来自当前 Git 基线和需求正文哈希，单独调用时来自需求正文哈希。也可用 `testing.journey_harness.cases_dir` 或 `--journeys-dir` 显式指定。至少包含一个有效 action/step，拒绝零测试假绿。
- 不把需求用例长期保存在共享壳源码中。执行器每次只把当前用例集同步到壳的暂存目录，并清除上一次运行残留的 XML，防止跨项目串用测试。
- 多指、长按、双击、旋转/折叠、精确计数或复杂条件不稳定时，改用项目已有 Compose/Espresso/UIAutomator，或明确列为人工测试。

### 壳项目执行

目标项目路径默认读取 `../profiles/local.yaml` 的全局 `project_path`，也允许通过 `--config` 指定项目自己的配置文件：

```bash
python3 ai-skills/android-delivery-skills/android-test-and-fix/scripts/run_journey.py \
  --config ai-skills/android-delivery-skills/profiles/local.yaml \
  --ui-impact behavior
# 已安装目标 APK 时可使用 --skip-build；此时必须配置 app_package_name，但不要求源码项目存在。
# 临时指定其他用例目录时可使用 --journeys-dir /path/to/journeys。
```

`--ui-impact` 是 Skill 内部必填的安全参数，由模型的适用性判断产生，不要求用户提供。未判断时脚本拒绝启动。通常无 UI 或纯视觉需求不调用本脚本；需要结构化记录跳过原因时，模型才执行 `--ui-impact none` 或 `--ui-impact visual`。跳过模式只读取配置以定位当前需求报告目录，不检查 SDK、不连接设备。

执行器必须：

1. 拒绝零 Journey、空 action/step、成功日志中的 `NO-SOURCE`/`0 tests`，以及没有本轮结构化 JUnit XML 的成功退出；只有实际测试数大于 0 且失败数为 0 才判绿。
2. 使用目标项目自己的 Gradle wrapper 构建指定 module/variant，不改变其 AGP。
3. 从最终 APK 读取 applicationId，安装后通过 `pm path` 校验实际包名。
4. 通过独立 AGP 9 壳注入 `JOURNEYS_CUSTOM_APP_ID`，并隔离 `GRADLE_USER_HOME`。
5. 每轮先 force-stop 并重新应用配置中明确的 Given 前置条件；优先用结构化失败结果归类。只有连续两次真实 UI 断言失败才返回 `APP_ASSERTION_FAILED`，且不证明生产代码必然有错。
6. 只从 Journey/screenshot/capture 结果目录收集截图，禁止把普通构建资源当成证据。
7. 按需求作用域输出 `<requirement_dir>/test-results/journey-harness/<需求作用域>/result.json` 和 `result.md`，记录实际测试数、结构化结果、命令、设备、包名、APK、task、轮次和截图。
8. 对 adb、Gradle 和 Journey 命令设置超时；终端及报告中的 DeepLink 查询参数、Token、密码和密钥必须脱敏。

退出码：`0` 表示 Journey 真实执行通过、明确不适用或仅预检；必须结合状态区分 `PASS`、`SKIPPED_*` 和 `PREFLIGHT_PASS`。`1` 表示环境、壳或结构化证据不足，只能修环境或换用其他测试；`2` 表示连续两次真实 UI 断言失败，可进入根因分析。确认是生产缺陷才修目标代码；用例、数据或前置条件错误只修测试侧。

首次启用壳项目时，使用当前 Android Studio 的 `New > Journey Test` 生成与 Studio Labs 版本匹配的 XML schema、testSuites、依赖和任务。该操作只初始化共享壳一次，不要求用户为每个目标项目重复执行。

## 命令选择规则

不得写死命令。先识别项目模块和已有命令，再选择最小验证：

- 环境识别：例如 `which adb`、`adb devices`、`./gradlew tasks --all`、Android CLI 可用性检查。
- 构建：例如 `./gradlew :app:assembleDebug`。
- 单测：例如 `./gradlew :app:testDebugUnitTest`。
- 指定测试：例如 `--tests "完整类名"`。
- Lint：例如 `./gradlew :app:lintDebug`。
- 仪器测试：例如 `./gradlew :app:connectedDebugAndroidTest`。
- 设备：`adb devices`、`adb logcat`、`adb exec-out screencap -p`。

没有设备时仅跳过确实依赖设备的项；本地单测、构建和 lint 仍必须执行。没有现成测试框架时，优先使用项目已有依赖补最小测试；新增重型依赖需用户确认。

## 全绿门禁

- 必需：新增/受影响测试、相关模块测试、assemble、lint 0 Error。
- 条件必需：按业务影响选择仪器或截图测试；Journey 仅在适用性门禁通过且设备可用时执行。
- 所有 BDD Then 均已覆盖；无法自动化的项有可复现人工步骤和原因。
- 失败数为 0，P0/P1 测试缺口为 0。未执行项不得计为通过。

## Android 版本兼容测试

当需求涉及系统 API、权限、存储、通知、后台任务、前台服务、WebView、FileProvider、DeepLink、WindowInsets、相册、蓝牙、定位、媒体、软键盘、状态栏或导航栏时，测试用例矩阵必须包含 Android 版本兼容项。

测试设计必须基于当前项目：

- `minSdk`
- `targetSdk`
- `compileSdk`
- 目标 build variant
- 当前项目已支持的设备范围
- CI 或本地可用的模拟器 / 真机

重点覆盖：

- 低版本设备是否能正常安装、启动和进入相关页面。
- 高版本设备是否触发新权限、新限制或 Manifest 配置要求。
- 权限拒绝、永久拒绝、系统版本不支持权限时的降级体验。
- 通知渠道、通知权限、后台任务、前台服务、Alarm、WorkManager 的版本差异。
- 分区存储、相册/媒体权限、FileProvider、文件 URI 的版本差异。
- `PendingIntent`、`android:exported`、包可见性、DeepLink 的版本差异。
- WindowInsets、状态栏、导航栏、软键盘、暗黑模式、字体缩放导致的 UI 差异。

如果没有对应 Android 版本设备或模拟器，必须把该项标记为“未验证”，并给出建议测试版本和原因。不得把单一设备通过当作全版本兼容通过。

## 禁止事项

- 不得伪造测试结果。
- 不得因为测试失败就直接忽略。
- 不得为了测试擅自新增重型依赖。
- 不得在生产环境运行破坏性测试。
- Monkey、清数据、真实支付、真实删除等操作必须用户明确同意。

## 输出格式

1. 测试范围
2. 测试用例矩阵
3. 自动化可执行项
4. 需要人工验证项
5. 执行命令和结果
6. 自修复轮次、根因和修改
7. 失败项与降级记录（失败分类、原专项能力/工具、证据、AI 替代、能力损失、所需输入、当前状态）
8. 未验证项和剩余风险
9. 门禁结论：全绿 / 未完成 / 受阻
