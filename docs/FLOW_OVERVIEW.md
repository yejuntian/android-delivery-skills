# Android Delivery Skills 当前流程总览

> 本文用于新窗口快速恢复流程，不是额外门禁或需求事实源。规则冲突时以当前项目 `AGENTS.md`、对应 Skill 和已确认 `spec.md` 为准。
> 图形版见 [FLOW_DIAGRAMS.md](FLOW_DIAGRAMS.md)。

## 目录

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

<a id="flow-resume"></a>
## 新窗口从这里开始

1. 确认 Android 项目、当前分支、Git 状态和本需求自己的配置；未显式指定配置时才读取 `profiles/local.yaml`。
2. 从配置读取 `project_path` 和 `requirement_name`；已有 `requirement_dir` 就直接复用，没有时先复用唯一同名日期目录，没有匹配才按首次启动日期创建并写回配置。
3. 优先读取 `<requirement_dir>/docs/spec.md`；旧目录只有唯一 `docs/<requirement_name>.md` 时把它作为兼容规格源，不创建第二份；存在 `api/api.md`、`docs/result.md` 时一并读取。
4. 核对 `baseline_commit` 是否仍是当前历史祖先，并检查从基线到当前 `HEAD` 的 diff 和未提交改动。
5. 根据 `spec.md` 状态继续：`draft` 回到澄清，`confirmed` 才能实现；已有最终结果但代码又变化时重跑受影响验证。
6. 不依赖聊天摘要恢复需求，不复用其他需求的测试结果，也不自动清理、stash 或覆盖已有改动。

<a id="flow-components"></a>
## 当前组成

```text
android-delivery-skills/
├── android-implement-and-verify/  主流程：澄清、规格、实现、增量和最终交付
├── android-test-and-fix/          测试、AI Journey、失败诊断和最小修复
├── android-code-review/           规格一致性与 Android 工程风险审查
├── android-verify-api-contract/   API 契约核验
├── android-verify-ui/             UI 截图、交互和无障碍验收
├── docs/                          当前流程总览与图解
├── profiles/                      当前需求的本机配置示例
└── scripts/verify_results.py      可选：核对 JUnit XML 非空、非全跳过且不过期
```

主入口是 `android-implement-and-verify`。其余四个 Skill 只在任务或最终 diff 触发时使用，不建立统一 route、状态机或脚本门禁。

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
| 3. 一次确认规格 | 把需求、BDD、保护行为、范围、来源、实施决策和测试边界写入一份规格 | 对最新完整 `spec.md` 纯确认一次 | `status: confirmed` 的 `spec.md` |
| 4. 纵向实现 | 每个行为执行失败测试、最小实现和受影响验证 | 不重复确认已确认内容 | 代码与真实测试结果 |
| 5. 增量闭环 | 按变化类型只重做受影响部分 | 语义、范围或测试边界变化时确认变化部分 | 更新后的规格、代码和测试 |
| 6. 最终交付 | 基于完整 diff 做一次适用的完整测试和专项检查 | 用户明确要求最终检查、准备提交或完整交付 | `docs/result.md` 和中文结论 |

<a id="flow-facts"></a>
### 1. 先查事实

- 读取项目 `AGENTS.md`、相关代码、Gradle、测试、当前分支、Git 状态、当前需求配置及用户输入。
- 能从文件、代码、工具或链接查到的事实由 Agent 自己查，不转问用户。
- 开始需求时把当前提交写入 `spec.md` 的 `baseline_commit`。
- 引用路径在当前分支不存在时保留原引用，说明查过的位置，并询问参考分支或替代来源；不擅自删除引用或切分支。
- 工作区已有改动时先说明它们是否可能属于本需求，由用户决定纳入、隔离或先处理。

<a id="flow-clarify"></a>
### 2. 集中澄清

- 先建立决策树，每轮只问前置事实已明确的当前前沿。
- 同一轮列出所有互不依赖的问题，使用 `Q1`、`Q2` 编号，说明影响并给出推荐答案。
- 用户可以一次回答一个或多个问题；吸收本轮全部回答和纠正后，再计算剩余前沿。
- 产品级未知未清空前，不写 BDD、不确认计划、不修改生产代码。
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

- `待确认` 非空时保持 `draft`，不得写 BDD。
- BDD 只描述 Given/When/Then 的外部可观察结果，每条同时写计划验证方式。
- 自动化不可行时，写可复现人工步骤、原因和未验证风险，不能只写“人工验证”。
- 需求和实施计划合并为一次确认；用户确认最新完整内容后才改为 `confirmed`。
- 默认保持一份规格。复杂需求在规格内拆纵向切片，不自动创建 Tickets。

<a id="flow-implement"></a>
### 4. 纵向实现与紧反馈

每个已确认行为依次执行：

1. 选择一个 BDD 和最高可观察测试边界。
2. 先写会因缺少该行为而失败的测试，并确认失败原因正确。
3. 编写刚好满足行为的最小实现。
4. 运行当前测试、直接受影响模块测试和必要编译。
5. 重复下一个行为；完整测试、Lint 和专项留到最终阶段一次执行。

疑难 Bug、偶发故障和性能回归必须先建立 Agent 可重复执行的紧反馈入口。不能稳定命中用户症状时，报告尝试和缺少条件，不猜根因直接修改。

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

| 变化 | 规格状态 | 需要确认 | 重做范围 |
| --- | --- | --- | --- |
| 用户行为、业务语义或验收变化 | 改回 `draft` | 只确认变化部分 | 受影响 BDD、代码和测试 |
| 模块、依赖、公共接口或测试边界变化 | 暂时改回 `draft` | 只确认范围或测试边界变化 | 受影响实现和验证 |
| 颜色、间距、资源或已确认范围内实现细节 | 保持 `confirmed` | 不需要 | 受影响代码和最小验证 |
| 最终验证后代码再次变化 | 保持当前需求状态 | 语义未变时不需要 | 重跑受影响项并重新汇总最终结果 |

UI/API 资料是否触发重新确认，取决于它是否改变已确认行为或验收，不取决于输入是链接、截图还是文件。

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

只有用户明确要求最终检查、完整交付或准备提交时才开始。以当时的完整 Git diff 为准统一调度适用验证；命令、variant/设备环境和被验证输入未变时复用已有证据，只补缺失或失效项：

| 触发内容 | 使用能力 |
| --- | --- |
| Kotlin/Java、业务逻辑、生命周期或工程风险 | `android-code-review` |
| 测试失败、设备回归、疑难 Bug 或 AI Journey | `android-test-and-fix` |
| endpoint、DTO、序列化、mapper、缓存契约 | `android-verify-api-contract` |
| 布局、状态、交互、截图、文案或无障碍 | `android-verify-ui` |

按需检查持久化迁移、生命周期、性能、安全隐私、构建、依赖和 release/R8。没有需求或 diff 候选时不机械展开；适用但缺少设备、基准、旧数据或正式契约时标记未验证。

最终创建或更新 `docs/result.md`，每个 BDD 恰好对应一项实际自动测试或已执行人工步骤。结论只使用“通过、失败、未验证、不适用”；缺少必要证据时不能声明完整通过。

`scripts/verify_results.py` 只辅助检查 JUnit XML：报告必须晚于当前代码和规格、测试总数非零、至少一个测试实际执行且 failures/errors 为零。它不决定需求、专项或最终业务结论。

<a id="flow-parallel"></a>
## 多需求并行与大需求

- 并行入口只用于互不冲突且可独立验收的需求。
- 每个需求使用独立 worktree、分支、配置、`requirement_dir`、`spec.md`、代码和测试结果；配置首次只需 `project_path + requirement_name`，各自推导日期目录，`profiles/local.yaml` 只能作为当前单个需求未指定配置时的默认值。
- 同一 worktree 不同时修改两个活动需求。共享模拟器、真机、账号和不可并发后端数据仍串行使用。
- 默认在一份规格内完成大需求，并按 BDD 做纵向切片；不因代码量大自动创建 Tickets。
- 只有用户决定把多个独立结果作为多个需求管理时，才分别进入现有并行流程；存在依赖的结果按顺序完成。
- 集成前由用户授权；需求分支先 rebase 到最新目标分支，冲突时停止核对业务语义，目标分支只 fast-forward 合并，并在合入后重跑受影响验证。
- 完整合并顺序、冲突分流和批次停止条件见 [合并规则图](FLOW_DIAGRAMS.md#diagram-merge)。

<a id="flow-safety"></a>
## 授权和安全边界

- 不自动切分支、提交、推送、发布、升级 AGP、操作生产数据或索取凭据。
- 需求未确认前不修改生产代码；确认后出现新的产品未知立即回到澄清。
- 不清理、覆盖、stash 或回退用户已有改动。
- Mock、Fake 和 sample data 默认与 release 路径隔离；主代码占位必须经用户明确批准并记录替换边界。
- 测试失败不能通过删除断言、吞异常、扩大超时或伪造报告解决。
- 提交、推送和发布分别需要用户明确授权，并遵守项目 `AGENTS.md`。
