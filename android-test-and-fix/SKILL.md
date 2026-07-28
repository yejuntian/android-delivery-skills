---
name: android-test-and-fix
description: Android 测试驱动交付与自修复闭环。将已确认 BDD 物化为 Unit、参数化、迁移、A11y、仪器、截图或 Journey 测试。编码后的完善/修改/删除/修复用局部迭代模式（只跑受影响测试和必要编译）；最终交付时用完整交付模式（按条件执行构建、Lint、OpenAPI、泄漏、性能、安全能力）。失败时定位根因、最小修复并重跑；单独调用时也可生成测试矩阵和验证报告。
---

# Android 测试与失败自修复

## 共享规则

执行本 Skill 前，必须先遵守 `../_shared/android-global-rules.md`。由 `android-implement-and-verify` 调用时按其阶段选择局部迭代或完整交付并启用自修复；单独要求“仅测试/仅报告”时不得修改生产代码。

## 职责边界

- **负责**：BDD 测试物化、受影响测试与必要编译、完整交付时的构建/lint、失败根因定位、代码修复、回归重跑和全绿门禁。
- **不负责**：替代需求确认、接口契约来源、设计稿判断或发布上线。
- **只报告模式**：用户明确要求“仅测试/仅报告”时不得修改生产代码；否则名称中的 `fix` 表示失败后必须修复并重跑。

## 工作模式

- **局部迭代模式**：首次实现后继续完善、修改、删除或修复某个点时使用。只选择本轮受影响的测试；生产代码变化时追加受影响模块的最小编译，删除代码时检查调用方。除非本轮风险本身需要，不运行全量模块回归、全量构建、全量 Lint、完整 Journey/设备矩阵、全部条件专项或交付报告。
- **完整交付模式**：用户当前或最初请求明确要求最终检查、完整交付或准备提交时使用。按最终 diff 执行全部必需测试、构建、Lint、条件专项和新鲜证据门禁。
- 模式由总入口根据用户语义和当前阶段选择，不要求用户记忆英文参数或额外命令。局部迭代结果只能证明本轮受影响范围，不能输出整体全绿；完整交付结果在代码再次变化后立即失效。

## 内置资源

- `references/adaptive-test-routing.md`：BDD 场景证据、`L1`、`L2`、`L3` 风险、分层测试、Journey `FULL`、`PARTIAL`、`NONE`、能力降级和统一证据门禁；出现 UI 与业务混合、Journey 只能覆盖部分步骤、测试层选择或证据缺口时必须读取。
- `scripts/run_journey.py`：可选 AGP 9 壳的 Journey 预检、目标 APK 构建安装、重试、错误分类和测试报告生成；不是默认 Journey 前置。
- `scripts/detect_package.py`：仅作源码阶段 applicationId 诊断；正式执行从 APK 读取真实包名。
- `scripts/tests/`：Journey 执行器回归测试。
- `assets/journey-harness/`：可选独立 AGP 9/Gradle 9.1 测试壳；不升级或修改低 AGP 目标项目。
- `assets/journey-harness/JOURNEY_USAGE.md`：Journey 适用性、Android CLI Agent 默认路线、可选壳初始化、配置、状态码和故障降级的完整指南；判断是否调用 Journey 或排查执行问题时必须读取。

## 闭环执行顺序

1. 从最近确认需求快照和 `test-mapping.json` 读取稳定 `BDD-###`；存在待确认或冲突时不生成通过证据。建立 `BDD 场景 -> 真实测试 ID -> 业务观察边界 -> 断言 -> 执行命令` 映射，一个 BDD 可以映射多个测试。
2. 检索现有测试目录、依赖、基类、fixture、命名和 Gradle task；沿用项目范式。
3. 对 Bug 或可观察行为变化，先运行能复现目标行为的测试并看到业务断言 Red，再做最小修改使其 Green。Red/Green 收据、代码快照、测试源码快照和 BDD/testcase 关系由 `tdd_cycle.py` 自动保存；测试在实现前就通过时，检查断言、前置和覆盖范围。
4. 为每个 BDD 场景选择调用方可观察的最高且足够的既有业务边界，例如公开方法、UI State、Repository 输出、迁移结果或系统行为。
5. 为本次行为新增或补强测试。优先黑盒状态/输出断言，不测试实现细节；预期值必须来自已确认需求、接口契约、已知样例或固定事实，不得用与生产代码相同的算法重新计算答案。新增 Mock 优先只放在网络、数据库、时间、文件、系统或第三方等不可控边界，项目已有内部 Mock 可以沿用但不得新增调用次数断言代替业务结果。`【保护已上线业务】` 先复用并运行已有测试；没有时只补本次可能波及的最小保护测试。`【修改已上线业务】` 只有在确认的新预期与旧断言冲突时才更新对应测试，其他旧测试失败仍按回归处理。
6. 先完成测试映射，再逐个 BDD 执行 `Red -> Green -> Refactor`，Green 后重跑受影响测试。局部迭代只追加必要编译和风险直接要求的测试层；完整交付再运行相关模块测试、构建和 lint。
7. 失败时保留原始命令、退出码和首个根因，修改最小范围代码后重跑。生产缺陷修生产代码；测试本身错误才修测试。
8. 每轮修复后重跑失败项和受影响回归集。连续 3 轮同一根因仍失败才暂停。
9. 局部迭代在受影响测试和必要编译转绿后输出本轮结果；完整交付在最后一次修复后重新执行全部必需命令并刷新机器证据，旧轮次结果不得作为最终证据。
10. 只有完整交付模式全部必需门禁通过后才输出整体交付结论。

禁止通过删除测试、注释断言、扩大容差、添加无依据 sleep、`@Ignore`、排除 Gradle task 或把失败改成人工项来造绿。

Red-Green 优先规则不要求删除或重写旧生产代码。生成代码、纯配置/文档变化、老项目没有可用测试框架，或复现需要不可控第三方环境时，可以使用最小编译、静态检查、集成验证或人工路径替代，但必须记录无法先 Red 的原因、替代证据和剩余风险。

## 场景完整性与防 flaky

- 对每个 BDD 检查主流程、异常流程、恢复流程和相关非功能约束；资料不足项回写“待确认”，禁止脑补预期。
- 非功能场景按实际影响选择性能、稳定性、安全、兼容性、可访问性或资源使用，不要求所有需求机械执行所有类型。
- 禁止固定 `sleep`、`Thread.sleep` 或无条件延时掩盖时序问题；优先使用 IdlingResource、条件轮询、虚拟时间、框架智能等待或目标项目已有等待机制。
- 重试只允许处理已证明的环境或基础设施不稳定，不能重试业务断言直到碰巧通过。相同证据 ID 的每轮执行必须保留独立 `attempt-###` 收据，首次失败命令、日志、重试原因、次数和每次结果都不得覆盖。
- 必需测试只有重试后才通过时标记 `FLAKY`，不得计为稳定全绿；先定位并关闭不稳定根因，无法关闭时门禁为“未完成/受阻”。

## 新鲜证据

- 局部迭代保留本轮命令、退出码和测试结果作为过程证据，不要求生成全部 gate 收据或最终报告；最终证据必须来自最后一次生产代码、测试、资源或构建配置修改之后的执行，任何必需项变化都会使对应旧最终证据失效。
- 每项最终命令使用 `scripts/execution_evidence.py --gate <gate-id>` 生成单一用途收据，记录 `TEST-ID`、参数数组、执行目录、退出码、JUnit testcase、日志、报告路径和 SHA-256；测试和迁移自动收据没有本轮实际执行数大于零的 JUnit 时不能证明 gate，没有具体通过 testcase 时不能覆盖 BDD 场景，一份收据不得兼任其他 gate。
- 替代验证必须覆盖相同 BDD、运行条件和风险；能力损失仍标记未验证，不得用较弱证据冒充原门禁通过。

## 项目已有静态门禁发现与执行

完整交付阶段只执行与最终 diff、受影响语言、模块和 variant 相符的现有任务或配置。局部迭代复用已确认命令，只为本轮代码选择必要的最小编译；已确认命令存在且 Gradle/模块/variant 未变化时不得重新探测。真实 task 或静态门禁来源缺失且本模块必须确认 Gradle 任务时，才读取 `references/gradle-task-discovery.md`。缺少某项能力时降级并继续其他门禁，不自动安装工具、添加插件或修改依赖。

命令来源优先级：已确认实施计划、`test-cases/impact-radius.json` 的 `expected_tests`、`test-cases/test-mapping.json`、本轮执行收据、CI、README、项目脚本、用户确认。前序文件已经覆盖当前需求修订时，直接读取复用；不得为了“再确认”重复执行耗时发现。

执行顺序：

1. **Kotlin/Java 编译**：读取已确认命令或按需发现结果，优先执行受影响模块已有的 Kotlin/Java compile task；无法可靠确定独立 compile task 时，使用项目已有最小 assemble/test task 覆盖编译，不猜任务名造结果。
2. **Android Lint**：存在 Android 模块和对应 lint task 时执行受影响范围的现有 lint；最终机器证据保存本轮 XML 或 SARIF，HTML 可另存给人查看。收据解析 Fatal/Error，不能依赖 `abortOnError` 的进程退出码造绿。
3. **语言专项**：Kotlin 仅执行项目已配置的 detekt；Java 仅执行项目已配置的 Error Prone、NullAway、SpotBugs 或 Infer。遵守现有版本、task、config 和扫描范围，不临时生成规则集。
4. **质量任务**：PMD、Checkstyle 等格式或风格任务只有项目已配置时执行；其结果路由给代码质量审查，不能把格式/风格通过写成稳定性通过。
5. **跨语言扫描**：Semgrep 只有本机/项目已有 binary 且仓库已有明确 config/rules 时执行；CodeQL 只有仓库、脚本或 CI 已配置 Kotlin/Java 流程时复用。不得自动下载未知规则、创建数据库或设计新查询套件。
6. **公开契约**：公共 Java/Kotlin API 变化且项目已有 ABI/API validator 或兼容任务时执行；没有既有能力时做人工兼容审查并记录机器校验未验证。

detekt、Semgrep、CodeQL 或其他已有工具能够输出 SARIF 时，使用 `execution_evidence.py --gate android-static-analysis --report <SARIF或SARIF.JSON>` 生成独立收据。收据从报告重新统计 Error/Warning、`baselineState` 和稳定问题编号；`new/updated/unknown` Error 即使命令退出码为零也不能通过，只有报告明确标记 `unchanged` 的历史 Error 才只记录不阻断。工具不支持 SARIF 时仍保存其原生报告或编译日志，由稳定性专项明确记录版本、实际范围、分析模式和能力损失，不伪造格式转换。

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

- 直接复用共享失败分类、处理状态和降级记录模板，不在测试 Skill 维护第二套枚举或说明。
- 测试失败只证明观察结果不符；对照已确认 BDD、fixture、前置和原始证据后，才能区分生产实现、测试本身或环境问题。
- 替代测试只有覆盖同一 BDD、运行条件和风险时才等价；缺少设备、真实 UI、性能或线上能力时保持未验证，不计入全绿。

## 测试用例生成

计划确认后、生产实现前，先按已确认 BDD 生成或补强测试并观察业务断言 Red；编码后再结合实际 diff 补齐受影响的异常、恢复和回归路径。网络、权限、生命周期、并发、列表、数据、UI 状态、系统版本和构建兼容只在真实影响存在时选择，不机械生成组合；每条用例标注对应 BDD、预期结果、执行层和风险。

### 已上线业务保护

- `【修改已上线业务】` 用例证明用户已确认的新行为；测试说明保留修改前与修改后语义，不能只写“新逻辑正常”。
- `【保护已上线业务】` 用例证明本次可能波及的旧行为仍保持；优先复用项目已有回归测试，缺少时只补行为输出测试，不锁定私有实现细节。
- 当前代码表现、历史需求和已有测试互相冲突时停止并请求确认，不把疑似旧 Bug 固化，也不由测试 Skill 决定产品规则。
- 旧测试失败时先对照确认的修改项：属于明确变化才更新预期；不属于确认范围则修复生产代码。禁止删除测试、弱化断言或扩大容差掩盖回归。
- 最终 diff 新发现未登记调用方时不直接补测试造绿，先返回总入口更新需求说明和保护 Then，经用户确认后再继续。

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

不得要求用户编写或提供 Journey XML、action/step、文件名或 Gradle task。必须先从已确认需求、BDD、实际 diff、现有测试和页面入口自动生成测试用例；只有无法确定业务前置条件或预期结果时才询问缺失的业务含义。`NO_JOURNEY_FOUND` 是本 Skill 需要补齐测试物化的内部门禁，不是把技术工作转嫁给用户的提示。

### 适用性门禁

生成 Journey 前同时检查需求和实际 diff，不得因为项目有界面就默认运行。**适用性判断规则（`SKIPPED_NO_UI`/`SKIPPED_VISUAL_ONLY`、`FULL`/`PARTIAL`/`NONE` 三级聚合、两次判断一次执行、调用前置四条件）的完整清单和判定表**见 `assets/journey-harness/JOURNEY_USAGE.md`，本节只强调不可逾越的边界：

- `FULL/PARTIAL/NONE` 只是适用性，不是测试结果。Journey `PASS` 只证明它实际断言的部分，不能替代同一 BDD 所需的业务、接口、数据、视觉、性能或安全证据。
- `NO_JOURNEY_FOUND` 只允许出现在已有验证义务最终分配给 Journey、但用例未成功物化之后；无 UI 或纯视觉需求用对应 `SKIPPED_*`，不算测试失败，也不得要求用户补 Journey 场景。
- Journey 是否适用由模型根据需求、BDD、实际 diff、前置条件和预期结果判断，不要求用户选择工具；调用前按每条 BDD 记录 `FULL/PARTIAL/NONE + 原因`。
- 采用"两次判断、一次执行"：需求确认后初判（只标候选、生成草稿，不启动设备/壳）→ 编码完成后终判（读实际 diff，能力缩小则拆分路由）→ 只执行一次（终判仍有义务分配给 Journey 才物化 XML）。需求初判与实际 diff 不一致时以终判为准，并在测试报告中说明变化原因。

### BDD 物化规则

- 把 `Given` 转成可复现前置条件（启动入口/DeepLink/登录/数据/权限/语言/主题/字体/方向）；壳只负责启动应用，不能隐式满足前置条件。
- 把每个 `When` 拆成独立 action，把每个 `Then` 写成独立 verify/check，不得只隐含在操作描述中。多指、长按、双击、旋转/折叠、精确计数或复杂条件不稳定时改用项目已有 Compose/Espresso/UIAutomator 或人工测试。
- Journey 用例名、说明和 action 自然语言用中文，界面真实文案、资源标识、包名、类名和 XML schema 保持原值并在中文步骤中引用，不为翻译改变查找目标。
- XML 和最终报告必须标明覆盖的 BDD；一个 BDD 需要多层证据时，Journey 通过不改变其他证据的状态。
- Journey XML 作为当前需求测试用例，默认放 `<requirement_dir>/test-cases/journeys/<需求作用域>/[场景名].xml`；完整流程的作用域来自当前 Git 基线、确认修订和需求正文/UI/API 输入摘要，单独调用时来自当前完整输入摘要。默认 Agent 路线用 Android CLI Journey 约定的 `journey/actions/action`；可选壳路线必须用当前 Android Studio 官方模板生成的 schema，不得猜测预览 DSL。至少包含一个有效 action/step，拒绝零测试假绿。
- 不把需求用例长期保存在共享壳源码中；默认 Agent 直接读当前作用域，可选壳每次只同步当前用例集并清除上次残留 XML，防止跨项目串用。

### 默认 Android CLI Agent 执行

默认路线在当前 AI 会话中完成，不存在可以由 Python 虚构调用的 `android journey` 或 `android agent` 子命令。使用目标项目自己的 Gradle wrapper 构建已确认 module/variant（不升级 AGP）或确认目标 APK 已安装，再用 adb 启动、截图、输入、抓日志逐个执行 XML action。稳定命令链按下方，不得依赖未经实测的命令。

- **启动**：`adb -s <serial> shell am start -n <pkg>/<activity>`；`android run` 需要 `--apks` 不适用于已安装 APK，直接用 adb 启动。
- **可见断言**：`adb -s <serial> exec-out screencap -p > <step>.png` 截图后人工/AI 视觉判断。不使用 `android screen capture`（有缓存、不支持 `--device`）。
- **布局断言**：`android layout` 与 `adb shell uiautomator dump` 在部分真机返回 `null root node`，不可用时必须降级到截图视觉判断，不得假装布局可用。
- **点击/输入**：`adb shell input tap <x> <y>`；点击坐标受状态栏+控件+margin 累积偏移影响，必须先截图视觉定位真实坐标，不能用固定假设值。`adb shell input text` 不支持中文，涉及中文输入用英文等价用例覆盖并说明等价性。
- **行为断言**：`adb logcat -d -s <TAG>:<level>` 抓埋点/日志，验证内部行为而非仅页面可见结果。

action 只包含一个操作或一个可见断言，严格按顺序独立判断；任一步失败、应用退出、崩溃或冻结时停止该 Journey，后续 action 标记跳过。
每步记录脱敏命令、截图/布局 SHA-256、状态和说明；不得把 AI 观察描述当作不存在的工具返回值。按 `../android-implement-and-verify/references/specialist-result.schema.json` 输出 `specialist=android-test-and-fix/journey-agent` 统一结果，`executed_tests` 为实际完成的 Journey 数，`executed_checks` 为实际判断的 action 数，最终报告用 `AGENT` 证据类型。
Android CLI、adb 或设备不可用时先路由到项目已有 Compose/Espresso/UIAutomator；仍无等价能力时把对应 BDD 标为未验证。设备只能完成部分步骤时保留 `PARTIAL + ENVIRONMENT_FAILED`，不得用中断前截图冒充通过。

### 可选壳项目执行

只有用户明确选择壳、默认 Agent 路线不可用且壳已经初始化时才调用 `scripts/run_journey.py`：

```bash
python3 ai-skills/android-delivery-skills/android-test-and-fix/scripts/run_journey.py \
  --config ai-skills/android-delivery-skills/profiles/local.yaml \
  --ui-impact behavior --applicability PARTIAL \
  --covered-then BDD-001 --uncovered-then BDD-002
# 已安装目标 APK 时可用 --skip-build（必须配 app_package_name）；临时指定用例目录用 --journeys-dir。
```

参数均由 Skill 根据需求、BDD 和最终 diff 生成，不要求用户提供；行为型 Journey 缺少 `FULL/PARTIAL` 或至少一个覆盖 Then 时脚本拒绝启动；无 UI 或纯视觉需求不调用本脚本。**壳执行器的零测试假绿防护、APK 包名校验、隔离缓存、force-stop 前置、截图证据收集、退出码语义和可选壳一次性初始化**等完整规则见 `assets/journey-harness/JOURNEY_USAGE.md`，本节不重复。退出码 `0` 必须结合状态区分 `PASS`/`SKIPPED_*`/`PREFLIGHT_PASS`；`1` 表示壳/环境/证据不足，默认降级到 Agent 路线不阻断流程；`2` 表示连续两次真实 UI 断言失败，确认生产缺陷才改目标代码，用例/数据错误只修测试侧。

## 命令选择规则

不得写死命令。先识别项目模块和已有命令，再选择最小验证：

- 环境识别：例如 `which adb`、`adb devices`、Android CLI 可用性检查；Gradle 任务未知时按本模块 reference 处理。
- 构建：例如 `./gradlew :app:assembleDebug`。
- 单测：例如 `./gradlew :app:testDebugUnitTest`。
- 指定测试：例如 `--tests "完整类名"`。
- Lint：例如 `./gradlew :app:lintDebug`。
- 仪器测试：例如 `./gradlew :app:connectedDebugAndroidTest`。
- 设备：`adb devices`、`adb logcat`、`adb exec-out screencap -p`。

没有设备时仅跳过确实依赖设备的项。局部迭代仍执行受影响测试和必要编译；完整交付仍执行本地单测、构建和 lint。没有现成测试框架时，优先使用项目已有依赖补最小测试；新增重型依赖需用户确认。

## 完整交付全绿门禁

- 必需：新增/受影响测试、相关模块测试、assemble、lint 0 Error。
- 已上线业务：全部 `【修改已上线业务】` 和 `【保护已上线业务】` 必需 BDD 均有最终代码上的真实 testcase 或已执行人工证据。
- 条件必需：按业务影响选择仪器或截图测试；Journey 只执行 `FULL` 或 `PARTIAL` 中实际分配给它的验证义务。
- 每个 BDD 使用 `COVERED_AUTOMATED`、`COVERED_MANUAL`、`UNVERIFIED`、`BLOCKED` 或 `NOT_APPLICABLE`；`COVERED_MANUAL` 必须已经实际执行并有证据。
- 全部已确认 BDD 都必须进入 `test-mapping.json`；`traceability.md` 由机器自动渲染。
- 测试映射：`COVERED_AUTOMATED` 义务必须在 `<requirement_dir>/test-cases/test-mapping.json` 中登记，`mapping_status=CURRENT`，且登记的 `test_ids` 出现在执行收据里；STALE 映射表示需求已增量但测试未同步，直接阻断。
- 所有必需 BDD 均为 `COVERED_AUTOMATED` 或有证据的 `COVERED_MANUAL`；任何工具不得越过自身证据边界。
- 失败数为 0，P0/P1 测试缺口为 0。未执行项不得计为通过。
- 必需测试不得存在未关闭的 `FLAKY`，最终证据必须在最后一次修复后重新执行。

## 变异测试（防假断言）

PIT/pitest 用于高风险业务逻辑的断言强度检查，不是每个需求的固定步骤：

- 当前影响半径含 `L3` 或 profile 明确 `testing.mutation_testing.required=true` 时必须输出 `mutation_testing`；L1/L2 可省略。
- 有变异存活 = 断言没有真正约束行为（测试是假的，或需求增量后断言没更新）。通过结论要求 `generated_mutants > 0` 且 `survived = 0`；存活变异阻断完整通过，必须补强断言并重跑。
- 优先复用项目已有 pitest 配置；没有时只对本次 diff 涉及的类以最小变异算子集运行，不自动升级 AGP/Gradle、不新增重型依赖。Kotlin 目标需要 pitest Kotlin 插件。
- Kotlin 项目的编译器生成代码（`kotlin.jvm.internal.Intrinsics` 的 null-check、`checkParameterIsNotNull` 等）不是业务逻辑，业务测试无法也无需杀死这些变异。必须配置 `excludedClasses = ["kotlin.jvm.internal.Intrinsics"]` 排除，否则正常 Kotlin 交付永远无法满足 `survived=0`，使 FULL_PASS 形同虚设。排除的是编译器插桩，不排除任何业务代码。
- 诚实边界：变异测试基于 JVM 字节码，覆盖 Unit Test 层业务逻辑（“AI 不更新断言”风险最高、命中最高的层），不覆盖 Robolectric 和 instrumented 测试。机器能证明“断言杀掉了变异”，仍读不懂测试语义正确性——后者由 route 阶段 `android-review-diff` 复核“映射声称改了测试 vs 测试文件真实 diff”。
- 已要求 PIT 但最终范围只有资源或配置、没有业务字节码时，允许 `languages=["NONE"]`、零变异并说明原因。

## 架构测试层（ArchUnit，补 M16 六条不变量）

架构约束可由 AI 生成可执行测试固化，替代易碎的手写扫描脚本：

- 每个义务在 `test-mapping.json` 的 `architecture_tests` 字段登记它的架构约束（如“埋点只在统一出口”“X 包不依赖 Y”“禁绕过 Repository 直接调网络”）。
- AI 生成 ArchUnit 测试进项目 test 源集，和普通 JUnit 一起跑，进现有 `android-test-and-fix` 门禁，零额外门禁基建；通过 `obligation_test_cases` 机制登记即可。
- 复用原则：项目已有 ArchUnit 就用；没有时用纯 Kotlin 反射写（零依赖）；需要强表达力且用户同意才引入 `archunit-junit5`。不自动升级 AGP/Gradle、不新增重型依赖。
- 边界：ArchUnit 是 JVM 编译期结构层，与六条不变量（AI 语义审查 + 控制面审计）互补不重叠；时序类约束（A 早于 B）仍归变异测试。

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

局部迭代只输出：本轮修改点、受影响测试/必要编译、命令与结果、自修复记录、未验证项和剩余风险。不得套用完整交付结论。

完整交付输出：

1. 测试范围
2. 已上线业务修改、保护项及其回归结果
3. 追溯覆盖率：`BDD-ID -> 测试 ID/实际人工验收 -> 覆盖状态 -> 最终证据`
4. 项目已有静态门禁：Kotlin/Java 编译、Lint、语言专项、跨语言扫描和 API/ABI 任务的发现依据、命令、退出码、报告和能力损失
5. 历史债务：`NEW` / `AFFECTED` / `PRE_EXISTING` / `UNKNOWN_ORIGIN` 数量、处置和证据
6. release/R8/Java 兼容：适用性、variant、命令、结论与未验证项
7. 条件能力矩阵：OpenAPI / 迁移 / 泄漏 / 性能 / UI-A11y / 安全隐私的适用性、设备类型和结论
8. 测试用例矩阵：BDD 场景、风险等级、必需性、主/备用执行器、主流程 / 备选 / 异常 / 恢复 / 非功能及不适用理由
9. TDD 结论：Red-Green-Refactor 是否完成；自动化 BDD 必须有有效 `.state/tdd-cycle.json`，不能只凭最终 Green
10. 自动化可执行项和需要人工验证项
11. 最终新鲜证据：命令、退出码、测试数、关键输出和报告/产物路径
12. flaky 状态：首次失败、重试原因/次数/结果、是否已关闭
13. 自修复轮次、根因和修改
14. 失败项与降级记录（失败分类、原专项能力/工具、证据、AI 替代、能力损失、所需输入、当前状态）
15. 未验证项和剩余风险
16. 门禁结论：全绿 / 代码与本地门禁完成、真机专项待验证 / 未完成 / 受阻
