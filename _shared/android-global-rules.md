# Android Skills 共享全局规则

适用于 `android-delivery-skills` 下所有 Android Skill。只保留跨项目通用约束，不写公司私有信息。

## 默认输入

- 默认读取 Skill 套件根目录下的 `profiles/local.yaml`，用户不需要每次重复说明。
- `profiles/local.yaml` 是日常入口，通常只维护：
  - `project_path`：Android 项目路径
  - `branch`：目标分支
  - `requirement_file`：需求文档路径
  - 可选 `ui`：UI 链接 / 截图
  - 可选 `api`：接口链接 / 接口文件
- 用户也可以在对话中临时覆盖这些信息。

## 语言要求

- 默认使用中文输出需求理解、分析、报告、风险和验证结果。
- 命令、路径、文件名、类名、方法名、字段名、日志关键字保留原文。

## 需求文档规则

- `requirement_file` 只代表需求正文、评审记录和验收标准来源。
- 不要求需求文档包含 UI 截图、设计稿或接口文档。
- UI 资料优先从 `ui.links`、`ui.screenshots` 或用户补充中读取。
- 接口资料优先从 `api.links`、`api.files` 或用户补充中读取。
- 如果需求文档无法读取或信息不足，必须说明缺失内容，不得脑补。

## 需求理解规则

- **强制检查点：读完 `profiles/local.yaml` 和 `requirement_file` 后必须立即输出"当前需求理解"，不得继续默默读取 AGENTS.md、README、Gradle 等项目文件。项目文件在用户确认需求、进入编码阶段时再按需读取。**
- 第一步必须先做需求理解，等待用户确认。
- 用户补充或纠正后，必须重新整理需求理解。
- 需求理解必须包含影响面判断：UI、接口契约、业务逻辑、数据存储、系统能力。
- 需求理解未确认前，可以输出“初步影响范围（待确认）”和待确认问题。
- 需求理解未确认前，不得输出最终方案、不得修改代码、不得把假设当事实。
- 用户明确确认需求后，默认直接进入编码；不要固定插入需求变更分析、接口分析、UI 分析、测试计划、稳定性风险或代码质量报告。
- 只有用户明确要求“仅分析 / 先别改 / 只报告”或遇到阻塞时，才在编码前暂停输出分析。

## 项目路径与分支规则

执行代码修改、构建、测试或 Git 操作前，必须检查：

1. `project_path` 是否存在。
2. `project_path` 是否是 Git 仓库。
3. 当前分支是否等于 `branch`。
4. 工作区是否有未提交改动。

默认安全策略：

- 分支不匹配时停止修改，报告当前分支和目标分支。
- 工作区有改动时列出变更文件，避免覆盖用户已有改动。
- 不得默认自动切分支、建分支、stash、reset、checkout、clean。
- 只有用户明确要求后，才能执行对应 Git 操作。

## 不确定信息处理

遇到需求、UI、接口、字段、枚举、错误码、埋点、灰度或测试环境不确定时，必须区分：

- 已确认
- 合理假设
- 待确认
- 阻塞项

待确认内容不得写入正式生产逻辑。阻塞项是指继续编码会明显导致脑补、误改或高风险破坏；遇到阻塞项必须暂停并请用户确认。

## 强制工具链兜底策略 (Forced Toolchain Fallbacks)

在遇到以下三大复杂疑难杂症时，**严禁凭空盲猜或仅靠代码分析，必须强制调用特定的工程工具进行诊断**：

1. **复杂 UI 调试（防盲猜布局）**：如果调整 UI 时元素不可见、尺寸异常或被遮挡，严禁凭空修改 XML 参数试错。必须强制调用 `android layout` (或同等 Dump 脚本) 拉取当前设备的真实 View Tree (JSON)，根据实际测绘尺寸和渲染状态定位问题。
2. **性能与卡顿分析（防背诵八股文）**：遇到卡顿、ANR 或内存泄漏优化任务时，禁止直接修改业务代码或背诵通用优化理论。必须要求用户提供 Trace 或 Heap Dump 文件，并优先调用 `perfetto-trace-analysis` 等专项技能通过 SQL 数据分析找到确切瓶颈。
3. **深层 Gradle 冲突（防盲猜版本号）**：遇到 `Duplicate class` 或深层依赖库版本冲突导致构建失败时，严禁盲目修改 `build.gradle` 的版本号撞运气。必须强制运行 `./gradlew app:dependencies` (或相关模块的 dependencies task) 打印完整依赖树，分析确切冲突链路后使用 `exclude` 精准解决。
4. **Release 包混淆闪退（防乱关混淆）**：遇到 Release 包特有的 `ClassNotFoundException` 等混淆问题时，严禁大面积使用通配符 `-keep class **` 关闭混淆！必须强制要求使用 `r8-analyzer` 技能（或查阅 `usage.txt` / `mapping.txt`），精准定位被缩减的类，仅针对引发崩溃的最小闭环添加 Keep 规则。
5. **协程与异步生命周期（防内存泄漏）**：处理协程生命周期异常或并发时序问题时，绝对禁止使用 `GlobalScope` 逃避生命周期，绝对禁止使用 `delay()` 掩盖时序报错。必须强制追溯宿主生命周期状态，严格使用 `viewModelScope` 或 `repeatOnLifecycle` 进行重构。
6. **大版本适配与权限（防盲猜废弃 API）**：涉及 Android 权限申请（存储、相册、通知等）和隐式 Intent 跳转修改时，严禁依赖模型自身的“记忆”！必须强制调用 `android docs search` 等命令查阅目标 API Level 的官方变更指南，以最新规范为准修改 Manifest 和代码。

## 外部资料读取策略（非终止）

在进入需求理解前，优先读取用户本次输入或 `profiles/local.yaml` 中提供的资料，但外部链接不可读不得默认终止整个流程。

资料读取优先级：

1. 用户本次对话中的明确文字、截图、文件路径和补充说明。
2. 本地资料：`ai-skills/tempfile/`（由 Figma 导出的本地离线标注与 JSON 树）、`requirement_file`、`requirement_dir`、`ui.directory`、`ui.screenshots`、`ui.assets`、`api.files`。
3. 结构化工具：Figma MCP、Figma REST API、YApi/Apifox/OpenAPI/Postman 导出、平台 MCP/CLI/API。
4. 浏览器可见页面：只读取用户已授权后页面上可见的内容，不读取 Cookie、Token、密码或会话存储。
5. 外部网页直读：公开页面、公开 API 或无需登录的导出接口。

执行规则：

- 能读到的资料立即纳入需求理解和实现依据。
- 外部链接返回 401、403、请登录、无权限、前端壳页面、空数据或关键内容不可见时，只记录为“外部资料未读取”，不要直接终止流程。
- 如果本地资料、用户文字或其他可用资料足以理解需求，继续进入需求理解；在待确认问题和最终报告中标记未读取链接及剩余风险。
- 只有在“该链接是唯一关键资料，且没有任何替代资料，继续编码必然脑补 UI / 接口 / 业务规则”时，才暂停请求用户补充资料或授权。
- 用户说“哪个行得通就走哪个”“先按现有资料做”“跳过链接”“用 mock / fake / sampledata”时，必须降级继续，不得卡在授权流程。
- Figma 资料默认优先通过 Figma MCP 读取结构化设计数据，例如 design context、metadata、variables/styles、component variants 和 screenshot；MCP 不可用、权限不足或返回不完整时，再使用本地 Figma 离线标注数据（`ai-skills/tempfile/[file_key]_[node_id]_spec.json`，读取前须先检查 `source.exported_at` 新鲜度，超过 4 小时对比 Figma `lastModified`，超过 24 小时须在 Design Spec Gate 标注 `⚠️ 数据可能过期`）；仍不可用再尝试 `FIGMA_TOKEN` 环境变量驱动的 Figma REST API；最后才退回本地截图/资源包或标记未验证。
- YApi / Apifox / Swagger 链接不可读时，优先尝试导出 JSON、OpenAPI、Postman collection 或本地接口文件；仍不可用且需求要求接正式接口时，才暂停确认。

外部资料读取失败记录模板：

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

安全边界：

- Token、Cookie、账号、密码不得写入 `local.yaml`、需求文档、Skill 或 Git 仓库。
- 不得要求用户手动提供 Cookie、账号或密码。
- 如需 Personal Access Token，只能建议放到环境变量、系统钥匙串或本机密钥管理器；不得硬编码或提交。
- 不得绕过平台权限、伪造授权结果或声称读取了未实际读取的资料。
- 无法读取授权资料时，必须说明未验证项和剩余风险，不得声称已确认设计稿或接口契约。

## 资料缺失时

- UI 未确认：如果需求允许低风险实现，可以按项目现有组件风格编码；如果要求像素级还原，必须暂停确认。
- 接口未确认：如果用户允许，可以先做 mock / fake / sampledata 或领域模型草案；如果要求接正式接口，必须暂停确认。
- 字段未确认：不能写死假字段；只能使用 Unknown / default 兜底或暂停确认。
- 测试环境缺失：编码后只生成测试用例和人工验证路径，不伪造测试结果。

## 当前项目优先

所有方案必须服从当前项目事实，优先读取或识别：

- `AGENTS.md`
- `README.md`
- `CONTRIBUTING.md`
- Gradle 配置
- CI 配置
- 相关模块已有代码和测试

不得假设项目一定使用 Compose、Hilt、Retrofit、Room、Coroutines、Flow 或某个固定架构。

## 项目规则优先

如果目标项目存在 `AGENTS.md`、`CONTRIBUTING.md` 或其他项目级规则，且其修改审批、代码规范或验证要求比本 Skill 更严格，必须优先遵守项目级规则。

尤其当项目 `AGENTS.md` 要求修改前展示 diff、修改预览或详细方案并等待用户明确同意时，不得因为本 Skill 写了“需求确认后直接编码”而绕过审批流程。

## 新需求修改预览

对于新需求，即使没有相同业务参照，也必须在修改前先识别最小落点并输出修改预览。

修改预览至少包含：

- 准备新增或修改哪些文件。
- 新功能放在哪个模块、页面、入口或包路径下。
- 为什么这样放，是否符合当前项目结构。
- 是否复用已有主题、资源、组件、架构层或工具类。
- 明确不改哪些范围，例如不改接口、不改业务逻辑、不改其他页面。

如果无法确认落点、入口、UI 技术或业务边界，必须先暂停确认，不得直接创建文件。

## 单一职责边界

每个 Skill 阶段必须只处理自己的职责，不得把其他阶段的判断、实现或审查混入当前 Skill。

- `android-delivery-workflow`：只负责需求理解、影响面识别、阻塞确认、路由编排和最终汇总。
- `android-change-review`：只负责实际 diff、业务逻辑、变更范围、架构边界、回归和上线风险审查。
- `android-api-contract-review`：只负责接口、DTO、请求响应、mapper、Repository 网络行为、缓存字段和契约兼容审查。
- `android-ui-verify`：只负责 UI 还原、设计稿/截图一致性、资源规范、页面状态和可见轻交互的 UI 表现验证；不得判断或实现接口、业务规则、数据存储、权限、登录、支付、下载、提交、保存等真实业务能力。
- `android-test-delivery`：只负责测试用例、验证命令、执行结果、失败项、未验证项和剩余风险。
- `android-stability-review`：只负责崩溃、生命周期、协程、内存泄漏、ANR、资源释放和 Android 版本兼容风险。
- `android-code-quality-review`：只负责代码质量、可维护性、架构一致性、资源规范、重复逻辑、依赖边界和测试覆盖风险。

如果当前 Skill 发现问题属于其他职责范围，只能记录为“需要路由到对应 Skill / 需要用户确认”，不得在当前 Skill 中扩展处理或替代其他 Skill。

## 修改与验证边界

- 默认先做需求理解；需求确认后直接编码。未经用户确认需求，不修改代码。
- 高风险变更必须二次确认，例如 Gradle、依赖、数据库迁移、登录、支付、权限、WebView、CI、签名、混淆、公共组件。
- 不得伪造构建、测试、lint、截图、logcat 或设备验证结果。
- 无法验证时必须说明原因、剩余风险和建议验证方式。
- 编码后发现风险默认先报告，不自动扩大修复范围；用户明确说“修复”或“继续处理”后才修改。

## 外部智能体与工具规则

- `android-delivery-workflow` 作为总入口；专项 Skill 默认放在编码后按实际改动调用，不要一开始无差别展开所有流程。
- 编码后必须按实际 diff 轻量复核影响面：未修改 UI 相关文件时跳过 UI 还原验证；修改 UI 相关文件但没有设计稿、截图或可对比基准时跳过设计稿一致性验证，只做必要的 UI 基础检查；未修改接口、DTO、mapper、Repository 网络行为或缓存结构时跳过接口契约审查；如果 diff 与需求影响面不一致，必须重新标记并说明原因。
- `android-change-review` 默认用于编码后审查实际 diff；只有用户要求先分析或变更范围阻塞时才前置。
- `android-api-contract-review` 默认用于编码后审查接口实现；只有关键接口资料缺失导致无法安全编码时才前置。
- `android-ui-verify` 默认用于编码后 UI 验证；只有关键设计资料缺失导致无法实现时才前置。
- `android-test-delivery`、`android-stability-review`、`android-code-quality-review` 默认用于编码后验证和审查。
- 涉及 Figma UI 还原时，编码前先输出一份精简 Design Spec Gate，至少包含 target screen、resource tokens、layout structure、component mapping、assets 和 risks/assumptions；这属于实现闸门，不等同于额外展开一轮完整分析报告。
- Figma UI 实现顺序默认是：resources → text styles → drawable/selector → layout XML → minimal Kotlin/ViewBinding；不要先堆完整 XML 再回头补资源。
- Android CLI、Gradle、adb 只在需要真实构建、安装运行、自动测试、截图、抓日志、设备兼容验证时调用。
- 需求理解阶段默认不调用 Android CLI；需求未确认前不得用构建或设备结果反推需求结论。
- Firebase MCP 只在涉及 Firebase、Crashlytics、Remote Config、Analytics、AB 实验、线上崩溃或线上配置时调用。
- 外部工具不可用、未登录、无权限、无设备或无网络时，必须如实报告，并给出替代验证方式。
- 所有风险、异常、内存泄漏、ANR、兼容性和线上问题发现点默认先报告，不自动修复。

## 大厂级工程规范与自适应约束

除了解决 Bug 和实现功能，必须强制遵守以下顶级开源项目的工程纪律。AI 必须具备“环境嗅探”能力，根据项目实际架构采取适配动作：

### 1. 多模块架构防腐（防跨层乱引依赖）
- **嗅探规则**：添加任何跨模块依赖或新依赖前，必须先检索根目录 `settings.gradle` / `settings.gradle.kts`。
- **强制约束**：如果发现项目采用多模块架构（包含 `:core`, `:feature` 等），**严禁底层模块（如 `:core`）反向依赖上层模块（如 `:feature`）**，严禁引入循环依赖。
- **处置方案**：必须优先查阅 `AGENTS.md` 或 `README.md` 中的架构分层图。如果不确定依赖方向，必须拒绝修改依赖并向用户抛出阻塞警告。

### 2. Version Catalog 统一版本管理
- **嗅探规则**：在修改或添加库依赖前，必须先探测 `gradle/libs.versions.toml` 文件是否存在。
- **强制约束**：
  - **如果存在**：一票否决任何在 `build.gradle` 中直接写死版本号的行为（如 `implementation 'xx:1.0'`）。必须将库注册到 TOML 的 `[versions]` 和 `[libraries]` 中，并通过 `libs.xxx` 引用。
  - **如果不存在**：允许使用传统 `build.gradle` 写法，但对于同类库（如 Retrofit, OkHttp）优先提取统一的版本号变量。

### 3. A11y 与 I18n 一票否决（强制底线）
- **适用范围**：无视项目架构，所有项目强制适用。
- **强制约束**：
  - **I18n（国际化）**：绝对禁止在 XML 布局或 Kotlin 代码中出现硬编码的中/英文字符串（如 `android:text="登录"`）。所有面向用户的文本，必须抽取到 `res/values/strings.xml` 中。
  - **A11y（无障碍）**：所有非纯装饰性质的 `ImageView`、`ImageButton` 或带有点击事件的图标，必须强制补齐具有实际意义的 `android:contentDescription` 属性（或通过 `@string` 引用），否则代码审查按不合格处理。
