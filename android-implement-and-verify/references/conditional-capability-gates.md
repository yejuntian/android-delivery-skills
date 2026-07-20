# Android 第二轮条件能力门禁

本文定义 OpenAPI、数据迁移、动态泄漏、性能、UI/A11y 和安全隐私六类条件能力。只有需求或实际 diff 触发时才读取并执行；日常需求不应无差别加载全文或运行全部工具。

## 目录

1. [共同原则](#共同原则)
2. [统一记录](#统一记录)
3. [设备与降级](#设备与降级)
4. [OpenAPI](#openapi)
5. [数据迁移](#数据迁移)
6. [动态泄漏](#动态泄漏)
7. [性能](#性能)
8. [UI 与 A11y](#ui-与-a11y)
9. [安全隐私](#安全隐私)
10. [职责归属](#职责归属)
11. [完成结论](#完成结论)

## 共同原则

- 同时结合已确认需求与最终 diff 判断适用性，路径和注解只提供候选证据。脚本候选与 `android-review-diff` v4 的七类 `confirmed_impacts` 取并集，任一来源确认的条件能力都必须进入最终门禁。
- 不适用写明原因；需要但缺少工具、设备、契约、旧数据或基准时写“未验证”，不得改写成通过。
- 先复用目标项目已有依赖、任务、测试框架和报告；不自动安装重型工具或升级 AGP/Gradle。
- 外部工具只采集事实，AI 结合需求与代码判断根因；工具告警不自动等同于生产缺陷。
- 修复后用最终代码重新执行对应门禁，旧报告不算最终证据。
- 不引入通用状态机、CI 聚合、独立 Reviewer 或 Maestro；最终只使用一次性 `delivery-result.json` 统一核对新鲜证据，不保存流程阶段。

## 统一记录

每项条件能力在当前需求追溯表或最终报告中记录：

| 字段 | 内容 |
| --- | --- |
| 能力 | OpenAPI / 迁移 / 泄漏 / 性能 / UI-A11y / 安全隐私 |
| 触发依据 | 对应 `REQ-ID`、`BDD-ID` 和实际 diff |
| 适用性 | 适用 / 不适用及原因 |
| 工具与命令 | 项目已有任务、外部工具或人工路径 |
| 新鲜证据 | 退出码、测试数、指标、报告或产物路径 |
| 结论 | 通过 / 未验证 / 阻塞 |
| 能力损失 | 降级后无法证明的事实 |
| 剩余风险 | 设备、版本、数据或环境风险 |

`不适用` 表示该需求没有对应影响；`未验证` 表示本应检查但缺少条件。两者不得混用。

机器结果中，Diff Reviewer 必须逐项确认 `ui/api/data/system/build/architecture/tests`，适用项绑定真实 diff 文件和原因；这些语义影响用于补充条件门禁，不直接证明专项通过。稳定性专项固定使用必需的 `android-static-semantics`，以及 `android-dynamic-leak`、`android-performance`、`android-security-privacy` 三个条件 capability ID；迁移和 UI/A11y 分别使用 `android-data-migration`、`android-ui-a11y` gate。适用但缺少设备时使用 `UNVERIFIED` 并进入 `pending_capabilities`，同时引用同能力的专项或实际人工阻塞证据；不得用无关构建、Unit 或 Review 证据占位。

## 设备与降级

- 没有实体真机时继续执行全部非真机门禁；模拟器可等价覆盖的迁移、功能、基础 A11y 和泄漏场景继续运行。
- 没有任何设备时继续构建、Unit、lint、OpenAPI、静态迁移、安全配置和代码审查，只把设备项标为未验证。
- 正式性能、厂商 ROM、相机/蓝牙/传感器等真实硬件能力，以及需求明确指定的真机验收，原则上需要真机。
- 缺少真机不停止其他工作，但对应能力不能判通过。若它是明确验收标准，则完整交付受阻；否则可以声明“代码与本地门禁完成，真机专项待验证”。
- 模拟器结果必须标明设备类型，不得写成真机结果。

## OpenAPI

触发：endpoint、请求参数、响应模型、DTO、枚举、错误响应、鉴权或网络缓存契约变化。

- 优先读取本地 OpenAPI/Swagger JSON/YAML 或平台正式导出；链接不可读时按资料降级规则处理。
- 优先运行项目或本机已有的 OpenAPI 校验命令；没有成熟校验器时只做人工契约核验，并标明机器校验未执行。
- 只核对本次涉及的 operation、schema、`required`、`nullable`、类型、格式、枚举和错误响应。
- 契约自身有错误、引用无法解析或与实现冲突时阻断接口通过。
- 不自动执行 OpenAPI Generator 覆盖旧项目手写网络层，也不把未知字段一律 nullable/default。

证据至少包含契约来源、文件摘要或版本、涉及的 operation/schema、命令、退出码和实现映射结果。

## 数据迁移

触发：Room version/schema、Entity/Dao、DataStore、SharedPreferences、Proto、缓存或持久化格式变化。

- 检查旧版本到新版本的连续迁移路径、非空字段默认值、索引、外键、唯一约束和旧数据保留。
- 项目已有 Room schema 和 `MigrationTestHelper` 时执行真实旧库迁移；其他存储沿用项目已有兼容测试。
- 缺少旧 schema、旧样本或可执行测试环境时保持未验证，不能用新库建库成功替代迁移证据。
- 禁止用清数据、卸载重装、删除旧缓存或 `fallbackToDestructiveMigration` 造绿。
- 高风险迁移必须包含失败恢复、降级/回滚和多版本升级风险。

证据至少包含源版本、目标版本、旧数据准备、迁移命令、迁移后断言和报告路径。

## 动态泄漏

触发：Activity/Fragment/ViewBinding、监听器、Receiver、Handler、协程/Flow、Adapter、Dialog、WebView、Camera、Media 等生命周期或资源释放变化，以及明确泄漏问题。

- 先做静态生命周期审查，再按条件复用项目已有 LeakCanary、Heap Dump、Leak Trace 或内存分析流程。
- 不为普通需求自动接入 LeakCanary；已有 debug 能力时才直接使用，新增依赖先确认。
- 静态未发现风险、单次 `dumpsys meminfo` 或页面退出后内存暂未下降，都不能证明无泄漏。
- 没有设备或动态证据时继续其他门禁，并写“静态审查完成，动态泄漏未验证”。
- 修复后以相同进入/退出路径和次数重验，记录最短强引用链或等价证据。

## 性能

触发：明确性能验收，或启动、列表、图片、数据库、序列化、大循环、主线程、锁、ANR/卡顿等性能敏感改动。

- 阈值优先来自需求、项目基线或已有 Benchmark；没有来源时不得发明固定毫秒、帧率或内存阈值。
- 复用项目已有 Macrobenchmark、Benchmark、Perfetto 或性能测试；Trace 分析必须基于真实数据。
- 保持设备、系统、variant、数据和操作路径一致，记录多轮结果及项目采用的 P50/P95 等指标。
- 模拟器只能用于流程调通和趋势参考；正式性能结论原则上使用固定真机。
- 没有真机、基线或 Trace 时保持性能未验证，不阻断其他门禁继续执行。

## UI 与 A11y

触发：布局、可见状态、交互控件、文案、图标、Compose semantics、焦点、字体或主题变化。

- 视觉还原继续由 `android-verify-ui` 手动独立验收；自动化 A11y 与 UI 功能测试由 `android-test-and-fix` 执行。
- 检查语义标签、装饰元素排除、可点击区域、焦点顺序、状态描述、错误提示、字体缩放以及不能只靠颜色表达状态。
- 优先复用项目已有 Compose/Espresso semantics、AccessibilityChecks 或其他测试；Accessibility Scanner/TalkBack 可作为设备或人工证据。
- 没有设备时继续静态资源与 semantics 检查；动态 TalkBack、焦点和触摸体验保持未验证。
- 没有设计稿只影响视觉一致性，不自动阻断可访问性静态检查。

## 安全隐私

触发：权限、Manifest 导出组件、DeepLink、WebView、网络安全配置、Token/Cookie、用户数据、日志、埋点、文件或剪贴板变化。

- 识别数据类型、来源、存储、传输、日志/埋点、生命周期、信任边界和导出入口；资料不足时不得猜测数据敏感等级。
- 检查 exported 组件、Intent/DeepLink 输入、WebView JS Bridge/文件访问/混合内容、明文 HTTP、本地敏感存储和 release 调试入口。
- 检查日志、Crashlytics、Analytics、通知、截图和剪贴板是否暴露 PII、Token、密码或密钥。
- 优先运行项目已有 Android lint、detekt、Semgrep、MobSF 或安全任务；不自动安装，也不把静态审查写成渗透测试通过。
- 缺少后端、证书、真机或生产配置时记录能力损失；确认的敏感信息泄漏按 P0 处理。

## 职责归属

| 能力 | 主责 Skill | 执行协作 |
| --- | --- | --- |
| OpenAPI | `android-verify-api-contract` | `android-test-and-fix` 执行契约相关测试 |
| 数据迁移 | `android-test-and-fix` | `android-review-diff` 复核范围和回滚风险 |
| 动态泄漏 | `android-audit-stability` | `android-test-and-fix` 复现和重验 |
| 性能 | `android-audit-stability` | `android-test-and-fix` 执行 Benchmark/Trace 流程 |
| UI/A11y | `android-verify-ui` 负责人工表现，`android-test-and-fix` 负责自动测试 | 总入口只提示独立视觉验收 |
| 安全隐私 | `android-audit-stability` 负责风险，`android-review-diff` 负责变更边界 | `android-test-and-fix` 执行已有安全任务 |

## 完成结论

- 所有适用且属于明确验收标准的能力有新鲜通过证据，才可声明完整交付。
- 不适用项有需求和 diff 依据，可以正常跳过。
- 未验证项不停止其他门禁，但必须进入最终报告；若它是必需验收则结论为未完成/受阻。
- 没有真机但不涉及真机必需验收时，允许声明“代码与本地自动门禁完成，真机专项待验证”，不得缩写为“全部通过”。
