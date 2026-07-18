# Kotlin / Java / Android 静态语义分析

本文定义 `android-audit-stability` 在 Kotlin、Java 和混合 Android 项目中审查生命周期、资源所有权、异步任务、并发与语言边界的通用方法。它不是漏洞关键词清单，也不替代项目已有静态工具、LeakCanary 或设备复现。

## 目录

1. [使用时机](#使用时机)
2. [目标与边界](#目标与边界)
3. [事实与证据优先级](#事实与证据优先级)
4. [静态分析步骤](#静态分析步骤)
5. [六条通用不变量](#六条通用不变量)
6. [资源所有权表](#资源所有权表)
7. [Kotlin、Java 与 Android 语义映射](#kotlinjava-与-android-语义映射)
8. [Kotlin 与 Java 混合边界](#kotlin-与-java-混合边界)
9. [并发访问表](#并发访问表)
10. [必要调用链复核](#必要调用链复核)
11. [生成代码与不透明边界](#生成代码与不透明边界)
12. [项目已有工具的使用边界](#项目已有工具的使用边界)
13. [老项目历史债务隔离](#老项目历史债务隔离)
14. [静态与动态结论边界](#静态与动态结论边界)
15. [输出模板](#输出模板)
16. [维护原则](#维护原则)

## 使用时机

出现以下任一候选时读取本文：

- Kotlin、Java 或混合代码修改了生命周期对象、异步任务、监听器、回调或可关闭资源。
- Java/Kotlin 互调修改了 Nullability、公开方法、默认参数、异常、泛型、SAM/Callback 或异步转换边界。
- diff 涉及 Activity、Fragment、View、Compose、ViewModel、Service、Receiver、WebView、Camera、Media、Location 或 Sensor。
- diff 涉及 CoroutineScope、Job、Flow、Channel、callbackFlow、stateIn、shareIn 或 Compose Effect。
- diff 涉及 Handler、Executor、Future、RxJava、共享可变状态、锁、Atomic、线程或调度器切换。
- diff 涉及反射、注解生成、AIDL、JNI、闭源 SDK、R8/ProGuard 或 release 专有行为。
- 用户报告内存增长、页面退出后仍回调、重复订阅、任务未取消、崩溃、ANR 或资源占用。
- 静态工具产生生命周期、资源释放、协程或引用逃逸告警，需要结合真实调用链复核。

纯文档、纯资源文案或与运行时所有权无关的改动不必机械加载本文。

## 目标与边界

目标是回答：本次改动是否破坏对象、任务或资源的所有权与生命周期关系。

- 以语义和调用关系为中心，不以文件名或正则命中数量代替判断。
- Kotlin 是现代 Android 优先方向，Java 是老项目的一等支持语言；共用一套模型，不复制第二套流程。
- 兼容 XML View、Compose、RxJava 和低 AGP 老项目，不强制迁移技术栈。
- 只审查与需求和最终 diff 有关的路径，再扩展到直接受影响的创建、持有和清理位置。
- 静态审查负责发现可由代码证明的问题或风险；动态泄漏、长期内存和设备行为仍需要动态证据。
- 不自动安装工具、添加 Gradle 插件、更新依赖、创建 baseline 或批量 suppress。

## 事实与证据优先级

按以下顺序建立事实，不用通用经验覆盖项目真实约定：

1. 用户已确认的需求、BDD 和明确验收标准。
2. 目标项目的 `AGENTS.md`、`CONTRIBUTING.md`、模块说明和现有架构约束。
3. 最终 diff、相关调用链、生命周期入口和清理路径。
4. 项目已有测试、Lint、Kotlin/Java 专项工具、Semgrep/CodeQL 配置及其新鲜执行结果。
5. Android、AndroidX、Kotlin、Java/JVM 和所用库的官方契约。
6. 通用 Android/Kotlin/Java 经验，仅用于提出待验证候选，不能冒充项目事实。

工具告警是证据入口，不是最终结论。工具未告警也不能证明不存在泄漏或并发问题。

## 静态分析步骤

### 1. 确认审查边界

- 从已确认需求和最终 diff 标出新增、删除或改变的行为。
- 找出直接调用者、被调用者、对象创建点、持有点和生命周期终点。
- 区分本次新增风险、已有风险和无法归因于本次改动的观察项。

### 2. 识别所有者与资源

对每个候选对象回答：

- 谁创建它？
- 谁持有它？
- 谁允许使用它？
- 它应当存活多久？
- 谁负责取消、解绑、关闭或置空？
- 引用是否逃逸到更长生命周期的对象或异步任务？

### 3. 建立资源所有权表

生命周期或资源候选存在时必须建立所有权表。表中未知项写“未确认”，不得按习惯补齐。

### 4. 验证六条不变量

逐条验证适用的不变量。发现违反时必须给出创建、持有、触发和清理路径的代码证据。

### 5. 复核必要调用链

只沿能证明所有权、逃逸、释放或并发关系的调用链展开，避免无边界阅读整个仓库。

### 6. 对照已有工具与历史基线

读取项目已有配置、报告和可比较基线，确认规则是否实际启用、报告是否来自最终代码，并区分新增、受影响、历史和来源不明告警。

### 7. 给出有边界的结论

明确区分“明确静态问题”“未发现明确静态问题”“证据不足”和“动态未验证”。

## 六条通用不变量

### 不变量 1：短生命周期对象不能被长生命周期对象持有

Activity、Fragment、View、ViewBinding、Dialog 及其隐式引用，不应逃逸到 Application、Singleton、`object`、静态字段、长驻线程或无界缓存。

判断重点：

- 持有关系是强引用还是可证明安全的短时引用。
- lambda、匿名内部类、协程和回调是否隐式捕获宿主。
- Context 的实际类型和用途是否要求 Activity，而不是仅看变量名。
- 长生命周期持有是否存在明确、可达且及时的释放路径。

### 不变量 2：注册与解绑必须成对

Listener、Callback、Observer、Receiver、ContentObserver、传感器监听和第三方 SDK 注册，必须由同一所有权边界负责解绑。

判断重点：

- 注册可能执行几次，解绑是否覆盖相同次数和相同实例。
- 生命周期重复进入/退出时是否重复注册或漏解绑。
- 异常、提前返回和部分初始化时，解绑是否仍可达。
- 第三方 API 的解绑契约是否要求原 Callback 实例或额外 Token。

### 不变量 3：获取与释放必须成对

Stream、Cursor、Socket、File、ParcelFileDescriptor、Camera、Media、WebView 等资源必须在所有终止路径释放。

判断重点：

- 优先确认 `use`、`try/finally` 或框架生命周期是否真实覆盖资源。
- 初始化中途失败时，已获取资源是否仍会释放。
- 重复关闭是否安全，释放后是否还会被异步回调使用。
- 释放的是实际持有实例，而不是后来覆盖的新实例。

### 不变量 4：异步任务生命周期不能超过宿主

协程、Flow 收集、线程、Handler、Runnable、Timer、Future 和回调任务必须受明确所有者约束，并在宿主结束时取消或停止产生副作用。

判断重点：

- Scope/Job 的所有者、父子关系和取消入口是否明确。
- 页面销毁后是否仍访问 View、更新已失效状态或启动导航。
- 取消是否被吞掉，阻塞调用是否实际响应取消。
- 热流共享作用域是否与数据所有者一致，而不是与临时页面偶然绑定。

### 不变量 5：清理路径必须真实可达

代码中“写了 cleanup”不等于一定执行。正常、异常、取消、提前返回、重复进入退出和部分初始化路径都必须能到达正确清理逻辑。

判断重点：

- 生命周期回调是否一定与创建阶段配对，例如 Fragment View 与 Fragment 本身不能混淆。
- key、条件分支和状态位是否让清理对应到正确实例。
- cleanup 自身抛错或被取消时，后续资源是否仍能释放。
- 回调晚到、并发关闭或重复调用时是否保持幂等。

### 不变量 6：共享可变状态必须有并发纪律

跨线程、调度器或异步回调访问的共享状态，必须有单一所有者、线程约束、不可变快照或明确同步策略。

判断重点：

- 写入者与读取者实际运行在哪个线程、Looper、Executor、Scheduler 或 Dispatcher。
- `volatile` 只保证可见性，是否被错误当成复合操作原子性保证。
- `synchronized`、Lock、Atomic、Mutex 或串行队列是否保护同一状态和完整临界区。
- check-then-act、集合遍历修改、延迟回调和旧请求晚返回是否存在竞态。
- 锁顺序、阻塞 Future、主线程等待或同步 Binder 调用是否可能形成死锁或 ANR。

## 资源所有权表

使用以下固定列；只记录与本次需求和调用链相关的对象：

| 对象/资源 | 创建位置 | 持有者 | 预期生命周期 | 释放/取消位置 | 引用逃逸 | 证据/风险 |
| --- | --- | --- | --- | --- | --- | --- |
| 示例：页面 Listener | `onViewCreated` | Fragment View | `onDestroyView` 前 | 未确认 | 第三方 SDK 持有 | 需核对 unregister 契约 |

填写规则：

- “持有者”写真实对象，不写模糊的“系统”或“框架”。
- “预期生命周期”来自项目和 API 契约；不确定时标未确认。
- “释放/取消位置”必须能定位到文件、方法或框架保证。
- “引用逃逸”说明逃逸目标、引用类型和持续条件。
- 没有候选时不生成空表；有候选但信息不足时保留未知项并列入剩余风险。

## Kotlin、Java 与 Android 语义映射

以下内容是六条不变量的常见应用，不是需要无限扩充的漏洞枚举。

### CoroutineScope 与 Job

- 确认 Scope 由 ViewModel、LifecycleOwner、Repository、Application 或调用方中的谁拥有。
- 自建 Scope 必须有可定位的取消入口；`GlobalScope` 和无父 Job 需要证明其进程级生命周期合理。
- `viewModelScope`、`lifecycleScope` 并不自动保证内部持有的外部资源正确释放。
- 检查 `CancellationException` 是否被宽泛 `catch` 吞掉，以及阻塞工作是否切换到合适 dispatcher。

### Flow、Channel 与共享状态

- `callbackFlow` 必须核对注册成功、`awaitClose`、解绑实例和异常关闭路径；不能只检查是否出现 `awaitClose` 字样。
- `stateIn` / `shareIn` 的 Scope 和 `SharingStarted` 必须与数据所有者和订阅预期一致。
- 页面收集优先沿用项目已有生命周期方式；检查重复 collect、多个收集者副作用和旧请求晚返回。
- Channel/Flow 完成、取消或关闭后，不应继续持有失效页面对象或发送不可达结果。

### Jetpack Compose

- `LaunchedEffect` 的 key 应表达任务重启边界；key 错误可能造成任务不重启或无意义重启。
- `DisposableEffect` 的注册和 `onDispose` 必须作用于同一实例，key 变化时也能正确清理。
- `rememberCoroutineScope` 只应服务于对应 Composition 生命周期，不应逃逸给长生命周期单例或缓存。
- `remember`、lambda 和 state holder 需要检查是否捕获 Activity、View 或过期参数。

### 传统 Android 组件

- Fragment ViewBinding 的所有权通常截止 `onDestroyView`，不能默认延长到 Fragment 销毁。
- Listener、Receiver、Observer、WebView、Camera 和 Media 的具体释放点必须服从目标 API 和项目现有封装。
- `object`、`companion object`、静态字段、长驻 Repository 或缓存中的 lambda 可能隐式捕获 Activity/View。
- Handler/Runnable 即使延时很短，也要核对宿主销毁、队列清理和回调晚到路径。

### Java 与老项目

- Java 匿名内部类、非静态内部类、lambda、Handler/Runnable 和静态集合按相同所有权不变量审查，确认是否隐式持有 Activity/Fragment/View。
- Handler、Message、Thread、Executor、Future 和 Timer 必须有明确所有者、取消/关闭入口与回调晚到策略。
- Listener、Callback、Receiver、ContentObserver、`observeForever` 必须核对注册次数、原实例和对应解绑位置。
- RxJava 核对 Disposable/CompositeDisposable 所有者、Scheduler、终止事件、重复订阅和生命周期清理。
- Cursor、Stream、Socket、ParcelFileDescriptor 等优先核对 try-with-resources 或覆盖全部出口的 finally。
- AsyncTask、Loader、旧 Service、自研线程池或旧式 Callback 沿用其真实 cancel/dispose/unregister 契约。
- `WeakReference` 不是默认修复；先修正不合理所有权，只有 API 契约确实需要弱引用时才采用。
- 不因旧项目缺少 Lifecycle、Compose 或协程就要求迁移；只验证现有机制能否守住不变量。

## Kotlin 与 Java 混合边界

只有真实混合调用或公共契约变化时检查以下内容，不机械要求添加 JVM 注解：

- Java 无 Nullability 契约的返回值在 Kotlin 中形成 platform type，直接解引用前必须有项目事实或边界校验。
- Java 调用 Kotlin 非空参数、属性或泛型时，确认 Java 侧是否能传入 null，以及失败位置是否可接受。
- primitive/boxed、可变/只读集合、数组、泛型通配符和 SAM/Callback 转换不能改变空值、所有权或可变性语义。
- Kotlin 默认参数、顶层函数、companion、`@JvmStatic`、`@JvmOverloads`、suspend API 只按真实 Java 调用方和既有公开契约核对。
- Java checked exception、Kotlin 未声明异常、Future/RxJava 与 coroutine/Flow 桥接时，确认异常和取消能双向传播。
- 公共方法、字段、构造器或接口变化时，区分源码兼容、二进制兼容和行为兼容；优先执行项目已有 ABI/API 检查任务。

## 并发访问表

存在共享可变状态、锁或多调度器候选时，除资源所有权表外按需输出：

| 共享状态 | 写入者 | 读取者 | 线程/调度器 | 同步或串行保证 | 证据/风险 |
| --- | --- | --- | --- | --- | --- |
| 示例：页面结果缓存 | 网络回调 | 主线程渲染 | IO → Main | 未确认 | 旧请求可能覆盖新状态 |

没有并发候选时不生成空表；线程或同步策略无法确认时写“未确认”，并保留动态或压力测试风险。

## 必要调用链复核

最小调用链通常包括：

```text
创建/注册/启动
→ 持有或订阅
→ 正常使用
→ 生命周期结束、异常、取消或重复进入
→ 释放/解绑/关闭
```

按以下规则控制范围：

- 向上追到能确定所有者和调用时机的最近入口。
- 向下追到能确定资源获取、副作用和清理契约的最近实现。
- 跨模块时只读取直接边界、接口实现和 DI 绑定，不无目的展开全部消费者。
- 遇到反射、代码生成、第三方闭源 SDK 或运行时注入时，记录静态证据边界并转为动态或人工验证项。
- 只有跨文件证据能改变结论时才扩展调用链；文件名或规则命中本身不是扩展理由。

## 生成代码与不透明边界

- 注解处理器、KAPT/KSP、DataBinding、AIDL 等生成产物优先通过生成任务和编译验证；不直接修改生成文件。
- 反射、动态代理、ServiceLoader、JNI/native、插件化和运行时 DI 无法由普通调用链完整证明时，审查手写边界的输入、输出、线程、所有权和异常契约。
- 第三方闭源 SDK 优先读取正式契约、已有封装和项目测试；契约不可得时标记静态证据不足，不猜内部持有或线程行为。
- 反射序列化、代码生成、JNI 或 keep 规则变化时，按条件执行项目已有 release/minify/R8 验证；没有可执行 variant 时把 release 行为标为未验证。
- 不为验证自动升级 AGP、Gradle、JDK、依赖或关闭混淆；Release 特有问题只添加能由证据支持的最小 keep 规则。

## 项目已有工具的使用边界

执行命令由 `android-test-and-fix` 负责，本 Skill 解释与复核结果。

优先级如下：

1. 项目已有 Kotlin/Java 编译和 Android Lint。
2. Kotlin 项目已配置的 detekt，或 Java 项目已配置的 Error Prone、NullAway、SpotBugs、Infer。
3. 项目已有 PMD/Checkstyle 等质量任务时保留其结果，但不把风格通过当成稳定性证明。
4. 项目已有 Semgrep binary/config/rules 时的 Kotlin/Java 扫描。
5. 项目或 CI 已配置 CodeQL、ABI/API 检查时的跨文件或公共契约结果。
6. 针对适用风险的 LeakCanary、Leak Trace、Heap Dump、release/R8 或设备复现。

共同边界：

- 不自动安装、不修改版本、不接入新插件。
- 不自动创建或更新 baseline，不批量 suppress 告警。
- 先确认规则配置、扫描范围、退出码和报告时间，再使用结果。
- Semgrep 社区能力或单文件规则不能冒充完整跨函数/跨模块证明。
- CodeQL 支持 Kotlin/Java 也不代表项目已配置或查询覆盖当前框架语义。
- 工具无告警只能说明其已启用规则未发现命中，不能证明无泄漏。

## 老项目历史债务隔离

已有报告或可比较基线时，将告警按本次需求归为：

| 分类 | 判定 | 处理 |
| --- | --- | --- |
| `NEW` | 本次 diff 新增 | P0/P1 必须关闭；其余按门禁规则处理 |
| `AFFECTED` | 原问题位于本次直接调用链，且改动可能触发或放大 | 结合真实证据处理或阻断 |
| `PRE_EXISTING` | 本次需求开始前已存在且不在直接影响面 | 记录但不扩大本次修改 |
| `UNKNOWN_ORIGIN` | 缺少基线、报告不可比或位置无法归因 | 不脑补来源，记录能力损失 |

- 不更新 baseline、改规则或加 suppress 掩盖 `NEW`。
- 不为了清理 `PRE_EXISTING` 扩大需求范围，也不能用历史告警数量忽略 `NEW`。
- 没有可靠基线时只能按当前 diff 和调用链判断；无法归因的告警不自动算通过或生产缺陷。
- 完成声明必须关闭本次新增和直接受影响的 P0/P1；无关历史债务进入剩余风险，不混入本次修复。

## 静态与动态结论边界

允许的静态结论：

- **明确静态问题**：调用链和 API 契约足以证明某条不变量被破坏。
- **未发现明确静态问题**：已审查指定 diff、调用链和已有工具结果，未找到可由静态证据证明的问题。
- **静态证据不足**：关键持有者、第三方契约、生成代码、运行时绑定或清理路径无法确认。

动态状态单独记录：

- **动态通过**：适用的复现路径在明确设备与工具上取得新鲜结构化证据，且验收条件满足。
- **动态未验证**：无设备、无复现条件、无项目已有工具或证据不足。
- **动态失败**：新鲜证据确认泄漏、资源未释放、崩溃或其他运行时异常。

禁止使用以下结论：

- “静态检查通过，所以绝对没有内存泄漏。”
- “detekt/SpotBugs/Semgrep/CodeQL 没有告警，所以生命周期安全或线程安全。”
- “页面退出后内存下降，所以没有泄漏。”
- “没有设备，因此稳定性检查全部失败或全部跳过。”

## 输出模板

```text
Kotlin/Java/Android 静态语义审查：
- 触发依据：需求 / diff / 工具告警 / 用户问题
- 审查边界：文件、入口、直接调用链
- 语言形态：Kotlin / Java / 混合
- 适用不变量：1 / 2 / 3 / 4 / 5 / 6
- 资源所有权表：见表格
- 并发访问表：适用时见表格
- 混合语言/公开契约：适用性、调用方和 ABI/API 证据
- 项目已有工具：命令、配置、退出码、报告路径；未执行时说明原因
- 告警归因：NEW / AFFECTED / PRE_EXISTING / UNKNOWN_ORIGIN
- 生成/反射/JNI/闭源边界：已确认事实与证据缺口
- release/R8：适用性、variant、命令与结论
- 明确静态问题：位置、触发路径、违反的不变量、影响
- 静态结论：明确静态问题 / 未发现明确静态问题 / 静态证据不足
- 动态适用性：适用 / 不适用
- 动态证据：设备、路径、工具和结果
- 动态结论：通过 / 失败 / 未验证
- 能力损失与剩余风险：
```

## 维护原则

- 新语言或框架先映射到六条不变量和边界契约，不复制新的完整审查流程。
- 不把一次项目缺陷扩写成全局强制规则；先记录其 API 契约和适用条件。
- 工具列表变化时只调整发现和执行策略，不改变“项目已有工具优先、缺失不安装”的边界。
- 更新本文后，同步稳定性 Skill、测试执行 Skill、行为评测场景和开源设计依据。
