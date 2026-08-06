---
name: android-test-and-fix
description: Android 测试驱动交付与自修复闭环。将已确认 BDD 物化为 Unit、参数化、迁移、A11y、仪器、截图或 Journey 测试。编码后的完善/修改/删除/修复用局部迭代模式，只跑受影响测试和必要编译；最终交付时按最终 diff 执行构建、Lint 和条件能力。失败时定位根因、最小修复并重跑；用户明确只测或只报告时不修改生产代码。
---

# Android 测试与失败自修复

## 共享规则

执行前必须遵守 `../_shared/android-global-rules.md`。由总入口调用时按其阶段执行并获得范围内最小自修复授权；用户明确要求“仅测试/仅报告”时不得修改生产代码。

## 职责边界

- 负责 BDD 测试物化、受影响测试、必要编译、完整交付 build/lint、失败根因、最小修复和重验。
- 不替代需求确认、正式接口契约、设计稿判断、独立 UI 验收或发布上线。
- 只报告模式保留失败和证据，不因 Skill 名称中的 `fix` 擅自改代码。

## 工作模式

- **局部迭代**：验收语义不变的完善、删除或修复，只跑本轮受影响测试；生产代码变化追加最小编译，删除代码检查调用方。结果只证明本轮范围。
- **完整交付**：用户明确要求最终检查、完整交付或准备提交时，按最终 diff、映射和影响类别执行全部必需测试、build、lint 和条件能力。
- 模式由总入口选择，不让用户记参数。任何代码、测试、资源或构建配置变化都会使旧最终证据失效，但不自动触发每轮完整交付。

## 按需读取

- UI 与业务混合、测试层选择或证据缺口：`references/adaptive-test-routing.md`。
- Kotlin/Java 静态门禁、历史债务、release/R8 和版本兼容：`references/project-static-and-compatibility.md`。
- Journey 适用性、BDD 物化和执行：`references/journey-testing.md`；可选壳故障再读 `assets/journey-harness/JOURNEY_USAGE.md`。
- Gradle task 确实无法从项目资料判断且当前门禁必须确认能力：`references/gradle-task-discovery.md`。

普通单元测试不要求预先配置固定命令；先根据已确认计划、真实测试结构和项目资料直接选择最小验证命令。

## 闭环执行

1. 从已确认需求和 CURRENT/STALE 映射建立 `BDD → 测试 ID → 可观察边界 → 断言 → 命令`；有待确认或冲突时不生成通过证据。
2. 读取项目已有测试目录、依赖、基类、fixture、命名、CI 和任务，沿用项目范式。
3. Bug 或行为变化先通过业务断言观察 Red；环境失败、编译失败和零测试不算 Red。
4. 只在网络、数据库、时间、文件、系统或第三方等不可控边界新增替身；优先断言公开输出、UI State、Repository 结果、迁移结果或系统行为。
5. 预期来自已确认需求、正式契约、固定样例或项目事实，不复制生产算法计算答案，不用内部调用次数代替业务结果。
6. 逐个 BDD 完成 `Red → 最小实现 → Green → 必要重构`，再运行受影响回归。
7. 失败时保留原始命令、退出码和首个根因，只修对应生产代码、测试或环境；连续三轮同一根因不能关闭才 `BLOCKED`。
8. 局部模式转绿后输出本轮结果；完整模式在最后一次修复后重跑全部必需命令并刷新证据。

禁止删除测试、注释或弱化断言、扩大容差、无依据 sleep、`@Ignore`、排除任务或把失败改成人工项造绿。无法先 Red 时记录原因、替代证据和剩余风险。

## 已上线业务保护

- `【修改已上线业务】` 测试证明用户确认的新行为，保留修改前后语义；只有与新预期冲突的旧断言可以更新。
- `【保护已上线业务】` 优先复用已有回归测试；缺少时只补本次可能波及的最小行为测试，不锁私有实现。
- 旧测试失败但不属于确认变化时修生产代码。最终 diff 发现未登记调用方时返回总入口更新需求，不直接补测试适配当前实现。

## 场景与防 flaky

- 对每个 BDD 检查主流程、异常、恢复和适用的非功能约束；资料不足回写待确认。
- 禁止固定 sleep 掩盖时序；使用框架等待、条件轮询、虚拟时间或项目已有同步机制。
- 重试只处理已证明的环境不稳定，每次保留独立 attempt。必需测试靠重试才通过时标记 `FLAKY`，不能计为稳定全绿。

## 新鲜证据

- 局部模式保存过程命令和结果；完整交付证据必须来自最后一次生产代码、测试、资源或构建配置变化之后。
- 最终命令用 `execution_evidence.py --gate <gate-id>` 生成单一用途收据；测试/迁移没有本轮执行数大于零的报告和具体 testcase 时不能覆盖 BDD。
- `CURRENT` test mapping 至少包含影响半径的 `expected_tests`，允许额外真实测试；人工验收使用空 expected_tests 和明确原因。
- 替代验证必须覆盖同一 BDD、运行条件和证据边界；能力损失保持未验证。

## 测试选择

- 业务逻辑优先 Unit、参数化、相邻回归和最小构建。
- UI 行为使用 Compose UI Test、Espresso、UIAutomator 或 Journey；视觉还原由 `android-verify-ui` 独立验收。
- 数据迁移优先真实旧 schema、旧数据和 Migration 测试；禁止清数据、卸载或 destructive migration 造绿。
- A11y 自动测试覆盖语义、装饰排除、触摸区域、焦点、状态描述、字体缩放和非纯颜色表达；TalkBack 与真机体验不能由静态检查替代。
- 泄漏、性能和安全命令只在稳定性专项判定适用后执行项目已有能力，不自动安装工具。
- 没有设备只跳过真正依赖设备的项，继续 Unit、build、lint、静态和其他本地门禁。

## Journey UI 测试

Journey 是已安装 APK 的关键用户旅程冒烟测试，不是全部业务测试入口：

- 由本 Skill 根据已确认 BDD、实际 diff、前置和预期自动判断 `FULL/PARTIAL/NONE`，不要求用户提供 XML、action 或 Gradle task。
- 采用“两次判断、一次执行”：需求确认后只初判候选，编码后按真实 diff 终判，只有仍分配了 Journey 义务才物化和执行。
- Given 转成可复现前置，When 拆成 action，Then 拆成独立 check；Journey PASS 只覆盖实际断言部分。
- 正式 XML 放 `<requirement_dir>/test-cases/journeys/<作用域>/`；共享壳只读，可选壳复制到需求级 `.state/journey-runtime/` 后运行。
- 默认在当前 AI 会话通过目标项目 Gradle、adb、截图、输入和日志执行；不存在可由 Python 虚构的 `android journey` 命令。
- `NO_JOURNEY_FOUND` 只表示已分配义务但物化失败；无 UI 或纯视觉分别使用 `SKIPPED_NO_UI`、`SKIPPED_VISUAL_ONLY`。
- 设备只能完成部分步骤时保留 `PARTIAL + ENVIRONMENT_FAILED`，不得用中断前截图冒充通过。

详细前置、CLI Agent、可选壳、零测试保护、状态码和降级规则必须按需读取 `references/journey-testing.md`。

## 完整交付门禁

- 必需 BDD 全部进入 `test-mapping.json`，状态为 CURRENT，并由真实自动 testcase 或已执行人工证据覆盖；STALE 直接阻断。
- 受影响测试、相关模块测试、build 和 lint 在最终代码上通过；Lint 必须读取报告中的 Fatal/Error，不能只信退出码。
- 适用的迁移、A11y、release/R8、版本兼容、泄漏、性能和安全能力有新鲜证据或诚实未验证状态。
- 失败数、未关闭 P0/P1 测试缺口和必需 FLAKY 均为零，才可支持整体通过。

## 禁止事项与输出

不得伪造结果、忽略失败、擅自引入重型依赖或运行未经授权的清数据、Monkey、真实支付/删除等破坏性测试。

局部输出只包含本轮修改、受影响测试/编译、命令结果、自修复、未验证项和风险。完整输出增加 BDD 追溯、静态门禁、历史债务、release/版本兼容、条件能力、TDD、flaky、降级记录和最终门禁结论；具体测试步骤留在测试代码或 Journey XML，不复制进报告。
