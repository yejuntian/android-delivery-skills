---
name: android-delivery-workflow
description: Android 新需求、需求变更、Bug 修复和功能迭代的完整交付总入口流程。适用于用户提供需求描述、需求文档、UI 链接、截图、接口文档、动态配置或测试要求时，先做需求理解并等待确认；需求确认后直接编码；编码完成后按 UI、接口契约、业务逻辑、数据存储、系统能力识别影响面，再编排实际 diff 变更审查、接口实现契约审查、UI 验证、测试交付、稳定性审查和代码质量审查；未涉及的专项审查应跳过并说明原因。资料缺失、高风险或继续编码会脑补生产逻辑时才在编码前暂停提问。
---

# Android 需求交付总入口

## 共享规则

执行本 Skill 前，必须先遵守 `../_shared/android-global-rules.md`：默认中文输出、动态资料不写死、接口和 UI 不确定时不脑补、不伪造验证结果、发现问题默认先报告不自动修复。

## 定位

这是 Android Skills 套件的总指挥，用来处理一次完整 Android 需求交付。标准路径是：读取资料 → 需求理解 → 用户确认 → 直接编码 → 编码后审查和验证 → 最终交付报告。

本 Skill 不把专项 Skill 固定插在编码前。需求确认后不再默认输出一轮分析报告；只有遇到阻塞或用户明确要求“先分析别改”时，才暂停并输出对应分析。

专项 Skill 的默认位置：

- `android-change-review`：编码后审查实际 diff、影响范围、无关改动和回归风险；只有变更范围不清或用户要求先分析时才前置。
- `android-api-contract-review`：编码后审查接口实现是否符合契约；只有关键接口资料缺失、继续写会脑补字段或 endpoint 时才前置。
- `android-ui-verify`：编码后做 UI 还原、截图或视觉验证；只有缺少必要设计资料且无法低风险实现时才前置提问。
- `android-test-delivery`：编码后生成/执行测试矩阵、构建、单测、lint、仪器测试或人工验证路径。
- `android-stability-review`：编码后检查崩溃、内存泄漏、ANR、协程、生命周期和 Android 版本兼容。
- `android-code-quality-review`：编码后检查架构一致性、最小修改、资源规范、重复逻辑和测试覆盖。

## 外部智能体与工具调用策略

总原则：需求确认前保持轻量；需求确认后直接编码；编码后再按实际改动调用审查和验证能力。

- 需求理解：只读取需求文档、截图、链接和用户补充；默认不调用 Android CLI、Gradle、adb 或 Firebase MCP。
- 需求确认后：开始编码。编码前不固定输出 `android-change-review`、`android-api-contract-review`、`android-ui-verify`、`android-test-delivery`、稳定性或代码质量报告。
- 编码过程中：内部识别项目事实、复用现有封装、控制最小修改范围；除非遇到阻塞，否则不打断用户。
- 阻塞处理：如果缺少关键 UI / 接口 / 字段 / 枚举 / 业务规则，继续编码会变成猜测或高风险改动，必须暂停说明缺口并请用户确认下一步。
- Android CLI / Gradle / adb：只在真实构建、安装运行、单测、lint、仪器测试、截图、logcat、设备兼容验证时使用；不可用时退回项目已有 Gradle/adb 命令或标记未验证。
- Firebase MCP：仅当需求或问题涉及 Firebase、Crashlytics、Remote Config、Analytics、AB 实验、线上崩溃、线上配置或埋点分析时使用；未配置、无权限或无法访问时必须说明。
- 线上或设备验证结果不得伪造；没有实际运行就只能写“未验证”。

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

## 影响面识别与路由

需求理解阶段必须先判断本次需求影响面，并在“当前需求理解”中输出：

- UI：是否涉及页面布局、资源、文案、状态展示、交互、Adapter、Compose/XML。
- 接口契约：是否涉及 endpoint、请求参数、响应字段、DTO、mapper、Repository 网络层、缓存字段。
- 业务逻辑：是否涉及规则判断、状态流转、排序筛选、权限判断、计费、实验开关、数据计算、入口条件。
- 数据存储：是否涉及数据库、缓存、DataStore、SharedPreferences、文件、迁移或旧数据兼容。
- 系统能力：是否涉及权限、通知、后台任务、文件、WebView、DeepLink、系统版本兼容。

如果某一类影响面明确未涉及，编码后不得强行调用对应专项审查，只需在最终报告中说明“未涉及，已跳过”。

### 轻量 diff 触发规则

编码后必须基于实际 diff 快速复核影响面，不做全量矩阵分析，只判断是否触发专项审查：

- 修改 `res/layout`、`res/drawable`、`res/values`、Activity、Fragment、Adapter、Composable，且存在设计稿、截图或可对比基准：触发 `android-ui-verify`。
- 修改 UI 相关文件但没有设计稿、截图或可对比基准：跳过设计稿一致性验证，只在变更审查、稳定性审查或代码质量审查中做必要的 UI 基础检查。
- 修改 Api、Service、Request、Response、DTO、mapper、网络 Repository、缓存字段：触发 `android-api-contract-review`。
- 修改 Entity、Dao、Database、DataStore、SharedPreferences、缓存结构：触发数据兼容检查。
- 修改 AndroidManifest、权限、通知、后台任务、WebView、DeepLink、文件访问：触发系统能力和版本兼容检查。
- 仅修改 if/when 判断、状态计算、排序筛选、权限条件、开关逻辑：按业务逻辑路径处理。

如果需求判断为未涉及 UI / 接口，但实际 diff 修改了相关文件，必须重新标记影响面并说明原因；否则按未涉及跳过，不展开额外报告。

### 路由规则

- 仅业务逻辑变更：
  - 必须关注：`android-change-review`、`android-test-delivery`、`android-stability-review`、`android-code-quality-review`。
  - 默认跳过：`android-ui-verify`、`android-api-contract-review`。
  - 除非业务逻辑改变了 UI 状态展示，否则不做 UI 还原验证。
  - 除非业务逻辑改变了接口字段、请求参数、DTO、mapper、Repository 网络行为或缓存结构，否则不做接口契约审查。
- UI 变更：
  - 有设计稿、截图或可对比基准时包含 `android-ui-verify`。
  - 没有设计稿、截图或可对比基准时跳过设计稿一致性验证，并说明“设计资料缺失，未验证与设计稿一致”。
  - 如果只是 UI 展示，不涉及接口字段或请求逻辑，跳过 `android-api-contract-review`。
- 接口 / 数据契约变更：
  - 必须包含 `android-api-contract-review`。
  - 如果接口变更影响 UI 状态展示，再包含 `android-ui-verify`。
- 数据存储 / 缓存变更：
  - 必须额外关注旧数据兼容、迁移、默认值、清缓存、降级路径和回滚风险。
- 系统能力变更：
  - 必须额外关注 Android 版本兼容、权限降级、生命周期和设备验证。

## 完整工作流

这是一个由 `delivery.py` CLI 状态机驱动的极简版需求交付工作流。作为 AI，你不再需要自己判断复杂的上下文和流转逻辑，只需严格听从脚本的输出指令。

### 执行手册

请严格按照以下三个阶段、通过运行 Python 脚本推进流程。**每次运行脚本后，必须严格遵循终端输出中带有“👉 AI 指令”的提示内容。**

#### 阶段 1：初始化需求理解

首先运行以下命令：

```bash
python3 ai-skills/android-delivery-skills/scripts/delivery.py init --config profiles/local.yaml
```

**AI 动作**：将脚本输出的内容整合后输出“当前需求理解”。输出完毕后，**必须立即结束当前回合，等待用户确认**。不要急着进入下一步。

#### 阶段 2：环境检查与编码

在用户明确回复“确认”、“可以开始做”之后，运行以下命令：

```bash
python3 ai-skills/android-delivery-skills/scripts/delivery.py check-env --config profiles/local.yaml
```

**AI 动作**：如果检查通过，请按需读取 `AGENTS.md`、`README.md` 等项目背景资料，然后开始编写代码。
**强制约束**：代码编写完成后，输出简短的“已修改文件总结”，**必须立即结束当前回合**，绝对不要在同一个回合里做任何其他的审查动作！

#### 阶段 3：审查路由分析

代码写完的回合结束后，在紧接着的新回合里，运行以下命令：

```bash
python3 ai-skills/android-delivery-skills/scripts/delivery.py route --config profiles/local.yaml
```

**AI 动作**：脚本会根据你刚写的 `git diff` 自动决定需要触发哪些专项审查 Skill（例如 `android-ui-verify` 或 `android-api-contract-review`）。请严格按照终端列出的清单，**逐个单独调用对应的 Skill**。
- 一次只查一项。
- 不要自行脑补脚本未列出的审查项。

## 资料缺失兜底 (Contract-First 降级策略)

如果在编码过程中缺乏关键资料（如 API 缺失接口文档、UI 缺少设计图），**不得直接停止工作或罢工**。请采取以下降级策略保证工程骨架完整：

1. **TODO 显式占位**：架构、类结构、ViewModel 和业务逻辑依然要写完。对于缺失的 Endpoint、具体请求参数或未知状态，使用 Kotlin 的 `TODO("原因")` 显式占位，将问题暴露在编译期，坚决不瞎编假数据糊弄。
2. **纯前端领域模型与 Mock**：如果缺少整个接口定义，请先构建客户端视角的纯领域模型（Domain Entity），并编写 `FakeRepository` 使用本地 Mock 数据驱动 UI 完成剩余工作。网络层（DTO）留空，等待后续 API 就绪。
3. **安全默认值兜底**：处理不明确的 API 字段时，所有的基础类型必须 `nullable` 或提供业务上安全的 default value。对于未明确的枚举状态，必须包含一个 `UNKNOWN` 兜底，防止线上 NPE。
4. **风险强提示**：编码结束后，必须在当前回合的输出总结中，明确列出所有打上了 `TODO` 的位置和采取了 Mock 降级的地方。
