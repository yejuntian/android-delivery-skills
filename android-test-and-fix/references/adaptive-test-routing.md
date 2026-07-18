# Android 自适应自动化测试路由

本文定义如何把已确认需求转换为分层自动化测试，尤其处理无 UI、UI 与业务混合、Journey 只能覆盖部分步骤、老项目缺少现代测试能力以及没有设备的情况。日常简单需求不必全文加载；出现混合影响、Journey 能力边界、测试层选择或最终证据缺口时读取。

## 目录

1. [核心目标](#核心目标)
2. [原子验证义务](#原子验证义务)
3. [风险等级与两次判定](#风险等级与两次判定)
4. [选择测试层](#选择测试层)
5. [Journey 适用性](#journey-适用性)
6. [能力缺口路由](#能力缺口路由)
7. [环境与工具降级](#环境与工具降级)
8. [报告与完成门禁](#报告与完成门禁)
9. [典型示例](#典型示例)

## 核心目标

执行以下不变量：

- 把 Journey、Compose UI Test、Espresso、UIAutomator、Unit、Integration、Contract、Screenshot 和人工验收视为不同证据执行器，不把任何单一工具当成需求测试总入口。
- 为每个已确认验收结果选择能够证明该行为的最低且足够的测试层；使用大量快速确定的小测试和少量高保真的完整流程。
- 优先复用目标项目已有框架、Gradle task、fixture 和报告；缺少能力时记录损失，不自动安装工具、升级 AGP/Gradle/JDK 或迁移架构。
- 让 Journey 只验证少量关键、稳定、可见、可表达的用户旅程；Journey 通过不得覆盖它没有断言的业务、数据、契约、视觉或非功能风险。
- 不追求所有需求机械执行全部测试类型；只要求所有必需验证义务都有新鲜证据，或明确为未验证/阻塞。

## 原子验证义务

### 拆分规则

读取已确认 `REQ-###` 和 `BDD-###`，把每个复合 Then 拆成可独立证明的原子结果，使用 `BDD-001/T1`、`BDD-001/T2` 这样的局部标识，不新增持久化状态机。

例如：

```text
BDD-001：用户使用优惠券提交订单
- BDD-001/T1：优惠券开关显示选中
- BDD-001/T2：订单金额由 100 变为 80
- BDD-001/T3：请求包含正确 couponId
- BDD-001/T4：提交失败后显示可重试状态
- BDD-001/T5：重启后仍保留已确认的本地选择
```

禁止把“页面显示提交成功”同时当作金额、请求字段、服务端写入和本地持久化全部正确的证据。

### 建立覆盖矩阵

为每个原子验证义务记录：

```text
REQ-ID / BDD-ID / Then
→ 风险与必需性
→ 需要证明的行为
→ 主执行器
→ 备用执行器
→ 命令和运行条件
→ 证据与状态
→ 剩余缺口
```

主执行器应当是维护成本最低但证据足够的能力。备用执行器只有覆盖相同输入、运行条件、断言和风险时才算等价；较弱证据只能记录能力损失。

## 风险等级与两次判定

### 等级

| 等级 | 判定边界 | 默认验证范围 |
| --- | --- | --- |
| `L1` 轻量 | 改动局部、业务含义明确、单一影响面且没有高风险边界 | 受影响 Unit/截图、最小编译、lint 和直接回归 |
| `L2` 标准 | 可观察业务行为变化，或 UI、业务、数据、接口中两个以上影响面协作 | Unit/Component/Integration 加一条代表性 UI 或应用流程 |
| `L3` 强化 | 支付/金额、鉴权/隐私、数据迁移、并发、生命周期、权限/后台/硬件、公共 API、R8/反射、核心跨模块链路 | 多层确定性证据、设备或 Sandbox、受影响回归和候选版本验证 |
| `BLOCKED` | 缺少业务预期、接口契约、设计基准、旧 schema/样本或继续实现必需的输入 | 停止依赖该输入的实现与判绿，请求最小用户输入 |

不要按代码行数判断风险。一行金额阈值、数据库版本、`exported`、Scope 或 R8 规则也可能是 `L3`。

### 两次判定

1. 需求确认后根据 BDD 初判影响向量、风险等级、验证义务和候选测试层，只准备测试计划或骨架，不启动 Journey 壳。
2. 编码后根据最终 diff、调用链、构建变体和真实前置条件终判；发现新增影响时自动升级。只有证据证明影响收敛时才允许降级，并记录原因。
3. 任何生产代码、测试、资源或构建配置再次变化后，使受影响证据失效并重新执行对应门禁。

## 选择测试层

| 验证目标 | 首选能力 | 证据边界 |
| --- | --- | --- |
| Kotlin/Java 纯业务规则、金额、排序、边界 | JUnit、参数化测试 | 覆盖输入输出，不证明 Android 集成 |
| 大量输入或业务不变量 | 项目已有属性测试 | 业务不变量必须来自已确认需求，不由 AI 发明 |
| ViewModel、UseCase、UI State | 状态驱动 Unit、虚拟时间 | 不用内部方法调用次数代替行为 |
| Flow、Callback、并发和取消 | 项目已有 coroutine/Rx/Executor 测试能力 | 使用受控调度和顺序，不用 sleep 碰运气 |
| Repository、缓存、网络组合 | Integration、Fake、MockWebServer | 证明边界协作，不冒充正式后端通过 |
| OpenAPI、DTO、请求字段、错误码 | 契约测试、`android-verify-api-contract` | UI 成功提示不能替代契约证据 |
| Room、DataStore、旧数据 | DAO/迁移/Instrumentation | 新库建库成功不能替代旧版本迁移 |
| Compose App 内语义和交互 | Compose UI Test | 适合节点、状态和时间控制 |
| 传统 View App 内交互 | Espresso | 适合 View、Intent 和确定性同步 |
| 已安装 APK 的简单关键旅程 | Journey | 只证明实际操作与可见断言 |
| 权限框、通知、设置、文件选择、跨应用 | UIAutomator | 需要设备；优先项目已有能力 |
| WebView/Hybrid | Espresso-Web 或项目已有 Appium | 外部动态网站仍需 Sandbox/人工 |
| UI 外观和视觉回归 | 项目已有 Paparazzi/Roborazzi/Shot | 只证明截图，不证明真实业务 |
| A11y | Semantics、AccessibilityChecks、动态辅助技术验证 | 静态检查不能冒充 TalkBack 通过 |
| 生命周期、旋转、进程恢复 | Robolectric、Instrumentation、adb | Robolectric 不冒充厂商 ROM 或硬件 |
| 泄漏、性能、ANR | 项目已有 Leak/Heap、Benchmark、Perfetto | Journey 只能提供复现入口 |
| 验证码、真实支付、闭源第三方、真实硬件 | Mock/Sandbox 加实际人工或真机专项 | 没有真实证据时保持未验证或阻塞 |

不自动引入 Maestro、Appium、Kaspresso、属性测试或 Mutation 工具。项目已有时可以复用；新增依赖、服务或长期测试体系必须由用户明确批准。

## Journey 适用性

### 三级判定

| 级别 | 判定条件 | 执行动作 |
| --- | --- | --- |
| `FULL` | BDD 中全部用户可见操作和可见断言都能由 Journey 稳定完成 | 物化并执行完整 Journey；非 UI/不可见 Then 仍由其他测试层证明 |
| `PARTIAL` | Journey 只能稳定完成其中部分用户可见操作或可见断言 | 只为可覆盖的 Then 生成 Journey；其余 Then 路由到其他能力并保留独立状态 |
| `NONE` | 没有 UI 行为、只有视觉变化，或 Given/When/Then 无法由 Journey 可靠表达 | 不启动壳，使用其他测试或人工路径 |

`FULL/PARTIAL/NONE` 是每条 BDD 用户旅程的适用性，不是测试通过状态。Journey `PASS` 只更新它实际覆盖的原子 Then。

### Journey 使用底线

- 只选择本次需求的一到少量高价值主流程、直接回归流程或 Bug 复现/恢复流程。
- 不用 Journey 穷举金额、枚举、空值、分页、时区和大量状态组合。
- 不用 Journey 证明请求体、数据库、泄漏、性能、安全、像素或全部设备兼容。
- Journey 引擎不支持某动作时记录能力缺口，不把它归因成生产实现失败。
- Journey 仍适合黑盒 UI 且只是引擎能力不足时，才考虑项目已有或用户允许的 Maestro；业务上不适合 Journey 的场景通常也不适合 Maestro。

## 能力缺口路由

先判断缺口类型，再选择能力：

| 缺口类型 | 处理方式 |
| --- | --- |
| 动作无法表达 | App 内优先 Compose/Espresso；系统或跨应用优先 UIAutomator；黑盒仍适用且已有体系时考虑 Maestro/Appium |
| Given 无法稳定准备 | 使用测试账号、Fake、Sandbox、DeepLink 或 debug/test 范围的数据注入；不得把测试后门带入 release |
| Then 属于不可见内部状态 | 下沉到 Unit、Repository、数据库或契约测试，不增加虚假 UI 断言 |
| 地图、Canvas、视频、相机缺少稳定节点 | 拆分状态逻辑、Provider 和视觉证据；必要时使用局部仪器/真机/人工，不依赖脆弱坐标作为唯一证据 |
| 复杂手势或精确时序 | 使用项目已有确定性 UI/仪器能力、受控时间和条件等待，不添加固定 sleep |
| 第三方授权、验证码、支付 | 使用 Mock/Sandbox 覆盖自有边界；真实闭环必须获得授权并使用隔离环境，否则未验证/阻塞 |
| 无法获得等价自动证据 | 只有实际执行并保留证据后才能标人工覆盖；未执行时保持未验证 |

## 环境与工具降级

- 没有设备时继续编译、Unit、参数化、Robolectric、Repository、MockWebServer、契约、截图和静态门禁；只把需要设备的验证义务标为未验证。
- 模拟器可以等价证明功能、迁移或基础 A11y 时继续执行；正式性能、厂商 ROM 和真实硬件不得用模拟器冒充。
- 低 AGP 目标项目继续使用自己的 wrapper 构建 APK；Journey 壳只做黑盒 Journey，不升级或修改目标项目。
- 优先复用目标项目已有 Compose/Espresso/UIAutomator；需要为老项目补外部 UIAutomator 时单独设计执行能力，不把逻辑塞进 `run_journey.py`。
- 工具失败先标 `ENVIRONMENT_FAILED` 并保留原始证据。AI 可以选择等价工具和最小修复，但不能模拟执行结果。
- 明确验收所必需的能力没有等价证据时，完整交付保持未完成/受阻；这不否定其他已完成范围。

## 报告与完成门禁

### 三个正交维度

不要把适用性、覆盖状态和失败原因混成一个状态：

1. **适用性**：每条 BDD 用户旅程的 Journey 使用 `FULL/PARTIAL/NONE`，其他条件能力使用适用/不适用。
2. **覆盖状态**：`COVERED_AUTOMATED`、`COVERED_MANUAL`、`UNVERIFIED`、`BLOCKED`、`NOT_APPLICABLE`。
3. **失败分类**：`REQUIREMENT_BLOCKED`、`ENVIRONMENT_FAILED`、`TEST_FAILED`、`IMPLEMENTATION_FAILED`、`UNKNOWN`。

这些值只作为本次报告标签，不建立跨需求缓存或持久化状态机。

### 防假绿门禁

- `COVERED_AUTOMATED` 必须有最终代码上的命令、退出码、测试数或工具限制说明、关键输出和报告路径。
- `COVERED_MANUAL` 只允许用于已经实际完成并保留步骤、结果和证据的人工验收；计划由人工执行只能写 `UNVERIFIED`。
- Journey、截图、Unit 或静态扫描的通过都不能越过自身证据边界。
- 替代测试必须覆盖同一 BDD/Then、输入、运行条件和风险；能力损失必须保留为未验证。
- 所有必需 Then 均为 `COVERED_AUTOMATED` 或实际 `COVERED_MANUAL` 后，才允许整体全绿。

## 典型示例

### UI 与业务混合

需求：用户在结算页选择优惠券并提交订单。

```text
开关选中和页面跳转        → Journey 或 Compose/Espresso
金额、会员、边界和旧规则  → 参数化 Unit
couponId 和错误码          → MockWebServer/OpenAPI
订单缓存或恢复             → Repository/数据库测试
第三方支付                 → Sandbox；真实闭环按授权人工验证
```

Journey 可以是 `PARTIAL` 并通过，但只有其他必需 Then 也有证据时整条 BDD 才通过。

### 小改动

需求：只调整标题间距和图标。

```text
风险等级                  → L1
Journey                   → NONE / SKIPPED_VISUAL_ONLY
验证                      → 项目已有截图、最小构建、lint
设计还原                  → 独立 android-verify-ui
```

不因为项目存在页面就启动设备和 Journey。

### 没有设备

需求：修改重试按钮以及错误到成功的状态恢复，当前没有模拟器或真机。

```text
ViewModel 状态和重复点击    → 本地自动覆盖
请求失败/成功              → Fake 或 MockWebServer 自动覆盖
真实按钮点击和页面显示      → UNVERIFIED（需要设备）
最终声明                    → 本地门禁完成，UI 动态验证待完成
```

不得把本地状态测试改写成真实 UI 已通过。
