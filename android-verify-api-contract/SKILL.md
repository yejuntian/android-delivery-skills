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
- **绝对契约驱动底线（禁止盲目信任）**：把所有后端的接口字段当成不可信的！审查 DTO 时，除非 Swagger/接口文档明确标明 `required=true`，否则**所有网络响应字段必须强制声明为可空类型（如 Kotlin 的 `String?`）或赋予安全默认值**。严禁结合业务语境去“脑补”某个字段是否必然非空，必须全盘防御。
- 状态枚举：未知枚举、服务端新增枚举、默认兜底是否安全。
- 错误码：业务错误、登录过期、权限不足、服务端异常、限流是否接入项目统一处理。
- 网络异常：超时、无网络、弱网、重试、取消是否处理。
- 数据分层：DTO 是否通过 mapper 转成领域模型，UI 是否避免直接依赖原始 DTO。
- 本地缓存：接口数据和缓存数据结构是否兼容，旧缓存是否安全。
- Mock / 测试数据：是否只存在于 debug、fake、sampledata 或测试范围，没有混入 release 生产逻辑。

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
2. 已确认契约
3. 实现一致性结论
4. 待确认字段 / 枚举 / 错误码
5. 兼容性风险
6. 不应进入生产代码的部分
7. 建议测试项
