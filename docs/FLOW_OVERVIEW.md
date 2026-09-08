# Android Delivery Skills 当前流程总览

> 本文用于新窗口快速恢复流程，不是额外门禁或需求事实源。规则冲突时以当前项目 `AGENTS.md`、对应 Skill 和已确认 `spec.md` 为准。
> 图形版见 [FLOW_DIAGRAMS.md](FLOW_DIAGRAMS.md)。

## 目录

0. [陌生项目首次接手](#flow-onboarding)
1. [新窗口从这里开始](#flow-resume)
2. [当前组成](#flow-components)
3. [文档与文件布局](#flow-layout)
4. [完整流程](#flow-main)
   1. [先查事实](#flow-facts)
   2. [集中澄清](#flow-clarify)
   3. [一次确认规格](#flow-spec)
   4. [纵向实现与紧反馈](#flow-implement)
   5. [测试与 AI Journey](#flow-testing)
   6. [增量闭环](#flow-incremental)
5. [Figma 与 API](#flow-inputs)
   1. [Figma](#flow-figma)
   2. [API](#flow-api)
6. [最终交付与专项](#flow-final)
7. [多需求并行与大需求](#flow-parallel)
8. [授权和安全边界](#flow-safety)

<a id="flow-onboarding"></a>
## 陌生项目首次接手

仅当用户明确表示首次接手、完全不了解或要求摸底现有 Android 项目时，先使用 `android-onboard-existing-project`：读取项目规则、Git、Gradle、模块、CI、测试和代表性链路，建立有证据的项目地图、验证基线、风险与未知项。默认不改生产代码、构建配置或依赖，也不创建需求 profile、日期需求目录、`spec.md`、BDD 或需求基线。

项目事实需要跨需求复用或用户要求写入项目文档时，默认只创建 `<project_path>/document/project-context/overview.md`；内容确实独立后才按需拆分同目录文档，不预建空文件。接手完成后，具体需求再进入现有 `android-implement-and-verify` 交付流程，并以需求实际开始点记录 `baseline_commit`。普通新窗口、普通新需求或缺少项目上下文文档不触发全项目重扫。

<a id="flow-resume"></a>
## 新窗口从这里开始

1. 确认 Android 项目、当前分支、Git 状态和本需求自己的配置；未显式指定配置时才读取 `profiles/local.yaml`。
2. 从配置读取 `project_path` 和 `requirement_name`；已有 `requirement_dir` 就直接复用，没有时先复用唯一同名日期目录，没有匹配才按首次启动日期创建并写回配置。
3. 优先读取 `<requirement_dir>/docs/spec.md`；旧目录只有唯一 `docs/<requirement_name>.md` 时把它作为兼容规格源，不创建第二份；存在 `api/api.md`、`docs/result.md` 时一并读取。
4. 核对 `baseline_commit` 是否仍是当前历史祖先，读取从基线到当前 `HEAD` 的边界提交和 Git 状态；用提交标题中的 `BDD-##`、`SLICE-##` 或 `MIGRATE-*` 定位，再核对实际代码、后续修复或回退和有效证据是否满足最新规格，不能仅凭 ID 判断完成。
5. 根据 `spec.md` 状态继续：`draft` 回到澄清，`confirmed` 才能实现；未提交切片按增量闭环核对归属、授权和原起点后续接，不当作新切片启动。已有最终结果但代码或验收语义变化时重跑失效验证。
6. 不依赖聊天摘要恢复需求，不复用其他需求的测试结果，也不自动清理、stash 或覆盖已有改动。

<a id="flow-components"></a>
## 当前组成

```text
android-delivery-skills/
├── android-onboard-existing-project/  前置入口：陌生项目地图、基线和风险边界
├── android-implement-and-verify/  主流程：澄清、规格、实现、增量和最终交付
├── android-test-and-fix/          测试、AI Journey、失败诊断和最小修复
├── android-code-review/           规格一致性与 Android 工程风险审查
├── android-verify-api-contract/   API 契约核验
├── android-verify-ui/             UI 截图、交互和无障碍验收
├── docs/                          当前流程总览与图解
├── profiles/                      当前需求的本机配置示例
└── scripts/verify_results.py      可选：核对 JUnit XML 非空、非全跳过且不过期
```

具体需求主入口是 `android-implement-and-verify`；`android-onboard-existing-project` 仅处理明确的陌生项目首次接手。其余四个 Skill 只在任务或最终 diff 触发时使用，不建立统一 route、状态机或脚本门禁。

<a id="flow-layout"></a>
## 文档与文件布局

一个需求拥有独立分支、worktree、配置和 `requirement_dir`。配置与需求文档分开：

```text
android-delivery-skills/
└── profiles/
    ├── local.example.yaml       配置格式示例
    ├── local.yaml               未显式指定配置时的单需求默认值
    └── <requirement>.yaml       并行或长期需求各自使用的独立配置；只需先填项目路径和需求名

<project_path>/document/YYYY-MM-DD-<requirement_name>/    即 requirement_dir
├── docs/
│   ├── spec.md                  唯一需求规格：行为、BDD、保护项、范围、来源和测试边界
│   └── result.md                最终结果：真实命令、BDD 证据、专项和剩余风险（最终阶段按需创建）
├── api/                         收到 API 资料时按需创建
│   ├── api.md                   唯一归一化契约：来源、请求响应、冲突和未知项
│   └── <原始资料>               OpenAPI、YApi 导出、抓包、JSON 或截图（需要留存时）
├── ui/                          需要落盘 UI 证据时按需创建
│   └── <设计导出或验收截图>      原始设计、实现截图和必要映射；不复制无关资源
└── test-cases/                  需要 AI Journey 时按需创建
    └── journeys/
        └── <需求作用域>/
            └── <场景名>.xml      Agent 根据已确认 BDD 创建的官方 Journey 用例
```

陌生项目接手文档与日期需求目录并列，默认只创建一个入口文件：

```text
<project_path>/document/project-context/
└── overview.md                  项目地图、验证基线、风险、未知项和来源指针
```

项目已有等价文档时引用或最小更新，不创建第二份事实源；接手文档不保存需求 BDD、实现进度或最终验收结果。

Android 生产代码和普通自动化测试仍落在业务项目自己的既有目录；需求级 Journey XML 是例外，固定放在 `requirement_dir`：

```text
<project_path>/<module>/src/main/          生产 Kotlin/Java、Manifest 和资源
<project_path>/<module>/src/test/          本地单元测试
<project_path>/<module>/src/androidTest/   Instrumentation、UIAutomator 或项目已有设备测试
<requirement_dir>/test-cases/journeys/     Agent 创建并维护的需求级 Journey XML
<项目已有 build/report 位置>               Gradle/JUnit/Lint 原始报告；路径和结果写入 result.md
```

| 输入或产物 | 固定落点 | 规则 |
| --- | --- | --- |
| 陌生项目接手上下文 | `<project_path>/document/project-context/overview.md` | 需要持久化时创建；只保存项目级结论、边界和来源指针，不替代当前代码或需求证据 |
| 当前需求配置 | 用户指定的独立 profile；未指定时 `profiles/local.yaml` | 首次只需 `project_path` 和 `requirement_name`；配置不得包含敏感值 |
| `requirement_dir` | `<project_path>/document/YYYY-MM-DD-<requirement_name>/` | 先复用唯一同名日期目录；没有匹配才由 Agent 创建并写回配置，后续窗口不随日期漂移 |
| Word、PDF、截图或聊天需求 | 新需求记录到 `docs/spec.md`；旧目录可沿用唯一 `docs/<requirement_name>.md` | 不因输入格式创建平行事实源，也不复制旧规格制造第二份 |
| Figma 链接 | `docs/spec.md` 的 UI 来源 | 需要保留导出或截图时才创建 `ui/` |
| API 链接、文件、截图或聊天契约 | `api/api.md` | 原始证据需要留存时与契约共置于 `api/` |
| Figma 生成的 XML、drawable、字体和映射 | Android 项目既有 `src/main/res/` | `ui/` 只保留来源或验收证据，不代替业务资源目录 |
| Kotlin/Java 实现 | Android 项目既有模块 | 不把实现副本写入需求文档目录 |
| Unit、Instrumentation 和 UI 测试 | Android 项目既有测试 source set | 不建立 Skill 私有测试框架或通用 Harness |
| AI Journey XML | `<requirement_dir>/test-cases/journeys/<需求作用域>/` | Agent 从已确认 BDD 创建；不要求用户预建 |
| 测试报告、截图和日志 | 保留在实际工具输出位置；必要证据可放 `ui/` 或 API 原始资料旁 | `docs/result.md` 记录命令、路径、数量和结论，不复制大批构建产物 |

- 新需求的 `spec.md` 是唯一需求事实源；旧目录只有唯一 `docs/<requirement_name>.md` 时继续把它作为兼容规格源，不自动创建第二份。
- 项目上下文是跨需求索引；当前代码、Gradle、CI 或实际命令与它冲突时以当前一手证据为准，接手基线不得冒充需求 BDD 或最终交付证据。
- `result.md` 是输出，不得反向改写已确认需求。
- `spec.md`、`api.md` 和 `result.md` 都在标题后维护可点击目录和稳定锚点；说明按章节、编号列表和必要表格组织，增量更新时同步目录。
- API 资料一旦提供给当前需求，就创建或更新 `api/api.md`，不再询问是否处理。
- `requirement_dir` 首次定位后必须写回当前需求配置；定位前先检查唯一同名旧目录，避免跨日期或新窗口产生第二个目录。
- 所有按需目录都在真正有资料时才创建；Journey 被选为验证方式时由 Agent 创建对应 `test-cases/journeys/`。
- 不恢复旧版 `.state/`、计划收据、测试映射、route 快照、SHA 状态链或 11 个模板；`test-cases/` 只承载需求级 Journey XML。

<a id="flow-main"></a>
## 完整流程

| 阶段 | Agent 做什么 | 用户确认 | 主要产物 |
| --- | --- | --- | --- |
| 1. 查事实 | 读项目、需求配置、代码、Git、UI/API 来源和已有测试 | 仅工作区归属或资料处置需要决定时 | 已知事实与当前基线 |
| 2. 集中澄清 | 只问会改变行为、范围、数据、失败处理、验收或资料来源的问题 | 逐轮回答决策树当前前沿 | 完整共同理解 |
| 3. 一次确认规格 | 把需求、BDD、保护行为、范围、来源、实施决策和测试边界写入一份规格 | 对最新完整 `spec.md` 纯确认一次 | `status: confirmed` 的 `spec.md` 和 `SPEC` 边界提交 |
| 4. 纵向实现 | 每个切片执行失败测试、最小实现、受影响验证、工作区审查和自动边界提交 | 规格确认时一次性授权本地边界提交 | 代码、测试和可恢复的原子提交 |
| 贯穿所有阶段：增量闭环 | 随时接收或发现增量，只重做受影响部分 | 语义、范围或测试边界变化时确认变化部分 | 更新后的规格、代码和测试 |
| 6. 最终交付 | 分层审查 `baseline_commit...HEAD`，做一次适用的完整验证并确认工作区干净 | 用户明确要求最终检查、准备提交或完整交付 | 已提交的 `docs/result.md`、最终审计和中文结论 |

<a id="flow-facts"></a>
### 1. 先查事实

- 读取项目 `AGENTS.md`、相关代码、Gradle、测试、当前分支、Git 状态、当前需求配置及用户输入。
- 存在 `document/project-context/overview.md` 时只读取当前需求相关来源；缺失时不阻塞普通需求或触发全项目重扫。
- 能从文件、代码、工具或链接查到的事实由 Agent 自己查，不转问用户。
- 开始需求前先建立独立且干净的需求分支或 worktree，再把当前提交写入 `spec.md` 的 `baseline_commit`。
- 引用路径在当前分支不存在时保留原引用，说明查过的位置，并询问参考分支或替代来源；不擅自删除引用或切分支。
- 工作区已有改动时先说明归属风险，等待用户在原工作区自行保存、提交或隔离；不得把它们纳入自动边界提交。工作区恢复干净前不记录本需求基线。

<a id="flow-clarify"></a>
### 2. 集中澄清

- 先建立决策树，每轮只问前置事实已明确的当前前沿。
- 同一轮列出所有互不依赖的问题，使用 `Q1`、`Q2` 编号，说明影响并给出推荐答案。
- 用户可以一次回答一个或多个问题；吸收本轮全部回答和纠正后，再计算剩余前沿。
- 待确认非空时，不新增或改写任何 BDD、不确认计划、不修改生产代码；已有且未受影响的 BDD 保留。
- 实现方式可自行选择且不改变可见行为时，记为实施决策，不打扰用户。

<a id="flow-spec"></a>
### 3. 一次确认规格

新需求统一创建或增量更新 `<requirement_dir>/docs/spec.md`；旧目录只有唯一 `docs/<requirement_name>.md` 时继续维护该兼容规格源：

```markdown
---
status: draft
baseline_commit: <需求开始提交>
---

# <需求名称>

## 目录
1. [问题与目标](#spec-goal)
2. [已确认行为](#spec-behavior)
3. [已上线业务保护](#spec-protection)
4. [BDD 验收与计划验证方式](#spec-bdd)
5. [UI 与 API 来源](#spec-sources)
6. [实现范围](#spec-scope)
7. [实施决策](#spec-decisions)
8. [测试边界](#spec-testing)
9. [不在范围](#spec-out-of-scope)
10. [待确认](#spec-pending)

<a id="spec-goal"></a>
## 问题与目标

<a id="spec-behavior"></a>
## 已确认行为

<a id="spec-protection"></a>
## 已上线业务保护

<a id="spec-bdd"></a>
## BDD 验收与计划验证方式

<a id="spec-sources"></a>
## UI 与 API 来源

<a id="spec-scope"></a>
## 实现范围

<a id="spec-decisions"></a>
## 实施决策

<a id="spec-testing"></a>
## 测试边界

<a id="spec-out-of-scope"></a>
## 不在范围

<a id="spec-pending"></a>
## 待确认
```

- `待确认` 非空时保持 `draft`；清空后补齐受影响 BDD 和计划验证，再请求规格确认。
- BDD 只描述 Given/When/Then 的外部可观察结果，每条同时写计划验证方式。
- 自动化不可行时，写可复现人工步骤、原因和未验证风险，不能只写“人工验证”。
- 需求和实施计划合并为一次确认；请求确认时说明它同时授权当前需求的本地边界提交。用户确认最新完整内容后才改为 `confirmed`，自动形成不夹带生产实现的 `SPEC` 提交；首次实现前工作区必须恢复干净，中途规格变化按增量闭环处理。
- 默认保持一份规格。Agent 根据可观察结果、必要上下文和验证入口判断整体交付或分片，在实施决策简述依据；不按 BDD 数量、行数或累计 Token 判大小。紧密相关的 BDD 可以在同一边界交付，标题列出对应 `BDD-##`；整体过大或需分组、依赖计划时，在规格内增加带 `SLICE-##`、覆盖 BDD、依赖和计划验证的纵向切片，不创建第二份 Tickets。
- 宽范围迁移在“实施决策”中预先记录 `MIGRATE-EXPAND`、`MIGRATE-##` 和 `MIGRATE-CONTRACT` 的范围与依赖。规格只保存静态计划，不记录执行状态、测试结果或提交 SHA；进度从 `baseline_commit..HEAD` 的边界提交恢复。

<a id="flow-implement"></a>
### 4. 纵向实现与紧反馈

每个已确认切片依次执行：

1. 复核交付粒度，确认工作区干净，记录 `slice_base_commit = HEAD`，选择该边界覆盖的 BDD 和最高可观察测试边界。
2. 先写会因缺少目标行为而失败的测试，并确认失败原因正确。
3. 编写刚好满足行为的最小实现并运行当前测试；多条 BDD 在同一边界内逐条重复红绿循环，再运行直接受影响模块测试和必要编译。
4. 检查 staged、unstaged 和 untracked 内容，只保留当前切片范围。
5. 自动创建包含对应 BDD ID 或 `SLICE-##` 的中文语义原子提交，正文保留实际验证及未覆盖边界；提交后工作区重新干净才进入下一切片。整片取消/替代按增量闭环收拢，不要求完成旧目标或空实现提交。
6. 完整测试、Lint、需求级审查和专项留到最终阶段一次执行。

疑难 Bug、偶发故障和性能回归先建立可重复命中准确症状的紧反馈入口；无法建立时报告阻塞，不猜因修复。能复现后依次执行最小化、假设排序、单假设单变量探针和证据支持的最小修复；通常列出 2–5 个有依据的可证伪假设，仅有一个合理候选时记录排除依据、不凑数。偶发问题用固定轮次统计复现率。

<a id="flow-testing"></a>
### 5. 测试与 AI Journey

- 优先复用项目已有 Unit、Instrumentation、UIAutomator、截图和 CI 入口。
- 核心端到端 UI 路径可把 BDD 转为官方 Journey XML；Agent 创建 `<requirement_dir>/test-cases/journeys/<需求作用域>/<场景名>.xml`，再自动准备设备、操作并判断可见结果。
- 老项目低于 AGP 9.0.0 时保持原构建；生成 APK 后优先通过 Android CLI 测试已安装应用，不为测试升级 AGP，也不创建自定义 Harness 或运行脚本。
- Journey 只承载稳定的点击、输入和滑动/滚动。双击、长按、多指、旋转、计数、分支和精确耗时使用确定性自动测试。
- 测试数量为零、全部 skipped、命令未执行或报告早于当前代码和规格，都属于未验证。
- 同一根因连续三轮没有进展时停止，报告证据、尝试和解除条件。

<a id="flow-incremental"></a>
### 6. 增量闭环

增量更新贯穿所有阶段，不是实现后的步骤。任何时候收到或发现需求变化、漏洞、遗漏，都先评估，从最早受影响内容同步下游、复验后继续；不等待当前阶段或检查通过，也不重走未受影响流程。

只对改变行为、范围、契约或验收的部分重新确认；已确认要求的补漏、范围内细节和纯计划调整不重复确认。始终保留同一规格、原基线和授权边界，以最新规格、实际代码和有效证据判断完成。

实现中途与跨窗口续接须证明当前改动的归属、授权、隔离性和原切片起点；不能把 SPEC 提交当作实现完成。整片取消/替代、边界收拢与结果重验统一见 [增量闭环](../android-implement-and-verify/references/implement-and-test.md#incremental-loop)，不另建规则副本。

<a id="flow-inputs"></a>
## Figma 与 API

<a id="flow-figma"></a>
### Figma

- 在 `spec.md` 保留原始设计链接及其对应页面或状态。
- 先从项目确认 XML View、Compose 或混合技术栈。
- 已确认的 XML View 页面使用同级 `figma-android-xml` 生成 XML 和资源；会话列表未显示时先检查 `android-delivery-skills/figma-android-xml/SKILL.md`，Compose 页面不调用 XML Skill。
- 设计不可读时说明边界；用户确认后可以使用截图、导出或临时 UI，但不能声明像素级通过。
- 生成成功或构建成功不等于视觉通过，最终仍需真实页面截图验收。

<a id="flow-api"></a>
### API

- 收到资料后立即创建或增量更新 `api/api.md`，记录来源、读取时间、method/path、参数、类型、可空性、单位、响应、错误、分页、冲突和未知项。
- 交互式接口页面必须先递归展开请求与响应 Schema 的全部可展开节点；折叠内容未读完时不得判定字段缺失或要求用户补充。
- 网页、截图和聊天资料只证明其中实际可见的事实；不得从客户端类型反推服务端契约。
- 来源冲突且影响 DTO、序列化、业务行为或验收时询问用户，不自行选择看似合理的类型。
- 经用户确认可使用 Fake 或临时契约，但必须与 release 正式路径隔离，也不能冒充正式服务端能力。

<a id="flow-final"></a>
## 最终交付与专项

只有用户明确要求最终检查、完整交付或准备提交时才开始。先确认 `baseline_commit` 是当前 `HEAD` 的祖先且工作区干净，再依次读取 stat、name-status 和提交历史；按 `BDD-##`、`SLICE-##` 或 `MIGRATE-*` 审查小 diff，单段仍过大时继续按模块、文件和 hunk 分块，从 name-status 清单逐项销账，最后检查整体 diff。命令、variant/设备环境和被验证输入未变时复用已有证据，只补缺失或失效项：

| 触发内容 | 使用能力 |
| --- | --- |
| Kotlin/Java、业务逻辑、生命周期或工程风险 | `android-code-review` |
| 测试失败、设备回归、疑难 Bug 或 AI Journey | `android-test-and-fix` |
| endpoint、DTO、序列化、mapper、缓存契约 | `android-verify-api-contract` |
| 布局、状态、交互、截图、文案或无障碍 | `android-verify-ui` |

按需检查持久化迁移、生命周期、性能、安全隐私、构建、依赖和 release/R8。没有需求或 diff 候选时不机械展开；适用但缺少设备、基准、旧数据或正式契约时标记未验证。

最终创建或更新 `docs/result.md`，每个 BDD 恰好对应一项结果；通过或失败必须有实际自动测试或已执行人工步骤，未验证则明确缺少的证据。审查范围可信、验证实际执行且工作区除结果外干净时，无论通过、部分通过还是失败都如实形成 `RESULT` 提交；只提交结果文档和项目约定的必要证据，不提交构建产物、原始大日志、敏感信息、本机绝对路径或无关截图。结果记录 `verified_head`，不记录会因报告自身提交而立即失效的 `current_head`；提交后以新的 `HEAD` 重做 `baseline_commit...HEAD` 整体审计并确认工作区干净。结论只使用“通过、失败、未验证、不适用”；缺少必要证据时不能声明完整通过。

`scripts/verify_results.py` 只辅助检查 JUnit XML：报告必须晚于当前代码和规格、测试总数非零、至少一个测试实际执行且 failures/errors 为零。它不决定需求、专项或最终业务结论。

<a id="flow-parallel"></a>
## 多需求并行与大需求

- 并行入口只用于互不冲突且可独立验收的需求。
- 每个需求使用独立 worktree、分支、配置、`requirement_dir`、`spec.md`、代码和测试结果；配置首次只需 `project_path + requirement_name`，各自推导日期目录，`profiles/local.yaml` 只能作为当前单个需求未指定配置时的默认值。
- 同一 worktree 不同时修改两个活动需求。共享模拟器、真机、账号和不可并发后端数据仍串行使用。
- 默认在一份规格内完成大需求，并按 BDD 做纵向切片；每个切片形成上下文检查点，不因代码量大创建第二份 Tickets。
- 公共 API、包名、设计系统或构建配置等宽范围迁移使用 expand-migrate-contract，并以 `MIGRATE-EXPAND`、`MIGRATE-##`、`MIGRATE-CONTRACT` 作为稳定提交 ID：新旧形式兼容、按模块分批迁移、最后删除旧形式；每批独立验证和提交，最终仍统一审计 `baseline_commit...HEAD`。Contract 前按实际发布边界核对 Kotlin/Java 源兼容、JVM 二进制兼容、默认参数、反射、生成代码和仓库外消费者，无法证明时保留适配层或停止确认。
- 只有用户决定把多个独立结果作为多个需求管理时，才分别进入现有并行流程；存在依赖的结果按顺序完成。
- 集成前由用户授权；需求分支先 rebase 到最新目标分支，冲突时停止核对业务语义，目标分支只 fast-forward 合并，并在合入后重跑受影响验证。
- 完整合并顺序、冲突分流和批次停止条件见 [合并规则图](FLOW_DIAGRAMS.md#diagram-merge)。

<a id="flow-safety"></a>
## 授权和安全边界

- 不自动切分支、推送、集成、发布、升级 AGP、操作生产数据或索取凭据。
- 需求未确认前不修改生产代码；确认后出现新的产品未知立即回到澄清。
- 不清理、覆盖、stash 或回退用户已有改动。
- 规格确认时一次性授权独立需求分支上的已确认输入、实现和最终结果边界提交，前提是范围纯净且不会夹带已有改动；实现提交必须通过相应验证，`RESULT` 则如实记录实际通过、部分通过或失败结论。用户拒绝时暂停流程。
- Mock、Fake 和 sample data 默认与 release 路径隔离；主代码占位必须经用户明确批准并记录替换边界。
- 测试失败不能通过删除断言、吞异常、扩大超时或伪造报告解决。
- 本地边界提交不授权 amend、squash、rebase、推送、集成或发布；这些操作仍分别遵守项目 `AGENTS.md` 和用户授权。
