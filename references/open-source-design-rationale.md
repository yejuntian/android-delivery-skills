# Android Delivery Skills 开源设计依据

本文记录本套流程为什么这样设计、参考了哪些高 Star 开源项目、吸收了什么以及明确拒绝照搬什么。维护或重构 Skill 时先读本文；日常执行需求时不必全文加载。

## 目录

1. [设计目标](#设计目标)
2. [参考项目](#参考项目)
3. [第一轮设计决策](#第一轮设计决策)
4. [明确不照搬](#明确不照搬)
5. [长期不变量](#长期不变量)
6. [维护规则](#维护规则)

## 设计目标

本流程面向新旧 Android 项目的串行需求交付，核心目标是：

- 先确认需求，再修改代码；不从代码或工具结果反推产品需求。
- 把需求、BDD、实现、测试和执行证据连成可追溯闭环，减少遗漏。
- 遵守目标项目既有架构，保持高内聚、低耦合和最小修改，不强推技术迁移。
- 用真实命令、日志、报告和设备结果支撑结论；未验证项不得写成通过。
- 失败时先找根因，再做单变量最小修复；不得用删测试、弱化断言或重复碰运气造绿。
- 不承诺数学意义上的“零 Bug”，而是保证缺少必需证据时阻断完成声明。

## 参考项目

Star 数是 2026-07-18 的调研快照，只用于说明社区采用度，不作为设计正确性的唯一依据。

| 项目 | 调研时 Star | 吸收的做法 | 不照搬的做法 |
| --- | ---: | --- | --- |
| [obra/superpowers](https://github.com/obra/superpowers) | 256,904 | 需求澄清、根因调查、行为级 Red-Green、完成前新鲜证据、独立复审 | 每个小改动都写完整设计、强制多智能体、频繁自动提交、删除已有实现后重写 |
| [github/spec-kit](https://github.com/github/spec-kit) | 122,063 | 稳定需求 ID、场景与边界覆盖、最多询问高影响问题、跨产物覆盖分析 | 为每个需求复制完整 spec/plan/tasks/checklists 体系和复杂状态管理 |
| [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | 81,177 | 工作区与权限边界、自动化和人工授权分离 | 常驻 Agent 平台、多后端服务和超出本仓库目标的运行时 |
| [Aider-AI/aider](https://github.com/Aider-AI/aider) | 47,492 | 编辑后立即 lint/test、把真实失败输出交给 AI、分析与编辑职责分离 | 自动提交、自动提交用户脏改动、默认绕过 commit hook |
| [android/architecture-samples](https://github.com/android/architecture-samples) | 45,758 | 清晰层边界、Repository/DataSource、Unit/Integration/E2E 分层、fake 与生产隔离 | 把示例架构当成所有旧项目的模板 |
| [square/leakcanary](https://github.com/square/leakcanary) | 29,949 | 动态 Leak Trace、生命周期前后泄漏断言、CI 阻断新泄漏 | 无条件给所有项目新增依赖，或把工具输出直接当根因 |
| [OpenAPITools/openapi-generator](https://github.com/OpenAPITools/openapi-generator) | 26,563 | 机器可读契约、schema 校验、Kotlin 模型与客户端一致性 | 直接覆盖旧项目手写网络层或信任未经审查的生成输入 |
| [android/compose-samples](https://github.com/android/compose-samples) | 23,314 | UI 状态、主题、输入、导航、UI 测试和自适应设备形态 | 无条件迁移 Compose |
| [android/nowinandroid](https://github.com/android/nowinandroid) | 21,538 | 单向数据流、模块依赖图、测试公共能力、截图测试、Benchmark、变更文件覆盖和 CI 证据 | 照抄模块数量、Convention Plugin 或固定覆盖率阈值 |
| [mobile-dev-inc/Maestro](https://github.com/mobile-dev-inc/Maestro) | 14,950 | 可读 E2E Flow、条件等待、结构化 JUnit/HTML 报告 | 默认替换 Journey 或强制老项目安装另一套 UI 测试体系 |

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
- **决策**：路由除 UI/API 文件名外，还识别数据、系统、构建、架构和测试候选，并对可读改动文件做轻量内容信号检查。
- **原因**：`Client.kt`、DI Module、Manifest、Proto 或 Gradle 改动不能只靠文件名后缀判断。
- **边界**：脚本只输出候选证据，最终业务语义仍由 AI 结合需求和真实 diff 复核。

### M04 架构边界卡片

- **来源**：Superpowers 的 design for isolation、Android Architecture Samples 和 Now in Android 模块化实践。
- **决策**：最小修改预览必须说明组件职责、输入输出、依赖方向、复用点和明确不修改范围。
- **原因**：高内聚低耦合必须落实为可审查边界，不能只写成口号。
- **边界**：始终服从现有项目架构，不强制 MVVM、MVI、Clean、Compose、Hilt 或拆模块。

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
6. `android-verify-ui` 保持手动独立；Journey 测试归 `android-test-and-fix` 且只在适用时运行。
7. Git 提交和推送必须获得用户明确授权。
8. 没有新鲜执行证据时不能声明完成；没有动态证据时不能宣称无泄漏、无性能问题或实机通过。

## 维护规则

- 修改跨 Skill 原则时，同步 `_shared/android-global-rules.md` 和本文对应决策。
- 修改完整流程时，同步 `android-implement-and-verify/SKILL.md`、导航文档和行为评测场景。
- 修改路由逻辑时，同步 `scripts/delivery.py`、`scripts/tests/test_delivery.py` 和相关场景预期。
- 修改测试门禁时，同步 `android-test-and-fix/SKILL.md`；不得只改说明不改执行证据要求。
- 新增外部参考时记录项目、采用点、拒绝点和日期；不要因为 Star 高就复制其全部流程。
- 如果项目实践与本文冲突，以目标项目更严格的 `AGENTS.md` / `CONTRIBUTING.md` 和用户明确要求为准。
