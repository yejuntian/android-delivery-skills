---
name: android-test-and-fix
description: Android 测试驱动交付与自修复闭环。适用于 Android 需求、Bug 修复或功能迭代中，将已确认 BDD 物化为 Unit、参数化、迁移、A11y、仪器、截图或 Journey 测试，并按条件执行 OpenAPI、泄漏、性能和安全工具；低 AGP 老项目可通过独立 AGP 9 journey-harness 测试已安装 APK。失败时定位根因、最小修复并重跑，直到必需门禁全绿或明确受阻。完整交付时必须使用；单独调用时也可生成测试矩阵和验证报告。
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

- `references/adaptive-test-routing.md`：原子验证义务、`L1`、`L2`、`L3` 风险、分层测试、Journey `FULL`、`PARTIAL`、`NONE`、能力降级和统一证据门禁；出现 UI 与业务混合、Journey 只能覆盖部分步骤、测试层选择或证据缺口时必须读取。
- `scripts/run_journey.py`：Journey 预检、目标 APK 构建安装、重试、错误分类和测试报告生成。
- `scripts/detect_package.py`：仅作源码阶段 applicationId 诊断；正式执行从 APK 读取真实包名。
- `scripts/tests/`：Journey 执行器回归测试。
- `assets/journey-harness/`：独立 AGP 9/Gradle 9.1 测试壳；不升级或修改低 AGP 目标项目。
- `assets/journey-harness/JOURNEY_USAGE.md`：Journey 适用性、禁用场景、工具选择、壳初始化、配置、状态码和故障降级的完整指南；判断是否调用 Journey 或排查壳问题时必须读取。

## 闭环执行顺序

1. 从当前需求追溯表读取稳定 `REQ-###` / `BDD-###`，把复合 Then 拆成 `BDD-001/T1` 形式的原子验证义务，建立 `BDD/Then -> TEST-### -> 测试方法 -> 断言 -> 执行命令` 映射。单独调用且没有追溯表时，先在本次报告中建立同结构的最小映射；只有 `requirement_dir` 已确认时才创建文件。
2. 检索现有测试目录、依赖、基类、fixture、命名和 Gradle task；沿用项目范式。
3. 对 Bug 或可观察行为变化，优先先运行能复现目标行为的测试并保留 Red 证据，再做最小修改使其转 Green。测试在实现前就通过时，必须检查断言是否无效、前置是否错误或测试未覆盖变化。
4. 为本次行为新增或补强测试。优先黑盒状态/输出断言，不测试实现细节。
5. 先运行新增/受影响测试，再运行相关模块测试、构建和 lint；按业务需求、BDD、风险和实际 diff 选择能够证明行为的最低且足够测试层。混合影响或能力边界按 `references/adaptive-test-routing.md` 路由，只有分配给 Journey 的验证义务通过适用性门禁时才调用 `run_journey.py`。
6. 失败时保留原始命令、退出码和首个根因，修改最小范围代码后重跑。生产缺陷修生产代码；测试本身错误才修测试。
7. 每轮修复后重跑失败项和受影响回归集。连续 3 轮同一根因仍失败才暂停。
8. 最后一次修复完成后重新执行全部必需命令，把最终结果写回追溯表；旧轮次通过结果不得作为最终证据。
9. 全部必需门禁通过后才输出交付结论。

禁止通过删除测试、注释断言、扩大容差、添加无依据 sleep、`@Ignore`、排除 Gradle task 或把失败改成人工项来造绿。

Red-Green 优先规则不要求删除或重写旧生产代码。生成代码、纯配置/文档变化、老项目没有可用测试框架，或复现需要不可控第三方环境时，可以使用最小编译、静态检查、集成验证或人工路径替代，但必须记录无法先 Red 的原因、替代证据和剩余风险。

## 场景完整性与防 flaky

- 对每个 `REQ-ID` 检查主流程、备选流程、异常流程、恢复流程和非功能约束；只选择与需求及实际 diff 相关的场景。不适用项写明原因，资料不足项标为待确认，禁止脑补预期。
- 非功能场景按实际影响选择性能、稳定性、安全、兼容性、可访问性或资源使用，不要求所有需求机械执行所有类型。
- 禁止固定 `sleep`、`Thread.sleep` 或无条件延时掩盖时序问题；优先使用 IdlingResource、条件轮询、虚拟时间、框架智能等待或目标项目已有等待机制。
- 重试只允许处理已证明的环境或基础设施不稳定，不能重试业务断言直到碰巧通过。必须保留首次失败命令、日志、重试原因、次数和每次结果。
- 必需测试只有重试后才通过时标记 `FLAKY`，不得计为稳定全绿；先定位并关闭不稳定根因，无法关闭时门禁为“未完成/受阻”。

## 新鲜证据

- 最终证据必须来自最后一次生产代码、测试、资源或构建配置修改之后的执行；任何必需项变化都会使对应旧证据失效。
- 每项最终证据记录 `TEST-ID`、完整命令、执行目录、退出码、实际测试数、关键输出以及报告/产物路径；没有结构化测试数时如实说明工具限制。
- 替代验证必须覆盖相同 BDD、运行条件和风险；能力损失仍标记未验证，不得用较弱证据冒充原门禁通过。

## Android CLI / Gradle / adb 使用策略

- 只在需要真实构建、安装运行、自动测试、截图、logcat 或设备兼容验证时调用。
- 先识别本机是否存在 Android CLI、`./gradlew`、`adb`、可用模拟器或真机；不可用时如实报告。
- 优先使用项目已有 Gradle task 和测试框架；Android CLI 能提供更稳定的设备、SDK、模拟器或测试能力时再使用。
- 不得在需求理解阶段用 CLI 代替需求确认；测试命令只能验证实现结果，不能替代产品、设计或后端确认。
- 涉及清数据、卸载、Monkey、真实支付、真实删除、生产环境接口或破坏性操作时，必须用户明确同意。
- 每次执行后记录命令、退出码、关键日志、失败原因和剩余风险；没有实际执行不得写成已通过。

## 项目已有静态门禁发现与执行

测试阶段必须根据最终 diff 自动发现目标项目已经具备的 Kotlin、Java 和 Android 静态能力，只执行与受影响语言、模块和 variant 相符的现有任务或配置。缺少某项能力时降级并继续其他门禁，不自动安装工具、添加插件或修改依赖。

执行顺序：

1. **Kotlin/Java 编译**：读取项目模块、variant 和 Gradle task，优先执行受影响模块已有的 Kotlin/Java compile task；无法可靠确定独立 compile task 时，使用项目已有最小 assemble/test task 覆盖编译，不猜任务名造结果。
2. **Android Lint**：存在 Android 模块和对应 lint task 时执行受影响范围的现有 lint；保存文本输出及项目生成的 SARIF、XML 或 HTML 报告路径。
3. **语言专项**：Kotlin 仅执行项目已配置的 detekt；Java 仅执行项目已配置的 Error Prone、NullAway、SpotBugs 或 Infer。遵守现有版本、task、config 和扫描范围，不临时生成规则集。
4. **质量任务**：PMD、Checkstyle 等格式或风格任务只有项目已配置时执行；其结果路由给代码质量审查，不能把格式/风格通过写成稳定性通过。
5. **跨语言扫描**：Semgrep 只有本机/项目已有 binary 且仓库已有明确 config/rules 时执行；CodeQL 只有仓库、脚本或 CI 已配置 Kotlin/Java 流程时复用。不得自动下载未知规则、创建数据库或设计新查询套件。
6. **公开契约**：公共 Java/Kotlin API 变化且项目已有 ABI/API validator 或兼容任务时执行；没有既有能力时做人工兼容审查并记录机器校验未验证。

发现与结论规则：

- 从 Gradle 配置、version catalog、脚本、配置目录和 CI 文件确认能力是否真实存在；不能因电脑上有 binary 就假定项目已采用该门禁。
- 不自动创建或更新任何静态工具 baseline，不批量添加 `@Suppress`、`//noinspection`、规则排除或忽略路径来造绿。
- 每项记录发现依据、完整命令、执行目录、variant、退出码、关键输出、结构化报告路径和报告生成时间。
- 工具失败先按失败分类处理；规则告警需交给对应质量或稳定性 Skill 结合调用链复核，不能自动等同于生产缺陷。
- 工具不存在、配置缺失或老项目无法执行时，记录“未执行 + 原因 + 损失能力”；这不是通过，也不停止编译、测试及其他仍可运行门禁。
- 最终代码变化后，受影响的静态门禁证据失效，必须重新执行。

### 老项目历史债务隔离

已有可比较基线或旧报告时，把告警标为 `NEW`、`AFFECTED`、`PRE_EXISTING` 或 `UNKNOWN_ORIGIN`：

- `NEW`：本次 diff 新增；按严重级别关闭，不能写入 baseline。
- `AFFECTED`：旧问题位于本次直接调用链且可能被改动触发或放大；必须结合证据处理。
- `PRE_EXISTING`：需求开始前已存在且不在直接影响面；记录但不扩大本次修改。
- `UNKNOWN_ORIGIN`：报告不可比或基线不足；记录能力损失，不脑补为新增、历史或通过。

历史告警总量不能掩盖本次新增问题，也不能成为顺手清理全仓库的理由。完整交付必须关闭本次新增和直接受影响的 P0/P1；无关历史债务只进入剩余风险。

### Java 与混合项目测试发现

- 同时检索 `src/test/java`、`src/androidTest/java`、Kotlin source set、变体 source set 和自定义测试目录。
- 识别并沿用项目已有 JUnit4/JUnit5、Robolectric、Mockito、PowerMock、Espresso、Instrumentation runner 和自定义 Gradle task；不为统一风格迁移框架。
- Mockito/PowerMock 只作为现有测试能力，仍优先断言状态、返回值和可观察副作用，不用内部调用次数代替业务行为。
- 老框架无法安全先 Red 时，记录原因并选择覆盖相同 BDD 的最小编译、Robolectric、仪器或人工路径。

### release、R8 与 Java 版本条件门禁

- 反射序列化、注解生成、JNI、动态加载、R8/ProGuard、公共 API、Java language level、desugaring 或构建配置变化时适用。
- 只执行项目已有且不需要生产签名/凭据的 release、minify、consumer-rules、ABI/API 或等价验证 task；不得自动升级 AGP、Gradle、JDK 或关闭混淆。
- 没有可执行任务时继续 debug、本地测试和其他门禁，并写“Debug 已验证，release/R8/目标 Java 兼容未验证”。
- Release 特有失败保留 mapping、usage、missing rules 和堆栈证据，交给稳定性/`r8-analyzer` 做最小根因修复后重验。

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
- Kotlin/Java 混合边界：null/platform type、primitive/boxed、异常、Callback/异步取消和公开 API 兼容。
- 并发时序：旧请求晚返回、共享状态竞争、取消与回调同时发生；只在真实并发候选存在时生成。
- 列表场景：快速滑动、分页、刷新、重复点击、复用错位、请求乱序。
- 本地数据：旧缓存、清缓存、迁移失败、默认值。
- UI 状态：加载、成功、失败、空态、禁用、选中。
- 灰度开关：开启、关闭、默认值缺失。
- Android 版本兼容：项目 `minSdk` 到目标 `targetSdk` 范围内的权限、存储、通知、后台任务、系统组件和 UI 行为差异。
- 构建兼容：反射、生成代码、R8/ProGuard、Java language level 或 desugaring 变化时覆盖项目已有 release/minify/目标 variant。
- 回归影响：相关入口、详情页、搜索、筛选、推送、DeepLink。

每条用例标注：对应 `BDD/Then`、用例名、前置条件、步骤、预期结果、自动化类型、风险等级、是否本次必须执行。

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
- Screenshot：Paparazzi、Shot 或项目已有截图方案。
- CLI：Gradle 构建、lint、adb 安装、截图、logcat。
- Manual：需要人工确认的设计稿、复杂交互、第三方环境、真实后端数据。

## 第二轮条件测试

六类能力的共同触发、设备降级和报告边界见 `../android-implement-and-verify/references/conditional-capability-gates.md`。本 Skill 只执行与已确认需求和最终 diff 相符的测试，不因为缺少真机停止其他可运行门禁。

### 数据迁移

- Room version/schema、Entity/Dao、DataStore、SharedPreferences、Proto 或缓存格式变化时适用。
- 优先复用项目已有 schema、Migration、`MigrationTestHelper` 和仪器测试；验证真实旧版本到新版本、旧数据保留、默认值、索引、外键和约束。
- 没有实体真机时优先使用模拟器；没有任何设备时继续 schema/代码静态检查和其他本地门禁，动态迁移标为未验证。
- 缺少旧 schema 或旧数据样本时不得用新库建库成功代替迁移证据；禁止清数据、卸载重装或 destructive migration 造绿。
- 证据记录源/目标版本、旧数据准备、命令、迁移后断言、测试数和报告路径。

### UI/A11y 自动测试

- UI、交互控件、图标、可见状态、Compose semantics、焦点、字体或主题变化时检查 A11y 适用性；视觉设计验收仍由 `android-verify-ui` 手动独立执行。
- 优先复用项目已有 Compose/Espresso semantics、AccessibilityChecks、截图矩阵或仪器测试，不自动新增依赖。
- 测试语义标签、装饰元素排除、可点击区域、焦点顺序、状态描述、错误提示、字体缩放，以及不能只靠颜色表达状态。
- 模拟器可执行的项目继续运行；没有设备时完成静态 XML/Compose/resource 检查，把 TalkBack、动态焦点和触摸体验标为未验证。

### 泄漏、性能与安全任务协作

- `android-audit-stability` 判定动态泄漏、性能或安全隐私适用后，本 Skill 只负责执行项目已有 LeakCanary/Heap、Benchmark/Perfetto、Lint、detekt、Error Prone、NullAway、SpotBugs、Infer、Semgrep、CodeQL、MobSF 等命令并保留证据。
- 工具不存在时不自动安装，不用较弱命令冒充等价通过；继续其他门禁并记录未验证与能力损失。
- 模拟器结果必须标明，正式性能、厂商 ROM 和真实硬件验收没有真机时保持未验证。

## Journey UI 测试

Journey 属于已安装 APK 的关键用户旅程冒烟测试，由本 Skill 根据已确认 BDD 生成和执行；它不是全部业务测试入口。`android-verify-ui` 只消费截图或结果做设计还原验收，不管理 Journey 用例。

不得要求用户编写或提供 Journey XML、action/step、文件名或 Gradle task。必须先从已确认需求、BDD、实际 diff、现有测试和页面入口自动生成当前需求的测试用例；只有无法确定业务前置条件或预期结果时，才询问缺失的业务含义。`NO_JOURNEY_FOUND` 是本 Skill 需要补齐测试物化的内部门禁，不是把技术工作转交给用户的提示。

### 适用性门禁

生成 Journey 前先同时检查需求和实际 diff，不得因为项目有界面就默认运行。先判断 UI 影响：

| UI 影响 | Journey 处理 | 状态 |
| --- | --- | --- |
| 无 UI 文件、可见状态或用户交互变化 | 不生成用例，不启动 SDK、设备或壳 | `SKIPPED_NO_UI` |
| 只有布局、颜色、字号、间距、图片等视觉变化 | 不运行 Journey；按需运行截图测试，并提示单独视觉验收 | `SKIPPED_VISUAL_ONLY` |
| 用户操作、导航、输入、可见状态流转或系统交互变化 | 进入 `FULL/PARTIAL/NONE` 适用性判断 | 候选，不等于必须执行 |

再按每个原子 Then 的能力分配，聚合出整条 BDD 用户旅程的三级适用性：

| 适用性 | 判定 | Journey 处理 |
| --- | --- | --- |
| `FULL` | BDD 中全部用户可见操作和可见断言都能由 Journey 稳定完成 | 生成并执行完整 Journey；非 UI/不可见 Then 仍由其他测试层证明 |
| `PARTIAL` | Journey 只能稳定完成其中部分用户可见操作或可见断言 | 只生成可覆盖部分；其余 Then 路由到 Unit、Integration、Compose/Espresso、UIAutomator、截图或实际人工路径 |
| `NONE` | 前置、操作或结果无法可靠表达，或其他测试层更合适 | 不启动壳，使用其他证据 |

`FULL/PARTIAL/NONE` 只是适用性，不是测试结果。Journey `PASS` 只允许把它实际断言的 Then 标为自动覆盖，不能替代同一 BDD 中的业务计算、接口、数据库、视觉、性能、泄漏或安全验证。`NO_JOURNEY_FOUND` 只允许出现在已有验证义务最终分配给 Journey、但用例未成功物化之后。无 UI 或纯视觉需求使用对应 `SKIPPED_*`，不算测试失败，也不得要求用户补 Journey 场景。

Journey 是否适用必须由模型根据用户业务需求、已确认 BDD、实际 diff、前置条件和预期结果自动判断，不得要求用户选择 `none`、`visual` 或 `behavior`。调用前按每条 BDD 记录 `FULL/PARTIAL/NONE + 原因`，并逐个 Then 记录是否分配给 Journey。只有分配给 Journey 的验证义务同时满足以下条件才调用：

1. 本次需求改变用户操作、导航、输入或可见状态流转。
2. Given 前置条件可以稳定准备，不依赖验证码、真实支付或不可控第三方环境。
3. Then 可以通过页面上可见的文本、控件或状态判断。
4. 不要求像素级精度、复杂手势、精确时序或内部数据证明。

任一条件不满足时，只把对应验证义务路由到 Unit、Integration、Espresso、Compose UI Test、UIAutomator、截图测试或实际人工路径；其他满足条件的验证义务仍可作为 `PARTIAL` Journey 执行。

采用“两次判断、一次执行”：

1. **需求确认后初判**：根据已确认 BDD 和原子 Then 分配，标记整条 Journey 候选 `FULL/PARTIAL/NONE`，用于提前设计测试。候选可覆盖时可以生成 Journey 用例草稿，但不得启动设备或壳。
2. **编码完成后终判**：读取实际 diff、最终页面入口和可执行前置条件，重新判断并记录最终原因；能力缩小则拆分路由，影响扩大则补充其他测试层。
3. **只执行一次**：只要终判仍有验证义务分配给 Journey，就物化这些义务的最终 XML，并携带 `--ui-impact behavior`、`--applicability FULL/PARTIAL`、覆盖及未覆盖 Then 调用脚本；没有分配项时选择其他测试，不调用 Journey。

需求初判与实际 diff 不一致时，以编码后的终判为准，并在测试报告中说明变化原因。

### BDD 物化规则

- 把 `Given` 转成可复现前置条件：启动入口、DeepLink、登录/数据、权限、语言、主题、字体和方向。壳只负责启动应用，不能隐式满足前置条件。
- 把每个 `When` 拆成独立 action，避免一个 action 包含多个操作。
- 把每个 `Then` 写成独立 verify/check action，不得只隐含在操作描述中。
- XML 和最终报告必须标明覆盖的 `BDD/Then`；同一 BDD 中未分配给 Journey 的 Then 保持自己的测试与状态，不因 Journey 通过而改变。
- 把 Journey XML 作为当前需求的测试用例，默认放入 `<requirement_dir>/test-cases/journeys/<需求作用域>/[场景名].xml`；完整流程的作用域来自当前 Git 基线和需求正文哈希，单独调用时来自需求正文哈希。也可用 `testing.journey_harness.cases_dir` 或 `--journeys-dir` 显式指定。至少包含一个有效 action/step，拒绝零测试假绿。
- 不把需求用例长期保存在共享壳源码中。执行器每次只把当前用例集同步到壳的暂存目录，并清除上一次运行残留的 XML，防止跨项目串用测试。
- 多指、长按、双击、旋转/折叠、精确计数或复杂条件不稳定时，改用项目已有 Compose/Espresso/UIAutomator，或明确列为人工测试。

### 壳项目执行

目标项目路径默认读取 `../profiles/local.yaml` 的全局 `project_path`，也允许通过 `--config` 指定项目自己的配置文件：

```bash
python3 ai-skills/android-delivery-skills/android-test-and-fix/scripts/run_journey.py \
  --config ai-skills/android-delivery-skills/profiles/local.yaml \
  --ui-impact behavior \
  --applicability PARTIAL \
  --covered-then BDD-001/T1 \
  --uncovered-then BDD-001/T2
# 已安装目标 APK 时可使用 --skip-build；此时必须配置 app_package_name，但不要求源码项目存在。
# 临时指定其他用例目录时可使用 --journeys-dir /path/to/journeys。
```

这些参数均由 Skill 根据需求、BDD 和最终 diff 生成，不要求用户提供。行为型 Journey 缺少 `FULL/PARTIAL` 或至少一个覆盖 Then 时脚本拒绝启动。通常无 UI 或纯视觉需求不调用本脚本；需要结构化记录跳过原因时，模型才执行 `--ui-impact none` 或 `--ui-impact visual`，适用性自动记为 `NONE`。

执行器必须：

1. 拒绝零 Journey、空 action/step、成功日志中的 `NO-SOURCE`/`0 tests`，以及没有本轮结构化 JUnit XML 的成功退出；只有实际测试数大于 0 且失败数为 0 才判绿。
2. 使用目标项目自己的 Gradle wrapper 构建指定 module/variant，不改变其 AGP。
3. 从最终 APK 读取 applicationId，安装后通过 `pm path` 校验实际包名。
4. 通过独立 AGP 9 壳注入 `JOURNEYS_CUSTOM_APP_ID`，并把隔离的 `GRADLE_USER_HOME`、Gradle 项目缓存与 build 输出放在 Skill 目录外的用户缓存位置。
5. 每轮先 force-stop 并重新应用配置中明确的 Given 前置条件；优先用结构化失败结果归类。只有连续两次真实 UI 断言失败才返回 `APP_ASSERTION_FAILED`，且不证明生产代码必然有错。
6. 只从 Journey/screenshot/capture 结果目录收集截图，禁止把普通构建资源当成证据。
7. 按需求作用域输出 `<requirement_dir>/test-results/journey-harness/<需求作用域>/result.json` 和 `result.md`，记录实际测试数、结构化结果、命令、设备、包名、APK、task、轮次和截图。
8. 对 adb、Gradle 和 Journey 命令设置超时；终端及报告中的 DeepLink 查询参数、Token、密码和密钥必须脱敏。

退出码：`0` 表示 Journey 真实执行通过、明确不适用或仅预检；必须结合状态区分 `PASS`、`SKIPPED_*` 和 `PREFLIGHT_PASS`。`1` 表示初始化、环境、壳或结构化证据不足；`INITIALIZATION_REQUIRED` 只允许用当前 Android Studio 的官方 `New > Journey Test` 一次性补齐，不手写预览 DSL。`2` 表示连续两次真实 UI 断言失败，可进入根因分析。确认是生产缺陷才修目标代码；用例、数据或前置条件错误只修测试侧。

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
- 条件必需：按业务影响选择仪器或截图测试；Journey 只执行 `FULL` 或 `PARTIAL` 中实际分配给它的验证义务。
- 每个原子 Then 使用 `COVERED_AUTOMATED`、`COVERED_MANUAL`、`UNVERIFIED`、`BLOCKED` 或 `NOT_APPLICABLE`；`COVERED_MANUAL` 必须已经实际执行并有证据，不能用于尚未执行的计划。
- 当前需求追溯表中全部已确认 `REQ-ID` 都映射到 `BDD-ID/Then`、实现、`TEST-ID`/实际人工验收、必需性、命令和最终证据，需求映射率为 100%。
- 所有必需 Then 均为 `COVERED_AUTOMATED` 或有证据的 `COVERED_MANUAL`；Journey、截图、Unit 或静态扫描不得越过自身证据边界。
- 失败数为 0，P0/P1 测试缺口为 0。未执行项不得计为通过。
- 必需测试不得存在未关闭的 `FLAKY`，最终证据必须在最后一次修复后重新执行。

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
2. 追溯覆盖率：`REQ-ID -> BDD-ID/Then -> TEST-ID/实际人工验收 -> 覆盖状态 -> 最终证据`
3. 项目已有静态门禁：Kotlin/Java 编译、Lint、语言专项、跨语言扫描和 API/ABI 任务的发现依据、命令、退出码、报告和能力损失
4. 历史债务：`NEW` / `AFFECTED` / `PRE_EXISTING` / `UNKNOWN_ORIGIN` 数量、处置和证据
5. release/R8/Java 兼容：适用性、variant、命令、结论与未验证项
6. 条件能力矩阵：OpenAPI / 迁移 / 泄漏 / 性能 / UI-A11y / 安全隐私的适用性、设备类型和结论
7. 测试用例矩阵：原子 Then、风险等级、必需性、主/备用执行器、主流程 / 备选 / 异常 / 恢复 / 非功能及不适用理由
8. Red-Green 证据：首次 Red、最小修改和最终 Green；不适用时说明原因
9. 自动化可执行项和需要人工验证项
10. 最终新鲜证据：命令、退出码、测试数、关键输出和报告/产物路径
11. flaky 状态：首次失败、重试原因/次数/结果、是否已关闭
12. 自修复轮次、根因和修改
13. 失败项与降级记录（失败分类、原专项能力/工具、证据、AI 替代、能力损失、所需输入、当前状态）
14. 未验证项和剩余风险
15. 门禁结论：全绿 / 代码与本地门禁完成、真机专项待验证 / 未完成 / 受阻
