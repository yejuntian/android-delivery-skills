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
| DTO、Api 接口、Repository、mapper | `android-api-contract-review` |
| XML 布局、资源、Activity/Fragment/Compose，且有设计稿/截图 | `android-ui-verify` |
| 任意业务逻辑变更 | `android-stability-review` + `android-code-quality-review` |
| 任意变更 | `android-change-review` + `android-test-delivery` |
| 修改了 XML 但无设计稿或截图 | 跳过 `android-ui-verify` 的设计稿一致性部分，说明"设计资料缺失，未验证" |

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

### android-ui-verify 强制审查门限
在做 UI 验证时，**打勾"完成"之前**必须先输出 Markdown 表格，列出所有 `<TextView>`，逐一检查是用的 `android:text` 还是 `tools:text`，符合量化规则后才能逐项打勾完成。此外：
- `targetSdk >= 35` 时**必须额外检查 edge-to-edge / WindowInsets**，确认内容未被状态栏或导航栏遮挡。
- Figma 导出的 `.png` 文件可能实际是 SVG 内容，导入前必须验证格式，必要时转成 VectorDrawable。

### android-code-quality-review AI 生成代码专项检查
审查 AI 自己写的代码时，必须额外确认以下反模式是否存在：
- 假设了项目中不存在的字段、接口或工具类。
- 生成了看似完整、但实际无法运行的代码骨架。
- **为了让编译通过而牺牲了业务正确性**（如把类型改成 `Any`、删除关键业务判断）。
- Fragment 中的 `private lateinit var binding` 没有在 `onDestroyView` 中置空。

### android-change-review 爆炸半径底线
- 局部 Feature 的 Bug 修复，**严禁为了图省事去修改 Base 类、公共网络库或底层 Core 组件**，必须在局部作用域内消化。
- 审查是否混入了与本次需求无关的格式化、重命名或重构。

### android-test-delivery 黑盒状态驱动原则
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
