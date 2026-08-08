# Android Delivery Skills 完整流程总览

<!-- android-delivery-flow:generated:start -->
## 自动同步的流程契约摘要

> 由 `ai-skills/android-delivery-skills/references/delivery-flow.yaml` 生成；契约摘要 `6349db7c7eec31a7ebd3c6dab61cd538f8d3dd3dd6d73cb466285e7b51271dd7`。

**用户流程**：确认需求 → 拆分测试与确认计划 → 实现验证 → 变更后增量循环 → 最终交付

| 阶段 | 主要命令 | 用户确认 |
| --- | --- | --- |
| 确认需求 | `delivery.py init / check-env / confirm-requirement-update` | 需要 |
| 拆分测试与确认计划 | `delivery.py confirm-plan / init-test-mapping` | 需要 |
| 实现验证 | `Red / 最小实现 / Green / 受影响验证` | 不需要 |
| 变更后增量循环 | `按变化类型回到需求、计划或局部验证` | 语义/范围变化时需要 |
| 最终交付 | `delivery.py route / delivery_gate.py assemble` | 用户明确触发 |

**失效与回退**

| 事件 | 保留 | 失效 | 回到 |
| --- | --- | --- | --- |
| 需求语义变化 | 当前需求初始 Git 基线；未受影响需求义务及其 CURRENT 测试映射 | 当前需求确认状态；旧计划收据；受影响测试映射并标记 STALE；旧 route、专项结果和最终证据 | `DRAFT_REQUIREMENT` |
| 实施计划或影响半径变化 | 已确认需求修订 | 旧计划收据；旧 route、专项结果和最终证据 | `REQUIREMENT_CONFIRMED` |
| Figma 只改变已确认范围内的视觉资料 | 已确认需求修订；影响半径未变化时的计划收据；未受影响 BDD 测试映射 | Figma XML 产物交接结果；UI 构建、截图和视觉验收证据；requirement_inputs_sha256 变化时绑定旧输入的专项和执行收据；旧 route 和最终结论 | `PLAN_CONFIRMED` |
| 已确认范围内的实现细节变化 | 已确认需求和计划；未受影响测试映射 | 受影响执行收据；旧 route、专项结果和最终结论 | `IMPLEMENTING` |
| Figma 新增状态、交互、文案语义或业务规则 | 当前需求初始 Git 基线；未受影响需求义务、代码和 CURRENT 测试映射 | 当前需求确认状态；旧计划收据；受影响测试映射并标记 STALE；旧 route、专项结果和最终证据 | `DRAFT_REQUIREMENT` |

<!-- android-delivery-flow:generated:end -->


> 本文件是当前流程的完整快照，覆盖流程阶段、命令、产物、防脑补机制和验证入口。
> 维护验证入口：`python3 scripts/validate_maintenance.py`；测试数量和结果以当次命令输出为准。
> 状态语义：`STALE` = 已失效、待重新回填；`CURRENT` = 已与当前需求义务和测试结果对齐。

## 目录

1. [仓库结构](#fo-repository)
2. [五步流程（用户看到的）](#fo-five-steps)
3. [内部命令链（AI 执行的）](#fo-command-chain)
4. [文档布局（按通道选择）](#fo-document-layout)
5. [核心防脑补与风险门禁](#fo-gates)
6. [增量闭环铁律](#fo-incremental)
7. [测试执行铁律](#fo-testing)
8. [Evals 自动护栏铁律](#fo-evals)
9. [版本号（已中文化）](#fo-versions)
10. [多需求并行](#fo-parallel)
11. [docx → md 事实源切换](#fo-docx)
12. [11 个交付模板](#fo-templates)
13. [压测验证](#fo-stress)
14. [业界对照](#fo-industry)
15. [机器状态隔离](#fo-state)
16. [关键脚本职责](#fo-scripts)

<a id="fo-repository"></a>
## 一、仓库结构

```text
android-delivery-skills/
├── 9 个 Skill 目录（2 个显式用户入口 + 7 个运行时 Skill）
│   ├── android-delivery-guide/         ← 只导航，不修改交付状态
│   ├── android-delivery-setup/         ← 项目发现与确认后初始化
│   ├── android-implement-and-verify/   ← 唯一完整交付总入口
│   │   ├── SKILL.md
│   │   ├── templates/                  ← 11 个交付模板
│   │   └── references/                 ← schema/eval/条件门禁
│   ├── android-review-diff/            ← diff 范围审查
│   ├── android-review-code-quality/    ← 代码质量审查
│   ├── android-audit-stability/        ← 稳定性（泄漏/并发/性能/安全）
│   ├── android-test-and-fix/           ← 测试 + 证据 + 自修复
│   ├── android-verify-api-contract/    ← 接口契约审查
│   └── android-verify-ui/              ← UI 独立验收
├── _shared/android-global-rules.md     ← 跨 Skill 共享规则
├── references/
│   ├── open-source-design-rationale.md ← M01-M34 设计决策依据
│   ├── skill-catalog.yaml              ← Skill 角色与显式/隐式调用策略
│   ├── delivery-flow.yaml              ← 五步、回退和失效声明式契约
│   └── 流程设计审查-<日期>.md           ← 流程问题记录（按需）
├── evals/                              ← artifact/contracts/behavior/transcript/command 评测
├── scripts/                            ← Python 编排、门禁、产物和维护脚本
└── profiles/                           ← 本机配置（local.yaml + local.example.yaml）
```

<a id="fo-five-steps"></a>
## 二、五步流程（用户看到的）

```text
① 确认需求
  → ② 拆分测试与确认计划
    → ③ 实现验证
      → ④ 变更后增量循环
        → ⑤ 最终交付
```

- **确认需求**：先综合已知资料并区分事实、决定、推导和假设；资料足够时不重复提问。每个已接受答案写回唯一需求文件，纯确认后进入计划准备。
- **拆分测试与确认计划**：把行为映射为测试，再用一份 Markdown 展示实现和范围边界；复杂需求才按可独立验证结果拆纵向步骤，小需求一行直通。`confirm-plan` 核对 BDD、预期文件和测试与影响半径的对应关系，确认后才编码。
- **实现验证**：按一个可观察行为完成 Red → 最小实现 → Green，只报告本轮实现和验证结果。
- **变更后增量循环**：需求增量→AI 全自动改代码+改测试+回填+增量回归（见第六节增量闭环铁律）。
- **最终交付**：只有用户明确要求时，才基于最终 diff 执行完整审查、回归、构建、Lint、条件专项和中文报告；自动化测试按 BDD、实际 diff 和影响类别选择。

<a id="fo-command-chain"></a>
## 三、内部命令链（AI 执行的）

```bash
# ① 确认需求
delivery.py init --config profiles/local.yaml
# 读需求；docx 自动转写为 docs/<需求名>.md 作事实源；刷新续接指南；打印流程位置

delivery.py check-env --config profiles/local.yaml
# 校验分支+物理 worktree claim+代码工作区干净（文档改动不阻断）；建 Git 基线 + 需求快照到 .state/

# 物化 requirement-revision.json（AI 按 schema 写增改删清单）
delivery.py confirm-requirement-update --config profiles/local.yaml
# 推进版本号（首次确认 → 增量修订）；标记 STALE（已失效，待重新回填）；刷新 docs/ 下的续接指南和追溯视图（映射说明存在时）

# ② 拆测试 + 确认计划
# AI 先写 docs/实施计划.md 和 test-cases/impact-radius.json，展示后等待用户确认
delivery.py confirm-plan --config profiles/local.yaml
# 生成计划确认收据（绑定需求+计划+影响半径 sha256），并交叉校验 BDD/文件/测试引用；未确认不得编码

delivery.py init-test-mapping --config profiles/local.yaml
# 生成测试映射骨架（STALE：已失效，待回填）；AI 填 test_ids 后回填 CURRENT（已对齐）
# --validate 和最终 gate 会检查 CURRENT test_ids 包含影响半径 expected_tests；允许额外测试

# ③ 实现验证（AI 编码：Red → 最小实现 → Green）
# ④ 增量循环（见第六节）

# ⑤ 最终交付（用户明确要求完整交付时）
delivery.py route --config profiles/local.yaml
# 基于真实 diff 和已确认影响取并集，生成 .state/route-impact.json 的专项任务清单；route 不直接调用 Skill
# 默认最多 3 个变化轮次；相同输入复用并标记 STABLE；人工确认后可用 --new-session 开启新会话

# 推荐：根据产物清单自动组装并立即校验
delivery_gate.py assemble --config profiles/local.yaml --manifest <产物清单.yaml>
# 特殊场景才手写 delivery-result.json 后执行 validate
delivery_gate.py validate --config profiles/local.yaml
# 最终交付门禁：用中文检查专项任务、义务集合、sha256、STALE（已失效状态）、证据、条件专项和追溯表
```

<a id="fo-document-layout"></a>
## 四、文档布局（按通道选择）

先根据当前 profile 的 `requirement_dir` 判断通道，不从目录示例反推实际路径：

- **项目内 worktree 通道**：`<project_path>/document/<日期-英文名>/`，文档随目标项目 Git 跟踪；`.state/` 单独忽略。
- **本机串行轮换通道**：`<workspace_root>/requirements-runtime/REQ-日期-序号-名称/`，由 `requirement_workspace.py next` 创建，不进入目标项目 Git。

两种通道使用相同的内部职责，只改变保存位置和 Git 生命周期。日常只需要关注四个人工入口：

```text
docs/
├── <需求名>.md       ← 唯一需求事实源
├── 实施计划.md       ← 已确认的实现边界
├── 续接指南.md       ← 当前状态、路径和下一步指针
└── 交付结论.md       ← 最终中文结论
```

其余 Markdown 是自动生成视图或按需记录；`test-cases/`、`test-results/` 和 `.state/` 是机器校验区，不要求用户日常逐个阅读。

完整内部结构如下，以项目内通道为例：

```text
<project_path>/document/<日期-英文名>/
├── requirement-workspace.json     ← 可移植工作区元数据；项目路径使用相对引用
├── docs/                         ← 人读 Markdown 入口
│   ├── <需求名>.md                  ← 唯一需求事实源（docx 自动转写，以后增量都在此）
│   ├── 需求状态.md                 ← 自动生成的工作区状态，不写业务需求
│   ├── 续接指南.md                 ← AI 续做第一眼（每次 init/confirm 自动刷新）
│   ├── 实施计划.md                 ← 用户确认后才能编码
│   ├── 测试结果.md                 ← 可选人读摘要（基于真实收据，不是机器事实源）
│   ├── 需求修订说明.md             ← 自动渲染（从需求快照）
│   ├── 测试映射说明.md             ← 自动渲染（从 test-mapping.json）
│   ├── 需求测试追溯.md             ← 自动渲染（需求→测试→证据）
│   ├── 交付结论.md                 ← 自动渲染（最终中文结论）
│   ├── 协作待办.md                 ← blocker/待确认/草稿消息（AI 手写）
│   ├── api.md                      ← 收到 API 资料时创建或更新：契约、来源、冲突与未知项
│   ├── design-note.md              ← 按需创建：UI 状态、交互和资源对照
│   ├── config-note.md              ← 按需创建：非密配置说明
│   ├── 审查-<主题>.md               ← 按需创建，Diff+Context 双表
│   ├── 决策-<主题>.md               ← 按需创建，MADR 轻量版
│   └── 问题-<主题>.md               ← 按需创建，现象/根因/处置/证据
├── api/                           ← 按需创建：接口原始资料、抓包或契约证据
├── ui/                            ← 按需创建：UI 截图、设计稿和视觉证据
├── config/                        ← 按需创建：机器可读的非密配置元数据
├── issues/                        ← 按需创建：问题附件或机器结构化记录
├── test-cases/
│   ├── test-mapping.json          ← 义务↔测试绑定（STALE：已失效待回填 / CURRENT：已对齐）
│   ├── requirement-revision.json  ← 修订清单（增改删+决策）
│   ├── implementation-plan-receipt.json ← 计划确认收据
│   ├── impact-radius.json          ← 允许文件/目录和受影响场景
│   └── journeys/                  ← 按需创建：Journey 测试用例，不放入共享壳源码
│       └── <需求作用域>/
│           └── <场景名>.xml
├── test-results/
│   └── delivery-result.json        ← 最终机器报告
└── .state/                        ← 运行时机器状态（不进 git，跟需求走）
    ├── baseline.json              ← Git 基线
    ├── requirement-snapshot.json  ← 需求快照（sha256 + 义务 + 版本）
    ├── route-impact.json          ← 路由快照（候选、输入摘要、轮次和收敛状态）
    ├── journey-runtime/           ← Journey 可选壳的需求级临时运行目录
    │   └── <scope-key>/
    │       ├── harness-app/        ← 共享壳的需求级可写副本
    │       ├── harness-app-build/  ← 壳构建输出、JUnit 和截图
    │       ├── project-cache/      ← Gradle 项目缓存
    │       └── reports/            ← 壳运行兜底报告
    └── evidence/                  ← 执行收据/日志/专项结果
```

新需求只固定创建需求输入、`docs/需求状态.md`、`test-cases/`、`test-results/` 和 `.state/`；首次 `init` 后才形成 Markdown 事实源及续接视图，实施计划和交付结论按阶段生成。接口、UI、配置、问题附件及其他人读记录全部按需创建，避免空目录污染。已有工作区的 `docs/需求说明.md` 继续原位刷新，不强制迁移，也不成为业务事实源。

Journey 运行目录规则：

1. 正式测试用例只来自 `<requirement_dir>/test-cases/journeys/<需求作用域>/`，不是共享壳目录，也不是任何全局缓存。
2. 选择可选 Journey 壳后，脚本把只读 `assets/journey-harness` 复制到 `<requirement_dir>/.state/journey-runtime/<scope-key>/`，后续任务发现、XML 暂存、构建和结果收集都只使用该副本。
3. 全局 `$XDG_CACHE_HOME/android-delivery-skills/gradle/`（默认 `~/.cache/android-delivery-skills/gradle/`）只共享 Gradle 依赖缓存，不保存 Journey XML、构建产物或需求报告。
4. `check-env` 或直接执行 Journey 时，若需求目录位于目标项目 worktree 内，流程自动把 `.state/` 登记到项目 Git 的 `<git-common-dir>/info/exclude`；`document/<日期-英文名>/.state/` 使用一条 `/document/*/.state/` 规则，其他布局使用当前需求的精确路径。该规则不修改项目 `.gitignore`、不制造代码 diff，只排除机器状态。

Android 测试代码落盘规则：

1. 单元测试正式落在目标项目的 `<project_path>/<module>/src/test/java/` 或 `<project_path>/<module>/src/test/kotlin/`；这里保存 JUnit、UseCase、ViewModel、Repository、mapper 和纯业务规则测试代码。
2. Android 插桩测试正式落在 `<project_path>/<module>/src/androidTest/java/` 或 `<project_path>/<module>/src/androidTest/kotlin/`；这里保存需要 Android 设备/模拟器、Instrumentation、Espresso、Compose UI Test 或 UIAutomator 的测试代码。
3. 变体专用目录 `<project_path>/<module>/src/<variant>Test/`、自定义 source set 或项目已有测试目录只有在项目实际使用时沿用，不为了统一目录迁移已有测试。
4. `test-cases/` 只保存需求映射、修订、影响半径和 Journey XML；它不替代 Android 项目中的 Unit/插桩测试代码。

<a id="fo-gates"></a>
## 五、核心防脑补与风险门禁

| 层 | 机制 | 强度 | 业界对照 |
|---|---|---|---|
| **SHA-256 哈希链** | 需求/计划/代码/证据全绑定，改了不重读就拦 | 机器强制 | 比业界更强 |
| **STALE（已失效待回填）联动** | 需求增量→义务 sha256 变→测试自动标记 STALE→gate 暂停放行 | 机器强制 | 自动化测试证据刷新 |
| **影响类别路由** | 脚本路径候选与 Diff Reviewer 的 `confirmed_impacts` 取并集，适用专项不能漏跑 | 机器快照 + 语义影响确认 | 影响驱动测试 |
| **route 有界收敛** | 记录七类候选和 `route_input_sha256`；相同输入复用，变化超过 `route.max_rounds` 阻断最终 gate | 机器强制 | 有界循环 + 幂等重试 |
| **Worktree claim** | 同一物理代码目录的多个活动需求在 `check-env` 阻断，不锁整个 Git 仓库 | 机器强制 | Git worktree 协作边界 |

### route 收敛规则

`route` 仍然是单次 CLI 调用；修复导致代码或候选变化时才重新执行。`.state/route-impact.json` 记录 `route_session`、`route_round`、`max_route_rounds`、`route_context_sha256`、`route_input_sha256`、`previous_route_input_sha256`、七类 `impact_candidates` 和 `convergence_status`。

- 首次 route 标记 `INITIAL`；输入变化进入下一轮 `CHANGED`。
- 需求、计划或影响半径上下文变化自动开启新会话；同一输入标记 `STABLE` 并复用候选和任务。
- 默认 `route.max_rounds: 3`；超过上限标记 `BLOCKED`，`route` 非零退出，最终 gate 拒绝继续。
- 原范围内确需继续时，人工确认后执行 `delivery.py route --new-session`；不能自动放大上限或跳过既有需求、计划、影响半径和专项门禁。

### 阶段四摘要

1. **进入阶段四**：阶段三所有场景已有真实结果后，执行 `delivery.py route`。
2. **route 校验与收敛**：校验需求、计划、影响半径和完整输入摘要；相同输入复用，输入变化按轮次推进，超过默认 3 轮标记 `BLOCKED`。
3. **影响复核与专项**：先执行 `android-review-diff`，再按 `specialist_tasks` 逐项执行专项；route 只登记任务，不直接调用 Skill。
4. **发现问题后的分流**：范围或需求问题进入增量闭环；代码或专项问题最小修复，改变 diff 后必须重新 route；只缺证据时局部补证和重验。
5. **最终验证与门禁**：完成必要回归并收集证据后，优先执行 `assemble --manifest`，不适用时手写结果再 `validate`。
6. **交付结果**：门禁根据实际证据输出 `FULL_PASS`、`LOCAL_PASS_DEVICE_PENDING`、`INCOMPLETE` 或 `BLOCKED`，最后由用户决定是否提交。

<a id="fo-incremental"></a>
## 六、增量闭环铁律（任何阶段需求变更都触发，AI 全自动）

**需求变更可能发生在任何阶段**（写需求时、拆 BDD 时、写计划时、编码时、写测试时、真机测试时、route 审查时、gate 校验时）。不管在哪一步发现，都先写回需求文档，再触发全自动闭环。

confirm-requirement-update 成功后，如果续接指南有 STALE（已失效待回填）或新增义务，AI 必须继续受影响闭环；但计划或影响半径变化时，必须重新展示并等待用户确认：

1. **更新计划边界**：同步 `docs/实施计划.md` 和 `test-cases/impact-radius.json`，登记场景变化、允许路径、受影响模块和测试；计划里的 BDD、预期文件和预期测试要与影响半径保持对应。
2. **重新确认计划**：需求、计划或影响半径变化会使旧计划收据失效；`confirm-plan` 成功前不得修改代码。
3. **重建测试映射**：执行 `init-test-mapping`，为 STALE（已失效）/新增场景登记真实测试 ID，先用业务断言确认 Red；回填 `CURRENT` 时必须包含对应 `expected_tests`，人工验收可保持空列表并填写原因。
4. **最小实现**：只改当前影响半径内的生产代码，使受影响场景 Green，不碰未变化场景和无关已交付逻辑。
5. **重构回归**：在 Green 保护下做必要重构，运行受影响测试和必要编译；旧测试失败必须修复。
6. **刷新证据**：刷新真实测试映射和执行收据；测试结果摘要按需基于这些证据回填，需求或代码变化后不得复用旧证据。
7. **报告完成**：说明修改文件、测试结果和剩余风险；未完成或受阻项必须如实标记。

需求语义仍有待确认、存在冲突或计划影响半径发生变化时必须等待用户；只有不改变已确认计划边界的实现细节完善，才可直接执行局部迭代。

<a id="fo-testing"></a>
## 六.A、测试执行铁律（编码后、route 前的必做环节）

编码完成后不能直接跳 route+gate。必须：

1. **建立测试清单**：执行 `init-test-mapping`，让每个 BDD 关联真实测试代码、Journey XML 或人工验收；测试步骤保存在可执行测试载体中，不复制到报告。计划的 `expected_tests` 是预期入口，真实覆盖仍以映射 `test_ids` 和执行收据为准；`CURRENT` 映射至少包含对应预期测试，允许额外测试，人工验收的预期测试留空并填 `manual_reason`。
2. **按需求和风险选择验证层**：执行 Unit、集成、构建、安装、Journey、截图、日志或人工验收中的适用项，不机械运行固定长链路。
3. **可选回填人读摘要**（`docs/测试结果.md`）：根据真实执行收据和报告记录实际命令、退出码、测试数、收据/报告路径和每个 BDD 的 `PASS/FAIL/UNVERIFIED`；普通自动化/人工业务验收绑定对应证据，UI 视觉验收先完成物理设备预检，再记录 `device_check`、Figma 链接、真机截图/差异图链接和动态区域说明。该摘要不是机器事实源，测试执行事实以执行收据、JUnit/XML/SARIF、Journey 结果和 `delivery-result.json` 为准。
4. **所有场景都有诚实结果**后才进入 route+gate；未执行不能写 PASS。
5. 测试中发现需求漏洞 → 触发增量闭环（见第六节），闭环后回到测试继续。

UI 视觉验收保持轻量：先用共享 `device_preflight.py` 检查 `adb devices -l`、设备状态和截图命令，再将真机截图与 Figma Frame 对比；固定内容严格比对，动态或系统区域按说明忽略/使用固定测试数据；不要求 APK、versionCode、安装收据或截图 SHA-256。只有物理设备预检为 `READY` 且截图成功时，UI 专项才可写 `PASS`。

<a id="fo-evals"></a>
## 六.B、Evals 自动护栏铁律（流程会变，AI 必须跟着最新约束走）

Evals 的核心不是“多写测试”，而是把流程要求变成机器可检查的约束。接入前，AI 主要靠提示词和上下文记忆执行流程；接入后，关键动作、测试证据、最终 gate 和流程维护提交都会被自动验证。

本流程已把维护验证统一收敛到（在 Skill 根目录执行）：

```bash
cd ai-skills/android-delivery-skills
python3 -m unittest discover -s scripts/tests -p 'test_*.py'
python3 -m unittest discover -s android-test-and-fix/scripts/tests -p 'test_*.py'
python3 scripts/validate_maintenance.py
python3 evals/runners/run_evals.py --suite fast
python3 evals/runners/run_artifact_evals.py
```

以上命令共同构成当前验证基线；测试数量和结果以当次命令输出为准，不在文档中固化。

开启 `Run Git hooks` 后，凡是提交涉及 Skill、references、evals、scripts、contract、oracle 或 gate 的流程维护改动，pre-commit 自动触发验证；失败直接阻止提交。

1. **流程约束机器化**：当前有效约束写入 `active-contracts.yaml`，流程变更优先改 contract，不让 eval 停留在旧流程。
2. **行为顺序可检查**：需求未持久化、需求未确认、计划未确认时，编码、route、最终交付都会被 behavior/transcript eval 抓住。
3. **需求变化定向失效**：用户中途新增、修改或删除需求后，当前确认、旧计划、旧 route 和旧最终证据失效；只有受影响测试映射进入 STALE，未受影响 CURRENT 映射继续保留。绑定旧完整输入的执行收据按新鲜度规则刷新。
4. **测试不能假绿**：0 测试、STALE（已失效）映射、未执行测试、旧测试结果，都不能算自动覆盖。
5. **证据必须新鲜**：最终结论必须绑定当前需求、当前输入和当前代码；需求或代码一变，旧证据立即失效。
6. **gate 不能漏**：接口、UI、稳定性、安全、性能等条件门禁按 route 候选和专项语义影响取并集，不能靠 AI 主观跳过。
7. **未验证不能写通过**：设备缺失、权限不足、环境失败、阻塞项只能标 UNVERIFIED/BLOCKED，不能包装成 FULL_PASS。
8. **维护失败不能提交**：pre-commit 自动运行 `validate_maintenance.py`；规则归属、artifact、contracts、behavior、transcript、command 任一失败都阻止提交。
9. **模型升级可回归**：换模型、改 Skill、改提示词后，用同一套 eval 回归验证 AI 是否仍按当前流程走。

一句话：Evals 把“希望 AI 遵守流程”变成“AI 不遵守流程就会被发现、被拦住”。

<a id="fo-versions"></a>
## 七、版本号（已中文化）

| 机器值（JSON） | 用户看到（终端/md） |
|---|---|
| 0 | 初始（尚未确认需求） |
| 1 | 首次确认 |
| 2 | 增量修订（第 1 次） |
| 3 | 增量修订（第 2 次） |
| N | 增量修订（第 N-1 次） |

<a id="fo-parallel"></a>
## 八、多需求并行

```text
一个需求 = 一个 git worktree + 独立分支 + 独立 profiles/<需求>.yaml + 独立 document/<日期-英文名>/
```

- 每个 `--config` 是一个交付通道；`check-env` 原子占用当前物理 worktree，同一目录被第二个需求复用时阻断，不锁整个 Git 仓库。
- 不同 worktree 即使属于同一 Git 仓库也允许并行；各窗口使用独立分支、profile 和 `requirement_dir`，代码、基线、测试与证据互不覆盖。
- `route` 复核当前 worktree、需求目录和分支仍属于原 claim；最终 gate 复核 route 快照、Git 基线和当前代码摘要，不要求合并后的主工作树额外创建集成 claim。
- 合并保持一条线：私有分支集成前只做一次 `git rebase`，主分支只用 `git merge --ff-only`；合入后的最终代码必须重新执行受影响门禁。
- 串行轮换、并行 `integrate` 或取消需求后释放通道；异常遗留通道可用 `requirement_workspace.py release --config <配置>` 显式释放。
- 同一需求补充直接走增量闭环；只有上一需求已经完成或取消、用户明确开始下一独立需求时，本机串行通道才用 `requirement_workspace.py next` 预览并确认轮换。项目内 worktree 通道为续接需求新建独立 `document/<日期-英文名>/`，两者随后都执行 `delivery.py init → 用户确认 → check-env --new-requirement`，不复用旧需求的 ID、BDD、测试和证据。
- 全局总览在主工作树 `document/需求总览.md`（六列：目录/中文标题/分支/状态/集成批次/最后修订）。

<a id="fo-docx"></a>
## 九、docx → md 事实源切换

- `requirement_file` 配 docx 时，init 自动按正文顺序转写为 `<requirement_dir>/docs/<需求名>.md`，保留标题、列表、表格和超链接；内嵌图片留下原文核对标记。
- 以后所有增量、修订、门禁都以 md 为准，docx 仅作初始记录保留。
- 图片型 docx（无文本正文）：用模板骨架建空 md，AI 在后续沟通中填充。
- 运行时只认当前需求目录 `docs/<需求名>.md`；`config_paths.py` 在配置仍指向 docx 时自动切换到该文件，旧根目录 md 不作为回退事实源。

<a id="fo-templates"></a>
## 十、11 个交付模板

| 模板 | 用途 |
|---|---|
| requirement.md | `docs/<需求名>.md` 需求事实源骨架（来源、规则、状态、BDD 和范围） |
| plan.md | 实施计划（小需求一行；复杂需求按可验证结果纵向拆分） |
| review.md | 变更审查（逐文件清单 + Diff + Context 双表） |
| test.md | 可选人读测试摘要模板（基于真实收据，不是机器事实源） |
| result.md | 交付结论（强制未验证项 + 残留风险段） |
| decision.md | 决策记录（MADR：Status 流转 + superseded） |
| communications.md | 协作待办（4 表：待确认/阻塞/已发送/低风险） |
| api.md | `docs/api.md` API 契约记录（来源 + 请求/响应 + 冲突 + 未知项） |
| issue.md | 问题台账（现象/根因/处置/证据） |
| config-note.md | 配置说明（key 名/环境/owner/安全边界） |
| design-note.md | `docs/design-note.md` 设计说明（页面状态/交互/资源对照） |

<a id="fo-stress"></a>
## 十一、压测验证

| 轮次 | 方式 | 发现 | 结果 |
|---|---|---|---|
| **当前自动化验证** | **全量单测 + Journey + fast eval + maintenance validation** | **全量链路回归** | **以当次命令输出为准** |
| 单需求端到端 | 手动 8 场景 | 5 个 bug（hash 漂移/跨项目残留/docx 增量/document 脏/docx 全链路断裂） | 全修 |
| 5 窗口并行 | 5 个无上下文 agent | 10 个问题（route 崩溃/破坏性重写/正则不一致/硬编码/gitignore/校验顺序/错误聚合/噪音/traceability/STALE 文案） | 全修 |
| **10 窗口并行** | **10 个无上下文 agent** | **0 个新 bug** | **10/10 全通过** |

当前自动化评测覆盖核心防脑补机制（STALE 联动、gate 拦截、sha256 绑定、计划收据失效、证据新鲜度和用户确认顺序）；结果以维护验证命令的当次输出为准。

<a id="fo-industry"></a>
## 十二、业界对照（10 维度）

| 能力 | 业界最强 | 本流程 | 排名 |
|---|---|---|---|
| 需求唯一事实源 + 增量修订 | Spec Kit（单向写回） | SHA 双向校验 | 更强 |
| 防测试不更新 | 多数项目依赖 CI 约定 | STALE（已失效待回填）映射 + 最终证据绑定 | 业界顶尖 |
| 防假断言 | 测试断言与代码评审 | Red/Green 业务断言 + 测试映射 + 执行收据 | 业界实践 |
| 防脑补（最终） | Spec Kit coverage | obligation_sha256 强等 | 更强 |
| plan 唯一 + 确认收据 | Spec Kit spec/plan 分离 | 固定文件名 + 三重 sha | 持平 |
| 续接旧需求 | Spec Kit spec continuity | 续接指南 + 波及清单 | 持平 |
| plan 自动进入 | codex 状态驱动 | 流程位置指示器 + 命令驱动 | 持平 |
| 多需求维护 | XDG/Gradle 回收 | 总览 + 归档 + 独立目录 | 持平 |
| 人读产物 | shareit docs | `docs/` 人读目录 + JSON 自动渲染视图 | 持平 |
| 交互轻量度 | Spec Kit constitution 几十行 | description 浓缩铁律 + 共享规则与 Skill 分工 | 持平 |

<a id="fo-state"></a>
## 十三、机器状态隔离

- 状态文件在 `<requirement_dir>/.state/`（跟需求走，不写全局 `~/.local/state/`）。
- 需求目录在项目 worktree 内时，`check-env`/Journey 自动写入项目 Git 的本地 `info/exclude`；只忽略 `.state/` 机器状态，不忽略 `document/`、`docs/`、`test-cases/` 或 `test-results/`。
- 换需求即换目录，物理隔离，无跨需求残留。
- 活动通道 claim 按规范化物理 worktree 存在 Git common dir 的私有锁目录，不写入工作树，也不锁整个仓库。
- document/ git 跟踪可 commit；check-env 只检查代码工作区，文档改动不阻断。
- delivery_gate 代码摘要排除 document/，文档变化不污染 snapshot_sha256。

<a id="fo-scripts"></a>
## 十四、关键脚本职责

| 脚本 | 职责 |
|---|---|
| delivery.py | 总编排器（init/check-env/confirm-*/route/init-test-mapping） |
| delivery_gate.py | 最终门禁校验（义务/sha256/STALE/证据/条件专项/需求测试追溯） |
| channel_guard.py | 物理 worktree claim、身份复核和释放 |
| config_paths.py | 路径解析 + docx→md 自动切换 + requirement_dir 派生 |
| requirement_snapshot.py | 需求快照（sha256 + 义务 + 版本 + 修订历史） |
| implementation_plan.py | 计划校验（6 类必需边界）+ 收据生成（需求/计划/影响半径摘要绑定） |
| test_mapping.py | 测试映射（STALE 已失效联动 + CURRENT 已对齐校验 + 保留未变化登记） |
| route_impact.py | 路由快照（8 字段绑定需求/计划/代码） |
| execution_evidence.py | 执行收据（单 gate 不可覆盖） |
| specialist_result.py | 专项结果校验（P0-P3 + 自动化测试证据 + capability） |
| assemble_result.py | 从产物清单组装最终 `delivery-result.json`，并立即执行 validate |
| render_artifacts.py | JSON→md 渲染（续接指南/修订说明/映射说明/集成报告/波及清单） |
| validate_maintenance.py | 流程维护提交前运行 catalog、规则归属、FLOW 同步和 fast eval |
| validate_skill_catalog.py | 校验九个 Skill 的角色、frontmatter、调用策略和共享规则归属 |
| render_flow_docs.py | 从结构化流程契约同步两份 FLOW 文档的自动区块 |
| figma_xml_handoff.py | Figma provider 调用前快照及 XML/资源交接范围、新鲜度和完整差异校验 |
| atomic_write.py | 公共原子写（0600 权限，收敛 5+ 处重复） |
| requirement_workspace.py | 工作区轮换 + 回收 + index 总览 + integrate 集成报告 |
| user_facing_labels.py | 机器枚举→中文（含 revision_label 版本号中文化） |
| git_changes.py | Git 只读收集（分支/基线/diff/patch/snapshot） |
