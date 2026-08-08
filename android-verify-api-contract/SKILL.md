---
name: android-verify-api-contract
description: Android API 实现与接口契约核验。用于涉及网络层（Retrofit/OkHttp/Ktor/自研）、DTO、Repository、mapper、缓存、鉴权、错误码、Mock/sampledata 的改动，依据 YApi/Apifox/Swagger/OpenAPI 文档和实际 diff 核验 endpoint、请求参数、响应字段、nullable、枚举、错误码、映射和兼容性。检测到 API/DTO/Repository 网络行为变化、私有接口页需登录授权，或用户要求核对接口实现时使用；无接口契约变化时跳过。
---

# Android API 契约核验

## 共享规则

执行本 Skill 前，必须先遵守 `../_shared/android-global-rules.md`。

## 职责边界

- **负责**：核验客户端 API、DTO、mapper、网络 Repository 与明确契约是否一致。
- **不负责**：判断产品需求、通用架构质量、页面视觉、运行时全量稳定性或完整测试门禁。
- **资料底线**：没有契约证据时报告缺口，不猜 endpoint、字段、枚举或错误码。

## 输入解析

优先读取：

- 实际 diff 中涉及的 API service、DTO、mapper、Repository、DataSource、缓存、mock、sampledata 和测试。
- Swagger / OpenAPI 链接或 JSON 文件。
- Apifox、YApi、Postman、Markdown 接口文档。
- 后端口头说明、聊天记录摘要、字段表；这些必须标明来源性质，不能冒充正式服务端契约。
- 项目已有网络封装、统一 Response、错误处理、鉴权刷新和日志脱敏逻辑。

接口资料缺失但需求已经明确时，允许根据需求建立业务字段、领域模型、Repository / DataSource 抽象、Mock / Fake 和标记待对齐的临时契约；这些内容不等于正式后端契约。不得把推测的接口地址、请求方式、JSON 字段名、字段类型、枚举值或错误码写成已确认事实。

## 登录态与契约归一化

- 用户提供 API 链接、截图、文件或聊天契约时，不再询问“是否需要处理接口”；直接读取并生成或增量更新唯一 `<requirement_dir>/api/api.md`。
- 当前需求或 diff 涉及接口契约且配置了 `api.links` 时，先检测并复用本机 Chrome 已有登录状态，只读取页面可见内容。
- 读取 YApi、Apifox 等结构化响应树时，对 object 和 array 节点递归展开到叶子字段，并滚动读取当前 operation 的完整字段；首次可见文本不是读取完成的依据。
- 折叠节点、虚拟滚动未渲染或当前 DOM 不含子项，只表示“尚未读完”，不得据此断言 schema、类型或必填性缺失。用户截图与首次读取结论不一致时，先重新核对展开和滚动状态；只有完整读取后仍不一致，才记录来源冲突或未知项。
- 如果链接落到登录页、返回 401/403 或提示无权限，标记 `USER_INPUT_REQUIRED`，请用户在 Chrome 登录或授权并回复“已经登录”，随后重试原链接；不得索要、读取或保存账号、密码、Cookie 和会话存储。
- 未获得登录状态前，停止依赖该契约的 endpoint、DTO、mapper、Repository 和测试实现。已有 `api.files` 只能作为历史或替代证据，不能自动代表用户同意跳过在线来源。
- 只有用户明确要求使用现有本地证据、跳过链接或先 mock/fake 时才降级；与接口无关的独立范围可以继续并说明隔离依据。
- 资料读取成功后，把来源定位、读取状态、method/path、请求参数、响应字段、必填性、可空性、分页、错误、冲突和未知项合并到 `api/api.md`；文档已存在时只更新当前 operation，禁止覆盖或删除其他接口。
- 原始 JSON、OpenAPI、Postman/YApi 导出和用户提供的截图按原形与 `api.md` 共置在 `<requirement_dir>/api/`；`api/api.md` 与采用的稳定文件一起登记到 `api.files` 以绑定内容摘要，不为每个来源生成另一份摘要。
- 只有会改变产品行为、客户端采用方式或验收结果的契约结论才同步到 `requirement_file`；纯字段证据留在 `api/api.md`，避免需求正文复制完整接口文档。
- 在线页面、本地证据或页面内部字段相互矛盾时保持 `partial`、未验证或阻断，逐项请求用户/接口负责人确认，不根据客户端现状替后端决定。

登录阻塞时使用面向用户的中文提示，至少包含：无法读取的链接、当前看到的登录/权限现象、请在本机 Chrome 登录、无需提供任何凭据、登录后回复“已经登录”。

## 序列化框架识别

核对字段契约前，必须先从依赖、插件、DTO 注解、adapter/serializer 和网络配置识别本次真实使用的序列化框架，不能仅凭 Kotlin data class 或某依赖存在就假定生效。按项目实际情况检查 kotlinx.serialization（`@Serializable`/`@SerialName`/`Json` 配置）、Moshi（`@JsonClass`/`@Json`/codegen adapter）、Gson（`@SerializedName`/TypeAdapter，注意 Kotlin 非空属性缺字段的运行时风险）、Jackson（Kotlin module/`@JsonProperty`/ObjectMapper 配置）或自定义混合方案（Converter/手写 parser/反射边界），逐框架核对未知字段策略、未知枚举处理和 nullable 真实行为。没有识别到框架或关键配置时写"序列化行为未确认"，不得默认按 kotlinx.serialization 解释，也不得为统一检查引入或迁移新框架。

Java DTO 或 Java/Kotlin 混合模型还必须核对：primitive 与 boxed 对缺字段/显式 null 的不同结果（如 `int` vs `Integer`）；Nullability 注解是否真实参与编译/静态分析/运行时 adapter；序列化实际用字段/构造器/Getter/Setter 还是生成 adapter（不能按 data class 推断 Java Bean）；泛型/继承/多态/未知子类型的真实 adapter/TypeToken 配置；反射序列化或生成 adapter 受 R8/ProGuard 影响时路由到稳定性和测试门禁执行项目已有 release/minify 验证，不自动增加宽泛 keep 规则。

## 契约检查清单

编码后必须检查：

- 接口路径、请求方式、baseUrl、鉴权方式是否与文档一致。
- 请求参数：必填、可选、默认值、分页、排序、筛选是否完整。
- 字段可空性必须严格来自实际契约：区分 OpenAPI schema 的 `required`、`nullable` 和客户端默认值，再结合真实序列化框架判断“字段缺失”与“显式 null”。契约未确认时不得凭业务语境断言非空，也不得把所有字段一律改成 nullable/default 来掩盖缺失契约。
- 状态枚举：核对未知枚举、服务端新增枚举和项目实际 serializer/adapter 的行为；没有明确 Unknown/default 契约时不得脑补兜底值。
- 未知字段：确认真实配置是忽略还是失败，并检查其与前后兼容要求一致；不能把“忽略未知字段”误写成“未知枚举安全”。
- 字段命名：逐项核对 `@SerialName`、`@Json`、`@SerializedName`、`@JsonProperty` 或自定义映射，避免只比较 Kotlin 属性名。
- 错误码：业务错误、登录过期、权限不足、服务端异常、限流是否接入项目统一处理。
- 网络异常：超时、无网络、弱网、重试、取消是否处理。
- 数据分层：DTO 是否通过 mapper 转成领域模型，UI 是否避免直接依赖原始 DTO。
- 本地缓存：接口数据和缓存数据结构是否兼容，旧缓存是否安全。
- Mock / 测试数据：是否只存在于 debug、fake、sampledata 或测试范围，没有混入 release 生产逻辑。

## OpenAPI 条件门禁

仅当接口候选存在且本次变更能关联到正式 OpenAPI/Swagger 契约时执行机器校验；详细共同规则见 `../android-implement-and-verify/references/conditional-capability-gates.md`。

执行顺序：

1. 记录本地契约文件、正式导出或可访问链接，确认版本/摘要和本次涉及的 operation/schema。
2. 识别本次 endpoint 实际使用的序列化框架、converter、全局/局部配置和自定义 adapter；无法确认时记录证据缺口。
3. 优先运行目标项目或本机已有 OpenAPI 校验命令；不得自动安装校验器或生成器。
4. 核对本次 operation 的 method/path、参数位置、`required`、`nullable`、默认值、类型、格式、枚举、错误响应和引用 schema。
5. 对照 DTO、字段命名注解、未知字段策略、未知枚举策略、mapper、Repository 与相关测试，记录每个不一致的真实位置。
6. 修复后重新运行机器校验和受影响测试，保存最终命令、退出码与报告。

状态边界：

- 无 API 契约变化：不适用，正常跳过。
- profile 的 `api.status` 不是 `confirmed`：专项最高为未验证或受阻，不得标记通过。
- 有正式契约且机器校验与实现核对通过：通过。
- 有契约但没有成熟校验器：人工核对可以继续，但机器校验标为未验证。
- 需求要求接正式接口但契约缺失、无法读取或互相冲突：阻断正式网络接入和契约通过，不阻断根据已确认需求完成领域模型、Fake、业务逻辑、临时 UI 及其测试。
- 不得自动运行 OpenAPI Generator 覆盖旧项目网络层，也不得把生成成功等同于业务契约通过。

## 编码前阻塞使用边界

如果在编码前触发本 Skill，只允许判断是否能安全编码：

- 需求已明确业务含义但缺 endpoint、请求方式或 baseUrl：继续领域模型、抽象边界、Mock / Fake、业务逻辑和测试，正式网络接入保持待对齐。
- 缺关键请求参数、响应字段、枚举或错误码，且正式联调依赖这些事实：阻塞正式 DTO / Endpoint 和契约通过，不把 Unknown/default 当作正式契约替代品。
- 需求本身也无法确定金额、权限、安全、持久化或关键业务分支：暂停对应业务实现并请求最小必要输入。
- 后端返回格式不稳定时，UI 只依赖稳定领域模型，不直接依赖临时或原始 DTO。
- Mock / Fake / sampledata 可以继续支撑业务闭环，但必须避免进入 release 生产逻辑，并明确记录正式资料到达后的替换位置和受影响测试。

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
2. 实际序列化框架、converter、配置与自定义 adapter
3. OpenAPI 适用性、operation/schema 和机器校验证据
4. `required` / `nullable` / 默认值 / unknown keys / unknown enum / 字段命名映射
5. 已确认契约
6. 实现一致性结论
7. 待确认字段 / 枚举 / 错误码
8. 兼容性风险
9. 不应进入生产代码的部分
10. 建议测试项

由 `android-implement-and-verify` 编排时，同时按 `../android-implement-and-verify/references/specialist-result.schema.json` 输出统一专项结果；记录契约摘要、operation/schema、机器能力状态、P0-P3 和未关闭项。缺少正式契约或存在未关闭 P0/P1 时不得标记 `PASS`。

统一专项结果的 API 机器字段必须满足：

- `capabilities` 包含 `{"id":"api-contract","required":true,"status":"PASS|UNVERIFIED|BLOCKED|FAIL"}`；正式契约缺失、无法访问或冲突时不能写 `PASS`。
- `checks` 至少包含 `contract-source`（契约来源/版本/摘要）、`operation-schema`（本次 method/path/参数/schema/错误响应）、`implementation-mapping`（DTO/mapper/Repository/测试映射）。
- `executed_checks` 必须等于实际 checks 数量；`PASS` 时上述三项检查均需完成且通过。
- `artifacts` 至少绑定一个未变化文件：OpenAPI/Swagger/Postman/YApi 导出、结构化 Markdown 契约摘要、截图或核对报告，并填写 `sha256`。
- 无 artifact、无 operation/schema、只凭客户端代码或自然语言总结，不得输出 `PASS`；应输出 `UNVERIFIED`、`BLOCKED` 或带 P0/P1 的 `FAIL`。
