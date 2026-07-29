# Android Delivery Skills 开源设计依据

本文记录本套流程为什么这样设计、参考了哪些高 Star 开源项目、吸收了什么以及明确拒绝照搬什么。维护或重构 Skill 时先读本文；日常执行需求时不必全文加载。

## 目录

1. [设计目标](#设计目标)
2. [筛选方法](#筛选方法)
3. [Android 交付 Top15](#android-交付-top15)
4. [Java 老项目补充参考](#java-老项目补充参考)
5. [排除与历史补充参考](#排除与历史补充参考)
6. 第一轮设计决策
   - [M01 需求质量门禁](#m01-需求质量门禁)
   - [M02 需求追溯矩阵](#m02-需求追溯矩阵)
   - [M03 语义影响路由](#m03-语义影响路由)
   - [M04 架构边界卡片](#m04-架构边界卡片)
   - [M05 行为级 Red-Green](#m05-行为级-red-green)
   - [M06 测试场景完整性](#m06-测试场景完整性)
   - [M07 防 flaky 规则](#m07-防-flaky-规则)
   - [M08 新鲜证据门禁](#m08-新鲜证据门禁)
   - [M09 Skill 行为评测集](#m09-skill-行为评测集)
7. 第二轮设计决策
   - [M10 OpenAPI 条件门禁](#m10-openapi-条件门禁)
   - [M11 数据迁移门禁](#m11-数据迁移门禁)
   - [M12 动态泄漏门禁](#m12-动态泄漏门禁)
   - [M13 性能门禁](#m13-性能门禁)
   - [M14 UI/A11y 门禁](#m14-uia11y-门禁)
   - [M15 安全隐私门禁](#m15-安全隐私门禁)
   - [M16 Kotlin / Java Android 静态语义分析](#m16-kotlin-java-android-静态语义分析)
   - [M17 自适应分层自动化测试](#m17-自适应分层自动化测试)
   - [M18 需求增量与最终证据新鲜度](#m18-需求增量与最终证据新鲜度)
   - [M19 条件门禁快照与执行收据](#m19-条件门禁快照与执行收据)
   - [M20 Android CLI Agent Journey 默认路线](#m20-android-cli-agent-journey-默认路线)
   - [M21 编码后局部迭代与最终门禁分层](#m21-编码后局部迭代与最终门禁分层)
   - [M22 本机配置与当前需求运行输入隔离](#m22-本机配置与当前需求运行输入隔离)
   - [M23 串行需求独立工作区与延迟回收](#m23-串行需求独立工作区与延迟回收)
   - [M24 已上线业务影响前置与保护证据](#m24-已上线业务影响前置与保护证据)
   - [M25 首次确认草稿收敛](#m25-首次确认草稿收敛)
   - [M26 运行时上下文去重](#m26-运行时上下文去重)
   - [M27 Matt Pocock Skills 精华适配](#m27-matt-pocock-skills-精华适配)
   - [M28 五步用户入口与后台治理分离](#m28-五步用户入口与后台治理分离)
   - [M29 单一实施计划与确认收据](#m29-单一实施计划与确认收据)
   - [M30 Karpathy 编程降错准则适配](#m30-karpathy-编程降错准则适配)
   - [M31 人读产物体系与多需求维护](#m31-人读产物体系与多需求维护)
   - [M32 多需求并行（git worktree）与交付文档落地](#m32-多需求并行git-worktree与交付文档落地)
   - [M33 增量影响半径与越界 diff 门禁](#m33-增量影响半径与越界-diff-门禁)
   - [运行时规则唯一归属](#运行时规则唯一归属)
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
- 首次编码前保证需求和测试准备完整，编码后用局部快速反馈迭代，最终交付再做一次完整兜底。
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

- **来源**：[GitHub Spec Kit clarification](https://github.com/github/spec-kit/blob/main/templates/commands/clarify.md) 的结构化歧义扫描、互斥候选和增量写回，[Superpowers brainstorming](https://github.com/obra/superpowers/blob/main/skills/brainstorming/SKILL.md) 的单问题、优先选择题和推荐取舍，[OpenSpec editing changes](https://github.com/Fission-AI/OpenSpec/blob/main/docs/editing-changes.md) 的实时事实文件与用户/AI 双向编辑，[Cucumber Example Mapping](https://cucumber.io/docs/bdd/example-mapping/) 的规则、例子、问题与测试映射；高风险技术取舍参考 [MADR](https://github.com/adr/madr/blob/develop/template/adr-template.md) 的决策依据、候选与后果。
- **决策**：保留稳定 `REQ-###`、五类场景检查和最多 5 个高影响问题；按“影响程度 × 不确定程度”排序并一次只展示一个。能形成真实方案时提供 2～4 个互斥候选、直接影响和可选建议，始终允许补充、组合、修改或自行填写；最终只把合并后的业务语义写回 `requirement_file` 并同步 BDD/测试，不保存选项字母。
- **证据边界**：候选和建议必须来自当前需求、代码、测试、契约或已确认资料；通用最佳实践只能解释取舍，不能替用户决定产品规则。用户回答不完整、候选冲突或新项目事实推翻已选方案时继续澄清受影响范围，不静默选择。
- **原因**：需求遗漏往往发生在编码前；预选项降低用户表达成本，自定义入口避免把用户锁进 AI 方案，逐项写回防止聊天丢失，同时沿用现有需求修订和测试追溯关闭下游返工。
- **拒绝**：不引入完整 Spec Kit/OpenSpec 文件体系，不为普通问题新增 ADR、Schema、脚本或状态机，也不把每个小需求扩张成长时间方案会。

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
- **决策**：用代表性 Android 需求验证需求门禁、路由、测试选择、阻断和禁止声明，而不只测试 Python 函数；可由仓库产物直接证明的不变量用 `evals/runners/run_artifact_evals.py` 做本地确定性 Evals，当前有效约束用 contract + oracle 层做轻量索引，人工/多 Agent forward test 仍按场景文件评分。
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

- 相关候选按 GitHub Star 近似排序，但只采用与 Android/Kotlin/Java 静态语义、生命周期、并发或泄漏证据直接相关的能力。
- **来源**：Kotlin 编译器、kotlinx.coroutines 与 RxJava 的语言/异步契约，AndroidX 的 Lifecycle/Compose/Lint 实现，LeakCanary 的引用链模型；detekt、Error Prone、NullAway、SpotBugs、Infer、Semgrep、CodeQL、PMD、Checkstyle、P3C、SonarJava 和 Slack Lints 的规则、类型/字节码/数据流、SARIF 与规则测试实践；Gradle、MobSF 和 OWASP MASTG 的可重复执行及静态/动态证据边界。
- **决策**：不维护无限规则清单，统一用六条不变量审查：短生命周期不被长生命周期持有、注册/解绑成对、获取/释放成对、异步任务不超过宿主、清理路径可达、共享状态具有并发纪律。
- **语言边界**：Kotlin 优先、Java 一等支持；混合调用额外核对 Nullability/platform type、primitive/boxed、异常、泛型、SAM/Callback、取消传播和公开 API/ABI，不复制第二套流程。
- **执行**：`android-audit-stability` 建立资源所有权表和按需并发访问表、复核必要调用链并解释告警；`android-test-and-fix` 只发现和执行项目已有编译、Lint、语言专项、跨语言扫描、测试、release/R8 与 API/ABI 任务。
- **机器门禁**：稳定性专项 version 4 固定要求 `android-static-semantics`、六条不变量和静态控制面七项检查；`static_analysis` 记录语言、实际文件、工具模式/范围、绑定当前代码的控制面审计、全部候选处置和稳定问题编号，防止换模型后只写自然语言结论或漏掉候选。
- **报告与控制面**：项目已有工具能够输出 SARIF 时使用独立 `android-static-analysis` version 3 收据，直接解析报告 Error、`baselineState` 和稳定 `FND-...`；`new/updated/unknown` Error 阻断，明确 `unchanged` 的历史 Error 只记录不扩改。新增 suppress、baseline、exclude 或失败策略生成 `CTL-...` 并逐项说明，不因命令零退出或配置放宽造绿。
- **模型评测**：使用 Kotlin、Java、混合语言、安全反例、闭源证据不足和控制面放宽样例评估所有权、调用链、契约和结论边界；评测答案不进入日常 Skill 上下文。
- **历史债务**：告警区分 `NEW`、`AFFECTED`、`PRE_EXISTING`、`UNKNOWN_ORIGIN`；不更新 baseline 掩盖新增问题，也不借需求清理无关旧问题。
- **变异测试边界**：Kotlin 项目变异测试必须排除编译器自动注入的 `kotlin.jvm.internal.Intrinsics` 空检查变异。这些变异由编译器对参数非空约束生成，不属于业务逻辑，业务测试无法杀死，若不排除则正常交付永远 `survived > 0`，使 FULL_PASS 门禁形同虚设。排除只针对编译器插桩，不排除任何业务代码变异；Java 项目无此类注入，无需排除。
- **证据边界**：生成代码、反射、AIDL、JNI、闭源 SDK 或 release 行为无法确认时标未验证；静态零告警只能写“未发现明确静态问题”，不能宣称无泄漏、线程安全或实机通过。
- **原因**：项目配置变化只影响能力发现与证据，不要求修改路由脚本或强制迁移语言、AGP、Gradle、JDK 和测试框架。

### M17 自适应分层自动化测试

- **来源**：[Android 官方测试策略](https://developer.android.com/training/testing/fundamentals/strategies) 的单元、组件、功能、应用和候选版本分层，[Android 测试基础](https://developer.android.com/training/testing/fundamentals) 的可测试架构与解耦，[UIAutomator](https://developer.android.com/training/testing/other-components/ui-automator)、[Espresso](https://developer.android.com/training/testing/espresso) 和 [Compose UI Test](https://developer.android.com/develop/ui/compose/testing) 的能力边界；Maestro、Robolectric、Kaspresso、Paparazzi、Kotest 属性测试和 PIT Mutation Testing 作为补充对照。
- **决策**：把每个 BDD 的复合 Then 拆成 `BDD-001/T1` 形式的原子验证义务，按 `L1/L2/L3/BLOCKED` 做需求初判和最终 diff 终判，再为每项选择最低且足够的测试层。Journey 只做少量关键黑盒旅程，并根据原子 Then 分配用 `FULL/PARTIAL/NONE` 表达整条 BDD 的适用性；Journey 通过只覆盖它实际断言的 Then。
- **老项目边界**：低 AGP 项目继续使用自身 wrapper 构建 APK，当前 AI 会话优先使用 Android CLI/adb 对已安装 APK 执行 Journey；已经初始化的独立壳只作可选回退。项目已有 Compose/Espresso/UIAutomator 时复用，不升级目标项目。
- **工具边界**：不自动安装 Maestro、Appium、Kaspresso、属性测试或 Mutation 工具。只有场景仍适合黑盒 UI、Journey 引擎能力不足且项目已有或用户允许时才考虑 Maestro；业务上不适合 Journey 的场景不能通过换黑盒引擎解决。
- **原因**：成熟方案不是万能 E2E 兜底，而是大量快速确定的小测试加少量高保真流程。原子证据可以补齐 UI 与业务混合需求、Journey 部分覆盖和无设备降级，同时避免每个小改动机械执行完整测试矩阵。
- **拒绝**：不按代码行数判断风险，不把 Journey/截图/Unit/静态扫描越权写成整条业务通过，不把计划人工测试写成已覆盖，不建立跨需求持久化状态机。

### M18 需求增量与最终证据新鲜度

- **来源**：[Git diff](https://git-scm.com/docs/git-diff) 的 name-status、rename detection、patch 与工作树比较能力，[JSON Schema 2020-12](https://json-schema.org/draft/2020-12) 的可移植数据契约；结合本流程“串行需求、外部基线、最终代码新鲜证据”的目标。
- **决策**：`init` 只读需求，不触碰 Git 基线；`check-env` 在干净工作区同时保存 Git 起点与需求起点，重复执行只复用，只有用户明确的新串行需求使用 `--new-requirement` 更换起点。中途重读按最近确认修订和追溯表输出差异；独立修订清单逐项记录增改删、替代、确认/待定/拒绝/冲突及删除处置，只有全部解决才推进版本。路由消费 `A/M/D/R` 和实际 patch，最终 `delivery-result.json` 必须与当前有效 Then 集合精确一致，并绑定需求修订、基线与工作树摘要。
- **职责边界**：需求修订脚本只校验连续性和原子保存，不判断业务语义或修改 Git；Git 脚本不决定路由，最终门禁不运行测试或修代码。Journey 只使用已确认修订的用例作用域，并只声明实际覆盖的 Then。
- **原因**：提示词规则无法单独证明某个 Skill 已执行，也无法阻止测试后代码变化继续复用旧结果；最小结构化契约可以关闭假绿，同时保持脚本可替换和跨模型可读。
- **拒绝**：不新增通用 phase/state 状态机，不把待定/冲突或聊天内容自动合并进总需求，不把文本删除直接等同于删除公共代码，不用文件名代替真实 patch，不让最终门禁执行 Git 写操作、测试或发布。

### M19 条件门禁快照与执行收据

- **来源**：JSON Schema、Gradle/JUnit/Android Lint 原生报告；[Now in Android Build](https://github.com/android/nowinandroid/blob/main/.github/workflows/Build.yaml) 的分层 Build/Lint/Roborazzi/Instrumentation、[Lottie Validate](https://github.com/airbnb/lottie-android/blob/master/.github/workflows/validate.yml) 的 Lint/Unit/API/Snapshot 独立 Job，以及 [Detekt Danger](https://github.com/detekt/detekt/blob/main/bots/dangerfile.js) 的 diff 缺测试提示。
- **决策**：`route` 把四类条件门禁及直接依据保存到项目外快照，并绑定需求修订、已确认实施计划、UI/API 输入、Git 基线和代码摘要。Diff Reviewer 使用专项结果 version 4 逐项确认七类语义影响，最终门禁把它与脚本快照取并集。自动命令由独立执行器按单一 gate 保存不可覆盖 attempt、JUnit testcase、Lint/通用 SARIF 机器报告和脱敏日志；测试/迁移收据强制要求非零 JUnit，普通自动收据不能越权证明专项 gate。稳定性固定记录静态语义、泄漏/性能/安全适用性，Journey 按需扩展。最终结果契约保持 version 4。
- **职责边界**：路由快照只表达候选，不替代业务适用性终判；执行器只运行已经选定的命令，不选择 task、不修代码；最终门禁只校验，不运行命令。
- **原因**：自然语言约束不能阻止条件专项被漏写，也不能证明 AI 填写的退出码和报告路径真实存在；但强迫普通 Review 填写 Journey 字段也会制造维护成本。最小信封加原生报告在关闭假绿的同时避免建立通用状态机。

### M20 Android CLI Agent Journey 默认路线

- **来源**：Google Android CLI Skill 的 Journey action 顺序、失败和结构化汇总规则，以及 Android CLI `run/layout/screen` 的已安装 APK 操作能力。
- **决策**：Journey 适用时，由执行当前 Skill 的 AI 会话优先读取 XML，使用 Android CLI/adb 逐个 action 操作和验证；统一专项结果保存 Journey 数、action 数、命令及布局/截图摘要。AGP 9 Studio Labs 壳保留为已经初始化后的可选 JUnit 回退。
- **边界**：当前 Android CLI 没有可由 Python 调用的 `android journey` 或 `android agent` 子命令，不创建伪命令；没有 Agent 会话、设备或等价 UI 引擎时保持未验证。壳未初始化不再阻断默认路线，也不自动要求用户打开 Android Studio。

### M21 编码后局部迭代与最终门禁分层

- **来源**：[AndroidX Presubmits](https://github.com/androidx/androidx/blob/androidx-main/.github/workflows/presubmit.yml) 按变更文件处理格式并按项目拆分构建，[detekt Pre Merge](https://github.com/detekt/detekt/blob/main/.github/workflows/pre-merge.yaml) 在非主干启用预测式测试选择，[Now in Android Build](https://github.com/android/nowinandroid/blob/main/.github/workflows/Build.yaml) 在 PR 执行测试、构建、Lint 和设备任务并把 [Baseline Profile](https://github.com/android/nowinandroid/blob/main/.github/workflows/NightlyBaselineProfiles.yaml) 放入夜间任务，[LeakCanary Main](https://github.com/square/leakcanary/blob/main/.github/workflows/main.yml) 把普通构建与相关模块的多 API 设备测试拆分。
- **决策**：首次编码前继续完整确认需求、BDD、测试设计和 Git 基线；首次实现后的完善、修改、删除或修复只执行受影响测试和必要编译，验收语义变化时只修订受影响义务；用户当前或最初明确要求最终检查、完整交付或准备提交时，才基于最终代码执行一次完整 route、专项、构建、Lint 和交付报告。
- **证据边界**：局部结果只证明本轮受影响范围。最终结果生成后代码、测试、资源或构建配置变化会使其失效，但完善期间不要求每次立即重跑完整门禁；再次准备交付时统一生成最终新鲜证据。
- **拒绝**：不新增通用阶段状态机或外部预测测试服务；`confirm-plan` 只保存一次窄职责确认收据，不管理阶段。高成本设备矩阵和全部 Reviewer 不进入每次小改动，也不以“局部测试通过”冒充整体交付通过。

### M22 本机配置与当前需求运行输入隔离

- **问题**：`local.yaml`、当前需求正文、截图、接口证据和测试报告会随项目与需求持续变化；把它们作为 Skill 源码跟踪会让工作区长期变脏，并增加误提交业务资料、覆盖用户输入或把需求变化混入流程改动的风险。
- **决策**：仓库只版本化带详细中文注释、没有真实路径和业务资料的 `profiles/local.example.yaml`；真实 `profiles/local.yaml` 与项目外 `requirement_dir` 由 Git 忽略并归用户所有。放在 Android 项目 `document/` 下的需求目录是交付文档，随目标项目代码提交。已有本机文件不得被模板覆盖，取消 Git 跟踪不得删除物理文件，也不得用 `git add -f` 绕过边界。
- **证据边界**：不进入源码版本控制不等于不校验。脚本继续读取真实配置、需求文件和已确认实施计划，完整输入摘要绑定需求正文、计划与已登记 UI/API 资料；任何输入变化仍使旧路由、证据和最终报告失效。
- **拒绝**：不使用 `skip-worktree` 或 `assume-unchanged` 隐藏已跟踪文件，因为它们是本机隐式状态，换机器或换 AI 后难以复核；需要长期归档的需求由用户明确选择独立归档位置。

### M23 串行需求独立工作区与延迟回收

- **问题**：长期复用一个 `current-requirement` 会让上一需求的正文、截图、接口证据、测试用例和报告与下一需求混放；每次开始需求就清空目录又会在误判完成状态、需要追溯或回看失败证据时造成不可逆丢失。纯机器编号可以隔离，但用户无法快速识别内容。
- **来源**：[XDG Base Directory Specification](https://specifications.freedesktop.org/basedir/latest/) 区分持久状态与可再生成缓存；[Bazel Sandboxing](https://bazel.build/docs/sandboxing) 为动作建立隔离执行根，避免未声明的旧输入影响结果；[Gradle-managed Directories](https://docs.gradle.org/current/userguide/directory_layout.html#dir:gradle_user_home) 对缓存采用周期清理和不同保留期，而不是每次构建后全部删除。
- **决策**：采用这些原则而不照搬工具实现。每个新串行需求创建 `REQ-日期-序号-中文名称` 独立目录；JSON 保存稳定机器状态，`需求说明.md` 提供中文入口。只有用户明确结束/取消上一需求并开始下一需求时才轮换；默认先预览，确认后执行。上一需求和新需求不共享正文、UI/API 固定证据、测试用例、报告或 Git 基线。
- **回收边界**：已完成或取消的需求必须同时超出最近保留数量和最短保留天数才可回收；活动、未完成、近期、状态缺失或损坏的目录保留。可再生成的 `tempfile` 使用相同时间门槛，但仍只删除允许根目录的直接子项。轮换和回收不嵌入 `init`、测试或交付命令，避免隐式破坏。
- **职责边界**：`requirement_workspace.py` 只管理项目外目录和 `local.yaml` 的两个活动指针；它不理解需求、不修改 Android 源码、不执行测试、不提交或清理 Git。确认写操作使用单写锁和唯一暂存目录，失败回滚只处理本轮拥有的对象并恢复旧状态，避免多个窗口互相覆盖。轮换后仍必须按 `init → 用户确认 → check-env --new-requirement` 建立新需求事实和基线。
- **拒绝**：不按每次交付无条件删除 `current-requirement` 或整个 `tempfile`，不以同一目录加前缀模拟隔离，不让 AI 根据聊天内容猜测上一需求是否完成，也不把工作区目录纳入 Skill 源码提交。

### M24 已上线业务影响前置与保护证据

- **问题**：新需求可能明确修改旧规则，也可能只复用共享代码却意外波及其他已上线业务。只验证当前需求会遗漏回归；机械保护全部旧实现又会固化历史 Bug、扩大测试和阻止合理业务变化。
- **采用依据**：延续 M02 的需求追溯、M03 的语义影响路由、M05/M06 的行为级测试、M08 的新鲜证据和 M21 的三阶段反馈；不引入新的发布平台或第二套状态机。
- **决策**：最终需求确认前允许 AI 先只读核对项目身份和目标分支，再定向检查相关实现、调用方和已有测试，并把结果置顶分为“本次明确修改、必须保持不变、暂时无法确认、明确不修改范围”。前两类分别使用 `【修改已上线业务】`、`【保护已上线业务】` 原子 Then，强制作为必需项直接复用现有测试、追溯和最终证据门禁。最终 diff 新发现计划外影响时回到需求修订并复用原 Git 基线，不重复 `check-env`，也不允许只在报告补写。
- **证据边界**：只有有代码、测试、契约或用户确认支持的可观察行为才能成为保护义务；疑似旧 Bug 或业务含义不明时保持待确认。保护项必须绑定真实 testcase 或已经执行的完整人工证据，未验证或失败时不能完整通过。
- **报告边界**：中文 `delivery-summary.md` 从已经确认的义务文本中识别两个固定标记并置顶展示，不修改 `delivery-result.json`、需求快照或 Schema。详细实现、调用方和测试仍由追溯表承担，避免报告脚本理解 Android 业务。
- **拒绝**：不扫描并固化全仓库历史行为，不要求每个需求全量回归，不新增旧业务 Skill、配置或机器状态，也不把功能开关、影子运行和灰度设为普通本地需求的固定步骤。

### M25 首次确认草稿收敛

- **问题**：首次确认前用户可能连续新增、删除、纠正或一边说“确认”一边补充需求。只把变化留在聊天会导致换模型后丢失；为每轮草稿建立正式修订或新状态机又会增加无价值复杂度。
- **决策**：继续以 `requirement_file` 作为唯一完整需求事实。每轮变化先用中文分类，再合并并同步文件，重新执行 `init` 读取，只分析受影响范围，随后只展示本轮变化摘要、最新文件路径和待确认点，默认不在聊天重贴完整需求。只有不带新变化的明确确认才建立首次 Git 基线并形成 R1；确认后编码、测试、route 和最终报告必须重新读取已确认文件、修订清单和追溯表，不再沿用确认前聊天理解。
- **边界**：首次确认前的临时编号对未变化项保持稳定；撤回的草稿项不进入 R1，也不要求实现删除处置。R1 之后继续使用现有需求修订、删除处置和证据失效机制，不新增草稿事实源、配置或通用 Python 状态机。
- **拒绝**：不把“收到”“可以，但再加一项”当成最终确认，不允许聊天成为唯一事实来源，也不在每轮澄清时建立 Git 基线或正式修订号。

### M26 运行时上下文去重

- **问题**：共享规则、总入口和测试 Skill 重复抄写输入、工具、失败分类与降级模板，会增加上下文占用，并让后续修改容易只同步其中一份。
- **决策**：跨 Skill 不变量只保留在 `_shared/android-global-rules.md`；三阶段编排和需求修订只保留在总入口；测试选择与执行只保留在测试 Skill；详细条件能力继续按需读取 `references/`。Skill 的触发场景只写在 YAML `description`，正文不重复“定位/调用”说明；专项正文只补充检查、执行和输出，不复述共享规则。
- **边界**：面向用户的外部说明可以解释同一能力，但不得成为运行时规则来源。去重只删除重复说明，不改变命令、机器契约、门禁、状态或职责。
- **拒绝**：不为了缩短行数删除安全边界，也不把所有规则塞进单一巨型 Skill；没有重复证据时不做无目的重写。

### M27 Matt Pocock Skills 精华适配

- **调研对象**：2026-07-21 阅读 [mattpocock/skills](https://github.com/mattpocock/skills) 提交 `9603c1cc8118d08bc1b3bf34cf714f62178dea3b`，重点核对 `tdd`、`diagnosing-bugs`、`domain-modeling`、`to-tickets`、`code-review` 和 `writing-great-skills`。
- **判断**：其小 Skill 组合、单一事实源和渐进加载与本流程方向一致，但它是通用工程方法集，不具备本流程的 Android 路由、需求修订、旧业务保护、设备降级、证据新鲜度和机器门禁，不能替换现有 Harness。
- **采用**：测试必须落在调用方可观察的稳定业务边界，预期来自需求/契约/确定样例而不是重复生产算法，新增 Mock 优先停在不可控外部边界；全部义务先完成映射，实际编码按原子 Then 或不可分割 BDD 逐个完成 Red-Green 小闭环。
- **采用**：疑难、偶现、性能回退或首次修复未关闭的问题，在继续修改生产代码前建立能够捕获原始症状的最小反馈命令；无法可靠复现时请求真实环境或证据，不把假设冒充根因。明确编译、Lint 和单测失败仍走轻量直接闭环。
- **采用**：目标项目已有领域术语表、`CONTEXT.md`、`CONTEXT-MAP.md` 或 ADR 时按当前范围读取；缺失时不自动创建、不阻断，事实与业务决策冲突时才请求确认。
- **采用**：只有跨会话的大型需求，或者 `L3` 同时包含多条独立验收链路时，才在现有追溯表编排纵向切片和依赖；普通需求和单点高风险小改动保持原流程，不引入 Ticket 系统。
- **拒绝**：不复制其完整 Skill 套件、Issue/Wayfinder/Handoff 体系、每个需求逐题长时间访谈、定期主动重构或实现后自动提交；这些做法会增加认知和运行成本，或违背用户授权、最小修改及旧业务保护目标。
- **落点**：领域资料与疑难诊断只写共享规则，测试可信度只写测试 Skill，大型切片只写总入口；本文保存来源和取舍，评测场景防回归。不新增 Skill、脚本、Schema、状态、配置或运行时文档副本。

### M28 五步用户入口与后台治理分离

- **问题**：Git 基线、需求修订、追溯、路由、专项和机器证据都是可靠交付所需的内部治理，但直接把命令、Skill 名称和状态文件当成用户步骤，会让普通需求显得像大型发布工程。
- **采用依据**：延续 `spec-kit` 的单一需求事实与追溯、`superpowers` 的小步验证、Cucumber Example Mapping 的需求到测试映射、AndroidX/Now in Android 的局部反馈与最终门禁分层，以及 M21/M26 的三阶段反馈和运行时去重。
- **决策**：用户只看到“确认需求、拆分测试与确认计划、实现验证、变更后增量循环、最终交付”。AI 继续在后台执行原三阶段、Git 基线、需求修订、条件路由和证据门禁；只有用户明确询问，或解除故障、授权、阻塞确实需要时，才展开对应技术细节。
- **边界**：五步是呈现契约，不是新状态机、脚本协议或第二套事实源。业务语义变化仍更新受影响需求和测试，实现完善仍只做局部验证，最终完整门禁仍由用户交付意图触发。
- **拒绝**：不为简化界面删除安全门禁，不要求用户手动选择专项，不把所有局部修改升级为完整交付，也不新增五步专用配置或通用状态机；计划确认只补编码前缺失的事实门禁。

### M29 单一实施计划与确认收据

- **问题**：多轮需求虽已落到 `requirement_file`，但需求确认后直接编码时，用户看不到实现范围、旧业务影响、预计文件、测试和不修改边界；聊天中的计划也会随上下文丢失，需求或计划变化后无法机器阻止复用旧理解。
- **采用依据**：Spec Kit 的 spec/plan 分离和跨产物一致性、Superpowers 的编码前计划确认与小步执行，以及本流程 M01 单一事实、M02 追溯、M08 新鲜证据、M21 局部反馈和 M26 规则去重。
- **决策**：`requirement_file` 仍是唯一需求事实；每个接受答案先写回并重新读取。R1/R2 确认后只新增一份用户可读 `<requirement_dir>/实施计划.md`，固定展示五类边界；用户确认后由单一职责 `implementation_plan.py` 生成绑定需求修订、有效义务摘要、计划摘要和影响半径摘要的收据。`route` 与完整输入摘要复核收据，需求、计划或影响半径变化后旧 route、测试收据和专项证据失效。
- **增量边界**：验收语义变化只更新受影响需求、测试、同一计划和影响半径，再确认后继续局部迭代；没有改变五类计划内容和影响半径的实现完善不重复确认。聊天只给摘要与 Markdown 链接，机器收据不要求用户阅读。
- **拒绝**：不复制 Spec Kit 的 spec/plan/tasks/checklists 文件树，不把 `需求说明.md` 改成业务事实，不新增通用 phase 状态机，也不让脚本生成业务计划或替用户确认。

### M30 Karpathy 编程降错准则适配

- **调研对象**：2026-07-23 阅读 [multica-ai/andrej-karpathy-skills `CLAUDE.md`](https://github.com/multica-ai/andrej-karpathy-skills/blob/2c606141936f1eeef17fa3043a72095b4765b9c2/CLAUDE.md) 提交 `2c606141936f1eeef17fa3043a72095b4765b9c2`。
- **判断**：其“先想清楚、简单优先、外科手术式修改、目标驱动执行”与本流程的需求确认、最小修改、单一职责、TDD 和证据新鲜度一致，但原文是通用编码守则，不具备 Android 需求事实、实施计划、旧业务保护和最终门禁约束。
- **采用**：把用户确认的 AI 编程十二条强制约束固定为 `CODING-01` 到 `CODING-12`，并恢复“用户不需要重复提醒”、总入口、专项 Skill、独立调用、自修复和测试补齐等原有合理适用范围；同时把关键假设、可验证成功标准、多解释先确认、不要求用户指定技术实现、不增加未请求抽象/配置化、不处理不可能场景、不写死临时样例或未确认字段、每行改动可追溯、能简单则简化，压缩进 `_shared/android-global-rules.md` 的既有最小修改、单一职责和需求确认规则。
- **拒绝**：不新增 `CLAUDE.md`、不复制完整英文规则、不创建新 Skill 或第二套编程流程，也不让普通简单任务因为通用“谨慎”原则固定多一轮方案会。

### M31 人读产物体系与多需求维护

- **问题**：现有交付产物（requirement-revision/test-mapping/route-impact/receipt）全是 JSON，机器能校验但用户打开看不懂、无法自检"这步对不对"；半个月后接旧需求 AI 需重新翻聊天才懂原状；多需求并存后无法一眼全局；旧需求删除后证据全丢。对标 shareit/shell 的 `docs/` 产物体系后发现差距。
- **来源**：shareit/shell `docs/`（阶段目录 + 每产物人读 md + task 串联 + verify 脚本断言化）；[GitHub Spec Kit](https://github.com/github/spec-kit) 的 spec continuity 与稳定 ID；[XDG Base Directory](https://specifications.freedesktop.org/basedir/latest/) 与 [Gradle-managed Directories](https://docs.gradle.org/current/userguide/directory_layout.html) 的延迟回收（已落地为 M23）；[MADR](https://github.com/adr/madr) 的决策记录轻量化。
- **决策**：
  - md 是主产物（人读/自检/AI 执行依据），JSON 是门禁附件（SHA 链/变异测试/哈希校验全读 JSON 不动）。`render_artifacts.py` 从 JSON 渲染同名 md 影子：`续接指南.md`（每次 init、confirm-plan 和最终报告刷新，聚合需求快照/映射/计划收据/最终结论，是续做旧需求的第一入口）、`需求修订说明.md`、`测试映射说明.md`、`traceability.md`、`交付结论.md`（强制未验证项与残留风险独立段）。需求语义必须先写回 requirement_file，计划确认成功后同步相关人读 md；JSON 不能成为唯一追溯记录。
  - 阶段子目录 `plan/ review/ decisions/`（与既有 `test-cases/ test-results/` 不冲突）；协作待办、变更审查（Diff+Context 双表）、决策记录由 AI 手写并填 `android-implement-and-verify/templates/` 骨架（plan/review/test/result/decision/communications）。
  - 多需求维护：`requirement_workspace.py index` 渲染 workspace 级 `需求总览.md`；回收旧需求前 `archive_before_reclaim` 把关键人读 md 归档到 `archive/<requirement_id>/`，机器 JSON 随源清理不堆积；双门槛（keep_completed + retention_days）不变。
- **边界**：续接指南是从事实源渲染的状态快照，不是第二事实源（不变量 #25 不变）；md 与 JSON 一致性靠脚本渲染（零漂移），手写 md 由 SKILL 要求填模板；JSON 路径全部原位不迁移，零破坏在途需求。
- **拒绝**：不迁移 JSON 路径（破坏在途需求风险）；不新建 test/ result/ 子目录（与 test-cases/test-results 混淆）；不复制 Spec Kit/Matt Pocock 完整文件树或 Handoff 体系（M01/M27 已拒绝）；本轮不加并行冲突检测（目录已为多 requirement_dir 预留，用户明确后续补）；不做需求级度量或架构图（超范围）。
- **落点**：新增 `scripts/atomic_write.py`（公共原子写，渐进收敛 5+ 处重复）、`scripts/render_artifacts.py`；规则落 `_shared/android-global-rules.md`（产物体系一条）、`android-implement-and-verify/SKILL.md`（续接入口）；本文保存来源与取舍，评测场景防回归。

### M32 多需求并行（git worktree）与交付文档落地

- **问题**：单配置流程默认一个 `profiles/local.yaml` 对应一个活动需求；多需求共用同一配置/工作树/需求目录并行会互相污染（Git 基线、route 快照、证据覆盖、未提交代码阻塞）。
- **来源**：[git worktree 官方](https://git-scm.com/docs/git-worktree)、[Claude Code worktrees](https://code.claude.com/docs/en/worktrees)、[OpenAI Codex worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)；Spec Kit spec continuity（集成批次汇总）。
- **沙盒实测证据**：两 worktree 独立分支互不污染；A 脏工作树不阻塞 B（独立 worktree）；`config_paths` 以各自 `requirement_dir/.state` 隔离 baseline/snapshot/route/evidence/capabilities；同文件同行冲突 git merge 自然检出；改不同文件无冲突；`git worktree remove/prune` 可回收；同 config 并发第二写窗口被 O_EXCL 锁拒。
- **决策**：
  - 业界标准 = 纯 git worktree，零自研并行 wrapper 脚本。一个需求 = 一个 worktree + 独立分支 + 独立 profile + 独立 requirement_dir。
  - 文档落地：`requirement_dir = <project_path>/document/<日期-英文名>/`（文档跟 worktree 走），目录名英文 slug（kebab-case），中文名存 `需求说明.md` 首行 + workspace state 的 title，只在总览/集成报告显示。
  - 合并用 `git merge --no-ff`（线性主干 + merge commit 标记需求边界 + 提交 hash 保留，证据链不断）；不用 rebase（改写 hash 断证据链）、不用 cherry-pick（丢追溯链）。
  - `requirement_workspace.py` 新增 `integrate`（汇总各通道结论生成 `<主工作树>/document/integration-<批次>.md` + 各通道标 MERGED+批次号）、扩展 `index --main-worktree`（刷新全局 `<主工作树>/document/需求总览.md`，六列含分支和集成批次，分支自动从 workspace state 填）。
  - 不污染门禁：document/ 随 Android 项目代码提交；`git_changes.current_delivery_snapshot` 排除 document/（含 untracked 子文件，沙盒验证不污染也不误伤代码变化）。
- **对不变量 #18 / M22 的覆盖说明**：M22 原则"需求资料默认不进 Android 项目"。本决策由用户明确确认：文档放 project_path/document/ 时跟代码提交 + 摘要排除，保证可追溯且不污染代码门禁，覆盖旧默认。rotate 单配置通道仍可用项目外 requirements-runtime，不变。
- **拒绝**：不新增 parallel_channel.py 或任何自研并行 wrapper（业界无此实践）；不做冲突预检机器门禁（git 合入自然报冲突）；不用 rebase/cherry-pick 合并；不把 `document/` 加入目标项目 `.gitignore`。

### M33 增量影响半径与越界 diff 门禁

- **问题**：用户在编码中新增、修改或删除需求时，希望只处理受影响部分；仅靠中文计划和 AI 自觉容易发生两类失控：旧需求被整体重做，或最终 diff 悄悄越过已确认范围。
- **来源**：Spec Kit 的稳定需求 ID 和跨产物一致性、Cucumber Example Mapping 的需求到测试映射、AndroidX/LeakCanary/Detekt 等 CI 对变更文件选择受影响验证、M21 的局部反馈与最终兜底、M29 的计划确认收据。
- **决策**：新增机器可读 `<requirement_dir>/test-cases/impact-radius.json`。它绑定当前 `requirement_id`、修订号、需求正文 SHA 和有效义务摘要 SHA；当前需求基线以来的 ADDED/CHANGED/REMOVED/SUPERSEDED 义务必须逐项登记影响原因、风险、允许文件/目录前缀、预计测试和模块。`confirm-plan` 把影响半径 digest 写入计划收据，`route` 和最终门禁继续绑定该 digest；最终 diff 中任何代码文件不在已确认范围内时阻断完整通过。
- **匹配语义**：影响半径的允许范围只用两种确定性匹配，不允许通配符：`allowed_files` 精确路径命中，`allowed_dirs` 目录前缀匹配（必须 `/` 结尾）。无锚点通配符（如 `**/*.kt`）会放行整个仓库任意同类文件，使“防越界”门禁失效；强制 `/` 结尾则消除 `src` 误放行 `src_new` 这类兄弟目录的歧义。
- **增量边界**：影响半径是“允许触达范围”，不是 AI 自动扩大范围的许可证。语义变化时只更新受影响义务、测试映射、实施计划和影响半径并重新确认；语义不变的实现完善只能在已确认半径内做最小改动。确需扩大范围时，先把新增影响写回需求/计划/影响半径并重新确认；无关改动应移除。
- **拒绝**：不引入全仓精准依赖图服务、预测测试 SaaS 或复杂状态机；不因为增量而跳过最终兜底；不允许 AI 在最终报告中口头豁免越界 diff，也不把所有需求变化重跑成完整从头流程。

### 运行时规则唯一归属

| 规则范围 | 唯一运行时来源 |
| --- | --- |
| 跨 Skill 底线 | `_shared/android-global-rules.md` |
| 需求确认、用户可见五步、内部三阶段、Git 基线、需求修订和最终交付 | `android-implement-and-verify/SKILL.md` |
| 测试选择、Red-Green 小闭环和 Journey | `android-test-and-fix/SKILL.md` |
| 专项检查 | 对应专项目录的 `SKILL.md` |
| 使用说明、设计取舍和行为评测 | 现有说明、本文和评测文件；仅解释或验证，不作为第二运行时来源 |

维护时先修改唯一运行时来源，再同步必要导航、设计依据和测试；不得把完整执行规则复制到其他运行时文件。仓库级 `.agents/AGENTS.md` 只负责强制 AI 进入本项目维护规则，不保存第二套 Android 运行规则。

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
2. 需求确认前不修改代码；每个接受答案先收敛到 `requirement_file` 并重新读取。用户纯确认后完成 `check-env`、`confirm-requirement-update`、测试拆分和唯一实施计划展示；用户确认计划并执行 `confirm-plan` 后才编码，不增加其他冗长方案会。
3. 当前项目事实优先；允许依据已确认需求建立标记待对齐的业务模型和 UI，但不把它们冒充正式接口、传输字段、设计基准、架构事实或测试结果。
4. 当前需求 Git 基线隔离串行需求；工作区不干净时停止，不自动处理用户改动。
5. 最小修改和单一职责是全局默认，不需要用户重复提醒。
6. `android-verify-ui` 保持手动独立；Journey 测试归 `android-test-and-fix`，只覆盖 `FULL/PARTIAL` 中实际分配给它的关键用户旅程。
7. Git 提交和推送必须获得用户明确授权。
8. 没有新鲜执行证据时不能声明完成；没有动态证据时不能宣称无泄漏、无性能问题或实机通过。
9. 缺少真机不停止其他可执行门禁；只限制对应动态能力和完整交付结论。
10. 第二轮条件能力复用现有 Skill 和项目工具，不自动安装依赖或扩张为六个新 Skill。
11. Kotlin/Java/Android 静态审查以六条不变量、语言边界和必要调用链为核心；机器结果逐项记录静态检查、工具覆盖、控制面变化和稳定问题编号，工具零告警不能改写成无泄漏或线程安全。
12. 老项目历史债务与本次新增问题必须分离；不更新 baseline 造绿，也不扩大需求清理无关旧问题。
13. 每个已确认 BDD 的必需原子 Then 必须有新鲜自动证据、实际人工证据或明确阻塞；任一工具的通过不得覆盖它没有断言的风险。
14. `init` 永不删除需求 Git 基线，重复 `check-env` 永不覆盖当前起点；中途需求变化保留未变化 ID，最终通过必须绑定当前需求、基线和工作树摘要。
15. 新增 Kotlin/Java 核心代码必须落实职责分层、依赖方向、可测试构造和必要 KDoc/核心注释；代码质量专项不得用自然语言摘要省略这四项检查。
16. 首次编码前完整准备一次，编码后普通变化走局部迭代，最终 route 和完整门禁只在明确交付意图下执行；局部结果不得冒充整体通过。
17. 机器 JSON、Schema 和收据保持稳定英文协议；需求、变更、阶段提示、失败说明、测试结果和最终摘要等用户出口统一转换为自然中文，未知状态不得直接泄漏机器枚举。
18. 仓库只跟踪通用配置示例；真实 `local.yaml` 和当前需求工作区属于用户运行输入，默认由 Git 忽略但继续参与需求摘要与证据新鲜度校验，不得覆盖、删除或强制提交。
19. 新串行需求默认使用机器编号加中文名称的独立工作区；轮换与回收必须显式预览/确认，回收遵守状态、最近数量和最短时间边界，永不隐式清空活动或未完成资料。
20. 最终需求确认前只读、定向分析相关已有业务；明确修改和必须保护的旧行为进入同一原子义务与证据门禁，计划外影响必须重新确认，不能由 AI 静默处置。
21. 首次确认前每轮增删改都必须展示变化摘要、合并最新完整需求并同步文件；默认不在聊天重贴完整需求，带新变化的“确认”不能推进基线或 R1。
22. 共享不变量、总入口编排和专项细节各自只有一个运行时规则来源；其他文档只解释或导航，不复制第二套可执行规则。
23. 测试预期必须有独立事实来源，疑难问题先建立可靠复现；领域资料只在目标项目已存在时按需读取，纵向切片只服务大型需求，不能把这些增强扩张为普通小需求的固定仪式。
24. 用户只看到确认需求、拆分测试与确认计划、实现验证、变更后增量循环和最终交付五步；内部三阶段、Git 基线、追溯、路由、专项和机器证据保持不变，默认不向用户展开。
25. `requirement_file` 始终是唯一需求事实；`实施计划.md` 只说明如何实现，不得改写业务需求。需求、计划或影响半径变化后重新确认受影响计划和半径，旧 route 和证据不得复用。
26. 编码中需求增删改必须走增量影响半径：只处理受影响义务、测试和代码；最终 diff 超出已确认半径时阻断通过，不能由 AI 口头豁免。
27. 影响半径的允许范围只用精确路径和目录前缀两种确定性匹配，禁止通配符；无锚点通配（如 `**/*.kt`）放行整个仓库使门禁失效，目录前缀必须以 `/` 结尾避免兄弟目录歧义。
28. Kotlin 项目变异测试必须排除 `kotlin.jvm.internal.Intrinsics` 等编译器注入的变异，否则正常交付永远 `survived > 0` 使 FULL_PASS 门禁失效；排除只针对编译器插桩，不排除业务代码变异。

## 维护规则

- 每次修改 Skill、脚本、配置、Schema、路由、门禁或用户可见流程后，交付前主动核对并最小同步职责对应的运行时来源、设计依据和测试；不相关文档不改，说明文档只摘要或链接。
- 修改规则时先分离"本次新增目标"和"旧约束保护清单"：新增目标只允许最小增量落地，旧有需求确认、旧业务保护、新鲜证据、影响半径、职责归属、Git 授权、设备降级和维护验证等约束默认保留；除非用户明确要求废弃并同步运行时来源、设计依据和测试，否则不得为适配新增目标删弱旧约束。
- 本机首次维护本流程时先运行 `python3 scripts/install_maintenance_hook.py` 安装 pre-commit 自动验证；修改共享规则、任一 Skill、本文、流程契约、Oracle、路由、门禁或脚本行为后，必须从本仓库根目录运行 `python3 scripts/validate_maintenance.py`；该命令统一运行规则归属测试和 fast eval。这些维护门禁不接入 `delivery.py`，普通 Android 需求没有修改流程仓库时不运行。
- 修改跨 Skill 原则时，同步 `_shared/android-global-rules.md` 和本文对应决策。
- 修改完整流程时，同步 `android-implement-and-verify/SKILL.md`、导航文档和行为评测场景。
- 修改路由逻辑时，同步 `scripts/delivery.py`、`scripts/tests/test_delivery.py` 和相关场景预期。
- 修改测试门禁时，同步 `android-test-and-fix/SKILL.md`；不得只改说明不改执行证据要求。
- 修改已上线业务标记、确认顺序或中文摘要分组时，同步全局规则、总入口、Diff Review、测试 Skill、`delivery_gate.py`、单元测试和行为评测场景。
- 修改第二轮条件能力时，同步 `android-implement-and-verify/references/conditional-capability-gates.md`、主责 Skill、route 提示和对应行为评测场景。
- 修改 Kotlin/Java 生命周期、并发、语言边界或静态工具策略时，同步 `android-audit-stability/references/kotlin-java-static-analysis.md`、稳定性 Skill、测试执行 Skill、代码质量 Skill 和行为评测场景。
- 新增外部参考时记录项目、采用点、拒绝点和日期；不要因为 Star 高就复制其全部流程。
- 如果项目实践与本文冲突，以目标项目更严格的 `AGENTS.md` / `CONTRIBUTING.md` 和用户明确要求为准。
