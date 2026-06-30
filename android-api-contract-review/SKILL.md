---
name: android-api-contract-review
description: Android 后端接口契约、字段兼容、OpenAPI、Swagger、Apifox、YApi、Postman、接口文档和后端不确定性审查流程。适用于需求涉及网络请求、请求参数、响应字段、状态枚举、错误码、分页、鉴权、缓存或接口尚未完全确定时，防止 AI 脑补生产接口并输出待确认问题。
---

# Android 接口契约审查

## 共享规则

执行本 Skill 前，必须先遵守 `../_shared/android-global-rules.md`：默认中文输出、动态资料不写死、接口和 UI 不确定时不脑补、不伪造验证结果、发现问题默认先报告不自动修复。

## 定位

用于在接入后端前审查接口契约，尤其适合接口还没完全确定、后端字段可能变化、只有口头说明或临时文档的场景。

## 输入解析

支持动态输入：

- Swagger / OpenAPI 链接或 JSON 文件。
- Apifox、YApi、Postman、Markdown 接口文档。
- 后端口头说明、聊天记录摘要、字段表。
- 现有 DTO、API service、Repository、Mock 数据。

接口资料缺失时，不得脑补接口地址、字段名、字段类型、枚举值或错误码。

## 契约检查清单

必须检查：

- 接口路径、请求方式、baseUrl、鉴权方式。
- 请求参数：必填、可选、默认值、分页、排序、筛选。
- 响应结构：字段类型、nullable、缺省值、空数组、空对象。
- 状态枚举：未知枚举、服务端新增枚举、默认兜底。
- 错误码：业务错误、登录过期、权限不足、服务端异常、限流。
- 网络异常：超时、无网络、弱网、重试、取消。
- 本地缓存：接口数据和缓存数据结构是否兼容。
- Mock / 测试数据是否需要同步更新。

## 不确定时的编码边界

- 字段未确认：不得写正式 DTO 和 mapper；可以写领域模型草案或 TODO 注明待确认。
- 接口未确认：不得写死正式 endpoint；可以使用 debug-only fake 或项目已有 sampledata。
- 枚举未确认：必须保留 Unknown / default 兜底方案。
- 错误码未确认：必须保留通用错误处理和可扩展分支。
- 后端返回格式不稳定：不要让 UI 直接依赖原始 DTO。

## 接入建议

优先复用项目已有：

- Retrofit / OkHttp / Ktor / 自研网络封装。
- 统一 Response 包装、错误处理、鉴权刷新、日志脱敏。
- DTO → Domain Model mapper。
- Repository / DataSource / UseCase 分层。
- MockWebServer、fake repository、sampledata 测试方式。

## 输出格式

1. 接口资料来源
2. 已确认契约
3. 合理假设
4. 待确认字段 / 枚举 / 错误码
5. 阻塞项
6. 兼容性风险
7. 可先做部分
8. 暂不建议写入生产代码的部分
9. 接入方案
10. 测试建议

