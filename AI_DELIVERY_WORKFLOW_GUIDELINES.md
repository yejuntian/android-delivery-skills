# Android Delivery Skills 整体流程说明

本文档面向流程使用者和后续维护模型，用于说明这套 Skill 为什么存在、每个角色负责什么、一次 Android 需求如何从理解走到交付，以及哪些情况必须阻断或降级。

本文档是整体理解入口，不取代具体执行规则。实际执行时仍以 `_shared/android-global-rules.md`、`android-implement-and-verify/SKILL.md` 和对应专项 `SKILL.md` 为准。

## 目录

1. [设计目标](#一设计目标)
2. [核心原则](#二核心原则)
3. [Skill 角色与职责](#三skill-角色与职责)
4. [脚本职责划分](#四脚本职责划分)
5. [端到端交付流程](#五端到端交付流程)
6. [需求确认与中途变更](#六需求确认与中途变更)
7. [编码与影响路由](#七编码与影响路由)
8. [自动化测试策略](#八自动化测试策略)
9. [Journey 的定位](#九journey-的定位)
10. [失败分析与自动修复](#十失败分析与自动修复)
11. [机器证据与防假绿](#十一机器证据与防假绿)
12. [最终结论与 Git](#十二最终结论与-git)
13. [用户需要提供什么](#十三用户需要提供什么)
14. [明确能力边界](#十四明确能力边界)
15. [规则来源与维护方式](#十五规则来源与维护方式)

## 一、设计目标

这套流程不是单纯让 AI 生成 Android 代码，而是让 AI 在受约束、可复核的前提下完成需求理解、编码、审查、测试、修复和交付。

目标包括：

- 需求没有理解清楚时不开始脑补式编码。
- 同一需求中途增删改时保留最近确认总需求和最初 Git 基线。
- 默认遵守最小化修改、单一职责、高内聚低耦合和业务隔离。
- Kotlin 优先，同时完整支持 Java、XML View、旧 Gradle 和旧测试框架。
- UI、非 UI 和混合业务都能分配到合适的测试层。
- 每个“通过”都有当前需求和最终代码上的新鲜证据。
- 专项工具失败时允许 AI 分析替代，仍无法关闭时明确提示用户。
- 没有设备或资料时诚实保留未验证项，不把能力缺失写成通过。
- Git 提交由用户决定，不把自动提交作为交付完成条件。

这套流程不能承诺任何代码绝对没有问题。它要实现的是：风险有门禁、结论有证据、职责有边界、失败有去向、未验证项不会被隐藏。

### 1.1 架构定位

本系统采用轻量化 `Harness + SDD` 总体架构，并把 `BDD + TDD` 作为需求实现核心实践：

```text
Harness（约束 AI 如何执行）
└── SDD（以最新确认需求驱动开发）
    ├── BDD（把需求拆成可观察业务行为）
    └── TDD（用行为级 Red-Green 驱动最小实现）
```

Harness 由总入口、共享规则、脚本、专项 Skill 和证据门禁共同组成，不是名为 `harness` 的单一文件；`journey-harness` 仅指可选界面测试壳。SDD 的唯一需求事实是 `requirement_file`，R1/R2/R3、BDD/Then、测试和最终证据都必须跟随它的确认版本。

## 二、核心原则

### 2.1 需求优先

需求文档、用户补充、UI 资料和 API 资料共同构成需求输入。AI 只根据已经确认的信息生成 BDD 和实现；可以依据明确需求定义业务字段、页面状态和待对齐的临时实现，但不得把它们冒充正式传输字段、错误码、设计基准或测试结果。

### 2.2 最小修改

优先沿用目标项目现有架构、依赖、模块、命名、测试框架和 Gradle task。不得为了统一风格无关升级 AGP、Gradle、JDK，或把局部需求扩大成全项目重构。

### 2.3 单一职责

总入口只编排；Git 脚本只收集差异；需求脚本只维护修订；测试 Skill 只负责测试和修复；UI Skill 独立负责视觉与可访问性验收。一个脚本或 Skill 不吞并其他角色的职责。

### 2.4 自适应而非全量堆叠

根据已确认需求、最终 diff 和业务风险选择最低且足够的验证层。小改动不机械执行所有重型流程，高风险改动也不能因为代码行数少而跳过专项门禁。

### 2.5 证据优先

自然语言“已经通过”不是证据。最终结论必须引用真实命令、JUnit testcase、Android Lint 机器报告、专项结果、截图/布局或结构完整的人工执行记录。

### 2.6 用户控制

不自动切分支、stash、commit、push、reset、checkout 或 clean。清数据、卸载、真实支付、真实删除和生产环境操作也必须由用户明确授权。

### 2.7 三阶段反馈

首次编码前完整完成需求确认、BDD、测试设计和 Git 基线；编码后的完善、修改、删除或修复只运行受影响测试和必要编译；用户明确最终检查、完整交付或准备提交时，才基于最终代码执行一次完整路由和门禁。业务验收语义变化只修订受影响义务，不把整个流程推倒重来。

### 2.8 已上线业务优先保护

当前需求明确允许改变的已有业务按确认范围修改；没有明确覆盖的已有行为默认保持不变。编码前只读、定向分析相关项目代码、调用方和测试，在需求说明最前面展示“本次明确修改、必须保持不变、暂时无法确认、明确不修改范围”。修改项和保护项分别使用 `【修改已上线业务】`、`【保护已上线业务】` 原子 Then 进入现有测试与证据门禁；最终 diff 新发现计划外影响时重新确认，不由 AI 自行处置。

## 三、Skill 角色与职责

| Skill                          | 角色 | 负责内容 | 不负责内容 |
|--------------------------------|---|---|---|
| `android-implement-and-verify` | 项目负责人、总入口 | 读取需求、维护修订、建立 Git 基线、控制编码、路由专项、汇总最终交付 | 不代替专项完成详细审查 |
| `android-review-diff`          | 变更范围 Reviewer | 检查需求覆盖、改动越界、误改旧逻辑、遗漏调用方和回归风险 | 不负责整体架构和测试执行 |
| `android-review-code-quality`  | 架构与质量 Reviewer | 检查职责边界、耦合、重复、可维护性和项目架构一致性 | 不负责需求确认和动态稳定性 |
| `android-audit-stability`      | 稳定性工程师 | 检查生命周期、资源释放、泄漏、并发、性能、安全隐私及动态能力适用性 | 不把静态未发现问题写成绝对无泄漏 |
| `android-test-and-fix`         | 测试工程师与修复门禁 | 局部迭代执行受影响测试和必要编译；最终交付执行完整测试、分析失败、最小修复和回归 | 不负责需求确认和设计稿视觉还原 |
| `android-verify-api-contract`  | API 契约检查员 | 检查 endpoint、Request/Response、DTO、mapper、错误码、缓存字段和兼容性 | 不负责普通架构和 UI 验收 |
| `android-verify-ui`            | 独立 UI 验收工程师 | 检查设计还原、截图、布局、动态 UI 和可访问性 | 不生成或管理业务测试用例，不由 route 自动执行 |
| `figma-android-xml`         | 外部 XML UI 生产 Skill | 在已确认的 Figma + XML View 场景生成 XML、Drawable、Color、Dimen 和预览资源 | 不写 Kotlin/Java 业务逻辑，不负责行为测试和最终 UI 验收 |

`android-verify-ui` 保持独立。Journey 可以证明用户操作和可见结果，UI 验收负责判断页面是否符合设计基准；二者可以复用截图，但不能互相代替。

`figma-android-xml` 作为成熟黑盒单向接入：Delivery 只判断是否满足“Figma + XML View”，传入已确认设计，接收 UI 资源和 XML；不复制它的内部生成规则，也不修改它的脚本或配置。产物进入项目后执行独立交接门禁，确保用户文案、图片语义、项目资源和业务代码边界服从 Delivery 全局规则。Compose 需求继续服从目标项目现有实现。

## 四、脚本职责划分

| 脚本 | 单一职责 |
|---|---|
| `scripts/delivery.py` | 读取需求、检查环境、编排需求/计划确认和 route |
| `scripts/requirement_workspace.py` | 预览并轮换串行需求独立目录，按数量与时间延迟回收项目外运行资料 |
| `scripts/config_paths.py` | 统一解析项目、需求和项目外状态路径 |
| `scripts/git_changes.py` | 只读收集分支、基线、committed/staged/unstaged/untracked、A/M/D/R 和实际 patch |
| `scripts/requirement_snapshot.py` | 保存确认需求、原子 Then、修订清单和文本差异 |
| `scripts/implementation_plan.py` | 校验唯一实施计划并生成绑定当前需求的确认收据 |
| `scripts/requirement_inputs.py` | 为需求正文、实施计划及配置声明的 UI/API 资料生成稳定摘要 |
| `scripts/route_impact.py` | 保存绑定确认计划和最终 diff 的最小条件门禁快照 |
| `scripts/android_project_capabilities.py` | 只读发现模块、variant、Gradle task 及已有静态配置/CI 信号 |
| `scripts/static_analysis.py` | 规范化已有 SARIF、生成稳定问题编号并审计静态门禁控制面变化 |
| `scripts/execution_evidence.py` | 执行一条已选择命令并生成单 gate、不可覆盖的机器收据 |
| `scripts/specialist_result.py` | 校验专项结果、P0-P3、capability、变异测试摘要和证据摘要 |
| `scripts/test_mapping.py` | 维护义务↔测试用例结构化绑定，需求增量后标记 STALE 由 AI 回填 |
| `scripts/delivery_gate.py` | 校验最终报告与当前需求、代码、测试映射和全部证据是否一致 |
| `scripts/user_facing_labels.py` | 把稳定机器枚举转换为自然中文，不修改 JSON、Schema、业务状态或退出码 |
| `android-test-and-fix/scripts/detect_package.py` | 仅在源码诊断阶段嗅探候选 applicationId；正式 Journey 仍以 APK 内真实包名为准 |
| `android-test-and-fix/scripts/run_journey.py` | 执行已经判定适用的可选壳 Journey，并生成结构化结果 |
| `../figma-android-xml/scripts/figma_workflow.py` | 外部按需下载 Figma PNG 视觉基准；不生成结构化设计数据、HTML 或 XML |
| `scripts/tests/test_skill_rule_ownership.py` | 维护 Skill 时检查规则归属、文档同步、脚本职责表和上下文预算；不进入普通 Android 需求流程 |

表中覆盖本仓库全部非测试生产脚本，以及流程直接调用的外部或维护脚本。`__init__.py` 仅声明 Python 包；其余 `scripts/tests/test_*.py` 和 `*/scripts/tests/test_*.py` 是隔离单元测试，不承担运行时职责。

所有基线、route 快照、执行日志和专项结果默认保存在目标 Android 项目之外，避免证据文件本身改变项目 diff。

## 五、端到端交付流程

### 5.1 先看这里：简单总结

对用户只呈现五步：

```text
确认需求
→ 拆分测试与确认计划
→ 实现验证
→ 变更后增量循环
→ 最终交付
```

- **确认需求**：读取需求和相关代码，置顶展示已上线业务影响；每个已接受答案先写回唯一需求文件，纯确认后进入计划准备。
- **拆分测试与确认计划**：把行为映射为测试（`confirm-plan` 后用 `delivery.py init-test-mapping` 生成结构化 `test-mapping.json`，登记每个义务的 test_ids 并回填 `CURRENT`），再用一份 Markdown 展示实现范围、旧业务影响、预计文件、测试和不修改范围；确认后才编码。
- **实现验证**：按一个可观察行为完成 `Red → 最小实现 → Green`，只报告本轮实现和验证结果。
- **变更后增量循环**：实现完善只做局部修改和受影响测试；业务语义变化只修订受影响需求、测试和代码，并使义务 sha256 变化的旧测试登记自动标记 STALE，AI 必须回填 CURRENT 才能通过最终门禁。
- **最终交付**：只有用户明确要求时，才基于最终 diff 执行完整审查、回归、构建、Lint、变异测试(PIT)、条件专项和中文报告。

接口或 UI 资料晚到但需求已经明确时，先用领域模型、Fake 和需求驱动 UI 跑通业务，并标记待正式资料对齐；正式资料到达后局部调整。关键业务含义仍不明确时，只暂停依赖该资料的范围并请求用户补充。

内部仍按三阶段执行 Git 基线、需求修订、追溯、路由、专项和机器证据；五步只是用户呈现，不新增状态机，也不删减门禁。失败时说明原因、已完成范围、剩余风险和下一步；最终如实输出中文结论，Git 提交、push 和 PR 始终由用户决定。

#### 详细图的定位与整体总览

以下流程图根据 `_shared/android-global-rules.md`、`android-implement-and-verify/SKILL.md`、各专项 Skill、现有脚本和机器 Schema 汇总形成，用于帮助后续 AI 理解整套设计，不是独立执行规则。发生冲突时，以共享规则、当前 Skill、专项 Skill 和机器 Schema 为准；修改实际流程后必须同步核对本章，避免说明与执行漂移。

```mermaid
flowchart TD
    OV1["① 确认需求<br/>含已上线业务影响"] --> OV2["② 拆分测试与确认计划<br/>只展示摘要和 Markdown 链接"]
    OV2 --> OV3["③ 实现验证<br/>Red → 最小实现 → Green"]
    OV3 --> OV4["④ 变更后增量循环<br/>只处理受影响部分"]
    OV4 -- "需求或实现继续变化" --> OV3
    OV4 -- "验收语义变化" --> OV1
    OV4 -- "最终检查 / 完整交付 / 准备提交" --> OV5["⑤ 最终交付<br/>完整门禁与中文报告"]
    OV5 -- "发现技术问题" --> OV3
    OV5 -- "发现计划外业务影响" --> OV1
    OV5 --> OV6["用户决定是否本地提交<br/>push / PR 另行授权"]
```

### 5.2 阶段一：需求确认与基线

```mermaid
flowchart TD
        A["读取配置和需求资料"] --> B["delivery.py init"]
        B --> C["只读分析相关代码、调用方和已有测试"]
        C --> D["置顶展示已上线业务影响"]
        D --> E["拆分 REQ / BDD / 原子 Then"]
        E --> DOR{"业务含义和验收是否足以确认"}
        DOR -- "否" --> NEED["列出最小缺口并暂停相关范围"]
        NEED -- "资料补齐" --> A
        DOR -- "是" --> F{"用户确认完整需求和旧业务处置"}
        F -- "补充 / 修改 / 删除 / 待定 / 冲突" --> G["分类本轮新增、修改、删除和保留"]
        G --> G1["合并最新完整需求并同步 requirement_file"]
        G1 --> G2["delivery.py init 重新读取"]
        G2 --> G3["展示变化摘要和 requirement_file 路径"]
        G3 --> C
        F -- "无新变化，明确确认" --> B1["delivery.py check-env"]
        B1 --> ENV{"分支、环境和工作区检查通过"}
        ENV -- "否" --> ENVFAIL["说明问题，不自动 stash / 提交 / 清理"]
        ENVFAIL -- "用户处理后" --> B1
        ENV -- "是，保存 Git 基线" --> H["confirm-requirement-update"]
        H --> REV{"需求修订确认有效"}
        REV -- "待定 / 冲突 / 无效" --> REVFIX["修正清单或继续澄清"]
        REVFIX --> C
        REV -- "是" --> FACTS["重新读取 requirement_file<br/>requirement-revision.json<br/>traceability.md"]
        FACTS --> STAGE1["阶段一完成：需求事实已确认<br/>尚未允许编码"]
```

### 5.3 阶段二：拆分测试、确认计划与增量实现

```mermaid
flowchart TD
        FACTS["阶段一输出：需求事实已确认"] --> MAP["映射全部已确认 BDD / Then<br/>执行 init-test-mapping 生成 test-mapping.json<br/>阻塞项保留未验证"]
        MAP --> INPUT{"正式 API / UI 资料状态"}
        INPUT -- "已齐或不适用" --> PLAN["生成唯一 实施计划.md"]
        INPUT -- "晚到但需求明确" --> PROVISIONAL["计划领域模型 / Fake / 需求驱动 UI<br/>标记待正式资料对齐"]
        PROVISIONAL --> PLAN
        INPUT -- "当前范围必须正式联调或像素验收" --> WAITINPUT["请求最小必要输入<br/>只暂停依赖该资料的范围"]
        WAITINPUT -- "其他独立范围继续" --> PLAN
        WAITINPUT -- "资料补齐" --> INPUT
        PLAN --> PC{"用户确认计划"}
        PC -- "修改计划" --> PLAN
        PC -- "确认" --> PCR["delivery.py confirm-plan"]
        PCR --> X{"Figma UI 且使用 XML View"}
        X -- "是" --> Y["figma-android-xml 生成 XML 与资源"]
        Y --> Z["Delivery 执行 UI 产物交接门禁"]
        X -- "否" --> I["按可执行原子 Then 完成 Red → 最小实现 → Green"]
        Z --> I
        I --> J{"编码后下一步"}
        J -- "实现完善 / 正式资料到达且验收不变" --> W["对比临时实现<br/>局部修改 + 受影响测试 + 必要编译"]
        W --> J
        J -- "需求语义或旧业务处置变化" --> K["delivery.py init 生成受影响项修订清单"]
        K --> K1{"用户确认受影响修订"}
        K1 -- "待定或冲突" --> K
        K1 -- "确认" --> K2["confirm-requirement-update<br/>复用原 Git 基线<br/>义务 sha256 变化的映射自动标 STALE"]
        K2 --> K3["回填 test-mapping.json 为 CURRENT<br/>更新同一份实施计划"]
        K3 --> K4{"用户重新确认受影响计划"}
        K4 -- "修改" --> K3
        K4 -- "确认并执行 confirm-plan" --> W
```

### 5.4 阶段三：最终审查、修复与交付

```mermaid
flowchart TD
        J["阶段二输出：编码后下一步"] -- "最终检查 / 完整交付 / 准备提交" --> L["delivery.py route"]
        L --> M["Diff / 质量 / 稳定性 / API 专项"]
        M --> M0{"存在需要修复的问题"}
        M0 -- "否" --> M1{"发现计划外旧业务影响"}
        M1 -- "是" --> REVISE["返回阶段二：确认受影响修订"]
        M1 -- "否" --> N["选择测试层并执行完整回归"]
        N --> O["构建、Lint、JUnit、变异测试(PIT)、Journey 或人工证据"]
        O --> O0{"必需命令或专项失败"}
        O0 -- "否" --> UIQ{"需要独立 UI 验收"}
        UIQ -- "无 UI 影响" --> P["生成 delivery-result.json"]
        UIQ -- "有 UI 且有可比基准" --> UIRUN["用户单独调用 android-verify-ui"]
        UIRUN --> UIRESULT{"UI 验收通过或用户明确豁免"}
        UIRESULT -- "是" --> P
        UIRESULT -- "否" --> FIX
        UIQ -- "有 UI 但无可比基准" --> UIPENDING["记录视觉待对齐或未验证<br/>不冒充像素级通过"]
        UIPENDING --> P
        P --> Q{"delivery_gate.py validate<br/>含测试映射 CURRENT 与变异 survived=0"}
        Q -- "报告或证据缺口<br/>映射 STALE / 缺失<br/>或变异存活" --> FIX["保存证据并分类<br/>最小修复一个根因"]
        M0 -- "是" --> FIX
        O0 -- "是" --> FIX
        FIX -- "需求语义或旧业务冲突" --> REVISE
        FIX -- "代码 / 测试 / 资源 / UI/API 输入变化" --> L
        FIX -- "只重跑专项证据" --> M
        FIX -- "只重跑测试或环境命令" --> N
        FIX -- "仅报告结构或证据引用" --> P
        FIX -- "同一根因三轮仍无法关闭" --> BLOCKED["当前条件阻塞<br/>BLOCKED"]
        Q -- "设备待验" --> DEVICE["本地门禁通过，真机待验证<br/>LOCAL_PASS_DEVICE_PENDING"]
        Q -- "仍有未完成项" --> INCOMPLETE["仍有未完成项<br/>INCOMPLETE"]
        Q -- "当前无法继续" --> BLOCKED
        Q -- "全部完成" --> PASS["全部完成<br/>FULL_PASS"]

    DEVICE --> COMMIT{"用户是否明确要求<br/>按当前真实结论本地提交"}
    INCOMPLETE --> COMMIT
    BLOCKED --> COMMIT
    PASS --> COMMIT
    COMMIT -- "否" --> HOLD["保留工作区等待用户"]
    COMMIT -- "是" --> LOCALCOMMIT["根据真实结论生成本地语义提交"]
    LOCALCOMMIT --> REMOTE["不自动 push / PR<br/>等待用户单独授权"]
    HOLD -- "同一需求后续变化或正式资料到达" --> ITERATE["返回阶段二：局部迭代"]
    REMOTE -- "同一需求后续变化或正式资料到达" --> ITERATE
```

#### 阶段一补充：初始化

仓库只版本化 `profiles/local.example.yaml` 配置结构；真实 `profiles/local.yaml` 和 `requirement_dir` 是用户所有的本机运行输入，由 Git 忽略。首次使用时从示例复制并填写，已有本机文件时不得覆盖、删除或强制提交。`requirement_workspace.mode=rotate` 时，每个新串行需求由 `requirement_workspace.py` 创建独立目录；稳定编号用于机器隔离，中文名称和 `需求说明.md` 用于用户识别。该隔离只减少源码工作区噪声，不降低追溯强度：`delivery.py init` 仍读取真实配置和当前需求，中途重复执行时仍对比最近确认修订并显示变化，完整输入摘要仍使过期 route 和最终证据失效。

#### 阶段一补充：环境与基线

`delivery.py check-env` 校验项目路径、目标分支和干净工作区，在项目外保存当前需求的 Git 起点与需求起点。重复执行只复用原起点；只有用户明确开始新的串行需求时才使用 `--new-requirement` 替换。脏工作区不能直接开启一个新的串行需求。

#### 阶段一补充：需求确认

AI 先根据需求形成初步理解，再只读、定向检查相关项目规则、实现、调用方、共享边界和已有测试，不逐行扫描无关仓库，也不在确认前编码或运行构建。随后在需求说明最前面展示已上线业务影响，根据需求生成稳定的 `REQ-###`、`BDD-###` 和 `BDD-001/T1` 原子 Then。明确修改和必须保护的已有业务进入同一义务集合。

首次确认前，用户每次新增、修改、删除、纠正或改变旧业务处置时，AI 都必须先列出本轮变化摘要；每接受一个答案先合并进最新完整需求、同步 `requirement_file` 并由 `init` 重新读取成功，才回复下一问。默认不在聊天重贴完整需求；“确认，但再增加一项”仍属于需求变化。未变化的临时编号保持稳定，撤回草稿不进入 R1。纯确认后执行 `check-env` 和 `confirm-requirement-update`，再拆分测试、生成唯一 `实施计划.md` 并等待用户确认；`confirm-plan` 成功前不得编码。

#### 阶段二补充：编码与路由

编码遵守已经确认的实施计划和目标项目现状。Figma + XML View 场景先由 `figma-android-xml` 生成纯 UI 资源和 XML，总入口执行交接门禁后接管业务连线；Compose 或非 Figma 场景不调用该 XML Skill。普通完善只做最小修改、受影响测试和必要编译；验收语义变化时确认受影响修订并同步、重新确认计划。不得仅因代码写完就自动执行 `route`。

#### 阶段三补充：最终门禁

用户当前或最初请求明确要求最终检查、完整交付或准备提交时，才执行 `route`，让脚本候选与 Diff Reviewer 的七类语义影响取并集并完成全部必需命令和专项。Diff Reviewer 同时复核编码前登记的旧业务影响；新发现的已有业务调用方或可观察变化必须回到需求确认。随后生成一次性 `delivery-result.json`；`delivery_gate.py validate` 校验证据并从可信结果生成面向用户的中文 `delivery-summary.md`，不运行测试、不修代码。摘要最前面分组显示已上线业务修改、保护项和验证状态；退出码为 0 才允许使用通过结论。最终回复优先展示中文摘要，JSON 只作机器附件。

需求理解、需求变化、编码提示、授权请求、测试结果、失败原因和最终报告统一使用自然中文。机器状态只保留在 JSON、Schema 和原始证据中；文件路径、命令、接口与代码标识保留原文但附中文说明。未知机器状态不得原样显示，原始英文日志必须先提炼中文根因和解除方法。

## 六、需求确认与中途变更

### 6.1 首次确认与确认修订

首次确认前的多轮沟通只收敛同一份最新完整需求，不生成 R1、R2 或删除实现处置；每个接受答案先写回 `requirement_file` 并重新读取，再展示变化摘要、文件路径和待确认点，最后一次纯确认才形成 R1。随后拆分测试并确认唯一实施计划；编码、测试、route 和最终报告重新读取需求文件、修订清单、追溯表和计划。后续变化形成 R2、R3，并使旧计划确认和相关证据自动失效。

### 6.2 中途增加或修改需求

编码中用户补充内容时先判断验收语义：只完善实现且不改变已展示计划五类内容时直接进入局部测试循环；新增、删除或改变业务行为、边界和验收结果时，把补充同步到需求文件，只确认受影响义务，并更新同一份测试映射和实施计划。用户重新确认计划后才执行受影响实现和回归；未确认内容不能进入实现和最终证据。

### 6.3 删除需求

删除已确认内容时必须明确一种处置：

- 删除对应实现；
- 保留兼容实现；
- 停止尚未完成的实现。

没有处置结论时不推进修订，避免需求从文档消失但旧代码无意保留。

### 6.4 串行需求

当前需求未完成时，不把另一个独立需求混入同一 Git 基线。同一需求的增改删和局部重测继续使用原目录、原 Git 基线和未变化的义务 ID；它们不是“下一个需求”。

只有用户明确确认上一需求已经完成或取消并要求开始下一需求时，才使用 `scripts/requirement_workspace.py next`。命令默认输出中文预览，不修改文件；用户确认后追加 `--confirm`。新需求正文必须位于旧活动目录之外，Android 项目必须处于干净状态。脚本保留上一目录，创建 `REQ-日期-序号-中文名称` 独立目录，只更新 `local.yaml` 的活动需求指针，不操作 Android 源码和 Git。

轮换后先执行 `delivery.py init` 并由用户确认新需求，再执行 `check-env --new-requirement` 建立新 Git 基线。项目外需求正文、UI/API 固定证据、测试用例、报告和机器状态均留在对应需求目录，不复用上一需求结果。同一配置只允许一个活动写入窗口；轮换和回收通过单写锁阻断第二个写窗口，失败回滚只处理本轮实际创建或修改的对象。整个需求取消时不生成空义务或通过结论，先由用户决定代码处置。

回收采用“最近数量 + 最短时间”双门槛：当前活动、未完成、近期或状态损坏的需求永不进入自动候选；已经完成/取消的目录还必须超出 `keep_completed` 且超过 `cache_retention_days`。`tempfile` 只使用时间门槛。`next` 预览会列出随本次轮换回收的候选，追加 `--confirm` 才同时授权轮换和回收；独立 `prune` 同样先预览、再用 `prune --confirm`。两条路径都只删除白名单根目录的直接子项，不在需求初始化或交付结束时无条件清空。轮换成功但回收失败属于“新工作区已生效、旧内容待回收”，修复后只重试 `prune`，不得重跑 `next`。

### 6.5 完整输入摘要

最终上下文同时绑定：

- 规范化需求正文；
- 当前已确认实施计划；
- `ui` 配置、链接和本地 UI 资料；
- `api` 配置、链接和本地接口文件；
- 当前确认修订；
- Git 基线和最终代码摘要。

设备、重试次数和 Journey 执行环境属于运行条件，不进入需求摘要，避免制造虚假的需求修订。远程 UI/API 链接只绑定 URL；当前需求涉及已配置的私有 `api.links` 时，优先复用本机 Chrome 登录态，登录/权限阻塞必须请求用户授权后重试，不得静默跳过或脑补。读取成功后登记本地导出、截图或可验证版本摘要，否则远程内容变化风险保持未验证。

### 6.6 接口或 UI 资料晚到

- 需求已经明确时，不因正式接口或设计稿尚未提供而阻断可独立完成的业务开发；根据需求建立领域模型、业务字段、交互状态、临时接口契约、需求驱动的 UI 和 Mock / Fake，并统一标记“待正式资料对齐”。
- 临时实现不能证明正式 endpoint、JSON 字段、错误码或视觉参数。Fake 不进入 release 生产路径；没有设计基准时不声明像素级还原通过。
- 正式资料到达后，先对比现有实现，只调整 DTO、Mapper、正式 DataSource、资源和表现层并重跑受影响测试；资料改变业务语义时才进入需求修订并更新相关 BDD / 测试用例。
- 阶段结果和最终回复分别展示业务实现、正式接口、UI 视觉和测试状态；最终交付沿用现有 API 门禁原因和独立 UI 验收报告，不新增机器状态。不能把“业务已跑通”写成“正式联调或视觉验收已通过”。

## 七、编码与影响路由

### 7.1 风险分层

- `L1`：局部、低风险、单影响面，没有高风险边界。
- `L2`：存在可观察业务变化，或两个以上影响面协作。
- `L3`：支付、金额、鉴权、隐私、迁移、并发、生命周期、权限、后台、硬件、公共 API、R8、反射或核心跨模块链路。
- `BLOCKED`：缺少继续实现必需的业务预期，或当前明确要求正式联调/像素级还原但缺少不可替代的接口契约/设计基准；仅资料晚到且需求足以支撑临时实现时不属于阻塞。

风险按业务后果和调用链判断，不按改动行数判断。

### 7.2 最终 diff 路由

| 变化信号 | 主要路由 |
|---|---|
| Compose、XML、资源、导航和可见页面 | UI 候选、测试路由，UI 验收保持独立 |
| Retrofit、Service、DTO、Request/Response、mapper、网络 Repository | API 契约专项 |
| Room、DataStore、Proto、序列化格式、数据库版本 | 迁移门禁与迁移测试 |
| Manifest、权限、Service、Receiver、后台能力 | 系统和安全隐私候选 |
| Gradle、依赖、variant、R8、反射 | 构建、兼容和稳定性候选 |
| DI、模块边界、公共接口、跨模块调用 | 代码质量和 Diff Review |
| 生命周期、资源、线程、Coroutine、Flow | 稳定性、并发和泄漏审查 |

API 资料缺失且继续正式网络接入会脑补 endpoint 或传输字段时，API 专项可以前置阻断该接入；需求已经明确的领域模型、业务逻辑、Fake 和测试仍按 6.6 继续。通常仍在编码后根据真实实现做最终契约审查。

脚本只负责快速发现候选，不维护所有框架关键词。`android-review-diff` 必须基于当前需求和真实 diff 逐项确认 UI、API、数据、系统、构建、架构和测试影响；即使普通文件名中的 Ktor、SharedPreferences 或权限调用未被正则识别，语义确认仍会进入最终机器门禁。

## 八、自动化测试策略

每个原子 Then 选择最低且足够可靠的测试层，不要求所有需求执行所有测试类型。

先为全部义务确定测试映射和调用方可观察的稳定业务边界，再按一个原子 Then 或不可分割 BDD 逐项完成 `Red -> 最小实现 -> Green`。断言预期来自已确认需求、契约、确定样例或固定事实，不重复生产算法；新增 Mock 优先停在不可控外部边界。只有跨会话的大型需求，或者 `L3` 同时包含多条独立验收链路时，才在现有追溯表中编排纵向切片和依赖；普通需求和单点高风险小改动不增加 Ticket 或文档。

| 需求类型 | 首选验证 |
|---|---|
| Kotlin/Java 纯业务规则、计算、状态转换 | Unit Test |
| ViewModel、Coroutine、Flow、状态机 | Unit Test / Coroutine Test |
| Repository、缓存、数据库协作 | Integration Test / Robolectric |
| Retrofit、DTO、请求字段、错误码 | MockWebServer / Contract Test |
| Room schema 和旧数据升级 | Migration Test |
| Android 生命周期和组件行为 | Robolectric / Instrumentation |
| 稳定、顺序明确的可见 UI 旅程 | Journey / Espresso / Compose UI |
| 设计稿、像素、布局和可访问性 | `android-verify-ui` |
| 设备、硬件、真实权限、动态泄漏 | 模拟器、真机或明确待验证 |
| 无法安全自动化的外部闭环 | 结构完整的人工收据 |

### 8.1 无 UI 需求

Repository、数据库、缓存、算法、后台任务、接口映射和并发逻辑不调用 Journey。使用 Unit、Integration、Contract、Migration、Robolectric 或已有项目测试。

### 8.2 混合需求

把混合需求按原子 Then 拆开。例如“点击保存后写入数据库并显示成功”：

- 点击和可见成功状态由 UI 测试或 Journey 验证；
- 字段映射由 Unit Test 验证；
- 请求参数由 Contract Test 验证；
- 数据库存储由 Integration 或 Migration Test 验证；
- 页面是否符合设计稿由独立 UI 验收验证。

任一测试层只能覆盖自己实际断言的 Then，不能因为一条 Journey 通过就覆盖整条业务。

### 8.3 老项目兼容

识别并沿用项目已有 JUnit4/JUnit5、Robolectric、Mockito、PowerMock、Espresso、Instrumentation runner、自定义 variant 和 Gradle task。不为统一风格迁移测试框架，不升级目标 AGP、Gradle 或 JDK。

## 九、Journey 的定位

Journey 是用户行为旅程工具，不是万能 UI 测试，也不负责视觉还原。

### 9.1 适合场景

- 启动应用、点击、输入、返回和稳定页面跳转；
- 验证明确可见的文本、控件和短业务链路；
- 登录、搜索、创建、编辑等可控主流程；
- 少量关键黑盒回归。

### 9.2 不适合场景

- 精确像素比较和设计稿还原；
- 多指、复杂拖拽、折叠屏和不稳定手势；
- 摄像头、蓝牙、NFC 等硬件闭环；
- 不可控系统弹窗、真实支付、验证码和第三方登录；
- 数据库内部状态、接口字段、后台任务和复杂并发；
- 不稳定的真实后端或生产敏感数据。

### 9.3 两次判断、一次执行

需求确认后，根据 BDD 初判 Journey 为 `FULL/PARTIAL/NONE`；编码完成后再根据真实 diff、入口、前置条件和设备能力终判。只有终判仍分配了验证义务时才执行。

### 9.4 默认 Agent 与可选壳

默认由当前 AI 会话使用 Android CLI/adb 按 XML action 逐步操作和判断。`journey-harness` 是已经通过 Android Studio 官方模板初始化后的可选回退壳，用于老项目无法直接采用新插件的情况；它不升级或修改目标项目。

壳未初始化、没有设备或 Journey 不适用时，不阻断其他本地测试。改用项目已有 UI 测试、其他测试层或完整人工证据，并保留能力损失。

Journey 用例归 `android-test-and-fix`，默认保存在当前需求作用域下。`android-verify-ui` 只复用截图或布局做独立验收，不管理 Journey 用例。

## 十、失败分析与自动修复

失败后先分类，再决定修改对象：

| 分类 | 含义 | 处理方向 |
|---|---|---|
| `REQUIREMENT_BLOCKED` | 缺少继续当前范围必需的业务预期，或明确要求正式联调/像素级验收却缺少不可替代的契约/基准 | 请求最小必要输入；需求足以支撑临时实现时按 6.6 继续，不冒充正式通过 |
| `ENVIRONMENT_FAILED` | SDK、Gradle、设备、网络或测试环境失败 | 修环境或使用等价路径，不改生产逻辑 |
| `TEST_FAILED` | 用例、fixture、数据、Given 或断言有误 | 只修测试侧并重新验证 |
| `IMPLEMENTATION_FAILED` | 生产代码与已确认需求不符 | 做最小生产修复并回归 |
| `UNKNOWN` | 当前证据无法定位根因 | 继续采证，仍无法定位则请求输入或阻断 |

修复闭环：

1. 保留首个失败命令、退出码、日志和报告。
2. 偶现、性能回退、根因不明或首次修复未关闭时，先实际运行能够捕获用户原始症状的最小反馈命令；明确编译、Lint 和单测失败不增加此步骤。
3. 一次只处理一个当前主根因。
4. 优先使用对应专项能力和项目已有工具。
5. 专项能力不足时，由 AI 根据代码和真实日志进行替代分析。
6. 只有证据指向生产代码时才修改生产代码。
7. 每轮修复后重跑失败项和受影响回归集。
8. 同一根因连续三轮仍无法关闭时停止碰运气，说明需要的资料、权限、设备或人工动作。

禁止通过删除测试、注释断言、扩大容差、添加无依据 sleep、排除 Gradle task、修改 baseline 或把失败改成人工项来造绿。

## 十一、机器证据与防假绿

### 11.1 单 gate 执行收据

每条最终命令通过 `execution_evidence.py` 执行，并记录：

- 唯一 evidence ID 和唯一 gate；
- 不可覆盖的 `attempt-001/002/...`；
- 参数数组、执行目录和起止时间；
- 命令退出码、脱敏 stdout/stderr；
- JUnit testcase、Android Lint XML/SARIF，或项目已有 Kotlin/Java 工具的通用 SARIF；
- 日志、报告和产物 SHA-256；
- 当前需求、完整输入、Git 基线和最终代码摘要。

### 11.2 gate 证明边界

- `android-build`：真实 Gradle `assemble*` 或 `bundle*` 收据。
- `android-lint`：真实 Gradle `lint*` 收据和本轮 XML/SARIF；Fatal/Error 即使零退出也阻断。
- `android-test-and-fix`、`android-data-migration`：实际执行数大于零且无失败的本轮 JUnit，或允许的 Agent/人工路径。
- API、UI/A11y、安全、泄漏和性能：对应专项 capability；允许人工的动态项必须使用完整人工收据。
- Diff、代码质量和稳定性核心 gate：对应专项 Skill 的统一结果。

普通成功命令不能通过填写同名 `gate_id` 冒充专项证据。

### 11.3 原子 Then 证据

普通自动覆盖必须把 `BDD/Then` 映射到 JUnit 中真实存在且状态为 PASS 的 testcase。非零测试总数不能代替具体映射。Agent Journey 必须记录实际 action/check、执行数量和布局/截图产物。

### 11.4 人工收据

人工验证必须记录执行人、带时区时间、设备/环境、逐步操作、预期、实际、状态及产物摘要；确实没有产物时说明原因。计划以后执行不能写成 `COVERED_MANUAL`。

### 11.5 已阻断的假绿

- 命令没有实际执行或只有手填 `exit_code=0`；
- 测试/迁移没有 JUnit、零测试、失败或全部 skipped；
- Then 没有真实通过 testcase；
- Lint 报告仍有 Fatal/Error；
- 静态分析命令返回零，但 SARIF 仍有新增、更新或来源不明 Error；
- 稳定性结果漏写六条静态不变量、与当前代码绑定的控制面审计/候选处置、实际文件范围或稳定问题编号；
- 一份收据跨 gate 复用或任意命令冒充专项；
- 同一 ID 重跑覆盖第一次失败；
- 报告、日志或产物被修改；
- 测试后代码、需求修订、实施计划或 UI/API 输入又发生变化；
- 空人工说明、空设备待验项或无关证据占位。

## 十二、最终结论与 Git

`delivery-result.json` 是当前需求和最终代码的一次性交付结果，不是通用 phase/state 状态机。

| 结论 | 含义 |
|---|---|
| `FULL_PASS` | 所有必需 Then 和 gate 都有当前、有效、可复核证据，没有待验证能力 |
| `LOCAL_PASS_DEVICE_PENDING` | 本地门禁全部完成，但存在真实设备待验项，并引用同能力未验证证据 |
| `INCOMPLETE` | 仍有未完成项，报告如实保留缺口 |
| `BLOCKED` | 缺少关键需求、环境、权限、设备或存在无法关闭的根因 |

核心通过 gate 包括 Diff Review、代码质量、稳定性、测试与修复、构建和 Android Lint。API、迁移、UI/A11y 和安全隐私由最终 route 候选决定是否成为条件 gate。

没有真机不自动否定已经完成的本地范围，也不能把动态能力写成已通过。`LOCAL_PASS_DEVICE_PENDING` 不是 `FULL_PASS` 的空别名。

流程验证通过后不会自动提交 Git。只有用户明确要求提交时，才检查本地 diff、生成语义化提交信息并提交；push 和 PR 仍需要单独授权。

## 十三、用户需要提供什么

通常只需要：

- 目标项目路径，可以来自全局或本机配置；
- 当前需求文档；
- 可选 UI 设计链接、截图、资源；
- 可选 API 文档链接或本地契约文件；
- 需求本身缺少关键业务含义时的澄清；
- 真机、账号、权限或人工动作确实不可替代时的协助。

用户通常不需要手写 Journey XML、action/step、Gradle task、测试用例或最终 JSON。AI 应从已确认需求和真实项目能力中分析生成；无法可靠确定时才请求最小必要输入。

## 十四、明确能力边界

### 14.1 远程资料

需求输入摘要自动哈希本地 UI/API 文件和配置中的远程 URL，但不访问网络。Figma MCP 负责结构化设计数据，`figma_workflow.py fetch` 只提供 PNG 视觉基准；本轮采用的截图应保存到 `<requirement_dir>/ui/` 或登记到 `ui.screenshots` / `ui.directory`。这样同一 Figma URL 内容变化后，新截图 SHA-256 会使旧 route 和交付证据失效；只有 URL 而没有本地基准时，必须记录该证据缺口。

### 14.2 设备能力

没有设备时无法完成真实 UI/A11y、动态泄漏、部分性能、权限和硬件闭环。流程会继续全部本地与模拟器可验证项，并把剩余范围标成设备待验，而不是伪造通过。

### 14.3 未知工具与老项目

不默认安装 Maestro、Appium、LeakCanary、自定义 Lint 或其他重型工具。优先使用项目已有能力和 Android 自带 Gradle Lint；工具不存在时使用等价验证或保留未验证原因。

### 14.4 绝对零风险

任何流程都不能诚实承诺所有 Android 需求绝对没有 Bug。当前目标是显著降低遗漏、回归、泄漏和耦合风险，并确保每个剩余风险都能被看见、复核和追踪。

## 十五、规则来源与维护方式

### 15.1 运行时规则唯一归属

| 规则范围 | 唯一运行时来源 |
| --- | --- |
| 跨 Skill 底线 | `_shared/android-global-rules.md` |
| 需求确认、用户可见五步、内部三阶段、Git 基线、需求修订和最终交付 | `android-implement-and-verify/SKILL.md` |
| 测试选择、Red-Green 小闭环和 Journey | `android-test-and-fix/SKILL.md` |
| 专项检查 | 对应专项目录的 `SKILL.md` |

`SIMPLE_USAGE.md`、本文、`references/open-source-design-rationale.md`、行为评测和其他 `references/` 只负责使用说明、设计取舍、导航或验证，不是第二运行时规则来源。`android-implement-and-verify/references/*.schema.json` 只定义稳定机器契约。

仓库级 `.agents/AGENTS.md` 是 AI 维护入口，只强制维护者读取本项目共享规则并执行项目声明的验证，不保存第二套 Android 运行规则。

规则冲突时按以下顺序处理：目标项目更严格的 `AGENTS.md` / `CONTRIBUTING.md` → `_shared/android-global-rules.md` → 当前 Skill。无法确定时暂停说明，不自行选择宽松规则。

### 15.2 维护约束

- 维护、扩展或质疑流程前，先读取 `references/open-source-design-rationale.md`，确认现有设计依据、采用/拒绝原因和长期不变量，避免后续 AI 重复推翻已经确认的取舍。
- 新的跨 Skill 约束只写入 `_shared/android-global-rules.md`。
- 新的完整交付步骤只写入 `android-implement-and-verify/SKILL.md`。
- 专项细节只写入对应 Skill，低频细节放入 `references/` 或 `assets/`。
- 本文档只维护整体理解和导航，不代替机器契约或专项规则。
- 新增或修改 Python 文件时，主动补齐中文文件简介、类/函数/测试方法用途和必要的核心逻辑注释；简单赋值和显而易见分支不添加废注释，注释必须与实现同步更新。
- 修改 Skill、脚本、配置、Schema、路由、门禁或用户可见流程后，交付前主动核对并最小同步职责对应的运行时来源、整体说明、使用导航、设计依据和测试；不相关文档不改，说明文档不复制第二套执行规则。
- 修改共享规则、任一 Skill、本文、`SIMPLE_USAGE.md` 或设计依据后，必须从本仓库根目录运行 `python3 -m unittest scripts.tests.test_skill_rule_ownership -q`；失败不得完成维护。该检查阻止第二运行时来源和上下文无边界膨胀，不接入普通 Android 需求流程。
- 修改 Skill、路由或门禁后运行行为评测、单元测试、Schema 校验和 Skill 结构校验。
- 只有真实需求暴露可复现问题时再做最小修复，不进行没有证据的无限扩展。

一句话概括：这是一套“AI 可以执行，但不能自说自话”的 Android 需求交付体系。它允许 AI 根据具体项目智能选择路径，但在需求、改动范围、测试证据、风险结论和 Git 操作上设置不可越过的边界。
