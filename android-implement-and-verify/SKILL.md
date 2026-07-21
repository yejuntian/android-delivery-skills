---
name: android-implement-and-verify
description: Android 需求实现与闭环验证总入口。用于完整完成 Android 新需求、需求变更、Bug 修复和功能迭代：首次编码前读取需求/UI/接口资料、确认 BDD、物化测试并建立基线；编码后的完善、修改、删除或修复只做受影响测试和必要编译；用户要求最终检查、完整交付或准备提交时，再按最终 diff 编排范围、接口、质量、稳定性和 UI 专项检查并驱动全绿门禁。仅需单项审查时改用对应专项 Skill。
---

# Android 需求实现与闭环验证

## 共享规则

执行本 Skill 前，必须先遵守 `../_shared/android-global-rules.md`。本 Skill 启用总入口自修复授权：本次需求范围内的问题默认最小修复并重验，不采用专项 Skill 的 standalone report-only 默认值；是否进入完整交付仍按三阶段规则判断。

维护、扩展或重构本流程时读取 `../references/open-source-design-rationale.md`；修改 Skill、路由或门禁后按 `references/delivery-eval-scenarios.md` 做行为评测。编码后出现接口、数据、UI、生命周期、性能或安全候选时，按需读取 `references/conditional-capability-gates.md`；出现 UI 与业务混合、Journey 只能覆盖部分步骤、测试层选择或证据缺口时读取 `../android-test-and-fix/references/adaptive-test-routing.md`。物化中途需求增删改时遵守 `references/requirement-revision.schema.json`，生成最终机器报告时遵守 `references/delivery-result.schema.json`。这些资料都不是日常需求执行时的固定上下文。

## 职责边界

- **负责**：需求确认、BDD、测试物化、编码、动态路由、自修复、重验和最终门禁。
- **不负责**：自动发布、推送、上线、操作生产数据或未经授权提交 Git。
- **与专项 Skill 的关系**：本 Skill 是唯一总入口；专项 Skill 提供诊断与验证结果，不另行编排完整交付。

## 需求质量与追溯

### 稳定 ID 与场景门禁

- 为每条已确认需求分配稳定 `REQ-001`，为可观察验收场景分配 `BDD-001`，为可执行测试分配 `TEST-001`；同一需求内不得因排序或补充内容随意改号。
- 首次确认前已经展示的临时 REQ/BDD/原子 Then 对未变化内容保持编号稳定；用户在首次确认前撤回的草稿项不进入 R1，不使用已实现需求的删除处置。
- 需求确认前检查主流程、备选流程、异常流程、恢复流程和非功能约束。缺少某类场景时标记“待确认”或“不适用 + 原因”，不得为了凑数量脑补。
- 只询问会改变实现、验收或风险判断的问题，最多 5 个并尽量一次确认完成；关键业务含义仍不明确时必须阻塞，不用问题数量限制掩盖缺口。
- 已确认需求必须清晰、无冲突且可通过可观察结果验收；不能从代码、工具输出或常见做法反推未写明的产品规则。

### 当前需求追溯表

- 完整交付统一维护 `<requirement_dir>/test-cases/traceability.md`；它是当前需求交付物，不是跨需求缓存或状态机。单独调用测试 Skill 可以先在本次报告中建立映射，但进入完整交付前必须同步到该固定路径，保证 `init`、最终门禁和中文报告读取同一份事实。
- 表格列为：`REQ-ID | 来源/验收 | BDD-ID/Then | 影响面/风险 | 实现文件 | TEST-ID/类型 | 必需性 | 命令 | 证据/状态`。
- 需求确认时把复合 Then 拆成 `BDD-001/T1` 形式的原子验证义务，填写来源、初步影响面、风险和必需性；编码与验证后补齐实现、测试、命令、新鲜证据和覆盖状态。同一 BDD 可由多个测试层共同覆盖，不建立跨需求状态机。
- 所有已确认 `REQ-ID` 都必须有实现或明确“不需要代码”的依据，并映射到测试或可复现人工验收。需求映射率必须为 100%；这是需求覆盖，不等于代码行覆盖率。

### 中途需求修订

- `<requirement_dir>/test-cases/requirement-revision.json` 是 AI 物化、用户审阅的修订清单；结构必须符合 `references/requirement-revision.schema.json`，并绑定脚本输出的 `requirement_id` 和 `base_revision`。
- 同一需求逐项使用 `ADDED/CHANGED/REMOVED/UNCHANGED/SUPERSEDED`；决策使用 `CONFIRMED/PENDING/REJECTED/CONFLICT`。`PENDING/CONFLICT` 只保存候选且不推进版本，`REJECTED` 不进入当前总需求。
- `REMOVED + CONFIRMED` 必须明确 `REMOVE_IMPLEMENTATION/KEEP_COMPATIBILITY/STOP_UNFINISHED_WORK`；`SUPERSEDED` 必须在同轮指向一个已确认的新增 Then。
- 每轮必须分类全部既有有效 Then 和上轮待定项；未变化项保留 ID。只在聊天中确认的变化先同步到 `requirement_file`，不得让聊天成为唯一事实来源。
- 只有用户确认正文语义完全不变时才允许 `format_only=true`，并要求全部 Then 为 `UNCHANGED`；该操作同步正文摘要但不推进语义修订号。
- `confirm-requirement-update` 只更新最近确认正文、修订号、有效义务和修订历史，不读取或修改 Git。重复 `check-env` 只复用当前起点；新的串行需求必须完成当前需求并获得用户明确确认后，在干净工作区执行 `check-env --new-requirement`。

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

进入最终交付时必须基于实际 diff 快速复核影响面，不做全量矩阵分析，只判断是否触发专项审查；局部迭代只对本轮修改做测试选择和高风险边界判断：

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
  - 按上方轻量 diff 触发规则决定提示独立 UI 验收或记录设计资料缺口，不重复建立第二套路由判断。
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

#### 开始下一个串行需求

只有用户明确确认上一需求已经完成或取消并要求开始新需求时，才执行工作区轮换。同一需求的补充、修改、删除和局部重测继续使用当前目录。新需求文件必须先放在当前 `requirement_dir` 之外；先运行不带 `--confirm` 的命令向用户展示中文预览：

```bash
python3 ai-skills/android-delivery-skills/scripts/requirement_workspace.py next \
  --title "新需求中文名称" \
  --requirement-file /path/to/new-requirement.docx \
  --previous-title "上一需求中文名称" \
  --previous-outcome 已完成
```

用户确认预览后，使用完全相同的命令追加 `--confirm`。脚本要求 Android 项目工作区干净，保留上一需求，创建 `REQ-日期-序号-中文名称` 目录及中文 `需求说明.md`，并只更新本机配置中的活动需求路径；不操作 Android 源码或 Git。轮换完成后继续执行下方阶段 1，确认新需求理解后，阶段 2 使用 `check-env --new-requirement` 建立新基线。不得直接跳到 `check-env --new-requirement`。

查看当前目录和回收候选使用 `requirement_workspace.py status`。历史需求和 `tempfile` 只有状态明确、不是活动需求且同时超过最近保留数量和保留天数时才成为候选；`next` 预览会明确列出候选，同一命令追加 `--confirm` 后才随轮换回收。也可以单独执行 `prune` 预览，再用 `prune --confirm` 回收。确认写操作使用单写锁；另一个窗口正在轮换或回收时停止，绝不覆盖其配置、锁或目录。轮换成功但回收失败时，新需求目录和配置仍然有效；明确告诉用户只需修复权限或路径后单独重试 `prune`，不得再次执行 `next` 制造重复需求。

#### 阶段 1：初始化需求理解

首次使用时从 `workspace_root` 安装依赖：

```bash
python3 -m pip install -r ai-skills/android-delivery-skills/requirements.txt
```

然后运行：

```bash
python3 ai-skills/android-delivery-skills/scripts/delivery.py init
```

**AI 动作**：脚本会输出需求上下文。先形成初步需求理解；读取项目代码前只读核对 `project_path` 存在且为 Git 仓库、当前分支符合配置。首次需求尚无基线且工作区已有改动时停止，已有当前需求基线的中途修订则保留原基线继续分析，不重复 `check-env`。随后只读、定向检查目标项目规则、模块结构、本次相关实现、调用方、共享状态、接口/存储边界和已有测试；不逐行扫描全仓库，不修改代码，也不运行构建或设备任务。分配稳定 `REQ-###` / `BDD-###`，检查主流程、备选、异常、恢复和非功能场景，提炼足以覆盖真实需求的 **BDD (Given/When/Then)** 验收标准；把复合 Then 拆成 `BDD-001/T1` 形式的原子验证义务，初判影响面与 `L1/L2/L3/BLOCKED`，并同时输出最小修改预览。BDD 和 Then 数量服从实际需求，不为凑数量脑补场景；最多一次提出 5 个真正影响实现或验收的问题。

完整需求理解最前面固定输出“请优先确认：已上线业务影响”，按自然中文分为：

- **本次明确修改**：当前需求明确允许改变的已有业务，原子 Then 以 `【修改已上线业务】` 开头，并写清修改前和修改后行为。
- **必须保持不变**：可能被本次实现波及、但当前需求没有允许改变的已有业务，原子 Then 以 `【保护已上线业务】` 开头，只记录有代码、测试、契约或用户确认支持的可观察行为。
- **暂时无法确认**：无法确定是否允许改变的已有行为；作为待定/冲突项阻断确认，不把当前代码表现或疑似旧 Bug 擅自固化。
- **明确不修改范围**：本次确认不会触及的相邻业务和公共边界。

完全没有识别到已有业务关联时只写“当前确认需求未登记需要修改或重点保护的已上线业务；编码后仍按最终 diff 复核”，不得宣称绝对没有影响。上述影响说明与完整需求只确认一次，不增加独立审批回合。

首次确认前，用户每次新增、修改、删除、纠正或改变旧业务处置时：先用自然中文列出本轮新增、修改、删除和保留项；将结果合并为最新完整需求并同步到 `requirement_file`；重新执行 `delivery.py init` 读取文件；只重新分析受影响代码、调用方、测试和旧业务；最后同时展示本轮变化、最新完整需求、更新后的影响说明和原子验收项，再等待确认。用户回复同时包含“确认”和新变化时仍按变化处理，禁止直接执行 `check-env`。只有用户已经看到最新完整需求并作出不带新变化的明确确认，才进入阶段 2。

同一需求编码中途再次运行 `init` 时，读取最近确认需求修订和现有追溯表，输出增改删、替代和逐项确认决策。保留未变化的 REQ/BDD/Then ID；修改和新增项重新确认，删除项选择实现处置。用户明确开始新的串行需求时不沿用旧 ID；`init` 和 `confirm-requirement-update` 均不修改 Git 基线。
**DoR (准备就绪) 门禁**：如果需求缺少继续实现所必需的业务含义、边界条件或报错证据，列出缺口并暂停请求补充；能够明确表达一个真实场景时，不得仅因条目少而阻塞。

最小修改预览中的每个新增或改动组件必须附轻量架构边界卡片：`组件/文件 | 职责 | 输入 | 输出 | 依赖方向 | 复用点 | 明确不修改范围`。同一组件的相关文件可以合并一行，避免文档膨胀。卡片服从目标项目现有架构，不用于强推分层、拆模块或技术迁移。需求确认且 `check-env` 成功建立基线后，在 `<requirement_dir>/test-cases/traceability.md` 建立追溯表前半部分，并把已确认的四类已上线业务影响说明放在文件顶部；修改/保护已上线业务的 Then 必须为必需项，并与实际实现、受影响调用方和测试证据同表追踪，不能让追溯文件反过来触发脏工作区门禁。

只有需求规模或依赖关系预计跨会话，或者 `L3` 同时包含多个可独立验收链路时，才在现有追溯表中把 BDD/Then 编排为带依赖关系的纵向交付切片；每个切片必须贯穿其实际涉及的 UI、业务、数据和测试并能独立编译、验证，完成一个再进入已解除依赖的下一项。普通需求和单点高风险小改动不增加切片、Ticket 或新文件，只追加风险直接要求的最小专项。

架构边界卡片必须落实到真实包、文件和构造依赖，不能只写文档。多职责功能没有既有分层时，按共享规则建立最小功能内分层并集中装配具体依赖；同时为核心 Kotlin/Java 类型和生命周期、并发、缓存、重试、索引等不直观逻辑补充必要 KDoc/注释，不要求给样板代码逐行加注释。
输出完毕后，**必须立即结束当前回合，等待用户确认**。绝不能直接开写代码。

#### 阶段 2：测试左移、环境检查与编码

在用户已经看到最新完整需求，并明确回复不带任何新增、修改、删除或纠正的“确认”“可以开始做”之后，运行以下命令：

```bash
python3 ai-skills/android-delivery-skills/scripts/delivery.py check-env
```

**AI 动作**：环境检查只在目标分支和工作区干净时一起建立当前需求 Git 基线与需求起点；已有起点时安全复用，绝不覆盖。任一失败都不进入编码。检测到已有改动时停止，不自动 stash、提交或清理。只有用户明确开始新的串行需求时才使用 `check-env --new-requirement`。随后按 `references/requirement-revision.schema.json` 把用户已确认的全部原子 Then 写入 `<requirement_dir>/test-cases/requirement-revision.json`，并执行：

```bash
python3 ai-skills/android-delivery-skills/scripts/delivery.py confirm-requirement-update
```

退出码 `0` 才表示最新版总需求已确认并允许编码；`2` 表示仍有 `PENDING/CONFLICT`，继续澄清而不覆盖上一确认版本；`1` 表示清单、路径、版本或同步关系无效。编码中途只有业务行为、边界或验收结果发生变化时，才重复 `init → 用户确认 → 更新修订清单 → confirm-requirement-update`；实现层完善不创建需求修订。两种情况都保留最初 Git 基线。修订确认后遵守以下规约：
1. **先物化测试**：先把全部已确认 `BDD/Then` 映射为测试清单，再按一个原子 Then 或不可分割的 BDD 切片逐项生成可编译测试和断言，完成 `Red -> 最小实现 -> Green` 后才进入下一项，不采用“批量写完全部测试、再批量实现”的横向方式。`【保护已上线业务】` 优先复用并先运行已有测试；缺少测试时只为本次可能波及的可观察旧行为补最小保护测试，业务含义不明时重新确认，不机械固化当前实现。`【修改已上线业务】` 允许按已确认新预期更新对应测试，但不得删除或弱化未授权旧业务断言。纯业务逻辑至少覆盖正常、边界、异常和回归路径；UI 与业务混合场景拆给能够证明行为的最低且足够测试层。Journey 此时只根据原子 Then 分配做整条 BDD 的 `FULL/PARTIAL/NONE` 候选初判，并为可覆盖部分生成用例草稿，不启动设备或 Journey 引擎；编码后结合实际 diff 终判，仍有分配项才执行。`android-verify-ui` 只负责后续视觉验收，不得只输出 BDD 文本。
2. **主动检索**：动笔前，主动用搜索工具在项目中寻找同类组件、Base 类和测试范式。
3. **Figma UI 分流与接管 (最小化修改)**：先根据目标项目真实代码确认 XML View、Compose 或混合实现，不因设计链接擅自换技术栈。已确认的 Figma + XML View 部分调用 `figma-android-xml` 生成纯 UI 资源和 XML；Compose 部分沿用项目既有结构，不调用 XML 生成 Skill。生成后只检查本轮产物并执行交接门禁：固定用户文案资源化，动态预览数据只用 `tools:text`；装饰图片使用空语义，功能/信息图片使用有需求依据的描述，语义不明时暂停确认；资源命名和复用服从目标项目。外部阶段不得新增 Kotlin/Java 业务代码，随后由本 Skill 接管必要的 Kotlin/Java、ViewBinding/DataBinding、Adapter、状态和业务连线。
4. **首次验证**：首次处理该项目、本轮修改 Gradle/模块/variant，或真实 task 未知时，运行 `scripts/android_project_capabilities.py --config <配置>`；普通业务代码修改复用最近能力事实并直接执行已确认 task。发现失败时允许结合 Gradle 文件人工确认，但不得猜任务名。
5. **自修复**：任一项失败，按“统一故障处理与 AI 接管”保存证据并分类，确认根因后只修改对应的生产代码、测试或环境配置，再重跑失败项及相关回归集。禁止删测试、弱化断言、跳过任务或用假数据掩盖失败。
6. **循环上限**：同一根因连续 3 轮未关闭才进入 `BLOCKED`；报告失败分类、原专项能力/工具、命令、退出码、关键日志、AI 替代与能力损失、已尝试修改和所需输入。
7. **同步追溯**：编码和验证过程中把最终实现文件、`TEST-###`、真实命令和证据补入当前需求追溯表，不把上一需求或中间轮次结果复用为完成证据。

#### 编码后局部迭代

首次实现后，用户继续要求完善、修改、删除或修复某个点时，先做一次语义判断：

- **验收语义不变**：不执行 `init`、`confirm-requirement-update`、`route`、全部专项 Reviewer 或最终报告。只检查本轮修改落点和调用方，做最小代码修改，更新对应测试，并调用 `android-test-and-fix` 的局部迭代模式运行受影响测试；生产代码变化时追加能够发现引用或签名错误的最小编译，删除代码时必须先检查调用方。
- **验收语义变化**：把用户确认的变化同步到 `requirement_file`；如果补充内容改变已有业务的“修改/保护”处置，同时更新置顶影响说明和对应标记 Then。只对受影响义务执行需求修订与确认，再按上一条进入局部迭代；未变化的 REQ/BDD/Then、代码和测试不得重做。
- **风险直接扩大**：如果本轮修改触及数据库迁移、公共 API、支付、鉴权、安全、权限、生命周期或其他 L3 边界，只追加能够验证该风险的最小专项，不机械运行全部专项。
- **局部结果边界**：只向用户报告本轮修改、执行的测试/最小编译、结果和剩余风险；不得生成新的整体通过结论，也不得把旧 `delivery-summary.md` 当成当前代码的最终报告。

局部迭代可以重复多次。仅因代码写完不得自动进入阶段 3；用户当前或最初请求明确包含“最终检查、完整交付、准备提交”等意图时，才进入最终交付。如果之前已经生成过最终结果，任何后续代码、测试、资源或构建配置变化都会使其失效，但不要求在每次局部迭代后立刻重跑完整门禁。

#### 阶段 3：审查、自修复与交付门禁

确认用户已要求最终检查、完整交付或准备提交后，基于当前最终代码运行：

```bash
python3 ai-skills/android-delivery-skills/scripts/delivery.py route
```

**AI 动作**：脚本只分析 `check-env` 记录的当前需求 Git 基线之后的 diff，输出专项审查与测试顺序，并在项目外生成符合 `references/route-impact.schema.json` 的影响快照。快照同时绑定需求正文、配置声明的 UI/API 链接与本地资料摘要；这些输入变化后必须重新确认影响并 route。逐个调用，每项输出必须进入闭环，而不是止于报告。
- Git 分支、工作区、committed/staged/unstaged/untracked、`A/M/D/R` 状态、真实修改片段和最终代码摘要由 `scripts/git_changes.py` 只读收集；`delivery.py` 只消费结果并编排路由，不得在任一脚本中混入对方职责。
- 一次只查一项。
- 不要自行脑补脚本未列出的审查项。
- `android-review-diff` 必须按 `specialist-result.schema.json` v4 对 UI、API、数据、系统、构建、架构和测试七类影响逐项输出 `confirmed_impacts`。适用项绑定项目相对路径和原因，不适用项也说明需求/diff 依据；该语义结果与脚本候选取并集，新增的条件能力必须继续执行，不能因文件名或正则漏检而省略。
- `android-review-diff` 还必须用最终 diff 复核已确认的旧业务影响。发现未登记的已有业务调用方或可观察行为变化时，立即暂停最终交付，把影响同步到 `requirement_file`，重新展示置顶提醒并让用户确认，再修订受影响 Then、实现和测试；已有当前需求 Git 基线时不得重复执行 `check-env`，也不得只在最终报告追加说明。
- 已确认需求范围内的 P0/P1 技术问题发现后立即修复，并从受影响的最小测试集开始重跑；计划外已上线业务影响、需求冲突或业务预期不明确即使评为 P0/P1 也必须先重新确认。低风险 P2/P3 可修复时一并关闭。
- 修复导致 diff 变化时重新执行 `route`，直到路由结果稳定。
- 最后执行 `android-test-and-fix` 的完整回归门禁；UI 变更时在报告中提示用户另行调用 `android-verify-ui`，不得在自动 route 中执行。
- `android-test-and-fix` 在此阶段先根据最终 diff 终判风险和测试层，再根据原子 Then 分配聚合每条 BDD 的 Journey `FULL/PARTIAL/NONE`；需求阶段的候选结论不能直接触发 Journey 执行，Journey 通过也不能替代未分配给它的证据。
- 根据 route 输出建立第二轮条件能力矩阵；逐项记录适用/不适用、主责 Skill、设备类型、命令、证据和未验证能力。缺少真机时继续执行全部本地与模拟器可覆盖门禁。
- 完成声明前，必须基于最后一次修复后的最终代码重新执行所有必需命令；修改前或中间轮次的通过结果只能作为过程记录，不能作为最终门禁证据。
- `route` 或 Diff Reviewer 语义确认的 OpenAPI、迁移、UI/A11y 和安全隐私候选由最终门禁机器强制出现；对应 Skill 终判不适用时使用 `required=false + SKIPPED`，同时填写需求/diff 原因和复核证据，不能直接省略。
- 最终命令必须通过 `scripts/execution_evidence.py --id <证据ID> --gate <gate-id> --report <报告> -- <命令参数>` 执行；一份收据只证明一个 gate，同 ID 重跑保留独立 attempt。测试和迁移自动收据必须包含实际执行数大于零的本轮 JUnit；用于覆盖原子 Then 的证据还必须把 obligation 映射到真实通过的 testcase。普通自动收据不能直接代替接口、UI/A11y、安全、泄漏或性能专项结论。
- 核心审查和条件接口审查按 `references/specialist-result.schema.json` 输出机器结果；`android-audit-stability` 必须记录必需静态语义能力、七项静态检查，以及动态泄漏、性能和安全隐私的 `PASS/FAIL/SKIPPED/UNVERIFIED/BLOCKED`。先用 `scripts/specialist_result.py path --config <配置>` 获取外部目录，再校验结果；P0/P1 或必需能力未关闭时不得写 `PASS`。
- 人工覆盖必须填写执行人、带时区时间、环境、逐步操作、预期、实际结果和产物或无产物原因。`LOCAL_PASS_DEVICE_PENDING` 必须登记真实设备待验项并引用同能力的未验证证据；`FULL_PASS` 不允许待验或 `UNVERIFIED/BLOCKED` 项。
- 最终中文摘要必须把 `【修改已上线业务】` 和 `【保护已上线业务】` 义务置顶分组展示；任一必需保护项缺少新鲜证据时，沿用现有义务门禁阻断完整通过。

所有必需项完成后，先执行 `delivery_gate.py snapshot` 获取当前确认修订、有效义务、Git 基线和最终代码摘要，按 `references/delivery-result.schema.json` 写入 `<requirement_dir>/test-results/delivery-result.json`，再执行：

通过结论必须包含并通过核心 gate：`android-review-diff`、`android-review-code-quality`、`android-audit-stability`、`android-test-and-fix`、`android-build`、`android-lint`；接口、迁移、UI/A11y 和安全隐私条件 gate 由最新 route 快照与 Diff Reviewer 的 `confirmed_impacts` 并集要求，不能由最终报告自行决定是否出现。

```bash
python3 ai-skills/android-delivery-skills/scripts/delivery_gate.py validate
```

校验命令在机器结果结构可信后同步生成 `<requirement_dir>/test-results/delivery-summary.md`；无论结论是通过、未完成还是受阻，最终回复都必须优先展示并链接这份中文摘要，`delivery-result.json` 只作为机器附件。只有退出码为 0 才允许使用通过结论。`INCOMPLETE/BLOCKED` 可以诚实保存并生成摘要，但不会被当成交付通过。机器文件是一次性交付结果，不是 phase/state 状态机。

### Definition of Done

只有同时满足以下条件才可声明交付完成：

- 每条 BDD 的所有原子 Then 均映射到实现及 JUnit 中真实通过的 testcase、Agent Journey 中实际执行的 action/check，或结构完整的实际人工收据；计划人工执行但尚未执行时不得写成已覆盖。
- 需求修订状态为 `CONFIRMED`，不存在 `PENDING/CONFLICT`；最终报告的 obligation ID、必需性和语义摘要与当前有效 Then 集合完全一致。
- 当前需求追溯表覆盖全部已确认 `REQ-ID` 和必需 Then，需求映射率为 100%，每条记录包含最终实现、测试/实际人工验收、必需性与证据状态。
- 受影响自动测试、构建和 lint 实际执行通过；不得把“未执行”写成通过。
- 必需命令在最后一次代码或测试修复后重新执行，最终报告记录命令、退出码、测试数、关键输出和报告/产物路径。
- OpenAPI、迁移、泄漏、性能、UI/A11y、安全隐私均已记录适用性；所有明确验收所必需的条件能力有新鲜通过证据。
- 所有 P0/P1 已关闭；无豁免的测试失败为 0。
- 代码质量专项已逐项通过 `architecture-layering`、`responsibility-cohesion`、`source-documentation` 和 `dependency-testability`；无 Kotlin/Java 变更时也必须明确说明不适用依据，不能省略检查。
- UI/设备/外部环境无法验证时明确列出未验证项，但不得掩盖本可本地执行的失败。
- 专项能力降级后，只有等价重验覆盖了同一 BDD 和风险才可计入通过；必需门禁能力缺失时结论必须是“未完成/受阻”。
- 存在 UI 变更和可对比基准时，必须附上独立 `android-verify-ui` 报告或用户明确豁免；否则结论只能是“代码与自动测试完成，UI 验收待执行”。
- 最终报告包含变更、测试命令与结果、自修复记录、失败分类、专项能力/工具降级、AI 替代、能力损失、所需用户输入、未验证项和剩余风险。
- 所有用户可见结论均使用自然中文；英文机器枚举只保留在 JSON、Schema 和原始证据中，并通过统一呈现模块转换为包含原因和下一步的中文说明。
- 没有真机但不涉及真机必需验收时，结论只能是“代码与本地门禁完成，真机专项待验证”；真机是明确验收条件时保持“未完成/受阻”，但不否定其他已完成范围。
- `<requirement_dir>/test-results/delivery-result.json` 已通过独立最终门禁，且需求文件、UI/API 输入摘要、Git 基线、最终代码摘要和所有引用证据仍一致；同时已生成并向用户展示中文 `delivery-summary.md`。

任一必需门禁未满足时只能声明“未完成/受阻”，不得使用“交付完成”“全部通过”。Git 提交仅在用户明确要求时执行，不得把自动提交作为完成条件。

## 资料缺失降级边界

资料缺失时先区分是否会影响正式生产契约：

1. 缺少 Endpoint、请求方式、关键字段、枚举或错误码且需求要求接正式接口时，停止对应网络接入并请求契约，不创建猜测性 DTO、Endpoint 或运行时 `TODO()`。
2. 用户明确允许先做 UI 骨架或 Mock 时，只在 `debug`、`fake`、`sampledata`、Preview 或测试范围内建立最小 Fake；不得进入 release 生产路径。
3. 已有契约明确允许未知枚举/default 时，沿用项目现有兼容策略；契约未确认时不得把所有字段一律 nullable/default 当作完成。
4. 最终报告列出未接入部分、降级位置、未验证项和恢复正式接入所需资料。
