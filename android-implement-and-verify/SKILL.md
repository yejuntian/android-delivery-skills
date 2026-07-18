---
name: android-implement-and-verify
description: Android 需求实现与闭环验证总入口。用于完整完成 Android 新需求、需求变更、Bug 修复和功能迭代：读取需求/UI/接口资料，确认 BDD，物化测试，编写代码，按实际 diff 编排范围、接口、质量、稳定性和 UI 专项检查，驱动测试失败与 P0/P1 自修复，直到全绿门禁或明确受阻。用户要求完整开发、实现并验证、修到测试通过或交付一个 Android 改动时使用；仅需单项审查时改用对应专项 Skill。
---

# Android 需求实现与闭环验证

## 共享规则

执行本 Skill 前，必须先遵守 `../_shared/android-global-rules.md`。本 Skill 启用完整交付模式：本次需求范围内的问题默认自修复并重验，不采用专项 Skill 的 standalone report-only 默认值。

维护、扩展或重构本流程时读取 `../references/open-source-design-rationale.md`；修改 Skill、路由或门禁后按 `references/delivery-eval-scenarios.md` 做行为评测。编码后出现接口、数据、UI、生命周期、性能或安全候选时，按需读取 `references/conditional-capability-gates.md`；出现 UI 与业务混合、Journey 只能覆盖部分步骤、测试层选择或证据缺口时读取 `../android-test-and-fix/references/adaptive-test-routing.md`。物化中途需求增删改时遵守 `references/requirement-revision.schema.json`，生成最终机器报告时遵守 `references/delivery-result.schema.json`。这些资料都不是日常需求执行时的固定上下文。

## 定位

这是 Android Skills 套件的总指挥，用来处理一次完整 Android 需求交付。标准路径是：读取资料 → 需求理解 → 用户确认 → 物化测试 → 编码 → 执行测试与审查 → 失败自修复并重跑 → 全绿门禁 → 最终交付。

本 Skill 不把专项 Skill 固定插在编码前。需求确认后不再默认输出一轮分析报告；只有遇到阻塞或用户明确要求“先分析别改”时，才暂停并输出对应分析。

## 职责边界

- **负责**：需求确认、BDD、测试物化、编码、动态路由、自修复、重验和最终门禁。
- **调用**：完整实现需求、修复 Bug、完成迭代，或用户要求“实现并验证到可交付”。
- **不负责**：自动发布、推送、上线、操作生产数据或未经授权提交 Git。
- **与专项 Skill 的关系**：本 Skill 是唯一总入口；专项 Skill 提供诊断与验证结果，不另行编排完整交付。

专项 Skill 的默认位置：

- `android-review-diff`：编码后审查实际 diff、影响范围、无关改动和回归风险；只有变更范围不清或用户要求先分析时才前置。
- `android-verify-api-contract`：编码后审查接口实现和 OpenAPI 是否符合契约；只有关键接口资料缺失、继续写会脑补字段或 endpoint 时才前置。
- `android-verify-ui`：独立手动收尾能力；总入口检测到 UI/A11y 变更时只提示用户单独调用，不自动执行视觉或人工验收。
- `android-test-and-fix`：BDD 确认后物化自动测试，编码后执行测试矩阵、构建、单测、lint、迁移、A11y、Journey、截图或仪器测试；失败时驱动自修复。
- `android-audit-stability`：编码后检查崩溃、动态泄漏、性能、安全隐私、ANR、协程、生命周期和 Android 版本兼容。
- `android-review-code-quality`：编码后检查架构一致性、最小修改、资源规范、重复逻辑和测试覆盖。

## 外部智能体与工具调用策略

总原则：需求确认前保持轻量；需求确认后直接编码；编码后再按实际改动调用审查和验证能力。

- 需求理解：只读取需求文档、截图、链接和用户补充；默认不调用 Android CLI、Gradle、adb 或 Firebase MCP。
- 需求确认后：开始编码。编码前不固定输出 `android-review-diff`、`android-verify-api-contract`、`android-verify-ui`、`android-test-and-fix`、稳定性或代码质量报告。
- 编码过程中：内部识别项目事实、复用现有封装、控制最小修改范围；除非遇到阻塞，否则不打断用户。
- 阻塞处理：如果缺少关键 UI / 接口 / 字段 / 枚举 / 业务规则，继续编码会变成猜测或高风险改动，必须暂停说明缺口并请用户确认下一步。
- Android CLI / Gradle / adb：只在真实构建、安装运行、单测、lint、仪器测试、截图、logcat、设备兼容验证时使用；不可用时退回项目已有 Gradle/adb 命令或标记未验证。
- Firebase MCP：仅当需求或问题涉及 Firebase、Crashlytics、Remote Config、Analytics、AB 实验、线上崩溃、线上配置或埋点分析时使用；未配置、无权限或无法访问时必须说明。
- 线上或设备验证结果不得伪造；没有实际运行就只能写“未验证”。

## 统一故障处理与 AI 接管

任一实现、构建、测试、审查或外部工具失败时，使用共享规则中的五类失败和四个处理状态，不新增场景关键字分支：

1. 先冻结原始证据：触发步骤、命令、退出码、首个有效根因、关键日志/报告路径、当前 diff 与相关环境事实。
2. 将当前主因标为 `REQUIREMENT_BLOCKED`、`ENVIRONMENT_FAILED`、`TEST_FAILED`、`IMPLEMENTATION_FAILED` 或 `UNKNOWN`；证据变化时重新分类并记录原因。
3. 按失败事实选择对应专项 Skill/智能体和最小外部工具集，状态记为 `SPECIALIST_ACTIVE`。Android CLI、Gradle、adb 等只采集或验证工程事实，不代替业务判断。
4. 专项能力不可用或执行失败时，先按共享模板提示用户，再判断能否由通用 AI 接管。不得静默跳过专项能力，也不得把工具失败直接归因于生产代码。
5. 只有证据充分、修改仍在已确认需求内、操作低风险且可以等价重验时，才进入 `AI_FALLBACK_ACTIVE` 并执行最小修复；`UNKNOWN` 或关键证据不足时禁止修改生产代码。
6. 缺少资料、权限、设备动作或用户决策时进入 `USER_INPUT_REQUIRED`；专项能力和 AI 均无法关闭、同一根因连续 3 轮失败或必需门禁无等价验证时进入 `BLOCKED`。
7. 修复后先重跑直接失败项，再跑受影响回归集并重新执行路由。替代验证损失的能力必须标为“未验证”，不能计入全绿门禁。

通用 AI 是有边界的诊断与修复兜底，不是外部工具模拟器。SDK/CLI 更新、Gradle 大版本升级、清数据、卸载、真实支付/删除、生产环境写操作等仍按共享规则请求用户授权。

## 动态输入

默认读取 Skill 套件根目录下的 `profiles/local.yaml`。用户不需要每次重复说明“读取 local.yaml”。

优先级：

1. 用户本次对话中明确提供的项目路径、分支、需求文档、UI 链接、接口链接。
2. 用户指定的配置文件，例如 `.codex/current-requirement.yaml`。
3. 默认配置：`profiles/local.yaml`。

支持动态输入：

- 定位参数：`project_path`（项目路径）和 `branch`（目标分支）。这是后续所有编码、测试和验证的执行上下文。
- 公共路径：`workspace_root`（本机工作区根路径）和 `requirement_dir`（当前需求资料目录）。
- 固定需求文档：`requirement_file`，只表示需求正文、评审记录和验收标准来源，不强制包含 UI 或接口资料。
- 需求资料：需求描述、Jira、TAPD、飞书、语雀、Confluence、GitHub Issue。
- UI 资料：Figma、蓝湖、即时设计、摹客、MasterGo、截图、UI 截图目录 `ui.directory`、PDF、图片、字体、动效、资源 zip。
- 接口资料：Swagger、OpenAPI、Apifox、YApi、Postman、Markdown 接口文档、后端字段说明。
- 项目环境：模块名、build variant、server env、packageName、目标设备、测试环境。
- 验证要求：是否跑构建、单测、lint、UI 测试、截图对比、logcat 扫描。
- 交付策略：直接实现、仅分析、只做 UI 骨架、只做 mock、完整实现、只报告风险、允许修复。

不得把任何公司内部链接、账号、Token、密钥或业务规则写死进 Skill。

路径解析规则：

- `workspace_root` 是公共路径根目录。
- `requirement_dir` 如果是相对路径，基于 `workspace_root` 解析。
- `requirement_file`、`ui.directory`、`ui.screenshots`、`ui.assets` 如果是相对路径，优先基于 `requirement_dir` 解析。
- 用户本次对话中提供的绝对路径优先，不受上述规则影响。

需求正文读取规则：

- `delivery.py init` 只读取 `.docx`、`.md`、`.markdown` 和 `.txt`；PDF 可作为 UI 资料，但作为 `requirement_file` 时先转换格式。
- DOCX 使用 Python 标准库读取 OOXML 正文；文件损坏或结构不支持时重新导出，不要求额外安装文档解析库。
- 文件不存在、为空、损坏或格式不支持时，报告最终绝对路径、失败原因和修正方式后停止需求判断；不得搜索其他同名文件或脑补正文。

## 外部资料读取策略（非终止）

在需求理解前先尝试读取外部链接，但不要把“链接需要登录/授权”作为默认终止条件。

读取顺序：

1. 先读本地需求文档、截图目录、资源目录和接口文件。
2. 再尝试 Figma MCP / Figma REST API / 平台 MCP / 导出接口。
3. 再尝试浏览器可见页面和公开网页直读。
4. 哪条路径可用就使用哪条路径；不可用路径只记录失败和风险。

执行规则：

- 外部链接可读时，纳入资料来源。
- 外部链接不可读时，记录链接、来源、失败类型和已尝试方式，但继续使用其他可用资料进入需求理解。
- 只有当链接是唯一关键资料，且没有任何本地文档、截图、资源、接口文件或用户文字可替代时，才暂停请求用户补充资料或授权。
- 用户明确表示“哪个行得通就走哪个”“先用现有资料”“跳过这个链接”“先 mock”时，不得继续卡在授权流程。
- Figma 优先级：Figma MCP 结构化读取 → 本地离线标注（`ai-skills/tempfile/[file_key]_[node_id]_spec.json`，读取前先检查 `source.exported_at` 新鲜度）→ `FIGMA_TOKEN` 环境变量驱动的 REST API → 本地截图/资源包 → 浏览器可见页面 → 标记未验证。
- 接口优先级：本地 OpenAPI/Postman/YApi 导出 → 平台 MCP/API → 浏览器可见页面 → mock/fake/sampledata → 标记未验证。
- 不得读取、保存或要求用户提供 Cookie、账号、密码；Token 只能来自环境变量或本机安全存储，且不得写入仓库或日志。

外部资料读取失败时输出：

```text
外部资料未读取：
- 链接：
- 来源：
- 失败类型：
- 已尝试：
- 是否阻塞：是/否
- 降级依据：
- 剩余风险：
```

## 需求质量与追溯

### 稳定 ID 与场景门禁

- 为每条已确认需求分配稳定 `REQ-001`，为可观察验收场景分配 `BDD-001`，为可执行测试分配 `TEST-001`；同一需求内不得因排序或补充内容随意改号。
- 需求确认前检查主流程、备选流程、异常流程、恢复流程和非功能约束。缺少某类场景时标记“待确认”或“不适用 + 原因”，不得为了凑数量脑补。
- 只询问会改变实现、验收或风险判断的问题，最多 5 个并尽量一次确认完成；关键业务含义仍不明确时必须阻塞，不用问题数量限制掩盖缺口。
- 已确认需求必须清晰、无冲突且可通过可观察结果验收；不能从代码、工具输出或常见做法反推未写明的产品规则。

### 当前需求追溯表

- 默认维护 `<requirement_dir>/test-cases/traceability.md`，除非用户或目标项目指定其他同职责路径；它是当前需求交付物，不是跨需求缓存或状态机。
- 表格列为：`REQ-ID | 来源/验收 | BDD-ID/Then | 影响面/风险 | 实现文件 | TEST-ID/类型 | 必需性 | 命令 | 证据/状态`。
- 需求确认时把复合 Then 拆成 `BDD-001/T1` 形式的原子验证义务，填写来源、初步影响面、风险和必需性；编码与验证后补齐实现、测试、命令、新鲜证据和覆盖状态。同一 BDD 可由多个测试层共同覆盖，不建立跨需求状态机。
- 所有已确认 `REQ-ID` 都必须有实现或明确“不需要代码”的依据，并映射到测试或可复现人工验收。需求映射率必须为 100%；这是需求覆盖，不等于代码行覆盖率。

### 中途需求修订

- `<requirement_dir>/test-cases/requirement-revision.json` 是 AI 物化、用户审阅的修订清单；结构必须符合 `references/requirement-revision.schema.json`，并绑定脚本输出的 `requirement_id` 和 `base_revision`。
- 同一需求逐项使用 `ADDED/CHANGED/REMOVED/UNCHANGED/SUPERSEDED`；决策使用 `CONFIRMED/PENDING/REJECTED/CONFLICT`。`PENDING/CONFLICT` 只保存候选且不推进版本，`REJECTED` 不进入当前总需求。
- `REMOVED + CONFIRMED` 必须明确 `REMOVE_IMPLEMENTATION/KEEP_COMPATIBILITY/STOP_UNFINISHED_WORK`；`SUPERSEDED` 必须在同轮指向一个已确认的新增 Then。
- 每轮必须分类全部既有有效 Then 和上轮待定项；未变化项保留 ID。只在聊天中确认的变化先同步到 `requirement_file`，不得让聊天成为唯一事实来源。
- 只有用户确认正文语义完全不变时才允许 `format_only=true`，并要求全部 Then 为 `UNCHANGED`；该操作同步正文摘要但不推进语义修订号。
- `confirm-requirement-update` 只更新最近确认正文、修订号、有效义务和修订历史，不读取或修改 Git。新的串行需求必须完成当前需求后，在干净工作区重新执行 `check-env`。

## 影响面识别与路由

需求理解阶段必须先判断本次需求影响面，并在“当前需求理解”中输出：

- UI：是否涉及页面布局、资源、文案、状态展示、交互、Adapter、Compose/XML。
- 接口契约：是否涉及 endpoint、请求参数、响应字段、DTO、mapper、Repository 网络层、缓存字段。
- 业务逻辑：是否涉及规则判断、状态流转、排序筛选、权限判断、计费、实验开关、数据计算、入口条件。
- 数据存储：是否涉及数据库、缓存、DataStore、SharedPreferences、文件、迁移或旧数据兼容。
- 系统能力：是否涉及权限、通知、后台任务、文件、WebView、DeepLink、系统版本兼容。

如果某一类影响面明确未涉及，编码后不得强行调用对应专项审查，只需在最终报告中说明“未涉及，已跳过”。

编码后的 `route` 另行输出 UI、接口、数据、系统、构建、架构和测试七类工程候选。候选只提示需要复核的证据：API 候选增加 `android-verify-api-contract`；数据、系统、构建、架构和测试候选进入既有 diff、质量、稳定性和测试职责，不为它们新增万能 Skill，也不由脚本直接下业务结论。

第二轮条件能力继续由现有 Skill 承载：OpenAPI 归接口契约，动态泄漏/性能/运行时安全归稳定性，迁移和自动化 A11y 归测试，视觉与人工 A11y 归独立 UI 验收。每项记录触发依据、适用性、工具、执行证据、能力损失和结论；详细边界见 `references/conditional-capability-gates.md`。

### 风险自适应与两次判定

- 需求确认后初判 `L1/L2/L3/BLOCKED`：`L1` 为局部单影响面且无高风险边界；`L2` 为可观察业务变化或两个以上影响面协作；`L3` 由支付/金额、鉴权/隐私、迁移、并发、生命周期、权限/后台/硬件、公共 API、R8/反射或核心跨模块链路触发；关键预期或契约缺失时为 `BLOCKED`。
- 风险根据业务后果、边界和调用链判断，不按代码行数判断。初判只决定测试准备，不得因此提前运行设备或 Journey。
- 编码后根据最终 diff、调用链、variant 和可执行前置条件终判。发现额外影响时自动升级；只有证据证明影响收敛时才降级，并在追溯表说明原因。
- 选择能够证明每个原子 Then 的最低且足够测试层；UI 与业务混合需求必须拆层，任何单一工具通过都不能覆盖它没有断言的义务。

### 轻量 diff 触发规则

编码后必须基于实际 diff 快速复核影响面，不做全量矩阵分析，只判断是否触发专项审查：

- 修改 `res/layout`、`res/drawable`、`res/values`、Activity、Fragment、Adapter、Composable，且存在设计稿、截图或可对比基准：提示用户单独运行 `android-verify-ui`，不加入自动队列。
- 修改 UI 相关文件但没有设计稿、截图或可对比基准：跳过设计稿一致性验证，只在变更审查、稳定性审查或代码质量审查中做必要的 UI 基础检查。
- 修改 Api、Service、Request、Response、DTO、mapper、网络 Repository、缓存字段：触发 `android-verify-api-contract`。
- 修改 Entity、Dao、Database、DataStore、SharedPreferences、缓存结构：触发数据兼容检查。
- 修改 AndroidManifest、权限、通知、后台任务、WebView、DeepLink、文件访问：触发系统能力和版本兼容检查。
- 修改 Gradle、version catalog、ProGuard/R8 或 build-logic：触发构建兼容、依赖解析和模块方向检查，不自动升级版本。
- 修改 DI Module/Component、模块 API/impl 边界或项目依赖：触发架构边界检查；修改测试文件时复核断言有效性和追溯覆盖。
- 仅修改 if/when 判断、状态计算、排序筛选、权限条件、开关逻辑：按业务逻辑路径处理。

如果需求判断为未涉及 UI / 接口，但实际 diff 修改了相关文件，必须重新标记影响面并说明原因；否则按未涉及跳过，不展开额外报告。

### 路由规则

- 仅业务逻辑变更：
  - 必须关注：`android-review-diff`、`android-test-and-fix`、`android-audit-stability`、`android-review-code-quality`。
  - 默认跳过：`android-verify-ui`、`android-verify-api-contract`。
  - 除非业务逻辑改变了 UI 状态展示，否则不做 UI 还原验证。
  - 除非业务逻辑改变了接口字段、请求参数、DTO、mapper、Repository 网络行为或缓存结构，否则不做接口契约审查。
- UI 变更：
  - 有设计稿、截图或可对比基准时提示单独运行 `android-verify-ui`。
  - 没有设计稿、截图或可对比基准时跳过设计稿一致性验证，并说明“设计资料缺失，未验证与设计稿一致”。
  - 由 `android-test-and-fix` 根据业务需求、已确认 BDD 和实际 diff 自动判断 Journey 适用性，不向用户询问测试工具选择。只有布局、颜色、字号、间距或资源变化时标记 `SKIPPED_VISUAL_ONLY`；涉及点击、输入、导航、可见状态流转或系统交互时，根据原子 Then 分配聚合整条 BDD 的 `FULL/PARTIAL/NONE`，只为 Journey 可稳定覆盖的部分生成并执行用例。
  - 如果只是 UI 展示，不涉及接口字段或请求逻辑，跳过 `android-verify-api-contract`。
- 接口 / 数据契约变更：
  - 必须包含 `android-verify-api-contract`。
  - 如果接口变更影响 UI 状态展示，提示单独运行 `android-verify-ui`。
- 数据存储 / 缓存变更：
  - 必须额外关注旧数据兼容、迁移、默认值、清缓存、降级路径和回滚风险。
- 系统能力变更：
  - 必须额外关注 Android 版本兼容、权限降级、生命周期和设备验证。

## 完整工作流

这是一个由 `delivery.py` 三阶段命令编排器驱动的闭环交付工作流。它只持久化当前需求 Git 基线，不维护通用状态机。不得在测试或审查失败后只输出报告并结束。

### 执行手册

请严格按照以下三个阶段、通过运行 Python 脚本推进流程。**每次运行脚本后，必须严格遵循终端输出中带有“👉 AI 指令”的提示内容。**

#### 阶段 1：初始化需求理解

首次使用时从 `workspace_root` 安装依赖：

```bash
python3 -m pip install -r ai-skills/android-delivery-skills/requirements.txt
```

然后运行：

```bash
python3 ai-skills/android-delivery-skills/scripts/delivery.py init
```

**AI 动作**：脚本会输出需求上下文。分配稳定 `REQ-###` / `BDD-###`，检查主流程、备选、异常、恢复和非功能场景，提炼足以覆盖真实需求的 **BDD (Given/When/Then)** 验收标准；把复合 Then 拆成 `BDD-001/T1` 形式的原子验证义务，初判影响面与 `L1/L2/L3/BLOCKED`，并同时输出最小修改预览。BDD 和 Then 数量服从实际需求，不为凑数量脑补场景；最多一次提出 5 个真正影响实现或验收的问题。

同一需求编码中途再次运行 `init` 时，读取最近确认需求修订和现有追溯表，输出增改删、替代和逐项确认决策。保留未变化的 REQ/BDD/Then ID；修改和新增项重新确认，删除项选择实现处置。用户明确开始新的串行需求时不沿用旧 ID；`init` 和 `confirm-requirement-update` 均不修改 Git 基线。
**DoR (准备就绪) 门禁**：如果需求缺少继续实现所必需的业务含义、边界条件或报错证据，列出缺口并暂停请求补充；能够明确表达一个真实场景时，不得仅因条目少而阻塞。

最小修改预览中的每个新增或改动组件必须附轻量架构边界卡片：`组件/文件 | 职责 | 输入 | 输出 | 依赖方向 | 复用点 | 明确不修改范围`。同一组件的相关文件可以合并一行，避免文档膨胀。卡片服从目标项目现有架构，不用于强推分层、拆模块或技术迁移。需求确认且 `check-env` 成功建立基线后，在 `<requirement_dir>/test-cases/traceability.md` 建立追溯表前半部分，不能让追溯文件反过来触发脏工作区门禁。
输出完毕后，**必须立即结束当前回合，等待用户确认**。绝不能直接开写代码。

#### 阶段 2：测试左移、环境检查与编码

在用户明确回复“确认”、“可以开始做”之后，运行以下命令：

```bash
python3 ai-skills/android-delivery-skills/scripts/delivery.py check-env
```

**AI 动作**：环境检查只在目标分支和工作区干净时一起建立当前需求 Git 基线与需求起点；任一失败都不进入编码。检测到已有改动时停止，不自动 stash、提交或清理。随后按 `references/requirement-revision.schema.json` 把用户已确认的全部原子 Then 写入 `<requirement_dir>/test-cases/requirement-revision.json`，并执行：

```bash
python3 ai-skills/android-delivery-skills/scripts/delivery.py confirm-requirement-update
```

退出码 `0` 才表示最新版总需求已确认并允许编码；`2` 表示仍有 `PENDING/CONFLICT`，继续澄清而不覆盖上一确认版本；`1` 表示清单、路径、版本或同步关系无效。编码中途发生变化时重复 `init → 用户确认 → 更新修订清单 → confirm-requirement-update`，始终保留最初 Git 基线。修订确认后遵守以下规约：
1. **先物化测试**：把每个已确认 `BDD/Then` 映射为测试清单；项目具备测试框架时，编码前生成可编译的测试骨架和断言。纯业务逻辑至少覆盖正常、边界、异常和回归路径；UI 与业务混合场景拆给能够证明行为的最低且足够测试层。Journey 此时只根据原子 Then 分配做整条 BDD 的 `FULL/PARTIAL/NONE` 候选初判，并为可覆盖部分生成用例草稿，不启动壳；编码后结合实际 diff 终判，仍有分配项才执行。`android-verify-ui` 只负责后续视觉验收，不得只输出 BDD 文本。
2. **主动检索**：动笔前，主动用搜索工具在项目中寻找同类组件、Base 类和测试范式。
3. **UI 逻辑接管 (最小化修改)**：如果前置步骤生成纯 XML，主动补充对应的 Kotlin ViewBinding 和业务代码。
4. **首次验证**：编码后运行受影响测试、`assemble` 和 `lint`。命令必须按项目模块与 variant 动态选择。
5. **自修复**：任一项失败，按“统一故障处理与 AI 接管”保存证据并分类，确认根因后只修改对应的生产代码、测试或环境配置，再重跑失败项及相关回归集。禁止删测试、弱化断言、跳过任务或用假数据掩盖失败。
6. **循环上限**：同一根因连续 3 轮未关闭才进入 `BLOCKED`；报告失败分类、原专项能力/工具、命令、退出码、关键日志、AI 替代与能力损失、已尝试修改和所需输入。
7. **同步追溯**：编码和验证过程中把最终实现文件、`TEST-###`、真实命令和证据补入当前需求追溯表，不把上一需求或中间轮次结果复用为完成证据。

#### 阶段 3：审查、自修复与交付门禁

代码写完的回合结束后，在紧接着的新回合里，运行以下命令：

```bash
python3 ai-skills/android-delivery-skills/scripts/delivery.py route
```

**AI 动作**：脚本只分析 `check-env` 记录的当前需求 Git 基线之后的 diff，并输出专项审查与测试顺序。逐个调用，每项输出必须进入闭环，而不是止于报告。
- Git 分支、工作区、committed/staged/unstaged/untracked、`A/M/D/R` 状态、真实修改片段和最终代码摘要由 `scripts/git_changes.py` 只读收集；`delivery.py` 只消费结果并编排路由，不得在任一脚本中混入对方职责。
- 一次只查一项。
- 不要自行脑补脚本未列出的审查项。
- P0/P1 发现后立即修复，并从受影响的最小测试集开始重跑；低风险 P2/P3 可修复时一并关闭。
- 修复导致 diff 变化时重新执行 `route`，直到路由结果稳定。
- 最后执行 `android-test-and-fix` 的完整回归门禁；UI 变更时在报告中提示用户另行调用 `android-verify-ui`，不得在自动 route 中执行。
- `android-test-and-fix` 在此阶段先根据最终 diff 终判风险和测试层，再根据原子 Then 分配聚合每条 BDD 的 Journey `FULL/PARTIAL/NONE`；需求阶段的候选结论不能直接触发 Journey 执行，Journey 通过也不能替代未分配给它的证据。
- 根据 route 输出建立第二轮条件能力矩阵；逐项记录适用/不适用、主责 Skill、设备类型、命令、证据和未验证能力。缺少真机时继续执行全部本地与模拟器可覆盖门禁。
- 完成声明前，必须基于最后一次修复后的最终代码重新执行所有必需命令；修改前或中间轮次的通过结果只能作为过程记录，不能作为最终门禁证据。

所有必需项完成后，先执行 `delivery_gate.py snapshot` 获取当前确认修订、有效义务、Git 基线和最终代码摘要，按 `references/delivery-result.schema.json` 写入 `<requirement_dir>/test-results/delivery-result.json`，再执行：

通过结论必须包含并通过核心 gate：`android-review-diff`、`android-review-code-quality`、`android-audit-stability`、`android-test-and-fix`、`android-build`、`android-lint`；接口、迁移、UI/设备等条件 gate 按真实影响追加。

```bash
python3 ai-skills/android-delivery-skills/scripts/delivery_gate.py validate
```

只有退出码为 0 才允许使用通过结论。`INCOMPLETE/BLOCKED` 可以作为诚实报告保存，但校验命令不会把它当成交付通过。该文件是一次性交付结果，不是 phase/state 状态机。

### Definition of Done

只有同时满足以下条件才可声明交付完成：

- 每条 BDD 的所有原子 Then 均映射到实现和可执行测试，或明确标记为实际人工覆盖、未验证或阻塞；计划人工执行但尚未执行时不得写成已覆盖。
- 需求修订状态为 `CONFIRMED`，不存在 `PENDING/CONFLICT`；最终报告的 obligation ID、必需性和语义摘要与当前有效 Then 集合完全一致。
- 当前需求追溯表覆盖全部已确认 `REQ-ID` 和必需 Then，需求映射率为 100%，每条记录包含最终实现、测试/实际人工验收、必需性与证据状态。
- 受影响自动测试、构建和 lint 实际执行通过；不得把“未执行”写成通过。
- 必需命令在最后一次代码或测试修复后重新执行，最终报告记录命令、退出码、测试数、关键输出和报告/产物路径。
- OpenAPI、迁移、泄漏、性能、UI/A11y、安全隐私均已记录适用性；所有明确验收所必需的条件能力有新鲜通过证据。
- 所有 P0/P1 已关闭；无豁免的测试失败为 0。
- UI/设备/外部环境无法验证时明确列出未验证项，但不得掩盖本可本地执行的失败。
- 专项能力降级后，只有等价重验覆盖了同一 BDD 和风险才可计入通过；必需门禁能力缺失时结论必须是“未完成/受阻”。
- 存在 UI 变更和可对比基准时，必须附上独立 `android-verify-ui` 报告或用户明确豁免；否则结论只能是“代码与自动测试完成，UI 验收待执行”。
- 最终报告包含变更、测试命令与结果、自修复记录、失败分类、专项能力/工具降级、AI 替代、能力损失、所需用户输入、未验证项和剩余风险。
- 没有真机但不涉及真机必需验收时，结论只能是“代码与本地门禁完成，真机专项待验证”；真机是明确验收条件时保持“未完成/受阻”，但不否定其他已完成范围。
- `<requirement_dir>/test-results/delivery-result.json` 已通过独立最终门禁，且需求文件、Git 基线、最终代码摘要和所有引用证据仍一致。

任一必需门禁未满足时只能声明“未完成/受阻”，不得使用“交付完成”“全部通过”。Git 提交仅在用户明确要求时执行，不得把自动提交作为完成条件。

## 资料缺失降级边界

资料缺失时先区分是否会影响正式生产契约：

1. 缺少 Endpoint、请求方式、关键字段、枚举或错误码且需求要求接正式接口时，停止对应网络接入并请求契约，不创建猜测性 DTO、Endpoint 或运行时 `TODO()`。
2. 用户明确允许先做 UI 骨架或 Mock 时，只在 `debug`、`fake`、`sampledata`、Preview 或测试范围内建立最小 Fake；不得进入 release 生产路径。
3. 已有契约明确允许未知枚举/default 时，沿用项目现有兼容策略；契约未确认时不得把所有字段一律 nullable/default 当作完成。
4. 最终报告列出未接入部分、降级位置、未验证项和恢复正式接入所需资料。
