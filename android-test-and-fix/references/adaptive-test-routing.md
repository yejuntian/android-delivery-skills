# Android 自适应自动化测试路由

本文定义如何把已确认需求转换为分层自动化测试，尤其处理无 UI、UI 与业务混合、Journey 只能覆盖部分步骤、老项目缺少现代测试能力以及没有设备的情况。日常简单需求不必全文加载；出现混合影响、Journey 能力边界、测试层选择或最终证据缺口时读取。

## 目录

1. [核心目标](#核心目标)
2. [BDD 场景与测试证据](#bdd-场景与测试证据)
3. [影响类别与测试路由](#影响类别与测试路由)
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

## BDD 场景与测试证据

### 拆分规则

读取当前确认修订中的 `BDD-###`。独立触发、异常、恢复或能够单独通过/失败的结果必须在需求事实源中拆成独立 BDD 场景；同一触发下不可分割的结果可用 `And`，不再创建 `/T#` 或 `AC-###` 子编号。

例如：

```text
BDD-001：用户选择优惠券后开关显示选中
BDD-002：用户选择优惠券后订单金额由 100 变为 80
BDD-003：用户提交优惠订单时请求包含正确 couponId
BDD-004：优惠订单提交失败后显示可重试状态
BDD-005：用户重启应用后仍保留已确认的本地选择
```

每个场景都在需求文件中写完整 Given/When/Then。禁止把“页面显示提交成功”同时当作金额、请求字段、服务端写入和本地持久化全部正确的证据。

### 建立覆盖矩阵

为每个 BDD 场景记录：

```text
当前需求修订 / BDD-###
→ 影响类别与证据要求
→ 需要证明的行为
→ 一个或多个真实测试 ID
→ 主执行器与备用执行器
→ 命令和运行条件
→ 证据与状态
→ 剩余缺口
```

主执行器应当是维护成本最低但证据足够的能力。备用执行器只有覆盖相同输入、运行条件、断言和证据边界时才算等价；较弱证据只能记录能力损失。

## 影响类别与测试路由

先记录 BDD、实际 diff、影响类别、预期文件和可执行前置条件，再由确定性路由选择能够证明这些结果的测试层。

- `ui`：Compose/Espresso、截图、A11y 或独立 UI 验收。
- `api`：契约、DTO、请求字段和错误码测试，必要时执行 `android-verify-api-contract`。
- `data`：DAO、缓存、旧数据和迁移测试。
- `system`：权限、通知、后台、WebView、文件和版本兼容测试。
- `build` / `architecture`：构建、依赖解析、模块方向和静态检查。
- `tests`：测试断言、映射和执行收据复核。

需求确认阶段只生成测试映射和必要骨架，不启动设备或 Journey。编码后由脚本路径候选与 Diff Reviewer 的 `confirmed_impacts` 取并集，登记全部适用专项；没有可执行条件时标记 `UNVERIFIED` 或 `BLOCKED`，不能用主观判断跳过验证。代码、测试、资源或构建配置变化后，受影响证据失效并重新执行对应门禁。

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

不自动引入新的测试框架、服务或长期测试体系。项目已有工具可以复用；新增依赖必须由用户明确批准。

## Journey 适用性

### 三级判定

| 级别 | 判定条件 | 执行动作 |
| --- | --- | --- |
| `FULL` | BDD 中全部用户可见操作和可见断言都能由 Journey 稳定完成 | 物化并执行完整 Journey；场景内非 UI 结果仍由其他测试层共同证明 |
| `PARTIAL` | Journey 只能稳定完成其中部分用户可见操作或可见断言 | 只为可覆盖步骤生成 Journey；其余结果路由到其他能力并汇总到同一 BDD |
| `NONE` | 没有 UI 行为、只有视觉变化，或 Given/When/Then 无法由 Journey 可靠表达 | 不启动 Journey 引擎，使用其他测试或人工路径 |

`FULL/PARTIAL/NONE` 是每条 BDD 用户旅程的适用性，不是测试通过状态。Journey `PASS` 只为它实际覆盖的 BDD 场景提供一部分证据。

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
- 设备只能完成部分 Journey 时，先把能够独立闭环的可见路径拆成短 Journey 并重跑通过，再按 BDD 场景记录剩余缺口；中断前的截图只作过程证据，不能直接算自动覆盖：

| 环境限制 | 后续处理 |
| --- | --- |
| DNS 或真实接口不可控 | 使用 Fake/MockWebServer 验证业务状态；真实连通性仍标未验证 |
| ROM 禁止 shell 点击或滑动 | 转项目已有 Compose/Espresso/UIAutomator，或已有可控模拟器；当前 ROM 只保留实际完成或人工证据 |
| 性能、泄漏或 ANR | 转 Benchmark、Perfetto 或稳定性专项；Journey 只提供复现入口 |

- 低 AGP 目标项目继续使用自己的 wrapper 构建 APK；默认由当前 AI 会话使用 Android CLI/adb 对已安装 APK 执行 Journey，不要求初始化 Studio 壳。已经初始化的独立壳只作可选回退，同样不升级或修改目标项目。
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

- 普通 `COVERED_AUTOMATED` 必须有最终代码上的单 gate 收据，并把该 BDD 场景映射到 JUnit 报告中真实通过的 testcase；测试总数大于零不能替代具体映射。Agent Journey 则必须引用实际执行的 action/check、数量和布局/截图产物。
- `android-test-and-fix` 和 `android-data-migration` 的自动 gate 证据本身也必须包含实际执行数大于零的本轮 JUnit；接口、UI/A11y、安全、泄漏和性能使用对应专项结果，不能用任意成功命令加同名 `gate_id` 占位。
- `COVERED_MANUAL` 只允许用于已经实际完成并保留执行人、带时区时间、环境、步骤、预期、实际结果和产物的业务/迁移/安全人工验收；UI 视觉验收不使用此状态承载，改由独立 `android-verify-ui` 结果记录 Figma 与真机截图/差异图链接。没有产物时说明原因，计划由人工执行只能写 `UNVERIFIED`。
- Journey、截图、Unit 或静态扫描的通过都不能越过自身证据边界。
- 替代测试必须覆盖同一 BDD 场景、输入、运行条件和证据边界；能力损失必须保留为未验证。
- 所有必需 BDD 场景均为 `COVERED_AUTOMATED` 或实际 `COVERED_MANUAL` 后，才允许整体全绿。

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

Journey 可以是 `PARTIAL` 并通过，但同一 BDD 所需的业务、接口或数据结果也有证据时，该场景才算覆盖。

### 小改动

需求：只调整标题间距和图标。

```text
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
