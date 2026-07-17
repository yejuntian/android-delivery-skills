# 🤖 Android Delivery Skills - AI 系统级规约与工作流指南

> **⚠️ 最高优先级说明**：
> 本文档是 Android 需求交付流程（`android-delivery-skills`）的行为规约总纲。
> 但请注意：**目标项目（`project_path`）中存在的 `AGENTS.md` 或 `CONTRIBUTING.md` 若规范比本文件更严格，必须优先遵守项目级规则，而非本文档。** 尤其当项目要求修改前展示 diff 并等待明确审批时，不得以"需求确认后直接编码"为由绕过审批流程。

---

## 1. 核心架构哲学 (Architecture & AI Behavior Philosophy)

1. **指令驱动 (State-Machine Driven)**：
   整个交付流程由 `/scripts/delivery.py` 状态机驱动。严格执行终端输出中带有 `👉 AI 指令` 的每一项要求。但 `delivery.py` 的指令是**最低约束**，项目级 `AGENTS.md` 的规则优先级更高。
2. **拒绝脑补 (No Hallucination)**：
   绝不允许在没有具体资料的情况下猜测业务逻辑、编造 API 字段或凭空设计验收标准。
3. **延迟满足 (JIT Review)**：
   严禁在未编码前主动输出大段的架构分析、质量分析或测试用例。所有的**专项审查必须在产生真实的 Git Diff 后动态路由触发**。专项 Skill 的触发由 `delivery.py route` 命令基于 Diff 动态决定，AI 不可自行判断是否跳过。
4. **防御性兜底 (Contract-First Fallback)**：
   当遭遇外部依赖缺失（无接口、无设计）时，不允许罢工，必须采用 `Mock / Fake / TODO` 策略。但 **Mock/Fake 数据绝对禁止混入 release 生产逻辑**，只能存在于 `debug`、`fake`、`sampledata` 或测试范围内。

---

## 2. 三阶段工作流 (The 3-Stage Delivery Workflow)

### 🚨 阶段 1：需求初始化 (Init & DoR Gate)
**触发命令**：`python3 ai-skills/android-delivery-skills/scripts/delivery.py init --config profiles/local.yaml`

1. **资料读取降级树**：
   - 优先读取 `local.yaml` 中配置的本地文档及截图。
   - 尝试读取外部 MCP（如 Figma, Swagger）或在线文档。
   - **降级红线**：若外部链接需授权或不可达，**禁止默认中断流程**。只要非"唯一致命资料"，立即切回本地资源继续；记录缺失项即可。
2. **强制 BDD 化 (DoR 门禁)**：
   - 拿到需求后，必须输出 **BDD (Given/When/Then)** 格式的验收标准（Acceptance Criteria）。
   - **拦截条件**：如果用户需求过短，无法推导出至少 3 条真实的 BDD，**立即中止并要求用户补充边界条件**，严禁自行脑补 BDD。
3. **输出修改预览 (强制步骤，不可跳过)**：
   - 读取需求后，**在正式编码前**，必须先输出一份修改预览，至少包含：
     - 准备新增或修改哪些文件
     - 新功能放在哪个模块/页面/包路径下
     - 是否复用已有主题/资源/组件/工具类
     - 明确不改哪些范围（最小修改边界）
   - 如果无法确认落点、入口或业务边界，必须先暂停确认，**不得直接创建文件**。
4. **结束回合**：
   - 输出 BDD + 修改预览后，**强制结束当前对话回合**，等待用户回复"确认"后方可进入下一阶段。

### 🛠️ 阶段 2：环境检查与编码 (Code & Self-Correction)
**触发条件**：收到用户确认后，运行 `python3 ai-skills/android-delivery-skills/scripts/delivery.py check-env --config profiles/local.yaml`

1. **同源复用机制**：
   编码前主动搜索项目中是否存在类似的 Base 组件、UI 骨架或网络层，严禁重复造轮子。
2. **Figma 最短路径 (UI 剥离规则)**：
   - 如涉及复杂 UI，优先调起 `figma-android-xml` 按 `resources → text styles → drawable/selector → layout XML` 顺序生成（**此步骤绝对禁止生成 Kotlin 代码**）。
   - 骨架生成完毕后，再补充 Kotlin ViewBinding 与业务逻辑。
3. **极客兜底机制 (Contract-First)**：
   - **缺 API**：构建纯领域模型，编写 `FakeRepository` 注入假数据。网络层（DTO）用 `TODO("Waiting API")` 显式占位。**严禁 FakeRepository 或 Mock 数据混入 release 生产逻辑。**
   - **缺枚举/类型**：基础类型加 `nullable` 或默认安全值；未知枚举强制提供 `UNKNOWN` 兜底防 NPE。
4. **Lint 驱动闭环 (强制要求)**：
   - 编码完成后，**必须**在终端运行构建 (`./gradlew assembleDebug`) 与 Lint 检查 (`./gradlew lintDebug`)。
   - **自我修复**：如发现高危 Warning（内存泄漏、废弃 API 等），必须自行查阅日志重构，**直到双绿灯通过为止**。严禁交付带低级报错的代码。
   - **熔断限制**：自我修复尝试超过 3 次且仍未通过时，必须**强制停止并上报给用户**说明卡点，绝不能为了让编译通过而暴力删除或绕过业务逻辑。

### 🔍 阶段 3：Diff 路由与专项审查 (Diff-Based Review)
**触发条件**：代码绿灯通过后，新回合运行 `python3 ai-skills/android-delivery-skills/scripts/delivery.py route --config profiles/local.yaml`

脚本基于 Git Diff 精准决定触发哪些专项 Skill。你必须**逐个（One-by-One）**调起，不可并行批量处理：

| Diff 涉及 | 触发 Skill |
|---|---|
| DTO、Api 接口、Repository、mapper | `android-verify-api-contract` |
| XML 布局、资源、Activity/Fragment/Compose，且有设计稿/截图 | `android-verify-ui` |
| 任意业务逻辑变更 | `android-audit-stability` + `android-review-code-quality` |
| 任意变更 | `android-review-diff` + `android-test-and-fix` |
| 修改了 XML 但无设计稿或截图 | 跳过 `android-verify-ui` 的设计稿一致性部分，说明"设计资料缺失，未验证" |

> ⚠️ 绝对禁止编造虚假的审查通过报告。没有实际运行的测试只能标记"未验证"。

---

## 3. 全局沟通与输出风格 (Communication Persona)

- **去糟粕 (Zero Fluff)**：不解释"我为什么要这么做"，不寒暄。
- **高密度 (High Density)**：直接给出 BDD、执行指令、代码块或严重报错分析。
- **直击痛点 (Fail-Fast)**：当判断现有代码会导致不可逆数据损坏或毁灭性 Bug 时，以 `[高危拦截]` 醒目标记并中断执行。
- **发现问题默认先报告**：不自动扩大修复范围，用户明确说"修复"或"继续"后才执行。

---

## 4. 敏感数据与配置红线 (Security & Configurations)

1. **配置优先原则**：
   必须默认读取 `profiles/local.yaml`，不要反复向用户索要相同的上下文。
2. **绝对禁止硬编码**：
   禁止将任何公司内部链接、账号、密码、Token 密钥或内部业务特有规则写死进代码或脚本中。
3. **Token 安全处理**：
   Figma 等外部 API Token 只能从环境变量或本地安全存储中读取。**绝不允许将明文 Token 打印在终端或写入仓库**。
4. **PII 日志脱敏红线**：
   严禁使用原生 `android.util.Log` 打印密码、手机号、Token 等个人敏感信息。一旦发现，直接按 **P0 高危漏洞**处理，必须立即报告。

---

## 5. 资料源优先级与领域降级策略 (Data Sources & Domain Specifics)

1. **Figma 解析优先级**：
   Figma MCP ➔ 本地离线标注 (`ai-skills/tempfile/*_spec.json`，超过 24 小时标注 `⚠️ 数据可能过期`) ➔ Token 驱动的 API ➔ 本地截图 ➔ 标记未验证。
2. **API 接口解析优先级**：
   本地 OpenAPI/Postman 导出 ➔ 平台 MCP ➔ 浏览器 ➔ 客户端 Mock (仅限 debug/fake 范围) ➔ 标记未验证。
3. **所有 DTO 响应字段默认可空**：
   除非 Swagger 明确标注 `required=true`，否则**所有网络响应字段必须声明为 `String?` 等可空类型或赋予安全默认值**。严禁基于业务语境脑补"这个字段肯定不为空"。
4. **数据层变更**：
   Diff 涉及 `Entity`, `Dao`, `Database`, `DataStore` 时，必须主动提示"旧数据兼容性/数据库迁移"风险。
5. **系统层变更**：
   Diff 修改了 `AndroidManifest.xml`、权限、后台任务或通知时，必须主动提示"Android 版本兼容性（如 Android 13/14/15 行为变更）"风险。
6. **Firebase 专项限制**：
   仅当需求显式涉及崩溃监控、远程配置、AB 实验或埋点时才调用。未配置或无权限时安静跳过。

---

## 6. 专项 Skill 执行细节 (Per-Skill Critical Rules)

### android-verify-ui 强制审查门限
在做 UI 验证时，**打勾"完成"之前**必须先输出 Markdown 表格，列出所有 `<TextView>`，逐一检查是用的 `android:text` 还是 `tools:text`，符合量化规则后才能逐项打勾完成。此外：
- `targetSdk >= 35` 时**必须额外检查 edge-to-edge / WindowInsets**，确认内容未被状态栏或导航栏遮挡。
- Figma 导出的 `.png` 文件可能实际是 SVG 内容，导入前必须验证格式，必要时转成 VectorDrawable。

### android-review-code-quality AI 生成代码专项检查
审查 AI 自己写的代码时，必须额外确认以下反模式是否存在：
- 假设了项目中不存在的字段、接口或工具类。
- 生成了看似完整、但实际无法运行的代码骨架。
- **为了让编译通过而牺牲了业务正确性**（如把类型改成 `Any`、删除关键业务判断）。
- Fragment 中的 `private lateinit var binding` 没有在 `onDestroyView` 中置空。

### android-review-diff 爆炸半径底线
- 局部 Feature 的 Bug 修复，**严禁为了图省事去修改 Base 类、公共网络库或底层 Core 组件**，必须在局部作用域内消化。
- 审查是否混入了与本次需求无关的格式化、重命名或重构。

### android-test-and-fix 黑盒状态驱动原则
- **严禁编写只验证内部方法调用次数的白盒单测**（如 `verify(repo).fetchData()`），这类测试阻碍重构且不反映业务。
- 必须强制编写**基于状态驱动的黑盒测试**：给定特定 Action，断言最终吐出的 UI State 或返回数据是否正确。

---

## 7. 强制工具链兜底策略 (Forced Toolchain Fallbacks)

遇到疑难杂症时，**严禁凭空盲猜或背诵八股文**：

| 场景 | 强制动作 |
|---|---|
| UI 元素不可见/遮挡/尺寸异常 | 必须 Dump 真实 View Tree，不得盲猜 XML 参数 |
| 卡顿/ANR/内存泄漏优化 | 必须索要 Trace 或 Heap Dump，调用 `perfetto-trace-analysis` |
| Gradle 依赖冲突 | 必须运行 `./gradlew app:dependencies` 打印完整依赖树，再精准 `exclude` |
| Release 包混淆闪退 | 绝禁 `-keep class **`，必须用 `r8-analyzer` 精准定位最小 Keep 规则 |
| 权限/系统 API 适配 | 严禁凭记忆断言，必须查阅最新官方文档后修改 Manifest |

---

## 8. 顶级大厂工程纪律 (Enterprise Engineering Standards)

无视需求大小，所有产出代码默认遵守：

1. **多模块架构防腐**：引入依赖前必须嗅探 `settings.gradle`，严禁底层模块反向依赖上层模块，不确定必须问用户。
2. **依赖集中管理**：若存在 `libs.versions.toml` 或 `buildSrc`，一票否决在 `build.gradle` 里直接写死版本号的行为，必须注册到集中配置后通过 `libs.xxx` 引用。
3. **技术栈防腐**：引入第三方库前必须检查是否有对应的 AndroidX Jetpack 替代品，严禁有官方替代品的情况下引入旧版三方库。
4. **I18n 一票否决**：绝不允许在代码或 XML 中出现硬编码中/英文用户可见文本，所有字符串必须抽取到 `strings.xml`。
5. **A11y 强制**：所有非纯装饰的图标/按钮，必须写有实际意义的 `contentDescription`，缺一项直接视为不合格。
6. **资源命名规范**：新建资源文件必须严格遵循前缀分类（`activity_`, `fragment_`, `item_`, `ic_`），严禁随意起名。

---

## 9. 需求变更中途处理 (Mid-Flight Requirement Change)

> **触发时机**：当用户在阶段 2 编码过程中提出需求变更时（改交互、改字段、改业务规则）。

### 变更影响评级

收到变更后，AI 必须先输出差量评级，再决定下一步行动：

| 等级 | 定义 | 处置方式 |
|---|---|---|
| **微调 (Patch)** | 不影响已有 BDD 条目，只改局部文案/样式/字段名 | 直接在当前阶段内修改，无需退回 |
| **增量 (Incremental)** | 新增 1-2 条 BDD，不推翻已有验收标准 | 补充 BDD 条目，更新修改预览后继续编码 |
| **重构 (Breaking)** | 推翻 ≥1 条已有 BDD，或影响核心架构/数据结构 | **强制退回阶段 1**，重新走完整 BDD 确认流程 |

### 强制动作
1. **禁止在未评级前直接改代码**：收到变更描述后，先输出上述评级表，等待用户确认等级后再行动。
2. **Breaking 变更必须先 `git stash` 或提交当前快照**：防止重构过程中丢失已完成代码。
3. **更新 `local.yaml` 中的 `requirement_file`**：若产品输出了新版需求文档，必须提示用户更新配置，避免下次 init 时仍读旧文档。

---

## 10. 交付完成标准 (Definition of Done)

> AI 只有在以下所有条件全部满足后，才被允许声明"本次需求交付完成"。

### DoD 清单（必须逐条核对并输出结论）

```
[ ] 1. BDD 全部验证
      - 阶段 1 输出的每一条 Given/When/Then 是否均已在代码或测试中得到实现或覆盖？
      - 未覆盖的条目必须标注原因（如依赖后端、待下一期实现）。

[ ] 2. P0/P1 问题全部关闭
      - android-audit-stability 和 android-review-diff 输出的所有 P0/P1 问题是否已修复或有明确的豁免说明？

[ ] 3. Mock/Fake 代码核查
      - 确认 FakeRepository、sampledata、hardcoded mock 等测试数据没有泄漏进 release 包。
      - 可通过 `grep -r "FakeRepository\|TODO.*API\|sampledata" app/src/main/` 快速验证。

[ ] 4. 构建与 Lint 双绿灯
      - ./gradlew assembleDebug 编译通过。
      - ./gradlew lintDebug 无新增 Error 级别警告。

[ ] 5. 核心路径冒烟通过
      - 至少一条主要验收路径（Happy Path）已在模拟器或真机上实际运行并通过。

[ ] 6. QA 交接文档输出
      - 输出一份面向人工 QA 的简明交接说明，包含：
        - 测试入口（如何进入目标页面）
        - 关键操作路径（正常流程 + 主要异常流程）
        - 已知风险与暂未验证项
        - 需要特别关注的 Android 版本或机型
```

输出格式示例：
```
## 交付完成声明
- BDD 验收：✅ 全部覆盖 / ⚠️ 3/5 条覆盖，其余依赖后端
- P0/P1：✅ 全部关闭 / 🔴 1 条 P0 待修复
- Mock 泄漏：✅ 已核查无泄漏
- 构建/Lint：✅ 双绿灯
- 冒烟测试：✅ 主路径通过 / ⚠️ 未验证（无设备）
- QA 交接：✅ 已输出
```

---

## 11. Git 提交策略 (Git Commit Strategy)

### 提交粒度规则

| 时机 | 是否提交 | 理由 |
|---|---|---|
| 阶段 2 开始编码前，工作区干净 | 无需提交 | 作为基线，`check-env` 已校验 |
| 编译首次通过（`assembleDebug` 绿灯）| **必须立即提交快照** | 防止后续 Lint 自我修复损坏代码 |
| Lint 双绿灯通过 | **必须提交** | 作为阶段 2 的最终完成点 |
| 每个独立功能模块完成 | 建议提交 | 便于 Code Review 和问题回溯 |

### 提交 Message 格式（强制）

与 `android-lint-rules` 仓库保持一致，**所有 Commit Message 必须使用中文**，遵循语义化提交规范：

```
格式：<type>(<scope>): <subject>

type 可选值：
  特性 (feat)  — 新功能
  修复 (fix)   — Bug 修复
  重构 (refactor) — 不改功能的代码重构
  格式 (style) — 仅格式/空白/注释变化
  性能 (perf)  — 性能优化
  测试 (test)  — 新增或修改测试
  构建 (build) — 构建/依赖变更
  文档 (docs)  — 文档变更

示例：
  特性(用户中心): 新增头像裁剪上传功能
  修复(首页Feed): 修复列表快速滑动时图片闪烁问题
  重构(网络层): 统一错误码处理逻辑，迁移至 ErrorHandler
```

### 禁止事项
- **严禁 `git commit -m "fix"` / `"update"` / "测试" 此类无意义提交**。
- **严禁在 Lint 未通过时提交**（保护快照只提交编译通过节点）。
- **严禁 force push 到 `main`/`master`**，除非用户明确授权。

---

## 12. 大需求拆分策略 (Large Feature Decomposition)

> **触发条件**：需求涉及 ≥3 个页面、≥2 个模块、或预估编码时间超过单次 Session 能完成的范围。

### 拆分原则：最小可验证单元 (MVU)

每个 MVU 必须满足：
1. **独立可编译**：单独完成后能编译通过，不依赖其他 MVU 的未完成部分。
2. **独立可测试**：至少有 1 条可执行的验收路径（可以是 Mock 数据驱动）。
3. **独立可回滚**：单个 MVU 出问题时，不影响其他已完成的 MVU。

### 拆分输出格式

在阶段 1 输出 BDD 时，若判定为大需求，**必须同时输出拆分计划**：

```markdown
## 需求拆分计划

| MVU # | 范围 | BDD 覆盖 | 依赖项 | 预估状态 |
|---|---|---|---|---|
| MVU-1 | 页面骨架 + Mock 数据展示 | Given-1, When-1 | 无 | 待开始 |
| MVU-2 | 接口对接 + 真实数据渲染 | Then-1, Given-2 | 后端 API Ready | 待开始 |
| MVU-3 | 错误态 + 空态 + 边界处理 | When-2, Then-2 | MVU-2 完成 | 待开始 |
```

### Session 断点续传规则

每次 Session 结束时，AI **必须将当前进度写入 `local.yaml`**（通过提示用户手动更新）：

```yaml
delivery:
  phase: "coding"           # 当前所处阶段
  current_mvu: "MVU-2"     # 当前正在进行的 MVU
  completed_mvus: ["MVU-1"] # 已完成的 MVU 列表
  last_commit: "abc1234"    # 最后一次 Git 快照的 commit hash
```

下次 AI 接手时，读取此配置，**从 `current_mvu` 续接**，不重复已完成工作。

---

## 13. Compose 专项规范 (Jetpack Compose Rules)

> **触发条件**：项目中存在 `@Composable` 函数、或 diff 涉及 Compose 相关文件时生效。

### 强制底线

1. **`LaunchedEffect` key 规则**：
   - 必须传入能唯一标识"副作用执行时机"的 key（如 `userId`、`orderId`）。
   - **严禁使用 `LaunchedEffect(Unit)` 来代替 `init` 逻辑**（这会在 Recomposition 时重复触发）。
   - 需要只执行一次的副作用，必须使用 `LaunchedEffect(key1 = true)` 或移到 ViewModel 的 `init {}` 块中。

2. **`remember` vs `rememberSaveable`**：
   - 普通的 UI 临时状态（如展开/折叠）用 `remember`。
   - **需要在屏幕旋转或进程恢复后存活的状态**（如表单输入、滚动位置），必须用 `rememberSaveable`。
   - 严禁把 ViewModel 内的状态用 `remember` 在 Composable 内复制一份。

3. **State Hoisting 边界**：
   - 遵循"状态下移，事件上提"原则。
   - **严禁在叶子 Composable 中直接调用 ViewModel**。叶子组件只接收数据参数和事件回调。
   - 页面级 Composable（Screen）才能持有 ViewModel 引用。

4. **`derivedStateOf` 使用时机**：
   - 只有当某个计算结果依赖的 State 变化频率**高于**该结果实际需要更新的频率时，才使用 `derivedStateOf`（防止 Recomposition 爆炸）。
   - 对简单的属性访问直接用，不要过度使用 `derivedStateOf`。

5. **Preview 状态覆盖要求**：
   - 每个有多种展示状态的 Composable，必须提供对应的 `@Preview`：
     - `LoadingPreview`
     - `EmptyPreview`
     - `ErrorPreview`
     - `SuccessPreview`（含数据）
   - **严禁只写一个 Happy Path Preview 就认为覆盖完整**。

6. **性能红线**：
   - 严禁在 `@Composable` 函数体内直接创建 `remember {}` 内的 Lambda 对象（导致每次 Recomposition 都创建新对象）。
   - 列表场景必须为 `LazyColumn`/`LazyRow` 的每个 `item` 提供稳定的 `key`，防止列表动画错乱。

---

## 14. 埋点与 Analytics 验证 (Tracking & Analytics Validation)

> **触发条件**：需求文档、PRD 或用户描述中出现"埋点"、"上报"、"统计"、"Analytics"、"事件"等关键字时生效。

### 埋点三要素核查

编码完成后，必须逐一核查：

1. **触发时机是否正确**：
   - 曝光埋点：在元素进入可视区域时触发，不是在页面 `onCreate` 时。
   - 点击埋点：在用户点击的那一刻触发，而不是在请求成功后。
   - 结果埋点（成功/失败）：必须在回调返回后触发，并携带结果状态参数。

2. **参数字段是否完整**：
   - 对照埋点文档（tracking plan），逐字段核查参数名（注意大小写、下划线vs驼峰）。
   - 所有参数必须有空值/默认值兜底，防止因字段缺失导致埋点平台解析错误。
   - **严禁把用户个人信息（手机号、UID 明文等 PII）直接作为埋点参数上报**。

3. **Debug 与生产环境隔离**：
   - Debug 包的埋点必须打印到日志（便于验证），同时**不得上报到生产数据看板**。
   - 严禁在 release 包中保留 `Log.d("Analytics", ...)` 这类调试日志。
   - 推荐使用项目已有的埋点封装（如 `AnalyticsHelper`、`TrackingManager`），严禁绕过封装直接调用底层 SDK。

### 无埋点文档时的处理

如果需求涉及埋点但没有提供埋点文档（tracking plan）：
- **不得凭空编造埋点事件名和参数**。
- 必须用 `TODO("需要埋点文档确认事件名和参数")` 占位。
- 在 DoD 清单里标注"埋点验证：⚠️ 待埋点文档确认，当前为占位"。
