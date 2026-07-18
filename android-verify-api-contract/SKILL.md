---
name: android-verify-api-contract
description: Android API 实现与接口契约核验。用于涉及 Retrofit、OkHttp、Ktor、自研网络层、DTO、Repository、mapper、缓存、分页、鉴权、错误码、Mock 或 sampledata 的改动，依据接口文档和实际 diff 核验 endpoint、请求参数、响应字段、nullable、枚举、错误码、映射和兼容性。检测到 API/DTO/Repository 网络行为变化，或用户要求核对接口实现时使用；无接口契约变化时跳过。
---

# Android API 契约核验

## 共享规则

执行本 Skill 前，必须先遵守 `../_shared/android-global-rules.md`：默认中文输出、动态资料不写死、接口和 UI 不确定时不脑补、不伪造验证结果、发现问题默认先报告不自动修复。

## 定位

默认用于编码后审查接口实现是否符合契约，而不是需求确认后的固定前置分析阶段。核心目标是确认实际代码没有脑补生产接口、没有遗漏错误处理、没有让 UI 直接依赖不稳定 DTO。

只有当关键接口资料缺失、继续编码会写死假 endpoint / 假字段 / 假枚举时，才在编码前暂停使用本 Skill 输出阻塞问题。

## 职责边界

- **负责**：核验客户端 API、DTO、mapper、网络 Repository 与明确契约是否一致。
- **调用**：接口、字段、鉴权、分页、错误码或网络缓存契约发生变化时。
- **不负责**：判断产品需求、通用架构质量、页面视觉、运行时全量稳定性或完整测试门禁。
- **资料底线**：没有契约证据时报告缺口，不猜 endpoint、字段、枚举或错误码。

## 输入解析

优先读取：

- 实际 diff 中涉及的 API service、DTO、mapper、Repository、DataSource、缓存、mock、sampledata 和测试。
- Swagger / OpenAPI 链接或 JSON 文件。
- Apifox、YApi、Postman、Markdown 接口文档。
- 后端口头说明、聊天记录摘要、字段表。
- 项目已有网络封装、统一 Response、错误处理、鉴权刷新和日志脱敏逻辑。

接口资料缺失时，不得脑补接口地址、字段名、字段类型、枚举值或错误码。

## 契约检查清单

编码后必须检查：

- 接口路径、请求方式、baseUrl、鉴权方式是否与文档一致。
- 请求参数：必填、可选、默认值、分页、排序、筛选是否完整。
- 字段可空性必须严格来自实际契约：同时检查 OpenAPI schema 的 `required` 列表、`nullable`、类型和项目序列化策略。契约未确认时不得凭业务语境断言非空，也不得把所有字段一律改成 nullable/default 来掩盖缺失契约。
- 状态枚举：未知枚举、服务端新增枚举、默认兜底是否安全。
- 错误码：业务错误、登录过期、权限不足、服务端异常、限流是否接入项目统一处理。
- 网络异常：超时、无网络、弱网、重试、取消是否处理。
- 数据分层：DTO 是否通过 mapper 转成领域模型，UI 是否避免直接依赖原始 DTO。
- 本地缓存：接口数据和缓存数据结构是否兼容，旧缓存是否安全。
- Mock / 测试数据：是否只存在于 debug、fake、sampledata 或测试范围，没有混入 release 生产逻辑。

## OpenAPI 条件门禁

仅当接口候选存在且本次变更能关联到正式 OpenAPI/Swagger 契约时执行机器校验；详细共同规则见 `../android-implement-and-verify/references/conditional-capability-gates.md`。

执行顺序：

1. 记录本地契约文件、正式导出或可访问链接，确认版本/摘要和本次涉及的 operation/schema。
2. 优先运行目标项目或本机已有 OpenAPI 校验命令；不得自动安装校验器或生成器。
3. 核对本次 operation 的 method/path、参数位置、`required`、`nullable`、类型、格式、枚举、错误响应和引用 schema。
4. 对照 DTO、序列化注解、mapper、Repository 与相关测试，记录每个不一致的真实位置。
5. 修复后重新运行机器校验和受影响测试，保存最终命令、退出码与报告。

状态边界：

- 无 API 契约变化：不适用，正常跳过。
- 有正式契约且机器校验与实现核对通过：通过。
- 有契约但没有成熟校验器：人工核对可以继续，但机器校验标为未验证。
- 需求要求接正式接口但契约缺失、无法读取或互相冲突：阻断接口实现/通过，不阻断其他独立范围继续验证。
- 不得自动运行 OpenAPI Generator 覆盖旧项目网络层，也不得把生成成功等同于业务契约通过。

## 编码前阻塞使用边界

如果在编码前触发本 Skill，只允许判断是否能安全编码：

- 缺 endpoint、请求方式或 baseUrl，且需求要求接正式接口：阻塞。
- 缺关键请求参数或响应字段，且字段会影响业务逻辑：阻塞。
- 缺关键枚举或错误码，且没有 Unknown/default 兜底策略：阻塞。
- 后端返回格式不稳定，且 UI 需要直接展示关键字段：阻塞。
- 用户允许先做 mock / fake / sampledata：可以继续编码，但必须避免写入 release 生产逻辑。

不得为了推进编码而自造正式 DTO、endpoint、枚举或错误码。

## 接入和修复建议

优先复用项目已有：

- Retrofit / OkHttp / Ktor / 自研网络封装。
- 统一 Response 包装、错误处理、鉴权刷新、日志脱敏。
- DTO → Domain Model mapper。
- Repository / DataSource / UseCase 分层。
- MockWebServer、fake repository、sampledata 测试方式。

## 输出格式

编码后审查按发现点输出，严重程度从高到低：

- 严重级别：P0 / P1 / P2 / P3
- 类型：endpoint / 请求参数 / 响应字段 / nullable / 枚举 / 错误码 / 缓存 / mock 泄漏 / 测试缺口
- 位置：文件、类、方法、行号或 diff 片段
- 契约来源
- 问题说明
- 影响后果
- 修复建议
- 是否建议立即修复

最后汇总：

1. 接口资料来源
2. OpenAPI 适用性、operation/schema 和机器校验证据
3. 已确认契约
4. 实现一致性结论
5. 待确认字段 / 枚举 / 错误码
6. 兼容性风险
7. 不应进入生产代码的部分
8. 建议测试项
