# Android Delivery Skills 开源设计依据

本文记录本套流程为什么这样设计、参考了哪些高 Star 开源项目、吸收了什么以及明确拒绝照搬什么。维护或重构 Skill 时先读本文；日常执行需求时不必全文加载。

## 目录

1. [设计目标](#设计目标)
2. [筛选方法](#筛选方法)
3. [Android 交付 Top15](#android-交付-top15)
4. [Java 老项目补充参考](#java-老项目补充参考)
5. [排除与历史补充参考](#排除与历史补充参考)
6. [第一轮设计决策](#第一轮设计决策)
7. [第二轮设计决策](#第二轮设计决策)
8. [明确不照搬](#明确不照搬)
9. [长期不变量](#长期不变量)
10. [维护规则](#维护规则)

## 设计目标

本流程面向新旧 Android 项目的串行需求交付，核心目标是：

- 先确认需求，再修改代码；不从代码或工具结果反推产品需求。
- 把需求、BDD、实现、测试和执行证据连成可追溯闭环，减少遗漏。
- 遵守目标项目既有架构，保持高内聚、低耦合和最小修改，不强推技术迁移。
- Kotlin 作为现代 Android 优先方向，Java 老项目作为一等支持对象，混合项目不复制第二套流程。
- 用真实命令、日志、报告和设备结果支撑结论；未验证项不得写成通过。
- 失败时先找根因，再做单变量最小修复；不得用删测试、弱化断言或重复碰运气造绿。
- 不承诺数学意义上的“零 Bug”，而是保证缺少必需证据时阻断完成声明。

## 筛选方法

Star 数是 2026-07-18 的 GitHub 调研快照，只用于说明社区采用度，不作为设计正确性的唯一依据。本表不是全 GitHub 绝对排名，而是按以下方法得到的本流程相关 Top15：

1. 候选必须直接覆盖需求驱动开发、Android/Kotlin/Java 架构、异步并发、静态分析、契约、泄漏、性能、安全、UI 或自动化测试中的至少一项。
2. Kotlin/Android 代表现代主路径，Java-first 项目用于补足老项目和混合语言证据；两者不因语言不同复制交付流程。
3. 同一能力只保留更贴近当前目标或维护更活跃的代表，避免用多个同类工具堆满名额。
4. 逐个核对仓库文档、源码目录、规则/查询、测试或报告能力；不只根据项目名和 Star 推断。
5. 只吸收可迁移的设计原则，不因排名强制引入依赖、升级构建或改变旧项目架构。

Star 会持续变化，后续维护只需更新快照日期和数值；除非项目能力或本流程目标改变，不应因名次小幅波动重写决策。

## Android 交付 Top15

Top15 保持 Kotlin/Android 优先，同时要求原则能落到 Java 老项目；Java 专项工具按下一节补充，不因 Star 排名强制接入。

| 排名 | 项目 | 调研时 Star | 与本流程的直接关系 | 吸收的做法 | 不照搬的做法 |
| ---: | --- | ---: | --- | --- | --- |
| 1 | [obra/superpowers](https://github.com/obra/superpowers) | 256,945 | Agent 需求与验证流程 | 需求澄清、根因调查、行为级 Red-Green、完成前新鲜证据 | 每个小改动都写完整设计、强制多智能体、频繁自动提交或删除旧实现重写 |
| 2 | [github/spec-kit](https://github.com/github/spec-kit) | 122,078 | 规格与追溯 | 稳定需求 ID、场景边界、跨产物覆盖分析 | 为每个需求复制完整 spec/plan/tasks/checklists 和复杂状态管理 |
| 3 | [android/architecture-samples](https://github.com/android/architecture-samples) | 45,759 | Android 架构与分层测试 | 清晰层边界、Repository/DataSource、Unit/Integration/E2E 分层、fake 隔离 | 把示例架构当成所有旧项目模板 |
| 4 | [square/leakcanary](https://github.com/square/leakcanary) | 29,949 | Kotlin/Android 泄漏证据 | Leak Trace、Heap/Object Inspector、生命周期前后动态泄漏验证 | 无条件新增依赖，或把工具输出直接当根因 |
| 5 | [OpenAPITools/openapi-generator](https://github.com/OpenAPITools/openapi-generator) | 26,572 | OpenAPI 与 Kotlin 模型 | 机器可读 schema、Kotlin client/data class/Room 模板的一致性思路 | 直接覆盖旧项目手写网络层或信任未经审查的生成输入 |
| 6 | [android/compose-samples](https://github.com/android/compose-samples) | 23,315 | Compose 状态与 UI 测试 | UI 状态、主题、输入、导航、UI 测试和自适应设备形态 | 无条件迁移 Compose |
| 7 | [android/nowinandroid](https://github.com/android/nowinandroid) | 21,540 | Kotlin Android 生产样例 | 单向数据流、模块依赖图、截图测试、Benchmark、变更证据 | 照抄模块数量、Convention Plugin 或固定覆盖率阈值 |
| 8 | [MobSF/Mobile-Security-Framework-MobSF](https://github.com/MobSF/Mobile-Security-Framework-MobSF) | 21,449 | 移动端安全分析 | Android 包、Manifest、代码和配置的静态/动态安全证据分层 | 把一次扫描写成渗透测试通过，或强制每个需求部署完整平台 |
| 9 | [semgrep/semgrep](https://github.com/semgrep/semgrep) | 15,941 | Kotlin/Gradle 静态规则 | 项目已有规则优先、结构化告警和可审查规则 | 把社区版单文件/有限跨函数能力冒充完整调用链证明，或自动下载未知规则 |
| 10 | [mobile-dev-inc/Maestro](https://github.com/mobile-dev-inc/Maestro) | 14,959 | Android E2E 自动化 | 可读 Flow、条件等待、模拟器/真机执行和结构化报告 | 本轮替换 Journey，或强制老项目安装第二套 UI 测试体系 |
| 11 | [Kotlin/kotlinx.coroutines](https://github.com/Kotlin/kotlinx.coroutines) | 13,800 | Kotlin 协程与 Flow 契约 | 结构化并发、取消传播、Flow/callbackFlow 生命周期语义 | 把 API 名清单当成所有权分析，或要求旧项目迁移全部异步实现 |
| 12 | [github/codeql](https://github.com/github/codeql) | 9,844 | Kotlin/Java 跨文件数据流 | Kotlin extractor、模型和查询提供的跨文件证据 | 未配置项目中自动建库/下载套件，或把查询零结果写成无风险 |
| 13 | [detekt/detekt](https://github.com/detekt/detekt) | 7,007 | Kotlin 原生静态分析 | 复用项目既有规则、配置、baseline 和报告 | 自动接入插件、更新 baseline、批量 suppress 或以风格告警替代语义复核 |
| 14 | [google/perfetto](https://github.com/google/perfetto) | 6,236 | Android 性能与内存 Trace | Java/Kotlin/native profiling、Trace SQL 和调用时间线证据 | 无 Trace 发明性能根因，或用模拟器单次结果宣称正式性能通过 |
| 15 | [androidx/androidx](https://github.com/androidx/androidx) | 6,038 | AndroidX 实现与验证基准 | Lifecycle、Compose、Test、Benchmark 和 Kotlin Lint detector 的真实契约 | 复制内部实现、强制升级 AndroidX，或把最新 API 当成旧项目唯一解 |

## Java 老项目补充参考

以下 Star 同为 2026-07-18 GitHub API 快照。它们补充 Top15 的 Java、构建和测试证据，不构成另一套强制工具链。

| 项目 | 调研时 Star | 采用点 | 边界 |
| --- | ---: | --- | --- |
| [ReactiveX/RxJava](https://github.com/ReactiveX/RxJava) | 48,235 | Java 异步流、Scheduler、Disposable 和终止语义 | 不强制把旧项目迁移到 RxJava，也不把 dispose 调用存在等同于生命周期正确 |
| [gradle/gradle](https://github.com/gradle/gradle) | 18,704 | source set、variant、Java/JVM toolchain 和可复用任务发现 | 不自动升级 Gradle、JDK 或重写构建体系 |
| [facebook/infer](https://github.com/facebook/infer) | 15,666 | Java 空值、资源、并发静态证据 | 只在项目已有配置时执行，不把 Java 优势冒充 Kotlin 完整覆盖 |
| [mockito/mockito](https://github.com/mockito/mockito) | 15,444 | 复用 Java 老项目既有测试替身 | 不用内部方法调用次数代替业务行为断言 |
| [OWASP/mastg](https://github.com/OWASP/mastg) | 13,059 | 移动安全验证边界与动态证据 | 不把静态扫描写成完整安全测试通过 |
| [android/testing-samples](https://github.com/android/testing-samples) | 9,295 | Java/Android 测试框架、runner 和分层示例 | 不复制样例依赖或强制迁移测试框架 |
| [google/error-prone](https://github.com/google/error-prone) | 7,208 | Java 编译期常见错误 | 未配置项目不自动接入 compiler plugin |
| [robolectric/robolectric](https://github.com/robolectric/robolectric) | 6,024 | 无设备 Java/Android 行为测试 | 不用 Robolectric 冒充真机、厂商 ROM 或硬件证据 |
| [uber/NullAway](https://github.com/uber/NullAway) | 4,079 | Java Nullability 与低成本 NPE 约束 | 不批量补注解或把零告警写成绝对无 NPE |
| [spotbugs/spotbugs](https://github.com/spotbugs/spotbugs) | 3,911 | Java bug pattern 与历史报告 | 不清理全仓库历史债务，不更新 baseline 掩盖新增问题 |

## 排除与历史补充参考

以下项目并非质量差，而是没有占用 Android 交付 Top15 名额：

- **OpenHands、Cline、Aider、Continue**：属于通用 Agent/编码工具，和 Superpowers、Spec Kit 的流程能力重叠；Aider 的 repo context 与编辑后 lint/test 仍作为 M03、M08 的历史补充依据，OpenHands 的工作区权限边界只保留为全局安全原则的历史参考。
- **Fastlane**：更偏 CI、签名和发布自动化，留到第三轮 CI/报告聚合讨论。
- **Appium**：跨平台能力强但运行体系较重；当前 UI 自动化候选已经保留 Maestro，且本轮不改 Journey。
- **Swagger Codegen**：与维护更活跃、Kotlin 模板更完整的 OpenAPI Generator 能力重复。
- **Koin**：是具体 DI 方案，强纳入会违背兼容 Hilt/Dagger/手写 DI 和老项目的目标。
- **ktlint**：主要解决格式与风格，不承担生命周期、泄漏或业务正确性证明。
- **Retrofit、OkHttp**：是业务网络库而非交付门禁；接口核验仍兼容它们，但不绑定为强制方案。

## 第一轮设计决策

### M01 需求质量门禁

- **来源**：Spec Kit 的 clarification、spec 场景和 requirement quality checklist。
- **决策**：只引入稳定 `REQ-###`、五类场景检查和最多 5 个高影响问题，不引入完整 Spec Kit 文件体系。
- **原因**：需求遗漏往往发生在编码前；先检查完整性、清晰度、可衡量性和冲突，比编码后补测试成本更低。

### M02 需求追溯矩阵

- **来源**：Spec Kit 的 requirement/task coverage analysis，以及 Superpowers 的 requirements checklist。
- **决策**：每个需求维护 `REQ -> BDD -> 实现文件 -> 测试 -> 命令 -> 证据` 映射。
- **原因**：代码覆盖率不能证明需求覆盖；本流程优先要求已确认需求映射率为 100%。
- **边界**：追溯表是当前需求的 Markdown 交付物，不是持久化状态机或通用 JSON Schema。

### M03 语义影响路由

- **来源**：Aider 的 repo context、Now in Android 的模块依赖图、Spec Kit 的跨产物一致性检查。
- **决策**：路由除 UI/API 文件名外，还识别数据、系统、构建、架构和测试候选，并对可读改动文件做轻量内容信号检查；Diff Reviewer 再对七类影响逐项给出绑定真实文件的语义结论，最终条件门禁取二者并集。
- **原因**：`Client.kt`、DI Module、Manifest、Proto 或 Gradle 改动不能只靠文件名后缀判断。
- **边界**：脚本只输出候选证据，不维护无限框架关键词；AI 只确认影响类别而不替代专项结论。语义结果必须绑定当前代码摘要、项目相对路径和原因，不能用自然语言绕过机器门禁。

### M04 架构边界卡片

- **来源**：Superpowers 的 design for isolation、Android Architecture Samples 和 Now in Android 模块化实践。
- **决策**：最小修改预览必须说明组件职责、输入输出、依赖方向、复用点和明确不修改范围，并落实为真实包/文件、集中依赖装配及核心 KDoc/非显然逻辑注释；代码质量结果用四项结构化检查阻止只写“架构清晰”。
- **原因**：高内聚低耦合必须落实为可审查边界，不能只写成口号。
- **边界**：始终服从现有项目架构；只有功能横跨多个变化原因且项目无现成边界时才建最小功能内分层，不强制 MVVM、MVI、Clean、Compose、Hilt 或拆模块，也不要求给样板代码逐行注释。

### M05 行为级 Red-Green

- **来源**：Superpowers 的 TDD 和 systematic debugging。
- **决策**：Bug 与可观察行为变更优先先复现失败，再做最小实现并转绿；不要求删除旧项目已有代码，也不强制每个简单方法单独测试。
- **原因**：没有观察到正确的 Red，无法证明新增测试真的能捕获缺陷。

### M06 测试场景完整性

- **来源**：Spec Kit 的 primary/alternate/exception/recovery/non-functional 场景，以及 Android 官方样例的分层测试。
- **决策**：按需求影响选择场景和测试层，不维护无限故障枚举；不适用项必须写原因。
- **原因**：场景分类比固定报错列表更能覆盖未知需求，同时避免所有测试类型无差别执行。

### M07 防 flaky 规则

- **来源**：Maestro 的 smart waiting、Superpowers 的 condition-based waiting 和根因优先原则。
- **决策**：禁止用固定 sleep 掩盖时序；重试只处理环境不稳定，并保留首个失败证据。
- **原因**：只在重试后通过的测试不能作为稳定通过证据。

### M08 新鲜证据门禁

- **来源**：Superpowers 的 verification-before-completion、Aider 的自动 lint/test、Now in Android 的 CI 报告产物。
- **决策**：完成声明前必须使用最终代码重新运行必需命令，记录退出码、测试数、关键输出和报告路径。
- **原因**：修改前或中间轮次的通过结果不能证明最终 diff 可交付。

### M09 Skill 行为评测集

- **来源**：Superpowers 的 Skill forward testing、Spec Kit 的 self-test 和 Android 官方样例的场景化测试。
- **决策**：用代表性 Android 需求验证需求门禁、路由、测试选择、阻断和禁止声明，而不只测试 Python 函数。
- **原因**：脚本单测通过不能证明更换 AI 后仍会正确理解并执行 Skill。

## 第二轮设计决策

第二轮不新增六个 Skill，而是把条件能力放回现有职责，并统一使用“适用 / 不适用 / 未验证 / 通过 / 阻塞”。缺少真机只限制对应证据与完整交付声明，不中断其他可执行门禁。

### M10 OpenAPI 条件门禁

- **来源**：OpenAPI Generator 的机器可读契约与校验能力，以及第一轮契约不脑补原则。
- **决策**：接口变化时优先校验正式 OpenAPI/Swagger 并核对本次 operation/schema；不自动生成或覆盖旧项目代码。

### M11 数据迁移门禁

- **来源**：Android Architecture Samples/Now in Android 的持久化测试与兼容实践。
- **决策**：真实验证旧 schema/旧数据到新版本；缺少旧样本时标未验证，禁止清数据或 destructive migration 造绿。

### M12 动态泄漏门禁

- **来源**：LeakCanary 的 Leak Trace 与生命周期引用链证据。
- **决策**：生命周期或资源释放候选才执行；优先复用项目已有能力，不自动增加 LeakCanary，静态审查不能冒充动态无泄漏。

### M13 性能门禁

- **来源**：Now in Android 的 Benchmark/性能报告以及 Perfetto 的数据驱动诊断。
- **决策**：只对明确指标或性能敏感 diff 触发；阈值来自需求/项目/基线，正式性能结论原则上使用固定真机。

### M14 UI/A11y 门禁

- **来源**：Compose Samples/Now in Android 的 UI semantics、截图和多设备测试实践。
- **决策**：视觉验收保持手动独立，自动 A11y 归测试；无设备仍做静态语义检查，动态 TalkBack/焦点保持未验证。外部 Figma XML 产物在 Delivery 接管时按已确认需求、项目规则、I18n 和装饰/功能语义做交接检查，不修改外部 Skill，也不让其越权生成业务代码。

### M15 安全隐私门禁

- **来源**：MobSF 的移动端静态/动态安全证据，以及 AndroidX/Android 官方项目的 Manifest、网络、存储与日志安全实践。
- **决策**：权限、导出组件、WebView、用户数据和敏感日志变化才触发；复用项目已有扫描，不把静态检查写成渗透测试通过。

### M16 Kotlin / Java Android 静态语义分析

- **来源**：kotlinx.coroutines 与 RxJava 的异步契约，AndroidX 的 Lifecycle/Compose/Lint 实现，LeakCanary 的引用链模型，以及 detekt、Error Prone、NullAway、SpotBugs、Infer、Semgrep、CodeQL 的静态能力。
- **决策**：不维护无限规则清单，统一用六条不变量审查：短生命周期不被长生命周期持有、注册/解绑成对、获取/释放成对、异步任务不超过宿主、清理路径可达、共享状态具有并发纪律。
- **语言边界**：Kotlin 优先、Java 一等支持；混合调用额外核对 Nullability/platform type、primitive/boxed、异常、泛型、SAM/Callback、取消传播和公开 API/ABI，不复制第二套流程。
- **执行**：`android-audit-stability` 建立资源所有权表和按需并发访问表、复核必要调用链并解释告警；`android-test-and-fix` 只发现和执行项目已有编译、Lint、语言专项、跨语言扫描、测试、release/R8 与 API/ABI 任务。
- **历史债务**：告警区分 `NEW`、`AFFECTED`、`PRE_EXISTING`、`UNKNOWN_ORIGIN`；不更新 baseline 掩盖新增问题，也不借需求清理无关旧问题。
- **证据边界**：生成代码、反射、AIDL、JNI、闭源 SDK 或 release 行为无法确认时标未验证；静态零告警只能写“未发现明确静态问题”，不能宣称无泄漏、线程安全或实机通过。
- **原因**：项目配置变化只影响能力发现与证据，不要求修改路由脚本或强制迁移语言、AGP、Gradle、JDK 和测试框架。

### M17 自适应分层自动化测试

- **调研日期**：2026-07-19。
- **来源**：[Android 官方测试策略](https://developer.android.com/training/testing/fundamentals/strategies) 的单元、组件、功能、应用和候选版本分层，[Android 测试基础](https://developer.android.com/training/testing/fundamentals) 的可测试架构与解耦，[UIAutomator](https://developer.android.com/training/testing/other-components/ui-automator)、[Espresso](https://developer.android.com/training/testing/espresso) 和 [Compose UI Test](https://developer.android.com/develop/ui/compose/testing) 的能力边界；Maestro、Robolectric、Kaspresso、Paparazzi、Kotest 属性测试和 PIT Mutation Testing 作为补充对照。
- **决策**：把每个 BDD 的复合 Then 拆成 `BDD-001/T1` 形式的原子验证义务，按 `L1/L2/L3/BLOCKED` 做需求初判和最终 diff 终判，再为每项选择最低且足够的测试层。Journey 只做少量关键黑盒旅程，并根据原子 Then 分配用 `FULL/PARTIAL/NONE` 表达整条 BDD 的适用性；Journey 通过只覆盖它实际断言的 Then。
- **老项目边界**：低 AGP 项目继续使用自身 wrapper 构建 APK，当前 AI 会话优先使用 Android CLI/adb 对已安装 APK 执行 Journey；已经初始化的独立壳只作可选回退。项目已有 Compose/Espresso/UIAutomator 时复用，不升级目标项目。
- **工具边界**：不自动安装 Maestro、Appium、Kaspresso、属性测试或 Mutation 工具。只有场景仍适合黑盒 UI、Journey 引擎能力不足且项目已有或用户允许时才考虑 Maestro；业务上不适合 Journey 的场景不能通过换黑盒引擎解决。
- **原因**：成熟方案不是万能 E2E 兜底，而是大量快速确定的小测试加少量高保真流程。原子证据可以补齐 UI 与业务混合需求、Journey 部分覆盖和无设备降级，同时避免每个小改动机械执行完整测试矩阵。
- **拒绝**：不按代码行数判断风险，不把 Journey/截图/Unit/静态扫描越权写成整条业务通过，不把计划人工测试写成已覆盖，不建立跨需求持久化状态机。

### M18 需求增量与最终证据新鲜度

- **调研日期**：2026-07-19。
- **来源**：[Git diff](https://git-scm.com/docs/git-diff) 的 name-status、rename detection、patch 与工作树比较能力，[JSON Schema 2020-12](https://json-schema.org/draft/2020-12) 的可移植数据契约；结合本流程“串行需求、外部基线、最终代码新鲜证据”的目标。
- **决策**：`init` 只读需求，不触碰 Git 基线；`check-env` 在干净工作区同时保存 Git 起点与需求起点。中途重读按最近确认修订和追溯表输出差异；独立修订清单逐项记录增改删、替代、确认/待定/拒绝/冲突及删除处置，只有全部解决才推进版本。路由消费 `A/M/D/R` 和实际 patch，最终 `delivery-result.json` 必须与当前有效 Then 集合精确一致，并绑定需求修订、基线与工作树摘要。
- **职责边界**：需求修订脚本只校验连续性和原子保存，不判断业务语义或修改 Git；Git 脚本不决定路由，最终门禁不运行测试或修代码。Journey 只使用已确认修订的用例作用域，并只声明实际覆盖的 Then。
- **原因**：提示词规则无法单独证明某个 Skill 已执行，也无法阻止测试后代码变化继续复用旧结果；最小结构化契约可以关闭假绿，同时保持脚本可替换和跨模型可读。
- **拒绝**：不新增通用 phase/state 状态机，不把待定/冲突或聊天内容自动合并进总需求，不把文本删除直接等同于删除公共代码，不用文件名代替真实 patch，不让最终门禁执行 Git 写操作、测试或发布。

### M19 条件门禁快照与执行收据

- **调研日期**：2026-07-19。
- **来源**：JSON Schema、Gradle/JUnit/Android Lint 原生报告；[Now in Android Build](https://github.com/android/nowinandroid/blob/main/.github/workflows/Build.yaml) 的分层 Build/Lint/Roborazzi/Instrumentation、[Lottie Validate](https://github.com/airbnb/lottie-android/blob/master/.github/workflows/validate.yml) 的 Lint/Unit/API/Snapshot 独立 Job，以及 [Detekt Danger](https://github.com/detekt/detekt/blob/main/bots/dangerfile.js) 的 diff 缺测试提示。
- **决策**：`route` 把四类条件门禁及直接依据保存到项目外快照，并绑定需求修订、UI/API 输入、Git 基线和代码摘要。Diff Reviewer 使用专项结果 version 3 逐项确认七类语义影响，最终门禁把它与脚本快照取并集。自动命令由独立执行器按单一 gate 保存不可覆盖 attempt、JUnit testcase、Lint 机器报告和脱敏日志；测试/迁移收据强制要求非零 JUnit，普通自动收据不能越权证明专项 gate。稳定性固定记录泄漏/性能/安全适用性，Journey 按需扩展。最终结果契约保持 version 4。
- **职责边界**：路由快照只表达候选，不替代业务适用性终判；执行器只运行已经选定的命令，不选择 task、不修代码；最终门禁只校验，不运行命令。
- **原因**：自然语言约束不能阻止条件专项被漏写，也不能证明 AI 填写的退出码和报告路径真实存在；但强迫普通 Review 填写 Journey 字段也会制造维护成本。最小信封加原生报告在关闭假绿的同时避免建立通用状态机。

### M20 Android CLI Agent Journey 默认路线

- **调研日期**：2026-07-19。
- **来源**：Google Android CLI Skill 的 Journey action 顺序、失败和结构化汇总规则，以及 Android CLI `run/layout/screen` 的已安装 APK 操作能力。
- **决策**：Journey 适用时，由执行当前 Skill 的 AI 会话优先读取 XML，使用 Android CLI/adb 逐个 action 操作和验证；统一专项结果保存 Journey 数、action 数、命令及布局/截图摘要。AGP 9 Studio Labs 壳保留为已经初始化后的可选 JUnit 回退。
- **边界**：当前 Android CLI 没有可由 Python 调用的 `android journey` 或 `android agent` 子命令，不创建伪命令；没有 Agent 会话、设备或等价 UI 引擎时保持未验证。壳未初始化不再阻断默认路线，也不自动要求用户打开 Android Studio。

## 明确不照搬

- 不为每个小需求自动生成并提交多份设计、计划和任务文档。
- 不自动创建分支、worktree、stash、commit、push、reset、checkout 或 clean。
- 不因高 Star 示例而强制迁移技术栈、架构、AGP、Gradle、Compose、Hilt 或依赖版本。
- 不要求所有代码机械追求 100% 行覆盖；优先保证需求追溯 100%，覆盖率阈值服从项目基线。
- 不把多智能体、Maestro、LeakCanary、OpenAPI Generator 或其他工具设为所有项目的强制依赖。
- 不把工具失败、测试失败或静态告警直接等同于生产代码缺陷。

## 长期不变量

以下原则变化时必须由用户明确确认，并同步所有相关 Skill、脚本和测试：

1. 完整需求只有一个总入口：`android-implement-and-verify`。
2. 需求确认前不修改代码；需求确认后默认直接编码，不固定增加冗长方案会。
3. 当前项目事实优先，不脑补接口、字段、设计、架构或测试结果。
4. 当前需求 Git 基线隔离串行需求；工作区不干净时停止，不自动处理用户改动。
5. 最小修改和单一职责是全局默认，不需要用户重复提醒。
6. `android-verify-ui` 保持手动独立；Journey 测试归 `android-test-and-fix`，只覆盖 `FULL/PARTIAL` 中实际分配给它的关键用户旅程。
7. Git 提交和推送必须获得用户明确授权。
8. 没有新鲜执行证据时不能声明完成；没有动态证据时不能宣称无泄漏、无性能问题或实机通过。
9. 缺少真机不停止其他可执行门禁；只限制对应动态能力和完整交付结论。
10. 第二轮条件能力复用现有 Skill 和项目工具，不自动安装依赖或扩张为六个新 Skill。
11. Kotlin/Java/Android 静态审查以六条不变量、语言边界和必要调用链为核心；工具零告警不能改写成无泄漏或线程安全。
12. 老项目历史债务与本次新增问题必须分离；不更新 baseline 造绿，也不扩大需求清理无关旧问题。
13. 每个已确认 BDD 的必需原子 Then 必须有新鲜自动证据、实际人工证据或明确阻塞；任一工具的通过不得覆盖它没有断言的风险。
14. `init` 永不删除需求 Git 基线；中途需求变化保留未变化 ID，最终通过必须绑定当前需求、基线和工作树摘要。
15. 新增 Kotlin/Java 核心代码必须落实职责分层、依赖方向、可测试构造和必要 KDoc/核心注释；代码质量专项不得用自然语言摘要省略这四项检查。

## 维护规则

- 修改跨 Skill 原则时，同步 `_shared/android-global-rules.md` 和本文对应决策。
- 修改完整流程时，同步 `android-implement-and-verify/SKILL.md`、导航文档和行为评测场景。
- 修改路由逻辑时，同步 `scripts/delivery.py`、`scripts/tests/test_delivery.py` 和相关场景预期。
- 修改测试门禁时，同步 `android-test-and-fix/SKILL.md`；不得只改说明不改执行证据要求。
- 修改第二轮条件能力时，同步 `android-implement-and-verify/references/conditional-capability-gates.md`、主责 Skill、route 提示和对应行为评测场景。
- 修改 Kotlin/Java 生命周期、并发、语言边界或静态工具策略时，同步 `android-audit-stability/references/kotlin-java-static-analysis.md`、稳定性 Skill、测试执行 Skill、代码质量 Skill 和行为评测场景。
- 新增外部参考时记录项目、采用点、拒绝点和日期；不要因为 Star 高就复制其全部流程。
- 如果项目实践与本文冲突，以目标项目更严格的 `AGENTS.md` / `CONTRIBUTING.md` 和用户明确要求为准。
