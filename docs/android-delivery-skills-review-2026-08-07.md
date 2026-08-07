# Android Delivery Skills 审查问题汇总

> 审查日期：2026-08-07
>
> 审查范围：`android-delivery-skills` 全部 9 个 Skill、共享规则、脚本、配置、测试与路由契约
>
> 当前状态：仅完成审查与问题复现，以下问题尚未修复

## 1. 结论

仓库基础结构、校验和测试体系完整，但存在 **7 个核心问题：1 个 P0、6 个 P1**。主要风险集中在：

1. 归档失败可能删除原始需求数据。
2. JUnit 和 UI 证据无法可靠证明结果来自本轮执行。
3. setup 默认配置、channel 状态和 Skill 路由存在契约冲突。

现有测试均通过，但未覆盖上述失败路径和证据真实性边界，不能据此判定交付链路安全。

## 2. 核心问题

| ID | 优先级 | 问题 | 主要影响 | 建议方向 |
|---|---|---|---|---|
| ADS-001 | P0 | 归档失败仍删除源需求目录 | 归档不完整时可能永久丢失需求数据 | 改为 fail-closed，完整校验后再删除源目录 |
| ADS-002 | P1 | 旧 JUnit 报告可冒充本轮测试 | 未实际执行测试也可能得到通过结果 | 绑定执行 ID、进程时间、项目输出目录和构建身份 |
| ADS-003 | P1 | setup 默认配置不可用 | 按模板初始化后仍会被工作区策略拒绝 | 统一模板与路径策略，setup 后自动执行 doctor |
| ADS-004 | P1 | 无效 channel 可标记为 `MERGED` | 拼错或不存在的渠道可形成虚假集成状态 | 状态更新前校验 channel 注册、工作区和前置状态 |
| ADS-005 | P1 | UI 验证证据可假绿 | 无法证明截图来自本轮 APK、设备和验证过程 | 绑定 APK、设备、安装收据、截图和执行 ID |
| ADS-006 | P1 | Figma 主路由定义冲突 | 可能绕过计划确认、总入口或最终验证 | 固定编排入口和 provider 职责 |
| ADS-007 | P1 | UI Skill 调用策略冲突 | 模型无法确定自动调用、手动调用还是跳过 | 统一自动编排与独立调用边界 |

### ADS-001：归档失败仍删除源需求目录

证据：

- [`scripts/requirement_workspace.py:475`](../scripts/requirement_workspace.py#L475)
- [`scripts/requirement_workspace.py:565`](../scripts/requirement_workspace.py#L565)

已使用 `docs/` 内悬空符号链接复现：归档内容不完整，但源需求目录仍被删除。

建议流程：

```text
复制到临时归档目录
→ 校验文件数量、类型和必要内容
→ 原子重命名为正式归档目录
→ 删除源目录
```

任一步失败时必须保留源目录、清理或隔离不完整归档，并返回非零退出码。

验收条件：

- 复制异常、悬空符号链接、权限错误和校验失败时均不删除源目录。
- 只有归档校验完成后才允许删除源目录。
- 增加“归档失败不删除源目录”回归测试。

### ADS-002：旧 JUnit 报告可冒充本轮测试

证据：

- [`scripts/execution_evidence.py:229`](../scripts/execution_evidence.py#L229)
- [`scripts/execution_evidence.py:678`](../scripts/execution_evidence.py#L678)

已复现：对旧的项目外 JUnit XML 执行 `touch` 或 `os.utime()` 后，收集器返回 `collector_exit=0`、测试数为 1，最终校验无错误。

当前主要依靠文件时间判断报告新鲜度，无法证明报告由本轮测试命令生成。

建议至少绑定：

- 本轮唯一 `execution_id`。
- 测试命令、启动时间、结束时间和退出码。
- 报告路径必须位于允许的项目输出目录。
- commit SHA、build variant 和被测 APK 身份。
- Gradle task 与实际生成报告的关联关系。

验收条件：历史报告即使更新时间戳也必须被拒绝；只有本轮命令生成且身份匹配的报告可以通过。

### ADS-003：setup 默认配置不可用

证据：

- [`android-delivery-setup/assets/channel.example.yaml:4`](../android-delivery-setup/assets/channel.example.yaml#L4)
- [`scripts/requirement_workspace.py:190`](../scripts/requirement_workspace.py#L190)

setup 模板默认生成项目内 `document/`，但工作区重叠策略会拒绝该布局，导致用户按默认模板初始化后仍可能无法继续。

建议：

- 明确是否支持项目内工作区，并让模板与校验规则使用同一策略。
- 如果禁止项目内工作区，默认生成项目外路径。
- setup 完成后自动运行 `doctor` 或 dry-run。
- 错误信息提供可直接采用的合法路径示例。

验收条件：全新工程使用默认配置完成 setup 后，工作区初始化和首个需求创建均成功。

### ADS-004：无效 channel 可标记为 `MERGED`

证据：

- [`scripts/requirement_workspace.py:639`](../scripts/requirement_workspace.py#L639)

不存在或拼错的 channel 可以被创建记录并标记为 `MERGED`，形成没有实际渠道对应的集成状态。

状态更新前应强制验证：

- channel 已在当前配置注册。
- channel 已初始化且对应工作区存在。
- 当前状态满足目标状态的前置条件。
- `MERGED` 包含可核验的提交、分支或产物引用。

验收条件：未知 channel、未初始化 channel 和非法状态跃迁全部失败，且不得写入状态文件。

### ADS-005：UI 验证证据可假绿

证据：

- [`scripts/specialist_result.py:154`](../scripts/specialist_result.py#L154)
- [`scripts/specialist_result.py:183`](../scripts/specialist_result.py#L183)
- [`android-verify-ui/SKILL.md:68`](../android-verify-ui/SKILL.md#L68)

当前 UI `PASS` 主要检查非空链接和自报 `device_check`，无法证明 APK、设备、截图和预检属于同一次执行。

建议证据链：

```text
execution_id
→ APK SHA-256 / applicationId / versionCode / variant
→ device serial
→ install receipt
→ launch/activity receipt
→ screenshot metadata
→ specialist result
```

验收条件：历史截图、不同 APK、不同设备、缺失预检收据或执行 ID 不一致时均拒绝 `PASS`。

### ADS-006：Figma 主路由定义冲突

证据：

- [`android-delivery-guide/SKILL.md:27`](../android-delivery-guide/SKILL.md#L27)
- [`android-delivery-guide/SKILL.md:33`](../android-delivery-guide/SKILL.md#L33)
- [`references/skill-catalog.yaml:49`](../references/skill-catalog.yaml#L49)

导航表把 `figma-android-xml` 定义为主 Skill，其他规则又把它定义为计划确认后的 provider，可能导致模型绕过总入口和确认门禁。

建议固定职责：

| 组件 | 单一职责 |
|---|---|
| `android-delivery-guide` | Skill 发现与导航 |
| `android-implement-and-verify` | 唯一交付编排入口 |
| `figma-android-xml` | 计划确认后调用的实现 provider |
| `android-verify-ui` | 编排流程调用的验证 specialist |

验收条件：同一 Figma 实现请求在导航表、catalog 和主流程中产生一致入口与调用顺序。

### ADS-007：UI Skill 调用策略冲突

证据：

- [`android-verify-ui/SKILL.md:15`](../android-verify-ui/SKILL.md#L15)
- [`android-implement-and-verify/SKILL.md:104`](../android-implement-and-verify/SKILL.md#L104)
- [`android-implement-and-verify/references/final-delivery.md:19`](../android-implement-and-verify/references/final-delivery.md#L19)

`android-verify-ui` 要求手动独立调用，但主交付流程又要求按 route 执行专项，自动调用与人工调用边界不明确。

建议统一为：

- 完整交付请求检测到 UI 变更时，由 `android-implement-and-verify` 自动调用 UI specialist。
- 用户明确只验证 UI 时，允许直接调用 `android-verify-ui`。
- 自动与独立模式使用相同证据 Schema 和 PASS 门禁。

验收条件：完整交付、纯 UI 验证和无 UI 变更三类请求均只有一条明确路由。

## 3. 工程补充建议

| 优先级 | 建议 | 目的 |
|---|---|---|
| P2 | 统一脚本的 cwd 和根路径解析规则 | 避免不同入口解析到不同项目或工作区 |
| P2 | 将 9 个 Skill 打包为 bundle/plugin，并增加安装发现 smoke test | 避免源码存在但 Codex 无法发现或隐式触发 |
| P2 | 增加统一 `doctor` | 检查配置、路径、Android 工程能力、Gradle、设备和证据目录 |
| P2 | 明确 `SKIPPED_NO_UI` 到机器状态 `SKIPPED` 的映射 | 统一人读状态和机器 Schema |
| P2 | 为 `android-test-and-fix` 增加 standalone 模式 | 支持不依赖完整交付工作区的独立测试修复 |
| P2 | 扩展 pre-commit 覆盖范围 | 覆盖嵌套脚本、`agents/openai.yaml` 和 `delivery-flow.yaml` |
| P2 | 将完整 401 项测试纳入统一维护命令或 CI | 避免维护命令只执行部分测试 |
| P2 | 精简 `_shared/android-global-rules.md` | 仅保留真正跨 Skill 的安全不变量，降低上下文成本 |
| P2 | setup 复用 `android_project_capabilities.py` | 自动发现 variant、Gradle task 和工程类型 |

## 4. 当前验证基线

| 验证项 | 结果 |
|---|---|
| 官方 `quick_validate.py` | 9/9 Skill 通过 |
| `python3 scripts/validate_maintenance.py` | 4/4 通过 |
| fast eval | 43/43 通过 |
| `scripts/tests` | 376/376 通过 |
| Journey 测试 | 25/25 通过 |
| 前向试用 | 能正确路由到 `android-implement-and-verify`，并停在输入/确认门禁 |

这些结果证明基础结构和主成功路径稳定，但不覆盖 ADS-001 至 ADS-007 的失败路径、来源真实性和跨组件契约冲突。

## 5. 推荐修复顺序

1. 修复 ADS-001：归档 fail-closed，并补失败不删除回归测试。
2. 修复 ADS-002：证明 JUnit 报告来自本轮执行。
3. 修复 ADS-003：统一 setup 模板和工作区策略。
4. 修复 ADS-004：阻断无效 channel 和非法状态跃迁。
5. 修复 ADS-005：绑定 UI 截图、设备预检和当前构建身份。
6. 修复 ADS-006、ADS-007：统一 Figma/UI 路由和调用契约。
7. 补齐 doctor、完整 CI、安装发现测试和上下文精简。

## 6. 完成判定

只有满足以下条件后，才能将本轮审查问题标记为关闭：

1. ADS-001 至 ADS-007 均有对应代码或规则修复。
2. 每个问题至少新增一个能在修复前失败、修复后通过的回归测试。
3. 官方 Skill 校验、维护校验、fast eval、脚本测试和 Journey 测试全部通过。
4. 安装后的 Skill discovery 与关键路由 smoke test 通过。
5. 设计依据、运行规则和机器校验保持一致，不以说明文档代替实际门禁。
